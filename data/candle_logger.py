"""
options_trader_v3/data/candle_logger.py — end-of-day 1-minute candle logger. v3.1
v3.1 — 2026-07-12 — DOC SYNC (no logic change): removed the dangling reference to
        `timing_analysis.py`, a file that does not exist anywhere in the repo or
        the fleet (docstring-only; never imported, zero runtime dependency). It
        was the original consumer that defined this module's CSV contract and has
        since been superseded by the replay harnesses. The CSV contract itself is
        unchanged and is now cited directly.
v3.0 — 2026-07-10 — YAHOO-FINANCE PURGE / data stream mapping optimization.
        Converted from a one-shot DXFeed subscribe/drain into a CONSUMER of
        the shared feed store (data/candle_feed.py owns the box's ONLY
        DXLinkStreamer subscription — Mandate 2: one producer, many readers).
        This module now exports the store's 1m bars to the same CSV layout as
        before: {out}/{YYYY-MM-DD}/{SYMBOL}.csv with
        timestamp,open,high,low,close,volume (ET ISO timestamps). The DXFeed
        subscribe/drain mechanics that lived here (v1.x _collect) moved into
        candle_feed.py as a persistent subscription. CLI unchanged.
v1.1 — 2026-07-08 — defaults so one uniform unit works fleet-wide: --out now
        defaults to <repo>/data/OHLC (self-locating, in-project, no /var/lib
        permission trap), and --symbols defaults to this box's
        config.INSTRUMENT (OT_INSTRUMENT), so no per-box symbol editing.
v1.0 — 2026-07-07 — pulled 1-min OHLC candles from the same DXLink/DXFeed
        session the bot trades on, one CSV per symbol per day, so analysis is
        done against the exact data set the trades executed on.

Design (v3.0):
  - Opens the shared SQLite store read-only; no session, no streamer, no
    second subscription — the feed service already holds today's bars.
  - Selects 1m bars for the requested ET date (09:30 onward), drops the
    still-forming minute, and writes the tape CSVs the replay harnesses
    consume (tests/replay_confluence.py, tests/replay_classifier.py — see
    docs/REPLAY_VALIDATION.md §1 for the calibration contract).
  - If the store has no bars for a symbol/date, logs a WARNING (0 bars) —
    check candle-feed.service health and symbology (OT_DXFEED_SYMBOL).

Usage:
    python -m data.candle_logger                       # this box's symbol → data/OHLC/
    python -m data.candle_logger --symbols AMD,UNH     # explicit symbols
    python -m data.candle_logger --date 2026-07-07     # a specific stored day
"""
import argparse
import csv
import logging
import os
import sqlite3
from datetime import datetime, time as dtime, timezone
from zoneinfo import ZoneInfo

from data.candle_feed import feed_db_path, SESSION_OPEN_HM

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

INTERVAL = "1m"

# Default output lives inside the project's data/ dir, right next to this module,
# so it self-locates no matter where the repo is checked out — no /var/lib, no
# per-box path to hard-code. Files land at data/OHLC/<date>/<SYMBOL>.csv.
DEFAULT_OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "OHLC")


def _read_day_bars(conn, symbol, day):
    """[(ts_et, o, h, l, c, v)] for `symbol`'s 1m bars on ET date `day`,
    session open onward, ascending."""
    start = datetime.combine(day, dtime(*SESSION_OPEN_HM), tzinfo=ET)
    end   = datetime.combine(day, dtime(23, 59, 59), tzinfo=ET)
    cur = conn.execute(
        "SELECT ts_epoch_ms, open, high, low, close, volume FROM candles "
        "WHERE symbol=? AND interval=? AND ts_epoch_ms BETWEEN ? AND ? "
        "ORDER BY ts_epoch_ms ASC",
        (symbol, INTERVAL,
         int(start.timestamp() * 1000), int(end.timestamp() * 1000)))
    rows = []
    for t_ms, o, h, l, c, v in cur.fetchall():
        ts = datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc).astimezone(ET)
        rows.append((ts, o, h, l, c, v))
    return rows


def _write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for ts, o, h, l, c, v in rows:
            w.writerow([ts.isoformat(), o, h, l, c, v if v is not None else ""])


def dump_session_candles(symbols, out_dir, date=None, drop_forming=True):
    """Export the store's 1m candles for `symbols` on `date` (default: today
    ET) to CSVs. Returns {symbol: (path, n_bars)}. Reads the shared feed
    store — opens NO DXFeed subscription (Mandate 2)."""
    d = date or datetime.now(ET).date()
    db = feed_db_path()
    if not os.path.exists(db):
        logger.warning("candle_logger: feed store missing at %s — is "
                       "candle-feed.service running?", db)
        conn = None
    else:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5.0)

    now_min = datetime.now(ET).replace(second=0, microsecond=0) if drop_forming else None
    out_day = os.path.join(out_dir, d.isoformat())
    os.makedirs(out_day, exist_ok=True)

    written = {}
    try:
        for sym in symbols:
            rows = _read_day_bars(conn, sym, d) if conn is not None else []
            if now_min is not None:
                rows = [r for r in rows if r[0] < now_min]   # skip forming minute
            path = os.path.join(out_day, f"{sym}.csv")
            _write_csv(path, rows)
            written[sym] = (path, len(rows))
            if rows:
                logger.info("candle_logger: %s → %s (%d bars, %s–%s ET)",
                            sym, path, len(rows), rows[0][0].strftime("%H:%M"),
                            rows[-1][0].strftime("%H:%M"))
            else:
                logger.warning("candle_logger: %s → 0 bars (check candle-feed "
                               "health / OT_DXFEED_SYMBOL)", sym)
    finally:
        if conn is not None:
            conn.close()
    return written


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=None,
                    help="comma-separated tickers (default: this box's OT_INSTRUMENT)")
    ap.add_argument("--out", default=None,
                    help="output base dir (default: <repo>/data/OHLC)")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: today ET)")
    args = ap.parse_args()

    if not args.symbols:
        from config import INSTRUMENT
        args.symbols = INSTRUMENT
    out_dir = args.out or DEFAULT_OUT_DIR

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    d = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else None

    written = dump_session_candles(symbols, out_dir, date=d)
    total = sum(n for _, n in written.values())
    print(f"candle_logger: wrote {len(written)} files, {total} bars total → {out_dir}")
    for sym, (path, n) in written.items():
        print(f"  {sym:<6} {n:>4} bars  {path}")


if __name__ == "__main__":
    main()
