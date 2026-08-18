"""
strategy/continuation_strategy.py — Trend-continuation on pullback. — v1.8
v1.8  2026-08-18  STR.1: sets `vix_at_signal`. It did not, and neither did
        the other highest-volume strategy, so `trades.vix_at_entry` fell to its
        REAL DEFAULT 0.0 on most rows - **58% of the book**. The separation
        probe read that default as a measured value and reported "58% ties,
        median 0.000 in both arms", which looks exactly like "VIX does not
        separate outcomes". A COLLECTION GAP WEARING THE COSTUME OF A NULL.
        A column with a numeric DEFAULT cannot distinguish "measured zero" from
        "never written" - check for a writer before calling a primitive dead.
v1.7 — 2026-08-13 — GRD.2: POPULATE `underlying_target`. `trend_strike_plan`
        has ALWAYS computed it (EM fraction scaled by ADX + conviction) and USED
        IT to pick the strike, then DISCARDED it — so the bot was never
        target-free, it was TARGET-BLIND, and three consumers sat inert on 77% of
        fleet volume: `_rrr()` returned None on every continuation signal (which
        is why `rrr` appears in ORB's scorer table and nowhere else, and why the
        MIN_RRR floor was structurally inert on most of the book);
        `_pools_in_path` scans `entry < p < target`, so with 0.0 a LONG's window
        is EMPTY BY CONSTRUCTION and `liquidity_clear` was a structural constant
        at 1.000 rather than a measured one; and
        `exit_engine._update_post_target_trail` is guarded on `> 0`, so
        continuation always fell back to the blunt 85% trail instead of the FVG
        floor past 100% TP.
        ⚠️ NOT A TAKE-PROFIT, AND NOTHING CONSUMES IT AS ONE. The operator's
        no-target design stands — "the multiple is a want, not a need... use
        stops creatively so nothing stops them running when they're correct."
        This is the R denominator and the trail's reference. A test pins that no
        exit fires on reaching it.
        ⚠️ THE ENTRY GATE BARELY MOVES, and that is arithmetic not opinion:
        `liq_score = max(1 - n*0.25, 0)` at weight 0.20 removes AT MOST 0.20
        from a continuation total whose measured p50 is 0.885, against a
        grade_b bar of 0.55 — even 4+ blocking pools leaves 0.685 and still
        fires. THE REAL CHANGE IS THE EXIT TRAIL. A test pins the arithmetic so
        the claim fails loudly if a weight or the bar moves.
        ORB's A/B grade also reads `_pools_in_path`, but ORB already populated
        its target and GRD.1 set continuation's grade_a to 1.01, so that path is
        untouched here.
v1.6 — 2026-08-11 — CNT.7: THE CONFIRMATION WAS TOO LITERAL AND WAS REJECTING
        TIES. v1.5 required the confirmation bar to close STRICTLY beyond the
        tagging bar's extreme. First live session, on a strong downtrend day the
        operator watched go untraded:
            QQQ  need < 720.26  got 720.34   (8c,  0.011%)
            PLTR need < 175.18  got 175.22   (4c,  0.023%)
            CVX  need > 194.94  got 194.91   (3c)
            TSLA need > 334.39  got 334.35   (4c)
            SPX  need < 7735.58 got 7737.13  (1.55, 0.02%)
        The bar closed essentially AT the extreme and failed on a rounding-level
        margin. The thesis was right; the comparison was not.
        NOW: the threshold carries a tolerance of CONT_CONFIRM_TOL_ATR * ATR —
        the same principle as the BOS distance floor, because a fixed cent value
        cannot serve both QQQ and GLD.
        ⚠️ 0.40 IS DERIVED FROM THE SESSION. Every logged miss in ATR units
        splits into two populations with NOTHING between them: ties at
        0.073-0.360, genuine failures at 1.133-3.355. A 3x gap. My first draft
        used 0.05, which would have rejected EVERY case above — a no-op wearing
        the name of a fix, caught only by testing the constant against the
        actual logged misses instead of shipping it.
        ⚠️ ONE SESSION of evidence. The gap is wide and the classes unambiguous,
        but re-derive once a week of post-deploy misses exists.
        Also logs the MISS and the TOLERANCE, because being able to read
        `need` against `got` is exactly what turned "the gate is firing" into
        "the gate is failing by four cents".
        Kill switch: OT_CONT_CONFIRM_TOL_ATR=0 restores v1.5 exactly.
v1.5 — 2026-08-10 — 1-BAR CONFIRMATION. The FVG tag alone commits while price is
        still moving AGAINST the trend: the trade is a bet on a resumption that
        has not happened yet. Leading suspect for the 40% never-favourable
        population and for the micro-scratch cluster the operator named — 0.3
        min holds on ~$1K positions exiting at +/-$49, i.e. one or two 15s
        ticks, before the thesis could be true or false.
        Now the bar AFTER the tag must CLOSE BEYOND the tagging bar's extreme in
        the trend direction. A miniature break of structure, and deliberately
        the WEAKEST test that still requires price to have DONE something — not
        "closed green" (noise inside a pullback), not "reclaimed the gap edge"
        (takes several bars, loses the 1-bar property).
        ⚠️ FEWER TRADES BY DESIGN. Setups that never confirm are never taken;
        those are the entries that were being paid for in order to find out.
        ⚠️ WORSE ENTRY PRICE by roughly one bar, in exchange for the resumption
        having started. Side effect worth knowing: it pushes BOS's seeded
        protected level further from entry, since that level is taken from the
        first bar closing above entry — so the hair-trigger seeding shrinks
        without BOS being touched at all.
        ⚠️ EXPECT A LOWER WIN RATE AND A BETTER LOSS PROFILE. If the tagging bar
        was the low, the confirmation bar captures the first thrust and we buy
        the top of it. Read win rate and loss distribution TOGETHER — win rate
        alone will look like a regression.
        ⚠️ SHIPPED WITHOUT THE OFFLINE COUNTERFACTUAL. The replay that would
        have priced this against the 12-session corpus was not run; the operator
        chose to ship and measure live. The first week of post-deploy data IS
        the evidence, and OT_CONT_REQUIRE_CONFIRM=0 is both kill switch and A/B
        control.
v1.3 — 2026-07-28 — PULLBACK TRIGGER REWIRED: BB-midline -> 1-min wick TAGGING
        the nearest unfilled 5-min FVG (edge-tag, >= 1 cent penetration,
        CONTINUATION_FVG_TAG_MIN). The midline trigger was too conservative — a
        strong trend outruns the midline so it never presented (continuation sat
        out the SPX 2026-07-28 rip for exactly this). FVGs are where price
        actually returns in a trend. Uses the existing structure_analyzer FVG
        primitive (smap.fvgs, already built every tick in main). Removed the
        orphaned CONTINUATION_MIDLINE_ATR / CONTINUATION_MAX_PULLBACK_R. New
        params structure + df_1m threaded from the main dispatch. STRATEGY change
        (not an L1 definition) — freeze-safe, live this week to observe fires.
v1.2 — 2026-07-22 — stop backstop 40%% -> 25%% (CONTINUATION_STOP_LOSS_PCT now
        lives in config, env OT_CONT_STOP_PCT). Paired with exit_engine v4.0:
        5m-anchored trail + theta-bleed enabled for this strategy.
v1.1 — 2026-07-22 — UNBLOCKED (defect W). This strategy could NEVER fire.
        It read `getattr(trend, "momentum", "")`, but momentum lives on
        TrendVote (per-timeframe) and was never aggregated onto TrendState —
        the object main.py actually passes in. So momentum was ALWAYS "",
        and BOTH paths dead-ended before ever reaching strike selection:
          standalone: "" != "ACCELERATING"          -> return None, every tick
          handoff:    "" not in (ACCELERATING,...)  -> return None, every tick
        Every gate above it (trending regime, conviction floor, midline
        proximity, pullback depth) could pass perfectly and the trade still
        died here. The getattr default swallowed the missing attribute, so it
        threw no error and logged nothing — it looked exactly like "conditions
        never set up". Live from 2026-07-18 deploy to this fix: ZERO fires
        fleet-wide, by construction.
        FIX: read trend.primary_momentum (trend_engine v3.2 surfaces it from
        the 5m vote, same as primary_adx).
        ALSO: the resumption vocabulary was wrong. This checked for "STEADY",
        which trend_engine NEVER emits — its values are ACCELERATING /
        DECELERATING / FLAT. "STEADY" was a phantom, so even correctly wired
        the handoff path would have been stricter than designed. The intent
        ("handoff accepts steady, standalone demands acceleration") now maps
        onto the REAL vocabulary: handoff accepts ACCELERATING or FLAT (i.e.
        not actively decelerating against us); standalone demands
        ACCELERATING. "" (no 5m vote) blocks BOTH — unknown is never a green
        light.

v1.0 — 2026-07-18 — The trend-native trade the trend_engine v3.1 fix enables.
        Fires ONLY when regime is trending (a high bar now that direction
        resolves). Waits for price to pull back to the BB midline, then enters
        on a LOW-BAR resumption (momentum flips back toward the trend). The
        intelligence lives in the EXIT (exhaustion detection), not the entry —
        "make entry easy, make exit smart."

DESIGN (per spec, options_trader_v3 continuation-trade decisions):
  GATE       regime TRENDING_BULL/BEAR + conviction floor + pullback not so
             deep the trend is arguably broken.
  LEVEL      BB midline (vol_state.bb_middle) — dynamic support in an uptrend,
             resistance in a downtrend. Reuses the condor anchor.
  ENTRY      low bar: trend alive + price returned to the midline + momentum
             flipping back toward the trend (DECELERATING -> ACCELERATING).
  STOP       regime-change OR MAX_LOSS_PCT (40%), whichever first. Regime
             invalidation IS the smart stop (the trade is defined by the trend).
             underlying_stop set just past the pullback extreme for reference /
             structure, but the governing exits are regime-flip + the 40% floor.
  EXIT       exhaustion-based (owned by exit_engine, informed here via setup):
             momentum divergence + extension-from-midline; trail arms on the
             resumption confirmation so theta goes silent immediately.
  VEHICLE    debit directional (long call in an uptrend, long put in a downtrend).
  CONTEXT    two entry paths — ORB-runaway HANDOFF (looser: the runaway already
             proved directional force) and STANDALONE mid-session (stricter:
             self-sourced trend+pullback+resumption). handoff flag toggles it.

SAFETY: this module is inert until wired in AND enabled. main.py registers it
NOTE (v1.1): earlier text here described a CONTINUATION_ENABLED flag
(default False, "ships dark"). No such flag was ever defined or checked
anywhere in the repo — the strategy dispatches live from main.py
Priority 2.5. The claim was stale doc, not a real gate; what actually
kept it dark was the momentum defect above. Left here so nobody goes
hunting for a flag that does not exist. Historical text follows:
behind CONTINUATION_ENABLED (default False) so it ships dark and is proven in
paper/backtest before it can affect live dispatch.

v1.3.1 — 2026-07-29 — HOTFIX. v1.3 deleted the BB-midline block (which defined
        `mid`) but left four references to it: the structural stop
        (`underlying_stop = mid +/- 0.5*atr`), the confluence string, and the log
        line. Result: NameError: name 'mid' is not defined, raised EVERY TICK,
        killing the main loop before any strategy could evaluate. Fleet-wide, 15
        boxes, ZERO trades taken 2026-07-29 open through ~09:55 ET.
        Fix: the stop now anchors to the FVG, which is structurally correct --
        the gap IS the level the entry was taken on. Long tags gap.top from
        above, so a close through gap.bottom means the pullback became a
        breakdown -> stop = gap.bottom - 0.5*atr. Short mirrors on gap.top.
        Confluence and log lines now report the gap range instead of a midline
        that no longer exists.
        LESSON: v1.3 compiled and its FVG-tag geometry was unit-tested, but the
        full generate_signal path was never executed -- the tastytrade SDK is not
        installable in the sandbox, so only the extracted block was exercised. A
        compile check does not catch an unbound name on a branch that never ran.
        The canary must import and CALL the strategy on a box before deploy.

v1.3.3 — 2026-07-30 — LOG THE DECLINES (all of them). v1.3/v1.3.1 had THREE silent `return
        None` paths, so a box in TRENDING_BULL printed only "STRATEGY: NO TRADE"
        with no way to tell whether the structure/df_1m plumbing was missing, no
        unfilled FVG existed in the trend direction, or the wick simply did not
        reach the gap. Observed on AMZN 2026-07-30: a full session of
        TRENDING_BULL (100% conviction), zero trades, zero explanation. Each
        branch now logs its inputs -- including gap bounds, the wick, and
        missed_by, so "it declined correctly" and "it is broken" are
        distinguishable at a glance. No behaviour change; observability only.
        v1.3.3 extends this to every decline that can refuse a QUALIFYING
        setup: the bare `except Exception` around the df_1m tag read (which
        returned None on EVERY tick if the frame's columns were not what was
        expected -- silent, and a prime suspect for AMZN), plus the conviction
        floor, the 5m momentum vote, and the 5m direction agreement.
        Regime-mismatch gates are deliberately left silent -- they fire every
        tick and would drown the log.
        (Third instance of this pattern: butterfly gates at DEBUG, ORB's
        "1 named level(s)", now continuation. A gate that cannot say why it
        declined cannot be diagnosed.)

v1.4 — 2026-07-30 — STRIKE SELECTION. THE STRATEGY HAD NONE. generate_signal
        built an OptionsSignal with no strike and no premium, so is_valid()
        (strike > 0 and entry_premium > 0) rejected it every single tick and
        main logged only "Invalid signal from ContinuationStrategy". Trend
        Continuation has NEVER taken a trade. v1.1's defect-W note said both
        paths "dead-ended before ever reaching strike selection" -- the gates
        were fixed, the strike selection they were supposed to reach was never
        written. Diagnosed on AMZN 2026-07-30: TRENDING_BULL 100%, FVG tagged,
        HANDOFF fired, conv=1.00, signal regenerated every 15s all session,
        zero fills.
        The strike now sits a FRACTION OF THE EXPECTED MOVE out in the trend
        direction, the fraction being a confluence of ADX (mechanical travel)
        and regime conviction (the engine's agreement). Disagreement between
        them pulls the strike back toward the money; only mutual agreement
        pushes it out. EM is the ATM straddle -- the same basis the condor's
        0.80xEM floor uses.
        `trend_strike_plan()` is module-level ON PURPOSE so trade_readiness can
        call it while a trade is merely STAGING -- awareness of what the chain
        offers now and what it will offer if conviction reaches the fire bar,
        rather than looking the chain up at the moment of the trigger.
        Bounds fitted from the fleet archive; all OT_CONT_* env-overridable.
"""
# v-runaway-fix (2026-07-24) — accepts runaway handoff_direction so it can enter on a flipped-off-trending label; conviction floor steps aside when the runaway (not the label) is the directional evidence.


