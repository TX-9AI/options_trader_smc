# docs/BACKLOG.md — options_trader_smc — v1.15

**Fork opened 2026-08-18 from options_trader_v3 @ `0720753`. Candidate: QQQ —
the EXISTING box, converted (operator's decision, 2026-08-18; SPX stays on the
legacy core as the other daily trader).
Read top-down. Tags as in the parent: `[DESK]` workable now · `[DESK·DATA]`
blocked until sessions accrue · `[FLEET]` needs the box up or a deploy window.
This backlog ships in every archive (parent WA §18 — EV moves only when the
backlog records it). BUILT ≠ PUSHED ≠ BAKED.**

## PART 0 — WHY THIS FORK EXISTS
The parent's founding premise — infer a forming pattern, score it, scale on
the score — was never run; what ran confirmed moves already made (grade
inversion A −$8,244 vs B +$1,893; RGCV 1.00-vs-0.34 inversion; L3 0%). The
2026-08-17 verdict: RETOOL WITH A NEW CORE. P0.1 then showed the STRUCTURAL
input class was never even collected. SMC/ICT **is** that class, made the
engine rather than a probe column. This fork is the concrete bet; the converted
QQQ box runs it against the legacy fleet on identical plumbing.
**The comparison is the experiment: one variable (the entry core), same
execution, same exits, same risk — the pitchfork-twin discipline at fork
scale.**

## PART 1 — THE SCHEDULE (accomplishment order)

**F.1 — Repo stood up. ✅ BUILT 2026-08-18 (this delivery).** Salvage tree +
`smc/` core + main v6.19 wiring + config v4.19 + docs + behavioral suite +
wiring canary, all green in the sandbox. ◐ becomes PUSHED when the operator
lands the tarball on control and pushes to the new remote; ✅ when the QQQ box
bakes it.

**F.2 — [FLEET] Convert the existing QQQ box. ORDER IS LOAD-BEARING.**
No new instance: the box already has its IAM role, its S3 push timer, its
feed_store candle depth, and QQQ is already configured fleet-wide (strike
increment 1, penny class, ALWAYS_ON so it trades every session). Sequence:
1. **F.2a — engine provenance on the trade row. ✅ BUILT 2026-08-18.**
   The `regime_engine` column has existed since v-eng (2026-07-30) and main's
   changelog claimed trades carried it — **but no caller ever set it**, so
   every row on every box holds the `''` default. Fixed CENTRALLY in
   `trade_logger` v3.16 (`set_engine_tag()` + a stamp inside `log_entry`, so
   the fourth call site that nobody remembers is covered too) and wired in
   main v6.20, which resolves the tag AFTER the engine is resolved — a box
   whose smc import failed stamps what actually RAN, not what was asked for.
   Proven by `tests/test_engine_provenance.py`: rows written, column read
   back, including the ALTER-TABLE migration path the real QQQ box will take.
   Pre-cutover rows keep `''` — honest ("not recorded"), distinguishable from
   `"L2"`. ⚠️ **The same one-line fix belongs in the PARENT** so legacy rows
   assert `L2` rather than implying it by absence; until then the legacy
   fleet's rows stay blank and the cutover boundary is the DATE plus this
   box's own non-blank rows.
2. Repoint the box's git remote to `options_trader_smc`; bake; set
   `OT_REGIME_ENGINE=smc` in the systemd env (the repo default already is,
   but state it so the value is auditable on the box).
3. Verify: `[SMC c=..]` on the first REGIME line, an `smc_setup` row in the
   day's journal, `engine="SMC"` on regime_log rows, PAPER_TRADING True.
4. **Record the cutover timestamp in HISTORY.md and in this backlog** — every
   before/after comparison keys on it.
⚠️ **Exclude this box from fleet-wide bakes** until the bake path is
repo-aware (WA §26). One fan-out push ends the experiment silently.

**F.3 — [DESK] Candle depth: mostly already there.** Converting an existing
box means the virgin-box backfill largely evaporates — feed_store already
holds this symbol's rolling window and the warehouse holds QQQ history from
first push. What remains: confirm the depth actually present is enough for the
HTF structure reads, and only if it is not, build the read-only
`s3://…/raw/candles/dt=*/sym=QQQ/` → feed_store materializer (provenance-
stamped, dry-run gated). ⚠️ Control has no PutObject and must not get it;
this is read-only in both directions.

**F.4 — [DESK·DATA] First-light calibration.** After ~5 sessions: fit the
SMC_TRUTHS §5 priors from the journaled distributions (the readiness-digest
pattern — print the exact `export OT_SMC_*` lines; flag anything pegged >60%).
Never off one session.

