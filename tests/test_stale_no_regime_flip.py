"""
tests/test_stale_no_regime_flip.py — v1.1 — 2026-08-04 (main v5.2)

v1.1 — 2026-08-04 — the clock is pinned. v1.0 was time-of-day dependent: the
15:45 hard close short-circuits ahead of every regime branch these tests
exercise, so the file was green all day and red between 15:45 and 16:00 ET. A
suite that passes depending on when you run it is worse than one that fails.

Operator directive, 2026-08-04: "Do not execute a regime flip exit on stale."

The rule has TWO halves and the second is the one that can be got wrong:
  1. no regime-driven exit may fire while the book is stale, and
  2. every PRICE-based exit must keep firing. Stale means the regime book has
     not resolved — it is not evidence the price feed is down, and a 0DTE
     position that skips its 15:45 flatten becomes an overnight orphan on an
     expiring contract.

So these tests assert both directions through the real ExitEngine: that a live
label DOES flip the trade out (proving the mechanism is armed and the None case
is not passing vacuously), and that withholding the label suppresses the flip
while the hard close and the max-loss floor still fire on the same record.

Deliberate-failure check performed when written: reverting main.py's `regime=(
None if _rgm_stale ...)` to the v5.1 form turns
test_main_withholds_the_label_while_the_book_is_stale red.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution.exit_engine import ExitEngine        # noqa: E402


def _continuation_record():
    """A long continuation position, comfortably inside every price stop so
    that ONLY the regime branch can close it."""
    return {
        "trade_id":      "stale01",
        "symbol":        "QQQ",
        "strategy":      "ContinuationStrategy",
        "direction":     "long",
        "option_side":   "call",
        "contracts":     1,
        "entry_premium": 1.00,
        "stop_premium":  0.60,
        "max_loss":      100.0,
        "status":        "open",
        "is_butterfly":  0,
        "is_condor_leg": 0,
        "target_premium": 2.00,
        "entry_time":    "2026-08-04T14:00:00+00:00",
    }


def _eng():
    return ExitEngine(paper_trading=True)


@pytest.fixture(autouse=True)
def _not_hard_close(monkeypatch):
    """v1.1 — PIN THE CLOCK. Every test below reasons about the regime branch,
    and `hard_close_15:45_ET` short-circuits BEFORE it. Without this the suite
    passes all day and fails between 15:45 and 16:00 ET — which is exactly when
    someone would be running it after the close. Found on 2026-08-04 by a suite
    run that happened to land in that window; it had been green since the file
    shipped that morning purely because of the hour.
    The one test that WANTS the hard close overrides this with its own patch.
    """
    import execution.exit_engine as xe
    monkeypatch.setattr(xe, "is_hard_close_time", lambda: False)


# ── the mechanism is armed (so the None case below is not vacuous) ───────────
def test_a_live_adverse_label_does_flip_the_trade_out():
    d = _eng().evaluate(_continuation_record(), current_premium=0.98,
                        regime="RANGING")
    assert d.should_exit is True
    assert "regime_flip" in d.exit_reason


def test_a_live_with_trend_label_does_not_flip_it_out():
    d = _eng().evaluate(_continuation_record(), current_premium=0.98,
                        regime="TRENDING_BULL")
    assert d.should_exit is False or "regime_flip" not in d.exit_reason


# ── half 1: withholding the label suppresses the regime exit ────────────────
def test_no_regime_flip_when_the_label_is_withheld():
    """The same record and the same premium that flipped out above. The only
    difference is that the book was stale, so no label was supplied."""
    d = _eng().evaluate(_continuation_record(), current_premium=0.98,
                        regime=None)
    assert "regime_flip" not in (d.exit_reason or "")


def test_butterfly_and_condor_regime_exits_are_suppressed_too():
    """All three regime-driven branches, not just continuation's."""
    fly = _continuation_record() | {"trade_id": "stale02", "is_butterfly": 1,
                                    "net_debit": 1.0, "max_profit": 3.0,
                                    "target_premium": 3.0}
    leg = _continuation_record() | {"trade_id": "stale03", "is_condor_leg": 1,
                                    "credit_received": 0.70, "spread_width": 5.0,
                                    "target_premium": 0.05}
    for rec in (fly, leg):
        d = _eng().evaluate(rec, current_premium=0.90, regime=None)
        assert "regime_flip" not in (d.exit_reason or ""), rec["trade_id"]


# ── half 2: price-based protection is UNAFFECTED ────────────────────────────
def test_the_max_loss_floor_still_fires_with_no_label():
    """A position deep through its floor must still close on a stale book."""
    d = _eng().evaluate(_continuation_record(), current_premium=0.30,
                        regime=None)
    assert d.should_exit is True
    assert "regime_flip" not in d.exit_reason


def test_the_hard_close_still_fires_with_no_label(monkeypatch):
    """15:45 is not negotiable — a 0DTE position left open becomes an overnight
    orphan on an expiring contract."""
    import execution.exit_engine as xe
    monkeypatch.setattr(xe, "is_hard_close_time", lambda: True)
    d = _eng().evaluate(_continuation_record(), current_premium=0.98,
                        regime=None)
    assert d.should_exit is True
    assert "hard_close" in d.exit_reason


# ── the wiring itself, asserted at source ───────────────────────────────────
def test_main_withholds_the_label_while_the_book_is_stale():
    """Source-level, deliberately. The gate lives in main.py's tick loop, which
    cannot be stood up in a unit test — but a silent revert to the v5.1 form is
    exactly the regression this rule exists to prevent, and it is greppable.
    Same idiom as tests/test_replay_1m_session_scope.py.
    """
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "main.py")).read()
    assert "_rgm_stale" in src, "v5.2 stale gate is missing from main.py"
    assert re.search(r"regime=\(None if _rgm_stale", src), \
        "manage_open_position no longer withholds the label on a stale book"
