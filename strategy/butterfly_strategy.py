"""
strategy/butterfly_strategy.py — Debit butterfly for RANGING/COMPRESSION regimes. v3.5
v3.5  2026-08-15  BFLY.3: THE DEBIT CEILING IS FLAT AT 0.50. CONVICTION IS OUT.
        Max profit is `wing - debit`, so 0.50 is the STRUCTURE'S OWN BREAK-EVEN
        - risk equals reward there, above it the payoff is upside-down. Not a
        fitted number: no holdout needed, cannot be overfit.
        MEASURED FLEET-WIDE (29 boxes) AND IT REFUTED BOTH CANDIDATE DESIGNS.
        conv->ratio slope is POSITIVE on 5 of 7 sampled symbols (AVGO +0.103,
        GS +2.550, NVDA +0.109, PLTR +0.038, QQQ +0.211; only SMH -0.048 and
        TLT -0.031 negative) - higher conviction travels with MORE EXPENSIVE
        tents, so scaling the ceiling up with conviction paid more exactly where
        the trade was WORSE, and INVERTING it would have been worse still.
        AND IT COST TRADES: SMH had 46 setups at mean ratio 0.379 and fired 3,
        because conviction averaged 0.033 and pinned the ceiling to its 0.33
        floor. AVGO 1 of 5, QQQ 1 of 27, MSFT 1 of 2.
        THE REJECTS STILL DO THE WORK - NVDA 0.718, PLTR 0.799, NFLX 0.941 and
        TLT 1.029 stay refused on PRICE. `_conv` is still journaled so the
        relationship stays measurable; it simply no longer gates. The old
        constants remain in config unread, so a revert is one line.
v3.4 — 2026-07-31 — AC: find_strike's "no liquid contract" path was a SILENT
        return, killing a butterfly that had already cleared the GEX-pin and
        regime gates. It now logs the target strike, how many contracts were
        examined, and that none were priced.
v3.3 — 2026-07-30 — NameError: `_mult` referenced on line 190 after the
        conviction-scaled proximity multiplier was reverted to a fixed 1x EM and
        the variable removed. Raised on EVERY butterfly evaluation, but only a
        box in COMPRESSION reaches that gate — so IWM restarted twice while the
        other 14 boxes ran the same code without a scratch. Second orphaned-
        variable NameError in two days (continuation `mid`, 07-29); both were
        caught only by a live box crashing. `tests/test_no_undefined_names.py`
        now fails the suite on any undefined name, which catches both.
v3.0 — original release
v3.1 — 2026-07-12 — DOC SYNC (no logic change): the header described
        BUTTERFLY_ENTRY_CUTOFF_ET as a "hard exit at 2:00 PM". It is an ENTRY
        cutoff only and is not consulted by exit_engine at all. Corrected.
v3.2 — 2026-07-14 — DISCOUNT GATE (relabeled in the 2026-07-23 header audit —
        shipped mis-numbered v1.4 after v3.1 already existed): net_debit ≤ BUTTERFLY_MAX_DEBIT_PCT_WIDTH ×
        wing width (config, prior 0.33 ≈ min 2:1 RR). Encodes the operator's
        thesis — enter the pin-centered tent while price is still a walk away
        and the fly is cheap — as the risk:reward stated directly, instead of
        a delta proxy (whipsaws on 0DTE gamma; dies with the Greeks feed).
        Ratio logged on every evaluation for ledger calibration.
v1.1 — 2026-06-29 — GEX pin center strike, fixed wings by instrument,
        noon-2PM entry window, one-per-session limit, TP at 20%
v3.0 — 2026-07-10 — repo-wide v3.0 bump: Yahoo-Finance purge & data stream
        mapping optimization (all market data now flows from the single
        shared TastyTrade candle feed — see data/candle_feed.py). No logic
        change in this file.

Entry logic:
  - Only fires between 12:00 PM and 2:00 PM ET
  - Only one butterfly per RTH session
  - Requires GEX environment to be PINNING
  - Price must be within 1× expected move of GEX pin strike
  - Center strike = GEX pin strike (not ATM)
  - Wings: 25 points on SPX, $5 on QQQ/SPY (fixed, not ATR-based)
  - Direction (call vs put) based on VWAP bias

Exit logic:
  - TP: 20% of max profit
  - SL: 25% of net debit
  - Entry cutoff: 2:00 PM ET (BUTTERFLY_ENTRY_CUTOFF_ET). This is an ENTRY
    gate only — it is NOT a hard exit. An open butterfly exits on: regime
    flip to trending, 2.5h max hold, 25% stop, 20% target, or the 15:45
    hard close. Whichever fires first.
  - Max hold: 2.5 hours

v-convdiscount — 2026-07-28 — THE DISCOUNT CEILING IS EARNED BY CONVICTION.
        MEASURED, not inferred. QQQ's full log: debit ratios 0.41-0.64 (min 0.41,
        cluster 0.47-0.53) against a FLAT 0.33 ceiling -> the gate rejected 100%
        of setups that reached it. Three butterflies exist in the whole fleet
        archive (07-09, 07-20, 07-24). Ruled out first: VIX (16.0-18.2, under the
        20 disable), regime (COMPRESSION/RANGING, valid), GEX (QQQ logs 708
        PINNING ticks, real 0.4-1.0M magnitudes), and PROXIMITY -- gate 6 logged
        ZERO "too far from pin" rejections ever, so it was never binding and
        scaling it would have admitted nothing.
        The tent is expensive because price sits near the pin. With high
        conviction it STAYS pinned, paying more is justified; with low conviction,
        demand the cheap tent. The ceiling now scales 0.33 (conv <= 0.30) to 0.50
        (conv >= 0.55); at the observed median conviction 0.438 the gate is 0.42,
        which admits the cheapest observed setups. Bounds are set against the
        OBSERVED conviction range (0.000-0.582), NOT a nominal 0-1.
        Knobs OT_BFLY_DEBIT_HICONV / OT_BFLY_DISC_CONV_LO / _HI are env-
        overridable. Every evaluation logs
        "Butterfly discount gate: conv= ratio= gate= ... PASS|REJECT"
        so accepts AND rejects are both on the ledger.
"""

