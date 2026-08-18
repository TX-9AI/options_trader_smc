"""
tests/test_orb_not_gated_by_stale.py — v1.0 — 2026-08-04 (main v5.4)

v5.0 blocked ALL new entries while the regime book is stale. The block sits
above the dispatch, so it returned before `orb_regime_bypass` ever ran — which
made `ORB_FIRES_REGARDLESS_OF_REGIME`, the constant defect V created precisely
to un-gate the flagship, unreachable on any stale tick.

Measured on 2026-08-04: the block ran 09:35:01 → 09:39-09:41 ET on all 15 boxes.
ORB's entry window opens at 09:35:00. So every session since v5.0 deployed lost
the first four to six minutes of the flagship's window, fleet-wide, silently —
the log line said "Entry blocked", not "ORB blocked", and ORB simply produced
fewer morning trades.

Both halves are asserted, because the second is where a fix like this goes
wrong: ORB proceeds, and NOTHING ELSE does. Widening this to "ignore stale"
would delete v5.0's actual protection, which is real — continuation, condor,
butterfly and sweep all condition on the label.

Deliberate-failure check performed when written: dropping `_orb_exempt` from the
condition turns test_a_confirmed_orb_is_exempt red; making the exemption
unconditional (not keyed on ORB state) turns
test_everything_other_than_a_confirmed_orb_is_still_blocked red.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MAIN = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "main.py")).read()


def _gate_block() -> str:
    """The stale-gate region: from the v5.4 comment to the chain fetch.

    Source-level, deliberately. The gate lives inside `attempt_new_entry`, whose
    real path needs a broker chain, a risk manager, a session guard and a live
    integrator — standing all of that up would test the mocks. A silent revert
    to the v5.0 form is the regression that matters, and it is greppable.
    Same idiom as tests/test_stale_no_regime_flip.py's source assert.
    """
    start = MAIN.index("v5.4 — ORB IS EXEMPT")
    return MAIN[start:MAIN.index("Fetch options chain", start)]


def test_a_confirmed_orb_is_exempt():
    g = _gate_block()
    assert "_orb_exempt" in g
    assert "ORBState.OPEN_LONG" in g and "ORBState.OPEN_SHORT" in g, \
        "the exemption must be keyed on a CONFIRMED break, not on ORB existing"


def test_the_exemption_honours_the_config_constant():
    """If ORB_FIRES_REGARDLESS_OF_REGIME is turned off, ORB is regime-gated by
    intent and the exemption must go with it."""
    assert "ORB_FIRES_REGARDLESS_OF_REGIME and _orb_ctx is not None" in _gate_block()


def test_everything_other_than_a_confirmed_orb_is_still_blocked():
    """v5.0's protection is real for every strategy that reads the label. The
    gate must still return — the exemption is a branch inside it, not a deletion
    of it."""
    g = _gate_block()
    assert "if not _orb_exempt:" in g, "the block must still fire for non-ORB"
    assert re.search(r"if not _orb_exempt:\s*\n\s*logger\.info\(\"Entry blocked",
                     g), "the non-ORB path must still log and return"
    assert "return" in g.split("if not _orb_exempt:")[1]


def test_the_stale_gate_itself_survives():
    """A fix that removed the gate would pass every assertion above."""
    assert 'getattr(_l2_integ, "stale", False)' in _gate_block()


def test_the_exempt_path_says_why_in_the_log():
    """A branch that silently proceeds where the previous version blocked is the
    kind of change nobody can audit from a log after the fact."""
    g = _gate_block()
    assert "STALE book, but ORB is CONFIRMED" in g


def test_it_is_not_widened_to_ignore_stale():
    """`stale` is the regime BOOK; the feed has its own guard, latch and pager.
    An exemption phrased as 'skip the gate' rather than 'skip it for a confirmed
    ORB' would silently re-admit every strategy."""
    g = _gate_block()
    assert "_l2_integ" in g and "if not _orb_exempt:" in g
    # the unconditional early-return form must be gone
    assert not re.search(r'stale", False\):\s*\n\s*logger\.info\("Entry blocked',
                         g), "the v5.0 unconditional block form is back"
