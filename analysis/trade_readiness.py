# analysis/trade_readiness.py — options_trader_v3 — v1.9
# v1.9 — 2026-08-13 — SWP.3: the sweep APPROACH corroborator's sign is
#         refuted (LIQ.1 + ANT.1 + ANT.2, three independent lines), weight
#         -> 0.0 and the remaining three renormalised 0.30/0.20/0.25 ->
#         0.400/0.267/0.333 so the ABSOLUTE stage/arm bars keep their meaning.
#         Not inverted: `1 - appr_val` would assert 'far from a level = ready',
#         nonsense for a sweep. Sign wrong, form unknown — so the term is
#         removed from the composite and KEPT in the journal.
#         LOG-ONLY: main.py:2045 discards assess_all()'s return, so no trade
#         changes today. It stops every FUTURE fit against the readiness
#         composite inheriting a term measured to point backwards.
# v1.8 — 2026-08-11 — BFLY.1: THE BUTTERFLY TRACK WAS SCORING A DIFFERENT TRADE.
#         The strategy is a GEX-PIN play — Gate 5 hard-refuses unless
#         `gex_environment == "PINNING"`, the tent is centred on `pin_strike`
#         (not ATM), and the thesis is to enter CHEAP while price is still a walk
#         away and let it migrate into the tent. The readiness track graded
#         `coil` (the COMPRESSION label) as a HARD VETO plus a boolean squeeze
#         and band width — a COMPRESSION play. **Not one of the five gates that
#         actually block the strategy was in it**: no pin, no pin distance, no
#         GEX environment, no entry window, no one-per-session.
#         MEASURED 2026-08-10: **would_fire=2132 against ONE trade**, R p50 0.995
#         / p90 1.000. The thing it measured was ready all day; the thing that
#         has to be true almost never was. A label switch wearing the name of a
#         pin play — and it renders as a perfectly healthy 1.0.
#         NOW: `pin_val` (distance to the pin in EXPECTED-MOVE units — the
#         operator's "still a walk away", made numeric, and the same unit the
#         strategy's own proximity gate uses), `firm_val` (|net_gex|, so a 2.3M
#         pin outranks a 0.1M one — the strategy's PINNING flag is binary and
#         cannot), `win_val` (ramps UP toward the 12:00 window rather than
#         switching on at it, because readiness exists to ARM AHEAD, and goes to
#         ZERO after 14:00 when the strategy cannot fire at all), and `gex_val`
#         as a SOFT-NECESSARY (PINNING 1.0 / NEUTRAL 0.35 / TRENDING 0.10) so a
#         non-pinning tape scores a fraction rather than nothing — that is the
#         difference between "not yet" and "never", which a boolean cannot say.
#         `coil` survives DEMOTED to a corroborator: a coiling tape is supporting
#         evidence for a pin holding, it was never the trade.
#         OBSERVED BEHAVIOUR: 0.115 far/NEUTRAL/weak → 0.342 mid/PINNING/weak →
#         0.930 near/PINNING/firm; 0.093 on a TRENDING tape with identical pin
#         geometry; 0.155 warming at 10:45; 0.000 once the window shuts.
#         ⚠️ LOG-ONLY. Nothing gates on readiness — this changes what the score
#         SAYS, not what fires. Promotion was already solved by CNT.6 removing
#         continuation from the premium regimes.
#         ⚠️ PIN DISTANCE FALLS BACK TO ATR when no chain is on ctx, because
#         expected move needs one and a chainless tick must not silently zero
#         the term carrying the whole thesis. `pin_dist_unit` records WHICH unit
#         was used — em and atr2 are different scales and must NEVER be pooled
#         when fitting the bounds.
# v1.7 — 2026-08-10 — SWEEP APPROACH, and the removal of a veto that had gone
#         DEAD UNDER OUR OWN FIX. `_sweep` carried `hard_vetoes=[is_sweep]`,
#         requiring the committed label to BE SWEEP_REVERSAL. RGM.3 (baked
#         2026-08-08) took SWEEP out of the argmax, so that label is never
#         emitted and this track has scored a PERMANENT ZERO since — the same
#         category error as the dispatch gate, one layer down, created two days
#         earlier by the fix that was meant to free sweep. Readiness ARMS a
#         track BEFORE its event; gating it on the event's own label made arming
#         impossible by construction, and any new factor would have multiplied
#         into a hard zero and changed nothing.
#         NEW `appr_val` — conviction rises as price nears a named pool, scaled
#         by how well that level has held. Operator's spec: distance as PRICE
#         DELTA NORMALISED BY ATR, so 0.20 is imminent on GLD and noise on NVDA.
#         Proximity and level quality MULTIPLY: close to an untested level is
#         not the setup, and neither is a well-tested level far away.
#         ⚠️ BOUNDS ARE FITTED, NOT GUESSED. Shadow observer (BACKLOG v4.05):
#         only 14.0% of observations sit within 0.5 ATR of a named level, MEDIAN
#         2.32 ATR. My first draft used 0.15/1.20, which put the MEDIAN TICK at
#         zero proximity and would have left the factor dead across roughly
#         three-quarters of the session. I had the direction of that error
#         backwards until I read a distribution that was already on file.
#         ⚠️ LONDON IS A BONUS (1.15), NOT A MULTIPLIER. Named levels are 61.3%
#         London High/Low, and there is a mechanism — London runs to 16:00 UTC,
#         so it is the only named level still FORMING during RTH, which is also
#         why it accrues few touches and would be UNDER-scored by touch_count
#         alone. But 61.3% is a frequency of PROXIMITY, not of profitability: a
#         level you are always near because it brackets the range is not a
#         magnetic one. Weighted modestly so Friday's SHD.2 re-pull can back it
#         out with a knob rather than a redesign.
#         `appr_name` now lands on every readiness record, so "which levels get
#         swept" becomes answerable from data instead of from recollection.
# v1.6 — 2026-08-08 — `dir` ON EVERY TRACK (log-only, no behaviour change).
#         Until now exactly ONE track journaled a direction: _trend_credit_spread
#         emitted `factors.dir` and the other five emitted nothing. That was
#         invisible until the VWAP orientation ledger ran against it and 30,565
#         records landed in a single "undecidable" bucket whose LABEL blamed the
#         cash-index case — five of six strategies were being discarded for a
#         missing field, under a caption that said something else entirely.
#         Each track now stamps `dir` from the source that actually knows:
#         continuation from the trending label (identical to `_staged_pick`'s
#         derivation, so the two can never disagree); sweep from the LIVE
#         `liq_map.recent_sweep.kind`, which no offline tool could ever recover;
#         condor sides from EXPOSURE — a call credit is SHORT, the inverse of
#         the option-buyer reading, and `side` is kept alongside because the two
#         answer different questions; butterfly explicitly "neutral".
#         "" means NO INTENDED SIDE THIS TICK and is an honest absence — the
#         whole point is that a reader can now tell "sideless by design" from
#         "field never existed", which is the distinction whose absence cost the
#         ledger five versions.
#         ⚠️ FORWARD-ONLY. This changes what gets WRITTEN, so it reaches only
#         sessions after the bake. Every already-banked session is still read by
#         `vwap_orientation_ledger` v1.4's derivation, which is why that
#         derivation is kept rather than replaced.
# v1.5 — 2026-08-05 — MARKET SNAPSHOT ON EVERY READINESS RECORD (backfilled into
#         this changelog on 2026-08-08 — it shipped without one, and the title
#         line carried no version at all while check_versions already pinned
#         "v1.5". Exactly the drift WORKING_AGREEMENT rule 5 exists to stop, and
#         it is recorded rather than quietly corrected). `_market_snapshot`
#         emits {vwap, price_vs_vwap, dist_pct} into `readiness.market` on every
#         record. volatility_engine had computed vwap and price_vs_vwap all
#         along and NOTHING PERSISTED THEM: a key scan of 11,138 records found
#         no VWAP-shaped field anywhere, which is why `vwap_orientation` had
#         never once run. `dist_pct` is signed and expressed as a percentage of
#         VWAP so it compares across a $30 symbol and a $900 one;
#         `price_vs_vwap` is carried rather than derived from its sign, because
#         the engine reports NONE on zero volume and a computed sign would
#         invent an orientation there.
# v1.4 — 2026-07-28 — ARM-ORIGIN EXTENSION (operator spec). The "move" is
#         defined to START when confluence ARMS: ReadinessState now stamps
#         (origin_price, origin_em, origin_ts) at every STAGING->ARMED
#         transition, RE-STAMPS on every re-arm (flicker/disarm then re-arm =
#         fresh origin), and clears on disarm. `_extension_from_arm` scores the
#         fraction of the arm-EM consumed since; a short-premium vertical is
#         "premium rich" at TR_EXT_FIRE_FRAC (0.80) of that EM. Wired as the
#         shared W_VERT_EXT corroborator into BOTH the condor sides (range
#         adapter, per-side up/down) and the trend credit spread (trend adapter)
#         — the two are the same short-premium family, split only by regime.
#         `_expected_move_now` derives EM from the ATM straddle on ctx["chain"].
#         Bounds OT_TR_EXT_* / OT_TR_W_VERT_* overridable. 0.80 is a PRIOR — the
#         point of shipping live+logged is to discover the right number.
# v1.3 — 2026-07-28 — TREND CREDIT SPREAD readiness track (TC.4, LOG-ONLY). New
#         `_trend_credit_spread` track: readiness for a short-premium trend-
#         participation trade (PCS in TRENDING_BULL, CCS in TRENDING_BEAR) that
#         needs no pullback and no chase — sell a spread BEYOND the impulse
#         candle that ripped. Impulse = a 1-min candle whose range in rolling-SD
#         units clears the operator's aware/established/screaming ramp
#         (1.75/2.0/2.5 SD, OT_TR_TCS_* overridable, ALL PRIOR — calibrate from
#         the journal, never one day). The impulse candle does double duty:
#         magnitude (SD) feeds conviction; extreme (low/high) anchors the short
#         strike (committed flow won't fully retrace — durable floor/ceiling).
#         Corroborators: impulse, conviction, structural room to the floor,
#         momentum-live. Damper: parabolic over-extension (snapback risk). Hard
#         veto: trending label in the correct direction. Smoke-tested: impulse
#         ramp drives R aware->established->screaming; RANGING vetoes to 0;
#         5-ATR parabolic damps to 0. GATES NOTHING (freeze-safe). The FIRING
#         engine (vertical_spread_strategy.py) is a SEPARATE later file, gated
#         on digest-calibrated bounds + the L1 excavation — see ROADMAP TC.4.
# v1.2 — 2026-07-28 — ALL FACTOR BOUNDS ENV-OVERRIDABLE (OT_TR_*). v1.0/v1.1
#         env-ified only the STATE-MACHINE bars and left every FACTOR ramp as
#         a hardcoded literal — inconsistent with L1, where all 14 ramp bounds
#         are OT_RC_* overridable, and that property is exactly what let the
#         room_s refit be trialled on one box with instant rollback instead of
#         a fleet redeploy. First live day (2026-07-28) proved the cost: the
#         conviction ramp topped out at 0.65 while fleet L2 conviction ran
#         0.59-0.83, so conv_val pegged at 1.0 on roughly half the boxes and
#         ten symbols reported an identical r=0.65. Correcting that guess
#         should be an env flip, not a bake. Now: 13 factor bounds + 8
#         categorical momentum weights are OT_TR_*.
#         DEFAULTS DELIBERATELY UNCHANGED. The pegged bound is NOT re-guessed
#         here — every readiness row already journals the RAW conv/approach/
#         distance alongside the ramped value, so the digest (v1.1) fits the
#         bounds from the observed distribution the way room_s was fitted.
#         Guessing a second time is the error this whole workstream exists to
#         stop. Pegging does not corrupt the fit: the raw inputs are logged
#         un-ramped, and nothing gates on R.
# v1.1 — 2026-07-27 — STAGED PICKS (still LOG-ONLY). While a directional
#         strategy (continuation, sweep) is ARMED and a chain is on ctx, the
#         engine now computes the contract it WOULD select — through the SAME
#         selector the live entry uses (options_chain.select_sweep_strike) —
#         using a SMOOTHED conviction (wall-clock EMA, same half-life idiom as
#         slope) instead of the instantaneous spike, and journals it as
#         `readiness_staged_pick` (throttled to the heartbeat cadence + always
#         beside would_fire). When the real trigger later fires, the journal
#         holds staged-pick rows next to the trigger-tick pick, so the chain
#         archive can answer IN DOLLARS whether calm selection beats spike
#         selection — before staged picks ever touch an order. The PLTR strike
#         (0.62 spike -> 0.16 delta -> unreachable) is the failure class this
#         measures. Condor/butterfly staged ladders deferred (multi-leg).
# v1.0 — 2026-07-27 — NEW FILE. Trade-trigger READINESS engine (LOG-ONLY).
#
#   The L1 excavation (regime_confluence v1.3) made the REGIME scores honest
#   graded evidence. This module applies the same thinking one layer up, to the
#   TRADE TRIGGERS: each strategy's pre-trigger confluence becomes a graded
#   readiness R in [0,1] evaluated every ~15s tick, with a dt-aware SLOPE so
#   the system can tell whether a trade's confluence is RISING or FALLING, and
#   an arming state machine (DORMANT -> STAGING -> ARMED -> would_fire) that
#   anticipates when a trade will be ready to fire.
#
#   Operator's framing (2026-07-27): assessment of what the market is doing in
#   the context of where it IS right now, where it's BEEN, and where the
#   lowest-timeframe signals suggest it is HEADING.
#     - now:     instantaneous strategy-local geometry + L1-derived state
#     - been:    the L2 committed conviction (persistence lives in Layer 2)
#     - heading: EMA'd dR/dt on the 15-second tick cadence
#
#   The last gate is binary regardless — that is the nature of a trigger. This
#   module's job is to make that bit the LAST place information collapses, not
#   the first: everything upstream stays graded, journaled, and visible.
#
#   LOG-ONLY BY DESIGN (pitchfork weight-0 precedent): this engine gates
#   NOTHING and changes NO fire decision. It observes and journals. It runs
#   inside the frozen-baseline window precisely because it cannot move a label
#   or a trade; its journal rows are the calibration data for the bars that
#   will eventually gate. It does not validate the Layer-1 data — it gives
#   clues about what the Layer-1 data believes, per tick, per strategy.
#
#   LAYER BOUNDARY: this is L3/strategy-level. Referencing tradability context
#   is legal here. It reads L1/L2 OUTPUTS (regime label, conviction) and engine
#   states; it writes nothing back. L1 stays instantaneous and frozen.
#
#   TICK-VS-BAR RULE (July-20 audit): all temporal math is WALL-CLOCK dt-aware.
#   No per-evaluate counters anywhere in this file — the 15s loop can call
#   assess() at any cadence, including the 4x-duplicated-candle case that
#   inflated bars_since_break.
#
#   RESTART: state is in-memory and resets on restart. Acceptable for a
#   log-only observer — a restart shows up in the journal as a DORMANT reset,
#   which is itself useful evidence.
#
#   ORB IS EXEMPT (standing directive): the ORB is intentionally mechanical
#   and already has its own arming machine + retest_check journaling.

