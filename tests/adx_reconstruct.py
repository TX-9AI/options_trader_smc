#!/usr/bin/env python3
"""
tests/adx_reconstruct.py — v1.2 — 2026-08-03

v1.2 — 2026-08-03 — A MINIMUM OVERLAP, AND A STALENESS COLUMN. The first fleet
       run exposed two things v1.1 could not see.
       (a) THE BAR COULD BE CLEARED BY ONE ROW. Overlaps came back n=1,2,1,3,2,1,
       4,1,4,1 — and ORCL "FAILED" on n=1 while eight symbols "PASSED" on n<=4.
       A median over one observation is that observation. Every other tool this
       week carries a refusal floor (MIN_CELL_N, MIN_DEATHS); this one did not,
       which is the same omission in a new place. MIN_OVERLAP now refuses rather
       than reporting a verdict a single row could flip.
       (b) regime_log IS NOT A TICK LOG. 457 rows across a month — it writes on
       regime CHANGES. Measured against real entries: the gap back to the nearest
       preceding row is p50 600s, p90 1740s, max 4770s. Within 60s: 13/42. So the
       item's "tolerance <= 60s" was written assuming a denser log, and at 60s
       roughly a third of rows get filled.
       WIDENING THE TOLERANCE IS THE WRONG FIX. ADX-14 on 5m spans 70 minutes so
       a 10-minute-old reading is not absurd — but it is not the reading AT ENTRY
       either, and `adx_at_entry` means what was true at that moment. So instead
       every reconstructed row now records HOW STALE its source was, in a
       `staleness_s` column, and the caveat travels with the data rather than
       living in one decision made once. A downstream study picks its own
       tolerance; this tool no longer picks it for everyone.
v1.1 — 2026-08-03 — --db ACCEPTS A DIRECTORY. v1.0 took a single file, on the
       assumption there was one trades.db. There is not: the fleet pulls to
       `~/day_trader_pro/trades/<date>/<SYM>_trades_<date>.db` — one db PER SYMBOL
       per pull. The per-db join was already right (each box's db holds exactly
       one symbol, which is why regime_log needs no symbol column); it just had to
       walk the tree. Given a directory, every .db under it is processed
       independently and the overlap bar is evaluated PER DB — one symbol failing
       its own held-out check does not block the others, and does not get written.

BACKFILL `adx_at_entry` ON PRE-2026-07-27 TRADE ROWS by timestamp-joining
`regime_log` to `trades`. Backlog item: "Historical ADX reconstruction",
deferred at the 07-24 fix and worth doing now that the warm rebuild has landed.

WHAT THIS UNBLOCKS
    `adx_at_entry` arrived with the v-obs migration on 2026-07-24, so rows before
    that carry the schema default 0.0 rather than a real reading. Every study
    that wants to condition on trend strength at entry — and after the 08-03
    gap-day session that is a live question — silently treats those rows as
    ADX=0 or drops them. Reconstructing lengthens the usable sample without
    collecting anything new.

THE JOIN, and why nearest-PRECEDING rather than nearest
    For each trade, take the regime_log row with the LARGEST `logged_at` that is
    <= the trade's `entry_time`, same db, tolerance <= 60s. Nearest-preceding, not
    nearest-absolute: a regime row stamped AFTER the entry describes a world the
    trade could not have seen, and joining to it would leak hindsight into a
    column that is supposed to record what was known at the moment of entry. That
    is the same look-ahead error `a2_rail_drift`'s --persistent-only had, and it
    is worth not repeating.

TOLERANCE
    60s, per the item. regime_log writes on the tick cadence, so a gap wider than
    that means the nearest row genuinely describes a different moment. Rows with
    no match inside tolerance are LEFT ALONE — not filled with a best guess.

PROVENANCE — every written row is tagged
    Reconstructed values go in with `notes` gaining a `source=reconstructed`
    marker, so a later reader can always separate measured from inferred. A
    backfilled column that cannot be distinguished from a live one is a trap: the
    next person to find a surprising ADX distribution has no way to tell whether
    it is the market or the backfill.

THE VALIDATION IS FREE, and it is the reason to trust the result
    Rows since 2026-07-27 carry a REAL adx_at_entry. Run the identical join
    against those and compare the reconstruction to the recorded value. That is a
    held-out check costing nothing, and it measures the join rather than assuming
    it. `--verify-only` runs exactly that and writes nothing.
    **If the overlap does not agree, the backfill does not run.** Agreement is
    defined up front as median |error| <= 1.0 ADX point and >= 90% of overlap rows
    within 5 points — stated here before the numbers are seen.

USAGE (control box, repo root)
    python3 tests/adx_reconstruct.py --db <path> --verify-only      # check first
    python3 tests/adx_reconstruct.py --db <path> --dry-run          # what would change
    python3 tests/adx_reconstruct.py --db <path> --apply            # write

Read-only unless --apply. Never touches a row that already has a real value.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sqlite3
import sys
from datetime import datetime

# The v-obs migration that added adx_at_entry. Rows entered on or after this
# carry a real reading and are the held-out overlap.
REAL_FROM = "2026-07-27"
TOLERANCE_S = 60

# Pre-registered agreement bar — stated before the overlap is measured.
MAX_MEDIAN_ERR = 1.0
MIN_WITHIN_5 = 0.90
# A median over one observation IS that observation. Refuse rather than report a
# verdict a single row could flip — the same floor every other tool here carries.
MIN_OVERLAP = 8

TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2}):(\d{2})")


def _parse(ts):
    m = TS_RE.search(str(ts or ""))
    if not m:
        return None
    d = m.group(1)
    return datetime(int(d[:4]), int(d[5:7]), int(d[8:10]),
                    int(m.group(2)), int(m.group(3)), int(m.group(4)))


def _median(xs):
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def _load_regime(conn):
    """(datetime, adx) sorted ascending. regime_log has no symbol column, so the
    join is per-DB — which is correct, because each box's db holds exactly one
    symbol's rows."""
    out = []
    for logged_at, adx in conn.execute(
            "SELECT logged_at, adx FROM regime_log WHERE adx IS NOT NULL"):
        t = _parse(logged_at)
        if t is not None:
            out.append((t, float(adx)))
    out.sort(key=lambda r: r[0])
    return out


