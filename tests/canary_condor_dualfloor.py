#!/usr/bin/env python3
# tests/canary_condor_dualfloor.py — post-deploy canary for the 2026-07-28
# condor rebuild: 0.80*EM dual floor, outward liquid selection, independent legs,
# and the arm-origin extension clock.
# Run on a BOT box (needs the tastytrade SDK):
#   cd ~/options-trader && PYTHONPATH=. python tests/canary_condor_dualfloor.py
# Exit 0 = healthy.

import sys
from types import SimpleNamespace as NS


def main():
    ok = True
    skipped = []
    def check(name, cond):
        nonlocal ok
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        ok = ok and cond

    # ── 1. config floor present and correct ──────────────────────────────────
    try:
        from config import CONDOR_EM_FLOOR_FRAC
        check("CONDOR_EM_FLOOR_FRAC == 0.80", abs(CONDOR_EM_FLOOR_FRAC - 0.80) < 1e-9)
    except Exception as e:
        print(f"  [FAIL] config floor: {e}")
        return 2

    # ── 2. condor strategy: outward selector exists, inside-fallback gone ─────
    try:
        import strategy.iron_condor_strategy as ic
        cls = ic.IronCondorStrategy if hasattr(ic, "IronCondorStrategy") else None
        if cls is None:
            import inspect
            cls = [o for n, o in inspect.getmembers(ic, inspect.isclass)
                   if "Condor" in n and o.__module__ == ic.__name__][0]
        strat = cls()
        check("_select_beyond_floor exists", hasattr(strat, "_select_beyond_floor"))

        # a chain where NOTHING is beyond the floor -> must return None (skip),
        # never fall back to a near strike (that was the 3-week bug).
        near = [NS(strike=s, mark=1.0, open_interest=100, volume=50)
                for s in (100, 101, 102)]
        got = strat._select_beyond_floor(near, floor_level=110.0, side="call")
        check("no strike beyond floor -> None (no inside fallback)", got is None)

        # with strikes beyond the floor, it selects one that CLEARS the floor
        far = near + [NS(strike=s, mark=0.5, open_interest=200, volume=80)
                      for s in (110, 115, 120)]
        got2 = strat._select_beyond_floor(far, floor_level=110.0, side="call")
        check("selects a strike at/beyond the floor",
              got2 is not None and got2.strike >= 110.0)

        # put side mirrors
        got3 = strat._select_beyond_floor(far, floor_level=95.0, side="put")
        check("put side: None when nothing at/below floor", got3 is None)
    except ModuleNotFoundError as e:
        if "tastytrade" in str(e):
            print(f"  [SKIP] condor selector — SDK not on this box "
                  f"(control box: expected; run on a BOT box for full coverage)")
            skipped.append("condor selector")
        else:
            print(f"  [FAIL] condor selector: {e}"); ok = False
    except Exception as e:
        print(f"  [FAIL] condor selector: {e}")
        ok = False

    # ── 3. independent legs: plan tracks sides separately ────────────────────
    try:
        from strategy.iron_condor_strategy import CondorPlan
        p = CondorPlan()
        check("plan has call_filled/put_filled", hasattr(p, "call_filled") and hasattr(p, "put_filled"))
        check("plan has pending_side", hasattr(p, "pending_side"))
    except ModuleNotFoundError as e:
        if "tastytrade" in str(e):
            print(f"  [SKIP] independent legs — SDK not on this box")
            skipped.append("independent legs")
        else:
            print(f"  [FAIL] independent legs: {e}"); ok = False
    except Exception as e:
        print(f"  [FAIL] independent legs: {e}")
        ok = False

    # ── 4. arm-origin extension clock ────────────────────────────────────────
    try:
        from analysis.trade_readiness import (TradeReadinessEngine, TR_EXT_FIRE_FRAC, ARMED)
        check("TR_EXT_FIRE_FRAC == 0.80", abs(TR_EXT_FIRE_FRAC - 0.80) < 1e-9)
        eng = TradeReadinessEngine(emit=lambda ev, **s: None, clock=lambda: eng._t)
        eng._t = 1000.0
        k = "condor_call"; tr = eng.tracks[k]
        eng._t += 15; eng._advance(k, 0.40, {}, eng._t, price=100.0, em=5.0)
        eng._t += 15; eng._advance(k, 0.60, {}, eng._t, price=100.0, em=5.0)
        check("origin stamps at ARM", tr.machine == ARMED and tr.origin_price == 100.0
              and tr.origin_em == 5.0)
        _, _, fires_lo = eng._extension_from_arm(tr, 102.0, "up")   # 40% of EM
        _, _, fires_hi = eng._extension_from_arm(tr, 104.0, "up")   # 80% of EM
        check("below 80% of arm-EM does NOT fire", not fires_lo)
        check("at 80% of arm-EM DOES fire", fires_hi)
        eng._t += 15; eng._advance(k, 0.10, {}, eng._t, price=104.0, em=5.0)
        check("origin clears on disarm", tr.origin_price == 0.0)
    except Exception as e:
        print(f"  [FAIL] extension clock: {e}")
        ok = False

    if not ok:
        print("\nCANARY: PROBLEM — see FAILs above")
        return 1
    if skipped:
        print(f"\nCANARY: OK (PARTIAL) — {len(skipped)} check group(s) skipped "
              f"(no SDK here): {', '.join(skipped)}.\n"
              f"          Everything runnable on this box PASSED. Re-run on a BOT "
              f"box after deploy for full coverage.")
        return 0
    print("\nCANARY: HEALTHY — dual floor holds, no inside fallback, legs "
          "independent, arm-origin extension live")
    return 0


if __name__ == "__main__":
    sys.exit(main())
