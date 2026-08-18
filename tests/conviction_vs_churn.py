#!/usr/bin/env python3
"""
tests/conviction_vs_churn.py — v1.0 — 2026-08-17   (L2.7)

DOES L2 CONVICTION KNOW HOW CONTESTED ITS OWN LABEL WAS?

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python tests/conviction_vs_churn.py

────────────────────────────────────────────────────────────────────────────
THE QUESTION, AND WHY IT IS NOT ACADEMIC
────────────────────────────────────────────────────────────────────────────
QQQ, 2026-08-17. L1 could not decide: RANGING scored on **61%** of ticks —
MORE than TRENDING_BULL's 49% — and nothing dominated (BULL 35, RANG 26,
BREA 19, COMP 15). The argmax flipped **29 times**.

L2 emitted **BULL 81%**, with **2 label switches — churn crushed 14.5x**.

**That is the integrator doing exactly its job, and it is why three directional
trades stopped out.** On a genuinely trending tape, crushing churn is the whole
point. On a tape where the argmax flips 29 times because nothing is winning,
the SAME smoothing converts *"the engine cannot decide"* into *"the engine is
confident"* — and every consumer downstream reads the second.

Contrast TSLA 2026-08-04, a real trend day: BULL `>0%` **100%**, dominance
**99%**, **1** argmax flip. **81%-from-29-flips and 99%-from-1-flip are not the
same claim**, and nothing currently distinguishes them.

⚠️ THE SUSPICION THIS TESTS: **conviction measures STABILITY OF THE OUTPUT when
a consumer needs AGREEMENT IN THE INPUT.** The smoothing is what PRODUCES the
high number — "churn crushed 14.5x" means the integrator worked hard to hold a
label the tape kept disagreeing with, and then reported the result as strength.

────────────────────────────────────────────────────────────────────────────
WHAT IT MEASURES
────────────────────────────────────────────────────────────────────────────
Per SYMBOL-SESSION, from the replay tick logs:
  · `flips`      — L1 argmax changes (the contest)
  · `switches`   — L2 committed-label changes (what survived smoothing)
  · `crush`      — flips / switches (how hard the integrator worked)
  · `conv_p50`   — median L2 conviction (what it TOLD everyone)
  · `dom%`       — share of ticks the winning L1 regime led

**The test: does `conv_p50` fall as `flips` rises?** If it does, conviction
already carries the information and no change is needed. **If conviction is FLAT
against flips, it is blind to the contest** — and a high-flip session is
indistinguishable downstream from a clean one.

⚠️ REPORTS A CORRELATION, PROPOSES NOTHING. A relationship here does not by
itself say what conviction SHOULD be; it says whether the current number can
tell these sessions apart. The fix, if any, is a separate decision.

⚠️ AND IT NAMES ITS OWN WEAKNESS: sessions are not independent trials. A
trending week supplies many low-flip sessions and a chop week many high-flip
ones, so n is closer to the number of WEEKS than the number of rows. Read the
session count, not the row count.
"""

