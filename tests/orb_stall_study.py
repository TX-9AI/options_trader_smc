#!/usr/bin/env python3
"""
tests/orb_stall_study.py — v1.2 — 2026-08-12

v1.2 — THE PACE ENVELOPE. Operator's construction: "the 100% TP is the height of
       the range, and we know the average hold time of winners — the velocity of
       the required move can be derived." Verified against the trade rows:
       target = range boundary +/- range HEIGHT, so the distance every ORB trade
       must cover IS the range height and progress-as-%-of-distance is already
       normalised across symbol and volatility. A pace floor derived this way is
       symbol-agnostic by construction.
       Prints WINNERS p10/p25/p50 and losers p50/p75/p90 at each mark, counting
       only trades STILL OPEN at that mark. A floor set at winners p10 admits 90%
       of historical winners BY CONSTRUCTION — the floor is derived from the
       distribution rather than chosen, which is what keeps a curve with a shape,
       a scale and an intercept from simply describing 2026.

v1.1 — ⚠️ v1.0's CUT TABLE WAS WRONG IN TWO WAYS AND BOTH INFLATED THE CASE FOR
       A RULE. Corrected here, and the corrections change the answer.
       (a) IT NEVER CHECKED WHETHER THE TRADE WAS STILL OPEN AT THE MARK. Median
           loser hold is 4.0 min and `orb_structure_stop` — 61 of 76 losers over
           15 sessions — has a median hold of 3.0 min. Those trades are ALREADY
           CLOSED before a 10- or 15-minute rule could fire, yet v1.0 counted
           them as "cut" because it scored progress over whatever bars the hold
           contained. **Most of the $14,559 it credited to a 15m rule was
           unreachable by construction.**
       (b) `$saved` summed the FULL REALIZED LOSS of every cut trade, which
           assumes cutting mid-trade recovers everything lost up to that point.
           It does not. The trade is already down at the mark; only the bleed
           AFTER it is recoverable.
       v1.1 gates every cut on `hold >= mark`, reports ELIGIBLE (what a rule can
       actually touch) separately from the population, and labels the dollar
       column an UPPER BOUND with its assumption stated — the per-trade premium
       series needed for an exact figure is not in the trade DB.
       It also splits eligible losers by whether their WORST premium came before
       or after the mark: damage already done is not recoverable by cutting.

DO STALLED ORB TRADES DECLARE THEMSELVES EARLY ENOUGH TO CUT?

THE PROBLEM THIS MEASURES, found on 2026-08-12. Three ORB trades that day died
at the hard percentage stop (-39% to -47%) rather than at `orb_structure_stop`,
and reading the 1m tape showed why: **the structure stop never had cause to
fire.** On QQQ and AVGO the underlying finished the hold BELOW the short entry —
directionally right the whole time — and never once closed through the
structural level. The loss came entirely from PREMIUM DECAY on a sub-dollar 0DTE
contract while the setup stayed technically valid.

    QQQ   entry 724.19  structure 724.75  closes above it: 0   result -42.2%
    AVGO  entry 421.195 structure 422.28  closes above it: 0   result -40.4%

`_theta_bleed` does not cover this either, and correctly so: its gate (1) is a
GAIN FLOOR (`pnl_pct < THETA_MIN_GAIN_PCT` -> return False). It is a
PROFIT-PROTECTION rule — "you earned something, decay is about to take it" — and
has no opinion on a losing position. QQQ peaked at +22.5% only 5.75 min in,
which is inside the 20-minute blackout AND already above the 20% trail ceiling,
so theta was silent by design; by the time the blackout lifted the gain was gone
and the 10% floor locked it out permanently. It then bled for 50 more minutes.

**So "the setup has not invalidated AND has not worked" is a state with no
owner.** This tool measures whether that state is IDENTIFIABLE EARLY.

THE STATISTIC: progress of the UNDERLYING toward its own target, as a percentage
of the entry->target distance, sampled at 3/5/10/15 minutes. Measured on the
underlying rather than on premium deliberately — premium conflates direction
with decay, and decay is the thing under suspicion.

⚠️ WHY THIS IS A STUDY AND NOT A RULE. On 2026-08-12 alone the separation looked
decisive (winners 83% progress by 3 min, losers 12%) — but that was **n=2
winners, both AVGO, one hour apart.** That is one observation dressed as two.
The number that decides whether a cut is safe is the FALSE-POSITIVE RATE: how
often a trade below the threshold goes on to win anyway. One counterexample
moves the threshold; zero counterexamples at n=5 tells you nothing.

⚠️ A CONFOUND THIS TOOL PRINTS RATHER THAN HIDES: on 08-12 every ORB loser was a
SHORT (ORB Short -$2,422 on 13 vs ORB Long +$497 on 4). A progress rule and a
direction rule could be measuring the same thing at that sample size, so the
output splits by direction and refuses a verdict when one side is empty.

READ-ONLY. stdlib only. Touches no fleet, no live path, writes nothing.

USAGE (control)
    python3 tests/orb_stall_study.py 2026-08-12
    python3 tests/orb_stall_study.py 2026-08-05 2026-08-12     # inclusive range
    python3 tests/orb_stall_study.py --since 2026-08-01
"""

