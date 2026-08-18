#!/usr/bin/env python3
# tests/regime_backfill.py — options_trader_v3 — v1.2
# v1.2 — 2026-08-01 — --warm-sessions PASSTHROUGH. This module invoked
#   replay_confluence without it, so EVERY diary, backfill and downstream
#   analysis run has used the harness default — which was 5, a depth that
#   starves the 15m frame the calibration now depends on (config v4.1 raises
#   15m to 150 bars = ~5.8 sessions). The harness default moves to 8 in v2.2;
#   this makes the depth EXPLICIT and overridable from the whole chain
#   (validate_regime.sh -> here -> replay_confluence) instead of silently
#   inherited. Recorded in the per-date banner so a corpus can be traced back to
#   the depth it was built at.
# v1.1 — 2026-07-14 — LAYOUT CONSOLIDATION: tape root defaults to
#   ~/day_trader_pro/ohlc (dated subfolders, <SYM>_ohlc_<date>.csv — legacy
#   _OHLC_ names still accepted), replay jsonl now written under reports/
#   (new --reports arg), diary default moves to reports/. Logic unchanged.
# v1.0 — 2026-07-11 — NEW FILE. Failsafe backfill for the manual regime replay.
#   The regime replay is MANUAL (you review each day). This catches up any days
#   whose OHLC tape harvest already collected but that were never replayed/diaried.
#
#   Worklist = the DISK: every data/harvest/<date>/ folder that actually contains
#   *_OHLC_*.csv. A date with no tape is never a candidate (no empty runs). Order-
#   independent: a gap filled weeks late slots into its correct chronological row,
#   because the diary is date-keyed (regime_diary.py upserts).
#
#   Default: skip any date already present in the diary — only gaps are filled.
#   --rebuild: re-run every candidate date regardless (use after a threshold change).
#
#   For each date to process it runs, in-process:
#     replay_confluence  -> writes regime_replay_<date>.jsonl next to that day's tape
#     regime_diary       -> upserts that date's row (one per date, no duplicates)
#
#   Usage:
#     python -m tests.regime_backfill                 # fill all diary gaps that have tape
#     python -m tests.regime_backfill --rebuild       # re-score every day that has tape
#     python -m tests.regime_backfill --from 2026-07-01 --to 2026-07-11   # bound the scan
#     python -m tests.regime_backfill --dry-run       # list what WOULD run, do nothing

from __future__ import annotations
import argparse, glob, json, os, re, subprocess, sys
from typing import List, Optional, Set

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def dates_with_tape(harvest_root: str) -> List[str]:
    """Every <date> folder under harvest that holds at least one *_OHLC_*.csv."""
    out = []
    if not os.path.isdir(harvest_root):
        return out
    for name in sorted(os.listdir(harvest_root)):
        if not _DATE_RE.match(name):
            continue
        day_dir = os.path.join(harvest_root, name)
        if not os.path.isdir(day_dir):
            continue
        if (glob.glob(os.path.join(day_dir, "*_ohlc_*.csv"))
                or glob.glob(os.path.join(day_dir, "*_OHLC_*.csv"))):
            out.append(name)
    return out


def dates_in_diary(diary_dir: str) -> Set[str]:
    jsonl = os.path.join(diary_dir, "regime_diary.jsonl")
    have: Set[str] = set()
    if os.path.isfile(jsonl):
        with open(jsonl) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        d = json.loads(line).get("date")
                        if d:
                            have.add(d)
                    except json.JSONDecodeError:
                        pass
    return have


def _run(mod_args: List[str]) -> int:
    """Invoke a sibling module as a subprocess so one bad day never aborts the batch."""
    return subprocess.call([sys.executable, "-m"] + mod_args)


def process_date(date: str, harvest_root: str, diary_dir: str,
                 reports_dir: str, warm_sessions: Optional[int] = None) -> bool:
    day_dir = os.path.join(harvest_root, date)
    os.makedirs(reports_dir, exist_ok=True)
    log = os.path.join(reports_dir, f"regime_replay_{date}.jsonl")
    warm_note = f"  (warm-sessions {warm_sessions})" if warm_sessions is not None else ""
    print(f"\n=== {date} ==={warm_note}")
    mod_args = ["tests.replay_confluence", day_dir, "--no-v13", "--jsonl", log]
    if warm_sessions is not None:
        mod_args += ["--warm-sessions", str(warm_sessions)]
    rc = _run(mod_args)
    if rc not in (0, 2):   # 0=all pass, 2=ran but an acceptance check failed (still valid data)
        print(f"  replay failed (rc={rc}) — skipping diary for {date}")
        return False
    if not os.path.isfile(log):
        print(f"  no tick log produced for {date} — skipping diary")
        return False
    _run(["tests.regime_diary", "--log", log, "--diary-dir", diary_dir])
    return True


def main():
    ap = argparse.ArgumentParser(description="Failsafe backfill for the manual regime replay")
    ap.add_argument("--harvest", default=os.path.expanduser("~/day_trader_pro/ohlc"))
    ap.add_argument("--diary-dir", default=os.path.expanduser("~/day_trader_pro/reports"))
    ap.add_argument("--reports", default=os.path.expanduser("~/day_trader_pro/reports"))
    ap.add_argument("--from", dest="date_from", default=None, help="lower bound YYYY-MM-DD (incl.)")
    ap.add_argument("--to", dest="date_to", default=None, help="upper bound YYYY-MM-DD (incl.)")
    ap.add_argument("--rebuild", action="store_true", help="re-run even dates already in the diary")
    ap.add_argument("--warm-sessions", type=int, default=None, dest="warm_sessions",
                    help="prior sessions of tape to prepend so the resampled HTF "
                         "frames warm (passed through to replay_confluence; its "
                         "own default applies when omitted)")
    ap.add_argument("--dry-run", action="store_true", help="list what would run; do nothing")
    args = ap.parse_args()

    have_tape = dates_with_tape(args.harvest)
    if args.date_from:
        have_tape = [d for d in have_tape if d >= args.date_from]
    if args.date_to:
        have_tape = [d for d in have_tape if d <= args.date_to]

    if not have_tape:
        print(f"no dates with OHLC tape under {args.harvest} — nothing to run")
        sys.exit(0)

    already = dates_in_diary(args.diary_dir)
    todo = have_tape if args.rebuild else [d for d in have_tape if d not in already]
    skipped = [] if args.rebuild else [d for d in have_tape if d in already]

    print(f"harvest tape dates: {len(have_tape)}  |  already in diary: {len(already & set(have_tape))}"
          f"  |  to process: {len(todo)}"
          + ("  [--rebuild: all]" if args.rebuild else ""))
    if skipped:
        print(f"skip (already in diary): {', '.join(skipped)}")
    if not todo:
        print("nothing to backfill — every dated tape is already in the diary.")
        sys.exit(0)
    print(f"will process: {', '.join(todo)}")

    if args.dry_run:
        print("\n[dry-run] no work done.")
        sys.exit(0)

    ok = 0
    for d in todo:
        if process_date(d, args.harvest, args.diary_dir, args.reports,
                        args.warm_sessions):
            ok += 1
    print(f"\nbackfill complete: {ok}/{len(todo)} dates diaried.")
    sys.exit(0)


if __name__ == "__main__":
    main()
