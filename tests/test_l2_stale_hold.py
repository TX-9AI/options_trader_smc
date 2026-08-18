"""
tests/test_l2_stale_hold.py — v1.0 — 2026-08-03.

main.py v5.0 — the two stale rules. These test the DECISION LOGIC in isolation,
mirroring the branch structure in main.py's L2 gate, because the gate itself sits
inside a tick loop that needs a live feed, a chain and a broker to reach.

That is a real limitation and worth stating: these prove the RULES are right, not
that main.py is wired to them. The wiring is verified by the deploy gate's marker
check plus the log lines the rules emit on a live box ("L2.5 STALE — HOLDING ..."
and "Entry blocked: regime book is STALE").

WHAT WENT WRONG, and why the fix is shaped this way
    `st.regime and not st.stale` was READ correctly — the bug was the FALLBACK.
    On a stale tick the bot dropped to the v1.3 classifier, i.e. raw L1 argmax,
    which is exactly the churn L2 exists to remove (436 committed switches vs 695
    argmax flips). exit_engine checks regime-flip SECOND, before any price stop,
    so one wobbled tick closed the position.
    Measured over 2026-07-23 onward: regime_flip exits have median hold 0.8 min
    and p25 TWELVE SECONDS, against 5-12 min for every other exit reason. And the
    trigger is routine — a tick gap over dt_max=90s re-stales every tick.

THE ASYMMETRY IS THE POINT
    HOLD on exit, REFUSE on entry. Holding is declining to act on unknown
    information, and the position stays protected by every price-based stop, none
    of which read the label. Opening a position is a DECISION against a
    classification the engine cannot currently confirm.
    A test asserts BOTH, because "hold everything" and "refuse everything" are
    each trivially satisfiable and neither is the rule.

Run: PYTHONPATH=. pytest tests/test_l2_stale_hold.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _St:
    """Stand-in for the integrator's returned state."""
    def __init__(self, regime, conviction, stale):
        self.regime, self.conviction, self.stale = regime, conviction, stale


def decide(st, held):
    """The v5.0 gate, mirroring main.py's branch order exactly.

    Returns (source, label, conviction) where source is:
      "l2"    committed and fresh — the normal path
      "hold"  stale WITH a remembered label — the fix
      "v13"   fall through to the un-smoothed classifier
    """
    if st.regime and not st.stale:
        held["regime"], held["conviction"] = st.regime, st.conviction
        held["since"] = None
        return "l2", st.regime, st.conviction
    if st.stale and held["regime"]:
        if held["since"] is None:
            held["since"] = "now"
        return "hold", held["regime"], held["conviction"]
    return "v13", None, 0.0


def entry_allowed(integrator_stale):
    """v5.0 entry rule: no new entries while the book is stale."""
    return not integrator_stale


@pytest.fixture
def held():
    return {"regime": None, "conviction": 0.0, "since": None}


# ── the normal path still works ──────────────────────────────────────────────
def test_fresh_committed_label_is_used(held):
    src, label, conv = decide(_St("TRENDING_BULL", 0.82, False), held)
    assert (src, label) == ("l2", "TRENDING_BULL")
    assert held["regime"] == "TRENDING_BULL", "the label was not remembered"


# ── the fix ──────────────────────────────────────────────────────────────────
def test_stale_holds_the_last_committed_label(held):
    decide(_St("TRENDING_BULL", 0.82, False), held)          # commit
    src, label, conv = decide(_St("RANGING", 0.11, True), held)  # stale wobble
    assert src == "hold", "fell back to the un-smoothed classifier"
    assert label == "TRENDING_BULL", (
        "held the WOBBLE instead of the committed label — this is the bug, not "
        "the fix")
    assert conv == 0.82


def test_a_stale_wobble_does_not_flip_the_label(held):
    """The exact sequence that closed positions in 12 seconds: commit TRENDING,
    one stale tick reading something else, then recovery."""
    decide(_St("TRENDING_BULL", 0.80, False), held)
    seq = [_St("RANGING", 0.10, True), _St("COMPRESSION", 0.09, True),
           _St("TRENDING_BULL", 0.79, False)]
    labels = [decide(s, held)[1] for s in seq]
    assert labels == ["TRENDING_BULL", "TRENDING_BULL", "TRENDING_BULL"], (
        f"label changed across a stale stretch: {labels}")


def test_a_real_committed_flip_still_changes_the_label(held):
    """The fix must not make the fork unkillable. A FRESH committed flip is real
    evidence and must be honoured — otherwise 'hold' becomes 'never exit'."""
    decide(_St("TRENDING_BULL", 0.80, False), held)
    src, label, _ = decide(_St("TRENDING_BEAR", 0.71, False), held)
    assert (src, label) == ("l2", "TRENDING_BEAR"), \
        "a genuine committed flip was suppressed — that would disable the exit"


# ── the cold-book path is unchanged ──────────────────────────────────────────
def test_cold_book_at_the_open_still_falls_back(held):
    """No prior state exists to hold, so v1.3 is correct here and must stay. This
    path was never the bug."""
    src, _, _ = decide(_St("", 0.0, True), held)
    assert src == "v13"


def test_empty_label_on_a_warm_book_falls_back(held):
    src, _, _ = decide(_St(None, 0.0, False), held)
    assert src == "v13"


# ── the asymmetry, asserted from both sides ─────────────────────────────────
def test_entries_are_refused_while_stale():
    assert entry_allowed(False) is True
    assert entry_allowed(True) is False, \
        "entries were allowed on a label the engine cannot confirm"


def test_hold_and_refuse_are_different_rules(held):
    """'Hold everything' and 'refuse everything' are each trivially satisfiable.
    The rule is HOLD on the label, REFUSE on entry — so a stale tick must do BOTH,
    and asserting only one of them would pass under the wrong design."""
    decide(_St("TRENDING_BULL", 0.80, False), held)
    src, label, _ = decide(_St("RANGING", 0.10, True), held)
    assert src == "hold" and label == "TRENDING_BULL"   # exits: hold
    assert entry_allowed(True) is False                  # entries: refuse


def test_recovery_clears_the_hold_marker(held):
    """`since` is observability only — it must reset on recovery so a later hold
    logs again rather than being silently swallowed by the throttle."""
    decide(_St("TRENDING_BULL", 0.80, False), held)
    decide(_St("RANGING", 0.10, True), held)
    assert held["since"] is not None
    decide(_St("TRENDING_BULL", 0.81, False), held)
    assert held["since"] is None, "a second stale stretch would log nothing"
