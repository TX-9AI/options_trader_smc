#!/usr/bin/env python3
"""
tests/symbol_edge.py — v1.0 — 2026-08-12  (SEL.1)

HOW MANY TIMES ITS OWN BREAKEVEN DOES THIS SYMBOL TYPICALLY MOVE?

This is the synthesis of PRE.1 and SPD.1, and it exists because NEITHER IS
ACTIONABLE ALONE:

  SPD.1 says CVX needs a **0.254%** underlying move just to pay its own spread,
        against SPX's **0.006%** — a 42x range.
  PRE.1 says the median available move is **0.57%** at 09:00 and **0.18%** at
        13:00 (post-08-08, 20 bars).

But those hourly figures are FLEET-WIDE medians, and a symbol with a wide spread
may simply be a symbol that moves a lot — in which case the two cancel and the
expensive name is fine. **That cancellation is the thing this tool tests.** The
only number that decides tradeability is the RATIO, per symbol, per hour:

    edge ratio = (median available move for THAT symbol, that hour)
                 ---------------------------------------------------
                 (breakeven for THAT symbol at its traded delta)

  ratio  < 1   the typical move does not even pay the spread. Structurally
               unprofitable, however good the setup. A SELECTION verdict.
  ratio ~ 1-2  marginal: only the upper tail of moves pays anything.
  ratio  > 3   the spread is a rounding error and setup quality decides.

⚠️ WHY THIS IS A SELECTION TOOL AND NOT A STRIKE TOOL. SPD.1 measured the delta
curve as nearly FLAT and U-shaped: 0.05-0.15 breakeven 0.186%, the fleet's
0.15-0.25 bucket 0.136%, the optimum 0.25-0.35 at 0.127%, then rising again to
0.230% deep ITM. Moving to the optimal bucket buys **7%**. Spread and leverage
very nearly cancel across the chain, so "buy closer to the money" is worth
almost nothing — while the SYMBOL axis spans **42x**. The lever is which boxes
wake, not which strike they buy.

⚠️ BOUNDS, both stated so a ratio near 1 is not over-read:
  - Breakeven is the PESSIMISTIC bound (full round-trip cross). `limit_ladder`
    posts AT the mark, so the real cost is somewhere between that and half of
    it, with the residual being NO-FILL RISK rather than price. A ratio computed
    on the pessimistic bound is therefore CONSERVATIVE — halve the breakeven and
    the ratio doubles.
  - Available move is DIRECTIONLESS (the larger of up and down). A 0DTE long is
    directional, so availability is necessary and not sufficient.

READ-ONLY. stdlib only. Reads the chain archive + replay corpora + OHLC already
on disk. Touches no fleet, no live path, writes nothing.

USAGE (control)
    python3 tests/symbol_edge.py --since 2026-08-08
    python3 tests/symbol_edge.py --since 2026-07-23 --horizon 20
"""

import argparse
import collections
import csv
import datetime as dt
import glob
import gzip
import json
import os
import sys

DTP = os.path.expanduser("~/day_trader_pro")
CHAINS = os.path.join(DTP, "chain_snapshots")
REPORTS = os.path.join(DTP, "reports")
OHLC = os.path.join(DTP, "ohlc")
DELTA_LO, DELTA_HI = 0.15, 0.25          # the bucket the fleet actually trades


def pctile(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))] if v else None


def breakeven_by_symbol(dates, min_mark):
    """SPD.1's core, restricted to the traded delta bucket."""
    out = collections.defaultdict(list)
    for date in dates:
        for path in sorted(glob.glob(os.path.join(CHAINS, date, "*.jsonl.gz"))):
            sym = os.path.basename(path).split(".")[0]
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
                    for c in (r.get("contracts") or []):
                        try:
                            bid = float(c.get("bid") or 0)
                            ask = float(c.get("ask") or 0)
                            mark = float(c.get("mark") or 0)
                            d = abs(float(c.get("delta") or 0))
                        except Exception:                      # noqa: BLE001
                            continue
                        if mark < min_mark or ask <= bid or bid < 0:
                            continue
                        if not (DELTA_LO <= d < DELTA_HI):
                            continue
                        lv = d * float(S) / mark
                        if lv > 0:
                            out[sym].append((ask - bid) / mark * 100.0 / lv)
    return {s: pctile(v, .5) for s, v in out.items() if v}


