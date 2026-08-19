"""
main.py — options_trader_smc v6.24
v6.24  2026-08-19  🔴 ICT GRADING WAS HOSTAGE TO ENTRY PERMISSION. SPLIT.
       v6.22 placed the whole ICT branch inside attempt_new_entry — which has
       five early returns above the insertion point (daily-loss halt,
       session.can_enter, stale regime book, chain-fetch failure, the UNKNOWN
       hard gate) and is itself called only in an `else`, skipped whenever a
       position is open or condor legs are being managed. Result on the first
       live morning: ZERO ict_setup rows, with no error anywhere — the suite
       imported fine, raised nothing, and simply was never reached.
       ⚠️ My own v6.22 wiring test asserted the branch was INSIDE
       attempt_new_entry and reported that as a virtue. It pinned what I had
       built instead of the property that was asked for.
       Now split: the GRADING pass (build_context + evaluate_all +
       journal_setup_state) runs unconditionally in run_regime_classification,
       needs no chain, and journals on ticks where no entry was possible —
       which is the point, since a setup that formed while a position was open
       is exactly the observation that tells us what the ranking costs. The
       ACTION path (ict_dispatch) stays in attempt_new_entry and now CONSUMES
       ctx["ictx"] rather than rebuilding it, so the state journaled is the
       state the entry decision was made on. No ictx ⇒ no dispatch: acting on
       a context we could not journal is the worst of both.
v6.23  2026-08-19  ORB IS BLOCKED UNDER RANGING (operator direction: that
       cell is the conclusive loss leader). The refusal is JOURNALED as
       `gate_block:orb_ranging` rather than being a silent absence — without
       that row, "ORB did not set up" and "ORB was forbidden" are
       indistinguishable in the record, and only one of them is a decision we
       can audit or reverse. Implemented as a leading branch with the existing
       ladder moved to `elif`, so RANGING is refused BEFORE the permissive
       ORB_FIRES_REGARDLESS_OF_REGIME clause can readmit it. Flag:
       OT_ORB_BLOCK_RANGING=0 restores the old behaviour. Ships to
       options_trader_v3 too — one arm changing is not a comparison.
v6.22  2026-08-19  G6 — ICT PRE-LADDER DISPATCH WIRED. The seven ICT setups
       (strategy/ict, F.13) now evaluate on EVERY tick, ahead of the
       label-keyed priority ladder, because that ladder gates each branch on
       primary_regime and would discard a Silver Bullet for carrying a
       COMPRESSION label. This branch consults no label (operator 2026-08-18:
       a label may be used by a setup that earns something from it, never as
       a silent precondition). A returned None falls through and the ladder
       is byte-identical to v6.21. Runs even when nothing can fire, on
       purpose: the suite journals FORMING states continuously and that
       journal is the only source the priors are ever fitted from. SB/ORB
       share the slot with ICT ranked first and every preemption journaled as
       `preempted:ict_ranked_first`, so the counterfactual stays measurable.
       SAFETY: three gates inside the suite default CLOSED (OT_ICT_ARMED,
       per-setup OT_ICT_<NAME>_VALIDATED, the 11:30 debit cutoff), so this
       can only return None until a validated setup is armed. Import is
       guarded and pages loudly — an unavailable suite must not look like a
       quiet session.
v6.21  2026-08-18  🔴 LAYER-1 HOISTED OUT OF THE L2 BRANCH — two regressions
       the SMC wiring introduced silently, neither about the label.
       (1) SweepReversal COULD NOT FIRE under the smc engine: its dispatch
       gates on ctx["l1"].scores["SWEEP_REVERSAL"] (SWP.1 deliberately stopped
       requiring the LABEL), and ctx["l1"] was only ever assigned inside the
       `_REGIME_ENGINE == "l2"` branch — so the score read 0.0 on every tick.
       Off by construction, not by decision. (2) regime.flat_angle_deg fell
       back to its default for five strategies + entry_engine, re-opening the
       bug STR.2 had just closed. Also _l1_scores(ctx) returned None, omitting
       the regime-axes decomposition from every journal row this box wrote.
       The scorer produces SETUP SCORES and structural telemetry, not the
       committed label, so it now runs ABOVE the engine branch for every
       engine. L2 is unchanged: same inputs, same call, same position relative
       to the v1.3 classification; it consumes the hoisted result and raises
       into its own existing handler if the scorer failed.
v6.20  2026-08-18  F.2a — ENTRY-CORE PROVENANCE ON THE TRADE ROW. The engine
       is RESOLVED once at import (accounting for a failed smc import falling
       back to L2/v13 — the tag says what RAN, not what was asked for) and
       handed to trade_logger v3.16, which stamps `regime_engine` centrally on
       every entry. That column has existed since 2026-07-30 and nothing ever
       wrote to it. Mandatory before the QQQ cutover: without it, that box's
       history is two entry cores pooled under one symbol.
v6.19  2026-08-18  SMC CORE WIRED (fork: options_trader_smc, candidate QQQ).
       OT_REGIME_ENGINE=smc routes the committed label + confidence from
       smc/smc_engine.py — structure (BOS/CHoCH), dealing-range position
       (premium/discount), draw-on-liquidity, displacement, and an
       ANTICIPATORY setup lifecycle (FORMING/CONFIRMED/REVOKED) journaled on
       every transition as `smc_setup`. A REVOKED setup withdraws entry
       permission in the revoked direction at the post-dispatch choke point
       (permissive-until-disqualified; OT_SMC_REVOKE_GATES=0 disarms).
       l2/v13 remain intact as rollbacks; exits untouched by design.
       Provenance: [SMC c=..] log tag + engine="SMC" on regime_log rows.
       FORK DEFAULT is OT_REGIME_ENGINE=smc — env overrides to l2/v13 roll
       the box back to the parent repo's engines with no code change.
v6.18  2026-08-18  P0 FIX: v6.16/v6.17 wrote ctx["gap"]/ctx["level_near"]
       before ctx existed — run_analysis built its dict only at the return,
       so the NameError raised in the try and the handler's own ctx[...] =
       None re-raised it UNCAUGHT. run_analysis failed on EVERY tick: no
       ctx, no classification, no strategy could ever fire. ctx is now bound
       before the Level.1/A2.6b blocks. Same class as WA §21's
       is_trend_participation NameError; reproduced behaviorally pre-fix.
v6.17  2026-08-18  A2.6b: MEASURE the overnight gap instead of inheriting it
        as an anonymous ATR spike. `atr_series` uses true range with prev_close
        and the 5m tape is continuous, so a large gap spikes ATR at the open and
        decays - every consumer sees a volatility number that is partly last
        night's news and CANNOT TELL WHICH PART. Nowhere was the gap measured
        as itself.
        THE ONLY PRE-OPEN DECISION-TIME INPUT IN THE STACK: ADX, conviction,
        the regime scores and IV skew all need bars from THIS session; the gap
        is fully formed at 09:30 before a single RTH bar prints.
        PRIOR DIRECTION COMES FROM LAST TICK'S REGIME, deliberately: `regime` is
        not bound this early in the tick, and a bare getattr would have raised
        into the except and pinned prior_dir=0 forever - making gap_class
        permanently "UNDIRECTED". A silent constant is the failure this whole
        week has been about.
        CLASSIFICATION IMPORTED from tests/gap_backfill.py, never
        reimplemented (7) - and gap_pct is a REAL column with a NULL default,
        because a gap of exactly zero is a real reading.
v6.16  2026-08-18  Level.1: GRADED LEVEL STRENGTH, FOR EVERY STRATEGY.
        `level_strength` measured 94% ties on TWO unique values. Two causes,
        both collection defects:
        (1) the formula was min(1.0, (0.6 if named else 0.2) +
            min(touch_count,4)*0.1) and TOUCH_COUNT IS A CONSTANT - named pools
            hardcode it to 1 and nothing increments it (44,450 of 44,890 ticks
            read exactly 1), so it only ever produced 0.7 or 0.3.
        (2) only `sweep_reversal` wrote it, and sweep is hard-gated with a 0.4%
            live win rate - so 94% of the book carried the column default.
            THE PROBE NEVER MEASURED LEVELS; IT MEASURED AN EMPTY COLUMN.
        Now graded by TYPE with a rung discount (analysis/level_grade.py), and
        `ctx["level_near"]` puts the nearest graded pool in front of EVERY
        strategy each tick. `swept_level_name` had no writer either and now
        does.
        GRADES ARE STATED PRIORS, NOT FITTED - ordering follows resting
        liquidity. Fitting on P&L would repeat the grade inversion (A-grade
        -$8,244 vs B +$1,893).
        UNBLOCKED BY LIQ.6 (rung in the name) AND FEED.2 (ON High/Low real).
v6.15  2026-08-18  STR.2: carry `flat_angle_deg` from the L1 breakdown onto
        the regime state. FIVE strategies already read `regime.flat_angle_deg`
        and ALL FIVE took the default, because RegimeState had no such
        attribute - so trades.flat_angle_deg came back 100% tied on ONE unique
        value and the separation probe read it as a measured zero.
        The quantity was never missing: regime_confluence.flat_angle_deg() runs
        on every RANGING/COMPRESSION evaluation and lands in the breakdown as
        {"angle": ...}. COMPUTED, RECORDED IN THE EVIDENCE, NEVER DELIVERED -
        the same shape as `direction_conf`. Third instance of that class in a
        week.
        THE SENTINEL IS -1.0, NOT 0.0: zero degrees IS the flattest possible
        reading, so a 0.0 default is indistinguishable from a genuinely flat
        tape - exactly the confusion that produced the bug.
        WHY IT MATTERS MOST: the angle is a STRUCTURAL read, not a magnitude
        one - slope of the recent window in ATR units, the closest thing
        collected to "is price going anywhere or just rotating".
v6.14  2026-08-17  P0.3: all seven `regime_ctx` call sites now pass the RAW
        L1 score vector, via `_l1_scores(ctx)` reading `ctx["l1"].scores`
        defensively. Emission only - no gate, no size, no behaviour change.
        A malformed ctx returns None and the axes are simply ABSENT, which is
        distinguishable downstream from zero; a 0.0 default would not be.
v6.13  2026-08-17  TCS.4: THE FIRST TC.6 TRADE THAT FORMED CORRECTLY DIED AT
        THE WRITE, AND CRASH-LOOPED A LIVE BOX. `_execute_condor_leg` set
        `is_trend_credit` on the record; `log_entry` INSERTs every record key;
        the field has NO COLUMN. OperationalError on the INSERT -> loop error
        cap -> service shutdown -> restart -> again, every 15s for the rest of
        NFLX's session.
        IT NEVER FIRED BEFORE because TC.6 could never REACH execution - TCS.3
        fixed the bound at noon and exposed it hours later. A latent defect
        surfaced by a fix.
        WHY THE FIELD EXISTED (checked before removing): `ed9d30a` (08-13) made
        it the EXIT ENGINE'S DISCRIMINATOR - `if bool(record.get(
        "is_trend_credit"))` routed TC.6 to breach-or-nickel. On 08-14 it was
        found not to be a column, so every restart lost it and the branch
        silently stopped firing; `structure.py` was built to replace it by
        DERIVING from persisted `strategy`/`setup_type`. The read side moved.
        The write side was never cleaned up. It is vestigial, not spurious.
        WHY REMOVED AND NOT ADDED AS A COLUMN: WORKING_AGREEMENT 22, written on
        08-14 about THIS FIELD - "PREFER DERIVING. A new column fixes tomorrow
        and not today: every position opened before the migration still
        rehydrates without it, SELECT * returns None, and None reads as False -
        the exact failure, silently."
        THE SIGNAL ATTRIBUTE `sig.is_trend_credit` IS UNTOUCHED - in-memory
        only, read via getattr to set `_is_tcs`, never persisted.
v6.12  2026-08-17  TCS.3: THE BOUND OUTLIVED ITS FRAME. `_opening_range`
        read the 60-bar 1m cache and the 09:30-09:35 bars leave that window
        at ~10:35 ET — 25 minutes before TCS_START_ET — so trend
        participation (TC.6) was structurally unable to fire: the bound was
        None for the entire credit window on every box since d12ee3e baked
        (Fri 08-14). Fleet-verified before fixing (13/15 boxes logging
        `[tcs] no opening-range`, up to 290/290 evaluated ticks). The range
        now reads TODAY'S 09:30 5m bar (exact for a 5-minute window, present
        all session on every tape), with the 1m window kept for the early
        session and non-5m window sizes; both paths date-filtered. Same
        failure class as AUDIT A2.1, one function over: a lookback written
        against history the frame does not carry.
        NOTE: FEED.2 (2026-08-15) edited this file (_EXT preference in
        _named_level_frame) without a title bump — recorded here so the
        version history stays truthful; no behaviour change beyond FEED.2's
        own.
v6.11  2026-08-15  AUDIT A2: four fixes from adversarial audit #2.
        (A2.1) named levels get a DEEP frame: `_named_level_frame()` reads the
        candle store directly (1h bars, NAMED_FRAME_1H_BARS, 300s TTL) and is
        passed to the mapper as `named_df` - the cached 5m frame is 100 bars
        (~8.3h) and was feeding the 10-day section lookback truncated tape:
        wrong pool prices, rungs mutating intraday. Store precedent is PF.2
        ("the history was never missing - the frame was"). Fails soft to the
        old behavior (mapper guards truncation on any input).
        (A2.2) the F5 orphan announcement MOVED to the manage branch. Its old
        home, `_condor_leg_open_without_plan`, is only called inside
        attempt_new_entry, which only runs when has_open_position() is False -
        and that falls back to the SAME get_open_trades(). While an orphan leg
        was open the call site was unreachable; when reachable, the count was
        by construction zero. The v6.10/v4.83 danger model (TC.6 opening a
        second spread against an orphan) was impossible for the same reason -
        the fix guarded a scenario the gate already forbids, with a guard the
        gate made unreachable, and the once-per-restart WARNING could never
        fire. It now fires from the has_open_position branch, where an open
        leg can actually be seen. The checker itself is now side-effect-free
        and stays as belt-and-braces on the TC.6 dispatch.
        (A2.4) ledger bar selection moved into the ledger: feed_frame() walks
        every closed session bar newer than the persisted last_bar_ts - the
        old iloc[-2] + one-stamp guard silently DROPPED bars on any tick
        slower than ~75s, undercounting exactly the busy tape.
        (A2.9) an empty first-tick seed no longer latches the date - the
        ledger retries seeding until the mapper produces named pools; and the
        wiring routes through get_ledger() so there is ONE singleton, not two.
v6.9 — 2026-08-14 — AUDIT F6: A TC.6 RECORD IS NOT A CONDOR LEG.
        `_execute_condor_leg` still stamped is_condor_leg=1 and
        condor_leg_num=2 onto every trend credit spread, called
        notify_leg_filled() on its fill (advancing a condor plan state machine
        the trade has nothing to do with — a no-op today only because TC.6
        defers whenever a plan is active: a gate, not a guarantee), and sent a
        Telegram entry alert advertising a stop for a trade whose record
        deliberately carries stop_premium=0.0 — a lie on the exact channel
        that caught the last identity bug. All three now condition on _is_tcs.
        The two persisted fields were spoofing `_condor_sibling_open` (an
        opposite-side open TC.6 would make a standalone condor leg read
        "formed": ratchet and TP suppressed) and `condor_roll`'s leg discovery
        (could have closed a TC.6 leg as rolled_to_broken_wing).
        ⚠️ position_manager v3.2 lands in the SAME commit: its premium fetch
        keyed on is_condor_leg, which this change removes from TC.6 rows —
        without v3.2 the spread pricing silently falls to the single-leg path.
        That pairing is the hop this fix would have broken if shipped alone.
v6.8 — 2026-08-14 — TC.6 IDENTITY THROUGH THE EXECUTION PATH.
        `_execute_condor_leg` hardcoded condor identity onto every record it
        built, so `is_trend_credit` and `underlying_stop` never reached the
        trade and the exit branch gated on them COULD NEVER FIRE. Every trend
        credit spread inherited the condor ratchet and the 25%% premium stop.
        Identity now derives from the SIGNAL: strategy, regime, underlying_stop,
        is_trend_credit, and stop_premium=0 for a trend credit spread.
v6.7 — 2026-08-14 — `_opening_range()`: the ORB high/low recomputed FROM THE
        TAPE as trend PARTICIPATION's bound. Separates the ORB ENGINE (no
        runaway gate, no slot arbitration past 11:00) from the ORB LEVEL (a
        price, not a dependency). Restart-proof and available past the cutoff.
v6.6 — 2026-08-14 — AFD.1 MOVED TO PRE-DISPATCH. It was a POST-SELECTION veto,
        so past 11:00 a debit strategy still WON the slot: `signal` went
        non-None, TC.6 (behind `if signal is None`) never ran, and the debit
        signal was refused afterwards — **the tick produced NO trade and the
        afternoon slot was consumed by a strategy forbidden to trade in it.**
        Likely the real reason TC.6 fired zero times on 2026-08-14, independent
        of the runaway gate. ORB / Continuation / Sweep are now SKIPPED, not
        evaluated-then-refused. The post-selection gate is retained as defence
        in depth.
v6.5 — 2026-08-14 — TC.6 v2.0 call site: no `orb`, pass `trend`. The runaway
        gate was slot arbitration, not anchoring — after 11:00 ORB owns nothing.
v6.4 — 2026-08-13 — TC.6 WIRED. TrendCreditSpread dispatches after the condor
        and routes through `_execute_condor_leg`, deferring when a condor plan
        holds the symbol. Exit is BREACH-OR-NICKEL via `is_trend_credit`
        (exit_engine v4.17) — the measured +$0.52/spread was HELD TO EXPIRY,
        UNMANAGED, so the ratchet and 25%% stop are deliberately unreachable.
v6.3 — 2026-08-13 — PF.5 WIRED. The condor now consults the DAILY pitchfork and
        the session extremes. `_condor_rails()` returns the rails or None, and
        **None means NO CONDOR** — operator: "consider the condor off the table
        if we don't have guardrails. That is the insurance policy that
        eliminates a bad decision in an unpredictable session." Measured cost on
        2026-08-12: 13 distinct daily forks across 7 of 15 boxes, so roughly
        half the fleet becomes condor-ineligible. Accepted.
        `_session_extremes()` takes the max across BOTH frames — each is a
        rolling window and neither is guaranteed to reach 09:30. A late window
        UNDERSTATES the extreme, which loosens the filter rather than tightening
        it, so the failure direction is a missed rejection not a wrong one; the
        strategy logs a missing extreme as a plumbing fault rather than trading
        with the filter silently off.
        This is the pitchfork overlay's FIRST CONSUMER — it has been live as a
        weight-0 observer since 2026-08-12 with one call site and nothing
        reading the rails back.
v6.2 — 2026-08-13 — AFTERNOON DEBIT BLOCK. Operator: "The only other Long that
        can fire is either part of a butterfly or an iron condor vertical
        spread from 11 o'clock onwards." ORB/Continuation/SweepReversal are
        refused past DEBIT_DIRECTIONAL_CUTOFF_ET (11:00 ET, env-tunable).
        PLACED AFTER THE SIGNAL IS CHOSEN, not at dispatch: one gate instead of
        three, so a strategy added later cannot silently bypass the rule; the
        refused signal is fully formed so the journal records WHAT WAS REFUSED
        (a gate that vetoes invisibly can never be calibrated from its own
        rejections — the reasoning that put gates E and F after the score in
        setup_scorer); and condor legs never reach it, having routed through
        `_execute_condor_leg` above, so the credit path is exempt BY
        CONSTRUCTION rather than by a list entry that could rot.
        ENTRIES ONLY — open positions manage normally.
        ⚠️ IN A TRENDING AFTERNOON THIS LEAVES NOTHING: the condor self-gates to
        RANGING and the butterfly needs PINNING GEX. That window belongs to the
        trend credit spread (TC.6), which is NOT BUILT. Dark on purpose until
        it is — the measured cost of that window is negative.
v6.1 — 2026-08-11 — RGM.6: THE FALLBACK RESOLVES TO A KNOWN LABEL.
        Operator: "unknown should be virtually eliminated by the time we freeze
        layer 1… there should be ways to extrapolate and resolve to a KNOWN
        label." The diary sizes it exactly: **L1 is all-zero on only 2.4-3.0% of
        ticks on EVERY session since 07-15**, while the v13 fallback emitted
        UNKNOWN on ~18-19%. A known answer existed roughly SEVEN TIMES more
        often than we were genuinely blind, and it was discarded.
        v5.0's hold covered STALE ticks. The other fall-through — the code's own
        "empty committed label on a WARM book" — went straight to v13, which
        re-derives from scratch with NO MEMORY and says UNKNOWN when nothing
        matches its ladder.
        THE LADDER IS NOW: committed L2 -> held incumbent -> **L1 ARGMAX** ->
        v13. UNKNOWN is reserved for the ~2.4% that are genuinely all-zero.
        ⚠️ CONVICTION IS CARRIED, NOT INVENTED. An L1-argmax label carries L1's
        RAW score, which is below theta_commit by construction — that is the
        point. Downstream gates that read conviction see a weak label as weak.
        ⚠️ THE ENGINE TAG IS NOW FOUR STATES: [L2 c=] committed, [L2-hold c=]
        incumbent, [L1 c=] argmax, [v13] true fallback. `grep -c '[v13]'` has
        been the fallback-rate measure all week — with the split, a DROP in it
        must not be read as a fix when it is a relabelling.
        ⚠️ EXPECT UNKNOWN TO FALL TOWARD ITS ~2.4% FLOOR and the labelled
        population to grow a low-conviction tail. Per-regime statistics are
        therefore NOT poolable across this deploy.
        Kill switch: OT_RGM6_L1_ARGMAX=0 restores the pre-RGM.6 ladder exactly.
v6.0
v6.0 — 2026-08-10 — CNT.6: CONTINUATION IS BLOCKED IN RANGING AND COMPRESSION.
        A trend continuation is a trend RESUMING after a pullback. RANGING and
        COMPRESSION are the assertion that there is no trend to continue, so the
        entry contradicts its own premise — this is a correctness defect, not a
        permissiveness setting.
        ⚠️ THE MECHANISM WAS THE `_is_runaway` BYPASS. The gate read
        `_is_runaway OR regime in (TRENDING_BULL, TRENDING_BEAR, BREAKOUT)`, so a
        runaway ORB flag skipped the label check entirely and continuation fired
        on ANY tape at Priority 2 — ahead of Butterfly (P3, RANGING/COMPRESSION)
        and Condor (P4, RANGING), both behind `if signal is None` and therefore
        never evaluated. The operator saw it as condors and butterflies going
        extinct; the cause was a dispatch bypass, not an absence of setups.
        MEASURED, 13 sessions: RANGING → Continuation 94 vs IronCondor 27 ·
        COMPRESSION → Continuation 39 vs Butterfly 6. Continuation took 3.5x the
        condor's opportunities and 6.5x the butterfly's, inside the regimes those
        strategies exist for.
        ⚠️ WHY IT IS IN DISPATCH AND NOT IN THE STRATEGY: CNT.3 already blocked
        the COMPRESSION handoff INSIDE continuation_strategy and the squeeze
        continued, because a strategy-level veto still CONSUMES THE SLOT on its
        way to returning None. Only a gate above the call frees P3/P4.
        ⚠️ EXPECT FEWER CONTINUATION TRADES AND THE RETURN OF BUTTERFLY/CONDOR.
        Do not read the drop in continuation volume as a regression — it is the
        change working. Kill switch: OT_CONT_BLOCK_PREMIUM=0.
        SEPARATE AND NOT ADDRESSED HERE: RANGING is emitted on only ~2% of L2
        ticks, so the condor is ALSO starved by the label itself. Freeing the
        slot is necessary but not sufficient for condor volume.
v5.9 — 2026-08-08 — L1 EVIDENCE ON THE FIRED DISPOSITION. The sweep collection
        is meant to characterise what made a good ENTRY good, and the journal
        was recording only the regime's label and conviction — every
        contributing term that decided the entry was computed at the fire and
        then discarded. Reconstructing them later means replaying the tape and
        hoping the replayed score matches the one that fired, which is an
        approximation sitting exactly where the analysis lives. Now records the
        six-score vector on every fire, plus the firing setup's own L1
        breakdown via `_L1_BREAKDOWN_FOR`.
        ⚠️ A WRONG MAPPING IS SILENT — it files a well-formed breakdown from the
        wrong scorer. ORB is deliberately unmapped (regime-immune by design);
        an unmapped strategy records no breakdown rather than a wrong one.
        Log-only: no gate, no dispatch and no sizing reads any of this.
v5.8 — 2026-08-07 — MEM.2: in-process tracemalloc, gated by OT_MEM_TRACE.
        The standalone probe failed FOUR times in an afternoon and never once
        for a reason about memory — wrong box, un-pulled file, `tmux sh -c`
        inheriting neither .bashrc nor the unit environment (so no credentials
        and OT_INSTRUMENT defaulting to QQQ on the SPX box), and finally an
        `xargs env` workaround that echoed every secret to the terminal. All
        four are the same root cause: a second process cannot easily inherit the
        trading environment. **The bot already has it.**
        Costs one bool test per tick when off; tracemalloc is not even imported.
        ⚠️ When ON it adds ~10-30% memory overhead, which on a 951 MB box is
        itself a risk — enable on the RESIZED SPX box only, never fleet-wide.

v5.7 — 2026-08-07 — CNT.1: CONTINUATION DISPATCH OPENED TO BREAKOUT_VOLATILE.
        Operator's call, to gather data. The bar was structural, not a quality
        judgement: continuation derives DIRECTION from the label, and
        BREAKOUT_VOLATILE asserts volatility expansion without saying which way,
        so no branch could assign one. continuation_strategy now takes direction
        from `trend.overall_direction` when the label is BREAKOUT, gated on
        `primary_adx >= CONT_BREAKOUT_MIN_ADX` (default 25) — an ADX bar rather
        than a conviction bar, because under a non-trending label continuation's
        conviction floor is skipped and BREAKOUT's conviction is not the trend's.
        Entries are tagged `trend_continuation_breakout` so the cross-day rollup
        scores this path separately from _standalone and _handoff.
        Kill switch: OT_CONT_BREAKOUT_DIRECTION=0.

v5.6 — 2026-08-07 — SWP.1: SWEEP UNGATED FROM THE REGIME LABEL. Operator's
        ruling — sweep is an EVENT, not a market state. The dispatch required
        `regime.primary_regime == Regime.SWEEP_REVERSAL`; that label wins 0.4%
        of live ticks, is exactly zero on 96%, and F7's commit threshold made it
        rarer still. Dispatch now gates on the L1 `_sweep` SETUP SCORE
        (>= SWEEP_SETUP_FLOOR), captured from the confluence result this loop
        already computes. The score's three hard vetoes ARE the stated spec:
        named level, rejected back through, not accepted beyond. The PLTR
        trend-opposition guard is a soft-necessary INSIDE that score, so it
        survives the change — it never lived in this gate.

v5.5 — 2026-08-06 — LIVE A/B ON THE EMISSION LAW (RGM.1 F7). conviction_
        integrator v2.1 closes the unprotected branch: below theta_hold the
        incumbent was replaced by bare argmax every tick, which accounted for
        96.9% of 8,345 label switches across 19 sessions at a median incumbent
        conviction of 0.08. v2.1 now runs BOTH laws on every tick and reports
        the other one's label as `shadow_regime`; this file logs the pair
        whenever the divergence CHANGES (never per tick). Nothing reads the
        shadow to trade. Kill switch: OT_L2_PROTECT_BELOW_HOLD=0 restores the
        v2.0 law exactly, and the shadow then models v2.1 — so the A/B reads
        the same in either direction and one env var runs the control.

v5.4 — 2026-08-04 — ORB WAS BEING GATED BY THE STALE-BOOK ENTRY BLOCK, AND THAT
        WAS NEVER INTENDED. v5.0 put the block ABOVE the dispatch, so it
        returned before `orb_regime_bypass` ran and
        ORB_FIRES_REGARDLESS_OF_REGIME — the constant defect V exists to
        provide — became unreachable on a stale tick. MEASURED, not inferred:
        the block ran 09:35:01 → 09:39-09:41 ET on ALL 15 boxes on 2026-08-04,
        which is the first four to six minutes of ORB's own entry window (ORB
        opens 09:35:00 sharp). Every session since v5.0 deployed lost that
        window fleet-wide, and the flagship is the strategy the morning belongs
        to.
        A CONFIRMED ORB (OPEN_LONG / OPEN_SHORT) is now exempt. Nothing else is:
        continuation, condor, butterfly and sweep all condition on the label and
        stay blocked, so v5.0's actual protection is intact.
        THIS IS NOT "IGNORE STALE". `stale` is the regime BOOK; the feed has its
        own guard, latch and pager. A confirmed ORB break on a stale book reads
        fresh price and no label at all.
v5.3 — 2026-08-04 — W.2: _capture_entry_snapshot's handler now logs inside the
        except itself. It always warned, but the census reads the HANDLER BODY,
        so it was counted SILENT — and a census that miscounts is worse than
        none. No behaviour change.
v5.2 — 2026-08-04 — NO REGIME-FLIP EXIT ON A STALE BOOK (operator directive).
        v5.1 blocked ENTRIES on stale and held the committed label, but a HELD
        label is still a label: `_evaluate_continuation` fires `regime_flip` on
        any label that is not TRENDING in the trade's direction, so a position
        could still be closed on a classification the engine could not confirm
        at that moment. And on a COLD book — stale with nothing committed —
        main fell back to v1.3 raw argmax, which is the churn L2 exists to
        remove, feeding it straight into the exit that checks regime SECOND,
        before any price stop. That is the 07-23..08-03 flicker mechanism with
        one branch left open.
        THE FIX IS ONE ARGUMENT, NOT A NEW GATE: pass `regime=None` into the
        exit path while the book is stale. All three regime-driven exits
        already guard on the label being present — `regime_flip`,
        `regime_flip_adverse` (condor) and the butterfly `regime_flip_exit` —
        so None disables exactly those three and nothing else.
        EVERY PRICE-BASED EXIT STILL RUNS: 15:45 hard close, stop, max_loss,
        trail, FVG trail, break-of-structure, condor ratchet, nickel close,
        theta. Stale means the regime BOOK has not resolved; it is not evidence
        the price feed is down, and refusing to stop out on it would be a
        different and worse rule. A 0DTE position must still flatten at 15:45.
v5.1 — 2026-08-04 — ENTRY SNAPSHOT HOOK (log-only, freeze-safe). Every confirmed
        fill — directional and both condor legs — now persists the entry-time
        FVG/structure picture to trades.entry_snapshot via
        analysis/entry_snapshot.py. Runs AFTER the record is written, so it
        cannot reach the entry decision, the size, the strike or any exit; the
        only thing it can do to a live position is nothing.
        WHY HERE AND NOT IN entry_engine: one call site per path, in the file
        that owns ctx, and it keeps a second lineage out of another agent's
        file (working agreement §7). The condor helper gains an optional ctx
        for the same reason — both of its callers already hold one.
        THE CAPTURE'S OWN FAILURE IS AUDIBLE. set_entry_snapshot returns a
        boolean and the payload carries `err`; a miss logs once per reason per
        process (the _log_backfill_depth idiom, §17) rather than every fill or
        never. A snapshot hook that fails silently would leave a column of
        NULLs indistinguishable from a day with no trades — which is the exact
        shape of every observability defect this repo has paid for.
v4.9 — 2026-07-30 — DISPATCH ISOLATION. Each strategy evaluation now runs inside
        _safe_strategy(): a raise is logged at ERROR and returns None, so the
        priority cascade continues instead of aborting the tick. Before this, one
        strategy raising silently disabled every strategy BELOW it — butterfly's
        `_mult` NameError (Priority 3) suppressed the iron condor (Priority 4) on
        every RANGING/COMPRESSION tick where GEX was pinning, and nothing in any
        log said the condor had been skipped. Applies to all six dispatch call
        sites plus the Leg-2 check in the tick loop.
v5.0 — 2026-08-03 — STOP TRADING ON THE UN-SMOOTHED CLASSIFIER. Two rules, no
        new parameter, nothing to tune.
        THE DEFECT: `st.regime and not st.stale` was read correctly, but the
        FALLBACK was wrong. On a stale tick the bot dropped to the v1.3
        classifier — raw L1 argmax — which is precisely the churn L2 exists to
        remove (436 committed switches vs 695 argmax flips). exit_engine checks
        regime-flip SECOND, before any price stop, so a single wobbled tick
        closed the position. MEASURED over 2026-07-23..: regime_flip exits have
        median hold 0.8 min and p25 12 SECONDS, against 5-12 min for every other
        exit reason; 19% of continuation exits and 27% of iron-condor exits.
        A 12-second position has not had time to be right or wrong — only to pay
        a round trip. And the trigger is routine: v4.6's own note records that
        "a tick gap over dt_max=90s re-stales every tick".
        THE FIX: (a) on a stale tick WITH a committed label, HOLD that label
        instead of falling back; (b) take NO NEW ENTRIES while stale. Holding is
        declining to act on unknown information — the position stays protected
        by every price-based stop, none of which read the label. Entering is a
        DECISION and is refused.
        A COLD BOOK AT THE OPEN STILL FALLS BACK TO v1.3 — that path was always
        correct (no prior state exists to hold) and is unchanged.
        WHY THIS MATTERS EVEN THOUGH LOSSES ARE ACCEPTABLE RIGHT NOW: the fleet
        is deliberately permissive to collect a broad sample. A flickered exit
        does not just cost $48, it writes a row tagged
        "ContinuationStrategy / TRENDING / -$48" that will later be counted as
        evidence about continuation in a trending regime. It is not — it is
        evidence about an exit mechanism. The fix does not reduce firing; it
        stops premature exits, so each trade actually expresses its setup.
v4.8 — 2026-07-30 — DECLARE THE OPENING GAP, AND STAMP THE ENGINE.
        (a) The first ~25 minutes of every session legitimately cannot produce
        RANGING or COMPRESSION: both are computed on a 25-bar 1-MINUTE window,
        and market_data deliberately scopes the 1m frame to the current session
        (OT_FEED_INTRADAY_SCOPE=session) so it can never bleed across the
        overnight gap and fabricate a slope. v4.6 announced that designed
        condition at WARNING as "NOT L2.5-grade" and fired it on 13 of 15 boxes
        at 09:30 on 2026-07-30. It now logs INFO ("warming as designed", naming
        the dims and the frame depth) when ONLY window-dependent dims are missing
        AND the frame is still filling, and keeps the WARNING — now carrying
        df_1m — for every other starve, which really is a fault. Deliberately NOT
        fixed by padding the frame (that is what the guard prevents) nor by
        fabricating a low value (synthetic data would enter the calibration set)
        nor by weakening the integrator's full-vector invariant.
        (b) regime_log rows now carry `engine` ("L2" | "v13"), and trades carry
        `regime_engine`. Provenance was previously recoverable only from a
        [L2 c=..]/[v13] tag in bot.log — which is why "has L2.5 ever committed?"
        took a fleet-wide grep across 138k-line logs. It also makes the designed
        v1.3 opening window excludable from L2-conditioned fits by a WHERE
        clause instead of by inference. Auto-migrates via ALTER TABLE (v-obs
        pattern); observability only, no trade-mechanics change.
v4.7 — 2026-07-29
v4.7 — 2026-07-29 — **L2.5 WAS NEVER REACHABLE.** Root cause of every symptom
        chased today. `_REGIME_ENGINE` is built with `.lower()`, yielding "l2",
        and BOTH gates compared it to the uppercase literal "L2" — at the tick
        override (was line 482) and at the startup warm-load (was 1749). "l2" ==
        "L2" is False, so the L2.5 block has never executed on any box since
        v4.0 wired it, and no environment variable could have helped because the
        DEFAULT itself failed the comparison. This is why a fleet-wide grep of
        34k-138k-line bot.logs on all 29 boxes returned L2=0, FAILED=0, STALE=0
        and integrator_state.json had never been written: nothing inside the
        block — commit, save, load, even the failure handler — was ever reached.
        The v4.5 import fix and v4.6 observability were both real and both
        irrelevant to reachability. Fixed by comparing lowercase at both sites,
        plus a start-up assert that refuses to boot on an unrecognised value
        rather than silently selecting an engine nobody chose, and a start-up log
        line naming the active engine so "which engine is running?" is answerable
        from line one of the log instead of inferred from regime tags.
v4.6 — 2026-07-29 — THE SILENT L2 GATE IS NOW AUDIBLE. v4.5 fixed the import,
        and a probe against the real classes confirmed L2 commits from tick 1
        on a full evidence vector (TRENDING_BULL, conviction 0.984). But three
        conditions must hold for L2 to override v1.3, and only two of them
        logged anything: `st.regime and not st.stale` failing was completely
        silent. Since ConvictionIntegrator clears `stale` ONLY when every
        dimension of the evidence vector is non-None, one perpetually-None
        dimension pins the book stale indefinitely and every REGIME line prints
        [v13] with no warning anywhere — which is exactly why "did L2.5 land?"
        was unanswerable from the logs. The non-committing branch now reports
        the reason and names the missing dimensions, throttled to one line per
        change, and announces recovery when it starts committing again. Known
        starvation paths: closes=None (df_1m shorter than RANGE_WINDOW_BARS)
        nulls RANGING+COMPRESSION; a tick gap over dt_max=90s re-stales every
        tick. Observability only — no change to trading behaviour.
v4.5 — 2026-07-29 — L2.5 IMPORT CONTRACT FIXED + SILENT DEGRADATION MADE LOUD.
        `RANGE_WINDOW_BARS` was imported from conviction_integrator, which does
        not define it — it lives in regime_confluence (v1.3, ~line 181) and was
        only ever reachable through a re-export tuple that the 07-28 excavation
        trimmed. The ImportError was swallowed by the L2 guard, so all 15 boxes
        ran the v1.3 classifier for the whole 07-29 session while logging a
        single WARNING per start. Two changes: (a) both symbols now import from
        the modules that OWN them — a re-export is not a contract; (b) the
        fallback logs at ERROR and pages via
        alert_manager.send_regime_engine_degraded_alert (v1.7), because a
        silent engine swap invalidates the session's conviction data for
        calibration even though trading continues unaffected. The pager is
        itself wrapped — it can never take the bot down.
v4.4 — 2026-07-27 — READINESS STAGED PICKS (trade_readiness v1.1, LOG-ONLY):
        while ARMED, continuation/sweep now journal the contract they WOULD
        select via the live selector on SMOOTHED conviction — the calm-vs-
        spike strike experiment. Constructor passes contract_ctx. No entry
        path touched.
v4.3 — 2026-07-27 — TRADE READINESS wired in (LOG-ONLY). New
        analysis/trade_readiness.py evaluates every strategy's pre-trigger
        confluence as a graded readiness R in [0,1] each ~15s tick, with a
        dt-aware slope (R/minute) and a DORMANT->STAGING->ARMED machine that
        journals transitions, heartbeats, and readiness_would_fire moments.
        Gates NOTHING — no fire decision changes anywhere; guarded import
        (loop byte-identical without it), assess errors swallowed. Hooked in
        the every-tick block beside the chain snapshot, deliberately BEFORE
        the has_open_position branch so observation continues while halted or
        holding. ORB exempt (mechanical by directive). This is the sight-
        picture groundwork: where the market IS (instant geometry), where
        it's BEEN (L2 conviction), where it's HEADING (slope on the lowest
        timeframe). Log-only per the pitchfork weight-0 precedent so it rides
        inside the frozen-baseline window; its journal rows calibrate the
        bars that will eventually gate.
v4.2 — 2026-07-23 — FULL OPTION-CHAIN ARCHIVAL (analysis/chain_snapshot.py).
        The bot already fetched the complete 0DTE chain every ~15s tick — bid,
        ask, mark, delta, gamma, theta, vega, IV, OI, volume on every strike,
        ~23,000 full-chain snapshots per fleet-day — and discarded all of it
        except the one selected contract in the signal_journal `scored` event
        (which drops gamma and vega besides). Chains are NOT reconstructible
        after the session: unlike the 1-min tape or deterministic swing pivots,
        a quote for a strike nobody selected is gone permanently at 16:00.
        Now archived to data/chain_snapshots/<date>/<SYM>.jsonl.gz on a
        wall-clock cadence (OT_CHAIN_SNAPSHOT_MIN, default 5). Log-only, gates
        nothing, adds NO fetch. Makes any future strike-selection rule
        retroactively testable instead of a live experiment.
v4.1 — 2026-07-22 — PAPER CONDOR CREDIT via the shared authority (audit
        defect T). The condor leg paper fill applied PAPER_FILL_SLIPPAGE_PCT
        inline while single-leg and butterfly entries had moved to booking the
        bare mark (entry_engine v3.8), so paper friction differed BY STRATEGY.
        It now calls execution/limit_ladder.paper_fill_credit(), the one
        paper-pricing authority, which honours the same knob for every path
        (default 0.0 = book the mark, matching the mid-credit limit live
        actually posts). No live-path change.
v4.0 — 2026-07-21 — L2.5: LIVE regime now driven by the Layer-2 conviction
        integrator's committed label (Layer-1 confluence evidence → integrator),
        replacing the v1.3 boolean classifier's raw argmax as the trade gate.
        Cures the fleet-wide UNKNOWN flicker (v1.3 dropped to UNKNOWN mid-trend
        at avg ADX ~29 — a hard no-trade gate firing during the strongest
        conditions). The integrator holds a regime through single-tick evidence
        drops (theta_hold hysteresis) and never emits UNKNOWN. Gates run WIDE
        OPEN (conviction logged, not gated — L3 tunes bars later); paper P&L is
        the arbiter. v1.3 still runs and populates RegimeState's rich fields;
        only primary_regime/conviction are overridden. Book persisted per box
        (data/integrator_state.json), warm-loaded at boot. Rollback:
        OT_REGIME_ENGINE=v13.
v3.9 — 2026-07-18 — SIGNAL JOURNAL DISPOSITIONS (ROADMAP Phase 3.1, log-only,
        zero behavior change): attempt_new_entry now emits what happened to
        every signal AFTER scoring — `disposition` events for fired /
        sizing_rejected / invalid_signal (below-B REJECTs are already emitted
        by setup_scorer v1.3's `scored` event) — plus `condor_plan` /
        `condor_leg` events carrying regime conviction at decision time (the
        condor bypasses the score path, so without these its conviction bar
        could never be calibrated). ORB dispositions carry retest_depth_px
        (orb_engine v3.7, defect G) and its ATR-relative form. All emissions
        route through analysis/signal_journal (guarded import, every failure
        swallowed) — the trading loop is byte-identical if the journal is
        absent or broken.
v3.8 — 2026-07-15 — pass df_5m through to position management so exit trails
        anchor to 5-minute FVGs (exit_engine v3.8 runner refinements).
v3.7 — 2026-07-15 — CONDOR ENTRY FILL-CONFIRMATION (audit defect O, part 1).
        _execute_condor_leg live path now confirms the fill before ANY record
        exists: submit the signed-credit limit → poll via
        execution/order_confirm.confirm_order_fill (bounded by
        LIVE_ENTRY_DEADLINE_SECONDS) → book ONLY confirmed contracts at the
        broker's per-leg net credit. Unfilled → cancel, walk away, no ghost;
        partial → book the filled size; uncancellable → page, reconcile adopts.
        notify_leg_filled() therefore advances the legging state machine only
        on real fills. PAPER mirrors live friction: condor credit now applies
        PAPER_FILL_SLIPPAGE_PCT (it previously ignored the knob and filled at
        exact mid). price_effect kwarg dropped (ignored by SDK; sign carries
        the credit).
v3.6 — 2026-07-15 — PHANTOM P&L RECOVERY + denser reconcile schedule.
        (a) A phantom (DB open, broker flat — e.g. a manual close at the broker)
            now books its REAL fill: one order-history read per reconcile pass,
            match_closing_fills() finds the closing order(s), phantom_pnl()
            books credit-signed truth into the DB (which DAILY_LOSS_LIMIT
            reads). No matching order (expiry/assignment) -> flagged $0.00 as
            before. Applies to BOTH the startup reconcile (history covers back
            to each phantom's entry date) and intraday sweeps.
        (b) Intraday sweeps every BROKER_RECONCILE_INTERVAL_MIN (default 10,
            was hardcoded 30), PLUS wind-down sweeps at 15:45, 15:50, and a
            final 15:57 post-flatten truth pass (last guaranteed look before
            the loop goes dormant at 16:00).
        (c) Phantom alerts now carry the recovered P&L.
v3.4 — 2026-07-15 — Condor legs now record |short-strike delta| as setup_score
        (a calibration "street-sign", read AFTER the BB-anchored selector
        picks the strike — it does NOT influence selection or sizing). NULL
        when the Greeks feed did not populate delta, so a stored value is
        always a genuine delta. Enables later condor threshold calibration;
        previously condor legs logged no score at all.
v3.4 — 2026-07-15 — handle_hard_close() now fetches the options chain once and
        passes it to flatten_all(), so the 15:45 force-flatten has real marks
        (paper fill price / live context) instead of booking at entry premium
        and logging every leg at +$0.00. Reused across the 15:45->16:00 retries.
v3.3 — 2026-07-13 — defect H rename only: NO_ENTRY_AFTER_ET -> ORB_NO_ENTRY_AFTER_ET
        (import + the orb_state.json "past_cutoff" flag). Same constant, same
        (11, 0) value, same behaviour — the name now states its ORB scope.
v3.2 — 2026-07-11 — REGIME UN-GATE for the flagship ORB (config-switched,
        ORB_FIRES_REGARDLESS_OF_REGIME, default on). A confirmed ORB break+retest
        now fires regardless of the regime label — including UNKNOWN and
        SWEEP_REVERSAL — because the ORB engine's break+retest is self-validating
        and the classifier does not test for it. Two changes in run_entry_logic:
        (1) the hard UNKNOWN gate is bypassed when the engine is in a confirmed
            OPEN state (the label no longer vetoes a proven setup);
        (2) the ORB dispatch admits UNKNOWN and SWEEP_REVERSAL (ORB beats sweep;
            engine no longer defers OPEN under a sweep — see orb_engine v3.2).
        Nothing else loosens: sweep/butterfly/condor still self-gate on their own
        regime values, and the setup scorer's B-threshold still governs (under
        UNKNOWN the regime_conviction dimension just contributes 0). Set the flag
        False to restore strict v2 gating. Every ORB fired under UNKNOWN is logged
        regime=UNKNOWN — labeled tape for the shadow observer.
v3.1 — 2026-07-10 — condor leg ENTRY alert now names the instrument. The leg-
        filled Telegram alert was built with a raw _send() that omitted the
        symbol (every other entry alert routes through the structured methods
        that already include it), so condor entries read "[PAPER] Condor Leg 2
        …" with no way to tell which box fired. Added {INSTRUMENT} after the
        mode, matching the "[MODE] SYMBOL | …" form of the other alerts. DB
        logging already recorded the symbol; this was display-only.
v3.0 — 2026-07-10 — repo-wide v3.0 bump: Yahoo-Finance purge & data stream
        mapping optimization (all market data now flows from the single
        shared TastyTrade candle feed — see data/candle_feed.py). No logic
        change in this file.
v2.13 — 2026-07-07 — INTRADAY broker reconcile (LIVE + enabled): every 30 min
        across RTH with the last sweep at 15:30, a leg-role-aware check catches
        positions the broker closed mid-session — especially a SHORT leg
        auto-closed while the long remains (loud alarm, close the broken record,
        adopt the surviving long so the 15:45 flatten handles it cleanly). Only
        inspects rows we already manage; fail-safe on a bad/empty read.
v2.12 — 2026-07-07 — LIVE broker reconciliation wired into recovery: the broker
        is the source of truth for existence. _reconcile_with_broker() queries
        open positions, KEEPs DB-planned rows confirmed there, ADOPTs+journals
        broker positions with no DB plan (managed by the ADOPTED exit path),
        and closes PHANTOM DB rows the broker no longer shows. FAIL-SAFE: a
        failed or empty broker read never closes anything — falls back to
        DB-only recovery. Paper is unchanged (no broker query).
v2.11 — 2026-07-07 — durable 15:45 flatten + expiry-aware recovery. handle_hard_
        close now routes through pos_mgr.flatten_all() so EVERY open record
        (both condor legs) is truly closed in the DB + P&L booked (the old path
        called place_exit_order directly and never wrote status='closed'),
        retries every tick to 16:00, and pages once on failure. Startup recovery
        keys on EXPIRY, not entry date (the bot trades weeklies): sweep only
        genuinely expired orphans, resume every still-live row, and flag a
        CARRIED-overnight position. Restart alerts self-identify (box symbol +
        fresh-boot vs service-restart from /proc/uptime).
v2.10 — 2026-07-02 — directional-only instruments (single names): skip iron
        condor and butterfly in the dispatch; ORB + sweep only.
v2.9 — 2026-07-02 — block new entries when the daily loss halt is active
        (day P&L <= -DAILY_LOSS_LIMIT_USD); open positions still exit.
v2.8 — 2026-07-02 — (2a) ORB-window sweep override: when an ORB signal fires but
        a sweep reversal has higher conviction, take the sweep. (2b) pass the
        current regime into the ORB engine for regime-gated re-arm. (#3) run
        the broken-wing roll check when both condor verticals are open.
v2.7 — 2026-07-02 — condor legs are now TRACKED positions: each vertical is
        sized at half the grade budget, written to the trade log, registered
        with the position manager (the only two-position strategy), and
        managed/exited per-side. Replaces the phantom notify-only path.
v2.6 — 2026-07-02 — session loss limit forces a regime reassessment instead of
        halting: main_loop consumes RiskManager.consume_reassess_request() and
        reclassifies with trigger="loss_limit".
v2.5 — 2026-07-02 — ORB range is now three-state (ESTABLISHED/IN_PROGRESS/
        EXPIRED) and always carries the last valid range. Startup fetch runs
        unconditionally (populates last-valid EXPIRED range pre-open); the
        open-poll runs from 9:30 ET and latches only when today's range is
        ESTABLISHED. Flag renamed orb_range_fetched_today -> _established_.
v2.4 — 2026-07-02 — remove duplicate _execute_condor_leg (dead 2-arg def shadowed by
        a broken 3-arg def that referenced a non-existent CondorLeg class and
        mark_leg_filled method); single canonical impl on the real OptionsSignal
        API with live TastyTrade placement ported in. ORB range fetch is now
        success-keyed (retries until today's 9:30-9:35 candle is really written)
        and the startup fetch is gated to >= 9:35 ET so it never writes a
        stale prior-day range; instrument read from OT_INSTRUMENT (no systemd
        unit-file parsing).
v2.3 — 2026-07-02 — fix missing ZoneInfo import causing loop error every tick
v2.2 — 2026-07-01 — iron condor legged entry, BB-anchored strikes,
        regime-flip exits, ORB range via get_orb_range.py/orb_range.json,
        fed day trading enabled, ORB cutoff 11AM, condor window 11AM-2PM
v1.0 — original release

0DTE options bot: ORB, Sweep Reversal, Butterfly
RTH only (9:30–16:00 ET), hard close 15:45 ET.
Run modes:
  python main.py            — interactive startup (prompts instrument, risk $, paper/live)
  python main.py --service  — non-interactive for systemd
"""
# v-runaway-fix (2026-07-24) — runaway ORB reroute — hands to CONTINUATION (with-trend on pullback) FIRST, not sweep; post-runaway sweep gated to NAMED levels only. Fixes afternoon-giveback: runaway momentum was being faded by sweep reversal.

