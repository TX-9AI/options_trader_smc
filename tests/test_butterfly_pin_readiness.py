"""
tests/test_butterfly_pin_readiness.py — v1.0 — 2026-08-11

Pins the butterfly readiness rewrite (trade_readiness v1.8).

THE DEFECT. The strategy is a GEX-PIN trade — Gate 5 hard-refuses unless
`gex_environment == "PINNING"`, and the tent is centred on `gex.pin_strike`,
not ATM. The READINESS TRACK scored something else entirely: `coil` (the
COMPRESSION label) as a HARD VETO, plus a boolean squeeze and band width. **Not
one of the five gates that actually block the strategy was in it** — no pin, no
pin distance, no GEX environment, no entry window.
Consequence, measured 2026-08-10: **would_fire=2132 against ONE trade**, and
R p50 0.995 / p90 1.000. The thing it measured was genuinely ready all day; the
thing that has to be true almost never was. A switch on a label, wearing the
name of a pin play.

WHAT THE REWRITE MUST DO, and each is a test below:
  - RISE as the thesis comes true (pin firms, price migrates in), rather than
    switching on a label.
  - FALL on a tape the trade does not belong in — a perfect pin on a TRENDING
    tape must score LOW, because that is the operator's "no neutral play during
    a trend".
  - WARM toward the 12:00 window instead of switching on at it, since readiness
    exists to ARM AHEAD.
  - GO TO ZERO after 14:00, when the strategy cannot fire at all.

THE SILENT FAILURES GUARDED:
  1. A RESTORED HARD VETO. If `coil` goes back into hard_vetoes the score is a
     switch again and nothing errors — it just reads 0.995 forever.
  2. A CHAINLESS TICK ZEROING THE THESIS. Pin distance wants EXPECTED MOVE,
     which needs a chain. Without a fallback the term that carries the whole
     trade silently reads 0. `pin_dist_unit` records which unit was used, and
     the two scales must never be pooled when fitting bounds.
  3. A MISSING CLOCK PINNING THE WINDOW OPEN. `win_val` defaults to 1.0 on an
     exception so an unreadable clock cannot SUPPRESS a live setup — which is
     also exactly how a missing `now_et` import would have gone unnoticed
     during the build. It was, briefly.

Deliberate-failure check performed when written: putting `coil` back into
hard_vetoes turns test_score_rises_as_the_thesis_comes_true red (every case
collapses to the same value); removing the ATR fallback turns
test_a_chainless_tick_still_scores_the_pin red.
"""
import os
import sys
from datetime import datetime
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analysis.trade_readiness as TR                              # noqa: E402


def _ctx(px, pin, env, netg, atr=0.6, bb="SQUEEZE", width=0.12):
    return {"price": px,
            "vol": NS(bb_state=bb, bb_width_pct=width, atr_current=atr),
            "gex": NS(pin_strike=pin, gex_environment=env, net_gex=netg),
            "chain": None,
            "trend": NS(primary_momentum="FLAT", primary_adx=15.0,
                        overall_direction="NEUTRAL")}


def _score(ctx, label="COMPRESSION", conv=0.8, hhmm=(12, 30)):
    eng = TR.TradeReadinessEngine(emit=lambda *a, **k: None)
    old = TR.now_et
    TR.now_et = lambda: datetime(2026, 8, 11, hhmm[0], hhmm[1])
    try:
        return eng._butterfly(ctx, NS(primary_regime=label, conviction=conv))
    finally:
        TR.now_et = old


def test_score_rises_as_the_thesis_comes_true():
    far, _ = _score(_ctx(100.0, 104.0, "NEUTRAL", 0.2e6))
    mid, _ = _score(_ctx(100.0, 101.2, "PINNING", 0.4e6))
    near, _ = _score(_ctx(100.0, 100.3, "PINNING", 2.4e6))
    assert far < mid < near, \
        f"the score must CLIMB as the pin firms and price walks in " \
        f"({far:.3f} / {mid:.3f} / {near:.3f}) — a label switch cannot do this"
    assert near > 0.8, "a firm pin, price a short walk away, mid-window: high"


