"""
tests/test_insurance_stop.py — v1.0 — 2026-08-07

Pins CNT.2: the insurance gate that covers BOS's blind window on continuation.

WHY THE HOLE EXISTS. `BOSTracker.protected_level` starts None and is set only
when the trade makes a new CLOSING HIGH past entry. So BOS — continuation's
thesis invalidator, deliberately ungated on P&L — is structurally BLIND on a
trade that goes wrong from the first tick. That is exactly the population that
runs to the floor: 45 trades, 11 sessions, realized −29% with MFE of +1%.

WHAT MUST NOT BREAK. The gate arms ONLY while `protected_level is None`. The
instant BOS has a level to defend, BOS owns the trade and insurance disarms
permanently — no overlap, no double jeopardy. A test below fails if that
condition is ever loosened, because a gate that stays armed after BOS wakes up
would re-create the very winner-cutting the floor sweep ruled out.
"""

import ast
import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _code(*parts) -> str:
    """Source minus the module docstring — an absence check over raw source
    matches the CHANGELOG, which necessarily quotes what it describes."""
    src = open(os.path.join(_ROOT, *parts)).read()
    mod = ast.parse(src)
    if ast.get_docstring(mod, clean=False) is not None and mod.body:
        return "\n".join(src.splitlines()[mod.body[0].end_lineno:])
    return src


def _exec_only(*parts) -> str:
    """`_code` with COMMENT LINES stripped as well.

    Docstring-stripping is not enough. This engine documents the gates it
    deliberately does NOT have — 2b's comment quotes ``pnl_pct > 0`` precisely
    to explain that BOS is ungated, unlike Sweep's copy. An absence check over
    commented source therefore fires on a CORRECT file. Third time in one day a
    canary matched prose instead of code (main v5.6's changelog, the
    excursion_report substring guard, and this): when a test asserts something
    is ABSENT, it must read executable lines only.
    """
    return "\n".join(ln for ln in _code(*parts).splitlines()
                      if not ln.strip().startswith("#"))


def test_gate_is_armed_only_while_bos_has_no_protected_level():
    """THE LOAD-BEARING CONDITION. Without it the gate would keep firing after
    BOS wakes up, and a static level that outlives its window is the exact
    objection the July decision raised against using underlying_stop as an
    exit."""
    src = _code("execution", "exit_engine.py")
    assert "_bos.protected_level is None" in src, (
        "insurance no longer disarms when BOS establishes a level")


def test_bos_tracker_is_built_outside_the_df_1m_guard():
    """`_bos` must exist even on a tick with no 1m frame, or gate 2c references
    an unbound name — the same NameError class as defect W, which hard-blocked
    a whole strategy silently."""
    src = _code("execution", "exit_engine.py")
    i = src.index("_bos = self._get_bos_tracker(trade_id, str(record.get(\"direction\"")
    preceding = src[max(0, i - 400):i]
    assert "if df_1m is not None:" not in preceding.split("# v4.14")[-1], (
        "_bos construction moved back inside the df_1m guard")


def test_exit_is_tagged_separately_from_floor_and_bos():
    """The point of this gate is to collect data on it. Tagged `max_loss_floor`
    or `bos_exit` it would pool with 45 and 111 trades of history."""
    src = _code("execution", "exit_engine.py")
    assert "insurance_stop" in src


def test_direction_is_respected():
    """A long exits BELOW the level, a short ABOVE it. Getting this backwards
    would fire the gate on every healthy trade and be invisible in the tag."""
    src = _code("execution", "exit_engine.py")
    assert '(_close < _ins) if _dirn == "long" else (_close > _ins)' in src


def test_it_uses_the_same_closed_candle_as_bos():
    """BOS reads iloc[-2], the last FULLY closed candle. If insurance read the
    forming candle the two gates could disagree about what price did."""
    src = _code("execution", "exit_engine.py")
    i = src.index("insurance_stop")
    assert 'iloc[-2]' in src[max(0, i - 900):i]


def test_kill_switch():
    os.environ["OT_CONT_INSURANCE"] = "0"
    import config
    importlib.reload(config)
    assert config.CONT_INSURANCE_STOP is False
    del os.environ["OT_CONT_INSURANCE"]
    importlib.reload(config)
    assert config.CONT_INSURANCE_STOP is True


def test_bos_itself_stays_ungated_on_pnl():
    """CNT.2 must not disturb 2b. BOS being ungated is what lets it fire on a
    losing continuation at all; re-gating it would restore the hole this gate
    was built beside, not instead of."""
    src = _code("execution", "exit_engine.py")
    i = src.index("2b. BREAK OF STRUCTURE")
    j = src.index("2c. INSURANCE")
    window = "\n".join(ln for ln in src[i:j].splitlines()
                        if not ln.strip().startswith("#"))
    assert "pnl_pct > 0" not in window, "BOS on continuation got a P&L gate"
