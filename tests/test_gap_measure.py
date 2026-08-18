#!/usr/bin/env python3
"""
tests/test_gap_measure.py — v1.0 — 2026-08-18   (A2.6b)

THE ONLY PRE-OPEN DECISION-TIME INPUT IN THE STACK.

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python -m pytest tests/test_gap_measure.py -q

Every primitive the separation probe has tested — ADX, conviction, the regime
scores, IV skew, the structural columns — needs bars from THIS session to exist.
**The overnight gap is fully formed at 09:30, before a single RTH bar prints.**
If anything collected can speak before the day starts, this is it.

⚠️ AND IT WAS ENTERING ANONYMOUSLY. `atr_series` uses true range with
`prev_close` and the 5m tape is continuous, so a large gap SPIKES ATR at the
open and decays over the window — every consumer sees a volatility number that
is partly last night's news **and cannot tell which part.**

Operator, 2026-08-01: *"the gaps you see overnight from previous close to
current open are big and meaningful, and they have to be reflected somewhere."*

⚠️ FULLY BACKFILLABLE, unlike everything else this week. `tests/gap_backfill.py`
computes it from banked OHLC, so historical rows can be filled retroactively.
**The classification is IMPORTED from that tool, never reimplemented** (§7) —
two copies of the rule would drift and nobody would notice until they disagreed
on a number already acted on.
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.gap_measure import measure_gap                    # noqa: E402


def _frame(prior_close, today_open):
    idx = pd.to_datetime(["2026-08-17 15:55", "2026-08-18 09:30",
                          "2026-08-18 09:35"])
    return pd.DataFrame({"open": [prior_close, today_open, today_open],
                         "close": [prior_close, today_open, today_open]},
                        index=idx)


def test_the_gap_is_measured_from_prior_close_to_todays_open():
    g = measure_gap(_frame(600.0, 606.0))
    assert abs(g["gap_pct"] - 1.0) < 1e-6


def test_it_uses_todays_FIRST_bar_not_the_latest():
    """The gap is a property of the OPEN. Reading the newest bar would make it
    drift all session and stop being a pre-open quantity at all."""
    idx = pd.to_datetime(["2026-08-17 15:55", "2026-08-18 09:30",
                          "2026-08-18 14:00"])
    df = pd.DataFrame({"open": [600.0, 606.0, 640.0],
                       "close": [600.0, 606.0, 640.0]}, index=idx)
    assert abs(measure_gap(df)["gap_pct"] - 1.0) < 1e-6


def test_classification_matches_the_backfill_tool():
    """⚠️ IMPORTED, NOT REDEFINED. A second copy of the CONT/REV rule would
    drift from the historical numbers within a week."""
    from tests.gap_backfill import classify
    assert measure_gap(_frame(600.0, 606.0), prior_dir=1)["gap_class"] == \
        classify(1.0, 1, 0.15)
    assert measure_gap(_frame(600.0, 594.0), prior_dir=1)["gap_class"] == "REV"
    assert measure_gap(_frame(600.0, 606.0), prior_dir=-1)["gap_class"] == "REV"


def test_an_undirected_prior_says_so_rather_than_guessing():
    assert measure_gap(_frame(600.0, 606.0),
                       prior_dir=0)["gap_class"] == "UNDIRECTED"


def test_a_tiny_gap_is_FLAT_not_a_direction():
    assert measure_gap(_frame(600.0, 600.3), prior_dir=1)["gap_class"] == "FLAT"


def test_None_when_the_prior_session_is_not_in_frame():
    """⚠️ NOT 0.0. A gap of exactly zero is a REAL reading — the market opened
    unchanged — and a numeric default would be indistinguishable from it. That
    exact confusion made `flat_angle_deg`, `level_strength` and `vix_at_entry`
    look like measured nulls this week rather than empty columns."""
    idx = pd.to_datetime(["2026-08-18 09:30", "2026-08-18 09:35"])
    df = pd.DataFrame({"open": [600.0, 601.0], "close": [600.0, 601.0]},
                      index=idx)
    assert measure_gap(df) is None
    assert measure_gap(None) is None


def test_a_genuine_zero_gap_is_reported_as_zero_not_None():
    g = measure_gap(_frame(600.0, 600.0))
    assert g is not None and g["gap_pct"] == 0.0


def test_gap_pct_IS_A_COLUMN():
    """⚠️ `is_trend_credit` was written to the record with NO COLUMN and
    crash-looped NFLX every 15 seconds. Persisting a field means adding the
    column, and adding it to the MIGRATION list so existing boxes get it by
    ALTER TABLE rather than needing a rebuild."""
    import re
    s = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                          "database", "trade_logger.py"), encoding="utf-8").read()
    m = re.search(r"CREATE TABLE IF NOT EXISTS trades\s*\((.*?)\n\s*\)", s, re.S)
    cols = set(re.findall(r"^\s*(\w+)\s+(?:TEXT|INTEGER|REAL|BOOLEAN)",
                          m.group(1), re.M))
    assert "gap_pct" in cols
    assert '("gap_pct",' in s, "missing from the migration list"


def test_the_column_default_is_NULL_not_zero():
    s = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                          "database", "trade_logger.py"), encoding="utf-8").read()
    i = s.index("gap_pct           REAL")
    assert "DEFAULT" not in s[i:i + 40]
