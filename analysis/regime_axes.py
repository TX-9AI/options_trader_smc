#!/usr/bin/env python3
"""
analysis/regime_axes.py — v1.1 — 2026-08-07

THE AXIS DECOMPOSITION. Log-only. Gates nothing.

⚠️⚠️ THE CONJUNCTION `pair_conf` IS DEAD. MEASURED, FAILED, KEPT ONLY SO THE
CROSS-TAB STILL RUNS. DO NOT BUILD ON IT. ⚠️⚠️
AX.2 over 571 matched trades, median by outcome (never-favourable vs the rest):
    direction_conf    nf 0.697  ok 0.885   gap +0.188   SEPARATES
    volatility_conf   nf 0.091  ok 0.156   gap +0.065   SEPARATES
    pair_conf         nf 0.000  ok 0.001   gap +0.001   DOES NOT SEPARATE
It was the WORST of the three, not the best — the opposite of the hypothesis.
WHY, and it is STRUCTURAL rather than tunable: the volatility axis is at or near
ZERO on most ticks (BREAKOUT scores exactly 0 on 63.8%, COMPRESSION on 79.5%,
`is_expanding` true on 9.6% of shadow ticks). `min()` over a SPARSE axis
collapses toward zero and DESTROYS the information the direction axis carried.
A conjunction needs both components populated and on comparable scales; this
pair is neither. Any rescue variant must be justified independently — fitting
one to this failure is exactly the re-litigating this note exists to prevent.

⚠️ WHAT SURVIVED, AND IT IS BIGGER THAN THE CONJUNCTION WOULD HAVE BEEN.
`direction_conf` — the RAW LAYER-1 direction score — separates favourable trades
from never-favourable ones at **+0.188 on n=571**. That is roughly double the
best separation previously found anywhere: `setup_score`'s best cell was 0.80 vs
0.91, and `regime_conviction` is 0.99 vs 1.00, flat.
**The RAW score separates where the INTEGRATED conviction does not**, which
points at Layer-2 integration as a possible destroyer of signal. That is the
finding worth carrying forward, and it needs OUT-OF-SAMPLE confirmation before
anything gates on it.

THE IDEA (operator, 2026-08-07). The regime set is not six independent states —
it is TWO ORTHOGONAL OPPOSITIONS that the argmax fuses and then throws half of
away:

    direction    TRENDING_BULL / TRENDING_BEAR  <->  RANGING
    volatility   BREAKOUT_VOLATILE              <->  COMPRESSION

Both are already scored every tick. Nothing new is measured here; this only
stops discarding one of them.

WHY IT IS NOT MERELY ELEGANT — the number that prompted it. Continuation by
regime over 12 sessions: RANGING 82 trades 51% **+$578.50**, BREAKOUT_VOL 51 49%
+$220, COMPRESSION 39 28% -$454, TRENDING_BULL 252 48% **-$3,221**,
TRENDING_BEAR 85 35% **-$4,952**. A trend-following strategy makes money ONLY
where it is not supposed to work and loses in both states it was built for.
That is what a partnership effect looks like when one label buries it.

THE SPECIFIC, FALSIFIABLE HOPE. `SETUP.nf ~= SETUP.ok` and `RGCV.nf ~= RGCV.ok`
across the whole book: neither existing score separates good trades from bad, so
no threshold on either can. **A CONJUNCTION CAN SEPARATE WHERE ITS COMPONENTS DO
NOT** — `min(a, b)` is low whenever EITHER is low, which is a different function
from anything currently computed. If the 3x3 cross-tab shows no separation
either, the idea dies cheaply and honestly.

WHY `min` AND NOT A MEAN. A mean lets a confident direction paper over an
unknown volatility state. The claim being made is "BOTH axes agree the context is
legible", and the weakest link is exactly what that means. `min` also cannot
manufacture confidence the components lack — it is bounded above by both.

⚠️ MARGIN IS REPORTED SEPARATELY AND IS NOT FOLDED IN. A winner at 0.90 against
a runner-up at 0.89 is not a confident read, but collapsing level and margin into
one number would hide which of the two is missing. The census already proved this
matters: separation looked healthy at p50 0.347 only because uncontested ticks
inflated it.

⚠️ SWEEP_REVERSAL IS ON NEITHER AXIS, deliberately. It is an EVENT OVERLAY
(MECHANICS.md:304) and left the integrated set in RGM.3. Putting it on an axis
would repeat exactly the category error that kept it losing an argmax it could
never win.

⚠️ THIS GATES NOTHING AND MUST NOT, YET. Emit, measure, then decide — the same
order as F7's shadow A/B. Anything that gates on the pair is RGM.2 Stage 3,
post-go-live.

Pure functions, stdlib only, no I/O. Safe to call every tick.
"""

from typing import Dict, Optional, Tuple

BULL = "TRENDING_BULL"
BEAR = "TRENDING_BEAR"
RANGE = "RANGING"
EXPAND = "BREAKOUT_VOLATILE"
COMPRESS = "COMPRESSION"

DIRECTION_AXIS = (BULL, BEAR, RANGE)
VOLATILITY_AXIS = (EXPAND, COMPRESS)


