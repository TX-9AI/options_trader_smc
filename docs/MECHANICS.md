# MECHANICS — how the system decides, sizes, and exits

Current behaviour reference. Regime definitions (Layer 1), every exit path, the observability fields on the trade record, and the ORB regime/stop models.

**Consolidated 2026-07-28.** Nothing was rewritten or summarised — each
former file is preserved verbatim as a section below, so historical
decisions stay on the record and fixes don't get quietly reverted.

## Contents

- **REGIME_TRUTHS.md — Layer 1 (Regime Confluence) definitional truth audit**  <sub>(was `docs/REGIME_TRUTHS.md`)</sub>
- **EXIT RULES — every way every trade closes, and what it's set at**  <sub>(was `docs/EXIT_RULES.md`)</sub>
- **Trade Record — Observability Fields**  <sub>(was `docs/TRADE_RECORD_FIELDS.md`)</sub>
- **ORB Regime Un-Gate — v3.2 (2026-07-11)**  <sub>(was `docs/README_orb_regime_ungate_v3_2.md`)</sub>
- **ORB Stop-Placement Rework — v3.1 (2026-07-11)**  <sub>(was `docs/README_orb_stop_rework_v3_1.md`)</sub>

---


<!-- ================= was: docs/REGIME_TRUTHS.md ================= -->

##### REGIME_TRUTHS.md — Layer 1 (Regime Confluence) definitional truth audit

**v0.4 — 2026-07-27 — Definitional only; all thresholds PRIOR.** Companion to
`analysis/regime_confluence.py` v1.3 (this document's implementation; smoke-verified,
tape-unvalidated).
Written against **v3 HEAD `49d7af8`** (engines + `regime_classifier.py` v1.3) and the
off-repo reference `conviction_integrator.py` v1.0 (`EvidenceAdapter`, built vs
`ef76b4a`/v1.2 — every field it reads was re-verified present at `49d7af8`).

Changelog:
- **v0.4** — COMPRESSION gains a **containment hard veto** (`price_vs_bb == INSIDE`),
  surfaced by the v1.3 A/B pool: on squeeze-BREAK ticks (price closed beyond a narrow
  band, ATR not yet expanded) COMPRESSION scored >0.5 while the honest BREAKOUT did too
  — an A3 violation latent since v1.0 that never collided until breakout could
  accumulate. Definitional, not tuning: compression's truth is flat center + tightening
  container + **faded** excursions, and a close beyond the band edge is an unfaded
  excursion — release, not storage. Sync with `regime_confluence.py` v1.3.1.
- **v0.3** — **CONFLUENCE EXCAVATION** (sync with `regime_confluence.py` v1.3).
  Four of the five scorers did not implement the §0 grammar they claimed. Two
  (`BREAKOUT_VOLATILE`, `SWEEP_REVERSAL`) had an **empty corroborator sum**, so
  `_combine` defaulted that term to 1.0 and the score was vetoes × dampers with
  nothing accumulating. Two (`RANGING`, `COMPRESSION`) carried a **constant 1.0
  corroborator** — a fixed contribution that never varied with evidence, which
  is a Boolean gate's flat base, not a degree of agreement. Role changes:

  | regime | factor | v0.2 role | v0.3 role | why |
  |---|---|---|---|---|
  | SWEEP | rejection strength | ◐ soft-necessary | ✚ corroborator (merged) | weak rejection ⇒ weakly *supported*, not partly *invalid* |
  | SWEEP | **trend opposition** | *(absent)* | ◐ soft-necessary | the matrix's `direction (reject dir)` cell, finally implemented |
  | SWEEP | level quality (pool touches) | *(absent)* | ✚ merged into rejection quality | correlated with depth; merging avoids double-count |
  | SWEEP | trend deceleration | *(absent)* | ✚ corroborator (largest) | a reversal's thesis IS that the prior move is spent |
  | BREAKOUT | ATR expansion | ◐ soft-necessary | ✚ corroborator | directional regime ⇒ compensatory (§0 asymmetry) |
  | BREAKOUT | band clearance, momentum | *(absent)* | ✚ corroborators | breakout *strength* must accumulate |
  | RANGING | base constant | ✚ corroborator (1.0) | **deleted** | a constant is not evidence |
  | RANGING | midline balance | *(absent)* | ✚ corroborator | rotation must be two-sided, not merely frequent |
  | COMPRESSION | base constant | ✚ corroborator (1.0) | **deleted** | a constant is not evidence |
  | COMPRESSION | ATR contraction depth | *(absent)* | ✚ corroborator | contraction *depth* must accumulate |
  | COMPRESSION | narrowness | ◐ soft-necessary | ◐ **unchanged** | premium regime ⇒ mass stays in vetoes (§0 asymmetry) |

  The last row is the load-bearing one: **the re-slotting rule is not universal.**
  §0's failure-cost asymmetry decides it per regime — directional regimes keep
  corroborators compensatory because the expensive error is *missing* the move;
  premium regimes keep mass in necessary conditions because the expensive error
  is *claiming* the regime. Promoting narrowness was tried and reverted when it
  let COMPRESSION score 0.25 on wide-band RANGE tape.
  Also: the `OSC_CROSS_*` bounds are **decoupled** per scorer (RANGING reads many
  crossings as rotation, COMPRESSION reads few as a coil — one axis, opposite
  ends, so any calibration of one silently moved the other), and the two
  no-window fallbacks that fabricated a score are deleted in favour of `None`.
  **Weights are design-derived, not tape-fitted** — each block states the minimum
  evidence set that should just barely score and solves for it. Pool calibration
  is the next pass.
- **v0.2** — RANGING gains a **`room_s` soft-necessary** on `bb_width_pct` (a range
  needs room to oscillate; as the container squeezes, range-ness hands off to
  COMPRESSION on the same width axis). Discriminator matrix + calibration table
  updated. Sync with `regime_confluence.py` v1.0.
- **v0.1** — initial six-regime audit, three-tier factor grammar, discriminator
  matrix, UNKNOWN disposition table.

Scope: **Layer 1 only.** This document defines *what the tape is at this instant*
per regime. It does not smooth, remember, count-over-N, or accumulate — that is
Layer 2 (the conviction integrator). It does not reference strikes, premium,
sizing, fills, or tradability — that is Layer 3. Where a truth *wants* persistence,
it is written in its instantaneous form and the persistence is handed to Layer 2
in a **[→L2]** margin note.

---

##### 0. The factor grammar (decisions #3 and #4, resolved)

Every factor is sorted into exactly one of three roles. The per-regime score is:

```
score_R = ( ∏ hard_veto_i ∈ {0,1} )          # definitional gates — any 0 ⇒ regime impossible
        × ( ∏ soft_necessary_j ∈ [0,1] )      # graded necessary conditions (ramps, not cliffs)
        × ( Σ w_k · corroborator_k ),  Σ w_k = 1   # independent compensatory evidence
```

This is the brief's `(∏ vetoes) × (Σ wᵢfᵢ)` **taken literally**, with the middle
term added: factors that are *necessary but graded* live outside the sum as soft
multipliers, so the sum contains only genuinely compensatory evidence. The
adapter's hand-rolled products (`expand_s * outside_s`, `max(align, ramp(adx))`)
are exactly this pattern discovered ad hoc; here it is made explicit.

**Why this shape and not a global product or global sum** (rationale — does NOT
enter runtime code):

- A global **product** makes every factor a quasi-veto; the score sits near 0
  except in perfect windows and spikes rarely. Fed to the leaky integrator, a
  mostly-zero signal reads as *disagreement*, conviction bleeds, and genuine
  regimes fight to commit. It also depresses the evidence ceiling below the
  ~0.85 the Layer-2 τ/θ constants were derived against.
- A global **sum** lets a real veto (flat center in a trend) be out-voted by
  agreeing corroborators — the disguised-trend failure that sells premium into a
  move.
- **Failure-cost asymmetry** decides the lean per regime: directional regimes
  (BREAKOUT, TRENDING) keep corroborators *compensatory* — the expensive error is
  *missing* the move (the 07-09 UNKNOWN disaster). Premium regimes (RANGING,
  COMPRESSION) keep more of their mass in *hard vetoes* — the expensive error is
  *claiming range during a disguised trend*. This asymmetry sorts the factors; it
  is recorded here as design rationale and is **never** a runtime reference to any
  trade type.

**Role legend:** `⛔ HARD VETO` (∈{0,1}) · `◐ SOFT-NECESSARY` (∈[0,1], multiplies) ·
`✚ CORROBORATOR` (∈[0,1], weighted-summed) · `[→L2]` persistence deferred to Layer 2.

**Input vocabulary** (verified at HEAD; these are the only readable fields):
`TrendState`: primary_adx, aligned_timeframes/total_timeframes, overall_direction,
is_bullish/is_bearish · `TrendVote`: momentum {ACCELERATING/DECELERATING/FLAT} ·
`VolatilityState`: atr_current, atr_avg_20, atr_state {EXPANDING/CONTRACTING/STABLE},
bb_width_pct, bb_state {SQUEEZE/EXPANDING/NORMAL}, price_vs_bb {INSIDE/ABOVE_UPPER/
BELOW_LOWER}, is_expanding, is_compressing, price_vs_vwap · `StructureMap`:
structure_sequence {HH_HL/LH_LL/MIXED/NEUTRAL}, in_sr_zone, nearest_sr_distance_pct ·
`LiquidityMap`: recent_sweep, sweep_age_bars, named levels · `LiquiditySweep`:
reclaimed, closes_beyond, rejection_pct, swept_named_level, bars_ago · plus the
Layer-1-internal **flat_angle_deg(closes, atr)** and **midline_crossings(closes)**
computed over the rolling 25-bar window (a property of the current window — legal).

---

##### 1. TASK 1 — Per-regime truth audit

##### TRENDING_BULL / TRENDING_BEAR  *(directional — corroborators compensatory)*

The two are one definition; `overall_direction` routes the score to one label and
zeroes the other. `_BEAR` flips the sign on every directional read.

| role | factor | field / formula | PRIOR |
|---|---|---|---|
| ⛔ HARD VETO | no contradicting structure | `structure_sequence` ≠ contra (contra = LH_LL for bull, HH_HL for bear) | — |
| ⛔ HARD VETO | direction is not neutral | `overall_direction` ∈ {BULLISH, BEARISH} | — |
| ◐ SOFT-NECESSARY | trend strength | `ramp(primary_adx, ADX_TREND−5, ADX_STRONG_SOLO)` = ramp(20, 35) | 20 / 35 |
| ✚ CORROBORATOR | timeframe alignment | `aligned_timeframes / total_timeframes` | w≈0.6 |
| ✚ CORROBORATOR | momentum accelerating | `momentum == ACCELERATING` (per primary TF) | w≈0.4 |

**Settled hard truths:** structure-contradiction veto (v1.2) and non-neutral
direction. A tape whose swings print LH_LL cannot be a bull trend regardless of ADX.
**Graded:** ADX strength is necessary-but-graded — soft, not a cliff. Alignment is
**corroboration, not a gate** — the v1.3 coverage fix: above `ADX_STRONG_SOLO=35`,
unambiguous strength carries the trend even when alignment momentarily fractures.
Encoded as a corroborator (in the sum), so weak alignment *lowers* the score without
zeroing it — this is precisely what stops the 07-09 clean-breakout-scored-UNKNOWN
failure. **Wrongly excluded by v1.3's boolean form:** marginal-ADX trends with
perfect alignment scored identically to strong-ADX trends; graded ADX fixes this.
**Discriminator vs adjacent regimes:** see matrix — the load-bearing one is the
value-center veto against RANGING (a trend's value migrates; a range's does not),
expressed there as RANGING's flat-angle veto being TRENDING's mirror.

*Note — ADX slope:* rising/falling ADX would strengthen this, but true ADX-slope is
not a HEAD field. `momentum {ACCELERATING/DECELERATING}` is the instantaneous proxy
and is used. A dedicated ADX-slope field is a **proposed engine addition**, not
assumed here. **[→L2]** "ADX has been rising for N ticks" is persistence — the
integrator banks a rising series of TRENDING evidence; Layer 1 only reports
accelerating-*now*.

---

##### BREAKOUT_VOLATILE  *(directional — necessary-conjunctive, minimal sum)*

| role | factor | field / formula | PRIOR |
|---|---|---|---|
| ◐ SOFT-NECESSARY | range expanding | `ramp(atr_current/atr_avg_20, 1.0, 1.5)` if `is_expanding` else same ramp(1.1,1.6)×0.6 | 1.0/1.5 |
| ◐ SOFT-NECESSARY | price accepting outside envelope | `1.0 if price_vs_bb≠INSIDE else ramp(primary_adx, 38, 50)` | 38/50 |
| ✚ CORROBORATOR | (reserved) velocity-at-level | *proposed — see below* | — |

Breakout is genuinely **two necessary conditions with almost no corroborators**, so
its score is a soft-necessary product and the sum is (for now) near-empty — the one
place the adapter's "product" form is *correct* and is kept. Expansion answers "is
energy releasing," envelope-acceptance answers "through a level, not just poking."

**Momentum carry (the anchor), and why it is Layer 1 and not Layer 2:** the
envelope factor does **not** hard-zero on a momentary BB re-entry — at clearly-high
ADX (`ramp(38,50)`) an inside-band print still scores. This reads **only current
ADX**: "high ADX *now* means an inside print *now* doesn't contradict breakout." It
is a statement about this tick, so it is legal Layer 1. Remembering that price *was*
outside 3 ticks ago would be memory — illegal; not done. **[→L2]** persistence of
the breakout across a genuine multi-tick re-entry is the integrator's decay
resistance, not ours.

**Discriminator vs TRENDING:** breakout = expansion *through* a level (envelope +
`atr_state=EXPANDING`); trending = sustained strength that is agnostic to expansion
(a trend runs at any vol). **Discriminator vs SWEEP at a level:** acceptance
(`closes_beyond ≥ 2`) is breakout; penetrate-then-reclaim is sweep — the same level,
opposite resolution. **Future first-class discriminator (proposed, Phase-3+):**
velocity sign at the mapped level — accelerate-*through* vs decelerate-*reverse* —
which would separate BREAKOUT from SWEEP on the *approach*, before the reclaim
resolves. Needs an engine velocity field; flagged, not assumed.

