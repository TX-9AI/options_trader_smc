#!/usr/bin/env python3
"""
tests/sweep_opportunity_audit.py — v1.1 — 2026-08-11

v1.1 — `--symbol SYM` applies the STRATEGY's own gates to the cleared ticks.
       Clearing the L1 floor only gets sweep as far as `generate_signal`; two
       further gates refuse there, both logging at DEBUG and therefore invisible
       at the fleet's INFO level — and BOTH are testable from fields already in
       this corpus. The ORB-ownership gate is unconditionally open after 11:00
       ET, and the strategy hard-rejects at SWEEP_MAX_AGE_BARS=8 while L1's
       age_decay is only a 3-bar half-life. A tick that is post-11:00 AND fresh
       AND still did not trade is refused by something this corpus cannot see,
       and the tool says so rather than guessing.

DID SWEEP HAVE OPPORTUNITIES IT DECLINED, AND WHY — the whole funnel, end to
end, from data already on disk.

THE SITUATION. Sweep is historically the best-selecting strategy in the book
(9% never-favourable against continuation's 48%; `Sweep Reversal Long` 81% WR,
+$2,844). On 2026-08-11 it produced ONE trade fleet-wide, against 231 readiness
arm episodes. `sweep_score_dist` says the setup score is exactly ZERO on 96.6%
of ticks — but a bare "96.6% annihilated" cannot distinguish

    "there was no sweep to take"        (nothing declined — the tape was quiet)
from
    "there WAS a sweep and we refused"  (something declined it — and what?)

and those have opposite responses. This splits them.

THE FUNNEL, and every stage is a read of `breakdown.SWEEP_REVERSAL` which the
replay corpus already records on every tick:

  STAGE 0  all ticks
  STAGE 1  veto_loc = 1        a NAMED LEVEL was swept          <- opportunity
  STAGE 2  + veto_reclaim = 1  price REJECTED and reclaimed it  <- a reversal
  STAGE 3  + veto_accept = 1   not accepted beyond the level    <- the full spec
  STAGE 4  + score >= floor    cleared the dispatch gate
  STAGE 5  + a trade fired

Stage 3 IS the operator's stated condition set — "a move into a named liquidity
pool, accompanied by a rejection or exhaustion." Everything that reaches stage 3
and dies before stage 5 is AN OPPORTUNITY DECLINED, and the soft-necessary and
corroborator terms in the same breakdown say which one did it:
    trend_opp   (PLTR protection: opposing trend suppression)
    age_decay   (0.5 ** age_bars/3 — the setup went stale)
    rejq_val    (rejection quality: depth x level touch-count)
    exh_val     (exhaustion; note "" -> 0.0, the missing-momentum case)
    spent_val   (v1.4 spent-move context)

THE PAYOFF — DODGED vs MISSED. A count of declines says nothing about whether
declining was RIGHT. For every stage-3 tick that did not trade, this measures
the tape's forward move in the sweep's own intended direction:
    DODGED  price continued AGAINST the reversal  -> the gate earned its keep
    MISSED  price reversed as the setup predicted -> the gate cost money
A floor whose declines are mostly MISSED is too tight. That is the only
evidence that can justify moving it, and it is the reason this tool exists
rather than another distribution print.

⚠️ WHY THE EXISTING LEDGER CANNOT ANSWER THIS. `analysis/rejection_ledger.py`
(L3.2a) already implements DODGED/MISSED — but it reads `scored` and
`disposition` events, and below the floor sweep NEVER GENERATES A SIGNAL, so no
`scored` row is ever written. The existing machinery is structurally blind to
exactly this strategy's declines. Recorded so the overlap is not mistaken for
duplication.

⚠️ WHAT THIS CANNOT SEE, stated so the output is not over-read:
  - THE SLOT. One position per box; a qualifying tick on an occupied box could
    never have traded regardless of score. Occupancy is not in the replay
    corpus, so a stage-4 tick that did not trade may be a slot conflict rather
    than a refusal. Cross-check against the trades DB before concluding.
  - LIVE vs REPLAY. The corpus covers ALL symbol-sessions offline; the fleet
    wakes ~15. A qualifying symbol-day on a box that was never awake is not a
    missed trade. Per-symbol counts are printed so this is checkable.
  - Forward move is measured on the UNDERLYING, not on premium. A reversal that
    happens is not the same as a fill that pays.

READ-ONLY. stdlib only. Touches no fleet, no live path, writes nothing.

USAGE (control)
    python3 tests/sweep_opportunity_audit.py                    # whole corpus
    python3 tests/sweep_opportunity_audit.py --since 2026-08-11
    python3 tests/sweep_opportunity_audit.py --horizons 5,10,20
"""

