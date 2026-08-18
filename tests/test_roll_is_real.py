"""
tests/test_roll_is_real.py — audit defect P: the broken-wing roll must place a
REAL rolled vertical and book only broker truth.

  1. LIVE happy path: old vertical closed at the CONFIRMED fill (not
     plan.close_cost), a real signed-credit limit is placed for the rolled
     vertical, and the record books the broker's net credit and quantity.
  2. Rolled open never fills → NO record written (no ghost), HALF-COMPLETE
     page fires, roll returns False; DB matches broker.
  3. Fills come in light → structure booked truthfully AND the risk-free
     claim is re-checked against actual credit, paging when it fails.
  4. PAPER mirrors live: routes through place_exit_order for the close and
     applies PAPER_FILL_SLIPPAGE_PCT to the rolled credit.

Run: PYTHONPATH=. pytest tests/test_roll_is_real.py -v
"""

import sys
import os
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tastytrade.order import OrderStatus  # noqa: E402

import config as cfg                       # noqa: E402
import strategy.condor_roll as cr          # noqa: E402
from strategy.condor_roll import _execute_roll  # noqa: E402

OLD_SHORT, OLD_LONG = "SPXW OS", "SPXW OL"
NEW_SHORT, NEW_LONG = "SPXW NS", "SPXW NL"


def leg(sym, fills):
    return NS(symbol=sym, fills=[NS(quantity=q, fill_price=p) for q, p in fills])


def order_state(oid, status, legs=()):
    return NS(id=oid, status=status, legs=list(legs), reject_reason=None)


class FakeBroker:
    def __init__(self, submits, get_map):
        self.submits = list(submits)
        self.get_map = get_map          # oid -> callable(cancelled) -> state
        self.placed  = []
        self.cancels = []
        self.cancelled = set()

    def place_order(self, session, order, dry_run=False):
        self.placed.append(order)
        return NS(errors=None, order=self.submits.pop(0))

    def get_order(self, session, oid):
        return self.get_map[oid](oid in self.cancelled)

    def delete_order(self, session, oid):
        self.cancels.append(oid)
        self.cancelled.add(oid)


class FakeTL:
    def __init__(self):
        self.exits, self.entries, self.updates = [], [], []
    def log_exit(self, trade_id, exit_price, pnl_usd, exit_reason):
        self.exits.append((trade_id, exit_price, pnl_usd, exit_reason))
    def log_entry(self, record):
        self.entries.append(record)
    def update_fields(self, trade_id, **f):
        self.updates.append((trade_id, f))


class FakePM:
    def __init__(self):
        self.removed = []
    def remove_record(self, tid):
        self.removed.append(tid)
    def add_condor_leg(self, rec):
        pass


def plan(**kw):
    d = dict(contracts=1, close_cost=0.35, roll_credit=1.10,
             new_short_strike=6180.0, new_long_strike=6175.0,
             new_short_symbol=NEW_SHORT, new_long_symbol=NEW_LONG,
             untested_side="put", tested_side="call",
             tested_width=5.0, total_credit_after=5.20, risk_free=True)
    d.update(kw)
    return NS(**d)


def untested_record():
    return {"trade_id": "old-untested-1", "contracts": 1, "entry_premium": 1.00,
            "credit_received": 1.00, "is_condor_leg": 1, "symbol": "SPX",
            "strategy": "IronCondorStrategy", "spread_width": 5.0,
            "short_symbol": OLD_SHORT, "long_symbol": OLD_LONG,
            "option_symbol": OLD_SHORT}


def make_tested_record():
    return {"trade_id": "old-tested-1", "is_condor_leg": 1}


@pytest.fixture
def wiring(monkeypatch):
    monkeypatch.setattr(cfg, "LIVE_FILL_POLL_SECONDS", 0.0, raising=False)
    monkeypatch.setattr(cfg, "LIVE_FILL_DEADLINE_SECONDS", 0.02, raising=False)
    monkeypatch.setattr(cfg, "LIVE_ENTRY_DEADLINE_SECONDS", 0.02, raising=False)

    tl, pm, pages = FakeTL(), FakePM(), []
    import database.trade_logger as tlm
    import notifications.alert_manager as am
    import execution.exit_engine as xe
    monkeypatch.setattr(tlm, "get_trade_logger", lambda: tl)
    monkeypatch.setattr(am, "get_alert_manager",
                        lambda: NS(_send=lambda m: pages.append(m)))
    monkeypatch.setattr(xe, "get_trade_logger", lambda: None)
    return tl, pm, pages, monkeypatch


def wire_broker(monkeypatch, broker):
    import execution.exit_engine as xe
    import data.tasty_client as tc
    monkeypatch.setattr(xe, "get_session", lambda: NS())
    monkeypatch.setattr(xe, "get_account", lambda: broker)
    monkeypatch.setattr(tc, "get_session", lambda: NS())
    monkeypatch.setattr(tc, "get_account", lambda: broker)
    # exit engine singleton must be fresh per test
    xe._exit_engine = None


