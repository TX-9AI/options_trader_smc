"""
tests/backtest_harness.py — offline multi-day backtest over spliced 1-minute tape.
v1.2 — 2026-07-31 — `--all` and `--json PATH`. The fired listing was capped at
        `fired[:8]`, which is fine for reading one symbol and fatal for pooling:
        per-trade R BY REGIME across 29 symbols was impossible, and the first 8
        chronologically is not a random sample — it is the start of the window.
        `--json` appends one object per fired trade so a sweep can concatenate
        them. Item AH's stated prerequisite.
v1.1 — 2026-07-30 — +STRATEGY ATTEMPT CENSUS. v1.0 drove ORB only, so "how often
        does each strategy even get a setup" could not be answered offline —
        which is how ContinuationStrategy went weeks building signals with
        strike=0 that main rejected every tick, with nobody noticing. Now also
        drives Continuation, SweepReversal and IronCondor over the same tape,
        against a chain MODELLED with this file's own Black-Scholes pricer, and
        reports setups / valid / invalid / raised plus the regime each setup
        occurred under. Occurrence only — marks are theoretical and there is no
        fill model, so these are NOT P&L. Butterfly is excluded deliberately: it
        needs a GEX pin and modelling one would manufacture setups. --no-census
        restores exact v1.0 behaviour.
v1.0 — 2026-07-11

Drives the REAL deployed engines over a multi-day 1-minute OHLC file (per symbol),
the way the bot would see them, and reports what would have fired and how it would
have resolved. Reads-only. Sits beside replay_confluence.py and reuses its loader.

WHAT IS EXACT (drives the actual modules, no reimplementation):
  - Regime labels               (regime_classifier + the four analysis engines)
  - v3 confluence scores         (regime_confluence — uncalibrated, informational)
  - ORB setups / stops           (orb_engine v3.2 — impulsive-origin stop, origin gate)
  - Entry gate                   (main.py v3.2 logic: ORB_FIRES_REGARDLESS_OF_REGIME)
  - Setup grade / B-threshold    (setup_scorer)
  - Structure-stop outcome       (exit_engine v3.1 rule, evaluated on the underlying)
  - VIX no-entry gate + macro dim (real VIX series)

WHAT IS MODELED (clearly not exact — no option chain in an OHLC file):
  - Option premium & dollar P&L via Black-Scholes off the VIX level. Enable with
    --model-premium. Assumptions, all documented at PremiumModel:
      * 0DTE by default (expiry 16:00 same session); --dte N for N-day expiry.
      * vol = VIX/100. Apt for index ORBs (SPX/QQQ/DIA). For SINGLE STOCKS the
        single-name IV differs from VIX, so single-stock premium P&L is a rough
        proxy — treat it as relative, not a fill-accurate statement.
      * European BS, no smirk, no bid/ask, no early-fill slippage.
    The signal/regime/ORB/structure layer is exact regardless of this flag.

FIDELITY NOTES:
  - Intraday timeframes (1m/5m/15m) are SESSION-SCOPED (reset each session), matching
    the live feed's "never padded across the overnight gap." Higher timeframes
    (1h/4h/1d) use full continuous multi-day history, matching the feed store. This
    is why multi-day tape is required: on one session 1h is starved and direction
    collapses to NEUTRAL. ~15+ sessions gives 1h real depth.
  - 1d/4h are synthesized from the tape; over a ~month they are short (<55 bars) and
    contribute NEUTRAL, same as the live feed's thin daily backfill.
  - macro.is_fed_day defaults False (no FOMC calendar here); pass --fed-days to mark.

USAGE:
  python tests/backtest_harness.py --symbol CVX_1m_30d.csv --vix VIX_1m_30d.csv
  python tests/backtest_harness.py --symbol CVX_1m_30d.csv --vix VIX_1m_30d.csv --model-premium --dte 0
"""
import sys, os, argparse
from datetime import time as dtime, datetime
from zoneinfo import ZoneInfo
from collections import Counter
import math
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.replay_confluence import load_ohlc, resample
import analysis.orb_engine as OE
from analysis.volatility_engine import get_volatility_engine
from analysis.trend_engine import get_trend_engine
from analysis.structure_analyzer import get_structure_analyzer
from analysis.liquidity_mapper import get_liquidity_mapper
from analysis.regime_classifier import get_regime_classifier, Regime
try:
    from analysis.regime_confluence import RegimeConfluenceScorer
    _HAS_CONFLUENCE = True
