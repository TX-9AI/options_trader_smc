"""
tests/test_entry_fill_confirmation.py — audit defect O part 1 (condor entry)
and defect R (paper mirrors live friction).

confirm_order_fill (execution/order_confirm.py) against a scripted broker:
  1. Full fill → filled=True, quantity, and the net credit computed from
     per-leg fills (broker truth), NOT the limit price.
  2. Rejected → filled=False, no quantity, no price.
  3. Never fills by deadline → cancel requested → filled=False; caller records
     NOTHING (no ghost position).
  4. Partial then cancelled → filled=True for the PARTIAL quantity at the
     weighted net (a real position must be booked and managed).
  5. Cancel keeps failing on a working order → filled=False with
     working_order_id set (page + reconcile-adopt safety net).
  6. Fill lands during the cancel race → booked (race resolved to truth).
  7. Butterfly basis math: lower + upper − 2·center from per-leg fills.
  8. Paper condor CREDIT routes through limit_ladder.paper_fill_credit and
     applies PAPER_FILL_SLIPPAGE_PCT against the trade (receives LESS).
 14. Paper friction is UNIFORM across every paper path (defect T, 2026-07-22):
     at the 0.0 default every path books the bare mark; at a non-zero knob
     every path degrades together, debits paying more and credits receiving
     less. This replaces the pre-v3.8 assertion that singles were hardcoded to
     mark*1.01 — that stopped being true when live moved to mark-limits.

Run: PYTHONPATH=. pytest tests/test_entry_fill_confirmation.py -v
"""

import sys
import os
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tastytrade.order import OrderStatus  # noqa: E402

import config as cfg                                          # noqa: E402
from execution.limit_ladder import (                           # noqa: E402
    paper_fill_price, paper_fill_credit,
)
from execution.order_confirm import (                          # noqa: E402
    confirm_order_fill, net_from_fills, EntryFill,
)

SHORT = "SPXW  260715P06200000"
LONG  = "SPXW  260715P06190000"
VERT_BASIS = [(SHORT, 1, +1), (LONG, 1, -1)]


def leg(sym, fills):
    return NS(symbol=sym, fills=[NS(quantity=q, fill_price=p) for q, p in fills])


def order_state(oid, status, legs=(), reject_reason=None):
    return NS(id=oid, status=status, legs=list(legs), reject_reason=reject_reason)


class FakeAccount:
    def __init__(self, states=None, states_fn=None, cancel_fails=0):
        self.states       = list(states or [])
        self.states_fn    = states_fn
        self.cancels      = []
        self.cancelled    = False
        self.cancel_fails = cancel_fails   # raise on the first N delete_order calls

    def get_order(self, session, oid):
        if self.states_fn is not None:
            return self.states_fn(self.cancelled)
        if len(self.states) > 1:
            return self.states.pop(0)
        return self.states[0]

    def delete_order(self, session, oid):
        self.cancels.append(oid)
        if len(self.cancels) <= self.cancel_fails:
            raise RuntimeError("cancel refused")
        self.cancelled = True


@pytest.fixture(autouse=True)
def fast_polls(monkeypatch):
    monkeypatch.setattr(cfg, "LIVE_FILL_POLL_SECONDS", 0.0, raising=False)
    monkeypatch.setattr(cfg, "LIVE_ENTRY_DEADLINE_SECONDS", 0.02, raising=False)


SESSION = NS(name="fake")


# 1 — full fill at broker truth, not the limit
def test_full_fill_books_broker_net_credit():
    filled = order_state(1, OrderStatus.FILLED,
                         legs=[leg(SHORT, [(2, 1.42)]), leg(LONG, [(2, 0.30)])])
    acct = FakeAccount(states=[filled])
    res = confirm_order_fill(SESSION, acct, order_state(1, OrderStatus.LIVE),
                             VERT_BASIS, what="condor-leg entry")
    assert res.filled is True
    assert res.quantity == 2
    assert res.net_price == pytest.approx(1.12)   # 1.42 − 0.30, not the 1.50 limit
    assert acct.cancels == []


# 2 — reject: nothing to record
def test_reject_records_nothing():
    rejected = order_state(2, OrderStatus.REJECTED,
                           legs=[leg(SHORT, []), leg(LONG, [])],
                           reject_reason="insufficient buying power")
    acct = FakeAccount(states=[rejected])
    res = confirm_order_fill(SESSION, acct, order_state(2, OrderStatus.LIVE),
                             VERT_BASIS)
    assert res.filled is False and res.quantity == 0 and res.net_price is None
    assert "rejected" in res.detail