# v-obs (2026-07-24) — condor leg entry record now stores adx_at_entry / regime_conviction / flat_angle_deg (from signal, falling back to state.current_regime).


import logging
import logging.handlers
import os
import signal
import sys
import time
import traceback
from datetime import datetime, time as dtime
from typing import Optional
from zoneinfo import ZoneInfo

from config import (
    POLL_INTERVAL_SECONDS, LOG_LEVEL, LOG_FILE, LOG_ROTATION_MB,
    PAPER_TRADING, RISK_PER_TRADE_USD, DAILY_LOSS_LIMIT_USD,
    CONT_BLOCK_PREMIUM_REGIMES,                 # CNT.6
    REGIME_REASSESS_MINUTES, INSTRUMENT, SessionConfig, DIRECTIONAL_ONLY,
    ORB_NO_ENTRY_AFTER_ET, BROKER_RECONCILE_ENABLED, ORB_FIRES_REGARDLESS_OF_REGIME,
    ORB_BLOCK_RANGING,
    DEBIT_DIRECTIONAL_CUTOFF_ET, DEBIT_DIRECTIONAL_STRATEGIES, DEBIT_BLOCK_ACTIVE,
    CONDOR_PF_TIMEFRAME,                        # PF.5
    RTH_OPEN_ET, ORB_WINDOW_MINUTES,            # TC.6 v2.1 — range from tape
    BROKER_RECONCILE_INTERVAL_MIN
)


