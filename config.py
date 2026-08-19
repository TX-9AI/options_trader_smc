"""
config.py — options_trader_smc v4.21 (fork of options_trader v4.18)
v4.21 — 2026-08-19 — (1) MAX_LOSS_PCT 0.40 -> 0.25 by operator direction —
        tightens `stop_hit` (sweep + ICT), `hard_stop` (ORB) and the ADOPTED
        stops, which inherit it via ADOPTED_STOP_PCT. Butterfly (0.25 already),
        condor (CONDOR_STOP_LOSS_PCT) and continuation (0.15) are unaffected —
        they never read this constant. The identical change ships to
        options_trader_v3 so the comparison stays apples-to-apples.
        (2) ORB_BLOCK_RANGING — ORB no longer fires under RANGING. The operator
        calls that cell the conclusive loss leader. Implemented as its own
        env-tunable flag rather than by deleting RANGING from the tuple, so the
        decision is visible, reversible and journaled rather than buried in a
        literal.
v4.20 — 2026-08-19 — G8: ICT SUITE REGISTRATIONS. (1) The seven ICT setups
        added to DEBIT_DIRECTIONAL_STRATEGIES by name — §3.1: a directional
        debit strategy that is not in this set silently bypasses the cutoff.
        (2) DEBIT_DIRECTIONAL_CUTOFF_ET default 11:00 -> 11:30, because the
        Silver Bullet window runs to 11:30 and the old value would have killed
        its last half hour without saying so. (3) The OT_ICT_* knob block
        documented at the end of this file — all stated priors, all three fire
        gates default CLOSED. The GEX-pin butterfly stays exempt by ABSENCE
        from the set, exactly as it already was.
v4.19 — 2026-08-18 — SMC CORE KNOBS (fork: options_trader_smc). Documented
        defaults for the smc/ package; env always wins (the OT_RC_*/OT_TR_*
        convention — a bound correction is an env flip, not a bake):
        OT_SMC_ACCEPT_CLOSES (2)      closes beyond a level = acceptance
        OT_SMC_POI_APPROACH_ATR (0.75) FVG-approach distance that FORMS a setup
        OT_SMC_REVOKE_GATES (1)       REVOKED setup blocks same-direction entries
        Engine selection: OT_REGIME_ENGINE=smc (fork default via systemd env;
        l2/v13 remain rollbacks). Every threshold is a STATED PRIOR — the
        QQQ cutover collects the distribution these get fitted
        from; do not tune them on the first bad session.
v4.18 — 2026-08-14 — TCS_COOLDOWN_MIN retired to 0 (TC.6 no longer reads it);
        TCS_MIN_CREDIT_PCT_WIDTH superseded by the joint EV test.
v4.17 — 2026-08-14 — TCS_LOSS_GIVEN_BREACH: the credit and POP floors are
        now ONE joint EV test rather than two independent ones.
v4.16 — 2026-08-14 — TC.6 HOTFIX: TCS_START_ET (11:00), TCS_MIN_CREDIT_PCT_WIDTH
        (0.10), TCS_MIN_CREDIT_NICKEL_MULT (4.0), TCS_COOLDOWN_MIN (30). It
        rapid-fired the fleet selling $0.06 credits on $5 wides at 10:02 ET.
v4.15 — 2026-08-13 — TREND_CREDIT_ACTIVE. TC.6 was the only new firing
        strategy with no env kill switch.
v4.14 — 2026-08-13 — ENTRY_LIMIT_LADDER [0.50, 0.25, 0.00] @ 15s.
        DEFAULTS OFF (ENTRY_LADDER_ACTIVE=0) — the pricing primitive and the
        fill model land together, but nothing changes behaviour until the fill
        model is proven against live quotes.
v4.13 — 2026-08-13 — PENNY_CLASSES + PRICE_INCREMENT_BOUNDARY. Option quote
        increments are class- AND level-dependent; `round(px, 2)` posts invalid
        limits on nickel/dime classes.
v4.12 — 2026-08-13 — VERTICAL_HOLD_TO_ET (15:45). Credit verticals are exempt
        from the 15:40 flatten ladder; debit positions keep it, because the
        mark-limit phase is what stops every EOD exit paying the full spread.
v4.11 — 2026-08-13 — CONDOR_RATCHET_STANDALONE_ONLY. The ratchet closed
        UNTESTED legs on a reversal; scoped to standalone only.
v4.10 — 2026-08-13 — CONDOR_MAX_QUOTE_WIDTH (0.25 of mid). A ranking never
        refuses; a floor does.
v4.9 — 2026-08-13 — CONDOR_MIN_POP / CONDOR_POP_BAR_MIN. Probability-of-profit
        floor on every short leg, defaulting to 0.70 — the BOTTOM of the
        operator's 70-80%% band, because he asked explicitly not to be
        restrictive on a trade he already knows is risky.
v4.8 — 2026-08-13 — CONDOR PITCHFORK ANCHOR (PF.5). CONDOR_PITCHFORK_ANCHOR /
        CONDOR_REQUIRE_FORK / CONDOR_PF_TIMEFRAME / CONDOR_PF_FLAT_SLOPE.
        The pitchfork has been BUILT AND LIVE as a weight-0 observer since
        2026-08-12 with exactly ONE call site (main.py:2091, `_pf_snap`) and
        NOTHING has ever read the rails back. This is its first consumer — the
        one the white paper pre-registered, because strike placement produces a
        CREDIT that is directly comparable on identical tape.
        DAILY fork by operator ruling. A daily fork is invalidated only by DAILY
        closes, so an intraday session cannot kill it; the hourly one has a
        measured p50 lifetime of 5 bars plus a k=3 confirmation lag and would
        re-anchor mid-position. `CONDOR_PF_FLAT_SLOPE` exists because a SIGN is
        not a SLOPE — a fork drifting 0.001%% a bar is noise, and ordering legs
        off its sign would be reading a coin flip as structure.
v4.7 — 2026-08-13 — CONTINUATION_STOP_LOSS_PCT default 0.25 -> 0.15. THE REPO
        DEFAULT IS THE FLEET LEVER, not the env var: every box receives
        config.py through git pull + bake, so this reaches all 15 on the bake
        already scheduled — no systemd edit, no rotate_tokens change (its FIELDS
        table is hardcoded to seven credentials and has no arbitrary-var path),
        no extra restart. `OT_CONT_STOP_PCT` remains the PER-BOX OVERRIDE, which
        is what a modular fleet wants. It is also the only path that
        participates in the version discipline — a systemd `Environment=` line
        is invisible to check_versions, absent from the changelog and outside
        git entirely.
        EVIDENCE: excursion_report floor sweep, `max_loss_floor /
        ContinuationStrategy`, n=66 across 9 sessions at a **0%% win rate** — a
        15%% floor stops all 66 with **ZERO WINNERS CUT**, NET DELTA +8.85 units
        of entry premium against +2.25 at the current 25%%. Meets the
        pre-registered cheapest-threshold-catching-zero-winners rule rather than
        an in-sample argmax.
        ⚠️ WHAT THIS COHORT IS, and why tightening it is not the same as
        tightening a thesis stop: these are BY DEFINITION the trades where NO
        structural stop fired — not regime_flip, not bos_exit, not
        insurance_stop. The thesis was still technically intact and the premium
        died anyway. Zero winners cut over 9 sessions is evidence it did not
        cost anything; it is not proof that it cannot.
v4.6 — 2026-08-13 — DEBIT_DIRECTIONAL_CUTOFF_ET / _STRATEGIES / DEBIT_BLOCK_ACTIVE
        for main v6.2's afternoon debit block. Env: OT_DEBIT_CUTOFF_ET ("HH:MM")
        and OT_DEBIT_BLOCK_ACTIVE, so the hour moves and the rule dies without a
        deploy. ⚠️ ONE DEFINITION ONLY — a parallel AFTERNOON_NO_DEBIT_* block
        was drafted and removed before shipping; two names for one rule, with
        the later assignment silently winning, is the exact failure class the
        version discipline exists to catch.
v4.5 — 2026-08-07 — SWP.2 + CNT.3, the two Tier-1 tuning priors.
        SWEEP_SETUP_FLOOR_SHORT (default 0.20) separates short sweeps from
        longs — three measures agree and the PLTR mechanism backs it, but n=6
        and a 0.20 floor against a ~0.265 score ceiling is a NEAR-DISABLE, not
        a dial. CONT_HANDOFF_BLOCK_COMPRESSION stops the runaway handoff firing
        under COMPRESSION (39 trades, 28% WR, and the worst never-favourable
        cell at 80%) — a runaway asserts expansion while the label asserts
        coiling.

v4.4 — 2026-08-07 — CNT.2: CONT_INSURANCE_STOP (OT_CONT_INSURANCE, default on).
        Arms the already-stamped `underlying_stop` as a structural early
        invalidator for continuation, ONLY while BOSTracker.protected_level is
        None — i.e. only in the window BOS cannot cover — then hands off.
        Exits tag `insurance_stop`.

v4.3 — 2026-08-07 — CNT.1: CONT_BREAKOUT_DIRECTION + CONT_BREAKOUT_MIN_ADX.
        Standalone continuation may now fire under BREAKOUT_VOLATILE, taking
        direction from the trend engine's `overall_direction` instead of from
        the label (which carries none). Gated on ADX rather than on
        regime.conviction, because under a non-trending label the conviction
        floor is skipped and BREAKOUT's conviction is not the trend's. Tagged
        `trend_continuation_breakout` so it scores separately.

v4.2 — 2026-08-07 — SWP.1: SWEEP_SETUP_FLOOR (OT_SWEEP_SETUP_FLOOR, default
        0.05). Sweep stops gating on the regime label and gates on the L1
        _sweep SETUP SCORE. The label wins 0.4% of live ticks and is exactly
        zero on 96%, so the trade was effectively off. A PRIOR for the
        collection phase, to be tightened on live fires.

v4.1 — 2026-08-01 — 15m FETCH DEPTH 50 -> 150, waking a vote that has never
        fired. trend_engine._analyze_single bails to NEUTRAL below EMA_SLOW+5=55
        bars, and 15m fetched 50 — so the 0.30 direction weight v3.1 moved ONTO
        15m on 07-16 (to route around starved 1d/1h) was itself dead on arrival.
        Only 5m (100 bars) has ever been able to vote.
        WHY 150 AND NOT 60: clearing 55 wakes the vote but not usefully. The
        engine re-seeds the EMA on whatever tail it is handed, so measured
        against a fully-warm EMA-50 the error is 69% of a 0.30 bar at 55 bars and
        49% at 60 — a confident vote on a number dominated by its seed, which is
        worse than an honest NEUTRAL. At 80 bars the error is 2.5%, at 150 it is
        0.3%. 150 15m bars is ~5.8 sessions.
        COSTS NOTHING IN DATA: candle_feed prunes to max(need,60)*PRUNE_FACTOR,
        so the store already retained 240 15m bars — only the fetch cap hid them.
        Raising need to 150 raises retention to 600 automatically.
        1h DELIBERATELY LEFT AT 50 (asleep). Operator's call: the market responds
        more to developments since the close than to the prior session's range,
        which is a reference point rather than a discriminator. A live 1h vote in
        the morning is dominated by the PRIOR session and would oppose the
        opening drive, suppressing TRENDING in exactly the 09:30-10:40 window
        under study. 15m carries more weight and has no such lag pathology.
        WATCH ON FIRST BAKE: TastyTrade's backfill reach is limited and the exact
        cutoff is unknown, so a cold store may not be served 150 immediately. It
        accumulates ~26 15m bars/session and the vote stays NEUTRAL until it
        fills — no worse than today. trend_engine v3.3's STARVED warning reports
        the real per-box depth from the first RTH session.
v4.0 — 2026-07-27 — SWEEP STRIKE FLOOR. SWEEP_DELTA_STRONG 0.08 -> 0.12,
        paired unchanged with SWEEP_DELTA_WEAK 0.30. The inverse-delta
        scaling in strategy/sweep_reversal_strategy.py:_sweep_target_delta
        maps max conviction to the STRONG endpoint, so the highest-conviction
        sweeps were buying the FURTHEST-OTM contracts. On 2026-07-27 a 0.62
        conviction resolved to a 0.16 delta and bought a PLTR $122 put ~6%
        OTM, where gamma could not reach it inside the holding window. The
        endpoints now read: max conviction -> 0.12 delta (leveraged but
        REACHABLE), low conviction -> 0.30 (near-ATM), linear between.
        SEPARATE DEFECT, SEPARATE FIX: the same trade also had a bad ENTRY
        because analysis/regime_confluence.py _sweep could not see trend at
        all (fixed in regime_confluence v1.3). These are deliberately not
        bundled — bundling them would make post-freeze sweep P&L
        unattributable between strike selection and entry quality.
v3.9 — 2026-07-22 — PAPER FRICTION UNIFIED (audit defect T). Default
        PAPER_FILL_SLIPPAGE_PCT 0.01 -> 0.0, and the knob is now applied by
        ONE authority (execution/limit_ladder) across every paper path —
        single, butterfly, condor leg, and rolled vertical. Rationale: under
        the mark-limit policy (limit_ladder v1.2) live posts AT the mark and
        either fills there or does not fill, so a markup made paper
        PESSIMISTIC on price while still optimistic on fill rate. Booking the
        mark everywhere is the honest default; the residual paper->live gap is
        no-fill risk. The knob survives as a UNIFORM stress lever: set
        OT_PAPER_SLIPPAGE_PCT to the fill quality measured in the live
        shakedown and every paper path degrades together.
        Also folds in the un-bumped changes that shipped under the stale v3.3
        header (audit defect U): FLATTEN_WINDOW_OPEN_ET (15,40) 2026-07-22,
        CONDOR_TRIGGER_APPROACH 2026-07-17, runner-refinement knobs v2.0.
v3.3 — 2026-07-13 — CUTOFF DISAMBIGUATION (defect H). Two constants named so
        similarly they were confused for one rule are now named for their scope,
        and the global cutoff is no longer hardcoded outside config.
        (a) NO_ENTRY_AFTER_ET -> ORB_NO_ENTRY_AFTER_ET. Unchanged at (11, 0).
            It is, and always was, the ORB-scoped cutoff (orb_engine v3.6) and
            the arm condition for sweep reversal (sweep_reversal_strategy v3.1).
        (b) NEW: GLOBAL_NO_ENTRY_ET = (14, 0) — the global 0DTE entry cutoff for
            ALL strategies. utils/time_utils v3.1 now READS this instead of
            hardcoding dtime(14, 0), so config is finally the single source of
            truth for both cutoffs.
        NOT a behaviour change: both cutoffs keep their exact prior values.
v1.0 — original release
v1.1 — 2026-06-27 — remove Twilio, fix SWEEP_TARGET_DELTA to 0.08,
        remove Grade C, add BUTTERFLY_ENTRY_CUTOFF_ET
v1.2 — 2026-06-29 — butterfly overhaul: fixed wings by instrument,
        GEX pin proximity gate (1x expected move), noon-2PM entry window,
        one-per-session limit, TP reduced to 20%
v1.3 — 2026-07-02 — narrow SPX condor wings 25->5 so each vertical is
        affordable (max loss ~$235/contract), enabling half-budget-per-side
        condor sizing.
v1.4 — 2026-07-02 — add DAILY_LOSS_LIMIT_USD (default = per-trade risk): halts
        new entries when the day's NET P&L is down by that amount.
v1.5 — 2026-07-02 — add single-name instruments (NFLX/META/MU/MSFT/TSLA/AAPL/
        NVDA/SMCI/ORCL) as DIRECTIONAL-ONLY: ORB + sweep only, no condor/
        butterfly. Widens paper-trading coverage for data collection.
v1.6 — 2026-07-03 — expand the tradeable universe to the full screener list.
v1.8 — 2026-07-15 — live fill-confirmation knobs (LIVE_FILL_*, v3.5) and
        reconcile cadence (BROKER_RECONCILE_INTERVAL_MIN, v3.6); and
        BROKER_RECONCILE_ENABLED now defaults to the trading mode (LIVE=on,
        PAPER=off) so going live via configure.sh auto-enables reconciliation —
        explicit OT_BROKER_RECONCILE=True/False still overrides.
v2.0 — 2026-07-15 — RUNNER REFINEMENTS (all env-tunable): MAX_LOSS_PCT
        25%→40% for directionals (butterfly pinned at 25% via
        BUTTERFLY_STOP_LOSS_PCT); USE_5M_FVG_TRAIL (5-minute FVGs anchor
        trails); FVG_FLOOR_MAX_LOCK_PCT=0.90 clamp; POST_TARGET_TRAIL_LOCK_PCT
        0.85→0.75 (leash no longer inverts past target);
        SWEEP_POST_TARGET_TRAIL=True (sweep runners trail past +100% instead
        of the hard TP).
v1.9 — 2026-07-15 — LIVE_ENTRY_DEADLINE_SECONDS (entry fill-confirmation
        window, defect O) and PAPER_FILL_SLIPPAGE_PCT now env-tunable with an
        honest 1% default applied against the trade (defect R).
        Neutral strategies run ONLY on true-0DTE index products (SPY/QQQ/SPX/
        IWM); every other symbol (single names + weekly-only ETFs) is
        directional-only, derived automatically from FULL_STRATEGY_INSTRUMENTS.
v1.7 — 2026-07-03 — sweep strike delta now scales with reversal strength
        (strong->far-OTM, weak->near-ATM); ORB strike snapping breaks toward
        higher/lower delta; paper fills at the exact bid/ask midpoint (no
        slippage) — all orders priced at the mark.
v3.0 — 2026-07-10 — repo-wide v3.0 bump: Yahoo-Finance purge & data stream
        mapping optimization (all market data now flows from the single
        shared TastyTrade candle feed — see data/candle_feed.py). No logic
        change in this file.
v3.2 — 2026-07-12 — TOLERANCES REMOVED + SESSION_LOSS_LIMIT deleted.
        (a) ORB_BREAK_BUFFER (0.05% of price) REMOVED. It gated the break on the
            close clearing the range by a PERCENTAGE — $0.49 on MU, ~$3.00 on SPX.
            The retest is already the noise filter (a meaningless break fails it),
            so the buffer only cost real setups while scaling into a hole on
            high-priced instruments. See orb_engine v3.5.
        (b) SESSION_LOSS_LIMIT (the integer 2) DELETED. It was a COUNT of losing
            trades from the v1.x count-based circuit breaker, and it is NOT the
            daily loss halt. It has been vestigial since risk_manager v1.4, which
            requests a regime reassessment after EVERY losing trade — the count
            gates nothing. It survived only in dashboards, which printed
            "Session CB: 2 losses -> halt" for a halt that could never occur.
            The REAL halt is DAILY_LOSS_LIMIT_USD (below): dollars, net for the
            day, so a green day keeps trading no matter how many losses stack up.
v3.1 — 2026-07-12 — DEAD-CONSTANT PURGE + honest comments.
        (a) BUTTERFLY_ENTRY_CUTOFF_ET 15:00 -> 14:00. The 15:00 value was
            UNREACHABLE: main.py calls session_guard.can_enter() WITHOUT
            is_butterfly=True, so the generic 14:00 cutoff always fired first.
            14:00 is also the intended rule (post-14:00 tape gets erratic on
            dealer hedging). This makes config agree with live behaviour; it is
            NOT a behaviour change.
        (b) REMOVED, never imported by any module (verified by grep across the
            tree and by git log -S back to the initial commit):
              ORB_TRAIL_ACTIVATION   — duplicate of TRAIL_ACTIVATION_PCT
              CONDOR_SHORT_DELTA     — from iron_condor v1.0 (delta selection),
              CONDOR_DELTA_TOLERANCE   dead since v1.1 made strikes BB-anchored
              MIN_TF_CONFLUENCE      — concept lives in regime_classifier v1.3 as
                                       a HARDCODED `aligned_timeframes < 2`; the
                                       config value (1) was LOOSER and unwired
              ENTRY_COOLDOWN_MINUTES — ORB's state machine IS the cooldown
                                       (waiting / armed / open are exclusive)
        (c) The Iron Condor comment claiming "Delta-based strike selection is
            primary" was false since v1.1 — strikes are Bollinger-Band anchored
            with NO delta anywhere. Corrected.
        (d) MIN_RRR and VWAP_FILTER_ACTIVE are RETAINED but explicitly marked
            UNWIRED. Both are genesis constants (present at the initial commit,
            never referenced, never mentioned in any changelog). They are kept
            because each names an intended feature that was never built — see
            the notes at their definitions. Deleting them would erase the only
            evidence the intent existed.

All secrets come from environment variables — never from hardcoded values
or editable files. The setup_ec2.sh script writes them into the systemd
unit so the bot has them at runtime without any manual file editing.

Tunable strategy parameters live here and are safe to commit.
"""

