"""
utils/time_utils.py — Timezone, RTH session helpers, and time utilities.
All bot logic operates in US/Eastern time to match market hours.
v3.1 — 2026-07-13 — NO_ENTRY is READ FROM CONFIG (defect H). It was hardcoded
        as dtime(14, 0), so editing config could not move the global cutoff.
        It now derives from config.GLOBAL_NO_ENTRY_ET.
        NOT a behaviour change: GLOBAL_NO_ENTRY_ET is (14, 0), the same value
        that was hardcoded. Note the config constant this does NOT read is
        ORB_NO_ENTRY_AFTER_ET (11:00) — that is the ORB-scoped cutoff, a
        different rule. Wiring NO_ENTRY to it would silently move the global
        0DTE cutoff three hours earlier.
v3.0 — 2026-07-10 — repo-wide v3.0 bump: Yahoo-Finance purge & data stream
        mapping optimization (all market data now flows from the single
        shared TastyTrade candle feed — see data/candle_feed.py). No logic
        change in this file.
"""

import logging
from datetime import datetime, timezone, timedelta, time as dtime
from typing import Optional, Tuple
import pytz

from config import GLOBAL_NO_ENTRY_ET

logger = logging.getLogger(__name__)

ET = pytz.timezone("US/Eastern")

# RTH boundaries (ET)
RTH_OPEN    = dtime(9, 30)
RTH_CLOSE   = dtime(16, 0)
HARD_CLOSE  = dtime(15, 45)
NO_ENTRY    = dtime(*GLOBAL_NO_ENTRY_ET)   # global 0DTE cutoff — from config
ORB_END     = dtime(9, 35)   # ORB defined by 9:30–9:35 candle


# v3.8 — 2026-07-22 — is_hard_close_time() now opens the flatten window at
# FLATTEN_WINDOW_OPEN (15:40 ET), five minutes before the 15:45 cross, so the
# mark-limit phase has time to fill before the order is forced marketable.

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_et() -> datetime:
    return datetime.now(ET)


def fmt_et_short(dt: Optional[datetime] = None) -> str:
    dt = dt or now_et()
    if dt.tzinfo is None:
        dt = ET.localize(dt)
    return dt.strftime("%m/%d %H:%M ET")


def fmt_et_full(dt: Optional[datetime] = None) -> str:
    dt = dt or now_et()
    if dt.tzinfo is None:
        dt = ET.localize(dt)
    return dt.strftime("%Y-%m-%d %H:%M:%S ET")


def ts_for_db(dt: Optional[datetime] = None) -> str:
    dt = dt or now_utc()
    return dt.isoformat()


def is_rth() -> bool:
    """True if current ET time is within RTH (9:30–16:00 ET, weekdays)."""
    now = now_et()
    if now.weekday() >= 5:   # Saturday=5, Sunday=6
        return False
    t = now.time()
    return RTH_OPEN <= t < RTH_CLOSE


# v3.8: flatten window opens 5 min before the hard cross so the mark-limit
# phase has time to work. Falls back to HARD_CLOSE if config is older.
try:
    from config import FLATTEN_WINDOW_OPEN_ET as _FWO
    FLATTEN_WINDOW_OPEN = dtime(*_FWO)
except Exception:
    FLATTEN_WINDOW_OPEN = HARD_CLOSE


def is_hard_close_time() -> bool:
    """True if the end-of-day flatten window is open (≥ 15:40 ET).

    v3.8: the window now OPENS FIVE MINUTES EARLIER than the hard close itself.
    15:40-15:44 the flatten posts mark-limits (re-priced each tick) so a
    position can close without paying the spread; at 15:45 it crosses and the
    position closes unconditionally. Opening at 15:45 would have left zero time
    for the limit phase — the escalation would never fire before the bell. The
    cross-over instant is still HARD_CLOSE (15:45); see
    execution/limit_ladder.hard_close_order_mode."""
    now = now_et()
    return now.time() >= FLATTEN_WINDOW_OPEN


def is_past_entry_cutoff() -> bool:
    """True if it's past 2:00 PM ET — no new 0DTE entries after this."""
    now = now_et()
    return now.time() >= NO_ENTRY


def is_orb_window() -> bool:
    """True if we're in the 9:30–9:35 ORB definition window."""
    now = now_et()
    if now.weekday() >= 5:
        return False
    t = now.time()
    return RTH_OPEN <= t < ORB_END


def is_orb_complete() -> bool:
    """True if the ORB window has closed and we can look for setups."""
    now = now_et()
    return now.time() >= ORB_END


def minutes_since(dt: datetime) -> float:
    """Minutes elapsed since dt (handles timezone-aware and naive)."""
    now = now_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).total_seconds() / 60


def is_within_minutes(dt: datetime, minutes: float) -> bool:
    return minutes_since(dt) < minutes


def today_et() -> datetime:
    """Today's date at midnight ET."""
    return now_et().replace(hour=0, minute=0, second=0, microsecond=0)


def seconds_until_hard_close() -> float:
    """Seconds until 15:45 ET today."""
    now = now_et()
    hc = now.replace(hour=15, minute=45, second=0, microsecond=0)
    if now >= hc:
        return 0
    return (hc - now).total_seconds()


def seconds_until_rth_open() -> float:
    """Seconds until next RTH open (9:30 ET). Returns 0 if already open."""
    now = now_et()
    if is_rth():
        return 0
    open_today = now.replace(hour=9, minute=30, second=0, microsecond=0)
    if now < open_today and now.weekday() < 5:
        return (open_today - now).total_seconds()
    # Next weekday
    days_ahead = 1
    while (now + timedelta(days=days_ahead)).weekday() >= 5:
        days_ahead += 1
    next_open = (now + timedelta(days=days_ahead)).replace(
        hour=9, minute=30, second=0, microsecond=0
    )
    return (next_open - now).total_seconds()


def current_session_label() -> str:
    """Human-readable session label."""
    now = now_et()
    t = now.time()
    if t < RTH_OPEN:
        return "pre_market"
    if RTH_OPEN <= t < ORB_END:
        return "orb_window"
    if ORB_END <= t < dtime(11, 0):
        return "early_session"
    if dtime(11, 0) <= t < dtime(14, 0):
        return "mid_session"
    if dtime(14, 0) <= t < HARD_CLOSE:
        return "late_session"
    return "closed"
