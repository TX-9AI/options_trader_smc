#!/usr/bin/env python3
"""
tests/shadow_summary.py — v1.0 — 2026-08-07

WHAT IS ACTUALLY IN THE SHADOW OBSERVER'S 282,350 RECORDS.

The observer has run fleet-wide since 2026-07-22 and NOTHING HAS EVER READ IT.
It was pulled off the boxes for the first time on 2026-08-07 (harvest.py has no
shadow class, so every file had been sitting on its own box's EBS volume). This
answers the only question worth asking first: is it a DATASET or is it volume?

⚠️ THE HEADLINE IS THE FILL RATE, NOT THE RECORD COUNT. A primitive that is
null on most ticks is not evidence, however many rows carry the key. The first
line of any session has `velocity`, `roc_*` and `intrabar_pos` null BY
CONSTRUCTION — there is no prior tick — so a naive `head -1` says nothing about
whether they ever populate. This measures every record.

WHY THE NAMED-LEVEL BLOCK MATTERS MOST RIGHT NOW: SWP.1 (2026-08-07) gates the
sweep trade on a score whose three HARD VETOES are "a NAMED level was swept, and
rejected, and not accepted beyond". The observer has been recording, every 15
seconds for 13 sessions, exactly how far price sat from the nearest named level
in both percent and ATR — independently, scoring nothing and trading nothing.
That is the distribution underneath the gate we just shipped.

⚠️ TWO CAVEATS THE OUTPUT REPEATS, because they decide what may be concluded:
  1. COVERAGE IS WILDLY UNEVEN. GS has zero sessions; SMCI has ELEVEN LINES;
     DIA/GLD/IWM/TLT have exactly one 1,560-line session each — which is one
     clean RTH day at 15s and then nothing, the ORIGINAL 07-22 failure
     signature. This is not a balanced panel and must not be pooled as one.
  2. EVERY LABEL HERE CAME FROM THE PRE-RGM.3 SIX-REGIME ENGINE. Sweep left the
     argmax on 2026-08-07. Pooling these `regime` values with post-Monday data
     repeats the basis error already flagged for the per-regime statistics.

Streams one file at a time — 238 MB will not be held in memory. Three earlier
tools in this repo died of load-everything-then-filter; this one does not.
Read-only, stdlib only, always exits 0.

USAGE
    python3 tests/shadow_summary.py
    python3 tests/shadow_summary.py --root ~/day_trader_pro/shadow
"""

import argparse
import collections
import glob
import json
import os
import sys

ROOT = "~/day_trader_pro/shadow"
PRIMS = ("roc_raw", "roc_typical", "velocity", "velocity_prev", "atr",
         "atr_normalized", "forming_range_atr", "bb_width_pct",
         "vwap_dist_pct", "intrabar_pos")


