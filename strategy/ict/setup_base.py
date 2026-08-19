"""
strategy/ict/setup_base.py — shared base for the seven ICT setups. v1.0
v1.0 — 2026-08-18 — INITIAL (ICT setup suite, HANDOFF_FABLE_ICT_SETUPS).

Each setup subclasses ICTSetup and supplies:
  - NAME, RANK (dispatch order), DEBIT_DIRECTIONAL (must be registered in
    config.DEBIT_DIRECTIONAL_STRATEGIES by the config owner — SPEC G8)
  - evaluate(ictx) -> SetupScore       (continuous; journaled by dispatch)
  - _levels(ictx, sc) -> (entry, stop, target) underlying prices, or None

Signal construction is shared here so stop/target discipline is uniform:
  - DEBIT expression only in v1.0. Post-cutoff credit expression is a
    designed follow-up (BACKLOG F.14): the ICT layer supplies side, strike
    anchor and invalidation; the TCS/credit_vertical machinery executes.
    Until F.14, dispatch refuses debit-blocked fires and journals them.
  - Strike selection reuses the fleet's delta selector
    (chain_fetcher.select_sweep_strike) — target delta scales inversely
    with score, the SweepReversal idiom: strong setup -> farther OTM.
  - contracts sizing: the signal carries `conviction = score` and
    `notes` carries the ICT size fraction; position sizing multiplies the
    strategy's base risk by that fraction downstream. No signal ever asks
    for MORE than baseline risk (RETOOL_VERDICT Q4 preconditions unmet).

PAPER SAFETY: nothing in this package touches execution or config; a
setup can only ever RETURN a proposal object.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional, Tuple

from strategy.ict.context import ICTContext
from strategy.ict.scoring import SetupScore, size_fraction

logger = logging.getLogger(__name__)


def _target_delta(score: float) -> float:
    """Inverse-with-strength delta target, the SweepReversal idiom:
    score→1 buys ~0.18Δ (leverage on a clean setup), score→floor buys
    ~0.35Δ (participation on a marginal one). Prior."""
    return round(0.35 - 0.17 * max(0.0, min(1.0, score)), 3)


class ICTSetup(ABC):
    NAME: str = ""
    RANK: int = 99
    DEBIT_DIRECTIONAL: bool = True     # SPEC G8: register NAME in config set

    @abstractmethod
    def evaluate(self, ictx: ICTContext) -> SetupScore: ...

    @abstractmethod
    def _levels(self, ictx: ICTContext, sc: SetupScore
                ) -> Optional[Tuple[float, float, float]]:
        """(entry, stop, target) at the UNDERLYING, or None if unresolvable."""
        ...

    # ── shared debit signal builder ─────────────────────────────────────
    def generate_signal(self, ictx: ICTContext, sc: SetupScore, chain=None):
        """Build an OptionsSignal for a fire-eligible score. Returns None —
        never raises — when the chain can't serve a contract."""
        if not sc.fire_eligible():
            return None
        frac = size_fraction(ictx.displacement_sd, sc.bias_quality())
        if frac <= 0.0:
            sc.blocked = "size_zero"
            return None
        lv = self._levels(ictx, sc)
        if lv is None:
            sc.blocked = "levels_unresolved"
            return None
        entry, stop, target = lv
        if sc.direction == "long" and not (stop < entry < target):
            sc.blocked = "levels_incoherent"
            return None
        if sc.direction == "short" and not (target < entry < stop):
            sc.blocked = "levels_incoherent"
            return None

        from strategy.base_strategy import OptionsSignal   # lazy: heavy chain deps
        side = "call" if sc.direction == "long" else "put"
        contract = None
        if chain is not None:
            try:
                from data.options_chain import get_chain_fetcher
                contract = get_chain_fetcher().select_sweep_strike(
                    chain, sc.direction, _target_delta(sc.score()))
            except Exception as e:
                logger.warning("%s: strike selection failed: %s", self.NAME, e)
                sc.blocked = "no_contract"
                return None
        sig = OptionsSignal(
            strategy_name=self.NAME,
            setup_type=f"ict_{self.NAME.lower()}",
            direction=sc.direction,
            option_side=side,
            underlying_entry=float(entry),
            underlying_stop=float(stop),
            underlying_target=float(target),
            contract=contract,
            strike=float(getattr(contract, "strike", 0.0) or 0.0),
            conviction=sc.score(),
            confluence_factors=[c.name for c in sc.components
                                if c.available and c.value >= c.floor],
            regime="",   # deliberately blank — no label was consulted unless
                         # a dir:regime component says so (handoff §3.2)
            notes=(f"ict size_frac={frac:.2f} completeness={sc.completeness():.2f} "
                   f"bias={sc.bias_quality():.2f} disp_sd={ictx.displacement_sd:.2f}"),
        )
        return sig


