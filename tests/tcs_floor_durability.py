#!/usr/bin/env python3
"""
tests/tcs_floor_durability.py — v1.3 — 2026-08-04   (backlog TC.4b prerequisite)

v1.3 — 2026-08-04 — `--control matched`, BECAUSE 62% MEANS NOTHING WITHOUT ONE.
        In a trending tape a recent intraday low "holds" terminally a great deal
        of the time simply because trends trend. Every number this tool printed
        before v1.3 was an absolute rate with nothing to compare it against.
        FIRST I TRIED THE OBVIOUS CONTROL AND IT DOES NOT EXIST. The plan was to
        measure ranging-tape floors against trending ones. It cannot be done from
        this journal: `_trend_credit_spread` sets `direction = ""` on any
        non-TRENDING label, `_impulse_sd` is then never called, and `floor_px` is
        None. **There is no ranging floor recorded anywhere.** Stating that
        rather than quietly substituting a different comparison, because a
        control that answers a different question is worse than none.
        WHAT `--control matched` DOES INSTEAD, and it is a stronger test. For
        every real impulse it draws a MATCHED pseudo-impulse on the SAME
        symbol-day: same construction (the low/high of a bar, same lookback),
        same direction, same minimum forward window, at a random earlier minute.
        Then it runs the identical terminal measurement on both. That asks the
        question the strategy actually rests on — **does the IMPULSE origin
        survive better than an ARBITRARY recent extreme?** — holding day, symbol,
        direction and session position roughly constant.
        Seeded (`--seed`) so a run is reproducible; a control that moves between
        runs cannot be argued with.

v1.2 — 2026-08-04 — TERMINAL OUTCOME + THE STRIKE-DISTANCE CURVE, because v1.1
        answered a question the trade does not ask. "Did a 1m close EVER go back
        through the floor before the bell?" is an INTRADAY VIOLATION rate. A
        defined-risk 0DTE spread does not lose when the level is touched; it
        loses on WHERE PRICE SITS AT THE BELL. A floor breached at 10:04 and
        reclaimed by 15:00 expires fine, and v1.1 counted it as a failure.
        So v1.2 reports BOTH and never merges them:
          - INTRADAY (v1.1's number) — how often the level was violated at all.
            Still the honest test of the premise AS STATED, and still the number
            that says whether the impulse origin is respected.
          - TERMINAL — the close nearest 15:45 relative to the floor. This is the
            one that maps to money.
          - RECOVERY — violated intraday, fine at the bell. The gap between the
            two rates IS the answer to "is the premise wrong, or is the strike
            just too close?"
          - THE STRIKE CURVE — terminal failure rate as a function of distance
            BEYOND the floor. That curve is the short-strike selector: it says
            how far OTM the spread has to sit for terminal failure to reach a
            tolerance you choose, priced from the state's own behaviour rather
            than from a delta.
        No new collection: same journal, same tape, same join.

v1.1 — 2026-08-04 — `--machine ARMED` (and `--min-r`), BECAUSE v1.0's FIRST RUN
        MEASURED THE WRONG POPULATION. It scored every floor the track ever
        computed — the impulse lookback rolls on EVERY tick, so most of those
        floors belong to moments when readiness was DORMANT and the strategy
        would never have sold anything. 5,129 "impulses" is the count of
        distinct floors observed, not of setups. The durability of a floor the
        trade would never have used answers no question anyone asked. The
        journal already carries `machine` (DORMANT / STAGING / ARMED) and `r`,
        so the filter costs nothing and the default is now ARMED.
        v1.0's numbers are SUPERSEDED, not merely refined: they are a different
        population and must not be compared to a filtered run.

DOES THE IMPULSE FLOOR HOLD? That is the entire premise of the trend credit
spread — sell a spread BEYOND the impulse candle, on the claim that committed
order flow will not fully retrace it. No engine exists yet, deliberately: TC.4b
says this table runs FIRST, because if the floor does not hold the strategy is
wrong and the firing engine is wasted work.

WHAT IT ASKS, per armed impulse:
    the readiness track recorded floor_px at time T.
    Between T and the session close, did a 1-MINUTE CLOSE go back through it?

CLOSE, not wick, and that is a real choice rather than a convenience. A short
strike is not taken out by a touch; it is threatened by acceptance beyond the
level. The wick statistic is reported ALONGSIDE (max penetration in ATR-free
percent) because it is what a stop would have felt, but the headline durability
number is close-based. Both are printed so the two are never conflated.

WHAT IT OUTPUTS, and each line answers a different open question:
  1. DURABILITY BY SD BUCKET — survival rate per impulse-magnitude tier. This IS
     the fit for TR_TCS_IMPULSE_SD_LO/HI: the bound belongs where durability
     starts clearing, not where a prior guessed. Feeds TC.4b (Aug 8-9).
  2. PENETRATION DISTRIBUTION — how far past the floor price actually traded on
     the failures. p90 is a STRIKE-DISTANCE rule priced from the state's own
     behaviour, the same argument AQ made for the condor on a strategy that
     wants it.
  3. TIME-TO-FAILURE — a floor that breaks at 15:55 is a different animal from
     one that breaks in four minutes, and only the second invalidates the trade.

DISCIPLINE, inherited rather than reinvented:
  - Cells under MIN_N are REFUSED, never read (a2_partition's rule).
  - The minimum detectable effect is printed, so an underpowered cell is never
    mistaken for a null (gap_outcome_join's lesson).
  - This is NOT a backtest and NOT a P&L claim. No spread is priced, no credit
    is assumed, no fill is modelled. It reports what the underlying did after a
    state the fleet already records.

Read-only. stdlib only. Runs on control, needs no boxes.

USAGE
    python3 tests/tcs_floor_durability.py
    python3 tests/tcs_floor_durability.py --since 2026-07-28 --min-sd 1.0
    python3 tests/tcs_floor_durability.py --diagnose     # why rows did not join
"""

