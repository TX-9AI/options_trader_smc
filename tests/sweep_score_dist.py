#!/usr/bin/env python3
"""
tests/sweep_score_dist.py — v1.0 — 2026-08-07

Sets the SWEEP SETUP FLOOR from data instead of from a guess.

WHY THIS EXISTS. The operator's ruling: sweep is not a regime, it is an event —
"the trade should only require a move into a named liquidity pool/level,
accompanied by a rejection or exhaustion." Today the strategy is gated TWICE on
the committed label being SWEEP_REVERSAL (main.py ~1325 and
sweep_reversal_strategy.py:121), and that label wins **0.4% of live ticks** and
scores exactly 0 on **96%**. The ungating replaces "wins the argmax" with
"setup score clears a floor" — and that floor cannot be invented. Too high and
sweep stays as dead as it is now; too low and it fires on noise. This prints the
distribution and the passage counts at candidate floors so the number is chosen
against the corpus.

WHAT IT MEASURES. The `scores.SWEEP_REVERSAL` value already recorded on every
replay tick. That value IS the setup score: `_sweep` computes named-level match,
rejection quality (`rejq_val`), exhaustion (`exh_val`), `age_decay` and
`trend_opp` — the operator's condition set, already assembled. Nothing here
re-derives it; the ungating just stops requiring it to also win an argmax.

⚠️ TREND_OPP IS THE PLTR PROTECTION AND IT IS INSIDE THIS SCORE. `_sweep` passes
`trend_opp` as a soft-necessary term, so a short sweep into a strong uptrend
scores 0 — which is why PLTR 07-27 (shorted a +7.2% up-trending tape, −27.8%)
cannot recur while the gate keys on this score. Gating on anything OTHER than
the score would lose that protection. That constraint is the reason this tool
measures the score rather than, say, a raw liquidity-map event count.

⚠️ WHAT THIS CANNOT TELL YOU. It shows how OFTEN a floor would admit a tick, not
whether those ticks are GOOD trades. A floor that admits 200 ticks/session is
obviously too low; one that admits 2 across 19 sessions is obviously too high.
Between those, the corpus cannot decide — that is a forward-outcome question and
it needs live fires to answer. Pick a floor that admits a plausible handful per
symbol-day, ship it as a stated PRIOR with the env knob, and revise on evidence.

Read-only, stdlib only, streams one file at a time, always exits 0.
USAGE
    python3 tests/sweep_score_dist.py
    python3 tests/sweep_score_dist.py --glob "$HOME/corpus_backup_20260806/regime_replay_*.jsonl"

CHANGELOG
  v1.0 — 2026-08-07 — first issue. Written after the operator ruled that sweep
         must stop gating on regime, and after a fleet log grep confirmed ZERO
         sweep activity for the session (every "Sweep strike:" line came from
         trade_readiness's CONTINUATION staged pick at target delta 0.45 —
         `select_sweep_strike` is a shared selector whose log message names the
         function, not the caller).
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
FLOORS = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50)


def _pct(sv, p):
    if not sv:
        return 0.0
    return sv[min(len(sv) - 1, int(round(p / 100.0 * (len(sv) - 1))))]


def main(argv) -> int:
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

    vals = []
    ticks = 0
    symdays = set()
    per_floor_symday = {f: collections.Counter() for f in FLOORS}

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
            sc = r.get("scores")
            if not sc or "SWEEP_REVERSAL" not in sc:
                continue
            ticks += 1
            key = (date, r.get("sym", "?"))
            symdays.add(key)
            v = sc.get("SWEEP_REVERSAL") or 0.0
            if v > ZERO:
                vals.append(round(v, 4))
                for f in FLOORS:
                    if v >= f:
                        per_floor_symday[f][key] += 1

    vals.sort()
    n, nsd = len(vals), max(1, len(symdays))
    print(f"files: {len(paths)}   ticks with a SWEEP score: {ticks}   "
          f"symbol-days: {len(symdays)}")
    print(f"NONZERO SWEEP ticks: {n}  ({100.0*n/max(1,ticks):.1f}% of ticks) — "
          f"so {100.0-100.0*n/max(1,ticks):.1f}% are annihilated to exactly 0")
    if not n:
        print("\nNo nonzero SWEEP score anywhere in this corpus. That is itself")
        print("the finding: the scorer, not the gate, is what blocks the trade,")
        print("and no floor can rescue it. Look at _sweep's inputs instead.")
        return 0

    print()
    print("=== DISTRIBUTION OF NONZERO SWEEP SETUP SCORES ===")
    print(f"  p25={_pct(vals,25):.3f}  p50={_pct(vals,50):.3f}  "
          f"p75={_pct(vals,75):.3f}  p90={_pct(vals,90):.3f}  "
          f"p99={_pct(vals,99):.3f}  max={vals[-1]:.3f}")
    print()
    print("=== WHAT EACH CANDIDATE FLOOR WOULD ADMIT ===")
    print(f"  {'floor':>6}{'ticks':>10}{'sym-days':>10}{'ticks/symday':>14}"
          f"{'% of symdays':>14}")
    for f in FLOORS:
        c = per_floor_symday[f]
        t = sum(c.values())
        sd = len(c)
        print(f"  {f:>6.2f}{t:>10d}{sd:>10d}{(t/max(1,sd)):>14.1f}"
              f"{100.0*sd/nsd:>13.1f}%")
    print()
    print("  'ticks' counts TICKS above the floor, not trades — consecutive")
    print("  ticks of one sweep collapse into a single entry once the strategy's")
    print("  own cooldown and position checks apply, so the trade count will be")
    print("  far lower than the tick count. Read the SHAPE, not the magnitude.")
    print()
    print("  'sym-days' is how many symbol-sessions would see at least one")
    print("  qualifying tick — that is the number to weigh against the operator's")
    print("  sense of how often a genuine sweep setup appears.")
    print()
    print("  ⚠️ This says how OFTEN a floor admits, never whether those are GOOD")
    print("  trades. The corpus cannot answer that; only forward outcomes can.")
    print("  Ship the chosen floor as a stated PRIOR behind OT_SWEEP_SETUP_FLOOR")
    print("  and revise it on live fires.")
    return 0


if __name__ == "__main__":
    try:
        rc = main(sys.argv)
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        rc = 0
    sys.exit(rc)
