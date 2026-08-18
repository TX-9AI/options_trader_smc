#!/usr/bin/env python3
"""
tests/pitchfork_prior_sweep.py — v1.2 — 2026-08-03

v1.2 — 2026-08-03 — +VARIANT rows, because TWO ROUNDS OF FIXING THE KILL RULE
       BOTH FAILED and the evidence points at the GEOMETRY instead.
       v1.1 measured the pivot form and it came back WORSE: best adverse-share
       CLOSES 56.5% vs PIVOT 72.0%. So the §5.3(b) replacement I wrote into the
       whitepaper is not supported by the tape, and the paper has been amended to
       say so rather than keep it.
       WHY IT FAILED, and it was foreseeable: a k=3 FRACTAL PIVOT IS NOT A
       STRUCTURAL FILTER. It is a local extremum over a 7-bar window, and an
       ordinary pullback produces one every few bars. The claim that "a pivot
       requires the excursion to have structure" was wrong — it requires a local
       low, which is nearly free.
       THE READING THAT NOW FITS EVERYTHING: 22 ACCELERATION events on 33 births,
       AND 56-89% adverse deaths. **Price is leaving the channel on BOTH SIDES,
       routinely.** No invalidation rule can look good if the fork is not
       describing the price envelope in the first place — that is a GEOMETRY
       problem, and §12 open question 2 (variant) is exactly where the paper says
       evidence should decide it. §3.2 chose Modified Schiff "on reasoning, not
       evidence".
       MEASURED on a trending fixture: andrews slope +0.70/bar with channel width
       29.6; modified_schiff +0.26 and 23.5; schiff +0.17 and 22.1. Andrews is
       both STEEPER and WIDER, which is the shape that would contain price
       escaping on both sides. Variant rows test that instead of assuming it.
       ACCELERATION RATE is now reported per row, since "channel too narrow" is
       the hypothesis and acceleration is its direct symptom.
v1.1 — 2026-08-03 — +the PIVOT form, measured against the same criterion. v1.0
       swept N x D on §5.3(b) as WRITTEN and returned NO SETTING CLEARS THE BAR:
       adverse-tine went 88.9% -> 56.5% across the whole grid while deaths barely
       moved (27 -> 23). That is the signature of a rule wrong in FORM, so
       lifecycle v1.2 added `adverse_mode="pivot"` — invalidate on a CONFIRMED
       PIVOT beyond the counter tine rather than on N consecutive closes.
       It was built but never measured, which left the whitepaper asserting the
       written form is broken while offering an untested replacement. This closes
       that: pivot rows run under the SAME pre-registered criterion, so the two
       forms are comparable rather than merely both present.
       PIVOT MODE IGNORES N — it counts no consecutive closes — so it is swept on
       D alone and N is shown as "-".

WHAT N AND D SHOULD BE FOR THE HOURLY FORK — with the criterion fixed BEFORE the
numbers are looked at.

THE FINDING THAT PROMPTED THIS
    pitchfork_filter_audit v1.3 on the real tape, 29 symbols:
        CAUSE OF DEATH   24 (88.9%) adverse tine     3 (11.1%) structural (P0)
        LIFETIME         min 2   p50 5   p90 27   max 53   (hourly bars)
        COVERAGE         10.1% mean, 5.3% median, 0.0% min
    A p50 of five hourly bars is under one session. §5.2 expects a persistent
    object to survive far longer, and §5.3(a) calls structural break "the
    strongest and cleanest condition" — yet it accounts for 11% of deaths while a
    threshold accounts for 89%.
    **The anchors are fine. Structural breaks are RARE, so the underlying
    P0/P1/P2 structures are durable — it is the KILL RULE ending them.**

WHY THE PRIOR IS WRONG RATHER THAN THE TAPE
    §5.3(b) gives "Start N = 2, D = 0.25" with NO TIMEFRAME QUALIFIER. Two
    consecutive DAILY closes 0.25 ATR beyond a rail is a real structural event.
    Two consecutive HOURLY closes is an ordinary pullback — roughly two hours of
    drift against the channel. The prior was not mis-specified so much as applied
    at a timeframe it was never scaled for, which is the same shape as every
    other finding this week: a value that was fine where it was written and wrong
    where it was used.

THE CRITERION, PRE-REGISTERED — read this before the table
    §10 names the ten-parameter surface as a headline overfitting risk, so
    "sweep until coverage looks good" is exactly the failure mode to avoid.
    Coverage is therefore NOT the target. The paper supplies a better one:

        §5.3(a) calls structural break the STRONGEST and CLEANEST condition.
        A healthy fork should die mostly THAT way.

    So the pre-registered rule is: **choose the SMALLEST (N, D) at which
    adverse-tine ceases to be the dominant cause of death — adverse share below
    50%.** Smallest, not best: the loosest setting that clears the bar, because
    every further loosening buys coverage by declining to invalidate, which is
    not the same as the fork being right.

    Two guards on that:
      - If NO setting in the grid clears 50%, do not pick the best of a bad grid.
        That result means the adverse-tine rule is wrong in FORM rather than in
        magnitude, and the answer is a different condition, not a bigger number.
      - Coverage is reported alongside but must not drive the choice. If the
        chosen setting also happens to maximise coverage, that is a coincidence
        to note, not a justification.

WHAT THIS DOES NOT DO
    It does not change a default. It prints a table and names the setting the
    criterion selects. Changing §5.3's priors is a separate, deliberate act — and
    per AW the hourly fork is not on the critical path anyway, so there is no
    reason to rush it. The DAILY fork is where these priors were always meant to
    live, and it does not exist yet (AP).

USAGE (single line, control box, repo root)
    python3 tests/pitchfork_prior_sweep.py
    python3 tests/pitchfork_prior_sweep.py --symbols SPX,QQQ,NVDA

Read-only. Changes no default, gates nothing.
"""

