"""
execution/order_confirm.py — LIVE entry-order fill confirmation (audit defect O).
v1.0 — 2026-07-15 — initial. The ENTRY-side mirror of exit_engine v3.5's
        fill-confirmation: submit is NOT a fill, and a position may be recorded
        ONLY at the broker's actual per-leg net fill price, for the quantity
        that actually filled.

        Entry semantics differ from exits in one deliberate way: an exit MUST
        eventually happen (the caller retries and escalates), but an entry is
        OPTIONAL — if the order doesn't fill by the deadline we CANCEL and walk
        away; the strategy re-evaluates on a later tick with fresh marks.
        There is no cross-tick resume for entries. The one thing we never do is
        walk away from contracts that DID fill: a partial entry is booked at
        its weighted net price for the filled quantity (it is a real position
        and must be managed), and the unfilled remainder is cancelled.

        Safety net: if the cancel itself fails and the order is still working
        after retries, we return unfilled with the order id and page — anything
        that fills afterward is picked up by broker reconciliation's ADOPT path
        (which exists precisely for broker positions with no DB plan).

Used by: main._execute_condor_leg (v3.7). Built to be reused by
entry_engine's single-leg and butterfly paths and condor_roll's rolled
vertical (audit defects O-remainder and P).
"""

import logging
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

from tastytrade.order import OrderStatus

import config as _cfg

logger = logging.getLogger(__name__)

# States in which an order is still working at the broker.
WORKING_STATES = {
    OrderStatus.RECEIVED, OrderStatus.ROUTED, OrderStatus.IN_FLIGHT,
    OrderStatus.LIVE, OrderStatus.CONTINGENT,
    OrderStatus.CANCEL_REQUESTED, OrderStatus.REPLACE_REQUESTED,
}
# Terminal states that are not a full fill (may still carry partial fills).
DEAD_STATES = {
    OrderStatus.CANCELLED, OrderStatus.EXPIRED,
    OrderStatus.REMOVED, OrderStatus.PARTIALLY_REMOVED,
}


@dataclass
class EntryFill:
    """Outcome of an entry order after confirmation.

    filled=True means SOME quantity is confirmed filled and MUST be recorded
    as a position: `quantity` spread units at `net_price` per share on the
    caller's basis. filled=False means nothing filled — record NOTHING.
    `working_order_id` is set only in the pathological case where the order
    could not be cancelled and may still fill: page, and let reconciliation
    adopt whatever lands."""
    filled:           bool
    quantity:         int             = 0
    net_price:        Optional[float] = None
    order_id:         Optional[str]   = None
    detail:           str             = ""
    working_order_id: Optional[str]   = None


# A basis is how per-leg fills combine into the strategy's net price, matching
# the mark the P&L math uses:  net = Σ sign · ratio · leg_avg_fill,
# spread units filled = min(leg_filled / ratio).
#   credit vertical entry:  [(short_sym, 1, +1), (long_sym, 1, -1)]
#   long butterfly entry:   [(lower, 1, +1), (center, 2, -1), (upper, 1, +1)]
#   single leg:             [(sym, 1, +1)]
Basis = List[Tuple[str, int, int]]


def _leg_fill_stats(placed, symbol: str) -> Tuple[float, Optional[float]]:
    for leg in (getattr(placed, "legs", None) or []):
        if getattr(leg, "symbol", None) == symbol:
            fills = getattr(leg, "fills", None) or []
            q = sum(float(f.quantity) for f in fills)
            if q <= 0:
                return 0.0, None
            p = sum(float(f.quantity) * float(f.fill_price) for f in fills) / q
            return q, p
    return 0.0, None


def net_from_fills(placed, basis: Basis) -> Optional[Tuple[int, float]]:
    """(spread_units_filled, net_price) from a PlacedOrder's per-leg fills on
    the given basis, or None if nothing consistently filled."""
    units, net = None, 0.0
    for symbol, ratio, sign in basis:
        q, p = _leg_fill_stats(placed, symbol)
        leg_units = q / float(ratio)
        units = leg_units if units is None else min(units, leg_units)
        if p is None:
            return None
        # Marks are quoted per share of the combination (short−long;
        # lower+upper−2·center), i.e. Σ sign·ratio·leg_price — the basis
        # encodes exactly that, so fills land on the same scale as the marks
        # and entry_premium the P&L math compares against.
        net += sign * ratio * p
    if units is None or units <= 0:
        return None
    return int(units), round(net, 4)


