#!/usr/bin/env python3
"""
tests/retreat_probe.py — v1.0 — 2026-08-15   (LIQ.5)

HOW OFTEN IS A NAMED LEVEL ACTUALLY TESTED AND DEFENDED IN A SESSION?

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python tests/retreat_probe.py

────────────────────────────────────────────────────────────────────────────
WHY THIS EXISTS
────────────────────────────────────────────────────────────────────────────
The operator's sizing rule — **size scales with previous touches by a
consistent multiple** — is sound and CANNOT RUN on the field that exists.
`touch_count` reads **1 on 44,450 of 44,890 ticks (99%)** because it is never
incremented: named pools hardcode `touch_count=1` (`liquidity_mapper:461`) and
only equal-high/low CLUSTERS carry a real count. A PDH reads 1 forever no
matter how many times price came back to it.

That is the same failure shape as the condor's constant conviction and SWP.3's
approach weight: **a score with no variation cannot drive anything.**

**THE MAPPER IS NOT CHANGED** (operator's call). It stays the level-finder; the
retreat count is computed ALONGSIDE it.

────────────────────────────────────────────────────────────────────────────
THE DEFINITION, AND WHY IT MATCHES THE REST OF THE SYSTEM
────────────────────────────────────────────────────────────────────────────
*"A level is a zone, not a fixed number."* A RETREAT is:

    a wick reaching WITHIN 0.2% of the level, and a body closing back inside.

0.2% is not a new number — it is `within_pct(..., 0.002)`, the tolerance the
mapper's own dedupe already uses to decide two prices are the same level. One
definition of a zone, not two.

⚠️ **A RETREAT AND A SWEEP ARE THE SAME EVENT AT DIFFERENT DEPTHS** —
reach-and-reject vs breach-and-reject. So the retreat count is the level's
DEFENCE RECORD, and a sweep that eventually fires inherits it as size.

⚠️ **WICKS AND BODIES (operator's standing rule).** The wick is the test; the
close is the decision. A bar whose body closes BEYOND the level is not a
retreat — that is acceptance, and it ENDS the level rather than defending it.

────────────────────────────────────────────────────────────────────────────
WHERE THE LEVELS COME FROM — AND WHY NOT RECOMPUTED
────────────────────────────────────────────────────────────────────────────
The level prices are harvested from the replay tick logs
(`breakdown.SWEEP_REVERSAL.pool_price` + `named`), i.e. **from the mapper's own
output**. They are NOT re-derived here. Re-deriving PDH/PDL would create a
second lineage of level-finding, which is the failure WORKING_AGREEMENT 7
forbids and which cost this project a 774-line duplicate two days ago.

⚠️ CONSEQUENCE, STATED: this only sees levels the mapper NAMED AND SWEPT at
least once in that session. A level defended all day and never breached is
invisible here. **So these counts are a FLOOR, not a census.**

⚠️ DEFAULTS TO 2026-08-12 ONWARD. LIQ.1 (London/Asia removed as sweepable
pools) took effect 08-12 — 08-11 still shows 3,013 London-named sweeps, and
mixing the two regimes makes the numbers incomparable.
"""

import argparse
import collections
import csv
import glob
import json
import os
import re
import sys

REPORTS = os.path.expanduser("~/day_trader_pro/reports")
OHLC_ROOTS = ("~/day_trader_pro/ohlc", "~/day_trader_pro/data/ohlc")
ZONE_PCT = 0.002          # same tolerance the mapper's dedupe uses


def session_bars(date, symbol):
    """[(minute, high, low, close)] from the archived OHLC, or []."""
    for root in OHLC_ROOTS:
        d = os.path.join(os.path.expanduser(root), date)
        if not os.path.isdir(d):
            continue
        pre = (symbol or "").upper() + "_"
        for fn in os.listdir(d):
            if not fn.upper().startswith(pre) or not fn.lower().endswith(".csv"):
                continue
            out = []
            try:
                with open(os.path.join(d, fn), encoding="utf-8") as fh:
                    for r in csv.DictReader(fh):
                        t = r.get("timestamp") or r.get("time") or ""
                        try:
                            out.append((int(t[11:13]) * 60 + int(t[14:16]),
                                        float(r["high"]), float(r["low"]),
                                        float(r["close"])))
                        except Exception:                      # noqa: BLE001
                            continue
            except Exception:                                  # noqa: BLE001
                continue
            if out:
                out.sort()
                return out
    return []


