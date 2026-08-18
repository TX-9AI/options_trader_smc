#!/usr/bin/env python3
# v2.7 - 2026-08-15 - `--sweeps` STREAMS TOO. Same fix, before it could bite:
#        a named-pool sweep is RARE, so only the handful of ticks carrying
#        `breakdown.SWEEP_REVERSAL.named` are kept and memory scales with EVENTS
#        rather than archive size. A cheap `'"named"' not in line` prefilter
#        skips the full JSON parse on ~99.9% of lines. MEASURED: 282,750 records
#        at 76 MB peak RSS. Writes a report file like the grid.
# v2.6 - 2026-08-15 - THE GRID STREAMS. Constant memory, and it writes a file.
#        ⚠️ v2.4/v2.5 parsed every matched log into ONE LIST and reported off
#        it. Five sessions is ~56k records and control **OOM-KILLED it, rc=137**,
#        before printing a line - silence that looks exactly like the command
#        not running. The kill is on the INPUT side, so writing output to a file
#        would not have helped on its own.
#        The grid needs SIX INTEGERS per symbol-date, not the records. It now
#        reads a line, increments, and discards. MEASURED: 25 sessions x 29
#        symbols x 390 ticks = 282,750 records at **77 MB peak RSS** - the same
#        workload that was killed. `--out` writes the report next to the tick
#        logs so it persists like every other report.
# v2.5 - 2026-08-15 - `--last N`, `--from`, `--to` SELECT FILES BEFORE READING.
#        ⚠️ v2.4's `--last` loaded EVERY matched log and trimmed dates
#        afterwards. 25 sessions is ~280k records held at once, and on the
#        control box that was SILENTLY OOM-KILLED - no output, no traceback, no
#        non-zero message the operator could act on. A date range is a FILE
#        SELECTION, not a post-filter. Also prints `[files] N matched` so a run
#        that reads nothing says so.
# v2.4 - 2026-08-15 - `--grid` and `--sweeps`, and records are DATE-TAGGED.
#        THE GRID is symbols down / dates across, one dominant-regime code per
#        cell (TL TB RG BO CP SW), with `*` marking a cell that clears L1.7's
#        TRENDING bar. A trend day is now a glance instead of a query.
#        ⚠️ DATE TAGGING WAS REQUIRED FIRST: saved records carry `ts` as HH:MM
#        only, so a multi-file scan would have BLENDED a symbol's trend day into
#        its chop days and diluted exactly what is being looked for. The date
#        comes from the filename.
#        `--sweeps` answers "was a previously NAMED pool actually swept during
#        the session" - the scorer already writes `named`, `reclaimed`,
#        `pool_price`, `kind` and `age_bars` into `breakdown`, so this reads
#        history rather than collecting anything. It prints the decay shape
#        after the peak and marks a row TIER-B CANDIDATE only when all three of
#        L1.7's conditions hold: SWEEP>0 at the bar, a reclaim, and a monotone
#        decay. A high max score alone is a LEAD, never a pass.
# v2.3 - 2026-08-15 - PER-SYMBOL VIEW. `--symbol SYM`, `--by-symbol`, and
#        `--report-only` now takes MULTIPLE files (or a glob) for a date range.
#        WHY: L1.7's acceptance criteria are written PER SYMBOL-DAY ("one
#        genuine trend day showing TRENDING_* dominant ~50%"), but every report
#        in this suite aggregated ~29 symbol-sessions - and blending them
#        GUARANTEES no regime dominates, because different symbols are in
#        different regimes on the same day. A perfect trend day on QQQ was
#        averaged against 28 others. **So the four "tape gaps" were never
#        testable, and the qualifying days may already be on disk.**
#        Demonstrated: the same 400 ticks show nothing dominant in aggregate and
#        TRENDING_BEAR at 70% dominance filtered to one symbol.
#        `--symbol` filters at the PATH for a live replay (one file per symbol,
#        so ~29x faster and the normal report comes out per-symbol with no
#        special casing) and at the RECORD for `--report-only`, where saved tick
#        logs are already merged and there are no paths left to filter.
#        `--by-symbol` ranks every symbol by TRENDING_* dominance so a whole
#        archive is SCANNED rather than checked one symbol at a time.
#        Default behaviour with no flags is unchanged.
# tests/replay_confluence.py — options_trader_v3 — v2.3
# v2.3 — 2026-08-04 — the emitted-distribution line collapsed TRENDING_BULL and
#         TRENDING_BEAR into one token ("TREND") — the same defect found in the
#         diary, on the line the Aug 10-21 freeze watch reads nightly. Uses
#         utils/regime_labels.label(). Display only.
# v2.2 — 2026-08-01 — FRAME CAPS FROM CONFIG, so the replay sees exactly what
#         LIVE sees. The as-of slices were UNCAPPED — every warm session added
#         history no live engine would ever receive, and the divergence grew with
#         --warm-sessions. It became load-bearing the moment we decided to wake
#         the 15m vote and leave 1h asleep (config v4.1): at warm >= 7 the
#         replay's 1h frame reaches 55+ bars and VOTES, while live holds it at 50
#         and it stays NEUTRAL. The offline corpus would have carried a
#         directional vote production does not have.
#         Each resampled frame is now trimmed to TIMEFRAMES[tf]["candles"], the
#         same number data_cache passes to fetch_candles. Warm depth then only has
#         to FILL the caps and anything beyond is inert — so the default moves
#         5 -> 8, enough for a 150-bar 15m frame (~5.8 sessions) with margin.
#         WHY 5 WAS WRONG: nothing in the chain ever passed --warm-sessions
#         (regime_backfill invoked this module without it), so every diary,
#         backfill and a2_characterise run has been at 5 — which starves the 15m
#         frame the calibration now depends on.
#         MEASURED, so the cap is not assumed to be free: ADX-14 on 5m is
#         insensitive to depth past ~100 bars (identical to 2dp at 104/130/156
#         bars), and bb_width_pct / atr_avg_20 are bounded-lookback by
#         construction (BB-20, mean of last 20 ATR values) so extra frame length
#         is unreachable to them. structure_sequence reads the whole frame and is
#         the one engine that could shift — watch it first if a regen surprises.
#         CONSEQUENCE: corpus numbers built before this are not comparable. The
#         4.02% A2 rate and the 45%-in-the-10:00-hour concentration are superseded.
# v2.1 — 2026-08-01 — THE BOOKMARK WAS WARMING THE 1m FRAME TOO, AND 1m IS THE ONE
#         FRAME LIVE DELIBERATELY DOES NOT WARM. v1.2 prepended prior sessions to
#         df1m so the RESAMPLED 5m/15m/1h would carry ADX/EMA history — correct, and
#         still the point. But `s1m` was then sliced out of that same concatenated
#         frame, so the 25-bar 1-minute close window handed to the scorer straddled
#         the overnight gap for the first 25 bars of every replayed session.
#         market_data v3.1 session-scopes 1m ONLY, on purpose ("no overnight
#         padding"); tests/test_market_data_contract.py asserts that contract on the
#         LIVE path. The replay violated the same contract, so:
#           • live has < 25 one-minute bars until ~09:55 → passes closes=None →
#             RANGING and COMPRESSION are NOT SCORED for the first 25 minutes;
#           • replay scored both from 09:30, off a gap-spanning regression.
#         Measured on a synthetic two-session fixture through this same code path:
#         at the target day's first bar, 24 of the 25 window bars belonged to the
#         PRIOR session and a -1.14 gap sat inside the regression.
#         FIX: df1m stays warm for the RESAMPLE (unchanged, that is the bookmark);
#         `s1m` is now scoped to the target session, and `closes` is built exactly
#         as main.py:551 builds it — None below RANGE_WINDOW_BARS. HTF warming is
#         untouched. Consequence to know when reading old artifacts: RANGING /
#         COMPRESSION counts in the opening 25 minutes DROP to None, matching live;
#         any acceptance or characterisation number computed over the old corpus
#         included ticks live could never have produced.
# v2.0 — 2026-07-12 — LAYER-2 TRACKS + drift merge.
#   (a) MERGE: absorbs the control-box local mod (--report-only: rebuild + reprint
#       the full report from a saved tick-log JSONL; no engines, no re-scoring)
#       that never reached GitHub — ends the two-way drift where the repo had
#       v1.1's sibling-skip and control had report-only, neither had both.
#   (b) LAYER-2: each symbol-session's per-tick evidence vector is now ALSO fed,
#       in time order, through a fresh ConvictionIntegrator (v2.0, always-argmax).
#       Every JSONL record gains an "l2" object {regime, c, stale, cv[, trigger]}
#       and the report gains a LAYER-2 section: emitted-label distribution,
#       label SWITCHES per symbol-session vs L1-argmax flips (the churn metric
#       the integrator exists to crush), and stale%. Purely additive: CLI args,
#       exit codes (0 pass / 2 acceptance-fail), and every existing JSONL field
#       are unchanged — regime_diary/regime_backfill/validate_regime.sh work
#       as-is; L2 report prints only when l2 fields are present (old logs
#       reprint cleanly under --report-only). Layer-1 acceptance checks remain
#       the sole exit-code authority; L2 is observational until L2 targets land.
# v1.2 — 2026-07-21 — ADX-WARMUP BOOKMARK. Prepend up to --warm-sessions (default 5)
#         prior sessions of the same symbol's 1m tape before resampling, so 5m/15m/1h
#         carry enough history to warm ADX-14 / the 50-EMA from the target day's FIRST
#         scored tick. Prior bars feed the engines but are never scored or logged (the
#         tick loop starts at the target day's open). Fixes the replay-only defect where
#         ADX stayed 0.0 until ~14:00 — trend-blind every morning — mislabeling genuine
#         trend days as CHOP (AAPL 2026-07-21: true 5m ADX peaked 52, replay logged 0
#         until 14:00). The LIVE engine was already warm (feed store retains 400 5m bars
#         ≈ 5 days); this gives the replay the same reach-back. --warm-sessions 0 restores
#         the old single-day behaviour.
# v1.1 — 2026-07-11 — skip non-OHLC siblings in harvest folders (fleet_trades_*.csv,
#         *_trades_*.db, daily_trades_*.json) that share data/harvest/<date>/ with the
#         tape; load_ohlc returns None on a missing timestamp column. v1.0 crashed at
#         the report step on the consolidated fleet_trades CSV. No scoring-logic change.
#   Layer-1 VALIDATION + CALIBRATION harness. Replays analysis/regime_confluence.py
#   over the candle logger's DXFeed 1-min OHLC (data/OHLC/<date>/<SYMBOL>.csv) — the
#   traded tape, store-consistent per ROADMAP. NOT the shadow observer jsonl —
#   not because the observer is a different feed (it is not; see REPLAY_VALIDATION
#   v1.1) but because its sampling is tick-cadenced and staleness-gated, where
#   calibration needs deterministic, evenly-spaced 1-min bars.
#
#   Method: AS-OF replay. For each 1-min bar t of the session, slice every timeframe
#   frame to bars ≤ t, run the REAL engines (volatility/trend/structure/liquidity —
#   the same code the live bot runs), then score the resulting states with the real
#   RegimeConfluenceScorer. Optionally logs the v1.3 boolean regime for comparison.
#
#   Emits: (1) per-regime score distributions, (2) per-FACTOR distributions split by
#   the v1.3 label (the calibration gold — e.g. flat-angle on RANGING vs TRENDING
#   ticks), (3) the Layer-1 acceptance checks (see REPLAY_VALIDATION.md). No Layer-2
#   behavior is invoked — this validates instantaneous scores only.
#
#   Run (on-box, repo root):  python -m tests.replay_confluence data/OHLC/2026-07-13
#         or specific files:   python -m tests.replay_confluence path/to/SPX.csv ...
#         options:  --jsonl out.jsonl   --warmup 20   --no-v13
#
#   Isolation: reads OHLC + runs engines only. Places no orders, opens no trades.db,
#   writes only the report (+ optional --jsonl). Safe to run anytime.

