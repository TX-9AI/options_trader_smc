#!/usr/bin/env python3
"""
tests/pitchfork_filter_audit.py — v1.5 — 2026-08-04

v1.5 — 2026-08-04 — ACCEL PER HELD BAR, because per-birth was CONFOUNDED and
       the first real run showed it. On the 29-symbol corpus v1.4 printed
       andrews 0.22 against modified_schiff 0.67 — a 3x gap that reads as
       "andrews contains the move far better". But andrews also has the SHORTEST
       median life (3 bars against 6), and a fork that dies at bar 3 has less
       time to be exceeded than one that lives to 7. The rate was measuring
       longevity as much as geometry. Per HELD BAR the same run is roughly
       0.073 / 0.112 / 0.516 — schiff stays disqualified, and the
       andrews-vs-modified gap falls from ~3x to ~1.5x.
       Both are printed. Per birth answers "how often does a fork get exceeded
       in its lifetime"; per held bar answers "how often per unit of exposure",
       and only the second is comparable across variants with different
       lifetimes. Neither decides a default — §10's overfitting surface and
       §12's consumer-sprawl risk are unchanged by a better denominator.

v1.4 — 2026-08-04 — `--variant-sweep`, WHICH IS THE ONE PITCHFORK QUESTION NOT
       BLOCKED ON THE CALENDAR. v1.3 flagged 22 ACCELERATION events against 33
       births and said, correctly, that forks exceeded on the TREND side
       two-thirds of the time look like a channel too NARROW for the move it
       describes — plausibly a Modified Schiff artifact, since §3.2 chose that
       variant precisely because Andrews runs steep. It reported the count "so it
       can be watched rather than assumed" and then nobody could act on it,
       because watching one variant tells you nothing about the other two.
       `build_all_variants` has computed all three in parallel since PF.1 and
       `ForkTracker` already threads `variant`, so the sweep is plumbing, not new
       geometry. It runs the SAME lifecycle on the SAME tape three times and
       prints births, MEDIAN coverage, the ACCELERATION rate per birth, the
       cause-of-death split and the lifetime distribution side by side.
       WHAT IT CAN AND CANNOT DECIDE. It is a GEOMETRY comparison, not an
       outcome one: a variant that gets exceeded less often is describing the
       move better, which is a necessary property, never a profitable one. §12
       names consumer sprawl as a headline risk and §10 names the ten-parameter
       surface as an overfitting risk — so this changes NO prior and ships no
       default. Picking the variant with the prettiest coverage would be exactly
       the fit-to-the-number this file exists to avoid.

v1.3 — 2026-08-03 — WHICH CONDITION IS KILLING THEM, and how long they live.
       v1.2's coverage run raised a question it could not answer: 27 INVALIDATED
       against 33 BORN, so forks die almost as fast as they are born. §5.2 expects
       a persistent object to survive far longer, and "27 deaths" does not say
       whether the TAPE is unsuitable or the §4.3/§5.3 PRIORS are strangling the
       object. Those have opposite responses — accept the fork is rare, versus
       revisit N/D. Now every INVALIDATED event is binned by cause and the
       lifetime distribution is printed.
       ALSO WATCHING: 22 ACCELERATION events on 33 births. Forks being exceeded
       on the TREND side two-thirds of the time suggests the channel is too
       narrow for the move it is describing — plausibly a Modified Schiff
       artifact, since §3.2 chose it precisely because Andrews runs steep. That
       is a variant question, not a threshold one, and the count is reported so
       it can be watched rather than assumed.
v1.2 — 2026-08-03 — MEASURES COVERAGE NOW THAT LIFECYCLE EXISTS. v1.1 could only
       report the BIRTH rate and said so; with analysis/pitchfork_lifecycle.py
       (AS) the fork HOLDS until invalidated, so the number that actually matters
       is finally computable. Both are printed side by side, because the whole
       point of AS was that conflating them made the fork look starved: 156
       births from 2,297 attempts read as 6.8% "coverage" when it was ~5 anchor
       events per symbol in three weeks — entirely normal for a persistent object.
       The per-bar build_fork walk is KEPT, not replaced, because it is still the
       only way to attribute rejections to a filter. It just no longer pretends
       to be a coverage measurement.
v1.1 — 2026-08-01 — VERDICT BINNING CORRECTED, AND WHAT 6.8% ACTUALLY MEASURES.
       v1.0 swept STRUCTURAL_* into "filter tightness" and reported
       "FILTER TIGHTNESS (2064 vs 77)" on the first real run. That overstates it
       badly: `P2_not_above_P0` does NOT mean a threshold is too tight, it means
       the last three pivots are NOT A DIRECTIONAL STRUCTURE — a correct
       rejection of chop, with no parameter behind it. Re-binned honestly the
       same counts read ~52% no-structure-exists (STRUCTURAL 1,128 + fewer-than-3
       77), ~41% parameter-sensitive (SEPARATION 915 + SIGNIFICANCE 21), 6.8%
       built. Three bins now, not two.
       AND THE HEADLINE NUMBER IS MISNAMED. 6.8% is the fork BIRTH rate — this
       tool calls the stateless build_fork at EVERY index. But §5.2 says a fork
       HOLDS UNTIL INVALIDATED, so with lifecycle implemented one birth covers
       every bar until it dies. 156 births across 29 symbols is ~5 anchor events
       per symbol in three weeks, which is entirely reasonable for a PERSISTENT
       object. Coverage is the number that matters and it is not measured here.

WHY THE HOURLY FORK ALMOST NEVER BUILDS — corpus length, or filter tightness?

`a2_rail_drift` reported **1,030 ticks with no usable fork** and only n=78 for
both median-line regressions, so Predictor 2 was REFUSED at every horizon. That
is a NON-RESULT, not a negative — the question was never measured. But the two
possible causes have opposite responses:

    CORPUS LENGTH   15 sessions is ~105 hourly bars per symbol. If most
                    rejections are FRAME_TOO_SHORT or
                    FEWER_THAN_3_ALTERNATING_PIVOTS, the series simply does not
                    yet contain qualifying structure -> WAIT. Bars accrue at ~7
                    per session; PF.2 is blocked on time, not on design.

    FILTER TIGHTNESS  If most rejections are SIGNIFICANCE / SEPARATION /
                    RECENCY, the §4.3 priors (S=1.0 ATR, 2k+1 separation, R=40)
                    are too tight for a series this short -> REVISIT THE PRIORS.
                    §10 already names the ten-parameter surface as an overfitting
                    risk, so any loosening must be pre-registered and justified
                    from THIS audit rather than tuned until forks appear.

This walks each symbol's hourly series bar by bar, calls the REAL build_fork at
every index (so the confirmation-lag rule and every filter are exactly the
shipped ones), and tallies `last_reject_reason()`. It duplicates no filter logic —
that was the point of adding the reasons to pitchfork.py v1.1 rather than
reimplementing the gate chain here and creating a second lineage of it.

Read-only. Builds nothing, changes no threshold, recommends no value.

USAGE (single line, control box, repo root)
    python3 tests/pitchfork_filter_audit.py
    python3 tests/pitchfork_filter_audit.py --symbols SPX,QQQ
"""

