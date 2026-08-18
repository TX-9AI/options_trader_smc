# VALIDATION — replay, calibration, and the backtest harness

How Layer-1 is validated and calibrated against tape, and how to run the offline backtest harness.

**Consolidated 2026-07-28.** Nothing was rewritten or summarised — each
former file is preserved verbatim as a section below, so historical
decisions stay on the record and fixes don't get quietly reverted.

## Contents

- **REPLAY_VALIDATION.md — Layer 1 validation & calibration plan**  <sub>(was `docs/REPLAY_VALIDATION.md`)</sub>
- **Backtest Harness — v1.0**  <sub>(was `docs/README_offline_backtest_harness.md`)</sub>
- **Offline measurement tools — what each one answers**  <sub>(added 2026-08-04)</sub>

---


<!-- ================= was: docs/REPLAY_VALIDATION.md ================= -->

##### Offline measurement tools — what each one answers

Added 2026-08-04. These are control-side, read-only, and drive nothing. They are
listed here rather than in MECHANICS because MECHANICS describes what the bot
DOES; these describe how a claim about it gets TESTED.

| tool | the question it answers | reads |
|---|---|---|
| `tests/tcs_floor_durability.py` | **Does the impulse floor hold, and where must the short strike sit?** The trend credit spread's entire premise — that committed order flow will not fully retrace — measured before the firing engine exists (TC.4b's stated prerequisite). | readiness journal + banked OHLC |
| `tests/gap_outcome_join.py` | Does outcome depend on gap class? `--pool gapflat` triples n and prints its own CONT-vs-REV legitimacy verdict. | `gap_pct.json` + `fleet_trades_<date>.json` |
| `tests/a2_partition.py` | Is A2's 10:00 signature horizon co-truth, opening drive, or a gap artifact? | replay corpus |
| `tests/post_exit_continuation.py` | After an exit fires, does price keep going the trade's way? | trades + tape |
| `tests/swallow_audit.py` | Which exception handlers fail silently, and what was added since a snapshot? | source, statically |

**`tcs_floor_durability.py` — read this before reading its output.**

*What it asks.* For every impulse the readiness track recorded a `floor_px` for,
did a **1-minute CLOSE** go back through that floor before the bell?

*Close, not wick — deliberately.* A short strike is threatened by ACCEPTANCE
beyond a level, not by a touch. The wick statistic (maximum penetration) is
reported separately; merge the two and durability silently becomes a stop-out
statistic answering a different question.

*One impulse, counted once.* The track scores every tick, so a single impulse
appears on hundreds of consecutive journal rows. Rows are deduped on
`(date, symbol, floor_px, direction)`.

*The population filter is the thing to get right.* The impulse lookback rolls on
EVERY tick, so most floors the track computes belong to moments when it was
DORMANT and the strategy would never have sold anything. `--machine ARMED` is the
default for that reason. `--machine ANY` exists only so the two populations can be
COMPARED — a result read from it is a result about arithmetic, not about a trade.

*Intraday vs TERMINAL — v1.2, and it is the distinction that decides TC.4.*
"Did a 1m close ever go back through the floor?" is an INTRADAY VIOLATION rate. A
defined-risk 0DTE spread does not lose when a level is touched; it loses on where
price sits AT THE BELL. Both rates are reported, never merged, alongside the
RECOVERY rate (violated intraday, fine at the close) — and the gap between them is
the answer to *is the premise wrong, or is the strike too close?* The STRIKE CURVE
prices that directly: terminal failure rate as a function of distance beyond the
floor. The offset where it crosses a tolerance stated in advance IS the
short-strike rule. It bounds RISK only — further OTM collects less credit, and
this tool prices no credit at all.

*Its three original outputs.* Durability by SD bucket **is** the fit for
`TR_TCS_IMPULSE_SD_LO/HI` — the bound belongs where durability starts clearing,
not where a prior guessed, and a flat curve says impulse magnitude is not what
protects the floor. Penetration p90 on failures is a strike distance priced from
the state's own behaviour. Time-to-failure separates *a 0DTE that ran out of
clock* from *a thesis that was wrong*; a p50 in single-digit minutes is the
second.

