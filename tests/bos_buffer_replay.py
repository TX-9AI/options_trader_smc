#!/usr/bin/env python3
"""
tests/bos_buffer_replay.py — v1.1 — 2026-08-08

v1.1 — tape index normalised to NAIVE ET inside load_tape. Harvest CSVs are
       tz-aware (UTC-04:00) while the operator's exported tapes are naive, so
       the first live run raised "Cannot compare tz-naive and tz-aware" the
       moment it found real tape. Normalising at the BOUNDARY rather than at
       each comparison means every site downstream has one guarantee instead of
       a tz question. Also: --tapes default corrected to ~/day_trader_pro/ohlc,
       which is where the tape actually lives — `data/harvest` was inferred from
       a variable name in replay_confluence, not read off disk.

Prices the two proposals against each other on the SAME trades:
  A. BUFFERED BOS      — protected level padded by k*ATR, still armed at all times
  B. PROFIT-GATED BOS  — BOS disarmed until pnl > 0, with a premium floor catching
                         everything below

WHY A REPLAY AND NOT A QUERY. Stored MFE/MAE cannot answer this. MFE is measured
over the life the CURRENT exit produced, so a trade killed two minutes in has an
MFE that reflects the killing. Asking "would it have survived" requires re-running
the tracker over the 1m tape, which is what this does.

THE DEFECT BEING PRICED
    `BOSTracker.__init__` sets peak_close = entry_price, protected_level = None.
    The level is therefore established by THE FIRST 1m CANDLE THAT CLOSES ABOVE
    ENTRY, and is set to that candle's LOW — with no buffer of any kind.
    Continuation enters on a pullback into an unfilled FVG, so the first candle
    back above entry is by construction the SMALLEST, EARLIEST part of the
    resumption, and its low sits a hair under the entry. The next ordinary wiggle
    closes below it and BOS fires. The invalidation level is an accident of
    candle geometry, not a decision.

WHAT IT REPORTS
    1. CANDLE-B DEATHS — trades where the buffered level would have SURVIVED the
       candle that actually killed them. This is the size of the prize.
    2. For those survivors, what happened NEXT — forward move at fixed horizons
       from the actual exit, so the answer does not depend on how the trade was
       later managed. If they died anyway, the buffer only delays the funeral.
    3. THE COST, paid on every BOS exit: extra adverse travel between the raw
       level and the buffered one, converted to premium via entry_delta.
    4. THE PROFIT-GATE POPULATION — trades that never went positive. These are
       exactly what proposal B releases, with their actual MAE, so the deeper
       tail can be priced instead of assumed.

⚠️ APPROXIMATIONS, STATED UP FRONT
    - BOS operates on the UNDERLYING, so the tracker replay is exact.
    - Premium is NOT in the tape. Anything expressed in premium terms here is
      delta-approximated (move * entry_delta * 100) and is a FIRST-ORDER
      estimate that ignores gamma, theta and spread. On 0DTE that understates
      both directions. Read premium figures as ORDERS OF MAGNITUDE.
    - No fills, no spread. A level that survives is not a fill that happened.

READ-ONLY. Touches no fleet, no live path, writes nothing.

USAGE (control)
    python3 tests/bos_buffer_replay.py --tapes ~/day_trader_pro/data/harvest \\
            2026-07-23 2026-07-24 ... 2026-08-07
    python3 tests/bos_buffer_replay.py --tapes DIR --buffer 0.5 --horizons 5,15,30 DATES...
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

REPORTS_ROOT = os.path.expanduser("~/day_trader_pro/reports")
UTC = timezone.utc
ET  = timezone(timedelta(hours=-4))


def _ts(v, default_tz):
    """Parse to an AWARE datetime. trade rows are UTC (ts_for_db); tape is ET."""
    if v is None:
        return None
    s = str(v).strip().replace("Z", "+00:00")
    dt = None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(s[:19], f)
                break
            except ValueError:
                continue
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=default_tz)


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_tape(tape_dir, sym):
    """1m OHLC for one symbol. Accepts <SYM>*.csv (any suffix)."""
    hits = []
    for pat in (f"{sym}*.csv", f"_{sym}*.csv", f"{sym}*.CSV"):
        hits += glob.glob(os.path.join(tape_dir, "**", pat), recursive=True)
    if not hits:
        return None
    frames = []
    for p in sorted(set(hits)):
        try:
            raw = pd.read_csv(p)
        except Exception:                                     # noqa: BLE001
            continue
        raw.columns = [c.strip().lower() for c in raw.columns]
        tcol = next((c for c in ("timestamp", "time", "date", "datetime")
                     if c in raw.columns), None)
        if tcol is None:
            continue
        idx = pd.to_datetime(raw[tcol], errors="coerce", utc=False)
        raw = raw[idx.notna()].copy()
        raw.index = pd.DatetimeIndex(idx[idx.notna()])
        for c in ("open", "high", "low", "close"):
            if c not in raw.columns:
                raw = None
                break
            raw[c] = pd.to_numeric(raw[c], errors="coerce")
        if raw is None:
            continue
        frames.append(raw[["open", "high", "low", "close"]].dropna())
    if not frames:
        return None
    df = pd.concat(frames).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    # v1.1 — NORMALISE THE INDEX TO NAIVE ET AT THE BOUNDARY.
    # Harvest tapes carry an offset (datetime64[us, UTC-04:00]); the operator's
    # exported CSVs are naive ET. Mixing them against the naive ET stamps built
    # from the (UTC) trade rows raises "Cannot compare tz-naive and tz-aware".
    # Converting ONCE here, rather than at each comparison, is the fix — every
    # comparison site downstream then has one guarantee to rely on instead of a
    # tz question to re-answer. Third timezone defect in this codebase today,
    # all from reconciling clocks at the point of USE instead of at the point of
    # ENTRY.
    try:
        if getattr(df.index, "tz", None) is not None:
            df.index = df.index.tz_convert(ET).tz_localize(None)
    except (TypeError, AttributeError):
        pass
    return df


def atr_at(df, when, n=14):
    """Simple 1m ATR over the n bars ending at `when`. None if too little tape."""
    win = df[df.index <= when].tail(n + 1)
    if len(win) < 5:
        return None
    tr = []
    prev = None
    for _, r in win.iterrows():
        if prev is not None:
            tr.append(max(r["high"] - r["low"], abs(r["high"] - prev),
                          abs(r["low"] - prev)))
        prev = r["close"]
    return (sum(tr) / len(tr)) if tr else None


def replay_bos(df, entry_t, entry_px, direction, buffer_px, until_t):
    """Re-run BOSTracker semantics. Returns (fired_at, level_at_fire) or (None, None).

    Faithful to execution/exit_engine.BOSTracker: peak seeded at entry_price,
    protected level = the low (long) / high (short) of the candle that made a new
    closing extreme, tested on CLOSED candles only. The ONLY difference is the
    pad — and the pad is RATCHETED (max for longs, min for shorts) because
    level = low - k*ATR is NOT monotone: if ATR expands between candles a new
    level can come out LOWER than the old one, silently loosening the stop
    exactly when volatility rises.
    """
    seg = df[(df.index > entry_t) & (df.index <= until_t)]
    peak = entry_px
    prot = None
    for ts, r in seg.iterrows():
        close, high, low = float(r["close"]), float(r["high"]), float(r["low"])
        if direction == "long":
            if close > peak:
                peak = close
                cand = low - buffer_px
                prot = cand if prot is None else max(prot, cand)
            if prot is not None and close < prot:
                return ts, prot
        else:
            if close < peak:
                peak = close
                cand = high + buffer_px
                prot = cand if prot is None else min(prot, cand)
            if prot is not None and close > prot:
                return ts, prot
    return None, None


def fwd(df, t, minutes, entry_px, direction):
    """Signed favourable move from entry_px, `minutes` after t. Management-free."""
    seg = df[(df.index > t) & (df.index <= t + timedelta(minutes=minutes))]
    if seg.empty:
        return None
    px = float(seg.iloc[-1]["close"])
    return (px - entry_px) if direction == "long" else (entry_px - px)


def _pct(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    return s[min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))]


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("dates", nargs="+")
    ap.add_argument("--tapes", default=os.path.expanduser("~/day_trader_pro/ohlc"),
                    help="dir holding 1m OHLC CSVs (searched recursively)")
    ap.add_argument("--buffer", type=float, default=0.5, help="k in k*ATR")
    ap.add_argument("--horizons", default="5,15,30")
    ap.add_argument("--strategy", default="ContinuationStrategy")
    a = ap.parse_args(argv[1:])
    horizons = [int(x) for x in a.horizons.split(",") if x.strip()]

    rows = []
    for d in a.dates:
        p = os.path.join(REPORTS_ROOT, f"fleet_trades_{d}.json")
        if not os.path.isfile(p):
            continue
        try:
            data = json.load(open(p, encoding="utf-8"))
        except Exception as exc:                              # noqa: BLE001
            print(f"  ! unreadable {p}: {exc}")
            continue
        recs = data if isinstance(data, list) else (
            data.get("trades") or data.get("rows") or [])
        if isinstance(recs, dict):
            recs = list(recs.values())
        for t in recs:
            if isinstance(t, dict) and str(t.get("strategy", "")) == a.strategy:
                t["_date"] = d
                rows.append(t)

    bos = [t for t in rows if "bos" in str(t.get("exit_reason", "")).lower()]
    print(f"dates: {len(a.dates)}   {a.strategy} trades: {len(rows)}   "
          f"bos_exit: {len(bos)}   buffer: {a.buffer}*ATR")
    if not bos:
        print("\nNo bos_exit rows. Check --strategy and that the dates are harvested.")
        return 1

    tapes, skipped = {}, {}
    saved, died_anyway, unchanged = [], [], []
    cost_px, never_pos = [], []
    fwd_by_h = {h: [] for h in horizons}

    for t in bos:
        sym = str(t.get("symbol", "")).upper()
        if sym not in tapes:
            tapes[sym] = load_tape(a.tapes, sym)
        df = tapes[sym]
        if df is None or df.empty:
            skipped["no tape for symbol"] = skipped.get("no tape for symbol", 0) + 1
            continue
        et = _ts(t.get("entry_time"), UTC)
        xt = _ts(t.get("exit_time"), UTC)
        px = _f(t.get("underlying_entry"))
        direction = str(t.get("direction", "")).lower()
        if None in (et, xt, px) or direction not in ("long", "short"):
            skipped["missing entry/exit/underlying/direction"] = \
                skipped.get("missing entry/exit/underlying/direction", 0) + 1
            continue
        # tape index is ET wall clock; trade stamps are UTC
        et_l = et.astimezone(ET).replace(tzinfo=None)
        xt_l = xt.astimezone(ET).replace(tzinfo=None)
        if df[(df.index >= et_l) & (df.index <= xt_l)].empty:
            skipped["no tape covering the trade window"] = \
                skipped.get("no tape covering the trade window", 0) + 1
            continue

        atr = atr_at(df, et_l) or 0.0
        pad = a.buffer * atr
        horizon_end = xt_l + timedelta(minutes=max(horizons) + 5)

        raw_fire, _ = replay_bos(df, et_l, px, direction, 0.0, horizon_end)
        buf_fire, _ = replay_bos(df, et_l, px, direction, pad, horizon_end)

        mfe = _f(t.get("max_premium_seen"))
        entry_prem = _f(t.get("entry_premium"))
        if mfe is not None and entry_prem:
            if mfe <= entry_prem * 1.0001:
                never_pos.append(t)

        if raw_fire is None:
            unchanged.append(t)
            continue
        if buf_fire is None or buf_fire > raw_fire:
            saved.append((t, raw_fire, buf_fire, df, px, direction))
            for h in horizons:
                v = fwd(df, raw_fire, h, px, direction)
                if v is not None:
                    fwd_by_h[h].append(v)
            if buf_fire is not None:
                died_anyway.append((raw_fire, buf_fire))
        else:
            unchanged.append(t)
        if pad > 0:
            dl = _f(t.get("entry_delta")) or 0.0
            cost_px.append(pad * abs(dl) * 100.0)

    print(f"\n--- replayed: {len(saved) + len(unchanged)} of {len(bos)} ---")
    for w, n in sorted(skipped.items()):
        print(f"    skipped {n}: {w}")

    tot = len(saved) + len(unchanged)
    if tot == 0:
        print("\nNothing replayable — the tape does not cover these trades.")
        return 1

    print(f"\n{'='*68}\n  1. CANDLE-B DEATHS — would the BUFFER have survived the killing bar?"
          f"\n{'='*68}")
    print(f"    SAVED (buffer survives the bar that fired the raw level): "
          f"{len(saved)}/{tot} ({100.0*len(saved)/tot:.0f}%)")
    print(f"    unchanged (buffer fires on the same bar or earlier):      "
          f"{len(unchanged)}")
    if died_anyway:
        deltas = [ (b - r).total_seconds()/60.0 for r, b in died_anyway ]
        print(f"    …of the saved, {len(died_anyway)} still fired LATER — "
              f"median +{_pct(deltas,0.5):.1f} min of extra life")
        print(f"       (a buffer that only DELAYS the funeral is not a fix)")

    print(f"\n{'='*68}\n  2. WHAT HAPPENED NEXT to the saved trades (from the raw exit)"
          f"\n{'='*68}")
    print("    Forward move in the trade's OWN direction, fixed horizons —")
    print("    management-independent by construction.")
    for h in horizons:
        v = fwd_by_h[h]
        if not v:
            continue
        pos = sum(1 for x in v if x > 0)
        print(f"    +{h:>3} min   n={len(v):<4} median={_pct(v,0.5):+.3f}  "
              f"p90={_pct(v,0.9):+.3f}  favourable {100.0*pos/len(v):.0f}%")
    if all(not fwd_by_h[h] for h in horizons):
        print("    (no forward tape — dates may end at the exit)")

    print(f"\n{'='*68}\n  3. THE COST — paid on EVERY bos exit, winners included"
          f"\n{'='*68}")
    if cost_px:
        print(f"    extra adverse travel to the buffered level, delta-approximated:")
        print(f"    n={len(cost_px)}  median=${_pct(cost_px,0.5):.2f}/contract  "
              f"p90=${_pct(cost_px,0.9):.2f}  total=${sum(cost_px):.2f}")
        print(f"    ⚠️ FIRST-ORDER ONLY — ignores gamma, theta and spread. On 0DTE")
        print(f"       this UNDERSTATES the true figure. Order of magnitude, not a price.")

    print(f"\n{'='*68}\n  4. THE PROFIT-GATE POPULATION — what proposal B releases"
          f"\n{'='*68}")
    print(f"    bos_exit trades that NEVER went positive: {len(never_pos)}/{len(bos)}")
    if never_pos:
        maes, pnls = [], []
        for t in never_pos:
            mn, ep = _f(t.get("min_premium_seen")), _f(t.get("entry_premium"))
            if mn is not None and ep:
                maes.append(100.0 * (mn - ep) / ep)
            v = _f(t.get("pnl_usd"))
            if v is not None:
                pnls.append(v)
        if maes:
            print(f"    their MAE at exit: median {_pct(maes,0.5):+.1f}%  "
                  f"p90 {_pct(maes,0.9):+.1f}%")
        if pnls:
            print(f"    their realised P&L: total ${sum(pnls):+,.2f}  "
                  f"median ${_pct(pnls,0.5):+.2f}")
        print(f"    ⇒ Disarming BOS until profit releases THESE. They stop dying")
        print(f"      at the MAE above and start dying at the premium floor instead.")
        print(f"      That difference, times {len(never_pos)}, is what proposal B costs.")

    print("\n  Neither option is scored here. This prices them; the choice is a")
    print("  design decision and both are BEHAVIOURAL — Monday, or after the freeze.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
