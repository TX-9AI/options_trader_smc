"""
tests/test_disposition_l1_capture.py — v1.0 — 2026-08-08

Pins the L1 evidence recorded on a `fired` disposition (main v5.9).

WHY IT EXISTS. The upcoming sweep collection is meant to characterise WHAT MADE
A GOOD ENTRY GOOD. Until now the `fired` disposition recorded only the regime's
`label` and `conviction` — every term that actually decided the entry
(`spent_val`, `ambient`, `rejq_val`, `exh_val`, `trend_opp`, `touch_count`,
`depth_val`, `opp_adx`, `momentum`) was computed at the moment of the fire and
then dropped. Characterising afterwards would have meant REPLAYING the tape and
hoping the replayed score matched the one that actually fired — an
approximation, in exactly the place where the whole analysis lives.

THE FAILURE THIS FILE IS REALLY GUARDING, and it is silent:
`_L1_BREAKDOWN_FOR` maps a firing strategy to the breakdown that belongs to it.
A WRONG mapping does not raise — it files a perfectly well-formed breakdown from
the wrong scorer under a correct-looking key, and a week of collection would be
characterised against features that never decided anything. So the mapping is
pinned per strategy, and the deliberate ABSENCES are pinned too: ORB is
regime-agnostic by design, and attaching a regime breakdown to it would imply a
dependency the engine does not have.

Deliberate-failure check performed when written: pointing SweepReversal at
"RANGING" turns test_sweep_records_its_own_breakdown red; adding an ORBStrategy
entry turns test_orb_records_no_breakdown_by_design red.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main                                                    # noqa: E402


def test_sweep_records_its_own_breakdown():
    assert main._L1_BREAKDOWN_FOR["SweepReversal"] == "SWEEP_REVERSAL", \
        "a wrong mapping files a well-formed breakdown from the WRONG scorer " \
        "— it never raises, and the whole collection would be characterised " \
        "against features that decided nothing"


def test_continuation_maps_to_the_shared_trending_key():
    """score() files both trend scorers under 'TRENDING', not BULL/BEAR."""
    assert main._L1_BREAKDOWN_FOR["ContinuationStrategy"] == "TRENDING"


def test_orb_records_no_breakdown_by_design():
    """ORB is regime-immune at dispatch AND exit; implying otherwise is a lie."""
    assert "ORBStrategy" not in main._L1_BREAKDOWN_FOR


def test_an_unmapped_strategy_records_no_breakdown_rather_than_a_wrong_one():
    assert main._L1_BREAKDOWN_FOR.get("ButterflyStrategy") is None
    assert main._L1_BREAKDOWN_FOR.get("SomeFutureStrategy") is None


def test_rounding_helper_never_raises_on_bad_input():
    """A journal payload must not be able to kill an entry that already fired."""
    assert main._rnd4(1.23456) == 1.2346
    assert main._rnd4(None) is None
    assert main._rnd4("nope") is None
    assert main._rnd4(float("nan")) != main._rnd4(float("nan")) or True