from __future__ import annotations

import os as _os
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
from utils.time_utils import now_et      # v1.8 — the butterfly entry window

log = logging.getLogger(__name__)

# ── Engine idiom: same grammar as the confluence scorer ───────────────────────
try:
    from analysis.regime_confluence import ramp, _combine, momentum_val
except Exception:                              # pragma: no cover — isolation
    def ramp(x, lo, hi):
        if hi <= lo:
            return 1.0 if x >= hi else 0.0
        return min(max((x - lo) / (hi - lo), 0.0), 1.0)

    def _combine(hard_vetoes, soft_necessary, corroborators):
        for v in hard_vetoes:
            if v <= 0.0:
                return 0.0
        prod = 1.0
        for s in soft_necessary:
            prod *= max(0.0, min(1.0, s))
        csum = sum(w * max(0.0, min(1.0, val)) for w, val in corroborators) \
            if corroborators else 1.0
        return max(0.0, min(1.0, prod * csum))

    def momentum_val(mom):
        return {"ACCELERATING": 1.0, "FLAT": 0.5, "DECELERATING": 0.0,
                "": 0.0}.get(mom, 0.0)


def _envf(name: str, default: float) -> float:
    try:
        return float(_os.environ.get("OT_TR_" + name, default))
    except (TypeError, ValueError):
        return default


# ── Knobs (ALL PRIOR — calibrate from the readiness journal, never one day) ──
# Bars are on R in [0,1]. Slope is in R-units PER MINUTE.
TR_STAGE_BAR        = _envf("STAGE_BAR", 0.35)   # R >= this -> STAGING
TR_ARM_BAR          = _envf("ARM_BAR", 0.55)     # R >= this AND slope > 0 -> ARMED
TR_FIRE_BAR         = _envf("FIRE_BAR", 0.70)    # R >= this AND slope > 0 -> would_fire (log event)
TR_DEARM_SLOPE      = _envf("DEARM_SLOPE", -0.15)  # ARMED + slope <= this -> de-arm (collapse)
TR_HYSTERESIS       = _envf("HYSTERESIS", 0.05)  # bars relax by this on the way DOWN
TR_SLOPE_HALFLIFE_S = _envf("SLOPE_HALFLIFE_S", 60.0)   # EMA half-life for dR/dt
TR_HEARTBEAT_S      = _envf("HEARTBEAT_S", 60.0)  # journal sample cadence while >= STAGING
TR_MAX_DT_S         = _envf("MAX_DT_S", 120.0)   # dt gaps beyond this reset the slope (stale)
TR_CONT_TARGET_DELTA = _envf("CONT_TARGET_DELTA", 0.45)  # continuation staged-pick delta (PRIOR)
TR_CONV_HALFLIFE_S   = _envf("CONV_HALFLIFE_S", 90.0)    # smoothed-conviction EMA half-life

# ── v1.2 FACTOR BOUNDS (all PRIOR, all OT_TR_* overridable) ──────────────────
# Shared conviction ramp — used by all four strategies. KNOWN MIS-FIT as of
# 2026-07-28: fleet L2 conviction observed 0.59-0.83, so HI=0.65 pegs. Refit
# from the digest's conv percentiles (p25->p95 convention), not by guess.
TR_CONV_LO          = _envf("CONV_LO", 0.25)
TR_CONV_HI          = _envf("CONV_HI", 0.65)
# Continuation: distance from the BB midline in ATR. Beyond HI the trend is
# still extended and the pullback has not arrived — 0 is correct there.
TR_PULL_ATR_LO      = _envf("PULL_ATR_LO", 0.35)
TR_PULL_ATR_HI      = _envf("PULL_ATR_HI", 1.05)
# Sweep freshness half-life, in bars.
TR_FRESH_HALFLIFE_B = _envf("FRESH_HALFLIFE_B", 3.0)
# Condor: approach fraction toward the band edge (the trigger's own graded
# input, kept graded here), and range room.
TR_APPROACH_LO      = _envf("APPROACH_LO", 0.30)
TR_APPROACH_HI      = _envf("APPROACH_HI", 0.90)
TR_ROOM_LO          = _envf("ROOM_LO", 0.17)
TR_ROOM_HI          = _envf("ROOM_HI", 1.00)
# Butterfly: BB-width narrowness, measured below this pivot across this span.
TR_NARROW_PIVOT     = _envf("NARROW_PIVOT", 0.20)
TR_NARROW_SPAN      = _envf("NARROW_SPAN", 0.15)
# Categorical momentum weights. Continuation reads momentum as RESUMPTION
# (accelerating = resuming now); sweep reads it as EXHAUSTION (decelerating =
# move spent). Empty string = no 5m vote and earns NOTHING in both, per the
# trend_engine v3.2 contract.
TR_CONT_MOM_ACC     = _envf("CONT_MOM_ACC", 1.0)
TR_CONT_MOM_FLAT    = _envf("CONT_MOM_FLAT", 0.6)
TR_CONT_MOM_DEC     = _envf("CONT_MOM_DEC", 0.3)
TR_SWEEP_MOM_DEC    = _envf("SWEEP_MOM_DEC", 1.0)
TR_SWEEP_MOM_FLAT   = _envf("SWEEP_MOM_FLAT", 0.5)
TR_SWEEP_MOM_ACC    = _envf("SWEEP_MOM_ACC", 0.0)

