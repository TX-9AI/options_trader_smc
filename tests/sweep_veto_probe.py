#!/usr/bin/env python3
"""
tests/sweep_veto_probe.py — v1.0 — 2026-08-15   (SWP.6)

WHY DOES EVERY NAMED-POOL SWEEP SCORE 0.000?

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python tests/sweep_veto_probe.py

────────────────────────────────────────────────────────────────────────────
THE FINDING THIS EXISTS TO EXPLAIN
────────────────────────────────────────────────────────────────────────────
`replay_confluence --sweeps` over 25 archived sessions found **dozens of
named-pool sweeps** — PDH, PDL, NY High, NY Low, London High, London Low —
across nearly every symbol. **Every single one scored 0.000, with
`reclaimed=yes`.**

Including FRESH ones: AVGO PDH at `age_bars=3`, JPM NY Low at 9, TSLA NY Low
at 9. Named, reclaimed, minutes old, and still zero.

**So SWEEP_REVERSAL is not rare on this tape. The mapper finds the events and
the scorer refuses to score them.** That single fact would explain the 2%
fleet-wide dominance, L1.7's "SWEEP tape gap", and the strategy's 0.4% live
win rate — one cause, three symptoms that were being investigated separately.

────────────────────────────────────────────────────────────────────────────
WHAT THIS MEASURES
────────────────────────────────────────────────────────────────────────────
`_sweep()` applies THREE HARD VETOES — any one of them forces the score to
zero regardless of every other term:

    veto_loc     = 1.0 if named      else 0.0
    veto_reclaim = 1.0 if reclaimed  else 0.0
    veto_accept  = 1.0 if closes_beyond < SWEEP_ACCEPT_CLOSES (2) else 0.0

plus `age_decay`, which multiplies the surviving score toward zero as the
sweep ages past `SWEEP_STALE_HARD_BARS`.

**The hypothesis is `veto_accept`**, because the archive shows ages like 285,
321, 354 and 393 bars — pools swept HOURS earlier that price has been living
beyond ever since, so `closes_beyond` is large and the veto fires permanently.
But `age_decay` could be zeroing them independently, and **the two call for
different fixes**, so this counts them separately rather than assuming.

⚠️ READ-ONLY. Streams the tick logs, keeps only counters, writes nothing to the
repo. Memory is constant regardless of archive size — the same reason
`replay_confluence` v2.6/v2.7 stream.
"""

import collections
import glob
import json
import os
import sys

DEFAULT_GLOB = os.path.expanduser(
    "~/day_trader_pro/reports/regime_replay_*.jsonl")