except Exception:
    _HAS_CONFLUENCE = False
from config import (REGIME_REASSESS_MINUTES, ORB_FIRES_REGARDLESS_OF_REGIME,
                    VIX_NO_ENTRY_THRESHOLD, VIX_LOW_THRESHOLD,
                    VIX_ELEVATED_THRESHOLD, VIX_CRISIS_THRESHOLD)

ET = ZoneInfo("America/New_York")
_CLOCK = {"t": None}
OE.now_et = lambda: _CLOCK["t"]
OE.is_past_entry_cutoff = lambda: (_CLOCK["t"].hour, _CLOCK["t"].minute) >= (11, 0)

RTH_OPEN, RTH_CLOSE, HARD_CLOSE = dtime(9, 30), dtime(16, 0), dtime(15, 45)
RANGE_END, ORB_CUTOFF = dtime(9, 35), dtime(11, 0)


# ───────────────────────── data prep ─────────────────────────
def prep(path):
    df = load_ohlc(path)
    if df.index.tz is None:
        df.index = df.index.tz_localize(ET)
    df = df[(df.index.time >= RTH_OPEN) & (df.index.time <= RTH_CLOSE)]
    return df


def vix_asof(vix_df, ts):
    """Last VIX close at or before ts (as-of merge, one lookup)."""
    sub = vix_df.loc[:ts]
    return float(sub["close"].iloc[-1]) if len(sub) else float("nan")


def macro_from_vix(vix, fed=False):
    if vix >= VIX_CRISIS_THRESHOLD:      reg = "CRISIS"
    elif vix >= VIX_ELEVATED_THRESHOLD:  reg = "ELEVATED"
    elif vix < VIX_LOW_THRESHOLD:        reg = "LOW"
    else:                                reg = "NORMAL"
    from types import SimpleNamespace
    # macro_context (RISK_ON/RISK_OFF/NEUTRAL) comes from the macro calendar /
    # market_brief in production; not derivable from price+VIX alone, so NEUTRAL.
    return SimpleNamespace(vix=vix, vix_regime=reg, is_fed_day=fed,
                           macro_context="NEUTRAL",
                           vix_no_entry=(vix >= VIX_NO_ENTRY_THRESHOLD))


# ───────────────────────── premium model ─────────────────────────
class PremiumModel:
    """Black-Scholes premium off the VIX level. MODELED — see header caveats."""
    def __init__(self, dte=0, r=0.045):
        self.dte, self.r = dte, r

    def _t_years(self, now_ts):
        if self.dte > 0:
            return max(self.dte, 0.5) / 252.0
        # 0DTE: fraction of the RTH day remaining to 16:00, floored so theta is finite
        end = now_ts.replace(hour=16, minute=0, second=0)
        mins = max((end - now_ts).total_seconds() / 60.0, 5.0)
        return (mins / 390.0) / 252.0

    @staticmethod
    def _norm_cdf(x):
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    def price(self, S, K, vix, now_ts, call=True):
        T = self._t_years(now_ts)
        sig = max(vix, 1.0) / 100.0
        if T <= 0 or sig <= 0:
            intr = max(S - K, 0) if call else max(K - S, 0)
            return intr
        d1 = (math.log(S / K) + (self.r + sig * sig / 2) * T) / (sig * math.sqrt(T))
        d2 = d1 - sig * math.sqrt(T)
        if call:
            return S * self._norm_cdf(d1) - K * math.exp(-self.r * T) * self._norm_cdf(d2)
        return K * math.exp(-self.r * T) * self._norm_cdf(-d2) - S * self._norm_cdf(-d1)


# ───────────────────────── regime timeline ─────────────────────────
class _BarClock:
    """Make a strategy's datetime.now(ET) return the BAR's time, not wall clock.

    IronCondor.decide() gates on datetime.now(ET) against an 11:11-14:00 ET
    entry window, and butterfly does the same for its own cutoff. In a backtest
    that reads real wall clock, so a run started at 18:00 sees every bar as
    "past cutoff" and reports zero setups forever — which looks exactly like a
    broken strategy and is not one. Patch per evaluation so the strategy sees
    the simulated time it is actually being asked about.
    """

    def __init__(self, module, ts):
        self.module, self.ts = module, ts

    def __enter__(self):
        real = self.module.datetime
        ts = self.ts

        class _DT(real):
            @classmethod
            def now(cls, tz=None):
                return ts.astimezone(tz) if tz is not None else ts

        self._real = real
        self.module.datetime = _DT
        return self

    def __exit__(self, *a):
        self.module.datetime = self._real


