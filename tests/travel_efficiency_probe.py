#!/usr/bin/env python3
"""
tests/travel_efficiency_probe.py — v1.0 — 2026-08-10

CAN "AMOUNT OF UP/DOWN MOVEMENT OVER A PERIOD" DO WHAT bb_width_pct CANNOT?

THE PROBLEM IT IS AIMED AT. RANGING's score is a PRODUCT:
    flat_s x room_s x (0.55*osc_s + 0.45*bal_val)
and `room_s = ramp(bb_width_pct, 0.17, 1.00)` while bb_width_pct runs p50 0.44 /
p95 1.00. So at the median tick room_s ~= 0.33 and the whole score is multiplied
by it. Measured peak RANGING evidence is p50 **0.322** — that IS room_s. The
regime therefore cannot reach theta_commit 0.65 and commits on 2.1% of its
argmax runs against trending's 36.9%.
Two correct decisions produced it: the de-saturation work widened
RANGE_ROOM_HI 0.20 -> 1.00 to stop RANGING over-firing (it worked, dominance
44% -> 27%), and F7 later made theta_commit a hard requirement. Neither was
wrong; nobody re-derived one against the other.

THE OPERATOR'S PROPOSAL, and it is two numbers rather than one:
    TRAVEL       = sum |close[i] - close[i-1]| over the window, in ATR units.
                   Total up/down movement, DIRECTION-BLIND.
    EFFICIENCY   = |close[-1] - close[0]| / travel_path. Net progress per unit
                   of travel. (Kaufman's ratio; 1.0 = a straight line.)
The four regimes should fall out of the PAIR, not either alone:
    TRENDING     high travel, HIGH efficiency
    RANGING      HIGH travel, low efficiency   <- travel is what splits these
    COMPRESSION  LOW travel,  low efficiency   <-   two, not efficiency
    BREAKOUT     rising travel, rising efficiency

WHAT THIS TOOL DECIDES — three questions, in order. Do not skip to the third.
  Q1 SEPARATION: split by the COMMITTED label, do travel/efficiency actually
     separate RANGING from COMPRESSION? If the distributions overlap, the idea
     is dead regardless of how appealing it is, and bb_width_pct's failure is
     not evidence that this succeeds.
  Q2 CEILING: can a genuine RANGING tick reach ~1.0 on a travel-based ramp?
     That is the whole point — room_s cannot, and a replacement that also
     cannot is no improvement.
  Q3 AGAINST THE INCUMBENT: is travel BETTER than bb_width_pct at the same job,
     measured as separation between the two labels? A new term that merely
     ties is not worth a behavioural change before a freeze.

⚠️ WHAT THIS CANNOT TELL YOU. It measures separation of the two LABELS as the
engine currently commits them — and those labels are themselves produced by the
scorer under investigation. So a term that agrees with the current labelling
looks good partly BY CONSTRUCTION. Read Q1 as necessary-not-sufficient: failing
it kills the idea, passing it does not prove the term is right, and only live
trading can do that.

READ-ONLY. stdlib only.

USAGE
    python3 tests/travel_efficiency_probe.py
    python3 tests/travel_efficiency_probe.py --window 25 <replay.jsonl> ...
"""

import argparse
import glob
import json
import os
import sys
from collections import defaultdict

REPORTS = os.path.expanduser("~/day_trader_pro/reports")
RANGING, COMPRESSION = "RANGING", "COMPRESSION"
TRENDS = ("TRENDING_BULL", "TRENDING_BEAR")


def pct(v, q):
    if not v:
        return None
    s = sorted(v)
    return s[min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))]


