"""
strategy/sweep_reversal_strategy.py — Post-liquidity-sweep reversal for options.
v3.5 — 2026-08-11 — SWP.4: THE RECOVERY WINDOW PENALISED GOOD REJECTIONS.
        `recovery_pct` was measured from `sweep.sweep_price` — the WICK EXTREME
        of the raid — so the DEEPER the rejection, the FARTHER the entry
        appeared, and the gate refused exactly the setups it should want.
        Reproduced on a fabricated textbook PDL raid: a 2.36% rejection produced
        recovery_pct 2.4% against the 2.0% cap and was refused with "Sweep long:
        too far from sweep", on the single best setup the scorer can produce.
        Now anchored to `sweep.pool_price` — the level that was RECLAIMED, which
        is the thesis being traded. The same setup then reads 0.11%.
        Wick depth is a measure of rejection QUALITY and `rejq_val` already
        scores it; it has no business inflating a distance-from-entry measure.
        Both sides changed. OT_SWEEP_RECOVERY_FROM_POOL=0 restores the old
        anchor exactly.
        ⚠️ VERIFIED END TO END on three fabricated scenarios: an excellent PDL
        raid now passes EVERY logic gate (L1 1.000), a weak one is still
        refused as too old (L1 0.000), and the same excellent raid into an
        ACCELERATING opposing trend scores 0.150 — a tenth of A, still above
        the long floor. The discrimination survives the unshackling.
        ⚠️ NOT CHANGED, and worth knowing: the 1m BOS lookback references recent
        swing highs, so a raid that is really a COLLAPSE (5% in two minutes)
        cannot satisfy it by construction. A realistic approach-and-raid does.
        That was a fixture defect on my side, not a code defect.

v3.6 — 2026-08-11 — SWP.4 + SWP.5.

        SWP.4 THE RECOVERY WINDOW PENALISED GOOD REJECTIONS. `recovery_pct` was
        measured from `sweep.sweep_price` — the WICK EXTREME — so the DEEPER the
        rejection, the FARTHER the entry appeared. On a fabricated textbook PDL
        raid a 2.36% rejection produced 2.4% against the 2.0% cap and was
        refused, on the best setup the scorer can produce. Now anchored to
        `sweep.pool_price` — the level RECLAIMED, which is the thesis traded —
        where the same setup reads 0.11%. Wick depth is rejection QUALITY and
        `rejq_val` already scores it. Both sides changed.
        OT_SWEEP_RECOVERY_FROM_POOL=0 restores the old anchor.

        SWP.5 LIVENESS REPLACES THE CLOCK. `SWEEP_MAX_AGE_BARS = 8` was standing
        in for an invalidation test the code did not have. MEASURED over 90 real
        symbol-days: of the stale sweeps it refused, **32.9% still had a LIVE
        thesis** — price had never accepted back through the raided level and
        was still on the correct side. The gate now asks LIQ.3's running
        `sweep_invalidated` instead.
        RESULT on the same 90 symbol-days: refusals went from **98.4% "too old"**
        to **77.2% INVALIDATED** (the level actually failed) + 13.9% backstop,
        and setups reaching STRIKE SELECTION went **5 -> 40**.
        ⚠️ AGE SURVIVES AS A BACKSTOP, NOT AS THE TEST: SWEEP_STALE_HARD_BARS
        (48 = 4h) still refuses a live-but-ancient raid, because an
        all-session-old level is a different trade. That 48 is a PRIOR — nothing
        in the data picked it. 414 setups hit it.
        ⚠️ ALL THESE COUNTS ARE NVDA/SPX/SMCI WITH STUBBED REGIME AND VOL STATE.
        The gate ORDERING is real; the absolute numbers are not the fleet.
        OT_SWEEP_LIVENESS_GATE=0 restores the pure-clock behaviour exactly.

v3.4 — 2026-08-07 — SWP.2: SHORT SWEEPS GET THEIR OWN FLOOR
        (`SWEEP_SETUP_FLOOR_SHORT`, default 0.20; longs stay at 0.05). Three
        measures agree that long and short are not the same trade — win rate
        81% vs 33%, never-favourable 4% vs 33%, and forward drift building to
        +0.314 vs falling to −0.290. n=6 on the short side is thin, so this is a
        PRIOR carried by the MECHANISM (the 07-27 PLTR short-into-strength
        incident), not a fit. ⚠️ With SWEEP capped near 0.265 this NEAR-DISABLES
        shorts; that is deliberate and is stated rather than disguised.

v3.3 — 2026-08-07 — SWP.1: THE REGIME GATE IS GONE. Operator's ruling — sweep is
        an EVENT, not a market state. `generate_signal` refused unless the
        committed label was SWEEP_REVERSAL; that label wins 0.4% of live ticks,
        is exactly zero on 96%, and F7's commit threshold narrowed it further,
        so the trade was effectively off. Dispatch (main v5.6) now qualifies the
        setup on the L1 `_sweep` SCORE, whose three hard vetoes ARE the spec: a
        NAMED level, REJECTED back through, not accepted beyond.
        NEW `setup_score` kwarg carries that score and becomes the strategy's
        CONVICTION — it drives `_sweep_target_delta`, the confluence note, and
        `signal.conviction`. Previously all three read `regime.conviction`,
        which after ungating would be the AMBIENT regime's conviction (e.g.
        TRENDING_BULL at 0.80) — a nonsense input to sweep strike selection and
        a silent one. Defaults to `regime.conviction` only so an un-migrated
        caller degrades visibly rather than crashing.
        WHAT DID NOT CHANGE: the ORB-ownership gate below, the confirmed/fresh
        sweep preconditions, and the PLTR trend-opposition guard — the last of
        which lives as a soft-necessary INSIDE the score, never in the removed
        gate, so it travels with the new qualification.

v3.2 — 2026-07-21 — ORB-OWNERSHIP GATE (hardcoded). A sweep may fire ONLY after
        the ORB has released its claim on price. While the ORB owns price —
        inside the range awaiting a break (WAITING_FOR_BREAK), broken out and
        awaiting/at retest (ARMED_LONG/SHORT), a position open (OPEN_LONG/SHORT),
        or the range failed back inside (INVALIDATED/close_inside) — the sweep
        is blocked. Released = retest went stale (INVALIDATED/timeout), price ran
        past the 50%% level (INVALIDATED/runaway), EXPIRED, or past the 11:00 ET
        cutoff. Replaces the old broke_high/broke_low check, which let a sweep
        fire the instant a break REGISTERED — i.e. while the ORB was still ARMED
        and awaiting its retest — the exact double-ownership this forbids.
        (CVX 2026-07-21 09:55: sweep short fired with price inside the range.)
        Method renamed _sweep_broke_orb -> _orb_released_price.
v3.1 — 2026-07-13 — defect H rename only: NO_ENTRY_AFTER_ET -> ORB_NO_ENTRY_AFTER_ET.
        Same constant, same (11, 0) value, same behaviour. This file is precisely
        why the rename earns its keep: the 11:00 ORB cutoff is the ARM condition
        here (past it, the ORB window is over and sweep works any level), which
        the old name did nothing to convey.
v3.0 — 2026-07-06 — entry-gate tuning (separate pass from detection): recovery
        window is ATR-aware (LARGER of SWEEP_MAX_RECOVERY_PCT or
        SWEEP_RECOVERY_ATR_MULT × ATR%) so fast/volatile reversals aren't
        rejected as "too far"; BOS lookback is configurable (SWEEP_BOS_LOOKBACK)
        and also accepts a BOS that closed on the just-closed candle.
v1.3 — 2026-07-06 — ORB-BREAK GATE (registered break, not wick clear): before
        the 11:00 ET cutoff a sweep may ONLY fire after a GENUINE breakout — a
        1-min candle that CLOSED beyond the range (ORB engine broke_high /
        broke_low). A wick that pokes the boundary and closes back inside is
        still 'in range, awaiting break' → no trade (this was the AVGO hole).
        High sweep needs a registered break HIGH; low sweep needs break LOW.
        After 11:00 the ORB window is closed and the gate lifts.
v1.2 — 2026-07-06 — ORB-boundary gate (wick clear) — superseded by v1.3.
v1.1 — 2026-07-03 — OTM target delta scales inversely with reversal strength
        (regime conviction): strong -> far-OTM low delta, weak -> near-ATM.
v3.0 — 2026-07-10 — repo-wide v3.0 bump: Yahoo-Finance purge & data stream
        mapping optimization (all market data now flows from the single
        shared TastyTrade candle feed — see data/candle_feed.py). No logic
        change in this file.

Ported from crypto_trader SweepReversalStrategy and adapted for 0DTE options:
- Same sweep detection (PDH/PDL, equal H/L, session H/L)
- Same 1-min BOS confirmation in reversal direction
- Strike selection: closest to 0.20 delta OTM in reversal direction
- Naked long call (low sweep → long) or naked long put (high sweep → short)
- Stop: 25% of premium paid
- TP: 100% of premium at first target; trailing stop at 50%


SWP.8 (2026-08-15) — REFUSAL PATHS PROMOTED TO INFO.
    All 10 `logger.debug` calls in this file are REASONS A TRADE DID NOT HAPPEN,
    and the fleet runs at `LOG_LEVEL="INFO"` — so **none of them existed in any
    log anyone could read.**

    ⚠️ THIS COST A WHOLE MORNING. The 2026-08-15 sweep investigation had to
    proceed by elimination-by-reading the source, because the strategy never
    said why it declined. Meanwhile the BUTTERFLY logs its gates at INFO, and
    that same morning its blocker was found in a single grep: `GEX not PINNING`
    dominating 20-50x, then the discount gate rejecting 39/26. Same class of
    question, two very different costs.

    Log-only. No gate, threshold or behaviour changes. Freeze-safe.
    ⚠️ Volume: these fire per-tick on a refused sweep, so a symbol that never
    qualifies will print steadily. That is the POINT — a silent refusal is
    indistinguishable from a strategy that was never evaluated, which is exactly
    the ambiguity that made VEL.1, the AFD.1 slot bug and this one all cost
    hours to diagnose.
"""
# v-obs2 (2026-07-24) — stamps swept_level_name + level_strength (0..1, named+touch_count) onto the sweep signal so the trade record captures level conviction.


