#!/usr/bin/env python3
"""
tests/preclusion_census.py — v1.0 — 2026-08-12  (PRE.1)

WHAT DOES THIS TAPE STATE MAKE IMPOSSIBLE?

Operator, 2026-08-12: *"There are shared characteristics on every tape that
reliably preclude a set of possible outcomes. We can exploit that."*

────────────────────────────────────────────────────────────────────────────
WHY PRECLUSION AND NOT PREDICTION — this is the whole design decision
────────────────────────────────────────────────────────────────────────────
Predicting "a setup forms here" is a **~0.7% base-rate** problem: 1,116 scored
events against ~157,000 replay ticks. A classifier reaching 50% precision there
needs a **70x lift**, which is an extraordinary claim, not a modest one.

Preclusion inverts it into a HIGH-base-rate question with a falsifiable form:

    while condition X held, what is the LARGEST forward move EVER observed?

If that maximum never clears the threshold across thousands of ticks, X is a
preclusion — and refusing to trade into it is nearly free: you forfeit an
OPTION rather than realising a loss, and you cannot cut the tail because the
tail was not available. **ONE COUNTEREXAMPLE KILLS A PRECLUSION.** That is the
point: it is a claim that can be destroyed by a single row, which is what makes
it worth more than a probability.

⚠️ AND THE TAIL IS THE ONLY THING THAT MATTERS HERE. ORB is +$5,775 at a **43%**
win rate; the `>+50%` premium band alone is 28 trades / 100% win / **+$23,773**.
This book wins on MAGNITUDE. So the quantity to preclude is not "a loss" — it is
**the upper tail being unreachable**. Optimising win rate would cut the tail
that pays.

────────────────────────────────────────────────────────────────────────────
WHAT IT MEASURES
────────────────────────────────────────────────────────────────────────────
Every replay tick already carries the tape state (per-regime scores, the full
breakdown, L2 label + conviction + stale, price, ts). Forward excursion comes
from the 1m OHLC harvested alongside it. NO NEW COLLECTION IS REQUIRED — this
runs against 22 sessions already on disk, which is deliberate: the chain archive
sat unread for 20 days because collection was built before a question needed it.

For each candidate condition, for each horizon, the report gives:
    n            ticks where the condition held
    max fwd      the LARGEST favourable move observed  <- the preclusion test
    p99 / p95    how thin the top is
    share>=thr   how often the move cleared the threshold

⚠️ FORWARD MOVE IS MEASURED ON THE UNDERLYING, AS A PERCENTAGE, DIRECTIONLESS
(the larger of the up-move and the down-move). A 0DTE long is directional, but a
preclusion is a statement about whether ANY tradeable excursion was available.
Signing it would fold a directional call into a question that is not asking one.

⚠️ THE UNDERLYING IS NOT THE PREMIUM. A 0.3% underlying move on a 0.17-delta
0DTE contract is not a 0.3% premium move — gamma and theta both intervene, and
relative SPREAD (measured 5.7% continuation, **10.8% sweep**, at
`target_delta p50 = 0.171`) eats the difference. **A preclusion found here is
NECESSARY, NOT SUFFICIENT**: it says the underlying never moved enough, which
means the premium certainly did not. It cannot say the reverse.
    -> The delta/spread work is the OTHER half of this and is not in this tool.
       Underlying thresholds here should be read alongside the spread-by-delta
       measurement from the chain archive before any threshold is shipped.

READ-ONLY. stdlib only. Touches no fleet, no live path, writes nothing.

USAGE (control)
    python3 tests/preclusion_census.py --since 2026-07-20
    python3 tests/preclusion_census.py --since 2026-07-20 --thr 0.4 --horizons 10,20,30
"""

import argparse
import collections
import csv
import datetime as dt
import glob
import json
import os
import sys

DTP = os.path.expanduser("~/day_trader_pro")
REPORTS = os.path.join(DTP, "reports")
OHLC = os.path.join(DTP, "ohlc")


def pctile(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))] if v else None