def confirm_order_fill(session, account, placed, basis: Basis,
                       what: str = "entry") -> EntryFill:
    """Poll `placed` (a just-submitted PlacedOrder) to a bounded deadline and
    return what ACTUALLY filled. Never invents a price; never reports more
    than the broker confirms. Cancels the remainder at deadline."""
    order_id = getattr(placed, "id", None)
    if order_id is None:
        return EntryFill(filled=False, detail=f"{what}: no order id in response")

    poll     = max(0.0, float(getattr(_cfg, "LIVE_FILL_POLL_SECONDS", 2.0)))
    deadline = time.monotonic() + float(getattr(_cfg, "LIVE_ENTRY_DEADLINE_SECONDS", 20.0))
    cancel_requested = False
    cancel_attempts  = 0

    while True:
        try:
            placed = account.get_order(session, order_id)
        except Exception as e:
            logger.warning(f"{what} {order_id}: poll error ({e}) — retrying")
        status = placed.status

        if status == OrderStatus.FILLED:
            got = net_from_fills(placed, basis)
            if got is None:
                # Broker says filled but fills unreadable — do NOT invent a
                # price. Report unfilled-with-working-id so the caller pages;
                # reconciliation's adopt path will book broker truth.
                logger.error(f"{what} {order_id}: FILLED but fills unreadable")
                return EntryFill(filled=False, order_id=str(order_id),
                                 working_order_id=str(order_id),
                                 detail="filled but fills unreadable — reconcile will adopt")
            units, net = got
            return EntryFill(filled=True, quantity=units, net_price=net,
                             order_id=str(order_id),
                             detail=f"{what} confirmed fill {units} @ net {net}")

        if status == OrderStatus.REJECTED:
            why = getattr(placed, "reject_reason", None) or "unknown"
            return EntryFill(filled=False, order_id=str(order_id),
                             detail=f"rejected: {why}")

        if status in DEAD_STATES:
            got = net_from_fills(placed, basis)
            if got is not None and got[0] > 0:
                units, net = got
                logger.warning(f"{what} {order_id}: PARTIAL {units} filled, "
                               f"remainder {status} — booking the filled part")
                return EntryFill(filled=True, quantity=units, net_price=net,
                                 order_id=str(order_id),
                                 detail=f"partial fill {units} @ net {net}; remainder {status}")
            return EntryFill(filled=False, order_id=str(order_id),
                             detail=f"not filled ({status})")

        # Still working.
        if time.monotonic() >= deadline:
            if not cancel_requested or cancel_attempts < 3:
                try:
                    account.delete_order(session, order_id)
                    cancel_requested = True
                    cancel_attempts += 1
                    # grace to resolve the cancel/fill race
                    deadline = time.monotonic() + max(3 * poll, 6.0)
                    logger.info(f"{what} {order_id}: deadline — cancel requested, "
                                f"resolving race")
                    continue
                except Exception as e:
                    cancel_attempts += 1
                    logger.error(f"{what} {order_id}: cancel failed ({e}), "
                                 f"attempt {cancel_attempts}/3")
                    if cancel_attempts < 3:
                        deadline = time.monotonic() + max(2 * poll, 4.0)
                        continue
            # Cancel could not be confirmed — the order may still fill later.
            # This is the ONLY path that leaves a working order behind, and it
            # is reported loudly: reconciliation adopts whatever fills.
            logger.error(f"{what} {order_id}: UNRESOLVED working order after "
                         f"cancel attempts — reconcile will adopt any late fill")
            return EntryFill(filled=False, order_id=str(order_id),
                             working_order_id=str(order_id),
                             detail="deadline; cancel unconfirmed — order may still fill; "
                                    "reconcile will adopt")
        time.sleep(poll)
