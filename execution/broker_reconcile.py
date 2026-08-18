"""
execution/broker_reconcile.py — LIVE broker⇄DB position reconciliation.
v3.6 — 2026-07-15 — PHANTOM P&L RECOVERY. New pure helpers so a phantom (DB
        open, broker flat — e.g. Jason closed it manually at the broker) can be
        booked at its REAL fill instead of the forced $0.00:
          match_closing_fills(record, orders) — scan broker order history for
            CLOSING legs matching the record's symbols (BUY_TO_CLOSE on short
            roles, SELL_TO_CLOSE on long roles; opening orders never match),
            aggregate per-leg fills across however many orders the manual close
            took, and return (closed_qty, net_price) on the record's own mark
            basis (vertical: short−long; butterfly: lower+upper−2·center).
          phantom_pnl(record, net_price) — the SAME credit-signed P&L math as
            position_manager._execute_exit, so a recovered phantom feeds
            DAILY_LOSS_LIMIT the truth.
        Both are pure (no SDK, no DB) and unit-tested in
        tests/test_phantom_pnl_recovery.py. Callers (main.py v3.6) fetch order
        history once per reconcile pass and fall back to the flagged $0.00 only
        when NO closing order exists (legitimately: expiry, assignment).
        CAVEAT (documented, accepted): matching is by option symbol — two
        same-day records on identical strikes could cross-match; 0DTE re-entry
        on the exact same strikes is rare and the reason field flags recovery.
v3.0 — 2026-07-07 — initial: the brokerage is the source of truth for whether a
        position EXISTS; the DB supplies the management plan. Builds a plan of
        keep / adopt / close-phantom / anomaly from broker positions + DB live
        rows. Pure logic (no SDK, no DB writes) so it is fully unit-testable; the
        caller performs the DB writes and alerts. PAPER never calls this — the DB
        is truth there.
v1.1 — 2026-07-07 — leg_roles(): split a record's option symbols into (short,
        long) so an intraday reconcile can detect a broker-closed SHORT leg
        while the long remains (build_plan only checks any-leg presence).
v3.0 — 2026-07-10 — repo-wide v3.0 bump: Yahoo-Finance purge & data stream
        mapping optimization (all market data now flows from the single
        shared TastyTrade candle feed — see data/candle_feed.py). No logic
        change in this file.

Rules (agreed design):
  - A broker position already represented by a LIVE DB row  -> KEEP (manage from
    the existing plan).
  - A broker position with NO DB plan                       -> ADOPT and manage
    on its own merit: entry = broker average_open_price, side from the broker,
    stop = entry * (1 ∓ ADOPTED_STOP_PCT), managed by the generic adopted exit.
  - A LIVE DB row with NO matching broker position          -> PHANTOM: close it
    (broker wins on existence).
  - Pairing is for LABELLING only: a short leg with a matching long (same
    underlying+expiry+type) is tagged as part of a spread; a short with no such
    long is flagged an ANOMALY (per the account's margin reality a naked short
    should be near-impossible) — but it is still adopted and managed, loudly.
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Optional

from config import ADOPTED_STOP_PCT
from utils.time_utils import ts_for_db

logger = logging.getLogger(__name__)


@dataclass
class ReconcilePlan:
    keep: List[dict]            = field(default_factory=list)  # DB rows confirmed at broker
    adopt: List[dict]           = field(default_factory=list)  # synthesized records to manage+journal
    close_phantom: List[str]    = field(default_factory=list)  # DB trade_ids absent at broker
    anomalies: List[str]        = field(default_factory=list)  # adopted trade_ids that are lone shorts


# ── OCC option symbol parsing ────────────────────────────────────────────────
# Standard 21-char OCC: 6-char root (space-padded) + YYMMDD + C/P + 8-digit
# strike in thousandths. e.g. "AMD   260711C00180000" -> AMD 2026-07-11 call 180.
def parse_occ(symbol: str) -> Optional[dict]:
    if not symbol:
        return None
    s = str(symbol)
    # Tolerate a stray leading dot/streamer form and extra spaces; work off the
    # fixed-width tail (last 15 chars = YYMMDD + C/P + 8-digit strike).
    core = s.lstrip(".").rstrip()
    if len(core) < 15:
        return None
    tail = core[-15:]
    root = core[:-15].strip()
    ymd, cp, strike_raw = tail[:6], tail[6:7].upper(), tail[7:]
    if cp not in ("C", "P") or not ymd.isdigit() or not strike_raw.isdigit():
        return None
    try:
        expiry = f"20{ymd[:2]}-{ymd[2:4]}-{ymd[4:6]}"
        strike = int(strike_raw) / 1000.0
    except Exception:
        return None
    return {
        "underlying": root,
        "expiry": expiry,
        "option_side": "call" if cp == "C" else "put",
        "strike": strike,
    }


def _adopt_record(pos: dict) -> Optional[dict]:
    """Synthesize a manageable TradeRecord from one normalized broker position.
    `pos` keys: symbol, underlying, quantity, direction ('Long'/'Short'),
    average_open_price. Returns None if the OCC symbol can't be parsed."""
    occ = parse_occ(pos.get("symbol", ""))
    if occ is None:
        logger.error(f"Adopt: cannot parse broker symbol {pos.get('symbol','')!r} — skipping")
        return None
    is_short = str(pos.get("direction", "")).lower().startswith("short")
    entry    = float(pos.get("average_open_price", 0) or 0)
    contracts = abs(int(float(pos.get("quantity", 0) or 0)))
    # Stop at the same max-loss degree our normal stops respect, sign-correct:
    # a long loses as premium falls, a short as premium rises.
    if is_short:
        stop = round(entry * (1 + ADOPTED_STOP_PCT), 2)
    else:
        stop = round(entry * (1 - ADOPTED_STOP_PCT), 2)
    return {
        "trade_id":          f"adopt-{uuid.uuid4().hex[:12]}",
        "symbol":            pos.get("underlying") or occ["underlying"],
        "strategy":          "ADOPTED",
        "setup_type":        "orphan_adopted",
        "option_side":       occ["option_side"],
        "strike":            occ["strike"],
        "expiry":            occ["expiry"],
        "contracts":         contracts,
        "entry_premium":     entry,
        "total_cost":        round(entry * contracts * 100, 2),
        "stop_premium":      stop,
        "is_short_position": 1 if is_short else 0,
        "option_symbol":     pos.get("symbol", ""),
        "paper_trade":       0,          # adoption only happens live
        "status":            "open",
        "entry_time":        ts_for_db(),
        "notes":             "adopted from broker (no DB plan)",
    }


