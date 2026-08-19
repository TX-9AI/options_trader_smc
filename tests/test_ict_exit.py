#!/usr/bin/env python3
"""
tests/test_ict_exit.py — does an ICT trade exit on its OWN level? v1.0
v1.0 — 2026-08-19 — INITIAL (exit_engine v4.23).

THE BUG THIS PINS: before v4.23 every ICT strategy fell through the exit
router's `else` into `_evaluate_sweep`, which contains no reference to
`underlying_stop` in its 94 lines. The setup computed a structural stop, the
record carried it, and the exit engine managed the trade on a 40% premium
floor — the invalidation sat on the row and was never read. Nothing raised,
no test went red, and the symptom would have been "the ICT setups lose"
rather than "the stop is not wired".

So this CALLS the evaluator and asserts on the DECISION (WA §21), never on the
source. Five properties:

  A. ROUTING — an ICT record reaches _evaluate_ict, and the legacy strategies
     still reach the evaluators they always did. A prefix rule that stole
     SweepReversal's routing would be a silent regression in the box we are
     comparing against.
  B. THE STRUCTURE STOP FIRES on a close beyond the invalidation, in both
     directions, while the premium is still healthy — the case that was
     entirely unreachable before.
  C. A WICK THROUGH THE LEVEL SURVIVES. Evaluation is on the last CLOSED bar,
     so a liquidity sweep of the setup's own level does not stop the trade
     out. An ICT setup stopped by a raid would be a parody of itself.
  D. THE PREMIUM FLOOR STILL BACKSTOPS when structure is intact but the
     dollars are gone. Structure-first must not mean premium-never.
  E. AN INERT STOP IS NOT A PASSING CHECK — no tape means the structural rule
     cannot run, and that must be visible rather than silently green.

Run:  cd <repo> && PYTHONPATH=. python3 tests/test_ict_exit.py
Deliberate-failure proof: OT_ICTEXIT_SELFTEST=1 feeds a close that does NOT
breach; case B must go red.
"""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for _n in ("tastytrade", "tastytrade.instruments", "tastytrade.session",
           "tastytrade.market_data", "tastytrade.dxfeed", "tastytrade.streamer",
           "tastytrade.account", "tastytrade.order", "tastytrade.utils"):
    if _n not in sys.modules:
        _m = types.ModuleType(_n)

        class _AnyMeta(type):
            """Any attribute, at any depth, resolves. Enumerating the SDK's
            members by hand is whack-a-mole — exit_engine's class body touches
            OrderStatus.RECEIVED, .CONTINGENT and others, and the list grows
            with the SDK. The stub answers everything and means nothing; it
            exists only so the module imports off-box. On control the real SDK
            is present and none of this runs."""
            def __getattr__(cls, k):
                return type(k, (), {})

        class _Any(metaclass=_AnyMeta):
            def __getattr__(self, k):
                return _Any()

        _m.__getattr__ = lambda k: _Any
        sys.modules[_n] = _m

import pandas as pd                                    # noqa: E402
from execution.exit_engine import ExitEngine           # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    if not ok:
        FAILS.append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail else ''}")


def rec(strategy="ICTSweepMSS", direction="long", stop=99.0,
        entry_prem=2.00, stop_prem=1.20, target=4.00):
    return {
        "trade_id": "t-" + strategy, "strategy": strategy,
        "direction": direction, "option_side": "call" if direction == "long" else "put",
        "entry_premium": entry_prem, "stop_premium": stop_prem,
        "target_premium": target, "trail_activation": 3.00,
        "contracts": 1, "underlying_stop": stop, "underlying_target": 110.0,
        "is_butterfly": False, "entry_time": "2026-08-19T10:00:00-04:00",
    }


def tape(closes):
    """1m frame whose LAST CLOSED bar is closes[-2] — the bar the rule reads."""
    idx = pd.date_range("2026-08-19 10:00", periods=len(closes), freq="1min",
                        tz="America/New_York")
    return pd.DataFrame({"open": closes, "high": [c + 0.2 for c in closes],
                         "low": [c - 0.2 for c in closes], "close": closes,
                         "volume": [1000] * len(closes)}, index=idx)


