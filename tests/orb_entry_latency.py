#!/usr/bin/env python3
"""
tests/orb_entry_latency.py — v1.1 — 2026-08-08

v1.1 — 2026-08-08 — TWO CLOCKS, ONE COMPARISON. The first live run over 12
       sessions paired 95 of 102 ORB trades and then binned ALL 95 as
       out-of-window outliers, leaving `clean` empty and dividing by zero.
       Cause: `entry_time` is written by `ts_for_db()` = `now_utc().isoformat()`
       — UTC — while the journal's `ts_et` is ET. v1.0 called
       `.replace(tzinfo=None)` on both, which STRIPS the offsets rather than
       reconciling them, so every latency came out +4h. `trade_logger.py:66`
       carries an explicit warning about comparing a UTC field against an ET
       clock, and it was read earlier the same day.
       Fixed: every stamp is parsed to an AWARE datetime with the correct
       per-source default (trades UTC, journal ET) and compared in absolute
       time. Also, an empty sample now REFUSES WITH A DIAGNOSIS instead of
       crashing — a tight cluster a whole number of hours from zero is named as
       a clock mismatch, because a real latency distribution cannot look like
       that, and "every entry precedes every retest" is reported as the clock
       signature it is rather than as a missing journal.
       ⚠️ THE LESSON: the 95-outlier line was doing its job — the header already
       said "if this count is large, emit the candle ts before trusting any of
       this." A guard that fires correctly is worthless if the tool crashes
       before the reader can act on it.

WHAT THIS ANSWERS
    The ORB retest rule is evaluated on the last CLOSED 1-minute candle
    (`orb_engine.update` -> `df_1m.iloc[-2]`), but the tick loop polls on a
    15-second cadence with FREE-RUNNING PHASE — `main.py` sleeps
    `max(0, POLL_INTERVAL_SECONDS - elapsed)`, counted from whenever that bot
    process started. So the delay between "the qualifying candle closed" and
    "the order went in" is uniform 0-15s, it differs box to box, and it
    RESETS ON EVERY RESTART.

    Operator's concern, and it is the right one: that delay is paid as a worse
    entry — a higher premium on the long contract and a wider risk leg on the
    same stop.

    This measures it. Four numbers per trade, then the one test that decides
    whether the latency is worth engineering away.

THE TEST THAT DECIDES IT — is the slip SYSTEMATICALLY ADVERSE, or symmetric?
    If entry slip is a coin flip around zero, 15 seconds costs VARIANCE, not
    expectancy, and phase-locking the tick is tidiness. If it is systematically
    adverse, it is a real drain on every ORB trade and the fix pays for itself.
    There is a MECHANISM to expect adverse — a confirmed retest means price
    rejected the level and is resuming the break direction, so the next 15
    seconds of that move are against your fill BY CONSTRUCTION — but a
    mechanism is a hypothesis, and the whole point of measuring is to let it
    be wrong.

THE FREE-RUNNING PHASE IS AN ACCIDENTAL NATURAL EXPERIMENT — USE IT
    Because each box's offset is arbitrary and resets on restart, the sample
    already contains a spread of latencies. So this does not just report a
    mean: it REGRESSES adverse slip on measured latency. If slip grows with
    delay, causation is pinned down rather than inferred, and the fix is
    justified by evidence instead of by argument. If the slope is flat, the
    latency is not what is hurting you and the engineering should go elsewhere.

    NOTE the regression is observational, not randomised. Latency correlates
    with tick phase, which correlates with nothing else obvious — but a
    confound (e.g. faster-moving tapes finishing ticks later) is not excluded.
    Read a positive slope as strong support, never as proof.

HOW THE QUALIFYING CANDLE IS IDENTIFIED
    `retest_check` (orb_engine v3.7) emits, for EVERY 1-minute candle examined
    while ARMED, the candle OHLC plus `retest_depth_px` and `direction`. It
    does NOT emit orb_high/orb_low — but it does not need to, because the depth
    IS the level:
        long:  depth = orb_high - low   =>  orb_high = low + depth
        short: depth = high - orb_low   =>  orb_low  = high - depth
    So the confirm rule (`orb_engine.py:620/652`) is reconstructable exactly:
        long:  depth > 0 AND min(open, close) >= low + depth
        short: depth > 0 AND max(open, close) <= high - depth
    This is the SAME arithmetic the engine ran, not an approximation of it.

⚠️ THE ONE INFERENCE IN HERE, STATED PLAINLY
    `retest_check` records the candle's PRICES but not the candle's own
    TIMESTAMP — only the journal record's emission time. The examined candle is
    `iloc[-2]`, the last closed one, so its close is taken as the emission time
    FLOORED TO THE MINUTE. That is right whenever the newer bar had already
    landed, which on a liquid tape is sub-second. On a quiet symbol where no
    candle event has yet arrived for the new minute, `iloc[-2]` is one bar older
    and this inference is 60s wrong.
    Rather than hide that, every trade's latency is printed and anything over
    LATENCY_OUTLIER_S is REPORTED SEPARATELY and EXCLUDED from the regression —
    so a bad inference shows up as an outlier instead of quietly inflating the
    mean. If the outlier count is large, the emitter should carry the candle
    timestamp (a one-line fix in orb_engine) before this analysis is trusted.

READ-ONLY. stdlib only. Touches no fleet, no live path, and nothing it reads.

USAGE (control server)
    python3 tests/orb_entry_latency.py 2026-08-05 2026-08-06 2026-08-07
    python3 tests/orb_entry_latency.py --since 2026-07-23
"""

