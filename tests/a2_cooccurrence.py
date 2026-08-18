# options_trader_v3/tests/a2_cooccurrence.py — v1.2
# v1.2 — 2026-08-04 — SLIM AT PARSE TIME. devtools option 47 was SIGKILLed by
#        the OOM killer (`Killed`, rc 137, no traceback and no output) once the
#        replay corpus reached 17 sessions: load() held EVERY field of every
#        tick and segments() then copied them all again per symbol. Records are
#        now reduced to the five keys this file actually reads. Same failure and
#        same fix as ramp_calibration v1.2, which died producing no output on a
#        13-session run. No analysis changes — the dropped fields were never read.
# v1.1 — 2026-07-22 — auto-discovery of the replay jsonl (validate_regime.sh
#        v2.1 consolidated products to ~/day_trader_pro/reports/; the old
#        data/harvest/<date>/ path is legacy). Prints what it loaded.
"""
A2 co-occurrence analyzer — what actually happens when TRENDING and RANGING
are both strong (>0.5) on the same tick.

Read-only, offline. Consumes the JSONL that replay_confluence.py already
writes (--jsonl); touches no box, no DB, no live state.

Answers three questions:

  1. WHO WINS.  On A2 co-occurrence ticks, which label did the Layer-2
     integrator actually commit? (TRENDING via its fast tau_up=40s, RANGING
     via tau_up=780s, or something else.) This is the tie-break audit.

  2. CONDITIONED DRIFT.  Does an LTF range inside an HTF bull trend actually
     drift UP? For each co-occurrence tick, forward price change is measured
     at several horizons and bucketed by which HTF direction was hot.

  3. THE CONTROL.  Same drift measured on RANGING-only ticks (range with NO
     HTF trend). Without this the drift number means nothing — the question
     is not "does a range drift" but "does a range drift MORE when an HTF
     trend is running under it".

Usage:
    python -m tests.a2_cooccurrence                      # auto-discovers all sessions
    python -m tests.a2_cooccurrence --horizons 10,20,30
    python -m tests.a2_cooccurrence <explicit.jsonl> ... # override discovery

Notes:
  - Records are 1-min bars in time order, so a horizon of N ~= N minutes.
  - Multi-day files are handled: a per-symbol segment break is inserted
    whenever ts goes backwards (HH:MM wrap).
  - Drift is signed % of price, and is reported RELATIVE TO TREND DIRECTION
    for the trending buckets (bear drift is sign-flipped) so a positive
    number always means "moved the way the HTF trend pointed".
"""

from __future__ import annotations

import argparse
import glob
import json
import statistics
import sys
from collections import defaultdict
from typing import Dict, List, Optional

# Search order for the replay tick logs. validate_regime.sh v2.1 consolidated
# all products under reports/; earlier layouts are kept as fallbacks so this
# keeps working across layout changes instead of silently finding nothing.
SEARCH_PATHS = [
    "~/day_trader_pro/reports/regime_replay_*.jsonl",
    "~/day_trader_pro/data/harvest/*/regime_replay_*.jsonl",   # legacy
    "~/day_trader_pro/reports/*/regime_replay_*.jsonl",
]

TRENDING_BULL = "TRENDING_BULL"
TRENDING_BEAR = "TRENDING_BEAR"
RANGING = "RANGING"
STRONG = 0.5


# ── loading ──────────────────────────────────────────────────────────────────
def discover() -> List[str]:
    """Find replay jsonl files without hardcoding one layout."""
    import os
    for pat in SEARCH_PATHS:
        hits = sorted(glob.glob(os.path.expanduser(pat)))
        if hits:
            return hits
    return []


# ── v1.1 — the fields this tool actually reads. Everything else in a replay
# record (the full per-factor breakdown, every engine state object) is dropped
# AT PARSE TIME rather than carried for the life of the run.
#
# WHY: option 47 was SIGKILLed by the OOM killer on 2026-08-04 — `Killed`, rc
# 137, no traceback, no output. Not a code fault: the corpus reached 17 sessions
# and this held every field of every tick, then `segments()` copied them all
# again into per-symbol lists. Identical to ramp_calibration v1.2's failure,
# which died producing NO OUTPUT on a 13-session run for the same reason and was
# fixed the same way.
# THE SLIM IS EXHAUSTIVE, NOT A GUESS: `sym`, `ts`, `price`, `scores`, `l2` are
# the only keys read anywhere in this file (verified by enumerating every
# .get() call), and `l2` is reduced to the two members used. A field added to a
# future analysis must be added HERE too — hence the assertion in
# tests/test_a2_cooccurrence_slim.py, which fails if a .get() appears for a key
# the slim does not keep.
_KEEP = ("sym", "ts", "price", "scores")


