#!/usr/bin/env python3
"""
tests/regime_switch_cost.py — v1.1 — 2026-08-06

HOW MUCH OF THE LABEL CHURN IS A REAL REGIME CHANGE, AND HOW MUCH IS ARGMAX
FLIPPING ON A MARGIN? Replays the recorded per-tick scores and re-derives the
committed label under a SWITCHING COST: the challenger must beat the incumbent
by at least `delta` before the label is allowed to change.

WHY. Layer 2 is `always-argmax` — its own log line says so. Whichever regime is
fractionally ahead wins, every tick, with no cost to changing its mind. It damps
raw argmax by about 1.6x (961 flips -> 586 committed switches on 2026-08-05),
so damping exists, but 586 across 29 symbols is **~20 switches per symbol per
session** — one every twenty minutes.

THE OPERATOR'S PRIOR, stated 2026-08-06 and recorded here because it is the only
external check available: a session realistically contains ONE OR TWO regime
changes. A tape that starts trending and goes sideways; a muted open that catches
a move late. Not dozens. That is a 10-20x discrepancy between what the engine
reports and what the market does.

WHY THE CHURN IS EXPECTED FROM THE A2 RESULT. TRENDING reads a ~70-minute
lookback and RANGING a ~25-minute one, so both are frequently TRUE at once
(3.9% of ticks with both >0.5 — and on those ticks L2 commits at median
conviction 1.00). When two labels are genuinely co-true, argmax picking between
them is a coin flip on noise, and every flip is a "regime change" that is
nothing of the sort.

WHAT THIS TOOL IS AND IS NOT. It measures how many switches survive at each
delta, and how long the label holds. It does NOT show that fewer switches make
money — that needs the trade join and more sessions. **Do not read a delta off
this table and ship it.** Picking the delta that matches the prior is fitting to
a belief; the prior tells you which region is plausible, and the outcome data
has to confirm it later. Both halves are required.

Read-only, stdlib only, control-side.

USAGE
    python3 tests/regime_switch_cost.py
    python3 tests/regime_switch_cost.py --since 2026-07-28 --deltas 0,.02,.05,.1
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
# The operator's prior, 2026-08-06: a real session holds 1-2 regime changes.
PRIOR_LO, PRIOR_HI = 1.0, 3.0


def _committed(recs, delta: float):
    # `recs` is a list of SCORE DICTS (v1.1), not full replay records.
    """Re-derive the label sequence under a switching cost.

    The incumbent keeps the label unless a challenger leads it by `delta`.
    delta=0 reproduces plain argmax, which is the control arm: if the delta=0
    row does not roughly match the engine's own reported switch count, this
    harness is not modelling the engine and nothing below it can be trusted.
    """
    label = None
    switches = 0
    holds = []
    held = 0
    for sc in recs:
        if not sc:
            continue
        best = max(sc, key=lambda k: sc.get(k) or 0.0)
        bestv = float(sc.get(best) or 0.0)
        if label is None:
            label, held = best, 1
            continue
        curv = float(sc.get(label) or 0.0)
        if best != label and (bestv - curv) >= delta:
            switches += 1
            holds.append(held)
            label, held = best, 1
        else:
            held += 1
    if held:
        holds.append(held)
    return switches, holds


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default=REPLAY_GLOB)
    ap.add_argument("--since", default="")
    ap.add_argument("--deltas", default="0,0.02,0.05,0.10,0.15,0.20,0.30")
    a = ap.parse_args(argv[1:])

    deltas = [float(x) for x in a.deltas.split(",") if x.strip()]

    # v1.1 — ONE FILE AT A TIME, AND ONLY THE SCORES.
    # v1.0 read all 186,582 records into one dict and kept the FULL record when
    # the sweep only ever touches `scores`. It was OOM-KILLED on the 19-session
    # corpus — `Killed`, no traceback. That is the third tool in this repo to die
    # the same way (ramp_calibration, a2_cooccurrence, this), and I wrote it four
    # days after fixing the identical bug in a2_cooccurrence. The pattern is
    # "load everything, then filter", which works until the corpus crosses a
    # threshold and then fails silently.
    # A symbol-day series never spans files, so a file can be swept and dropped
    # before the next one is opened: memory is now one session, not nineteen.
    paths = [p for p in sorted(glob.glob(os.path.expanduser(a.glob)))
             if DATE_RE.search(p)
             and (not a.since or DATE_RE.search(p).group(1) >= a.since)]
    if not paths:
        print(f"no replay files matched {a.glob}"
              + (f" since {a.since}" if a.since else ""))
        return 2

    tot = {d: 0 for d in deltas}
    holds = {d: [] for d in deltas}
    days, n_series = [], 0
    for path in paths:
        day = DATE_RE.search(path).group(1)
        by_sym = collections.defaultdict(list)
        for line in open(path, errors="ignore"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:                                    # noqa: BLE001
                continue
            sc = r.get("scores")
            if sc:
                # ONLY the scores. Everything else in a replay record — the
                # breakdown, the engine state — is dead weight here.
                by_sym[r.get("sym", "?")].append(sc)
        if not by_sym:
            continue
        days.append(day)
        n_series += len(by_sym)
        for d in deltas:
            for series in by_sym.values():
                sw, h = _committed(series, d)
                tot[d] += sw
                holds[d].extend(h)
        del by_sym

    if not days:
        print("replay files found but no scored ticks in them")
        return 2

    print(f"{len(days)} session(s) {days[0]}..{days[-1]} · {n_series} "
          f"symbol-session series\n")
    print(f"  {'delta':>7}{'switches':>11}{'per sym/day':>14}"
          f"{'median hold':>13}{'p90 hold':>11}   verdict")

    for d in deltas:
        tot_d, holds_d = tot[d], holds[d]
        per = tot_d / n_series if n_series else 0.0
        holds_d.sort()
        med = holds_d[len(holds_d) // 2] if holds_d else 0
        p90 = (holds_d[min(int(.9 * len(holds_d)), len(holds_d) - 1)]
               if holds_d else 0)
        if per > PRIOR_HI * 3:
            v = "churn — argmax on a margin"
        elif per > PRIOR_HI:
            v = "still above the prior"
        elif per >= PRIOR_LO:
            v = "<- matches the operator prior (1-3/session)"
        else:
            v = "below the prior — may be missing real transitions"
        print(f"  {d:>7.2f}{tot_d:>11,}{per:>14.1f}{med:>13}{p90:>11}   {v}")

    print("\n  HOLD is in TICKS (~15s each): 4 ticks ~ 1 minute, 240 ~ 1 hour.")
    print("  A label that survives one or two ticks is not describing a regime.")
    print("\n  THE delta=0 ROW IS THE CONTROL. If it does not roughly match the")
    print("  engine's own reported switch count, this harness is not modelling")
    print("  the engine and every row below it is meaningless.")
    print("\n  ⚠️ DO NOT SHIP A DELTA OFF THIS TABLE ALONE. Choosing the value")
    print("  that matches the prior is fitting to a belief. The prior says which")
    print("  region is PLAUSIBLE; whether fewer switches also improve outcomes")
    print("  needs the trade join and more sessions. Both halves are required.")
    print("\n  AND NOTE WHAT A SWITCHING COST CANNOT FIX: when TRENDING and")
    print("  RANGING are genuinely BOTH TRUE (different lookbacks — see MECHANICS")
    print("  A2), a delta only decides which one wins more stubbornly. It does")
    print("  not make the choice meaningful. That is the axis-split question.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
