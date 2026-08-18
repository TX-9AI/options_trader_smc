#!/usr/bin/env python3
"""
tests/gap_backfill.py — v1.1 — 2026-08-01

BACKFILL THE OVERNIGHT GAP (item A2.6). Read-only over the tape; writes one
lookup file.

v1.1 — 2026-08-01 — TAPE ROOT CORRECTED. v1.0 defaulted to
       ~/day_trader_pro/data/OHLC and ./data/OHLC; neither exists. The
       consolidated tape root is ~/day_trader_pro/ohlc/<date>/ (validate_regime.sh
       v2.1, regime_backfill v1.1) — note that ~/day_trader_pro/data/ holds only
       instance_map.json, mock_state.json and report.json, and the harvest roots
       are its SIBLINGS. Mine, caught on the box before it ever ran.

WHY THIS EXISTS
    The overnight gap enters ATR through true range (`prev_close = close.shift(1)`
    in utils.math_utils.atr_series, and 5m is continuous across sessions — only 1m
    is session-scoped per market_data v3.1). So the first 5m bar after the open
    carries |high - prev_close| and a large gap spikes ATR immediately. But the
    gap is MEASURED nowhere. It enters as an anonymous ATR spike that decays over
    14 periods and the magnitude is discarded.

    Unlike rrr / closes_beyond / paused_trend, this one is BACKFILLABLE: prior
    close and today's open are both already on disk for every session, so no
    sessions are lost waiting for it to accrue.

WHAT IT EMITS, AND WHY THE DIRECTION FIELD IS SHAPED THIS WAY
    Per (date, symbol):
        gap_pct       (open - prior_close) / prior_close * 100
        prior_dir_70  sign of the prior session's LAST 70 MINUTES
        prior_dir_day sign of the prior session's whole-session net move
        gap_class     CONT / REV / FLAT, computed against prior_dir_70

    The 70-minute window is not arbitrary. The gap perturbs ADX-14 on the 5m
    frame, whose window IS 70 minutes, so what determines whether the boundary
    bar's directional movement REINFORCES or CANCELS the accumulated +DM/-DM is
    the direction of the last ~14 5m bars — not the direction of the whole prior
    session. prior_dir_day is emitted alongside so the choice can be checked
    rather than trusted.

    Measured mechanism this classification is built to test (ablation, 2026-08-01,
    synthetic two-session fixture, real trend_engine, only the boundary changed):
        zero gap                        ADX 46.4 @09:40 -> 16.3 @12:30
        gap WITH prior direction        ADX 52.0 @09:40 -> 17.8 @12:30  (inflated)
        gap COUNTER to prior direction  ADX 26.1 @09:40 -> 14.9 @12:30  (SUPPRESSED)
    A reversal gap DEPRESSING ADX is the fingerprint no other A2 hypothesis
    predicts — horizon co-truth and the opening-drive story can only ADD
    violations, never produce a deficit. That is what tests/a2_partition.py reads.

TAPE PARSING
    Uses load_ohlc from tests/replay_confluence.py rather than a second reader,
    so gap numbers and replay scores are derived from an identical view of the
    tape (WORKING_AGREEMENT §7 — one owner per file, no second lineage). That
    also means zero-range bars are dropped here exactly as the replay drops them.

USAGE (single line, control box, repo root)
    python3 tests/gap_backfill.py
    python3 tests/gap_backfill.py --ohlc-root ~/day_trader_pro/data/OHLC --out ~/day_trader_pro/reports/gap_pct.json

Read-only over the tape. Opens no trades.db, places no orders.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.replay_confluence import load_ohlc  # noqa: E402

# The consolidated tape root. NOT ~/day_trader_pro/data/ — that holds only
# instance_map.json / mock_state.json / report.json; ohlc/, trades/, reports/ and
# the rest are SIBLINGS of it, one folder per KIND of artifact.
DEFAULT_ROOTS = [
    "~/day_trader_pro/ohlc",
    "./ohlc",
]
DEFAULT_OUT = "~/day_trader_pro/reports/gap_pct.json"

# The gap perturbs ADX-14 on the 5m frame = a 70-minute window. Direction of the
# prior session's last 70 minutes is what the boundary bar's DM adds to or cancels.
PRIOR_DIR_MINUTES = 70


def _sessions(root: str) -> list:
    """Ascending date folders under the OHLC root."""
    if not os.path.isdir(root):
        return []
    return sorted(d for d in os.listdir(root)
                  if os.path.isdir(os.path.join(root, d)) and d[:2] == "20")


def _symbol_files(day_dir: str) -> dict:
    """{SYMBOL: path} for every OHLC file in a date folder. Non-tape siblings
    (fleet_trades_*.csv and friends) are rejected by load_ohlc, not guessed at."""
    out = {}
    for f in sorted(os.listdir(day_dir)):
        if "_ohlc_" not in f.lower() or not f.lower().endswith(".csv"):
            continue
        out[f.split("_ohlc_")[0].upper()] = os.path.join(day_dir, f)
    return out


def _direction(df, minutes: int):
    """Sign of the net move over the last `minutes` of a session, as -1/0/+1,
    plus the move itself. Returns (sign, move_pct)."""
    if df is None or df.empty:
        return 0, 0.0
    tail = df.iloc[-minutes:] if len(df) > minutes else df
    move = float(tail["close"].iloc[-1]) - float(tail["close"].iloc[0])
    base = max(abs(float(tail["close"].iloc[0])), 1e-9)
    move_pct = 100.0 * move / base
    if move_pct > 0:
        return 1, move_pct
    if move_pct < 0:
        return -1, move_pct
    return 0, 0.0


def classify(gap_pct: float, prior_dir: int, flat_pct: float) -> str:
    """CONT when the gap extends the prior direction, REV when it opposes it,
    FLAT when the gap is too small to move ADX either way. A prior direction of
    exactly 0 leaves CONT/REV undefined — say so rather than guess."""
    if abs(gap_pct) < flat_pct:
        return "FLAT"
    if prior_dir == 0:
        return "UNDIRECTED"
    gap_dir = 1 if gap_pct > 0 else -1
    return "CONT" if gap_dir == prior_dir else "REV"


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ohlc-root", default="", help="OHLC root; default = auto-discover")
    ap.add_argument("--out", default=DEFAULT_OUT, help="output JSON path")
    ap.add_argument("--flat-pct", type=float, default=0.10,
                    help="|gap_pct| below this is FLAT (default 0.10)")
    a = ap.parse_args(argv[1:])

    roots = ([a.ohlc_root] if a.ohlc_root else DEFAULT_ROOTS)
    root = next((os.path.expanduser(r) for r in roots
                 if os.path.isdir(os.path.expanduser(r))), None)
    if root is None:
        print("No OHLC root found. Looked in:")
        for r in roots:
            print(f"   {r}")
        return 2

    dates = _sessions(root)
    if len(dates) < 2:
        print(f"Need at least 2 session folders to compute a gap; found {len(dates)} in {root}")
        return 2

    print(f"OHLC root : {root}")
    print(f"sessions  : {len(dates)}  ({dates[0]} .. {dates[-1]})")
    print(f"flat band : |gap_pct| < {a.flat_pct:.2f}%\n")

    # prior session's frames, carried forward per symbol so a symbol that skips a
    # day still gaps against the session it actually last traded — not against a
    # hole. The date it gapped FROM is recorded so this is auditable.
    prev = {}          # SYMBOL -> (date, df)
    out = {}
    counts = {"CONT": 0, "REV": 0, "FLAT": 0, "UNDIRECTED": 0}
    abs_gaps = []
    skipped_no_prior = 0

    for date in dates:
        day_dir = os.path.join(root, date)
        files = _symbol_files(day_dir)
        day_rec = {}
        for sym, path in files.items():
            df = load_ohlc(path)
            if df is None or df.empty:
                continue
            prior = prev.get(sym)
            if prior is not None:
                prior_date, pdf = prior
                prior_close = float(pdf["close"].iloc[-1])
                today_open = float(df["open"].iloc[0])
                if prior_close > 0:
                    gap_pct = 100.0 * (today_open - prior_close) / prior_close
                    d70, m70 = _direction(pdf, PRIOR_DIR_MINUTES)
                    dday, mday = _direction(pdf, len(pdf))
                    klass = classify(gap_pct, d70, a.flat_pct)
                    day_rec[sym] = {
                        "gap_pct": round(gap_pct, 4),
                        "prior_date": prior_date,
                        "prior_close": round(prior_close, 4),
                        "open": round(today_open, 4),
                        "prior_dir_70": d70,
                        "prior_move_70_pct": round(m70, 4),
                        "prior_dir_day": dday,
                        "prior_move_day_pct": round(mday, 4),
                        "gap_class": klass,
                    }
                    counts[klass] += 1
                    abs_gaps.append(abs(gap_pct))
            else:
                skipped_no_prior += 1
            prev[sym] = (date, df)
        if day_rec:
            out[date] = day_rec

    if not abs_gaps:
        print("No gaps computed — check the OHLC layout under the root.")
        return 2

    srt = sorted(abs_gaps)

    def q(p):
        return srt[min(len(srt) - 1, max(0, int(round(p / 100.0 * (len(srt) - 1)))))]

    print(f"session-symbols with a gap : {len(abs_gaps)}")
    print(f"first-appearance skips     : {skipped_no_prior} (no prior session for that symbol)")
    print("\n|gap_pct| distribution")
    print(f"    p10={q(10):.3f}  p25={q(25):.3f}  p50={q(50):.3f}  "
          f"p75={q(75):.3f}  p90={q(90):.3f}  max={srt[-1]:.3f}")
    print("\nclassification against the prior session's last 70 minutes")
    for k in ("CONT", "REV", "FLAT", "UNDIRECTED"):
        n = counts[k]
        share = 100.0 * n / len(abs_gaps)
        print(f"    {k:<11} {n:>6}   {share:5.1f}%")
    if counts["FLAT"] < 0.05 * len(abs_gaps):
        print(f"\n    NOTE: the FLAT bucket is only {counts['FLAT']} session-symbols. It is the "
              f"\n    control cell in a2_partition — if it stays this thin, raise --flat-pct "
              f"\n    toward p25 ({q(25):.3f}) so the control has population to read.")

    dest = os.path.expanduser(a.out)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w") as fh:
        json.dump({"flat_pct": a.flat_pct,
                   "prior_dir_minutes": PRIOR_DIR_MINUTES,
                   "ohlc_root": root,
                   "sessions": out}, fh, indent=1, sort_keys=True)
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