from __future__ import annotations

import argparse
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402

from analysis.pitchfork_lifecycle import replay  # noqa: E402
from utils.math_utils import atr_series  # noqa: E402

TAPE_ROOTS = ["~/day_trader_pro/ohlc", "./ohlc"]
DATE_RE = re.compile(r"^20\d\d-\d\d-\d\d$")

# The grid. N is bars, D is ATR multiples. The paper's start values (2, 0.25) are
# the top-left corner so the table always shows where we came from.
N_GRID = (2, 3, 4, 6)
D_GRID = (0.25, 0.50, 1.00)

ADVERSE_DOMINANT = 0.50     # the pre-registered bar
# A cell with almost no deaths passes the bar VACUOUSLY — "0 of 0 is under 50%"
# would crown a setting that simply never invalidates anything, which is the
# degenerate answer the criterion exists to avoid. Caught on the first run.
MIN_DEATHS = 10


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


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tape-root", default="")
    ap.add_argument("--symbols", default="")
    a = ap.parse_args(argv[1:])

    root = _tape_root(a.tape_root)
    if not root:
        print("No tape root found.")
        return 2
    syms = ([s.strip().upper() for s in a.symbols.split(",") if s.strip()]
            or _symbols(root))

    frames = {}
    for sym in syms:
        h1 = _hourly(root, sym)
        if h1 is not None and len(h1) >= 25:
            frames[sym] = (h1, atr_series(h1, 14).tolist())
    if not frames:
        print(f"No usable hourly series under {root}")
        return 2

    print(f"tape {root} | {len(frames)} symbol(s)")
    print("CRITERION (pre-registered, see header): the SMALLEST (N, D) at which")
    print("adverse-tine drops below 50% of deaths. Coverage is reported but must")
    print("NOT drive the choice — §5.3(a) calls structural the cleanest condition,")
    print("so a healthy fork should die mostly that way.\n")

    print("CLOSES form = §5.3(b) as written. PIVOT form = lifecycle v1.2's")
    print("replacement (confirmed pivot beyond the counter tine; ignores N).\n")
    print(f"{'variant':<9}{'N':>2} {'D':>5} | {'cover':>6} {'births':>6} "
          f"{'deaths':>6} {'adverse%':>8} {'accel/fk':>7} {'p50':>8}")
    print("-" * 74)

    results = {}
    # (mode, n, d) — pivot ignores N, so it gets one row per D
    combos = [("modified_schiff", "closes", n, d) for n in N_GRID for d in D_GRID]
    combos += [("modified_schiff", "pivot", None, d) for d in D_GRID]
    # §12 open question 2 — the variant was chosen on reasoning, not evidence.
    # Held at the paper's own N/D so the variant is the only thing changing.
    combos += [(v, "closes", 2, 0.25) for v in ("andrews", "schiff")]
    combos += [(v, "closes", 6, 1.00) for v in ("andrews", "schiff")]
    for variant, mode, n, d in combos:
        if True:
            covs, births, cause, lifetimes = [], 0, collections.Counter(), []
            accel = 0
            for sym, (h1, atrs) in frames.items():
                tr = replay(sym, h1, "1h", atrs, variant=variant,
                            adverse_closes=(n or 2), adverse_atr=d,
                            adverse_mode=mode)
                covs.append(tr.coverage(len(h1)))
                born_at = None
                for ev in tr.events:
                    if ev.kind == "ACCELERATION":
                        accel += 1
                    if ev.kind == "BORN":
                        births += 1
                        born_at = ev.idx
                    elif ev.kind == "INVALIDATED":
                        cause["adverse" if "adverse" in ev.reason
                              else "structural" if "structural" in ev.reason
                              else "other"] += 1
                        if born_at is not None:
                            lifetimes.append(ev.idx - born_at)
                            born_at = None
            deaths = sum(cause.values())
            adv = cause["adverse"] / deaths if deaths else 0.0
            cov = sum(covs) / len(covs)
            p50 = sorted(lifetimes)[len(lifetimes) // 2] if lifetimes else 0
            accel_rate = accel / births if births else 0.0
            results[(variant, mode, n, d)] = (cov, births, deaths, adv, p50,
                                              accel_rate)
            star = (" <- paper's start"
                    if (variant, mode, n, d) == ("modified_schiff", "closes", 2, 0.25)
                    else " <- PIVOT" if mode == "pivot"
                    else f" <- {variant.upper()}" if variant != "modified_schiff"
                    else "")
            nlabel = "-" if n is None else str(n)
            print(f"{variant[:8]:<9}{nlabel:>2} {d:>5.2f} | {cov:>6.1%} "
                  f"{births:>6} {deaths:>6} {adv:>8.1%} {accel_rate:>7.1f} "
                  f"{p50:>8}{star}")

    # ── apply the criterion, without looking at coverage ────────────────────
    print("\n" + "=" * 60)
    eligible = {k: r for k, r in results.items() if r[2] >= MIN_DEATHS}
    thin = len(results) - len(eligible)
    if thin:
        print(f"  ({thin} cell(s) had fewer than {MIN_DEATHS} deaths and are NOT "
              f"eligible —\n   a setting that never invalidates passes the bar "
              f"vacuously.)")
    passing = [k for k, r in eligible.items() if r[3] < ADVERSE_DOMINANT]
    closes_best = min((r[3] for k, r in eligible.items()
                       if k[1] == "closes" and k[0] == "modified_schiff"),
                      default=None)
    pivot_best = min((r[3] for k, r in eligible.items() if k[1] == "pivot"),
                     default=None)
    for v in ("andrews", "schiff"):
        rows = [(k, r) for k, r in eligible.items() if k[0] == v]
        if rows:
            best = min(rows, key=lambda kr: kr[1][3])
            print(f"  {v:>16}: adverse {best[1][3]:.1%}  cover {best[1][0]:.1%}  "
                  f"accel/fork {best[1][5]:.1f}  p50 {best[1][4]}")
    if closes_best is not None and pivot_best is not None:
        print(f"  best adverse-share: CLOSES {closes_best:.1%}   "
              f"PIVOT {pivot_best:.1%}")
        if pivot_best >= closes_best:
            print("  -> the PIVOT form does NOT improve on the written one. The")
            print("     whitepaper §5.3(b) correction claimed a replacement that")
            print("     the tape does not support — say so rather than keep it.")
    if not eligible:
        print("VERDICT  REFUSED — no cell has enough deaths to judge. Either the")
        print("         tape is too short or no fork ever invalidated. Nothing")
        print("         here supports changing a prior.")
    elif not passing:
        print("VERDICT  NO SETTING CLEARS THE BAR. Adverse-tine stays dominant")
        print("         across the whole grid, so the rule is wrong in FORM, not")
        print("         in magnitude — a bigger N is not the answer. §5.3(b) may")
        print("         need a different condition entirely (e.g. requiring the")
        print("         break to persist past a rail RE-TEST rather than counting")
        print("         consecutive closes). Do NOT pick the best of a bad grid.")
    else:
        # "smallest" = fewest bars, then smallest ATR margin
        pick = sorted(passing, key=lambda k: (k[1] != "pivot", k[2] or 0, k[3]))[0]
        cov, births, deaths, adv, p50 = results[pick]
        best_cov = max(r[0] for r in eligible.values())
        pv, pm, pn, pd = pick
        print(f"VERDICT  {pv} / {pm.upper()} form, N={'-' if pn is None else pn}, "
              f"D={pd:.2f} — the SMALLEST setting where")
        print(f"         adverse-tine is no longer dominant ({adv:.1%} of {deaths}"
              f" deaths).")
        print(f"         coverage {cov:.1%}, p50 life {p50} bars, {births} births.")
        if abs(cov - best_cov) < 1e-9:
            print("         NOTE: this also happens to maximise coverage. That is a")
            print("         coincidence to record, not a justification — the")
            print("         criterion did not use it.")
        else:
            print(f"         (max coverage in the grid is {best_cov:.1%} at a looser")
            print("         setting — deliberately NOT chosen, since coverage bought")
            print("         by declining to invalidate is not the fork being right.)")
    print("=" * 60)
    print("This changes NO default. Per AW the hourly fork is off the critical")
    print("path; the DAILY fork is where these priors were always meant to live,")
    print("and it does not exist yet (AP).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