from __future__ import annotations

import argparse
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402

from analysis.pitchfork import build_fork, last_reject_reason  # noqa: E402
from analysis.pitchfork_lifecycle import replay  # noqa: E402
from utils.math_utils import atr_series  # noqa: E402

TAPE_ROOTS = ["~/day_trader_pro/ohlc", "./ohlc"]
DATE_RE = re.compile(r"^20\d\d-\d\d-\d\d$")


def _tape_root(explicit: str = ""):
    for r in ([explicit] if explicit else TAPE_ROOTS):
        p = os.path.expanduser(r)
        if os.path.isdir(p):
            return p
    return None


def _symbols(root: str):
    syms = set()
    for d in os.listdir(root):
        if not DATE_RE.match(d):
            continue
        for f in os.listdir(os.path.join(root, d)):
            low = f.lower()
            if "_ohlc_" in low and low.endswith(".csv"):
                syms.add(f.split("_ohlc_")[0].upper())
    return sorted(syms)


def _hourly(root: str, sym: str):
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
    df1m = pd.concat(frames).sort_index()
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    return df1m.resample("1h", label="right", closed="right").agg(agg).dropna(subset=["close"])


def _variant_sweep(root, syms, scan) -> int:
    """§12 open question 2 — the three variants, same tape, same lifecycle.

    Reports the ACCELERATION RATE PER BIRTH rather than a raw count, because a
    variant that simply builds more forks would otherwise look worse for being
    more productive. Median coverage rather than mean, for the reason AW already
    established: the mean was 10.1% while the median was 5.3% and half the
    symbols carried a fork under 5% of the time.
    """
    from analysis.pitchfork import VARIANTS

    print("=" * 74)
    print("VARIANT SWEEP — §12 open question 2 (geometry only; changes nothing)")
    print("=" * 74)
    rows = []
    for variant in VARIANTS:
        births = accel = touches = invalid = superseded = 0
        covs, lifetimes = [], []
        covs_raw, bars_raw = [], []
        causes = collections.Counter()
        for sym in syms:
            h1 = _hourly(root, sym)
            if h1 is None or len(h1) < 25:
                continue
            av = atr_series(h1, 14).tolist()
            tr = replay(sym, h1, "1h", av, variant=variant,
                        uniqueness_scan=scan)
            _cov = tr.coverage(len(h1))
            covs.append(_cov)
            covs_raw.append(_cov)
            bars_raw.append(len(h1))
            born_at = None
            for ev in tr.events:
                if ev.kind == "BORN":
                    births += 1
                    born_at = ev.idx
                elif ev.kind == "ACCELERATION":
                    accel += 1
                elif ev.kind == "TOUCH":
                    touches += 1
                elif ev.kind == "SUPERSEDED":
                    superseded += 1
                elif ev.kind == "INVALIDATED":
                    invalid += 1
                    r = ev.reason
                    causes[("structural (P0)" if "structural" in r
                            else "adverse tine" if "adverse" in r
                            else "stale" if "stale" in r else r[:20])] += 1
                    if born_at is not None:
                        lifetimes.append(ev.idx - born_at)
                        born_at = None
        covs.sort()
        med_cov = covs[len(covs) // 2] if covs else 0.0
        # v1.5 — held bars, the honest denominator. Derived from the SAME span
        # accounting coverage() uses, so the two can never disagree.
        held_bars = sum(c * n for c, n in zip(covs_raw, bars_raw)) if covs_raw else 0.0
        lifetimes.sort()
        med_life = lifetimes[len(lifetimes) // 2] if lifetimes else None
        rows.append({"variant": variant, "births": births, "accel": accel,
                     "touch": touches, "inval": invalid, "sup": superseded,
                     "cov": med_cov, "life": med_life, "causes": causes,
                     "held": held_bars})

    print(f"  {'variant':<18}{'births':>8}{'med cov':>9}{'ACCEL/birth':>13}"
          f"{'ACCEL/held bar':>16}{'touch/birth':>13}{'med life':>10}")
    for r in rows:
        ab = f"{r['accel'] / r['births']:.2f}" if r["births"] else "—"
        ah = f"{r['accel'] / r['held']:.3f}" if r["held"] else "—"
        tb = f"{r['touch'] / r['births']:.2f}" if r["births"] else "—"
        life = r["life"] if r["life"] is not None else "—"
        print(f"  {r['variant']:<18}{r['births']:>8}{r['cov']:>8.1%}"
              f"{ab:>13}{ah:>16}{tb:>13}{str(life):>10}")

    print("\n  CAUSE OF DEATH, per variant")
    for r in rows:
        tot = sum(r["causes"].values())
        parts = "  ".join(f"{k} {v}({v / tot:.0%})"
                          for k, v in r["causes"].most_common()) if tot else "—"
        print(f"    {r['variant']:<18} {parts}")

    print("\n" + "=" * 74)
    print("READING IT")
    print("=" * 74)
    print("  READ ACCEL/HELD BAR FIRST. Per-birth is confounded by LIFETIME — a")
    print("  variant whose forks die early has less time to be exceeded and looks")
    print("  better for being fragile. Per held bar divides by exposure, which is")
    print("  the only denominator comparable across variants with different lives.")
    print("  ACCELERATION/birth is the number v1.3 flagged. A rate near or above")
    print("  1.0 means the channel is routinely exceeded on the TREND side — the")
    print("  fork is describing a move narrower than the one that happened. If")
    print("  one variant is markedly lower, §3.2's choice of Modified Schiff is")
    print("  the thing to revisit, and that is a VARIANT question with no")
    print("  parameter attached — which is why it is safe to ask now.")
    print("  COVERAGE is median, not mean: the mean was 10.1% against a median")
    print("  of 5.3%, and half the symbols carried a fork under 5% of the time.")
    print("  DEATH CAUSE separates 'the tape broke it' (structural) from 'the")
    print("  N=2 / D=0.25 priors are strangling it' (adverse tine). Those have")
    print("  OPPOSITE responses and the split is per variant here for the first")
    print("  time.")
    print("\n  THIS DECIDES NO DEFAULT. A variant exceeded less often describes")
    print("  the move better — a necessary property, never a profitable one. No")
    print("  prior moves off this table; PF.3's condor-credit head-to-head is")
    print("  still the only thing that can convict a consumer.")
    return 0


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tape-root", default="")
    ap.add_argument("--symbols", default="")
    ap.add_argument("--variant-sweep", action="store_true",
                    help="§12 open question 2: run the lifecycle on ALL THREE "
                         "variants over the same tape and compare births, "
                         "median coverage, ACCELERATION per birth, death causes "
                         "and lifetimes. Changes no prior and ships no default.")
    ap.add_argument("--uniqueness-scan", action="store_true",
                    help="§4.3.5 second reading: scan back for the most recent "
                         "triple SATISFYING the filters (pitchfork v1.2). Run "
                         "the audit BOTH ways on the same tape and compare "
                         "MEDIAN coverage, not the birth rate.")
    a = ap.parse_args(argv[1:])

    # §4.3.5 head-to-head flag, captured HERE and not read later: `a` is the
    # parsed namespace but is REBOUND to an ATR list inside the symbol loop
    # below, so any `a.<attr>` after that point is a list attribute lookup.
    scan = a.uniqueness_scan
    sweep = a.variant_sweep
    root = _tape_root(a.tape_root)
    if not root:
        print("No tape root found (looked in " + ", ".join(TAPE_ROOTS) + ")")
        return 2
    syms = ([s.strip().upper() for s in a.symbols.split(",") if s.strip()]
            or _symbols(root))
    if not syms:
        print(f"No symbols found under {root}")
        return 2

    print(f"tape {root} | {len(syms)} symbol(s)\n")

    if sweep:
        return _variant_sweep(root, syms, scan)

    totals = collections.Counter()
    built = 0
    attempts = 0
    bars_by_sym = {}

    for sym in syms:
        h1 = _hourly(root, sym)
        if h1 is None or len(h1) < 20:
            bars_by_sym[sym] = 0 if h1 is None else len(h1)
            continue
        bars_by_sym[sym] = len(h1)
        for idx in range(20, len(h1)):
            sub = h1.iloc[:idx + 1]
            atr = float(atr_series(sub, 14).iloc[-1]) if len(sub) > 15 else 0.0
            attempts += 1
            f = build_fork(sym, sub, "1h", atr,
                           uniqueness_scan=scan)
            if f is not None:
                built += 1
                totals["__BUILT__"] += 1
            else:
                totals[last_reject_reason() or "UNKNOWN"] += 1

    # ── coverage, via the lifecycle (v1.2) ──────────────────────────────────
    cov_by_sym = {}
    life_events = collections.Counter()
    death_cause = collections.Counter()
    lifetimes = []
    for sym in syms:
        h1 = _hourly(root, sym)
        if h1 is None or len(h1) < 25:
            continue
        a = atr_series(h1, 14).tolist()
        tr = replay(sym, h1, "1h", a,
                    uniqueness_scan=scan)
        cov_by_sym[sym] = tr.coverage(len(h1))
        for ev in tr.events:
            life_events[ev.kind] += 1
        # cause-of-death and lifetime, the two things v1.2 could not say
        born_at = None
        for ev in tr.events:
            if ev.kind == "BORN":
                born_at = ev.idx
            elif ev.kind == "INVALIDATED":
                r = ev.reason
                cause = ("structural (P0)" if "structural" in r
                         else "adverse tine" if "adverse" in r
                         else "stale" if "stale" in r else r[:28])
                death_cause[cause] += 1
                if born_at is not None:
                    lifetimes.append(ev.idx - born_at)
                    born_at = None

    bars = list(bars_by_sym.values())
    print(f"hourly bars per symbol: min {min(bars)}  median "
          f"{sorted(bars)[len(bars)//2]}  max {max(bars)}")
    print(f"build attempts {attempts}   forks built {built} "
          f"({100.0*built/max(attempts,1):.1f}%)\n")
    if cov_by_sym:
        covs = sorted(cov_by_sym.values())
        mean_cov = sum(covs) / len(covs)
        print(f"COVERAGE (lifecycle held-fork bars / total bars), {len(covs)} symbols")
        print(f"  mean {mean_cov:.1%}   min {covs[0]:.1%}   "
              f"median {covs[len(covs)//2]:.1%}   max {covs[-1]:.1%}")
        print(f"  lifecycle events: {dict(life_events)}")
        birth_rate = built / max(attempts, 1)
        if death_cause:
            tot = sum(death_cause.values())
            print("  CAUSE OF DEATH")
            for c, n in death_cause.most_common():
                print(f"    {n:>4}  {100.0*n/tot:5.1f}%  {c}")
            print("    -> mostly ADVERSE TINE means the N/D priors are strangling "
                  "a persistent\n       object and are worth revisiting. Mostly "
                  "STRUCTURAL (P0) means the tape\n       genuinely broke the fork "
                  "and the priors are fine.")
        if lifetimes:
            lt = sorted(lifetimes)
            print(f"  LIFETIME in bars, n={len(lt)}: min {lt[0]}  "
                  f"p50 {lt[len(lt)//2]}  p90 {lt[min(len(lt)-1,int(len(lt)*0.9))]}  "
                  f"max {lt[-1]}")
            print("    -> a p50 under ~20 hourly bars (~3 sessions) is NOT "
                  "persistent behaviour;\n       §5.2 expects a daily fork to "
                  "survive weeks.")
        print(f"  vs BIRTH rate {birth_rate:.1%} — these are NOT the same number, "
              f"and treating\n  the birth rate as coverage is what made the fork "
              f"look starved (AS).\n")

    print("REJECTIONS, most common first")
    for reason, n in totals.most_common():
        if reason == "__BUILT__":
            continue
        print(f"  {n:>7}  {100.0*n/max(attempts,1):5.1f}%  {reason}")

    # ── the verdict this file exists to give ────────────────────────────────
    # v1.1 — THREE bins. STRUCTURAL is neither a length problem nor a tight
    # parameter: it means the last three pivots are not a directional structure,
    # which is a correct rejection of chop and has no threshold behind it.
    # Binning it with SEPARATION/SIGNIFICANCE (as v1.0 did) manufactures a
    # "filter tightness" verdict out of the engine working properly.
    length_side = sum(totals[r] for r in
                      ("FRAME_TOO_SHORT", "FEWER_THAN_3_ALTERNATING_PIVOTS",
                       "NO_ATR"))
    no_structure = sum(totals[r] for r in totals if r.startswith("STRUCTURAL"))
    filter_side = sum(totals[r] for r in totals
                      if r.startswith(("SIGNIFICANCE", "SEPARATION", "RECENCY")))
    print(f"\n  binned:  no qualifying structure {length_side + no_structure}"
          f"   parameter-sensitive {filter_side}   built {built}")
    print("\n" + "=" * 60)
    if attempts == 0:
        print("VERDICT  REFUSED — no build attempts.")
    elif built and 100.0 * built / attempts > 20:
        print(f"VERDICT  NEITHER — forks build {100.0*built/attempts:.0f}% of the "
              f"time. a2_rail_drift's\n         starvation is elsewhere: check the "
              f"hidx>=20 warmup cut and the\n         is_born_by() gate in that "
              f"tool, not these filters.")
    elif (length_side + no_structure) > filter_side:
        print(f"VERDICT  NO QUALIFYING STRUCTURE ({length_side + no_structure} vs "
              f"{filter_side}). Most rejections are\n         the engine correctly "
              f"refusing chop, not a threshold turning work away.\n         Do NOT "
              f"loosen the §4.3 priors to force forks.")
    else:
        print(f"VERDICT  FILTER TIGHTNESS ({filter_side} vs {length_side}). Structure "
              f"EXISTS and the\n         §4.3 priors are rejecting it. Revisit them — "
              f"but pre-register the\n         change from these counts (§10: ten "
              f"parameters is a large overfitting\n         surface). The dominant "
              f"reason above names which prior to look at.")
    print("=" * 60)
    print("REMEMBER: the percentage above is the BIRTH rate, not COVERAGE. A fork")
    print("holds until invalidated (§5.2), so once lifecycle exists one birth")
    print("covers many bars. A low birth rate is expected for a persistent object.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
