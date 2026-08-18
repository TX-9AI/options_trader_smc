#!/usr/bin/env python3
"""
tests/evm_status.py — v1.1 — 2026-07-30

EARNED VALUE against docs/BACKLOG.md, with the one adaptation that makes EVM
honest for this project: SCHEDULE VARIANCE IS SPLIT BY WHAT CAUSED IT.

    A late [DESK] item is a performance failure. Nothing blocked it; we did not
    do it. It counts against us.

    A late [DESK·DATA] item is a DC&A dependency — the sessions had not accrued
    yet. It is not a failure of execution and must not be averaged into the
    number that measures execution, or the metric stops meaning anything.

    A late [FLEET] item waited on a deploy window or boxes being up.

So this reports TWO indices. SPI(all) is the calendar truth — what the plan says
versus what exists. SPI(desk) is the accountability truth — of the work that was
ours to move, how much moved. A healthy project can carry SPI(all) < 1 while
SPI(desk) = 1.0; that is a plan waiting on data, which is fine. SPI(desk) < 1 is
the number that should sting.

TERMS, since this is a backlog and not a cost account:
    BAC  every item in the plan (open + resolved). One item = one unit; we have
         no effort estimates and inventing them would be false precision.
    PV   items whose SCHEDULED date has arrived — what the plan says should be
         done by now.
    EV   items actually marked ✅ — what is genuinely done.
    SV   EV − PV. Negative = behind.
    SPI  EV / PV. Below 1.00 = behind.
    (No CV/CPI: there is no cost baseline. Reporting one would be theatre.)

FORECAST + GET-WELL
    Projects the finish from the observed completion rate and tests it against
    the gate dates. If a gate is at risk it prints a GET-WELL PLAN naming the
    specific items driving the variance, separated by cause, because the
    recovery for "we have not done the desk work" is not the recovery for "the
    data does not exist yet."

USAGE
    python3 tests/evm_status.py                # today
    python3 tests/evm_status.py --asof 2026-08-10
    python3 tests/evm_status.py --quiet        # one headline line (conductor)

Read-only. stdlib only. Parses the backlog; changes nothing.
"""

import argparse
import datetime as dt
import os
import re
import sys

YEAR = 2026
MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}

# Gates that matter. Slipping these is the thing the plan exists to prevent.
GATES = [("FREEZE declared", dt.date(2026, 8, 21)),
         ("GO LIVE (tiny size)", dt.date(2026, 8, 31)),
         ("FULL SIZE", dt.date(2026, 9, 14))]


def parse_day(header):
    """'**⬜ Sat Aug 8 – Sun Aug 9 (weekend fit)**' -> date(2026,8,8). First date wins."""
    m = re.search(r"\b([A-Z][a-z]{2})\s+(\d{1,2})\b", header)
    if not m or m.group(1) in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
        m2 = re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\b",
                       header)
        if not m2:
            return None
        m = m2
    try:
        return dt.date(YEAR, MONTHS[m.group(1)], int(m.group(2)))
    except Exception:                                    # noqa: BLE001
        return None