*The matched control — v1.3, and no rate here means anything without it.* In a
trending tape a recent intraday extreme survives terminally a great deal of the
time simply because trends trend. `--control matched` draws a pseudo-impulse at a
random earlier minute on the SAME symbol-day, same direction and construction,
and runs the identical measurement — so the printed difference is *impulse minus
arbitrary extreme*, with a two-proportion band. The seed is fixed and moves only
the control draw; a control that wandered between runs could not be argued with.
**The ranging-vs-trending control was attempted first and is impossible:**
`_trend_credit_spread` sets `direction = ""` on any non-TRENDING label, so no
ranging floor is ever recorded. Written down here so it is not planned again.

*What it cannot say.* No spread is priced, no credit assumed, no fill modelled. A
held floor is a NECESSARY condition for the trade, never a profitable one.

---

##### REPLAY_VALIDATION.md — Layer 1 validation & calibration plan

**v1.1 — 2026-07-13.** Companion to `tests/replay_confluence.py` v1.0 and
`analysis/regime_confluence.py` v1.0 / `REGIME_TRUTHS.md` v0.2. Closes ROADMAP
Phase 1 (finish the regime truths) by making the scorer replayable and stating what
Layer-1 acceptance means — **without invoking any Layer-2 behavior** (no conviction,
no commit, no hysteresis; instantaneous scores only).

---

##### 1. Method — why replay, and why over the DXFeed CSVs

The scorer is validated and calibrated by **replay over the candle logger's DXFeed
1-min OHLC** (`data/OHLC/<date>/<SYMBOL>.csv`), **not** the shadow observer's
`data/shadow/<date>/<SYMBOL>.jsonl`.

**Corrected premise (v1.1).** Earlier revisions justified this by claiming the
observer "scores off yfinance" and was therefore a divergent feed. **That is false,
and was false when written.** `shadow/observer.py` acquires data through exactly one
call — `get_cache(symbol)` → `data/data_cache.py` → `data/market_data.py` — and since
the v3.0 purge `market_data` reads the on-box shared SQLite store written by
`data/candle_feed.py` (TastyTrade/DXFeed), read-only, heartbeat-guarded. There is no
yfinance anywhere in the repo and none in `requirements.txt`. **The observer scores off
the same DXFeed tape the CSVs are cut from.** The old rationale would send an agent off
to "re-purge" code that is already clean.

**The real reason to prefer the CSVs is sampling, not source.** Same tape, different
sampling of it:

| | shadow jsonl | DXFeed CSVs |
|---|---|---|
| cadence | every `POLL_INTERVAL_SECONDS`, wall-clock | fixed 1-min bars |
| freshness | staleness-gated cache; a frame may be re-read across ticks, or served as `None` past the hard-stale ceiling | every bar present exactly once |
| reproducibility | depends on tick timing, restarts, staleness state | deterministic — same input, same output, forever |

Calibration needs a **deterministic, evenly-sampled substrate**, which is the CSVs. The
observer's log is an *operational* record of what the live scorer actually saw, which is
a different and also useful thing — but it is not a calibration surface. The CSVs also
already accumulate fleet-wide on every box, so no fleet observer deployment is required.

**As-of replay.** For each 1-min bar *t* of a session the harness slices every
timeframe frame to bars ≤ *t*, runs the **real** engines
(`volatility/trend/structure/liquidity_engine.analyze()` — the same code the live
bot runs, not a reimplementation), and scores the resulting state objects with the
real `RegimeConfluenceScorer`. It optionally also runs the v1.3 boolean classifier
on the same states for a side-by-side label. This reconstructs, bar by bar, exactly
what the live scorer would have seen — so the factor distributions it produces are
the genuine calibration surface, not a proxy.

**Run:**
```
python -m tests.replay_confluence data/OHLC/2026-07-13            # a whole session dir
python -m tests.replay_confluence data/OHLC/2026-07-13/SPX.csv    # one symbol
        [--warmup 20] [--jsonl out.jsonl] [--no-v13]
```
Isolation: reads OHLC + runs engines only; no orders, no `trades.db`, writes only the
report (+ optional `--jsonl`). Safe to run anytime, including mid-RTH (read-only).

---

##### 2. Acceptance — two tiers

##### Tier A — structural invariants (label-free; must hold on ANY replay)

These validate the scorer's *logic* and need no labeled tape. Implemented as the
harness's acceptance block; **all five pass on the 07-09/07-10 sample.**

