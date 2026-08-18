#!/usr/bin/env python3
"""
tests/pitchfork_outcome.py — v1.0 — 2026-08-12  (PF.3)

DOES POSITION IN THE PITCHFORK CHANNEL PREDICT FORWARD MOVEMENT?

PF.2 has been journaling `pos_pct` since the 2026-08-12 wake — where price sits
between the tines, 0% on the lower and 100% on the upper. `pitchfork_digest`
v1.0 DESCRIBES that population (13 daily forks / 7 symbols, 41 hourly / 13
symbols; daily p50 74.2%, hourly p50 28.6%; 2.8% and 7.6% of observations
OUTSIDE a tine). **It has never been joined to an outcome.** That is the same
gap `r` had before ANT.1 — a well-populated score with nothing attached to it.

This applies ANT.1's machinery to the fork: bucket `pos_pct` and measure the
forward move of the underlying from the harvested tape.

────────────────────────────────────────────────────────────────────────────
WHAT WOULD COUNT AS THE RAILS MEANING SOMETHING
────────────────────────────────────────────────────────────────────────────
The white paper's §5.2 claim is that TAGGING A RAIL is the tradeable event — not
that price inside the channel drifts. So the shape to look for is a **U**: more
forward movement near BOTH tines (0-20% and 80-100%) than mid-channel (40-60%).
That is the opposite of the shape ANT.1 looked for, and it is deliberate — a
monotone rise in `pos_pct` would just mean "higher in the channel means more
movement", which is a trend statement, not a rail statement.

⚠️ AND THE OUTSIDE BUCKET IS THE SHARPEST TEST. Price beyond a tine is a TOUCH
or a BREAK. §5.3 says breaking the trend-side tine is ACCELERATION, not
invalidation. If the `outside` bucket shows the largest forward move, that is
the overlay's core claim surviving its first contact with an outcome.

⚠️ UNDERPOWERED BY CONSTRUCTION AND THAT IS NOT A FLAW TO HIDE. PF.2 went live
on the 2026-08-12 wake, so **one session** exists. Daily forks built on only 7
of 15 boxes. Treat every table here as a SHAPE to check on Friday, not a result.
The tool prints n per bucket so a thin cell is visible rather than averaged in.

⚠️ ROWS ARE NOT FORKS. The observer rebuilds on a 5-minute cadence but journals
EVERY tick, so one fork contributes ~20 near-identical rows. The effective
sample is far smaller than the row count, and rows within one fork are not
independent. **A confident-looking n here is mostly repetition.**

⚠️ DIRECTIONLESS, matching ANT.1 and PRE.1: the larger of the up-move and the
down-move. A fork is directional, so this is the WEAK test — availability, not
direction. Failure here is conclusive; success is necessary and not sufficient.

READ-ONLY. stdlib only. Reads the signal journal + harvested OHLC.
Touches no fleet, no live path, writes nothing.

USAGE (control)
    python3 tests/pitchfork_outcome.py --since 2026-08-12
    python3 tests/pitchfork_outcome.py --since 2026-08-12 --tf 1d
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
JOURNAL = os.path.join(DTP, "signal_journal")
OHLC = os.path.join(DTP, "ohlc")
MARKS = (5, 10, 20)


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


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-08-12")
    ap.add_argument("--tf", default="")
    a = ap.parse_args(argv[1:])

    dates = sorted(d for d in os.listdir(JOURNAL) if len(d) == 10 and d >= a.since)
    if not dates:
        print(f"no journal folders at/after {a.since}")
        return 1

    rows = []
    forks = collections.defaultdict(set)
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
                    if '"pitchfork"' not in line:
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:                          # noqa: BLE001
                        continue
                    p = r.get("pitchfork")
                    if not isinstance(p, dict):
                        continue
                    ts = str(r.get("ts_et") or "")[11:16]
                    if ts not in imap:
                        continue
                    i0 = imap[ts]
                    px = bars[i0][3]
                    if px <= 0:
                        continue
                    fwd = {}
                    for m in MARKS:
                        w = bars[i0:i0 + m + 1]
                        if len(w) < 2:
                            continue
                        hi = max(b[1] for b in w)
                        lo = min(b[2] for b in w)
                        fwd[m] = max((hi - px) / px, (px - lo) / px) * 100.0
                    if not fwd:
                        continue
                    for tf in ("1d", "1h"):
                        if a.tf and tf != a.tf:
                            continue
                        e = p.get(tf)
                        if not isinstance(e, dict):
                            continue
                        pos = e.get("pos_pct")
                        if pos is None:
                            continue
                        span = [t for t in (e.get("span") or ())
                                if str(t).startswith("SPAN_")]
                        forks[tf].add((date, sym, span[0] if span else "?"))
                        rows.append({"tf": tf, "sym": sym, "date": date,
                                     "pos": float(pos), "fwd": fwd,
                                     "dir": e.get("dir"),
                                     "dist": e.get("dist_ml_atr")})

    if not rows:
        print("no pitchfork rows joined to tape — PF.2 may not have been live")
        return 1

    print("=" * 78)
    print(f"  PITCHFORK OUTCOME (PF.3) — {len(dates)} session(s),"
          f" {len(rows):,} joined rows")
    for tf in sorted(forks):
        print(f"    {tf}: {len(forks[tf])} DISTINCT forks"
              f"   ({sum(1 for x in rows if x['tf']==tf):,} rows)")
    print(f"  ⚠️ rows are ~20x the fork count (journals every tick, rebuilds every")
    print(f"     5 min) and rows within one fork are NOT independent. The")
    print(f"     effective sample is the FORK count, not the row count.")
    print("=" * 78)

    bands = [(-1e9, 0, "OUTSIDE below"), (0, 20, "0-20  lower tine"),
             (20, 40, "20-40"), (40, 60, "40-60  mid"),
             (60, 80, "60-80"), (80, 100, "80-100  upper tine"),
             (100, 1e9, "OUTSIDE above")]
    for tf in sorted({x["tf"] for x in rows}):
        g = [x for x in rows if x["tf"] == tf]
        print(f"\n  ── {tf} — forward move by POSITION IN CHANNEL ──")
        print(f"    {'band':22}{'n':>8}{'forks':>7}" +
              "".join(f"{'p50@'+str(m):>10}" for m in MARKS))
        cells = {}
        for lo, hi, lab in bands:
            sub = [x for x in g if lo <= x["pos"] < hi]
            if not sub:
                continue
            nf = len({(x["date"], x["sym"]) for x in sub})
            vals = [pctile([x["fwd"][m] for x in sub if m in x["fwd"]], .5)
                    for m in MARKS]
            cells[lab] = vals[1] if len(vals) > 1 else None
            flag = "  <- thin" if nf < 3 else ""
            print(f"    {lab:22}{len(sub):>8,}{nf:>7}" +
                  "".join(f"{(v if v is not None else 0):>10.3f}" for v in vals)
                  + flag)
        mid = cells.get("40-60  mid")
        tines = [cells.get("0-20  lower tine"), cells.get("80-100  upper tine")]
        tines = [t for t in tines if t is not None]
        out = [cells.get("OUTSIDE below"), cells.get("OUTSIDE above")]
        out = [t for t in out if t is not None]
        print(f"\n    ⇒ §5.2 predicts a U: MORE movement near the TINES than mid.")
        if mid and tines:
            best = max(tines)
            if best > mid * 1.25:
                print(f"      TINE {best:.3f} vs MID {mid:.3f} — the U IS PRESENT"
                      f" ({(best/mid-1)*100:.0f}% more)")
            elif best < mid * 0.8:
                print(f"      TINE {best:.3f} vs MID {mid:.3f} — INVERTED: more"
                      f" movement MID-channel. The rails are not the event.")
            else:
                print(f"      TINE {best:.3f} vs MID {mid:.3f} — FLAT. No rail"
                      f" effect at this sample.")
        if out and mid:
            print(f"      OUTSIDE {max(out):.3f} vs MID {mid:.3f} — §5.3's"
                  f" ACCELERATION claim {'HOLDS' if max(out) > mid*1.25 else 'does NOT show'}")
        print(f"    ⚠️ read the FORKS column, not n. Fewer than ~3 forks in a band")
        print(f"       is one or two objects repeated, not a measurement.")

    print(f"\n  ── HONEST SCOPE ──")
    print(f"    PF.2 went live on the 2026-08-12 wake. With one session this is a")
    print(f"    SHAPE to re-check on Friday, not a result. The Fri 2026-08-14")
    print(f"    evaluation already carries PF.2's delete criterion; this is the")
    print(f"    other half of it — the digest says forks BUILD, this says whether")
    print(f"    they MEAN anything.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
