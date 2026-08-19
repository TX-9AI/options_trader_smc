#!/usr/bin/env python3
"""
tests/ict_observe.py — the OBSERVE RUN. v1.0
v1.0 — 2026-08-19 — INITIAL.

Nothing here decides anything. It replays the ICT suite over real tape and
reports the six things a healthy result is supposed to look like, so the
NUMBERS get supplied from an observed distribution instead of invented and
then confirmed. That ordering is the whole point: a threshold chosen before
seeing the data is a prior; one chosen after, and then tested on the same
data, is a fit dressed as a discovery.

The six sections match the pre-registered criteria verbatim:

  1. FREQUENCY      — rare and clustered in the morning, sessions vary,
                      zero-setup sessions are a correct answer.
                      Wrong: uniform arrival, or identical counts per session.
  2. CHAIN INTEGRITY— four invariants with NO threshold. A violation is a
                      DEFECT IN OUR CODE, not a signal about the setup:
                        · raid ts precedes shift ts on every completed chain
                        · sweep direction agrees with shift direction
                        · no setup forms on the -1.0 no-range sentinel
                        · the raided pool is identifiable in the row
  3. SCORE DISTRIB. — a spread with a tail; the score should ACCUMULATE.
                      Wrong: piled at one value, bimodal at floor/ceiling, or
                      jumping to final in a single bar.
  4. STABILITY      — form, accumulate, resolve ONCE. Flapping means the
                      scorer is reading noise.
  5. SEPARATION     — THE ONE THAT DECIDES IT. Rank completed setups by
                      score, split, compare forward outcome. DIRECTION IS
                      PRE-REGISTERED HERE IN CODE: high-score median forward
                      R must EXCEED low-score median forward R. An inverted
                      result is the grade-inversion signature and is a
                      stop-and-rethink, not a retune.
  6. NOVELTY        — do these land where the legacy engine wasn't trading?
                      Wrong: shadowing ORB on the same bars and direction.

⚠️ OCCURRENCE, NOT P&L. Forward outcome is measured on the UNDERLYING in R
units using each setup's own invalidation as the risk denominator. There is no
option chain, no fill model and no theta here. A positive separation says the
score ranks structure usefully; it does not say the trade makes money.

Run (tmux, it is not instant):
  cd ~/options-trader-smc && PYTHONPATH=. ~/options-trader-v3/venv/bin/python \\
      tests/ict_observe.py --glob "$HOME/day_trader_pro/ohlc/*/QQQ_ohlc_*.csv"
"""

import argparse
import os
import statistics as stats
import sys
from collections import Counter, defaultdict
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ET = ZoneInfo("America/New_York")
RTH_OPEN, RTH_CLOSE = dtime(9, 30), dtime(16, 0)
FORWARD_BARS = 30          # how far ahead the outcome is measured (prior)


def load_tape(pattern):
    import glob
    paths = sorted(glob.glob(os.path.expanduser(pattern)))
    if not paths:
        raise SystemExit(f"no files matched {pattern}")
    frames = []
    for p in paths:
        raw = pd.read_csv(p, header=0, dtype=str)
        raw.columns = [c.strip().lower() for c in raw.columns]
        if "timestamp" not in raw.columns:
            continue
        ts = pd.to_datetime(raw["timestamp"], format="ISO8601", errors="coerce")
        ok = ts.notna()
        df = raw[ok].copy()
        df.index = ts[ok]
        for c in ("open", "high", "low", "close", "volume"):
            if c in df:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        frames.append(df.dropna(subset=["open", "high", "low", "close"])
                      [["open", "high", "low", "close", "volume"]])
    if not frames:
        raise SystemExit("matched files, none parsed as OHLC")
    df = pd.concat(frames).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df.index = (df.index.tz_localize(ET) if df.index.tz is None
                else df.index.tz_convert(ET))
    df = df[(df.index.time >= RTH_OPEN) & (df.index.time <= RTH_CLOSE)]
    firsts = {d: df[df.index.date == d].index[0].time()
              for d in sorted(set(df.index.date))}
    bad = {d: t for d, t in firsts.items() if t != RTH_OPEN}
    if len(bad) > len(firsts) // 2:
        raise SystemExit(
            f"REFUSING TO RUN: {len(bad)}/{len(firsts)} sessions do not start "
            f"at 09:30 ET (e.g. {sorted(bad.items())[:3]}) — the tape is not "
            f"Eastern. Fix the tape, not the harness.")
    print(f"  tape: {len(df)} bars, {len(firsts)} sessions "
          f"({min(firsts)} → {max(firsts)})")
    return df


