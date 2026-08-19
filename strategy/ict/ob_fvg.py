"""
strategy/ict/ob_fvg.py — generic Order Block + FVG, unfiltered (rank 7). v1.0
v1.0 — 2026-08-18 — INITIAL (ICT setup suite, HANDOFF_FABLE_ICT_SETUPS §2.2.7).

SPEC (operator corrects, then it is law):
  TRIGGER SEQUENCE: price returns into an unmitigated in-favour FVG or an
    order block agreeing with 5m structure. No time filter, no sweep
    requirement — which is exactly why it ranks LAST: without kill-zone
    timing, liquidity context and rapid displacement these produce chop
    that is death for long 0-DTE premium (handoff's words).
  INVALIDATION: acceptance through the far edge of the zone entered.
  TARGET: nearest draw on liquidity.
  SCORE ACCUMULATION: zone-entry(req) + structure agreement(req);
    displacement, kill-zone and draw graded — the graded terms are the
    only thing separating a tradeable instance from chop, so the score
    floor does the filtering the setup definition refuses to.
  SIZE: "size appropriate with conviction" — scoring.size_fraction, and
    additionally HARD-CAPPED at SIZE_FRAC_MARGINAL: the lowest-ranked
    setup never takes more than the marginal fraction regardless of how
    clean the tape looks. Stated prior.
"""

from __future__ import annotations

from typing import Optional, Tuple

from strategy.ict.context import ICTContext
from strategy.ict.scoring import Component, SetupScore, SIZE_FRAC_MARGINAL
from strategy.ict.setup_base import (
    ICTSetup, clamp01, fvg_entry_evidence, displacement_evidence,
    draw_agreement, infer_thesis, to_trade_direction,
)

_KZ_WEIGHT = {"NY_AM": 1.0, "NY_LUNCH": 0.3, "NY_PM": 0.5,
              "PRE": 0.0, "WINDDOWN": 0.0}


class OBFVGSetup(ICTSetup):
    NAME = "ICTOBFVG"
    RANK = 7
    DEBIT_DIRECTIONAL = True

    def evaluate(self, ictx: ICTContext) -> SetupScore:
        thesis = infer_thesis(ictx)
        sc = SetupScore(setup=self.NAME, direction=to_trade_direction(thesis))
        if not thesis:
            return sc

        fv, g = fvg_entry_evidence(ictx, thesis)
        v_ob = 0.0
        if fv < 0.6 and ictx.price > 0:
            for ob in ictx.order_blocks:
                if getattr(ob, "direction", "") != thesis:
                    continue
                top, bot = float(ob.top), float(ob.bottom)
                if bot <= ictx.price <= top:
                    v_ob = 0.9
                    break
                dist = (bot - ictx.price) if ictx.price < bot else (ictx.price - top)
                v_ob = max(v_ob, 0.9 * clamp01(1.0 - dist / (0.004 * ictx.price)))
        sc.components.append(Component("zone_entry", 2.0, max(fv, v_ob),
                                       required=True, floor=0.6))

        v_str = 1.0 if ictx.structure_dir_5m == thesis else 0.0
        sc.components.append(Component("dir:structure_5m", 2.0, v_str,
                                       required=True, floor=1.0))
        sc.components.append(Component("dir:displacement", 1.5,
                                       displacement_evidence(ictx, thesis)))
        kz = _KZ_WEIGHT.get(ictx.killzone, 0.0)
        sc.components.append(Component("killzone", 1.0, kz,
                                       available=bool(ictx.killzone),
                                       reason="" if ictx.killzone
                                       else "clock unavailable"))
        sc.components.append(Component("dir:draw", 1.0,
                                       draw_agreement(ictx, thesis)))
        self._entered_gap = g if fv >= v_ob else None
        return sc

    def generate_signal(self, ictx, sc, chain=None):
        sig = super().generate_signal(ictx, sc, chain)
        if sig is not None:
            # hard cap: lowest rank never exceeds the marginal fraction
            for tag in ("size_frac=1.00", "size_frac=0.66"):
                sig.notes = sig.notes.replace(
                    tag, f"size_frac={SIZE_FRAC_MARGINAL:.2f}")
        return sig

    def _levels(self, ictx: ICTContext, sc: SetupScore
                ) -> Optional[Tuple[float, float, float]]:
        g = getattr(self, "_entered_gap", None)
        zone = g
        if zone is None:
            zone = next((ob for ob in ictx.order_blocks
                         if getattr(ob, "direction", "") ==
                         ("bullish" if sc.direction == "long" else "bearish")),
                        None)
        if zone is None or ictx.price <= 0:
            return None
        stop = float(zone.bottom) if sc.direction == "long" else float(zone.top)
        target = ictx.draw_above if sc.direction == "long" else ictx.draw_below
        if not target:
            return None
        return (ictx.price, stop, float(target))
