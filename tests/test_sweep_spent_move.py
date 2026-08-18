"""
tests/test_sweep_spent_move.py — v1.0 — 2026-08-08

Pins the operator's spec into `_sweep` (regime_confluence v1.4):
**a SPENT move into a named liquidity pool that gets rejected.**

The pool and the rejection were always scored. "Spent" was only ever inferred
from 5m momentum, and nothing asked WHAT was spent — so a rejection at a named
level in dead air and the same rejection at the end of an extended trending leg
scored identically. Only the second is the trade.

THE TWO THINGS THAT WOULD GO WRONG SILENTLY, and both are guarded here:

1. **THE PLTR REGRESSION.** On 2026-07-27 a lone level-rejection scored 0.62
   while the underlying ran +7.2% on its SMA50 and the fleet bought a put into
   it (-27.8%). `trend_opp` is the fix and it is a SOFT-NECESSARY — multiplicative,
   so full opposition annihilates. Raising sweep's sensitivity without keeping
   that annihilation re-opens the exact loss. `test_pltr_protection_survives` is
   the load-bearing test in this file; nothing else here matters if it fails.

2. **THE ABSENCE ASYMMETRY.** A missing 5m vote used to suppress (`opp_mom` ""
   -> 0.8, near full opposition) AND withhold corroboration (`exh_val` "" ->
   0.0) — one absent input penalised twice. v1.4 stops the SUPPRESSION half and
   deliberately keeps the CORROBORATION half at zero. Absence of evidence must
   not count as evidence against; it must also not count as evidence for. A
   future edit that "tidies" this into symmetry would silently start scoring
   sweeps on unknowns, so both halves are pinned separately.

Deliberate-failure check performed when written: setting `opp_mom[""]` back to
0.8 turns test_absence_no_longer_double_penalises red; giving `exh_val[""]` a
non-zero value turns test_absence_does_not_corroborate red; dropping `trend_opp`
from soft_necessary turns test_pltr_protection_survives red.
"""

import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.regime_confluence import RegimeConfluenceScorer      # noqa: E402


def _liq(named="PDH", reclaimed=True, beyond=0, rej_pct=0.65,
         kind="high_sweep", pool_px=100.0, touches=4, age=1):
    sweep = NS(reclaimed=reclaimed, swept_named_level=named, closes_beyond=beyond,
               rejection_pct=rej_pct, kind=kind, pool_price=pool_px)
    pools = [NS(price=pool_px, touch_count=touches)]
    return NS(recent_sweep=sweep, pools=pools, sweep_age_bars=age)


def _trend(adx=15.0, direction="NEUTRAL", momentum="DECELERATING"):
    return NS(primary_adx=adx, overall_direction=direction,
              primary_momentum=momentum)


def _score(liq=None, trend=None, ambient=None):
    return RegimeConfluenceScorer()._sweep(liq or _liq(), trend or _trend(),
                                           ambient=ambient)


def test_spent_move_scores_higher_than_the_same_rejection_in_dead_air():
    """The operator's spec, stated as a comparison."""
    dead, _ = _score(ambient=0.0)
    spent, bd = _score(ambient=0.9)
    assert spent > dead, \
        "an identical rejection at the end of an extended move must score " \
        "HIGHER than one in dead air — that difference IS the setup"
    assert bd["spent_val"] > 0.0


def test_spent_context_is_encouragement_not_a_requirement():
    """'Permitted and encouraged', per the operator — not gated behind a trend."""
    dead, _ = _score(ambient=0.0)
    assert dead > 0.0, \
        "with the veto triple passed, a sweep must still score without a " \
        "trending ambient — making spent-context multiplicative would be " \
        "NARROWER than what was asked for"


def test_pltr_protection_survives():
    """LOAD-BEARING. 2026-07-27: a put bought into a +7.2% uptrend, -27.8%."""
    opposed = _trend(adx=40.0, direction="BULLISH", momentum="ACCELERATING")
    score, bd = _score(liq=_liq(kind="high_sweep"), trend=opposed, ambient=0.95)
    assert bd["opposed"] is True
    assert bd["trend_opp"] == 0.0, \
        "a SHORT reversal into a strong ACCELERATING uptrend must annihilate"
    assert score == 0.0, \
        "a high ambient score must NEVER rescue a sweep fighting an " \
        "accelerating opposing trend — that is the PLTR loss re-opened"


def test_absence_no_longer_double_penalises():
    """A missing 5m vote must not suppress harder than FLAT."""
    flat = _score(trend=_trend(adx=40.0, direction="BULLISH", momentum="FLAT"),
                  liq=_liq(kind="high_sweep"))[1]
    empty = _score(trend=_trend(adx=40.0, direction="BULLISH", momentum=""),
                   liq=_liq(kind="high_sweep"))[1]
    assert empty["opp_mom"] == flat["opp_mom"], \
        "'' must suppress no harder than FLAT — it was 0.8 against FLAT's " \
        "0.6, purely because an input was missing"


def test_absence_does_not_corroborate():
    """The other half of the asymmetry, and it is deliberate."""
    _, bd = _score(trend=_trend(momentum=""))
    assert bd["exh_val"] == 0.0, \
        "absence must not count as evidence FOR exhaustion either — if we " \
        "cannot see that the move is spent, we have no evidence that it is"


def test_named_level_is_still_required():
    """The operator's spec is the veto triple; permissiveness must not reach it."""
    score, _ = _score(liq=_liq(named=""), ambient=0.9)
    assert score == 0.0, "no named pool -> no sweep, whatever else is true"
    score, _ = _score(liq=_liq(reclaimed=False), ambient=0.9)
    assert score == 0.0, "no rejection -> no sweep, whatever else is true"


def test_ambient_defaults_to_neutral_when_absent():
    """Callers that predate the signature change must not crash or be punished."""
    s_none, bd = _score(ambient=None)
    assert s_none > 0.0 and bd["spent_val"] == 0.0