def main(argv):
    pattern = argv[1] if len(argv) > 1 else DEFAULT_GLOB
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"no tick log(s) matched: {pattern}")
        d = os.path.dirname(pattern) or "."
        if os.path.isdir(d):
            near = sorted(x for x in os.listdir(d) if x.endswith(".jsonl"))
            print(f"  in {d}: {len(near)} .jsonl file(s)"
                  + (f", e.g. {near[0]}" if near else ""))
        print("  ABSENT MEASUREMENT, not a null.")
        return 1

    combos = collections.Counter()
    which = collections.Counter()
    ages = []
    beyonds = []
    examples = []
    named_ticks = 0
    scored_gt0 = 0

    for fp in files:
        with open(fp) as f:
            for line in f:
                if '"named"' not in line:
                    continue                    # cheap prefilter before parsing
                try:
                    r = json.loads(line)
                except Exception:                              # noqa: BLE001
                    continue
                bd = (r.get("breakdown") or {}).get("SWEEP_REVERSAL") or {}
                if not bd.get("named"):
                    continue
                named_ticks += 1
                sc = float((r.get("scores") or {}).get("SWEEP_REVERSAL") or 0.0)
                if sc > 0:
                    scored_gt0 += 1

                vl = bd.get("veto_loc")
                vr = bd.get("veto_reclaim")
                va = bd.get("veto_accept")
                ad = bd.get("age_decay")
                combos[(vl, vr, va, sc > 0)] += 1

                # attribute the zero to the FIRST thing that forces it
                if sc == 0.0:
                    if va == 0.0:
                        which["veto_accept (closes_beyond >= 2)"] += 1
                    elif vr == 0.0:
                        which["veto_reclaim (never reclaimed)"] += 1
                    elif vl == 0.0:
                        which["veto_loc (level not named)"] += 1
                    elif ad is not None and float(ad) == 0.0:
                        which["age_decay == 0 (stale past the hard bar)"] += 1
                    else:
                        which["none of the hard vetoes — a WEIGHTED term is 0"] += 1

                if bd.get("age_bars") is not None:
                    ages.append(int(bd["age_bars"]))
                if bd.get("closes_beyond") is not None:
                    beyonds.append(int(bd["closes_beyond"]))
                if sc == 0.0 and len(examples) < 10:
                    examples.append((
                        str(r.get("sym", "?")), str(bd.get("named"))[:14],
                        bd.get("closes_beyond"), bd.get("age_bars"),
                        bd.get("age_decay"), vl, vr, va))

    print("=" * 86)
    print("SWEEP VETO PROBE — why named-pool sweeps score zero")
    print(f"  {len(files)} session(s)   {named_ticks:,} tick(s) with a NAMED pool"
          f"   {scored_gt0:,} scored > 0")
    print("=" * 86)

    if not named_ticks:
        print("\n  NO NAMED POOLS AT ALL. That is a different problem from a zero")
        print("  score: the mapper is not naming levels in the replay path.")
        return 0

    print("\n  WHAT FORCES THE ZERO (first cause per tick)")
    for k, v in which.most_common():
        print(f"    {v:>8,}  ({100.0*v/named_ticks:5.1f}%)  {k}")

    print("\n  VETO COMBINATIONS  (loc, reclaim, accept) -> scored>0")
    for (vl, vr, va, pos), v in combos.most_common(8):
        print(f"    {v:>8,}  loc={vl}  reclaim={vr}  accept={va}  -> {pos}")

    def pct(vals, p):
        return sorted(vals)[int(len(vals) * p)] if vals else 0

    if beyonds:
        print(f"\n  closes_beyond   n={len(beyonds):,}  min={min(beyonds)}  "
              f"p50={pct(beyonds,0.5)}  p90={pct(beyonds,0.9)}  max={max(beyonds)}")
        fresh = sum(1 for b in beyonds if b < 2)
        print(f"    under the SWEEP_ACCEPT_CLOSES=2 bar: {fresh:,} "
              f"({100.0*fresh/len(beyonds):.1f}%)")
    if ages:
        print(f"  age_bars        n={len(ages):,}  min={min(ages)}  "
              f"p50={pct(ages,0.5)}  p90={pct(ages,0.9)}  max={max(ages)}")

    print("\n  EXAMPLES (sym, level, closes_beyond, age_bars, age_decay, "
          "veto_loc/reclaim/accept)")
    for e in examples:
        print(f"    {e[0]:6} {e[1]:15} beyond={str(e[2]):>5}  age={str(e[3]):>5}  "
              f"decay={str(e[4]):>6}  vetoes={e[5]}/{e[6]}/{e[7]}")

    print("\n  HOW TO READ IT")
    print("  · If `veto_accept` dominates, the scorer is refusing sweeps because")
    print("    price CLOSED BEYOND the level 2+ times. On a pool swept hours")
    print("    earlier that price has lived beyond since, that veto can never")
    print("    clear again — the sweep and the later acceptance are the same tape")
    print("    at different times, and the veto may be reading the wrong window.")
    print("  · If `age_decay` dominates, the events are real but STALE by the time")
    print("    they are scored, which is a freshness problem, not a veto problem.")
    print("  · Those need DIFFERENT fixes, which is why they are counted apart.")
    print("\n  ⚠️ NOTHING IS PROPOSED HERE. This says WHICH gate closes, not")
    print("     whether it should — that decision needs the operator.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