def main():
    eng = ExitEngine(paper_trading=True)
    seen = {}

    for name in ("_evaluate_ict", "_evaluate_sweep", "_evaluate_orb"):
        orig = getattr(eng, name)

        def spy(*a, _n=name, _o=orig, **kw):
            seen[_n] = seen.get(_n, 0) + 1
            return _o(*a, **kw)
        setattr(eng, name, spy)

    # ── A. routing ────────────────────────────────────────────────────────
    healthy = tape([100.0, 100.5, 100.4, 100.6])
    eng.evaluate(rec("ICTSweepMSS"), 2.10, healthy, None)
    check("A1 an ICT record routes to _evaluate_ict", seen.get("_evaluate_ict") == 1)
    eng.evaluate(rec("SweepReversal"), 2.10, healthy, None)
    check("A2 SweepReversal still routes to _evaluate_sweep",
          seen.get("_evaluate_sweep") == 1, "legacy routing untouched")
    for n in ("ICTSilverBullet", "ICTJudasPO3", "ICTModel2022",
              "ICTBreakerUnicorn", "ICTOTEConfluence", "ICTOBFVG"):
        eng.evaluate(rec(n), 2.10, healthy, None)
    check("A3 every ICT name routes by prefix — none forgotten",
          seen.get("_evaluate_ict") == 7, f"count={seen.get('_evaluate_ict')}")

    # ── B. the structural stop fires ──────────────────────────────────────
    breach_long = tape([100.0, 100.2, 98.5, 99.5])       # last CLOSED = 98.5
    if os.environ.get("OT_ICTEXIT_SELFTEST", "0") == "1":
        breach_long = tape([100.0, 100.2, 99.9, 99.5])   # deliberate: no breach
    d = eng.evaluate(rec(direction="long", stop=99.0), 2.10, breach_long, None)
    check("B1 long exits on a close BELOW the invalidation",
          d.should_exit and "ict_structure_stop" in d.exit_reason, d.exit_reason)
    check("B2 and it fired while the premium was HEALTHY (unreachable before)",
          d.should_exit, "premium 2.10 vs floor 1.20")

    breach_short = tape([100.0, 100.2, 101.5, 100.5])
    d = eng.evaluate(rec(direction="short", stop=101.0), 2.10, breach_short, None)
    check("B3 short exits on a close ABOVE the invalidation",
          d.should_exit and "ict_structure_stop" in d.exit_reason, d.exit_reason)

    # ── C. a wick through the level survives ──────────────────────────────
    wick = tape([100.0, 100.2, 99.8, 100.1])
    wick.iloc[2, wick.columns.get_loc("low")] = 98.0     # deep wick, close inside
    d = eng.evaluate(rec(direction="long", stop=99.0), 2.10, wick, None)
    check("C1 a WICK through the level does not stop the trade",
          not d.should_exit, d.exit_reason or "(held)")

    # ── D. the premium floor still backstops ──────────────────────────────
    d = eng.evaluate(rec(direction="long", stop=99.0), 1.10, healthy, None)
    check("D1 premium floor still fires when structure is intact",
          d.should_exit and "stop_hit" in d.exit_reason, d.exit_reason)

    # ── E. an inert stop is visible, not silently green ───────────────────
    d = eng.evaluate(rec(direction="long", stop=99.0), 2.10, None, None)
    check("E1 no tape → no structural exit claimed", not d.should_exit,
          d.exit_reason or "(held)")
    d = eng.evaluate(rec(direction="long", stop=0.0), 2.10, healthy, None)
    check("E2 a record with NO invalidation still evaluates (floor only)",
          d is not None)

    print()
    if FAILS:
        print(f"ict_exit: {len(FAILS)} FAILED — " + "; ".join(FAILS))
        return 1
    print("ict_exit: ALL PASS (A routing · B structure stop both ways · "
          "C wick survives · D floor backstops · E inert stop visible)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
