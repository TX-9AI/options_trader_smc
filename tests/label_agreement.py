#!/usr/bin/env python3
"""
tests/label_agreement.py — v1.1 — 2026-08-07

RGM.1 GATE: IS THE STEADIER LABEL THE *RIGHT* LABEL? Everything measured so far
says the emission fix makes the label STABLE (17.6 -> 3.3 switches/symbol-day).
Stability is necessary and not sufficient — a law that emitted one regime all
day would score zero switches and be worthless. This tool is the independent
check, and it is the gate on the Aug 10 deploy.

THE GROUND TRUTH IS INDEPENDENT BY CONSTRUCTION. `day_trader_pro/auto_label.py`
labels a symbol-day from PRICE ACTION ONLY — body fraction and close position
for TREND, last-hour range fraction for PIN, prior-session extremes for
SWEEP/BREAKOUT. It has never seen a confluence score, a conviction value or a
regime label, so it cannot agree with the engine by construction. Output lands
in `~/day_trader_pro/reports/session_labels.jsonl`, one row per DATE carrying
per-symbol tag lists.

THE PRE-REGISTERED HYPOTHESIS, stated before the numbers are read so it cannot
be adjusted afterwards:

    H1  On symbol-days auto_label tagged TREND, the protected law spends a
        HIGHER share of ticks in TRENDING_BULL/TRENDING_BEAR than the current
        law, and its MODAL label agrees with the tag more often.
    H0  Agreement is unchanged (the fix only removes flicker) or falls (the fix
        buys stability by locking in whichever label happened to be held).

    A FALL IN AGREEMENT KILLS THE DEPLOY. That is the whole reason this runs
    before Monday and not after.

WHAT A TAG DOES AND DOES NOT CLAIM. The tags are WHOLE-SESSION characterisations,
so they are coarse: a TREND day that trends for two hours and chops for four is
still tagged TREND, and no per-tick truth exists anywhere. This measures the
DOMINANT read of a session, not moment-to-moment accuracy. An untagged symbol
carries NO positive claim and is excluded from agreement rather than counted as
RANGING — absence of a tag is not evidence of a range.

TAG -> EXPECTED REGIME FAMILY (from auto_label's own docstring):
    TREND     -> TRENDING_BULL / TRENDING_BEAR
    PIN       -> COMPRESSION            (coiled into the close)
    BREAKOUT  -> BREAKOUT_VOLATILE      (broke the prior extreme and held)
    SWEEP     -> SWEEP_REVERSAL         (breached the prior extreme, closed back inside)

Read-only, stdlib only, streams one file at a time, always exits 0.
USAGE
    python3 tests/label_agreement.py
    python3 tests/label_agreement.py --since 2026-07-20

CHANGELOG
  v1.1 — 2026-08-07 — EACH TAG SCORED OVER ITS OWN TIMEFRAME. v1.0 compared
         every tag against the SESSION-MODAL label, but only TREND is a
         whole-session characterisation. PIN is a LAST-HOUR property, so a day
         that trends then coils into the close was scored as a miss. BREAKOUT
         and SWEEP are SINGLE-EVENT tags and are now reported as NOT SCORED
         rather than given a number — scoring them needs a breach timestamp that
         session_labels.jsonl does not carry, and a wrong number is worse than
         none. The v1.0 PIN 8.9% / BREAKOUT 2.8% / SWEEP 0.0% figures were MY
         tool asking the wrong question, and they were quoted once before that
         was caught.
  v1.0 — 2026-08-06 — first issue, as the acceptance gate for the F7 emission
         fix. Built BEFORE the fix was proposed for deploy, so the criterion
         could not be chosen to suit the result.
"""

import argparse
import collections
import glob
import json
import os
import re
import sys

REPLAY_GLOB = "~/day_trader_pro/reports/regime_replay_*.jsonl"
LABELS_PATH = "~/day_trader_pro/reports/session_labels.jsonl"
DATE_RE = re.compile(r"regime_replay_(20\d\d-\d\d-\d\d)\.jsonl$")