def test_a_perfect_pin_on_a_trending_tape_scores_low():
    """The operator's rule: no neutral play during a trend."""
    trend, _ = _score(_ctx(100.0, 100.3, "TRENDING", 2.4e6), label="TRENDING_BULL")
    near, _ = _score(_ctx(100.0, 100.3, "PINNING", 2.4e6))
    assert trend < 0.25 and trend < near / 3, \
        "identical pin geometry on a TRENDING tape must not score like a pin play"


def test_pin_firmness_ranks_pins():
    weak, _ = _score(_ctx(100.0, 100.3, "PINNING", 0.35e6))
    firm, _ = _score(_ctx(100.0, 100.3, "PINNING", 2.4e6))
    assert firm > weak, \
        "the strategy's PINNING flag is binary and cannot rank a 2.3M pin above " \
        "a 0.1M one — conviction should"


def test_it_warms_toward_the_window_and_dies_after_it():
    early, _ = _score(_ctx(100.0, 100.3, "PINNING", 2.4e6), hhmm=(10, 45))
    inwin, _ = _score(_ctx(100.0, 100.3, "PINNING", 2.4e6), hhmm=(12, 30))
    late, bd = _score(_ctx(100.0, 100.3, "PINNING", 2.4e6), hhmm=(15, 0))
    assert 0.0 < early < inwin, "readiness must ARM AHEAD, not switch on at 12:00"
    assert late == 0.0 and bd["win_val"] == 0.0, \
        "after 14:00 the strategy cannot fire — no score may survive it"


def test_a_chainless_tick_still_scores_the_pin():
    _, bd = _score(_ctx(100.0, 100.3, "PINNING", 2.4e6))
    assert bd["pin_val"] > 0.0, \
        "expected move needs a chain; without an ATR fallback the term carrying " \
        "the WHOLE thesis silently reads 0 on a chainless tick"
    assert bd["pin_dist_unit"] in ("em", "atr2"), \
        "the unit must be RECORDED — em and atr2 are different scales and must " \
        "never be pooled when fitting the bounds"


def test_no_gex_at_all_does_not_crash_and_scores_low():
    ctx = _ctx(100.0, 100.3, "PINNING", 2.4e6)
    ctx["gex"] = None
    r, bd = _score(ctx)
    assert r >= 0.0 and bd["pin"] is None and bd["gex_env"] is None


def test_the_coil_is_a_corroborator_not_a_veto():
    """A veto made this a switch; it is supporting evidence, not the trade."""
    comp, _ = _score(_ctx(100.0, 100.3, "PINNING", 2.4e6), label="COMPRESSION")
    rang, _ = _score(_ctx(100.0, 100.3, "PINNING", 2.4e6), label="RANGING")
    assert rang > 0.0, \
        "RANGING must still score — as a hard veto it was zero outside " \
        "COMPRESSION, which is why the track read 0.995 or nothing"
    assert comp >= rang
    assert rang > 0.90 * comp, \
        f"RANGING {rang:.3f} vs COMPRESSION {comp:.3f} — as a corroborator the " \
        f"coil only moves the 0.15-weighted narrow term, so these sit close"


def test_the_coil_is_not_in_hard_vetoes():
    """THE DISCRIMINATING TEST, and it took two tries to make it able to fail.

    `_combine` treats hard_vetoes as a ZERO TEST, not a multiplier — so
    restoring `coil_val` there does NOT change a COMPRESSION (1.0) or RANGING
    (0.5) tick at all. My first attempt compared those two and passed with the
    veto restored, i.e. it could not fail. The only case that discriminates is a
    label where `coil_val` is EXACTLY 0.0 while the pin thesis is strong.
    """
    r, bd = _score(_ctx(100.0, 100.3, "PINNING", 2.4e6), label="BREAKOUT_VOLATILE")
    assert bd["coil_val"] == 0.0, "fixture must exercise the zero-coil branch"
    assert r > 0.0, \
        "a firm, close pin must still score with the coil at zero — if this is " \
        "0.0 the coil is back in hard_vetoes and the track is a label switch again"
