#!/usr/bin/env python3
"""
tests/condor_block_attribution.py — v1.0 — 2026-08-11

WHY THE CONDOR DID NOT TRADE — attributed to a SPECIFIC GATE, not guessed.

THE SITUATION IT WAS BUILT FOR. On 2026-08-11 the L1 replay showed RANGING
winning the argmax on **26% of ticks** — second only to TRENDING_BEAR — while L2
emitted it on **4%**, and the whole fleet produced exactly **ONE** condor plan
and ZERO condor trades. RGM.4 had already lowered RANGING's commit bar 0.65 ->
0.60 the night before, which roughly doubled emission (2% -> 4%) and changed
nothing about the outcome.

⚠️ THE POINT OF THIS TOOL IS TO STOP THE OBVIOUS WRONG MOVE. The tempting fix is
to widen RANGING further. But the condor has SIX conjunctive gates and the
regime is only one of them:

    1  entry window 11:11-14:00 ET      (CONDOR_ENTRY_START/CUTOFF_ET)
    2  one plan per session             (self._plan is not None -> return)
    3  regime == RANGING
    4  VIX < 20                         (shares VIX_BUTTERFLY_DISABLE)
    5  expected move computable         (em <= 0 -> return)
    6  liquid strikes beyond BOTH 0.80*EM and the Bollinger band, per side
       (the DUAL FLOOR — no fallback by design; a leg with nothing liquid past
       the floor is SKIPPED, never placed inside. That rule was added after
       three weeks of bleeding and must not be loosened casually.)

Widening gate 3 while gate 1 or gate 6 is the binding one buys nothing and
costs a behaviour change. This tool says WHICH.

WHAT IT CAN AND CANNOT SEE, stated plainly because it decides what the output
means:
  MEASURABLE OFFLINE (this tool, from control, boxes down):
    gate 1 x gate 3 — the intersection of RANGING commits with the entry
                      window, per symbol, from the replay corpus
    gate 2         — plans actually created, from the signal journal
  NEEDS THE BOX LOGS (requires waking the fleet):
    gates 4, 5, 6  — each logs its own refusal line, but to bot.log, which
                     lives on the boxes and is not replicated to control
So a NON-ZERO gate-1x3 intersection does not prove the condor could have
traded — it proves the OPPORTUNITY existed and moves the question downstream.
A ZERO intersection is conclusive on its own: nothing downstream can fire.

READ-ONLY. stdlib only. Touches no fleet, no live path, writes nothing.

USAGE (control)
    python3 tests/condor_block_attribution.py                 # today
    python3 tests/condor_block_attribution.py 2026-08-11
    python3 tests/condor_block_attribution.py 2026-08-11 --window 11:11-14:00
"""

import argparse
import collections
import glob
import json
import os
import sys
from datetime import datetime

DTP = os.path.expanduser("~/day_trader_pro")
REPORTS = os.path.join(DTP, "reports")
JOURNAL = os.path.join(DTP, "signal_journal")

# config.py CONDOR_ENTRY_START_ET / CONDOR_ENTRY_CUTOFF_ET
DEFAULT_WINDOW = "11:11-14:00"
RANGING = "RANGING"


def parse_window(s):
    try:
        a, b = s.split("-")
        return (tuple(int(x) for x in a.split(":")),
                tuple(int(x) for x in b.split(":")))
    except Exception:                                        # noqa: BLE001
        raise SystemExit(f"bad --window {s!r}; expected HH:MM-HH:MM")


