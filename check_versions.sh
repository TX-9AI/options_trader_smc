#!/bin/bash
# v4.54 — 2026-08-17 — TCS.3 (main v6.12): the trend-participation bound now
#         reads TODAY'S 09:30 5m bar — the 1m-only version lost its source
#         bars at ~10:35 ET, 25 min before the credit window opened, so TC.6
#         could never fire (fleet-verified before fixing). Canary greps the
#         5m-primary branch, never a version string.
# v4.53 — 2026-08-15 — AUDIT A2 (mapper v4.1, ledger v1.1, main v6.11,
#         position_manager v3.3): behavior canaries for the audit-2 fix set —
#         section truncation guard + DST-derived NY hours, the deep named
#         frame wired into analyze, the gap-safe ledger feed + restart
#         hydrate, the orphan announcement in the MANAGE branch (the only
#         branch that runs with a leg open), and an ABSENCE canary on the
#         dead session-pool knob (assignment pattern, so changelog mentions
#         of the bare name stay legal — the SWP.1 lesson).
# v4.52 — 2026-08-14 — AUDIT F1/F2/F4/F6 (exit_engine v4.21, main v6.9,
#         position_manager v3.2). Five canaries, every one guarding a defect
#         that was REPRODUCED AT RUNTIME while 162 text-based tests stayed
#         green: the structure IMPORT (without it, NameError on every condor
#         tick and a ~7.5-min crash loop), the DISPATCH routing credit
#         verticals by structure (without it, every new TC.6 record is managed
#         by the DEBIT sweep evaluator with sign-inverted P&L), the F4 seed
#         guard 0<persisted<base_stop (without the bound the restart seed
#         would adopt stale/foreign trail values as a ratchet), the TC.6
#         is_condor_leg=0 conditional (without it TC.6 rows spoof
#         _condor_sibling_open and condor_roll), and position_manager pricing
#         by structure (without it, main v6.9 makes TC.6 premium fetch fall to
#         the single-leg path — the paired-commit hop).
#         ⚠️ TITLE DRIFT FIXED: this file's title read v4.46 while its newest
#         changelog entry was v4.51 — five bumps recorded below the line that
#         claims the version. Same failure class as the devtools banner.
# v4.46 — 2026-08-11 — LIQ.1 + SWP.4. Three canaries, all guarding SILENT
#         failures: the dedupe tiebreak (losing it empties swept_named_level
#         and the SWEEP score becomes exactly 0.000, with no error anywhere),
#         the session-pool gate (London overlaps RTH by 2.5h, so its level is
#         set by the price being traded), and the recovery anchor (from the
#         wick, a deeper rejection reads as a farther entry).
# v4.51 — 2026-08-12 — OBSERVER DEBT. Two canaries pin the EVALUATION DATE into
#         the code itself: a backlog entry can be skimmed, a module docstring is
#         read by whoever next touches the file. Zero firings by 08-14 means
#         DELETE, not "leave it running".
# v4.50 — 2026-08-12 — VEL.1 velocity stall. The load-bearing canary is the
#         BREACH COUNTER in __init__: without it the check AttributeErrors on
#         first call, the except swallows it, and the whole mechanism is a
#         permanent SILENT no-op that still looks shipped. Also pins the ladder
#         ORDER (theta_bleed before velocity) and current_delta being stashed.
# v4.49 — 2026-08-11 — PF.2 containment anchor + weight-0 observer. The
#         load-bearing canary is the §4.4 CONFIRMATION LAG guard: without it the
#         builder returns forks anchored on information that did not exist when
#         P2 printed, nothing errors, and every backtest result from them is
#         fiction. Also pins the 1d frame depth — the boxes hold 84 daily bars
#         and the engines were being handed 10.
# v4.48 — 2026-08-11 — RGM.6. The load-bearing canary is the L1-argmax rung
#         itself: without it the fallback silently reverts to v13 and UNKNOWN
#         climbs back to ~18% with nothing erroring. Also pins the four-state
#         engine tag, because [v13] has been the fallback-rate measure and a
#         collapse back to two states makes that number mean something else.
# v4.47 — 2026-08-11 — LIQ.1 + LIQ.3 + SWP.4 + SWP.5. Six canaries, every one
#         guarding a SILENT failure: the dedupe tiebreak (losing it empties
#         swept_named_level and the SWEEP score is exactly 0.000, no error), the
#         session-pool gate (London overlaps RTH by 2.5h so its level is set by
#         the price being traded), the recovery anchor (from the wick, a deeper
#         rejection reads as a farther entry), and the running liveness check
#         plus its bounded backstop (without them the gate reverts to a clock
#         that discarded 32.9% of still-live theses).
# v4.45 — 2026-08-11 — CNT.7 confirmation tolerance. The canary pins the ATR
#         form, because the failure mode is a SILENT NO-OP: a tolerance too
#         small to admit any real tie leaves the gate exactly as strict while
#         looking fixed. My first draft was 0.05 and did precisely that.
# v4.44 — 2026-08-11 — BFLY.1 butterfly readiness rewritten around the pin.
#         The load-bearing canary is the ABSENCE of `coil` from hard_vetoes.
#         `_combine` treats hard_vetoes as a ZERO TEST, so restoring it there
#         changes NOTHING on a COMPRESSION or RANGING tick and only bites where
#         coil_val is exactly 0 — which is why the first version of the test
#         could not fail. Pin the corroborator form instead.
# v4.43 — 2026-08-10 — CV.1 CLOSED. The orphaned condor_plan_lifetime canary is
#         removed with its reasoning inline, and this file reports ALL GREEN on
#         a clean checkout for the first time in weeks. That matters more than
#         the one check: a permanently-red sweep trains the reader to skip its
#         own DONE banner, at which point every OTHER canary here stops working
#         too. Also adds the VW.1f pins.
# v4.42 — 2026-08-10 — RGM.4 per-regime commit bar. Two canaries: the override
#         map itself, and the ARMING site using the challenger's own bar. If
#         either reverts to the global theta_commit, RANGING goes quiet again
#         with no error — it reads as "no ranges today", which is exactly how it
#         hid for weeks.
# v4.41 — 2026-08-10 — CNT.6 continuation blocked in the premium regimes. The
#         canary pins the NEGATED form (`not _cont_blocked`) because restoring
#         the bare `_is_runaway or ...` bypass raises NOTHING — butterfly and
#         condor simply go quiet again, which reads as "no setups today" rather
#         than as a regression. That is the failure this file exists for.
# v4.40 — 2026-08-10 — sweep readiness approach (trade_readiness v1.7). The
#         load-bearing canary is the ABSENCE of a label hard-veto: `is_sweep`
#         back in hard_vetoes returns the whole track to a permanent zero and
#         NOTHING ELSE BREAKS — no error, no log, exactly how it sat dead for
#         two days. Also pins the shadow-FITTED ramp bounds, because 0.15/1.20
#         put the median tick at zero and the factor was dead on 3/4 of the
#         session.
# v4.39 — 2026-08-10 — BOS minimum distance (exit_engine v4.15). Two canaries
#         carry the weight: the RATCHET (max/min), because low-min_dist is not
#         monotone and losing it slackens the stop as volatility widens; and the
#         min_dist==0 branch, because if that stops being byte-identical the
#         kill switch silently stops being one.
# v4.38 — 2026-08-10 — continuation 1-bar confirmation (v1.5). Pins the gate,
#         the knob, and — the one that matters — the REFUSAL on an undecidable
#         confirmation. Falling through on thin tape would restore the
#         unconfirmed entry invisibly and only sometimes, which is the worst
#         shape a regression can take here.
# v4.37 — 2026-08-08 — sweep spent-move (regime_confluence v1.4) + L1 evidence
#         on the fired disposition (main v5.9). The LOAD-BEARING canary is
#         `soft_necessary=.trend_opp, age_decay.` — if trend_opp ever leaves
#         that list a high ambient score can rescue a sweep fighting an
#         accelerating opposing trend, and the 2026-07-27 PLTR loss re-opens.
#         Also pins the deliberate absence ASYMMETRY: "" must NOT suppress
#         (opp_mom 0.6) and must NOT corroborate (exh_val 0.0). Making those
#         symmetric in EITHER direction is a regression, so both are pinned.
#         NOTE the bracket form is escaped — grep reads [..] as a character
#         class, which silently matched a single char on the first attempt.
# v4.36 — 2026-08-08 — `dir` on every readiness track (trade_readiness v1.6).
#         Four canaries, and the load-bearing one is the CONDOR EXPOSURE
#         mapping: a call credit is SHORT, which is the inverse of the intuitive
#         call=long reading. Inverting it would flip every condor row in the
#         orientation ledger while the output still rendered perfectly — the
#         wrong-answer-that-looks-right class this file exists to catch. Also
#         pins sweep's dir to the LIVE liq_map source (unrecoverable offline)
#         and butterfly's explicit "neutral", so sideless-by-design can never
#         again be mistaken for a field that was never written.
# v4.35 — 2026-08-05 — VWAP reaches the journal. volatility_engine has computed
#         vwap/price_vs_vwap all along and nothing persisted them — a key scan of
#         11,138 records found no VWAP field anywhere, which is why
#         vwap_orientation has never run. The canary pins the EMIT, not just the
#         helper: a value computed, available and never written is exactly the
#         failure being fixed.
# v4.34 — 2026-08-05 — readiness_digest v1.2: the headline pegged count and the
#         FIT SUGGESTIONS list now measure the SAME thing (ramped output). They
#         disagreed, and the headline is what people act on.
# v4.33 — 2026-08-05 — A2 becomes a BANDED METRIC. It had failed every session
#         since the harness existed (16 diary sessions, all 4/5) because the
#         invariant was wrong, not the engine: TRENDING reads ~70min and RANGING
#         ~25min, so both scoring high is a real state. A permanently-failing
#         check hides a NEW failure — the canary pins the band so nobody quietly
#         reverts it to `both == 0`.
# v4.32 — 2026-08-05 — conditional_tables v1.6 DE-DUPLICATES. The box DBs are
#         cumulative and the harvest copies them into every dated folder, so the
#         same trade was counted once per subsequent day. trade_id was not even
#         SELECTed. Inflated n makes Wilson intervals too NARROW — cells look
#         decisive when they are not.
# v4.31 — 2026-08-05 — conditional_tables v1.5: the trade-DB glob had NEVER
#         matched a file, and an empty load printed a statistical verdict. Both
#         canaries are absence-shaped in spirit — the failure mode is a tool that
#         runs clean, exits 0 and reports a null on a corpus it never read.
# v4.30 — 2026-08-05 — conditional_tables v1.4 reports SESSION SPREAD. The 08-05
#         headline named a starve candidate at n=48 with an interval excluding
#         50%, and the tool could not say whether that was eight sessions or two
#         bad days. The canary pins the DATE REACHING Cell.add, not just the
#         flag: dropping it leaves every cell claiming to be a standing pattern
#         and raises nothing.
# v4.29 — 2026-08-05 — W.2b: the three TIER-1 handlers the 2026-08-05 census
#         flagged now log inline. All three shipped the previous evening, hours
#         after the W.2a lesson was written down — the census caught them in one
#         cycle, which is the system working. Canaries pin the log calls, not
#         the handlers: the swallow is correct in all three cases, the SILENCE
#         was not.
# v4.28 — 2026-08-04 — N.9 contract telemetry. Canaries pin the OCC-symbol match
#         and BOTH fill seams: matching on strike would attribute one condor
#         leg's greeks to the other, and a condor leg that skipped the capture
#         would be invisible in the decomposition while still appearing in P&L.
#         Neither failure raises anything.
# v4.27 — 2026-08-04 — +2 canaries for the condor plan-lifetime audit and the
#         corrected DIRECTIONAL_ONLY comment. The stale comment claimed single
#         names were skipped; the config has enabled every box since 07-14, and
#         reading the comment instead of the value cost an investigation.
# v4.26 — 2026-08-04 — candle_feed v3.11 collapses both RTH checks into ONE
#         predicate, and pull_today_ohlc v1.5 restores its guard to ON now that
#         the real cause (v3.10) is fixed. The canary counts CALLS to the
#         predicate rather than matching a condition: three independent clock
#         checks in a chain is what caused the outage, and a fourth written by
#         hand is what this prevents.
# v4.25 — 2026-08-04 — candle_feed v3.10: `--once` exempt from BOTH RTH gates.
#         THE ABSENCE CANARY IS THE POINT — a bare `if not is_rth():` inside
#         run() is the v3.9 form, and it hangs every EOD candle retrieval with
#         no exception, no non-zero exit and an INFO line. It cost two sessions
#         of sat-out tape, and DXFeed history is same-evening only.
# v4.24 — 2026-08-04 — pull_today_ohlc v1.4: the RTH guard is OFF BY DEFAULT per
#         operator directive, gated on OT_PULL_RTH_GUARD. The canary now pins
#         the KNOB rather than the condition — the refusal path still exists and
#         must stay correct for when it is switched back on.
# v4.23 — 2026-08-04 — pull_today_ohlc v1.3: the RTH guard now requires a LIVE
#         OPTIONSBOT, not just the clock. +2 canaries, one of them an ABSENCE
#         check on the v1.1 condition — the old form silently wrote header-only
#         csvs for every sat-out box backfill woke, and DXFeed history is
#         same-evening only, so a revert costs a session of tape per night with
#         no error anywhere.
# v4.22 — 2026-08-04 — +3 canaries: a2_cooccurrence v1.2's parse-time slim (the
#         OOM that SIGKILLed devtools 47 with no traceback and no output) and
#         the audit v1.5 ACCEL-per-held-bar denominator. The slim canary pins
#         _KEEP by name because a future analysis reading a dropped field does
#         not crash — it reads None, and the tool prints a clean table
#         describing nothing.
# v4.21 — 2026-08-04 — main v5.4: ORB EXEMPT FROM THE STALE ENTRY GATE, +3
#         canaries and the header re-pinned. v5.0's block sat ABOVE the dispatch
#         so ORB_FIRES_REGARDLESS_OF_REGIME was unreachable on a stale tick, and
#         the fleet lost 09:35-09:41 of the flagship's window every session since
#         it deployed. The ABSENCE canary is the load-bearing one: the v5.0
#         unconditional form returns before ORB is ever consulted, raises
#         nothing, and shows up only as fewer morning trades.
# v4.20 — 2026-08-04 — +2 canaries for pitchfork_filter_audit v1.4's variant
#         sweep. The load-bearing one pins that `variant` is THREADED to the
#         replay: swallow it and the sweep still prints a clean three-row table,
#         three runs of one variant wearing three labels. A comparison that
#         silently compares nothing is worse than no comparison.
# v4.19 — 2026-08-04 — tcs_floor_durability v1.3: +2 canaries on the MATCHED
#         CONTROL. Every rate this tool printed before v1.3 was an absolute with
#         nothing to beat — in a trending tape a recent extreme survives
#         terminally most of the time regardless. Losing the control does not
#         error; it restores a number that looks like a result and is a fact
#         about the tape. The DRAW is pinned separately from the flag, because a
#         fixed anchor satisfies determinism while measuring nothing.
# v4.18 — 2026-08-04 — tcs_floor_durability v1.2: +2 canaries on the TERMINAL
#         split. v1.1 measured INTRADAY violation, which is not what a
#         defined-risk 0DTE spread loses on — it expires on the close. Collapsing
#         terminal back onto intraday would restore an 82% "failure" rate for
#         trades that would have expired fine, so the terminal test and the
#         strike curve are both pinned by name.
# v4.17 — 2026-08-04 — tcs_floor_durability v1.1: +2 canaries on the POPULATION
#         FILTER. v1.0's first real run measured every floor the rolling
#         lookback ever computed instead of the ARMED ones the strategy would
#         have traded — 5,129 "impulses" that were mostly arithmetic. It did not
#         error and it did not look wrong; it answered a question nobody asked.
#         The default is pinned to ARMED and the DORMANT-exclusion is pinned by
#         name, because reverting either restores a confidently wrong number.
# v4.16 — 2026-08-04 — +2 canaries for tcs_floor_durability v1.0 (TC.4b's
#         prerequisite). The DEDUP one is load-bearing: the readiness track
#         scores every tick, so one impulse appears on hundreds of consecutive
#         journal rows. Losing the dedup key does not error — it reports a
#         sample size that does not exist and weights a long-lived impulse
#         hundreds of times, which is a confidently wrong answer rather than a
#         missing one.
# v4.15 — 2026-08-04 — +3 canaries for gap_outcome_join v1.5 (--pool gapflat).
#         The pooled cell and its legitimacy verdict are ONE feature: pooling
#         two arms that disagree manufactures a null from two real opposite
#         effects, and the pooled table cannot show it. A sync that kept the
#         flag and dropped the verdict would be worse than one that dropped
#         both, so the verdict is pinned by name.
# v4.14 — 2026-08-04 — labels are BULL/BEAR and the map is SHARED. The same
#         truncation defect was found in tests/replay_confluence.py (the
#         nightly emitted-distribution line the freeze watch reads) and in
#         regime_confluence's self-test. Canaries now pin the shared map and
#         each consumer of it, because fixing one renderer leaves the next free
#         to invent its own abbreviation.
# v4.13 — 2026-08-04 — +3 canaries for regime_diary v1.3. The ABSENCE check is
#         the load-bearing one: `k.split('_')[0][:4]` collapsed TRENDING_BULL
#         and TRENDING_BEAR into the same token for 16 sessions and nothing
#         failed — no error, no test, a report that simply could not express
#         the distinction. A revert would be equally silent.
# v4.12 — 2026-08-04 — main header pin v5.2 -> v5.3, and +3 W.2a canaries. The
#         pin FAILED on its own during the W.2a pass, which is the point of
#         having it: a version bump that nobody re-pins is how the pin sat at
#         v4.8 while the fleet ran v5.0.
# v4.11 — 2026-08-04 — +3 canaries for main v5.2 (no regime-flip exit on a
#         stale book). The ABSENCE check is the one that matters: the gate is a
#         single argument, so a stale sync reverting it produces NO error and NO
#         log line — exits simply start firing on unconfirmed labels again, and
#         the only visible symptom would be regime_flip hold-times creeping back
#         down weeks later in flicker_audit. Also pins the main header to v5.2.
# v4.10 — 2026-08-04 — +6 canaries for N.5 exit-ladder latency (exit_engine
#         v4.11 / trade_logger v3.11). The load-bearing one is the ABSENCE
#         check on the confirmed-guard: writing telemetry on an UNCONFIRMED
#         pass books the fast final leg of every slow close, which is the exact
#         population the TC.2 stop-trigger decision is measured on — a silent
#         corruption of the answer rather than a missing column. Found by
#         running the deliberate-failure check, not by reading the code.
# v4.9 — 2026-08-04 — +7 canaries for the ENTRY SNAPSHOT (main v5.1 /
#         trade_logger v3.10 / analysis/entry_snapshot.py v1.0), and the stale
#         main-header pin corrected: it still read v4.8 while the fleet ran
#         v5.0, so the one check whose whole job is "is main current" had been
#         green on a two-version drift. Now pinned to v5.1.
#         The load-bearing canary is the ABSENCE one on the condor call sites.
#         The capture is log-only, so if a stale sync drops the ctx argument the
#         condor legs simply stop being captured — no error, no alert, and the
#         column keeps filling from the directional path, which is exactly what
#         a working capture looks like. Nothing else in the repo can see that.
# v4.8 — 2026-07-30 — +4 canaries for main v4.8: the opening warm-up now logs
#         INFO rather than a WARNING that fired on 13/15 boxes every morning for
#         designed behaviour, and regime_log/trades carry the engine that
#         produced each label. The engine stamp is the one that matters most —
#         without it, "which engine labelled this row" was answerable only by
#         grepping bot.log, and the designed v1.3 opening window could not be
#         excluded from an L2-conditioned fit.
# v4.7 — 2026-07-29 — REACHABILITY CANARY. main v4.7 fixed the real 07-29 root
#         cause: `_REGIME_ENGINE` is .lower()ed to "l2" while both gates compared
#         it to "L2", so L2.5 never executed once on any box since v4.0 wired it.
#         An absence canary now fails if the uppercase literal returns, plus a
#         presence check on the startup engine-identity line. This is the canary
#         that would have caught it: no test, no log line and no alert could,
#         because a gate that never opens raises nothing.
# v4.6 — 2026-07-29 — +2 canaries for main v4.6's audible L2 gate, and the
#         version-pinned main header moved to v4.6. The gate matters because a
#         probe showed L2 CAN commit (tick 1, conviction 0.984) while production
#         may still print [v13] indefinitely from starved evidence — with no log
#         line at all before v4.6.
# v4.5 — 2026-07-29 — L2.5 IMPORT-CONTRACT CANARIES + absence-loop counting.
#         Adds 3 presence checks and 1 absence check pinning main.py v4.5's
#         corrected L2 import and the v1.7 degraded-engine pager, after an
#         ImportError swallowed by the L2 guard put all 15 boxes on the v1.3
#         classifier for a full session. Also fixes a defect in v4.3's own
#         banner: the regime_confluence ABSENCE loop printed ✗ STALE without
#         incrementing MISS, so a restored fabricated fallback would have
#         reported "ALL CANARIES GREEN". Absence failures now count.
# v4.4 — 2026-07-29 — GLYPH FIX (legibility, no logic change). Every status
#         line printed a literal "\u2713 PRESENT" / "\u2717 MISSING": bash's
#         echo does not interpret \u escapes, so the check/cross glyphs have
#         never actually rendered — inherited defect, present since the marks
#         were introduced, caught on the first control-side run of v4.3. Now
#         literal UTF-8 characters. Matters most for the v4.3 banner: 15 boxes
#         of output are meant to be scanned, and a wall of \u2717 defeats that.
#         Grep note: `grep '✗'` now works; `grep MISSING` always did and is
#         still the encoding-proof form for fleet passes.
# v4.3 — 2026-07-29 — PARITY INVARIANT (closes the last open piece of audit
#         defect U). New section after GIT STATE: compares this checkout's
#         HEAD to origin HEAD via ls-remote — RED on mismatch (a box running
#         stale code passes every fingerprint if its files are internally
#         consistent; only the commit comparison catches "consistent but
#         old"). Origin unreachable = WARN not FAIL (boxes may check while
#         offline); dirty tracked files = WARN (fingerprints on a modified
#         file prove nothing about origin). Also: MISSING/PARITY failures now
#         counted and summarized on the DONE banner, so option-23 fleet output
#         is one greppable line per box instead of 125. Exit code deliberately
#         still 0 — callers' semantics unchanged.
# v4.2 — 2026-07-28 — +5 canaries: trade_readiness v1.2 (all factor bounds
#         OT_TR_* overridable — parity with OT_RC_*) and readiness_digest v1.1
#         (factor calibration + fit suggestions).
# v4.1 — 2026-07-27 — +3 canaries: trade_readiness v1.1 staged picks, main
#         v4.4, tests/readiness_digest.py (conductor phase-9 target).
# v4.0 — 2026-07-27 — +6 canaries: trade_readiness v1.0 engine + main v4.3
#         every-tick hook (LOG-ONLY readiness workstream).
# v3.9 — 2026-07-27 — +1 canary: regime_confluence v1.3.1 compression
#         containment veto (the A3 squeeze-break fix the A/B pool surfaced).
# v3.8 — 2026-07-27 — CONFLUENCE EXCAVATION CANARIES. Adds 11 presence checks
#         and 4 ABSENCE checks for regime_confluence v1.3, plus 2 VALUE-pinned
#         checks for the config v4.0 sweep strike floor. The absence loop is the
#         load-bearing half: v1.3 was mostly about REMOVING terms (two constant
#         corroborators, two fabricated no-window fallbacks), and a stale sync
#         that restores them keeps every constant NAME intact while silently
#         reverting the behaviour. The v1.3 changelog was deliberately written
#         WITHOUT naming those four identifiers so these bare-token greps stay
#         honest — the changelog-prose trap has re-tripped absence canaries twice
#         (_orb_quality, then again during this pass before it shipped).
# v3.7 — 2026-07-23 — HEADER-AUDIT LABEL CORRECTIONS (no canary logic change):
#         risk_manager's 2026-07-23 full-budget entry relabeled v1.4 -> v3.2
#         (the file was already at v3.1); butterfly's 2026-07-14 discount gate
#         v1.4 -> v3.2; status.py's duplicated v1.12 (2026-07-20) -> v1.13.
#         Prose references below updated to match. Fingerprints unchanged.
#         BONUS CATCH: the half_budget absence canary was legitimately RED —
#         risk_manager's success-path log still referenced the deleted
#         half_budget variable (NameError on every successful condor-leg
#         sizing). Fixed as risk_manager v3.3; canary now green.
# v3.6 — 2026-07-23 — chain-archival fingerprints. A stale sync silently stops
#         archiving option chains, and chains cannot be backfilled — every
#         un-archived session is a permanent hole in the dataset.
# v3.5 — 2026-07-23 — condor v2 fingerprints (exit_engine v4.1, risk v3.2,
#         iron_condor v3.2, 11:11 gate). A stale sync silently restores the
#         un-ratcheted stop (every stopped leg round-tripped from ~+25% to
#         -25%), the half-size verticals, the leg-2 CANCEL, or the 11:00 window
#         that runs on a bb_middle=current_price fallback.
# v3.4 — 2026-07-22 — continuation EXIT-rework fingerprints (exit_engine v4.0):
#         5m-anchored trail, theta-bleed enabled, 25%% backstop. A stale file
#         silently reverts to 1m tripwire trails and NO theta protection.
# v3.3 — 2026-07-22 — continuation-unblock fingerprints (defect W). Pins that
#         TrendState surfaces primary_momentum and that the strategy READS it
#         — a stale sync of either file silently re-blocks the trade forever
#         with no error and no log, which is exactly how it hid for 4 days.
#         Also an ABSENCE check on the phantom "STEADY" value.
# v3.2 — 2026-07-22 — ORB geometry-gate fingerprints (setup_scorer v1.4).
#         Pins that the ORB grades via _grade_orb (liquidity-in-path A/B only)
#         and that _orb_quality is GONE — a stale file would silently restore
#         the regime/VWAP/macro-weighted ORB score that could veto a confirmed
#         break. Absence-check on _orb_quality is inverted (see below).
# v3.1 — 2026-07-22 — CANARY GAP CLOSED (audit defect U). Before this the
#         newest fingerprint was dated 2026-07-18: a stale sync of ANY file
#         shipped 07-20 → 07-22 (orb v3.9, sweep v3.2, main v4.0/v4.1,
#         regime_confluence v1.2, the whole limit_ladder execution change,
#         status v1.13) passed this check silently — the exact failure mode
#         this script exists to catch, and the one that caused the 07-16
#         unmanaged-position incident. Adds 16 fingerprints covering every
#         post-07-18 change, and pins the two VALUES (not just the names)
#         that a stale file would revert: the de-saturated ramp bound and the
#         paper-friction default.
# v3.0 — 2026-07-10 — repo-wide v3.0 bump: Yahoo-Finance purge & data stream
#         mapping optimization (single shared TastyTrade candle feed). No
#         logic change in this file.
# =============================================================================
# check_versions.sh — Recursively verify version headers and key fixes
# across the entire options_trader project.
#
# Excludes: venv, __pycache__, .git, *.pem, trades.db*, bot.log, snapshots
#
# Run from ~/options-trader
# =============================================================================

