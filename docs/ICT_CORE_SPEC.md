# docs/ICT_CORE_SPEC.md — what the ICT setup suite needs from the core — v1.0

**From:** the ICT setup suite (owner of `strategy/ict/`)
**To:** the core owner (owner of `smc/`, `main.py`, `config.py` — WA §7)
**Date:** 2026-08-18
**Status per item:** REQUESTED until the core marks it DELIVERED here with a
version + commit. This file ships in the repo so the contract survives both
threads (the 07-30 rule: the other thread's output lands as a record, not
only a commit).

The suite consumes ONE object — `strategy/ict/context.ICTContext` (contract
v0.1, defined in `strategy/ict/context.py`). Every gap below is a field of
that object. The suite already runs degraded: gaps register in
`ICTContext.unavailable`, cap `completeness`, and bar CONFIRM where required.
Delivering a gap = constructing the field and removing its `unavailable`
entry. **No setup file changes when a gap lands — availability flips.**

What fires TODAY vs what waits: `ICTSweepMSS`, `ICTJudasPO3` (degraded
true-open) and `ICTOBFVG` complete their required chains on the current
surface; `ICTSilverBullet` waits on G1, `ICTModel2022` on G2,
`ICTBreakerUnicorn` on G3, `ICTOTEConfluence` on G4. Nothing fires at all
until G6 wiring + §3.5 validation regardless.

---

