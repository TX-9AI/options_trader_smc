"""
strategy/ict/silver_bullet.py — ICT Silver Bullet (rank 1). v1.0
v1.0 — 2026-08-18 — INITIAL (ICT setup suite, HANDOFF_FABLE_ICT_SETUPS §2.2.1).

SPEC (operator corrects, then it is law — handoff §5.3):
  TRIGGER SEQUENCE, in order, all inside the window (09:45–11:30 ET, prior,
  env OT_ICT_SB_START/OT_ICT_SB_END):
    1. liquidity sweep of an unswept pool (live raid preferred — anticipation)
    2. displacement / MSS in the reversal direction
    3. entry on retrace into the FVG CREATED INSIDE THE WINDOW by that leg
  INVALIDATION: acceptance beyond the raid wick extreme (stop level), or a
    CHoCH against the thesis post-dating the setup (core revocation covers
    the latter at the choke point).
  TARGET: the draw on liquidity on the profit side (nearest untapped pool).
  SCORE ACCUMULATION: window(req) -> sweep(req) -> shift(req) -> FVG
    approach(req) accumulate continuously; displacement, zone and draw are
    graded confluence. A 3-of-4 state journals as FORMING with its score.
  SIZE: scoring.size_fraction(displacement_sd, bias_quality) — §2.1 mapping.
  DISPATCH: shares the slot with ORB, SB ranks first, preemption journaled
    (handoff §4.2 decision — the wiring is main.py's, SPEC G6).

CORE GAPS THAT BIND HERE: the FVG-formed-inside-window rule needs FVG birth
stamps (G1) — that component is REQUIRED and UNAVAILABLE today, so Silver
Bullet can reach FORMING and journal near-misses but CANNOT fire until the
core delivers G1. That is deliberate: firing on an FVG of unknown
provenance is exactly the kind of unstated assumption this fork exists to
remove.
"""

from __future__ import annotations

from typing import Optional, Tuple

from strategy.ict.context import ICTContext, G1_SB_WINDOW
from strategy.ict.scoring import Component, SetupScore
from strategy.ict.setup_base import (
    ICTSetup, sweep_evidence, shift_evidence, displacement_evidence,
    fvg_entry_evidence, zone_alignment, draw_agreement, infer_thesis,
    to_trade_direction,
)


class SilverBulletSetup(ICTSetup):
    NAME = "ICTSilverBullet"
    RANK = 1
    DEBIT_DIRECTIONAL = True

    def evaluate(self, ictx: ICTContext) -> SetupScore:
        thesis = infer_thesis(ictx)
        sc = SetupScore(setup=self.NAME, direction=to_trade_direction(thesis))
        if not thesis:
            return sc

        # 1 — window (required)
        win_avail = ictx.sb_window is not None
        sc.components.append(Component(
            "window", 2.0, 1.0 if ictx.sb_window else 0.0,
            available=win_avail, required=True, floor=1.0,
            reason="" if win_avail else "clock unavailable"))

        # 2 — sweep (required, directional)
        sv, snote = sweep_evidence(ictx, thesis)
        sc.components.append(Component("dir:sweep", 2.0, sv, required=True,
                                       floor=0.6, reason=snote))

        # 3 — shift / MSS (required, directional)
        sc.components.append(Component("dir:shift", 2.0,
                                       shift_evidence(ictx, thesis),
                                       required=True, floor=0.7))

        # 4 — FVG entry (required) + in-window provenance (required, G1)
        fv, _g = fvg_entry_evidence(ictx, thesis)
        sc.components.append(Component("fvg_entry", 2.0, fv, required=True,
                                       floor=0.6))
        births_avail = ictx.fvg_births is not None
        sc.components.append(Component(
            "fvg_in_window", 1.0,
            0.0,  # value computed only once G1 lands
            available=births_avail, required=True, floor=1.0,
            reason="" if births_avail else G1_SB_WINDOW))

        # confluence
        sc.components.append(Component("dir:displacement", 1.5,
                                       displacement_evidence(ictx, thesis)))
        za = zone_alignment(ictx, thesis)
        sc.components.append(Component("zone", 0.5, za,
                                       available=ictx.position_pct >= 0,
                                       reason="" if ictx.position_pct >= 0
                                       else "no dealing range"))
        sc.components.append(Component("dir:draw", 1.0,
                                       draw_agreement(ictx, thesis)))
        return sc

    def _levels(self, ictx: ICTContext, sc: SetupScore
                ) -> Optional[Tuple[float, float, float]]:
        raid = ictx.raid or {}
        long_side = sc.direction == "long"
        stop = raid.get("wick_extreme") or (
            ictx.displacement_origin if ictx.displacement_origin else None)
        target = ictx.draw_above if long_side else ictx.draw_below
        if not stop or not target or ictx.price <= 0:
            return None
        return (ictx.price, float(stop), float(target))
