"""
tests/test_rejection_ledger.py — v1.0 — 2026-08-07

Pins L3.2a's ONE load-bearing property: outcomes never read the decision bar.

⚠️ THE BACKLOG ITEM'S OWN VALIDATION DOES NOT PROVE THIS, and that is worth
recording rather than quietly working around. It prescribes "shift the decision
timestamp +1 bar and confirm outcomes change accordingly". They DO change — but
they change whether the window starts at `idx` or at `idx + 1`, because shifting
the index moves the reference price either way. So the shift test detects
DEPENDENCE ON THE INDEX, not exclusion of the decision bar. It passed on a
deliberately leaking build.
The property is structural, so it is pinned structurally: a hand-built series
where including the decision bar gives a DIFFERENT, KNOWN answer.
`--verify` is kept as a cheap sanity check — it still catches a degenerate or
constant join — but it is not the proof.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.rejection_ledger import outcome   # noqa: E402


def test_the_decision_bar_is_never_read():
    """Bar 0 is a spike that ONLY the decision bar sees. If it appears in the
    result, the join is leaking the information the block was made without."""
    series = [("09:30", 100.0), ("09:31", 101.0), ("09:32", 101.0)]
    mfe, mae = outcome(series, 0, 1.0, 5)
    assert abs(mfe - 1.0) < 1e-9
    # Including bar 0 would put a 0.0% move in the set and drag MAE to 0.0.
    assert abs(mae - 1.0) < 1e-9, (
        "MAE reached 0.0% — the decision bar is inside the window")


def test_direction_sign_inverts_for_shorts():
    series = [("09:30", 100.0), ("09:31", 99.0)]
    mfe, _ = outcome(series, 0, -1.0, 5)
    assert abs(mfe - 1.0) < 1e-9, "a short into a falling tape must read POSITIVE"


def test_no_forward_bars_returns_none():
    """The last bar of a session has no future. It must return None rather than
    a zero, which would be indistinguishable from a flat outcome."""
    assert outcome([("09:30", 100.0)], 0, 1.0, 5) is None
