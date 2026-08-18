#!/usr/bin/env bash
# options_trader_v3/install_s3_push_timer.sh — v1.1
# v1.1 — 2026-08-13 — the report line stops crying wolf. v1.0 read `next` out of
#        `systemctl list-timers` with an awk column offset, which printed "- -"
#        on most boxes and sent me hunting a scheduling fault twice. It now asks
#        systemd directly. NOTE an empty NEXT is still legitimate and expected:
#        a timer shows no next elapse while its unit is ACTIVE, i.e. while a
#        drain is in flight. That is health, not failure — so it is labelled.
# v1.0 — 2026-08-12 — initial release. Installs the box-side warehouse pusher
#        (warehouse/s3_push.py) as s3-push.service + s3-push.timer, sourced
#        from deploy/ in the repo rather than written inline, so the units are
#        version-controlled and reviewable instead of living in a heredoc.
#
#        ⚠ DOES NOT TOUCH THE BOT. daemon-reload re-reads unit definitions; it
#        does not restart running services, and the two units created here are
#        new. optionsbot and candle-feed are not stopped, restarted or altered.
#        No reboot, no pycache clear. Safe to run on a live box, though the
#        house discipline is still to install outside RTH.
#
#        Fast by design — well under the fleet fan-out's ~22s SSH ceiling. The
#        first push is left to the timer rather than kicked synchronously here.
#
# Deploy to every running box from the control server (devtools option 14):
#   cd ~/options-trader && git pull && sudo bash install_s3_push_timer.sh
set -uo pipefail

DIR=/home/ubuntu/options-trader
WORKER="$DIR/warehouse/s3_push.py"
SRC="$DIR/deploy"
DST=/etc/systemd/system

# ── Sanity: never install a timer pointing at a worker that is not here ───────
[ -f "$WORKER" ] || { echo "🚨 $WORKER missing — git pull on this box before installing."; exit 1; }
[ -f "$SRC/s3-push.service" ] || { echo "🚨 $SRC/s3-push.service missing — repo is stale."; exit 1; }
[ -f "$SRC/s3-push.timer" ]   || { echo "🚨 $SRC/s3-push.timer missing — repo is stale."; exit 1; }

# ── Sanity: system python must be able to import boto3 ───────────────────────
# The bot venv does NOT have boto3 and never needs it. If this check fails the
# timer would run every 5 minutes doing nothing, silently, forever.
/usr/bin/python3 -c "import boto3" 2>/dev/null || {
    echo "🚨 /usr/bin/python3 cannot import boto3 on $(hostname) — aborting rather than"
    echo "   installing a timer that can never push. Install boto3 for system python first."
    exit 1
}

# ── Syntax-gate the worker before wiring a timer to it ───────────────────────
/usr/bin/python3 -c "import ast,sys;ast.parse(open('$WORKER').read())" 2>/dev/null || {
    echo "🚨 $WORKER does not parse — aborting."; exit 1; }

sudo install -m 0644 "$SRC/s3-push.service" "$DST/s3-push.service"
sudo install -m 0644 "$SRC/s3-push.timer"   "$DST/s3-push.timer"

sudo systemctl daemon-reload
sudo systemctl enable --now s3-push.timer >/dev/null 2>&1

# ── Report by NAME, not by exit code ─────────────────────────────────────────
ACTIVE=$(systemctl is-active s3-push.timer 2>/dev/null)
NEXT=$(systemctl show s3-push.timer -p NextElapseUSecRealtime --value 2>/dev/null)
RUNNING=$(systemctl is-active s3-push.service 2>/dev/null)
# An empty NEXT while the service is activating is CORRECT: systemd schedules no
# next elapse while the unit is running. Say so rather than printing a bare dash.
if [ -z "$NEXT" ] && [ "$RUNNING" = "activating" ]; then NEXT="(draining now)"; fi
echo "s3-push.timer host=$(hostname) active=${ACTIVE:-unknown} next=${NEXT:-unknown}"
exit 0