import os
from dataclasses import dataclass
from typing import Optional


# ─── ENVIRONMENT HELPERS ──────────────────────────────────────────────────────

def _require(key: str) -> str:
    val = os.environ.get(key, "")
    if not val:
        raise EnvironmentError(
            f"\n\n  ❌  Missing required environment variable: {key}\n"
            f"      Run setup_ec2.sh to configure this bot properly.\n"
            f"      For local dev, export {key}='...' in your shell.\n"
        )
    return val

def _optional(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# ─── TASTYTRADE CREDENTIALS (from environment) ────────────────────────────────

def get_tt_client_secret()  -> str: return _require("TT_CLIENT_SECRET")
def get_tt_refresh_token()  -> str: return _require("TT_REFRESH_TOKEN")
def get_tt_account_number() -> str: return _require("TT_ACCOUNT_NUMBER")


# ─── TELEGRAM ALERTS (from environment) ──────────────────────────────────────

def get_telegram_token()    -> str: return _optional("TELEGRAM_TOKEN")
def get_telegram_chat_id()  -> str: return _optional("TELEGRAM_CHAT_ID")

def telegram_configured() -> bool:
    return bool(get_telegram_token() and get_telegram_chat_id())


# ─── INSTRUMENT SELECTION ─────────────────────────────────────────────────────

INSTRUMENT          = os.environ.get("OT_INSTRUMENT", "QQQ")

# Tradeable universe. Strike increments are a per-price-band starting point;
# the options chain resolves to the nearest liquid strike, so a slightly-off
# value is not fatal — tune a name here only if its fills consistently miss.
# ── OPTION PRICE INCREMENTS (2026-08-13, operator: "some contracts allow one
# cent increments others are five cents and even a few other are $.10") ───────
# TWO DIMENSIONS, not one: the CLASS decides whether it quotes in pennies, and
# the PRICE LEVEL decides the increment above the $3.00 boundary.
#   PENNY class      : $0.01 below $3.00, $0.05 at/above
#   NON-PENNY class  : $0.05 below $3.00, $0.10 at/above
# ⚠️ `PENNY_CLASSES` BELOW IS A STARTING LIST, NOT A VERIFIED ONE. Membership of
# the Penny Interval Program changes and is a BROKER/OCC fact, not something
# derivable from anything on this box. Verify against TastyTrade's contract
# metadata before trusting it — a wrong entry here posts an INVALID LIMIT that
# the venue rejects or silently adjusts, and a silently adjusted limit is a fill
# at a price nobody chose. Treated conservatively: anything NOT listed is
# assumed NON-PENNY, so an unknown symbol posts a coarser (valid) price rather
# than a finer (possibly rejected) one.
# ── ENTRY LIMIT LADDER (2026-08-13, operator's manual technique) ─────────────
# His worked example: bid 1.95 / ask 2.35 -> mark 2.15, spread 0.40.
# "I would try 2.05, 2.10 and then 2.15" — every ENTRY_LADDER_STEP_SEC, walking
# from aggressive toward the mark. Expressed as fractions of the HALF-spread out
# from the mark, so it self-scales: 0.50 -> 2.05, 0.25 -> 2.10, 0.00 -> 2.15.
# Terminal rung SITS AT MARK and re-anchors on a fresh quote each tick — his
# words: "let it sit at Mark in case price comes back and the plan can activate."
# ⚠️ PRICING ONLY. Posting an aggressive limit and ASSUMING it fills manufactures
# edge — the better the rung, the larger the fake gain. `execution/fill_model.py`
# is the other half and must gate any paper fill booked from these prices.
# ── TC.6 KILL SWITCH (2026-08-13) ────────────────────────────────────────────
# TC.6 is the ONLY brand-new FIRING strategy shipped today and was the only one
# with no env-level off switch — stopping it would have needed a code change and
# a re-bake, on a strategy that has never executed a live order. Every other
# change today has one. This closes that gap.
# ── TC.6 OWNS ITS OWN CONSTANTS (TCS.1, 2026-08-14) ──────────────────────────
# ⚠️ TREND PARTICIPATION BORROWED SIX `CONDOR_*` KNOBS, so changing one for the
# CONDOR silently retuned a DIFFERENT TRADE and nothing said so. These are the
# same numbers under names that mean what they govern.
# **VALUES ARE IDENTICAL TO THE CONDOR DEFAULTS THEY REPLACE** — this is a
# de-coupling, not a re-tune, and `tests/test_tcs_decoupling.py` asserts the
# equality so a future divergence is a DECISION rather than a drift.
TCS_MIN_POP                 = float(os.environ.get("OT_TCS_MIN_POP", "0.70"))
TCS_MAX_QUOTE_WIDTH         = float(os.environ.get("OT_TCS_MAX_QUOTE_WIDTH", "0.25"))
TCS_POP_BAR_MIN             = float(os.environ.get("OT_TCS_POP_BAR_MIN", "5"))
TCS_NICKEL_REF              = float(os.environ.get("OT_TCS_NICKEL_REF", "0.05"))
TCS_WING_WIDTH_SPX          = float(os.environ.get("OT_TCS_WING_SPX", "5"))
TCS_WING_WIDTH_QQQ          = float(os.environ.get("OT_TCS_WING_QQQ", "5"))

TREND_CREDIT_ACTIVE         = os.environ.get("OT_TCS_ACTIVE", "1") == "1"
# ── TC.6 ENTRY GATES (2026-08-14 HOTFIX — it rapid-fired the whole fleet) ─────
# Observed 10:02 ET on 08-14: NVDA sold a $5-wide for $0.06, PLTR a $6-wide for
# $0.08, and every box re-entered seconds after a nickel close.
# THREE THINGS WERE MISSING AND EACH ONE ALONE WOULD HAVE STOPPED IT:
#  (1) NO AFTERNOON GATE. Designed as afternoon trend participation, coded
#      against GLOBAL_NO_ENTRY_ET (14:00). It fired at 10:02.
#  (2) NO MINIMUM CREDIT — and the POP floor CAUSES this. POP rises with
#      distance, so requiring POP >= 0.70 selects for FAR strikes, and far
#      strikes collect almost nothing. The probability half of the gate shipped
#      without the payoff half. A gate that only demands SAFETY systematically
#      finds the worst-paid trade that clears it.
#  (3) NO RE-ENTRY COOLDOWN. With credit $0.06 and the nickel close at $0.05,
#      total profit potential is ONE CENT — the trade closes on the tick it
#      opens, then reopens. "No per-session limit" was the operator's call and
#      is respected; a LOOP is a defect, not a limit question.
TCS_START_ET                = (11, 0)     # afternoon only, matches AFD.1
# Credit must clear BOTH floors. Width-relative keeps risk/reward sane;
# nickel-relative guarantees the trade has room to exist at all.
# 0.10 is a STATED PRIOR inside the measured band: credit_edge ran 8-19% of
# width at sellable offsets, and TC.7's ORB-anchored 0.00% cell was ~17%.
TCS_MIN_CREDIT_PCT_WIDTH    = float(os.environ.get("OT_TCS_MIN_CREDIT_PCT", "0.10"))
# ── THE JOINT EV TEST (2026-08-14) ───────────────────────────────────────────
# Operator: "The trade should at least enter on some expectation of profit, not
# all willy nilly like this."
# A flat credit floor and a flat POP floor are INDEPENDENT tests, and independent
# is the bug: POP >= 0.70 selects FAR strikes, far strikes pay little, and the
# two floors never talk to each other. The correct condition is a single
# inequality:
#       EV = credit * POP - L * width * (1 - POP) > 0
#   =>  credit / width  >  L * (1 - POP) / POP
# so a LOW-POP strike must pay RICHLY and a HIGH-POP strike may be thin. That is
# the shape a credit spread actually has.
# `L` is loss-given-breach as a fraction of width. **NOT 1.0**: a breach rarely
# runs the full width by the bell — TC.7's ORB-anchored cell measured E[loss]
# 0.35 on a $5 wide (7% of width) at 90% terminal-OK, and credit_edge put real
# credits at 8-19% of width. At L=1.0 a POP-0.70 strike would need 30% of width,
# which essentially never occurs, and the gate would silence TC.6 entirely —
# over-correcting into silence is its own failure.
# L=0.5 is a STATED PRIOR: it requires 21% of width at POP 0.70, 5.6% at POP
# 0.90, 2.6% at POP 0.95. Conservative against the measured 7%, and it produces
# the right ORDERING regardless of the exact value.
TCS_LOSS_GIVEN_BREACH       = float(os.environ.get("OT_TCS_LGB", "0.5"))
TCS_MIN_CREDIT_NICKEL_MULT  = float(os.environ.get("OT_TCS_NICKEL_MULT", "4.0"))
# ⚠️ RETIRED 2026-08-14, NOT DELETED. TC.6 no longer reads this. It was an
# emergency brake during the rapid-fire incident and was the wrong instrument
# for the right worry — the loop came from a $0.06 credit sitting one cent from
# a nickel close and one cent from a mis-set stop, all fixed at the source. The
# constant survives so a future re-add needs no config change; nothing consults
# it today.
TCS_COOLDOWN_MIN            = float(os.environ.get("OT_TCS_COOLDOWN_MIN", "0"))

ENTRY_LIMIT_LADDER          = [0.50, 0.25, 0.00]
ENTRY_LADDER_STEP_SEC       = float(os.environ.get("OT_ENTRY_LADDER_STEP_SEC", "15"))
ENTRY_LADDER_ACTIVE         = os.environ.get("OT_ENTRY_LADDER", "0") == "1"

PENNY_CLASSES = {
    "SPY", "QQQ", "IWM", "DIA", "GLD", "TLT",
    "AAPL", "AMD", "AMZN", "AVGO", "COST", "CRM", "CVX", "GOOGL", "GS",
    "JPM", "LLY", "META", "MSFT", "MU", "NFLX", "NVDA", "ORCL", "PLTR",
    "SMCI", "SMH", "TSLA", "UNH", "XOM",
}
# SPX is DELIBERATELY ABSENT — index options are not in the penny program.
PRICE_INCREMENT_BOUNDARY    = 3.00

STRIKE_INCREMENTS = {
    # Index products with true 0DTE — full strategy set (condor/butterfly OK)
    "SPY": 1, "QQQ": 1, "SPX": 5, "IWM": 1,
    # Weekly-only ETFs — directional only
    "DIA": 1, "SMH": 1, "TLT": 1, "GLD": 1,
    # Single names — directional only
    "AAPL": 5, "MSFT": 5, "META": 5, "MU": 5, "TSLA": 5, "NVDA": 1,
    "NFLX": 1, "ORCL": 1, "SMCI": 1, "PLTR": 1, "AMD": 1, "AMZN": 1,
    "GOOGL": 1, "XOM": 1, "CVX": 1, "JPM": 5, "GS": 5, "LLY": 5,
    "UNH": 5, "AVGO": 5, "CRM": 5, "COST": 5,
}
STRIKE_INCREMENT    = STRIKE_INCREMENTS.get(INSTRUMENT, 1)

# Neutral strategies (iron condor, butterfly) require true-0DTE decay and strike
# density, so they run ONLY on these. Every other tradeable symbol is
# directional-only (ORB + Sweep Reversal), derived automatically — add a symbol
# to STRIKE_INCREMENTS and it's directional unless it's listed here.
# 2026-07-14 (operator directive): neutral strategies enabled FLEET-WIDE for
# data collection — every configured symbol runs butterfly/condor eligibility.
# Was {"SPY","QQQ","SPX","IWM"}, which silently excluded 26 of 29 live boxes.
FULL_STRATEGY_INSTRUMENTS    = set(STRIKE_INCREMENTS)

# ── Butterfly discount gate (2026-07-14, operator directive) ──────────────────
# The fly's edge is buying the tent at a DISCOUNT while price still has to walk
# into it: require net_debit <= this fraction of wing width (0.33 => min ~2:1
# reward:risk). Self-normalizing across symbols; needs only marks. PRIOR —
# calibrate from logged debit-ratio vs outcome once fleet-wide entries accrue.
BUTTERFLY_MAX_DEBIT_PCT_WIDTH = 0.33
# ── Conviction-scaled DISCOUNT gate (v-convdiscount 2026-07-28) ─────────────
# MEASURED on QQQ's full log: debit ratios 0.41-0.64 (min 0.41, cluster
# 0.47-0.53) against a flat 0.33 ceiling -> the gate rejected 100% of setups that
# reached it. Three butterflies exist in the entire fleet archive. Proximity was
# NOT the constraint: zero "too far from pin" rejections were ever logged.
# The tent is expensive because price sits near the pin. With high conviction it
# STAYS pinned, paying more is justified; with low conviction, demand the cheap
# tent. So the ceiling scales from the strict floor to a high-conviction ceiling.
# Bounds are set against the OBSERVED conviction range (0.000-0.582), NOT 0-1.
# ALL PRIOR -- refit from the debit-ratio ledger, which logs every evaluation.
BUTTERFLY_MAX_DEBIT_PCT_WIDTH_HICONV = float(os.environ.get("OT_BFLY_DEBIT_HICONV", "0.50"))

# ── BFLY.3 (2026-08-15) — THE FLAT DEBIT CEILING ─────────────────────────────
# Max profit is `wing - debit`, so at ratio 0.50 you risk exactly what you can
# win. **0.50 IS THE STRUCTURE'S OWN BREAK-EVEN**, not a fitted threshold — it
# needs no holdout and cannot be overfit. Above it the payoff is upside-down.
# Replaces the conviction-scaled ceiling: measured fleet-wide across 29 boxes,
# the conv->ratio slope is POSITIVE on 5 of 7 sampled symbols, so scaling up
# with conviction paid MORE exactly where the trade was WORSE. It also cost real
# trades — SMH had 46 setups at mean ratio 0.379 and fired 3.
BUTTERFLY_DEBIT_CEILING = float(os.environ.get("OT_BFLY_DEBIT_CEILING", "0.50"))
BUTTERFLY_DISC_CONV_LO = float(os.environ.get("OT_BFLY_DISC_CONV_LO", "0.30"))
BUTTERFLY_DISC_CONV_HI = float(os.environ.get("OT_BFLY_DISC_CONV_HI", "0.55"))
DIRECTIONAL_ONLY_INSTRUMENTS = set(STRIKE_INCREMENTS) - FULL_STRATEGY_INSTRUMENTS
DIRECTIONAL_ONLY             = INSTRUMENT in DIRECTIONAL_ONLY_INSTRUMENTS
CONTRACT_MULTIPLIER = 100

# ─── ACCOUNT & RISK ───────────────────────────────────────────────────────────

RISK_PER_TRADE_USD  = float(os.environ.get("OT_RISK_USD", "200"))
# Daily loss limit: halt NEW entries when the day's NET realized P&L is down by
# this much. Defaults to one trade's risk; override via OT_DAILY_LOSS_LIMIT.
DAILY_LOSS_LIMIT_USD = float(os.environ.get("OT_DAILY_LOSS_LIMIT", str(RISK_PER_TRADE_USD)))
# v2.0 (runner refinement): the universal directional premium floor, now 40%
# by default. On 0DTE, gamma routinely wicks a healthy trade -25% while the
# thesis (impulsive origin) is intact — the old floor front-ran the structure
# stop and stopped winners on noise. Sizing is FULL-PREMIUM based (risk unit =
# position size), so at $1000 positions a floored trade now costs ~$400 (was
# ~$250) — set OT_DAILY_LOSS_LIMIT with that in mind. Butterflies keep their
# own 25% (their 20%-of-max TP can't carry a 40% stop); condors keep
# CONDOR_STOP_LOSS_PCT. Env-tunable for A/B: OT_MAX_LOSS_PCT=0.25 restores.
# v4.21 (2026-08-19) — TIGHTENED 0.40 -> 0.25 BY OPERATOR DIRECTION, and the
# SAME CHANGE SHIPS TO THE LEGACY FLEET so the SMC box and its peers are still
# an apples-to-apples comparison. Changing the floor on one arm only would
# have made every subsequent P&L difference unattributable.
# ⚠️ This supersedes the v2.0 reasoning below, which is left intact because it
# is the argument this change overrules, not a mistake: v2.0 widened the floor
# on the grounds that 0DTE gamma wicks a healthy trade -25% while the
# impulsive origin is intact. That reasoning assumed the STRUCTURE STOP was
# doing the real work underneath. It now genuinely is for ORB, Continuation,
# TC.6 and — as of exit_engine v4.23 — the ICT suite, so the premium floor can
# go back to being a disaster backstop rather than a second stop.
# One floored $1000 position now costs ~$250 (was ~$400).
MAX_LOSS_PCT        = float(os.environ.get("OT_MAX_LOSS_PCT", "0.25"))
BUTTERFLY_STOP_LOSS_PCT = 0.25   # pin plays keep the tight floor (see above)
# Max-loss stop applied to an ADOPTED position (one discovered open at the
# broker on a LIVE restart with no DB plan). Defaults to the same threshold
# every strategy already respects, so an adopted position exits at the same
# "degree of red" our normal stops would have. Long: stop = entry*(1-pct);
# short: stop = entry*(1+pct).
ADOPTED_STOP_PCT    = float(os.environ.get("OT_ADOPTED_STOP_PCT", str(MAX_LOSS_PCT)))
# Master switch for LIVE broker<->DB position reconciliation (adopt / keep /
# phantom-close + v3.6 phantom P&L recovery).
# v1.8: FOLLOWS TRADING MODE by default — flipping to LIVE via configure.sh
# (or any other way OT_PAPER_TRADING=False is set) enables reconciliation
# automatically; nothing extra to remember on go-live. Paper stays OFF (paper
# never reconciles; the DB is truth there). An explicit OT_BROKER_RECONCILE
# =True/False still overrides in either direction — the escape hatch if
# get_open_option_positions() ever needs re-verifying on a live box.
_reconcile_env = os.environ.get("OT_BROKER_RECONCILE", "")
if _reconcile_env in ("True", "False"):
    BROKER_RECONCILE_ENABLED = _reconcile_env == "True"
else:
    BROKER_RECONCILE_ENABLED = os.environ.get("OT_PAPER_TRADING", "True") == "False"
# v3.6: minutes between intraday reconcile sweeps (was hardcoded 30). On top of
# these interval slots, dedicated wind-down sweeps fire at 15:45, 15:50, and a
# final 15:57 pass — the post-flatten truth check (the main loop goes dormant
# at 16:00, so the last sweep must land inside the hard-close window).
BROKER_RECONCILE_INTERVAL_MIN = int(os.environ.get("OT_BROKER_RECONCILE_INTERVAL_MIN", "10"))

# ─── PAPER TRADING ────────────────────────────────────────────────────────────

PAPER_TRADING       = os.environ.get("OT_PAPER_TRADING", "True") != "False"

# ─── VIX / IV THRESHOLDS ──────────────────────────────────────────────────────

VIX_LOW_THRESHOLD           = 15
VIX_ELEVATED_THRESHOLD      = 20
VIX_CRISIS_THRESHOLD        = 30
VIX_BUTTERFLY_DISABLE       = 20
VIX_BUTTERFLY_HALF_SIZE     = 15
VIX_NO_ENTRY_THRESHOLD      = 30
IV_RANK_HIGH                = 50

# ─── SESSION / TIME RULES ─────────────────────────────────────────────────────

TIMEZONE                    = "US/Eastern"
RTH_OPEN_ET                 = (9, 30)
RTH_CLOSE_ET                = (16, 0)
HARD_CLOSE_ET               = (15, 45)
# v3.8: the end-of-day flatten OPENS here and posts mark-limits (re-priced each
# ~15s tick) so positions can close without paying the spread; at HARD_CLOSE_ET
# it crosses unconditionally. An unfilled 0DTE at the bell is an expiry (and an
# assignment on a short leg), not an overnight hold — so the cross is absolute.
FLATTEN_WINDOW_OPEN_ET      = (15, 40)
ORB_NO_ENTRY_AFTER_ET       = (11, 0)   # ORB-SCOPED: ORB entries valid until 11:00 ET.
                                        #   Also the ARM condition for sweep reversal.
# ── AFTERNOON DEBIT BLOCK (2026-08-13, operator's directive) ─────────────────
# "no long contracts in the afternoon unless they're part of a vertical spread
# or a butterfly."  MECHANISM: on 0DTE, an afternoon debit needs a large move
# just to clear decay, and the payability ratio (available move / breakeven)
# falls monotonically from the open in EVERY symbol. Measured cost of the window
# it closes: 10:00 -$8,715 · 11:00-14:00 -$1,539.50 · 13:00 -$4,138 against a
# whole-book +$463 (843 trades, 15 sessions).
# EXEMPT BY DESIGN: IronCondorStrategy (credit verticals) and ButterflyStrategy
# (a debit, but deliberately crafted OTM at a deep discount toward a GEX pin —
# it is the operator's named exception, and its own window already starts 12:00).
# NOT A CUTOFF ON MANAGEMENT: open positions are unaffected, this blocks ENTRIES.
# OPERATOR, 2026-08-13, verbatim: "The only other Long that can fire is either
# part of a butterfly or an iron condor vertical spread from 11 o'clock onwards."
# MEASURED, 843 trades / 15 sessions: open 09:30-10:00 +$10,717.50 against
# 10:00-11:00 -$8,715 and 11:00-14:00 -$1,539.50, on a whole book of +$463.
# ⚠️ THE HOLE THIS LEAVES IS DELIBERATE AND NAMED: in a TRENDING afternoon the
# condor is correctly blocked (it self-gates to RANGING at main.py:1607 and
# cancels Leg 1 on a directional flip) and the butterfly needs PINNING GEX, so
# NOTHING fires. That window belongs to the trend credit spread (TC.6), which is
# NOT BUILT. Until it is, a trending afternoon is dark ON PURPOSE — which is the
# point: the measured cost of that window is negative.
# G8 (v4.20) — DEFAULT MOVED 11:00 -> 11:30. The Silver Bullet window runs to
# 11:30, so an 11:00 cutoff would have silently killed its last thirty minutes
# (operator, 2026-08-18). Still env-overridable via OT_DEBIT_CUTOFF_ET, and the
# GLOBAL 14:00 no-entry ceiling below still applies to EVERYTHING, credits
# included.
DEBIT_DIRECTIONAL_CUTOFF_ET = tuple(int(x) for x in
                                    os.environ.get("OT_DEBIT_CUTOFF_ET", "11:30").split(":"))
# G8 (v4.20) — the seven ICT setups are all debit-directional in v1.0, so each
# is registered BY NAME per handoff §3.1: a new directional debit strategy that
# is not in this set silently bypasses the cutoff. The GEX-pin butterfly is
# absent DELIBERATELY — absence is how it stays exempt, and it is separately
# window-gated by BUTTERFLY_ENTRY_START_ET / BUTTERFLY_ENTRY_CUTOFF_ET.
DEBIT_DIRECTIONAL_STRATEGIES = {"ORBStrategy", "ContinuationStrategy", "SweepReversal",
                                "ICTSilverBullet", "ICTJudasPO3", "ICTModel2022",
                                "ICTSweepMSS", "ICTBreakerUnicorn",
                                "ICTOTEConfluence", "ICTOBFVG"}
DEBIT_BLOCK_ACTIVE          = os.environ.get("OT_DEBIT_BLOCK_ACTIVE", "1") == "1"

GLOBAL_NO_ENTRY_ET          = (14, 0)   # GLOBAL: no new 0DTE entries after 14:00 ET,
                                        #   ANY strategy. Read by utils/time_utils.
BUTTERFLY_ENTRY_CUTOFF_ET   = (14, 0)   # was 15:00 and unreachable (see v3.1 header)
BUTTERFLY_ENTRY_START_ET    = (12, 0)   # No butterfly entries before noon
ORB_WINDOW_MINUTES          = 5

# ─── ORB STRATEGY ─────────────────────────────────────────────────────────────

ORB_MAX_RETEST_BARS         = 12
ORB_TP_MULTIPLIER           = 1.0
FED_DAY_ORB_BOOST           = 0.20

# ─── ORB REGIME GATE SWITCH (v3.2) ────────────────────────────────────────────
# When True, a CONFIRMED ORB break+retest fires regardless of the regime label —
# including UNKNOWN and SWEEP_REVERSAL. The ORB engine's break+retest is self-
# validating (the classifier does not even test for it), so the label is not
# consulted for the go/no-go; only the setup scorer's B-threshold and the ORB
# engine's own structure gate it. Under UNKNOWN the regime_conviction dimension
# simply contributes 0 to the score. Under SWEEP_REVERSAL, ORB wins (the engine
# no longer defers its OPEN to the sweep). Set False to restore strict v2 gating
# (UNKNOWN/sweep block ORB). Every ORB that fires under UNKNOWN is logged with
# regime=UNKNOWN — labeled tape for the shadow observer.
# v4.21 (2026-08-19) — ORB IS BLOCKED UNDER RANGING. The operator's call:
# that cell is the conclusive loss leader. A flag rather than a deletion from
# _orb_ok_regimes, for three reasons — the decision stays READABLE, it is
# reversible with an env var if the measurement says otherwise, and the
# refusal can be JOURNALED so "ORB did not fire" is distinguishable from "ORB
# was not allowed to". A silent deletion would have produced the second while
# looking like the first.
ORB_BLOCK_RANGING   = os.environ.get("OT_ORB_BLOCK_RANGING", "1") == "1"
ORB_FIRES_REGARDLESS_OF_REGIME = True
# When snapping an ORB strike target to the nearest available strike, break
# toward the "higher" (more ITM / participation) or "lower" (further OTM) delta.
ORB_STRIKE_DELTA_BIAS       = "lower"

# ─── SWEEP REVERSAL STRATEGY ──────────────────────────────────────────────────

# Sweep OTM strike delta scales INVERSELY with reversal strength (conviction):
# a strong snap-back can carry a far-OTM (low-delta) strike ITM for max leverage;
# a weak move needs a nearer, higher-delta strike to actually participate.
SWEEP_DELTA_STRONG          = 0.12   # conviction -> 1.0 : leveraged but REACHABLE
SWEEP_DELTA_WEAK            = 0.30   # conviction -> 0.0 : near-ATM, participation
SWEEP_DELTA_TOLERANCE       = 0.04   # acceptable band around the target delta

# ── SWP.1 — sweep is an EVENT, not a regime (2026-08-07, operator's ruling) ──
# The trade required the committed L2 label to be SWEEP_REVERSAL, a label that
# wins 0.4% of live ticks and is exactly 0 on 96% of them, so the trade was
# effectively off. It now gates on the L1 _sweep SETUP SCORE instead.
#
# WHY A LOW FLOOR IS THE CORRECT READING OF THE SPEC, not laziness: _sweep's
# THREE HARD VETOES are veto_loc (a NAMED level), veto_reclaim (rejected back
# through it) and veto_accept (not accepted beyond). All three must pass for the
# score to be non-zero at all — which is precisely "a move into a named
# liquidity pool accompanied by a rejection". Every non-zero tick therefore
# ALREADY qualifies; magnitude above zero is quality grading, not qualification.
#
# Corpus, 19 sessions / 523 symbol-days: non-zero on 4.0% of ticks; of those
# p50=0.016, p90=0.154, max=0.717. This floor admits the top ~29% of non-zero
# ticks (78 symbol-days, ~28 ticks/symbol-day before the strategy's own cooldown
# and position checks collapse them into far fewer entries).
#
# A PRIOR, NOT A FIT — deliberately permissive for the collection phase and
# meant to be TIGHTENED once live fires exist. The corpus can say how OFTEN a
# floor admits; it cannot say whether those are good trades.
# Permissiveness cannot steal from other setups: sweep is Priority 2.5 behind
# `if signal is None`, so ORB and Continuation always get first refusal.
SWEEP_SETUP_FLOOR = float(os.environ.get("OT_SWEEP_SETUP_FLOOR", "0.05"))

# ── SWP.2 — SWEEP SHORTS GET THEIR OWN, HIGHER FLOOR (2026-08-07) ─────────────
# Long and short sweeps are not the same trade and the data says so on THREE
# independent measures over 12 sessions:
#   Sweep Reversal Long   27 trades · 81% WR · +$2,844 · 4% never-favourable ·
#                         forward drift BUILDING +0.001 → +0.081 → +0.314 with
#                         52% → 56% → 67% of trades positive
#   Sweep Reversal Short   6 trades · 33% WR · −$1,403.50 · 33% never-favourable ·
#                         drift −0.148 → −0.215 → −0.290, 33% positive
# n=6 is THIN and this is NOT a fit — it is a PRIOR, and what earns it is that
# the MECHANISM agrees: the 2026-07-27 PLTR incident was exactly a short
# reversal into a +7.2% up-trending tape, which is why `trend_opp` exists.
#
# ⚠️ SAY THE HONEST THING ABOUT THIS NUMBER: SWEEP's score is CAPPED near 0.265
# (measured max on the 08-07 replay; it is the only scorer with an age-decay
# soft-necessary, half-life 3 bars). A short floor of 0.20 therefore fires only
# in the top sliver of sweep scores and NEAR-DISABLES shorts. That may well be
# correct at −$233/trade — but it is a near-disable wearing a threshold, and it
# should be read that way rather than as a tuning dial.
# Longs are untouched at 0.05. Set equal to SWEEP_SETUP_FLOOR to restore the
# single-floor behaviour.
SWEEP_SETUP_FLOOR_SHORT = float(
    os.environ.get("OT_SWEEP_SETUP_FLOOR_SHORT", "0.20"))

# ── CNT.3 — THE HANDOFF DOES NOT FIRE UNDER COMPRESSION (2026-08-07) ──────────
# COMPRESSION/Continuation is 39 trades, 28% WR, −$454, and COMPRESSION is the
# WORST never-favourable cell in the book: 80% (LIFT 1.98, n=45).
# Continuation cannot enter on a compression LABEL — the direction branches
# require TRENDING_BULL/BEAR or BREAKOUT — so all 39 of those are RUNAWAY
# HANDOFFS, which ignore the label by design.
# THE MECHANISM IS A CONTRADICTION: a runaway asserts EXPANSION while the label
# asserts COILING. The handoff's licence to ignore the label is what makes it
# valuable after a real runaway; this is the one place it clearly costs.
# OT_CONT_HANDOFF_IN_COMPRESSION=1 restores the old behaviour.
CONT_HANDOFF_BLOCK_COMPRESSION = os.environ.get(
    "OT_CONT_HANDOFF_IN_COMPRESSION", "0").strip().lower() in ("0", "false", "no", "off")
SWEEP_MIN_REJECTION_PCT     = 0.003
SWEEP_MAX_AGE_BARS          = 8
# Entry-window tuning (separate pass from detection). The recovery window is now
# ATR-aware: a fast reversal on a volatile name that has already moved isn't
# rejected as "too far" — the window is the LARGER of a floor % or a multiple of
# ATR%. BOS lookback is configurable and also accepts a BOS that printed on the
# just-closed candle (so a 1-tick-late evaluation doesn't miss it).
SWEEP_MAX_RECOVERY_PCT      = 0.02   # floor recovery window (fraction of sweep price)
SWEEP_RECOVERY_ATR_MULT     = 1.5    # ...or this × ATR%, whichever is larger
SWEEP_BOS_LOOKBACK          = 5      # 1m candles used as the BOS structure reference

# ─── BUTTERFLY STRATEGY ───────────────────────────────────────────────────────

BUTTERFLY_TP_PCT            = 0.20   # 20% of max profit
BUTTERFLY_MAX_HOLD_MIN      = 150

# Fixed wing widths by instrument
BUTTERFLY_WING_SPX          = 25     # 25-point wings on SPX
BUTTERFLY_WING_QQQ          = 5      # $5 wings on QQQ/SPY

# GEX pin proximity gate: price must be within 1x expected move of pin
# Formula: underlying × VIX% × sqrt(hours_remaining/6.5) / sqrt(252)
# Computed at runtime in butterfly_strategy.py
BUTTERFLY_GEX_PIN_PROXIMITY_MULT = 1.0  # Multiplier on expected move

# ─── IRON CONDOR STRATEGY ─────────────────────────────────────────────────────
# Fallback for RANGING regime when no GEX pin is available for a butterfly.
# Strike selection is BOLLINGER-BAND ANCHORED — there is NO delta anywhere in the
# condor path (short call = lowest liquid strike at/above the BB upper band; short
# put = highest liquid strike at/below the BB lower band). Delta is deliberately
# excluded: it is relative to where price sits, not to the actual range boundary.
# The expected-move guardrail is a sanity check only, not a parallel sizing method.

CONDOR_WING_WIDTH_SPX       = 5      # Narrow wings — affordable verticals (was 25)
CONDOR_WING_WIDTH_QQQ       = 5      # Fixed wing width in points on QQQ/SPY
CONDOR_EXPECTED_MOVE_GUARDRAIL_MULT = 1.2  # Short strikes must be within this x EM
CONDOR_EM_FLOOR_FRAC = 0.80   # short strike must sit >= this * expected_move from spot
CONDOR_PROXIMITY_STRIKES    = 2      # (legacy) strikes inside the short — superseded by CONDOR_TRIGGER_APPROACH
# Fraction of the distance from the BB midline to each short strike that price
# must travel before that side's spread fires. Higher = price must get closer
# to the band before selling (richer premium, fewer fills). Env-tunable for A/B.
CONDOR_TRIGGER_APPROACH     = float(os.environ.get("OT_CONDOR_TRIGGER_APPROACH", "0.65"))
                                     # (2 strikes = 10pt on SPX, $2 on QQQ — scales naturally)
CONDOR_STOP_LOSS_PCT        = 0.25   # Exit if spread value rises to 125% of credit received
# ── Condor leg management, v2 (2026-07-23) ────────────────────────────────
# A RATCHET IS NOT A TAKE-PROFIT. A TP closes the position and so structurally
# guarantees the condor never forms: the move that makes side one profitable IS
# the move that carries price to the far band and triggers side two. So before
# the entry cutoff we only ever move the STOP and leave the leg open.
CONDOR_RATCHET_BE_AT        = float(os.environ.get("OT_CONDOR_RATCHET_BE", "0.20"))   # +20% -> stop to breakeven
CONDOR_RATCHET_LOCK_AT      = float(os.environ.get("OT_CONDOR_RATCHET_LOCK_AT", "0.40"))
CONDOR_RATCHET_LOCK_PCT     = float(os.environ.get("OT_CONDOR_RATCHET_LOCK_PCT", "0.20"))
# Hard TP applies ONLY after CONDOR_ENTRY_CUTOFF_ET, when no second leg can
# fire and the structure is definitively dead. Backtest on 18 standalone legs:
# TP@25% turned -$242.77 into -$8.43; 30% was +$14 better = noise; 40%/50% worse.
CONDOR_TP_PCT               = float(os.environ.get("OT_CONDOR_TP_PCT", "0.25"))
# Min hold before the TP is even evaluated — a QUOTE-NOISE filter, not a
# structure mechanism. On a 0DTE spread with a nickel-wide bid/ask a +25% mark
# move can be one tick of noise. Kept modest (10m, not theta's 20m) because
# price moving away from the short strike is a legitimate fast gain (delta).
CONDOR_TP_MIN_HOLD_MIN      = float(os.environ.get("OT_CONDOR_TP_MIN_HOLD", "10"))
CONDOR_NICKEL_CLOSE         = 0.05   # Close leg when spread value decays to $0.05
# 2026-07-23: 11:00 -> 11:11. Bollinger needs BB_PERIOD(20) 5-minute bars, so
# the first valid bb_middle is ~11:05 ET (verified on the 07-22 tape). The old
# 11:00 open meant the first ten minutes of the condor window ran with
# bb_middle == 0, and decide() falls back to `mid = current_price` in that case
# — i.e. strikes and triggers computed with NO volatility reference at all.
# 11:11 clears 11:05 with margin and removes that fallback path entirely.
# ── CONDOR PITCHFORK ANCHOR (2026-08-13, operator directive) ─────────────────
# "The tine should be the trigger for 'rich premium' and the short strike should
#  be just outside the range of the rail at the most liquid strike where price
#  has still not exceeded... consider the condor off the table if we don't have
#  guardrails. That is the insurance policy that eliminates a bad decision in an
#  unpredictable session."
# DAILY fork, deliberately: "It's a guardrail, not the road." A daily fork is
# invalidated only by DAILY closes, so an intraday session cannot kill it — the
# rail a spread was sold against is still there while the spread is open. The
# hourly fork has a measured p50 lifetime of 5 bars and a k=3 confirmation lag,
# so it can be born mid-window and dead before the close: that re-anchors
# intraday, which is another indicator, not a guardrail.
# NO FORK -> NO CONDOR. Accepted volume cost, operator's call: "I'm ok with not
# getting the condor if the fork isn't there."
CONDOR_PITCHFORK_ANCHOR     = os.environ.get("OT_CONDOR_PF_ANCHOR", "1") == "1"
CONDOR_REQUIRE_FORK         = os.environ.get("OT_CONDOR_REQUIRE_FORK", "1") == "1"
CONDOR_PF_TIMEFRAME         = os.environ.get("OT_CONDOR_PF_TF", "daily")
# Slope magnitude (fraction of price per bar) below which the fork is treated as
# FLAT and leg order falls back to proximity. A sign alone is not a slope: a
# fork drifting 0.001% a bar is noise, and ordering legs off its sign would be
# reading a coin flip as structure.
CONDOR_PF_FLAT_SLOPE        = float(os.environ.get("OT_CONDOR_PF_FLAT", "0.00002"))

# ── POP FLOOR (2026-08-13, operator directive) ───────────────────────────────
# "Selling late afternoon premium on zero DTE is incredibly risky so just make
#  sure that the factors appear favorable before executing. There should be a
#  reasonable expectation of trade success better than 50-50... somewhere near
#  the 70 to 80% range."  And, on tone: "this approach is already inherently
#  risky. I'm aware of that and I'm comfortable with it so don't be too
#  restrictive."  Hence a FLOOR at the bottom of his band, not the top.
# POP = P(terminal close on the safe side of the short strike)
#     = Phi(z),  z = distance_to_strike / (sigma_per_bar * sqrt(bars_left))
# TIME IS THE POINT: the same distance is a LARGER z late in the session, so a
# strike that fails at 11:15 can pass at 14:30 on identical geometry. A
# fixed-percent rule cannot express that and this is why the offset tables were
# time-blind.
# ⚠️ VALIDATED OUT-OF-SAMPLE, not fitted: on TC.7's handoff arm every offset
# with terminal-OK BELOW 70% had NEGATIVE EV (58%/-0.23, 54%/-0.33, 63%/-0.24,
# 67%/-0.09) and every offset at/above 76% was POSITIVE (+0.33/+0.32/+0.35).
# The sign flips inside the operator's stated band.
CONDOR_MIN_POP              = float(os.environ.get("OT_CONDOR_MIN_POP", "0.70"))
# Reject a short leg quoted wider than this fraction of its mid. A RANKING never
# refuses — it returns the least-bad strike even when every candidate is broken.
# On 0DTE a nickel of noise on a wide quote trips the 25%% stop on the QUOTE
# rather than on price. 0.25 is a stated PRIOR reasoned from an ADJACENT
# population (factor_sweep's worst continuation quintile ran spread_pct_of_mid
# 0.13-0.88 at -$37/trade; the two best bands sat under 0.043) — debit entries,
# not condor shorts. The rejected-leg log is what would fit it properly.
CONDOR_MAX_QUOTE_WIDTH      = float(os.environ.get("OT_CONDOR_MAX_QUOTE_WIDTH", "0.25"))

# ── RATCHET SCOPE (2026-08-13, operator ruling) ──────────────────────────────
# "the ratchet is inappropriate for this trade if the condor is fully formed.
#  It should only be in effect if there's one side open."  And:
# "don't close a leg if it hasn't been tested - that's what the roll is for."
# THE DEFECT IT FIXES: the base -25% stop only ever fires on the TESTED side
# (spread value rises as price approaches your short). But the ratchet tightens
# the UNTESTED side's stop to breakeven at +20% and +20% locked at +40% —
# precisely because it is WINNING. On the reversal the tested side stops at -25%
# AND the untested side hits its ratcheted stop, so a leg price never went near
# is closed by a stop that exists only because it was profitable. That is the
# double-stop: 5 of 14 condor symbol-days had BOTH sides stopped. It also fires
# BEFORE the roll can ever be used, because the roll needs a tested side.
# WHAT IS PRESERVED: `condor_stop` went 0% -> 19% win after the ratchet shipped,
# but that evidence came mostly from STANDALONES (18 of 46 legs never got a
# second side). Scoping to standalone keeps the gain where it was measured and
# removes it where it disassembles a working structure.
# ⚠️ ACCEPTED CONSEQUENCE: an untested leg that runs to +40% and reverses now
# gives it back rather than locking +20%. That is the price of not taking apart
# a formed condor.
CONDOR_RATCHET_STANDALONE_ONLY = os.environ.get(
    "OT_CONDOR_RATCHET_STANDALONE_ONLY", "1") == "1"

# ── CREDIT VERTICALS HOLD TO 15:45 (2026-08-13, operator ruling) ─────────────
# The flatten ladder opens at FLATTEN_WINDOW_OPEN (15:40) and posts mark-limits
# until the 15:45 cross, so a DEBIT position can close without paying the
# spread. That ladder is why it is not moved: opening it at 15:45 would leave
# zero time for the limit phase and force EVERY end-of-day exit marketable —
# the exact failure time_utils v3.8 was written to fix, and expensive on a book
# whose widest spread quintile already costs -$37/trade.
# BUT THE SIGN IS OPPOSITE FOR A CREDIT VERTICAL. A long debit sitting at 15:40
# is decaying to ZERO, so five more minutes cost the holder and the limit phase
# is pure upside. A SHORT vertical is decaying TOWARD the holder, and 15:40-15:45
# is the steepest part of that curve. Operator: "It's 5 more minutes of
# exponentially rising profit curve."
# ⚠️ NOT held past 15:45, deliberately. Every instrument here except SPX is
# AMERICAN-STYLE and PHYSICALLY SETTLED, so a spread finishing BETWEEN the
# strikes assigns the short and leaves an unhedged overnight stock position —
# "defined risk" is true at settlement, not through assignment. The paper engine
# has no assignment model and would never show it, which is the worst kind of
# clean result.
# ⚠️ COST, stated rather than hidden: verticals then close AT 15:45 with no
# limit phase of their own, so they pay the crossing. A few cents on a spread
# that has already decayed; a worse fill on one still near its short strike.
VERTICAL_HOLD_TO_ET         = (15, 45)
VERTICAL_HOLD_TO_CLOSE      = os.environ.get("OT_VERTICAL_HOLD_1545", "1") == "1"
# Minutes per bar of the ATR feeding sigma. 5m frame by default; wrong here
# scales sqrt(T) and silently moves every POP.
CONDOR_POP_BAR_MIN          = float(os.environ.get("OT_CONDOR_POP_BAR_MIN", "5"))

CONDOR_ENTRY_START_ET       = (11, 11)  # No condor entries before 11:11 (BB must be valid)
CONDOR_ENTRY_CUTOFF_ET      = (14, 0)   # Standard entry cutoff

# ─── EXIT MANAGEMENT ──────────────────────────────────────────────────────────

TRAIL_ACTIVATION_PCT        = 0.50
TRAIL_LOCK_PCT              = 0.25

# ─── LONG-OPTION THETA PROTECTION + FVG PROFIT TRAIL ──────────────────────────
# Theta bleed: exit a PROFITABLE long when the projected time decay over the next
# THETA_LOOKAHEAD_MIN minutes would erase the current unrealized gain (direction
# hasn't gone against us — the option is just handing the profit back to time).
THETA_LOOKAHEAD_MIN         = 20     # minutes of decay to project
RTH_MINUTES                 = 390    # 6.5h session, to convert daily theta → per-min
# FVG-anchored trailing stop for longs: once armed, the stop parks at the FAR
# edge of the nearest unfilled in-favor 1m FVG (room to pull back INTO the gap
# for continuation); a close beyond the gap exits. Falls back to a % lock.
FVG_TRAIL_ARM_PCT           = 0.20   # arm once the trade is up this much
FVG_TRAIL_LOCK_PCT          = 0.80   # premium floor = 80% of current when no FVG
# v2.0 runner refinements (all env-tunable for paper A/B):
# 5-minute FVGs anchor the trails instead of 1-minute — structurally
# meaningful gaps, natural gamma room; 1m stays for structure stop and BOS.
USE_5M_FVG_TRAIL            = os.environ.get("OT_USE_5M_FVG_TRAIL", "True") != "False"
# An FVG-derived floor may never sit tighter than this fraction of current
# premium — a gap hugging price can't turn the runner leash into a tripwire.
FVG_FLOOR_MAX_LOCK_PCT      = float(os.environ.get("OT_FVG_FLOOR_MAX_LOCK_PCT", "0.90"))
# Post-target no-FVG fallback lock. Was 0.85 — TIGHTER than the pre-target
# 75% ratchet, an inverted leash that harvested proven runners on one gamma
# wick. Now matches the pre-target trail.
POST_TARGET_TRAIL_LOCK_PCT  = float(os.environ.get("OT_POST_TARGET_TRAIL_LOCK_PCT", "0.75"))
# Sweep reversals get the ORB post-target trail instead of the +100%
# guillotine (the one hard TP among directionals). False restores target_hit.
SWEEP_POST_TARGET_TRAIL     = os.environ.get("OT_SWEEP_POST_TARGET_TRAIL", "True") != "False"

POLL_INTERVAL_SECONDS       = 15

# ─── REGIME CLASSIFICATION ────────────────────────────────────────────────────

ADX_TREND_THRESHOLD         = 25

# ── CNT.1 — continuation under BREAKOUT_VOLATILE (2026-08-07, operator's call) ─
# Standalone continuation was barred under BREAKOUT for a structural reason, not
# a quality one: `continuation_strategy` derives DIRECTION FROM THE LABEL
# (TRENDING_BULL -> long, TRENDING_BEAR -> short) and BREAKOUT_VOLATILE asserts
# volatility EXPANSION without saying which way, so no branch could assign one.
# The runaway handoff already solves this by taking direction from the ORB.
# This does the same thing from the trend engine's own vote.
#
# WHY A SEPARATE ADX FLOOR RATHER THAN THE CONVICTION FLOOR: under a non-trending
# label `_label_trending` is False, so continuation's `CONTINUATION_CONV_FLOOR`
# check is SKIPPED ENTIRELY — the same hole the handoff path has. Reusing
# `regime.conviction` would be worse than nothing, since under BREAKOUT it is
# BREAKOUT's conviction, not the trend's. The direction is coming from the trend
# engine, so the quality bar must come from there too.
#
# DEFAULT = ADX_TREND_THRESHOLD (25), the same bar the rest of the system uses to
# call a trend a trend. A PRIOR, not a fit — deliberately permissive for the
# collection phase per the operator ("to gather data").
# Entries take setup_type `trend_continuation_breakout` so the rollup can score
# this path SEPARATELY from _standalone and _handoff. Without that split the
# data this is being turned on to collect would be unreadable.
# ── CNT.2 — the INSURANCE gate for continuation (2026-08-07, operator's call) ─
# BOS (exit_engine 2b) is continuation's thesis invalidator and it is
# deliberately UNGATED on P&L — but `BOSTracker.protected_level` starts None and
# is only set once the trade makes a new CLOSING HIGH past entry. So BOS is
# structurally BLIND until the trade goes favourable in the underlying, and that
# blind window is exactly where the 45 max_loss_floor trades die at −29% with
# MFE +1%.
#
# THE LEVEL IS ALREADY COMPUTED AND STORED, and until now was dead in the
# decision path: continuation_strategy:447/450 stamps
# `underlying_stop = gap.bottom - 0.5*atr` (long) / `gap.top + 0.5*atr` (short)
# on every entry, trade_logger:206 persists it, and the ONLY reader was
# query.py:233 — for display.
#
# WHY STRUCTURAL AND NOT A TIGHTER PREMIUM FLOOR: a premium-percent stop on 0DTE
# measures gamma, not thesis. The floor sweep proved a tighter one nets ~zero
# because it cuts winners that merely dip (peak is late, drawdown is early).
# This level is the ENTRY PREMISE INVERTED — continuation enters on a pullback
# INTO an unfilled 5m FVG expecting resumption, so price closing beyond the far
# edge plus a half-ATR buffer means the pullback was the reversal continuing.
#
# WHY IT DOES NOT REOPEN THE JULY DECISION: `underlying_stop` was rejected as
# THE exit for two reasons — "a gap fill is NOT trend failure" and "the FVG
# level is STATIC so it protects nothing once the trade works". Neither applies
# to a gate that lives ONLY while BOS has no protected level and yields the
# instant it does. It fills the hole that decision knowingly left; it does not
# overturn it.
#
# ⚠️ THE LEVEL HAS NEVER BEEN READ BY ANYTHING THAT TRADES, so it has no track
# record. Exits are tagged `insurance_stop` so the cross-day rollup scores this
# path separately from max_loss_floor and bos_exit — without that split the data
# this exists to collect is unreadable. Kill switch: OT_CONT_INSURANCE=0.
CONT_INSURANCE_STOP = os.environ.get(
    "OT_CONT_INSURANCE", "1").strip().lower() not in ("0", "false", "no", "off")

CONT_BREAKOUT_DIRECTION = os.environ.get(
    "OT_CONT_BREAKOUT_DIRECTION", "1").strip().lower() not in ("0", "false", "no", "off")
CONT_BREAKOUT_MIN_ADX   = float(os.environ.get("OT_CONT_BREAKOUT_MIN_ADX",
                                               str(ADX_TREND_THRESHOLD)))
ADX_RANGE_THRESHOLD         = 25   # v3.3 (2026-07-14): was 20 — closed the ADX
                                   # DEAD ZONE. _is_ranging required adx<20 while
                                   # _is_trending requires adx>=25, so ordinary
                                   # mild-drift tape at ADX 20-25 matched NO regime
                                   # and fell to UNKNOWN (hard no-trade). Measured
                                   # live: AAPL sat at ADX 19.26 — 0.74 under the
                                   # cliff — flickering RANGING<->UNKNOWN all session;
                                   # ~85% of fleet ticks were UNKNOWN on 07-13/07-14
                                   # and the fleet took ZERO trades for two days.
                                   # A range does not stop being a range because ADX
                                   # ticked 19.9 -> 20.1; it is the same regime with
                                   # LOWER CONVICTION. _ranging_conviction already
                                   # ramps on 1 - adx/ADX_RANGE_THRESHOLD, so raising
                                   # the gate to the trend line extends that ramp
                                   # across the gap: ADX 12 -> ~0.52, ADX 24 -> ~0.16.
                                   # Matches docs/REGIME_TRUTHS.md, which defines ADX
                                   # for RANGING as "any (allowed)" and strength as a
                                   # SOFT-NECESSARY ramp, never a cliff.
                                   # PRIOR — recalibrate from multi-day tape.
ATR_EXPANSION_MULTIPLIER    = 1.5
BB_WIDTH_COMPRESSION_PCT    = 0.20
SWEEP_REJECTION_CANDLES     = 3
EQUAL_LEVEL_PCT             = 0.001
REGIME_REASSESS_MINUTES     = 5

# ─── SETUP SCORING ────────────────────────────────────────────────────────────

GRADE_A_MIN_SCORE           = 0.78
GRADE_B_MIN_SCORE           = 0.55

# ── Brief nudge (2026-07-15) ─────────────────────────────────────────────────
# Signed pre-market move-probability prior applied post-sum in setup_scorer:
# +w·strength for ORB, -w·strength for neutrals, 0 for sweep reversal. This
# value is the hard cap (strength is 0..1). Small on purpose — a tie-breaker,
# never an override. Calibrate from the signal ledger once entries accrue.
BRIEF_CONVICTION_WEIGHT     = 0.05
GRADE_SIZE_MULTIPLIER       = {"A": 1.5, "B": 1.0}

# ─── VOLATILITY / TREND ───────────────────────────────────────────────────────

ATR_PERIOD                  = 14
ATR_STOP_MULTIPLIER         = 1.5
BB_PERIOD                   = 20
BB_STD                      = 2.0
EMA_FAST                    = 9
EMA_MID                     = 21
EMA_SLOW                    = 50
EMA_ANCHOR                  = 200

# ─── LIQUIDITY MAPPING ────────────────────────────────────────────────────────

EQUAL_HIGH_LOW_LOOKBACK     = 50
IMBALANCE_MIN_SIZE_PCT      = 0.002
LIQUIDITY_BUFFER_PCT        = 0.003

# ─── SIGNAL VALIDATION ────────────────────────────────────────────────────────

# ⚠️ UNWIRED — neither constant is imported anywhere. Both date to the initial
# commit and appear in no changelog. Retained deliberately as a record of intent:
#   MIN_RRR            — no risk/reward floor exists in the codebase. ORB's RRR is
#                        structural (stop = impulsive origin, target = 100% of range
#                        width), so it varies per setup and is currently ungated.
#   VWAP_FILTER_ACTIVE — implies a HARD VWAP gate. None exists. What is live is a
#                        SOFT score in setup_scorer (vwap_alignment, weight 0.15;
#                        a misaligned trade scores 0.25 on that dimension and can
#                        still clear the 0.55 B-threshold). NOTE: crypto_trader
#                        learned the opposite lesson the hard way — shorts above
#                        VWAP / longs below VWAP had to become HARD blocks. That
#                        lesson is NOT ported here. Open decision.
# E + F (2026-07-31) — WIRED AT LAST. Both were declared here at genesis and
# never read by anything; `VWAP_FILTER_ACTIVE = True` in particular sat as a
# hardcoded True that nothing consulted, so "the filter is on" was true in the
# config and false in the code for months.
#
# Both now ship env-tunable and DEFAULT OFF, which is a deliberate downgrade from
# the True above: house rule is evidence-decides, and neither has yet been
# convicted on collected data. They run as log-only counters until the retro
# ledger (signal_journal has carried vwap + price_vs_vwap since 07-18, and rrr
# since 07-31 via N.2) shows the blocked trades are net-negative. If they are
# not, these stay off and the counter IS the finding.
#
# A duplicate VWAP_FILTER_ACTIVE was briefly added higher in this file on 07-31
# and was silently overridden by this line — later assignment wins. Caught by a
# test asserting the default was False when it read True. One definition only.
MIN_RRR                     = float(os.environ.get("OT_MIN_RRR", "1.3"))
MIN_RRR_ACTIVE              = os.environ.get("OT_MIN_RRR_ACTIVE", "0") == "1"
VWAP_FILTER_ACTIVE          = os.environ.get("OT_VWAP_FILTER_ACTIVE", "0") == "1"

# ─── STRUCTURE ANALYSIS ───────────────────────────────────────────────────────

SWING_LOOKBACK              = 10
MIN_SWING_SIZE_ATR          = 0.5
FVG_MIN_SIZE_PCT            = 0.001
SR_TOUCH_MIN                = 2
SR_ZONE_PCT                 = 0.002
ORDER_BLOCK_LOOKBACK        = 20

# ─── ORDER EXECUTION ──────────────────────────────────────────────────────────

LIMIT_RETRY_SECONDS         = 30
LIMIT_IMPROVE_TICKS         = 1
# PAPER FILL FRICTION — v3.9 (2026-07-22), default 0.0.
# Applied AGAINST the trade, uniformly, by execution/limit_ladder (the single
# paper-pricing authority): debits pay (1+pct)·mark, credits receive
# (1−pct)·mark. Every paper path honours it — single leg, butterfly, condor
# leg, rolled vertical.
#
# WHY THE DEFAULT IS ZERO: live no longer sends market orders. Under the
# mark-limit policy (limit_ladder v1.2) live posts AT the mark and either
# fills there or does not fill at all, so a markup would make paper
# PESSIMISTIC on price while remaining optimistic on FILL RATE. The honest
# residual gap is no-fill risk, not slippage — and no-fill risk cannot be
# modelled as a price haircut.
#
# WHEN TO RAISE IT: after the tiny-account live shakedown measures real
# mark-limit fill quality, set OT_PAPER_SLIPPAGE_PCT to that number and every
# paper path degrades together — one lever, fleet-wide, no code change.
# (Pre-2026-07-22 paper history was booked at 0.01; set that value to compare
# like for like.)
PAPER_FILL_SLIPPAGE_PCT     = float(os.environ.get("OT_PAPER_SLIPPAGE_PCT", "0.0"))

# ─── TASTYTRADE API ───────────────────────────────────────────────────────────

TT_BASE_URL                 = "https://api.tastytrade.com"
TT_PAPER_BASE_URL           = "https://api.cert.tastyworks.com"

# ─── MACRO / FED CALENDAR ─────────────────────────────────────────────────────

FOREX_FACTORY_URL           = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
MACRO_FETCH_INTERVAL_MIN    = 60
FED_EVENT_KEYWORDS          = ["FOMC", "Fed", "Federal Funds Rate", "Powell"]

# ─── TIMEFRAMES ───────────────────────────────────────────────────────────────

TIMEFRAMES = {
    # PF.2 (2026-08-11) — RAISED 10 -> 60. The boxes were VERIFIED to already
    # hold 84 daily bars (2026-06-11 -> 08-11, checked on SPX and GLD); this
    # number was clipping the frame handed to the engines to 10, which is below
    # the pitchfork anchor rule's minimum and made RECENCY=40 unsatisfiable.
    # The history was never missing — the frame was. No new fetch, no new
    # timing, nothing for session_guard to collide with.
    "1d":  {"candles": 60,  "role": "bias"},
    "1h":  {"candles": 50,  "role": "structure"},
    # v4.1: 150, not 50. Below EMA_SLOW+5=55 the vote is NEUTRAL; below ~80 the
    # EMA-50 is re-seeded on the tail and materially wrong. See the header.
    "15m": {"candles": 150, "role": "trend"},
    "5m":  {"candles": 100, "role": "entry_context"},
    "1m":  {"candles": 60,  "role": "trigger"},
}

CACHE_STALENESS_SECONDS = {
    "1d":  3600,
    "1h":  300,
    "15m": 120,
    "5m":  30,
    "1m":  10,
}

# ─── NOTIFICATIONS ────────────────────────────────────────────────────────────

NOTIFY_ON_ENTRY             = True
NOTIFY_ON_EXIT              = True
NOTIFY_ON_CIRCUIT_BREAK     = True
NOTIFY_ON_REGIME_CHANGE     = True

# ─── DATABASE & LOGGING ───────────────────────────────────────────────────────

DB_PATH                     = os.path.expanduser("~/options-trader/trades.db")
LOG_LEVEL                   = "INFO"
LOG_FILE                    = os.path.expanduser("~/options-trader/bot.log")
LOG_ROTATION_MB             = 50

# ─── BOT IDENTITY ─────────────────────────────────────────────────────────────

BOT_NAME                    = os.environ.get("OT_BOT_NAME", "OptionsTrader")

# ─── LIVE EXIT FILL-CONFIRMATION (v3.5) ──────────────────────────────────────
# Governs ExitEngine._confirm_and_book_live_exit (live/cash mode ONLY — the
# paper path never reads these). See FABLE_SPEC_live_exit_fill_confirmation.md.

# Seconds between broker order-status polls while a close order is working.
LIVE_FILL_POLL_SECONDS      = float(os.environ.get("OT_LIVE_FILL_POLL_SECONDS", "2"))
# Total seconds to wait for a fill before cancelling and handing the position
# back to the caller's retry loop (15:45→16:00 hard-close retries + paging).
LIVE_FILL_DEADLINE_SECONDS  = float(os.environ.get("OT_LIVE_FILL_DEADLINE_SECONDS", "30"))
# Marketable-limit buffer ($/share THROUGH the mark) for multi-leg closes.
# tastytrade rejects MARKET orders on spreads, so closes go out as aggressive
# limits: vertical debit = min(mark + buffer, spread width); butterfly credit
# = max(mark - buffer, one tick). Retry ticks re-price at a fresh mark.
LIVE_CLOSE_LIMIT_BUFFER     = float(os.environ.get("OT_LIVE_CLOSE_LIMIT_BUFFER", "0.10"))
# v1.9 (audit defect O): bounded fill-confirmation window for ENTRY orders.
# Entries are optional (unlike exits): unfilled at the deadline -> cancel and
# walk away; the strategy re-evaluates next tick. Whatever DID fill is booked.
LIVE_ENTRY_DEADLINE_SECONDS = float(os.environ.get("OT_LIVE_ENTRY_DEADLINE_SECONDS", "20"))


@dataclass
class SessionConfig:
    """Runtime session config — populated at startup."""
    paper_trading:      bool    = True
    instrument:         str     = "QQQ"
    risk_per_trade_usd: float   = 200.0
    notes:              str     = ""
    confirmed_at:       Optional[str] = None

# ─── CONTINUATION (trend-pullback) exhaustion exit ────────────────────────────
# Exhaustion detection for the trend-continuation runner. Extension tightens the
# trail; momentum divergence exits. All env-tunable for paper-phase calibration.
# Continuation stop. 2026-07-22: 0.40 -> 0.25 per user directive. The 40%
# blanket floor (MAX_LOSS_PCT) is a DISASTER backstop sized for trades whose
# primary stop is structural; the continuation trade's primary stop is the
# REGIME FLIP, which fires long before a 40% premium bleed. A 40% floor was
# therefore dead weight that only ever paid out on a gap. 25% keeps the
# backstop meaningful without letting a dead thesis bleed.
CONTINUATION_STOP_LOSS_PCT      = float(os.environ.get("OT_CONT_STOP_PCT", "0.15"))
CONTINUATION_EXHAUST_EXT_ATR    = float(os.environ.get("OT_CONT_EXT_ATR", "2.0"))   # ATRs from midline = "stretched"
CONTINUATION_EXHAUST_MIN_GAIN   = float(os.environ.get("OT_CONT_MIN_GAIN", "0.15")) # only manage exhaustion past +15%
CONTINUATION_EXHAUST_TRAIL_LOCK = float(os.environ.get("OT_CONT_TRAIL_LOCK", "0.85"))# extension tightens trail to 85% of premium

# ── CONTINUATION 1-BAR CONFIRMATION (v1.5, 2026-08-10) ───────────────────────
# The FVG tag alone commits while price is still moving AGAINST the trend —
# a bet on a resumption that has not happened. With this ON, the bar AFTER the
# tag must close BEYOND the tagging bar's extreme in the trend direction before
# an entry is taken. Fewer trades, later entries, and the ones that never
# confirm are simply never taken.
# OT_CONT_REQUIRE_CONFIRM=0 restores the pre-v1.5 behaviour exactly, which
# makes this knob its own A/B control rather than a one-way door.
CONTINUATION_REQUIRE_CONFIRM = os.getenv("OT_CONT_REQUIRE_CONFIRM", "1") == "1"

# ── BOS MINIMUM DISTANCE (exit_engine v4.15, 2026-08-10) ─────────────────────
# BOS seeds its protected level from the LOW of the first bar closing above
# entry. On a pullback entry that bar is the smallest, earliest part of the
# resumption, so the level lands inside the symbol's own noise band and the next
# ordinary wiggle fires it. Observed live 2026-08-10: JPM in $1.26 12:49, out
# $0.00 12:50, back in $1.26 the same minute — the exit condition was already
# true at entry. QQQ fragmented one move into four scratches the same session.
# Expressed in ATR so it scales with the symbol; a raw price gap could not.
# 0.0 restores the pre-v4.15 behaviour exactly (kill switch and A/B control).
BOS_MIN_DIST_ATR = float(os.getenv("OT_BOS_MIN_DIST_ATR", "0.35"))

# ── CONTINUATION: THE PREMIUM REGIMES ARE NOT ITS TAPE (CNT.6, 2026-08-10) ────
# A trend continuation is, definitionally, a trend resuming after a pullback.
# RANGING and COMPRESSION are the assertion that there is NO trend to continue,
# so a continuation entry there is not a marginal call — it is a contradiction.
# It happened anyway because the dispatch gate reads
#     `_is_runaway OR regime in (TRENDING_BULL, TRENDING_BEAR, BREAKOUT_VOLATILE)`
# and `_is_runaway` BYPASSES THE LABEL ENTIRELY. So an ORB runaway flag let
# continuation fire on any tape at Priority 2 — ahead of Butterfly (P3, needs
# RANGING/COMPRESSION) and Condor (P4, needs RANGING), both of which sit behind
# `if signal is None` and were therefore never evaluated.
# MEASURED over 13 sessions: RANGING → Continuation 94 trades vs IronCondor 27;
# COMPRESSION → Continuation 39 vs Butterfly 6. Continuation took 3.5x the
# condor's opportunities and 6.5x the butterfly's, inside the regimes those
# strategies exist for.
# CNT.3 already blocked the handoff in COMPRESSION, but only INSIDE the strategy
# and only for the handoff path — RANGING was never covered, and a strategy-level
# check cannot stop the slot being consumed before P3/P4 are reached.
# Set to 0 to restore the pre-CNT.6 behaviour exactly (kill switch and A/B).
CONT_BLOCK_PREMIUM_REGIMES = os.getenv("OT_CONT_BLOCK_PREMIUM", "1") == "1"

# ── CONTINUATION CONFIRMATION TOLERANCE (v1.6, 2026-08-11) ───────────────────
# v1.5 required the confirmation bar to close STRICTLY beyond the tagging bar's
# extreme. Measured on the first live session, that failed BY PENNIES:
#   QQQ  need < 720.26  got 720.34   (8c, 0.011%)
#   PLTR need < 175.18  got 175.22   (4c, 0.023%)
#   CVX  need > 194.94  got 194.91   (3c)
#   TSLA need > 334.39  got 334.35   (4c)
#   SPX  need < 7735.58 got 7737.13  (1.55, 0.02%)
# Those are TIES, not failed resumptions — the bar closed essentially AT the
# extreme and was rejected on a rounding-level margin. The thesis is right; the
# comparison was too literal.
# Expressed in ATR so it scales with the symbol: an 8c miss is nothing on QQQ
# and everything on GLD, and a fixed cent value could never serve both.
# 0.40 IS DERIVED FROM THE SESSION, NOT PREFERRED. Expressing every logged miss
# in ATR units produces a CLEAN GAP with nothing in it:
#   near-misses (ties):  0.073 · 0.229 · 0.300 · 0.318 · 0.333 · 0.344 · 0.360
#   genuine failures:    1.133 · 1.442 · 1.694 · 1.743 · 3.355
# The two populations separate at better than 3x, so any value between 0.36 and
# 1.13 splits them and 0.40 sits just past the near-miss tail with a wide margin
# before the nearest real failure. My first draft used 0.05 and would have
# rejected EVERY case above — a no-op wearing the name of a fix, caught only by
# testing the constant against the actual logged misses instead of shipping it.
# ⚠️ ONE SESSION. The gap is wide and the classes are unambiguous, but this is
# a single day's evidence — re-derive it once a week of post-deploy misses
# exists rather than treating 0.40 as settled.
# 0.0 restores the strict v1.5 comparison exactly (kill switch and A/B control).
CONT_CONFIRM_TOL_ATR = float(os.getenv("OT_CONT_CONFIRM_TOL_ATR", "0.40"))

# ── SWP.4 (2026-08-11) — RECOVERY MEASURED FROM THE SWEPT LEVEL ──────────────
# The entry-distance gate measured recovery from `sweep.sweep_price` (the wick
# extreme of the raid), so a DEEPER rejection made the entry look FARTHER away
# and the gate refused the best setups. On a fabricated textbook PDL raid a
# 2.36% rejection produced a 2.4% "recovery" against the 2.0% cap and was
# rejected outright. Measured from the POOL (the level reclaimed — the thesis
# actually being traded) the same setup reads 0.11%.
# Wick depth is rejection QUALITY and `rejq_val` already scores it; it has no
# business inflating a distance-from-entry measure.
# 0 restores the pre-SWP.4 anchor exactly (kill switch and A/B control).
SWEEP_RECOVERY_FROM_POOL = os.environ.get("OT_SWEEP_RECOVERY_FROM_POOL", "1") == "1"

# ── SWP.5 (2026-08-11) — LIVENESS REPLACES THE CLOCK ────────────────────────
# `SWEEP_MAX_AGE_BARS = 8` was standing in for an invalidation test the code did
# not have. MEASURED over 90 real symbol-days: of the stale sweeps it refused,
# **32.9% still had a LIVE thesis** — price had never accepted back through the
# raided level and was still on the correct side. ~9.5 valid setups discarded
# per symbol-day, on a clock.
# The right test already exists in spirit: `veto_accept` asks whether price
# accepted beyond the level — it is just a BIRTH-TIME snapshot. LIQ.3 makes it
# a running check, and this gate reads it.
# ⚠️ THE BACKSTOP IS DELIBERATE. A level that still holds at 5 hours is a
# different trade from a fresh raid, and this is a collection phase. 48 bars
# (5m-equivalent) = 4 hours: generous enough to keep the 32.9%, bounded enough
# that "still holding" cannot mean "all week".
SWEEP_LIVENESS_GATE   = os.environ.get("OT_SWEEP_LIVENESS_GATE", "1") == "1"
SWEEP_STALE_HARD_BARS = int(os.environ.get("OT_SWEEP_STALE_HARD_BARS", "48"))

# ── VEL.1 (2026-08-12) — VELOCITY STALL: "is this thing MOVING at all?" ──────
# The third question, and until now nobody asked it. `orb_structure_stop` asks
# "did the thesis break?"; `_theta_bleed` asks "is my GAIN about to evaporate?"
# (gate 1 is a gain floor, so it never looks at a losing position). A LOSING
# POSITION THAT HAS STOPPED MOVING answers NO to both and falls to the -40%
# percentage floor, which is the ABSENCE of a mechanism rather than one.
#
# THE STATISTIC, and note it needs NO TARGET — which is why it generalises to
# every long-premium strategy, not just ORB:
#     breakeven velocity  bev = |theta| / (|delta| * 1440)     underlying pts/min
#                               at which delta gains exactly offset decay.
#     delivered velocity        cumulative underlying travel toward the trade's
#                               direction, per minute since entry.
#     ratio = delivered / bev.  1.0 is the FLAT LINE. Below it the position
#                               bleeds even while the thesis is intact.
#
# MEASURED over 15 sessions / 145 ORB trades against the chain archive
# (tests/velocity_feasibility.py), among trades STILL OPEN at each mark:
#            mark   winners p10   losers p50   losers p90
#             5m       -21.1         -37.3        91.3     <- NO SEPARATION
#            10m         3.9          -6.7        20.5
#            15m        18.0           0.3        26.7
#            20m        29.8           0.9        18.5     <- barely overlap
# The median surviving LOSER sits at ~1.0 — treading water exactly at breakeven
# — while the bottom decile of WINNERS is at 30x it. Different regimes, not a
# marginal difference.
#
# ⚠️ THE 5-MINUTE ROW IS WHY GRACE EXISTS: winners p10 of -21.1 means the bottom
# decile of eventual WINNERS was moving AWAY at five minutes. Any evaluation
# before 10 minutes kills those trades. GRACE is forced by data, not chosen.
#
# ⚠️ THE FLOOR IS DERIVED, NOT PICKED. Each value is the winners' p10 at that
# mark, so a floor at STRICTNESS=1.0 admits 90% of historical winners BY
# CONSTRUCTION. Re-run the study to refresh it; do not hand-tune it.
VELOCITY_STALL_ENABLED  = os.environ.get("OT_VELOCITY_STALL", "1") == "1"
# ⚠️ SHIPS OBSERVE-ONLY. The floors rest on n=22 at the 20-minute mark and were
# derived from ORB alone. Log the breach, collect a session, THEN enforce.
VELOCITY_STALL_ENFORCE  = os.environ.get("OT_VELOCITY_ENFORCE", "0") == "1"
VELOCITY_GRACE_MIN      = float(os.environ.get("OT_VELOCITY_GRACE_MIN", "10"))
VELOCITY_STRICTNESS     = float(os.environ.get("OT_VELOCITY_STRICTNESS", "1.0"))
# consecutive breaches before cutting. ⚠️ NOT COSMETIC: the 2026-08-12 QQQ trade
# crossed back ABOVE breakeven at minutes 41-61 before dying at 70. A single-tick
# rule oscillates; confirmation is what makes the cumulative form usable.
VELOCITY_CONFIRM_TICKS  = int(os.environ.get("OT_VELOCITY_CONFIRM", "3"))
# minutes -> winners p10 ratio. Largest mark <= held wins; under the first mark
# no check runs at all.
VELOCITY_FLOOR_BY_MIN   = {10: 3.9, 15: 18.0, 20: 29.8}
# ⚠️ Strategies whose floor has been MEASURED. Others are evaluated and LOGGED
# but never cut, whatever ENFORCE says — the floors above are ORB-derived and
# applying them blind to continuation or sweep would be an untested extrapolation
# wearing a measured number.
VELOCITY_MEASURED_STRATEGIES = ("ORBStrategy",)

# ═════════════════════════════════════════════════════════════════════════════
# SMC CORE (fork: options_trader_smc) — v4.19, 2026-08-18
# The structural entry core's knobs. smc/primitives.py and smc/smc_engine.py
# read the OT_SMC_* environment at import, so these assignments are the
# DOCUMENTED DEFAULTS and the single place a reader finds them — the same
# contract as OT_RC_* / OT_TR_*. Change via systemd env, not by editing here.
# Every value is a STATED PRIOR (category 1 of the operator's three-way
# split): the QQQ SMC box journals the raw inputs and the bounds
# get fitted from observed percentiles — the room_s convention. Do not tune
# them on the first bad session.
# ═════════════════════════════════════════════════════════════════════════════
SMC_ACCEPT_CLOSES    = int(os.environ.get("OT_SMC_ACCEPT_CLOSES", "2"))
SMC_POI_APPROACH_ATR = float(os.environ.get("OT_SMC_POI_APPROACH_ATR", "0.75"))
SMC_REVOKE_GATES     = os.environ.get("OT_SMC_REVOKE_GATES", "1") == "1"


# ═════════════════════════════════════════════════════════════════════════════
# ICT SETUP SUITE (strategy/ict, F.13) — G8, v4.20, 2026-08-19
# DOCUMENTED DEFAULTS ONLY. The suite reads OT_ICT_* from the environment at
# import — the same contract as OT_SMC_* / OT_RC_* / OT_TR_*: env wins, config
# is where a reader finds out what exists. Change via systemd env, not here.
# EVERY VALUE IS A STATED PRIOR (operator's category 1), to be fitted from this
# box's own `ict_setup` journal — never tuned on one bad session.
# ⚠️ THE THREE FIRE GATES DEFAULT CLOSED AND STAY THAT WAY until a setup passes
# a §3.5 harness run against a pass condition the OPERATOR wrote first.
# ═════════════════════════════════════════════════════════════════════════════
ICT_ARMED              = os.environ.get("OT_ICT_ARMED", "0") == "1"
ICT_SCORE_FLOOR        = float(os.environ.get("OT_ICT_SCORE_FLOOR", "0.65"))
ICT_COMPLETENESS_FLOOR = float(os.environ.get("OT_ICT_COMPLETENESS_FLOOR", "0.75"))
ICT_SB_START           = os.environ.get("OT_ICT_SB_START", "09:45")  # Silver Bullet
ICT_SB_END             = os.environ.get("OT_ICT_SB_END",   "11:30")  #   window, ET
ICT_DEBIT_CUTOFF       = os.environ.get("OT_ICT_DEBIT_CUTOFF", "11:30")
ICT_SIZE_BIAS_MIN      = float(os.environ.get("OT_ICT_SIZE_BIAS_MIN", "0.50"))
ICT_SIZE_BIAS_STRONG   = float(os.environ.get("OT_ICT_SIZE_BIAS_STRONG", "0.75"))
ICT_SIZE_BIAS_CLEAN    = float(os.environ.get("OT_ICT_SIZE_BIAS_CLEAN", "0.85"))
ICT_SIZE_SD_AWARE      = float(os.environ.get("OT_ICT_SIZE_SD_AWARE", "1.75"))
ICT_SIZE_SD_CONFIRM    = float(os.environ.get("OT_ICT_SIZE_SD_CONFIRM", "2.0"))
ICT_SIZE_FRAC_MARGINAL = float(os.environ.get("OT_ICT_SIZE_FRAC_MARGINAL", "0.33"))
ICT_SIZE_FRAC_SOLID    = float(os.environ.get("OT_ICT_SIZE_FRAC_SOLID", "0.66"))
# Per-setup validation gates. Arming a setup = OT_ICT_<NAME>_VALIDATED=1 in the
# unit file, AFTER its harness run, and never before.
ICT_VALIDATED = {n: os.environ.get(f"OT_ICT_{n}_VALIDATED", "0") == "1"
                 for n in ("ICTSILVERBULLET", "ICTJUDASPO3", "ICTMODEL2022",
                           "ICTSWEEPMSS", "ICTBREAKERUNICORN",
                           "ICTOTECONFLUENCE", "ICTOBFVG")}