def _axis(scores: Dict[str, Optional[float]], members) -> Tuple[str, float, float]:
    """(winner, level, margin) for one axis.

    An all-zero axis returns NEUTRAL at level 0.0 — NOT the first member, and
    NOT a tie-break. A tie-break head is how SWEEP_REVERSAL came to win the 4.2%
    of ticks where the engine knew nothing; an axis with no evidence should say
    so rather than name a state.
    """
    vals = [(m, float(scores.get(m) or 0.0)) for m in members]
    vals.sort(key=lambda kv: -kv[1])
    top_name, top = vals[0]
    runner = vals[1][1] if len(vals) > 1 else 0.0
    if top <= 0.0:
        return ("NEUTRAL", 0.0, 0.0)
    return (top_name, top, top - runner)


def decompose(scores: Dict[str, Optional[float]]) -> Dict[str, object]:
    """Split an L1 score vector into its two axes plus the conjunction.

    `scores` is the per-regime vector the confluence scorer already produces.
    Extra keys (SWEEP_REVERSAL, anything future) are ignored, not rejected —
    the caller must never have to filter before calling.
    """
    d_name, d_lvl, d_mrg = _axis(scores, DIRECTION_AXIS)
    v_name, v_lvl, v_mrg = _axis(scores, VOLATILITY_AXIS)

    # Direction collapses to three readable outcomes; RANGING is the absence of
    # a directional claim, not a third direction.
    if d_name == BULL:
        direction = "BULL"
    elif d_name == BEAR:
        direction = "BEAR"
    elif d_name == RANGE:
        direction = "RANGE"
    else:
        direction = "NEUTRAL"

    volatility = ("EXPANDING" if v_name == EXPAND else
                  "COMPRESSING" if v_name == COMPRESS else "NEUTRAL")

    return {
        "direction": direction,
        "direction_conf": round(d_lvl, 4),
        "direction_margin": round(d_mrg, 4),
        "volatility": volatility,
        "volatility_conf": round(v_lvl, 4),
        "volatility_margin": round(v_mrg, 4),
        # ⚠️ DEAD — MEASURED AND FAILED (AX.2, 571 trades: gap +0.001 against
        # direction_conf's +0.188). Retained ONLY so `tests/axis_crosstab.py`
        # keeps running and the negative result stays reproducible. Nothing
        # should consume this. See the module docstring for why the failure is
        # structural and not a tuning problem.
        "pair_conf": round(min(d_lvl, v_lvl), 4),
        "pair_conf_status": "DEAD — does not separate; use direction_conf",
        "pair": f"{direction}/{volatility}",
    }


if __name__ == "__main__":
    fails = []

    def check(name, cond, detail=""):
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
              + (f"  ({detail})" if detail else ""))
        if not cond:
            fails.append(name)

    print("(1) a confident trend in a coiling tape — the pullback case")
    r = decompose({BULL: 0.90, BEAR: 0.0, RANGE: 0.10,
                   EXPAND: 0.10, COMPRESS: 0.70})
    check("pair reads BULL/COMPRESSING", r["pair"] == "BULL/COMPRESSING", r["pair"])
    check("conjunction takes the WEAKER axis", abs(r["pair_conf"] - 0.70) < 1e-9,
          f"{r['pair_conf']} (dir 0.90, vol 0.70)")

    print("(2) one axis blind — the conjunction must collapse")
    r = decompose({BULL: 0.95, BEAR: 0.0, RANGE: 0.0, EXPAND: 0.0, COMPRESS: 0.0})
    check("volatility reads NEUTRAL, not a state", r["volatility"] == "NEUTRAL")
    check("pair_conf is 0 despite 0.95 direction", r["pair_conf"] == 0.0,
          "a mean would have reported ~0.48 here")

    print("(3) level and margin are reported separately")
    r = decompose({BULL: 0.90, BEAR: 0.89, RANGE: 0.0,
                   EXPAND: 0.60, COMPRESS: 0.10})
    check("high level", abs(r["direction_conf"] - 0.90) < 1e-9)
    check("but tiny margin is VISIBLE", abs(r["direction_margin"] - 0.01) < 1e-9,
          "collapsing the two would have hidden which is missing")

    print("(4) a dead tick names no state")
    r = decompose({BULL: 0.0, BEAR: 0.0, RANGE: 0.0, EXPAND: 0.0, COMPRESS: 0.0})
    check("NEUTRAL/NEUTRAL, no tie-break head",
          r["pair"] == "NEUTRAL/NEUTRAL", r["pair"])

    print("(5) SWEEP_REVERSAL is ignored, not rejected")
    r = decompose({BULL: 0.8, BEAR: 0.0, RANGE: 0.0, EXPAND: 0.5,
                   COMPRESS: 0.0, "SWEEP_REVERSAL": 0.99})
    check("sweep cannot win an axis", r["pair"] == "BULL/EXPANDING", r["pair"])

    print("(6) missing keys and None are tolerated")
    r = decompose({BULL: None, RANGE: 0.4, COMPRESS: 0.3})
    check("no KeyError, no crash on None", r["pair"] == "RANGE/COMPRESSING",
          r["pair"])

    print("\n" + ("ALL PASS — decomposition is pure and gates nothing"
                  if not fails else f"FAILURES: {fails}"))