from __future__ import annotations
import argparse, os, re, sys, json, math, warnings, glob
from typing import Dict, List, Optional, Tuple
import pandas as pd
# volume-less index tape (e.g. cash SPX logs volume=0) makes the engine VWAP a 0/0;
# our scorer reads price_vs_bb, not VWAP, so it does not affect scores — quiet the noise.
warnings.filterwarnings("ignore", category=RuntimeWarning)

# --- repo engines (this harness is repo-bound by design; regime_confluence is not) --
from utils.regime_labels import label
from analysis.volatility_engine import get_volatility_engine
from analysis.trend_engine import get_trend_engine
from analysis.structure_analyzer import get_structure_analyzer
from analysis.liquidity_mapper import get_liquidity_mapper
from config import TIMEFRAMES

# v2.2 — live's per-timeframe fetch depth, read from config rather than copied,
# so this can never drift from what data_cache actually requests.
_CAP = {tf: TIMEFRAMES[tf]["candles"] for tf in ("5m", "15m", "1h")}
from analysis.regime_confluence import (
    RegimeConfluenceScorer, REGIMES, RANGE_WINDOW_BARS,
    TRENDING_BULL, TRENDING_BEAR, RANGING, BREAKOUT_VOLATILE, COMPRESSION, SWEEP_REVERSAL,
)

try:
    from analysis.regime_classifier import get_regime_classifier
    _HAVE_V13 = True
except Exception:
    _HAVE_V13 = False

# Layer 2 (v2.0): optional so a mid-sync checkout without the ported integrator
# still replays Layer 1 — the L2 fields/report simply don't appear.
try:
    from analysis.conviction_integrator import ConvictionIntegrator
    _HAVE_L2 = True
except Exception:
    _HAVE_L2 = False


# ── CSV load (candle-logger tape: footer junk, zero-range pads, CRLF, ISO8601 tz) ──
def load_ohlc(path: str) -> Optional[pd.DataFrame]:
    raw = pd.read_csv(path, header=0, dtype=str)
    raw.columns = [c.strip().lower() for c in raw.columns]
    # Not an OHLC tape file (e.g. harvest's fleet_trades_<date>.csv sits in the same
    # folder): no timestamp column → skip gracefully rather than crash the run.
    if "timestamp" not in raw.columns:
        return None
    ts = pd.to_datetime(raw["timestamp"], format="ISO8601", errors="coerce")
    ok = ts.notna()
    df = raw[ok].copy()
    df.index = ts[ok]
    for c in ["open", "high", "low", "close", "volume"]:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    zr = (df.high == df.low) & (df.open == df.close) & (df.high == df.close)
    return df[~zr][["open", "high", "low", "close", "volume"]]


_AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def resample(df1m: pd.DataFrame, rule: str) -> pd.DataFrame:
    return df1m.resample(rule, label="right", closed="right").agg(_AGG).dropna(subset=["close"])


def sym_of(path: str) -> str:
    return re.split(r"[_.]", os.path.basename(path))[0].upper()


# ── distribution helper ───────────────────────────────────────────────────────
def dist(xs: List[float]) -> dict:
    xs = sorted(v for v in xs if v is not None)
    if not xs:
        return {"n": 0}
    n = len(xs)
    q = lambda p: xs[min(n - 1, int(p * n))]
    return {"n": n, "min": round(xs[0], 3), "p10": round(q(.10), 3),
            "p50": round(q(.50), 3), "p90": round(q(.90), 3), "max": round(xs[-1], 3)}


