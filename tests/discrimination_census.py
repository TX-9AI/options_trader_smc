#!/usr/bin/env python3
"""
tests/discrimination_census.py — v1.0 — 2026-08-07

RGM.1 / LAYER 1: DOES THE SCORE VECTOR CARRY ENOUGH INFORMATION TO RANK SIX
REGIMES? The emission fix (F7, conviction_integrator v2.1) stops the LABEL
thrashing. It does nothing about the EVIDENCE the label is chosen from. The
operator's framing, which is the right one: recognition is fast, but it is not
DISCRIMINATING — and a stable label chosen from an undiscriminating vector is
still a guess, just a steadier one.

WHAT IS ALREADY KNOWN. Fleet-wide, the share of ticks at exactly 0.00 runs
SWEEP_REVERSAL 96.0 · COMPRESSION 79.5 · TRENDING_BEAR 73.0 · TRENDING_BULL
71.2 · BREAKOUT_VOLATILE 63.8 · RANGING 45.7. That is per-regime. It does NOT
answer the question that matters, which is about the vector as a whole: on a
given tick, is there anything to choose BETWEEN?

WHY THE GRAMMAR MAKES THIS THE RIGHT QUESTION. regime_confluence's own header:

    score_R = (∏ hard_veto ∈{0,1}) · (∏ soft_necessary ∈[0,1]) · (Σ w·corrob)

A single hard veto at 0 annihilates the regime no matter how strong every
corroborator is. Annihilation does not just lower a score — it DESTROYS THE
ORDERING, because every vetoed regime lands on the same value. Two regimes at
0.00 are not "both weak by different amounts"; they are indistinguishable.

THE FOUR NUMBERS THIS PRODUCES
  1. DEAD TICKS — all six scores exactly 0. On these the argmax has NO
     information whatsoever and the label falls to conviction_integrator's
     `_TIEBREAK_ORDER`, a hardcoded tuple whose head is SWEEP_REVERSAL — the
     regime that is above zero on 4% of ticks. If this share is material, the
     label on those ticks is an artifact of a list ordering, not a read of the
     tape. That would be the same family of silent defect as the case-mismatch
     gate that made L2 unreachable for weeks.
  2. ZERO-ARGMAX TICKS — the winner itself scores 0. Weaker than (1) but the
     same problem: nothing was actually chosen.
  3. SEPARATION — the #1 minus #2 gap. A vector can be non-degenerate and still
     undiscriminating if the top two are a rounding apart. Reported as a
     distribution, and separately for the ticks that are NOT dead, because
     mixing dead ticks into the gap stats would report a confident 0.00 gap for
     a reason that has nothing to do with closeness.
  4. LIVE REGIMES PER TICK — how many score above zero at all. 1 means the
     grammar decided by elimination; 5-6 means it is genuinely ranking.

WHAT THIS DOES NOT SHOW. It does not say the scores are WRONG. A veto that
fires often may be correctly describing a condition that genuinely comes and
goes. It measures whether there is information to rank with, not whether the
ranking is right — `label_agreement.py` is the tool for the second question.
It also cannot say which veto is responsible; `veto_attribution.py` does that.

Read-only, stdlib only, streams one file at a time, always exits 0.
USAGE
    python3 tests/discrimination_census.py
    python3 tests/discrimination_census.py --since 2026-08-01

CHANGELOG
  v1.0 — 2026-08-07 — first issue. Built to give the Layer-1 discrimination
         problem a NUMBER before any fix to the veto grammar is proposed —
         the same discipline that turned the emission-law suspicion into the
         96.9% attribution, and that the three refuted hypotheses on this
         thread were all missing.
"""

import argparse
import collections
import glob
import json
import os
import re
import sys

REPLAY_GLOB = "~/day_trader_pro/reports/regime_replay_*.jsonl"
DATE_RE = re.compile(r"regime_replay_(20\d\d-\d\d-\d\d)\.jsonl$")
ZERO = 0.001

# conviction_integrator._TIEBREAK_ORDER, verbatim. The head of this tuple is
# what wins a dead tick, which is the whole point of measuring dead ticks.
TIEBREAK = ("SWEEP_REVERSAL", "BREAKOUT_VOLATILE", "COMPRESSION",
            "TRENDING_BULL", "TRENDING_BEAR", "RANGING")


