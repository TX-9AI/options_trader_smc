#!/usr/bin/env python3
"""
tests/test_grd2_underlying_target.py — v1.0 — 2026-08-13

GRD.2 — continuation populates `underlying_target`.

`trend_strike_plan` has ALWAYS computed the target (EM fraction scaled by ADX +
conviction) and USED IT to pick the strike, then discarded it. So the bot was
never target-free; it was **target-blind**, and three consumers sat inert on 77%
of fleet volume.

⚠️ THIS IS NOT A TAKE-PROFIT AND NOTHING CONSUMES IT AS ONE. The operator's
no-target design stands — *"the multiple is a want, not a need... use stops
creatively so nothing stops them running when they're correct."* This is the R
denominator and the trail's reference, not an exit trigger. A test below pins
that no exit fires on the target.

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python -m pytest tests/test_grd2_underlying_target.py -q
"""

import ast
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.join(os.path.dirname(__file__), "..")


def src(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


# ── the assignment itself ──────────────────────────────────────────────────

def test_continuation_assigns_the_target_from_the_plan():
    s = src("strategy/continuation_strategy.py")
    assert 'signal.underlying_target = float(_plan["target_price"] or 0.0)' in s


def test_the_assignment_is_inside_generate_signal():
    """Placement matters: `_plan` is built AFTER the signal is constructed, so
    this cannot live in the OptionsSignal(...) call."""
    s = src("strategy/continuation_strategy.py")
    lines = s.split("\n")
    hit = next(i for i, l in enumerate(lines, 1)
               if "signal.underlying_target" in l)
    fn = None
    for j in range(hit - 1, 0, -1):
        m = re.match(r"    def (\w+)", lines[j - 1])
        if m:
            fn = m.group(1)
            break
    assert fn == "generate_signal", f"assignment landed in {fn}()"


def test_it_runs_only_after_the_plan_succeeded():
    """A failed plan returns before this point — assigning a target from a
    plan that did not resolve would write 0.0 and look populated."""
    s = src("strategy/continuation_strategy.py")
    assert s.index('if not _plan["ok"]') < s.index("signal.underlying_target")


def test_the_field_exists_on_the_signal():
    assert "underlying_target:" in src("strategy/base_strategy.py")


# ── the three consumers ────────────────────────────────────────────────────

def test_pools_in_path_window_needs_a_nonzero_target():
    """With target 0.0 a LONG's window `entry < p < 0.0` is EMPTY BY
    CONSTRUCTION, so `liquidity_clear` was a structural constant at 1.000 —
    not a measured one. That is why the scorer showed it flat."""
    s = src("risk/setup_scorer.py")
    assert "signal.underlying_entry < p.price < signal.underlying_target" in s


def test_post_target_trail_is_guarded_on_the_target():
    """Guarded on `underlying_target > 0`, so continuation always fell back to
    the blunt 85% trail instead of the FVG floor past 100% TP. THIS is the real
    behavioural change — the entry gate barely moves."""
    s = src("execution/exit_engine.py")
    i = s.index("def _update_post_target_trail")
    assert "underlying_target" in s[i:i + 3000]


def test_rrr_returns_None_rather_than_zero_when_levels_are_missing():
    """'No stop planned' and 'worst possible trade' must not collapse into the
    same number, or a MIN_RRR floor would veto every unpopulated signal."""
    s = src("risk/setup_scorer.py")
    i = s.index("def _rrr_of")
    assert "return None" in s[i:i + 1200]


# ── the entry gate barely moves — the claim, pinned ────────────────────────

def test_liquidity_clear_cannot_veto_a_median_continuation_setup():
    """ARITHMETIC, not opinion. `liq_score = max(1 - n*0.25, 0)` at weight 0.20
    removes AT MOST 0.20 from a continuation total whose measured p50 is 0.885,
    against a grade_b bar of 0.55. Even 4+ blocking pools leaves 0.685.

    If this ever fails, the weight or the bar changed and the 'entry gate barely
    moves' claim in the changelog is no longer true."""
    import config
    from risk.setup_scorer import STRATEGY_PROFILES
    prof = STRATEGY_PROFILES["ContinuationStrategy"]
    w = prof["score_weights"]["liquidity_clear"]
    bar = prof["grade_b"]
    p50 = 0.885
    assert p50 - w * 1.0 > bar, (
        f"liquidity_clear (w={w}) can now veto a median setup against "
        f"bar={bar} — the entry gate is no longer inert")


def test_orb_ab_grade_path_is_untouched_by_this_change():
    """`pools_in_path` ALSO selects A/B — but on ORB's path, and ORB already
    populated its target. Continuation's exposure is the SCORE path only, and
    GRD.1 set continuation's grade_a to 1.01 so it cannot grade A regardless."""
    from risk.setup_scorer import STRATEGY_PROFILES
    assert STRATEGY_PROFILES["ContinuationStrategy"]["grade_a"] > 1.0


# ── the operator's design is not violated ──────────────────────────────────

def test_no_exit_fires_on_reaching_the_target():
    """The no-target philosophy stands. `underlying_target` is the R
    denominator and the trail's reference — NOT an exit trigger. If an exit
    ever keys on reaching it, this goes red."""
    s = src("execution/exit_engine.py")
    for bad in ("underlying_target and should_exit",
                'exit_reason = "target_reached"',
                'exit_reason = f"target_reached'):
        assert bad not in s, f"an exit now fires on the target: {bad}"