THETA_COMMIT, THETA_HOLD, DELTA_DISPLACE = 0.65, 0.45, 0.12
TIEBREAK = {r: i for i, r in enumerate((
    "SWEEP_REVERSAL", "BREAKOUT_VOLATILE", "COMPRESSION",
    "TRENDING_BULL", "TRENDING_BEAR", "RANGING"))}

EXPECTED = {
    "TREND":    {"TRENDING_BULL", "TRENDING_BEAR"},
    "PIN":      {"COMPRESSION"},
    "BREAKOUT": {"BREAKOUT_VOLATILE"},
    "SWEEP":    {"SWEEP_REVERSAL"},
}

# ── v1.1 — EACH TAG IS SCORED OVER ITS OWN TIMEFRAME ──────────────────────────
# v1.0 compared every tag against the SESSION-MODAL label, and only TREND is a
# genuine whole-session characterisation. That mismatch produced PIN 8.9% /
# BREAKOUT 2.8% / SWEEP 0.0% — numbers that looked like engine blindness and
# were actually MY tool asking the wrong question. They were quoted once before
# the error was caught.
#   TREND     — auto_label: body fraction + close position over the WHOLE day.
#               Session-modal is the right comparison. UNCHANGED.
#   PIN       — auto_label: LAST-HOUR range fraction. A day that trends from the
#               open then coils into the close is correctly PIN, yet its session
#               modal should NOT be COMPRESSION. Scored over the last 60 min.
#   BREAKOUT  — SINGLE-EVENT tags (prior-session extreme breached / breached and
#   SWEEP       reclaimed). Scoring them needs the BREACH TIMESTAMP, which is not
#               in session_labels.jsonl and cannot be recovered from the replay
#               corpus without the prior session's extremes. **NOT SCORED** —
#               reported as unscoreable rather than given a number that is not
#               evidence. Printing a wrong number is worse than printing none.
WINDOW = {"TREND": None, "PIN": 60}          # None = whole session, int = last N min
UNSCOREABLE = ("BREAKOUT", "SWEEP")


def _top(cv):
    return min(cv.items(), key=lambda kv: (-kv[1], TIEBREAK.get(kv[0], 99)))


def emit(cv, inc, armed, protect):
    """One tick of an emission law. Mirrors conviction_integrator v2.1."""
    top_r, top_c = _top(cv)
    if top_c >= THETA_COMMIT:
        armed = True
    if inc is None:
        return top_r, armed
    inc_c = cv.get(inc, 0.0)
    if inc_c >= THETA_HOLD or (protect and armed):
        if (top_r != inc and top_c >= THETA_COMMIT
                and top_c >= inc_c + DELTA_DISPLACE):
            return top_r, armed
        return inc, armed
    return top_r, armed


