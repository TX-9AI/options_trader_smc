"""
strategy/trend_credit_spread.py — options_trader_v3 — v2.1 — 2026-08-14  (TC.6)

v2.1 — 2026-08-14 — NAMING CODIFIED, AND THE CONDOR RULES DIS-INHERITED.
        **TREND CONTINUATION** = the LONG (DEBIT) contract placed on an ORB
        runaway handoff. Blocked after 11:00 by AFD.1.
        **TREND PARTICIPATION** (this file) = a CREDIT SPREAD at the floor of a
        move, BOUNDED BY THE ORB HIGH for a long / ORB LOW for a short, and
        INVALIDATED BY A BREACH of that level. Nothing else closes it before the
        session hard close.
        THE OPERATOR'S CORRECTION THAT MATTERS: *"those levels are fixtures."*
        The ORB **ENGINE** must not gate an afternoon trade — no runaway flag,
        no slot arbitration, no `invalidation_reason`, and nothing a restart can
        erase. The ORB **LEVEL** is a price on a chart and is recomputed from
        the TAPE (`main._opening_range`). v2.0 over-corrected by removing both.
        DIS-INHERITED FROM THE CONDOR:
          · **the 0.80 x EM minimum distance.** The condor needs it because it
            sells around a PIN with no structural level; TC.6 HAS one. Since a
            strike must clear BOTH constraints, an EM floor beyond the ORB high
            would push the strike past the specified level — a FITTED
            percentage silently overriding a STRUCTURAL one.
          · **the nickel close.** A profit exit caps a position whose measured
            EV was HELD TO EXPIRY, UNMANAGED.
        ADDED: **price must be OUTSIDE the range at entry.** The exit calls a
        close back through the bound INVALIDATION, so entering while price is
        already inside means the trade is BORN IN THE STATE ITS OWN EXIT CALLS
        DEAD — the CNT.1 failure shape, which made every breakout continuation
        a one-tick artefact for a week.
        REMOVED: **the 30-minute cooldown.** It was an emergency brake during
        the rapid-fire incident and the wrong instrument for the right worry —
        the loop came from a $0.06 credit sitting one cent from a nickel close
        and one cent from a mis-set stop, all now fixed at the source. Operator:
        *"It's gated enough. The cooldown is excessive."*
        RETAINED from the condor, deliberately: quote width (liquidity is
        universal), POP >= 0.70 (the operator's own 70-80%% band, stated about
        exactly this trade), the not-exceeded session extreme, and deferral to
        an active condor plan (real deconfliction, not conflation).

AFTERNOON TREND PARTICIPATION BY SELLING PREMIUM BENEATH THE MOVE.

⚠️ v2.0 — **THE ORB LINK IS SEVERED.** Operator, 2026-08-14, after TC.6 went
silent for an entire afternoon: *"Trend participation should have nothing to do
with orb range after the 11AM cutoff... If they are linked in any way after
11AM, then it's wrong."*

WHY THE ORB ANCHOR WAS WRONG, and it was wrong from the start:
  · **IT WAS THE WRONG LEVEL.** v1.x anchored on the broken ORB boundary, which
    was imported from a measurement of MORNING runaway trades where price was
    still near the opening range. By 13:00 that range is four hours stale and
    price may be nowhere near it.
  · **IT MADE AN AFTERNOON STRATEGY DEPEND ON MORNING STATE.** `orb_state.json`
    is WRITE-ONLY — there is no load path anywhere in the repo — so the ORB
    engine lives entirely in memory. The 2026-08-14 10:37 restart wiped
    `invalidation_reason` on all 15 boxes, and because ORB cannot re-arm past
    its 11:00 cutoff, **the runaway flag was gone permanently for the session.**
    TC.6's hard gate became unsatisfiable no matter what the tape did. A whole
    afternoon of zero fires, from a silent gate.
  · **AND THE GATE WAS SILENT**, which is how the afternoon was spent guessing.

THE ANCHOR IS NOW THE SESSION EXTREME — the operator's own original framing,
*"a vertical spread at the floor of the Move."* Session LOW for a bull trend,
session HIGH for a bear. It updates continuously, exists on every box every day,
survives restarts, and needs nothing from the morning.

MEASURED (`spread_counterfactual --anchor floor`, 18 sessions, PDL + session
low): TRENDING_BEAR +0.39 / +0.48 / +0.46 and TRENDING_BULL +0.60 / +0.66 /
+0.78 at 0.00%% / 0.25%% / 0.50%% beyond the floor.
⚠️ **BOTH ARMS POSITIVE, so this is a GENERAL credit edge rather than a
regime-specific one** — weaker evidence than the ORB result, whose control
FAILED. Stated plainly rather than dressed up.

⚠️ AND THE RUNAWAY GATE WAS A CATEGORY ERROR. Operator: *"The reason it
requires a runaway before 11am is because ORB OWNS THAT SLOT. So a runaway is
the only exception a different trade can execute."* The runaway is a
SLOT-ARBITRATION rule, never an anchoring rule — ORB owns 09:35-11:00, and a
runaway is the one condition where ORB is definitively out (INVALIDATED, never
re-arms) so the slot frees. The correct occupants of that freed slot ALREADY
EXIST and are unchanged by this file: `trend_continuation_handoff` (via
`_is_runaway`) and `SweepReversal` (gates on `invalidation_reason in ("runaway",
"timeout")`).
**AFTER 11:00 ORB HAS STOPPED ENTIRELY — there is no slot to arbitrate**, so
requiring the arbitration condition was asking permission from a strategy that
is not running. TC.6 owns afternoon trend participation outright.

DIRECTION COMES FROM THE TREND VOTE (`overall_direction` + ADX), the same source
CNT.1's breakout branch already uses — no new machinery, and no dependence on
any morning artefact.

EXIT: BREACH OR NICKEL. Breach is a CLOSED BAR through the floor recorded AT
ENTRY. Fixed, not ratcheting: a floor that follows price would tighten the
invalidation on a winning trade, which is the opposite of letting it run — and
the short strike it was sold against does not move either.
⚠️ **THE MEASURED EV WAS HELD TO EXPIRY, UNMANAGED.** No premium stop, no
ratchet. `is_trend_credit` keeps `exit_engine` out of the condor ladder.

STRIKE SELECTION HAS ONE OWNER, AND IT IS NEITHER STRATEGY.
`strategy/credit_vertical.py` implements rail -> min-distance -> not-exceeded ->
quote-width -> POP, and both this file and the condor import it. TC.6 used to
instantiate `IronCondorStrategy` to borrow five of its methods and six of its
`CONDOR_*` knobs — so a condor tuning change silently retuned this trade, and
its identity had to survive as a flag on a record built by the condor's own
execution path. That is the coupling that produced 108 bad trades on
2026-08-14.
"""

