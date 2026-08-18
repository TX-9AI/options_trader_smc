#!/usr/bin/env python3
"""
tests/pitchfork_touch_outcome.py — v1.1 — 2026-08-03

v1.1 — 2026-08-03 — THE CONTROL WAS UNSIGNED AND THE TOUCHES WERE SIGNED, so the
       two columns did not mean the same thing and could not be compared. Worse,
       the sign convention plausibly MANUFACTURES the pattern the first run showed.
       WHAT THE FIRST RUN SHOWED: every readable cell smaller than its own minimum
       detectable effect — but a consistent, monotone sign. upper/from_below ran
       -0.019 -> -0.118 -> -0.379 across h=1,2,4 and lower/from_above ran -0.064 ->
       -0.154 -> -0.441, both saying the rail did NOT hold and both GROWING with
       horizon. `lower/from_above/h=4` even separated from zero (-0.441 ±0.281).
       WHY THAT IS PROBABLY AN ARTIFACT OF MY OWN SIGN RULE: "from_below" means
       price approached the rail from underneath, which is what an UPTREND does,
       and that instance is assigned sign = -1. So in any drifting market, signing
       by approach side ANTI-CORRELATES with the drift and produces exactly this —
       negative, and growing with horizon because drift compounds. A raw-return
       control cannot reveal that, because signed and unsigned series have
       different expected values under the null.
       THE FIX: the control is now signed by THE SAME RULE. For every non-touch bar
       with a live fork, find the nearest rail, determine which side price sits on,
       apply the identical sign, and measure. Both columns then answer the same
       question and their difference is the rail effect with drift removed.

DOES PRICE REACT AT A RAIL? The one question the hourly fork can actually be
asked, and the only thing it produced in quantity.

WHY THIS AND NOT MORE FORK PLUMBING
    §5.2 is explicit: "tagging the median or either tine is NOT invalidation —
    those are the TRADEABLE EVENTS the whole overlay exists to produce." Every
    other measurement this week has been about the fork's internals. This is the
    first one about whether the fork is worth anything.
    It is also the highest-yield thing available without waiting for the daily
    series (AP): the hourly fork produced **162 TOUCH events against 33 births**.
    Touches are the abundant output; births are the scarce one.

WHAT AW ESTABLISHED THAT CONSTRAINS THE READING
    The hourly fork is NOT a level — coverage 10.1% mean / 5.3% median, median
    life ~9 bars, exceeded on the trend side 22 times in 33 births, and NO
    variant/N/D combination in the sweep produced a fork that both persists and
    contains price. So a touch here is a touch on an object that price is often
    outside of. A positive result would be surprising and would need replication
    on the daily fork before it meant anything; a null is the expected outcome and
    is not evidence against the DAILY fork, which is a different instrument.

THE THREE RAILS ARE THREE HYPOTHESES, never pooled
    upper   — resistance in a bullish fork, support in a bearish one
    median  — Andrews' mean-reversion anchor, the claim 2b already tested and
              found null over minute horizons (r² ~ 0.001)
    lower   — support in a bullish fork, resistance in a bearish one
    And APPROACH SIDE splits each again: a rail tagged from BELOW and one tagged
    from ABOVE are opposite trades. Pooling would average a bounce against a
    rejection and report zero for both.

THE OUTCOME IS SIGNED BY WHAT THE RAIL PREDICTS, not by direction
    "React at the rail" means price turns AWAY from it. For a bullish fork's
    LOWER rail touched from above, that is a move UP. For its UPPER rail touched
    from below, that is a move DOWN. So each instance is signed by its own
    expected reaction and a positive mean means the rails held.
    Against a matched CONTROL: bars in the SAME fork with no touch, same symbol.
    Without the control this measures hourly drift, not the rail.

POWER FIRST — read it before the table
    n=162 across three rails and two approach sides is ~27 per cell before any
    horizon split. The trade-level work this week established the discipline: a
    cell too small to resolve a plausible effect is UNDERPOWERED, not null, and
    labelling it null is the error that made a confounded condor split look real.
    So the minimum detectable effect is printed per cell and cells under n=20 are
    REFUSED outright.

USAGE (single line, control box, repo root)
    python3 tests/pitchfork_touch_outcome.py
    python3 tests/pitchfork_touch_outcome.py --horizons 1,2,4 --variant andrews

Read-only. Places nothing, sizes nothing, gates nothing.
"""