## G1 — Silver Bullet window + FVG-formed-inside rule
**Need:** (a) the authoritative window primitive — 09:45–11:30 ET, env
`OT_ICT_SB_START` / `OT_ICT_SB_END` (the suite's interim clock
`context._sb_clock` reads the same envs; bless it or supersede it, but ONE
clock — the killzone docstring's own rule). (b) **FVG birth stamps**:
`ICTContext.fvg_births: Dict[int, str]` mapping `id(fvg) -> ISO bar
timestamp of the middle candle`, for every FVG the analyzer carries.
`FairValueGap.index` is positional in a growing frame and cannot answer
"formed inside the window" after the frame rolls; a birth **timestamp** can.
(c) With births present, the core (or the suite, once births exist — state
which) computes `fvg_in_window` for the entry gap; the suite's component
holds value 0 until then (test C4 pins that availability alone cannot fake
a pass).

## G2 — Displacement → FVG linkage
**Need:** `ICTContext.displacement_fvg` — the FairValueGap **created by the
displacement leg that caused the MSS**, or None. `last_displacement()` knows
the candle; the analyzer knows the gaps; only the core can join them without
the suite re-deriving detection (the 774-line-duplicate error). The 2022
model's entry IS this gap — the setup refuses to substitute nearest-in-favour
(that trade exists and scores under `ICTOBFVG`).

## G3 — Breaker / Unicorn detection
**Need:** `ICTContext.breakers: List[Breaker]` and `unicorns:
List[Unicorn]`.
Shape consumed by `breaker_unicorn.py`:
```
Breaker: .top .bottom .direction ("bullish"=failed bearish OB after a
         bullish MSS, mirrored) .failed_ts .mss_ref
Unicorn: .breaker (the Breaker object) .fvg (the overlapping FairValueGap)
         .overlap_top .overlap_bottom
```
Absent entirely today (handoff §4.2.3).

## G4 — Named impulse leg (OTE basis)
**Need:** `ICTContext.impulse_leg: dict` — `{"origin": float, "extreme":
float, "dir": "bullish"|"bearish", "start_ts": iso, "end_ts": iso}` for the
most recent displacement **leg** (multi-bar, origin wick to terminal
extreme), not the single qualifying candle. OTE = 0.62–0.79 retracement of
THAT leg — a different quantity from dealing-range position (handoff
§4.2.4). The suite computes the band itself (`ote_confluence.ote_band`);
it only needs the leg named.

## G5 — AMD phase state + true opens
**Need:** `ICTContext.amd: dict` — `{"phase":
"ACCUMULATION"|"MANIPULATION"|"DISTRIBUTION", "true_open_midnight": float,
"true_open_0830": float, "true_open_0930": float}`. Constraint acknowledged:
the EXT stream is **1-HOUR** (FEED.2, ~54 MB veto on finer), so midnight and
08:30 opens are 1h-resolution reads — fine for reference levels, stated as
such. The suite already computes the 09:30 open from the RTH frame and runs
Judas degraded on it; G5 raises completeness rather than gating fire.

## G6 — Pre-ladder dispatch branch (main.py wiring)
**Need, in `attempt_new_entry` BEFORE the label-keyed priority ladder:**
```python
from strategy.ict import build_context, ict_dispatch
ictx = build_context(smc_state=ctx.get("smc"), structure=ctx["structure"],
                     liq_map=ctx["liq"], df_1m=ctx["df_1m"],
                     now_et=now_et, price=current_price)
sig = ict_dispatch(ictx, chain=chain, now_et=now_et, journal=_sigj.journal)
if sig is not None:
    # -> scorer/risk/entry path, same as any strategy signal
    # if ORB's window is live, journal orb_preempted_by=sig.strategy_name
```
(Exact ctx key names are the core's to correct — stated here as read from
main v6.21.) Hard requirements from handoff §3.2.1: this branch consults
**no `primary_regime`**; a returned None falls through to the existing
ladder unchanged; every tick calls it (the suite journals forming states
even when nothing fires — that journal is how priors get fitted). SB/ORB
share the slot with SB ranked first and preemption journaled (§4.2
decision, measurable counterfactual).

## G7 — Versioned structural-context snapshot (core-built ICTContext)
**Need:** the core constructs `ICTContext` itself (`built_by="core"`) once
per tick with G1–G5 filled, superseding the suite's degraded
`build_context`. Contract version bumps (0.1 → 0.2 …) go through THIS file
with a changelog line; the suite pins `contract_version` and will refuse a
major mismatch loudly rather than misread fields.

## G8 — config.py registrations (one edit, core-owned)
1. Add to `DEBIT_DIRECTIONAL_STRATEGIES`: `ICTSilverBullet`, `ICTJudasPO3`,
   `ICTModel2022`, `ICTSweepMSS`, `ICTBreakerUnicorn`, `ICTOTEConfluence`,
   `ICTOBFVG` (all seven are debit-directional in v1.0; §3.1 "every new
   directional debit strategy added to that set by name").
2. Move `DEBIT_DIRECTIONAL_CUTOFF_ET` default 11:00 → **11:30** (handoff
   §3.1, "the constant moves to 11:30 for this build"). The suite's own
   belt-and-braces cutoff reads `OT_ICT_DEBIT_CUTOFF` (default 11:30) and
   journals `wants_credit` on post-cutoff eligibility — demand data for the
   credit adapter (BACKLOG F.14).
3. Document the suite's env knobs (env wins, config documents — house
   convention): `OT_ICT_ARMED` (0), `OT_ICT_<NAME>_VALIDATED` (0 each),
   `OT_ICT_SCORE_FLOOR` (0.65), `OT_ICT_COMPLETENESS_FLOOR` (0.75),
   `OT_ICT_SB_START` (09:45), `OT_ICT_SB_END` (11:30),
   `OT_ICT_DEBIT_CUTOFF` (11:30), `OT_ICT_SIZE_BIAS_MIN/STRONG/CLEAN`
   (0.50/0.75/0.85), `OT_ICT_SIZE_SD_AWARE/CONFIRM` (1.75/2.0),
   `OT_ICT_SIZE_FRAC_MARGINAL/SOLID` (0.33/0.66). All stated priors
   (§3.4) — fitted later from this box's own `ict_setup` journal.

---

## What the suite guarantees back
- PAPER-safe: the package builds proposal objects only; three independent
  gates (armed / per-setup validated / debit cutoff) all default closed.
- Every setup journals `ict_setup` on state change (phase, score band,
  direction, missing-required) — banded to 0.05 so it cannot spam.
- No label gating anywhere; any future label use will be a scored `dir:`
  component with its own weight, journaled (handoff §3.2.3).
- Behavioural suite `tests/test_ict_setups.py` (script-mode, deliberate-
  failure check included) is green at delivery; `tests/test_smc_core.py`
  and `test_no_undefined_names` re-verified green beside it.
- §3.5 stands: no setup arms until `backtest_harness --engine smc` passes
  on real QQQ tape against a pass condition the OPERATOR writes first.
  Suggested first candidate: `ICTSweepMSS` — the only setup whose full
  required chain completes on today's surface.

## Changelog
- **v1.0 — 2026-08-18** — created with the ICT setup suite delivery. G1–G8
  REQUESTED.
