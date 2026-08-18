#!/usr/bin/env python3
"""
tests/trail_engage_sweep.py — v1.0 — 2026-08-12

WHY DOES A TRAIL NEVER ENGAGE ON MOST ORB TRADES, AND WHAT WOULD MOVING IT COST?

THE DEFECT, found 2026-08-12 by replaying the QQQ trade through the real exit
engine. `_update_fvg_trail` computes a floor every tick once the trade is up
FVG_TRAIL_ARM_PCT (0.20), then:

    current_trail = self._trail_stops.get(trade_id, entry_prem)   # SEEDS AT ENTRY
    if new_trail > current_trail:                                 # must BEAT entry
        self._trail_stops[trade_id] = new_trail

and with no FVG in frame the floor is `current_premium * FVG_TRAIL_LOCK_PCT`
(0.80). So the floor only beats the entry seed once

    peak_premium * 0.80 > entry_premium   =>   peak >= +25.0%

**There is a DEAD ZONE from +20% to +25%** where the trail arms, runs every
tick, computes a floor, and SILENTLY DISCARDS IT. A trade peaking in that band
has NO TRAIL AT ALL and rides to the structure stop or the -40% floor.

QQQ 2026-08-12 peaked at **+22.5%** — dead centre — and closed at **-42.2%**
after 70.5 minutes. On that session, ORB split exactly on the threshold:
below +25%, 11 trades / 0 winners / -$4,278; at or above, 6 trades / 6 winners
/ +$2,353. Every trade above it exited `orb_trail_stop`; not one below it did.

⚠️ THE SEED IS NOT ITSELF A BUG. Seeding at entry means the trail refuses to
lock in a LOSS, which is a deliberate and defensible rule. The defect is the
MISMATCH: arming at +20% while engaging at +25%.

────────────────────────────────────────────────────────────────────────────
WHAT THIS SWEEPS
────────────────────────────────────────────────────────────────────────────
  LOCK   — raise FVG_TRAIL_LOCK_PCT so the floor beats entry sooner.
           engage% = (1/LOCK - 1). 0.80 -> +25.0% · 0.90 -> +11.1% ·
           0.95 -> +5.3%. ⚠️ A higher lock is a TIGHTER leash on EVERY trade,
           including the winners that currently run — it does not only rescue
           the dead zone, and the cost lands on the trades that pay.
  SEED   — allow the trail to sit BELOW entry (operator's "let structure catch
           the rest"). This LOCKS A SMALL LOSS rather than none, and is the
           only way to protect a trade that peaks under +25%.

────────────────────────────────────────────────────────────────────────────
THE COUNTERFACTUAL, and its assumptions — read these before believing a number
────────────────────────────────────────────────────────────────────────────
The trail ratchets, so its final level is `max_premium_seen * LOCK`. A trade is
counted as trail-exited only when **min_premium_seen_at is AFTER
max_premium_seen_at** — i.e. the low genuinely came after the peak, so the
descent through the trail actually happened. That timestamp pair is the whole
reason this is answerable at all (trade_logger v3.9 added it 2026-08-04).
  ⚠️ ASSUMES a fill AT the trail level: no slippage, and no intra-tick spike
     through it. Paper books the mark, so this is consistent with how the book
     was recorded, but live fills are a limit at the mark that may not fill.
  ⚠️ IGNORES the separate % trail at TRAIL_ACTIVATION_PCT and the FVG anchor
     itself — an actual FVG in frame can set a floor HIGHER than the pct floor,
     so real engagement can be earlier than modelled. This sweep is therefore
     CONSERVATIVE about how often a trail would have engaged.
  ⚠️ IGNORES path between the recorded extremes. Only four premium points per
     trade exist; there is no series.

READ-ONLY. stdlib only. Touches no fleet, no live path, writes nothing.

USAGE (control)
    python3 tests/trail_engage_sweep.py --since 2026-07-01
    python3 tests/trail_engage_sweep.py 2026-08-12 --verbose
"""

import argparse
import collections
import datetime as dt
import glob
import os
import sqlite3
import sys

TRADES = os.path.expanduser("~/day_trader_pro/trades")
LOCK_NOW = 0.80
ARM_NOW = 0.20


def _iso(s):
    try:
        d = dt.datetime.fromisoformat(str(s))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:                                          # noqa: BLE001
        return None


def load(dates, strategy_filter):
    out = []
    for date in dates:
        for path in sorted(glob.glob(os.path.join(TRADES, date, "*_trades_*.db"))):
            try:
                conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
                conn.row_factory = sqlite3.Row
                rows = [dict(r) for r in conn.execute("SELECT * FROM trades")]
                conn.close()
            except Exception:                                  # noqa: BLE001
                continue
            for d in rows:
                if str(d.get("status") or "") != "closed":
                    continue
                st = str(d.get("setup_type") or "")
                if strategy_filter and strategy_filter not in st:
                    continue
                try:
                    e = float(d.get("entry_premium") or 0)
                    mx = float(d.get("max_premium_seen") or 0) or e
                    mn = float(d.get("min_premium_seen") or 0) or e
                    n = int(float(d.get("contracts") or 0))
                    pnl = float(d.get("pnl_usd") or 0)
                except Exception:                              # noqa: BLE001
                    continue
                if e <= 0 or n <= 0:
                    continue
                out.append({
                    "date": date, "sym": d.get("symbol"), "entry": e,
                    "max": mx, "min": mn, "n": n, "pnl": pnl,
                    "peak_pct": (mx - e) / e * 100.0,
                    "trough_pct": (mn - e) / e * 100.0,
                    "max_at": _iso(d.get("max_premium_seen_at")),
                    "min_at": _iso(d.get("min_premium_seen_at")),
                    "exit": str(d.get("exit_reason") or "").split(" pnl")[0],
                })
    return out