import logging
from typing import Optional

from analysis.level_grade import grade_level as _grade_level
from strategy.base_strategy import BaseOptionsStrategy, OptionsSignal
from config import SWEEP_SETUP_FLOOR, SWEEP_SETUP_FLOOR_SHORT   # SWP.2
from analysis.regime_classifier import RegimeState   # v3.3: `Regime` no longer
# imported — the enum was used ONLY by the removed label gate. Leaving a dead
# import would let a future edit silently re-introduce the gate it belongs to.
from analysis.volatility_engine import VolatilityState
from analysis.structure_analyzer import StructureMap
from analysis.liquidity_mapper import LiquidityMap, LiquiditySweep
from analysis.orb_engine import get_orb_engine, ORBState
from data.options_chain import OptionsChain
from data.options_chain import get_chain_fetcher
from data.macro_data import MacroSnapshot
from utils.time_utils import now_et
from config import (
    SWEEP_DELTA_STRONG, SWEEP_DELTA_WEAK, SWEEP_MAX_AGE_BARS,
    ORB_NO_ENTRY_AFTER_ET,
    SWEEP_MAX_RECOVERY_PCT, SWEEP_RECOVERY_ATR_MULT, SWEEP_BOS_LOOKBACK,
    SWEEP_RECOVERY_FROM_POOL,                      # SWP.4
    SWEEP_LIVENESS_GATE, SWEEP_STALE_HARD_BARS,    # SWP.5
    MAX_LOSS_PCT,
)


