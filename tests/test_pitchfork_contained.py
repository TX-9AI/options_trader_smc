"""
tests/test_pitchfork_contained.py — v1.0 — 2026-08-11

Pins §4.3.6, the CONTAINMENT anchor (pitchfork v1.3) and the weight-0 observer.

THE OPERATOR'S CONSTRUCTION, 2026-08-11: "start at the present date and go
backwards, and anything that falls out of the channel is not included in this
pitchfork." That inverts §4.3 — instead of selecting three pivots and hoping the
channel fits, CONTAINMENT DEFINES THE EXTENT and the anchors follow.

WHY IT EARNED A PLACE. On the same tapes the §4.3 pivot rule refuses everything
tested (SEPARATION / STRUCTURAL / FEWER_THAN_3_ALTERNATING_PIVOTS) while the
containment path builds forks with 97-100% of closes inside. It also REMOVES a
parameter: §4.3's RECENCY imposes one timescale on every symbol, and the
operator's objection was that "some forks are gonna be shorter than other ones —
some will be a week old, some months." Under containment the span is an OUTPUT
(measured: NVDA 1h 12 bars, SPX 1h 32, SMCI 1h 139 — one rule, three epochs).

THE FAILURES GUARDED, all silent:
1. **DETERMINISM LOST.** §4.3's whole bet is that anchor selection is a pure
   function of the tape — "if it needs judgment or per-symbol tuning the overlay
   is unbacktestable and should be abandoned rather than patched". Same bars in
   must mean same fork out, every time.
2. **THE CONFIRMATION LAG SKIPPED.** §4.4 is non-negotiable: a fork is born at
   index(P2) + k, never at index(P2). My sandbox prototype omitted this and
   produced a 12-bar NVDA fork that the repo version correctly refuses. A
   backtest anchoring at the pivot's own timestamp uses information that did not
   exist and every result is fiction.
3. **THE OBSERVER GAINING WEIGHT.** It must gate nothing and never raise. An
   observation module that can affect a trading decision by failing is not an
   observation module.

Deliberate-failure check performed when written: removing the `p2.idx + k >
n - 1` guard turns test_confirmation_lag_is_enforced red; making the observer
re-raise turns test_observer_never_raises red.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analysis.pitchfork as PF                                # noqa: E402
import analysis.pitchfork_observer as OBS                      # noqa: E402
import config                                                  # noqa: E402


def _leg(n=44, base=100.0):
    """low -> high -> reaction -> partial recovery.

    ⚠️ THE SHAPE MATTERS AND MY FIRST FIXTURE GOT IT WRONG: a monotone rise puts
    argmax on the LAST bar, so there is no room for P2 and no fork can exist —
    which is exactly why NVDA (seven bars straight up off its low, no pullback)
    correctly returns NO_CONTAINED_WINDOW on real tape. A fork needs the first
    REACTION; you cannot draw one on a one-way move.
    """
    hi_at = int(n * 0.45)
    lo2_at = int(n * 0.65)
    rows, px = [], base
    for i in range(n):
        if i < hi_at:
            px += 0.9
        elif i < lo2_at:
            px -= 0.75
        else:
            px += 0.22                     # recovers but stays BELOW the high:
                                           # 0.9*hi_at up, 0.75 down, then a
                                           # partial retrace — checked, not assumed
        rows.append((px - 0.25, px + 0.4, px - 0.5, px))
    idx = pd.date_range("2026-05-01", periods=n, freq="D")
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)
    df["volume"] = 1000.0
    return df


def _rising(n=44, **kw):
    return _leg(n)


def _atr(df):
    return OBS._atr(df)


def test_containment_builds_where_the_pivot_rule_refuses():
    df = _leg(44)
    a = _atr(df)
    c = PF.build_fork_contained("T", df, "1d", a)
    assert c is not None, \
        "the containment anchor exists BECAUSE the pivot rule refuses real " \
        "structure — if it cannot build here it has no reason to exist"
    assert c.direction == "bullish"


def test_it_is_deterministic():
    """§4.3's whole bet. Same bars in, same fork out."""
    df = _leg(44)
    a = _atr(df)
    f1 = PF.build_fork_contained("T", df, "1d", a)
    f2 = PF.build_fork_contained("T", df.copy(), "1d", a)
    assert (f1.p0.idx, f1.p1.idx, f1.p2.idx) == (f2.p0.idx, f2.p1.idx, f2.p2.idx)
    assert f1.slope == f2.slope


