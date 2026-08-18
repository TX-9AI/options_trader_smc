"""
execution/limit_ladder.py — Mid-anchored limit pricing for entries and exits.
v1.3 — 2026-07-22 — SINGLE PAPER-PRICING AUTHORITY (audit defect T). Paper
        friction was split: singles/butterflies booked the bare mark (v1.2)
        while condor legs and rolled verticals still applied a 1% haircut in
        their own call sites. Both credit and debit paper fills now route
        through this module and honour ONE knob
        (config.PAPER_FILL_SLIPPAGE_PCT, default 0.0) applied AGAINST the
        trade. New: paper_fill_credit() — the credit-side twin of
        paper_fill_price(). Read at CALL time so the knob is monkeypatchable
        and env changes need no restart of this module.
v1.2 — 2026-07-22 — hard-close escalation: 15:40 mark-limits -> 15:45 MARKET.
v1.1 — 2026-07-22 — simplified to MARK-REPRICING (no synthetic tick-walk).

WHY THIS EXISTS
---------------
Before this, single-leg entries AND single-leg exits were MARKET orders, and
spread closes used a fixed $0.10 buffer past mark. On a $0.20 0DTE contract
with a $0.05 spread that is ~25% of premium round-trip — larger than any edge
the strategies are trying to capture. Every price in this system is derived
from mark ((bid+ask)/2), so the DECISION was made at mid while the FILL paid
the touch on both sides.

THE POLICY
----------
We never cross the spread. We post AT THE MARK and re-post at the NEW mark
every tick (~15s) until filled.

  OPENS   Post at mark and let it sit. Re-priced to the current mark each tick.
          An entry that never fills costs nothing — the trade simply is not
          taken and the strategy re-signals next tick.

  CLOSES  Post at mark, and RE-PRICE to the current mark every tick until it
          fills. This is the important property: because the limit re-anchors
          to the live mark on every retry, it CHASES a falling market down
          instead of parking at a stale price. A stop triggered at 0.60 does
          not sit at 0.60 while the contract prints 0.40 — the next tick posts
          at the new mark, and the next, until it fills.

  The exit TRIGGER (e.g. -40%) decides WHEN to start closing. It NEVER anchors
  WHERE the limit sits. That separation is the whole point.

  THE ONE EXCEPTION — end-of-day flatten. 15:40 ET starts mark-limit reposts;
  15:45 ET sends a MARKET order, no exceptions, because an unfilled 0DTE at the
  bell is an expiry (and an assignment on a short leg), not an overnight hold.
  See hard_close_order_mode().

v1.1 NOTE: v1.0 shaded the limit one tick further past the mark on each urgent
attempt to synthesise a walk toward the touch. That was dropped — bid/ask are
not plumbed through to the exit path (only a combined mark is), so the shade
was guesswork about a spread we cannot see. Re-pricing at a live mark achieves
the same "follow the market" behaviour honestly and never pays a spread we
have not measured.
"""
from __future__ import annotations

from datetime import time as _time
from typing import Optional

# ── HARD-CLOSE ESCALATION — the ONE exception to "never cross" ────────────────
# Everything else in this module posts at the mark and waits. The end-of-day
# flatten cannot wait: an unfilled 0DTE at the bell does not become an
# overnight hold, it becomes an EXPIRY (and, for a short leg, an assignment).
# So the flatten gets a five-minute mark-limit window and then a market order.
#
#   15:40 ET  begin posting mark-limits, re-priced every tick (~15s)
#   15:45 ET  MARKET order. No exceptions. The position closes.
#
# NB this MOVES the start of the flatten sweep earlier (it was a single 15:45
# market sweep). The extra five minutes is what buys the chance of a mark fill.
HARD_CLOSE_LIMIT_START_ET = _time(15, 40)
HARD_CLOSE_MARKET_AT_ET   = _time(15, 45)


def hard_close_order_mode(now_et) -> str:
    """'limit' | 'market' | 'none' for the end-of-day flatten.

    now_et : timezone-aware ET datetime (or a datetime.time)

    'none'   before 15:40 — the flatten window has not opened.
    'limit'  15:40-15:44  — post at the mark, re-price each tick, try to fill
                            without paying the spread.
    'market' 15:45 onward — the position MUST close; cross and be done.
    """
    t = now_et.time() if hasattr(now_et, "time") else now_et
    if t >= HARD_CLOSE_MARKET_AT_ET:
        return "market"
    if t >= HARD_CLOSE_LIMIT_START_ET:
        return "limit"
    return "none"