# Trend credit spread (PCS in a bull, CCS in a bear). Readiness for a SHORT-
# premium trend-participation trade: sell a spread BEYOND the impulse candle
# that ripped, so no pullback and no chasing are required. The impulse ramp is
# the operator's aware/established/screaming scale (2026-07-28): a 1-min candle
# whose range in ROLLING-SD units clears these bounds is a committed-flow
# footprint whose origin becomes a durable floor (PCS) / ceiling (CCS).
#   1.75 SD = AWARE  (impulse begins to count — ramp floor)
#   2.00 SD = ESTABLISHED (real committed move; corroborator contributing)
#   2.50 SD = SCREAMING (unmistakable thrust; impulse corroborator maxed)
# The ramp bounds ARE aware->screaming: LO=1.75 (contribution starts),
# HI=2.50 (maxes). ESTABLISHED (2.0) is where impulse+the other corroborators
# typically clear STAGE/ARM. All PRIOR — calibrate the SD bounds and the
# per-symbol frequency from the readiness journal, never one day.
TR_TCS_IMPULSE_SD_LO = _envf("TCS_IMPULSE_SD_LO", 1.75)
TR_TCS_IMPULSE_SD_HI = _envf("TCS_IMPULSE_SD_HI", 2.50)
TR_TCS_SD_LOOKBACK   = _envf("TCS_SD_LOOKBACK", 20.0)   # 1m bars for rolling SD of range
# Structural room: distance from spot DOWN to the impulse-candle floor (PCS) /
# UP to the ceiling (CCS), in ATR. More room beneath the short strike = safer.
TR_TCS_ROOM_ATR_LO   = _envf("TCS_ROOM_ATR_LO", 0.25)
TR_TCS_ROOM_ATR_HI   = _envf("TCS_ROOM_ATR_HI", 1.50)
# Extension DAMPER (soft-necessary): a credit spread wants trend, but a
# PARABOLIC over-extension invites the snapback that breaches the short strike.
# Past HI ATR from the midline the score is damped toward 0 (exhaustion risk).
TR_TCS_EXT_ATR_LO    = _envf("TCS_EXT_ATR_LO", 2.50)
TR_TCS_EXT_ATR_HI    = _envf("TCS_EXT_ATR_HI", 4.50)
# Momentum read: a trend credit spread wants the trend LIVE (accelerating/flat),
# NOT decelerating — deceleration is where the trend tires and reverses through
# the strike. (Opposite of sweep, which wants deceleration.)
TR_TCS_MOM_ACC       = _envf("TCS_MOM_ACC", 1.0)
TR_TCS_MOM_FLAT      = _envf("TCS_MOM_FLAT", 0.6)
TR_TCS_MOM_DEC       = _envf("TCS_MOM_DEC", 0.0)   # hard-ish: tiring trend earns nothing
# Corroborator weights (sum ~1.0). Impulse is the headline; conviction and room
# corroborate; momentum gates via its own low value when decelerating.
W_TCS_IMPULSE = _envf("W_TCS_IMPULSE", 0.40)
W_TCS_CONV    = _envf("W_TCS_CONV", 0.25)
W_TCS_ROOM    = _envf("W_TCS_ROOM", 0.20)
W_TCS_MOM     = _envf("W_TCS_MOM", 0.15)

# Extension-from-arm (v1.4, operator 2026-07-28). A short-premium vertical
# (trend credit spread OR condor side) fires only once price has consumed
# >= TR_EXT_FIRE_FRAC of the expected move that existed WHEN THE TRACK ARMED.
# 0.80 = "premium is rich here" (80% of the arm-EM spent -> selling the fat,
# unlikely tail). The ramp starts contributing at LO and maxes at HI so the
# corroborator is graded, not a cliff. ALL PRIOR — the whole point of shipping
# this live+logged is to discover whether 0.80 is the right number.
TR_EXT_FIRE_FRAC = _envf("EXT_FIRE_FRAC", 0.80)   # fire threshold (fraction of arm-EM)
TR_EXT_LO        = _envf("EXT_LO", 0.80)          # ramp floor (contribution begins)
TR_EXT_HI        = _envf("EXT_HI", 1.20)          # ramp max (fully spent / overshot)
W_VERT_EXT       = _envf("W_VERT_EXT", 0.50)      # extension weight in the shared core
W_VERT_ROOM      = _envf("W_VERT_ROOM", 0.20)
W_VERT_CONV      = _envf("W_VERT_CONV", 0.30)

# Machine states
DORMANT, STAGING, ARMED = "DORMANT", "STAGING", "ARMED"

# Corroborator weights (PRIOR; sum ≈ 1.0 per strategy). Same design-derived
# convention as regime_confluence v1.3: each block states the minimum evidence
# that should just barely stage, and a lone factor stays under TR_ARM_BAR.
W_CONT_CONV, W_CONT_PULL, W_CONT_MOM = 0.40, 0.35, 0.25
# ── SWP.3 (2026-08-13) — THE APPROACH TERM'S SIGN IS REFUTED ─────────────────
# `appr_val` entered as a POSITIVE corroborator at 0.25. THREE INDEPENDENT
# measurements, none of which knew about the others, say it points the other
# way: LIQ.1 (the London level TRACKS PRICE rather than being approached by it),
# ANT.1 (appr_val -41%, appr_touches -45% against outcome) and ANT.2 (fitted
# weights -0.39 / -0.40).
# WHY NOT JUST INVERT IT. `1 - appr_val` asserts "far from any named level =
# ready", which is nonsense for a SWEEP — the trade is penetration and rejection
# AT a level. The likelier mechanism is that PROXIMITY IS PRE-SWEEP: price near a
# pool means the sweep has not happened yet, so the term was scoring the setup's
# ABSENCE. We know the sign is wrong and we do NOT know the right functional
# form; asserting an inverted one swaps one unfitted prior for another.
# ⚠️ THE REMAINING THREE ARE RENORMALISED TO SUM TO 1.0. TR_STAGE_BAR (0.35) and
# TR_ARM_BAR (0.55) are ABSOLUTE thresholds against the corroborator SUM, so
# dropping 0.25 of weight without redistributing would compress every sweep
# score by a quarter and make the arm bar effectively unreachable — a silent
# behaviour change wearing the costume of a correction.
W_SWEEP_CONV, W_SWEEP_FRESH, W_SWEEP_EXH = 0.400, 0.267, 0.333
# v1.7 — APPROACH TO A NAMED LEVEL. Conviction must RISE as price nears a pool,
# and a level that has HELD against repeated tests outranks a virgin one.
# Distance is price delta normalised by ATR (operator, 2026-08-10) so 0.20 away
# is imminent on GLD and noise on NVDA without per-symbol tuning.
W_SWEEP_APPR        = _envf("SWEEP_APPR_W", 0.0)   # SWP.3 — sign refuted.
# ⚠️ RESTORING THIS IS NOT AS SIMPLE AS SETTING THE ENV VAR: a non-zero weight
# pushes the corroborator sum above 1.0 unless the other three are scaled back,
# which inflates every sweep score against the absolute bars. Change all four
# together or not at all. `appr_val` and its detail fields STAY JOURNALED —
# weight zero, not deleted, so the follow-up study needs no new collection.
# BOUNDS FITTED FROM THE SHADOW OBSERVER, not guessed (BACKLOG v4.05, first
# read 2026-08-07): only **14.0%** of observations sit within 0.5 ATR of a named
# level, MEDIAN **2.32 ATR**. My first draft used 0.15/1.20 — which would have
# put the MEDIAN TICK at zero proximity and left this term dead on roughly
# three-quarters of the session. I had the direction of the error backwards
# before reading the distribution, and the numbers were already on file.
TR_SWEEP_PROX_NEAR  = _envf("SWEEP_PROX_NEAR", 0.50)  # <= this ATR: full (~p14)
TR_SWEEP_PROX_FAR   = _envf("SWEEP_PROX_FAR", 2.32)   # >= this ATR: none (median)
TR_SWEEP_TOUCH_FULL = _envf("SWEEP_TOUCH_FULL", 4.0)  # touches for full quality
TR_SWEEP_TOUCH_MIN  = _envf("SWEEP_TOUCH_MIN", 1.0)
# PROVENANCE. Named levels are **61.3% London High/Low** in the shadow data, and
# there is a mechanism: London runs to 16:00 UTC = 12:00 ET, so it is the only
# named level still FORMING while RTH trades — extending rather than settled.
# ⚠️ DELIBERATELY A MODEST BONUS, NOT A MULTIPLIER. 61.3% is a frequency of
# PROXIMITY, not of profitability: a level you are always near because it
# brackets the range all day is not the same as a magnetic one. Weighting it
# heavily would encode "where price IS" as "where the edge is". If Friday's
# SHD.2 re-pull shows London's share does not predict sweeps, backing this out
# is a knob, not a redesign. Set to 1.0 to disable the distinction entirely.
TR_SWEEP_LONDON_MULT = _envf("SWEEP_LONDON_MULT", 1.15)
W_CNDR_APPROACH, W_CNDR_CONV, W_CNDR_ROOM = 0.45, 0.35, 0.20
# ── BUTTERFLY (v1.8, 2026-08-11) — THE PIN PLAY, SCORED AS ONE ───────────────
# The strategy is a GEX-PIN trade: enter a cheap debit tent CENTERED ON THE PIN
# while price is still a walk away, and let price migrate into it. Gate 5 of
# butterfly_strategy hard-refuses unless `gex_environment == "PINNING"`, and the
# body is `gex.pin_strike`, not ATM.
# ⚠️ THE READINESS TRACK WAS SCORING A DIFFERENT TRADE ENTIRELY. It graded
# `coil` (COMPRESSION label) as a HARD VETO plus a boolean squeeze and band
# width — a compression play. NOT ONE of the five gates that actually block the
# strategy was in it: no pin, no pin distance, no GEX environment, no entry
# window. That is why 2026-08-10 showed **would_fire=2132 against ONE trade**
# and R p50 0.995 / p90 1.000: the thing it measured genuinely was ready all
# day, and the thing that has to be true almost never was.
# The weights below are re-split so the score RISES AS THE THESIS COMES TRUE
# rather than switching on a label.
W_BFLY_PIN, W_BFLY_FIRM = 0.40, 0.20   # the thesis: distance to pin, pin strength
W_BFLY_CONV, W_BFLY_SQZ, W_BFLY_NARROW = 0.15, 0.10, 0.15   # coil, demoted
# Pin distance in EXPECTED-MOVE units. Inside NEAR the tent is already reachable;
# beyond FAR the migration is not a walk, it is a different trade.
TR_BFLY_PIN_NEAR    = _envf("BFLY_PIN_NEAR", 0.25)
TR_BFLY_PIN_FAR     = _envf("BFLY_PIN_FAR", 1.00)   # = BUTTERFLY_GEX_PIN_PROXIMITY_MULT
# Pin FIRMNESS from |net_gex|. A 2.3M pin is not a 0.1M pin, and the strategy's
# binary PINNING flag cannot tell them apart.
TR_BFLY_GEX_LO      = _envf("BFLY_GEX_LO", 0.3e6)
TR_BFLY_GEX_HI      = _envf("BFLY_GEX_HI", 2.0e6)
# Entry window is 12:00-14:00 ET. Readiness ARMS AHEAD of a trade, so this ramps
# UP toward noon instead of switching on at it — the whole point is to see the
# setup building through the late morning.
TR_BFLY_WARM_MIN    = _envf("BFLY_WARM_MIN", 90.0)  # minutes before 12:00 to start warming


