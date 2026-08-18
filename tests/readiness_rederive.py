#!/usr/bin/env python3
"""
tests/readiness_rederive.py — v1.0 — 2026-08-12  (ANT.2)

CAN A COMBINATION DERIVED FROM MEASURED SIGNS BEAT `r`?

ANT.1 established two things on 128,503 labelled readiness rows:

  1. **`r` DOES NOT PREDICT.** Its band tables are U-SHAPED with the LOWEST band
     winning — continuation 0.0-0.2 -> 0.340 (highest of any band), sweep
     0.0-0.2 -> 0.468 (more than double every other). That is the CONFLUENCE
     FAILURE inside the layer built to avoid it: readiness rises as evidence
     accumulates, and evidence accumulates AFTER the move begins.
  2. **INDIVIDUAL FACTORS DO SEPARATE — several of them NEGATIVELY.** Sweep:
     `appr_touches` −45%, `appr_val` −41%, `age_bars` −31%. Condor put:
     `room_val` +77%. Butterfly: `conv` +60%. And `conv` INVERTS BY STRATEGY
     (continuation −6% · sweep +25% · butterfly +60% · condor_call +39%), so a
     single global weighting for it cannot be right.

**⇒ THE HYPOTHESIS THIS TESTS: the factors carry signal and the COMBINATION
cancels it, because the weights assume every factor points the same way.**

────────────────────────────────────────────────────────────────────────────
THE METHOD, and the discipline that keeps it honest
────────────────────────────────────────────────────────────────────────────
For each strategy independently:
  - measure each factor's SIGN and MAGNITUDE against forward movement on a
    FIT half of the sessions,
  - build `r_new` = a sign-corrected, magnitude-weighted z-score combination,
  - and score BOTH `r` and `r_new` on a HELD-OUT half never used for fitting.

⚠️ **THE HOLD-OUT IS THE WHOLE POINT.** With 128,503 rows and a dozen factors it
is trivial to fit a combination that describes 2026 and predicts nothing. The
sessions are split by DATE (not by row) so an entire session is either fit or
held out — splitting by row would leak, because rows minutes apart on the same
symbol-day share almost all their information.

⚠️ **A WIN HERE IS NECESSARY, NOT SUFFICIENT.** This is still the DIRECTIONLESS
test: it asks whether the combination anticipates MOVEMENT, not direction. A
combination that cannot predict available movement cannot predict a directional
outcome — but one that can has only cleared the first bar.

⚠️ **AND IT CANNOT RESCUE A CONSTANT.** `mom_val` (continuation), `squeeze_val`
(butterfly), `is_sweep` and `fresh_val` (sweep), and the condor `ext_*` family
are CONSTANTS in the recorded data. A constant carries zero information at any
weight; fixing those means changing what they MEASURE, which is out of scope
here and is the larger piece of work.

READ-ONLY. stdlib only. Same journal + OHLC as ANT.1. No new collection.

USAGE (control)
    python3 tests/readiness_rederive.py --since 2026-07-20
    python3 tests/readiness_rederive.py --since 2026-07-20 --horizon 10
"""

import argparse
import collections
import csv
import datetime as dt
import glob
import json
import math
import os
import sys

DTP = os.path.expanduser("~/day_trader_pro")
JOURNAL = os.path.join(DTP, "signal_journal")
OHLC = os.path.join(DTP, "ohlc")


def pctile(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))] if v else None