from __future__ import annotations

import os
import logging
from typing import Optional

from analysis.regime_classifier import RegimeState, Regime
from analysis.volatility_engine import VolatilityState
from analysis.trend_engine import TrendState
from strategy.base_strategy import BaseOptionsStrategy, OptionsSignal

logger = logging.getLogger(__name__)

# ── Tunables (env-overridable at wire-in time; conservative defaults) ─────────
CONTINUATION_CONV_FLOOR      = 0.45   # min regime conviction to consider the trade
# v-fvg-pullback (2026-07-28): pullback trigger is now a 1-min wick TAGGING the
# nearest unfilled 5-min FVG (edge-tag, >= 1 cent penetration). The old BB-midline
# trigger (CONTINUATION_MIDLINE_ATR / _MAX_PULLBACK_R) was removed — too
# conservative, a strong trend outruns the midline so it never presented.
CONTINUATION_FVG_TAG_MIN     = 0.01   # cents the 1m wick must penetrate the FVG edge to "tag" it
# v1.2 (2026-07-22): sourced from config (env OT_CONT_STOP_PCT), tightened
# 0.40 -> 0.25. Regime-flip remains the PRIMARY exit; this is the backstop.
from config import CONTINUATION_STOP_LOSS_PCT   # 0.25 default
from config import CONT_BREAKOUT_DIRECTION, CONT_BREAKOUT_MIN_ADX  # CNT.1
from config import CONT_HANDOFF_BLOCK_COMPRESSION                  # CNT.3
from config import CONTINUATION_REQUIRE_CONFIRM                    # v1.5
from config import CONT_CONFIRM_TOL_ATR                            # v1.6
CONTINUATION_TP_PCT          = 1.0    # nominal; runner is exhaustion-trailed, not TP-capped
CONTINUATION_HANDOFF_CONV_RELAX = 0.10  # handoff path lowers the conviction floor by this