import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPORTS = os.path.expanduser("~/day_trader_pro/reports")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports", default=REPORTS)
    ap.add_argument("--since", default="2026-01-01")
    a = ap.parse_args(argv[1:])

    from analysis.regime_confluence import REGIMES

    files = sorted(f for f in glob.glob(os.path.join(a.reports,
                                                     "regime_replay_*.jsonl"))
                   if (re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(f))
                       and re.search(r"(\d{4}-\d{2}-\d{2})",
                                     os.path.basename(f)).group(1) >= a.since))
    if not files:
        print(f"no replay logs at/after {a.since} in {a.reports}")
        print("  ABSENT MEASUREMENT, not a null.")
        return 1

    # stream: keep only per-(date,sym) sequences of (argmax, l2label, conviction)
    rows = {}
    for fp in files:
        day = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(fp)).group(1)
        with open(fp) as f:
            for line in f:
                if '"l2"' not in line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:                              # noqa: BLE001
                    continue
                l2 = r.get("l2") or {}
                sc = r.get("scores") or {}
                if not l2 or not sc:
                    continue
                top = max(REGIMES, key=lambda k: (sc.get(k) or 0))
                if (sc.get(top) or 0) <= 0:
                    continue
                key = (day, str(r.get("sym", "?")))
                rows.setdefault(key, []).append(
                    (top, l2.get("regime"), l2.get("c")))

    if not rows:
        print("no L2 records in those logs. ABSENT MEASUREMENT, not a null.")
        return 1

    out = []
    for (day, sym), seq in sorted(rows.items()):
        if len(seq) < 30:
            continue
        flips = sum(1 for x, y in zip(seq, seq[1:]) if x[0] != y[0])
        switches = sum(1 for x, y in zip(seq, seq[1:]) if x[1] != y[1])
        convs = sorted(c for _t, _l, c in seq if isinstance(c, (int, float)))
        if not convs:
            continue
        cp50 = convs[len(convs) // 2]
        tally = {}
        for t, _l, _c in seq:
            tally[t] = tally.get(t, 0) + 1
        dom = 100.0 * max(tally.values()) / len(seq)
        out.append((day, sym, len(seq), flips, switches, cp50, dom))

    if not out:
        print("no symbol-session had >=30 scored ticks.")
        return 1

    print("=" * 92)
    print("CONVICTION vs CHURN — does L2 conviction know how contested its label was?")
    print(f"  {len(out)} symbol-session(s) across {len(files)} session file(s)")
    print("=" * 92)

    # the headline: conviction binned by flip count
    bins = [(0, 2, "0-2   (clean)"), (3, 9, "3-9"), (10, 24, "10-24"),
            (25, 10 ** 9, "25+   (contested)")]
    print(f"\n  {'argmax flips':<20}{'n':>5}{'conv p50':>10}{'dom% p50':>10}"
          f"{'crush (flips/sw)':>19}")
    print("  " + "-" * 62)
    for lo, hi, label in bins:
        grp = [r for r in out if lo <= r[3] <= hi]
        if not grp:
            continue
        cs = sorted(r[5] for r in grp)
        ds = sorted(r[6] for r in grp)
        crush = [r[3] / max(1, r[4]) for r in grp]
        print(f"  {label:<20}{len(grp):>5}{cs[len(cs)//2]:>10.2f}"
              f"{ds[len(ds)//2]:>9.0f}%{sum(crush)/len(crush):>19.1f}x")

    print("\n  HOW TO READ IT")
    print("  · conv p50 FALLING as flips rise -> conviction already carries the")
    print("    contest, and no change is needed.")
    print("  · conv p50 FLAT across bins -> **conviction is blind to it**: a")
    print("    29-flip session and a 1-flip session make the same claim, and no")
    print("    consumer downstream can tell them apart.")
    print("  · crush rising with flips is EXPECTED - that is the integrator")
    print("    working. The question is whether it REPORTS having worked.")

    print("\n  MOST-CONTESTED SESSIONS (highest flips)")
    print(f"    {'date':11}{'sym':7}{'ticks':>6}{'flips':>7}{'sw':>5}"
          f"{'conv':>7}{'dom%':>7}")
    for day, sym, n, fl, sw, cp, dm in sorted(out, key=lambda r: -r[3])[:10]:
        print(f"    {day:11}{sym:7}{n:>6}{fl:>7}{sw:>5}{cp:>7.2f}{dm:>6.0f}%")

    print("\n  CLEANEST SESSIONS (fewest flips, for contrast)")
    for day, sym, n, fl, sw, cp, dm in sorted(out, key=lambda r: r[3])[:5]:
        print(f"    {day:11}{sym:7}{n:>6}{fl:>7}{sw:>5}{cp:>7.2f}{dm:>6.0f}%")

    print("\n  ⚠️ SESSIONS ARE NOT INDEPENDENT TRIALS. A trending week supplies")
    print("     many low-flip sessions and a chop week many high-flip ones, so n")
    print("     is closer to the number of WEEKS than the number of rows.")
    print("  ⚠️ NOTHING IS PROPOSED HERE. This says whether the current number")
    print("     can tell these sessions apart, not what it should be instead.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