def count_retreats(bars, level, kind):
    """(retreats, acceptances) for one level over one session.

    A RETREAT: the wick reaches within ZONE_PCT of the level and the body closes
    back inside. Consecutive bars that stay in the zone count ONCE — a single
    approach that lingers is one test, not five.

    An ACCEPTANCE: a body closes beyond the level. It ends the level, so
    counting stops there — anything after is a different regime for that price.
    """
    band = abs(level) * ZONE_PCT
    retreats, in_test, acceptances = 0, False, 0
    for _m, hi, lo, close in bars:
        if kind == "high":
            reached = hi >= level - band
            accepted = close > level + band
            inside = close <= level
        else:
            reached = lo <= level + band
            accepted = close < level - band
            inside = close >= level
        if accepted:
            acceptances += 1
            break                      # the level is gone; stop counting
        if reached and inside:
            if not in_test:
                retreats += 1
                in_test = True
        elif not reached:
            in_test = False            # left the zone; the next approach is new
    return retreats, acceptances


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-08-12",
                    help="LIQ.1 took effect 08-12; earlier logs are contaminated")
    ap.add_argument("--reports", default=REPORTS)
    a = ap.parse_args(argv[1:])

    logs = sorted(f for f in glob.glob(os.path.join(a.reports,
                                                    "regime_replay_*.jsonl"))
                  if (re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(f))
                      and re.search(r"(\d{4}-\d{2}-\d{2})",
                                    os.path.basename(f)).group(1) >= a.since))
    if not logs:
        print(f"no tick log(s) at/after {a.since} in {a.reports}")
        print("  ABSENT MEASUREMENT, not a null.")
        return 1

    # harvest the mapper's OWN named levels — never recomputed here
    levels = collections.defaultdict(dict)     # (date, sym) -> {name: (price, kind)}
    for fp in logs:
        day = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(fp)).group(1)
        with open(fp) as f:
            for line in f:
                if '"named"' not in line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:                              # noqa: BLE001
                    continue
                b = (r.get("breakdown") or {}).get("SWEEP_REVERSAL") or {}
                name, px = b.get("named"), b.get("pool_price")
                if not name or not px:
                    continue
                kind = "high" if str(b.get("kind", "")).startswith("high") else "low"
                levels[(day, str(r.get("sym", "?")))][str(name)] = (float(px), kind)

    dist = collections.Counter()
    by_level = collections.defaultdict(list)
    rows, no_tape = [], 0

    for (day, sym), lv in sorted(levels.items()):
        bars = session_bars(day, sym)
        if not bars:
            no_tape += 1
            continue
        for name, (px, kind) in lv.items():
            n, acc = count_retreats(bars, px, kind)
            dist[n] += 1
            by_level[name].append(n)
            rows.append((day, sym, name, px, n, acc))

    print("=" * 80)
    print("RETREAT PROBE - how often is a named level tested and DEFENDED?")
    print(f"  {len(logs)} session(s) since {a.since}   "
          f"{len(rows)} level-session(s)"
          + (f"   ({no_tape} skipped: no OHLC)" if no_tape else ""))
    print(f"  a retreat = wick within {ZONE_PCT*100:.1f}% + body closing back inside")
    print("=" * 80)

    if not rows:
        print("\n  no level-sessions with tape. ABSENT MEASUREMENT, not a null.")
        return 0

    print("\n  RETREAT COUNT DISTRIBUTION   <- what a size multiple would read")
    tot = sum(dist.values())
    for n in sorted(dist):
        bar = "#" * min(40, int(40 * dist[n] / max(dist.values())))
        print(f"    {n:>3} retreat(s)  {dist[n]:>6,}  ({100.0*dist[n]/tot:4.1f}%)  {bar}")

    vals = sorted(x[4] for x in rows)
    p = lambda q: vals[min(len(vals) - 1, int(len(vals) * q))]
    print(f"\n  min={vals[0]}  p50={p(0.5)}  p90={p(0.9)}  max={vals[-1]}"
          f"  mean={sum(vals)/len(vals):.1f}")
    varies = sum(1 for v in vals if v != vals[0])
    print(f"  DOES IT VARY? {varies:,} of {len(vals):,} differ from the min "
          f"({100.0*varies/len(vals):.0f}%)"
          + ("  <- usable as a multiplier" if varies > len(vals) * 0.2
             else "  <- TOO CONSTANT, same trap as touch_count"))

    print("\n  BY LEVEL NAME")
    for name, v in sorted(by_level.items(), key=lambda x: -len(x[1]))[:10]:
        sv = sorted(v)
        print(f"    {name:<16} n={len(v):>5}  p50={sv[len(sv)//2]:>3}  "
              f"max={sv[-1]:>3}  mean={sum(v)/len(v):.1f}")

    print("\n  MOST-DEFENDED LEVEL-SESSIONS")
    for d, sym, name, px, n, acc in sorted(rows, key=lambda x: -x[4])[:10]:
        print(f"    {d}  {sym:<6} {name:<14} @{px:<10.2f} {n:>3} retreat(s)"
              + ("  (then accepted)" if acc else ""))

    print("\n  HOW TO READ IT")
    print("  · The DISTRIBUTION is what a size multiple would actually see. If it")
    print("    is concentrated on one value, the multiplier is decorative - the")
    print("    exact trap `touch_count` fell into.")
    print("  · Counts here are a FLOOR: only levels the mapper NAMED AND SWEPT at")
    print("    least once appear. A level defended all day and never breached is")
    print("    invisible.")
    print("  · A high p90 argues for a MODEST multiple. Six defences must not")
    print("    mean six times the risk.")
    print("\n  NOTHING IS PROPOSED HERE.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
