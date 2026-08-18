#!/usr/bin/env python3
"""
tests/engine_arms.py — v1.1 — 2026-08-13

v1.1 — 2026-08-13 — TWO DEFECTS FOUND ON THE FIRST REAL RUN.
       (a) SPLIT SEMANTICS. `--split` was documented as "last session of ARM A"
           but the code assigns `d < split` to A, so `--split 2026-07-27` put
           the 07-27 SESSION in arm B. Deploys land in the EVENING (the 07-23
           deploy was confirmed 21:22-21:51), so the boxes almost certainly
           traded 07-27 on the PRIMITIVE engine. `--split` is now documented
           and defaulted as the FIRST SESSION OF ARM B = 2026-07-28.
       (b) THE RULESET AUDIT LIED ABOUT ITS OWN ABSENCE. It printed "journal
           starts later than these sessions" whenever no stamps were found —
           but the journal covers 07-20 onward and the real cause is that the
           `ruleset` field postdates those rows. It reported a wrong REASON,
           which is the renders-cleanly-means-something-else failure this repo
           exists to catch, committed inside the audit built to catch it. Now
           distinguishes no-directory / no-files / files-present-field-absent.
v1.0 — 2026-08-13 — first cut.

DID THE CONFLUENCE EXCAVATION TRADE BETTER THAN THE PRIMITIVE L1 IT REPLACED?

Operator, 2026-08-13: *"the layer one engine was arguably trading better than
the upgraded confluence engine"* and *"the earliest trading on the primitive
engine was wildly successful, but I intentionally steered it away with the goal
of developing the confluence tests that made prediction a priority."*

`92c89d7` (2026-07-27) — "regime_confluence v1.3: excavate the confluence
engine — rebuild _sweep/_breakout/_ranging/_compression as accumulating
evidence, wire trend into sweep, decouple the crossings axis" — is the change
under test. The 08-05 volatility contraction is EIGHT DAYS LATER, so for once
the engine change and the tape change are separable.

    ARM A (primitive)  sessions on or before the split date
    ARM B (excavated)  sessions after it, STOPPING BEFORE 2026-08-05

⚠️ ARM B IS DELIBERATELY CUT AT 08-04. Including 08-05 onward would let the
   volatility contraction answer a question about the engine — median available
   movement fell 15-25%% in EVERY HOUR after that date. The standing rule is
   that no P&L comparison may span 08-05 unnormalised. Here we do not span it
   at all, and we normalise anyway (below), because mid-July and early-August
   tape differ even without the cliff.

────────────────────────────────────────────────────────────────────────────
WHAT IT WILL AND WILL NOT TELL YOU
────────────────────────────────────────────────────────────────────────────
This is a NATURAL EXPERIMENT, not a controlled one. Between the arms, other
things also changed — the 07-24 runaway reroute (runaway handed to CONTINUATION
instead of SWEEP) sits INSIDE arm A, and CNT/SWP/LIQ work landed later. So a
difference here is attributable to "the system as it stood", not to
regime_confluence v1.3 alone. The `ruleset` audit below reports which commits
each arm actually ran, because BUILT != PUSHED != BAKED and a commit dated
07-27 may not have reached the boxes that day.

THREE THINGS THAT WOULD MAKE THE RESULT A MIRAGE, ALL REPORTED, NONE HIDDEN:
  1. UNEQUAL OPPORTUNITY. Fixed by normalising: every arm's net-per-trade is
     ALSO expressed per unit of available movement, computed from the same OHLC
     the fleet traded. A tape that simply moved more will produce more dollars
     from an identical engine.
  2. UNEQUAL FLEET. If arm A ran 8 boxes and arm B ran 15, per-trade figures
     are comparable and per-SESSION figures are not. Both are printed, and the
     symbol count per arm is printed next to them.
  3. MISSING TELEMETRY. `max_premium_seen` did not exist in the earliest
     schema. Rows without it CANNOT contribute MFE, never-favorable or capture
     — so those metrics are computed on a SUBSET, and the subset size is
     printed on every line that uses it. Nothing is silently dropped; the
     excursion report's `usable()` filter drops such rows without making the
     omission the headline, which is exactly how an arm can look thin when it
     is merely unmeasured.

READ-ONLY. stdlib only. Reads trade DBs (including the pre-07-23 archive), OHLC
CSVs, and the signal journal for ruleset stamps. Writes nothing, touches no
fleet, no live path.

USAGE (control)
    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python tests/engine_arms.py
    ... --split 2026-07-27 --b-end 2026-08-04
    ... --a-start 2026-07-20          # restrict A to the max_premium_seen era
"""

