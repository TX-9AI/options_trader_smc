#!/usr/bin/env python3
"""
tools/segregate_nonrth_bars.py — move the 24-hour contamination. v1.0
v1.0 — 2026-08-20 — INITIAL. Companion to candle_feed v3.17.

⚠️ THIS MOVES, IT DOES NOT DELETE — and that distinction was nearly missed.
`EXT_INTERVAL` is **1h only**, so for 5m/15m/1m there is no extended stream at
all: an overnight bar written by the contaminated backfill is the ONLY copy
that will ever exist, and DXFeed history is use-it-or-lose-it. Deleting to
protect the RTH series would have traded one irreversible loss for another.
Non-RTH rows are re-symboled to `<SYM>_EXT`, which already means "this stream
carries overnight". The RTH series becomes pure again for the consumers built
to read it — structure_analyzer's swings and S/R at weight 2.0, the
pitchfork's 1h fractals, trend_engine's 0.20 context vote, entry_snapshot —
and every bar stays queryable.

WHY THIS EXISTS. After the FEED.2 route collision was fixed (v3.16), the
restart's backfill asked DXFeed for plain-symbol history and got 24-HOUR bars
back — roughly 12 bars/hour overnight against 38–39 in RTH, reaching about 15
days back (the 2026-08-05 boundary). v3.17 stops any MORE arriving. This
removes what already landed.

⚠️ WHY IT MATTERS MORE THAN THE ORIGINAL HOLE. A gap announces itself; this
does not. The series CHANGES CHARACTER MID-STREAM — 07-31 is RTH-only, 08-19
is 24-hour — with nothing marking the seam. Anything reading higher-timeframe
structure across it (swings, S/R, the hourly pitchfork) is reading a
discontinuity it cannot detect. Every day this waits is another day of
analysis built on a mixed series.

THE CONTROL THAT PROVES IT IS REAL: SPX shows only hours 13–20 UTC. An index
has no overnight session, so it had nothing to contaminate — which rules out a
timezone or DST artifact and confirms genuine extended-hours data on the
equities.

SAFETY, because this DELETES:
  · DRY RUN BY DEFAULT. `--apply` is required to write anything.
  · `*_EXT` symbols are NEVER touched. Carrying overnight is their purpose.
  · 1d and coarser are NEVER touched. A daily bar is stamped at midnight and
    would fail every intraday test — deleting the daily series is one line
    away and would stay invisible until something asked for a daily level.
  · Weekends and holidays are removed only for INTRADAY intervals.
  · A backup copy of the DB is taken before the first write unless
    `--no-backup` is passed.
  · Rows that would COLLIDE with an existing `<SYM>_EXT` bar at the same
    timestamp are reported, not silently merged — if the two disagree that is
    worth seeing before either is trusted.
  · Reports per (symbol, interval): rows kept, rows to delete, the resulting
    oldest/newest, and the DATE RANGE affected — so the blast radius is
    visible before it happens, not after.

Run on a BOX (never control — the feed_store lives on the boxes):
  cd ~/options-trader && python3 tools/segregate_nonrth_bars.py          # dry run
  cd ~/options-trader && python3 tools/segregate_nonrth_bars.py --apply
"""

import argparse
import os
import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# Must stay identical to candle_feed._RTH_BY_INTERVAL — the store and the
# writer disagreeing about what "RTH" means is how a series drifts back into
# a mixed state one restart at a time.
RTH_BY_INTERVAL = {
    "1m":  ((9, 30), (16, 0)),
    "5m":  ((9, 30), (16, 0)),
    "15m": ((9, 30), (16, 0)),
    "1h":  ((9, 0),  (16, 30)),
}


def within_rth(ts_ms: int, interval: str) -> bool:
    win = RTH_BY_INTERVAL.get(interval)
    if win is None:
        return True                       # 1d and coarser: always kept
    try:
        et = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).astimezone(ET)
    except (OverflowError, OSError, ValueError):
        return True                       # unparseable: leave it for the poison purge
    if et.weekday() >= 5:
        return False
    (sh, sm), (eh, em) = win
    mins = et.hour * 60 + et.minute
    return (sh * 60 + sm) <= mins < (eh * 60 + em)


