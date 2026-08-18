#!/usr/bin/env python3
"""
tests/test_swp3_approach_weight.py — v1.0 — 2026-08-13

SWP.3 — the sweep readiness `approach` corroborator's sign is refuted.

THREE INDEPENDENT MEASUREMENTS, none of which knew about the others:
  · LIQ.1 — the London level TRACKS PRICE rather than being approached by it
  · ANT.1 — appr_val -41%, appr_touches -45% against outcome
  · ANT.2 — fitted weights -0.39 / -0.40

⚠️ THE SUBTLE FAILURE THIS SUITE EXISTS TO CATCH is not the removal — it is the
RENORMALISATION. `TR_STAGE_BAR` (0.35) and `TR_ARM_BAR` (0.55) are ABSOLUTE
thresholds against a corroborator sum. Drop 0.25 of weight without
redistributing and every sweep score compresses by a quarter, the arm bar
becomes effectively unreachable, and the sweep track goes quiet — **a silent
behaviour change wearing the costume of a correction.** The sum test below is
the whole point of this file.

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python -m pytest tests/test_swp3_approach_weight.py -q
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analysis.trade_readiness as TR                          # noqa: E402


def test_the_refuted_term_carries_zero_weight():
    assert TR.W_SWEEP_APPR == 0.0


def test_the_corroborator_weights_still_sum_to_one():
    """THE ONE THAT MATTERS. The bars are absolute; the sum is the scale."""
    total = (TR.W_SWEEP_CONV + TR.W_SWEEP_FRESH
             + TR.W_SWEEP_EXH + TR.W_SWEEP_APPR)
    assert abs(total - 1.0) < 1e-6, (
        f"sweep corroborators sum to {total:.3f}, not 1.0 — every sweep score "
        f"is now mis-scaled against TR_ARM_BAR={TR.TR_ARM_BAR}")


def test_the_surviving_weights_keep_their_relative_ratios():
    """Renormalisation must not silently re-rank the factors. Original
    0.30/0.20/0.25 -> conv > exh > fresh, and that ordering has to survive."""
    assert TR.W_SWEEP_CONV > TR.W_SWEEP_EXH > TR.W_SWEEP_FRESH


def test_a_full_score_can_still_reach_the_arm_bar():
    """If every surviving corroborator maxes out, readiness must still be able
    to arm. A sum below the bar would mean the track can never fire."""
    best = TR.W_SWEEP_CONV + TR.W_SWEEP_FRESH + TR.W_SWEEP_EXH
    assert best >= TR.TR_ARM_BAR, (
        f"max achievable sweep readiness {best:.3f} is below the arm bar "
        f"{TR.TR_ARM_BAR} — the track is dead")


def test_a_lone_corroborator_still_stays_under_the_arm_bar():
    """The design intent recorded in the module: 'a lone factor stays under
    TR_ARM_BAR'. Renormalisation must not break that either."""
    for w in (TR.W_SWEEP_CONV, TR.W_SWEEP_FRESH, TR.W_SWEEP_EXH):
        assert w < TR.TR_ARM_BAR, (
            f"a single corroborator at {w} now clears the arm bar alone")


def test_appr_val_is_still_journaled():
    """Weight zero, NOT deleted. The sign is refuted; the right functional form
    is unknown. Keeping the raw field is what makes the follow-up study
    possible without a new collection."""
    src = open(os.path.join(os.path.dirname(__file__), "..",
                            "analysis", "trade_readiness.py"),
               encoding="utf-8").read()
    for field in ('"appr_val"', '"appr_touches"', '"appr_dist_atr"',
                  '"appr_name"'):
        assert field in src, f"{field} was removed — the study data is gone"


def test_the_env_override_is_documented_as_not_standalone():
    """Setting SWEEP_APPR_W alone pushes the sum above 1.0 and inflates every
    score against the absolute bars. The module must say so."""
    src = open(os.path.join(os.path.dirname(__file__), "..",
                            "analysis", "trade_readiness.py"),
               encoding="utf-8").read()
    i = src.index('W_SWEEP_APPR        = _envf')
    seg = src[i:i + 900]
    # match on a phrase that cannot be split by line wrapping — my first two
    # attempts asserted on "Change all four together", which the comment wraps
    # as "Change all four\n# together". Testing prose is fine; testing prose
    # LAYOUT is not.
    assert "RESTORING THIS IS NOT AS SIMPLE" in seg
    assert "not at all" in seg


# ── deliberate failure ─────────────────────────────────────────────────────

def test_deliberate_failure_the_sum_check_can_fail():
    """Prove the sum assertion is reachable rather than vacuous."""
    broken = 0.30 + 0.20 + 0.25 + 0.0
    assert abs(broken - 1.0) > 1e-6, (
        "the un-renormalised weights sum to 1.0, so the check proves nothing")
    assert broken < TR.TR_ARM_BAR + 0.25       # and it would compress the scale