cd "$(dirname "$0")" || exit 1

echo ""
echo "============================================================"
echo "  RECURSIVE VERSION HEADER CHECK — $(date)"
echo "  Directory: $(pwd)"
echo "============================================================"
echo ""

# Find every .py and .sh file in the project, excluding noise
FILES=$(find . \
    -type d \( -name venv -o -name __pycache__ -o -name .git -o -name snapshots \) -prune \
    -o -type f \( -name "*.py" -o -name "*.sh" \) -print \
    | sed 's|^\./||' \
    | sort)

TOTAL=0
for f in $FILES; do
    TOTAL=$((TOTAL+1))
    echo "------------------------------------------------------------"
    echo "FILE: $f"
    echo "  Last modified: $(stat -c '%y' "$f" 2>/dev/null || stat -f '%Sm' "$f" 2>/dev/null)"
    echo "  Size: $(wc -l < "$f") lines"
    echo "  Header:"
    head -12 "$f" | sed 's/^/    /'
    echo ""
done

echo "============================================================"
echo "  TOTAL FILES SCANNED: $TOTAL"
echo "============================================================"
echo ""
echo "============================================================"
echo "  CRITICAL FIX CHECKS — today's session"
echo "============================================================"
echo ""

MISS=0
check() {
    local file="$1"
    local pattern="$2"
    local label="$3"
    if [ -f "$file" ] && grep -q "$pattern" "$file" 2>/dev/null; then
        echo "  ✓ PRESENT: $label  (in $file)"
    else
        echo "  ✗ MISSING: $label  (expected in $file)"
        MISS=$((MISS+1))
    fi
}