# 3 — the ghost-position test: never fills → cancel → NO position
def test_unfilled_deadline_cancels_and_records_nothing():
    def states(cancelled):
        st = OrderStatus.CANCELLED if cancelled else OrderStatus.LIVE
        return order_state(3, st, legs=[leg(SHORT, []), leg(LONG, [])])
    acct = FakeAccount(states_fn=states)
    res = confirm_order_fill(SESSION, acct, order_state(3, OrderStatus.LIVE),
                             VERT_BASIS)
    assert res.filled is False
    assert res.net_price is None                 # never a fabricated credit
    assert acct.cancels == [3]
    assert res.working_order_id is None          # cleanly dead, nothing lingering


# 4 — partial is a REAL position: book the filled size at weighted net
def test_partial_books_filled_quantity():
    def states(cancelled):
        st = OrderStatus.CANCELLED if cancelled else OrderStatus.LIVE
        return order_state(4, st, legs=[leg(SHORT, [(1, 1.40)]),
                                        leg(LONG,  [(1, 0.28)])])
    acct = FakeAccount(states_fn=states)
    res = confirm_order_fill(SESSION, acct, order_state(4, OrderStatus.LIVE),
                             VERT_BASIS)
    assert res.filled is True
    assert res.quantity == 1                     # of the 2 requested
    assert res.net_price == pytest.approx(1.12)


# 5 — uncancellable working order: page + reconcile-adopt safety net
def test_cancel_failure_reports_working_order():
    live = order_state(5, OrderStatus.LIVE, legs=[leg(SHORT, []), leg(LONG, [])])
    acct = FakeAccount(states=[live], cancel_fails=99)
    res = confirm_order_fill(SESSION, acct, live, VERT_BASIS)
    assert res.filled is False
    assert res.working_order_id == "5"
    assert len(acct.cancels) >= 3                # it genuinely tried


# 6 — fill lands during the cancel race → booked
def test_fill_during_cancel_race_is_booked():
    def states(cancelled):
        if cancelled:   # cancel "landed" but the fill won the race
            return order_state(6, OrderStatus.FILLED,
                               legs=[leg(SHORT, [(2, 1.45)]),
                                     leg(LONG,  [(2, 0.35)])])
        return order_state(6, OrderStatus.LIVE,
                           legs=[leg(SHORT, []), leg(LONG, [])])
    acct = FakeAccount(states_fn=states)
    res = confirm_order_fill(SESSION, acct, order_state(6, OrderStatus.LIVE),
                             VERT_BASIS)
    assert res.filled is True and res.quantity == 2
    assert res.net_price == pytest.approx(1.10)


# 7 — butterfly basis math
def test_butterfly_basis():
    basis = [("L", 1, +1), ("C", 2, -1), ("U", 1, +1)]
    placed = order_state(7, OrderStatus.FILLED,
                         legs=[leg("L", [(1, 2.00)]),
                               leg("C", [(2, 1.20)]),
                               leg("U", [(1, 0.80)])])
    units, net = net_from_fills(placed, basis)
    assert units == 1
    assert net == pytest.approx(2.00 + 0.80 - 2 * 1.20)   # 0.40 debit basis


# 8 — paper condor credit applies friction against the trade (defect R/T)
#     v2: exercises the REAL helper instead of re-doing the arithmetic inline.
#     The old version asserted round(1.50*0.99, 4) == 1.485, which tested
#     Python, not the system — it would have passed even after the call site
#     stopped applying the knob (which is exactly what happened).
def test_paper_condor_credit_applies_slippage(monkeypatch):
    monkeypatch.setattr(cfg, "PAPER_FILL_SLIPPAGE_PCT", 0.01, raising=False)
    assert paper_fill_credit(1.50) == pytest.approx(1.485)  # credit REDUCED
    assert paper_fill_price(0.90) == pytest.approx(0.91)    # debit pays MORE
                                                            # (2dp postable tick)


# ═══ O parts 2+3 — single-leg readback and the butterfly rebuild ═════════════

from execution import entry_engine as ee  # noqa: E402
from execution.entry_engine import EntryEngine  # noqa: E402