def _pct(sv, p):
    if not sv:
        return 0.0
    return sv[min(len(sv) - 1, int(round(p / 100.0 * (len(sv) - 1))))]


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default=REPLAY_GLOB)
    ap.add_argument("--since", default="")
    a = ap.parse_args(argv[1:])

    paths = [p for p in sorted(glob.glob(os.path.expanduser(a.glob)))
             if DATE_RE.search(p)
             and (not a.since or DATE_RE.search(p).group(1) >= a.since)]
    if not paths:
        print(f"no replay files matched {a.glob}")
        return 0

    ticks = dead = zero_argmax = 0
    live_hist = collections.Counter()
    gaps = []                       # #1-#2, non-dead ticks only
    winners = collections.Counter()  # argmax on LIVE ticks
    dead_winners = collections.Counter()  # what a dead tick would be labelled
    per_day_dead = collections.Counter()
    per_day_ticks = collections.Counter()

    for path in paths:
        date = DATE_RE.search(path).group(1)
        for line in open(path, errors="ignore"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:                                    # noqa: BLE001
                continue
            sc = r.get("scores") or {}
            if not sc:
                continue
            # None (abstain) is NOT 0.0 (contradicted), but for the purpose of
            # "is there anything to rank?" both are unrankable. Counted as 0
            # and called out in the note so the reading stays honest.
            vals = sorted(((v or 0.0) for v in sc.values()), reverse=True)
            if len(vals) < 2:
                continue
            ticks += 1
            per_day_ticks[date] += 1
            live = sum(1 for v in vals if v > ZERO)
            live_hist[live] += 1
            if live == 0:
                dead += 1
                per_day_dead[date] += 1
                dead_winners[TIEBREAK[0]] += 1
                continue
            if vals[0] <= ZERO:
                zero_argmax += 1
            gaps.append(round(vals[0] - vals[1], 4))
            top = max(sc.items(),
                      key=lambda kv: ((kv[1] or 0.0),
                                      -TIEBREAK.index(kv[0])
                                      if kv[0] in TIEBREAK else -9))
            winners[top[0]] += 1

    g = sorted(gaps)
    print(f"files: {len(paths)}  ({DATE_RE.search(paths[0]).group(1)} .. "
          f"{DATE_RE.search(paths[-1]).group(1)})")
    print(f"ticks with a score vector: {ticks}")
    print()
    print("=== 1. DEAD TICKS (all six regimes at exactly 0) ===")
    print(f"  {dead} / {ticks} = {100.0*dead/max(1,ticks):.1f}%")
    print(f"  on these the label is decided by _TIEBREAK_ORDER, whose head is")
    print(f"  {TIEBREAK[0]} — a regime above zero on ~4% of ticks.")
    print(f"  zero-argmax ticks (winner itself is 0, live>0 impossible): "
          f"{zero_argmax}")
    print()
    print("=== 2. HOW MANY REGIMES ARE LIVE AT ALL ===")
    for k in range(0, 7):
        n = live_hist.get(k, 0)
        if n or k <= 3:
            print(f"  {k} live: {n:8d}  ({100.0*n/max(1,ticks):.1f}%)")
    print()
    print("=== 3. SEPARATION — #1 minus #2, DEAD TICKS EXCLUDED ===")
    print(f"  n={len(g)}  p10={_pct(g,10):.3f}  p50={_pct(g,50):.3f}  "
          f"p90={_pct(g,90):.3f}  max={g[-1] if g else 0:.3f}")
    tiny = sum(1 for x in g if x <= 0.05)
    print(f"  gap <= 0.05 (effectively a coin flip): {tiny} = "
          f"{100.0*tiny/max(1,len(g)):.1f}% of live ticks")
    print()
    print("=== 4. WHO WINS, ON LIVE TICKS ===")
    for reg, n in winners.most_common():
        print(f"  {reg:<20}{n:8d}  ({100.0*n/max(1,sum(winners.values())):.1f}%)")
    print()
    print("=== 5. DEAD-TICK SHARE BY SESSION (a spike is a data day, not a")
    print("       grammar day — check the tape before reading it as evidence) ===")
    for d in sorted(per_day_ticks):
        t, dd = per_day_ticks[d], per_day_dead.get(d, 0)
        print(f"  {d}: {100.0*dd/max(1,t):5.1f}%  ({dd}/{t})")
    print()
    print("  NOTE: an ABSTAIN (score None) is counted as 0 here. None means")
    print("  'unobservable' and 0.0 means 'contradicted' — different causes,")
    print("  but identically unrankable, which is what this tool measures.")
    print("  Whether the scores are RIGHT is label_agreement.py's question;")
    print("  WHICH veto zeroed them is veto_attribution.py's.")
    return 0


if __name__ == "__main__":
    try:
        rc = main(sys.argv)
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        rc = 0
    sys.exit(rc)
