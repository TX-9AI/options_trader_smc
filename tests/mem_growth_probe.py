#!/usr/bin/env python3
"""
tests/mem_growth_probe.py — v1.0 — 2026-08-06

WHERE IS THE MEMORY GOING? Drives the per-tick paths in a loop under
`tracemalloc` and reports which source lines are still holding memory after the
loop ends. Offline, on control, no fleet impact — the running boxes are not
touched or imported from.

WHY A HARNESS AND NOT CODE READING. I read the three suspect paths (N.5 exit
latency, N.7 entry snapshot, N.9 contract capture) and found no unbounded list,
no retained collection, nothing obviously wrong. That is exactly when a harness
is worth more than another pass of reading: a leak that is visible in the source
would already have been found.

WHAT THE FLEET DATA SAYS, so the harness targets the right thing (2026-08-06,
10:14 -> 11:42, same code everywhere):
    SPX   285 -> 428 MB   +143   holding an open position since ~09:50
    CRM   175 -> 255      +79    traded
    ORCL  180 -> 250      +70    traded
    QQQ   273 -> 270       -3    LARGE CHAIN, no position
    GLD   225 -> 221       -5    quiet
QQQ has a chain the same order of magnitude as SPX and did not move. That kills
"large chains need more memory" as the explanation. What separates the climbers
is ACTIVITY — trades, and above all an OPEN POSITION being managed every 15s.
So the loop below models a tick with a position open, which is the population
that grows.

READING THE OUTPUT. `tracemalloc` reports memory still allocated at the end of
the loop, grouped by the line that allocated it. A line that grows roughly
linearly with --ticks is a leak. A line that is large but FLAT between two tick
counts is a cache doing its job. That is why this runs the loop twice at
different sizes and prints the delta per line rather than a single total —
a single snapshot cannot tell a leak from a working set, and reporting one
would be the same mistake as reading a median and calling it a distribution.

USAGE
    python3 tests/mem_growth_probe.py                    # 200 vs 800 ticks
    python3 tests/mem_growth_probe.py --ticks 400 --ticks2 1600 --top 25
"""

import argparse
import gc
import sys
import tracemalloc
from collections import Counter


def _fake_ctx(i: int):
    """One tick's worth of the objects the per-tick paths consume.

    Deliberately rebuilt EVERY iteration, because that is what the live loop
    does: the chain is re-fetched and re-built every 15 seconds. If something
    retains a reference to a chain, the old ones cannot be freed and the growth
    is proportional to chain size x ticks — which is the shape SPX shows and
    QQQ does not.
    """
    class _Vol:
        vwap = 100.0 + (i % 7) * 0.1
        price_vs_vwap = "ABOVE"
        bb_middle = 100.0
        bb_upper = 101.0
        bb_lower = 99.0
        bb_width_pct = 0.02
        bb_state = "NORMAL"
        atr_current = 0.5

    class _Contract:
        __slots__ = ("symbol", "strike", "bid", "ask", "mark", "delta",
                     "gamma", "theta", "vega", "iv", "open_interest", "volume")

        def __init__(self, k):
            self.symbol = f"SPXW  260806C{k:08d}"
            self.strike = float(k)
            self.bid, self.ask, self.mark = 1.0, 1.1, 1.05
            self.delta, self.gamma, self.theta = 0.3, 0.01, -0.08
            self.vega, self.iv = 0.1, 0.44
            self.open_interest, self.volume = 100, 10

    class _Chain:
        # 574 contracts is SPX's real size, from the 2026-08-06 logs.
        def __init__(self):
            self.calls = [_Contract(7000 + n) for n in range(287)]
            self.puts = [_Contract(7000 + n) for n in range(287)]
            self.spot_price = 7735.0
            self.iv_rank = 0.5

    return {"vol": _Vol(), "price": 7735.0 + (i % 11), "chain": _Chain(),
            "trend": None}


def _drive(ticks: int, engine, regime):
    """One pass. Whatever the loop retains is what we are hunting."""
    for i in range(ticks):
        ctx = _fake_ctx(i)
        try:
            engine.assess_all(ctx, regime)
        except Exception:                                        # noqa: BLE001
            pass
        del ctx
    gc.collect()


def _df(n=240, base=7700.0):
    """A 1-minute frame the size the live loop carries. Rebuilt every tick,
    exactly as the real loop does — if anything retains one, the growth is
    frames x ticks and that is large."""
    import pandas as pd
    return pd.DataFrame({
        "open":  [base + (i % 5) for i in range(n)],
        "high":  [base + (i % 5) + 1 for i in range(n)],
        "low":   [base + (i % 5) - 1 for i in range(n)],
        "close": [base + (i % 5) + 0.5 for i in range(n)],
        "volume": [1000 + i for i in range(n)],
    })


