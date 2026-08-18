#!/usr/bin/env python3
"""
tests/fleet_correlation.py — v1.0 — 2026-08-12  (SEL.2)

HOW MANY INDEPENDENT BETS IS THE FLEET ACTUALLY MAKING?

⚠️ THIS IS THE GAP SEL.1 CANNOT SEE. `symbol_edge` ranks symbols one at a time
and says nothing about whether they move TOGETHER. The 13 symbols that clear its
"trade it" bar are almost entirely tech and index: QQQ/SPX/IWM share a beta,
NVDA/MU/AMD/AVGO are semis, AAPL/GOOGL/AMZN/TSLA/NFLX are mega-cap tech. On a
day like the late-July semiconductor selloff most of that book moves as one
position.

**That does not reduce edge PER TRADE. It reduces the number of shots.** Thirteen
boxes at high mutual correlation is not thirteen bets — and daily P&L variance
scales with the EFFECTIVE count, not the nominal one.

    effective N  =  N / (1 + (N-1) * mean_pairwise_correlation)

    N=13, rho 0.0 -> 13.0 independent bets
    N=13, rho 0.3 -> 3.2
    N=13, rho 0.6 -> 1.6      <- thirteen boxes, under two real positions
    N=13, rho 0.9 -> 1.2

⚠️ WHY THIS MATTERS FOR SIZING RATHER THAN SELECTION. A high correlation is NOT
an argument against the 13-symbol list — those symbols were chosen because their
spread is payable, which is a per-trade property and still true. It is an
argument about POSITION SIZE: risking a fixed amount per box across 13
correlated boxes is risking that amount roughly `effective N` times over, not
13 times. The operator's stated exposure is **~$15K every morning**; if the
effective count is under 2, that is far more concentrated than the box count
suggests.

⚠️ AND IT IS DIRECTIONAL WHERE SEL.1 WAS NOT. `preclusion_census` and
`symbol_edge` deliberately measure movement DIRECTIONLESSLY, because
availability is a directionless question. Correlation is not — two symbols that
both move a lot but oppositely are diversifying. So this uses SIGNED returns.

READ-ONLY. stdlib only (no numpy/pandas). Reads the harvested OHLC.
Touches no fleet, no live path, writes nothing.

USAGE (control)
    python3 tests/fleet_correlation.py --since 2026-07-23
    python3 tests/fleet_correlation.py --since 2026-08-01 --bar 5 \\
        --symbols QQQ,SPX,NVDA,TSLA,IWM,AMZN,PLTR,AAPL,MU,GOOGL,NFLX,AMD,AVGO
"""

import argparse
import collections
import csv
import datetime as dt
import glob
import math
import os
import sys

OHLC = os.path.expanduser("~/day_trader_pro/ohlc")


def pearson(a, b):
    n = len(a)
    if n < 20:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    if va <= 0 or vb <= 0:
        return None
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    return cov / math.sqrt(va * vb)


