#!/usr/bin/env python3
"""
tests/condor_approach.py — v1.0 — 2026-08-04   (item AI's decisive measurement)

IS `CONDOR_TRIGGER_APPROACH = 0.65` A PARAMETER TO FIT, OR IS THE MIDPOINT
WRONG? Those need opposite fixes and nothing has been able to tell them apart.

WHAT THIS READS. `condor_abandon` journal rows (iron_condor_strategy
v-approachalways), one per dead plan, carrying how far price actually travelled
toward each trigger as a fraction of the distance it needed. 1.0 = the trigger
was reached.

WHY THE FRACTION AND NOT THE DOLLARS. The denominator is trigger-minus-
spot-at-plan — the REQUIRED journey — so the number is comparable across
symbols priced from $30 to $900 and across days of different volatility. A
dollar distance is not.

HOW TO READ THE ANSWER, pre-registered here so the threshold is not chosen
after seeing the data:

    p90 approach < 0.40   ->  GEOMETRY. The trigger sits where price does not
                              go on this tape. Re-tuning 0.65 cannot reach it;
                              the ANCHOR is the problem (item AI's "expected
                              move measured from a MIDPOINT that has not been
                              identified yet" — the pitchfork/VWAP work).
    p90 approach >= 0.60  ->  PARAMETER. Price routinely gets most of the way.
                              CONDOR_TRIGGER_APPROACH can be fitted from this
                              distribution, and the geometry stands.
    in between            ->  NEITHER IS ESTABLISHED. Report it and say so.

WHAT IT CANNOT SAY. Reaching a trigger is not earning a credit: nothing here
prices premium, and a nearer strike collects less. This bounds ONE side of the
trade-off — whether the entry is reachable at all — which is the side that has
been silently failing.

CONTEXT THAT MAKES A LOW NUMBER MEANINGFUL: on 2026-08-04 plan lifetimes ran
1-94 minutes, median ~30, several 88-94. Plans were ALIVE across most of the
window, so a low approach means "price never went there", not "no time".

Read-only. stdlib only. Runs on control.

USAGE
    python3 tests/condor_approach.py
    python3 tests/condor_approach.py --since 2026-08-04 --by symbol
"""

import argparse
import collections
import glob
import json
import os
import re
import sys

JOURNAL_GLOB = "~/day_trader_pro/signal_journal/*/*.jsonl"
DATE_RE = re.compile(r"(20\d\d-\d\d-\d\d)")

# Pre-registered, stated in the module docstring above, asserted in the tests.
GEOMETRY_MAX = 0.40
PARAMETER_MIN = 0.60
MIN_N = 20