# ── EM-anchored, confluence-scaled strike selection (v1.4) ───────────────────
# Shared by the FIRING path (generate_signal) and the AWARENESS path
# (trade_readiness._staged_pick), so the chain is inspected while the trade is
# still queuing rather than at the moment of the trigger.
#
# The strike sits a FRACTION OF THE EXPECTED MOVE out in the trend direction.
# The fraction is a confluence of two independent reads of trend strength:
#   ADX        — mechanical: how hard is price actually travelling
#   conviction — the confluence engine's agreement that this is a real trend
# They can disagree, and the disagreement is informative: a high-ADX/low-conv
# tape is a chop-driven spike, high-conv/low-ADX is structure without thrust.
# Either pulls the strike BACK toward the money. Only when both agree does the
# strike go far out. Same rising-sea-level logic, applied to construction.
#
# Bounds fitted from the fleet archive (2026-07-30, n=36 ADX / n=32 conviction):
#   ADX  p25=24.7  p50=35.5  p75=47.3   (directional-only p25=35.4 p75=49.0)
#   CONV p25=0.396 p50=0.445 p75=0.528 p90=0.587 max=0.831
# ALL PRIOR — tune from continuation's own entries once it starts logging them.
CONT_ADX_LO   = float(os.environ.get("OT_CONT_ADX_LO",   "25.0"))
CONT_ADX_HI   = float(os.environ.get("OT_CONT_ADX_HI",   "50.0"))
CONT_CONV_LO  = float(os.environ.get("OT_CONT_CONV_LO",  "0.40"))
CONT_CONV_HI  = float(os.environ.get("OT_CONT_CONV_HI",  "0.60"))
CONT_W_ADX    = float(os.environ.get("OT_CONT_W_ADX",    "0.6"))
CONT_W_CONV   = float(os.environ.get("OT_CONT_W_CONV",   "0.4"))
CONT_EM_FRAC_MIN = float(os.environ.get("OT_CONT_EM_FRAC_MIN", "0.25"))
CONT_EM_FRAC_MAX = float(os.environ.get("OT_CONT_EM_FRAC_MAX", "0.75"))
CONT_MIN_MARK    = float(os.environ.get("OT_CONT_MIN_MARK", "0.10"))