def _drive_position(ticks: int):
    """The path the fleet data actually implicates: an OPEN POSITION managed
    every tick. SPX grew +143 MB holding one position for two hours while QQQ,
    with a comparable chain and no position, did not move at all."""
    sys.path.insert(0, ".")
    from execution.exit_engine import get_exit_engine
    eng = get_exit_engine(True)
    rec = {"trade_id": "probe-0001", "direction": "long", "strategy": "ORBStrategy",
           "entry_premium": 8.70, "contracts": 1, "symbol": "SPX",
           "option_side": "C", "strike": 7750.0, "setup_type": "ORB Long",
           "entry_time": "2026-08-06T13:50:00", "status": "open",
           "max_premium_seen": 8.70, "min_premium_seen": 8.70}
    for i in range(ticks):
        df1, df5 = _df(240), _df(150)
        try:
            t = eng._get_bos_tracker(rec["trade_id"], "long", 7750.0) \
                if hasattr(eng, "_get_bos_tracker") else None
            if t is not None:
                t.update(df1)
        except Exception:                                        # noqa: BLE001
            pass
        try:
            eng.evaluate_exit(rec, 8.70 + (i % 7) * 0.1, df_1m=df1, df_5m=df5)
        except Exception:                                        # noqa: BLE001
            pass
        del df1, df5
    gc.collect()


def _measure(ticks: int, path: str = "readiness"):
    if path == "position":
        gc.collect()
        tracemalloc.start(15)
        before = tracemalloc.take_snapshot()
        _drive_position(ticks)
        after = tracemalloc.take_snapshot()
        stats = after.compare_to(before, "lineno")
        tracemalloc.stop()
        return {f"{s.traceback[0].filename.split('/')[-1]}:{s.traceback[0].lineno}":
                s.size_diff for s in stats if s.size_diff > 0}

    sys.path.insert(0, ".")
    from analysis.trade_readiness import TradeReadinessEngine

    class _Regime:
        primary_regime = "TRENDING_BULL"
        conviction = 0.8

    # emit=None keeps the journal out of it for the first pass: if growth
    # disappears without the journal, the journal is the suspect and that is a
    # one-line answer.
    engine = TradeReadinessEngine(emit=None)
    gc.collect()
    tracemalloc.start(15)
    before = tracemalloc.take_snapshot()
    _drive(ticks, engine, _Regime())
    after = tracemalloc.take_snapshot()
    stats = after.compare_to(before, "lineno")
    tracemalloc.stop()
    return {f"{s.traceback[0].filename.split('/')[-1]}:{s.traceback[0].lineno}":
            s.size_diff for s in stats if s.size_diff > 0}


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=200)
    ap.add_argument("--ticks2", type=int, default=800)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--path", default="readiness",
                    choices=("readiness", "position"),
                    help="which per-tick path to drive. `position` models an "
                         "OPEN POSITION managed every tick, which is what the "
                         "2026-08-06 fleet data implicates: SPX +143MB holding "
                         "one position, QQQ -3MB with a comparable chain and "
                         "none.")
    a = ap.parse_args(argv[1:])

    print(f"path: {a.path}")
    print(f"pass 1: {a.ticks} ticks")
    small = _measure(a.ticks, a.path)
    print(f"pass 2: {a.ticks2} ticks")
    big = _measure(a.ticks2, a.path)

    ratio = a.ticks2 / a.ticks
    rows = []
    for k, v2 in big.items():
        v1 = small.get(k, 0)
        # A LEAK scales with the tick count; a working set does not.
        scale = (v2 / v1) if v1 > 0 else float("inf")
        rows.append((v2, v1, scale, k))
    rows.sort(reverse=True)

    print(f"\n{'retained@' + str(a.ticks2):>14}{'@' + str(a.ticks):>12}"
          f"{'scale':>8}   line")
    print(f"  (a LEAK scales ~{ratio:.0f}x with the tick count; a CACHE stays "
          f"flat)")
    for v2, v1, scale, k in rows[:a.top]:
        sc = "inf" if scale == float("inf") else f"{scale:.1f}x"
        mark = "  <- SCALES" if scale >= ratio * 0.7 else ""
        print(f"{v2/1024:>13.0f}K{v1/1024:>11.0f}K{sc:>8}   {k}{mark}")

    tot2 = sum(big.values()) / 1024 / 1024
    tot1 = sum(small.values()) / 1024 / 1024
    print(f"\n  TOTAL retained: {tot1:.1f} MB @{a.ticks} -> {tot2:.1f} MB "
          f"@{a.ticks2}  ({(tot2/tot1 if tot1 else 0):.1f}x for {ratio:.0f}x "
          f"the ticks)")
    print("\n  A total that scales with ticks reproduces the fleet's behaviour")
    print("  and the SCALES lines are the cause. A total that stays flat means")
    print("  the growth is NOT in this path — and that is a real result too:")
    print("  it exonerates the readiness/journal changes and points elsewhere")
    print("  (position management, the chain cache, or the L2 book).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