class FakeBroker(FakeAccount):
    """FakeAccount + place_order: `submits` is a list of PlacedOrders to hand
    back per place_order call (None → errors)."""
    def __init__(self, submits, **kw):
        super().__init__(**kw)
        self.submits = list(submits)
        self.placed  = []

    def place_order(self, session, order, dry_run=False):
        self.placed.append(order)
        nxt = self.submits.pop(0)
        if nxt is None:
            return NS(errors=[{"message": "refused"}], order=None)
        return NS(errors=None, order=nxt)


LOWER, CENTER, UPPER = "SPXW L", "SPXW C", "SPXW U"


def fly_signal(net_debit=0.90):
    return NS(is_butterfly=True, net_debit=net_debit,
              lower_contract=NS(symbol=LOWER, strike=6150),
              center_contract=NS(symbol=CENTER, strike=6200),
              upper_contract=NS(symbol=UPPER, strike=6250))


def single_signal(mark=2.00):
    return NS(is_butterfly=False, entry_premium=mark,
              contract=NS(symbol=SHORT, strike=6200))


def live_engine(monkeypatch, broker):
    monkeypatch.setattr(ee, "get_trade_logger", lambda: None)
    monkeypatch.setattr(ee, "get_session", lambda: SESSION)
    monkeypatch.setattr(ee, "get_account", lambda: broker)
    return EntryEngine(paper_trading=False)


# 9 — single-leg MARKET: fill price read back from fills, never the signal mark
def test_single_leg_books_broker_fill_not_signal_mark(monkeypatch):
    filled = order_state(11, OrderStatus.FILLED, legs=[leg(SHORT, [(2, 2.35)])])
    broker = FakeBroker(submits=[order_state(11, OrderStatus.LIVE)], states=[filled])
    eng = live_engine(monkeypatch, broker)

    price, oid, qty = eng._place_single_leg(single_signal(mark=2.00), 2)
    assert price == pytest.approx(2.35)   # broker fill, NOT the 2.00 mark
    assert qty == 2 and oid == "11"


# 10 — butterfly debit priced NEGATIVE (signed SDK convention)
def test_butterfly_debit_is_negative_priced(monkeypatch):
    filled = order_state(12, OrderStatus.FILLED,
                         legs=[leg(LOWER, [(1, 2.00)]), leg(CENTER, [(2, 1.20)]),
                               leg(UPPER, [(1, 0.80)])])
    broker = FakeBroker(submits=[order_state(12, OrderStatus.LIVE)], states=[filled])
    eng = live_engine(monkeypatch, broker)

    price, oid, qty = eng._place_butterfly(fly_signal(net_debit=0.90), 1)
    assert float(broker.placed[0].price) == pytest.approx(-0.90)  # − = debit
    assert price == pytest.approx(0.40)   # broker net from fills, not the limit
    assert qty == 1


# 11 — ladder: attempt 2 only after attempt 1 confirmed dead with zero fills
def test_butterfly_ladder_replaces_only_after_confirmed_dead(monkeypatch):
    dead_empty = order_state(13, OrderStatus.CANCELLED,
                             legs=[leg(LOWER, []), leg(CENTER, []), leg(UPPER, [])])
    filled2 = order_state(14, OrderStatus.FILLED,
                          legs=[leg(LOWER, [(1, 2.02)]), leg(CENTER, [(2, 1.20)]),
                                leg(UPPER, [(1, 0.79)])])

    class Ladder(FakeBroker):
        def get_order(self, session, oid):
            if oid == 13:
                if self.cancelled:
                    return dead_empty
                return order_state(13, OrderStatus.LIVE,
                                   legs=[leg(LOWER, []), leg(CENTER, []), leg(UPPER, [])])
            return filled2

    broker = Ladder(submits=[order_state(13, OrderStatus.LIVE),
                             order_state(14, OrderStatus.LIVE)])
    eng = live_engine(monkeypatch, broker)

    price, oid, qty = eng._place_butterfly(fly_signal(net_debit=0.90), 1)
    assert len(broker.placed) == 2
    assert float(broker.placed[1].price) == pytest.approx(-0.91)  # 1-tick improve
    assert broker.cancels == [13]           # attempt 1 was killed first
    assert (price, qty) == (pytest.approx(0.41), 1)


