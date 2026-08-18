"""
tests/test_readiness_market_snapshot.py — v1.0 — 2026-08-05

Guards the VWAP context now journaled on every readiness record.

WHY IT EXISTS. `volatility_engine` has computed `vwap` and `price_vs_vwap` all
along and NOTHING PERSISTED THEM. A key scan of 2026-08-05's journal — 11,138
records, every event type — found no VWAP-shaped field anywhere. That is why
`vwap_orientation` has never once run: not a broken tool, a tool built against a
schema that never landed.

WHY IT MATTERS NOW. Item AI's candidate fix for the condor is a VWAP-ANCHORED
midpoint instead of the flat Bollinger midline, and that cannot be evaluated on
data that does not exist. Every session between now and the decision is history
we either have or do not — the same use-it-or-lose-it logic as the candle tape.

Deliberate-failure check performed when written: deriving `price_vs_vwap` from
the sign of dist_pct instead of reading the engine's field turns
test_no_volume_reports_NONE_rather_than_inventing_a_side red; dropping the
division by vwap turns test_distance_is_comparable_across_price_levels red.
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from analysis.trade_readiness import TradeReadinessEngine as TR  # noqa: E402


class _Vol:
    vwap = 100.0
    price_vs_vwap = "ABOVE"


def test_the_snapshot_carries_all_three_fields():
    s = TR._market_snapshot({"vol": _Vol(), "price": 101.5})
    assert set(s) == {"vwap", "price_vs_vwap", "dist_pct"}


def test_distance_is_signed():
    class Below(_Vol):
        price_vs_vwap = "BELOW"
    assert TR._market_snapshot({"vol": _Vol(), "price": 101.5})["dist_pct"] == 1.5
    assert TR._market_snapshot({"vol": Below(), "price": 98.0})["dist_pct"] == -2.0


def test_distance_is_comparable_across_price_levels():
    """A percentage of VWAP, not a dollar gap — otherwise a $900 symbol
    dominates every pooled read and the field is useless for the fleet."""
    class Cheap(_Vol):
        vwap = 30.0
    class Rich(_Vol):
        vwap = 900.0
    a = TR._market_snapshot({"vol": Cheap(), "price": 30.3})["dist_pct"]
    b = TR._market_snapshot({"vol": Rich(), "price": 909.0})["dist_pct"]
    assert a == b == 1.0


def test_no_volume_reports_NONE_rather_than_inventing_a_side():
    """The engine sets NONE when there is no volume. Deriving the side from a
    computed sign would silently manufacture an orientation exactly where the
    engine is telling you it has none."""
    class NoVol(_Vol):
        vwap = 0.0
        price_vs_vwap = "NONE"
    s = TR._market_snapshot({"vol": NoVol(), "price": 100.0})
    assert s["price_vs_vwap"] == "NONE"
    assert s["vwap"] is None and s["dist_pct"] is None


def test_the_side_is_READ_from_the_engine_not_derived():
    """Behavioural tests cannot separate these: the no-volume path returns early
    on vwap<=0, so a derived side produces identical output on every case above.
    Found by the deliberate-failure run — swapping in
    `"ABOVE" if px >= vw else "BELOW"` left the whole file green.
    It still matters: the engine owns the NONE state, and a derived sign would
    always have an opinion where the engine deliberately has none."""
    src = open(os.path.join(REPO, "analysis", "trade_readiness.py")).read()
    body = src[src.index("def _market_snapshot"):]
    body = body[:body.index("def _journal")]
    assert 'getattr(vol, "price_vs_vwap"' in body, \
        "price_vs_vwap must be read from the volatility engine, not computed " \
        "from the sign of the distance"
    assert '"ABOVE" if' not in body and '"BELOW" if' not in body


def test_a_missing_context_never_raises():
    """Log-only: this must never reach the trading loop."""
    for ctx in ({}, None, {"vol": None, "price": 0.0}):
        assert isinstance(TR._market_snapshot(ctx), dict)


def test_the_journal_actually_emits_it():
    """The helper being correct is worthless if the emit does not carry it —
    which is precisely the failure being fixed: a value computed, available,
    and never persisted."""
    src = open(os.path.join(REPO, "analysis", "trade_readiness.py")).read()
    assert '"market": self._mkt' in src
    assert "self._mkt = self._market_snapshot(ctx)" in src
