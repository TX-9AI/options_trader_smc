"""
tests/test_pitchfork_lifecycle.py — v1.0 — 2026-08-03.

§5 lifecycle tests. The properties here are the ones that make a fork a
PERSISTENT OBJECT rather than an indicator, and every one of them was violated
by the pre-lifecycle code path:

  HOLDS ACROSS BARS      §5.2 — "explicitly not recomputed each bar, each tick,
                         or each session". a2_rail_drift called build_fork per
                         bar and used only non-None returns, which is exactly the
                         per-bar-indicator behaviour §5.2 forbids.
  A TOUCH IS NOT DEATH   §5.2 — tagging the median or a tine is the TRADEABLE
                         EVENT the overlay exists to produce. "A fork that dies
                         when price touches it has inverted its own purpose."
  TREND-SIDE = LIFE      §5.3 — breaking the trend-side tine is ACCELERATION.
                         A bullish fork closing above its UML is understating the
                         move, not wrong. This is the single easiest thing to get
                         backwards: a naive "price left the channel, kill it"
                         rule kills forks on precisely the moves they called
                         correctly. Tested from BOTH directions so an inverted
                         sign cannot pass.
  COUNTER-SIDE = DEATH   §5.3(b) — but only after N consecutive closes beyond it
                         by >= D x ATR. One close is not enough.
  P0 BREAK = DEATH       §5.3(a) — the leg that defined the fork is gone.
  CHURN GUARD            §5.3(c) — supersession needs MATERIALLY different
                         geometry. Without the guard every marginal pivot
                         re-anchors and persistence evaporates, reintroducing the
                         very bug this module fixes.
  DETERMINISTIC          replay() must give byte-identical history on identical
                         bars, or tracker state stops being a cache of something
                         recomputable and starts being load-bearing.

Run: PYTHONPATH=. pytest tests/test_pitchfork_lifecycle.py -v
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.pitchfork_lifecycle import (  # noqa: E402
    ACCELERATION, BORN, INVALIDATED, SUPERSEDED, TOUCH, ForkTracker, replay,
)
from utils.math_utils import atr_series  # noqa: E402

ATR = 2.0


def _seg(a, b, n):
    """Ramp that does not repeat its start value — a repeated junction value is a
    tie, and ties yield no fractal pivot by design."""
    return list(np.linspace(a, b, n + 1))[1:]


def _frame(closes):
    idx = pd.date_range("2026-05-01", periods=len(closes), freq="1h",
                        tz="America/New_York")
    return pd.DataFrame({"open": closes,
                         "high": [c + 0.4 for c in closes],
                         "low": [c - 0.4 for c in closes],
                         "close": closes, "volume": 1}, index=idx)


@pytest.fixture
def bullish():
    """low(12) -> high(32) -> higher low(46), then drift up. P2 > P0 = bullish."""
    c = [100.0] + _seg(100, 88, 12) + _seg(88, 116, 20) + _seg(116, 97, 14) \
        + _seg(97, 108, 12)
    return _frame(c)


def _tracker_with_fork(df, **kw):
    """Step to the first bar carrying an active fork, then hand it back."""
    tr = ForkTracker("T", "1h", **kw)
    for i in range(20, len(df)):
        if tr.step(df, ATR, i) is not None:
            return tr, i
    raise AssertionError("no fork was ever born on this fixture")


# ── persistence (§5.2) — the property the old code path violated ─────────────
def test_fork_holds_across_bars_without_being_rebuilt(bullish):
    tr, born_at = _tracker_with_fork(bullish)
    first = tr.active
    held = 0
    for i in range(born_at + 1, len(bullish)):
        fk = tr.step(bullish, ATR, i)
        if fk is None:
            break
        assert fk is first, "the fork was rebuilt instead of held"
        held += 1
    assert held >= 3, f"held only {held} bars — that is indicator behaviour"


def test_coverage_far_exceeds_the_birth_rate(bullish):
    """The filter audit's 6.8% was BIRTHS/attempts. Coverage is what matters, and
    conflating them is what made the fork look starved."""
    a = atr_series(bullish, 14).tolist()
    tr = replay("T", bullish, "1h", a)
    births = sum(1 for e in tr.events if e.kind == BORN)
    cov = tr.coverage(len(bullish))
    birth_rate = births / len(bullish)
    assert cov > birth_rate * 5, (
        f"coverage {cov:.1%} vs birth rate {birth_rate:.1%} — lifecycle is not "
        f"holding the fork")


# ── a touch is NOT invalidation (§5.2) ───────────────────────────────────────
@pytest.fixture
def touching():
    """A longer frame that actually interacts with its own rails — a trend, a
    pullback, a second leg and a break. The plain `bullish` fixture never touches
    inside the stepped range, so using it here would let the test pass
    vacuously."""
    c = ([100.0] + _seg(100, 88, 12) + _seg(88, 116, 20) + _seg(116, 97, 14)
         + _seg(97, 108, 12) + _seg(108, 120, 15) + _seg(120, 86, 18))
    return _frame(c)


def test_touching_a_rail_does_not_kill_the_fork(touching):
    a = atr_series(touching, 14).tolist()
    tr = replay("T", touching, "1h", a)
    touches = [e for e in tr.events if e.kind == TOUCH]
    assert touches, "fixture never touched a rail; the test would prove nothing"
    kills = {e.idx for e in tr.events if e.kind == INVALIDATED}
    for t in touches:
        if t.idx in kills:
            ev = [e for e in tr.events
                  if e.kind == INVALIDATED and e.idx == t.idx][0]
            assert ("structural" in ev.reason or "adverse" in ev.reason), (
                f"a bare touch invalidated at bar {t.idx}: {ev.reason}")


# ── the acceleration asymmetry (§5.3) — tested from both sides ───────────────
def test_breaking_the_trend_side_tine_is_acceleration_not_death(bullish):
    """A bullish fork closing ABOVE its UML is understating the move. Killing it
    there would kill forks on exactly the moves they got right."""
    tr, born_at = _tracker_with_fork(bullish)
    fk = tr.active
    assert fk.direction == "bullish"
    df = bullish.copy()
    # drive the close far above the upper rail for several bars
    for i in range(born_at + 1, min(born_at + 5, len(df))):
        above = fk.upper_at(i) + 5.0
        df.iloc[i, df.columns.get_loc("close")] = above
        df.iloc[i, df.columns.get_loc("high")] = above + 0.4
    for i in range(born_at + 1, min(born_at + 5, len(df))):
        tr.step(df, ATR, i)
    assert tr.active is not None, "fork was killed by a TREND-side break"
    assert any(e.kind == ACCELERATION for e in tr.events), \
        "trend-side break was not flagged as acceleration"


def test_breaking_the_counter_side_tine_does_kill_it(bullish):
    """Same geometry, opposite rail — this one must be fatal, or the asymmetry is
    just 'never invalidate'."""
    tr, born_at = _tracker_with_fork(bullish)
    fk = tr.active
    df = bullish.copy()
    for i in range(born_at + 1, min(born_at + 4, len(df))):
        below = fk.lower_at(i) - (0.25 * ATR) - 5.0
        df.iloc[i, df.columns.get_loc("close")] = below
        df.iloc[i, df.columns.get_loc("low")] = below - 0.4
    for i in range(born_at + 1, min(born_at + 4, len(df))):
        tr.step(df, ATR, i)
    assert tr.active is None, "counter-side break did not invalidate"
    assert any(e.kind == INVALIDATED and "adverse" in e.reason for e in tr.events)


def test_one_adverse_close_is_not_enough(bullish):
    """N=2. A single close beyond the counter tine must not kill it, or noise
    ends every fork."""
    tr, born_at = _tracker_with_fork(bullish)
    fk = tr.active
    df = bullish.copy()
    i = born_at + 1
    below = fk.lower_at(i) - (0.25 * ATR) - 5.0
    df.iloc[i, df.columns.get_loc("close")] = below
    tr.step(df, ATR, i)
    assert tr.active is not None, "a single adverse close killed the fork"


# ── structural break (§5.3a) ─────────────────────────────────────────────────
def test_a_retired_triple_cannot_re_birth(bullish):
    """§5.1 — birth is at P2 CONFIRMATION. Without this, build_fork hands back the
    same qualifying triple on the next bar and every invalidation is a no-op."""
    tr, born_at = _tracker_with_fork(bullish)
    spent = tr.active.p2.idx
    df = bullish.copy()
    i = born_at + 1
    df.iloc[i, df.columns.get_loc("close")] = tr.active.p0.price - 1.0
    tr.step(df, ATR, i)
    assert tr.active is None, "fork reincarnated on the bar it was killed"
    for j in range(i + 1, min(i + 6, len(df))):
        tr.step(df, ATR, j)
        assert tr.active is None or tr.active.p2.idx > spent, \
            "the spent triple came back"


def test_close_beyond_p0_kills_it_immediately(bullish):
    tr, born_at = _tracker_with_fork(bullish)
    fk = tr.active
    df = bullish.copy()
    i = born_at + 1
    df.iloc[i, df.columns.get_loc("close")] = fk.p0.price - 1.0
    tr.step(df, ATR, i)
    assert tr.active is None, "P0 violation did not invalidate"
    ev = [e for e in tr.events if e.kind == INVALIDATED][-1]
    assert "structural" in ev.reason


# ── supersession churn guard (§5.3c) ─────────────────────────────────────────
def test_supersession_requires_materially_different_geometry(bullish):
    tr, born_at = _tracker_with_fork(bullish)
    before = tr.active
    for i in range(born_at + 1, len(bullish)):
        tr.step(bullish, ATR, i)
        if tr.active is None:
            break
    swaps = [e for e in tr.events if e.kind == SUPERSEDED]
    # on a smooth fixture nothing should churn; if it did, it must have been for
    # a materially different reason rather than every marginal pivot
    assert len(swaps) <= 1, f"{len(swaps)} supersessions — the churn guard is not holding"
    if not swaps:
        assert before is not None


# ── determinism ──────────────────────────────────────────────────────────────
def test_coverage_counts_supersession_chains(touching):
    """A supersession emits SUPERSEDED then BORN with no INVALIDATED between. If
    coverage only pairs BORN→INVALIDATED, every held bar before the final fork is
    silently dropped — and coverage can come out BELOW the birth rate, which is
    arithmetically impossible."""
    a = atr_series(touching, 14).tolist()
    tr = replay("T", touching, "1h", a)
    births = sum(1 for e in tr.events if e.kind == BORN)
    supers = sum(1 for e in tr.events if e.kind == SUPERSEDED)
    if supers == 0:
        pytest.skip("fixture produced no supersession; nothing to test here")
    cov = tr.coverage(len(touching))
    assert cov >= births / len(touching), (
        f"coverage {cov:.1%} is below the birth rate {births/len(touching):.1%} — "
        f"supersession spans are being dropped")


def test_replay_is_deterministic(bullish):
    a = atr_series(bullish, 14).tolist()
    one = replay("T", bullish, "1h", a)
    two = replay("T", bullish.copy(), "1h", list(a))
    assert [(e.kind, e.idx, e.reason) for e in one.events] == \
           [(e.kind, e.idx, e.reason) for e in two.events]


def test_pivot_mode_ships_off(bullish):
    """§5.3(b)'s written form stays the default so the two are measurable side by
    side. Switching it is a separate, deliberate act."""
    tr = ForkTracker("T", "1h")
    assert tr.adverse_mode == "closes"


@pytest.fixture
def flat_tail():
    """The bullish structure with a LONG stationary tail. The plain fixture has
    only 9 bars after birth — nowhere near enough for the rail to climb through
    price, so a test built on it proves nothing either way. Measured: the rail
    needs ~43 bars here, because price sits well ABOVE the lower rail at birth
    rather than on it."""
    c = ([100.0] + _seg(100, 88, 12) + _seg(88, 116, 20) + _seg(116, 97, 14)
         + _seg(97, 108, 12) + [108.0] * 40)
    return _frame(c)


def _run(df, **kw):
    tr = ForkTracker("T", "1h", **kw)
    born = None
    for i in range(20, len(df)):
        tr.step(df, ATR, i)
        if born is None and tr.active is not None:
            born = i
    deaths = [e for e in tr.events if e.kind == INVALIDATED]
    return tr, born, deaths


def test_closes_mode_dies_on_stationary_price(flat_tail):
    """§5.3(b) as written is TIME-DEPENDENT: all three rails share the fork's
    slope, so a bullish fork's LOWER rail rises through stationary price. This is
    the defect, demonstrated — zero adverse movement, fork still dies."""
    _, born, deaths = _run(flat_tail)
    assert deaths, "closes mode held through a stationary tail; fixture too short?"
    assert "adverse" in deaths[0].reason
    assert deaths[0].idx - born > 20, (
        "died too fast to attribute to the rail climbing — check the fixture is "
        "actually stationary")


def test_pivot_mode_survives_stationary_price(flat_tail):
    """Same tape, pivot form. No confirmed pivot forms outside the channel when
    price merely stands still, so the fork holds — which is the whole point."""
    tr, _, deaths = _run(flat_tail, adverse_mode="pivot")
    assert not deaths, f"pivot mode invalidated on flat price: {deaths[0].reason}"
    assert tr.active is not None


def test_staleness_ships_off(bullish):
    """§5.3(d) says measure before enabling. It must be implemented AND off."""
    from analysis import pitchfork_lifecycle as pl
    assert pl.STALE_ENABLED is False
    tr = ForkTracker("T", "1h")
    assert tr.stale_enabled is False


def test_staleness_fires_when_explicitly_enabled(bullish):
    """Off by default is only defensible if the mechanism actually works when
    turned on — otherwise 'ships off' is hiding a stub."""
    a = atr_series(bullish, 14).tolist()
    tr = replay("T", bullish, "1h", a, stale_enabled=True, stale_bars=2)
    assert any(e.kind == INVALIDATED and "stale" in e.reason for e in tr.events), \
        "staleness never fired even with stale_bars=2"


def test_at_most_one_active_fork(bullish):
    """§6: at most one active fork per (symbol, timeframe)."""
    a = atr_series(bullish, 14).tolist()
    tr = replay("T", bullish, "1h", a)
    assert not isinstance(tr.active, (list, tuple))


def test_events_carry_provenance(bullish):
    """A fork that vanished with no INVALIDATED event would be unauditable — the
    event log IS the provenance."""
    a = atr_series(bullish, 14).tolist()
    tr = replay("T", bullish, "1h", a)
    for e in tr.events:
        assert e.kind and e.reason and e.symbol and e.timeframe
        assert isinstance(e.idx, int)
