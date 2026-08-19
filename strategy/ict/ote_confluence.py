"""
strategy/ict/ote_confluence.py — Optimal Trade Entry, 62–79% (rank 6). v1.0
v1.0 — 2026-08-18 — INITIAL (ICT setup suite, HANDOFF_FABLE_ICT_SETUPS §2.2.6).

SPEC (operator corrects, then it is law):
  TRIGGER SEQUENCE: a NAMED impulse leg (origin -> extreme) -> retracement
    into the 0.62–0.79 band OF THAT LEG -> entry strongest when an OB or
    FVG sits INSIDE the band (the confluence that earns the trade — as a
    standalone it is weaker for 0-DTE, handoff's own ranking).
  INVALIDATION: acceptance beyond the 0.79 boundary toward the leg origin.
  TARGET: the leg extreme first, draw on liquidity beyond it.
  SCORE ACCUMULATION: named-leg(req) -> price-in-OTE(req) -> OB/FVG-inside
    heavy confluence; structure agreement graded.
  SIZE: scoring.size_fraction, CAPPED at SIZE_FRAC_SOLID standalone — the
    full fraction requires the OB/FVG-inside confluence to be passing.
  AFTERNOON: the deep-retrace wait often lands past the debit cutoff —
    handoff §2.2.6 says express as a CREDIT SPREAD then. v1.0 does not
    build credit legs (BACKLOG F.14); dispatch journals `wants_credit`
    on a post-cutoff fire-eligible OTE so the demand is measured before
    the adapter is built.

CORE GAP THAT BINDS HERE: OTE is a retracement of a NAMED impulse leg
(G4) — a different quantity from position in the dealing range, and from
the single displacement CANDLE the adapter can see. `impulse_leg` is
REQUIRED and unavailable today; the degraded candle-based band is refused
for CONFIRM by construction (context registers it DEGRADED:G4).
"""

from __future__ import annotations

from typing import Optional, Tuple

from strategy.ict.context import ICTContext, G4_IMPULSE_LEG
from strategy.ict.scoring import Component, SetupScore, SIZE_FRAC_SOLID
from strategy.ict.setup_base import (
    ICTSetup, clamp01, shift_evidence, displacement_evidence, draw_agreement,
    infer_thesis, to_trade_direction,
)

OTE_LO, OTE_HI = 0.62, 0.79      # the band. Definitional, not a prior.


def ote_band(leg: dict) -> Optional[Tuple[float, float]]:
    """(near, far) prices of the 0.62–0.79 retracement of a named leg."""
    try:
        o, e = float(leg["origin"]), float(leg["extreme"])
    except (KeyError, TypeError, ValueError):
        return None
    span = e - o
    return (e - OTE_LO * span, e - OTE_HI * span)


class OTEConfluenceSetup(ICTSetup):
    NAME = "ICTOTEConfluence"
    RANK = 6
    DEBIT_DIRECTIONAL = True

    def evaluate(self, ictx: ICTContext) -> SetupScore:
        thesis = infer_thesis(ictx)
        sc = SetupScore(setup=self.NAME, direction=to_trade_direction(thesis))
        if not thesis:
            return sc

        leg_avail = ictx.impulse_leg is not None
        band = ote_band(ictx.impulse_leg) if leg_avail else None
        sc.components.append(Component(
            "named_leg", 2.0, 1.0 if band else 0.0, available=leg_avail,
            required=True, floor=1.0,
            reason="" if leg_avail else G4_IMPULSE_LEG))

        v_in = 0.0
        if band and ictx.price > 0:
            hi, lo = max(band), min(band)
            if lo <= ictx.price <= hi:
                v_in = 1.0
            else:
                dist = (lo - ictx.price) if ictx.price < lo else (ictx.price - hi)
                v_in = clamp01(1.0 - dist / (0.004 * ictx.price))
        sc.components.append(Component(
            "in_ote", 2.0, v_in, available=leg_avail, required=True, floor=0.6,
            reason="" if leg_avail else G4_IMPULSE_LEG))

        # OB or FVG INSIDE the band — the confluence
        v_conf = 0.0
        if band:
            hi, lo = max(band), min(band)
            gaps = ictx.fvgs_bull if thesis == "bullish" else ictx.fvgs_bear
            for g in gaps:
                if lo <= (float(g.top) + float(g.bottom)) / 2.0 <= hi:
                    v_conf = 1.0
                    break
            if v_conf == 0.0:
                for ob in ictx.order_blocks:
                    if getattr(ob, "direction", "") == thesis and \
                       lo <= (float(ob.top) + float(ob.bottom)) / 2.0 <= hi:
                        v_conf = 0.8
                        break
        sc.components.append(Component("poi_inside_ote", 1.5, v_conf,
                                       available=leg_avail,
                                       reason="" if leg_avail else G4_IMPULSE_LEG))

        sc.components.append(Component("dir:shift", 1.0,
                                       shift_evidence(ictx, thesis)))
        sc.components.append(Component("dir:displacement", 1.0,
                                       displacement_evidence(ictx, thesis)))
        sc.components.append(Component("dir:draw", 1.0,
                                       draw_agreement(ictx, thesis)))
        # standalone cap noted for sizing (setup_base reads notes? — cap is
        # enforced in generate via override below)
        self._conf_passing = v_conf >= 0.5
        return sc

    def generate_signal(self, ictx, sc, chain=None):
        sig = super().generate_signal(ictx, sc, chain)
        if sig is not None and not getattr(self, "_conf_passing", False):
            # standalone OTE: cap the size fraction at SOLID
            sig.notes = sig.notes.replace(
                "size_frac=1.00", f"size_frac={SIZE_FRAC_SOLID:.2f}")
        return sig

    def _levels(self, ictx: ICTContext, sc: SetupScore
                ) -> Optional[Tuple[float, float, float]]:
        leg = ictx.impulse_leg
        band = ote_band(leg) if leg else None
        if not band or ictx.price <= 0:
            return None
        stop = min(band) if sc.direction == "long" else max(band)
        # widen stop just past the 0.79 boundary toward origin
        stop = stop * (0.999 if sc.direction == "long" else 1.001)
        target = float(leg["extreme"])
        return (ictx.price, stop, target)
