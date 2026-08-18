# analysis/regime_confluence.py — options_trader_v3 — v1.4
# v1.4 — 2026-08-08 — THE SPENT MOVE. Operator's spec, stated plainly: "a SPENT
#         move into a named liquidity pool that gets rejected." The pool
#         (veto_loc) and the rejection (veto_reclaim + rejq_val) were always
#         scored. "Spent" was only ever inferred from 5m momentum, and NOTHING
#         ASKED WHAT WAS SPENT — so a rejection at a named level in dead air and
#         the same rejection at the end of an extended trending leg scored
#         identically. Only the second is the trade.
#         (1) NEW CORROBORATOR `spent_val`, ramped off `ambient` = the max of
#             this tick's TRENDING_BULL / TRENDING_BEAR / BREAKOUT_VOLATILE
#             scores. Those are computed a few lines earlier in score(), so this
#             adds NO new input, no new state and no ordering dependency —
#             the information was already in hand and simply never consulted.
#             A CORROBORATOR, NOT A SOFT-NECESSARY: multiplicative would mean a
#             sweep can only fire after a strong trend, which is narrower than
#             what was asked for. "Permitted and encouraged", not required.
#         (2) `opp_mom[""]` 0.8 -> 0.6. An absent 5m vote used to suppress
#             almost as hard as a fully ACCELERATING opposing trend AND, via
#             exh_val[""] = 0.0, withhold half the corroborating evidence — ONE
#             missing input penalised TWICE, landing hardest on exactly the
#             setup this scorer exists for.
#         ⚠️ THE ASYMMETRY IS DELIBERATE AND MUST NOT BE "TIDIED": absence of
#             evidence must not count as evidence AGAINST (so "" now matches
#             FLAT in the suppression term), and must not count as evidence FOR
#             (so exh_val[""] deliberately STAYS 0.0). Making these symmetric in
#             either direction is a regression, and both halves are pinned by
#             tests/test_sweep_spent_move.py.
#         ⚠️ WHAT DID NOT MOVE, AND MUST NOT: the hard veto triple (veto_loc,
#             veto_reclaim, veto_accept) is UNCHANGED — the operator's spec IS
#             those three, so permissiveness never reaches them. And `trend_opp`
#             stays a SOFT-NECESSARY: a high ambient score must never rescue a
#             sweep fighting an accelerating opposing trend. That is the
#             2026-07-27 PLTR loss (-27.8% on a put into a +7.2% uptrend) and
#             its guard is the load-bearing test in the new file.
#         CONTEXT: sweep last fired 2026-07-29. It was gated on winning an
#         argmax it was built to lose — a category error the operator named
#         repeatedly ("sweep isn't a regime"). SWP.1 and RGM.3 removed that gate
#         and baked 08-08; this makes the underlying score reflect the setup the
#         operator actually trades. Knobs: SWEEP_SPENT_CTX_LO/HI, W_SWEEP_SPENT.
# v1.3.2 — 2026-08-04 — DISPLAY ONLY, inside the __main__ self-test: its score
#         line truncated regime names at 5 chars, so TRENDING_BULL and
#         TRENDING_BEAR both printed "TREND". Uses utils/regime_labels. NO
#         scoring, weight, veto or threshold is touched — every v1.3/v1.3.1
#         canary string is unchanged.
# v1.3.1 — 2026-07-27 — COMPRESSION CONTAINMENT VETO (A3 fix, found in the
#         A/B pool). _compression gains hard veto veto_inside: price closed
#         beyond the band edge zeroes the coil. Its own truth is flat center +
#         tightening container + FADED excursions; a close outside the band is
#         an unfaded excursion — release, not storage. Latent pre-v1.3
#         (COMPRESSION scored >0.5 on squeeze-break ticks but old BREAKOUT
#         could not accumulate, so A3 never collided); v1.3's honest breakout
#         exposed it on XOM 2026-07-22 14:10-14:11 (COMP 0.572 with price
#         BELOW_LOWER vs BRK 0.585 — two A3-violating ticks). Verified: those
#         ticks now score COMP 0.0, XOM back to 5/5 acceptance, and the veto
#         changes nothing on any tick where price is INSIDE.
# v1.3 — 2026-07-27 — CONFLUENCE EXCAVATION. Four of the five scorers were
#         Boolean gates wearing confluence clothing. Rebuilt as true
#         accumulating evidence. ORB is not scored here and is untouched;
#         _trending is unchanged and remains the reference implementation.
#         (a) CONSTANT CORROBORATORS KILLED. The ranging base-weight term, the
#             compression base-weight term, and the vol-only fallback's 0.5
#             pair were all weighted against a fixed 1.0 that never varied with
#             evidence — a Boolean gate's flat base pretending to be agreement.
#             All three removed. (Their identifiers are deliberately NOT spelled
#             here: check_versions greps bare tokens to prove they are gone, and
#             changelog prose has re-tripped absence canaries twice before.)
#         (b) EMPTY CORROBORATOR BLOCKS FILLED. _breakout and _sweep both
#             passed corroborators=[], so _combine defaulted their sum term to
#             1.0 and the score was PURELY vetoes x dampers. Nothing
#             accumulated. Both now carry real weighted evidence.
#         (c) RE-SLOTTING (the substantive change). rej_pct (_sweep) and
#             expand_s (_breakout) were already graded but sat in
#             soft_necessary, which asserts "this setup is partially INVALID".
#             That is the wrong claim: weak rejection means weakly SUPPORTED,
#             not partly invalid. Both promoted to corroborators. narrow_s
#             (_compression) likewise. Expect the score DISTRIBUTION to move
#             in both directions — a term that multiplied the whole score by
#             0.6 now contributes its weight additively.
#         (d) _sweep IS NO LONGER TREND-BLIND. Signature gains trend_state.
#             2026-07-27 a box shorted PLTR into a +7.2% uptrend at conviction
#             0.62 and lost 27.8%: _sweep could not see trend at all. A
#             trend-opposition soft-necessary now collapses a reversal that
#             fights a strong ACCELERATING trend to ~0. REGIME_TRUTHS.md's
#             discriminator matrix always listed "direction (reject dir)" for
#             SWEEP; it was never implemented. This implements it.
#         (e) OSC_CROSS_* DECOUPLED. _ranging (many crossings = rotation) and
#             _compression (few = coil) read OPPOSITE ENDS OF ONE AXIS, so a
#             dial moved for one see-sawed the other — measured on 2026-07-22,
#             COMPRESSION p90 0.65 -> 0.879 purely as a side effect of the
#             osc_s move for RANGING. Each scorer now has its own bounds,
#             DEFAULTED TO THE SHARED VALUE so the split itself is a no-op.
#             OSC_CROSS_LO/HI survive as the shared default and keep their
#             OT_RC_ env names; per-scorer overrides are OT_RC_RANGE_OSC_* and
#             OT_RC_COMP_OSC_*.
#         (f) FABRICATED FALLBACKS DELETED. The ranging no-window branch (a flat
#             0.6 from a Boolean) and the compression vol-only branch both
#             invented a score when the bar window was unavailable. Measured at
#             0.1% of 100,281 ticks, so behaviourally negligible — but they are
#             the exact lie being excavated. Both now return None. Unobservable
#             is not the same as refuted, and the contract already carries None.
#         WEIGHTS ARE DESIGN-DERIVED, NOT TAPE-FITTED. Each block below states
#         the minimum evidence set that should just barely score, and the
#         weights are solved so that set lands at the gate. They have NOT been
#         calibrated against the 6-session pool — that is the next pass, and
#         until it runs these are honest priors, not fitted values.
# v1.2 — 2026-07-22 — RAMP DE-SATURATION. Two changes, one behavioural.
#         (a) All 14 ramp PRIOR bounds are now env-overridable via OT_RC_<NAME>
#             (helper _envf), so calibration is a config change with instant
#             rollback rather than a code edit. No behavioural delta by itself.
#         (b) BEHAVIOURAL: room_s and osc_s bounds re-fitted from tape and
#             promoted to defaults —
#               RANGE_ROOM_LO 0.05 -> 0.17,  RANGE_ROOM_HI 0.20 -> 1.00
#               OSC_CROSS_LO  2.0  -> 4.0,   OSC_CROSS_HI  5.0  -> 10.0
#             Both terms were behaving as SWITCHES, not dials: room_s was
#             pegged at 1.0 on 72.7%% of scored ticks (hi bound sat at input
#             p27), osc_s on 70.5%% (hi at p30). RANGING therefore saturated
#             every day (p90 = 1.0) and collided with TRENDING.
#             Fitted on 60,341 ticks across 6 sessions (2026-07-14/15/16/17/
#             20/21; 07-13 excluded — ADX-starved, no warm-up). The pool
#             independently re-derives these same bounds (room_s p25/p95 =
#             0.16/1.00, osc_s 4/10), i.e. convergence, not a one-day fit.
#             Result: room_s 15.8%% -> 66.2%% graded, osc_s 22.5%% -> 60.0%%,
#             RANGING p90 1.0 -> 0.476, A2 violations 14.4%% -> 4.3%% of ticks.
#             NOTE OSC_CROSS_* is shared with _compression, which reads FEW
#             crossings as a coil — the crossings axis is a see-saw, so this
#             also lifts COMPRESSION (p90 0.65 -> 0.879). Expected, watched.
#         Unchanged and still unfitted: flat_s (conditional sample — only
#         ticks past the flat veto), adx_s / align_val (offline HTF starvation,
#         align_frac never exceeds 0.67 in replay — blocked on L1.9 bookmark).
# v1.1 — 2026-07-12 — FIX silent config-import failure. The guarded import
#         requested SWEEP_ACCEPT_CLOSES from config, but it lives in
#         analysis/regime_classifier.py; the whole block threw, the except
#         swallowed it, and every constant ran on standalone fallbacks
#         (_HAVE_CONFIG=False on every box — verified at runtime). Split into
#         two independent guards: config constants from config,
#         SWEEP_ACCEPT_CLOSES from its real home. Zero behavioral delta today
#         (fallbacks equal live config values); future config tunes now reach
#         the scorer. No scoring-logic change.
# v1.0 — 2026-07-11 — NEW FILE (not present at HEAD 49d7af8).
#         Layer 1 — Regime Confluence Scorer. Instantaneous, graded, per-regime
#         evidence in [0,1] (or None = unobservable) computed every tick from the
#         engine state objects. Implements REGIME_TRUTHS.md v0.1 in the three-tier
#         grammar:  score_R = (∏ hard_veto ∈{0,1}) · (∏ soft_necessary ∈[0,1])
#                            · (Σ w_k · corroborator_k),   Σ w_k = 1
#
# LAYER BOUNDARY (enforced):
#   • Instantaneous only. No smoothing, no memory, no count-over-N, no accumulation.
#     The 25-bar angle/crossings window is a property of the CURRENT window (legal),
#     not accumulated belief. Persistence is Layer 2 (conviction integrator).
#   • No reference to strikes, premium, sizing, fills, ROI, or tradability (Layer 3).
#   • Unobservable ≠ contradicted:  None = inputs unavailable;  0.0 = actively refuted.
#   • Instrument-agnostic: every input is ATR-relative, a percentile, an angle, or a
#     categorical engine state — one parameter set serves SPX and a $4 name alike.
#
# Output contract: score(...) -> ConfluenceResult(scores, breakdown).
#   scores:   Dict[str, Optional[float]] keyed by the six regime labels — the exact
#             vector the conviction integrator's update()/replay() consumes.
#   breakdown: Dict[str, dict] — every raw input and mapped factor per regime, for
#             shadow logging and PRIOR calibration. (No I/O here; caller logs it.)
#
# Standalone: guards the repo config import; duck-types the state objects; no side
# effects at import. Importable and testable in isolation ( __main__ smoke test ).