# ── shared component helpers (each returns value 0..1) ───────────────────────

def clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def sweep_evidence(ictx: ICTContext, thesis: str) -> Tuple[float, str]:
    """1.0 = live raid agreeing with thesis (anticipation — the fork's point);
    0.7 = mapper-CONFIRMED sweep agreeing, not invalidated; else 0."""
    raid = ictx.raid or {}
    if raid:
        rdir = str(raid.get("thesis", raid.get("direction", "")))
        if rdir == thesis:
            return 1.0, "live_raid"
    sw = ictx.recent_sweep or {}
    if sw and not sw.get("invalidated", False):
        sdir = str(sw.get("direction", ""))
        # a swept LOW that reclaimed is bullish evidence, mirrored for highs
        if (thesis == "bullish" and sdir in ("low", "bullish")) or \
           (thesis == "bearish" and sdir in ("high", "bearish")):
            return 0.7, f"confirmed_sweep:{sw.get('level_name','')}"
    return 0.0, ""


def shift_evidence(ictx: ICTContext, thesis: str) -> float:
    """MSS agreement: CHoCH in thesis direction 1.0; BOS in direction 0.8."""
    if ictx.last_shift_dir != thesis or not ictx.last_shift:
        return 0.0
    return 1.0 if ictx.last_shift == "CHOCH" else 0.8


def displacement_evidence(ictx: ICTContext, thesis: str,
                          aware: float = 1.75, confirm: float = 2.0) -> float:
    if ictx.displacement_dir != thesis or ictx.displacement_sd <= 0:
        return 0.0
    if ictx.displacement_sd >= confirm:
        return 1.0
    if ictx.displacement_sd >= aware:
        return 0.6
    return 0.3


def fvg_entry_evidence(ictx: ICTContext, thesis: str,
                       approach_frac: float = 0.005) -> Tuple[float, object]:
    """Nearest in-favour unmitigated FVG; 1.0 when price is inside it,
    scaling down with distance (approach_frac of price = 0). Prior."""
    gaps = ictx.fvgs_bull if thesis == "bullish" else ictx.fvgs_bear
    if not gaps or ictx.price <= 0:
        return 0.0, None
    g = gaps[0]
    top, bot = float(g.top), float(g.bottom)
    if bot <= ictx.price <= top:
        return 1.0, g
    dist = (bot - ictx.price) if ictx.price < bot else (ictx.price - top)
    v = clamp01(1.0 - dist / (approach_frac * ictx.price))
    return v, g


def zone_alignment(ictx: ICTContext, thesis: str) -> float:
    """Buy discount, sell premium. Sentinel range -> 0 (and the component is
    marked unavailable by callers when position_pct is -1.0)."""
    if ictx.position_pct < 0:
        return 0.0
    return clamp01(1.0 - ictx.position_pct) if thesis == "bullish" \
        else clamp01(ictx.position_pct)


def draw_agreement(ictx: ICTContext, thesis: str) -> float:
    """Is the nearest untapped pool on the profit side of the thesis?"""
    if thesis == "bullish":
        return 1.0 if ictx.draw_above is not None and ictx.draw_side in ("above", "") else \
               (0.5 if ictx.draw_above is not None else 0.0)
    return 1.0 if ictx.draw_below is not None and ictx.draw_side in ("below", "") else \
           (0.5 if ictx.draw_below is not None else 0.0)


def infer_thesis(ictx: ICTContext) -> str:
    """The setup's working direction, from structure evidence in priority
    order: live raid thesis > last shift dir > displacement dir > 5m dir.
    Empty string = no basis (setup stays DORMANT)."""
    raid = ictx.raid or {}
    t = str(raid.get("thesis", "") or "")
    if t in ("bullish", "bearish"):
        return t
    if ictx.last_shift_dir in ("bullish", "bearish"):
        return ictx.last_shift_dir
    if ictx.displacement_dir in ("bullish", "bearish"):
        return ictx.displacement_dir
    if ictx.structure_dir_5m in ("bullish", "bearish"):
        return ictx.structure_dir_5m
    return ""


def to_trade_direction(thesis: str) -> str:
    return {"bullish": "long", "bearish": "short"}.get(thesis, "")
