#!/usr/bin/env python3
"""
tests/a2_rail_drift.py — v1.1 — 2026-08-03

v1.1 — 2026-08-03 — USES THE LIFECYCLE. v1.0 called build_fork once per hourly
       bar and used the result only when it returned non-None — which treated the
       fork as a PER-BAR INDICATOR, the one thing §5.2 says it is not. That is
       why Predictor 2 came back REFUSED at n=78 with "1,030 ticks with no usable
       fork": a fork that HOLDS was being asked to re-qualify from scratch every
       hour. Now it steps a ForkTracker (AS / analysis/pitchfork_lifecycle.py)
       through the hourly series once per symbol and reads `active_by_idx` — the
       fork that was actually IN EFFECT at that bar, which is the question a
       consumer should be asking.
       Whether Predictor 2's starvation was my bug or the data is exactly what
       this re-run answers.

CAN WE PREDICT WHERE PRICE GOES DURING A PAUSED TREND — with two predictors that
are both knowable at the tick, and neither of which is the pooled mean that
nearly killed the idea.

WHY a2_excursion's ANSWER WAS TOO SMALL, and it was my error not the data's
    That tool measured drift as a POOLED SCALAR — one mean across every
    paused-trend instance. But those instances sit inside trends of different
    slopes pointing in OPPOSITE directions. Averaging a +0.4%/hr uptrend against
    a -0.4%/hr downtrend gives zero. The +0.0184% that survived at h=5 is the
    RESIDUE of that cancellation, not what any instance did. The fix is to stop
    averaging across trends and start predicting PER INSTANCE.

PREDICTOR 1 — ELAPSED PERSISTENCE (fixes a look-ahead problem, not a small one)
    a2_excursion's `--persistent-only` conditions on the FUTURE: to know the
    state holds for the whole 5-bar window you must know bars t+1..t+5 are also
    violations. That is not knowable at t. Its result says "episodes that LASTED
    >= 5 bars behaved this way", NOT "when you see a violation, expect this" —
    the same class of error as anchoring a pitchfork at P2's own timestamp
    (whitepaper §4.4).
    What IS knowable at t is how long the state has ALREADY run. Episode duration
    measured p50 2 / p75 6 / p90 12, so a state already 3 bars old has materially
    better odds of continuing than a fresh one. This measures forward outcomes
    conditioned on ELAPSED bars only, with zero forward conditioning, and it maps
    directly onto the existing arming state machine.

PREDICTOR 2 — DISPLACEMENT FROM THE MEDIAN LINE
    The operator's point, and it closes a loop: a trend line taken out to a
    moment in time IS a drift prediction. `rail_price(t) = anchor + slope *
    (t - anchor_time)` — analysis/pitchfork.py already computes it (PF.1).
    Two distinct questions fall out, tested separately because they can disagree:
      2a SLOPE      does price move at the rate the median line predicts?
                    predicted = slope * h bars, expressed in % of price.
      2b REVERSION  Andrews' actual teaching is that price RETURNS to the ML. So
                    the signed target is (ML(t) - price(t)) — a per-instance
                    number, which is what "guess WHERE" actually asks for, rather
                    than a pooled average that cancels itself out.
    Both are reported as a REGRESSION of realized forward return on the
    prediction: a slope coefficient (1.0 = price moves exactly as predicted, 0 =
    no relationship) plus R² and binned means, so a weak-but-real relationship is
    visible instead of being collapsed into a single mean.

FORK CONSTRUCTION — the honest part
    Forks are HOURLY (k=3), built from 1m tape resampled to 1h and CONCATENATED
    ACROSS SESSIONS, because §4.3's recency filter R=40 bars is ~6 sessions at
    ~7 hourly bars/session. A fork is rebuilt only when a new hourly bar closes
    (cached per (symbol, hour index)), not per tick — the geometry is placed once
    and thereafter three linear evaluations, which is the whole cost argument.
    CONFIRMATION LAG IS PRESERVED: build_fork is called with now_idx = the last
    COMPLETED hourly bar at or before the tick, so no fork is used before
    index(P2) + k. Any result that ignored this would be fiction.

KNOWN WEAKNESS, stated up front
    The hourly fork's median line barely moves across a 5-minute window, so 2a
    (slope) has little to work with at these horizons — it is nearly a constant
    within an episode. 2b (reversion) does not have that problem: displacement is
    a level, not a rate. The DAILY fork would carry more slope per window and its
    series began accruing 2026-08-01 (daily_bars.py); re-run 2a when it ripens.

SCOPE NOTE
    This tests whether the fork PREDICTS anything. It is upstream of the white
    paper's condor-strike head-to-head (§9/PF.3) rather than a second consumer
    competing with it — rail-anchored strikes only make sense if the rail says
    something true about future price, and testing that directly is cheaper than
    a credit differential. §12 names consumer sprawl as a headline risk; this
    builds no consumer and gates nothing.

USAGE (single line, control box, repo root)
    python3 tests/a2_rail_drift.py
    python3 tests/a2_rail_drift.py --horizons 3,5,10 --window CLEAN

Read-only. Places nothing, sizes nothing, gates nothing.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402

from analysis.pitchfork_lifecycle import replay as fork_replay  # noqa: E402
from utils.math_utils import atr_series  # noqa: E402

TAPE_ROOTS = ["~/day_trader_pro/ohlc", "./ohlc"]
CORPUS_GLOB = "~/day_trader_pro/reports/regime_replay_*.jsonl"
DATE_RE = re.compile(r"(20\d\d-\d\d-\d\d)")
BUCKETS = (("OPEN", "09:30", "10:40"), ("DECAY", "10:40", "12:00"),
           ("CLEAN", "12:00", "16:00"))
MIN_N = 200          # lower than a2_excursion's 500: these cells are conditioned
                     # on elapsed persistence and are structurally smaller.


def time_bucket(ts: str):
    for name, lo, hi in BUCKETS:
        if lo <= ts < hi:
            return name
    return None


def _tape_root():
    for r in TAPE_ROOTS:
        p = os.path.expanduser(r)
        if os.path.isdir(p):
            return p
    return None


def _load_1m(root: str, sym: str):
    """Every session's 1m tape for one symbol, concatenated in time order."""
    frames = []
    for date in sorted(d for d in os.listdir(root)
                       if DATE_RE.match(d) and os.path.isdir(os.path.join(root, d))):
        day = os.path.join(root, date)
        for f in os.listdir(day):
            low = f.lower()
            if low.startswith(sym.lower() + "_ohlc_") and low.endswith(".csv"):
                try:
                    df = pd.read_csv(os.path.join(day, f), parse_dates=["timestamp"])
                except Exception:                                # noqa: BLE001
                    continue
                df = df.set_index("timestamp").sort_index()
                frames.append(df[["open", "high", "low", "close"]])
    if not frames:
        return None
    return pd.concat(frames).sort_index()


