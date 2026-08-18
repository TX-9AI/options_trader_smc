#!/usr/bin/env python3
"""
tests/factor_sweep.py — v1.1 — 2026-08-13

v1.1 — 2026-08-13 — TWO DEFECTS FOUND BY READING v1.0's OWN OUTPUT, plus the
        filter the handoff question needs.
        (a) **HOURS WERE UTC, LABELLED AS ET.** `entry_time` in trades.db is UTC
            ISO and v1.0 read `.hour` off it directly, so bands printed 13..17
            and `minutes_from_open` ran 245..509 for a 09:30 open. This is the
            EXACT mistake `excursion_report` documents and refuses to make —
            "entry_time is UTC and the tape is ET-offset... duplicating it
            half-done is how the 2026-07 verdict got inverted." Now converted
            with ZoneInfo, with a NAMED fallback rather than a silent one.
        (b) **`MONOTONE` FIRED ON TWO BANDS.** `derived.confluence_count` takes
            only the values 3 and 4 in the whole sample, and v1.0 called it
            "MONOTONE RISING". Across two bands monotonicity is trivially true
            whenever they differ — it is not evidence of a trend, it is
            arithmetic. A verdict now needs MIN_BANDS_FOR_MONOTONE; below that
            the cell reads TOO FEW BANDS, which is what the direct test of the
            project's premise actually returned: absent measurement, neither
            support nor refutation.
        (c) `--setup-type` — the handoff question. `trend_continuation_handoff`
            is 386 trades / 62%% of continuation volume at 52%% never-favorable
            against standalone's 33%%, and the handoff is the path where
            CONTINUATION_CONV_FLOOR deliberately steps aside. Filtering the
            sweep to one setup_type asks whether the handoff population differs
            in `reg.conviction` (the floor was skipped) or only in outcome (the
            post-runaway tape is simply bad). Those need opposite fixes.

WHAT ARE WE RECORDING AND NOT LEVERAGING?

Operator, 2026-08-13: *"Measure any variable worth checking for edge we are not
leveraging."*

`scorer_backtest` v1.1 answered "do the scorer's OWN dimensions separate?" —
answer, on continuation, no: every dimension sep 0.000, two of them constants.
That is a question about five numbers. The journal records roughly THIRTY per
signal, and the scorer looks at five of them. This tool tests the other
twenty-five against realised P&L.

The candidates that have never been scored on any strategy:
  · `rrr`                       proven to separate on ORB (win p50 4.16 vs lose
                                4.85 — NEGATIVELY, high advertised R:R loses)
  · `contract.spread_pct_of_mid` the per-trade version of SEL.1's 42x symbol
                                lever, recorded on the contract actually bought
  · `contract.delta/iv/theta/volume/oi`
  · `entry_premium`             finding #5 says ORB splits totally on premium
  · `vol.atr`, `vol.bb_width`   the per-signal proxy for "is a worthwhile move
                                available today" — the thing the 08-05 break
                                showed dominates everything
  · `macro.vix`
  · `hour`                      the hourly ratio matrix says this is large
  · `confluence_count`          THE THESIS TEST. The project's central claim is
                                that confluence means LATE. Every journal row
                                carries the confluence list. Counting it and
                                banding it tests that claim directly on 805
                                trades rather than by argument.

────────────────────────────────────────────────────────────────────────────
METHOD — deliberately not the one scorer_backtest uses
────────────────────────────────────────────────────────────────────────────
scorer_backtest compares WINNER MEDIAN vs LOSER MEDIAN. That test is blind to a
binary or sparse input: ORB's `pools_in_path` reads "flat" (both medians 0.000,
because 78% of the population is zero) while the grade built from it separates
+$56 vs -$25 per trade. A median test on a sparse column reports FLAT BY
CONSTRUCTION. So here:

  1. BAND, don't average. Quintiles by value (or one band per distinct value
     when there are six or fewer). Report n / win% / avg$ / net$ per band.
  2. MONOTONICITY IS THE VERDICT, NOT SPREAD. A U-shaped table with a high
     bottom band is the confluence failure, not separation. Only a strictly
     ordered table earns "MONOTONE".
  3. WINNERS-CAUGHT on every cut. The cheapest threshold catching zero winners
     is the only thing shippable as a hard cut; everything else is a size or
     ordering signal, not a gate.
  4. REFUSE BELOW THE FLOOR. A band under --min-n prints its n and no verdict.
     Absent measurement, not a null.

⚠️ THIS IS AN IN-SAMPLE SWEEP OVER ~25 FACTORS. At 25 factors, roughly one will
   look monotone at p<0.05 by chance alone. A result here is a CANDIDATE, not a
   finding. The disposition for anything that separates is a held-out
   re-derivation (the ANT.2 pattern), not a weight. Nothing here ships to a
   scorer profile on this output alone.

READ-ONLY. stdlib only. Imports the join from scorer_backtest — ONE JOIN, ONE
OWNER. Touches no fleet, no live path, writes nothing.

USAGE (control)
    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python tests/factor_sweep.py --since 2026-07-20
    ... --since 2026-07-20 --strategy ContinuationStrategy
    ... --since 2026-07-20 --bands 3 --min-n 20
"""

