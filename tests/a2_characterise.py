#!/usr/bin/env python3
"""
tests/a2_characterise.py — v1.1 — 2026-08-01
v1.1 — TWO fixes, both found on the first real run against the corpus.
       (a) The breakdown key is "TRENDING"; `res.scores` uses TRENDING_BULL /
           TRENDING_BEAR but `res.breakdown` collapses them into one entry
           (regime_confluence.py:738). v1.0 looked up the score keys, found no
           adx at all, and STILL PRINTED A VERDICT — reaching "genuine
           co-occurrence" purely from the symbol-spread branch with zero adx
           evidence. Exactly the silent-degradation failure this tool exists to
           detect, committed inside the tool itself.
       (b) It now REFUSES a verdict when the discriminator did not run, instead
           of falling through to a weaker branch.
       Also promotes the hour histogram: a >=30% single-hour concentration is
       itself evidence for the lag story and is now called out.

WHAT ARE THE A2 VIOLATIONS, ACTUALLY?

A2 asserts TREND and RANGE are never both > 0.5. It fails on ~196 of 11,299
ticks (1.7%). This tool describes those ticks. **It builds nothing and fixes
nothing — and it exists specifically because it can KILL the planned fix.**

THE ROOT CAUSE IS ALREADY KNOWN (2026-08-01), which is why the question is
narrow:
    _breakout:     expand_val       = ramp(atr_ratio, LO, HI)
    _compression:  atr_contract_val = 1.0 - ramp(atr_ratio_c, LO, HI)
        -> ONE measurement, TWO ends. A3 passes with ZERO violations, by
           construction rather than by luck.

    _trending:     adx_s  = ramp(adx, adx_trend - 5, ADX_STRONG_SOLO)   <- ADX
    _ranging:      flat_s = ramp(CUT_DEG - angle, 0, SOFT_DEG)          <- ANGLE
        -> TWO unrelated measurements, nothing coupling them.

So a shared axis (A2.2) is the obvious fix. This tool asks whether it is the
RIGHT one, by separating three stories that all produce "both > 0.5":

  (1) ADX LAG — the move ended, angle already flattened, ADX-14 has not decayed.
      SIGNATURE: violators sit at HIGH adx and LOW angle, and adx is FALLING.
      IF THIS DOMINATES, a shared axis papers over a measurement problem. The
      right fix is an ADX freshness/decay term, and A2.2 should NOT be built as
      specified. Supporting evidence already collected: raising the replay's
      --warm-sessions 5 -> 15 made A2 WORSE (179 -> 196) while TRENDING dom% rose
      30% -> 36% — deeper history makes ADX more confidently high.

  (2) GENUINE CO-OCCURRENCE — a slow steady grind really is both directional and
      contained. SIGNATURE: violators spread across the adx/angle plane rather
      than clustering. A2.2 (shared axis, Kaufman Efficiency Ratio) is correct.

  (3) CROSS-HORIZON DISAGREEMENT — pitchfork white paper §7.3: the daily and
      hourly forks can legitimately slope in OPPOSITE directions, so some
      violators may be real structural disagreement rather than a scoring
      defect. **A single-axis reformulation would ERASE that signal rather than
      repair it.** Cannot be fully tested until PF.1 exists; this tool records
      the symbol/time clustering that would support it.

USAGE
    python3 tests/a2_characterise.py
    python3 tests/a2_characterise.py --jsonl ~/day_trader_pro/reports/regime_replay_2026-07-30.jsonl

Read-only. Streams the corpus (files are ~23MB each; loading them all at once is
what made ramp_calibration die silently on 2026-07-30).
"""

import argparse
import collections
import glob
import json
import os
import statistics
import sys

DEFAULT_GLOBS = [
    "~/day_trader_pro/reports/regime_replay_*.jsonl",
    "~/day_trader_pro/data/harvest/*/regime_replay_*.jsonl",
]
TREND_KEYS = ("TRENDING_BULL", "TRENDING_BEAR")