**F.5 — [DESK·DATA] The acceptance test, pre-registered NOW:** replay the
parent's QQQ 2026-08-17 tape through this core. PASS = permission withdrawn
before the second and third morning entries using only tape available at each
instant, AND not withdrawn on the profitable trending sessions
(TRENDING_BULL +$4,394 / _BEAR +$4,196 / BREAKOUT +$2,729). Both halves
required — a signal that revokes everything is not a signal. The bounded cost
(trades taken between the range establishing and the revocation) is reported,
not hidden.

**F.6 — [DESK·DATA] Head-to-head — TWO comparisons, both weak alone.**
(a) SEQUENTIAL, same symbol: QQQ post-cutover vs QQQ's own legacy history —
one variable is the core, but the tape differs, so any regime-mix shift
between the periods confounds it; report the regime mix of both windows
alongside the result. (b) CONCURRENT, cross-symbol: QQQ-SMC vs SPX-legacy
over identical sessions — same tape conditions, but symbol (spread, increment,
notional) confounds it. **Neither is a clean twin; state which confound you
are eating in every claim.** Mechanically both are a WHERE clause once
`engine=` exists on the rows (F.2a). Compare nf/ok separation of the structural confidence against
RGCV's measured inversion, and the revocation gate's dodged-loss vs
missed-winner ledger (`gate_block:smc_revoked` rows carry the full refused
signal — the recall side, by construction).

**F.7 — [DESK] Order blocks into the POI slot (S.4).** The analyzer already
emits them; the setup lifecycle currently arms on FVGs only. Extend
`unmitigated` filtering to OBs, journal which POI class converts better.

**F.8 — [DESK] FILE_MAP regeneration for the fork** (the parent's was
dropped as stale-by-construction; regenerate from real imports once the tree
settles).

