#!/usr/bin/env python3
"""
tests/test_afternoon_debit_block.py — v1.0 — 2026-08-13

PRESSURE TEST for main v6.2's afternoon debit block.

Operator, 2026-08-13: *"The only other Long that can fire is either part of a
butterfly or an iron condor vertical spread from 11 o'clock onwards."*

TWO KINDS OF TEST, and the second is the one that matters:

  1. THE PREDICATE — `_afternoon_debit_blocked()` blocks the three debit
     directional strategies past the cutoff, allows them before it, allows the
     butterfly at any hour, and goes inert when DEBIT_BLOCK_ACTIVE is off.

  2. THE POSITION — the condor exemption is POSITIONAL, not conditional. Condor
     legs are exempt because they route through `_execute_condor_leg` BEFORE the
     gate, not because anything checks for them. Nothing in the predicate would
     notice if that ordering were reversed, so a source-order assertion is the
     only thing standing between "condor legs are exempt" and a silent
     regression. This is the same reasoning as the repo's absence canaries.

DELIBERATE-FAILURE CHECKS are included and RUN — each asserts that the test
would go RED against a broken rule. A fixture that cannot fail is not evidence,
and three tests passed this week that should have gone red because the fixture
could not exercise the guard.

READ-ONLY on the repo. No fleet, no live path, no network.

USAGE
    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python -m pytest tests/test_afternoon_debit_block.py -q
"""

import datetime as dt
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config                                                   # noqa: E402
import main                                                     # noqa: E402

CUT = tuple(config.DEBIT_DIRECTIONAL_CUTOFF_ET)
BEFORE = dt.datetime(2026, 8, 13, CUT[0] - 1, 59)
AT     = dt.datetime(2026, 8, 13, CUT[0], CUT[1])
AFTER  = dt.datetime(2026, 8, 13, CUT[0] + 2, 1)

BLOCKED = ("ORBStrategy", "ContinuationStrategy", "SweepReversal")
EXEMPT  = ("ButterflyStrategy", "IronCondorStrategy")


# ── 1. the predicate ────────────────────────────────────────────────────────

def test_debit_directional_blocked_past_cutoff():
    for name in BLOCKED:
        assert main._afternoon_debit_blocked(name, AFTER), name
        assert main._afternoon_debit_blocked(name, AT), f"{name} at the cutoff"


def test_debit_directional_allowed_before_cutoff():
    for name in BLOCKED:
        assert not main._afternoon_debit_blocked(name, BEFORE), name


def test_butterfly_and_condor_never_blocked():
    """The butterfly is the operator's named exception. IronCondorStrategy is
    listed here for completeness — its legs do not reach the gate at all."""
    for name in EXEMPT:
        for when in (BEFORE, AT, AFTER):
            assert not main._afternoon_debit_blocked(name, when), f"{name} {when}"


def test_kill_switch_makes_the_gate_inert():
    old = config.DEBIT_BLOCK_ACTIVE
    try:
        main.DEBIT_BLOCK_ACTIVE = False
        for name in BLOCKED:
            assert not main._afternoon_debit_blocked(name, AFTER), name
    finally:
        main.DEBIT_BLOCK_ACTIVE = old