from __future__ import annotations

import argparse
import collections
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402

from analysis.pitchfork import DEFAULT_VARIANT  # noqa: E402
from analysis.pitchfork_lifecycle import BORN, INVALIDATED, TOUCH, replay  # noqa: E402
from utils.math_utils import atr_series  # noqa: E402

TAPE_ROOTS = ["~/day_trader_pro/ohlc", "./ohlc"]
DATE_RE = re.compile(r"^20\d\d-\d\d-\d\d$")
MIN_CELL_N = 20


def _tape_root(explicit=""):
    for r in ([explicit] if explicit else TAPE_ROOTS):
        p = os.path.expanduser(r)
        if os.path.isdir(p):
            return p
    return None


def _symbols(root):
    syms = set()
    for d in os.listdir(root):
        if not DATE_RE.match(d):
            continue
        for f in os.listdir(os.path.join(root, d)):
            low = f.lower()
            if "_ohlc_" in low and low.endswith(".csv"):
                syms.add(f.split("_ohlc_")[0].upper())
    return sorted(syms)


def _hourly(root, sym):
    frames = []
    for date in sorted(d for d in os.listdir(root) if DATE_RE.match(d)):
        day = os.path.join(root, date)
        for f in os.listdir(day):
            low = f.lower()
            if low.startswith(sym.lower() + "_ohlc_") and low.endswith(".csv"):
                try:
                    df = pd.read_csv(os.path.join(day, f), parse_dates=["timestamp"])
                except Exception:                                # noqa: BLE001
                    continue
                frames.append(df.set_index("timestamp").sort_index()
                              [["open", "high", "low", "close"]])
    if not frames:
        return None
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    return (pd.concat(frames).sort_index()
            .resample("1h", label="right", closed="right").agg(agg)
            .dropna(subset=["close"]))