---

##### RANGING  *(premium — hard veto carries the weight)*

| role | factor | field / formula | PRIOR |
|---|---|---|---|
| ⛔ HARD VETO | flat value center | `flat_angle_deg(w25, atr) < FLAT_ANGLE_CUT_DEG` | 20° |
| ◐ SOFT-NECESSARY | flatness depth | `ramp(CUT − angle, 0, FLAT_ANGLE_SOFT_DEG)` | soft 8° |
| ◐ SOFT-NECESSARY | room to oscillate | `ramp(bb_width_pct, RANGE_ROOM_LO, RANGE_ROOM_HI)` | 0.05 / 0.20 |
| ✚ CORROBORATOR | midline oscillation | `ramp(midline_crossings(w25), 2, 5)`, blended `0.4 + 0.6·osc` | 2/5 |

**The deal-breaker truth (validated):** a trend cannot hold a flat value center —
its value migrates; a range oscillates around a stable local one. `flat_angle_deg`
is instrument-agnostic by the `ATR·√n` normalization (fixed the SPX raw-percent
false-flat, 48%→17%), so one 20° cutoff serves SPX and a $4 name. At/above the cut
the regime is **vetoed to 0.0** no matter how low ADX looks. **Local-center anchor:**
the window's own regression midline — valid *only because the veto has certified it
flat* (session VWAP too strict, trailing mean too loose; in a trend the veto fires
first, so the trailing-mean leak is structurally blocked). **No R²/fit filter** —
shark-fin scatter is expected; only the center must hold. Oscillation is
**confirmation only** and enters as a corroborator: crossing *frequency*
distinguishes rotation (a range) from a pin/drift, not residual balance (which is
near-balanced by construction).

**Room to oscillate (v0.2 — the COMPRESSION handoff):** a range needs room. As the
container squeezes toward zero width, the tape is no longer *oscillating across* a
range — the oscillation is dying into a coil, and range-ness must fade. `room_s`
ramps RANGING down over `bb_width_pct ∈ [0.05, 0.20]`; this is the exact instantaneous
complement of COMPRESSION's `narrow_s` — the **same width axis pushing the two regimes
apart**, RANGING fading as COMPRESSION rises. A normal/wide flat center with active
crossings stays full RANGING; a squeezed flat center hands off. It does **not** require
wide bands (energetic chop at moderate width still ranges) — it only bites at genuine
squeeze. In the transition both score moderately, which is honest; Layer 2 resolves.

**Wrongly excluded by v1.3:** the old `_is_ranging` (ADX<20 + price INSIDE bands)
was too strict to claim energetic mean-reverting chop — the 88% of the 07-09 UNKNOWN
dwell. Elevated ADX and BB pokes are **allowed** here: fin stabs hit the edges by
nature. The angle read is what admits that chop as RANGING. **Honest caveat:** a
single 25-bar window is a noisy estimator — a marginal drift can read 12° on one
window. That is *why Layer 2 exists*: single-window misreads don't persist, ranges
do. Layer 1 reports the honest per-window angle; the impostor separation is
downstream. **[→L2]** "held the flat angle 24–29 bars" (genuine) vs "12–15 bars"
(impostor) is the integrator's slow RANGING τ_up — never a Layer-1 counter.

**Fallback** (bars unavailable): reduced-ceiling quiet-range read (`adx <
ADX_RANGE_THRESHOLD` and `price_vs_bb=INSIDE` and not expanding) → 0.6, so the
regime is not blind. Returns **None** only when the window/ATR are unreadable
(unobservable ≠ contradicted).

---

##### COMPRESSION  *(premium — the weakest regime; truths written here)*

**This is the regime the ROADMAP flags as "little more than a BB-width percentile."**
The adapter's current read (`ramp(0.20 − bb_width_pct, 0, 0.15) × quiet`) has **no
flat-center truth and no discriminator against early-RANGING** — its known gap. New
Layer-1 definition:

| role | factor | field / formula | PRIOR |
|---|---|---|---|
| ⛔ HARD VETO | flat value center | `flat_angle_deg(w25, atr) < FLAT_ANGLE_CUT_DEG` | 20° (shared w/ RANGING) |
| ⛔ HARD VETO | containment (v0.4) | `price_vs_bb == "INSIDE"` — close beyond band edge ⇒ coil resolving | — |
| ◐ SOFT-NECESSARY | bands narrow | `ramp(BB_WIDTH_COMPRESSION_PCT − bb_width_pct, 0, 0.15)` | 0.20 |
| ◐ SOFT-NECESSARY | not expanding | `1.0 if atr_state∈{CONTRACTING,STABLE} and not is_expanding else 0.0` | — |
| ✚ CORROBORATOR | squeeze state | `1.0 if bb_state == SQUEEZE else 0.0` | w=1.0 |

**The discriminator we owe — COMPRESSION vs early-RANGING:** *both* are flat-center
(so both take the flat-angle veto — this is the fix: compression now shares RANGING's
center truth instead of ignoring it). They separate on **band width regime**:
RANGING oscillates across a flat center at *normal/expanded* width (crossings are its
signature); COMPRESSION is a flat center at *contracted* width with the crossings
*collapsing* toward the midline. In Layer-1 instantaneous terms: low `bb_width_pct` +
`atr_state=CONTRACTING/STABLE` + `bb_state=SQUEEZE` = compression; normal width +
oscillation = ranging. The handoff is **symmetric on the width axis** (v0.2):
COMPRESSION's `narrow_s` rises exactly as RANGING's `room_s` falls, so squeeze moves
score from one to the other rather than lighting both. **Potential-energy read
(instantaneous):** a range *spends* energy — excursions reach the edges and turn
around (crossings, at width); a coil *stores* it — the envelope tightens while
excursions fade (SQUEEZE + collapsing crossings, encoded as the `stored` corroborator
`1 − osc`). Both flat-center; the separator is release-vs-absorb, read at one tick.
A tape can score *both* moderately during the transition — that is honest, and Layer 2
resolves which is committing.

**[→L2] — the "persisting" truth is explicitly NOT here.** The ROADMAP wants
"contraction persisting — width percentile falling or floored *over N bars*." That
"over N bars" is accumulation and is **deferred to the integrator**: Layer 1 reports
narrow-and-flat-*now*; the integrator banking a run of high COMPRESSION ticks *is*
"it has been coiling." Writing an N-bar counter here would double-smooth the system.
**Discriminator vs BREAKOUT:** exact opposite on the width axis — `is_expanding` /
`atr_state=EXPANDING` zeroes the not-expanding factor, so a tape cannot score
COMPRESSION and BREAKOUT together.

---

##### SWEEP_REVERSAL  *(event overlay — hard-veto triple × age-decay)*

| role | factor | field / formula | PRIOR |
|---|---|---|---|
| ⛔ HARD VETO | LOCATION — named zone swept | `recent_sweep.swept_named_level` non-empty | — |
| ⛔ HARD VETO | REJECTION — reclaimed | `recent_sweep.reclaimed == True` | — |
| ⛔ HARD VETO | non-acceptance | `recent_sweep.closes_beyond < SWEEP_ACCEPT_CLOSES` | <2 |
| ◐ SOFT-NECESSARY | **trend opposition** (v0.3) | `1 − ramp(primary_adx,20,35)·opp_mom` when the reversal direction fights `overall_direction`; else 1 | 20/35 |
| ◐ SOFT-NECESSARY | age-decay | `0.5 ** (sweep_age_bars / SWEEP_HALFLIFE_BARS)` | half-life 3 bars |
| ✚ CORROBORATOR | rejection quality (v0.3) | `0.60·ramp(rejection_pct,0.002,0.008) + 0.40·ramp(pool.touch_count,2,5)` | w = 0.45 |
| ✚ CORROBORATOR | trend exhaustion (v0.3) | `primary_momentum` DECELERATING 1.0 / FLAT 0.5 / ACCELERATING 0.0 / no-vote 0.0 | w = 0.55 |

**Direction is definitional and was missing (v0.3).** The discriminator matrix
below has always carried a `direction — (reject dir)` cell for SWEEP, but the
implementation never received `trend_state` at all: `_sweep(self, liq_map)` was
structurally incapable of seeing a trend. On 2026-07-27 that let a lone
level-rejection score 0.62 and short a name trending +7.2% on the day. The
opposition term is **multiplicative** precisely so a strong accelerating trend
can zero the regime outright, and `opp_mom` weights it by whether that opposing
trend is ACCELERATING (1.0 — full suppression) or DECELERATING (0.25 — barely
suppresses, because a decelerating opposing trend is the exhaustion being traded).

**Level quality is matched, not read.** `LiquiditySweep` carries no strength
field; the swept pool is matched back through `LiquidityMap.pools` by
`pool_price`. A `getattr(sweep, "level_strength", 0.0)` would have returned 0.0
forever with no error and no log — the same silent-attribute failure that
hard-blocked the continuation trade (see `trend_engine` v3.2, defect W).

**The sweep truth triple (definitional, closed — v1.1):** LOCATION + PENETRATION +
REJECTION. All three are hard vetoes no other regime touches — its specialism made
literal. **Acceptance = breakout, not sweep:** `closes_beyond ≥ 2` fails the
non-acceptance veto, which is the exact BREAKOUT-at-a-level discriminator. **Age
decay is the key event-property:** a sweep without follow-through must *evaporate* —
the `0.5**(age/3bars)` half-life is what lets a rising BREAKOUT *displace* a stale
sweep instead of the sweep lingering (the AMZN failure). This decay reads
`sweep_age_bars` (a current field), so it is instantaneous, not memory. **[→L2]** the
*displacement* of a stale sweep by a competitor is the integrator's δ-margin
mechanic; Layer 1 only decays the evidence.

---

##### 2. Discriminator matrix (mutual exclusivity from truths, not cascade order)

The system reduces to **three organizing binary truths** stacked with graded
evidence. Read each column for the axis that separates the pair.

| axis (normalized) | TREND_BULL | TREND_BEAR | RANGING | COMPRESSION | BREAKOUT | SWEEP |
|---|---|---|---|---|---|---|
| **value center** (flat_angle) | migrating ⛔ | migrating ⛔ | **flat ⛔** | **flat ⛔** | migrating | — |
| **band width** (bb_width_pct/state) | — | — | **needs room ◐** | **contracting ◐** | **expanding ◐** | — |
| **level resolution** (closes_beyond/reclaim) | — | — | — | — | **accept-through ◐** | **reclaim ⛔** |
| ADX strength | ≥mid ◐ | ≥mid ◐ | any (allowed) | low | ≥high ◐ | — |
| direction | bull ⛔ | bear ⛔ | — | — | (breakout dir) | (reject dir) |
| oscillation crossings | low | low | **high ✚** | collapsing | — | — |
| named-zone location | — | — | — | — | — | **present ⛔** |

**The three cleaving truths:**
1. **value center migrating vs flat** — cleaves {TRENDING, BREAKOUT} from {RANGING,
   COMPRESSION} before any other factor speaks. The master discriminator.
2. **band width contracting vs expanding** — within flat-center, splits COMPRESSION
   (contracting) from RANGING (normal); within migrating, marks BREAKOUT (expanding).
3. **acceptance vs rejection at a level** — within migrating-at-a-level, splits
   BREAKOUT (accept-through) from SWEEP (penetrate-reclaim).

Everything else is graded confluence stacked on top. **A signal's role is
regime-relative and that is the consensus mechanic:** high ADX lifts TRENDING/
BREAKOUT and is *allowed* under RANGING; width-contraction lifts COMPRESSION and
zeroes BREAKOUT. A tape where ADX rises *and* width contracts genuinely scores two
regimes moderately and *should* — the ambiguity is honest, and Layer 2 sorts it over
time. Mutual exclusivity is enforced by opposing truths, never by priority order.

---

##### 3. TASK 2 — UNKNOWN disposition table

UNKNOWN is eliminated **as a regime**. Every population it absorbed gets an explicit
destination. Layer 1's obligation: **always emit scores, never abstain** (the adapter
already satisfies this — it returns per-regime floats/None, never a global UNKNOWN).
The UNKNOWN *emission* deletion is Layer 2's port task (ROADMAP Phase 0), not Layer 1.

| UNKNOWN population (07-09 autopsy) | share | new destination | mechanism |
|---|---|---|---|
| Breakout flicker (BB re-entry at ADX 43–50) | 12% (≤30s) | **BREAKOUT** score stays >0 | momentum carry: `outside_s=ramp(adx,38,50)` doesn't zero on inside print |
| Energetic shark-fin chop (flat VWAP, high-vol fin stabs) | 88% (long dwell) | **RANGING** score dominant | flat-angle veto passes + crossings corroborate; elevated ADX/pokes allowed |
| Genuine regime-to-regime transition | — | **both** regimes score moderately | honest low/split scores; Layer 2 displacement resolves, no UNKNOWN interlude |
| Pre-open / insufficient bars | — | RANGING **None** (fallback if partial) | `None` = unobservable; integrator stale-decays, ORB lockout covers commit window |
| Engine-state fault (stale feed / restart gap) | — | **DATA-FAULT state** (not a regime) | owned by `candle_feed` heartbeat + integrator STALE; the only surviving hard block |

**`UNKNOWN` string-scrub checklist** (Phase 4 — grep the fleet before enum deletion):
`analysis/regime_classifier.py` (enum + `_classify` fallback) · `main.py` (dispatch
no-trade gate ~L469–560) · `status.py` · `query.py` · `eod_summary.py` ·
`notifications/` (regime-change alerts) · `conviction_integrator.py` emission law
(§2 — the `→ UNKNOWN` fallback becomes always-argmax) · any `data/shadow/` JSONL
readers keyed on the label. Data-fault no-trade **survives**; indecision no-trade
does not.

---

##### 4. Open calibration knobs (all PRIOR — fit from candle-logger tape, never one day)