from __future__ import annotations

import os as _os
import math
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# ── Guarded repo imports (module runs standalone if the repo is absent) ───────
# v1.1: split into TWO independent guards. The v1.0 block requested
# SWEEP_ACCEPT_CLOSES from config, but that constant lives in
# analysis/regime_classifier.py — the whole import threw, the except swallowed
# it, and ALL FOUR constants silently ran on the standalone fallbacks
# (_HAVE_CONFIG was False on every box). Harmless only while the fallback
# values equal config's; any future config tune would never have reached this
# scorer. Now each import fails independently.
try:
    from config import (                       # type: ignore
        ADX_TREND_THRESHOLD,
        ADX_RANGE_THRESHOLD,
        BB_WIDTH_COMPRESSION_PCT,
    )
    _HAVE_CONFIG = True
except Exception:                              # pragma: no cover - isolation path
    ADX_TREND_THRESHOLD      = 25.0
    ADX_RANGE_THRESHOLD      = 20.0
    BB_WIDTH_COMPRESSION_PCT = 0.20
    _HAVE_CONFIG = False

try:
    from analysis.regime_classifier import SWEEP_ACCEPT_CLOSES  # type: ignore
except Exception:                              # pragma: no cover - isolation path
    SWEEP_ACCEPT_CLOSES      = 2

# ── Regime labels (MUST match conviction_integrator.py string constants) ──────
TRENDING_BULL     = "TRENDING_BULL"
TRENDING_BEAR     = "TRENDING_BEAR"
RANGING           = "RANGING"
BREAKOUT_VOLATILE = "BREAKOUT_VOLATILE"
COMPRESSION       = "COMPRESSION"
SWEEP_REVERSAL    = "SWEEP_REVERSAL"
REGIMES = (TRENDING_BULL, TRENDING_BEAR, RANGING,
           BREAKOUT_VOLATILE, COMPRESSION, SWEEP_REVERSAL)

# ── Calibration knobs (ALL PRIOR — recalibrate from candle-logger tape) ───────
# --- env-tunable PRIOR bounds -------------------------------------------------
# v3.1: every ramp bound below is overridable via OT_RC_<NAME> so calibration is
# a config change (instant rollback, no deploy) rather than a code edit. Defaults
# are UNCHANGED, so importing this module with no env set is behaviour-identical.
def _envf(name: str, default: float) -> float:
    try:
        return float(_os.environ.get("OT_RC_" + name, default))
    except (TypeError, ValueError):
        return default


