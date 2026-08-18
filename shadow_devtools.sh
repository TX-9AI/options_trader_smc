#!/usr/bin/env bash
# shadow_devtools.sh v1.3 — operator menu for the SHADOW subsystem (live on the QQQ paper box).
# v1.3 — 2026-07-31 — item D, SERVICE HALF. deploy/shadow-observer.service had
#        /home/ubuntu/options-trader hardcoded in WorkingDirectory and ExecStart,
#        so the unit pointed at the canonical path from ANY checkout — a silent
#        no-op on the fleet and a broken observer anywhere else. The template now
#        carries __INSTALL_DIR__ and new option 11 substitutes $REPO at install
#        time, mirroring setup_ec2.sh's ${INSTALL_DIR} pattern for
#        optionsbot.service. Refuses to arm the unit if the placeholder survives.
# Run from anywhere: the script self-locates its repo (defect D remainder —
# v1.2 — 2026-07-23 — shadow-start/shadow-stop timers RETIRED (2026-07-22,
#        fleet-wide): edge-triggered timers fired while overnight-stopped boxes
#        were off; the observer is now enable-at-boot and self-gates on RTH.
#        Item 10 and the banner label them retired — 'disabled' is HEALTHY.
# the v1.0 hardcoded $HOME/options-trader hard-exited on any other checkout,
# e.g. the control box's ~/options-trader-v3). Mirrors observer.py's
# REPO_ROOT derivation so script and service always agree on the tree.
# Observe-only subsystem: nothing here can place a trade.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$REPO/venv/bin/python"
OBS="shadow-observer.service"
DROPIN_DIR="/etc/systemd/system/${OBS}.d"
STAGE_CONF="$DROPIN_DIR/stage.conf"
TODAY="$(TZ=America/New_York date +%F)"
SHADOW_DIR="$REPO/data/shadow/$TODAY"

cd "$REPO" 2>/dev/null || { echo "cannot cd to $REPO"; exit 1; }

cur_stage() {
  # drop-in wins if present, else the unit default
  if [ -f "$STAGE_CONF" ]; then grep -oE 'OT_SHADOW_STAGE=[0-9]+' "$STAGE_CONF" | cut -d= -f2
  else grep -oE 'OT_SHADOW_STAGE=[0-9]+' /etc/systemd/system/$OBS 2>/dev/null | cut -d= -f2 || echo "?"; fi
}

pause() { read -rp $'\n[enter] '; }