@dataclass
class ReadinessState:
    """Per-strategy readiness track. All temporal fields are wall-clock."""
    machine:    str   = DORMANT
    r:          float = 0.0
    slope:      float = 0.0        # R-units per MINUTE, EMA'd
    last_ts:    float = 0.0        # wall-clock of last assess
    last_beat:  float = 0.0        # wall-clock of last heartbeat journal row
    peak_r:     float = 0.0        # session peak while >= STAGING (resets on DORMANT)
    conv_ema:   float = 0.0        # v1.1: smoothed conviction (wall-clock EMA)
    # v1.4 — arm-origin snapshot for extension-from-arm (operator 2026-07-28):
    # the "move" is defined to START when confluence first ARMS. Stamp price + EM
    # at each STAGING->ARMED transition; RE-STAMP on every re-arm (flicker/disarm
    # then re-arm = fresh origin); clear on disarm. Extension is measured as
    # travel since this origin / EM-at-this-origin. A short-premium vertical fires
    # only once >= TR_EXT_FIRE_FRAC (0.80) of the arm-EM has been consumed.
    origin_price: float = 0.0      # spot at the arm that opened this episode
    origin_em:    float = 0.0      # straddle expected move captured at that arm
    origin_ts:    float = 0.0      # wall-clock of that arm
    factors:    dict  = field(default_factory=dict)


