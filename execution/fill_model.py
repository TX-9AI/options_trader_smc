"""
execution/fill_model.py — options_trader_v3 — v1.0 — 2026-08-13   (FRC.2)

DID THE QUOTE ACTUALLY COME TO OUR LIMIT?

⚠️ THIS MODULE EXISTS BECAUSE THE ENTRY LADDER IS DANGEROUS WITHOUT IT.

`limit_ladder.paper_fill_price` books the posted price and is explicit about the
assumption: *"paper is now honest about PRICE but still optimistic about FILL
RATE — the residual gap to model later is no-fill risk, not slippage."* That is
defensible when paper posts AT THE MARK, because a mark-limit usually fills.

It stops being defensible the moment paper posts INSIDE the spread. An
aggressive limit that is assumed to fill books a better price on every single
trade and never models the entries that were missed — **the more aggressive the
rung, the larger the fake gain.** Rung 1 would look like the best change this
system has ever made, and the improvement would be entirely manufactured.

So: no shading without a fill test. This is that test.

────────────────────────────────────────────────────────────────────────────
THE TEST, and why it is deliberately conservative
────────────────────────────────────────────────────────────────────────────
A BUY limit at L fills only if someone sold at or below L while it rested. The
honest proxy available on this box is the UNDERLYING'S OWN 1m tape via the
option quote we already read each tick:

    BUY  fills if the ASK trades down to L or lower   (ask <= L)
    SELL fills if the BID trades up to L or higher    (bid >= L)

WHY THE FAR SIDE, NOT THE MID: to buy at L, someone must be OFFERING at or
below L. That is the ASK reaching down to us, not the mid drifting. Testing
against the mid would report a fill whenever the mid crossed L, which happens
roughly twice as often — and would recreate exactly the optimism this module
exists to remove.

QUEUE POSITION IS NOT MODELLED and cannot be from this data. A resting limit AT
the touch may still not fill if size ahead of it absorbs the trade. So even this
is optimistic — but it is optimistic about QUEUE, which is second-order, rather
than about PRICE, which is first-order and was previously unmodelled entirely.
State it, do not paper over it.

⚠️ CLOSED TICKS ONLY. A quote sampled mid-tick is a snapshot, not a range. The
caller passes the ticks OBSERVED WHILE THE ORDER RESTED, and each one is a real
sample of where the market was. Feeding a forming bar would count a level that
had not printed.
"""

import logging
from typing import Optional, Sequence

logger = logging.getLogger(__name__)


def would_fill(side: str, limit_price: float,
               quotes: Sequence[dict]) -> Optional[dict]:
    """Did any observed quote reach our resting limit?

    quotes: dicts carrying at least "bid" and "ask", sampled while the order
            rested. Order is preserved so the FIRST touching quote is returned —
            a fill happens at the first opportunity, not the best one.

    Returns the filling quote (with "fill_price") or None. None means NO FILL,
    and the caller must treat that as NO TRADE — not as a trade at a worse
    price. Silently degrading a miss into a fill is the failure this whole
    module exists to prevent.
    """
    try:
        L = float(limit_price)
    except (TypeError, ValueError):
        return None
    if L <= 0 or side not in ("buy", "sell"):
        return None

    for q in (quotes or []):
        try:
            bid = float(q.get("bid") or 0.0)
            ask = float(q.get("ask") or 0.0)
        except (TypeError, ValueError):
            continue
        if bid <= 0 or ask <= 0 or ask < bid:
            continue
        if side == "buy" and ask <= L:
            # someone offered at or below our bid — we get OUR price, not
            # theirs: a resting limit does not improve when the market gaps
            # through it.
            return {**q, "fill_price": L}
        if side == "sell" and bid >= L:
            return {**q, "fill_price": L}
    return None


def walk_ladder(side: str, prices: Sequence[float],
                quotes_per_rung: Sequence[Sequence[dict]]) -> dict:
    """Walk the ladder rung by rung and report what actually happened.

    `quotes_per_rung[i]` is the quotes observed while rung `i` rested. Returns
    {filled, fill_price, rung, rungs_tried, missed_rungs}.

    NOT FILLING IS A REAL OUTCOME and is reported as one. A caller that treats
    `filled=False` as "fill at the last rung anyway" reintroduces the exact
    optimism this replaces, so the shape makes that awkward: there is no price
    in the result when nothing filled.
    """
    tried = 0
    for i, px in enumerate(prices or []):
        tried += 1
        got = would_fill(side, px,
                         quotes_per_rung[i] if i < len(quotes_per_rung) else [])
        if got is not None:
            return {"filled": True, "fill_price": got["fill_price"],
                    "rung": i, "rungs_tried": tried,
                    "missed_rungs": i}
    return {"filled": False, "fill_price": None, "rung": None,
            "rungs_tried": tried, "missed_rungs": tried}
