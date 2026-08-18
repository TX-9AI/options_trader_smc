#!/usr/bin/env python3
# tests/canary_continuation_fvg_pullback.py — post-deploy canary for the
# continuation FVG-pullback rewire (v1.3). Run on a box AFTER deploy, where the
# tastytrade SDK exists:  python tests/canary_continuation_fvg_pullback.py
# Exit 0 = healthy. Non-zero = investigate. Proves the FVG-tag trigger fires
# where the old BB-midline trigger would not, and that grazes/no-gap don't fire.

import sys
import pandas as pd
from types import SimpleNamespace as NS


def main():
    ok = True
    def check(name, cond):
        nonlocal ok
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        ok = ok and cond

    # the strategy imports the full stack (tastytrade etc.) — on a box that's fine
    try:
        import inspect
        import strategy.continuation_strategy as cs
        from analysis.regime_classifier import Regime
        clss = [o for n, o in inspect.getmembers(cs, inspect.isclass)
                if "ontinuation" in n and o.__module__ == cs.__name__]
        Strat = clss[0]
        strat = Strat()
        check("continuation strategy imports", True)
        check("FVG tag-min constant present", hasattr(cs, "CONTINUATION_FVG_TAG_MIN"))
        check("midline constants REMOVED", not hasattr(cs, "CONTINUATION_MIDLINE_ATR"))
    except Exception as e:
        print(f"  [FAIL] import: {e}")
        return 2

    FVG = lambda t, b, d, f=False: NS(top=t, bottom=b, direction=d, filled=f,
                                      size_pct=0.01, index=0)
    mk = lambda lo, hi: pd.DataFrame([{"open": (lo + hi) / 2, "high": hi,
                                       "low": lo, "close": (lo + hi) / 2}])
    regime = NS(primary_regime=Regime.TRENDING_BULL, conviction=0.66)
    vol = NS(atr_current=5.0, bb_middle=7420.0)
    trend = NS(primary_momentum="ACCELERATING")
    struct = NS(fvgs=[FVG(7433.0, 7430.0, "bullish")])

    def call(px, df, st=struct):
        try:
            return strat.generate_signal(regime=regime, vol_state=vol, trend=trend,
                                         chain=None, current_price=px,
                                         structure=st, df_1m=df)
        except Exception as e:
            print(f"    (generate_signal raised: {e})")
            return "RAISED"

    # SPX-rip geometry: price extended, wick nowhere near the gap -> no fire
    check("no-pullback -> None (SPX-rip case)", call(7447.0, mk(7445.0, 7448.0)) is None)
    # wick tags gap top by 1 cent -> fires (the entry midline missed)
    fired = call(7435.0, mk(7432.99, 7440.0))
    check("1-cent tag -> FIRES", fired is not None and fired != "RAISED")
    # exact-edge graze (0 cent) -> no fire (depth lesson)
    check("0-cent graze -> None", call(7435.0, mk(7433.00, 7440.0)) is None)
    # no FVG -> None (can't manufacture a pullback)
    check("no-FVG -> None", call(7435.0, mk(7432.99, 7440.0), NS(fvgs=[])) is None)

    print("\nCANARY: " + ("HEALTHY — FVG-tag pullback fires where midline would not; "
                          "grazes/no-gap correctly skip" if ok
                          else "PROBLEM — see FAILs above"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