# 12 — the double-position guard: uncancellable attempt 1 STOPS the ladder
def test_butterfly_uncancellable_never_places_second_order(monkeypatch):
    class Stuck(FakeBroker):
        def get_order(self, session, oid):
            return order_state(15, OrderStatus.LIVE,
                               legs=[leg(LOWER, []), leg(CENTER, []), leg(UPPER, [])])
    broker = Stuck(submits=[order_state(15, OrderStatus.LIVE),
                            order_state(16, OrderStatus.LIVE)],
                   cancel_fails=99)
    import notifications.alert_manager as am
    pages = []
    monkeypatch.setattr(am, "get_alert_manager",
                        lambda: NS(_send=lambda m: pages.append(m)))
    eng = live_engine(monkeypatch, broker)

    price, oid, qty = eng._place_butterfly(fly_signal(), 1)
    assert (price, qty) == (None, 0)         # nothing recorded
    assert len(broker.placed) == 1           # attempt 2 NEVER placed
    assert any("could not be cancelled" in m for m in pages)


# 13 — butterfly partial on attempt 1 books the filled size, no re-place
def test_butterfly_partial_books_filled_size_no_replace(monkeypatch):
    def states(cancelled):
        st = OrderStatus.CANCELLED if cancelled else OrderStatus.LIVE
        return order_state(17, st,
                           legs=[leg(LOWER, [(1, 2.00)]), leg(CENTER, [(2, 1.20)]),
                                 leg(UPPER, [(1, 0.80)])])
    broker = FakeBroker(submits=[order_state(17, OrderStatus.LIVE),
                                 order_state(18, OrderStatus.LIVE)],
                        states_fn=states)
    eng = live_engine(monkeypatch, broker)

    price, oid, qty = eng._place_butterfly(fly_signal(), 2)
    assert qty == 1 and price == pytest.approx(0.40)
    assert len(broker.placed) == 1           # partial → position, not a re-place


# 14 — PAPER FRICTION IS UNIFORM (defect T, 2026-07-22)
#
#   Supersedes the pre-v3.8 assertion that a paper single booked mark*1.01.
#   That encoded a MARKET-order world: live crossed the spread, so paper had
#   to pay a haircut to stay honest. Live now posts a LIMIT AT THE MARK
#   (limit_ladder v1.2) and either fills there or does not fill at all, so a
#   markup would make paper PESSIMISTIC on price while staying optimistic on
#   FILL RATE — the wrong error in the wrong direction. Booking the mark is
#   the honest default; no-fill risk is the residual, and it cannot be
#   modelled as a price haircut.
#
#   What must hold instead, and what this test pins:
#     (a) at the 0.0 DEFAULT every paper path books the bare mark, and
#     (b) at a non-zero knob every path degrades TOGETHER — debits pay more,
#         credits receive less — so no strategy is quietly cheaper to trade in
#         paper than another. (a) is the policy; (b) is what makes the knob a
#         usable stress lever once the live shakedown measures real fill
#         quality.
def test_paper_entries_book_the_mark_by_default(monkeypatch):
    monkeypatch.setattr(cfg, "PAPER_FILL_SLIPPAGE_PCT", 0.0, raising=False)
    monkeypatch.setattr(ee, "get_trade_logger", lambda: None)
    eng = EntryEngine(paper_trading=True)

    p, oid, q = eng._place_single_leg(single_signal(mark=2.00), 2)
    assert p == pytest.approx(2.00) and q == 2       # the mark, not the ask
    p, oid, q = eng._place_butterfly(fly_signal(net_debit=0.90), 3)
    assert p == pytest.approx(0.90) and q == 3
    assert paper_fill_credit(1.50) == pytest.approx(1.50)   # credits too


def test_paper_friction_knob_applies_to_every_path(monkeypatch):
    monkeypatch.setattr(cfg, "PAPER_FILL_SLIPPAGE_PCT", 0.01, raising=False)
    monkeypatch.setattr(ee, "get_trade_logger", lambda: None)
    eng = EntryEngine(paper_trading=True)

    p, oid, q = eng._place_single_leg(single_signal(mark=2.00), 2)
    assert p == pytest.approx(2.02) and q == 2       # debit pays MORE
    p, oid, q = eng._place_butterfly(fly_signal(net_debit=0.90), 3)
    assert p == pytest.approx(0.91) and q == 3       # debit pays MORE (2dp)
    assert paper_fill_credit(1.50) == pytest.approx(1.485)  # credit gets LESS
    # the condor leg and the rolled vertical share this helper, so the knob
    # can no longer reach one strategy and miss another.