def test_rule_has_exactly_one_definition():
    """A parallel AFTERNOON_NO_DEBIT_* block was drafted and removed before
    shipping. Two definitions of one rule, later assignment silently winning,
    is the failure this pins shut."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "config.py"),
               encoding="utf-8").read()
    for name in ("DEBIT_DIRECTIONAL_CUTOFF_ET", "DEBIT_DIRECTIONAL_STRATEGIES",
                 "DEBIT_BLOCK_ACTIVE"):
        n = len(re.findall(rf"^{name}\s*=", src, re.M))
        assert n == 1, f"{name} defined {n} times, expected exactly 1"
    # SCOPED TO ASSIGNMENTS, NOT MENTIONS. A bare substring check trips on the
    # changelog entry that DESCRIBES the removal — the canary-prose trap this
    # repo has now hit three times (_orb_quality, main v5.6's absence test, and
    # this one, caught by this very test on its first run). An absence canary
    # must test for a DEFINITION, never for the name appearing anywhere.
    assert not re.findall(r"^AFTERNOON_NO_DEBIT\w*\s*=", src, re.M), \
        "the removed duplicate block came back as a live assignment"


# ── 2. the position — the condor exemption lives here and nowhere else ──────

def test_gate_sits_after_condor_leg_execution():
    """CONDOR LEGS ARE EXEMPT BY ORDERING, NOT BY A CHECK.

    They route through `_execute_condor_leg` earlier in attempt_new_entry and
    return before the gate is reached. Nothing in the predicate would notice if
    that order were reversed — the legs would simply start being blocked, and
    the only symptom would be a credit strategy quietly not trading in the
    afternoon, which is the exact behaviour this whole change is meant to
    PROTECT. Hence a source-order assertion.
    """
    src = open(os.path.join(os.path.dirname(__file__), "..", "main.py"),
               encoding="utf-8").read()
    body = src[src.index("def attempt_new_entry("):]
    i_leg = body.index("_execute_condor_leg(leg_signal")
    i_gate = body.index("_afternoon_debit_blocked(signal.strategy_name")
    assert i_leg < i_gate, (
        "the afternoon debit gate now runs BEFORE condor-leg execution — "
        "condor legs would be blocked in the afternoon, which is the opposite "
        "of the operator's rule")


def test_gate_runs_before_validity_and_scoring():
    """Placed after the signal is chosen but before `is_valid`/scoring, so the
    refused signal is fully formed and the journal records what was refused."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "main.py"),
               encoding="utf-8").read()
    body = src[src.index("def attempt_new_entry("):]
    i_gate = body.index("_afternoon_debit_blocked(signal.strategy_name")
    i_valid = body.index("if not signal.is_valid:")
    assert i_gate < i_valid


# ── 3. deliberate failure — prove these tests CAN go red ────────────────────

def test_deliberate_failure_the_predicate_can_fail():
    """If the strategy set were empty the block would be inert, and
    test_debit_directional_blocked_past_cutoff MUST go red. Asserting that here
    means a future refactor emptying the set cannot pass silently."""
    old = main.DEBIT_DIRECTIONAL_STRATEGIES
    try:
        main.DEBIT_DIRECTIONAL_STRATEGIES = set()
        assert not main._afternoon_debit_blocked("ContinuationStrategy", AFTER), (
            "with an empty strategy set the gate must be inert — if this "
            "asserts, the predicate is not reading the set at all")
    finally:
        main.DEBIT_DIRECTIONAL_STRATEGIES = old
    # and the real rule still holds afterwards
    assert main._afternoon_debit_blocked("ContinuationStrategy", AFTER)


def test_deliberate_failure_the_cutoff_is_actually_read():
    """Move the cutoff past the sample time; the block must switch off. If it
    does not, the predicate is hardcoding an hour somewhere."""
    old = main.DEBIT_DIRECTIONAL_CUTOFF_ET
    try:
        main.DEBIT_DIRECTIONAL_CUTOFF_ET = (23, 59)
        assert not main._afternoon_debit_blocked("ContinuationStrategy", AFTER)
    finally:
        main.DEBIT_DIRECTIONAL_CUTOFF_ET = old
    assert main._afternoon_debit_blocked("ContinuationStrategy", AFTER)


def test_deliberate_failure_the_position_check_can_fail():
    """Prove the ordering assertion is real: on a reversed source it must
    detect the inversion rather than pass on a substring coincidence."""
    fake = ("def attempt_new_entry(\n"
            "    _afternoon_debit_blocked(signal.strategy_name, now_et())\n"
            "    _execute_condor_leg(leg_signal, state, ctx)\n"
            "    if not signal.is_valid:\n")
    body = fake[fake.index("def attempt_new_entry("):]
    assert body.index("_execute_condor_leg(leg_signal") > \
           body.index("_afternoon_debit_blocked(signal.strategy_name"), (
        "the reversed fixture should show the gate FIRST — if it does not, "
        "the real assertion is not testing order")
