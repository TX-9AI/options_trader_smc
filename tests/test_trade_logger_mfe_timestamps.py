"""
tests/test_trade_logger_mfe_timestamps.py — v1.0 — 2026-08-03

Guards trade_logger v3.9. The whole point of the column is to tell a trade that
peaked early and bled from one that reversed at the exit, so the test that
matters is that the stamp marks WHEN the extreme was set and does not creep
forward on every re-confirming tick. Proven by ticking a real path through a
real SQLite file, not by reading the SQL and agreeing with it.

Run:  cd ~/options-trader-v3 && venv/bin/python -m pytest \
          tests/test_trade_logger_mfe_timestamps.py -q
"""

import os
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.trade_logger import TradeLogger  # noqa: E402


def _logger(tmp_path):
    return TradeLogger(db_path=str(tmp_path / "trades.db"), paper_trading=True)


def _seed(tl, trade_id="T1"):
    with sqlite3.connect(tl.db_path) as conn:
        conn.execute("INSERT INTO trades (trade_id) VALUES (?)", (trade_id,))


def _read(tl, trade_id="T1"):
    with sqlite3.connect(tl.db_path) as conn:
        return conn.execute(
            "SELECT max_premium_seen, max_premium_seen_at, "
            "min_premium_seen, min_premium_seen_at FROM trades "
            "WHERE trade_id=?", (trade_id,)).fetchone()


def test_columns_exist_on_a_fresh_db(tmp_path):
    tl = _logger(tmp_path)
    with sqlite3.connect(tl.db_path) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(trades)")}
    assert "max_premium_seen_at" in cols
    assert "min_premium_seen_at" in cols


def test_columns_migrate_onto_a_db_that_predates_them(tmp_path):
    """Every banked row must survive the upgrade with NULL, not with a
    fabricated time."""
    path = str(tmp_path / "trades.db")
    tl = _logger(tmp_path)
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO trades (trade_id, max_premium_seen) "
                     "VALUES ('OLD', 1.5)")
        conn.execute("UPDATE trades SET max_premium_seen_at=NULL")
    TradeLogger(db_path=path, paper_trading=True)   # re-open, re-migrate
    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT max_premium_seen, max_premium_seen_at "
                           "FROM trades WHERE trade_id='OLD'").fetchone()
    assert row[0] == 1.5
    assert row[1] is None, "a pre-v3.9 row must read NULL, never a stand-in"


def test_mfe_timestamp_tracks_only_new_highs(tmp_path):
    """The path: up, higher, back down, lower still, new high, fade. The peak
    stamp must name the tick that SET the peak — t4 — not the last tick, and
    not t1 where the first high happened."""
    tl = _logger(tmp_path)
    _seed(tl)
    for premium, stamp in [(1.00, "t0"), (1.40, "t1"), (1.10, "t2"),
                           (0.70, "t3"), (1.90, "t4"), (1.20, "t5")]:
        tl.update_current_premium("T1", premium, ts=stamp)
    mx, mx_at, mn, mn_at = _read(tl)
    assert (mx, mx_at) == (1.90, "t4")
    assert (mn, mn_at) == (0.70, "t3")


def test_reconfirming_ticks_do_not_move_the_stamp(tmp_path):
    """An equal tick is not a new extreme. If it moved the stamp, a flat
    winner would look like it peaked at the exit."""
    tl = _logger(tmp_path)
    _seed(tl)
    tl.update_current_premium("T1", 1.50, ts="peak")
    for _ in range(5):
        tl.update_current_premium("T1", 1.50, ts="later")
    mx, mx_at, _, _ = _read(tl)
    assert (mx, mx_at) == (1.50, "peak")


def test_first_tick_seeds_both_stamps(tmp_path):
    tl = _logger(tmp_path)
    _seed(tl)
    tl.update_current_premium("T1", 1.00, ts="first")
    mx, mx_at, mn, mn_at = _read(tl)
    assert mx == mn == 1.00
    assert mx_at == mn_at == "first"


def test_production_call_needs_no_timestamp_argument(tmp_path):
    """Existing callers pass (trade_id, premium) only — v3.9 must not break
    them, and must stamp with ts_for_db()."""
    tl = _logger(tmp_path)
    _seed(tl)
    tl.update_current_premium("T1", 1.00)
    mx, mx_at, _, _ = _read(tl)
    assert mx == 1.00
    assert mx_at and mx_at.startswith("20"), \
        f"expected a UTC ISO stamp from ts_for_db(), got {mx_at!r}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
