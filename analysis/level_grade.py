#!/usr/bin/env python3
"""
analysis/level_grade.py — v1.0 — 2026-08-18   (Level.1)

GRADE A LIQUIDITY LEVEL BY WHAT IT IS, NOT BY A BOOLEAN.

    from analysis.level_grade import grade_level
    strength = grade_level("PDH (R2)")        # -> 0.0 .. 1.0

────────────────────────────────────────────────────────────────────────────
WHY
────────────────────────────────────────────────────────────────────────────
`trades.level_strength` came back from the separation probe as **94% ties on
TWO unique values** — read as "level strength does not separate outcomes."

It is not that. Only `sweep_reversal` writes it, and its formula is

    min(1.0, (0.6 if named else 0.2) + min(touch_count, 4) * 0.1)

⚠️ **`touch_count` IS A CONSTANT.** Named pools hardcode it to 1 at creation and
nothing ever increments it — 44,450 of 44,890 ticks read exactly 1. So the
formula collapses to **0.7 (named) or 0.3 (unnamed)**: a boolean wearing a
float's clothing. Two values, which is precisely what the probe measured.

⚠️ AND THE GRADING INPUT NOW EXISTS. Before LIQ.6 (2026-08-15) there was
nothing better to grade on. LIQ.6 gave the mapper a **three-deep ladder with
the rung in the name** — `PDH (R2)`, `NY High (R3)` — and FEED.2 (08-17)
delivered the overnight tape that makes ON High/Low real. This module was
blocked on both and is not any more.

────────────────────────────────────────────────────────────────────────────
THE ORDERING, AND WHY IT IS NOT FITTED
────────────────────────────────────────────────────────────────────────────
Grades are assigned by **how much resting liquidity a level type accumulates**,
which is doctrine, not a regression on outcomes:

    prior-day extremes (PDH/PDL)   — a full session of stops, the deepest pool
    overnight extremes (ON H/L)    — a full off-hours session, thinner tape
    prior session extremes         — Asia/London closed blocks
    today's session extremes       — partial, still forming beneath it
    equal highs/lows               — a magnet, but no session behind it

⚠️ **FITTING THIS ON P&L WOULD BE THE GRADE-INVERSION ERROR AGAIN.** The setup
scorer's weights were fitted and A-grade lost $8,244 while B made $1,893. These
are STATED PRIORS from market structure. They are wrong in a way that can be
MEASURED — that is the point of emitting them.

⚠️ THE RUNG DISCOUNTS, IT DOES NOT RE-RANK. Rung 1 is the nearest untaken
liquidity; rungs 2-3 are where price runs if it takes rung 1. A deeper rung is
the same TYPE of level further away, so it keeps its class and loses a little
weight — it does not become a different kind of level.
"""

import re
from typing import Optional

# ⚠️ ORDER MATTERS: the first pattern that matches wins, so the more specific
# names must precede the general ones. "NY High" must be tested before a bare
# "High", and "Prev Day High" before "Day High".
_CLASSES = (
    (r"\b(PDH|PDL|Prev(ious)?[ _]?Day)\b",                     1.00),
    (r"\b(ON|Overnight)[ _]?(High|Low)\b",                     0.85),
    (r"\b(Asia|London|Globex)[ _]?(High|Low)\b",               0.70),
    (r"\b(NY|RTH|Session)[ _]?(High|Low)\b",                   0.55),
    (r"\bEqual[ _]?(High|Low)s?\b|\bEQH\b|\bEQL\b",            0.40),
)

# each rung beyond the first costs this much; a deeper rung is the same TYPE of
# level further away, not a lesser kind of level.
_RUNG_STEP = 0.10

UNNAMED = 0.15          # an unnamed swing is not nothing, but it is not a pool


def _rung(name: str) -> int:
    m = re.search(r"\(R(\d+)\)", name or "")
    try:
        return max(1, int(m.group(1))) if m else 1
    except Exception:                                          # noqa: BLE001
        return 1


def grade_level(name: Optional[str], is_named: Optional[bool] = None) -> float:
    """0.0-1.0 by level TYPE, discounted by ladder rung.

    ⚠️ RETURNS `UNNAMED` FOR ANYTHING UNRECOGNISED — never 0.0. Zero is a
    legitimate grade only for "no level at all", and a name this module has not
    learned yet is not the same statement as no level. The distinction is the
    one `flat_angle_deg` got wrong (0.0 default vs 0.0 measurement) and the one
    `vix_at_entry` got wrong (default read as data).
    """
    if not name:
        return 0.0 if is_named is False else UNNAMED
    for pat, base in _CLASSES:
        if re.search(pat, name, re.I):
            return round(max(0.05, base - (_rung(name) - 1) * _RUNG_STEP), 4)
    return UNNAMED


def describe(name: Optional[str]) -> str:
    """For the log: the grade AND why, so a misgrade is visible in the tape."""
    g = grade_level(name)
    r = _rung(name or "")
    return f"{name or '(unnamed)'} -> {g:.2f}" + (f" (rung {r})" if r > 1 else "")


def nearest_graded(pools, price: float, within_pct: float = 0.004):
    """(name, grade, distance_pct) for the highest-graded pool near `price`.

    ⚠️ THIS IS THE HALF THAT MATTERS. `level_strength` was written ONLY by
    `sweep_reversal` — a strategy hard-gated at main.py:1325 with a 0.4% live
    win rate. So the column was populated by a strategy that essentially does
    not trade, which is why 94% of the book carried the default. Grading sweep
    better fixes nothing on its own; **every strategy needs to know what it is
    trading INTO.**

    ⚠️ HIGHEST GRADE WINS, NOT NEAREST. A PDH four tenths of a percent away is
    more consequential than an unnamed swing two ticks off — proximity is the
    filter, not the ranking. Distance is returned so a consumer can weigh it,
    rather than being folded in here where nobody can see the trade-off.

    ⚠️ RETURNS None WHEN NOTHING IS NEAR, never a zero grade. "No level within
    range" and "a level of zero strength" are different statements, and
    collapsing them is the exact error that made three columns look like
    measured nulls this week.
    """
    if not pools or not price or price <= 0:
        return None
    best = None
    for p_ in pools:
        try:
            pp = float(getattr(p_, "pool_price", 0) or 0)
            if pp <= 0:
                continue
            dist = abs(pp - price) / price
            if dist > within_pct:
                continue
            nm = getattr(p_, "name", "") or ""
            g = grade_level(nm, getattr(p_, "is_named", None))
            if best is None or g > best[1]:
                best = (nm, g, round(dist, 5))
        except Exception:                                      # noqa: BLE001
            continue
    return best