def _setup_logging():
    import os
    root = logging.getLogger()
    if root.handlers:
        return
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    fh = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=LOG_ROTATION_MB * 1024 * 1024, backupCount=5
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)
    root.setLevel(level)


_setup_logging()
logger = logging.getLogger(__name__)

from utils.time_utils import (
    now_utc, now_et, fmt_et_short, minutes_since, is_rth,
    seconds_until_rth_open, is_hard_close_time
)
from data.data_cache import get_cache
from data.macro_data import get_macro_manager

from data.options_chain import get_chain_fetcher

from analysis.volatility_engine import get_volatility_engine
from analysis.trend_engine import get_trend_engine
from analysis.structure_analyzer import get_structure_analyzer
from analysis.entry_snapshot import to_json as _entry_snapshot_json
from analysis.liquidity_mapper import get_liquidity_mapper
from analysis.regime_classifier import get_regime_classifier, RegimeState, Regime
from analysis.orb_engine import get_orb_engine, ORBState

# ── L2.5 (2026-07-21): wire the Layer-1 confluence scorer + Layer-2 conviction
# integrator into the LIVE regime decision. The committed (integrated) label
# replaces the v1.3 boolean classifier's raw argmax as the regime that gates
# trades. WHY: the v1.3 classifier flickers to UNKNOWN for a single tick at high
# ADX (fleet-wide: UNKNOWN fired at avg ADX ~29, i.e. mid-trend, up to 41 on
# AAPL) — each flicker a hard no-trade gate slamming shut during exactly the
# high-conviction moments. The integrator holds a regime through single-tick
# evidence drops (theta_hold hysteresis) and NEVER emits UNKNOWN — indecision is
# a low conviction number on a best-fit label, not a seventh label. Gates run
# WIDE OPEN this week (conviction logged, not gated — L3 tunes the bars later);
# paper P&L is the de-facto arbiter of L1+L2 quality. Rollback: OT_REGIME_ENGINE=v13.
# v4.7 — the value is LOWERCASED here, so every comparison against it must be
# lowercase too. It was compared to "L2" at both gate sites, which can never
# match "l2" — L2.5 was unreachable dead code from the moment v4.0 wired it.
_REGIME_ENGINE = os.environ.get("OT_REGIME_ENGINE", "SMC").lower()   # "l2" | "v13" | "smc"
assert _REGIME_ENGINE in ("l2", "v13", "smc"), (
    f"OT_REGIME_ENGINE={_REGIME_ENGINE!r} is not 'l2', 'v13' or 'smc' — refusing to "
    f"start rather than silently running an unintended regime engine")
try:
    # RANGE_WINDOW_BARS is OWNED by regime_confluence (v1.3, line ~181). It was
    # previously imported via conviction_integrator, which merely re-exported a
    # tuple of regime-label constants — when the v1.3 excavation trimmed that
    # tuple the import broke and every box silently dropped to the v1.3
    # classifier for a full session (2026-07-29). Import symbols from the module
    # that DEFINES them; a re-export is not a contract.
    from analysis.regime_confluence import RegimeConfluenceScorer, RANGE_WINDOW_BARS
    from analysis.conviction_integrator import ConvictionIntegrator, INTEGRATED_REGIMES
    from analysis.regime_confluence import RANGING, COMPRESSION
    _L2_OK = True
except Exception as _l2e:                       # pragma: no cover
    _L2_OK = False
    # ERROR, not WARNING: this silently changes WHICH ENGINE produces every
    # regime label and conviction value for the session. Trading survives; the
    # session's conviction data is not calibration-grade. Page immediately.
    logger.error("L2.5 UNAVAILABLE (%s) — falling back to v1.3 classifier; "
                 "this session's conviction data is NOT calibration-grade", _l2e)
    try:
        from notifications.alert_manager import get_alert_manager as _gam
        _gam().send_regime_engine_degraded_alert(
            os.environ.get("OT_INSTRUMENT", "?"), str(_l2e))
    except Exception:                           # pragma: no cover
        pass                                    # never let the pager kill the bot

# ── v6.19 — SMC CORE (fork: options_trader_smc) ─────────────────────────────
# OT_REGIME_ENGINE=smc routes the committed label + confidence from the SMC
# structural core (smc/smc_engine.py) instead of the L2 conviction integrator.
# The 2026-08-17 retool verdict: the confirmatory conviction is retired as the
# ENTRY quantity; exits are untouched. l2 and v13 remain intact as rollbacks
# (OT_REGIME_ENGINE=l2 restores the parent repo's behavior exactly).
try:
    from smc.smc_engine import SMCEngine
    _SMC_OK = True
except Exception as _smce:                      # pragma: no cover
    _SMC_OK = False
    if _REGIME_ENGINE == "smc":
        # same severity rule as the L2 import failure: this silently changes
        # WHICH ENGINE produces every label for the session. Page immediately.
        logger.error("SMC CORE UNAVAILABLE (%s) — falling back to L2/v13; "
                     "this session is NOT running the SMC engine", _smce)
_smc_engine = None
if _SMC_OK and _REGIME_ENGINE == "smc":
    _smc_engine = SMCEngine(state_dir=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data"))
_smc_last_setup_phase = None    # journal setup transitions once per change

# ── G6 (v6.22) — the ICT setup suite (strategy/ict, F.13) ────────────────────
# Guarded like the SMC import: an unavailable suite must not take the bot down,
# but it must SAY SO once rather than degrade into "no setup ever formed",
# which is a legitimate reading and would hide the outage.
try:
    from strategy.ict import build_context as build_ict_context, ict_dispatch
    from strategy.ict.dispatch import evaluate_all as ict_evaluate_all
    from strategy.ict.scoring import journal_setup_state as ict_journal_state
    _ICT_OK = True
except Exception as _icte:                      # pragma: no cover
    _ICT_OK = False
    logger.error("ICT SUITE UNAVAILABLE (%s) — the seven ICT setups will not "
                 "be evaluated this session; the label ladder is unaffected",
                 _icte)

_l2_mute     = {}          # v4.6 — last-reported reason L2 is not committing
# v4.7 — state the active regime engine ONCE at import, at INFO. Until now the
# only way to answer "which engine is running?" was to infer it from [L2]/[v13]
# tags on regime-CHANGE lines — which is how a dead L2.5 block hid for weeks.
logger.info("REGIME ENGINE: %s (L2 import %s, SMC import %s) — "
            "OT_REGIME_ENGINE=%s",
            _REGIME_ENGINE, "OK" if _L2_OK else "FAILED",
            "OK" if _SMC_OK else "FAILED",
            os.environ.get("OT_REGIME_ENGINE", "(unset, default smc)"))

# ── v6.20 (F.2a) — RESOLVE the engine tag ONCE and hand it to the trade log ──
# RESOLVED, not intended: if OT_REGIME_ENGINE=smc but the smc import failed,
# what actually labels every tick is the L2/v13 fallback, and the trade rows
# must say so. Stamping happens centrally in trade_logger.log_entry (v3.16) —
# the `regime_engine` column has existed since 2026-07-30 and no caller had
# ever written to it, so every historical row reads ''. Without this, QQQ's
# pre- and post-cutover trades are one undifferentiated population.
def _resolved_engine_tag() -> str:
    if _REGIME_ENGINE == "smc" and _SMC_OK and _smc_engine is not None:
        return "SMC"
    if _REGIME_ENGINE == "l2" and _L2_OK:
        return "L2"
    if _REGIME_ENGINE == "smc":
        return "L2" if _L2_OK else "v13"   # the honest fallback, named
    return "v13"


_ENGINE_TAG_RESOLVED = _resolved_engine_tag()
logger.info("ENTRY CORE (resolved): %s — trade rows carry "
            "regime_engine=%r", _ENGINE_TAG_RESOLVED, _ENGINE_TAG_RESOLVED)
_l1_scorer   = RegimeConfluenceScorer() if _L2_OK else None
_l2_integ    = ConvictionIntegrator() if _L2_OK else None
# v5.5 — last (live, shadow) emission pair, so the A/B logs on CHANGE only.
_l2_ab: dict = {}

# v5.0 — the last label L2 actually committed, held across stale ticks so the bot
# never swaps the smoother for the raw classifier mid-position. `since` is set on
# the first stale tick of a stretch and cleared on recovery, purely so a long
# hold is visible in the log — it gates nothing.
_l2_held     = {"regime": None, "conviction": 0.0, "since": None}
# RGM.6 — 0 restores the pre-RGM.6 ladder exactly (v13 straight after the hold).
RGM6_L1_ARGMAX_FALLBACK = os.environ.get("OT_RGM6_L1_ARGMAX", "1") == "1"
_L2_STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "data", "integrator_state.json")

# v3.9 — signal journal (log-only). Guarded: the loop runs identically without it.
try:
    from analysis import signal_journal as _sigj
except Exception:
    _sigj = None

# v4.3 — trade readiness engine (LOG-ONLY, gates nothing). Guarded the same
# way: the trading loop is byte-identical if the import fails. Emits through
# the signal journal; with no journal it still tracks state silently (harmless).
try:
    from analysis.trade_readiness import TradeReadinessEngine as _TRE
    _readiness = _TRE(emit=(_sigj.journal if _sigj is not None else None),
                      contract_ctx=(_sigj.contract_ctx if _sigj is not None else None))
except Exception:
    _readiness = None

from typing import TYPE_CHECKING
if TYPE_CHECKING:                     # v4.9 — resolves the quoted annotation on
    from strategy.base_strategy import OptionsSignal   # _execute_condor_leg; a
                                      # forward reference never evaluates at
                                      # runtime, so this is lint-clean at zero
                                      # cost and lets the undefined-name gate
                                      # run at ZERO tolerance instead of one.
from strategy.orb_strategy import ORBStrategy
from strategy.sweep_reversal_strategy import SweepReversalStrategy
from config import SWEEP_SETUP_FLOOR
from utils import mem_trace          # MEM.2 — in-process tracemalloc, env-gated

# MEM.2 — start at import. Deliberately placed BELOW this import and not
# beside the engine banner higher up: `_l2_ab` and the banner both live
# above the import block, so a call there is an unbound name. The
# undefined-name gate caught exactly that on the first attempt.
# No-op unless OT_MEM_TRACE is set; tracemalloc is not imported otherwise.
mem_trace.start(logger)
from strategy.butterfly_strategy import ButterflyStrategy
from strategy.iron_condor_strategy import IronCondorStrategy
from strategy.trend_credit_spread import TrendCreditSpread
from strategy.continuation_strategy import ContinuationStrategy

from risk.risk_manager import init_risk_manager, get_risk_manager
from risk.setup_scorer import get_setup_scorer
from risk.session_guard import get_session_guard

from execution.entry_engine import get_entry_engine
from execution.position_manager import get_position_manager

from database.trade_logger import get_trade_logger
from database.trade_logger import set_engine_tag as _set_engine_tag

# v6.20 (F.2a) — stamp the RESOLVED entry core onto every trade row from here
# on. Module-level call: no TradeLogger is constructed, so no DB is opened at
# import. Never fatal — but never silent either: a miss here reproduces the
# exact defect v3.16 exists to fix, so it reports at ERROR.
try:
    _set_engine_tag(_ENGINE_TAG_RESOLVED)
except Exception as _te:                     # noqa: BLE001
    logger.error("could not set regime_engine=%s for trade rows (%s) — rows "
                 "will read '' and the cutover boundary would have to be "
                 "recovered from the cutover DATE", _ENGINE_TAG_RESOLVED, _te)
from utils.blindness_latch import BlindnessLatch, ALERT as _BLIND_ALERT, \
    RECOVERED as _BLIND_RECOVERED
from data.market_data import last_blindness, clear_blindness
from notifications.alert_manager import get_alert_manager


# Strategy singletons
_orb_strategy     = ORBStrategy()
_sweep_strategy   = SweepReversalStrategy()
_butterfly_strategy = ButterflyStrategy()
_iron_condor_strategy = IronCondorStrategy()
# TC.6 — trend credit spread. Sits with the other strategy instances and is
# UNGUARDED on purpose: it imports only config + IronCondorStrategy, both
# already hard dependencies here, so a guarded import would hide a real
# breakage rather than tolerate an optional one.
_trend_credit_strategy = TrendCreditSpread()
_continuation_strategy = ContinuationStrategy()


class BotState:
    def __init__(self):
        self.last_regime_at:   Optional[datetime] = None
        self.current_regime:   Optional[RegimeState] = None
        self.last_regime_name: str = "UNKNOWN"
        self.tick_count:       int = 0
        self.errors_this_hour: int = 0
        self.paper_trading:    bool = PAPER_TRADING
        self.session_reset_done: bool = False   # Reset once per RTH open
        self.orb_reset_done:   bool = False     # ORB reset once per session
        self.orb_range_established_today: bool = False  # today's ORB range ESTABLISHED
        self.hard_close_alerted: bool = False   # alerted once on a failed 15:45 flatten
        self.last_reconcile_slot: Optional[str] = None  # last intraday broker-reconcile slot done
        # v4.11: pages once per outage when the bot cannot see, and once when
        # sight returns. Instantiated here so the latch state survives ticks.
        self.blind_latch = BlindnessLatch()


_LEDGER = None
_LEDGER_DATE = None


# ── A2.1 — a deep frame for NAMED levels only ────────────────────────────────
# The mapper's section lookback is 10 days; the cached 5m frame is 100 bars.
# 1h bars carry hour granularity (all the section masks use). Read directly
# from the store with a local TTL - the shared cache stays capped for every
# other consumer (raising it would re-seed EMAs across the engines).
# DEPTH TRUTH (corrected r2): BACKFILL_DAYS requests 16 days of 1h ONCE, but
# candle_feed's pruner trims 1h to max(50,60)*PRUNE_FACTOR = 240 rows every
# 300s - so steady state is ~240h: ~10 days of 24h tape, ~34 RTH-only
# sessions. Asking for 264 is harmless headroom (fetch returns what exists);
# with the earliest partial day skipped by the truncation guard, the ladder
# effectively sees ~9 complete days + today on 24h symbols.
NAMED_FRAME_1H_BARS = 264      # >= prune ceiling (240); fetch caps at reality
_NLF_TTL_S = 300               # sections only change on an hour boundary
_NLF_CACHE = (0.0, None)


_NLF_SAID = {}


def _named_level_frame():
    """The deep 1h frame for the mapper's named levels, or None (fail soft).
    None simply means the mapper falls back to the live frame - where its
    truncation guard (A2.1) keeps partial sections out."""
    global _NLF_CACHE
    try:
        ts, df = _NLF_CACHE
        if df is not None and (time.time() - ts) < _NLF_TTL_S:
            return df
        from data.market_data import fetch_candles
        # ── FEED.2 (2026-08-15) — PREFER THE EXTENDED-HOURS STREAM ───────────
        # `<SYM>_EXT` is the same 1h interval subscribed WITHOUT `tho=true`, so
        # it carries the overnight bars that Asia and London sections are built
        # from. Plain "1h" is RTH-only and always will be — it is read by
        # structure_analyzer, the pitchfork and entry_snapshot, and must not
        # move under them.
        # ⚠️ FALLS BACK, DELIBERATELY. A box baked before FEED.2, or one with
        # OT_EXT_1H=0, has no _EXT rows. Falling back to RTH-only 1h means the
        # named levels are exactly what they are today — the sections simply
        # stay inert there, which is the CURRENT behaviour and not a regression.
        df = fetch_candles(f"{INSTRUMENT}_EXT", "1h", NAMED_FRAME_1H_BARS)
        if df is None or df.empty:
            df = fetch_candles(INSTRUMENT, "1h", NAMED_FRAME_1H_BARS)
            if df is not None and not df.empty and not _NLF_SAID.get("rth"):
                _NLF_SAID["rth"] = True
                logger.warning(
                    "[named-levels] no %s_EXT rows - using RTH-ONLY 1h. Asia and "
                    "London sections CANNOT build from this frame; the ladder is "
                    "NY-only on this box until the extended stream collects.",
                    INSTRUMENT)
        if df is not None and not df.empty:
            _NLF_CACHE = (time.time(), df)
            return df
        return None
    except Exception as exc:                                   # noqa: BLE001
        logger.debug("named-level frame unavailable: %s", exc)
        return None


def _feed_liquidity_ledger(liq_map, df_1m) -> None:
    """LIQ.4 WIRING — seed the ledger at RTH open, feed it CLOSED 1m bars.

    ⚠️ THE LEDGER HAS BEEN BUILT, TESTED AND COLLECTING NOTHING SINCE 08-13.
    Every session it stays unwired is level history that CANNOT be recovered
    later — the tape survives, but the running touch/hold/breach record does
    not, and rebuilding it after the fact means re-deriving levels that the
    mapper found live.

    It implements the operator's retreat rule verbatim: a WICK reaching the
    level is a touch, a CLOSE beyond is a breach, a CLOSE back on the origin
    side is a hold, and a bar that never reaches does nothing.

    ⚠️ CLOSED BARS ONLY, and exactly once each. `df_1m`'s last row is the
    FORMING bar on most ticks — feeding it would count a wick that has not
    finished printing and a close that is not a close, and would count the same
    bar dozens of times as it forms. `_LEDGER_LAST_BAR` is the guard.

    ⚠️ SEEDS COME FROM THE MAPPER, never re-derived here. LIQ.6 changed what a
    named pool IS (sections, closed-only, a 3-deep ladder), so the ledger takes
    whatever the mapper currently names — including the `(R1)`/`(R2)`/`(R3)`
    rung suffixes — rather than holding a second opinion about levels.
    """
    global _LEDGER, _LEDGER_DATE
    try:
        if df_1m is None or getattr(df_1m, "empty", True) or len(df_1m) < 2:
            return
        from analysis.liquidity_ledger import get_ledger
        today = str(df_1m.index[-1].date())
        if _LEDGER is None or _LEDGER_DATE != today:
            seeds = [(p.price, p.kind, p.name, True)
                     for p in (getattr(liq_map, "pools", None) or [])
                     if getattr(p, "is_named", False)]
            # A2.9 — an EMPTY first-tick seed must not latch the date: a mapper
            # warm-up hiccup used to lock a zero-level ledger for the whole
            # session. Retry every tick until the mapper produces named pools.
            if not seeds:
                logger.debug("[ledger] no named pools yet — seeding deferred")
                return
            # ONE singleton (A2.9): route through get_ledger so any future
            # consumer sees the same instance, not a second empty book.
            _LEDGER = get_ledger(INSTRUMENT)
            _LEDGER.reset_for_session(today, seeds=seeds)
            _LEDGER_DATE = today
            logger.info("[ledger] session %s seeded with %d named level(s)",
                        today, len(seeds))
        # A2.4 — bar selection lives in the ledger now: every closed session
        # bar newer than the persisted last_bar_ts, forming row excluded. The
        # old iloc[-2] + one-stamp guard dropped bars on any tick > ~75s.
        _LEDGER.feed_frame(df_1m)
        _LEDGER.write()
    except Exception as exc:                                   # noqa: BLE001
        logger.debug("[ledger] skipped: %s", exc)


def run_analysis(state: BotState) -> dict:
    """Fetch all market data and run analysis pipeline."""
    cache  = get_cache()
    data   = cache.get_all()
    price  = cache.get_price()
    if price is None:
        raise ValueError("Could not fetch current price")

    df_5m  = data.get("5m")
    df_1m  = data.get("1m")
    df_15m = data.get("15m")
    df_1h  = data.get("1h")

    if df_5m is None or df_5m.empty:
        raise ValueError("No 5m data available")

    df_1h_safe = df_1h if df_1h is not None else df_5m

    vol_state = get_volatility_engine().analyze(df_5m, df_1h_safe, price)
    trend     = get_trend_engine().analyze(data)
    structure = get_structure_analyzer().analyze(df_5m, df_15m, df_1h, price)
    liq_map   = get_liquidity_mapper().analyze(df_5m, df_15m, price,
                                               named_df=_named_level_frame())
    _feed_liquidity_ledger(liq_map, df_1m)      # LIQ.4 wiring

    # ── v6.18 — BIND ctx BEFORE ANYTHING WRITES INTO IT ─────────────────────
    # v6.16/v6.17 (Level.1, A2.6b) wrote ctx["gap"] / ctx["level_near"] into a
    # name that did not exist yet — run_analysis built its dict only at the
    # return. The NameError raised inside the try, and the except handler's
    # own ctx["gap"] = None re-raised it UNCAUGHT, so run_analysis failed on
    # EVERY tick: no ctx, no classification, no strategy could ever fire
    # (WORKING_AGREEMENT §21/§24 — same class as the is_trend_participation
    # NameError, reproduced behaviorally before this fix shipped). The dict is
    # bound HERE; the blocks below write into it; macro/orb are added before
    # the single return.
    ctx = {
        "price":     price,
        "data":      data,
        "vol":       vol_state,
        "trend":     trend,
        "structure": structure,
        "liq_map":   liq_map,
        "df_1m":     df_1m,
        "df_5m":     df_5m,
    }

    # ── Level.1 (2026-08-18) — WHAT IS PRICE TRADING INTO? ──────────────────
    # ⚠️ `level_strength` was written ONLY by `sweep_reversal`, which is
    # hard-gated (main.py:1325) with a 0.4% live win rate — so the column was
    # populated by a strategy that essentially does not trade, and 94% of the
    # book carried the default. The probe read that as "levels do not separate
    # outcomes." It never measured levels at all.
    # This puts the graded nearest level in ctx for EVERY strategy, every tick.
    # ⚠️ STRUCTURAL, NOT MAGNITUDE: "there is prior-day liquidity half a percent
    # above" is a statement about WHERE PRICE IS, which is the class the
    # operator reads charts with and the class nothing here has ever recorded.
    # ── A2.6b (2026-08-18) — MEASURE THE GAP, DO NOT INHERIT IT ─────────────
    # ⚠️ THE ONLY PRE-OPEN DECISION-TIME INPUT IN THE STACK. ADX, conviction,
    # the regime scores and IV skew all need bars from THIS session to exist;
    # the overnight gap is fully formed at 09:30 before a single RTH bar prints.
    # ⚠️ TODAY IT ENTERS ANONYMOUSLY. `atr_series` uses true range with
    # prev_close and the 5m tape is continuous, so a large gap SPIKES ATR at the
    # open and decays over the window — every consumer sees a volatility number
    # that is partly last night's news and cannot tell which part.
    # Operator, 2026-08-01: "the gaps you see overnight from previous close to
    # current open are big and meaningful, and they have to be reflected
    # somewhere."
    try:
        from analysis.gap_measure import measure_gap
        # ⚠️ LAST TICK'S REGIME, DELIBERATELY. `regime` is not bound yet at this
        # point — classification happens further down the tick — and a bare
        # `getattr(regime, ...)` would have raised into the except and set
        # prior_dir=0 forever, making `gap_class` permanently "UNDIRECTED".
        # A silent constant is exactly the failure this whole week has been
        # about, so the prior tick's committed direction is used instead: it is
        # yesterday's trend at the open, which is precisely what CONT/REV means.
        _prev = getattr(state, "current_regime", None)
        _dir = getattr(_prev, "trend_direction", "") if _prev else ""
        _pd = 1 if _dir == "BULLISH" else (-1 if _dir == "BEARISH" else 0)
        ctx["gap"] = measure_gap(df_5m, prior_dir=_pd)
    except Exception:                                          # noqa: BLE001
        ctx["gap"] = None

    try:
        from analysis.level_grade import nearest_graded
        _ng = nearest_graded(getattr(liq_map, "pools", None), price)
        ctx["level_near"] = _ng          # (name, grade, dist_pct) or None
    except Exception:                                          # noqa: BLE001
        ctx["level_near"] = None
    macro     = get_macro_manager().get()

    # ORB engine update (every tick during RTH). Pass last-tick regime so the
    # engine can gate its re-arm decision (this runs before reclassification).
    _regime_str = state.current_regime.primary_regime if state.current_regime else None
    orb = get_orb_engine().update(df_5m, df_1m, price, _regime_str)

    # Write ORB state to JSON file so status.py can read it directly
    # without parsing bot.log — eliminates all log-parsing timing issues.
    # Includes the disarm reason, break latches, live price and the 11:00
    # cutoff flag so status can render the true engine state (DISARMED / EXPIRED
    # / price-vs-range) rather than inferring it from the clock.
    try:
        import json as _json
        _eng = get_orb_engine()
        _now_et = now_et()
        _orb_state = {
            "high":       orb.orb_high if orb.orb_high > 0 else None,
            "low":        orb.orb_low  if orb.orb_low  > 0 else None,
            "width":      orb.orb_width,
            "state":      orb.state,
            "attempt":    orb.attempt_number,
            "reason":     orb.invalidation_reason,
            "broke_high": _eng.broke_high,
            "broke_low":  _eng.broke_low,
            "price":      price,
            "past_cutoff": (_now_et.hour, _now_et.minute) >= ORB_NO_ENTRY_AFTER_ET,
            "updated_at": _now_et.strftime("%Y-%m-%d %H:%M:%S ET"),
        }
        _state_path = os.path.join(os.path.dirname(LOG_FILE), "orb_state.json")
        with open(_state_path, "w") as _f:
            _json.dump(_orb_state, _f)
    except Exception:
        pass

    ctx["macro"] = macro
    ctx["orb"] = orb
    return ctx


