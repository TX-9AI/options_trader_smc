# docs/BACKLOG.md — options_trader_smc — v1.3

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

## PART 2 — DEFERRED, WITH THE GATE NAMED
- **Sizing on structural confidence** — gated on the parent transition
  roadmap's five Phase-2 preconditions. Not before.
- **HTF (1h/1d) structure state in the core** — gated on F.3 depth landing;
  a vote cast on a starved frame is not the vote a warm frame casts.
- **CONFIRMED-setup fast-path entries** (a dedicated SMC strategy rather than
  relabeled gates) — gated on F.5 passing and F.4 fitted bounds.
- **Killzone-conditional gating** — journal first; the windows already gate.

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