FLAT_ANGLE_CUT_DEG   = _envf("FLAT_ANGLE_CUT_DEG", 20.0)   # RANGING/COMPRESSION hard veto: ≥ ⇒ center not flat
FLAT_ANGLE_SOFT_DEG  = _envf("FLAT_ANGLE_SOFT_DEG", 8.0)    # full flat credit at (CUT − SOFT) = 12°
RANGE_WINDOW_BARS    = 25     # angle + crossings window (matches tape study)
ADX_STRONG_SOLO      = _envf("ADX_STRONG_SOLO", 35.0)   # ADX above which strength carries a trend solo
SWEEP_HALFLIFE_BARS  = 3.0    # sweep evidence half-life, absent follow-through
OSC_CROSS_LO         = _envf("OSC_CROSS_LO", 4.0)    # crossings ramp lo (few = pin/coil)
OSC_CROSS_HI         = _envf("OSC_CROSS_HI", 10.0)    # crossings ramp hi (many = two-sided rotation)
RANGE_ROOM_LO        = _envf("RANGE_ROOM_LO", 0.17)   # RANGING "room to oscillate": below this width, not ranging
RANGE_ROOM_HI        = _envf("RANGE_ROOM_HI", 1.00)   #   … at/above this width, full room (= BB_WIDTH_COMPRESSION_PCT)
BREAKOUT_ADX_LO      = _envf("BREAKOUT_ADX_LO", 38.0)   # momentum-carry ramp: inside-band forgiven from here
BREAKOUT_ADX_HI      = _envf("BREAKOUT_ADX_HI", 50.0)   #   … to here (fully forgiven)
EXPAND_RATIO_LO      = _envf("EXPAND_RATIO_LO", 1.0)    # atr_current/atr_avg_20 expansion ramp
EXPAND_RATIO_HI      = _envf("EXPAND_RATIO_HI", 1.5)
SWEEP_REJ_LO         = _envf("SWEEP_REJ_LO", 0.002)  # rejection_pct → strength ramp
SWEEP_REJ_HI         = _envf("SWEEP_REJ_HI", 0.008)
COMPRESS_WIDTH_SPAN  = _envf("COMPRESS_WIDTH_SPAN", 0.15)   # narrowness ramp span below BB_WIDTH_COMPRESSION_PCT

# v1.3 — DECOUPLED crossings bounds. OSC_CROSS_* above remains the shared
# default (and keeps its OT_RC_OSC_CROSS_* env names, so nothing that pins the
# old values breaks). Each scorer now reads its OWN bound, defaulted to that
# shared value, so this split is behaviour-identical until one is overridden.
# Rationale: the two scorers read opposite ends of ONE axis, which made every
# calibration of one an uncontrolled change to the other.
RANGE_OSC_LO = _envf("RANGE_OSC_LO", OSC_CROSS_LO)
RANGE_OSC_HI = _envf("RANGE_OSC_HI", OSC_CROSS_HI)
COMP_OSC_LO  = _envf("COMP_OSC_LO",  OSC_CROSS_LO)
COMP_OSC_HI  = _envf("COMP_OSC_HI",  OSC_CROSS_HI)

# v1.3 — new PRIOR bounds for the rebuilt corroborators.
SWEEP_OPP_ADX_LO     = _envf("SWEEP_OPP_ADX_LO", 20.0)   # opposing-trend suppression ramps in from here
SWEEP_OPP_ADX_HI     = _envf("SWEEP_OPP_ADX_HI", 35.0)   #   … to full opposition here
SWEEP_TOUCH_LO       = _envf("SWEEP_TOUCH_LO", 2.0)      # swept pool touch_count → level quality
SWEEP_TOUCH_HI       = _envf("SWEEP_TOUCH_HI", 5.0)
BREAKOUT_CLEAR_SPAN  = _envf("BREAKOUT_CLEAR_SPAN", 0.50)  # clearance beyond the band edge, in HALF-BAND units
COMP_ATR_CONTRACT_LO = _envf("COMP_ATR_CONTRACT_LO", 0.60)  # atr_current/atr_avg_20 at/below → full contraction credit
COMP_ATR_CONTRACT_HI = _envf("COMP_ATR_CONTRACT_HI", 1.00)  #   … at/above → no contraction credit

# ── Corroborator weights (PRIOR; each block sums to 1.0) ──────────────────────
# v1.3: every block below is DERIVED from a stated minimum-evidence rule rather
# than picked. The rule for each is written above its weights, and the gate the
# arithmetic is solved against is the Layer-3 B-grade bar (0.55). A block whose
# weights are not traceable to such a statement is a guess.
W_TREND_ALIGN, W_TREND_MOM   = 0.65, 0.35          # unchanged — reference impl

# RANGING — "rotation alone is not a range; it must rotate EVENLY about the
# center." osc alone 0.55 sits AT the bar and cannot clear it, so a lopsided
# sawtooth that happens to cross often does not classify as range.
W_RANGE_OSC, W_RANGE_BAL = 0.55, 0.45

# COMPRESSION — "faded oscillation alone is not a coil." stored alone 0.45 sits
# below the bar; stored + ATR contraction 0.80 clears it.
#   narrow_s STAYS A SOFT-NECESSARY and is deliberately NOT promoted to a
#   corroborator. The first cut of this rebuild did promote it, and the smoke
#   test caught the consequence immediately: on wide-band RANGE tape,
#   COMPRESSION scored 0.25 where it must score 0, because a corroborator at 0
#   only costs its weight while a necessary condition at 0 kills the regime. A
#   coil with a wide container is not a coil. REGIME_TRUTHS.md §0 predicts this
#   exactly — premium regimes keep their mass in vetoes because the expensive
#   error is CLAIMING the regime, whereas directional regimes keep corroborators
#   compensatory because the expensive error is MISSING the move. That asymmetry
#   is why expand_val IS promoted in _breakout and narrow_s is NOT here.
#   The re-slotting rule is not universal; it is decided per regime by which
#   error costs more.
# squeeze_val is the one Boolean left in any corroborator block. It is real
# evidence that varies with data (not a constant), and carries the least weight.
W_COMP_STORED, W_COMP_ATR, W_COMP_SQZ = 0.45, 0.35, 0.20

# BREAKOUT — "expansion alone is not a breakout." expansion alone 0.40 sits
# below the bar; expansion + decisive clearance 0.70 clears it. ADX is
# deliberately NOT a corroborator here: outside_s already consumes ADX as its
# carry term, and scoring it twice inside one scorer is double-counting.
W_BRK_EXPAND, W_BRK_CLEAR, W_BRK_MOM = 0.40, 0.30, 0.30

# SWEEP — "a strong rejection at a good level, on its own, must NOT classify a
# reversal." rejection quality alone 0.45 sits below the bar; it needs the trend
# to be visibly spent. Rejection depth and level quality are MERGED into one
# term because they are correlated (strong levels produce strong rejections) and
# corroborators are defined as *independent* compensatory evidence — weighting
# around a correlation double-counts it, merging does not. Deceleration carries
# the larger weight because a reversal's entire thesis is that the prior move is
# spent; the pre-v1.3 engine weighted it at zero.
W_SWEEP_REJQ, W_SWEEP_EXH = 0.45, 0.55
# v1.4 — SPENT-MOVE CONTEXT. The operator's spec is "a SPENT move into a named
# liquidity pool that gets rejected". The pool and the rejection were always
# scored; "spent" was only ever inferred from 5m momentum, with no reference to
# WHAT was spent. These gate a corroborator that asks whether the thing being
# faded was actually a trending or breakout-volatile move — the setup the
# operator trades — rather than a rejection occurring in dead air.
SWEEP_SPENT_CTX_LO   = _envf("SWEEP_SPENT_CTX_LO", 0.35)  # ambient trend/breakout score
SWEEP_SPENT_CTX_HI   = _envf("SWEEP_SPENT_CTX_HI", 0.75)  #   … to full context here
W_SWEEP_SPENT        = _envf("W_SWEEP_SPENT", 0.35)       # weight of the spent-context corroborator
W_SWEEP_REJ_DEPTH, W_SWEEP_REJ_LEVEL = 0.60, 0.40   # internal split of rejection quality


