#!/usr/bin/env bash
# options_trader_v3/pull_today_ohlc.sh — one-shot EOD retrieval of TODAY's FULL 1-min session on THIS box.
# v1.5 — 2026-08-04 — GUARD BACK ON BY DEFAULT. The v1.4 disable was a response
#        to a misdiagnosis: the failing backfill was `candle_feed --once` hanging
#        on ITS OWN RTH gate (v3.10), not this one. With that fixed, v1.3's
#        condition is correct and protects a real case — a pull fired at a
#        TRADING box mid-session stops its feed for ~200s while the bot reads a
#        frozen store. Reports and backfills are unaffected: they run against
#        boxes with no bot, or after the close. OT_PULL_RTH_GUARD=0 still
#        disables it.
# v1.4 — 2026-08-04 — RTH GUARD OFF BY DEFAULT (operator directive). Gated on
#        OT_PULL_RTH_GUARD; set it to 1 to restore v1.3 behaviour. The refusal
#        path is unchanged and still there — only its default flipped, so this
#        is one env var to reverse rather than a deletion to re-derive.
#        NOTE FOR THE LATER DISCUSSION: the 2026-08-04 16:28 backfill that
#        prompted this returned "0 full, 0 short, 14 still missing" with
#        "0 bot box(es) currently running" and POSTCLOSE=1 — a state where
#        NEITHER v1.1's guard NOR v1.3's could fire. Whatever blocked that run
#        was downstream of the guard entirely; the box-side
#        pull_today_ohlc.log holds the actual reason.
# v1.3 — 2026-08-04 — THE RTH GUARD WAS BLOCKING THE BACKFILL IT WAS NEVER MEANT
#        TO BLOCK. v1.1's test was "candle-feed live AND before 16:00 ET" — a
#        pure clock check. eod_backfill wakes SAT-OUT boxes mid-session to fetch
#        their candles; those boxes have a cold store and no trading bot, so the
#        guard refused the one rebuild that would have produced anything and the
#        script wrote a HEADER-ONLY csv instead. Measured 2026-08-04: fourteen
#        38-byte files against fifteen 15-16 KB ones from the boxes that were
#        already running. DXFeed history is SAME-EVENING ONLY, so every session
#        lost this way is lost permanently at midnight.
#        The guard now also requires `optionsbot` to be ACTIVE — that is the
#        consumer a feed stop would starve, and it is what the guard was for.
#        Post-close behaviour is unchanged; Mandate 2 is unchanged (the feed is
#        still stopped before the --once pass and restarted after).
# v1.2 — 2026-07-10 — Hoist TT_* cred fetch to the top of __work so BOTH the v3 --once refill and a
#        v2 self-subscribing logger run with creds in-process (v3 logger ignores them). This lets the
#        EOD timer's oneshot service call `__work` directly and keep NO secrets in the unit file.
# v1.1 — 2026-07-10 — Full-session correctness fix. The v3 candle-feed store is pruned to
#        max(need,60)*PRUNE_FACTOR = 240 one-minute bars, but an RTH session is ~390 (09:30-16:00),
#        so a plain store read after ~noon silently drops the morning (opening range / ORB window).
#        On v3 this now ALWAYS rebuilds the full session first via ONE synchronous producer pass
#        (data.candle_feed --once backfills 1m from 09:30 and flushes), stopping candle-feed first
#        so there is never a second live producer (Mandate 2), then reads+exports, then restores the
#        feed. Guard: if it is still RTH (before 16:00 ET) AND the feed is live, it will NOT stop the
#        feed (would starve the trading bot) — it reads the store and flags the result as partial.
#        Symbol is passed explicitly (--symbols) so it never depends on OT_INSTRUMENT being in env.
# v1.0 — 2026-07-10 — initial: background-detached retrieval (fleet.py run has a ~22s SSH ceiling;
#        a v2 drain / --once warm can exceed it), --check readout, v2/v3 aware.
#
# Usage (from the control server):
#   1) python fleet.py run 'bash ~/options-trader/pull_today_ohlc.sh'            # launch on all
#   2) (wait ~60s) python fleet.py run 'bash ~/options-trader/pull_today_ohlc.sh --check'
#   3) python fleet.py pull ohlc --day <today-ET>                                # SCP to control
set -uo pipefail

DIR=/home/ubuntu/options-trader
VENV="$DIR/venv"
PY="$VENV/bin/python"; [ -x "$PY" ] || PY=/usr/bin/python3
LOG="$DIR/pull_today_ohlc.log"
FULL_SESSION_BARS=380          # soft completeness threshold for the "short session" flag
cd "$DIR" 2>/dev/null || { echo "🚨 $DIR not found"; exit 9; }