def load(path):
    """Parse PART 1 + PART 2 only.

    PART 3 is the resolved REGISTER — a second write-up of items that already
    appear (marked ✅) in PART 1. Counting it inflates EV, and the first run of
    this tool reported SPI 2.53 for exactly that reason: more work 'earned' than
    the plan contained. A metric that can exceed its own baseline is measuring
    the document, not the project.
    """
    full = open(path, encoding="utf-8").read()
    # v1.1 — BACKLOG v3.15 moved resolved items OUT of the schedule. Earned value
    # now lives in PART 3 and remaining work in PART 1+2; reading PART 1 alone
    # reported EV 2/49 and SPI 2.00, the same can't-exceed-your-own-baseline
    # signature that flagged the duplicate-counting bug on the first ever run.
    try:
        raw   = full[full.index("## PART 1"):full.index("## PART 3")]
        p3raw = full[full.index("## PART 3"):full.index("## PART 4")]
    except ValueError:
        raw, p3raw = full, ""
    n_resolved = len([l for l in p3raw.split("\n")
                      if re.match(r"^- \*\*[A-Za-z0-9.]+ ?[—✅]", l)])
    items, day, day_hdr = [], None, ""
    items.append({"_resolved_count": n_resolved})
    for line in raw.split("\n"):
        h = re.match(r"^\*\*[⬜✅◐]\s*(.+?)\*\*", line)
        if h:
            day_hdr = h.group(1)
            day = parse_day(day_hdr)
            continue
        b = re.match(r"^-\s+(?:`\[([^\]]+)\]`\s+)?\*\*([A-Za-z0-9.]+)", line)
        if not b:
            continue
        tag = b.group(1) or ("RESOLVED" if "✅" in line[:70] else "UNTAGGED")
        items.append({"name": b.group(2), "tag": tag, "day": day,
                      "day_hdr": day_hdr[:34],
                      "done": "✅" in line[:70]})
    return items


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--backlog", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "docs", "BACKLOG.md"))
    ap.add_argument("--asof")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv[1:])
    asof = (dt.date.fromisoformat(a.asof) if a.asof
            else dt.datetime.now().date())

    items = load(a.backlog)
    resolved_n = items[0].get("_resolved_count", 0) if items else 0
    items = [i for i in items if "name" in i]
    if not items:
        print("no items parsed — has the backlog format changed?")
        return 1

    # EV = work completed (PART 3). Overdue = scheduled by now, still open.
    overdue = [i for i in items if i["day"] and i["day"] <= asof and not i["done"]]
    ev  = resolved_n
    bac = resolved_n + len(items)
    pv  = ev + len(overdue)              # what the plan says should be done by now
    spi_all = (ev / pv) if pv else 1.0

    # controllable slice: DESK only, and only those already due
    # Accountability: DESK work that was due and is still open. Reported as a
    # COUNT, not a ratio — resolved items no longer carry tags, so a desk ratio
    # would have an unknowable denominator, and inventing one is false precision.
    desk_overdue = [i for i in overdue if i["tag"] == "DESK"]
    spi_desk = 1.0 if not desk_overdue else 0.0

    late = overdue
    late_desk = [i for i in late if i["tag"] == "DESK"]
    late_data = [i for i in late if i["tag"] in ("DESK·DATA", "FLEET", "DESK→DEPLOY")]

    if a.quiet:
        print(f"EVM {asof}: EV {ev}/{bac} · PV {pv} · SV {ev - pv:+d} · "
              f"SPI {spi_all:.2f} · overdue {len(late)} "
              f"({len(desk_overdue)} DESK, on us)")
        return 0

    print(f"EARNED VALUE — as of {asof}\n" + "=" * 62)
    print(f"  BAC (all items in plan)        {bac}")
    print(f"  PV  (scheduled by now)         {pv}")
    print(f"  EV  (actually done)            {ev}")
    print(f"  SV  (EV − PV)                  {ev - pv:+d}")
    print(f"  SPI(all)   {spi_all:5.2f}   <- calendar truth (includes data waits)")
    print(f"  DESK overdue  {len(desk_overdue):>3}   <- ACCOUNTABILITY: due, open, "
          f"and nothing blocking it")

    # v1.3 — NAME THEM. The count alone cannot be acted on: deciding what to
    # drop before a gate needs the list, and reading it meant opening BACKLOG by
    # hand. A schedule variance you cannot attribute to specific work is a
    # number, not a status.
    # DESK first and separately, because the two kinds of lateness have
    # DIFFERENT CAUSES and different responses — a late [DESK] item is
    # performance (nothing blocked it), a late [DESK·DATA] item is a DC&A
    # dependency waiting on sessions that have not accrued. Briefing them
    # together would misattribute the variance.
    if desk_overdue:
        print(f"\n  DESK — LATE ON US ({len(desk_overdue)}), oldest first:")
        for i in sorted(desk_overdue, key=lambda x: x["day"]):
            print(f"     {i['day']}  ({(asof - i['day']).days:>2}d)  {i['name'][:62]}")
    other_overdue = [i for i in late if i["tag"] != "DESK"]
    if other_overdue:
        print(f"\n  WAITING ON SOMETHING ({len(other_overdue)}) — data, a fleet "
              f"window, or a bake:")
        for i in sorted(other_overdue, key=lambda x: x["day"]):
            print(f"     {i['day']}  ({(asof - i['day']).days:>2}d)  "
                  f"[{i['tag']}] {i['name'][:52]}")

    remaining = bac - ev
    print(f"\n  remaining: {remaining}")
    by_tag = {}
    for i in items:
        if not i["done"]:
            by_tag[i["tag"]] = by_tag.get(i["tag"], 0) + 1
    for t, n in sorted(by_tag.items(), key=lambda kv: -kv[1]):
        note = {"DESK": "  <- ours; only effort moves these",
                "DESK·DATA": "  <- unblocks on the calendar",
                "FLEET": "  <- needs a window",
                "DESK→DEPLOY": "  <- build now, bake Monday"}.get(t, "")
        print(f"     {t:<14} {n:>3}{note}")

    for name, when in GATES:
        days = (when - asof).days
        if days < 0:
            continue
        print(f"\n  gate: {name} — {when} ({days} calendar days out)")
        due_by = [i for i in items if i["day"] and i["day"] <= when and not i["done"]]
        desk_by = [i for i in due_by if i["tag"] == "DESK"]
        print(f"        {len(due_by)} items still open on or before it "
              f"({len(desk_by)} DESK)")
        # crude rate check: DESK items per remaining day needed
        if desk_by and days > 0:
            need = len(desk_by) / days
            print(f"        DESK burn needed: {need:.2f}/day "
                  f"({'comfortable' if need <= 0.34 else 'tight' if need <= 0.7 else 'AT RISK'})")

    if late:
        print("\n" + "-" * 62)
        print("  BEHIND PLAN — split by cause, because the fix differs")
        print("-" * 62)
        if late_desk:
            print(f"  ON US ({len(late_desk)}) — nothing blocked these:")
            for i in late_desk:
                print(f"     {i['name']:<12} was due {i['day']}  [{i['day_hdr']}]")
        if late_data:
            print(f"  NOT ON US ({len(late_data)}) — DC&A / window dependencies:")
            for i in late_data[:10]:
                print(f"     {i['name']:<12} {i['tag']:<12} due {i['day']}")

        print("\n  GET-WELL PLAN")
        if late_desk:
            print(f"    1. {len(late_desk)} DESK item(s) are late with no dependency. "
                  f"These are recoverable by effort alone —")
            print(f"       clear them before taking on anything newly scheduled.")
        if late_data:
            print(f"    2. {len(late_data)} item(s) slipped on data or window "
                  f"availability, NOT execution. Do not")
            print(f"       compress these; re-date them honestly and record the "
                  f"dependency that moved them.")
        print("    3. If a GATE is at risk, the decision is scope or date — "
              "never quietly compressing")
        print("       validation. A gate met with unvalidated work is not a "
              "gate met.")
    else:
        print("\n  No items are behind plan.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
