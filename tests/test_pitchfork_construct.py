"""
tests/test_pitchfork_construct.py — v1.0 — 2026-08-01.

PF.1 CONSTRUCT tests. The overlay's whole bet is that anchor placement is a PURE
FUNCTION of the tape (§4 of docs/WHITEPAPER_pitchfork_overlay.md). §10 names
look-ahead as "the easiest way to fake success", so the confirmation-lag rule
gets more tests here than the geometry does.

What these assert, and why each one exists:

  CONFIRMATION LAG (§4.4)  A fork must not exist before index(P2) + k. A swing low
                           is not knowable until k bars after it prints, and a
                           backtest anchoring at the pivot's own timestamp is
                           fiction. Tested by REPLAYING the frame bar by bar and
                           checking no fork appears early.
  DETERMINISM (§4)         Same bars in, same fork out. This is what makes the
                           persistent object reconstructible from tape rather
                           than a place where state drifts invisibly.
  TIE SAFETY               A plateau yields NO pivot. The shared helper in
                           utils.math_utils uses float equality and emits every
                           tied bar, which breaks alternation — that defect is
                           demonstrated here rather than described, so the
                           filed backlog item has a reproduction.
  FILTERS (§4.3)           Each of significance / separation / structural /
                           recency rejects on its own.
  GEOMETRY (§3.1)          UML passes through P1 and LML through P2 for a bullish
                           fork, mirrored for bearish, and all three rails share
                           one slope.

Run: PYTHONPATH=. pytest tests/test_pitchfork_construct.py -v
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.pitchfork import (  # noqa: E402
    FRACTAL_K, VARIANTS, Fork, _alternating_tail, _pivots, build_all_variants,
    build_fork, pivots_shared,
)

ATR = 2.0


def _seg(a, b, n):
    """Ramp that does NOT repeat its start value, so segment junctions do not
    create tied bars unless a test wants them."""
    return list(np.linspace(a, b, n + 1))[1:]


def _frame(closes, freq="1h"):
    idx = pd.date_range("2026-05-01", periods=len(closes), freq=freq,
                        tz="America/New_York")
    return pd.DataFrame({"open": closes,
                         "high": [c + 0.4 for c in closes],
                         "low": [c - 0.4 for c in closes],
                         "close": closes, "volume": 1}, index=idx)


@pytest.fixture
def bullish():
    """low(12) -> high(32) -> higher low(46). P2 > P0, so structurally bullish."""
    c = [100.0] + _seg(100, 88, 12) + _seg(88, 116, 20) + _seg(116, 97, 14) + _seg(97, 108, 12)
    return _frame(c)


@pytest.fixture
def bearish():
    c = [100.0] + _seg(100, 116, 12) + _seg(116, 88, 20) + _seg(88, 107, 14) + _seg(107, 96, 12)
    return _frame(c)


# ── confirmation lag — the rule that separates validation from fiction ────────
def test_no_fork_exists_before_the_confirmation_bar(bullish):
    """Replay the frame bar by bar. A fork anchored on P2 must not appear until
    k bars after P2 prints — anywhere earlier is look-ahead."""
    full = build_fork("T", bullish, "1h", ATR)
    assert full is not None
    k = FRACTAL_K["1h"]
    expected_birth = full.p2.idx + k

    first_seen = None
    for n in range(len(bullish)):
        f = build_fork("T", bullish, "1h", ATR, now_idx=n)
        if f is not None and f.p2.idx == full.p2.idx and first_seen is None:
            first_seen = n
    assert first_seen is not None, "fork never appeared during replay"
    assert first_seen >= expected_birth, (
        f"fork on P2@{full.p2.idx} appeared at bar {first_seen}, "
        f"before its confirmation bar {expected_birth} — look-ahead")


def test_born_idx_is_computed_not_supplied(bullish):
    f = build_fork("T", bullish, "1h", ATR)
    assert f.born_idx == f.p2.idx + f.k
    assert not f.is_born_by(f.p2.idx), "usable at the pivot's own bar — look-ahead"
    assert not f.is_born_by(f.born_idx - 1)
    assert f.is_born_by(f.born_idx)


def test_pivots_are_not_used_before_they_are_confirmed(bullish):
    """A pivot 1 bar old cannot anchor anything when k=3."""
    f = build_fork("T", bullish, "1h", ATR)
    for p in (f.p0, f.p1, f.p2):
        assert p.confirmed_idx == p.idx + p.k


# ── determinism — the property the persistent object rests on ────────────────
def test_same_bars_produce_the_same_fork(bullish):
    a = build_fork("T", bullish, "1h", ATR)
    b = build_fork("T", bullish.copy(), "1h", ATR)
    assert (a.p0, a.p1, a.p2, a.slope, a.born_idx) == (b.p0, b.p1, b.p2, b.slope, b.born_idx)


def test_fork_is_frozen(bullish):
    f = build_fork("T", bullish, "1h", ATR)
    assert isinstance(f, Fork)
    with pytest.raises(Exception):
        f.slope = 99.0


# ── tie safety, and the shared helper's defect, demonstrated ─────────────────
def test_a_plateau_yields_no_pivot():
    """Strict inequality both sides. A flat top has no single turning bar, and
    saying so is more honest than picking one."""
    c = [100.0] + _seg(100, 90, 8) + [95.0] * 5 + _seg(95, 85, 8)
    highs = [x + 0.4 for x in c]
    lows = [x - 0.4 for x in c]
    # indices 9..13 are the five tied bars. Index 8 is the genuine ramp low that
    # precedes them and SHOULD be a pivot — the assertion is about the flat top,
    # not about its shoulder.
    assert c[9:14] == [95.0] * 5, "fixture drifted; the plateau is not where the test thinks"
    flat = [p for p in _pivots(highs, lows, 2, "1h") if 9 <= p.idx <= 13]
    assert not flat, f"plateau produced pivots: {[(p.idx, p.kind) for p in flat]}"


def test_shared_helper_emits_duplicate_pivots_on_a_plateau():
    """REPRODUCTION for the filed defect: utils.math_utils.find_swing_highs tests
    `prices[i] == max(window)`, so every tied bar is a pivot. This is why the
    fork does not consume it. Fix belongs post-freeze — it feeds
    StructureAnalyzer -> structure_sequence -> TRENDING's veto."""
    c = [100.0] * 3 + [90.0] * 3 + [95.0] * 7 + [90.0] * 3 + [100.0] * 3
    shared = pivots_shared([x + 0.4 for x in c], [x - 0.4 for x in c], 2, "1h")
    highs = [p for p in shared if p.kind == "high"]
    assert len(highs) > 1, "expected the float-equality defect to emit duplicates"
    mine = [p for p in _pivots([x + 0.4 for x in c], [x - 0.4 for x in c], 2, "1h")
            if p.kind == "high"]
    assert len(mine) < len(highs), "the fork's definition should not inherit it"


