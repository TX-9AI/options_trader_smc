#!/usr/bin/env python3
"""
tests/butterfly_cutoff_query.py — v1.2 — 2026-08-03

v1.2 — 2026-08-03 — DST. v1.1 fixed the UTC-vs-ET comparison but did it with a
       HARDCODED -4, reasoning that "the whole trading calendar here is inside
       DST". True today, false on **2026-11-01**, when ET goes to UTC-5 and every
       converted time silently shifts an hour — nine weeks after go-live. That is
       the same class of bug as v1.0, just with a fuse on it: correct now, wrong
       later, and nothing would announce the change.
       Now uses ZoneInfo("America/New_York") so DST is handled by the tz database,
       with the fixed offset kept ONLY as a no-tzdata fallback (fresh boxes may
       lack it) and LABELLED in the output when it is used, so a reader can see
       which path produced the numbers.
       NOTE the contrast with eod_summary.py, which also carries a fixed -4: that
       one is a documented no-tzdata fallback whose only consumer needs the DATE,
       and it runs at 15:50 — an hour of error cannot change the date except
       between 23:00 and midnight. It is correct for its purpose and was
       deliberately left alone rather than changed to look thorough.
v1.1 — 2026-08-03 — TIMEZONE. v1.0 read the raw HH:MM out of `entry_time` and
       compared it to a 15:00 ET cutoff. But entry_time is stored in **UTC** —
       `2026-08-03T17:38:45.284192+00:00`. So every entry looked four hours later
       than it was, and the first real run reported three "late" butterflies at
       16:35 / 16:41 / 17:40 that are actually **12:35 / 12:41 / 13:40 ET** — all
       comfortably BEFORE the cutoff.
       THE VERDICT WAS EXACTLY BACKWARDS: "late entries exist and WON, so the
       cutoff would have cost money" became "no butterfly has ever opened at or
       after 15:00, so the branch guards nothing". The ACTION happens to be the
       same (delete the branch), but the REASONING was wrong and would have gone
       into the record as evidence the cutoff is harmful — a claim the tape does
       not make.
       Now the offset in the timestamp is parsed and applied, ET is derived
       properly, and both the raw and converted times are printed so the
       conversion is visible rather than trusted.

BACKLOG ITEM I — "butterfly cutoff branch decision". `can_enter(is_butterfly=...)`
is unreachable: either fix the main.py call site (if a 15:00 butterfly cutoff is
ever wanted) or DELETE the branch so config and code stop disagreeing.

The item says "decision today; code post-freeze", and specifies the evidence:

    "one query on collected trades — the butterfly entry-time distribution
     (trades.db). If no fill has ever wanted the 15:00 window, delete the branch
     (loose-code principle); if late entries exist and lost, wire the call."

This is that query. It answers the decision rather than restating it, so the
decision costs a glance instead of a debate.

WHAT MAKES THIS DECIDABLE FROM DATA
    The branch exists to stop butterflies opening after 15:00 ET. Whether it is
    worth wiring depends entirely on whether butterflies ever HAVE opened then:
      - zero late entries ever      -> the branch guards nothing. DELETE it.
                                       Unreachable code that config believes in is
                                       worse than no code, because the config is
                                       lying about the system's behaviour.
      - late entries exist and LOST -> the cutoff is earning its keep. WIRE IT.
      - late entries exist and WON  -> the cutoff would have COST money. Delete
                                       the branch AND correct the config, which is
                                       the outcome nobody expects and the one most
                                       worth catching.

    That third branch is why this is a query and not a coin flip. "Wire the guard"
    is the intuitive answer and the data can say it is wrong.

HONEST LIMIT, stated because the sample is small
    Butterfly has ~3 lifetime trades in the cross-day report. A distribution over
    3 rows cannot support "late entries lose"; it CAN support "no fill has ever
    wanted the window", which is the branch the item leans toward and the only one
    a tiny n can establish. If late entries exist but are few, this prints them
    individually rather than computing a win rate over four trades.

USAGE (control box, repo root) — accepts one db or a directory of them
    python3 tests/butterfly_cutoff_query.py --db ~/day_trader_pro/trades/
    python3 tests/butterfly_cutoff_query.py --db /path/to/trades.db --cutoff 15:00

Read-only. Touches nothing.
"""

from __future__ import annotations

import argparse
import collections
import glob
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

# capture the offset too — entry_time is written in UTC (+00:00), and comparing
# a UTC wall clock to an ET cutoff shifts every trade four hours later.
TS_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2}):(\d{2})"
    r"(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?")
DEFAULT_CUTOFF = "15:00"
# DST is handled by the tz database, not by an assumption. ET is UTC-4 in EDT and
# UTC-5 in EST, and the changeover on 2026-11-01 falls nine weeks after go-live.
try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except Exception:                                    # noqa: BLE001 - no tzdata
    _ET = None
ET_OFFSET_H = -4          # fallback ONLY, and announced when used