TODAY=$(TZ=America/New_York date +%F)
SYM=$(systemctl show optionsbot -p Environment --value 2>/dev/null | tr ' ' '\n' | grep '^OT_INSTRUMENT=' | head -1 | cut -d= -f2-)
[ -n "$SYM" ] || SYM=$("$PY" -c 'from config import INSTRUMENT; print(INSTRUMENT)' 2>/dev/null)
CSV="$DIR/data/OHLC/$TODAY/${SYM}.csv"

csv_rows() { if [ -f "$CSV" ]; then echo $(( $(wc -l < "$CSV") - 1 )); else echo -1; fi; }
run_logger() { timeout 180 "$PY" -m data.candle_logger --date "$TODAY" --symbols "$SYM" 2>&1; }

# ── --check: fast status readout (well under the SSH ceiling) ─────────────────
if [ "${1:-}" = "--check" ]; then
    R=$(csv_rows)
    if   [ "$R" -ge "$FULL_SESSION_BARS" ]; then echo "✅ $SYM $TODAY: $R bars (full session)"
    elif [ "$R" -gt 0 ]; then echo "✅ $SYM $TODAY: $R bars (⚠ short of a full ~390-bar session)"
    elif [ "$R" -eq 0 ]; then echo "🚨 $SYM $TODAY: 0 bars (store empty / entitlement — see log)"
    else echo "… $SYM $TODAY: not written yet (still running?)"; tail -n 2 "$LOG" 2>/dev/null; fi
    exit 0
fi

