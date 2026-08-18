"""
tests/test_tier1_priors.py — v1.0 — 2026-08-07

Pins the two Tier-1 tuning priors from the 692-trade / 12-session sample.

BOTH ARE PRIORS, NOT FITS, and the distinction is the point. Neither number was
read off an in-sample argmax — each is carried by a MECHANISM that was already
known, with the data agreeing rather than deciding. The reports themselves
refuse to name a best value for exactly this reason.

SWP.2 — sweep shorts clear a higher floor than longs
    long   27 trades · 81% WR · +$2,844 · 4% never-favourable · drift building
           +0.001 -> +0.081 -> +0.314, 52/56/67% positive
    short   6 trades · 33% WR · −$1,403.50 · 33% never-favourable · drift
           −0.148 -> −0.215 -> −0.290, 33% positive
    n=6 is thin. What earns the change is the 2026-07-27 PLTR incident: a short
    reversal into a +7.2% up-trending tape, which is why `trend_opp` exists.

CNT.3 — the runaway handoff does not fire under COMPRESSION
    COMPRESSION/Continuation: 39 trades, 28% WR, −$454, and COMPRESSION is the
    worst never-favourable cell in the book at 80% (LIFT 1.98).
    Continuation cannot enter on a compression LABEL, so all 39 are handoffs,
    which ignore the label by design. A runaway asserts EXPANSION while the
    label asserts COILING.
"""

import ast
import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _exec_only(*parts) -> str:
    """Executable source only — docstring AND comments stripped.

    Both changes are DOCUMENTED in prose that necessarily quotes what they
    replace, so an absence check over raw source fires on a correct file. That
    has now bitten three times in one day (main v5.6's changelog, the
    excursion_report substring guard, and exit_engine's 2b comment quoting the
    P&L gate it deliberately lacks)."""
    src = open(os.path.join(_ROOT, *parts)).read()
    mod = ast.parse(src)
    if ast.get_docstring(mod, clean=False) is not None and mod.body:
        src = "\n".join(src.splitlines()[mod.body[0].end_lineno:])
    return "\n".join(ln for ln in src.splitlines()
                     if not ln.strip().startswith("#"))


def test_short_floor_exists_and_is_above_the_long_floor():
    import config
    importlib.reload(config)
    assert config.SWEEP_SETUP_FLOOR_SHORT > config.SWEEP_SETUP_FLOOR, (
        "the short floor is no longer stricter than the long floor — SWP.2 is "
        "inert")
    assert abs(config.SWEEP_SETUP_FLOOR_SHORT - 0.20) < 1e-9, (
        "the short floor moved off its stated PRIOR; that should be deliberate "
        "and recorded, not incidental")


def test_the_short_floor_is_applied_to_shorts_only():
    src = _exec_only("strategy", "sweep_reversal_strategy.py")
    i = src.index('sweep.kind == "high_sweep"')
    j = src.index("_short_reversal(", i)
    assert "SWEEP_SETUP_FLOOR_SHORT" in src[i:j], (
        "the short floor is not checked on the high_sweep branch")
    k = src.index('sweep.kind == "low_sweep"')
    assert "SWEEP_SETUP_FLOOR_SHORT" not in src[k:i], (
        "the short floor leaked onto the LONG branch — longs are the profitable "
        "side and must stay at 0.05")


def test_short_floor_can_be_restored_to_parity_by_env():
    """The kill switch is setting it equal, not removing the check — so an
    operator can undo the prior without a deploy."""
    os.environ["OT_SWEEP_SETUP_FLOOR_SHORT"] = "0.05"
    import config
    importlib.reload(config)
    assert config.SWEEP_SETUP_FLOOR_SHORT == config.SWEEP_SETUP_FLOOR
    del os.environ["OT_SWEEP_SETUP_FLOOR_SHORT"]
    importlib.reload(config)


def test_handoff_is_blocked_under_compression():
    src = _exec_only("strategy", "continuation_strategy.py")
    assert "CONT_HANDOFF_BLOCK_COMPRESSION" in src
    assert "Regime.COMPRESSION" in src, (
        "CNT.3 no longer names the regime it blocks")


def test_cnt3_blocks_only_the_handoff_branch():
    """The TRENDING and BREAKOUT branches must be untouched — CNT.3 removes one
    licence the handoff has to ignore the label, nothing else."""
    src = _exec_only("strategy", "continuation_strategy.py")
    assert "if rgm == Regime.TRENDING_BULL:" in src
    assert "elif rgm == Regime.TRENDING_BEAR:" in src
    i = src.index("is_handoff and handoff_direction")
    assert "CONT_HANDOFF_BLOCK_COMPRESSION" in src[i:i + 300]


def test_cnt3_kill_switch():
    os.environ["OT_CONT_HANDOFF_IN_COMPRESSION"] = "1"
    import config
    importlib.reload(config)
    assert config.CONT_HANDOFF_BLOCK_COMPRESSION is False
    del os.environ["OT_CONT_HANDOFF_IN_COMPRESSION"]
    importlib.reload(config)
    assert config.CONT_HANDOFF_BLOCK_COMPRESSION is True
