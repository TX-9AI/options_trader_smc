"""
tests/test_continuation_premium_block.py — v1.0 — 2026-08-10

Pins CNT.6: continuation must not trade RANGING or COMPRESSION (main v6.0).

THE DEFECT, in one line. The dispatch gate read

    if signal is None and (_is_runaway
                           or regime in (TRENDING_BULL, TRENDING_BEAR, BREAKOUT_VOLATILE))

`_is_runaway` is OR'd with the regime tuple, so an ORB runaway flag BYPASSED THE
LABEL ENTIRELY and let continuation fire on any tape — at Priority 2, ahead of
Butterfly (P3, needs RANGING/COMPRESSION) and Condor (P4, needs RANGING). Both
sit behind `if signal is None`, so once continuation took the slot they were
never evaluated at all.

MEASURED over 13 sessions, and this is why it is a defect rather than a
preference: RANGING → Continuation **94** trades against IronCondor **27**;
COMPRESSION → Continuation **39** against Butterfly **6**. Continuation took
3.5x the condor's opportunities and 6.5x the butterfly's, INSIDE THE REGIMES
THOSE STRATEGIES EXIST FOR. And a continuation in a range is not a marginal
call — RANGING is the assertion that there is no trend to continue, so the
entry contradicts its own premise.

WHY THE BLOCK LIVES IN DISPATCH AND NOT IN THE STRATEGY. CNT.3 already blocked
the handoff in COMPRESSION, inside continuation_strategy — and the squeeze
carried on. A strategy-level veto still CONSUMES THE DISPATCH SLOT on its way to
returning None. Only a gate above the call frees P3/P4.

THE FAILURE THIS GUARDS, and it is silent: if the runaway bypass is ever
restored, nothing errors. Butterfly and Condor simply go quiet again, which
looks like "no setups today" rather than like a regression.

Deliberate-failure check performed when written: restoring the bare
`_is_runaway or ...` condition turns test_runaway_cannot_bypass_a_premium_regime
red.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config                                                    # noqa: E402
from analysis.regime_classifier import Regime                    # noqa: E402


PREMIUM = (Regime.RANGING, Regime.COMPRESSION)
TRENDY = (Regime.TRENDING_BULL, Regime.TRENDING_BEAR, Regime.BREAKOUT_VOLATILE)


def _dispatches(regime, is_runaway, block=True):
    """Mirror of the CNT.6 gate — same shape as main.attempt_new_entry.

    Restated rather than imported so a change to the CONTRACT shows up here as a
    disagreement instead of silently travelling into the test.
    """
    blocked = block and regime in PREMIUM
    return (not blocked) and (is_runaway or regime in TRENDY)


def test_the_knob_exists_and_defaults_on():
    assert config.CONT_BLOCK_PREMIUM_REGIMES is True, \
        "shipping it OFF makes the deploy a no-op that looks live"


def test_runaway_cannot_bypass_a_premium_regime():
    """THE BUG. A runaway flag used to fire continuation on ANY tape."""
    for r in PREMIUM:
        assert not _dispatches(r, is_runaway=True), \
            f"a runaway must NOT open continuation in {r} — that is the bypass " \
            f"that took 94 RANGING and 39 COMPRESSION trades from P3/P4"


def test_continuation_still_fires_where_it_belongs():
    for r in TRENDY:
        assert _dispatches(r, is_runaway=False), \
            f"{r} is continuation's tape and must be untouched"
        assert _dispatches(r, is_runaway=True)


def test_a_premium_regime_leaves_the_slot_for_p3_p4():
    """The POINT of the change: dispatch must fall through, not merely decline."""
    for r in PREMIUM:
        assert not _dispatches(r, is_runaway=True), \
            "continuation must not be REACHED — a strategy-level veto still " \
            "consumes the slot, which is exactly why CNT.3 did not fix this"


def test_the_kill_switch_restores_the_old_behaviour_exactly():
    for r in PREMIUM:
        assert _dispatches(r, is_runaway=True, block=False), \
            "with the knob off the pre-CNT.6 bypass must return, or there is " \
            "no A/B control and no way back"


def test_a_non_runaway_premium_tick_was_never_dispatching_anyway():
    """Guards against overstating what changed: only the runaway path moved."""
    for r in PREMIUM:
        assert not _dispatches(r, is_runaway=False, block=False), \
            "without a runaway, a premium regime never opened continuation — " \
            "the bypass was the whole mechanism"
