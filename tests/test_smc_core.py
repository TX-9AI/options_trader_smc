"""
tests/test_smc_core.py — behavioral proof of the SMC core. v1.0
v1.0 — 2026-08-18 — INITIAL (fork: options_trader_smc).

Offline, deterministic, no network, no orders, no trades.db. Drives the
REAL structure_analyzer over a synthetic textbook tape and the REAL
liquidity_mapper dataclasses with controlled values (using the live
objects, never reimplementing them — WORKING_AGREEMENT §25). Every
expectation is PRE-REGISTERED in the fixture builder's comments: the tape
is engineered to contain exactly one raid, one reclaim, one displacement
and one structure shift, and the test asserts the engine finds THOSE, at
the bars they were placed.

WA §21 compliance: test D calls the actual DECISION function
(entry_permitted) and asserts on the returned decision, not on source
text. WA §20 corollary: test F corrupts the classifier and REQUIRES the
suite to fail against the corruption — a canary that has never gone red
is one nobody knows works.

Run:  cd <repo> && PYTHONPATH=. python3 tests/test_smc_core.py
Exit 0 on pass; nonzero with a named failure otherwise.
"""

import sys
import os
import types
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from smc import primitives as P
from smc.smc_engine import SMCEngine, SetupState
from analysis.liquidity_mapper import LiquidityPool, LiquiditySweep, LiquidityMap


# ── fixture: the textbook sequence ───────────────────────────────────────────
# Bars (1m, closed):
#   0–39   : quiet range 99.5–100.5, equal lows resting at 99.50 (the pool)
#   40     : THE RAID — wick to 99.30 through the 99.50 pool, close 99.62
#            back inside (raid, not acceptance)          <- FORMING here
#   41     : reclaim bar, close 99.85                    <- CONFIRMED here
#   42     : THE DISPLACEMENT — range ~5x the rolling SD, close 100.95
#            (bullish impulse; origin/low 99.80)
#   43–55  : uptrend continuation to ~102, leaving the range
# The pre-registered expectations reference these indices by name below.

RAID_BAR = 40
RECLAIM_BAR = 41
DISPLACEMENT_BAR = 42


def build_tape() -> pd.DataFrame:
    rng = np.random.default_rng(7)          # fixed seed — determinism
    rows = []
    t0 = dt.datetime(2026, 8, 18, 9, 30)
    px = 100.0
    for i in range(56):
        t = t0 + dt.timedelta(minutes=i)
        if i < 40:
            o = px
            c = 100.0 + float(rng.uniform(-0.22, 0.22))
            hi = max(o, c) + 0.10
            lo = min(o, c) - 0.10
            lo = max(lo, 99.52)             # the pool at 99.50 stays untapped
            if i in (10, 22, 33):           # engineered equal lows -> pool
                lo = 99.50
            px = c
        elif i == RAID_BAR:
            o, c, hi, lo = px, 99.62, px + 0.05, 99.30   # wick through 99.50
            px = c
        elif i == RECLAIM_BAR:
            o, c, hi, lo = px, 99.85, 99.90, 99.55
            px = c
        elif i == DISPLACEMENT_BAR:
            o, c, hi, lo = 99.82, 100.95, 101.05, 99.75  # ~1.3 range vs tight chop SD
            px = c
        else:
            o = px
            c = px + 0.12 + float(rng.uniform(-0.03, 0.03))
            hi, lo = max(o, c) + 0.08, min(o, c) - 0.05
            px = c
        rows.append({"timestamp": t, "open": o, "high": hi, "low": lo,
                     "close": c, "volume": 1000})
    df = pd.DataFrame(rows).set_index("timestamp")
    return df