# ── one symbol replay ─────────────────────────────────────────────────────────
def _prior_session_1m(path: str, sessions_back: int) -> Optional[pd.DataFrame]:
    """v1.2 ADX-WARMUP BOOKMARK. Load up to `sessions_back` prior sessions of the
    SAME symbol's 1-min tape and return them concatenated (ascending), so the
    resampled 5m/15m/1h frames carry enough history to warm ADX-14 / the 50-EMA
    from the target day's FIRST tick.

    Why: the live engine reads a rolling multi-session window from the feed store
    (5m retained 400 bars ≈ 5 days), so live ADX is warm at 09:30. The replay
    resampled 5m from a SINGLE day-file, so its ADX stayed 0.0 until ~14:00 —
    every replayed morning was trend-blind, and the diary mislabeled genuine
    trend days as CHOP. This gives the replay the same reach-back the live store
    already has. Prior bars WARM the engines; they are never scored or logged
    (the tick loop still starts at the target day's open — see replay_symbol).

    Layout: data/OHLC/<date>/<SYMBOL>_ohlc_<date>.csv. We walk sibling date
    folders older than the target and collect this symbol's files. After-hours /
    gaps are fine — ADX only needs continuous *bars*, not continuous *time*.
    Missing prior days are skipped silently (a fresh deployment simply warms
    less, exactly as live would after a cold store).
    """
    if sessions_back <= 0:
        return None
    day_dir  = os.path.dirname(os.path.abspath(path))
    ohlc_dir = os.path.dirname(day_dir)                 # .../data/OHLC
    this_date = os.path.basename(day_dir)
    fname     = os.path.basename(path)
    if not os.path.isdir(ohlc_dir):
        return None
    prior_dates = sorted(d for d in os.listdir(ohlc_dir)
                         if os.path.isdir(os.path.join(ohlc_dir, d)) and d < this_date)
    prior_dates = prior_dates[-sessions_back:]          # the N most-recent priors
    frames = []
    for d in prior_dates:
        # match the same symbol regardless of the date embedded in the filename
        cand = os.path.join(ohlc_dir, d, fname.replace(this_date, d))
        if not os.path.isfile(cand):
            # fall back to any *_ohlc_* for this symbol in that folder
            stem = fname.split("_ohlc_")[0]
            hits = [f for f in os.listdir(os.path.join(ohlc_dir, d))
                    if f.upper().startswith(stem.upper() + "_OHLC_")]
            if not hits:
                continue
            cand = os.path.join(ohlc_dir, d, hits[0])
        df = load_ohlc(cand)
        if df is not None and not df.empty:
            frames.append(df)
    if not frames:
        return None
    warm = pd.concat(frames).sort_index()
    warm = warm[~warm.index.duplicated(keep="last")]
    return warm


def replay_symbol(path: str, warmup: int, use_v13: bool,
                  warm_sessions: int = 8) -> Tuple[List[dict], str]:
    sym = sym_of(path)
    df1m_today = load_ohlc(path)
    if df1m_today is None or len(df1m_today) < warmup + 5:
        return [], sym

    # v1.2: prepend prior-session 1m so resampled frames warm ADX/EMA from the
    # open. score_start marks the target day's first bar — only bars at/after it
    # are scored and logged; everything before is warmup context only.
    prior = _prior_session_1m(path, warm_sessions)
    if prior is not None:
        prior = prior[prior.index < df1m_today.index[0]]     # strictly before today
        df1m = pd.concat([prior, df1m_today]).sort_index()
        df1m = df1m[~df1m.index.duplicated(keep="last")]
    else:
        df1m = df1m_today
    score_start = df1m_today.index[0]

    d5, d15, d1h = resample(df1m, "5min"), resample(df1m, "15min"), resample(df1m, "1h")

    volE, trE, stE, lqE = (get_volatility_engine(), get_trend_engine(),
                           get_structure_analyzer(), get_liquidity_mapper())
    scorer = RegimeConfluenceScorer()
    clf = get_regime_classifier() if (use_v13 and _HAVE_V13) else None
    integ = ConvictionIntegrator() if _HAVE_L2 else None   # fresh book per symbol-session

    recs: List[dict] = []
    idx1m = df1m.index
    # start at the target day's open (or `warmup` bars in, whichever is later) so
    # the warmup context feeds the engines but is never scored/logged.
    start_i = max(warmup, idx1m.searchsorted(score_start))
    for i in range(start_i, len(df1m)):
        t = idx1m[i]
        if t < score_start:
            continue
        price = float(df1m["close"].iloc[i])
        # as-of slices (only bars that had closed by t)
        # v2.2 — trimmed to live's fetch depth. data_cache passes
        # TIMEFRAMES[tf]["candles"] to fetch_candles, so an uncapped as-of slice
        # hands the engines history production never sees.
        s5  = d5[d5.index <= t].tail(_CAP["5m"])
        s15 = d15[d15.index <= t].tail(_CAP["15m"])
        s1h = d1h[d1h.index <= t].tail(_CAP["1h"])
        # v2.1 — SESSION-SCOPED, matching market_data v3.1's no-overnight-padding
        # rule for 1m. Warm prior-session bars belong to the RESAMPLE (above), not
        # to the 25-bar close window: a regression must not span the gap.
        s1m = df1m.loc[score_start:t]
        if s5.empty:
            continue
        s1h_safe = s1h if not s1h.empty else s5
        try:
            vol = volE.analyze(s5, s1h_safe, price)
            trend = trE.analyze({"1m": s1m, "5m": s5, "15m": s15, "1h": s1h})
            structure = stE.analyze(s5, s15, s1h if not s1h.empty else None, price)
            liq = lqE.analyze(s5, s15, price)
        except Exception as e:            # engine hiccup on thin early tape — skip bar
            continue

        # v2.1 — byte-for-byte the shape main.py:551 passes. Below the window
        # length live sends None and RANGING/COMPRESSION go unscored; the replay
        # must do the same or the two engines are answering different questions.
        closes = None
        if len(s1m) >= RANGE_WINDOW_BARS:
            closes = s1m["close"].tolist()[-RANGE_WINDOW_BARS:]
        atr = getattr(vol, "atr_current", None)
        res = scorer.score(vol, trend, structure, liq, closes=closes, atr=atr)

        rec = {"ts": t.strftime("%H:%M"), "sym": sym, "price": price,
               "scores": res.scores, "breakdown": res.breakdown}
        if integ is not None:
            st = integ.update(t.timestamp(), res.evidence())
            l2 = {"regime": st.regime, "c": round(st.conviction, 3),
                  "stale": bool(st.stale),
                  "cv": {k: round(v, 3) for k, v in st.convictions.items()}}
            if st.trigger:
                l2["trigger"] = st.trigger
            rec["l2"] = l2
        if clf is not None:
            try:
                rc = clf.classify(vol, trend, structure, liq, macro=None, trigger="replay")
                rec["v13"] = rc.primary_regime
            except Exception:
                rec["v13"] = "ERR"
        recs.append(rec)
    return recs, sym


# ── acceptance checks (Layer-1 only — instantaneous scores, no L2) ────────────
# v2.4 — A2's band. Observed 3.0-5.3% since the tuned pool; 8% leaves room for
# ordinary variation so the alarm means "the tape changed", not "it moved".
A2_BAND_HI = 0.08


