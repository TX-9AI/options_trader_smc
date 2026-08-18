#!/usr/bin/env python3
"""
tests/grade_inversion_check.py — v1.0 — 2026-08-13  (EV.1)

IS THE GRADE INVERSION REAL, OR IS IT A HANDFUL OF BIG LOSERS?

`scorer_backtest` v1.0 measured, over 18 sessions and 805 joined trades:

    ContinuationStrategy   A: 399 trades  44% win  **-$8,244**
                           B: 220 trades  49% win  **+$1,893**
    SweepReversal          A:   3 trades  67% win     +$494
                           B:  28 trades  **82%** win  +$2,238

**That is the single largest located leak in the book** — and "stop preferring
your highest-graded trades" is a wild enough conclusion that it must survive
scrutiny before it becomes an action. A difference of that size can come from
four sources, and only one of them justifies a change:

  1. A GENUINE INVERSION — A really does select worse trades.
  2. A FEW BIG LOSERS — one or two outliers in A carrying the whole gap.
  3. ONE BAD SESSION — the split holding on a single day and nowhere else.
  4. A SIZE ARTEFACT — A trades sized larger, so the same win rate costs more.

This separates them. Each test can independently kill the finding.

────────────────────────────────────────────────────────────────────────────
THE FOUR TESTS
────────────────────────────────────────────────────────────────────────────
  PER-SESSION SIGN — how many sessions did B beat A? A real effect shows up in
      MOST sessions, not in the total. **This is the strongest single test**:
      a 12-of-18 split is an effect; 4-of-18 with one huge day is an outlier.
  TRIMMED — drop the best and worst 5% of trades in EACH grade and re-total.
      If the gap collapses, it was outliers.
  PER-TRADE AVERAGE and MEDIAN — the median is immune to outliers entirely.
      If A's MEDIAN trade is also worse, the inversion is in the body of the
      distribution and not in its tail.
  SIZE — average contracts per grade. If A is sized larger, part of the dollar
      gap is exposure and not selection, and the honest comparison is pnl_pct.

⚠️ WHAT THIS TOOL CANNOT DO. It cannot say WHY the grade inverts. The mechanism
already on record is that every quality input is a CONFLUENCE COUNT and things
agree only AFTER a move is underway — so on a decaying instrument a high score
means LATE. That explanation is consistent with an inversion but is not proven
by it, and this tool does not test it.

⚠️ AND THE ACTION IS NOT OBVIOUS EVEN IF IT SURVIVES. "Refuse A-grade
continuation" is one reading; "the grade carries no information and the volume
is the problem" is another, and CNT.6 is the precedent for the second — it cut
continuation volume 6x and took it from worst in the book to best in a session
WITHOUT touching the grade. Prefer the volume reading unless the per-session
sign test is decisive.

READ-ONLY. stdlib only. Reads the signal journal + trades.db.
Touches no fleet, no live path, writes nothing.

USAGE (control)
    python3 tests/grade_inversion_check.py --since 2026-07-20
    python3 tests/grade_inversion_check.py --since 2026-07-20 --strategy SweepReversal
"""

import argparse
import collections
import datetime as dt
import glob
import json
import os
import sqlite3
import sys

DTP = os.path.expanduser("~/day_trader_pro")
JOURNAL = os.path.join(DTP, "signal_journal")
TRADES = os.path.join(DTP, "trades")
JOIN_TOL_S = 2.0


def _iso(s):
    try:
        d = dt.datetime.fromisoformat(str(s))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:                                          # noqa: BLE001
        return None


