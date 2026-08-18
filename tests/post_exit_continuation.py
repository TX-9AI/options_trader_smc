#!/usr/bin/env python3
"""
tests/post_exit_continuation.py — v1.0 — 2026-08-03

AFTER AN EXIT FIRES, DOES PRICE KEEP GOING IN THE TRADE'S DIRECTION?

Backlog **AY**, third miss. The 2026-08-03 session put `bos_exit` at **21 trades,
−$2,757.50 — 88% of the day's net loss** — with realized −9%, MFE +2%, giveback
+11%. And MU, which the fleet had CORRECTLY identified, ran a 60-minute leg from
~803 to ~830 while the fleet took 6 trades at 2.8 minutes average hold for −$377.

Giveback (MFE − realized) says a trade gave back what it made BEFORE exiting.
It cannot say whether the move CONTINUED AFTER. Those are different defects with
different fixes: giveback means the trail is loose, continuation means the exit
fired too early on a move that was still running. This measures the second.

WHAT IS NOT ASSUMED
    `bos_exit` is NOT presumed broken. Cumulatively it is **40 trades, 57% win,
    +$477.55** — it inverted on one session rather than being wrong in general.
    So the comparison is against EVERY OTHER EXIT REASON on the same tape and the
    same horizons. If all exits show post-exit continuation, that is momentum or
    drift and says nothing about BOS. **Only a BOS-specific excess is a finding.**

THE MEASUREMENT
    At exit, take the underlying price. Look forward N minutes. Sign by the
    trade's direction (`long` → up is favourable, `short` → down is favourable).
    A POSITIVE number means price kept moving the way the trade wanted **after we
    were already out** — money left on the table.

TIMEZONES — the thing this file is most likely to get wrong
    `exit_time` is stored **UTC** (`...T17:16:28+00:00`). The 1m tape is written
    with an **ET offset** (`...T13:16:00-04:00`). Comparing the wall clocks would
    be off by four hours, and DST would move it again in November. So both sides
    are parsed to AWARE datetimes and compared as ABSOLUTE INSTANTS — no wall
    clock, no offset arithmetic, no DST assumption. That is the discipline the
    butterfly query needed two versions to learn.

POWER, printed before the table
    `bos_exit` is ~40 trades lifetime. Split across horizons that is thin, and the
    week's lesson is that an underpowered cell read as a null is how a confounded
    result looks real. The minimum detectable effect is printed per cell and cells
    under n=10 are REFUSED.

USAGE (control box, repo root)
    python3 tests/post_exit_continuation.py --db ~/day_trader_pro/trades/2026-08-03
    python3 tests/post_exit_continuation.py --db <dir> --horizons 5,15,30

Read-only. Reads trade dbs and the 1m tape. Changes nothing.
"""

from __future__ import annotations

import argparse
import collections
import glob
import math
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

TAPE_ROOTS = ["~/day_trader_pro/ohlc", "./ohlc"]
DATE_RE = re.compile(r"^20\d\d-\d\d-\d\d$")
TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2}):(\d{2})"
                   r"(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?")
MIN_CELL_N = 10


def _aware(ts):
    """Parse to an AWARE datetime. Naive input is treated as UTC, which matches
    how the trade logger writes. Everything downstream compares instants."""
    m = TS_RE.search(str(ts or ""))
    if not m:
        return None
    d = m.group(1)
    dt = datetime(int(d[:4]), int(d[5:7]), int(d[8:10]),
                  int(m.group(2)), int(m.group(3)), int(m.group(4)))
    off = m.group(5)
    if off in (None, "Z", "+00:00", "+0000"):
        return dt.replace(tzinfo=timezone.utc)
    sign = 1 if off[0] == "+" else -1
    oh, om = int(off[1:3]), int(off[-2:])
    return dt.replace(tzinfo=timezone(sign * timedelta(hours=oh, minutes=om)))


def _tape_root(explicit=""):
    for r in ([explicit] if explicit else TAPE_ROOTS):
        p = os.path.expanduser(r)
        if os.path.isdir(p):
            return p
    return None


def _load_tape(root, sym, date):
    """[(aware_dt, close)] for one symbol-day, ascending."""
    day = os.path.join(root, date)
    if not os.path.isdir(day):
        return []
    out = []
    for f in os.listdir(day):
        low = f.lower()
        if not (low.startswith(sym.lower() + "_ohlc_") and low.endswith(".csv")):
            continue
        with open(os.path.join(day, f)) as fh:
            head = fh.readline().strip().split(",")
            try:
                ti, ci = head.index("timestamp"), head.index("close")
            except ValueError:
                continue
            for line in fh:
                p = line.rstrip("\n").split(",")
                if len(p) <= max(ti, ci):
                    continue
                t = _aware(p[ti])
                if t is None:
                    continue
                try:
                    out.append((t, float(p[ci])))
                except ValueError:
                    continue
    out.sort(key=lambda r: r[0])
    return out


def _price_at(tape, when):
    """Close of the last bar at or before `when`. Instant comparison only."""
    lo, hi, best = 0, len(tape) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if tape[mid][0] <= when:
            best = tape[mid][1]
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _norm_reason(r):
    r = (r or "unknown").strip().lower()
    for fam in ("bos_exit", "regime_flip", "hard_close", "trail", "target",
                "max_loss", "stop", "theta_bleed", "condor", "expiry",
                "exhaustion", "flatten"):
        if fam in r:
            return fam
    return r.split("(")[0].split("pnl=")[0].strip()[:20] or "unknown"