import argparse
import collections
import csv
import datetime as dt
import glob
import json
import os
import sqlite3
import sys

DTP = os.path.expanduser("~/day_trader_pro")
TRADES = os.path.join(DTP, "trades")
ARCHIVE = os.path.join(TRADES, "_archive_pre_2026-07-23")
JOURNAL = os.path.join(DTP, "signal_journal")
# symbol_edge.py resolves OHLC here; WORKING_AGREEMENT S14 mentions data/OHLC.
# Probe both rather than guess, and SAY which one answered.
OHLC_CANDIDATES = (os.path.join(DTP, "ohlc"),
                   os.path.join(DTP, "data", "OHLC"),
                   os.path.join(DTP, "data", "ohlc"))

MIN_CELL_N = 40          # same floor the excursion report pre-registered
MIN_SESSIONS = 3
MOVE_HORIZON = 20        # bars, matching SEL.1's default


def pctile(v, q):
    v = sorted(x for x in v if x is not None)
    return v[min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))] if v else None


def mean(v):
    v = [x for x in v if x is not None]
    return sum(v) / len(v) if v else None


# ── sessions ─────────────────────────────────────────────────────────────────

def all_sessions():
    """Every dated trade folder, live and archived, as {date: path}."""
    out = {}
    for root in (ARCHIVE, TRADES):
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            if len(name) == 10 and name[4] == "-":
                out[name] = os.path.join(root, name)
    return out


def load_trades(day_dir):
    rows = []
    for path in sorted(glob.glob(os.path.join(day_dir, "*.db"))):
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cols = {r[1] for r in conn.execute("PRAGMA table_info(trades)")}
            got = [dict(r) for r in conn.execute("SELECT * FROM trades")]
            conn.close()
        except Exception:                                      # noqa: BLE001
            continue
        for d in got:
            if str(d.get("status") or "") != "closed":
                continue
            d["_has_mps"] = "max_premium_seen" in cols
            rows.append(d)
    return rows


def fnum(row, key):
    try:
        v = row.get(key)
        return None if v is None else float(v)
    except Exception:                                          # noqa: BLE001
        return None


def excursion(row):
    """(mfe_frac, realized_frac) as fractions of entry premium, or (None, r)."""
    entry = fnum(row, "entry_premium")
    hi = fnum(row, "max_premium_seen")
    pnl = fnum(row, "pnl_usd") or 0.0
    if not entry or entry <= 0:
        return None, None
    mfe = (hi - entry) / entry if hi is not None else None
    return mfe, pnl


# ── available movement, from OHLC only (no replay-jsonl dependency) ──────────

def ohlc_root():
    for c in OHLC_CANDIDATES:
        if os.path.isdir(c):
            return c
    return None


def available_move(dates, root):
    """Median max favourable excursion over MOVE_HORIZON bars, per session.

    Deliberately computed from the OHLC CSVs ALONE. symbol_edge's version keys
    off regime_replay_<date>.jsonl, which does not exist for the mid-July
    sessions — depending on it would make the primitive arm look empty for a
    reason that has nothing to do with the engine.

    Returns {date: median_pct_move}. A date with no OHLC returns no key, and
    the caller reports the coverage rather than silently averaging fewer days.
    """
    out = {}
    if not root:
        return out
    for date in dates:
        moves = []
        for path in sorted(glob.glob(os.path.join(root, date, "*.csv"))):
            bars = []
            try:
                with open(path, encoding="utf-8") as fh:
                    for r in csv.DictReader(fh):
                        try:
                            bars.append((float(r["high"]), float(r["low"]),
                                         float(r.get("open") or r["close"])))
                        except Exception:                      # noqa: BLE001
                            continue
            except Exception:                                  # noqa: BLE001
                continue
            for i in range(0, max(0, len(bars) - MOVE_HORIZON)):
                px = bars[i][2]
                if px <= 0:
                    continue
                w = bars[i:i + MOVE_HORIZON + 1]
                hi = max(b[0] for b in w)
                lo = min(b[1] for b in w)
                moves.append(max((hi - px) / px, (px - lo) / px) * 100.0)
        m = pctile(moves, .5)
        if m:
            out[date] = m
    return out