def _synth_chain(bs, spot, vix, now_ts):
    """A modelled 0DTE chain, priced with the SAME Black-Scholes model the
    harness already uses for --model-premium.

    WHY THIS EXISTS: continuation, sweep and condor all need a chain — for
    strike selection and for the ATM-straddle expected move. A price-only tape
    has none, which is why v1.0 could only evaluate ORB. Modelling the chain
    lets their ENTRY LOGIC be exercised over real tape.

    WHAT THIS IS NOT: a fill model. Marks here are theoretical, spreads are
    synthetic, and liquidity is assumed. Treat every non-ORB number as
    "how often did the entry conditions occur", NEVER as P&L. Butterfly is
    deliberately still excluded — it needs a GEX pin, which cannot be modelled
    from price alone, and faking one would invent setups that never existed.
    """
    from data.options_chain import OptionsChain, OptionContract
    vixv = float(vix or 16.0)
    iv = max(0.05, vixv / 100.0)
    step = 1.0 if spot < 100 else (5.0 if spot > 1000 else 2.5)
    calls, puts = [], []
    for k in [round((spot + i * step) / step) * step for i in range(-12, 13)]:
        for side, bucket in (("call", calls), ("put", puts)):
            try:
                mk = bs.price(spot, k, vixv, now_ts, call=(side == "call"))
            except Exception:                                   # noqa: BLE001
                mk = max(0.01, (spot - k) if side == "call" else (k - spot))
            mk = round(max(0.01, mk), 2)
            bucket.append(OptionContract(
                symbol=f"SYN{k}{side[0].upper()}", underlying="SYN",
                expiry="", option_type=side, strike=float(k),
                bid=round(max(0.01, mk - 0.02), 2), ask=round(mk + 0.02, 2),
                mark=mk, delta=0.5, gamma=0.05, theta=-0.1, vega=0.08, iv=iv,
                open_interest=5000, volume=2000, streamer_symbol=""))
    return OptionsChain(underlying="SYN", expiry="", spot_price=spot,
                        iv_rank=50.0, calls=calls, puts=puts)


