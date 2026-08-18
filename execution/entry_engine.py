"""
execution/entry_engine.py — Options order placement via TastyTrade SDK.
v3.9 — 2026-07-22 — DOC TRUTH + shared paper authority (audit defect T).
        v3.8 said paper "books the MARK", which was true only because the
        knob was being ignored here while condor legs still applied it. Paper
        debit fills still route through limit_ladder.paper_fill_price — no
        call-site change — but that helper (v1.3) now honours
        PAPER_FILL_SLIPPAGE_PCT for every path uniformly, default 0.0 = the
        mark. So the v3.8 behaviour is the DEFAULT, not a hardcode, and the
        knob is a fleet-wide stress lever again.
v3.8 — 2026-07-22 — MARK-LIMIT ENTRIES. Single-leg entry was a MARKET order
        (paid the ask while the signal was scored on the mark). It now posts a
        LIMIT at the mark and lets it sit; unfilled orders are cancelled by
        confirm_order_fill and the strategy re-signals next tick against a
        fresh mark. Paper fills book the MARK for both single-leg and
        butterfly (was mark * (1 + PAPER_FILL_SLIPPAGE_PCT)) so paper and live
        trade on the same principle — the residual gap is no-fill risk, not
        slippage.
v3.7 — 2026-07-15 — ENTRY FILL-CONFIRMATION (audit defect O, parts 2+3).
        Records are written ONLY for broker-confirmed fills at the broker's
        actual fill price, for the quantity that actually filled — never on
        submission, never at the signal mark, never at our limit.
        SINGLE LEG: still a MARKET order, but the fill price is now READ BACK
        from the order's fills via order_confirm (the old code booked
        `placed.price or signal.entry_premium` — a market order has no
        .price, so live entries were ALWAYS recorded at the signal mark).
        BUTTERFLY: rebuilt. (a) debit priced NEGATIVE per the SDK's signed
        convention (the old positive price demanded a CREDIT to open a debit
        fly — could never fill; price_effect is ignored by current SDKs and
        is gone); (b) fill detection is a bounded poll via
        confirm_order_fill, not an instant status peek (which always saw
        Received/Routed and churned place→cancel→place); (c) the
        double-position race is closed: a second attempt is placed ONLY after
        the first is confirmed dead with zero fills — an uncancellable order
        stops the ladder, pages, and is adopted by reconcile if it fills;
        (d) a PARTIAL fill is booked at its weighted net for the filled size.
        Butterfly records now persist lower/center/upper leg SYMBOLS —
        without them the v3.5 live close and reconcile leg-matching both fail.
        enter() sizes the record from the CONFIRMED quantity. Paper is
        unchanged in shape (fills at mark ± PAPER_FILL_SLIPPAGE_PCT in one
        pass) and returns the requested quantity — mirroring live as closely
        as a simulator without a book can.
v3.0 — original release
v1.1 — 2026-06-27 — store orb_range_high/low in TradeRecord so exit_engine
        can detect ORB range violations on 1-min candle closes
v3.0 — 2026-07-10 — repo-wide v3.0 bump: Yahoo-Finance purge & data stream
        mapping optimization (all market data now flows from the single
        shared TastyTrade candle feed — see data/candle_feed.py). No logic
        change in this file.

Order types:
  - Single-leg (ORB, SweepReversal): MARKET order, fill price read back from
    the broker's fills (bounded confirmation poll).
  - Multi-leg butterfly: signed-DEBIT limit at MID; if confirmed dead unfilled,
    ONE retry improved by LIMIT_IMPROVE_TICKS. Never pays worse than
    mid + 1 tick; never places attempt 2 while attempt 1 might still fill.

Paper mode: books limit_ladder.paper_fill_price (the mark by default;
mark ± PAPER_FILL_SLIPPAGE_PCT when the stress knob is set). No real order.
"""
# v-obs2 (2026-07-24) — entry record now also stores swept_level_name + level_strength.

# v-obs (2026-07-24) — directional entry record now stores adx_at_entry / regime_conviction / flat_angle_deg from the signal.


import logging
import time
import uuid
from decimal import Decimal
from typing import Optional, Tuple

from tastytrade.order import (
    NewOrder, Leg, OrderAction, OrderType, OrderTimeInForce,
    InstrumentType
)

from execution.order_confirm import confirm_order_fill
from execution.limit_ladder import limit_at_mark, paper_fill_price