def load_tape(sym, date):
    p = os.path.join(OHLC, date, f"{sym}_ohlc_{date}.csv")
    if not os.path.isfile(p):
        return None, None
    bars = []
    with open(p, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            t = r.get("timestamp") or r.get("time")
            try:
                d = dt.datetime.fromisoformat(t)
                bars.append((d.strftime("%H:%M"), float(r["high"]),
                             float(r["low"]), float(r["close"])))
            except Exception:                                  # noqa: BLE001
                continue
    if not bars:
        return None, None
    return bars, {t: i for i, (t, *_x) in enumerate(bars)}


def collect(dates, horizon):
    rows = []
    for date in dates:
        tapes = {}
        for path in sorted(glob.glob(os.path.join(JOURNAL, date, "*.jsonl"))):
            sym = os.path.basename(path).split(".")[0]
            if sym not in tapes:
                tapes[sym] = load_tape(sym, date)
            bars, imap = tapes[sym]
            if not bars:
                continue
            with open(path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"readiness"' not in line:
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:                          # noqa: BLE001
                        continue
                    if not str(r.get("event", "")).startswith("readiness"):
                        continue
                    rd = r.get("readiness")
                    if not isinstance(rd, dict):
                        rd = r
                    ts = str(r.get("ts_et") or "")[11:16]
                    if ts not in imap:
                        continue
                    i0 = imap[ts]
                    px = bars[i0][3]
                    w = bars[i0:i0 + horizon + 1]
                    if px <= 0 or len(w) < 2:
                        continue
                    hi = max(b[1] for b in w)
                    lo = min(b[2] for b in w)
                    rows.append({
                        "date": date, "strat": rd.get("strategy"),
                        "r": rd.get("r"),
                        "f": {k: v for k, v in (rd.get("factors") or {}).items()
                              if isinstance(v, (int, float))},
                        "y": max((hi - px) / px, (px - lo) / px) * 100.0,
                    })
    return rows


def band_table(rows, key):
    """p50 forward move across quintiles of `key`. Returns the ordered list."""
    vals = [(x[key], x["y"]) for x in rows if x.get(key) is not None]
    if len(vals) < 250:
        return None
    vs = sorted(v for v, _ in vals)
    cuts = [vs[int(len(vs) * q)] for q in (.2, .4, .6, .8)]
    out = []
    for i in range(5):
        lo = -9e18 if i == 0 else cuts[i - 1]
        hi = 9e18 if i == 4 else cuts[i]
        sub = [y for v, y in vals if lo <= v < hi]
        out.append(pctile(sub, .5) if len(sub) >= 40 else None)
    return out


def verdict(o):
    o = [x for x in o if x is not None]
    if len(o) < 3:
        return "—", 0.0
    lift = (max(o) - min(o)) / max(min(o), 1e-9) * 100
    rising = all(o[i + 1] >= o[i] * 0.98 for i in range(len(o) - 1))
    if rising and lift >= 25:
        return "PREDICTS — monotone rise", lift
    if o[0] >= max(o) * 0.98:
        return "U-SHAPED, lowest wins — does NOT predict", lift
    if o[-1] >= max(o) * 0.98 and lift >= 25:
        return "top highest, not monotone — weak", lift
    return "FLAT / NON-MONOTONE", lift


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-07-20")
    ap.add_argument("--horizon", type=int, default=10)
    a = ap.parse_args(argv[1:])

    dates = sorted(d for d in os.listdir(JOURNAL) if len(d) == 10 and d >= a.since)
    if len(dates) < 6:
        print(f"need >=6 sessions to split fit/holdout; found {len(dates)}")
        return 1
    # ⚠️ SPLIT BY DATE, NEVER BY ROW. Rows minutes apart on the same symbol-day
    # share almost all their information; a row split leaks the answer.
    fit_d = dates[::2]
    hold_d = [d for d in dates if d not in fit_d]

    rows = collect(dates, a.horizon)
    if not rows:
        print("no rows joined")
        return 1
    by = collections.defaultdict(list)
    for x in rows:
        if x["strat"]:
            by[x["strat"]].append(x)

    print("=" * 78)
    print(f"  READINESS RE-DERIVATION (ANT.2) — horizon {a.horizon} bars")
    print(f"  fit sessions {len(fit_d)}   HELD-OUT {len(hold_d)}   rows {len(rows):,}")
    print(f"  split by DATE so no session appears in both halves")
    print("=" * 78)

    for strat, g in sorted(by.items(), key=lambda kv: -len(kv[1])):
        fit = [x for x in g if x["date"] in fit_d]
        hold = [x for x in g if x["date"] in hold_d]
        if len(fit) < 500 or len(hold) < 500:
            continue
        names = sorted({k for x in fit for k in x["f"]})

        # ── FIT: measured sign + magnitude per factor ──────────────────────
        wts = {}
        for nm in names:
            vals = [(x["f"][nm], x["y"]) for x in fit if nm in x["f"]]
            if len(vals) < 250:
                continue
            vs = sorted(v for v, _ in vals)
            q1, q3 = vs[len(vs) // 4], vs[3 * len(vs) // 4]
            if q3 <= q1:
                continue                       # CONSTANT — carries no information
            lo = [y for v, y in vals if v <= q1]
            hi = [y for v, y in vals if v >= q3]
            if len(lo) < 60 or len(hi) < 60:
                continue
            mlo, mhi = pctile(lo, .5), pctile(hi, .5)
            lift = (mhi - mlo) / max(mlo, 1e-9)
            if abs(lift) < 0.10:
                continue                       # too weak to earn a weight
            mean = sum(v for v, _ in vals) / len(vals)
            var = sum((v - mean) ** 2 for v, _ in vals) / len(vals)
            sd = math.sqrt(var)
            if sd <= 0:
                continue
            wts[nm] = (lift, mean, sd)         # SIGN comes from the data

        if not wts:
            print(f"\n  {strat}: no factor cleared the weighting bar")
            continue

        def r_new(x):
            num = tot = 0.0
            for nm, (lift, mean, sd) in wts.items():
                v = x["f"].get(nm)
                if v is None:
                    continue
                z = (v - mean) / sd
                num += lift * z                # lift carries the SIGN
                tot += abs(lift)
            return num / tot if tot else None

        for x in hold:
            x["rn"] = r_new(x)

        t_r = band_table(hold, "r")
        t_n = band_table(hold, "rn")
        print(f"\n{'='*78}\n  {strat}   fit {len(fit):,} / HELD-OUT {len(hold):,}"
              f"   factors weighted {len(wts)}")
        print(f"    weights (sign from the data): " +
              ", ".join(f"{nm} {lift:+.2f}" for nm, (lift, _m, _s)
                        in sorted(wts.items(), key=lambda kv: -abs(kv[1][0]))))
        for lab, t in (("r      (shipped)", t_r), ("r_new  (re-derived)", t_n)):
            if not t:
                print(f"    {lab:22} — insufficient rows")
                continue
            v, lift = verdict(t)
            print(f"    {lab:22}" +
                  "".join(f"{(x if x is not None else 0):>8.3f}" for x in t) +
                  f"   {lift:>5.0f}%  {v}")
        print(f"    quintiles of the score, low -> high, p50 forward move.")

    print(f"\n  ── WHAT COUNTS AS A WIN ──")
    print(f"    `r_new` must be MONOTONE RISING on the HELD-OUT half where `r`")
    print(f"    is U-shaped. Anything less and the factors' signal does not")
    print(f"    survive recombination — which would mean the layer is not")
    print(f"    salvageable by re-weighting, and the constants and the")
    print(f"    measurement itself are the real problem.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