def move_by_symbol_hour(dates, horizon):
    """PRE.1's core, kept PER SYMBOL instead of pooled."""
    out = collections.defaultdict(lambda: collections.defaultdict(list))
    for date in dates:
        p = os.path.join(REPORTS, f"regime_replay_{date}.jsonl")
        if not os.path.isfile(p):
            continue
        tapes, idx = {}, {}
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:                                  # noqa: BLE001
                continue
            sym, ts, px = rec.get("sym"), rec.get("ts"), rec.get("price")
            if not sym or not ts or not px:
                continue
            if sym not in tapes:
                bars = []
                fp = os.path.join(OHLC, date, f"{sym}_ohlc_{date}.csv")
                if os.path.isfile(fp):
                    with open(fp, encoding="utf-8") as fh:
                        for r in csv.DictReader(fh):
                            t = r.get("timestamp") or r.get("time")
                            try:
                                d = dt.datetime.fromisoformat(t)
                                bars.append((d.strftime("%H:%M"), float(r["high"]),
                                             float(r["low"])))
                            except Exception:                  # noqa: BLE001
                                continue
                tapes[sym] = bars
                idx[sym] = {t: i for i, (t, *_r) in enumerate(bars)}
            bars, imap = tapes[sym], idx[sym]
            if ts not in imap:
                continue
            i0 = imap[ts]
            w = bars[i0:i0 + horizon + 1]
            if len(w) < 2:
                continue
            hi = max(b[1] for b in w)
            lo = min(b[2] for b in w)
            mv = max((hi - px) / px, (px - lo) / px) * 100.0
            out[sym][int(ts[:2])].append(mv)
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-08-08")
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--min-mark", type=float, default=0.05)
    ap.add_argument("--pay-mult", type=float, default=3.0,
                    help="a move is PAYABLE at this multiple of breakeven")
    a = ap.parse_args(argv[1:])

    dates = sorted(d for d in os.listdir(REPORTS)
                   if d.startswith("regime_replay_")
                   and d[14:24] >= a.since)
    dates = [d[14:24] for d in dates]
    if not dates:
        print(f"no replay corpora at/after {a.since}")
        return 1

    be = breakeven_by_symbol(dates, a.min_mark)
    mv = move_by_symbol_hour(dates, a.horizon)
    if not be:
        print("no chain rows in the traded delta bucket — cannot compute breakeven")
        return 1

    hours = sorted({h for s in mv for h in mv[s]})
    print("=" * 78)
    print(f"  SYMBOL EDGE (SEL.1) — {len(dates)} session(s), horizon {a.horizon} bars")
    print(f"  delta bucket {DELTA_LO}-{DELTA_HI} (what the fleet actually trades)")
    print(f"  ratio = median available move / breakeven.  <1 means the typical")
    print(f"  move does not pay the spread.")
    print("=" * 78)

    rows = []
    for sym in sorted(set(be) & set(mv)):
        allmv = [x for h in mv[sym] for x in mv[sym][h]]
        if len(allmv) < 200 or not be[sym]:
            continue
        rows.append((pctile(allmv, .5) / be[sym], sym, be[sym],
                     pctile(allmv, .5), len(allmv)))
    if not rows:
        print("\n  no symbol had both a breakeven and >=200 measured ticks")
        return 1

    print(f"\n  {'SYM':8}{'breakeven':>11}{'med move':>10}{'RATIO':>8}{'n':>9}   verdict")
    for ratio, sym, b, m, n in sorted(rows, reverse=True):
        v = ("spread irrelevant" if ratio >= 3 else
             ("marginal — only the tail pays" if ratio >= 1 else
              "UNPROFITABLE — move < spread"))
        print(f"  {sym:8}{b:>10.3f}%{m:>9.3f}%{ratio:>8.1f}{n:>9,}   {v}")

    # ── TAIL-AWARE VIEW ────────────────────────────────────────────────────
    # ⚠️ THE MEDIAN RATIO IS NOT THE WHOLE STORY, AND COST IS THE PROOF: ratio
    # 0.6 (median move BELOW breakeven) yet **+$1,985** on two long-hold ORB
    # trades. This book is fat-tailed — the `>+50%` premium band is 28 trades,
    # 100% win, **+$23,773** — so what matters is not whether the TYPICAL move
    # pays but HOW OFTEN A PAYABLE MOVE IS ON OFFER. A symbol whose median is
    # hopeless but whose tail is alive is a SIZING and FREQUENCY question, not a
    # ban. A symbol with neither is a ban.
    print(f"\n  TAIL VIEW — how often is a PAYABLE move on offer?")
    print(f"    payable = available move >= {a.pay_mult:.0f}x breakeven")
    print(f"    {'SYM':8}{'p50 ratio':>11}{'p90 ratio':>11}{'p99 ratio':>11}"
          f"{'payable%':>10}   verdict")
    for ratio, sym, b, m, n in sorted(rows, reverse=True):
        allmv = [x for h in mv[sym] for x in mv[sym][h]]
        r90 = pctile(allmv, .90) / b
        r99 = pctile(allmv, .99) / b
        pay = 100.0 * sum(1 for x in allmv if x >= a.pay_mult * b) / len(allmv)
        if ratio >= a.pay_mult:
            v = "trade it"
        elif pay >= 10.0:
            v = "TAIL ONLY — size down, do not ban"
        elif r99 >= a.pay_mult:
            v = "tail is thin — rare, real"
        else:
            v = "NO PAYABLE TAIL — ban candidate"
        print(f"    {sym:8}{ratio:>11.1f}{r90:>11.1f}{r99:>11.1f}"
              f"{pay:>9.1f}%   {v}")
    print(f"    ⚠️ 'payable%' is the honest selection statistic: a symbol offering")
    print(f"       a payable move on 10%% of ticks is TRADEABLE AT LOW FREQUENCY,")
    print(f"       not untradeable. Only a symbol whose p99 never clears the")
    print(f"       multiple has no tail to trade at all.")

    print(f"\n  RATIO BY HOUR — where the day actually closes down")
    print(f"    {'SYM':8}" + "".join(f"{h:02d}:00".rjust(8) for h in hours))
    for ratio, sym, b, m, n in sorted(rows, reverse=True):
        cells = []
        for h in hours:
            v = mv[sym].get(h)
            cells.append(f"{(pctile(v,.5)/b):>8.1f}" if v and len(v) >= 30 else "       —")
        print(f"    {sym:8}" + "".join(cells))
    print(f"    A cell below 1.0 is an hour in which that symbol cannot pay its")
    print(f"    own spread on a typical move. That is a WAKE decision and an")
    print(f"    entry-window decision, not a setup-quality decision.")

    print(f"\n  ⚠️ CONSERVATIVE BY CONSTRUCTION: breakeven is the full round-trip")
    print(f"     cross, but limit_ladder posts AT the mark. Halve the breakeven")
    print(f"     and every ratio doubles — so a symbol at ratio 0.8 here may be")
    print(f"     marginal rather than hopeless. Treat <1 as a flag to measure")
    print(f"     fill rate on, not as proof on its own.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
