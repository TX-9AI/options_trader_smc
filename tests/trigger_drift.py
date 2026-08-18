#!/usr/bin/env python3
"""
tests/trigger_drift.py — v1.0 — 2026-08-07

FORWARD DRIFT CONDITIONED ON THE ENTRY TRIGGER, NOT ON THE REGIME LABEL —
with ORB as a POSITIVE CONTROL.

WHY THIS EXISTS, and it is a correction to how the previous measurement was
read. `a2_cooccurrence` measures forward drift from LABEL STATES and finds
nothing anywhere: every bucket, every horizon, inside +/-0.03%. It was about to
be treated as "the regime label carries no directional edge" — but that tool has
only a NULL control (RANGE_ONLY). **There is no bucket in it that we KNOW
carries edge, so it has never been shown capable of detecting one.**

ORB nets **+$10,156 over 12 sessions** (118 trades, 47% win). Drift after an ORB
break must therefore be visible. If this tool cannot see the one strategy we
know works, the INSTRUMENT is wrong — wrong horizon, wrong signing, wrong
sampling — and no conclusion drawn from label-state drift stands. That is what
this measures first, and it is the only reason the rest of the output means
anything.

WHAT IT DOES. Every CLOSED TRADE is a trigger event that actually fired. For
each one it takes the entry timestamp, finds that symbol-day's price series in
the replay corpus, and measures the signed forward change at several horizons —
SIGNED BY THE TRADE'S OWN DIRECTION, so a profitable short reads positive.
Buckets by `setup_type`, so `ORB Short` / `ORB Long` are the control arms and
`trend_continuation_handoff` / `_standalone` / `Sweep Reversal Long` are the
comparisons.

⚠️ THE HORIZON IS NOT THE HOLD. This deliberately ignores the exit: it asks
"what did the underlying do in the N minutes after this trigger", not "what did
we make". A trigger can carry real drift and still lose money to a bad stop —
that separation is the entire point, and it is why this cannot be read off
MFE/MAE, which are premium-based and bounded by the exit.

⚠️ TIMEZONE — the trap that has already inverted one verdict in this repo.
`entry_time` is stored UTC (trade_logger's own comment says so, deliberately);
the replay corpus stamps `ts` as ET wall-clock "HH:MM". Converting with
`zoneinfo` rather than a fixed offset, because a fixed −4/−5 is wrong on one
side of every DST boundary. Trades whose converted minute has no matching tick
are DROPPED and COUNTED, never snapped to a neighbour.

⚠️ THE RANDOM ARM IS THE NULL. Drift is also measured from randomly chosen
ticks on the same symbol-days. Without it, "ORB drifts +0.05%" is unreadable —
the question is whether it drifts MORE than an arbitrary moment on the same
tape. Seeded, so the null is reproducible.

Read-only, stdlib only, streams one file at a time, always exits 0.
USAGE
    python3 tests/trigger_drift.py
    python3 tests/trigger_drift.py --horizons 10,20,30 --since 2026-07-23

CHANGELOG
  v1.0 — 2026-08-07 — first issue, built specifically to give the drift
         measurement a positive control before any conclusion is drawn from it.
"""

import argparse
import collections
import glob
import json
import os
import random
import re
import sqlite3
import sys
from datetime import datetime, timedelta

REPLAY_GLOB = "~/day_trader_pro/reports/regime_replay_*.jsonl"
TRADES_GLOB = "~/day_trader_pro/trades/*/*.db"
DATE_RE = re.compile(r"regime_replay_(20\d\d-\d\d-\d\d)\.jsonl$")
TRADE_DATE_RE = re.compile(r"/trades/(20\d\d-\d\d-\d\d)/")

try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except Exception:                                                # noqa: BLE001
    _ET = None


def _to_et_hhmm(entry_time: str):
    """UTC ISO -> 'HH:MM' ET, or None. Never guesses an offset."""
    if not entry_time:
        return None
    t = str(entry_time).strip().replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(t)
    except Exception:                                            # noqa: BLE001
        return None
    if d.tzinfo is None:
        from datetime import timezone
        d = d.replace(tzinfo=timezone.utc)
    if _ET is None:
        return None            # refuse rather than apply a fixed offset
    return d.astimezone(_ET).strftime("%H:%M")


def _pct(sv, p):
    if not sv:
        return 0.0
    return sv[min(len(sv) - 1, int(round(p / 100.0 * (len(sv) - 1))))]


def _med(v):
    return _pct(sorted(v), 50)