def med(v):
    v = sorted(v)
    return v[len(v) // 2] if v else None


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-07-20")
    ap.add_argument("--strategy", default="ContinuationStrategy")
    a = ap.parse_args(argv[1:])

    dates = sorted(d for d in os.listdir(JOURNAL) if len(d) == 10 and d >= a.since)
    joined, unmatched = [], 0
    for date in dates:
        scored = collections.defaultdict(list)
        for path in sorted(glob.glob(os.path.join(JOURNAL, date, "*.jsonl"))):
            with open(path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"scored"' not in line:
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:                          # noqa: BLE001
                        continue
                    if r.get("event") != "scored":
                        continue
                    sc = r.get("score") or {}
                    ts = _iso(r.get("ts_et"))
                    if ts is None:
                        continue
                    scored[(r.get("symbol"), r.get("strategy"))].append(
                        (ts, sc.get("grade"), sc.get("total")))
        for path in sorted(glob.glob(os.path.join(TRADES, date, "*_trades_*.db"))):
            try:
                conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
                conn.row_factory = sqlite3.Row
                trs = [dict(x) for x in conn.execute("SELECT * FROM trades")]
                conn.close()
            except Exception:                                  # noqa: BLE001
                continue
            for t in trs:
                if str(t.get("status") or "") != "closed":
                    continue
                if t.get("strategy") != a.strategy:
                    continue
                ts = _iso(t.get("entry_time"))
                if ts is None:
                    continue
                best, bd = None, JOIN_TOL_S + 1
                for s in scored.get((t.get("symbol"), t.get("strategy")), []):
                    d = abs((s[0] - ts).total_seconds())
                    if d < bd:
                        best, bd = s, d
                if best is None or bd > JOIN_TOL_S:
                    unmatched += 1
                    continue
                joined.append({
                    "date": date, "sym": t.get("symbol"), "grade": str(best[1]),
                    "total": best[2], "pnl": float(t.get("pnl_usd") or 0),
                    "pnl_pct": float(t.get("pnl_pct") or 0) * 100,
                    "n": int(float(t.get("contracts") or 0)),
                })

    if not joined:
        print(f"no {a.strategy} trades joined to a scored event")
        return 1

    grades = sorted({x["grade"] for x in joined})
    print("=" * 78)
    print(f"  GRADE INVERSION CHECK (EV.1) — {a.strategy}")
    print(f"  {len(dates)} session(s), {len(joined)} joined, {unmatched} unmatched")
    print("=" * 78)

    print(f"\n  HEADLINE")
    print(f"    {'grade':8}{'n':>6}{'win%':>7}{'net$':>11}{'avg$':>9}"
          f"{'MEDIAN$':>10}{'avg %':>8}{'avg size':>10}")
    for g in grades:
        sub = [x for x in joined if x["grade"] == g]
        if not sub:
            continue
        w = sum(1 for x in sub if x["pnl"] > 0)
        print(f"    {g:8}{len(sub):>6}{100.0*w/len(sub):>6.0f}%"
              f"{sum(x['pnl'] for x in sub):>11,.0f}"
              f"{sum(x['pnl'] for x in sub)/len(sub):>9,.0f}"
              f"{med([x['pnl'] for x in sub]):>10,.0f}"
              f"{sum(x['pnl_pct'] for x in sub)/len(sub):>7.1f}%"
              f"{sum(x['n'] for x in sub)/len(sub):>10.1f}")
    print(f"    ⚠️ If MEDIAN$ inverts too, the effect is in the BODY of the")
    print(f"       distribution, not its tail. If avg size differs materially,")
    print(f"       part of the dollar gap is EXPOSURE, not selection — read")
    print(f"       'avg %' instead.")

    # ── PER-SESSION SIGN — the strongest single test ────────────────────────
    print(f"\n  PER-SESSION SIGN — did B beat A on most days, or on one day?")
    if len(grades) >= 2:
        hi, lo = grades[0], grades[1]        # 'A' sorts before 'B'
        wins = ties = 0
        rowsx = []
        for d in dates:
            ga = [x["pnl"] for x in joined if x["date"] == d and x["grade"] == hi]
            gb = [x["pnl"] for x in joined if x["date"] == d and x["grade"] == lo]
            if not ga or not gb:
                continue
            sa, sb = sum(ga), sum(gb)
            rowsx.append((d, len(ga), sa, len(gb), sb))
            if sb > sa:
                wins += 1
            elif sb == sa:
                ties += 1
        print(f"    {'date':12}{hi+' n':>6}{hi+' $':>10}{lo+' n':>6}{lo+' $':>10}"
              f"   winner")
        for d, na, sa, nb, sb in rowsx:
            print(f"    {d:12}{na:>6}{sa:>10,.0f}{nb:>6}{sb:>10,.0f}"
                  f"   {lo if sb > sa else hi}")
        tot = len(rowsx)
        if tot:
            print(f"\n    ⇒ {lo} beat {hi} on {wins}/{tot} sessions"
                  f" ({100.0*wins/max(tot,1):.0f}%)")
            if wins >= tot * 0.65:
                print(f"      **THE INVERSION IS PERSISTENT** — it is not one bad day.")
            elif wins <= tot * 0.4:
                print(f"      NOT PERSISTENT — the total is driven by a few sessions."
                      f" Do NOT act on the headline.")
            else:
                print(f"      MIXED — roughly a coin flip by session. The dollar gap")
                f"      is concentrated, not systematic."

    # ── TRIMMED ────────────────────────────────────────────────────────────
    print(f"\n  TRIMMED (drop best and worst 5% within each grade)")
    print(f"    {'grade':8}{'n kept':>8}{'net$':>11}{'avg$':>9}")
    for g in grades:
        sub = sorted((x["pnl"] for x in joined if x["grade"] == g))
        if len(sub) < 20:
            continue
        k = max(1, int(len(sub) * 0.05))
        kept = sub[k:-k]
        print(f"    {g:8}{len(kept):>8}{sum(kept):>11,.0f}"
              f"{sum(kept)/len(kept):>9,.0f}")
    print(f"    ⚠️ If the gap SURVIVES trimming, outliers are not the cause.")

    print(f"\n  ── HOW TO ACT ──")
    print(f"    Only the PER-SESSION SIGN test justifies refusing a grade. If it")
    print(f"    is mixed, the honest reading is that the grade carries no")
    print(f"    information and the VOLUME is the problem — CNT.6 is the")
    print(f"    precedent: it cut continuation volume 6x and moved it from worst")
    print(f"    to best in the book WITHOUT touching the grade.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
