#!/usr/bin/env python3
"""
tests/velocity_feasibility.py — v1.0 — 2026-08-12

CAN THIS TRADE PAY, AT THIS VELOCITY, IN THE TIME THAT IS LEFT?

⚠️ THIS IS THE FIRST TOOL TO READ THE CHAIN ARCHIVE. `chain_snapshot.py` has
been writing full 0DTE chains with delta, gamma, theta and vega at a 5-minute
cadence since 2026-07-23 and, until now, nothing had ever read them. Everything
here comes from data already on disk; nothing new is collected.

────────────────────────────────────────────────────────────────────────────
THE IDEA, and why it is different from every stop currently in the engine
────────────────────────────────────────────────────────────────────────────
Every existing exit is BACKWARD-LOOKING. `orb_structure_stop` asks "did the
setup break?". `_theta_bleed` asks "am I protecting a gain?". The hard floor
asks "how much have I lost?". **None of them asks whether the trade can still
work** — which is the only question that determines whether holding is rational.

On a LONG 0DTE option, "going in our favour" does not mean the underlying moved
our way. It means it moved our way FASTER THAN THETA TOOK IT BACK. Those come
apart constantly, and the gap is exactly what the 2026-08-12 QQQ trade was:
**44% of the way to its target and down 42.2%.**

Two velocities, both computable from the archive, neither of them fitted:

  BREAKEVEN VELOCITY  bev = |theta| / (|delta| * 1440)
      underlying points per MINUTE at which delta gains exactly offset decay.
      Below it the position BLEEDS EVEN WHILE THE THESIS IS INTACT. It is the
      option's own physics at that strike at that moment — not a threshold
      anyone chose. (theta is $/share/CALENDAR day; 1440 min/day.)

  REQUIRED VELOCITY   req = |target - underlying| / minutes_to_expiry
      the pace needed to actually reach the target before the contract dies.

  FEASIBILITY RATIO   req / bev
      **BELOW ~1 THE TRADE CANNOT PAY EVEN IF IT WORKS PERFECTLY** — reaching
      its own target would cover theta and nothing else. That is arithmetic, not
      a threshold. The only judgement is how much margin above 1 to demand.

SANDBOX CASE STUDY THAT MOTIVATED THIS (2026-08-12, synthetic Greeks solved from
the observed entry premium, validated against observed max/min):
    AVGO winner  delivered 1.28 pts/min against bev 0.0130  ->  **98x**
    QQQ  bleeder delivered 0.11 pts/min against bev 0.0091  ->   12x at 1 min,
                 then CUMULATIVELY NEGATIVE by minute 11 — with 59 minutes still
                 to run and no mechanism watching.
    And QQQ's req (0.0072-0.0115) was essentially EQUAL to its bev
    (0.0084-0.0108): **it was structurally marginal the moment it was placed.**

────────────────────────────────────────────────────────────────────────────
WHAT THIS TOOL ANSWERS — two separable questions
────────────────────────────────────────────────────────────────────────────
  (A) ENTRY FILTER. Does the feasibility ratio AT ENTRY separate winners from
      losers? An entry gate is strictly better than a stop here: declining
      forfeits an option, whereas a stop that fires wrongly REALISES a loss. It
      also has no whipsaw — one evaluation, one answer.
  (B) STOP. Among trades still open at each mark, does DELIVERED velocity
      relative to breakeven separate? ⚠️ Must be CUMULATIVE, never
      instantaneous: QQQ flipped back above breakeven at minutes 41-61 before
      dying at 70. A per-tick rule oscillates; the cumulative form is also what
      supplies the "room to breathe".

⚠️ LIMITS, stated so the output is not over-read:
  - The archive cadence is 5 MINUTES. Entry Greeks are the nearest snapshot AT
    OR BEFORE entry, so they can be up to 5 min stale. The staleness is printed.
  - Chains are archived only for boxes that were AWAKE and only since 07-23.
  - ORB carries an explicit measured-move target (range boundary +/- range
    height), so `req` is well defined. Continuation and sweep DO NOT — this
    tool restricts itself to strategies with a real target and says so.
  - Gamma cuts both ways: a fast move grows delta and LOWERS the requirement,
    which is how some trades recover from nowhere. A linear projection would cut
    those, so gamma is reported alongside rather than ignored.

READ-ONLY. stdlib only. Touches no fleet, no live path, writes nothing.

USAGE (control)
    python3 tests/velocity_feasibility.py --since 2026-07-23
    python3 tests/velocity_feasibility.py 2026-08-12 --verbose
"""

