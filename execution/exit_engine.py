"""
execution/exit_engine.py — v4.22  2026-08-15  AUDIT F7: the BREAKOUT_VOLATILE exemption was scoped to
        `_breakout` records only, so a standalone/handoff continuation that
        ACCELERATED into a breakout IN ITS OWN DIRECTION was closed as a
        regime_flip while a breakout record survived the identical tape.
        Now ANY continuation survives, gated on the TREND VOTE agreeing -
        which is what v4.19's own comment already said should decide, and
        which the label cannot supply because BREAKOUT_VOLATILE has no
        direction. A long no longer survives a violent move DOWN.
v4.21 — Strategy-aware exit logic for all options positions.
v4.21 — 2026-08-14 — 🔴 AUDIT F1+F2+F4: THE v4.20 FIX NEVER BOUND, AND THE
        DISPATCH NEVER ROUTED. Two defects of the exact species v4.20 fixed,
        one hop away each, found by the adversarial audit and REPRODUCED AT
        RUNTIME (every failure below executed against 3d9e82e, not inferred):
        (F1) `is_trend_participation` was called at the top of
        `_evaluate_condor_leg` and NEVER IMPORTED into this module — NameError
        on every condor-leg tick and every legacy TC.6 row. The exception
        escapes _manage_one into the tick loop's error counter: 30 errors at
        15s ticks = sys.exit(1) about 7.5 min after any condor leg opens, then
        a systemd crash-loop until the 15:45 branch (which sits ABOVE the
        call) flattens it. The chain test asserted the STRING existed in this
        file — a mention, not a binding (WORKING_AGREEMENT section 20, at the
        import level). Import added, module level.
        (F2) `_execute_condor_leg` now writes strategy="TrendCreditSpread"
        (main v6.8) but evaluate() only routed "IronCondorStrategy" to the
        condor evaluator — every NEW TC.6 record fell to `_evaluate_sweep`,
        the DEBIT evaluator: KeyError 'trail_activation' on the first tick of
        a fresh record; after the crash-restart, target_premium=$0.05 (the
        nickel) read as a debit TP satisfied from tick one, so the position
        lived in the ORB post-target trail with SIGN-INVERTED P&L labels and
        lost the VERTICAL_HOLD_TO_ET exemption; TypeError once value decayed
        below the nickel. The dispatch now routes any record structure.py
        recognises as a credit vertical — both strategy names, legacy rows,
        and the rolled broken wing — to `_evaluate_condor_leg`.
        (F4) the ratchet high-water lived ONLY in self._condor_ratchet, so
        every bake reset an earned breakeven/+20% lock to the base -25% and
        re-opened the round-trip v4.1 exists to close. The earned level now
        rides the SAME persistence the directional trails use: emitted via
        decision.new_trail_stop (position_manager writes the trail_stop
        column) on the STANDALONE branch only — v4.17's formed branch
        deliberately neither applies nor updates it — and re-seeded from the
        column on restart. Only a value below base_stop can be a real condor
        ratchet; anything else is stale/foreign and ignored.
        Ships with tests/test_exit_dispatch_runtime.py — the first suite on
        this path that EXECUTES evaluate() with real record shapes (fresh AND
        rehydrated) instead of grepping source. Verified to fail against
        3d9e82e before this fix.
v4.20 — 2026-08-14 — 🔴 THE TC.6 BRANCH DIED ON RESTART. `is_trend_credit` IS
        NOT A COLUMN in the trades table — it lives only in the in-memory
        record. `get_open_trades_live()` does SELECT *, so **any restart
        rehydrated an open trend-participation position WITHOUT the flag**, this
        branch stopped firing, and the leg dropped into the condor ladder with
        the ratchet and the 25% premium stop. Same bug as the 08-14 identity fix,
        one level down: fixed for the process that OPENED the trade, still broken
        for any process that INHERITS it — and the hop that dropped it is a
        systemctl restart, which happens on every bake.
        Now DERIVED from `strategy` / `setup_type`, which are REAL COLUMNS and
        already round-trip. No new column, no migration — a column would fix
        tomorrow and not today, because rows opened before it would still
        rehydrate as None and read as False. The old flag is still honoured when
        present; only its ABSENCE stopped meaning "not a trend credit".
        See strategy/structure.py.
v4.19 — 2026-08-14 — 🔴 CNT.1 SHIPPED HALF A FEATURE AND THIS IS THE OTHER HALF.
        The entry branch (continuation_strategy, CNT.1, 2026-08-07) lets
        continuation OPEN on BREAKOUT_VOLATILE, taking direction from the trend
        vote and gating on ADX. `still_trending` here only ever accepted
        TRENDING_BULL / TRENDING_BEAR. So every `trend_continuation_breakout`
        trade was **BORN ALREADY FAILING ITS OWN EXIT TEST** — opened on tick N,
        closed on tick N+1 by reading the SAME UNCHANGED LABEL. THE LABEL NEVER
        FLIPPED, and `regime_flip` was a lie in the exit reason.
        Measured live 2026-08-14: 15-second holds, exactly one tick, repeating
        while the setup held. P&L symmetric noise — one tick of random walk minus
        the spread. **This has been true for every breakout continuation since
        2026-08-07.** Sits BEFORE bos_exit, so nothing else got a look.
v4.18 — 2026-08-14 — 🔴 LIVE FIX: THE TC.6 BRANCH HAD NO TERMINAL RETURN.
        When NEITHER breach NOR nickel fired it fell straight through to the
        ratchet and the 25% condor stop. `_execute_condor_leg` writes
        stop_premium = credit x 1.25 at entry, so a $0.06 credit put the stop at
        $0.07 — ONE CENT of widening closed the trade. Every TC.6 leg on the
        fleet stopped out within seconds of opening on 2026-08-14.
        THE MEASURED EV WAS HELD TO EXPIRY, UNMANAGED. A premium stop is a
        different trade, which is the entire reason the branch exists.
        ⚠️ THE TEST THAT MISSED IT asserted the branch CONTAINED two
        `return decision` statements. It did. Neither covered the path where
        neither condition fires — the path that was broken. **Counting returns
        proves nothing about the path that has none.** Now asserted on the
        branch's LAST STATEMENT via AST, and verified to FAIL against the
        shipped version.
v4.17 — 2026-08-13 — THE RATCHET WAS CLOSING UNTESTED CONDOR LEGS. Operator:
        "the ratchet is inappropriate for this trade if the condor is fully
        formed. It should only be in effect if there's one side open" and
        "don't close a leg if it hasn't been tested - that's what the roll is
        for."
        MECHANISM: the base -25% stop only ever fires on the TESTED side,
        because a credit spread's value RISES as price approaches your short.
        The RATCHET does the opposite — it tightens the UNTESTED side's stop to
        breakeven at +20% and +20%-locked at +40% PRECISELY BECAUSE that side is
        winning. On the reversal the tested leg stops at -25% and the untested
        leg hits its ratcheted stop too. **A leg price never went near, closed
        by a stop that exists only because it was profitable.** That is the
        double-stop — 5 of 14 condor symbol-days had BOTH sides stopped — and it
        fires BEFORE the roll can be used, because the roll needs a tested side.
        FIX: while `_condor_sibling_open()` is true, the base floor is the ONLY
        stop; no tier, and the stored high-water is neither applied nor updated,
        so a leg returning to standalone resumes from a level it genuinely
        earned. Same interlock the take-profit already used, and it FAILS CLOSED
        (True on error) — treating a leg as part of a structure is the safe
        error.
        NOT CHANGED, deliberately: the adverse-regime-flip exit. It is
        direction-aware — a call spread exits only on TRENDING_BULL, which IS
        price rising toward that short strike — so it already fires only on the
        threatened side and is a tested-side exit.
        PRESERVED: `condor_stop` went 0% -> 19% win after the ratchet shipped,
        but that evidence came mostly from STANDALONES (18 of 46 legs never got
        a second side). Scoping keeps the gain where it was measured.
        ⚠️ ACCEPTED COST: an untested leg that runs to +40% and reverses now
        gives it back rather than locking +20%.
v4.16 — 2026-08-12 — VEL.1: THE VELOCITY STALL, ladder step 2c. THE THIRD
        QUESTION, and until now nobody asked it. `orb_structure_stop` asks "did
        the thesis break?"; `_theta_bleed` asks "is my GAIN about to evaporate?"
        — its gate 1 is a gain floor, so a LOSING position is invisible to it.
        **A losing position that has STOPPED MOVING answers no to both** and
        falls to the -40% percentage floor, which is the ABSENCE of a mechanism
        rather than one. 2026-08-12 QQQ: 50 minutes and -42.2% with the
        underlying sitting BELOW the short entry the entire hold — directionally
        right, bleeding anyway, and nothing watching.
        STATISTIC — and it needs NO TARGET, which is why it generalises to every
        long-premium strategy: bev = |theta| / (|delta| * 1440) is the pts/min
        at which delta gains exactly offset decay; ratio = delivered / bev, and
        1.0 IS THE FLAT LINE.
        MEASURED, 15 sessions / 145 ORB trades against the chain archive
        (tests/velocity_feasibility.py — the FIRST tool to ever read it), among
        trades STILL OPEN at each mark:
              mark   winners p10   losers p50   losers p90
               5m       -21.1        -37.3         91.3   <- NO SEPARATION
              10m         3.9         -6.7         20.5
              15m        18.0          0.3         26.7
              20m        29.8          0.9         18.5   <- barely overlap
        The median surviving LOSER treads water at ~1.0 — exactly breakeven —
        while the bottom decile of WINNERS runs at 30x it.
        ⚠️ ORDER IS DELIBERATE: theta_bleed evaluates FIRST so a trade up 10-20%
        and stalled exits GREEN via that path. INDEPENDENT gates, never a
        combined score — the QQQ failure was two mechanisms each correctly
        saying "not my problem" with nothing aggregating that into "then NOBODY
        is watching."
        ⚠️ GRACE IS FORCED BY DATA: winners p10 at 5 min is -21.1, so the bottom
        decile of eventual WINNERS was moving AWAY. No check before 10 minutes.
        ⚠️ SHIPS OBSERVE-ONLY (OT_VELOCITY_ENFORCE=0). Floors rest on n=22 at the
        20-minute mark and are ORB-derived; other strategies are logged, never
        cut, whatever ENFORCE says.
        ⚠️⚠️ EVALUATION DATE: **FRI 2026-08-14**, and it carries a DELETE
        CRITERION — **zero firings across 08-13 and 08-14 means REMOVE THIS
        CODE.** A mechanism that never triggers is not cautious; it is dead code
        that still has to be read, tested and maintained. Standing rule agreed
        with the operator 2026-08-12 after three observers shipped in two days
        with no dates: an observer ships with an evaluation date and a delete
        criterion, or it does not ship. The cautionary case is the chain archive
        — written 07-23, first read 08-12, twenty days later.
        ⚠️ THE ENTRY-FILTER FORM OF THIS IDEA WAS MEASURED AND REJECTED:
        feasibility ratio at entry ran HIGHER for losers than winners at every
        percentile (losers p50 5.05 vs winners 3.87, n=145) — a wide range gives
        a distant target AND a big required move, so feasibility and difficulty
        are the same axis pointing opposite ways. Recorded so it is not rebuilt.

v4.15 — 2026-08-10 — BOS PROTECTED LEVEL GETS A MINIMUM DISTANCE. The level is
        seeded from the LOW of the first bar closing above entry. On a pullback
        entry that bar is the smallest, earliest part of the resumption, so its
        low sits a hair under entry — the level lands INSIDE the symbol's own
        noise band and the next ordinary wiggle fires it.
        OBSERVED LIVE, not inferred: JPM in $1.26 12:49 -> out **$0.00** 12:50
        -> back in $1.26 the same minute. A null round trip — the exit condition
        was already true at entry. QQQ the same session fragmented ONE move into
        four scratches (+$30/+$45.50/+$35/+$7), same strike, three minutes, each
        exit immediately followed by re-entry because the setup was still valid.
        The re-entry loop is a SYMPTOM: it cannot happen unless the position
        closes, so a cooldown would suppress the symptom and leave the premature
        exit intact.
        Fix: floor the level at BOS_MIN_DIST_ATR * ATR from entry, ATR-scaled so
        it widens on NVDA and tightens on GLD automatically. Applied ONLY on the
        continuation path, which seeds with `underlying_entry`.
        ⚠️ min_dist=0 IS BYTE-IDENTICAL to pre-v4.15, ratchet included — a test
        pins that, because otherwise the kill switch is not a kill switch and
        there is no A/B control.
        ⚠️ `low - min_dist` IS NOT MONOTONE: a widening ATR can produce a new
        candidate BELOW the old level, silently slackening the stop exactly when
        volatility rises. Longs max(), shorts min().
        ⚠️ PRE-EXISTING DEFECT FOUND AND DELIBERATELY NOT PATCHED HERE: the
        generic/ORB caller (~966) seeds the tracker with `entry_prem` — the
        OPTION premium — while BOSTracker compares against df_1m UNDERLYING
        closes. A ~$1.26 premium against ~$352 closes means the first bar always
        beats peak_close, so that path seeds a level on bar one regardless of
        structure. Recorded rather than silently fixed; an ATR distance in
        premium units would be meaningless anyway.
v4.14 — 2026-08-07 — CNT.2 INSURANCE GATE (2c), continuation only. BOS (2b) is
        the thesis invalidator and is deliberately ungated on P&L, but
        `BOSTracker.protected_level` is None until the trade makes a new closing
        high past entry — so BOS is structurally BLIND on a trade that goes
        wrong from the first tick, and that is exactly the population running to
        the floor at −29% with MFE +1% (45 trades, 11 sessions). 2c arms the
        already-stamped `underlying_stop` ONLY while `protected_level is None`
        and disarms the instant BOS has a level, so the handoff is exact and
        needs no time window. Structural, not premium-percent: a tighter premium
        floor was measured to net ~zero because it cuts winners that merely dip.
        Exits tag `insurance_stop` so the rollup scores it apart from
        max_loss_floor and bos_exit. `_bos` construction moved OUT of the df_1m
        guard so 2c cannot reference an unbound name. OT_CONT_INSURANCE=0 to
        disable. The level has never been read by anything that trades — treat
        it as an untested prior.

v4.13 — 2026-08-04 — W.2 follow-on: the v4.12 throttle reused the ALERT set,
        so the census classified a debug-only handler as "pages". Own set now.
v4.12 — 2026-08-04 — W.2: the v4.11 escalation guard was a bare `except: pass`
        inside place_exit_order — a SILENT swallow in the census's tier 1. Now
        DEBUG, once per process. No behaviour change.
v4.11 — 2026-08-04 — EXIT LADDER LATENCY (N.5, log-only). place_exit_order() —
        the ONE seam every close routes through, paper and live — now stamps
        submit and fill instants, counts the passes the close took, flags
        escalation, and records the MARK AT TRIGGER. Written to the trade row
        via trade_logger v3.11 set_exit_latency() on a CONFIRMED close only.
        WHY THE MARK MATTERS MORE THAN THE MILLISECONDS: TC.2 has to choose a
        stop trigger (-40% vs 35% vs 25%) "calibrated against measured ladder
        fill-latency", and latency is not a cost until it is priced. The cost
        is (mark when the exit fired) - (price it actually filled at). Paper
        books the mark, so the two are equal by construction there — that
        equality is the PLUMBING PROOF that the capture is wired, not a result.
        The real distribution only exists in the live week.
        STATE LIVES ON THE RECORD, NOT ON THE ENGINE, because a live close is
        MULTI-TICK: the deadline can expire and the next tick RESUMES the same
        broker order. Keying off the record means submit_ts is the FIRST submit
        of that close attempt and the pass count spans the whole sequence; an
        engine-level counter would reset on restart and undercount exactly the
        slow closes the study is about.
        NOTHING IN THE TRADING PATH READS ANY OF IT. No exit decision, no
        price, no size changes — the capture runs after the FillResult exists.
v4.1 — 2026-07-23 — CONDOR LEG MANAGEMENT v2 (user directive, data-driven).
        (a) RATCHETING STOP: +20% -> breakeven, +40% -> lock +20%, tightens only.
        (b) TIME-GATED TP at 25%, ONLY after CONDOR_ENTRY_CUTOFF_ET and ONLY
            when the opposite side is not open. Backtest, 18 standalone legs:
            TP@25% turned -$242.77 into -$8.43; on 28 condor legs a TP was WORSE
            at every level, confirming a condor leg must never be closed on
            profit — the only reason to close one is the roll.
        (c) Min-hold before TP: a quote-noise filter, not a structure mechanism.
        Nickel close, 15:45 hard close and the direction-aware regime exit are
        UNCHANGED (that regime exit has fired 0 times in 143 legs).
v4.0 — 2026-07-22 — CONTINUATION EXIT REWORK (user directive). Three changes,
        all scoped to _evaluate_continuation — no other strategy touched:
        (a) TRAIL ANCHORS TO 5m FVGs. It was passing df_1m straight into
            _update_fvg_trail, bypassing the _fvg_frame() helper that ORB and
            sweep have used since v3.8. 1m gaps on a trend-continuation runner
            are noise-tight tripwires; 5m gaps are structurally meaningful and
            naturally wider. Now routed through _fvg_frame(df_1m, df_5m), so
            it also inherits the graceful 1m fallback when 5m is thin.
        (b) THETA-BLEED ENABLED. _theta_bleed had exactly ONE call site
            (_evaluate_orb) — continuation had NO theta protection at all, so
            a stalled winner decayed untouched toward the floor. Now called,
            with its existing four gates unchanged: >=THETA_MIN_GAIN_PCT gain,
            below the FVG_TRAIL_ARM_PCT trail ceiling, past the
            THETA_MIN_HOLD_MIN 20-minute blackout, and projected calendar-day
            decay >= the gain. Placed AFTER exhaustion so the smarter signal
            (momentum divergence) gets first refusal in the narrow overlap;
            theta only catches the genuinely STALLED case.
        (c) BACKSTOP 40%% -> 25%% via CONTINUATION_STOP_LOSS_PCT. The floor
            fallback no longer borrows the blanket MAX_LOSS_PCT.
v3.8 — 2026-07-15 — RUNNER REFINEMENTS (all config/env-tunable; see config
        v2.0). Goals: let winners run harder, keep the loss unit deliberate,
        give 0DTE gamma room to breathe.
        (a) FLOOR 25%→40% for directionals: the -25% premium floor front-ran
            the impulsive-origin structure stop on normal gamma retests,
            stopping intact theses on noise. Floor fallbacks now read
            MAX_LOSS_PCT; the hard-stop label carries the record's ACTUAL
            floor pct (old records keep 25%, truthfully). Sizing is
            full-premium based, so at $1000 positions a floored trade now
            costs ~$400 — the daily cap should be set accordingly.
            Butterflies stay at 25% (BUTTERFLY_STOP_LOSS_PCT); condors
            unchanged.
        (b) 5-MINUTE FVG TRAILS (USE_5M_FVG_TRAIL): trails anchor to 5m gaps
            — structurally meaningful, naturally wider. 1m remains
            authoritative for the structure stop and BOS (speed-critical).
            evaluate()/_evaluate_orb/_evaluate_sweep accept df_5m; graceful
            1m fallback when 5m is absent.
        (c) FVG FLOOR CLAMP (FVG_FLOOR_MAX_LOCK_PCT=0.90): an FVG hugging
            price can no longer set a floor tighter than 90% of current —
            both the armed FVG trail and the post-target trail are clamped.
        (d) LEASH UN-INVERTED: post-target no-FVG fallback 0.85→0.75
            (POST_TARGET_TRAIL_LOCK_PCT, now in config) — proven runners no
            longer get a shorter leash than unproven ones.
        (e) SWEEP RUNNER MODE (SWEEP_POST_TARGET_TRAIL, default on): the +100%
            target_hit — the one hard TP among directionals — is replaced by
            the ORB post-target trail; env False restores it for A/B.
        Telemetry companion: trade_logger v3.8 records per-trade MFE/MAE
        (max/min premium seen) so every threshold above is tunable from
        evidence.
v3.5 — 2026-07-15 — LIVE FILL-CONFIRMATION IMPLEMENTED (closes the Fable spec).
        _confirm_and_book_live_exit() is no longer a stub: it submits the close,
        captures the broker order id, polls to a bounded deadline
        (LIVE_FILL_POLL_SECONDS / LIVE_FILL_DEADLINE_SECONDS in config), and
        returns confirmed=True ONLY on a broker-confirmed fill at the broker's
        actual net fill price read back from per-leg fills — never the mark,
        never entry, never $0.00. Unfilled-at-deadline → cancel, resolve the
        cancel/fill race, return confirmed=False (position STAYS OPEN; the
        15:45→16:00 retry loop re-attempts and it pages once per trade/kind).
        PARTIALS: filled portion stashed on the record, remainder resubmitted
        next tick at a fresh mark; books once, at the quantity-weighted net
        price — never a partial as whole. IDEMPOTENT: a working order id is
        stashed on the record and RESUMED on re-entry, so retry ticks can never
        double-submit a close. Also fixed on the way (all live-only):
        (a) condor-leg verticals now close as ONE 2-leg spread order
            (BUY_TO_CLOSE short / SELL_TO_CLOSE long) — they previously routed
            to _close_single_leg, which sold the short symbol (wrong action)
            and orphaned the long leg at the broker;
        (b) spread closes are marketable LIMITs (tastytrade rejects MARKET on
            multi-leg): vertical debit capped at spread width, butterfly credit
            floored at one tick — the old MARKET butterfly close would have
            been rejected every tick;
        (c) SDK signed-price convention verified (v13.x): NewOrder.price is
            negative=debit / positive=credit and price_effect is IGNORED — a
            positive-priced buy-to-close would never fill;
        (d) adopted short single legs BUY_TO_CLOSE instead of selling more.
        PAPER PATH UNTOUCHED. Acceptance tests A–E:
        tests/test_live_fill_confirmation.py. Spec:
        FABLE_SPEC_live_exit_fill_confirmation.md.
v3.4 — 2026-07-15 — FILL-CONFIRMED EXIT CONTRACT. place_exit_order() now returns
        a FillResult (confirmed / fill_price / order_id / partial), not a bare
        bool — the SHARED seam between paper and live so the two can't fight.
        PAPER: simulate the fill at the last-known mark (passed in) and confirm
        it in one pass; if no mark, decline (confirmed=False) rather than invent
        a price. LIVE: routes to _confirm_and_book_live_exit(), which MUST book
        only on a broker-confirmed fill at the ACTUAL fill price — currently a
        fail-loud stub (raises NotImplementedError) so flipping to cash before
        it exists can NEVER book an unconfirmed close at a fabricated $0.00.
        _submit_live_close() retained (submission != fill) for Fable to call.
        See FABLE_SPEC_live_exit_fill_confirmation.md. Fixes the 15:45 hard-close
        batch that logged every leg at +$0.00 (booked at entry premium).
v3.3 — 2026-07-12 — F5 FIX (exit-reason integrity; behaviorally neutral).
        position_manager used to overwrite record['stop_premium'] (+DB) with
        every trail update, so the floor checks here (ORB #1b, sweep #2,
        adopted #2) fired AT THE TRAIL LEVEL and labeled every trail-armed
        exit 'hard_stop_25pct'/'stop_hit'/'adopted_stop_long' — including
        post-target exits at +100%+. Exit LEVEL was always correct (it was
        the trail); the LABEL lied, poisoning exit_reason distributions for
        Phase-3 calibration. Now: stop_premium is immutable (the true entry
        -25% floor), trails persist in the new trail_stop column, and
        _seed_trail_from_record() re-arms the in-memory trail on restart so
        recovery survivability is preserved. Same exit ticks, same exit
        prices — only the labels change to the truth.
v3.2 — 2026-07-12 — DOC SYNC (no logic change). Three docstrings in this file
        contradicted the code beneath them and were actively dangerous: an agent
        or engineer reading them would "correct" working code back into a fixed
        bug.
        (a) `_evaluate_orb`'s docstring still described the PRE-v3.1 stop ("1-min
            candle closes back inside ORB range") — precisely the behaviour v3.1
            replaced. Rewritten to the actual, ordered trigger list, and it now
            states explicitly that the -25% floor and the structure stop are an
            AND, that there is NO BOS on ORB, NO max-hold, and that the 11:00 ET
            cutoff expires the ENGINE and not an open position.
        (b) The v1.1 changelog line describing that same old stop is now marked
            [HISTORICAL — do not restore].
        (c) `_evaluate_butterfly`'s docstring claimed a 25% profit target; the
            live value is BUTTERFLY_TP_PCT = 20%.
        Zero executable lines changed — verified by diff.
v3.1 — 2026-07-11 — ORB STRUCTURE STOP now keys off the IMPULSIVE candle's
        origin, not the range boundary. The old rule (v1.1) exited on a 1-min
        close back inside the ORB range (close < orb_high for a long). That is
        "just entering the range," which by the strategy's definition is NOT an
        invalidation — the trade is allowed to breathe inside the range as long
        as it holds the impulsive (break) candle's origin. The stop now fires
        only on a 1-min CLOSE beyond that origin: below the impulsive candle's
        low for a long, above its high for a short, read from record
        `underlying_stop` (set correctly by orb_engine v3.1). Companion to the
        engine fix; the two ship together. The unconditional -25% premium floor
        (v1.6) is UNCHANGED and still evaluated first every tick — structure
        stop and dollar floor are an AND (either exits), catching thesis-death
        and total-premium-loss independently. Contained to _evaluate_orb.
v3.0 — original release
v1.1 — 2026-06-27 — strategy-aware exit routing:
        ORB:     stop on 1-min close back inside range, trail at 50% TP, no BOS
                 [HISTORICAL — the range-boundary stop was REPLACED in v3.1 by
                  the impulsive-origin stop. Do not restore. See v3.1 above.]
        Sweep:   BOS on 1-min structure, hard stop 25%
        Butterfly: time/premium exits only, no BOS, no trail
v1.2 — 2026-06-30 — ORB no longer hard-exits at 100% TP. Past 100%, the trail
        tightens to track the nearest unfilled 1-minute Fair Value Gap on the
        underlying (in the trade\'s favor), giving the position room to wick
        back and fill the gap without exiting on every dip, while still
        protecting the bulk of gains if the move actually reverses. FVG
        detection is scoped to 1m data only, matching ORB entry/exit logic
        which is always evaluated on the 1-minute timeframe.
v1.3 — 2026-07-06 — long-option THETA PROTECTION + generalized FVG trail:
        (a) theta-bleed exit — a profitable long is closed when projected time
            decay over THETA_LOOKAHEAD_MIN would erase the current gain (the
            clock, not price, is the threat). Uses live per-contract theta.
        (b) FVG-anchored trailing stop for ALL longs (ORB + Sweep), armed at
            +FVG_TRAIL_ARM_PCT: parks at the far edge of the nearest unfilled
            in-favor 1m FVG (room to continue), runs with the % trail (max wins).
v1.4 — 2026-07-07 — ADOPTED-position exit path: manages a position discovered
        open at the broker on a LIVE restart with no DB plan (see
        broker_reconcile) by the universal core of our rules — sign-correct
        max-loss stop (long/short), long-side profit trail, 15:45 hard close.
        No strategy-specific context required.
v1.5 — 2026-07-07 — theta-bleed REWORK (merged onto the v1.4 adopted-position
        path; supersedes the v1.3 theta logic that shipped inside v1.4). The
        v1.3 check fired on the first green tick: on 07-07 and 07-08, ~50-58 of
        ~77-87 exits were theta_bleed at a median ~60s hold, capping trends
        while the day's P&L came from the trades that reached the trail.
        _theta_bleed is now bounded by four gates: (1) a minimum gain floor,
        (2) a trail ceiling (once armed, the trail owns the trade — theta goes
        silent so trends run), (3) a MIN-HOLD blackout after entry, and (4) a
        corrected per-CALENDAR-day decay projection (v1.3/v1.4 divided by
        RTH_MINUTES=390, overstating projected decay ~3.7x). No call sites
        change; the adopted-position exit path (_evaluate_adopted) is untouched.
v1.6 — 2026-07-09 — ORB UNCONDITIONAL -25% HARD FLOOR (critical risk fix). The
        -25% dollar failsafe is universal by design and sweep/butterfly/adopted
        all enforce it directly (if current_premium <= stop_prem). ORB was the
        lone exception: it routed its floor through _update_trail, which returns
        None below the +50% trail activation — so any ORB trade that never armed
        the trail ran with NO dollar-loss stop and could bleed toward zero while
        the structure stop held (CRM 2026-07-09: -83%, underlying still above the
        range, trail never armed). _evaluate_orb now checks the floor DIRECTLY and
        UNCONDITIONALLY right after the hard-close check, mirroring the other
        three paths. _update_trail is unchanged (its de-arm is correct for the
        TRAIL; the floor no longer depends on it). Known failure mode — the
        adopted path's own comment already flagged _update_trail's de-arm.
v3.0 — 2026-07-10 — repo-wide v3.0 bump: Yahoo-Finance purge & data stream
        mapping optimization (all market data now flows from the single
        shared TastyTrade candle feed — see data/candle_feed.py). No logic
        change in this file.

Exit triggers by strategy:

  ORB
    1. HARD CLOSE: 15:45 ET
    2. STRUCTURE STOP: 1-min close beyond the impulsive candle's origin
       (close < impulsive low for longs, close > impulsive high for shorts).
       Closing back inside the range alone does NOT stop — only a close past
       the impulsive origin does. Runs beside the unconditional -25% floor.
    3. TRAIL (below 100% TP): activates at 50% TP, trails at 75% of current premium
    4. TRAIL (at/past 100% TP): tightens to track the nearest unfilled 1m FVG
       in the trade\'s favor — no hard exit at target, position can keep running

  SWEEP REVERSAL
    1. HARD CLOSE: 15:45 ET
    2. HARD STOP: current premium <= 25% loss
    3. TARGET HIT: 100% TP
    4. BOS EXIT: 1-min break of structure against position
    5. TRAIL: activates at 50% TP

  BUTTERFLY
    1. HARD CLOSE: 15:45 ET
    2. MAX HOLD: 2.5 hours
    3. HARD STOP: net value <= 25% loss
    4. TARGET HIT: 25% of max profit

  ADOPTED (broker-discovered, no DB plan)
    1. HARD CLOSE: 15:45 ET
    2. MAX-LOSS STOP: sign-correct (long: premium <= stop; short: premium >= stop)
    3. LONG PROFIT TRAIL: standard trail to lock gains; short rides to hard close
"""

