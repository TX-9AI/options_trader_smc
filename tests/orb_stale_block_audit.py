#!/usr/bin/env python3
"""
tests/orb_stale_block_audit.py — v1.0 — 2026-08-04

HOW MUCH ORB DID THE v5.0 STALE GATE ACTUALLY COST? Reads a box's `bot.log` and
answers it from what was logged, rather than leaving "ORB was gated" as a
mechanism nobody put a number on.

WHAT IT COUNTS, per session found in the log:
  1. the stale-block window — first and last `Entry blocked: regime book is
     STALE`, and how many ticks it spanned;
  2. whether the ORB engine was CONFIRMED (OPEN_LONG / OPEN_SHORT) at any point
     inside that window — those are the ticks where a trade was available and
     the gate refused it;
  3. after v5.4, the `STALE book, but ORB is CONFIRMED` line, which is the
     direct before/after: it should appear exactly where the block used to.

WHY bot.log AND NOT trades.db. A blocked entry leaves NO trade row — that is the
whole problem. The refusal exists only as a log line, so the log is the only
place the counterfactual can be recovered from. `orb_state.json` carries the
CURRENT state and is overwritten every tick, so it cannot answer a question
about 09:35 after the fact either.

WHAT IT CANNOT SAY, and this bounds every number it prints: a confirmed ORB
inside the window is a trade that COULD have fired, not one that WOULD have
made money. Sizing, grade, liquidity-in-path and the daily-loss halt all sit
downstream of the gate and none of them are in the log. Treat the count as an
upper bound on opportunities refused, never as forgone P&L.

Read-only. stdlib only. Runs on a BOX (`~/options-trader/bot.log`) or on
control against a pulled copy.

USAGE
    python3 tests/orb_stale_block_audit.py
    python3 tests/orb_stale_block_audit.py --log ~/options-trader/bot.log
"""

import argparse
import os
import re
import sys

DEFAULT_LOG = "~/options-trader/bot.log"

TS = re.compile(r"(20\d\d-\d\d-\d\d)[ T](\d\d):(\d\d):(\d\d)")
BLOCKED = "Entry blocked: regime book is STALE"
EXEMPT = "STALE book, but ORB is CONFIRMED"
ORB_CONFIRMED = re.compile(r"\bOPEN_(LONG|SHORT)\b")


def _stamp(line):
    m = TS.search(line)
    if not m:
        return None, None
    return m.group(1), int(m.group(2)) * 60 + int(m.group(3))


def _hhmm(mins):
    return f"{mins // 60:02d}:{mins % 60:02d}" if mins is not None else "—"


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default=DEFAULT_LOG)
    a = ap.parse_args(argv[1:])

    path = os.path.expanduser(a.log)
    if not os.path.isfile(path):
        print(f"no log at {path}")
        return 2

    days = {}
    for line in open(path, errors="ignore"):
        d, mins = _stamp(line)
        if d is None:
            continue
        rec = days.setdefault(d, {"blocked": [], "exempt": [], "orb": set()})
        if BLOCKED in line:
            rec["blocked"].append(mins)
        elif EXEMPT in line:
            rec["exempt"].append(mins)
        elif ORB_CONFIRMED.search(line):
            rec["orb"].add(mins)

    if not days:
        print("no timestamped lines parsed — is this a bot.log?")
        return 2

    print(f"log {path}   {len(days)} session(s)\n")
    print(f"  {'date':<12}{'blocked':>9}{'window':>16}{'ORB confirmed':>16}"
          f"{'exempt (v5.4)':>16}")
    tot_b = tot_overlap = tot_e = 0
    for d in sorted(days):
        r = days[d]
        b = r["blocked"]
        lo, hi = (min(b), max(b)) if b else (None, None)
        # THE NUMBER THAT MATTERS: minutes inside the block window where the ORB
        # engine was CONFIRMED — a trade was available and the gate refused it.
        overlap = sorted(m for m in r["orb"]
                         if lo is not None and lo <= m <= hi)
        tot_b += len(b)
        tot_overlap += len(overlap)
        tot_e += len(r["exempt"])
        win = f"{_hhmm(lo)}-{_hhmm(hi)}" if b else "—"
        print(f"  {d:<12}{len(b):>9}{win:>16}{len(overlap):>16}"
              f"{len(r['exempt']):>16}")

    print(f"\n  totals: {tot_b} blocked tick(s), {tot_overlap} of them with a "
          f"CONFIRMED ORB, {tot_e} v5.4 exemption(s)")
    print("\n" + "=" * 70)
    print("READING IT")
    print("=" * 70)
    print("  'ORB confirmed' is the count of minutes inside the block window")
    print("  where the engine had a confirmed break. Those are opportunities the")
    print("  gate refused — an UPPER BOUND, because sizing, grade, liquidity and")
    print("  the daily-loss halt all sit downstream and none of them are logged.")
    print("  NOT forgone P&L, and not a claim any of them would have won.")
    print("  A ZERO does not clear the gate. It says this box had no confirmed")
    print("  break during its own stale window, which on most boxes most days is")
    print("  the expected answer — ORB confirms on a break AND retest, and the")
    print("  window is four to six minutes wide. The fleet total is the number,")
    print("  not any single box.")
    print("  After the v5.4 bake, 'exempt' should appear where 'blocked' used to")
    print("  and the two columns become the direct before/after.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