| knob | current PRIOR | calibration plan |
|---|---|---|
| **FLAT_ANGLE_CUT_DEG** | 20° | **top priority.** Sweep 16–26° against labeled range/trend windows from multi-day store tape. One day clusters everyone at 24–32° — needs base rates. |
| FLAT_ANGLE_SOFT_DEG | 8° | joint with the cut, from the same labeled windows |
| crossings ramp | 2 / 5 | rotation-vs-pin frequency on confirmed ranges |
| ADX ramps (trend/breakout) | 20/35, 38/50 | ROC of score vs labeled trend/breakout onset |
| bb_width compression ramp | 0.20 / 0.15 | squeeze base rate; separate early-compression from ranging |
| RANGE_ROOM_LO / _HI | 0.05 / 0.20 | width at which RANGING hands off to COMPRESSION; fit jointly with the compression ramp against the same squeeze base rate |
| sweep rejection ramp | 0.002 / 0.008 | confirmed-sweep rejection_pct distribution |
| sweep half-life | 3 bars | follow-through-vs-evaporation survival curve |
| corroborator weights `w_k` | see tables | **Phase 1 tape** — per-regime, one factor at a time |

**Circularity guard:** truths tuned and weights calibrated on the *same* sessions
look beautiful and mean nothing. Split the tape — the sessions used to set these
thresholds must not be the sessions used to validate the scorer.

---


##### A2 — TREND and RANGE co-occurrence: a CO-TRUTH, and what it does NOT buy

Settled 2026-08-05 across two measurements. Recorded here so it is not
re-opened.

**It is not a contradiction.** TRENDING reads a ~70-minute lookback, RANGING a
~25-minute one. A tick scoring both above 0.5 is a slow uptrend containing a
tight recent range — both labels are correct about their own horizon. The old
acceptance check asserted mutual exclusion and therefore FAILED every session
the harness ever ran (16 diary sessions, all 4/5). It is now a **banded metric**
(`A2_BAND_HI = 8%`, observed 3.0-5.3%) that passes in-band and can finally raise
a real alarm out of it. **A check that always fails is not a check.**

**The HTF trend carries NO forward information for the LTF range.** Measured
over 175,302 ticks, 6,860 of them co-occurring (3.9%), with RANGE_ONLY as the
control:

```
+10 bars: range-in-bull-trend median drift  -0.001%  vs a plain range
+20 bars:                                   +0.003%
+30 bars:                                   +0.011%
```

The tool's own pre-registered criterion was *"a materially positive lift
supports treating HTF direction as a drift/bias term on the LTF range"*. At
n≈3,500 per bucket, +0.011% at thirty minutes is a rounding error on a 0DTE
contract. **So HTF direction is NOT a usable drift term inside a range**, and
any proposal to use it as a tiebreaker is measured and rejected, not untested.

**What the co-occurrence DOES cost, and it is not prediction.** On those ticks
Layer 2 commits to a trend label **98% of the time** — TRENDING_BULL 50.6%,
TRENDING_BEAR 47.8%, RANGING **1.5%** — because argmax makes the labels compete.
So on 3.9% of all ticks a genuine range state is INVISIBLE to every strategy
gated on RANGING, which is the condor and the butterfly. The loss is not a worse
forecast; it is a co-truth suppressing half of itself.

**⚠️ AND THE CONVICTION IS PEGGED WHILE IT PREDICTS NOTHING.** Median conviction
on those commits is **1.00** for both BULL and BEAR — the integrator is maximally
confident on exactly the ticks where the drift study says that direction has no
forward content. **Confidence and predictive value have come apart.** That is a
finding about L2's conviction scale, not about A2, and it bears on the L1 freeze:
a label can be certain and uninformative at the same time.

**⬜ THE OPEN CANDIDATE (post-freeze): split A2 into two independently weighted
axes** rather than competing labels, so a range inside a trend is both. It would
NOT improve prediction — that is settled above. It would stop RANGING losing
argmax on ticks where it is true.
**GATE IT ON A MEASUREMENT FIRST, not on the argument.** The replay corpus
already holds all 6,860 ticks with both scores, so one offline pass answers: if
RANGING had won there, how many condor plans would have existed, and in which
regimes? A handful means the architecture change buys little; the condor's
missing population means it has its justification with a number attached. Run it
in the Aug 8-9 slot — it is offline and changes nothing.
**Scope warning:** this makes regimes AXES rather than mutually exclusive
competitors, so every consumer reading `primary_regime` is affected — the
condor's RANGING gate, the continuation's TRENDING gate, the exit-side regime
flip. Post-freeze only.

##### 5. Provenance & boundary ledger

- **Read from HEAD `49d7af8`:** all engine fields, enums, config thresholds, v1.3
  classifier logic. Every field cited above verified present.
- **Reference (off-repo):** `conviction_integrator.py` v1.0 `EvidenceAdapter` — the
  Layer-1 prototype this document audits and re-sorts into the three-tier grammar.
  Built vs `ef76b4a`/v1.2; field-compatible with HEAD (re-verified).
- **Layer boundary held:** no factor references a trade, strike, premium, size, or
  ROI (Layer 3). No factor remembers, counts-over-N, or accumulates (Layer 2) —
  every persistence-flavored truth carries a **[→L2]** deferral. Failure-cost
  asymmetry is design rationale only; it is absent from runtime.
- **Not yet validated on real tape:** the entire Layer-1 factor design. Synthetic
  sims validated the *integrator*, never the *adapter*. Monday's shadow run is the
  first real-tape test — expect PRIOR knobs to move.

**Open decisions carried forward (none block the build):**
- ADX-slope and velocity-at-level are **proposed engine additions**, used via
  proxies (`momentum`, and nothing yet) until built — not assumed present.
- GRIND / VOLATILE_RANGE seventh-regime candidates remain **shelved** (insufficient
  non-chop tape); resume conditions logged separately.

---
*Next deliverable: `analysis/regime_confluence.py` v1.0 — the standalone module
implementing this document (adapter lifted from `conviction_integrator.py`, re-sorted
to the three-tier grammar, breakdown/audit dict added, guarded imports, no side
effects). Then the Layer-1 validation plan for Monday's shadow tape.*

---


<!-- ================= was: docs/EXIT_RULES.md ================= -->

##### EXIT RULES — every way every trade closes, and what it's set at

Extracted from the running code (`exit_engine.py` **v4.1**, `base_strategy.py`,
`config.py` v3.9), 2026-07-15, **last synced 2026-07-23** — covers the runner
refinements (v3.8), the 2026-07-22 **mark-limit closes** (exits post a limit AT
the mark, re-anchored every retry tick; EOD flatten escalates 15:40 mark-limit →
15:45 MARKET), the **continuation exit rework** (v4.0: 5m-anchored FVG trail,
theta-bleed enabled after exhaustion, backstop 40%→25% via
`CONTINUATION_STOP_LOSS_PCT`), and **condor leg management v2** (v4.1: ratcheting
stop, time-gated TP@25%). Original v3.8 note (all
env-tunable for paper A/B): directional floor 25%→**40%** (`OT_MAX_LOSS_PCT`);
trails anchor to **5-minute FVGs** (`OT_USE_5M_FVG_TRAIL`); FVG floors clamped
to ≤ **90% of current** (`OT_FVG_FLOOR_MAX_LOCK_PCT`); post-target fallback
**85%→75%** (`OT_POST_TARGET_TRAIL_LOCK_PCT`); sweep's +100% hard TP replaced
by the post-target trail (`OT_SWEEP_POST_TARGET_TRAIL`). Butterfly floor stays
25%; condor unchanged. Sizing is full-premium based, so at $1000 positions a
floored directional now costs ~$400 — set `OT_DAILY_LOSS_LIMIT` to match
(e.g. 3 stops = $1,200). New telemetry: `max_premium_seen` / `min_premium_seen`
per trade (MFE/MAE) for evidence-based tuning. Evaluated **every tick, first
match wins**, in the order listed per strategy.

Each exit is tagged by its role in the design:
- 🛑 **LOSS-MINIMIZER** — fires on losing trades to cap the damage
- 📉 **GIVE-BACK EXIT** — books a PROFIT, but only when the market starts
  taking it back (trail/structure/momentum) — the "let runners run" family
- 🎯 **HARD TAKE-PROFIT** — closes at a fixed profit level regardless
- ⏰ **TIME EXIT** — the clock, not price

---

##### Universal (every strategy, every mode)

| Exit | Trigger | Value | Tag |
|---|---|---|---|
| Hard close | **15:40 ET mark-limit flatten → 15:45 ET MARKET escalation** (`limit_ladder.hard_close_order_mode`, 2026-07-22) | flatten_all retries every tick to 16:00, pages on failure | ⏰ |

---

##### ORB (the flagship) — **no hard take-profit exists, by design**

| # | Exit | Trigger | Set at | Tag |
|---|---|---|---|---|
| 1 | Hard close | 15:45 ET | — | ⏰ |
| 2 | **Hard stop (−25% floor)** | premium ≤ `stop_premium` | **entry × 0.60 (−40%, `MAX_LOSS_PCT`)** — immutable, set at entry, checked UNCONDITIONALLY every tick regardless of trail state; label carries the record's actual floor pct | 🛑 |
| 3 | **Structure stop** | last CLOSED 1m candle beyond the impulsive candle's wick (`underlying_stop`): close < impulsive low (long) / > impulsive high (short). Closing back inside the ORB range does NOT stop | thesis level, set at entry | 🛑 (thesis death — can fire green or red) |
| 4 | **Theta bleed** | ALL of: held ≥ **20 min** · gain ≥ **+10%** · gain < **+20%** (trail ceiling) · projected decay over next **20 min** (per CALENDAR day, θ×20/1440) ≥ current gain | narrow window: a small, stalled winner only | 📉 |
| 5 | **Past +100%** ("target") | premium ≥ entry × 2.0 (`ORB_TP_MULTIPLIER = 1.0`) — **NO exit fires.** Trail tightens: nearest unfilled in-favor **5m** FVG (1m fallback) converted to a premium floor, else **85% of current premium** | the runner regime | 📉 |
| 6 | **Trail (below +100%)** | Two trails, HIGHER governs: **FVG trail** arms at **+20%** (floor = FVG level, else 80% of current — `FVG_TRAIL_LOCK_PCT`); **% trail** arms at **+50%** (`TRAIL_ACTIVATION_PCT`), initial lock at entry × 1.25 (`TRAIL_LOCK_PCT`), then ratchets to **75% of current premium**, never down | 📉 |

**ORB never exits "at target."** +100% just switches it into the tightest
trail. Every profitable ORB exit is the market taking some back: trail hit,
FVG floor hit, structure break, or theta about to eat a stalled small gain.

##### Sweep Reversal

| # | Exit | Trigger | Set at | Tag |
|---|---|---|---|---|
| 1 | Hard close | 15:45 ET | — | ⏰ |
| 2 | Hard stop | premium ≤ `stop_premium` | **entry × 0.60** (−40%) | 🛑 |
| 3 | **Past +100%** | `SWEEP_POST_TARGET_TRAIL=True` (default): NO hard exit — switches to the ORB post-target trail (5m FVG / 75%-of-current fallback). Env False restores the old `target_hit` guillotine | 📉 (was the one hard TP among directionals) |
| 4 | **BOS exit** | 1-min break of structure against the position — only once pnl > 0 (a healthy retest that hasn't moved yet can't be BOS'd out) | structure-defined | 📉 |
| 5 | Theta bleed | same four gates as ORB (≥20 min, gain in [+10%, +20%), decay ≥ gain) | 📉 |
| 6 | Trail | same dual trail as ORB: FVG arms +20%, % trail arms +50% → 75%-of-current ratchet, higher governs, floored at the −25% stop | 📉 |

##### Iron Condor legs (credit verticals — P&L is inverted: spread value ↓ = profit)

| # | Exit | Trigger | Set at | Tag |
|---|---|---|---|---|
| 1 | Hard close | 15:45 ET | — | ⏰ |
| 2 | **Adverse regime flip** | direction-aware: call spread exits on TRENDING_BULL / BREAKOUT_VOLATILE; put spread on TRENDING_BEAR / BREAKOUT_VOLATILE. A FAVORABLE flip holds (Leg 2 **pauses** — `iron_condor` v3.2; it fires when RANGING returns AND price is at the far band). Note: fired **0 times in 143 legs** to date | regime engine | 🛑 (thesis death, pre-emptive) |
| 3 | **Ratcheting stop** (v4.1) | tightens only: at **+20%** gain → stop moves to **breakeven**; at **+40%** → stop locks **+20%**. Base floor before any ratchet: spread value ≥ credit × **1.25** (`CONDOR_STOP_LOSS_PCT = 0.25`, −25% of credit) | ends the ~+25%→−25% round-trip | 🛑→📉 |
| 4 | **Time-gated TP @ 25%** (v4.1) | ONLY after `CONDOR_ENTRY_CUTOFF_ET`, ONLY when the opposite side is **not open** (a condor leg is never closed on profit — the only reason to close one is the roll), min-hold quote-noise gate | backtest: turned −$242.77 into −$8.43 on 18 standalone legs | 🎯 |
| 5 | **Nickel close** | spread value ≤ **$0.05** (`CONDOR_NICKEL_CLOSE`) | ~all the credit captured; closes to free margin and kill tail risk | 🎯 |
| — | **Broken-wing roll** | not an exit: when one side is tested and rolling the untested side makes it risk-free, the untested vertical closes (books its P&L) and re-opens rolled. Final form — no further adjustments | strategy | — |

##### Trend Continuation (debit directional — NEW 2026-07-18, exits reworked v4.0)

| # | Exit | Trigger | Set at | Tag |
|---|---|---|---|---|
| 1 | Hard close | 15:45 ET | — | ⏰ |
| 2 | **Regime flip** | regime no longer trending **in our direction** — thesis death, the primary smart stop | regime engine | 🛑 |
| 3 | **Backstop −25%** | premium ≤ entry × **0.75** (`CONTINUATION_STOP_LOSS_PCT`, v4.0 — no longer borrows `MAX_LOSS_PCT`) | disaster floor | 🛑 |
| 4 | **Exhaustion (two-stage)** | *only past +15% gain* (`CONTINUATION_EXHAUST_MIN_GAIN`). **Extension**: ≥ 2·ATR from the BB midline → tighten trail to **85%** (does NOT exit). **Divergence**: new favourable extreme on weaker 5-bar momentum → **exit** | detect a spent move | 📉 |
| 5 | **Theta bleed** (v4.0) | placed AFTER exhaustion (the smarter signal gets first refusal): held ≥ 20 min · gain ≥ +10% · below the trail ceiling · projected calendar-day decay ≥ gain | a stalled winner no longer decays to the floor | 📉 |
| 6 | **Runner trail** | FVG trail **anchored to 5m gaps** via `_fvg_frame` (v4.0; graceful 1m fallback); once armed it owns the trade and silences theta | let it run | 📉 |

Prefers live `vol_state`/`trend` threaded from `main.py`; falls back to recomputing
midline/ROC from `df_5m` (restart recovery, adopted) — degrades precision, never raises.

##### Debit Butterfly

| # | Exit | Trigger | Set at | Tag |
|---|---|---|---|---|
| 1 | Hard close | 15:45 ET | — | ⏰ |
| 2 | **Regime flip** | regime becomes TRENDING_BULL / TRENDING_BEAR / BREAKOUT_VOLATILE — any trend breaks the pinning thesis, either direction | regime engine | 🛑 (pre-emptive) |
| 3 | **Max hold** | held ≥ **150 min** (`BUTTERFLY_MAX_HOLD_MIN`, 2.5h) | ⏰ |
| 4 | Hard stop | net value ≤ `stop_premium` | **net debit × 0.75** (−25%) | 🛑 |
| 5 | **Target hit** | net value ≥ debit + **20% of max profit** (`BUTTERFLY_TP_PCT = 0.20`) | 🎯 (deliberately modest — pin plays decay fast) |

No trail, no BOS on butterflies.

##### Adopted positions (found at the broker with no DB plan)

| # | Exit | Trigger | Set at | Tag |
|---|---|---|---|---|
| 1 | Hard close | 15:45 ET | — | ⏰ |
| 2 | Hard stop | sign-correct: long ≤ entry × 0.75; short ≥ entry × 1.25 (`ADOPTED_STOP_PCT = 0.25`, tracking `MAX_LOSS_PCT`) | 🛑 |
| 3 | Trail (LONGS only) | standard % trail (arms +50%, 75%-of-current ratchet). Lone adopted shorts (anomaly) get stop + hard close only — no trail | 📉 |

Already past its stop when adopted → exits first tick ("if red exit, if green
manage").

---

##### The design, confirmed by the tags

Count the profit-side exits: across all six strategies there are exactly
**four 🎯 hard take-profits** — sweep's +100% (default-replaced by the
post-target trail since v3.8, `SWEEP_POST_TARGET_TRAIL`), the condor nickel
close, the v4.1 time-gated condor TP@25% (a standalone-leg salvage, never on a
formed condor), and the butterfly's 20%-of-max — and two of those (nickel,
butterfly) exist
because *holding* a nearly-max-profit 0DTE credit/pin structure is pure tail
risk for pennies. Everything else that books a profit is 📉 **give-back
triggered**: trails that only ratchet up, FVG floors, BOS, the impulsive-origin
structure stop, theta protection on stalled small winners. The flagship (ORB)
has **no hard TP at all** — +100% only tightens the leash.

