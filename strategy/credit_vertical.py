"""
strategy/credit_vertical.py — options_trader_v3 — v1.1 — 2026-08-14   (TCS.1)
v1.1  2026-08-17  SWALLOW T1: this file's silent handler(s) now announce
        themselves once. Behaviour unchanged in every case; only the silence
        was the defect.

SELECTION MATH SHARED BY EVERY CREDIT VERTICAL. OWNED BY NEITHER STRATEGY.

⚠️ WHY THIS MODULE EXISTS, and it is not tidiness.

`TrendCreditSpread` was built inside `IronCondorStrategy`'s plumbing: it borrowed
six `CONDOR_*` constants, five of its methods, set `is_iron_condor = True`, and
executed and exited through `_execute_condor_leg` / `_evaluate_condor_leg`. Two
consequences, one of them already paid for:

  · **CHANGING A CONDOR KNOB SILENTLY RETUNED A DIFFERENT TRADE.** `CONDOR_MIN_POP`
    governed both. Nothing said so.
  · **AND ON 2026-08-14 IT PRODUCED 108 BAD TRADES.** Because TC.6 rode the
    condor's execution path, its identity had to survive as a FLAG on the record
    (`is_trend_credit`) — and when `_execute_condor_leg` hardcoded condor
    identity instead, the flag never arrived, the exit branch never fired, and
    every leg inherited the condor's ratchet and 25% premium stop. **A trade
    living inside another trade's plumbing fails the moment one hop drops a
    field.**

So the math both trades genuinely share lives HERE, imported by both, owned by
neither. Each strategy keeps its OWN constants, so a knob change reaches exactly
the trade it names.

⚠️ **VALUES ARE UNCHANGED BY THIS MOVE.** Every function is lifted verbatim from
`IronCondorStrategy`; the TCS_* defaults equal the CONDOR_* values they replace.
This is a de-coupling, not a re-tune — behaviour must be provably identical, and
a test asserts the defaults still match.
"""

import logging
import math
from typing import List, Optional, Sequence

logger = logging.getLogger(__name__)


# ── SWALLOW T1 REVIEW, 2026-08-17 ────────────────────────────────────────────
# The three handlers below were flagged as silent. **All three FAIL CLOSED and
# their behaviour is correct**: an unreadable quote ranks worst (9.99), fails
# `quote_ok`, or scores POP 0.0 — every path ends in "do not select this
# contract". None of them can grant permission.
# They are noisy-once now because a SYSTEMATIC quote problem would otherwise be
# indistinguishable from a genuinely illiquid chain: every contract silently
# ranked 9.99 looks exactly like a chain with no liquidity, and the strategy
# would simply stop trading with nothing to read.
_WARNED_CV: set = set()


def _cv_warn(where: str, exc: Exception) -> None:
    """Once per site per process. Fail-closed is the behaviour; silence is not."""
    if where in _WARNED_CV:
        return
    _WARNED_CV.add(where)
    logger.warning(
        "[cv] %s could not evaluate a contract (%s) - FAILING CLOSED, this "
        "contract will not be selected. If this repeats across the chain the "
        "quote source is the problem, not the liquidity.", where, exc)


def liquidity_rank(c) -> tuple:
    """Rank key for "most liquid". LOWER IS BETTER.

    BID/ASK WIDTH FIRST, because it is the only liquidity signal that is
    actually populated: `factor_sweep` found `open_interest` and `volume`
    CONSTANT across the entire joined sample, so the old `open_interest + volume`
    sum was 0 for every contract and selection fell through to its "no OI/vol
    data" branch on every call. Width is also what matters on a 0DTE credit
    spread — a nickel-wide quote is what trips a stop on quote noise rather than
    on price. Depth survives only as a tie-break and only when non-zero.
    """
    try:
        bid, ask = float(getattr(c, "bid", 0) or 0), float(getattr(c, "ask", 0) or 0)
        mid = (bid + ask) / 2.0
        width = (ask - bid) / mid if (mid > 0 and ask >= bid) else 9.99
    except Exception as exc:                                   # noqa: BLE001
        _cv_warn("liquidity_rank", exc)
        width = 9.99
    depth = (getattr(c, "open_interest", 0) or 0) + (getattr(c, "volume", 0) or 0)
    return (round(width, 4), -depth)


def quote_ok(c, max_width_pct: float) -> bool:
    """Reject a short leg quoted wider than `max_width_pct` of its mid.

    RANKING ALONE NEVER REFUSES — it returns the least-bad strike even when every
    candidate is broken. On a 0DTE credit spread a nickel of quote noise on a
    wide market moves the spread enough to trip a stop on the QUOTE rather than
    on price. Width needs a FLOOR as well as an ordering.
    """
    try:
        if max_width_pct <= 0:
            return True
        bid, ask = float(getattr(c, "bid", 0) or 0), float(getattr(c, "ask", 0) or 0)
        mid = (bid + ask) / 2.0
        if mid <= 0 or ask < bid:
            return False
        return (ask - bid) / mid <= max_width_pct
    except Exception as exc:                                   # noqa: BLE001
        _cv_warn("quote_ok", exc)
        return False


