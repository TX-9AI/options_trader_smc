"""
tests/test_conditional_session_spread.py — v1.0 — 2026-08-05

Guards conditional_tables v1.4's session-spread reporting.

WHY IT EXISTS. On 2026-08-05 the headline named
`BREAKOUT_VOLATILE x ORBStrategy x B  n=48  P(win)=25%  [15%,39%]  E=-$32.03`.
The Wilson interval excludes 50%, so on its face that is a starve candidate —
and the tool could not say whether the 48 trades came from eight sessions or
from two bad days. `trade_report` and `excursion_report` both carry a SESSION
SPREAD block for exactly this reason; the conditional table, which is the tool
a DISABLE decision would actually be read from, did not.

The Wilson interval answers "is this distinguishable from chance", which is a
question about n. It is silent on whether the n is a standing pattern.

Deliberate-failure check performed when written: dropping the date argument
from Cell.add turns test_a_two_session_cell_is_flagged red while leaving the
n and P(win) assertions green — which is precisely the blind spot being fixed.
"""

import importlib.util
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
_spec = importlib.util.spec_from_file_location(
    "ct", os.path.join(REPO, "tests", "conditional_tables.py"))
ct = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ct)


def _cell(dates):
    c = ct.Cell()
    for d in dates:
        c.add(-32.0, d)
    return c


def test_a_two_session_cell_is_flagged():
    """THE CASE THAT PROMPTED THIS. n is large, the interval is tight, and the
    whole thing is two days."""
    c = _cell(["2026-08-04"] * 44 + ["2026-08-03"] * 4)
    assert c.n == 48
    assert c.sessions == 2
    assert "2 SESSION(S)" in c.spread_flag()


def test_a_concentrated_cell_is_flagged_even_with_enough_sessions():
    """Three sessions clears the count test, but 90% on one date is still a
    one-day event wearing a multi-session label."""
    c = _cell(["2026-08-04"] * 45 + ["2026-08-03", "2026-07-31", "2026-07-30"])
    assert c.sessions == 4
    assert "SINGLE-SESSION" in c.spread_flag()


def test_a_well_spread_cell_is_not_flagged():
    c = _cell([f"2026-08-{1 + i % 8:02d}" for i in range(48)])
    assert c.sessions == 8
    assert c.spread_flag() == ""


def test_the_flag_does_not_change_the_statistics():
    """Session awareness is a WARNING, not a filter. A flagged cell still
    reports its real n, win rate and expectancy — suppressing it would hide a
    finding rather than qualify it."""
    c = _cell(["2026-08-04"] * 44 + ["2026-08-03"] * 4)
    c2 = ct.Cell()
    for _ in range(48):
        c2.add(-32.0)
    assert (c.n, c.wins, round(c.pnl, 2)) == (c2.n, c2.wins, round(c2.pnl, 2))


def test_sessions_survives_a_missing_date():
    """Rows without entry_time must not crash the cell or inflate the count."""
    c = ct.Cell()
    c.add(1.0, "")
    c.add(1.0, "2026-08-04")
    assert c.n == 2 and c.sessions == 1


def test_the_date_actually_reaches_the_cell_from_a_trade_ROW():
    """THE WIRING TEST, and the first draft of this file did not have it.

    Every other test here builds a Cell by hand, so dropping the date argument
    at the build_trade_tables call site left all of them GREEN — the exact
    regression the guard exists to catch, invisible to the guard. Found by the
    deliberate-failure run, which is what it is for.
    """
    rows = [{"pnl_usd": -32.0, "contracts": 1, "regime": "BREAKOUT_VOLATILE",
             "strategy": "ORBStrategy", "setup_grade": "B",
             "entry_time": f"2026-08-{1 + i % 2:02d}T14:00:00"}
            for i in range(48)]
    tables = ct.build_trade_tables(rows)
    cells = [c for c in tables[("regime",)].values() if c.n]
    assert cells, tables
    assert any(c.sessions == 2 for c in cells), \
        "entry_time is not reaching Cell.add — every cell will report as a " \
        "standing pattern regardless of how few sessions produced it"


def test_the_headline_carries_sessions():
    src = open(os.path.join(REPO, "tests", "conditional_tables.py")).read()
    head = src[src.index("def build_headline"):]
    assert "sess={c.sessions}" in head
    assert "c.spread_flag()" in head, \
        "the headline is the line a disable decision is read from; it must " \
        "carry the concentration warning, not just the interval"