So yes: by construction, most winning exits WILL log as some form of "stop"
(`trail_stop_hit`, `post_target_trail`, `bos_exit`, `orb_structure_stop` in
the green, `theta_bleed`) — that is the runner philosophy working, not stops
misfiring. The v3.3 exit-reason integrity fix matters here: labels are now
truthful (a post-target trail exit at +140% logs as a trail, never as
`hard_stop_25pct`), so the `exit_reason` distribution in the DB can be read
at face value when checking this design against results.

**The one number to watch:** the loss side is a single flat rule everywhere —
**−25% of premium/credit/debit** (`stop_premium`, immutable since v3.3) plus
thesis stops (structure, adverse regime) that usually fire before the dollars
do. Loss-minimization = whichever dies first, premium or thesis.

---


<!-- ================= was: docs/TRADE_RECORD_FIELDS.md ================= -->

##### Trade Record — Observability Fields

**What this is:** the reference for the diagnostic fields captured on every trade
record. These exist so a trade can be explained *after the fact* without
reconstructing state from logs. If you are trying to answer "why did it take that
trade / at that strike / with that size," start here.

**Where the data lives:**
- Per box: `~/options-trader/trades.db` (table `trades`)
- Consolidated: `~/day_trader_pro/fleet_trades_<YYYY-MM-DD>.json` and `.csv`
  (built by the **EOD conductor**, devtools menu option **50**; re-runnable
  standalone via option **39**)

---

##### Fields

##### `adx_at_entry` — float
ADX at the moment the entry signal fired. Trend strength, 0–100ish. Added
2026-07-24 (commit `0421f37`).

**Why it exists:** post-mortems kept asking "was this a trending tape?" and the
answer had to be reconstructed from replay logs, which were often cold-start and
wrong. Now it is stamped on the trade.

**Reading it:** >40 is a strong trend; <20 is chop. A countertrend trade with a
high `adx_at_entry` is a red flag — that combination is what surfaced the sweep's
missing trend filter.

##### `regime_conviction` — float, nominally 0.0–1.0
The Layer-1 regime conviction at entry — the confluence engine's own confidence in
the regime label it assigned. Added 2026-07-24 (commit `0421f37`).

**Why it exists:** conviction drives strike selection (sweep delta scaling) and
position sizing, but was never recorded, so there was no way to check whether
high-conviction trades actually outperformed. It is captured **for the sole purpose
of evaluating the conviction scores themselves.**

**KNOWN ISSUES as of 2026-07-28 (first full day of collection, n=23):**
- **Compressed ceiling.** Observed range was `0.000 – 0.582`. Nothing approached
  the top of the nominal 0–1 scale. Any consumer treating 0.8+ as "high
  conviction" is reading a scale that never gets there.
- **Quantized, not continuous.** Five trades landed on exactly `0.438` (AVGO,
  NFLX, PLTR, QQQ, TSLA — all ORB) and four on exactly `0.000`. Nine of 23 sat on
  two discrete values. That is the signature of a score driven by a few
  boolean-ish inputs rather than accumulating evidence.
- **No relationship to outcome yet.** correlation(conviction, pnl) = **0.104**,
  n=23. The four highest-conviction trades went 0/4, −$740; the mid band
  (0.40–0.50) went 6/11, +$787. **Confounded** — the high band was dominated by
  condors, which had a separate strike-placement bug that day. Do not read this as
  "conviction is inverted"; read it as "not yet measurable."
- The confluence excavation (`92c89d7`, `regime_confluence` v1.3) landed
  2026-07-28. **Comparing the conviction distribution before/after that commit is
  a clean test of whether the rebuild widened the scale.**

##### `flat_angle_deg` — float, degrees
The directional-drift angle of the regime window at entry. Added 2026-07-24
(commit `0421f37`). Low = flat/ranging tape, higher = directional drift.

**Status:** as a *day-level* discriminator this was tested and
**CONFIRMED-NEGATIVE** — it does not separate good sweep days from washouts (see
OBSERVATIONS, 2026-07-24 entry). Retained as per-trade context; do not build a
gate on it without new evidence.

##### `exit_submit_ts` / `exit_fill_ts` / `exit_latency_ms` / `exit_ladder_steps` / `exit_escalated` / `exit_mark_at_trigger` — the exit ladder, measured
Added 2026-08-04, N.5 (`exit_engine` v4.11, `trade_logger` v3.11). Written at
`place_exit_order()` — the one seam every close routes through in both modes — on
a **confirmed close only**.

**Why it exists.** TC.2 has to place the directional stop trigger (−40% today, vs
35% or 25%) "calibrated against measured ladder fill-latency" rather than guessed.
That calibration reads these columns and nothing else.

**`exit_mark_at_trigger` is the measurement.** Milliseconds are not a cost until
they are priced; the cost of the ladder is (mark when the exit fired) − (price it
actually filled at). In PAPER the two are equal by construction — paper books the
mark — and that equality is the **plumbing proof** that the capture is wired, not
a result. The real distribution exists only in live.

**`exit_submit_ts` is the FIRST submit of the close attempt, not of the pass.** A
live close is multi-tick: the deadline expires, the order is cancelled or left
working, and the next tick RESUMES the same broker order. State therefore lives on
the record, so `exit_ladder_steps` spans the whole sequence. An engine-level
counter would reset on restart and undercount exactly the slow closes this exists
to find.

**`exit_escalated`** = the close needed more than a plain limit-at-mark post.
Two disjoint causes, either sufficient: the 15:45 hard-close market cross, or the
live loop hitting its deadline and cancelling.

**What "good" looks like:** in paper, `exit_latency_ms` ≈ the ladder cadence,
`exit_ladder_steps` mostly 1, `exit_escalated` 0 outside the 15:45 window, and
`exit_mark_at_trigger` == `exit_premium`. Any paper row where those last two
differ is a defect in the capture, not a market observation.

**NULL means no confirmed close** — never captured, never zero. An unconfirmed
pass writes nothing deliberately: booking one would put the fast final leg of
every slow close into the population the trigger decision is measured on, which
biases the answer instead of leaving a hole.

##### `entry_snapshot` — TEXT (JSON), NULL when not captured
The FVG zones, the frame the trail would anchor to, the live StructureMap levels
and the per-timeframe bar depth — all **as held at the instant of the fill**.
Added 2026-08-04 (`analysis/entry_snapshot.py` v1.0, `trade_logger` v3.10,
`main.py` v5.1). Written on every confirmed entry: directional, butterfly, and
both condor legs.

**Why it exists.** The TC.2 exit bake-off compares break-of-structure, the trail
and the 5-minute FVG exit **counterfactually on identical entries** — the only
comparison that measures exit quality rather than entry luck. Two of those three
rules need to know which gaps existed when the trade opened.

**What is deliberately NOT in it, and this corrects a natural assumption.**
Break-of-structure levels are absent on purpose. `BOSTracker` seeds from entry
price and direction (both already columns) and ratchets forward on closed 1-minute
candles, so a BoS counterfactual is a pure function of the post-entry tape and
needs no capture. Storing it would be storage for nothing.

**Why the rest genuinely cannot be reconstructed later:**
- The trail anchors on the frame `_fvg_frame()` picks, and the live 5m frame is
  **continuous across sessions** while the banked tape is session-scoped RTH. A
  gap formed across the overnight boundary exists live and *cannot* exist in an
  offline resample — the same divergence class as defect S's 1m contamination.
- Frame **depth** is provenance: AK showed three of four timeframes had never
  voted, and a vote cast on a starved frame is not the vote a warm frame casts.
  Depth is gone the moment the tick ends.

**Fields:** `v` schema version · `at` capture time (UTC ISO, same base as
`entry_time` — never ET) · `px` underlying · `dir` long/short/neutral · `frame`
5m or 1m · `anchor` the in-favor zone the trail would use · `fvg` up to 12
most-recent zones on that frame · `swing` seq/res/sup/hi/lo · `depth` bars per
timeframe · `err` present only on a failed capture.

**What "good" looks like:** non-NULL on every row entered after the deploy.
`anchor: null` is a **real observation** — the trail had no in-favor gap and fell
back to the percentage leash — and must never be read as a missing value. A
condor leg is `dir: neutral` and always has a null anchor by definition: there is
no in-favor side. NULL in the column means *not captured*, which is why the
column has no DEFAULT and no empty-string sentinel.

**Known issue to watch on the first sessions:** capture failures are logged once
per reason per process (`entry_snapshot NOT captured`), not once per fill — so
one line in `bot.log` can stand for a whole session of misses. Read the line, not
the count.

##### `swept_level_name` — string, `level_strength` — float 0.0–1.0
For sweep trades: which liquidity level was swept, and its quality. Added
2026-07-24 (commit `934f9d4`).

`level_strength` scale: equal-H/L (unnamed) ≈ 0.2; named PDH/PDL/session 0.6–1.0
scaled by touch count.

**Why it exists:** to test the live hypothesis that **sweep outcome is driven by
the quality of the pool it targeted**, not by the entry logic or the tape. This is
the surviving lead after the tape/regime fingerprint was ruled out.

**Note:** stamped by the sweep path only. ORB trades leave these empty/0.0 — that
is expected, not a bug.

---

##### Querying it

Per box, straight from the trade DB:

```
cd ~/options-trader && sqlite3 -header -column trades.db \
  "SELECT symbol,strategy,adx_at_entry,regime_conviction,pnl_usd,exit_reason
   FROM trades WHERE date(entry_time)=date('now') ORDER BY regime_conviction DESC;"
```

Fleet-wide, from the conductor's consolidated CSV on the control box:

```
cd ~/day_trader_pro && python3 -c "
import csv,sys
r=[t for t in csv.DictReader(open(sys.argv[1])) if t['entry_time'].startswith(sys.argv[2])]
f=lambda x: float(x) if x not in ('','None') else 0.0
for t in sorted(r,key=lambda x:-f(x['regime_conviction'])):
    print(f\"{t['symbol']:6}{t['strategy'][:20]:21}conv={f(t['regime_conviction']):.3f} \"
          f\"adx={f(t['adx_at_entry']):5.1f} pnl={f(t['pnl_usd']):>9.2f}  {t['exit_reason'][:30]}\")
" fleet_trades_2026-07-28.csv 2026-07-28
```

Distribution check (the thing that exposed the compressed ceiling):

```
cd ~/day_trader_pro && python3 -c "
import csv,sys
from collections import Counter
r=[t for t in csv.DictReader(open(sys.argv[1]))]
f=lambda x: float(x) if x not in ('','None') else 0.0
c=Counter(round(f(t['regime_conviction']),3) for t in r)
for v,n in sorted(c.items()): print(f'{v:.3f}: {n}')
" fleet_trades_2026-07-28.csv
```

---

##### Adding a new observability field