import argparse
import csv
import datetime as dt
import glob
import gzip
import json
import os
import sqlite3
import sys

DTP = os.path.expanduser("~/day_trader_pro")
TRADES = os.path.join(DTP, "trades")
CHAINS = os.path.join(DTP, "chain_snapshots")
OHLC = os.path.join(DTP, "ohlc")
MARKS = (5, 10, 15, 20)
ARCHIVE_START = "2026-07-23"          # chain_snapshot.py v1.0 ship date


def _iso(s):
    try:
        d = dt.datetime.fromisoformat(str(s))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:                                          # noqa: BLE001
        return None


def load_chain_day(sym, date):
    """[(ts, underlying, {(type,strike): row})] — multi-member gzip, one JSON
    object per line. Written with mode 'ab' so each line is its own member."""
    path = os.path.join(CHAINS, date, f"{sym}.jsonl.gz")
    if not os.path.isfile(path):
        return []
    out = []
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:                              # noqa: BLE001
                    continue
                ts = _iso(r.get("ts_et"))
                if ts is None:
                    continue
                idx = {}
                for c in (r.get("contracts") or []):
                    try:
                        idx[(str(c.get("type", "")).lower()[:1],
                             round(float(c.get("strike") or 0), 4))] = c
                    except Exception:                          # noqa: BLE001
                        continue
                out.append((ts, r.get("underlying"), idx))
    except Exception as exc:                                   # noqa: BLE001
        print(f"    ⚠️ {sym} {date}: unreadable archive ({exc})")
        return []
    out.sort(key=lambda x: x[0])
    return out


def greeks_at(chain_day, when, side, strike):
    """Nearest snapshot AT OR BEFORE `when`. Returns (row, staleness_min)."""
    best = None
    for ts, _u, idx in chain_day:
        if ts <= when:
            best = (ts, idx)
        else:
            break
    if best is None:
        return None, None
    row = best[1].get((side[:1].lower(), round(float(strike), 4)))
    if row is None:
        return None, None
    return row, (when - best[0]).total_seconds() / 60.0


def load_trades(date):
    out = []
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
            # ⚠️ ONLY strategies with a REAL measured-move target. `req` is
            # meaningless without one, and inventing a proxy here would make the
            # ratio a statement about the proxy.
            if "ORB" not in str(d.get("setup_type") or ""):
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
                bars.append((t, float(r["close"])))
            except Exception:                                  # noqa: BLE001
                continue
    return bars or None