def _slim(rec: dict) -> dict:
    out = {k: rec.get(k) for k in _KEEP if k in rec}
    l2 = rec.get("l2")
    if isinstance(l2, dict):
        out["l2"] = {"regime": l2.get("regime"), "c": l2.get("c")}
    return out


def load(paths: List[str]) -> List[dict]:
    import os
    recs, loaded = [], []
    for pat in paths:
        for path in sorted(glob.glob(os.path.expanduser(pat))) or [pat]:
            try:
                with open(path) as fh:
                    n0 = len(recs)
                    for line in fh:
                        line = line.strip()
                        if line:
                            recs.append(_slim(json.loads(line)))
                    loaded.append((os.path.basename(path), len(recs) - n0))
            except FileNotFoundError:
                print(f"  ! not found: {path}", file=sys.stderr)
    if loaded:
        print(f"loaded {len(loaded)} file(s):")
        for name, n in loaded:
            print(f"   {name:<34} {n:>7d} ticks")
        print()
    return recs


def sc(rec: dict, key: str) -> float:
    v = (rec.get("scores") or {}).get(key)
    return float(v) if v is not None else 0.0


def segments(recs: List[dict]) -> Dict[str, List[List[dict]]]:
    """Group by symbol, split into time-ordered segments on a ts wrap."""
    by_sym: Dict[str, List[dict]] = defaultdict(list)
    for r in recs:
        by_sym[r.get("sym", "?")].append(r)
    out: Dict[str, List[List[dict]]] = {}
    for sym, rows in by_sym.items():
        segs, cur, last = [], [], None
        for r in rows:
            ts = r.get("ts", "")
            if last is not None and ts < last and cur:
                segs.append(cur)
                cur = []
            cur.append(r)
            last = ts
        if cur:
            segs.append(cur)
        out[sym] = segs
    return out


# ── classification of a tick ─────────────────────────────────────────────────
def bucket_of(rec: dict) -> Optional[str]:
    """Return the analysis bucket for a tick, or None if it is not of interest."""
    bull, bear = sc(rec, TRENDING_BULL), sc(rec, TRENDING_BEAR)
    rng = sc(rec, RANGING)
    trend_hot = max(bull, bear) > STRONG
    range_hot = rng > STRONG
    if trend_hot and range_hot:
        return "COOC_BULL" if bull >= bear else "COOC_BEAR"
    if range_hot and not trend_hot:
        return "RANGE_ONLY"          # the control
    if trend_hot and not range_hot:
        return "TREND_ONLY_BULL" if bull >= bear else "TREND_ONLY_BEAR"
    return None


def forward_drift(seg: List[dict], i: int, horizon: int) -> Optional[float]:
    """Signed % price change from tick i to tick i+horizon within a segment."""
    j = i + horizon
    if j >= len(seg):
        return None
    p0 = seg[i].get("price")
    p1 = seg[j].get("price")
    if not p0 or not p1:
        return None
    try:
        return (float(p1) - float(p0)) / float(p0)
    except (TypeError, ZeroDivisionError):
        return None


# ── report helpers ───────────────────────────────────────────────────────────
def pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:5.1f}%" if d else "    -"


