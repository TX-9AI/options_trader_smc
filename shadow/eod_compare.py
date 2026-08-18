"""
shadow/eod_compare.py — EOD would-have-fired vs actually-fired comparison.
v1.0 — 2026-07-09 — initial release.

Joins the shadow log (data/shadow/<date>/<SYMBOL>.jsonl) against trades.db
(GROUND TRUTH, opened strictly READ-ONLY) and reconstructs would-be outcomes
from the candle logger's 1-minute DXFeed OHLC (data/OHLC/<date>/<SYMBOL>.csv —
the same feed the fills priced against).

WOULD-BE OUTCOME RECONSTRUCTION
  For each candidate threshold (0.50..0.95): walk the shadow ticks; when a
  scorer's conviction crosses the threshold and no simulated position is open
  at that threshold, open one (long->call / short->put, first OTM strike per
  config.STRIKE_INCREMENTS, same-session expiry). Reprice forward on the 1-min
  closes with Black-Scholes (sigma = the day's realized 1m vol, annualized in
  trading time; r = 0) under the SAME exit logic the bot's long singles use
  (base_strategy v-current + exit_engine v1.2/1.3):
      stop        premium <= 0.75 x entry            (25% stop)
      trail arm   premium >= 1.50 x entry            (50% TP)
      trail floor 0.75 x peak; tightens to 0.85 x peak past 2.00 x entry
      hard close  15:45 ET
  Premiums are BS ESTIMATES (no chain snapshot exists for trades that never
  happened) — labeled EST throughout; directional comparability is the point,
  not cent accuracy.

Output: per threshold — would-fire count, est P&L per 1 contract, and the
agreement view: BOTH fired / SHADOW-ONLY / BOT-ONLY (entry times matched
within +/- MATCH_WINDOW_MIN, same direction).

Usage:
    python -m shadow.eod_compare                     # today, this box's symbol
    python -m shadow.eod_compare --date 2026-07-09 --symbol AVGO
Fleet rollup:  fleet.py run "cd ~/options-trader && venv/bin/python -m shadow.eod_compare" --all
"""

import argparse
import csv
import json
import math
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from config import INSTRUMENT, DB_PATH, STRIKE_INCREMENTS

ET = ZoneInfo("America/New_York")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHADOW_DIR = os.path.join(REPO_ROOT, "data", "shadow")
OHLC_DIR = os.path.join(REPO_ROOT, "data", "OHLC")

THRESHOLDS = [round(0.50 + 0.05 * i, 2) for i in range(10)]
MATCH_WINDOW_MIN = 5
HARD_CLOSE_HM = (15, 45)
TRADING_MIN_PER_YEAR = 252 * 390

# exit params mirrored from base_strategy / exit_engine (long singles)
STOP_MULT, TARGET_MULT = 0.75, 2.00
TRAIL_ARM_MULT, TRAIL_LOCK, POST_TARGET_LOCK = 1.50, 0.75, 0.85


# ── Black-Scholes (erf-based; no scipy) ───────────────────────────────────────
def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_price(S: float, K: float, T_years: float, sigma: float, side: str) -> float:
    """European BS, r=0. side: 'call'/'put'. Intrinsic at/after expiry."""
    if T_years <= 0 or sigma <= 0:
        return max(S - K, 0.0) if side == "call" else max(K - S, 0.0)
    st = sigma * math.sqrt(T_years)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T_years) / st
    d2 = d1 - st
    if side == "call":
        return S * _ncdf(d1) - K * _ncdf(d2)
    return K * _ncdf(-d2) - S * _ncdf(-d1)


# ── Data loading ──────────────────────────────────────────────────────────────
def load_ohlc(date_str: str, symbol: str) -> List[dict]:
    path = os.path.join(OHLC_DIR, date_str, f"{symbol}.csv")
    if not os.path.exists(path):
        return []
    rows = []
    with open(path) as f:
        for r in csv.DictReader(f):
            try:
                ts = datetime.fromisoformat(r["timestamp"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=ET)
                rows.append({"ts": ts.astimezone(ET), "close": float(r["close"])})
            except (KeyError, ValueError):
                continue
    rows.sort(key=lambda r: r["ts"])
    return rows


def realized_sigma(ohlc: List[dict]) -> float:
    closes = [r["close"] for r in ohlc if r["close"] > 0]
    if len(closes) < 30:
        return 0.35   # conservative fallback, flagged in report
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    mean = sum(rets) / len(rets)
    var = sum((x - mean) ** 2 for x in rets) / max(len(rets) - 1, 1)
    sig = math.sqrt(var) * math.sqrt(TRADING_MIN_PER_YEAR)
    return min(max(sig, 0.10), 3.0)


def load_shadow(date_str: str, symbol: str) -> List[dict]:
    path = os.path.join(SHADOW_DIR, date_str, f"{symbol}.jsonl")
    if not os.path.exists(path):
        return []
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def load_actual_trades(db_path: str, date_str: str, symbol: str) -> List[dict]:
    """GROUND TRUTH — trades.db opened strictly read-only (mode=ro)."""
    if not os.path.exists(db_path):
        return []
    uri = f"file:{db_path}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT trade_id, strategy, direction, option_side, strike, contracts,"
            "       entry_premium, exit_premium, pnl_usd, status, exit_reason,"
            "       entry_time, exit_time, underlying_entry "
            "FROM trades WHERE symbol = ? AND substr(entry_time, 1, 10) = ? "
            "ORDER BY entry_time", (symbol, date_str),
        ).fetchall()
    finally:
        con.close()
    out = []
    for r in rows:
        d = dict(r)
        d["entry_dt"] = _parse_et(d.get("entry_time"))
        side = (d.get("option_side") or "").lower()
        direc = (d.get("direction") or "").lower()
        d["dir_norm"] = ("long" if side == "call" or direc in ("long", "bullish")
                         else "short")
        out.append(d)
    return out


