"""
tests/test_exit_latency.py — v1.1 — 2026-08-04 (N.5)

v1.1 — 2026-08-04 — the clock is pinned. `exit_escalated` is set from 15:45 ET
by the hard-close ladder, so these assertions passed all day and failed after
the close. Found the same hour as the identical defect in
tests/test_stale_no_regime_flip.py.

Proves the exit-ladder latency capture through the REAL `place_exit_order` seam
and a REAL sqlite trades table. The paper path is exercised end to end; the live
path's multi-tick accumulation is exercised through the same public seam by
driving the record state the live loop maintains, because standing up a broker
session in a unit test would test the mock, not the ladder.

The load-bearing assertions are the two that describe how this capture can be
WRONG rather than absent:
  - an UNCONFIRMED pass must write nothing and must NOT reset the submit
    instant, or every slow close reports only its fast final leg;
  - `exit_mark_at_trigger` must be the mark the exit DECISION saw, not the
    price it eventually filled at — in paper they coincide, and that
    coincidence is the plumbing proof, not a result.

Deliberate-failure check performed when written: stamping `_exit_submit_ts` on
every pass (instead of only the first) turns
test_unconfirmed_pass_does_not_restart_the_clock red; writing on an unconfirmed
result turns test_unconfirmed_close_writes_nothing red.
"""

import os
import sqlite3
import sys
import tempfile
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.trade_logger import TradeLogger          # noqa: E402
from execution.exit_engine import ExitEngine, FillResult  # noqa: E402


def _engine_and_logger():
    """A paper ExitEngine writing to a throwaway DB — never the repo root."""
    tmp = tempfile.mkdtemp()
    tl = TradeLogger(db_path=os.path.join(tmp, "trades.db"), paper_trading=True)
    eng = ExitEngine(paper_trading=True)
    eng._trade_logger = tl
    return eng, tl


@pytest.fixture(autouse=True)
def _outside_the_flatten_window(monkeypatch):
    """v1.1 — PIN THE CLOCK. `exit_escalated` is set whenever
    hard_close_order_mode() reads "market", i.e. from 15:45 ET, so the escalation
    assertions below were time-of-day dependent: green all day, red after the
    close. Second test of mine flushed out by one 15:58 ET suite run — the same
    defect class in a different file, both shipped today.
    The escalation test drives the flag through the record instead, which is what
    the live deadline branch does anyway."""
    import execution.exit_engine as xe
    monkeypatch.setattr(xe, "hard_close_order_mode", lambda _now: "none")


def _open_trade(tl, trade_id="lat001"):
    tl.log_entry({"trade_id": trade_id, "symbol": "QQQ",
                  "strategy": "ORBStrategy", "contracts": 2})
    return {"trade_id": trade_id, "contracts": 2}


def _row(tl, trade_id="lat001"):
    with sqlite3.connect(tl.db_path) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute("SELECT * FROM trades WHERE trade_id=?",
                            (trade_id,)).fetchone()


# ── columns ──────────────────────────────────────────────────────────────────
def test_columns_exist_after_migration():
    _, tl = _engine_and_logger()
    with sqlite3.connect(tl.db_path) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(trades)")]
    for c in ("exit_submit_ts", "exit_fill_ts", "exit_latency_ms",
              "exit_ladder_steps", "exit_escalated", "exit_mark_at_trigger"):
        assert c in cols, c


def test_never_exited_stays_null():
    """NULL means 'no confirmed close'. It must stay distinguishable from a
    close that filled instantly, which writes a real 0-ish latency."""
    _, tl = _engine_and_logger()
    _open_trade(tl)
    r = _row(tl)
    assert r["exit_submit_ts"] is None and r["exit_latency_ms"] is None


# ── the paper path, through the real seam ────────────────────────────────────
def test_paper_close_writes_the_full_row():
    eng, tl = _engine_and_logger()
    rec = _open_trade(tl)

    result = eng.place_exit_order(rec, "stop pnl=-40%", mark_price=1.25)
    assert result.confirmed is True

    r = _row(tl)
    assert r["exit_submit_ts"] and r["exit_fill_ts"]
    assert r["exit_latency_ms"] is not None and r["exit_latency_ms"] >= 0
    assert r["exit_ladder_steps"] == 1
    assert r["exit_escalated"] == 0


def test_mark_at_trigger_is_the_decisions_mark_and_paper_equals_the_fill():
    """The plumbing proof N.5 predicts: paper books the mark, so trigger and
    fill coincide. Asserting the equality is what proves the field is wired to
    the DECISION's mark rather than to the booked price by accident."""
    eng, tl = _engine_and_logger()
    rec = _open_trade(tl)
    result = eng.place_exit_order(rec, "trail", mark_price=2.40)
    assert _row(tl)["exit_mark_at_trigger"] == pytest.approx(2.40)
    assert result.fill_price == pytest.approx(2.40)