def summarize(vals: List[float]) -> str:
    if not vals:
        return "      n/a"
    med = statistics.median(vals) * 100
    mean = statistics.mean(vals) * 100
    return f"med {med:+.3f}%  mean {mean:+.3f}%"


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="A2 co-occurrence + HTF-conditioned drift")
    ap.add_argument("jsonl", nargs="*",
                    help="replay jsonl file(s); globs ok. Omit to auto-discover.")
    ap.add_argument("--horizons", default="10,20,30",
                    help="forward horizons in bars/minutes (default 10,20,30)")
    ap.add_argument("--min-move", type=float, default=0.0,
                    help="ignore drifts smaller than this abs %% (e.g. 0.0005)")
    args = ap.parse_args(argv[1:])
    horizons = [int(h) for h in args.horizons.split(",") if h.strip()]

    paths = args.jsonl or discover()
    if not paths:
        print("No replay jsonl found. Looked in:")
        for p in SEARCH_PATHS:
            print(f"   {p}")
        print("\nPass an explicit path if your layout differs.")
        return 2

    recs = load(paths)
    if not recs:
        print("no records loaded")
        return 2

    segs = segments(recs)
    n_total = len(recs)

    # ── 1. who wins the tie ──────────────────────────────────────────────────
    cooc = [r for r in recs if (bucket_of(r) or "").startswith("COOC")]
    committed: Dict[str, int] = defaultdict(int)
    conv_by_label: Dict[str, List[float]] = defaultdict(list)
    no_l2 = 0
    for r in cooc:
        l2 = r.get("l2")
        if not isinstance(l2, dict) or not l2.get("regime"):
            no_l2 += 1
            continue
        lbl = l2["regime"]
        committed[lbl] += 1
        c = l2.get("c")
        if isinstance(c, (int, float)):
            conv_by_label[lbl].append(float(c))

    print("=" * 74)
    print(f"A2 CO-OCCURRENCE — {len(cooc)} of {n_total} ticks "
          f"({pct(len(cooc), n_total).strip()}) have TREND>0.5 AND RANGE>0.5")
    print("=" * 74)

    print("\n-- 1. which label did Layer-2 actually commit on those ticks --")
    if not committed and no_l2:
        print(f"   no l2 object on {no_l2} ticks (replay run without the integrator?)")
    for lbl, n in sorted(committed.items(), key=lambda kv: -kv[1]):
        cv = conv_by_label[lbl]
        cstr = f"  conviction med {statistics.median(cv):.2f}" if cv else ""
        print(f"   {lbl:<16} {n:6d}  {pct(n, len(cooc))}{cstr}")
    if no_l2:
        print(f"   (no l2 on {no_l2} ticks)")

    # ── 2/3. conditioned drift vs control ────────────────────────────────────
    drift: Dict[int, Dict[str, List[float]]] = {h: defaultdict(list) for h in horizons}
    counts: Dict[str, int] = defaultdict(int)
    for sym, seglist in segs.items():
        for seg in seglist:
            for i, r in enumerate(seg):
                b = bucket_of(r)
                if b is None:
                    continue
                counts[b] += 1
                for h in horizons:
                    d = forward_drift(seg, i, h)
                    if d is None or abs(d) < args.min_move:
                        continue
                    # express trending buckets relative to trend direction
                    if b.endswith("BEAR"):
                        d = -d
                    drift[h][b].append(d)

    print("\n-- 2/3. forward drift, signed toward the HTF trend direction --")
    print("   (RANGE_ONLY is the control: a range with NO HTF trend under it)")
    order = ["COOC_BULL", "COOC_BEAR", "RANGE_ONLY", "TREND_ONLY_BULL", "TREND_ONLY_BEAR"]
    for h in horizons:
        print(f"\n   horizon +{h} bars (~{h} min)")
        print(f"   {'bucket':<18}{'n':>7}   {'drift (toward trend)':<28}")
        for b in order:
            vals = drift[h].get(b, [])
            print(f"   {b:<18}{len(vals):>7}   {summarize(vals):<28}")

    # ── the headline comparison ──────────────────────────────────────────────
    print("\n-- headline: does an HTF trend bias the LTF range? --")
    for h in horizons:
        cb = drift[h].get("COOC_BULL", [])
        ro = drift[h].get("RANGE_ONLY", [])
        if cb and ro:
            lift = (statistics.median(cb) - statistics.median(ro)) * 100
            print(f"   +{h:>2} bars: range-in-bull-trend median drift is "
                  f"{lift:+.3f}% vs a plain range")
        else:
            print(f"   +{h:>2} bars: insufficient sample")
    print("\n   A materially positive lift supports treating HTF direction as a")
    print("   drift/bias term on the LTF range rather than a competing label.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