def load_tape(sym, date):
    p = os.path.join(OHLC, date, f"{sym}_ohlc_{date}.csv")
    if not os.path.isfile(p):
        return None
    out = []
    with open(p, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            t = r.get("timestamp") or r.get("time")
            if not t:
                continue
            try:
                d = dt.datetime.fromisoformat(t)
                out.append((d.strftime("%H:%M"), float(r["high"]),
                            float(r["low"]), float(r["close"])))
            except Exception:                                  # noqa: BLE001
                continue
    return out or None


def conditions(rec):
    """Candidate tape states. Each yields (family, label).

    Deliberately COARSE and hand-named — a preclusion has to be statable in one
    sentence to be actionable, and a learned boundary is not falsifiable by one
    counterexample the way a named condition is.
    """
    out = []
    sc = rec.get("scores") or {}
    l2 = rec.get("l2") or {}
    lab = l2.get("regime") or "NONE"
    conv = l2.get("c")
    out.append(("L2 label", lab))
    if l2.get("stale"):
        out.append(("L2 book", "STALE"))
    if conv is not None:
        for lo, hi, name in ((0, .25, "conv <0.25"), (.25, .5, "conv .25-.50"),
                             (.5, .75, "conv .50-.75"), (.75, 1.01, "conv >=0.75")):
            if lo <= conv < hi:
                out.append(("L2 conviction", name))
    live = {k: v for k, v in sc.items() if isinstance(v, (int, float)) and v > 0}
    out.append(("L1 breadth", f"{len(live)} regime(s) scoring >0"))
    if not live:
        out.append(("L1 breadth", "ALL-ZERO tick"))
    top = max(live.values()) if live else 0.0
    for lo, hi, name in ((0, .001, "top score = 0"), (.001, .3, "top <0.30"),
                         (.3, .6, "top .30-.60"), (.6, 1.01, "top >=0.60")):
        if lo <= top < hi:
            out.append(("L1 peak", name))
    hh = int(rec.get("ts", "00:00")[:2])
    out.append(("hour ET", f"{hh:02d}:00"))
    bd = (rec.get("breakdown") or {})
    for reg in ("TRENDING_BULL", "TRENDING_BEAR", "RANGING", "COMPRESSION"):
        b = bd.get(reg)
        if isinstance(b, dict):
            for k in ("bb_width_pct", "atr_normalized"):
                v = b.get(k)
                if isinstance(v, (int, float)):
                    out.append((k, "low" if v < 0.25 else
                                ("mid" if v < 0.60 else "high")))
                    break
            break
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="")
    ap.add_argument("--thr", type=float, default=0.40,
                    help="underlying %% move that counts as a tradeable excursion")
    ap.add_argument("--horizons", default="10,20,30")
    ap.add_argument("--min-n", type=int, default=200)
    a = ap.parse_args(argv[1:])
    hs = [int(x) for x in a.horizons.split(",") if x.strip()]

    files = sorted(glob.glob(os.path.join(REPORTS, "regime_replay_*.jsonl")))
    if a.since:
        files = [f for f in files
                 if os.path.basename(f)[14:24] >= a.since]
    if not files:
        print(f"no replay corpora under {REPORTS}")
        return 1

    # family -> label -> horizon -> list of forward %% moves
    agg = collections.defaultdict(
        lambda: collections.defaultdict(lambda: collections.defaultdict(list)))
    ticks = skipped = 0

    for path in files:
        date = os.path.basename(path)[14:24]
        tapes, idx = {}, {}
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:                                  # noqa: BLE001
                continue
            sym, ts = rec.get("sym"), rec.get("ts")
            px = rec.get("price")
            if not sym or not ts or not px:
                continue
            if sym not in tapes:
                tapes[sym] = load_tape(sym, date)
                if tapes[sym]:
                    idx[sym] = {t: i for i, (t, *_r) in enumerate(tapes[sym])}
            bars, imap = tapes.get(sym), idx.get(sym)
            if not bars or ts not in (imap or {}):
                skipped += 1
                continue
            i0 = imap[ts]
            ticks += 1
            conds = conditions(rec)
            for h in hs:
                w = bars[i0:i0 + h + 1]
                if len(w) < 2:
                    continue
                hi = max(b[1] for b in w)
                lo = min(b[2] for b in w)
                # DIRECTIONLESS: the larger of the two excursions. A preclusion
                # asks whether ANY move was available, not which way.
                mv = max((hi - px) / px, (px - lo) / px) * 100.0
                for fam, lab in conds:
                    agg[fam][lab][h].append(mv)

    print("=" * 78)
    print(f"  PRECLUSION CENSUS (PRE.1) — {len(files)} session(s), {ticks:,} ticks"
          f"   threshold {a.thr}% underlying")
    if skipped:
        print(f"  ⚠️ {skipped:,} ticks skipped — no tape bar at that timestamp")
    print(f"  A condition whose MAX forward move never clears the threshold is a")
    print(f"  PRECLUSION. One counterexample kills it.")
    print("=" * 78)

    for fam in sorted(agg):
        print(f"\n  ── {fam} ──")
        print(f"    {'condition':26}{'h':>4}{'n':>8}{'MAX':>8}{'p99':>8}"
              f"{'p95':>8}{'p50':>7}{'>=thr':>8}")
        for lab in sorted(agg[fam]):
            for h in hs:
                v = agg[fam][lab][h]
                if len(v) < a.min_n:
                    continue
                mx = max(v)
                share = 100.0 * sum(1 for x in v if x >= a.thr) / len(v)
                flag = "  <-- PRECLUDES" if mx < a.thr else ""
                print(f"    {lab[:25]:26}{h:>4}{len(v):>8,}{mx:>8.2f}"
                      f"{pctile(v,.99):>8.2f}{pctile(v,.95):>8.2f}"
                      f"{pctile(v,.50):>7.2f}{share:>7.1f}%{flag}")
    print(f"\n  ⚠️ MAX is the column that matters. p99 being low is a TENDENCY;")
    print(f"     MAX being below the threshold is a PRECLUSION. Only the second")
    print(f"     one is safe to trade on, and only until a counterexample lands.")
    print(f"  ⚠️ NECESSARY, NOT SUFFICIENT: this is the UNDERLYING. Premium also")
    print(f"     pays gamma, theta and a relative spread measured at 5.7%-10.8%")
    print(f"     at target_delta 0.171. Pair any threshold here with the")
    print(f"     spread-by-delta read from the chain archive before shipping it.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