import glob
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

# v1.1 — THE TWO CLOCKS. `entry_time` is written by `ts_for_db()` =
# `now_utc().isoformat()`, i.e. UTC. The journal's `ts_et` is ET. v1.0 called
# .replace(tzinfo=None) on both, which STRIPS the offsets instead of
# reconciling them, so every latency came out +4h and all 95 paired trades
# were binned as outliers -> `clean` empty -> ZeroDivisionError. Both are now
# made timezone-AWARE with the correct default and compared in absolute time.
ET_TZ  = timezone(timedelta(hours=-4))   # journal stamps carry their own offset;
                                         # this is only the naive-string fallback
UTC_TZ = timezone.utc

JOURNAL_ROOT = os.path.expanduser("~/day_trader_pro/signal_journal")
REPORTS_ROOT = os.path.expanduser("~/day_trader_pro/reports")

LATENCY_OUTLIER_S = 25.0   # above this the candle-time inference is suspect
MIN_N             = 12     # below this: counts only, no slope, no verdict
CONTRACT_MULT     = 100


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_ts(v, default_tz=None):
    """Parse to an AWARE datetime. A naive string gets `default_tz` — never
    silently compared against a stamp from the other clock."""
    if v is None:
        return None
    s = str(v).strip().replace("Z", "+00:00")
    dt = None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(s[:19], fmt)
                break
            except ValueError:
                continue
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=default_tz or UTC_TZ)
    return dt


def load_journal_retests(dates):
    """(symbol, date) -> [qualifying retest dicts], chronological."""
    out = defaultdict(list)
    examined = 0
    for d in dates:
        for path in sorted(glob.glob(os.path.join(JOURNAL_ROOT, d, "*.jsonl"))):
            sym = os.path.basename(path).split(".")[0].upper()
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:                     # noqa: BLE001
                        continue
                    if str(r.get("event", "")) != "retest_check":
                        continue
                    orb = r.get("orb") or {}
                    c = orb.get("candle") or {}
                    o, h, l, cl = (_f(c.get("open")), _f(c.get("high")),
                                   _f(c.get("low")), _f(c.get("close")))
                    depth = _f(orb.get("retest_depth_px"))
                    direc = str(orb.get("direction") or "").lower()
                    if None in (o, h, l, cl, depth) or direc not in ("long", "short"):
                        continue
                    examined += 1
                    # Reconstruct the engine's own confirm test. The level comes
                    # from the depth, so this is the same arithmetic, not a proxy.
                    if direc == "long":
                        qualifies = depth > 0 and min(o, cl) >= (l + depth)
                    else:
                        qualifies = depth > 0 and max(o, cl) <= (h - depth)
                    if not qualifies:
                        continue
                    # journal stamps are ET; naive ones default to ET, NOT UTC
                    ts = _parse_ts(r.get("ts_et") or r.get("ts"), ET_TZ)
                    if ts is None:
                        continue
                    out[(sym, d)].append({
                        "emit_ts":     ts,
                        "close_t":     ts.replace(second=0, microsecond=0),
                        "close_px":    cl,
                        "direction":   direc,
                        "depth":       depth,
                        "orb_width":   _f(orb.get("orb_width")),
                        "attempt":     orb.get("attempt"),
                    })
    for k in out:
        out[k].sort(key=lambda x: x["emit_ts"])
    return out, examined


def load_orb_trades(dates):
    rows = []
    for d in dates:
        p = os.path.join(REPORTS_ROOT, f"fleet_trades_{d}.json")
        if not os.path.isfile(p):
            continue
        try:
            data = json.load(open(p, encoding="utf-8"))
        except Exception as exc:                          # noqa: BLE001
            print(f"  ! unreadable {p}: {exc}")
            continue
        recs = data if isinstance(data, list) else (
            data.get("trades") or data.get("rows") or [])
        if isinstance(recs, dict):
            recs = list(recs.values())
        for t in recs:
            if not isinstance(t, dict):
                continue
            if str(t.get("strategy", "")).upper() != "ORBSTRATEGY":
                continue
            t["_date"] = d
            rows.append(t)
    return rows