import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, List, Tuple
from datetime import datetime

import pandas as pd

from tastytrade.order import (
    NewOrder, Leg, OrderAction, OrderType, OrderTimeInForce,
    PriceEffect, InstrumentType, OrderStatus
)

import config as _cfg   # live fill knobs read at CALL time (test/env tunable)

from database.trade_logger import TradeRecord, get_trade_logger
from data.tasty_client import get_session, get_account, TastyClientError
from config import (
    BOS_MIN_DIST_ATR,                          # v4.15
    PAPER_TRADING, CONTRACT_MULTIPLIER,
    BUTTERFLY_MAX_HOLD_MIN, TRAIL_LOCK_PCT, TRAIL_ACTIVATION_PCT, FVG_MIN_SIZE_PCT,
    THETA_LOOKAHEAD_MIN, RTH_MINUTES, FVG_TRAIL_ARM_PCT, FVG_TRAIL_LOCK_PCT,
    CONT_INSURANCE_STOP,
    MAX_LOSS_PCT, POST_TARGET_TRAIL_LOCK_PCT, FVG_FLOOR_MAX_LOCK_PCT,
    USE_5M_FVG_TRAIL, SWEEP_POST_TARGET_TRAIL,
    CONTINUATION_EXHAUST_EXT_ATR, CONTINUATION_EXHAUST_MIN_GAIN,
    CONTINUATION_EXHAUST_TRAIL_LOCK, CONTINUATION_STOP_LOSS_PCT
)
from utils.time_utils import (is_hard_close_time, minutes_since, now_utc,
                              fmt_et_short, now_et, ts_for_db)
from execution.limit_ladder import limit_at_mark, hard_close_order_mode
# v4.21 (AUDIT F1): the binding v4.20 forgot. `is_trend_participation` was
# called in _evaluate_condor_leg and never imported — NameError on every condor
# leg evaluation. `is_credit_vertical` routes the dispatch (F2).
from strategy.structure import is_trend_participation, is_credit_vertical

logger = logging.getLogger(__name__)

# POST_TARGET_TRAIL_LOCK_PCT now lives in config (v3.8): 0.85→0.75 default —
# the old value made the leash TIGHTER past target than before it (inverted),
# harvesting proven runners on a single gamma wick. Env: OT_POST_TARGET_TRAIL_LOCK_PCT.

# ─── Theta-bleed gates (v1.5) ─────────────────────────────────────────────────
# Bound the theta-bleed exit to its legitimate job — a small, stalled winner
# that has had time to develop and still won't reach the trail. Without these
# the check fires on the first green tick (see v1.5 header note).
THETA_MIN_HOLD_MIN       = 20      # blackout: no theta exit in the first N min after entry
from config import (VELOCITY_STALL_ENABLED, VELOCITY_STALL_ENFORCE,   # VEL.1
                    VELOCITY_GRACE_MIN, VELOCITY_STRICTNESS,
                    VELOCITY_CONFIRM_TICKS, VELOCITY_FLOOR_BY_MIN,
                    VELOCITY_MEASURED_STRATEGIES)
THETA_MIN_GAIN_PCT       = 0.10    # gain floor: don't protect a gain smaller than this
MINUTES_PER_CALENDAR_DAY = 1440    # theta greek is $/share/CALENDAR day (not the 390 RTH min)


# W.2 — throttle keys for TELEMETRY-only debug lines. Deliberately NOT the
# alert set: swallow_audit classifies a handler by what its body names, and
# reusing `_live_exit_alerted` made a debug-only handler read as "pages". A
# census you can mislead by choosing a variable name is not a census.
_telemetry_logged: set = set()


@dataclass
class FillResult:
    """The outcome of a close order — the SHARED CONTRACT between paper and live.

    Both place_exit_order() modes return one of these; _execute_exit() books P&L
    from it and NEVER inspects paper_trading itself. This is the seam that lets
    the paper implementation (here, now) and the live broker-confirmation
    implementation (Fable — see FABLE_SPEC_live_exit_fill_confirmation.md)
    coexist without either re-tooling the other:

        - confirmed=True  → the close is REAL. Book P&L at fill_price. Only a
                            confirmed result may ever mark a DB row closed.
        - confirmed=False → NOT filled. Book NOTHING, mark NOTHING closed. The
                            position stays open and the caller retries/escalates.
                            This is the anti-orphan invariant: an unconfirmed
                            live close must never become a $0.00 (or any) row.

    fill_price is the price the position ACTUALLY closed at — a simulated mark in
    paper, the broker's real fill in live. It is never entry-as-a-fallback and
    never a fabricated 0.0; if there is no real price, confirmed must be False.
    """
    confirmed:   bool
    fill_price:  Optional[float] = None      # actual close price; None iff not confirmed
    order_id:    Optional[str]   = None       # broker order id (live); None in paper
    partial:     bool            = False      # live: partially filled, remainder working
    detail:      str             = ""         # human-readable status for logs/alerts