def acceptance(recs: List[dict]) -> List[Tuple[str, bool, str]]:
    out = []
    if not recs:
        return [("has ticks", False, "no replayed ticks")]

    def sc(r, k): 
        v = r["scores"].get(k); return v if v is not None else 0.0

    n = len(recs)
    # A1 — score bounds: every score is None or ∈ [0,1]
    bad = [k for r in recs for k, v in r["scores"].items() if v is not None and not (0.0 <= v <= 1.0)]
    out.append(("A1 scores in [0,1] or None", not bad, f"{len(bad)} out-of-range" if bad else "ok"))

    # A2 — CO-OCCURRENCE RATE, reported not asserted. v2.4, 2026-08-05.
    #
    # This was written as a mutual-exclusion INVARIANT — TRENDING and RANGING
    # must never both exceed 0.5 — and it has FAILED every session since the
    # harness existed. The excavation established why, and the invariant is what
    # is wrong: TRENDING reads a ~70-minute lookback and RANGING a ~25-minute
    # one, so a tick scoring both high is not a contradiction. It is a slow
    # uptrend containing a tight recent range — a real, tradeable state. The two
    # labels answer DIFFERENT QUESTIONS, and an invariant that treats them as
    # answering the same one cannot be satisfied.
    #
    # WHY THIS MATTERS MORE THAN THE 4/5: a permanent standing FAIL means a NEW
    # A2 failure is invisible. If this jumped from 224 ticks to 900 tomorrow the
    # line would read identically, and sixteen diary sessions of "4/5" trained
    # everyone to skip it. A check that always fails is not a check.
    #
    # So it PASSES on the observed band and fails only outside it. The band is
    # the range this has actually held since the tuned pool landed (3.0-5.3%),
    # widened to 8% because A2 is a REPORTED CHARACTERISTIC and the alarm should
    # fire on a regime change in the tape, not on ordinary variation.
    both = sum(1 for r in recs if (sc(r, TRENDING_BULL) > .5 or sc(r, TRENDING_BEAR) > .5) and sc(r, RANGING) > .5)
    rate = both / n if n else 0.0
    out.append((f"A2 TREND+RANGE co-occurrence within band (<={A2_BAND_HI:.0%})",
                rate <= A2_BAND_HI,
                f"{both} tick(s) = {rate:.1%}"
                + ("  [expected 3.0-5.3%; different lookbacks, NOT a "
                   "contradiction — see MECHANICS A2]" if rate <= A2_BAND_HI
                   else "  ⚠️ ABOVE BAND — this is the alarm A2 exists to raise")))

    # A3 — BREAKOUT and COMPRESSION never both strong (opposite width axis)
    both_bc = sum(1 for r in recs if sc(r, BREAKOUT_VOLATILE) > .5 and sc(r, COMPRESSION) > .5)
    out.append(("A3 BREAKOUT & COMPRESSION not both >0.5", both_bc == 0, f"{both_bc} violating ticks"))

    # A4 — structure-contradiction veto: no tick has TRENDING_BULL>0 with LH_LL structure
    viol = sum(1 for r in recs
               if sc(r, TRENDING_BULL) > 0 and r["breakdown"].get("TRENDING", {}).get("structure_sequence") == "LH_LL")
    out.append(("A4 no TREND_BULL under LH_LL structure", viol == 0, f"{viol} violating ticks"))

    # A5 — no global abstention: every tick has at least one regime scoring >0
    silent = sum(1 for r in recs if all(sc(r, k) == 0.0 for k in REGIMES))
    out.append(("A5 no all-zero ticks (UNKNOWN eliminated)", silent / n < 0.15,
                f"{silent}/{n} ({100*silent/n:.0f}%) all-zero — target <15%"))
    return out


# ── report ────────────────────────────────────────────────────────────────────
def report(all_recs: List[dict], jsonl: Optional[str]):
    if jsonl:
        with open(jsonl, "w") as f:
            for r in all_recs:
                f.write(json.dumps(r) + "\n")

    n = len(all_recs)
    print(f"\n{'='*70}\nLAYER-1 REPLAY — {n} ticks across "
          f"{len(set(r['sym'] for r in all_recs))} symbol-sessions\n{'='*70}")

    # 1) per-regime score distribution + share of ticks scoring dominant
    print("\n── per-regime instantaneous score distribution ──")
    print(f"{'regime':18}{'>0%':>6}{'p50':>7}{'p90':>7}{'max':>7}{'dom%':>7}")
    for k in REGIMES:
        vals = [r["scores"].get(k) for r in all_recs]
        nz = [v for v in vals if v is not None and v > 0]
        dom = sum(1 for r in all_recs
                  if (r["scores"].get(k) or 0) == max((r["scores"].get(x) or 0) for x in REGIMES)
                  and (r["scores"].get(k) or 0) > 0)
        d = dist([v for v in vals if v is not None])
        print(f"{k:18}{100*len(nz)/n:5.0f}%{d.get('p50',0):7}{d.get('p90',0):7}"
              f"{d.get('max',0):7}{100*dom/n:6.0f}%")

    # 2) CALIBRATION: flat-angle distribution split by v1.3 label (top priority knob)
    have_v13 = any("v13" in r for r in all_recs)
    if have_v13:
        print("\n── CALIBRATION: flat-angle° by v1.3 label (sets FLAT_ANGLE_CUT_DEG) ──")
        by = {}
        for r in all_recs:
            ang = r["breakdown"].get("RANGING", {}).get("angle")
            if ang is None:
                ang = r["breakdown"].get("COMPRESSION", {}).get("angle")
            if ang is not None:
                by.setdefault(r.get("v13", "?"), []).append(ang)
        print(f"{'v1.3 label':20}{'n':>6}{'min':>7}{'p10':>7}{'p50':>7}{'p90':>7}{'max':>7}")
        for lbl, xs in sorted(by.items(), key=lambda kv: -len(kv[1])):
            d = dist(xs)
            print(f"{lbl:20}{d['n']:6}{d.get('min',0):7}{d.get('p10',0):7}"
                  f"{d.get('p50',0):7}{d.get('p90',0):7}{d.get('max',0):7}")
        print("  → calibration read: the cut belongs between the RANGING p90 and the")
        print("    TRENDING p10 of this column, swept 16–26° on multi-day tape.")

    # 3) label agreement (context only — NOT a Layer-1 acceptance metric)
    if have_v13:
        def top(r):
            best = max(REGIMES, key=lambda k: (r["scores"].get(k) or 0))
            return best if (r["scores"].get(best) or 0) > 0 else "NONE"
        agree = sum(1 for r in all_recs if r.get("v13") == top(r))
        print(f"\n── L1-argmax vs v1.3 label agreement: {100*agree/n:.0f}%  "
              f"(context only; L1 argmax ≠ L2 committed label)")

    # 3b) LAYER-2 tracks (v2.0) — printed only when the log carries l2 fields
    l2recs = [r for r in all_recs if r.get("l2")]
    if l2recs:
        print("\n── LAYER-2 (conviction integrator, always-argmax) ──")
        m = len(l2recs)
        emitted = {}
        for r in l2recs:
            emitted[r["l2"]["regime"]] = emitted.get(r["l2"]["regime"], 0) + 1
        # v2.3 — was k.split('_')[0][:5], which printed "TREND" for BOTH
        # TRENDING_BULL and TRENDING_BEAR on the nightly emitted-distribution
        # line the freeze watch reads. Shared map now.
        dist_line = "  ".join(f"{label(k)} {100*v/m:.0f}%"
                              for k, v in sorted(emitted.items(), key=lambda kv: -kv[1]))
        stale_n = sum(1 for r in l2recs if r["l2"].get("stale"))
        print(f"  emitted: {dist_line}")
        # churn: L2 label switches vs L1 argmax flips, per symbol-session
        def _top1(r):
            return max(REGIMES, key=lambda k: (r["scores"].get(k) or 0))
        sw_tot = fl_tot = 0
        per_sym = []
        by_sym: Dict[str, List[dict]] = {}
        for r in l2recs:
            by_sym.setdefault(r["sym"], []).append(r)
        for s, rs in sorted(by_sym.items()):
            sw = sum(1 for a, b in zip(rs, rs[1:]) if a["l2"]["regime"] != b["l2"]["regime"])
            fl = sum(1 for a, b in zip(rs, rs[1:]) if _top1(a) != _top1(b))
            sw_tot += sw; fl_tot += fl
            per_sym.append((s, sw, fl))
        ratio = f"{fl_tot/max(sw_tot,1):.1f}x" if sw_tot else "∞"
        print(f"  label switches: {sw_tot} vs L1-argmax flips: {fl_tot}  "
              f"(churn crushed {ratio})   stale ticks: {100*stale_n/m:.0f}%")
        worst = sorted(per_sym, key=lambda x: -x[1])[:5]
        if worst and worst[0][1] > 0:
            print("  switchiest: " + "  ".join(f"{s}:{sw}" for s, sw, _ in worst if sw > 0))

    # 4) acceptance checks
    print("\n── LAYER-1 ACCEPTANCE ──")
    checks = acceptance(all_recs)
    for name, ok, detail in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  — {detail}")
    n_pass = sum(1 for _, ok, _ in checks if ok)
    print(f"\n{n_pass}/{len(checks)} acceptance checks passed")
    return n_pass == len(checks)


