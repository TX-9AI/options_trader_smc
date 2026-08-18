#!/usr/bin/env python3
"""
tests/credit_edge.py — v1.2 — 2026-08-13   (TC.5 — the credit side of the trade)

v1.2 — 2026-08-13 — THE POPULATION WAS WRONG, AND THE OPERATOR CAUGHT IT.
        *"The vertical is sold when the price is sitting in close proximity to
        the short strike level so that it's rich in premium & can withstand a
        little pressure... essentially a 'touch' of the channel outer tines
        should trigger a short strike selection just out of reach and with good
        liquidity."*
        v1.1 priced a spread at EVERY snapshot regardless of where price sat.
        That pools two different trades — price MID-CHANNEL (strike far, credit
        thin, safety high) and price AT THE TINE (strike near, credit rich, risk
        real) — and reports the blend. It is why credit averaged only 14-19%% of
        width. THE TOUCH IS THE TRADE; everything else is a different strategy.
        (1) `--approach`: fire only when `pos_pct` has cleared the threshold on
            that side — high for the call, low for the put. NOT a new emission:
            `pitchfork_observer` already journals `pos_pct`, 0%% on the lower
            tine and 100%% on the upper. This is the same shape as the condor's
            existing `CONDOR_TRIGGER_APPROACH`.
        (2) OTM GUARD. v1.1 never checked the PROJECTED tine was actually
            out-of-the-money against spot, so a stale or near-flat fork could
            project a tine at or inside spot and the tool would happily price a
            short call BELOW THE MONEY. That is the `flat/call` cell in the
            08-12 run: n=184, 22%% safe, E[loss] 3.89, EV -3.04, dragging the
            whole pitchfork arm negative. The operator's "just out of reach" is
            precisely this guard.
        (3) LIQUIDITY on BID/ASK WIDTH, not volume/OI — factor_sweep found
            `contract.volume` and `contract.oi` CONSTANT on the joined sample,
            which almost certainly means zeros in the payload. A filter on a
            constant is a filter that does nothing.
        (4) EFFECTIVE n IS SYMBOL-DAYS. v1.1 printed n=139,600 spreads, but
            every spread from one symbol-day shares ONE terminal close and
            snapshots repeat every 5 min on the same underlying. The real count
            was ~336 independent outcomes. Reporting the spread count as n
            overstates power by two orders of magnitude.

v1.1 — 2026-08-13 — `--anchor pitchfork`: THE PROJECTED TINE, and the reason
        the operator's leg-ordering rule does not need to be encoded.
        His point: a fork has SLOPE and therefore TIME. The short strike is
        FIXED once sold; the tine keeps moving. On an UP-sloping fork a PUT
        sold at today's lower tine gets SAFER every bar (the channel rises away
        from it) while a CALL sold at today's upper tine gets more DANGEROUS
        (the channel rises INTO it). So the honest call strike is not the tine
        NOW, it is the tine PROJECTED TO THE BELL, and the extra buffer it
        needs is `slope x bars_remaining` — a quantity that SHRINKS as the
        session runs.
        ⇒ ONE RULE PRODUCES HIS ORDERING: sell each side when its strike clears
        the tine projected to the close. On an up-slope the put clears
        immediately and the call only clears late; on a down-slope, mirrored.
        No slope-sign branch, and it also handles the cases a branch gets
        wrong — a near-flat fork (both sides sellable early) and a steep one
        late in the day (neither is).
        SLOPE IS DERIVED, NOT ASSUMED: the observer journals `upper`/`median`/
        `lower` at the CURRENT bar only, so slope is fitted from two
        observations of the SAME fork — keyed on (tf, born_idx), because a
        re-anchored fork is a different object and pooling them would fit a
        slope across a discontinuity.
        ⚠️ COVERAGE IS THE BINDING CONSTRAINT, NOT THE MATHS. PF.2's observer
        began journaling at the 2026-08-12 wake. Expect this arm to REFUSE for
        a while. The spot arm is the baseline it has to beat, and it runs on
        three weeks of archived chains today.
v1.0 — 2026-08-13 — first cut, spot anchor.

WHAT DOES A SHORT VERTICAL ACTUALLY PAY, AND DOES IT SURVIVE TO THE BELL?

Operator, 2026-08-13: *"Some of those boxes in the afternoon would have to move
massively to overcome expiring theta in any meaningful way, which makes the case
that they should only be selling Credit in the afternoons and not taking long
contracts anymore."*

`tcs_floor_durability` v1.3 answered half of this and said so itself: *"further
OTM collects less credit, and this table prices no credit at all. It bounds
RISK, and the credit side of that trade-off is a separate measurement."* This is
that measurement.

────────────────────────────────────────────────────────────────────────────
WHY THIS IS NOT A REPEAT OF THE DURABILITY RUN
────────────────────────────────────────────────────────────────────────────
Durability gives terminal SURVIVAL by distance. Survival alone cannot decide
anything: a strike 3% out survived 98.5% of the time and may collect three
cents, which loses money. The decision needs both sides multiplied together:

    EV per $1 of width = P(safe) x credit  -  E[loss | breach]

and E[loss|breach] is NOT the full width — a vertical held to expiry loses only
the distance price finished BEYOND the short strike, capped at the width. That
partial-loss term is the difference between a real answer and a scare number,
so it is computed exactly rather than assumed.

⚠️ THE DURABILITY RUN ALSO KILLED THE IMPULSE ANCHOR. Matched control 2026-08-13:
   impulse minus control, TERMINAL **-3.6%% ±1.7%%** — an ARBITRARY recent extreme
   survived BETTER than the impulse origin, at every offset on the curve. So this
   tool deliberately anchors on SPOT, not on an impulse floor: the state that was
   supposed to select was measured selecting nothing. Anchors that are still live
   candidates (pitchfork tines, VWAP) slot into `--anchor` when their data
   supports it — see the note at the bottom of the output.

────────────────────────────────────────────────────────────────────────────
THE DATA, AND WHAT IS ASSUMED
────────────────────────────────────────────────────────────────────────────
Prices are REAL ARCHIVED QUOTES from `data/chain_snapshots/<date>/<SYM>.jsonl.gz`
(harvested to control since harvest v0.5.1). Nothing is modelled:
  · credit  = short leg BID  -  long leg ASK   (you cross the spread on both)
  · outcome = the session's LAST OHLC close vs the short strike

ASSUMED, and each one is a real limitation:
  · HELD TO EXPIRY. No management, no stop, no roll. That is the trade being
    proposed, but it means this cannot be compared to a managed book.
  · Same-day expiry only. The archive is the 0DTE chain the fleet trades.
  · No early assignment, no pin risk at the strike, no commission.
  · The last 1m close stands in for settlement. For SPX (AM/PM settle nuances)
    treat the index rows as indicative, not exact.

REFUSALS: a cell under `--min-n` prints its n and NO verdict. Absent
measurement, not a null — the same floor the rest of the toolkit uses.

READ-ONLY. stdlib only. Writes nothing, touches no fleet, no live path.

USAGE (control)
    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python tests/credit_edge.py --since 2026-07-28
    ... --since 2026-07-28 --from-hour 11        # the operator's afternoon design
    ... --since 2026-07-28 --width 5 --min-n 40
"""

