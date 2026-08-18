#!/usr/bin/env python3
"""
tests/spread_counterfactual.py — v1.4 — 2026-08-13   (TC.7)

v1.4 — 2026-08-13 — `--anchor floor`, for the operator's TRENDING_BEAR thesis:
        *"massive downward moves almost always end with them hitting a hard
        floor. There's some spot of support that they hammer into and they
        cannot go past it."* TRENDING_BEAR is the worst regime in the book —
        118 trades, 36%% win, **-$7,373.50** — and he will not sit it out.
        THE STRUCTURE IS HIS ORB RULE MIRRORED: sell a PUT SPREAD BENEATH the
        floor rather than buy puts into the move. It also explains the losses
        mechanically — a long put chasing a down move dies when the move stalls
        at support, which is exactly what a debit cannot survive and a credit is
        indifferent to.
        ⚠️ **THE POOL LIST IS NOT ON DISK.** `LiquidityPool` (price/kind/
        touch_count/name/is_named/swept) lives only in memory; there is no
        `liq_ctx` in the journal and nothing writes the pools. So the floor is
        RECONSTRUCTED FROM THE TAPE, and only the parts that are DETERMINISTIC:
          · PDL — the prior trading session's low
          · SESSION LOW so far, up to the entry minute
        **EQUAL-LOWS ARE DELIBERATELY EXCLUDED.** Reproducing the mapper's swing
        definition here would create a SECOND LINEAGE of the same concept — the
        thing WORKING_AGREEMENT 7 and the pitchfork white paper both forbid —
        and a floor built on a slightly different pivot rule is not the floor
        the bot would have used. Two levels, both exact, is the honest scope;
        the result is a LOWER BOUND on what a full pool set would find.
        ⇒ FILE THIS AS A COLLECTION GAP: the pools are the input to every
        named-level decision and they are not archived. Same class as the chain
        archive before 2026-07-23.

v1.3 — 2026-08-13 — `--anchor orb`. THE OPERATOR'S STRUCTURAL STRIKE RULE:
        *"set the put spread at the top of the orb range for a runaway long and
        the bottom of the orb range for the call spread on a runaway short."*
        WHY IT IS A BETTER ANCHOR THAN A PERCENTAGE FROM ENTRY: the broken ORB
        boundary IS the invalidation level. On a runaway long price broke the
        range and never retested it, so the ORB HIGH is the floor of that move
        and the level `orb_structure_stop` calls thesis death. A put spread
        short there loses only if the setup was wrong. Same geometry mirrored
        for a runaway short: the ORB LOW is now overhead, so the call spread
        sells above it.
        **THE DISTRIBUTION IS THE WHOLE ANSWER AND IT IS PRINTED FIRST.** v1.2
        found the handoff NEGATIVE at 0.25-1.00%% from entry and POSITIVE at
        1.50%%+ (+0.33/+0.32/+0.35). The handoff enters on a pullback into an
        FVG above the broken range, so the boundary sits some distance below
        entry. **If that distance clusters at 1.5%%+ the rule lands in the
        profitable band BY CONSTRUCTION rather than by tuning; if it clusters
        near 0.5%% it lands in the band that lost money.** No new collection
        needed — the range reconstructs from the 09:30-09:35 bars already in
        the OHLC.
        ⚠️ OFFSETS MEAN SOMETHING DIFFERENT UNDER THIS ANCHOR. They are distance
        BEYOND THE BOUNDARY, not beyond entry, and 0.00%% (at the boundary
        exactly, which is the operator's literal proposal) is included.
        ⚠️ THE CONTROL ARM STILL MATTERS. This is the population that priced
        WORST in v1.2 and the control beat it at every offset. Distance may
        rescue it — that is what "it doesn't matter that it turned against me as
        long as it doesn't breach" buys — but the tape underneath is still the
        worse tape. Run standalone on the identical anchor, and if it also wins
        this is a general edge, not a runaway-specific one.

v1.2 — 2026-08-13 — OOM-KILLED ON THE FIRST WORKING RUN. Bounded work, UNBOUNDED
        MEMORY. v1.1 cached every parsed chain snapshot for every (date, symbol)
        it touched and never evicted: ~78 snapshots x ~120 contracts x 13 fields
        as Python dicts, times a couple of hundred symbol-days, resident at once.
        The kernel killed it before a single row printed.
        THE FIX IS SCOPE, NOT CLEVERNESS — process ONE SYMBOL-DAY AT A TIME:
        group the population by (date, symbol), collect that group's target
        minutes FIRST, stream the .jsonl.gz once keeping ONLY snapshots within
        the match window of a target, price the group, then drop it. Peak
        residency is one symbol-day instead of all of them, and the file is
        still read exactly once.
        ⚠️ WHY NO FIXTURE CAUGHT THIS: the fixture is one symbol, one date, one
        chain file. **A single-symbol-day fixture cannot exercise a cache that
        only grows across symbol-days** — the same blind spot as v1.0's
        single-snapshot fixture missing the sort tie, one level up. Scale
        failures need a fixture with scale, and this one still does not have
        one; the guard is the restructure, not a test.
        Also reports peak group size so a pathological symbol-day is visible.

v1.1 — 2026-08-13 — CRASH FIX: `sorted(snaps)` on `(minute, dict)` tuples.
        When two snapshots share a minute Python falls through to comparing the
        DICTS and raises `TypeError: '<' not supported between instances of
        'dict' and 'dict'`. Now sorted on the KEY ONLY.
        ⚠️ WHY THE FIXTURE MISSED IT, and this is the reusable part: the fixture
        wrote ONE snapshot per symbol-day, so the tuple comparator was never
        reached — a single-element list cannot exercise a sort. A fixture that
        cannot produce a TIE cannot test a tie-break. The fixture now writes two
        snapshots at the SAME minute, which reproduces the crash against v1.0.

WOULD THESE TRADES HAVE PAID AS SHORT VERTICALS INSTEAD OF LONG PREMIUM?

Operator, 2026-08-13: *"I think those opportunities would have fared better as
vertical spreads instead of paying long premium to chase spent moves."* And,
correcting the statistic this tool was nearly built on: **"With a credit spread,
it doesn't matter that it turned against me as long as it doesn't breach."**

────────────────────────────────────────────────────────────────────────────
THE POPULATION, AND WHY IT IS THIS ONE
────────────────────────────────────────────────────────────────────────────
`factor_sweep --setup-type trend_continuation_handoff` split by
`reg.conviction` found ONE band carrying more than the whole strategy's loss:

    conviction EXACTLY 1.00, handoff path — n=128, 41%% win, **-$52/trade,
    -$6,623** — against ContinuationStrategy's total of -$6,351.

The same peg through the STANDALONE path is n=128, 50%% win, **+$1/trade**. Same
conviction, same count, opposite outcome. The handoff's licence is that the
label is UNRELIABLE after a runaway; when the label is also pegged at maximum
you have the runaway AND total regime confidence, i.e. the move is finished and
obvious. That is the population this prices a counterfactual for.

────────────────────────────────────────────────────────────────────────────
TERMINAL ONLY. THIS IS THE WHOLE METHOD AND IT IS THE OPERATOR'S CORRECTION.
────────────────────────────────────────────────────────────────────────────
The first design counted MAXIMUM ADVERSE EXCURSION against candidate short
strikes. **That is wrong**, and it is the same error `tcs_floor_durability` v1.1
was rewritten to fix: MAE counts a TOUCH, a defined-risk spread held to expiry
only loses on ACCEPTANCE. On the impulse population that distinction was worth
everything — intraday held 14.7%%, terminal OK **56.1%%**, **41.4%% RECOVERED**.

**Every trade that dipped through a candidate short strike and came back is a
LOSS for the long and a WIN for the spread.** An MAE-based test measures that
entire population out of existence. So this reports INTRADAY / TERMINAL /
RECOVERED separately and never merges them, exactly as the durability tool does.

⚠️ "Never favorable" is IRRELEVANT here. It says the LONG never went green. For
   a short vertical sold beneath the move that is neutral-to-good.

GEOMETRY, the one place direction still bites: a bull handoff BUYS CALLS, so the
credit equivalent (the operator's "vertical spread at the floor of the Move")
SELLS A PUT SPREAD BENEATH ENTRY. Price moving against the long is price moving
TOWARD the short strike — so the adverse side is the side that matters, but only
at the close, never on the way.

────────────────────────────────────────────────────────────────────────────
⚠️ THE ASYMMETRY. READ THIS BEFORE READING THE TABLE.
────────────────────────────────────────────────────────────────────────────
The LONG side is REAL: real fills, real slippage, real management — stops fired,
trails engaged, positions closed early. The SPREAD side is MODELLED: archived
quotes, held to expiry, no management, no early assignment, no commission, and
a fill at the posted bid.

**That tilts the comparison toward the counterfactual by construction.** The gap
has to be LARGE to survive it. A narrow win for the spread is a NULL, not a
result, and this tool says so rather than leaving it to the reader.

READ-ONLY. stdlib only. Imports the join from `scorer_backtest` and the pricing
from `credit_edge` — ONE implementation of each, never a third.

USAGE (control)
    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python tests/spread_counterfactual.py --since 2026-07-20
    ... --setup-type trend_continuation_standalone      # the control arm
    ... --conv-min 0.0 --conv-max 1.01                  # the whole path
"""

