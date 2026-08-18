#!/usr/bin/env python3
"""
tests/emission_law_sweep.py — v1.0 — 2026-08-06

RGM.1: IS THE CHURN COMING FROM THE UNPROTECTED BRANCH OF THE EMISSION LAW,
and would restoring the protection actually reach the operator's 2-4 switches
per session? Attribution first, counterfactual second. Read-only, offline.

WHY THIS TOOL CAN EXIST AT ALL. The replay corpus records `l2.cv` — the FULL
per-regime conviction vector, post-update, on every tick — plus `l2.regime` and
`l2.trigger`. Emission is a pure function of that vector and the incumbent, so
candidate emission laws can be re-run over the RECORDED convictions with no
engine run, no tape, and no re-integration. Nothing here re-derives conviction;
it only re-decides the label from convictions that were actually observed.

WHAT IS BEING TESTED (conviction_integrator v2.0 `_emit`, read at HEAD):
  incumbent conviction >= theta_hold (0.45)   -> PROTECTED: a challenger
      displaces only if it clears theta_commit (0.65) AND beats the incumbent
      by delta_displace (0.12).
  incumbent conviction <  theta_hold          -> UNPROTECTED: `incumbent =
      top_r`, unconditionally, every tick. No commit bar, no margin, no dwell.
The module header states the contract "a single-tick flicker can never move the
emitted label off a held regime". Below theta_hold that is not what the code
does. This tool measures how much of the churn lives in that branch.

THE THREE NUMBERS THAT MATTER
  1. TIME BELOW HOLD — the share of ticks where the incumbent sits under
     theta_hold. If that is the normal operating mode rather than an edge case,
     the unprotected branch IS the emission law in practice.
  2. SWITCH ATTRIBUTION — every observed label change assigned to its branch,
     read off the recorded trigger string ("displaced ..." vs "fell below
     hold ..."), so the split is the engine's own account of itself, not mine.
  3. COUNTERFATUAL SWITCHES/SYMBOL-DAY under each candidate law, against the
     operator's stated prior of 2-4 real regime changes in a session.

HARNESS VALIDATION IS THE FIRST OUTPUT, NOT A FOOTNOTE. Variant `baseline`
re-implements the CURRENT law and must reproduce the recorded label sequence.
Agreement well under 100% means the re-emission model is not faithful and every
counterfactual below it is void — read that line before reading anything else.
(This is the same discipline that validated regime_switch_cost: delta=0 had to
reproduce the engine's own ~20 switches before the sweep meant anything.)

WHAT THIS DOES NOT SHOW. It does not show that a steadier label is a MORE
ACCURATE label. A law that emits one regime all day would score 0 switches and
be worthless. Stability is necessary, not sufficient; agreement against
session_labels.jsonl is the separate question and this tool does not touch it.
Nor does it address Layer 1: if the score vector is mostly exact zeros, the
convictions feeding this are degenerate no matter which law reads them.

Read-only, stdlib only, streams one file at a time, always exits 0.
USAGE
    python3 tests/emission_law_sweep.py
    python3 tests/emission_law_sweep.py --since 2026-08-01 --dwell 2,4,8,12

CHANGELOG
  v1.0 — 2026-08-06 — first issue. Written after the fallback run-length probe
         (rng_probe v1.0) refuted the bar-availability hypothesis and reading
         `_emit` at HEAD surfaced the unprotected branch. Measures before it
         proposes: the fix is not defensible until the attribution says the
         churn is actually there.
"""

import argparse
import collections
import glob
import json
import os
import re
import sys

REPLAY_GLOB = "~/day_trader_pro/reports/regime_replay_*.jsonl"
DATE_RE = re.compile(r"regime_replay_(20\d\d-\d\d-\d\d)\.jsonl$")

THETA_COMMIT = 0.65
THETA_HOLD = 0.45
DELTA_DISPLACE = 0.12

# conviction_integrator._TIEBREAK_ORDER, verbatim — ties must break the same
# way or the baseline variant will disagree with the engine for a reason that
# has nothing to do with the emission law.
TIEBREAK = {r: i for i, r in enumerate((
    "SWEEP_REVERSAL", "BREAKOUT_VOLATILE", "COMPRESSION",
    "TRENDING_BULL", "TRENDING_BEAR", "RANGING",
))}