The pattern these followed, so the next one is not a dig to find:

1. Add the column to the `trades` table schema **with auto-migration** (existing
   DBs must not break).
2. Wire it through every entry path that creates a trade record — strategies,
   `entry_engine`, and the condor leg builder. Missing one path produces silent
   zeros in a subset of trades.
3. Add it to the consolidation so the EOD conductor carries it into
   `fleet_trades_<date>.json/.csv`.
4. **Document it here**, with: what it is, why it exists, what "good" looks like,
   and any known issues found in the first days of collection.

Step 4 is the one that got skipped for the 2026-07-24 batch — the fields were
live and collecting for four days before anyone could say what they were without
reading commits.

---


<!-- ================= was: docs/README_orb_regime_ungate_v3_2.md ================= -->

##### ORB Regime Un-Gate — v3.2 (2026-07-11)

##### Scope

Lets the flagship **5-minute ORB break-and-retest fire regardless of the regime
label** — including `UNKNOWN` and `SWEEP_REVERSAL` — behind a single config
switch. The ORB engine's break+retest is self-validating; the classifier does
not even test for it, so the label is not consulted for the go/no-go decision.

This pass sits **on top of the v3.1 stop rework** (`orb_engine` + `exit_engine`).
Deploy them together — the four files below are the complete, consistent set.

Files:

- `config.py` — new switch `ORB_FIRES_REGARDLESS_OF_REGIME` (default `True`)
- `main.py` (v3.2) — dispatch un-gate
- `analysis/orb_engine.py` (v3.2) — stop rework (v3.1) **+** sweep-deferral guard
- `execution/exit_engine.py` (v3.1) — structure stop (from the stop-fix pass, unchanged)

**Not included (still queued):** the ORB-target-path conviction haircut and the
proximity-graded sweep demotion. Those touch scoring, not gating, and are a
separate pass.

---

##### Why this exists

The ORB is the highest-quality, fully mechanical setup in the book, and v2 was
blocking it: during the opening-range window the classifier frequently returns
`UNKNOWN` (a single 5m frame early in the session rarely resolves to a named
regime), and `UNKNOWN` was a hard no-trade. So the best setup was being gated by
a label that says nothing about whether the setup is present.

The fix is one rule: **a confirmed ORB fires regardless of the label.** The
break+retest is the edge; the regime dimension becomes a *scoring input*, not a
veto.

---

##### What changed

##### `config.py`

```python
ORB_FIRES_REGARDLESS_OF_REGIME = True   # set False to restore strict v2 gating
```

##### `main.py` (v3.2) — `run_entry_logic`

Two edits, both switch-gated:

1. **Hard UNKNOWN gate bypassed for a confirmed ORB.** The `UNKNOWN`/undefined
   no-trade gate no longer vetoes when the engine is in a confirmed `OPEN_LONG`/
   `OPEN_SHORT` state. A genuinely unclassified tape with *no* ORB setup still
   blocks (only a proven setup bypasses).
2. **ORB dispatch admits `UNKNOWN` and `SWEEP_REVERSAL`.** A confirmed ORB now
   dispatches under those labels too (previously only TRENDING/BREAKOUT/RANGING/
   COMPRESSION).

##### `analysis/orb_engine.py` (v3.2)

The retest confirm previously **deferred** (left the setup awaiting retest)
whenever the regime was `SWEEP_REVERSAL`, so a sweep label suppressed a valid
ORB. Now guarded by the switch: with it on, the engine confirms OPEN under a
sweep label so the dispatch can fire it — **ORB beats sweep.** (The v3.1 stop
logic is unchanged.)

---

##### Expected behavior (verified truth table)

| regime label | ORB engine confirmed? | switch | outcome |
|---|---|---|---|
| UNKNOWN | yes | **on** | **ORB fires** |
| UNKNOWN | yes | off | blocked (v2 behavior) |
| UNKNOWN | no | on | blocked (no setup to bypass) |
| SWEEP_REVERSAL | yes | **on** | **ORB fires (beats sweep)** |
| SWEEP_REVERSAL | yes | off | falls to sweep strategy (v2 behavior) |
| RANGING / COMPRESSION / TRENDING / BREAKOUT | yes | either | ORB fires (unchanged) |
| None / undefined | — | on | blocked (no crash) |

What does **not** change:

- **The setup scorer still governs.** A confirmed ORB under `UNKNOWN` still has to
  clear the B threshold. `regime_conviction` simply contributes 0 (its 0.20
  weight), so only ORBs that earn a B on break quality + VWAP + liquidity + macro
  fire; marginal ones are still refused. The scorer *is* the consensus filter.
- **Exits are unchanged.** v3.1 structure stop (close beyond the impulsive origin)
  + the unconditional −25% premium floor. The un-gate changes entry, not exit.
- **Sweep / butterfly / condor are untouched.** They self-gate on their own regime
  values and do not fire under `UNKNOWN`. This pass only frees the ORB.

---

##### Interaction with the shadow observer

Every ORB that fires under `UNKNOWN` is logged with `regime=UNKNOWN` on the trade
record. That is precisely the labeled tape the shadow subsystem exists to
capture: it can now record the Layer-1 confluence scores (`regime_confluence`)
and raw factors at the moment an `UNKNOWN`-labeled ORB fires and resolves, which
is the corpus the v3 conviction integrator needs to be calibrated against. In
other words, un-gating the ORB is also what starts *feeding* the shadow program
the exact population v2 was starving it of.

---

##### What this does and does not establish

- **Verified:** the gate logic (all 9 regime/state/switch combinations), the
  engine confirming OPEN under a sweep label, syntax and imports across all four
  files. The un-gate does what it says and is fully reversible via the switch.
- **Not established here:** that the newly-fired ORBs are net-profitable. That is
  a **paper-forward** question — option-premium P&L can't be reconstructed from
  underlying OHLC. The posture is deliberate: these are lower-information trades
  (the tape was `UNKNOWN`), taken to generate labeled data, with the scorer's
  B-threshold and the v3.1 stops containing the downside. Expect a lower hit rate
  than regime-confirmed ORBs; that's the point.
- **Reminder on single-day tape:** the classifier is starved on one session, so
  the exact "how often was the ORB window `UNKNOWN`" rate is only reliable live —
  which the shadow program will now measure directly.

---

##### Deploy

All four files are one consistent set (v3.1 stops + v3.2 un-gate). Ship together:

```
scp config.py   <box>:<repo>/config.py ;
scp main.py     <box>:<repo>/main.py ;
scp orb_engine.py  <box>:<repo>/analysis/orb_engine.py ;
scp exit_engine.py <box>:<repo>/execution/exit_engine.py ;
```

No new dependencies, no schema changes. To roll back the un-gate alone, set
`ORB_FIRES_REGARDLESS_OF_REGIME = False` (restores strict v2 gating; the v3.1 stop
rework stays in force). Restart the bot service to load the changes; confirm
`PAPER_TRADING` is set as intended before the first session.

---


<!-- ================= was: docs/README_orb_stop_rework_v3_1.md ================= -->

##### ORB Stop-Placement Rework — v3.1 (2026-07-11)

##### Scope

The 5-minute opening-range break-and-retest stop was being placed and enforced
against the wrong price levels. This change corrects **where the stop level is
set** (the engine) and **how it is enforced** (the exit path). Two files change,
both bumped to **v3.1**:

- `analysis/orb_engine.py`
- `execution/exit_engine.py`

No other strategy (sweep, butterfly, condor) is touched. **The regime un-gate
(letting a confirmed ORB fire under an UNKNOWN/sweep label) is NOT part of this
change set** — it remains queued separately.

---

##### Root cause

Two distinct defects, both in the ORB stop, discovered by driving the real
engine over candle-logger tape:

1. **Stop LEVEL was anchored to the impulsive candle's body, not its wick.**
   The engine set the stop to `min(open, close)` (long) / `max(open, close)`
   (short) of the break candle. When that candle opened *outside* the range, its
   body edge sat outside the level — so the retest entry (which returns to the
   level) printed a stop on the *wrong side* of the entry. Result: inverted /
   near-zero risk on a meaningful share of trades.

2. **The exit's structure stop fired at the range boundary, not the impulsive
   origin.** `_evaluate_orb` exited on any 1-minute close back inside the ORB
   range (`close < orb_high` for a long). By the strategy's definition that is
   *not* an invalidation — the trade is allowed to breathe inside the range as
   long as it holds the impulsive candle's origin. Stopping at the range edge
   cut trades that were still structurally valid.

A separate, important finding from the same dissection: the corrected
`underlying_stop` is **not** the live executor. Live exits govern off the **−25%
premium floor** (`current_premium <= stop_premium`); the underlying level is a
structure check that runs *beside* it. Both are intentional and both are kept —
see "The stop model now."

---

##### What changed

##### `analysis/orb_engine.py` (v3.1) — `_check_for_break`

1. **Stop anchors to the impulsive candle's wick**: its `low` for a long, its
   `high` for a short (was the body `min/max(open, close)`). The wick is the true
   origin of the breakout move and sits inside the range where invalidation lives.

2. **A valid impulsive candle must originate inside the range**: `low < orb_high`
   for a long, `high > orb_low` for a short. A candle sitting entirely beyond the
   range is late continuation, not an ORB break; taking its "retest" was the
   source of the remaining inverted stops (fast/gap breaks and re-arms while
   price was already extended). Gating on origin removes them, and — because the
   engine now waits for the valid break instead of firing on the extended one —
   it did not cost setups.

##### `execution/exit_engine.py` (v3.1) — `_evaluate_orb`

- The structure stop now keys off `underlying_stop` (the impulsive origin set by
  the engine) instead of `orb_range_high` / `orb_range_low`. A long exits on a
  1-minute close **below the impulsive low**, a short on a close **above the
  impulsive high**. A close back inside the range that still holds the origin now
  **keeps** the trade.
- It remains close-based on the last *closed* candle (`iloc[-2]`), so an intrabar
  wick into the range survives; only a confirmed close beyond the origin exits.
- The **unconditional −25% premium floor (v1.6) is unchanged** and still evaluated
  first, every tick.

---

##### The stop model now (the "AND")

Two independent exits protect an ORB position. Whichever trips first closes it —
they are an **AND** (both always armed), not a choice:

| Exit | Level | Fires when | Catches |
|---|---|---|---|
| **Structure stop** | impulsive candle origin (low/high) | 1-min *close* beyond it | thesis is dead, regardless of premium |
| **−25% premium floor** | 75% of entry premium | premium ≤ floor | dollars gone past tolerance — theta, retracement, or the two combined — regardless of structure |

Neither is redundant: a slow bleed or a shallow-but-costly retracement can hit
−25% without ever closing beyond the origin, and a sharp close beyond the origin
can invalidate the thesis while the premium is still above −25%.

---

##### Smoke test

**Tape:** candle-logger 1-minute OHLC for 2026-07-09 (15 symbols) and 2026-07-10
(29 symbols) — 44 symbol-sessions. **Method:** the *real* `ORBEngine` is driven
bar-by-bar with the clock and opening range injected (no reimplementation), then
each confirmed entry's stop geometry is measured; the *real* `_evaluate_orb` is
run against the MU reference sequence.

##### Expected

- Every confirmed entry carries a stop below entry (long) / above entry (short).
- The MU 2026-07-10 setup reproduces the manual read: impulsive candle 09:49,
  retest 09:50, stop at the impulsive low, 09:54 survives, 09:55 stops.
- The exit's structure stop gives room inside the range that the old
  range-boundary rule did not.

##### Realized

| Metric | Before (body stop, range-boundary exit) | After (v3.1) |
|---|---|---|
| Inverted / degenerate-risk entries | **26 / 92 (28%)** | **0 / 96 (0%)** |
| Median entry risk (% of price) | 0.089% (collapsed onto entry) | **0.201%** (sane distance) |
| Confirmed ORB entries | 92 | 96 (fix did not cost setups) |

- **MU reference, through the real exit method:**
  ORB range 971.50 / 958.08; impulsive candle **09:49** (O 971.35, H 975.49,
  **L 971.14**, C 973.83); retest **09:50** doji (L 971.00 wicks in, C 973.99
  closes out) → fires, entry 973.83, **stop = 971.14**.
  `09:54` close 972.15 → **holds**. `09:55` close 970.88 → **exits**:
  `orb_structure_stop: 1m close 970.88 below impulsive-candle low 971.14`. Exact
  match to the manual walkthrough.
- **Extra room from the exit change:** across the entries where the two rules
  differed, the impulsive-origin stop held the trade a **median of +3 bars**
  longer than the old range-boundary stop (~1/3 of entries), i.e. it survived a
  range re-entry the old rule would have cut. The −25% floor still independently
  caps dollar loss on those.

---

##### What this does and does not establish

- **Verified:** stop *geometry* (level) and exit *trigger* (level + close-based).
  Every ORB entry in the run now has a correctly-placed, non-inverted stop, and
  the exit fires on the origin, not the range edge.
- **Not established here:** option-premium P&L / win-rate. The bot's real
  outcomes ride on option premium (a 25% premium stop and premium target), which
  cannot be reconstructed from underlying OHLC without the option chain. Whether
  these setups are net-profitable is a **paper-forward** question, not a
  backtest-from-tape one.
- **Data limits:** two single-day sessions; the regime classifier is starved on
  single-day tape and is unaffected by this change regardless.

---

##### Deploy

Both files ship together (they are a matched pair — the engine sets the level the
exit reads).

```
scp orb_engine.py  <box>:<repo>/analysis/orb_engine.py ;
scp exit_engine.py <box>:<repo>/execution/exit_engine.py ;
```

No `config.py` changes, no new dependencies, no schema changes. `underlying_stop`
is already carried on the trade record (written by `entry_engine`), so no
migration is required. Restart the bot service to load v3.1.

---



---

## APPENDIX — migrated from the root README (2026-07-28)

<!-- ================= was: README.md § Trade readiness engine ================= -->

## Trade readiness (v4.4 / engine v1.1, 2026-07-27 — LOG-ONLY, gates nothing)

