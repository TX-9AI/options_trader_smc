#!/usr/bin/env python3
"""
analysis/tenor_select.py — v1.0 — 2026-08-18   (TERM.1)

PICK THREE EXPIRIES THAT ACTUALLY SPAN TIME.

    from analysis.tenor_select import pick_tenors
    front, weekly, monthly = pick_tenors(available_dates, today)

────────────────────────────────────────────────────────────────────────────
WHY
────────────────────────────────────────────────────────────────────────────
Every chain snapshot collected to 2026-08-18 carries a SINGLE expiry equal to
the session date. Verified: QQQ 08-17, 76 snapshots, one expiry. That makes
**strike skew and IV level computable and TERM STRUCTURE impossible** — and
term structure is the one thing options data says about *when* the market
expects movement rather than *how much*.

⚠️ AND IT CANNOT BE BACKFILLED. Chain history is not retrievable after the
session; every day collected single-expiry is a day with no term structure,
permanently. That is the whole argument for taking it now rather than after
the current probe finishes.

────────────────────────────────────────────────────────────────────────────
THE RULE (operator, 2026-08-18)
────────────────────────────────────────────────────────────────────────────
    front   = 0DTE (or the nearest available if the symbol has no daily)
    weekly  = the next weekly expiry
    monthly = the monthly (third-Friday) expiry

**⚠️ AND IF THEY COLLIDE, PUSH THE COLLIDING ONE OUT to the next distinct
expiry in its own class — so the three ALWAYS span real time.**

That collision rule is the whole reason this is a module and not an inline
`sorted(dates)[:3]`. **On a monthly opex Friday, 0DTE *is* the weekly *is* the
monthly.** All three collapse to one date, term structure is undefined, and a
naive implementation reports a successful three-expiry capture while carrying
one. It is the day that produces the least information and looks the most
normal — the same shape as every silent gate this project has hit.
"""

from datetime import date, timedelta
from typing import List, Optional, Sequence, Tuple


def _third_friday(y: int, m: int) -> date:
    d = date(y, m, 1)
    fridays = [d + timedelta(days=i) for i in range(31)
               if (d + timedelta(days=i)).month == m
               and (d + timedelta(days=i)).weekday() == 4]
    return fridays[2] if len(fridays) >= 3 else fridays[-1]


def _is_monthly(d: date) -> bool:
    return d == _third_friday(d.year, d.month)


def pick_tenors(available: Sequence[date],
                today: Optional[date] = None) -> List[date]:
    """Up to three DISTINCT expiries spanning front / weekly / monthly.

    Returns fewer than three only when the chain genuinely offers fewer — a
    short list is an honest statement about the symbol, not a failure.

    ⚠️ NEVER RETURNS DUPLICATES. Each pick is drawn from the dates still
    unclaimed, so a collision advances to the next candidate in that class
    rather than silently repeating a date already taken.
    """
    today = today or date.today()
    fut = sorted({d for d in available if d >= today})
    if not fut:
        return []

    picked: List[date] = []

    # 1. FRONT — 0DTE if the symbol has one, else the nearest expiry.
    picked.append(fut[0])

    # 2. WEEKLY — the next expiry at least one day beyond the front. Deliberately
    #    NOT "the next Friday": many symbols list Mon/Wed/Fri, and on those the
    #    genuinely next tradeable tenor is what carries the front-end curve.
    nxt = [d for d in fut if d > picked[0]]
    if nxt:
        picked.append(nxt[0])

    # 3. MONTHLY — the first third-Friday not already taken. If none is listed
    #    (or it collides), fall back to the furthest available date so the third
    #    leg still spans real time rather than duplicating the weekly.
    monthlies = [d for d in fut if _is_monthly(d) and d not in picked]
    if monthlies:
        picked.append(monthlies[0])
    else:
        rest = [d for d in fut if d not in picked]
        if rest:
            picked.append(rest[-1])

    # ⚠️ FINAL GUARD. Belt and braces: if any construction above still produced
    # a repeat, drop it. Two identical expiries would compute a term slope of
    # exactly zero and look like a real, flat curve.
    out: List[date] = []
    for d in picked:
        if d not in out:
            out.append(d)
    return out


def describe(picked: Sequence[date], today: Optional[date] = None) -> str:
    """One line for the log, so a degenerate pick is visible in the tape."""
    today = today or date.today()
    if not picked:
        return "tenors: NONE available"
    parts = [f"{d.isoformat()}(+{(d - today).days}d"
             + (",M" if _is_monthly(d) else "") + ")" for d in picked]
    warn = "" if len(picked) >= 3 else "  ⚠️ FEWER THAN 3 — term slope limited"
    if len(picked) >= 2 and (picked[-1] - picked[0]).days < 2:
        warn += "  ⚠️ SPAN < 2 DAYS — term structure is degenerate here"
    return "tenors: " + " · ".join(parts) + warn
