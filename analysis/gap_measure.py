#!/usr/bin/env python3
"""
analysis/gap_measure.py — v1.0 — 2026-08-18   (A2.6b live path)

MEASURE THE OVERNIGHT GAP INSTEAD OF INHERITING IT AS AN ATR SPIKE.

    from analysis.gap_measure import measure_gap
    g = measure_gap(df_5m)          # -> {"gap_pct": .., "gap_class": ..} or None

────────────────────────────────────────────────────────────────────────────
WHY
────────────────────────────────────────────────────────────────────────────
Operator, 2026-08-01: *"the gaps you see overnight from previous close to
current open are big and meaningful, and they have to be reflected somewhere."*

**They are reflected — anonymously.** `atr_series` uses proper true range with
`prev_close = close.shift(1)` and the 5m tape is continuous, so the first 5m bar
after the open carries `|high − prev_close|` and a large gap **spikes ATR
immediately**, then decays over the window. The 25-bar angle correctly never
sees it (1m is session-scoped; a regression must not span a gap).

⚠️ **NOWHERE IS THE GAP MEASURED AS ITSELF.** No `gap_pct`, no `gap_class`,
nothing conditions on it. Every consumer sees a volatility number that is
partly last night's news and cannot tell which part.

⚠️ **AND IT IS THE ONLY PRE-OPEN DECISION-TIME INPUT IN THE STACK.** Every
other primitive tested — ADX, conviction, the regime scores, IV skew — needs
bars from the session to exist. The gap is **fully formed at 09:30**, before a
single RTH bar prints. If anything collected can speak before the day starts,
this is it.

⚠️ AND UNLIKE EVERYTHING ELSE THIS WEEK, IT IS **FULLY BACKFILLABLE**.
`tests/gap_backfill.py` v1.1 already computes it per (date, symbol) from banked
OHLC. This module is the LIVE path; **the classification is imported from that
tool rather than reimplemented**, so the historical and live numbers cannot
drift apart (§7 — one lineage per quantity).
"""

from typing import Dict, Optional

# ⚠️ IMPORTED, NOT REDEFINED. A second copy of this rule would drift from the
# backfill within a week and nobody would notice until the two disagreed on a
# number that had already been acted on.
try:
    from tests.gap_backfill import classify as _classify
except Exception:                                              # noqa: BLE001
    _classify = None

FLAT_PCT = 0.15          # matches gap_backfill's default


def measure_gap(df_5m, prior_dir: int = 0,
                flat_pct: float = FLAT_PCT) -> Optional[Dict[str, object]]:
    """Overnight gap from the 5m frame, or None when it cannot be established.

    ⚠️ RETURNS None RATHER THAN 0.0 WHEN THE PRIOR SESSION IS NOT IN FRAME.
    A gap of exactly zero is a real and meaningful reading — the market opened
    unchanged. **A default of 0.0 would be indistinguishable from it**, which is
    precisely the confusion that made `flat_angle_deg`, `level_strength` and
    `vix_at_entry` look like measured nulls this week rather than empty columns.

    ⚠️ 5m IS USED BECAUSE IT IS CONTINUOUS ACROSS THE BOUNDARY. The 1m frame is
    session-scoped and reaches back only 1.0h — it cannot see yesterday at all.
    """
    try:
        if df_5m is None or len(df_5m) < 2:
            return None
        idx = df_5m.index
        today = idx[-1].date()
        prior = None
        for i in range(len(df_5m) - 1, -1, -1):
            if idx[i].date() != today:
                prior = i
                break
        if prior is None:
            return None          # only today in frame — cannot see the gap
        prior_close = float(df_5m["close"].iloc[prior])
        # first bar OF TODAY, not the latest bar
        today_open = float(df_5m["open"].iloc[prior + 1])
        if prior_close <= 0:
            return None
        gap_pct = 100.0 * (today_open - prior_close) / prior_close
        out = {"gap_pct": round(gap_pct, 4),
               "gap_abs_pct": round(abs(gap_pct), 4)}
        if _classify is not None:
            out["gap_class"] = _classify(gap_pct, prior_dir, flat_pct)
        return out
    except Exception:                                          # noqa: BLE001
        return None