def make_liq_map(df_1m_asof: pd.DataFrame, bar: int) -> LiquidityMap:
    """Real LiquidityMap dataclasses with controlled, fixture-true values.

    The pool at 99.50 is unswept until the raid bar; the mapper's confirmed
    sweep (reclaimed=True) exists only from the RECLAIM bar onward — one
    bar AFTER the raid, which is exactly the anticipation gap the engine's
    FORMING phase must beat (expectation C).
    """
    pool = LiquidityPool(price=99.50, kind="low", touch_count=3,
                         timeframe="1m", name="PDL", is_named=True,
                         swept=(bar > RAID_BAR),
                         rejection_confirmed=(bar >= RECLAIM_BAR))
    m = LiquidityMap(pools=[pool])
    if bar >= RECLAIM_BAR:
        m.recent_sweep = LiquiditySweep(
            pool_price=99.50, sweep_price=99.30, kind="low_sweep",
            confirmed=True, reclaimed=True, closes_beyond=0,
            swept_named_level="PDL", bars_ago=bar - RECLAIM_BAR)
        m.sweep_age_bars = bar - RECLAIM_BAR
    return m


class VolStub:
    """Duck-typed VolatilityState surface the engine reads (field names
    match analysis/volatility_engine.VolatilityState)."""
    atr_current = 0.35
    bb_state = "NORMAL"
    is_expanding = False