# ── __work: the (possibly long) full-session retrieval; runs detached, logs to $LOG ──
if [ "${1:-}" = "__work" ]; then
    IS_V3=0; [ -f data/candle_feed.py ] && IS_V3=1
    NOWHM=$(( 10#$(TZ=America/New_York date +%H%M) ))
    POSTCLOSE=0; [ "$NOWHM" -ge 1600 ] && POSTCLOSE=1
    echo "=== $(date '+%F %T %Z') pull start $SYM $TODAY (v$([ "$IS_V3" = 1 ] && echo 3 || echo 2), postclose=$POSTCLOSE) ==="

    # Creds up front: the v3 --once refill needs them, and a v2 self-subscribing logger needs them
    # in-process. The v3 logger ignores them (it reads the store). Sourced from the running bot unit.
    EL=$(systemctl show optionsbot -p Environment --value 2>/dev/null)
    gv() { echo "$EL" | tr ' ' '\n' | grep "^$1=" | head -1 | cut -d= -f2-; }
    OT_INSTRUMENT=$(gv OT_INSTRUMENT)
    TT_CLIENT_SECRET=$(gv TT_CLIENT_SECRET)
    TT_REFRESH_TOKEN=$(gv TT_REFRESH_TOKEN)
    TT_ACCOUNT_NUMBER=$(gv TT_ACCOUNT_NUMBER)
    export OT_INSTRUMENT TT_CLIENT_SECRET TT_REFRESH_TOKEN TT_ACCOUNT_NUMBER
    HAVE_CREDS=0
    [ -n "$TT_CLIENT_SECRET" ] && [ -n "$TT_REFRESH_TOKEN" ] && [ -n "$TT_ACCOUNT_NUMBER" ] && HAVE_CREDS=1

    if [ "$IS_V3" = "1" ]; then
        FEED=$(systemctl is-active candle-feed 2>/dev/null || echo unknown)
        # v1.3 — THE GUARD NOW ASKS THE RIGHT QUESTION. It used to be
        # "feed live AND still RTH", i.e. a pure clock test — so a SAT-OUT box
        # woken mid-session purely to backfill was refused the rebuild, read its
        # COLD store, and wrote a HEADER-ONLY csv. Measured 2026-08-04: fourteen
        # 38-byte files at 11:11/11:18/11:23 ET while the fifteen trading boxes
        # wrote 15-16 KB. Two sessions of sat-out tape lost that way, and DXFeed
        # history is same-evening only, so each one is permanent at midnight.
        # WHAT THE GUARD IS ACTUALLY PROTECTING is a TRADING BOT on THIS box —
        # stopping candle-feed under a live optionsbot starves its analysis. A
        # box with optionsbot INACTIVE has no such consumer: stopping its feed
        # for one synchronous producer pass starves nobody, and that is exactly
        # the population backfill wakes.
        # MANDATE 2 IS UNAFFECTED. The feed is still stopped before the --once
        # pass and restarted after, so there is never a second live producer on
        # this box either way.
        BOT=$(systemctl is-active optionsbot 2>/dev/null || echo unknown)
        # v1.5 — RESTORED TO ON (default 1) now that the real cause is fixed.
        # v1.4 turned it off at operator direction while the backfill failure was
        # being diagnosed — and the diagnosis proved this guard was NOT the
        # cause: the 16:28 run was post-close with no bot running, a state where
        # it cannot fire. `candle_feed` v3.10 was. Leaving this off would have
        # removed a protection that IS correct to pay for a bug elsewhere.
        # `OT_PULL_RTH_GUARD=0` remains the escape hatch, and should sit unused —
        # a knob you HAVE to set is a design smell.
        # WHAT IS BEING GIVEN UP, stated so the re-enable decision is informed:
        # with the guard off, a pull fired at a TRADING box during RTH will stop
        # its candle-feed for the ~200s producer pass. Its bot keeps running but
        # reads a frozen store for that window — every engine that consumes 1m/5m
        # frames sees stale bars, and market_data v3.3's bar-recency guard will
        # start recording BLINDNESS. Mandate 2 still holds (feed stopped before
        # the pass, restarted after), so this is a starvation risk, never a
        # double-producer one.
        # IT IS NOT A RISK AT ALL ON A BOX WITH NO BOT, which is the population
        # eod_backfill wakes — hence v1.3's narrower condition, which this knob
        # now sits on top of rather than replacing.
        GUARD="${OT_PULL_RTH_GUARD:-1}"
        if [ "$GUARD" != "1" ]; then
            echo "RTH guard DISABLED via OT_PULL_RTH_GUARD=$GUARD (escape hatch; default is ON)."
            [ "$FEED" = "active" ] && [ "$POSTCLOSE" = "0" ] && [ "$BOT" = "active" ] && \
                echo "⚠ RTH + optionsbot ACTIVE on this box: the feed will be stopped for the refill and the bot will read a FROZEN store for ~200s."
        fi
        if [ "$GUARD" = "1" ] && [ "$FEED" = "active" ] && [ "$POSTCLOSE" = "0" ] && [ "$BOT" = "active" ]; then
            echo "RTH + feed live + optionsbot ACTIVE: NOT stopping the feed (would starve the bot)."
            echo "Reading store as-is; result may be PARTIAL (1m store holds ~240 bars)."
            echo "Re-run after 16:00 ET for a full session."
            run_logger
        else
            # Safe to rebuild the full session with a single producer pass:
            # either we are post-close, or no optionsbot is running on this box
            # to be starved by a brief feed stop. v1.3 says WHICH, because
            # "refilling" with no reason printed is how the old behaviour hid.
            if [ "$POSTCLOSE" = "1" ]; then
                echo "post-close: safe to rebuild"
            elif [ "$BOT" != "active" ]; then
                echo "RTH but optionsbot is $BOT (not trading on this box): safe to rebuild"
            else
                echo "RTH with a LIVE bot, rebuilding anyway because the guard is OFF"
            fi
            [ "$FEED" = "active" ] && { echo "stopping candle-feed for a single-producer refill"; sudo systemctl stop candle-feed; }
            if [ "$HAVE_CREDS" = "1" ]; then
                echo "refilling full session via one synchronous producer pass (candle_feed --once)"
                timeout 200 "$PY" -m data.candle_feed --once 2>&1
            else
                echo "cannot refill: TT_* creds not present in the optionsbot unit — reading store (may be partial)"
            fi
            [ "$FEED" = "active" ] && { echo "restarting candle-feed"; sudo systemctl start candle-feed; }
            run_logger
        fi
    else
        # v2: the logger self-subscribes to DXFeed from 09:30 → full session directly (needs creds).
        [ "$HAVE_CREDS" = "1" ] || echo "warning: v2 logger needs TT_* creds and none were found in the optionsbot unit"
        run_logger
    fi

    echo "=== $(date '+%F %T %Z') pull done: $(csv_rows) bars → $CSV ==="
    exit 0
fi

# ── default: detach the work so the SSH call returns immediately ──────────────
: > "$LOG" 2>/dev/null || true
setsid bash "$DIR/pull_today_ohlc.sh" __work >>"$LOG" 2>&1 </dev/null &
disown 2>/dev/null || true
echo "launched $SYM full-session pull for $TODAY (bg) → check: bash ~/options-trader/pull_today_ohlc.sh --check"
exit 0