def _db_leg_symbols(row: dict) -> set:
    """Every option symbol a DB row could be known by (single leg + spread/
    butterfly legs), so a broker leg can be matched to its owning row."""
    keys = ("option_symbol", "short_symbol", "long_symbol",
            "lower_symbol", "center_symbol", "upper_symbol")
    return {row.get(k) for k in keys if row.get(k)}


def build_plan(broker_positions: List[dict], db_live_rows: List[dict]) -> ReconcilePlan:
    """Pure reconciliation. Inputs:
        broker_positions — normalized dicts (see _adopt_record) for OPEN option
                           positions at the broker.
        db_live_rows     — DB rows currently considered live (unexpired open).
    Returns a ReconcilePlan; the caller does the DB writes + alerts."""
    plan = ReconcilePlan()

    # Map every broker leg symbol -> its position for fast lookup.
    broker_by_symbol = {p.get("symbol"): p for p in broker_positions if p.get("symbol")}
    broker_symbols   = set(broker_by_symbol)

    # 1) KEEP vs PHANTOM: each DB live row must have at least one leg present at
    #    the broker, else it no longer exists -> phantom, close it.
    matched_broker_symbols = set()
    for row in db_live_rows:
        legs = _db_leg_symbols(row)
        present = legs & broker_symbols
        if present:
            plan.keep.append(row)
            matched_broker_symbols |= present
        else:
            plan.close_phantom.append(row.get("trade_id", ""))

    # 2) ADOPT: any broker position not already explained by a DB row.
    to_adopt = [p for sym, p in broker_by_symbol.items()
                if sym not in matched_broker_symbols]
    adopted = []
    for pos in to_adopt:
        rec = _adopt_record(pos)
        if rec is not None:
            rec["_direction"] = "short" if rec["is_short_position"] else "long"
            adopted.append(rec)

    # 3) Pairing pass — LABEL only. A short with a matching unmatched long
    #    (same underlying+expiry+side) is part of a spread; a short with none is
    #    an anomaly (still adopted+managed).
    longs_avail = [r for r in adopted if r["_direction"] == "long"]
    for rec in adopted:
        if rec["_direction"] != "short":
            continue
        partner = next(
            (l for l in longs_avail
             if not l.get("_paired")
             and l["symbol"] == rec["symbol"]
             and l["expiry"] == rec["expiry"]
             and l["option_side"] == rec["option_side"]),
            None,
        )
        if partner is not None:
            partner["_paired"] = True
            rec["_paired"] = True
            rec["notes"] = "adopted short — paired with open long (defined risk)"
        else:
            rec["notes"] = "adopted LONE SHORT — no defining long found (anomaly)"
            plan.anomalies.append(rec["trade_id"])

    # strip scratch keys before handing back
    for rec in adopted:
        rec.pop("_direction", None)
        rec.pop("_paired", None)
        plan.adopt.append(rec)

    return plan