check "main.py"                          "ORBState.OPEN_LONG"           "ORB state fix (OPEN_LONG not CONFIRMED_LONG)"
check "main.py"                          "STRATEGY: NO TRADE"           "NO TRADE log line"
check "main.py"                          "send_shutdown_alert"          "Shutdown alert hook"
check "main.py"                          "signal.SIGTERM"               "SIGTERM handler"
check "main.py"                          "score is None"                "Handles scorer returning None (no Grade C)"
check "analysis/orb_engine.py"           "OPEN_LONG"                    "ORB engine state rename"
check "analysis/orb_engine.py"           "_rearm"                       "ORB re-arm logic"
check "analysis/get_orb_range.py"        "in_opening_window"            "Today-gated 9:30 candle resolve (range moved out of orb_engine)"
check "analysis/orb_engine.py"           "_load_range_from_file"        "ORB range consumed via file handoff (orb_range.json)"
check "analysis/trend_engine.py"         'tf == "5m"'                   "ADX from 5m timeframe"

# ── v3.5-v3.8 remediation fingerprints (stale-sync canaries) ──────────────
check "execution/exit_engine.py"         "_confirm_and_book_live_exit"  "v3.5 fill-confirmed live exits"
check "execution/exit_engine.py"         "from strategy.structure import is_trend_participation" "v4.21 F1 — the binding v4.20 forgot; without it NameError on every condor tick"
check "execution/exit_engine.py"         "or is_credit_vertical(record):" "v4.21 F2 — dispatch routes credit verticals by STRUCTURE, not one strategy string"
check "execution/exit_engine.py"         "0.0 < _persisted < base_stop"  "v4.21 F4 — ratchet restart seed, bounded so stale/foreign values are never adopted"
check "main.py"                          "is_condor_leg    = 0 if _is_tcs else 1," "v6.9 F6 — TC.6 rows no longer claim condor-leg identity"
check "execution/position_manager.py"    "if _is_credit_vertical(record):" "v3.2 F6 pairing — spread pricing by structure (must land WITH main v6.9)"
check "execution/order_confirm.py"       "confirm_order_fill"           "v3.7 entry fill-confirmation module"
check "main.py"                          "confirm_order_fill"           "v3.7 condor legs book on confirmed fill"
check "execution/broker_reconcile.py"    "phantom_pnl"                  "v3.6 phantom P&L recovery"
check "database/trade_logger.py"         "max_premium_seen"             "v3.8 MFE/MAE telemetry columns"
check "database/trade_logger.py"         'COALESCE(paper_trade,1)'      "v3.7 mode-scoped queries (defect Q)"
check "strategy/condor_roll.py"          "ROLL IS REAL"                 "v3.7 roll places a real order (defect P)"
check "config.py"                        "SWEEP_POST_TARGET_TRAIL"      "v2.0 runner refinements in config"
check "execution/position_manager.py"    "df_5m"                        "v3.8 5m FVG trail anchor threaded"

