"""
shadow/registry.py — registry of named "completeness" conjunctions.
v1.0 — 2026-07-09 — initial release.

A PASSIVE library of reusable sub-checks over the shared primitives. Always
available; every scorer reads it independently and composes its own recipe.
Deliberately NO regime-gating here — these are pattern-agnostic building
blocks, and gating a precursor library behind the regime it helps detect
would reintroduce the late-entry chicken-and-egg.

Every function is pure: (Primitives, [LiquidityMap]) -> bool / small struct.
Calibration constants are placeholders to be tightened from shadow sessions.
"""

from dataclasses import dataclass
from typing import Optional

from shadow.primitives import Primitives, LevelRef

# ── Calibration knobs ─────────────────────────────────────────────────────────
ELIGIBLE_DIST_ATR   = 1.5    # "near a level" = within this many ATRs
AT_LEVEL_DIST_ATR   = 0.35   # "AT the level" for exhaustion/rejection checks
THRUST_VELOCITY     = 1.5    # |normalized velocity| that counts as a thrust
EXHAUST_CONTRACT    = 0.6    # |v| must fall to <= this fraction of previous |v|
REJECT_VELOCITY     = 0.75   # opposing |velocity| that counts as active rejection
ACCEPT_CLOSES       = 2      # closes through the level ==> acceptance (breakout)
ACCEPT_VELOCITY     = 1.25   # through-level velocity that counts toward acceptance
ACCEPT_DEPTH_ATR    = 0.50   # ...but only once price is THIS far beyond the level:
                             # the sweep's own poke has high through-velocity for a
                             # tick; acceptance means price is TRAVELLING, not poking


@dataclass
class LevelContext:
    """Which named level a check is being evaluated against."""
    level: LevelRef
    toward: int    # +1 if the level is above price, -1 if below


def nearest_eligible_level(prim: Primitives) -> Optional[LevelContext]:
    """POSITION eligibility: the nearest named level within ELIGIBLE_DIST_ATR.
    Returns None when NO pattern anchored to a named level can form here —
    scorers log null (not 0) in that case; the two mean different things."""
    candidates = []
    for ref in (prim.nearest_named_above, prim.nearest_named_below):
        if ref is not None and (ref.dist_atr <= ELIGIBLE_DIST_ATR or
                                (prim.atr <= 0 and ref.dist_pct <= 0.005)):
            candidates.append(ref)
    if not candidates:
        return None
    ref = min(candidates, key=lambda l: l.dist_pct)
    return LevelContext(level=ref, toward=+1 if ref.side == "above" else -1)


def at_level(prim: Primitives, ctx: LevelContext) -> bool:
    """Price is effectively AT the level (or has poked past it)."""
    if ctx.level.dist_atr <= AT_LEVEL_DIST_ATR and prim.atr > 0:
        return True
    return penetrated(prim, ctx)


def penetrated(prim: Primitives, ctx: LevelContext) -> bool:
    """Price is currently on the FAR side of the level (poked through)."""
    if ctx.toward > 0:
        return prim.price > ctx.level.price
    return prim.price < ctx.level.price


def thrust_into_level(prim: Primitives, ctx: LevelContext) -> bool:
    """Elevated velocity DIRECTED AT the level."""
    v = prim.velocity
    if v is None:
        return False
    return abs(v) >= THRUST_VELOCITY and (v > 0) == (ctx.toward > 0)


def exhaustion_at_level(prim: Primitives, ctx: LevelContext) -> bool:
    """Velocity CONTRACTING while at/through the level. Contraction without
    pretext is not information; contraction AT a level is a rejection forming.
    (The 'AND price held inside' part is reclaim_held's job.)"""
    v, vp = prim.velocity, prim.velocity_prev
    if v is None or vp is None or abs(vp) < 0.25:
        return False
    if not at_level(prim, ctx):
        return False
    return abs(v) <= abs(vp) * EXHAUST_CONTRACT


def rejection_velocity_flip(prim: Primitives, ctx: LevelContext) -> bool:
    """Velocity has FLIPPED and is now running AWAY from the level with force —
    the early accept/reject discriminator: a sweep decelerates and reverses at
    a level; a breakout accelerates through it."""
    v = prim.velocity
    if v is None:
        return False
    return abs(v) >= REJECT_VELOCITY and (v > 0) != (ctx.toward > 0)


def reclaim_held(prim: Primitives, ctx: LevelContext, liq_map=None) -> bool:
    """Price back on the NEAR side of the level and holding. Confirmed by the
    liquidity mapper's own sweep verdict when one exists at this level."""
    back_inside = not penetrated(prim, ctx)
    if not back_inside:
        return False
    sweep = getattr(liq_map, "recent_sweep", None) if liq_map is not None else None
    if sweep is not None and _sweep_is_of(sweep, ctx):
        return bool(getattr(sweep, "reclaimed", False))
    # No mapper-confirmed sweep yet: forming-bar evidence — price inside and the
    # forming bar closing on the near side of its own range in the reclaim direction.
    if prim.intrabar_pos is None:
        return True
    return prim.intrabar_pos <= 0.5 if ctx.toward > 0 else prim.intrabar_pos >= 0.5


def clean_break(prim: Primitives, ctx: LevelContext, liq_map=None) -> bool:
    """ACCEPTANCE through the level ==> this is a breakout, not a sweep.
    Reversal scorers treat this as INVALIDATION (score collapse)."""
    sweep = getattr(liq_map, "recent_sweep", None) if liq_map is not None else None
    if sweep is not None and _sweep_is_of(sweep, ctx):
        if getattr(sweep, "closes_beyond", 0) >= ACCEPT_CLOSES:
            return True
    v = prim.velocity
    if v is not None and penetrated(prim, ctx):
        depth = abs(prim.price - ctx.level.price)
        deep = prim.atr > 0 and depth / prim.atr >= ACCEPT_DEPTH_ATR
        if deep and abs(v) >= ACCEPT_VELOCITY and (v > 0) == (ctx.toward > 0):
            return True
    return False


def mapper_sweep_at(prim: Primitives, ctx: LevelContext, liq_map=None) -> bool:
    """The liquidity mapper has itself registered a sweep of THIS named level."""
    sweep = getattr(liq_map, "recent_sweep", None) if liq_map is not None else None
    return sweep is not None and _sweep_is_of(sweep, ctx)


def _sweep_is_of(sweep, ctx: LevelContext) -> bool:
    name = getattr(sweep, "swept_named_level", "") or ""
    if name and name == ctx.level.name:
        return True
    pool = getattr(sweep, "pool_price", 0.0) or 0.0
    return pool > 0 and abs(pool - ctx.level.price) / ctx.level.price < 0.001