def _mean_ci(xs):
    n = len(xs)
    if n < 2:
        return (xs[0] if n else 0.0), 0.0, n
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return m, 1.96 * math.sqrt(var / n), n


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tape-root", default="")
    ap.add_argument("--symbols", default="")
    ap.add_argument("--variant", default=DEFAULT_VARIANT)
    ap.add_argument("--horizons", default="1,2,4",
                    help="forward HOURLY bars (the fork's own timeframe)")
    a = ap.parse_args(argv[1:])
    horizons = [int(h) for h in a.horizons.split(",") if h.strip()]

    root = _tape_root(a.tape_root)
    if not root:
        print("No tape root found.")
        return 2
    syms = ([s.strip().upper() for s in a.symbols.split(",") if s.strip()]
            or _symbols(root))

    # (rail, approach, horizon) -> [signed reaction]; control keyed by horizon
    touch = collections.defaultdict(list)
    control = collections.defaultdict(list)
    n_touch = 0

    for sym in syms:
        h1 = _hourly(root, sym)
        if h1 is None or len(h1) < 25:
            continue
        closes = h1["close"].tolist()
        tr = replay(sym, h1, "1h", atr_series(h1, 14).tolist(), variant=a.variant)

        # which bars had a live fork, and its direction — needed to sign the
        # expected reaction, and to draw controls from the SAME population
        live = {}
        cur_dir = None
        for ev in tr.events:
            if ev.kind == BORN:
                cur_dir = ev.direction
            elif ev.kind == INVALIDATED:
                cur_dir = None
            if cur_dir:
                live[ev.idx] = cur_dir
        touched_idx = set()

        for ev in tr.events:
            if ev.kind != TOUCH:
                continue
            i = ev.idx
            rail = ev.detail.get("rail", "?")
            approach = ev.detail.get("approach", "?")
            touched_idx.add(i)
            n_touch += 1
            p0 = closes[i]
            if p0 <= 0:
                continue
            # "react" = turn AWAY from the rail. Touched from below -> the rail
            # is overhead, so a reaction is DOWN; from above -> reaction is UP.
            # NOTE this does not depend on FORK DIRECTION: an overhead rail is
            # resistance whether the fork is bullish or bearish. Splitting by
            # direction as well would fragment an already-thin n for nothing.
            sign = -1.0 if approach == "from_below" else 1.0
            for h in horizons:
                if i + h >= len(closes):
                    continue
                touch[(rail, approach, h)].append(
                    sign * 100.0 * (closes[i + h] - p0) / p0)

        # CONTROLS, v1.1: bars with a live fork and NO touch, signed by THE SAME
        # RULE as the touches. Find the nearest rail, work out which side price
        # sits on, apply the identical sign. Without this the control is a raw
        # drift series while the touches are sign-flipped, so the comparison is
        # meaningless and — worse — invisible, because both columns still print.
        fk_by_idx = tr.active_by_idx
        for i in live:
            if i in touched_idx or i >= len(closes) or closes[i] <= 0:
                continue
            fk = fk_by_idx.get(i)
            if fk is None:
                continue
            p0 = closes[i]
            rails = (("upper", fk.upper_at(i)), ("median", fk.median_at(i)),
                     ("lower", fk.lower_at(i)))
            name, rail = min(rails, key=lambda nr: abs(nr[1] - p0))
            sign = -1.0 if p0 <= rail else 1.0
            for h in horizons:
                if i + h >= len(closes):
                    continue
                control[h].append(sign * 100.0 * (closes[i + h] - p0) / p0)

    if not touch:
        print("No touches found. Check the tape root and that forks are building.")
        return 2

    print(f"tape {root} | variant {a.variant} | horizons {horizons} (HOURLY bars)")
    print(f"touch events: {n_touch}\n")
    print("A 'reaction' is price turning AWAY from the rail, so each instance is")
    print("signed by what its own rail predicts. Positive mean = the rails held.\n")

    print(f"{'rail':<8}{'approach':<12}{'h':>2} | {'reaction':>18} "
          f"{'control':>18} {'min detectable':>15}")
    print("-" * 78)
    any_read = False
    for rail in ("upper", "median", "lower"):
        for approach in ("from_below", "from_above"):
            for h in horizons:
                xs = touch.get((rail, approach, h), [])
                cs = control.get(h, [])
                if len(xs) < MIN_CELL_N:
                    print(f"{rail:<8}{approach:<12}{h:>2} | "
                          f"{'REFUSED n=' + str(len(xs)):>18}")
                    continue
                any_read = True
                m, hw, n = _mean_ci(xs)
                cm, chw, cn = _mean_ci(cs)
                sd = hw * math.sqrt(n) / 1.96 if n > 1 else 0.0
                mde = (1.96 + 0.84) * sd * math.sqrt(2.0 / n)
                diff = m - cm
                sep = abs(diff) > (hw + chw)
                mark = "  <- SEPARATES" if sep else ""
                print(f"{rail:<8}{approach:<12}{h:>2} | "
                      f"{m:+.4f}% ±{hw:.4f} n={n:<4} "
                      f"{cm:+.4f}% ±{chw:.4f}      {mde:+.4f}%{mark}")
    if not any_read:
        print("\nEVERY CELL REFUSED. 162 touches across 3 rails x 2 approach sides")
        print("x horizons is ~27 per cell before splitting, and the hourly fork's")
        print("10% coverage caps how many more can accrue. This is an ABSENT")
        print("MEASUREMENT, not a null — and per AW the answer is the DAILY fork")
        print("(AP), not more hourly tape.")
    else:
        print("\nBOTH COLUMNS ARE NOW SIGNED BY THE SAME RULE (v1.1), so their")
        print("DIFFERENCE is the rail effect with drift removed. A shared sign in")
        print("both columns is the sign convention, not the rails.")
        print("\nREAD THE 'min detectable' COLUMN FIRST. A cell whose reaction is")
        print("smaller than that is UNDERPOWERED, not null. Calling an underpowered")
        print("cell null is the error that made the confounded condor split look")
        print("real earlier this week.")
    print("\nAW's constraint stands: the hourly fork is not a level (10% coverage,")
    print("~9-bar life, no variant/N/D combination both persists and contains")
    print("price). A positive result here would need replication on the daily fork")
    print("before it meant anything.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
