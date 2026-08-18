"""
options_trader_v3/utils/blindness_latch.py — v1.0 — 2026-08-01

WHEN TO PAGE THE OPERATOR BECAUSE THE BOT CANNOT SEE.

The requirement (2026-08-01): if ANY condition blinds the bot — the feed going
down, stale data, a dead heartbeat, or anything else — notify immediately, and
log the exact conditions that caused it.

Two things follow from "anything else", and they shape this file:

  1. The trigger is the SYMPTOM, not a list of causes. Every return-None path in
     market_data funnels through record_blindness(); this latch reads that record
     and never re-derives a cause of its own. A cause list could only ever cover
     the failures already thought of, and the whole point is the ones we haven't.

  2. The forensic snapshot is taken at the FIRST blind tick and held. The latch
     deliberately waits a few ticks before paging, so by the time it fires the
     conditions have often moved — a feed that reconnects mid-outage would
     otherwise report healthy fields alongside an alert, which is the worst
     possible troubleshooting record. First moment wins; later ticks only extend
     the duration.

Lives apart from main.py on purpose: main.py is not importable in the test
environment (SDK, env, systemd), and an alarm nobody can unit-test is an alarm
nobody should trust. See tests/test_blindness_latch.py.

This module decides ONLY when to alert. It sends nothing and reads nothing —
callers pass the blindness record in and act on the returned verdict.
"""

from __future__ import annotations

import os
import time as _time
from typing import Dict, Optional

# Consecutive blind ticks before paging. One transient read failure should not
# reach the operator's phone; a real outage will hold across several. Kept small
# because with 0DTE and live capital, minutes matter.
BLIND_TICKS_BEFORE_ALERT = int(os.environ.get("OT_BLIND_TICKS", "3"))
# Floor on elapsed time as well as tick count, so a fast tick loop cannot page on
# a sub-second flicker.
BLIND_SECONDS_BEFORE_ALERT = float(os.environ.get("OT_BLIND_SECONDS", "45"))

ALERT = "ALERT"
RECOVERED = "RECOVERED"


class BlindnessLatch:
    """Feed it every tick. It returns ALERT once per outage, RECOVERED once when
    sight comes back, and None the rest of the time."""

    def __init__(self, ticks_before_alert: int = BLIND_TICKS_BEFORE_ALERT,
                 seconds_before_alert: float = BLIND_SECONDS_BEFORE_ALERT):
        self._ticks_needed = max(1, ticks_before_alert)
        self._seconds_needed = max(0.0, seconds_before_alert)
        self._blind_ticks = 0
        self._blind_since: Optional[float] = None
        self._first_snapshot: Optional[Dict] = None
        self._alerted = False
        # Preserved ACROSS the reset so the recovery notice can still say how
        # long the outage lasted and what caused it. Without this, _reset()
        # wipes the duration a beat before the caller reports it — the recovery
        # message would read "was blind 0s", which is the one number it exists
        # to carry.
        self.last_outage_s: float = 0.0
        self.last_outage_cause: str = ""

    # ── state the caller reports on ──────────────────────────────────────────
    @property
    def snapshot(self) -> Optional[Dict]:
        """The record captured at the FIRST blind tick of this outage."""
        return self._first_snapshot

    def blind_for_s(self, now: Optional[float] = None) -> float:
        if self._blind_since is None:
            return 0.0
        return (now if now is not None else _time.time()) - self._blind_since

    @property
    def is_alerted(self) -> bool:
        return self._alerted

    # ── the one call the tick loop makes ─────────────────────────────────────
    def update(self, blindness: Optional[Dict],
               now: Optional[float] = None) -> Optional[str]:
        """`blindness` is market_data.last_blindness() — None means the bot can
        see. Returns ALERT, RECOVERED, or None.

        ALERT is returned at most once per outage. RECOVERED is returned only if
        an ALERT was actually sent, so a brief blip that never paged does not
        produce an all-clear for an alarm the operator never received.
        """
        now = now if now is not None else _time.time()

        if blindness is None:
            if self._alerted:
                self.last_outage_s = self.blind_for_s(now)
                self.last_outage_cause = (self._first_snapshot or {}).get("cause", "")
                self._reset()
                return RECOVERED
            self._reset()
            return None

        if self._blind_since is None:
            # first blind tick of this outage — capture and hold
            self._blind_since = now
            self._first_snapshot = dict(blindness)
        self._blind_ticks += 1

        if self._alerted:
            return None
        if (self._blind_ticks >= self._ticks_needed
                and (now - self._blind_since) >= self._seconds_needed):
            self._alerted = True
            return ALERT
        return None

    def _reset(self):
        self._blind_ticks = 0
        self._blind_since = None
        self._first_snapshot = None
        self._alerted = False