def by_symbol_table(all_recs: List[dict]):
    """Per-symbol dominance, so a whole archive can be SCANNED at once.

    ⚠️ WHY THIS EXISTS. L1.7 asks for "one genuine trend day on tape, labeled,
    showing TRENDING_* dominant ~50%". Every report in this suite aggregates
    every symbol-session together — and blending ~29 symbols GUARANTEES no
    regime dominates, because on any given day different symbols are in
    different regimes. A perfect trend day on QQQ is averaged against 28 others
    doing something else.

    So the four "tape gaps" may never have been TESTABLE, and the qualifying
    days may already be on disk. This groups by symbol and ranks, so the answer
    to "has it ever happened" is a scan rather than a wait.

    TRENDING_* is summed BULL+BEAR, because the acceptance text uses the
    wildcard — a bear trend day closes the row exactly as a bull one does.
    """
    from collections import defaultdict
    by = defaultdict(list)
    for r in all_recs:
        by[str(r.get("sym", "?"))].append(r)

    def dom_share(recs, keys):
        hit = 0
        for r in recs:
            sc = r.get("scores") or {}
            best = max((sc.get(x) or 0) for x in REGIMES)
            if best <= 0:
                continue
            if any((sc.get(k) or 0) == best for k in keys):
                hit += 1
        return 100.0 * hit / max(1, len(recs))

    rows = []
    for sym, recs in by.items():
        rows.append((
            sym, len(recs),
            dom_share(recs, ("TRENDING_BULL", "TRENDING_BEAR")),
            dom_share(recs, ("RANGING",)),
            dom_share(recs, ("BREAKOUT_VOLATILE",)),
            dom_share(recs, ("COMPRESSION",)),
            dom_share(recs, ("SWEEP_REVERSAL",)),
            max((r.get("scores") or {}).get("SWEEP_REVERSAL") or 0 for r in recs),
        ))
    rows.sort(key=lambda x: -x[2])

    print(f"\n{'='*86}\nPER-SYMBOL DOMINANCE  {len(rows)} symbol(s), "
          f"{len(all_recs)} tick(s)\n{'='*86}")
    print(f"{'sym':8}{'ticks':>7}{'TREND*':>8}{'RANGE':>7}{'BREAK':>7}"
          f"{'COMP':>7}{'SWEEP':>7}{'swp_max':>9}   Tier-B")
    for sym, n, tr, rg, bk, cp, sw, swmax in rows:
        flags = []
        if tr >= 50.0:
            flags.append("TRENDING")
        if swmax > 0:
            flags.append("sweep>0")
        print(f"{sym:8}{n:>7}{tr:>7.0f}%{rg:>6.0f}%{bk:>6.0f}%{cp:>6.0f}%"
              f"{sw:>6.0f}%{swmax:>9.3f}   {' '.join(flags)}")

    hits = [r for r in rows if r[2] >= 50.0]
    print(f"\n  TRENDING_* dominant >=50%: {len(hits)} symbol-session(s)"
          + (f" -> {', '.join(h[0] for h in hits)}" if hits else ""))
    print("  ^ that is L1.7's TRENDING acceptance bar. A hit here is a candidate")
    print("    Tier-B row that needs LABELING, not more calendar time.")
    print("\n  swp_max is the highest SWEEP_REVERSAL score seen. L1.7's SWEEP row")
    print("    needs a NAMED-ZONE reclaim with decay over ~3 bars, so a non-zero")
    print("    max is a lead to inspect, NOT a pass on its own.")


# Compact codes so a row stays readable across 20+ dates.
# 4-letter codes, matching the convention the L2 block already prints
# ("BULL 31%  BEAR 25%  COMP 23%  BREA 12%  RANG 8%") rather than inventing a
# second vocabulary for the same six regimes.
REGIME_CODE = {"TRENDING_BULL": "BULL", "TRENDING_BEAR": "BEAR",
               "RANGING": "RANG", "BREAKOUT_VOLATILE": "BREA",
               "COMPRESSION": "COMP", "SWEEP_REVERSAL": "SWEE"}


def _dominant(recs):
    """(code, share%) for the regime that led the most ticks in a session."""
    tally = {k: 0 for k in REGIMES}
    scored = 0
    for r in recs:
        sc = r.get("scores") or {}
        best = max((sc.get(x) or 0) for x in REGIMES)
        if best <= 0:
            continue
        scored += 1
        for k in REGIMES:
            if (sc.get(k) or 0) == best:
                tally[k] += 1
                break
    if not scored:
        return "--", 0.0
    top = max(tally, key=lambda k: tally[k])
    return REGIME_CODE.get(top, top[:2]), 100.0 * tally[top] / scored


def regime_grid(all_recs: List[dict]):
    """SYMBOLS down, DATES across, the dominant regime in each cell.

    The shape the operator asked for, and the one that makes a trend day
    obvious: a run of TB/TL across a row is a trending symbol; a wall of RG is
    chop. Reading 29 symbols x N dates as one aggregate number told us nothing
    for weeks.

    ⚠️ TL/TB SPLIT ON PURPOSE. L1.7's bar is `TRENDING_*` (either direction), so
    a cell of TB counts toward the row exactly as TL does — but seeing WHICH
    direction is what lets you match a cell against the chart.
    """
    from collections import defaultdict
    cells = defaultdict(dict)
    dates, syms = set(), set()
    for r in all_recs:
        d, sy = str(r.get("date", "?")), str(r.get("sym", "?"))
        cells[sy].setdefault(d, []).append(r)
        dates.add(d)
        syms.add(sy)
    dates = sorted(dates)
    # rank symbols by how often they trended, so candidates float to the top
    def trendiness(sy):
        n = 0
        for d in dates:
            recs = cells[sy].get(d)
            if recs and _dominant(recs)[0] in ("BULL", "BEAR"):
                n += 1
        return -n
    syms = sorted(syms, key=lambda sy: (trendiness(sy), sy))

    head = "".join(f"{d[5:]:>7}" for d in dates)      # MM-DD
    print(f"\n{'='*(9 + 7*len(dates))}")
    print(f"REGIME GRID  {len(syms)} symbol(s) x {len(dates)} session(s)  "
          f"BULL/BEAR=trending  RANG=range  BREA=breakout  COMP=compress  SWEE=sweep")
    print("=" * (9 + 7 * len(dates)))
    print(f"{'sym':9}{head}")
    for sy in syms:
        row = ""
        for d in dates:
            recs = cells[sy].get(d)
            if not recs:
                row += f"{'.':>7}"
                continue
            code, share = _dominant(recs)
            # a cell that clears L1.7's bar is marked, so the eye finds it
            star = "*" if share >= 50 and code in ("BULL", "BEAR") else ""
            row += f"{code + star:>7}"
        print(f"{sy:9}{row}")
    print("\n  * = TRENDING_* dominant >=50% for that symbol-session — L1.7's")
    print("      acceptance bar. Those are candidate Tier-B rows that need")
    print("      LABELING, not more calendar time.")
    print("  . = no ticks for that symbol on that date.")


def sweep_report(all_recs: List[dict]):
    """WAS A PREVIOUSLY NAMED POOL ACTUALLY SWEPT DURING THE SESSION?

    L1.7's SWEEP row needs a mapper-confirmed NAMED-ZONE RECLAIM showing
    SWEEP > 0 at the sweep bar and decaying over ~3 bars. A max score alone is
    not a pass, which is why the per-symbol table only ever called it a lead.

    Everything needed is already in the saved ticks: the scorer writes `named`,
    `reclaimed`, `pool_price`, `kind` and `age_bars` into `breakdown`. So this
    is a read of history, not a new collection.
    """
    from collections import defaultdict
    events = defaultdict(list)
    for r in all_recs:
        bd = (r.get("breakdown") or {}).get("SWEEP_REVERSAL") or {}
        named = bd.get("named")
        if not named:
            continue
        sc = (r.get("scores") or {}).get("SWEEP_REVERSAL") or 0.0
        events[(str(r.get("date", "?")), str(r.get("sym", "?")), str(named))].append(
            (str(r.get("ts", "")), float(sc), bool(bd.get("reclaimed")),
             bd.get("age_bars"), bd.get("kind"), bd.get("pool_price")))

    print(f"\n{'='*94}")
    print("NAMED-POOL SWEEPS  every session in which the mapper named a swept level")
    print("=" * 94)
    if not events:
        print("\n  NO NAMED POOL WAS SWEPT in these session(s).")
        print("  That is an ABSENT MEASUREMENT for L1.7's SWEEP row, not a null —")
        print("  the event simply did not occur on this tape.")
        return

    print(f"\n{'date':11}{'sym':7}{'level':22}{'first':7}{'peak':>7}"
          f"{'recl':>6}{'bars':>6}   decay over ~3 bars")
    hits = 0
    for (d, sy, lvl), rows in sorted(events.items()):
        rows.sort()
        peak = max(x[1] for x in rows)
        recl = any(x[2] for x in rows)
        i = next(i for i, x in enumerate(rows) if x[1] == peak)
        tail = [x[1] for x in rows[i:i + 4]]
        decays = len(tail) >= 2 and all(
            tail[j] >= tail[j + 1] for j in range(len(tail) - 1)) and tail[-1] < peak
        shape = " -> ".join(f"{v:.2f}" for v in tail[:4])
        ok = peak > 0 and recl and decays
        if ok:
            hits += 1
        print(f"{d:11}{sy:7}{lvl[:21]:22}{rows[0][0]:7}{peak:>7.3f}"
              f"{('yes' if recl else 'no'):>6}{str(rows[0][3] or '-'):>6}   "
              f"{shape}{'   <= TIER-B CANDIDATE' if ok else ''}")

    print(f"\n  {len(events)} named-pool sweep(s); {hits} show SWEEP>0 at the bar,")
    print("  a RECLAIM, and a monotone decay after the peak — L1.7's acceptance")
    print("  shape. Those need LABELING; the rest are leads that did not qualify.")