def build_regime_timeline(df, vix_df, fed_days, cadence_min, _census=None):
    """Returns {timestamp -> (regime_label, RegimeState, confluence_dict)} at cadence."""
    d5c, d15c, d1hc = resample(df, "5min"), resample(df, "15min"), resample(df, "1h")
    d4hc, d1dc = resample(df, "4h"), resample(df, "1D")
    volE, trE, stE, lqE = (get_volatility_engine(), get_trend_engine(),
                           get_structure_analyzer(), get_liquidity_mapper())
    clf = get_regime_classifier()
    conf = RegimeConfluenceScorer() if _HAS_CONFLUENCE else None
    idx = df.index
    days = sorted(set(idx.date))
    timeline = {}
    for d in days:
        sess_start = pd.Timestamp(datetime.combine(d, RTH_OPEN), tz=ET)
        sess = [t for t in idx if t.date() == d and RANGE_END <= t.time() <= RTH_CLOSE]
        fed = d in fed_days
        for i, t in enumerate(sess):
            if i % cadence_min != 0:
                continue
            _CLOCK["t"] = t.to_pydatetime()
            price = float(df.loc[t, "close"])
            # intraday session-scoped; HTF continuous
            s5  = d5c[(d5c.index >= sess_start) & (d5c.index <= t)]
            s15 = d15c[(d15c.index >= sess_start) & (d15c.index <= t)]
            s1h = d1hc[d1hc.index <= t]
            s4h = d4hc[d4hc.index <= t]
            s1d = d1dc[d1dc.index <= t]
            if len(s5) < 5:
                continue
            vix = vix_asof(vix_df, t)
            macro = macro_from_vix(vix, fed)
            try:
                vs = volE.analyze(s5, s1h if len(s1h) else s5, price)
                tr = trE.analyze({"1m": df[(df.index >= sess_start) & (df.index <= t)],
                                  "5m": s5, "15m": s15, "1h": s1h, "4h": s4h, "1d": s1d})
                st = stE.analyze(s5, s15, s1h if len(s1h) else None, price)
                lq = lqE.analyze(s5, s15, price)
                rc = clf.classify(vs, tr, st, lq, macro=macro, trigger="backtest")
            except Exception:
                continue
            # ── v1.1: STRATEGY ATTEMPT CENSUS ───────────────────────────
            # v1.0 drove ORB only, so "how often does each strategy actually
            # get a setup" was unanswerable offline — which is exactly how
            # ContinuationStrategy went weeks without ever producing a valid
            # signal and nobody noticed. Everything these need (vs/tr/st/lq/rc)
            # is already computed above; only the chain was missing, and that
            # is now modelled. Butterfly stays excluded on purpose: it requires
            # a GEX pin, and inventing one would manufacture setups.
            if _census is not None:
                _sc = _synth_chain(_census["bs"], price, macro.vix, t)
                _df1 = df[(df.index >= sess_start) & (df.index <= t)]
                for _name, _fn in (
                    ("Continuation", lambda: _census["cont"].generate_signal(
                        regime=rc, vol_state=vs, trend=tr, chain=_sc,
                        current_price=price, structure=st, df_1m=_df1,
                        macro=macro)),
                    ("SweepReversal", lambda: _census["sweep"].generate_signal(
                        regime=rc, vol_state=vs, structure=st, liq_map=lq,
                        chain=_sc, macro=macro, df_1m=_df1, current_price=price)),
                    ("IronCondor", lambda: _census["condor_run"](rc, vs, _sc,
                                                                 macro, price, t)),
                ):
                    _c = _census["stats"][_name]
                    _c["evals"] += 1
                    try:
                        _sig = _fn()
                    except Exception as _e:                       # noqa: BLE001
                        _c["raised"] += 1
                        _c["last_error"] = f"{type(_e).__name__}: {_e}"
                        continue
                    if _sig is None:
                        continue
                    _c["setups"] += 1
                    _c["by_regime"][str(rc.primary_regime)] = \
                        _c["by_regime"].get(str(rc.primary_regime), 0) + 1
                    _iv = getattr(_sig, "is_valid", None)
                    _ok = bool(_iv() if callable(_iv) else _iv) \
                        if _iv is not None else True
                    if _ok:
                        _c["valid"] += 1
                    else:
                        _c["invalid"] += 1

            cdict = None
            if conf is not None:
                try:
                    cdict = conf.score(vs, tr, st, lq)
                except Exception:
                    cdict = None
            timeline[t] = (rc.primary_regime, rc, vs, st, lq, macro, cdict)
    return timeline


def regime_at(timeline, ts):
    """Nearest prior regime evaluation to ts (the label the bot would hold)."""
    prior = [k for k in timeline if k <= ts]
    return timeline[max(prior)] if prior else None


# ───────────────────────── ORB engine per session ─────────────────────────
def orb_setups(df):
    idx = df.index
    days = sorted(set(idx.date))
    out = []
    for d in days:
        sess = df[df.index.date == d]
        ix = sess.index
        first = sess[(ix.time >= RTH_OPEN) & (ix.time < RANGE_END)]
        if len(first) == 0:
            continue
        oh, ol = float(first["high"].max()), float(first["low"].min())
        if oh - ol <= 0:
            continue
        e = OE.ORBEngine()
        e._data.orb_high, e._data.orb_low, e._data.orb_width = oh, ol, oh - ol
        e._range_date = ix[0].strftime("%Y-%m-%d")
        e._data.state = OE.ORBState.WAITING_FOR_BREAK
        for k in range(2, len(sess) + 1):
            sub = sess.iloc[:k]
            _CLOCK["t"] = ix[k - 1].to_pydatetime()
            dd = e.update(None, sub, float(sub["close"].iloc[-1]), regime=None)
            if dd.state in (OE.ORBState.OPEN_LONG, OE.ORBState.OPEN_SHORT):
                out.append(dict(
                    day=d, t=ix[k - 1],
                    long=(dd.state == OE.ORBState.OPEN_LONG),
                    entry=float(sub["close"].iloc[-2]),
                    stop=dd.stop_level,
                    target=dd.target_100pct,
                    orb_high=oh, orb_low=ol,
                ))
                e.notify_position_closed()
    return out


