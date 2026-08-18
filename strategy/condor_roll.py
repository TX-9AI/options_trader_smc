"""
strategy/condor_roll.py — Broken-wing roll of a live iron condor. v1.1
v1.1 — 2026-07-31 — AC: the missing-mark path was a SILENT return. This one
        declines a roll on a LIVE position with one side already tested — the
        roll IS the risk-reduction step, so a quiet refusal is the most
        consequential of the three silent declines. Now names which leg had no
        mark and states the position was left as-is.
v3.8 — 2026-07-22 — paper roll credit routed through limit_ladder
        .paper_fill_credit (audit defect T): the rolled vertical applied
        PAPER_FILL_SLIPPAGE_PCT inline, one of the two credit paths that kept
        a haircut after entry_engine v3.8 dropped it for debits. One authority,
        one knob (default 0.0 = book the mark). Same 4dp precision as before;
        no live-path change.
v3.7 — 2026-07-15 — ROLL IS REAL (audit defect P). Step 1 (close old untested
        vertical): both modes route through place_exit_order and book the
        FillResult's ACTUAL fill price — the old code booked plan.close_cost
        even when the confirmed live fill differed. Step 2 (open rolled
        vertical): a REAL signed-credit limit order is placed and
        fill-confirmed via execution/order_confirm — the old code wrote the
        DB record without placing ANY live order (a fictional position). The
        record books ONLY confirmed contracts at the broker's net credit;
        paper mirrors live friction via PAPER_FILL_SLIPPAGE_PCT. If the open
        fails after the close succeeded, position-truth is preserved (DB
        matches broker), a HALF-COMPLETE page fires, and the roll re-evaluates
        on a later tick with a fresh plan. The risk-free claim is re-checked
        against the ACTUAL fill credit and pages if the fills came in light.
v3.1 — 2026-07-15 — FillResult adoption: the live roll-close of the untested
        vertical now goes through the confirmed-fill contract (place_exit_order
        returns FillResult); the roll aborts and leaves the position OPEN unless
        the close is broker-confirmed, instead of treating order submission as a
        completed close. No paper-path change.
v3.0 — 2026-07-02 — initial build.
v3.0 — 2026-07-10 — repo-wide v3.0 bump: Yahoo-Finance purge & data stream
        mapping optimization (all market data now flows from the single
        shared TastyTrade candle feed — see data/candle_feed.py). No logic
        change in this file.

When BOTH condor verticals are open and price tests ONE side, a professional
adjustment is to roll the UNTESTED side toward price to collect additional
credit. If the cumulative credit collected covers the tested side's width, the
tested side becomes RISK-FREE — the structure is now a broken-wing butterfly.

Risk-free condition (the whole point):
    total_credit_collected  >=  tested_side_width
    (both in per-share terms; ×100 is the dollar figure)

    where total_credit_collected = banked_condor_credit
                                   + roll_credit (new untested vertical)
                                   - close_cost  (buying back the old untested vertical)

This module:
  1. classify_tested()      — which side is being tested, which is untested.
  2. find_risk_free_roll()  — pure premium math over live chain marks; finds the
                              smallest roll of the untested side that makes the
                              tested side risk-free (smallest roll = least new
                              risk on the rolled side).
  3. check_and_execute_roll() — orchestrator: detect, solve, and (only if a
                              risk-free roll exists) execute it, marking the
                              result a broken wing.

HARD CONTRACT: the roll is the FINAL adjustment. Once rolled, every leg is
flagged is_broken_wing=1 and this module never touches it again — it is managed
to exit only (stop / target / nickel), no further rolls.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Optional, List, Tuple

from config import STRIKE_INCREMENT, CONTRACT_MULTIPLIER
from utils.time_utils import fmt_et_short

logger = logging.getLogger(__name__)


@dataclass
class RollPlan:
    tested_side:        str    # "call" or "put" — the threatened side (goes risk-free)
    untested_side:      str    # the side we roll toward price
    new_short_strike:   float
    new_long_strike:    float
    new_short_symbol:   str
    new_long_symbol:    str
    roll_credit:        float  # per-share credit of the new untested vertical
    close_cost:         float  # per-share debit to buy back the old untested vertical
    total_credit_after: float  # cumulative per-share credit after the roll
    tested_width:       float
    risk_free:          bool
    contracts:          int


def _mark_at(contracts, strike: float) -> Optional[float]:
    return next((c.mark for c in contracts if c.strike == strike and c.mark > 0), None)


def _contract_at(contracts, strike: float):
    return next((c for c in contracts if c.strike == strike and c.mark > 0), None)


def classify_tested(legs: List[dict], current_price: float,
                    proximity_strikes: int = 1) -> Tuple[Optional[dict], Optional[dict]]:
    """Return (tested_leg, untested_leg). A side is 'tested' when price is within
    proximity_strikes of that side's short strike (or beyond it)."""
    call_leg = next((l for l in legs if l.get("option_side") == "call"), None)
    put_leg  = next((l for l in legs if l.get("option_side") == "put"),  None)
    if not (call_leg and put_leg):
        return None, None

    prox = proximity_strikes * STRIKE_INCREMENT
    if current_price >= call_leg["short_strike"] - prox:
        return call_leg, put_leg      # call tested, put untested
    if current_price <= put_leg["short_strike"] + prox:
        return put_leg, call_leg      # put tested, call untested
    return None, None