def _ensure_staleness_col(conn):
    """Add staleness_s if absent. Additive, idempotent, and it is what lets a
    later reader choose a tolerance instead of inheriting this tool's."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(trades)")]
    if "staleness_s" not in cols:
        conn.execute("ALTER TABLE trades ADD COLUMN staleness_s REAL")
        conn.commit()


def _nearest_preceding(rows, t, tol_s):
    """Largest logged_at <= t, within tolerance. Binary search on a sorted list.

    PRECEDING ONLY: a regime row stamped after the entry describes a world the
    trade could not have seen.
    """
    lo, hi = 0, len(rows) - 1
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if rows[mid][0] <= t:
            best = rows[mid]
            lo = mid + 1
        else:
            hi = mid - 1
    if best is None:
        return None
    age = (t - best[0]).total_seconds()
    if age > tol_s:
        return None
    return best[1], age


def _dbs(path):
    p = os.path.expanduser(path)
    if os.path.isfile(p):
        return [p]
    if os.path.isdir(p):
        return sorted(glob.glob(os.path.join(p, "**", "*.db"), recursive=True))
    return []


def run_one(path, a) -> int:
    """Process ONE db. Returns 0 ok / 1 overlap failed / 2 unusable."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        regime = _load_regime(conn)
    except Exception as exc:                                     # noqa: BLE001
        print(f"  {os.path.basename(path):<34} SKIP — no regime_log ({exc})")
        return 2
    if not regime:
        print(f"  {os.path.basename(path):<34} SKIP — regime_log empty")
        return 2
    trades = list(conn.execute(
        "SELECT trade_id, entry_time, adx_at_entry, notes FROM trades"))

    errs, within5, overlap = [], 0, 0
    for t in trades:
        et = _parse(t["entry_time"])
        if et is None or et.strftime("%Y-%m-%d") < REAL_FROM:
            continue
        real = float(t["adx_at_entry"] or 0.0)
        if real <= 0:
            continue
        hit = _nearest_preceding(regime, et, a.tolerance)
        if hit is None:
            continue
        got, _age = hit
        overlap += 1
        e = abs(got - real)
        errs.append(e)
        if e <= 5.0:
            within5 += 1

    name = os.path.basename(path)
    if overlap < MIN_OVERLAP:
        print(f"  {name:<34} REFUSED — overlap n={overlap} < {MIN_OVERLAP}; a "
              f"verdict here would rest on\n       too few rows to mean anything "
              f"(a median over one row IS that row).")
        conn.close()
        return 2
    med, frac = _median(errs), within5 / overlap
    ok = med <= MAX_MEDIAN_ERR and frac >= MIN_WITHIN_5
    verdict = "PASS" if ok else "FAIL"
    print(f"  {name:<34} overlap n={overlap:<4} med|err| {med:>6.2f}  "
          f"within5 {frac:>4.0%}  {verdict}")
    if not ok:
        print("       -> NOT written. A wrong ADX is worse than a 0.0: a zero "
              "is obviously missing.")
        conn.close()
        return 1
    if a.verify_only:
        conn.close()
        return 0

    to_write, no_match, already = [], 0, 0
    for t in trades:
        et = _parse(t["entry_time"])
        if et is None or et.strftime("%Y-%m-%d") >= REAL_FROM:
            continue
        if float(t["adx_at_entry"] or 0.0) > 0:
            already += 1
            continue
        hit = _nearest_preceding(regime, et, a.tolerance)
        if hit is None:
            no_match += 1
            continue
        got, age = hit
        to_write.append((t["trade_id"], got, age, t["notes"] or ""))
    if a.apply and to_write:
        _ensure_staleness_col(conn)
        cur = conn.cursor()
        for tid, adx, age, notes in to_write:
            tag = "source=reconstructed"
            nn = notes if tag in notes else (notes + " " + tag).strip()
            cur.execute("UPDATE trades SET adx_at_entry=?, staleness_s=?, "
                        "notes=? WHERE trade_id=?", (adx, age, nn, tid))
        conn.commit()
        ages = sorted(w[2] for w in to_write)
        print(f"       ✅ wrote {len(to_write)}  (no match {no_match}, "
              f"already real {already})")
        print(f"          staleness_s: p50 {ages[len(ages)//2]:.0f}s  "
              f"max {ages[-1]:.0f}s  — downstream picks its own tolerance")
    else:
        print(f"       would write {len(to_write)}  (no match {no_match}, "
              f"already real {already})"
              + ("" if a.apply else "  [dry-run]"))
    conn.close()
    return 0


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True,
                    help="a trades .db, or a DIRECTORY of them (walked "
                         "recursively — the fleet layout is "
                         "trades/<date>/<SYM>_trades_<date>.db)")
    ap.add_argument("--tolerance", type=int, default=TOLERANCE_S)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--verify-only", action="store_true",
                   help="run the held-out overlap check and stop")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv[1:])

    dbs = _dbs(a.db)
    if not dbs:
        print(f"No .db found at {a.db}\n"
              f"  the fleet layout is ~/day_trader_pro/trades/<date>/"
              f"<SYM>_trades_<date>.db — pass the DIRECTORY.")
        return 2

    mode = ("verify-only" if a.verify_only else
            "APPLY" if a.apply else "dry-run")
    print(f"{len(dbs)} db(s) | tolerance {a.tolerance}s | mode {mode}")
    print(f"real values from {REAL_FROM}; bar: median |err| <= {MAX_MEDIAN_ERR}, "
          f">= {MIN_WITHIN_5:.0%} within 5\n")

    ok = fail = skip = 0
    for d in dbs:
        r = run_one(d, a)
        ok += r == 0
        fail += r == 1
        skip += r == 2
    print(f"\n{ok} passed, {fail} failed the overlap bar, {skip} unusable.")
    if fail:
        print("Failures are per-symbol and were NOT written; the rest are "
              "unaffected.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