def pair(trades, retests):
    """Attach each ORB trade to the last qualifying retest before its entry."""
    paired, unmatched = [], defaultdict(int)
    for t in trades:
        sym = str(t.get("symbol", "")).upper()
        # trade rows are UTC (ts_for_db -> now_utc().isoformat())
        entry_t = _parse_ts(t.get("entry_time"), UTC_TZ)
        if entry_t is None:
            unmatched["no parseable entry_time"] += 1
            continue
        cands = retests.get((sym, t["_date"]))
        if not cands:
            unmatched["no qualifying retest in journal for that symbol/date"] += 1
            continue
        et = entry_t                       # aware; compared in absolute time
        prior = [c for c in cands
                 if c["emit_ts"] <= et + timedelta(seconds=5)]
        if not prior:
            unmatched["every qualifying retest is AFTER the entry"] += 1
            continue
        c = prior[-1]
        u_entry = _f(t.get("underlying_entry"))
        if u_entry is None:
            unmatched["trade row has no underlying_entry"] += 1
            continue
        latency = (et - c["close_t"]).total_seconds()
        raw = u_entry - c["close_px"]
        adverse = raw if c["direction"] == "long" else -raw
        paired.append({
            "symbol": sym, "date": t["_date"], "direction": c["direction"],
            "latency": latency, "close_px": c["close_px"], "u_entry": u_entry,
            "adverse": adverse,
            "delta": _f(t.get("entry_delta")),
            "premium": _f(t.get("entry_premium")),
            "stop": _f(t.get("underlying_stop")),
            "pnl": _f(t.get("pnl_usd")),
        })
    return paired, unmatched


