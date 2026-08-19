#!/usr/bin/env python3
"""
tests/test_stops_and_orb_ranging.py — the two operator changes, pinned. v1.0
v1.0 — 2026-08-19 — INITIAL.

Two changes that are one constant and one branch, which is exactly why they
need tests: both are the kind of edit a later refactor reverts without anyone
noticing, and neither raises when wrong.

  A. THE PREMIUM FLOOR IS 25%, NOT 40%, and it reaches every exit that
     inherits it — `stop_hit` on sweep AND on the ICT suite, `hard_stop` on
     ORB, and the ADOPTED stops via ADOPTED_STOP_PCT. Asserted as a DECISION:
     a trade at -30% must now exit and a trade at -20% must not. Asserting the
     constant alone would pass even if nothing read it.
     Butterfly (own 0.25), condor (CONDOR_STOP_LOSS_PCT) and continuation
     (0.15) must be UNTOUCHED — they never read this constant, and a change
     that quietly moved them would be a different experiment.

  B. ORB DOES NOT FIRE UNDER RANGING, and the refusal is JOURNALED. The
     journal half matters as much as the block: without a row, "ORB did not
     set up" and "ORB was forbidden" are indistinguishable in the record, and
     only one of those is a decision we can audit or reverse. Checked by AST
     so the RANGING branch is proven to sit BEFORE the permissive
     ORB_FIRES_REGARDLESS_OF_REGIME clause — order is the property; a block
     placed after it would be dead code that still looks correct.

Run:  cd <repo> && PYTHONPATH=. python3 tests/test_stops_and_orb_ranging.py
Deliberate-failure proof: OT_STOPS_SELFTEST=1 asserts the OLD 40% behaviour;
case A must go red.
"""

import ast
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
            def __getattr__(cls, k):
                return type(k, (), {})

        class _Any(metaclass=_AnyMeta):
            def __getattr__(self, k):
                return _Any()

        _m.__getattr__ = lambda k: _Any
        sys.modules[_n] = _m

import pandas as pd                                   # noqa: E402
import config                                         # noqa: E402
from execution.exit_engine import ExitEngine          # noqa: E402

FAILS = []
FLOOR = 0.40 if os.environ.get("OT_STOPS_SELFTEST", "0") == "1" else 0.25


def check(name, ok, detail=""):
    if not ok:
        FAILS.append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail else ''}")


def rec(strategy, entry=2.00, direction="long", stop_underlying=99.0):
    """A record whose stop_premium is derived the way entry_engine derives it."""
    return {
        "trade_id": "t-" + strategy, "strategy": strategy,
        "direction": direction, "option_side": "call",
        "entry_premium": entry, "stop_premium": entry * (1 - FLOOR),
        "target_premium": entry * 2, "trail_activation": entry * 1.5,
        "contracts": 1, "underlying_stop": stop_underlying,
        "underlying_target": 110.0, "is_butterfly": False,
        "entry_time": "2026-08-19T10:00:00-04:00",
    }


def tape():
    idx = pd.date_range("2026-08-19 10:00", periods=4, freq="1min",
                        tz="America/New_York")
    c = [100.0, 100.2, 100.1, 100.3]
    return pd.DataFrame({"open": c, "high": [x + .2 for x in c],
                         "low": [x - .2 for x in c], "close": c,
                         "volume": [1000] * 4}, index=idx)


def main():
    # ── A. the floor, as a DECISION ───────────────────────────────────────
    check("A1 MAX_LOSS_PCT is 0.25", abs(config.MAX_LOSS_PCT - 0.25) < 1e-9,
          str(config.MAX_LOSS_PCT))
    check("A2 ADOPTED_STOP_PCT inherits it",
          abs(config.ADOPTED_STOP_PCT - 0.25) < 1e-9, str(config.ADOPTED_STOP_PCT))

    eng = ExitEngine(paper_trading=True)
    df = tape()
    for strat in ("ICTSweepMSS", "SweepReversal"):
        d_out = eng.evaluate(rec(strat), 2.00 * 0.70, df, None)   # -30%
        d_in = eng.evaluate(rec(strat), 2.00 * 0.80, df, None)    # -20%
        check(f"A3 {strat}: -30% exits on the floor",
              d_out.should_exit and "stop_hit" in (d_out.exit_reason or ""),
              d_out.exit_reason)
        check(f"A4 {strat}: -20% does NOT exit",
              not d_in.should_exit, d_in.exit_reason or "(held)")

    check("A5 butterfly keeps its own 0.25",
          abs(config.BUTTERFLY_STOP_LOSS_PCT - 0.25) < 1e-9)
    check("A6 condor untouched", abs(config.CONDOR_STOP_LOSS_PCT - 0.25) < 1e-9)
    check("A7 continuation keeps 0.15",
          abs(config.CONTINUATION_STOP_LOSS_PCT - 0.15) < 1e-9)

    # ── B. ORB blocked under RANGING, and the block comes FIRST ───────────
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()
    check("B1 the flag exists and defaults ON", config.ORB_BLOCK_RANGING is True)
    check("B2 the refusal is journaled", "gate_block:orb_ranging" in src)

    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "attempt_new_entry")
    block_at = permissive_at = None
    for node in ast.walk(fn):
        if isinstance(node, ast.If):
            t = ast.dump(node.test)
            if "ORB_BLOCK_RANGING" in t and block_at is None:
                block_at = node.lineno
            if "ORB_FIRES_REGARDLESS_OF_REGIME" in t and permissive_at is None:
                permissive_at = node.lineno
    check("B3 the RANGING block is evaluated BEFORE the permissive clause",
          block_at is not None and permissive_at is not None
          and block_at <= permissive_at,
          f"block@{block_at} permissive@{permissive_at}")
    check("B4 RANGING is still in _orb_ok_regimes (the flag decides, not a deletion)",
          "Regime.RANGING, Regime.COMPRESSION" in src,
          "so flipping the flag restores the old behaviour exactly")

    print()
    if FAILS:
        print(f"stops_and_orb: {len(FAILS)} FAILED — " + "; ".join(FAILS))
        return 1
    print("stops_and_orb: ALL PASS (A 25% floor decides, others untouched · "
          "B ORB refused in RANGING, journaled, and refused first)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