def _pct(sv, p):
    return 0.0 if not sv else sv[min(len(sv) - 1,
                                     int(round(p / 100.0 * (len(sv) - 1))))]


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=ROOT)
    a = ap.parse_args(argv[1:])

    files = sorted(glob.glob(os.path.join(os.path.expanduser(a.root),
                                          "*", "shadow", "*", "*.jsonl")))
    if not files:
        print(f"no shadow files under {a.root}")
        return 0

    n = 0
    per_sym = collections.Counter()
    per_date = collections.Counter()
    fill = collections.Counter()
    reg = collections.Counter()
    conv = []
    pvb = collections.Counter()
    expanding = collections.Counter()
    lvl_name = collections.Counter()
    dist_atr, dist_pct = [], []
    stages = collections.Counter()
    scored = 0

    for f in files:
        for line in open(f, errors="ignore"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:                                    # noqa: BLE001
                continue
            n += 1
            per_sym[r.get("symbol", "?")] += 1
            per_date[str(r.get("ts", ""))[:10]] += 1
            stages[r.get("stage")] += 1
            reg[r.get("regime") or "?"] += 1
            if r.get("regime_conviction") is not None:
                conv.append(float(r["regime_conviction"]))
            if r.get("scores"):
                scored += 1
            p = r.get("primitives") or {}
            for k in PRIMS:
                if p.get(k) is not None:
                    fill[k] += 1
            if p.get("price_vs_bb"):
                pvb[p["price_vs_bb"]] += 1
            expanding[bool(p.get("is_expanding"))] += 1
            for side in ("nearest_named_above", "nearest_named_below"):
                nl = p.get(side)
                if isinstance(nl, dict) and nl.get("name"):
                    lvl_name[nl["name"]] += 1
                    if nl.get("dist_atr") is not None:
                        dist_atr.append(float(nl["dist_atr"]))
                    if nl.get("dist_pct") is not None:
                        dist_pct.append(float(nl["dist_pct"]))

    print(f"records: {n:,}   files: {len(files)}   symbols: {len(per_sym)}   "
          f"dates: {len(per_date)}")
    print(f"stage: {dict(stages)}   records carrying a SCORE: {scored} "
          f"(stage 1 scores nothing — a non-zero here would be a surprise)")

    print("\n=== FILL RATE PER PRIMITIVE — the headline ===")
    print("  a primitive null on most ticks is not evidence, however many rows")
    print("  carry the key.")
    for k in PRIMS:
        pcnt = 100.0 * fill[k] / max(1, n)
        flag = "  <- MOSTLY NULL" if pcnt < 50 else ""
        print(f"  {k:<22}{fill[k]:>9,}{pcnt:>8.1f}%{flag}")

    print("\n=== COVERAGE — NOT a balanced panel ===")
    for sym, c in sorted(per_sym.items(), key=lambda kv: -kv[1]):
        sess = round(c / 1560.0, 1)
        flag = "  <- THIN" if c < 5000 else ""
        print(f"  {sym:<8}{c:>9,} records  ~{sess:>5} sessions{flag}")

    print("\n=== REGIME AT THE TICK (PRE-RGM.3 SIX-REGIME ENGINE) ===")
    for k, c in reg.most_common():
        print(f"  {k:<20}{c:>9,}{100.0*c/max(1,n):>8.1f}%")
    conv.sort()
    if conv:
        print(f"  conviction  p10={_pct(conv,10):.3f}  p50={_pct(conv,50):.3f}"
              f"  p90={_pct(conv,90):.3f}")

    print("\n=== NAMED LEVELS — the distribution under SWP.1's hard vetoes ===")
    for k, c in lvl_name.most_common(12):
        print(f"  {k:<20}{c:>9,}{100.0*c/max(1,sum(lvl_name.values())):>8.1f}%")
    dist_atr.sort()
    dist_pct.sort()
    if dist_atr:
        print(f"  dist_atr  p10={_pct(dist_atr,10):.2f}  p25={_pct(dist_atr,25):.2f}"
              f"  p50={_pct(dist_atr,50):.2f}  p75={_pct(dist_atr,75):.2f}"
              f"  p90={_pct(dist_atr,90):.2f}")
        print(f"  dist_pct  p10={_pct(dist_pct,10):.4f}  p50={_pct(dist_pct,50):.4f}"
              f"  p90={_pct(dist_pct,90):.4f}")
        near = sum(1 for d in dist_atr if d <= 0.5)
        print(f"  within 0.5 ATR of a named level: {near:,} of {len(dist_atr):,}"
              f" = {100.0*near/len(dist_atr):.1f}% of level observations")

    print("\n=== BOLLINGER / EXPANSION ===")
    for k, c in pvb.most_common():
        print(f"  price_vs_bb {k:<14}{c:>9,}{100.0*c/max(1,n):>8.1f}%")
    print(f"  is_expanding True {expanding[True]:>9,}"
          f"{100.0*expanding[True]/max(1,n):>8.1f}%")

    print("\n  ⚠️ COVERAGE IS UNEVEN — do not pool these boxes as one panel.")
    print("  ⚠️ EVERY `regime` HERE IS FROM THE PRE-RGM.3 SIX-REGIME ENGINE.")
    print("  Sweep left the argmax on 2026-08-07; pooling with post-Monday data")
    print("  repeats the basis error already flagged for per-regime statistics.")
    return 0


if __name__ == "__main__":
    try:
        rc = main(sys.argv)
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        rc = 0
    sys.exit(rc)
