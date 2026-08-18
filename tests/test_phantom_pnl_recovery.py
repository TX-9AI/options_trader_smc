"""
tests/test_phantom_pnl_recovery.py — v3.6 phantom P&L recovery + reconcile
schedule.

Covers:
  1. Vertical manual close fully recovered from order history — real net price
     and credit-signed P&L (never $0.00).
  2. Opening orders on the SAME symbols never match (only closing actions).
  3. No matching order (expiry / assignment) -> None -> caller books the
     flagged $0.00 fallback.
  4. Manual close split across multiple orders -> aggregated, quantity-weighted.
  5. Butterfly recovery on the lower+upper-2*center basis.
  6. Adopted short single leg: BUY_TO_CLOSE matches, credit-signed P&L.
  7. Slot schedule: interval slots, wind-down sweeps at 15:45/15:50/15:57,
     nothing at/after 16:00 or on weekends.

Run: PYTHONPATH=. pytest tests/test_phantom_pnl_recovery.py -v
"""

import sys
import os
from datetime import datetime
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution.broker_reconcile import match_closing_fills, phantom_pnl  # noqa: E402

SHORT = "SPXW  260715P06200000"
LONG  = "SPXW  260715P06190000"


def leg(sym, action, fills):
    return NS(symbol=sym, action=action,
              fills=[NS(quantity=q, fill_price=p) for q, p in fills])


def order(*legs):
    return NS(legs=list(legs))


def vertical_record(contracts=2):
    return {
        "trade_id": "abcd1234", "contracts": contracts, "entry_premium": 1.50,
        "is_condor_leg": 1, "strategy": "IronCondorStrategy", "symbol": "SPX",
        "short_symbol": SHORT, "long_symbol": LONG, "option_symbol": SHORT,
        "spread_width": 10.0, "entry_time": "2026-07-15 13:02:11",
    }


# 1 — full manual close recovered
def test_vertical_manual_close_recovered():
    rec = vertical_record(contracts=2)
    hist = [order(leg(SHORT, "Buy to Close",  [(2, 0.60)]),
                  leg(LONG,  "Sell to Close", [(2, 0.15)]))]
    match = match_closing_fills(rec, hist)
    assert match is not None
    qty, net = match
    assert qty == 2 and net == pytest.approx(0.45)
    pnl = phantom_pnl(rec, net, closed_qty=qty)
    assert pnl == pytest.approx((1.50 - 0.45) * 2 * 100)   # +210.00, never $0


# 2 — opening orders on the same symbols must NOT match
def test_opening_orders_excluded():
    rec = vertical_record()
    hist = [order(leg(SHORT, "Sell to Open", [(2, 1.50)]),
                  leg(LONG,  "Buy to Open",  [(2, 0.40)]))]
    assert match_closing_fills(rec, hist) is None


# 3 — expiry/assignment: no closing order anywhere -> None (caller flags $0)
def test_no_matching_order_returns_none():
    rec = vertical_record()
    hist = [order(leg("AMD   260711C00180000", "Sell to Close", [(1, 2.10)]))]
    assert match_closing_fills(rec, hist) is None
    assert match_closing_fills(rec, []) is None


# 4 — manual close split across multiple orders -> weighted aggregate
def test_multi_order_manual_close_weighted():
    rec = vertical_record(contracts=2)
    hist = [
        order(leg(SHORT, "Buy to Close",  [(1, 0.60)]),
              leg(LONG,  "Sell to Close", [(1, 0.10)])),   # net 0.50 x1
        order(leg(SHORT, "Buy to Close",  [(1, 0.80)]),
              leg(LONG,  "Sell to Close", [(1, 0.20)])),   # net 0.60 x1
    ]
    qty, net = match_closing_fills(rec, hist)
    assert qty == 2
    assert net == pytest.approx(0.55)   # short avg 0.70 - long avg 0.15


# 5 — butterfly basis
def test_butterfly_recovery_basis():
    rec = {
        "trade_id": "fly00001", "contracts": 1, "entry_premium": 0.90,
        "is_butterfly": True, "symbol": "SPX",
        "lower_symbol": "L", "center_symbol": "C", "upper_symbol": "U",
    }
    hist = [order(leg("L", "Sell to Close", [(1, 2.00)]),
                  leg("C", "Buy to Close",  [(2, 1.20)]),
                  leg("U", "Sell to Close", [(1, 0.80)]))]
    qty, net = match_closing_fills(rec, hist)
    assert qty == 1
    assert net == pytest.approx(2.00 + 0.80 - 2 * 1.20)    # 0.40
    assert phantom_pnl(rec, net) == pytest.approx((0.40 - 0.90) * 1 * 100)  # long math


# 6 — adopted short single leg: buy-to-close matches, credit-signed
def test_adopted_short_single_leg():
    rec = {"trade_id": "adopt001", "contracts": 1, "entry_premium": 2.00,
           "is_short_position": 1, "option_symbol": SHORT, "symbol": "SPX"}
    hist = [order(leg(SHORT, "Buy to Close", [(1, 0.75)]))]
    qty, net = match_closing_fills(rec, hist)
    assert (qty, net) == (1, 0.75)
    assert phantom_pnl(rec, net) == pytest.approx((2.00 - 0.75) * 100)
    # and a sell-to-close on a short must NOT match
    assert match_closing_fills(rec, [order(leg(SHORT, "Sell to Close", [(1, 0.75)]))]) is None


# 7 — reconcile schedule
def test_reconcile_slot_schedule(monkeypatch):
    import config as cfg
    monkeypatch.setattr(cfg, "BROKER_RECONCILE_INTERVAL_MIN", 10, raising=False)
    import main
    monkeypatch.setattr(main, "BROKER_RECONCILE_INTERVAL_MIN", 10, raising=False)
    slot = main._intraday_reconcile_slot
    wed = lambda h, m: datetime(2026, 7, 15, h, m)          # a Wednesday

    assert slot(wed(9, 29)) is None
    assert slot(wed(9, 30)).endswith("09:30")
    assert slot(wed(9, 39)).endswith("09:30")
    assert slot(wed(9, 40)).endswith("09:40")               # 10-min cadence
    assert slot(wed(13, 55)).endswith("13:50")
    # wind-down sweeps:
    assert slot(wed(15, 45)).endswith("15:45")
    assert slot(wed(15, 52)).endswith("15:50")
    assert slot(wed(15, 58)).endswith("15:57")              # post-flatten pass
    assert slot(wed(16, 0)) is None                          # loop dormant
    assert slot(datetime(2026, 7, 18, 12, 0)) is None        # Saturday
