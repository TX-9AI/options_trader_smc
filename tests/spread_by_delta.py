#!/usr/bin/env python3
"""
tests/spread_by_delta.py — v1.0 — 2026-08-12  (SPD.1)

WHAT UNDERLYING MOVE DOES EACH STRIKE NEED JUST TO COVER ITS OWN SPREAD?

This is the other half of the preclusion census. PRE.1 measures what the
UNDERLYING does; this measures whether the PREMIUM can capture it. Neither is
actionable alone — a move that is available but uncapturable is not an edge.

────────────────────────────────────────────────────────────────────────────
THE TRADE-OFF THIS EXISTS TO PRICE
────────────────────────────────────────────────────────────────────────────
The fleet buys at `target_delta p50 = 0.171` — deep OTM 0DTE, where relative
spreads are worst. Measured from the readiness staged picks: **5.7% of mid on
continuation, 10.8% on sweep.**

Moving UP the chain cuts relative spread — the same nickel market is 10% of a
$0.51 contract and 2.5% of a $2.00 one. **But it also cuts LEVERAGE**, because a
higher-delta contract costs more premium per unit of delta. Those pull in
opposite directions and the naive "just buy closer to the money" is not
obviously right. The quantity that settles it:

    leverage   = delta * S / premium      (premium %% move per 1%% underlying move)
    breakeven  = spread%% / leverage        (underlying %% move that just pays the
                                           round-trip spread and nothing else)

**BREAKEVEN IS THE NUMBER.** It is directly comparable against the PRE.1 census
output: PRE.1 says how often a move of size X was available, this says what X
has to be for a given strike to profit at all. A delta bucket whose breakeven
sits above the movement typically available is unusable however good the setup.

⚠️ THE MARK-LIMIT POLICY MATTERS AND IS NOT IGNORED. `limit_ladder` v1.2 posts
AT the mark rather than crossing, and paper books the mark — so the system does
NOT pay the full spread on a filled order. What it pays instead is NO-FILL RISK,
which rises with spread width. So treat `breakeven` as the pessimistic bound
(full round-trip cross) and `breakeven/2` as the optimistic one (one side only).
Both are printed. The truth is somewhere between and depends on fill rate, which
only the live week can measure.

⚠️ ALSO NOT PRICED HERE: gamma. A fast move grows delta and therefore leverage,
so a real trade's effective leverage exceeds the entry snapshot's. This tool is
CONSERVATIVE about high-gamma strikes for that reason, which is exactly the
deep-OTM bucket the fleet currently buys.

READ-ONLY. stdlib only. Reads the chain archive (written since 2026-07-23).
Touches no fleet, no live path, writes nothing.

USAGE (control)
    python3 tests/spread_by_delta.py --since 2026-07-23
    python3 tests/spread_by_delta.py --since 2026-08-01 --symbol QQQ
"""

import argparse
import collections
import datetime as dt
import glob
import gzip
import json
import os
import sys

CHAINS = os.path.expanduser("~/day_trader_pro/chain_snapshots")
BUCKETS = [(0.05, 0.15, "0.05-0.15"), (0.15, 0.25, "0.15-0.25  <- fleet"),
           (0.25, 0.35, "0.25-0.35"), (0.35, 0.45, "0.35-0.45"),
           (0.45, 0.60, "0.45-0.60"), (0.60, 0.85, "0.60-0.85")]