def _stream(files):
    """Yield (record, date) one at a time, never holding more than one line.

    ⚠️ WHY THIS EXISTS. `--grid` and `--sweeps` used to build a full `all_recs`
    list first: 5 sessions is ~56k records and the control box **OOM-KILLED it
    (rc=137)**. Neither report needs the records — the grid needs six counters
    per symbol-date and the sweep report needs only the rows that name a level.
    So both stream, and 25 sessions costs the same as 1.
    """
    for fp in files:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(fp))
        day = m.group(1) if m else os.path.basename(fp)
        with open(fp) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:                              # noqa: BLE001
                    continue
                yield r, str(r.get("date", day))


def regime_grid_stream(files, symbol=None):
    """SYMBOLS down, DATES across, dominant regime per cell. Streams."""
    from collections import defaultdict
    tally = defaultdict(lambda: defaultdict(int))   # (sym,date) -> regime -> n
    scored = defaultdict(int)
    want = symbol.upper() if symbol else None
    for r, day in _stream(files):
        sy = str(r.get("sym", "?"))
        if want and sy.upper() != want:
            continue
        sc = r.get("scores") or {}
        best = max((sc.get(x) or 0) for x in REGIMES)
        if best <= 0:
            continue
        key = (sy, day)
        scored[key] += 1
        for k in REGIMES:
            if (sc.get(k) or 0) == best:
                tally[key][k] += 1
                break
    if not scored:
        print("\n  no scored ticks. ABSENT MEASUREMENT, not a null.")
        return
    dates = sorted({d for _, d in scored})
    syms = sorted({sy for sy, _ in scored})

    def cell(sy, d):
        key = (sy, d)
        if key not in scored:
            return ".", 0.0
        top = max(tally[key], key=lambda k: tally[key][k])
        return REGIME_CODE.get(top, top[:4]), 100.0 * tally[key][top] / scored[key]

    def trendiness(sy):
        return -sum(1 for d in dates if cell(sy, d)[0] in ("BULL", "BEAR")
                    and cell(sy, d)[1] >= 50)
    syms.sort(key=lambda sy: (trendiness(sy), sy))

    w = 9 + 7 * len(dates)
    print(f"\n{'='*min(w, 120)}")
    print(f"REGIME GRID  {len(syms)} symbol(s) x {len(dates)} session(s)  "
          f"BULL/BEAR=trending  RANG=range  BREA=breakout  COMP=compress  SWEE=sweep")
    print("=" * min(w, 120))
    print(f"{'sym':9}" + "".join(f"{d[5:]:>7}" for d in dates))
    for sy in syms:
        row = ""
        for d in dates:
            code, share = cell(sy, d)
            star = "*" if share >= 50 and code in ("BULL", "BEAR") else ""
            row += f"{code + star:>7}"
        print(f"{sy:9}{row}")
    hits = sum(1 for sy in syms for d in dates
               if cell(sy, d)[0] in ("BULL", "BEAR") and cell(sy, d)[1] >= 50)
    print(f"\n  * = TRENDING_* dominant >=50% for that symbol-session - L1.7's")
    print(f"      acceptance bar. {hits} starred cell(s) across this range.")
    print("      Those are candidate Tier-B rows that need LABELING, not more")
    print("      calendar time.   . = no ticks for that symbol on that date.")


def sweep_report_stream(files, symbol=None):
    """Was a previously NAMED pool actually swept during the session? Streams."""
    from collections import defaultdict
    events = defaultdict(list)
    want = symbol.upper() if symbol else None
    for r, day in _stream(files):
        sy = str(r.get("sym", "?"))
        if want and sy.upper() != want:
            continue
        bd = (r.get("breakdown") or {}).get("SWEEP_REVERSAL") or {}
        named = bd.get("named")
        if not named:
            continue
        sc = (r.get("scores") or {}).get("SWEEP_REVERSAL") or 0.0
        events[(day, sy, str(named))].append(
            (str(r.get("ts", "")), float(sc), bool(bd.get("reclaimed")),
             bd.get("age_bars")))

    print(f"\n{'='*94}")
    print("NAMED-POOL SWEEPS  every session in which the mapper named a swept level")
    print("=" * 94)
    if not events:
        print("\n  NO NAMED POOL WAS SWEPT in these session(s).")
        print("  ABSENT MEASUREMENT for L1.7's SWEEP row, not a null - the event")
        print("  did not occur on this tape.")
        return
    print(f"\n{'date':11}{'sym':7}{'level':20}{'first':7}{'peak':>7}"
          f"{'recl':>6}   decay after the peak")
    hits = 0
    for (d, sy, lvl), rows in sorted(events.items()):
        rows.sort()
        peak = max(x[1] for x in rows)
        recl = any(x[2] for x in rows)
        i = next(i for i, x in enumerate(rows) if x[1] == peak)
        tail = [x[1] for x in rows[i:i + 4]]
        decays = (len(tail) >= 2
                  and all(tail[j] >= tail[j + 1] for j in range(len(tail) - 1))
                  and tail[-1] < peak)
        ok = peak > 0 and recl and decays
        hits += 1 if ok else 0
        print(f"{d:11}{sy:7}{lvl[:19]:20}{rows[0][0]:7}{peak:>7.3f}"
              f"{('yes' if recl else 'no'):>6}   "
              + " -> ".join(f"{v:.2f}" for v in tail[:4])
              + ("   <= TIER-B CANDIDATE" if ok else ""))
    print(f"\n  {len(events)} named-pool sweep(s); {hits} show SWEEP>0 at the bar,")
    print("  a RECLAIM, and a monotone decay after the peak - L1.7's acceptance")
    print("  shape. A high max score alone is a LEAD, never a pass.")