def rulesets(dates):
    """Distinct `ruleset` commit stamps per arm, plus WHY none were found.

    v1.1 — returns (counter, reason). v1.0 collapsed three different absences
    into one sentence that named the wrong one.
    """
    seen = collections.Counter()
    dirs = files = 0
    for date in dates:
        if os.path.isdir(os.path.join(JOURNAL, date)):
            dirs += 1
            files += len(glob.glob(os.path.join(JOURNAL, date, "*.jsonl")))
    for date in dates:
        for path in sorted(glob.glob(os.path.join(JOURNAL, date, "*.jsonl"))):
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    for n, line in enumerate(fh):
                        if n > 400:            # a stamp is constant per process
                            break
                        try:
                            r = json.loads(line)
                        except Exception:      # noqa: BLE001
                            continue
                        rs = r.get("ruleset")
                        if rs:
                            seen[str(rs)[:12]] += 1
            except Exception:                  # noqa: BLE001
                continue
    if seen:
        return seen, ""
    if not dirs:
        return seen, "no journal directory for any session in this arm"
    if not files:
        return seen, f"{dirs} journal dir(s) present but EMPTY"
    return seen, (f"{files} journal file(s) across {dirs} session(s) present, "
                  f"but NO `ruleset` field in them — the stamp postdates these "
                  f"rows (signal_journal v1.2). The split date stays an "
                  f"ASSUMPTION for this arm.")


# ── report ───────────────────────────────────────────────────────────────────

def arm_stats(rows):
    net = sum(fnum(r, "pnl_usd") or 0.0 for r in rows)
    wins = sum(1 for r in rows if (fnum(r, "pnl_usd") or 0.0) > 0)
    with_mps = [r for r in rows if r.get("_has_mps")
                and fnum(r, "max_premium_seen") is not None]
    nf, caps = 0, []
    for r in with_mps:
        mfe, pnl = excursion(r)
        if mfe is None:
            continue
        if mfe <= 0.02:
            nf += 1
        if pnl and pnl > 0 and mfe and mfe > 0:
            entry = fnum(r, "entry_premium") or 0
            if entry > 0:
                caps.append(min(1.0, (pnl / (entry * 100.0)) / mfe)
                            if mfe else None)
    return {
        "n": len(rows), "net": net,
        "per_trade": net / len(rows) if rows else None,
        "win": 100.0 * wins / len(rows) if rows else None,
        "n_mps": len(with_mps),
        "nf_rate": 100.0 * nf / len(with_mps) if with_mps else None,
        "capture": pctile([c for c in caps if c is not None], .5),
        "syms": len({r.get("symbol") for r in rows}),
    }