# 1 — live happy path: real order, broker truth booked everywhere
def test_live_roll_places_real_order_and_books_truth(wiring):
    tl, pm, pages, monkeypatch = wiring
    close_filled = order_state(100, OrderStatus.FILLED,
                               legs=[leg(OLD_SHORT, [(1, 0.42)]),
                                     leg(OLD_LONG,  [(1, 0.05)])])   # net 0.37
    open_filled  = order_state(200, OrderStatus.FILLED,
                               legs=[leg(NEW_SHORT, [(1, 1.30)]),
                                     leg(NEW_LONG,  [(1, 0.25)])])   # net 1.05
    broker = FakeBroker(
        submits=[order_state(100, OrderStatus.LIVE),
                 order_state(200, OrderStatus.LIVE)],
        get_map={100: lambda c: close_filled, 200: lambda c: open_filled})
    wire_broker(monkeypatch, broker)

    ok = _execute_roll(FakePM.__new__(FakePM) if False else pm,
                       make_tested_record(), untested_record(),
                       plan(), NS(paper_trading=False))
    assert ok is True
    # close booked at the CONFIRMED 0.37, not plan.close_cost 0.35:
    tid, exit_price, pnl, reason = tl.exits[0]
    assert exit_price == pytest.approx(0.37)
    assert pnl == pytest.approx((1.00 - 0.37) * 1 * 100)
    # a REAL rolled order was placed, credit-signed positive:
    assert len(broker.placed) == 2
    assert float(broker.placed[1].price) == pytest.approx(1.10)
    # record books broker net 1.05, not the 1.10 plan credit:
    rec = tl.entries[0]
    assert rec["entry_premium"] == pytest.approx(1.05)
    assert rec["credit_received"] == pytest.approx(1.05)
    assert rec["contracts"] == 1 and rec["order_id"] == "200"


# 2 — rolled open never fills: NO ghost, page, False
def test_live_roll_open_unfilled_writes_no_ghost(wiring):
    tl, pm, pages, monkeypatch = wiring
    close_filled = order_state(100, OrderStatus.FILLED,
                               legs=[leg(OLD_SHORT, [(1, 0.35)]),
                                     leg(OLD_LONG,  [(1, 0.02)])])
    def open_states(cancelled):
        st = OrderStatus.CANCELLED if cancelled else OrderStatus.LIVE
        return order_state(200, st, legs=[leg(NEW_SHORT, []), leg(NEW_LONG, [])])
    broker = FakeBroker(
        submits=[order_state(100, OrderStatus.LIVE),
                 order_state(200, OrderStatus.LIVE)],
        get_map={100: lambda c: close_filled, 200: open_states})
    wire_broker(monkeypatch, broker)

    ok = _execute_roll(pm, make_tested_record(), untested_record(),
                       plan(), NS(paper_trading=False))
    assert ok is False
    assert tl.entries == []                         # no fictional vertical
    assert 200 in broker.cancels                    # the unfilled open was killed
    assert any("HALF-COMPLETE" in m for m in pages) # and it paged


# 3 — fills come in light: booked truthfully, risk-free claim re-checked
def test_light_fill_pages_not_risk_free(wiring):
    tl, pm, pages, monkeypatch = wiring
    close_filled = order_state(100, OrderStatus.FILLED,
                               legs=[leg(OLD_SHORT, [(1, 0.35)]),
                                     leg(OLD_LONG,  [(1, 0.02)])])
    open_light   = order_state(200, OrderStatus.FILLED,
                               legs=[leg(NEW_SHORT, [(1, 1.00)]),
                                     leg(NEW_LONG,  [(1, 0.25)])])   # net 0.75 << 1.10
    broker = FakeBroker(
        submits=[order_state(100, OrderStatus.LIVE),
                 order_state(200, OrderStatus.LIVE)],
        get_map={100: lambda c: close_filled, 200: lambda c: open_light})
    wire_broker(monkeypatch, broker)

    ok = _execute_roll(pm, make_tested_record(), untested_record(),
                       plan(total_credit_after=5.20, tested_width=5.0),
                       NS(paper_trading=False))
    assert ok is True
    assert tl.entries[0]["entry_premium"] == pytest.approx(0.75)
    # actual total credit = 5.20 - 1.10 + 0.75 = 4.85 < 5.0 width → page:
    assert any("NOT fully risk-free" in m for m in pages)


# 4 — paper mirrors live shape: close via place_exit_order, slippage on credit
def test_paper_roll_mirrors_live(wiring):
    tl, pm, pages, monkeypatch = wiring
    monkeypatch.setattr(cfg, "PAPER_FILL_SLIPPAGE_PCT", 0.01, raising=False)
    import execution.exit_engine as xe
    xe._exit_engine = None

    ok = _execute_roll(pm, make_tested_record(), untested_record(),
                       plan(), NS(paper_trading=True))
    assert ok is True
    tid, exit_price, pnl, reason = tl.exits[0]
    assert exit_price == pytest.approx(0.35)               # paper close at the mark
    rec = tl.entries[0]
    assert rec["entry_premium"] == pytest.approx(1.10 * 0.99)  # credit less slippage
    assert rec["order_id"] == "PAPER"
