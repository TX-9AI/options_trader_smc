#!/usr/bin/env python3
"""
tests/test_vix_coverage.py — v1.0 — 2026-08-18   (STR.1)

A COLLECTION GAP WEARING THE COSTUME OF A MEASURED NULL.

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python -m pytest tests/test_vix_coverage.py -q

The separation probe reported `VIX at entry` as **58% ties, median 0.000 in
BOTH arms** — which reads as "VIX does not separate outcomes". It is not that.
**ORB, butterfly and sweep set `vix_at_signal`; continuation and iron_condor —
the two HIGHEST-VOLUME strategies — never did**, so `trades.vix_at_entry` fell
to its `REAL DEFAULT 0.0` on most rows and the probe scored a default as a
measurement.

⚠️ THE GENERAL LESSON, AND IT APPLIES TO EVERY REMAINING CANDIDATE: a column
with a numeric DEFAULT cannot distinguish "measured zero" from "never written".
`flat_angle_deg` is 100% ties on ONE unique value — nothing anywhere sets it.
`level_strength` is 94% ties on TWO — only `sweep_reversal` sets it, and sweep
barely fires. **Before any primitive is called dead, check that something
writes it.**

⚠️ CONDOR CARRIES **PLAN-TIME** VIX, AND THE NAME SAYS SO. `_build_leg_signal`
has no `macro` in scope: the plan is built while macro is available, then legs
fire minutes or hours later on a price trigger. Threading `macro` to the builder
would still have delivered a plan-time snapshot — so it rides on the plan
explicitly rather than pretending to be fill-time.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

STRAT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "strategy")


def _src(name):
    return open(os.path.join(STRAT, name), encoding="utf-8").read()


def test_every_trading_strategy_now_sets_vix():
    """⚠️ THE TWO THAT DID NOT ARE THE TWO THAT TRADE MOST. That is why the
    column was 58% empty rather than a little sparse."""
    for f in ("orb_strategy.py", "butterfly_strategy.py",
              "sweep_reversal_strategy.py", "continuation_strategy.py"):
        assert "vix_at_signal" in _src(f), f"{f} does not set vix_at_signal"


def test_condor_carries_plan_time_vix():
    s = _src("iron_condor_strategy.py")
    assert "vix_at_plan" in s
    assert "vix_at_signal     = float(getattr(plan," in s, \
        "the leg signal must read VIX off the plan"


def test_the_plan_captures_vix_where_macro_is_actually_in_scope():
    """A leg builder with no macro cannot invent one; capturing at plan time is
    the honest option, not a convenience."""
    from strategy.iron_condor_strategy import CondorPlan
    assert CondorPlan().vix_at_plan == 0.0
    assert CondorPlan(vix_at_plan=15.1).vix_at_plan == 15.1


def test_continuation_survives_a_missing_macro():
    """`macro` is OPTIONAL on continuation's signature. A missing macro must
    cost telemetry, never a signal."""
    s = _src("continuation_strategy.py")
    assert "if macro is not None else 0.0" in s


def test_flat_angle_is_COMPUTED_AND_DISCARDED_not_absent():
    """⚠️ I GOT THIS WRONG FIRST AND THIS TEST CAUGHT IT.

    I claimed `flat_angle_deg` was "written by nothing" — because my grep
    excluded `getattr` lines. **FIVE strategies set it**, via
    `getattr(regime, 'flat_angle_deg', 0.0)`. The column is 100% tied at ONE
    value because the REGIME OBJECT HAS NO SUCH ATTRIBUTE, so all five reads
    fall to the default.

    The quantity is real and already computed: `regime_confluence.flat_angle_deg()`
    runs at lines ~609 and ~646 and the result lands in the breakdown dict as
    `{"angle": ...}`. **Computed, recorded in the evidence, never carried to the
    consumer** — the same shape as `direction_conf`, which separated on the book
    and was journaled nowhere.

    ⚠️ SO IT IS NOT A DEAD COLUMN. It is an unwired one, and the wiring is
    STR.2. Until then the probe must not read its zeros as measurements."""
    import os
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    setters = 0
    for fn in os.listdir(os.path.join(root, "strategy")):
        if not fn.endswith(".py"):
            continue
        if "signal.flat_angle_deg" in open(
                os.path.join(root, "strategy", fn), encoding="utf-8").read():
            setters += 1
    assert setters >= 4, "strategies stopped reading the angle — check STR.2"

    conf = open(os.path.join(root, "analysis", "regime_confluence.py"),
                encoding="utf-8").read()
    assert "def flat_angle_deg(" in conf, "the producer disappeared"


def test_level_strength_is_written_by_one_barely_firing_strategy():
    """94% ties on TWO unique values. Only `sweep_reversal` sets it, and sweep
    is hard-gated with a 0.4% live win rate — so the column is populated for a
    strategy that essentially does not trade. **Sparse by construction, not a
    measured null**, and Level.1 is the real scope."""
    import os
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    writers = [fn for fn in os.listdir(os.path.join(root, "strategy"))
               if fn.endswith(".py")
               and "signal.level_strength" in open(
                   os.path.join(root, "strategy", fn), encoding="utf-8").read()]
    assert writers == ["sweep_reversal_strategy.py"],         f"level_strength writers changed: {writers} — re-check the probe's read"
