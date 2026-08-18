#!/usr/bin/env python3
"""
tests/rgm5_fallthrough.py — v1.0 — 2026-08-11

RGM.5 — WHAT DO THE v13 CLASSIFIER'S SWEEP_REVERSAL TICKS BECOME IF THAT BRANCH
IS REMOVED? The measurement the BACKLOG requires BEFORE the cut.

THE SITUATION. RGM.3 took SWEEP_REVERSAL out of the L2 integrator's argmax, and
stopped there. `regime_classifier.py` still assigns it at PRIORITY 1 of five, and
`main` falls back to the v13 classifier on every tick where L2 is not committing
— so the label reappears on the fallback path. That is the same category error
RGM.3 was meant to end, surviving in a second place.

⚠️ WHY THE MEASUREMENT COMES FIRST, and it is the whole reason this file exists.
`_is_sweep_reversal` is evaluated BEFORE the four rungs below it (BREAKOUT →
COMPRESSION → TRENDING → RANGING-default), so the ticks it absorbs have NEVER
been scored by any of them. Nobody knows what they would become. The likely
answer is BREAKOUT_VOLATILE — the one label whose only dispatch effect is
SUBTRACTIVE (it removes standalone continuation and enables nothing) — which
would MOVE the dead zone rather than remove it. Cutting blind risks trading one
silent gap for another.

⚠️ AND WHY THIS USES THE REAL ENGINES. The four lower rungs read vol_state,
trend_state and structure. Stubbing those would decide the answer by
construction — stub a BEARISH trend and everything falls to TRENDING_BEAR. So
this builds all four inputs from tape with the SHIPPING engines
(volatility_engine, trend_engine, structure_analyzer, liquidity_mapper) and asks
the SHIPPING classifier twice: once as-is, once with the sweep branch disabled.

WHAT IT CANNOT SEE, stated so the output is not over-read:
  - `macro` is None, so vix_regime/macro_context are UNKNOWN/NEUTRAL. The four
    lower rungs do not read macro, so the fall-through is unaffected — but the
    conviction values are not comparable to live.
  - Tape is whatever is passed in; the fleet's live mapper is built from 15s
    feed-store frames that 1m RTH tape cannot reproduce exactly.
  - This measures the CLASSIFIER in isolation. What reaches dispatch also
    depends on whether L2 was committing on that tick, which this does not model.

READ-ONLY. Touches no fleet, no live path, writes nothing.

USAGE
    python3 tests/rgm5_fallthrough.py <tape.csv> [<tape.csv> ...]
"""

import collections
import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd                                              # noqa: E402

from analysis.liquidity_mapper import LiquidityMapper            # noqa: E402
from analysis.regime_classifier import RegimeClassifier, Regime  # noqa: E402
from analysis.volatility_engine import get_volatility_engine     # noqa: E402
from analysis.trend_engine import get_trend_engine               # noqa: E402
from analysis.structure_analyzer import get_structure_analyzer   # noqa: E402


def load(path):
    r = pd.read_csv(path)
    r.columns = [c.strip().lower() for c in r.columns]
    t = next(c for c in ("timestamp", "time", "date", "datetime") if c in r.columns)
    idx = pd.to_datetime(r[t], errors="coerce")
    r = r[idx.notna()].copy()
    r.index = pd.DatetimeIndex(idx[idx.notna()])
    if getattr(r.index, "tz", None) is not None:
        r.index = r.index.tz_localize(None)
    for c in ("open", "high", "low", "close"):
        r[c] = pd.to_numeric(r[c], errors="coerce")
    if "volume" not in r.columns:
        r["volume"] = 1000.0
    return r[["open", "high", "low", "close", "volume"]].dropna().sort_index()


def rs(df, rule):
    return df.resample(rule).agg({"open": "first", "high": "max", "low": "min",
                                  "close": "last", "volume": "sum"}).dropna()