from strategy.base_strategy import OptionsSignal
from risk.setup_scorer import SetupScore
from risk.risk_manager import SizingResult
from database.trade_logger import TradeRecord, make_record, get_trade_logger
from data.tasty_client import get_session, get_account, TastyClientError
from config import (
    PAPER_TRADING, PAPER_FILL_SLIPPAGE_PCT,
    CONTRACT_MULTIPLIER, INSTRUMENT,
    LIMIT_IMPROVE_TICKS
)
from utils.time_utils import ts_for_db, fmt_et_short

logger = logging.getLogger(__name__)


class EntryEngine:
    """Places orders for all strategy types and returns a populated TradeRecord."""

    def __init__(self, paper_trading: bool = PAPER_TRADING):
        self.paper_trading = paper_trading
        self._trade_logger = get_trade_logger()

    def enter(self,
              signal:  OptionsSignal,
              score:   SetupScore,
              sizing:  SizingResult) -> Optional[TradeRecord]:
        """
        Place entry order and record the trade.
        Returns TradeRecord on success, None on failure.
        """
        mode = "PAPER" if self.paper_trading else "LIVE"

        if signal.is_butterfly:
            logger.info(
                f"[{mode}] BUTTERFLY ENTRY: "
                f"{signal.butterfly_direction.upper()} "
                f"{sizing.contracts} × "
                f"{signal.lower_contract.strike}/"
                f"{signal.center_contract.strike}/"
                f"{signal.upper_contract.strike} "
                f"net_debit=${signal.net_debit:.2f} "
                f"grade={score.grade}"
            )
            fill_premium, order_id, filled_qty = self._place_butterfly(
                signal, sizing.contracts)
        else:
            logger.info(
                f"[{mode}] DIRECTIONAL ENTRY: "
                f"{signal.option_side.upper()} {signal.strike} "
                f"{sizing.contracts} contract(s) "
                f"mark=${signal.entry_premium:.2f} "
                f"grade={score.grade}"
            )
            fill_premium, order_id, filled_qty = self._place_single_leg(
                signal, sizing.contracts)

        if fill_premium is None or filled_qty <= 0:
            logger.error("Entry order failed — no confirmed fill, no position recorded")
            return None
        if filled_qty < sizing.contracts:
            logger.warning(
                f"[{mode}] Entry PARTIAL: {filled_qty}/{sizing.contracts} "
                f"filled — recording the filled size")

        total_cost = fill_premium * filled_qty * CONTRACT_MULTIPLIER

        record = make_record(
            trade_id          = str(uuid.uuid4()),
            symbol            = INSTRUMENT,
            strategy          = signal.strategy_name,
            setup_type        = signal.setup_type,
            setup_grade       = score.grade,
            setup_score       = score.score,
            direction         = signal.direction,
            option_side       = signal.option_side if not signal.is_butterfly else signal.butterfly_direction,
            is_butterfly      = signal.is_butterfly,
            strike            = signal.strike if not signal.is_butterfly else signal.center_contract.strike,
            expiry            = signal.expiry if not signal.is_butterfly else signal.center_contract.expiry,
            contracts         = filled_qty,
            entry_premium     = fill_premium,
            total_cost        = total_cost,
            max_loss          = total_cost,
            stop_premium      = signal.stop_premium(),
            trail_activation  = signal.trail_activation_premium(),
            target_premium    = signal.target_premium(),
            underlying_entry  = signal.underlying_entry,
            underlying_stop   = signal.underlying_stop,
            underlying_target = signal.underlying_target,
            regime            = signal.regime,
            vix_at_entry      = signal.vix_at_signal,
            adx_at_entry      = getattr(signal, 'adx_at_signal', 0.0),
            regime_conviction = getattr(signal, 'conviction', 0.0),
            flat_angle_deg    = getattr(signal, 'flat_angle_deg', 0.0),
            swept_level_name  = getattr(signal, 'swept_level_name', ''),
            level_strength    = getattr(signal, 'level_strength', 0.0),
            is_fed_day        = signal.is_fed_day,
            order_id          = order_id,
            paper_trade       = 1 if self.paper_trading else 0,
            status            = "open",
            notes             = signal.notes,
        )

        if signal.is_butterfly:
            record["lower_strike"]  = signal.lower_contract.strike
            record["center_strike"] = signal.center_contract.strike
            record["upper_strike"]  = signal.upper_contract.strike
            record["net_debit"]     = signal.net_debit
            record["max_profit"]    = signal.max_profit
            # v3.7: leg SYMBOLS persisted — the live close (exit_engine v3.5
            # _close_butterfly) and reconcile leg-matching both require them.
            record["lower_symbol"]  = signal.lower_contract.symbol
            record["center_symbol"] = signal.center_contract.symbol
            record["upper_symbol"]  = signal.upper_contract.symbol

        # ── ORB range boundaries — persisted for exit_engine range violation ──
        # exit_engine checks if 1-min close goes back inside the ORB range
        if signal.is_orb:
            record["orb_range_high"] = signal.orb_range_high
            record["orb_range_low"]  = signal.orb_range_low

        self._trade_logger.log_entry(record)

        logger.info(
            f"✅ Entry confirmed [{mode}]: "
            f"ID={record['trade_id'][:8]} "
            f"fill=${fill_premium:.2f}/share "
            f"total=${total_cost:.2f}"
        )
        return record

    # ─── Order Placement ──────────────────────────────────────────────────────

    def _place_single_leg(self, signal: OptionsSignal,
                           contracts: int) -> Tuple[Optional[float], str, int]:
        """Returns (fill_price, order_id, filled_qty). Live fill price is READ
        BACK from the broker's fills — a market order has no .price, so the
        old `placed.price or signal.entry_premium` always booked the signal
        mark. filled_qty==0 means record NOTHING."""
        if self.paper_trading:
            return self._paper_fill_single(signal, contracts)

        try:
            session  = get_session()
            account  = get_account()
            symbol   = signal.contract.symbol

            leg = Leg(
                instrument_type = InstrumentType.EQUITY_OPTION,
                symbol          = symbol,
                action          = OrderAction.BUY_TO_OPEN,
                quantity        = contracts,
            )
            # v3.8: MARK-LIMIT ENTRY (was MARKET). A market entry paid the ask
            # while the signal that justified the trade was scored on the mark —
            # on a $0.20 0DTE with a $0.05 spread that is ~12% of premium before
            # the position even moves. We post AT THE MARK and let it sit. An
            # entry that does not fill costs NOTHING: confirm_order_fill cancels
            # and we walk away, and the strategy re-signals next tick against a
            # FRESH mark (that re-anchoring is what tracks a moving market —
            # there is no stale resting order). Debit paid -> price NEGATIVE per
            # the SDK signed convention.
            mid = float(signal.entry_premium or 0.0)
            if mid <= 0:
                logger.warning("Single-leg entry: no mark to price the limit — "
                               "skipping this pass")
                return None, "", 0
            limit = limit_at_mark(mid, floor=0.01)
            order = NewOrder(
                time_in_force = OrderTimeInForce.DAY,
                order_type    = OrderType.LIMIT,
                price         = Decimal(str(-limit)),   # - = DEBIT paid to open
                legs          = [leg],
            )
            response = account.place_order(session, order, dry_run=False)
            if response.errors:
                logger.error(f"Order errors: {response.errors}")
                return None, "", 0

            fill = confirm_order_fill(session, account, response.order,
                                      [(symbol, 1, +1)],
                                      what=f"single-leg entry (LIMIT @ mark {limit:.2f})")
            if not fill.filled or fill.net_price is None:
                self._page_if_working(fill, "single-leg entry")
                logger.warning(f"Single-leg entry NOT filled ({fill.detail})")
                return None, "", 0
            return fill.net_price, fill.order_id or "", fill.quantity

        except Exception as e:
            logger.error(f"Single-leg order failed: {e}")
            return None, "", 0

    def _place_butterfly(self, signal: OptionsSignal,
                          contracts: int) -> Tuple[Optional[float], str, int]:
        """Returns (net_debit_fill, order_id, filled_qty). v3.7 rebuild:

        - debit priced NEGATIVE (SDK signed convention — the old positive
          price demanded a CREDIT to open a debit fly and could never fill);
        - each attempt is confirmed via a bounded poll, not an instant
          status peek;
        - attempt 2 (mid improved by LIMIT_IMPROVE_TICKS) is placed ONLY
          after attempt 1 is confirmed DEAD with ZERO fills. A partial fill
          on attempt 1 is booked as the position (no re-place — that would
          risk overfilling). An uncancellable order stops the ladder, pages,
          and reconcile adopts any late fill. Never pays worse than
          mid + LIMIT_IMPROVE_TICKS ticks."""
        if self.paper_trading:
            return self._paper_fill_butterfly(signal, contracts)

        try:
            session = get_session()
            account = get_account()
            mid     = signal.net_debit
            basis   = [(signal.lower_contract.symbol,  1, +1),
                       (signal.center_contract.symbol, 2, -1),
                       (signal.upper_contract.symbol,  1, +1)]

            for attempt in range(2):
                limit_price = round(mid + attempt * LIMIT_IMPROVE_TICKS * 0.01, 2)
                legs = [
                    Leg(instrument_type=InstrumentType.EQUITY_OPTION,
                        symbol=signal.lower_contract.symbol,
                        action=OrderAction.BUY_TO_OPEN, quantity=contracts),
                    Leg(instrument_type=InstrumentType.EQUITY_OPTION,
                        symbol=signal.center_contract.symbol,
                        action=OrderAction.SELL_TO_OPEN, quantity=contracts * 2),
                    Leg(instrument_type=InstrumentType.EQUITY_OPTION,
                        symbol=signal.upper_contract.symbol,
                        action=OrderAction.BUY_TO_OPEN, quantity=contracts),
                ]
                order = NewOrder(
                    time_in_force = OrderTimeInForce.DAY,
                    order_type    = OrderType.LIMIT,
                    price         = Decimal(str(-limit_price)),  # − = DEBIT paid
                    legs          = legs,
                )
                response = account.place_order(session, order, dry_run=False)
                if response.errors:
                    logger.error(f"Butterfly attempt {attempt+1} order errors: "
                                 f"{response.errors}")
                    if attempt == 1:
                        return None, "", 0
                    continue

                fill = confirm_order_fill(session, account, response.order,
                                          basis, what=f"butterfly entry #{attempt+1}")
                if fill.filled and fill.net_price is not None and fill.quantity > 0:
                    return fill.net_price, fill.order_id or "", fill.quantity
                if fill.working_order_id:
                    # Attempt 1 may still fill — placing attempt 2 now is the
                    # double-position race. STOP the ladder; page; reconcile
                    # adopts whatever lands.
                    self._page_if_working(fill, "butterfly entry")
                    return None, "", 0
                logger.info(f"Butterfly attempt {attempt+1} confirmed dead "
                            f"unfilled ({fill.detail})"
                            + (" — improving 1 tick and retrying" if attempt == 0
                               else " — giving up"))
            return None, "", 0

        except Exception as e:
            logger.error(f"Butterfly order failed: {e}")
            return None, "", 0

    @staticmethod
    def _page_if_working(fill, what: str):
        """An entry order that could not be cancelled may still fill — page
        once so it's watched; broker reconciliation ADOPTS any late fill."""
        if not fill.working_order_id:
            return
        try:
            from notifications.alert_manager import get_alert_manager
            get_alert_manager()._send(
                f"\U0001F6A8 {what}: order {fill.working_order_id} could not "
                f"be cancelled and may still fill — reconcile will adopt it. "
                f"({fill.detail})")
        except Exception as e:
            logger.warning(f"Working-order page failed to send: {e}")

    def _paper_fill_single(self, signal: OptionsSignal,
                           contracts: int) -> Tuple[float, str, int]:
        """v3.8: books the MARK, matching the live mark-limit entry.

        Was mark * (1 + PAPER_FILL_SLIPPAGE_PCT) — modelling the market order
        that live no longer sends. Under the mark-limit policy live either
        fills AT the mark or does not fill at all, so a slippage markup would
        now make paper PESSIMISTIC on price while still being optimistic on
        fill rate. The honest residual gap is no-fill risk, not slippage; see
        execution/limit_ladder.paper_fill_price."""
        fill_price = paper_fill_price(float(signal.entry_premium or 0.0), floor=0.01)
        return fill_price, f"PAPER-{uuid.uuid4().hex[:8].upper()}", contracts

    def _paper_fill_butterfly(self, signal: OptionsSignal,
                              contracts: int) -> Tuple[float, str, int]:
        """v3.8: books the MARK — see _paper_fill_single."""
        fill_price = paper_fill_price(float(signal.net_debit or 0.0), floor=0.01)
        return fill_price, f"PAPER-BF-{uuid.uuid4().hex[:8].upper()}", contracts


_entry_engine: Optional[EntryEngine] = None


def get_entry_engine(paper_trading: bool = PAPER_TRADING) -> EntryEngine:
    global _entry_engine
    if _entry_engine is None:
        _entry_engine = EntryEngine(paper_trading)
    return _entry_engine
