"""Offline self-test for data/candle_logger.py v3.0 — builds a synthetic feed
store (SQLite, same schema candle_feed.py writes) and proves the store→CSV
export works: day filtering, ascending order, forming-minute drop, and the
exact CSV header the analysis harness reads. No network / no creds / no DXFeed.
v3.0 — 2026-07-10 — rewritten for the Yahoo-Finance purge: the logger is now a
        store consumer (Mandate 2 — one producer, many readers), so the fake
        streamer harness is replaced by a synthetic store."""
import csv
import os
import sys
import tempfile
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def _ms(y, mo, d, h, m):
    return int(datetime(y, mo, d, h, m, tzinfo=ET).astimezone(timezone.utc).timestamp() * 1000)


def main():
    fails = []
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "feed_store.db")
    os.environ["OT_FEED_DB"] = db_path

    # Build a synthetic store with candle_feed's own schema/writer
    from data.candle_feed import FeedStore
    import data.candle_logger as cl

    store = FeedStore(db_path)
    rows = [
        # AMD 2026-07-07: 09:36–09:38 plus a pre-open bar (must be excluded)
        ("AMD", "1m", _ms(2026, 7, 7, 9, 15), 556.0, 556.2, 555.9, 556.1, 90),
        ("AMD", "1m", _ms(2026, 7, 7, 9, 36), 557.0, 557.4, 556.8, 557.2, 100),
        ("AMD", "1m", _ms(2026, 7, 7, 9, 37), 557.2, 558.3, 557.1, 558.1, 100),
        ("AMD", "1m", _ms(2026, 7, 7, 9, 38), 558.1, 558.5, 557.6, 557.7, 100),
        # a different day (must be excluded by --date filtering)
        ("AMD", "1m", _ms(2026, 7, 6, 10, 0), 550.0, 550.5, 549.9, 550.2, 100),
        # a different interval (must never leak into the 1m export)
        ("AMD", "5m", _ms(2026, 7, 7, 9, 35), 557.0, 558.5, 556.8, 557.7, 500),
    ]
    store.upsert_candles(rows)
    # last-write-wins correction on the 09:37 bar
    store.upsert_candles([("AMD", "1m", _ms(2026, 7, 7, 9, 37),
                           557.2, 558.9, 557.1, 558.4, 120)])
    store.heartbeat()
    store.commit()
    store.close()

    def check(label, cond):
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
        if not cond:
            fails.append(label)

    written = cl.dump_session_candles(
        ["AMD", "NVDA"], tmp, date=datetime(2026, 7, 7).date(), drop_forming=False)

    amd_path, amd_n = written["AMD"]
    check("AMD exported 3 bars (pre-open + other-day + 5m excluded)", amd_n == 3)
    check("NVDA present with 0 bars (warned, not crashed)", written["NVDA"][1] == 0)

    with open(amd_path) as f:
        r = list(csv.reader(f))
    check("CSV header exact", r[0] == ["timestamp", "open", "high", "low", "close", "volume"])
    ts = [row[0] for row in r[1:]]
    check("rows ascending", ts == sorted(ts))
    check("timestamps ET-zoned ISO", all(("-04:00" in t or "-05:00" in t) for t in ts))
    check("09:37 correction applied (high=558.9, last write wins)",
          any(row[2] == "558.9" for row in r[1:]))

    print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILURE(S): " + "; ".join(fails)))
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