def run_regime_classification(ctx: dict, trigger: str, state: BotState) -> RegimeState:
    """Classify current market regime and log transitions.

    L2.5: when OT_REGIME_ENGINE=L2 (default), the regime that gates trades is the
    Layer-2 conviction integrator's COMMITTED label — computed from the Layer-1
    confluence evidence vector — not the v1.3 boolean classifier's raw argmax.
    The v1.3 classifier still runs (its rich fields — adx, structure, bb_width —
    populate RegimeState and the logs), but its primary_regime is OVERRIDDEN by
    the integrator's stable label, which never emits UNKNOWN and holds through
    single-tick flicker. OT_REGIME_ENGINE=v13 restores the raw v1.3 label.
    """
    regime = get_regime_classifier().classify(
        vol_state  = ctx["vol"],
        trend_state= ctx["trend"],
        structure  = ctx["structure"],
        liq_map    = ctx["liq_map"],
        macro      = ctx["macro"],
        trigger    = trigger
    )
    state.last_regime_at = now_utc()

    # ── v6.24 — ICT GRADING PASS. UNCONDITIONAL, EVERY TICK. ────────────────
    # 🔴 v6.22 put the whole ICT branch inside attempt_new_entry, which has
    # FIVE early returns above it (daily-loss halt, session.can_enter, stale
    # regime book, chain-fetch failure, the UNKNOWN hard gate) and is itself
    # only called in an `else` — skipped entirely while a position is open or
    # condor legs are being managed. So on 2026-08-19 the suite journaled
    # NOTHING all morning: no [ict] lines, no dispatch errors, a healthy
    # journal, zero ict_setup rows. Grading was hostage to entry permission.
    # That is backwards. The journal of FORMING states is the only data the
    # priors are ever fitted from, and it must accrue on the ticks where we
    # could NOT have traded as much as the ones where we could — a setup that
    # formed while a position was open is exactly the observation that tells
    # us what the ranking costs.
    # So: OBSERVATION here, unconditional and chain-free. ACTION stays in
    # attempt_new_entry, where permission is decided. `ctx["ictx"]` carries the
    # built context forward so the entry path does not rebuild it.
    if _ICT_OK:
        try:
            ctx["ictx"] = build_ict_context(
                smc_state=ctx.get("smc"), structure=ctx["structure"],
                liq_map=ctx["liq_map"], df_1m=ctx.get("df_1m"),
                now_et=now_et(), price=ctx["price"])
            for _sc in ict_evaluate_all(ctx["ictx"]):
                ict_journal_state(
                    _sc, _sigj.journal if _sigj is not None else None)
        except Exception as _ige:                              # noqa: BLE001
            # LOUD: a silent failure here reads exactly like "no setup formed",
            # which is a legitimate outcome. The two must never look alike.
            logger.error("[ict] grading pass failed (%s) — no setup states "
                         "journaled this tick", _ige)

    # ── v6.21 — LAYER-1 IS ENGINE-INDEPENDENT. RUN IT BEFORE THE BRANCH. ─────
    # 🔴 The v6.19 wiring left the L1 scorer call inside the `_REGIME_ENGINE ==
    # "l2"` branch, where it had always lived. Two things silently broke the
    # moment the fork's default became "smc", and NEITHER is about the label:
    #   1. `ctx["l1"]` was never set, so the SweepReversal dispatch — which
    #      gates on `ctx["l1"].scores["SWEEP_REVERSAL"] >= SWEEP_SETUP_FLOOR`
    #      since SWP.1 deliberately stopped requiring the LABEL — read 0.0 on
    #      every tick. SweepReversal could not fire at all: OFF BY
    #      CONSTRUCTION, not by decision.
    #   2. `regime.flat_angle_deg` fell back to its default for the five
    #      strategies and entry_engine that read it — re-opening the exact bug
    #      STR.2 had just closed, in a different way.
    # Also `_l1_scores(ctx)` returned None, so the regime-axes decomposition
    # was absent from every journal row this box wrote.
    # THE SCORER IS NOT THE COMMITTED LABEL. It produces per-regime SETUP
    # SCORES and structural telemetry that the dispatch and the journal
    # consume regardless of which engine commits the label — so it belongs
    # ABOVE the branch. L2 behaviour is unchanged: it consumes the same
    # `_l1_res` from the same inputs, computed after the v1.3 classification
    # exactly as before.
    _l1_res = None
    if _l1_scorer is not None:
        try:
            closes = None
            df1m = ctx.get("df_1m")
            if df1m is not None and len(df1m) >= RANGE_WINDOW_BARS:
                closes = df1m["close"].tolist()[-RANGE_WINDOW_BARS:]
            atr = getattr(ctx["vol"], "atr_current", None)
            _l1_res = _l1_scorer.score(ctx["vol"], ctx["trend"],
                                       ctx["structure"], ctx["liq_map"],
                                       closes=closes, atr=atr)
            ctx["l1"] = _l1_res

            # ── STR.2 (2026-08-18) — CARRY THE ANGLE TO THE CONSUMER ─────────
            # ⚠️ FIVE STRATEGIES READ `regime.flat_angle_deg` and all five were
            # taking the default, because RegimeState had no such attribute.
            # `regime_confluence.flat_angle_deg()` computes it on every
            # RANGING/COMPRESSION evaluation and drops it into the breakdown as
            # {"angle": ...} — computed, recorded in the evidence, never
            # delivered. Same shape as `direction_conf`.
            # ⚠️ THE ANGLE IS A STRUCTURAL READ, not a magnitude one: the slope
            # of the recent window in ATR units — the closest thing collected
            # to "is price going anywhere or just rotating", which is the class
            # the operator reads charts with and the class the separation probe
            # has never been able to test.
            try:
                _bd_all = _l1_res.breakdown or {}
                for _k in ("RANGING", "COMPRESSION"):
                    _a = (_bd_all.get(_k) or {}).get("angle")
                    if _a is not None:
                        regime.flat_angle_deg = float(_a)
                        break
            except Exception:                                  # noqa: BLE001
                pass          # telemetry must never break the regime path
        except Exception as _l1e:                              # noqa: BLE001
            # A scorer failure must not kill classification under ANY engine.
            # L2 handles a None _l1_res below by raising into its own except,
            # which is the same path it took when the score() call failed here
            # before the hoist — identical behaviour, one level up.
            _l1_res = None
            logger.error("L1 scorer failed (%s) — no setup scores this tick "
                         "(SweepReversal cannot fire, axes omitted)", _l1e)

    # ── v6.19 — SMC OVERRIDE (fork): the structural core drives the gate ──────
    # Parallel to the L2.5 branch below and mutually exclusive with it. The
    # v1.3 classifier above still runs and populates RegimeState's rich fields
    # (adx, structure, bb_width) exactly as it does under l2 — the SMC core
    # overrides ONLY primary_regime/conviction, the same boundary L2.5
    # overrode. ctx["smc"] carries the full structural context (dealing range,
    # position/zone, draw, raid, displacement, setup lifecycle) for every
    # downstream consumer and the journal. Setup-phase TRANSITIONS journal
    # once per change (the one-time-per-key idiom).
    global _smc_last_setup_phase
    _smc_label = None
    if _REGIME_ENGINE == "smc" and _SMC_OK and _smc_engine is not None:
        try:
            smc_st = _smc_engine.update(
                price=ctx["price"], df_1m=ctx.get("df_1m"),
                df_5m=ctx.get("df_5m"), structure=ctx["structure"],
                liq_map=ctx["liq_map"], vol_state=ctx["vol"],
                now_et=now_et())
            ctx["smc"] = smc_st
            regime.primary_regime = smc_st.label
            regime.conviction     = smc_st.confidence
            _smc_label = smc_st.label
            try:
                _smc_engine.save()
            except Exception:                              # noqa: BLE001
                pass
            _ph = (smc_st.setup.phase, smc_st.setup.thesis,
                   smc_st.setup.basis)
            if _ph != _smc_last_setup_phase:
                logger.info("[SMC] setup %s %s (%s) label=%s conf=%.2f "
                            "zone=%s pos=%.2f",
                            smc_st.setup.phase, smc_st.setup.thesis,
                            smc_st.setup.detail, smc_st.label,
                            smc_st.confidence, smc_st.zone,
                            smc_st.position_pct)
                if _sigj is not None:
                    try:
                        _sigj.journal("smc_setup",
                                      state=smc_st.journal_dict())
                    except Exception:                      # noqa: BLE001
                        pass
                _smc_last_setup_phase = _ph
        except Exception as _se:                           # noqa: BLE001
            # ERROR, not silent: a failed SMC tick leaves the v1.3 label in
            # place for THIS tick (the honest fallback — no smc hold book
            # exists yet), and the session's labels are mixed-engine.
            logger.error("SMC engine tick failed (%s) — v1.3 label stands "
                         "for this tick", _se)
        # falls THROUGH to the shared transition/alert/log_regime tail; the
        # L2 branch below is skipped by its own _REGIME_ENGINE == "l2" test.

    # ── L2.5 override: committed integrator label drives the gate ──────────────
    l2_label = None
    l2_conv  = None
    _l1_fallback = False          # RGM.6 — did we resolve via the L1 argmax?
    # v6.21 — `_l1_res` is now bound ABOVE the branch (engine-independent) and
    # must NOT be re-initialised to None here; the fallback rung still reads it.
    if _REGIME_ENGINE == "l2" and _L2_OK:      # v4.7 — value is .lower()ed
        try:
            # v5.6 (SWP.1) — the FULL result, not just the vector: it gives
            # dispatch the per-regime SETUP SCORES, so the sweep gate does not
            # need that label to win the L2 argmax. v6.21 — computed above.
            if _l1_res is None:
                raise RuntimeError("L1 scorer unavailable — see the error "
                                   "logged above; L2 cannot commit without it")
            evidence = _l1_res.evidence()

            st = _l2_integ.update(now_utc().timestamp(), evidence)
            # persist the book so a mid-session restart doesn't reset conviction
            try:
                _l2_integ.save(_L2_STATE_PATH)
            except Exception:
                pass
            # a warmed, committed label overrides v1.3; an unwarmed/cold book
            # (stale, or empty label before first real evidence) leaves v1.3 in
            # place so the open isn't driven by a zero-conviction argmax.
            if st.regime and not st.stale:
                l2_label, l2_conv = st.regime, st.conviction
                regime.primary_regime = st.regime
                regime.conviction     = st.conviction
                # v5.0 — remember it, so a stale tick can HOLD rather than fall
                # back to the un-smoothed classifier.
                _l2_held["regime"] = st.regime
                _l2_held["conviction"] = st.conviction
                _l2_held["since"] = None
                if _l2_mute.get("why"):          # v4.6 — announce recovery once
                    logger.info("L2.5 COMMITTING again (%s c=%.2f) — was: %s",
                                st.regime, st.conviction, _l2_mute["why"])
                    _l2_mute.clear()
                # v5.5 — LIVE A/B (RGM.1 F7). conviction_integrator v2.1 runs
                # BOTH emission laws off the same conviction vector and reports
                # what the other one would have emitted. Log only on a CHANGE of
                # the divergence pair, never per tick — a per-tick line is spam,
                # not observability (WORKING_AGREEMENT §17). Observational: the
                # shadow gates nothing and is never read to trade.
                mem_trace.tick(logger)   # MEM.2 — no-op unless OT_MEM_TRACE
                _ab = (st.regime, st.shadow_regime)
                if st.shadow_regime and _ab != _l2_ab.get("pair"):
                    _l2_ab["pair"] = _ab
                    if st.regime != st.shadow_regime:
                        logger.info("L2 A/B DIVERGE live=%s shadow=%s "
                                    "(switches live=%d shadow=%d, armed=%s)",
                                    st.regime, st.shadow_regime,
                                    st.switches, st.shadow_switches, st.armed)
                    else:
                        logger.info("L2 A/B agree=%s (switches live=%d "
                                    "shadow=%d)", st.regime, st.switches,
                                    st.shadow_switches)
            # ── RGM.6 (2026-08-11) — RESOLVE TO A KNOWN LABEL ────────────────
            # Operator: "unknown should be virtually eliminated by the time we
            # freeze layer 1… there should be ways to extrapolate and resolve to
            # a KNOWN label." The data says the answer is almost always already
            # in hand: **L1 produces an all-zero tick only 2.4-3.0% of the time**
            # (regime diary, every session since 07-15), while the v13 fallback
            # emits UNKNOWN on ~18-19%. So we were discarding an available answer
            # roughly seven times more often than we were genuinely blind.
            # v5.0's hold covered STALE ticks only. The other fall-through —
            # "empty committed label on a WARM book" — went to the v13
            # classifier, which re-derives from scratch with NO MEMORY and
            # returns UNKNOWN whenever nothing matches its ladder.
            # THE LADDER NOW IS: committed L2 -> held incumbent -> L1 ARGMAX
            # (a low-conviction KNOWN label) -> v13. UNKNOWN is reserved for the
            # ~2.4% that are genuinely all-zero.
            # ⚠️ CONVICTION IS CARRIED HONESTLY, NOT INVENTED. A held label
            # keeps its own conviction; an L1-argmax label carries L1's raw
            # score, which is BELOW theta_commit by construction — that is the
            # point. Downstream gates that read conviction (continuation's
            # floor, condor's plan) therefore see a weak label as weak.
            # ⚠️ THE TAG CHANGES so this is legible in the logs and countable
            # later: [L2 c=] committed, [L2-hold c=] incumbent, [L1 c=] argmax,
            # [v13] the true fallback. Anyone counting [v13] to measure the
            # fallback rate must know these are now four states, not two.
            elif st.stale and _l2_held["regime"]:
                # v5.0 — HOLD THE LAST COMMITTED LABEL. This branch is the whole
                # fix. Falling through to v1.3 here swapped the SMOOTHER out for
                # the RAW classifier at exactly the moment the smoother was
                # unavailable — 436 committed switches vs 695 L1-argmax flips, so
                # v1.3 is the churn L2 exists to remove. exit_engine checks
                # regime-flip SECOND, before any price stop, so one wobbled tick
                # closed the position: measured median hold on regime_flip exits
                # was 0.8 min, p25 12 SECONDS, against 5-12 min for every other
                # exit reason.
                # And the trigger is routine — v4.6's own note: "a tick gap over
                # dt_max=90s re-stales every tick."
                # HOLDING IS NOT DECIDING ON UNKNOWN INFORMATION, it is declining
                # to act on it. The position stays protected the entire time by
                # everything that reads PRICE — 15:45 hard close, break-of-
                # structure, trail, stop, max loss — none of which touch the
                # label. No expiry: a label held for 30 stale minutes costs
                # nothing, because regime-flip was never what kept the position
                # safe, it was what closed it early.
                if _l2_held["since"] is None:
                    _l2_held["since"] = now_utc()
                    logger.info("L2.5 STALE — HOLDING %s c=%.2f (was falling back "
                                "to v1.3 raw argmax, the churn source)",
                                _l2_held["regime"], _l2_held["conviction"])
                l2_label = _l2_held["regime"]
                l2_conv  = _l2_held["conviction"]
                regime.primary_regime = l2_label
                regime.conviction     = l2_conv
            elif _l1_res is not None and RGM6_L1_ARGMAX_FALLBACK:
                # RGM.6 — no committed label and nothing held: take L1's own
                # argmax rather than re-deriving from scratch in v13. This is
                # the "extrapolate to a KNOWN label" rung.
                try:
                    _sc = {k: v for k, v in (_l1_res.scores or {}).items()
                           if isinstance(v, (int, float)) and v > 0.0}
                except Exception:                      # noqa: BLE001
                    _sc = {}
                if _sc:
                    _top = max(_sc, key=lambda k: _sc[k])
                    l2_label = _top
                    l2_conv  = float(_sc[_top])
                    regime.primary_regime = _top
                    regime.conviction     = l2_conv
                    _l1_fallback = True
                    if _l2_mute.get("why") != "l1-argmax":
                        _l2_mute["why"] = "l1-argmax"
                        logger.info(
                            "L2 not committing — resolving to the L1 ARGMAX "
                            "%s c=%.2f rather than UNKNOWN. L1 is all-zero on "
                            "only ~2.4%% of ticks, so a known answer is almost "
                            "always available.", _top, l2_conv)
                else:
                    _l1_fallback = False
                    logger.info("L2 not committing and L1 is ALL-ZERO — this is "
                                "the genuinely blind case (~2.4%% of ticks); "
                                "falling back to v13.")

            else:
                # v4.6 — THE SILENT GATE, NOW AUDIBLE. Import can be fine and the
                # integrator can run without raising, yet L2 still not commit,
                # because `stale` only clears on a FULL evidence vector:
                #     if all(evidence.get(r) is not None ...): self.stale = False
                # One perpetually-None dimension therefore pins the book stale
                # forever and every REGIME line prints [v13] with NOTHING logged.
                # That is precisely why the 2026-07-29 question "did L2.5 land?"
                # could not be answered from the logs. Report the REASON, and the
                # exact dimensions that are missing, throttled so a long stale
                # stretch is one line per change rather than one per tick.
                _missing = [r for r in INTEGRATED_REGIMES if evidence.get(r) is None]
                if st.stale:
                    _why = ("stale: evidence dims None=" + ",".join(_missing)) if _missing \
                           else "stale: awaiting a full evidence vector (or post-gap warm-up)"
                else:
                    _why = "empty committed label on a warm book"

                # v4.8 — DECLARE THE OPENING GAP AS INTENTIONAL, NOT AS AN ERROR.
                # RANGING and COMPRESSION are computed on a 25-bar 1-MINUTE window,
                # and market_data deliberately scopes the 1m frame to the CURRENT
                # SESSION (OT_FEED_INTRADAY_SCOPE=session) so that window can never
                # bleed across the overnight gap and fabricate a slope. Therefore
                # those two dims are legitimately unavailable for the first ~25
                # minutes of every session — arithmetic, as market_data's own
                # docstring says, not a fault. v4.6 announced it at WARNING with
                # "NOT L2.5-grade", which is alarm language for designed behaviour
                # and fired 13 times fleet-wide at 09:30 on 2026-07-30. A warning
                # that cries wolf every morning is how real ones get ignored.
                # The distinction: EXPECTED = only window-dependent dims missing,
                # and the 1m frame is still filling. Anything else stays a WARNING.
                _WINDOW_DIMS = {RANGING, COMPRESSION}
                _bars = 0 if df1m is None else len(df1m)
                _warming = (bool(_missing)
                            and set(_missing) <= _WINDOW_DIMS
                            and _bars < RANGE_WINDOW_BARS)
                if _l2_mute.get("why") != _why:
                    if _warming:
                        logger.info(
                            "L2.5 warming as designed — %s need a %d-bar 1m window "
                            "and the frame holds %d (session-scoped by design, never "
                            "padded across the overnight gap). v1.3 label in use "
                            "until the window fills.",
                            "+".join(sorted(_missing)), RANGE_WINDOW_BARS, _bars)
                    else:
                        logger.warning(
                            "L2.5 NOT committing — %s; falling back to the v1.3 "
                            "label. df_1m=%s. This is NOT the designed opening "
                            "warm-up: conviction data logged while it persists is "
                            "not L2.5-grade.", _why,
                            "None" if df1m is None else _bars)
                    _l2_mute["why"] = _why
        except Exception as e:
            logger.warning("L2.5 integrator step failed (%s) — using v1.3 label", e)

    if regime.primary_regime != state.last_regime_name:
        # RGM.6 — four states, not two. Anyone counting [v13] to measure the
        # fallback rate must know that.
        if _smc_label:
            engine_tag = f" [SMC c={regime.conviction:.2f}]"
        elif l2_label and _l1_fallback:
            engine_tag = f" [L1 c={l2_conv:.2f}]"
        elif l2_label and _l2_held.get("since") is not None:
            engine_tag = f" [L2-hold c={l2_conv:.2f}]"
        elif l2_label:
            engine_tag = f" [L2 c={l2_conv:.2f}]"
        else:
            engine_tag = " [v13]"
        logger.info(
            f"REGIME: {state.last_regime_name} → {regime.primary_regime} "
            f"(conviction={regime.conviction:.2f} trigger={trigger}){engine_tag}"
        )
        get_alert_manager().send_regime_alert(
            old_regime = state.last_regime_name,
            new_regime = regime.primary_regime,
            conviction = regime.conviction,
            notes      = regime.notes
        )
        get_trade_logger().log_regime(
            regime        = regime.primary_regime,
            conviction    = regime.conviction,
            macro_context = ctx["macro"].macro_context if ctx["macro"] else "NEUTRAL",
            adx           = regime.adx,
            trigger       = trigger,
            # v4.8 — PROVENANCE IN THE ROW, not just in a bot.log tag. Which
            # engine produced this label was previously recoverable only by
            # grepping [L2 c=..]/[v13] out of the log, which is how "has L2.5
            # ever committed?" became a 29-box, 138k-line archaeology exercise
            # on 2026-07-30. It also makes the designed v1.3 opening window
            # excludable from L2-conditioned fits by a WHERE clause.
            engine        = ("SMC" if _smc_label
                             else "L2" if l2_label else "v13")
        )

    state.last_regime_name = regime.primary_regime
    state.current_regime   = regime
    return regime


# ── Entry snapshot (v5.1) — log-only capture, one place, both entry paths ─────
_snapshot_warned: set = set()
_contract_warned: set = set()   # reason -> logged once per process (§17 idiom)