@dataclass
class ExitDecision:
    should_exit:        bool  = False
    exit_reason:        str   = ""
    new_trail_stop:     Optional[float] = None
    current_pnl_pct:    float = 0.0
    current_pnl_usd:    float = 0.0


@dataclass
class _SimpleFVG:
    """Minimal 1-minute FVG used only for the post-target ORB trail."""
    top:       float
    bottom:    float
    direction: str   # "bullish" or "bearish"
    index:     int


def _find_1m_fvgs(df_1m: pd.DataFrame) -> List["_SimpleFVG"]:
    """
    Detect Fair Value Gaps on the 1-minute timeframe only.
    Same 3-candle imbalance logic as structure_analyzer.py, scoped to 1m
    since ORB entry/exit conditions are always evaluated on 1m.
    Returns most-recent-first.
    """
    gaps: List[_SimpleFVG] = []
    if df_1m is None or len(df_1m) < 3:
        return gaps

    for i in range(2, len(df_1m)):
        # Bullish FVG: candle[i].low > candle[i-2].high
        gap_bot = float(df_1m["high"].iloc[i - 2])
        gap_top = float(df_1m["low"].iloc[i])
        if gap_top > gap_bot:
            size_pct = (gap_top - gap_bot) / gap_bot if gap_bot > 0 else 0
            if size_pct >= FVG_MIN_SIZE_PCT:
                gaps.append(_SimpleFVG(top=gap_top, bottom=gap_bot,
                                        direction="bullish", index=i))

        # Bearish FVG: candle[i].high < candle[i-2].low
        gap_top2 = float(df_1m["low"].iloc[i - 2])
        gap_bot2 = float(df_1m["high"].iloc[i])
        if gap_bot2 < gap_top2:
            size_pct = (gap_top2 - gap_bot2) / gap_top2 if gap_top2 > 0 else 0
            if size_pct >= FVG_MIN_SIZE_PCT:
                gaps.append(_SimpleFVG(top=gap_top2, bottom=gap_bot2,
                                        direction="bearish", index=i))

    return sorted(gaps, key=lambda g: g.index, reverse=True)


def _nearest_unfilled_fvg_in_favor(df_1m: pd.DataFrame, current_price: float,
                                    direction: str) -> Optional["_SimpleFVG"]:
    """
    Find the nearest unfilled 1m FVG below current price for a long
    (bullish gap, price hasn\'t traded back down through it) or above
    current price for a short (bearish gap, price hasn\'t traded back
    up through it). This is the gap the trail should give the trade
    room to wick back into without exiting.
    """
    gaps = _find_1m_fvgs(df_1m)
    if not gaps:
        return None

    candidates = []
    for g in gaps:
        if direction == "long" and g.direction == "bullish" and g.top < current_price:
            candidates.append(g)
        elif direction == "short" and g.direction == "bearish" and g.bottom > current_price:
            candidates.append(g)

    if not candidates:
        return None

    if direction == "long":
        return max(candidates, key=lambda g: g.top)
    else:
        return min(candidates, key=lambda g: g.bottom)


class BOSTracker:
    """
    Tracks 1-minute Break of Structure for sweep reversal trades.
    Long:  tracks highest closing high \u2192 protected HL = low of that candle
           BOS = 1m close below protected HL
    Short: tracks lowest closing low \u2192 protected LH = high of that candle
           BOS = 1m close above protected LH
    """
    def __init__(self, direction: str, entry_price: float,
                 min_dist: float = 0.0):
        self.direction       = direction
        self.entry_price     = entry_price
        self.peak_close      = entry_price
        self.protected_level = None   # HL for longs, LH for shorts
        # v4.15 — MINIMUM DISTANCE. The protected level is seeded from the LOW
        # of the first bar that closes above entry, and on a pullback entry that
        # bar is the smallest, earliest part of the resumption — its low sits a
        # hair under entry. The level therefore lands INSIDE the symbol's own
        # noise band, and the next ordinary wiggle fires BOS.
        # Observed live 2026-08-10: JPM in at $1.26 12:49, out at EXACTLY $0.00
        # 12:50, back in at $1.26 the same minute. A null round trip — the exit
        # condition was already true at entry. QQQ the same session fragmented
        # ONE move into four scratches (+$30/+$45.50/+$35/+$7) by the same
        # mechanism: exit, setup still valid, re-enter, repeat.
        # `min_dist` is passed in ATR terms by the caller so it scales with the
        # symbol; a raw price gap never could.
        self.min_dist        = max(0.0, float(min_dist or 0.0))

    def update(self, df_1m: pd.DataFrame) -> bool:
        """
        Update structure tracking. Returns True if BOS triggered.
        Uses iloc[-2] \u2014 the last fully closed candle.
        """
        if df_1m is None or len(df_1m) < 3:
            return False

        candle = df_1m.iloc[-2]   # last closed candle
        close  = float(candle["close"])
        high   = float(candle["high"])
        low    = float(candle["low"])

        if self.direction == "long":
            if close > self.peak_close:
                self.peak_close      = close
                # v4.15 — never seed INSIDE the noise band, and never LOOSEN.
                # `low - min_dist` is not monotone: if the caller's ATR widens,
                # a new candidate can come out BELOW the old level, which would
                # silently slacken the stop exactly when volatility is rising.
                # max() makes the level ratchet in one direction only.
                if self.min_dist > 0:
                    _cand = min(low, self.entry_price - self.min_dist)
                    self.protected_level = (
                        _cand if self.protected_level is None
                        else max(self.protected_level, _cand))
                else:
                    # min_dist == 0 must be BYTE-IDENTICAL to pre-v4.15,
                    # ratchet included — otherwise the kill switch is not a
                    # kill switch and there is no A/B control. Caught by
                    # test_min_dist_zero_is_byte_identical_to_the_old_behaviour.
                    self.protected_level = low
                logger.debug(
                    f"BOS long: new HH close={close:.2f} "
                    f"protected_HL={self.protected_level:.2f}"
                )
            if self.protected_level and close < self.protected_level:
                logger.info(
                    f"BOS TRIGGERED (long): close={close:.2f} < "
                    f"protected_HL={self.protected_level:.2f}"
                )
                return True

        else:  # short
            if close < self.peak_close:
                self.peak_close      = close
                if self.min_dist > 0:
                    _cand = max(high, self.entry_price + self.min_dist)
                    self.protected_level = (
                        _cand if self.protected_level is None
                        else min(self.protected_level, _cand))
                else:
                    self.protected_level = high
                logger.debug(
                    f"BOS short: new LL close={close:.2f} "
                    f"protected_LH={self.protected_level:.2f}"
                )
            if self.protected_level and close > self.protected_level:
                logger.info(
                    f"BOS TRIGGERED (short): close={close:.2f} > "
                    f"protected_LH={self.protected_level:.2f}"
                )
                return True

        return False