| # | invariant | rationale | status |
|---|---|---|---|
| A1 | every score ∈ [0,1] or None | grammar bound; None only when inputs unreadable | ✅ |
| A2 | TRENDING & RANGING never both > 0.5 | the flat-angle master veto is mutually exclusive | ✅ |
| A3 | BREAKOUT & COMPRESSION never both > 0.5 | opposite ends of the width axis | ✅ |
| A4 | no TRENDING_BULL > 0 under LH_LL structure | the structure-contradiction hard veto | ✅ |
| A5 | all-zero ("would-be UNKNOWN") ticks < 15% | Task 2 — indecision is low score, not abstention | ✅ (13%) |

A1–A4 are permanent regression guards — any future change that breaks one is a
definitional error. A5 is a calibration-sensitive target (see §4): the all-zero
residual should *fall* as the flat cut is fit, because most all-zero ticks are ranges
over-vetoed by too-low an angle cut.

##### Tier B — labeled-behavior criteria (need known session types; the RTH targets)

These validate that each regime *fires on its own tape*. Each needs a session (or
window) whose type is known from independent evidence — the eye, the v1.3 log, the
liquidity mapper's own sweep verdict, or a documented post-mortem episode. Thresholds
are PRIOR. **This table is the "make the most of the next RTH" checklist** — each row
names the tape to capture and the bar it must clear.

| regime | acceptance criterion (Layer-1, instantaneous) | tape needed | PRIOR bar | have it? |
|---|---|---|---|---|
| **RANGING** | on a shark-fin/chop session, RANGING is the dominant nonzero score on ≥ X% of mid-session ticks | 07-09 autopsy day | X ≈ 60% | ✅ **64% dom** |
| **COMPRESSION** | on a coil-into-pin session, COMPRESSION rises relative to RANGING through the final hour (energy-bleed arc) | a QQQ/SPX pin day | Δdom > 0 AM→PM | partial (need a clean pin) |
| **BREAKOUT** | on the 07-09 clean-breakout names, BREAKOUT stays > 0 through the BB re-entry flicker at ADX 43–50 (momentum carry) | AMD/MU/PLTR/AMZN 07-09 | > 0 across flicker | partial (have MU/NVDA) |
| **TRENDING** | on a genuine trend day, TRENDING_* dominant ≥ X% and RANGING vetoed through it | **a real trend day (missing)** | X ≈ 50% | ❌ **tape gap** |
| **SWEEP** | at a mapper-confirmed named-zone reclaim, SWEEP > 0 at the sweep bar and decays over ~3 bars absent follow-through | a session with a confirmed sweep | > 0 at bar, decays | ❌ none in sample |

**The tape gaps are the RTH shopping list.** TRENDING cannot be validated on any tape
we hold — every session so far is chop/flat (the same confound that shelved GRIND).
Monday, capture and label: (a) any symbol that trends cleanly, (b) any that coils into
a pin, (c) any mapper-flagged sweep. Those three fill the table.

---

##### 3. First-light findings (07-09 fleet slice + 07-10 SPX, 2595 ticks)

Real numbers from the real engines — treat as directional, not settled (all chop/flat
tape; see gaps above):

- **RANGING claims the chop, as designed.** 76–78% of ticks score RANGING > 0, 62–64%
  dominant. This is the system doing what the 07-09 autopsy said it *should* — claiming
  energetic mean-reverting chop as RANGING instead of dwelling in UNKNOWN. The single
  biggest v1.x failure mode is closed on this tape.
- **UNKNOWN reclamation is real.** The v1.3 classifier labeled 566 of these ticks
  UNKNOWN; the scorer assigns them to RANGING/COMPRESSION. The 62% L1-vs-v1.3 label
  agreement is *mostly this designed disagreement*, not error.
- **TRENDING scored 0% everywhere — and so did v1.3** (its label set here is only
  RANGING/COMPRESSION/UNKNOWN). Consistent, not a bug: there is no trend tape in the
  sample. Cannot validate the TRENDING factors until we have a trend day.
- **SWEEP scored 0%** — no mapper-confirmed named-zone reclaim in the sample. Cannot
  validate SWEEP yet.

---

##### 4. Calibration — the factor-distribution report

The harness prints each regime's score distribution and, the calibration payload,
**the flat-angle distribution split by v1.3 label**. First-light (single/few days, so
angles run hot exactly as the persistence design predicted):