# ══ 2026-07-20 → 07-22 fingerprints ══════════════════════════════
# Everything below post-dates the day-zero block. A box that misses any ONE of
# these is running a materially different engine from the control checkout and
# the parity invariant is broken — re-sync before trusting a session's data.

# ORB v3.9 (2026-07-20) — stale-retest timeout on REAL bars, and re-arming
check "analysis/orb_engine.py"           "_rearm"                       "v3.9 timeout re-arms (not terminal) — SMH missed-short fix"
check "analysis/orb_engine.py"           "bars_since_break"             "v3.9 timeout counts deduped 1m bars, not 15s loop ticks"

# status v1.12 (2026-07-20) — daily-loss banner reads the LIVE unit env
check "status.py"                        "get_runtime_env"              "v1.12 loss-limit read via runtime env (false \$200 HALT fix)"

# main v4.0 / L2.5 (2026-07-21) — the Layer-2 label drives live trading
check "main.py"                          "OT_REGIME_ENGINE"             "v4.0 L2 committed label drives regime (+v13 rollback)"
check "main.py"                          "ConvictionIntegrator"         "v4.0 integrator wired into the live loop"
check "main.py"                          "integrator_state.json"        "v4.0 conviction book persisted per box"

# sweep v3.2 (2026-07-21) — ORB-ownership gate
check "strategy/sweep_reversal_strategy.py" "_orb_released_price"       "v3.2 sweep blocked until the ORB releases price"

# regime_confluence v1.2 (2026-07-22) — ramp de-saturation. PIN THE VALUES:
# a stale file keeps the constant NAMES and silently reverts the bounds, which
# is invisible to a name-only check and would re-saturate RANGING.
check "analysis/regime_confluence.py"    "RANGE_ROOM_LO\", 0.17"        "v1.2 room_s lower bound de-saturated (0.05 -> 0.17)"
check "analysis/regime_confluence.py"    "OSC_CROSS_HI\", 10.0"         "v1.2 osc_s upper bound de-saturated (5 -> 10)"
check "analysis/regime_confluence.py"    "_envf"                        "v1.2 all 14 ramp bounds env-overridable (OT_RC_*)"

# regime_confluence v1.3 (2026-07-27) — confluence excavation. PIN THE VALUES
# and the ABSENCES. A stale sync keeps constant NAMES while reverting values, so
# weights are value-pinned; and since this pass was mostly about REMOVING terms,
# absence is the load-bearing check. The v1.3 changelog deliberately does not
# spell the removed identifiers, so bare-token greps below are safe (the
# changelog-prose trap has re-tripped absence canaries twice).
check "analysis/regime_confluence.py"    "v1.3 — 2026-07-27"            "v1.3 confluence excavation header present"
check "analysis/regime_confluence.py"    "def _sweep(self, liq_map, trend_state=None, ambient=None)"  "v1.3/v1.4 _sweep receives trend_state (PLTR blindness fix) + ambient"
check "analysis/regime_confluence.py"    "trend_opp = 1.0 - (opp_adx \* opp_mom)"  "v1.3 sweep trend-opposition suppressor live"
check "analysis/regime_confluence.py"    "W_SWEEP_REJQ, W_SWEEP_EXH = 0.45, 0.55"  "v1.3 sweep weights pinned (rejq 0.45 / exhaustion 0.55)"
check "analysis/regime_confluence.py"    "W_RANGE_OSC, W_RANGE_BAL = 0.55, 0.45"   "v1.3 ranging weights pinned (osc 0.55 / balance 0.45)"
check "analysis/regime_confluence.py"    "W_COMP_STORED, W_COMP_ATR, W_COMP_SQZ = 0.45, 0.35, 0.20"  "v1.3 compression weights pinned"
check "analysis/regime_confluence.py"    "W_BRK_EXPAND, W_BRK_CLEAR, W_BRK_MOM = 0.40, 0.30, 0.30"   "v1.3 breakout weights pinned"
check "analysis/regime_confluence.py"    "COMP_OSC_LO"                  "v1.3 crossings axis decoupled ranging/compression"
check "analysis/regime_confluence.py"    "def midline_balance"          "v1.3 real range-balance corroborator exists"
check "analysis/regime_confluence.py"    "def momentum_val"             "v1.3 shared momentum mapper (no-vote earns no credit)"
check "analysis/regime_confluence.py"    "soft_necessary=\[narrow_s\]"   "v1.3 compression tightness stays NECESSARY (not a corroborator)"
check "analysis/regime_confluence.py"    "veto_inside"                  "v1.3.1 compression containment veto (A3 squeeze-break fix)"

# trade readiness v1.0 / main v4.3 (2026-07-27) — LOG-ONLY readiness engine.
# The absence half matters: a stale main.py sync silently drops the hook and
# the journal just stops growing readiness rows with no error anywhere.
check "analysis/trade_readiness.py"      "TradeReadinessEngine"         "v1.0 trade readiness engine present"
check "analysis/trade_readiness.py"      "readiness_would_fire"         "v1.0 would-fire observation event"
check "analysis/trade_readiness.py"      "TR_DEARM_SLOPE"               "v1.0 slope de-arm knob (falling confluence disarms)"
check "analysis/trade_readiness.py"      "0.5 \*\* (dt / TR_SLOPE_HALFLIFE_S)" "v1.0 dt-aware slope EMA (wall-clock, no tick counters)"
check "main.py"                          "_readiness.assess_all(ctx, regime)" "v4.3 readiness hooked in the every-tick block"
check "main.py"                          "main.py — options_trader v6.1" "v6.1 main header current (ORB exempt from the stale entry gate)"
check "main.py"                          "_orb_exempt"                  "v5.4 confirmed ORB bypasses the stale entry block"
check "main.py"                          "STALE book, but ORB is CONFIRMED"  "v5.4 the exempt path says why in the log"
check "tests/orb_stale_block_audit.py"   "ORB confirmed"                "v1.0 the cost of the gate is measurable, not asserted"

# ── rollup 2026-08-04 — the OOM and the confounded denominator ────────────
check "tests/a2_cooccurrence.py"         "_KEEP = "                     "v1.2 records slimmed at parse time (devtools 47 was OOM-killed)"
check "tests/test_a2_cooccurrence_slim.py" "covers_every_field_the_source_reads"  "v1.0 the slim is checked against the SOURCE, not a list"
check "tests/pitchfork_filter_audit.py"  "ACCEL/held bar"               "v1.5 exposure denominator (per-birth is confounded by lifetime)"

# ── pull_today_ohlc v1.3 (2026-08-04) — the guard that ate the backfill ───
check "pull_today_ohlc.sh"               'BOT=$(systemctl is-active optionsbot' "v1.3 guard reads optionsbot, not just the clock"


# CV.1 (2026-08-10) — CANARY REMOVED, NOT SILENTLY DROPPED. It pinned
# `tests/condor_plan_lifetime.py`, which does not exist at any HEAD in this
# repo, so the sweep ended `DONE — CANARY FAILURE(S)` on a PERFECTLY CLEAN
# checkout. A permanently-red gate is worse than no gate: it trains the reader
# to skip its own DONE banner, which is the cried-wolf failure this file exists
# to prevent (WORKING_AGREEMENT §17).
# `tests/condor_approach.py` covers adjacent ground (it discusses plan
# lifetimes) but carries no "WOULD A PAUSE HAVE HELPED" marker, so it is NOT a
# rename and the canary was not re-pointed at it on a guess.
# ⚠️ IF condor_plan_lifetime.py EXISTS SOMEWHERE OFF-REPO, RESTORE THE FILE AND
# THIS LINE rather than leaving the check deleted — the intent (measure the
# fix's PREMISE, not just the deaths) is sound and worth keeping.
check "main.py"                          "DIRECTIONAL_ONLY is EMPTY fleet-wide"  "stale single-names comment corrected"