# ── Pure helpers ──────────────────────────────────────────────────────────────
def ramp(x: float, lo: float, hi: float) -> float:
    """Monotone [lo,hi] → [0,1] clamp."""
    if hi <= lo:
        return 1.0 if x >= hi else 0.0
    return min(max((x - lo) / (hi - lo), 0.0), 1.0)


def flat_angle_deg(closes: List[float], atr: float) -> Optional[float]:
    """
    Instrument-agnostic trend/flat read over a window of closes:
        angle = arctan( |slope·n| / (ATR·√n) )   in degrees, 0=flat … 90=steep
    Numerator = net regression drift; denominator = the random-walk excursion a
    pure-noise process of this ATR would show over n bars. Dimensionless ratio ⇒
    one cutoff serves SPX and a $4 name. Returns None if inputs unusable.
    """
    n = len(closes)
    if n < 8 or atr is None or atr <= 0:
        return None
    xbar = (n - 1) / 2.0
    ybar = sum(closes) / n
    sxx = sum((i - xbar) ** 2 for i in range(n))
    sxy = sum((i - xbar) * (closes[i] - ybar) for i in range(n))
    slope = sxy / sxx if sxx > 0 else 0.0
    drift = abs(slope * n)
    noise = atr * math.sqrt(n)
    return math.degrees(math.atan2(drift, noise))


def midline_crossings(closes: List[float]) -> int:
    """
    Crossings of the window's own regression midline. Graded confirmation ONLY,
    valid AFTER the flat-angle veto certifies the center flat. Many crossings =
    two-sided rotation (RANGING spends energy); few = pin/coil (COMPRESSION stores
    it). No R²/fit filter — shark-fin scatter is expected; only the center holds.
    """
    n = len(closes)
    if n < 8:
        return 0
    xbar = (n - 1) / 2.0
    ybar = sum(closes) / n
    sxx = sum((i - xbar) ** 2 for i in range(n))
    sxy = sum((i - xbar) * (closes[i] - ybar) for i in range(n))
    slope = sxy / sxx if sxx > 0 else 0.0
    resid = [closes[i] - (ybar + slope * (i - xbar)) for i in range(n)]
    return sum(1 for a, b in zip(resid, resid[1:])
               if a != 0 and b != 0 and (a > 0) != (b > 0))


def momentum_val(mom: str) -> float:
    """
    5m momentum → corroborator value. v1.3.

    NOTE THE "" CASE. trend_engine v3.2 surfaces primary_momentum with default
    "" and its docstring is explicit that "" means NO 5m VOTE THIS TICK and
    consumers MUST treat it as no-trade, not as neutral. Mapping "" to 0.5 would
    hand every warm-up tick half a corroborator's worth of evidence it has not
    earned — which is the same class of lie as a constant corroborator. It maps
    to 0.0: no vote, no credit. This is NOT a veto; the other corroborators in
    each block can still carry a setup, by design.
    """
    return {"ACCELERATING": 1.0, "FLAT": 0.5, "DECELERATING": 0.0, "": 0.0}.get(mom, 0.0)


def midline_balance(closes: List[float]) -> float:
    """
    How EVENLY the window rotates about its own regression midline, in [0,1].
    1.0 = residuals split 50/50 above/below; 0.0 = entirely one-sided.

    Independent of crossing COUNT, which is the point: crossings measure how
    often the tape rotates, balance measures whether the rotation is two-sided.
    A drifting sawtooth can cross the midline often while sitting mostly on one
    side of it — that is not a range, and counting crossings alone cannot tell.
    This is the real variable that replaces the old ranging base-weight constant.
    """
    n = len(closes)
    if n < 8:
        return 0.0
    xbar = (n - 1) / 2.0
    ybar = sum(closes) / n
    sxx = sum((i - xbar) ** 2 for i in range(n))
    sxy = sum((i - xbar) * (closes[i] - ybar) for i in range(n))
    slope = sxy / sxx if sxx > 0 else 0.0
    resid = [closes[i] - (ybar + slope * (i - xbar)) for i in range(n)]
    nz = [r for r in resid if r != 0]
    if not nz:
        return 0.0
    above = sum(1 for r in nz if r > 0) / len(nz)
    return max(0.0, min(1.0, 1.0 - abs(above - 0.5) * 2.0))


def _combine(hard_vetoes: List[float],
             soft_necessary: List[float],
             corroborators: List[Tuple[float, float]]) -> float:
    """
    score = (∏ hard_veto ∈{0,1}) · (∏ soft_necessary ∈[0,1]) · (Σ w·corroborator).
    Empty corroborator block ⇒ sum term defaults to 1.0 (veto·necessary only).
    """
    for v in hard_vetoes:
        if v <= 0.0:
            return 0.0
    prod = 1.0
    for s in soft_necessary:
        prod *= max(0.0, min(1.0, s))
    if corroborators:
        csum = sum(w * max(0.0, min(1.0, val)) for w, val in corroborators)
    else:
        csum = 1.0
    return max(0.0, min(1.0, prod * csum))


# ── Result container ──────────────────────────────────────────────────────────
@dataclass
class ConfluenceResult:
    scores:    Dict[str, Optional[float]] = field(default_factory=dict)
    breakdown: Dict[str, dict]            = field(default_factory=dict)

    def evidence(self) -> Dict[str, Optional[float]]:
        """The bare score vector the conviction integrator consumes."""
        return dict(self.scores)