def _pct(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    return s[min(int(q * len(s)), len(s) - 1)]


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", default=JOURNAL_GLOB)
    ap.add_argument("--since", default="2026-08-04",
                    help="first date the condor_abandon row existed")
    ap.add_argument("--until", default="9999-12-31")
    ap.add_argument("--by", default="", choices=("", "symbol", "cause"))
    a = ap.parse_args(argv[1:])

    rows, causes = [], collections.Counter()
    for path in sorted(glob.glob(os.path.expanduser(a.journal))):
        m = DATE_RE.search(path)
        if not m or not (a.since <= m.group(1) <= a.until):
            continue
        try:
            fh = open(path)
        except Exception:                                        # noqa: BLE001
            continue
        with fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:                                # noqa: BLE001
                    continue
                if r.get("event") != "condor_abandon":
                    continue
                ap_ = r.get("approach") or {}
                causes[r.get("cause", "?")] += 1
                rows.append({"sym": r.get("symbol", "?"),
                             "date": m.group(1),
                             "cause": r.get("cause", "?"),
                             **ap_})

    if not rows:
        print(f"No condor_abandon rows in {a.since}..{a.until}.")
        print("The row ships with iron_condor_strategy v-approachalways "
              "(2026-08-04); sessions before that\ndeath-reported only the "
              "regime, which is exactly the gap this measures. Nothing to read "
              "yet\nis the honest answer — not a null.")
        return 2

    # BEST approach per plan: a plan only needs ONE side to fire, so the
    # measurement is how close the CLOSER side came, not the average of both.
    best = []
    for r in rows:
        cands = [v for v in (r.get("call_approach"), r.get("put_approach"))
                 if v is not None]
        if cands:
            r["best"] = max(cands)
            best.append(r["best"])

    print(f"window      : {a.since} .. {a.until}")
    print(f"dead plans  : {len(rows)}   with a usable approach: {len(best)}")
    print(f"causes      : " + "  ".join(f"{k} {v}" for k, v in causes.most_common()))
    print("metric      : fraction of the REQUIRED journey to the nearer "
          "trigger (1.0 = fired)\n")

    if len(best) < MIN_N:
        print(f"  n={len(best)} REFUSED (under n={MIN_N}) — underpowered, not "
              f"a null.")
        return 0

    p50, p90, p95 = _pct(best, .50), _pct(best, .90), _pct(best, .95)
    reached = sum(1 for x in best if x >= 1.0)
    print("=" * 66)
    print("APPROACH DISTRIBUTION")
    print("=" * 66)
    print(f"  p50 {p50:.0%}   p75 {_pct(best, .75):.0%}   p90 {p90:.0%}   "
          f"p95 {p95:.0%}   max {max(best):.0%}")
    print(f"  reached the trigger: {reached}/{len(best)} ({reached/len(best):.0%})")

    if a.by:
        key = "sym" if a.by == "symbol" else "cause"
        print(f"\n  by {a.by}")
        grp = collections.defaultdict(list)
        for r in rows:
            if "best" in r:
                grp[r[key]].append(r["best"])
        for k, xs in sorted(grp.items(), key=lambda kv: -len(kv[1])):
            mark = "" if len(xs) >= MIN_N else f"  <- n<{MIN_N}"
            print(f"    {str(k)[:16]:<18}{len(xs):>5}  p50 {_pct(xs,.5):.0%}"
                  f"  p90 {_pct(xs,.9):.0%}{mark}")

    print("\n" + "=" * 66)
    print("VERDICT  (thresholds pre-registered in this file's docstring)")
    print("=" * 66)
    if p90 < GEOMETRY_MAX:
        print(f"  GEOMETRY. p90 approach is {p90:.0%}, under the {GEOMETRY_MAX:.0%}")
        print("  line. Price does not go where the trigger sits, so no value of")
        print("  CONDOR_TRIGGER_APPROACH reaches it — lowering it would only sell")
        print("  nearer the middle, which is the un-floored behaviour that bled")
        print("  P&L for ~3 weeks before the dual floor existed. The ANCHOR is")
        print("  the problem: item AI's midpoint, and the pitchfork/VWAP work.")
    elif p90 >= PARAMETER_MIN:
        print(f"  PARAMETER. p90 approach is {p90:.0%}, at or above "
              f"{PARAMETER_MIN:.0%} —")
        print("  price routinely completes most of the journey. The geometry")
        print("  stands and CONDOR_TRIGGER_APPROACH can be FITTED from this")
        print("  distribution rather than guessed. Place it where the marginal")
        print("  fire still clears fee-adjusted expectancy, not at a percentile.")
    else:
        print(f"  NEITHER ESTABLISHED. p90 approach is {p90:.0%}, between "
              f"{GEOMETRY_MAX:.0%} and {PARAMETER_MIN:.0%}.")
        print("  Say so rather than picking the nearer story. More sessions, or")
        print("  a per-symbol split once the cells clear n.")
    print("\n  NOT A CREDIT MEASUREMENT. Reaching a trigger is not earning a")
    print("  premium; nothing here prices one. This bounds whether the entry is")
    print("  REACHABLE — the side that has been failing silently.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