import logging
from datetime import datetime
from typing import Optional

import pytz

from config import (
    TCS_MIN_POP, TCS_MAX_QUOTE_WIDTH, TCS_POP_BAR_MIN, TCS_NICKEL_REF,
    TCS_WING_WIDTH_SPX, TCS_WING_WIDTH_QQQ,
    TREND_CREDIT_ACTIVE, TCS_START_ET, TCS_MIN_CREDIT_NICKEL_MULT,
    TCS_LOSS_GIVEN_BREACH, CONT_BREAKOUT_MIN_ADX,
    GLOBAL_NO_ENTRY_ET, INSTRUMENT, HARD_CLOSE_ET,
)
# ⚠️ NOT `from strategy.iron_condor_strategy import IronCondorStrategy`.
# TC.6 previously instantiated the condor to borrow five of its methods. The
# shared math now lives in a module OWNED BY NEITHER, so neither strategy can
# retune the other by accident — and TC.6 no longer needs the condor to exist.
from strategy import credit_vertical as cv

logger = logging.getLogger(__name__)
ET = pytz.timezone("US/Eastern")


class TrendCreditSpread:
    """Sell a defined-risk vertical beyond the session extreme — the floor of
    the current move. Afternoon only; owns the slot outright once ORB stops."""

    name = "TrendCreditSpread"

    def __init__(self):
        pass

    @staticmethod
    def _wing_width() -> float:
        return (TCS_WING_WIDTH_SPX if INSTRUMENT in ("SPX", "SPXW")
                else TCS_WING_WIDTH_QQQ)

    def generate_signal(self, regime, vol_state, chain, macro,
                        current_price: float, trend=None,
                        orb_high: Optional[float] = None,
                        orb_low: Optional[float] = None,
                        session_high: Optional[float] = None,
                        session_low: Optional[float] = None,
                        condor_active: bool = False,
                        now_et: Optional[datetime] = None):
        """Returns a condor-leg-shaped OptionsSignal, or None.

        ⚠️ NO `orb` PARAMETER. v1.x took one and gated on
        `invalidation_reason == "runaway"`; both are gone. After 11:00 ORB has
        stopped and owns nothing, so there is no slot to arbitrate and no
        morning level worth anchoring to.

        GATES, in order, EACH ONE LOGGED — a gate that can silence a strategy
        for a whole session without leaving a line is how 2026-08-14's afternoon
        was spent guessing:
          1. active flag
          2. inside the 11:00 -> GLOBAL_NO_ENTRY_ET window
          3. no active condor plan (it holds the slot; a third credit spread on
             one underlying is unmanaged risk)
          5. a directional trend vote clearing CONT_BREAKOUT_MIN_ADX
          6. a session extreme on the floor side
          7. a strike clearing floor / min-distance / not-exceeded / quote-width
             / POP
          8. a protective wing
          9. positive EV, and a credit with room to exist
        """
        try:
            if not TREND_CREDIT_ACTIVE:
                return None
            now = now_et or datetime.now(ET)
            if (now.hour, now.minute) >= GLOBAL_NO_ENTRY_ET:
                return None
            if (now.hour, now.minute) < TCS_START_ET:
                return None
            # ── NO COOLDOWN. REMOVED 2026-08-14 ──────────────────────────────
            # It was added as an emergency brake when TC.6 rapid-fired the fleet,
            # and at that moment it was the wrong instrument for the right
            # worry: the loop existed because a $0.06 credit sat one cent from a
            # $0.05 nickel close and one cent from a mis-set stop. Those are
            # fixed at the source — the exit no longer falls through to a
            # premium stop, the nickel close is gone entirely, and the joint EV
            # test refuses a credit that thin.
            # The trade is now gated on: the 11:00-14:00 window, a directional
            # trend vote clearing ADX, an ORB bound that exists, PRICE OUTSIDE
            # the range, no active condor, a strike clearing not-exceeded /
            # quote-width / POP, a protective wing, positive EV, and a credit
            # with room. Operator: "It's gated enough. The cooldown is
            # excessive." A timer stacked on top of nine substantive gates
            # suppresses valid re-entries without preventing a single bad one.
            if condor_active:
                logger.info("[tcs] deferring — a condor plan holds this symbol")
                return None

            # ── DIRECTION FROM THE LIVE TREND VOTE ───────────────────────────
            # The same source CNT.1's breakout branch uses. Nothing from the
            # morning: the runaway that freed ORB's slot may have been a
            # DIFFERENT MOVE, or the opposite one, and selling against a level
            # set by a move that already ended is how v1.x could pass its gate
            # and still be incoherent.
            _dir = str(getattr(trend, "overall_direction", "NEUTRAL") or "NEUTRAL").upper()
            _adx = float(getattr(trend, "primary_adx", 0.0) or 0.0)
            if _dir not in ("BULLISH", "BEARISH"):
                logger.info("[tcs] no directional trend vote (%s) — SKIP", _dir)
                return None
            if _adx < CONT_BREAKOUT_MIN_ADX:
                logger.info("[tcs] ADX %.1f below %.1f — SKIP",
                            _adx, CONT_BREAKOUT_MIN_ADX)
                return None

            # ── THE FLOOR OF THE MOVE = THE SESSION EXTREME ──────────────────
            # Bull trend -> sell PUTS beneath the session LOW.
            # Bear trend -> sell CALLS above the session HIGH.
            # It updates as the move does, exists on every box every day, and
            # survives a restart — unlike the ORB range, which is a 09:30-09:35
            # structure held only in memory.
            # ── THE BOUND (operator's spec, 2026-08-14) ──────────────────────
            # "Trend participation is a credit spread at the floor of a move,
            #  bounded by the ORB HIGH mark for a long & invalidated by a
            #  breach. Or, at the ORB LOW mark for a short & also invalidated by
            #  a breach of that level."
            # A runaway LONG broke UP through the ORB high, so that level is the
            # FLOOR of the move and the credit trade is a PUT spread beneath it.
            # Mirrored for a short at the ORB low.
            # ⚠️ THE LEVEL, NOT THE ENGINE. `orb_high`/`orb_low` arrive
            # RECOMPUTED FROM THE TAPE (main._opening_range) — no runaway flag,
            # no `invalidation_reason`, no slot arbitration, and nothing that a
            # restart can erase. The ORB ENGINE owns 09:35-11:00; after 11:00 it
            # owns nothing, but the opening range is still a price on a chart.
            # The SESSION extreme is retained as the not-exceeded filter: a
            # strike price has already traded through today is one the market
            # has proven it can reach.
            # ⚠️ NO NOT-EXCEEDED FILTER. DIS-INHERITED 2026-08-14, and this one
            # was not merely redundant — IT MADE THE BOUND DECORATIVE.
            # The arithmetic is unavoidable: `session_low` <= `orb_low` <
            # `orb_high` (the opening range is PART of the session), so
            # requiring a put strike to clear BOTH the bound AND the session low
            # collapses to the session low **every single time**. The strike was
            # always placed below the ORB LOW and never at the operator's level.
            # Mirrored exactly for calls. So the ENTRY placed the strike
            # somewhere the EXIT never referenced — the CNT.1 failure shape one
            # layer up.
            # AND IT COST THE PREMIUM. Operator: *"wouldn't the orb bounds be
            # 'richer' than the furthest away it's been?"* Yes — the bound sits
            # CLOSER to spot, so it is the richer level; the extreme is further,
            # thinner, and always won.
            # POP IS THE BETTER INSTRUMENT ANYWAY. "Price traded through here
            # today" is backward-looking and ignores time remaining and current
            # volatility. POP asks the same question — can price REACH this
            # strike — in sigma*sqrt(T) terms FROM NOW. A level touched at 09:45
            # may be unreachable at 13:00 with 2.75h left, and POP knows that
            # while the extreme does not. Safety is carried by POP >= 0.70 and
            # the joint EV test, not by a cruder proxy that binds harder.
            # `session_high`/`session_low` are still accepted for telemetry and
            # for a future study; they no longer gate.
            if _dir == "BULLISH":
                side, bound, extreme = "put", orb_high, None
                direction = "long"
            else:
                side, bound, extreme = "call", orb_low, None
                direction = "short"
            if not bound or bound <= 0:
                logger.warning("[tcs] no opening-range %s — the bound is the "
                               "anchor, SKIP rather than trade without one",
                               "high" if side == "put" else "low")
                return None

            # ── NO EM FLOOR. DIS-INHERITED FROM THE CONDOR ───────────────────
            # The condor needs an EM-derived minimum distance because it sells
            # around a PIN with no structural level to lean on. **TC.6 HAS a
            # structural level — the ORB bound.**
            # `_select_beyond_rail` requires a strike to clear BOTH the rail and
            # the min-distance, so WHICHEVER IS FURTHER OUT WINS. If 0.80 x EM
            # sat beyond the ORB high it would push the strike past the level the
            # operator specified and the bound would stop being the bound — a
            # FITTED PERCENTAGE silently overriding a STRUCTURAL LEVEL, which is
            # backwards. Neutralised with a sentinel that can never bind rather
            # than deleted from the shared selector, because that selector is
            # also the condor's and the condor still needs it.
            min_dist = float("inf") if side == "put" else float("-inf")

            # ── PRICE MUST BE OUTSIDE THE RANGE AT ENTRY ─────────────────────
            # The exit calls a close back through the bound INVALIDATION. If
            # price is already inside the range when we enter, the trade is BORN
            # IN THE STATE ITS OWN EXIT CALLS DEAD — the same entry/exit
            # disagreement that made every breakout continuation a one-tick
            # artefact for a week (CNT.1, fixed 2026-08-14).
            _outside = (current_price > bound if side == "put"
                        else current_price < bound)
            if not _outside:
                logger.info("[tcs] price %.2f is back INSIDE the range (bound "
                            "%.2f) — the move that set the level has failed, "
                            "SKIP", current_price, bound)
                return None

            sigma = float(getattr(vol_state, "atr_current", 0.0) or 0.0)
            bars = cv.bars_left(now, TCS_POP_BAR_MIN, HARD_CLOSE_ET)

            contracts = chain.puts if side == "put" else chain.calls
            short = cv.select_beyond_rail(
                contracts, side, bound, min_dist, extreme,
                spot=current_price, sigma=sigma, bars=bars,
                min_pop=TCS_MIN_POP, max_width_pct=TCS_MAX_QUOTE_WIDTH)
            if short is None:
                logger.info(
                    "[tcs] no %s strike clears ORB bound %.2f / min-dist %.2f "
                    "/ POP>=%.2f at %.1f bars — SKIP",
                    side, bound, min_dist, TCS_MIN_POP, bars)
                return None

            width = self._wing_width()
            long_strike = (short.strike - width if side == "put"
                           else short.strike + width)
            long_c = cv.find_contract_at_strike(contracts, long_strike)
            if long_c is None or long_c.strike == short.strike:
                logger.info("[tcs] no protective wing at %.2f — SKIP "
                            "(undefined risk is never sold)", long_strike)
                return None

            credit = max(0.0, (short.bid or 0.0) - (long_c.ask or 0.0))
            pop = cv.pop(abs(short.strike - current_price), sigma, bars)
            if pop <= 0.0:
                logger.info("[tcs] POP unresolvable (sigma %.4f, bars %.1f) — "
                            "SKIP. A missing input is not a safe trade.",
                            sigma, bars)
                return None
            req = TCS_LOSS_GIVEN_BREACH * (1.0 - pop) / pop
            if credit / width <= req:
                logger.info(
                    "[tcs] NEGATIVE EV — credit %.2f = %.1f%% of width %.0f, "
                    "needs > %.1f%% at POP %.2f — SKIP",
                    credit, 100.0 * credit / width, width, 100.0 * req, pop)
                return None
            floor_n = TCS_MIN_CREDIT_NICKEL_MULT * TCS_NICKEL_REF
            if credit < floor_n:
                logger.info("[tcs] credit %.2f below %.1fx nickel (%.2f) — "
                            "no room to profit, SKIP",
                            credit, TCS_MIN_CREDIT_NICKEL_MULT, floor_n)
                return None

            return self._build_signal(side, short, long_c, direction, bound,
                                      current_price, regime, bars)
        except Exception as exc:                               # noqa: BLE001
            logger.warning("[tcs] generate_signal failed: %s", exc)
            return None

    def _build_signal(self, side, short, long_c, direction, boundary,
                      current_price, regime, bars):
        """Condor-leg shape, so `_execute_condor_leg` runs it unchanged.

        `is_trend_credit` is the flag `exit_engine` keys on. WITHOUT IT this leg
        inherits the condor's 25%% premium stop and ratchet — and the measured
        EV was HELD TO EXPIRY, UNMANAGED. A stop bolted on afterwards is a
        different trade with a different expectancy.
        """
        from strategy.base_strategy import OptionsSignal
        sig = OptionsSignal(
            strategy_name=self.name,
            setup_type=f"trend_credit_{direction}",
            direction="neutral",              # a credit spread has no side to be on
            option_side=side,
            underlying_entry=current_price,
            # THE INVALIDATION LEVEL, and the exit. A close beyond the broken
            # boundary is thesis death — the same event orb_structure_stop names.
            underlying_stop=boundary,
            regime=str(getattr(regime, "primary_regime", "")),
        )
        sig.is_credit_vertical = True         # credit-spread math, not debit
        sig.is_trend_credit = True            # exit_engine: breach-or-nickel ONLY
        sig.net_credit = max(0.0, (short.bid or 0.0) - (long_c.ask or 0.0))
        if side == "call":
            sig.short_call_contract, sig.long_call_contract = short, long_c
        else:
            sig.short_put_contract, sig.long_put_contract = short, long_c
        sig.contract = short
        sig.conviction = 1.0
        logger.info(
            "[tcs] %s spread: short %.2f / long %.2f, credit %.2f, boundary "
            "%.2f, %.1f bars left — exit is BREACH or NICKEL, no premium stop",
            side, short.strike, long_c.strike, sig.net_credit, boundary, bars)
        return sig