def hm(ts):
    """'HH:MM' -> (h, m), or None."""
    if not ts or ":" not in str(ts):
        return None
    try:
        p = str(ts).split(":")
        return int(p[0][-2:]), int(p[1][:2])
    except Exception:                                        # noqa: BLE001
        return None


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?",
                    default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--window", default=DEFAULT_WINDOW)
    a = ap.parse_args(argv[1:])
    lo, hi = parse_window(a.window)
    d = a.date

    print("=" * 70)
    print(f"  CONDOR BLOCK ATTRIBUTION — {d}   window {a.window} ET")
    print("=" * 70)

    # ── GATES 1 x 3, from the replay corpus ─────────────────────────────────
    rp = os.path.join(REPORTS, f"regime_replay_{d}.jsonl")
    if not os.path.isfile(rp):
        print(f"\n  NO REPLAY for {d} at {rp}")
        print("  Run devtools 42 (today) or 43 (pick a date) first — gates 1x3")
        print("  cannot be measured without it, and they are the decisive pair.")
        return 1

    allc, win = collections.Counter(), collections.Counter()
    rang_by_sym = collections.Counter()
    rang_win_by_sym = collections.Counter()
    win_ticks = 0
    for line in open(rp, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:                                    # noqa: BLE001
            continue
        lab = (r.get("l2") or {}).get("regime") or ""
        t = hm(r.get("ts"))
        if not lab or t is None:
            continue
        allc[lab] += 1
        in_win = lo <= t < hi
        if in_win:
            win[lab] += 1
            win_ticks += 1
        if lab == RANGING:
            sym = r.get("sym", "?")
            rang_by_sym[sym] += 1
            if in_win:
                rang_win_by_sym[sym] += 1

    total = sum(allc.values())
    print(f"\n  replay ticks {total:,}   inside the window {win_ticks:,}\n")
    print(f"  {'EMITTED LABEL':22}{'all':>8}{'%':>7}{'in window':>12}{'%':>7}")
    for k, v in allc.most_common():
        print(f"  {k:22}{v:>8}{100.0*v/max(total,1):>6.1f}%"
              f"{win[k]:>12}{100.0*win[k]/max(win_ticks,1):>6.1f}%")

    rw = win[RANGING]
    print(f"\n  ── GATE 1 x GATE 3 ─────────────────────────────────────────")
    print(f"  RANGING ticks INSIDE the entry window: {rw}")
    if rw == 0:
        print("  ⇒ CONCLUSIVE: the condor could not have planned at all today.")
        print("    RANGING never committed inside 11:11-14:00, so gates 4, 5 and 6")
        print("    were never reached. WIDENING THE REGIME BAR WOULD NOT HAVE")
        print("    HELPED unless it also moved commits INTO the window.")
        print("    The question becomes: does RANGING commit at all, and WHEN?")
        outside = allc[RANGING] - rw
        print(f"    RANGING committed {allc[RANGING]} times today, {outside} of them")
        print(f"    OUTSIDE the window. If those cluster early or late, the WINDOW")
        print(f"    is the defect, not the label.")
    else:
        print(f"  ⇒ THE OPPORTUNITY EXISTED on {rw} tick(s).")
        print("    Gates 1 and 3 are NOT the blocker. The refusal is downstream —")
        print("    VIX (gate 4), expected move (5), or the DUAL STRIKE FLOOR (6).")
        print("    Those log to bot.log ON THE BOXES; see the tail of this report.")
        print(f"\n  {'SYMBOL':10}{'RANGING all':>13}{'in window':>12}")
        for s, n in rang_win_by_sym.most_common(12):
            print(f"  {s:10}{rang_by_sym[s]:>13}{n:>12}")
        if not rang_win_by_sym:
            print("    (none — all RANGING commits fell outside the window)")

    # ── WHEN does RANGING commit? ───────────────────────────────────────────
    print(f"\n  ── WHEN RANGING COMMITS (hourly) ───────────────────────────")
    by_hour = collections.Counter()
    for line in open(rp, encoding="utf-8"):
        try:
            r = json.loads(line.strip() or "{}")
        except Exception:                                    # noqa: BLE001
            continue
        if ((r.get("l2") or {}).get("regime") or "") != RANGING:
            continue
        t = hm(r.get("ts"))
        if t:
            by_hour[t[0]] += 1
    if by_hour:
        mx = max(by_hour.values())
        for h in sorted(by_hour):
            bar = "#" * max(1, int(28 * by_hour[h] / mx))
            mark = "  <- in window" if lo[0] <= h < hi[0] else ""
            print(f"    {h:02d}:00  {by_hour[h]:>5}  {bar}{mark}")
    else:
        print("    RANGING never committed today at any hour.")

    # ── GATE 2, from the signal journal ─────────────────────────────────────
    print(f"\n  ── GATE 2 — PLANS ACTUALLY CREATED ─────────────────────────")
    plans = []
    for p in sorted(glob.glob(os.path.join(JOURNAL, d, "*.jsonl"))):
        sym = os.path.basename(p).split(".")[0]
        for line in open(p, encoding="utf-8"):
            if "condor_plan" not in line:
                continue
            try:
                r = json.loads(line.strip())
            except Exception:                                # noqa: BLE001
                continue
            if r.get("event") == "condor_plan":
                r["_sym"] = sym
                plans.append(r)
    if not plans:
        print("    NONE. No condor plan was created anywhere on the fleet.")
    else:
        print(f"    {len(plans)} plan(s):")
        for r in plans:
            pl = r.get("plan") or {}
            rg = r.get("regime") or {}
            print(f"      {r['_sym']:6} {str(r.get('ts_et',''))[11:19]}  "
                  f"leg1={pl.get('leg1_side')}  under={pl.get('underlying')}  "
                  f"call_trig={pl.get('call_trigger')}  put_trig={pl.get('put_trigger')}  "
                  f"conv={rg.get('conviction')}")
        print("\n    A plan is INFORMATIONAL — no order is placed until a LEG")
        print("    TRIGGER fires. A plan with no trade means the legs never")
        print("    triggered, which is a DIFFERENT repair from the regime gate.")

    # ── WHAT THIS CANNOT SEE ────────────────────────────────────────────────
    print(f"\n  ── GATES 4, 5, 6 — NOT MEASURABLE FROM CONTROL ─────────────")
    print("    Each logs its own refusal, but to bot.log on the BOXES:")
    print("      gate 4  'Condor blocked: VIX='")
    print("      gate 5  'Condor: could not compute expected move'")
    print("      gate 6  the dual-floor skip (no liquid strike beyond the floor)")
    print("    If gates 1x3 passed above, wake the fleet and count those three")
    print("    on option 14 — that is the only way to attribute further.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