import argparse
import collections
import glob
import json
import os
import sys

REPORTS = os.path.expanduser("~/day_trader_pro/reports")
GLOB = os.path.join(REPORTS, "regime_replay_*.jsonl")
SWEEP = "SWEEP_REVERSAL"
FLOOR_LONG = float(os.environ.get("OT_SWEEP_SETUP_FLOOR", "0.05"))
FLOOR_SHORT = float(os.environ.get("OT_SWEEP_SETUP_FLOOR_SHORT", "0.20"))


def pct(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    return s[min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))]


def f(bd, k, default=None):
    v = bd.get(k)
    return v if isinstance(v, (int, float)) else default


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default=GLOB)
    ap.add_argument("--since", default="")
    ap.add_argument("--horizons", default="5,10,20",
                    help="forward bars for the DODGED/MISSED read")
    ap.add_argument("--symbol", default="",
                    help="dump the CLEARED ticks for one symbol and test them "
                         "against the STRATEGY's own gates (v1.1)")
    a = ap.parse_args(argv[1:])
    horizons = [int(x) for x in a.horizons.split(",") if x.strip()]

    files = sorted(glob.glob(a.glob))
    if a.since:
        files = [p for p in files
                 if os.path.basename(p)[len("regime_replay_"):-len(".jsonl")] >= a.since]
    if not files:
        print(f"no replay files matched {a.glob}")
        return 1

    # per symbol-day series so forward drift stays inside one session
    series = collections.defaultdict(list)
    for p in files:
        date = os.path.basename(p)[len("regime_replay_"):-len(".jsonl")]
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:                              # noqa: BLE001
                    continue
                series[(date, r.get("sym", "?"))].append(r)

    stage = collections.Counter()
    killer = collections.Counter()          # what killed a stage-3 tick
    declined = []                           # stage-3, below floor
    cleared = []                            # stage-3, above floor
    symday_stage3 = collections.Counter()
    symday_cleared = collections.Counter()
    nonzero_scores = []

    for (date, sym), rows in series.items():
        for i, r in enumerate(rows):
            bd = ((r.get("breakdown") or {}).get(SWEEP)) or {}
            sc = ((r.get("scores") or {}).get(SWEEP))
            sc = float(sc) if isinstance(sc, (int, float)) else 0.0
            if sc > 0:
                nonzero_scores.append(sc)
            stage["0_all"] += 1
            vloc = f(bd, "veto_loc")
            if vloc is None:
                stage["no_breakdown"] += 1
                continue
            if vloc <= 0:
                stage["1_no_named_level"] += 1
                continue
            stage["1_named_level_swept"] += 1
            if f(bd, "veto_reclaim", 0.0) <= 0:
                stage["2_no_reclaim"] += 1
                continue
            stage["2_reclaimed"] += 1
            if f(bd, "veto_accept", 0.0) <= 0:
                stage["3_accepted_beyond"] += 1
                continue
            stage["3_FULL_SPEC"] += 1
            symday_stage3[(date, sym)] += 1

            direction = str(bd.get("dir") or "").lower()
            floor = FLOOR_SHORT if direction.startswith("s") else FLOOR_LONG
            rec = {"date": date, "sym": sym, "i": i, "score": sc,
                   "dir": direction or "?", "floor": floor, "bd": bd,
                   "ts": str(r.get("ts") or "")}
            if sc >= floor:
                stage["4_cleared_floor"] += 1
                symday_cleared[(date, sym)] += 1
                cleared.append(rec)
            else:
                stage["4_below_floor"] += 1
                declined.append(rec)
                # WHICH TERM SUPPRESSED IT — the multiplicative structure means
                # the smallest soft-necessary is the dominant suppressor.
                to = f(bd, "trend_opp", 1.0)
                ad = f(bd, "age_decay", 1.0)
                rq = f(bd, "rejq_val", 0.0)
                ex = f(bd, "exh_val", 0.0)
                if to <= 0.01:
                    killer["trend_opp ~0 (opposing trend — PLTR guard)"] += 1
                elif ad <= 0.10:
                    killer["age_decay ~0 (setup went stale, >10 bars)"] += 1
                elif to < ad and to < 0.5:
                    killer["trend_opp low (partial trend opposition)"] += 1
                elif ad < 0.5:
                    killer["age_decay low (setup ageing)"] += 1
                elif rq + ex <= 0.2:
                    killer["weak corroborators (rejq + exh both low)"] += 1
                else:
                    killer["no single dominant term — score just small"] += 1

    tot = stage["0_all"]
    print("=" * 72)
    print(f"  SWEEP OPPORTUNITY AUDIT — {len(files)} file(s)"
          f"{', since ' + a.since if a.since else ''}")
    print(f"  floors in force: LONG {FLOOR_LONG}   SHORT {FLOOR_SHORT}")
    print("=" * 72)

    print(f"\n  THE FUNNEL ({tot:,} ticks)\n")
    rows_out = [
        ("ticks with a breakdown", tot - stage["no_breakdown"]),
        ("1. a NAMED LEVEL was swept", stage["1_named_level_swept"]),
        ("2. ...and price RECLAIMED it", stage["2_reclaimed"]),
        ("3. ...and was NOT accepted beyond  <- FULL SPEC",
         stage["3_FULL_SPEC"]),
        ("4. ...and the score CLEARED the floor", stage["4_cleared_floor"]),
    ]
    prev = None
    for label, n in rows_out:
        share = f"{100.0*n/max(tot,1):5.1f}% of ticks"
        drop = "" if prev is None else f"   (kept {100.0*n/max(prev,1):4.1f}% of prior)"
        print(f"    {label:<48}{n:>8}  {share}{drop}")
        prev = n

    print(f"\n  ⇒ OPPORTUNITIES (full spec met):     {stage['3_FULL_SPEC']:>8}")
    print(f"    of which DECLINED by the floor:    {stage['4_below_floor']:>8}")
    print(f"    of which cleared:                  {stage['4_cleared_floor']:>8}")
    print(f"    distinct symbol-days with an opportunity: "
          f"{len(symday_stage3)}   that cleared: {len(symday_cleared)}")

    if stage["3_FULL_SPEC"] == 0:
        print("\n  ⇒ NOTHING WAS DECLINED. The full spec was never met on any tick —")
        print("    sweeps simply did not occur. The floor is irrelevant; the")
        print("    constraint is the tape (or the three vetoes are mis-specified,")
        print("    which is a different and much larger question).")
        return 0

    print(f"\n  WHY THE DECLINED ONES DIED  (n={len(declined)})")
    for k, n in killer.most_common():
        print(f"    {n:>7}  {100.0*n/max(len(declined),1):5.1f}%  {k}")

    # ── DODGED vs MISSED ────────────────────────────────────────────────────
    print(f"\n{'=' * 72}\n  WAS DECLINING RIGHT?  (forward move in the sweep's own direction)"
          f"\n{'=' * 72}")
    print("  DODGED = tape continued AGAINST the reversal -> the gate earned it")
    print("  MISSED = tape reversed as the setup predicted -> the gate cost money\n")

    def fwd(rows, i, h, direction, px0):
        j = i + h
        if j >= len(rows):
            return None
        p1 = rows[j].get("price")
        if not p1 or not px0:
            return None
        d = (float(p1) - float(px0)) / float(px0)
        # a LOW sweep is faded LONG; a HIGH sweep is faded SHORT
        return d if direction.startswith("l") else -d

    for pop_name, pop in (("DECLINED (below floor)", declined),
                          ("CLEARED  (above floor)", cleared)):
        if not pop:
            continue
        print(f"  {pop_name}")
        for h in horizons:
            vals = []
            for rec in pop:
                rows = series[(rec["date"], rec["sym"])]
                px0 = rows[rec["i"]].get("price")
                v = fwd(rows, rec["i"], h, rec["dir"], px0)
                if v is not None:
                    vals.append(v)
            if not vals:
                continue
            miss = sum(1 for v in vals if v > 0)
            print(f"    +{h:>3} bars  n={len(vals):<6} "
                  f"MISSED {miss:>5} ({100.0*miss/len(vals):4.1f}%)   "
                  f"DODGED {len(vals)-miss:>5} ({100.0*(len(vals)-miss)/len(vals):4.1f}%)   "
                  f"median {pct(vals,.5)*100:+.3f}%")
        print()

    # ── WHERE ───────────────────────────────────────────────────────────────
    print(f"  SYMBOL-DAYS WITH AN OPPORTUNITY (top 12)")
    print(f"    {'date':12}{'sym':8}{'stage-3':>9}{'cleared':>9}")
    for (dt, sym), n in symday_stage3.most_common(12):
        print(f"    {dt:12}{sym:8}{n:>9}{symday_cleared.get((dt,sym),0):>9}")
    print("\n    ⚠️ The corpus covers ALL symbol-sessions; the fleet wakes ~15.")
    print("       A symbol-day here that was never AWAKE is not a missed trade.")
    print("       Cross-check against the wake list before reading a loss.")

    if nonzero_scores:
        print(f"\n  nonzero score distribution: p50={pct(nonzero_scores,.5):.3f} "
              f"p90={pct(nonzero_scores,.9):.3f} max={max(nonzero_scores):.3f}")

    print("\n  ⚠️ A stage-4 tick that did not trade may be a SLOT conflict (one")
    print("     position per box), not a refusal. Occupancy is not in this corpus.")

    # ── v1.1 — THE STRATEGY'S OWN GATES, applied to the CLEARED ticks ────────
    # Clearing the L1 floor only gets sweep to `generate_signal`. TWO further
    # gates then refuse, both logging at DEBUG (invisible at the fleet's INFO
    # level), and BOTH are testable from fields already in this corpus:
    #
    #   ORB OWNERSHIP  — sweep is hard-blocked while the ORB has a live claim
    #     on price (inside range / armed awaiting retest / position open /
    #     range failed back inside). It is RELEASED past the 11:00 ET cutoff,
    #     on a stale retest, on a runaway, or when no range exists.
    #     ⚠️ AND A RUNAWAY RELEASE HANDS PRICE TO CONTINUATION FIRST — the
    #     handoff path is Priority 2, sweep is 2.5, so "released" never means
    #     "sweep gets it", only "sweep is now eligible IF continuation passes".
    #     Before 11:00 the ORB state decides and this corpus cannot see it.
    #     AFTER 11:00 the gate is unconditionally open, so a cleared tick after
    #     11:00 that did not trade was refused by something ELSE.
    #
    #   AGE  — the strategy hard-rejects at SWEEP_MAX_AGE_BARS = 8, while L1's
    #     age_decay is a 3-bar HALF-LIFE that merely shrinks the score. A strong
    #     setup can therefore still clear the 0.05 floor at an age the STRATEGY
    #     refuses outright. That disagreement window is the interesting one.
    if a.symbol:
        want = a.symbol.upper()
        rows_c = [r for r in cleared if r["sym"].upper() == want]
        print(f"\n{'=' * 72}\n  {want} — CLEARED TICKS vs THE STRATEGY'S OWN GATES"
              f"\n{'=' * 72}")
        if not rows_c:
            print(f"  no cleared ticks for {want} in range.")
            return 0
        MAX_AGE = float(os.environ.get("OT_SWEEP_MAX_AGE_BARS", "8"))
        post11 = [r for r in rows_c if r["ts"] >= "11:00"]
        aged = [r for r in rows_c if (f(r["bd"], "age_bars", 0.0) or 0.0) > MAX_AGE]
        print(f"  cleared ticks: {len(rows_c)}")
        print(f"    AFTER 11:00 ET (ORB gate unconditionally OPEN): {len(post11)}")
        print(f"    age_bars > {MAX_AGE:.0f} (strategy HARD-REJECTS regardless): {len(aged)}")
        free = [r for r in post11 if (f(r["bd"], "age_bars", 0.0) or 0.0) <= MAX_AGE]
        print(f"    ⇒ past BOTH gates (post-11:00 AND fresh enough): {len(free)}")
        if not post11:
            print("\n  ⇒ EVERY cleared tick was BEFORE 11:00 — the ORB still had a")
            print("    claim on price, so sweep was deferring to ORB BY DESIGN.")
            print("    Not a defect. The fix, if any, is the ORB cutoff, not sweep.")
        elif not free:
            print("\n  ⇒ Every post-11:00 cleared tick was TOO OLD for the strategy")
            print(f"    (>{MAX_AGE:.0f} bars). L1's 3-bar HALF-LIFE and the strategy's hard")
            print("    8-bar cutoff DISAGREE: the score still clears 0.05 at ages the")
            print("    strategy refuses. That gap is the defect, and it is a constant,")
            print("    not a scorer problem.")
        else:
            print(f"\n  ⇒ {len(free)} tick(s) passed BOTH the ORB gate and the age gate")
            print("    and STILL did not trade. The refusal is one of the remaining")
            print("    debug-logged paths: recovery window, 1m BOS confirmation,")
            print("    confluence floor, or the short floor. Those need the box logs")
            print("    at DEBUG — none of them is visible from this corpus.")
        print(f"\n  {'ts':8}{'dir':7}{'score':>8}{'floor':>7}{'age':>6}"
              f"{'age_dec':>9}{'trend_opp':>11}")
        for r in rows_c[:25]:
            bd = r["bd"]
            print(f"  {r['ts']:8}{r['dir']:7}{r['score']:>8.3f}{r['floor']:>7.2f}"
                  f"{(f(bd,'age_bars',0) or 0):>6.0f}"
                  f"{(f(bd,'age_decay',0) or 0):>9.3f}"
                  f"{(f(bd,'trend_opp',0) or 0):>11.3f}")
        if len(rows_c) > 25:
            print(f"  … {len(rows_c)-25} more")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
