#!/usr/bin/env python3
"""
tests/veto_attribution.py — v1.1 — 2026-08-06

WHICH VETO IS CAUSING THE CHURN? For every tick where a regime's score crosses
between ZERO and NON-ZERO, reports which hard veto changed state.

v1.1 — a veto key that APPEARS or DISAPPEARS between ticks is a BRANCH CHANGE,
not a veto flip. v1.0 counted it as one, and credited RANGING with 4,929
`veto_flat` transitions when RANGING's veto_flat is a hardcoded 1.0 that never
changes — the live one belongs to COMPRESSION. Branch changes now get their own
row, and they matter: they mean the regime switched between its full window path
and its reduced vol-only fallback, which is a BAR-AVAILABILITY event rather than
a market one.

WHY THIS IS THE RIGHT QUESTION. The scoring grammar is multiplicative and
documented in regime_confluence's own header:

    score_R = (∏ hard_veto ∈{0,1}) · (∏ soft_necessary ∈[0,1]) · (Σ w·corroborator)

A single hard veto at 0 zeroes the whole regime, however strong every
corroborator is. That is why 64-96% of all scores are EXACTLY 0.00 across 19
sessions — not missing data and not weak signal: a veto fired.

WHICH MEANS A REGIME TRANSITION IS A BOOLEAN FLIPPING, NOT A SCORE CROSSING.
That explains why the switching-cost sweep (regime_switch_cost v1.1) decayed
gradually instead of cliffing: a delta asks the challenger to beat the incumbent
by a margin, but the incumbent did not lose by a margin — it was vetoed to zero,
and any challenger above delta clears it. **Hysteresis cannot fight a boolean.**

It also explains why re-weighting corroborators would change little: the weights
live in the LAST term, which is multiplied by zero on the majority of ticks.

WHAT A RESULT LOOKS LIKE. If one or two vetoes account for most transitions,
that is a specific and fixable target — and the candidate fix is to make that
veto a SOFT DAMPER (a value in [0,1] that reduces the score) rather than a HARD
GATE (a boolean that annihilates it). A damper degrades; a gate teleports.

WHAT THIS DOES NOT SHOW. It does not say the veto is WRONG. A veto that fires
often may be correctly describing a condition that genuinely comes and goes —
`veto_inside` on a band, for instance. Whether softening it improves OUTCOMES
needs the trade join, and this tool cannot answer that. It localises the churn;
it does not license a change.

Read-only, stdlib only, streams one file at a time (v1.0 of two earlier tools in
this repo were OOM-killed by loading the whole corpus — see regime_switch_cost).

USAGE
    python3 tests/veto_attribution.py
    python3 tests/veto_attribution.py --since 2026-08-03 --regime RANGING
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
ZERO = 0.001


def _vetoes(bd: dict) -> dict:
    """Every published hard veto in a breakdown block.

    Keyed by name so the report can attribute a transition to a SPECIFIC gate.
    A veto is published as 0.0 or 1.0; anything else in the breakdown is a
    corroborator or a diagnostic and is ignored here.
    """
    return {k: v for k, v in (bd or {}).items()
            if k.startswith("veto") and isinstance(v, (int, float))}


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default=REPLAY_GLOB)
    ap.add_argument("--since", default="")
    ap.add_argument("--regime", default="", help="restrict to one regime")
    ap.add_argument("--top", type=int, default=12)
    a = ap.parse_args(argv[1:])

    paths = [p for p in sorted(glob.glob(os.path.expanduser(a.glob)))
             if DATE_RE.search(p)
             and (not a.since or DATE_RE.search(p).group(1) >= a.since)]
    if not paths:
        print(f"no replay files matched {a.glob}")
        return 2

    # transitions[(regime, cause)] = count
    trans = collections.Counter()
    totals = collections.Counter()
    no_bd = collections.Counter()
    days = []

    for path in paths:
        days.append(DATE_RE.search(path).group(1))
        prev = {}            # (sym, regime) -> (was_zero, vetoes)
        for line in open(path, errors="ignore"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:                                    # noqa: BLE001
                continue
            sym = r.get("sym", "?")
            scores = r.get("scores") or {}
            bds = r.get("breakdown") or {}
            for reg, sc in scores.items():
                if a.regime and reg != a.regime:
                    continue
                is_zero = (sc or 0.0) <= ZERO
                bd = bds.get(reg) or bds.get(reg.split("_")[0]) or {}
                vt = _vetoes(bd)
                if not vt:
                    no_bd[reg] += 1
                key = (sym, reg)
                if key in prev:
                    was_zero, was_vt = prev[key]
                    if was_zero != is_zero:
                        totals[reg] += 1
                        # WHICH veto changed across this transition?
                        # v1.1 — A KEY THAT APPEARS OR DISAPPEARS IS NOT A VETO
                        # FLIP. Several regimes have two evaluation branches (a
                        # window path and a reduced vol-only fallback) that
                        # publish DIFFERENT key sets. v1.0 compared
                        # vt.get(k) != was_vt.get(k), so a missing key read as a
                        # change — and that is how RANGING was credited with
                        # 4,929 `veto_flat` transitions when its veto_flat is a
                        # HARDCODED 1.0 that never changes. The live veto_flat
                        # belongs to COMPRESSION.
                        # A branch change is a real and separate cause: it means
                        # the regime switched between full and fallback
                        # evaluation, which is a BAR-AVAILABILITY event, not a
                        # market one. It gets its own row.
                        both = set(vt) & set(was_vt)
                        changed = [k for k in both if vt[k] != was_vt[k]]
                        appeared = set(vt) ^ set(was_vt)
                        if appeared and not changed:
                            trans[(reg, f"(branch change: {'/'.join(sorted(appeared))[:26]})")] += 1
                            continue
                        if not changed:
                            # zero<->nonzero with NO veto change means the
                            # corroborator sum or a soft term did it — a
                            # genuine score crossing, which is the case a
                            # switching cost COULD help.
                            trans[(reg, "(no veto changed — soft/corroborator)")] += 1
                        else:
                            for c in changed:
                                trans[(reg, c)] += 1
                prev[key] = (is_zero, vt)

    if not totals:
        print("no zero<->nonzero transitions found. If the replay records carry "
              "no `breakdown`\nblock, this tool cannot attribute anything — "
              "check one record's keys first.")
        return 2

    print(f"{len(days)} session(s) {days[0]}..{days[-1]}\n")
    print("ZERO <-> NON-ZERO TRANSITIONS, attributed to the veto that changed\n")
    print(f"  {'regime':<20}{'cause':<40}{'count':>8}{'share':>8}")
    for (reg, cause), n in trans.most_common(a.top):
        print(f"  {reg[:20]:<20}{cause[:40]:<40}{n:>8,}{n/totals[reg]:>8.0%}")

    print(f"\n  {'regime':<20}{'total transitions':>20}")
    for reg, n in totals.most_common():
        print(f"  {reg[:20]:<20}{n:>20,}")

    if no_bd:
        print(f"\n  ⚠️ {sum(no_bd.values()):,} tick-regimes had NO published "
              f"veto in their breakdown.")
        print("  Those transitions cannot be attributed and are counted under "
              "'(no veto changed)',\n  which will overstate that row. Check "
              "whether the replay carries `breakdown`.")

    print("\n  READING IT")
    print("  A veto with a large share is where the churn lives, and the")
    print("  candidate fix is to make it a SOFT DAMPER (a value in [0,1] that")
    print("  reduces the score) rather than a HARD GATE (a boolean that")
    print("  annihilates it). A damper degrades; a gate teleports.")
    print("  A large '(no veto changed)' share means the opposite: those")
    print("  transitions ARE score crossings, and a switching cost would help")
    print("  them — which would partly rehabilitate regime_switch_cost.")
    print("\n  ⚠️ THIS DOES NOT SHOW THE VETO IS WRONG. A veto that fires often")
    print("  may be correctly describing a condition that genuinely comes and")
    print("  goes. Whether softening it improves OUTCOMES needs the trade join.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
