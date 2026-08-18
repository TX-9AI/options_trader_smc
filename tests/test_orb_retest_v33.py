"""
tests/test_orb_retest_v33.py — v1.0 — 2026-07-12.
Offline regression for orb_engine v3.3 (grace-band removal) + v3.4 (state rename).
Replays the MU 2026-07-10 reference sequence and the grace-band case that v3.3
closed. No network, no store, no SDK calls beyond import.

Reference tape (MU 07-10, 1m):
  09:48  pokes above the range, CLOSES BACK INSIDE      -> not a break
  09:49  O 971.35 H 975.49 L 971.27 C 973.59            -> BREAK (impulsive candle)
  09:50  green doji: wicks INTO range, closes OUTSIDE   -> RETEST -> fire long
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from analysis.orb_engine import ORBEngine, ORBState

ORB_HIGH, ORB_LOW = 971.50, 958.06


def _engine():
    e = ORBEngine()
    d = e._data
    d.orb_high, d.orb_low = ORB_HIGH, ORB_LOW
    d.orb_width = ORB_HIGH - ORB_LOW
    d.state = ORBState.WAITING_FOR_BREAK
    e._range_date = "2026-07-10"
    return e


def _df(rows):
    # engine reads iloc[-2] (last CLOSED candle); append a forming bar
    rows = rows + [rows[-1]]
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"])


def check(name, got, want):
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  (got {got})")
    return ok


results = []

# 1. 09:48 — wick above, close back inside. NOT a break.
e = _engine()
e._check_for_break(_df([[970.80, 972.10, 970.50, 971.20]]))
results.append(check("09:48 wick-above/close-inside is NOT a break",
                     e._data.state, ORBState.WAITING_FOR_BREAK))

# 1b. v3.5 ORIGIN GATE — candle OPENS ABOVE the range, wicks back in, closes higher.
#     v3.1 accepted this (low_ < orb_high). It never broke OUT of the range; it was
#     already outside. Must NOT be a break.
e = _engine()
e._check_for_break(_df([[972.00, 976.00, 971.30, 975.00]]))   # open 972.00 > orb_high
results.append(check("opens ABOVE range (wick back in) is NOT a break [v3.5]",
                     e._data.state, ORBState.WAITING_FOR_BREAK))

# 1c. v3.5 BUFFER GONE — a close just barely beyond the range IS a break.
#     Old buffer (0.05% = $0.49 on MU) required close > 971.99. 971.60 was ignored.
e = _engine()
e._check_for_break(_df([[971.40, 971.80, 971.10, 971.60]]))   # closes $0.10 clear
results.append(check("close just beyond range IS a break (buffer removed) [v3.5]",
                     e._data.state, ORBState.ARMED_LONG))

# 2. 09:49 — opens inside, closes outside. THE break. Stop = impulsive WICK low.
e = _engine()
e._check_for_break(_df([[971.35, 975.49, 971.27, 973.59]]))
results.append(check("09:49 break -> ARMED_LONG", e._data.state, ORBState.ARMED_LONG))
results.append(check("stop = impulsive candle LOW (not body)",
                     round(e._data.stop_level, 2), 971.27))

# 3. 09:50 — wick into range, body outside. RETEST -> fire.
e._check_for_retest(_df([[973.50, 974.00, 971.30, 973.60]]))
results.append(check("09:50 retest (wick in, body out) -> OPEN_LONG",
                     e._data.state, ORBState.OPEN_LONG))

# 4. THE v3.3 FIX — retest candle whose BODY closes back INSIDE the range.
#    orb_high*0.999 = 970.53, so a 971.00 close sat inside the old grace band and
#    was CONFIRMED as a valid retest. It must now DISARM instead.
e = _engine()
e._check_for_break(_df([[971.35, 975.49, 971.27, 973.59]]))
e._check_for_retest(_df([[972.00, 972.20, 970.90, 971.00]]))   # close 971.00 -> INSIDE
results.append(check("body closing INSIDE range disarms (was: fired under grace)",
                     e._data.state, ORBState.INVALIDATED))
results.append(check("...and the reason is close_inside (re-armable)",
                     e._data.invalidation_reason, "close_inside"))

# 5. Runaway — ran to the 50% TP with no retest.
e = _engine()
e._check_for_break(_df([[971.35, 975.49, 971.27, 973.59]]))
tp50 = e._data.target_50pct
e._check_for_retest(_df([[974.00, tp50 + 1.0, 973.90, tp50 + 0.5]]))
results.append(check("runaway to 50% TP without retest -> INVALIDATED",
                     e._data.state, ORBState.INVALIDATED))
results.append(check("...reason=runaway (does NOT re-arm; hands to sweep)",
                     e._data.invalidation_reason, "runaway"))

print("\n" + ("ALL PASS" if all(results) else "FAILURES PRESENT"))