def _et(ts):
    """(date_et, 'HH:MM' ET, 'HH:MM' as stored) or None.

    entry_time is UTC. Convert BEFORE comparing to a wall-clock ET cutoff.
    """
    m = TS_RE.search(str(ts or ""))
    if not m:
        return None
    d = m.group(1)
    dt = datetime(int(d[:4]), int(d[5:7]), int(d[8:10]),
                  int(m.group(2)), int(m.group(3)), int(m.group(4)))
    raw = f"{m.group(2)}:{m.group(3)}"
    off = m.group(5)
    # normalise to an AWARE UTC datetime first, then let the tz database do the
    # conversion — so EDT/EST is a lookup, not an assumption.
    if off in (None, "Z", "+00:00", "+0000"):
        aware = dt.replace(tzinfo=timezone.utc)
    else:
        sign = 1 if off[0] == "+" else -1
        oh, om = int(off[1:3]), int(off[-2:])
        aware = dt.replace(tzinfo=timezone(
            sign * timedelta(hours=oh, minutes=om)))
    et = (aware.astimezone(_ET) if _ET
          else aware.astimezone(timezone.utc) + timedelta(hours=ET_OFFSET_H))
    return et.strftime("%Y-%m-%d"), et.strftime("%H:%M"), raw


def _dbs(path):
    p = os.path.expanduser(path)
    if os.path.isfile(p):
        return [p]
    if os.path.isdir(p):
        return sorted(glob.glob(os.path.join(p, "**", "*.db"), recursive=True))
    return []


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="a trades.db, or a dir of them")
    ap.add_argument("--cutoff", default=DEFAULT_CUTOFF)
    a = ap.parse_args(argv[1:])

    dbs = _dbs(a.db)
    if not dbs:
        print(f"No .db found at {a.db}")
        return 2

    rows, scanned, no_time = [], 0, 0
    for d in dbs:
        try:
            conn = sqlite3.connect(f"file:{d}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT trade_id, symbol, strategy, setup_type, entry_time, "
                "exit_time, pnl_usd, status, is_butterfly FROM trades")
        except Exception:                                        # noqa: BLE001
            continue
        for t in cur:
            scanned += 1
            is_bfly = (int(t["is_butterfly"] or 0) == 1
                       or "butterfly" in str(t["strategy"] or "").lower()
                       or "butterfly" in str(t["setup_type"] or "").lower())
            if not is_bfly:
                continue
            conv = _et(t["entry_time"])
            if conv is None:
                no_time += 1
                continue
            d_et, hm, raw = conv
            rows.append({"id": t["trade_id"], "sym": t["symbol"],
                         "date": d_et, "hhmm": hm, "raw": raw,
                         "pnl": float(t["pnl_usd"] or 0.0),
                         "status": str(t["status"] or ""),
                         "setup": str(t["setup_type"] or "")})
        conn.close()

    if _ET is None:
        print("⚠ no tzdata — falling back to a FIXED UTC-4. Correct through "
              "2026-10-31 only.")
    print(f"scanned {scanned} trade row(s) across {len(dbs)} db(s)")
    print(f"butterfly trades found: {len(rows)}"
          + (f"   ({no_time} dropped: unparseable entry_time)" if no_time else ""))
    if not rows:
        print("\nNo butterfly trades on record at all. The 15:00 branch has never")
        print("had an opportunity to matter, so this query cannot yet distinguish")
        print("'guards nothing' from 'never tested'. NOT a decision — say so.")
        return 0

    print(f"\nENTRY-TIME DISTRIBUTION — converted to ET "
          f"(entry_time is stored UTC; cutoff under test: {a.cutoff} ET)")
    by_hour = collections.Counter(r["hhmm"][:2] + ":00" for r in rows)
    for h in sorted(by_hour):
        bar = "█" * by_hour[h]
        print(f"  {h}  {by_hour[h]:>3}  {bar}")

    late = [r for r in rows if r["hhmm"] >= a.cutoff]
    early = [r for r in rows if r["hhmm"] < a.cutoff]
    print(f"\n  before {a.cutoff}: {len(early)}      "
          f"at/after {a.cutoff}: {len(late)}")

    print("\n" + "=" * 62)
    if not late:
        print(f"VERDICT  NO BUTTERFLY HAS EVER OPENED AT/AFTER {a.cutoff}.")
        print("         The branch guards nothing. Per the item's loose-code")
        print("         principle: DELETE it, so config and code stop disagreeing.")
        print(f"         Evidence: {len(early)} butterfly entries, latest "
              f"{max(r['hhmm'] for r in early)} ET.")
    else:
        wins = [r for r in late if r["pnl"] > 0]
        net = sum(r["pnl"] for r in late)
        print(f"VERDICT  {len(late)} LATE ENTR{'Y' if len(late)==1 else 'IES'} "
              f"EXIST — net ${net:+.2f}, {len(wins)} winner(s).")
        print("         Listed individually below: with a sample this small a win")
        print("         rate would be theatre, so read the rows, not a percentage.")
        for r in sorted(late, key=lambda r: r["hhmm"]):
            print(f"           {r['date']} {r['hhmm']} ET "
                  f"({r['raw']} UTC) {r['sym']:<6} "
                  f"{r['pnl']:+9.2f}  {r['setup'][:30]}")
        if net < 0:
            print("\n         Net NEGATIVE -> the cutoff would have helped. WIRE the")
            print("         call site.")
        else:
            print("\n         Net POSITIVE -> the cutoff would have COST money. This")
            print("         is the outcome nobody expects: delete the branch AND")
            print("         correct the config, rather than wiring a guard that")
            print("         the tape says is wrong.")
    print("=" * 62)
    print("Read-only. No code changed — item I says decision now, code post-freeze.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
