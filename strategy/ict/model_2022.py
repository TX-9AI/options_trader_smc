"""
strategy/ict/model_2022.py — 2022 Mentorship Model (rank 3). v1.0
v1.0 — 2026-08-18 — INITIAL (ICT setup suite, HANDOFF_FABLE_ICT_SETUPS §2.2.3).

SPEC (operator corrects, then it is law):
  TRIGGER SEQUENCE: liquidity sweep -> MSS -> retrace into THE FVG CREATED
    BY THE DISPLACEMENT LEG THAT CAUSED THE MSS. The linkage IS the model
    (handoff: "the entry FVG is specifically the gap created by the
    displacement leg that caused the MSS"). A nearby unlinked FVG is a
    different, weaker trade — it scores under ob_fvg.py, not here.
  INVALIDATION: acceptance beyond the swept level / displacement origin.
  TARGET: draw on liquidity on the profit side.
  SCORE ACCUMULATION: sweep(req) -> shift(req) -> LINKED-FVG approach(req);
    kill-zone weighting graded (loses edge outside high-volume windows —
    theta dominates before the move expands).
  SIZE: scoring.size_fraction — §2.1 mapping.

CORE GAP THAT BINDS HERE: the displacement→FVG link (G2). REQUIRED and
UNAVAILABLE today, so the 2022 model journals FORMING states now and fires
only after G2 lands. Substituting "nearest in-favour FVG" for "the linked
FVG" would silently trade a different model under this model's name —
refused by construction.
"""

from __future__ import annotations

from typing import Optional, Tuple

from strategy.ict.context import ICTContext, G2_DISP_FVG_LINK
from strategy.ict.scoring import Component, SetupScore
from strategy.ict.setup_base import (
    ICTSetup, sweep_evidence, shift_evidence, displacement_evidence,
    draw_agreement, infer_thesis, to_trade_direction, clamp01,
)

_KZ_WEIGHT = {"NY_AM": 1.0, "NY_LUNCH": 0.4, "NY_PM": 0.5,
              "PRE": 0.0, "WINDDOWN": 0.0}


class Model2022Setup(ICTSetup):
    NAME = "ICTModel2022"
    RANK = 3
    DEBIT_DIRECTIONAL = True

    def evaluate(self, ictx: ICTContext) -> SetupScore:
        thesis = infer_thesis(ictx)
        sc = SetupScore(setup=self.NAME, direction=to_trade_direction(thesis))
        if not thesis:
            return sc

        sv, snote = sweep_evidence(ictx, thesis)
        sc.components.append(Component("dir:sweep", 2.0, sv, required=True,
                                       floor=0.6, reason=snote))
        sc.components.append(Component("dir:shift", 2.0,
                                       shift_evidence(ictx, thesis),
                                       required=True, floor=0.7))
        sc.components.append(Component("dir:displacement", 1.5,
                                       displacement_evidence(ictx, thesis)))

        # THE LINKED FVG — required, G2 until the core delivers it
        g = ictx.displacement_fvg
        linked_avail = g is not None
        if linked_avail and ictx.price > 0:
            top, bot = float(g.top), float(g.bottom)
            if bot <= ictx.price <= top:
                v = 1.0
            else:
                dist = (bot - ictx.price) if ictx.price < bot else (ictx.price - top)
                v = clamp01(1.0 - dist / (0.005 * ictx.price))
        else:
            v = 0.0
        sc.components.append(Component(
            "linked_fvg_entry", 2.5, v, available=linked_avail,
            required=True, floor=0.6,
            reason="" if linked_avail else G2_DISP_FVG_LINK))

        kz = _KZ_WEIGHT.get(ictx.killzone, 0.0)
        sc.components.append(Component("killzone", 1.0, kz,
                                       available=bool(ictx.killzone),
                                       reason="" if ictx.killzone
                                       else "clock unavailable"))
        sc.components.append(Component("dir:draw", 1.0,
                                       draw_agreement(ictx, thesis)))
        return sc

    def _levels(self, ictx: ICTContext, sc: SetupScore
                ) -> Optional[Tuple[float, float, float]]:
        sw = ictx.recent_sweep or {}
        raid = ictx.raid or {}
        stop = raid.get("wick_extreme") or sw.get("sweep_price") or (
            ictx.displacement_origin if ictx.displacement_origin else None)
        target = ictx.draw_above if sc.direction == "long" else ictx.draw_below
        if not stop or not target or ictx.price <= 0:
            return None
        return (ictx.price, float(stop), float(target))
