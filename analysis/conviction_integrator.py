"""
options_trader_v3/analysis/conviction_integrator.py — Layer 2: persistence
(conviction-integrator) regime engine. — v2.3

v2.3 — 2026-08-10 — RGM.4: PER-REGIME COMMIT BAR. `theta_commit` was ONE number
        applied to scores living on DIFFERENT SCALES, and RANGING went dark
        because of it. Measured over 209,061 ticks: L1 sees a range on 24.2% of
        ticks — the same share as TRENDING_BULL's 23.5% — while L2 EMITS ranging
        on 2%. The bot was not failing to RECOGNISE range; it was failing to
        COMMIT it.
        83.2% of failed RANGING runs failed on the CEILING: peak EVIDENCE never
        reached 0.65 either, and conviction asymptotes to the evidence feeding
        it, so a faster tau_up could not have helped. RANGING evidence p50 0.322
        / p90 0.779 / max 0.982 — it NEVER pegs. TRENDING p90 1.000.
        ⚠️ TWO CORRECT DECISIONS PRODUCED IT. `room_s = ramp(bb_width_pct, 0.17,
        1.00)` is a SOFT-NECESSARY so it multiplies the whole score, and
        bb_width_pct p50 0.44 puts it at ~0.33 — exactly the observed peak
        evidence 0.322. Those bounds were widened (0.20 -> 1.00) to stop RANGING
        over-firing and it WORKED (dominance 44% -> 27%). F7 later made
        theta_commit mandatory for every challenger. Neither was wrong; nobody
        re-derived one against the other.
        ⚠️ THE INPUT IS NOT THE PROBLEM. bb_width_pct separates RANGING from
        COMPRESSION at 0.040 overlap — near-perfect. A travel/efficiency
        replacement was proposed, measured and REJECTED at 0.766: travel cannot
        even tell a range from a trend (p50 1.24 vs 1.19). Recorded so it is not
        re-proposed.
        0.60 IS DERIVED, NOT PREFERRED. tau_up 780 was fitted so commits land at
        ~17-19 bars — past the 12-15 bar window where TRENDS hold a false flat,
        inside the 24-29 where true ranges do. At RANGING's p90 evidence: 0.65
        -> 23.4 bars (LATE, outside the design), 0.60 -> 19.1 (in it), 0.50 ->
        13.3 (INSIDE the impostor window, rejected). This RESTORES the timing
        tau_up was fitted to produce. tau_up is UNTOUCHED.
        ⚠️ EXPECT A MODEST GAIN: 2.1% -> ~3.3% of RANGING runs committing. The
        residual is genuine — evidence p50 0.322 means most ranging argmax ticks
        are weak and SHOULD not commit.
        Kill switch: OT_L2_THETA_COMMIT_RANGING=0.65.

v2.2 — 2026-08-07 — SWEEP_REVERSAL LEAVES THE INTEGRATION SET (RGM.3).
        Operator: "sweep isn't a regime, it's a strategy — where did that even
        come from?" It came from being filed in the Regime enum despite
        MECHANICS.md heading its own section "EVENT OVERLAY". It is the only
        scorer with an age-decay soft-necessary (half-life 3 bars), so its score
        halves every three minutes and can never win an argmax against states
        that peg at 1.0 — measured 22% non-zero but p90 0.0, max 0.265,
        dominant 1%.
        `INTEGRATED_REGIMES` and `_TIEBREAK_ORDER` drop it; its RegimeParams row
        goes with them. The SCORER IS UNTOUCHED — SWP.1's dispatch gate reads
        that score and depends on it.
        ⚠️ THE TIE-BREAK HEAD MOVES from SWEEP_REVERSAL to BREAKOUT_VOLATILE, so
        all-zero ticks (4.2%, measured) stop being labelled with an event that
        did not occur.
        ⚠️ EVERY POOLED PER-REGIME STATISTIC IS NOW ON A DIFFERENT BASIS and is
        NOT comparable to the 12-session history banked before this.

v2.1 — 2026-08-06 — THE UNPROTECTED BRANCH IS CLOSED (RGM.1 / F7).

        THE DEFECT. v2.0's emission law protected the incumbent only while its
        conviction sat at or above theta_hold. Below it, `_emit` executed
        `self.incumbent = top_r` UNCONDITIONALLY, every tick — no commit bar,
        no displacement margin, no dwell. A challenger at conviction 0.05 took
        the label and could lose it again on the next tick. That contradicts
        this module's OWN design contract, four lines below: "Fast to
        recognize, slow to abandon… A single-tick flicker can never move the
        emitted label off a held regime." Below theta_hold it demonstrably
        could.

        MEASURED over 19 sessions / 523 symbol-days / 186,582 ticks
        (tests/emission_law_sweep.py v1.0): 8,083 of 8,345 label switches —
        **96.9%** — came from the unprotected branch. The commit threshold and
        the displacement margin governed 3.1%. Median incumbent conviction at
        the moment of a switch was **0.08**: the typical label change handed
        off between two near-zero beliefs. The incumbent sat below theta_hold
        on 50.3% of ticks, so this was not an edge case — it was half the
        session.

        IT ALSO EXPLAINS WHY A SWITCHING COST DID NOT WORK. `delta_displace`
        lives only in the protected branch, so the delta sweep was tuning a
        knob outside the path where the churn happened — right knob, wrong
        branch. That is the gradual-decay-no-cliff signature it produced.

        THE FIX. `protect_below_hold` (default True, env
        OT_L2_PROTECT_BELOW_HOLD=0 to restore v2.0) applies commit+margin in
        BOTH branches and HOLDS the incumbent when no challenger qualifies. A
        fading belief is still the best available belief; declining to switch
        is not the same as asserting the old label is strong, and conviction —
        which Layer 3 gates on — reports the weakness honestly either way.

        COLD START IS CARVED OUT. Protection ARMS only once some regime has
        reached theta_commit at least once (`self.armed`). Before that the book
        holds near-zero convictions and the argmax is the deterministic
        tiebreak head, SWEEP_REVERSAL — which is above zero on 4% of ticks.
        Protecting from tick 1 would pin the session to it. Plain argmax until
        armed; protection thereafter. (main.py independently gates on
        `not st.stale`, so the open is doubly covered.)

        SHADOW A/B, no behavioural cost. The state now also carries
        `shadow_regime` — what the OTHER law would have emitted from the same
        conviction vector — plus `switches` and `shadow_switches`. Both laws
        run on every tick, so a live session measures the divergence directly
        instead of inferring it from a counterfactual. Costs one dict lookup.

        NOT CHANGED: the integration law, the tau constants, staleness, the
        snapshot format, or theta_commit / theta_hold / delta_displace values.
        Only WHICH branch the displacement test runs in.

v2.0 — 2026-07-12 — PHASE 0 PORT to v3 (ROADMAP 0.1). Three changes:
        1. EMISSION LAW: always argmax. The UNKNOWN fallback is DELETED from
           emission — there is always an emitted best-fit label with graded
           conviction. Indecision is a LOW CONVICTION NUMBER, not a seventh
           label; Layer 3 gates on conviction, so an uncommitted read simply
           doesn't clear any trade's bar. The θ_hold/θ_commit/δ hysteresis
           band is KEPT for label stability: an incumbent above θ_hold is
           displaced only by a challenger that is committed-grade AND clearly
           better. Below θ_hold the incumbent loses privilege and emission
           follows plain argmax (which is usually still the fading incumbent —
           label continuity improves vs v1.0's drop-to-UNKNOWN).
        2. The STALE/gap state SURVIVES unchanged: a wall-clock gap > dt_max
           decays all conviction on tau_stale and flags stale=True until a
           full evidence vector is observed (or replay() warms the book).
           The no-trade condition for DATA FAULTS survives; the no-trade
           condition for INDECISION does not.
        3. EvidenceAdapter and its duplicated helpers/knobs are RETIRED.
           Layer 1 is analysis/regime_confluence.py (RegimeConfluenceScorer)
           and nothing else — resolves the two-Layer-1 collision (defects A/B).
           This module consumes the scorer's vector:
               scorer.score(vol, trend, structure, liq, closes, atr).evidence()
           → Dict[label, float∈[0,1] | None], keyed by the six regime labels.

v1.0 — 2026-07-09 — initial (options_trader_v2, shadow-mode). Leaky per-regime
        conviction integration: rising on agreement, decaying on disagreement,
        decay resistance scaled by banked conviction; argmax emission with
        hysteresis and displacement-by-competitor; dt-aware; snapshot/replay
        warm start. THRESHOLDS ARE PRIORS — re-fit from accumulated
        candle-logger tape before this engine drives the live classify path.

SHADOW-MODE: this module still drives nothing in the live loop. It exists to
run alongside the v1.3 classifier (both reading the shared store), logging
per tick: both labels, the full conviction vector, trigger, and stale flag —
the paired data that calibrates Phase-2/3 conviction bars.

Design contract (unchanged):
  • Fast to recognize, slow to abandon. Recognition is instantaneous at the
    evidence level; COMMITMENT and ABANDONMENT are durational.
  • A single-tick flicker can never move the emitted label off a held regime.
  • A held regime is displaced by a COMPETING regime accumulating its own
    conviction (belief yields to better belief).
  • Updates are dt-aware (wall-clock); irregular tick spacing is handled
    identically to regular cadence.
  • The integrator governs CLASSIFICATION ONLY. It must never sit in the path
    of price-based stops/targets/trails (exit_engine) — those stay
    instantaneous.
"""