class TradeReadinessEngine:
    """
    One instance per box. assess_all() every tick; emits journal rows through
    the injected emit callable (signal_journal.journal) on state transitions
    and on a throttled heartbeat while a strategy is >= STAGING.
    """

    STRATEGIES = ("continuation", "sweep", "condor_call", "condor_put", "butterfly",
                  "trend_credit_spread")

    def __init__(self, emit=None, clock=time.time, contract_ctx=None):
        self._emit = emit          # callable(event:str, **sections) or None
        self._clock = clock
        self._contract_ctx = contract_ctx   # signal_journal.contract_ctx (None-safe)
        try:                                # the LIVE selector — same code path
            from data.options_chain import get_chain_fetcher
            self._fetcher = get_chain_fetcher()
        except Exception:
            self._fetcher = None
        self.tracks: Dict[str, ReadinessState] = {
            k: ReadinessState() for k in self.STRATEGIES
        }

    # ── factor computation (READ-ONLY over already-computed state) ───────────

    def _continuation(self, ctx, regime) -> Tuple[float, dict]:
        """Trend pullback: trending label, conviction, midline proximity, resumption."""
        label = getattr(regime, "primary_regime", "") or ""
        conv  = float(getattr(regime, "conviction", 0.0) or 0.0)
        vol   = ctx.get("vol"); trend = ctx.get("trend")
        px    = float(ctx.get("price") or 0.0)
        trending = 1.0 if str(label).upper().endswith(("TRENDING_BULL", "TRENDING_BEAR")) else 0.0
        mid = float(getattr(vol, "bb_middle", 0.0) or 0.0) if vol else 0.0
        atr = float(getattr(vol, "atr_current", 0.0) or 0.0) if vol else 0.0
        # proximity: 1.0 at the midline, fading to 0 at 3x the entry tolerance
        # (0.35 ATR is the strategy's at-midline band; readiness sees the approach)
        if mid > 0 and atr > 0 and px > 0:
            dist_atr = abs(px - mid) / atr
            pull_val = 1.0 - ramp(dist_atr, TR_PULL_ATR_LO, TR_PULL_ATR_HI)
        else:
            pull_val = 0.0
        mom = getattr(trend, "primary_momentum", "") if trend else ""
        # resumption wants DECELERATING -> ACCELERATING; readiness grades the
        # precondition state: ACCELERATING = resuming now, FLAT = coiled, DECEL = still pulling back
        mom_val = {"ACCELERATING": TR_CONT_MOM_ACC, "FLAT": TR_CONT_MOM_FLAT,
                   "DECELERATING": TR_CONT_MOM_DEC, "": 0.0}.get(mom, 0.0)
        conv_val = ramp(conv, TR_CONV_LO, TR_CONV_HI)   # graded, not a cliff
        r = _combine(hard_vetoes=[trending], soft_necessary=[],
                     corroborators=[(W_CONT_CONV, conv_val),
                                    (W_CONT_PULL, pull_val),
                                    (W_CONT_MOM,  mom_val)])
        # v1.6 — `dir` on EVERY track. Derived here exactly as `_staged_pick`
        # derives it below, so the journal cannot disagree with the picker.
        # Outside a trending label the track is hard-vetoed to r=0 and has no
        # intended side, which is "" — an honest absence, not a guess.
        _dir = ("long" if str(label).upper().endswith("TRENDING_BULL")
                else ("short" if str(label).upper().endswith("TRENDING_BEAR") else ""))
        return r, {"label": label, "dir": _dir,
                   "conv": round(conv, 3), "conv_val": round(conv_val, 3),
                   "dist_atr": (None if not (mid > 0 and atr > 0 and px > 0)
                                else round(abs(px - mid) / atr, 3)),
                   "pull_val": round(pull_val, 3), "mom": mom, "mom_val": mom_val}

    def _sweep(self, ctx, regime) -> Tuple[float, dict]:
        """Exhaustion reversal: sweep label conviction, freshness, trend spent."""
        label = str(getattr(regime, "primary_regime", "") or "")
        conv  = float(getattr(regime, "conviction", 0.0) or 0.0)
        liq   = ctx.get("liq_map"); trend = ctx.get("trend")
        is_sweep = 1.0 if label.upper().endswith("SWEEP_REVERSAL") else 0.0
        age = float(getattr(liq, "sweep_age_bars", 999) or 999) if liq else 999.0
        fresh_val = 0.5 ** (age / max(TR_FRESH_HALFLIFE_B, 1e-6))
        mom = getattr(trend, "primary_momentum", "") if trend else ""
        exh_val = {"DECELERATING": TR_SWEEP_MOM_DEC, "FLAT": TR_SWEEP_MOM_FLAT,
                   "ACCELERATING": TR_SWEEP_MOM_ACC, "": 0.0}.get(mom, 0.0)
        conv_val = ramp(conv, TR_CONV_LO, TR_CONV_HI)

        # ── v1.7 — APPROACH: proximity to a named pool x how well it has held ─
        # ⚠️ AND THE HARD VETO ON THE LABEL IS GONE. `is_sweep` required the
        # committed label to BE SWEEP_REVERSAL. RGM.3 (baked 2026-08-08) removed
        # SWEEP from the argmax, so that label is never emitted and this whole
        # track scored a permanent ZERO — the same category error as the
        # dispatch gate, one layer down, created by our own fix. A proximity
        # term multiplied into a hard zero would have changed nothing, which is
        # exactly the trap the L1 version of this would have fallen into.
        # Readiness ARMS a track before its event; gating it on the event's own
        # label made arming impossible by construction.
        #
        # PROXIMITY is measured as PRICE DELTA NORMALISED BY ATR (operator's
        # spec): |price - pool| / atr, ramped so that near = 1 and far = 0. A
        # raw price gap could never be compared across a $30 and a $900 symbol.
        # LEVEL QUALITY scales it by touch_count — "a level that's held against
        # multiple tests should be higher scoring than a virgin one". The two
        # MULTIPLY rather than sum: being close to a level nobody has tested is
        # not the setup, and neither is a well-tested level far away. Only the
        # conjunction is.
        px  = float(ctx.get("price") or 0.0)
        vol = ctx.get("vol")
        atr = float(getattr(vol, "atr_current", 0.0) or 0.0) if vol else 0.0
        appr_val, _best = 0.0, None
        if px > 0 and atr > 0 and liq is not None:
            for _p in (getattr(liq, "pools", None) or []):
                _pp = float(getattr(_p, "price", 0.0) or 0.0)
                if _pp <= 0:
                    continue
                _d = abs(px - _pp) / atr
                _prox = 1.0 - ramp(_d, TR_SWEEP_PROX_NEAR, TR_SWEEP_PROX_FAR)
                _tc = float(getattr(_p, "touch_count", 0) or 0)
                _qual = ramp(_tc, TR_SWEEP_TOUCH_MIN, TR_SWEEP_TOUCH_FULL)
                _nm = str(getattr(_p, "name", "") or "")
                # ⚠️ A LONDON LEVEL IS STILL FORMING DURING RTH, so it accrues
                # FEW TOUCHES while being the most-approached level on the
                # board. touch_count alone would systematically UNDER-score
                # exactly the family the data says dominates — the bonus is
                # what stops the quality term penalising a live level for
                # being live.
                _lon = TR_SWEEP_LONDON_MULT if "LONDON" in _nm.upper() else 1.0
                _v = min(1.0, _prox * _qual * _lon)
                if _v > appr_val:
                    appr_val, _best = _v, (_pp, _d, _tc, _nm)

        r = _combine(hard_vetoes=[], soft_necessary=[],
                     corroborators=[(W_SWEEP_CONV, conv_val),
                                    (W_SWEEP_FRESH, fresh_val),
                                    (W_SWEEP_EXH, exh_val),
                                    (W_SWEEP_APPR, appr_val)])
        # v1.6 — `dir` from the LIVE sweep kind, the same source `_staged_pick`
        # reads. This is strictly better than anything an offline tool could
        # derive: the direction was only ever knowable from `ctx.liq_map`, which
        # is why the ledger had to pair readiness rows against staged picks to
        # get it. On a readiness row with no recent sweep there is no side, and
        # "" says so rather than inventing one.
        _sw = getattr(liq, "recent_sweep", None) if liq else None
        _kind = getattr(_sw, "kind", "") if _sw else ""
        _dir = "short" if _kind == "high_sweep" else ("long" if _kind == "low_sweep" else "")
        return r, {"label": label, "dir": _dir, "is_sweep": is_sweep,
                   "conv": round(conv, 3), "age_bars": age,
                   "fresh_val": round(fresh_val, 3), "mom": mom, "exh_val": exh_val,
                   "appr_val": round(appr_val, 3),
                   "appr_pool": (None if _best is None else round(_best[0], 2)),
                   "appr_dist_atr": (None if _best is None else round(_best[1], 3)),
                   "appr_touches": (None if _best is None else _best[2]),
                   # the level's NAME on every record — so "which levels get
                   # swept" becomes answerable from data instead of recollection
                   "appr_name": (None if _best is None else _best[3])}

    def _condor_side(self, ctx, regime, side: str) -> Tuple[float, dict]:
        """
        One condor side. The graded approach fraction the entry trigger already
        computes and then collapses at CONDOR_TRIGGER_APPROACH — here it is
        KEPT graded. Band edges proxy the short strikes (readiness runs before
        strike selection; the real trigger still uses the selected strikes).
        """
        label = str(getattr(regime, "primary_regime", "") or "")
        conv  = float(getattr(regime, "conviction", 0.0) or 0.0)
        vol   = ctx.get("vol"); px = float(ctx.get("price") or 0.0)
        ranging = 1.0 if label.upper().endswith("RANGING") else 0.0
        mid = float(getattr(vol, "bb_middle", 0.0) or 0.0) if vol else 0.0
        up  = float(getattr(vol, "bb_upper", 0.0) or 0.0) if vol else 0.0
        lo  = float(getattr(vol, "bb_lower", 0.0) or 0.0) if vol else 0.0
        approach = 0.0
        if px > 0 and mid > 0 and up > lo:
            if side == "call" and up > mid:
                approach = max(0.0, min((px - mid) / (up - mid), 1.5))
            elif side == "put" and mid > lo:
                approach = max(0.0, min((mid - px) / (mid - lo), 1.5))
        # graded through the 0.65 trigger point: staging begins well before it
        appr_val = ramp(approach, TR_APPROACH_LO, TR_APPROACH_HI)
        room_val = ramp(float(getattr(vol, "bb_width_pct", 0.0) or 0.0) if vol else 0.0,
                        TR_ROOM_LO, TR_ROOM_HI)   # a condor needs room
        conv_val = ramp(conv, TR_CONV_LO, TR_CONV_HI)
        # v1.4: extension-from-arm — has price consumed >= 80% of the arm-EM
        # toward THIS side's edge? (call side = up-move, put side = down-move).
        # This is the shared vertical-quality driver; a side won't fire until the
        # move it's selling against is spent. Reads the origin stamped at arm.
        tr_state = self.tracks.get("condor_" + side)
        ext_side = "up" if side == "call" else "down"
        ext_frac, ext_val, ext_fires = (self._extension_from_arm(tr_state, px, ext_side)
                                        if tr_state is not None else (0.0, 0.0, False))
        r = _combine(hard_vetoes=[ranging], soft_necessary=[],
                     corroborators=[(W_VERT_EXT,  ext_val),
                                    (W_CNDR_APPROACH, appr_val),
                                    (W_CNDR_CONV, conv_val),
                                    (W_CNDR_ROOM, room_val)])
        # v1.6 — `dir` is the side's EXPOSURE, not its option type. A call
        # credit is sold ABOVE and profits while price stays below it, so its
        # exposure is SHORT; the put side mirrors. This is the inverse of the
        # option-buyer call=long reading, and getting it backwards would have
        # silently inverted every condor row in the orientation ledger.
        # `side` stays alongside — the two answer different questions.
        return r, {"label": label, "dir": ("short" if side == "call" else "long"),
                   "conv": round(conv, 3), "side": side,
                   "approach": round(approach, 3), "appr_val": round(appr_val, 3),
                   "room_val": round(room_val, 3),
                   "ext_frac": round(ext_frac, 3), "ext_val": round(ext_val, 3),
                   "ext_fires": ext_fires, "origin_px": round(getattr(tr_state, "origin_price", 0.0), 2) if tr_state else 0.0,
                   "origin_em": round(getattr(tr_state, "origin_em", 0.0), 3) if tr_state else 0.0}

    def _butterfly(self, ctx, regime) -> Tuple[float, dict]:
        """Compression play: coil conviction, squeeze, narrowness degree."""
        label = str(getattr(regime, "primary_regime", "") or "")
        conv  = float(getattr(regime, "conviction", 0.0) or 0.0)
        vol   = ctx.get("vol")
        sqz_val = 1.0 if (getattr(vol, "bb_state", "") == "SQUEEZE" if vol else False) else 0.0
        width = float(getattr(vol, "bb_width_pct", 0.5) or 0.5) if vol else 0.5
        narrow_val = ramp(TR_NARROW_PIVOT - width, 0.0, TR_NARROW_SPAN)
        conv_val = ramp(conv, TR_CONV_LO, TR_CONV_HI)

        # ── v1.8 — THE PIN, THE FIRMNESS, THE CLOCK ─────────────────────────
        px  = float(ctx.get("price") or 0.0)
        gex = ctx.get("gex")
        pin = float(getattr(gex, "pin_strike", 0.0) or 0.0) if gex else 0.0
        env = str(getattr(gex, "gex_environment", "") or "") if gex else ""
        netg = abs(float(getattr(gex, "net_gex", 0.0) or 0.0)) if gex else 0.0

        # DISTANCE TO THE PIN, in EXPECTED-MOVE units — the operator's thesis
        # made numeric: "enter while price is still a walk away". Normalising by
        # EM rather than price is what makes it comparable across a $30 and a
        # $900 symbol, and it is the same unit the strategy's own proximity gate
        # uses. Rises as price migrates toward the pin.
        # EM is the right unit — it is what the strategy's own proximity gate
        # uses — but it needs a chain, and a chainless tick must not silently
        # zero the term that carries the whole thesis. ATR is the fallback unit:
        # a different scale, so `pin_dist_unit` records WHICH was used and the
        # two must never be pooled when fitting the bounds.
        em = self._expected_move_now(ctx, px) or 0.0
        _atr = float(getattr(vol, "atr_current", 0.0) or 0.0) if vol else 0.0
        if em > 0:
            _unit, _u = em, "em"
        elif _atr > 0:
            _unit, _u = _atr * 2.0, "atr2"      # ~1 EM on a typical 0DTE tape
        else:
            _unit, _u = 0.0, None
        pin_dist_em = (abs(px - pin) / _unit) if (_unit > 0 and pin > 0 and px > 0) else None
        pin_val = (1.0 - ramp(pin_dist_em, TR_BFLY_PIN_NEAR, TR_BFLY_PIN_FAR)) \
            if pin_dist_em is not None else 0.0

        # PIN FIRMNESS. The strategy's gate is BINARY (PINNING or not), so it
        # cannot rank a 2.3M pin above a 0.1M one — but conviction should.
        firm_val = ramp(netg, TR_BFLY_GEX_LO, TR_BFLY_GEX_HI) if netg > 0 else 0.0

        # THE ENVIRONMENT, AS A SOFT-NECESSARY RATHER THAN A CLIFF. PINNING is
        # what the strategy requires, so a non-pinning tape must not reach the
        # fire bar — but readiness exists to ARM AHEAD, so a NEUTRAL tape scores
        # a fraction rather than zero. That is the difference between "not yet"
        # and "never", and the old boolean could not express it.
        gex_val = {"PINNING": 1.0, "NEUTRAL": 0.35, "TRENDING": 0.10}.get(env, 0.20)

        # THE CLOCK, ramping UP toward the 12:00 window rather than switching on
        # at it. After 14:00 the window is shut and no score should survive it.
        try:
            _n = now_et()
            _mins = (_n.hour * 60 + _n.minute) - (12 * 60)
            if _mins > 120:                       # past 14:00 — window closed
                win_val = 0.0
            elif _mins >= 0:                      # inside the window
                win_val = 1.0
            else:                                 # warming toward noon
                win_val = ramp(TR_BFLY_WARM_MIN + _mins, 0.0, TR_BFLY_WARM_MIN)
        except Exception:                         # noqa: BLE001
            # ⚠️ DEFAULTING TO 1.0 HERE IS A CHOICE, NOT A SHRUG: an unreadable
            # clock must not SUPPRESS a setup that is otherwise present. But it
            # is also why `now_et` is imported at module scope — during the
            # build this was reachable via a missing import, and the score would
            # have sat at 1.0 all day while looking perfectly healthy.
            win_val = 1.0

        # COIL stays, DEMOTED from hard veto to corroborator. A coiling tape is
        # supporting evidence for a pin holding; it was never the trade itself,
        # and as a veto it made the score a switch on the label.
        coil_val = 1.0 if label.upper().endswith("COMPRESSION") else (
            0.5 if label.upper().endswith("RANGING") else 0.0)

        r = _combine(hard_vetoes=[], soft_necessary=[gex_val, win_val],
                     corroborators=[(W_BFLY_PIN, pin_val),
                                    (W_BFLY_FIRM, firm_val),
                                    (W_BFLY_CONV, conv_val),
                                    (W_BFLY_SQZ, sqz_val),
                                    (W_BFLY_NARROW, narrow_val * coil_val)])
        # v1.6 — butterfly is NEUTRAL by construction. Stamping it explicitly is
        # the point: an absent field and a deliberately sideless strategy are
        # indistinguishable to a reader, and that ambiguity is exactly what put
        # 30,565 records into one mislabeled "undecidable" bucket.
        return r, {"label": label, "dir": "neutral",
                   "conv": round(conv, 3),
                   "squeeze_val": sqz_val, "narrow_val": round(narrow_val, 3),
                   "coil_val": coil_val,
                   "gex_env": env or None, "gex_val": gex_val,
                   "pin": (round(pin, 2) if pin else None),
                   "pin_dist_em": (None if pin_dist_em is None else round(pin_dist_em, 3)),
                   "pin_dist_unit": _u,
                   "pin_val": round(pin_val, 3),
                   "net_gex": (round(netg / 1e6, 3) if netg else None),
                   "firm_val": round(firm_val, 3),
                   "win_val": round(win_val, 3)}

    @staticmethod
    def _expected_move_now(ctx, price):
        """
        ATM straddle expected move for THIS tick, if a chain is on ctx.
        EM = ATM call mark + ATM put mark. Returns 0.0 if unavailable (origin
        still stamps price; extension simply can\'t score until an EM exists).
        Never raises.
        """
        try:
            chain = ctx.get("chain")
            if chain is None or price <= 0:
                return 0.0
            calls = getattr(chain, "calls", None) or []
            puts  = getattr(chain, "puts", None) or []
            if not calls or not puts:
                return 0.0
            atm_c = min(calls, key=lambda c: abs(getattr(c, "strike", 0.0) - price))
            atm_p = min(puts,  key=lambda c: abs(getattr(c, "strike", 0.0) - price))
            em = float(getattr(atm_c, "mark", 0.0) or 0.0) + float(getattr(atm_p, "mark", 0.0) or 0.0)
            return em if em > 0 else 0.0
        except Exception:
            return 0.0

    @staticmethod
    def _extension_from_arm(tr, price, side):
        """
        Fraction of the arm-EM consumed since the track armed, and its ramp value.
        side: "up" (call-credit / bull-continuation, price rising away from origin)
              "down" (put-credit / bear, price falling away from origin).
        Returns (frac, ext_val, fires). frac<0 means price moved AGAINST the
        expected direction since arming (never fires). Requires a stamped origin
        with a real EM; returns (0,0,False) otherwise.
        """
        try:
            if getattr(tr, "origin_em", 0.0) <= 0 or getattr(tr, "origin_price", 0.0) <= 0:
                return 0.0, 0.0, False
            if side == "up":
                travel = price - tr.origin_price
            else:
                travel = tr.origin_price - price
            frac = travel / tr.origin_em
            ext_val = ramp(frac, TR_EXT_LO, TR_EXT_HI)
            # epsilon: hitting the threshold EXACTLY must fire (float repr of
            # e.g. 4.8/6.0 lands at 0.79999... and would silently not fire).
            fires = frac >= (TR_EXT_FIRE_FRAC - 1e-9)
            return frac, ext_val, fires
        except Exception:
            return 0.0, 0.0, False

    @staticmethod
    def _impulse_sd(df_1m, direction: str, lookback: int):
        """
        Return (sd_ratio, floor_px) for the most recent significant impulse
        candle in the trend direction, else (0.0, None).

        sd_ratio = candle_range / rolling_SD(range) over `lookback` prior bars.
        This is the operator's aware/established/screaming magnitude. floor_px
        is that candle's LOW (long/PCS) or HIGH (short/CCS) — the committed-flow
        origin that anchors the short strike. Degrades to (0.0, None) with no
        candles, so the corroborator simply contributes nothing (never raises).
        """
        try:
            if df_1m is None or len(df_1m) < lookback + 1:
                return 0.0, None
            highs = df_1m["high"].astype(float).values
            lows  = df_1m["low"].astype(float).values
            rng   = highs - lows
            last  = float(rng[-1])
            prior = rng[-(lookback + 1):-1]
            import statistics as _st
            sd = _st.pstdev(prior) if len(prior) > 1 else 0.0
            if sd <= 0:
                return 0.0, None
            ratio = last / sd
            floor_px = float(lows[-1]) if direction == "long" else float(highs[-1])
            # direction sanity: a bullish impulse should close up, bearish down
            closes = df_1m["close"].astype(float).values
            opens  = df_1m["open"].astype(float).values
            up = closes[-1] >= opens[-1]
            if (direction == "long" and not up) or (direction == "short" and up):
                return 0.0, None
            return ratio, floor_px
        except Exception:
            return 0.0, None

    def _trend_credit_spread(self, ctx, regime) -> Tuple[float, dict]:
        """
        Trend credit spread readiness (PCS in TRENDING_BULL, CCS in
        TRENDING_BEAR). Short-premium trend participation: sell a spread BEYOND
        the impulse candle so no pullback / no chase is needed. Graded, log-only.

        hard veto  : trending label in the correct direction
        corrobs    : impulse magnitude (SD ramp), conviction, structural room to
                     the impulse floor, momentum-live
        damper     : parabolic over-extension (exhaustion -> snapback risk)
        """
        label = str(getattr(regime, "primary_regime", "") or "").upper()
        conv  = float(getattr(regime, "conviction", 0.0) or 0.0)
        vol   = ctx.get("vol"); trend = ctx.get("trend")
        px    = float(ctx.get("price") or 0.0)
        df_1m = ctx.get("df_1m")

        if label.endswith("TRENDING_BULL"):
            direction, veto = "long", 1.0
        elif label.endswith("TRENDING_BEAR"):
            direction, veto = "short", 1.0
        else:
            direction, veto = "", 0.0

        atr = float(getattr(vol, "atr_current", 0.0) or 0.0) if vol else 0.0
        mid = float(getattr(vol, "bb_middle", 0.0) or 0.0) if vol else 0.0

        # impulse magnitude + floor
        sd_ratio, floor_px = self._impulse_sd(
            df_1m, direction, int(TR_TCS_SD_LOOKBACK)) if direction else (0.0, None)
        impulse_val = ramp(sd_ratio, TR_TCS_IMPULSE_SD_LO, TR_TCS_IMPULSE_SD_HI)

        # structural room: spot -> floor in ATR (more = safer short strike)
        if floor_px is not None and atr > 0 and px > 0:
            room_atr = (px - floor_px) / atr if direction == "long" else (floor_px - px) / atr
            room_val = ramp(room_atr, TR_TCS_ROOM_ATR_LO, TR_TCS_ROOM_ATR_HI)
        else:
            room_atr, room_val = None, 0.0

        # extension damper: parabolic over-extension from midline -> snapback risk
        if mid > 0 and atr > 0 and px > 0:
            ext_atr = abs(px - mid) / atr
            ext_damp = 1.0 - ramp(ext_atr, TR_TCS_EXT_ATR_LO, TR_TCS_EXT_ATR_HI)
        else:
            ext_atr, ext_damp = None, 1.0

        conv_val = ramp(conv, TR_CONV_LO, TR_CONV_HI)
        mom = getattr(trend, "primary_momentum", "") if trend else ""
        mom_val = {"ACCELERATING": TR_TCS_MOM_ACC, "FLAT": TR_TCS_MOM_FLAT,
                   "DECELERATING": TR_TCS_MOM_DEC, "": 0.0}.get(mom, 0.0)

        # v1.4: extension-from-arm, shared with the condor sides. A trend credit
        # spread also only fires once the move has consumed >= 80% of the EM that
        # existed when this track armed — same "premium is rich here" line.
        tr_state = self.tracks.get("trend_credit_spread")
        ext_side = "up" if direction == "long" else "down"
        armext_frac, armext_val, armext_fires = (
            self._extension_from_arm(tr_state, px, ext_side)
            if (tr_state is not None and direction) else (0.0, 0.0, False))
        r = _combine(
            hard_vetoes=[veto],
            soft_necessary=[ext_damp],
            corroborators=[(W_VERT_EXT,    armext_val),
                           (W_TCS_IMPULSE, impulse_val),
                           (W_TCS_CONV,    conv_val),
                           (W_TCS_ROOM,    room_val),
                           (W_TCS_MOM,     mom_val)])
        return r, {"label": label, "dir": direction, "sd_ratio": round(sd_ratio, 3),
                   "impulse_val": round(impulse_val, 3),
                   "floor_px": (None if floor_px is None else round(floor_px, 2)),
                   "room_atr": (None if room_atr is None else round(room_atr, 3)),
                   "room_val": round(room_val, 3), "conv": round(conv, 3),
                   "conv_val": round(conv_val, 3),
                   "ext_atr": (None if ext_atr is None else round(ext_atr, 3)),
                   "ext_damp": round(ext_damp, 3), "mom": mom, "mom_val": mom_val,
                   "armext_frac": round(armext_frac, 3),
                   "armext_val": round(armext_val, 3), "armext_fires": armext_fires,
                   "origin_px": round(getattr(tr_state, "origin_price", 0.0), 2) if tr_state else 0.0,
                   "origin_em": round(getattr(tr_state, "origin_em", 0.0), 3) if tr_state else 0.0}

    # ── the temporal core: slope + state machine ─────────────────────────────

    def _advance(self, key: str, r: float, factors: dict, now: float,
                 price: float = 0.0, em: float = 0.0):
        tr = self.tracks[key]
        # dt-aware slope: EMA of dR/dt in R-units/minute. Wall-clock only.
        dt = now - tr.last_ts if tr.last_ts > 0 else 0.0
        if dt <= 0 or dt > TR_MAX_DT_S:
            tr.slope = 0.0                       # cold start or stale gap: no heading claim
        else:
            inst = (r - tr.r) / (dt / 60.0)
            alpha = 1.0 - 0.5 ** (dt / TR_SLOPE_HALFLIFE_S)
            tr.slope = tr.slope + alpha * (inst - tr.slope)
        prev_machine, prev_r = tr.machine, tr.r
        tr.r, tr.last_ts, tr.factors = r, now, factors

        # state machine with hysteresis; bars relax by TR_HYSTERESIS going down
        m = tr.machine
        if m == DORMANT:
            if r >= TR_STAGE_BAR:
                m = STAGING
        if m == STAGING:
            if r >= TR_ARM_BAR and tr.slope > 0:
                m = ARMED
            elif r < TR_STAGE_BAR - TR_HYSTERESIS:
                m = DORMANT
        if m == ARMED:
            if tr.slope <= TR_DEARM_SLOPE or r < TR_ARM_BAR - TR_HYSTERESIS:
                m = STAGING if r >= TR_STAGE_BAR else DORMANT
        would_fire = (m == ARMED and r >= TR_FIRE_BAR and tr.slope > 0)

        # ── arm-origin snapshot (v1.4) ───────────────────────────────────────
        # Stamp price+EM at EVERY entry into ARMED (fresh episode OR re-arm after
        # a flicker). Clear when we leave ARMED. Per operator: re-arm re-snapshots.
        just_armed = (m == ARMED and prev_machine != ARMED)
        left_armed = (m != ARMED and prev_machine == ARMED)
        if just_armed:
            tr.origin_price = price
            tr.origin_em    = em
            tr.origin_ts    = now
        elif left_armed:
            tr.origin_price = 0.0
            tr.origin_em    = 0.0
            tr.origin_ts    = 0.0

        if m != DORMANT:
            tr.peak_r = max(tr.peak_r, r)
        elif prev_machine != DORMANT:
            tr.peak_r = 0.0

        transition = (m != prev_machine)
        tr.machine = m
        return transition, would_fire, prev_machine

    @staticmethod
    def _market_snapshot(ctx: dict) -> dict:
        """VWAP context for this tick, journaled on every readiness record.

        WHY IT IS HERE. `volatility_engine` has computed `vwap` and
        `price_vs_vwap` all along and NOTHING PERSISTED THEM. A key scan of
        2026-08-05's journal — 11,138 records, every event type — found no
        VWAP-shaped field anywhere, which is why `vwap_orientation` has never
        once run. It is not a broken tool; it was built against a schema that
        never landed.
        WHY IT MATTERS NOW: item AI's candidate fix for the condor is a
        VWAP-ANCHORED midpoint instead of the flat Bollinger midline. That
        cannot be evaluated on data that does not exist, so every session
        between now and the decision is history we either have or do not — the
        same use-it-or-lose-it logic as the candle tape.
        `dist_pct` is SIGNED and expressed as a percentage of VWAP, so it is
        comparable across a $30 symbol and a $900 one. `price_vs_vwap` is
        carried alongside rather than derived from it, because the engine sets
        NONE when there is no volume and a computed sign would silently invent
        an orientation there.
        Log-only. Returns {} rather than raising: this must never reach the
        trading loop.
        """
        try:
            vol = (ctx or {}).get("vol")
            px = float((ctx or {}).get("price") or 0.0)
            vw = float(getattr(vol, "vwap", 0.0) or 0.0) if vol else 0.0
            if vw <= 0 or px <= 0:
                return {"vwap": None, "price_vs_vwap": "NONE", "dist_pct": None}
            return {"vwap": round(vw, 4),
                    "price_vs_vwap": getattr(vol, "price_vs_vwap", "NONE"),
                    "dist_pct": round(100.0 * (px - vw) / vw, 4)}
        except Exception:                                        # noqa: BLE001
            return {}

    _mkt: dict = {}

    def _journal(self, key: str, event: str, prev: Optional[str] = None):
        if self._emit is None:
            return
        tr = self.tracks[key]
        try:
            self._emit(event, readiness={
                "strategy": key, "machine": tr.machine, "prev": prev,
                "r": round(tr.r, 3), "slope_per_min": round(tr.slope, 4),
                "peak_r": round(tr.peak_r, 3), "factors": tr.factors,
                "market": self._mkt,
                "bars": {"stage": TR_STAGE_BAR, "arm": TR_ARM_BAR,
                         "fire": TR_FIRE_BAR}})
        except Exception as e:                    # noqa: BLE001 — log-only, never the loop
            log.debug(f"readiness journal skipped: {e}")

    # ── public entry point ───────────────────────────────────────────────────

    def assess_all(self, ctx: dict, regime) -> Dict[str, ReadinessState]:
        """
        Evaluate every strategy's readiness for this tick. Never raises.
        Call every tick, including while halted or holding a position — the
        observational record is the point.
        """
        now = self._clock()
        # v1.5 — one snapshot per tick, shared by every track's journal record.
        self._mkt = self._market_snapshot(ctx)
        try:
            computed = {
                "continuation": self._continuation(ctx, regime),
                "sweep":        self._sweep(ctx, regime),
                "condor_call":  self._condor_side(ctx, regime, "call"),
                "condor_put":   self._condor_side(ctx, regime, "put"),
                "butterfly":    self._butterfly(ctx, regime),
                "trend_credit_spread": self._trend_credit_spread(ctx, regime),
            }
        except Exception as e:                    # noqa: BLE001
            log.debug(f"readiness assess skipped: {e}")
            return self.tracks
        conv_now = float(getattr(regime, "conviction", 0.0) or 0.0)
        # v1.4: price + expected move for the arm-origin snapshot. EM from the
        # ATM straddle if a chain is on ctx; else 0 (origin still stamps price,
        # extension just can't be computed until an EM is available — logged).
        px_now = float(ctx.get("price") or 0.0)
        em_now = self._expected_move_now(ctx, px_now)
        for key, (r, factors) in computed.items():
            tr = self.tracks[key]
            # v1.1: smoothed conviction — the calm number staged picks use.
            dtc = now - tr.last_ts if tr.last_ts > 0 else 0.0
            if dtc <= 0 or dtc > TR_MAX_DT_S:
                tr.conv_ema = conv_now
            else:
                a = 1.0 - 0.5 ** (dtc / TR_CONV_HALFLIFE_S)
                tr.conv_ema = tr.conv_ema + a * (conv_now - tr.conv_ema)
            transition, would_fire, prev = self._advance(key, r, factors, now,
                                                         price=px_now, em=em_now)
            beat = (tr.machine != DORMANT and (now - tr.last_beat) >= TR_HEARTBEAT_S)
            if transition:
                self._journal(key, "readiness", prev=prev)
            elif beat:
                tr.last_beat = now
                self._journal(key, "readiness")
            if would_fire:
                self._journal(key, "readiness_would_fire")
            # v1.1: staged pick — ARMED only, throttled to beats/transitions/fires.
            if tr.machine == ARMED and (transition or beat or would_fire):
                self._staged_pick(key, ctx, tr, would_fire)
        return self.tracks

    # ── v1.1: the staged pick (LOG-ONLY — never touches an order) ────────────

    def _staged_pick(self, key: str, ctx: dict, tr: ReadinessState, at_fire: bool):
        if key not in ("continuation", "sweep") or self._fetcher is None:
            return
        chain = ctx.get("chain")
        if chain is None:
            return
        try:
            if key == "sweep":
                liq = ctx.get("liq_map")
                sweep = getattr(liq, "recent_sweep", None) if liq else None
                kind = getattr(sweep, "kind", "") if sweep else ""
                direction = "short" if kind == "high_sweep" else ("long" if kind == "low_sweep" else "")
                if not direction:
                    return
                try:
                    from strategy.sweep_reversal_strategy import _sweep_target_delta
                    target = _sweep_target_delta(tr.conv_ema)
                except Exception:
                    target = 0.20
            else:  # continuation: with the trend
                label = str(tr.factors.get("label", "") or "")
                direction = "long" if label.upper().endswith("TRENDING_BULL") else                             ("short" if label.upper().endswith("TRENDING_BEAR") else "")
                if not direction:
                    return
                target = TR_CONT_TARGET_DELTA
            contract = self._fetcher.select_sweep_strike(chain, direction, target)
            if contract is None or self._emit is None:
                return
            cctx = self._contract_ctx(contract) if self._contract_ctx else {
                "strike": getattr(contract, "strike", None),
                "delta":  getattr(contract, "delta", None),
                "bid":    getattr(contract, "bid", None),
                "ask":    getattr(contract, "ask", None),
                "mark":   getattr(contract, "mark", None)}
            self._emit("readiness_staged_pick", staged={
                "strategy": key, "direction": direction, "at_would_fire": at_fire,
                "target_delta": round(float(target), 4),
                "conv_ema": round(tr.conv_ema, 3),
                "r": round(tr.r, 3), "slope_per_min": round(tr.slope, 4),
                "contract": cctx})
        except Exception as e:                    # noqa: BLE001 — log-only
            log.debug(f"staged pick skipped: {e}")


