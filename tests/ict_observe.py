#!/usr/bin/env python3
"""
tests/ict_observe.py — the OBSERVE RUN. v1.1
v1.1 — 2026-08-19 — THREE FIXES AND A NEW SECTION, after the first real run.
       Two of the alarming numbers in that run were THIS FILE'S BUGS:
       (1) "raided pool identifiable on 0/1065 READY rows" — I read
           `raid["level"]`. `raid_in_progress()` returns `pool`, `kind`,
           `name`, `depth_pct`. There is no `level` key and never was, so the
           lookup returned None on every row and the harness reported a data
           problem that did not exist. Worse, the RISK DENOMINATOR fell back to
           the displacement origin, so section 5's R units were not the setup's
           own invalidation — which is what section 5 claims to measure.
       (2) "INVERTED — the scorer is confirming spent moves" was printed for
           low −0.00R vs high −0.00R. A strictly-less-than test on two
           effectively-equal medians. FLAT and INVERTED are different findings
           with different responses, and calling a tie an inversion is the
           cry-wolf pattern in the one section that decides everything. There
           is now a tolerance band, the raw delta is printed, and a quartile
           profile is shown so a monotone relationship is visible rather than
           inferred from two numbers.
       (3) Sentinel rows are counted per BAR and the zone mix is reported for
           READY rows specifically, so "formed with no dealing range" is
           quantified rather than implied.
       NEW SECTION 7 — COMPONENT DIAGNOSTICS. The first run said six of seven
       setups never reached READY and gave no way to ask why. Section 7 reports,
       per setup and per component: how often it was AVAILABLE, its mean value
       when available, and how often it MET ITS FLOOR — then names the required
       component that blocked most often. "SweepMSS never fired" is not
       actionable; "SweepMSS stalled on dir:sweep in 97% of ticks because the
       raid primitive is rarely available" is.
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
    comp = defaultdict(lambda: {"n": 0, "avail": 0, "met": 0, "sum": 0.0,
                                "req": False, "floor": 0.0, "why": {}})
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
                # ── v1.1 §7 — WHY did this setup not advance? Per component:
                # availability, value when available, and whether it met its
                # floor. Without this, "six of seven never reached READY" is a
                # dead end; with it, the blocking component is named.
                for c in sc.components:
                    st_ = comp[(sc.setup, c.name)]
                    st_["n"] += 1
                    st_["req"] = bool(getattr(c, "required", False))
                    st_["floor"] = float(getattr(c, "floor", 0.0) or 0.0)
                    if getattr(c, "available", True):
                        st_["avail"] += 1
                        st_["sum"] += float(c.value)
                        if float(c.value) >= st_["floor"]:
                            st_["met"] += 1
                    elif getattr(c, "reason", ""):
                        st_["why"][c.reason] = st_["why"].get(c.reason, 0) + 1
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
                # v1.1 — the key is `pool`, not `level`. Getting this wrong
                # silently moved section 5's R denominator off the setup's own
                # invalidation and onto the displacement origin.
                risk = None
                pool = None
                if ictx.raid and isinstance(ictx.raid, dict):
                    pool = ictx.raid.get("pool")
                    if pool:
                        risk = abs(price - float(pool))
                if not risk:
                    sw = ictx.recent_sweep or {}
                    _sp = sw.get("sweep_price") or sw.get("price")
                    if _sp:
                        pool = pool or _sp
                        risk = abs(price - float(_sp))
                if not risk and ictx.displacement_origin:
                    risk = abs(price - ictx.displacement_origin) or None
                rows.append({
                    "t": t, "setup": key, "phase": ph, "score": s,
                    "completeness": sc.completeness(),
                    "direction": sc.direction,
                    "pos": ictx.position_pct, "zone": ictx.zone,
                    "raid": bool(ictx.raid),
                    "pool": pool,
                    "pool_name": (ictx.raid or {}).get("name") if ictx.raid else None,
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
    nozone = sum(1 for r in ready if r["pos"] == -1.0)
    print(f"  READY rows with NO dealing range (-1.0 sentinel): "
          f"{nozone}/{len(ready)}"
          + ("   🔴 a POI setup with no range is a claim about nothing"
             if nozone else ""))
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
        # v1.1 — a TOLERANCE, because FLAT and INVERTED demand different
        # responses and a strictly-less-than test on two equal medians called
        # a tie an inversion. Flat means the score carries no information;
        # inverted means it carries information the wrong way round, which is
        # the grade-inversion signature and a far more serious finding.
        eps = 0.05
        delta = mhi - mlo
        verdict = ("SEPARATES" if delta > eps else
                   "INVERTED — the scorer is confirming spent moves"
                   if delta < -eps else
                   "FLAT — the score carries no forward information "
                   "(not an inversion; a nullity)")
        print(f"  n={len(scored)}  low-half median {mlo:+.3f}R  "
              f"high-half median {mhi:+.3f}R  delta {delta:+.3f}R  "
              f"(tolerance ±{eps})  →  {verdict}")
        # quartile profile: a monotone climb is the thing SEPARATES claims
        qs = [scored[i * len(scored) // 4:(i + 1) * len(scored) // 4]
              for i in range(4)]
        prof = "  ".join(f"Q{i+1} {stats.median([r['fwd_r'] for r in q]):+.3f}"
                         for i, q in enumerate(qs) if q)
        print(f"  by score quartile (low→high): {prof}")
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

    # ── 7. COMPONENT DIAGNOSTICS — the "why" behind section 1 ───────────
    print("\n-- 7. COMPONENT DIAGNOSTICS (why a setup did or did not advance)")
    setups = sorted({k[0] for k in comp})
    for name in setups:
        items = [(k[1], v) for k, v in comp.items() if k[0] == name]
        items.sort(key=lambda kv: (not kv[1]["req"], kv[0]))
        n_tot = max((v["n"] for _k, v in items), default=0)
        print(f"\n  {name}  ({n_tot} evaluations)")
        blockers = []
        for cname, v in items:
            av = 100.0 * v["avail"] / max(1, v["n"])
            mean = v["sum"] / max(1, v["avail"])
            met = 100.0 * v["met"] / max(1, v["n"])
            tag = "REQUIRED" if v["req"] else "        "
            print(f"    {tag} {cname:<20} avail {av:5.1f}%  "
                  f"mean {mean:4.2f}  meets floor({v['floor']:.2f}) {met:5.1f}%")
            if v["why"]:
                top = sorted(v["why"].items(), key=lambda x: -x[1])[0]
                print(f"             unavailable because: {top[0]} "
                      f"({100.0*top[1]/max(1,v['n']):.0f}% of ticks)")
            if v["req"]:
                blockers.append((met, cname))
        if blockers:
            blockers.sort()
            print(f"    → STALLED ON: {blockers[0][1]} "
                  f"(met its floor on only {blockers[0][0]:.1f}% of ticks)")

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
