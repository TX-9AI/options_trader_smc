"""
smc/primitives.py — SMC/ICT structural primitives (pure functions). v1.1
v1.1 — 2026-08-19 — `raid_in_progress()` now states the THESIS it implies.
        It emitted `kind` ("high_raid"/"low_raid") and nothing else about
        direction, while every consumer asked for `thesis`/`direction`. The
        result was silent and total: `sweep_evidence()` scored 0.00 on every
        tick of 27 sessions, so ICTSweepMSS, ICTModel2022 and ICTJudasPO3
        could never reach READY and the only setup that ever fired was the
        one that needs no sweep at all — the lowest-ranked of the seven.
        Nothing raised; a required component was simply always zero.
v1.0 — 2026-08-18 — INITIAL (fork: options_trader_smc, candidate QQQ).
        Pure functions only — no state, no I/O, no side effects. Every
        function is a function of the frames/state objects passed in, in
        the same stateless idiom as trend_engine.analyze(). Statefulness
        (setup lifecycle, structure ratchets) lives in smc/smc_engine.py.

        WHAT THIS LAYER ADDS over the salvaged substrate, and what it
        deliberately reuses rather than re-implements:
        - REUSED: swings (structure_analyzer.SwingPoint), FVGs
          (structure_analyzer.FairValueGap), order blocks
          (structure_analyzer.OrderBlock), liquidity pools / sweeps /
          session levels (liquidity_mapper). Re-deriving any of those here
          would be the 774-line-duplicate error (WORKING_AGREEMENT §25).
        - NEW: dealing range + premium/discount position, displacement
          (SD-normalized impulse over closed 1m bars — the same yardstick
          trade_readiness._impulse_sd uses, restated here as a pure
          function), BOS vs CHoCH classification over a swing sequence,
          draw-on-liquidity (nearest untapped pool each side), killzone
          clock, and inducement flagging (a minor pool sitting between
          price and the draw).

        DESIGN RULES INHERITED FROM THE PARENT REPO:
        - Sentinels distinguish "not computed" from a real zero (STR.2:
          a 0.0 default that is also a legal reading is how a probe scores
          defaults as data). position_pct uses -1.0 for "no range".
        - No look-ahead: everything reads CLOSED bars (iloc[:-1] where a
          forming bar may be present is the CALLER's contract — main.py's
          cache serves closed bars; the replay harness slices as-of).
        - No per-evaluate counters (the 07-20 tick-vs-bar audit): ages are
          derived from bar indices/timestamps, never incremented per call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

# ── Tunables (env-overridable via config; imported lazily to keep this module
#    importable offline without the full config chain) ────────────────────────
DISPLACEMENT_SD_AWARE = 1.75      # impulse begins to matter (TC.4 vocabulary)
DISPLACEMENT_SD_CONFIRM = 2.0     # a real committed move
EQUILIBRIUM_BAND = 0.05           # ±5% around 0.50 counts as equilibrium
PREMIUM_FLOOR = 0.62              # position_pct above this = premium zone
DISCOUNT_CEIL = 0.38              # position_pct below this = discount zone
SWEEP_WICK_MIN_PCT = 0.0005       # min raid depth beyond a pool (0.05% of price)


# ── Dealing range / premium–discount ─────────────────────────────────────────

@dataclass
class DealingRange:
    """The external range price is currently dealing inside.

    Anchored on the most recent CONFIRMED swing high and swing low that
    bracket current price on the anchor timeframe. External liquidity
    rests beyond both ends; equilibrium is the 50% of the range.
    """
    high: float
    low: float
    high_index: int
    low_index: int
    timeframe: str = ""

    @property
    def width(self) -> float:
        return self.high - self.low

    @property
    def equilibrium(self) -> float:
        return self.low + 0.5 * self.width

    def position_pct(self, price: float) -> float:
        """0.0 at the range low, 1.0 at the range high. -1.0 = degenerate."""
        if self.width <= 0:
            return -1.0
        return (price - self.low) / self.width


def dealing_range(swing_highs, swing_lows, price: float,
                  timeframe: str = "") -> Optional[DealingRange]:
    """Most recent swing high above price + most recent swing low below.

    Consumes structure_analyzer.SwingPoint lists (price/index/kind). Returns
    None when price is not bracketed (e.g. price above every recorded swing
    high — an expansion leg with no upper reference yet). None is honest:
    "unobservable ≠ a regime" (REGIME_TRUTHS Task 2).
    """
    highs_above = [s for s in (swing_highs or []) if s.price > price]
    lows_below = [s for s in (swing_lows or []) if s.price < price]
    if not highs_above or not lows_below:
        return None
    h = max(highs_above, key=lambda s: s.index)
    l = max(lows_below, key=lambda s: s.index)
    if h.price - l.price <= 0:
        return None
    return DealingRange(high=h.price, low=l.price,
                        high_index=h.index, low_index=l.index,
                        timeframe=timeframe)


def zone_of(position_pct: float) -> str:
    """PREMIUM / DISCOUNT / EQUILIBRIUM / NONE (sentinel -1.0)."""
    if position_pct < 0:
        return "NONE"
    if position_pct >= PREMIUM_FLOOR:
        return "PREMIUM"
    if position_pct <= DISCOUNT_CEIL:
        return "DISCOUNT"
    if abs(position_pct - 0.5) <= EQUILIBRIUM_BAND:
        return "EQUILIBRIUM"
    return "MID"


# ── Displacement ─────────────────────────────────────────────────────────────

@dataclass
class Displacement:
    """A 1m candle whose range clears the rolling-SD bound — committed flow."""
    sd: float                     # candle range in rolling-SD units
    direction: str                # "bullish" / "bearish"
    index: int                    # positional index in the frame passed in
    open: float = 0.0
    close: float = 0.0
    high: float = 0.0
    low: float = 0.0

    @property
    def origin(self) -> float:
        """The impulse origin — durable floor (bull) / ceiling (bear)."""
        return self.low if self.direction == "bullish" else self.high


def last_displacement(df_1m: pd.DataFrame, lookback: int = 30,
                      sd_floor: float = DISPLACEMENT_SD_AWARE
                      ) -> Optional[Displacement]:
    """Most recent closed 1m candle whose range ≥ sd_floor rolling SDs.

    The SD is computed over the `lookback` bars PRECEDING each candidate
    (never including it) — the same no-self-reference rule the readiness
    track's _impulse_sd uses. Returns None when the frame is too thin or no
    candle clears the floor; None is "no displacement observed", never 0.0.
    """
    if df_1m is None or len(df_1m) < lookback + 2:
        return None
    rng = (df_1m["high"] - df_1m["low"]).astype(float)
    closes = df_1m["close"].astype(float)
    opens = df_1m["open"].astype(float)
    best: Optional[Displacement] = None
    # scan the most recent 20 closed candles for the LATEST qualifier
    start = max(lookback, len(df_1m) - 20)
    for i in range(start, len(df_1m)):
        window = rng.iloc[i - lookback:i]
        mu, sd = float(window.mean()), float(window.std(ddof=0))
        if sd <= 0:
            continue
        z = (float(rng.iloc[i]) - mu) / sd
        if z >= sd_floor:
            direction = "bullish" if closes.iloc[i] >= opens.iloc[i] else "bearish"
            best = Displacement(sd=round(z, 3), direction=direction, index=i,
                                open=float(opens.iloc[i]),
                                close=float(closes.iloc[i]),
                                high=float(df_1m["high"].iloc[i]),
                                low=float(df_1m["low"].iloc[i]))
    return best


# ── Structure shift: BOS vs CHoCH ────────────────────────────────────────────

@dataclass
class StructureEvent:
    """A confirmed break of a swing point by a 1m CLOSE."""
    kind: str          # "BOS" (with prior direction) or "CHOCH" (against it)
    direction: str     # direction of the BREAK: "bullish" (broke a high) / "bearish"
    level: float       # the swing price that was broken
    bar_index: int     # index of the breaking close


def classify_break(prior_direction: str, break_direction: str) -> str:
    """BOS continues the prior structure direction; CHoCH reverses it.

    prior_direction ∈ {"bullish","bearish","neutral"}. A break with no
    established prior direction is a BOS by convention (first structure).
    """
    if prior_direction in ("", "neutral", None):
        return "BOS"
    return "BOS" if prior_direction == break_direction else "CHOCH"


def find_break(df_1m: pd.DataFrame, swing_highs, swing_lows,
               prior_direction: str = "neutral"
               ) -> Optional[StructureEvent]:
    """Did the LAST CLOSED 1m candle close beyond the most recent swing?

    Close-based, never wick-based — the same acceptance-vs-touch rule the
    ORB stop and tcs_floor_durability use (a wick is a raid; a close is
    acceptance). Reads only the final closed bar so repeated calls on the
    same bar return the same answer (no per-call accumulation).
    """
    if df_1m is None or len(df_1m) < 2:
        return None
    close = float(df_1m["close"].iloc[-1])
    idx = len(df_1m) - 1
    # nearest unbroken swing high below/above scan: use the most recent swings
    recent_high = max((s for s in (swing_highs or [])), key=lambda s: s.index,
                      default=None)
    recent_low = max((s for s in (swing_lows or [])), key=lambda s: s.index,
                     default=None)
    if recent_high is not None and close > recent_high.price:
        return StructureEvent(kind=classify_break(prior_direction, "bullish"),
                              direction="bullish", level=recent_high.price,
                              bar_index=idx)
    if recent_low is not None and close < recent_low.price:
        return StructureEvent(kind=classify_break(prior_direction, "bearish"),
                              direction="bearish", level=recent_low.price,
                              bar_index=idx)
    return None


# ── Liquidity: draw, raids, inducement ───────────────────────────────────────

@dataclass
class LiquidityDraw:
    """The nearest untapped pool on each side — where price is drawn to."""
    above: Optional[float] = None
    above_name: str = ""
    below: Optional[float] = None
    below_name: str = ""

    def nearest_side(self, price: float) -> str:
        """Which draw is closer: 'above' / 'below' / ''. """
        da = (self.above - price) if self.above is not None else None
        db = (price - self.below) if self.below is not None else None
        if da is None and db is None:
            return ""
        if db is None or (da is not None and da <= db):
            return "above"
        return "below"


def draw_on_liquidity(pools, price: float) -> LiquidityDraw:
    """Nearest UNSWEPT pool above and below current price.

    Consumes liquidity_mapper.LiquidityPool objects. A swept pool no longer
    holds resting stops, so it cannot be a draw. Named pools (PDH/PDL,
    session H/L) and equal-H/L clusters both qualify — external liquidity
    is external regardless of its name.
    """
    d = LiquidityDraw()
    for p in (pools or []):
        if getattr(p, "swept", False):
            continue
        if p.price > price and (d.above is None or p.price < d.above):
            d.above, d.above_name = p.price, (getattr(p, "name", "") or "eqh")
        elif p.price < price and (d.below is None or p.price > d.below):
            d.below, d.below_name = p.price, (getattr(p, "name", "") or "eql")
    return d


def raid_in_progress(df_1m: pd.DataFrame, pools, price: float
                     ) -> Optional[dict]:
    """A pool whose level the CURRENT closed bar's WICK has pierced while the
    CLOSE stayed inside — a raid that has not yet resolved to sweep-reclaim
    (mapper's job) or acceptance (breakout).

    This is the ANTICIPATORY read: the mapper confirms a sweep after
    reclaim; this flags the purge while it is happening, so a setup can be
    FORMING before confirmation. Returns {"pool","kind","depth_pct"} or None.
    """
    if df_1m is None or len(df_1m) < 1 or not pools:
        return None
    hi = float(df_1m["high"].iloc[-1])
    lo = float(df_1m["low"].iloc[-1])
    close = float(df_1m["close"].iloc[-1])
    for p in pools:
        if getattr(p, "swept", False):
            continue
        if p.price > 0 and hi > p.price and close < p.price:
            depth = (hi - p.price) / p.price
            if depth >= SWEEP_WICK_MIN_PCT:
                return {"pool": p.price, "kind": "high_raid",
                        # v1.1 — THE THESIS THE RAID IMPLIES, stated outright.
                        # Consumers were asking `raid["thesis"]` and getting
                        # nothing, because this dict only ever carried `kind`.
                        # A raid THROUGH a high that closes back inside took
                        # buy-side liquidity and failed, so the thesis is DOWN.
                        "thesis": "bearish", "direction": "bearish",
                        "name": getattr(p, "name", "") or "eqh",
                        "depth_pct": round(depth, 6)}
        if 0 < p.price and lo < p.price and close > p.price:
            depth = (p.price - lo) / p.price
            if depth >= SWEEP_WICK_MIN_PCT:
                return {"pool": p.price, "kind": "low_raid",
                        # a swept LOW that reclaimed took sell-side liquidity
                        # and failed -> the thesis is UP.
                        "thesis": "bullish", "direction": "bullish",
                        "name": getattr(p, "name", "") or "eql",
                        "depth_pct": round(depth, 6)}
    return None


def inducement(pools, price: float, draw: LiquidityDraw) -> Optional[float]:
    """A minor unswept pool sitting BETWEEN price and the dominant draw —
    the pocket likely to be purged before the real objective is run.

    Returns the inducement price or None. Purely positional; no prediction
    is claimed (the A2 drift study is the standing warning against claiming
    forward content from position alone — this is context, weight-0).
    """
    side = draw.nearest_side(price)
    if side == "above" and draw.above is not None:
        between = [p.price for p in (pools or [])
                   if not getattr(p, "swept", False)
                   and price < p.price < draw.above]
        return min(between) if between else None
    if side == "below" and draw.below is not None:
        between = [p.price for p in (pools or [])
                   if not getattr(p, "swept", False)
                   and draw.below < p.price < price]
        return max(between) if between else None
    return None


# ── Imbalance freshness ──────────────────────────────────────────────────────

def unmitigated_fvgs(fvgs, price: float, direction: str = "",
                     max_n: int = 6) -> List:
    """Unfilled FVGs, optionally filtered to the in-favor side, nearest first.

    Consumes structure_analyzer.FairValueGap. "In favor" for a bullish
    thesis = bullish gaps BELOW price (the retrace destination); mirrored
    for bearish. No new detection — the analyzer already finds them.
    """
    out = []
    for g in (fvgs or []):
        if getattr(g, "filled", False):
            continue
        if direction == "bullish" and not (g.direction == "bullish"
                                           and g.top <= price):
            continue
        if direction == "bearish" and not (g.direction == "bearish"
                                           and g.bottom >= price):
            continue
        out.append(g)
    mid = lambda g: (g.top + g.bottom) / 2.0
    out.sort(key=lambda g: abs(mid(g) - price))
    return out[:max_n]


# ── Killzones ────────────────────────────────────────────────────────────────

def killzone(now_et) -> str:
    """Which ICT killzone the ET clock sits in. Pure clock read.

    NY_AM 09:30–11:00 · NY_LUNCH 11:00–13:00 · NY_PM 13:00–14:00 ·
    WINDDOWN 14:00+ (global entry cutoff already blocks entries there) ·
    PRE before 09:30. These deliberately align with the session windows the
    strategies already run (ORB 9:35–11:00, global cutoff 14:00) so the
    killzone is a NAME for existing behavior, not a second clock to drift.
    """
    hm = (now_et.hour, now_et.minute)
    if hm < (9, 30):
        return "PRE"
    if hm < (11, 0):
        return "NY_AM"
    if hm < (13, 0):
        return "NY_LUNCH"
    if hm < (14, 0):
        return "NY_PM"
    return "WINDDOWN"