def main(argv):
    tapes = argv[1:]
    if not tapes:
        print("usage: rgm5_fallthrough.py <tape.csv> [...]")
        return 1

    clf = RegimeClassifier()
    mapper = LiquidityMapper()
    vol_eng = get_volatility_engine()
    trend_eng = get_trend_engine()
    struct_eng = get_structure_analyzer()

    # the branch under test, and its disabled twin
    _orig = RegimeClassifier._is_sweep_reversal

    sweep_ticks = 0
    total = 0
    becomes = collections.Counter()
    all_labels = collections.Counter()
    errors = collections.Counter()

    for path in tapes:
        sym = os.path.basename(path).split("_")[0].upper().lstrip("_") or "?"
        df = load(path)
        D5, D15, D1H = rs(df, "5min"), rs(df, "15min"), rs(df, "1h")
        days = sorted({d.date() for d in df.index})
        for di, day in enumerate(days):
            if di == 0:
                continue                       # need a prior day for PDH/PDL
            today5 = D5[[d.date() == day for d in D5.index]]
            if len(today5) < 14:
                continue
            for k in range(14, len(today5)):
                asof = today5.index[k]
                w5 = D5[D5.index <= asof].tail(100)
                w15 = D15[D15.index <= asof].tail(50)
                w1h = D1H[D1H.index <= asof].tail(50)
                w1m = df[df.index <= asof].tail(400)
                px = float(w5.iloc[-1]["close"])
                try:
                    vol = vol_eng.analyze(w5, w1h, px)
                    trend = trend_eng.analyze({"1m": w1m, "5m": w5,
                                               "15m": w15, "1h": w1h})
                    struct = struct_eng.analyze(w5, w15, w1h, px)
                    liq = mapper.analyze(w5, w15, px)
                except Exception as exc:                      # noqa: BLE001
                    errors[f"engine: {type(exc).__name__}"] += 1
                    continue
                total += 1
                try:
                    st = clf.classify(vol, trend, struct, liq)
                    lab = str(getattr(st.primary_regime, "value",
                                      st.primary_regime))
                    all_labels[lab] += 1
                    if lab != "SWEEP_REVERSAL":
                        continue
                    sweep_ticks += 1
                    # ask again with the branch disabled
                    RegimeClassifier._is_sweep_reversal = lambda *a, **k: False
                    try:
                        st2 = clf.classify(vol, trend, struct, liq)
                        lab2 = str(getattr(st2.primary_regime, "value",
                                           st2.primary_regime))
                        becomes[lab2] += 1
                    finally:
                        RegimeClassifier._is_sweep_reversal = _orig
                except Exception as exc:                      # noqa: BLE001
                    errors[f"classify: {type(exc).__name__}"] += 1

    print("=" * 68)
    print(f"  RGM.5 FALL-THROUGH — {len(tapes)} tape(s), {total:,} ticks")
    print("=" * 68)
    if errors:
        for k, n in errors.most_common(4):
            print(f"    skipped {n}: {k}")

    print(f"\n  v13 CLASSIFIER LABEL DISTRIBUTION (as shipped)")
    for k, n in all_labels.most_common():
        mark = "   <- the branch under test" if k == "SWEEP_REVERSAL" else ""
        print(f"    {k:22}{n:>8}  {100.0 * n / max(total, 1):5.1f}%{mark}")

    print(f"\n  WHAT THE {sweep_ticks} SWEEP_REVERSAL TICKS BECOME WITHOUT IT")
    if not sweep_ticks:
        print("    NONE — the v13 classifier never emitted SWEEP_REVERSAL on this")
        print("    tape. The branch is already dead here; removing it is a no-op")
        print("    and the fallback path is NOT where the label comes from.")
        return 0
    for k, n in becomes.most_common():
        print(f"    {k:22}{n:>8}  {100.0 * n / sweep_ticks:5.1f}%")

    # ⚠️ A LABEL IS "DEAD" IF NOTHING BUT ORB CAN FIRE ON IT.
    # UNKNOWN trips the hard gate at the top of dispatch (only ORB has a
    # bypass), and BREAKOUT_VOLATILE's only dispatch effect is SUBTRACTIVE — it
    # removes standalone continuation and enables nothing. My first version of
    # this verdict counted only BREAKOUT and therefore called a 63.6% UNKNOWN
    # fall-through "genuinely shrinks the dead zone". It does not: UNKNOWN is
    # the same dead zone wearing a different name.
    dead = becomes.get("BREAKOUT_VOLATILE", 0) + becomes.get("UNKNOWN", 0)
    live = sweep_ticks - dead
    print(f"\n  ⇒ VERDICT   still-dead {dead}/{sweep_ticks} "
          f"({100.0 * dead / max(sweep_ticks, 1):.1f}%)   "
          f"newly-tradeable {live} ({100.0 * live / max(sweep_ticks, 1):.1f}%)")
    if dead / max(sweep_ticks, 1) > 0.5:
        print("    THE CUT MOSTLY MOVES THE DEAD ZONE, it does not remove it.")
        print("    Those ticks land on UNKNOWN (hard-gated: only ORB has a")
        print("    bypass) or BREAKOUT_VOLATILE (subtractive: removes standalone")
        print("    continuation, enables nothing). Cutting the branch buys")
        print("    little — the real question is what SHOULD claim that tape.")
    else:
        print("    The ticks redistribute across labels that DO enable")
        print("    strategies, so removing the branch genuinely shrinks the")
        print("    dead zone rather than relocating it. Read the split above")
        print("    against what each label enables at dispatch before cutting.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