import argparse
import collections
import csv
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.scorer_backtest import (load_scored, load_trades,                # noqa: E402
                                   JOIN_TOL_S, JOURNAL)
from tests.credit_edge import (CHAINS, ohlc_root, price_vertical,           # noqa: E402
                               settle_loss, OFFSETS, MIN_CREDIT)

MIN_N = 30
# The ORB is the 09:30-09:35 ET candle: 1m bars 570..574 inclusive.
ORB_FIRST_MIN, ORB_LAST_MIN = 9 * 60 + 30, 9 * 60 + 34
# Under --anchor orb the ladder starts AT the boundary, which is the operator's
# literal proposal, then walks further out.
ORB_OFFSETS = (0.0,) + OFFSETS


def prior_date(date, root):
    """The trading date immediately before `date` in the OHLC archive."""
    if not root or not os.path.isdir(root):
        return None
    ds = sorted(d for d in os.listdir(root) if len(d) == 10 and d < date)
    return ds[-1] if ds else None


def named_floor(date, sym, root, minute, entry):
    """Nearest DETERMINISTIC named support strictly below `entry`.

    Returns (price, name) or None. Only two levels, both exact and both the
    ones a human would actually name:
      · PDL      — prior session low
      · SESS_LOW — the running low of THIS session up to the entry minute
                   (up to, never past — a level formed after the fill is
                   information the trade did not have)
    """
    cands = []
    pd = prior_date(date, root)
    if pd:
        pb = (session_path(pd, root) or {}).get(sym) or []
        if pb:
            cands.append((min(b[2] for b in pb), "PDL"))
    tb = (session_path(date, root) or {}).get(sym) or []
    upto = [b for b in tb if b[0] <= minute]
    if upto:
        cands.append((min(b[2] for b in upto), "SESS_LOW"))
    below = [c for c in cands if c[0] < entry]
    return max(below, key=lambda c: c[0]) if below else None


