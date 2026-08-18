"""
execution/tick_size.py — options_trader_v3 — v1.0 — 2026-08-13   (FRC.3)

THE VENUE'S PRICE GRID — ONE RESOLVER, USED BY EVERY ORDER PATH.

Operator: *"some contracts allow one cent increments others are five cents and
even a few other are $.10"* and *"that should extend to all orders
unambiguously."*

An unpostable limit is not a rounding nit. The venue either REJECTS it — the
order never exists and the setup passes — or SILENTLY ADJUSTS it, which is a
fill at a price nobody chose, with nothing in our logs to explain the
difference. The second is worse, because it looks like it worked.

⚠️ THIS REPLACED A GUESS. The first version keyed off a hardcoded
`PENNY_CLASSES` set. Membership of the Penny Interval Program is a BROKER/OCC
fact that changes over time and is not derivable from anything on this box, so
that list was flagged unverified the day it was written. The venue publishes the
real rule; this reads it.

────────────────────────────────────────────────────────────────────────────
RESOLUTION ORDER — and the point is that ORDER TIME NEVER GUESSES
────────────────────────────────────────────────────────────────────────────
  1. VENUE RULE — `NestedOptionChain.tick_sizes`, a list of
     `TickSize(value, threshold, symbol)`. `threshold` expresses the $3.00
     boundary GENERICALLY, so nothing here hardcodes 3.00 or assumes a single
     breakpoint. Static instrument metadata, so it is fetched once per symbol
     per session and cached.
  2. QUOTE PROOF — a bid of 2.13 PROVES a penny grid. ASYMMETRIC: an off-nickel
     price proves penny, but an on-nickel price proves nothing (0.05 is a
     multiple of 0.01). So this can only ever REFINE downward, never coarsen.
     Free, and a live cross-check on the cached rule.
  3. FALLBACK LIST — `config.PENNY_CLASSES`, last resort, and it LOGS when
     reached so "how often are we still guessing" is a number rather than an
     assumption.

EVERY RESOLUTION CARRIES ITS SOURCE. If a fill ever returns at a price we did
not post, the log must say whether we priced off the venue rule, an inference,
or the guess — otherwise the silent-adjustment failure is undiagnosable.

UNKNOWN STAYS COARSE. No rule and no proof means the widest plausible increment:
a valid price at a slightly worse level beats a rejected or silently adjusted
one.
"""

import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# symbol -> [(threshold_or_None, value)], sorted with None (the catch-all) last
_VENUE_RULES: dict = {}
_FETCH_FAILED: set = set()

COARSE_DEFAULT = 0.10


def cache_venue_rule(symbol: str, tick_sizes) -> bool:
    """Store the venue's rule for a symbol. Returns True if usable.

    `tick_sizes` is the SDK's list of TickSize(value, threshold, symbol).
    A rule with a threshold applies BELOW that threshold; the entry without one
    is the catch-all above it.
    """
    try:
        rules = []
        for t in (tick_sizes or []):
            val = float(getattr(t, "value", 0) or 0)
            if val <= 0:
                continue
            thr = getattr(t, "threshold", None)
            rules.append((float(thr) if thr is not None else None, val))
        if not rules:
            return False
        rules.sort(key=lambda r: (r[0] is None, r[0] if r[0] is not None else 0))
        _VENUE_RULES[str(symbol).upper()] = rules
        logger.info("[tick] venue rule for %s: %s", symbol,
                    " · ".join(f"<{t}:{v}" if t else f"else:{v}" for t, v in rules))
        return True
    except Exception as exc:                                   # noqa: BLE001
        logger.debug("[tick] could not cache rule for %s: %s", symbol, exc)
        return False