import argparse
import csv
import datetime as dt
import glob
import os
import sqlite3
import sys

DTP = os.path.expanduser("~/day_trader_pro")
TRADES = os.path.join(DTP, "trades")
OHLC = os.path.join(DTP, "ohlc")
MARKS = (3, 5, 10, 15)
MIN_N = 8               # below this a cell is reported but never graded


def _iso(s):
    try:
        d = dt.datetime.fromisoformat(str(s))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:                                          # noqa: BLE001
        return None


def load_trades(date):
    """Every ORB trade for one date, from the per-symbol DBs."""
    out = []
    for path in sorted(glob.glob(os.path.join(TRADES, date, "*_trades_*.db"))):
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM trades").fetchall()
            conn.close()
        except Exception as exc:                               # noqa: BLE001
            print(f"  skip {os.path.basename(path)}: {exc}")
            continue
        for r in rows:
            d = dict(r)
            if "ORB" not in str(d.get("setup_type") or ""):
                continue
            if str(d.get("status") or "") != "closed":
                continue
            out.append(d)
    return out


def load_tape(sym, date):
    p = os.path.join(OHLC, date, f"{sym}_ohlc_{date}.csv")
    if not os.path.isfile(p):
        return None
    bars = []
    with open(p, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            t = _iso(r.get("timestamp") or r.get("time"))
            if t is None:
                continue
            try:
                bars.append((t.astimezone(dt.timezone.utc), float(r["high"]),
                             float(r["low"]), float(r["close"])))
            except Exception:                                  # noqa: BLE001
                continue
    return bars or None


def progress(bars, t0, entry, target, short, minutes=None):
    """Best excursion toward TARGET as a share of the entry->target distance.

    100% = the target was reached. Negative = it went the wrong way. Measured on
    the UNDERLYING, so it is a statement about the THESIS and not about decay.
    """
    dist = abs(target - entry)
    if dist <= 0:
        return None
    w = bars if minutes is None else [
        b for b in bars if (b[0] - t0).total_seconds() <= minutes * 60]
    if not w:
        return None
    ext = min(b[2] for b in w) if short else max(b[1] for b in w)
    return ((entry - ext) if short else (ext - entry)) / dist * 100.0


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("dates", nargs="*")
    ap.add_argument("--since", default="")
    a = ap.parse_args(argv[1:])

    if a.since:
        dates = sorted(d for d in os.listdir(TRADES)
                       if len(d) == 10 and d >= a.since)
    elif len(a.dates) == 2:
        lo, hi = sorted(a.dates)
        dates = sorted(d for d in os.listdir(TRADES)
                       if len(d) == 10 and lo <= d <= hi)
    elif a.dates:
        dates = a.dates
    else:
        print("usage: orb_stall_study.py <date> [<date2>] | --since <date>")
        return 1

    recs, no_tape = [], 0
    for date in dates:
        trades = load_trades(date)
        tapes = {}
        for t in trades:
            sym = t.get("symbol")
            if sym not in tapes:
                tapes[sym] = load_tape(sym, date)
            bars = tapes[sym]
            t0, t1 = _iso(t.get("entry_time")), _iso(t.get("exit_time"))
            try:
                e = float(t.get("underlying_entry") or 0)
                tgt = float(t.get("underlying_target") or 0)
            except Exception:                                  # noqa: BLE001
                continue
            if not bars or not t0 or not t1 or e <= 0 or tgt <= 0:
                no_tape += 1
                continue
            hold_bars = [b for b in bars if t0 <= b[0] <= t1]
            if not hold_bars:
                no_tape += 1
                continue
            short = str(t.get("direction") or "") == "short"
            lo_at = _iso(t.get("min_premium_seen_at"))
            recs.append({
                "date": date, "sym": sym, "t0": t0,
                "dir": "short" if short else "long",
                "pnl": float(t.get("pnl_usd") or 0),
                "pnl_pct": float(t.get("pnl_pct") or 0) * 100,
                "exit": str(t.get("exit_reason") or "").split(":")[0].split(" pnl")[0],
                "hold": (t1 - t0).total_seconds() / 60.0,
                "prog": {m: progress(hold_bars, t0, e, tgt, short, m) for m in MARKS},
                "best": progress(hold_bars, t0, e, tgt, short),
                # v1.1 — was the WORST premium still ahead at each mark?
                "low_after_mark": {
                    m: (lo_at is not None
                        and (lo_at - t0).total_seconds() / 60.0 > m)
                    for m in MARKS},
            })

    if not recs:
        print("no ORB trades with usable tape in range")
        return 1

    win = [r for r in recs if r["pnl"] > 0]
    los = [r for r in recs if r["pnl"] <= 0]
    print("=" * 78)
    print(f"  ORB STALL STUDY — {len(dates)} session(s), {len(recs)} ORB trade(s)"
          f"   winners {len(win)}  losers {len(los)}")
    if no_tape:
        print(f"  ⚠️ {no_tape} trade(s) skipped — no matching tape or bars in hold")
    print("=" * 78)

    def med(vals):
        v = sorted(x for x in vals if x is not None)
        return v[len(v) // 2] if v else None

    def fmt(v):
        return f"{v:>7.0f}%" if v is not None else "      —"

    print(f"\n  PROGRESS TOWARD TARGET ON THE UNDERLYING (median)")
    print(f"    {'':10}{'n':>5}" + "".join(f"{'@'+str(m)+'m':>8}" for m in MARKS)
          + f"{'best':>8}{'hold':>8}")
    for name, grp in (("winners", win), ("losers", los)):
        if not grp:
            continue
        print(f"    {name:10}{len(grp):>5}"
              + "".join(fmt(med([r['prog'][m] for r in grp])) for m in MARKS)
              + fmt(med([r['best'] for r in grp]))
              + f"{med([r['hold'] for r in grp]):>7.1f}m")

    # ── THE PACE ENVELOPE ─────────────────────────────────────────────────
    # Operator's construction (2026-08-12): "the 100% TP is the height of the
    # range, and we know the average hold time of winners — the velocity of the
    # required move can be derived."
    # Confirmed against the trade rows: target = range boundary +/- range HEIGHT
    # (AVGO range 421.77-426.53, height 4.76, short target 417.01 = 421.77-4.76).
    # So the distance every ORB trade must cover IS the range height, and
    # progress-as-%-of-distance is already normalised across symbols and
    # volatility — the curve derived here is symbol-agnostic by construction.
    #
    # ⚠️ THE FLOOR MUST BE DERIVED, NOT CHOSEN. A curve has a shape, a scale and
    # an intercept; fitted freely to 58 winners it will describe 2026 rather
    # than the strategy. Taking a LOW PERCENTILE of the winners' own
    # distribution removes that freedom: the floor is then "worse than 90% of
    # winners ever were at this point", which is a measurement, not a shape
    # anyone picked.
    def pct(vals, q):
        v = sorted(x for x in vals if x is not None)
        if not v:
            return None
        return v[min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))]

    print(f"\n  PACE ENVELOPE — progress percentiles at each mark")
    print(f"    {'':10}{'n':>5}" + "".join(f"{'@'+str(m)+'m':>8}" for m in MARKS))
    for label, grp, qs in (("WINNERS", win, (0.10, 0.25, 0.50)),
                           ("losers", los, (0.50, 0.75, 0.90))):
        for q in qs:
            # only trades STILL OPEN at the mark inform the floor at that mark:
            # a winner that closed at 4 min says nothing about where a live
            # trade should be at 10.
            row = "".join(
                fmt(pct([r["prog"][m] for r in grp if r["hold"] >= m], q))
                for m in MARKS)
            print(f"    {label+' p'+str(int(q*100)):10}"
                  f"{len([r for r in grp if r['hold'] >= MARKS[0]]):>5}{row}")
    print(f"    ⚠️ Each cell counts only trades STILL OPEN at that mark — a winner")
    print(f"       that closed at 4 min cannot inform where a live trade should be")
    print(f"       at 10. Cell n therefore SHRINKS across the row; read it with the")
    print(f"       reachability table below.")
    print(f"    A floor at WINNERS p10 admits 90% of historical winners by")
    print(f"    construction. Compare it against the losers' p50/p75/p90 rows:")
    print(f"    the floor only earns its place where those sit BELOW it.")

    # ── REACHABILITY FIRST ────────────────────────────────────────────────
    # ⚠️ A TIME-BASED RULE CAN ONLY TOUCH A TRADE THAT IS STILL OPEN AT THE MARK.
    # v1.0 omitted this and it was the single biggest error in the tool: with a
    # median loser hold of 4.0 min, most losers are gone before a 10m or 15m
    # rule exists. Print the reachable population BEFORE any threshold talk, so
    # the ceiling on what any rule can achieve is visible first.
    print(f"\n  ⚠️ REACHABILITY — how many trades are STILL OPEN at each mark?")
    print(f"    {'mark':>6}{'open':>7}{'of':>5}{'losers':>8}{'winners':>9}"
          f"{'loser $ at risk':>17}")
    for m in MARKS:
        elig = [r for r in recs if r["hold"] >= m]
        el = [r for r in elig if r["pnl"] <= 0]
        ew = [r for r in elig if r["pnl"] > 0]
        print(f"    {m:>5}m{len(elig):>7}{len(recs):>5}{len(el):>8}{len(ew):>9}"
              f"{-sum(r['pnl'] for r in el):>17,.0f}")
    unreachable = [r for r in recs if r["pnl"] <= 0 and r["hold"] < MARKS[0]]
    if unreachable:
        print(f"    {len(unreachable)} loser(s) closed before {MARKS[0]}m "
              f"(${-sum(r['pnl'] for r in unreachable):,.0f}) — NO time rule "
              f"reaches these.")

    # ── THE DECIDING NUMBER ────────────────────────────────────────────────
    # A cut only pays if trades below the threshold RARELY win. Separation of
    # medians is not enough — the false-positive rate is what costs money.
    print(f"\n  IF WE CUT AT <X% PROGRESS BY N MINUTES — among trades STILL OPEN")
    print(f"    {'mark':>6}{'thresh':>8}{'cut':>6}{'losers':>8}{'WINNERS':>9}"
          f"{'$≤bound':>10}{'$forgone':>10}{'recov':>7}")
    for m in MARKS:
        for thr in (10, 25, 40):
            cut = [r for r in recs if r["hold"] >= m          # <- v1.1 GATE
                   and r["prog"][m] is not None and r["prog"][m] < thr]
            if not cut:
                continue
            cl = [r for r in cut if r["pnl"] <= 0]
            cw = [r for r in cut if r["pnl"] > 0]
            # RECOVERABLE = the worst premium came AFTER the mark, so there was
            # still something left to save. If the low was already in, cutting
            # at the mark recovers nothing — the damage is done.
            rec_n = sum(1 for r in cl if r.get("low_after_mark", {}).get(m))
            print(f"    {m:>5}m{thr:>7}%{len(cut):>6}{len(cl):>8}{len(cw):>9}"
                  f"{-sum(r['pnl'] for r in cl):>10,.0f}"
                  f"{sum(r['pnl'] for r in cw):>10,.0f}"
                  f"{rec_n:>6}/{len(cl)}")
    print("    ⚠️ $≤bound is an UPPER BOUND, not a saving. It is the FULL realized")
    print("       loss of the cut trades — i.e. it assumes cutting at the mark")
    print("       recovers everything, which it cannot: the trade is already down")
    print("       at that moment. The per-trade premium SERIES needed for an exact")
    print("       figure is not in the trade DB; only max/min and their times are.")
    print("    recov = of the cut losers, how many had their WORST premium AFTER")
    print("       the mark. Only those have anything left to save. The rest were")
    print("       already at their low when the rule would have fired.")
    print("    ⚠️ WINNERS > 0 in a row is the whole argument against that threshold.")

    # ── CONFOUND: direction ────────────────────────────────────────────────
    print(f"\n  ⚠️ CONFOUND CHECK — is this a PROGRESS rule or a DIRECTION rule?")
    for d in ("short", "long"):
        g = [r for r in recs if r["dir"] == d]
        if not g:
            print(f"    {d:6} n=0 — cannot separate; a progress rule fitted here"
                  f" would be a {('long' if d == 'short' else 'short')} rule")
            continue
        gw = [r for r in g if r["pnl"] > 0]
        print(f"    {d:6} n={len(g):<4} win {100.0*len(gw)/len(g):>3.0f}%"
              f"  net ${sum(r['pnl'] for r in g):>+9,.0f}"
              f"  median progress@5m {fmt(med([r['prog'][5] for r in g]))}")

    # ── EXIT MECHANISM ─────────────────────────────────────────────────────
    print(f"\n  WHICH MECHANISM CLOSED THE LOSERS")
    by = {}
    for r in los:
        by.setdefault(r["exit"], []).append(r)
    for k, g in sorted(by.items(), key=lambda kv: sum(x["pnl"] for x in kv[1])):
        print(f"    {k[:34]:36}n={len(g):<4} net ${sum(x['pnl'] for x in g):>+9,.0f}"
              f"  median pnl {med([x['pnl_pct'] for x in g]):>6.1f}%"
              f"  hold {med([x['hold'] for x in g]):>5.1f}m")

    print(f"\n  ── VERDICT ──")
    if len(win) < MIN_N or len(los) < MIN_N:
        print(f"    UNDERPOWERED — winners {len(win)}, losers {len(los)}, floor"
              f" {MIN_N} each. This is an ABSENT MEASUREMENT, not a null.")
        print(f"    Do not fit a threshold to it. Add sessions with --since.")
    else:
        print(f"    Sample clears the floor. Read the WINNERS column in the cut")
        print(f"    table: the cheapest threshold with ZERO winners caught is the")
        print(f"    only one that is safe to ship as a hard cut. If every")
        print(f"    threshold catches winners, the rule wants to be a WARNING or")
        print(f"    a size reduction, not an exit.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