def counterfactual(r, lock, allow_below_entry):
    """P&L if the trail engaged with this lock. None => unchanged (no trail)."""
    seed = 0.0 if allow_below_entry else r["entry"]
    trail = r["max"] * lock
    if trail <= seed:
        return None                       # never engages; outcome unchanged
    if r["max_at"] is None or r["min_at"] is None:
        return None                       # cannot prove the low came after
    if r["min_at"] <= r["max_at"]:
        return None                       # low came FIRST — no descent through
    if r["min"] >= trail:
        return None                       # never fell to the trail
    return (trail - r["entry"]) * r["n"] * 100.0


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("dates", nargs="*")
    ap.add_argument("--since", default="")
    ap.add_argument("--setup", default="ORB")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(argv[1:])

    if a.since:
        dates = sorted(d for d in os.listdir(TRADES) if len(d) == 10 and d >= a.since)
    elif a.dates:
        dates = a.dates
    else:
        print("usage: trail_engage_sweep.py <date> | --since <date>")
        return 1

    rows = load(dates, a.setup)
    if not rows:
        print(f"no closed {a.setup} trades in range")
        return 1
    have_ts = [r for r in rows if r["max_at"] and r["min_at"]]

    print("=" * 78)
    print(f"  TRAIL ENGAGE SWEEP — {a.setup or 'ALL'} — {len(dates)} session(s),"
          f" {len(rows)} trade(s), net ${sum(r['pnl'] for r in rows):+,.0f}")
    print(f"  MFE/MAE timestamps present on {len(have_ts)}/{len(rows)}"
          f" — only these can be counterfactualled")
    print(f"  today: ARM {ARM_NOW*100:.0f}%, LOCK {LOCK_NOW}"
          f"  => a trail engages only above +{(1/LOCK_NOW-1)*100:.1f}%")
    print("=" * 78)

    print(f"\n  OUTCOME BY PEAK PREMIUM  (does the threshold divide the book?)")
    print(f"    {'band':20}{'n':>5}{'win%':>7}{'net$':>11}{'trail exits':>13}")
    bands = [(-1e9, 0, "never green"), (0, 10, "0 to +10%"),
             (10, 20, "+10 to +20%"), (20, 25, "+20 to +25%  DEAD"),
             (25, 50, "+25 to +50%"), (50, 1e9, ">+50%")]
    for lo, hi, lab in bands:
        g = [r for r in rows if lo <= r["peak_pct"] < hi]
        if not g:
            continue
        w = sum(1 for r in g if r["pnl"] > 0)
        t = sum(1 for r in g if "trail" in r["exit"])
        print(f"    {lab:20}{len(g):>5}{100.0*w/len(g):>6.0f}%"
              f"{sum(r['pnl'] for r in g):>11,.0f}{t:>9}/{len(g)}")

    print(f"\n  (A) RAISE THE LOCK — tighter leash on EVERY trade")
    print(f"    {'LOCK':>6}{'engages >':>11}{'n changed':>11}{'delta $':>11}"
          f"{'helped':>8}{'HURT':>7}")
    for lock in (0.80, 0.85, 0.90, 0.925, 0.95):
        deltas = []
        for r in have_ts:
            cf = counterfactual(r, lock, allow_below_entry=False)
            if cf is not None and abs(cf - r["pnl"]) > 1e-6:
                deltas.append(cf - r["pnl"])
        if not deltas:
            print(f"    {lock:>6.2f}{(1/lock-1)*100:>10.1f}%{0:>11}{0:>11}"
                  f"{0:>8}{0:>7}")
            continue
        print(f"    {lock:>6.2f}{(1/lock-1)*100:>10.1f}%{len(deltas):>11}"
              f"{sum(deltas):>11,.0f}{sum(1 for d in deltas if d>0):>8}"
              f"{sum(1 for d in deltas if d<0):>7}")

    print(f"\n  (B) LET THE TRAIL SIT BELOW ENTRY — locks a small loss, structure backstops")
    print(f"    {'LOCK':>6}{'n changed':>11}{'delta $':>11}{'helped':>8}{'HURT':>7}")
    for lock in (0.80, 0.85, 0.90, 0.95):
        deltas = []
        for r in have_ts:
            cf = counterfactual(r, lock, allow_below_entry=True)
            if cf is not None and abs(cf - r["pnl"]) > 1e-6:
                deltas.append(cf - r["pnl"])
        if not deltas:
            continue
        print(f"    {lock:>6.2f}{len(deltas):>11}{sum(deltas):>11,.0f}"
              f"{sum(1 for d in deltas if d>0):>8}{sum(1 for d in deltas if d<0):>7}")

    print(f"\n    ⚠️ HURT is the column that decides this. A tighter leash cuts the")
    print(f"       trades that currently RUN — the few that carry the book. If")
    print(f"       HURT rises faster than helped, the fix costs more than the")
    print(f"       defect. And every number here assumes a fill AT the trail")
    print(f"       level with no slippage; live posts a limit at the mark.")

    if a.verbose:
        print(f"\n  DEAD-ZONE TRADES (+20% to +25% peak) — the population a fix rescues")
        dz = [r for r in rows if 20 <= r["peak_pct"] < 25]
        if not dz:
            print("    none in range")
        for r in sorted(dz, key=lambda x: x["pnl"]):
            print(f"    {r['date']:11}{r['sym']:6} peak {r['peak_pct']:>+6.1f}%"
                  f"  trough {r['trough_pct']:>+7.1f}%  pnl ${r['pnl']:>+8,.0f}"
                  f"  {r['exit'][:30]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
