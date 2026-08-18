"""
analysis/trend_engine.py — Trend detection via EMA stacks, ADX, momentum. v3.3
Operates on 5m, 15m, and 1H timeframes for multi-TF trend alignment.
v1.0 — original release
v3.3 — 2026-08-01 — STARVATION IS NO LONGER SILENT, and it was hiding a
        half-landed fix. _analyze_single() bails to NEUTRAL below EMA_SLOW+5=55
        bars and said NOTHING. Measured against live fetch depths
        (TIMEFRAMES[tf]["candles"]): 1d=10, 1h=50, 15m=50 are ALL under 55, so
        THREE OF FOUR timeframes have been voting NEUTRAL in production
        permanently — only 5m (100) can vote at all.
        That matters because v3.1's reweight on 07-16 diagnosed exactly this for
        1d/1h and moved the direction weight onto 15m (0.30) + 5m (0.35) — but
        15m fetches 50 bars too, so 0.30 of the weight it moved TO was already
        dead. The fix only half-landed, and the symptom is a silent NEUTRAL
        rather than an error, so nothing surfaced it for two weeks.
        Consequence with only 5m voting: total_weight = 0.35 + half-weight for
        each NEUTRAL frame = 0.675, so bull_score = 0.519*conviction and the
        0.30 gate needs the 5m vote above 0.579 conviction. Below that,
        overall_direction is NEUTRAL — which is a HARD VETO on TRENDING in
        regime_confluence._trending — so TRENDING is structurally unreachable and
        argmax necessarily lands on RANGING/COMPRESSION. Iron condor is the
        RANGING fallback, so it has been absorbing that deficit.
        This release adds the WARNING only; the fetch-depth change is config.py
        (15m 50 -> 150, sized so the EMA-50 has actually converged — at 55-60
        bars it is re-seeded on the tail and off by ~half a bar).
v3.2 — 2026-07-22 — SURFACE primary_momentum ON TrendState (defect W).
        momentum was computed per-timeframe on TrendVote but NEVER aggregated
        onto TrendState, the object handed to the strategies. Any consumer
        doing getattr(trend, "momentum", "") silently got "" — no
        AttributeError, no log — which hard-blocked the trend continuation
        trade on every tick since it shipped 2026-07-18 (see
        continuation_strategy v1.1). Now surfaced from the 5m vote, exactly
        as primary_adx already is, for the same reason: 5m is the timeframe
        this bot actually trades. Default "" means "no 5m vote this tick" and
        consumers MUST treat it as no-trade, not as neutral.
v1.1 — 2026-06-30 — primary_adx now sourced from the 5m timeframe instead
        of 1H. This is a 0DTE intraday bot trading off ORB/butterfly setups
        on 5-min structure — 1H ADX lags the actual session move and was
        causing trend days to misclassify as RANGING (ADX stuck near 0
        until the 1H candle had enough history to show directional
        persistence, which can be hours after the actual breakout fired).
v3.0 — 2026-07-10 — repo-wide v3.0 bump: Yahoo-Finance purge & data stream
        mapping optimization (all market data now flows from the single
        shared TastyTrade candle feed — see data/candle_feed.py). No logic
        change in this file.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Optional
import pandas as pd

from config import EMA_FAST, EMA_MID, EMA_SLOW, EMA_ANCHOR, ADX_TREND_THRESHOLD, ADX_RANGE_THRESHOLD
from utils.math_utils import ema_series, adx_series, current_adx
from utils.time_utils import is_rth        # v3.3: warnings are RTH-only

logger = logging.getLogger(__name__)


@dataclass
class TrendVote:
    """Trend assessment for a single timeframe."""
    timeframe:   str   = ""
    direction:   str   = "NEUTRAL"   # BULLISH / BEARISH / NEUTRAL
    ema_aligned: bool  = False        # All EMAs in stack order
    adx:         float = 0.0
    momentum:    str   = "FLAT"      # ACCELERATING / DECELERATING / FLAT

    ema_fast:    float = 0.0
    ema_mid:     float = 0.0
    ema_slow:    float = 0.0
    ema_anchor:  float = 0.0

    price_vs_ema_fast: str = "ABOVE"  # ABOVE / BELOW
    conviction: float  = 0.0          # 0.0 – 1.0


@dataclass
class TrendState:
    """Aggregated trend picture across all analyzed timeframes."""
    overall_direction:  str               = "NEUTRAL"
    overall_conviction: float             = 0.0
    votes:              Dict[str, TrendVote] = field(default_factory=dict)
    aligned_timeframes: int               = 0   # TFs agreeing with overall direction
    total_timeframes:   int               = 0

    # Convenience flags
    is_trending:       bool  = False
    is_bullish:        bool  = False
    is_bearish:        bool  = False
    primary_adx:       float = 0.0    # ADX from the 5m TF — matches the bot's trading timeframe
    primary_momentum:  str   = ""     # v3.2: momentum from the 5m TF — ACCELERATING /
                                      # DECELERATING / FLAT. "" = no 5m vote this tick;
                                      # consumers must treat "" as NO-TRADE, not neutral.


class TrendEngine:
    """
    Multi-timeframe trend analysis.
    Analyzes 1m, 5m, 15m, 1H and votes on direction.
    """

    def __init__(self):
        # v3.3: timeframes currently in a starvation episode, so the WARNING is
        # emitted once per episode rather than once per tick.
        self._starved_logged: set = set()

    def _analyze_single(self, df: pd.DataFrame, timeframe: str) -> TrendVote:
        """Run full trend analysis on a single timeframe DataFrame."""
        vote = TrendVote(timeframe=timeframe)

        if df is None or len(df) < EMA_SLOW + 5:
            # v3.3 — say so. A starved frame is indistinguishable from a
            # genuinely directionless one at the call site, and that is exactly
            # how three dead timeframes went unnoticed. WARNING, not debug: this
            # means a declared vote weight is silently contributing nothing.
            # ONE line per timeframe per starvation episode, not per tick.
            # v3.3.0 logged every tick and buried bot.log — an alarm that spams
            # is an alarm that gets filtered, which is how this went unseen in
            # the first place. Same one-time-per-key idiom as candle_feed's
            # _log_backfill_depth(). Re-arms when the frame recovers below.
            # RTH-ONLY. Outside the session a thin frame is arithmetic, not a
            # fault — every pre-open and post-close cycle would otherwise emit
            # a warning for a condition that is expected and harmless. Muted to
            # DEBUG there so the record still exists without polluting the
            # channel the operator actually watches.
            if not is_rth():
                logger.debug("trend vote starved %s outside RTH (%d bars) — "
                             "expected, not warned",
                             timeframe, 0 if df is None else len(df))
            elif timeframe not in self._starved_logged:
                self._starved_logged.add(timeframe)
                logger.warning(
                    "trend vote STARVED %s: %d bars, need %d (EMA_SLOW+5) — "
                    "voting NEUTRAL, its declared weight contributes nothing "
                    "(logged once per episode)",
                    timeframe, 0 if df is None else len(df), EMA_SLOW + 5)
            vote.direction = "NEUTRAL"
            return vote

        if timeframe in self._starved_logged:
            self._starved_logged.discard(timeframe)
            logger.info("trend vote RECOVERED %s: %d bars — voting again",
                        timeframe, len(df))

        closes = df["close"]
        price  = float(closes.iloc[-1])

        # EMA stack
        vote.ema_fast   = float(ema_series(closes, EMA_FAST).iloc[-1])
        vote.ema_mid    = float(ema_series(closes, EMA_MID).iloc[-1])
        vote.ema_slow   = float(ema_series(closes, EMA_SLOW).iloc[-1])
        vote.ema_anchor = float(ema_series(closes, EMA_ANCHOR).iloc[-1])

        vote.price_vs_ema_fast = "ABOVE" if price >= vote.ema_fast else "BELOW"

        # Full bullish stack: price > fast > mid > slow > anchor
        bullish_stack = (
            price > vote.ema_fast > vote.ema_mid >
            vote.ema_slow > vote.ema_anchor
        )
        # Full bearish stack: price < fast < mid < slow < anchor
        bearish_stack = (
            price < vote.ema_fast < vote.ema_mid <
            vote.ema_slow < vote.ema_anchor
        )

        vote.ema_aligned = bullish_stack or bearish_stack

        # ADX
        if len(df) >= ADX_TREND_THRESHOLD:
            try:
                vote.adx = current_adx(df)
            except Exception:
                vote.adx = 0.0

        # Determine direction
        if bullish_stack:
            vote.direction = "BULLISH"
        elif bearish_stack:
            vote.direction = "BEARISH"
        elif price > vote.ema_slow:
            vote.direction = "BULLISH"  # Weak bullish
        elif price < vote.ema_slow:
            vote.direction = "BEARISH"  # Weak bearish
        else:
            vote.direction = "NEUTRAL"

        # Momentum: compare last 3 EMA fast values
        fast_series = ema_series(closes, EMA_FAST)
        if len(fast_series) >= 5:
            recent_slope = fast_series.iloc[-1] - fast_series.iloc[-4]
            if vote.direction == "BULLISH":
                vote.momentum = "ACCELERATING" if recent_slope > 0 else "DECELERATING"
            elif vote.direction == "BEARISH":
                vote.momentum = "ACCELERATING" if recent_slope < 0 else "DECELERATING"
            else:
                vote.momentum = "FLAT"

        # Conviction: ADX + EMA alignment
        adx_score = min(vote.adx / 50, 1.0) if vote.adx else 0.0
        align_score = 1.0 if vote.ema_aligned else 0.5
        vote.conviction = adx_score * 0.6 + align_score * 0.4

        return vote

    def analyze(self, data: Dict[str, Optional[pd.DataFrame]]) -> TrendState:
        """
        Analyze trend across all available timeframes.

        Args:
            data: Dict of timeframe → DataFrame from DataCache

        Returns:
            TrendState with directional votes and overall conviction
        """
        state = TrendState()

        # Timeframes to analyze for trend (ordered by weight).
        # v3.1 (2026-07-16): direction is now intraday-primary, consistent with
        # primary_adx already being 5m-sourced. The old stack put 0.80 of the
        # direction weight on 1d/4h/1h — but 4h is NEVER produced by the live
        # feed (1m/5m/15m/1h/1d only) so its weight evaporated, and 1d (~10 bars)
        # / 1h (~50 bars) sit under EMA_SLOW+5=55 on the live feed's thin
        # backfill, returning NEUTRAL and diluting the vote below the 0.30 gate.
        # 5m carried only 0.05 and could never lift bull/bear past 0.30 alone,
        # pinning overall_direction to NEUTRAL and making TRENDING unreachable
        # (2026-07-13..16 replay: 0 TRENDING across 34,925 ticks). Now the frames
        # the 0DTE bot actually trades and that reach depth in-session (5m/15m)
        # drive direction; 1h/1d are context. 4h dropped (never produced).
        tf_weights = {"1d": 0.15, "1h": 0.20, "15m": 0.30, "5m": 0.35}

        weighted_bull  = 0.0
        weighted_bear  = 0.0
        total_weight   = 0.0
        primary_adx    = 0.0
        primary_momentum = ""

        for tf, weight in tf_weights.items():
            df = data.get(tf)
            if df is None or df.empty:
                continue

            vote = self._analyze_single(df, tf)
            state.votes[tf] = vote
            state.total_timeframes += 1

            # primary_adx drives the regime classifier's trending/ranging
            # decision. For an intraday 0DTE bot this must reflect the
            # timeframe the bot actually trades on (5m ORB/butterfly
            # structure), not 1H which lags the live session by hours.
            if tf == "5m":
                primary_adx = vote.adx
                # v3.2: momentum rides along with ADX off the SAME 5m vote —
                # the strategies need the aggregate, not per-TF votes.
                primary_momentum = vote.momentum

            if vote.direction == "BULLISH":
                weighted_bull += weight * vote.conviction
                total_weight  += weight
            elif vote.direction == "BEARISH":
                weighted_bear += weight * vote.conviction
                total_weight  += weight
            else:
                total_weight += weight * 0.5  # Neutral still counts as weight

        state.primary_adx      = primary_adx
        state.primary_momentum = primary_momentum

        # Overall direction from weighted votes
        if total_weight > 0:
            bull_score = weighted_bull / total_weight
            bear_score = weighted_bear / total_weight

            if bull_score > bear_score and bull_score > 0.3:
                state.overall_direction  = "BULLISH"
                state.overall_conviction = bull_score
            elif bear_score > bull_score and bear_score > 0.3:
                state.overall_direction  = "BEARISH"
                state.overall_conviction = bear_score
            else:
                state.overall_direction  = "NEUTRAL"
                state.overall_conviction = 0.0

        # Count aligned timeframes
        state.aligned_timeframes = sum(
            1 for v in state.votes.values()
            if v.direction == state.overall_direction
        )

        state.is_trending = primary_adx >= ADX_TREND_THRESHOLD
        state.is_bullish  = state.overall_direction == "BULLISH"
        state.is_bearish  = state.overall_direction == "BEARISH"

        logger.debug(
            f"Trend: {state.overall_direction} "
            f"conviction={state.overall_conviction:.2f} "
            f"ADX(5m)={primary_adx:.1f} "
            f"aligned={state.aligned_timeframes}/{state.total_timeframes}"
        )
        return state


# Module-level singleton
_trend_engine: Optional[TrendEngine] = None


def get_trend_engine() -> TrendEngine:
    global _trend_engine
    if _trend_engine is None:
        _trend_engine = TrendEngine()
    return _trend_engine
