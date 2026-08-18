"""
analysis/orb_engine.py — Opening Range Breakout state machine.
v3.9 — 2026-07-20 — STALE-RETEST TIMEOUT RESTORED, CORRECTED (supersedes v3.8's
        removal; per user spec same day). The window's only job: after a break,
        call the retest STALE once ORB_MAX_RETEST_BARS real 1-minute bars pass
        with no confirm (not far enough to be a runaway). Fixes vs pre-v3.8:
        (1) TICK-COUNTING BUG — the old counter incremented every 15-second
        engine tick, not per bar (journal: one candle logged 4x), so 12 "bars"
        expired in ~3 minutes; now dedupes on the candle timestamp
        (last_retest_bar_ts) and counts true bars. (2) NON-TERMINAL — expiry
        now calls _rearm() (WAITING_FOR_BREAK) instead of a dormant
        INVALIDATED; a fresh close beyond either level starts a new attempt
        with a fresh window. Timing: the break candle is excluded from the
        count, so with ORB_MAX_RETEST_BARS=12 the stale signal fires on the
        13th post-break bar — a 13-minute window. Runaway stays terminal;
        close_inside re-arm
        unchanged. Day-zero SMH replay under these rules: pre-10:00 attempt
        goes stale ~10:12 OR dies close_inside, either way 10:06's fresh break
        re-arms and 10:07's confirm FIRES the short.
v3.8 — 2026-07-20 — RETEST TIMEOUT REMOVED (structural defect, user spec): the
        ORB_MAX_RETEST_BARS=12 timeout invalidation retired an armed side on a
        CLOCK, not a market event — and because 'timeout' was terminal (never
        re-armed), a stale expired attempt left the engine blind to a FRESH
        valid break. Day-zero cost: SMH 10:06 break + 10:07 textbook confirm
        (H 566.99 wick-in, body-high 566.59 out, close 566.50 out vs ORB low
        566.71) went untaken; journal retest_check proved the armed window
        ended 10:03:15 and never re-armed. Fix: timeout deleted from the state
        machine. ARMED now persists until one of three REAL outcomes: retest
        confirm (trade), 1m close back inside (re-arm via close_inside), or
        runaway to the 50% TP (terminal, hands to sweep). bars_since_break
        kept as journal telemetry only. ORB_MAX_RETEST_BARS no longer imported.
v3.7 — 2026-07-18 — DEFECT G MEASUREMENT (log-only, zero gating change): the
        near-miss retest is now MEASURED, never gated, exactly as the defect
        prescribes. (1) ORBData.retest_depth_px records the confirming retest
        candle's penetration into the range (long: orb_high - low; short:
        high - orb_low) so the fired setup carries its own retest depth.
        (2) every 1-min candle examined while ARMED emits a `retest_check`
        event to analysis/signal_journal with the raw px depth (NEGATIVE =
        near-miss: the wick approached but never entered) + orb_width +
        outcome, building the depth distribution the Phase-3 ROI buckets
        need before anyone decides whether a "B-grade almost-retest" is
        worth grading. Depth is logged in PX and divided by tape ATR offline
        (ATR-relative per defect G — never a percentage; percentages scale
        into holes on high-priced instruments). Confirm/invalidate logic is
        byte-identical; the journal import is guarded and every emission is
        swallowed on failure.
v3.6 — 2026-07-13 — defect H rename only: NO_ENTRY_AFTER_ET -> ORB_NO_ENTRY_AFTER_ET
        (import + the past_orb_cutoff test). Same constant, same (11, 0) value,
        same behaviour. NOTE the two cutoffs in this file are DIFFERENT rules and
        always were: past_orb_cutoff uses the 11:00 ORB-scoped constant, while
        is_past_entry_cutoff() (from utils.time_utils, used in notify_position_closed
        to decide EXPIRED vs re-arm) uses the 14:00 GLOBAL cutoff. The rename makes
        that distinction legible at the call site.
v3.5 — 2026-07-12 — THE BREAK IS NOW DEFINITIONAL. Two changes, one principle:
        the setup is mechanical, so every tolerance is removed and the rule is
        stated exactly.
        (1) ORIGIN GATE now keys on the OPEN, not the wick. The impulsive candle
            must OPEN INSIDE the opening range (orb_low <= open <= orb_high) and
            CLOSE OUTSIDE it. v3.1 approximated "originates inside" as
            `low_ < orb_high` — the wick merely reaching back into the range —
            which still admitted a candle that OPENED ABOVE the range, dipped a
            wick in, and closed higher. That candle never broke out of the range;
            it was already outside it. It is late continuation, and it is not an
            OPENING-RANGE break by definition.
        (2) ORB_BREAK_BUFFER REMOVED (both the break test and the session latch).
            The buffer required the close to clear the range by 0.05% OF PRICE
            before a break registered. It filtered nothing the retest does not
            already filter — a marginal break that means nothing simply FAILS its
            retest — and, being a percentage, it scaled into a hole: $0.49 on MU,
            ~$3.00 on SPX. Price could close three full points beyond the opening
            range and the engine would not call it a break. A break is a close
            beyond the level. Full stop.
        The latch (_update_break_latches, which arms the SWEEP gate) drops the
        buffer as well, preserving its documented invariant that it uses the SAME
        threshold as _check_for_break(). The latch remains CLOSE-ONLY by design and
        does NOT take the origin gate — it records a session fact, not a setup.
        Net effect on the ORB: FEWER breaks (origin gate is strictly tighter) and
        EARLIER breaks (no buffer to clear). On the sweep gate: marginally MORE
        breaks latch, since the buffer no longer suppresses a small close-out.
        Together with v3.3 the whole setup is now free of tolerances:
            BREAK  = opens inside the range, closes outside it.
            RETEST = wick into the range, body outside it.
            STOP   = a close beyond the impulsive candle's wick.
v3.4 — 2026-07-12 — STATE VOCABULARY CORRECTED. The state names described the
        mechanism, not the trade, and one of them collided with an unrelated
        concept. `ORBState.RANGING` and `Regime.RANGING` shared a string while
        meaning completely different things ("the ORB has no break yet" vs "the
        tape is oscillating") — a latent trap for any reader, human or model,
        holding both in view. Renamed to the operator's own vocabulary:
            WAITING                    -> NO_RANGE           (range not established)
            RANGING                    -> WAITING_FOR_BREAK  (range set, no break)
            BREAK_HIGH_AWAITING_RETEST -> ARMED_LONG         (break done, awaiting retest)
            BREAK_LOW_AWAITING_RETEST  -> ARMED_SHORT
            OPEN_LONG / OPEN_SHORT     -> unchanged (a position is live)
        ARMED means a break has occurred and the next event is FIRE or INVALIDATE.
        Before a break there is nothing armed — the engine is merely WAITING.
        Rename only: no state transition, threshold, or condition changed. The
        strings surface in orb_state.json, which main.py rewrites every tick, so
        a stale file self-heals within one poll interval (15s) — no migration.
v3.3 — 2026-07-12 — RETEST GRACE BAND REMOVED (correctness fix, both sides).
        The retest confirm carried a percentage tolerance on the BODY test:
        long  `body_low  >= orb_high * 0.999`
        short `body_high <= orb_low  * 1.001`
        Intent was to admit a "near-miss" retest (wick approaches the range but
        does not enter) as a lower-grade setup. The code did the OPPOSITE. The
        first clause of the same condition (`low < orb_high`) ALREADY requires
        the wick to enter the range, so a true near-miss was never admitted and
        never fired. What the 0.999 actually admitted was a candle whose BODY
        CLOSED BACK INSIDE THE RANGE — by up to 0.1% — as a CONFIRMED retest.
        That is the DISARM condition, bought as an entry. And because the confirm
        branch is evaluated before the (b) close-inside branch, it won.
        Scale of the hole (percentage of price, so it grows with the instrument):
          MU  @ 971.50 range high → admitted closes down to 970.53 (~$0.97 inside)
          SPX @ 6000.00           → admitted closes ~6.0 POINTS inside the range
        The retest is the FALSIFICATION step of the break hypothesis ("this level
        is now support"). A level that was not actually tested produced no
        evidence, and a level whose retest closed back inside was tested and
        FAILED. Neither is a graded setup; both are no-trade. The test is now
        exact: wick INTO the range, body OUTSIDE it. No tolerance.
        Behavioural effect: strictly FEWER entries. Every entry removed was one
        taken on a candle that had already invalidated the setup. Verified against
        the MU 2026-07-10 reference (09:49 break / 09:50 retest / 09:55 stop):
        sequence reproduces unchanged — the reference retest's body sits fully
        outside the range and never depended on the grace.
        NOTE (future, NOT in this change): if the near-miss is to be evaluated as
        a genuine B-grade variant, it must be MEASURED, not gated — log an
        ATR-relative `retest_depth = (orb_high - candle_low) / ATR` on every setup
        (negative = near-miss) and let the Phase-3 ROI buckets decide. It belongs
        in orb_quality inside setup_scorer, never as a tolerance in the state
        machine. See ROADMAP Phase 3.
v3.2 — 2026-07-11 — ORB beats sweep under the regime switch. The retest confirm
        used to DEFER (leave the setup awaiting retest) whenever the regime was
        SWEEP_REVERSAL, so a sweep label suppressed a valid ORB. Guarded by
        config.ORB_FIRES_REGARDLESS_OF_REGIME: when on, the engine confirms OPEN
        under a sweep label and the dispatch fires ORB (ORB wins). When off,
        behaviour is unchanged (defers to sweep). Pairs with main.py v3.2, which
        admits UNKNOWN/SWEEP_REVERSAL to the ORB dispatch. No change to the v3.1
        stop logic.
v3.1 — 2026-07-11 — STOP PLACEMENT FIX + impulsive-candle origin gate.
        (1) The protective stop now anchors to the impulsive (break) candle's
            actual WICK — its LOW for a long, its HIGH for a short — not the
            body (min/max of open,close) it used before. When the impulsive
            candle opened outside the range, the body edge sat OUTSIDE the
            level, so the retest entry (which returns to the level) printed a
            stop on the wrong side of entry — inverted/degenerate risk. The
            wick is the true origin of the breakout move and sits inside the
            range where invalidation actually lives.
        (2) A valid impulsive candle must ORIGINATE INSIDE the range: its low
            must reach into the range for a long (low < orb_high), its high for
            a short (high > orb_low). A candle sitting entirely beyond the range
            is late continuation, not an ORB break; taking its "retest" was the
            source of the remaining inverted stops (fast/gap breaks and re-arms
            while price was extended). Gating on origin removes them.
        Verified on candle-logger tape (2026-07-09/10, 44 symbol-sessions):
        inverted-risk entries fell to 0 and the MU 2026-07-10 09:49/09:50
        reference setup reproduces exactly (stop 971.14 = impulsive low).
        Stop-LEVEL fix only; the exit TRIGGER is unchanged (see note below).
v3.0 — 2026-07-07 — FIX (grave): break latches broke_high/broke_low are now
        maintained UNCONDITIONALLY every tick by _update_break_latches(),
        decoupled from the RANGING-only _check_for_break() path. Previously the
        latches were set solely inside _check_for_break(), which runs ONLY in
        RANGING state — so once the engine left RANGING without re-arming
        (runaway, retest-timeout, or a confirmed OPEN), it never re-checked for
        a break and the OPPOSITE-side latch could never be set. A genuine
        opposite-side 1-min CLOSE breakout after a one-sided runaway was
        therefore invisible to the sweep-reversal gate (_sweep_broke_orb),
        BLOCKING the highest-conviction failed-breakout reversals pre-11:00 —
        and the surviving same-side latch could be leaned on while stale. The
        latch is now a pure session fact ("did a 1-min candle CLOSE beyond this
        boundary this session"), independent of ORB entry state. Preserved:
        it stays CLOSE-based (a wick that pokes and closes back inside still
        does NOT arm a sweep — the AVGO-trap protection) and latch-only (set
        True; cleared solely by reset_for_session()). Fix is contained to this
        file; downstream (sweep gate + orb_state.json) reads the properties
        unchanged.
v1.8 — 2026-07-06 — (a) session break latches broke_high/broke_low set on a
        1-min CLOSE beyond the range — these arm the sweep reversal (same break
        the ORB retest uses), so a wick poke that closes back inside no longer
        arms a sweep. (b) retest confirm DEFERS when regime==SWEEP_REVERSAL
        (sweeps take priority) so the engine can't get stuck in a phantom OPEN.
        (c) re-arm rule tightened to: 1-min close back inside AND before 11:00
        (runaway/timeout never re-arm).
v1.0 — original release
v1.1 — 2026-06-30 — full state model rewrite
v1.2 — 2026-06-30 — fix cutoff check running before range-setting
v1.3 — 2026-07-01 — ORB range now read from orb_range.json (written by
        analysis/get_orb_range.py). Single source of truth — no external feed
        calls inside the engine, no log parsing, no circular logic.
v1.4 — 2026-07-02 — fix _range_date comparison: now stored as string from
        JSON date field so today check works correctly and engine stops
        reloading orb_range.json every tick after range is set.
v1.7 — 2026-07-02 — regime-gated re-arm: after a (b) close-inside invalidation,
        re-arm and watch for another break ONLY while the regime is still
        ORB-friendly (RANGING/COMPRESSION). Do NOT re-arm after an (a) runaway
        (hand off to sweep) or once the regime has shifted to sweep/trend/
        breakout. Tracks invalidation_reason to distinguish the two.
v1.6 — 2026-07-02 — 11:00 ET HARD cutoff (expire even awaiting-retest, so the
        bot moves to other regimes after 11:00) + two explicit invalidation
        rules: (a) price runs to the 50% TP with no retest (runaway breakout,
        favors sweep reversal); (b) a 1m candle closes back inside the ORB
        range. Replaces the 2PM/exempt-retest behavior.
v1.5 — 2026-07-02 — honor the orb_range.json "status" field. Only an
        ESTABLISHED range dated today is loaded and armed (WAITING->RANGING).
        EXPIRED (last RTH) and IN_PROGRESS (opening candle still forming)
        ranges are ignored for trading, so the engine can never break out on
        a carried-over prior-day range.
v3.0 — 2026-07-10 — repo-wide v3.0 bump: Yahoo-Finance purge & data stream
        mapping optimization (all market data now flows from the single
        shared TastyTrade candle feed — see data/candle_feed.py). No logic
        change in this file.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional
from datetime import datetime
import pandas as pd

from utils.time_utils import now_et, is_past_entry_cutoff
from utils.math_utils import orb_strike_selection
from config import (
    ORB_MAX_RETEST_BARS, STRIKE_INCREMENT, INSTRUMENT,
    ORB_NO_ENTRY_AFTER_ET, ORB_FIRES_REGARDLESS_OF_REGIME
)

# v3.7 — defect-G measurement. Guarded: engine runs identically without it.
try:
    from analysis.signal_journal import journal as _sig_journal
except Exception:
    _sig_journal = None

logger = logging.getLogger(__name__)

ORB_RANGE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "orb_range.json")


class ORBState:
    NO_RANGE                   = "NO_RANGE"          # opening range not established yet
    WAITING_FOR_BREAK          = "WAITING_FOR_BREAK" # range set; no break yet
    ARMED_LONG                 = "ARMED_LONG"        # broke HIGH; awaiting retest
    ARMED_SHORT                = "ARMED_SHORT"       # broke LOW; awaiting retest
    INVALIDATED                = "INVALIDATED"
    OPEN_LONG                  = "OPEN_LONG"
    OPEN_SHORT                 = "OPEN_SHORT"
    EXPIRED                    = "EXPIRED"


@dataclass
class ORBData:
    state:              str   = ORBState.NO_RANGE
    orb_high:           float = 0.0
    orb_low:            float = 0.0
    orb_width:          float = 0.0
    break_candle_high:  float = 0.0
    break_candle_low:   float = 0.0
    break_candle_close: float = 0.0
    break_direction:    str   = ""
    bars_since_break:   int   = 0
    last_retest_bar_ts: str   = ""   # v3.9: dedupe 15s ticks -> count real 1m bars
    target_100pct:      float = 0.0
    target_50pct:       float = 0.0
    stop_level:         float = 0.0
    target_strike:      int   = 0
    confirmed_at:       str   = ""
    attempt_number:     int   = 0
    entries_expired:    bool  = False
    invalidation_reason: str  = ""   # 'runaway' | 'close_inside' (v3.8: 'timeout' removed)
    retest_depth_px:    float = 0.0  # v3.7 (defect G): confirming retest wick's
                                     # penetration into the range, in PX
                                     # (long: orb_high - low; short: high - orb_low).
                                     # Measured only — gates nothing.


class ORBEngine:

    def __init__(self):
        self._data = ORBData()
        self._range_date = None
        # Session-level latches: did a 1-min candle CLOSE beyond the range this
        # session? These arm the sweep reversal (a sweep needs the SAME
        # registered break as the ORB retest). They survive _rearm() and are
        # only cleared by reset_for_session().
        self._broke_high = False
        self._broke_low  = False

    @property
    def data(self) -> ORBData:
        return self._data

    @property
    def broke_high(self) -> bool:
        """True once a 1-min candle CLOSED above the ORB high this session."""
        return self._broke_high

    @property
    def broke_low(self) -> bool:
        """True once a 1-min candle CLOSED below the ORB low this session."""
        return self._broke_low

    def reset_for_session(self):
        self._data = ORBData()
        self._range_date = None
        self._broke_high = False
        self._broke_low  = False
        logger.info("ORB engine reset for new session")

    def _rearm(self):
        d = self._data
        orb_high, orb_low, orb_width_val = d.orb_high, d.orb_low, d.orb_width
        attempt = d.attempt_number
        self._data = ORBData()
        self._data.orb_high       = orb_high
        self._data.orb_low        = orb_low
        self._data.orb_width      = orb_width_val
        self._data.state          = ORBState.WAITING_FOR_BREAK
        self._data.attempt_number = attempt
        logger.info(
            f"ORB re-armed for next attempt (#{attempt + 1}): "
            f"watching range {orb_low:.2f}-{orb_high:.2f}"
        )

    def _load_range_from_file(self):
        """Load the ORB range from orb_range.json — single source of truth.

        Only an ESTABLISHED range dated today is armed for trading. EXPIRED
        (last RTH) and IN_PROGRESS (opening candle forming) states are ignored
        so the engine never breaks out on a carried-over prior-day range.
        """
        d = self._data
        try:
            with open(ORB_RANGE_FILE) as f:
                data = json.load(f)
            status = str(data.get("status", "")).upper()
            date   = data.get("date")
            today  = now_et().strftime("%Y-%m-%d")

            if status != "ESTABLISHED" or date != today:
                logger.debug(
                    f"ORB range not established for today "
                    f"(status={status or 'NONE'} date={date}) — engine waits"
                )
                return

            high  = float(data["high"])
            low   = float(data["low"])
            width = float(data["width"])
            if high > 0 and low > 0:
                d.orb_high  = high
                d.orb_low   = low
                d.orb_width = width
                self._range_date = today
                if d.state == ORBState.NO_RANGE:
                    d.state = ORBState.WAITING_FOR_BREAK
                logger.info(
                    f"ORB range ESTABLISHED: high={high:.2f} low={low:.2f} "
                    f"width={width:.2f} date={date}"
                )
        except Exception as e:
            logger.debug(f"ORB range file not ready: {e}")

    def update(self, df_5m: pd.DataFrame, df_1m: pd.DataFrame,
               current_price: float, regime: Optional[str] = None) -> ORBData:
        d = self._data

        # Load range from file if not yet set for today
        today = now_et().strftime("%Y-%m-%d")
        if self._range_date != today or d.orb_high == 0.0:
            self._load_range_from_file()

        now = now_et()
        past_orb_cutoff = (now.hour, now.minute) >= ORB_NO_ENTRY_AFTER_ET
        d.entries_expired = past_orb_cutoff

        # Maintain the session break latches on EVERY tick, in EVERY state, the
        # moment the range is established — a break is a session-level fact, not
        # a property of the ORB entry state machine. This must run BEFORE the
        # cutoff/OPEN/INVALIDATED early-returns below so that a genuine 1-min
        # CLOSE beyond a boundary is recorded even when the ORB itself is
        # dormant (e.g. after a one-sided runaway), which is exactly when the
        # opposite-side sweep reversal needs the latch. (v1.9)
        self._update_break_latches(df_1m)

        # 11:00 ET HARD cutoff — the ORB window is over. Expire from ANY state,
        # including OPEN_LONG/OPEN_SHORT, so the engine stops watching and can
        # never hold a phantom OPEN past the window. (A real live position is
        # managed by the position manager and exits on its own rules; expiring
        # the ENGINE state here does not touch the position.)
        if past_orb_cutoff:
            if d.state != ORBState.EXPIRED:
                d.state = ORBState.EXPIRED
                logger.info(
                    f"ORB: past 11:00 ET cutoff — EXPIRED "
                    f"(range: {d.orb_low:.2f}-{d.orb_high:.2f})"
                )
            return d

        # Before the cutoff, a confirmed OPEN is left untouched (a live ORB
        # trade is being managed elsewhere; the engine doesn't re-fire).
        if d.state in (ORBState.OPEN_LONG, ORBState.OPEN_SHORT):
            return d

        if d.state == ORBState.WAITING_FOR_BREAK:
            self._check_for_break(df_1m)

        if d.state in (ORBState.ARMED_LONG, ORBState.ARMED_SHORT):
            self._check_for_retest(df_1m, regime)

        if d.state == ORBState.INVALIDATED:
            # Re-arm ONLY after a (b) close-inside invalidation. Past 11:00 the
            # engine already EXPIRED above, so this branch is inherently
            # before-cutoff — i.e. the rule is exactly "1-min close back inside
            # the range AND before 11:00". A runaway (a) NEVER re-arms (it hands
            # off to sweep reversal). v3.8: 'timeout' no longer exists — the
            # retest clock was removed per spec; armed persists until a market
            # event resolves it.
            if d.invalidation_reason == "close_inside":
                self._rearm()
            else:
                logger.debug(
                    f"ORB dormant after '{d.invalidation_reason}' invalidation "
                    f"(regime={regime}) — deferring to sweep reversal"
                )

        return d

    def notify_position_closed(self):
        d = self._data
        if d.state in (ORBState.OPEN_LONG, ORBState.OPEN_SHORT):
            if is_past_entry_cutoff():
                d.state = ORBState.EXPIRED
            else:
                logger.info("ORB position closed — re-arming for next attempt")
                self._rearm()

    def _update_break_latches(self, df_1m: pd.DataFrame):
        """Record, as a session-level fact, whether a 1-min candle has CLOSED
        beyond the ORB range in each direction (broke_high / broke_low).

        Deliberately independent of the ORB entry state machine: the sweep
        reversal gate must know a genuine breakout occurred even when the ORB
        is dormant (post-runaway / OPEN / EXPIRED), which _before_
        v1.9 was impossible because the latches were only set inside
        _check_for_break() (RANGING-only). Uses the SAME closed candle
        (iloc[-2]) and the SAME break threshold as _check_for_break(), so the
        latch and the ORB retest arm on identical conditions. Latch-only: sets
        True and never clears (reset_for_session() is the sole reset). Purely
        CLOSE-based, so a wick that pokes a boundary and closes back inside
        does NOT arm a sweep (AVGO-trap protection preserved).
        """
        d = self._data
        if d.orb_high <= 0 or d.orb_low <= 0:
            return                      # range not established — nothing to latch
        if df_1m is None or len(df_1m) < 2:
            return
        close  = float(df_1m.iloc[-2]["close"])
        # (v3.5) Buffer removed here too, to preserve this method's stated invariant:
        # the latch must use the SAME break threshold as _check_for_break(). The latch
        # is deliberately CLOSE-ONLY and does NOT apply the opens_inside origin gate —
        # it records a session FACT ("a 1m candle closed beyond this boundary"), which
        # is what the sweep gate needs, not an ORB entry setup.
        if close > d.orb_high:
            if not self._broke_high:
                self._broke_high = True
                logger.info(
                    f"ORB latch: 1-min CLOSE {close:.2f} above high "
                    f"{d.orb_high:.2f} — broke_high armed (session-level)"
                )
        elif close < d.orb_low:
            if not self._broke_low:
                self._broke_low = True
                logger.info(
                    f"ORB latch: 1-min CLOSE {close:.2f} below low "
                    f"{d.orb_low:.2f} — broke_low armed (session-level)"
                )

    def _check_for_break(self, df_1m: pd.DataFrame):
        d = self._data
        if df_1m is None or len(df_1m) < 2:
            return
        candle = df_1m.iloc[-2]
        close  = float(candle["close"])
        open_  = float(candle["open"])
        high_  = float(candle["high"])
        low_   = float(candle["low"])

        # THE BREAK (v3.5). Definitional, no tolerances:
        #   the impulsive candle OPENS INSIDE the opening range and CLOSES OUTSIDE it.
        # `opens_inside` is the whole premise of the setup — it is an OPENING-RANGE
        # break; a candle that began life outside the range never broke out of it,
        # it was already out. (v3.1 approximated this with `low_ < orb_high`, i.e.
        # the wick merely reaching back in, which admitted candles that opened above
        # the range, dipped, and closed higher — late continuation, not a break.)
        # The percentage break buffer is GONE (v3.5): the retest IS the noise filter
        # — a marginal break that means nothing simply fails its retest. The buffer
        # only cost real setups, and being a % of price it scaled into a hole
        # (0.05% = $0.49 on MU, ~$3.00 on SPX: price could close three points clear
        # of the range and not register).
        opens_inside = d.orb_low <= open_ <= d.orb_high

        if opens_inside and close > d.orb_high:
            d.break_direction    = "long"
            d.break_candle_close = close
            # Stop anchors to the IMPULSIVE candle's WICK, not its body: the low of
            # the candle that caused the breakout (v3.1). Using min(open,close)
            # (the body low) placed the stop ABOVE the level whenever the impulsive
            # candle opened outside the range, inverting risk on the retest entry.
            d.break_candle_high  = high_
            d.break_candle_low   = low_
            d.bars_since_break   = 0
            d.last_retest_bar_ts = str(df_1m.index[-2])  # break candle excluded from stale count
            d.target_100pct      = d.orb_high + d.orb_width
            d.target_50pct       = d.orb_high + d.orb_width * 0.5
            d.stop_level         = d.break_candle_low
            d.target_strike      = orb_strike_selection(d.orb_high, d.orb_low, "long", STRIKE_INCREMENT)
            d.attempt_number    += 1
            d.state              = ORBState.ARMED_LONG
            # (v1.9) broke_high is now latched by _update_break_latches() every
            # tick, independent of state — not set here.
            logger.info(
                f"ORB BREAK HIGH (attempt #{d.attempt_number}): close={close:.2f} "
                f"above {d.orb_high:.2f} target={d.target_100pct:.2f} strike={d.target_strike}"
            )
        elif opens_inside and close < d.orb_low:
            d.break_direction    = "short"
            d.break_candle_close = close
            # Stop anchors to the IMPULSIVE candle's WICK (its HIGH for a short) —
            # the high of the candle that caused the breakout (v3.1).
            d.break_candle_high  = high_
            d.break_candle_low   = low_
            d.bars_since_break   = 0
            d.last_retest_bar_ts = str(df_1m.index[-2])  # break candle excluded from stale count
            d.target_100pct      = d.orb_low - d.orb_width
            d.target_50pct       = d.orb_low - d.orb_width * 0.5
            d.stop_level         = d.break_candle_high
            d.target_strike      = orb_strike_selection(d.orb_high, d.orb_low, "short", STRIKE_INCREMENT)
            d.attempt_number    += 1
            d.state              = ORBState.ARMED_SHORT
            # (v1.9) broke_low is now latched by _update_break_latches() every
            # tick, independent of state — not set here.
            logger.info(
                f"ORB BREAK LOW (attempt #{d.attempt_number}): close={close:.2f} "
                f"below {d.orb_low:.2f} target={d.target_100pct:.2f} strike={d.target_strike}"
            )

    def _check_for_retest(self, df_1m: pd.DataFrame, regime: Optional[str] = None):
        d = self._data
        if df_1m is None or len(df_1m) < 2:
            return
        # v3.9 STALE-RETEST TIMEOUT, per spec 2026-07-20: the window applies
        # ONLY while ARMED (i.e. after the break, which is the only place this
        # method runs) and its sole purpose is to declare a retest STALE after
        # ORB_MAX_RETEST_BARS 1-minute bars pass without one — too slow to be a
        # retest, not far enough to be a runaway. On expiry the engine goes
        # straight back to WAITING_FOR_BREAK (non-terminal): a fresh 1m close
        # beyond either level starts a new attempt with a fresh window.
        #   Two defects in the pre-v3.8 timeout, both fixed here:
        #   (1) it counted 15-SECOND LOOP TICKS as "bars" (journal 2026-07-20:
        #       one candle logged 4x, each tick incrementing), so "12 bars"
        #       actually expired in ~3 minutes;
        #   (2) it was TERMINAL (never re-armed), so an expired stale attempt
        #       left the engine blind to SMH's fresh 10:06 break + 10:07
        #       textbook confirm. Now: real bars, and expiry re-arms.
        candle_ts = str(df_1m.index[-2])
        if candle_ts != d.last_retest_bar_ts:
            d.last_retest_bar_ts = candle_ts
            d.bars_since_break += 1
        if d.bars_since_break > ORB_MAX_RETEST_BARS:
            logger.info(
                f"ORB: retest STALE after {d.bars_since_break - 1} bars with no "
                f"confirm (attempt #{d.attempt_number}) — re-arming, waiting "
                f"for a fresh break"
            )
            self._rearm()
            return

        candle    = df_1m.iloc[-2]
        close     = float(candle["close"])
        open_     = float(candle["open"])
        high      = float(candle["high"])
        low       = float(candle["low"])
        body_high = max(open_, close)
        body_low  = min(open_, close)

        # v3.7 (defect G) — MEASURE the retest depth on every examined candle,
        # near-misses included (negative depth = wick approached but never
        # entered the range). Log-only; gates nothing; failures swallowed.
        if _sig_journal is not None:
            try:
                depth_px = ((d.orb_high - low) if d.break_direction == "long"
                            else (high - d.orb_low))
                _sig_journal("retest_check", orb={
                    "direction":        d.break_direction,
                    "attempt":          d.attempt_number,
                    "bars_since_break": d.bars_since_break,
                    "retest_depth_px":  round(depth_px, 4),
                    "orb_width":        round(d.orb_width, 4),
                    "candle": {"open": open_, "high": high,
                               "low": low, "close": close},
                })
            except Exception:
                pass

        if d.break_direction == "long":
            # (a) Runaway breakout — ran to the 50% TP with no retest → invalidate.
            # This is the setup that most favors a sweep reversal instead.
            if high >= d.target_50pct:
                d.state = ORBState.INVALIDATED
                d.invalidation_reason = "runaway"
                logger.info(
                    f"ORB INVALIDATED: ran to 50% TP ({d.target_50pct:.2f}) "
                    f"without retest — runaway breakout (favors sweep reversal)"
                )
                return
            # RETEST (v3.3): the wick must ENTER the range (low < orb_high) and the
            # BODY must stay OUTSIDE it (body_low >= orb_high). No grace band. The
            # retest is the falsification step — the level either held or it did
            # not. A body that closes back inside the range is a DISARM, not a
            # near-miss, and falls through to the (b) branch below.
            if low < d.orb_high and body_low >= d.orb_high:
                # Sweeps take priority when regime is sweep: don't confirm a
                # phantom OPEN the dispatch will override — leave it awaiting
                # retest so the engine can't get stuck OPEN with no position.
                # (v3.2) UNLESS ORB_FIRES_REGARDLESS_OF_REGIME — then ORB beats
                # sweep: confirm OPEN and let the dispatch fire it.
                if regime == "SWEEP_REVERSAL" and not ORB_FIRES_REGARDLESS_OF_REGIME:
                    logger.debug("ORB retest met but regime=SWEEP_REVERSAL — deferring to sweep")
                    return
                d.state           = ORBState.OPEN_LONG
                d.confirmed_at    = str(now_et())
                d.retest_depth_px = round(d.orb_high - low, 4)   # v3.7 defect G
                logger.info(f"ORB CONFIRMED LONG (attempt #{d.attempt_number}): wick={low:.2f} body_low={body_low:.2f}")
            # (b) Retrace into range — 1m candle closes back inside the ORB range.
            elif close < d.orb_high:
                d.state = ORBState.INVALIDATED
                d.invalidation_reason = "close_inside"
                logger.info(f"ORB INVALIDATED: 1m close={close:.2f} back inside range")
        else:
            # (a) Runaway breakout (short) — ran to the 50% TP with no retest.
            if low <= d.target_50pct:
                d.state = ORBState.INVALIDATED
                d.invalidation_reason = "runaway"
                logger.info(
                    f"ORB INVALIDATED: ran to 50% TP ({d.target_50pct:.2f}) "
                    f"without retest — runaway breakout (favors sweep reversal)"
                )
                return
            # RETEST (v3.3) — mirror of the long side. Wick enters the range
            # (high > orb_low), body stays outside (body_high <= orb_low). No grace.
            if high > d.orb_low and body_high <= d.orb_low:
                if regime == "SWEEP_REVERSAL" and not ORB_FIRES_REGARDLESS_OF_REGIME:
                    logger.debug("ORB retest met but regime=SWEEP_REVERSAL — deferring to sweep")
                    return
                d.state           = ORBState.OPEN_SHORT
                d.confirmed_at    = str(now_et())
                d.retest_depth_px = round(high - d.orb_low, 4)   # v3.7 defect G
                logger.info(f"ORB CONFIRMED SHORT (attempt #{d.attempt_number}): wick={high:.2f} body_high={body_high:.2f}")
            # (b) Retrace into range — 1m candle closes back inside the ORB range.
            elif close > d.orb_low:
                d.state = ORBState.INVALIDATED
                d.invalidation_reason = "close_inside"
                logger.info(f"ORB INVALIDATED: 1m close={close:.2f} back inside range")

    def mark_triggered(self):
        self.notify_position_closed()

    @property
    def is_confirmed(self) -> bool:
        return self._data.state in (ORBState.OPEN_LONG, ORBState.OPEN_SHORT)

    @property
    def direction(self) -> str:
        if self._data.state == ORBState.OPEN_LONG:  return "long"
        if self._data.state == ORBState.OPEN_SHORT: return "short"
        return ""


_orb_engine: Optional[ORBEngine] = None

def get_orb_engine() -> ORBEngine:
    global _orb_engine
    if _orb_engine is None:
        _orb_engine = ORBEngine()
    return _orb_engine
