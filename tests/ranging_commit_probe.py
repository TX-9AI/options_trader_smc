#!/usr/bin/env python3
"""
tests/ranging_commit_probe.py — v1.0 — 2026-08-10

WHY DOES L1 SEE A RANGE ON ~19% OF TICKS WHILE L2 EMITS RANGING ON ~2%?

THE TWO CANDIDATE CAUSES, and they need OPPOSITE fixes:

  THE CLOCK   — RANGING's `tau_up` is 780s against trending's 40s, so reaching
                `theta_commit` 0.65 from zero needs ~13.6 MINUTES of continuous
                maximal evidence. If L1 RANGING wins the argmax only in short
                bursts, conviction never has time to climb. Fix: a faster rise.
  THE CEILING — conviction ASYMPTOTES TO THE EVIDENCE LEVEL. RANGING's L1 score
                ran p50 0.029 / p90 0.504 on 2026-08-10, so on most ticks the
                evidence itself sits BELOW the 0.65 commit bar. Conviction then
                converges to a ceiling under the threshold and NO AMOUNT OF TIME
                crosses it. Fix: a per-regime commit threshold, or a scorer that
                produces higher evidence — a faster tau would change nothing.

⚠️ GUESSING BETWEEN THEM WOULD BE EXPENSIVE. Dropping tau_up to 180 restores
commits AND readmits the 12-15 bar false-flat trends the 780 was chosen to
exclude — and the integrator's own comment says that window is why the number
is what it is. This is the premium-selling gate; the impostor error is the
expensive one. So the fix must be chosen from the split, not from the symptom.

⚠️ AND THE CONSTANT WAS NOT WRONG WHEN IT WAS WRITTEN. 780 was picked under the
UNPROTECTED emission law, where RANGING could take the label on a bare argmax at
any conviction — slow commit cost nothing. F7's `protect_below_hold` made
`theta_commit` mandatory for every challenger. A number chosen against one law
became load-bearing under a different one, and nobody re-derived it.

NO SIMULATION IS NEEDED. The replay corpus records `l2.cv` — the FULL per-regime
conviction vector, post-update, on every tick — alongside the L1 `scores`. So
this reads what conviction RANGING ACTUALLY REACHED rather than modelling it.

POSITIVE CONTROL, and the run is not trustworthy without it: the same analysis
runs for TRENDING_BULL. Trending demonstrably commits (44% of emitted labels), so
if this tool cannot show trending clearing the bar, the tool is wrong and nothing
it says about RANGING stands.

READ-ONLY. stdlib only. Touches no fleet and no live path.

USAGE
    python3 tests/ranging_commit_probe.py                    # auto-discover corpus
    python3 tests/ranging_commit_probe.py <replay.jsonl> ...
    python3 tests/ranging_commit_probe.py --regime COMPRESSION
"""

import argparse
import glob
import json
import os
import sys
from collections import defaultdict

REPORTS = os.path.expanduser("~/day_trader_pro/reports")
THETA_COMMIT = 0.65          # conviction_integrator default
THETA_HOLD = 0.45
TICK_S = 15.0                # fleet cadence; replay steps bar-to-bar but runs are in ticks


def pct(v, q):
    if not v:
        return None
    s = sorted(v)
    return s[min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))]


def discover(args):
    if args:
        return args
    return sorted(glob.glob(os.path.join(REPORTS, "regime_replay_*.jsonl")))


