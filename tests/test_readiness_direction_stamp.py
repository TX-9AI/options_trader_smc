"""
tests/test_readiness_direction_stamp.py — v1.0 — 2026-08-08

Pins `dir` onto EVERY readiness track (trade_readiness v1.6).

WHY IT EXISTS. Exactly one track journaled a direction — `_trend_credit_spread`
emitted `factors.dir`, the other five emitted nothing — and that went unnoticed
until the VWAP orientation ledger ran against it and put 30,565 records into a
single "undecidable" bucket whose caption blamed the cash-index case. Five of
six strategies were being discarded for a missing field under a label that said
something else. A field that only one caller writes is indistinguishable from a
field nobody needs, right up until a reader depends on it.

THE TWO THINGS THIS GUARDS, and the second is the one that would go wrong
quietly:
  1. Every track stamps the key at all.
  2. CONDOR DIRECTION IS EXPOSURE, NOT OPTION TYPE. A call credit is sold ABOVE
     and profits while price stays below, so its exposure is SHORT. The
     option-buyer reading (call=long) is the intuitive one and it is backwards
     here; getting it wrong inverts every condor row in the ledger while the
     output still looks perfectly well-formed. That is the failure class this
     repo keeps finding — a wrong answer that renders cleanly.

Also pinned: continuation's `dir` must agree with the derivation `_staged_pick`
uses, so the journal and the picker cannot drift apart; and "" must survive as
an honest "no intended side this tick" rather than being coerced to a side.

Deliberate-failure check performed when written: swapping the condor mapping to
call->long turns test_condor_direction_is_exposure_not_option_type red;
dropping the continuation label derivation turns
test_continuation_dir_matches_the_staged_pick_derivation red.
"""

import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.trade_readiness import TradeReadinessEngine  # noqa: E402


def _engine():
    rows = []
    eng = TradeReadinessEngine(emit=lambda ev, **s: rows.append((ev, s)))
    return eng, rows


def _ctx(price=100.0, sweep_kind=None):
    vol = NS(bb_middle=100.0, bb_upper=102.0, bb_lower=98.0,
             atr_current=0.5, bb_width_pct=0.45, bb_state="NORMAL",
             vwap=99.5, price_vs_vwap="ABOVE")
    sweep = NS(kind=sweep_kind) if sweep_kind else None
    liq = NS(recent_sweep=sweep, sweep_age_bars=2)
    return {"price": price, "vol": vol, "liq_map": liq,
            "trend": NS(primary_momentum="ACCELERATING")}


def _regime(label, conv=0.7):
    return NS(primary_regime=label, conviction=conv)


def test_every_track_stamps_a_direction():
    eng, _ = _engine()
    factors = {}
    for label in ("TRENDING_BULL", "RANGING", "COMPRESSION", "SWEEP_REVERSAL"):
        eng.assess_all(_ctx(sweep_kind="low_sweep"), _regime(label))
        for key, tr in eng.tracks.items():
            if tr.factors:
                factors.setdefault(key, tr.factors)
    missing = [k for k, f in factors.items() if "dir" not in f]
    assert not missing, f"tracks with no dir stamp: {missing}"
    assert len(factors) >= 6, f"expected all six tracks to report, got {sorted(factors)}"


def test_condor_direction_is_exposure_not_option_type():
    eng, _ = _engine()
    eng.assess_all(_ctx(), _regime("RANGING"))
    assert eng.tracks["condor_call"].factors["dir"] == "short", \
        "a CALL CREDIT is short exposure — the buyer's-eye call=long reading " \
        "inverts every condor row while the output still looks well-formed"
    assert eng.tracks["condor_put"].factors["dir"] == "long"
    # `side` must survive alongside — they answer different questions.
    assert eng.tracks["condor_call"].factors["side"] == "call"


def test_continuation_dir_matches_the_staged_pick_derivation():
    eng, _ = _engine()
    eng.assess_all(_ctx(), _regime("TRENDING_BULL"))
    assert eng.tracks["continuation"].factors["dir"] == "long"
    eng.assess_all(_ctx(), _regime("TRENDING_BEAR"))
    assert eng.tracks["continuation"].factors["dir"] == "short"


def test_no_intended_side_stays_empty_rather_than_guessing():
    eng, _ = _engine()
    eng.assess_all(_ctx(), _regime("RANGING"))
    assert eng.tracks["continuation"].factors["dir"] == "", \
        "outside a trending label continuation has no side; '' is the honest " \
        "answer and must not be coerced into one"


def test_sweep_direction_comes_from_the_live_sweep_kind():
    eng, _ = _engine()
    eng.assess_all(_ctx(sweep_kind="high_sweep"), _regime("SWEEP_REVERSAL"))
    assert eng.tracks["sweep"].factors["dir"] == "short", \
        "a HIGH sweep is faded SHORT — this is the field no offline tool " \
        "could recover, since it only ever existed in ctx.liq_map"
    eng2, _ = _engine()
    eng2.assess_all(_ctx(sweep_kind="low_sweep"), _regime("SWEEP_REVERSAL"))
    assert eng2.tracks["sweep"].factors["dir"] == "long"
    eng3, _ = _engine()
    eng3.assess_all(_ctx(sweep_kind=None), _regime("SWEEP_REVERSAL"))
    assert eng3.tracks["sweep"].factors["dir"] == ""


def test_butterfly_is_explicitly_neutral():
    eng, _ = _engine()
    eng.assess_all(_ctx(), _regime("COMPRESSION"))
    assert eng.tracks["butterfly"].factors["dir"] == "neutral", \
        "sideless BY DESIGN and a field that never existed must not look alike"


def test_the_journal_payload_actually_carries_it():
    """A value computed and never written is the exact bug v1.5 fixed for VWAP."""
    eng, rows = _engine()
    eng.assess_all(_ctx(sweep_kind="low_sweep"), _regime("TRENDING_BULL"))
    payloads = [s.get("readiness", {}) for ev, s in rows if "readiness" in s]
    assert payloads, "no readiness rows journaled"
    assert any("dir" in (p.get("factors") or {}) for p in payloads), \
        "dir is computed but never reaches the journal"