import json
import logging
import math
import os
import tempfile
from dataclasses import dataclass, field, asdict


def _envf(name: str, default: float) -> float:
    """OT_-prefixed float knob. Local to this module — the integrator does not
    import config, deliberately, so that a replay can drive it standalone."""
    try:
        return float(os.getenv(f"OT_{name}", default))
    except (TypeError, ValueError):
        return default
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Regime labels: imported from the canonical Layer 1 when the repo is on
# path (single source of truth), with string fallbacks so this module stays
# importable in isolation (backtests, notebooks) — same guard pattern as
# regime_confluence v1.1.
try:
    from analysis.regime_confluence import (      # type: ignore
        TRENDING_BULL, TRENDING_BEAR, RANGING,
        BREAKOUT_VOLATILE, COMPRESSION, SWEEP_REVERSAL,
    )
except Exception:                                 # pragma: no cover - isolation
    TRENDING_BULL     = "TRENDING_BULL"
    TRENDING_BEAR     = "TRENDING_BEAR"
    RANGING           = "RANGING"
    BREAKOUT_VOLATILE = "BREAKOUT_VOLATILE"
    COMPRESSION       = "COMPRESSION"
    SWEEP_REVERSAL    = "SWEEP_REVERSAL"

# ── RGM.3 (v2.2) — SWEEP_REVERSAL IS NOT A REGIME AND NEVER WAS ──────────────
# `docs/MECHANICS.md:304` heads its own section "SWEEP_REVERSAL (EVENT OVERLAY —
# hard-veto triple x age-decay)". It is the only one of the six the
# documentation does not call a regime, and it is the only scorer carrying an
# AGE-DECAY soft-necessary: 0.5 ** (sweep_age_bars / 3). Its score HALVES every
# three minutes BY CONSTRUCTION.
#
# A decaying score entered into an argmax against persistent states that peg at
# 1.0 cannot win — not by tuning, structurally. Measured 2026-08-07 on an
# 11,231-tick replay: SWEEP was non-zero on 22% of ticks yet p90 = 0.0,
# max = 0.265, dominant on 1%. TRENDING_BULL: max 1.0, dominant 31%.
#
# So SWEEP leaves the INTEGRATION set. The SCORER STAYS EXACTLY AS IT IS —
# `regime_confluence._sweep` still runs every tick and its score still reaches
# `ctx["l1"].scores`, because SWP.1's dispatch gate now DEPENDS on it. Removing
# it from the integrator changes what can be EMITTED as a label, nothing about
# what is measured.
#
# ⚠️ THIS ALSO MOVES THE TIE-BREAK HEAD. SWEEP was first, so on an all-zero
# tick the emitted label WAS SWEEP_REVERSAL — the engine's least-supported
# regime won precisely the ticks where it knew nothing (4.2% of them, measured).
# The head is now BREAKOUT_VOLATILE, which is at least a state the tape can be
# in. A dead tick still deserves scrutiny, but it no longer names an event that
# did not happen.
INTEGRATED_REGIMES = (
    TRENDING_BULL, TRENDING_BEAR, RANGING,
    BREAKOUT_VOLATILE, COMPRESSION,
)

