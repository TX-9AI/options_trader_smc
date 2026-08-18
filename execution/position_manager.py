"""
execution/position_manager.py — v3.4 — AUDIT A2.2: expose the open condor-leg
v3.4  2026-08-17  SWALLOW T1: this file's silent handler(s) now announce
        themselves once. Behaviour unchanged in every case; only the silence
        was the defect.
        count for the orphan announcement. The F5 warning was wired to a call
        site that cannot run while a leg is open (attempt_new_entry sits
        behind has_open_position, which reads the same DB), so it could never
        fire. The manage branch announces instead, counting from the records
        this manager already holds - no second DB read on the hot path.
v3.2 — AUDIT F6 pairing: price a spread by
        STRUCTURE, not by is_condor_leg. main v6.9 stops stamping
        is_condor_leg=1 onto TC.6 records, and this module's premium fetch
        keyed on exactly that flag (or strategy=="IronCondorStrategy") — so
        without this change a TC.6 record would silently fall to the
        single-leg pricing path. is_credit_vertical() reads only persisted
        columns (strategy / setup_type), so condor legs, both TC.6 row
        generations, and the rolled broken wing all price as short-long.
        Ships in the SAME commit as main v6.9, deliberately.
v3.1 — VEL.1 stashes current_delta
        alongside current_theta: breakeven velocity is |theta|/(|delta|*1440),
        so theta alone cannot answer whether the position is gaining or
        bleeding. Manages the single open options position.
v3.9 — 2026-07-22 — remove the dead PAPER_FILL_SLIPPAGE_PCT import (audit
        defect T). This module has never priced a paper fill — entry pricing
        lives in entry_engine/main and exit pricing in exit_engine, both now
        via execution/limit_ladder. The unused import falsely implied this
        file was a third friction call site. Import-only change.
v3.8 — 2026-07-15 — thread df_5m to exit_engine.evaluate() so trails can
        anchor to 5-minute FVGs (exit_engine v3.8 runner refinements). 1m is
        untouched and remains the structure-stop/BOS timeframe.
v3.4 — 2026-07-15 — BOOK ONLY ON CONFIRMED FILL. _execute_exit() now consumes
        the FillResult from place_exit_order(): it books P&L ONLY when
        fill.confirmed is True and uses fill.fill_price (the ACTUAL close price
        — simulated mark in paper, broker fill in live), never the mark we
        passed nor entry-as-fallback. An unconfirmed result books NOTHING and
        leaves the row OPEN (anti-orphan invariant) so flatten_all's 15:45->16:00
        retry can act. Kills the hard-close $0.00 bookings. flatten_all still
        passes a chain (now supplied by handle_hard_close) so paper has a real
        mark to simulate against.
v3.1 — 2026-07-12 — F5 FIX: trail updates now write to the trail_stop column
        via update_trail_stop() instead of overwriting stop_premium/update_stop.
        stop_premium stays the immutable entry-time -25% floor, so the exit
        engine's floor checks and exit_reason labels are truthful again.
v3.0 — original release
v1.1 — 2026-06-27 — pass df_1m to exit_engine.evaluate() for strategy-aware
        ORB range violation and BOS exits
v1.2 — 2026-06-29 — use live chain marks in paper mode for accurate P&L display;
        butterfly mark computed from lower + upper - 2×center legs
v1.3 — 2026-06-30 — notify ORB engine when an ORB trade closes so it re-arms
        and watches for the next breakout attempt this session
v1.4 — 2026-06-30 — pass current regime to exit_engine.evaluate() so regime-flip
        exits can fire for butterfly and condor leg positions
v1.5 — 2026-07-02 — multi-position support for legged condors: hold up to two
        verticals at once (condor ONLY; every other strategy stays single),
        manage each independently, mark a leg as short_mark - long_mark, and
        invert P&L sign for credit spreads.
v1.6 — 2026-07-02 — add remove_record() for the broken-wing roll (drops the old
        untested vertical when it is rolled).
v1.7 — 2026-07-02 — pass realized P&L into record_win/record_loss so the risk
        manager can track NET daily P&L for the daily loss halt.
v1.8 — 2026-07-07 — set_open_positions(): resume a recovered SET of open rows
        wholesale (1 normally, 2 for a legged condor) so startup recovery
        manages exactly the rows that survived stale-orphan reconciliation
        without dropping a condor leg.
v1.9 — 2026-07-07 — flatten_all(): durable, complete forced close for the 15:45
        hard cutoff. Routes EVERY open record (all condor legs) through the full
        _execute_exit accounting so the DB row is actually marked closed and P&L
        booked — replacing main.py's old direct place_exit_order() that submitted
        an order but never wrote status='closed'. Returns trade_ids that failed
        to close so the caller can retry/escalate.
v2.1 — 2026-07-09 — _fetch_current_premium PAPER fallback fixed: on a chain miss
        it returned the ENTRY premium, so any exit taken during a chain gap booked
        exit==entry (P&L=$0) — a real loss recorded as a scratch, and the exit
        logic blinded to the true premium. Now returns the LAST-KNOWN mark
        (update_current_premium), surrendering to entry only if never priced.
v2.0 — 2026-07-07 — _execute_exit P&L is now credit-signed for an adopted SHORT
        (is_short_position), not just condor legs — so flatten_all/normal exits
        book a broker-adopted short's realized P&L with the correct sign.
v3.0 — 2026-07-10 — repo-wide v3.0 bump: Yahoo-Finance purge & data stream
        mapping optimization (all market data now flows from the single
        shared TastyTrade candle feed — see data/candle_feed.py). No logic
        change in this file.
"""

