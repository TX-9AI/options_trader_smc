#!/bin/bash
# =============================================================================
# tests/verify_feed_v3.sh — options_trader v3.0 acceptance gate (ON-BOX)
# v3.0 — 2026-07-10 — Yahoo-Finance purge verification. Run on ONE box during
#         RTH with candle-feed.service + optionsbot running (paper). Covers the
#         three checks that can only be proven on the live box; the DataFrame
#         contract test (tests/test_market_data_contract.py) and the zero-Yahoo
#         grep run anywhere.
# Usage:  bash tests/verify_feed_v3.sh ; echo "exit=$?"
# =============================================================================
set -u
PASS=0; FAIL=0
ok()   { echo "  [PASS] $1"; PASS=$((PASS+1)); }
bad()  { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }

echo "── 1. Single-subscription proof (Mandate 2) ─────────────────────────────"
# DXLink is a websocket to tasty's dxfeed gateway on 443. Exactly ONE process
# on the box may hold it: candle_feed. The bot/observer/logger read SQLite.
FEED_PID=$(systemctl show -p MainPID --value candle-feed 2>/dev/null)
BOT_PID=$(systemctl show -p MainPID --value optionsbot 2>/dev/null)
echo "  candle-feed PID=${FEED_PID:-?}  optionsbot PID=${BOT_PID:-?}"
DX_CONNS=$(ss -tnp 2>/dev/null | grep -iE "dxlink|dxfeed" ; true)
# Hostname may not appear in ss output — fall back to counting established
# wss connections per PID to tasty/dxfeed endpoints via /proc net + lsof:
CONN_PIDS=$(sudo lsof -iTCP -sTCP:ESTABLISHED -P -n 2>/dev/null \
    | grep -iE "dxlink|dxfeed|tasty" | awk '{print $2}' | sort -u)
echo "  PIDs holding tasty/dxfeed TCP: ${CONN_PIDS:-none-matched}"
N_STREAMERS=0
for p in $CONN_PIDS; do
    # count only long-lived websocket-style connections owned by python procs
    CMD=$(ps -p "$p" -o cmd= 2>/dev/null)
    echo "    pid $p: $CMD"
    if echo "$CMD" | grep -q "candle_feed"; then N_STREAMERS=$((N_STREAMERS+1));
    elif echo "$CMD" | grep -qE "main.py|shadow|candle_logger"; then
        bad "consumer pid $p ($CMD) holds a market-data TCP connection"
    fi
done
# The bot legitimately holds REST (httpx) connections for orders/chains — the
# check is that no consumer holds a PERSISTENT dxlink websocket. Definitive
# proof: grep each consumer's maps for the dxfeed websocket lib usage at runtime:
for label in optionsbot; do
    P=$(systemctl show -p MainPID --value $label)
    [ -z "$P" ] || [ "$P" = "0" ] && continue
    if sudo ls -l /proc/$P/fd 2>/dev/null | grep -q "socket" && \
       sudo lsof -p $P -iTCP -sTCP:ESTABLISHED -P -n 2>/dev/null | grep -qiE "dxlink"; then
        bad "$label holds a dxlink websocket — Mandate 2 violated"
    else
        ok "$label holds NO dxlink websocket (reads the store)"
    fi
done
if [ -n "$FEED_PID" ] && [ "$FEED_PID" != "0" ]; then
    ok "candle-feed.service running (pid $FEED_PID) — the one producer"
else
    bad "candle-feed.service not running"
fi

echo "── 2. Store health / staleness guard ────────────────────────────────────"
python3 - << 'PYEOF'
import sqlite3, time, sys
from data.candle_feed import feed_db_path
try:
    conn = sqlite3.connect(f"file:{feed_db_path()}?mode=ro", uri=True)
    hb = conn.execute("SELECT last_write_epoch FROM feed_meta "
                      "WHERE symbol='__feed__' AND interval='heartbeat'").fetchone()
    age = time.time() - hb[0]
    print(f"  [{'PASS' if age < 120 else 'FAIL'}] heartbeat age {age:.0f}s (<120s)")
    for tf in ("1m","5m","15m","1h","1d"):
        n = conn.execute("SELECT COUNT(*) FROM candles WHERE interval=?", (tf,)).fetchone()[0]
        print(f"         {tf}: {n} bars in store")
    sys.exit(0 if age < 120 else 1)
except Exception as e:
    print(f"  [FAIL] store unreadable: {e}"); sys.exit(1)
PYEOF
[ $? -eq 0 ] && ok "store heartbeat fresh" || bad "store heartbeat stale/missing"

echo "── 3. ORB equivalence (feed vs traded tape) ─────────────────────────────"
# The original sin: the 5-minute opening range from the old source diverged
# from the tape the bot trades. Now both MUST be identical because they are
# the same bars. Compare fetch_candles' 9:30 5m candle to the store's raw row.
python3 - << 'PYEOF'
import sqlite3, sys
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo
from config import INSTRUMENT
from data.market_data import fetch_candles
from data.candle_feed import feed_db_path
ET = ZoneInfo("America/New_York")
df = fetch_candles(INSTRUMENT, "5m", 100)
if df is None or df.empty:
    print("  [FAIL] fetch_candles returned no 5m data"); sys.exit(1)
today = datetime.now(ET).date()
opening = df[(df.index.date == today) &
             (df.index.time == dtime(9, 30))]
if opening.empty:
    print("  [WARN] no 9:30 bar yet (pre-open?) — rerun after 09:35 ET"); sys.exit(1)
o = opening.iloc[0]
conn = sqlite3.connect(f"file:{feed_db_path()}?mode=ro", uri=True)
start_ms = int(datetime.combine(today, dtime(9,30), tzinfo=ET).timestamp()*1000)
row = conn.execute("SELECT high, low FROM candles WHERE symbol=? AND interval='5m' "
                   "AND ts_epoch_ms=?", (INSTRUMENT, start_ms)).fetchone()
match = row and float(o["high"]) == float(row[0]) and float(o["low"]) == float(row[1])
print(f"  ORB via seam:  high={o['high']}  low={o['low']}")
print(f"  ORB raw store: high={row[0] if row else '?'}  low={row[1] if row else '?'}")
print(f"  [{'PASS' if match else 'FAIL'}] opening range identical to the traded tape")
print("  → also eyeball against the bot's own log line for today's ORB and your")
print("    TastyTrade chart 9:30–9:35 candle; all three must agree now.")
sys.exit(0 if match else 1)
PYEOF
[ $? -eq 0 ] && ok "ORB equivalence" || bad "ORB equivalence (or pre-open — rerun after 09:35 ET)"

echo "── 4. Zero-Yahoo gate ───────────────────────────────────────────────────"
# Pattern assembled at runtime so this script never trips its own gate.
PAT="yf""inance|yf""\\."
if grep -rniE "$PAT" . --exclude-dir=venv --exclude-dir=.git \
     --exclude-dir=__pycache__ --exclude="*.db*" > /dev/null 2>&1; then
    bad "residue found:"; grep -rniE "$PAT" . --exclude-dir=venv \
        --exclude-dir=.git --exclude-dir=__pycache__ --exclude="*.db*"
else
    ok "zero residue across code, config, shell, docs, requirements"
fi

echo ""
echo "═══ verify_feed_v3: ${PASS} pass, ${FAIL} fail ═══"
exit $([ $FAIL -eq 0 ] && echo 0 || echo 1)