# ───────────────────────── gate + structure outcome ─────────────────────────
def orb_fires(regime_label):
    ok = (Regime.TRENDING_BULL, Regime.TRENDING_BEAR, Regime.BREAKOUT_VOLATILE,
          Regime.RANGING, Regime.COMPRESSION)
    if regime_label in ok:
        return True
    return ORB_FIRES_REGARDLESS_OF_REGIME and regime_label in (Regime.UNKNOWN, Regime.SWEEP_REVERSAL)


def _result(outcome, t, xp, bars, setup, risk, prem_entry, prem_exit):
    long = setup["long"]
    under_R = (((xp - setup["entry"]) if long else (setup["entry"] - xp)) / risk) if risk > 0 else 0.0
    prem_pct = None
    if prem_entry is not None and prem_entry > 1e-6:
        prem_pct = (prem_exit - prem_entry) / prem_entry * 100
    return dict(outcome=outcome, exit_ts=t, exit_price=xp, bars=bars,
                under_R=under_R, prem_entry=prem_entry, prem_exit=prem_exit,
                prem_pnl_pct=prem_pct)


def simulate_trade(df, vix_df, setup, pm=None):
    """Faithful two-stop AND exit on the underlying + (optional) modeled premium.
    Per bar, in order: structure stop (1m close beyond impulsive origin),
    −25% premium floor (modeled premium ≤ 75% of entry), target (intrabar).
    Whichever fires first. Matches exit_engine v3.1 (structure) + the −25% floor."""
    idx = df.index
    ki = list(idx).index(setup["t"])
    stop, tgt, long, entry = setup["stop"], setup["target"], setup["long"], setup["entry"]
    risk = (entry - stop) if long else (stop - entry)
    K = tgt  # bot buys near the projected-target strike
    prem_entry = floor = None
    if pm is not None:
        prem_entry = pm.price(entry, K, vix_asof(vix_df, setup["t"]),
                              setup["t"].to_pydatetime(), call=long)
        floor = 0.75 * prem_entry
    for j in range(ki + 1, len(df)):
        t = idx[j]
        if t.date() != setup["day"] or t.time() >= HARD_CLOSE:
            break
        c = float(df["close"].iloc[j]); hi = float(df["high"].iloc[j]); lo = float(df["low"].iloc[j])
        prem_c = pm.price(c, K, vix_asof(vix_df, t), t.to_pydatetime(), call=long) if pm else None
        # 1) −25% premium floor (theta / retracement / mix) — tick-level in life,
        #    so it front-runs the close-based structure stop; modeled fill AT the
        #    floor (a 1m bar can close past it, but the stop would have caught -25%).
        if pm is not None and prem_entry and prem_entry > 1e-6 and prem_c <= floor:
            return _result("PREMIUM_FLOOR", t, c, j - ki, setup, risk, prem_entry, floor)
        # 2) structure stop — close beyond the impulsive origin (premium here is
        #    guaranteed above -25%, since the floor above did not fire)
        if (long and c < stop) or ((not long) and c > stop):
            return _result("STRUCTURE_STOP", t, c, j - ki, setup, risk, prem_entry, prem_c)
        # 3) target — intrabar reach of the 100% projection
        if (long and hi >= tgt) or ((not long) and lo <= tgt):
            prem_t = pm.price(tgt, K, vix_asof(vix_df, t), t.to_pydatetime(), call=long) if pm else None
            return _result("TARGET", t, tgt, j - ki, setup, risk, prem_entry, prem_t)
    # flatten at 15:45
    day_df = df[(df.index.date == setup["day"]) & (df.index.time < HARD_CLOSE)]
    xt = day_df.index[-1] if len(day_df) else setup["t"]
    xp = float(day_df["close"].iloc[-1]) if len(day_df) else entry
    prem_x = pm.price(xp, K, vix_asof(vix_df, xt), xt.to_pydatetime(), call=long) if pm else None
    return _result("EOD_FLAT", xt, xp, 0, setup, risk, prem_entry, prem_x)