def _capture_entry_contract(ctx: dict, record: dict) -> bool:
    """v5.5 (N.9) — persist the CONTRACT's own state at entry.

    Every value here was ALREADY IN MEMORY: `OptionContract` carries
    bid/ask/mark/delta/gamma/theta/vega/iv and `OptionsChain` carries
    spot_price/iv_rank. They were read for strike selection and discarded.
    Nothing new is fetched, subscribed or computed.

    WHY: every other instrument in this repo reports WHAT the premium did.
    None reports WHY. A -27% floor stop is currently indistinguishable between
    "the underlying went against us", "the underlying went nowhere and theta
    ate it", and "we were right and IV collapsed" — three causes, three
    different fixes, one number. On 0DTE that distinction is the whole game.

    Matched on the OCC symbol the row was actually filled on, not on strike:
    two legs of a condor share an underlying and a session, and picking the
    wrong side would attribute one leg's greeks to the other.

    Log-only. A failure warns once per reason per process and never gates.
    """
    trade_id = (record or {}).get("trade_id", "")
    occ = (record or {}).get("option_symbol", "")
    reason = ""
    try:
        chain = (ctx or {}).get("chain")
        con = None
        if chain is not None and occ:
            for c in list(getattr(chain, "calls", []) or []) + \
                     list(getattr(chain, "puts", []) or []):
                if getattr(c, "symbol", "") == occ:
                    con = c
                    break
        if con is None:
            reason = "contract-not-found"
        else:
            payload = {
                "entry_delta": getattr(con, "delta", None),
                "entry_gamma": getattr(con, "gamma", None),
                "entry_theta": getattr(con, "theta", None),
                "entry_iv":    getattr(con, "iv", None),
                "entry_bid":   getattr(con, "bid", None),
                "entry_ask":   getattr(con, "ask", None),
                "chain_iv_rank": getattr(chain, "iv_rank", None),
            }
            if get_trade_logger().set_entry_contract(trade_id, payload):
                return True
            reason = "write-returned-false"
    except Exception as exc:                                 # noqa: BLE001
        # Logged INLINE so the W.2 swallow census can see this handler is not
        # silent — it reads the except body, not the code after it.
        logger.debug("entry_contract capture raised (%s: %s)",
                     type(exc).__name__, exc)
        reason = f"raised:{type(exc).__name__}"

    if reason not in _contract_warned:
        _contract_warned.add(reason)
        logger.warning(
            "entry_contract NOT captured (%s) for %s — this trade cannot enter "
            "the premium-decomposition read (direction vs theta vs IV); logged "
            "once per reason per process.", reason, trade_id[:8])
    return False


def _capture_entry_snapshot(ctx: dict, record: dict, direction: str) -> bool:
    """Persist the entry-time FVG/structure picture onto the trade row.

    Called only after a fill is confirmed and the row exists. Returns True on a
    write. A failure is logged ONCE per reason per process and then never again:
    a per-fill warning would be spam, and no warning at all is how three dead
    timeframes went unnoticed for two weeks.
    """
    trade_id = (record or {}).get("trade_id", "")
    try:
        payload = _entry_snapshot_json(ctx, direction)
        wrote = get_trade_logger().set_entry_snapshot(trade_id, payload)
        if not wrote:
            reason = "write-returned-false"
        elif '"err"' in payload:
            reason = "payload-error"
        else:
            return True
    except Exception as exc:                                 # noqa: BLE001
        # Logged HERE as well as in the warning below so the W.2 census can see
        # this handler is not silent — it reads the except body, not the code
        # that follows it.
        logger.debug("entry_snapshot capture raised (%s: %s)",
                     type(exc).__name__, exc)
        reason = f"raised:{type(exc).__name__}"
        payload = ""

    if reason not in _snapshot_warned:
        _snapshot_warned.add(reason)
        logger.warning(
            "entry_snapshot NOT captured (%s) for %s — this trade cannot enter "
            "the TC.2 exit counterfactual; logged once per reason per process. "
            "%s", reason, trade_id[:8], payload[:300])
    return False


def _execute_condor_leg(signal: "OptionsSignal", state: BotState,
                        ctx: dict = None):
    """
    Execute a single condor leg (one vertical credit spread) from the
    OptionsSignal produced by IronCondorStrategy.check_leg_triggers().

    Legging model (per strategy design): Leg 1 fires on the side price is
    moving toward first; Leg 2 is queued and only fires after Leg 1 fills and
    only while the regime is still RANGING. If the regime flips before Leg 2,
    the strategy cancels Leg 2 and the filled Leg 1 vertical is managed
    standalone through normal stop/nickel exits. This function just executes
    whichever leg the strategy has decided is ready this tick.

    Paper mode: fills at mid credit. Live mode: places the 2-leg vertical as a
    single CREDIT limit order via TastyTrade (same SDK pattern as entry_engine).
    """
    from config import (CONTRACT_MULTIPLIER, CONDOR_NICKEL_CLOSE,
                        CONDOR_STOP_LOSS_PCT, INSTRUMENT)
    from database.trade_logger import make_record, get_trade_logger
    import uuid

    mode = "PAPER" if state.paper_trading else "LIVE"

    # Short/long contracts for this leg live on the call- or put-side fields.
    if signal.option_side == "call":
        short_contract = signal.short_call_contract
        long_contract  = signal.long_call_contract
    else:
        short_contract = signal.short_put_contract
        long_contract  = signal.long_put_contract

    if short_contract is None or long_contract is None:
        logger.error("Condor leg: missing contracts — cannot execute")
        return

    net_credit   = signal.net_credit
    spread_width = abs(short_contract.strike - long_contract.strike)

    # Size this vertical at HALF the grade budget — each side is independent,
    # so a B-grade $1000 trade becomes two ~$500 verticals.
    sizing = get_risk_manager().compute_condor_leg_size(spread_width, net_credit, "B")
    if not sizing.allowed:
        logger.info(f"Condor leg not sized: {sizing.reject_reason}")
        return
    contracts = sizing.contracts

    if not state.paper_trading:
        # ── LIVE 2-leg vertical credit entry — FILL-CONFIRMED (v3.7, defect O) ─
        # Submission is not a fill. The record is written ONLY for contracts
        # the broker confirms filled, at the broker's per-leg net credit —
        # never the limit price we asked for. Unfilled by the deadline →
        # cancel and walk away (the strategy re-evaluates next tick).
        # A PARTIAL fill is a real position: book the filled quantity.
        # SDK NOTE (verified v13.x): NewOrder.price is SIGNED — positive =
        # CREDIT received, which is what a short vertical collects. The old
        # price_effect kwarg is ignored by current SDKs and is gone.
        try:
            from data.tasty_client import get_session, get_account
            from execution.order_confirm import confirm_order_fill
            from tastytrade.order import (
                NewOrder, Leg, OrderAction, OrderType, OrderTimeInForce,
                InstrumentType,
            )
            from decimal import Decimal

            session = get_session()
            account = get_account()
            legs = [
                Leg(instrument_type=InstrumentType.EQUITY_OPTION,
                    symbol=short_contract.symbol,
                    action=OrderAction.SELL_TO_OPEN, quantity=contracts),
                Leg(instrument_type=InstrumentType.EQUITY_OPTION,
                    symbol=long_contract.symbol,
                    action=OrderAction.BUY_TO_OPEN, quantity=contracts),
            ]
            order = NewOrder(
                time_in_force = OrderTimeInForce.DAY,
                order_type    = OrderType.LIMIT,
                price         = Decimal(str(round(net_credit, 2))),  # + = credit
                legs          = legs,
            )
            response = account.place_order(session, order, dry_run=False)
            if response.errors:
                logger.error(f"Condor leg order failed: {response.errors}")
                return
            basis = [(short_contract.symbol, 1, +1),
                     (long_contract.symbol,  1, -1)]   # net = short − long (credit)
            fill = confirm_order_fill(session, account, response.order, basis,
                                      what="condor-leg entry")
            if not fill.filled or fill.quantity <= 0 or fill.net_price is None:
                logger.warning(f"Condor leg entry NOT filled ({fill.detail}) — "
                               f"no position recorded")
                if fill.working_order_id:
                    get_alert_manager()._send(
                        f"\U0001F6A8 {INSTRUMENT} Condor entry order "
                        f"{fill.working_order_id} could not be cancelled and may "
                        f"still fill — reconcile will adopt it. ({fill.detail})")
                return
            if fill.quantity < contracts:
                logger.warning(f"Condor leg entry PARTIAL: {fill.quantity}/"
                               f"{contracts} filled — booking the filled size")
            contracts   = fill.quantity          # book what ACTUALLY filled
            fill_credit = fill.net_price         # broker net, not our limit
            order_id    = fill.order_id or ""
        except Exception as e:
            logger.error(f"Condor leg order failed: {e}")
            return
    else:
        # ── PAPER books what the live mid-credit limit posts (v4.1). Routed
        # through limit_ladder.paper_fill_credit — the SINGLE paper-pricing
        # authority — so condor legs, rolled verticals, singles and butterflies
        # all degrade together under one knob (PAPER_FILL_SLIPPAGE_PCT,
        # default 0.0 = the mark). Before v4.1 this haircut was applied here
        # inline while entry_engine v3.8 had stopped applying it — paper
        # friction differed by strategy, which made cross-strategy paper P&L
        # non-comparable.
        from execution.limit_ladder import paper_fill_credit
        fill_credit = paper_fill_credit(net_credit)
        order_id    = "PAPER"

    is_leg1  = "Leg 1" in signal.setup_type
    max_loss = (spread_width - fill_credit) * contracts * CONTRACT_MULTIPLIER

    # ── DELTA STREET-SIGN (v3.x, 2026-07-15) ──────────────────────────────────
    # The BB-anchored selector already chose short_contract; we do NOT influence
    # that. We only READ the delta off the strike it picked and record it as the
    # setup_score, purely as a calibration waypoint. abs() puts put-side (negative
    # delta) and call-side (positive) on one 0-1 scale. If the Greeks feed didn't
    # populate delta (contract default 0.0), store NULL — a real short strike is
    # never exactly 0.0 delta, so NULL unambiguously means "delta unavailable",
    # not "delta was zero". Calibration can then trust every non-null value.
    short_delta = abs(getattr(short_contract, "delta", 0.0) or 0.0)
    delta_score = short_delta if short_delta > 0 else None

    # Register the leg as a TRACKED position so it is managed, exited, and P&L'd.
    # The condor is the ONLY strategy allowed a second concurrent position.
    # One function serves two trades; the identity must come from the SIGNAL,
    # never from the function it happens to route through.
    _is_tcs = bool(getattr(signal, "is_trend_credit", False))
    record = make_record(
        trade_id         = str(uuid.uuid4()),
        symbol           = INSTRUMENT,
        strategy         = ("TrendCreditSpread" if _is_tcs
                            else "IronCondorStrategy"),
        setup_type       = signal.setup_type,
        setup_grade      = "B",
        setup_score      = delta_score,          # street-sign: |short-strike delta|
        direction        = "neutral",
        option_side      = signal.option_side,
        is_butterfly     = 0,
        strike           = short_contract.strike,
        short_strike     = short_contract.strike,
        long_strike      = long_contract.strike,
        spread_width     = spread_width,
        credit_received  = fill_credit,
        expiry           = getattr(short_contract, "expiry", ""),
        contracts        = contracts,
        entry_premium    = fill_credit,                # credit basis for exits
        total_cost       = max_loss,
        max_loss         = max_loss,
        # NO PREMIUM STOP ON A TREND CREDIT SPREAD. Its measured EV was HELD
        # TO EXPIRY, UNMANAGED, and its only exits are a breach of the bound or
        # the 15:45 close. Writing a stop here is what made a $0.06 credit
        # closeable on one cent of widening.
        stop_premium     = (0.0 if _is_tcs
                            else fill_credit * (1 + CONDOR_STOP_LOSS_PCT)),
        target_premium   = CONDOR_NICKEL_CLOSE,
        underlying_entry = getattr(signal, "underlying_entry", 0.0),
        # ⚠️ TC.6 CARRIES ITS OWN IDENTITY THROUGH THIS PATH (2026-08-14).
        # This function builds the record for BOTH a condor leg and a trend
        # credit spread, and it was hardcoding condor identity onto both. The
        # consequences were total, not cosmetic:
        #   · `is_trend_credit` never reached the record, so
        #     `_evaluate_condor_leg`'s TC.6 branch — gated on
        #     `record.get("is_trend_credit")` — COULD NEVER FIRE. Every TC.6 leg
        #     fell into the condor ladder and picked up the ratchet and the 25%
        #     premium stop. That is the `stop=$0.69` on a $0.55 credit seen in
        #     Telegram at 10:02 on 2026-08-14.
        #   · `underlying_stop` was never set, so even had the branch fired the
        #     breach rule would have had NO BOUND to test and would have skipped
        #     itself silently.
        #   · `strategy` and `regime` were hardcoded, so TC.6 trades were logged
        #     as IronCondorStrategy in RANGING and their P&L was attributed to
        #     the condor.
        # The strategy and the exit engine were both correct in isolation; the
        # HANDOFF between them dropped every flag they agreed on.
        regime           = ("RANGING" if not _is_tcs
                            else getattr(signal, "regime", "") or "TRENDING"),
        underlying_stop  = getattr(signal, "underlying_stop", 0.0),
        # ── TCS.4 (2026-08-17) — REMOVED: `is_trend_credit` IS NOT A COLUMN ──
        # ⚠️ THIS CRASH-LOOPED NFLX LIVE. `log_entry` INSERTs every key in the
        # record, so a key with no column raises OperationalError on the INSERT,
        # the loop error counter hits its cap, and the service shuts down and
        # restarts — every 15s, for the whole session.
        # It never fired before today because TC.6 could never REACH execution:
        # TCS.3 fixed the bound at noon and **the first trade that formed
        # correctly died at the write.** A latent defect exposed by a fix, which
        # is the shape audit #1 was convened over.
        # `structure.py` has said this since 08-14 — *"`is_trend_credit` IS NOT
        # A COLUMN"* — and already derives the answer from the PERSISTED
        # `strategy`/`setup_type`. Verified with the flag absent:
        # is_trend_participation -> True, is_credit_vertical -> True. The field
        # was write-only and the exit path never needed it.
        vix_at_entry     = getattr(signal, "vix_at_signal", 0.0),
        adx_at_entry      = getattr(signal, "adx_at_signal", 0.0)
                            or (state.current_regime.adx if state.current_regime else 0.0),
        regime_conviction = getattr(signal, "conviction", 0.0)
                            or (state.current_regime.conviction if state.current_regime else 0.0),
        flat_angle_deg    = getattr(signal, "flat_angle_deg", 0.0),
        # ── Level.1 (2026-08-18) — PERSIST THE GRADE OR IT IS TELEMETRY ─────
        # ⚠️ THE WHOLE POINT OF THIS WEEK: a quantity computed and not written
        # to the row cannot be tested against outcomes. `direction_conf`
        # separated on the live book and was journaled nowhere;
        # `flat_angle_deg` was computed every tick and never reached the regime
        # object; the pusher's SHORT lines were captured and truncated. This is
        # the same class, caught before shipping rather than after.
        # Falls back to the strategy's own value (sweep sets one directly), so
        # a strategy with a better local read is not overwritten by a generic
        # proximity grade.
        level_strength    = (float(getattr(signal, "level_strength", 0.0) or 0.0)
                             or ((ctx.get("level_near") or (None, 0.0, 0))[1]
                                 if isinstance(ctx, dict) else 0.0)),
        # A2.6b: persist the gap or it is telemetry. Backfillable, so historical
        # rows can be filled retroactively — unlike everything else this week.
        gap_pct           = ((ctx.get("gap") or {}).get("gap_pct")
                             if isinstance(ctx, dict) else None),
        swept_level_name  = (getattr(signal, "swept_level_name", "") or
                             ((ctx.get("level_near") or ("", 0, 0))[0]
                              if isinstance(ctx, dict) else "")),
        # v6.9 (AUDIT F6): a TC.6 record must not claim condor-leg identity —
        # is_condor_leg is what _condor_sibling_open and condor_roll key on,
        # and condor_leg_num=2 on every TC.6 row was data pollution.
        is_condor_leg    = 0 if _is_tcs else 1,
        condor_leg_num   = 0 if _is_tcs else (1 if is_leg1 else 2),
        is_broken_wing   = 0,
        short_symbol     = getattr(short_contract, "symbol", ""),
        long_symbol      = getattr(long_contract, "symbol", ""),
        option_symbol    = getattr(short_contract, "symbol", ""),
        order_id         = order_id,
        paper_trade      = 1 if state.paper_trading else 0,
        status           = "open",
    )
    get_trade_logger().log_entry(record)
    # v5.1 — a condor leg is "neutral": no in-favor side, so no trail anchor.
    # The zone inventory is still captured — it bounds where the underlying had
    # room to run toward either short strike. ctx is optional so a caller that
    # cannot supply one degrades to no capture rather than to a raise.
    if ctx is not None:
        _capture_entry_snapshot(ctx, record, "neutral")
        _capture_entry_contract(ctx, record)          # v5.5 (N.9)
    get_position_manager(state.paper_trading).add_condor_leg(record)

    # Advance the plan (DECIDED -> LEG1_FILLED -> COMPLETE).
    # v6.9 (AUDIT F6): only a CONDOR fill advances the condor plan. A TC.6 fill
    # reaching this call was a no-op only because TC.6 defers while a plan is
    # active — a gate, not a guarantee.
    if not _is_tcs:
        _iron_condor_strategy.notify_leg_filled(
            is_leg1        = is_leg1,
            credit         = fill_credit,
            short_contract = short_contract,
            long_contract  = long_contract,
        )

    # v6.9 (AUDIT F6): the alert must describe THIS trade's exits. A TC.6 leg
    # has NO premium stop and NO nickel close — breach of the bound or 15:45,
    # nothing else — and advertising a stop here is a lie on the channel that
    # caught the last identity bug.
    _exit_desc = (f"exit=breach@{getattr(signal, 'underlying_stop', 0.0):.2f} or 15:45"
                  if _is_tcs else
                  f"stop=${fill_credit * (1 + CONDOR_STOP_LOSS_PCT):.2f} | "
                  f"nickel=${CONDOR_NICKEL_CLOSE:.2f}")
    get_alert_manager()._send(
        f"\U0001F985 [{mode}] {INSTRUMENT} | {signal.setup_type} | "
        f"sell={short_contract.strike:.0f} buy={long_contract.strike:.0f} "
        f"x{contracts} credit=${fill_credit:.2f} | "
        f"{_exit_desc} | maxloss=${max_loss:.0f} | "
        f"{fmt_et_short()}"
    )

    logger.info(
        f"[{mode}] CONDOR LEG EXECUTED (tracked): {signal.setup_type} "
        f"short={short_contract.strike:.0f} long={long_contract.strike:.0f} "
        f"x{contracts} credit=${fill_credit:.2f} max_loss=${max_loss:.0f}"
    )


def _safe_strategy(name: str, fn):
    """v4.9 — run ONE strategy evaluation in isolation.

    THE DEFECT (2026-07-30): the dispatch in attempt_new_entry is a bare cascade
    of `if signal is None:` blocks with NO exception handling between them.
    Butterfly is Priority 3; Iron Condor is Priority 4. When butterfly raised
    NameError on `_mult`, the exception went straight to the tick loop and EVERY
    strategy below it was skipped — condor was never asked. Proven on IWM: 161
    `_mult` raises and PLAN=0, while CVX and ORCL (MULT=0, butterfly declining
    cleanly at the GEX gate) built 3 and 4 condor plans on the same tape.

    The dispatcher could not tell "this strategy DECLINED" from "this strategy
    EXPLODED" — and those mean opposite things. A decline means try the next
    priority. An explosion meant abandon the tick and silently suppress every
    strategy below, announcing nothing.

    Returns None on failure so the cascade continues exactly as for a normal
    decline, and logs at ERROR naming the strategy: a raise is a defect and must
    never be quiet, but it must not take the rest of the tick with it.
    """
    try:
        return fn()
    except Exception as exc:                       # noqa: BLE001
        logger.error("%s raised during dispatch — SKIPPED, continuing to the "
                     "next priority; other strategies unaffected. %s: %s",
                     name, type(exc).__name__, exc, exc_info=True)
        return None


def _opening_range(ctx: dict):
    """(orb_high, orb_low) recomputed FROM THE TAPE, or (None, None).

    ⚠️ TCS.3 (2026-08-17) — THE 1m-ONLY VERSION WAS STRUCTURALLY DEAD, and the
    fleet proved it live. v6.7 read `ctx["df_1m"]`, which the cache caps at 60
    bars, while asserting "the bars do not go anywhere." They go off the LEFT
    EDGE of a rolling window: the 09:30-09:35 bars leave a 60-bar 1m frame at
    ~10:35 ET — 25 minutes BEFORE TCS_START_ET (11:00) — so the bound was
    (None, None) for every minute of the credit window, every session, on
    every box, and trend participation could never fire. Fleet-verified
    2026-08-17: `[tcs] no opening-range` on up to 290 of 290 evaluated ticks;
    on GLD/MU/SMH/TLT/GS/SPX/NFLX the vote and ADX gates passed essentially
    ALL morning and every evaluation died here. Its own sibling
    `_session_extremes` already stated the truth this function denied: "each
    is a rolling window and neither is guaranteed to reach 09:30."

    PRIMARY SOURCE IS NOW df_5m. The old "a 5m frame cannot resolve a
    5-minute window" was false for this repo's constants:
    ORB_WINDOW_MINUTES=5 and 5m bars align to :30, so TODAY'S 09:30 bar IS
    the opening range, exactly — and the 5m frame holds it all session on
    every box (RTH-only tape spans the day with margin; SPX's 24h tape
    reaches back ~8.3h, keeping 09:30 in-frame past the close). The 1m
    window remains as the early-session supplement (before today's first 5m
    bar prints) and as the general path for any ORB_WINDOW_MINUTES not
    divisible by 5. Both paths filter to TODAY — an RTH-only 5m frame
    carries ~1.3 sessions, so yesterday's 09:30 bar is usually present too
    and must never become today's bound.

    v6.7's reasons for NOT reading the ORB engine all stand — restart-proof,
    available past the cutoff, one definition. Only the frame was wrong.
    """
    try:
        h0, m0 = RTH_OPEN_ET
        start = h0 * 60 + m0
        end = start + ORB_WINDOW_MINUTES              # exclusive
        # ── 5m primary (TCS.3): today's aligned bars, available all day ──
        if ORB_WINDOW_MINUTES % 5 == 0:
            df5 = ctx.get("df_5m")
            if df5 is not None and not getattr(df5, "empty", True):
                today = df5.index[-1].date()
                rows = [i for i, t in enumerate(df5.index)
                        if t.date() == today
                        and start <= (t.hour * 60 + t.minute) < end]
                if rows:
                    win = df5.iloc[rows]
                    return (float(win["high"].max()),
                            float(win["low"].min()))
        # ── 1m supplement: pre-09:35 partial window / non-5m windows ─────
        df = ctx.get("df_1m")
        if df is None or getattr(df, "empty", True):
            return None, None
        today1 = df.index[-1].date()
        rows = [i for i, t in enumerate(df.index)
                if t.date() == today1
                and start <= (t.hour * 60 + t.minute) < end]
        if not rows:
            return None, None
        win = df.iloc[rows]
        return float(win["high"].max()), float(win["low"].min())
    except Exception as exc:                                   # noqa: BLE001
        logger.debug("opening range unavailable: %s", exc)
        return None, None


def _session_extremes(ctx: dict):
    """(session_high, session_low) from the widest tape available, or (None, None).

    PF.5's third strike filter: a level price has ALREADY TRADED THROUGH today
    is a level the market has proven it can reach, so a short strike must sit
    beyond it. This is the input.

    Takes the max across BOTH frames rather than trusting one: each is a rolling
    window and neither is guaranteed to reach 09:30. A window that starts late
    UNDERSTATES the extreme, which makes the filter LOOSER, not tighter — so the
    failure direction is a missed rejection rather than a wrong one. Returning
    None on absence is deliberate: the strategy logs it as a plumbing fault
    instead of silently trading with the filter switched off.
    """
    hi, lo = None, None
    try:
        for key in ("df_1m", "df_5m"):
            df = ctx.get(key)
            if df is None or getattr(df, "empty", True):
                continue
            h = float(df["high"].max())
            l = float(df["low"].min())
            hi = h if hi is None else max(hi, h)
            lo = l if lo is None else min(lo, l)
    except Exception as exc:                                   # noqa: BLE001
        logger.debug("session extremes unavailable: %s", exc)
        return None, None
    return hi, lo


def _condor_rails(ctx: dict):
    """Daily pitchfork rails for the condor, or None. Never raises.

    DAILY by operator ruling — "It's a guardrail, not the road." A daily fork is
    invalidated only by DAILY closes, so an intraday session cannot move the
    rail a spread was sold against. None means NO CONDOR, which is the whole
    point of the gate.
    """
    try:
        from analysis.pitchfork_observer import rails_for
        return rails_for(ctx, INSTRUMENT, CONDOR_PF_TIMEFRAME)
    except Exception as exc:                                   # noqa: BLE001
        logger.debug("condor rails unavailable: %s", exc)
        return None


def _afternoon_debit_blocked(strategy_name: str, now) -> bool:
    """True when a LONG-PREMIUM DIRECTIONAL entry is refused by the afternoon
    cutoff. Operator, 2026-08-13: "The only other Long that can fire is either
    part of a butterfly or an iron condor vertical spread from 11 o'clock
    onwards."

    A FUNCTION rather than an inline condition so it can be tested without
    standing up the whole entry path, and so the rule has ONE definition. The
    butterfly and the condor are NOT listed here: the butterfly is the
    operator's named exception, and condor legs never reach this gate at all
    (they route through `_execute_condor_leg` earlier in attempt_new_entry), so
    the credit path is exempt BY CONSTRUCTION rather than by a list entry that
    could rot.
    """
    if not DEBIT_BLOCK_ACTIVE:
        return False
    if strategy_name not in DEBIT_DIRECTIONAL_STRATEGIES:
        return False
    return (now.hour, now.minute) >= tuple(DEBIT_DIRECTIONAL_CUTOFF_ET)