def _top(cv):
    """argmax over the conviction vector with the engine's tie order."""
    return min(cv.items(), key=lambda kv: (-kv[1], TIEBREAK.get(kv[0], 99)))


class Law:
    """A candidate emission law. `step` returns the incumbent after this tick."""

    def __init__(self, name, protect_below=False, dwell=0):
        self.name = name
        self.protect_below = protect_below   # apply commit+margin in BOTH branches
        self.dwell = dwell                   # ticks a challenger must lead first
        self.reset()

    def reset(self):
        self.inc = None
        self.cand = None
        self.cand_run = 0
        self.switches = 0
        self.run = 0
        self.runs = []

    def _qualified(self, top_r, top_c, inc_c):
        return (top_c >= THETA_COMMIT and top_c >= inc_c + DELTA_DISPLACE)

    def step(self, cv):
        top_r, top_c = _top(cv)
        prev = self.inc

        if self.inc is None:
            self.inc = top_r
        else:
            inc_c = cv.get(self.inc, 0.0)
            protected = (inc_c >= THETA_HOLD) or self.protect_below
            if protected:
                ok = (top_r != self.inc and self._qualified(top_r, top_c, inc_c))
            else:
                ok = (top_r != self.inc)          # current law: bare argmax
            if ok and self.dwell:
                # time, not margin: a challenger must LEAD for `dwell` ticks.
                # A boolean veto that flips back inside the window never
                # commits, which a score margin cannot achieve.
                if self.cand == top_r:
                    self.cand_run += 1
                else:
                    self.cand, self.cand_run = top_r, 1
                ok = self.cand_run >= self.dwell
            elif not ok:
                self.cand, self.cand_run = None, 0
            if ok:
                self.inc = top_r
                self.cand, self.cand_run = None, 0

        if prev is not None and self.inc != prev:
            self.switches += 1
            self.runs.append(self.run)
            self.run = 1
        else:
            self.run += 1
        return self.inc

    def end_symday(self):
        if self.run:
            self.runs.append(self.run)
        self.inc = None
        self.cand, self.cand_run, self.run = None, 0, 0


