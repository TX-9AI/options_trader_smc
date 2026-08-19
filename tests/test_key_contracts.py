#!/usr/bin/env python3
"""
tests/test_key_contracts.py — every key a consumer reads, a producer emits. v1.0
v1.0 — 2026-08-19 — INITIAL.

THREE INSTANCES IN TWELVE HOURS, all the same shape and all silent:

  1. `sweep_evidence()` read `raid["thesis"]`; `raid_in_progress()` emitted
     `pool`/`kind`/`name`/`depth_pct`. A REQUIRED component scored 0.00 on
     every tick of 27 sessions, so three of the seven setups could never reach
     READY and the only one that ever fired was the lowest-ranked — the one
     needing no sweep at all.
  2. The ICT context adapter read `LiquiditySweep.direction`; the dataclass
     had `kind` and no such attribute, so `getattr(s, "direction", "")`
     returned "" forever and the confirmed-sweep branch was dead too.
  3. The observe harness read `raid["level"]`, reported "raided pool
     identifiable on 0/1065 rows" as if it were a data problem, and silently
     moved the separation study's R denominator off the setup's own
     invalidation.

None raised. None failed a test. Each presented as a MODEL result — "the
setups don't fire", "the pool isn't identifiable", "the score doesn't
separate" — which is the expensive kind of wrong, because you go looking at
the model instead of the plumbing.

So this test asserts the CONTRACT rather than any one bug: for each
producer/consumer pair, every key or attribute the consumer reads must exist
in what the producer actually returns, checked against a REAL produced object,
not a hand-written fixture. A fixture would only encode the same assumption
that was wrong in the first place.

Run:  cd <repo> && PYTHONPATH=. python3 tests/test_key_contracts.py
Deliberate-failure proof: OT_CONTRACT_SELFTEST=1 adds a key no producer emits;
the suite must go red.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILS = []


def check(name, ok, detail=""):
    if not ok:
        FAILS.append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail else ''}")


def _raid():
    """A REAL raid dict from the real primitive, not a fixture."""
    from smc.primitives import raid_in_progress

    class _Pool:
        def __init__(self, price, name):
            self.price = price
            self.name = name
            self.swept = False

    # a bar that wicks below a pool and closes back above it. Signature read
    # from the source, not assumed: (df_1m, pools, price).
    import pandas as pd
    df = pd.DataFrame({"open": [100.5], "high": [101.0], "low": [98.5],
                       "close": [100.6], "volume": [1000]})
    return raid_in_progress(df, [_Pool(100.0, "PDL")], 100.6)


def main():
    # ── 1. raid_in_progress -> sweep_evidence ─────────────────────────────
    raid = _raid()
    check("raid_in_progress returns a dict for a real raid", isinstance(raid, dict),
          str(raid)[:90])
    if isinstance(raid, dict):
        needed = ["pool", "thesis"]
        if os.environ.get("OT_CONTRACT_SELFTEST", "0") == "1":
            needed.append("level")          # deliberate: no producer emits this
        for k in needed:
            check(f"raid dict carries '{k}' (read by sweep_evidence / harness)",
                  k in raid, f"keys={sorted(raid)}")
        check("raid thesis is a real direction, not empty",
              raid.get("thesis") in ("bullish", "bearish"), str(raid.get("thesis")))

    # ── 2. LiquiditySweep -> the ICT context adapter ──────────────────────
    from analysis.liquidity_mapper import LiquiditySweep
    sw = LiquiditySweep(pool_price=100.0, sweep_price=99.0, kind="low_sweep")
    for attr in ("direction", "sweep_price", "kind", "swept_named_level"):
        check(f"LiquiditySweep exposes .{attr} (read by the adapter)",
              hasattr(sw, attr))
    check("a low_sweep reads BULLISH", sw.direction == "bullish", sw.direction)
    check("a high_sweep reads BEARISH",
          LiquiditySweep(pool_price=1, sweep_price=1, kind="high_sweep").direction
          == "bearish")

    # ── 3. the evidence function actually SCORES on a real raid ───────────
    # The contract check above is necessary but not sufficient: the key can
    # exist and still not be consulted. Assert the DECISION.
    from strategy.ict.setup_base import sweep_evidence
    from strategy.ict.context import ICTContext
    ctx = ICTContext(price=100.6)
    ctx.raid = raid
    val, note = sweep_evidence(ctx, "bullish")
    check("sweep_evidence scores a live raid 1.0 for the agreeing thesis",
          val == 1.0, f"{val} ({note})")
    val_opp, _ = sweep_evidence(ctx, "bearish")
    check("and 0.0 for the opposing thesis", val_opp == 0.0, str(val_opp))

    ctx2 = ICTContext(price=100.0)
    ctx2.recent_sweep = {"sweep_price": 99.0, "direction": sw.direction,
                         "level_name": "PDL", "invalidated": False}
    val2, note2 = sweep_evidence(ctx2, "bullish")
    check("a CONFIRMED sweep scores 0.7 for the agreeing thesis",
          val2 == 0.7, f"{val2} ({note2})")

    print()
    if FAILS:
        print(f"key_contracts: {len(FAILS)} FAILED — " + "; ".join(FAILS))
        return 1
    print("key_contracts: ALL PASS (raid dict · LiquiditySweep · "
          "sweep_evidence decides on both branches)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
