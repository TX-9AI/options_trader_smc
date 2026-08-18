"""
strategy/structure.py — options_trader_v3 — v1.0 — 2026-08-14   (TCS.2 stage 1)

WHAT KIND OF TRADE IS THIS RECORD? DERIVED, NEVER CARRIED.

────────────────────────────────────────────────────────────────────────────
⚠️ THIS IS A LIVE DEFECT FIX, NOT GROUNDWORK
────────────────────────────────────────────────────────────────────────────
`is_trend_credit` **IS NOT A COLUMN** in the trades table. It is written into
the in-memory `TradeRecord` dict and never persisted. `get_open_trades_live()`
does `SELECT *`, so **a restart rehydrates an open trend-participation position
with the flag GONE** — and `exit_engine`'s TC.6 branch, gated on
`record.get("is_trend_credit")`, silently stops firing. The position drops into
the condor ladder and picks up the ratchet and the 25%% premium stop.

That is the SAME bug fixed on 2026-08-14 (identity hardcoded in
`_execute_condor_leg`), one level down: fixed for the process that opened the
trade, still broken for any process that inherits it. **A flag that has to be
copied at every hop will eventually be dropped at one of them** — and the hop
that drops this one is a systemctl restart, which happens on every bake.

────────────────────────────────────────────────────────────────────────────
THE FIX: DERIVE FROM WHAT ALREADY SURVIVES
────────────────────────────────────────────────────────────────────────────
`strategy` and `setup_type` are REAL COLUMNS, already written correctly by
`_execute_condor_leg` (`"TrendCreditSpread"` / `trend_credit_short`), and they
already round-trip through the database. So the discriminator needs no new
column and no migration — it needs to STOP BEING A PARALLEL BOOLEAN and start
being a reading of the fields that persist.

⚠️ WHY NOT JUST ADD THE COLUMN. A new column fixes tomorrow and not today: every
position opened before the migration still rehydrates without it, and `SELECT *`
on an older row returns None, which reads as False — the exact failure, silently.
Deriving works on rows that already exist, including the ones open right now.

⚠️ FAILS CLOSED. An unrecognised record returns DIRECTIONAL, the most restrictive
reading: it keeps its ordinary stop and never inherits a credit structure's
management. A misread must never hand a position a LOOSER exit than it earned.
"""

from enum import Enum
from typing import Any, Mapping, Optional


class Structure(str, Enum):
    """The trade shapes the exit engine must tell apart.

    `str` mixin so a value compares and serialises as plain text — a record can
    carry it, a log can print it, and a test can assert on it without importing
    this module.
    """

    DIRECTIONAL = "directional"        # ORB, continuation, sweep — debit, long
    BUTTERFLY = "butterfly"            # debit, three legs
    CONDOR_LEG = "condor_leg"          # credit vertical, sibling-aware
    TREND_PARTICIPATION = "trend_participation"   # credit vertical, ORB-bounded


CREDIT_STRUCTURES = frozenset({Structure.CONDOR_LEG,
                               Structure.TREND_PARTICIPATION})


def of(record: Optional[Mapping[str, Any]]) -> Structure:
    """Classify a trade record. Reads ONLY fields that are real columns.

    Order matters: the most specific test first, because a trend-participation
    leg and a condor leg are both credit verticals and only `strategy` /
    `setup_type` tell them apart.
    """
    if not record:
        return Structure.DIRECTIONAL

    strat = str(record.get("strategy") or "").strip().lower()
    setup = str(record.get("setup_type") or "").strip().lower()

    # TREND PARTICIPATION — `strategy` is authoritative and persisted.
    # `setup_type` is checked too because rows written BEFORE the 2026-08-14
    # identity fix carry `strategy="IronCondorStrategy"` with
    # `setup_type="trend_credit_short"`. Those rows are mislabelled at the
    # strategy level and the setup type is the only surviving truth.
    if "trendcredit" in strat.replace("_", "") or setup.startswith("trend_credit"):
        return Structure.TREND_PARTICIPATION

    if "ironcondor" in strat.replace("_", ""):
        return Structure.CONDOR_LEG

    if "butterfly" in strat.replace("_", "") or setup.startswith("butterfly"):
        return Structure.BUTTERFLY

    # ⚠️ FAIL CLOSED. Unknown means ordinary directional management — the most
    # restrictive reading. Never hand a position a looser exit than it earned.
    return Structure.DIRECTIONAL


def is_credit_vertical(record: Optional[Mapping[str, Any]]) -> bool:
    return of(record) in CREDIT_STRUCTURES


def is_trend_participation(record: Optional[Mapping[str, Any]]) -> bool:
    """Replaces `record.get("is_trend_credit")`.

    ⚠️ THE OLD FLAG IS STILL HONOURED when present, because a position opened by
    a process running the previous build carries it in memory and its
    `strategy` field is already correct anyway — so the two agree. What changes
    is that its ABSENCE is no longer read as "not a trend participation trade",
    which is what a restart produced.
    """
    if record and record.get("is_trend_credit"):
        return True
    return of(record) is Structure.TREND_PARTICIPATION
