#!/usr/bin/env python3
"""
tests/test_dispatch_slot_map.py — v1.1 — 2026-08-17
v1.1 — 2026-08-17 — TCS.3: the one-definition pin's 1800-char segment no
        longer reached the constants after main v6.12's _opening_range
        rewrite grew the docstring; widened to 3600. The pin's intent —
        strategy and engine share ONE window definition — unchanged.
v1.0 — 2026-08-14

THE SLOT MAP, AS SPECIFIED BY THE OPERATOR 2026-08-14, ENFORCED STRUCTURALLY.

    BEFORE 11:00  ORB owns 09:35-11:00. A RUNAWAY is the one condition that
                  frees the slot — it is SLOT ARBITRATION, not anchoring. The
                  freed slot goes to `trend_continuation_handoff` FIRST
                  (dispatch order), and to SweepReversal only on a NAMED level.

    AFTER 11:00   ORB / Continuation / Sweep are ALL blocked (AFD.1 — every one
                  is debit directional). The afternoon is three non-overlapping
                  regimes with one occupant each:
                      condor    RANGING + a live daily pitchfork
                      butterfly 12:00-14:00 + PINNING GEX
                      TC.6      directional trend vote, everything else
                  TC.6 defers when a condor plan holds the symbol.

⚠️ THE DEFECT THIS FILE EXISTS TO PREVENT, found by auditing the paths on
2026-08-14: **AFD.1 was a POST-SELECTION veto.** It ran AFTER every strategy had
been evaluated, so past 11:00 a debit strategy still WON the slot — `signal`
went non-None, TC.6 (which sits behind `if signal is None`) never ran, and only
then was the debit signal refused. **The tick produced no trade at all and the
slot the spec assigns to TC.6 was consumed by a strategy forbidden to trade in
it.** Placing the gate after selection was right for JOURNALLING and wrong for
ARBITRATION.

These are SOURCE-ORDER assertions because the failure is positional. No unit
test of `_afternoon_debit_blocked` could have caught it — the predicate was
always correct; it was simply called too late.

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python -m pytest tests/test_dispatch_slot_map.py -q
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SRC = open(os.path.join(os.path.dirname(__file__), "..", "main.py"),
           encoding="utf-8").read()


def body() -> str:
    i = SRC.index("def attempt_new_entry(")
    return SRC[i:SRC.index("\ndef ", i + 10)]


def at(needle: str) -> int:
    b = body()
    assert needle in b, f"{needle!r} is not in attempt_new_entry"
    return b.index(needle)


# ── the block must be computed BEFORE any strategy is evaluated ────────────

def test_afd_is_computed_before_priority_1():
    assert at("_afd_orb  = _afternoon_debit_blocked") < at("# Priority 1: ORB")


def test_each_debit_dispatch_is_guarded_by_its_own_flag():
    """SKIPPED, not evaluated-then-refused. A strategy that cannot trade in this
    window must not be able to consume the slot."""
    b = body()
    assert "if orb_confirmed and not _afd_orb and (" in b
    assert "if signal is None and not _cont_blocked and not _afd_cont and (" in b
    assert "if signal is None and not _afd_swp and _sweep_setup >= SWEEP_SETUP_FLOOR:" in b


def test_the_post_selection_gate_is_retained_as_defence_in_depth():
    """It costs nothing, still journals a fully-formed refusal, and catches a
    future strategy added to DEBIT_DIRECTIONAL_STRATEGIES that forgets the
    pre-gate."""
    assert at("_afternoon_debit_blocked(signal.strategy_name") > at("# Priority 1: ORB")


# ── the pre-11:00 runaway handoff ──────────────────────────────────────────

def test_continuation_is_dispatched_before_sweep():
    """Continuation gets FIRST REFUSAL on a freed slot; sweep sits behind
    `if signal is None`."""
    assert at("# Priority 2 (was sweep): Trend Continuation.") < \
        at("# Priority 2.5 (was 2): Sweep Reversal.")


def test_post_runaway_sweep_requires_a_NAMED_level():
    """The explicit quality gate for when continuation declines: sweep inherits
    a runaway only on a level a human would name, never an equal-H/L cluster."""
    b = body()
    assert 'if sweep_sig is not None and _is_runaway and not getattr(sweep_sig, "swept_level_name", "")' in b
    assert "runaway hands to continuation; sweep only on named levels" in b


# ── the afternoon occupants ────────────────────────────────────────────────

def test_all_three_debit_strategies_are_in_the_block_list():
    """If one is missing it keeps trading past the cutoff AND keeps eating the
    slot. Sweep is the easy one to forget — it is a debit directional too."""
    import config
    assert config.DEBIT_DIRECTIONAL_STRATEGIES == {
        "ORBStrategy", "ContinuationStrategy", "SweepReversal"}


def test_tc6_is_dispatched_and_defers_to_the_condor():
    b = body()
    assert "_trend_credit_strategy.generate_signal(" in b
    # ⚠️ WIDENED BY AUDIT F5. Deferral used to read the in-memory plan ALONE,
    # which a restart destroys — so an ORPHANED leg freed the symbol and TC.6
    # could open a second credit spread against it. The DB-derived check is now
    # OR'd in, because `is_condor_leg` persists and the plan does not.
    assert "condor_active = (_iron_condor_strategy.has_active_plan" in b
    assert "_condor_leg_open_without_plan()" in b


def test_tc6_receives_the_orb_LEVEL_but_not_the_orb_ENGINE():
    """⚠️ THE DISTINCTION IS THE WHOLE POINT, and this test previously asserted
    a blanket ban because I had over-corrected.

    The operator's rule separates two things: the ORB **ENGINE** (runaway flag,
    slot arbitration, `invalidation_reason`) must not gate an afternoon trade —
    ORB owns 09:35-11:00 and owns nothing after. But the ORB **LEVEL** is a
    price on a chart, and *"those levels are fixtures"*.

    So the call site MUST pass `orb_high`/`orb_low` — recomputed from the TAPE
    by `_opening_range`, never read from the engine — and MUST NOT pass an `orb`
    object or any invalidation state."""
    b = body()
    i = b.index("_trend_credit_strategy.generate_signal(")
    call = b[i:i + 800]
    assert "orb_high" in call and "orb_low" in call, (
        "TC.6 is not receiving the ORB bound — the level is the anchor")
    assert "orb           =" not in call and "invalidation_reason" not in call, (
        "the TC.6 call site passes the ORB ENGINE, not just the level")
    assert "_orb_hi, _orb_lo = _opening_range(ctx)" in b, (
        "the bound is being read from the engine rather than recomputed from "
        "the tape — a restart would wipe it")


def test_the_opening_range_is_derived_from_the_same_window_as_the_engine():
    """One definition, not two. If this drifts, the strategy and the engine
    disagree about where the range is."""
    assert "RTH_OPEN_ET" in SRC and "ORB_WINDOW_MINUTES" in SRC
    i = SRC.index("def _opening_range(")
    seg = SRC[i:i + 3600]   # TCS.3 (v6.12) grew the docstring; window widened
    assert "RTH_OPEN_ET" in seg and "ORB_WINDOW_MINUTES" in seg
    assert 'ctx.get("df_1m")' in seg, "a 5m frame cannot resolve a 5-minute window"


def test_tc6_receives_the_trend_vote_and_session_extremes():
    b = body()
    i = b.index("_trend_credit_strategy.generate_signal(")
    call = b[i:i + 700]
    for arg in ("trend", "session_high", "session_low"):
        assert arg in call, f"TC.6 is not receiving {arg}"


# ── deliberate failure ─────────────────────────────────────────────────────

def test_deliberate_failure_the_ordering_assertions_are_real():
    """Prove the position checks can fail rather than passing on a substring
    coincidence — a reversed fixture must be detected."""
    fake = ("def attempt_new_entry(\n"
            "    # Priority 1: ORB\n"
            "    _afd_orb  = _afternoon_debit_blocked('ORBStrategy', now)\n"
            "\ndef next_fn(): pass\n")
    b = fake[fake.index("def attempt_new_entry("):]
    assert b.index("_afd_orb  = _afternoon_debit_blocked") > b.index("# Priority 1: ORB"), (
        "the reversed fixture should show the block AFTER Priority 1 — if it "
        "does not, the ordering assertion is not testing order")