def _condor_leg_open_without_plan() -> bool:
    """True if a condor leg is OPEN but no in-memory plan owns it.

    ⚠️ AUDIT F5 — THE PLAN IS PROCESS-LOCAL AND A RESTART ORPHANS THE
    STRUCTURE. `IronCondorStrategy._plan` lives in memory only. On a restart
    with leg 1 filled and leg 2 pending, the plan is GONE — and the plan is the
    only thing that knew leg 2's TRIGGER PRICE, which is in no column, so the
    structure can never complete. **A restart happens on every bake.**

    THE ORPHANED LEG ITSELF IS FINE: `_condor_sibling_open()` reads the DB,
    returns False, and CND.7 correctly manages it as a STANDALONE vertical with
    the ratchet it earns. That part needs no fix.

    WHAT BREAKS IS DEFERRAL. `has_active_plan` goes False, so **TC.6 stops
    standing down and can open a SECOND credit spread on the same underlying**
    while the orphan is still open — two credit verticals on one symbol, which
    nothing sizes or manages as a pair.

    So the symbol stays OCCUPIED as long as a condor leg is open, derived from
    the same persisted fields `_condor_sibling_open` already trusts
    (`is_condor_leg`, `status='open'`) rather than from a plan that did not
    survive. FAILS CLOSED: on any error, treat the symbol as occupied — a
    missed trade costs less than an unmanaged pair.
    """
    try:
        from database.trade_logger import get_trade_logger
        n = sum(1 for t in get_trade_logger().get_open_trades()
                if t.get("is_condor_leg") and t.get("symbol") == INSTRUMENT)
        # A2.2 - the orphan ANNOUNCEMENT no longer lives here: this function is
        # only called inside attempt_new_entry, which only runs when
        # has_open_position() is False - and that falls back to the SAME
        # get_open_trades(). With a leg open this site is unreachable; when
        # reached, n is by construction 0. The warning now fires from the
        # manage branch, where an open leg can actually be seen. This checker
        # stays, side-effect-free, as belt-and-braces on the TC.6 dispatch.
        return n > 0
    except Exception as exc:                                   # noqa: BLE001
        logger.warning("[F5] could not check for an orphaned condor leg (%s) - "
                       "treating the symbol as OCCUPIED", exc)
        return True


def _l1_scores(ctx):
    """The RAW Layer-1 score vector for the axis decomposition, or None.

    ⚠️ P0.3 / AX.3 (2026-08-17). `ctx["l1"]` is the scorer result set at
    `run_regime_classification`; its `.scores` is the vector `regime_axes`
    decomposes. Reading it defensively here means the seven `regime_ctx` call
    sites need no plumbing and a missing/blank L1 simply omits the axes rather
    than raising inside a journal write.
    """
    try:
        r = (ctx or {}).get("l1")
        sc = getattr(r, "scores", None)
        return sc if isinstance(sc, dict) and sc else None
    except Exception:                                          # noqa: BLE001
        return None


def attempt_new_entry(ctx: dict, regime: RegimeState, state: BotState):
    """Try to generate and execute a trade signal."""
    session  = get_session_guard()
    risk_mgr = get_risk_manager()
    scorer   = get_setup_scorer()
    entry_eng = get_entry_engine(state.paper_trading)

    # ── Session gate ──────────────────────────────────────────────────────────
    # Daily loss halt: if the day's NET P&L is down by the limit, take no new
    # trades (open positions keep being managed to exit). Override via configure.sh.
    if risk_mgr.is_halted():
        logger.info("Entry blocked: DAILY LOSS LIMIT reached — halted. Override via configure.sh.")
        return

    can_enter, reason = session.can_enter(ctx["macro"])
    if not can_enter:
        logger.debug(f"Entry blocked: {reason}")
        return

    # ── v5.0 — NO NEW ENTRIES WHILE THE REGIME BOOK IS STALE ──────────────────
    # The asymmetry is deliberate and is the other half of the hold above.
    # HOLDING a label on a stale tick is declining to act on unknown information.
    # OPENING a position is a DECISION — taking on new risk against a
    # classification the engine currently cannot confirm — which is exactly what
    # the rule prohibits. The costs are asymmetric too: a missed entry costs
    # opportunity, and with 29 boxes there is plenty of that; a wrong entry costs
    # capital.
    # Open positions are unaffected: they keep being managed to exit by every
    # price-based stop.
    # v5.4 — ORB IS EXEMPT, and this is a RESTORATION rather than a new licence.
    # v5.0's gate sat ABOVE the dispatch, so it returned before
    # `orb_regime_bypass` (line ~1111) could ever execute — which made
    # ORB_FIRES_REGARDLESS_OF_REGIME, the constant defect V created for exactly
    # this purpose, unreachable on any stale tick. Measured 2026-08-04: the
    # block ran 09:35:01 → 09:39-09:41 ET on ALL 15 boxes, i.e. the first four
    # to six minutes of ORB's own entry window, every session since v5.0.
    # WHY ORB AND NOTHING ELSE. v5.0's rule is "opening a position is a DECISION
    # against a classification the engine cannot confirm". ORB reads no
    # classification: break, retest, close back outside — price structure only,
    # graded on liquidity alone since setup_scorer v1.4. There is no label for a
    # stale label to invalidate. Continuation, condor, butterfly and sweep all
    # genuinely condition on the label and stay blocked.
    # AND STALE IS NOT BLIND. `stale` is the REGIME BOOK (a tick gap past
    # dt_max=90s); the feed has its own guard, latch and pager (market_data v3.3
    # / blindness_latch). A confirmed ORB break on a stale book still has fresh
    # price — which is the whole reason this exemption is safe and why it must
    # NOT be widened to "ignore stale".
    _orb_ctx = ctx.get("orb")
    _orb_exempt = bool(
        ORB_FIRES_REGARDLESS_OF_REGIME and _orb_ctx is not None
        and getattr(_orb_ctx, "state", None) in (ORBState.OPEN_LONG,
                                                 ORBState.OPEN_SHORT))
    if _l2_integ is not None and getattr(_l2_integ, "stale", False):
        if not _orb_exempt:
            logger.info("Entry blocked: regime book is STALE — waiting for a tick "
                        "that resolves it. (Open positions keep being managed.)")
            return
        logger.info("STALE book, but ORB is CONFIRMED — proceeding. ORB reads no "
                    "regime label (defect V); price is not stale, the book is.")


    # ── Fetch options chain (shared across strategies) ────────────────────────
    chain = ctx.get("chain") or get_chain_fetcher().fetch_chain()
    if chain is None:
        logger.warning("Could not fetch options chain — skipping entry attempt")
        return

    macro = ctx["macro"]
    signal = None

    # ── HARD GATE: UNKNOWN / undefined regime ⇒ NO TRADE, full stop. ───────────
    # Memoryless pass-through of the classifier's verdict — it adds ZERO latency
    # and holds NO state. It does not debounce, confirm, or wait: the instant
    # classify() returns a real regime, this passes on the SAME tick, so a
    # UNKNOWN→BREAKOUT transition fires the entry immediately (no late entries).
    # It only blocks when the tape is genuinely unclassified. Leaving UNKNOWN is
    # gated solely by the regime definitions becoming true, never by this gate.
    #
    # EXCEPTION (v3.2, ORB_FIRES_REGARDLESS_OF_REGIME): a confirmed ORB break+
    # retest is self-validating — the engine has already proven the setup
    # independent of the regime label, which the classifier does not even test
    # for. When the switch is on and the engine is in a confirmed OPEN state, an
    # UNKNOWN/undefined label does not veto: it flows through to the ORB dispatch
    # below and the setup scorer decides (regime_conviction just contributes 0).
    orb = ctx["orb"]
    orb_confirmed = orb.state in (ORBState.OPEN_LONG, ORBState.OPEN_SHORT)
    orb_regime_bypass = (ORB_FIRES_REGARDLESS_OF_REGIME and orb_confirmed
                         and regime is not None)
    if (regime is None or getattr(regime, "primary_regime", None)
            in (Regime.UNKNOWN, None, "")) and not orb_regime_bypass:
        logger.info("STRATEGY: NO TRADE — regime UNKNOWN/undefined (hard gate)")
        return

    # ── Strategy dispatch: regime → strategy ──────────────────────────────────
    # ── AFD.1 PRE-DISPATCH BLOCK (v6.6, 2026-08-14) ──────────────────────────
    # ⚠️ THIS WAS A POST-SELECTION VETO AND THAT WAS THE BUG. The gate ran AFTER
    # every strategy had been evaluated, so past 11:00 a debit strategy could
    # still WIN the slot — `signal` became non-None, TC.6 (which sits behind
    # `if signal is None`) never ran, and only THEN was the debit signal
    # refused. **The tick produced no trade at all, and the slot the spec says
    # TC.6 owns was consumed by a strategy forbidden to trade in it.**
    # Placing it after the signal was chosen was right for JOURNALLING (the
    # refused signal is fully formed) and wrong for ARBITRATION. A strategy that
    # cannot trade in this window must not be EVALUATED in it.
    # The post-selection gate below is RETAINED as defence in depth: it costs
    # nothing, it still journals a fully-formed refusal if anything slips
    # through, and it catches a future strategy added to
    # DEBIT_DIRECTIONAL_STRATEGIES that forgets this pre-gate.
    _now_disp = now_et()
    _afd_orb  = _afternoon_debit_blocked("ORBStrategy", _now_disp)
    _afd_cont = _afternoon_debit_blocked("ContinuationStrategy", _now_disp)
    _afd_swp  = _afternoon_debit_blocked("SweepReversal", _now_disp)
    if _afd_orb or _afd_cont or _afd_swp:
        logger.info("[afd] pre-dispatch: debit directional blocked past the "
                    "cutoff (orb=%s cont=%s sweep=%s) — the afternoon slot "
                    "belongs to the credit structures",
                    _afd_orb, _afd_cont, _afd_swp)
        # ── AUDIT F8 (2026-08-15) — THE REFUSAL JOURNAL MOVED WITH THE GATE ──
        # Moving AFD.1 to pre-dispatch made the POST-SELECTION journal at the
        # bottom of this function STRUCTURALLY UNREACHABLE for these three
        # strategies: they are skipped, so no signal is ever formed to carry a
        # `gate_block:afternoon_debit` disposition. **The cutoff's telemetry
        # went to zero the moment the slot bug was fixed** - a silent loss, and
        # exactly the class the repo's own gate-ordering reasoning warns about.
        # ⚠️ HONEST TRADEOFF, STATED: there is no SIGNAL here, so this record
        # carries no contract, strike or score. It answers "the cutoff fired and
        # for whom", not "what would have traded". The richer post-selection
        # record is retained below for anything that still reaches it.
        if _sigj is not None:
            try:
                for _nm, _hit in (("ORBStrategy", _afd_orb),
                                  ("ContinuationStrategy", _afd_cont),
                                  ("SweepReversal", _afd_swp)):
                    if _hit:
                        _sigj.journal("disposition",
                                      outcome="gate_block:afternoon_debit",
                                      signal={"strategy": _nm,
                                              "stage": "pre_dispatch"},
                                      regime=_sigj.regime_ctx(regime, _l1_scores(ctx)))
            except Exception:                                  # noqa: BLE001
                pass

    # ══ G6 (v6.22) — ICT PRE-LADDER DISPATCH ═══════════════════════════════
    # The seven ICT setups run HERE, ahead of the label-keyed ladder below,
    # because that ladder gates every branch on `primary_regime` and would
    # discard a Silver Bullet for the crime of a COMPRESSION label. Operator,
    # 2026-08-18: a regime label may be USED by a setup that earns something
    # from it, but it may never be a silent precondition. This branch consults
    # no label at all.
    #
    # ⚠️ RUNS EVERY TICK, ON PURPOSE, even when nothing can fire. The suite
    # journals FORMING states continuously and that journal is the only data
    # from which the priors ever get fitted. A "dispatch only when armed"
    # shortcut would leave us with an empty journal and nothing to calibrate —
    # the parent's exact mistake, which is why this fork exists.
    #
    # SAFETY: three independent gates inside the suite all default CLOSED
    # (OT_ICT_ARMED, per-setup OT_ICT_<NAME>_VALIDATED, the 11:30 debit
    # cutoff), so until the operator arms a validated setup this branch can
    # only ever return None. `None` falls through to the ladder unchanged.
    # v6.24 — ACTION ONLY. The GRADING pass already ran unconditionally in
    # run_regime_classification and journaled every setup's state, so this
    # branch is purely "may one of them fire?". It consumes the context built
    # there rather than rebuilding it — one context per tick, so the state the
    # journal recorded is the state the entry decision was made on. If the
    # grading pass failed, ctx["ictx"] is absent and dispatch is skipped:
    # acting on a context we could not journal would be the worst of both.
    ict_sig = None
    _ictx = ctx.get("ictx")
    if _ICT_OK and _ictx is not None:
        try:
            ict_sig = ict_dispatch(
                _ictx, chain=chain, now_et=now_et(),
                journal=(_sigj.journal if _sigj is not None else None))
        except Exception as _ie:                               # noqa: BLE001
            logger.error("[ict] dispatch failed (%s) — no ICT entry this "
                         "tick; the ladder below is unaffected", _ie)
    if ict_sig is not None:
        signal = ict_sig
        # ── SB/ORB SHARE THE SLOT, and the counterfactual is recorded ───────
        # Operator's §4.2 decision: ICT ranks first, ORB takes the ticks it
        # does not want, and every preemption is journaled so "what did the
        # ranking cost?" is answerable from data rather than opinion. Without
        # this row, an ORB that never fired is indistinguishable from an ORB
        # that never set up.
        if orb_confirmed and not _afd_orb:
            logger.info("[ict] %s preempted a CONFIRMED ORB this tick",
                        signal.strategy_name)
            if _sigj is not None:
                try:
                    _sigj.journal("disposition",
                                  outcome="preempted:ict_ranked_first",
                                  signal={"strategy": "ORBStrategy",
                                          "stage": "pre_ladder",
                                          "preempted_by": signal.strategy_name},
                                  regime=_sigj.regime_ctx(regime,
                                                          _l1_scores(ctx)))
                except Exception:                              # noqa: BLE001
                    pass
        logger.info("[ict] %s takes the slot — the label ladder is skipped "
                    "this tick", signal.strategy_name)

    # Priority 1: ORB — only when the engine has a CONFIRMED break+retest.
    # With ORB_FIRES_REGARDLESS_OF_REGIME on, a confirmed ORB also fires under
    # UNKNOWN and SWEEP_REVERSAL (ORB beats sweep — the engine no longer defers
    # its OPEN under a sweep label; see orb_engine v3.2). The break+retest is the
    # edge; the label is not consulted for go/no-go, only for scoring.
    _orb_ok_regimes = (
        Regime.TRENDING_BULL, Regime.TRENDING_BEAR,
        Regime.BREAKOUT_VOLATILE, Regime.RANGING, Regime.COMPRESSION
    )
    # v6.23 (2026-08-19) — ORB IS BLOCKED UNDER RANGING (operator: that cell is
    # the conclusive loss leader). Journaled as a REFUSAL, not silence: without
    # this row "ORB did not fire" and "ORB was forbidden to fire" look identical
    # in the record, and the second is a decision we need to be able to audit
    # and reverse. OT_ORB_BLOCK_RANGING=0 restores the old behaviour.
    if (ORB_BLOCK_RANGING and signal is None and orb_confirmed and not _afd_orb
            and regime.primary_regime == Regime.RANGING):
        logger.info("ORB: BLOCKED — confirmed break+retest under RANGING, "
                    "which is a blocked cell by operator direction")
        if _sigj is not None:
            try:
                _sigj.journal("disposition",
                              outcome="gate_block:orb_ranging",
                              signal={"strategy": "ORBStrategy",
                                      "stage": "regime_gate"},
                              regime=_sigj.regime_ctx(regime, _l1_scores(ctx)))
            except Exception:                                  # noqa: BLE001
                pass
    elif signal is None and orb_confirmed and not _afd_orb and (
            regime.primary_regime in _orb_ok_regimes
            or (ORB_FIRES_REGARDLESS_OF_REGIME and
                regime.primary_regime in (Regime.UNKNOWN, Regime.SWEEP_REVERSAL))):
        orb_sig = _safe_strategy("ORB", lambda: _orb_strategy.generate_signal(
            orb           = orb,
            regime        = regime,
            vol_state     = ctx["vol"],
            liq_map       = ctx["liq_map"],
            chain         = chain,
            macro         = macro,
            current_price = ctx["price"]
        ))
        if orb_sig:
            signal = orb_sig
            get_orb_engine().mark_triggered()

    # ── Post-runaway routing (v-runaway-fix 2026-07-24) ───────────────────────
    # A RUNAWAY ORB (broke the range and ran to 50% TP with no retest) is a
    # MOMENTUM/TREND event, not an exhaustion. It must hand off to CONTINUATION
    # (enter WITH the move on a pullback), NOT to sweep reversal (which fades the
    # move and gets run over — the afternoon-giveback pattern). Sweep only runs
    # AFTER continuation has no setup, and then ONLY against a NAMED level
    # (PDH/PDL/session) — a reversal off a weak equal-H/L at the end of a strong
    # push is exactly the low-quality sweep that bled last week.
    _is_runaway = getattr(orb, "invalidation_reason", "") == "runaway"

    # Priority 2 (was sweep): Trend Continuation.
    # The runaway proved directional force, so it gets FIRST refusal on the
    # pullback via the looser handoff gate — even if the regime label has since
    # flipped to SWEEP_REVERSAL/BREAKOUT (a runaway commonly flips it). The
    # standalone (stricter) path still requires a trending label.
    # CNT.1 (v5.7) — BREAKOUT_VOLATILE added. The strategy decides whether it
    # can actually take it: it fires only if the trend engine's own vote gives a
    # direction (BULLISH/BEARISH, not NEUTRAL) AND primary_adx clears
    # CONT_BREAKOUT_MIN_ADX. Widening this tuple alone would NOT open the trade —
    # the direction branch inside the strategy is what does, and it self-vetoes
    # on a directionless tape.
    # ── CNT.6 (2026-08-10) — A CONTINUATION CANNOT CONTINUE A TREND THAT THE
    # LABEL SAYS IS NOT THERE. RANGING and COMPRESSION assert the absence of a
    # trend, so continuation in them is a contradiction, not a permissive edge.
    # ⚠️ THE BYPASS IS THE BUG: `_is_runaway` is OR'd with the regime tuple, so a
    # runaway ORB flag let continuation fire on ANY tape — at Priority 2, ahead
    # of Butterfly (P3, RANGING/COMPRESSION) and Condor (P4, RANGING), which sit
    # behind `if signal is None` and were never even evaluated. That is the
    # squeeze: 13 sessions show RANGING → Continuation 94 vs IronCondor 27, and
    # COMPRESSION → Continuation 39 vs Butterfly 6.
    # The block goes HERE rather than in the strategy because a strategy-level
    # veto still consumes the dispatch slot on its way to returning None — CNT.3
    # blocked the COMPRESSION handoff inside continuation_strategy and the
    # squeeze continued regardless.
    _cont_blocked = (CONT_BLOCK_PREMIUM_REGIMES
                     and regime.primary_regime in (Regime.RANGING, Regime.COMPRESSION))
    if _cont_blocked and (_is_runaway
                          or regime.primary_regime in (Regime.TRENDING_BULL,
                                                       Regime.TRENDING_BEAR,
                                                       Regime.BREAKOUT_VOLATILE)):
        logger.info(f"[continuation] BLOCKED — regime {regime.primary_regime} is a "
                    f"premium regime; a continuation needs a trend to continue "
                    f"(runaway={_is_runaway}). Butterfly/Condor now get the slot.")
    if signal is None and not _cont_blocked and not _afd_cont and (
            _is_runaway
            or regime.primary_regime in (Regime.TRENDING_BULL, Regime.TRENDING_BEAR,
                                         Regime.BREAKOUT_VOLATILE)):
        cont_sig = _safe_strategy("Continuation", lambda: _continuation_strategy.generate_signal(
            regime        = regime,
            vol_state     = ctx["vol"],
            trend         = ctx["trend"],
            chain         = chain,
            current_price = ctx["price"],
            is_handoff    = _is_runaway,   # runaway ORB -> looser handoff gate
            handoff_direction = getattr(orb, "break_direction", "") if _is_runaway else "",
            structure     = ctx.get("structure"),
            df_1m         = ctx.get("df_1m"),
            macro         = macro,
        ))
        if cont_sig:
            if _is_runaway:
                cont_sig.setup_type = cont_sig.setup_type or "trend_continuation_handoff"
                logger.info("[continuation] ORB-runaway HANDOFF -> trend continuation")
            signal = cont_sig

    # Priority 2.5 (was 2): Sweep Reversal.
    # After a runaway, sweep is the FALLBACK (continuation had no pullback setup)
    # and is gated to NAMED levels only — a runaway that then sweeps a real pool
    # and rejects is a legitimate reversal; a runaway that pokes an equal-H/L is
    # not. Non-runaway sweeps are unchanged (fire as before on the SWEEP label).
    # v5.6 (SWP.1) — SWEEP IS AN EVENT, NOT A REGIME. This required the
    # committed label to be SWEEP_REVERSAL; that label wins 0.4% of live ticks
    # and is exactly zero on 96%, so the trade was effectively off, and F7's
    # commit threshold narrowed it further. It now gates on the L1 _sweep SETUP
    # SCORE, whose three HARD VETOES are precisely the operator's stated
    # condition — a NAMED level (veto_loc), REJECTED back through (veto_reclaim),
    # not accepted beyond (veto_accept). A non-zero score already means all
    # three passed.
    # THE PLTR PROTECTION TRAVELS WITH THE SCORE: `trend_opp` is a
    # soft-necessary inside _sweep, so a reversal into a strong ACCELERATING
    # opposing trend still scores 0 and still cannot fire. That guard lived in
    # the scorer, never in this gate — which is why gating on the score keeps it
    # and gating on anything else would have lost it.
    _sweep_setup = 0.0
    _l1r = ctx.get("l1")
    if _l1r is not None:
        _sweep_setup = (getattr(_l1r, "scores", {}) or {}).get("SWEEP_REVERSAL") or 0.0
    if signal is None and not _afd_swp and _sweep_setup >= SWEEP_SETUP_FLOOR:
        sweep_sig = _safe_strategy("SweepReversal", lambda: _sweep_strategy.generate_signal(
            regime        = regime,
            setup_score   = _sweep_setup,
            vol_state     = ctx["vol"],
            structure     = ctx["structure"],
            liq_map       = ctx["liq_map"],
            chain         = chain,
            macro         = macro,
            df_1m         = ctx.get("df_1m"),
            current_price = ctx["price"]
        ))
        if sweep_sig is not None and _is_runaway and not getattr(sweep_sig, "swept_level_name", ""):
            # post-runaway sweep on an UNNAMED (equal-H/L) level — refuse it.
            logger.info("[sweep] post-runaway sweep on unnamed level — BLOCKED "
                        "(runaway hands to continuation; sweep only on named levels)")
            sweep_sig = None
        signal = sweep_sig

    # Priority 3: Butterfly (Ranging/Compression — requires GEX PINNING)
    # Fed days allowed — bot reaction time is faster and more systematic
    # than manual trading on a volatile FOMC day. Fed day boosts ORB
    # conviction instead of blocking entries.
    if (signal is None and
            not DIRECTIONAL_ONLY and
            regime.primary_regime in (Regime.RANGING, Regime.COMPRESSION) and
            macro.butterfly_allowed):
        signal = _safe_strategy("Butterfly", lambda: _butterfly_strategy.generate_signal(
            regime        = regime,
            vol_state     = ctx["vol"],
            liq_map       = ctx["liq_map"],
            chain         = chain,
            macro         = macro,
            current_price = ctx["price"],
            gex           = ctx.get("gex")
        ))

    # Priority 4: Iron Condor — legged entry, RANGING fallback when no GEX pin.
    if not _iron_condor_strategy.has_active_plan:
        # Try to make a condor plan if no other signal fired and regime is RANGING.
        # NOTE (2026-08-04): DIRECTIONAL_ONLY is EMPTY fleet-wide — config.py:220
        # set FULL_STRATEGY_INSTRUMENTS = set(STRIKE_INCREMENTS) on the
        # 2026-07-14 operator directive ("neutral strategies enabled FLEET-WIDE
        # for data collection"), so EVERY box is condor-eligible. The old
        # comment here read "Skipped for directional-only instruments (single
        # names)" and was false for three weeks; it cost an investigation on
        # 2026-08-04 that concluded only SPX and QQQ could plan condors. The
        # check stays — it is correct if the set is ever narrowed again — but
        # do not read it as describing today's fleet.
        if (signal is None and
                not DIRECTIONAL_ONLY and
                regime.primary_regime == Regime.RANGING):
            _sess_hi, _sess_lo = _session_extremes(ctx)
            _rails = _condor_rails(ctx)
            plan = _safe_strategy("CondorPlan", lambda: _iron_condor_strategy.decide(
                regime        = regime,
                vol_state     = ctx["vol"],
                chain         = chain,
                macro         = macro,
                current_price = ctx["price"],
                rails         = _rails,           # PF.5 — None means NO CONDOR
                session_high  = _sess_hi,
                session_low   = _sess_lo
            ))
            # Plan is informational — no order yet. Leg triggers fire on
            # subsequent ticks via check_leg_triggers().
            if plan:
                logger.info(
                    f"Condor plan active — Leg 1={plan.leg1_side.upper()} "
                    f"trigger@{plan.call_trigger_price if plan.leg1_side == 'call' else plan.put_trigger_price:.0f}"
                )
                if _sigj is not None:
                    try:
                        _sigj.journal("condor_plan",
                                      regime=_sigj.regime_ctx(regime, _l1_scores(ctx)),
                                      plan={"leg1_side": plan.leg1_side,
                                            "call_trigger": round(plan.call_trigger_price, 2),
                                            "put_trigger": round(plan.put_trigger_price, 2),
                                            "underlying": round(ctx["price"], 2)})
                    except Exception:
                        pass
    else:
        # Active plan: check if a leg should fire this tick
        leg_signal = _safe_strategy("CondorLeg", lambda: _iron_condor_strategy.check_leg_triggers(
            regime        = regime,
            chain         = chain,
            current_price = ctx["price"]
        ))
        if leg_signal is not None:
            # Route directly to entry — bypasses normal signal/score path
            # since condor legs are credit spreads with their own P&L math.
            # v3.9: journal conviction at fire time — the condor's Phase-3
            # bar (provisional 0.65) is uncalibratable without it.
            if _sigj is not None:
                try:
                    _sigj.journal("condor_leg",
                                  regime=_sigj.regime_ctx(regime, _l1_scores(ctx)),
                                  leg={"underlying": round(ctx["price"], 2)})
                except Exception:
                    pass
            _execute_condor_leg(leg_signal, state, ctx)

    # ── TC.6 TREND CREDIT SPREAD ─────────────────────────────────────────────
    # Sells a defined-risk vertical BEYOND the broken ORB boundary after a
    # runaway. Placed HERE, after the condor, for two reasons:
    #   · it routes through `_execute_condor_leg` like a condor leg, so it must
    #     sit where that path is reachable;
    #   · the condor holds the slot when both want the symbol — it got there
    #     first, and stacking a third credit spread on one underlying is
    #     unmanaged risk. `condor_active` carries that deferral.
    # NOT blocked by AFD.1: `DEBIT_DIRECTIONAL_STRATEGIES` is a name list and a
    # credit vertical is not on it — correct by construction, pinned by a test.
    if signal is None:
        _tcs_hi, _tcs_lo = _session_extremes(ctx)
        _orb_hi, _orb_lo = _opening_range(ctx)   # from the TAPE, not the engine
        tcs_sig = _safe_strategy("TrendCreditSpread", lambda: (
            _trend_credit_strategy.generate_signal(
                regime        = regime,
                vol_state     = ctx["vol"],
                chain         = chain,
                macro         = macro,
                current_price = ctx["price"],
                trend         = ctx.get("trend"),   # direction source
                orb_high      = _orb_hi,            # bound, recomputed from bars
                orb_low       = _orb_lo,
                session_high  = _tcs_hi,
                session_low   = _tcs_lo,
                condor_active = (_iron_condor_strategy.has_active_plan
                                 or _condor_leg_open_without_plan()))))
        if tcs_sig is not None:
            _execute_condor_leg(tcs_sig, state, ctx)
            return

    if signal is None:
        logger.info(f"STRATEGY: NO TRADE — regime={regime.primary_regime}")
        return

    # ── AFTERNOON DEBIT BLOCK (2026-08-13) ────────────────────────────────────
    # Operator: "no long contracts in the afternoon unless they're part of a
    # vertical spread or a butterfly."
    # PLACED HERE, AFTER THE SIGNAL IS CHOSEN, ON PURPOSE — three reasons:
    #   1. ONE gate instead of three. Guarding each dispatch branch means the
    #      next strategy added silently bypasses the rule.
    #   2. The blocked signal is fully formed, so the journal records WHAT WAS
    #      REFUSED. A gate that vetoes invisibly can never be calibrated from
    #      its own rejections — the same reasoning that put gates E and F after
    #      the score in setup_scorer rather than before it.
    #   3. Condor legs never reach here (they route through
    #      `_execute_condor_leg` above), so the credit path is untouched by
    #      construction rather than by an exemption that could rot.
    # Butterfly and condor are exempt; both are already window-gated elsewhere.
    if _afternoon_debit_blocked(signal.strategy_name, now_et()):
        if True:
            logger.info(
                "STRATEGY: BLOCKED — %s is long premium and it is past the "
                "%02d:%02d ET afternoon debit cutoff (%s). Credit verticals and "
                "the pin butterfly are unaffected.",
                signal.strategy_name, DEBIT_DIRECTIONAL_CUTOFF_ET[0],
                DEBIT_DIRECTIONAL_CUTOFF_ET[1], fmt_et_short())
            if _sigj is not None:
                try:
                    _sigj.journal("disposition",
                                  outcome="gate_block:afternoon_debit",
                                  signal=_sigj.signal_ctx(signal),
                                  regime=_sigj.regime_ctx(regime, _l1_scores(ctx)))
                except Exception:                              # noqa: BLE001
                    pass
            return

    # ── v6.19 — SMC REVOCATION GATE (fork) ────────────────────────────────────
    # Permissive-until-disqualified (operator, 2026-08-17): entries stand
    # UNLESS the active SMC setup was REVOKED against the signal's direction —
    # the QQQ-08-17 acceptance behavior, withdrawing permission only once the
    # market has ESTABLISHED the disqualifier. Placed here for the same three
    # reasons as the afternoon-debit gate directly above: one gate instead of
    # per-branch guards, the refused signal is fully formed so the journal
    # records WHAT was refused, and condor legs (direction-neutral) never
    # reach this seam by construction. OT_SMC_REVOKE_GATES=0 disarms it.
    if _REGIME_ENGINE == "smc" and _smc_engine is not None:
        _sig_dir = ("bullish" if getattr(signal, "option_side", "") == "call"
                    else "bearish" if getattr(signal, "option_side", "") == "put"
                    else "")
        if _sig_dir and not _smc_engine.entry_permitted(_sig_dir):
            logger.info("STRATEGY: BLOCKED — SMC setup REVOKED against %s "
                        "(%s); permission withdrawn until a fresh setup "
                        "forms.", _sig_dir, signal.strategy_name)
            if _sigj is not None:
                try:
                    _sigj.journal("disposition",
                                  outcome="gate_block:smc_revoked",
                                  signal=_sigj.signal_ctx(signal),
                                  regime=_sigj.regime_ctx(regime,
                                                          _l1_scores(ctx)))
                except Exception:                          # noqa: BLE001
                    pass
            return

    if not signal.is_valid:
        logger.warning(f"Invalid signal from {signal.strategy_name}")
        if _sigj is not None:
            try:
                _sigj.journal("disposition", outcome="invalid_signal",
                              signal=_sigj.signal_ctx(signal),
                              regime=_sigj.regime_ctx(regime, _l1_scores(ctx)))
            except Exception:
                pass
        return

    # ── Score and size ─────────────────────────────────────────────────────────
    score  = scorer.score(
        signal    = signal,
        regime    = regime,
        vol_state = ctx["vol"],
        structure = ctx["structure"],
        liq_map   = ctx["liq_map"],
        macro     = macro
    )

    if score is None:
        # Setup scored below the B threshold — there is no C grade.
        # This is not a trade, regardless of available capital.
        logger.info(f"STRATEGY: NO TRADE — {signal.strategy_name} setup below B threshold")
        return

    sizing = risk_mgr.compute_size(
        premium           = signal.entry_premium,
        grade             = score.grade,
        is_butterfly      = signal.is_butterfly,
        net_debit         = signal.net_debit if signal.is_butterfly else 0.0,
        butterfly_half_size = macro.butterfly_half_size if signal.is_butterfly else False
    )

    if not sizing.allowed:
        logger.info(f"Sizing rejected: {sizing.reject_reason}")
        if _sigj is not None:
            try:
                _sigj.journal("disposition", outcome="sizing_rejected",
                              reason=str(sizing.reject_reason),
                              signal=_sigj.signal_ctx(signal),
                              regime=_sigj.regime_ctx(regime, _l1_scores(ctx)),
                              score={"grade": score.grade,
                                     "total": score.score})
            except Exception:
                pass
        return

    # Populate contract count in signal
    signal.contracts  = sizing.contracts
    signal.total_cost = sizing.total_cost

    # ── Enter trade ───────────────────────────────────────────────────────────
    record = entry_eng.enter(signal=signal, score=score, sizing=sizing)
    if record:
        # v5.1 — capture BEFORE anything else touches the row, but AFTER the
        # fill: the picture we want is the one that produced this entry.
        _capture_entry_snapshot(ctx, record, signal.direction)
        _capture_entry_contract(ctx, record)          # v5.5 (N.9)
        get_position_manager(state.paper_trading).set_open_position(record)
        get_alert_manager().send_entry_alert(record)
        logger.info(
            f"✅ Entry: {signal.setup_type} "
            f"grade={score.grade} "
            f"contracts={sizing.contracts} "
            f"total=${sizing.total_cost:.2f}"
        )
        if _sigj is not None:
            try:
                _orb_ctx = None
                if signal.strategy_name == "ORBStrategy":
                    _depth = float(getattr(ctx["orb"], "retest_depth_px", 0.0))
                    _atr   = float(getattr(ctx["vol"], "atr_current", 0.0))
                    _orb_ctx = {"retest_depth_px": round(_depth, 4),
                                "retest_depth_atr": (round(_depth / _atr, 4)
                                                     if _atr > 0 else None)}
                # v5.9 — L1 EVIDENCE AT THE MOMENT OF THE FIRE.
                # `regime_ctx` records only label + conviction, so every term
                # that DECIDED the entry — the sweep's spent_val, ambient,
                # rejq_val, exh_val, trend_opp, touch_count, depth_val,
                # opp_adx, momentum — was computed here and then dropped.
                # Characterising entries afterwards would have meant REPLAYING
                # the tape and hoping the replayed score matched the one that
                # actually fired. The values exist at this line; recording them
                # costs one payload and no computation.
                # Always: the six-score VECTOR — cheap, and it is the ambient
                # context for ANY entry, not only sweeps.
                # Additionally: the firing setup's OWN breakdown, keyed by
                # strategy, so a fire does not carry five unused breakdowns.
                _l1_ctx = None
                try:
                    _l1r = ctx.get("l1")
                    if _l1r is not None:
                        _l1_ctx = {"scores": {str(k): _rnd4(v)
                                              for k, v in (_l1r.scores or {}).items()}}
                        _bdkey = _L1_BREAKDOWN_FOR.get(signal.strategy_name)
                        if _bdkey:
                            _bd = (_l1r.breakdown or {}).get(_bdkey)
                            if _bd:
                                _l1_ctx["breakdown"] = _bd
                                _l1_ctx["breakdown_of"] = str(_bdkey)
                except Exception:
                    _l1_ctx = None
                _sigj.journal("disposition", outcome="fired",
                              signal=_sigj.signal_ctx(signal),
                              regime=_sigj.regime_ctx(regime, _l1_scores(ctx)),
                              l1=_l1_ctx,
                              score={"grade": score.grade,
                                     "total": score.score},
                              fill={"contracts": sizing.contracts,
                                    "total_cost": round(sizing.total_cost, 2)},
                              orb=_orb_ctx)
            except Exception:
                pass