def _parse_et(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace(" ET", "").strip())
        return dt.replace(tzinfo=ET) if dt.tzinfo is None else dt.astimezone(ET)
    except ValueError:
        return None


# ── Would-be trade simulation ─────────────────────────────────────────────────
def _strike_for(symbol: str, S: float, direction: str) -> float:
    inc = STRIKE_INCREMENTS.get(symbol, 1)
    return (math.ceil(S / inc) * inc) if direction == "long" else (math.floor(S / inc) * inc)


def _t_years(dt: datetime) -> float:
    close = dt.replace(hour=16, minute=0, second=0, microsecond=0)
    return max((close - dt).total_seconds() / 60.0, 0.0) / TRADING_MIN_PER_YEAR


def simulate_trade(entry_dt: datetime, S_entry: float, direction: str,
                   symbol: str, ohlc: List[dict], sigma: float) -> Optional[dict]:
    side = "call" if direction == "long" else "put"
    K = _strike_for(symbol, S_entry, direction)
    entry_prem = bs_price(S_entry, K, _t_years(entry_dt), sigma, side)
    if entry_prem < 0.02:
        return None                                   # untradeably cheap estimate

    hard_close = entry_dt.replace(hour=HARD_CLOSE_HM[0], minute=HARD_CLOSE_HM[1],
                                  second=0, microsecond=0)
    peak, trail_armed = entry_prem, False
    for bar in ohlc:
        if bar["ts"] <= entry_dt:
            continue
        prem = bs_price(bar["close"], K, _t_years(bar["ts"]), sigma, side)
        peak = max(peak, prem)
        if bar["ts"] >= hard_close:
            return _result(entry_dt, bar["ts"], entry_prem, prem, K, side, "hard_close")
        if prem <= entry_prem * STOP_MULT:
            return _result(entry_dt, bar["ts"], entry_prem, prem, K, side, "stop_25pct")
        if not trail_armed and prem >= entry_prem * TRAIL_ARM_MULT:
            trail_armed = True
        if trail_armed:
            lock = POST_TARGET_LOCK if peak >= entry_prem * TARGET_MULT else TRAIL_LOCK
            if prem <= peak * lock:
                return _result(entry_dt, bar["ts"], entry_prem, prem, K, side, "trail")
    if ohlc:
        last = ohlc[-1]
        prem = bs_price(last["close"], K, _t_years(last["ts"]), sigma, side)
        return _result(entry_dt, last["ts"], entry_prem, prem, K, side, "eod_data_end")
    return None


def _result(edt, xdt, ep, xp, K, side, reason) -> dict:
    return {"entry_dt": edt, "exit_dt": xdt, "entry_prem": round(ep, 3),
            "exit_prem": round(xp, 3), "strike": K, "side": side, "reason": reason,
            "pnl_est": round((xp - ep) * 100, 2)}     # per 1 contract


def would_trades_for_threshold(ticks: List[dict], th: float, symbol: str,
                               ohlc: List[dict], sigma: float) -> List[dict]:
    """One simulated position at a time (matches the bot's single-position model)."""
    trades, busy_until = [], None
    for t in ticks:
        tdt = _parse_et(t.get("ts"))
        if tdt is None:
            continue
        if busy_until and tdt <= busy_until:
            continue
        for s in t.get("scores", []):
            conv = s.get("conviction")
            if conv is None or conv < th or s.get("invalidated"):
                continue
            direction = s.get("direction") or "long"
            sim = simulate_trade(tdt, float(t["price"]), direction, symbol, ohlc, sigma)
            if sim:
                sim.update({"threshold": th, "direction": direction,
                            "scorer": s.get("scorer"), "level": s.get("level"),
                            "conviction": conv})
                trades.append(sim)
                busy_until = sim["exit_dt"]
            break
    return trades