def test_alternating_tail_keeps_the_most_extreme_of_a_run():
    from analysis.pitchfork import Pivot
    run = [Pivot(0, 100.0, "high", 2, "1h"), Pivot(5, 105.0, "high", 2, "1h"),
           Pivot(10, 90.0, "low", 2, "1h")]
    alt = _alternating_tail(run)
    assert [p.idx for p in alt] == [5, 10]


# ── filters (§4.3) ───────────────────────────────────────────────────────────
def test_significance_filter_rejects_noise(bullish):
    """Same structure, ATR raised so the legs no longer clear S*ATR."""
    assert build_fork("T", bullish, "1h", ATR) is not None
    assert build_fork("T", bullish, "1h", atr=100.0) is None


def test_recency_filter_rejects_stale_structure(bullish):
    assert build_fork("T", bullish, "1h", ATR, recency_bars=40) is not None
    assert build_fork("T", bullish, "1h", ATR, recency_bars=1) is None


def test_structural_validity_rejects_a_broken_leg():
    """Bullish needs P2 > P0. Here the second low undercuts the first, so the
    structure is not directional and gets no fork."""
    c = [100.0] + _seg(100, 88, 12) + _seg(88, 116, 20) + _seg(116, 80, 14) + _seg(80, 92, 12)
    f = build_fork("T", _frame(c), "1h", ATR)
    assert f is None or f.direction == "bearish"


def test_non_anchor_timeframe_is_refused(bullish):
    """5m and 1m are execution frames — too noisy to anchor a persistent object."""
    assert build_fork("T", bullish, "5m", ATR) is None
    assert build_fork("T", bullish, "1m", ATR) is None