import argparse
import collections
import os
import sys

try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except Exception:                                              # noqa: BLE001
    _ET = None

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.scorer_backtest import load_scored, load_trades, JOIN_TOL_S, JOURNAL  # noqa: E402

MIN_N_DEFAULT = 12
# A two-band table cannot evidence a trend: with two cells, "monotone" is true
# whenever they differ at all. Three is the floor at which the word means
# something.
MIN_BANDS_FOR_MONOTONE = 3


# ── factor extraction ────────────────────────────────────────────────────────

def _num(v):
    """A number, or None. Booleans count as 0/1; strings never coerce."""
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    return None


def factors(raw, trade):
    """Every numeric candidate on one joined row, flattened to name -> value.

    Prefix tells you where it came from, so a result is traceable back to the
    field that produced it without grepping the journal.
    """
    out = {}
    sig = raw.get("signal") or {}
    reg = raw.get("regime") or {}
    vol = raw.get("vol") or {}
    mac = raw.get("macro") or {}
    con = sig.get("contract") or {}

    for src, prefix in ((sig, "sig."), (reg, "reg."), (vol, "vol."),
                        (mac, "macro."), (con, "contract.")):
        for k, v in src.items():
            n = _num(v)
            if n is not None:
                out[prefix + k] = n

    # ── derived ──────────────────────────────────────────────────────────────
    # THE THESIS TEST. `confluence` is a list of strings; its LENGTH is the
    # confluence count the whole premise rests on. If the count is flat or
    # inverted, "things agree only after the move is underway" stops being an
    # argument and becomes a measurement.
    conf = sig.get("confluence")
    if isinstance(conf, list):
        out["derived.confluence_count"] = float(len(conf))

    ts = trade.get("ts")
    if ts is not None:
        # v1.1 — `ts` comes from trades.db `entry_time`, which is UTC. Convert,
        # never assume. A NAMED fallback so a missing tzdata is visible in the
        # output rather than silently shifting every band by four hours.
        if _ET is not None:
            et = ts.astimezone(_ET)
            out["derived.hour_et"] = float(et.hour)
            out["derived.minutes_from_open"] = float(
                max(0, (et.hour - 9) * 60 + et.minute - 30))
        else:
            out["derived.hour_UTC_NO_TZDATA"] = float(ts.hour)

    # Premium-relative stop distance: how far the underlying has to travel
    # before the structural stop is hit, in ATR. Nothing scores this.
    e, st = _num(sig.get("underlying_entry")), _num(sig.get("underlying_stop"))
    atr = _num(vol.get("atr"))
    if e and st and atr and atr > 0:
        out["derived.stop_dist_atr"] = abs(e - st) / atr

    return out


# ── banding ──────────────────────────────────────────────────────────────────

