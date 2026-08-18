"""
tests/test_regime_axes.py — v1.0 — 2026-08-07

Pins the conjunction's defining properties. It gates nothing today, so these
tests protect the SEMANTICS before anything depends on them — which is the
right order, and the opposite of how SWEEP_REVERSAL got into the regime enum.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.regime_axes import decompose        # noqa: E402


def test_conjunction_is_the_weaker_axis_never_an_average():
    """THE DEFINING PROPERTY. A mean would let a confident direction paper over
    an unknown volatility state — which is precisely the failure the pair is
    meant to expose."""
    r = decompose({"TRENDING_BULL": 0.95, "BREAKOUT_VOLATILE": 0.0,
                   "COMPRESSION": 0.0})
    assert r["pair_conf"] == 0.0, "a blind axis must collapse the conjunction"
    r = decompose({"TRENDING_BULL": 0.90, "COMPRESSION": 0.70})
    assert abs(r["pair_conf"] - 0.70) < 1e-9


def test_conjunction_can_never_exceed_either_component():
    for d, v in ((0.9, 0.2), (0.2, 0.9), (0.5, 0.5), (0.0, 1.0)):
        r = decompose({"TRENDING_BULL": d, "BREAKOUT_VOLATILE": v})
        assert r["pair_conf"] <= r["direction_conf"] + 1e-9
        assert r["pair_conf"] <= r["volatility_conf"] + 1e-9


def test_an_empty_axis_names_no_state():
    """No tie-break head, ever. A tie-break head is how SWEEP_REVERSAL won the
    4.2% of ticks where the engine knew nothing."""
    r = decompose({})
    assert r["pair"] == "NEUTRAL/NEUTRAL"


def test_margin_is_separate_from_level():
    """0.90 against 0.89 is a high level and a terrible margin. Folding them
    together would hide which one is missing — the same error that made the
    census's p50 separation of 0.347 look healthy."""
    r = decompose({"TRENDING_BULL": 0.90, "TRENDING_BEAR": 0.89})
    assert abs(r["direction_conf"] - 0.90) < 1e-9
    assert abs(r["direction_margin"] - 0.01) < 1e-9


def test_sweep_is_on_neither_axis():
    """It is an EVENT OVERLAY and left the integrated set in RGM.3. Putting it
    on an axis repeats the category error, and it would win on a 0.99 score."""
    r = decompose({"TRENDING_BULL": 0.8, "BREAKOUT_VOLATILE": 0.5,
                   "SWEEP_REVERSAL": 0.99})
    assert r["pair"] == "BULL/EXPANDING"


def test_the_dead_conjunction_is_labelled_dead():
    """AX.2 measured `pair_conf` at gap +0.001 against `direction_conf`'s
    +0.188 — it was the WORST of the three, and the failure is structural (the
    volatility axis is near-zero on most ticks, so `min()` collapses). It is
    retained only so the cross-tab keeps running. Without this marker in the
    payload, a future caller reads a plausible-looking float and builds on a
    measured dead end."""
    r = decompose({"TRENDING_BULL": 0.9, "COMPRESSION": 0.7})
    assert r["pair_conf_status"].startswith("DEAD")
    assert "direction_conf" in r["pair_conf_status"]


def test_it_gates_nothing():
    """The module must stay pure. The moment it imports config or an engine it
    has stopped being a measurement and started being a decision."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "analysis",
                            "regime_axes.py")).read()
    for forbidden in ("import config", "from config", "os.environ"):
        assert forbidden not in src, f"regime_axes took a dependency: {forbidden}"