def orb_range(bars):
    """(high, low) of the 09:30-09:35 opening candle, or None.

    Reconstructed from the 1m tape rather than read from a log, so it works on
    every archived session including ones that predate any ORB journalling.
    """
    w = [b for b in bars if ORB_FIRST_MIN <= b[0] <= ORB_LAST_MIN]
    if not w:
        return None
    return max(b[1] for b in w), min(b[2] for b in w)


def session_path(date, root):
    """{symbol: [(minute, high, low, close)]} for the whole session."""
    out = {}
    if not root:
        return out
    for path in sorted(glob.glob(os.path.join(root, date, "*.csv"))):
        sym = os.path.basename(path).split("_")[0]
        bars = []
        try:
            with open(path, encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    t = r.get("timestamp") or r.get("time") or ""
                    try:
                        m = int(t[11:13]) * 60 + int(t[14:16])
                        bars.append((m, float(r["high"]), float(r["low"]),
                                     float(r["close"])))
                    except Exception:                          # noqa: BLE001
                        continue
        except Exception:                                      # noqa: BLE001
            continue
        if bars:
            out[sym] = sorted(bars)
    return out


def load_group_chain(date, sym, minutes, window=10):
    """Snapshots for ONE symbol-day, keeping only those near a target minute.

    v1.2 — the memory fix. `minutes` is every entry minute in this group, known
    before the file is opened, so the stream can discard the ~95%% of snapshots
    no trade needs instead of parsing them into a cache that never shrinks.
    Returns [(minute, {(side, strike): contract})] sorted by minute.
    """
    path = os.path.join(CHAINS, date, f"{sym}.jsonl.gz")
    if not os.path.isfile(path) or not minutes:
        return []
    import gzip
    keep = []
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:                              # noqa: BLE001
                    continue
                ts = r.get("ts_et") or ""
                if len(ts) < 16 or not r.get("underlying"):
                    continue
                try:
                    m = int(ts[11:13]) * 60 + int(ts[14:16])
                except Exception:                              # noqa: BLE001
                    continue
                if min(abs(m - t) for t in minutes) > window:
                    continue                    # nothing in this group wants it
                rows = {}
                for c in (r.get("contracts") or []):
                    t = str(c.get("type") or "").lower()
                    t = "call" if t.startswith("c") else (
                        "put" if t.startswith("p") else "")
                    if not t:
                        continue
                    try:
                        rows[(t, round(float(c.get("strike")), 4))] = c
                    except Exception:                          # noqa: BLE001
                        continue
                if rows:
                    keep.append((m, rows))
    except Exception:                                          # noqa: BLE001
        return []
    # KEY ONLY (v1.1) — bare-tuple sort falls through to the dict on a tie.
    keep.sort(key=lambda x: x[0])
    return keep


def nearest(snaps, minute, window=10):
    if not snaps:
        return None
    best = min(snaps, key=lambda s: abs(s[0] - minute))
    return best[1] if abs(best[0] - minute) <= window else None


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-07-20")
    ap.add_argument("--strategy", default="ContinuationStrategy")
    ap.add_argument("--setup-type", default="trend_continuation_handoff")
    ap.add_argument("--conv-min", type=float, default=1.0,
                    help="regime conviction floor (default 1.0 = the pegged "
                         "band that carries the whole loss)")
    ap.add_argument("--conv-max", type=float, default=1.01)
    ap.add_argument("--width", type=float, default=5.0)
    ap.add_argument("--min-n", type=int, default=MIN_N)
    ap.add_argument("--regime", default="",
                    help="restrict to one regime label, e.g. TRENDING_BEAR")
    ap.add_argument("--anchor", default="entry", choices=("entry", "orb", "floor"),
                    help="entry = offsets beyond the fill (v1.2 behaviour). "
                         "orb = offsets beyond the BROKEN ORB BOUNDARY — the "
                         "invalidation level: ORB high for a long, low for a "
                         "short. floor = nearest DETERMINISTIC named support "
                         "below the fill (PDL or session low) — the operator's "
                         "hard-floor thesis.")
    a = ap.parse_args(argv[1:])

    if not os.path.isdir(JOURNAL):
        print(f"no journal at {JOURNAL}")
        return 0
    dates = sorted(d for d in os.listdir(JOURNAL)
                   if len(d) == 10 and d >= a.since)
    root = ohlc_root()

    # ── join, reusing scorer_backtest's implementation ──────────────────────
    pop, seen, unmatched = [], set(), 0
    for date in dates:
        sc = load_scored(date)
        idx = collections.defaultdict(list)
        for s in sc:
            idx[(s["sym"], s["strategy"])].append(s)
        for t in load_trades(date, seen):
            if t["strategy"] != a.strategy:
                continue
            if a.setup_type and t["setup_type"] != a.setup_type:
                continue
            best, bd = None, JOIN_TOL_S + 1
            for s in idx.get((t["sym"], t["strategy"])) or []:
                d = abs((s["ts"] - t["ts"]).total_seconds())
                if d < bd:
                    best, bd = s, d
            if best is None or bd > JOIN_TOL_S:
                unmatched += 1
                continue
            _reg = (best.get("raw") or {}).get("regime") or {}
            conv = _reg.get("conviction")
            if conv is None or not (a.conv_min <= float(conv) < a.conv_max):
                continue
            if a.regime and str(_reg.get("label") or "") != a.regime:
                continue
            pop.append({**t, "date": date, "conv": float(conv)})

    print("=" * 84)
    print("  SPREAD COUNTERFACTUAL (TC.7) — long premium vs a short vertical")
    print(f"  {a.strategy} / {a.setup_type or 'ALL'} / conviction "
          f"[{a.conv_min}, {a.conv_max})   width {a.width:g}")
    print(f"  {len(dates)} session(s) since {a.since}   population {len(pop)}"
          f"   unmatched-to-journal {unmatched}")
    print("=" * 84)
    if not pop:
        print("\n  empty population. ABSENT MEASUREMENT, not a null.")
        return 0

    cells = collections.defaultdict(list)
    sym_days, no_chain, no_tape, no_entry = set(), 0, 0, 0
    long_pnl = 0.0
    peak_group = 0
    no_orb = 0
    no_floor = 0
    floor_names = collections.Counter()
    boundary_dist = []          # entry-to-boundary, % of entry — the answer
    offsets = ORB_OFFSETS if a.anchor in ("orb", "floor") else OFFSETS

    # v1.2 — ONE SYMBOL-DAY AT A TIME. Group first, so the chain file for a
    # group is opened once, filtered to that group's minutes, and DROPPED before
    # the next group is touched. Peak residency is one symbol-day.
    groups = collections.defaultdict(list)
    for t in pop:
        groups[(t["date"], t["sym"])].append(t)

    for (date, sym), grp in sorted(groups.items()):
        usable = []
        for t in grp:
            raw = t.get("raw") or {}
            try:
                entry = float(raw.get("underlying_entry") or 0)
            except Exception:                                  # noqa: BLE001
                entry = 0.0
            direction = str(raw.get("direction") or "").lower()
            if entry <= 0 or direction not in ("long", "short"):
                no_entry += 1
                continue
            usable.append((t, entry, direction,
                           t["ts"].hour * 60 + t["ts"].minute))
        if not usable:
            continue

        bars = (session_path(date, root) or {}).get(sym) or []
        if not bars:
            no_tape += len(usable)
            continue

        orb = orb_range(bars) if a.anchor == "orb" else None
        if a.anchor == "orb" and orb is None:
            no_orb += len(usable)
            continue

        snaps = load_group_chain(date, sym, [u[3] for u in usable])
        peak_group = max(peak_group, len(snaps))

        for t, entry, direction, minute in usable:
            rows = nearest(snaps, minute)
            if not rows:
                no_chain += 1
                continue
            fwd = [b for b in bars if b[0] >= minute]
            if len(fwd) < 2:
                no_tape += 1
                continue
            term_close = fwd[-1][3]
            long_pnl += t["pnl"]
            sym_days.add((date, sym))

            # THE ADVERSE SIDE. A long (bull) handoff is replaced by a PUT
            # spread BENEATH entry; a short by a CALL spread above it.
            side = "put" if direction == "long" else "call"
            # v1.3 — the ANCHOR. `entry` is the fill; `orb` is the BROKEN
            # BOUNDARY, which is the invalidation level and therefore the floor
            # of the move: ORB high under a long, ORB low under a short.
            if a.anchor == "floor":
                # THE FLOOR IS ALWAYS BELOW AND THE SPREAD IS ALWAYS A PUT.
                # Both his cases reduce to one structure: a bull move's floor
                # is the level it broke from, a bear move's floor is the
                # support it hammers into. Sell beneath it either way.
                side = "put"
                fl = named_floor(date, sym, root, minute, entry)
                if fl is None:
                    no_floor += 1
                    continue
                base, _nm = fl
                floor_names[_nm] += 1
                boundary_dist.append(100.0 * (entry - base) / entry)
            elif a.anchor == "orb":
                base = orb[0] if side == "put" else orb[1]
                # Record how far the fill sat from the boundary. THIS is what
                # decides whether the rule lands in the band that paid.
                d = (entry - base) / entry if side == "put" else (base - entry) / entry
                boundary_dist.append(100.0 * d)
            else:
                base = entry
            strikes = sorted({k[1] for k in rows})
            for off in offsets:
                target = base * (1 - off) if side == "put" else base * (1 + off)
                cand = [k for k in strikes
                        if (k <= target if side == "put" else k >= target)]
                if not cand:
                    continue
                k = max(cand) if side == "put" else min(cand)
                pv = price_vertical(rows, side, k, a.width)
                if pv is None:
                    continue
                credit, ks, kl = pv
                touched = any((b[2] < ks) if side == "put" else (b[1] > ks)
                              for b in fwd)
                loss = settle_loss(side, ks, kl, term_close, a.width)
                cells[off].append((credit, loss, touched))
        snaps = None                      # explicit — the whole point of v1.2

    print(f"\n  priced {sum(len(v) for v in cells.values()):,} spreads over "
          f"{len(sym_days)} SYMBOL-DAYS — read every n against that, not itself.")
    print(f"  skipped — no chain within 10 min {no_chain} · no tape {no_tape} ·"
          f" no entry/direction {no_entry}")
    print(f"  peak snapshots resident for any one symbol-day: {peak_group}"
          f"  ({len(groups)} symbol-day groups processed one at a time)")
    if a.anchor == "floor":
        print(f"  skipped — no named floor below the fill {no_floor}")
        if floor_names:
            print("  floor used: " + " · ".join(f"{k} {v}" for k, v in
                                                floor_names.most_common()))
    if a.anchor == "orb":
        print(f"  skipped — no ORB window in the tape {no_orb}")
    if a.anchor in ("orb", "floor"):
        if boundary_dist:
            bd = sorted(boundary_dist)
            def _q(q):
                return bd[min(len(bd) - 1, max(0, int(round(q * (len(bd) - 1)))))]
            print(f"\n  {'-' * 80}")
            print(f"  ENTRY-TO-{'FLOOR' if a.anchor == 'floor' else 'BOUNDARY'}"
                  f" DISTANCE (% of entry, n={len(bd)}) — READ THIS FIRST")
            print(f"    p10 {_q(.10):+.2f}%   p25 {_q(.25):+.2f}%   "
                  f"p50 {_q(.50):+.2f}%   p75 {_q(.75):+.2f}%   "
                  f"p90 {_q(.90):+.2f}%")
            neg = sum(1 for x in bd if x <= 0)
            print(f"    at/through the boundary already: {neg} "
                  f"({100.0*neg/len(bd):.0f}%) — those are fills where the "
                  f"structural strike sits AT or BEYOND spot")
            print(f"  v1.2 found the ENTRY-anchored ladder NEGATIVE below 1.00%")
            print(f"  and POSITIVE from 1.50%. If this distribution sits in the")
            print(f"  second band the rule is structurally in the money; if it")
            print(f"  sits in the first it is not, and no strike tuning fixes it.")
    print(f"\n  ACTUAL LONG RESULT on the same trades: net ${long_pnl:+,.0f}"
          f"  ({len(sym_days)} symbol-days)")

    if not cells:
        print("\n  nothing priced. ABSENT MEASUREMENT, not a null.")
        return 0

    print(f"\n  offsets are distance beyond "
          + {"orb": "THE ORB BOUNDARY", "floor": "THE NAMED FLOOR"}
          .get(a.anchor, "the fill"))
    print(f"  {'offset':>8}{'n':>7}{'touched':>9}{'terminal OK':>13}"
          f"{'RECOVERED':>11}{'credit':>9}{'E[loss]':>9}{'EV/spread':>11}")
    for off in offsets:
        g = cells.get(off) or []
        if not g:
            continue
        n = len(g)
        safe = sum(1 for c, l, tch in g if l <= 0.0)
        tch_n = sum(1 for c, l, tch in g if tch)
        rec = sum(1 for c, l, tch in g if tch and l <= 0.0)
        cr = sum(c for c, _, _ in g) / n
        el = sum(l for _, l, _ in g) / n
        flag = "" if n >= a.min_n else "  <- UNDERPOWERED"
        print(f"  {off*100:>7.2f}%{n:>7}{100.0*tch_n/n:>8.0f}%"
              f"{100.0*safe/n:>12.0f}%"
              f"{(f'{100.0*rec/tch_n:.0f}%' if tch_n else '—'):>11}"
              f"{cr:>9.2f}{el:>9.2f}{cr-el:>+11.2f}{flag}")

    print("\n  RECOVERED = of the spreads price TOUCHED through, the share that")
    print("  still closed safe. THAT COLUMN IS THE OPERATOR'S POINT: every one")
    print("  of those is a loss for the long and a win for the spread, and an")
    print("  MAE-based test would have counted it as a breach.")

    print(f"\n{'=' * 84}")
    print("  ⚠️ THE ASYMMETRY, and it decides how you read the table above.")
    print("  The LONG number is REAL — real fills, real slippage, real")
    print("  management (stops fired, trails engaged, early closes). The SPREAD")
    print("  number is MODELLED — archived quotes, filled at the posted bid,")
    print("  held to expiry, no management, no early assignment, no commission.")
    print("  That tilts the comparison TOWARD the counterfactual by")
    print("  construction. A NARROW WIN FOR THE SPREAD IS A NULL, NOT A RESULT.")
    print("=" * 84)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