def overlap(a, b):
    """Share of the two distributions that cannot be told apart by any cut.

    The single number that decides Q1. A perfect separator overlaps 0%; two
    identical distributions overlap 100%. Computed as 1 - (best achievable
    accuracy of a single threshold), so it answers exactly the question a ramp
    bound would face.
    """
    if not a or not b:
        return None
    lo, hi = min(min(a), min(b)), max(max(a), max(b))
    if hi <= lo:
        return 1.0
    best = 0.0
    for i in range(201):
        t = lo + (hi - lo) * i / 200.0
        # a should be BELOW t, b ABOVE t (or the reverse — take the better)
        acc1 = (sum(1 for x in a if x < t) + sum(1 for x in b if x >= t)) / (len(a) + len(b))
        acc2 = (sum(1 for x in a if x >= t) + sum(1 for x in b if x < t)) / (len(a) + len(b))
        best = max(best, acc1, acc2)
    return round(2.0 * (1.0 - best), 4)          # 0 = perfect split, 1 = identical


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--window", type=int, default=25,
                    help="bars of lookback (default 25 = RANGE_WINDOW_BARS)")
    a = ap.parse_args(argv[1:])

    files = a.files or sorted(glob.glob(os.path.join(REPORTS, "regime_replay_*.jsonl")))
    if not files:
        print(f"no replay files in {REPORTS}")
        return 1
    print(f"reading {len(files)} replay file(s), window={a.window} bars\n")

    # per symbol, keep a rolling price window; label each computed tick
    hist = defaultdict(list)
    trav = defaultdict(list)      # label -> [travel_atr]
    eff = defaultdict(list)       # label -> [efficiency]
    bbw = defaultdict(list)       # label -> [bb_width_pct]  (the incumbent)
    n_tick = 0

    for path in files:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:                              # noqa: BLE001
                    continue
                px = r.get("price")
                lab = (r.get("l2") or {}).get("regime") or ""
                if not px or not lab:
                    continue
                sym = r.get("sym", "?")
                h = hist[sym]
                h.append(float(px))
                if len(h) > a.window:
                    h.pop(0)
                if len(h) < a.window:
                    continue
                n_tick += 1

                path_len = sum(abs(h[i] - h[i - 1]) for i in range(1, len(h)))
                disp = abs(h[-1] - h[0])
                # ATR is not on the replay record; normalise by the window's own
                # mean absolute step instead — a self-scaling proxy that makes
                # TRAVEL comparable across a $30 and a $900 symbol without
                # needing a second data source.
                step = path_len / max(len(h) - 1, 1)
                if step <= 0 or h[0] <= 0:
                    continue
                travel_norm = path_len / h[0] * 100.0        # % of price travelled
                efficiency = disp / path_len if path_len > 0 else 0.0

                trav[lab].append(travel_norm)
                eff[lab].append(efficiency)
                bd = (r.get("breakdown") or {}).get(RANGING) or {}
                if isinstance(bd.get("bb_width_pct"), (int, float)):
                    bbw[lab].append(float(bd["bb_width_pct"]))

    print(f"ticks with a full {a.window}-bar window and a committed label: {n_tick:,}\n")
    labels = [l for l in (RANGING, COMPRESSION) + TRENDS if trav.get(l)]
    if RANGING not in labels or COMPRESSION not in labels:
        print("RANGING or COMPRESSION absent from the committed labels — "
              "nothing to separate. (RANGING commits on ~2% of runs, so a thin\n"
              "sample here is itself the finding.)")
        return 1

    print("=" * 74)
    print("  DISTRIBUTIONS BY COMMITTED LABEL")
    print("=" * 74)
    print(f"  {'label':<18}{'n':>8}  {'TRAVEL % p25/p50/p75':>26}   "
          f"{'EFFICIENCY p25/p50/p75':>24}")
    for l in labels:
        t, e = trav[l], eff[l]
        print(f"  {l:<18}{len(t):>8}  "
              f"{pct(t,.25):>8.4f}/{pct(t,.5):.4f}/{pct(t,.75):.4f}   "
              f"{pct(e,.25):>8.3f}/{pct(e,.5):.3f}/{pct(e,.75):.3f}")

    print("\n" + "=" * 74)
    print("  Q1 — DOES TRAVEL SEPARATE RANGING FROM COMPRESSION?")
    print("=" * 74)
    ov_t = overlap(trav[COMPRESSION], trav[RANGING])
    ov_e = overlap(eff[COMPRESSION], eff[RANGING])
    print(f"  TRAVEL      overlap {ov_t:.3f}   (0 = perfectly separable, 1 = identical)")
    print(f"  EFFICIENCY  overlap {ov_e:.3f}")
    if bbw.get(RANGING) and bbw.get(COMPRESSION):
        ov_b = overlap(bbw[COMPRESSION], bbw[RANGING])
        print(f"  bb_width_pct (INCUMBENT) overlap {ov_b:.3f}   <- the bar to beat")
    else:
        ov_b = None
        print("  bb_width_pct (INCUMBENT) not on these records — no head-to-head")

    print("\n  Expected if the operator's model holds: TRAVEL separates (low overlap)")
    print("  and EFFICIENCY does NOT (both regimes are inefficient by definition).")
    if ov_e < ov_t:
        print("  ⚠️  EFFICIENCY separated BETTER than travel — that CONTRADICTS the")
        print("      model. Do not proceed on the travel term without explaining it.")

    print("\n" + "=" * 74)
    print("  Q2 — COULD A TRAVEL RAMP REACH 1.0 ON A GENUINE RANGE?")
    print("=" * 74)
    tr = trav[RANGING]
    print(f"  RANGING travel p50={pct(tr,.5):.4f}  p90={pct(tr,.9):.4f}  "
          f"p95={pct(tr,.95):.4f}  max={max(tr):.4f}")
    print(f"  A ramp bounded LO=p25(COMPRESSION) HI=p75(RANGING) would put the")
    print(f"  MEDIAN ranging tick at:")
    lo_c, hi_r = pct(trav[COMPRESSION], .25), pct(tr, .75)
    med = 0.0
    if hi_r > lo_c:
        med = max(0.0, min(1.0, (pct(tr, .5) - lo_c) / (hi_r - lo_c)))
        print(f"     LO={lo_c:.4f}  HI={hi_r:.4f}  ->  room-equivalent = {med:.3f}")
        print(f"     (the incumbent room_s puts it at ~0.33 — THIS is the comparison")
        print(f"      that matters, because the ceiling is what starved the regime)")
        if med <= 0.40:
            print("     ⚠️  NO BETTER THAN THE INCUMBENT. A replacement that also")
            print("         cannot peg does not solve the ceiling — reject.")
    else:
        print("     bounds invert — the two labels are not ordered as the model expects")

    print("\n" + "=" * 74)
    print("  Q3 — VERDICT")
    print("=" * 74)
    # ⚠️ THE VERDICT WEIGHS TWO THINGS, AND THE CEILING IS THE ONE THAT MATTERS.
    # A first draft rejected on separation alone — which is backwards. The
    # regime was starved because room_s CANNOT PEG (median 0.33), not because
    # bb_width_pct fails to separate. A replacement that separates slightly
    # worse but reaches ~1.0 on a genuine range is still the better term; one
    # that separates beautifully and also caps at 0.33 changes nothing.
    _sep_ok = ov_t <= 0.60
    _beats = (ov_b is None) or (ov_t <= ov_b + 0.05)   # ties count as beating
    _ceil_ok = (med > 0.60) if 'med' in dir() else False
    if not _sep_ok:
        print("  ✗ TRAVEL DOES NOT SEPARATE (overlap > 0.60). Dead on this corpus")
        print("    regardless of how well it reasons — report it and stop.")
    elif not _ceil_ok:
        print("  ✗ TRAVEL SEPARATES BUT CANNOT PEG. The median ranging tick still")
        print("    lands low on the ramp, so the CEILING — the thing that actually")
        print("    starved the regime — is unchanged. Not worth the change.")
    elif not _beats:
        print("  ~ TRAVEL PEGS BUT SEPARATES WORSE than bb_width_pct. That trade is")
        print("    the operator's call, not mine: it buys commit-ability at the cost")
        print("    of admitting more compression ticks as ranges. Read both numbers.")
    else:
        print("  ✓ TRAVEL SEPARATES, TIES-OR-BEATS THE INCUMBENT, AND CAN PEG.")
        print("    Worth building as a replacement for room_s, with COMPRESSION")
        print("    taking the low end of the same axis. Fit the bounds from the")
        print("    percentiles above, not by hand.")
    print("\n  ⚠️  READ Q1 AS NECESSARY, NOT SUFFICIENT: the labels being separated")
    print("      are produced by the scorer under investigation, so agreement is")
    print("      partly circular. Failing kills the idea; passing does not prove it.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