def find_risk_free_roll(tested_leg: dict, untested_leg: dict, chain,
                        current_price: float,
                        banked_credit: float) -> Optional[RollPlan]:
    """Solve for the smallest roll of the untested side that makes the tested
    side risk-free. Returns the best RollPlan found (risk_free flag set), or
    None if the chain can't be priced."""
    tested_side   = tested_leg["option_side"]
    untested_side = untested_leg["option_side"]
    tested_width  = float(tested_leg["spread_width"])
    wing          = float(untested_leg["spread_width"])
    contracts     = int(untested_leg.get("contracts", 1))

    u_list = chain.puts if untested_side == "put" else chain.calls

    # Cost to buy back the existing (cheap, far-OTM) untested vertical.
    old_short_m = _mark_at(u_list, untested_leg["short_strike"])
    old_long_m  = _mark_at(u_list, untested_leg["long_strike"])
    if old_short_m is None or old_long_m is None:
        # AC 2026-07-31 — was a SILENT return. This refuses a roll on a LIVE
        # position with one side tested: the roll is the risk-reduction step,
        # so declining it quietly is the worst of the three silent declines.
        _missing = ("short" if old_short_m is None else "") + \
                   ("/long" if old_long_m is None else "")
        logger.info(
            f"Condor roll SKIPPED: no mark for the untested {untested_side} "
            f"vertical ({_missing.strip('/')} leg) — strikes "
            f"{untested_leg['short_strike']:g}/{untested_leg['long_strike']:g}, "
            f"{len(u_list)} contracts in chain. Position left as-is."
        )
        return None
    close_cost = max(old_short_m - old_long_m, 0.0)

    # Candidate short strikes for the rolled vertical, marching from the current
    # short strike TOWARD price (roll up for puts, down for calls). Smallest roll
    # that reaches risk-free wins → least new risk on the rolled side.
    inc = STRIKE_INCREMENT
    candidates: List[float] = []
    if untested_side == "put":
        k = untested_leg["short_strike"] + inc
        while k <= current_price:
            candidates.append(k); k += inc
    else:  # call side rolled down toward price
        k = untested_leg["short_strike"] - inc
        while k >= current_price:
            candidates.append(k); k -= inc

    best: Optional[RollPlan] = None
    for new_short in candidates:
        new_long = new_short - wing if untested_side == "put" else new_short + wing
        ns = _contract_at(u_list, new_short)
        nl = _contract_at(u_list, new_long)
        if ns is None or nl is None:
            continue
        roll_credit = ns.mark - nl.mark
        if roll_credit <= 0:
            continue
        total_after = banked_credit + roll_credit - close_cost
        plan = RollPlan(
            tested_side=tested_side, untested_side=untested_side,
            new_short_strike=new_short, new_long_strike=new_long,
            new_short_symbol=ns.symbol, new_long_symbol=nl.symbol,
            roll_credit=roll_credit, close_cost=close_cost,
            total_credit_after=total_after, tested_width=tested_width,
            risk_free=(total_after >= tested_width), contracts=contracts,
        )
        # Track the best (highest cumulative credit) and return the FIRST one
        # that is risk-free (smallest roll toward price).
        if best is None or plan.total_credit_after > best.total_credit_after:
            best = plan
        if plan.risk_free:
            return plan
    return best


def check_and_execute_roll(pos_mgr, chain, current_price: float, state) -> bool:
    """If both condor verticals are open and one side is tested, roll the
    untested side into a broken wing — but ONLY if that roll makes the tested
    side risk-free. Returns True if a roll was executed."""
    if chain is None:
        return False

    legs = [r for r in pos_mgr.get_open_records() if r.get("is_condor_leg")]
    if len(legs) != 2:
        return False
    # Final-form guard: never touch a position that has already been rolled.
    if any(r.get("is_broken_wing") for r in legs):
        return False

    tested, untested = classify_tested(legs, current_price)
    if tested is None:
        return False

    banked_credit = sum(float(l.get("credit_received", l.get("entry_premium", 0.0)))
                        for l in legs)
    plan = find_risk_free_roll(tested, untested, chain, current_price, banked_credit)
    if plan is None or not plan.risk_free:
        # No roll available that removes tested-side risk — manage normally.
        return False

    return _execute_roll(pos_mgr, tested, untested, plan, state)