**v1.1 staged picks:** while ARMED, continuation/sweep journal the contract they
WOULD select — via the live `select_sweep_strike` selector on a SMOOTHED
conviction (wall-clock EMA, `OT_TR_CONV_HALFLIFE_S=90`) instead of the
instantaneous spike — as `readiness_staged_pick` rows. When the real trigger
fires, the journal holds calm-pick vs spike-pick side by side and the chain
archive prices the difference. **Nightly automation (zero manual steps):**
dtp `harvest` v0.5.0 pulls each box's `data/signal_journal/<date>/<SYM>.jsonl`
into the control journal root (lighting up conductor phase 8's journal tables —
the 07-18 deferral closed), and conductor v1.6.0 **phase 9 READINESS** runs
`tests/readiness_digest.py --quiet` (states, R distribution, would-fire counts,
arm episodes, staged-pick stats, anticipation lead-times) into
`reports/readiness_digest_<date>.{txt,jsonl}` with a 🧭 Telegram headline.
Safe to deploy ahead of the fleet: an empty journal prints an honest headline
and returns 0.

**v1.2 (2026-07-28) — every factor bound is now `OT_TR_*` overridable**, parity
with L1's `OT_RC_*`. v1.0/v1.1 env-ified only the state-machine bars and left
the factor ramps hardcoded; day one showed the cost when the conviction ramp
(top 0.65) pegged against live L2 conviction of 0.59–0.83 and ten symbols
reported an identical `r=0.65`. Correcting a bound is now an env flip trialled
on one box, not a fleet bake. **Defaults are deliberately unchanged** — the raw
inputs (`conv`, `dist_atr`, `approach`, `age_bars`) are journaled un-ramped, and
`readiness_digest` **v1.1** fits the bounds from their observed percentiles and
prints the exact `export OT_TR_..._LO=/_HI=` line, flagging any ramped factor
pegged on >60% of ticks. Fitted, not guessed — the room_s convention.

`analysis/trade_readiness.py` v1.0 + the `main.py` v4.3 every-tick hook. Each
strategy's pre-trigger confluence is a graded readiness **R ∈ [0,1]** (same
three-tier `_combine` grammar as L1, living at strategy level where tradability
context is legal), with a **dt-aware slope** (R/minute, wall-clock EMA — no
per-evaluate counters) and a **DORMANT → STAGING → ARMED** machine that
journals transitions, 60s heartbeats while active, and `readiness_would_fire`
moments. The last gate stays binary — the point is that the bit is the LAST
place information collapses: level AND slope AND state, so a wick-flicker
(same level, collapsing slope) de-arms instead of firing. Strategies covered:
continuation, sweep, condor call/put sides (the approach fraction the condor
trigger computes and then collapses at 0.65 is kept graded here), butterfly.
ORB exempt (mechanical by directive). Knobs `OT_TR_*` (stage 0.35 / arm 0.55 /
fire 0.70 / de-arm slope −0.15/min), all PRIOR — calibrate from the readiness
journal. Log-only per the pitchfork weight-0 precedent, so it rides inside the
frozen-baseline window; it does not validate L1, it records what L1 believes,
per strategy, per tick. Restart resets the in-memory tracks (journals as a
DORMANT reset — itself evidence).

`regime_confluence.py` **v1.3.1 (2026-07-27)**: adds the COMPRESSION containment hard
veto (close beyond the band edge zeroes the coil) — an A3 squeeze-break collision the
A/B pool surfaced on XOM 07-22, latent since v1.0 but only exposed once BREAKOUT could
accumulate. See `docs/REGIME_TRUTHS.md` v0.4.

`regime_confluence.py` **v1.3 (2026-07-27, CONFLUENCE EXCAVATION)**: four of the five
scorers were Boolean gates wearing confluence clothing — `_breakout` and `_sweep` passed
an EMPTY corroborator list (so `_combine` defaulted their sum term to 1.0 and nothing
accumulated), while `_ranging` and `_compression` each carried a constant-1.0
corroborator worth 40% / 30% of their "confluence". All four rebuilt so evidence
actually accumulates; `_trending` was already real and is untouched; ORB is not scored
here at all. `_sweep` now RECEIVES `trend_state` — it previously could not see trend,
which on 2026-07-27 let a lone level-rejection score 0.62 and short PLTR into a +7.2%
uptrend for −27.8%. The `OSC_CROSS_*` crossings axis is now decoupled per scorer.
Weights are **design-derived, not tape-fitted** (each block states the minimum evidence
set that should just barely score); pool calibration is the next pass, so treat the
current weights as honest priors. See `docs/REGIME_TRUTHS.md` v0.3 for the role table.
Paired with `config.py` **v4.0** (`SWEEP_DELTA_STRONG` 0.08 → 0.12 — the same PLTR trade
also bought a strike gamma could not reach; deliberately a SEPARATE commit so post-freeze
sweep P&L stays attributable between entry quality and strike selection).

`regime_confluence.py` **v1.2 (2026-07-22, ramp de-saturation)**: all 14 ramp bounds
env-overridable (`OT_RC_<NAME>`); `room_s`/`osc_s` re-fitted from 60,341 ticks over 6 sessions
and promoted to defaults (RANGE_ROOM 0.05–0.20 → 0.17–1.00, OSC_CROSS 2–5 → 4–10). RANGING was
saturating (p90=1.0) and colliding with TRENDING on 14–25% of ticks; now 4.3% (the residual is
genuine cross-horizon co-occurrence, not saturation — see ROADMAP L1.10).

`regime_classifier.py` **v1.3 still runs** alongside (memoryless boolean cascade, first-match-
wins: SWEEP_REVERSAL → BREAKOUT_VOLATILE → COMPRESSION → TRENDING_BULL/BEAR → RANGING →
UNKNOWN) and populates RegimeState's rich fields; it is the rollback engine. ADX comes from the
**5-minute** timeframe. The `UNKNOWN` hard gate below only matters under rollback — the live L2
label cannot emit it.

| Regime | Strategies permitted to fire |
|---|---|
| TRENDING_BULL / TRENDING_BEAR | **ORB · Trend Continuation** |
| BREAKOUT_VOLATILE | **ORB** |
| SWEEP_REVERSAL | Sweep Reversal · **ORB (v3.2 — ORB wins)** |
| RANGING | Iron Condor · Butterfly (if GEX PINNING) · **ORB** |
| COMPRESSION | Butterfly (if GEX PINNING) · **ORB** |
| UNKNOWN | **ORB only** (v3.2 un-gate). Everything else: no trade. |

The ORB appears in every row because the break+retest is **self-validating** — the classifier
does not even test for it, so the label is a scoring input, not a veto.

---

---

<!-- ================= was: README.md § The ORB — the flagship, and it is now definitional ================= -->

## The ORB — the flagship, and it is now definitional

The setup is mechanical. As of **v3.5 there are no tolerances anywhere in it.**

```
BREAK  = a 1m candle that OPENS INSIDE the opening range and CLOSES OUTSIDE it.
RETEST = a SUBSEQUENT 1m candle — any bar within ORB_MAX_RETEST_BARS (12) of the
         break, NOT only the very next one — whose WICK enters the range and
         whose BODY stays entirely OUTSIDE it. Bars in between that neither
         retest, close back inside, nor reach the 50% TP simply pass; the
         engine stays ARMED and keeps waiting.
STOP   = a 1m CLOSE beyond the impulsive (break) candle's WICK.
```

**Opening range** = the 9:30–9:35 ET 5-minute candle, sourced through the bot's own data
layer (`market_data.fetch_candles`) so it always agrees with the tape the bot trades. Written
to `orb_range.json` as a three-state model — `ESTABLISHED` / `IN_PROGRESS` / `EXPIRED` — and
the engine **arms only on `ESTABLISHED`/today**, so a carried prior-day range can never be
traded.