# ── candle_feed v3.10 (2026-08-04) — the gate that ate the backfill ───────
# CV.1 PRECEDENT (2026-08-15): a canary pinning a LITERAL VERSION STRING goes
# red on every legitimate bump and teaches the operator to ignore a red run.
# `addendum v3.11` did exactly that at v3.13. Replaced with BEHAVIOUR canaries
# on the two things that must not silently revert.
check "data/candle_feed.py"              "extended_trading_hours=ext"   "FEED.2 extended-hours sub"
check "data/candle_feed.py"              "_maintenance_now()"           "FEED.1 maintenance gate"
check "data/candle_feed.py"              "def _idle_outside_session"    "v3.11 ONE predicate for both RTH checks"

# ── condor approach telemetry (2026-08-04) — item AI's measurement ────────
check "strategy/iron_condor_strategy.py" "v-approachalways"             "approach reported on EVERY plan death"
check "strategy/iron_condor_strategy.py" "def _approach"                "approach helper present"
check "tests/condor_approach.py"         "GEOMETRY_MAX"                 "v1.0 verdict thresholds pre-registered"

# ── N.9 contract telemetry (2026-08-04) — premium decomposition ───────────
check "database/trade_logger.py"         "def set_entry_contract"       "v3.12 contract telemetry setter"
check "database/trade_logger.py"         '("entry_delta",       "REAL")' "v3.12 columns migrate (NULL = not captured, no defaults)"
check "main.py"                          "def _capture_entry_contract"  "v5.5 capture at the fill seam"
check "tests/test_entry_contract.py"     "matched_on_occ_symbol"        "v1.0 OCC match pinned (strike would cross condor legs)"
check "database/trade_logger.py"         "set_entry_contract failed"    "v3.13 handler is AUDIBLE to the swallow census"
check "database/trade_logger.py"         "set_exit_contract failed"     "v3.13 handler is AUDIBLE to the swallow census"
check "strategy/iron_condor_strategy.py" "condor_abandon journal failed" "v-audibleabandon handler is AUDIBLE"

# ── conditional_tables v1.4 (2026-08-05) — session spread on every cell ────
check "tests/conditional_tables.py"      "def spread_flag"              "v1.4 concentration warning present"
check "tests/conditional_tables.py"      't.get("entry_time"'           "v1.4 the DATE reaches Cell.add (wiring, not just the flag)"
check "tests/test_conditional_session_spread.py" "reaches_the_cell_from_a_trade_ROW" "v1.0 wiring test present"
check "tests/conditional_tables.py"      '*_trades*.db'                 "v1.5 glob matches the DATED filename the fleet actually writes"
check "tests/conditional_tables.py"      "LOAD FAILED"                  "v1.5 an empty load refuses instead of reporting a null"
check "tests/test_conditional_load.py"   "refuses_instead_of_reporting_a_null" "v1.0 empty-load guard present"
check "tests/conditional_tables.py"      "def _dedup_key"               "v1.6 de-duplicates across dated folders"
check "tests/conditional_tables.py"      "trade_id,symbol"              "v1.6 trade_id is SELECTed (it was not)"
check "tests/test_conditional_load.py"   "two_dated_folders_counts_once" "v1.0 de-dup guard present"
check "tests/replay_confluence.py"       "A2_BAND_HI"                   "v2.4 A2 is a banded metric, not an unsatisfiable invariant"
check "tests/test_a2_band.py"            "far_above_the_band_still_fails" "v1.0 A2 can still raise a real alarm"
check "tests/readiness_digest.py"        "npeg = len(fits)"             "v1.2 headline counts the same pegged RAMPS the fits list"
check "analysis/trade_readiness.py"      "def _market_snapshot"         "v1.5 VWAP context helper"
check "analysis/trade_readiness.py"      '"market": self._mkt'          "v1.5 the journal actually EMITS it (a computed value never written is the bug)"
check "analysis/trade_readiness.py"      '"dir": ("short" if side == "call" else "long")' "v1.6 condor dir is EXPOSURE not option type (call credit = short; the buyer's-eye reading inverts every condor row and still renders cleanly)"
check "analysis/trade_readiness.py"      '"dir": "neutral"'             "v1.6 butterfly sideless BY DESIGN, stamped so it cannot be confused with a missing field"
check "analysis/trade_readiness.py"      '_kind == "high_sweep"'        "v1.6 sweep dir from the LIVE liq_map — the field no offline tool could recover"
check "tests/test_readiness_direction_stamp.py" "test_every_track_stamps_a_direction" "v1.0 all six tracks carry dir (one writer made it look optional for weeks)"
check "analysis/trade_readiness.py"      "W_BFLY_PIN, W_BFLY_FIRM"     "v1.8 the butterfly scores the PIN, not the label"
check "analysis/trade_readiness.py"      "pin_dist_unit"               "v1.8 em and atr2 are different scales — the unit must be recorded, never pooled"
check "tests/test_butterfly_pin_readiness.py" "test_the_coil_is_not_in_hard_vetoes" "v1.0 the only test that can see the veto come back"
check "analysis/trade_readiness.py"      "W_SWEEP_APPR, appr_val"       "v1.7 approach factor present; a label hard-veto would return this track to a silent permanent zero — restoring one is a silent permanent zero"
check "analysis/trade_readiness.py"      "SWEEP_PROX_FAR., 2.32"       "v1.7 FAR = shadow-observed MEDIAN 2.32 ATR, not a guess"
check "analysis/trade_readiness.py"      "appr_name"                   "v1.7 the level's NAME reaches the journal"
check "tests/test_readiness_sweep_approach.py" "test_track_scores_without_the_sweep_label" "v1.0 the guard on the veto we already shipped once"
check "execution/exit_engine.py"          "self.min_dist"               "v4.15 BOS level floored out of the noise band"
check "execution/exit_engine.py"          "else max(self.protected_level, _cand)" "v4.15 RATCHET — low-min_dist is not monotone; losing this slackens the stop as ATR widens"
check "config.py"                        "OT_BOS_MIN_DIST_ATR"         "v4.15 kill switch AND A/B control"
check "tests/test_bos_min_distance.py"   "test_min_dist_zero_is_byte_identical_to_the_old_behaviour" "v1.0 the kill switch must actually kill"
check "tests/vwap_orientation_ledger.py" "MIN_ARM_TRADES"              "v1.6 VW.1f-c — a verdict rests on the SMALLER arm; a floor on the total does not constrain it"
check "tests/vwap_orientation_ledger.py" "MAPPED BUT UNMATCHED"        "v1.6 VW.1f-a — trades that map but never match were vanishing with no line anywhere"
check "tests/vwap_orientation_ledger.py" "_SRC_BY_TRACK"               "v1.6 VW.1f-b — the era warning must key on ONE TRACK holding both, not on the totals"
check "analysis/conviction_integrator.py" "regime engine. — v2.3"      "v2.3 header current"
check "analysis/conviction_integrator.py" "theta_commit_by_regime"     "v2.3 RGM.4 per-regime commit bar — a revert to the global silently re-darkens RANGING"
check "analysis/conviction_integrator.py" "p.commit_bar(top_r)"        "v2.3 the ARMING site uses the challenger's own bar, not the global"
check "tests/test_ranging_commit_bar.py" "test_the_bar_stays_out_of_the_impostor_window" "v1.0 the bar may move; it may not move into the 12-15 bar false-flat zone"
check "main.py"                          "not _cont_blocked"           "v6.0 CNT.6 — the runaway bypass must NOT reopen the premium regimes; its return is silent"
check "main.py"                          "main.py — options_trader v6.1" "v6.1 header current"
check "config.py"                        "OT_CONT_BLOCK_PREMIUM"       "v6.0 kill switch AND A/B control"
check "tests/test_continuation_premium_block.py" "test_runaway_cannot_bypass_a_premium_regime" "v1.0 the guard that matters"
check "strategy/continuation_strategy.py" "CONT_CONFIRM_TOL_ATR"        "v1.6 CNT.7 — the confirmation tolerance must be ATR-scaled, never raw price"
check "config.py"                        "OT_CONT_CONFIRM_TOL_ATR"     "v1.6 kill switch AND A/B control"
check "tests/test_continuation_confirmation.py" "test_a_too_small_tolerance_would_be_a_no_op" "v1.6 guards against a fix in name only"
check "strategy/continuation_strategy.py" "CONTINUATION_REQUIRE_CONFIRM" "v1.5 the tag is the SETUP, the next bar is the TRIGGER"
check "strategy/continuation_strategy.py" "confirmation UNDECIDABLE"    "v1.5 thin tape REFUSES — an absent confirmation is not a passed one"
# CV.2 (2026-08-15) — CANARY REMOVED, NOT SILENTLY DROPPED (CV.1 precedent).
# "v1.6 header current" pinned the VERSION STRING in continuation_strategy's
# title, so it went red the moment the file legitimately moved to v1.7 — on a
# perfectly clean sync. Version-string pins are exactly what the canary rules
# forbid: they alarm on progress, not on regression. The v1.6 BEHAVIOR
# canaries (CNT.7 ATR-scaled tolerance, above) remain and still guard the
# change itself. Found red at HEAD 89cbaf6 during audit #2 packaging.
check "config.py"                        "OT_CONT_REQUIRE_CONFIRM"     "v1.5 kill switch AND A/B control"
check "tests/test_continuation_confirmation.py" "test_undecidable_refuses_rather_than_passes" "v1.0 the guard that matters"
check "analysis/regime_confluence.py"    "soft_necessary=.trend_opp, age_decay." "v1.4 PLTR GUARD — trend_opp stays multiplicative; ambient must never rescue an opposed sweep"
check "analysis/regime_confluence.py"    "spent_val"                   "v1.4 the spent-move corroborator — was the thing being faded actually a MOVE"
check "analysis/regime_confluence.py"    '"DECELERATING": 0.25, "": 0.6' "v1.4 absence must not SUPPRESS harder than FLAT"
check "analysis/regime_confluence.py"    '"ACCELERATING": 0.0, "": 0.0' "v1.4 absence must not CORROBORATE either — the asymmetry is deliberate"
check "tests/test_sweep_spent_move.py"   "test_pltr_protection_survives" "v1.0 the guard that matters"
check "main.py"                          "_L1_BREAKDOWN_FOR"           "v5.9 L1 evidence recorded at the fire, not replayed later"
check "main.py"                          "main.py — options_trader v6.1" "v6.1 main header current"
check "tests/test_disposition_l1_capture.py" "test_orb_records_no_breakdown_by_design" "v1.0 ORB is regime-immune — a mapping there would imply a dependency that does not exist"
check "tests/test_readiness_market_snapshot.py" "READ_from_the_engine_not_derived" "v1.0 side comes from the engine, never a derived sign"
check "tests/test_readiness_peg_count.py" "counts_ramps_not_raw_values"  "v1.0 one definition of pegged"
_n_cap=$(grep -c "_capture_entry_contract(ctx, record)" main.py 2>/dev/null || echo 0)
if [ "$_n_cap" = "2" ]; then
    echo "  ✓ PRESENT: N.9 captures at BOTH fill seams (directional + condor leg)"