status() {
  echo "── SHADOW status ──────────────────────────────"
  echo "observer : $(systemctl is-active $OBS 2>/dev/null)  (stage $(cur_stage))"
  echo "timers (RETIRED 07-22, disabled=healthy): start $(systemctl is-enabled shadow-start.timer 2>/dev/null) | stop $(systemctl is-enabled shadow-stop.timer 2>/dev/null)"
  echo -n "today log: "
  if [ -f "$SHADOW_DIR/"*.jsonl ] 2>/dev/null; then
    f=$(ls "$SHADOW_DIR"/*.jsonl 2>/dev/null | head -1)
    echo "$(wc -l < "$f") lines  ($f)"
  else echo "none yet ($SHADOW_DIR)"; fi
  echo "trading day today: $($PY shadow/trading_day.py && echo YES || echo 'NO (weekend/holiday)')"
}

toggle_stage() {
  local now; now=$(cur_stage); local next
  [ "$now" = "2" ] && next=1 || next=2
  echo "current stage: $now  →  new stage: $next"
  [ "$next" = "2" ] && echo "  (stage 2 enables the scorer + would-fire logging — still ZERO firing)"
  read -rp "confirm toggle to stage $next? [y/N] " ok
  [ "$ok" = "y" ] || { echo "cancelled"; return; }
  sudo mkdir -p "$DROPIN_DIR"
  printf '[Service]\nEnvironment=OT_SHADOW_STAGE=%s\n' "$next" | sudo tee "$STAGE_CONF" >/dev/null
  sudo systemctl daemon-reload
  systemctl is-active --quiet $OBS && sudo systemctl restart $OBS && echo "restarted at stage $next" || echo "drop-in set to stage $next (observer not running; applies on next start)"
}

verify_isolation() {
  echo "── isolation re-check ─────────────────────────"
  echo -n "imports from execution/risk/strategy/notifications: "
  grep -rnE "^(from|import) (execution|risk|strategy|notifications)" shadow/*.py >/dev/null 2>&1 && echo "⚠ FOUND — STOP" || echo "none ✓"
  echo -n "order/broker calls: "
  grep -rniE "place_order|submit_order|tasty_client|send_order" shadow/*.py >/dev/null 2>&1 && echo "⚠ FOUND — STOP" || echo "none ✓"
  echo -n "eod_compare trades.db mode: "
  grep -q "mode=ro" shadow/eod_compare.py && echo "read-only ✓" || echo "⚠ not read-only"
}

while true; do
  clear 2>/dev/null
  echo "═══ SHADOW devtools — $(hostname) — $TODAY ═══"
  status
  cat <<MENU

  1) Start observer now            6) Run EOD comparison report
  2) Stop observer now             7) Toggle stage (1 <-> 2)
  3) Restart observer              8) Tail observer journal (live)
  4) View today's shadow log       9) Verify isolation
  5) Would-fire summary (today)   10) Timer schedule (next fire)
                                  11) Install/refresh the unit (this checkout)
  0) Exit
MENU
  read -rp "> " c
  case "$c" in
    1) sudo systemctl start $OBS; pause ;;
    2) sudo systemctl stop $OBS; pause ;;
    3) sudo systemctl restart $OBS; pause ;;
    4) f=$(ls "$SHADOW_DIR"/*.jsonl 2>/dev/null | head -1); [ -n "$f" ] && tail -n 30 "$f" || echo "no log for $TODAY yet"; pause ;;
    5) f=$(ls "$SHADOW_DIR"/*.jsonl 2>/dev/null | head -1)
       if [ -n "$f" ]; then echo "would-fire events today (stage 2 only):"
         grep -c '"would_fire"' "$f" 2>/dev/null | xargs echo "  lines with would_fire field:"
         grep '"would_fire": true' "$f" 2>/dev/null | tail -10
       else echo "no log yet"; fi; pause ;;
    6) echo "running eod_compare (reads trades.db read-only + data/OHLC)…"; $PY -m shadow.eod_compare; pause ;;
    7) toggle_stage; pause ;;
    8) echo "Ctrl-C to exit tail"; journalctl -u $OBS -f --no-pager ;;
    9) verify_isolation; pause ;;
    10) echo "start (RETIRED 2026-07-22 — disabled is the healthy state):"; systemctl list-timers shadow-start.timer --no-pager 2>/dev/null | head -2
        echo "stop:";  systemctl list-timers shadow-stop.timer  --no-pager 2>/dev/null | head -2; pause ;;
    11) # D — install the unit with THIS checkout's path substituted in.
        # The template ships with __INSTALL_DIR__ rather than a hardcoded
        # /home/ubuntu/options-trader, which used to make the unit point at the
        # canonical path from any checkout: a no-op on the fleet and a silently
        # broken observer on the tester or any non-standard install.
        _src="$REPO/deploy/shadow-observer.service"
        if [ ! -f "$_src" ]; then echo "template missing: $_src"; pause; continue; fi
        echo "installing $OBS with WorkingDirectory=$REPO"
        sudo sed "s|__INSTALL_DIR__|$REPO|g" "$_src" \
             | sudo tee /etc/systemd/system/$OBS >/dev/null
        if grep -q "__INSTALL_DIR__" /etc/systemd/system/$OBS; then
            echo "REFUSED: placeholder survived substitution — unit not armed"
        else
            sudo systemctl daemon-reload
            echo "installed. WorkingDirectory now:"
            grep -E "WorkingDirectory|ExecStart" /etc/systemd/system/$OBS
            echo "NOTE: Environment= lines still need copying from optionsbot.service"
        fi
        pause ;;
    0) exit 0 ;;
    *) ;;
  esac
done
