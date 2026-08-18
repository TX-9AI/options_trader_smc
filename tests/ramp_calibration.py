# options_trader_v3/tests/ramp_calibration.py — v1.2
# v1.2 — 2026-07-30 — TWO SILENT FAILURES, both found on the tool's first real
#        use. (a) Run as a direct script, `from analysis import regime_confluence`
#        failed (tests/ is on sys.path, not the repo root) and _RC fell to None
#        WITHOUT a word — so every CURRENT bound printed a hardcoded fallback
#        instead of the live constant. room_s reported lo=0.05/hi=0.20 when the
#        dials in force were 0.17/1.00. Repo root is now on sys.path and a failed
#        import prints a banner saying the bounds column cannot be trusted.
#        (b) load() held every record of every session in memory (~300MB for a
#        fortnight); the 13-session auto-discover run died producing NO OUTPUT.
#        Now streams per line and keeps only the sampled floats.
# v1.1 — 2026-07-22 — CURRENT bounds now read the LIVE module constants (which
#        honour OT_RC_* overrides) instead of hardcoded defaults, so a run with
#        dials set no longer misreports its own bounds or raises a false
#        'hi bound too low'. Terms whose bounds are NOT simple module constants
#        (adx_s lo is derived from the constructor; align_val is a max() of two
#        sources) are now marked DERIVED and give no suggestion.
"""
Ramp calibration — find WHICH scoring term is saturating and where its ramp
bounds should actually sit, fitted to observed tape instead of priors.

Read-only, offline. Consumes the replay JSONL that validate_regime.sh writes.

For each ramped term it reports:
  * SATURATION  — %% of scored ticks where the term is pegged at 1.0 (and at 0.0).
                  A term pegged most of the time is a switch, not a dial.
  * INPUT SPREAD— percentiles of the raw input feeding that ramp.
  * CURRENT     — the ramp bounds in force today, and what percentile of real
                  tape each bound lands on. A hi-bound sitting at p40 means
                  60%% of ticks max the term out.
  * SUGGESTED   — bounds placed at target percentiles so the ramp spans the
                  range the tape actually occupies.

Nothing is changed. The output is the evidence for a config change.

Usage:
    python -m tests.ramp_calibration                 # auto-discovers sessions
    python -m tests.ramp_calibration --lo-pct 25 --hi-pct 95
    python -m tests.ramp_calibration <explicit.jsonl> ...
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import statistics
import sys
from typing import Dict, List, Optional, Tuple

SEARCH_PATHS = [
    "~/day_trader_pro/reports/regime_replay_*.jsonl",
    "~/day_trader_pro/data/harvest/*/regime_replay_*.jsonl",   # legacy
    "~/day_trader_pro/reports/*/regime_replay_*.jsonl",
]

# (label, regime-breakdown key, input field, scored field, current lo, current hi,
#  higher_input_means_higher_score)
# Live bounds come from the module, so OT_RC_* overrides are reflected.
# v1.2 — running this as a DIRECT SCRIPT puts tests/ on sys.path, not the repo
# root, so `from analysis import ...` failed and _RC fell silently to None —
# every CURRENT bound then printed a hardcoded fallback instead of the value
# actually in force. On 2026-07-30 that made room_s report lo=0.05/hi=0.20 when
# the live constants were 0.17/1.00, i.e. the tool misreported the very dials it
# exists to calibrate. Put the repo root on the path, and if the import still
# fails SAY SO instead of quietly substituting defaults.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from analysis import regime_confluence as _RC
    _RC_ERR = None
except Exception as _e:                              # standalone use
    _RC, _RC_ERR = None, f"{type(_e).__name__}: {_e}"


def _live(name: str, fallback: float):
    return getattr(_RC, name, fallback) if _RC else fallback


def _bounds_banner():
    """A calibration report whose CURRENT column is wrong is worse than none."""
    if _RC:
        return ("bounds source: LIVE module constants "
                "(analysis.regime_confluence, honours OT_RC_*)")
    return ("\u26a0 BOUNDS SOURCE: HARDCODED FALLBACKS — could not import "
            f"analysis.regime_confluence ({_RC_ERR}).\n"
            "   Every CURRENT and SUGGESTED line below is measured against "
            "DEFAULTS, not the dials actually in force.\n"
            "   SATURATION and INPUT are still valid (they come from the tape). "
            "Fix the import before changing any bound.")


# (label, regime, input field, scored field, lo, hi, ascending, tunable)
# lo/hi = None means the bound is DERIVED, not a simple module constant.
def _terms():
    cut, soft = _live("FLAT_ANGLE_CUT_DEG", 20.0), _live("FLAT_ANGLE_SOFT_DEG", 8.0)
    return [
        ("TRENDING adx_s      (soft-necessary)", "TRENDING", "adx", "adx_s",
         None, _live("ADX_STRONG_SOLO", 35.0), True, "hi only (lo = adx_trend-5, constructor)"),
        ("TRENDING align_val  (corroborator)", "TRENDING", "align_frac", "align_val",
         None, None, True, "DERIVED: max(align_frac, ramp(adx,...)) - two sources"),
        ("RANGING  flat_s     (soft-necessary)", "RANGING", "angle", "flat_s",
         cut - soft, cut, False, "conditional sample: only ticks past the flat veto"),
        ("RANGING  room_s     (soft-necessary)", "RANGING", "bb_width_pct", "room_s",
         _live("RANGE_ROOM_LO", 0.05), _live("RANGE_ROOM_HI", 0.20), True, ""),
        ("RANGING  osc_s      (corroborator)", "RANGING", "crossings", "osc_s",
         _live("OSC_CROSS_LO", 2.0), _live("OSC_CROSS_HI", 5.0), True, ""),
    ]


def discover() -> List[str]:
    for pat in SEARCH_PATHS:
        hits = sorted(glob.glob(os.path.expanduser(pat)))
        if hits:
            return hits
    return []


def stream_collect(paths: List[str], wanted) -> Tuple[Dict[str, Tuple[List[float], List[float]]], int]:
    """v1.2 — STREAM. Read one line, take the few floats each term needs, drop it.

    v1.1 loaded every record of every session into one list before computing
    anything. At ~23MB per replay log that is ~300MB for a fortnight's corpus,
    and on 2026-07-30 the auto-discover run over 13 sessions produced NO OUTPUT
    AT ALL — the process died before the first print. Silent, because the load
    happens before anything is emitted. A calibration tool that fails as the
    corpus grows is one that breaks exactly when it becomes worth running.

    Memory now scales with the number of SAMPLED VALUES, not the tape.
    """
    acc: Dict[str, Tuple[List[float], List[float]]] = {
        f"{rg}|{ik}|{ok}": ([], []) for rg, ik, ok in wanted}
    loaded, total = [], 0
    for pat in paths:
        for path in sorted(glob.glob(os.path.expanduser(pat))) or [pat]:
            n0 = total
            try:
                with open(path) as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            r = json.loads(line)
                        except Exception:            # noqa: BLE001 — truncated tail
                            continue
                        total += 1
                        bds = r.get("breakdown") or {}
                        for rg, ik, ok in wanted:
                            bd = bds.get(rg) or {}
                            iv, ov = bd.get(ik), bd.get(ok)
                            ins, outs = acc[f"{rg}|{ik}|{ok}"]
                            if isinstance(iv, (int, float)):
                                ins.append(float(iv))
                            if isinstance(ov, (int, float)):
                                outs.append(float(ov))
                loaded.append((os.path.basename(path), total - n0))
            except FileNotFoundError:
                print(f"  ! not found: {path}", file=sys.stderr)
    if loaded:
        print(f"loaded {len(loaded)} file(s), streamed:")
        for name, n in loaded:
            print(f"   {name:<34} {n:>7d} ticks")
        print()
    return acc, total


def pctile(vals: List[float], p: float) -> Optional[float]:
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * (p / 100.0)
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def pct_rank(vals: List[float], x: float) -> Optional[float]:
    """What percentile of vals does value x sit at?"""
    if not vals:
        return None
    s = sorted(vals)
    below = sum(1 for v in s if v < x)
    return 100.0 * below / len(s)


def collect(recs: List[dict], regime: str, in_key: str,
            out_key: str) -> Tuple[List[float], List[float]]:
    ins, outs = [], []
    for r in recs:
        bd = (r.get("breakdown") or {}).get(regime) or {}
        iv, ov = bd.get(in_key), bd.get(out_key)
        if isinstance(iv, (int, float)):
            ins.append(float(iv))
        if isinstance(ov, (int, float)):
            outs.append(float(ov))
    return ins, outs


def fmt(v: Optional[float], w: int = 7, d: int = 2) -> str:
    return f"{v:>{w}.{d}f}" if v is not None else " " * (w - 3) + "n/a"


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="ramp saturation + bound calibration")
    ap.add_argument("jsonl", nargs="*", help="replay jsonl; omit to auto-discover")
    ap.add_argument("--lo-pct", type=float, default=25.0,
                    help="target percentile for the ramp LOW bound (default 25)")
    ap.add_argument("--hi-pct", type=float, default=95.0,
                    help="target percentile for the ramp HIGH bound (default 95)")
    args = ap.parse_args(argv[1:])

    paths = args.jsonl or discover()
    if not paths:
        print("No replay jsonl found. Looked in:")
        for p in SEARCH_PATHS:
            print(f"   {p}")
        return 2
    wanted = [(rg, ik, ok) for _, rg, ik, ok, _, _, _, _ in _terms()]
    acc, n_ticks = stream_collect(paths, wanted)
    if not n_ticks:
        print("no records loaded")
        return 2

    print("=" * 78)
    print(f"RAMP CALIBRATION — {n_ticks} ticks")
    print("A term pegged at 1.0 on most scored ticks is a SWITCH, not a dial.")
    print(_bounds_banner())
    print("=" * 78)

    for label, regime, in_key, out_key, cur_lo, cur_hi, ascending, caveat in _terms():
        ins, outs = acc[f"{regime}|{in_key}|{out_key}"]
        if not outs:
            print(f"\n{label}\n   (no data)")
            continue

        n = len(outs)
        peg1 = sum(1 for v in outs if v >= 0.999)
        peg0 = sum(1 for v in outs if v <= 0.001)
        mid = n - peg1 - peg0

        print(f"\n{label}")
        print(f"   SATURATION   pegged 1.0: {100.0*peg1/n:5.1f}%   "
              f"pegged 0.0: {100.0*peg0/n:5.1f}%   "
              f"graded in between: {100.0*mid/n:5.1f}%")

        if caveat:
            print(f"   NOTE         {caveat}")
        if ins and cur_lo is not None and cur_hi is not None:
            ps = {p: pctile(ins, p) for p in (5, 25, 50, 75, 90, 95, 99)}
            print(f"   INPUT {in_key:<13} p5{fmt(ps[5])}  p25{fmt(ps[25])}  "
                  f"p50{fmt(ps[50])}  p75{fmt(ps[75])}  p90{fmt(ps[90])}  "
                  f"p95{fmt(ps[95])}  p99{fmt(ps[99])}")
            r_lo, r_hi = pct_rank(ins, cur_lo), pct_rank(ins, cur_hi)
            print(f"   CURRENT      lo={cur_lo:<7g} (input p{r_lo:.0f})   "
                  f"hi={cur_hi:<7g} (input p{r_hi:.0f})")
            if ascending:
                s_lo, s_hi = pctile(ins, args.lo_pct), pctile(ins, args.hi_pct)
            else:
                # descending input (e.g. angle): low score at high angle
                s_lo, s_hi = pctile(ins, 100 - args.hi_pct), pctile(ins, 100 - args.lo_pct)
            print(f"   SUGGESTED    lo={s_lo:<7.2f}(p{args.lo_pct:.0f})   "
                  f"hi={s_hi:<7.2f}(p{args.hi_pct:.0f})", end="")
            if r_hi is not None and r_hi < 60 and peg1 / n > 0.40:
                print("   <-- hi bound too low AND term is pegging; widen it")
            else:
                print()
        elif ins:
            ps2 = {p: pctile(ins, p) for p in (25, 50, 95)}
            print(f"   INPUT {in_key:<13} p25{fmt(ps2[25])}  p50{fmt(ps2[50])}  "
                  f"p95{fmt(ps2[95])}   (no bound suggestion - see NOTE)")

    print("\n" + "=" * 78)
    print("Reading this: a term with <25% 'graded in between' is behaving as a")
    print("switch. Moving its hi bound out to a genuinely rare percentile restores")
    print("grading. Do NOT push a bound past ~p99 of real tape or the term becomes")
    print("unreachable — the failure v3.1 just fixed, in reverse.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