def _pct(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[i]


def _ols(xs, ys):
    """slope, intercept, pearson r — stdlib, no numpy."""
    n = len(xs)
    if n < 3:
        return None, None, None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx == 0 or syy == 0:
        return None, None, None
    slope = sxy / sxx
    return slope, my - slope * mx, sxy / math.sqrt(sxx * syy)


def main(argv):
    dates = [a for a in argv[1:] if not a.startswith("--")]
    if not dates:
        print(__doc__.strip().split("USAGE")[1].strip())
        return 2

    retests, examined = load_journal_retests(dates)
    trades = load_orb_trades(dates)
    print(f"dates: {', '.join(dates)}")
    print(f"retest_check records examined: {examined}   "
          f"qualifying: {sum(len(v) for v in retests.values())}   "
          f"ORB trades: {len(trades)}")

    paired, unmatched = pair(trades, retests)
    if unmatched:
        print("\n--- ORB trades NOT paired, BY CAUSE ---")
        for why in sorted(unmatched):
            print(f"    {unmatched[why]:>5}  {why}")
    if not paired:
        # v1.1 — name the cause instead of guessing at it. "every qualifying
        # retest is AFTER the entry" across the whole sample is a CLOCK
        # SIGNATURE, not a data gap, and saying "missing journal" there sends
        # the reader to the wrong place entirely.
        if unmatched.get("every qualifying retest is AFTER the entry", 0) >= max(3, len(trades) // 2):
            print("\n⇒ Every entry precedes every qualifying retest. That is "
                  "impossible in market time, so it is a CLOCK MISMATCH between "
                  "\n  the trade rows (UTC, via ts_for_db) and the journal "
                  "(ET). Check both stamps before anything else.")
        else:
            print("\nNothing to measure. If the journal files are absent, the "
                  "dates were not harvested to control.")
        return 1

    clean = [p for p in paired if 0 <= p["latency"] <= LATENCY_OUTLIER_S]
    outl  = [p for p in paired if not (0 <= p["latency"] <= LATENCY_OUTLIER_S)]

    # v1.1 — REFUSE, do not divide. v1.0 crashed with ZeroDivisionError when
    # every trade fell outside the window, which is the case that most needed a
    # diagnosis printed. An empty `clean` is a FINDING about the clock, not an
    # arithmetic accident: the raw latency spread below names the cause, because
    # a tight cluster near a whole number of hours is a timezone error, while a
    # broad scatter is genuinely late entries.
    if not clean:
        raw = sorted(p["latency"] for p in paired)
        print(f"\n--- LATENCY ---")
        print(f"    n={len(raw)}  ALL outside 0-{LATENCY_OUTLIER_S:.0f}s. "
              f"min={raw[0]:+.1f}s  p50={_pct(raw,0.5):+.1f}s  max={raw[-1]:+.1f}s")
        spread = raw[-1] - raw[0]
        near_hr = abs(round(raw[0] / 3600.0) * 3600.0 - raw[0])
        if spread < 900 and near_hr < 300 and abs(raw[0]) > 1800:
            print(f"    ⇒ CLOCK MISMATCH, not slow entries: the whole sample sits "
                  f"~{raw[0]/3600.0:+.1f}h off with only {spread:.0f}s of spread. "
                  f"A real latency distribution cannot look like this.")
        else:
            print(f"    ⇒ Spread is {spread:.0f}s — inspect a few trades by hand "
                  f"before assuming a clock problem.")
        print("\nRefusing to report slip, premium or a slope off a sample whose "
              "\ntimestamps do not line up. Nothing below would mean anything.")
        return 1

    print(f"\n--- LATENCY: qualifying candle close -> order in ---")
    lat = [p["latency"] for p in clean]
    if lat:
        print(f"    n={len(lat)}  min={min(lat):.1f}s  p50={_pct(lat,0.5):.1f}s  "
              f"p90={_pct(lat,0.9):.1f}s  max={max(lat):.1f}s  "
              f"mean={sum(lat)/len(lat):.1f}s")
        print(f"    (expected under a free-running 15s phase: ~uniform 0-15s, "
              f"mean ~7.5s)")
    if outl:
        print(f"    ⚠ {len(outl)} trade(s) outside 0-{LATENCY_OUTLIER_S:.0f}s — "
              f"EXCLUDED from the slope below. These are most likely the "
              f"candle-timestamp inference failing on a quiet tape (see header), "
              f"NOT real 60s entries. If this count is large, emit the candle ts "
              f"in orb_engine before trusting any of this.")

    print(f"\n--- SLIP: adverse price movement paid at entry (underlying) ---")
    adv = [p["adverse"] for p in clean]
    n_adv = sum(1 for a in adv if a > 0)
    print(f"    mean={sum(adv)/len(adv):+.4f}   p50={_pct(adv,0.5):+.4f}   "
          f"p90={_pct(adv,0.9):+.4f}")
    print(f"    adverse on {n_adv}/{len(adv)} trades ({100.0*n_adv/len(adv):.0f}%)"
          f"   — 50% means a coin flip, i.e. variance not expectancy")

    prem = [abs(p["adverse"]) * abs(p["delta"]) * CONTRACT_MULT
            for p in clean if p["delta"]]
    if prem:
        print(f"\n--- PREMIUM COST (|slip| x |entry_delta| x {CONTRACT_MULT}) ---")
        print(f"    n={len(prem)}  mean=${sum(prem)/len(prem):.2f}/contract   "
              f"p90=${_pct(prem,0.9):.2f}   total=${sum(prem):.2f}")
        print(f"    NOTE this is the DELTA-IMPLIED cost of the underlying move "
              f"only. It is NOT the spread — entry_premium is MARK, so any "
              f"cross-the-spread cost is a separate and additive question.")

    widen = []
    for p in clean:
        if p["stop"] is None:
            continue
        r0 = abs(p["close_px"] - p["stop"])
        r1 = abs(p["u_entry"] - p["stop"])
        if r0 > 0:
            widen.append(100.0 * (r1 - r0) / r0)
    if widen:
        print(f"\n--- RISK LEG: stop distance widening (same stop, worse entry) ---")
        print(f"    n={len(widen)}  mean={sum(widen)/len(widen):+.1f}%   "
              f"p90={_pct(widen,0.9):+.1f}%")
        print(f"    A wider risk leg on an unchanged target is a straight "
              f"reduction in R:R — this is the operator's concern, quantified.")

    print(f"\n{'='*70}")
    print("  DOES SLIP GROW WITH LATENCY?  (the question that decides the fix)")
    print(f"{'='*70}")
    if len(clean) < MIN_N:
        print(f"  INSUFFICIENT — {len(clean)} paired trades, need {MIN_N}. "
              f"Counts above stand; no slope, no verdict.")
    else:
        slope, _, r = _ols([p["latency"] for p in clean], adv)
        if slope is None:
            print("  Degenerate — no variation in latency or slip.")
        else:
            print(f"  slope = {slope:+.5f} underlying-px per second of delay   "
                  f"(r = {r:+.3f}, n = {len(clean)})")
            print(f"  implied cost of the full 15s window: "
                  f"{slope*15:+.4f} px")
            if slope > 0 and r > 0.25:
                print("  -> SLIP GROWS WITH DELAY. The latency is being paid. "
                      "Phase-locking the tick is justified on evidence.")
            elif abs(r) <= 0.25:
                print("  -> NO RELATIONSHIP VISIBLE. The slip may be real but "
                      "the DELAY is not what is driving it — phase-locking "
                      "would not recover it. Look at the spread instead.")
            else:
                print("  -> SLIP SHRINKS WITH DELAY. Unexpected; suspect a "
                      "confound before acting on it.")

    print("\n  Reminder: this licenses a DESIGN REVIEW, not a dial. Any change to "
          "\n  entry timing is a BEHAVIOUR change — deploy Monday, and the freeze "
          "\n  window opens Mon Aug 17.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