# Deterministic tie-break priority when convictions are exactly equal
# (mirrors the v1.x decision hierarchy; in practice ties are measure-zero).
_TIEBREAK_ORDER = {r: i for i, r in enumerate((
    BREAKOUT_VOLATILE, COMPRESSION,
    TRENDING_BULL, TRENDING_BEAR, RANGING,
))}


# ─── Parameters (PRIORS — recalibrate from multi-day tape) ────────────────────

@dataclass
class RegimeParams:
    """Per-regime integration constants (units: seconds)."""
    tau_up:   float   # rise time constant: C approaches evidence as 1-exp(-t/tau_up)
    tau_dn0:  float   # decay time constant floor (at zero banked conviction)
    lam:      float   # conviction-scaling of decay: tau_dn(C) = tau_dn0 * exp(lam*C)


@dataclass
class IntegratorParams:
    theta_commit: float = 0.65   # conviction needed to EMIT a regime (enter)
    # ── RGM.4 (2026-08-10) — PER-REGIME COMMIT BAR ───────────────────────────
    # theta_commit was ONE global number applied to scores living on DIFFERENT
    # SCALES, and that is why RANGING went dark. Measured over 209,061 ticks:
    #   L1 sees a range on 24.2% of ticks — essentially the same share as
    #   TRENDING_BULL's 23.5% — but L2 EMITS ranging on 2%.
    #   Of the RANGING argmax runs that failed to commit, 83.2% failed on the
    #   CEILING: peak EVIDENCE never reached 0.65 either, and conviction
    #   asymptotes to the evidence feeding it, so no tau change could help.
    #   RANGING peak evidence p50 0.322 / p90 0.779 / max 0.982 — it NEVER
    #   pegs. TRENDING_BULL p90 1.000. Same bar, different scales.
    # THE CAUSE IS AN INTERACTION, NOT A BAD CONSTANT. `room_s =
    # ramp(bb_width_pct, 0.17, 1.00)` is a SOFT-NECESSARY, so it multiplies the
    # whole score; bb_width_pct runs p50 0.44, putting room_s ~0.33 — and the
    # observed peak RANGING evidence is 0.322. That IS room_s. Those bounds were
    # widened deliberately (0.20 -> 1.00) to stop RANGING over-firing, and it
    # worked (dominance 44% -> 27%). Then F7 made theta_commit mandatory for
    # every challenger. Both changes were right; nobody re-derived one against
    # the other.
    # ⚠️ AND bb_width_pct IS NOT THE PROBLEM — it separates RANGING from
    # COMPRESSION at 0.040 overlap, near-perfect. A travel/efficiency
    # replacement was measured and REJECTED at 0.766 overlap: travel cannot even
    # tell a range from a trend (p50 1.24 vs 1.19). The input is right; the BAR
    # was wrong.
    # 0.60 IS DERIVED, NOT PREFERRED. tau_up 780 was fitted so sustained flat
    # evidence commits at ~17-19 bars — past the 12-15 bar window where TRENDS
    # hold a false-flat angle, inside the 24-29 bar window where true ranges do.
    # At RANGING's p90 evidence 0.779:  theta 0.65 -> 23.4 bars (LATE, past the
    # design), theta 0.60 -> 19.1 bars (the designed window), 0.57 -> 17.1,
    # 0.50 -> 13.3 bars (INSIDE the impostor window — rejected).
    # So 0.60 RESTORES THE TIMING THE tau WAS FITTED TO PRODUCE. It is not a
    # loosening; the effective bar had drifted late when the evidence scale
    # changed underneath it.
    # ⚠️ EXPECT A MODEST GAIN, NOT A TRANSFORMATION: the counterfactual on real
    # conviction values puts RANGING commits at 3.3% of runs against 2.1% today.
    # The residual is genuine — RANGING's evidence p50 is 0.322 and most argmax
    # ticks are weak, which SHOULD not commit. This fixes the scale mismatch and
    # nothing else.
    # ⚠️ tau_up IS UNTOUCHED, so the impostor protection is intact. Only the bar
    # moves. Empty dict = every regime uses the global value (kill switch).
    theta_commit_by_regime: Dict[str, float] = field(default_factory=lambda: {
        RANGING: _envf("L2_THETA_COMMIT_RANGING", 0.60),
    })

    def commit_bar(self, regime: Optional[str]) -> float:
        """The commit threshold for THIS regime. Falls back to the global."""
        if not regime:
            return self.theta_commit
        return self.theta_commit_by_regime.get(regime, self.theta_commit)
    theta_hold:   float = 0.45   # conviction needed to KEEP a held regime (hysteresis)
    delta_displace: float = 0.12 # margin a challenger needs over the incumbent
    dt_max:       float = 90.0   # gap > dt_max seconds ⇒ do not integrate; mark stale
    tau_stale:    float = 600.0  # decay constant while evidence is UNOBSERVABLE (None)
    # v2.1 — apply commit+margin in BOTH branches instead of only above
    # theta_hold. OT_L2_PROTECT_BELOW_HOLD=0 restores the v2.0 law exactly,
    # which is the kill switch and the A/B control.
    protect_below_hold: bool = field(
        default_factory=lambda: os.environ.get(
            "OT_L2_PROTECT_BELOW_HOLD", "1").strip().lower()
        not in ("0", "false", "no", "off"))

    per_regime: Dict[str, RegimeParams] = field(default_factory=lambda: {
        # Directional regimes: fast to commit (3 integrating ticks / ~60 s wall ⇒
        # roughly one confirmed candle — "one candle isn't a pattern" means
        # commitment needs a sustained read, not that recognition is slow).
        TRENDING_BULL:     RegimeParams(tau_up=40.0,  tau_dn0=25.0, lam=2.2),
        TRENDING_BEAR:     RegimeParams(tau_up=40.0,  tau_dn0=25.0, lam=2.2),
        BREAKOUT_VOLATILE: RegimeParams(tau_up=40.0,  tau_dn0=25.0, lam=2.2),
        # Sweeps are events: recognized fast, and must DIE fast when stale —
        # low lam so banked sweep conviction cannot squat over a breakout.
        # SWEEP_REVERSAL removed in v2.2 — it is an event overlay, not an
        # integrated regime. Its scorer is untouched; see RGM.3 above.
        # Compression builds over minutes.
        COMPRESSION:       RegimeParams(tau_up=180.0, tau_dn0=40.0, lam=2.0),
        # RANGING commits SLOWLY by design: on real tape, trends held a
        # false-flat angle for 12–15 bars while true ranges held 24–29.
        # tau_up is chosen so sustained flat evidence commits at ~17–19 bars —
        # past the impostor window, inside the genuine-range window. This is
        # the premium-selling gate; slow is correct.
        RANGING:           RegimeParams(tau_up=780.0, tau_dn0=60.0, lam=2.0),
    })