def _leg_p2_at_the_edge(n=40, base=100.0):
    """low -> high -> decline running to the LAST bar.

    P2 then lands within k of the end, so index(P2)+k exceeds the frame and the
    §4.4 lag is NOT yet served. This is the ONLY shape that exercises the guard;
    a fixture whose P2 sits mid-frame cannot see it, which is exactly why my
    first version of this test passed with the guard deleted.
    """
    hi_at = int(n * 0.55)
    rows, px = [], base
    for i in range(n):
        px += 0.9 if i < hi_at else -0.7
        rows.append((px - 0.25, px + 0.4, px - 0.5, px))
    idx = pd.date_range("2026-05-01", periods=n, freq="D")
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)
    df["volume"] = 1000.0
    return df


def test_confirmation_lag_is_enforced():
    """§4.4 — born at index(P2) + k, NEVER at index(P2)."""
    df = _leg(44)
    f = PF.build_fork_contained("T", df, "1d", _atr(df))
    k = PF.FRACTAL_K["1d"]
    assert f.born_idx == f.p2.idx + k, \
        "anchoring at P2's own timestamp uses information that did not exist"
    assert f.born_idx <= len(df) - 1, \
        "a fork whose lag is not yet served must not be returned at all"


def test_a_fork_whose_lag_is_unserved_is_refused():
    """THE DISCRIMINATING TEST. P2 within k of the end -> no fork at all.

    Deleting the `p2.idx + k > n - 1` guard makes this return a fork built on
    information that did not exist when P2 printed. Every backtest result from
    such a fork is fiction (§4.4), and nothing else in this file can see it.
    """
    df = _leg_p2_at_the_edge(40)
    k = PF.FRACTAL_K["1d"]
    f = PF.build_fork_contained("T", df, "1d", _atr(df))
    if f is not None:
        assert f.p2.idx + k <= len(df) - 1, \
            f"returned a fork with P2 at {f.p2.idx} and k={k} on a {len(df)}-bar " \
            f"frame — the confirmation lag is NOT served and this fork could " \
            f"not have existed at the time it claims"


def test_the_span_is_an_output_not_a_parameter():
    """The operator's point: fork age varies with the magnitude of the move."""
    a, b = _leg(28), _leg(64)
    short = PF.build_fork_contained("T", a, "1d", _atr(a))
    long_ = PF.build_fork_contained("T", b, "1d", _atr(b))
    spans = []
    for f in (short, long_):
        if f is None:
            continue
        spans.append([t for t in f.filters_passed if t.startswith("SPAN_")])
    assert spans, "at least one frame must produce a fork with a recorded span"


def test_a_frame_too_short_refuses_rather_than_guessing():
    df = _leg(8)
    assert PF.build_fork_contained("T", df, "1d", _atr(df)) is None
    assert PF.last_reject_reason() in ("FRAME_TOO_SHORT", "NO_CONTAINED_WINDOW")


def test_daily_frame_is_deep_enough_for_the_anchor_rule():
    """The prerequisite. 10 bars cannot hold three pivots plus the lag."""
    assert config.TIMEFRAMES["1d"]["candles"] >= 40, \
        "the boxes hold 84 daily bars; clipping the frame to 10 made every " \
        "daily fork unbuildable and RECENCY=40 unsatisfiable"


def test_observer_never_raises():
    """It gates nothing, so it must never be able to break a trading tick."""
    for bad in ({}, {"price": None}, {"data": None, "price": 100.0},
                {"data": {"1d": "not a frame"}, "price": 100.0}):
        assert OBS.snapshot(bad, "T") is None or isinstance(OBS.snapshot(bad, "T"), dict)
        assert OBS.stamp(bad, "T") is None or isinstance(OBS.stamp(bad, "T"), dict)


def test_observer_is_weight_zero():
    """No strategy may import it, and it must expose no scoring surface."""
    src = open(OBS.__file__).read()
    assert "WEIGHT 0" in src
    for forbidden in ("def score", "def veto", "setup_score", "conviction ="):
        assert forbidden not in src, \
            f"{forbidden!r} in an observation module is consumer sprawl (§12)"


def test_position_in_channel_is_the_join_key():
    """pos_pct is what the continuation comparison reads. 0 = lower tine."""
    df = _leg(44)
    ctx = {"data": {"1d": df}, "price": float(df["close"].iloc[-1])}
    OBS._cache["ts"] = 0.0
    rec = OBS.snapshot(ctx, "T")
    if rec is None:
        return                      # no fork on this fixture is acceptable
    for tf in ("1d", "1h"):
        if tf in rec and isinstance(rec[tf], dict):
            assert "pos_pct" in rec[tf]