**State machine** (`ORBState`, renamed in v3.4 to the operator's vocabulary):

```
NO_RANGE → WAITING_FOR_BREAK → ARMED_LONG / ARMED_SHORT → OPEN_LONG / OPEN_SHORT
                  ↑                       ↓
                  └───── INVALIDATED ─────┘        (re-arm rules below)
```

**ARMED means a break has occurred and the next event is FIRE or INVALIDATE.** Before a break
there is nothing armed — the engine is merely waiting.

**Why "opens inside" is definitional (v3.5).** It is an *opening-range* break. A candle that
began life outside the range never broke out of it — it was already out. That is late
continuation. (v3.1 approximated origin as `low < orb_high` — the wick merely reaching back in
— which still admitted candles that opened *above* the range, dipped, and closed higher.)

**Why there is no buffer (v3.5).** The retest **is** the noise filter — a marginal break that
means nothing simply fails its retest. The old `ORB_BREAK_BUFFER` (0.05% *of price*) required
the close to clear the range by **$0.49 on MU, ~$3.00 on SPX**, so price could close three
full points beyond the opening range and not register a break.

**Why there is no grace band (v3.3).** The retest is the **falsification step** of the break
hypothesis ("this level is now support"). A level that was not tested produced *no evidence*;
a level whose retest closed back inside was tested and **failed**. Neither is a graded setup.
The old `body_low >= orb_high * 0.999` admitted a candle whose body **closed back inside the
range** — the disarm condition — as a *confirmed retest*, and bought it. On SPX that window
was ~6 points deep.

**Three invalidations:**

| Reason | Trigger | Re-arms? |
|---|---|---|
| `close_inside` | 1m close back inside the range — the hypothesis failed | ✅ **Yes**, if before 11:00. The second attempt is often the cleaner one; the first is often the fake-out. |
| `runaway` | Ran to the 50% TP with **no retest** | ❌ No. Hands off to Sweep Reversal — the setup a failed runaway most favors. |
| `timeout` | 12 bars without a retest (`ORB_MAX_RETEST_BARS`) | ❌ No. The setup has gone stale. |

**Break latches** (`broke_high`/`broke_low`) are maintained **unconditionally every tick, in
every state**. They are a session-level fact ("a 1m candle closed beyond this boundary"),
independent of the ORB entry state machine, because the sweep gate needs them even while the
ORB is dormant. They are **close-based** (a wick that pokes and closes back inside does not
arm a sweep) and take **no origin gate** — they record a fact, not a setup.

**Entry:** single-leg long call/put, strike near the ORB-projected 100% target.
**Hard cutoff 11:00 ET** — the engine EXPIRES from any state. This expires the *engine*, not
an open position: a fill at 10:58 runs to its own exits.

---

---


---

## APPENDIX — strategy & exit detail migrated from the root README (2026-07-28)

> **STALE WARNING:** the Iron Condor subsection below describes the
> pre-2026-07-28 model (Bollinger-anchored strike selection; sequential
> `DECIDED → LEG1_FILLED → COMPLETE` legging). Both were replaced on
> 2026-07-28 — see the *Iron Condor (current)* note that follows it.

<!-- ================= was: README.md § Strategies ================= -->

## Strategies

##### Sweep Reversal
Detects liquidity sweeps at **mapped** zones (PDH/PDL, equal highs/lows, session H/L). A sweep
requires all three: **location** (at a named pool), **penetration**, and **rejection**
(reclaimed and held). Acceptance *through* a level is a breakout, not a sweep. OTM strikes by
delta targeting, scaled inversely to reversal strength (strong snap → far-OTM; weak →
near-ATM). **BOS exit** on the 1m chart — closes only, no wicks.

##### TERMINOLOGY — the two trend trades are DIFFERENT TRADES (fixed 2026-08-14)

These names were used loosely and it caused real confusion. They are now fixed:

- **TREND CONTINUATION** is the **LONG (DEBIT)** contract placed on an **ORB
  runaway handoff**. Directional, buys premium, and is **BLOCKED AFTER 11:00 ET**
  by AFD.1 along with every other debit directional.
- **TREND PARTICIPATION** is a **CREDIT SPREAD bounded by the ORB RANGE** — the
  ORB HIGH for a long, the ORB LOW for a short — **invalidated by a close
  through that level**, and **otherwise unrelated to the other trades.** It sells
  premium, runs 11:00–14:00, and nothing closes it before the session hard close
  except a breach.

⚠️ **THE RUNAWAY IS SLOT ARBITRATION, NOT A SHARED PREMISE.** ORB owns
09:35–11:00. A runaway is the one condition that definitively frees that slot
(ORB is INVALIDATED and never re-arms), which is why continuation-handoff and
sweep-reversal may take it. **After 11:00 ORB owns nothing**, so trend
participation requires no runaway and asks no permission — it uses the ORB
range only as a PRICE LEVEL, recomputed from the 09:30–09:35 bars, never from
the ORB engine's state.

The two trades share a name fragment and nothing else: opposite premium
direction, different windows, different anchors, different invalidation.

##### Trend Continuation (NEW 2026-07-18 — paper-first, the trend-native trade)
The trade the `trend_engine v3.1` fix exists to enable. Fires **only in a trending regime** —
and because the classifier is *stingy* about calling trend (it is a high bar to clear), a
trending label is itself the high-conviction signal. Debit directional (long call in
`TRENDING_BULL`, long put in `TRENDING_BEAR`).

**Philosophy: make entry easy, make exit smart.** Entry is a deliberately *low* bar — the
protection lives in the exit, not the entry. Price pulls back to the **BB midline**
(`bb_middle`, the same anchor the condor uses), momentum flips back toward the trend, and it
enters. Two entry paths, both trend-gated:

- **Handoff (looser).** A **runaway ORB** — a break that ran to the 50% TP with no retest —
  is one of the *strongest* trend confirmations there is (strong push → pullback → next leg is
  textbook trend behaviour). So when a runaway ORB invalidates in a trending regime, it now
  **hands off to continuation first** (`main.py` Priority 2.5, `is_handoff=True`): conviction
  floor relaxed 0.45→0.35, `STEADY` momentum accepted. This replaces the old hardcoded
  runaway→sweep chain. Sweep still owns a runaway heading into a near/strong mapped zone when
  *not* trending.
- **Standalone (stricter).** No runaway vouching for it, so it must self-source the setup:
  conviction ≥ 0.45 and `ACCELERATING` momentum required.

**Downside = regime-change OR 40%, whichever first.** Regime-invalidation *is* the smart
stop — the trade is *defined* by the trend, so a flip out of trending kills the thesis
regardless of P&L (this mirrors how the condor self-gates on RANGING). The 40% floor is the
disaster backstop beneath it. No separate structural stop.

All thresholds env-tunable (`OT_CONT_*`). The `MIDLINE_ATR` band (how close to the midline
counts as "at" it, default 0.35·ATR) is the primary knob — it controls how *often* the trade
fires — and is the first thing to calibrate off the paper baseline.

##### Iron Condor (legged, tracked)
RANGING fallback when no GEX pin is available. **Strike SELECTION is Bollinger-Band anchored —
no delta enters the strike-picking path.** Short call = lowest liquid strike at/above the BB
upper band; short put = highest at/below the BB lower band. Delta is deliberately excluded
*from selection*: it is relative to where price *sits*, not to the actual range boundary.

**Delta as a calibration street-sign (v3.4).** Distinct from selection: after the BB selector
has picked the short strike, the leg **records `abs(short-strike delta)` as its `setup_score`** —
read-only, purely as a logged waypoint. It does not influence which strike is chosen, how the
leg is sized, or whether it fires; it is written *after* the pick is final. Condor legs
otherwise carry no conviction score (they hardcode Grade B), so this is the axis condor
threshold-calibration will bin fee-adjusted ROI against later. `NULL` when the Greeks feed did
not populate delta — a real short strike is never exactly 0.0 delta, so a stored value is
always a genuine delta. This is the *only* delta anywhere near the condor, and it decides
nothing.

The condor is **the only strategy allowed two concurrent positions** (its two verticals). Each
vertical is a fully tracked position — managed, exited, and P&L'd independently with
credit-spread math — and each is sized at the **full grade budget** (`risk_manager` v3.2, 2026-07-23 — half-budget
retired: 18 of 46 legs never got a second side, so half-sizing chronically under-sized a
structure that never existed). Wings are narrow (5 points SPX / $5 QQQ). Legged entry:
`DECIDED → LEG1_FILLED → COMPLETE`; a pending leg **PAUSES** if the regime flips away from
RANGING (`iron_condor` v3.2, 2026-07-23 — the plan stays alive; leg 2 fires when regime
returns AND price is at the far band); a filled leg is never cancelled. Exit per leg
(`exit_engine` v4.1, 2026-07-23): **ratcheting stop** (+20% → breakeven, +40% → lock +20%,
tightens only), **time-gated TP at 25%** (only after the entry cutoff, only when the sibling
side is not open, min-hold quote-noise gate), or a $0.05 nickel close. Regime-flip exit is **direction-aware** — a call spread only
exits on a bullish flip; a bearish flip is favorable, so it holds.

##### Broken-Wing Roll
When both verticals are open and price tests one side, rolls the **untested** side toward
price — **only if the math makes the tested side risk-free**
(`banked_credit + roll_credit − close_cost ≥ tested_side_width`). Smallest qualifying roll
wins. **One-time and final**: once rolled, every leg is flagged `is_broken_wing` and never
adjusted again. Roll once, stand it, defend it.

##### Debit Butterfly
RANGING or COMPRESSION **with a PINNING GEX environment**. Center strike = the **GEX pin**, not
ATM. Gated on proximity (price within 1× the session expected move of the pin). Fixed wings
(25pt SPX / $5 QQQ). One per session. Exits immediately on a flip to trending.

**GEX is computed live from the TastyTrade chain every 15s. No scraping, no external API.**
Derived: call wall, put wall, pin strike, flip strike, environment. The condor is intentionally
*not* GEX-dependent — it fires precisely when GEX is **not** pinning.

---

**In development** (not firing; see [`docs/ROADMAP.md`](docs/ROADMAP.md)):

- **Trend Credit Spread (TC.4)** — participates in a strong trend that never pulls
  back, by selling premium beneath it (PCS in a bull, CCS in a bear). Readiness
  track is live and log-only; the firing engine is gated on calibration and on the
  Layer-1 excavation.

  **WHAT EXISTS TODAY, precisely — asked directly on 2026-08-04 and worth writing
  down rather than re-deriving.** There is **no `strategy/vertical_spread_strategy.py`**.
  ⚠️ SUPERSEDED 2026-08-14 — `strategy/trend_credit_spread.py` (TrendCreditSpread)
  is now a REAL FIRING STRATEGY, not a readiness track. See the TERMINOLOGY block
  under §Strategies. What follows describes the log-only precursor.

  What runs is the READINESS TRACK, `analysis/trade_readiness._trend_credit_spread()`,
  live on the fleet since 2026-07-28 and log-only; `tests/canary_trend_credit_spread.py`
  exists to prove it is *wired and inert*, not that it trades. It is scored, journaled
  and gates nothing.

  **THE TRADE.** Sell a spread BEYOND the impulse candle, so the trade needs no
  pullback and no chase — which is the point: it is the trade for a trend that
  never gives you an entry. Grading is a hard veto on the directional label, then
  corroborators (impulse magnitude on an SD ramp, conviction, structural room from
  spot to the impulse floor in ATR, momentum-live), a parabolic over-extension
  damper (exhaustion → snapback risk), and the ≥80%-of-arm expected-move extension
  gate it shares with the condor sides.

  **ITS PREMISE, AND HOW IT GETS TESTED.** The strategy rests on one claim:
  *committed order flow will not fully retrace the impulse*. Until 2026-08-04 that
  claim had never been measured. `tests/tcs_floor_durability.py` v1.0 measures it
  offline from data already journaled — for every armed impulse, did a 1-minute
  CLOSE go back through `floor_px` before the bell? It reports durability by SD
  bucket (which IS the fit for `TR_TCS_IMPULSE_SD_LO/HI`), the penetration
  distribution on failures (p90 is a strike distance priced from the state's own
  behaviour), and time-to-failure (a floor broken at 15:55 is a 0DTE out of clock;
  one broken in four minutes is a wrong thesis). See
  [`docs/VALIDATION.md`](VALIDATION.md).

  **WHY THE ENGINE IS NOT BUILT YET, and it is not a schedule excuse.** A held
  floor is a NECESSARY condition for the trade, not a profitable one — and an
  unheld floor means the strategy is wrong and the engine was wasted work. Three
  supporting reasons: the SD bounds are unfitted until TC.4b (Aug 8-9); a new
  firing strategy moves fire-rate, one of the four numbers the Aug 21 freeze
  verdict is written from, so it would break its own baseline; and it changes the
  trade population AV's Aug 13 read and `conditional_tables` are measured on. If
  the floor holds, the build is fast, well-specified, and belongs in the **Aug 24
  paper deploy** — post-freeze, four weeks before full size.

  **WHERE THIS STANDS — 2026-08-04, measured, not asserted.** First real runs of
  `tests/tcs_floor_durability.py` over 2026-07-28 → 08-04:

  | population | impulses | intraday floor held |
  |---|---|---|
  | ARMED (what the strategy would have sold beyond) | 2,812 | **17.9%** |
  | ANY (every floor the rolling lookback computed) | 5,129 | 14.6% |

  **THE PREMISE AS STATED IS NOT SUPPORTED.** Time-to-failure on the ARMED
  population is **p10 1 min, p50 6 min**, p90 68. The tool pre-registered that a
  single-digit p50 means *the thesis was wrong* rather than *the 0DTE ran out of
  clock*, and that is what came back. Half of all violations happen within six
  minutes of the impulse.

  **BUT THE MEASURE DOES NOT MATCH HOW THE TRADE PAYS, and that is the live
  question.** "Was the floor ever violated intraday" is not a defined-risk
  spread's loss condition — **where price sits at the bell is.** A floor breached
  at 10:04 and reclaimed by 15:00 expires fine. v1.2 therefore reports INTRADAY,
  TERMINAL and RECOVERY separately and never merges them, plus a STRIKE CURVE:
  terminal failure rate as a function of distance beyond the floor. The gap
  between the intraday and terminal rates is the answer to *is the premise wrong,
  or is the strike simply too close?*

  **THE SD RAMP MAY NOT BE FITTABLE ON THIS POPULATION — a concrete problem for
  TC.4b's stated method.** ARMED buckets came back `sub-aware n=0`, `aware n=5`,
  `establish n=987`, `screaming n=1820`: **arming already requires magnitude**, so
  there is no low-SD variance left to fit a ramp against. The two populated
  buckets differ 15% vs 19% against an MDE of 4% — sitting on the detection limit,
  so "durability rises with magnitude" is NOT established, only not-refuted. The
  fit has to come from `--machine STAGING+` or it does not come at all.

  **STRIKE DISTANCE, from the same run:** penetration on failures p50 0.862%,
  p90 3.001%, p95 3.756%, max 6.597% of the floor price.

  **DECISION POSTURE:** the engine stays unbuilt. Not on schedule grounds — on
  the grounds that a premise which fails its own pre-registered test does not get
  a firing engine until the terminal measure says whether the failure is the
  thesis or the strike. See BACKLOG **TC.4b-pre**.

  **RE-SCOPED 2026-08-04, operator's decision after the control run: KEEP THE
  TREND LABEL, DELETE THE SCORING.**

  | population | n | intraday held | terminal OK |
  |---|---|---|---|
  | ARMED | 2,812 | 17.9% | **62.6%** |
  | ANY (every floor the lookback computed) | 5,129 | 14.6% | **60.9%** |

  **Arming buys 1.7 points, and at the wider strikes the unarmed control is
  marginally BETTER** (failure at +1.00%: 15.5% armed vs 16.7% control; at
  +2.00%: 6.4% vs 6.2%). Terminal survival is also FLAT across every SD bucket in
  both populations — 59-64% from sub-aware to screaming, every band overlapping.
  Two independent measurements saying the same thing: **`impulse_val` does not
  discriminate on the outcome the trade depends on.** By the operator's own
  three-way split that is CORRECTNESS (category 2) — a contributor not doing the
  job it was designed for — not a tuning question.

  **WHAT IS DELETED:** the readiness gate as TC.4's trigger, and TC.4b's plan to
  fit `TR_TCS_IMPULSE_SD_LO/HI` from a durability curve. There is no curve.
  **WHAT SURVIVES:** the trend label as the condition, and a strike distance
  taken from the measured terminal-survival curve rather than from a delta.
  TC.4 becomes *in a confirmed trend, sell N% beyond a recent extreme* — N from
  the tape, not from a prior.
  **WHAT IS NOT DELETED, and deliberately:** the log-only readiness track keeps
  emitting. It gates nothing, costs nothing, is the ONLY source of the
  impulse-floor record that made this analysis possible, and shares
  `_extension_from_arm` with the condor sides. Removing the emitter would destroy
  the input to every re-examination while changing no behaviour.

  **THE CONTROL THAT COULD NOT BE BUILT, recorded so nobody plans it again.** The
  natural next test was ranging-tape floors against trending ones. It is
  impossible from this journal: `_trend_credit_spread` sets `direction = ""` on
  any non-TRENDING label, so `_impulse_sd` is never called and `floor_px` is
  None. **No ranging floor exists anywhere in the record.** What replaced it is
  `--control matched` — a pseudo-impulse at a random earlier minute on the same
  symbol-day, same direction and construction — which asks the sharper question:
  does the impulse origin survive better than an ARBITRARY recent extreme?

  **STILL UNMEASURED AND STILL DECISIVE: the credit.** The strike curve bounds
  RISK only. A 5-wide taking $1.00 risks 4 to make 1 and needs roughly 80%
  terminal survival to break even before fees; 62% at the floor is far under
  that, and 94% at +2% is only useful if premium survives that far out. Nothing
  here prices it.
- **Pitchfork sloped S/R** — designed, not built, gated on Layer 2. See
  [`docs/WHITEPAPER_pitchfork_overlay.md`](docs/WHITEPAPER_pitchfork_overlay.md).

Per-strategy entry mechanics, gates and thresholds are in
[`docs/MECHANICS.md`](docs/MECHANICS.md); every exit path is catalogued there too.

---

<!-- ================= Iron Condor (current, 2026-07-28) ================= -->


##### Contract telemetry — WHAT IS COLLECTED AND WHO CAN READ IT

Added 2026-08-04 (N.9; `trade_logger` v3.12, `main` v5.5). **Log-only —
nothing gates on any of it.**

**The gap it closes.** Every existing instrument reports WHAT the premium did —
MFE, MAE, giveback, capture ratio, the floor sweep — and they are correctly
denominated in PREMIUM, which is where the P&L lives. None of them reports WHY.
A -27% floor stop is indistinguishable between *the underlying went against us*,
*the underlying went nowhere and theta ate it*, and *we were right and IV
collapsed*. Three causes, three different fixes, one number. On 0DTE that
distinction is the whole game — a correct thesis that resolves slowly is a dud.

**Nothing new is fetched.** `OptionContract` already carries
bid/ask/mark/delta/gamma/theta/vega/iv and `OptionsChain` carries
spot_price/iv_rank. The chain is polled every tick and these values were read
for strike selection and then discarded. This persists them.

**Columns on `trades` (all NULLable, no defaults — see below):**

| column | what it is |
|---|---|
| `entry_delta` | contract delta at fill. **A SELECTOR OUTPUT, not a market observation** — the strike chooser picked it, so "0.30-delta does worse" is partly a statement about the selector |
| `entry_gamma`, `entry_theta` | greeks at fill; theta is the decay rate the trade started against |
| `entry_iv` | contract IV at fill |
| `entry_bid`, `entry_ask` | the SPREAD at fill |
| `chain_iv_rank` | session-level IV context |
| `exit_bid`, `exit_ask`, `exit_iv` | **columns exist, NOT YET POPULATED — see the open item below** |

**Already stored, deliberately not duplicated:** `entry_premium` (the mark),
`exit_premium`, `underlying_entry` (spot at entry), `vix_at_entry`. Two names
for one fact is how a report ends up quietly reading the stale one.

**NULL means NOT CAPTURED, and that is load-bearing.** There are no defaults: a
row from before this shipped must stay distinguishable from a capture that ran.
A default of `0.0` would make every pre-deploy trade look like a zero-delta
entry.

**Captured at both fill seams** — the directional entry and the condor leg —
matched on the **OCC symbol** the row actually filled on, not on strike, because
a condor's two legs share an underlying and a session.

**AVAILABLE FOR REPORTING NOW.** These are ordinary columns on `trades`, so
every consumer that already reads that table can use them with no plumbing:
`excursion_report` (option 40), `trade_report` (option 41), the fleet
consolidation into `fleet_trades_<date>.json` (option 39), and any offline tool
that opens a pulled `trades.db` (option 16). Nothing needs to be added for the
data to be queryable — the reports simply do not GROUP by these fields yet.

**What becomes answerable once sessions accrue:**

- **Direction vs decay vs crush.** `entry_theta` x hold duration gives the decay
  cost in dollars; `underlying_entry` versus the exit spot gives the directional
  component; the residual is IV and gamma. That is a per-trade attribution.
- **Where a correct thesis stops paying.** Bucket that attribution by hold time
  and the crossover is a **TIME STOP** — an exit this system does not currently
  have. `hard_close_15:45` is a session boundary, not a decay boundary.
- **The slippage assumption.** The floor sweep states *"ASSUMES: fill AT the
  floor, no slippage"*. `entry_ask - entry_bid` turns that from a declared
  assumption into a measured distribution, and is the basis for the
  paper-versus-live fill comparison once live trading starts on Aug 31.
- **The 10:00-11:00 hole.** That phase is the worst on the board (-$319 across
  120 trades) while the open is the best (+$9,761). `entry_iv` beside a later
  exit IV is the most direct test of whether that is post-open IV crush.

**⬜ OPEN — exit-side capture is NOT wired.** `place_exit_order(record, reason,
mark_price)` has no chain in scope, and plumbing one through a signature used
everywhere was not worth doing days before the behavioral freeze. The columns
exist and stay NULL until it is. **Consequence for the first read:** the
decomposition can separate DIRECTION and THETA, but IV and gamma stay merged in
the residual. Say "residual", not "IV crush", until the exit side lands.

##### Iron Condor — the PLAN LIFECYCLE, and why 23 plans produced 0 legs

Added 2026-08-04 from a fleet-wide measurement. A condor never trades directly:
it **plans**, then waits for price to reach a trigger. Everything below is about
the gap between those two.

**The plan's reject ladder** (`IronCondorStrategy.decide()`), in order — note
which rungs are silent, because the absence of a log line is itself the signal:

```
1. outside 11:11-14:00 ET                       silent
2. a plan already exists                        silent
3. regime != RANGING                            silent   <- the common one
4. VIX >= VIX_BUTTERFLY_DISABLE                 LOGS
5. expected move <= 0                           DEBUG
6. no liquid strike beyond the dual floor       LOGS
```

Upstream in `main.py` the box must also be **flat** (`attempt_new_entry` is
gated on no open position) and **nothing else may have fired that tick** —
condor is Priority 4, behind ORB, sweep, continuation and butterfly.

**Both death paths, and the asymmetry that matters.** A live plan dies either at
the 14:00 cutoff or on a directional label:

- `CANCELLED before Leg 1` — regime flipped to TRENDING_BULL / TRENDING_BEAR /
  BREAKOUT_VOLATILE. **Sets `self._plan = None`: the plan is destroyed, not
  paused.** A later return to RANGING must build a new one.
- Leg 2 does the opposite — it **PAUSES** on a directional tick. v3.2
  (2026-07-23) made that change explicitly because *"previously this set
  COMPLETE, permanently killing the structure on a single non-RANGING tick"* —
  and its own comment records that **Leg 1 never got the same treatment**.

**THE 2026-08-04 MEASUREMENT — 23 plans, 23 deaths, 0 legs, fleet-wide.**
Cutoff fired **zero** times; every plan died on the cancel branch. But plan
lifetimes ran **1-94 minutes, median ~30**, several 88-94 — so these plans were
alive across most of the window. **Price never reached a trigger on any of
them.** That is not label churn cutting plans short; it is the trigger sitting
where price did not go. `nofloor=0` fleet-wide, so strike selection was not the
constraint either.

**What that leaves open — item AI, and the two answers need opposite fixes.**
Either `CONDOR_TRIGGER_APPROACH = 0.65` is simply too far (a parameter to fit),
or the MIDPOINT the distance is measured from is wrong (the anchor — AI's
argument for a sloped median line rather than the Bollinger midline). Until
2026-08-04 nothing could tell them apart: the approach telemetry existed but
lived **only on the cutoff path**, which never fires.

**Now instrumented on BOTH paths** (`iron_condor_strategy` v-approachalways):
every dead plan logs how far price travelled toward each trigger as a fraction
of the distance it needed, and emits a `condor_abandon` journal row.
`tests/condor_approach.py` reads them and returns a pre-registered verdict —
p90 under 40% is GEOMETRY, at or above 60% is PARAMETER, in between is neither
established. It measures the **closer** side, because a plan needs only one leg
to fire.

**What it does not measure:** premium. Reaching a trigger is not earning a
credit, and a nearer strike collects less. This bounds whether the entry is
reachable — the side that had been failing silently.

##### Iron Condor — current model (supersedes the subsection above)

**Strike selection — dual floor.** The short strike must clear BOTH
`0.80 × expected_move` from spot AND the Bollinger band; whichever is farther
wins. Among strikes beyond that floor the most liquid is chosen, biased outward,
with the tie broken toward the floor (richest premium that still clears it).
**There is no inside fallback** — if no liquid strike exists beyond the floor the
leg is skipped, never sold close. This replaced BB-anchored selection, which had
no minimum-distance floor at all and a fallback that placed strikes *inside* the
band; on 2026-07-28 that model sold seven legs at 6–28% of the expected move.

**Legging — independent.** Both triggers are checked every tick. Whichever side's
conditions are met fires, regardless of order; `call_filled` / `put_filled` are
tracked separately and the structure is COMPLETE only when both are in. This
replaced the sequential model, under which leg 2 was state-gated behind leg 1 —
so if price only ever visited leg 2's side, that leg never fired at all.

Once one side is filled the only valid next actions are **fill the other side** or
**close the filled one**; no new condor plan can start while a leg is live.

<!-- ================= end-of-day flatten (limit_ladder v1.2) ================= -->

##### End-of-day flatten — the 15:40 ladder, then the 15:45 market cross

**This applies to every strategy and every open position.** It is the one place the
mark-limit policy is deliberately abandoned, because an unfilled 0DTE at the bell
is worth nothing.

`execution/limit_ladder.hard_close_order_mode(now_et)` returns the mode:

| ET window | mode | behaviour |
|---|---|---|
| before **15:40** | `none` | Flatten window not open. Normal exits only. |
| **15:40 – 15:44** | `limit` | Post at the mark and **re-price every tick (~15s)**, repeatedly, trying to close without paying the spread. |
| **15:45** onward | `market` | MARKET order. No exceptions. The position closes. |

Constants: `HARD_CLOSE_LIMIT_START_ET = 15:40`, `HARD_CLOSE_MARKET_AT_ET = 15:45`
(`execution/limit_ladder.py`); `HARD_CLOSE_ET = (15, 45)` in `config.py`.

Two notes that matter when reading fills:

- **The 15:40 start is a change, not the original design** (limit_ladder v1.2,
  2026-07-22). It used to be a single 15:45 market sweep; the five-minute ladder
  was added so most positions close at the mark instead of crossing.
- Trades closed this way carry exit reason **`hard_close_15:45_ET`**. A position
  that filled during the 15:40–15:44 ladder still books under that reason, so the
  reason alone does not tell you whether it crossed the spread — check the fill
  time against 15:45.

<!-- ================= was: README.md § Exits ================= -->

## Exits

##### ORB — evaluated every tick, first match wins

| # | Trigger | Condition | Purpose |
|---|---|---|---|
| 1 | Hard close | 15:45 ET | Time |
| 2 | **−25% premium floor** | `premium ≤ entry × 0.75` — **unconditional, every tick**, independent of trail state | **Minimize loss** |
| 3 | **Structure stop** | Last *closed* 1m candle closes **beyond the impulsive candle's wick** (`underlying_stop`). **NOT** the range boundary — closing back inside the range does **not** stop the trade | **Thesis death** |
| 4 | Theta bleed | **All four:** held ≥ 20 min · gain ≥ 10% · gain **< 20%** · projected decay (`theta × 20/1440`) ≥ current gain | **Protect profit** |
| 5 | Past 100% TP | **No hard exit.** Trail tightens to the nearest unfilled in-favor 1m FVG, floored at 85% of current premium | **Let it run** |
| 6 | Below 100% TP | FVG trail arms at **+20%**; % trail arms at **+50%** and ratchets to 75% of current. Higher governs | **Protect profit** |

**#2 and #3 are an AND, not an OR.** They catch different deaths: premium death (theta,
retracement, or the mix) and thesis death (structure). Whichever fires first.