def _hourly(df1m):
    """1h bars, sessions concatenated. dropna removes the empty overnight bins,
    which is what makes the hourly series continuous in BAR INDEX space — the
    space the fork's slope is expressed in."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    return df1m.resample("1h", label="right", closed="right").agg(agg).dropna(subset=["close"])


def _magnitudes(pred, real):
    """Median |prediction| vs median |realized|. Reported alongside every
    regression because a coefficient far from 1.0 is ambiguous on its own: it can
    mean the predictor is DIRECTIONALLY right but far too SMALL, which is exactly
    the hourly fork's situation (its median line is nearly flat across a handful
    of 1-minute bars, so the prediction sits orders of magnitude under the noise
    it is buried in). Without these two numbers a reader cannot tell a scale
    mismatch from a broken formula — I mistook one for the other while building
    this."""
    def med(xs):
        if not xs:
            return 0.0
        s_ = sorted(abs(x) for x in xs)
        return s_[len(s_) // 2]
    return med(pred), med(real)


def _ols(xs, ys):
    """Least squares slope, intercept, r². Returns (slope, r2, n)."""
    n = len(xs)
    if n < 3:
        return 0.0, 0.0, n
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return 0.0, 0.0, n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    syy = sum((y - my) ** 2 for y in ys)
    r2 = (sxy ** 2) / (sxx * syy) if syy > 0 else 0.0
    return b, r2, n


def _mean_ci(xs):
    n = len(xs)
    if n < 2:
        return (xs[0] if n else 0.0), 0.0, n
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return m, 1.96 * math.sqrt(var / n), n


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizons", default="3,5,10")
    ap.add_argument("--window", default="CLEAN")
    ap.add_argument("--tape-root", default="")
    a = ap.parse_args(argv[1:])
    horizons = [int(h) for h in a.horizons.split(",") if h.strip()]
    want = a.window.upper()

    root = os.path.expanduser(a.tape_root) if a.tape_root else _tape_root()
    if not root:
        print("No tape root found (looked in " + ", ".join(TAPE_ROOTS) + ")")
        return 2
    paths = sorted(glob.glob(os.path.expanduser(CORPUS_GLOB)))
    if not paths:
        print("No replay corpus found.")
        return 2

    # elapsed[(elapsed_bucket, h)] -> [forward signed return]
    elapsed = collections.defaultdict(list)
    control = collections.defaultdict(list)
    # regression samples: predicted vs realized, per horizon
    slope_pred = collections.defaultdict(list)
    slope_real = collections.defaultdict(list)
    revert_pred = collections.defaultdict(list)
    revert_real = collections.defaultdict(list)
    no_fork = 0
    hourly_cache = {}
    tracker_cache = {}

    for path in paths:
        date = DATE_RE.search(os.path.basename(path))
        if not date:
            continue
        by_sym = collections.defaultdict(list)
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:                                # noqa: BLE001
                    continue
                by_sym[r.get("sym", "?")].append(r)

        for sym, recs in by_sym.items():
            if sym not in hourly_cache:
                df1m = _load_1m(root, sym)
                hourly_cache[sym] = _hourly(df1m) if df1m is not None else None
            h1 = hourly_cache[sym]

            prices = [float(r.get("price") or 0.0) for r in recs]
            viols = []
            for r in recs:
                sc = r.get("scores") or {}
                t_ = max(float(sc.get("TRENDING_BULL") or 0.0),
                         float(sc.get("TRENDING_BEAR") or 0.0))
                viols.append(t_ > 0.5 and float(sc.get("RANGING") or 0.0) > 0.5)

            # elapsed[i] = how many consecutive violation bars END at i, inclusive.
            # Uses only the PAST, which is the whole point.
            run = 0
            elapsed_at = []
            for v in viols:
                run = run + 1 if v else 0
                elapsed_at.append(run)

            # step the lifecycle through this symbol's hourly series ONCE; the
            # fork in effect at bar i is then a lookup, not a rebuild
            if h1 is not None and sym not in tracker_cache:
                tracker_cache[sym] = fork_replay(
                    sym, h1, "1h", atr_series(h1, 14).tolist())
            tracker = tracker_cache.get(sym)
            for i, r in enumerate(recs):
                if time_bucket(r.get("ts", "")) != want:
                    continue
                p0 = prices[i]
                if p0 <= 0:
                    continue
                sc = r.get("scores") or {}
                bull = float(sc.get("TRENDING_BULL") or 0.0)
                bear = float(sc.get("TRENDING_BEAR") or 0.0)
                sign = 1.0 if bull >= bear else -1.0
                e = elapsed_at[i]

                for h in horizons:
                    j = i + h
                    if j >= len(prices) or prices[j] <= 0:
                        continue
                    realized = sign * 100.0 * (prices[j] - p0) / p0
                    if e == 0:
                        control[h].append(realized)
                        continue
                    bucket = "1" if e == 1 else ("2-3" if e <= 3 else
                                                 ("4-7" if e <= 7 else "8+"))
                    elapsed[(bucket, h)].append(realized)

                # ── predictor 2: the fork ────────────────────────────────────
                if h1 is None or e == 0:
                    continue
                ts = pd.Timestamp(f"{date.group(1)}T{r['ts']}:00")
                try:
                    ts = ts.tz_localize(h1.index.tz)
                except Exception:                                # noqa: BLE001
                    pass
                # last COMPLETED hourly bar at or before this tick — the
                # confirmation-lag rule is enforced inside build_fork from here.
                hidx = h1.index.searchsorted(ts, side="right") - 1
                if hidx < 20:
                    continue
                fk = tracker.active_by_idx.get(hidx) if tracker else None
                if fk is None or not fk.is_born_by(hidx):
                    no_fork += 1
                    continue
                ml_now = fk.median_at(hidx)
                if ml_now <= 0:
                    continue
                for h in horizons:
                    j = i + h
                    if j >= len(prices) or prices[j] <= 0:
                        continue
                    realized = 100.0 * (prices[j] - p0) / p0
                    # 2a slope: h one-minute bars = h/60 of an hourly bar
                    slope_pred[h].append(100.0 * fk.slope * (h / 60.0) / p0)
                    slope_real[h].append(realized)
                    # 2b reversion: signed distance to the median line
                    revert_pred[h].append(100.0 * (ml_now - p0) / p0)
                    revert_real[h].append(realized)

    if not elapsed:
        print("Nothing measured — check the corpus and tape roots.")
        return 2

    print(f"corpus files {len(paths)} | tape {root} | window {want} | "
          f"horizons {horizons}")
    print(f"ticks with no usable fork: {no_fork}\n")

    print("=" * 62)
    print("PREDICTOR 1 — ELAPSED PERSISTENCE (knowable at the tick)")
    print("=" * 62)
    print("  How long the state has ALREADY run. No forward conditioning, so")
    print("  unlike --persistent-only this is something a live gate could use.\n")
    for h in horizons:
        cm, ch, cn = _mean_ci(control[h])
        print(f"  h={h} bars   control (no violation) {cm:+.4f}% ±{ch:.4f} (n={cn})")
        for bucket in ("1", "2-3", "4-7", "8+"):
            xs = elapsed[(bucket, h)]
            if len(xs) < MIN_N:
                print(f"    elapsed {bucket:<4} REFUSED (n={len(xs)} < {MIN_N})")
                continue
            m, hw, n = _mean_ci(xs)
            sep = abs(m - cm) > (hw + ch)
            verdict = ("RESUMES" if m > cm else "FADES") if sep else "no edge"
            print(f"    elapsed {bucket:<4} {m:+.4f}% ±{hw:.4f} (n={n})  "
                  f"vs control {m - cm:+.4f}  -> {verdict}")
        print()

    print("=" * 62)
    print("PREDICTOR 2 — THE MEDIAN LINE (analysis/pitchfork.py, hourly fork)")
    print("=" * 62)
    print("  Regression of REALIZED forward return on the fork's PREDICTION.")
    print("  coefficient 1.0 = price moves exactly as predicted; 0 = unrelated.")
    print("  Reported unsigned — these are per-instance predictions, so unlike a")
    print("  pooled mean, opposite-signed trends do not cancel.\n")
    for h in horizons:
        b, r2, n = _ols(slope_pred[h], slope_real[h])
        if n < MIN_N:
            print(f"  h={h}  2a SLOPE      REFUSED (n={n} < {MIN_N})")
        else:
            mp, mr = _magnitudes(slope_pred[h], slope_real[h])
            ratio = (mr / mp) if mp > 0 else float("inf")
            print(f"  h={h}  2a SLOPE      coef {b:+.3f}  r2 {r2:.4f}  (n={n})")
            print(f"           median |predicted| {mp:.6f}%  vs  |realized| "
                  f"{mr:.6f}%  ({ratio:.0f}x)")
            if ratio > 20:
                print("           -> SCALE MISMATCH, not necessarily a failure: the "
                      "prediction is\n              far smaller than the noise it "
                      "sits in, so read r2 (is there a\n              relationship "
                      "at all?) and IGNORE the coefficient's magnitude.")
        b2, r22, n2 = _ols(revert_pred[h], revert_real[h])
        if n2 < MIN_N:
            print(f"        2b REVERSION  REFUSED (n={n2} < {MIN_N})")
        else:
            mp2, mr2 = _magnitudes(revert_pred[h], revert_real[h])
            print(f"        2b REVERSION  coef {b2:+.3f}  r2 {r22:.4f}  (n={n2})")
            print(f"           median |displacement| {mp2:.4f}%  vs  |realized| "
                  f"{mr2:.4f}%")
            if b2 > 0.05:
                print(f"           -> price moves TOWARD the median line: "
                      f"{b2:.0%} of the gap closes in {h} bars.")
            elif b2 < -0.05:
                print("           -> price moves AWAY from the median line — "
                      "the fork is\n              describing divergence, not "
                      "attraction. Worth knowing.")
            else:
                print("           -> no relationship to the median line at this "
                      "horizon.")
    print("\nNOTE: the HOURLY median line barely moves across a few 1-minute "
          "bars, so 2a\nhas little to work with here — 2b is the load-bearing "
          "test. Re-run 2a when\nthe DAILY fork ripens (daily_bars.py, ~Aug 21).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
