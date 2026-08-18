"""
tests/test_blindness_latch.py — v1.0 — 2026-08-01.

WHAT THIS EXISTS FOR
    The operator's requirement (2026-08-01) is that ANY condition blinding the
    bot — the feed down, stale data, a dead heartbeat, or anything else — pages
    immediately and logs the exact conditions. An alarm that has never fired is
    an alarm nobody knows works, and main.py is not importable in the test
    environment (SDK, env, systemd), so the decision logic lives in
    utils/blindness_latch.py precisely so it CAN be tested here.

    These assert the four properties that make the alarm trustworthy rather than
    merely present:

      1. It does not page on a transient blip.
      2. It pages EXACTLY ONCE per outage — a tick loop firing every few seconds
         would otherwise turn one outage into a pager storm.
      3. It reports the snapshot from the FIRST blind tick. A feed that
         reconnects mid-outage must not be able to overwrite the record that
         explains what happened.
      4. It never sends an all-clear for an alarm that was never raised, and the
         all-clear still carries the duration and cause after the internal reset.

Run: PYTHONPATH=. pytest tests/test_blindness_latch.py -v
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.blindness_latch import (  # noqa: E402
    ALERT, RECOVERED, BlindnessLatch,
)

T0 = 1_000.0
STALE = {"cause": "BARS_STALE", "timeframe": "5m",
         "fields": {"age_s": "930", "limit_s": "900"}}
HEARTBEAT = {"cause": "HEARTBEAT_STALE", "timeframe": "5m",
             "fields": {"threshold_s": "120"}}


def _latch():
    return BlindnessLatch(ticks_before_alert=3, seconds_before_alert=45)


def test_transient_blip_does_not_page():
    """One bad read is not an outage. Paging on it trains the operator to ignore
    the alarm, which is the same as not having one."""
    latch = _latch()
    assert latch.update(STALE, T0) is None
    assert latch.update(None, T0 + 1) is None
    assert not latch.is_alerted


def test_needs_both_tick_count_and_elapsed_time():
    """A fast tick loop must not satisfy the threshold in under a second."""
    latch = _latch()
    for i in range(10):
        assert latch.update(STALE, T0 + i * 0.1) is None, f"paged at tick {i}"
    assert latch.update(STALE, T0 + 45) == ALERT


def test_pages_exactly_once_per_outage():
    latch = _latch()
    verdicts = [latch.update(STALE, T0 + dt) for dt in (0, 20, 50, 60, 120, 300)]
    assert verdicts.count(ALERT) == 1, verdicts
    assert verdicts.index(ALERT) == 2, verdicts


def test_snapshot_is_from_the_first_blind_tick():
    """The forensic record must survive the outage changing shape underneath it —
    a feed that reconnects mid-outage would otherwise report healthy fields
    alongside the alert, which is the worst possible troubleshooting artifact."""
    latch = _latch()
    latch.update(STALE, T0)
    latch.update(HEARTBEAT, T0 + 20)
    assert latch.update(HEARTBEAT, T0 + 50) == ALERT
    assert latch.snapshot["cause"] == "BARS_STALE", latch.snapshot
    assert latch.snapshot["fields"]["age_s"] == "930"


def test_snapshot_is_a_copy_not_a_live_reference():
    """market_data reuses its record dict; holding a reference would let the next
    failure mutate the evidence for this one."""
    latch = _latch()
    live = dict(STALE)
    latch.update(live, T0)
    live["cause"] = "MUTATED"
    latch.update(live, T0 + 20)
    assert latch.update(live, T0 + 50) == ALERT
    assert latch.snapshot["cause"] == "BARS_STALE"


def test_recovery_only_after_an_actual_alert():
    """No all-clear for an alarm the operator never received."""
    latch = _latch()
    latch.update(STALE, T0)
    assert latch.update(None, T0 + 5) is None
    assert not latch.is_alerted


def test_recovery_fires_once_and_keeps_duration_and_cause():
    """The reset must not wipe the two numbers the all-clear exists to carry."""
    latch = _latch()
    for dt in (0, 20, 50):
        latch.update(STALE, T0 + dt)
    assert latch.update(None, T0 + 142) == RECOVERED
    assert latch.last_outage_s == 142.0
    assert latch.last_outage_cause == "BARS_STALE"
    assert latch.update(None, T0 + 200) is None


def test_a_second_outage_pages_again():
    """The latch must re-arm, or the first outage of the day is the only one the
    operator ever hears about."""
    latch = _latch()
    for dt in (0, 20, 50):
        latch.update(STALE, T0 + dt)
    assert latch.update(None, T0 + 100) == RECOVERED
    verdicts = [latch.update(HEARTBEAT, T0 + 200 + dt) for dt in (0, 20, 50)]
    assert verdicts[-1] == ALERT, verdicts
    assert latch.snapshot["cause"] == "HEARTBEAT_STALE"


def test_blind_duration_is_measured_from_the_first_blind_tick():
    latch = _latch()
    latch.update(STALE, T0)
    latch.update(STALE, T0 + 50)
    assert latch.blind_for_s(T0 + 90) == 90.0


def test_clean_latch_reports_no_outage():
    latch = _latch()
    assert latch.update(None, T0) is None
    assert latch.blind_for_s(T0) == 0.0
    assert latch.snapshot is None