def analyse(files, target):
    """Walk each symbol's tick series, collect runs where `target` is L1 argmax."""
    runs = []                      # one dict per run
    state = defaultdict(lambda: {"in_run": False, "n": 0,
                                 "max_ev": 0.0, "max_cv": 0.0, "committed": False})
    ticks = argmax_ticks = 0

    for path in files:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:                              # noqa: BLE001
                    continue
                sc = r.get("scores") or {}
                l2 = r.get("l2") or {}
                cv = l2.get("cv") or {}
                if not sc:
                    continue
                ticks += 1
                sym = r.get("sym", "?")
                st = state[sym]

                live = {k: v for k, v in sc.items() if isinstance(v, (int, float))}
                if not live:
                    continue
                top = max(live, key=lambda k: live[k])
                is_target = (top == target and live[top] > 0)
                if is_target:
                    argmax_ticks += 1

                if is_target:
                    st["in_run"] = True
                    st["n"] += 1
                    st["max_ev"] = max(st["max_ev"], float(live.get(target, 0.0)))
                    c = float(cv.get(target, 0.0) or 0.0)
                    st["max_cv"] = max(st["max_cv"], c)
                    if c >= THETA_COMMIT:
                        st["committed"] = True
                elif st["in_run"]:
                    runs.append({"sym": sym, "n": st["n"], "max_ev": st["max_ev"],
                                 "max_cv": st["max_cv"], "committed": st["committed"]})
                    state[sym] = {"in_run": False, "n": 0, "max_ev": 0.0,
                                  "max_cv": 0.0, "committed": False}
    # close any run still open at EOF
    for sym, st in state.items():
        if st["in_run"]:
            runs.append({"sym": sym, "n": st["n"], "max_ev": st["max_ev"],
                         "max_cv": st["max_cv"], "committed": st["committed"]})
    return runs, ticks, argmax_ticks


