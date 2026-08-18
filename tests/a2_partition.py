#!/usr/bin/env python3
"""
tests/a2_partition.py — v1.0 — 2026-08-01

WHICH OF THE THREE A2 STORIES IS TRUE — AND IT MAY BE MORE THAN ONE.

A2 asserts TRENDING and RANGING are never both > 0.5. It fails on 4.02% of
156,712 corpus ticks, 45% of them in the 10:00 hour. Three mechanisms produce
that same signature, and the time-of-day histogram CANNOT separate them:

  H1  HORIZON CO-TRUTH — TRENDING is ADX-14 on the 5m frame (a 70-minute
      statement); RANGING's discriminating term is the angle over 25 bars of 1m
      (a 25-minute statement). Both can be honestly true. Structural, present
      ALL DAY. If this is the whole story there is nothing to fix: the flag is
      naming a real state (a paused trend / flag / pennant) rather than an error.

  H2  OPENING DRIVE — a real opening impulse sits inside the 70-minute ADX window
      until ~10:40 while the 25-minute angle flattens minutes after it ends. This
      is H1 with a time-of-day density. GENUINE, not artifact.

  H3  GAP ARTIFACT — the session-boundary bar's directional movement perturbs
      ADX. The "impulse" happened overnight, not in the tape, so a pause flagged
      from it has nothing to resume. ARTIFACT.

H2 and H3 predict an identical morning concentration. What separates them is the
SIGN, measured by ablation 2026-08-01 (synthetic two-session fixture, real
trend_engine, only the boundary changed):

      zero gap                        ADX 46.4 @09:40 -> 16.3 @12:30
      gap WITH prior direction        ADX 52.0 @09:40 -> 17.8 @12:30  inflated
      gap COUNTER to prior direction  ADX 26.1 @09:40 -> 14.9 @12:30  SUPPRESSED

A reversal gap DEPRESSES ADX by ~20 points. H1 and H2 can only ADD violations —
neither can produce a rate BELOW the all-day baseline. So a deficit in the
OPEN x REV cell is H3's unique fingerprint and cannot be faked by the other two.

THE GRID THIS PRINTS, and how to read it:

                        CONT        FLAT        REV
      OPEN   09:30-10:40  .           .           .
      DECAY  10:40-12:00  .           .           .
      CLEAN  12:00-16:00  .           .           .

    CLEAN row non-zero and flat across columns  -> H1 confirmed (structural)
    OPEN/FLAT clearly above CLEAN/FLAT          -> H2 real (drive, no gap needed)
    OPEN/CONT > OPEN/FLAT and OPEN/REV < CLEAN  -> H3 confirmed (artifact)

    All three can light up at once. That is the expected outcome, not a muddle:
    H1 is the structure, H2 is when it happens, H3 is what contaminates it.

WHY THE CLEAN CELL IS THE ONE THAT MATTERS FOR TRADING
    CLEAN x FLAT is an uncontaminated sample of the state — gap effect fully
    decayed, no gap to begin with. That is where `paused_trend` (A2.5) should be
    evaluated for forward edge on its own merit. Only then is it worth measuring
    how much the morning artifact dilutes it. Hold open the outcome that the
    state is real, correctly identified, and still has no edge.

PREREQUISITES — both matter, results are meaningless without them
    1. tests/gap_backfill.py has been run (writes reports/gap_pct.json).
    2. The replay corpus was regenerated under replay_confluence >= v2.1. v2.1
       fixed the 1m window straddling the overnight gap, which changed exactly
       the opening-25-minute ticks this tool reads. A corpus built before it
       contains opening ticks the live engine could not have produced.

USAGE (single line, control box, repo root)
    python3 tests/a2_partition.py
    python3 tests/a2_partition.py --gaps ~/day_trader_pro/reports/gap_pct.json
    python3 tests/a2_partition.py --jsonl ~/day_trader_pro/reports/regime_replay_2026-07-30.jsonl

Read-only. Streams the corpus (files are ~23MB each; loading them all at once is
what made ramp_calibration die silently on 2026-07-30). Builds nothing, fixes
nothing, and is allowed to kill the planned fix.
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

DEFAULT_GLOBS = [
    "~/day_trader_pro/reports/regime_replay_*.jsonl",
    "~/day_trader_pro/data/harvest/*/regime_replay_*.jsonl",
]
DEFAULT_GAPS = "~/day_trader_pro/reports/gap_pct.json"

TREND_KEYS = ("TRENDING_BULL", "TRENDING_BEAR")
DATE_RE = re.compile(r"(20\d\d-\d\d-\d\d)")

# Time buckets. OPEN is the ADX-14-on-5m window measured from the open (70 min),
# which is exactly the span over which a boundary bar can still move ADX. CLEAN
# starts where the ablation showed the perturbation gone (deltas < 1.5 by 12:30).
BUCKETS = (("OPEN", "09:30", "10:40"),
           ("DECAY", "10:40", "12:00"),
           ("CLEAN", "12:00", "16:00"))
CLASSES = ("CONT", "FLAT", "REV")

# A cell below this is not read. a2_characterise v1.1's lesson: refuse a verdict
# when the discriminator did not run, rather than falling through to a weaker one.
MIN_CELL_N = 500


def time_bucket(ts: str):
    for name, lo, hi in BUCKETS:
        if lo <= ts < hi:
            return name
    return None


def wilson_halfwidth(k: int, n: int) -> float:
    """95% half-width on a rate, so cells are not read as different when they are
    one standard error apart. Normal approximation; no scipy dependency."""
    if n <= 0:
        return 0.0
    p = k / n
    return 1.96 * math.sqrt(max(p * (1 - p), 1e-12) / n)


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", default="", help="one file; default = auto-discover all")
    ap.add_argument("--gaps", default=DEFAULT_GAPS, help="gap_pct.json from gap_backfill.py")
    a = ap.parse_args(argv[1:])

    gaps_path = os.path.expanduser(a.gaps)
    if not os.path.isfile(gaps_path):
        print(f"No gap lookup at {gaps_path}")
        print("Run tests/gap_backfill.py first — this tool cannot partition without it.")
        return 2
    with open(gaps_path) as fh:
        gapdoc = json.load(fh)
    gaps = gapdoc.get("sessions", {})

    paths = ([a.jsonl] if a.jsonl else
             [p for g in DEFAULT_GLOBS for p in sorted(glob.glob(os.path.expanduser(g)))])
    paths = [p for p in paths if os.path.isfile(os.path.expanduser(p))]
    if not paths:
        print("No replay jsonl found. Looked in:")
        for g in DEFAULT_GLOBS:
            print(f"   {g}")
        return 2

    ticks = collections.Counter()      # (bucket, class) -> ticks
    viols = collections.Counter()      # (bucket, class) -> violations
    unmatched_dates, unmatched_syms = set(), set()
    n_total = n_joined = n_viol_total = 0
    adx_by_cell = collections.defaultdict(list)

    for path in paths:
        p = os.path.expanduser(path)
        m = DATE_RE.search(os.path.basename(p))
        if not m:
            continue
        date = m.group(1)
        day = gaps.get(date)
        if day is None:
            unmatched_dates.add(date)
        with open(p) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:                                # noqa: BLE001
                    continue
                n_total += 1
                sym = r.get("sym", "?")
                bucket = time_bucket(r.get("ts", ""))
                if bucket is None or day is None:
                    continue
                grec = day.get(sym)
                if grec is None:
                    unmatched_syms.add(f"{date}/{sym}")
                    continue
                klass = grec.get("gap_class")
                if klass not in CLASSES:
                    continue                                     # UNDIRECTED excluded

                sc = r.get("scores") or {}
                bd = r.get("breakdown") or {}
                trend = max((float(sc.get(k) or 0.0) for k in TREND_KEYS), default=0.0)
                rng = float(sc.get("RANGING") or 0.0)

                n_joined += 1
                cell = (bucket, klass)
                ticks[cell] += 1
                if trend > 0.5 and rng > 0.5:
                    viols[cell] += 1
                    n_viol_total += 1
                    # breakdown collapses TRENDING_BULL/BEAR into one "TRENDING"
                    # entry (regime_confluence.py:738) — v1.1 of a2_characterise
                    # got this wrong and printed a verdict anyway.
                    for k in ("TRENDING",) + TREND_KEYS:
                        v = (bd.get(k) or {}).get("adx")
                        if isinstance(v, (int, float)):
                            adx_by_cell[cell].append(float(v))
                            break

    if n_joined == 0:
        print("Nothing joined. The corpus dates did not match the gap lookup.")
        if unmatched_dates:
            print(f"  corpus dates with no gap record: {sorted(unmatched_dates)[:8]}")
        return 2

    print(f"corpus files      : {len(paths)}")
    print(f"ticks read        : {n_total}")
    print(f"ticks joined      : {n_joined}  ({100.0*n_joined/max(n_total,1):.1f}%)")
    print(f"violations joined : {n_viol_total}  ({100.0*n_viol_total/n_joined:.2f}% of joined)")
    print(f"flat band         : |gap_pct| < {gapdoc.get('flat_pct')}%   "
          f"prior direction over {gapdoc.get('prior_dir_minutes')} min")
    if unmatched_dates:
        print(f"dates unmatched   : {len(unmatched_dates)} (no gap record — excluded)")
    if unmatched_syms:
        print(f"symbol-days unmatched: {len(unmatched_syms)} (excluded)")

    print("\nA2 VIOLATION RATE (% of ticks in cell), +/- 95%")
    print(f"  {'':<7}" + "".join(f"{c:>22}" for c in CLASSES))
    rate = {}
    for bname, _, _ in BUCKETS:
        row = f"  {bname:<7}"
        for c in CLASSES:
            n = ticks[(bname, c)]
            k = viols[(bname, c)]
            if n == 0:
                row += f"{'—':>22}"
                continue
            r_ = 100.0 * k / n
            hw = 100.0 * wilson_halfwidth(k, n)
            rate[(bname, c)] = (r_, hw, n)
            flag = "" if n >= MIN_CELL_N else "*"
            row += f"{f'{r_:5.2f} ±{hw:4.2f} (n={n}){flag}':>22}"
        print(row)
    print(f"  * cell below n={MIN_CELL_N} — not read below.")

    print("\n  median ADX on violating ticks, by cell")
    for bname, _, _ in BUCKETS:
        row = f"  {bname:<7}"
        for c in CLASSES:
            vals = sorted(adx_by_cell[(bname, c)])
            row += f"{(f'{vals[len(vals)//2]:.1f}' if vals else '—'):>22}"
        print(row)

    # ── verdicts, each stated only when its cells have population ─────────────
    print("\n" + "=" * 62)
    print("VERDICTS — each is refused, not guessed, when its cells are thin")
    print("=" * 62)

    def cell(b, c):
        v = rate.get((b, c))
        return v if v and v[2] >= MIN_CELL_N else None

    clean_flat = cell("CLEAN", "FLAT")
    open_flat = cell("OPEN", "FLAT")
    open_cont = cell("OPEN", "CONT")
    open_rev = cell("OPEN", "REV")
    clean_cells = [cell("CLEAN", c) for c in CLASSES]
    clean_ok = [x for x in clean_cells if x]

    # H1 — structural, all day
    if not clean_ok:
        print("H1 HORIZON     REFUSED — the CLEAN row has no cell above the floor.")
    else:
        lo = min(x[0] - x[1] for x in clean_ok)
        spread = max(x[0] for x in clean_ok) - min(x[0] for x in clean_ok)
        widest = max(x[1] for x in clean_ok)
        if lo > 0.0:
            flatness = "flat across gap classes" if spread <= 2 * widest else \
                       f"NOT flat across gap classes (spread {spread:.2f} vs ±{widest:.2f})"
            print(f"H1 HORIZON     SUPPORTED — violations persist after the gap effect is "
                  f"gone\n               (CLEAN row all > 0), {flatness}.")
            if spread > 2 * widest:
                print("               A CLEAN row that varies BY GAP CLASS is unexpected under "
                      "H1 and\n               would mean the gap leaves a mark past midday — "
                      "investigate before\n               treating the CLEAN cell as clean.")
        else:
            print("H1 HORIZON     NOT SUPPORTED — no violations survive into the CLEAN row. "
                  "The\n               state is not structural; it is entirely a "
                  "morning phenomenon.")

    # H2 — drive, genuine morning density
    if not (open_flat and clean_flat):
        print("H2 DRIVE       REFUSED — need both OPEN/FLAT and CLEAN/FLAT above the floor.")
    elif open_flat[0] - open_flat[1] > clean_flat[0] + clean_flat[1]:
        print(f"H2 DRIVE       SUPPORTED — flat-open mornings still run hot "
              f"({open_flat[0]:.2f}% vs {clean_flat[0]:.2f}%).\n"
              f"               Morning excess exists with NO gap involved, so it is the "
              f"opening\n               drive, and it is GENUINE — not something to filter out.")
    else:
        print(f"H2 DRIVE       NOT SUPPORTED — flat-open mornings ({open_flat[0]:.2f}%) are "
              f"not above\n               midday ({clean_flat[0]:.2f}%). The morning "
              f"concentration needs a gap to appear.")

    # H3 — gap artifact. The deficit is the fingerprint.
    if not (open_cont and open_rev and open_flat and clean_flat):
        print("H3 GAP         REFUSED — need OPEN x {CONT,FLAT,REV} and CLEAN/FLAT above the floor.")
    else:
        inflated = open_cont[0] - open_cont[1] > open_flat[0] + open_flat[1]
        deficit = open_rev[0] + open_rev[1] < clean_flat[0] - clean_flat[1]
        if inflated and deficit:
            print(f"H3 GAP         CONFIRMED — continuation gaps inflate "
                  f"({open_cont[0]:.2f}% vs {open_flat[0]:.2f}% flat) AND\n"
                  f"               reversal gaps DEPRESS below the midday baseline "
                  f"({open_rev[0]:.2f}% vs {clean_flat[0]:.2f}%).\n"
                  f"               The deficit is the fingerprint no other hypothesis "
                  f"predicts. A share of\n               the morning flags are "
                  f"boundary-bar artifacts with no impulse to resume.")
        elif inflated and not deficit:
            print(f"H3 GAP         PARTIAL — continuation gaps inflate "
                  f"({open_cont[0]:.2f}% vs {open_flat[0]:.2f}%) but reversal gaps\n"
                  f"               show no deficit ({open_rev[0]:.2f}% vs "
                  f"{clean_flat[0]:.2f}% midday). Consistent with gap-days simply "
                  f"BEING\n               trend days — correlation, not the ADX "
                  f"perturbation. Weak evidence.")
        elif deficit and not inflated:
            print("H3 GAP         ANOMALOUS — the deficit is present but the inflation is not. "
                  "Unexpected;\n               do not read either as confirmation until "
                  "it is understood.")
        else:
            print(f"H3 GAP         NOT SUPPORTED — gap class does not move the morning rate "
                  f"(CONT {open_cont[0]:.2f}%,\n               FLAT {open_flat[0]:.2f}%, "
                  f"REV {open_rev[0]:.2f}%). The gap is not what is driving A2.")

    print("\nNEXT — regardless of which lit up: CLEAN x FLAT is the uncontaminated")
    print("sample. Evaluate paused_trend's forward edge THERE first, per strategy,")
    print("before letting any of this touch a gate.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