def bands_for(values, nbands):
    """Cut points. Distinct values <= 6 become one band each; otherwise
    quantile edges. Returns a list of (label, lo, hi) with hi exclusive except
    on the last band."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return []
    distinct = sorted(set(vals))
    if len(distinct) <= 6:
        return [(f"={d:g}", d, d) for d in distinct]
    edges = []
    for i in range(1, nbands):
        edges.append(vals[int(round(i * (len(vals) - 1) / nbands))])
    edges = sorted(set(edges))
    out, lo = [], vals[0]
    for e in edges:
        if e > lo:
            out.append((f"{lo:.4g}..{e:.4g}", lo, e))
            lo = e
    out.append((f"{lo:.4g}..{vals[-1]:.4g}", lo, vals[-1]))
    return out


def assign(v, bands):
    for i, (_, lo, hi) in enumerate(bands):
        last = (i == len(bands) - 1)
        if lo == hi:
            if v == lo:
                return i
        elif (lo <= v <= hi) if last else (lo <= v < hi):
            return i
    return None


def monotone(seq):
    """+1 rising, -1 falling, 0 neither. Strict on the direction, tolerant of
    a repeat, because a tie is not a reversal."""
    ups = sum(1 for a, b in zip(seq, seq[1:]) if b > a)
    dns = sum(1 for a, b in zip(seq, seq[1:]) if b < a)
    if ups and not dns:
        return 1
    if dns and not ups:
        return -1
    return 0


# ── report ───────────────────────────────────────────────────────────────────

def sweep_strategy(strat, rows, nbands, min_n):
    print(f"\n{'=' * 78}")
    net = sum(r["pnl"] for r in rows)
    wins = sum(1 for r in rows if r["pnl"] > 0)
    print(f"  {strat}   n={len(rows)}  win {100.0 * wins / len(rows):.0f}%"
          f"  net ${net:+,.0f}")
    print("=" * 78)

    allf = collections.defaultdict(list)
    for r in rows:
        for k, v in r["factors"].items():
            allf[k].append((v, r["pnl"]))

    results = []
    for name in sorted(allf):
        pairs = allf[name]
        # Coverage: a factor present on a third of the population or less
        # cannot be swept on this sample. Say so; do not quietly drop it.
        cov = len(pairs) / float(len(rows))
        vals = [v for v, _ in pairs]
        if len(set(vals)) < 2:
            results.append((name, cov, "CONSTANT on this sample — "
                                       "no threshold can separate", None, 0))
            continue
        bands = bands_for(vals, nbands)
        if len(bands) < 2:
            continue
        cells = [[] for _ in bands]
        for v, pnl in pairs:
            i = assign(v, bands)
            if i is not None:
                cells[i].append(pnl)
        table = []
        for (label, _, _), c in zip(bands, cells):
            if not c:
                continue
            w = sum(1 for p in c if p > 0)
            table.append((label, len(c), 100.0 * w / len(c),
                          sum(c) / len(c), sum(c), w))
        if len(table) < 2:
            continue
        thin = [t for t in table if t[1] < min_n]
        avgs = [t[3] for t in table]
        m = monotone(avgs)
        gap = max(avgs) - min(avgs)
        if len(table) < MIN_BANDS_FOR_MONOTONE:
            verdict = (f"TOO FEW BANDS ({len(table)}) — this factor takes too "
                       f"few distinct values to evidence a trend. Absent "
                       f"measurement, not a null.")
        elif thin:
            verdict = (f"UNDERPOWERED — {len(thin)}/{len(table)} bands below "
                       f"n={min_n}. ABSENT MEASUREMENT, not a null.")
        elif m and gap > 0:
            verdict = (f"MONOTONE {'RISING' if m > 0 else 'FALLING'} — "
                       f"avg$ spans ${gap:,.0f}/trade across bands")
        elif gap > 0:
            verdict = (f"NON-MONOTONE — ${gap:,.0f}/trade band spread but not "
                       f"ordered. A U-shape is the confluence failure, "
                       f"not separation.")
        else:
            verdict = "flat"
        results.append((name, cov, verdict, table, abs(gap) if m else 0.0))

    results.sort(key=lambda r: -r[4])

    for name, cov, verdict, table, _ in results:
        cover = "" if cov > 0.99 else f"  [present on {100 * cov:.0f}% of rows]"
        print(f"\n  {name}{cover}")
        if table is None:
            print(f"    {verdict}")
            continue
        print(f"    {'band':24}{'n':>6}{'win%':>7}{'avg$':>9}{'net$':>10}"
              f"{'winners':>9}")
        for label, n, wr, avg, tot, w in table:
            print(f"    {label[:23]:24}{n:>6}{wr:>6.0f}%{avg:>9,.0f}"
                  f"{tot:>10,.0f}{w:>9}")
        print(f"    -> {verdict}")

    # ── the only shippable cut ───────────────────────────────────────────────
    print(f"\n  {'-' * 74}")
    print("  ZERO-WINNER BANDS — the only cuts shippable as a hard gate")
    found = False
    for name, _, _, table, _ in results:
        if not table:
            continue
        for label, n, wr, avg, tot, w in table:
            if w == 0 and n >= min_n:
                found = True
                print(f"    {name} {label}: n={n}, winners 0, "
                      f"net ${tot:,.0f} — cutting this band costs nothing "
                      f"and saves ${-tot:,.0f}")
    if not found:
        print(f"    none. No band of any factor caught zero winners at "
              f"n>={min_n}.")
        print(f"    Everything above is a SIZE or ORDERING signal, not a gate.")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="")
    ap.add_argument("--strategy", default="")
    ap.add_argument("--setup-type", default="",
                    help="restrict to one setup_type, e.g. "
                         "trend_continuation_handoff — the handoff question")
    ap.add_argument("--bands", type=int, default=5)
    ap.add_argument("--min-n", type=int, default=MIN_N_DEFAULT)
    a = ap.parse_args(argv[1:])

    if not a.since:
        print("usage: factor_sweep.py --since <YYYY-MM-DD>")
        return 0
    if not os.path.isdir(JOURNAL):
        print(f"no journal at {JOURNAL} — nothing to sweep")
        return 0

    dates = sorted(d for d in os.listdir(JOURNAL)
                   if len(d) == 10 and d >= a.since)

    joined, unmatched = [], 0
    for date in dates:
        sc = load_scored(date)
        tr = load_trades(date)
        idx = collections.defaultdict(list)
        for s in sc:
            idx[(s["sym"], s["strategy"])].append(s)
        for t in tr:
            cands = idx.get((t["sym"], t["strategy"])) or []
            best, bd = None, JOIN_TOL_S + 1
            for s in cands:
                d = abs((s["ts"] - t["ts"]).total_seconds())
                if d < bd:
                    best, bd = s, d
            if best is None or bd > JOIN_TOL_S:
                unmatched += 1
                continue
            joined.append({**t, "factors": factors(best.get("raw") or {}, t)})

    print("=" * 78)
    print(f"  FACTOR SWEEP — {len(dates)} session(s)")
    print(f"  trades joined {len(joined)}   UNMATCHED {unmatched}")
    if joined and unmatched > len(joined) * 0.25:
        print(f"  ⚠️⚠️ THE JOIN IS UNSOUND — do not believe anything below.")
    print("=" * 78)
    if not joined:
        print("\n  nothing joined; cannot proceed")
        return 0

    by = collections.defaultdict(list)
    for j in joined:
        if a.strategy and j["strategy"] != a.strategy:
            continue
        if a.setup_type and str(j.get("setup_type") or "") != a.setup_type:
            continue
        by[j["strategy"]].append(j)
    if a.setup_type:
        print(f"\n  FILTERED to setup_type == {a.setup_type!r}")

    for strat, rows in sorted(by.items(), key=lambda kv: -len(kv[1])):
        sweep_strategy(strat, rows, a.bands, a.min_n)

    print(f"\n{'=' * 78}")
    print("  ⚠️ IN-SAMPLE SWEEP OVER ~25 FACTORS. About one will look monotone")
    print("     by chance. Anything that separates here is a CANDIDATE for a")
    print("     held-out re-derivation (the ANT.2 pattern) — not a weight.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
