"""
strategy/ict/breaker_unicorn.py — Breaker Block + FVG / Unicorn (rank 5). v1.0
v1.0 — 2026-08-18 — INITIAL (ICT setup suite, HANDOFF_FABLE_ICT_SETUPS §2.2.5).

SPEC (operator corrects, then it is law):
  TRIGGER SEQUENCE: an order block FAILS (traded through) -> MSS confirms
    the failure -> price returns to the failed block (now a BREAKER) ->
    entry in the breaker, strongest when a fresh FVG OVERLAPS it (UNICORN).
  INVALIDATION: acceptance back through the breaker's far edge — the
    overlap gives an unusually clean invalidation, which is the setup's
    virtue (handoff: "high conviction and often a clean invalidation").
  TARGET: draw on liquidity on the profit side.
  SCORE ACCUMULATION: breaker(req) -> shift(req); unicorn overlap is
    heavy graded confluence; displacement and kill-zone graded. Lower
    frequency by nature — not counted on daily.
  SIZE: scoring.size_fraction — §2.1 mapping.

CORE GAP THAT BINDS HERE: breaker/unicorn detection (G3) is absent from
the core entirely. Both required components are UNAVAILABLE today; this
file ships as the spec-complete consumer so G3's shape is pinned by a
caller before it is built (the contract-first discipline), and journals
its unavailability rather than pretending a zero.
"""

from __future__ import annotations

from typing import Optional, Tuple

from strategy.ict.context import ICTContext, G3_BREAKER
from strategy.ict.scoring import Component, SetupScore
from strategy.ict.setup_base import (
    ICTSetup, clamp01, shift_evidence, displacement_evidence, draw_agreement,
    infer_thesis, to_trade_direction,
)

_KZ_WEIGHT = {"NY_AM": 1.0, "NY_LUNCH": 0.5, "NY_PM": 0.6,
              "PRE": 0.0, "WINDDOWN": 0.0}


def _in_zone_value(price: float, top: float, bottom: float) -> float:
    if bottom <= price <= top:
        return 1.0
    dist = (bottom - price) if price < bottom else (price - top)
    return clamp01(1.0 - dist / (0.005 * price)) if price > 0 else 0.0


class BreakerUnicornSetup(ICTSetup):
    NAME = "ICTBreakerUnicorn"
    RANK = 5
    DEBIT_DIRECTIONAL = True

    def evaluate(self, ictx: ICTContext) -> SetupScore:
        thesis = infer_thesis(ictx)
        sc = SetupScore(setup=self.NAME, direction=to_trade_direction(thesis))
        if not thesis:
            return sc

        breakers_avail = ictx.has("breakers")
        br = None
        v_br = 0.0
        if breakers_avail:
            for b in ictx.breakers:
                if getattr(b, "direction", "") == thesis:
                    v_br = _in_zone_value(ictx.price, float(b.top), float(b.bottom))
                    br = b
                    break
        sc.components.append(Component(
            "breaker_entry", 2.5, v_br, available=breakers_avail,
            required=True, floor=0.6,
            reason="" if breakers_avail else G3_BREAKER))

        uni_avail = ictx.has("unicorns")
        v_uni = 0.0
        if uni_avail and br is not None:
            v_uni = 1.0 if any(getattr(u, "breaker", None) is br
                               for u in ictx.unicorns) else 0.0
        sc.components.append(Component(
            "unicorn_overlap", 1.5, v_uni, available=uni_avail,
            reason="" if uni_avail else G3_BREAKER))

        sc.components.append(Component("dir:shift", 2.0,
                                       shift_evidence(ictx, thesis),
                                       required=True, floor=0.7))
        sc.components.append(Component("dir:displacement", 1.5,
                                       displacement_evidence(ictx, thesis)))
        kz = _KZ_WEIGHT.get(ictx.killzone, 0.0)
        sc.components.append(Component("killzone", 0.5, kz,
                                       available=bool(ictx.killzone),
                                       reason="" if ictx.killzone
                                       else "clock unavailable"))
        sc.components.append(Component("dir:draw", 1.0,
                                       draw_agreement(ictx, thesis)))
        return sc

    def _levels(self, ictx: ICTContext, sc: SetupScore
                ) -> Optional[Tuple[float, float, float]]:
        br = next((b for b in ictx.breakers
                   if getattr(b, "direction", "") ==
                   ("bullish" if sc.direction == "long" else "bearish")), None)
        if br is None or ictx.price <= 0:
            return None
        stop = float(br.bottom) if sc.direction == "long" else float(br.top)
        target = ictx.draw_above if sc.direction == "long" else ictx.draw_below
        if not target:
            return None
        return (ictx.price, stop, float(target))
