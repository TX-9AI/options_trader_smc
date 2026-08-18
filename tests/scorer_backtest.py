#!/usr/bin/env python3
"""
tests/scorer_backtest.py — v1.2 — 2026-08-13

v1.2 — 2026-08-13 — `load_trades` now carries `raw` (the whole trades.db row)
        and DE-DUPLICATES BY `trade_id`. The raw row is for
        `spread_counterfactual.py`, which needs `underlying_entry` and
        `direction` — fields this tool never used. The dedupe is the correction:
        harvest copied a CUMULATIVE trades.db into each dated folder, and even
        post-trim the live folders still hold repeats (`trade_report` reduces
        1,567 rows to 843 unique). Every reader of these DBs must key on
        `trade_id`; rows without one are KEPT and counted, never dropped.
        ⚠️ The joined counts printed by v1.0/v1.1 were therefore slightly
        inflated. The per-dimension medians are unaffected in shape but the n
        column was not a distinct-trade count.

v1.1 — 2026-08-13 — Each scored record now carries `raw`: the whole journal
        line. Nothing in this tool reads it. It exists so `factor_sweep.py`
        can test the fields the scorer never looks at (rrr, contract spread,
        atr, vix, confluence count) WITHOUT re-implementing the join. Two
        tools have now independently re-written this join and both got it
        wrong (ANT.1 v1.0 grouped 128,503 rows as None; grade_inversion_check
        v1.0 joined zero of 805). ONE JOIN, ONE OWNER — import from here.
v1.0 — 2026-08-12 — first cut.

DOES THE SETUP SCORER EARN ITS KEEP — ON EVERY STRATEGY, DIMENSION BY DIMENSION?

Operator, 2026-08-12: *"Let's make the setup scorer earn its keep. Not just on
ORB — on the entire arsenal. And I want to backtest on the data we're holding
right now."*

⚠️ THIS USES A CONTROL ARM THAT HAS NEVER BEEN READ. `setup_scorer.score()`
emits a `scored` event for EVERY signal **including below-B rejections**
(`grade="REJECT"`), carrying the full per-dimension breakdown. So the journal
holds the trades that were REFUSED as well as the ones taken — the counterfactual
population every threshold question has lacked all along.

────────────────────────────────────────────────────────────────────────────
WHAT IT ANSWERS
────────────────────────────────────────────────────────────────────────────
  1. PER DIMENSION, PER STRATEGY — does this input separate winners from
     losers? Reported as the median for each, plus SPREAD (p90-p10). A
     dimension whose p10 == p90 is a CONSTANT: no threshold on it can ever
     separate outcomes, and no amount of re-weighting will fix that. Fixing it
     means changing what the input MEASURES, not where its bar sits.
  2. DOES THE TOTAL SEPARATE? If `total` medians are equal for winners and
     losers, the scorer is not grading the thing that decides the outcome.
  3. DOES THE GRADE BAR SEPARATE? A vs B win rate and net.
  4. WHAT DID WE REFUSE? REJECT-grade signals never became trades, so they have
     no P&L — but their score DISTRIBUTION versus the taken population says
     whether the bar sits anywhere meaningful.

⚠️ ORB IS EXPECTED TO SHOW A CONSTANT AND THAT IS BY DESIGN, NOT A DEFECT.
setup_scorer v1.4 short-circuits ORB to `_grade_orb` BEFORE the weighted
machinery: "a confirmed ORB ALWAYS trades", the only grade input being whether
liquidity sits in the path to the 100% TP. The reasoning on record is that the
ORB state machine already validated the geometry and the old inputs were
"regime conviction in costume". So a flat 1.50 on ORB is the design speaking.
The open question this tool can inform is whether a DIFFERENT input — one that
answers "is a worthwhile move available today", not "is this setup well formed"
— would separate where the current ones do not.

────────────────────────────────────────────────────────────────────────────
THE JOIN, and its one fragile assumption
────────────────────────────────────────────────────────────────────────────
`scored` -> `disposition` -> trades.db, keyed on (symbol, strategy) within a
2-second window of `ts_et`. The journal's own contract states events within the
same second for one symbol/strategy ARE the same signal, because the loop is
single-threaded per box and emits one signal per tick. The tolerance is widened
to 2s only to survive clock rounding between the two writers.
  ⚠️ A trade with no matching `scored` row is DROPPED and counted, not guessed.
     The unmatched count is printed — if it is large the join is unsound and
     nothing below it should be believed.

READ-ONLY. stdlib only. Touches no fleet, no live path, writes nothing.

USAGE (control)
    python3 tests/scorer_backtest.py --since 2026-07-20
    python3 tests/scorer_backtest.py --since 2026-07-20 --strategy ContinuationStrategy
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
MIN_N = 8


def _iso(s):
    try:
        d = dt.datetime.fromisoformat(str(s))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:                                          # noqa: BLE001
        return None


def pct(v, q):
    v = sorted(x for x in v if x is not None)
    return v[min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))] if v else None


def load_scored(date):
    out = []
    for path in sorted(glob.glob(os.path.join(JOURNAL, date, "*.jsonl"))):
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"scored"' not in line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:                              # noqa: BLE001
                    continue
                if r.get("event") != "scored":
                    continue
                sc = r.get("score") or {}
                ts = _iso(r.get("ts_et"))
                if ts is None:
                    continue
                out.append({
                    "ts": ts, "sym": r.get("symbol"),
                    "strategy": r.get("strategy") or (r.get("signal") or {}).get("strategy"),
                    "total": sc.get("total"), "grade": sc.get("grade"),
                    "breakdown": sc.get("breakdown") or {},
                    # v1.1 — the untouched journal line, for factor_sweep.
                    "raw": r,
                })
    return out


def load_trades(date, seen=None):
    """Closed trades for one dated folder, DISTINCT by trade_id.

    `seen` is an optional cross-date set so a trade repeated in many folders
    counts ONCE across a whole run. Rows with no trade_id are KEPT and counted
    — discarding unattributable rows shrinks the corpus in a way nobody can
    audit, which is `trim_trade_dbs`' own stated principle.
    """
    out = []
    if seen is None:
        seen = set()
    for path in sorted(glob.glob(os.path.join(TRADES, date, "*_trades_*.db"))):
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            rows = [dict(r) for r in conn.execute("SELECT * FROM trades")]
            conn.close()
        except Exception:                                      # noqa: BLE001
            continue
        for d in rows:
            if str(d.get("status") or "") != "closed":
                continue
            ts = _iso(d.get("entry_time"))
            if ts is None:
                continue
            tid = d.get("trade_id")
            if tid:
                if tid in seen:
                    continue
                seen.add(tid)
            out.append({"ts": ts, "sym": d.get("symbol"),
                        "strategy": d.get("strategy"),
                        "pnl": float(d.get("pnl_usd") or 0),
                        "setup_type": d.get("setup_type") or "",
                        "raw": d})                     # v1.2
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("dates", nargs="*")
    ap.add_argument("--since", default="")
    ap.add_argument("--strategy", default="")
    a = ap.parse_args(argv[1:])

    if a.since:
        dates = sorted(d for d in os.listdir(JOURNAL) if len(d) == 10 and d >= a.since)
    elif a.dates:
        dates = a.dates
    else:
        print("usage: scorer_backtest.py <date> | --since <date>")
        return 1

    joined, rejects, unmatched, scored_n = [], [], 0, 0
    _seen = set()                                              # v1.2 dedupe
    for date in dates:
        sc = load_scored(date)
        scored_n += len(sc)
        tr = load_trades(date, _seen)
        idx = collections.defaultdict(list)
        for s in sc:
            idx[(s["sym"], s["strategy"])].append(s)
        rejects.extend(s for s in sc if str(s["grade"]).upper() == "REJECT")
        for t in tr:
            cands = idx.get((t["sym"], t["strategy"])) or []
            best, bd = None, JOIN_TOL_S + 1
            for s in cands:
                d = abs((s["ts"] - t["ts"]).total_seconds())
                if d < bd:
                    best, bd = s, d
            if best is None or bd > JOIN_TOL_S:
                unmatched += 1
                continue
            joined.append({**t, "total": best["total"], "grade": best["grade"],
                           "breakdown": best["breakdown"],
                           "raw": best.get("raw") or {}})

    print("=" * 78)
    print(f"  SETUP SCORER BACKTEST — {len(dates)} session(s)")
    print(f"  scored events {scored_n:,}   of which REJECT {len(rejects):,}"
          f"   trades joined {len(joined)}   UNMATCHED {unmatched}")
    if unmatched > len(joined) * 0.25:
        print(f"  ⚠️⚠️ {unmatched} trades had no `scored` row within {JOIN_TOL_S}s."
              f" THE JOIN IS UNSOUND — do not believe anything below.")
    print("=" * 78)
    if not joined:
        print("\n  nothing joined; cannot proceed")
        return 1

    by = collections.defaultdict(list)
    for j in joined:
        if a.strategy and j["strategy"] != a.strategy:
            continue
        by[j["strategy"]].append(j)

    for strat, g in sorted(by.items(), key=lambda kv: -len(kv[1])):
        w = [x for x in g if x["pnl"] > 0]
        l = [x for x in g if x["pnl"] <= 0]
        print(f"\n{'='*78}\n  {strat}   n={len(g)}  win {100.0*len(w)/len(g):.0f}%"
              f"  net ${sum(x['pnl'] for x in g):+,.0f}")
        if len(w) < MIN_N or len(l) < MIN_N:
            print(f"  ⚠️ UNDERPOWERED — winners {len(w)}, losers {len(l)},"
                  f" floor {MIN_N}. ABSENT MEASUREMENT, not a null.")
        tw = [x["total"] for x in w if x["total"] is not None]
        tl = [x["total"] for x in l if x["total"] is not None]
        if tw and tl:
            sw = (pct(tw, .9) or 0) - (pct(tw, .1) or 0)
            print(f"\n  TOTAL     win p50 {pct(tw,.5):.3f}   lose p50 {pct(tl,.5):.3f}"
                  f"   spread(win p90-p10) {sw:.3f}"
                  + ("   <-- CONSTANT: no threshold can separate" if sw < 1e-6 else ""))

        dims = set()
        for x in g:
            dims.update(k for k, v in (x["breakdown"] or {}).items()
                        if isinstance(v, (int, float)))
        if dims:
            print(f"\n  {'dimension':22}{'win p50':>9}{'lose p50':>10}{'sep':>8}"
                  f"{'spread':>9}   verdict")
            scored_dims = []
            for d in sorted(dims):
                vw = [x["breakdown"].get(d) for x in w]
                vl = [x["breakdown"].get(d) for x in l]
                mw, ml = pct(vw, .5), pct(vl, .5)
                if mw is None or ml is None:
                    continue
                allv = [v for v in vw + vl if v is not None]
                spread = (pct(allv, .9) or 0) - (pct(allv, .1) or 0)
                sep = mw - ml
                verdict = ("CONSTANT — change what it measures" if spread < 1e-6
                           else ("separates" if abs(sep) >= 0.05 else "flat"))
                scored_dims.append((abs(sep), d, mw, ml, sep, spread, verdict))
            for _, d, mw, ml, sep, spread, verdict in sorted(scored_dims, reverse=True):
                print(f"  {d[:21]:22}{mw:>9.3f}{ml:>10.3f}{sep:>+8.3f}"
                      f"{spread:>9.3f}   {verdict}")
            print(f"    sep = winner median - loser median. A dimension with sep")
            print(f"    ~0 does not grade the thing that decides the outcome, and")
            print(f"    re-weighting it changes nothing.")

        gr = collections.defaultdict(list)
        for x in g:
            gr[str(x["grade"])].append(x)
        print(f"\n  {'grade':10}{'n':>5}{'win%':>7}{'net$':>11}{'avg$':>9}")
        for k, gg in sorted(gr.items()):
            ww = sum(1 for x in gg if x["pnl"] > 0)
            print(f"  {k:10}{len(gg):>5}{100.0*ww/len(gg):>6.0f}%"
                  f"{sum(x['pnl'] for x in gg):>11,.0f}"
                  f"{sum(x['pnl'] for x in gg)/len(gg):>9,.0f}")

    # ── THE CONTROL ARM ────────────────────────────────────────────────────
    print(f"\n{'='*78}\n  THE REFUSED POPULATION — signals the bar turned away")
    print(f"{'='*78}")
    if not rejects:
        print("  no REJECT-grade rows found. Either the bar refused nothing, or")
        print("  the journal predates the below-B emission. Check before reading")
        print("  the absence as evidence.")
    else:
        rb = collections.defaultdict(list)
        for r in rejects:
            rb[r["strategy"]].append(r)
        print(f"  {'strategy':28}{'refused':>9}{'total p50':>11}{'p90':>9}")
        for s, rr in sorted(rb.items(), key=lambda kv: -len(kv[1])):
            tt = [x["total"] for x in rr if x["total"] is not None]
            print(f"  {str(s)[:27]:28}{len(rr):>9}"
                  f"{(pct(tt,.5) if tt else float('nan')):>11.3f}"
                  f"{(pct(tt,.9) if tt else float('nan')):>9.3f}")
        print(f"\n  ⚠️ These have NO P&L — they were never taken. What they tell you")
        print(f"     is whether the BAR sits anywhere meaningful: if the refused")
        print(f"     distribution overlaps the TAKEN one heavily, the bar is")
        print(f"     cutting arbitrarily rather than discriminating.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