def line(label, s, sessions, move):
    per_move = (s["per_trade"] / move) if (s["per_trade"] is not None
                                           and move) else None
    print(f"  {label:22}{s['n']:>6}{sessions:>6}{s['syms']:>6}"
          f"{s['net']:>11,.0f}"
          f"{(s['per_trade'] if s['per_trade'] is not None else 0):>9,.1f}"
          f"{(s['win'] if s['win'] is not None else 0):>7.0f}%"
          f"{(f'{per_move:,.1f}' if per_move is not None else '—'):>10}"
          f"{(f'{nfr:.0f}%' if (nfr := s['nf_rate']) is not None else '—'):>8}"
          f"{s['n_mps']:>7}")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="2026-07-28",
                    help="FIRST session of ARM B. NOT the commit date: a commit "
                         "dated D bakes on the EVENING of D, so session D still "
                         "ran the old engine. 92c89d7 landed 07-27 -> 07-28.")
    ap.add_argument("--a-start", default="",
                    help="earliest ARM A session (default: everything on disk)")
    ap.add_argument("--b-end", default="2026-08-04",
                    help="last ARM B session — DO NOT cross 2026-08-05")
    ap.add_argument("--min-n", type=int, default=MIN_CELL_N)
    a = ap.parse_args(argv[1:])

    sessions = all_sessions()
    if not sessions:
        print(f"no dated trade folders under {TRADES}")
        return 0

    a_dates = sorted(d for d in sessions
                     if d < a.split and (not a.a_start or d >= a.a_start))
    b_dates = sorted(d for d in sessions if a.split <= d <= a.b_end)

    root = ohlc_root()
    mv_a = available_move(a_dates, root)
    mv_b = available_move(b_dates, root)
    move_a, move_b = pctile(list(mv_a.values()), .5), pctile(list(mv_b.values()), .5)

    rows_a, rows_b = [], []
    for d in a_dates:
        rows_a += load_trades(sessions[d])
    for d in b_dates:
        rows_b += load_trades(sessions[d])

    print("=" * 86)
    print("  ENGINE ARMS — primitive L1 vs the 07-27 confluence excavation")
    print(f"  ARM A {a_dates[0] if a_dates else '—'}..{a_dates[-1] if a_dates else '—'}"
          f"  ({len(a_dates)} sessions)   "
          f"ARM B {b_dates[0] if b_dates else '—'}..{b_dates[-1] if b_dates else '—'}"
          f"  ({len(b_dates)} sessions)")
    print(f"  OHLC root: {root or 'NOT FOUND — normalisation unavailable'}")
    print(f"  available move (median %, {MOVE_HORIZON}-bar): "
          f"A {move_a if move_a else float('nan'):.3f} on {len(mv_a)}/{len(a_dates)} days"
          f"   B {move_b if move_b else float('nan'):.3f} on {len(mv_b)}/{len(b_dates)} days")
    if not move_a or not move_b:
        print("  ⚠️ NORMALISED COLUMN UNAVAILABLE for at least one arm — read the")
        print("     raw per-trade figures knowing the tape is NOT controlled for.")
    print("=" * 86)

    if not rows_a or not rows_b:
        print("\n  one arm is empty — cannot compare. ABSENT MEASUREMENT, not a null.")
        return 0

    print(f"\n  {'arm':22}{'n':>6}{'sess':>6}{'syms':>6}{'net$':>11}"
          f"{'$/trade':>9}{'win':>8}{'$/move':>10}{'nf%':>8}{'n(mfe)':>7}")
    line("A primitive", arm_stats(rows_a), len(a_dates), move_a)
    line("B excavated", arm_stats(rows_b), len(b_dates), move_b)
    print("\n  $/move = net per trade divided by that arm's median available")
    print("  movement. It is the column to read: raw $/trade lets the TAPE")
    print("  answer a question about the ENGINE. nf% = never-favorable (MFE")
    print("  <= +2%), computed only on n(mfe) rows — the rest predate the")
    print("  max_premium_seen column and are UNMEASURED, not favorable.")

    for key, title in (("strategy", "BY STRATEGY"), ("setup_type", "BY SETUP TYPE")):
        print(f"\n  {'-' * 82}\n  {title}")
        print(f"  {'cell':22}{'n':>6}{'sess':>6}{'syms':>6}{'net$':>11}"
              f"{'$/trade':>9}{'win':>8}{'$/move':>10}{'nf%':>8}{'n(mfe)':>7}")
        names = sorted({str(r.get(key) or "?") for r in rows_a + rows_b})
        for nm in names:
            for tag, rows, dates, mv in (("A", rows_a, a_dates, move_a),
                                         ("B", rows_b, b_dates, move_b)):
                sub = [r for r in rows if str(r.get(key) or "?") == nm]
                if not sub:
                    continue
                sess = len({str(r.get("entry_time") or "")[:10] for r in sub})
                s = arm_stats(sub)
                label = f"{tag} {nm[:19]}"
                line(label, s, sess, mv)
                if s["n"] < a.min_n or sess < MIN_SESSIONS:
                    print(f"  {'':22}   <- UNDERPOWERED (n<{a.min_n} or "
                          f"sessions<{MIN_SESSIONS}). ABSENT MEASUREMENT, not a null.")

    print(f"\n  {'-' * 82}\n  RULESET AUDIT — which commits each arm ACTUALLY ran")
    print("  BUILT != PUSHED != BAKED. A commit dated inside an arm may not have")
    print("  reached the boxes that day, and the split date is an assumption")
    print("  until these stamps confirm it.")
    for tag, dates in (("A", a_dates), ("B", b_dates)):
        rs, why = rulesets(dates)
        if not rs:
            print(f"    arm {tag}: {why}")
        else:
            top = ", ".join(f"{k} x{v}" for k, v in rs.most_common(6))
            print(f"    arm {tag}: {top}")

    print(f"\n{'=' * 86}")
    print("  ⚠️ NATURAL EXPERIMENT. The 07-24 runaway reroute sits INSIDE arm A,")
    print("     and CNT/SWP/LIQ work landed after arm B. A difference here is")
    print("     attributable to THE SYSTEM AS IT STOOD, not to regime_confluence")
    print("     v1.3 alone. Read $/move, check the ruleset stamps, and treat a")
    print("     cell flagged UNDERPOWERED as unmeasured.")
    print("=" * 86)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
