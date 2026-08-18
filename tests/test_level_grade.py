#!/usr/bin/env python3
"""
tests/test_level_grade.py — v1.0 — 2026-08-18   (Level.1)

A BOOLEAN WEARING A FLOAT'S CLOTHING.

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python -m pytest tests/test_level_grade.py -q

`trades.level_strength` measured **94% ties on TWO unique values** — read as
"levels do not separate outcomes." Two causes, both collection defects:

⚠️ (1) THE FORMULA COLLAPSED. `min(1.0, (0.6 if named else 0.2) +
min(touch_count,4)*0.1)` — and **`touch_count` IS A CONSTANT**: named pools
hardcode it to 1 at creation and nothing increments it (44,450 of 44,890 ticks
read exactly 1). So it only ever produced **0.7 or 0.3**.

⚠️ (2) ONLY ONE STRATEGY WROTE IT, and that strategy barely trades.
`sweep_reversal` is hard-gated at main.py:1325 with a 0.4% live win rate, so
94% of the book carried the column default. **The probe never measured levels;
it measured an empty column.**

Both are now fixed: graded by TYPE with a rung discount, and written for EVERY
strategy from the nearest pool in ctx.

⚠️ THE GRADES ARE STATED PRIORS, NOT FITTED. Ordering follows how much resting
liquidity a level type accumulates. **Fitting them on P&L would repeat the
grade-inversion error** — the setup scorer's weights were fitted and A-grade
lost $8,244 while B made $1,893. Priors can be wrong in a way that is
MEASURABLE, which is the entire reason to emit them.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.level_grade import (UNNAMED, grade_level,                # noqa: E402
                                  nearest_graded)


class _P:
    def __init__(self, name, price, named=True):
        self.name, self.pool_price, self.is_named = name, price, named


def test_more_than_two_distinct_grades_exist():
    """The defect in one line: the old formula produced exactly TWO values."""
    vals = {grade_level(n) for n in
            ("PDH", "ON High", "Asia High", "NY High", "Equal Highs", "junk")}
    assert len(vals) >= 5


def test_class_ordering_follows_resting_liquidity():
    assert (grade_level("PDH") > grade_level("ON High")
            > grade_level("Asia High") > grade_level("NY High")
            > grade_level("Equal Highs") > UNNAMED)


def test_the_rung_discounts_but_does_not_re_rank():
    """Rung 1 is the nearest untaken liquidity; 2-3 are where price runs if it
    takes rung 1. A deeper rung is the SAME TYPE further away — it must not
    become a lesser KIND of level."""
    assert grade_level("PDH") > grade_level("PDH (R2)") > grade_level("PDH (R3)")
    assert grade_level("PDH (R3)") > grade_level("NY High")


def test_an_unknown_name_is_not_a_zero_grade():
    """⚠️ A name this module has not learned is NOT the same statement as no
    level. Collapsing the two is exactly what made `flat_angle_deg` (0.0
    default vs 0.0 measurement) and `vix_at_entry` (default read as data) look
    like measured nulls."""
    assert grade_level("Some Unnamed Swing") == UNNAMED
    assert grade_level(None) == UNNAMED
    assert grade_level("", is_named=False) == 0.0


def test_highest_grade_wins_not_nearest():
    """A PDH a third of a percent away matters more than an unnamed swing two
    ticks off. Proximity is the FILTER; grade is the RANKING."""
    pools = [_P("NY High", 601.0), _P("PDH", 602.0), _P("Some Swing", 600.1)]
    assert nearest_graded(pools, 600.0)[0] == "PDH"


def test_nothing_near_returns_None_not_a_zero():
    assert nearest_graded([_P("PDH", 900.0)], 600.0) is None
    assert nearest_graded([], 600.0) is None
    assert nearest_graded(None, 600.0) is None


def test_distance_is_returned_not_folded_in():
    """Folding distance into the grade hides the trade-off where no consumer
    can see or override it."""
    out = nearest_graded([_P("PDH", 602.0)], 600.0)
    assert len(out) == 3 and out[2] > 0


def test_the_grade_is_PERSISTED_not_just_computed():
    """⚠️ THE LESSON OF THE WEEK. `direction_conf` separated on the live book
    and was journaled nowhere. `flat_angle_deg` was computed every tick and
    never reached the regime object. The pusher's SHORT lines were captured and
    truncated at the log boundary. **A quantity that is not written to the row
    cannot be tested against outcomes.**"""
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "main.py"), encoding="utf-8").read()
    assert "level_strength    = (float(" in src
    assert 'ctx["level_near"]' in src


def test_a_strategys_own_read_is_not_overwritten():
    """Sweep sets `level_strength` directly from the level it actually swept.
    A generic proximity grade must not clobber a better local read."""
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "main.py"), encoding="utf-8").read()
    i = src.index("level_strength    = (float(")
    assert 'getattr(signal, "level_strength"' in src[i:i + 200]