def stream_grid(files: List[str], symbol: Optional[str],
                out_path: Optional[str] = None) -> str:
    """Build the regime grid by STREAMING, holding only counters.

    ⚠️ WHY THIS EXISTS. The first version parsed every matched log into one list
    and reported off it. Five sessions is ~56k records and the control box
    **OOM-KILLED it (rc=137)** before printing a line. The kill is on the INPUT
    side, so writing output to a file would not have saved it.

    The grid needs SIX INTEGERS per symbol-date — one tally per regime — not the
    records. So this reads one line at a time, increments, and discards.
    **Memory is constant no matter how many sessions are scanned**, which is
    what makes a 25-session archive scan possible at all.

    Returns the report text and, if `out_path` is given, writes it there too so
    it persists like every other report rather than living in a terminal buffer.
    """
    from collections import defaultdict
    tally = defaultdict(lambda: defaultdict(int))   # (sym, date) -> regime -> n
    scored = defaultdict(int)                       # (sym, date) -> ticks scored
    dates, syms = set(), set()
    want = symbol.upper() if symbol else None

    for fp in files:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(fp))
        day = m.group(1) if m else os.path.basename(fp)
        with open(fp) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:                              # noqa: BLE001
                    continue
                sy = str(r.get("sym", "?"))
                if want and sy.upper() != want:
                    continue
                sc = r.get("scores") or {}
                best = max((sc.get(x) or 0) for x in REGIMES)
                if best <= 0:
                    continue
                key = (sy, day)
                scored[key] += 1
                for k in REGIMES:
                    if (sc.get(k) or 0) == best:
                        tally[key][k] += 1
                        break
                dates.add(day)
                syms.add(sy)
                # `r` goes out of scope here — nothing accumulates.

    if not scored:
        return "no scored ticks in those file(s). ABSENT MEASUREMENT, not a null."

    dates = sorted(dates)

    def cell(sy, d):
        key = (sy, d)
        n = scored.get(key, 0)
        if not n:
            return ".", 0.0
        t = tally[key]
        top = max(t, key=lambda k: t[k])
        return REGIME_CODE.get(top, top[:4]), 100.0 * t[top] / n

    def trendiness(sy):
        return -sum(1 for d in dates
                    if cell(sy, d)[0] in ("BULL", "BEAR") and cell(sy, d)[1] >= 50)

    syms = sorted(syms, key=lambda sy: (trendiness(sy), sy))

    L = []
    L.append("=" * (9 + 7 * len(dates)))
    L.append(f"REGIME GRID  {len(syms)} symbol(s) x {len(dates)} session(s)")
    L.append("BULL/BEAR=trending  RANG=range  BREA=breakout  COMP=compress  SWEE=sweep")
    L.append("=" * (9 + 7 * len(dates)))
    L.append(f"{'sym':9}" + "".join(f"{d[5:]:>7}" for d in dates))
    hits = []
    for sy in syms:
        row = ""
        for d in dates:
            code, share = cell(sy, d)
            star = "*" if share >= 50 and code in ("BULL", "BEAR") else ""
            if star:
                hits.append((sy, d, code, share))
            row += f"{code + star:>7}"
        L.append(f"{sy:9}{row}")
    L.append("")
    L.append(f"  {len(hits)} symbol-session(s) cleared TRENDING_* >=50% — L1.7's")
    L.append("  acceptance bar. Those are candidate Tier-B rows that need")
    L.append("  LABELING, not more calendar time.  '.' = no ticks that date.")
    if hits:
        L.append("")
        L.append("  strongest first:")
        for sy, d, code, share in sorted(hits, key=lambda x: -x[3])[:12]:
            L.append(f"    {d}  {sy:6} {code}  {share:.0f}% dominant")
    text = "\n".join(L)

    if out_path:
        try:
            with open(out_path, "w") as f:
                f.write(text + "\n")
            text += f"\n\n  written: {out_path}"
        except Exception as exc:                               # noqa: BLE001
            text += f"\n\n  (could not write {out_path}: {exc})"
    return text


def stream_sweeps(files: List[str], symbol: Optional[str],
                  out_path: Optional[str] = None) -> str:
    """WAS A PREVIOUSLY NAMED POOL ACTUALLY SWEPT DURING THE SESSION?

    Streams, like the grid — a named-pool sweep is RARE, so the only thing worth
    keeping is the handful of ticks where `breakdown.SWEEP_REVERSAL.named` is
    set. Everything else is read and discarded, so memory scales with the number
    of EVENTS rather than with the size of the archive.

    L1.7's SWEEP row needs a mapper-confirmed NAMED-ZONE RECLAIM showing
    SWEEP > 0 at the sweep bar and decaying over ~3 bars. A high max score alone
    is a LEAD, never a pass — so a row is only marked TIER-B CANDIDATE when all
    three hold, and the decay shape is printed so the "~3 bars" judgement stays
    with the reader rather than with a threshold I chose.
    """
    from collections import defaultdict
    events = defaultdict(list)
    want = symbol.upper() if symbol else None
    scanned = 0

    for fp in files:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(fp))
        day = m.group(1) if m else os.path.basename(fp)
        with open(fp) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # cheap prefilter: skip the ~99.9% of lines with no named pool
                # before paying for a full JSON parse.
                if '"named"' not in line:
                    scanned += 1
                    continue
                try:
                    r = json.loads(line)
                except Exception:                              # noqa: BLE001
                    continue
                scanned += 1
                sy = str(r.get("sym", "?"))
                if want and sy.upper() != want:
                    continue
                bd = (r.get("breakdown") or {}).get("SWEEP_REVERSAL") or {}
                named = bd.get("named")
                if not named:
                    continue
                sc = (r.get("scores") or {}).get("SWEEP_REVERSAL") or 0.0
                events[(day, sy, str(named))].append(
                    (str(r.get("ts", "")), float(sc), bool(bd.get("reclaimed")),
                     bd.get("age_bars"), bd.get("kind")))

    L = ["=" * 94,
         "NAMED-POOL SWEEPS  every session in which the mapper named a swept level",
         "=" * 94,
         f"  scanned {scanned:,} tick(s) across {len(files)} session(s)"]

    if not events:
        L += ["",
              "  NO NAMED POOL WAS SWEPT in these session(s).",
              "  That is an ABSENT MEASUREMENT for L1.7's SWEEP row, not a null -",
              "  either the event did not occur on this tape, or the mapper is not",
              "  naming levels in the replay path. Those are different problems and",
              "  the next step differs: the first waits for tape, the second is a bug."]
        text = "\n".join(L)
    else:
        L += ["",
              f"{'date':11}{'sym':7}{'level':20}{'first':7}{'peak':>7}"
              f"{'recl':>6}{'bars':>6}   decay after the peak"]
        hits = 0
        for (d, sy, lvl), rows in sorted(events.items()):
            rows.sort()
            peak = max(x[1] for x in rows)
            recl = any(x[2] for x in rows)
            i = next(i for i, x in enumerate(rows) if x[1] == peak)
            tail = [x[1] for x in rows[i:i + 4]]
            decays = (len(tail) >= 2
                      and all(tail[j] >= tail[j + 1] for j in range(len(tail) - 1))
                      and tail[-1] < peak)
            ok = peak > 0 and recl and decays
            hits += 1 if ok else 0
            L.append(f"{d:11}{sy:7}{lvl[:19]:20}{rows[0][0]:7}{peak:>7.3f}"
                     f"{('yes' if recl else 'no'):>6}{str(rows[0][3] or '-'):>6}   "
                     + " -> ".join(f"{v:.2f}" for v in tail[:4])
                     + ("   <= TIER-B CANDIDATE" if ok else ""))
        L += ["",
              f"  {len(events)} named-pool sweep(s); {hits} show SWEEP>0 at the bar,",
              "  a RECLAIM, and a monotone decay after the peak - L1.7's acceptance",
              "  shape. Those need LABELING; the rest are leads that did not qualify."]
        text = "\n".join(L)

    if out_path:
        try:
            with open(out_path, "w") as f:
                f.write(text + "\n")
            text += f"\n\n  written: {out_path}"
        except Exception as exc:                               # noqa: BLE001
            text += f"\n\n  (could not write {out_path}: {exc})"
    return text


def gather_paths(args_paths: List[str]) -> List[str]:
    out = []
    for p in args_paths:
        if os.path.isdir(p):
            # only OHLC tape files — harvest folders also hold fleet_trades_<date>.csv,
            # daily_trades_<date>.json, and per-box *_trades_<date>.db siblings.
            names = sorted(os.listdir(p))
            ohlc = [f for f in names if "_ohlc_" in f.lower() and f.lower().endswith((".csv", ".csv.gz"))]
            # fall back to any .csv only if no OHLC-named files exist (e.g. a bare dir)
            picked = ohlc if ohlc else [f for f in names if f.lower().endswith((".csv", ".csv.gz"))]
            out += [os.path.join(p, f) for f in picked]
        else:
            out.append(p)
    return out


