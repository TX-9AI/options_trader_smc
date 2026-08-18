#!/usr/bin/env python3
# tests/canary_trend_credit_spread.py — post-deploy canary for TC.4 readiness track.
# LOG-ONLY track, so the canary proves it is WIRED and INERT, not that it trades.
# Run on a box after deploy:  python tests/canary_trend_credit_spread.py
# Exit 0 = healthy (track present, evaluates, gates nothing). Non-zero = investigate.

import sys

def main():
    ok = True
    def check(name, cond):
        nonlocal ok
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        ok = ok and cond

    # 1. module imports and the track is registered
    try:
        from analysis.trade_readiness import TradeReadinessEngine
        eng = TradeReadinessEngine(emit=lambda ev, **s: None)
        check("trend_credit_spread in STRATEGIES", "trend_credit_spread" in eng.STRATEGIES)
        check("track state initialized", "trend_credit_spread" in eng.tracks)
    except Exception as e:
        print(f"  [FAIL] import/registration: {e}")
        return 2

    # 2. the SD bounds are the operator's aware/established/screaming priors
    try:
        from analysis import trade_readiness as tr
        check("aware bound == 1.75", abs(tr.TR_TCS_IMPULSE_SD_LO - 1.75) < 1e-9)
        check("screaming bound == 2.50", abs(tr.TR_TCS_IMPULSE_SD_HI - 2.50) < 1e-9)
    except Exception as e:
        print(f"  [FAIL] bounds: {e}")
        ok = False

    # 3. it evaluates without raising on a minimal ctx and returns R in [0,1]
    try:
        from types import SimpleNamespace as NS
        vol = NS(bb_middle=100.0, bb_upper=102.0, bb_lower=98.0, atr_current=1.0,
                 bb_width_pct=0.5, bb_state="NORMAL")
        trend = NS(primary_momentum="ACCELERATING")
        # no df_1m -> impulse degrades to 0, must NOT raise
        r, f = eng._trend_credit_spread(
            {"vol": vol, "trend": trend, "liq_map": None, "price": 100.5, "df_1m": None},
            NS(primary_regime="TRENDING_BULL", conviction=0.6))
        check("evaluates with no candles (no raise)", 0.0 <= r <= 1.0)
        check("factors journaled (sd_ratio key present)", "sd_ratio" in f)
    except Exception as e:
        print(f"  [FAIL] evaluation: {e}")
        ok = False

    # 4. INERT: non-trending label -> exactly 0 (cannot fire / cannot contribute)
    try:
        r_v, _ = eng._trend_credit_spread(
            {"vol": vol, "trend": trend, "liq_map": None, "price": 100.5, "df_1m": None},
            NS(primary_regime="RANGING", conviction=0.9))
        check("RANGING vetoes to 0 (inert on wrong regime)", r_v == 0.0)
    except Exception as e:
        print(f"  [FAIL] veto: {e}")
        ok = False

    print("\nCANARY: " + ("HEALTHY — track wired, evaluates, gates nothing" if ok
                          else "PROBLEM — see FAILs above"))
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
