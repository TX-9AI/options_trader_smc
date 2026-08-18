"""
tests/test_mode_isolation.py — audit defect Q: paper and live rows in one
trades.db must never cross modes in any decision or session-truth query.

Proves, on a single shared DB file:
  1. A LIVE logger's get_open_trades()/get_open_trade() return ONLY live rows —
     the live bot can never adopt and "manage" open paper positions. Paper
     symmetrically never sees live rows (paper keeps firing exactly as before).
  2. realized_pnl_today() — the DAILY_LOSS_LIMIT source of truth — sums only
     the current mode's P&L. Two weeks of paper red cannot halt real-money
     entries, and live losses cannot poison the paper dashboard.
  3. get_session_losses()/get_consecutive_losses() are mode-scoped.
  4. close_expired_open_trades() only autocloses the current mode's expired
     rows — a live bot leaves stale paper opens untouched.
  5. Legacy rows with paper_trade=NULL count as PAPER (schema default) — the
     safe direction: live sees none of them.

Run: PYTHONPATH=. pytest tests/test_mode_isolation.py -v
"""

import sys
import os
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.trade_logger import TradeLogger, make_record  # noqa: E402
from utils.time_utils import ts_for_db                      # noqa: E402


def _row(paper: int, status="open", pnl=None, expiry="2099-12-31", **kw):
    rec = make_record(
        trade_id      = str(uuid.uuid4()),
        symbol        = "SPX",
        strategy      = "IronCondorStrategy",
        contracts     = 1,
        entry_premium = 1.50,
        expiry        = expiry,
        paper_trade   = paper,
        status        = status,
        entry_time    = ts_for_db(),
        **kw,
    )
    return rec


@pytest.fixture
def loggers(tmp_path):
    db = str(tmp_path / "trades.db")
    paper = TradeLogger(db_path=db, paper_trading=True)
    live  = TradeLogger(db_path=db, paper_trading=False)
    return paper, live


def test_open_positions_never_cross_modes(loggers):
    paper, live = loggers
    p1 = _row(paper=1); paper.log_entry(p1)
    p2 = _row(paper=1); paper.log_entry(p2)
    l1 = _row(paper=0); live.log_entry(l1)

    live_open  = live.get_open_trades()
    paper_open = paper.get_open_trades()

    assert {r["trade_id"] for r in live_open}  == {l1["trade_id"]}
    assert {r["trade_id"] for r in paper_open} == {p1["trade_id"], p2["trade_id"]}
    # single-row variant too
    assert live.get_open_trade()["trade_id"] == l1["trade_id"]
    # and the liveness-filtered recovery view
    assert {r["trade_id"] for r in live.get_open_trades_live()} == {l1["trade_id"]}


def test_daily_loss_source_of_truth_is_mode_scoped(loggers):
    paper, live = loggers
    # A red paper day...
    for pnl in (-300.0, -250.0):
        r = _row(paper=1); paper.log_entry(r)
        paper.log_exit(r["trade_id"], exit_price=0.10, pnl_usd=pnl, exit_reason="stop")
    # ...and a green live day in the same file.
    r = _row(paper=0); live.log_entry(r)
    live.log_exit(r["trade_id"], exit_price=0.50, pnl_usd=100.0, exit_reason="target")

    assert live.realized_pnl_today()  == pytest.approx(100.0)   # breaker sees ONLY live
    assert paper.realized_pnl_today() == pytest.approx(-550.0)  # paper stays honest too
    assert live.get_session_losses()  == 0
    assert paper.get_session_losses() == 2
    assert live.get_consecutive_losses()  == 0
    assert paper.get_consecutive_losses() == 2


def test_expired_autoclose_only_touches_own_mode(loggers):
    paper, live = loggers
    stale_paper = _row(paper=1, expiry="2020-01-01"); paper.log_entry(stale_paper)
    stale_live  = _row(paper=0, expiry="2020-01-01"); live.log_entry(stale_live)

    closed = live.close_expired_open_trades()
    assert {r["trade_id"] for r in closed} == {stale_live["trade_id"]}
    # the paper row is still open, untouched by the live bot
    assert {r["trade_id"] for r in paper.get_open_trades()} == {stale_paper["trade_id"]}


def test_legacy_null_flag_counts_as_paper(loggers):
    paper, live = loggers
    r = _row(paper=1); paper.log_entry(r)
    # simulate a pre-flag legacy row: NULL paper_trade
    import sqlite3
    with sqlite3.connect(paper.db_path) as conn:
        conn.execute("UPDATE trades SET paper_trade=NULL WHERE trade_id=?",
                     (r["trade_id"],))
    assert live.get_open_trades() == []                       # live sees nothing
    assert {x["trade_id"] for x in paper.get_open_trades()} == {r["trade_id"]}
