#!/usr/bin/env bash
# options_trader_v3/install_candle_logger_timer.sh — install the EOD candle-logger timer on a box.
# v1.1 — 2026-07-10 — The 16:05 ET candle-logger.timer was never installed by any deploy script
#        (setup_ec2 enables only optionsbot + candle-feed; install_eod_timer installs the 15:50 P&L
#        writer, NOT the logger), so forensic 1-min OHLC CSVs were only ever produced by hand.
#        This creates candle-logger.service (oneshot) + candle-logger.timer (Mon-Fri 16:05 ET) and
#        enables the timer. The service runs `pull_today_ohlc.sh __work`, which captures the FULL
#        session (the v3 store is pruned to ~240 1m bars, so it rebuilds 09:30→close via one
#        synchronous candle_feed --once before reading) — so the nightly CSV matches the manual pull.
#        No secrets in the unit: __work sources TT_* from the running optionsbot unit at run time.
#        Idempotent. Fast (well under fleet's ~22s SSH ceiling): the validation kick is --no-block.
#
#        ⚠ TIMING: 16:05 assumes the box is still UP at 16:05. If the control server's EOD sweep
#        stops boxes earlier (e.g. 15:55), this timer never fires — move the stop after 16:06, or
#        fold the OHLC pull into the control-server EOD flow (see the note returned to the operator).
# Run per box (from the control server):
#   python fleet.py run 'bash ~/options-trader/install_candle_logger_timer.sh'
set -uo pipefail

DIR=/home/ubuntu/options-trader
SVC=/etc/systemd/system/candle-logger.service
TMR=/etc/systemd/system/candle-logger.timer
BOTUNIT=optionsbot
WORKER="$DIR/pull_today_ohlc.sh"

# ── Sanity: the worker the service calls must be present on this box ───────────
[ -f "$WORKER" ] || { echo "🚨 $WORKER missing — sync the repo (git pull) before installing."; exit 1; }

# ── Instrument + creds check from the RUNNING bot unit (single source of truth) ─
EL=$(systemctl show "$BOTUNIT" -p Environment --value 2>/dev/null)
gv() { echo "$EL" | tr ' ' '\n' | grep "^$1=" | head -1 | cut -d= -f2-; }
INSTRUMENT=$(gv OT_INSTRUMENT)
CS=$(gv TT_CLIENT_SECRET); RT=$(gv TT_REFRESH_TOKEN); AN=$(gv TT_ACCOUNT_NUMBER)

[ -n "$INSTRUMENT" ] || { echo "🚨 OT_INSTRUMENT not found in $BOTUNIT unit — aborting."; exit 1; }
if [ -z "$CS" ] || [ -z "$RT" ] || [ -z "$AN" ]; then
    echo "🚨 TT_* creds not found in the $BOTUNIT unit on this box — a full-session capture needs them"
    echo "   (v3 --once refill / v2 self-subscribe). Aborting rather than install a partial/0-bar timer."
    exit 1
fi

IS_V3=0; [ -f "$DIR/data/candle_feed.py" ] && IS_V3=1

# ── Service (oneshot). No secrets in the unit — __work sources them at run time. ─
sudo tee "$SVC" > /dev/null <<UNITEOF
[Unit]
Description=OPT_Trader EOD 1-min candle logger — full-session capture ($([ "$IS_V3" = 1 ] && echo 'v3' || echo 'v2'))
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=${DIR}
Environment=OT_INSTRUMENT=${INSTRUMENT}
ExecStart=/bin/bash ${WORKER} __work
UNITEOF
sudo chmod 644 "$SVC"

# ── Timer: weekdays 16:05 ET (after the 16:00 close, so the session is complete) ─
sudo tee "$TMR" > /dev/null <<'TMREOF'
[Unit]
Description=OPT_Trader EOD candle logger timer (Mon-Fri 16:05 ET)

[Timer]
OnCalendar=Mon..Fri 16:05 America/New_York
Persistent=false
AccuracySec=30s

[Install]
WantedBy=timers.target
TMREOF
sudo chmod 644 "$TMR"

# ── Activate (idempotent) ──────────────────────────────────────────────────────
sudo systemctl daemon-reload
sudo systemctl enable --now candle-logger.timer >/dev/null 2>&1
# Kick today's capture now (non-blocking so the SSH call returns immediately).
sudo systemctl start --no-block candle-logger.service 2>/dev/null || true

echo "✅ candle-logger.timer enabled on $(hostname) (instrument=${INSTRUMENT}, v$([ "$IS_V3" = 1 ] && echo 3 || echo 2))"
systemctl list-timers candle-logger.timer --no-pager 2>/dev/null | sed -n '1,2p'
echo "   validate today's output (give it ~60s):  bash ~/options-trader/pull_today_ohlc.sh --check"