| v1.3 label | n | p10 | p50 | p90 | max |
|---|---|---|---|---|---|
| RANGING | 1150 | 2.4° | 10.2° | **22.1°** | 37.2° |
| COMPRESSION | 851 | 1.8° | 9.6° | 19.1° | 38.8° |
| UNKNOWN | 566 | 2.7° | 13.5° | 29.0° | 38.6° |

**The #1 calibration finding:** `FLAT_ANGLE_CUT_DEG = 20°` looks **too low**. Ticks
that v1.3 (and the eye) call RANGING have a p90 of **22°** — so > 10% of genuine ranges
sit *above* our veto and get zeroed. This is precisely the "one day clusters everyone
at 24–32°, needs multi-day base rates" warning, now quantified. Do **not** just raise
the cut off one sample — the correct move is the documented sweep of 16–26° against
multi-day labeled windows; but the direction is clear and it explains A5's 13%
all-zero residual (ranges over-vetoed into silence). RANGING and COMPRESSION angle
distributions overlap (both flat, as they should); UNKNOWN skews higher (transitional).

Every PRIOR in `REGIME_TRUTHS.md` §4 gets a distribution column this way as labeled
tape accumulates: the ADX ramps from TRENDING/BREAKOUT onset ticks, the crossings ramp
from confirmed ranges, the compression width ramp and RANGE_ROOM span from the
squeeze-vs-range split, the sweep rejection ramp and half-life from confirmed sweeps.

---

##### 5. Circularity guard (non-negotiable)

Truths tuned and thresholds calibrated on the *same* sessions look beautiful and mean
nothing. **Split the tape:** the sessions used to fit `FLAT_ANGLE_CUT_DEG` (and every
other knob) must not be the sessions used to run Tier-B acceptance. Practically: as the
store accumulates, hold out a rotating ~30% of sessions as the acceptance set, fit on
the rest, and re-check. A knob that only validates on its own fit set is unproven.

---

##### 6. Known limitations

- **Volume-less index tape.** Cash SPX logs `volume = 0`, making the engine VWAP a 0/0
  NaN (warning suppressed in the harness). Our scorer reads `price_vs_bb`, not VWAP, so
  scores are unaffected — but any *future* VWAP-based factor is unreliable for index
  symbols and must guard for it.
- **Chop-only sample.** Every session held so far is chop/flat. TRENDING and SWEEP are
  structurally unvalidatable until trend/sweep tape is captured (§2 Tier B).
- **As-of boundary effects.** Timeframe frames are sliced at `index ≤ t`; a partially
  formed current higher-TF bar is excluded rather than half-counted. Conservative and
  deterministic; matches how a live tick sees closed bars.
- **Single-instance engines.** The harness reuses one engine singleton set across all
  symbols; engines are stateless across `.analyze()` calls (verified: they return fresh
  state objects), so cross-symbol contamination is not possible — but keep it in mind if
  an engine ever caches per-symbol.

---

##### 7. Monday workflow (the RTH plan)

1. Let the candle logger record as usual — no observer deployment needed for this.
2. EOD, pull the session dir and run: `python -m tests.replay_confluence
   data/OHLC/<date> --jsonl data/shadow/replay_<date>.jsonl`.
3. Read the report: Tier-A must stay 5/5; note RANGING dominance and the all-zero %.
4. **Label the day's exceptional symbols** (trend / coil-pin / sweep) and file which
   sessions fill the Tier-B gaps.
5. Append the flat-angle-by-label rows to the accumulating calibration set. Only sweep
   the cut once ≥ several distinct sessions are in — never off one day.
6. When a trend day and a confirmed sweep are in hand, Tier B can complete and the
   PRIORs graduate to VALIDATED — at which point the scorer is calibration-ready and
   the Phase-0 integrator port (Layer 2) can begin against real evidence distributions.

---


<!-- ================= was: docs/README_offline_backtest_harness.md ================= -->

##### Backtest Harness — v1.0

`tests/backtest_harness.py` — drops next to `replay_confluence.py`, reads-only,
drives the **real deployed engines** over a spliced multi-day 1-minute file per
symbol. It answers "how would my bots have traded this tape" faithfully for the
signal layer, and *approximately* for dollars.

##### Run

