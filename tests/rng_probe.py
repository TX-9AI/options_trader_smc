#!/usr/bin/env python3
"""
tests/rng_probe.py — v1.0 — 2026-08-06

RGM.1 probe: RUN LENGTHS of RANGING's no-bar-window fallback, and WHERE in the
session they occur. Decides between the hypothesis's branches:
  - mostly 1-TICK runs            => the input flaps on individual ticks (plumbing)
  - long runs                     => genuine warm-up or data outage
  - first-fallback p50 near 0     => benign session warm-up
  - p50 mid-session (300+)        => window LOST after being established (worse)

Extra discriminator, free from the tape: for each MID-SESSION run, the ts gap
entering the run — gap == 1 min means the tape was contiguous and the INPUT
flapped; gap > 1 min means missing bars (outage / engine-skip). Interpretation
note for THIS corpus: replay_confluence v2.1 builds `closes` as the last-25
slice of a growing frame, so it can never revert to None after bar 25 — a
mid-session fallback here can only be `atr_current` going None (or the run sits
after a tape gap).

Also reports IMPLIED crossings, counted the way veto_attribution v1.1 counts
them (a crossing exists only where the adjacent EVALUATED tick scored
nonzero; session edges and zero-to-zero neighbours contribute none), to
check the arithmetic against the 13,860 RANGING branch changes.

Read-only, stdlib only, streams one file at a time, always exits 0.
USAGE: python3 tests/rng_probe.py [--since 2026-07-13] [--top 12]

CHANGELOG
  v1.0 — 2026-08-06 — first issue. Written to answer the ONE question RGM.1 is
         blocked on: are RANGING's 11,972 fallback ticks a contiguous warm-up
         block or short isolated bursts? Adds two discriminators the original
         spec did not have: (a) the ts gap ENTERING each mid-session run, which
         separates "the tape was fine and the input flapped" (plumbing) from
         "bars were missing" (outage); (b) implied crossings counted with
         veto_attribution v1.1 semantics rather than a flat 2-per-burst, so the
         13,860 branch-change figure is checked apples-to-apples. Proven on a
         planted corpus with known run lengths before issue — this repo has a
         history of tools that were wrong in a way that read as a finding.
"""
import argparse, collections, glob, json, os, re, sys

REPLAY_GLOB = "~/day_trader_pro/reports/regime_replay_*.jsonl"
DATE_RE = re.compile(r"regime_replay_(20\d\d-\d\d-\d\d)\.jsonl$")


def _mins(ts):
    try:
        h, m = ts.split(":"); return int(h) * 60 + int(m)
    except Exception:
        return None


def _pct(sv, p):
    if not sv:
        return 0
    return sv[min(len(sv) - 1, int(round(p / 100.0 * (len(sv) - 1))))]


