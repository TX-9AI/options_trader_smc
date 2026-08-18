#!/usr/bin/env bash
# install_candle_feed.sh — options_trader v3
# v1.0 — 2026-07-10 — install the v3 candle-feed.service on a box that was set
#        up pre-v3 (repointed to v3 code, but the new shared feed service was
#        never created — `systemctl is-enabled candle-feed` => not-found).
#
# WHY: v3 routes ALL market data through one DXFeed subscription per box
# (data/candle_feed.py) writing a shared SQLite store every consumer reads.
# setup_ec2.sh v3.2 generates candle-feed.service; a plain repoint syncs code
# and restarts optionsbot but does NOT create that unit, so every bot finds the
# feed store missing, falls back to a REST market-data call (403), can't price,
# and self-exits into a systemd restart loop.
#
# This installer reuses the TT_* creds ALREADY present in the running optionsbot
# unit (same inline Environment= form setup_ec2.sh writes), so no secrets are
# re-entered or moved between machines. It is idempotent: safe to re-run.
#
# Run per box (from the control server):
#   python fleet.py run 'bash ~/options-trader/install_candle_feed.sh'
set -uo pipefail

UNIT=/etc/systemd/system/candle-feed.service
VENV=/home/ubuntu/options-trader/venv
BOTUNIT=optionsbot

# ── Pull creds + instrument from the RUNNING optionsbot unit (source of truth) ─
ENVLINE=$(systemctl show "$BOTUNIT" -p Environment --value 2>/dev/null)
getv() { echo "$ENVLINE" | tr ' ' '\n' | grep "^$1=" | head -1 | cut -d= -f2-; }
INSTRUMENT=$(getv OT_INSTRUMENT)
CS=$(getv TT_CLIENT_SECRET)
RT=$(getv TT_REFRESH_TOKEN)
AN=$(getv TT_ACCOUNT_NUMBER)

if [ -z "$CS" ] || [ -z "$RT" ] || [ -z "$AN" ]; then
    echo "🚨 TT_* creds not found in the $BOTUNIT unit environment on this box."
    echo "   Not installing a feed that can't authenticate. Use the bootstrap"
    echo "   installer here instead. (instrument=${INSTRUMENT:-unknown})"
    exit 1
fi
if [ -z "$INSTRUMENT" ]; then
    echo "🚨 OT_INSTRUMENT missing from $BOTUNIT unit — aborting."; exit 1
fi

# ── Write the unit (inline creds, matching setup_ec2.sh v3.2), chmod 600 ───────
sudo tee "$UNIT" > /dev/null <<UNITEOF
[Unit]
Description=options_trader v3 — single TastyTrade candle feed (DXFeed producer)
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/options-trader
Environment=OT_INSTRUMENT=${INSTRUMENT}
Environment=TT_CLIENT_SECRET=${CS}
Environment=TT_REFRESH_TOKEN=${RT}
Environment=TT_ACCOUNT_NUMBER=${AN}
ExecStart=${VENV}/bin/python -m data.candle_feed
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=candle-feed

[Install]
WantedBy=multi-user.target
UNITEOF
sudo chmod 600 "$UNIT"

# ── Activate ───────────────────────────────────────────────────────────────────
sudo systemctl daemon-reload
sudo systemctl enable candle-feed >/dev/null 2>&1
sudo systemctl restart candle-feed
sleep 6

STATE=$(systemctl is-active candle-feed 2>/dev/null)
echo "candle-feed=${STATE} instrument=${INSTRUMENT}"
if [ "$STATE" != "active" ]; then
    echo "🚨 candle-feed did NOT come active — last log lines:"
    journalctl -u candle-feed -n 12 --no-pager 2>/dev/null | tail -8
    exit 1
fi
echo "✅ feed producing — bots will price on their next loop."