import argparse
import collections
import csv
import datetime as dt
import glob
import gzip
import json
import os
import sys

DTP = os.path.expanduser("~/day_trader_pro")
CHAINS = os.path.join(DTP, "chain_snapshots")
JOURNAL = os.path.join(DTP, "signal_journal")
CLOSE_ET_MIN = 16 * 60          # the bell, in minutes past midnight ET
OHLC_CANDIDATES = (os.path.join(DTP, "ohlc"),
                   os.path.join(DTP, "data", "OHLC"))

# Offsets are the SAME LADDER tcs_floor_durability prints, so the two tables
# can be read side by side without re-basing anything.
OFFSETS = (0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.03)
MIN_N = 30
MIN_CREDIT = 0.02          # below two cents there is no trade to price
MIN_OTM_PCT = 0.001        # a short strike must clear spot by at least this


def pctile(v, q):
    v = sorted(x for x in v if x is not None)
    return v[min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))] if v else None


def ohlc_root():
    for c in OHLC_CANDIDATES:
        if os.path.isdir(c):
            return c
    return None


def terminal_closes(date, root):
    """{symbol: last 1m close} for the session. The settlement stand-in."""
    out = {}
    if not root:
        return out
    for path in sorted(glob.glob(os.path.join(root, date, "*.csv"))):
        sym = os.path.basename(path).split("_")[0]
        last = None
        try:
            with open(path, encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    try:
                        last = float(r["close"])
                    except Exception:                          # noqa: BLE001
                        continue
        except Exception:                                      # noqa: BLE001
            continue
        if last:
            out[sym] = last
    return out


def _mins(ts):
    """Minutes past midnight from an ET ISO timestamp, or None."""
    try:
        return int(ts[11:13]) * 60 + int(ts[14:16])
    except Exception:                                          # noqa: BLE001
        return None


def load_forks(date, sym):
    """Pitchfork observations for one symbol-day, grouped by FORK IDENTITY.

    Returns {(tf, born_idx): [(minute, upper, lower), ...]} time-ordered.
    Keyed on born_idx because a re-anchored fork is a DIFFERENT object — fitting
    a slope across a re-anchor would fit it across a discontinuity.
    """
    out = collections.defaultdict(list)
    path = os.path.join(JOURNAL, date, f"{sym}.jsonl")
    if not os.path.isfile(path):
        return out
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"pitchfork"' not in line:
                continue
            try:
                r = json.loads(line)
            except Exception:                                  # noqa: BLE001
                continue
            if r.get("event") != "pitchfork":
                continue
            m = _mins(r.get("ts_et") or "")
            pf = r.get("pitchfork") or {}
            if m is None or not isinstance(pf, dict):
                continue
            for tf, st in pf.items():
                if not isinstance(st, dict):
                    continue
                up, lo = st.get("upper"), st.get("lower")
                bi, pp = st.get("born_idx"), st.get("pos_pct")
                if up is None or lo is None:
                    continue
                out[(tf, bi)].append((m, float(up), float(lo),
                                      None if pp is None else float(pp)))
    for k in out:
        out[k].sort()
    return out


def project_tines(forks, minute):
    """Tines PROJECTED TO THE BELL, from the most recent fork observation.

    Returns (upper_at_close, lower_at_close, slope_sign, pos_pct) or None.
    A fork seen only ONCE has no derivable slope and is SKIPPED rather than
    projected flat — a flat projection on a sloping fork is exactly the error
    this whole argument is about.
    """
    best = None
    for (tf, _bi), obs in forks.items():
        prior = [o for o in obs if o[0] <= minute]
        if len(prior) < 2 or len(obs) < 2:
            continue
        (m0, u0, l0, _p0), (m1, u1, l1, p1) = obs[0], prior[-1]
        span = m1 - m0
        if span <= 0:
            continue
        su, sl = (u1 - u0) / span, (l1 - l0) / span
        remain = max(0, CLOSE_ET_MIN - minute)
        cand = (u1 + su * remain, l1 + sl * remain,
                (1 if (su + sl) > 0 else -1 if (su + sl) < 0 else 0), p1)
        # Prefer the observation closest to the snapshot.
        if best is None or m1 > best[0]:
            best = (m1, cand)
    return best[1] if best else None


def price_vertical(rows, side, short_strike, width):
    """Net credit for a vertical at short_strike, from real bid/ask.

    Returns (credit, actual_short, actual_long) or None when either leg is
    missing from the chain. The LONG leg is the protective wing: strike + width
    for a call spread, strike - width for a put spread.
    """
    long_strike = short_strike + width if side == "call" else short_strike - width
    s = rows.get((side, round(short_strike, 4)))
    l = rows.get((side, round(long_strike, 4)))
    if not s or not l:
        return None
    credit = (s.get("bid") or 0.0) - (l.get("ask") or 0.0)
    if credit < MIN_CREDIT:
        return None
    return credit, short_strike, long_strike


def settle_loss(side, short_strike, long_strike, close, width):
    """Exact expiry payoff loss for a defined-risk vertical, capped at width.

    A vertical held to expiry does NOT lose the full width the moment the short
    is breached — it loses the distance price finished beyond it. Treating every
    breach as a max loss is the single easiest way to make a viable credit trade
    look unviable.
    """
    if side == "call":
        beyond = close - short_strike
    else:
        beyond = short_strike - close
    return min(width, max(0.0, beyond))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-07-28")
    ap.add_argument("--from-hour", type=int, default=0,
                    help="ET hour floor for the snapshot (11 = the operator's "
                         "afternoon-credit design). 0 = whole session.")
    ap.add_argument("--to-hour", type=int, default=15)
    ap.add_argument("--width", type=float, default=5.0,
                    help="wing width in points/dollars (condor uses 5)")
    ap.add_argument("--min-n", type=int, default=MIN_N)
    ap.add_argument("--symbol", default="")
    ap.add_argument("--approach", type=float, default=0.0,
                    help="TOUCH TRIGGER (pitchfork anchor only): fire the CALL "
                         "side only when pos_pct >= 100-X and the PUT side only "
                         "when pos_pct <= X. 0 disables (v1.1 behaviour = every "
                         "snapshot, which is NOT the trade). Try 20.")
    ap.add_argument("--max-spread-pct", type=float, default=0.0,
                    help="LIQUIDITY: skip a short leg whose bid/ask width "
                         "exceeds this fraction of its mid. 0 disables. Keys on "
                         "WIDTH, not volume/OI — those read CONSTANT (zeros).")
    ap.add_argument("--anchor", default="spot", choices=("spot", "pitchfork"),
                    help="spot = offsets beyond spot at snapshot time (works on "
                         "3 weeks of chains). pitchfork = offsets beyond the "
                         "TINE PROJECTED TO THE BELL (coverage starts 08-12).")
    a = ap.parse_args(argv[1:])

    if not os.path.isdir(CHAINS):
        print(f"no chain archive at {CHAINS} — nothing to price")
        return 0
    root = ohlc_root()
    dates = sorted(d for d in os.listdir(CHAINS)
                   if len(d) == 10 and d >= a.since)

    # cell -> list of (credit, loss, width)
    cells = collections.defaultdict(list)
    by_hour = collections.defaultdict(list)
    by_slope = collections.defaultdict(list)
    seen_syms, snaps, priced, no_close = set(), 0, 0, 0
    no_fork = 0
    symbol_days = set()
    skip_touch = skip_otm = skip_liq = 0

    for date in dates:
        closes = terminal_closes(date, root)
        for path in sorted(glob.glob(os.path.join(CHAINS, date, "*.jsonl.gz"))):
            sym = os.path.basename(path).split(".")[0]
            if a.symbol and sym != a.symbol:
                continue
            close = closes.get(sym)
            if close is None:
                no_close += 1
                continue
            forks = load_forks(date, sym) if a.anchor == "pitchfork" else None
            seen_syms.add(sym)
            try:
                fh = gzip.open(path, "rt", encoding="utf-8")
            except Exception:                                  # noqa: BLE001
                continue
            with fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:                          # noqa: BLE001
                        continue
                    spot = r.get("underlying")
                    ts = r.get("ts_et") or ""
                    if not spot or len(ts) < 13:
                        continue
                    try:
                        hour = int(ts[11:13])
                    except Exception:                          # noqa: BLE001
                        continue
                    if not (a.from_hour <= hour <= a.to_hour):
                        continue
                    snaps += 1
                    slope_sign = 0
                    anchors = {"call": float(spot), "put": float(spot)}
                    if a.anchor == "pitchfork":
                        pj = project_tines(forks or {}, _mins(ts) or 0)
                        if pj is None:
                            no_fork += 1
                            continue
                        up_c, lo_c, slope_sign, pos_pct = pj
                        anchors = {"call": up_c, "put": lo_c}
                        # (2) OTM GUARD — PER SIDE, not per snapshot. A steeply
                        # rising channel legitimately projects its LOWER tine
                        # above spot by the bell; that kills the put side and
                        # leaves the call side perfectly sellable. v1.1 had no
                        # guard at all and priced short calls below the money;
                        # a per-snapshot guard would over-correct into throwing
                        # away the good side with the bad.
                        ok_side = {"call": up_c > float(spot) * (1 + MIN_OTM_PCT),
                                   "put":  lo_c < float(spot) * (1 - MIN_OTM_PCT)}
                        if not (ok_side["call"] or ok_side["put"]):
                            skip_otm += 1
                            continue
                        # (1) TOUCH TRIGGER — the trade only exists when price
                        # has come to the tine.
                        if a.approach > 0:
                            if pos_pct is None:
                                skip_touch += 1
                                continue
                            touched = {"call": pos_pct >= 100.0 - a.approach,
                                       "put":  pos_pct <= a.approach}
                        else:
                            touched = {"call": True, "put": True}
                        touched = {k: (touched[k] and ok_side[k]) for k in touched}
                        if not (touched["call"] or touched["put"]):
                            skip_touch += 1
                            continue
                    if a.anchor != "pitchfork":
                        touched = {"call": True, "put": True}
                    rows = {}
                    for c in (r.get("contracts") or []):
                        t = str(c.get("type") or "").lower()
                        t = "call" if t.startswith("c") else (
                            "put" if t.startswith("p") else "")
                        if not t:
                            continue
                        try:
                            rows[(t, round(float(c.get("strike")), 4))] = c
                        except Exception:                      # noqa: BLE001
                            continue
                    if not rows:
                        continue
                    strikes = sorted({k[1] for k in rows})
                    for off in OFFSETS:
                        for side in ("call", "put"):
                            if not touched.get(side):
                                continue
                            base = anchors[side]
                            if base <= 0:
                                continue
                            target = (base * (1 + off) if side == "call"
                                      else base * (1 - off))
                            # nearest listed strike at or BEYOND the target —
                            # never inside it, mirroring _select_beyond_floor's
                            # outward bias and its refusal to fall back inward.
                            cand = [s for s in strikes
                                    if (s >= target if side == "call" else s <= target)]
                            if not cand:
                                continue
                            k = min(cand) if side == "call" else max(cand)
                            # OTM guard also applies to the SPOT arm.
                            if (k <= float(spot) * (1 + MIN_OTM_PCT) if side == "call"
                                    else k >= float(spot) * (1 - MIN_OTM_PCT)):
                                skip_otm += 1
                                continue
                            if a.max_spread_pct > 0:
                                sc = rows.get((side, round(k, 4))) or {}
                                b, ak = (sc.get("bid") or 0.0), (sc.get("ask") or 0.0)
                                mid = (b + ak) / 2.0
                                if mid <= 0 or (ak - b) / mid > a.max_spread_pct:
                                    skip_liq += 1
                                    continue
                            pv = price_vertical(rows, side, k, a.width)
                            if pv is None:
                                continue
                            credit, ks, kl = pv
                            loss = settle_loss(side, ks, kl, close, a.width)
                            priced += 1
                            symbol_days.add((date, sym))
                            cells[(off, side)].append((credit, loss))
                            by_hour[hour].append((credit, loss, a.width))
                            if a.anchor == "pitchfork":
                                by_slope[(slope_sign, side)].append((credit, loss))

    print("=" * 84)
    print("  CREDIT EDGE (TC.5) — what a short vertical PAYS, and whether it survives")
    print(f"  anchor: {a.anchor.upper()}"
          + ("  (offsets beyond the TINE PROJECTED TO THE BELL)"
             if a.anchor == "pitchfork" else "  (offsets beyond spot)"))
    print(f"  {len(dates)} session(s) since {a.since}   hours {a.from_hour:02d}-{a.to_hour:02d} ET"
          f"   width {a.width:g}   symbols {len(seen_syms)}")
    print(f"  snapshots in window {snaps:,}   spreads priced {priced:,}"
          f"   symbol-days with no OHLC close {no_close}")
    print(f"  ⚠️ EFFECTIVE n = {len(symbol_days)} SYMBOL-DAYS, not {priced:,} spreads.")
    print(f"     Every spread from one symbol-day shares ONE terminal close and")
    print(f"     snapshots repeat every 5 min on the same underlying. Read every")
    print(f"     n below against {len(symbol_days)}, not against itself.")
    print(f"  skipped — touch {skip_touch:,} · OTM guard {skip_otm:,} ·"
          f" liquidity {skip_liq:,}")
    if a.anchor == "pitchfork":
        print(f"  snapshots with NO projectable fork {no_fork:,} — a fork seen")
        print(f"  ONCE has no derivable slope and is SKIPPED, never projected")
        print(f"  flat. That is UNMEASURED coverage, not an absent fork.")
    print("  credit = short BID - long ASK (you cross both). Loss = exact expiry")
    print("  payoff, capped at width — NOT a full-width loss on every breach.")
    print("=" * 84)
    if not priced:
        print("\n  nothing priced. ABSENT MEASUREMENT, not a null.")
        return 0

    print(f"\n  {'offset':>8}{'side':>6}{'n':>8}{'safe%':>8}{'credit':>9}"
          f"{'cr/width':>10}{'E[loss]':>9}{'EV/spread':>11}{'EV/width':>10}")
    for off in OFFSETS:
        for side in ("call", "put"):
            g = cells.get((off, side)) or []
            if not g:
                continue
            n = len(g)
            safe = sum(1 for c, l in g if l <= 0.0)
            cr = sum(c for c, _ in g) / n
            el = sum(l for _, l in g) / n
            ev = cr - el
            flag = "" if n >= a.min_n else "  <- UNDERPOWERED"
            print(f"  {off*100:>7.2f}%{side:>6}{n:>8}{100.0*safe/n:>7.0f}%"
                  f"{cr:>9.2f}{cr/a.width:>10.2f}{el:>9.2f}"
                  f"{ev:>+11.2f}{ev/a.width:>+10.3f}{flag}")

    print("\n  EV/spread = mean credit - mean expiry loss, in the same units as")
    print("  the premium. POSITIVE is a trade; the offset where EV peaks is the")
    print("  short-strike rule, priced from real quotes rather than a delta.")
    print("  ⚠️ safe% here is not comparable to tcs_floor_durability's terminal")
    print("     rate: that measured distance beyond an IMPULSE FLOOR, this is")
    print("     distance beyond SPOT at snapshot time. Different anchors.")

    print(f"\n  {'-' * 80}\n  BY HOUR (all offsets pooled — is the afternoon actually better?)")
    print(f"  {'hour ET':>9}{'n':>9}{'safe%':>8}{'credit':>9}{'E[loss]':>9}{'EV/spread':>11}")
    for hour in sorted(by_hour):
        g = by_hour[hour]
        n = len(g)
        safe = sum(1 for c, l, w in g if l <= 0.0)
        cr = sum(c for c, _, _ in g) / n
        el = sum(l for _, l, _ in g) / n
        flag = "" if n >= a.min_n else "  <- UNDERPOWERED"
        print(f"  {hour:>7}:00{n:>9}{100.0*safe/n:>7.0f}%{cr:>9.2f}{el:>9.2f}"
              f"{cr-el:>+11.2f}{flag}")
    print("\n  Pooling offsets flatters nothing — it is the same ladder in every")
    print("  hour. A rising EV by hour is the operator's theta argument made")
    print("  numeric: less clock left means less chance to travel to the strike.")

    if a.anchor == "pitchfork" and by_slope:
        print(f"\n  {'-' * 80}\n  SLOPE x SIDE — the operator's leg-ordering rule, tested")
        print(f"  {'slope':>8}{'side':>6}{'n':>9}{'safe%':>8}{'credit':>9}"
              f"{'E[loss]':>9}{'EV/spread':>11}")
        for sign in (1, 0, -1):
            for side in ("call", "put"):
                g = by_slope.get((sign, side)) or []
                if not g:
                    continue
                n = len(g)
                safe = sum(1 for c, l in g if l <= 0.0)
                cr = sum(c for c, _ in g) / n
                el = sum(l for _, l in g) / n
                nm = {1: "up", 0: "flat", -1: "down"}[sign]
                flag = "" if n >= a.min_n else "  <- UNDERPOWERED"
                print(f"  {nm:>8}{side:>6}{n:>9}{100.0*safe/n:>7.0f}%{cr:>9.2f}"
                      f"{el:>9.2f}{cr-el:>+11.2f}{flag}")
        print("\n  THE PREDICTION: on an UP slope the PUT side should price better")
        print("  (the channel rises away from a fixed short put) and the CALL")
        print("  side worse; on a DOWN slope, mirrored. If that asymmetry is not")
        print("  here, the slope is not doing the work the ordering rule assumes.")

    print(f"\n{'=' * 84}")
    print("  WHAT THIS DOES NOT DO: model management, a stop, a roll, early")
    print("  assignment, commission, or a fill worse than the posted bid. It")
    print("  prices the trade AS PROPOSED — sold and held to the bell.")
    print("  NEXT ANCHOR CANDIDATES (this run uses SPOT): the pitchfork observer")
    print("  journals `upper`/`median`/`lower` TINE PRICES per timeframe, and")
    print("  VWAP has banked correctly since the v1.5 bake (VW.2 closed 08-08).")
    print("  Both are drop-in replacements for the spot anchor once their")
    print("  coverage supports it — the pitchfork's starts 2026-08-12.")
    print("=" * 84)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
