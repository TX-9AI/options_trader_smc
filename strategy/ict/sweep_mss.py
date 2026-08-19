"""
strategy/ict/sweep_mss.py — Liquidity Sweep + MSS/CHoCH standalone (rank 4). v1.0
v1.0 — 2026-08-18 — INITIAL (ICT setup suite, HANDOFF_FABLE_ICT_SETUPS §2.2.4).

SPEC (operator corrects, then it is law):
  TRIGGER SEQUENCE: sweep at a KEY level (prior day H/L, equal H/L, session
    extreme) -> CHoCH/BOS against the raid -> enter on the reclaim, morning
    session-weighted. Bread-and-butter reversal/continuation trigger.
  INVALIDATION: acceptance back through the reclaimed level.
  TARGET: draw on liquidity on the profit side.
  SCORE ACCUMULATION: sweep(req) -> shift(req); displacement, key-level
    naming, session filter and draw graded. Every required input is
    AVAILABLE TODAY — this is the first setup that can complete its whole
    chain on the current core surface, which makes it the natural first
    harness-validation candidate (§3.5: operator writes the pass condition
    before the run; OT_ICT_ICTSWEEPMSS_VALIDATED arms it after).
  SIZE: scoring.size_fraction — §2.1 mapping.

RELATION TO THE LEGACY SweepReversal: same underlying event, DIFFERENT
model. SweepReversal is confirmatory (mapper-confirmed sweep + its own
gate stack); this scores the raid WHILE IT FORMS and expresses honest
sub-certainty. Both may coexist during the comparison window; dispatch
rank keeps this one first on the SMC box.
"""

from __future__ import annotations

from typing import Optional, Tuple

from strategy.ict.context import ICTContext
from strategy.ict.scoring import Component, SetupScore
from strategy.ict.setup_base import (
    ICTSetup, clamp01, sweep_evidence, shift_evidence, displacement_evidence,
    zone_alignment, draw_agreement, infer_thesis, to_trade_direction,
)


class SweepMSSSetup(ICTSetup):
    NAME = "ICTSweepMSS"
    RANK = 4
    DEBIT_DIRECTIONAL = True

    def evaluate(self, ictx: ICTContext) -> SetupScore:
        thesis = infer_thesis(ictx)
        sc = SetupScore(setup=self.NAME, direction=to_trade_direction(thesis))
        if not thesis:
            return sc

        sv, snote = sweep_evidence(ictx, thesis)
        sc.components.append(Component("dir:sweep", 2.5, sv, required=True,
                                       floor=0.6, reason=snote))
        sc.components.append(Component("dir:shift", 2.5,
                                       shift_evidence(ictx, thesis),
                                       required=True, floor=0.7))
        sc.components.append(Component("dir:displacement", 1.5,
                                       displacement_evidence(ictx, thesis)))

        named = bool((ictx.recent_sweep or {}).get("level_name")) or bool(
            (ictx.raid or {}).get("level_name"))
        sc.components.append(Component("key_level", 1.0, 1.0 if named else 0.0))

        mo = ictx.minutes_since_open
        mo_avail = mo >= 0
        sc.components.append(Component(
            "session", 0.5,
            clamp01(1.0 - max(0.0, mo - 150.0) / 150.0) if mo_avail else 0.0,
            available=mo_avail, reason="" if mo_avail else "clock unavailable"))

        za_avail = ictx.position_pct >= 0
        sc.components.append(Component("zone", 0.5,
                                       zone_alignment(ictx, thesis),
                                       available=za_avail,
                                       reason="" if za_avail else "no dealing range"))
        sc.components.append(Component("dir:draw", 1.0,
                                       draw_agreement(ictx, thesis)))
        return sc

    def _levels(self, ictx: ICTContext, sc: SetupScore
                ) -> Optional[Tuple[float, float, float]]:
        raid = ictx.raid or {}
        sw = ictx.recent_sweep or {}
        stop = raid.get("wick_extreme") or sw.get("sweep_price")
        target = ictx.draw_above if sc.direction == "long" else ictx.draw_below
        if not stop or not target or ictx.price <= 0:
            return None
        return (ictx.price, float(stop), float(target))