def test_short_frame_and_bad_atr_return_none(bullish):
    assert build_fork("T", bullish.iloc[:10], "1h", ATR) is None
    assert build_fork("T", bullish, "1h", atr=0.0) is None
    assert build_fork("T", None, "1h", ATR) is None


def test_filters_passed_is_recorded_for_audit(bullish):
    f = build_fork("T", bullish, "1h", ATR)
    assert set(f.filters_passed) == {"structural", "significance", "separation",
                                     "recency", "uniqueness"}


# ── geometry (§3.1) ──────────────────────────────────────────────────────────
def test_bullish_rails_pass_through_their_pivots(bullish):
    f = build_fork("T", bullish, "1h", ATR)
    assert f.direction == "bullish"
    assert f.upper_at(f.p1.idx) == pytest.approx(f.p1.price, abs=1e-9)
    assert f.lower_at(f.p2.idx) == pytest.approx(f.p2.price, abs=1e-9)


def test_bearish_rails_mirror(bearish):
    f = build_fork("T", bearish, "1h", ATR)
    assert f is not None and f.direction == "bearish"
    assert f.upper_at(f.p2.idx) == pytest.approx(f.p2.price, abs=1e-9)
    assert f.lower_at(f.p1.idx) == pytest.approx(f.p1.price, abs=1e-9)


def test_all_three_rails_share_one_slope(bullish):
    f = build_fork("T", bullish, "1h", ATR)
    for a, b in ((0, 10), (10, 40)):
        for rail in (f.median_at, f.upper_at, f.lower_at):
            assert (rail(b) - rail(a)) / (b - a) == pytest.approx(f.slope, abs=1e-9)


def test_channel_width_is_constant(bullish):
    """Parallel rails — width cannot drift with index."""
    f = build_fork("T", bullish, "1h", ATR)
    assert f.channel_width_at(0) == pytest.approx(f.channel_width_at(500), abs=1e-9)


def test_median_is_the_p0_to_midpoint_ray(bullish):
    f = build_fork("T", bullish, "1h", ATR, variant="andrews")
    m_idx = (f.p1.idx + f.p2.idx) / 2.0
    m_price = (f.p1.price + f.p2.price) / 2.0
    assert f.median_at(f.p0.idx) == pytest.approx(f.p0.price, abs=1e-9)
    assert f.median_at(m_idx) == pytest.approx(m_price, abs=1e-9)


# ── variants (§3.2) ──────────────────────────────────────────────────────────
def test_all_variants_build_on_the_same_anchors(bullish):
    forks = build_all_variants("T", bullish, "1h", ATR)
    assert set(forks) == set(VARIANTS)
    anchors = {(f.p0.idx, f.p1.idx, f.p2.idx) for f in forks.values() if f}
    assert len(anchors) == 1, "variants must differ only in the handle transform"


def test_andrews_is_the_steepest(bullish):
    """§3.2's stated reason for defaulting to Modified Schiff — a steep median
    runs away from price and is useless for anchoring condor strikes. Asserted
    here so the default rests on a measurement rather than on the document."""
    forks = build_all_variants("T", bullish, "1h", ATR)
    assert abs(forks["andrews"].slope) > abs(forks["modified_schiff"].slope)
    assert abs(forks["andrews"].slope) > abs(forks["schiff"].slope)


def test_modified_schiff_median_sits_nearer_price(bullish):
    forks = build_all_variants("T", bullish, "1h", ATR)
    last = len(bullish) - 1
    price = float(bullish["close"].iloc[-1])
    assert (abs(forks["modified_schiff"].median_at(last) - price)
            < abs(forks["andrews"].median_at(last) - price))


def test_rail_at_time_maps_through_the_frame(bullish):
    f = build_fork("T", bullish, "1h", ATR)
    last_ts = bullish.index[-1]
    by_time = f.rail_at_time(last_ts, bullish.index)
    by_idx = f.rails_at(len(bullish) - 1)
    assert by_time["median"] == pytest.approx(by_idx["median"], abs=1e-9)


def test_describe_carries_provenance(bullish):
    """A persistent object has to be auditable on what it claims to see."""
    d = build_fork("T", bullish, "1h", ATR).describe()
    for token in ("P0=", "P1=", "P2=", "slope=", "born@", "lag", "filters="):
        assert token in d, d