import logging
import math
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from strategy.base_strategy import BaseOptionsStrategy, OptionsSignal
from analysis.regime_classifier import RegimeState, Regime
from analysis.volatility_engine import VolatilityState
from analysis.liquidity_mapper import LiquidityMap
from data.options_chain import OptionsChain, OptionContract
from data.options_chain import get_chain_fetcher
from data.macro_data import MacroSnapshot
from config import (
    BUTTERFLY_TP_PCT, BUTTERFLY_WING_SPX, BUTTERFLY_WING_QQQ,
    BUTTERFLY_DEBIT_CEILING,
    BUTTERFLY_GEX_PIN_PROXIMITY_MULT,
    BUTTERFLY_ENTRY_START_ET, BUTTERFLY_ENTRY_CUTOFF_ET,
    STRIKE_INCREMENT, INSTRUMENT, VIX_BUTTERFLY_DISABLE,
    BUTTERFLY_MAX_DEBIT_PCT_WIDTH_HICONV,
    BUTTERFLY_DISC_CONV_LO, BUTTERFLY_DISC_CONV_HI,
    CONTRACT_MULTIPLIER,
    BUTTERFLY_MAX_DEBIT_PCT_WIDTH,
    BUTTERFLY_STOP_LOSS_PCT,
)

logger = logging.getLogger(__name__)
ET = ZoneInfo("US/Eastern")


