"""
tests/test_opening_range.py — v1.0 — 2026-08-17

EXECUTING tests for TCS.3 — `_opening_range` must resolve the 09:30-09:35
bound ALL SESSION, not only while those bars happen to sit inside a 60-bar
rolling 1m frame. Per WORKING_AGREEMENT 21 these call the REAL
`main._opening_range` with constructed frames and assert on the returned
bound — no source-text asserts.

WHY THIS SUITE EXISTS: the v6.7 bound read `ctx["df_1m"]` (capped at 60
bars). The 09:30-09:35 bars leave that window at ~10:35 ET, 25 minutes
before TCS_START_ET (11:00), so trend participation could NEVER fire —
fleet-verified 2026-08-17 (`[tcs] no opening-range` on up to 290/290
evaluated ticks). The defining test below is the one that FAILS on that
code: a 13:00 frame with 09:30 long gone must still produce the bound.

DELIBERATE-FAILURE VERIFICATION: born-red run against pristine `b672ae6`
recorded in the BACKLOG entry.

NOTE: this is the repo's first suite that imports `main` (the function lives
there). Import is guarded by the same broker-SDK stub pattern as
tests/test_audit2_fixes.py, a no-op on the boxes.
"""
import os
import sys
import types
import datetime as _dt

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import tastytrade                                             # noqa: F401
except Exception:
    class _AnyAttr(types.ModuleType):
        def __getattr__(self, name):
            v = type(name, (), {"__getattr__": lambda s, n: s})()
            setattr(self, name, v)
            return v
    for _m in ("tastytrade", "tastytrade.instruments", "tastytrade.order",
               "tastytrade.session", "tastytrade.account",
               "tastytrade.streamer"):
        sys.modules.setdefault(_m, _AnyAttr(_m))

import main                                                       # noqa: E402


def _frame(rows):
    """rows = [(iso_et_timestamp, high, low)] -> ET-indexed OHLC frame."""
    idx = pd.DatetimeIndex([pd.Timestamp(t, tz="America/New_York")
                            for t, _, _ in rows])
    return pd.DataFrame({"high": [h for _, h, _ in rows],
                         "low": [l for _, _, l in rows],
                         "close": [(h + l) / 2 for _, h, l in rows]},
                        index=idx)


def _afternoon_1m(day="2026-08-17"):
    """A realistic 60-bar 1m frame at 13:00 — 09:30 rolled off hours ago."""
    return _frame([(f"{day} {12 + (m + 1) // 60:02d}:{(1 + m) % 60:02d}",
                    101.0, 100.0) for m in range(60)])


def test_tcs3_bound_survives_the_1m_rolloff():
    """THE defect test. At 13:00 the 1m frame no longer reaches 09:30; the 5m
    frame does. The bound must come back — on the code this suite was born
    against, it comes back (None, None) and TC.6 is structurally off."""
    day = "2026-08-17"
    df5 = _frame([(f"{day} 09:30", 105.5, 104.2),
                  (f"{day} 09:35", 105.1, 104.6)] +
                 [(f"{day} {9 + (35 + 5 * k + 5) // 60:02d}:"
                   f"{(35 + 5 * k + 5) % 60:02d}", 104.0, 103.0)
                  for k in range(40)])
    hi, lo = main._opening_range({"df_1m": _afternoon_1m(day), "df_5m": df5})
    assert (hi, lo) == (105.5, 104.2), (
        f"bound lost after the 1m rolloff: ({hi}, {lo}) — trend participation "
        f"has no anchor for its entire 11:00+ window")


def test_tcs3_yesterdays_open_is_never_todays_bound():
    """An RTH-only 5m frame carries ~1.3 sessions, so YESTERDAY'S 09:30 bar is
    usually present too. The date filter must pick today's."""
    df5 = _frame([("2026-08-14 09:30", 99.9, 98.8),      # Friday's open
                  ("2026-08-17 09:30", 105.5, 104.2),
                  ("2026-08-17 09:35", 105.1, 104.6),
                  ("2026-08-17 12:55", 104.0, 103.0)])
    hi, lo = main._opening_range({"df_1m": _afternoon_1m(), "df_5m": df5})
    assert (hi, lo) == (105.5, 104.2), f"stale-session bound: ({hi}, {lo})"


def test_tcs3_early_session_uses_1m_before_first_5m_bar():
    """09:32 — today's 5m bar hasn't printed to the frame yet; the partial 1m
    window is the honest bound-so-far (same semantics the old path had)."""
    day = "2026-08-17"
    df1 = _frame([(f"{day} 09:30", 105.2, 104.5),
                  (f"{day} 09:31", 105.4, 104.9),
                  (f"{day} 09:32", 105.0, 104.7)])
    hi, lo = main._opening_range({"df_1m": df1, "df_5m": None})
    assert (hi, lo) == (105.4, 104.5)


def test_tcs3_non_5m_window_falls_back_to_1m(monkeypatch):
    """ORB_WINDOW_MINUTES not divisible by 5 cannot be resolved by 5m bars —
    the 1m path must own it (and the 5m path must not half-answer)."""
    monkeypatch.setattr(main, "ORB_WINDOW_MINUTES", 7)
    day = "2026-08-17"
    df1 = _frame([(f"{day} 09:{30 + m}", 105.0 + m * 0.1, 104.0)
                  for m in range(9)])                      # 09:30..09:38
    df5 = _frame([(f"{day} 09:30", 999.0, 1.0)])           # must NOT be used
    hi, lo = main._opening_range({"df_1m": df1, "df_5m": df5})
    assert (hi, lo) == (105.6, 104.0)                      # 09:30..09:36 only


def test_tcs3_no_frames_is_none():
    assert main._opening_range({}) == (None, None)
    assert main._opening_range({"df_1m": None, "df_5m": None}) == (None, None)


def test_tcs3_why_1m_alone_was_dead_by_1035():
    """PIN (passes on both worlds, and says so): a 60-bar 1m frame at 13:00
    with no 5m frame CANNOT produce the bound — the documented arithmetic
    behind making 5m primary. If this ever starts passing with a bound, the
    1m cache grew and the design note in `_opening_range` needs revisiting."""
    assert main._opening_range({"df_1m": _afternoon_1m()}) == (None, None)