# ─── Output state ─────────────────────────────────────────────────────────────

@dataclass
class IntegratorState:
    regime:      str = ""                 # emitted regime (always-argmax; "" only before the first update)
    conviction:  float = 0.0              # conviction of the emitted regime
    convictions: Dict[str, float] = field(default_factory=dict)  # full vector
    trigger:     str = ""                 # why the emission changed this tick ("" if unchanged)
    stale:       bool = False             # True after a gap/restart until warmed
    # v2.1 — live A/B. `shadow_regime` is what the OTHER emission law would
    # have emitted from this same conviction vector; the counters are
    # cumulative per process. Observational only — nothing reads them to trade.
    shadow_regime:   str = ""
    switches:        int = 0
    shadow_switches: int = 0
    armed:           bool = False         # has any regime ever reached theta_commit?


# ─── The integrator ───────────────────────────────────────────────────────────

class ConvictionIntegrator:
    """
    Per-regime leaky integrator with conviction-scaled decay.

    Update law (per regime r, elapsed wall-clock dt, evidence e ∈ [0,1] or None):

        rise  (e ≥ C):  C ← C + (1 − exp(−dt/τ_up)) · (e − C)
        fall  (e < C):  C ← C − (1 − exp(−dt/τ_dn(C))) · (C − e)
                        with τ_dn(C) = τ_dn0 · exp(λ·C)
        stale (e None): C ← C · exp(−dt/τ_stale)

    Properties: C stays in [0,1]; for constant evidence C converges to e (it
    tracks evidence, it does not saturate past it); the decay time constant
    GROWS exponentially with banked conviction, so a 0.95 regime shrugs off
    the single-tick contradiction that tears down a 0.55 regime — the
    operator's rule, exactly, and the reason a flicker cannot move the label.

    Emission law (v2.0 — always argmax, hysteresis + displacement):
      1. If an incumbent is held and C_inc ≥ θ_hold: keep it — UNLESS some
         challenger has C ≥ θ_commit AND C ≥ C_inc + δ, in which case switch
         to the challenger (belief yields to better belief, not to noise).
      2. v2.1 — the SAME test applies below theta_hold once the book is
         armed: no qualified challenger means the incumbent is HELD. There is
         still NO UNKNOWN — indecision is a low conviction number on the
         held label, and Layer 3's per-trade bars are what refuse to trade it.
         Unarmed (cold book) or OT_L2_PROTECT_BELOW_HOLD=0 restores the v2.0
         behaviour: below theta_hold, emission follows plain argmax.

    θ_hold < θ_commit is the hysteresis band: harder to displace than to
    keep, so the emitted label cannot chatter across a single threshold
    while conviction is meaningful. The `stale` flag (data gap / unwarmed)
    is the ONLY hard no-trade marker this engine emits.
    """

    def __init__(self, params: Optional[IntegratorParams] = None):
        self.p = params or IntegratorParams()
        self.C: Dict[str, float] = {r: 0.0 for r in INTEGRATED_REGIMES}
        self.incumbent: Optional[str] = None
        self.last_ts: Optional[float] = None
        self.stale: bool = True   # unwarmed until first update/replay
        # v2.1 — protection arms on the first genuinely committed read; see the
        # cold-start note in the header.
        self.armed: bool = False
        self.switches: int = 0
        self.shadow: Optional[str] = None      # incumbent under the OTHER law
        self.shadow_switches: int = 0

    # ── core update ──────────────────────────────────────────────────────────

    def update(self, ts: float, evidence: Dict[str, Optional[float]]) -> IntegratorState:
        """
        Advance the integrator to wall-clock time `ts` (epoch seconds) with the
        instantaneous evidence vector, and return the emitted state.
        Missing keys in `evidence` are treated as None (unobservable), which is
        NOT the same as 0.0 (contradicted): unobservable bleeds slowly toward 0
        instead of being torn down — an engine outage must not shred conviction.
        """
        if self.last_ts is None:
            dt = 0.0
        else:
            dt = ts - self.last_ts
            if dt < 0:
                logger.warning("integrator: non-monotonic ts (dt=%.1fs); clamping to 0", dt)
                dt = 0.0
        gap = self.last_ts is not None and dt > self.p.dt_max
        self.last_ts = ts

        if gap:
            # A gap (restart, feed outage) means the tape moved while we were
            # blind. Do NOT pretend continuity: decay everything on the stale
            # constant and flag the state so the caller can warm-start via
            # replay() from the candle logger before trusting emissions.
            for r in INTEGRATED_REGIMES:
                self.C[r] *= math.exp(-dt / self.p.tau_stale)
            self.stale = True
            logger.warning("integrator: %.0fs gap — state marked STALE, replay recommended", dt)
        elif dt > 0:
            for r in INTEGRATED_REGIMES:
                e = evidence.get(r, None)
                c = self.C[r]
                rp = self.p.per_regime[r]
                if e is None:
                    c *= math.exp(-dt / self.p.tau_stale)
                else:
                    e = min(max(float(e), 0.0), 1.0)
                    if e >= c:
                        beta = 1.0 - math.exp(-dt / rp.tau_up)
                        c += beta * (e - c)
                    else:
                        tau_dn = rp.tau_dn0 * math.exp(rp.lam * c)
                        beta = 1.0 - math.exp(-dt / tau_dn)
                        c -= beta * (c - e)
                self.C[r] = min(max(c, 0.0), 1.0)
            if all(evidence.get(r) is not None for r in INTEGRATED_REGIMES):
                self.stale = False
        else:
            # dt == 0 (first sample): seed toward evidence at rise rate of one
            # nominal tick is NOT done — first sample only registers the clock.
            pass

        return self._emit()

    # ── emission ─────────────────────────────────────────────────────────────

    def _emit(self) -> IntegratorState:
        p = self.p
        trigger = ""

        # sorted challenger view: highest conviction first, deterministic ties
        ranked = sorted(
            self.C.items(),
            key=lambda kv: (-kv[1], _TIEBREAK_ORDER[kv[0]]),
        )
        top_r, top_c = ranked[0]

        # v2.1 — protection ARMS on the first committed-grade read anywhere in
        # the book. Before that the convictions are near zero and the argmax is
        # just the tiebreak head; holding it would pin the whole session to a
        # regime nothing has evidenced.
        # RGM.4 — arm on the CHALLENGER'S OWN bar, not the global one. Using
        # the global here would keep the book unarmed through exactly the
        # ranging sessions this change exists to let commit.
        if top_c >= p.commit_bar(top_r):
            self.armed = True

        prev_inc = self.incumbent
        protect = p.protect_below_hold and self.armed

        if self.incumbent is not None and (self.C[self.incumbent] >= p.theta_hold
                                           or protect):
            inc_c = self.C[self.incumbent]
            # displacement: a challenger must be COMMITTED and clearly better.
            # v2.1 — this test now also runs BELOW theta_hold. When nothing
            # qualifies the incumbent is HELD: a fading belief is still the
            # best available belief, and its conviction reports the weakness
            # honestly to Layer 3, which is what gates the trade.
            if (top_r != self.incumbent
                    and top_c >= p.commit_bar(top_r)     # RGM.4 — per-regime
                    and top_c >= inc_c + p.delta_displace):
                trigger = f"displaced {self.incumbent}({inc_c:.2f}) → {top_r}({top_c:.2f})"
                self.incumbent = top_r
            elif inc_c < p.theta_hold and not trigger:
                trigger = ""      # held below hold — the v2.1 behaviour change
        else:
            # v2.0 law, retained for the unarmed cold book and for
            # OT_L2_PROTECT_BELOW_HOLD=0: below theta_hold the incumbent loses
            # privilege and emission follows the best fit.
            if self.incumbent is not None and top_r != self.incumbent:
                trigger = (f"{self.incumbent} fell below hold "
                           f"({self.C[self.incumbent]:.2f} < {p.theta_hold}); "
                           f"argmax → {top_r}({top_c:.2f})")
            elif self.incumbent is None:
                trigger = f"argmax {top_r}({top_c:.2f})"
            self.incumbent = top_r

        if prev_inc is not None and self.incumbent != prev_inc:
            self.switches += 1

        # ── v2.1 shadow: the OTHER law, same conviction vector, no side effects
        prev_shadow = self.shadow
        if self.shadow is None:
            self.shadow = top_r
        elif p.protect_below_hold:
            # shadow = the OLD (v2.0) law
            s_c = self.C[self.shadow]
            if s_c >= p.theta_hold:
                if (top_r != self.shadow and top_c >= p.theta_commit
                        and top_c >= s_c + p.delta_displace):
                    self.shadow = top_r
            else:
                self.shadow = top_r
        else:
            # shadow = the NEW (v2.1) law, so the A/B reads the same either way
            s_c = self.C[self.shadow]
            if (top_r != self.shadow and top_c >= p.theta_commit
                    and top_c >= s_c + p.delta_displace):
                self.shadow = top_r
        if prev_shadow is not None and self.shadow != prev_shadow:
            self.shadow_switches += 1

        regime, conviction = self.incumbent, self.C[self.incumbent]

        return IntegratorState(
            regime=regime,
            conviction=conviction,
            shadow_regime=self.shadow or "",
            switches=self.switches,
            shadow_switches=self.shadow_switches,
            armed=self.armed,
            convictions=dict(self.C),
            trigger=trigger,
            stale=self.stale,
        )

    # ── warm start / persistence across restarts ─────────────────────────────
    # The v1.x classifier was memoryless, so restarts were free. An integrator
    # has state; a mid-session restart (the NVDA lesson) must not reset the
    # book to UNKNOWN for the RANGING commit window (~18 min). Two mechanisms:
    #   1. Periodic snapshot to disk; reload if fresh (< dt_max old).
    #   2. Otherwise replay recent evidence history (candle-logger tape) to
    #      rebuild conviction deterministically.

    def replay(self, samples: List[Tuple[float, Dict[str, Optional[float]]]]) -> IntegratorState:
        """Rebuild state by replaying (ts, evidence) samples in time order.
        Resets state first. Returns the final emitted state."""
        self.C = {r: 0.0 for r in INTEGRATED_REGIMES}
        self.incumbent = None
        self.last_ts = None
        self.stale = True
        out = IntegratorState()
        for ts, ev in samples:
            out = self.update(ts, ev)
        return out

    def to_dict(self) -> dict:
        return {
            "C": dict(self.C),
            "incumbent": self.incumbent,
            "last_ts": self.last_ts,
        }

    def save(self, path: str) -> None:
        """Atomic snapshot (write temp + rename) — safe against mid-write kills."""
        d = os.path.dirname(path) or "."
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".integrator_")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self.to_dict(), f)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def load(self, path: str, now_ts: float) -> bool:
        """Load a snapshot if it is fresh enough to trust (age ≤ dt_max).
        Returns True on success; on False the caller should replay()."""
        try:
            with open(path) as f:
                d = json.load(f)
            last_ts = d.get("last_ts")
            if last_ts is None or (now_ts - last_ts) > self.p.dt_max:
                return False
            self.C = {r: float(d["C"].get(r, 0.0)) for r in INTEGRATED_REGIMES}
            self.incumbent = d.get("incumbent")
            self.last_ts = float(last_ts)
            self.stale = False
            return True
        except (OSError, ValueError, KeyError, TypeError):
            return False

