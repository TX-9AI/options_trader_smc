"""
tests/test_entry_snapshot.py — v1.0 — 2026-08-04

Proves analysis/entry_snapshot.py against the REAL exit-engine gap finders and a
REAL sqlite trades table. Nothing here re-implements what it is testing: the
parity test asserts the snapshot's anchor IS the object
`_nearest_unfilled_fvg_in_favor` returns, so if the trail's rule changes and the
snapshot's does not, this file goes red. That is the whole point — a
counterfactual built on a divergent lineage measures the capture, not the trail.

Deliberate-failure check performed when written: capping FVG_CAP at 0 turns
test_gap_inventory_is_recovered red, and returning the frame unconditionally as
"1m" turns test_frame_matches_the_exit_engines_choice red.
"""

import json
import os
import sqlite3
import sys
import tempfile

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.entry_snapshot import build, to_json, SCHEMA_VERSION  # noqa: E402
from database.trade_logger import TradeLogger                        # noqa: E402


# ── Fixtures — a frame with ONE planted bullish gap, well above FVG_MIN_SIZE_PCT
def _frame_with_bullish_gap() -> pd.DataFrame:
    """Bars 0..2 create a bullish FVG: bar2.low (102.0) > bar0.high (100.0).

    Everything after drifts up and never trades back down through the gap, so
    the gap stays UNFILLED and sits BELOW price — which is the condition the
    long trail anchors to.
    """
    rows = [
        {"open": 99.0,  "high": 100.0, "low": 98.5,  "close": 99.5},   # 0
        {"open": 100.5, "high": 103.0, "low": 100.2, "close": 102.5},  # 1
        {"open": 102.5, "high": 104.0, "low": 102.0, "close": 103.5},  # 2  gap
        {"open": 103.5, "high": 105.0, "low": 103.0, "close": 104.5},  # 3
        {"open": 104.5, "high": 106.0, "low": 104.0, "close": 105.5},  # 4
    ]
    return pd.DataFrame(rows)


def _flat_frame(n: int = 6) -> pd.DataFrame:
    """No imbalance anywhere — every bar overlaps its neighbours."""
    return pd.DataFrame([{"open": 100.0, "high": 100.5,
                          "low": 99.5, "close": 100.0} for _ in range(n)])


class _Swing:
    def __init__(self, price):
        self.price = price


class _Smap:
    structure_sequence = "HH_HL"
    nearest_resistance = 106.5
    nearest_support = 101.25
    swing_highs = [_Swing(104.0), _Swing(106.0)]
    swing_lows = [_Swing(98.5), _Swing(103.0)]


def _ctx(df_1m=None, df_5m=None, price=105.5, structure=True):
    return {
        "price": price,
        "df_1m": df_1m,
        "df_5m": df_5m,
        "data": {"15m": _flat_frame(20), "1h": _flat_frame(9)},
        "structure": _Smap() if structure else None,
    }


# ── The capture itself ───────────────────────────────────────────────────────
def test_gap_inventory_is_recovered():
    snap = build(_ctx(df_1m=_frame_with_bullish_gap()), "long")
    assert "err" not in snap, snap.get("err")
    assert snap["v"] == SCHEMA_VERSION
    gaps = snap["fvg"]
    assert len(gaps) == 1, gaps
    assert gaps[0]["d"] == "bullish"
    assert gaps[0]["b"] == pytest.approx(100.0)
    assert gaps[0]["t"] == pytest.approx(102.0)


def test_anchor_is_byte_identical_to_the_trails_own_answer():
    """PARITY. The snapshot must record the SAME zone the trail would anchor to.

    Asked of the real function rather than a copy of its rule — if exit_engine's
    selection changes, this fails instead of the two silently diverging.
    """
    from execution.exit_engine import _nearest_unfilled_fvg_in_favor

    df = _frame_with_bullish_gap()
    ctx = _ctx(df_1m=df)
    snap = build(ctx, "long")

    truth = _nearest_unfilled_fvg_in_favor(df, current_price=ctx["price"],
                                           direction="long")
    assert truth is not None, "fixture no longer plants a reachable gap"
    assert snap["anchor"] == {"t": round(float(truth.top), 4),
                              "b": round(float(truth.bottom), 4)}


def test_frame_matches_the_exit_engines_choice():
    """USE_5M_FVG_TRAIL defaults on, so a usable 5m frame wins — the trail
    anchors there and so must the snapshot."""
    from execution.exit_engine import ExitEngine

    df1, df5 = _frame_with_bullish_gap(), _flat_frame(8)
    ctx = _ctx(df_1m=df1, df_5m=df5)
    chosen = ExitEngine._fvg_frame(df1, df5)
    expected = "5m" if chosen is df5 else "1m"
    assert build(ctx, "long")["frame"] == expected


