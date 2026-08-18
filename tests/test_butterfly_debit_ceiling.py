#!/usr/bin/env python3
"""
tests/test_butterfly_debit_ceiling.py — v1.0 — 2026-08-15   (BFLY.3)

THE DEBIT CEILING IS FLAT AT 0.50, AND 0.50 IS NOT A FITTED NUMBER.

A butterfly's max profit is `wing - debit`. At `debit/wing == 0.50` you risk
exactly what you can win, so **0.50 is the structure's own break-even** — it
needs no holdout and cannot be overfit. Above it the payoff is upside-down.

⚠️ WHAT THIS REPLACED, and why BOTH candidate designs were wrong. The ceiling
used to scale with `regime.conviction` (0.33 at conv<=0.30 rising to 0.50 at
conv>=0.55). Measured fleet-wide across 29 boxes:

  · **THE conv->ratio SLOPE IS POSITIVE ON 5 OF 7 SAMPLED SYMBOLS**
    (AVGO +0.103, GS +2.550, NVDA +0.109, PLTR +0.038, QQQ +0.211; only
    SMH -0.048 and TLT -0.031 negative). Higher conviction travels with MORE
    EXPENSIVE tents. So the original design paid more exactly where the trade
    was worse — and INVERTING it, the other candidate, would have been worse
    still.
  · **AND IT COST REAL TRADES.** SMH: **46 setups at mean ratio 0.379**, and
    only **3 fired**, because conviction averaged 0.033 so the ceiling sat on
    its 0.33 floor. 43 cheap tents refused by a score that does not measure the
    thesis.

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python -m pytest tests/test_butterfly_debit_ceiling.py -q
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config                                                            # noqa: E402

SRC = open(os.path.join(os.path.dirname(__file__), "..", "strategy",
                        "butterfly_strategy.py"), encoding="utf-8").read()


def test_the_ceiling_is_the_structures_break_even():
    """0.50 exactly. Not 0.49, not 0.55 — at 0.50 risk equals reward, which is
    what makes it defensible without a holdout."""
    assert abs(config.BUTTERFLY_DEBIT_CEILING - 0.50) < 1e-9


def test_break_even_arithmetic_holds():
    """The claim the ceiling rests on, computed rather than asserted."""
    wing = 10.0
    for ratio, expect_positive in ((0.33, True), (0.49, True),
                                   (0.50, False), (0.54, False), (0.80, False)):
        debit = ratio * wing
        max_profit = wing - debit
        assert (max_profit > debit) is expect_positive, (
            f"ratio {ratio}: risk {debit} vs reward {max_profit}")


def test_conviction_no_longer_gates():
    """`_conv` must still be LOGGED — the relationship stays measurable and the
    decision revisitable — but it must not appear in the gate expression."""
    i = SRC.index("_gate = ")
    assert "BUTTERFLY_DEBIT_CEILING" in SRC[i:i + 120]
    seg = SRC[i:i + 400]
    assert "_t" not in seg.replace("_gate", "").replace("_t}", "")
    assert "conv=" in seg, "conviction must still be journaled"


def test_the_measured_population_splits_the_way_it_should():
    """Regression on the fleet-wide 2026-08-15 read. The cheap tents pass, the
    overpriced ones are STILL REFUSED — the rejects doing the heavy lifting is
    the whole reason a flat ceiling is safe."""
    ceiling = config.BUTTERFLY_DEBIT_CEILING
    passes = {"SMH": 0.379, "AVGO": 0.428, "COST": 0.270, "MSFT": 0.310,
              "LLY": 0.330, "GS": 0.441}
    refused = {"QQQ": 0.535, "NVDA": 0.718, "PLTR": 0.799,
               "NFLX": 0.941, "TLT": 1.029}
    for sym, r in passes.items():
        assert r <= ceiling, f"{sym} at {r} should clear {ceiling}"
    for sym, r in refused.items():
        assert r > ceiling, f"{sym} at {r} must stay refused"


def test_the_old_constants_survive_for_a_one_line_revert():
    """Kept in config, unread by this path. A revert must not need a rebuild."""
    for name in ("BUTTERFLY_DISC_CONV_LO", "BUTTERFLY_DISC_CONV_HI",
                 "BUTTERFLY_MAX_DEBIT_PCT_WIDTH_HICONV"):
        assert hasattr(config, name)


def test_deliberate_failure_the_old_gate_would_have_refused_SMH():
    """Prove the change is load-bearing: SMH's conviction of 0.033 put the old
    ceiling on its floor, refusing a tent priced at 0.379."""
    lo, hi = config.BUTTERFLY_DISC_CONV_LO, config.BUTTERFLY_DISC_CONV_HI
    floor, ceil = (config.BUTTERFLY_MAX_DEBIT_PCT_WIDTH,
                   config.BUTTERFLY_MAX_DEBIT_PCT_WIDTH_HICONV)
    conv, ratio = 0.033, 0.379
    t = min(max((conv - lo) / max(hi - lo, 1e-9), 0.0), 1.0)
    old_gate = floor + (ceil - floor) * t
    assert ratio > old_gate, "the old gate would have PASSED it — check the math"
    assert ratio <= config.BUTTERFLY_DEBIT_CEILING, "the new gate must pass it"
