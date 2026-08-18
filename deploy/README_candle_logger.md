# candle_logger — daily 1-min OHLC from the same feed you trade on (v3.0)

Exports 1-minute candles to one CSV per symbol per day, in the format the
analysis harnesses read. Purpose: evaluate trades against the exact data set
they executed on — the TastyTrade **DXLink/DXFeed** tape (the feed your fills,
marks, and greeks price against), never a divergent third-party series.

**v3.0 (Yahoo-Finance purge / data stream mapping optimization):** the logger
no longer opens its own DXFeed subscription. `data/candle_feed.py`
(`candle-feed.service`) owns the box's **only** DXLink stream and maintains
the shared SQLite store; the logger is now a plain **consumer** that reads the
store and writes CSVs. One producer, many readers — do not add streams.

No new dependency — `sqlite3` is stdlib. No credentials needed by the logger
itself (the feed service holds the session).

## Install (per bot box)
1. Ship `data/candle_logger.py` + `data/candle_feed.py` with the repo
   (`push.sh --deploy`). `setup_ec2.sh` v3.2 installs `candle-feed.service`.
2. Install the logger units:
   ```
   sudo cp deploy/candle-logger.service deploy/candle-logger.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now candle-logger.timer
   systemctl list-timers candle-logger.timer      # confirm next run = 16:05 ET
   ```

## First run — verify
Run it manually once during or just after a session:
```
python -m data.candle_logger
```
Then check `data/OHLC/<date>/<SYMBOL>.csv`:
- **Bars present?** 0 bars means the feed store is missing that symbol/date —
  check `journalctl -u candle-feed` (service health, backfill depth,
  entitlement) and `OT_DXFEED_SYMBOL` on index boxes.
- **Timestamps ET, 09:30 onward, forming minute dropped.**

Output: `<repo>/data/OHLC/<YYYY-MM-DD>/<SYMBOL>.csv`
(`timestamp,open,high,low,close,volume`).