def load_prices(paths):
    """(date, sym) -> [(hhmm, price)] in file order."""
    out = collections.defaultdict(list)
    for path in paths:
        date = DATE_RE.search(path).group(1)
        for line in open(path, errors="ignore"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:                                    # noqa: BLE001
                continue
            ts, sym, px = r.get("ts"), r.get("sym"), r.get("price")
            if ts and sym and px:
                out[(date, sym)].append((ts, float(px)))
    return out


def load_triggers(since, tglob):
    """[(date, sym, hhmm, dir_sign, setup_type)] from every closed trade."""
    rows, skipped_tz, skipped_cols = [], 0, 0
    for db in sorted(glob.glob(os.path.expanduser(tglob))):
        m = TRADE_DATE_RE.search(db)
        if not m or (since and m.group(1) < since):
            continue
        date = m.group(1)
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            cur = con.execute(
                "SELECT symbol, entry_time, direction, setup_type FROM trades")
            fetched = cur.fetchall()
            con.close()
        except Exception:                                        # noqa: BLE001
            skipped_cols += 1
            continue
        for sym, et, dirn, stype in fetched:
            hhmm = _to_et_hhmm(et)
            if hhmm is None:
                skipped_tz += 1
                continue
            sign = -1.0 if str(dirn or "").lower().startswith("short") else 1.0
            rows.append((date, sym, hhmm, sign, (stype or "?").strip()))
    return rows, skipped_tz, skipped_cols


def drift_at(series, idx, h, sign):
    j = idx + h
    if j >= len(series):
        return None
    p0, p1 = series[idx][1], series[j][1]
    if p0 <= 0:
        return None
    return sign * (p1 - p0) / p0 * 100.0


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default=REPLAY_GLOB)
    ap.add_argument("--since", default="")
    ap.add_argument("--trades", default=TRADES_GLOB,
                    help="glob for the per-symbol trade DBs")
    ap.add_argument("--horizons", default="10,20,30")
    ap.add_argument("--min-n", type=int, default=15)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args(argv[1:])
    horizons = [int(h) for h in a.horizons.split(",") if h.strip().isdigit()]

    paths = [p for p in sorted(glob.glob(os.path.expanduser(a.glob)))
             if DATE_RE.search(p)
             and (not a.since or DATE_RE.search(p).group(1) >= a.since)]
    if not paths:
        print(f"no replay files matched {a.glob}")
        return 0

    prices = load_prices(paths)
    trigs, skip_tz, skip_db = load_triggers(a.since, a.trades)
    if not trigs:
        print(f"no trade rows found under {a.trades}")
        return 0

    # index each symbol-day's ts -> position (first occurrence wins)
    pos = {}
    for key, series in prices.items():
        d = {}
        for i, (ts, _p) in enumerate(series):
            d.setdefault(ts, i)
        pos[key] = d

    by = {h: collections.defaultdict(list) for h in horizons}
    matched = unmatched = 0
    for date, sym, hhmm, sign, stype in trigs:
        key = (date, sym)
        series = prices.get(key)
        idx = pos.get(key, {}).get(hhmm)
        if series is None or idx is None:
            unmatched += 1
            continue
        matched += 1
        for h in horizons:
            d = drift_at(series, idx, h, sign)
            if d is not None:
                by[h][stype].append(d)

    # NULL ARM — random ticks on the same symbol-days, both directions
    rng = random.Random(a.seed)
    keys = [k for k in prices if len(prices[k]) > max(horizons) + 5]
    for _ in range(max(400, matched)):
        k = rng.choice(keys)
        i = rng.randrange(0, len(prices[k]) - max(horizons) - 1)
        sgn = rng.choice((1.0, -1.0))
        for h in horizons:
            d = drift_at(prices[k], i, h, sgn)
            if d is not None:
                by[h]["~RANDOM (null arm)"].append(d)

    print(f"replay sessions: {len(paths)}   trade triggers: {len(trigs)}   "
          f"matched to tape: {matched}   unmatched: {unmatched}")
    if skip_tz or skip_db:
        print(f"  dropped: {skip_tz} unparseable/naive entry_time, "
              f"{skip_db} unreadable DB(s)")
    if _ET is None:
        print("  ⚠️ zoneinfo unavailable — REFUSED to guess a UTC offset, so no")
        print("  ⚠️ trigger could be matched. Install tzdata and re-run.")

    print()
    print("=== READ THE ORB ROWS FIRST — THEY ARE THE POSITIVE CONTROL ===")
    print("  ORB nets +$10,156 over 12 sessions. If ORB does not drift more")
    print("  than the random arm, THIS INSTRUMENT CANNOT DETECT EDGE and no")
    print("  conclusion from label-state drift (a2_cooccurrence) survives.")

    for h in horizons:
        print(f"\n  horizon +{h} bars (~{h} min), signed by trade direction")
        print(f"    {'setup_type':<34}{'n':>6}{'median %':>11}{'mean %':>10}"
              f"{'>0 %':>8}")
        rows = sorted(by[h].items(), key=lambda kv: -_med(kv[1]))
        for stype, vals in rows:
            if not vals:
                continue
            n = len(vals)
            mean = sum(vals) / n
            up = 100.0 * sum(1 for v in vals if v > 0) / n
            thin = "  <- thin" if n < a.min_n else ""
            print(f"    {stype[:34]:<34}{n:>6}{_med(vals):>11.3f}"
                  f"{mean:>10.3f}{up:>7.0f}%{thin}")

    print()
    print("  SIGNED BY DIRECTION: a short whose underlying FELL reads POSITIVE.")
    print("  The horizon is NOT the hold — this ignores the exit deliberately,")
    print("  so a trigger can drift well and still have lost money. That gap is")
    print("  the point: it separates a bad ENTRY from a bad EXIT, which MFE/MAE")
    print("  cannot do because they are premium-based and bounded by the exit.")
    print("  The RANDOM arm is the null: read every row AGAINST it, never alone.")
    return 0


if __name__ == "__main__":
    try:
        rc = main(sys.argv)
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        rc = 0
    sys.exit(rc)