def _rnd4(v):
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return None


# v5.9 — which L1 breakdown belongs to a firing strategy. A WRONG entry here
# does not raise: it files a well-formed breakdown from the wrong scorer under a
# correct-looking key, and a week of collection would be characterised against
# features that decided nothing. ORB and Butterfly are deliberately ABSENT —
# ORB is regime-immune at both dispatch and exit, so attaching a regime
# breakdown to it would imply a dependency the engine does not have. An unmapped
# strategy records the score vector and NO breakdown, never a wrong one.
_L1_BREAKDOWN_FOR = {
    "SweepReversal":          "SWEEP_REVERSAL",
    "ContinuationStrategy":   "TRENDING",   # score() files BOTH trend scorers'
                                            # shared breakdown under this key,
                                            # not under the BULL/BEAR labels
    "IronCondorStrategy":     "RANGING",
}


def handle_session_reset(state: BotState):
    """Reset session-level state at the start of each RTH day."""
    if not state.session_reset_done:
        logger.info("RTH open — resetting session state")
        get_risk_manager().reset_session()
        state.session_reset_done = True
        state.orb_reset_done     = False
        state.orb_range_established_today = False

    if not state.orb_reset_done:
        get_orb_engine().reset_for_session()
        state.orb_reset_done = True
        logger.info("ORB engine reset for new session")

    # Fetch the ORB range only AFTER 9:35 ET when the 9:30-9:35 candle
    # is fully closed and baked. Fetching at 9:30 returns a degenerate
    # candle (high == low == 0 width) because the candle is still forming.
    if not state.orb_range_established_today:
        now_et_dt = datetime.now(ZoneInfo("US/Eastern"))
        if (now_et_dt.hour, now_et_dt.minute) >= (9, 30):
            # Poll from the open: 9:30-9:35 writes IN_PROGRESS, then ESTABLISHED
            # once the candle closes. Latch ONLY on ESTABLISHED (returns True) so
            # we keep polling across IN_PROGRESS/EXPIRED instead of locking in a
            # carried-over range for the session.
            state.orb_range_established_today = _fetch_orb_range()


def handle_hard_close(state: BotState):
    """Force-close every open position at 15:45 ET — durably.

    Routes through pos_mgr.flatten_all(), which closes ALL open records (both
    condor legs) via the full exit accounting so each DB row is actually marked
    closed and booked — not just an order submitted. The main loop calls this
    every tick from 15:45 to 16:00, so an incomplete close is retried
    automatically; a persistent failure pages once (before the 16:00 stop turns
    it into an overnight orphan).
    """
    pos_mgr = get_position_manager(state.paper_trading)
    if not pos_mgr.has_open_position():
        state.hard_close_alerted = False   # nothing open — clear any prior page
        return

    instrument = os.environ.get("OT_INSTRUMENT", INSTRUMENT)
    # v3.4: fetch the chain ONCE for the hard-close so flatten_all can get real
    # marks (paper: simulated fill price; live: context). Without it, marks were
    # None and paper booked at entry premium -> every leg logged $0.00, poisoning
    # calibration. Fetched once here and reused across the 15:45->16:00 retries.
    chain = None
    try:
        chain = get_chain_fetcher().fetch_chain()
    except Exception as e:
        logger.warning(f"Hard close: chain fetch failed ({e}); "
                       f"paper marks may be unavailable this pass — will retry")
    failed = pos_mgr.flatten_all("hard_close_15:45_ET", chain=chain)

    if not failed:
        logger.info("HARD CLOSE complete — all positions flat.")
        state.hard_close_alerted = False
        return

    logger.error(
        f"HARD CLOSE INCOMPLETE [{instrument}]: {len(failed)} still open "
        f"{[t[:8] for t in failed]} — retrying every tick until 16:00"
    )
    if not state.hard_close_alerted:
        get_alert_manager().send_hard_close_failure_alert(instrument, failed)
        state.hard_close_alerted = True


def _check_blindness(state: BotState):
    """Page the operator when the bot cannot see, and again when it can.

    Requirement (2026-08-01): ANY blinding condition — the feed down, stale data,
    a dead heartbeat, or anything else — notifies immediately AND logs the exact
    conditions, so the outage can be troubleshot rather than guessed at.

    This COMPLEMENTS the existing bot/service-down notification rather than
    duplicating it: that one fires when the bot STOPS, this one fires when the
    bot KEEPS RUNNING on data it cannot trust. Process alive, service green,
    trading blind was the uncovered middle.

    The snapshot reported is the one the latch captured at the FIRST blind tick,
    not the current state — by the time the latch trips, a feed that reconnected
    mid-outage would otherwise report healthy fields alongside the alert.
    """
    verdict = state.blind_latch.update(last_blindness())
    clear_blindness()          # this tick's fetches record fresh evidence

    if verdict == _BLIND_ALERT:
        instrument = os.environ.get("OT_INSTRUMENT", INSTRUMENT)
        snap = state.blind_latch.snapshot or {}
        try:
            open_rows = get_trade_logger().get_open_trades_live()
            descs = [getattr(r, "position_desc", None) or str(r) for r in open_rows]
        except Exception as e:                                    # noqa: BLE001
            # Never let the position read swallow the alert — a DB problem while
            # blind is more reason to page, not less.
            logger.error(f"blind alert: open-position read failed: {e}")
            descs = ["position read FAILED — check manually"]   # v4.12: no angle brackets; see alert_manager v1.10
        get_alert_manager().send_blind_alert(
            instrument, snap, open_positions=descs,
            paper=state.paper_trading,
            blind_for_s=state.blind_latch.blind_for_s())

    elif verdict == _BLIND_RECOVERED:
        instrument = os.environ.get("OT_INSTRUMENT", INSTRUMENT)
        # duration/cause come from the preserved fields — the latch has already
        # reset its live state by the time RECOVERED is returned.
        get_alert_manager().send_sight_restored_alert(
            instrument, state.blind_latch.last_outage_s,
            state.blind_latch.last_outage_cause)


def main_loop(state: BotState):
    pos_mgr = get_position_manager(state.paper_trading)

    while True:
        tick_start  = time.time()
        state.tick_count += 1

        try:
            # ── Pre-RTH: sleep until open ──────────────────────────────────
            if not is_rth():
                if state.session_reset_done:
                    # Day ended — reset flag so it fires again tomorrow
                    state.session_reset_done = False
                secs = seconds_until_rth_open()
                if secs > 120:
                    logger.info(
                        f"Market closed. Next RTH open in "
                        f"{secs/60:.0f} min. Sleeping 60s."
                    )
                    time.sleep(60)
                    continue
                else:
                    logger.info(f"RTH opens in {secs:.0f}s — standing by")
                    time.sleep(max(secs - 5, 5))
                    continue

            # ── RTH session reset ──────────────────────────────────────────
            handle_session_reset(state)

            # ── BLINDNESS WATCH (v4.11) ────────────────────────────────────
            # Evaluates the record left by the PREVIOUS tick's data fetches,
            # then clears it so this tick starts with a clean slate. The one-
            # tick lag is immaterial — the latch waits several ticks and 45s
            # before paging anyway — and reading it here means EVERY blind
            # path is covered, including the ones that raise out of
            # run_analysis before any later code could check.
            #
            # Deliberately keyed on the SYMPTOM (market_data could not serve
            # current data) rather than an enumerated list of causes: a cause
            # list only ever covers the failures already thought of, and the
            # requirement is "anything else that is blinding it".
            _check_blindness(state)

            # ── Intraday broker reconcile (LIVE + enabled) ─────────────────
            # Every 30 min across RTH, last sweep at 15:30 — catches a broker-
            # side leg closure (e.g. shorts auto-closed) before the 15:45
            # flatten acts. Fires once per slot; fail-safe on a bad/empty read.
            if not state.paper_trading and BROKER_RECONCILE_ENABLED:
                slot = _intraday_reconcile_slot(now_et())
                if slot and slot != state.last_reconcile_slot:
                    state.last_reconcile_slot = slot
                    _intraday_reconcile(
                        state, os.environ.get("OT_INSTRUMENT", INSTRUMENT)
                    )

            # ── Hard close check ──────────────────────────────────────────
            if is_hard_close_time():
                handle_hard_close(state)
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            # ── Main analysis ─────────────────────────────────────────────
            ctx = run_analysis(state)

            # ── Regime reassessment — EVERY TICK ──────────────────────────
            # "Regime aware" means aware now, not eventually. Classification is
            # cheap (threshold checks over the ctx run_analysis already computed),
            # so we reclassify every tick — no throttle. Verified safe: the only
            # stateful consumer of regime is exit_engine's regime-flip exits
            # (butterfly/condor), which are event-driven and WANT to fire the
            # instant a regime flips. A loss-limit request still forces its own
            # off-schedule reassessment tag for the logs.
            loss_reassess = get_risk_manager().consume_reassess_request()
            trigger = "loss_limit" if loss_reassess else "scheduled"
            regime = run_regime_classification(ctx, trigger, state)

            if regime is None:
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            # ── Compute GEX every tick (used by all strategies + position mgr)
            try:
                from data.options_chain import get_chain_fetcher
                from data.gex_data import compute_gex as _compute_gex
                _gex_chain = get_chain_fetcher().fetch_chain()
                if _gex_chain:
                    ctx["gex"]   = _compute_gex(_gex_chain, ctx["price"])
                    ctx["chain"] = _gex_chain
                    # v4.2: archive the FULL chain on a wall-clock cadence.
                    # LOG-ONLY and NO extra market-data load — it serializes the
                    # object we already hold. Hooked here rather than in
                    # attempt_new_entry because this block runs EVERY tick
                    # regardless of entry eligibility, so snapshots continue
                    # while halted, while a position is open, and outside the
                    # condor window. Option chains are unrecoverable after
                    # 16:00; nothing else in the system archives them.
                    # ── PF.2 (2026-08-11) — PITCHFORK OBSERVATION, WEIGHT 0 ──
                    # Builds the daily + hourly forks from THIS BOX's own frames
                    # and journals where price sits in each channel. Gates
                    # nothing, is read by no strategy, and never raises.
                    # Hooked HERE for the same reason chain_snapshot is: the
                    # entry path is skipped when entries are blocked, so a hook
                    # there would silently lose observations during halts, while
                    # a position is open, and outside every strategy's window.
                    # The point is the CONTINUATION JOIN — when continuation
                    # fires, where was price relative to the rail? That is one
                    # observation per trade at 13-76 trades a session, unlike
                    # the touch study which needed n~600 and was unreachable.
                    try:
                        from analysis.pitchfork_observer import snapshot as _pf_snap
                        _pf_snap(ctx, INSTRUMENT,
                                 journal=(_sigj.journal if _sigj is not None
                                          else None))
                    except Exception:
                        pass
                    try:
                        from analysis.chain_snapshot import snapshot as _chain_snap
                        _r = ctx.get("regime")
                        _chain_snap(
                            _gex_chain,
                            underlying_price=ctx.get("price"),
                            regime=getattr(_r, "primary_regime", None)
                                   if _r is not None else None,
                        )
                    except Exception:
                        pass          # never let archival touch the loop
            except Exception as _gex_err:
                logger.warning(f"GEX tick fetch failed: {_gex_err}")

            # ── v4.3: TRADE READINESS (log-only) — every tick, like the chain
            # snapshot: it must keep observing while halted, while a position
            # is open, and outside any entry window, because the record of the
            # confluence RISING AND FALLING is the point. Gates nothing; the
            # engine swallows its own failures; the loop cannot be touched.
            if _readiness is not None:
                _readiness.assess_all(ctx, regime)

            # ── Manage open position ──────────────────────────────────────
            if pos_mgr.has_open_position():
                # ── Broken-wing roll: FIRST REFUSAL ───────────────────────
                # The roll must run BEFORE manage_open_position. The per-leg
                # 25% condor stop lives in manage_open_position; if it runs
                # first it closes the tested leg, and the roll needs BOTH
                # verticals open — so the stop used to guillotine the tested
                # side before the roll could ever act. check_and_execute_roll
                # self-gates: it executes ONLY when a risk-free roll exists,
                # so when no roll is viable the stop still fires exactly as
                # before (same 25% downside, no new risk). When a roll IS
                # viable, it converts the untested side and the tested side
                # goes risk-free instead of stopping at a loss.
                try:
                    from strategy.condor_roll import check_and_execute_roll
                    check_and_execute_roll(pos_mgr, ctx.get("chain"), ctx["price"], state)
                except Exception as _roll_err:
                    logger.warning(f"Roll check failed: {_roll_err}")

                # v5.2 — the regime label is WITHHELD from the exit path while
                # the book is stale, so no regime-driven exit can fire on a
                # classification the engine cannot currently confirm. None is
                # the existing "do not judge on regime" signal every one of
                # those three branches already honours; price-based exits are
                # untouched and keep protecting the position.
                _rgm_stale = (_l2_integ is not None
                              and getattr(_l2_integ, "stale", False))
                pos_mgr.manage_open_position(
                    chain=ctx.get("chain"),
                    df_1m=ctx.get("df_1m"),
                    regime=(None if _rgm_stale
                            else (regime.primary_regime if regime else None)),
                    df_5m=ctx.get("df_5m"),   # v3.8: 5m FVG trail anchor
                    vol_state=ctx.get("vol"),
                    trend=ctx.get("trend"),   # continuation exhaustion exit
                )
                # ── A2.2 — the orphan announces itself HERE, once ─────────
                # This branch is the only code that runs while a condor leg is
                # open, so it is the only place the "plan did not survive the
                # restart" warning can actually fire. report_orphaned_plan
                # keeps its own once-latch.
                try:
                    _iron_condor_strategy.report_orphaned_plan(
                        pos_mgr.open_condor_leg_count())
                except Exception:                              # noqa: BLE001
                    pass

                # ── Condor Leg 2 check ────────────────────────────────────
                # If Leg 1 is the open position and Leg 2 is still queued,
                # check_leg_triggers() must run here — not in attempt_new_entry()
                # which is blocked by has_open_position(). This is the only
                # path that allows Leg 2 to fire while Leg 1 is already live.
                # Once both legs are filled the condor is a complete 4-leg
                # position and no further leg firing occurs.
                if (_iron_condor_strategy.has_active_plan and
                        _iron_condor_strategy.plan is not None and
                        _iron_condor_strategy.plan.state == "LEG1_FILLED"):
                    leg_signal = _safe_strategy("CondorLeg", lambda: _iron_condor_strategy.check_leg_triggers(
                        regime        = regime,
                        chain         = ctx.get("chain"),
                        current_price = ctx["price"]
                    ))
                    if leg_signal is not None:
                        _execute_condor_leg(leg_signal, state, ctx)
            else:
                attempt_new_entry(ctx, regime, state)

            # ── Periodic heartbeat log ────────────────────────────────────
            if state.tick_count % 20 == 0:
                summary = get_trade_logger().today_summary()
                logger.info(
                    f"Tick #{state.tick_count} | "
                    f"{fmt_et_short()} | "
                    f"price=${ctx['price']:,.2f} | "
                    f"regime={regime.primary_regime} ({regime.conviction:.0%}) | "
                    f"orb={ctx['orb'].state} | "
                    f"session: {summary.get('wins',0)}W/"
                    f"{summary.get('losses',0)}L "
                    f"pnl=${summary.get('total_pnl',0):+.2f} | "
                    f"{get_risk_manager().status_report()}"
                )

            state.errors_this_hour = max(0, state.errors_this_hour - 1)

        except Exception as e:
            state.errors_this_hour += 1
            logger.error(f"Loop error (#{state.errors_this_hour}): {e}")
            logger.error(traceback.format_exc())
            if state.errors_this_hour > 30:
                logger.critical("Too many errors — shutting down")
                sys.exit(1)

        elapsed = time.time() - tick_start
        time.sleep(max(0, POLL_INTERVAL_SECONDS - elapsed))