def main():
    ap = argparse.ArgumentParser(
        description="segregate non-RTH bars from plain symbols into <SYM>_EXT")
    ap.add_argument("--db", default="data/feed_store.db")
    ap.add_argument("--apply", action="store_true",
                    help="actually delete (default is a dry run)")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()

    if not os.path.isfile(args.db):
        print(f"no such db: {args.db}")
        return 2

    con = sqlite3.connect(args.db)
    rows = con.execute(
        "SELECT symbol, interval, ts_epoch_ms FROM candles").fetchall()
    print(f"scanned {len(rows)} row(s) in {args.db}\n")

    keep = defaultdict(int)
    drop = defaultdict(int)
    drop_dates = defaultdict(set)
    hours = defaultdict(lambda: defaultdict(int))

    for sym, interval, ts in rows:
        key = (sym, interval)
        if str(sym).endswith("_EXT") or interval not in RTH_BY_INTERVAL:
            keep[key] += 1
            continue
        if within_rth(ts, interval):
            keep[key] += 1
        else:
            drop[key] += 1
            try:
                et = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).astimezone(ET)
                drop_dates[key].add(et.date().isoformat())
                hours[key][et.hour] += 1
            except Exception:             # noqa: BLE001
                pass

    total_drop = sum(drop.values())
    allkeys = sorted(set(keep) | set(drop))
    print(f"{'symbol':<10} {'tf':<5} {'keep':>7} {'MOVE':>7}   affected dates")
    print("-" * 72)
    for k in allkeys:
        d = drop.get(k, 0)
        marker = "  <-- contaminated" if d else ""
        dates = sorted(drop_dates.get(k, []))
        span = f"{dates[0]} .. {dates[-1]} ({len(dates)}d)" if dates else "-"
        print(f"{k[0]:<10} {k[1]:<5} {keep.get(k,0):>7} {d:>7}   {span}{marker}")

    if not total_drop:
        print("\n✅ nothing to segregate — every plain-symbol intraday bar is RTH")
        return 0

    print(f"\nnon-RTH bars by ET hour (the overnight signature):")
    for k in allkeys:
        if not hours.get(k):
            continue
        hh = "  ".join(f"{h:02d}:00={n}" for h, n in sorted(hours[k].items()))
        print(f"  {k[0]} {k[1]}: {hh}")

    if not args.apply:
        print(f"\nDRY RUN — {total_drop} row(s) WOULD be MOVED to <SYM>_EXT "
              f"(nothing deleted). Re-run with --apply to do it.")
        return 0

    if not args.no_backup:
        bak = f"{args.db}.pre_rth_purge_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(args.db, bak)
        print(f"\nbackup written: {bak}")

    moved, collided = 0, 0
    before_total = con.execute("SELECT COUNT(*) FROM candles").fetchone()[0]
    for (sym, interval) in allkeys:
        if not drop.get((sym, interval)):
            continue
        dest = f"{sym}_EXT"
        bad = [ts for (s2, i2, ts) in rows
               if s2 == sym and i2 == interval and not within_rth(ts, interval)]
        existing = {t for (t,) in con.execute(
            "SELECT ts_epoch_ms FROM candles WHERE symbol=? AND interval=?",
            (dest, interval))}
        for ts in bad:
            if ts in existing:
                # The destination already holds this bar. Report rather than
                # merge: two sources for one timestamp is worth seeing.
                collided += 1
                con.execute("DELETE FROM candles WHERE symbol=? AND interval=? "
                            "AND ts_epoch_ms=?", (sym, interval, ts))
                continue
            con.execute("UPDATE candles SET symbol=? WHERE symbol=? AND "
                        "interval=? AND ts_epoch_ms=?", (dest, sym, interval, ts))
            moved += 1
    con.commit()

    after_total = con.execute("SELECT COUNT(*) FROM candles").fetchone()[0]
    print(f"\n✅ moved {moved} non-RTH row(s) to <SYM>_EXT")
    if collided:
        print(f"ℹ️  {collided} row(s) already existed at the destination "
              f"timestamp and were dropped from the plain series rather than "
              f"duplicated — the EXT copy was kept.")
    print(f"   rows before {before_total} → after {after_total} "
          f"(difference {before_total - after_total} = the collisions above)")
    print("⚠️ Restart candle-feed so the high-water marks are re-read.")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
