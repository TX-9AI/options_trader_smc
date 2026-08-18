"""
tests/test_velocity_stall.py — v1.0 — 2026-08-12

Pins VEL.1 — the velocity-stall exit, the THIRD question in the ladder.

WHY IT EXISTS. `orb_structure_stop` asks "did the thesis break?".
`_theta_bleed` asks "is my GAIN about to evaporate?" — its gate 1 is a gain
floor, so a LOSING position is invisible to it. **A losing position that has
stopped moving answers no to both**, and the -40% percentage floor eventually
catching it is the absence of a mechanism rather than one. On 2026-08-12 that
cost a QQQ trade 50 minutes and -42.2% while the underlying sat BELOW the short
entry the whole time — directionally right, and bleeding anyway.

THE FAILURES GUARDED, all of which are silent:
1. **ORDER SWAPPED.** theta_bleed MUST evaluate first. A trade up 10-20% and
   stalled should exit GREEN through theta_bleed, not fall to a velocity check
   that lets it drift back toward flat.
2. **GRACE REMOVED OR SHORTENED.** Winners p10 at 5 minutes is **-21.1** — the
   bottom decile of eventual WINNERS was moving AWAY. Evaluating before 10
   minutes kills those trades. The grace is derived, not chosen.
3. **CONFIRM SET TO 1.** QQQ crossed back ABOVE breakeven at minutes 41-61
   before dying at 70. A single-tick rule oscillates.
4. **ENFORCE ON FOR UNMEASURED STRATEGIES.** The floors are ORB-derived;
   applying them to continuation or sweep without measurement would be an
   untested extrapolation wearing a measured number.
5. **THE BREACH COUNTER MISSING FROM __init__.** Then the check AttributeErrors
   on first call, the except swallows it, and the whole mechanism is a
   permanent silent no-op that still looks shipped.

Deliberate-failure check performed when written: deleting `self._vel_breaches`
from __init__ turns test_breach_counter_exists red; setting CONFIRM to 1 turns
test_confirm_requires_multiple_breaches red.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config                                                  # noqa: E402
from execution.exit_engine import ExitEngine                   # noqa: E402


def test_breach_counter_exists():
    """Without this the check is a silent permanent no-op."""
    e = ExitEngine()
    assert hasattr(e, "_vel_breaches"), \
        "the counter must be initialised in __init__ — otherwise the first " \
        "call AttributeErrors, the except swallows it, and the mechanism " \
        "never runs while still appearing shipped"
    assert e._vel_breaches == {}


def test_grace_is_at_least_ten_minutes():
    assert config.VELOCITY_GRACE_MIN >= 10, \
        "winners p10 at 5 minutes is -21.1: the bottom decile of eventual " \
        "WINNERS was moving AWAY. Evaluating earlier kills them."


def test_confirm_requires_multiple_breaches():
    assert config.VELOCITY_CONFIRM_TICKS >= 2, \
        "QQQ crossed back above breakeven at minutes 41-61 before dying at " \
        "70 — a single-tick rule oscillates"


def test_ships_observe_only():
    assert config.VELOCITY_STALL_ENFORCE is False, \
        "floors rest on n=22 at the 20-minute mark and are ORB-derived; " \
        "collect a session of observe-only logs before cutting live positions"
    assert config.VELOCITY_STALL_ENABLED is True, \
        "shipping it disabled collects nothing and makes the deploy a no-op"


def test_floors_are_the_measured_percentiles():
    f = config.VELOCITY_FLOOR_BY_MIN
    assert set(f) >= {10, 15, 20}
    assert f[10] < f[15] < f[20], \
        "the floor must RISE with hold time — winners p10 measured 3.9 / 18.0 " \
        "/ 29.8 at 10/15/20 min. A flat or falling floor is not the curve"
    assert min(f) >= 10, "no floor below the grace period can ever be reached"


def test_only_measured_strategies_can_be_cut():
    assert "ORBStrategy" in config.VELOCITY_MEASURED_STRATEGIES
    for s in ("ContinuationStrategy", "SweepReversalStrategy"):
        assert s not in config.VELOCITY_MEASURED_STRATEGIES, \
            f"{s} has no measured floor; the ORB-derived numbers would be an " \
            f"untested extrapolation wearing a measured number"


def test_theta_bleed_is_evaluated_before_velocity():
    """ORDER. A stalled winner must exit GREEN via theta_bleed."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "execution", "exit_engine.py")).read()
    i_theta = src.index("if self._theta_bleed(record, current_premium, pnl_pct):")
    i_vel = src.index("_vel = self._velocity_stall(")
    assert i_theta < i_vel, \
        "theta_bleed must run FIRST — otherwise a trade up 10-20% and stalled " \
        "falls to the velocity check and drifts back toward flat before firing"


def test_the_rejected_entry_filter_stays_rejected():
    """The target-based form was measured and inverted. Do not reintroduce."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "execution", "exit_engine.py")).read()
    assert "MEASURED AND\n        REJECTED" in src or "REJECTED" in src, \
        "the docstring must record that feasibility-ratio-at-entry ran HIGHER " \
        "for losers than winners (p50 5.05 vs 3.87, n=145) — without that " \
        "note someone will rebuild it"