```
python tests/backtest_harness.py --symbol CVX_1m_30d.csv --vix VIX_1m_30d.csv
python tests/backtest_harness.py --symbol CVX_1m_30d.csv --vix VIX_1m_30d.csv --model-premium --dte 0
```

- `--model-premium` adds Black-Scholes dollar P&L off the VIX level (off by default)
- `--dte N` expiry for the premium model: `0` = 0DTE (default), `5` ≈ weekly
- `--fed-days 2026-06-17,2026-07-29` marks FOMC dates for the macro dimension

Files are `timestamp,open,high,low,close,volume`, ET, RTH; one file per symbol.
VIX same format/window. It runs in the repo, so it always drives whatever version
of the engines is currently deployed.

##### What is exact vs modeled

**Exact — drives the actual modules, no reimplementation:**
regime labels (`regime_classifier` + the four engines), v3 confluence scores
(`regime_confluence`, uncalibrated), ORB setups & stops (`orb_engine` v3.2), the
entry gate (`main.py` v3.2 `ORB_FIRES_REGARDLESS_OF_REGIME`), the structure stop
(`exit_engine` v3.1, on the underlying), and the VIX no-entry gate.

**Modeled — not exact (no option chain in an OHLC file):**
option premium and dollar P&L via Black-Scholes off VIX. The exit path runs the
real two-stop **AND** — structure stop (underlying close beyond the impulsive
origin), the **−25% premium floor**, and the target, whichever fires first — with
the floor modeled to fill at −25% (so no modeled loss is ever worse). Caveats:
0DTE by default; `vol = VIX/100` (apt for index ORBs, a rough proxy for single
names whose IV ≠ VIX); European BS, no smirk, no bid/ask, no slippage. Treat
dollar figures as **relative**, not a fill-accurate statement.

##### Fidelity notes (why multi-day tape is required)

- Intraday timeframes (1m/5m/15m) are **session-scoped** (reset each session),
  matching the live feed's "never padded across the overnight gap." Higher
  timeframes (1h/4h/1d) use full continuous history. On a single session 1h is
  starved and direction collapses to NEUTRAL — ~15+ sessions gives it real depth.
  This is faithful to the live feed and is *why* the ORB window often reads
  UNKNOWN/RANGING (the 5m ADX is short all morning).
- 1d/4h are synthesized from the tape; over ~a month they're short (<55 bars) and
  contribute NEUTRAL, same as the feed's thin daily backfill.

##### Reading the output — worked example (CVX, 19 sessions, 2026-06-12→07-10)

```
REGIME: RANGING 50% · COMPRESSION 31% · UNKNOWN 13% · TREND_BEAR 3% · TREND_BULL 2%
ORB: 29 setups, 29 fired, 0 gate-blocked (11 long / 18 short — short-lean = bearish drift)
  exact underlying:  TARGET 5 · STRUCTURE_STOP 24 · −0.54R expectancy
  modeled 0DTE:      TARGET 5 · STRUCTURE_STOP 4 · PREMIUM_FLOOR 20 · mean −5% / median −25%
```

What it tells you:

- **CVX was a chop/range month** (50% RANGING) — ORB break-and-retests mostly
  faked out (24/29 structure-stop on the underlying, −0.54R). That's the tape, not
  a bug: the un-gate deliberately trades this population.
- **On 0DTE the −25% floor is the binding stop, not the structure stop** (20 vs 4).
  Theta + a small retrace burns 25% of premium before price ever closes beyond the
  impulsive origin. This is exactly the "is the impulsive-low too loose in practice"
  question from the shadow plan — on 0DTE, yes. On `--dte 5` it shifts back toward
  the structure stop. **The ORB expiry choice per symbol changes the answer**, so
  run both.
- The 5 directional winners (+67% etc.) nearly offset the −25% losses → modeled
  mean −5%. A low-edge month, honestly rendered.

##### Two honest limits

- **One symbol, single-stock, VIX-vol proxy.** CVX's real IV isn't VIX; the dollar
  layer is roughest for single names. It's most faithful for the index ORBs
  (SPX/QQQ/DIA) the strategy is actually built around.
- **It does not validate the strategy.** It shows what *would have fired* and how it
  *would have resolved* on this tape, on a sound risk model. Edge is a
  many-symbol, many-month question — which is what the diary + shadow corpus are
  for. This harness is the offline complement to that, not a substitute.

---