def pop(distance: float, sigma_per_bar: float, bars_left: float) -> float:
    """P(terminal close on the SAFE side of the short strike) = Phi(z).

        z = distance / (sigma * sqrt(bars_left))

    TIME IS THE POINT: the same distance is a LARGER z later in the session, so a
    strike that fails at 11:15 passes at 14:30 on identical geometry.

    Driftless and normal, deliberately — a drift term would be a forecast, and
    this system's directional forecasts do not separate. Normal understates fat
    tails, so it reads slightly OPTIMISTIC on the extremes.

    Degenerate inputs return 0.0, which FAILS any floor. **A missing ATR must
    never read as a safe trade.**
    """
    try:
        d, sig, n = float(distance), float(sigma_per_bar), float(bars_left)
        if d <= 0 or sig <= 0 or n <= 0:
            return 0.0
        z = d / (sig * math.sqrt(n))
        return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    except Exception as exc:                                   # noqa: BLE001
        _cv_warn("pop", exc)
        return 0.0


def bars_left(now_et_dt, bar_minutes: float, close_et) -> float:
    """Bars of `bar_minutes` remaining until `close_et`.

    The caller passes the horizon. For both credit verticals that is the 15:45
    flatten, NOT the bell — the position is closed there, so using 16:00 would
    overstate T and make every POP look worse than the trade really is.
    """
    try:
        end = now_et_dt.replace(hour=close_et[0], minute=close_et[1],
                                second=0, microsecond=0)
        mins = (end - now_et_dt).total_seconds() / 60.0
        return max(0.0, mins / max(1e-9, float(bar_minutes)))
    except Exception:                                          # noqa: BLE001
        return 0.0


def find_contract_at_strike(contracts: Sequence, strike: float):
    for c in contracts or []:
        try:
            if abs(float(c.strike) - float(strike)) < 1e-6:
                return c
        except Exception:                                      # noqa: BLE001
            continue
    return None


def select_beyond_rail(contracts: List, side: str, rail: float,
                       min_distance_level: float,
                       session_extreme: Optional[float],
                       spot: float = 0.0, sigma: float = 0.0,
                       bars: float = 0.0, min_pop: float = 0.0,
                       max_width_pct: float = 0.0):
    """The short strike, or None.

    A strike qualifies only if it is ALL of:
      1. BEYOND THE RAIL           — the anchor the caller nominated
      2. BEYOND THE MIN DISTANCE   — a breathing-room floor; pass +/-inf to disable
      3. NOT EXCEEDED BY PRICE     — beyond the session extreme; pass None to disable
      4. QUOTED TIGHTLY ENOUGH     — bid/ask width within `max_width_pct`
      5. FAR ENOUGH IN TIME        — POP >= `min_pop`
    Among survivors: MOST LIQUID by bid/ask width, tie-break NEAREST the rail —
    the richest premium that still clears everything.

    ⚠️ RETURNS None RATHER THAN FALLING BACK INWARD. **No inside fallback, ever** —
    that fallback is what sold calls on top of spot for ~3 weeks.
    """
    def beyond(k, level):
        return k >= level if side == "call" else k <= level

    eligible = []
    for c in contracts or []:
        if not (getattr(c, "mark", 0) or 0) > 0.01:
            continue
        k = c.strike
        if not beyond(k, rail):
            continue
        if not beyond(k, min_distance_level):
            continue
        if session_extreme is not None and not beyond(k, session_extreme):
            continue
        if not quote_ok(c, max_width_pct):
            continue
        if min_pop > 0 and spot > 0:
            if pop(abs(k - spot), sigma, bars) < min_pop:
                continue
        eligible.append(c)

    if not eligible:
        priced = [c for c in (contracts or []) if (getattr(c, "mark", 0) or 0) > 0.01]
        logger.info(
            "credit-vertical: no %s strike clears rail %.2f / min-dist %.2f / "
            "extreme %s / POP>=%.2f — %d/%d priced. SKIP (no inside fallback).",
            side, rail, min_distance_level,
            f"{session_extreme:.2f}" if session_extreme is not None else "n/a",
            min_pop, len(priced), len(contracts or []))
        return None

    best = min(liquidity_rank(c) for c in eligible)
    cohort = [c for c in eligible
              if liquidity_rank(c)[0] <= best[0] * 1.5 + 1e-9]
    return (min(cohort, key=lambda c: c.strike) if side == "call"
            else max(cohort, key=lambda c: c.strike))


def leg_order_from_slope(slope: float, flat_eps: float):
    """(leg1, leg2) from a channel's slope, or None when it is FLAT.

    UP-sloping: price travels the LOWER rail toward the UPPER one across the
    session, so the PUT side is the one price is leaving and it fills FIRST.
    DOWN-sloping: mirrored.

    **A SIGN IS NOT A SLOPE** — below `flat_eps` the drift is noise, and ordering
    off it would be reading a coin flip as structure. None means "use proximity".
    """
    if slope is None or abs(slope) < flat_eps:
        return None
    return ("put", "call") if slope > 0 else ("call", "put")