# Below this many seconds of system uptime, a startup is treated as a fresh
# instance boot (EC2 stop/start or reboot); above it, a service-only restart
# (systemctl restart / crash / deploy while the box was already up).
BOOT_UPTIME_THRESHOLD_S = 180


def _boot_kind() -> str:
    """Classify why the bot just started, for restart self-identification.
    Fresh instance boot vs service-only restart, read from /proc/uptime.
    Best-effort: returns a generic 'restart' if uptime can't be read."""
    try:
        with open("/proc/uptime") as fh:
            uptime_s = float(fh.read().split()[0])
        return "fresh boot" if uptime_s < BOOT_UPTIME_THRESHOLD_S else "service restart"
    except Exception:
        return "restart"


def _describe_position(record: dict) -> str:
    """One-line, self-identifying description of an open row (used by both the
    recovery alert and the stale-orphan sweep alert)."""
    side = str(record.get("option_side", "")).upper()
    if bool(record.get("is_butterfly", 0)):
        return (
            f"BUTTERFLY {side} "
            f"{record.get('lower_strike',0):.0f}/"
            f"{record.get('center_strike',0):.0f}/"
            f"{record.get('upper_strike',0):.0f}"
        )
    if record.get("is_condor_leg") or record.get("strategy") == "IronCondorStrategy":
        return (f"CONDOR {side} "
                f"{record.get('short_strike',0):.0f}/{record.get('long_strike',0):.0f}")
    return f"{side} {record.get('strike',0):.0f}"


def _intraday_reconcile_slot(now):
    """Intraday reconcile slot key, or None outside the window. v3.6: interval
    slots every BROKER_RECONCILE_INTERVAL_MIN minutes (default 10, was a
    hardcoded 30) from 09:30 to 15:45, PLUS dedicated wind-down sweeps at
    15:45 (as the flatten starts — clears phantoms the flatten would otherwise
    fight), 15:50 (mid-window), and 15:57 (the post-flatten truth pass; the
    reconcile block runs before the hard-close branch each tick, and the loop
    goes dormant at 16:00, so this is the last guaranteed look of the day)."""
    if now.weekday() >= 5:
        return None
    t = now.time()
    if t < dtime(9, 30) or t >= dtime(16, 0):
        return None
    if t >= dtime(15, 45):
        if t >= dtime(15, 57):
            hh, mm = 15, 57
        elif t >= dtime(15, 50):
            hh, mm = 15, 50
        else:
            hh, mm = 15, 45
        return f"{now:%Y-%m-%d} {hh:02d}:{mm:02d}"
    interval = max(1, int(BROKER_RECONCILE_INTERVAL_MIN))
    mins_since_open = (now.hour - 9) * 60 + now.minute - 30
    slot_min = (mins_since_open // interval) * interval
    hh, mm = 9 + (30 + slot_min) // 60, (30 + slot_min) % 60
    return f"{now:%Y-%m-%d} {hh:02d}:{mm:02d}"


def _fetch_close_order_history(records: list) -> list:
    """One order-history read per reconcile pass (never per phantom), covering
    the earliest entry date among the phantom candidates. Fail-safe: any error
    returns [] and the caller books the flagged $0.00 fallback as before."""
    try:
        from data.tasty_client import get_session, get_account
        from datetime import date as _date
        start = _date.today()
        for rec in records:
            et = str(rec.get("entry_time", "") or "")[:10]
            try:
                y, m, d = int(et[0:4]), int(et[5:7]), int(et[8:10])
                start = min(start, _date(y, m, d))
            except Exception:
                pass
        session = get_session()
        account = get_account()
        return account.get_order_history(session, page_offset=None,
                                         start_date=start) or []
    except Exception as e:
        logger.error(f"Phantom P&L recovery: order-history read failed ({e}) — "
                     f"phantoms will book flagged $0.00 this pass.")
        return []


def _close_phantom_with_recovery(trade_logger, rec, orders, reason: str) -> str:
    """Close one phantom row, booking the REAL fill recovered from broker order
    history when a matching closing order exists (manual close), else the
    flagged $0.00 (expiry/assignment leave no closing order). Returns a short
    description for the alert."""
    from execution.broker_reconcile import match_closing_fills, phantom_pnl
    rid = rec.get("trade_id", "")
    match = match_closing_fills(rec, orders) if orders else None
    if match is not None:
        qty, net = match
        pnl = phantom_pnl(rec, net, closed_qty=min(qty, float(rec.get("contracts", 0) or 0)))
        full = qty >= float(rec.get("contracts", 0) or 0)
        trade_logger.close_phantom(
            rid,
            reason     = f"{reason}_pnl_recovered" + ("" if full else "_partial"),
            exit_price = net,
            pnl_usd    = pnl,
        )
        return f"{rid[:8]} pnl=${pnl:+.2f}@{net}" + ("" if full else f" ({qty:g} of {rec.get('contracts')})")
    trade_logger.close_phantom(rid, reason=reason)
    return f"{rid[:8]} pnl=UNKNOWN($0 flagged)"


def _intraday_reconcile(state: BotState, instrument: str):
    """
    LIVE intraday broker-truth check (gated by BROKER_RECONCILE_ENABLED). Detects
    positions the broker closed out from under us DURING the session — especially
    a SHORT leg auto-closed while the long remains — and reacts before the 15:45
    flatten. It only inspects rows WE already manage (it does not adopt brand-new
    broker positions intraday, so a manual trade you place is left alone).

    FAIL-SAFE: a failed or empty broker read changes nothing.
    """
    trade_logger = get_trade_logger()
    try:
        from data.tasty_client import get_open_option_positions
        broker = get_open_option_positions()
    except Exception as e:
        logger.error(f"Intraday reconcile: broker read failed ({e}) — no action.")
        return

    open_rows = trade_logger.get_open_trades_live()
    if not open_rows:
        return
    if not broker:
        logger.warning(
            "Intraday reconcile: broker empty while DB shows open rows — "
            "inconclusive, no action (fail-safe)."
        )
        get_alert_manager().send_reconcile_unavailable_alert(instrument, "empty read (intraday)")
        return

    from execution.broker_reconcile import leg_roles, _adopt_record
    broker_by_sym = {p["symbol"]: p for p in broker if p.get("symbol")}
    broker_syms   = set(broker_by_sym)

    changed  = False
    phantoms = []
    # v3.6: find ALL whole-position phantoms first, then ONE order-history read
    # recovers their real fills (manual closes) — see _close_phantom_with_recovery.
    gone = [rec for rec in open_rows
            if (leg_roles(rec)[0] | leg_roles(rec)[1])
            and not ((leg_roles(rec)[0] | leg_roles(rec)[1]) & broker_syms)]
    history = _fetch_close_order_history(gone) if gone else []
    for rec in open_rows:
        rid = rec.get("trade_id", "")
        short_syms, long_syms = leg_roles(rec)
        all_syms = short_syms | long_syms
        if not all_syms:
            continue

        # whole position gone at the broker -> phantom (real fill recovered
        # from order history when a matching manual close exists)
        if not (all_syms & broker_syms):
            desc = _close_phantom_with_recovery(trade_logger, rec, history,
                                                reason="phantom_intraday")
            phantoms.append(desc)
            changed = True
            continue

        # SHORT gone while a LONG remains -> broker closed our protection
        short_present = bool(short_syms & broker_syms)
        long_present  = bool(long_syms & broker_syms)
        if short_syms and not short_present and long_present:
            trade_logger.close_phantom(rid, reason="short_closed_by_broker")
            surviving = []
            for sym in (long_syms & broker_syms):
                adopted = _adopt_record(broker_by_sym[sym])
                if adopted:
                    trade_logger.log_entry(adopted)
                    surviving.append(_describe_position(adopted))
            changed = True
            get_alert_manager().send_short_leg_closed_alert(
                instrument  = instrument,
                closed_desc = _describe_position(rec),
                surviving   = ", ".join(surviving) or "(long leg)",
            )
            logger.error(
                f"SHORT LEG CLOSED BY BROKER [{instrument}] {_describe_position(rec)} "
                f"-> adopted surviving long(s): {surviving}"
            )

    if phantoms:
        get_alert_manager().send_phantom_closed_alert(instrument, phantoms)
    if changed:
        # re-sync in-memory management to the corrected DB truth
        get_position_manager(state.paper_trading).set_open_positions(
            trade_logger.get_open_trades_live()
        )


def _reconcile_with_broker(state: BotState, live_rows: list,
                           restart_type: str, instrument: str) -> list:
    """
    LIVE-only: reconcile the DB's live rows against the broker, which is the
    source of truth for whether a position EXISTS. Returns the final list of
    records to manage (kept DB rows + adopted broker positions). Journals adopts,
    closes phantoms, and alerts.

    FAIL-SAFE: on ANY broker read failure — or an empty read while the DB still
    shows live rows — return the DB rows unchanged and close NOTHING. A bad or
    empty read must never be interpreted as "the broker is flat", which would
    close real positions.
    """
    trade_logger = get_trade_logger()
    try:
        from data.tasty_client import get_open_option_positions
        broker = get_open_option_positions()
    except Exception as e:
        logger.error(f"Broker reconcile unavailable ({e}) — DB-only recovery, closed nothing.")
        get_alert_manager().send_reconcile_unavailable_alert(instrument, "read failed")
        return live_rows

    if not broker:
        if live_rows:
            logger.warning(
                "Broker returned NO option positions while the DB shows live rows — "
                "inconclusive; DB-only recovery, closed nothing."
            )
            get_alert_manager().send_reconcile_unavailable_alert(instrument, "empty read")
        return live_rows

    from execution.broker_reconcile import build_plan
    plan = build_plan(broker, live_rows)

    # Phantoms: open in our DB but absent at the broker -> close (broker wins).
    # v3.6: recover the REAL fill from order history (covering back to each
    # phantom's entry date — a manual close from a prior day is still found).
    if plan.close_phantom:
        by_id   = {r.get("trade_id", ""): r for r in live_rows}
        gone    = [by_id[t] for t in plan.close_phantom if t in by_id]
        history = _fetch_close_order_history(gone)
        descs   = []
        for tid in plan.close_phantom:
            rec = by_id.get(tid)
            if rec is None:
                trade_logger.close_phantom(tid)
                descs.append(f"{tid[:8]} pnl=UNKNOWN($0 flagged)")
                continue
            descs.append(_close_phantom_with_recovery(
                trade_logger, rec, history, reason="phantom_closed_at_broker"))
        get_alert_manager().send_phantom_closed_alert(instrument, descs)

    # Adopts: journal into our system of record + alert (loud for a lone short).
    anomaly_ids = set(plan.anomalies)
    for rec in plan.adopt:
        trade_logger.log_entry(rec)
        get_alert_manager().send_adopted_alert(
            instrument    = instrument,
            position_desc = _describe_position(rec),
            contracts     = int(rec.get("contracts", 0) or 0),
            entry_premium = float(rec.get("entry_premium", 0) or 0),
            is_short      = bool(rec.get("is_short_position")),
            anomaly       = rec.get("trade_id") in anomaly_ids,
            restart_type  = restart_type,
        )
        logger.warning(
            f"ADOPTED [{instrument}] {_describe_position(rec)} "
            f"({'short' if rec.get('is_short_position') else 'long'}) "
            f"id={rec.get('trade_id','')[:8]}"
        )

    return list(plan.keep) + list(plan.adopt)


def _recover_open_position(state: BotState, restart_type: str = ""):
    """
    Called immediately on every start, restart, and reboot, before the main loop.

    Step 1 — reconcile only TRULY EXPIRED orphans. A position's liveness is its
    EXPIRY, not its entry date: this bot also trades weeklies (nearest expiry can
    be days out), so a row entered on a prior session may still be a live
    contract today. Only rows whose expiry has actually passed are dead; those
    are closed in the DB up front so nothing manages a ghost.

    Step 2 — resume EVERY still-live open row (0DTE or weekly). If a position
    survived overnight (a weekly held, or one that leaked past the 15:45 flatten
    / a hard kill), it is identified and managed immediately, and flagged as
    CARRIED so it can't be missed.
    """
    pos_mgr = get_position_manager(state.paper_trading)
    trade_logger = get_trade_logger()
    instrument = os.environ.get("OT_INSTRUMENT", INSTRUMENT)

    # ── Step 1: sweep only genuinely EXPIRED orphans ─────────────────────────
    expired = trade_logger.close_expired_open_trades()
    if expired:
        descs = [_describe_position(r) for r in expired]
        logger.warning(
            f"Startup: auto-closed {len(expired)} EXPIRED orphan(s) [{instrument}]: "
            f"{', '.join(descs)}"
        )
        get_alert_manager().send_orphan_cleared_alert(
            instrument=instrument, descs=descs, restart_type=restart_type
        )

    # ── Step 2: resume every still-live (unexpired) position ─────────────────
    live = trade_logger.get_open_trades_live()

    # LIVE ONLY, and only when explicitly enabled: the broker is the source of
    # truth for what's actually open. (Paper has no broker to query; and even on
    # live this stays OFF until OT_BROKER_RECONCILE=True, so it can't fire before
    # get_open_option_positions() has been verified on a live box.)
    if not state.paper_trading and BROKER_RECONCILE_ENABLED:
        live = _reconcile_with_broker(state, live, restart_type, instrument)

    if not live:
        logger.info("Startup position check: no live positions to resume.")
        return

    pos_mgr.set_open_positions(live)

    # The recovery/carried alert covers DB-PLANNED rows only; adopted positions
    # already got their own adopted alerts inside the reconcile.
    db_planned = [r for r in live if r.get("strategy") != "ADOPTED"]
    if not db_planned:
        logger.info("Recovery: only adopted positions to manage (already alerted).")
        return

    # A position whose entry ET date is before today survived a session boundary.
    today_et = now_et().strftime("%Y-%m-%d")
    carried  = any(
        trade_logger._et_date(r.get("entry_time", "")) not in ("", today_et)
        for r in db_planned
    )

    descs         = [_describe_position(r) for r in db_planned]
    position_desc = " + ".join(descs)
    contracts     = sum(int(r.get("contracts", 0) or 0) for r in db_planned)
    total_cost    = sum(float(r.get("total_cost", 0) or 0) for r in db_planned)
    lead          = db_planned[0]
    entry_prem    = float(lead.get("entry_premium", 0) or 0)
    strategy      = lead.get("strategy", "")
    trade_ids     = ",".join(r.get("trade_id", "")[:8] for r in db_planned)

    logger.warning(
        f"⚠️  {'CARRIED' if carried else 'LIVE'} POSITION RECOVERED ON STARTUP "
        f"[{instrument}]: {position_desc} x{contracts} "
        f"entry=${entry_prem:.2f} total=${total_cost:.2f} "
        f"strategy={strategy} id={trade_ids} ({restart_type or 'restart'})"
    )
    get_alert_manager().send_recovery_alert(
        instrument   = instrument,
        position_desc = position_desc,
        contracts    = contracts,
        entry_premium = entry_prem,
        total_cost   = total_cost,
        strategy     = strategy,
        restart_type = restart_type,
        carried      = carried,
    )
    logger.info(
        f"Position recovery complete — main loop will manage "
        f"{position_desc} from first tick."
    )



def _fetch_orb_range(instrument: str = "") -> bool:
    """Fetch and write orb_range.json via the standalone get_orb_range.py.

    get_orb_range.py is the single source of truth. It ALWAYS writes the last
    valid range, tagged with one of three states, and returns it via exit code:
        0 = ESTABLISHED (today's, closed) -> return True
        2 = IN_PROGRESS (opening candle forming) -> return False (retry)
        3 = EXPIRED (carrying last RTH range)    -> return False (retry)
        1 = hard error                            -> return False

    Returns True ONLY when today's range is ESTABLISHED, so callers keep polling
    across IN_PROGRESS/EXPIRED until today's candle closes — while status.py and
    the engine always have the last valid range to read in the meantime.
    """
    try:
        import subprocess as _sp
        _symbol = instrument or os.environ.get("OT_INSTRUMENT", INSTRUMENT)
        # main.py lives in the install root; the script is a sibling package.
        _install_dir = os.path.dirname(os.path.abspath(__file__))
        _orb_script = os.path.join(_install_dir, "analysis", "get_orb_range.py")
        _result = _sp.run(
            [sys.executable, _orb_script, _symbol],
            capture_output=True, text=True, timeout=30
        )
        if _result.returncode == 0:
            _line = _result.stdout.splitlines()[0] if _result.stdout.strip() else ""
            logger.info(f"ORB range: {_line}")
            return True
        if _result.returncode == 2:
            logger.debug("ORB range: IN_PROGRESS — today's opening candle forming")
        elif _result.returncode == 3:
            logger.debug("ORB range: EXPIRED — carrying last RTH range, awaiting today's")
        else:
            logger.warning(f"ORB range fetch failed: {_result.stderr.strip()}")
        return False
    except Exception as e:
        logger.warning(f"ORB range fetch skipped: {e}")
        return False


def main():
    service_mode = "--service" in sys.argv

    if service_mode:
        session_config = SessionConfig(
            paper_trading      = PAPER_TRADING,
            instrument         = INSTRUMENT,
            risk_per_trade_usd = RISK_PER_TRADE_USD,
            notes              = "systemd auto-start"
        )
        logger.info(
            f"Service mode: {'PAPER' if PAPER_TRADING else 'LIVE'} | "
            f"{INSTRUMENT} | "
            f"risk=${RISK_PER_TRADE_USD:.0f}/trade | "
            f"daily_loss_cap=${DAILY_LOSS_LIMIT_USD:.0f} net"
        )
    else:
        session_config = _interactive_startup()

    # Initialize TastyTrade client
    # TastyTrade session initializes lazily on first use via get_session()

    # Initialize risk manager with session params
    risk_mgr = init_risk_manager(
        risk_per_trade = session_config.risk_per_trade_usd,
        paper_trading  = session_config.paper_trading
    )

    state = BotState()
    state.paper_trading = session_config.paper_trading

    # L2.5: warm-start the conviction integrator from its last snapshot so a
    # mid-session restart doesn't reset the book to zero (the NVDA-restart
    # lesson). If the snapshot is stale/absent, load() returns False and the
    # book stays cold — the first few ticks re-warm it, and stale=True keeps it
    # from driving the gate until warmed (see run_regime_classification).
    if _REGIME_ENGINE == "l2" and _L2_OK:      # v4.7 — value is .lower()ed
        try:
            ok = _l2_integ.load(_L2_STATE_PATH, now_utc().timestamp())
            logger.info("L2.5 integrator book %s (engine=%s)",
                        "reloaded from snapshot" if ok else "cold-start",
                        _REGIME_ENGINE)
        except Exception as e:
            logger.warning("L2.5 book load failed (%s) — cold-start", e)

    # Pre-fetch macro data
    logger.info("Fetching macro data...")
    get_macro_manager().get(force=True)

    # Classify this start (fresh instance boot vs service restart) so every
    # alert below can self-identify what kind of restart just happened.
    restart_type = _boot_kind()

    get_alert_manager().send_startup_alert(
        paper      = session_config.paper_trading,
        instrument = session_config.instrument,
        risk_usd   = session_config.risk_per_trade_usd,
        restart_type = restart_type,
    )

    # ── Graceful shutdown alert on SIGTERM/SIGINT ────────────────────────────
    # systemctl stop/restart sends SIGTERM. Without this handler the bot
    # just dies silently with no Telegram notification.
    def _handle_shutdown(signum, frame):
        reason = "systemctl stop/restart" if signum == signal.SIGTERM else "manual interrupt"
        logger.info(f"Shutdown signal received ({reason}) — sending alert and exiting")
        try:
            get_alert_manager().send_shutdown_alert(
                instrument = session_config.instrument,
                reason     = reason
            )
        except Exception as e:
            logger.error(f"Failed to send shutdown alert: {e}")
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT,  _handle_shutdown)

    # ── CRITICAL: Recover any open position immediately ─────────────────────
    # Runs before the main loop on every start, restart, or reboot.
    # If the bot went down with money on the line, we resume managing
    # that position within seconds — not waiting for the first loop cycle.
    _recover_open_position(state, restart_type)

    # ── Fetch ORB range on start/restart ─────────────────────────────────────
    # Runs unconditionally: get_orb_range.py always writes the last valid range
    # tagged ESTABLISHED / IN_PROGRESS / EXPIRED, so status.py and the ORB engine
    # always have a range to read (e.g. Friday's EXPIRED range on a Monday
    # pre-open restart). It is safe pre-open because the engine only ARMS on an
    # ESTABLISHED/today range. We latch only when today's range is ESTABLISHED;
    # otherwise handle_session_reset() keeps polling from the open.
    state.orb_range_established_today = _fetch_orb_range(
        os.environ.get("OT_INSTRUMENT", INSTRUMENT)
    )

    logger.info(
        f"OptionsBot ready | "
        f"{'PAPER' if state.paper_trading else 'LIVE'} | "
        f"{session_config.instrument} | "
        f"risk=${session_config.risk_per_trade_usd:.0f}/trade | "
        f"poll={POLL_INTERVAL_SECONDS}s"
    )

    main_loop(state)


def _interactive_startup() -> SessionConfig:
    """Interactive startup prompt for manual launch."""
    print("\n" + "="*50)
    print("  options_trader v1.0 — Startup Configuration")
    print("="*50)

    # Instrument
    print("\nInstrument:")
    print("  1. QQQ  (Nasdaq ETF, $1 strikes)")
    print("  2. SPY  (S&P 500 ETF, $1 strikes)")
    print("  3. SPX  (S&P 500 Index, $5 strikes)")
    choice = input("Select [1/2/3, default=1]: ").strip() or "1"
    instrument = {"1": "QQQ", "2": "SPY", "3": "SPX"}.get(choice, "QQQ")

    # Risk per trade
    risk_input = input(f"\nRisk per trade in $ [default=200]: ").strip() or "200"
    try:
        risk_usd = float(risk_input)
    except ValueError:
        risk_usd = 200.0

    # Paper vs live
    mode_input = input("\nTrading mode [P=Paper/L=Live, default=P]: ").strip().upper() or "P"
    paper = mode_input != "L"

    print(f"\n{'─'*50}")
    print(f"  Instrument:    {instrument}")
    print(f"  Risk/trade:    ${risk_usd:.0f}")
    print(f"  Mode:          {'PAPER' if paper else '⚠️  LIVE'}")
    print(f"  Daily cap:     ${DAILY_LOSS_LIMIT_USD:.0f} NET loss → halt new entries")
    print(f"{'─'*50}")

    if not paper:
        confirm = input("\n⚠️  LIVE TRADING — type YES to confirm: ").strip()
        if confirm != "YES":
            print("Defaulting to paper trading.")
            paper = True

    from utils.time_utils import fmt_et_full
    return SessionConfig(
        paper_trading      = paper,
        instrument         = instrument,
        risk_per_trade_usd = risk_usd,
        confirmed_at       = fmt_et_full()
    )


if __name__ == "__main__":
    main()