"""
tests/test_sweep_ungated.py — v1.0 — 2026-08-07

Pins SWP.1: sweep gates on the L1 `_sweep` SETUP SCORE, not on the committed
regime label. The failure these guard against is silent in both directions —
a re-introduced label gate turns the trade off with no error, and a lost
`trend_opp` guard turns the PLTR incident back on with no error.

Context: SWEEP_REVERSAL wins 0.4% of live ticks and is exactly 0 on 96% across
19 sessions, so the old gate held the trade shut. The operator's ruling: sweep
is an EVENT, not a market state — "the trade should only require a move into a
named liquidity pool/level, accompanied by a rejection or exhaustion."
"""

import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _code(*parts) -> str:
    """Source with the MODULE DOCSTRING STRIPPED.

    Learned the hard way while writing these: an absence check over raw source
    matches the CHANGELOG, which necessarily quotes the very line being removed.
    The first version of `test_dispatch_gates_on_the_setup_score_not_the_label`
    failed against a correct main.py because v5.6's header describes the gate it
    deleted. A canary that fires on documentation is worse than no canary — it
    trains you to loosen it. Scan executable source only.
    """
    src = open(os.path.join(_ROOT, *parts)).read()
    mod = ast.parse(src)
    doc = ast.get_docstring(mod, clean=False)
    if doc is not None and mod.body:
        return "\n".join(src.splitlines()[mod.body[0].end_lineno:])
    return src


def test_the_label_gate_is_gone_from_the_strategy():
    """The strategy must not re-check the regime label. It was checked in TWO
    places; removing only the dispatch one would leave the trade just as shut."""
    src = _code("strategy", "sweep_reversal_strategy.py")
    assert "primary_regime != Regime.SWEEP_REVERSAL" not in src, (
        "the in-strategy label gate is back — dispatch ungating is then void")


def test_dispatch_gates_on_the_setup_score_not_the_label():
    src = _code("main.py")
    assert "regime.primary_regime == Regime.SWEEP_REVERSAL" not in src, (
        "the dispatch label gate is back")
    assert "_sweep_setup >= SWEEP_SETUP_FLOOR" in src


def test_floor_knob_exists_and_is_env_tunable():
    import importlib
    os.environ["OT_SWEEP_SETUP_FLOOR"] = "0.37"
    import config
    importlib.reload(config)
    assert abs(config.SWEEP_SETUP_FLOOR - 0.37) < 1e-9
    del os.environ["OT_SWEEP_SETUP_FLOOR"]
    importlib.reload(config)
    assert abs(config.SWEEP_SETUP_FLOOR - 0.05) < 1e-9, "default prior moved"


def test_conviction_comes_from_the_setup_not_the_ambient_regime():
    """After ungating, `regime.conviction` is whatever the AMBIENT regime holds
    (e.g. TRENDING_BULL at 0.80). Feeding that to `_sweep_target_delta` would
    pick sweep strikes off an unrelated regime's confidence — wrong, and
    silent."""
    src = _code("strategy", "sweep_reversal_strategy.py")
    assert "_sweep_target_delta(regime.conviction)" not in src
    assert "_sweep_target_delta(conv)" in src
    assert "signal.conviction = regime.conviction" not in src


def test_trend_opp_still_annihilates_a_reversal_into_an_accelerating_trend():
    """THE PLTR GUARD. It lives as a soft-necessary inside `_sweep`, never in
    the removed gate — so gating on the score must preserve it. A short sweep
    into a strong ACCELERATING bull trend must still score 0, which means the
    floor can never admit it however low the floor is set."""
    src = _code("analysis", "regime_confluence.py")
    assert "soft_necessary=[trend_opp, age_decay]" in src, (
        "trend_opp is no longer soft-necessary — a fully opposed sweep can now "
        "score above zero and the PLTR failure mode is reachable again")
    # and the exhaustion asymmetry the operator asked for: conviction should
    # RISE as the opposing move decelerates, not merely be suppressed by trend.
    assert '"DECELERATING": 0.25' in src, "opp_mom no longer favours exhaustion"
    assert '"DECELERATING": 1.0' in src, "exh_val no longer rewards exhaustion"


def test_priority_order_still_puts_sweep_behind_orb_and_continuation():
    """A permissive floor must not let sweep pre-empt other setups. It cannot,
    because dispatch only reaches it when nothing higher produced a signal."""
    src = _code("main.py")
    i = src.index("_sweep_setup >= SWEEP_SETUP_FLOOR")
    assert "signal is None and" in src[i - 60:i], (
        "sweep no longer requires an empty signal slot — it can now pre-empt "
        "ORB or continuation")