def report(name, runs, ticks, argmax_ticks, fh=sys.stdout):
    w = fh.write
    w(f"\n{'=' * 74}\n  {name}\n{'=' * 74}\n")
    if not runs:
        w("  no argmax runs found — nothing to say\n")
        return
    lens = [r["n"] for r in runs]
    evs = [r["max_ev"] for r in runs]
    cvs = [r["max_cv"] for r in runs]
    committed = [r for r in runs if r["committed"]]

    w(f"  ticks {ticks:,}   L1-argmax ticks {argmax_ticks:,} "
      f"({100.0 * argmax_ticks / max(ticks, 1):.1f}%)   runs {len(runs)}\n")
    w(f"  run length (ticks):  p50={pct(lens, .5)}  p90={pct(lens, .9)}  "
      f"max={max(lens)}   (~{TICK_S:.0f}s each)\n")
    w(f"  peak L1 EVIDENCE:    p50={pct(evs, .5):.3f}  p90={pct(evs, .9):.3f}  "
      f"max={max(evs):.3f}\n")
    w(f"  peak L2 CONVICTION:  p50={pct(cvs, .5):.3f}  p90={pct(cvs, .9):.3f}  "
      f"max={max(cvs):.3f}\n")
    w(f"  runs that COMMITTED (cv >= {THETA_COMMIT}): {len(committed)}/{len(runs)} "
      f"({100.0 * len(committed) / len(runs):.1f}%)\n")

    # ── THE SPLIT ────────────────────────────────────────────────────────────
    failed = [r for r in runs if not r["committed"]]
    ceiling = [r for r in failed if r["max_ev"] < THETA_COMMIT]
    clock = [r for r in failed if r["max_ev"] >= THETA_COMMIT]
    w(f"\n  WHY THE FAILED RUNS FAILED  (n={len(failed)})\n")
    if failed:
        w(f"    CEILING — peak evidence NEVER reached {THETA_COMMIT}, so conviction\n")
        w(f"              asymptotes below the bar and NO tau change helps:\n")
        w(f"              {len(ceiling)}/{len(failed)} = "
          f"{100.0 * len(ceiling) / len(failed):.1f}%\n")
        w(f"    CLOCK   — evidence DID reach {THETA_COMMIT} but conviction did not,\n")
        w(f"              i.e. the run ended before the rise completed:\n")
        w(f"              {len(clock)}/{len(failed)} = "
          f"{100.0 * len(clock) / len(failed):.1f}%\n")
        if clock:
            w(f"              those runs: length p50={pct([r['n'] for r in clock], .5)} "
              f"ticks, peak cv p90={pct([r['max_cv'] for r in clock], .9):.3f}\n")

    # ── WHAT WOULD ACTUALLY MOVE IT ──────────────────────────────────────────
    w(f"\n  COUNTERFACTUAL — runs that WOULD have committed at a lower bar\n")
    for theta in (0.60, 0.55, 0.50, 0.45, 0.40, 0.35, 0.30):
        n = sum(1 for r in runs if r["max_cv"] >= theta)
        w(f"    theta_commit {theta:.2f} -> {n:4d}/{len(runs)} runs "
          f"({100.0 * n / len(runs):5.1f}%)\n")
    w(f"    (this varies the BAR only — the conviction values are the ones the\n")
    w(f"     integrator actually produced, so it isolates the threshold from tau)\n")

    if failed:
        # A NEAR-TIE MUST NOT PRODUCE A CONFIDENT VERDICT. Caught in testing:
        # a planted world split 20/20 and the tool named CLOCK off a bare
        # `>` comparison. The two causes need OPPOSITE fixes, so a coin-flip
        # margin is the one case where saying nothing is the correct output.
        _tot = len(ceiling) + len(clock)
        _share = max(len(ceiling), len(clock)) / _tot if _tot else 0.0
        if _share < 0.60:
            w(f"\n  ⇒ NO DOMINANT CAUSE — the split is {len(ceiling)} ceiling / "
              f"{len(clock)} clock ({100.0 * _share:.0f}% majority).\n")
            w("    These need OPPOSITE fixes, so a near-even split is not a "
              "mandate for\n    either one. Both mechanisms are live and a single "
              "dial will not do it.\n")
            return
        dom = "CEILING" if len(ceiling) > len(clock) else "CLOCK"
        w(f"\n  ⇒ DOMINANT CAUSE: {dom}  ({100.0 * _share:.0f}% of failed runs)\n")
        if dom == "CEILING":
            w("    A faster tau_up would change NOTHING — conviction cannot exceed\n")
            w("    the evidence feeding it. This points at a per-regime commit\n")
            w("    threshold, or at the L1 scorer producing higher evidence, and\n")
            w("    NOT at the rise time. Note that lowering the bar admits weaker\n")
            w("    evidence by definition — the 12-15 bar false-flat window the 780\n")
            w("    was chosen to exclude is the thing to check before doing it.\n")
        else:
            w("    Evidence is sufficient; the runs simply end before the rise\n")
            w("    completes. THIS is the case where tau_up is the right dial —\n")
            w("    and where shortening it re-opens the impostor window, so the\n")
            w("    run-length distribution above must be read against the 12-15\n")
            w("    bar false-flat figure before choosing a value.\n")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--regime", default="RANGING")
    ap.add_argument("--control", default="TRENDING_BULL",
                    help="positive control; a tool that cannot show THIS "
                         "committing is not measuring what it claims")
    a = ap.parse_args(argv[1:])

    files = discover(a.files)
    if not files:
        print(f"no replay files found in {REPORTS}")
        return 1
    print(f"reading {len(files)} replay file(s)\n")

    runs, t, at = analyse(files, a.regime)
    report(f"{a.regime} — THE QUESTION", runs, t, at)

    cruns, ct, cat = analyse(files, a.control)
    report(f"{a.control} — POSITIVE CONTROL (must commit readily)", cruns, ct, cat)

    if cruns:
        cc = sum(1 for r in cruns if r["committed"]) / len(cruns)
        print(f"\n  CONTROL CHECK: {a.control} committed on {100.0 * cc:.1f}% of its runs.")
        if cc < 0.20:
            print("  ⚠️  THE CONTROL FAILED. Trending demonstrably commits live "
                  "(44% of\n      emitted labels), so if it does not clear the bar "
                  "here the TOOL is\n      wrong and nothing above stands. Do not "
                  "act on this run.")
        else:
            print("  Control passes — the instrument can see a commit when one happens.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
