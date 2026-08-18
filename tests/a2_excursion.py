#!/usr/bin/env python3
"""
tests/a2_excursion.py — v1.0 — 2026-08-01

DOES THE PAUSED-TREND STATE PAY, AND TO WHICH SIDE OF THETA?

`a2_partition.py` settled the diagnosis: H1 (horizon co-truth) and H2 (opening
drive) are real, H3 (gap artifact) is dead as a cause. A2 is naming a genuine
state, not a defect. That leaves the only question that was ever commercially
interesting — and the operator's framing of it is what this file measures:

    "If price is going NOWHERE in that environment, that should be worked into
     our STOP logic. If price is expected to go SOMEWHERE in that environment,
     let's guess WHERE and trade it."
    "It should be relevant to whether we are long or short theta."

WHY ONE NUMBER CANNOT ANSWER BOTH, and this is the whole design
    Signed drift answers the LONG-theta question and tells a short-premium
    position NOTHING. A session that runs +2% then -2% has zero drift and would
    have blown through both wings of a condor. So NOWHERE and SOMEWHERE are
    different statistics computed from the same tape:

      theta NEGATIVE (needs movement)   continuation (debit directional),
                                        sweep_reversal (naked OTM ~0.20d), orb
        -> SIGNED forward return in the TRENDING direction, plus how fast it
           arrives, because decay is the clock it races.

      theta POSITIVE (wants stillness)  iron_condor, butterfly
        -> MAX ABSOLUTE EXCURSION over the window, and its DISTRIBUTION. Note the
           butterfly is a DEBIT structure that is theta-positive near the body —
           which is why theta sign, not credit/debit, is the correct axis.

THE DISTRIBUTION IS A STRIKE RULE, not just a verdict
    p50/p75/p90/max of |excursion| per cell says directly where a short strike
    belongs: place it where p90 of instances stayed inside and the wing is priced
    from the state's own behaviour rather than from a fixed delta or a Bollinger
    anchor. Same argument the pitchfork white paper makes for rail-anchored
    strikes, arriving from a different direction and available sooner.

THE HYPOTHESIS THIS IS BUILT TO KILL OR CONFIRM
    If paused_trend predicts LOW excursion, the fleet currently dispatches the
    WRONG THETA SIGN into it. A2 ticks have TRENDING > 0.5, so argmax tends
    TRENDING -> continuation fires -> a long-theta position pays decay to sit in
    tape that is not moving. Meanwhile condor and butterfly are gated to
    RANGING/COMPRESSION and are locked out of exactly the state they would want.
    That is a mechanism-level candidate for continuation standalone's -$2,024 at
    46% WR which has nothing to do with its entry conditions.

CONDITIONING — corrected from a2_partition's own closing line
    That tool says evaluate on CLEAN x FLAT because it is uncontaminated by gap.
    It is uncontaminated by GAP but SELECTED ON DAY TYPE: the partition showed
    FLAT-open days run hotter in every window (CLEAN 3.65% vs CONT 1.49% /
    REV 1.91%), i.e. gap class proxies for day type — gap days are trend days,
    flat-open days are range-ish. Judging the state only on FLAT would measure it
    on the least-trending days in the corpus, precisely where a paused trend is
    least likely to resume, and would understate the edge.
    So: CLEAN across ALL THREE classes, with gap_class reported as a COVARIATE
    rather than used as a filter. n~95k instead of ~6.5k.

WHAT A RESULT WITHOUT A CONTROL WOULD MEAN — nothing
    Forward drift on any tick is mostly market drift. Every statistic here is
    reported against MATCHED CONTROL ticks: same symbol, same time bucket, same
    gap class, NOT in violation. The number that matters is the difference.

INSTRUMENT NOTE, so nobody reads a low-excursion result as a licence to sell naked
    Undefined-risk structures are OUT OF SCOPE by decision. SPX's nominal size
    (~$640k/contract) makes a naked strangle a single indivisible bite larger
    than the per-trade risk budget, and that constraint is treated as protective.
    The low-excursion view is expressed as a DEFINED-RISK wide iron condor, where
    spread width is the sizing dial and risk_manager.compute_condor_leg_size
    already yields a real max_loss — so the session caps and session_guard keep
    their denominator. This tool sizes nothing and recommends no instrument; it
    reports how far price went.

EPISODE DURATION IS A PREREQUISITE, NOT A FOOTNOTE
    Found while running this against a planted corpus: the forward window from a
    violation tick spans N bars, but NOTHING GUARANTEES THE STATE PERSISTS across
    them. If paused_trend episodes are three ticks long, a 10-bar window measures
    mostly non-state tape and every statistic is diluted toward baseline — the
    planted test showed violations at HALF the control volatility coming back as
    p90 0.248% vs 0.245%, i.e. no signal, because the windows overlapped
    non-violating tape.
    So the duration distribution is reported FIRST and the horizons are chosen
    against it. A horizon longer than the median episode is measuring the wrong
    thing. `--persistent-only` restricts to ticks whose state holds for the whole
    window, which is the clean version of the question at the cost of sample.

UNITS
    Percent of price, not ATR multiples. Strike distance scales with price, so
    percent is directly what a strike rule reads and is comparable across SPX and
    QQQ without a second normalisation to get wrong.

USAGE (single line, control box, repo root)
    python3 tests/a2_excursion.py
    python3 tests/a2_excursion.py --horizons 5,10,20 --window CLEAN

Read-only. Streams the corpus. Places nothing, sizes nothing.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import math
import os
import re
import sys

DEFAULT_GLOBS = ["~/day_trader_pro/reports/regime_replay_*.jsonl"]
DEFAULT_GAPS = "~/day_trader_pro/reports/gap_pct.json"

TREND_KEYS = ("TRENDING_BULL", "TRENDING_BEAR")
DATE_RE = re.compile(r"(20\d\d-\d\d-\d\d)")
BUCKETS = (("OPEN", "09:30", "10:40"),
           ("DECAY", "10:40", "12:00"),
           ("CLEAN", "12:00", "16:00"))
CLASSES = ("CONT", "FLAT", "REV")
MIN_CELL_N = 500          # same refusal floor as a2_partition


def time_bucket(ts: str):
    for name, lo, hi in BUCKETS:
        if lo <= ts < hi:
            return name
    return None


def _mean_ci(xs):
    """Mean with a 95% half-width. Returns (mean, halfwidth, n)."""
    n = len(xs)
    if n < 2:
        return (xs[0] if n else 0.0), 0.0, n
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return m, 1.96 * math.sqrt(var / n), n


def _pcts(xs, ps=(50, 75, 90, 95)):
    if not xs:
        return {}
    s = sorted(xs)
    out = {}
    for p in ps:
        out[p] = s[min(len(s) - 1, max(0, int(round(p / 100.0 * (len(s) - 1)))))]
    out["max"] = s[-1]
    return out


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gaps", default=DEFAULT_GAPS)
    ap.add_argument("--jsonl", default="")
    ap.add_argument("--horizons", default="5,10,20",
                    help="forward bars (1m ticks) to measure over")
    ap.add_argument("--persistent-only", action="store_true",
                    help="only measure from ticks whose violation state holds "
                         "for the WHOLE forward window (clean but smaller n)")
    ap.add_argument("--window", default="CLEAN",
                    help="time bucket to report; ALL for every bucket")
    a = ap.parse_args(argv[1:])
    horizons = [int(h) for h in a.horizons.split(",") if h.strip()]
    want = [b[0] for b in BUCKETS] if a.window.upper() == "ALL" else [a.window.upper()]

    gaps_path = os.path.expanduser(a.gaps)
    if not os.path.isfile(gaps_path):
        print(f"No gap lookup at {gaps_path} — run tests/gap_backfill.py first.")
        return 2
    gaps = json.load(open(gaps_path)).get("sessions", {})

    paths = ([a.jsonl] if a.jsonl else
             [p for g in DEFAULT_GLOBS for p in sorted(glob.glob(os.path.expanduser(g)))])
    paths = [p for p in paths if os.path.isfile(os.path.expanduser(p))]
    if not paths:
        print("No replay jsonl found.")
        return 2

    # (bucket, class, violation?) -> {horizon: [signed_ret], ...}
    signed = collections.defaultdict(lambda: collections.defaultdict(list))
    excurs = collections.defaultdict(lambda: collections.defaultdict(list))
    favor = collections.defaultdict(lambda: collections.defaultdict(list))
    advers = collections.defaultdict(lambda: collections.defaultdict(list))
    truncated = 0
    episodes = []                 # lengths of consecutive-violation runs

    for path in paths:
        p = os.path.expanduser(path)
        m = DATE_RE.search(os.path.basename(p))
        if not m:
            continue
        day = gaps.get(m.group(1))
        if day is None:
            continue

        # group the day's ticks by symbol so forward windows never cross symbols
        by_sym = collections.defaultdict(list)
        with open(p) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:                                # noqa: BLE001
                    continue
                by_sym[r.get("sym", "?")].append(r)

        for sym, recs in by_sym.items():
            grec = day.get(sym)
            if not grec or grec.get("gap_class") not in CLASSES:
                continue
            klass = grec["gap_class"]
            prices = [float(r.get("price") or 0.0) for r in recs]
            # violation mask for the whole symbol-day, so episode length and
            # persistence are both answerable without re-deriving per tick
            viols = []
            for r in recs:
                sc = r.get("scores") or {}
                t_ = max(float(sc.get("TRENDING_BULL") or 0.0),
                         float(sc.get("TRENDING_BEAR") or 0.0))
                viols.append(t_ > 0.5 and float(sc.get("RANGING") or 0.0) > 0.5)
            run = 0
            for v in viols:
                if v:
                    run += 1
                elif run:
                    episodes.append(run)
                    run = 0
            if run:
                episodes.append(run)

            for i, r in enumerate(recs):
                bucket = time_bucket(r.get("ts", ""))
                if bucket not in want:
                    continue
                p0 = prices[i]
                if p0 <= 0:
                    continue
                sc = r.get("scores") or {}
                bull = float(sc.get("TRENDING_BULL") or 0.0)
                bear = float(sc.get("TRENDING_BEAR") or 0.0)
                trend = max(bull, bear)
                rng = float(sc.get("RANGING") or 0.0)
                viol = trend > 0.5 and rng > 0.5
                # direction the TRENDING score is asserting — what "resumes" means
                sign = 1.0 if bull >= bear else -1.0
                key = (bucket, klass, viol)

                for h in horizons:
                    j = i + h
                    if j >= len(prices):
                        truncated += 1
                        continue
                    if a.persistent_only and viol and not all(viols[i:j + 1]):
                        continue
                    path_px = prices[i + 1:j + 1]
                    if not path_px or min(path_px) <= 0:
                        continue
                    rets = [100.0 * (px - p0) / p0 for px in path_px]
                    signed[key][h].append(sign * rets[-1])
                    excurs[key][h].append(max(abs(x) for x in rets))
                    favor[key][h].append(max(sign * x for x in rets))
                    advers[key][h].append(min(sign * x for x in rets))

    if not signed:
        print("Nothing measured — check that the corpus dates match the gap lookup.")
        return 2

    print(f"corpus files : {len(paths)}   horizons(min): {horizons}   "
          f"window: {','.join(want)}")
    print(f"truncated    : {truncated} tick-horizons ran past the session close "
          f"(excluded, not extrapolated)")
    print("units        : percent of price. Control = same symbol/bucket/gap "
          "class, NOT in violation.")
    if a.persistent_only:
        print("mode         : --persistent-only (state must hold the whole window)")

    # Duration FIRST — it decides whether any horizon below is meaningful.
    if episodes:
        ep = _pcts(episodes, (50, 75, 90, 95))
        print(f"\nEPISODE DURATION (consecutive violation ticks, n={len(episodes)})")
        print(f"  p50 {ep[50]} bars   p75 {ep[75]}   p90 {ep[90]}   "
              f"p95 {ep[95]}   max {ep['max']}")
        too_long = [h for h in horizons if h > ep[50]]
        if too_long:
            print(f"  ⚠ horizons {too_long} EXCEED the median episode ({ep[50]} bars).")
            print("    Those windows spend most of their length OUTSIDE the state, "
                  "so the\n    statistics below are diluted toward baseline. Re-run "
                  "with --persistent-only,\n    or with horizons at or under the "
                  "median, before reading them as an edge.")
        else:
            print(f"  horizons {horizons} all sit within the median episode — "
                  "windows are in-state.")
    print()

    for bucket in want:
        for h in horizons:
            v_sig = [x for k, d in signed.items() if k[0] == bucket and k[2] for x in d[h]]
            c_sig = [x for k, d in signed.items() if k[0] == bucket and not k[2] for x in d[h]]
            v_exc = [x for k, d in excurs.items() if k[0] == bucket and k[2] for x in d[h]]
            c_exc = [x for k, d in excurs.items() if k[0] == bucket and not k[2] for x in d[h]]
            v_fav = [x for k, d in favor.items() if k[0] == bucket and k[2] for x in d[h]]
            v_adv = [x for k, d in advers.items() if k[0] == bucket and k[2] for x in d[h]]
            if len(v_sig) < MIN_CELL_N or len(c_sig) < MIN_CELL_N:
                print(f"{bucket} h={h}: REFUSED — n too small "
                      f"(violation {len(v_sig)}, control {len(c_sig)}, floor {MIN_CELL_N})")
                continue

            vm, vh, vn = _mean_ci(v_sig)
            cm, ch, cn = _mean_ci(c_sig)
            print(f"── {bucket}  h={h} bars ──────────────────────────────────")
            print("  SOMEWHERE (theta NEGATIVE — continuation / sweep / orb)")
            print("    signed return in the TRENDING direction")
            print(f"      violation {vm:+.4f}% ±{vh:.4f}  (n={vn})")
            print(f"      control   {cm:+.4f}% ±{ch:.4f}  (n={cn})")
            diff = vm - cm
            sep = abs(diff) > (vh + ch)
            if not sep:
                print(f"      -> NO EDGE: the difference ({diff:+.4f}%) is inside the "
                      f"confidence bands.\n"
                      f"         The state is real but the trend does NOT resume more "
                      f"than baseline.")
            elif diff > 0:
                print(f"      -> RESUMES: {diff:+.4f}% over control. The pause is a "
                      f"pause. Long-theta\n         entries have somewhere to go — "
                      f"target the TRENDING direction.")
            else:
                print(f"      -> EXHAUSTS: {diff:+.4f}% vs control — it goes the OTHER "
                      f"way. The 'pause'\n         is a top/bottom, which INVERTS the "
                      f"item's assumption. Worth more than a resume.")

            vp, cp = _pcts(v_exc), _pcts(c_exc)
            print("  NOWHERE (theta POSITIVE — condor / butterfly)")
            print("    max |excursion| over the window")
            print(f"      violation  p50 {vp[50]:.3f}%  p75 {vp[75]:.3f}%  "
                  f"p90 {vp[90]:.3f}%  p95 {vp[95]:.3f}%  max {vp['max']:.3f}%")
            print(f"      control    p50 {cp[50]:.3f}%  p75 {cp[75]:.3f}%  "
                  f"p90 {cp[90]:.3f}%  p95 {cp[95]:.3f}%  max {cp['max']:.3f}%")
            if vp[90] < cp[90]:
                print(f"      -> STILLER than baseline at p90 ({vp[90]:.3f}% vs "
                      f"{cp[90]:.3f}%). This is the cell\n         a defined-risk wide "
                      f"condor wants — and the fleet currently sends\n         "
                      f"continuation (long theta) into it instead.")
            else:
                print(f"      -> NOT stiller than baseline ({vp[90]:.3f}% vs "
                      f"{cp[90]:.3f}%). No short-premium case here.")
            print(f"    STRIKE RULE: a short strike at {vp[90]:.3f}% from spot "
                  f"contains 90% of these\n      instances over {h} bars; "
                  f"{vp[95]:.3f}% contains 95%.")

            fm, _, _ = _mean_ci(v_fav)
            am, _, _ = _mean_ci(v_adv)
            print(f"  WHICH WING — favorable {fm:+.3f}% / adverse {am:+.3f}% "
                  f"(mean, trend-signed)")
            print(f"    STOP LOGIC: mean adverse excursion is {abs(am):.3f}% of "
                  f"price. A stop tighter\n      than that is a noise stop in this "
                  f"state, not a risk control.\n")

    print("Reminder: undefined-risk structures are out of scope by decision. A "
          "low-excursion\nresult is a case for a DEFINED-RISK wide condor "
          "(width is the sizing dial), never\nfor a naked short.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