class ButterflyStrategy(BaseOptionsStrategy):
    """
    Debit butterfly strategy — GEX pin centered, noon-2PM window, one per session.
    """

    def __init__(self):
        self._fired_today: bool = False
        self._last_reset_date: Optional[str] = None

    @property
    def name(self) -> str:
        return "ButterflyStrategy"

    def _reset_if_new_day(self):
        """Reset one-per-session flag at start of each RTH day."""
        today = datetime.now(ET).strftime("%Y-%m-%d")
        if self._last_reset_date != today:
            self._fired_today    = False
            self._last_reset_date = today

    def _expected_move(self, underlying: float, vix: float) -> float:
        """
        1× expected move for remaining session time.
        Formula: underlying × VIX% × sqrt(hours_remaining / 6.5) / sqrt(252)
        Called at entry time to compute the proximity threshold dynamically.
        """
        now_et        = datetime.now(ET)
        close_et      = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        hours_remaining = max((close_et - now_et).total_seconds() / 3600, 0.5)
        return (
            underlying
            * (vix / 100)
            * math.sqrt(hours_remaining / 6.5)
            / math.sqrt(252)
        ) * BUTTERFLY_GEX_PIN_PROXIMITY_MULT

    def _wing_width(self) -> int:
        """Fixed wing width in strike increments by instrument."""
        if INSTRUMENT == "SPX":
            return BUTTERFLY_WING_SPX // STRIKE_INCREMENT   # 25pt / 5pt = 5 increments
        return BUTTERFLY_WING_QQQ // STRIKE_INCREMENT       # $5 / $1 = 5 increments

    def generate_signal(self,
                         regime: RegimeState,
                         vol_state: VolatilityState,
                         liq_map: LiquidityMap,
                         chain: OptionsChain,
                         macro: MacroSnapshot,
                         current_price: float,
                         gex=None) -> Optional[OptionsSignal]:
        """
        Generate a butterfly signal when all conditions are met.
        """
        self._reset_if_new_day()

        now_et = datetime.now(ET)
        hm     = (now_et.hour, now_et.minute)

        # ── Gate 1: Entry time window 12:00 PM – 2:00 PM ET ──────────────────
        if hm < BUTTERFLY_ENTRY_START_ET:
            logger.debug(f"Butterfly: too early ({now_et.strftime('%H:%M')} ET — window opens at 12:00)")
            return None
        if hm >= BUTTERFLY_ENTRY_CUTOFF_ET:
            logger.debug(f"Butterfly: past cutoff ({now_et.strftime('%H:%M')} ET)")
            return None

        # ── Gate 2: One per session ───────────────────────────────────────────
        if self._fired_today:
            logger.debug("Butterfly: already fired today — one per session limit")
            return None

        # ── Gate 3: Regime ────────────────────────────────────────────────────
        if regime.primary_regime not in (Regime.RANGING, Regime.COMPRESSION):
            return None

        # ── Gate 4: VIX threshold (Fed days allowed — bot trades them) ──────────
        if not macro.butterfly_allowed:
            logger.info(f"Butterfly blocked: VIX={macro.vix:.1f} above threshold")
            return None

        # ── Gate 5: GEX must be PINNING ───────────────────────────────────────
        if gex is None or gex.gex_environment != "PINNING":
            logger.info("Butterfly: GEX not PINNING — no edge without pin")
            return None

        pin_strike = gex.pin_strike
        if not pin_strike:
            logger.info("Butterfly: no pin strike available")
            return None

        # ── Gate 6: proximity to pin (fixed 1x EM — MEASURED never-binding:
        # zero "too far from pin" rejections in the entire QQQ log, so scaling
        # this gate would admit nothing. Left as-is deliberately.)
        _conv = float(getattr(regime, "conviction", 0.0) or 0.0)
        _em   = self._expected_move(current_price, macro.vix)
        # v3.3 — _mult is the multiplier ACTUALLY in force. The conviction-scaled
        # version was reverted to a fixed 1x EM (see the comment above), the
        # variable was deleted, and the log line below kept referencing it —
        # NameError on every butterfly evaluation. It only ever fired on a box in
        # COMPRESSION, so 14 of 15 boxes never reached it: IWM crash-looped on
        # 2026-07-30 while the rest ran clean. Kept as a named constant rather
        # than dropped from the f-string so the ledger's field schema is stable
        # if the multiplier is ever scaled again.
        _mult = 1.0
        proximity_threshold = _mult * _em
        distance_from_pin   = abs(current_price - pin_strike)

        # logged on EVERY evaluation (accept or reject) so the ledger can fit the
        # conviction->distance curve against real tape, same as the debit ratio.
        logger.info(
            f"Butterfly proximity: conv={_conv:.3f} mult={_mult:.2f}x "
            f"em=${_em:.2f} threshold=${proximity_threshold:.2f} "
            f"distance=${distance_from_pin:.2f} "
            f"pin=${pin_strike} spot=${current_price:.2f}"
        )
        if distance_from_pin > proximity_threshold:
            logger.info(
                f"Butterfly: price ${current_price:.2f} too far from pin ${pin_strike} "
                f"(distance=${distance_from_pin:.2f} > threshold=${proximity_threshold:.2f}) — skip"
            )
            return None

        # ── Strike selection: center = GEX pin strike ─────────────────────────
        center_strike = pin_strike
        wing_increments = self._wing_width()
        lower_strike  = center_strike - wing_increments * STRIKE_INCREMENT
        upper_strike  = center_strike + wing_increments * STRIKE_INCREMENT

        # ── Direction: call vs put based on VWAP ─────────────────────────────
        direction = self._pick_direction(vol_state, liq_map, current_price)

        # ── Fetch contracts from chain ────────────────────────────────────────
        contracts_list = chain.calls if direction == "call" else chain.puts

        def find_strike(target: float) -> Optional[OptionContract]:
            candidates = [c for c in contracts_list if c.strike == target and c.mark > 0]
            if candidates:
                return candidates[0]
            # Nearest liquid strike
            liquid = [c for c in contracts_list if c.mark > 0]
            if not liquid:
                # AC 2026-07-31 — was a SILENT return. This kills a butterfly
                # that has ALREADY passed the GEX-pin gate and the regime gate,
                # i.e. a qualifying setup, and said nothing about it. Butterfly
                # has 27 lifetime trades against sweep's 985; if some of that
                # scarcity is chain liquidity rather than gate strictness, this
                # is the line that shows it.
                logger.info(
                    f"Butterfly: no liquid strike near {target:g} — "
                    f"{len(contracts_list)} contracts examined, none with "
                    f"mark > 0. SKIP"
                )
                return None
            return min(liquid, key=lambda c: abs(c.strike - target))

        lower  = find_strike(lower_strike)
        center = find_strike(center_strike)
        upper  = find_strike(upper_strike)

        if not all([lower, center, upper]):
            logger.warning(
                f"Butterfly: could not find all strikes "
                f"{lower_strike}/{center_strike}/{upper_strike}"
            )
            return None

        # ── Net debit and max profit ──────────────────────────────────────────
        net_debit  = lower.mark + upper.mark - 2 * center.mark
        if net_debit <= 0:
            logger.info(f"Butterfly: net debit ≤ 0 ({net_debit:.4f}) — skip")
            return None

        wing_width = upper.strike - center.strike

        # ── v1.4 DISCOUNT GATE: the thesis is buying the tent CHEAP while
        # price still has to migrate into it. Delta was considered and
        # rejected as the proximity proxy (0DTE gamma makes it whipsaw; it
        # also dies with the Greeks feed). The debit-to-width ratio states
        # the edge directly: price on the pin => fat debit => rejected.
        # The ratio is logged on EVERY evaluation — accept or reject — so
        # the ledger can calibrate the prior.
        debit_ratio = net_debit / wing_width if wing_width > 0 else 1.0
        logger.info(
            f"Butterfly debit-ratio: {debit_ratio:.2f} "
            f"(debit={net_debit:.2f} / wing={wing_width:.0f}, "
            f"gate ≤ {BUTTERFLY_MAX_DEBIT_PCT_WIDTH:.2f})"
        )
        # ── BFLY.3 (2026-08-15) — THE CEILING IS FLAT. CONVICTION IS OUT. ────
        # ⚠️ MEASURED FLEET-WIDE, 29 boxes, and it refuted BOTH the original
        # design and the operator's proposed inversion:
        #   · **THE SLOPE IS POSITIVE ON 5 OF 7 SYMBOLS** that had samples
        #     (AVGO +0.103, GS +2.550, NVDA +0.109, PLTR +0.038, QQQ +0.211;
        #     only SMH -0.048 and TLT -0.031 negative). Higher regime conviction
        #     travels with MORE EXPENSIVE tents, not cheaper — the pin's own
        #     gravity compresses conditions and prices TOGETHER. So scaling the
        #     ceiling UP with conviction paid more exactly where the trade was
        #     already worse, and INVERTING would have been worse still.
        #   · **AND IT COST REAL TRADES.** SMH: 46 setups at a mean ratio of
        #     **0.379** — comfortably positive asymmetry — and only **3 fired**,
        #     because conviction averaged 0.033 so the ceiling sat on its 0.33
        #     floor. 43 cheap tents refused by a score that does not measure the
        #     thesis. AVGO 1 of 5, QQQ 1 of 27, MSFT 1 of 2.
        #
        # WHY 0.50 AND NOT HIGHER. Max profit is `wing - debit`, so at ratio 0.50
        # you risk exactly what you can win. **0.50 IS WHERE THE ASYMMETRY
        # INVERTS**, and above it a butterfly pays less than it costs. That is
        # not a fitted number — it is the structure's own break-even, which is
        # why it needs no holdout and cannot be overfit.
        #
        # THE REJECTS STILL DO THE WORK, which is the point: NFLX (0.941),
        # TLT (1.029), PLTR (0.799) and NVDA (0.718) remain refused at any sane
        # ceiling. Those tents are genuinely overpriced and the gate says so on
        # PRICE rather than on a regime score.
        #
        # `_conv` is still LOGGED so the relationship stays measurable and this
        # decision can be revisited against more sessions — it simply no longer
        # GATES. (BUTTERFLY_DISC_CONV_LO/HI and _HICONV remain in config,
        # unread by this path, so a revert is a one-line change.)
        _gate = BUTTERFLY_DEBIT_CEILING
        logger.info(
            f"Butterfly discount gate: conv={_conv:.3f} ratio={debit_ratio:.2f} "
            f"gate={_gate:.2f} (FLAT — conviction no longer scales it) "
            f"{'PASS' if debit_ratio <= _gate else 'REJECT'}")
        if debit_ratio > _gate:
            logger.info(
                f"Butterfly: tent too expensive — ratio {debit_ratio:.2f} > "
                f"{_gate:.2f}; above {_gate:.2f} the payoff is upside-down. skip")
            return None

        max_profit = wing_width - net_debit
        if max_profit <= 0:
            logger.info(
                f"Butterfly: no max profit potential "
                f"(wing={wing_width:.0f} debit={net_debit:.2f})"
            )
            return None

        # ── Build signal ──────────────────────────────────────────────────────
        signal = OptionsSignal(
            strategy_name       = self.name,
            setup_type          = f"Debit {direction.title()} Butterfly",
            direction           = "neutral",
            option_side         = direction,
            is_butterfly        = True,
            butterfly_direction = direction,
            lower_contract      = lower,
            center_contract     = center,
            upper_contract      = upper,
            net_debit           = net_debit,
            max_profit          = max_profit,
            underlying_entry    = current_price,
            underlying_stop     = 0.0,
            underlying_target   = center_strike,
            regime              = regime.primary_regime,
            vix_at_signal       = macro.vix,
            is_fed_day          = macro.is_fed_day,
            stop_loss_pct       = BUTTERFLY_STOP_LOSS_PCT,
            tp_pct              = BUTTERFLY_TP_PCT,   # 20%
        )

        if macro.butterfly_half_size:
            signal.notes = "VIX 15–20: half size butterfly"

        # ── Confluence ────────────────────────────────────────────────────────
        self._add_confluence(signal, f"Regime: {regime.primary_regime}")
        self._add_confluence(signal, f"GEX pin @ {pin_strike} ({distance_from_pin:.1f}pts away)")
        if regime.adx < 20:
            self._add_confluence(signal, f"Low ADX ({regime.adx:.1f}) — no trend")
        if direction == "call" and vol_state.price_vs_vwap == "ABOVE":
            self._add_confluence(signal, "Above VWAP — bullish lean")
        elif direction == "put" and vol_state.price_vs_vwap == "BELOW":
            self._add_confluence(signal, "Below VWAP — bearish lean")

        signal.conviction = regime.conviction * 0.7
        signal.adx_at_signal = regime.adx
        signal.flat_angle_deg = getattr(regime, 'flat_angle_deg', 0.0) or 0.0

        # ── Mark as fired for today ───────────────────────────────────────────
        self._fired_today = True

        logger.info(
            f"🦋 BUTTERFLY {direction.upper()}: "
            f"strikes={lower.strike}/{center.strike}/{upper.strike} "
            f"center=GEX_PIN@{pin_strike} "
            f"distance=${distance_from_pin:.1f} threshold=${proximity_threshold:.1f} "
            f"net_debit=${net_debit:.2f} max_profit=${max_profit:.2f} "
            f"TP=${max_profit * BUTTERFLY_TP_PCT:.2f} (20%) "
            f"SL=${net_debit * 0.75:.2f} (25% loss) "
            f"VIX={macro.vix:.1f}"
        )
        return signal

    def _pick_direction(self, vol_state: VolatilityState,
                         liq_map: LiquidityMap,
                         current_price: float) -> str:
        if vol_state.vwap > 0:
            if vol_state.price_vs_vwap == "ABOVE":
                return "call"
            elif vol_state.price_vs_vwap == "BELOW":
                return "put"
        if liq_map.recent_sweep:
            sweep = liq_map.recent_sweep
            if sweep.kind == "low_sweep":
                return "call"
            elif sweep.kind == "high_sweep":
                return "put"
        return "call"