# ── Standalone validation suite (runs only when executed directly) ───────────
if __name__ == "__main__":                     # pragma: no cover
    import random, tempfile
    random.seed(7)
    TICK = 15.0
    ALL  = INTEGRATED_REGIMES

    def ev(**kw):
        base = {r: 0.0 for r in ALL}
        base.update(kw)
        return base

    fails = []
    def check(name, cond, detail=""):
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
        if not cond:
            fails.append(name)

    print("(1) no-UNKNOWN invariant — 500 random-evidence ticks")
    ig = ConvictionIntegrator(); t = 0.0; bad = 0
    for _ in range(500):
        t += TICK
        e = {r: (None if random.random() < 0.1 else random.random()) for r in ALL}
        s = ig.update(t, e)
        if s.regime not in ALL:
            bad += 1
    check("emitted label always one of the INTEGRATED set", bad == 0, f"{bad} violations")

    print("(2) convergence — constant RANGING evidence 0.8")
    ig = ConvictionIntegrator(); t = 0.0
    for _ in range(400):                       # 100 min of 15s ticks
        t += TICK
        s = ig.update(t, ev(RANGING=0.8))
    check("conviction tracks evidence (≈0.8, never past it)",
          0.75 <= s.convictions[RANGING] <= 0.8, f"C={s.convictions[RANGING]:.3f}")
    check("emits RANGING", s.regime == RANGING, s.regime)

    print("(3) flicker resistance — one contradicting tick vs a 0.9 incumbent")
    ig = ConvictionIntegrator(); t = 0.0
    for _ in range(200):
        t += TICK
        ig.update(t, ev(TRENDING_BULL=0.95))
    before = ig.update(t, ev(TRENDING_BULL=0.95))
    t += TICK
    flick = ig.update(t, ev(TRENDING_BULL=0.0, RANGING=1.0))     # single flicker
    check("label survives the flicker", flick.regime == TRENDING_BULL, flick.regime)
    check("conviction dents, not shatters",
          flick.conviction > 0.75 * before.conviction,
          f"{before.conviction:.2f} → {flick.conviction:.2f}")

    print("(4) displacement — sustained breakout evidence vs held trend")
    switched_at = None
    for i in range(60):
        t += TICK
        s = ig.update(t, ev(TRENDING_BULL=0.0, BREAKOUT_VOLATILE=0.95))
        if s.regime == BREAKOUT_VOLATILE and switched_at is None:
            switched_at = i + 1
            check("displacement trigger recorded", "displaced" in s.trigger, s.trigger)
    check("challenger displaces the incumbent", switched_at is not None,
          f"after {switched_at} ticks" if switched_at else "never")

    print("(5) below-hold — always-argmax, label continuity (v2.0 law)")
    ig = ConvictionIntegrator(); t = 0.0
    for _ in range(200):
        t += TICK
        ig.update(t, ev(COMPRESSION=0.9))
    labels = set()
    for _ in range(400):                       # let it fade on zero evidence
        t += TICK
        s = ig.update(t, ev())
        labels.add(s.regime)
    check("fading incumbent keeps the label via argmax (no drop-out)",
          labels == {COMPRESSION}, str(labels))
    check("conviction reports the fade honestly", s.conviction < 0.20,
          f"C={s.conviction:.3f}")

    print("(6) gap → STALE survives; replay warms")
    ig = ConvictionIntegrator(); t = 0.0
    for _ in range(100):
        t += TICK
        ig.update(t, ev(RANGING=0.8))
    s = ig.update(t + 600.0, ev(RANGING=0.8))  # 10-min gap
    check("gap flags stale", s.stale is True)
    samples = []
    tt = t + 600.0
    for _ in range(100):
        tt += TICK
        samples.append((tt, ev(RANGING=0.8)))
    s = ig.replay(samples)
    check("replay clears stale + recommits", s.stale is False and s.regime == RANGING,
          f"stale={s.stale} regime={s.regime}")

    print("(7) snapshot persistence — fresh load restores, old load refuses")
    path = tempfile.mktemp(suffix=".json")
    ig.save(path)
    ig2 = ConvictionIntegrator()
    check("fresh snapshot loads", ig2.load(path, now_ts=ig.last_ts + 30.0) is True)
    check("state restored", abs(ig2.C[RANGING] - ig.C[RANGING]) < 1e-9
          and ig2.incumbent == ig.incumbent)
    ig3 = ConvictionIntegrator()
    check("stale snapshot refused (caller must replay)",
          ig3.load(path, now_ts=ig.last_ts + 9999.0) is False)

    print("(8) Layer-1 handshake — consumes RegimeConfluenceScorer's vector")
    try:
        from analysis.regime_confluence import RegimeConfluenceScorer, REGIMES as L1
        check("label sets identical", set(L1) == set(ALL))
    except Exception as e:
        print(f"  [skip] repo Layer 1 not importable here: {e}")

    print()
    print("ALL PASS — v2.0 emission law verified: always-argmax, hysteresis kept,"
          if not fails else f"{len(fails)} FAILURES: " + "; ".join(fails))
    if not fails:
        print("stale survives, UNKNOWN eliminated")
