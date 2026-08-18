#!/usr/bin/env bash
# options_trader_v3/install_eod_bot.sh — v1.0
# Installs the unified bot EOD timer (eod-bot.timer, 16:01 ET) running eod_bot.sh,
# and PURGES the two old bot EOD timers it replaces: ot-eod (15:50) + candle-logger
# (16:05). OT_INSTRUMENT is copied from the running optionsbot unit; TT_* are sourced
# at run time by pull_today_ohlc.sh __work, so no secrets live in this unit.
# Run per box (from the control server):
#   python fleet.py run 'bash ~/options-trader/install_eod_bot.sh'
set -uo pipefail
DIR=/home/ubuntu/options-trader
WORKER="$DIR/eod_bot.sh"
[ -f "$WORKER" ] || { echo "🚨 $WORKER missing — git pull first."; exit 1; }
INSTR=$(systemctl show optionsbot -p Environment --value 2>/dev/null | tr ' ' '\n' | grep '^OT_INSTRUMENT=' | head -1 | cut -d= -f2-)
[ -n "$INSTR" ] || { echo "🚨 OT_INSTRUMENT not found in optionsbot unit"; exit 1; }

# purge the retired bot EOD timers
for u in ot-eod candle-logger; do
  sudo systemctl disable --now "${u}.timer" >/dev/null 2>&1 || true
  sudo rm -f "/etc/systemd/system/${u}.timer" "/etc/systemd/system/${u}.service"
done
echo "purged old bot timers: ot-eod, candle-logger"

sudo tee /etc/systemd/system/eod-bot.service >/dev/null <<UNIT
[Unit]
Description=OPT_Trader unified EOD winddown (P&L + full-session OHLC)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=${DIR}
Environment=OT_INSTRUMENT=${INSTR}
ExecStart=/bin/bash ${WORKER}
TimeoutStartSec=600
UNIT
sudo chmod 644 /etc/systemd/system/eod-bot.service

sudo tee /etc/systemd/system/eod-bot.timer >/dev/null <<'UNIT'
[Unit]
Description=OPT_Trader EOD winddown timer (Mon-Fri 16:01 ET)

[Timer]
OnCalendar=Mon..Fri 16:01 America/New_York
Persistent=false
AccuracySec=30s

[Install]
WantedBy=timers.target
UNIT
sudo chmod 644 /etc/systemd/system/eod-bot.timer

sudo systemctl daemon-reload
sudo systemctl enable --now eod-bot.timer >/dev/null 2>&1
echo "✅ eod-bot.timer installed on $(hostname) (instrument=${INSTR}, 16:01 ET)"
systemctl list-timers eod-bot.timer --no-pager 2>/dev/null | sed -n '1,2p'