else
    echo "  ✗ STALE:   only $_n_cap of 2 fill seams capture contract telemetry — those trades appear in P&L but cannot enter the direction-vs-theta-vs-IV read"
    MISS=$((MISS+1))
fi
_n_ab=$(grep -c "self._journal_abandon(plan" strategy/iron_condor_strategy.py 2>/dev/null || echo 0)
if [ "$_n_ab" = "2" ]; then
    echo "  ✓ PRESENT: both plan-death paths emit condor_abandon (found $_n_ab)"
else
    echo "  ✗ STALE:   only $_n_ab of 2 plan-death paths emit condor_abandon — the CANCEL branch is 23 of 23 deaths, so losing it makes item AI unmeasurable again"
    MISS=$((MISS+1))
fi
check "pull_today_ohlc.sh"               'OT_PULL_RTH_GUARD:-1'         "v1.5 guard back ON by default (v3.10 fixed the real cause)"
check "tests/test_candle_feed_once_exempt.py" "both_gates_go_through_the_one_predicate"  "v1.0 BOTH gates pinned to the shared predicate"
_n_once=$(grep -c "self._idle_outside_session(once)" data/candle_feed.py 2>/dev/null || echo 0)
if [ "$_n_once" = "2" ]; then
    echo "  ✓ PRESENT: v3.11 both RTH checks route through the one predicate (found $_n_once)"
else
    echo "  ✗ STALE:   candle_feed has $_n_once of 2 predicate calls — an EOD candle pull outside RTH will sleep to its timeout and write a header-only csv; that day's sat-out tape is gone at midnight"
    MISS=$((MISS+1))
fi
check "tests/test_pull_ohlc_guard.sh"    "THE CASE IT EXISTS FOR"       "v1.2 guard decision table covered (guard ON by default)"
if grep -q '\[ "$FEED" = "active" \] && \[ "$POSTCLOSE" = "0" \]; then' pull_today_ohlc.sh 2>/dev/null; then
    echo "  ✗ STALE:   pull_today_ohlc guard is back to the clock-only form — every sat-out box backfill wakes will write a header-only csv and that session's tape is gone at midnight"
    MISS=$((MISS+1))
else
    echo "  ✓ PRESENT: v1.3 guard requires a live optionsbot before refusing the rebuild"
fi
if grep -q "if not _orb_exempt:" main.py 2>/dev/null; then
    echo "  ✓ PRESENT: v5.4 the stale gate still blocks everything that is not a confirmed ORB"
else
    echo "  ✗ STALE:   main.py no longer branches the stale gate on _orb_exempt — either ORB is gated again (v5.0 form) or the gate was deleted outright"
    MISS=$((MISS+1))
fi
check "analysis/trade_readiness.py"      "readiness_staged_pick"        "v1.1 staged-pick journaling (calm-vs-spike experiment)"
check "analysis/trade_readiness.py"      "TR_CONV_HALFLIFE_S"           "v1.1 smoothed-conviction EMA knob"
check "tests/readiness_digest.py"        "readiness_digest_"            "v1.0 nightly digest tool present (conductor phase 9 target)"
check "tests/readiness_digest.py"        "FIT SUGGESTIONS"              "v1.1 digest emits fitted OT_TR_* bounds (no second guess)"
check "tests/readiness_digest.py"        "FACTOR_MAP"                   "v1.1 factor calibration section (peg rates on ramped outputs)"
check "analysis/trade_readiness.py"      "TR_CONV_LO"                   "v1.2 conviction ramp env-overridable (the day-1 peg)"
check "analysis/trade_readiness.py"      "TR_PULL_ATR_LO"               "v1.2 midline-pull band env-overridable"
check "analysis/trade_readiness.py"      "TR_NARROW_PIVOT"              "v1.2 all 13 factor bounds OT_TR_* (parity with OT_RC_*)"

# ABSENCE checks — these four terms must be GONE from the whole file. Unlike the
# _orb_quality canary we can grep the bare token, because v1.3's changelog was
# written to describe them without naming them.
for _tok in W_RANGE_BASE W_COMP_BASE quiet_fallback vol_only_fallback; do
    if grep -q "$_tok" analysis/regime_confluence.py 2>/dev/null; then
        echo "  ✗ STALE:   $_tok is BACK in regime_confluence.py — a constant corroborator or fabricated fallback was restored (expected DELETED)"
        MISS=$((MISS+1))
    else
        echo "  ✓ PRESENT: $_tok deleted (v1.3 excavation held)"
    fi
done

# main v4.5 (2026-07-29) — THE L2.5 IMPORT CONTRACT. RANGE_WINDOW_BARS is owned
# by regime_confluence; importing it via conviction_integrator relied on a
# re-export tuple that the v1.3 excavation trimmed, and the resulting ImportError
# was swallowed by the L2 guard — 15 boxes ran the v1.3 classifier for a whole
# session on nothing but one WARNING per start. Presence pins the corrected
# source; absence pins that the broken form has not come back on a stale sync.
# The v4.5 changelog in main.py deliberately does not spell the old import line,
# so the bare grep below stays honest (changelog-prose trap).
check "main.py"  "regime_confluence import RegimeConfluenceScorer, RANGE_WINDOW_BARS"  "v4.5 L2 symbols imported from their OWNING module"
check "main.py"  "send_regime_engine_degraded_alert"  "v4.5 silent L2 fallback now pages (data-integrity event)"
check "main.py"  "L2.5 NOT committing"  "v4.6 non-committing L2 gate reports its reason (was silent)"
check "main.py"  "_l2_mute"             "v4.6 reason-change throttle present"
check "main.py"  "REGIME ENGINE:"       "v4.7 active regime engine stated at startup"
check "main.py"  "warming as designed"  "v4.8 opening 1m warm-up logs INFO, not a false WARNING"
check "main.py"  "engine        = \"L2\" if l2_label"  "v4.8 regime_log rows stamped with the engine"
check "database/trade_logger.py"  "regime_engine"  "v4.8 trades carry regime_engine"
check "database/trade_logger.py"  "ALTER TABLE regime_log ADD COLUMN engine"  "v4.8 regime_log auto-migrates"
if grep -q '_REGIME_ENGINE == "L2"' main.py 2>/dev/null; then
    echo "  ✗ STALE:   main.py compares _REGIME_ENGINE to \"L2\" but the value is .lower()ed — L2.5 is UNREACHABLE dead code (the 07-29 root cause is back)"
    MISS=$((MISS+1))
else
    echo "  ✓ PRESENT: v4.7 L2 gate literal is lowercase (block is reachable)"
fi
check "notifications/alert_manager.py"  "def send_regime_engine_degraded_alert"  "v1.7 degraded-engine pager exists"
check "notifications/alert_manager.py"  "def _send(self, msg: str) -> bool"      "v1.9 _send reports delivery"
check "notifications/alert_manager.py"  "def send_blind_alert"                   "v1.8 blind-alert pager exists"
check "utils/blindness_latch.py"        "def update"                             "v1.0 blindness latch present"
if grep -q "conviction_integrator import ConvictionIntegrator, RANGE_WINDOW_BARS" main.py 2>/dev/null; then
    echo "  ✗ STALE:   main.py re-imports RANGE_WINDOW_BARS from conviction_integrator — the 07-29 fleet-wide L2 outage is BACK"
    MISS=$((MISS+1))
else
    echo "  ✓ PRESENT: broken L2 import form is gone from main.py"
fi

# config v4.0 (2026-07-27) — sweep strike floor. VALUE-pinned: the number IS the
# fix, and a name-only check passes happily on the reverted 0.08.
check "config.py"                        "SWEEP_DELTA_STRONG          = 0.12"  "v4.0 sweep strike floor 0.08 -> 0.12 (reachable strikes)"
check "config.py"                        "SWEEP_DELTA_WEAK            = 0.30"  "v4.0 sweep weak endpoint unchanged at 0.30"

# limit_ladder (2026-07-22) — the mark-limit execution policy
check "execution/limit_ladder.py"        "hard_close_order_mode"        "limit ladder present: 15:40 mark-limit -> 15:45 MARKET"
check "execution/entry_engine.py"        "limit_at_mark"                "v3.9 entries post a LIMIT at the mark (was MARKET)"
check "execution/exit_engine.py"         "limit_at_mark"                "closes post at the mark, re-priced each tick"
check "config.py"                        "FLATTEN_WINDOW_OPEN_ET"       "flatten window opens 15:40 (config + time_utils)"
check "utils/time_utils.py"              "FLATTEN_WINDOW_OPEN"          "v3.8 is_hard_close_time() opens at 15:40"

