#!/usr/bin/env python3
"""
tests/sweep_accept_probe.py — v1.0 — 2026-08-15   (SWP.7)

DOES `veto_accept` REFUSE A DEFENDED LEVEL, OR A DEAD ONE?

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python tests/sweep_accept_probe.py

────────────────────────────────────────────────────────────────────────────
THE QUESTION, AND WHY A RAW COUNT CANNOT ANSWER IT
────────────────────────────────────────────────────────────────────────────
`_sweep()` hard-vetoes when `closes_beyond >= SWEEP_ACCEPT_CLOSES` (2). SWP.6
measured that veto closing **64.5% of all named-pool ticks** across the archive.

But **two completely different tapes produce the same count**:

  · **ACCEPTANCE** — price broke through, closed beyond, and STAYED. The level
    is gone and refusing is correct.
  · **REPEATED TESTING** — price poked through and came back, repeatedly. By the
    operator's read that is a SOLID level and the sweep setup should fire:
    *"if it gets tested multiple times, it's a solid level."*

A raw count of closes beyond cannot separate them. What separates them is
whether price **RETURNED** — and the scorer already records that as
`reclaimed`. So the crossing that matters is `closes_beyond` x `reclaimed`,
which nothing currently looks at.

⚠️ AND `closes_beyond` IS A BIRTH-TIME SNAPSHOT (LIQ.3, liquidity_mapper:135):
counted over the 2-3 bars right after the raid and NEVER UPDATED. It answers
"did price accept beyond IMMEDIATELY?", not "is the level still holding?" —
which makes the veto more defensible than it first looked, and makes a p50 of 3
suspicious: if the window is only 2-3 bars, a median of 3 means the typical
sweep closed beyond on essentially EVERY bar of it. That is either a real
market fact or a saturating counter, and they are different problems.

⚠️ DEFAULTS TO 2026-08-11 ONWARD. LIQ.1 shipped that day and removed
London/Asia as sweepable pools; earlier logs are contaminated by levels that
were still forming during RTH. Pass `--since 2026-07-13` to include them
deliberately.

⚠️ READ-ONLY, streams, keeps only counters. Nothing is proposed — this reports
which case the veto is actually hitting.
"""

import argparse
import collections
import glob
import json
import os
import re
import sys

DEFAULT_GLOB = os.path.expanduser(
    "~/day_trader_pro/reports/regime_replay_*.jsonl")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", default=DEFAULT_GLOB)
    ap.add_argument("--since", default="2026-08-11",
                    help="LIQ.1 (London/Asia removed) shipped 2026-08-11; "
                         "earlier logs are contaminated.")
    a = ap.parse_args(argv[1:])

    files = sorted(f for f in glob.glob(a.logs)
                   if (re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(f))
                       or [""]) and
                   (re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(f)).group(1)
                    if re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(f))
                    else "") >= a.since)
    if not files:
        print(f"no tick log(s) at/after {a.since} matched {a.logs}")
        print("  ABSENT MEASUREMENT, not a null.")
        return 1

    cross = collections.Counter()      # (closes_beyond, reclaimed) -> n
    touches = collections.Counter()
    by_level = collections.Counter()   # level name -> vetoed-but-reclaimed
    scored = collections.Counter()     # (vetoed?, reclaimed?) -> scored>0
    named_ticks = 0

    for fp in files:
        with open(fp) as f:
            for line in f:
                if '"named"' not in line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:                              # noqa: BLE001
                    continue
                b = (r.get("breakdown") or {}).get("SWEEP_REVERSAL") or {}
                lvl = b.get("named")
                if not lvl:
                    continue
                named_ticks += 1
                cb = b.get("closes_beyond")
                rc = bool(b.get("reclaimed"))
                sc = float((r.get("scores") or {}).get("SWEEP_REVERSAL") or 0.0)
                cross[(cb, rc)] += 1
                touches[b.get("touch_count")] += 1
                vetoed = (cb is not None and cb >= 2)
                scored[(vetoed, rc, sc > 0)] += 1
                if vetoed and rc:
                    by_level[str(lvl)] += 1

    print("=" * 84)
    print("SWEEP ACCEPT PROBE - is the veto refusing DEFENDED levels or DEAD ones?")
    print(f"  {len(files)} session(s) since {a.since}   "
          f"{named_ticks:,} tick(s) with a NAMED pool")
    print("=" * 84)
    if not named_ticks:
        print("\n  no named pools in that window. ABSENT MEASUREMENT, not a null.")
        return 0

    print("\n  closes_beyond x reclaimed   <- THE CROSSING NOTHING CURRENTLY READS")
    for (cb, rc), n in sorted(cross.items(), key=lambda x: -x[1])[:12]:
        tag = ""
        if cb is not None and cb >= 2:
            tag = ("  <= VETOED **AND RECLAIMED** (a defended level)"
                   if rc else "  <= vetoed, never reclaimed (dead level)")
        print(f"    beyond={str(cb):>4}  reclaimed={str(rc):5}  {n:>9,}{tag}")

    defended = sum(n for (cb, rc), n in cross.items()
                   if cb is not None and cb >= 2 and rc)
    dead = sum(n for (cb, rc), n in cross.items()
               if cb is not None and cb >= 2 and not rc)
    tot_vetoed = defended + dead
    print(f"\n  OF EVERYTHING THE ACCEPT VETO REFUSES ({tot_vetoed:,} tick(s)):")
    if tot_vetoed:
        print(f"    {defended:>9,}  ({100.0*defended/tot_vetoed:5.1f}%)  "
              f"WERE RECLAIMED - price came back and the level held")
        print(f"    {dead:>9,}  ({100.0*dead/tot_vetoed:5.1f}%)  "
              f"were never reclaimed - genuine acceptance")

    print("\n  touch_count (the scorer's OWN 'solid level' signal, already recorded)")
    for k, n in sorted(touches.items(), key=lambda x: -x[1])[:8]:
        print(f"    touches={str(k):>4}  {n:>9,}")

    if by_level:
        print("\n  vetoed-but-reclaimed, by level name")
        for lvl, n in by_level.most_common(10):
            print(f"    {lvl:<18} {n:>9,}")

    print("\n  HOW TO READ IT")
    print("  · A large RECLAIMED share means the veto is killing exactly the")
    print("    setup the operator described - a level tested repeatedly and")
    print("    DEFENDED each time - by counting closes without asking whether")
    print("    price returned.")
    print("  · A large never-reclaimed share means the veto is doing its job and")
    print("    the archive is simply full of levels that genuinely broke.")
    print("  · `closes_beyond` is a BIRTH-TIME snapshot over 2-3 bars (LIQ.3), so")
    print("    a p50 at the top of that range may be a SATURATING COUNTER rather")
    print("    than a market fact. LIQ.3 already added `closes_beyond_live` and")
    print("    `invalidated` for the running question; the veto does not use them.")
    print("\n  NOTHING IS PROPOSED HERE.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