def pct(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    i = min(len(s) - 1, max(0, int(round((p / 100.0) * (len(s) - 1)))))
    return s[i]


def describe(name, vals):
    if not vals:
        return f"    {name:<10} (none)"
    return (f"    {name:<10} n={len(vals):<6} p10={pct(vals,10):>7.2f} "
            f"p50={pct(vals,50):>7.2f} p90={pct(vals,90):>7.2f} "
            f"mean={statistics.fmean(vals):>7.2f}")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", default="", help="one file; default = auto-discover all")
    a = ap.parse_args(argv[1:])

    paths = ([a.jsonl] if a.jsonl else
             [p for g in DEFAULT_GLOBS for p in sorted(glob.glob(os.path.expanduser(g)))])
    paths = [p for p in paths if os.path.isfile(os.path.expanduser(p))]
    if not paths:
        print("No replay jsonl found. Looked in:")
        for g in DEFAULT_GLOBS:
            print(f"   {g}")
        return 2

    viol_adx, viol_ang, ok_adx, ok_ang = [], [], [], []
    by_sym = collections.Counter()
    by_hour = collections.Counter()
    sym_total = collections.Counter()
    n_ticks = 0
    prev_adx = {}
    adx_falling = adx_rising = 0

    for path in paths:
        with open(os.path.expanduser(path)) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:                                # noqa: BLE001
                    continue
                n_ticks += 1
                sc = r.get("scores") or {}
                bd = r.get("breakdown") or {}
                sym = r.get("sym", "?")
                sym_total[sym] += 1

                trend = max((float(sc.get(k) or 0.0) for k in TREND_KEYS), default=0.0)
                rng = float(sc.get("RANGING") or 0.0)

                # adx lives on the TRENDING breakdown; angle on RANGING's
                # v1.1 — THE BREAKDOWN KEY IS "TRENDING", NOT TRENDING_BULL.
                # `res.scores` is keyed by TRENDING_BULL / TRENDING_BEAR but
                # `res.breakdown` collapses both into a single "TRENDING" entry
                # (regime_confluence.py:738). v1.0 looked up the SCORE keys in
                # the breakdown, found nothing, and printed a verdict with the
                # ADX evidence silently missing — the exact failure this tool
                # exists to prevent, committed on its first real run.
                adx = None
                for k in ("TRENDING",) + TREND_KEYS:
                    v = (bd.get(k) or {}).get("adx")
                    if isinstance(v, (int, float)):
                        adx = float(v)
                        break
                ang = (bd.get("RANGING") or {}).get("angle")
                ang = float(ang) if isinstance(ang, (int, float)) else None

                violating = trend > 0.5 and rng > 0.5
                if violating:
                    by_sym[sym] += 1
                    hh = str(r.get("ts", ""))[:2]
                    if hh.isdigit():
                        by_hour[hh] += 1
                    if adx is not None:
                        viol_adx.append(adx)
                        # DIRECTION of adx is the lag discriminator: a decaying
                        # adx on a violating tick is the post-move signature.
                        p = prev_adx.get(sym)
                        if p is not None:
                            if adx < p - 0.01:
                                adx_falling += 1
                            elif adx > p + 0.01:
                                adx_rising += 1
                    if ang is not None:
                        viol_ang.append(ang)
                else:
                    if adx is not None:
                        ok_adx.append(adx)
                    if ang is not None:
                        ok_ang.append(ang)
                if adx is not None:
                    prev_adx[sym] = adx

    nv = len(viol_adx) or len(viol_ang)
    print("=" * 78)
    print(f"  A2 CHARACTERISATION — {n_ticks:,} ticks, {len(paths)} session file(s)")
    print("=" * 78)
    if not nv:
        print("\n  NO A2 VIOLATIONS in this corpus. Either the corpus predates the")
        print("  condition or a fix has already landed — check before concluding.")
        return 0
    print(f"  violating ticks: {nv:,}  ({100.0*nv/max(1,n_ticks):.2f}%)")

    print("\n  ── ADX on violating vs non-violating ticks ──")
    print(describe("VIOLATING", viol_adx))
    print(describe("clean", ok_adx))
    print("\n  ── midline ANGLE (deg) on violating vs non-violating ──")
    print(describe("VIOLATING", viol_ang))
    print(describe("clean", ok_ang))

    print("\n  ── ADX DIRECTION on violating ticks (the lag discriminator) ──")
    tot = adx_falling + adx_rising
    if tot:
        print(f"    falling {adx_falling:>5} ({100.0*adx_falling/tot:.0f}%)   "
              f"rising {adx_rising:>5} ({100.0*adx_rising/tot:.0f}%)")
    else:
        print("    (insufficient consecutive ticks per symbol)")

    print("\n  ── concentration ──")
    top = by_sym.most_common(6)
    span = len(by_sym)
    print(f"    symbols with violations: {span}")
    for sym, n in top:
        share = 100.0 * n / max(1, sym_total[sym])
        print(f"      {sym:<7}{n:>5}  ({share:.1f}% of that symbol's ticks)")
    if by_hour:
        print("    by hour: " + "  ".join(
            f"{h}:{n}" for h, n in sorted(by_hour.items())))
        _pk_h, _pk_n = max(by_hour.items(), key=lambda kv: kv[1])
        _share = 100.0 * _pk_n / max(1, sum(by_hour.values()))
        if _share >= 30.0:
            print(f"    !! {_share:.0f}% of all violations fall in the {_pk_h}:00 "
                  f"hour alone.")
            print(f"       A single-hour concentration is itself evidence for the")
            print(f"       LAG story: the opening drive ends, the angle flattens,")
            print(f"       and ADX-14 has not yet decayed. Weigh this against the")
            print(f"       adx direction figure above, not instead of it.")

    # ── the verdict, stated as which fix the data supports ──────────────────
    print("\n" + "=" * 78)
    vm_adx = statistics.fmean(viol_adx) if viol_adx else 0.0
    cm_adx = statistics.fmean(ok_adx) if ok_adx else 0.0
    vm_ang = statistics.fmean(viol_ang) if viol_ang else 0.0
    cm_ang = statistics.fmean(ok_ang) if ok_ang else 0.0
    fall_share = (adx_falling / tot) if tot else 0.0

    # v1.1 — REFUSE a verdict when the discriminator did not run. v1.0 fell
    # through to the "spread across symbols" branch with zero ADX samples and
    # printed LEANS (2) as if it meant something.
    if not viol_adx or not ok_adx:
        print("  !! NO ADX SAMPLES — the lag discriminator did NOT run, so NO")
        print("     VERDICT is possible. The angle and concentration figures")
        print("     above are still valid; the trend/range call is not.")
        print("     Check the breakdown key names against regime_confluence.py")
        print("     before trusting anything below.")
        return 1

    print("  READ:")
    print(f"    violating ticks average adx {vm_adx:.1f} vs {cm_adx:.1f} clean, "
          f"angle {vm_ang:.1f}° vs {cm_ang:.1f}° clean")
    if fall_share >= 0.60 and vm_adx > cm_adx:
        print("\n  -> LEANS (1) ADX LAG. Violators carry HIGH adx that is mostly")
        print("     FALLING while the angle has flattened: the post-move")
        print("     signature. A shared axis (A2.2) would paper over a")
        print("     MEASUREMENT problem. Consider an adx freshness/decay term")
        print("     instead, and do NOT build A2.2 as specified.")
    elif span >= 10 and max(by_sym.values()) < 0.25 * nv:
        print("\n  -> LEANS (2) GENUINE CO-OCCURRENCE. Violations are spread")
        print("     across many symbols rather than clustering. A2.2's shared")
        print("     axis (Kaufman Efficiency Ratio) is the right fix.")
    else:
        print("\n  -> MIXED or CONCENTRATED. Check the per-symbol shares above:")
        print("     a few symbols carrying most violations points at (3)")
        print("     cross-horizon disagreement or a symbol-specific artefact,")
        print("     NEITHER of which a single-axis reformulation should erase.")
    print("\n  This tool cannot fully test hypothesis (3) — that needs PF.1")
    print("  (the fork geometry) to exist so daily-vs-hourly slope disagreement")
    print("  can be checked directly. See WHITEPAPER §13.5.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