# paper-friction unification (2026-07-22, audit defect T) — one authority
check "execution/limit_ladder.py"        "def paper_fill_credit"        "v1.3 single paper-pricing authority (credit side)"
check "main.py"                          "paper_fill_credit"            "v4.1 condor leg paper credit uses the shared authority"
check "strategy/condor_roll.py"          "paper_fill_credit"            "v3.8 rolled vertical uses the shared authority"
check "config.py"                        "OT_PAPER_SLIPPAGE_PCT\", \"0.0\"" "paper friction default 0.0 (books the mark)"

# ── ORB geometry gate (setup_scorer v1.4, 2026-07-22) ────────────────────
check "risk/setup_scorer.py"             "_grade_orb"                   "v1.4 ORB graded by geometry gate (liquidity-in-path A/B only)"
check "risk/setup_scorer.py"             "_pools_in_path"               "v1.4 ORB A/B selector = unswept pool between entry and TP"

# ── trend continuation unblocked (defect W, 2026-07-22) ──────────────────
check "analysis/trend_engine.py"         "primary_momentum"             "v3.2 TrendState surfaces primary_momentum (5m vote)"
check "strategy/continuation_strategy.py" "primary_momentum"            "v1.1 continuation READS primary_momentum (was silently \"\")"
check "config.py"                        "OT_CONT_STOP_PCT"             "continuation backstop 25%% (was blanket 40%%)"
check "execution/exit_engine.py"         "CONTINUATION_STOP_LOSS_PCT"   "v4.0 continuation floor uses its own pct, not MAX_LOSS_PCT"
check "execution/exit_engine.py"         "_fvg_frame(df_1m, df_5m),"    "v4.0 continuation trail anchors to 5m FVGs"

# ── condor v2 (2026-07-23) ────────────────────────────────────────────────
check "config.py"                        "(11, 11)"                     "condor window opens 11:11 (BB valid; no current_price fallback)"
check "config.py"                        "OT_CONDOR_RATCHET_BE"         "condor ratchet knobs present"
check "config.py"                        "OT_CONDOR_TP_PCT"             "condor time-gated TP knob present"
check "execution/exit_engine.py"         "_condor_ratchet"              "v4.1 condor ratcheting stop (BE at +20%, lock +20% at +40%)"
check "execution/exit_engine.py"         "_condor_sibling_open"         "v4.1 TP fires only on a STANDALONE, never a condor leg"
check "execution/exit_engine.py"         "condor_tp pnl="               "v4.1 time-gated take-profit exit reason"
check "risk/risk_manager.py"             "leg_budget"                   "v3.2 condor vertical sized at FULL budget (was half)"
check "analysis/chain_snapshot.py"       "def snapshot"                 "chain archival module present (full 0DTE chain -> .jsonl.gz)"
check "analysis/chain_snapshot.py"       "vega"                         "chain archival keeps gamma+vega (signal_journal drops them)"

# ── ENTRY SNAPSHOT (2026-08-04) — the TC.2 exit-counterfactual precursor ──
# Log-only, which is precisely why it needs canaries: nothing downstream fails
# when it stops. A missing capture produces NULLs that look identical to a quiet
# session, and the bake-off it feeds cannot be run on rows banked without it.
check "analysis/entry_snapshot.py"       "SCHEMA_VERSION"               "v1.0 entry-snapshot module present"
check "analysis/entry_snapshot.py"       "_nearest_unfilled_fvg_in_favor"  "v1.0 anchor uses the exit engine's OWN finder (one lineage, not a copy)"
check "database/trade_logger.py"         "def set_entry_snapshot"       "v3.10 snapshot writer present"
check "database/trade_logger.py"         "return cur.rowcount > 0"      "v3.10 writer reports a REAL write (a no-op UPDATE must not read as success)"
check "main.py"                          "_capture_entry_snapshot"      "v5.1 capture hooked on the directional entry path"
check "tests/test_entry_snapshot.py"     "byte_identical_to_the_trails_own_answer"  "v1.0 parity test present (fails if the trail and the snapshot diverge)"

# ── N.5 EXIT LADDER LATENCY (2026-08-04) — the TC.2 stop-trigger dataset ──
check "execution/exit_engine.py"         "def _stamp_exit_latency"      "v4.11 latency stamp present at the single close seam"
check "execution/exit_engine.py"         "_exit_submit_mono"            "v4.11 submit instant kept on the RECORD (survives a multi-tick live close)"
check "database/trade_logger.py"         "def set_exit_latency"         "v3.11 latency writer present"
check "database/trade_logger.py"         "exit_mark_at_trigger"         "v3.11 mark-at-trigger captured (latency is not a cost until it is priced)"
check "tests/test_exit_latency.py"       "does_not_restart_the_clock"   "v1.0 multi-tick accumulation test present"

# ── v5.2 (2026-08-04) — NO REGIME-FLIP EXIT ON A STALE BOOK ──────────────
check "main.py"                          "_rgm_stale"                   "v5.2 stale gate present on the exit path"

# ── W.2a (2026-08-04) — this thread's own swallows, made audible ─────────
check "tests/swallow_audit.py"           "def _report_new"              "v1.1 --since names the new silent handlers"
check "execution/exit_engine.py"         "_telemetry_logged"            "v4.13 telemetry throttle has its OWN set (reusing the alert set misread as pages)"
check "analysis/entry_snapshot.py"       "def _first"                   "v1.2 inline logging + throttle (a log behind a helper is invisible to the census)"

# ── regime_diary v1.3 (2026-08-04) — the diary could not tell bull from bear ──
check "utils/regime_labels.py"           "\"TRENDING_BEAR\":     \"BEAR\""  "v1.0 shared label map (bull/bear distinguishable)"
check "tests/regime_diary.py"            "LABEL = REGIME_LABELS"        "v1.4 diary uses the SHARED map, not a local copy"

# ── gap_outcome_join v1.5 (2026-08-04) — the pooled read, with its own guard ──
check "tests/gap_outcome_join.py"        "POOLED_CLASSES"               "v1.5 --pool gapflat present"
check "tests/gap_outcome_join.py"        "POOL LEGITIMACY"              "v1.5 pooling prints its own CONT-vs-REV verdict"
check "tests/test_gap_pool.py"           "test_opposite_arms_are_refused"  "v1.0 planted-divergence test present"

# ── TC.4b prerequisite (2026-08-04) — does the impulse floor hold? ────────
check "tests/tcs_floor_durability.py"    "seen.add(key)"                "v1.0 one impulse counted once, not once per scored tick"
check "tests/tcs_floor_durability.py"    "through = (c < floor)"        "v1.0 durability is CLOSE-based (acceptance, not a touch)"
check "tests/tcs_floor_durability.py"    'default="ARMED"'              "v1.1 population defaults to ARMED (not every floor the lookback computed)"
check "tests/tcs_floor_durability.py"    'stats\["not_armed"\]'          "v1.1 DORMANT floors are excluded and counted"
check "tests/tcs_floor_durability.py"    "term_failed = (term_close < floor)"  "v1.2 TERMINAL outcome is measured at the bell, not from the intraday break"
check "tests/tcs_floor_durability.py"    "STRIKE CURVE"                 "v1.2 terminal failure vs distance beyond the floor"
check "tests/tcs_floor_durability.py"    "MATCHED CONTROL"              "v1.3 control arm present (an absolute rate proves nothing)"
check "tests/tcs_floor_durability.py"    "i = rng.choice(elig)"         "v1.3 the control anchor is DRAWN, not fixed"

# ── pitchfork variant sweep (2026-08-04) — §12 open question 2 ────────────
check "tests/pitchfork_filter_audit.py"  "VARIANT SWEEP"                "v1.4 three-variant geometry comparison present"
check "tests/pitchfork_filter_audit.py"  "replay(sym, h1, \"1h\", av, variant=variant"  "v1.4 variant is THREADED to the replay (not swallowed)"
check "tests/replay_confluence.py"       "from utils.regime_labels import label"  "v2.3 emitted-distribution line uses the shared map"
check "tests/regime_diary.py"            "churn-cut"                    "v1.3 churn-cut on the L2 line (flips per committed switch)"
check "tests/regime_diary.py"            "def rerender"                 "v1.3 --rerender rebuilds the md from the jsonl"
if grep -q "k.split('_')\[0\]\[:4\]} {d\[k\]" tests/regime_diary.py 2>/dev/null; then
    echo "  ✗ STALE:   regime_diary is back to the truncating label — TRENDING_BULL and TRENDING_BEAR both render as TREN"
    MISS=$((MISS+1))
else
    echo "  ✓ PRESENT: v1.3 truncating label is gone from the dominance row"
fi
check "tests/test_stale_no_regime_flip.py" "hard_close_still_fires"     "v1.0 proves PRICE exits still fire with no label"
if grep -q "regime=regime.primary_regime if regime else None," main.py 2>/dev/null; then
    echo "  ✗ STALE:   main.py passes the label to the exit path unconditionally — regime-flip exits can fire on a stale book again (v5.1 form is back)"
    MISS=$((MISS+1))
else
    echo "  ✓ PRESENT: v5.2 label withheld from exits while the book is stale"
fi
if grep -q "if not result or not result.confirmed:" execution/exit_engine.py 2>/dev/null; then
    echo "  ✓ PRESENT: v4.11 latency writes ONLY on a confirmed close"
else
    echo "  ✗ STALE:   exit_engine no longer guards the latency write on result.confirmed — unconfirmed passes will book the fast leg of every slow close and silently bias the TC.2 dataset"
    MISS=$((MISS+1))
fi
# ABSENCE — the condor legs must still be handed ctx. Without it the helper
# degrades to no capture BY DESIGN, so the failure is invisible by construction.
if grep -q "_execute_condor_leg(leg_signal, state)" main.py 2>/dev/null; then
    echo "  ✗ STALE:   main.py calls _execute_condor_leg WITHOUT ctx — condor legs are silently not captured (entry_snapshot NULL on every leg)"
    MISS=$((MISS+1))
else
    echo "  ✓ PRESENT: v5.1 both condor call sites pass ctx (legs are captured)"
