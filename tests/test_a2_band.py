"""
tests/test_a2_band.py — v1.0 — 2026-08-05

Pins A2 as a REPORTED CHARACTERISTIC with a band, not a mutual-exclusion
invariant.

WHY IT CHANGED. A2 was written as "TRENDING and RANGING must never both exceed
0.5" and FAILED every session since the harness existed — sixteen diary
sessions, all 4/5, always the same check. The excavation established that the
invariant is what is wrong: TRENDING reads a ~70-minute lookback and RANGING a
~25-minute one, so a tick scoring both high is a slow uptrend containing a tight
recent range. That is a real, tradeable state. The two labels answer DIFFERENT
QUESTIONS.

THE COST OF LEAVING IT: a permanent standing FAIL makes a NEW A2 failure
invisible. At 224 ticks and at 900 the line reads identically, and sixteen
sessions of "4/5" trained everyone to skip it. A check that always fails is not
a check.

Deliberate-failure check performed when written: restoring `both == 0` turns
test_the_observed_rate_passes red; removing the upper bound turns
test_a_rate_far_above_the_band_still_fails red.
"""

import importlib.util
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
_spec = importlib.util.spec_from_file_location(
    "rc", os.path.join(REPO, "tests", "replay_confluence.py"))
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)


def _world(n_both, n_tot):
    return [{"scores": {rc.TRENDING_BULL: .9, rc.TRENDING_BEAR: 0.0,
                        rc.RANGING: .9 if i < n_both else .1,
                        rc.BREAKOUT_VOLATILE: 0.0, rc.COMPRESSION: 0.0,
                        rc.SWEEP_REVERSAL: 0.0},
             "breakdown": {}, "label": "x"} for i in range(n_tot)]


def _a2(n_both, n_tot):
    return [c for c in rc.acceptance(_world(n_both, n_tot))
            if c[0].startswith("A2")][0]


def test_the_observed_rate_passes():
    """2026-08-05: 224 of 3,652 ticks = 6.1%. Under the old invariant this was
    a FAIL, and it had been every session."""
    name, ok, detail = _a2(224, 3652)
    assert ok, detail
    assert "6.1%" in detail


def test_zero_co_occurrence_passes():
    assert _a2(0, 3652)[1]


def test_a_rate_far_above_the_band_still_fails():
    """The point of keeping it as a check at all: A2 must still be able to raise
    an alarm when the tape genuinely changes."""
    name, ok, detail = _a2(500, 3652)
    assert not ok
    assert "ABOVE BAND" in detail


def test_the_passing_detail_explains_why_it_is_not_a_contradiction():
    """A reader who sees a non-zero count must not conclude something is
    broken — that reading is what the standing FAIL taught for sixteen
    sessions."""
    detail = _a2(224, 3652)[2]
    assert "different lookbacks" in detail
    assert "NOT a contradiction" in detail


def test_the_band_is_named_and_not_buried():
    src = open(os.path.join(REPO, "tests", "replay_confluence.py")).read()
    assert "A2_BAND_HI" in src
    assert "0.08" in src.split("A2_BAND_HI")[1][:40]


def test_the_check_still_reports_the_raw_count():
    """The number has to stay visible — turning a failing check into a silent
    pass would be worse than leaving it failing."""
    detail = _a2(224, 3652)[2]
    assert "224 tick(s)" in detail