def test_the_result_is_returned_unchanged():
    """Log-only means pass-through. The FillResult the caller books from must be
    the one the exit path produced, untouched."""
    eng, tl = _engine_and_logger()
    rec = _open_trade(tl)
    result = eng.place_exit_order(rec, "bos_exit", mark_price=0.85)
    assert (result.confirmed, result.fill_price, result.detail) == \
           (True, 0.85, "paper simulated fill")


# ── the multi-tick behaviour that makes or breaks the measurement ────────────
def test_unconfirmed_close_writes_nothing():
    """No mark → no simulated fill → nothing booked. A row written here would
    put a fabricated instant inside the population TC.2 measures on."""
    eng, tl = _engine_and_logger()
    rec = _open_trade(tl)
    result = eng.place_exit_order(rec, "stop", mark_price=None)
    assert result.confirmed is False
    assert _row(tl)["exit_submit_ts"] is None


def test_stamp_writes_nothing_on_an_unconfirmed_result():
    """Covers the LIVE path's guard specifically. The paper path returns its
    unconfirmed result before the stamp is ever reached, so the paper test
    above cannot exercise this — the live loop, which returns unconfirmed
    results THROUGH the stamp on every deadline and partial, can and does.
    Found by running the deliberate-failure check rather than by reading it:
    breaking the confirmed-guard left the paper test green.
    """
    eng, tl = _engine_and_logger()
    rec = _open_trade(tl)
    eng.place_exit_order(rec, "stop", mark_price=None)        # seed submit state
    out = eng._stamp_exit_latency(
        rec, FillResult(confirmed=False, detail="deadline; resuming next tick"))
    assert out.confirmed is False
    assert _row(tl)["exit_submit_ts"] is None


def test_unconfirmed_pass_does_not_restart_the_clock():
    """THE ONE THAT MATTERS. A live close is multi-tick: the deadline expires
    and the next tick resumes. If the submit instant were re-stamped per pass,
    every slow close would report only its final leg — the fast half of exactly
    the closes the study exists to find."""
    eng, tl = _engine_and_logger()
    rec = _open_trade(tl)

    eng.place_exit_order(rec, "stop", mark_price=None)      # pass 1, no fill
    first_submit = rec["_exit_submit_ts"]
    assert first_submit
    time.sleep(0.05)
    eng.place_exit_order(rec, "stop", mark_price=None)      # pass 2, no fill
    assert rec["_exit_submit_ts"] == first_submit

    eng.place_exit_order(rec, "stop", mark_price=1.10)      # pass 3, fills
    r = _row(tl)
    assert r["exit_submit_ts"] == first_submit
    assert r["exit_ladder_steps"] == 3
    assert r["exit_latency_ms"] >= 50


def test_escalation_flag_survives_to_the_row():
    """Set by the live loop's deadline-cancel branch and by the 15:45 market
    cross. Driven here through the record, which is the same state both write."""
    eng, tl = _engine_and_logger()
    rec = _open_trade(tl)
    eng.place_exit_order(rec, "hard_close_15:45_ET", mark_price=None)
    rec["_exit_escalated"] = 1          # what the deadline branch sets
    eng.place_exit_order(rec, "hard_close_15:45_ET", mark_price=0.05)
    assert _row(tl)["exit_escalated"] == 1


# ── the writer's own contract ────────────────────────────────────────────────
def test_writer_reports_a_real_write():
    _, tl = _engine_and_logger()
    _open_trade(tl)
    assert tl.set_exit_latency("lat001", "t0", "t1", 12, 2, False, 1.5) is True
    assert tl.set_exit_latency("nope", "t0", "t1", 12, 2, False, 1.5) is False
    assert tl.set_exit_latency("lat001", "", "t1", 12, 2, False) is False


def test_missing_mark_is_null_not_zero():
    """A real mark is never exactly 0.0 on a position being closed, so a zero
    here would be indistinguishable from 'no mark was available'."""
    _, tl = _engine_and_logger()
    _open_trade(tl)
    tl.set_exit_latency("lat001", "t0", "t1", 5, 1, False, None)
    assert _row(tl)["exit_mark_at_trigger"] is None


def test_capture_failure_never_breaks_the_close():
    """If the writer explodes, the close still books. The capture is telemetry;
    it may lose data, it may not lose a position."""
    eng, tl = _engine_and_logger()
    rec = _open_trade(tl)

    class _Boom:
        def set_exit_latency(self, **kw):
            raise RuntimeError("db gone")
    eng._trade_logger = _Boom()

    result = eng.place_exit_order(rec, "stop", mark_price=1.00)
    assert result.confirmed is True and result.fill_price == pytest.approx(1.00)