fi
check "main.py"                          "chain_snapshot import snapshot" "v4.2 chain archival wired into the every-tick GEX block"
check "strategy/iron_condor_strategy.py" "Leg 2 PAUSED"                 "v3.2 leg 2 pauses on non-RANGING (was CANCELLED)"
# ABSENCE: the half-size budget must be gone
if grep -q "half_budget" risk/risk_manager.py 2>/dev/null; then
    echo "  ✗ STALE:   risk_manager still half-sizes condor verticals (expected FULL budget)"
else
    echo "  ✓ PRESENT: condor verticals sized at full budget (no half_budget)"
fi
# ABSENCE: "STEADY" is a phantom — trend_engine emits ACCELERATING/DECELERATING/
# FLAT only. Its return means a stale continuation_strategy.py is back.
if grep -qE 'momentum in \("ACCELERATING", "STEADY"\)' strategy/continuation_strategy.py 2>/dev/null; then
    echo "  ✗ STALE:   continuation_strategy uses phantom STEADY value — pre-v1.1 file restored"
else
    echo "  ✓ PRESENT: continuation momentum vocabulary is ACCELERATING/FLAT (no phantom STEADY)"
fi
# ABSENCE check: _orb_quality must be GONE from executable code. A stale sync
# that restores it re-introduces the regime/VWAP/macro-weighted ORB score. We
# grep only for a CALL (self._orb_quality(), def _orb_quality) — the string
# survives in the v1.4 changelog prose, which is fine.
if grep -qE "def _orb_quality|self\._orb_quality\(" risk/setup_scorer.py 2>/dev/null; then
    echo "  ✗ STALE:   _orb_quality is BACK in setup_scorer.py — ORB weighted score restored (expected DELETED)"
else
    echo "  ✓ PRESENT: _orb_quality deleted from code (ORB is a geometry gate)"
fi

# ── 2026-07-17/18 day-zero fingerprints (trend v3.1 + VWAP + condor + continuation) ──
check "analysis/trend_engine.py"         '"5m": 0.35'                   "trend v3.1 intraday-primary tf_weights (dead-4h fix)"
check "analysis/volatility_engine.py"    'price_vs_vwap = "NONE"'       "VWAP zero-volume guard (SPX NaN->BELOW fix)"
check "config.py"                        "CONDOR_TRIGGER_APPROACH"      "condor premium-rich band-approach triggers"
check "strategy/continuation_strategy.py" "ContinuationStrategy"        "continuation trade strategy present"
check "main.py"                          "_continuation_strategy"       "continuation registered in dispatch"
check "execution/exit_engine.py"         "_evaluate_continuation"       "continuation exhaustion exit"
check "strategy/continuation_strategy.py" "CONTINUATION_CONV_FLOOR"     "continuation conviction floor present"
check "config.py"                        "CONTINUATION_EXHAUST_EXT_ATR" "continuation exhaustion config block"

# ── v3.9 Phase-3.1 instrumentation fingerprints (log-only) ────────────────
check "analysis/signal_journal.py"       "def journal"                  "v1.0 signal journal module present"
check "risk/setup_scorer.py"             "_journal_scored"              "v1.3 scorer emits scored events (REJECTs included)"
check "analysis/orb_engine.py"           "retest_depth_px"              "v3.7 defect-G retest depth measurement"
check "main.py"                          "condor_leg"                   "v3.9 condor conviction journaled at fire time"
check "status.py"                        "ORB High"                    "Structured ORB display"
check "status.py"                        "No Trade"                    "No Trade display string"
check "notifications/alert_manager.py"   "send_shutdown_alert"          "Shutdown alert method"
check "notifications/alert_manager.py"   "INSTRUMENT"                   "Ticker in alerts"
check "notifications/alert_manager.py"   "send_regime_alert"            "Regime alert present (should be no-op/pass)"
check "risk/setup_scorer.py"             "return None"                  "Grade C elimination (returns None)"
check "risk/setup_scorer.py"             "Optional\[SetupScore\]"       "Score return type updated"
check "strategy/butterfly_strategy.py"   "gex_environment"              "GEX field name fix"
check "strategy/butterfly_strategy.py"   "BUTTERFLY_WING_SPX"           "Fixed wing widths"
check "strategy/butterfly_strategy.py"   "_fired_today"                 "One butterfly per session"
check "strategy/orb_strategy.py"         "ORBState.OPEN_LONG"           "ORB strategy state rename"
check "execution/exit_engine.py"         "POST_TARGET_TRAIL_LOCK_PCT"   "FVG trail past 100% TP"
check "execution/exit_engine.py"         "_find_1m_fvgs"                "1m FVG detection"
check "execution/position_manager.py"    "notify_position_closed"       "ORB re-arm hook on position close"
check "config.py"                        "BUTTERFLY_WING_SPX"           "Butterfly config constants"
check "config.py"                        "BUTTERFLY_ENTRY_START_ET"     "Butterfly noon entry window"
check "push.sh"                          "Detected malformed remote"    "Self-healing remote URL"
check "push.sh"                          "diverged"                    "Diverged history handling"
check "setup_ec2.sh"                     'GITHUB_REPO#https://'         "GitHub URL normalization"

# ── AUDIT A2 (2026-08-15) — the six unbaked-queue fixes ──────────────────────
check "analysis/liquidity_mapper.py"     "frame_start > start"          "A2.1 left-truncated section guard (wrong-price pools)"
check "analysis/liquidity_mapper.py"     "_ny_utc_hours"                "A2.5 NY section hours derived from ET offset (2026-11-01)"
check "main.py"                          "named_df=_named_level_frame()" "A2.1 deep 1h store frame feeds named levels"
check "main.py"                          ".feed_frame(df_1m)"           "A2.4 gap-safe ledger feed (no closed bar skipped)"
check "analysis/liquidity_ledger.py"     "_hydrate_same_date"           "A2.3 ledger survives the bake (restart hydrate)"
check "analysis/liquidity_ledger.py"     '"last_bar_ts": self.last_bar_ts' "A2.3/A2.4 high-water mark persisted for gap recovery"
check "execution/position_manager.py"    "def open_condor_leg_count"    "A2.2 leg count the announcement reads"
check "tests/test_audit2_fixes.py"       "test_a22_why_the_old_site_was_dead" "A2 executing suite present (born-red verified vs 89cbaf6)"
check "main.py"                          "ORB_WINDOW_MINUTES % 5"       "TCS.3 bound reads the 5m frame (1m-only lost 09:30 at ~10:35 ET)"
check "tests/test_opening_range.py"      "test_tcs3_bound_survives_the_1m_rolloff" "TCS.3 executing suite present (born-red verified vs b672ae6)"
# A2.2 — the announcement must live in the MANAGE branch: the checker's old
# call site sits behind has_open_position() and cannot run with a leg open.
_n_orph=$(grep -c "report_orphaned_plan(" main.py 2>/dev/null || echo 0)
if grep -q "pos_mgr.open_condor_leg_count())" main.py 2>/dev/null && [ "$_n_orph" -ge 1 ]; then
    echo "  ✓ PRESENT: A2.2 orphan announcement fires from the manage branch"
else
    echo "  ✗ MISSING: A2.2 orphan announcement not wired where a leg is visible — the F5 warning is dead code again"
    MISS=$((MISS+1))
fi
# A2.6 — ABSENCE canary: the dead session-pool knob must stay gone. Grep the
# ASSIGNMENT pattern, not the bare name — changelogs legitimately mention it.
# grep -c exits 1 when the count IS zero — the expected result here — so the
# usual `|| echo 0` fallback would print a second 0. Capture, then default.
_n_knob=$(grep -c "NAMED_POOLS_INCLUDE_SESSIONS =" analysis/liquidity_mapper.py 2>/dev/null)
_n_knob=${_n_knob:-0}
if [ "$_n_knob" = "0" ]; then
    echo "  ✓ ABSENT:  A2.6 dead session-pool knob stays deleted (ladder never read it)"
else
    echo "  ✗ STALE:   NAMED_POOLS_INCLUDE_SESSIONS assigned again ($_n_knob) — a switch that gates nothing plus a green test is the renders-cleanly class"
    MISS=$((MISS+1))
fi

echo ""
echo "============================================================"
echo "  GIT STATE"
echo "============================================================"
git log --oneline -10 2>/dev/null
echo ""
echo "Remote:"
git remote get-url origin 2>/dev/null
echo ""
echo "Uncommitted changes:"
git status --short 2>/dev/null
echo ""
echo "============================================================"
echo "  PARITY INVARIANT — this checkout vs origin HEAD"
echo "============================================================"
LOCAL_HEAD=$(git rev-parse HEAD 2>/dev/null)
REMOTE_HEAD=$(timeout 10 git ls-remote origin HEAD 2>/dev/null | awk '{print $1}')
if [ -z "$LOCAL_HEAD" ]; then
    echo "  ✗ PARITY: not a git checkout — cannot verify"
    MISS=$((MISS+1))
elif [ -z "$REMOTE_HEAD" ]; then
    echo "  ⚠ PARITY: origin unreachable — HEAD is ${LOCAL_HEAD:0:12} (UNVERIFIED, not failed)"
elif [ "$LOCAL_HEAD" = "$REMOTE_HEAD" ]; then
    echo "  ✓ PARITY: checkout == origin HEAD (${LOCAL_HEAD:0:12})"
else
    echo "  ✗ PARITY BROKEN: local ${LOCAL_HEAD:0:12} != origin ${REMOTE_HEAD:0:12} — re-sync before trusting this session's data"
    MISS=$((MISS+1))
fi
DIRTY=$(git status --porcelain 2>/dev/null | grep -cv "^??")
if [ "$DIRTY" -gt 0 ]; then
    echo "  ⚠ PARITY: $DIRTY tracked file(s) locally modified (listed above) — a green fingerprint on a dirty file proves nothing about origin"
fi
echo ""
echo "============================================================"
if [ "$MISS" -eq 0 ]; then
    echo "  DONE — ALL CANARIES GREEN"
else
    echo "  DONE — $MISS CANARY/PARITY FAILURE(S) — DO NOT TRUST THIS SYNC"
fi
echo "============================================================"