def leg_roles(record: dict) -> tuple:
    """Split a record's option symbols into (short_syms, long_syms) by role, so
    an intraday reconcile can distinguish a broker-closed SHORT leg from a closed
    long. Covers condor legs (short_symbol/long_symbol), butterflies (center is
    the short, wings are long), adopted shorts (is_short_position), and plain
    long singles. Returns (set, set)."""
    short, long = set(), set()
    is_condor = (bool(record.get("is_condor_leg"))
                 or record.get("strategy") == "IronCondorStrategy")
    if is_condor:
        if record.get("short_symbol"):
            short.add(record["short_symbol"])
        if record.get("long_symbol"):
            long.add(record["long_symbol"])
        return short, long
    if record.get("is_butterfly"):
        if record.get("center_symbol"):
            short.add(record["center_symbol"])
        for k in ("lower_symbol", "upper_symbol"):
            if record.get(k):
                long.add(record[k])
        return short, long
    sym = record.get("option_symbol")
    if sym:
        (short if record.get("is_short_position") else long).add(sym)
    return short, long


# ── Phantom P&L recovery (v3.6) — pure, caller supplies order history ────────

def _is_closing(action, want_buy: bool) -> bool:
    """True if a leg's action closes a position of the given role. Tolerates
    enum or string action values ('Buy to Close' / 'Sell to Close')."""
    a = str(getattr(action, "value", action) or "").lower()
    if "to close" not in a:
        return False
    return a.startswith("buy") if want_buy else a.startswith("sell")


def _closing_leg_stats(orders, symbol: str, want_buy: bool):
    """Aggregate fills for `symbol` across every CLOSING leg in `orders` with
    the required direction. Returns (total_qty, weighted_avg_price) — (0, None)
    if nothing filled. Orders may be tastytrade PlacedOrder objects or
    equivalent duck-typed fakes; any order carrying fills counts (a manual
    close that was partially filled then cancelled still closed contracts)."""
    if not symbol:
        return 0.0, None
    qty, notional = 0.0, 0.0
    for order in orders or []:
        for leg in (getattr(order, "legs", None) or []):
            if getattr(leg, "symbol", None) != symbol:
                continue
            if not _is_closing(getattr(leg, "action", ""), want_buy):
                continue
            for f in (getattr(leg, "fills", None) or []):
                q = float(f.quantity)
                qty      += q
                notional += q * float(f.fill_price)
    if qty <= 0:
        return 0.0, None
    return qty, notional / qty


def match_closing_fills(record: dict, orders: list):
    """Find the broker-side CLOSE of `record` inside `orders` (the account's
    order history). Returns (closed_qty, net_price) on the same basis as the
    record's marks — directly comparable to entry_premium — or None if no
    closing fills exist (expiry/assignment leave no closing order; the caller
    falls back to the flagged $0.00 phantom booking).

    closed_qty is the min across legs of (filled / leg ratio): a spread only
    counts as closed to the depth ALL its legs closed."""
    if bool(record.get("is_butterfly", False)):
        # Long fly: wings are long (sell to close), center is short x2 (buy).
        ql, pl = _closing_leg_stats(orders, record.get("lower_symbol", ""),  want_buy=False)
        qc, pc = _closing_leg_stats(orders, record.get("center_symbol", ""), want_buy=True)
        qu, pu = _closing_leg_stats(orders, record.get("upper_symbol", ""),  want_buy=False)
        qty = min(ql, qu, qc / 2.0)
        if qty <= 0 or None in (pl, pc, pu):
            return None
        return qty, round(pl + pu - 2.0 * pc, 4)

    is_vertical = (bool(record.get("is_condor_leg"))
                   or record.get("strategy") == "IronCondorStrategy"
                   or (record.get("short_symbol") and record.get("long_symbol")))
    if is_vertical:
        qs, ps = _closing_leg_stats(orders, record.get("short_symbol", ""), want_buy=True)
        ql, pl = _closing_leg_stats(orders, record.get("long_symbol", ""),  want_buy=False)
        qty = min(qs, ql)
        if qty <= 0 or None in (ps, pl):
            return None
        return qty, round(ps - pl, 4)

    want_buy = bool(record.get("is_short_position"))
    q, p = _closing_leg_stats(orders, record.get("option_symbol", ""), want_buy=want_buy)
    if q <= 0 or p is None:
        return None
    return q, round(p, 4)


def phantom_pnl(record: dict, net_price: float, closed_qty: float = None) -> float:
    """P&L for a recovered phantom close — IDENTICAL credit-signed math to
    position_manager._execute_exit, so the DB realized P&L (and therefore the
    DAILY_LOSS_LIMIT breaker) sees the truth. Uses closed_qty if given (a
    partially-recovered phantom books only what provably closed), else the
    record's full contract count."""
    from config import CONTRACT_MULTIPLIER
    entry     = float(record.get("entry_premium", 0.0) or 0.0)
    contracts = float(closed_qty if closed_qty is not None
                      else record.get("contracts", 0) or 0)
    credit_signed = (bool(record.get("is_condor_leg"))
                     or record.get("strategy") == "IronCondorStrategy"
                     or bool(record.get("is_short_position")))
    per_share = (entry - net_price) if credit_signed else (net_price - entry)
    return round(per_share * contracts * CONTRACT_MULTIPLIER, 2)