def _execute_roll(pos_mgr, tested: dict, untested: dict,
                  plan: RollPlan, state) -> bool:
    """Close the old untested vertical, open the rolled vertical, and flag the
    whole structure a broken wing (final form — no further adjustments)."""
    from database.trade_logger import make_record, get_trade_logger
    from execution.exit_engine import get_exit_engine
    from notifications.alert_manager import get_alert_manager
    from config import INSTRUMENT, CONDOR_STOP_LOSS_PCT, CONDOR_NICKEL_CLOSE

    tl        = get_trade_logger()
    mode      = "PAPER" if state.paper_trading else "LIVE"
    contracts = plan.contracts

    try:
        # ── 1. Close the OLD untested vertical (buy it back) ──────────────────
        # v3.7 (defect P): BOTH modes route through place_exit_order and book
        # the FillResult's ACTUAL fill price — paper simulates at plan.close_cost
        # (same as every other paper exit), live is the broker's confirmed net.
        # The old code booked plan.close_cost even when the live fill differed.
        fill = get_exit_engine(state.paper_trading).place_exit_order(
            untested, "rolled_to_broken_wing",
            mark_price=plan.close_cost)
        if not fill.confirmed or fill.fill_price is None:
            logger.error("Roll aborted — untested vertical close not confirmed "
                         f"({fill.detail or 'no fill'}); leaving position OPEN")
            return False
        close_price = float(fill.fill_price)
        old_credit = float(untested.get("credit_received", untested.get("entry_premium", 0.0)))
        pnl_close  = (old_credit - close_price) * contracts * CONTRACT_MULTIPLIER
        tl.log_exit(untested["trade_id"], exit_price=close_price,
                    pnl_usd=pnl_close, exit_reason="rolled_to_broken_wing")
        pos_mgr.remove_record(untested["trade_id"])

        # ── 2. Open the ROLLED untested vertical (the new risk side) ──────────
        # v3.7 (defect P): a REAL order, fill-confirmed. The old code wrote the
        # DB record without placing ANY live order — a fictional position. Now:
        # live places the signed-credit limit and books ONLY the confirmed
        # contracts at the broker's net credit; paper mirrors live friction via
        # PAPER_FILL_SLIPPAGE_PCT (same as condor entries). If the open fails
        # AFTER the close succeeded, position-truth is preserved (DB matches
        # broker: old vertical gone, no new one) — we alert loudly and return
        # False; the roll conditions re-evaluate on a later tick with a fresh
        # plan.
        roll_qty = contracts
        if not state.paper_trading:
            from data.tasty_client import get_session, get_account
            from execution.order_confirm import confirm_order_fill
            from tastytrade.order import (
                NewOrder, Leg, OrderAction, OrderType, OrderTimeInForce,
                InstrumentType,
            )
            from decimal import Decimal

            session = get_session()
            account = get_account()
            legs = [
                Leg(instrument_type=InstrumentType.EQUITY_OPTION,
                    symbol=plan.new_short_symbol,
                    action=OrderAction.SELL_TO_OPEN, quantity=contracts),
                Leg(instrument_type=InstrumentType.EQUITY_OPTION,
                    symbol=plan.new_long_symbol,
                    action=OrderAction.BUY_TO_OPEN, quantity=contracts),
            ]
            order = NewOrder(
                time_in_force = OrderTimeInForce.DAY,
                order_type    = OrderType.LIMIT,
                price         = Decimal(str(round(plan.roll_credit, 2))),  # + = credit
                legs          = legs,
            )
            response = account.place_order(session, order, dry_run=False)
            if response.errors:
                logger.error(f"Rolled vertical order failed: {response.errors}")
                get_alert_manager()._send(
                    f"\U0001F6A8 [{mode}] ROLL HALF-COMPLETE: closed old "
                    f"{plan.untested_side} vertical but the rolled open was "
                    f"REJECTED — tested side is NOT risk-free; will re-evaluate")
                return False
            ofill = confirm_order_fill(
                session, account, response.order,
                [(plan.new_short_symbol, 1, +1), (plan.new_long_symbol, 1, -1)],
                what="rolled-vertical entry")
            if not ofill.filled or ofill.net_price is None or ofill.quantity <= 0:
                if ofill.working_order_id:
                    get_alert_manager()._send(
                        f"\U0001F6A8 [{mode}] rolled-vertical order "
                        f"{ofill.working_order_id} could not be cancelled and "
                        f"may still fill — reconcile will adopt it")
                get_alert_manager()._send(
                    f"\U0001F6A8 [{mode}] ROLL HALF-COMPLETE: closed old "
                    f"{plan.untested_side} vertical but the rolled open did NOT "
                    f"fill ({ofill.detail}) — tested side is NOT risk-free; "
                    f"will re-evaluate")
                return False
            roll_credit_fill = float(ofill.net_price)   # broker net, not the plan
            roll_qty         = int(ofill.quantity)
            roll_order_id    = ofill.order_id or ""
            if roll_qty < contracts:
                get_alert_manager()._send(
                    f"\u26A0\uFE0F [{mode}] rolled vertical PARTIAL: "
                    f"{roll_qty}/{contracts} filled — structure quantities "
                    f"are mismatched; booking the filled size")
        else:
            # v3.8: one paper-pricing authority for every path. Default 0.0
            # books the mark; a non-zero knob reduces the credit received.
            from execution.limit_ladder import paper_fill_credit
            roll_credit_fill = paper_fill_credit(plan.roll_credit)
            roll_order_id    = "PAPER"

        new_width  = abs(plan.new_short_strike - plan.new_long_strike)
        new_maxloss = (new_width - roll_credit_fill) * roll_qty * CONTRACT_MULTIPLIER
        rolled = make_record(
            trade_id        = str(uuid.uuid4()),
            symbol          = INSTRUMENT,
            strategy        = "IronCondorStrategy",
            setup_type      = f"BWB rolled {plan.untested_side} vertical",
            setup_grade     = "B",
            direction       = "neutral",
            option_side     = plan.untested_side,
            strike          = plan.new_short_strike,
            short_strike    = plan.new_short_strike,
            long_strike     = plan.new_long_strike,
            spread_width    = new_width,
            credit_received = roll_credit_fill,       # CONFIRMED credit, not plan
            contracts       = roll_qty,               # CONFIRMED quantity
            entry_premium   = roll_credit_fill,
            total_cost      = new_maxloss,
            max_loss        = new_maxloss,
            stop_premium    = roll_credit_fill * (1 + CONDOR_STOP_LOSS_PCT),
            target_premium  = CONDOR_NICKEL_CLOSE,
            regime          = "RANGING",
            is_condor_leg   = 1,
            is_broken_wing  = 1,                       # FINAL FORM
            short_symbol    = plan.new_short_symbol,
            long_symbol     = plan.new_long_symbol,
            option_symbol   = plan.new_short_symbol,
            order_id        = roll_order_id,
            paper_trade     = 1 if state.paper_trading else 0,
            status          = "open",
        )
        tl.log_entry(rolled)
        pos_mgr.add_condor_leg(rolled)

        # v3.7: the risk-free claim must survive contact with the ACTUAL fill.
        # The plan asserted risk_free using plan.roll_credit; if the confirmed
        # credit came in lighter, re-check and say so — the structure is still
        # booked truthfully either way, but nobody should believe a risk-free
        # label the fills didn't pay for.
        actual_total_credit = (plan.total_credit_after
                               - plan.roll_credit + roll_credit_fill)
        if actual_total_credit < plan.tested_width:
            get_alert_manager()._send(
                f"\u26A0\uFE0F [{mode}] ROLL FILLED LIGHT: actual credit "
                f"${actual_total_credit:.2f} < tested width "
                f"${plan.tested_width:.2f} — structure is NOT fully risk-free")

        # ── 3. Flag the TESTED (now risk-free) vertical a broken wing too ─────
        tl.update_fields(tested["trade_id"], is_broken_wing=1)
        tested["is_broken_wing"] = 1

        get_alert_manager()._send(
            f"\U0001F98B [{mode}] ROLLED TO BROKEN WING | "
            f"{plan.tested_side} side now RISK-FREE "
            f"(credit ${plan.total_credit_after:.2f} >= width ${plan.tested_width:.2f}) | "
            f"rolled {plan.untested_side} to {plan.new_short_strike:.0f}/{plan.new_long_strike:.0f} "
            f"for ${plan.roll_credit:.2f} | final form | {fmt_et_short()}"
        )
        logger.info(
            f"[{mode}] BROKEN-WING ROLL: {plan.tested_side} side risk-free "
            f"(cum credit ${plan.total_credit_after:.2f} >= width ${plan.tested_width:.2f}); "
            f"rolled {plan.untested_side} -> {plan.new_short_strike:.0f}/{plan.new_long_strike:.0f} "
            f"credit ${plan.roll_credit:.2f}. FINAL FORM — no further adjustments."
        )
        return True

    except Exception as e:
        logger.error(f"Broken-wing roll failed: {e}")
        return False