**Exit-reason integrity (v3.3, 2026-07-12):** `stop_premium` is **immutable** — set once at
entry, forever the true −25% floor. Trails persist in their own `trail_stop` column (schema
migration is automatic), and the exit engine re-arms its in-memory trail from it on restart.
Before this, every trail update overwrote `stop_premium`, so every trail-armed exit — including
post-target exits at +100%+ — was logged `hard_stop_25pct`/`stop_hit`, poisoning the
`exit_reason` distributions Phase-3 calibration reads. Same exit ticks, same prices; the labels
now tell the truth.

**The trail and the structure stop are both necessary and serve opposite jobs** — one protects
gains, one minimizes losses. Neither supersedes the other.

**Not present on the ORB:** no BOS exit (that is sweep-only) · no max-hold · no 11:00 exit.

##### Trend Continuation — EXHAUSTION-based (NEW 2026-07-18)

The continuation exit is where the trade lives or dies, so it is the deliberately intelligent
half. Evaluated every tick, first match wins:

| # | Trigger | Condition | Purpose |
|---|---|---|---|
| 1 | Hard close | 15:45 ET | Time |
| 2 | **Regime flip** | Regime no longer trending **in our direction** | **Thesis death — the primary stop** |
| 3 | **−25% backstop** | `premium ≤ entry × 0.75` (`CONTINUATION_STOP_LOSS_PCT`, `exit_engine` v4.0 — no longer borrows the blanket `MAX_LOSS_PCT`) | Disaster backstop |
| 4 | **Exhaustion (two-stage)** | *Only past +15% gain.* **Extension:** price ≥ 2·ATR from the midline → **tighten trail to 85%** (does *not* exit — a strong trend can stay stretched). **Divergence:** new favourable price extreme on **weaker** 5-bar momentum → **exit** | **Detect a spent move** |
| 5 | **Theta bleed** (`exit_engine` v4.0) | placed AFTER exhaustion: held ≥ 20 min · gain ≥ +10% · below the trail ceiling · projected calendar-day decay ≥ gain | A stalled winner no longer decays untouched toward the floor |
| 6 | Runner trail | FVG trail **anchored to 5m gaps** via `_fvg_frame` (v4.0; graceful 1m fallback); once armed it owns the trade and silences theta | Let it run |

The distinction from a normal stop: a stop asks *"was I proven wrong?"* (that is #2/#3).
Exhaustion asks *"is the move **tired**, even while still technically going my way?"* — which is
what stops a continuation trade from handing back its gains at the turn. **Extension tightens,
divergence exits** (v1 two-stage). A stricter "both must agree" mode is noted in-code for
future reconsideration; it maps closer to how the operator trades but is intentionally not a
live flag.

**Engine-state exactness with a safety net.** The exit prefers the *live* `vol_state`/`trend`
threaded down from `main.py` (so it judges exhaustion against the same midline/momentum the
entry used), but **falls back to recomputing midline and ROC from `df_5m`** when that state is
absent (restart recovery, adopted positions). It therefore *cannot* raise on a missing engine
snapshot — it only degrades precision. The `vol_state`/`trend` kwargs were added
**optional-with-defaults** through `manage_open_position → _manage_one → evaluate()`
specifically to avoid the 2026-07-16 signature-mismatch crash-loop; every existing strategy
routes byte-identically with them present (regression-checked).

The complete exit catalogue — every strategy, every path, with current values —
is in [`docs/MECHANICS.md`](docs/MECHANICS.md).

---

---

## Paper fill pricing — ONE model, every strategy (T.2, documented 2026-07-30)

**Every paper fill books the price the live path would have POSTED — the mark
for singles and butterflies, the mid-credit limit for condor legs and rolled
verticals. There is no synthetic haircut on any strategy.**

Single authority: `execution/limit_ladder.paper_fill_credit()`. Condor legs
(`main.py` v4.1), rolled verticals, singles and butterflies all route through
it, so paper friction is identical across strategies and cross-strategy paper
P&L is comparable. Before v4.1 the haircut was applied inline for condors while
`entry_engine` v3.8 had already stopped applying it to singles — two friction
models, and no note anywhere saying so.

**Why no haircut (the reasoning, so it isn't re-litigated):** a limit order at
the midpoint is a reasonable expectation. If it doesn't fill we cancel, reassess
and re-establish the midpoint — that is the 20-second cancel window doing the
work. The honest residual risk is therefore **no-fill risk, not slippage**, and
no-fill risk cannot be modelled as a price shave. A haircut would book a worse
price on trades that DID fill, which is a different and wrong claim.

**The knob:** `OT_PAPER_SLIPPAGE_PCT`, default `0.0` (= the posted price). One
lever, fleet-wide, no code change. It is deliberately a MEASURED value, not a
guess:

- **N.4 (Aug 14)** reprices post-Aug-3 paper condor credits against the archived
  chain NBBO at the entry timestamps. If paper credits sit systematically rich
  against real quotes, the haircut returns — with that measured number.
- From **Sep 1** the live fill-quality audit becomes the permanent validator.
- Pre-2026-07-22 paper history was booked at `0.01`; set that value to compare
  like for like against it.

**What this does NOT model:** the trade that never filled at all. Paper assumes
the post fills. That gap is real, it is not slippage, and N.4 is how it gets
measured rather than guessed.