# ───────────────────────── main ─────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True, help="per-symbol 1m OHLC CSV")
    ap.add_argument("--vix", required=True, help="1m VIX CSV, same window")
    ap.add_argument("--model-premium", action="store_true", help="add modeled BS premium P&L")
    ap.add_argument("--dte", type=int, default=0, help="days to expiry for the premium model (0=0DTE)")
    ap.add_argument("--fed-days", default="", help="comma YYYY-MM-DD FOMC dates")
    ap.add_argument("--all", action="store_true",
                    help="show every fired trade, not just the first 8")
    ap.add_argument("--json", default="",
                    help="APPEND every fired trade as jsonl to this path "
                         "(for pooling across symbols; delete the file first)")
    ap.add_argument("--no-census", action="store_true",
                    help="skip the non-ORB strategy attempt census (v1.0 behaviour)")
    args = ap.parse_args()

    sym = os.path.splitext(os.path.basename(args.symbol))[0].split("_")[0]
    df = prep(args.symbol)
    vix_df = prep(args.vix)
    fed_days = set()
    for s in [x.strip() for x in args.fed_days.split(",") if x.strip()]:
        fed_days.add(datetime.strptime(s, "%Y-%m-%d").date())
    days = sorted(set(df.index.date))

    print(f"\n{'='*66}\nBACKTEST — {sym} — {len(days)} sessions "
          f"({days[0]} → {days[-1]})\n{'='*66}")
    vlo, vhi = float(vix_df['close'].min()), float(vix_df['close'].max())
    print(f"VIX {vlo:.1f}–{vhi:.1f} (no-entry ≥{VIX_NO_ENTRY_THRESHOLD}: "
          f"{'never triggers' if vhi < VIX_NO_ENTRY_THRESHOLD else 'TRIGGERS on some bars'})")

    # 1) regime timeline
    cad = max(REGIME_REASSESS_MINUTES, 1)
    # v1.1 — strategy attempt census. Built here so the loop stays hot; None
    # disables it entirely (--no-census) and the harness behaves exactly as v1.0.
    _census = None
    if not args.no_census:
        try:
            from strategy.continuation_strategy import ContinuationStrategy
            from strategy.sweep_reversal_strategy import SweepReversalStrategy
            from strategy.iron_condor_strategy import IronCondorStrategy
            _census = {
                "bs": PremiumModel(dte=args.dte),
                "cont": ContinuationStrategy(),
                "sweep": SweepReversalStrategy(),
                "condor": IronCondorStrategy(),
                "condor_mod": sys.modules["strategy.iron_condor_strategy"],
                "stats": {n: {"evals": 0, "setups": 0, "valid": 0, "invalid": 0,
                              "raised": 0, "last_error": "", "by_regime": {}}
                          for n in ("Continuation", "SweepReversal", "IronCondor")},
            }
            def _condor_run(rc_, vs_, sc_, macro_, price_, ts_):
                with _BarClock(_census["condor_mod"], ts_):
                    return _census["condor"].decide(
                        regime=rc_, vol_state=vs_, chain=sc_, macro=macro_,
                        current_price=price_)
            _census["condor_run"] = _condor_run
        except Exception as exc:                                  # noqa: BLE001
            print(f"  (census disabled — {type(exc).__name__}: {exc})")
            _census = None

    timeline = build_regime_timeline(df, vix_df, fed_days, cad, _census)
    dist = Counter(v[0] for v in timeline.values())
    tot = sum(dist.values())
    print(f"\n── REGIME DISTRIBUTION ({tot} evals @ {cad}-min) ──")
    for k, v in dist.most_common():
        print(f"  {str(k):20}{v:5}  {100*v/max(tot,1):4.0f}%")

    # 2) ORB setups + gate + structure outcome
    setups = orb_setups(df)
    pm = PremiumModel(dte=args.dte) if args.model_premium else None
    fired, blocked = [], 0
    for s in setups:
        r = regime_at(timeline, s["t"])
        label = r[0] if r else Regime.UNKNOWN
        s["regime"] = label
        if not orb_fires(label):
            blocked += 1
            continue
        res = simulate_trade(df, vix_df, s, pm=pm)
        s.update(res)
        fired.append(s)

    if _census is not None:
        print(f"\n── STRATEGY ATTEMPTS (modelled chain — occurrence, NOT P&L) ──")
        for _n, _c in _census["stats"].items():
            _pct = 100.0 * _c["setups"] / max(1, _c["evals"])
            print(f"  {_n:<14} evals {_c['evals']:>5}   setups {_c['setups']:>4} "
                  f"({_pct:4.1f}%)   valid {_c['valid']:>4}   "
                  f"invalid {_c['invalid']:>3}   raised {_c['raised']:>4}")
            if _c["by_regime"]:
                _top = sorted(_c["by_regime"].items(), key=lambda kv: -kv[1])[:4]
                print(f"                 under: "
                      + "  ".join(f"{k}={v}" for k, v in _top))
            if _c["raised"]:
                print(f"                 !! {_c['last_error'][:78]}")
        print(f"  Butterfly       excluded — needs a GEX pin; price-only tape "
              f"cannot provide one")

    print(f"\n── ORB (gate applied) ──")
    print(f"  setups detected: {len(setups)}   fired: {len(fired)}   blocked by regime gate: {blocked}")
    if fired:
        wins = sum(1 for s in fired if s["outcome"] == "TARGET")
        stru = sum(1 for s in fired if s["outcome"] == "STRUCTURE_STOP")
        flr  = sum(1 for s in fired if s["outcome"] == "PREMIUM_FLOOR")
        eod  = sum(1 for s in fired if s["outcome"] == "EOD_FLAT")
        print(f"  long/short: {sum(s['long'] for s in fired)}/{sum(not s['long'] for s in fired)}")
        print(f"  exits:  TARGET {wins}  STRUCTURE_STOP {stru}  PREMIUM_FLOOR {flr}  EOD_FLAT {eod}")
        import statistics as st
        print(f"  underlying expectancy: {st.mean([s['under_R'] for s in fired]):+.2f}R  "
              f"median {st.median([s['under_R'] for s in fired]):+.2f}R")
        print(f"  fired under which regime label:")
        for k, v in Counter(s["regime"] for s in fired).most_common():
            print(f"     {str(k):18}{v}")
        if pm:
            pnls = [s["prem_pnl_pct"] for s in fired]
            print(f"  MODELED premium P&L (BS off VIX, {'0DTE' if args.dte==0 else str(args.dte)+'DTE'}): "
                  f"mean {st.mean(pnls):+.0f}%  median {st.median(pnls):+.0f}%  "
                  f"[modeled — not fill-accurate; VIX-vol proxy]")
        print(f"\n  sample fired setups:")
        # v1.2 — `--all` lifts the 8-trade display cap. The cap is fine for a
        # human reading one symbol; it makes per-trade R BY REGIME impossible to
        # pool across 29 symbols, which is exactly what item AH needs.
        _show = fired if args.all else fired[:8]
        if args.all and len(fired) > 8:
            print(f"    (--all: showing all {len(fired)})")
        for s in _show:
            extra = f" prem {s['prem_pnl_pct']:+.0f}%" if pm else ""
            print(f"    {s['t'].strftime('%m-%d %H:%M')} {'L' if s['long'] else 'S'} "
                  f"{str(s['regime']):16} entry={s['entry']:.2f} stop={s['stop']:.2f} "
                  f"-> {s['outcome']:14} {s['under_R']:+.2f}R{extra}")

        # v1.2 — `--json PATH` writes EVERY fired trade as one JSON object per
        # line. Text output is for reading; this is for pooling. Without it AH's
        # question ("is ORB-in-RANGING negative ACROSS symbols?") can only be
        # answered from a truncated sample, and a truncated sample of the first 8
        # chronologically is not a random sample — it is the start of the window.
        if args.json:
            import json as _json
            with open(args.json, "a") as _fh:
                for s in fired:
                    _fh.write(_json.dumps({
                        "symbol": sym,
                        "ts": s["t"].isoformat(),
                        "long": bool(s["long"]),
                        "regime": str(s["regime"]),
                        "entry": round(float(s["entry"]), 4),
                        "stop": round(float(s["stop"]), 4),
                        "outcome": s["outcome"],
                        "under_R": round(float(s["under_R"]), 4),
                        "prem_pnl_pct": (round(float(s["prem_pnl_pct"]), 2)
                                         if pm and s.get("prem_pnl_pct") is not None
                                         else None),
                    }) + "\n")
            print(f"    [--json] appended {len(fired)} trade(s) to {args.json}")


if __name__ == "__main__":
    main()
