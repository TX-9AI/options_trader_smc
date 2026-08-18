#!/usr/bin/env python3
"""
tests/flicker_audit.py — v1.0 — 2026-08-03

ARE WE BEING PECKED AWAY BY REGIME FLICKER? Operator's symptom, 2026-08-03:
*"indescribable short hold times with virtually no PnL gained or lost."*

THAT SYMPTOM HAS A SPECIFIC SIGNATURE and this measures it directly.

WHY IT IS PLAUSIBLE — the exit is more sensitive than the entry
    `exit_engine` checks regime-flip SECOND, after only the 15:45 hard close and
    BEFORE break-of-structure or any premium stop. The test is strict: a long
    survives only while "TRENDING_BULL" is in the regime string, a short only on
    "TRENDING_BEAR". **Anything else exits** — RANGING, COMPRESSION, BREAKOUT,
    SWEEP_REVERSAL, or a flip to the opposite trend. The comment is explicit that
    the trade is defined by the trend, so a dead thesis exits regardless of P&L.
    So one tick of label wobble closes the position. A trade opened and closed
    inside a few minutes at ~$0 is exactly what that produces, and continuation is
    the most regime-coupled strategy in the fleet (-$2,024 at 46% WR).

WHAT THIS DOES NOT ASSUME
    A regime-flip exit is not automatically wrong. Sometimes the trend really did
    die and the exit saved money. The distinguishing evidence is the JOINT
    distribution: **short hold AND near-zero P&L AND exit_reason=regime_flip**.
    A flip exit after 40 minutes with a real loss is the mechanism working. A
    cluster at 2-5 minutes and ±$20 is the mechanism firing on noise.
    So this reports hold-time and |P&L| distributions PER EXIT REASON, and the
    comparison between regime_flip and everything else is the finding — not the
    count of flip exits on its own.

THE CONTEXT THAT MAKES A FIX NON-OBVIOUS
    The L2 conviction integrator ALREADY debounces: 436 committed label switches
    against 695 L1-argmax flips, churn crushed 1.6x. So flicker suppression exists
    and the question is whether it is sufficient, not whether to begin.
    And the integrator computes a `stale` flag — set on every data gap, on
    restart, and while conviction decays on tau_stale — which it journals every
    tick. Grepping main.py and exit_engine.py for it returns NOTHING. **The engine
    knows it is operating on degraded evidence, records that, and the exit path
    never reads it.** Same shape as AlertManager._send discarding a boolean that
    already existed.
    That distinction matters for what a fix should be: adding HYSTERESIS is a new
    parameter on §10's overfitting surface, on an EXIT, where being wrong costs
    capital rather than opportunity. **Not acting on a label already flagged
    unreliable is not hysteresis at all** — it is the same principle as the
    blindness watch, one layer up.

READ THE JOINT CELL, NOT THE HEADLINE COUNT.

USAGE (single line, control box, repo root)
    python3 tests/flicker_audit.py
    python3 tests/flicker_audit.py --strategy ContinuationStrategy --since 2026-07-23

Read-only. Reads reports/fleet_trades_*.json. Changes nothing.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re
import sys

TRADES_GLOB = "~/day_trader_pro/reports/fleet_trades_*.json"
DATE_RE = re.compile(r"(20\d\d-\d\d-\d\d)")
# First session after the mark-limit execution change; before it, fills came from
# a different path and hold times are not comparable. Same cutoff gap_outcome_join
# defaults to, and for the same reason.
CONFOUND_CUTOFF = "2026-07-23"
SHORT_HOLD_MIN = 10.0       # "indescribably short"
FLAT_PNL_USD = 25.0         # "virtually no PnL gained or lost"


def _num(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _minutes(t0, t1):
    """Hold time in minutes from two ISO-ish stamps, or None if unparseable.
    Returns None rather than 0 on failure — a silent 0 would land in the
    short-hold bucket and manufacture the very finding being tested."""
    if not t0 or not t1:
        return None
    def _p(x):
        m = re.search(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2}):(\d{2})", str(x))
        if not m:
            return None
        from datetime import datetime
        return datetime(int(m.group(1)[:4]), int(m.group(1)[5:7]), int(m.group(1)[8:10]),
                        int(m.group(2)), int(m.group(3)), int(m.group(4)))
    a, b = _p(t0), _p(t1)
    if a is None or b is None:
        return None
    return (b - a).total_seconds() / 60.0


def _pcts(xs, ps=(25, 50, 75, 90)):
    if not xs:
        return {}
    s = sorted(xs)
    return {p: s[min(len(s) - 1, int(round(p / 100.0 * (len(s) - 1))))] for p in ps}


def _norm_reason(r):
    """Collapse a reason to its family. exit_engine writes
    'regime_flip (TRENDING_BEAR)' with the regime inline, so the raw string is
    high-cardinality and would fragment every bucket."""
    r = (r or "unknown").strip()
    low = r.lower()
    for fam in ("regime_flip", "hard_close", "break_of_structure", "bos",
                "trail", "target", "stop", "max_loss", "expiry", "flatten"):
        if fam in low:
            return fam
    return low.split("(")[0].strip()[:24] or "unknown"


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=CONFOUND_CUTOFF)
    ap.add_argument("--until", default="9999-12-31")
    ap.add_argument("--strategy", default="",
                    help="restrict to one strategy (default: all, plus a "
                         "per-strategy flip-share table)")
    a = ap.parse_args(argv[1:])

    paths = sorted(glob.glob(os.path.expanduser(TRADES_GLOB)))
    if not paths:
        print(f"No fleet_trades_*.json under {TRADES_GLOB}")
        return 2

    rows = []
    no_time = 0
    for p in paths:
        m = DATE_RE.search(os.path.basename(p))
        if not m or not (a.since <= m.group(1) <= a.until):
            continue
        try:
            bundle = json.load(open(p))
        except Exception:                                        # noqa: BLE001
            continue
        for t in bundle.get("trades", []):
            if str(t.get("status", "")).lower() != "closed":
                continue
            if a.strategy and str(t.get("strategy", "")) != a.strategy:
                continue
            hold = _minutes(t.get("entry_time"), t.get("exit_time"))
            if hold is None:
                no_time += 1
                continue
            rows.append({"reason": _norm_reason(t.get("exit_reason")),
                         "strategy": str(t.get("strategy") or "?"),
                         "hold": hold, "pnl": _num(t.get("pnl_usd")),
                         "conv": _num(t.get("regime_conviction"))})

    if not rows:
        print(f"No closed trades with usable timestamps in "
              f"{a.since}..{a.until}. ({no_time} dropped for unparseable times.)")
        return 2

    print(f"window {a.since} .. {a.until} | {len(rows)} closed trades"
          + (f" | strategy {a.strategy}" if a.strategy else ""))
    if no_time:
        print(f"  ({no_time} dropped: unparseable entry/exit time — NOT counted "
              f"as short holds)")
    print(f"  'short hold' = < {SHORT_HOLD_MIN:.0f} min   "
          f"'flat P&L' = |pnl| < ${FLAT_PNL_USD:.0f}\n")

    by = collections.defaultdict(list)
    for r in rows:
        by[r["reason"]].append(r)

    print(f"{'exit reason':<20}{'n':>5} {'hold p25':>9}{'p50':>7}{'p75':>7} "
          f"{'|pnl| p50':>10} {'SHORT+FLAT':>11}")
    print("-" * 72)
    flip_sf = other_sf = flip_n = other_n = 0
    for reason, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        holds = _pcts([r["hold"] for r in rs])
        apnl = _pcts([abs(r["pnl"]) for r in rs])
        sf = sum(1 for r in rs
                 if r["hold"] < SHORT_HOLD_MIN and abs(r["pnl"]) < FLAT_PNL_USD)
        if reason == "regime_flip":
            flip_sf, flip_n = sf, len(rs)
        else:
            other_sf += sf
            other_n += len(rs)
        print(f"{reason:<20}{len(rs):>5} {holds.get(25,0):>9.1f}"
              f"{holds.get(50,0):>7.1f}{holds.get(75,0):>7.1f} "
              f"{apnl.get(50,0):>10.2f} {sf:>6} ({100.0*sf/len(rs):>3.0f}%)")

    print("\n" + "=" * 72)
    if not flip_n:
        print("NO regime_flip EXITS in this window. The flicker hypothesis has")
        print("nothing to explain here — look elsewhere for the short holds.")
    else:
        fr = 100.0 * flip_sf / flip_n
        orr = 100.0 * other_sf / other_n if other_n else 0.0
        print(f"regime_flip: {flip_sf}/{flip_n} ({fr:.0f}%) are SHORT AND FLAT")
        print(f"everything else: {other_sf}/{other_n} ({orr:.0f}%)")
        if fr > orr * 1.5 and flip_sf >= 5:
            print("\n-> FLICKER IS PLAUSIBLE. Flip exits cluster at short holds with")
            print("   near-zero P&L far more than other exits do. That is the")
            print("   signature of an exit firing on label noise rather than on a")
            print("   dead thesis. NEXT: check whether the integrator's `stale`")
            print("   flag was set on those ticks — it is journaled every tick and")
            print("   the exit path never reads it.")
        elif flip_sf < 5:
            print("\n-> TOO FEW to judge. Not evidence against flicker, just not")
            print("   enough flip exits in this window to see it.")
        else:
            print("\n-> FLICKER NOT SUPPORTED. Flip exits look like other exits on")
            print("   hold time and P&L, so the short holds are coming from")
            print("   somewhere else. Do NOT add hysteresis on this evidence.")
    print("=" * 72)

    if not a.strategy:
        print("\nflip share by strategy (continuation is the most regime-coupled):")
        per = collections.defaultdict(lambda: [0, 0])
        for r in rows:
            per[r["strategy"]][1] += 1
            if r["reason"] == "regime_flip":
                per[r["strategy"]][0] += 1
        for s, (f, n) in sorted(per.items(), key=lambda kv: -kv[1][1]):
            print(f"  {s[:28]:<30}{f:>4}/{n:<5} ({100.0*f/n if n else 0:>3.0f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
