"""
strategy/ict/judas_po3.py — Judas Swing + Power of Three / AMD (rank 2). v1.0
v1.0 — 2026-08-18 — INITIAL (ICT setup suite, HANDOFF_FABLE_ICT_SETUPS §2.2.2).

SPEC (operator corrects, then it is law):
  TRIGGER SEQUENCE:
    1. accumulation reference established (Asia/pre-market range; true opens)
    2. MANIPULATION: engineered false break — an early-session raid of a
       NAMED pool (PDH/PDL, Asia/London/overnight session extreme)
    3. structure shift AGAINST the manipulation leg (the distribution turn)
    4. enter the DISTRIBUTION leg, same session, morning-weighted
  INVALIDATION: acceptance back beyond the manipulation extreme.
  TARGET: opposing session liquidity — the draw on the profit side.
  SCORE ACCUMULATION: named-raid(req) -> shift(req) -> displacement graded;
    session-phase weighting (first ~2h of RTH); true-open position graded
    (price trading at premium to the true open = bearish distribution
    context, mirrored for discount — Judas logic).
  SIZE: scoring.size_fraction — §2.1 mapping.

CORE GAPS THAT BIND HERE: AMD phase state + midnight/08:30 true opens (G5)
need the 1-HOUR EXT stream (FEED.2) read core-side. DEGRADED MODE today:
the 09:30 true open (computable from the RTH frame) carries the true-open
component at reduced weight-availability; the named pools themselves are
ALREADY available (liquidity_mapper names Asia/London/PDH/PDL), so the
manipulation leg is detectable now. G5 raises completeness; it does not
gate firing — the required chain is raid + shift, both live today.
"""

from __future__ import annotations

from typing import Optional, Tuple

from strategy.ict.context import ICTContext, G5_AMD_STATE
from strategy.ict.scoring import Component, SetupScore
from strategy.ict.setup_base import (
    ICTSetup, clamp01, sweep_evidence, shift_evidence, displacement_evidence,
    draw_agreement, infer_thesis, to_trade_direction,
)

_MORNING_FULL_MIN = 120.0    # full session-phase credit inside first 2h. Prior.


class JudasPO3Setup(ICTSetup):
    NAME = "ICTJudasPO3"
    RANK = 2
    DEBIT_DIRECTIONAL = True

    def evaluate(self, ictx: ICTContext) -> SetupScore:
        thesis = infer_thesis(ictx)
        sc = SetupScore(setup=self.NAME, direction=to_trade_direction(thesis))
        if not thesis:
            return sc

        # manipulation: a raid, and specifically of a NAMED level
        sv, snote = sweep_evidence(ictx, thesis)
        named = bool((ictx.recent_sweep or {}).get("level_name")) or bool(
            (ictx.raid or {}).get("level_name"))
        sc.components.append(Component("dir:named_raid", 2.5,
                                       sv if named else sv * 0.5,
                                       required=True, floor=0.5,
                                       reason=snote or "unnamed pool"))

        # distribution turn
        sc.components.append(Component("dir:shift", 2.0,
                                       shift_evidence(ictx, thesis),
                                       required=True, floor=0.7))
        sc.components.append(Component("dir:displacement", 1.5,
                                       displacement_evidence(ictx, thesis)))

        # session phase — Judas is a morning model
        mo = ictx.minutes_since_open
        ph_avail = mo >= 0
        sc.components.append(Component(
            "session_phase", 1.0,
            clamp01(1.0 - max(0.0, mo - _MORNING_FULL_MIN) / _MORNING_FULL_MIN)
            if ph_avail else 0.0,
            available=ph_avail, reason="" if ph_avail else "clock unavailable"))

        # true-open position: DEGRADED to the 09:30 open until G5
        to = ictx.true_open_0930
        if ictx.amd is not None:
            to = ictx.amd.get("true_open_midnight", to)
        to_avail = to is not None and ictx.price > 0
        if to_avail:
            above = ictx.price > float(to)
            v = 1.0 if ((thesis == "bearish" and above) or
                        (thesis == "bullish" and not above)) else 0.0
        else:
            v = 0.0
        sc.components.append(Component(
            "dir:true_open", 1.0, v, available=to_avail,
            reason=("degraded:0930_open" if ictx.amd is None and to_avail
                    else ("" if to_avail else G5_AMD_STATE))))

        # AMD phase itself — pure G5
        sc.components.append(Component(
            "amd_phase", 1.0,
            1.0 if (ictx.amd or {}).get("phase") == "DISTRIBUTION" else 0.0,
            available=ictx.amd is not None, reason="" if ictx.amd else G5_AMD_STATE))

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
