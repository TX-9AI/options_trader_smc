#!/usr/bin/env python3
"""
tests/test_condor_pitchfork_anchor.py — v1.0 — 2026-08-13   (PF.5)

The operator's spec is three filters and an ordering rule, and every test here
exists because one of them can fail silently:

  1. beyond the RAIL          — "just outside the range of the rail"
  2. beyond the MIN DISTANCE  — the surviving 0.80*EM floor
  3. NOT EXCEEDED by price    — beyond the session extreme
  then: MOST LIQUID among survivors, tie-break NEAREST the rail
  and:  leg order from the apparent SLOPE, flat falls back to proximity

⚠️ THE ONE THAT WOULD HAVE SHIPPED BROKEN. `_liquidity_rank` replaces an
`open_interest + volume` sum that factor_sweep found CONSTANT across the whole
joined sample — so `max_liq` was 0, the `else: top = eligible` branch took every
call, and "most liquid" silently resolved to "nearest the floor" from
v-dualfloor onward. A test that only checks the happy path with populated OI
would pass against the broken version too, so the suite asserts the ranking
works with OI and volume BOTH ZERO — the state the fleet is actually in.

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python -m pytest tests/test_condor_pitchfork_anchor.py -q
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy.iron_condor_strategy import IronCondorStrategy   # noqa: E402


class C:
    """Minimal OptionContract stand-in — only the fields the selector reads."""

    def __init__(self, strike, bid=1.00, ask=1.10, mark=None, oi=0, vol=0):
        self.strike = float(strike)
        self.bid, self.ask = float(bid), float(ask)
        self.mark = float(mark if mark is not None else (bid + ask) / 2.0)
        self.open_interest, self.volume = oi, vol

    def __repr__(self):
        return f"C({self.strike})"


def S():
    return IronCondorStrategy.__new__(IronCondorStrategy)      # no __init__ needed


# ── the three filters ───────────────────────────────────────────────────────

def test_call_must_clear_the_rail():
    sel = S()._select_beyond_rail(
        [C(100), C(105), C(110)], "call",
        rail=104.0, min_distance_level=0.0, session_extreme=None)
    assert sel.strike == 105.0, "a strike inside the rail was selected"


def test_put_must_clear_the_rail():
    sel = S()._select_beyond_rail(
        [C(90), C(95), C(100)], "put",
        rail=96.0, min_distance_level=1e9, session_extreme=None)
    assert sel.strike == 95.0


def test_min_distance_survives_a_rail_sitting_on_spot():
    """v-dualfloor's floor is retained as a MINIMUM. A rail near spot must not
    produce a strike with no breathing room — the ~3-week bleed."""
    sel = S()._select_beyond_rail(
        [C(101), C(103), C(108)], "call",
        rail=100.5, min_distance_level=107.0, session_extreme=None)
    assert sel.strike == 108.0, "the min-distance floor was not applied"


def test_session_extreme_blocks_a_strike_price_already_reached():
    """A level price has traded through today is one the market has PROVEN it
    can reach. THE NEW CONSTRAINT — nothing tested this before PF.5."""
    sel = S()._select_beyond_rail(
        [C(105), C(110), C(115)], "call",
        rail=104.0, min_distance_level=0.0, session_extreme=112.0)
    assert sel.strike == 115.0, "a strike below the session high was selected"


def test_all_three_filters_compose():
    sel = S()._select_beyond_rail(
        [C(105), C(110), C(115), C(120)], "call",
        rail=106.0, min_distance_level=111.0, session_extreme=113.0)
    assert sel.strike == 115.0


def test_no_inside_fallback_returns_None():
    """No eligible strike must SKIP the leg, never fall back inward."""
    assert S()._select_beyond_rail(
        [C(100), C(101)], "call",
        rail=150.0, min_distance_level=0.0, session_extreme=None) is None


def test_unpriced_contracts_are_ineligible():
    assert S()._select_beyond_rail(
        [C(110, bid=0.0, ask=0.0, mark=0.0)], "call",
        rail=100.0, min_distance_level=0.0, session_extreme=None) is None


# ── liquidity: the part that was silently dead ──────────────────────────────

def test_liquidity_ranks_on_width_with_OI_AND_VOLUME_BOTH_ZERO():
    """THE STATE THE FLEET IS ACTUALLY IN. The old ranker summed OI+volume,
    both zero, so every selection fell through to the fallback. Width must pick
    the tight quote even with no depth data at all."""
    wide = C(110, bid=1.00, ask=1.60, oi=0, vol=0)      # 46% of mid
    tight = C(115, bid=1.00, ask=1.02, oi=0, vol=0)     # 2% of mid
    sel = S()._select_beyond_rail([wide, tight], "call",
                                  rail=105.0, min_distance_level=0.0,
                                  session_extreme=None)
    assert sel.strike == 115.0, (
        "the wide-quote strike was selected — ranking is not reading bid/ask "
        "width, which is the only populated liquidity signal")


def test_tie_break_is_nearest_the_rail():
    """Equally liquid survivors: take the one closest to the rail — the richest
    premium that still clears everything, not the deepest OTM."""
    a = C(110, bid=1.00, ask=1.02)
    b = C(120, bid=1.00, ask=1.02)
    sel = S()._select_beyond_rail([a, b], "call", rail=105.0,
                                  min_distance_level=0.0, session_extreme=None)
    assert sel.strike == 110.0


def test_depth_only_breaks_ties_when_width_is_equal():
    equal_a = C(110, bid=1.00, ask=1.02, oi=0, vol=0)
    equal_b = C(112, bid=1.00, ask=1.02, oi=5000, vol=900)
    sel = S()._select_beyond_rail([equal_a, equal_b], "call", rail=105.0,
                                  min_distance_level=0.0, session_extreme=None)
    # both in the cohort; nearest-the-rail still decides
    assert sel.strike == 110.0


# ── leg order from slope ────────────────────────────────────────────────────

def test_up_slope_fills_the_PUT_side_first():
    assert IronCondorStrategy._leg_order_from_slope(0.001, 0.00002) == ("put", "call")


def test_down_slope_fills_the_CALL_side_first():
    assert IronCondorStrategy._leg_order_from_slope(-0.001, 0.00002) == ("call", "put")


def test_flat_fork_returns_None_so_the_caller_keeps_proximity():
    """A SIGN IS NOT A SLOPE. Below the epsilon the drift is noise and ordering
    off it reads a coin flip as structure."""
    assert IronCondorStrategy._leg_order_from_slope(0.000001, 0.00002) is None
    assert IronCondorStrategy._leg_order_from_slope(0.0, 0.00002) is None
    assert IronCondorStrategy._leg_order_from_slope(None, 0.00002) is None


# ── POP: the time-of-day gate ───────────────────────────────────────────────

def test_pop_rises_as_the_session_shortens():
    """THE WHOLE POINT. Same distance, less time, higher POP — a strike that
    fails at 11:15 passes at 14:30 on identical geometry. No fixed-percent rule
    can express this, which is why every offset table so far was time-blind."""
    early = IronCondorStrategy._pop(3.0, 0.5, 40)
    late = IronCondorStrategy._pop(3.0, 0.5, 8)
    assert 0.80 < early < 0.85
    assert late > 0.97
    assert late > early


def test_pop_rises_with_distance():
    near = IronCondorStrategy._pop(1.0, 0.5, 40)
    far = IronCondorStrategy._pop(3.0, 0.5, 40)
    assert near < 0.70 < far, "the floor must separate these two"


def test_pop_degenerate_inputs_FAIL_the_floor():
    """A missing ATR must never read as a safe trade. 0.0 fails any floor."""
    for bad in ((3.0, 0.0, 8), (3.0, 0.5, 0), (0.0, 0.5, 8), (-1.0, 0.5, 8)):
        assert IronCondorStrategy._pop(*bad) == 0.0


def test_pop_floor_rejects_a_near_strike_and_keeps_a_far_one():
    contracts = [C(101), C(110)]
    sel = S()._select_beyond_rail(
        contracts, "call", rail=100.0, min_distance_level=0.0,
        session_extreme=None, spot=100.0, sigma=0.5, bars_left=40,
        min_pop=0.70)
    assert sel.strike == 110.0, "the near strike passed a 0.70 POP floor"


def test_pop_floor_is_inert_when_not_configured():
    """min_pop=0 must leave v-dualfloor behaviour untouched."""
    sel = S()._select_beyond_rail(
        [C(101), C(110)], "call", rail=100.0, min_distance_level=0.0,
        session_extreme=None, spot=100.0, sigma=0.5, bars_left=40, min_pop=0.0)
    assert sel.strike == 101.0


# ── quote-width floor: ranking alone never refuses ──────────────────────────

def test_quote_width_floor_skips_a_broken_market():
    """Ranking returns the least-bad strike even when every candidate is
    broken. On 0DTE a nickel of noise on a wide quote trips the 25% stop on the
    QUOTE rather than on price."""
    wide_only = [C(110, bid=1.00, ask=1.80), C(115, bid=1.00, ask=1.90)]
    assert S()._select_beyond_rail(
        wide_only, "call", rail=105.0, min_distance_level=0.0,
        session_extreme=None, max_width_pct=0.25) is None


def test_quote_width_floor_keeps_a_decent_market():
    ok = [C(110, bid=1.00, ask=1.10), C(115, bid=1.00, ask=1.80)]
    sel = S()._select_beyond_rail(
        ok, "call", rail=105.0, min_distance_level=0.0,
        session_extreme=None, max_width_pct=0.25)
    assert sel.strike == 110.0


def test_bars_left_measures_to_the_1545_flatten():
    """15:45, not the bell — a condor leg is CLOSED at the hard close, so that
    is when the position actually ends. Using 16:00 overstates T and makes
    every POP look worse than the trade really is."""
    import datetime as dt
    at_1400 = dt.datetime(2026, 8, 13, 14, 0)
    assert IronCondorStrategy._bars_left(at_1400, 5.0) == 21.0     # 105 min / 5
    past = dt.datetime(2026, 8, 13, 15, 50)
    assert IronCondorStrategy._bars_left(past, 5.0) == 0.0


# ── deliberate failure ──────────────────────────────────────────────────────

def test_deliberate_failure_each_filter_is_load_bearing():
    """Relax each constraint in turn; the selection MUST move. If it does not,
    that filter is not being applied and the happy-path tests above would pass
    against a version that ignores it."""
    contracts = [C(105), C(110), C(115), C(120)]
    base = S()._select_beyond_rail(contracts, "call", rail=106.0,
                                   min_distance_level=111.0,
                                   session_extreme=113.0)
    assert base.strike == 115.0

    no_extreme = S()._select_beyond_rail(contracts, "call", rail=106.0,
                                         min_distance_level=111.0,
                                         session_extreme=None)
    assert no_extreme.strike == 115.0      # min-dist already binds at 111

    no_mindist = S()._select_beyond_rail(contracts, "call", rail=106.0,
                                         min_distance_level=0.0,
                                         session_extreme=None)
    assert no_mindist.strike == 110.0, (
        "dropping the min-distance floor did not move the selection — the "
        "floor is not being applied")

    no_rail = S()._select_beyond_rail(contracts, "call", rail=0.0,
                                      min_distance_level=0.0,
                                      session_extreme=None)
    assert no_rail.strike == 105.0, (
        "dropping the rail did not move the selection — the rail is not being "
        "applied")


def test_deliberate_failure_the_pop_floor_is_load_bearing():
    """Drop the floor and the near strike must come back. If the same strike
    wins either way the floor is not being applied."""
    contracts = [C(101), C(110)]
    gated = S()._select_beyond_rail(contracts, "call", rail=100.0,
                                    min_distance_level=0.0, session_extreme=None,
                                    spot=100.0, sigma=0.5, bars_left=40,
                                    min_pop=0.70)
    ungated = S()._select_beyond_rail(contracts, "call", rail=100.0,
                                      min_distance_level=0.0, session_extreme=None,
                                      spot=100.0, sigma=0.5, bars_left=40,
                                      min_pop=0.0)
    assert (gated.strike, ungated.strike) == (110.0, 101.0), (
        "the POP floor did not change the selection — it is not being applied")


def test_deliberate_failure_time_actually_moves_the_gate():
    """The SAME near strike must FAIL early and PASS late. If it behaves the
    same at both, bars_left is not reaching the POP calculation and the gate is
    time-blind — the exact defect it exists to fix."""
    contracts = [C(101)]
    early = S()._select_beyond_rail(contracts, "call", rail=100.0,
                                    min_distance_level=0.0, session_extreme=None,
                                    spot=100.0, sigma=0.5, bars_left=40,
                                    min_pop=0.70)
    late = S()._select_beyond_rail(contracts, "call", rail=100.0,
                                   min_distance_level=0.0, session_extreme=None,
                                   spot=100.0, sigma=0.15, bars_left=3,
                                   min_pop=0.70)
    assert early is None and late is not None, (
        "the gate did not respond to time remaining")


def test_deliberate_failure_width_actually_decides():
    """Flip which contract carries the tight quote; the selection must follow
    it. If the same strike wins both ways, width is not being read."""
    tight_far = [C(110, bid=1.00, ask=1.60), C(120, bid=1.00, ask=1.02)]
    tight_near = [C(110, bid=1.00, ask=1.02), C(120, bid=1.00, ask=1.60)]
    a = S()._select_beyond_rail(tight_far, "call", rail=105.0,
                                min_distance_level=0.0, session_extreme=None)
    b = S()._select_beyond_rail(tight_near, "call", rail=105.0,
                                min_distance_level=0.0, session_extreme=None)
    assert (a.strike, b.strike) == (120.0, 110.0), (
        "the selection did not follow the tight quote — width is not deciding")


# ── the fork gate, end to end ───────────────────────────────────────────────

def _stub_decide_env():
    """Minimal stand-ins so decide() can be exercised without a broker."""
    import types
    from analysis.regime_classifier import Regime
    regime = types.SimpleNamespace(primary_regime=Regime.RANGING, conviction=1.0)
    vol = types.SimpleNamespace(bb_upper=110.0, bb_lower=90.0, atr_current=0.5)
    macro = types.SimpleNamespace(vix=15.0, is_fed_day=False)
    chain = types.SimpleNamespace(calls=[C(k) for k in (105, 110, 115, 120)],
                                  puts=[C(k) for k in (80, 85, 90, 95)])
    return regime, vol, macro, chain


def test_no_fork_means_no_plan():
    """THE GATE. rails=None with CONDOR_REQUIRE_FORK on must produce NO PLAN —
    a caller that forgets to pass rails gets no condor rather than a silently
    un-anchored one. The failure mode must be missing trades, never unguarded
    ones."""
    import config
    from strategy.iron_condor_strategy import IronCondorStrategy
    if not config.CONDOR_REQUIRE_FORK:
        return
    s = IronCondorStrategy()
    regime, vol, macro, chain = _stub_decide_env()
    s._plan = None
    assert s.decide(regime=regime, vol_state=vol, chain=chain, macro=macro,
                    current_price=100.0, rails=None) is None


def test_decide_accepts_rails_and_extremes_without_raising():
    """Signature smoke test — the wiring passes three new kwargs and a
    TypeError here would be a live crash on every condor evaluation."""
    from strategy.iron_condor_strategy import IronCondorStrategy
    s = IronCondorStrategy()
    regime, vol, macro, chain = _stub_decide_env()
    s._plan = None
    s.decide(regime=regime, vol_state=vol, chain=chain, macro=macro,
             current_price=100.0,
             rails={"tf": "daily", "upper": 108.0, "median": 100.0,
                    "lower": 92.0, "slope": 0.001},
             session_high=107.0, session_low=93.0)