def load_tags(path):
    """date -> {symbol: set(tags)}. Later rows win (a human override via
    label_day.sh appends the same shape and must supersede the auto row)."""
    out = {}
    p = os.path.expanduser(path)
    if not os.path.isfile(p):
        return out
    for line in open(p, errors="ignore"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:                                        # noqa: BLE001
            continue
        d = r.get("date")
        if not d:
            continue
        per = {}
        for tag in EXPECTED:
            for sym in (r.get(tag) or []):
                per.setdefault(sym, set()).add(tag)
        out[d] = per
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default=REPLAY_GLOB)
    ap.add_argument("--labels", default=LABELS_PATH)
    ap.add_argument("--since", default="")
    a = ap.parse_args(argv[1:])

    tags = load_tags(a.labels)
    if not tags:
        print(f"no session labels at {a.labels} — run day_trader_pro/auto_label.py")
        print("first. Without independent ground truth this gate cannot run, and")
        print("a stability number alone must NOT be read as a correctness result.")
        return 0

    paths = [p for p in sorted(glob.glob(os.path.expanduser(a.glob)))
             if DATE_RE.search(p)
             and (not a.since or DATE_RE.search(p).group(1) >= a.since)]
    if not paths:
        print(f"no replay files matched {a.glob}")
        return 0

    # per law: tag -> [modal-hits, n, summed in-family tick share]
    agree = {law: collections.defaultdict(lambda: [0, 0, 0.0, 0])
             for law in ("current", "protected")}
    untagged = matched = 0

    for path in paths:
        date = DATE_RE.search(path).group(1)
        day_tags = tags.get(date)
        if not day_tags:
            continue
        st = {}
        for line in open(path, errors="ignore"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:                                    # noqa: BLE001
                continue
            cv = ((r.get("l2") or {}).get("cv")) or {}
            if not cv:
                continue
            sym = r.get("sym", "?")
            s = st.setdefault(sym, {"current": [None, False, []],
                                    "protected": [None, False, []]})
            ts = r.get("ts") or ""
            for law, protect in (("current", False), ("protected", True)):
                inc, armed, seq = s[law]
                inc, armed = emit(cv, inc, armed, protect)
                seq.append((ts, inc))          # v1.1 — keep TIME, not just counts
                s[law] = [inc, armed, seq]

        for sym, s in st.items():
            t = day_tags.get(sym)
            if not t:
                untagged += 1
                continue
            matched += 1
            for law in ("current", "protected"):
                seq = s[law][2]
                for tag in t:
                    if tag in UNSCOREABLE:
                        agree[law][tag][3] += 1     # counted, never rated
                        continue
                    win = WINDOW.get(tag)
                    sub = seq if win is None else seq[-win:]
                    if not sub:
                        continue
                    ctr = collections.Counter(lbl for _ts, lbl in sub)
                    total = sum(ctr.values()) or 1
                    modal = ctr.most_common(1)[0][0]
                    fam = EXPECTED[tag]
                    cell = agree[law][tag]
                    cell[0] += 1 if modal in fam else 0
                    cell[1] += 1
                    cell[2] += sum(ctr[k] for k in fam) / total

    print(f"replay files: {len(paths)}   labelled dates: {len(tags)}")
    print(f"symbol-days matched to a tag: {matched}   untagged (excluded): "
          f"{untagged}")
    print()
    print("H1: the protected law should agree MORE. A FALL KILLS THE DEPLOY.")
    print()
    print(f"  {'tag':<10}{'n':>5}{'modal current':>16}{'modal protected':>18}"
          f"{'in-fam cur':>13}{'in-fam prot':>13}")
    for tag in ("TREND", "PIN", "BREAKOUT", "SWEEP"):
        c, p_ = agree["current"][tag], agree["protected"][tag]
        n = c[1]
        if tag in UNSCOREABLE:
            print(f"  {tag:<10}{c[3]:>5}   NOT SCORED — single-event tag; needs a "
                  f"breach timestamp")
            continue
        if not n:
            print(f"  {tag:<10}{0:>5}   (no labelled symbol-days)")
            continue
        print(f"  {tag:<10}{n:>5}{100.0*c[0]/n:>15.1f}%{100.0*p_[0]/n:>17.1f}%"
              f"{100.0*c[2]/n:>12.1f}%{100.0*p_[2]/n:>12.1f}%")
    print()
    print("  'modal' = the label held on the most ticks of that symbol-day.")
    print("  'in-fam' = mean share of the session's ticks spent in the tag's")
    print("  expected regime family. Modal is the headline; in-family is the")
    print("  same claim without the winner-take-all rounding.")
    print()
    print("  v1.1: each tag is scored over ITS OWN timeframe — TREND over the")
    print("  whole session, PIN over the LAST HOUR (that is what auto_label")
    print("  measures). BREAKOUT and SWEEP are single-EVENT tags and are NOT")
    print("  scored at all: without a breach timestamp any number here would be")
    print("  the wrong question asked confidently, which is what v1.0 did.")
    print("  Still a DOMINANT-read measure inside each window, not per-tick")
    print("  accuracy — no per-tick truth exists anywhere.")
    print("  Untagged symbol-days are EXCLUDED, not scored as RANGING: absence")
    print("  of a tag is not evidence of a range.")
    return 0


if __name__ == "__main__":
    try:
        rc = main(sys.argv)
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        rc = 0
    sys.exit(rc)