def _ramp(x, lo, hi):
    if hi <= lo:
        return 1.0 if x >= hi else 0.0
    return min(max((x - lo) / (hi - lo), 0.0), 1.0)


def expected_move_from_straddle(chain, underlying):
    """ATM call mark + ATM put mark — the market's own price for the day's range.
    Same basis the condor uses. Returns 0.0 if unavailable; never raises."""
    try:
        calls = [c for c in getattr(chain, "calls", []) or [] if c.mark > 0]
        puts  = [c for c in getattr(chain, "puts",  []) or [] if c.mark > 0]
        if not calls or not puts or underlying <= 0:
            return 0.0
        atm_c = min(calls, key=lambda c: abs(c.strike - underlying))
        atm_p = min(puts,  key=lambda c: abs(c.strike - underlying))
        em = float(atm_c.mark) + float(atm_p.mark)
        return em if em > 0 else 0.0
    except Exception:
        return 0.0


def trend_strike_plan(chain, direction, current_price, adx, conviction):
    """Return a dict describing the strike this trade WOULD take right now.

    Callable while the trade is merely staging (awareness) or at the moment it
    fires. Reports chain availability and liquidity either way, so a setup that
    is about to arm can be checked against a chain that can actually fill it.

    Returns {'ok': bool, 'reason': str, 'contract': OptionContract|None, ...}.
    Never raises.
    """
    out = {"ok": False, "reason": "", "contract": None, "em": 0.0,
           "strength": 0.0, "em_frac": 0.0, "target_price": 0.0,
           "adx_val": 0.0, "conv_val": 0.0, "n_liquid": 0}
    try:
        em = expected_move_from_straddle(chain, current_price)
        out["em"] = em
        if em <= 0:
            out["reason"] = "no expected move (chain has no priced ATM straddle)"
            return out

        adx_val  = _ramp(float(adx or 0.0), CONT_ADX_LO, CONT_ADX_HI)
        conv_val = _ramp(float(conviction or 0.0), CONT_CONV_LO, CONT_CONV_HI)
        strength = CONT_W_ADX * adx_val + CONT_W_CONV * conv_val
        em_frac  = CONT_EM_FRAC_MIN + (CONT_EM_FRAC_MAX - CONT_EM_FRAC_MIN) * strength
        out.update(adx_val=adx_val, conv_val=conv_val,
                   strength=strength, em_frac=em_frac)

        offset = em * em_frac
        target = current_price + offset if direction == "long" else current_price - offset
        out["target_price"] = target

        pool = getattr(chain, "calls", []) if direction == "long" else getattr(chain, "puts", [])
        liquid = [c for c in (pool or []) if c.mark >= CONT_MIN_MARK]
        out["n_liquid"] = len(liquid)
        if not liquid:
            out["reason"] = f"no liquid {'call' if direction == 'long' else 'put'} (mark >= {CONT_MIN_MARK})"
            return out

        best = min(liquid, key=lambda c: abs(c.strike - target))
        out["contract"] = best
        out["ok"] = True
        out["reason"] = "ok"
        return out
    except Exception as _e:
        out["reason"] = f"{type(_e).__name__}: {_e}"
        return out