def needs_venue_rule(symbol: str) -> bool:
    """True only if we have neither a cached rule NOR a recorded failure.

    ⚠️ THIS GUARD IS LOAD-BEARING. Without it the fetcher fired an SDK call on
    every `fetch_chain()`, which the tick loop calls from three places —
    hundreds of needless requests per box per session and real rate-limit
    exposure on a live path.

    A FAILED attempt counts as answered. Retrying a broken fetch every tick is
    the same hot loop with a worse error rate, and the fallback already logs a
    warning each time it prices off the guess.
    """
    sym = str(symbol or "").upper()
    return sym not in _VENUE_RULES and sym not in _FETCH_FAILED


def mark_fetch_failed(symbol: str) -> None:
    _FETCH_FAILED.add(str(symbol).upper())


def _from_venue(symbol: str, price: float) -> Optional[float]:
    rules = _VENUE_RULES.get(str(symbol).upper())
    if not rules:
        return None
    for thr, val in rules:
        if thr is None or price < thr:
            return val
    return rules[-1][1]


def _proves_penny(*prices) -> bool:
    """True if any observed price is OFF the nickel grid.

    ASYMMETRIC BY CONSTRUCTION. An off-nickel quote proves a penny grid; an
    on-nickel quote proves nothing, because every nickel is also a valid penny.
    So this only ever refines an increment DOWNWARD and can never coarsen one.
    """
    for p in prices:
        try:
            v = float(p)
        except (TypeError, ValueError):
            continue
        if v <= 0:
            continue
        if abs(round(v / 0.05) * 0.05 - v) > 1e-6:
            return True
    return False


def resolve(symbol: str, price: float,
            bid: float = 0.0, ask: float = 0.0) -> Tuple[float, str]:
    """(increment, source). Source is one of venue / quote / list / default."""
    try:
        px = float(price)
    except (TypeError, ValueError):
        return COARSE_DEFAULT, "default"

    venue = _from_venue(symbol, px)
    if venue is not None:
        # A venue rule can still be REFINED by direct evidence: if the book is
        # quoting off-nickel, the grid is finer than a cached rule suggests.
        if venue > 0.01 and _proves_penny(bid, ask):
            logger.debug("[tick] %s venue says %.2f but the quote is off-nickel "
                         "— refining to 0.01", symbol, venue)
            return 0.01, "quote"
        return venue, "venue"

    if _proves_penny(bid, ask):
        return 0.01, "quote"

    try:
        from config import PENNY_CLASSES, PRICE_INCREMENT_BOUNDARY
        sym = str(symbol).upper()
        if sym in _FETCH_FAILED or sym not in _VENUE_RULES:
            logger.warning("[tick] NO VENUE RULE for %s — falling back to the "
                           "PENNY_CLASSES guess. This is the path that should "
                           "never price a live order.", symbol)
        penny = sym in PENNY_CLASSES
        bound = float(PRICE_INCREMENT_BOUNDARY)
        if penny:
            return (0.01 if px < bound else 0.05), "list"
        return (0.05 if px < bound else 0.10), "list"
    except Exception:                                          # noqa: BLE001
        return COARSE_DEFAULT, "default"


def snap(price: float, symbol: str, side: str,
         bid: float = 0.0, ask: float = 0.0) -> Tuple[float, str]:
    """Snap a limit onto the grid, ALWAYS in the trader's favour.

    buy  -> DOWN (never pay more than intended)
    sell -> UP   (never receive less than intended)

    Directional, not nearest. Nearest-rounding makes roughly half of all limits
    MORE aggressive than specified — on a dime grid that is a nickel of
    unrequested aggression per order. Rounding away from the market costs FILL
    PROBABILITY, which `fill_model` measures; rounding INTO the market costs
    money silently, which nothing measures.
    """
    import math
    try:
        px = float(price)
    except (TypeError, ValueError):
        return 0.0, "default"
    inc, src = resolve(symbol, px, bid, ask)
    if inc <= 0:
        return round(px, 2), src
    n = px / inc
    snapped = (math.floor(n + 1e-9) if side == "buy"
               else math.ceil(n - 1e-9)) * inc
    return round(max(inc, snapped), 4), src