def _pct(sv, p):
    if not sv:
        return 0
    return sv[min(len(sv) - 1, int(round(p / 100.0 * (len(sv) - 1))))]


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default=REPLAY_GLOB)
    ap.add_argument("--since", default="")
    ap.add_argument("--dwell", default="2,4,8,12",
                    help="dwell values (ticks) to sweep on the protected law")
    a = ap.parse_args(argv[1:])

    paths = [p for p in sorted(glob.glob(os.path.expanduser(a.glob)))
             if DATE_RE.search(p)
             and (not a.since or DATE_RE.search(p).group(1) >= a.since)]
    if not paths:
        print(f"no replay files matched {a.glob}")
        return 0

    dwells = [int(x) for x in a.dwell.split(",") if x.strip().isdigit()]
    laws = [Law("baseline (current law)"),
            Law("protect below hold", protect_below=True)]
    laws += [Law(f"protect + dwell {d}", protect_below=True, dwell=d)
             for d in dwells]

    observed_switches = 0
    attributed = collections.Counter()
    below_hold = at_or_above = 0
    inc_conv_at_switch = []
    baseline_agree = baseline_ticks = 0
    symdays = 0
    ticks = 0
    obs_runs = []

    for path in paths:
        date = DATE_RE.search(path).group(1)
        # stream, but the corpus interleaves symbols, so state is per symbol
        state = {}
        for line in open(path, errors="ignore"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:                                   # noqa: BLE001
                continue
            l2 = r.get("l2")
            if not l2:
                continue
            cv = l2.get("cv") or {}
            if not cv:
                continue
            sym = r.get("sym", "?")
            s = state.setdefault(sym, {"inc": None, "run": 0,
                                       "laws": [Law(l.name, l.protect_below,
                                                    l.dwell) for l in laws]})
            obs = l2.get("regime") or ""
            trig = l2.get("trigger") or ""
            inc_c = cv.get(s["inc"], 0.0) if s["inc"] else None

            # 1. time below hold, measured on the INCUMBENT before this tick
            if s["inc"] is not None:
                if inc_c >= THETA_HOLD:
                    at_or_above += 1
                else:
                    below_hold += 1

            # 2. observed switch attribution, from the engine's own trigger text
            if s["inc"] is not None and obs and obs != s["inc"]:
                observed_switches += 1
                obs_runs.append(s["run"])
                s["run"] = 0
                if "fell below hold" in trig:
                    attributed["UNPROTECTED (fell below hold -> argmax)"] += 1
                elif "displaced" in trig:
                    attributed["PROTECTED (committed challenger displaced)"] += 1
                elif trig:
                    attributed[f"other trigger: {trig.split()[0]}"] += 1
                else:
                    attributed["(no trigger text recorded)"] += 1
                inc_conv_at_switch.append(round(inc_c or 0.0, 2))
            s["run"] += 1
            if obs:
                s["inc"] = obs

            # 3. counterfactual laws over the same recorded vectors
            for law in s["laws"]:
                emitted = law.step(cv)
                if law.name.startswith("baseline"):
                    baseline_ticks += 1
                    if obs and emitted == obs:
                        baseline_agree += 1
            ticks += 1

        for sym, s in state.items():
            symdays += 1
            if s["run"]:
                obs_runs.append(s["run"])
            for law, agg in zip(laws, s["laws"]):
                agg.end_symday()
                law.switches += agg.switches
                law.runs.extend(agg.runs)

    sd = max(1, symdays)
    print(f"files: {len(paths)}  ({DATE_RE.search(paths[0]).group(1)} .. "
          f"{DATE_RE.search(paths[-1]).group(1)})")
    print(f"symbol-days: {symdays}   ticks with an l2 vector: {ticks}")
    print()
    print("=== 0. HARNESS VALIDATION (read this first) ===")
    agree = 100.0 * baseline_agree / max(1, baseline_ticks)
    print(f"  baseline law reproduces the recorded label on "
          f"{baseline_agree}/{baseline_ticks} ticks = {agree:.1f}%")
    print(f"  observed switches {observed_switches} "
          f"({observed_switches/sd:.1f}/symbol-day)  vs baseline "
          f"{laws[0].switches} ({laws[0].switches/sd:.1f}/symbol-day)")
    if agree < 97.0:
        print("  ** BELOW 97% — the re-emission model is NOT faithful. Every")
        print("  ** counterfactual below is VOID. Fix the model, not the engine.")
    print()
    print("=== 1. IS THE UNPROTECTED BRANCH THE NORMAL OPERATING MODE? ===")
    tot = max(1, below_hold + at_or_above)
    print(f"  incumbent BELOW theta_hold={THETA_HOLD}: {below_hold} ticks "
          f"({100.0*below_hold/tot:.1f}%)   at/above: {at_or_above} "
          f"({100.0*at_or_above/tot:.1f}%)")
    print()
    print("=== 2. OBSERVED SWITCHES, ATTRIBUTED BY THE ENGINE'S OWN TRIGGER ===")
    for cause, n in attributed.most_common():
        print(f"  {cause:<48}{n:7d}  ({100.0*n/max(1,observed_switches):.1f}%)")
    ics = sorted(inc_conv_at_switch)
    print(f"  incumbent conviction at the moment of switch: "
          f"p50={_pct(ics,50)}  p90={_pct(ics,90)}")
    orl = sorted(obs_runs)
    print(f"  observed label RUN LENGTH (ticks): p50={_pct(orl,50)}  "
          f"p90={_pct(orl,90)}")
    print()
    print("=== 3. COUNTERFACTUAL — SWITCHES PER SYMBOL-DAY BY LAW ===")
    print("    (operator's prior: 2-4 real regime changes in a session)")
    print(f"  {'law':<28}{'switches':>10}{'per sym-day':>14}{'median run':>12}")
    for law in laws:
        rs = sorted(law.runs)
        print(f"  {law.name:<28}{law.switches:10d}{law.switches/sd:14.1f}"
              f"{_pct(rs,50):12d}")
    print()
    print("  A law that never switches would print 0.0 and be useless. These")
    print("  numbers say STABILITY only; whether the steadier label is the")
    print("  CORRECT label is the session_labels agreement question, untouched.")
    return 0


if __name__ == "__main__":
    try:
        rc = main(sys.argv)
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        rc = 0
    sys.exit(rc)