# ── The scorer ────────────────────────────────────────────────────────────────
class RegimeConfluenceScorer:
    """
    Layer 1. One instance per box; `score()` is pure w.r.t. its arguments (no
    retained state between ticks — persistence is Layer 2's job by design).
    """

    def __init__(self,
                 adx_trend_threshold: float = float(ADX_TREND_THRESHOLD),
                 adx_range_threshold: float = float(ADX_RANGE_THRESHOLD)):
        self.adx_trend = adx_trend_threshold
        self.adx_range = adx_range_threshold

    # -- individual regime scorers each return (score|None, breakdown_dict) -----

    def _trending(self, trend_state, structure) -> Tuple[Dict[str, Optional[float]], dict]:
        if trend_state is None:
            return {TRENDING_BULL: None, TRENDING_BEAR: None}, {"reason": "no trend_state"}
        adx        = getattr(trend_state, "primary_adx", 0.0)
        aligned    = getattr(trend_state, "aligned_timeframes", 0)
        total      = max(getattr(trend_state, "total_timeframes", 0), 1)
        direction  = getattr(trend_state, "overall_direction", "NEUTRAL")
        is_bullish = getattr(trend_state, "is_bullish", direction == "BULLISH")
        seq        = getattr(structure, "structure_sequence", "NEUTRAL") if structure else "NEUTRAL"

        align_frac = aligned / total
        # v1.3 fix: alignment CORROBORATES marginal ADX; strong ADX forgives it.
        align_val  = max(align_frac, ramp(adx, self.adx_trend, ADX_STRONG_SOLO))

        # momentum corroborator (primary/5m vote if present; neutral otherwise)
        mom = "FLAT"
        votes = getattr(trend_state, "votes", None)
        if votes:
            v = votes.get("5m") or votes.get("1m") or next(iter(votes.values()), None)
            if v is not None:
                mom = getattr(v, "momentum", "FLAT")
        mom_val = {"ACCELERATING": 1.0, "FLAT": 0.5, "DECELERATING": 0.0}.get(mom, 0.5)

        contra    = "LH_LL" if is_bullish else "HH_HL"
        veto_struct = 0.0 if seq == contra else 1.0
        veto_dir    = 0.0 if direction not in ("BULLISH", "BEARISH") else 1.0
        adx_s       = ramp(adx, self.adx_trend - 5, ADX_STRONG_SOLO)   # soft-necessary

        trend_e = _combine(
            hard_vetoes=[veto_struct, veto_dir],
            soft_necessary=[adx_s],
            corroborators=[(W_TREND_ALIGN, align_val), (W_TREND_MOM, mom_val)],
        )
        bd = {"adx": round(adx, 2), "adx_s": round(adx_s, 3),
              "align_frac": round(align_frac, 3), "align_val": round(align_val, 3),
              "momentum": mom, "mom_val": mom_val, "structure_sequence": seq,
              "veto_struct": veto_struct, "veto_dir": veto_dir,
              "direction": direction, "trend_e": round(trend_e, 3)}

        if direction == "BULLISH":
            return {TRENDING_BULL: trend_e, TRENDING_BEAR: 0.0}, bd
        if direction == "BEARISH":
            return {TRENDING_BULL: 0.0, TRENDING_BEAR: trend_e}, bd
        return {TRENDING_BULL: 0.0, TRENDING_BEAR: 0.0}, bd

    def _breakout(self, vol_state, trend_state, closes=None) -> Tuple[Optional[float], dict]:
        """
        v1.3 REBUILD. Pre-v1.3 this passed corroborators=[], so _combine
        defaulted the sum term to 1.0 and the score was expand_s * outside_s —
        two dampers and nothing accumulating. Breakout STRENGTH now accumulates.

        `closes` is optional and used only for the clearance read; absent it,
        clearance contributes 0 rather than being invented.
        """
        if vol_state is None:
            return None, {"reason": "no vol_state"}
        adx        = getattr(trend_state, "primary_adx", 0.0) if trend_state else 0.0
        mom        = getattr(trend_state, "primary_momentum", "") if trend_state else ""
        atr_cur    = getattr(vol_state, "atr_current", 0.0)
        atr_avg    = max(getattr(vol_state, "atr_avg_20", 0.0), 1e-3)
        is_exp     = getattr(vol_state, "is_expanding", False)
        price_vs_bb = getattr(vol_state, "price_vs_bb", "INSIDE")

        atr_ratio = atr_cur / atr_avg
        # RE-SLOTTED v1.3: was a soft-necessary damper, now the primary
        # corroborator. Expansion magnitude is evidence of breakout STRENGTH,
        # not a statement that a weakly-expanding breakout is partly invalid.
        expand_val = ramp(atr_ratio, EXPAND_RATIO_LO, EXPAND_RATIO_HI) if is_exp \
                     else ramp(atr_ratio, EXPAND_RATIO_LO + 0.1, EXPAND_RATIO_HI + 0.1) * 0.6
        # SOFT-NECESSARY (kept): a breakout must be outside the band, or else
        # carried by ADX through a momentary inside-band print. This is a
        # genuine necessary condition, so it stays multiplicative.
        outside_s = 1.0 if price_vs_bb != "INSIDE" else ramp(adx, BREAKOUT_ADX_LO, BREAKOUT_ADX_HI)

        # NEW corroborator: how DECISIVELY the band edge was cleared, in
        # half-band units so it is instrument-agnostic like every other input.
        bb_up  = getattr(vol_state, "bb_upper", 0.0)
        bb_lo  = getattr(vol_state, "bb_lower", 0.0)
        bb_mid = getattr(vol_state, "bb_middle", 0.0)
        clear_val = 0.0
        clear_frac = None
        px = closes[-1] if closes else None
        half_band = max((bb_up - bb_lo) / 2.0, 1e-9)
        if px is not None and bb_up > 0 and bb_lo > 0 and bb_up > bb_lo:
            if px > bb_up:
                clear_frac = (px - bb_up) / half_band
            elif px < bb_lo:
                clear_frac = (bb_lo - px) / half_band
            else:
                clear_frac = 0.0
            clear_val = ramp(clear_frac, 0.0, BREAKOUT_CLEAR_SPAN)

        mom_val = momentum_val(mom)

        score = _combine(
            hard_vetoes=[],
            soft_necessary=[outside_s],
            corroborators=[(W_BRK_EXPAND, expand_val),
                           (W_BRK_CLEAR,  clear_val),
                           (W_BRK_MOM,    mom_val)],
        )
        bd = {"atr_ratio": round(atr_ratio, 3), "is_expanding": is_exp,
              "expand_val": round(expand_val, 3), "price_vs_bb": price_vs_bb,
              "adx": round(adx, 2), "outside_s": round(outside_s, 3),
              "bb_middle": round(bb_mid, 4),
              "clear_frac": (None if clear_frac is None else round(clear_frac, 3)),
              "clear_val": round(clear_val, 3),
              "momentum": mom, "mom_val": mom_val,
              "w": {"expand": W_BRK_EXPAND, "clear": W_BRK_CLEAR, "mom": W_BRK_MOM},
              "score": round(score, 3)}
        return score, bd

    def _compression(self, vol_state, closes, atr) -> Tuple[Optional[float], dict]:
        if vol_state is None:
            return None, {"reason": "no vol_state"}
        bb_width_pct = getattr(vol_state, "bb_width_pct", 0.5)
        atr_state    = getattr(vol_state, "atr_state", "STABLE")
        bb_state     = getattr(vol_state, "bb_state", "NORMAL")
        is_exp       = getattr(vol_state, "is_expanding", False)

        # SOFT-NECESSARY (kept, deliberately — see the weight block). A coil
        # with a wide container is not a coil; this must be able to kill the score.
        narrow_s    = ramp(BB_WIDTH_COMPRESSION_PCT - bb_width_pct, 0.0, COMPRESS_WIDTH_SPAN)
        veto_notexp = 0.0 if (is_exp or atr_state == "EXPANDING") else 1.0
        squeeze_val = 1.0 if bb_state == "SQUEEZE" else 0.0
        # NEW corroborator: ATR contraction DEPTH. Independent of band width —
        # realized-range contraction and container width are related but
        # distinct measures, and a coil shows both.
        atr_cur_c   = getattr(vol_state, "atr_current", 0.0)
        atr_avg_c   = max(getattr(vol_state, "atr_avg_20", 0.0), 1e-3)
        atr_ratio_c = atr_cur_c / atr_avg_c
        atr_contract_val = 1.0 - ramp(atr_ratio_c, COMP_ATR_CONTRACT_LO, COMP_ATR_CONTRACT_HI)
        # v1.3.1 HARD VETO: the container must CONTAIN. A close beyond the band
        # edge is an unfaded excursion — energy being RELEASED, the negation of
        # compression's own truth (flat center + tightening container + FADED
        # excursions). Latent in the old engine: COMPRESSION scored >0.5 on
        # squeeze-BREAK ticks (price outside a narrow band, ATR not yet
        # expanded) but never collided with anything because old BREAKOUT
        # could not accumulate. v1.3's honest breakout exposed it as an A3
        # violation (XOM 2026-07-22 14:10-14:11: COMP 0.572 with price
        # BELOW_LOWER, BRK 0.585). Instantaneous, current-tick field —
        # Layer-1 legal; a resumed squeeze re-passes next tick.
        pbb_c = getattr(vol_state, "price_vs_bb", "INSIDE")
        veto_inside = 1.0 if pbb_c == "INSIDE" else 0.0

        bd = {"bb_width_pct": round(bb_width_pct, 3), "narrow_s": round(narrow_s, 3),
              "atr_state": atr_state, "bb_state": bb_state, "veto_notexp": veto_notexp,
              "price_vs_bb": pbb_c, "veto_inside": veto_inside,
              "atr_ratio": round(atr_ratio_c, 3),
              "atr_contract_val": round(atr_contract_val, 3)}

        # Potential-energy read: flat center (veto) + tightening container + FADED
        # excursions (low crossings = energy stored, not released). Window path when
        # bars available; else a reduced-ceiling vol-only fallback (not blind).
        if closes is not None and atr is not None and len(closes) >= RANGE_WINDOW_BARS:
            w = closes[-RANGE_WINDOW_BARS:]
            ang = flat_angle_deg(w, atr)
            if ang is None:
                return None, {**bd, "reason": "angle uncomputable"}
            veto_flat = 0.0 if ang >= FLAT_ANGLE_CUT_DEG else 1.0
            cross = midline_crossings(w)
            osc_s = ramp(cross, COMP_OSC_LO, COMP_OSC_HI)   # v1.3: own bounds
            stored_val = 1.0 - osc_s          # few crossings ⇒ energy absorbed, not spent
            score = _combine(
                hard_vetoes=[veto_flat, veto_notexp, veto_inside],
                soft_necessary=[narrow_s],
                corroborators=[(W_COMP_STORED, stored_val),
                               (W_COMP_ATR,    atr_contract_val),
                               (W_COMP_SQZ,    squeeze_val)],
            )
            bd.update({"angle": round(ang, 2), "veto_flat": veto_flat,
                       "crossings": cross, "osc_s": round(osc_s, 3),
                       "stored_val": round(stored_val, 3), "squeeze_val": squeeze_val,
                       "w": {"stored": W_COMP_STORED, "atr": W_COMP_ATR,
                             "sqz": W_COMP_SQZ},
                       "path": "window", "score": round(score, 3)})
            return score, bd
        else:
            # v1.3: this fabricated branch is DELETED. It invented a score from
            # (0.5, 1.0) — a constant — whenever the bar window was missing.
            # Measured at ~0.1% of ticks, so removing it is behaviourally
            # negligible, but a fabricated number is exactly what this pass
            # exists to remove. Unobservable is not refuted: return None and let
            # the integrator see an abstain, which the contract already supports.
            return None, {**bd, "path": "no_window", "reason": "no bar window"}

    def _ranging(self, vol_state, trend_state, closes, atr) -> Tuple[Optional[float], dict]:
        adx     = getattr(trend_state, "primary_adx", 0.0) if trend_state else 0.0
        is_exp  = getattr(vol_state, "is_expanding", False) if vol_state else False
        pbb     = getattr(vol_state, "price_vs_bb", "INSIDE") if vol_state else "INSIDE"

        if closes is not None and atr is not None and len(closes) >= RANGE_WINDOW_BARS:
            w = closes[-RANGE_WINDOW_BARS:]
            ang = flat_angle_deg(w, atr)
            if ang is None:
                return None, {"reason": "angle uncomputable"}
            if ang >= FLAT_ANGLE_CUT_DEG:
                return 0.0, {"angle": round(ang, 2), "veto_flat": 0.0, "score": 0.0}
            flat_s = ramp(FLAT_ANGLE_CUT_DEG - ang, 0.0, FLAT_ANGLE_SOFT_DEG)   # soft-necessary
            bb_width_pct = getattr(vol_state, "bb_width_pct", 0.5) if vol_state else 0.5
            room_s = ramp(bb_width_pct, RANGE_ROOM_LO, RANGE_ROOM_HI)           # soft-necessary
            cross  = midline_crossings(w)
            osc_s  = ramp(cross, RANGE_OSC_LO, RANGE_OSC_HI)     # v1.3: own bounds
            # v1.3: replaces the old ranging base-weight constant. Range QUALITY accumulates
            # instead of sitting on a free 0.40 floor that never varied.
            bal_val = midline_balance(w)
            score  = _combine(hard_vetoes=[1.0], soft_necessary=[flat_s, room_s],
                              corroborators=[(W_RANGE_OSC, osc_s),
                                             (W_RANGE_BAL, bal_val)])
            bd = {"angle": round(ang, 2), "veto_flat": 1.0, "flat_s": round(flat_s, 3),
                  "bb_width_pct": round(bb_width_pct, 3), "room_s": round(room_s, 3),
                  "crossings": cross, "osc_s": round(osc_s, 3),
                  "balance_val": round(bal_val, 3),
                  "w": {"osc": W_RANGE_OSC, "bal": W_RANGE_BAL},
                  "path": "window", "score": round(score, 3)}
            return score, bd
        else:
            # v1.3: this fabricated branch is DELETED. It returned a flat 0.6 from a
            # three-way Boolean whenever the bar window was missing — a constant
            # by another name, and blind to exactly the energetic chop the angle
            # read exists to catch. ~0.1% of ticks. Abstain instead.
            return None, {"path": "no_window", "reason": "no bar window",
                          "adx": round(adx, 2), "is_expanding": is_exp,
                          "price_vs_bb": pbb}

    def _sweep(self, liq_map, trend_state=None, ambient=None) -> Tuple[Optional[float], dict]:
        """
        v1.3 REBUILD — the scorer that caused the 2026-07-27 PLTR loss.

        Pre-v1.3 this took only liq_map. It was STRUCTURALLY INCAPABLE of seeing
        a trend, so a lone level-rejection scored 0.62 while the underlying ran
        +7.2% on its SMA50, and the fleet bought a put into it. It also passed
        corroborators=[], so nothing accumulated: the score was two dampers.

        REGIME_TRUTHS.md's discriminator matrix has always carried a `direction
        (reject dir)` cell for SWEEP. It was never implemented. It is now.
        """
        if liq_map is None:
            return None, {"reason": "no liq_map"}
        sweep = getattr(liq_map, "recent_sweep", None)
        if sweep is None:
            return 0.0, {"reason": "no recent_sweep", "score": 0.0}
        reclaimed = getattr(sweep, "reclaimed", False)
        named     = getattr(sweep, "swept_named_level", "")
        beyond    = getattr(sweep, "closes_beyond", 0)
        rej_pct   = getattr(sweep, "rejection_pct", 0.0)
        kind      = getattr(sweep, "kind", "")
        pool_px   = getattr(sweep, "pool_price", 0.0)
        age_bars  = getattr(liq_map, "sweep_age_bars", 999)

        # -- hard vetoes (UNCHANGED — the closed sweep truth triple) -----------
        veto_loc     = 1.0 if named else 0.0
        veto_reclaim = 1.0 if reclaimed else 0.0
        veto_accept  = 1.0 if beyond < SWEEP_ACCEPT_CLOSES else 0.0

        # -- reversal direction, derived from the side that was swept ----------
        # high_sweep = highs taken and rejected DOWN  => the reversal is SHORT
        # low_sweep  = lows taken and rejected UP     => the reversal is LONG
        rev_dir = "SHORT" if kind == "high_sweep" else ("LONG" if kind == "low_sweep" else "")

        # -- NEW soft-necessary: trend opposition ------------------------------
        # A reversal that fights a strong, accelerating trend is not a reversal;
        # it is a loss with a good story. Multiplicative so opposition can zero
        # the score outright, which is the whole point.
        adx  = getattr(trend_state, "primary_adx", 0.0) if trend_state else 0.0
        direction = getattr(trend_state, "overall_direction", "NEUTRAL") if trend_state else "NEUTRAL"
        mom  = getattr(trend_state, "primary_momentum", "") if trend_state else ""
        opposed = (rev_dir == "SHORT" and direction == "BULLISH") or \
                  (rev_dir == "LONG"  and direction == "BEARISH")
        opp_adx = ramp(adx, SWEEP_OPP_ADX_LO, SWEEP_OPP_ADX_HI)
        # An opposing trend that is DECELERATING is the exhaustion we are
        # trading, so it barely suppresses. One that is ACCELERATING suppresses
        # fully.
        # v1.4 — "" NO LONGER SUPPRESSES HARDER THAN FLAT. It was 0.8, close to
        # full opposition, purely because the 5m vote was absent. Combined with
        # exh_val's "" -> 0.0 below, ONE missing input both crushed the
        # multiplier AND removed half the corroborating evidence — a DOUBLE
        # penalty from a single absence, and it lands hardest on exactly the
        # setup this scorer exists for.
        # THE ASYMMETRY IS DELIBERATE AND IS THE WHOLE FIX: absence of evidence
        # must not COUNT AS evidence against (so "" is treated as FLAT here),
        # but it must also not COUNT AS evidence for (so exh_val's "" stays
        # 0.0). Suppression on absence is a bug; corroboration on absence would
        # be a worse one.
        opp_mom = {"ACCELERATING": 1.0, "FLAT": 0.6, "DECELERATING": 0.25, "": 0.6}.get(mom, 0.6)
        trend_opp = 1.0 - (opp_adx * opp_mom) if opposed else 1.0
        trend_opp = max(0.0, min(1.0, trend_opp))

        age_decay = 0.5 ** (age_bars / SWEEP_HALFLIFE_BARS)                  # soft-necessary

        # -- corroborators (the exhaustion sea level) --------------------------
        # (1) rejection quality — depth MERGED with level quality, because the
        #     two are correlated and corroborators must be independent.
        depth_val = ramp(rej_pct, SWEEP_REJ_LO, SWEEP_REJ_HI)   # RE-SLOTTED from soft-necessary
        # Level quality from the swept pool's touch count. NOTE: LiquiditySweep
        # carries NO level_strength field — it is matched back to the pool by
        # price. A blind getattr(sweep, "level_strength", 0.0) would have
        # returned 0.0 forever with no error and no log, which is the failure
        # that hard-blocked the continuation trade (trend_engine v3.2, defect W).
        touches = 0
        for p in (getattr(liq_map, "pools", None) or []):
            if abs(getattr(p, "price", 0.0) - pool_px) < 1e-9:
                touches = getattr(p, "touch_count", 0)
                break
        level_val = ramp(float(touches), SWEEP_TOUCH_LO, SWEEP_TOUCH_HI)
        rejq_val  = (W_SWEEP_REJ_DEPTH * depth_val) + (W_SWEEP_REJ_LEVEL * level_val)

        # (2) trend exhaustion — the reversal thesis itself. "" earns nothing:
        #     if we cannot see whether the move is spent, we have no evidence
        #     that it is.
        exh_val = {"DECELERATING": 1.0, "FLAT": 0.5, "ACCELERATING": 0.0, "": 0.0}.get(mom, 0.0)

        # (3) v1.4 — SPENT-MOVE CONTEXT: was the thing being faded actually a
        #     MOVE? `exh_val` says the momentum is fading; it never asked what
        #     was fading. A rejection at a named level in dead air and the same
        #     rejection at the end of an extended trending or breakout-volatile
        #     leg scored identically, and only the second is the trade.
        #     `ambient` is the max of the TRENDING_BULL/BEAR and
        #     BREAKOUT_VOLATILE scores from THIS SAME TICK — computed a few
        #     lines above in score(), so this costs nothing and introduces no
        #     new input, no new state and no ordering dependency.
        #     A CORROBORATOR, NOT A NECESSARY: making it multiplicative would
        #     mean a sweep can only fire after a strong trend, which is
        #     narrower than the operator asked for. "Encouraged", not required.
        spent_val = ramp(float(ambient or 0.0), SWEEP_SPENT_CTX_LO, SWEEP_SPENT_CTX_HI)

        score = _combine(
            hard_vetoes=[veto_loc, veto_reclaim, veto_accept],
            soft_necessary=[trend_opp, age_decay],
            corroborators=[(W_SWEEP_REJQ, rejq_val), (W_SWEEP_EXH, exh_val),
                           (W_SWEEP_SPENT, spent_val)],
        )
        bd = {"named": named, "reclaimed": reclaimed, "closes_beyond": beyond,
              "kind": kind, "rev_dir": rev_dir,
              "rejection_pct": round(rej_pct, 4), "depth_val": round(depth_val, 3),
              "pool_price": round(pool_px, 4), "touch_count": touches,
              "level_val": round(level_val, 3), "rejq_val": round(rejq_val, 3),
              "trend_direction": direction, "adx": round(adx, 2),
              "momentum": mom, "opposed": opposed,
              "ambient": round(float(ambient or 0.0), 3),
              "spent_val": round(spent_val, 3),
              "opp_adx": round(opp_adx, 3), "opp_mom": opp_mom,
              "trend_opp": round(trend_opp, 3), "exh_val": exh_val,
              "age_bars": age_bars, "age_decay": round(age_decay, 3),
              "veto_loc": veto_loc, "veto_reclaim": veto_reclaim,
              "veto_accept": veto_accept,
              "w": {"rejq": W_SWEEP_REJQ, "exh": W_SWEEP_EXH,
                    "spent": W_SWEEP_SPENT},
              "score": round(score, 3)}
        return score, bd

    # -- public entry point -----------------------------------------------------

    def score(self, vol_state, trend_state, structure, liq_map,
              closes: Optional[List[float]] = None,
              atr: Optional[float] = None) -> ConfluenceResult:
        """
        Compute the instantaneous confluence vector. `closes` is the rolling
        1-min close window (≥ RANGE_WINDOW_BARS for the angle path); `atr` is the
        current ATR (VolatilityState.atr_current is the natural source). Both
        optional — absent, RANGING/COMPRESSION use reduced-ceiling fallbacks.
        """
        res = ConfluenceResult()

        tr_scores, tr_bd = self._trending(trend_state, structure)
        res.scores.update(tr_scores)
        res.breakdown["TRENDING"] = tr_bd

        res.scores[BREAKOUT_VOLATILE], res.breakdown[BREAKOUT_VOLATILE] = \
            self._breakout(vol_state, trend_state, closes)       # v1.3: closes for clearance
        res.scores[RANGING], res.breakdown[RANGING] = \
            self._ranging(vol_state, trend_state, closes, atr)
        res.scores[COMPRESSION], res.breakdown[COMPRESSION] = \
            self._compression(vol_state, closes, atr)
        res.scores[SWEEP_REVERSAL], res.breakdown[SWEEP_REVERSAL] = \
            self._sweep(liq_map, trend_state,                    # v1.3: trend_state wired in
                        ambient=max(                             # v1.4: spent-move context.
                            tr_scores.get(TRENDING_BULL, 0.0) or 0.0,   # Already computed
                            tr_scores.get(TRENDING_BEAR, 0.0) or 0.0,   # above this line —
                            res.scores[BREAKOUT_VOLATILE] or 0.0))      # no new inputs.

        return res

    def evidence(self, vol_state, trend_state, structure, liq_map,
                 closes: Optional[List[float]] = None,
                 atr: Optional[float] = None) -> Dict[str, Optional[float]]:
        """Convenience: bare score vector for direct hand-off to the integrator."""
        return self.score(vol_state, trend_state, structure, liq_map, closes, atr).evidence()


