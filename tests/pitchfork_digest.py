#!/usr/bin/env python3
"""
tests/pitchfork_digest.py — v1.0 — 2026-08-12

Reads the `pitchfork` journal events PF.2 writes and answers the three questions
its Fri 2026-08-14 evaluation depends on:

  1. DO DAILY FORKS BUILD AT ALL? The whole prerequisite was raising
     TIMEFRAMES["1d"]["candles"] 10 -> 60 so the engines could see the 84 daily
     bars the boxes already held. **A zero 1d count with a healthy 1h count
     means the frame fix did not take** — that is PF.2's delete criterion.
  2. WHERE DOES PRICE SIT? `pos_pct` — 0% is on the lower tine, 100% the upper.
     This is the join key for the first consumer (continuation's pullback rail).
  3. IS CONTAINMENT CARRYING IT? `pivot_built` records whether the §4.3
     pivot-selection arm ALSO built on the same frame. If containment builds and
     §4.3 never does, the old anchor rule is dead on real frames.

⚠️ EXPECT A LARGE ROW COUNT AND DO NOT READ IT AS FORK COUNT. The observer
rebuilds on a 5-minute cadence but journals on EVERY tick, so at 15s ticks the
same cached fork is written ~20x between rebuilds. 22,157 rows on 2026-08-12 is
the coded behaviour, not a malfunction — but it is ~20x the volume needed and is
worth narrowing later. Distinct (symbol, span) pairs are the honest fork count
and are reported separately.

READ-ONLY. stdlib only. Runs on CONTROL — the journal is harvested there.

USAGE
    python3 tests/pitchfork_digest.py 2026-08-12
    python3 tests/pitchfork_digest.py 2026-08-12 --journal-root ~/day_trader_pro/signal_journal
"""

import argparse
import collections
import glob
import json
import os
import sys

DEFAULT_ROOT = os.path.expanduser("~/day_trader_pro/signal_journal")


def pctile(vals, q):
    v = sorted(vals)
    return v[min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))] if v else None


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("date")
    ap.add_argument("--journal-root", default=DEFAULT_ROOT)
    a = ap.parse_args(argv[1:])

    root = os.path.expanduser(a.journal_root)
    files = sorted(glob.glob(os.path.join(root, a.date, "*.jsonl")))
    if not files:
        print(f"no journal files at {os.path.join(root, a.date)}")
        return 1

    rows = 0
    tf_rows = collections.Counter()
    pivot_built = collections.Counter()
    pivot_seen = collections.Counter()
    pos = collections.defaultdict(list)
    dirs = collections.Counter()
    spans = collections.defaultdict(set)          # (tf) -> {(sym, span)}
    per_sym = collections.defaultdict(collections.Counter)

    for path in files:
        sym = os.path.basename(path).split(".")[0]
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"pitchfork"' not in line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:                              # noqa: BLE001
                    continue
                p = r.get("pitchfork")
                if not isinstance(p, dict):
                    continue
                rows += 1
                for tf, built in (p.get("pivot_built") or {}).items():
                    pivot_seen[tf] += 1
                    pivot_built[tf] += int(bool(built))
                for tf in ("1d", "1h"):
                    e = p.get(tf)
                    if not isinstance(e, dict):
                        continue
                    tf_rows[tf] += 1
                    per_sym[tf][sym] += 1
                    if e.get("pos_pct") is not None:
                        pos[tf].append(float(e["pos_pct"]))
                    if e.get("dir"):
                        dirs[(tf, e["dir"])] += 1
                    sp = [t for t in (e.get("span") or ()) if str(t).startswith("SPAN_")]
                    if sp:
                        spans[tf].add((sym, sp[0]))

    print("=" * 72)
    print(f"  PITCHFORK DIGEST — {a.date}   {len(files)} journal file(s)"
          f"   {rows:,} pitchfork row(s)")
    print("=" * 72)
    if rows == 0:
        print("\n  NO pitchfork events. The observer is not running, or")
        print("  OT_PF_OBSERVE=0, or the boxes predate the PF.2 bake.")
        return 0
    print(f"\n  ⚠️ ROWS ARE NOT FORKS: the observer rebuilds every 5 min but")
    print(f"     journals every tick, so one fork is written ~20x. Read the")
    print(f"     DISTINCT column as the fork count.")

    print(f"\n  {'timeframe':12}{'rows':>9}{'distinct forks':>16}{'symbols':>9}")
    for tf in ("1d", "1h"):
        print(f"  {tf:12}{tf_rows[tf]:>9,}{len(spans[tf]):>16}{len(per_sym[tf]):>9}")

    if tf_rows["1d"] == 0:
        print(f"\n  ⚠️⚠️ NO DAILY FORKS BUILT. The frame fix (candles 10 -> 60)")
        print(f"       did not take, or 84 bars still are not reaching the")
        print(f"       engines. **This is PF.2's DELETE CRITERION** — the")
        print(f"       overlay is inert without a daily fork.")

    print(f"\n  DIRECTION")
    for (tf, d), n in sorted(dirs.items()):
        print(f"    {tf:5}{d:10}{n:>8,}")

    print(f"\n  POSITION IN CHANNEL  (0% = lower tine, 100% = upper)")
    print(f"    {'tf':6}{'n':>8}{'p10':>8}{'p25':>8}{'p50':>8}{'p75':>8}"
          f"{'p90':>8}{'outside':>9}")
    for tf in ("1d", "1h"):
        v = pos[tf]
        if not v:
            continue
        out = sum(1 for x in v if x < 0 or x > 100)
        print(f"    {tf:6}{len(v):>8,}"
              + "".join(f"{pctile(v,q):>8.1f}" for q in (.10, .25, .50, .75, .90))
              + f"{100.0*out/len(v):>8.1f}%")
    print(f"    'outside' is price beyond a tine — a TOUCH or a break, which is")
    print(f"    the tradeable event the overlay exists to produce (§5.2), not a")
    print(f"    failure.")

    print(f"\n  ⚠️ IS CONTAINMENT CARRYING IT?  (does §4.3 pivot-selection ever build?)")
    print(f"    {'tf':6}{'evaluated':>11}{'pivot built':>13}{'share':>8}")
    for tf in sorted(pivot_seen):
        n, b = pivot_seen[tf], pivot_built[tf]
        print(f"    {tf:6}{n:>11,}{b:>13,}{100.0*b/max(n,1):>7.1f}%")
    print(f"    A near-zero share means the OLD anchor rule is dead on real")
    print(f"    frames and §4.3.6 containment is doing all the work.")

    print(f"\n  TOP SYMBOLS BY DAILY-FORK ROWS")
    for sym, n in per_sym["1d"].most_common(10):
        print(f"    {sym:8}{n:>9,}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