def load_returns(date, bar):
    """symbol -> {HH:MM -> signed return over `bar` minutes}."""
    out = {}
    for path in sorted(glob.glob(os.path.join(OHLC, date, "*_ohlc_*.csv"))):
        sym = os.path.basename(path).split("_")[0]
        closes = []
        with open(path, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                t = r.get("timestamp") or r.get("time")
                try:
                    d = dt.datetime.fromisoformat(t)
                    closes.append((d.strftime("%H:%M"), float(r["close"])))
                except Exception:                              # noqa: BLE001
                    continue
        if len(closes) < bar + 20:
            continue
        rets = {}
        for i in range(bar, len(closes)):
            p0, p1 = closes[i - bar][1], closes[i][1]
            if p0 > 0:
                rets[closes[i][0]] = (p1 - p0) / p0 * 100.0
        if rets:
            out[sym] = rets
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-07-23")
    ap.add_argument("--bar", type=int, default=5,
                    help="return horizon in minutes")
    ap.add_argument("--symbols", default="")
    a = ap.parse_args(argv[1:])

    want = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    dates = sorted(d for d in os.listdir(OHLC) if len(d) == 10 and d >= a.since)
    if not dates:
        print(f"no OHLC at/after {a.since}")
        return 1

    pair = collections.defaultdict(list)      # (s1,s2) -> per-session rho
    seen = collections.Counter()
    per_session = {}                          # date -> (mean rho, stress, n)
    for date in dates:
        rets = load_returns(date, a.bar)
        syms = sorted(s for s in rets if (not want or s in want))
        for s in syms:
            seen[s] += 1
        day_r = []
        for i, s1 in enumerate(syms):
            for s2 in syms[i + 1:]:
                common = sorted(set(rets[s1]) & set(rets[s2]))
                if len(common) < 60:
                    continue
                r = pearson([rets[s1][t] for t in common],
                            [rets[s2][t] for t in common])
                if r is not None:
                    pair[(s1, s2)].append(r)
                    day_r.append(r)
        # ── SESSION STRESS ────────────────────────────────────────────────
        # ⚠️ CORRELATION IS NOT CONSTANT AND RISES IN STRESS — which is exactly
        # when concentration hurts most. A fleet that looks diversified on a
        # quiet day can become one position on a selloff. Stress here is the
        # fleet's median ABSOLUTE return over the session, so it is a property
        # of the tape and not of any label.
        if day_r and syms:
            allabs = [abs(v) for s in syms for v in rets[s].values()]
            if allabs:
                per_session[date] = (sum(day_r) / len(day_r),
                                     sorted(allabs)[len(allabs) // 2], len(syms))

    if not pair:
        print("no symbol pairs with enough overlapping bars")
        return 1

    med = lambda v: sorted(v)[len(v) // 2]
    syms = sorted({s for p in pair for s in p})
    print("=" * 78)
    print(f"  FLEET CORRELATION (SEL.2) — {len(dates)} session(s), "
          f"{len(syms)} symbols, {a.bar}-minute signed returns")
    print("=" * 78)

    rhos = [med(v) for v in pair.values()]
    mean_rho = sum(rhos) / len(rhos)
    N = len(syms)
    eff = N / (1 + (N - 1) * mean_rho) if mean_rho > -1 / (N - 1) else float(N)
    print(f"\n  mean pairwise correlation  {mean_rho:>6.3f}")
    print(f"  nominal symbols            {N:>6}")
    print(f"  ⇒ EFFECTIVE INDEPENDENT BETS {eff:>5.1f}")
    print(f"\n  Risking a fixed amount per box across {N} boxes concentrates that")
    print(f"  risk into roughly {eff:.1f} positions, not {N}. Size on the effective")
    print(f"  count. This is a SIZING verdict, not a reason to drop a symbol —")
    print(f"  spread payability is a per-trade property and is unaffected.")

    if per_session:
        print(f"\n  ⚠️ DOES DIVERSIFICATION SURVIVE STRESS?")
        ss = sorted(per_session.items(), key=lambda kv: kv[1][1])
        half = len(ss) // 2
        quiet = [v[0] for _d, v in ss[:half]]
        busy = [v[0] for _d, v in ss[half:]]
        if quiet and busy:
            qr = sum(quiet) / len(quiet)
            br = sum(busy) / len(busy)
            qe = N / (1 + (N - 1) * qr)
            be = N / (1 + (N - 1) * br)
            print(f"    {'half':10}{'sessions':>10}{'mean rho':>11}{'effective N':>13}")
            print(f"    {'quiet':10}{len(quiet):>10}{qr:>11.3f}{qe:>13.1f}")
            print(f"    {'busy':10}{len(busy):>10}{br:>11.3f}{be:>13.1f}")
            if br > qr:
                print(f"    ⇒ CORRELATION RISES WITH MOVEMENT. The fleet becomes")
                print(f"      MORE concentrated on exactly the days it trades most,")
                print(f"      so worst-case exposure is the BUSY figure, not the mean.")
            else:
                print(f"    ⇒ correlation does NOT rise with movement here — the")
                print(f"      diversification holds up on the days that matter.")
        print(f"\n    {'date':12}{'mean rho':>10}{'median |ret|':>14}{'syms':>6}")
        for d, (r, st, k) in sorted(per_session.items()):
            print(f"    {d:12}{r:>10.3f}{st:>13.3f}%{k:>6}")

    print(f"\n  MOST CORRELATED PAIRS (median across sessions)")
    top = sorted(((med(v), k) for k, v in pair.items()), reverse=True)[:12]
    for r, (s1, s2) in top:
        print(f"    {s1:6} {s2:6}{r:>8.3f}")

    print(f"\n  LEAST CORRELATED — where the real diversification is")
    for r, (s1, s2) in sorted(((med(v), k) for k, v in pair.items()))[:12]:
        print(f"    {s1:6} {s2:6}{r:>8.3f}")

    print(f"\n  PER-SYMBOL MEAN CORRELATION TO THE REST")
    per = collections.defaultdict(list)
    for (s1, s2), v in pair.items():
        m = med(v)
        per[s1].append(m)
        per[s2].append(m)
    print(f"    {'SYM':8}{'mean rho':>10}{'sessions':>10}   note")
    for s, v in sorted(per.items(), key=lambda kv: sum(kv[1]) / len(kv[1])):
        m = sum(v) / len(v)
        note = ("DIVERSIFIER" if m < 0.25 else
                ("adds little" if m > 0.55 else ""))
        print(f"    {s:8}{m:>10.3f}{seen[s]:>10}   {note}")
    print(f"\n  ⚠️ A symbol with a LOW mean correlation earns its slot twice: it")
    print(f"     trades on its own merits AND it is the only thing keeping the")
    print(f"     effective count above 1. Dropping diversifiers to concentrate on")
    print(f"     the highest-ratio names would RAISE per-trade edge and LOWER the")
    print(f"     number of bets — those pull in opposite directions.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
