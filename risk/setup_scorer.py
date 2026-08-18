"""
risk/setup_scorer.py — Scores and grades options trade signals A/B.
v1.7 — 2026-08-13 — CONTINUATION GETS AN EXPLICIT PROFILE. It had none, so it
        fell through to `"default"` — a silent default nobody chose for the
        strategy carrying 77%% of fleet volume. In that profile
        `regime_conviction` weighs 0.30 and `signal_quality` 0.25, and
        continuation_strategy.py sets `signal.conviction = regime.conviction`.
        THE SAME NUMBER, WEIGHTED TWICE = 55%% of the grade. Measured over 619
        joined trades (scorer_backtest, 18 sessions): both dimensions report
        identical medians AND identical spreads (0.913 / 0.636), because they
        are one column printed twice. `vwap_alignment` and `liquidity_clear`
        measured CONSTANT at 1.000 across all 619 — another 35%%. So ~90%% of
        the grade was a duplicate or a constant, and the grade INVERTED:
        A 399 trades -$8,244 (-$21/trade at 1.5x size) vs B 220 trades
        +$1,893 (+$9). High conviction means the trend is already obvious,
        which means LATE — v1.4 stripped exactly this from the ORB, calling it
        "regime conviction in costume", and left it on continuation.
        THE TOTAL IS ARITHMETICALLY UNCHANGED: 0.55*conv + 0.15*vwap +
        0.20*liq + 0.10*macro is what the default profile already computed via
        0.30+0.25 on one number. grade_b stays 0.55, so THE FIRE/NO-FIRE
        POPULATION IS PROVABLY IDENTICAL — this deploy cannot change which
        setups trade. The ONLY behavioural change is grade_a, set above the
        reachable maximum (1.00) so no continuation setup earns the 1.5x size
        upgrade on a grade measured to be anti-predictive. The bar comes back
        DOWN onto whatever `tests/factor_sweep.py` proves separates; it is not
        a permanent verdict, it is a refusal to pay 1.5x for a coin flip.
        `signal_quality` is still journalled (breakdown is built before the
        weighted sum) — it is telemetry now, not a grade input.
v1.6 — 2026-07-31 — F: MIN_RRR FLOOR. Second genesis constant (`MIN_RRR = 1.3
        # UNWIRED`), read by nothing since the beginning. MEASURED premise: a
        setup with rrr = 1.00 scores 0.84 and grades **A** — a 1:1 risk-reward
        trade is currently a top-grade fire, because the 5-dimension scorer has
        no RRR input at all. Hard floor on the scored path; **ORB is
        COUNTER-ONLY, never blocked** — its RRR is structural (stop = range
        boundary, target = measured move), so a narrow range mechanically
        produces a low ratio without the setup being worse, and gating the only
        strategy currently earning on a ratio it does not control is not a trade
        we make on zero evidence. Measure first. rrr of None (no planned stop or
        target) is INERT, not a violation: absence of evidence must not collapse
        into "worst possible trade". Ships DEFAULT OFF (`OT_MIN_RRR_ACTIVE`),
        floor `OT_MIN_RRR` default 1.3 — the genesis value, explicitly a PRIOR
        awaiting the Aug 1 fit, not a fitted number.
v1.5 — 2026-07-31 — E: VWAP HARD GATE. `vwap_alignment` scores 0.11 against a
        0.55 grade-B bar, so misalignment could never veto — a long BELOW vwap
        scored 0.73 and graded B (measured, not hypothesised). The gate now
        blocks, placed AFTER the score is final so the journal records what the
        blocked setup WOULD have graded; blocking earlier would save microseconds
        and destroy the evidence the retro ledger needs. Ships DEFAULT OFF
        (`OT_VWAP_FILTER_ACTIVE`) as a log-only counter until blocked trades are
        shown net-negative — evidence decides. ORB exempt by construction (it
        short-circuits to _grade_orb and never reaches here), matching defect V.
        Inert when `price_vs_vwap == "NONE"` (the 07-17 SPX zero-volume case:
        VWAP undefined is not VWAP misaligned) and on neutral direction.
        +`_journal_gate_block()` emitting N.2's `gate_block:<gate>` disposition —
        without it a gate vetoes invisibly and can never be calibrated from its
        own rejections.
v1.4 — 2026-07-22 — ORB IS A GEOMETRY GATE, NOT A WEIGHTED SCORE. The ORB
        was being run through the same 5-dimension weighted sum as every
        other strategy (regime_conviction, orb_quality, vwap_alignment,
        liquidity_clear, macro_context). That was wrong for this trade by
        design: the ORB is regime-AGNOSTIC (it is deliberately not regime-
        gated at dispatch) yet regime_conviction was 20%% of its grade; VWAP
        and macro have no bearing on a mechanically-confirmed break+retest;
        and orb_quality was a confluence-COUNT proxy (0.2*n) that never
        measured the geometry its docstring claimed. Net effect: the A/B
        grade of an ORB was regime conviction in costume, and liquidity-in-
        path could VETO a confirmed setup by dragging the weighted total
        under the bar.
        NOW: the ORB short-circuits BEFORE the weighted machinery. A
        confirmed ORB ALWAYS trades. The ONLY grade input is whether an
        unswept liquidity pool sits between the breakout and the 100%% TP:
          - clear path  -> A (1.5x size)
          - pool in path -> B (1.0x size)
        Liquidity can downgrade A->B; it can NEVER veto. No regime, no VWAP,
        no macro, no confluence count, no brief nudge, no session modifier
        touch the ORB grade. _orb_quality is DELETED. The 5-dimension path is
        unchanged for SweepReversal / Butterfly / Condor / default.
v1.3 — 2026-07-18 — SIGNAL JOURNAL (ROADMAP Phase 3.1 instrumentation, log-only):
        every scored signal — including below-B REJECTS — emits one `scored`
        event to analysis/signal_journal with the full breakdown, thresholds,
        regime conviction, quote context (bid/ask/spread/IV at signal time)
        and vol/macro snapshot. Zero behavior change: the journal call is
        wrapped so any failure degrades to a missing log line, never an
        exception; grading logic is untouched. This is the perishable data
        the Phase-3 conviction-bar buckets need — "a gate you can't
        counterfactual is a gate you can't calibrate."
v1.2 — 2026-07-15 — BRIEF NUDGE: a signed post-sum adjustment (cap ±0.05) from
        the pre-market move-probability brief. This box reads its own line from
        ~/brief_flags.json ({symbol, strength 0..1, date}); the nudge is
        +strength·cap for ORB (catalyst helps a breakout), -strength·cap for
        butterfly/condor (catalyst fights a pin/range), and ZERO for sweep
        reversal (structure-driven, catalyst-agnostic). Applied to the final
        total AFTER the weighted sum and late-session modifier, BEFORE the
        grade compare — so the ±0.05 lands literally on the score as a
        tie-breaker; it can never rescue a bad setup or sink a good one.
        Absent/stale/mismatched flag file => strength 0 => no nudge. Knob:
        config.BRIEF_CONVICTION_WEIGHT (default 0.05).
v3.0 — original release — A/B/C grading
v1.1 — 2026-06-30 — eliminated C grade entirely. There is no such thing
        as a C-grade setup by definition — anything below the B threshold
        is not a valid trade and returns None instead of a downsized
        position. This prevents marginal/low-conviction setups from ever
        firing in live trading regardless of available capital.
        Grade determines position size multiplier: A=1.5x, B=1.0x.
v1.2 — 2026-07-02 — remove duplicate Fed-day boost. is_fed_day was being
        applied twice on ORB: once in the macro_context dimension (its
        designated home) and again inside _orb_quality, double-counting the
        effect and polluting a dimension that measures confluence/regime/
        liquidity. Fed-day now boosts ORB through macro_context only.
v3.0 — 2026-07-10 — repo-wide v3.0 bump: Yahoo-Finance purge & data stream
        mapping optimization (all market data now flows from the single
        shared TastyTrade candle feed — see data/candle_feed.py). No logic
        change in this file.
v-namelevels (2026-07-28) — ORB grade line names the pools in path instead of
        counting them ("2 pool(s) in path: PDL@371.65, ..."), and the breakdown gains
        pools_in_path_detail. Observability only; grading unchanged.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from strategy.base_strategy import OptionsSignal
from analysis.regime_classifier import RegimeState, Regime
from analysis.volatility_engine import VolatilityState
from analysis.structure_analyzer import StructureMap
from analysis.liquidity_mapper import LiquidityMap
from data.macro_data import MacroSnapshot
from config import (GRADE_SIZE_MULTIPLIER, GRADE_A_MIN_SCORE,
                    GRADE_B_MIN_SCORE, VWAP_FILTER_ACTIVE,
                    MIN_RRR, MIN_RRR_ACTIVE)
try:
    from config import BRIEF_CONVICTION_WEIGHT
except Exception:
    BRIEF_CONVICTION_WEIGHT = 0.05
from utils.time_utils import current_session_label

# Signal journal (v1.3) — log-only instrumentation. Guarded import: if the
# module is absent or broken the scorer runs exactly as before.
try:
    from analysis import signal_journal as _journal
except Exception:
    _journal = None

logger = logging.getLogger(__name__)


@dataclass
class SetupScore:
    grade:           str   = "B"
    score:           float = 0.0
    size_multiplier: float = 1.0
    breakdown:       dict  = None

    def __post_init__(self):
        if self.breakdown is None:
            self.breakdown = {}


# ─── Strategy-specific scoring profiles ──────────────────────────────────────

STRATEGY_PROFILES = {
    # ORB IS NOT SCORED HERE (v1.4). It short-circuits to _grade_orb before the
    # weighted sum: a confirmed ORB always trades, graded A/B on liquidity-in-
    # path ONLY. This profile is retained for reference/telemetry but these
    # weights are DEAD for the ORB — do not re-point score() at them.
    "ORBStrategy": {
        "score_weights": {},   # unused — see _grade_orb
        "grade_a": 0.78,       # retained for any legacy reader; not applied
        "grade_b": 0.55,
    },
    # CONTINUATION (v1.7). Was absent -> fell to "default", which weighted
    # regime.conviction twice under two names (0.30 regime_conviction +
    # 0.25 signal_quality, and signal.conviction IS regime.conviction).
    # 0.55 is those two summed: the arithmetic is identical, the double count
    # is gone, and grade_b 0.55 keeps the fire boundary byte-for-byte.
    # grade_a is ABOVE THE MAXIMUM ACHIEVABLE TOTAL (0.55+0.15+0.20+0.10 =
    # 1.00) BY DESIGN: no measured input separates continuation winners from
    # losers, so nothing here earns 1.5x size. Lower it the moment factor_sweep
    # names an input that does. vwap_alignment and liquidity_clear are retained
    # at weight despite measuring constant across 619 trades — constant IN
    # SAMPLE is not constant BY CONSTRUCTION, and dropping them would remove a
    # veto that has never been observed to fire but can.
    "ContinuationStrategy": {
        "score_weights": {
            "regime_conviction":    0.55,
            "vwap_alignment":       0.15,
            "liquidity_clear":      0.20,
            "macro_context":        0.10,
        },
        "grade_a": 1.01,
        "grade_b": 0.55,
    },
    "SweepReversal": {
        "score_weights": {
            "regime_conviction":    0.25,
            "sweep_quality":        0.35,   # Rejection %, freshness, named level
            "vwap_alignment":       0.10,
            "liquidity_clear":      0.20,
            "macro_context":        0.10,
        },
        "grade_a": 0.75,
        "grade_b": 0.52,
    },
    "ButterflyStrategy": {
        "score_weights": {
            "regime_conviction":    0.30,   # Need clean ranging regime
            "range_quality":        0.35,   # BB width, ADX, time in range
            "vwap_alignment":       0.15,
            "liquidity_clear":      0.10,
            "macro_context":        0.10,
        },
        "grade_a": 0.75,
        "grade_b": 0.52,
    },
    "default": {
        "score_weights": {
            "regime_conviction":    0.30,
            "signal_quality":       0.25,
            "vwap_alignment":       0.15,
            "liquidity_clear":      0.20,
            "macro_context":        0.10,
        },
        "grade_a": 0.78,
        "grade_b": 0.55,
    },
}


class SetupScorer:
    """
    Scores an options signal using strategy-specific weights.
    Returns A or B grade only — anything scoring below the B threshold
    is not a valid trade and returns None.
    """

    def _brief_strength(self) -> float:
        """This box's pre-market move-strength (0..1) from ~/brief_flags.json,
        cached for the process. Any problem — missing file, stale date, wrong
        symbol, malformed — yields 0.0 (no nudge). Never raises."""
        if getattr(self, "_brief_cached", None) is not None:
            return self._brief_cached
        strength = 0.0
        try:
            import os, json, datetime
            path = os.path.expanduser("~/brief_flags.json")
            my_symbol = os.environ.get("OT_INSTRUMENT", "")
            if os.path.isfile(path):
                with open(path) as fh:
                    d = json.load(fh)
                today = datetime.date.today().isoformat()
                if d.get("symbol") == my_symbol and d.get("date") == today:
                    strength = max(0.0, min(1.0, float(d.get("strength", 0.0))))
        except Exception:
            strength = 0.0
        self._brief_cached = strength
        return strength

    def score(self,
              signal:    OptionsSignal,
              regime:    RegimeState,
              vol_state: VolatilityState,
              structure: StructureMap,
              liq_map:   LiquidityMap,
              macro:     Optional[MacroSnapshot] = None) -> Optional[SetupScore]:
        """
        Returns SetupScore for A or B grade setups only.
        Returns None if the setup scores below the B threshold —
        there is no C grade. A below-threshold setup is not a trade.
        """

        breakdown = {}
        name      = signal.strategy_name
        profile   = STRATEGY_PROFILES.get(name, STRATEGY_PROFILES["default"])
        weights   = profile["score_weights"]
        grade_a   = profile["grade_a"]
        grade_b   = profile["grade_b"]

        # ── ORB: geometry gate, not a weighted score (v1.4) ───────────────────
        # A confirmed ORB break+retest ALWAYS trades — the ORB state machine
        # already validated the geometry (body/wick rules) before this signal
        # existed, and the trade is regime-agnostic by design. The ONLY grade
        # input is liquidity in the path to the 100%% TP: clear -> A, pool in
        # the way -> B. Never a veto. Nothing else (regime/VWAP/macro/session/
        # brief) touches it. Returns here, before the 5-dimension machinery.
        if name == "ORBStrategy":
            return self._grade_orb(signal, liq_map, regime, vol_state, macro)

        # ── 1. Regime Conviction ──────────────────────────────────────────────
        reg_score = regime.conviction
        breakdown["regime_conviction"] = round(reg_score, 3)

        # ── 2. Strategy-specific quality score ───────────────────────────────
        if name == "SweepReversal":
            quality_score = self._sweep_quality(signal, liq_map, regime)
            breakdown["sweep_quality"] = round(quality_score, 3)
        elif name == "ButterflyStrategy":
            quality_score = self._range_quality(regime, vol_state)
            breakdown["range_quality"] = round(quality_score, 3)
        else:
            quality_score = signal.conviction
            breakdown["signal_quality"] = round(quality_score, 3)

        # ── 3. VWAP alignment ─────────────────────────────────────────────────
        vwap_score = 0.5
        if vol_state.vwap > 0:
            if signal.direction == "long" and vol_state.price_vs_vwap == "ABOVE":
                vwap_score = 1.0
            elif signal.direction == "short" and vol_state.price_vs_vwap == "BELOW":
                vwap_score = 1.0
            elif signal.direction == "neutral":
                vwap_score = 0.7   # Butterfly — VWAP matters less
            else:
                vwap_score = 0.25
        breakdown["vwap_alignment"] = round(vwap_score, 3)

        # ── 4. Liquidity path clear ───────────────────────────────────────────
        # (ORB never reaches here — it is graded by _grade_orb and returns
        # above. This weighted liquidity dimension is for sweep/condor/default;
        # it reuses the same path test but as a graded drag, not an A/B pick.)
        liq_score = 1.0
        if not signal.is_butterfly:
            pools_blocking = self._pools_in_path(signal, liq_map)
            liq_score = max(1.0 - len(pools_blocking) * 0.25, 0.0)
        breakdown["liquidity_clear"] = round(liq_score, 3)

        # ── 5. Macro context ──────────────────────────────────────────────────
        macro_score = 0.5
        if macro:
            if macro.is_fed_day and name == "ORBStrategy":
                macro_score = 1.0   # Fed day boosts ORB
            elif macro.vix_regime == "LOW":
                macro_score = 0.8
            elif macro.vix_regime == "ELEVATED":
                macro_score = 0.3
            elif macro.vix_regime == "CRISIS":
                macro_score = 0.0
            elif macro.vix_regime == "NORMAL":
                macro_score = 0.6
        breakdown["macro_context"] = round(macro_score, 3)

        # ── Weighted total ────────────────────────────────────────────────────
        total = 0.0
        for dim, w in weights.items():
            val = breakdown.get(dim, 0.5)
            total += val * w

        # Session time modifier — penalize late-session entries
        session = current_session_label()
        if session == "late_session":
            total *= 0.85

        # ── Brief nudge (v1.2) — signed pre-market prior, post-sum tie-breaker ──
        # ORB: +  (catalyst supports a breakout)
        # Butterfly/Condor: -  (catalyst fights a pin/range)
        # SweepReversal: 0  (structure-driven; catalyst-agnostic)
        brief_sign = {"ORBStrategy": 1.0,
                      "ButterflyStrategy": -1.0,
                      "IronCondorStrategy": -1.0,
                      "SweepReversal": 0.0}.get(name, 0.0)
        if brief_sign != 0.0:
            nudge = brief_sign * self._brief_strength() * BRIEF_CONVICTION_WEIGHT
            if nudge != 0.0:
                total += nudge
                breakdown["brief_nudge"] = round(nudge, 4)

        # ── E — VWAP HARD GATE (2026-07-31) ───────────────────────────────────
        # Placed AFTER the score is final, deliberately: the journal then records
        # what the blocked setup WOULD have graded, which is exactly what the
        # retro ledger needs to answer "did this gate block winners?". Blocking
        # earlier would save a few microseconds and destroy the evidence.
        #
        # Scoring alone cannot veto: misalignment costs 0.11 against a 0.55 bar,
        # so a short into strength still grades B and fires. This makes it a
        # block. ORB never reaches here (short-circuits to _grade_orb at the top
        # of score()), which is the defect-V exemption for free.
        #
        # THREE WAYS THIS DELIBERATELY DOES NOT FIRE:
        #  1. VWAP_FILTER_ACTIVE defaults OFF — it counts and journals but does
        #     not block until the retro ledger convicts. Evidence decides.
        #  2. price_vs_vwap == "NONE" means VWAP is UNDEFINED, not misaligned.
        #     That is the 07-17 zero-volume case: SPX cash prints volume=0, so
        #     VWAP is NaN and every index setup would be vetoed by an
        #     unmeasurable condition. Inert, never a false veto.
        #  3. direction "neutral" (butterfly/condor) has no VWAP side to be on.
        _misaligned = (
            vol_state.vwap > 0
            and getattr(vol_state, "price_vs_vwap", "NONE") in ("ABOVE", "BELOW")
            and signal.direction in ("long", "short")
            and not ((signal.direction == "long"
                      and vol_state.price_vs_vwap == "ABOVE")
                     or (signal.direction == "short"
                         and vol_state.price_vs_vwap == "BELOW"))
        )
        if _misaligned:
            _would_grade = ("A" if total >= grade_a
                            else "B" if total >= grade_b else "REJECT")
            breakdown["vwap_gate"] = ("BLOCK" if VWAP_FILTER_ACTIVE
                                      else "would_block")
            logger.info(
                f"VWAP gate {'BLOCK' if VWAP_FILTER_ACTIVE else 'WOULD BLOCK'}: "
                f"{name} {signal.direction} with price "
                f"{vol_state.price_vs_vwap} VWAP {vol_state.vwap:.2f} — "
                f"setup scored {total:.2f} ({_would_grade})"
            )
            if VWAP_FILTER_ACTIVE:
                self._journal_scored(signal, regime, vol_state, macro,
                                     total, f"GATE_BLOCK_VWAP({_would_grade})",
                                     breakdown, grade_a, grade_b, session)
                self._journal_gate_block(signal, regime, vol_state, "vwap",
                                         f"{signal.direction} with price "
                                         f"{vol_state.price_vs_vwap} VWAP, "
                                         f"would have graded {_would_grade}")
                return None

        # ── F — MIN_RRR FLOOR (2026-07-31) ────────────────────────────────────
        # Second genesis constant. `MIN_RRR = 1.3  # UNWIRED` sat in config from
        # the beginning, read by nothing. Placed here for the same reason as E:
        # after the score is final, so a blocked setup's journal row records what
        # it WOULD have graded and the floor can be fitted from its own
        # rejections rather than guessed.
        #
        # rrr is None when the signal has no planned stop or target. That is NOT
        # a floor violation — it is an absence of evidence, and treating it as
        # 0.0 would veto every such signal. Inert.
        _rrr = self._rrr_of(signal)
        if _rrr is not None and _rrr < MIN_RRR:
            _would_grade = ("A" if total >= grade_a
                            else "B" if total >= grade_b else "REJECT")
            breakdown["rrr"] = round(_rrr, 3)
            breakdown["rrr_gate"] = "BLOCK" if MIN_RRR_ACTIVE else "would_block"
            logger.info(
                f"RRR floor {'BLOCK' if MIN_RRR_ACTIVE else 'WOULD BLOCK'}: "
                f"{name} rrr={_rrr:.2f} < {MIN_RRR:.2f} — "
                f"setup scored {total:.2f} ({_would_grade})"
            )
            if MIN_RRR_ACTIVE:
                self._journal_scored(signal, regime, vol_state, macro,
                                     total, f"GATE_BLOCK_RRR({_would_grade})",
                                     breakdown, grade_a, grade_b, session)
                self._journal_gate_block(signal, regime, vol_state, "rrr",
                                         f"rrr={_rrr:.2f} < floor {MIN_RRR:.2f}, "
                                         f"would have graded {_would_grade}")
                return None
        elif _rrr is not None:
            breakdown["rrr"] = round(_rrr, 3)

        # ── Grade — A or B only. No C grade exists. ─────────────────────────────
        if total >= grade_a:
            grade = "A"
        elif total >= grade_b:
            grade = "B"
        else:
            logger.info(
                f"Setup REJECTED — below B threshold: score={total:.2f} "
                f"(need >= {grade_b:.2f}) strategy={name} "
                f"breakdown={breakdown}"
            )
            self._journal_scored(signal, regime, vol_state, macro,
                                 total, "REJECT", breakdown,
                                 grade_a, grade_b, session)
            return None

        multiplier = GRADE_SIZE_MULTIPLIER[grade]

        result = SetupScore(
            grade=grade,
            score=round(total, 3),
            size_multiplier=multiplier,
            breakdown=breakdown
        )

        logger.info(
            f"Setup grade: {grade} score={total:.2f} "
            f"strategy={name} mult={multiplier}x "
            f"breakdown={breakdown}"
        )
        self._journal_scored(signal, regime, vol_state, macro,
                             total, grade, breakdown,
                             grade_a, grade_b, session)
        return result

    @staticmethod
    def _rrr_of(signal):
        """Reward:risk from the planned underlying levels — the SAME computation
        signal_journal writes onto every scored event (N.2), imported rather than
        re-derived so the gate can never disagree with its own audit trail.

        Returns None, not 0.0, when levels are missing. That distinction is the
        whole point: "no stop planned" and "worst possible trade" must not
        collapse into the same number, or the floor would veto every signal that
        simply did not populate a stop.
        """
        if _journal is None:
            return None
        try:
            return _journal._rrr(signal)
        except Exception:                                          # noqa: BLE001
            return None

    @staticmethod
    def _journal_gate_block(signal, regime, vol_state, gate: str, detail: str):
        """N.2 — `gate_block:<gate>` disposition, emitted whenever a hard gate
        vetoes a setup that had already been scored.

        WHY THIS IS NOT OPTIONAL: without it a gate vetoes INVISIBLY. There would
        be no record of what was blocked, so the gate could never be calibrated
        from its own rejections, and L3.2 could not label a block as
        dodged-a-loss vs missed-a-winner. A gate that cannot be audited is a
        guess that compounds.
        """
        if _journal is None:
            return
        try:
            _journal.journal(
                "disposition",
                outcome = f"gate_block:{gate}",
                signal  = _journal.signal_ctx(signal),
                regime  = _journal.regime_ctx(regime),
                vol     = _journal.vol_ctx(vol_state),
                gate    = {"name": gate, "detail": detail},
            )
        except Exception:
            pass

    @staticmethod
    def _journal_scored(signal, regime, vol_state, macro,
                        total, grade, breakdown, grade_a, grade_b, session):
        """v1.3 — one `scored` event per scored signal, REJECTs included.
        Log-only; every failure is swallowed inside signal_journal."""
        if _journal is None:
            return
        try:
            _journal.journal(
                "scored",
                signal   = _journal.signal_ctx(signal),
                regime   = _journal.regime_ctx(regime),
                vol      = _journal.vol_ctx(vol_state),
                macro    = _journal.macro_ctx(macro),
                score    = {"total": round(float(total), 4),
                            "grade": grade,
                            "grade_a_bar": grade_a,
                            "grade_b_bar": grade_b,
                            "breakdown": breakdown,
                            "session": session},
            )
        except Exception:
            pass

    def _grade_orb(self, signal: OptionsSignal,
                   liq_map:   LiquidityMap,
                   regime:    RegimeState,
                   vol_state: VolatilityState,
                   macro) -> Optional["SetupScore"]:
        """The WHOLE ORB grade (v1.4). A confirmed ORB always trades; the only
        question is size.

        A  — no unswept liquidity pool between the breakout and the 100%% TP.
        B  — a pool sits in that path (the target may not be cleanly
             reachable), so the same setup trades at base size.

        There is no REJECT branch here: a confirmed ORB is never a no-trade on
        quality grounds. (Session/RTH/cutoff gating lives in session_guard, not
        here.) Regime, VWAP, macro, confluence count and the brief nudge are
        deliberately absent — this trade is geometry, validated upstream by the
        ORB state machine, plus one liquidity modifier.
        """
        pools_blocking = self._pools_in_path(signal, liq_map)
        grade = "A" if not pools_blocking else "B"
        multiplier = GRADE_SIZE_MULTIPLIER[grade]

        # v-namelevels 2026-07-28: name the pools, don't just count them. A bare
        # count is unauditable — "2 pool(s) in path" cost us an hour tracing an
        # AVGO ORB entry that this gate delayed by 6 ticks.
        _pool_names = ", ".join(
            f"{getattr(p, 'name', None) or 'unnamed'}@{getattr(p, 'price', 0.0):.2f}"
            for p in pools_blocking) or "none"

        breakdown = {
            "orb_geometry": "confirmed",          # the gate the state machine passed
            "pools_in_path": len(pools_blocking),
            "pools_in_path_detail": _pool_names,
            "liquidity_path": "clear" if grade == "A" else "pool_in_path",
        }

        logger.info(
            f"ORB grade: {grade} ({'clear path' if grade=='A' else ''}"
            f"{len(pools_blocking)} pool(s) in path: {_pool_names}) mult={multiplier}x"
        )
        # Journal it like any other scored signal (REJECT path is unreachable
        # for the ORB, so grade is always A or B here). total is reported as
        # the multiplier for a stable numeric field; there is no weighted sum.
        # F — ORB IS COUNTER-ONLY, NEVER BLOCKED. The ORB's RRR is structural:
        # the stop is the range boundary and the target is a measured move, so a
        # narrow range mechanically produces a low rrr without the setup being
        # worse. Gating a mechanical trade on a ratio it does not control is how
        # you delete the only strategy currently earning. Measure first: how
        # often WOULD a confirmed ORB fail the floor, and did those trades lose?
        # Only that answer justifies ever gating it.
        _orb_rrr = self._rrr_of(signal)
        if _orb_rrr is not None:
            breakdown["rrr"] = round(_orb_rrr, 3)
            if _orb_rrr < MIN_RRR:
                breakdown["rrr_gate"] = "counter_only"
                logger.info(
                    f"RRR floor COUNTER (ORB never blocked): rrr={_orb_rrr:.2f} "
                    f"< {MIN_RRR:.2f} — grade {grade}, trading anyway"
                )
        self._journal_scored(signal, regime, vol_state, macro,
                             float(multiplier), grade, breakdown,
                             grade_a=None, grade_b=None,
                             session=current_session_label())
        return SetupScore(
            grade=grade,
            score=round(float(multiplier), 3),
            size_multiplier=multiplier,
            breakdown=breakdown,
        )

    @staticmethod
    def _pools_in_path(signal, liq_map) -> list:
        """Unswept pools between entry and the 100%% TP, in the trade direction.
        A long is blocked by an unswept HIGH between entry and target; a short
        by an unswept LOW. This is the same path test the old dimension-4
        used — now it selects A vs B instead of subtracting a weighted drag."""
        return [
            p for p in liq_map.pools
            if not p.swept and (
                (signal.direction == "long"  and p.kind == "high" and
                 signal.underlying_entry < p.price < signal.underlying_target) or
                (signal.direction == "short" and p.kind == "low" and
                 signal.underlying_target < p.price < signal.underlying_entry)
            )
        ]

    def _sweep_quality(self, signal: OptionsSignal,
                        liq_map: LiquidityMap,
                        regime: RegimeState) -> float:
        """Sweep quality: rejection %, freshness, named level."""
        if not liq_map.recent_sweep:
            return 0.3
        sweep = liq_map.recent_sweep
        rejection_score = min(sweep.rejection_pct / 0.01, 1.0)
        age_score       = max(0, 1 - (liq_map.sweep_age_bars / 8))
        named_bonus     = 0.15 if sweep.swept_named_level else 0.0
        return min(rejection_score * 0.45 + age_score * 0.4 + named_bonus, 1.0)

    def _range_quality(self, regime: RegimeState,
                        vol_state: VolatilityState) -> float:
        """Ranging quality: low ADX, BB squeeze, stable ATR."""
        adx_score = max(0, 1 - regime.adx / 25)
        bb_score  = max(0, 1 - vol_state.bb_width_pct * 3)
        vol_score = 1.0 if vol_state.atr_state in ("STABLE", "CONTRACTING") else 0.5
        return adx_score * 0.4 + bb_score * 0.4 + vol_score * 0.2


# Singleton
_scorer: Optional[SetupScorer] = None


def get_setup_scorer() -> SetupScorer:
    global _scorer
    if _scorer is None:
        _scorer = SetupScorer()
    return _scorer
