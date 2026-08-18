"""
tests/test_continuation_breakout.py — v1.0 — 2026-08-07

Pins CNT.1: standalone continuation may fire under BREAKOUT_VOLATILE, taking
direction from the trend engine's vote instead of from the label.

WHY THE TRADE WAS BARRED, which is the thing these tests protect: the bar was
STRUCTURAL, not a quality judgement. `continuation_strategy` derives direction
from the label — TRENDING_BULL -> long, TRENDING_BEAR -> short — and
BREAKOUT_VOLATILE asserts volatility EXPANSION while saying nothing about which
way, so there was no branch that could assign one. The runaway handoff already
solves the same problem by taking direction from the ORB.

THE RISK THIS OPENS, and why the ADX bar exists: under a non-trending label
`_label_trending` is False, so continuation's `CONTINUATION_CONV_FLOOR` check is
skipped entirely — the same hole the handoff path has. Falling back to
`regime.conviction` would be worse than nothing, because under BREAKOUT that is
BREAKOUT's conviction, not the trend's. Direction comes from the trend engine,
so the quality bar must too.
"""

import ast
import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _code(*parts) -> str:
    """Source with the module docstring stripped — an absence check over raw
    source matches the CHANGELOG, which necessarily quotes the line it
    describes. A canary that fires on documentation trains you to loosen it."""
    src = open(os.path.join(_ROOT, *parts)).read()
    mod = ast.parse(src)
    if ast.get_docstring(mod, clean=False) is not None and mod.body:
        return "\n".join(src.splitlines()[mod.body[0].end_lineno:])
    return src


def test_dispatch_admits_breakout():
    src = _code("main.py")
    assert "Regime.BREAKOUT_VOLATILE)):" in src or \
           "Regime.BREAKOUT_VOLATILE))" in src, "breakout not in the dispatch tuple"


def test_direction_comes_from_the_trend_vote_not_the_label():
    src = _code("strategy", "continuation_strategy.py")
    assert 'getattr(trend, "overall_direction", "NEUTRAL") in ("BULLISH", "BEARISH")' in src
    assert "CONT_BREAKOUT_MIN_ADX" in src, "no ADX bar on the breakout path"


def test_neutral_tape_cannot_produce_a_breakout_entry():
    """The whole trade rests on the trend engine supplying the direction the
    label lacks. If the vote is NEUTRAL there is no direction to take and the
    branch must not fire — widening the dispatch tuple alone must not open it."""
    src = _code("strategy", "continuation_strategy.py")
    i = src.index("CONT_BREAKOUT_DIRECTION\n")
    branch = src[i:i + 700]
    assert '("BULLISH", "BEARISH")' in branch, (
        "NEUTRAL is not excluded — a directionless tape would get a direction "
        "assigned by fallthrough")


def test_breakout_entries_are_tagged_separately():
    """The point of turning this on is to COLLECT DATA on it. If the entries
    carry `_standalone`, they pool with a path that has 141 trades of history
    and the new data is unreadable."""
    src = _code("strategy", "continuation_strategy.py")
    assert '"_breakout" if is_breakout_dir' in src


def test_kill_switch_and_adx_default():
    os.environ["OT_CONT_BREAKOUT_DIRECTION"] = "0"
    import config
    importlib.reload(config)
    assert config.CONT_BREAKOUT_DIRECTION is False
    del os.environ["OT_CONT_BREAKOUT_DIRECTION"]
    importlib.reload(config)
    assert config.CONT_BREAKOUT_DIRECTION is True
    assert abs(config.CONT_BREAKOUT_MIN_ADX - config.ADX_TREND_THRESHOLD) < 1e-9, (
        "the ADX bar drifted off the system-wide trend threshold; that default "
        "is a stated PRIOR, so moving it should be deliberate and recorded")


def test_trending_paths_are_untouched():
    """CNT.1 must ADD a branch, never alter the two that were already there."""
    src = _code("strategy", "continuation_strategy.py")
    assert 'if rgm == Regime.TRENDING_BULL:' in src
    assert 'elif rgm == Regime.TRENDING_BEAR:' in src
    # CNT.3 (2026-08-07) legitimately rewrote this branch to add the
    # COMPRESSION block, so the assertion moved from the branch's EXACT TEXT to
    # its INTENT: the handoff path must still EXIST. Pinning exact text made
    # this canary fire on a correct change — a canary that fires on intended
    # edits gets loosened under pressure, which is how it stops protecting
    # anything. Assert what must remain true, not what the line looked like.
    assert 'is_handoff and handoff_direction in ("long", "short")' in src