# ── Agreement + report ────────────────────────────────────────────────────────
def agreement(would: List[dict], actual: List[dict]):
    win = timedelta(minutes=MATCH_WINDOW_MIN)
    both, shadow_only = [], []
    matched_actual = set()
    for w in would:
        hit = None
        for i, a in enumerate(actual):
            if i in matched_actual or a["entry_dt"] is None:
                continue
            if abs(a["entry_dt"] - w["entry_dt"]) <= win and a["dir_norm"] == w["direction"]:
                hit = i
                break
        if hit is not None:
            matched_actual.add(hit)
            both.append((w, actual[hit]))
        else:
            shadow_only.append(w)
    bot_only = [a for i, a in enumerate(actual) if i not in matched_actual]
    return both, shadow_only, bot_only


def _fmt_dt(dt) -> str:
    return dt.strftime("%H:%M") if dt else "??:??"


def main():
    ap = argparse.ArgumentParser(description="Shadow would-vs-actual EOD report")
    ap.add_argument("--date", default=datetime.now(tz=ET).strftime("%Y-%m-%d"))
    ap.add_argument("--symbol", default=INSTRUMENT)
    ap.add_argument("--db", default=DB_PATH)
    args = ap.parse_args()

    date_str, symbol = args.date, args.symbol
    ticks = load_shadow(date_str, symbol)
    ohlc = load_ohlc(date_str, symbol)
    actual = load_actual_trades(args.db, date_str, symbol)

    print(f"\n=== SHADOW vs ACTUAL — {symbol} {date_str} ===")
    print(f"shadow ticks: {len(ticks)} | 1m OHLC bars: {len(ohlc)} | actual trades: {len(actual)}")
    if not ticks:
        print("No shadow log for this date — nothing to compare.")
        return
    if not ohlc:
        print("No data/OHLC file for this date — cannot reconstruct would-be outcomes.")
        print("(Run after the 16:05 candle logger, or backfill it first.)")
        return

    sigma = realized_sigma(ohlc)
    scored = sum(1 for t in ticks for s in t.get("scores", []) if s.get("conviction") is not None)
    print(f"realized 1m vol (annualized, trading-time): {sigma:.1%} | scored ticks: {scored}")
    if scored == 0:
        print("Stage-1 log (primitives only) — no conviction scores to compare yet.")
        return

    print(f"\n{'thresh':>6} | {'would-fire':>10} | {'wins':>4} | {'losses':>6} | {'est P&L/1x':>10}")
    print("-" * 52)
    per_th = {}
    for th in THRESHOLDS:
        wt = would_trades_for_threshold(ticks, th, symbol, ohlc, sigma)
        per_th[th] = wt
        wins = sum(1 for w in wt if w["pnl_est"] > 0)
        pnl = sum(w["pnl_est"] for w in wt)
        print(f"{th:>6.2f} | {len(wt):>10} | {wins:>4} | {len(wt)-wins:>6} | {pnl:>+10.2f}")

    print(f"\nACTUAL trades (trades.db, read-only): {len(actual)}")
    for a in actual:
        print(f"  {_fmt_dt(a['entry_dt'])} {a['dir_norm']:<5} {a.get('strategy','?'):<14} "
              f"K={a.get('strike')} pnl={a.get('pnl_usd')} [{a.get('status')}/{a.get('exit_reason')}]")

    # Agreement view at a representative mid threshold (repeatable per threshold)
    ref_th = 0.70
    both, shadow_only, bot_only = agreement(per_th.get(ref_th, []), actual)
    print(f"\nAGREEMENT @ threshold {ref_th:.2f} (match: same direction, +/-{MATCH_WINDOW_MIN} min):")
    print(f"  BOTH fired      : {len(both)}")
    for w, a in both:
        print(f"    {_fmt_dt(w['entry_dt'])} {w['direction']:<5} shadowEST={w['pnl_est']:+.2f}"
              f"  actual={a.get('pnl_usd')}")
    print(f"  SHADOW-only     : {len(shadow_only)}   (shadow would have traded; bot did not)")
    for w in shadow_only:
        print(f"    {_fmt_dt(w['entry_dt'])} {w['direction']:<5} conv={w['conviction']:.2f} "
              f"@{w['level']} EST={w['pnl_est']:+.2f} [{w['reason']}]")
    print(f"  BOT-only        : {len(bot_only)}   (bot traded; shadow would not have)")
    for a in bot_only:
        print(f"    {_fmt_dt(a['entry_dt'])} {a['dir_norm']:<5} {a.get('strategy','?')} "
              f"pnl={a.get('pnl_usd')}")

    print("\nNOTE: shadow P&L figures are BS ESTIMATES per 1 contract (no chain "
          "snapshot exists for trades that never happened). Use them for base-rate "
          "and threshold selection, not cent-accurate accounting.\n")


if __name__ == "__main__":
    main()