class ExitEngine:
    """Evaluates every open options trade on each tick."""

    def __init__(self, paper_trading: bool = PAPER_TRADING):
        self.paper_trading  = paper_trading
        self._trail_stops:  dict = {}
        self._condor_ratchet: dict = {}   # v4.1 condor ratcheting stop
        self._exhaust_state: dict = {}   # per-trade {ext, mom} for continuation divergence
        self._trail_active: dict = {}
        self._bos_trackers: dict = {}   # trade_id \u2192 BOSTracker (sweep only)
        self._post_target_trail: dict = {}   # trade_id \u2192 bool (ORB only)
        # VEL.1 - consecutive velocity breaches per trade. WITHOUT THIS the
        # check AttributeErrors on first call and the except swallows it,
        # leaving a permanent silent no-op.
        self._vel_breaches: dict = {}          # trade_id -> consecutive breaches
        self._trade_logger  = get_trade_logger()
        self._live_exit_alerted: set = set()  # (trade_id, kind) — one page per failure kind

    @staticmethod
    def _fvg_frame(df_1m: Optional[pd.DataFrame],
                   df_5m: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
        """v3.8: trails anchor to 5-MINUTE FVGs (structurally meaningful gaps,
        natural gamma room) when enabled and available; 1m remains the
        fallback — and stays authoritative for the structure stop and BOS,
        which are speed-critical and unchanged."""
        if USE_5M_FVG_TRAIL and df_5m is not None and len(df_5m) >= 3:
            return df_5m
        return df_1m

    def _seed_trail_from_record(self, record: TradeRecord) -> None:
        """v3.3 — recovery seed. If this trade has a persisted trail level
        (record['trail_stop'], written by position_manager v3.1) and this
        engine instance has no in-memory trail for it yet (i.e. we restarted
        mid-position), adopt the persisted level so the locked profit floor
        survives the restart. Adopted longs also re-arm their persistent-trail
        flag, since their trail block is gated on _trail_active."""
        trade_id = record.get("trade_id", "")
        if not trade_id or trade_id in self._trail_stops:
            return
        try:
            persisted = float(record.get("trail_stop", 0.0) or 0.0)
        except (TypeError, ValueError):
            return
        if persisted > 0:
            self._trail_stops[trade_id] = persisted
            if record.get("strategy", "") == "ADOPTED":
                self._trail_active[trade_id] = True
            logger.info(
                f"Trail recovered from DB: {trade_id[:8]} trail=${persisted:.2f}"
            )

    def evaluate(self,
                 record: TradeRecord,
                 current_premium: float,
                 df_1m: Optional[pd.DataFrame] = None,
                 regime: Optional[str] = None,
                 df_5m: Optional[pd.DataFrame] = None,
                 vol_state=None,
                 trend=None) -> ExitDecision:
        """
        Strategy-aware exit evaluation.
        Routes to the appropriate exit logic based on strategy_name.
        regime: current regime string — used for regime-flip exit checks on
                neutral strategies (butterfly, condor) that depend on RANGING.
        """
        strategy = record.get("strategy", "")

        # v3.3: restart recovery — re-arm the in-memory trail from the persisted
        # trail_stop column (position_manager writes it there as of v3.1;
        # stop_premium is the immutable -25% floor and is never overwritten).
        # Without this seed, a mid-trail restart would forget the locked level
        # until the trail re-armed on its own.
        self._seed_trail_from_record(record)

        if record.get("is_butterfly"):
            return self._evaluate_butterfly(record, current_premium, regime=regime)
        elif strategy == "IronCondorStrategy" or is_credit_vertical(record):
            # v4.21 (AUDIT F2): route on the STRUCTURE, not one strategy string.
            # main v6.8 writes strategy="TrendCreditSpread"; the old test sent
            # every new TC.6 record to _evaluate_sweep (the DEBIT evaluator) —
            # the TC.6 branch inside the condor evaluator was unreachable for
            # every record opened after the identity fix. is_credit_vertical()
            # reads only persisted columns, so legacy rows and the rolled
            # broken wing route here too.
            return self._evaluate_condor_leg(record, current_premium,
                                             regime=regime, df_1m=df_1m)
        elif strategy == "ADOPTED":
            return self._evaluate_adopted(record, current_premium)
        elif strategy == "ORBStrategy":
            return self._evaluate_orb(record, current_premium, df_1m, df_5m)
        elif strategy == "ContinuationStrategy":
            return self._evaluate_continuation(record, current_premium, df_1m,
                                               df_5m=df_5m, regime=regime,
                                               vol_state=vol_state, trend=trend)
        else:
            # SweepReversal and any other directional strategies
            return self._evaluate_sweep(record, current_premium, df_1m, df_5m)

    # \u2500\u2500\u2500 ORB Exit \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

    def _evaluate_orb(self, record: TradeRecord,
                       current_premium: float,
                       df_1m: Optional[pd.DataFrame],
                       df_5m: Optional[pd.DataFrame] = None) -> ExitDecision:
        """
        ORB exit logic (v3.2 doc sync \u2014 this now matches the code below).
        Evaluated every tick, FIRST MATCH WINS:
          1. HARD CLOSE      \u2014 15:45 ET.
          2. HARD STOP       \u2014 premium <= entry * 0.75 (\u221225% floor).
                               UNCONDITIONAL, every tick, independent of trail state.
          3. STRUCTURE STOP  \u2014 last CLOSED 1m candle closes BEYOND the impulsive
                               (break) candle's wick: close < impulsive low (long) /
                               close > impulsive high (short), read from record
                               `underlying_stop`. NOT the ORB range boundary:
                               closing back INSIDE the range does NOT stop the trade.
                               (2) and (3) are an AND \u2014 premium death and thesis
                               death are caught independently, whichever fires first.
          4. THETA BLEED     \u2014 gated: held >= 20 min AND gain in [10%, 20%) AND
                               projected decay over the lookahead erases the gain.
          5. PAST 100% TP    \u2014 no hard exit. Trail tightens to the nearest unfilled
                               in-favor 1m FVG, floored at 85% of current premium.
          6. BELOW 100% TP   \u2014 FVG trail arms at +20%; % trail arms at +50% and
                               ratchets to 75% of current premium. Higher governs.
        NO break-of-structure exit (BOS is sweep-only). NO max-hold. The 11:00 ET
        cutoff expires the ENGINE, not an open position \u2014 a filled ORB runs to its
        own exits, up to the 15:45 hard close.
        """
        decision   = ExitDecision()
        trade_id   = record["trade_id"]
        entry_prem = record["entry_premium"]
        target     = record["target_premium"]
        trail_act  = record["trail_activation"]
        direction  = record.get("direction", "long")

        # P&L
        pnl_pct = (current_premium - entry_prem) / entry_prem if entry_prem > 0 else 0
        pnl_usd = (current_premium - entry_prem) * record["contracts"] * CONTRACT_MULTIPLIER
        decision.current_pnl_pct = pnl_pct
        decision.current_pnl_usd = pnl_usd

        # 1. HARD CLOSE
        if is_hard_close_time():
            decision.should_exit = True
            decision.exit_reason = "hard_close_15:45_ET"
            return decision

        # 1b. HARD STOP — unconditional -25% dollar floor (v1.6). Mirrors the
        #     sweep/butterfly/adopted paths, which check the floor DIRECTLY. ORB
        #     previously relied on _update_trail for this, but that returns None
        #     below the +50% trail activation — so a trade that never armed the
        #     trail had NO floor and could bleed toward zero while the structure
        #     stop held (CRM 2026-07-09: -83%). The floor must fire every tick,
        #     regardless of trail state. As of v3.3, record['stop_premium'] is
        #     IMMUTABLE (set once at entry; trails persist in trail_stop), so
        #     this check is truthful: it fires only at the real -25% floor.
        stop_prem = record.get("stop_premium", 0.0) or (entry_prem * (1 - MAX_LOSS_PCT))
        if stop_prem > 0 and current_premium <= stop_prem:
            decision.should_exit = True
            # label carries the record's ACTUAL floor pct (older records keep
            # their entry-time 25%; new ones carry MAX_LOSS_PCT) — truthful
            # either way for the exit_reason distributions.
            floor_pct = 1 - (stop_prem / entry_prem) if entry_prem > 0 else MAX_LOSS_PCT
            decision.exit_reason = f"hard_stop_{floor_pct:.0%} pnl={pnl_pct:.1%}"
            logger.info(
                f"ORB HARD STOP: {trade_id[:8]} prem={current_premium:.2f} "
                f"<= floor={stop_prem:.2f} (pnl={pnl_pct:.1%})"
            )
            return decision

        # 2. STRUCTURE STOP \u2014 1-min CLOSE beyond the IMPULSIVE candle's origin
        #    (v3.1). The invalidation level is the impulsive (break) candle's wick
        #    \u2014 its low for a long, its high for a short \u2014 carried on the record as
        #    `underlying_stop`, NOT the ORB range boundary. Merely closing back
        #    inside the range does NOT stop the trade: price is allowed to breathe
        #    inside the range as long as it holds the impulsive origin. Only a
        #    close PAST that origin invalidates the thesis. This is close-based on
        #    the last CLOSED candle (iloc[-2]) so an intrabar wick into the range
        #    survives; only a confirmed close beyond the origin exits. The \u201325%
        #    premium floor above is independent and still fires first if the
        #    dollars are gone (theta, retracement, or the two combined) even when
        #    this structure level is still intact \u2014 the two are an AND, not an OR.
        if df_1m is not None and len(df_1m) >= 2:
            stop_level = record.get("underlying_stop", 0.0)
            if stop_level > 0:
                last_close = float(df_1m.iloc[-2]["close"])
                if direction == "long" and last_close < stop_level:
                    decision.should_exit = True
                    decision.exit_reason = (
                        f"orb_structure_stop: 1m close {last_close:.2f} "
                        f"below impulsive-candle low {stop_level:.2f}"
                    )
                    logger.info(
                        f"ORB STOP: {trade_id[:8]} 1m close={last_close:.2f} "
                        f"< impulsive_low={stop_level:.2f} \u2014 origin violated"
                    )
                    return decision
                elif direction == "short" and last_close > stop_level:
                    decision.should_exit = True
                    decision.exit_reason = (
                        f"orb_structure_stop: 1m close {last_close:.2f} "
                        f"above impulsive-candle high {stop_level:.2f}"
                    )
                    logger.info(
                        f"ORB STOP: {trade_id[:8]} 1m close={last_close:.2f} "
                        f"> impulsive_high={stop_level:.2f} \u2014 origin violated"
                    )
                    return decision

        # 2b. THETA BLEED \u2014 profitable but time is about to eat the gain
        if self._theta_bleed(record, current_premium, pnl_pct):
            decision.should_exit = True
            decision.exit_reason = f"theta_bleed pnl={pnl_pct:.1%}"
            return decision
        # 2c. VELOCITY STALL - "is this thing MOVING at all?"
        # ORDER IS DELIBERATE AND MUST NOT BE SWAPPED: theta_bleed evaluates
        # FIRST so a trade that is up 10-20% and stalled exits GREEN via that
        # path, rather than falling through to a velocity check that would
        # let it drift back toward flat before firing.
        # These are INDEPENDENT gates, never a combined score. The 2026-08-12
        # QQQ failure was two mechanisms each correctly answering "not my
        # problem" while nothing aggregated that into "then NOBODY is
        # watching." A blended score would have averaged three healthy-ish
        # signals into inaction; separate gates, any one of which can fire,
        # fails safe.
        _vel = self._velocity_stall(record, pnl_pct, df_1m)
        if _vel is not None:
            decision.should_exit = True
            decision.exit_reason = _vel
            return decision

        # 3. PAST 100% TP \u2014 switch to tightened FVG-aware trail, no hard exit
        if current_premium >= target:
            if not self._post_target_trail.get(trade_id, False):
                self._post_target_trail[trade_id] = True
                logger.info(
                    f"ORB TARGET REACHED (no hard exit): {trade_id[:8]} "
                    f"pnl={pnl_pct:.1%} \u2014 switching to tightened FVG trail"
                )

            trail_stop = self._update_post_target_trail(
                trade_id, current_premium, record,
                self._fvg_frame(df_1m, df_5m), direction
            )
            if trail_stop is not None:
                if current_premium <= trail_stop:
                    decision.should_exit = True
                    decision.exit_reason = f"orb_fvg_trail_stop pnl={pnl_pct:.1%}"
                    return decision
                decision.new_trail_stop = trail_stop
            return decision

        # 4. TRAIL \u2014 below 100% TP: FVG-anchored once armed (+20%), plus the
        #    50% % trail; the higher of the two governs.
        if pnl_pct >= FVG_TRAIL_ARM_PCT:
            self._update_fvg_trail(trade_id, current_premium, record,
                                   self._fvg_frame(df_1m, df_5m), direction)
        trail_stop = self._update_trail(
            trade_id, current_premium, entry_prem, trail_act,
            record.get("stop_premium", 0.0) or entry_prem * (1 - MAX_LOSS_PCT)
        )
        trail_stop = self._trail_stops.get(trade_id, trail_stop)
        if trail_stop is not None:
            if current_premium <= trail_stop:
                decision.should_exit = True
                decision.exit_reason = f"orb_trail_stop pnl={pnl_pct:.1%}"
                return decision
            decision.new_trail_stop = trail_stop

        return decision

    def _update_post_target_trail(self, trade_id: str, current_premium: float,
                                   record: TradeRecord,
                                   df_1m: Optional[pd.DataFrame],
                                   direction: str) -> Optional[float]:
        """
        Past 100% TP: trail tightens to track the nearest unfilled 1m FVG
        in the trade\'s favor, converted to an equivalent premium floor.
        Falls back to a tightened percentage trail (85% of current premium)
        if no usable FVG is found in the 1m data.
        """
        underlying_entry  = record.get("underlying_entry", 0.0)
        underlying_target = record.get("underlying_target", 0.0)
        entry_prem        = record["entry_premium"]

        fvg_floor_premium = None

        if df_1m is not None and underlying_entry > 0 and underlying_target > 0:
            current_underlying_move = abs(underlying_target - underlying_entry)
            fvg = _nearest_unfilled_fvg_in_favor(
                df_1m,
                current_price=underlying_target,
                direction=direction
            )
            if fvg is not None and current_underlying_move > 0:
                premium_per_point = (current_premium - entry_prem) / current_underlying_move \
                                    if current_underlying_move > 0 else 0
                if direction == "long":
                    underlying_floor = fvg.top
                else:
                    underlying_floor = fvg.bottom

                underlying_distance_from_entry = abs(underlying_floor - underlying_entry)
                fvg_floor_premium = entry_prem + (underlying_distance_from_entry * premium_per_point)

        pct_trail = current_premium * POST_TARGET_TRAIL_LOCK_PCT

        if fvg_floor_premium is not None:
            new_trail = max(fvg_floor_premium, pct_trail)
        else:
            new_trail = pct_trail
        # v3.8 CLAMP (same as _update_fvg_trail): the floor may never sit
        # tighter than FVG_FLOOR_MAX_LOCK_PCT of current premium.
        new_trail = min(new_trail, current_premium * FVG_FLOOR_MAX_LOCK_PCT)

        current_trail = self._trail_stops.get(trade_id, entry_prem)
        if new_trail > current_trail:
            self._trail_stops[trade_id] = new_trail
            logger.debug(
                f"ORB post-target trail updated: {trade_id[:8]} "
                f"trail=${self._trail_stops[trade_id]:.2f} "
                f"(fvg_based={fvg_floor_premium is not None})"
            )

        return self._trail_stops.get(trade_id)

    # ─── Long-option theta protection + general FVG trail ─────────────────────
    def _velocity_stall(self, record: TradeRecord, pnl_pct: float,
                        df_1m) -> Optional[str]:
        """Is the underlying still delivering fast enough to beat decay?

        Returns an exit_reason when the position should be cut, else None.
        NEVER RAISES - an exit path that can throw is worse than one that
        occasionally declines to act.

        THE QUESTION NOTHING ELSE ASKS. `orb_structure_stop` asks whether the
        thesis broke; `_theta_bleed` asks whether a GAIN is about to evaporate
        (its gate 1 is a gain floor, so a LOSING position is invisible to it).
        A losing position that has STOPPED MOVING answers no to both, and the
        -40% percentage floor eventually catching it is the ABSENCE of a
        mechanism rather than one. On 2026-08-12 that cost a QQQ trade 50
        minutes and -42.2% while the underlying sat BELOW the short entry the
        entire time - directionally right, and bleeding anyway.

        NO TARGET IS USED. bev = |theta| / (|delta| * 1440) is the option's own
        physics, so this generalises to EVERY long-premium strategy rather than
        only ORB. The target-based form of the same idea was MEASURED AND
        REJECTED: feasibility ratio at entry ran HIGHER for losers than winners
        at every percentile (losers p50 5.05 vs winners 3.87, n=145) - a wide
        range gives a distant target AND a big required move, so feasibility and
        difficulty turn out to be the same axis pointing opposite ways. Do not
        reintroduce it.

        FOUR GATES:
          (1) GRACE    - no evaluation before VELOCITY_GRACE_MIN. Forced by the
                         data, not chosen: winners p10 at 5 minutes is -21.1,
                         i.e. the bottom decile of eventual WINNERS was moving
                         AWAY. Any earlier check kills those trades.
          (2) MEASURED - a strategy with no measured floor is evaluated and
                         LOGGED but never cut, whatever ENFORCE says.
          (3) FLOOR    - ratio must hold above winners-p10 * STRICTNESS at the
                         largest mark <= held.
          (4) CONFIRM  - VELOCITY_CONFIRM_TICKS consecutive breaches. QQQ crossed
                         back ABOVE breakeven at minutes 41-61 before dying at
                         70; a single-tick rule oscillates.
        """
        try:
            if not VELOCITY_STALL_ENABLED:
                return None
            trade_id = str(record.get("trade_id", ""))
            entry_time = record.get("entry_time")
            if not entry_time:
                return None
            entry_dt = entry_time if isinstance(entry_time, datetime) else None
            if entry_dt is None:
                try:
                    entry_dt = datetime.fromisoformat(str(entry_time))
                except ValueError:
                    return None
            held = minutes_since(entry_dt)
            if held < VELOCITY_GRACE_MIN:                      # (1) grace
                self._vel_breaches.pop(trade_id, None)
                return None
            delta = abs(float(record.get("current_delta", 0.0) or 0.0))
            theta = abs(float(record.get("current_theta", 0.0) or 0.0))
            if delta <= 1e-6 or theta <= 0.0:
                return None                    # no live Greeks -> do not guess
            und_entry = float(record.get("underlying_entry", 0.0) or 0.0)
            if und_entry <= 0 or df_1m is None or len(df_1m) == 0:
                return None
            und_now = float(df_1m["close"].iloc[-1])
            short = str(record.get("direction", "")) == "short"
            travelled = (und_entry - und_now) if short else (und_now - und_entry)
            delivered = travelled / max(held, 1e-9)
            bev = theta / (delta * 1440.0)
            if bev <= 0:
                return None
            ratio = delivered / bev
            marks = [m for m in sorted(VELOCITY_FLOOR_BY_MIN) if m <= held]
            if not marks:
                return None
            floor = VELOCITY_FLOOR_BY_MIN[marks[-1]] * VELOCITY_STRICTNESS
            if ratio >= floor:                                 # (3) floor
                self._vel_breaches.pop(trade_id, None)
                return None
            n = self._vel_breaches.get(trade_id, 0) + 1
            self._vel_breaches[trade_id] = n
            if n < VELOCITY_CONFIRM_TICKS:                     # (4) confirm
                return None
            strategy = str(record.get("strategy", ""))
            measured = strategy in VELOCITY_MEASURED_STRATEGIES
            if not (VELOCITY_STALL_ENFORCE and measured):      # (2) measured
                logger.info(
                    "VELOCITY STALL (observe-only%s): %s %s held=%.1fm "
                    "ratio=%.1f floor=%.1f delivered=%.4f bev=%.4f pnl=%.1f%%",
                    "" if measured else ", UNMEASURED strategy",
                    trade_id[:8], strategy, held, ratio, floor,
                    delivered, bev, pnl_pct * 100.0)
                return None
            logger.info(
                "VELOCITY STALL EXIT: %s held=%.1fm ratio=%.1f < floor=%.1f "
                "(delivered %.4f pts/min vs breakeven %.4f) pnl=%.1f%%",
                trade_id[:8], held, ratio, floor, delivered, bev,
                pnl_pct * 100.0)
            return (f"velocity_stall ratio={ratio:.1f}<{floor:.1f} "
                    f"held={held:.0f}m")
        except Exception as exc:                                # noqa: BLE001
            logger.debug("velocity stall check failed: %s", exc)
            return None

    def _theta_bleed(self, record: TradeRecord, current_premium: float,
                     pnl_pct: float) -> bool:
        """True only when a long has EARNED a real, sub-trail gain that time
        decay is now projected to erase — AND has been given room to develop
        first. Four gates (see v1.5 header) bound what was previously a
        first-green-tick guillotine:
          (1) GAIN FLOOR    — skip a trivial winner (< THETA_MIN_GAIN_PCT).
          (2) TRAIL CEILING — once up >= FVG_TRAIL_ARM_PCT the trail owns the
                              trade; theta stays silent so trends run.
          (3) MIN HOLD      — a THETA_MIN_HOLD_MIN blackout after entry lets the
                              move develop before the clock can cut it.
          (4) DECAY vs GAIN — only then, if projected decay over the lookahead
                              erases the gain, exit. Theta is $/share/CALENDAR
                              day, so scale the lookahead by 1440 min/day.
        Active window: held >= THETA_MIN_HOLD_MIN AND gain in
        [THETA_MIN_GAIN_PCT, FVG_TRAIL_ARM_PCT) AND stalling to theta."""
        # (1) gain floor — a tiny green is not worth protecting
        if pnl_pct < THETA_MIN_GAIN_PCT:
            return False
        # (2) trail ceiling — a running trade belongs to the trail, not theta
        if pnl_pct >= FVG_TRAIL_ARM_PCT:
            return False
        # (3) min-hold blackout — give the move room before the clock can cut it
        entry_time = record.get("entry_time")
        if not entry_time:
            return False                       # can't verify hold ⇒ don't cut
        entry_dt = entry_time if isinstance(entry_time, datetime) else None
        if entry_dt is None:
            try:
                entry_dt = datetime.fromisoformat(str(entry_time))
            except ValueError:
                return False
        if minutes_since(entry_dt) < THETA_MIN_HOLD_MIN:
            return False
        # (4) projected decay vs current gain
        theta = abs(float(record.get("current_theta", 0.0) or 0.0))  # $/share/CAL day
        if theta <= 0:
            return False
        gain_per_share = current_premium - record["entry_premium"]
        if gain_per_share <= 0:
            return False
        proj_decay = theta * (THETA_LOOKAHEAD_MIN / MINUTES_PER_CALENDAR_DAY)
        return proj_decay >= gain_per_share

    def _update_fvg_trail(self, trade_id: str, current_premium: float,
                          record: TradeRecord, df_1m: Optional[pd.DataFrame],
                          direction: str) -> Optional[float]:
        """FVG-anchored trailing stop for a long, armed once profitable. The
        stop parks at the FAR edge of the nearest unfilled in-favor 1m FVG
        (converted to an equivalent premium floor) so the trade has room to pull
        back INTO the gap for continuation; only a move beyond the gap exits.
        Falls back to a % lock of current premium when no usable FVG exists.
        Writes to the shared _trail_stops (highest trail wins)."""
        entry_prem       = record["entry_premium"]
        underlying_entry = record.get("underlying_entry", 0.0)
        fvg_floor_premium = None

        if df_1m is not None and len(df_1m) > 0 and underlying_entry > 0:
            cur_under = float(df_1m["close"].iloc[-1])
            move_from_entry = abs(cur_under - underlying_entry)
            fvg = _nearest_unfilled_fvg_in_favor(df_1m, current_price=cur_under,
                                                 direction=direction)
            if fvg is not None and move_from_entry > 0:
                premium_per_point = (current_premium - entry_prem) / move_from_entry
                # FAR edge → room to wick INTO the gap before exiting
                underlying_floor = fvg.bottom if direction == "long" else fvg.top
                dist = abs(underlying_floor - underlying_entry)
                fvg_floor_premium = entry_prem + dist * premium_per_point

        pct_trail = current_premium * FVG_TRAIL_LOCK_PCT
        new_trail = max(fvg_floor_premium, pct_trail) if fvg_floor_premium is not None else pct_trail
        # v3.8 CLAMP: an FVG hugging price must not turn the leash into a
        # tripwire — the floor may never sit tighter than
        # FVG_FLOOR_MAX_LOCK_PCT of current premium.
        new_trail = min(new_trail, current_premium * FVG_FLOOR_MAX_LOCK_PCT)

        current_trail = self._trail_stops.get(trade_id, entry_prem)
        if new_trail > current_trail:
            self._trail_stops[trade_id] = new_trail
            logger.debug(
                f"FVG trail: {trade_id[:8]} trail=${self._trail_stops[trade_id]:.2f} "
                f"(fvg_based={fvg_floor_premium is not None})"
            )
        return self._trail_stops.get(trade_id)

    # ─── Sweep Reversal Exit ──────────────────────────────────────────────────

    def _evaluate_sweep(self, record: TradeRecord,
                         current_premium: float,
                         df_1m: Optional[pd.DataFrame],
                         df_5m: Optional[pd.DataFrame] = None) -> ExitDecision:
        """
        Sweep reversal exit logic:
        - Hard stop: 25% premium loss
        - BOS: 1-min break of structure against position
        - TP: 100% of premium
        - Trail: activates at 50% TP
        """
        decision   = ExitDecision()
        trade_id   = record["trade_id"]
        entry_prem = record["entry_premium"]
        stop_prem  = record["stop_premium"]
        target     = record["target_premium"]
        trail_act  = record["trail_activation"]
        direction  = record.get("direction", "long")

        pnl_pct = (current_premium - entry_prem) / entry_prem if entry_prem > 0 else 0
        pnl_usd = (current_premium - entry_prem) * record["contracts"] * CONTRACT_MULTIPLIER
        decision.current_pnl_pct = pnl_pct
        decision.current_pnl_usd = pnl_usd

        # 1. HARD CLOSE
        if is_hard_close_time():
            decision.should_exit = True
            decision.exit_reason = "hard_close_15:45_ET"
            return decision

        # 2. HARD STOP
        if current_premium <= stop_prem:
            decision.should_exit = True
            decision.exit_reason = f"stop_hit pnl={pnl_pct:.1%}"
            return decision

        # 3. TARGET — v3.8 RUNNER MODE (SWEEP_POST_TARGET_TRAIL, default on):
        #    sweeps get the same post-target treatment as ORB — no hard TP,
        #    the trade switches to the tightened FVG-aware trail and runs
        #    until the market takes some back. This was the ONE hard
        #    take-profit among directionals; env OT_SWEEP_POST_TARGET_TRAIL=
        #    False restores the +100% target_hit for A/B.
        if current_premium >= target:
            if not SWEEP_POST_TARGET_TRAIL:
                decision.should_exit = True
                decision.exit_reason = f"target_hit pnl={pnl_pct:.1%}"
                return decision
            if not self._post_target_trail.get(trade_id, False):
                self._post_target_trail[trade_id] = True
                logger.info(f"SWEEP TARGET REACHED (runner mode, no hard exit): "
                            f"{trade_id[:8]} pnl={pnl_pct:.1%}")
            trail_stop = self._update_post_target_trail(
                trade_id, current_premium, record,
                self._fvg_frame(df_1m, df_5m), direction
            )
            if trail_stop is not None:
                if current_premium <= trail_stop:
                    decision.should_exit = True
                    decision.exit_reason = f"post_target_trail pnl={pnl_pct:.1%}"
                    return decision
                decision.new_trail_stop = trail_stop
            return decision

        # 4. BOS EXIT \u2014 only once premium is positive (don\'t BOS out of a
        #    healthy retest that hasn\'t moved yet)
        if df_1m is not None and pnl_pct > 0:
            tracker = self._get_bos_tracker(trade_id, direction, entry_prem)
            if tracker.update(df_1m):
                decision.should_exit = True
                decision.exit_reason = f"bos_exit pnl={pnl_pct:.1%}"
                return decision

        # 4b. THETA BLEED \u2014 profitable but time is about to eat the gain
        if self._theta_bleed(record, current_premium, pnl_pct):
            decision.should_exit = True
            decision.exit_reason = f"theta_bleed pnl={pnl_pct:.1%}"
            return decision

        # 5. TRAIL \u2014 FVG-anchored once armed (+20%), plus the 50% % trail; the
        #    higher of the two governs (both write to _trail_stops).
        if pnl_pct >= FVG_TRAIL_ARM_PCT:
            self._update_fvg_trail(trade_id, current_premium, record,
                                   self._fvg_frame(df_1m, df_5m), direction)
        trail_stop = self._update_trail(
            trade_id, current_premium, entry_prem, trail_act, stop_prem
        )
        trail_stop = self._trail_stops.get(trade_id, trail_stop)
        if trail_stop is not None:
            if current_premium <= trail_stop:
                decision.should_exit = True
                decision.exit_reason = f"trail_stop_hit pnl={pnl_pct:.1%}"
                return decision
            decision.new_trail_stop = trail_stop

        return decision

    # \u2500\u2500\u2500 Butterfly Exit \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

    def _evaluate_butterfly(self, record: TradeRecord,
                             current_premium: float,
                             regime: Optional[str] = None) -> ExitDecision:
        """
        Butterfly exit logic:
        - Regime flip: exit immediately if regime flips to TRENDING
        - Max hold: 2.5 hours
        - Hard stop: net value <= 25% loss   (SL: 25% of net debit)
        - Target: BUTTERFLY_TP_PCT = 20% of max profit  (was documented as 25%)
        - No BOS, no trail
        """
        decision     = ExitDecision()
        trade_id     = record["trade_id"]
        entry_prem   = record["entry_premium"]
        stop_prem    = record["stop_premium"]
        target       = record["target_premium"]
        entry_time   = record["entry_time"]

        pnl_pct = (current_premium - entry_prem) / entry_prem if entry_prem > 0 else 0
        pnl_usd = (current_premium - entry_prem) * record["contracts"] * CONTRACT_MULTIPLIER
        decision.current_pnl_pct = pnl_pct
        decision.current_pnl_usd = pnl_usd

        # 1. HARD CLOSE
        if is_hard_close_time():
            decision.should_exit = True
            decision.exit_reason = "hard_close_15:45_ET"
            return decision

        # 2. REGIME FLIP EXIT — butterfly assumption (neutral/ranging) is broken
        # if the market transitions to a trending regime. Exit immediately rather
        # than waiting for the stop to get hit by the same directional move.
        TRENDING_REGIMES = {"TRENDING_BULL", "TRENDING_BEAR", "BREAKOUT_VOLATILE"}
        if regime and regime in TRENDING_REGIMES:
            decision.should_exit = True
            decision.exit_reason = f"regime_flip_exit: {regime} incompatible with butterfly"
            logger.info(
                f"BUTTERFLY REGIME EXIT: {trade_id[:8]} — "
                f"regime flipped to {regime}, exiting neutral position"
            )
            return decision

        # 3. MAX HOLD
        if entry_time:
            try:
                from datetime import timezone
                entry_dt = datetime.fromisoformat(entry_time)
                if entry_dt.tzinfo is None:
                    entry_dt = entry_dt.replace(tzinfo=timezone.utc)
                mins_held = minutes_since(entry_dt)
                if mins_held >= BUTTERFLY_MAX_HOLD_MIN:
                    decision.should_exit = True
                    decision.exit_reason = f"butterfly_max_hold({mins_held:.0f}min)"
                    return decision
            except Exception:
                pass

        # 3. HARD STOP
        if current_premium <= stop_prem:
            decision.should_exit = True
            decision.exit_reason = f"stop_hit pnl={pnl_pct:.1%}"
            return decision

        # 4. TARGET HIT
        if current_premium >= target:
            decision.should_exit = True
            decision.exit_reason = f"target_hit pnl={pnl_pct:.1%}"
            return decision

        return decision

    # \u2500\u2500\u2500 Shared Helpers \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

    def _condor_sibling_open(self, record) -> bool:
        """True if the OPPOSITE side of this symbol's condor is also open.

        The user's deconfliction rule used as a STATE CHECK: one leg open =
        standalone (take-profit applies); both open = a real condor (hold for
        the roll — the only reason to close one is the roll). Needs no
        look-ahead; structure state is knowable at every instant.
        On any error, returns True (treat as condor = do NOT take profit),
        because wrongly TPing a condor leg is the costlier mistake.
        """
        try:
            from database.trade_logger import get_trade_logger
            tl = get_trade_logger()
            if tl is None:
                return False
            me = record.get("option_side", "")
            for t in tl.get_open_trades():
                if (t.get("is_condor_leg")
                        and t.get("symbol") == record.get("symbol")
                        and t.get("trade_id") != record.get("trade_id")
                        and t.get("option_side") and t.get("option_side") != me):
                    return True
            return False
        except Exception:
            return True

    @staticmethod
    def _held_minutes(record) -> float:
        try:
            et = record.get("entry_time")
            if not et:
                return 0.0
            t = datetime.fromisoformat(str(et).replace("Z", "+00:00"))
            now = datetime.now(t.tzinfo) if t.tzinfo else datetime.now()
            return (now - t).total_seconds() / 60.0
        except Exception:
            return 0.0

    def _evaluate_condor_leg(self, record: TradeRecord,
                              current_premium: float,
                              regime: Optional[str] = None,
                              df_1m=None) -> ExitDecision:
        """
        Iron condor leg exit logic.
        Each leg is a credit spread — rising spread value = losing money.

        Regime-flip exits are DIRECTION-AWARE:
          - Call spread: only exit on TRENDING_BULL or BREAKOUT_VOLATILE
            (price moving toward short calls). TRENDING_BEAR is favorable — hold.
          - Put spread: only exit on TRENDING_BEAR or BREAKOUT_VOLATILE
            (price moving toward short puts). TRENDING_BULL is favorable — hold.
          - Leg 2 cancellation on favorable flips handled by check_leg_triggers().

        Exits: hard close, adverse regime flip, 25% stop, $0.05 nickel close.
        """
        from config import (CONDOR_NICKEL_CLOSE, CONDOR_STOP_LOSS_PCT,
                            CONDOR_RATCHET_BE_AT, CONDOR_RATCHET_LOCK_AT,
                            CONDOR_RATCHET_LOCK_PCT, CONDOR_TP_PCT,
                            CONDOR_RATCHET_STANDALONE_ONLY,
                            VERTICAL_HOLD_TO_ET, VERTICAL_HOLD_TO_CLOSE,
                            CONDOR_TP_MIN_HOLD_MIN, CONDOR_ENTRY_CUTOFF_ET)
        from utils.time_utils import ET

        decision    = ExitDecision()
        trade_id    = record["trade_id"]
        entry_prem  = record["entry_premium"]
        option_side = record.get("option_side", "")

        pnl_pct = (entry_prem - current_premium) / entry_prem if entry_prem > 0 else 0
        pnl_usd = (entry_prem - current_premium) * record["contracts"] * CONTRACT_MULTIPLIER
        decision.current_pnl_pct = pnl_pct
        decision.current_pnl_usd = pnl_usd

        # v4.17 — CREDIT VERTICALS ARE EXEMPT FROM THE 15:40 LADDER.
        # `is_hard_close_time()` opens at FLATTEN_WINDOW_OPEN (15:40) so a DEBIT
        # position gets a mark-limit phase before the 15:45 cross — and that
        # ladder is why it is NOT moved globally: opening it at 15:45 would
        # force every EOD exit marketable, the exact failure time_utils v3.8
        # fixed. A SHORT VERTICAL HAS THE OPPOSITE SIGN. It decays TOWARD the
        # holder, so 15:40-15:45 is the steepest part of its curve.
        # ⚠️ HELD TO 15:45 AND NOT PAST IT. Every instrument except SPX is
        # American-style and physically settled, so a spread finishing BETWEEN
        # the strikes assigns the short and leaves an unhedged overnight stock
        # position — "defined risk" is true at settlement, not through
        # assignment. The paper engine has no assignment model and would show a
        # clean result that does not survive going live.
        _vnow = datetime.now(ET)
        _vert_close = ((_vnow.hour, _vnow.minute) >= VERTICAL_HOLD_TO_ET
                       if VERTICAL_HOLD_TO_CLOSE else is_hard_close_time())
        if _vert_close:
            decision.should_exit = True
            decision.exit_reason = "hard_close_15:45_ET"
            return decision

        # ── TC.6 TREND CREDIT SPREAD — BREACH OR NICKEL, NOTHING ELSE ────
        # Operator's spec: "Exit should be breached (loss) or nickel close
        # (profit)." NO premium stop and NO ratchet, and that is not a
        # simplification — THE MEASURED EV WAS HELD TO EXPIRY, UNMANAGED
        # (+$0.52/spread, 90% terminal OK, 79% recovered on the ORB-anchored
        # runaway arm). A stop bolted on afterwards is a DIFFERENT TRADE with a
        # different expectancy, and paper results from it would not transfer.
        # BREACH is structural, not a premium percentage: a CLOSED BAR beyond
        # the broken ORB boundary. That is the same event `orb_structure_stop`
        # already calls thesis death, and the level the short strike was
        # anchored to — so structure and invalidation agree instead of arguing.
        # CLOSED bars only: an intraday wick through the boundary is a touch,
        # and the operator's own rule is that only a close decides acceptance.
        if is_trend_participation(record):
            _b = float(record.get("underlying_stop") or 0.0)
            _side = record.get("option_side", "")
            _last = None
            try:
                if df_1m is not None and not df_1m.empty:
                    _last = float(df_1m["close"].iloc[-1])
            except Exception:                                  # noqa: BLE001
                _last = None
            if _b > 0 and _last is not None:
                # put spread sits BELOW the boundary -> a close below breaches;
                # call spread sits ABOVE -> a close above breaches.
                _breached = (_last < _b) if _side == "put" else (_last > _b)
                if _breached:
                    decision.should_exit = True
                    decision.exit_reason = (
                        f"tcs_breach: close {_last:.2f} beyond boundary {_b:.2f}")
                    return decision
            elif _b > 0:
                # No tape: report it. A breach rule that cannot see price is
                # inert, and an inert stop must never look like a passing check.
                logger.warning("[tcs] no 1m tape — the breach rule is INERT "
                               "this tick (boundary %.2f)", _b)
            # ⚠️ NO NICKEL CLOSE. Operator, 2026-08-14: "There should be no
            # closing it short of a BREACH of that level or the SESSION HARD
            # CLOSE cutoff." This revises the earlier breach-or-nickel spec.
            # A nickel close is a PROFIT exit, and taking it caps a position
            # whose measured EV was HELD TO EXPIRY, UNMANAGED. The 15:45 close
            # above is the only other way out.
            # ⚠️ TERMINAL RETURN — THE WHOLE POINT OF THE BRANCH.
            # Without this the branch FALLS THROUGH to the ratchet and the 25%
            # condor stop below. Observed live 2026-08-14: a $0.06 credit sets
            # stop_premium at $0.07 (credit x 1.25), so ONE CENT of widening
            # closed the trade — every TC.6 leg on the fleet stopped out within
            # seconds. The measured EV was HELD TO EXPIRY, UNMANAGED; a premium
            # stop is a different trade.
            # The v1.0 test asserted the branch contained two `return decision`
            # statements. It did. It never exercised the path where NEITHER
            # breach NOR nickel fires — which is the path that was broken.
            return decision
            # No other exit applies: the 15:45 close is handled ABOVE, and
            # the ratchet / 25% stop / TP below are deliberately unreachable
            # for a trend credit spread.


        TRENDING_REGIMES = {"TRENDING_BULL", "TRENDING_BEAR", "BREAKOUT_VOLATILE"}
        if regime and regime in TRENDING_REGIMES:
            adverse = False
            if option_side == "call" and regime in ("TRENDING_BULL", "BREAKOUT_VOLATILE"):
                adverse = True
            elif option_side == "put" and regime in ("TRENDING_BEAR", "BREAKOUT_VOLATILE"):
                adverse = True

            if adverse:
                decision.should_exit = True
                decision.exit_reason = f"regime_flip_adverse: {regime} threatens {option_side} spread"
                logger.info(
                    f"CONDOR LEG ADVERSE EXIT: {trade_id[:8]} — "
                    f"{regime} moving into {option_side} short strikes"
                )
                return decision
            else:
                logger.info(
                    f"CONDOR LEG: {regime} flip FAVORABLE for {option_side} spread "
                    f"(pnl={pnl_pct:.1%}) — holding, Leg 2 will be cancelled by strategy"
                )

        # ── RATCHETING STOP (v4.1) ────────────────────────────────────────
        # Every stopped leg in the 07-07..07-22 sample was GREEN FIRST (median
        # peak +24% pre-fix / +31% post) then round-tripped into the -25% stop.
        # Nothing existed between entry and the $0.05 nickel close to keep any
        # of it. This moves the STOP and never closes the leg, so the position
        # stays alive to reach the far band and complete the structure.
        base_stop  = entry_prem * (1 + CONDOR_STOP_LOSS_PCT)
        stop_level = base_stop
        tier = ""
        if pnl_pct >= CONDOR_RATCHET_LOCK_AT:
            stop_level = min(stop_level, entry_prem * (1 - CONDOR_RATCHET_LOCK_PCT))
            tier = f" [locked +{CONDOR_RATCHET_LOCK_PCT:.0%}]"
        elif pnl_pct >= CONDOR_RATCHET_BE_AT:
            stop_level = min(stop_level, entry_prem)
            tier = " [breakeven]"
        # ── RATCHET SCOPE (v4.2, 2026-08-13 operator ruling) ──────────────
        # "the ratchet is inappropriate for this trade if the condor is fully
        #  formed. It should only be in effect if there's one side open."
        # THE BASE STOP ONLY FIRES ON THE TESTED SIDE — spread value rises as
        # price approaches your short. The RATCHET is the opposite: it tightens
        # the UNTESTED side precisely BECAUSE it is winning, so on a reversal
        # the tested leg stops at -25% and the untested leg hits its ratcheted
        # stop too. A leg price never went near, closed by a stop that exists
        # only because it was profitable. That is the double-stop (5 of 14
        # condor symbol-days), and it fires BEFORE the roll can be used because
        # the roll needs a tested side.
        # `_condor_sibling_open` FAILS CLOSED (True on error) — treating a leg
        # as part of a structure is the safe error here, and it is the same
        # interlock the take-profit already uses.
        _formed = (CONDOR_RATCHET_STANDALONE_ONLY
                   and self._condor_sibling_open(record))
        if _formed:
            # base floor ONLY. No tier, no stored high-water — and the stored
            # value is deliberately NOT updated while formed, so a leg returning
            # to standalone resumes from the high-water it genuinely earned
            # rather than one set while the structure was intact.
            stop_level, tier = base_stop, " [formed: base only]"
        else:
            prev = self._condor_ratchet.get(trade_id)
            if prev is None:
                # v4.21 (AUDIT F4) — RESTART RECOVERY. The earned ratchet lived
                # ONLY in this dict; every bake reset an earned breakeven/+20%
                # lock to the base -25% stop. Seed from the trail_stop column
                # (written via new_trail_stop below). Only a value BELOW
                # base_stop can be a real condor ratchet — anything else is
                # stale/foreign and ignored.
                try:
                    _persisted = float(record.get("trail_stop", 0.0) or 0.0)
                except (TypeError, ValueError):
                    _persisted = 0.0
                if 0.0 < _persisted < base_stop:
                    prev = _persisted
            if prev is not None:
                stop_level = min(stop_level, prev)  # ratchet only ever tightens
            self._condor_ratchet[trade_id] = stop_level
            if stop_level < base_stop and (prev is None or stop_level < prev):
                # v4.21 (F4): persist the earned level through the SAME channel
                # the directional trails use. Emitted only when it tightened,
                # and only on this standalone branch — the formed branch above
                # deliberately neither applies nor updates the stored value.
                decision.new_trail_stop = stop_level

        if current_premium >= stop_level:
            decision.should_exit = True
            decision.exit_reason = f"condor_stop pnl={pnl_pct:.1%}{tier}"
            return decision

        # ── TIME-GATED TAKE PROFIT (v4.1) ─────────────────────────────────
        # ONLY after the entry cutoff (structure definitively dead) and ONLY on
        # a standalone. A TP before the cutoff would guarantee the condor never
        # forms: the move that makes side one profitable IS the move that
        # carries price to the far band to trigger side two.
        if pnl_pct >= CONDOR_TP_PCT and not self._condor_sibling_open(record):
            now_et = datetime.now(ET)
            if ((now_et.hour, now_et.minute) >= CONDOR_ENTRY_CUTOFF_ET
                    and self._held_minutes(record) >= CONDOR_TP_MIN_HOLD_MIN):
                decision.should_exit = True
                decision.exit_reason = f"condor_tp pnl={pnl_pct:.1%} (standalone, post-cutoff)"
                return decision

        if current_premium <= CONDOR_NICKEL_CLOSE:
            decision.should_exit = True
            decision.exit_reason = f"nickel_close pnl={pnl_pct:.1%}"
            return decision

        return decision

    def _evaluate_adopted(self, record: TradeRecord,
                          current_premium: float) -> ExitDecision:
        """
        Exit logic for an ADOPTED position — one discovered open at the broker on
        a LIVE restart with no DB plan (see broker_reconcile). The original setup
        is unknown, so it is managed by the universal core of our rules:
          - sign-correct max-loss stop (already on the record as stop_premium:
            long = entry*(1-ADOPTED_STOP_PCT); short = entry*(1+ADOPTED_STOP_PCT)),
          - long positions also trail to lock gains (standard trail helper),
          - the 15:45 hard close applies like everything else.
        A position already past its stop when adopted exits on the first tick; a
        healthy one rides. That is the "if red exit, if green manage" behaviour,
        via the normal exit path — no strategy-specific context required.

        A lone adopted SHORT (an anomaly per the account's margin reality) is
        held on a fixed protective stop + hard close only; no ratcheting trail.
        """
        decision   = ExitDecision()
        trade_id   = record["trade_id"]
        entry_prem = record.get("entry_premium", 0) or 0
        stop_prem  = record.get("stop_premium", 0) or 0
        contracts  = record.get("contracts", 0) or 0
        is_short   = bool(record.get("is_short_position", 0))

        # sign-correct P&L: a long gains as premium rises, a short as it falls
        if is_short:
            pnl_pct = (entry_prem - current_premium) / entry_prem if entry_prem > 0 else 0
            pnl_usd = (entry_prem - current_premium) * contracts * CONTRACT_MULTIPLIER
        else:
            pnl_pct = (current_premium - entry_prem) / entry_prem if entry_prem > 0 else 0
            pnl_usd = (current_premium - entry_prem) * contracts * CONTRACT_MULTIPLIER
        decision.current_pnl_pct = pnl_pct
        decision.current_pnl_usd = pnl_usd

        # 1. HARD CLOSE (also enforced by the 15:45 flatten — belt & suspenders)
        if is_hard_close_time():
            decision.should_exit = True
            decision.exit_reason = "hard_close_15:45_ET"
            return decision

        # 2. MAX-LOSS STOP (sign-correct)
        if is_short:
            if stop_prem > 0 and current_premium >= stop_prem:
                decision.should_exit = True
                decision.exit_reason = f"adopted_stop_short pnl={pnl_pct:.1%}"
            # anomalous short: fixed stop + hard close only, no ratcheting trail
            return decision

        if stop_prem > 0 and current_premium <= stop_prem:
            decision.should_exit = True
            decision.exit_reason = f"adopted_stop_long pnl={pnl_pct:.1%}"
            return decision

        # 3. LONG PROFIT TRAIL — once up TRAIL_ACTIVATION_PCT, arm a ratcheting
        #    stop that locks gains and PERSISTS: a pullback to the locked level
        #    exits (unlike the shared _update_trail, which de-arms below the
        #    activation threshold). Ratchets to TRAIL_LOCK_PCT below the high.
        if (not self._trail_active.get(trade_id, False)
                and pnl_pct >= TRAIL_ACTIVATION_PCT):
            self._trail_active[trade_id] = True
            self._trail_stops[trade_id] = entry_prem * (1 + TRAIL_LOCK_PCT)

        if self._trail_active.get(trade_id, False):
            ratchet = current_premium * (1 - TRAIL_LOCK_PCT)
            trail   = max(self._trail_stops.get(trade_id, stop_prem), ratchet)
            self._trail_stops[trade_id] = trail
            decision.new_trail_stop = trail
            if current_premium <= trail:
                decision.should_exit = True
                decision.exit_reason = f"adopted_trail pnl={pnl_pct:.1%}"

        return decision

    def _get_bos_tracker(self, trade_id: str,
                          direction: str,
                          entry_price: float,
                          min_dist: float = 0.0) -> BOSTracker:
        """v4.15 — `min_dist` defaults to 0.0 so every existing caller is
        byte-identical in behaviour. It is supplied ONLY by the continuation
        path, which seeds with `underlying_entry` and can therefore express a
        distance in ATR (underlying) units.

        ⚠️ DO NOT PASS min_dist FROM THE GENERIC/ORB CALLER AT ~966 WITHOUT
        FIXING IT FIRST: that site seeds with `entry_prem` — the OPTION premium
        — and BOSTracker compares against df_1m UNDERLYING closes. A ~$1.26
        premium against ~$352 closes means the very first bar always beats
        `peak_close`, so that path seeds a protected level immediately on bar
        one regardless of structure. Pre-existing, out of scope here, and
        recorded rather than silently patched — an ATR distance in premium
        units would be meaningless anyway."""
        if trade_id not in self._bos_trackers:
            self._bos_trackers[trade_id] = BOSTracker(direction, entry_price,
                                                      min_dist=min_dist)
        return self._bos_trackers[trade_id]

    def _update_trail(self, trade_id: str,
                       current: float, entry: float,
                       trail_activation: float,
                       hard_stop: float) -> Optional[float]:
        if current < trail_activation:
            return None

        if not self._trail_active.get(trade_id, False):
            self._trail_active[trade_id] = True
            initial_trail = entry * (1 + TRAIL_LOCK_PCT)
            self._trail_stops[trade_id] = initial_trail
            logger.info(
                f"TRAIL ACTIVATED: {trade_id[:8]} "
                f"initial_trail=${initial_trail:.2f}"
            )

        current_trail = self._trail_stops.get(trade_id, hard_stop)
        new_trail     = current * 0.75
        if new_trail > current_trail:
            self._trail_stops[trade_id] = new_trail

        return self._trail_stops[trade_id]

    # ─── Continuation (trend-pullback) Exit — EXHAUSTION-BASED ────────────────
    #
    # This is where the continuation trade lives or dies. Entry is deliberately a
    # low bar; the intelligence is here. The move is ridden while it has energy
    # and cut when it's SPENT — which is a different question than "was I proven
    # wrong" (that's the regime-flip / 40% floor below). Two exhaustion signals:
    #
    #   (1) EXTENSION-FROM-MIDLINE  — price stretched an abnormal distance from
    #       the BB midline (its mean). Cheap, early, stateless. FIRST TIER:
    #       tightens the trail hard (protect the stretched gain) but does NOT
    #       exit — a strong trend can stay extended.
    #   (2) MOMENTUM DIVERGENCE     — price prints a new run-favorable extreme
    #       while momentum (5m rate-of-change) is WEAKER than at the prior
    #       extreme: the move is continuing on fumes. CONFIRMATION: exits.
    #
    # COMBINE MODE (v1 = two-stage): extension tightens, divergence exits.
    #   ── NOTE TO FUTURE-SELF ─────────────────────────────────────────────
    #   A stricter "mode 3" was discussed and intentionally deferred: require
    #   BOTH signals to agree before exiting (divergence AND extension), which
    #   maps closer to how the operator actually trades — you don't bail on
    #   divergence alone if the move isn't also stretched. v1 ships the safer
    #   two-stage form (divergence-alone can exit). If you're reading this
    #   because you're reconsidering exits: the hook is the `_exhausted` combine
    #   step below — gate the exit on (divergence and extended) instead of
    #   (divergence) to become mode 3. Left as a code change, not a live flag,
    #   by the operator's request (they don't expect to touch it).
    #   ────────────────────────────────────────────────────────────────────
    #
    # ENGINE STATE: prefers the live vol_state/trend threaded from main.py (exact
    # — same midline/momentum the entry judged against). Falls back to values
    # RECOMPUTED from df_5m when the state isn't available (restart recovery,
    # adopted positions) so this NEVER raises — it only degrades precision.
    def _evaluate_continuation(self, record: TradeRecord,
                               current_premium: float,
                               df_1m: Optional[pd.DataFrame],
                               df_5m: Optional[pd.DataFrame] = None,
                               regime: Optional[str] = None,
                               vol_state=None,
                               trend=None) -> ExitDecision:
        decision   = ExitDecision()
        trade_id   = record["trade_id"]
        entry_prem = record["entry_premium"]
        direction  = record.get("direction", "long")

        pnl_pct = (current_premium - entry_prem) / entry_prem if entry_prem > 0 else 0
        pnl_usd = (current_premium - entry_prem) * record["contracts"] * CONTRACT_MULTIPLIER
        decision.current_pnl_pct = pnl_pct
        decision.current_pnl_usd = pnl_usd

        # 1. HARD CLOSE (session end)
        if is_hard_close_time():
            decision.should_exit = True
            decision.exit_reason = "hard_close_15:45_ET"
            return decision

        # 2. REGIME-FLIP EXIT — the primary smart stop. The trade is DEFINED by
        #    the trend; if regime is no longer trending in our direction, the
        #    thesis is dead regardless of P&L. (regime is a string here.)
        rgm = (regime or "").upper()
        # ⚠️ CNT.1 SHIPPED HALF A FEATURE (2026-08-07) AND THIS IS THE OTHER
        # HALF. The entry branch lets continuation OPEN on BREAKOUT_VOLATILE —
        # taking direction from the trend vote instead of the label, gated on
        # ADX — and produces setup_type `trend_continuation_breakout`. This test
        # never learned about it, so such a trade was **BORN ALREADY FAILING ITS
        # OWN EXIT CONDITION**: it opens on tick N with the label at
        # BREAKOUT_VOLATILE, and on tick N+1 this reads the SAME UNCHANGED label,
        # finds it is not TRENDING_BULL/BEAR, and closes as `regime_flip`.
        # THE LABEL NEVER FLIPPED.
        # Measured live 2026-08-14: 15-SECOND holds — exactly one tick —
        # repeating for as long as the setup stayed valid. SMH 14:24:19->14:24:34,
        # re-enter 14:24:49->14:25:04, eight times. P&L was symmetric noise
        # because the hold is one tick of random walk minus the spread (SMH's
        # eight netted -$29; GS's eight netted +$331 on the same mechanism).
        # This block sits BEFORE `bos_exit`, so it fired first and nothing else
        # ever got a look.
        # A breakout continuation must live or die on the TREND VOTE it was born
        # from, not on a label test it was never able to pass.
        # ── AUDIT F7 (2026-08-15) — THE BREAKOUT EXEMPTION WAS ASYMMETRIC ────
        # v4.19 scoped `BREAKOUT_VOLATILE` survival to `_breakout` records only,
        # to avoid over-reaching. That created a worse problem: **a STANDALONE
        # or HANDOFF continuation riding TRENDING_BULL that ACCELERATES into
        # BREAKOUT_VOLATILE — the strongest tape in its own direction — was
        # closed as a `regime_flip`, while a breakout record survived the
        # IDENTICAL TAPE.** Same market, opposite decision, on setup_type alone.
        #
        # ⚠️ AND BREAKOUT_VOLATILE CARRIES NO DIRECTION. v4.19's own comment says
        # a breakout continuation must live or die on the TREND VOTE — but the
        # code tested the LABEL, so a long survived a violent move DOWN. The
        # vote is already a parameter here and is the only directional evidence
        # available, so it decides.
        _vote = str(getattr(trend, "overall_direction", "") or "").upper()
        _vote_agrees = ((direction == "long" and _vote == "BULLISH")
                        or (direction == "short" and _vote == "BEARISH"))
        still_trending = (
            (direction == "long"  and "TRENDING_BULL" in rgm) or
            (direction == "short" and "TRENDING_BEAR" in rgm) or
            # ANY continuation survives a breakout that is still going ITS WAY.
            ("BREAKOUT_VOLATILE" in rgm and _vote_agrees)
        )
        if regime is not None and not still_trending:
            decision.should_exit = True
            decision.exit_reason = f"regime_flip ({regime})"
            return decision

        # 2b. BREAK OF STRUCTURE (v4.10) — the structural stop continuation
        #     never had. Operator's rule: the trade is defined by the trend, so
        #     the trend's structure failing is the exit — not a premium level.
        #     BOSTracker ratchets: every new closing high (long) promotes that
        #     candle's LOW to the protected higher-low; a 1m CLOSE below it means
        #     the HH/HL sequence is broken. Mirrors for shorts on closing lows /
        #     protected lower-high. Uses iloc[-2], the last FULLY CLOSED candle.
        #
        #     UNGATED, deliberately. Sweep's copy of this exit is gated on
        #     `pnl_pct > 0` ("don't BOS out of a healthy retest that hasn't moved
        #     yet"). That gate is exactly what would MISS the failure mode this is
        #     for: measured 2026-07-31, 31 continuation trades ran from entry
        #     straight to the -25% floor with MFE of only 2-3% — they never went
        #     positive, so a profit-gated BOS would never have fired. Gates 4
        #     (theta bleed) and 5 (trail) already require the trade to have worked
        #     first; a third such gate would leave the same hole.
        #
        #     CHOSEN OVER THE FVG STOP. `underlying_stop` is stamped on the record
        #     (gap.bottom - 0.5*atr for longs) and has never been read, but a gap
        #     fill is NOT trend failure — gaps fill routinely inside healthy
        #     trends. The FVG level is also STATIC, fixed at entry, so it protects
        #     nothing once the trade works. BOS is dynamic: the protected level
        #     ratchets up as the trend makes new highs, so it invalidates on
        #     actual structure failure and trails the gain structurally. The FVG
        #     remains the ENTRY (proven repeatedly on 2026-07-31); it is not the
        #     exit.
        # v4.14 — `_bos` is created unconditionally so gate 2c can read its
        # `protected_level`. Previously it was constructed inside the df_1m
        # guard; leaving it there would make 2c reference an unbound name on a
        # tick with no 1m frame — the same NameError class as defect W.
        # v4.15 — floor the protected level at BOS_MIN_DIST_ATR * ATR from
        # entry, so it can never be seeded inside the symbol's own noise band.
        _bm, _batr = self._midline_atr(vol_state, df_5m)
        _bos_min = (BOS_MIN_DIST_ATR * float(_batr)) if (_batr and _batr > 0) else 0.0
        _bos = self._get_bos_tracker(trade_id, str(record.get("direction", "")).lower(),
                                     float(record.get("underlying_entry", 0.0) or 0.0),
                                     min_dist=_bos_min)
        if df_1m is not None:
            if _bos.update(df_1m):
                decision.should_exit = True
                decision.exit_reason = f"bos_exit pnl={pnl_pct:.1%}"
                return decision

        # 2c. INSURANCE (v4.14, CNT.2) — the ONLY gate that covers BOS's blind
        #     window. `BOSTracker.protected_level` starts None and is set only
        #     when the trade makes a new CLOSING HIGH past entry, so 2b above
        #     cannot fire on a trade that went wrong from the first tick — which
        #     is precisely the population that runs to the floor at −29% with
        #     MFE +1%.
        #
        #     ARMED ONLY WHILE `protected_level is None`, so the handoff is
        #     EXACT and needs no time window: the instant BOS has a level to
        #     defend, BOS owns the trade and this disarms permanently. No
        #     overlap, no double jeopardy.
        #
        #     THE LEVEL IS STRUCTURAL, NOT PREMIUM. `underlying_stop` is stamped
        #     at entry by continuation_strategy:447/450 as
        #     gap.bottom − 0.5*atr (long) / gap.top + 0.5*atr (short) and until
        #     now was read ONLY by query.py for display. A premium-percent stop
        #     on 0DTE measures gamma, not thesis — the floor sweep proved a
        #     tighter one nets ~zero because it cuts winners that merely dip.
        #     This is the ENTRY PREMISE INVERTED: continuation enters on a
        #     pullback INTO an unfilled 5m FVG expecting resumption, so a close
        #     beyond the far edge plus a half-ATR buffer means the pullback was
        #     the reversal continuing.
        #
        #     Uses iloc[-2] — the last FULLY CLOSED 1m candle — the same bar BOS
        #     reads, so the two gates can never disagree about what price did.
        if (CONT_INSURANCE_STOP and df_1m is not None and len(df_1m) >= 2
                and _bos.protected_level is None):
            _ins = float(record.get("underlying_stop", 0.0) or 0.0)
            if _ins > 0:
                _dirn = str(record.get("direction", "")).lower()
                _close = float(df_1m["close"].iloc[-2])
                _broke = (_close < _ins) if _dirn == "long" else (_close > _ins)
                if _broke:
                    decision.should_exit = True
                    decision.exit_reason = (
                        f"insurance_stop pnl={pnl_pct:.1%} "
                        f"close={_close:.2f} lvl={_ins:.2f}")
                    return decision

        # 3. HARD FLOOR — 25% premium loss (v4.0; was the blanket 40%).
        #    Disaster backstop only: regime-flip above is the real stop and
        #    normally fires first. Existing rows keep the stop_premium written
        #    at entry; the fallback is the continuation-specific pct.
        stop_prem = record.get("stop_premium", 0.0) or (entry_prem * (1 - CONTINUATION_STOP_LOSS_PCT))
        if stop_prem > 0 and current_premium <= stop_prem:
            decision.should_exit = True
            floor_pct = 1 - (stop_prem / entry_prem) if entry_prem > 0 else MAX_LOSS_PCT
            decision.exit_reason = f"max_loss_floor_{int(floor_pct*100)}pct"
            return decision

        # ── EXHAUSTION SIGNALS ────────────────────────────────────────────────
        underlying = self._underlying_from_5m(df_5m)   # last close, or None

        # (1) EXTENSION-FROM-MIDLINE
        midline, atr = self._midline_atr(vol_state, df_5m)
        extended = False
        if underlying is not None and midline is not None and atr and atr > 0:
            stretch_atr = abs(underlying - midline) / atr
            extended = stretch_atr >= CONTINUATION_EXHAUST_EXT_ATR

        # (2) MOMENTUM DIVERGENCE — new favorable price extreme on weaker momentum
        diverging = self._momentum_divergence(trade_id, record, underlying,
                                              direction, trend, df_5m)

        # ── COMBINE (v1 two-stage) ────────────────────────────────────────────
        # Only manage exhaustion once the trade has a real gain to protect (mirror
        # the runner philosophy — don't exhaust-exit a trade that hasn't worked).
        if pnl_pct >= CONTINUATION_EXHAUST_MIN_GAIN:
            if diverging:
                # CONFIRMATION → exit. (mode-3 hook: `and extended`)
                decision.should_exit = True
                decision.exit_reason = "exhaustion_divergence" + ("_extended" if extended else "")
                return decision
            if extended:
                # FIRST TIER → tighten the trail hard, keep riding.
                new_trail = current_premium * CONTINUATION_EXHAUST_TRAIL_LOCK
                cur = self._trail_stops.get(trade_id, entry_prem)
                if new_trail > cur:
                    self._trail_stops[trade_id] = new_trail
                    decision.new_trail_stop = new_trail

        # 4. THETA BLEED (v4.0) — the stalled-winner exit. Four gates live
        #    inside _theta_bleed and are unchanged, including the 20-MINUTE
        #    MIN-HOLD blackout the user asked for. Its active window is a gain
        #    in [THETA_MIN_GAIN_PCT, FVG_TRAIL_ARM_PCT) with the trail not yet
        #    armed — i.e. a small winner going nowhere while the clock eats it.
        #    Sits AFTER exhaustion on purpose: where the two windows overlap, a
        #    momentum divergence is the more informative reason to leave, and
        #    it gives the L3 ledger the better exit_reason.
        if self._theta_bleed(record, current_premium, pnl_pct):
            decision.should_exit = True
            decision.exit_reason = f"theta_bleed pnl={pnl_pct:.1%}"
            return decision

        # 5. STANDARD RUNNER TRAIL — arms on the resumption gain, then owns the
        #    trade (this is also what silences theta via the v1.5 trail ceiling).
        #    v4.0: anchored to 5m FVGs via _fvg_frame (was raw df_1m).
        trail_stop = self._update_fvg_trail(trade_id, current_premium, record,
                                            self._fvg_frame(df_1m, df_5m),
                                            direction)
        if trail_stop is not None:
            decision.new_trail_stop = max(decision.new_trail_stop or 0.0, trail_stop)
            if current_premium <= trail_stop:
                decision.should_exit = True
                decision.exit_reason = "continuation_trail"
                return decision

        return decision

    # ─── Exhaustion helpers (self-contained; live-state-preferred) ────────────
    def _underlying_from_5m(self, df_5m: Optional[pd.DataFrame]) -> Optional[float]:
        if df_5m is None or len(df_5m) == 0:
            return None
        try:
            return float(df_5m["close"].iloc[-1])
        except Exception:
            return None

    def _midline_atr(self, vol_state, df_5m):
        """Prefer live vol_state; else recompute midline (20-SMA 5m close) + ATR."""
        midline = None
        atr = None
        if vol_state is not None:
            midline = getattr(vol_state, "bb_middle", None) or None
            atr = getattr(vol_state, "atr_current", None) or None
        if (midline is None or atr is None) and df_5m is not None and len(df_5m) >= 20:
            try:
                midline = float(df_5m["close"].tail(20).mean())
                tr = (df_5m["high"] - df_5m["low"]).tail(14)
                atr = float(tr.mean())
            except Exception:
                pass
        return midline, atr

    def _momentum_divergence(self, trade_id, record, underlying, direction,
                             trend, df_5m) -> bool:
        """
        True when price makes a NEW run-favorable extreme but momentum is weaker
        than it was at the prior extreme. Momentum = live trend reading if given,
        else 5m rate-of-change. State (last extreme + its momentum) is carried in
        self._exhaust_state per trade_id.
        """
        if underlying is None:
            return False
        # momentum reading: prefer a numeric from df_5m ROC (comparable across
        # extremes); the live `trend` object gives a categorical we can't diff.
        mom = None
        if df_5m is not None and len(df_5m) >= 6:
            try:
                c = df_5m["close"]
                mom = float(c.iloc[-1] - c.iloc[-6])  # 5-bar ROC
            except Exception:
                mom = None
        if mom is None:
            return False

        st = self._exhaust_state.setdefault(trade_id, {"ext": None, "mom": None})
        favorable_new_extreme = (
            st["ext"] is None or
            (direction == "long"  and underlying > st["ext"]) or
            (direction == "short" and underlying < st["ext"])
        )
        diverged = False
        if favorable_new_extreme:
            # new extreme: does momentum confirm or diverge vs the prior extreme?
            if st["mom"] is not None:
                if direction == "long":
                    diverged = mom < st["mom"] and mom <= 0
                else:
                    diverged = mom > st["mom"] and mom >= 0
            st["ext"] = underlying
            st["mom"] = mom
        return diverged

    def place_exit_order(self, record: TradeRecord, reason: str,
                         mark_price: Optional[float] = None) -> FillResult:
        """Place a closing order and return a FillResult (the shared paper/live
        contract). NEVER returns a bare success bool anymore: a close is only
        'done' when FillResult.confirmed is True AND fill_price is a real price.

        mark_price is the last-known mark for this position (spread value for a
        condor leg, net debit for a butterfly, single mark otherwise), supplied
        by position_manager. In PAPER it becomes the simulated fill price. In
        LIVE it is context only — the booked price MUST be the broker's actual
        fill, never this mark.
        """
        mode      = "PAPER" if self.paper_trading else "LIVE"
        trade_id  = record["trade_id"]
        contracts = record["contracts"]

        logger.info(f"[{mode}] CLOSING {trade_id[:8]}: {reason} contracts={contracts}")

        # ── N.5 (v4.11) — latency telemetry, log-only ────────────────────────
        # Stamped BEFORE dispatch so the submit instant is the submit instant,
        # not a value reconstructed after the fact. Set once per close attempt
        # and kept on the RECORD: a live close is multi-tick and the next tick
        # resumes the same order, so this must survive the pass boundary.
        if not record.get("_exit_submit_ts"):
            record["_exit_submit_ts"] = ts_for_db()
            record["_exit_submit_mono"] = time.monotonic()
            # The mark at TRIGGER — the price the exit decision saw. This is
            # the number the ladder's cost is measured against; None when no
            # mark was available, which is honest and must not become 0.0.
            record["_exit_mark_at_trigger"] = (
                float(mark_price) if mark_price is not None and mark_price >= 0
                else None)
        record["_exit_passes"] = int(record.get("_exit_passes", 0)) + 1
        # ESCALATED means the close needed more than a plain limit-at-mark post.
        # Two disjoint causes, either sufficient: the 15:45 hard-close market
        # cross, or the live loop hitting its deadline and cancelling (set at
        # that branch). Both are "the ladder did not simply fill".
        try:
            if hard_close_order_mode(now_et()) == "market":
                record["_exit_escalated"] = 1
        except Exception as exc:                             # noqa: BLE001
            # W.2: this sat in TIER 1 (risk/orders/record) as a bare `pass` —
            # the census's whole purpose. DEBUG, once per process, so a broken
            # escalation flag is findable without ever touching the close.
            if "n5-escalation" not in _telemetry_logged:
                _telemetry_logged.add("n5-escalation")
                logger.debug("N.5 escalation flag failed (%s: %s) — telemetry "
                             "only, the close is unaffected",
                             type(exc).__name__, exc)

        # ── PAPER: simulate the fill at the last-known mark and CONFIRM it ──────
        # A simulated close always succeeds on the first pass — there is no
        # broker, nothing to poll, nothing to reuse. If we have no mark we cannot
        # invent a price, so we decline (confirmed=False) rather than book a fake
        # one; the caller will try again next tick with a fresh mark.
        if self.paper_trading:
            if mark_price is None or mark_price < 0:
                logger.warning(f"[PAPER] {trade_id[:8]}: no mark available — "
                               f"cannot simulate a fill this pass, will retry")
                return FillResult(confirmed=False, detail="paper: no mark yet")
            logger.info(f"[PAPER] Simulated fill {trade_id[:8]} @ {mark_price:.2f}")
            return self._stamp_exit_latency(
                record,
                FillResult(confirmed=True, fill_price=float(mark_price),
                           detail="paper simulated fill"))

        # ── LIVE: submit, then book ONLY on broker-confirmed fill ──────────────
        # v3.5: implemented. Places the order, captures its id, polls the broker
        # to a bounded deadline, and returns confirmed=True with the REAL net
        # fill price — or confirmed=False (position stays open, retries and
        # escalates). See _confirm_and_book_live_exit and the Fable spec.
        return self._stamp_exit_latency(
            record, self._confirm_and_book_live_exit(record, reason, mark_price))

    def _stamp_exit_latency(self, record: TradeRecord,
                            result: FillResult) -> FillResult:
        """N.5 (v4.11) — write the ladder telemetry, then return the result
        UNCHANGED. Log-only: it is a pass-through by construction, so no exit
        path can be altered by it even if it fails.

        Writes ONLY on a confirmed close. An unconfirmed pass leaves the state
        on the record so the NEXT pass keeps accumulating against the same
        submit instant — that is the whole point of a ladder measurement, and
        booking a row per unconfirmed pass would report the fast half of every
        slow close.
        """
        try:
            if not result or not result.confirmed:
                return result
            submit_ts = record.get("_exit_submit_ts")
            if not submit_ts:
                return result
            mono = record.get("_exit_submit_mono")
            latency_ms = int(max(0.0, (time.monotonic() - mono)) * 1000) if mono else 0
            wrote = self._trade_logger.set_exit_latency(
                trade_id       = record.get("trade_id", ""),
                submit_ts      = submit_ts,
                fill_ts        = ts_for_db(),
                latency_ms     = latency_ms,
                ladder_steps   = int(record.get("_exit_passes", 1)),
                escalated      = bool(record.get("_exit_escalated", 0)),
                mark_at_trigger= record.get("_exit_mark_at_trigger"),
            )
            if not wrote and "latency-write" not in self._live_exit_alerted:
                # Once per process, not once per close: a per-exit warning is
                # spam and gets filtered, which is how a dead capture hides.
                self._live_exit_alerted.add("latency-write")
                logger.warning(
                    "N.5 exit-latency row NOT written for %s — these closes "
                    "cannot enter the TC.2 stop-trigger dataset (logged once "
                    "per process)", record.get("trade_id", "")[:8])
        except Exception as exc:                             # noqa: BLE001
            logger.warning("N.5 exit-latency capture failed (%s: %s) — the "
                           "close itself is unaffected",
                           type(exc).__name__, exc)
        return result

    # ── LIVE FILL-CONFIRMATION (v3.5) ────────────────────────────────────────
    # States in which an order is still working at the broker.
    _WORKING_STATES = {
        OrderStatus.RECEIVED, OrderStatus.ROUTED, OrderStatus.IN_FLIGHT,
        OrderStatus.LIVE, OrderStatus.CONTINGENT,
        OrderStatus.CANCEL_REQUESTED, OrderStatus.REPLACE_REQUESTED,
    }
    # Terminal states that are NOT a full fill (may still carry partial fills).
    _DEAD_STATES = {
        OrderStatus.CANCELLED, OrderStatus.EXPIRED,
        OrderStatus.REMOVED, OrderStatus.PARTIALLY_REMOVED,
    }

    def _confirm_and_book_live_exit(self, record: TradeRecord, reason: str,
                                    mark_price: Optional[float]) -> FillResult:
        """LIVE close with broker fill-confirmation.

        Books ONLY on a broker-confirmed fill at the broker's actual fill price.
        An unconfirmed close returns confirmed=False and the position STAYS
        OPEN — the caller (flatten_all 15:45→16:00 loop / _manage_one next
        tick) retries, and failures page once per trade per failure kind.

        PARTIAL-FILL POLICY (spec §4 — documented hybrid of (a)+(b)):
        a partial that completes within the deadline books as one fill. A
        partial still working at the deadline is cancelled; the filled portion
        is stashed on the record (in-memory: `_live_exit_fills`) and
        confirmed=False, partial=True is returned. The NEXT retry tick
        resubmits ONLY the remaining quantity at a fresh mark, and booking
        happens once — when cumulative fills cover the full position — at the
        quantity-weighted average net price. A partial is never booked as
        whole. (A mid-window process restart drops the in-memory stash; the
        startup broker_reconcile pass owns that path, as it does today.)

        IDEMPOTENCY / anti-double-submit: the working order id is stashed on
        the record (`_live_exit_order_id`). If a retry tick re-enters while a
        prior order is still working (e.g. cancel failed, or a prior pass
        errored mid-poll), we RESUME polling that order instead of submitting
        a second close against the same position.
        """
        trade_id = record["trade_id"]
        total    = int(record["contracts"])
        prior: List[Tuple[float, float]] = list(record.get("_live_exit_fills") or [])
        done_qty  = sum(q for q, _ in prior)
        remaining = total - int(done_qty)
        if remaining <= 0:
            # Everything already filled across prior partials — book it.
            return self._book_from_fills(record, prior, total,
                                         record.get("_live_exit_last_order_id"))

        try:
            session = get_session()
            account = get_account()
        except Exception as e:
            logger.error(f"LIVE exit {trade_id[:8]}: broker session unavailable: {e}")
            return FillResult(confirmed=False, detail=f"broker session unavailable: {e}")

        # ── 1. Resume a still-working prior order, else submit fresh ─────────
        order_id = record.get("_live_exit_order_id")
        placed   = None
        if order_id is not None:
            try:
                placed = account.get_order(session, order_id)
                logger.info(f"LIVE exit {trade_id[:8]}: resuming order {order_id} "
                            f"(status={placed.status})")
            except Exception as e:
                logger.error(f"LIVE exit {trade_id[:8]}: cannot fetch prior order "
                             f"{order_id}: {e} — will submit fresh")
                record.pop("_live_exit_order_id", None)
                order_id, placed = None, None

        if placed is not None and placed.status in self._DEAD_STATES:
            # Prior order died between passes — harvest any partial it made.
            fill = self._net_fill_price(record, placed)
            record.pop("_live_exit_order_id", None)
            order_id, placed = None, None
            if fill is not None and fill[0] > 0:
                prior.append(fill)
                record["_live_exit_fills"] = prior
                done_qty  = sum(q for q, _ in prior)
                remaining = total - int(done_qty)
                if remaining <= 0:
                    return self._book_from_fills(record, prior, total,
                                                 record.get("_live_exit_last_order_id"))

        if placed is None:
            placed = self._submit_live_close(record, remaining, mark_price,
                                             reason=reason)
            if placed is None:
                self._alert_live_exit_once(
                    trade_id, "submit",
                    f"LIVE close SUBMIT FAILED {trade_id[:8]} — position stays "
                    f"OPEN; retry loop engaged")
                return FillResult(confirmed=False, detail="submit failed")
            order_id = placed.id
            record["_live_exit_order_id"]      = order_id
            record["_live_exit_last_order_id"] = order_id
            logger.info(f"LIVE exit {trade_id[:8]}: close submitted, order "
                        f"{order_id}, qty={remaining} — awaiting broker fill")

        # ── 2. Poll to a bounded deadline; cancel-and-resolve on timeout ─────
        poll     = max(0.0, float(getattr(_cfg, "LIVE_FILL_POLL_SECONDS", 2.0)))
        deadline = time.monotonic() + float(getattr(_cfg, "LIVE_FILL_DEADLINE_SECONDS", 30.0))
        cancel_requested = False
        while True:
            try:
                placed = account.get_order(session, order_id)
            except Exception as e:
                logger.warning(f"LIVE exit {trade_id[:8]}: poll error ({e}) — retrying")
            status = placed.status

            if status == OrderStatus.FILLED:
                fill = self._net_fill_price(record, placed)
                record.pop("_live_exit_order_id", None)
                if fill is None or fill[0] <= 0:
                    # Broker says filled but fills unreadable — refuse to book
                    # fiction; reconcile/retry will resolve against the broker.
                    logger.error(f"LIVE exit {trade_id[:8]}: order {order_id} "
                                 f"FILLED but fills unreadable — NOT booking")
                    return FillResult(confirmed=False, order_id=str(order_id),
                                      detail="filled but fills unreadable; refusing to book")
                prior.append(fill)
                record["_live_exit_fills"] = prior
                if sum(q for q, _ in prior) >= total:
                    return self._book_from_fills(record, prior, total, order_id)
                # Defensive: FILLED for less than requested → treat as partial.
                return self._partial_result(record, prior, total, order_id, trade_id)

            if status == OrderStatus.REJECTED:
                record.pop("_live_exit_order_id", None)
                why = getattr(placed, "reject_reason", None) or "unknown"
                self._alert_live_exit_once(
                    trade_id, "reject",
                    f"LIVE close REJECTED {trade_id[:8]} order {order_id}: {why} "
                    f"— position stays OPEN; retry loop engaged")
                return FillResult(confirmed=False, order_id=str(order_id),
                                  detail=f"rejected: {why}")

            if status in self._DEAD_STATES:
                return self._resolve_dead_order(record, placed, prior, total,
                                                order_id, trade_id)

            # Still working.
            if time.monotonic() >= deadline:
                if not cancel_requested:
                    try:
                        account.delete_order(session, order_id)
                        cancel_requested = True
                        record["_exit_escalated"] = 1        # N.5: ladder did not simply fill
                        # Short grace window to resolve the cancel/fill race:
                        # the order may have filled while the cancel was in
                        # flight — the next polls tell us which won.
                        deadline = time.monotonic() + max(3 * poll, 6.0)
                        logger.warning(f"LIVE exit {trade_id[:8]}: deadline hit — "
                                       f"cancel requested for order {order_id}; "
                                       f"resolving race")
                        continue
                    except Exception as e:
                        # Cancel failed — the order may still be working. Keep
                        # the order id on the record so the NEXT tick RESUMES
                        # this order rather than double-submitting.
                        self._alert_live_exit_once(
                            trade_id, "deadline",
                            f"LIVE close UNFILLED at deadline {trade_id[:8]} "
                            f"order {order_id}; cancel failed ({e}) — resuming "
                            f"same order next tick, position stays OPEN")
                        return FillResult(confirmed=False, partial=done_qty > 0,
                                          order_id=str(order_id),
                                          detail="deadline; cancel failed; resuming next tick")
                else:
                    # Cancel didn't resolve within the grace window either.
                    self._alert_live_exit_once(
                        trade_id, "deadline",
                        f"LIVE close UNRESOLVED {trade_id[:8]} order {order_id} "
                        f"(cancel pending) — resuming next tick, position OPEN")
                    return FillResult(confirmed=False, partial=done_qty > 0,
                                      order_id=str(order_id),
                                      detail="deadline; cancel unresolved; resuming next tick")
            time.sleep(poll)

    def _resolve_dead_order(self, record, placed, prior, total,
                            order_id, trade_id) -> FillResult:
        """A close order reached a terminal non-FILLED state. Harvest whatever
        partial fills it made, then either book (if cumulative fills now cover
        the position — the cancel/fill race can end here), report a partial, or
        report a clean miss. Never books a partial as whole."""
        record.pop("_live_exit_order_id", None)
        fill = self._net_fill_price(record, placed)
        if fill is not None and fill[0] > 0:
            prior.append(fill)
            record["_live_exit_fills"] = prior
            if sum(q for q, _ in prior) >= total:
                return self._book_from_fills(record, prior, total, order_id)
            return self._partial_result(record, prior, total, order_id, trade_id)
        self._alert_live_exit_once(
            trade_id, "unfilled",
            f"LIVE close NOT FILLED by deadline {trade_id[:8]} (order {order_id} "
            f"ended {placed.status}, zero fills) — position stays OPEN; "
            f"re-pricing and retrying")
        return FillResult(confirmed=False, order_id=str(order_id),
                          detail=f"not filled ({placed.status}); re-price and retry")

    def _partial_result(self, record, prior, total, order_id, trade_id) -> FillResult:
        done = sum(q for q, _ in prior)
        record["_live_exit_fills"] = prior
        self._alert_live_exit_once(
            trade_id, "partial",
            f"LIVE close PARTIAL {trade_id[:8]}: {done:g}/{total} filled — "
            f"remainder resubmits next tick; booking deferred until fully closed")
        return FillResult(confirmed=False, partial=True, order_id=str(order_id),
                          detail=f"partial {done:g}/{total}; remainder resubmits next tick")

    def _book_from_fills(self, record, fills, total, order_id) -> FillResult:
        """All contracts confirmed closed — return the quantity-weighted net
        fill price (the broker's, never the mark) and clear the exit state."""
        qty = sum(q for q, _ in fills)
        wavg = sum(q * p for q, p in fills) / qty
        for k in ("_live_exit_fills", "_live_exit_order_id", "_live_exit_last_order_id"):
            record.pop(k, None)
        logger.info(f"LIVE exit {record['trade_id'][:8]}: CONFIRMED fill "
                    f"{qty:g}/{total} @ net {wavg:.4f} (order {order_id})")
        return FillResult(confirmed=True, fill_price=round(float(wavg), 4),
                          order_id=str(order_id) if order_id is not None else None,
                          detail=f"broker-confirmed fill, {len(fills)} order(s)")

    def _alert_live_exit_once(self, trade_id: str, kind: str, msg: str):
        logger.error(msg)
        if (trade_id, kind) in self._live_exit_alerted:
            return
        self._live_exit_alerted.add((trade_id, kind))
        try:
            from notifications.alert_manager import get_alert_manager
            get_alert_manager()._send(f"\U0001F6A8 {msg}")
        except Exception as e:
            logger.warning(f"Live-exit alert failed to send: {e}")

    # ── Order construction / submission (live only) ──────────────────────────

    def _submit_live_close(self, record: TradeRecord, contracts: int,
                           mark_price: Optional[float],
                           reason: str = "") -> Optional["object"]:
        """Order SUBMISSION only (no fill confirmation) — returns the broker
        PlacedOrder (carrying .id for polling) on submit success, else None.
        Submission is not a fill; only _confirm_and_book_live_exit may book.

        Routing (v3.5): condor legs are two-legged VERTICALS and now close as
        a single 2-leg spread order via _close_vertical — previously they fell
        through to _close_single_leg, which SELL_TO_CLOSEd only the short
        symbol (wrong action for a short, long leg orphaned at the broker).
        """
        # v3.8: MARK-LIMIT policy. Closes post AT THE MARK and are re-priced to
        # a fresh mark on every retry tick — we never pay the spread. The ONE
        # exception is the end-of-day flatten: from 15:45 ET the position MUST
        # close (an unfilled 0DTE at the bell is an expiry / assignment, not an
        # overnight hold), so force_market crosses. 15:40-15:44 still tries the
        # mark. See execution/limit_ladder.py.
        force_market = ("hard_close" in (reason or "").lower()
                        and hard_close_order_mode(now_et()) == "market")
        try:
            session = get_session()
            account = get_account()
            if bool(record.get("is_butterfly", False)):
                return self._close_butterfly(session, account, record,
                                             contracts, mark_price, force_market)
            is_vertical = (bool(record.get("is_condor_leg"))
                           or record.get("strategy") == "IronCondorStrategy"
                           or (record.get("short_symbol") and record.get("long_symbol")))
            if is_vertical:
                return self._close_vertical(session, account, record,
                                            contracts, mark_price, force_market)
            return self._close_single_leg(session, account, record, contracts,
                                          mark_price, force_market)
        except Exception as e:
            logger.error(f"Live close submit failed for {record['trade_id'][:8]}: {e}")
            return None

    @staticmethod
    def _tick_for(record: TradeRecord) -> float:
        """Price increment for close limits: SPX-family trades in nickels."""
        sym = str(record.get("symbol", "") or "").upper()
        return 0.05 if sym in ("SPX", "SPXW", "XSP") else 0.01

    @classmethod
    def _round_to_tick(cls, price: float, record: TradeRecord) -> float:
        tick = cls._tick_for(record)
        return max(tick, round(round(price / tick) * tick, 2))

    def _place(self, session, account, order, what: str) -> Optional["object"]:
        response = account.place_order(session, order, dry_run=False)
        if getattr(response, "errors", None):
            logger.error(f"{what} order errors: {response.errors}")
            return None
        placed = getattr(response, "order", None)
        if placed is None or getattr(placed, "id", None) is None:
            logger.error(f"{what} order: no order id in response — cannot poll; "
                         f"treating as submit failure")
            return None
        return placed

    def _close_single_leg(self, session, account, record, contracts,
                          mark_price: Optional[float] = None,
                          force_market: bool = False):
        """v3.8: posts a LIMIT AT THE MARK, not a market order.

        A single-leg market order paid the touch on every exit — combined with
        the market-order ENTRY that was ~25% of premium round-trip on a $0.20
        0DTE with a $0.05 spread, larger than the edge being traded. We now post
        at the mark and let the retry loop re-price against a fresh mark each
        tick, which chases a falling contract instead of parking at a stale
        price. force_market crosses, and is set ONLY by the 15:45 flatten."""
        symbol = record.get("option_symbol", "")
        if not symbol:
            logger.error("Cannot close: no option_symbol in record")
            return None
        # v3.5: an adopted SHORT leg must BUY to close, not sell more short.
        action = (OrderAction.BUY_TO_CLOSE if record.get("is_short_position")
                  else OrderAction.SELL_TO_CLOSE)
        leg = Leg(
            instrument_type = InstrumentType.EQUITY_OPTION,
            symbol          = symbol,
            action          = action,
            quantity        = contracts,
        )
        if force_market or mark_price is None or mark_price <= 0:
            # 15:45 flatten, or no mark to price against — cross and be done.
            order = NewOrder(
                time_in_force = OrderTimeInForce.DAY,
                order_type    = OrderType.MARKET,   # single-leg market is accepted
                legs          = [leg],
            )
            why = "hard-close cross" if force_market else "no mark"
            return self._place(session, account, order,
                               f"Single-leg close (MARKET — {why})")
        tick  = self._tick_for(record)
        limit = self._round_to_tick(limit_at_mark(mark_price, floor=tick), record)
        # SDK signed convention: SELL_TO_CLOSE receives a CREDIT (positive);
        # BUY_TO_CLOSE on an adopted short PAYS a debit (negative).
        signed = limit if action == OrderAction.SELL_TO_CLOSE else -limit
        order = NewOrder(
            time_in_force = OrderTimeInForce.DAY,
            order_type    = OrderType.LIMIT,
            price         = Decimal(str(signed)),
            legs          = [leg],
        )
        return self._place(session, account, order,
                           f"Single-leg close (LIMIT @ mark {limit:.2f})")

    def _close_vertical(self, session, account, record, contracts,
                        mark_price: Optional[float],
                        force_market: bool = False):
        """Close a condor-leg vertical as ONE 2-leg spread order: BUY_TO_CLOSE
        the short strike, SELL_TO_CLOSE the long strike. tastytrade rejects
        MARKET on spreads, so this is a marketable LIMIT: debit capped at the
        spread width (a vertical can never be worth more than its width), so
        even with no mark the order is bounded and safe.

        SDK NOTE (verified v13.x): NewOrder.price is SIGNED — negative=debit,
        positive=credit. price_effect on NewOrder is ignored by current SDKs.
        Closing a short vertical PAYS a debit → price must be NEGATIVE.
        """
        short_sym = record.get("short_symbol", "")
        long_sym  = record.get("long_symbol", "")
        if not short_sym or not long_sym:
            logger.error("Cannot close vertical: missing short/long symbols")
            return None
        width  = float(record.get("spread_width") or 0.0)
        # v3.8: post AT THE MARK (was mark + a fixed $0.10 buffer, i.e. paying
        # up on every close). tastytrade rejects MARKET on spreads, so the
        # 15:45 "market order" for a vertical is a maximally-marketable limit:
        # the debit capped at the spread WIDTH, which a vertical can never
        # exceed — guaranteed to fill, bounded, and safe.
        if force_market:
            if width <= 0:
                logger.error("Hard-close vertical: no spread_width to bound the "
                             "cross — cannot price")
                return None
            limit = width
        elif mark_price is not None and mark_price >= 0:
            limit = limit_at_mark(mark_price,
                                  cap=(width if width > 0 else None),
                                  floor=self._tick_for(record))
        elif width > 0:
            limit = width   # max possible value of the vertical — bounded marketable
        else:
            logger.error("Cannot price vertical close: no mark and no spread_width")
            return None
        limit = self._round_to_tick(limit, record)
        legs = [
            Leg(instrument_type=InstrumentType.EQUITY_OPTION,
                symbol=short_sym, action=OrderAction.BUY_TO_CLOSE,  quantity=contracts),
            Leg(instrument_type=InstrumentType.EQUITY_OPTION,
                symbol=long_sym,  action=OrderAction.SELL_TO_CLOSE, quantity=contracts),
        ]
        order = NewOrder(
            time_in_force = OrderTimeInForce.DAY,
            order_type    = OrderType.LIMIT,
            price         = Decimal(str(-limit)),   # negative = DEBIT paid to close
            legs          = legs,
        )
        return self._place(session, account, order,
                           f"Vertical close ({'MARKET-equiv @ width' if force_market else 'LIMIT @ mark'} "
                           f"{limit:.2f})")

    def _close_butterfly(self, session, account, record, contracts,
                         mark_price: Optional[float],
                         force_market: bool = False):
        """Close a long butterfly (sell wings, buy back the 2x short body) as
        one 3-leg order. v3.5: MARKET → marketable LIMIT (tastytrade rejects
        MARKET on spreads — the old market order would have failed every tick).
        Selling the fly RECEIVES a credit → price is POSITIVE (signed SDK
        convention), floored at one tick below mark; no mark → decline this
        pass rather than guess (retry tick brings a fresh mark)."""
        lower_sym  = record.get("lower_symbol", "")
        center_sym = record.get("center_symbol", "")
        upper_sym  = record.get("upper_symbol", "")
        if not all([lower_sym, center_sym, upper_sym]):
            logger.error("Cannot close butterfly: missing leg symbols")
            return None
        tick = self._tick_for(record)
        # v3.8: post AT THE MARK (was mark - a fixed $0.10 buffer — selling the
        # fly cheap on every close). At 15:45 the flatten must complete and
        # tastytrade rejects MARKET on spreads, so the cross is a limit at ONE
        # TICK of credit: the lowest price we can ask, hence maximally
        # marketable for a sale.
        if force_market:
            limit = self._round_to_tick(tick, record)
        elif mark_price is None or mark_price < 0:
            logger.warning("Butterfly close: no mark to price the limit — "
                           "declining this pass, will retry with a fresh mark")
            return None
        else:
            limit = self._round_to_tick(limit_at_mark(mark_price, floor=tick), record)
        legs = [
            Leg(instrument_type=InstrumentType.EQUITY_OPTION,
                symbol=lower_sym,  action=OrderAction.SELL_TO_CLOSE, quantity=contracts),
            Leg(instrument_type=InstrumentType.EQUITY_OPTION,
                symbol=center_sym, action=OrderAction.BUY_TO_CLOSE,  quantity=contracts * 2),
            Leg(instrument_type=InstrumentType.EQUITY_OPTION,
                symbol=upper_sym,  action=OrderAction.SELL_TO_CLOSE, quantity=contracts),
        ]
        order = NewOrder(
            time_in_force = OrderTimeInForce.DAY,
            order_type    = OrderType.LIMIT,
            price         = Decimal(str(limit)),   # positive = CREDIT received
            legs          = legs,
        )
        return self._place(session, account, order,
                           f"Butterfly close ({'MARKET-equiv @ 1 tick' if force_market else 'LIMIT @ mark'} "
                           f"{limit:.2f})")

    # ── Fill readback ─────────────────────────────────────────────────────────

    def _net_fill_price(self, record: TradeRecord,
                        placed) -> Optional[Tuple[float, float]]:
        """Read (closed_quantity, net_fill_price) from a PlacedOrder's per-leg
        fills. The net is on the SAME basis as the marks _fetch_current_premium
        produces, so _execute_exit's P&L math is untouched:
          vertical:   short_avg - long_avg          (mark: short_mark - long_mark)
          butterfly:  lower + upper - 2*center      (mark: same combination)
          single leg: the leg's weighted avg fill
        closed_quantity is the min across legs of (filled / leg ratio) — legs of
        a complex order fill together, min() is the safe floor. Returns None if
        nothing readable filled."""
        def leg_stats(sym: str) -> Tuple[float, Optional[float]]:
            for leg in (getattr(placed, "legs", None) or []):
                if getattr(leg, "symbol", None) == sym:
                    fills = getattr(leg, "fills", None) or []
                    q = sum(float(f.quantity) for f in fills)
                    if q <= 0:
                        return 0.0, None
                    p = sum(float(f.quantity) * float(f.fill_price) for f in fills) / q
                    return q, p
            return 0.0, None

        if bool(record.get("is_butterfly", False)):
            ql, pl = leg_stats(record.get("lower_symbol", ""))
            qc, pc = leg_stats(record.get("center_symbol", ""))
            qu, pu = leg_stats(record.get("upper_symbol", ""))
            qty = min(ql, qu, qc / 2.0)
            if qty <= 0 or None in (pl, pc, pu):
                return None
            return qty, round(pl + pu - 2.0 * pc, 4)

        if (record.get("is_condor_leg")
                or record.get("strategy") == "IronCondorStrategy"
                or (record.get("short_symbol") and record.get("long_symbol"))):
            qs, ps = leg_stats(record.get("short_symbol", ""))
            ql, pl = leg_stats(record.get("long_symbol", ""))
            qty = min(qs, ql)
            if qty <= 0 or None in (ps, pl):
                return None
            return qty, round(ps - pl, 4)

        q, p = leg_stats(record.get("option_symbol", ""))
        if q <= 0 or p is None:
            return None
        return q, round(p, 4)

    def clear_trail(self, trade_id: str):
        self._trail_stops.pop(trade_id, None)
        self._trail_active.pop(trade_id, None)
        self._bos_trackers.pop(trade_id, None)
        self._post_target_trail.pop(trade_id, None)


# Singleton
_exit_engine: Optional[ExitEngine] = None


def get_exit_engine(paper_trading: bool = PAPER_TRADING) -> ExitEngine:
    global _exit_engine
    if _exit_engine is None:
        _exit_engine = ExitEngine(paper_trading)
    return _exit_engine
