#!/usr/bin/env python3
"""
tests/gap_outcome_join.py — v1.5 — 2026-08-04

v1.5 — 2026-08-04 — --pool gapflat, WITH ITS OWN LEGITIMACY TEST ATTACHED.
         AV names collapsing the three-way split as the one lever that moves the
         answerable date: n per cell roughly triples, taking a 0.10 R read from
         ~2026-09-15 (after go-live) to inside the Aug 10-21 freeze window. It
         also says, correctly, that whether the pooling is LEGITIMATE is a
         judgement and not a given.
         So the flag does not just merge the columns. Cells stay keyed on the
         ORIGINAL class and the merge happens at print time, which makes the
         homogeneity check free: for every row it reports CONT vs REV with a
         band and states POOLABLE / NOT POOLABLE / UNDERPOWERED. Pooling two
         arms that disagree would manufacture a null out of two real and
         opposite effects — the one failure mode that makes a bigger n WORSE
         than a smaller one, and it would be invisible in the pooled table.
         A row marked NOT POOLABLE prints its pooled cell anyway, flagged, so
         the number is never silently withheld and never silently trusted.
v1.4 — 2026-08-02 — --metric r | winrate | pnl, BECAUSE pnl_usd IS UNDERPOWERED
       BY TWO ORDERS OF MAGNITUDE. The v1.3 clean-window run settled it: of 15
       cells only continuation cleared n=30, reporting CONT -12.3 ±90.1 and REV
       -1.4 ±100.5 — a band 7-8x the point estimate, which is not a weak result
       but NO measurement. (It also erased the condor CONT/REV split that looked
       like the one real signal at n=30/30 pooled; clean it is n=10/11, so it was
       an artifact of the confounded window exactly as HISTORY.md predicted.)
       BACKING sigma OUT OF THOSE BANDS gives ~$340 per trade. At 95% confidence
       and 80% power, n per cell to detect a mean difference:
           delta $200 -> n=  45   ~10 trading days
           delta $100 -> n= 181   ~38 trading days
           delta  $50 -> n= 725   ~153 trading days
           delta  $30 -> n=2014   ~424 trading days
       Detecting a $50/trade edge takes SEVEN MONTHS at the current rate. So the
       question is not "wait for more trades", it is "use a lower-variance
       statistic or accept the tick corpus is where the power lives" — the A2
       corpus resolved 0.05% differences on n=150,517 ticks, three orders of
       magnitude more than the 215 trades here.
       TWO CHEAPER STATISTICS, both added:
         --metric r        pnl_usd / max_loss. max_loss is on every trade row and
                           is the RISK MANAGER'S OWN number, not one reconstructed
                           here. Position size varies, so a large share of that
                           $340 sigma is SIZE rather than outcome; normalising by
                           risk removes it. This is the one most likely to make a
                           $100-equivalent effect visible inside the freeze window.
         --metric winrate  bounded [0,1], so variance is capped at 0.25 regardless
                           of trade size. It cannot tell you edge MAGNITUDE, only
                           whether gap class shifts the hit rate — but it answers
                           that far sooner than a mean ever will.
       The tool now prints the POWER LINE for whichever metric is selected, so an
       underpowered cell is labelled as such instead of being read as a null.
v1.3 — 2026-08-02 — --since / --until, AND A DEFAULT THAT REFUSES TO POOL ACROSS
       A DOCUMENTED CONFOUND. v1.2 fixed the join and the per-date column then
       showed the real problem: FOUR DAYS CARRY 73% OF ALL TRADES. 07-13 and
       07-14 have 225 each, 07-16/17 have 111/128, 07-31 has 116 — while the nine
       sessions 07-20..07-30 produced 134 COMBINED, about 15/day across 29 boxes.
       That is not one population and pooling pnl_usd across it is not analysis.
       WHAT ACTUALLY CHANGED, from docs/HISTORY.md — 2026-07-18 is "day zero on a
       materially changed engine":
         07-20  orb_engine v3.9 — the stale-retest timeout had been counting 15s
                loop ticks as bars and dying in ~3 minutes; fixed to real 1m bars,
                and expiry now RE-ARMS instead of terminating.
         07-21  main.py v4.0 — L2.5 live, the L1→L2 committed label now drives
                primary_regime. sweep_reversal v3.2 ORB-ownership gate.
         07-22  regime_confluence v1.2 ramp de-saturation AND, riding the same
                push, the MARK-LIMIT EXECUTION workstream — limit_ladder v1.2,
                entry_engine v3.8 mark-limit entries, mark-limit exit closes.
       And the volume cliff has a NAMED cause rather than being a mystery: the
       v2.5 row records that UNKNOWN's veto power was REMOVED FOR THE ORB —
       "Sample restored. The safety was removed before the replacement was built."
       Pre-07-20 volume was a deliberate un-gating, not a defect firing randomly.
       THE REPO ALREADY WARNED ABOUT THIS. HISTORY.md, on the 07-22 push:
       "label-gated regime metrics stay attributable to v1.2; P&L / FILL-DEPENDENT
       STATS ARE CONFOUNDED BY BOTH CHANGES. The ~2-week frozen-baseline window
       gets one week added to its back end to preserve a clean stretch."
       This tool reports pnl_usd, which is exactly a fill-dependent stat. So the
       DEFAULT is now --since 2026-07-23, the first session after mark-limit
       landed. Pooling the whole range requires --since 1970-01-01 and prints a
       warning, because it should be a deliberate act rather than the default.
       BE HONEST ABOUT WHAT THAT LEAVES: ~215 trades, 116 of them from 07-31
       alone. Over half the clean sample is ONE SESSION. Gap-conditioned P&L may
       simply not be answerable yet, and "not yet" is a legitimate answer.
v1.2 — 2026-08-02 — NORMALISE THE JOIN KEY. --diagnose immediately earned its
       keep: of the 450 unjoined, 225 were the first tape date (legitimate — no
       prior session to gap against) and 225 were ONE DATE, 2026-07-14, where the
       `box` field carries the SOURCE DB FILENAME (`AVGO_2026-07-14_TRADES.DB`)
       rather than the ticker. My join used `box` verbatim, so every trade that
       day missed. Recovering them is ~24% of the sample.
       `box` stays authoritative — consolidate_trades deliberately leaves the
       row's own `symbol` column untouched so a mislabeled db can be caught, so
       switching fields would discard that safeguard. The suffix is stripped
       instead.
v1.1 — 2026-08-02 — --diagnose. The first real run joined only 489 of 939 closed
       trades: 450 had NO GAP RECORD, which is ~48% of the sample discarded by an
       unknown selection rule. That is not a caveat, it is a hole — a cell drawn
       from half the trades with unknown bias tells you nothing. This flag says
       exactly which side is missing (date absent from the lookup vs symbol absent
       within a present date) and breaks it down by date and by symbol, so the
       cause is measured rather than guessed.
       Two priors worth checking against the output, both of which would be
       LEGITIMATE rather than defects: (a) the FIRST tape date has no prior
       session, so every symbol on it is a first-appearance skip by construction —
       gap_backfill reported 29 of those; (b) only a SUBSET of boxes wakes on a
       typical day, so a symbol that traded today but whose PRIOR session was
       never harvested has no gap to compute. If the 450 is mostly (b), the join
       is honest but the sample is structurally thin and that is the finding.

DOES GAP CLASS SEPARATE GOOD TRADING DAYS FROM BAD ONES? Joins already-banked
trade outcomes to the gap classification. No new collection, no waiting.

WHY THIS AND NOT THE A2 STATE ITSELF
    The clean-corpus A2 work (AQ, AR) killed most of what it set out to find:
    drift shows NO EDGE at any horizon or elapsed bucket, so paused_trend as a
    live drift factor is unsupported; the wrong-theta-sign hypothesis for
    continuation's -$2,024 is not supported; and the excursion difference is real
    but ~3% at p90, which does not move a condor's economics.

    What SURVIVED was something the A2 work was not looking for. From the clean
    partition grid:

                     OPEN         DECAY        CLEAN
        FLAT          3.60   →    13.78   →     3.55
        CONT          9.89   →     5.91   →     1.46
        REV           9.55   →     5.98   →     1.83

    **Gap class x time of day is a strong conditioning variable, and nothing in
    the fleet keys on it.** On a flat open the first 70 minutes are statistically
    indistinguishable from midday, then 10:40-12:00 runs ~4x hotter. On gap days
    the open is hot and decays monotonically. Two completely different day
    shapes, and every strategy currently treats them identically.

    So A2 was never the tradeable signal. It was the INSTRUMENT that made day type
    visible — a sensitive proxy for regime ambiguity that exposed a structure in
    the tape we had no other way to measure. That is a legitimate outcome for a
    diagnostic, and it is worth saying plainly rather than pretending the state
    itself pays.

THE SHARPEST TEST, and why ORB is first
    ORB forms its opening range 09:30-10:00 — PRECISELY the window that is dead
    on flat-open days and hot on gap days. Item **AH** has ORB at **-0.24R over
    252 trades** with no explanation offered. If that decomposes into something
    like "+0.3R on gap days, -0.8R on flat opens", it is a gate with a real
    sample behind it, no new collection, and it lands well before the freeze.
    The same split applies to the 362 condors and to continuation's
    handoff-vs-standalone problem.

WHAT THIS IS NOT
    It is not a backtest and it does not size, gate or recommend anything. It
    reports outcomes already realised, partitioned by a variable that was always
    computable and never computed. Any gate that follows needs its own
    pre-registered validation — this only says whether there is something there.

HONEST LIMITS, stated up front rather than discovered later
    - The fleet has been PAPER trading, so fills are simulated. A split that
      depends on fill quality will not show here.
    - Sample per cell will be small. 252 ORB trades over 15 sessions across 3 gap
      classes is ~84 per class BEFORE any strategy or grade split. The n>=30
      floor below is low for a mean-with-CI and cells are refused under it.
    - Gap class is assigned per (date, symbol), so every trade on a symbol-day
      inherits one class. That is correct — the gap is a property of the session,
      not of the trade — but it means cells are not independent samples.
    - pnl_usd is used, not R. Position sizes vary, so a big loser on one symbol
      can dominate a cell's net. Win rate and median are reported alongside the
      mean for exactly that reason.

USAGE (single line, control box, repo root)
    python3 tests/gap_outcome_join.py
    python3 tests/gap_outcome_join.py --by strategy
    python3 tests/gap_outcome_join.py --by strategy --window OPEN

Read-only. Reads reports/gap_pct.json and reports/fleet_trades_<date>.json.
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

DEFAULT_GAPS = "~/day_trader_pro/reports/gap_pct.json"
TRADES_GLOB = "~/day_trader_pro/reports/fleet_trades_*.json"
# v1.5 — the pooled view. CONT and REV are both GAP DAYS; FLAT is the other day
# shape. AV: "the ONE lever that moves the date is not waiting or re-slicing but
# NOT SPLITTING THREE WAYS" — n per cell roughly triples, which is what puts a
# 0.10 R read inside the freeze window instead of after go-live.
POOLED_CLASSES = ("GAP", "FLAT")
POOL_MAP = {"CONT": "GAP", "REV": "GAP", "FLAT": "FLAT"}
DATE_RE = re.compile(r"(20\d\d-\d\d-\d\d)")
CLASSES = ("CONT", "FLAT", "REV")

# Low, because the samples are what they are. A cell under this is REFUSED
# rather than read — the same discipline a2_partition uses at n>=500, scaled to
# trade counts instead of tick counts.
MIN_CELL_N = 30

# First session AFTER the mark-limit execution workstream landed (2026-07-22).
# Before this, fills came from a different execution path, so pnl_usd on either
# side is not the same measurement. HISTORY.md flags this explicitly.
CONFOUND_CUTOFF = "2026-07-23"

# Entry-time buckets, matching a2_partition's so the two can be read together.
BUCKETS = (("OPEN", "09:30", "10:40"),
           ("DECAY", "10:40", "12:00"),
           ("CLEAN", "12:00", "16:00"))


_DBNAME_RE = re.compile(r"_\d{4}-\d{2}-\d{2}_TRADES\.DB$", re.I)


def _symbol_of(t):
    """Ticker from a trade row.

    `box` is the authoritative tag (consolidate_trades stamps it from the source
    file and leaves the row's own `symbol` column untouched on purpose, so a
    mislabeled db stays detectable). But on some dates it carries the whole
    filename — `AVGO_2026-07-14_TRADES.DB` — so the suffix is stripped rather
    than falling back to `symbol`, which would throw the safeguard away.
    """
    raw = str(t.get("box") or t.get("symbol") or "?")
    raw = _DBNAME_RE.sub("", raw)
    if raw.lower().endswith(".db"):
        raw = raw[:-3]
    return raw.upper()


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _mean_ci(xs):
    n = len(xs)
    if n < 2:
        return (xs[0] if n else 0.0), 0.0, n
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return m, 1.96 * math.sqrt(var / n), n


def _median(xs):
    if not xs:
        return 0.0
    s = sorted(xs)
    return s[len(s) // 2]


def _entry_bucket(t):
    """Time bucket from whichever entry-time field the row carries. Returns None
    when no usable timestamp exists — those trades are counted and reported, not
    silently assigned to a bucket."""
    for key in ("entry_time", "entry_ts", "opened_at", "timestamp", "time"):
        v = t.get(key)
        if not v:
            continue
        m = re.search(r"(\d{2}):(\d{2})", str(v))
        if not m:
            continue
        hhmm = f"{m.group(1)}:{m.group(2)}"
        for name, lo, hi in BUCKETS:
            if lo <= hhmm < hi:
                return name
        return "OTHER"
    return None


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gaps", default=DEFAULT_GAPS)
    ap.add_argument("--by", default="strategy",
                    help="row dimension: strategy, setup_grade, regime, box")
    ap.add_argument("--since", default=CONFOUND_CUTOFF,
                    help=f"first date to include (default {CONFOUND_CUTOFF}, the "
                         f"session after mark-limit landed). Widening this pools "
                         f"pnl_usd across a documented execution change.")
    ap.add_argument("--until", default="9999-12-31",
                    help="last date to include")
    ap.add_argument("--metric", default="r", choices=("r", "winrate", "pnl"),
                    help="r = pnl_usd/max_loss (default; strips position size "
                         "from the variance). winrate = bounded hit rate. "
                         "pnl = raw dollars, underpowered — see the header.")
    ap.add_argument("--diagnose", action="store_true",
                    help="report WHY trades failed to join, by date and symbol")
    ap.add_argument("--pool", default="none", choices=("none", "gapflat"),
                    help="gapflat: collapse CONT+REV into GAP (n per cell "
                         "roughly triples). Prints a per-row CONT-vs-REV "
                         "homogeneity verdict so an illegitimate pool is "
                         "visible rather than averaged away.")
    ap.add_argument("--window", default="ALL",
                    help="restrict to an entry bucket: OPEN / DECAY / CLEAN / ALL")
    a = ap.parse_args(argv[1:])

    gaps_path = os.path.expanduser(a.gaps)
    if not os.path.isfile(gaps_path):
        print(f"No gap lookup at {gaps_path} — run tests/gap_backfill.py first.")
        return 2
    gaps = json.load(open(gaps_path)).get("sessions", {})

    paths = sorted(glob.glob(os.path.expanduser(TRADES_GLOB)))
    if not paths:
        print(f"No fleet_trades_*.json found under {TRADES_GLOB}")
        return 2

    # (row_key, gap_class) -> [pnl]
    cells = collections.defaultdict(list)
    totals = collections.Counter()
    no_gap_record = 0
    no_bucket = 0
    n_closed = 0
    in_window = 0
    # v1.1 diagnostics: split the miss by WHICH side is absent
    miss_date = collections.Counter()      # date not in the gap lookup at all
    miss_sym = collections.Counter()       # date present, symbol absent
    miss_class = collections.Counter()     # record present, class not CONT/FLAT/REV
    joined_by_date = collections.Counter()
    excluded_dates = {}
    no_denominator = 0

    for p in paths:
        m = DATE_RE.search(os.path.basename(p))
        if not m:
            continue
        date = m.group(1)
        if not (a.since <= date <= a.until):
            excluded_dates[date] = 0
            continue
        day = gaps.get(date)
        try:
            bundle = json.load(open(p))
        except Exception:                                        # noqa: BLE001
            continue
        for t in bundle.get("trades", []):
            if str(t.get("status", "")).lower() != "closed":
                continue
            n_closed += 1
            in_window += 1
            sym = _symbol_of(t)
            grec = (day or {}).get(sym)
            if not grec or grec.get("gap_class") not in CLASSES:
                no_gap_record += 1
                if day is None:
                    miss_date[date] += 1
                elif grec is None:
                    miss_sym[f"{date}/{sym}"] += 1
                else:
                    miss_class[str(grec.get("gap_class"))] += 1
                continue
            joined_by_date[date] += 1
            if a.window.upper() != "ALL":
                b = _entry_bucket(t)
                if b is None:
                    no_bucket += 1
                    continue
                if b != a.window.upper():
                    continue
            key = str(t.get(a.by) or "?")
            pnl = _num(t.get("pnl_usd"))
            if a.metric == "r":
                ml = abs(_num(t.get("max_loss")))
                if ml <= 0:
                    no_denominator += 1
                    continue
                val = pnl / ml
            elif a.metric == "winrate":
                val = 1.0 if pnl > 0 else 0.0
            else:
                val = pnl
            cells[(key, grec["gap_class"])].append(val)
            totals[grec["gap_class"]] += 1

    if a.diagnose:
        print(f"closed trades      : {n_closed}")
        print(f"joined             : {sum(totals.values())}")
        print(f"NOT joined         : {no_gap_record}\n")
        print("WHY, by cause")
        print(f"  date absent from the gap lookup : {sum(miss_date.values())}")
        for d, n in miss_date.most_common():
            print(f"      {d}  {n} trades   <- no gap record for this date at all")
        print(f"  symbol absent within a present date : {sum(miss_sym.values())}")
        by_sym = collections.Counter()
        by_date2 = collections.Counter()
        for k, n in miss_sym.items():
            d, sy = k.split("/")
            by_sym[sy] += n
            by_date2[d] += n
        print("      top symbols:", ", ".join(f"{s_}:{n}" for s_, n in by_sym.most_common(8)))
        print("      top dates  :", ", ".join(f"{d}:{n}" for d, n in by_date2.most_common(8)))
        print(f"  gap_class not CONT/FLAT/REV : {sum(miss_class.values())}"
              f"   {dict(miss_class)}")
        print("\nJOINED per date (to see whether the loss is one date or spread)")
        for d in sorted(set(list(joined_by_date) + list(miss_date) + list(by_date2))):
            print(f"  {d}   joined {joined_by_date[d]:>4}   "
                  f"missed {miss_date[d] + by_date2[d]:>4}")
        print("\nREADING IT: a loss concentrated on the FIRST tape date is the")
        print("first-appearance skip and is correct by construction. A loss spread")
        print("across dates and symbols means the PRIOR session was never harvested")
        print("for those symbols — the join is honest, but the sample is")
        print("structurally thin and that is itself the finding.")
        return 0

    if not cells:
        # Say WHICH cause, rather than blaming the first one that comes to mind.
        # v1.4's first run printed "check that trade dates overlap" when every
        # trade had actually been dropped for a missing max_loss — a failure
        # reporting the wrong reason, which is the exact class of bug this whole
        # session has been chasing.
        if a.metric == "r" and no_denominator:
            print(f"Nothing joined: all {no_denominator} in-window trades were "
                  f"dropped because\n  max_loss is missing or zero, so R has no "
                  f"denominator. Either those rows\n  predate the column being "
                  f"populated, or use --metric winrate instead.")
        elif in_window == 0:
            print(f"Nothing joined: no closed trades inside {a.since}..{a.until}.")
        else:
            print("Nothing joined: trades exist in the window but none matched a "
                  "gap record.\n  Run with --diagnose to see which side is missing.")
        return 2

    if a.since <= "2026-07-22":
        print("⚠ WARNING: --since is at or before 2026-07-22, so this pools "
              "pnl_usd ACROSS\n  the mark-limit execution change. HISTORY.md: "
              "\"P&L / fill-dependent stats\n  are confounded by both changes.\" "
              "Fills differ on either side of that date.\n")
    print(f"window             : {a.since} .. {a.until}"
          f"   ({len(excluded_dates)} date(s) excluded)")
    print(f"fleet_trades files : {len(paths)}")
    print(f"closed trades      : {n_closed}")
    print(f"joined to a gap    : {sum(totals.values())}"
          f"   (CONT {totals['CONT']}  FLAT {totals['FLAT']}  REV {totals['REV']})")
    print(f"no gap record      : {no_gap_record}")
    if a.window.upper() != "ALL":
        print(f"window             : {a.window.upper()}  "
              f"(no usable entry time: {no_bucket})")
    print(f"row dimension      : {a.by}")
    unit_label = {"r": "R (pnl_usd / max_loss)",
                  "winrate": "win rate, 0/1 per trade",
                  "pnl": "pnl_usd — UNDERPOWERED, see the header"}[a.metric]
    print(f"metric             : {unit_label}")
    if a.metric == "r" and no_denominator:
        print(f"                     ({no_denominator} trades dropped: max_loss "
              f"missing or zero)")
    print("                     PAPER fills — see the header's limits.\n")

    rows = sorted({k for k, _ in cells})

    # v1.5 — cells stay keyed on the ORIGINAL class; pooling happens HERE, so
    # the un-pooled arms remain available for the homogeneity check below.
    pooling = a.pool == "gapflat"
    show_classes = POOLED_CLASSES if pooling else CLASSES

    def vals(row, cls):
        if not pooling:
            return cells.get((row, cls), [])
        out = []
        for src, dst in POOL_MAP.items():
            if dst == cls:
                out.extend(cells.get((row, src), []))
        return out

    if pooling:
        print("POOLED: CONT + REV -> GAP. Verdicts below say whether that was "
              "legitimate\n        for each row; a NOT POOLABLE row's cell is "
              "printed but must not be read.\n")

    print(f"{'':<26}" + "".join(f"{c:>26}" for c in show_classes))
    for r in rows:
        line = f"{r[:25]:<26}"
        for c in show_classes:
            xs = vals(r, c)
            if len(xs) < MIN_CELL_N:
                line += f"{f'n={len(xs)} (refused)':>26}"
                continue
            mean, hw, n = _mean_ci(xs)
            wins = sum(1 for x in xs if x > 0)
            line += f"{f'{mean:+.1f}±{hw:.1f} {wins/n:.0%} n={n}':>26}"
        print(line)

    print(f"\n  mean {unit_label} ±95%, win rate, n. Cells under n={MIN_CELL_N} refused.")

    # ── POWER, so an underpowered cell is never read as a null ──────────────
    shown = {(r, c): vals(r, c) for r in rows for c in show_classes}
    allvals = [v for xs in shown.values() for v in xs]
    if len(allvals) > 2:
        m_all = sum(allvals) / len(allvals)
        sd = math.sqrt(sum((x - m_all) ** 2 for x in allvals) / (len(allvals) - 1))
        biggest = max((len(x) for x in shown.values()), default=0)
        # smallest difference detectable at 95%/80% with the largest cell we have
        detectable = (1.96 + 0.84) * sd * math.sqrt(2.0 / max(biggest, 1))
        print(f"\n  POWER: sd={sd:.3f} across all cells; largest cell n={biggest}.")
        print(f"  Smallest difference detectable at 95%/80% with that n: "
              f"{detectable:.3f} {unit_label.split(' ')[0]}.")
        print("  A cell showing 'no difference' smaller than that is UNDERPOWERED,")
        print("  not null — the sample cannot see an effect that size yet.")

    # ── v1.5 — WAS THE POOL LEGITIMATE? ─────────────────────────────────────
    # Pooling two arms that disagree averages a real positive against a real
    # negative and reports a null. That is the one way a LARGER n is worse than
    # a smaller one, and in the pooled table above it is completely invisible.
    if pooling:
        print("\n" + "=" * 62)
        print("POOL LEGITIMACY — CONT vs REV, the two arms merged into GAP")
        print("=" * 62)
        for r in rows:
            cont, rev = cells.get((r, "CONT"), []), cells.get((r, "REV"), [])
            if len(cont) < MIN_CELL_N or len(rev) < MIN_CELL_N:
                print(f"  {r[:25]:<26} UNDERPOWERED — CONT n={len(cont)}, "
                      f"REV n={len(rev)}; cannot say whether the pool is "
                      f"legitimate")
                continue
            mc, hc, _ = _mean_ci(cont)
            mr, hr, _ = _mean_ci(rev)
            diff = abs(mc - mr)
            band = math.sqrt(hc * hc + hr * hr)
            verdict = "NOT POOLABLE" if diff > band else "poolable"
            print(f"  {r[:25]:<26} CONT {mc:+.2f}±{hc:.2f}   REV {mr:+.2f}±{hr:.2f}"
                  f"   |diff| {diff:.2f} vs band {band:.2f}   -> {verdict}")
        print("\n  NOT POOLABLE means the two gap classes behave differently for")
        print("  that row, so the GAP column above is an average of two real and")
        print("  opposite effects. Read the three-way table for that row instead.")
        print("  UNDERPOWERED is not permission — it means the question is open.")

    # ── the one comparison worth calling out explicitly ─────────────────────
    print("\n" + "=" * 62)
    print("READING IT")
    print("=" * 62)
    print("  A row whose CONT and FLAT cells differ by more than their bands is")
    print("  a strategy whose outcome depends on the day type — and nothing in")
    print("  the fleet currently keys on that.")
    print("  ORB is the one to look at first: it forms its range 09:30-10:00,")
    print("  the window the clean A2 grid shows is DEAD on flat opens and HOT on")
    print("  gap days. AH has it at -0.24R over 252 trades with no explanation.")
    print("  Medians are printed below because one large loser can dominate a")
    print("  small cell's mean.")
    print()
    for r in rows:
        parts = []
        for c in show_classes:
            xs = vals(r, c)
            parts.append(f"{c} med {_median(xs):+.1f}" if len(xs) >= MIN_CELL_N
                         else f"{c} —")
        print(f"  {r[:25]:<26} " + "   ".join(parts))
    print("\nNot a backtest. Reports realised outcomes partitioned by a variable")
    print("that was always computable and never computed. Any gate that follows")
    print("needs its own pre-registered validation.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