def limit_at_mark(mark: float,
                  cap: Optional[float] = None,
                  floor: Optional[float] = None,
                  symbol: str = "", side: str = "",
                  bid: float = 0.0, ask: float = 0.0) -> float:
    """The limit price to post this attempt: the CURRENT mark, always.

    mark  : live mark ((bid+ask)/2, or the combined mark for a spread)
    cap   : optional hard ceiling — a vertical can never be worth more than its
            width, so a close is bounded even if the mark is garbage
    floor : optional hard floor — never post below one tick

    Callers re-invoke this every retry tick with a FRESH mark; that re-anchoring
    is what makes the order track the market instead of going stale.
    """
    if mark is None or mark < 0:
        raise ValueError("limit_at_mark: mark must be a non-negative number")
    px = float(mark)
    if cap is not None:
        px = min(px, float(cap))
    if floor is not None:
        px = max(px, float(floor))
    # v1.4 — SNAP TO THE VENUE GRID. `round(px, 2)` posted UNPOSTABLE prices on
    # nickel and dime classes, and this function prices EVERY exit plus the
    # 15:40-15:44 flatten reposts — far more orders than the entry ladder. An
    # invalid limit is rejected, or SILENTLY ADJUSTED, and a silent adjustment
    # is a fill at a price nobody chose. Degrades to round(px, 2) if the
    # resolver is unavailable, so a cold import can never break pricing.
    if symbol:
        try:
            from execution.tick_size import snap as _snap
            px, _src = _snap(px, symbol, side or "buy", bid, ask)
            return px
        except Exception:                                      # noqa: BLE001
            pass
    return round(px, 2)


def _paper_friction() -> float:
    """config.PAPER_FILL_SLIPPAGE_PCT, read at CALL time, clamped to >= 0.

    Imported inside the function on purpose: this module stays a pure pricing
    primitive at import time (no config dependency to break a cold import),
    and a call-time read means a monkeypatched or re-loaded config takes
    effect immediately. Any failure degrades to 0.0 — the frictionless mark,
    which is the documented default anyway.
    """
    try:
        from config import PAPER_FILL_SLIPPAGE_PCT as _pct
        pct = float(_pct)
        return pct if pct > 0.0 else 0.0
    except Exception:
        return 0.0


def paper_fill_price(mark: float,
                     cap: Optional[float] = None,
                     floor: Optional[float] = None) -> float:
    """The price PAPER books — the same mark-limit live would have posted.

    Paper previously filled exits at exact mark with ZERO friction while live
    sent MARKET orders, so paper P&L was optimistic by roughly half the spread
    on every exit. Under the mark-limit policy live also targets the mark, so
    paper and live now trade on the same principle.

    LIMITATION, stated plainly: paper assumes the mark-limit FILLS on the
    attempt it is posted. Live may sit unfilled for several ticks, or never
    fill if the mark keeps running away. So paper is now honest about PRICE but
    still optimistic about FILL RATE — the residual gap to model later is
    no-fill risk, not slippage.

    v1.3: honours config.PAPER_FILL_SLIPPAGE_PCT (default 0.0 = book the
    mark). Non-zero pays MORE on a debit — friction always runs against the
    trade. Use it to stress paper against measured live fill quality.
    """
    return limit_at_mark(float(mark) * (1.0 + _paper_friction()),
                         cap=cap, floor=floor)


def paper_fill_credit(mark: float,
                      cap: Optional[float] = None,
                      floor: Optional[float] = None) -> float:
    """The CREDIT paper books — the credit-side twin of paper_fill_price.

    v1.3: condor legs and rolled verticals receive premium rather than pay it,
    so friction runs the other way: a non-zero knob means RECEIVING LESS than
    the mark. At the default 0.0 this books the mark, matching the mid-credit
    limit live actually posts.

    Before v1.3 these two paths applied the haircut inline in main.py and
    condor_roll.py while singles/butterflies did not — the friction model was
    split across strategies. It is one authority now.

    NOTE the precision difference from paper_fill_price: credits are booked to
    4dp, not rounded to a postable 2dp tick. A condor credit feeds max-loss
    and risk-free-roll arithmetic where the extra precision matters, and the
    pre-v1.3 call sites booked 4dp — preserved deliberately.
    """
    px = float(mark) * (1.0 - _paper_friction())
    if cap is not None:
        px = min(px, float(cap))
    if floor is not None:
        px = max(px, float(floor))
    return round(px, 4)


# ═════════════════════════════════════════════════════════════════════════════
#  ENTRY LIMIT LADDER (v1.4 — 2026-08-13)  ·  FRC.2
# ═════════════════════════════════════════════════════════════════════════════
# Operator's manual technique, in his own worked example:
#   bid 1.95 / ask 2.35 -> mark 2.15, spread 0.40. "I would try 2.05, 2.10 and
#   then 2.15."
# So the rungs are fractions of the HALF-spread, out from the mark toward the
# near side, stepping every ENTRY_LADDER_STEP_SEC:
#       2.05 = mark - 0.50*half   ·   2.10 = mark - 0.25*half   ·   2.15 = mark
# Mirrored for a sell (2.25 / 2.20 / 2.15).
#
# ⚠️ WHY v1.0's VERSION WAS REMOVED AND THIS ONE IS DIFFERENT. v1.1 dropped the
# old shade because it moved a FIXED NUMBER OF TICKS past the mark without
# knowing the spread — "guesswork about a spread we cannot see". This is
# expressed as a FRACTION OF THE MEASURED SPREAD and takes bid/ask explicitly,
# so it is never guessing: a penny-wide quote shades a fraction of a cent, a
# dollar-wide quote shades twenty. Same objection, different mechanism.
#
# ⚠️ MINIMUM TICK. The operator's example splits 0.40 into clean nickels, but on
# a 0.04-wide quote the same fractions give 2.05 / 2.06 / 2.07 — steps the venue
# rounds away. Without a floor the ladder would post three identical prices and
# burn 45 seconds pretending to walk. Rungs that collapse onto a neighbour are
# DROPPED, so a narrow quote simply has fewer rungs.
#
# ⚠️ THIS IS PRICING ONLY. It does not decide whether to trade, and it must NOT
# be used to book a paper fill on its own — see `fill_model.would_fill()`.
# Posting an aggressive limit and ASSUMING it fills manufactures edge: the
# better the rung, the larger the fake gain.