def pctile(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))] if v else None


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-07-23")
    ap.add_argument("--symbol", default="")
    ap.add_argument("--min-mark", type=float, default=0.05,
                    help="ignore contracts below this mark — a 1c-wide market on")
    a = ap.parse_args(argv[1:])

    dates = sorted(d for d in os.listdir(CHAINS)
                   if len(d) == 10 and d >= a.since) if os.path.isdir(CHAINS) else []
    if not dates:
        print(f"no chain snapshots at/after {a.since} under {CHAINS}")
        return 1

    # bucket -> lists
    spread = collections.defaultdict(list)
    lever = collections.defaultdict(list)
    brk = collections.defaultdict(list)
    marks = collections.defaultdict(list)
    by_hour = collections.defaultdict(lambda: collections.defaultdict(list))
    by_sym = collections.defaultdict(lambda: collections.defaultdict(list))
    snaps = rowsn = skipped = 0

    for date in dates:
        for path in sorted(glob.glob(os.path.join(CHAINS, date, "*.jsonl.gz"))):
            sym = os.path.basename(path).split(".")[0]
            if a.symbol and sym.upper() != a.symbol.upper():
                continue
            try:
                fh = gzip.open(path, "rt", encoding="utf-8")
            except Exception:                                  # noqa: BLE001
                continue
            with fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:                          # noqa: BLE001
                        continue
                    S = r.get("underlying")
                    if not S:
                        continue
                    snaps += 1
                    try:
                        hh = int(str(r.get("ts_et"))[11:13])
                    except Exception:                          # noqa: BLE001
                        hh = -1
                    for c in (r.get("contracts") or []):
                        try:
                            bid = float(c.get("bid") or 0)
                            ask = float(c.get("ask") or 0)
                            mark = float(c.get("mark") or 0)
                            d = abs(float(c.get("delta") or 0))
                        except Exception:                      # noqa: BLE001
                            continue
                        if mark < a.min_mark or ask <= 0 or bid < 0 or ask < bid:
                            skipped += 1
                            continue
                        if d <= 0.02 or d >= 0.98:
                            continue
                        sp = (ask - bid) / mark * 100.0
                        lv = d * float(S) / mark          # premium %% per 1%% underlying
                        if lv <= 0:
                            continue
                        rowsn += 1
                        for lo, hi, lab in BUCKETS:
                            if lo <= d < hi:
                                spread[lab].append(sp)
                                lever[lab].append(lv)
                                marks[lab].append(mark)
                                brk[lab].append(sp / lv)
                                if hh >= 0:
                                    by_hour[lab][hh].append(sp / lv)
                                by_sym[sym][lab].append(sp / lv)
                                break

    print("=" * 78)
    print(f"  SPREAD BY DELTA (SPD.1) — {len(dates)} session(s), {snaps:,} snapshots,"
          f" {rowsn:,} contract rows")
    if skipped:
        print(f"  {skipped:,} rows skipped (mark < {a.min_mark} or crossed quote)")
    print(f"  breakeven = spread%% / leverage = the UNDERLYING %% move that pays the")
    print(f"  round-trip spread and nothing else.")
    print("=" * 78)

    print(f"\n  {'delta bucket':22}{'n':>9}{'mark':>8}{'spread%':>9}"
          f"{'leverage':>10}{'BREAKEVEN':>11}{'half':>8}")
    for _lo, _hi, lab in BUCKETS:
        if not brk[lab]:
            continue
        b = pctile(brk[lab], .50)
        print(f"  {lab:22}{len(brk[lab]):>9,}{pctile(marks[lab],.5):>8.2f}"
              f"{pctile(spread[lab],.5):>8.1f}%{pctile(lever[lab],.5):>10.1f}"
              f"{b:>10.3f}%{b/2:>7.3f}%")
    print(f"    leverage = premium %% move per 1%% underlying move (delta*S/mark).")
    print(f"    BREAKEVEN is the pessimistic bound (full round-trip cross); `half`")
    print(f"    is one side only. The mark-limit policy means the truth is between,")
    print(f"    and the residual is NO-FILL RISK rather than price.")

    print(f"\n  ⚠️ CROSS-REFERENCE WITH PRE.1 — is that move actually available?")
    print(f"     PRE.1 (post-08-08, 20 bars) median available underlying move:")
    print(f"       09:00 0.57%   10:00 0.35%   11:00 0.24%   12:00 0.21%")
    print(f"       13:00 0.18%   14:00 0.18%   15:00 0.21%")
    print(f"     A bucket whose BREAKEVEN exceeds the hour's median move is")
    print(f"     unusable in that hour however good the setup is.")

    print(f"\n  BREAKEVEN BY HOUR (median) — spreads widen into the close")
    hrs = sorted({h for lab in by_hour for h in by_hour[lab]})
    if hrs:
        print(f"    {'delta bucket':22}" + "".join(f"{h:02d}:00".rjust(8) for h in hrs))
        for _lo, _hi, lab in BUCKETS:
            if lab not in by_hour:
                continue
            row = "".join(
                (f"{pctile(by_hour[lab][h],.5):>7.3f}%" if by_hour[lab].get(h)
                 else "      —") for h in hrs)
            print(f"    {lab:22}{row}")

    print(f"\n  BREAKEVEN BY SYMBOL at the fleet's current bucket (0.15-0.25)")
    key = "0.15-0.25  <- fleet"
    rowsx = [(s, pctile(v[key], .5), len(v[key]))
             for s, v in by_sym.items() if v.get(key)]
    for s, b, n in sorted(rowsx, key=lambda x: x[1])[:20]:
        print(f"    {s:8}{b:>9.3f}%   n={n:,}")
    print(f"    ⚠️ A symbol whose breakeven sits above its typical hourly move is")
    print(f"       structurally unprofitable at this delta — that is a SELECTION")
    print(f"       question, not a strike question.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