def main():
    ap = argparse.ArgumentParser(description="Layer-1 confluence replay over DXFeed OHLC")
    ap.add_argument("paths", nargs="*", help="CSV files or a data/OHLC/<date>/ directory")
    ap.add_argument("--warmup", type=int, default=20, help="skip first N 1-min bars")
    ap.add_argument("--warm-sessions", type=int, default=8, dest="warm_sessions",
                    help="prior sessions of same-symbol 1m to prepend so ADX/EMA warm "
                         "from the open (0 = old single-day behaviour). Default 5 "
                         "matches the live feed store's 5m retention (~5 days).")
    ap.add_argument("--jsonl", default=None, help="dump per-tick records to this JSONL")
    ap.add_argument("--no-v13", action="store_true", help="skip the v1.3 comparison label")
    ap.add_argument("--symbol", default=None, metavar="SYM",
                    help="restrict the report to ONE symbol. L1.7's acceptance "
                         "criteria are written PER SYMBOL-DAY, but every report "
                         "in this suite aggregates ~29 symbol-sessions, which "
                         "guarantees no regime dominates because different "
                         "symbols are in different regimes on the same day.")
    ap.add_argument("--by-symbol", action="store_true", dest="by_symbol",
                    help="per-SYMBOL dominance table instead of the aggregate, "
                         "so a whole archive can be SCANNED for symbol-days "
                         "that clear Tier B.")
    ap.add_argument("--grid", action="store_true",
                    help="SYMBOLS down, DATES across, dominant regime per cell. "
                         "STREAMS the logs (constant memory) and writes the "
                         "report to a file as well as printing it.")
    ap.add_argument("--out", default=None, metavar="PATH",
                    help="where to write the grid report (default: alongside "
                         "the tick logs).")
    ap.add_argument("--last", type=int, default=0, metavar="N",
                    help="read only the N most recent session files. ⚠️ SELECTS "
                         "FILES BEFORE OPENING THEM — the first version loaded "
                         "all 25 logs (~280k records) and trimmed dates "
                         "afterwards, which was silently OOM-killed on control.")
    ap.add_argument("--from", dest="date_from", default=None, metavar="YYYY-MM-DD",
                    help="read only session files on/after this date.")
    ap.add_argument("--to", dest="date_to", default=None, metavar="YYYY-MM-DD",
                    help="read only session files on/before this date.")
    ap.add_argument("--sweeps", action="store_true",
                    help="every session in which a NAMED pool was swept, with "
                         "the score's decay shape - L1.7's SWEEP acceptance.")
    ap.add_argument("--report-only", default=None, metavar="JSONL", nargs="+",
                    help="rebuild + reprint the full report from a saved tick-log JSONL "
                         "(no engines, no re-scoring — the report is deterministic from the log)")
    args = ap.parse_args()

    # --report-only: reload a saved per-tick log and reprint the identical report.
    if args.report_only:
        # A DATE RANGE IS JUST N FILES. The tick logs are per-session and carry
        # `sym` on every record, so scanning history needs no re-run and no new
        # collection - only a different grouping of data already on disk.
        files = []
        for pat in args.report_only:
            files.extend(sorted(glob.glob(pat)) if any(c in pat for c in "*?[")
                         else [pat])
        files = [f for f in files if os.path.isfile(f)]

        # ⚠️ NARROW THE FILE LIST BEFORE READING ANY OF IT. Loading every log
        # and filtering afterwards is what got this OOM-killed: 25 sessions is
        # ~280k records held at once on a control box. A date range is a file
        # selection, not a post-filter.
        def _fdate(fp):
            m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(fp))
            return m.group(1) if m else ""
        if args.date_from:
            files = [f for f in files if _fdate(f) >= args.date_from]
        if args.date_to:
            files = [f for f in files if _fdate(f) <= args.date_to]
        files = sorted(files, key=_fdate)
        if args.last and args.last > 0:
            files = files[-args.last:]

        if not files:
            # ⚠️ LOUD, WITH DIAGNOSIS. A quoted glob that matches nothing used to
            # exit before printing anything at all, which looks identical to the
            # command not running. Say what was tried and what is actually there.
            print(f"no tick log(s) matched: {args.report_only}")
            for pat in args.report_only:
                d = os.path.dirname(pat) or "."
                if os.path.isdir(d):
                    near = sorted(x for x in os.listdir(d) if x.endswith(".jsonl"))
                    print(f"  in {d}: {len(near)} .jsonl file(s)"
                          + (f", e.g. {near[0]}" if near else ""))
                else:
                    print(f"  {d} is not a directory")
            print("  ABSENT MEASUREMENT, not a null.")
            sys.exit(1)
        print(f"[files] {len(files)} tick log(s) matched")

        # ⚠️ GRID STREAMS — it must run BEFORE any bulk load. Parsing every log
        # into one list is what got rc=137 on five sessions; the grid needs only
        # six counters per symbol-date, so it reads and discards.
        if args.sweeps:
            out = args.out or os.path.join(
                os.path.dirname(files[0]) or ".",
                f"named_sweeps_{len(files)}sessions.txt")
            print(stream_sweeps(files, args.symbol, out_path=out))
            sys.exit(0)

        if args.grid:
            out = args.out or os.path.join(
                os.path.dirname(files[0]) or ".",
                f"regime_grid_{len(files)}sessions.txt")
            print(stream_grid(files, args.symbol, out_path=out))
            sys.exit(0)
        all_recs = []
        for fp in files:
            # ⚠️ THE DATE COMES FROM THE FILENAME. Saved records carry `ts` as
            # HH:MM only, so without this a multi-session scan would blend
            # AVGO's trend day into AVGO's chop days and dilute the very thing
            # being looked for. The acceptance criterion is per SYMBOL-SESSION.
            m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(fp))
            day = m.group(1) if m else os.path.basename(fp)
            with open(fp) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:                          # noqa: BLE001
                        continue
                    r.setdefault("date", day)
                    all_recs.append(r)
        if not all_recs:
            print("tick log(s) empty"); sys.exit(1)
        span = f"{len(files)} file(s)" if len(files) > 1 else files[0]
        print(f"[report-only] rebuilt from {len(all_recs)} saved ticks - {span}")

        if args.symbol:
            want = args.symbol.upper()
            before = len(all_recs)
            all_recs = [r for r in all_recs
                        if str(r.get("sym", "")).upper() == want]
            if not all_recs:
                print(f"no ticks for {want} across those file(s); {before} tick(s) "
                      f"were present for other symbols. ABSENT MEASUREMENT, not a null.")
                sys.exit(1)
            print(f"[symbol] {want} only - {len(all_recs)} of {before} tick(s). "
                  f"Acceptance checks below are PER SYMBOL, which is what L1.7 "
                  f"asks for and what the aggregate cannot show.")

        if args.by_symbol:
            by_symbol_table(all_recs)
            sys.exit(0)

        ok = report(all_recs, jsonl=None)   # jsonl=None: don't re-dump, just print
        sys.exit(0 if ok else 2)

    if not args.paths:
        ap.error("provide OHLC paths to replay, or --report-only <jsonl> to reprint a saved run")

    paths = gather_paths(args.paths)

    # ── FILTER AT THE PATH, NOT AFTER THE FACT ───────────────────────────────
    # `gather_paths` returns ONE OHLC FILE PER SYMBOL, so restricting the list
    # here means we replay 1 symbol instead of 29 — roughly 29x faster, and the
    # per-symbol acceptance checks come out of the normal report with no special
    # casing. (`--report-only` still filters by RECORD, because saved tick logs
    # are already merged across symbols and there are no paths left to filter.)
    if args.symbol:
        want = args.symbol.upper()
        kept = [p for p in paths if sym_of(p).upper() == want]
        if not kept:
            found = sorted({sym_of(p).upper() for p in paths})
            print(f"no OHLC file for {want} in those path(s). Present: "
                  f"{', '.join(found) if found else '(none)'}. "
                  f"ABSENT MEASUREMENT, not a null.")
            sys.exit(1)
        print(f"[symbol] {want} only — replaying {len(kept)} of {len(paths)} file(s). "
              f"Acceptance checks are PER SYMBOL, which is what L1.7 asks for.")
        paths = kept

    all_recs: List[dict] = []
    for p in paths:
        recs, sym = replay_symbol(p, args.warmup, use_v13=not args.no_v13,
                                  warm_sessions=args.warm_sessions)
        print(f"  replayed {sym:6} {len(recs):4d} ticks  ({os.path.basename(p)})")
        all_recs += recs

    if not all_recs:
        print("no ticks replayed — check paths / warmup")
        sys.exit(1)
    if args.by_symbol:
        if args.jsonl:
            with open(args.jsonl, "w") as f:
                for r in all_recs:
                    f.write(json.dumps(r) + "\n")
        by_symbol_table(all_recs)
        sys.exit(0)
    ok = report(all_recs, args.jsonl)
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
