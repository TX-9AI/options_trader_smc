"""
tests/test_readiness_sweep_approach.py — v1.0 — 2026-08-10

Pins the sweep readiness track's APPROACH factor and the removal of its dead
label veto (trade_readiness v1.7).

TWO THINGS SHIPPED HERE AND THE FIRST IS A BUG WE CAUSED:

1. **THE TRACK WAS SCORING A PERMANENT ZERO.** `_sweep` carried
   `hard_vetoes=[is_sweep]`, requiring the committed label to BE
   SWEEP_REVERSAL. RGM.3 (baked 2026-08-08) removed SWEEP from the argmax, so
   that label is never emitted and the whole track died — the same category
   error as the dispatch gate, one layer down, created by our own fix two days
   earlier. Readiness ARMS a track before its event; gating it on the event's
   own label made arming impossible by construction. A proximity term added on
   top would have multiplied into a hard zero and changed nothing.

2. **APPROACH = proximity x level quality**, distance measured as price delta
   normalised by ATR (operator's spec), with a modest bonus for London levels.

THE FAILURES GUARDED, all of which render cleanly:
  - **A RESURRECTED HARD VETO.** If anything ever puts a label gate back into
    hard_vetoes, this track silently returns to zero and nothing else breaks.
  - **PROXIMITY INVERTED.** Scoring FAR levels higher than near ones is a sign
    flip that still produces a plausible 0..1 number.
  - **BOUNDS DRIFT.** NEAR/FAR were fitted from the shadow observer (14% within
    0.5 ATR, median 2.32). An earlier draft used 0.15/1.20, which put the
    MEDIAN TICK at zero and left the term dead on ~3/4 of the session. The
    values are pinned so a future "tidy" cannot quietly re-break it.
  - **LONDON AS A MULTIPLIER RATHER THAN A BONUS.** 61.3% is a frequency of
    PROXIMITY, not of profitability. If this ever grows into a dominant term it
    encodes "where price is" as "where the edge is".

Deliberate-failure check performed when written: restoring hard_vetoes=[is_sweep]
turns test_track_scores_without_the_sweep_label red; flipping the proximity ramp
turns test_nearer_scores_higher red.
"""

import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analysis.trade_readiness as TR                            # noqa: E402
from analysis.trade_readiness import TradeReadinessEngine        # noqa: E402


def _ctx(price=100.0, atr=1.0, pools=(), sweep_kind=None, mom="DECELERATING"):
    vol = NS(atr_current=atr, bb_middle=100.0, bb_upper=102.0, bb_lower=98.0,
             bb_width_pct=0.45, bb_state="NORMAL", vwap=99.5,
             price_vs_vwap="ABOVE")
    sweep = NS(kind=sweep_kind) if sweep_kind else None
    liq = NS(recent_sweep=sweep, sweep_age_bars=1,
             pools=[NS(price=p, touch_count=t, name=n) for p, t, n in pools])
    return {"price": price, "vol": vol, "liq_map": liq,
            "trend": NS(primary_momentum=mom, primary_adx=20.0,
                        overall_direction="NEUTRAL")}


def _score(**kw):
    eng = TradeReadinessEngine(emit=lambda *a, **k: None)
    regime = NS(primary_regime=kw.pop("label", "TRENDING_BULL"),
                conviction=kw.pop("conv", 0.8))
    return eng._sweep(_ctx(**kw), regime)


def test_track_scores_without_the_sweep_label():
    """THE BUG WE CAUSED. RGM.3 stopped emitting SWEEP_REVERSAL entirely."""
    r, bd = _score(label="TRENDING_BULL",
                   pools=[(100.4, 4, "London High")])
    assert r > 0.0, \
        "the readiness track must arm WITHOUT the SWEEP_REVERSAL label — " \
        "RGM.3 removed it from the argmax, so a label veto is a permanent zero"


def test_nearer_scores_higher():
    near, _ = _score(price=100.0, atr=1.0, pools=[(100.3, 4, "London High")])
    far,  _ = _score(price=100.0, atr=1.0, pools=[(105.0, 4, "London High")])
    assert near > far, "proximity must RISE as price approaches the level"


def test_a_well_tested_level_outranks_a_virgin_one():
    held,   _ = _score(pools=[(100.3, 5, "PDH")])
    virgin, _ = _score(pools=[(100.3, 1, "PDH")])
    assert held > virgin, \
        "a level that has held against multiple tests must score higher"


def test_bounds_are_the_shadow_fitted_ones():
    """0.15/1.20 put the MEDIAN tick (2.32 ATR) at zero — the term died."""
    assert TR.TR_SWEEP_PROX_NEAR == 0.50
    assert TR.TR_SWEEP_PROX_FAR == 2.32, \
        "FAR must reach the shadow-observed MEDIAN distance, or this factor " \
        "is dead on roughly three-quarters of the session"


def test_london_is_a_bonus_not_a_multiplier():
    assert 1.0 < TR.TR_SWEEP_LONDON_MULT <= 1.25, \
        "61.3% is a frequency of PROXIMITY, not of profitability — a dominant " \
        "weight would encode 'where price is' as 'where the edge is'"
    lon, _ = _score(pools=[(100.3, 4, "London High")])
    pdh, _ = _score(pools=[(100.3, 4, "PDH")])
    assert lon >= pdh


def test_the_level_name_reaches_the_journal():
    """So 'which levels get swept' stops being a question about recollection."""
    _, bd = _score(pools=[(100.3, 4, "London Low")])
    assert bd["appr_name"] == "London Low"
    assert bd["appr_dist_atr"] is not None
    assert bd["appr_touches"] == 4


def test_no_pools_or_no_atr_yields_zero_not_a_crash():
    r1, bd1 = _score(pools=[])
    assert bd1["appr_val"] == 0.0 and bd1["appr_name"] is None
    r2, bd2 = _score(atr=0.0, pools=[(100.3, 4, "PDH")])
    assert bd2["appr_val"] == 0.0, \
        "without ATR the distance cannot be normalised — no score, no guess"


def test_approach_is_capped_at_one():
    _, bd = _score(price=100.0, atr=1.0, pools=[(100.0, 9, "London High")])
    assert bd["appr_val"] <= 1.0, \
        "the London bonus must not push a corroborator above unity"