def _mean_ci(xs):
    n = len(xs)
    if n < 2:
        return (xs[0] if n else 0.0), 0.0, n
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return m, 1.96 * math.sqrt(var / n), n


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="a trades .db or a directory")
    ap.add_argument("--tape-root", default="")
    ap.add_argument("--horizons", default="5,15,30",
                    help="forward MINUTES after the exit")
    a = ap.parse_args(argv[1:])
    horizons = [int(h) for h in a.horizons.split(",") if h.strip()]

    root = _tape_root(a.tape_root)
    if not root:
        print("No tape root found — cannot measure what price did after the exit.")
        return 2
    p = os.path.expanduser(a.db)
    dbs = ([p] if os.path.isfile(p)
           else sorted(glob.glob(os.path.join(p, "**", "*.db"), recursive=True)))
    if not dbs:
        print(f"No .db found at {a.db}")
        return 2

    cells = collections.defaultdict(list)     # (reason, h) -> [signed % move]
    tape_cache, n_rows, no_tape, no_dir = {}, 0, 0, 0

    for d in dbs:
        try:
            conn = sqlite3.connect(f"file:{d}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT symbol, direction, exit_time, exit_reason, status "
                "FROM trades WHERE status='closed'")
        except Exception:                                        # noqa: BLE001
            continue
        for t in cur:
            n_rows += 1
            direction = str(t["direction"] or "").lower()
            if direction not in ("long", "short"):
                no_dir += 1          # neutral/condor has no directional thesis
                continue
            xt = _aware(t["exit_time"])
            if xt is None:
                continue
            sym = str(t["symbol"] or "").upper()
            # tape day is the ET date of the exit instant; derive it by scanning
            # the two candidate folders rather than assuming a UTC->ET offset
            cands = {(xt - timedelta(hours=h)).strftime("%Y-%m-%d")
                     for h in (0, 4, 5)}
            tape = []
            for dt_ in sorted(cands):
                key = (sym, dt_)
                if key not in tape_cache:
                    tape_cache[key] = _load_tape(root, sym, dt_)
                if tape_cache[key] and tape_cache[key][0][0] <= xt <= \
                        tape_cache[key][-1][0]:
                    tape = tape_cache[key]
                    break
            if not tape:
                no_tape += 1
                continue
            p0 = _price_at(tape, xt)
            if not p0 or p0 <= 0:
                no_tape += 1
                continue
            sign = 1.0 if direction == "long" else -1.0
            reason = _norm_reason(t["exit_reason"])
            for h in horizons:
                pn = _price_at(tape, xt + timedelta(minutes=h))
                if not pn or pn <= 0:
                    continue
                cells[(reason, h)].append(sign * 100.0 * (pn - p0) / p0)
        conn.close()

    if not cells:
        print(f"Nothing measured. {n_rows} closed rows, {no_tape} without usable "
              f"tape at the exit instant, {no_dir} non-directional.")
        return 2

    print(f"{len(dbs)} db(s) | tape {root} | horizons {horizons} minutes")
    print(f"closed rows {n_rows}   non-directional {no_dir} (skipped: no "
          f"directional thesis)   no tape at exit {no_tape}")
    print("\nPOSITIVE = price kept moving the way the trade wanted AFTER we were")
    print("already out. That is money left on the table by exiting.\n")

    reasons = sorted({r for r, _ in cells},
                     key=lambda r: -len(cells.get((r, horizons[0]), [])))
    print(f"{'exit reason':<16}{'h':>4} | {'post-exit move':>22} "
          f"{'min detectable':>15}")
    print("-" * 62)
    for r in reasons:
        for h in horizons:
            xs = cells.get((r, h), [])
            if len(xs) < MIN_CELL_N:
                print(f"{r:<16}{h:>4} | {'REFUSED n=' + str(len(xs)):>22}")
                continue
            m, hw, n = _mean_ci(xs)
            sd = hw * math.sqrt(n) / 1.96
            mde = (1.96 + 0.84) * sd * math.sqrt(2.0 / n)
            print(f"{r:<16}{h:>4} | {m:+.4f}% ±{hw:.4f} n={n:<4} "
                  f"{mde:+.4f}%")
        print()

    # ── the comparison the item actually asks for ───────────────────────────
    print("=" * 62)
    for h in horizons:
        bos = cells.get(("bos_exit", h), [])
        other = [v for (r, hh), xs in cells.items() if hh == h and r != "bos_exit"
                 for v in xs]
        if len(bos) < MIN_CELL_N or len(other) < MIN_CELL_N:
            print(f"h={h:>3}  REFUSED — bos n={len(bos)}, other n={len(other)}")
            continue
        bm, bhw, _ = _mean_ci(bos)
        om, ohw, _ = _mean_ci(other)
        diff = bm - om
        sep = abs(diff) > (bhw + ohw)
        print(f"h={h:>3}  bos_exit {bm:+.4f}% ±{bhw:.4f} (n={len(bos)})   "
              f"other exits {om:+.4f}% ±{ohw:.4f} (n={len(other)})")
        if not sep:
            print(f"      -> NO BOS-SPECIFIC EXCESS ({diff:+.4f}%, inside the "
                  f"bands). If both are\n         positive, that is momentum in "
                  f"the tape, not a BOS defect.")
        elif diff > 0:
            print(f"      -> BOS CUTS LIVE MOVES: {diff:+.4f}% more post-exit "
                  f"continuation than\n         other exits. The MU pattern "
                  f"generalises — BOS fires while the move runs.")
        else:
            print(f"      -> BOS EXITS LATE, if anything ({diff:+.4f}%). Price "
                  f"continues LESS after\n         a BOS than after other exits, "
                  f"so it is not cutting winners short.")
    print("=" * 62)
    print("Read the min-detectable column before calling any cell null. bos_exit")
    print("is ~40 trades lifetime, so thin cells are expected and are REFUSED")
    print("rather than reported.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