import argparse
import collections
import random
import csv
import glob
import json
import math
import os
import re
import sys

JOURNAL_GLOB = "~/day_trader_pro/signal_journal/*/*.jsonl"
OHLC_ROOT = "~/day_trader_pro/ohlc"
DATE_RE = re.compile(r"(20\d\d-\d\d-\d\d)")

# The track only started emitting on this date; earlier rows cannot exist and a
# wider window would silently look like missing data rather than absent history.
TRACK_START = "2026-07-28"

# Same floor as gap_outcome_join, same reason: the samples are what they are, and
# a cell below this is refused rather than read.
MIN_N = 30

# Operator's magnitude tiers (aware / established / screaming). Edges are the
# CURRENT priors — this tool exists partly to say whether they are the right
# ones, so they are printed as priors and never treated as settled.
SD_BUCKETS = [(0.0, 1.5, "sub-aware  <1.5"),
              (1.5, 2.0, "aware      1.5-2.0"),
              (2.0, 2.5, "establish  2.0-2.5"),
              (2.5, 99.0, "screaming  >=2.5")]


def _bucket(sd):
    for lo, hi, name in SD_BUCKETS:
        if lo <= sd < hi:
            return name
    return None


def _pct(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    return s[min(int(q * len(s)), len(s) - 1)]


def _load_tape(date, root):
    """{SYM: [(hhmm, close, high, low)]} for one session, in file order."""
    day_dir = os.path.join(os.path.expanduser(root), date)
    out = {}
    if not os.path.isdir(day_dir):
        return out
    for f in os.listdir(day_dir):
        if "_ohlc_" not in f.lower() or not f.lower().endswith(".csv"):
            continue
        sym = f.split("_ohlc_")[0].upper()
        rows = []
        try:
            with open(os.path.join(day_dir, f)) as fh:
                for r in csv.DictReader(fh):
                    ts = (r.get("timestamp") or r.get("time") or r.get("date")
                          or r.get("datetime") or "")
                    m = re.search(r"(\d\d):(\d\d)", str(ts))
                    if not m:
                        continue
                    try:
                        rows.append((int(m.group(1)) * 60 + int(m.group(2)),
                                     float(r["close"]), float(r["high"]),
                                     float(r["low"])))
                    except Exception:                            # noqa: BLE001
                        continue
        except Exception:                                        # noqa: BLE001
            continue
        if rows:
            out[sym] = sorted(rows)
    return out


def _minutes(ts_et):
    m = re.search(r"T(\d\d):(\d\d)", str(ts_et))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", default=JOURNAL_GLOB)
    ap.add_argument("--ohlc", default=OHLC_ROOT)
    ap.add_argument("--since", default=TRACK_START)
    ap.add_argument("--until", default="9999-12-31")
    ap.add_argument("--min-sd", type=float, default=0.0,
                    help="ignore impulses below this SD ratio")
    ap.add_argument("--machine", default="ARMED",
                    choices=("ARMED", "STAGING+", "ANY"),
                    help="which readiness state the floor must have been in. "
                         "ARMED (default) is the only population the strategy "
                         "would have traded; ANY reproduces v1.0 and is kept "
                         "only so the difference can be shown, not used.")
    ap.add_argument("--min-r", type=float, default=0.0,
                    help="additionally require readiness r >= this")
    ap.add_argument("--control", default="none", choices=("none", "matched"),
                    help="matched: for every real impulse, draw a pseudo-impulse "
                         "at a random earlier minute on the SAME symbol-day, same "
                         "direction and construction, and report both. Without it "
                         "every rate here is an absolute with nothing to beat.")
    ap.add_argument("--seed", type=int, default=20260804,
                    help="control draw seed; a control that moves between runs "
                         "cannot be argued with")
    ap.add_argument("--diagnose", action="store_true")
    a = ap.parse_args(argv[1:])

    paths = sorted(glob.glob(os.path.expanduser(a.journal)))
    if not paths:
        print(f"No journal files under {a.journal} — nothing harvested yet.")
        return 2

    # One observation per (date, symbol, floor_px, direction): the track scores
    # every tick, so the SAME impulse appears on hundreds of consecutive rows.
    # Counting them all would weight a long-lived impulse hundreds of times and
    # report a sample size that does not exist. Dedup on the floor itself.
    seen = set()
    obs = []
    tapes = {}
    stats = collections.Counter()

    for p in paths:
        m = DATE_RE.search(p)
        if not m:
            continue
        date = m.group(1)
        if not (a.since <= date <= a.until):
            continue
        sym_hint = os.path.basename(p).split(".")[0].split("_")[0].upper()
        try:
            fh = open(p)
        except Exception:                                        # noqa: BLE001
            continue
        with fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:                                # noqa: BLE001
                    continue
                rd = r.get("readiness") or {}
                if rd.get("strategy") != "trend_credit_spread":
                    continue
                stats["tcs_rows"] += 1
                f = rd.get("factors") or {}
                floor = f.get("floor_px")
                direction = f.get("dir") or ""
                sd = f.get("sd_ratio")
                if floor is None or direction not in ("long", "short"):
                    stats["no_floor"] += 1
                    continue
                if sd is None or float(sd) < a.min_sd:
                    stats["below_min_sd"] += 1
                    continue
                # v1.1 — THE POPULATION FILTER. A floor computed while the track
                # was DORMANT is not a setup; it is the rolling lookback doing
                # arithmetic. Measuring its durability answers nothing.
                mach = str(rd.get("machine") or "")
                if a.machine == "ARMED" and mach != "ARMED":
                    stats["not_armed"] += 1
                    continue
                if a.machine == "STAGING+" and mach not in ("ARMED", "STAGING"):
                    stats["not_armed"] += 1
                    continue
                try:
                    rr = float(rd.get("r") or 0.0)
                except Exception:                            # noqa: BLE001
                    rr = 0.0
                if rr < a.min_r:
                    stats["below_min_r"] += 1
                    continue
                key = (date, sym_hint, round(float(floor), 2), direction)
                if key in seen:
                    stats["dedup"] += 1
                    continue
                seen.add(key)
                t0 = _minutes(r.get("ts_et"))
                if t0 is None:
                    stats["no_ts"] += 1
                    continue
                obs.append({"date": date, "sym": sym_hint, "floor": float(floor),
                            "dir": direction, "sd": float(sd), "t0": t0})

    # ── join each impulse forward against its own session's tape ────────────
    results = []
    for o in obs:
        tape = tapes.get(o["date"])
        if tape is None:
            tape = tapes[o["date"]] = _load_tape(o["date"], a.ohlc)
        bars = tape.get(o["sym"])
        if not bars:
            stats["no_tape"] += 1
            continue
        fwd = [b for b in bars if b[0] > o["t0"]]
        if len(fwd) < 5:
            # Not a failure and not a hold — an impulse armed at 15:57 has no
            # forward window, and scoring it either way would be a lie.
            stats["no_forward_window"] += 1
            continue
        stats["joined"] += 1

        floor, long_ = o["floor"], o["dir"] == "long"
        broke_at, pen = None, 0.0
        for tm, c, h, lo in fwd:
            through = (c < floor) if long_ else (c > floor)
            if through and broke_at is None:
                broke_at = tm - o["t0"]
            depth = (floor - lo) if long_ else (h - floor)
            if depth > 0 and floor > 0:
                pen = max(pen, 100.0 * depth / floor)
        # v1.2 — TERMINAL: the close nearest the bell. `fwd` is sorted, so the
        # last bar is the session's final print for this symbol. A short session
        # (early close, truncated tape) ends where it ends — that is honest, and
        # the bar count is reported so a thin day is visible rather than assumed.
        term_close = fwd[-1][1]
        term_failed = (term_close < floor) if long_ else (term_close > floor)
        results.append({**o, "held": broke_at is None,
                        "mins_to_break": broke_at, "wick_pen_pct": pen,
                        "term_close": term_close, "term_failed": term_failed,
                        "fwd_bars": len(fwd)})

    # ── v1.3 — the matched control ──────────────────────────────────────────
    control = []
    if a.control == "matched" and results:
        rng = random.Random(a.seed)
        for o in results:
            bars = tapes.get(o["date"], {}).get(o["sym"]) or []
            # candidate anchors: any bar with the same minimum forward window the
            # real observation needed, so the two are compared on equal footing
            elig = [i for i in range(len(bars)) if len(bars) - i - 1 >= 5]
            if not elig:
                continue
            i = rng.choice(elig)
            tm, c, h, lo = bars[i]
            long_ = o["dir"] == "long"
            floor = lo if long_ else h
            fwd = bars[i + 1:]
            if len(fwd) < 5 or floor <= 0:
                continue
            broke_at, pen = None, 0.0
            for tm2, c2, h2, lo2 in fwd:
                through = (c2 < floor) if long_ else (c2 > floor)
                if through and broke_at is None:
                    broke_at = tm2 - tm
                depth = (floor - lo2) if long_ else (h2 - floor)
                if depth > 0:
                    pen = max(pen, 100.0 * depth / floor)
            term_close = fwd[-1][1]
            control.append({"dir": o["dir"], "floor": floor,
                            "held": broke_at is None,
                            "term_close": term_close,
                            "term_failed": (term_close < floor) if long_
                                           else (term_close > floor),
                            "wick_pen_pct": pen})

    if a.diagnose or not results:
        print("READINESS ROWS / JOIN DIAGNOSIS")
        for k in ("tcs_rows", "not_armed", "below_min_r", "dedup", "no_floor",
                  "below_min_sd", "no_ts", "no_tape", "no_forward_window",
                  "joined"):
            print(f"  {k:<20} {stats[k]}")
        print(f"  distinct impulses  {len(obs)}")
        if not results:
            print("\nNothing joined. `no_tape` dominating means the journal and "
                  "the OHLC\nroots disagree on symbol or date; `tcs_rows` at 0 "
                  "means the track\nnever emitted in this window.")
            return 2
        if a.diagnose:
            return 0

    held = [r for r in results if r["held"]]
    term_ok = [r for r in results if not r["term_failed"]]
    recovered = [r for r in results if not r["held"] and not r["term_failed"]]
    print(f"window        : {a.since} .. {a.until}")
    print(f"population    : machine={a.machine}"
          + (f"  min_r={a.min_r}" if a.min_r else "")
          + ("   <-- ARMED only: the floors the strategy would actually have "
             "sold beyond" if a.machine == "ARMED" else
             "   <-- NOT the traded population; every floor the lookback ever "
             "computed"))
    print(f"impulses      : {len(results)} distinct (deduped from "
          f"{stats['tcs_rows']} scored rows)")
    print(f"floor HELD    : {len(held)} ({100.0 * len(held) / len(results):.1f}%)"
          f"   — no 1m CLOSE back through the impulse origin before the bell")
    print(f"terminal OK   : {len(term_ok)} "
          f"({100.0 * len(term_ok) / len(results):.1f}%)"
          f"   — price CLOSED on the safe side of the floor at the bell")
    print(f"recovered     : {len(recovered)} "
          f"({100.0 * len(recovered) / len(results):.1f}%)"
          f"   — violated intraday, fine at the bell")
    print("definition    : CLOSE-based. A short strike is threatened by "
          "ACCEPTANCE beyond\n                a level, not by a touch; the wick "
          "statistic is reported separately.")
    print("READ THE TWO RATES TOGETHER. Intraday is the premise AS STATED — is "
          "the\n                impulse origin respected at all. Terminal is "
          "what a defined-risk 0DTE\n                spread actually pays on. A "
          "large gap between them does not rescue the\n                premise; "
          "it relocates the question to STRIKE DISTANCE, which the curve\n"
          "                below answers.\n")

    # ── 1. durability by SD bucket — this is the ramp fit ───────────────────
    print("=" * 66)
    print("DURABILITY BY IMPULSE MAGNITUDE  (the TR_TCS_IMPULSE_SD_* fit)")
    print("=" * 66)
    by_b = collections.defaultdict(list)
    for r in results:
        b = _bucket(r["sd"])
        if b:
            by_b[b].append(r)
    for _, _, name in SD_BUCKETS:
        rs = by_b.get(name, [])
        if len(rs) < MIN_N:
            print(f"  {name:<22} n={len(rs):<4} REFUSED (under n={MIN_N})")
            continue
        h = sum(1 for r in rs if r["held"])
        t = sum(1 for r in rs if not r["term_failed"])
        rate = h / len(rs)
        hw = 1.96 * math.sqrt(rate * (1 - rate) / len(rs))
        trate = t / len(rs)
        thw = 1.96 * math.sqrt(trate * (1 - trate) / len(rs))
        print(f"  {name:<22} n={len(rs):<4} intraday {rate:.0%} ±{hw:.0%}"
              f"   terminal {trate:.0%} ±{thw:.0%}")
    print("\n  ⚠ ON THE ARMED POPULATION THIS CURVE MAY NOT BE FITTABLE. Arming")
    print("  already REQUIRES magnitude, so the low-SD buckets are near-empty by")
    print("  construction and there is no variance to fit a ramp against. Run")
    print("  --machine STAGING+ for the population that still has low-SD mass.")
    print("\n  Bucket EDGES are the current PRIORS, not a result. If durability")
    print("  rises monotonically across them the tiers are real; if it is flat,")
    print("  impulse magnitude is not what protects the floor and the ramp is")
    print("  measuring nothing.")

    # ── 2. how far past the floor, on the failures ──────────────────────────
    print("\n" + "=" * 66)
    print("PENETRATION ON FAILURES  (a strike-distance rule, in % of floor)")
    print("=" * 66)
    fails = [r for r in results if not r["held"]]
    if len(fails) < MIN_N:
        print(f"  n={len(fails)} REFUSED (under n={MIN_N})")
    else:
        pens = [r["wick_pen_pct"] for r in fails]
        print(f"  n={len(fails)}   p50 {_pct(pens, .50):.3f}%   "
              f"p90 {_pct(pens, .90):.3f}%   p95 {_pct(pens, .95):.3f}%   "
              f"max {max(pens):.3f}%")
        print("\n  p90 is the distance a short strike would have had to sit "
              "beyond the\n  floor to survive nine failures in ten — priced from "
              "the state's own\n  behaviour rather than from a fixed delta.")

    # ── 3. time to failure ──────────────────────────────────────────────────
    print("\n" + "=" * 66)
    print("TIME TO FAILURE  (minutes from the impulse to the first close through)")
    print("=" * 66)
    mins = [r["mins_to_break"] for r in fails if r["mins_to_break"] is not None]
    if len(mins) < MIN_N:
        print(f"  n={len(mins)} REFUSED (under n={MIN_N})")
    else:
        print(f"  n={len(mins)}   p10 {_pct(mins, .10)}   p50 {_pct(mins, .50)}"
              f"   p90 {_pct(mins, .90)}   max {max(mins)}")
        print("\n  A floor that fails late is a 0DTE that ran out of clock, not "
              "a thesis\n  that was wrong. A p50 in single-digit minutes would "
              "say the opposite.")

    if control:
        c_term = sum(1 for r in control if not r["term_failed"])
        c_held = sum(1 for r in control if r["held"])
        n_c = len(control)
        print("\n" + "=" * 66)
        print("MATCHED CONTROL — an ARBITRARY recent extreme, same symbol-day")
        print("=" * 66)
        print(f"  n={n_c}   intraday held {c_held / n_c:.1%}"
              f"   terminal OK {c_term / n_c:.1%}")
        d_t = len(term_ok) / len(results) - c_term / n_c
        # two-proportion band; if the difference does not clear it, the impulse
        # is not doing anything the tape was not doing anyway.
        p1, p2 = len(term_ok) / len(results), c_term / n_c
        se = math.sqrt(p1 * (1 - p1) / len(results) + p2 * (1 - p2) / n_c)
        print(f"  impulse minus control, TERMINAL: {d_t:+.1%}  ±{1.96 * se:.1%}")
        print("\n  THIS IS THE NUMBER THE STRATEGY LIVES ON. If the impulse")
        print("  origin does not survive better than an arbitrary recent extreme")
        print("  on the same tape, the state is not selecting anything and the")
        print("  absolute rate above is a fact about trending tape, not a signal.")

    # ── v1.2 — THE STRIKE CURVE: terminal failure vs distance beyond the floor
    # This is the output that becomes a rule. Each row asks: if the short strike
    # had been placed this far BEYOND the impulse floor, how often would price
    # have closed through it at the bell? Read down until the rate reaches a
    # tolerance you are willing to state in advance.
    print("\n" + "=" * 66)
    print("STRIKE CURVE — terminal failure vs distance BEYOND the floor")
    print("=" * 66)
    print(f"  {'offset':<10}{'terminal failures':>20}{'rate':>10}"
          + ("      control" if control else ""))
    def _fail_at(rows, off):
        bad = 0
        for r in rows:
            f0 = r["floor"]
            strike = f0 * (1 - off / 100.0) if r["dir"] == "long" \
                else f0 * (1 + off / 100.0)
            through = (r["term_close"] < strike) if r["dir"] == "long" \
                else (r["term_close"] > strike)
            bad += 1 if through else 0
        return bad

    for off in (0.0, 0.25, 0.50, 0.75, 1.00, 1.50, 2.00, 3.00):
        bad = _fail_at(results, off)
        line = f"  {off:>5.2f}%    {bad:>18}{bad / len(results):>10.1%}"
        if control:
            cb = _fail_at(control, off)
            line += f"      control {cb / len(control):>6.1%}"
        print(line)
    print("\n  The offset where this crosses your tolerance IS the short-strike")
    print("  rule — priced from the state's own behaviour rather than a fixed")
    print("  delta. NOTE WHAT IT IS NOT: further OTM collects less credit, and")
    print("  this table prices no credit at all. It bounds RISK, and the credit")
    print("  side of that trade-off is a separate measurement.")

    # ── power ───────────────────────────────────────────────────────────────
    n = len(results)
    if n > 2:
        p = len(held) / n
        biggest = max((len(v) for v in by_b.values()), default=0)
        if biggest > 1:
            mde = (1.96 + 0.84) * math.sqrt(2 * p * (1 - p) / biggest)
            print(f"\n  POWER: largest bucket n={biggest}. Smallest difference in "
                  f"hold-rate\n  detectable at 95%/80% between two such buckets: "
                  f"{mde:.0%}. A gap smaller\n  than that is UNDERPOWERED, not a "
                  f"null.")

    print("\n" + "=" * 66)
    print("WHAT THIS DOES AND DOES NOT ESTABLISH")
    print("=" * 66)
    print("  ESTABLISHES: whether the underlying respects the impulse origin,")
    print("  and at what magnitude — which is the strategy's whole premise and")
    print("  the empirical basis for its SD ramp and its strike distance.")
    print("  DOES NOT: price a spread, assume a credit, model a fill, or claim")
    print("  a P&L. A held floor is a necessary condition for the trade, not a")
    print("  profitable one. The firing engine stays gated where TC.4 puts it.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
