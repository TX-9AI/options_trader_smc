"""
tests/test_entry_contract.py — v1.0 — 2026-08-04 (N.9)

Covers trade_logger v3.12's contract telemetry and main v5.5's capture.

WHY THIS DATA EXISTS. Every other instrument in this repo reports WHAT the
premium did — MFE, MAE, giveback, capture ratio, the floor sweep — and they are
correctly denominated in premium, which is where the P&L lives. None of them
reports WHY. A -27% floor stop is indistinguishable between "the underlying
went against us", "the underlying went nowhere and theta ate it" and "we were
right and IV collapsed". Three causes, three different fixes, one number.

NOTHING NEW IS FETCHED: OptionContract already carries bid/ask/delta/gamma/
theta/iv and OptionsChain carries iv_rank. They were read for strike selection
and discarded.

Deliberate-failure check performed when written: matching the contract on
strike instead of the OCC symbol turns test_the_contract_is_matched_on_occ_symbol
red (a condor's two legs share strike-adjacent rows); dropping the all-None
guard turns test_an_empty_payload_is_not_written red.
"""

import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.trade_logger import TradeLogger, make_record  # noqa: E402


def _tl():
    return TradeLogger(db_path=os.path.join(tempfile.mkdtemp(), "t.db"))


def _row(tl, cols, tid="t1"):
    return sqlite3.connect(tl.db_path).execute(
        f"select {cols} from trades where trade_id='{tid}'").fetchone()


def _open(tl, tid="t1"):
    tl.log_entry(make_record(trade_id=tid, symbol="AAA", direction="long",
                             strategy="X", entry_premium=1.15,
                             underlying_entry=101.2, contracts=1,
                             strike=100.0, option_side="C"))


def test_the_ten_columns_persist():
    tl = _tl(); _open(tl)
    assert tl.set_entry_contract("t1", {
        "entry_delta": 0.32, "entry_gamma": 0.02, "entry_theta": -0.08,
        "entry_iv": 0.44, "entry_bid": 1.10, "entry_ask": 1.20,
        "chain_iv_rank": 0.6})
    r = _row(tl, "entry_delta,entry_gamma,entry_theta,entry_iv,entry_bid,"
                 "entry_ask,chain_iv_rank")
    assert r == (0.32, 0.02, -0.08, 0.44, 1.10, 1.20, 0.6), r


def test_mark_and_spot_are_not_duplicated():
    """`entry_premium` and `underlying_entry` predate this and already hold the
    mark and the spot. Adding entry_mark / chain_spot_at_entry would have made
    two names for one fact, which is how a report quietly reads the stale one."""
    tl = _tl(); _open(tl)
    cols = {r[1] for r in sqlite3.connect(tl.db_path)
            .execute("PRAGMA table_info(trades)")}
    assert "entry_mark" not in cols and "chain_spot_at_entry" not in cols
    assert {"entry_premium", "underlying_entry"} <= cols


def test_an_empty_payload_is_not_written():
    """An all-None write would stamp the row as captured while carrying
    nothing — indistinguishable afterwards from a real capture that found
    zeros."""
    tl = _tl(); _open(tl)
    assert not tl.set_entry_contract("t1", {})
    assert not tl.set_entry_contract("t1", {"entry_delta": None})


def test_an_unknown_trade_id_is_not_written():
    tl = _tl(); _open(tl)
    assert not tl.set_entry_contract("nope", {"entry_delta": 0.3})


def test_nulls_stay_distinguishable_from_captured_zeros():
    """Rows written before v3.12 must remain readable AND identifiable. A
    default of 0.0 would make a pre-deploy trade look like a 0-delta entry."""
    tl = _tl(); _open(tl)
    assert _row(tl, "entry_delta,entry_iv") == (None, None)


def test_the_contract_is_matched_on_occ_symbol():
    """main v5.5 matches on `option_symbol`, not strike. A condor's two legs
    share an underlying and a session; matching loosely would attribute one
    leg's greeks to the other."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "main.py")).read()
    body = src[src.index("def _capture_entry_contract"):]
    body = body[:body.index("def _capture_entry_snapshot")]
    assert 'getattr(c, "symbol", "") == occ' in body
    assert 'record or {}).get("option_symbol"' in body


def test_the_capture_warns_once_and_never_gates():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "main.py")).read()
    body = src[src.index("def _capture_entry_contract"):]
    body = body[:body.index("def _capture_entry_snapshot")]
    assert "_contract_warned" in body
    assert "logger.debug(" in body, \
        "the except body must log INLINE or the W.2 swallow census reads it " \
        "as a silent handler"
    assert "return False" in body


def test_both_fill_seams_capture():
    """The directional entry AND the condor leg. A condor leg that skipped this
    would be invisible in the decomposition while still appearing in the P&L."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "main.py")).read()
    assert src.count("_capture_entry_contract(ctx, record)") == 2