class ContinuationStrategy(BaseOptionsStrategy):
    """Trend-continuation entry on a pullback: 1-min wick tagging a 5-min FVG."""

    def name(self) -> str:
        return "ContinuationStrategy"

    def generate_signal(self,
                        *,
                        regime: RegimeState,
                        vol_state: VolatilityState,
                        trend: TrendState,
                        chain,
                        current_price: float,
                        is_handoff: bool = False,
                        handoff_direction: str = "",
                        structure=None,
                        df_1m=None,
                        macro=None) -> Optional[OptionsSignal]:
        """
        Return an OptionsSignal if a trend-continuation pullback entry sets up,
        else None. `is_handoff=True` is the looser ORB-runaway path.
        """
        # ── 1. GATE: must be a trending regime ──────────────────────────────
        rgm = regime.primary_regime
        is_breakout_dir = False          # CNT.1 — set by the BREAKOUT branch below
        if rgm == Regime.TRENDING_BULL:
            direction, option_side = "long", "call"
        elif rgm == Regime.TRENDING_BEAR:
            direction, option_side = "short", "put"
        elif (CONT_BREAKOUT_DIRECTION
              and rgm == Regime.BREAKOUT_VOLATILE
              and getattr(trend, "overall_direction", "NEUTRAL") in ("BULLISH", "BEARISH")
              and float(getattr(trend, "primary_adx", 0.0) or 0.0) >= CONT_BREAKOUT_MIN_ADX):
            # CNT.1 — BREAKOUT_VOLATILE asserts volatility EXPANSION and says
            # nothing about direction, which is the ONLY reason this trade was
            # barred here; it was never a judgement that breakout tape is poor
            # continuation tape. The trend engine has the missing half, so take
            # it from there — the same move the runaway handoff already makes,
            # sourced from the vote instead of from the ORB.
            # ADX is the quality bar because `_label_trending` is False under
            # this label, so the CONTINUATION_CONV_FLOOR check below is skipped
            # and `regime.conviction` here would be BREAKOUT's, not the trend's.
            _bd = getattr(trend, "overall_direction", "NEUTRAL")
            direction   = "long" if _bd == "BULLISH" else "short"
            option_side = "call" if direction == "long" else "put"
            is_breakout_dir = True
        elif (is_handoff and handoff_direction in ("long", "short")
              and not (CONT_HANDOFF_BLOCK_COMPRESSION
                       and rgm == Regime.COMPRESSION)):
            # CNT.3 — THE HANDOFF DOES NOT FIRE UNDER COMPRESSION.
            # COMPRESSION/Continuation is 39 trades, 28% WR, −$454, and
            # COMPRESSION is the WORST never-favourable cell in the book at 80%
            # (LIFT 1.98, n=45). Continuation cannot enter on a compression
            # LABEL — the branches above require TRENDING or BREAKOUT — so all
            # 39 of those are RUNAWAY HANDOFFS, which ignore the label by
            # design.
            # THE MECHANISM IS A CONTRADICTION: a runaway asserts EXPANSION
            # while the label asserts COILING. The handoff's licence to ignore
            # the label is exactly what makes it valuable after a real runaway;
            # this is the one place it clearly costs.
            # OT_CONT_HANDOFF_IN_COMPRESSION=1 restores the old behaviour.
            # v-runaway-fix: a runaway ORB proved directional force even if the
            # regime LABEL has since flipped (commonly to SWEEP_REVERSAL/BREAKOUT).
            # Trust the runaway's direction for the handoff entry. Non-handoff
            # (standalone) continuation still requires a trending label.
            direction   = handoff_direction
            option_side = "call" if direction == "long" else "put"
        else:
            return None  # not trending and no runaway handoff → trade does not exist

        conv_floor = CONTINUATION_CONV_FLOOR
        if is_handoff:
            conv_floor -= CONTINUATION_HANDOFF_CONV_RELAX  # runaway vouched for direction
        # v-runaway-fix: when the handoff is driving direction because the label
        # FLIPPED off trending (rgm not TRENDING_*), regime.conviction is the
        # conviction of the NEW label (e.g. sweep), not the trend — applying it
        # would wrongly kill the handoff. The runaway IS the directional evidence;
        # skip the floor in that specific case. A still-trending handoff keeps it.
        _label_trending = rgm in (Regime.TRENDING_BULL, Regime.TRENDING_BEAR)
        if _label_trending and regime.conviction < conv_floor:
            logger.info(f"[continuation] declined: conviction={regime.conviction:.3f} < floor={conv_floor:.3f}")
            return None

        # ── 2. PULLBACK = 1-min WICK TAGS the nearest unfilled 5-min FVG ───────
        # v-fvg-pullback 2026-07-28: the BB-midline trigger was too conservative
        # — a strong trend outruns the midline and it NEVER presents (continuation
        # sat out the SPX 2026-07-28 rip for exactly this). FVGs are where price
        # ACTUALLY returns in a trend (the imbalance fills), so the pullback is a
        # 1-min wick TAGGING (>= 1 cent into) the nearest unfilled 5-min FVG in
        # the trend direction. Edge-tag is preferred: price often reverses at the
        # proximal edge without filling deep. Midline logic REMOVED entirely.
        atr = getattr(vol_state, "atr_current", 0.0)
        if atr <= 0 or df_1m is None or structure is None:
            logger.info(
                f"[continuation] no eval: atr={atr:.2f} "
                f"df_1m={'ok' if df_1m is not None else 'MISSING'} "
                f"structure={'ok' if structure is not None else 'MISSING'}")
            return None

        fvgs = [g for g in getattr(structure, "fvgs", []) if not getattr(g, "filled", False)]
        # direction filter: a long pulls back DOWN into a bullish gap below price;
        # a short pulls back UP into a bearish gap above price.
        want = "bullish" if direction == "long" else "bearish"
        cands = []
        for g in fvgs:
            if getattr(g, "direction", "") != want:
                continue
            if direction == "long"  and g.top < current_price:   # gap sits below
                cands.append(g)
            elif direction == "short" and g.bottom > current_price:  # gap sits above
                cands.append(g)
        if not cands:
            _all = len(getattr(structure, "fvgs", []) or [])
            _unf = len(fvgs)
            logger.info(
                f"[continuation] no FVG in favor: dir={direction} want={want} "
                f"px={current_price:.2f} fvgs_total={_all} unfilled={_unf} "
                f"(need an unfilled {want} gap "
                f"{'below' if direction == 'long' else 'above'} price)")
            return None
        # nearest unfilled gap in favor: for a long, the highest such gap top;
        # for a short, the lowest such gap bottom (the one price is closest to).
        gap = (max(cands, key=lambda g: g.top) if direction == "long"
               else min(cands, key=lambda g: g.bottom))

        # TAG test: the most recent 1-min candle must penetrate the gap's proximal
        # edge by >= TAG_MIN_PENETRATION (1 cent). Long: 1m low pokes at/under the
        # gap TOP. Short: 1m high pokes at/over the gap BOTTOM.
        try:
            last_low  = float(df_1m["low"].iloc[-1])
            last_high = float(df_1m["high"].iloc[-1])
        except Exception as _e:
            logger.warning(
                f"[continuation] FVG tag test FAILED reading df_1m: {type(_e).__name__}: {_e} "
                f"| cols={list(getattr(df_1m, 'columns', []))} "
                f"rows={len(df_1m) if df_1m is not None else 'None'} "
                f"— this returns None EVERY tick until fixed")
            return None
        if direction == "long":
            tagged = last_low <= (gap.top - CONTINUATION_FVG_TAG_MIN)
        else:
            tagged = last_high >= (gap.bottom + CONTINUATION_FVG_TAG_MIN)

        # ── v1.5 — 1-BAR CONFIRMATION ────────────────────────────────────────
        # The tagging bar is the SETUP. It is not the trigger. Require the NEXT
        # bar to close BEYOND that bar's extreme in the trend direction:
        #   long : tag bar wicks into the gap, next bar CLOSES ABOVE its HIGH
        #   short: mirrors on the low
        # Bars are the last two CLOSED ones (-3 tag, -2 confirm); the forming
        # bar decides nothing, because it can still change.
        if tagged and CONTINUATION_REQUIRE_CONFIRM:
            try:
                tag_bar = df_1m.iloc[-3]
                cfm_bar = df_1m.iloc[-2]
                # v1.6 — TOLERANCE IN ATR UNITS. v1.5's strict comparison was
                # rejecting TIES: the first live session shows misses of 3-9
                # cents (QQQ 0.011%, PLTR 0.023%) — the bar closed AT the
                # extreme and failed on a rounding-level margin. Same principle
                # as the BOS distance floor: express the threshold in the
                # symbol's own noise units, never in raw price, because a fixed
                # cent value cannot serve both QQQ and GLD.
                _atr = float(getattr(vol_state, "atr_current", 0.0) or 0.0)
                _tol = max(0.0, CONT_CONFIRM_TOL_ATR) * _atr
                if direction == "long":
                    _tag_ok   = float(tag_bar["low"]) <= (gap.top - CONTINUATION_FVG_TAG_MIN)
                    _need     = float(tag_bar["high"]) - _tol
                    confirmed = _tag_ok and float(cfm_bar["close"]) > _need
                    _got      = float(cfm_bar["close"])
                else:
                    _tag_ok   = float(tag_bar["high"]) >= (gap.bottom + CONTINUATION_FVG_TAG_MIN)
                    _need     = float(tag_bar["low"]) + _tol
                    confirmed = _tag_ok and float(cfm_bar["close"]) < _need
                    _got      = float(cfm_bar["close"])
            except (IndexError, KeyError, TypeError, ValueError):
                # REFUSE. Falling through here would restore the unconfirmed
                # entry invisibly, and only on thin tape — an absent
                # confirmation is not a passed one.
                logger.info("[continuation] confirmation UNDECIDABLE "
                            "(insufficient 1m bars) — no entry")
                return None
            if not confirmed:
                # v1.6 — log the MISS and the TOLERANCE. The first live session's
                # value was that `need`/`got` could be read against each other;
                # printing the gap directly is what turned "the gate is firing"
                # into "the gate is failing by 4 cents". Keep it that way.
                logger.info(
                    f"[continuation] tagged but NOT CONFIRMED: need close "
                    f"{'>' if direction == 'long' else '<'} {_need:.2f}, "
                    f"got {_got:.2f} (miss {abs(_got - _need):.2f}, "
                    f"tol {_tol:.2f}) — waiting for the resumption bar")
                return None

        if not tagged:
            _edge = gap.top if direction == "long" else gap.bottom
            _wick = last_low if direction == "long" else last_high
            _miss = abs(_wick - _edge)
            logger.info(
                f"[continuation] FVG not tagged: gap={gap.bottom:.2f}-{gap.top:.2f} "
                f"edge={_edge:.2f} wick={_wick:.2f} missed_by={_miss:.2f} "
                f"(need {'low<=' if direction == 'long' else 'high>='}"
                f"{_edge - CONTINUATION_FVG_TAG_MIN if direction == 'long' else _edge + CONTINUATION_FVG_TAG_MIN:.2f})")
            return None

        # ── 3. ENTRY (LOW BAR): momentum flipping back toward the trend ─────
        # Resumption is intentionally easy — protection lives in the exit. We
        # require the trend engine's momentum to be re-asserting in the trend
        # direction (not still decelerating against us).
        # v1.1: primary_momentum (5m vote, surfaced by trend_engine v3.2).
        # NOT `trend.momentum` — that attribute does not exist on TrendState
        # and getattr silently returned "", hard-blocking this trade forever.
        momentum = getattr(trend, "primary_momentum", "") or ""
        if not momentum:
            logger.info("[continuation] declined: no 5m momentum vote this tick")
            return None          # no 5m vote this tick — unknown is not a green light
        # Real vocabulary: ACCELERATING / DECELERATING / FLAT.
        #   standalone -> must be ACCELERATING (self-sourced, so demand thrust)
        #   handoff    -> ACCELERATING or FLAT (the runaway ORB already proved
        #                 directional force; we only need "not decelerating
        #                 against us"). FLAT is what the old code meant by the
        #                 phantom value "STEADY".
        if is_handoff:
            if momentum not in ("ACCELERATING", "FLAT"):
                return None
        elif momentum != "ACCELERATING":
            return None

        # direction agreement between regime and trend engine (cheap sanity)
        tdir = (getattr(trend, "overall_direction", "") or "").upper()
        if direction == "long"  and tdir not in ("BULLISH", "BULL", "UP"):
            logger.info(f"[continuation] declined: dir=long but 5m trend={tdir}")
            return None
        if direction == "short" and tdir not in ("BEARISH", "BEAR", "DOWN"):
            logger.info(f"[continuation] declined: dir=short but 5m trend={tdir}")
            return None

        # ── 4. Build the signal (debit directional) ────────────────────────
        # Stop reference: just past the pullback extreme (approximated as the
        # midline minus/plus a small ATR buffer). Governing exits are regime-flip
        # + the 40% premium floor; this underlying_stop is structural context.
        if direction == "long":
            # v-fvg-pullback fix: anchor the stop to the FVG, not the deleted
            # midline. Long entered by tagging gap.top from above; if price closes
            # THROUGH the gap (below gap.bottom) the pullback became a breakdown.
            underlying_stop = gap.bottom - 0.5 * atr
        else:
            # short entered by tagging gap.bottom from below; through gap.top = dead
            underlying_stop = gap.top + 0.5 * atr

        signal = OptionsSignal(
            # ⚠️ STR.1 (2026-08-18) — vix_at_entry WAS 58% EMPTY ACROSS THE BOOK.
            # ORB, butterfly and sweep set `vix_at_signal`; continuation and
            # iron_condor — the two HIGHEST-VOLUME strategies — never did, so
            # `trades.vix_at_entry` defaulted to 0.0 on most rows. The
            # separation probe read that as a real value of zero and reported
            # "58% ties, median 0.000 in both arms": **a collection gap wearing
            # the costume of a measured null.**
            # `macro` is optional on this signature, so a None guard rather than
            # an attribute access — a missing macro must not cost a signal.
            vix_at_signal    = (getattr(macro, "vix", 0.0) or 0.0)
                               if macro is not None else 0.0,
            strategy_name    = self.name(),
            setup_type       = "trend_continuation" + ("_handoff" if is_handoff
                                                       else "_breakout" if is_breakout_dir
                                                       else "_standalone"),
            direction        = direction,
            option_side      = option_side,
            underlying_entry = current_price,
            underlying_stop  = underlying_stop,
            regime           = rgm if isinstance(rgm, str) else str(rgm),
            stop_loss_pct    = CONTINUATION_STOP_LOSS_PCT,
            tp_pct           = CONTINUATION_TP_PCT,
        )

        # ── STRIKE SELECTION (v1.4) — the step that never existed ─────────────
        # Without this the signal shipped with strike=0 / entry_premium=0 and
        # main's is_valid() rejected it EVERY tick ("Invalid signal from
        # ContinuationStrategy"), so the strategy re-signalled forever and never
        # traded. Observed on AMZN 2026-07-30: valid setup, conv=1.00, signal
        # regenerated every 15s for the whole session, zero fills.
        _plan = trend_strike_plan(chain, direction, current_price,
                                  getattr(regime, "adx", 0.0), regime.conviction)
        if not _plan["ok"]:
            logger.info(
                f"[continuation] no strike: {_plan['reason']} "
                f"(em={_plan['em']:.2f} liquid={_plan['n_liquid']})")
            return None
        _c = _plan["contract"]
        # ── GRD.2 — POPULATE `underlying_target` ─────────────────────────────
        # `trend_strike_plan` has ALWAYS computed this (EM fraction scaled by
        # ADX + conviction) and USED IT to pick the strike — then discarded it.
        # So the bot was never target-free; it was TARGET-BLIND, and three
        # consumers sat inert on 77% of fleet volume:
        #   · `_rrr()` returned None on every continuation signal, which is why
        #     `rrr` appears in ORB's scorer table and nowhere else — and why the
        #     MIN_RRR floor was structurally inert on most of the book.
        #   · `_pools_in_path` scans `entry < p < target`; with target 0.0 a
        #     LONG's window is empty BY CONSTRUCTION, so `liquidity_clear` has
        #     been a structural constant at 1.000, not a measured one.
        #   · `exit_engine._update_post_target_trail` is guarded on
        #     `underlying_target > 0`, so continuation always fell back to the
        #     blunt 85% trail instead of the FVG floor past 100% TP.
        # ⚠️ THIS IS NOT A TAKE-PROFIT AND NOTHING CONSUMES IT AS ONE. The
        # operator's no-target design stands: "the multiple is a want, not a
        # need... use stops creatively so nothing stops them running when
        # they're correct." This is the R denominator and the trail's reference,
        # not an exit trigger.
        signal.underlying_target = float(_plan["target_price"] or 0.0)
        signal.strike        = _c.strike
        signal.entry_premium = _c.mark
        signal.option_symbol = getattr(_c, "symbol", "") or getattr(_c, "option_symbol", "")
        signal.contract      = _c
        logger.info(
            f"[continuation] strike {_c.option_type if hasattr(_c,'option_type') else option_side} "
            f"{_c.strike} mark=${_c.mark:.2f} delta={getattr(_c,'delta',0.0):.3f} | "
            f"em=${_plan['em']:.2f} frac={_plan['em_frac']:.2f} "
            f"strength={_plan['strength']:.2f} "
            f"(adx={_plan['adx_val']:.2f} conv={_plan['conv_val']:.2f}) "
            f"target=${_plan['target_price']:.2f} liquid={_plan['n_liquid']}")

        # conviction: inherit regime conviction (trending is the whole thesis),
        # small bump for a clean midline tag + momentum re-assertion.
        signal.conviction = regime.conviction
        signal.adx_at_signal = regime.adx
        signal.flat_angle_deg = getattr(regime, 'flat_angle_deg', 0.0) or 0.0
        self._add_confluence(signal, f"Trending regime ({signal.regime}) conv={regime.conviction:.2f}")
        self._add_confluence(signal, f"1m wick tagged 5m FVG {gap.bottom:.2f}-{gap.top:.2f}, price {current_price:.2f}")
        self._add_confluence(signal, f"Momentum {momentum} (resumption)")
        if is_handoff:
            self._add_confluence(signal, "ORB-runaway handoff (directional force pre-proven)")

        logger.info(
            f"[continuation] {direction} {option_side} @ {current_price:.2f} "
            f"fvg={gap.bottom:.2f}-{gap.top:.2f} atr={atr:.2f} mom={momentum} "
            f"conv={regime.conviction:.2f} {'HANDOFF' if is_handoff else 'STANDALONE'}"
        )
        return signal