import logging
from typing import Optional, List

import pandas as pd

from database.trade_logger import TradeRecord, get_trade_logger
from strategy.structure import is_credit_vertical as _is_credit_vertical
from execution.exit_engine import get_exit_engine, ExitDecision
from data.tasty_client import get_client, TastyClientError
from risk.risk_manager import get_risk_manager
from notifications.alert_manager import get_alert_manager
from config import PAPER_TRADING, CONTRACT_MULTIPLIER

logger = logging.getLogger(__name__)
_WARNED_LEG_COUNT: set = set()   # SWALLOW T1: warn once on an unreadable count


class PositionManager:
    """
    Manages the bot's single open position (one trade at a time).
    Fetches live option premium, evaluates exits, and closes when triggered.
    """

    def __init__(self, paper_trading: bool = PAPER_TRADING):
        self.paper_trading = paper_trading
        self._open_records: List[TradeRecord] = []
        self._trade_logger = get_trade_logger()

    def open_condor_leg_count(self) -> int:
        """Open condor legs among the records this manager holds (A2.2).

        Counts from `_open_records` when loaded (the manage branch runs right
        after they are), falling back to the DB on a cold call. Returns 0 on
        any error: this feeds an ANNOUNCEMENT, and the occupancy guards
        elsewhere already fail closed - a missed log line costs less than a
        crashed tick."""
        try:
            recs = self._open_records or self._trade_logger.get_open_trades()
            return sum(1 for r in recs if r.get("is_condor_leg"))
        except Exception as exc:                               # noqa: BLE001
            # ⚠️ SWALLOW T1, 2026-08-17 — THIS RETURNED 0 SILENTLY, AND 0 IS THE
            # PERMISSIVE ANSWER. "No condor legs open" is what a caller checks
            # before opening another; a failed COUNT therefore reads as CLEAR TO
            # PROCEED. That is the F5 shape exactly — an unreadable input
            # granting permission it never established.
            # The count is left at 0 (callers treat a raise as fatal and this
            # runs on the tick path) but it is NO LONGER SILENT: a box that
            # cannot count its own open legs must be visible before it acts on
            # the answer.
            if not _WARNED_LEG_COUNT:
                _WARNED_LEG_COUNT.add(1)
                logger.warning(
                    "[legs] could not count open condor legs (%s) - reporting 0, "
                    "which reads as NO LEGS OPEN to every caller. If a leg IS "
                    "open, deferral and sibling checks are running blind.", exc)
            return 0

    def has_open_position(self) -> bool:
        if self._open_records:
            return True
        # Fresh process (restart): reload any open trades from the DB.
        trades = self._trade_logger.get_open_trades()
        if trades:
            self._open_records = trades
            return True
        return False

    def set_open_position(self, record: TradeRecord):
        """Single-position strategies (ORB, sweep, butterfly): exactly one."""
        self._open_records = [record]

    def set_open_positions(self, records: List[TradeRecord]):
        """Resume managing a recovered SET of open positions (one for normal
        strategies, two for a legged condor). Replaces the active set wholesale.
        Used by startup recovery so the first tick manages exactly the rows that
        survived stale-orphan reconciliation — without dropping a condor leg."""
        self._open_records = list(records)

    def flatten_all(self, reason: str, chain=None) -> List[str]:
        """Force-close EVERY open record through the full exit accounting.

        Unlike a bare exit_engine.place_exit_order() (which submits/simulates an
        order but never marks the DB row closed), this routes each record through
        _execute_exit() so status='closed', P&L, the exit alert, trail cleanup
        and ORB re-arm all happen — the row is genuinely, durably closed. Closes
        ALL records (both condor legs), not just the first. If a live mark can't
        be fetched, books at entry premium as a last resort so the row still
        closes rather than surviving as an orphan (P&L approximate — logged).

        Returns the list of trade_ids that FAILED to close (empty == fully flat),
        so the 15:45 caller can retry each tick and escalate.
        """
        if not self._open_records:
            self._open_records = self._trade_logger.get_open_trades()

        failed: List[str] = []
        for record in list(self._open_records):
            trade_id = record.get("trade_id", "")
            premium = self._fetch_current_premium(record, chain=chain)
            if premium is None:
                premium = float(record.get("entry_premium", 0.0) or 0.0)
                logger.warning(
                    f"Flatten {trade_id[:8]}: no live mark — booking at entry "
                    f"premium (P&L approximate) so the row still closes."
                )
            decision = ExitDecision(should_exit=True, exit_reason=reason)
            if self._execute_exit(record, decision, premium):
                self._open_records = [r for r in self._open_records
                                      if r.get("trade_id") != trade_id]
            else:
                failed.append(trade_id)
                logger.error(f"Flatten FAILED for {trade_id[:8]} — will retry")
        return failed

    def add_condor_leg(self, record: TradeRecord):
        """The condor is the ONLY strategy allowed a second concurrent position
        (its two verticals). Appends rather than replacing."""
        self._open_records.append(record)

    def get_open_record(self) -> Optional[TradeRecord]:
        return self._open_records[0] if self._open_records else None

    def get_open_records(self) -> List[TradeRecord]:
        return list(self._open_records)

    def remove_record(self, trade_id: str):
        """Drop a record from active management (used by the broken-wing roll
        when it closes the old untested vertical)."""
        self._open_records = [r for r in self._open_records
                              if r.get("trade_id") != trade_id]

    def manage_open_position(self,
                              df_1m: Optional[pd.DataFrame] = None,
                              chain=None,
                              regime: Optional[str] = None,
                              df_5m: Optional[pd.DataFrame] = None,
                              vol_state=None, trend=None) -> bool:
        """Manage every open position this tick. Normally one; for a legged
        condor there can be two verticals open at once, each managed
        independently (a tested side exits on its own; the untested side
        stays)."""
        if not self._open_records:
            self._open_records = self._trade_logger.get_open_trades()
            if not self._open_records:
                return False

        still_open: List[TradeRecord] = []
        for record in list(self._open_records):
            if self._manage_one(record, df_1m, chain, regime, df_5m, vol_state, trend):
                still_open.append(record)
        self._open_records = still_open
        return len(self._open_records) > 0

    def _manage_one(self, record: TradeRecord,
                    df_1m: Optional[pd.DataFrame],
                    chain, regime: Optional[str],
                    df_5m: Optional[pd.DataFrame] = None,
                    vol_state=None, trend=None) -> bool:
        """Manage one record. Returns True if it should remain open."""
        trade_id = record["trade_id"]

        current_premium = self._fetch_current_premium(record, chain)
        if current_premium is None:
            logger.warning(
                f"Could not fetch premium for {trade_id[:8]} — skipping tick"
            )
            return True

        self._trade_logger.update_current_premium(trade_id, current_premium)

        exit_eng = get_exit_engine(self.paper_trading)
        decision = exit_eng.evaluate(record, current_premium, df_1m=df_1m,
                                     regime=regime, df_5m=df_5m,
                                     vol_state=vol_state, trend=trend)

        if decision.new_trail_stop is not None:
            # v3.1: trail persists in its OWN column. stop_premium is the
            # immutable -25% floor — overwriting it with the trail made the
            # exit engine's floor checks fire at the trail level and mislabel
            # every trail exit as a hard stop (F5).
            self._trade_logger.update_trail_stop(trade_id, decision.new_trail_stop)
            record["trail_stop"] = decision.new_trail_stop

        if decision.should_exit:
            closed = self._execute_exit(record, decision, current_premium)
            return not closed   # drop if closed; keep (retry) if the order failed

        logger.debug(
            f"Position [{trade_id[:8]}]: "
            f"premium=${current_premium:.2f} "
            f"pnl={decision.current_pnl_pct:.1%} "
            f"(${decision.current_pnl_usd:+.2f})"
        )
        return True

    def _fetch_current_premium(self, record: TradeRecord,
                                chain=None) -> Optional[float]:
        """
        Fetch current mark price for the option(s).
        Uses chain if available — even in paper mode for accurate P&L display.
        Butterfly mark = lower + upper - 2×center.
        Falls back to entry premium in paper mode if chain unavailable.
        """
        is_butterfly = bool(record.get("is_butterfly", False))

        if chain is not None:
            try:
                side           = record.get("option_side", "call")
                contracts_list = chain.calls if side == "call" else chain.puts

                # v3.2 (AUDIT F6): structure-derived, matching exit_engine
                # v4.21's dispatch — pricing and routing must never disagree
                # about what a record IS.
                if _is_credit_vertical(record):
                    short_s = record.get("short_strike", 0)
                    long_s  = record.get("long_strike",  0)
                    short_m = next((c.mark for c in contracts_list if c.strike == short_s and c.mark > 0), None)
                    long_m  = next((c.mark for c in contracts_list if c.strike == long_s  and c.mark > 0), None)
                    if short_m is not None and long_m is not None:
                        return short_m - long_m   # current spread value (credit basis)
                elif is_butterfly:
                    lower_s  = record.get("lower_strike",  0)
                    center_s = record.get("center_strike", 0)
                    upper_s  = record.get("upper_strike",  0)
                    lower_m  = next((c.mark for c in contracts_list if c.strike == lower_s  and c.mark > 0), None)
                    center_m = next((c.mark for c in contracts_list if c.strike == center_s and c.mark > 0), None)
                    upper_m  = next((c.mark for c in contracts_list if c.strike == upper_s  and c.mark > 0), None)
                    if None not in (lower_m, center_m, upper_m):
                        return lower_m + upper_m - 2 * center_m
                else:
                    strike = record.get("strike", 0)
                    match  = next(
                        (c for c in contracts_list if c.strike == strike and c.mark > 0),
                        None
                    )
                    if match:
                        # stash live theta so the exit engine's theta-bleed
                        # detector can see it (single-leg longs only)
                        record["current_theta"] = float(getattr(match, "theta", 0.0) or 0.0)
                        # VEL.1 — the velocity stall check needs DELTA as well:
                        # breakeven velocity is |theta| / (|delta| * 1440), so
                        # theta alone cannot answer "is this position gaining or
                        # bleeding right now". Same stash, same guard.
                        record["current_delta"] = float(getattr(match, "delta", 0.0) or 0.0)
                        return match.mark
            except Exception:
                pass

        if self.paper_trading:
            # LAST-KNOWN MARK, not entry (v2.1). Falling back to entry premium
            # here fabricated a $0 P&L on ANY exit taken while the chain was
            # momentarily unavailable — a real -$818 loss was booked as breakeven
            # at the 15:45 hard close (CRM 2026-07-09, exit recorded == entry).
            # It also blinded the exit logic (a position that "looks like entry"
            # can't trip a stop/target/trail). Use the last live mark that was
            # stored via update_current_premium every good tick; only surrender to
            # entry if we have literally never priced it, and log it so it's never
            # silent.
            last_mark = record.get("current_premium") or 0.0
            if last_mark > 0:
                return last_mark
            logger.warning(
                f"{str(record.get('trade_id',''))[:8]}: no chain and no prior "
                f"mark — falling back to entry premium (P&L may be understated)"
            )
            return record.get("entry_premium", 0.0)

        client = get_client()
        try:
            if is_butterfly:
                lower_sym  = record.get("lower_symbol",  "")
                center_sym = record.get("center_symbol", "")
                upper_sym  = record.get("upper_symbol",  "")

                lower_mark  = self._get_option_mark(client, lower_sym)
                center_mark = self._get_option_mark(client, center_sym)
                upper_mark  = self._get_option_mark(client, upper_sym)

                if None in (lower_mark, center_mark, upper_mark):
                    return None
                return lower_mark + upper_mark - 2 * center_mark
            else:
                symbol = record.get("option_symbol", "")
                return self._get_option_mark(client, symbol)

        except Exception as e:
            logger.error(f"Premium fetch error: {e}")
            return None

    def _get_option_mark(self, client, symbol: str) -> Optional[float]:
        if not symbol:
            return None
        try:
            data  = client.get(f"/market-data/quotes/{symbol}")
            quote = data.get("data", {})
            bid   = float(quote.get("bid", 0) or 0)
            ask   = float(quote.get("ask", 0) or 0)
            if bid > 0 and ask > 0:
                return (bid + ask) / 2
            return float(quote.get("mark", 0) or quote.get("last", 0) or 0) or None
        except Exception:
            return None

    def _execute_exit(self, record: TradeRecord,
                       decision: ExitDecision,
                       current_premium: float) -> bool:
        """Place the exit and book P&L ONLY on a confirmed fill. Returns True if
        the position genuinely closed, False if not (caller retries).

        v3.4: booking is gated on FillResult.confirmed and uses the ACTUAL fill
        price, not the mark we passed in. In paper the simulated fill price
        equals the mark; in live it is the broker's real fill. An unconfirmed
        result books NOTHING and leaves the row open — the anti-orphan invariant.
        current_premium is the last-known mark, passed to the exit engine as the
        paper fill price / live context.
        """
        trade_id = record["trade_id"]

        exit_eng = get_exit_engine(self.paper_trading)
        fill     = exit_eng.place_exit_order(record, decision.exit_reason,
                                             mark_price=current_premium)

        if not fill.confirmed:
            logger.error(f"Exit NOT confirmed for {trade_id[:8]} "
                         f"({fill.detail or 'no fill'}) — position stays OPEN, will retry")
            return False

        fill_price = fill.fill_price
        if fill_price is None:
            # confirmed with no price should be impossible; refuse to book fiction.
            logger.error(f"Exit for {trade_id[:8]} confirmed but no fill_price — "
                         f"refusing to book; will retry")
            return False

        entry_prem    = record["entry_premium"]
        contracts     = record["contracts"]
        # Credit/short positions profit when the premium FALLS, so the P&L sign
        # is inverted vs a debit (long) trade. This covers condor legs AND an
        # adopted short leg (is_short_position) discovered at the broker.
        credit_signed = (bool(record.get("is_condor_leg"))
                         or record.get("strategy") == "IronCondorStrategy"
                         or bool(record.get("is_short_position")))
        if credit_signed:
            pnl_per_share = entry_prem - fill_price
        else:
            pnl_per_share = fill_price - entry_prem
        pnl_usd       = pnl_per_share * contracts * CONTRACT_MULTIPLIER

        self._trade_logger.log_exit(
            trade_id    = trade_id,
            exit_price  = fill_price,
            pnl_usd     = pnl_usd,
            exit_reason = decision.exit_reason,
        )

        risk_mgr = get_risk_manager()
        if pnl_usd >= 0:
            risk_mgr.record_win(pnl_usd)
        else:
            risk_mgr.record_loss(pnl_usd)

        get_alert_manager().send_exit_alert(
            trade_id      = trade_id,
            setup_type    = record.get("setup_type", ""),
            exit_premium  = fill_price,
            entry_premium = entry_prem,
            pnl_usd       = pnl_usd,
            contracts     = contracts,
            reason        = decision.exit_reason,
        )

        exit_eng.clear_trail(trade_id)

        # ── Re-arm ORB engine if this was an ORB trade ─────────────────────────
        # Allows the engine to watch for another breakout attempt this session
        # rather than treating one trade as the end of the ORB opportunity.
        if "ORB" in record.get("strategy", ""):
            try:
                from analysis.orb_engine import get_orb_engine
                get_orb_engine().notify_position_closed()
            except Exception as e:
                logger.warning(f"Could not re-arm ORB engine: {e}")

        logger.info(
            f"✅ Position closed: {trade_id[:8]} "
            f"exit=${current_premium:.2f} "
            f"pnl=${pnl_usd:+.2f} "
            f"reason={decision.exit_reason}"
        )
        return True


# Singleton
_position_manager: Optional[PositionManager] = None


def get_position_manager(paper_trading: bool = PAPER_TRADING) -> PositionManager:
    global _position_manager
    if _position_manager is None:
        _position_manager = PositionManager(paper_trading)
    return _position_manager