class Sym:
    __slots__ = ("idx", "in_run", "run_len", "run_start", "prev_ts", "gap_in",
                 "runs", "entry_x", "prev_nz")
    def __init__(self):
        self.idx = 0; self.in_run = False; self.run_len = 0
        self.run_start = 0; self.prev_ts = None; self.gap_in = None
        self.runs = 0; self.entry_x = 0; self.prev_nz = None


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default=REPLAY_GLOB)
    ap.add_argument("--since", default="")
    ap.add_argument("--top", type=int, default=12)
    a = ap.parse_args(argv[1:])

    paths = [p for p in sorted(glob.glob(os.path.expanduser(a.glob)))
             if DATE_RE.search(p)
             and (not a.since or DATE_RE.search(p).group(1) >= a.since)]
    if not paths:
        print(f"no replay files matched {a.glob}"); return 0

    run_lens, first_idx, mid_starts = [], [], []
    hist = collections.Counter()
    per_symday = collections.Counter()
    warm_runs = mid_runs = mid_contig = mid_gap = mid_unk = 0
    implied = fb_ticks = total_ticks = symdays = 0

    def close_run(s, key, interior, exit_nz=False):
        nonlocal warm_runs, mid_runs, mid_contig, mid_gap, mid_unk, implied
        run_lens.append(s.run_len)
        L = s.run_len
        hist["1" if L == 1 else "2" if L == 2 else "3-5" if L <= 5
             else "6-20" if L <= 20 else "21-60" if L <= 60 else "61+"] += 1
        if s.runs == 0:
            first_idx.append(s.run_start)
        s.runs += 1
        per_symday[key] += 1
        implied += s.entry_x + (1 if (interior and exit_nz) else 0)
        if s.run_start == 0:
            warm_runs += 1
        else:
            mid_runs += 1
            mid_starts.append(s.run_start)
            if s.gap_in is None:
                mid_unk += 1
            elif s.gap_in <= 1:
                mid_contig += 1
            else:
                mid_gap += 1
        s.in_run = False; s.run_len = 0; s.gap_in = None

    for path in paths:
        date = DATE_RE.search(path).group(1)
        st = {}
        for line in open(path, errors="ignore"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            bd = (r.get("breakdown") or {}).get("RANGING")
            if bd is None:
                continue
            sym = r.get("sym", "?")
            s = st.setdefault(sym, Sym())
            tsm = _mins(r.get("ts", ""))
            fb = (bd.get("path") == "no_window"
                  or bd.get("reason") == "no bar window")
            if fb:
                if not s.in_run:
                    s.in_run = True; s.run_len = 1; s.run_start = s.idx
                    s.gap_in = (None if (tsm is None or s.prev_ts is None)
                                else tsm - s.prev_ts)
                    s.entry_x = 1 if s.prev_nz else 0
                else:
                    s.run_len += 1
                fb_ticks += 1
            else:
                nz = ((r.get("scores") or {}).get("RANGING") or 0.0) > 0.001
                if s.in_run:
                    close_run(s, (date, sym), interior=True, exit_nz=nz)
                s.prev_nz = nz
            s.prev_ts = tsm
            s.idx += 1
            total_ticks += 1
        for sym, s in st.items():
            symdays += 1
            if s.in_run:
                close_run(s, (date, sym), interior=False)

    runs = len(run_lens)
    rs, fi, ms = sorted(run_lens), sorted(first_idx), sorted(mid_starts)
    print(f"files: {len(paths)}  ({DATE_RE.search(paths[0]).group(1)} .. "
          f"{DATE_RE.search(paths[-1]).group(1)})")
    print(f"symbol-days: {symdays}   with >=1 fallback: {len(per_symday)}")
    print(f"fallback ticks: {fb_ticks} / {total_ticks} "
          f"({100.0*fb_ticks/max(1,total_ticks):.1f}%)   runs: {runs}")
    print(f"implied crossings vs veto_attribution (nonzero-adjacent only): {implied}")
    print()
    print("RUN LENGTHS")
    for b in ("1", "2", "3-5", "6-20", "21-60", "61+"):
        print(f"  {b:>5} ticks: {hist[b]:6d}  ({100.0*hist[b]/max(1,runs):.1f}%)")
    print(f"  p50={_pct(rs,50)}  p90={_pct(rs,90)}  max={rs[-1] if rs else 0}")
    print()
    print("WHERE THEY START")
    print(f"  warm-up runs (start at tick 0): {warm_runs}   mid-session: {mid_runs}")
    print(f"  mid-session tape entering the run: contiguous(1min)={mid_contig}  "
          f"gapped(>1min)={mid_gap}  unknown={mid_unk}")
    print(f"  FIRST fallback per symbol-day: p50={_pct(fi,50)}  "
          f"p90={_pct(fi,90)}  max={fi[-1] if fi else 0}")
    print(f"  ALL mid-session run starts:    p50={_pct(ms,50)}  p90={_pct(ms,90)}")
    print()
    print(f"TOP {a.top} symbol-days by fallback runs")
    for (d, sym), n in per_symday.most_common(a.top):
        print(f"  {d} {sym:>6}: {n} runs")
    return 0


if __name__ == "__main__":
    try:
        rc = main(sys.argv)
    except BrokenPipeError:
        # piping into `head` closes stdout early; that is not a failure and must
        # not print a traceback over the numbers or return non-zero.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        rc = 0
    sys.exit(rc)