def test_no_anchor_is_recorded_as_null_not_omitted():
    """A trade entered with no in-favor gap is a real observation: the trail had
    nothing to anchor to and fell back to the percentage leash. Null must be
    distinguishable from 'we did not look'."""
    snap = build(_ctx(df_1m=_flat_frame()), "long")
    assert "anchor" in snap and snap["anchor"] is None
    assert snap["fvg"] == []


def test_condor_leg_is_neutral_and_takes_no_anchor():
    snap = build(_ctx(df_1m=_frame_with_bullish_gap()), "neutral")
    assert snap["dir"] == "neutral"
    assert snap["anchor"] is None
    assert len(snap["fvg"]) == 1        # inventory still captured


def test_depth_is_recorded_per_timeframe():
    """AK's finding is why this is here: a vote cast on a starved frame is not
    the vote a warm frame casts, and depth is gone once the tick ends."""
    snap = build(_ctx(df_1m=_frame_with_bullish_gap(), df_5m=_flat_frame(30)),
                 "long")
    assert snap["depth"] == {"1m": 5, "5m": 30, "15m": 20, "1h": 9}


def test_structure_levels_come_from_the_live_map():
    snap = build(_ctx(df_1m=_frame_with_bullish_gap()), "long")
    assert snap["swing"] == {"seq": "HH_HL", "res": 106.5, "sup": 101.25,
                             "hi": 106.0, "lo": 103.0}


def test_missing_structure_is_empty_not_zero():
    """None must never be coerced to 0.0 — a real level is never exactly zero,
    so a zero would be indistinguishable from 'not formed yet'."""
    snap = build(_ctx(df_1m=_flat_frame(), structure=False), "long")
    assert snap["swing"] == {}


# ── It must never take a position down ───────────────────────────────────────
@pytest.mark.parametrize("ctx", [
    {},                                       # nothing at all
    {"price": None, "df_1m": None},           # no price, no frames
    {"price": "not-a-number", "df_1m": 17},   # wrong types throughout
])
def test_build_never_raises(ctx):
    snap = build(ctx, "long")
    assert snap["v"] == SCHEMA_VERSION
    assert "at" in snap


def test_to_json_always_returns_parseable_json():
    for ctx in ({}, _ctx(df_1m=_frame_with_bullish_gap())):
        parsed = json.loads(to_json(ctx, "long"))
        assert parsed["v"] == SCHEMA_VERSION


# ── The column, and the boolean that has to come back ────────────────────────
def _logger():
    tmp = tempfile.mkdtemp()
    return TradeLogger(db_path=os.path.join(tmp, "trades.db"),
                       paper_trading=True)


def test_column_exists_after_migration():
    tl = _logger()
    with sqlite3.connect(tl.db_path) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(trades)")]
    assert "entry_snapshot" in cols


def test_payload_round_trips_and_reports_success():
    tl = _logger()
    tl.log_entry({"trade_id": "abc123", "symbol": "QQQ", "strategy": "ORB"})
    payload = to_json(_ctx(df_1m=_frame_with_bullish_gap()), "long")

    assert tl.set_entry_snapshot("abc123", payload) is True

    with sqlite3.connect(tl.db_path) as conn:
        stored = conn.execute(
            "SELECT entry_snapshot FROM trades WHERE trade_id='abc123'"
        ).fetchone()[0]
    assert json.loads(stored)["anchor"]["t"] == pytest.approx(102.0)


def test_unknown_trade_id_returns_false_rather_than_silently_passing():
    """SQLite treats an UPDATE matching nothing as success. The whole reason
    this method returns a boolean is so that case is loud (item AU)."""
    tl = _logger()
    assert tl.set_entry_snapshot("no-such-trade", '{"v":1}') is False


def test_empty_inputs_return_false():
    tl = _logger()
    assert tl.set_entry_snapshot("", '{"v":1}') is False
    assert tl.set_entry_snapshot("abc", "") is False


def test_never_captured_stays_null_and_is_not_an_empty_string():
    """NULL means 'not captured'. It has to stay distinguishable from a capture
    that ran and found no gaps, which writes a real payload."""
    tl = _logger()
    tl.log_entry({"trade_id": "nocap", "symbol": "QQQ"})
    with sqlite3.connect(tl.db_path) as conn:
        val = conn.execute(
            "SELECT entry_snapshot FROM trades WHERE trade_id='nocap'"
        ).fetchone()[0]
    assert val is None
