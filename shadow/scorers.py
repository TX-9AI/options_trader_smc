"""
shadow/scorers.py — per-pattern conviction scorers (shadow: sweep-reversal first).
v1.0 — 2026-07-09 — initial release.

Each pattern owns its own completeness checklist and composes registry
conjunctions into a 0->1 conviction score. Different patterns are different
recipes over the SAME primitives.

SweepReversalPrecursorScorer models the reversal as a staged sequence:
    APPROACH -> THRUST -> EXHAUSTION -> REJECTION -> RECLAIM
  conviction = (weighted sum of assembled stages) x coherence multiplier
  - coherence: stages arriving IN ORDER and CLOSE IN TIME reinforce;
    scattered / out-of-order / stale pieces don't.
  - decay: completed stages expire (STAGE_TTL_S) as a forming setup goes stale.
  - invalidation collapse: ACCEPTANCE through the level (clean_break) means
    it's a breakout, not a reversal ==> full reset.

SELF-GATING IS ON ELIGIBILITY (position), NEVER ON REGIME. score() returns:
  None  -> ineligible: no named level within range; the pattern CANNOT form here
  0.0   -> eligible: the pattern COULD form here, nothing has assembled yet
These are logged distinctly (null vs 0) — they mean different things.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from shadow.primitives import Primitives
from shadow import registry as R

# ── Calibration knobs ─────────────────────────────────────────────────────────
STAGE_TTL_S        = 900.0   # a completed stage expires after this long
COHERENCE_WINDOW_S = 600.0   # full coherence when the assembled span fits inside this
MIN_COHERENCE      = 0.35    # floor of the coherence multiplier (ordered but slow)
ORDER_PENALTY      = 0.50    # multiplier hit when stages assembled out of order

STAGES  = ("APPROACH", "THRUST", "EXHAUSTION", "REJECTION", "RECLAIM")
WEIGHTS = {"APPROACH": 0.10, "THRUST": 0.20, "EXHAUSTION": 0.25,
           "REJECTION": 0.25, "RECLAIM": 0.20}


@dataclass
class ScoreResult:
    scorer: str
    eligible: bool
    conviction: Optional[float]          # None when ineligible
    direction: Optional[str] = None      # 'long' / 'short' (would-be trade direction)
    level_name: Optional[str] = None
    level_price: Optional[float] = None
    stages: Dict[str, bool] = field(default_factory=dict)
    invalidated: bool = False
    notes: str = ""


@dataclass
class _StageHit:
    stage: str
    at: float      # epoch seconds


class SweepReversalPrecursorScorer:
    """Stateful per symbol. call score() once per tick with fresh primitives."""

    name = "sweep_reversal_precursor"

    def __init__(self):
        self._hits: List[_StageHit] = []
        self._level_key: Optional[str] = None    # 'name:price' anchoring the sequence
        self._anchor_toward: Optional[int] = None  # level side AT SEQUENCE START
        self._penetrated: bool = False           # has THIS sequence poked through?

    # ────────────────────────────────────────────────────────────────────────
    def score(self, prim: Primitives, liq_map=None,
              now_s: Optional[float] = None) -> ScoreResult:
        now_s = now_s if now_s is not None else time.time()

        ctx = R.nearest_eligible_level(prim)
        if ctx is None:
            # ineligible here — do NOT decay/reset state; price may return
            return ScoreResult(scorer=self.name, eligible=False, conviction=None,
                               notes="no named level in range")

        key = f"{ctx.level.name}:{ctx.level.price:.4f}"
        if key != self._level_key:
            self._reset()                        # sequence anchors to ONE level
            self._level_key = key
            self._anchor_toward = ctx.toward
        # CRITICAL: use the toward-side captured at SEQUENCE START. When price
        # penetrates the level, nearest_eligible_level reports it on the other
        # side; recomputing toward would invert every check and make a breakout
        # thrust read as rejection+reclaim of the now-behind level.
        ctx = R.LevelContext(level=ctx.level, toward=self._anchor_toward)

        # invalidation FIRST: acceptance through the level ==> breakout, collapse
        if R.clean_break(prim, ctx, liq_map):
            self._reset()
            return ScoreResult(scorer=self.name, eligible=True, conviction=0.0,
                               direction=self._direction(ctx),
                               level_name=ctx.level.name, level_price=ctx.level.price,
                               invalidated=True, notes="acceptance through level (breakout)")

        # decay: expire stale stage completions
        self._hits = [h for h in self._hits if now_s - h.at <= STAGE_TTL_S]

        # evaluate stage conditions this tick (registry conjunctions).
        # A sweep BY DEFINITION requires PENETRATION (location + penetration +
        # rejection, per liquidity_mapper v1.3) — so REJECTION and RECLAIM only
        # count once this sequence has actually poked through the level.
        if R.penetrated(prim, ctx):
            self._penetrated = True
        cond = {
            "APPROACH":   True,   # eligibility itself IS the approach precondition
            "THRUST":     R.thrust_into_level(prim, ctx),
            "EXHAUSTION": R.exhaustion_at_level(prim, ctx),
            "REJECTION":  self._penetrated and
                          (R.rejection_velocity_flip(prim, ctx) or
                           R.mapper_sweep_at(prim, ctx, liq_map)),
            "RECLAIM":    self._penetrated and R.reclaim_held(prim, ctx, liq_map),
        }
        done = {h.stage for h in self._hits}
        for st in STAGES:
            if cond[st] and st not in done:
                self._hits.append(_StageHit(stage=st, at=now_s))
                done.add(st)

        # RECLAIM without a registered REJECTION/EXHAUSTION is just price sitting
        # inside — only count it once something upstream has assembled.
        if "RECLAIM" in done and not ({"REJECTION", "EXHAUSTION"} & done):
            self._hits = [h for h in self._hits if h.stage != "RECLAIM"]
            done.discard("RECLAIM")

        base = sum(WEIGHTS[s] for s in done)
        conviction = base * self._coherence(now_s) if base > 0 else 0.0

        return ScoreResult(
            scorer=self.name, eligible=True,
            conviction=round(min(max(conviction, 0.0), 1.0), 4),
            direction=self._direction(ctx),
            level_name=ctx.level.name, level_price=ctx.level.price,
            stages={s: (s in done) for s in STAGES},
            notes=f"{len(done)}/5 stages @ {ctx.level.name}",
        )

    # ────────────────────────────────────────────────────────────────────────
    def _coherence(self, now_s: float) -> float:
        """Order x freshness. In-order stages arriving close in time reinforce;
        out-of-order or aging assemblies are discounted."""
        if not self._hits:
            return 0.0
        by_time = sorted(self._hits, key=lambda h: h.at)
        canonical = [s for s in STAGES if s in {h.stage for h in by_time}]
        ordered = [h.stage for h in by_time] == canonical
        span = by_time[-1].at - by_time[0].at
        freshness = max(0.0, 1.0 - max(0.0, span - COHERENCE_WINDOW_S) /
                        max(STAGE_TTL_S - COHERENCE_WINDOW_S, 1.0))
        mult = max(MIN_COHERENCE, freshness)
        if not ordered:
            mult *= ORDER_PENALTY
        return mult

    @staticmethod
    def _direction(ctx: R.LevelContext) -> str:
        """Sweep of a HIGH (level above) reverses DOWN -> would-be short/put;
        sweep of a LOW (level below) reverses UP -> would-be long/call."""
        return "short" if ctx.toward > 0 else "long"

    def _reset(self):
        self._hits = []
        self._level_key = None
        self._anchor_toward = None
        self._penetrated = False


def build_scorers() -> list:
    """All shadow scorers to run per tick. One for now, by design (build order:
    validate the best-understood pattern before adding recipes)."""
    return [SweepReversalPrecursorScorer()]