**F.9 — [FLEET] Control-side guards so the cutover cannot be undone.
Shipped 2026-08-18 as a SEPARATE day_trader_pro delivery** (they are
day_trader_pro files; a menu's code lives in the repo that runs it). Three
changes, all additive, none altering what happens to the 28 legacy boxes:
(a) `devtools.sh` `ask_url()` no longer offers the parent repo as the
Enter-default — repoint now requires an explicitly typed URL; (b)
`fleet.py repoint` refuses an unscoped run when the fleet holds more than one
distinct remote, naming the boxes that would be overwritten; (c)
`wake_and_bake.py` VERIFY groups convergence BY REMOTE, so a heterogeneous
fleet stops printing `🚨 NOT converged` on every run — the cry-wolf class
(CV.1) that trains an operator to ignore red.
**Bake itself was never the risk:** its command is
`git fetch origin && git reset --hard origin/main` with no URL in it, and
`push.sh --deploy` parses the repo from the box's own remote. Verified by
reading both, 2026-08-18.

**F.10 — [DESK] UPSTREAM PORT LEDGER. The parent moved the day we forked.**
The fork's baseline is options_trader_v3 `0720753`. Every parent commit after
it is a conscious PORT-or-DECLINE, recorded here — silence is how two repos
become two different programs nobody can compare.

| parent commit | what | decision |
|---|---|---|
| `5b9e71f` main v6.18 P0 ctx fix | run_analysis NameError | already in the fork (it originated here) |
| `2cae11b` TC.6 v1.5 strike selection | short strike = FIRST strike INSIDE the ORB range; quote-width gate dropped for mark-or-better fills | **PORTED 2026-08-18** as trend_credit_spread **v2.2** |

⚠️ **Two parent-side defects found while porting — report upstream, do not
fix here silently:**
1. `2cae11b` did NOT bump `strategy/trend_credit_spread.py`'s header; the
   parent's title still reads v2.1 — 2026-08-14 while the file contains v1.5
   behaviour. Same stale-title class as the 07-23 sweep.
2. `2cae11b` shipped with **its own guard suite red**: three canaries in
   `tests/test_tcs_exit.py` pinned the exact source lines the rewrite deleted,
   and they fail against parent HEAD today. Verified by running the suite
   against `2cae11b` before touching anything. Re-pinned here to the
   PROPERTIES (absence of `min_dist`, of `select_beyond_rail(`, of a
   `bound, extreme` tuple; presence of the inside-range constraint) in
   test_tcs_exit **v1.1**, with a comment/docstring-stripped source helper so
   an accurate changelog can never trip an absence canary — the SWP.1 lesson.

**F.12 — [DESK] THE ACCEPTANCE REPLAY. Harness ✅ BUILT 2026-08-18
(`tests/backtest_harness.py` v1.3); the RUN is still owed.**
`--engine smc` drives the real SMC core from the same per-bar inputs the v1.3
classifier uses and overrides the same boundary main.py overrides. It also asks
`entry_permitted()` per census setup — without that the replay would show label
changes and silently miss the withdrawal mechanism, which is the mechanism
under test. Cadence is FORCED to 1 (edge-triggered breaks drop crossings on a
sparse tape) and the tape is asserted to be Eastern (a UTC tape would put the
ORB window in pre-market and produce a confident wrong answer).
Run it as: `--symbol-glob '~/day_trader_pro/ohlc/*/QQQ_ohlc_*.csv'` with
`--vix-const` or a VIX tape.
**PRE-REGISTERED PASS CONDITION, unchanged and both halves required:**
permission is withdrawn before the second and third QQQ 2026-08-17 morning
entries using only tape available at each instant, AND is not withdrawn across
the profitable trending sessions. A signal that revokes everything is not a
signal. Report the bounded cost — trades taken between the range establishing
and the revocation — rather than hiding it.
⚠️ Occurrence only: the chain is a modelled BS synth with no fill model.
⚠️ The ground truth (entry timestamps of those three trades) comes from the
trade record, not from impression.

**F.13 — [DESK] THE ICT SETUP SUITE. ✅ BUILT 2026-08-18 (this delivery);
wiring + validation owed.** Seven setups from scratch per
HANDOFF_FABLE_ICT_SETUPS, ranked (`strategy/ict/` v1.0): SilverBullet >
JudasPO3 > Model2022 > SweepMSS > BreakerUnicorn > OTEConfluence > OBFVG.
Each is a continuous SCORER, not a binary trigger: weighted components,
`score` over available inputs, `completeness` capped by core gaps, REQUIRED
components gate CONFIRM, and a 3-of-4 state journals as FORMING
(`ict_setup`, banded 0.05). Size = f(ICT bias, displacement) ONLY —
0/0.33/0.66/1.0 tiers, stated priors, never above baseline risk. No setup
consults `primary_regime`; any future label use must be a scored `dir:`
component (handoff §3.2). Three fire gates, all default closed:
`OT_ICT_ARMED`, per-setup `OT_ICT_<NAME>_VALIDATED` (set only after a §3.5
harness pass against an operator-pre-written condition), and the 11:30
debit cutoff (journals `wants_credit`). Behavioural suite
`tests/test_ict_setups.py` green incl. deliberate-failure check; smc_core +
no_undefined_names re-verified green beside it.
**Owed, in order:** (1) core gaps G1–G8 per `docs/ICT_CORE_SPEC.md` — the
contract file; the suite consumes `ICTContext` v0.1 and flips on
availability, no setup edits needed. G6 (pre-ladder dispatch wiring) and G8
(config registrations) unblock first light; G1–G5 unblock SB/2022/Breaker/
OTE respectively. (2) First validation candidate: **ICTSweepMSS** — the
only setup whose full required chain completes on today's surface; operator
writes the pass condition before the run. (3) F.14.

**F.14 — [DESK] CREDIT EXPRESSION FOR AFTERNOON ICT SETUPS. Gate: measured
`wants_credit` demand in the `ict_setup` journal.** Post-11:30 fire-eligible
debit setups (OTE especially — the deep retrace lands late by construction)
get expressed as credit verticals: the ICT layer supplies side, strike
anchor (the invalidation level) and thesis; construction/execution reuses
the TCS/`credit_vertical.py` machinery (POP-gated, mark-or-better) rather
than growing a second credit path — the TCS.1 lesson. Not built in v1.0;
dispatch journals the demand so this is sized by data, not appetite.

**F.15 — [FLEET] ✅ G6 + G8 BUILT 2026-08-19 — THE RAILS THE ICT SETUPS RUN ON.**
Until this landed, `strategy/ict/` was unreachable code however green its
tests were. **G6** (main **v6.22**): the ICT branch evaluates on EVERY tick
inside `attempt_new_entry`, positioned BEFORE the label-keyed ladder — proven
by AST line position, not by grep, because "before" is an order property.
Returns None → the ladder runs byte-identically to v6.21. ORB now tests
`signal is None` so it cannot overwrite an ICT signal one line later, and a
preempted CONFIRMED ORB journals `preempted:ict_ranked_first` — the
counterfactual the operator's share-the-slot decision depends on. Import
guarded; an unavailable suite PAGES rather than looking like a quiet session.
**G8** (config **v4.20**): all seven NAMEs registered in
`DEBIT_DIRECTIONAL_STRATEGIES` (verified equal to the suite's own NAME
constants — a name mismatch would exempt a debit setup from the cutoff
silently), `DEBIT_DIRECTIONAL_CUTOFF_ET` 11:00 → **11:30** so the Silver
Bullet window is not truncated, the GEX-pin butterfly still exempt BY ABSENCE,
and the OT_ICT_* knob block documented as stated priors.
`tests/test_ict_wiring.py` v1.0 pins all four properties with a
deliberate-failure mode.
⚠️ **NOTHING IS ARMED.** `OT_ICT_ARMED=0` and every per-setup
`OT_ICT_<NAME>_VALIDATED=0`. The next session journals `ict_setup` forming
states and trades no ICT setup — which is the intended first-light state, and
the journal is the data the priors get fitted from.
**Owed, in order:** (1) the operator writes the pass condition for
**ICTSweepMSS** — the only setup whose required chain completes on today's
surface; (2) its harness run (`--engine smc`, real QQQ tape); (3) arming it in
the unit file, and only then; (4) G1–G5 unblock SB / 2022 / Breaker / OTE /
Judas respectively.

**F.16 — [DESK] THE OBSERVE RUN. Harness ✅ BUILT 2026-08-19
(`tests/ict_observe.py` v1.0); the RUN on real QQQ tape is owed.**
Replays the ICT suite bar-by-bar over the per-date OHLC tape and reports the
six pre-registered criteria — frequency · chain integrity · score
distribution · stability · **separation** · novelty. It DECIDES NOTHING: the
numbers come out of the observed distribution, and the thresholds chosen from
them must be tested on a DIFFERENT pass, never the one that produced them.
**Separation's direction is pre-registered IN CODE:** the high-score half's
median forward R must EXCEED the low-score half's; inverted is the
grade-inversion signature and a stop-and-rethink, not a retune.
Forward outcome is TERMINAL move over 30 bars in underlying R on each setup's
own invalidation — deliberately not maximum-favourable excursion, which is
positive for nearly any bar and would manufacture a separation that is not
there. No premium, no fills, no theta: occurrence only.
⚠️ **Smoke-tested on synthetic tape only so far.** That run's separation
figure is meaningless (a random walk cannot separate) — it proved the plumbing,
not the model.
🔴 **AND IT ALREADY FOUND THE FIRST REAL DEFECT:** setups form while
`position_pct == -1.0`, the no-range sentinel. A POI setup is a claim about
where price sits in a range; with no range the claim is empty. 1122 bars of
the smoke tape tripped it. This is now a pre-registered CHAIN-INTEGRITY
violation — a defect in our code, not a signal about the setup — and it is the
core's to fix before any observed number is trusted.

## PART 2 — DEFERRED, WITH THE GATE NAMED
- **Sizing on structural confidence** — gated on the parent transition
  roadmap's five Phase-2 preconditions. Not before.
- **HTF (1h/1d) structure state in the core** — gated on F.3 depth landing;
  a vote cast on a starved frame is not the vote a warm frame casts.
- **CONFIRMED-setup fast-path entries** (a dedicated SMC strategy rather than
  relabeled gates) — gated on F.5 passing and F.4 fitted bounds.
- **Killzone-conditional gating** — journal first; the windows already gate.

**F.11 — [DESK] ✅ FIXED 2026-08-18 (main v6.21), BEFORE THE FIRST SMC SESSION.
Two silent regressions the v6.19 wiring introduced, neither about the label.**
The L1 scorer call sat inside the `_REGIME_ENGINE == "l2"` branch, where it
had always lived, so under the fork's default engine: (a) `ctx["l1"]` was
never set and **SweepReversal could not fire at all** — its dispatch gates on
`ctx["l1"].scores["SWEEP_REVERSAL"]` because SWP.1 deliberately stopped
requiring the label — and (b) `regime.flat_angle_deg` reverted to its default
for five strategies + entry_engine, re-opening STR.2's bug by another route.
`_l1_scores(ctx)` also returned None, omitting the regime-axes decomposition
from every journal row. Hoisted above the branch; L2 consumes the same result
and fails closed if the scorer is unavailable. `tests/test_l1_engine_independent.py`
asserts the SCOPE property by AST, fails against the pre-hoist file, and has a
deliberate-failure mode.
⚠️ **Live proof is still owed and belongs to the first session:** a NON-ZERO
`SWEEP_REVERSAL` setup score in the journal and a `flat_angle_deg` that is not
the default. The test proves placement, not usefulness.
⚠️ **DECISION OWED ON SWEEP:** it can now fire again, and its measured live
win rate is 0.4%. Leaving it armed is a choice — make it deliberately.

**F.17 — [FLEET] ✅ FIXED 2026-08-19 (exit_engine v4.23) — THE ICT STOP WAS
CARRIED AND NEVER READ.** Every ICT strategy fell through the exit router's
`else` into `_evaluate_sweep`, which contains **no reference to
`underlying_stop` in its 94 lines**. So a setup computed its structural stop
(SweepMSS: the raid's wick extreme), `setup_base` validated the level's
coherence, `entry_engine` wrote it to the record — and the trade was then
managed on the 40% premium floor plus a generic BOS check while the thesis
invalidation sat unread. Price could close back through the purged level with
the position still open. It would have presented as "the ICT setups lose",
not as a wiring gap. **Third instance of the same class** (sweep gate, flat
angle, this): carried correctly right up to the consumer, invisible to every
test.
`_evaluate_ict` evaluates STRUCTURE FIRST — close-based on the last CLOSED 1m
bar, so a wick through the swept level survives (a wick is a raid, a close is
acceptance; an ICT setup stopped out by its own liquidity sweep would be a
parody of itself) — keeps the premium floor underneath as a backstop, treats
reaching the opposing draw as runner mode rather than a hard TP, and inherits
hard-close, theta-bleed and the FVG trail unchanged. **Routed by PREFIX** so a
setup added later cannot inherit the wrong evaluator by being forgotten in an
enumeration. Legacy routing untouched — SweepReversal still lands in
`_evaluate_sweep`, which matters because it is the comparison baseline.
`tests/test_ict_exit.py` v1.0 calls the evaluator and asserts on the decision:
routing (incl. all seven names and that SweepReversal did not move), the stop
firing in BOTH directions while premium is healthy, the wick surviving, the
floor still backstopping, and an inert stop being visible rather than silently
green. **Proven to go red against the pre-v4.23 router (7 failures)** and
carries a deliberate-failure mode.

**F.18 — [FLEET] ✅ DONE 2026-08-19 — TIGHTER FLOOR + ORB OUT OF RANGING.
SHIPPED TO BOTH REPOS THE SAME DAY.** Operator direction. (1) `MAX_LOSS_PCT`
0.40 → **0.25**, reaching `stop_hit` (sweep AND the ICT suite), `hard_stop`
(ORB) and the ADOPTED stops via ADOPTED_STOP_PCT. Butterfly (own 0.25), condor
(CONDOR_STOP_LOSS_PCT) and continuation (0.15) never read the constant and are
untouched. The v2.0 argument for the wider floor assumed the structure stop was
doing the real work underneath — it now genuinely is for ORB, Continuation,
TC.6 and, since v4.23, the ICT suite, so the premium floor returns to being a
disaster backstop rather than a second stop. (2) **ORB no longer fires under
RANGING** — the operator's conclusive loss leader — as a FLAG
(`ORB_BLOCK_RANGING`, env-reversible) rather than a deletion from
`_orb_ok_regimes`, with the refusal journaled as `gate_block:orb_ranging`.
Silence would have made "ORB did not set up" and "ORB was forbidden"
indistinguishable in the record.
⚠️ **The identical change ships to options_trader_v3** (main v6.19 / config
v4.19 / BACKLOG v5.12). The fork and the legacy fleet are an A/B; moving a stop
or a regime permission on one arm only would make every later difference
between them unattributable.
`tests/test_stops_and_orb_ranging.py` asserts the floor as a DECISION (−30%
exits, −20% holds) rather than as a constant — asserting the constant alone
would pass even if nothing read it — and pins the RANGING branch AHEAD of the
permissive clause by AST, since a block placed after it would be dead code
that still reads correctly. Deliberate-failure mode included.

**F.19 — [DESK] 🔴 THE SWEEP EVIDENCE WAS DEAD ON BOTH BRANCHES. ✅ FIXED
2026-08-19.** The first real observe run said six of seven setups never
reached READY across 27 sessions, and the only one that ever fired was
**ICTOBFVG — the lowest-ranked of the seven, the one needing no sweep and no
kill-zone at all.** That looked like a model result. It was a key mismatch, in
two places:
1. `sweep_evidence()` reads `raid["thesis"]`; `raid_in_progress()` emitted
   `pool`/`kind`/`name`/`depth_pct` and nothing about direction. **primitives
   v1.1** now states the thesis a raid implies (a swept LOW that reclaimed took
   sell-side liquidity and failed → thesis UP; mirrored for highs).
2. The context adapter reads `LiquiditySweep.direction`; the dataclass had
   `kind` and no such attribute, so `getattr(s, "direction", "")` won every
   time. **liquidity_mapper v4.2** adds it as a DERIVED property — the
   consumer was already asking, the producer simply never offered.
Measured effect on the smoke tape: ICTSweepMSS's required `dir:sweep` went
from **mean 0.00 / meets-floor 0.0%** to **mean 0.40 / 57.2%**. Additive on
both sides; no consumer of `kind` changes.
⚠️ Neither raised. Neither failed a test. A required component was simply
always zero — and it presented as "the setups don't work".

**F.20 — [DESK] ✅ `tests/test_key_contracts.py` v1.0 — the generalizable guard.**
THREE instances of this exact shape inside twelve hours: the two above, plus
the observe harness reading `raid["level"]`, which reported "pool identifiable
on 0/1065 rows" as a data problem AND silently moved the separation study's R
denominator off the setup's own invalidation. The test asserts every key or
attribute a consumer reads exists in what the producer ACTUALLY RETURNS —
checked against a real produced object, never a fixture, because a fixture
just re-encodes the assumption that was wrong. Then it asserts the DECISION,
since a key can exist and still not be consulted.

**F.21 — [DESK] ✅ `tests/ict_observe.py` v1.1.** Three fixes and a new
section. The raid-key bug above; the separation verdict printing **INVERTED**
for low −0.00R vs high −0.00R (a strictly-less-than test on two equal medians
— FLAT and INVERTED demand different responses, and calling a tie an inversion
is cry-wolf in the one section that decides everything), now a tolerance band
with the raw delta and a quartile profile; and READY-row zone reporting so
"formed with no dealing range" is quantified. **NEW §7 COMPONENT
DIAGNOSTICS** — per setup and component: availability, mean when available,
how often it met its floor, and the required component that blocked most
often. "SweepMSS never fired" is not actionable; "SweepMSS stalled on
dir:sweep, mean 0.00" is — and that is how F.19 was found.

**F.23 — [FLEET] 🔴 ICT GRADING WAS HOSTAGE TO ENTRY PERMISSION. ✅ SPLIT
2026-08-19 (main v6.24).** First live morning: **zero `ict_setup` rows**, with
the suite importing cleanly, raising nothing, and the journal healthy at
101 KB. Cause: v6.22 put the whole ICT branch inside `attempt_new_entry`,
which has FIVE early returns above the insertion point (daily-loss halt,
`session.can_enter`, stale regime book, chain-fetch failure, the UNKNOWN hard
gate) and is itself called only in an `else` — skipped entirely whenever a
position is open or condor legs are being managed. Grading only happened when
trading was already permitted.
That is backwards. The journal of FORMING states is the only data the priors
are ever fitted from, and it has to accrue on the ticks where we could NOT
have traded as much as the ones where we could — **a setup that formed while a
position was open is precisely the observation that tells us what the ranking
costs.**
Now split: GRADING (`build_context` + `evaluate_all` + `journal_setup_state`)
runs unconditionally in `run_regime_classification`, needs no options chain,
and journals regardless of entry permission. ACTION (`ict_dispatch`) stays in
`attempt_new_entry` and CONSUMES `ctx["ictx"]` rather than rebuilding it, so
the state journaled is the state the entry decision was made on. No ictx ⇒ no
dispatch.
🔴 **AND THE TEST CERTIFIED THE DEFECT.** `test_ict_wiring` v1.0 asserted "the
ICT dispatch call is inside attempt_new_entry" and reported it as a PASS —
pinning the shape of what was built rather than the property that was asked
for. **A test that confirms your own construction is worse than no test.**
v1.1 asserts the split, adds reachability checks (no early return precedes the
grading call; its function is not invoked from an `else` arm), and **fails
with 5 red cases against the pre-split code** — verified by reverting the
block and re-running.

**F.24 — [FLEET] 🔴 THE SMC CORE SILENCED THE LEGACY STACK. ✅ UNTANGLED
2026-08-19 (main v6.25 / config v4.22).**
**What happened.** 09:35 ORB range established 719.28–721.50. 09:37:04 a 1-min
CLOSE at 718.66 broke the low. 09:40:04 the engine invalidated it — *ran to
50% TP without retest, runaway breakout*. The runaway handoff was reached and
**CNT.6 refused it, correctly on its own terms**, because the committed label
said RANGING and "a continuation needs a trend to continue". A nine-point
directional move went untraded by anything.
**The premise was wrong, not the reasoning.** The SMC core had labelled the
session **RANGING at conviction 1.00** — every structural condition for
RANGING satisfied — while the v1.3 classifier read **BREAKOUT_VOLATILE 0.75**
on the identical ticks. The label did not reach TRENDING_BEAR until 11:49 ET,
two hours after the move: the lag pathology this fork exists to escape,
reproduced by its replacement.
**The fix is separation, not a patch to CNT.6.** Making CNT.6 respect the
runaway flag again would reopen the squeeze the 2026-08-10 change closed and
would treat a strategy that reasoned correctly as the culprit.
(1) `SMC_OVERRIDE_LABEL` **defaults OFF**. LEGACY reads `regime` (L2/v13,
identical to the parent fleet — which also restores the A/B against SPX).
SMC/ICT reads `ctx["smc"]`: structure, not the label.
(2) **The two stacks compete for the entry slot**, mutually exclusive at the
POSITION level, each stand-down NAMED —
`blocked_by_legacy_trade_active` / `blocked_by_smc_trade_active` — and
journaled with the refused signal, so "what did the other stack cost this
one?" is a query rather than a guess. Ownership resolves BY PREFIX from the
LIVE open records, because a restart rehydrates positions from the DB and any
in-process memory of who opened them is gone.
`tests/test_stack_separation.py` v1.0 pins all four properties (no override by
default AND the assignment nested under the flag — a flag that exists is not a
flag that is consulted; prefix ownership incl. an unknown future strategy;
both refusals named; the legacy block ahead of the ladder) with a
deliberate-failure mode.
⚠️ **STILL OPEN — the labeller itself.** Untangling stops the damage; it does
not explain why a runaway breakout reads RANGING at 1.00. First suspect from
the 09:30 `smc_setup` row: range 715.92–734.58 (19 points) on a session whose
opening range was 2.22 — the dealing range is anchored to overnight swings, so
intraday displacement is measured against a window in which nothing looks
large (`displacement_sd: 0.0`). Testable against today's tape tonight.

**F.25 — [FLEET] 🔴 EVERY 1h CANDLE WENT TO THE WRONG SYMBOL FOR SIX DAYS.
✅ FIXED 2026-08-20 (candle_feed v3.16). SHIPS TO BOTH REPOS — the file is
byte-identical in each, so the defect and the fix are shared.**
`symbol_map` was keyed on `(dx_symbol, interval)`, and FEED.2 subscribes the
same symbol at the same interval TWICE — RTH and extended. The second
registration overwrote the first, so the single ingest lookup could not tell
the echoes apart and **every 1h bar landed under `*_EXT`**. Measured: plain
`QQQ` 1h newest **2026-08-14 19:00**, plain `SPX` 1h newest **08-14 20:00**,
both `*_EXT` current. 1h feeds `structure_analyzer`'s swings and S/R, the
pitchfork and its observer, and `entry_snapshot`.
⚠️ **THIS INVALIDATES THIS WEEK'S SMC DIAGNOSES.** The cutover was 08-18; the
1h froze 08-14. **The SMC core has never once run on current higher-timeframe
structure.** The RANGING-at-conviction-1.00 call that suppressed the 08-19
runaway, the frozen dealing range (`range_high: 0.0`), the absent displacement
(`displacement_sd: 0.0`) — all downstream of six-day-old swings. F.24's
untangle remains correct for its own reasons (neither engine should be able to
silence the other), but the diagnosis of WHY the label was wrong was built on
rotten input and was stated more confidently than the evidence supported.
⚠️ **Nothing raised.** `BLIND BARS_STALE … refused=False` warned every five
minutes for six days and the fleet traded on it. The alarm worked; nobody was
reading it. That is a separate finding and it belongs on the review list.
FIX: the map key carries the extended-hours flag; the router reads `tho=true`
off the echoed symbol — the attribute `_interval_of` deliberately discards is
exactly the one the router needed. GUARD: the feed REFUSES TO START on a
duplicate route key, a routeless subscription, or two subscriptions writing
one `(store_symbol, interval)`. `tests/test_candle_routing.py` proves both
directions route and goes RED against the old two-part key.
⚠️ **SECOND HALF (candle_feed v3.17 + tools/segregate_nonrth_bars.py).** After
v3.16 streaming routed correctly, but the restart's BACKFILL asked for
plain-symbol history and DXFeed returned **24-hour bars anyway** — ~12/hour
overnight vs 38–39 in RTH, reaching back to 2026-08-05. **SPX is the control
proving it is genuine extended-hours data rather than a timezone or DST
artifact:** an index has no overnight session, so it shows hours 13–20 UTC
only and had nothing to contaminate.
**Worse than the original hole** — a gap announces itself, this does not. The
series CHANGES CHARACTER MID-STREAM (07-31 RTH-only, 08-19 24-hour) with
nothing marking the seam, and `structure_analyzer`'s swings and S/R (weight
**2.0**, the heaviest structural input), the pitchfork's 1h fractals,
`trend_engine`'s 0.20 context vote and `entry_snapshot` all read across it.
ADX is unaffected — v1.1 sourced it from 5m precisely because 1h lagged.
The vendor flag was passed and ignored (`extended_trading_hours=False`, 24h
history returned regardless), so the guarantee lives at the WRITE.
⚠️ **SEGREGATED, NOT DELETED** — `EXT_INTERVAL` is 1h ONLY, so an overnight
5m/15m/1m bar is the only copy that will ever exist and DXFeed history is
use-it-or-lose-it; deleting to protect the RTH series would trade one
irreversible loss for another. Non-RTH rows move to `<SYM>_EXT`: the RTH
series is pure again for the consumers built to read it, and every bar stays
queryable. Destination collisions are REPORTED, never merged.
⚠️ History is not repaired — plain-symbol 1h from 08-14 to the deploy is gone;
DXFeed history is use-it-or-lose-it. Restart backfill refills what the API
still serves.

## PART 3 — RESOLVED REGISTER
- **P0 ctx NameError (main v6.18, 2026-08-18).** v6.16/v6.17 wrote
  `ctx["gap"]`/`ctx["level_near"]` before `ctx` existed; the handler re-raised;
  run_analysis failed EVERY tick. Fixed at the fork; **flagged to the operator
  for the parent repo, which still carries it at `0720753`.**
- **Setup self-revocation (smc_engine v1.0 pre-ship).** The raid bar's own
  break revoked the setup one bar after formation; fixed with the
  shift-postdates-setup rule. Caught by the behavioral suite before live.
- **Chop printing TRENDING (pre-ship).** Latched 15m direction + AWARE-tier
  displacement let range rotations label as trend; fixed (unlatched 15m read,
  CONFIRM-tier necessary condition). Caught by test E2.

## PART 4 — CHANGELOG
- **v1.15 — 2026-08-20** — F.25 second half: candle_feed v3.17 RTH guard
  (segregates non-RTH bars to <SYM>_EXT rather than dropping them, because
  5m/15m/1m have no extended stream) + tools/segregate_nonrth_bars.py for the
  rows already written.
- **v1.14 — 2026-08-20** — F.25: candle_feed v3.16 fixes the FEED.2 route
  collision that sent every 1h bar to *_EXT for six days fleet-wide; this
  invalidates the week's SMC labeller diagnoses, which ran on 08-14 structure.
- **v1.13 — 2026-08-19** — F.24: stacks untangled (main v6.25, config v4.22)
  after the SMC core's RANGING-at-1.00 call suppressed a nine-point runaway;
  they now compete with named mutual exclusion. The labeller defect itself
  remains open.
- **v1.12 — 2026-08-19** — F.23: grading split out of the entry path (main
  v6.24) after a live morning of zero journaled setups; test_ict_wiring v1.1
  re-pinned to reachability and proven red against the old shape.
- **v1.11 — 2026-08-19** — F.19 sweep evidence revived (primitives v1.1 +
  liquidity_mapper v4.2), F.20 key-contract test, F.21 observe v1.1 with
  component diagnostics.
- **v1.10 — 2026-08-19** — F.18: MAX_LOSS_PCT 0.25 and ORB blocked in RANGING,
  both mirrored to options_trader_v3 the same day for A/B integrity.
- **v1.9 — 2026-08-19** — F.17: exit_engine v4.23 adds `_evaluate_ict` so the
  suite's own invalidation is finally read; tests/test_ict_exit.py pins it and
  fails against the old router.
- **v1.8 — 2026-08-19** — F.16: tests/ict_observe.py v1.0 built (six
  pre-registered criteria, separation direction pinned in code). Found the
  sentinel-forming defect on its first run.
- **v1.7 — 2026-08-19** — F.15: G6 (main v6.22 pre-ladder ICT dispatch) and G8
  (config v4.20 registrations + 11:30 cutoff) BUILT, with
  tests/test_ict_wiring.py. The suite is now reachable; nothing is armed.
- **v1.6 — 2026-08-18** — F.13 ICT setup suite BUILT (strategy/ict/ v1.0:
  seven ranked continuous scorers, ICT-only sizing, three closed-by-default
  fire gates, tests/test_ict_setups.py) with docs/ICT_CORE_SPEC.md v1.0
  recording core gaps G1–G8 as REQUESTED; F.14 (afternoon credit expression)
  opened, gated on measured wants_credit demand.
- **v1.5 — 2026-08-18** — F.12 opened with the acceptance-replay harness BUILT
  (backtest_harness v1.3 + tests/test_harness_smc_mode.py); the run itself and
  its pre-registered pass condition are recorded as owed.
- **v1.4 — 2026-08-18** — F.11 opened and closed the same day: L1 hoisted out
  of the L2 branch (main v6.21) with an AST scope test; the SweepReversal
  arming decision recorded as owed.
- **v1.3 — 2026-08-18** — F.10 upstream port ledger opened; TC.6 v1.5 ported
  from parent `2cae11b` (trend_credit_spread v2.2, test_tcs_exit v1.1). Two
  parent-side defects recorded for upstream: a stale file header and a guard
  suite left red by that commit.
- **v1.2 — 2026-08-18** — F.2a BUILT (trade_logger v3.16 + main v6.20 +
  tests/test_engine_provenance.py) and marked so; F.2's remaining steps are
  now purely operational. Control-side bake/repoint guards recorded as F.9,
  shipped separately against day_trader_pro — they cannot live in this repo.
- **v1.1 — 2026-08-18** — CANDIDATE CHANGED META → QQQ (operator's decision;
  SPX remains a legacy daily trader). F.2 rewritten from "provision a box" to
  "convert the existing box, in this order", with F.2a (trade-row engine
  provenance) as its blocking first step. F.3 largely dissolved — an existing
  box is not virgin. F.6 split into the sequential and concurrent comparisons
  with their confounds named. Fleet-bake hazard recorded in WA §26.
- **v1.0 — 2026-08-18** — document created with the fork. F.1 BUILT; F.2–F.8
  open; deferred items gated by name; three pre-ship defects on the record.
