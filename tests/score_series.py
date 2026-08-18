#!/usr/bin/env python3
"""
tests/score_series.py — v1.0 — 2026-08-06

ARE THE SCORES THEMSELVES UNSTABLE? Dumps one symbol-day's per-regime score
series so the question can be answered by looking at it.

WHY THIS AND NOT MORE AGGREGATE STATS. The switching-cost sweep
(regime_switch_cost v1.1) came back with a gradual decay, not a cliff:

    delta 0.00   25.1 switches/sym/day   median hold  5 ticks
    delta 0.10   13.5                                12
    delta 0.30    8.2                                23   <- still 4x the prior

On a planted world with two real regime changes buried in tick noise, delta=0.10
collapsed churn from 104 to 2.5 — a cliff. Real tape does not do that. If the
churn were argmax flipping on a MARGIN, a modest switching cost would remove
most of it. It does not, which means the scores are crossing each other by WIDE
margins, repeatedly, all session.

A switching cost damps the REPORTING of an unstable signal. It cannot stabilise
the signal. So the question moved one layer down — to Layer 1, where the scores
are computed — and the fastest way to answer it is to look at the series rather
than compute another summary of it.

WHAT TO LOOK FOR in the sparkline:
  * A score swinging 0.2 -> 0.7 -> 0.2 within minutes is the finding. The
    classifier is recomputing from a lookback short enough that ordinary tape
    movement changes its answer completely.
  * A score that drifts smoothly and crosses another one a few times per session
    is a healthy signal, and would mean the churn is elsewhere.
  * Two scores tracking each other closely and swapping the lead repeatedly is
    the A2 co-truth case (different lookbacks, both true) — which no smoothing
    or delta fixes, and which is the axis-split question.

Read-only, stdlib only, control-side.

USAGE
    python3 tests/score_series.py --sym SPX
    python3 tests/score_series.py --sym MSFT --date 2026-08-06 --every 4
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
BLOCKS = " ▁▂▃▄▅▆▇█"
SHORT = {"TRENDING_BULL": "BULL", "TRENDING_BEAR": "BEAR", "RANGING": "RANG",
         "BREAKOUT_VOLATILE": "BREA", "COMPRESSION": "COMP",
         "SWEEP_REVERSAL": "SWEE"}


def _spark(vals):
    return "".join(BLOCKS[min(int((v or 0.0) * 8), 8)] for v in vals)


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default=REPLAY_GLOB)
    ap.add_argument("--sym", required=True)
    ap.add_argument("--date", default="", help="default: the latest session")
    ap.add_argument("--every", type=int, default=8,
                    help="sample every Nth tick (8 ~ every 2 minutes). The full "
                         "series is ~750 ticks and will not fit a phone screen.")
    ap.add_argument("--width", type=int, default=90)
    a = ap.parse_args(argv[1:])

    paths = {DATE_RE.search(p).group(1): p
             for p in glob.glob(os.path.expanduser(a.glob)) if DATE_RE.search(p)}
    if not paths:
        print(f"no replay files matched {a.glob}")
        return 2
    day = a.date or max(paths)
    if day not in paths:
        print(f"no replay for {day}. have: {', '.join(sorted(paths)[-5:])}")
        return 2

    series = []
    for line in open(paths[day], errors="ignore"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:                                        # noqa: BLE001
            continue
        if r.get("sym") != a.sym:
            continue
        sc = r.get("scores")
        if sc:
            series.append(sc)
    if not series:
        print(f"no scored ticks for {a.sym} on {day}")
        return 2

    sampled = series[::a.every][:a.width]
    regimes = sorted({k for sc in series for k in sc})
    print(f"{a.sym} · {day} · {len(series)} ticks, showing every "
          f"{a.every} ({len(sampled)} columns ~ "
          f"{a.every * len(sampled) * 15 // 60} min)\n")

    for reg in regimes:
        vals = [sc.get(reg) or 0.0 for sc in sampled]
        hi = max(vals)
        lo = min(vals)
        # RANGE is the headline: a score that spans most of [0,1] within a
        # session is not measuring a persistent state.
        print(f"  {SHORT.get(reg, reg[:4]):<5} {_spark(vals)}  "
              f"lo {lo:.2f} hi {hi:.2f} range {hi - lo:.2f}")

    # argmax ribbon — what the label would be, tick by tick, with no smoothing
    lead = [max(sc, key=lambda k: sc.get(k) or 0.0) for sc in sampled]
    print(f"\n  argmax {''.join(SHORT.get(x, '?')[0] for x in lead)}")
    runs = collections.Counter()
    cur, n = None, 0
    for x in lead:
        if x == cur:
            n += 1
        else:
            if cur is not None:
                runs[n] += 1
            cur, n = x, 1
    if cur is not None:
        runs[n] += 1
    total_runs = sum(runs.values())
    print(f"  {total_runs} argmax runs in {len(sampled)} sampled columns "
          f"(B=BULL/BEAR·R=RANG/BREA — first letter only)")

    print("\n  READING IT")
    print("  A score swinging most of [0,1] within minutes is the finding: the")
    print("  classifier's lookback is short enough that ordinary tape movement")
    print("  changes its answer completely. Smoothing or a longer lookback is")
    print("  then the fix, and a switching cost downstream is not.")
    print("  Two scores tracking each other and swapping the lead is the A2")
    print("  co-truth case instead — no delta and no smoothing fixes that one.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