def expiry_utc(date, sym):
    """0DTE cash close. SPX/index settle 16:15 ET; equities and ETFs 16:00."""
    et = dt.timezone(dt.timedelta(hours=-4))
    hh, mm = (16, 15) if sym.upper() in ("SPX", "_SPX", "XSP") else (16, 0)
    y, m, d = (int(x) for x in date.split("-"))
    return dt.datetime(y, m, d, hh, mm, tzinfo=et).astimezone(dt.timezone.utc)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("dates", nargs="*")
    ap.add_argument("--since", default="")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(argv[1:])

    if a.since:
        lo = max(a.since, ARCHIVE_START)
        dates = sorted(d for d in os.listdir(TRADES) if len(d) == 10 and d >= lo)
    elif a.dates:
        dates = [d for d in a.dates if d >= ARCHIVE_START]
        if not dates:
            print(f"no dates at/after the archive start {ARCHIVE_START}")
            return 1
    else:
        print("usage: velocity_feasibility.py <date> | --since <date>")
        return 1

    recs, no_chain, no_greek = [], 0, 0
    for date in dates:
        chains, tapes = {}, {}
        for t in load_trades(date):
            sym = t.get("symbol")
            if sym not in chains:
                chains[sym] = load_chain_day(sym, date)
                tapes[sym] = load_tape(sym, date)
            if not chains[sym]:
                no_chain += 1
                continue
            t0, t1 = _iso(t.get("entry_time")), _iso(t.get("exit_time"))
            try:
                und_e = float(t.get("underlying_entry") or 0)
                tgt = float(t.get("underlying_target") or 0)
                strike = float(t.get("strike") or 0)
            except Exception:                                  # noqa: BLE001
                continue
            side = str(t.get("option_side") or "")
            if not (t0 and t1 and und_e > 0 and tgt > 0 and strike > 0 and side):
                continue
            row, stale = greeks_at(chains[sym], t0, side, strike)
            if not row:
                no_greek += 1
                continue
            try:
                delta = abs(float(row.get("delta") or 0))
                theta = abs(float(row.get("theta") or 0))
                gamma = float(row.get("gamma") or 0)
                iv = float(row.get("iv") or 0)
            except Exception:                                  # noqa: BLE001
                continue
            if delta <= 1e-6 or theta <= 0:
                no_greek += 1
                continue
            exp = expiry_utc(date, sym)
            mins_left = max((exp - t0).total_seconds() / 60.0, 1e-9)
            bev = theta / (delta * 1440.0)
            req = abs(tgt - und_e) / mins_left
            bars = tapes.get(sym) or []
            short = str(t.get("direction") or "") == "short"

            def delivered(mark):
                """CUMULATIVE pace toward target at `mark` minutes.
                ⚠️ Cumulative, never instantaneous — QQQ crossed back above
                breakeven at 41-61 min before dying at 70, so a per-tick rule
                oscillates. Cumulative is also what gives room to breathe."""
                w = [b for b in bars if t0 <= b[0] <= t0 + dt.timedelta(minutes=mark)]
                if not w:
                    return None
                trav = (und_e - w[-1][1]) if short else (w[-1][1] - und_e)
                return trav / mark

            recs.append({
                "date": date, "sym": sym, "pnl": float(t.get("pnl_usd") or 0),
                "hold": (t1 - t0).total_seconds() / 60.0,
                "bev": bev, "req": req, "ratio": req / bev if bev > 0 else None,
                "delta": delta, "theta": theta, "gamma": gamma, "iv": iv,
                "stale": stale, "mins_left": mins_left,
                "deliv": {m: delivered(m) for m in MARKS},
                "exit": str(t.get("exit_reason") or "").split(":")[0].split(" pnl")[0],
            })

    if not recs:
        print("no ORB trades with usable chain Greeks in range")
        print(f"  (archive starts {ARCHIVE_START}; {no_chain} without a chain file,"
              f" {no_greek} without the traded strike in the snapshot)")
        return 1

    win = [r for r in recs if r["pnl"] > 0]
    los = [r for r in recs if r["pnl"] <= 0]

    def pct(v, q):
        v = sorted(x for x in v if x is not None)
        return v[min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))] if v else None

    def f(v, d=2):
        return f"{v:>8.{d}f}" if v is not None else "       —"

    print("=" * 78)
    print(f"  VELOCITY FEASIBILITY — {len(dates)} session(s), {len(recs)} ORB trade(s)"
          f"   winners {len(win)}  losers {len(los)}")
    print(f"  chain archive: {CHAINS}")
    if no_chain or no_greek:
        print(f"  ⚠️ skipped: {no_chain} no chain file, {no_greek} strike absent"
              f" from the snapshot")
    st = [r["stale"] for r in recs if r["stale"] is not None]
    if st:
        print(f"  entry-Greek staleness: median {pct(st,.5):.1f} min,"
              f" p90 {pct(st,.9):.1f} min (archive cadence is 5 min)")
    print("=" * 78)

    # ── (A) THE ENTRY FILTER ───────────────────────────────────────────────
    print(f"\n  (A) FEASIBILITY RATIO AT ENTRY   req / bev")
    print(f"      < 1.0 means reaching the target would cover theta AND NOTHING"
          f" ELSE.")
    print(f"      {'':10}{'n':>5}{'p10':>9}{'p25':>9}{'p50':>9}{'p75':>9}{'p90':>9}")
    for name, g in (("winners", win), ("losers", los)):
        print(f"      {name:10}{len(g):>5}" +
              "".join(f(pct([r["ratio"] for r in g], q))
                      for q in (.10, .25, .50, .75, .90)))
    print(f"\n      IF WE REFUSED ENTRIES BELOW A RATIO OF X:")
    print(f"      {'X':>6}{'blocked':>9}{'losers':>8}{'WINNERS':>9}"
          f"{'$avoided':>11}{'$forgone':>11}")
    for x in (0.5, 0.75, 1.0, 1.5, 2.0, 3.0):
        b = [r for r in recs if r["ratio"] is not None and r["ratio"] < x]
        if not b:
            continue
        bl = [r for r in b if r["pnl"] <= 0]
        bw = [r for r in b if r["pnl"] > 0]
        print(f"      {x:>6.2f}{len(b):>9}{len(bl):>8}{len(bw):>9}"
              f"{-sum(r['pnl'] for r in bl):>11,.0f}"
              f"{sum(r['pnl'] for r in bw):>11,.0f}")
    print(f"      ⚠️ An entry filter is CLEAN in a way a stop is not: $forgone is")
    print(f"         an opportunity cost, while a wrong stop REALISES a loss.")

    # ── (B) THE STOP ───────────────────────────────────────────────────────
    print(f"\n  (B) CUMULATIVE DELIVERED VELOCITY / BREAKEVEN, among trades"
          f" STILL OPEN")
    print(f"      {'mark':>6}{'':4}{'n':>5}{'win p10':>10}{'win p50':>10}"
          f"{'los p50':>10}{'los p90':>10}")
    for m in MARKS:
        w = [r for r in win if r["hold"] >= m and r["deliv"][m] is not None]
        l = [r for r in los if r["hold"] >= m and r["deliv"][m] is not None]
        rw = [r["deliv"][m] / r["bev"] for r in w if r["bev"] > 0]
        rl = [r["deliv"][m] / r["bev"] for r in l if r["bev"] > 0]
        print(f"      {m:>5}m{'':4}{len(w)+len(l):>5}"
              + f(pct(rw, .10), 1) + f(pct(rw, .50), 1)
              + f(pct(rl, .50), 1) + f(pct(rl, .90), 1))
    print(f"      A floor at winners p10 admits 90% of winners BY CONSTRUCTION.")
    print(f"      It earns its place only where the losers' p50/p90 sit BELOW it.")

    # ── CONTEXT ────────────────────────────────────────────────────────────
    print(f"\n  GREEKS AT ENTRY (medians)")
    for name, g in (("winners", win), ("losers", los)):
        if not g:
            print(f"      {name:10}n=0 — no rows; cannot compare Greeks")
            continue
        d_, th_, ga_, iv_, ml_ = (pct([r[k] for r in g], .5) for k in
                                  ("delta", "theta", "gamma", "iv", "mins_left"))
        print(f"      {name:10}n={len(g):<4} delta {d_:.3f}  theta {th_:.3f}"
              f"  gamma {ga_:.5f}"
              f"  iv {(iv_*100 if iv_ is not None else float('nan')):.1f}%"
              f"  mins to expiry {ml_:.0f}")
    print(f"      ⚠️ GAMMA CUTS BOTH WAYS: a fast move grows delta and LOWERS the")
    print(f"         requirement, which is how a trade recovers from nowhere. A")
    print(f"         linear projection would cut those — read gamma before")
    print(f"         hardening any threshold.")

    if a.verbose:
        print(f"\n  PER-TRADE")
        print(f"      {'date':11}{'sym':6}{'ratio':>7}{'bev':>9}{'req':>9}"
              f"{'hold':>7}{'pnl':>9}  exit")
        for r in sorted(recs, key=lambda x: (x["ratio"] is None, x["ratio"])):
            print(f"      {r['date']:11}{r['sym']:6}"
                  f"{(r['ratio'] if r['ratio'] is not None else 0):>7.2f}"
                  f"{r['bev']:>9.4f}{r['req']:>9.4f}{r['hold']:>7.1f}"
                  f"{r['pnl']:>+9,.0f}  {r['exit'][:26]}")

    print(f"\n  ── VERDICT ──")
    if len(win) < 8 or len(los) < 8:
        print(f"    UNDERPOWERED — winners {len(win)}, losers {len(los)}."
              f" ABSENT MEASUREMENT, not a null. Widen with --since.")
    else:
        print(f"    Read (A) first. If the ratio separates at entry, prefer the")
        print(f"    ENTRY FILTER — it forfeits an option instead of realising a")
        print(f"    loss, and needs no cumulative tracking or whipsaw handling.")
        print(f"    Use (B) only for what the filter cannot reach.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