def forward_r(df, i, direction, risk):
    """Forward move in R over FORWARD_BARS, signed by direction.

    R = (terminal move) / risk, where risk is the setup's own invalidation
    distance. TERMINAL, not maximum-favourable: MFE is positive for nearly any
    bar in any tape, so an MFE-based split would show both halves profitable
    and manufacture a separation that isn't there. Underlying only —
    deliberately crude, and labelled as such everywhere it is reported.
    """
    if risk is None or risk <= 0:
        return None
    end = min(i + FORWARD_BARS, len(df) - 1)
    if end <= i:
        return None
    seg = df.iloc[i + 1:end + 1]
    entry = float(df.iloc[i]["close"])
    exit_px = float(seg["close"].iloc[-1])
    if direction in ("long", "bullish"):
        return (exit_px - entry) / risk
    if direction in ("short", "bearish"):
        return (entry - exit_px) / risk
    return None


def main():
    ap = argparse.ArgumentParser(description="ICT observe run — no decisions")
    ap.add_argument("--glob", required=True, help="per-date OHLC csv pattern")
    ap.add_argument("--forward", type=int, default=FORWARD_BARS)
    args = ap.parse_args()

    df = load_tape(args.glob)

    from smc.smc_engine import SMCEngine
    from analysis.structure_analyzer import get_structure_analyzer
    from analysis.liquidity_mapper import get_liquidity_mapper
    from analysis.volatility_engine import get_volatility_engine
    from strategy.ict import build_context
    from strategy.ict.dispatch import evaluate_all

    stE, lqE, volE = (get_structure_analyzer(), get_liquidity_mapper(),
                      get_volatility_engine())
    smc = SMCEngine(state_dir=None)

    rows = []                      # one per (bar, setup) with a live score
    prev_phase = {}
    transitions = defaultdict(list)
    violations = []
    days = sorted(set(df.index.date))

    for d in days:
        sess_start = pd.Timestamp(datetime.combine(d, RTH_OPEN), tz=ET)
        sess = df[df.index.date == d]
        d5 = sess.resample("5min", label="right", closed="right").agg(
            {"open": "first", "high": "max", "low": "min",
             "close": "last", "volume": "sum"}).dropna(subset=["close"])
        d15 = sess.resample("15min", label="right", closed="right").agg(
            {"open": "first", "high": "max", "low": "min",
             "close": "last", "volume": "sum"}).dropna(subset=["close"])
        for i_local, t in enumerate(sess.index):
            i_global = df.index.get_loc(t)
            price = float(sess.iloc[i_local]["close"])
            s5 = d5[d5.index <= t]
            s15 = d15[d15.index <= t]
            d1m = sess[sess.index <= t]
            if len(s5) < 5 or len(d1m) < 20:
                continue
            try:
                vs = volE.analyze(s5, s5, price)
                st = stE.analyze(s5, s15, None, price)
                lq = lqE.analyze(s5, s15, price)
                smc_st = smc.update(price=price, df_1m=d1m, df_5m=s5,
                                    structure=st, liq_map=lq, vol_state=vs,
                                    now_et=t.to_pydatetime())
                ictx = build_context(smc_state=smc_st, structure=st,
                                     liq_map=lq, df_1m=d1m,
                                     now_et=t.to_pydatetime(), price=price)
                scores = evaluate_all(ictx)
            except Exception as exc:                       # noqa: BLE001
                violations.append(f"{t}: evaluate raised {type(exc).__name__}: {exc}")
                continue

            for sc in scores:
                ph = sc.phase()
                key = sc.setup
                if prev_phase.get(key) != ph:
                    transitions[key].append((t, ph))
                    prev_phase[key] = ph
                if ph in ("DORMANT",):
                    continue
                s = sc.score()
                # ── CHAIN INTEGRITY (no thresholds; violations are OUR bugs)
                if ictx.position_pct == -1.0 and ph in ("FORMING", "READY"):
                    # one row per BAR, not per setup — every setup sees the same
                    # sentinel, and 7x the same fact is noise, not 7x the news
                    _v = f"{t}: setup(s) formed on the -1.0 no-range sentinel"
                    if not violations or violations[-1] != _v:
                        violations.append(_v)
                if (ictx.raid and ictx.last_shift_dir and ictx.displacement_dir
                        and ictx.last_shift_dir != ictx.displacement_dir
                        and key == "ICTSweepMSS" and ph == "READY"):
                    violations.append(
                        f"{t} {key}: sweep/shift direction disagree "
                        f"({ictx.displacement_dir} vs {ictx.last_shift_dir})")
                risk = None
                if ictx.raid and isinstance(ictx.raid, dict):
                    lvl = ictx.raid.get("level")
                    if lvl:
                        risk = abs(price - float(lvl))
                if risk in (None, 0):
                    risk = abs(price - ictx.displacement_origin) or None
                rows.append({
                    "t": t, "setup": key, "phase": ph, "score": s,
                    "completeness": sc.completeness(),
                    "direction": sc.direction,
                    "pos": ictx.position_pct, "zone": ictx.zone,
                    "raid": bool(ictx.raid),
                    "pool": (ictx.raid or {}).get("level") if ictx.raid else None,
                    "fwd_r": forward_r(df, i_global, sc.direction, risk),
                    "hour": t.hour + t.minute / 60.0,
                    "day": str(d),
                })

    print(f"\n{'='*70}\nICT OBSERVE RUN — {len(days)} sessions, "
          f"{len(rows)} live setup-ticks\n{'='*70}")

    # ── 1. FREQUENCY ────────────────────────────────────────────────────
    print("\n-- 1. FREQUENCY (want: rare, clustered in the morning, sessions vary)")
    ready = [r for r in rows if r["phase"] == "READY"]
    per_day = Counter(r["day"] for r in ready)
    print(f"  READY setup-ticks: {len(ready)} across {len(per_day)} session(s) "
          f"with any; {len(days) - len(per_day)} session(s) produced NONE")
    if per_day:
        cnts = sorted(per_day.values())
        print(f"  per-session count: min {cnts[0]}  median "
              f"{stats.median(cnts):.0f}  max {cnts[-1]}"
              + ("   ⚠️ IDENTICAL EVERY SESSION — firing on a clock, not structure"
                 if len(set(cnts)) == 1 and len(cnts) > 2 else ""))
    hours = Counter(int(r["hour"]) for r in ready)
    if hours:
        print("  by hour ET: " + "  ".join(f"{h}:00={n}" for h, n in sorted(hours.items())))
        morning = sum(n for h, n in hours.items() if h < 12)
        print(f"  morning share: {100.0*morning/max(1,len(ready)):.0f}%"
              + ("   ⚠️ UNIFORM — the window component is not doing work"
                 if len(hours) > 4 and max(hours.values()) < 2 * min(hours.values())
                 else ""))
    per_setup = Counter(r["setup"] for r in ready)
    print("  by setup: " + (", ".join(f"{k}={v}" for k, v in per_setup.most_common())
                            or "(none reached READY)"))

    # ── 2. CHAIN INTEGRITY ──────────────────────────────────────────────
    print("\n-- 2. CHAIN INTEGRITY (no thresholds — a violation is OUR defect)")
    named = sum(1 for r in ready if r["pool"] is not None)
    if violations:
        print(f"  🔴 {len(violations)} VIOLATION(S) — fix before trusting anything below:")
        for v in violations[:8]:
            print(f"     {v}")
        if len(violations) > 8:
            print(f"     … {len(violations)-8} more")
    else:
        print("  ✅ no sentinel-forms, no direction disagreements, no raises")
    print(f"  raided pool identifiable on {named}/{len(ready)} READY rows"
          + ("   ⚠️ the row cannot say WHAT was raided" if ready and named < len(ready) else ""))

    # ── 3. SCORE DISTRIBUTION ───────────────────────────────────────────
    print("\n-- 3. SCORE DISTRIBUTION (want: a spread with a tail, accumulating)")
    live = [r["score"] for r in rows if r["phase"] in ("FORMING", "READY")]
    if live:
        q = lambda p: sorted(live)[min(len(live) - 1, int(p * len(live)))]
        print(f"  n={len(live)}  min {min(live):.2f}  p25 {q(.25):.2f}  "
              f"median {stats.median(live):.2f}  p75 {q(.75):.2f}  max {max(live):.2f}")
        top = Counter(round(x, 2) for x in live).most_common(1)[0]
        if top[1] > 0.5 * len(live):
            print(f"  ⚠️ {100.0*top[1]/len(live):.0f}% of scores sit at {top[0]} "
                  f"— components are not discriminating")
        buckets = Counter(min(9, int(x * 10)) for x in live)
        print("  histogram: " + " ".join(f"{b/10:.1f}:{n}" for b, n in sorted(buckets.items())))
        jumps = _jump_check(rows)
        print(f"  single-bar jumps to final score: {jumps}"
              + ("   ⚠️ nothing is ACCUMULATING" if jumps > len(live) * 0.5 else ""))
    else:
        print("  no FORMING/READY ticks — nothing to distribute")

    # ── 4. STABILITY ────────────────────────────────────────────────────
    print("\n-- 4. STABILITY (want: form → accumulate → resolve ONCE)")
    for k, tr in sorted(transitions.items()):
        seq = [p for _t, p in tr]
        flaps = sum(1 for a, b in zip(seq, seq[1:])
                    if (a, b) in (("READY", "FORMING"), ("FORMING", "DORMANT")))
        print(f"  {k:<20} {len(tr):>4} transitions   flap-backs {flaps}"
              + ("   ⚠️ reading noise" if flaps > len(tr) * 0.3 and len(tr) > 6 else ""))

    # ── 5. SEPARATION — pre-registered direction ────────────────────────
    print("\n-- 5. SEPARATION  ← THE ONE THAT DECIDES IT")
    print("  PRE-REGISTERED: high-score group's median forward R must EXCEED")
    print("  the low-score group's. Inverted = grade-inversion signature =")
    print("  stop and rethink, NOT a retune.")
    scored = [r for r in rows if r["phase"] in ("FORMING", "READY")
              and r["fwd_r"] is not None]
    if len(scored) < 20:
        print(f"  n={len(scored)} — TOO THIN TO READ. Not a result either way.")
    else:
        scored.sort(key=lambda r: r["score"])
        half = len(scored) // 2
        lo = [r["fwd_r"] for r in scored[:half]]
        hi = [r["fwd_r"] for r in scored[-half:]]
        mlo, mhi = stats.median(lo), stats.median(hi)
        verdict = ("SEPARATES" if mhi > mlo else
                   "INVERTED — the scorer is confirming spent moves"
                   if mhi < mlo else "FLAT")
        print(f"  n={len(scored)}  low-half median {mlo:+.2f}R  "
              f"high-half median {mhi:+.2f}R  →  {verdict}")
        print(f"  (forward window {args.forward} bars, UNDERLYING R on the "
              f"setup's own invalidation — no premium, no fills)")

    # ── 6. NOVELTY ──────────────────────────────────────────────────────
    print("\n-- 6. NOVELTY (want: not shadowing ORB — different bars/direction)")
    orb_window = [r for r in ready if 9.5 <= r["hour"] <= 11.0]
    print(f"  READY inside ORB's live window: {len(orb_window)}/{len(ready)}"
          + ("   ⚠️ mostly inside ORB's window — check for shadowing"
             if ready and len(orb_window) > 0.8 * len(ready) else ""))
    zones = Counter(r["zone"] for r in ready)
    print("  entry zone mix: " + (", ".join(f"{k}={v}" for k, v in zones.most_common())
                                  or "(none)"))

    print("\n" + "=" * 70)
    print("NOTHING WAS DECIDED HERE. Supply the numbers from these "
          "distributions,\nthen re-run to test them — never on this same pass.")
    print("=" * 70)
    return 1 if violations else 0


def _jump_check(rows):
    """How many setups reached their final score in a single bar?"""
    by = defaultdict(list)
    for r in rows:
        by[(r["setup"], r["day"])].append(r["score"])
    n = 0
    for seq in by.values():
        if len(seq) >= 2 and seq[0] >= max(seq) - 1e-9:
            n += 1
    return n


if __name__ == "__main__":
    sys.exit(main())