def price_increment(symbol: str, price: float) -> float:
    """The venue's minimum quote increment for this contract.

    TWO DIMENSIONS, and getting either wrong posts an unpostable limit:
      PENNY class      -> $0.01 below $3.00, $0.05 at/above
      NON-PENNY class  -> $0.05 below $3.00, $0.10 at/above

    UNKNOWN SYMBOLS ARE TREATED AS NON-PENNY. That is the conservative
    direction: a coarser increment is always a VALID price, while a finer one
    may be rejected — or worse, silently adjusted by the venue, which is a fill
    at a price nobody chose and nothing in our logs would explain.
    """
    try:
        px = float(price)
    except (TypeError, ValueError):
        return 0.05
    try:
        from config import PENNY_CLASSES, PRICE_INCREMENT_BOUNDARY
        penny = str(symbol or "").upper() in PENNY_CLASSES
        bound = float(PRICE_INCREMENT_BOUNDARY)
    except Exception:                                          # noqa: BLE001
        penny, bound = False, 3.00
    if penny:
        return 0.01 if px < bound else 0.05
    return 0.05 if px < bound else 0.10


def round_to_increment(price: float, symbol: str, side: str) -> float:
    """Snap a limit to a postable price, ALWAYS in the trader's favour.

    buy  -> round DOWN (never pay more than intended)
    sell -> round UP    (never receive less than intended)

    Directional on purpose. Nearest-rounding would make roughly half of all
    rungs MORE aggressive than the operator specified — on a dime class that is
    a nickel of unrequested aggression per rung, which is a quarter of the very
    edge this ladder exists to capture. Rounding away from the market costs fill
    probability, and fill probability is measured by `fill_model`; rounding INTO
    the market costs money silently.
    """
    import math
    try:
        px = float(price)
    except (TypeError, ValueError):
        return 0.0
    inc = price_increment(symbol, px)
    if inc <= 0:
        return round(px, 2)
    n = px / inc
    snapped = (math.floor(n + 1e-9) if side == "buy"
               else math.ceil(n - 1e-9)) * inc
    return round(max(inc, snapped), 2)


def entry_ladder_prices(bid: float, ask: float, side: str,
                        rungs=None, min_tick: float = None,
                        symbol: str = ""):
    """Limit prices to post, in order, walking from aggressive toward the mark.

    side: "buy" pays UP toward the ask, so its rungs sit BELOW the mark.
          "sell" receives, so its rungs sit ABOVE the mark.
    rungs: fractions of the HALF-spread out from the mark. Defaults to
           config.ENTRY_LIMIT_LADDER.

    Returns [] on an unusable quote (crossed, zero, missing) — an empty ladder
    means the caller falls back to `limit_at_mark`, never to a guess.
    """
    try:
        b, a = float(bid), float(ask)
    except (TypeError, ValueError):
        return []
    if b <= 0 or a <= 0 or a < b:
        return []
    if rungs is None:
        try:
            from config import ENTRY_LIMIT_LADDER as _r
            rungs = list(_r)
        except Exception:                                      # noqa: BLE001
            rungs = [0.50, 0.25, 0.00]

    mark = (a + b) / 2.0
    half = (a - b) / 2.0
    # The venue's increment, not a hardcoded penny. On a nickel or dime class
    # `round(px, 2)` produces an UNPOSTABLE price — the venue rejects it, or
    # silently adjusts it, and a silently adjusted limit is a fill at a price
    # nobody chose with nothing in the logs to explain it.
    inc, _src = ((None, None) if min_tick is not None else (None, None))
    if min_tick is None:
        from execution.tick_size import resolve as _resolve
        inc, _src = _resolve(symbol, mark, b, a)
    else:
        inc = float(min_tick)
    out = []
    for f in rungs:
        px = mark - half * float(f) if side == "buy" else mark + half * float(f)
        if min_tick is None:
            from execution.tick_size import snap as _snap
            px, _ = _snap(px, symbol, side, b, a)
        else:
            px = round(px, 2)
        # clamp inside the quote — a rung must never post through the far side
        px = max(b, min(a, px))
        if out and abs(px - out[-1]) < inc - 1e-9:
            continue                       # collapsed onto its neighbour
        out.append(px)
    return out