# ── Standalone smoke test (runs only when executed directly; no import side effects)
if __name__ == "__main__":                     # pragma: no cover
    from types import SimpleNamespace as NS

    def mk_closes(kind, n=30, base=100.0):
        import random; random.seed(3)
        if kind == "trend":
            return [base + 0.5 * i + random.gauss(0, 0.1) for i in range(n)]
        if kind == "range":  # two-sided rotation about a flat center (whole cycles)
            return [base + 1.2 * math.sin(i / 1.6) + random.gauss(0, 0.05) for i in range(n)]
        if kind == "coil":   # flat center, excursions fading toward the close
            return [base + 1.2 * math.sin(i / 1.6) * (1 - 0.85 * i / n) + random.gauss(0, 0.03)
                    for i in range(n)]
        return [base] * n

    def derive_atr(closes):
        # mean absolute step = the random-walk excursion scale the angle models;
        # self-consistent stand-in for ATR on close-only synthetic tape.
        d = [abs(closes[i] - closes[i - 1]) for i in range(1, len(closes))]
        return sum(d) / max(len(d), 1)

    sc = RegimeConfluenceScorer()

    def show(tag, vol, tr, st, lq, closes, atr=None):
        atr = derive_atr(closes[-RANGE_WINDOW_BARS:])
        r = sc.score(vol, tr, st, lq, closes, atr)
        # v1.3.2 — was k.split('_')[0][:5]: BULL and BEAR both printed "TREND"
        # in this self-test, the third instance of the same defect. Display
        # only, inside __main__ — no scoring path touched.
        from utils.regime_labels import label as _lab
        line = "  ".join(f"{_lab(k)}:{('None' if v is None else f'{v:.2f}')}"
                          for k, v in r.scores.items())
        print(f"{tag:10} {line}")
        return r

    # RANGING: flat center, active crossings, normal width
    vol_r = NS(atr_current=0.4, atr_avg_20=0.4, is_expanding=False, price_vs_bb="INSIDE",
               bb_width_pct=0.45, atr_state="STABLE", bb_state="NORMAL")
    tr_r  = NS(primary_adx=15, aligned_timeframes=1, total_timeframes=4,
               overall_direction="NEUTRAL", is_bullish=False, votes={})
    st_n  = NS(structure_sequence="MIXED")
    lq_0  = NS(recent_sweep=None, sweep_age_bars=999)
    r1 = show("RANGE", vol_r, tr_r, st_n, lq_0, mk_closes("range"), 0.4)

    # COMPRESSION: flat center, SQUEEZE, faded crossings, narrow width
    vol_c = NS(atr_current=0.2, atr_avg_20=0.4, is_expanding=False, price_vs_bb="INSIDE",
               bb_width_pct=0.08, atr_state="CONTRACTING", bb_state="SQUEEZE")
    r2 = show("COIL", vol_c, tr_r, st_n, lq_0, mk_closes("coil"), 0.2)

    # TRENDING_BULL: strong ADX, aligned, HH_HL, migrating center
    vol_t = NS(atr_current=0.6, atr_avg_20=0.4, is_expanding=True, price_vs_bb="ABOVE_UPPER",
               bb_width_pct=0.6, atr_state="EXPANDING", bb_state="EXPANDING")
    tr_t  = NS(primary_adx=40, aligned_timeframes=4, total_timeframes=4,
               overall_direction="BULLISH", is_bullish=True,
               votes={"5m": NS(momentum="ACCELERATING")})
    st_up = NS(structure_sequence="HH_HL")
    r3 = show("TREND_UP", vol_t, tr_t, st_up, lq_0, mk_closes("trend"), 0.6)

    # SWEEP: named zone, reclaimed, not accepted, fresh
    pool_pdh = NS(price=101.0, touch_count=4, name="PDH", is_named=True)
    lq_s = NS(pools=[pool_pdh],
              recent_sweep=NS(reclaimed=True, swept_named_level="PDH", kind="high_sweep",
                              pool_price=101.0, closes_beyond=0, rejection_pct=0.006),
              sweep_age_bars=1)
    r4 = show("SWEEP", vol_r, tr_r, st_n, lq_s, mk_closes("range"), 0.4)

    # ---- v1.3 PROOFS: the sweep sea level ------------------------------------
    # (A) THE PLTR COUNTER-EXAMPLE. Identical sweep evidence to r4, but the tape
    #     is a strong ACCELERATING uptrend and the reversal is SHORT. Pre-v1.3
    #     this scored 0.62 and the fleet bought a put into it.
    tr_pltr = NS(primary_adx=42, aligned_timeframes=4, total_timeframes=4,
                 overall_direction="BULLISH", is_bullish=True, primary_momentum="ACCELERATING",
                 votes={"5m": NS(momentum="ACCELERATING")})
    r5 = show("PLTR", vol_r, tr_pltr, st_n, lq_s, mk_closes("range"), 0.4)

    # (B) GENUINE EXHAUSTION. Same sweep, same uptrend, but the move is spent.
    tr_exh = NS(primary_adx=42, aligned_timeframes=4, total_timeframes=4,
                overall_direction="BULLISH", is_bullish=True, primary_momentum="DECELERATING",
                votes={"5m": NS(momentum="DECELERATING")})
    r6 = show("EXHAUST", vol_r, tr_exh, st_n, lq_s, mk_closes("range"), 0.4)

    print("\n-- SWEEP breakdowns (the sea level, visible) --")
    for tag, r in (("PLTR   ", r5), ("EXHAUST", r6)):
        b = r.breakdown[SWEEP_REVERSAL]
        print(f"  {tag} opposed={b['opposed']} trend_opp={b['trend_opp']} "
              f"rejq={b['rejq_val']} exh={b['exh_val']} -> {b['score']}")

    # sanity assertions
    assert r1.scores[RANGING] > r1.scores[COMPRESSION], "range should beat coil on range tape"
    assert r2.scores[COMPRESSION] > r2.scores[RANGING], "coil should beat range on coil tape"
    assert r3.scores[TRENDING_BULL] > 0.4 and r3.scores[RANGING] == 0.0, "trend up, range vetoed"
    assert r4.scores[SWEEP_REVERSAL] > 0.0, "fresh reclaimed named sweep should score"
    # v1.3 — the excavation's load-bearing claims
    assert r5.scores[SWEEP_REVERSAL] == 0.0, \
        "PLTR: short reversal into a strong ACCELERATING uptrend must be zeroed"
    assert r6.scores[SWEEP_REVERSAL] > r5.scores[SWEEP_REVERSAL], \
        "a spent trend must score far above an accelerating one on identical sweep evidence"
    assert r6.scores[SWEEP_REVERSAL] > 0.30, \
        "genuine exhaustion at a well-touched named level must accumulate real score"
    # no corroborator anywhere is a constant
    for _r, _k in ((r1, RANGING), (r2, COMPRESSION), (r6, SWEEP_REVERSAL)):
        assert "w" in _r.breakdown[_k], f"{_k} must publish its weights in bd"
    print("\nsmoke test OK — crossings axis separates RANGING/COMPRESSION; "
          "sweep is trend-aware and PLTR is structurally dead")