def _sweep_target_delta(conviction: float) -> float:
    """Scale the OTM target delta INVERSELY with reversal strength: a strong
    snap-back (conviction -> 1) uses a far-OTM low delta for max leverage; a
    weak one (conviction -> 0) uses a near-ATM higher delta to participate."""
    strength = max(0.0, min(1.0, conviction))
    return SWEEP_DELTA_WEAK - strength * (SWEEP_DELTA_WEAK - SWEEP_DELTA_STRONG)
import pandas as pd

logger = logging.getLogger(__name__)


class SweepReversalStrategy(BaseOptionsStrategy):
    """
    After a confirmed liquidity sweep with BOS confirmation,
    buy a naked OTM option (~0.20 delta) in the reversal direction.

    Long reversal (lows swept):   buy OTM call
    Short reversal (highs swept): buy OTM put
    """

    @property
    def name(self) -> str:
        return "SweepReversal"

    def generate_signal(self,
                         regime: RegimeState,
                         vol_state: VolatilityState,
                         structure: StructureMap,
                         liq_map: LiquidityMap,
                         chain: OptionsChain,
                         macro: MacroSnapshot,
                         df_1m: Optional[pd.DataFrame],
                         current_price: float,
                         setup_score: Optional[float] = None) -> Optional[OptionsSignal]:
        """
        Generate a sweep reversal options signal.

        Args:
            regime:         Ambient regime state (NO LONGER required to be
                            SWEEP_REVERSAL — v3.3/SWP.1)
            setup_score:    L1 `_sweep` setup score for this tick. Drives strike
                            selection. None => fall back to regime.conviction,
                            which is only correct for a caller that still gates
                            on the label.
            vol_state:      Volatility state
            structure:      Market structure (support/resistance)
            liq_map:        Liquidity map with recent sweep
            chain:          0DTE options chain
            macro:          Macro snapshot
            df_1m:          1-min candles for BOS confirmation
            current_price:  Current underlying price

        Returns:
            OptionsSignal or None
        """
        # v3.3 (SWP.1) — the label gate is GONE. Sweep is an event, not a
        # regime; dispatch now qualifies the setup on the L1 _sweep score, whose
        # hard vetoes are the named level + the rejection. Re-checking the label
        # here would silently re-impose the very gate that was removed upstream.
        # The preconditions below (a confirmed, fresh sweep) remain the
        # strategy's own authority and are unchanged.
        conv = regime.conviction if setup_score is None else float(setup_score)

        sweep = liq_map.recent_sweep
        if not sweep or not sweep.confirmed:
            return None

        # ── SWP.5 (2026-08-11) — LIVENESS BEFORE AGE ────────────────────────
        # Operator: "if the market makers are driving the price to either
        # extreme what difference does it make if it takes an hour or if it
        # takes all day?" None. What ends a sweep thesis is the level FAILING,
        # not the clock. MEASURED over 90 real symbol-days: of the stale sweeps
        # this gate refused, **32.9% still had a live thesis** (854 of 2,593) —
        # price had never accepted back through the raided level and was still
        # on the correct side. ~9.5 valid setups discarded per symbol-day.
        # The age gate was standing in for an invalidation test that the code
        # did not have: `veto_accept` asks exactly the right question but is a
        # BIRTH-TIME snapshot (counted over the 2-3 bars after the raid and
        # never updated). LIQ.3 now recomputes it every tick.
        # ⚠️ AGE SURVIVES AS A BACKSTOP, NOT AS THE TEST. A live level still
        # ages out at SWEEP_STALE_HARD_BARS — an all-session-old raid is a
        # different trade from a fresh one and this is a collection phase, not
        # a licence to hold forever. OT_SWEEP_LIVENESS_GATE=0 restores the
        # pure-clock behaviour exactly.
        _invalid = bool(getattr(liq_map, "sweep_invalidated", False))
        if SWEEP_LIVENESS_GATE:
            if _invalid:
                logger.info(f"Sweep INVALIDATED: price accepted back through "
                            f"{sweep.swept_named_level or 'the level'} "
                            f"({liq_map.sweep_age_bars} bars) — thesis dead")
                return None
            if liq_map.sweep_age_bars > SWEEP_STALE_HARD_BARS:
                logger.info(f"Sweep past the hard backstop: "
                            f"{liq_map.sweep_age_bars} > {SWEEP_STALE_HARD_BARS} "
                            f"bars (level still holding, but too old to trade)")
                return None
        elif liq_map.sweep_age_bars > SWEEP_MAX_AGE_BARS:
            logger.info(f"Sweep too old: {liq_map.sweep_age_bars} bars")
            return None

        # ── ORB-ownership gate ───────────────────────────────────────────────
        # While the ORB has a live claim on price (inside range, or broken out
        # and awaiting/at retest), the ORB owns it — a sweep must NOT fire. A
        # sweep is released only after the ORB gives price up: retest went stale
        # (timeout), price ran past the 50% level (runaway), or past the 11:00 ET
        # cutoff. See _orb_released_price.
        if not self._orb_released_price(sweep):
            logger.info(
                f"Sweep blocked: {sweep.kind} @ {sweep.sweep_price:.2f} — ORB still "
                f"owns price (state={get_orb_engine().data.state}); deferring to ORB"
            )
            return None

        # Determine reversal direction from sweep type
        if sweep.kind == "low_sweep":
            return self._long_reversal(
                sweep, regime, vol_state, structure, liq_map,
                chain, macro, df_1m, current_price, conv
            )
        elif sweep.kind == "high_sweep":
            # SWP.2 — SHORT SWEEPS CLEAR A HIGHER BAR THAN LONGS. Over 12
            # sessions: long 27 trades / 81% WR / +$2,844 / 4% never-favourable
            # / forward drift building to +0.314 at 30 bars with 67% positive;
            # short 6 / 33% / −$1,403.50 / 33% never-favourable / drift −0.290
            # with 33% positive. n=6 is thin, so this is a PRIOR — what earns it
            # is that the MECHANISM agrees: the 07-27 PLTR incident was exactly
            # a short reversal into a +7.2% up-trending tape.
            # ⚠️ SWEEP's score is capped near 0.265, so a 0.20 floor NEAR-
            # DISABLES shorts rather than trimming them. Deliberate at
            # −$233/trade, and named as such so nobody reads it as a dial.
            if conv < SWEEP_SETUP_FLOOR_SHORT:
                logger.info(
                    "Sweep SHORT blocked: setup %.3f < short floor %.2f "
                    "(longs use %.2f)", conv, SWEEP_SETUP_FLOOR_SHORT,
                    SWEEP_SETUP_FLOOR)
                return None
            return self._short_reversal(
                sweep, regime, vol_state, structure, liq_map,
                chain, macro, df_1m, current_price, conv
            )
        return None

    def _long_reversal(self, sweep: LiquiditySweep,
                        regime: RegimeState,
                        vol_state: VolatilityState,
                        structure: StructureMap,
                        liq_map: LiquidityMap,
                        chain: OptionsChain,
                        macro: MacroSnapshot,
                        df_1m: Optional[pd.DataFrame],
                        current_price: float,
                        conv: float) -> Optional[OptionsSignal]:
        """Low swept → buy OTM call."""

        # Price must have recovered above the swept level
        if current_price <= sweep.pool_price:
            logger.info("Sweep long: price not recovered above swept level")
            return None

        # Don't enter too far from the sweep. Window is ATR-aware: the LARGER
        # of a floor % or a multiple of ATR%, so a fast reversal that already
        # moved on a volatile name isn't rejected as "missed".
        # ⚠️ SWP.4 (2026-08-11) — MEASURE THE RECOVERY FROM THE SWEPT LEVEL, NOT
        # FROM THE WICK EXTREME. The old line used `sweep.sweep_price` — the
        # low of the raid — so the DEEPER the rejection, the FARTHER the entry
        # appeared, and the gate penalised exactly the quality it should reward.
        # Reproduced on a fabricated textbook PDL raid: a 2.36% rejection
        # produced recovery_pct 2.4% against a 2.0% cap and was REFUSED, with
        # "Sweep long: too far from sweep" — on the best setup the scorer can
        # produce. Wick depth is a measure of rejection QUALITY and `rejq_val`
        # already scores it; entry distance is properly measured from the LEVEL
        # that was reclaimed, which is the thesis being traded.
        # From the pool the same setup reads 0.11%, comfortably inside the cap.
        # OT_SWEEP_RECOVERY_FROM_POOL=0 restores the pre-SWP.4 behaviour.
        _anchor = (sweep.pool_price if (SWEEP_RECOVERY_FROM_POOL
                                        and getattr(sweep, "pool_price", 0) > 0)
                   else sweep.sweep_price)
        recovery_pct = (current_price - _anchor) / max(_anchor, 1)
        max_recovery = max(SWEEP_MAX_RECOVERY_PCT,
                           SWEEP_RECOVERY_ATR_MULT * vol_state.atr_normalized)
        if recovery_pct > max_recovery:
            logger.info(f"Sweep long: too far from sweep ({recovery_pct:.1%} > {max_recovery:.1%})")
            return None

        # BOS confirmation: 1m candle structure shows bullish shift
        if not self._confirm_bos(df_1m, "long", current_price):
            logger.info("Sweep long: no 1m BOS confirmation")
            return None

        signal = OptionsSignal(
            strategy_name    = self.name,
            setup_type       = "Sweep Reversal Long (low sweep → call)",
            direction        = "long",
            option_side      = "call",
            underlying_entry = current_price,
            underlying_stop  = sweep.sweep_price * 0.999,  # Just below sweep extreme
            underlying_target = current_price + (current_price - sweep.sweep_price) * 1.5,
            underlying_tp50  = current_price + (current_price - sweep.sweep_price) * 0.75,
            regime           = regime.primary_regime,
            vix_at_signal    = macro.vix,
            is_fed_day       = macro.is_fed_day,
            stop_loss_pct    = MAX_LOSS_PCT,
            tp_pct           = 1.0,
        )


        # v-obs: capture what KIND of level was swept, for sweep postmortems.
        # Named PDH/PDL/session = high conviction; equal-H/L = low. Value, not bool.
        _lvl_name = getattr(sweep, "swept_named_level", "") or ""
        _touches  = getattr(getattr(sweep, "pool", None), "touch_count", 0) or 0
        signal.swept_level_name = _lvl_name
        # ── Level.1 (2026-08-18) — GRADE BY TYPE, NOT BY A DEAD COUNTER ──
        # The old formula was
        #   min(1.0, (0.6 if named else 0.2) + min(touch_count,4)*0.1)
        # and **`touch_count` IS A CONSTANT** — named pools hardcode it to 1
        # at creation and nothing increments it (44,450 of 44,890 ticks read
        # exactly 1). So it collapsed to 0.7 or 0.3: a boolean wearing a
        # float's clothing, which is why the column measured 94% ties on TWO
        # unique values and looked like a null.
        # LIQ.6 (08-15) put the RUNG IN THE NAME and FEED.2 (08-17) made ON
        # High/Low real, so there is finally something to grade on.
        signal.level_strength   = _grade_level(_lvl_name)
        # N.3 2026-07-31 — closes_beyond AT ENTRY. The liquidity mapper computes
        # it (v1.3 reclaim rule) and shadow/registry gates on it, but it never
        # reached a trade row — so "did sweeps with more closes beyond the level
        # perform worse" was unanswerable after the fact. It is the single
        # cleanest sweep-vs-breakout discriminator available: a level swept and
        # RECLAIMED is a sweep; a level closed beyond repeatedly is a breakout
        # wearing a sweep's clothes. Captured at entry because it CANNOT be
        # reconstructed later — the bar window has moved on by exit.
        signal.closes_beyond = int(getattr(sweep, "closes_beyond", 0) or 0)
        signal.sweep_age_bars = int(getattr(sweep, "bars_ago", 0) or 0)
        # ── Confluence ────────────────────────────────────────────────────────
        self._add_confluence(signal,
            f"Low sweep confirmed ({sweep.rejection_pct:.1%} rejection)"
        )
        if liq_map.sweep_age_bars <= 3:
            self._add_confluence(signal, "Fresh sweep (≤3 bars)")
        elif liq_map.sweep_age_bars <= 6:
            self._add_confluence(signal, "Recent sweep (≤6 bars)")

        if vol_state.vwap > 0 and current_price > vol_state.vwap:
            self._add_confluence(signal, "Recovered above VWAP")

        if sweep.swept_named_level:
            self._add_confluence(signal, f"Named level swept: {sweep.swept_named_level}")
        elif liq_map.prev_day_low and abs(sweep.pool_price - liq_map.prev_day_low) / max(sweep.pool_price, 1) < 0.003:
            self._add_confluence(signal, "PDL swept")

        if structure.nearest_support and abs(current_price - structure.nearest_support) / current_price < 0.005:
            self._add_confluence(signal, "At structure support")

        if conv >= 0.65:
            self._add_confluence(signal, f"High setup score ({conv:.0%})")

        if len(signal.confluence_factors) < 2:
            logger.info("Sweep long: insufficient confluence")
            return None

        signal.conviction = conv
        signal.adx_at_signal = regime.adx
        signal.flat_angle_deg = getattr(regime, 'flat_angle_deg', 0.0) or 0.0

        # ── Strike selection: 0.20 delta OTM call ────────────────────────────
        target_delta = _sweep_target_delta(conv)
        contract = get_chain_fetcher().select_sweep_strike(chain, "long", target_delta)
        if contract is None:
            logger.warning("Sweep long: no suitable OTM call found")
            return None

        signal.strike        = contract.strike
        signal.expiry        = contract.expiry
        signal.entry_premium = contract.mark
        signal.contract      = contract

        logger.info(
            f"🔥 SWEEP REVERSAL LONG: "
            f"price={current_price:.2f} "
            f"pool={sweep.pool_price:.2f} swept_to={sweep.sweep_price:.2f} "
            f"call_strike={contract.strike} mark=${contract.mark:.2f} "
            f"delta={contract.delta:.3f} "
            f"confluence={signal.confluence_factors}"
        )
        return signal

    def _short_reversal(self, sweep: LiquiditySweep,
                         regime: RegimeState,
                         vol_state: VolatilityState,
                         structure: StructureMap,
                         liq_map: LiquidityMap,
                         chain: OptionsChain,
                         macro: MacroSnapshot,
                         df_1m: Optional[pd.DataFrame],
                         current_price: float,
                         conv: float) -> Optional[OptionsSignal]:
        """High swept → buy OTM put."""

        if current_price >= sweep.pool_price:
            logger.info("Sweep short: price not rejected below swept level")
            return None

        _anchor = (sweep.pool_price if (SWEEP_RECOVERY_FROM_POOL
                                        and getattr(sweep, "pool_price", 0) > 0)
                   else sweep.sweep_price)
        recovery_pct = (_anchor - current_price) / max(_anchor, 1)
        max_recovery = max(SWEEP_MAX_RECOVERY_PCT,
                           SWEEP_RECOVERY_ATR_MULT * vol_state.atr_normalized)
        if recovery_pct > max_recovery:
            logger.info(f"Sweep short: too far from sweep ({recovery_pct:.1%} > {max_recovery:.1%})")
            return None

        if not self._confirm_bos(df_1m, "short", current_price):
            logger.info("Sweep short: no 1m BOS confirmation")
            return None

        signal = OptionsSignal(
            strategy_name    = self.name,
            setup_type       = "Sweep Reversal Short (high sweep → put)",
            direction        = "short",
            option_side      = "put",
            underlying_entry = current_price,
            underlying_stop  = sweep.sweep_price * 1.001,
            underlying_target = current_price - (sweep.sweep_price - current_price) * 1.5,
            underlying_tp50  = current_price - (sweep.sweep_price - current_price) * 0.75,
            regime           = regime.primary_regime,
            vix_at_signal    = macro.vix,
            is_fed_day       = macro.is_fed_day,
            stop_loss_pct    = MAX_LOSS_PCT,
            tp_pct           = 1.0,
        )

        # v-obs: capture swept-level kind for sweep postmortems (see long path).
        _lvl_name = getattr(sweep, "swept_named_level", "") or ""
        _touches  = getattr(getattr(sweep, "pool", None), "touch_count", 0) or 0
        signal.swept_level_name = _lvl_name
        # ── Level.1 (2026-08-18) — GRADE BY TYPE, NOT BY A DEAD COUNTER ──
        # The old formula was
        #   min(1.0, (0.6 if named else 0.2) + min(touch_count,4)*0.1)
        # and **`touch_count` IS A CONSTANT** — named pools hardcode it to 1
        # at creation and nothing increments it (44,450 of 44,890 ticks read
        # exactly 1). So it collapsed to 0.7 or 0.3: a boolean wearing a
        # float's clothing, which is why the column measured 94% ties on TWO
        # unique values and looked like a null.
        # LIQ.6 (08-15) put the RUNG IN THE NAME and FEED.2 (08-17) made ON
        # High/Low real, so there is finally something to grade on.
        signal.level_strength   = _grade_level(_lvl_name)

        # ── Confluence ────────────────────────────────────────────────────────
        self._add_confluence(signal,
            f"High sweep confirmed ({sweep.rejection_pct:.1%} rejection)"
        )
        if liq_map.sweep_age_bars <= 3:
            self._add_confluence(signal, "Fresh sweep (≤3 bars)")
        elif liq_map.sweep_age_bars <= 6:
            self._add_confluence(signal, "Recent sweep (≤6 bars)")

        if vol_state.vwap > 0 and current_price < vol_state.vwap:
            self._add_confluence(signal, "Rejected below VWAP")

        if sweep.swept_named_level:
            self._add_confluence(signal, f"Named level swept: {sweep.swept_named_level}")
        elif liq_map.prev_day_high and abs(sweep.pool_price - liq_map.prev_day_high) / max(sweep.pool_price, 1) < 0.003:
            self._add_confluence(signal, "PDH swept")

        if structure.nearest_resistance and abs(current_price - structure.nearest_resistance) / current_price < 0.005:
            self._add_confluence(signal, "At structure resistance")

        if conv >= 0.65:
            self._add_confluence(signal, f"High setup score ({conv:.0%})")

        if len(signal.confluence_factors) < 2:
            logger.info("Sweep short: insufficient confluence")
            return None

        signal.conviction = conv
        signal.adx_at_signal = regime.adx
        signal.flat_angle_deg = getattr(regime, 'flat_angle_deg', 0.0) or 0.0

        # ── Strike selection: 0.20 delta OTM put ─────────────────────────────
        target_delta = _sweep_target_delta(conv)
        contract = get_chain_fetcher().select_sweep_strike(chain, "short", target_delta)
        if contract is None:
            logger.warning("Sweep short: no suitable OTM put found")
            return None

        signal.strike        = contract.strike
        signal.expiry        = contract.expiry
        signal.entry_premium = contract.mark
        signal.contract      = contract

        logger.info(
            f"🔥 SWEEP REVERSAL SHORT: "
            f"price={current_price:.2f} "
            f"pool={sweep.pool_price:.2f} swept_to={sweep.sweep_price:.2f} "
            f"put_strike={contract.strike} mark=${contract.mark:.2f} "
            f"delta={contract.delta:.3f} "
            f"confluence={signal.confluence_factors}"
        )
        return signal

    def _orb_released_price(self, sweep: LiquiditySweep) -> bool:
        """Gate: has the ORB RELEASED its claim on price, so a sweep may fire?

        Rule (hardcoded, v3.2): while the ORB has a live claim on price, the ORB
        owns it and a sweep must NOT fire — no double-dipping the same tape. The
        ORB owns price when:
          - price is still inside the range awaiting a break  (WAITING_FOR_BREAK)
          - a break happened and it is awaiting/at retest      (ARMED_LONG / SHORT)
          - a position is open on the ORB                      (OPEN_LONG / SHORT)
          - the range failed back into itself                  (INVALIDATED,
            invalidation_reason == 'close_inside') — the ORB reclaimed price; it
            did NOT release it to a sweep.

        The ORB has RELEASED price — sweep may fire — only when:
          - past the 11:00 ET ORB cutoff (ORB_NO_ENTRY_AFTER_ET): the ORB window
            is over, sweep reversal is free to work any level.
          - no established range for today (nothing to own).
          - the retest went STALE (invalidation_reason == 'timeout'), or
          - price RAN AWAY past the 50% level with no retest
            (invalidation_reason == 'runaway'),
          - or the ORB already EXPIRED.

        NB: this replaces the old broke_high/broke_low check, which let a sweep
        fire the instant a break REGISTERED — i.e. while the ORB was still ARMED
        and awaiting its retest — exactly the overlap this rule forbids.
        """
        now = now_et()
        if (now.hour, now.minute) >= ORB_NO_ENTRY_AFTER_ET:
            return True   # ORB window closed — sweep works any level

        eng = get_orb_engine()
        d   = eng.data
        if d.orb_high <= 0 or d.orb_low <= 0:
            return True   # no established range to own price

        # ORB still owns price → sweep blocked.
        if d.state in (ORBState.WAITING_FOR_BREAK,
                       ORBState.ARMED_LONG, ORBState.ARMED_SHORT,
                       ORBState.OPEN_LONG, ORBState.OPEN_SHORT):
            return False

        # ORB gave price up ONLY via runaway or timeout. A close_inside means the
        # ORB reclaimed the range — it did not release price to a sweep.
        if d.state == ORBState.INVALIDATED:
            return d.invalidation_reason in ("runaway", "timeout")

        # EXPIRED (or any dormant terminal state) → released.
        return True

    def _confirm_bos(self, df_1m: Optional[pd.DataFrame],
                      direction: str, current_price: float) -> bool:
        """
        Confirm 1-min Break of Structure in the reversal direction.
        BOS = price closes above the most recent swing high (long) or below the
        most recent swing low (short), over SWEEP_BOS_LOOKBACK closed candles.
        Also accepts a BOS that already CLOSED on the just-closed candle, so a
        one-tick-late evaluation doesn't miss it. Uses closed candles only.
        """
        lb = max(2, SWEEP_BOS_LOOKBACK)
        if df_1m is None or len(df_1m) < lb + 1:
            return False

        # last `lb` closed candles (exclude the current forming candle)
        recent     = df_1m.iloc[-(lb + 1):-1]
        last_close = float(df_1m.iloc[-2]["close"])

        if direction == "long":
            ref = float(recent["high"].max())
            return current_price > ref or last_close > ref
        else:  # short
            ref = float(recent["low"].min())
            return current_price < ref or last_close < ref