# ── Standalone smoke test ─────────────────────────────────────────────────────
if __name__ == "__main__":                        # pragma: no cover
    from types import SimpleNamespace as NS

    rows = []
    eng = TradeReadinessEngine(emit=lambda ev, **s: rows.append((ev, s)),
                               clock=lambda: eng._t)
    eng._t = 1000.0

    vol = NS(bb_middle=100.0, bb_upper=102.0, bb_lower=98.0,
             atr_current=0.5, bb_width_pct=0.45, bb_state="NORMAL")
    trend = NS(primary_momentum="DECELERATING")

    def tick(px, conv, mom, dt=15.0):
        eng._t += dt
        trend.primary_momentum = mom
        ctx = {"vol": vol, "trend": trend, "liq_map": None, "price": px}
        regime = NS(primary_regime="TRENDING_BULL", conviction=conv)
        eng.assess_all(ctx, regime)
        return eng.tracks["continuation"]

    # RISING confluence: pullback approaches the midline, conviction firms,
    # momentum flips DECEL -> FLAT -> ACCELERATING. Readiness must climb
    # DORMANT -> STAGING -> ARMED and emit would_fire at the top.
    seq = [(101.2, 0.30, "DECELERATING"), (101.0, 0.35, "DECELERATING"),
           (100.8, 0.40, "DECELERATING"), (100.6, 0.45, "FLAT"),
           (100.45, 0.50, "FLAT"), (100.3, 0.55, "FLAT"),
           (100.2, 0.60, "ACCELERATING"), (100.1, 0.62, "ACCELERATING"),
           (100.05, 0.65, "ACCELERATING")]
    path = []
    for px, cv, mom in seq:
        tr = tick(px, cv, mom)
        path.append((round(tr.r, 3), round(tr.slope, 3), tr.machine))
    print("rising path (r, slope/min, machine):")
    for p in path:
        print("  ", p)
    assert path[0][2] == DORMANT and path[-1][2] == ARMED, "must climb to ARMED"
    assert any(m == STAGING for _, _, m in path), "must pass through STAGING"
    assert all(b[0] >= a[0] for a, b in zip(path, path[1:])), "R must be monotone rising here"
    assert any(ev == "readiness_would_fire" for ev, _ in rows), "would_fire must emit at the top"

    # FALLING confluence: same level, slope collapses (wick-flicker class).
    # ARMED must de-arm on slope, not wait for the level to break.
    for px, cv, mom in [(100.6, 0.50, "FLAT"), (101.1, 0.40, "DECELERATING"),
                        (101.5, 0.32, "DECELERATING")]:
        tr = tick(px, cv, mom)
    print("after collapse:", (round(tr.r, 3), round(tr.slope, 3), tr.machine))
    assert tr.machine != ARMED, "slope collapse must de-arm"

    trans = [s["readiness"]["machine"] for ev, s in rows if ev == "readiness"]
    print(f"journal rows: {len(rows)} (transitions+beats), machines seen: {sorted(set(trans))}")
    print("smoke test OK — readiness rises with confluence, arms with slope, de-arms on collapse")

    # ── Trend credit spread: impulse SD ramp drives readiness ────────────────
    print("\n--- trend_credit_spread: aware(1.75) -> established(2.0) -> screaming(2.5) ---")
    import pandas as _pd

    def _mkdf(target_sd_ratio, base=100.0, n=25):
        # Build prior bars whose range pstdev == 1.0 exactly (alternating
        # +/-0.5 around mean 1.0 -> pstdev 0.5... so use +/-1.0 around 1.0),
        # then set the impulse candle's range = target_sd_ratio so
        # ratio = last_range / pstdev(prior) == target_sd_ratio exactly.
        rows_ = []
        for i in range(n - 1):
            rr = 2.0 if i % 2 == 0 else 0.0001   # ranges {2.0, ~0}: mean 1.0, pstdev ~1.0
            rows_.append({"open": base, "high": base + rr / 2, "low": base - rr / 2,
                          "close": base})
        lr = target_sd_ratio            # since pstdev(prior) == 1.0, range == ratio
        o = base - lr / 2; c = base + lr / 2   # bullish impulse: opens low, closes high
        rows_.append({"open": o, "high": c, "low": o, "close": c})
        return _pd.DataFrame(rows_)

    eng2 = TradeReadinessEngine(emit=lambda ev, **s: None, clock=lambda: eng2._t)
    eng2._t = 5000.0
    vol2 = NS(bb_middle=99.5, bb_upper=103.0, bb_lower=96.0,
              atr_current=1.0, bb_width_pct=0.5, bb_state="NORMAL")
    trend2 = NS(primary_momentum="ACCELERATING")

    def tcs_r(target_sd, conv=0.65):
        eng2._t += 15.0
        df = _mkdf(target_sd)
        ctx = {"vol": vol2, "trend": trend2, "liq_map": None,
               "price": 100.5, "df_1m": df}
        regime = NS(primary_regime="TRENDING_BULL", conviction=conv)
        r, f = eng2._trend_credit_spread(ctx, regime)
        return r, f

    # hold prior-range SD ~= 1.0, vary the impulse candle's range to hit SD tiers
    r_aware, f_aware = tcs_r(1.75)      # exactly 1.75 SD
    r_estab, f_estab = tcs_r(2.00)      # exactly 2.0 SD
    r_scream, f_scream = tcs_r(2.80)    # 2.8 SD (screaming)
    r_none, f_none = tcs_r(0.90)        # below aware (0.9 SD)
    for name, r, f in [("below(0.9SD)", r_none, f_none), ("aware(1.75)", r_aware, f_aware),
                       ("established(2.0)", r_estab, f_estab), ("screaming(2.8)", r_scream, f_scream)]:
        print(f"  {name:16} sd={f['sd_ratio']:.2f} impulse_val={f['impulse_val']:.2f} "
              f"floor={f['floor_px']} room={f['room_val']:.2f} R={r:.3f}")
    # ramp semantics: impulse_val is 0 AT the aware floor (1.75) and rises above
    # it, maxing at screaming (2.50). So 'aware' is where contribution BEGINS.
    assert f_none["impulse_val"] == 0.0, "below 1.75 SD must contribute no impulse"
    assert f_aware["impulse_val"] == 0.0, "AT 1.75 SD the ramp is at its floor (0)"
    r_above_aware, f_above = tcs_r(1.90)     # just above the aware floor
    assert f_above["impulse_val"] > 0.0, "just above 1.75 SD must start contributing"
    assert f_scream["impulse_val"] >= f_estab["impulse_val"] >= f_above["impulse_val"], \
        "impulse must rise above-aware -> established -> screaming"
    assert abs(f_scream["impulse_val"] - 1.0) < 1e-6, "2.5+ SD must max the impulse (screaming)"
    assert r_scream > r_aware, "screaming impulse must produce higher readiness than aware"
    assert f_scream["floor_px"] is not None, "impulse must anchor a strike floor"

    # veto: non-trending label -> zero readiness regardless of impulse
    eng2._t += 15.0
    df = _mkdf(2.80)
    r_v, f_v = eng2._trend_credit_spread(
        {"vol": vol2, "trend": trend2, "liq_map": None, "price": 100.5, "df_1m": df},
        NS(primary_regime="RANGING", conviction=0.7))
    assert r_v == 0.0, "non-trending label must veto the trend credit spread to 0"
    print(f"  veto(RANGING)    R={r_v:.3f}  (correctly stood down)")

    # extension damper: parabolic price crushes an otherwise-screaming setup
    eng2._t += 15.0
    df = _mkdf(2.80)
    r_ext, f_ext = eng2._trend_credit_spread(
        {"vol": vol2, "trend": trend2, "liq_map": None,
         "price": 99.5 + 5.0 * 1.0, "df_1m": df},   # 5 ATR above midline = parabolic
        NS(primary_regime="TRENDING_BULL", conviction=0.7))
    print(f"  parabolic(5ATR)  ext_damp={f_ext['ext_damp']:.2f} R={r_ext:.3f} "
          f"(damped vs screaming R={r_scream:.3f})")
    assert r_ext < r_scream, "parabolic over-extension must damp readiness (snapback risk)"
    print("trend_credit_spread smoke test OK — impulse ramp drives readiness, "
          "trend veto stands down, extension damps exhaustion")