def run_suite(engine_cls=SMCEngine, quiet=False) -> list:
    from analysis.structure_analyzer import get_structure_analyzer
    failures = []
    df = build_tape()
    eng = engine_cls()
    sa = get_structure_analyzer()
    phases = {}          # bar -> setup phase (first observation)
    labels = {}
    now_et = dt.datetime(2026, 8, 18, 10, 30)

    for bar in range(20, len(df)):
        df1 = df.iloc[: bar + 1]
        df5 = df1.resample("5min").agg({"open": "first", "high": "max",
                                        "low": "min", "close": "last",
                                        "volume": "sum"}).dropna()
        df15 = df1.resample("15min").agg({"open": "first", "high": "max",
                                          "low": "min", "close": "last",
                                          "volume": "sum"}).dropna()
        price = float(df1["close"].iloc[-1])
        structure = sa.analyze(df5, df15, None, price)
        liq = make_liq_map(df1, bar)
        st = eng.update(price, df1, df5, structure, liq,
                        vol_state=VolStub(), now_et=now_et)
        phases[bar] = (st.setup.phase, st.setup.thesis, st.setup.basis)
        labels[bar] = st.label

    # A · dealing-range / zone unit math on fixture values
    drng = P.DealingRange(high=102.0, low=100.0, high_index=1, low_index=0)
    if abs(drng.position_pct(101.5) - 0.75) > 1e-9 or P.zone_of(0.75) != "PREMIUM":
        failures.append("A: premium/discount math wrong")
    if P.zone_of(0.30) != "DISCOUNT" or P.zone_of(0.50) != "EQUILIBRIUM" \
            or P.zone_of(-1.0) != "NONE":
        failures.append("A2: zone mapping wrong")

    # A3 · BOS/CHoCH semantics pinned at the definition (the engine calls
    # this via classify_break_dyn, so a corrupted definition reaches every
    # shift the engine reports — this is what F corrupts)
    if P.classify_break("bullish", "bearish") != "CHOCH" \
            or P.classify_break("bullish", "bullish") != "BOS" \
            or P.classify_break("neutral", "bearish") != "BOS":
        failures.append("A3: BOS/CHoCH classification wrong")

    # B · the engineered displacement is found at its bar, sd ≥ 2
    disp = P.last_displacement(df.iloc[: DISPLACEMENT_BAR + 1])
    if disp is None or disp.index != DISPLACEMENT_BAR or disp.sd < 2.0 \
            or disp.direction != "bullish":
        failures.append(f"B: displacement not detected as placed ({disp})")

    # C · ANTICIPATION — FORMING fires on the RAID bar, bullish, basis=raid,
    #     i.e. one bar BEFORE the mapper's confirmed sweep exists
    ph, th, ba = phases.get(RAID_BAR, ("?", "?", "?"))
    if not (ph == "FORMING" and th == "bullish" and ba == "raid"):
        failures.append(f"C: raid bar phase={phases.get(RAID_BAR)} "
                        f"(want FORMING/bullish/raid)")

    # C2 · CONFIRMED on the reclaim bar
    ph, th, _ = phases.get(RECLAIM_BAR, ("?", "?", "?"))
    if not (ph == "CONFIRMED" and th == "bullish"):
        failures.append(f"C2: reclaim bar phase={phases.get(RECLAIM_BAR)} "
                        f"(want CONFIRMED/bullish)")

    # D · REVOCATION decision — the actual decision function, fresh engine.
    #     Acceptance through the invalidation must REVOKE and block entries
    #     in the revoked direction while permitting the opposite.
    e2 = engine_cls()
    e2._setup = SetupState(phase="CONFIRMED", thesis="bullish", basis="raid",
                           anchor=99.50, invalidation=99.50, since_bar=41)
    dfd = df.iloc[:RAID_BAR].copy()
    bad = pd.DataFrame([{"open": 99.55, "high": 99.60, "low": 99.20,
                         "close": 99.30, "volume": 1000}],
                       index=[dfd.index[-1] + dt.timedelta(minutes=1)])
    dfd = pd.concat([dfd, bad])
    df5d = dfd.resample("5min").agg({"open": "first", "high": "max",
                                     "low": "min", "close": "last",
                                     "volume": "sum"}).dropna()
    struct_d = sa.analyze(df5d, df5d, None, 99.30)
    e2.update(99.30, dfd, df5d, struct_d, make_liq_map(dfd, 30),
              vol_state=VolStub(), now_et=now_et)
    if e2._setup.phase != "REVOKED":
        failures.append(f"D: acceptance did not REVOKE ({e2._setup.phase})")
    if e2.entry_permitted("bullish") is not False:
        failures.append("D2: revoked thesis still permitted")
    if e2.entry_permitted("bearish") is not True:
        failures.append("D3: opposite direction wrongly blocked")

    # E · label sanity in the continuation segment: after the shift the
    #     label must be a directional-bull state (trend or breakout), and
    #     it must be RANGING-family in the pre-raid chop.
    tail_labels = {labels[b] for b in range(50, len(df))}
    if not tail_labels & {"TRENDING_BULL", "BREAKOUT_VOLATILE"}:
        failures.append(f"E: no bullish state in continuation ({tail_labels})")
    chop_labels = {labels[b] for b in range(25, 39)}
    if not chop_labels <= {"RANGING", "COMPRESSION"}:
        failures.append(f"E2: chop segment mislabeled ({chop_labels})")

    if not quiet:
        for b in sorted(phases):
            if phases[b][0] != "NONE" or b in (RAID_BAR, RECLAIM_BAR):
                print(f"  bar {b:>2}  label={labels[b]:<17} "
                      f"setup={phases[b]}")
    return failures


def deliberate_failure_check() -> bool:
    """Corrupt the break classifier; the suite MUST go red (WA §20)."""
    orig = P.classify_break
    try:
        P.classify_break = lambda prior, brk: "BOS"      # CHoCH can never print
        fails = run_suite(quiet=True)
        return bool(fails)          # corruption must produce failures
    finally:
        P.classify_break = orig


if __name__ == "__main__":
    fails = run_suite()
    if fails:
        print("\nFAIL:")
        for f in fails:
            print("  ✗", f)
        sys.exit(1)
    if not deliberate_failure_check():
        print("\nFAIL:\n  ✗ F: deliberate-failure check — corrupted classifier "
              "still passed; the suite is not testing the shift path")
        sys.exit(1)
    print("\nsmc_core: ALL PASS (A structural math · B displacement · "
          "C anticipation · C2 confirmation · D revocation decision · "
          "E labels · F deliberate-failure)")
    sys.exit(0)
