"""
options_trader_v3/tests/test_market_data_contract.py — v3.0 seam contract test.
v3.0 — 2026-07-10 — Yahoo-Finance purge acceptance check §6.1. Builds a
        synthetic feed store and proves fetch_candles honors the EXACT contract
        every consumer (data_cache, engines, get_orb_range, query.py, the
        off-repo shadow observer) depends on:
          - columns exactly [open, high, low, close, volume] (lowercase)
          - tz-aware DatetimeIndex in America/New_York, ascending
          - at most `count` rows; NaN rows dropped
          - None + WARNING when store missing OR heartbeat stale (dead feed)
          - a young session with few bars returns those bars (NOT None)
          - intraday windows never padded across the overnight gap
        No network, no creds, no DXFeed. Run: python -m tests.test_market_data_contract
"""
import importlib
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, time as dtime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ET = ZoneInfo("America/New_York")
fails = []


def check(label, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        fails.append(label)


def _ms(dt):
    return int(dt.astimezone(timezone.utc).timestamp() * 1000)


def build_store(db_path, stale=False):
    from data.candle_feed import FeedStore
    store = FeedStore(db_path)
    now = datetime.now(ET)
    today_open = datetime.combine(now.date(), dtime(9, 30), tzinfo=ET)
    yday_open = today_open - timedelta(days=1)
    rows = []
    # yesterday's session: 30 x 1m bars (the overnight-gap bait)
    for i in range(30):
        t = yday_open + timedelta(minutes=i)
        rows.append(("QQQ", "1m", _ms(t), 500 + i * .1, 500.2 + i * .1,
                     499.9 + i * .1, 500.1 + i * .1, 1000))
    # today's YOUNG session: only 6 x 1m bars, ending ~now so the latest bar
    # is fresh enough for the quote path (QUOTE_MAX_AGE_S)
    base = max(today_open, now - timedelta(minutes=6))
    for i in range(6):
        t = base + timedelta(minutes=i)
        rows.append(("QQQ", "1m", _ms(t), 510 + i * .1, 510.2 + i * .1,
                     509.9 + i * .1, 510.1 + i * .1, 1000))
    # 5m: 3 bars today incl. the 9:30 opening candle
    for i in range(3):
        t = min(today_open + timedelta(minutes=5 * i), now)
        rows.append(("QQQ", "5m", _ms(t), 510, 512.5, 509.5, 511, 5000))
    # 1h: 60 bars across days (must NOT be session-scoped)
    for i in range(60):
        t = now - timedelta(hours=60 - i)
        rows.append(("QQQ", "1h", _ms(t), 500, 505, 495, 502, 90000))
    # a NaN row that must be dropped
    rows.append(("QQQ", "1m", _ms(base + timedelta(minutes=7)),
                 None, None, None, None, 0))
    store.upsert_candles(rows)
    if not stale:
        store.heartbeat()
    else:  # heartbeat 10 minutes old => dead feed
        store.conn.execute(
            "INSERT OR REPLACE INTO feed_meta VALUES ('__feed__','heartbeat',?)",
            (time.time() - 600,))
    store.commit()
    store.close()


def load_market_data():
    for m in ("data.market_data", "data.candle_feed"):
        if m in sys.modules:
            importlib.reload(sys.modules[m])
    import data.market_data as md
    return importlib.reload(md)


def main():
    tmp = tempfile.mkdtemp()

    # ── live store ────────────────────────────────────────────────────────────
    db = os.path.join(tmp, "live.db")
    os.environ["OT_FEED_DB"] = db
    build_store(db)
    md = load_market_data()

    df = md.fetch_candles("QQQ", "1m", 25)
    check("1m returns a DataFrame (feed alive)", df is not None)
    if df is not None:
        check("columns exactly [open,high,low,close,volume]",
              list(df.columns) == ["open", "high", "low", "close", "volume"])
        check("index tz-aware America/New_York",
              df.index.tz is not None and "New_York" in str(df.index.tz))
        check("index ascending", df.index.is_monotonic_increasing)
        check("young session: 6 bars returned, NOT None, NOT padded to 25",
              len(df) == 6)
        check("no prior-session bars across the overnight gap",
              df.index.min().date() == datetime.now(ET).date())
        check("NaN row dropped", not df.isna().any().any())

    df5 = md.fetch_candles("QQQ", "5m", 100)
    check("5m young session returns 3 bars", df5 is not None and len(df5) == 3)

    dfh = md.fetch_candles("QQQ", "1h", 50)
    check("1h spans sessions (not session-scoped), capped at count=50",
          dfh is not None and len(dfh) == 50)

    check("unknown symbol -> None (loud, not empty frame)",
          md.fetch_candles("NVDA", "1m", 10) is None)

    q = md.fetch_quote("QQQ")
    check("fetch_quote returns latest 1m close from store",
          q is not None and abs(q - 510.6) < 1e-6)

    # ── stale store (dead feed) ───────────────────────────────────────────────
    db2 = os.path.join(tmp, "stale.db")
    os.environ["OT_FEED_DB"] = db2
    build_store(db2, stale=True)
    md = load_market_data()
    check("STALE heartbeat -> None (never stale numbers)",
          md.fetch_candles("QQQ", "1m", 25) is None)

    # ── cache hard-stale guard (data_cache v3.0) ──────────────────────────────
    import data.data_cache as dc
    importlib.reload(dc)
    cache = dc.DataCache("QQQ")           # OT_FEED_DB still points at stale.db
    check("data_cache: dead feed + no prior frame -> None",
          cache.get("1m") is None)
    # seed a frame as if fetched long ago, feed still dead -> hard ceiling trips
    import pandas as pd
    cache._cache["1m"] = pd.DataFrame({"open": [1.0], "high": [1.0],
                                       "low": [1.0], "close": [1.0],
                                       "volume": [1.0]})
    cache._fetched_at["1m"] = time.time() - 10_000
    check("data_cache: aged frame past hard ceiling -> None (fail loud)",
          cache.get("1m") is None)
    cache._fetched_at["1m"] = time.time() - 15   # fresh-ish, transient hiccup
    check("data_cache: recent frame within ceiling still served on hiccup",
          cache.get("1m") is not None)

    # ── missing store ─────────────────────────────────────────────────────────
    os.environ["OT_FEED_DB"] = os.path.join(tmp, "nope.db")
    md = load_market_data()
    check("missing store -> None + WARNING",
          md.fetch_candles("QQQ", "1m", 25) is None)

    print("\n" + ("ALL PASS" if not fails else
                  f"{len(fails)} FAILURE(S): " + "; ".join(fails)))
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
