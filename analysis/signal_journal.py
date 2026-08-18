"""
analysis/signal_journal.py — signal-time instrumentation (LOG-ONLY, never trades).
v1.3 — 2026-08-07 — N.7: every row carries `ruleset`, the short commit this
v1.3  2026-08-17  P0.3 / AX.3: `regime_ctx` now carries the RAW L1 AXES.
        It stamped every event with only the INTEGRATED label and conviction,
        and both are measured dead as entry-side quantities (RGCV.nf 1.00 vs
        .ok 0.34 in RANGING - an ANTI-signal; 1.00 vs 1.00 in trend).
        The RAW direction axis SEPARATES: nf 0.628 -> ok 0.885, gap +0.257,
        n=753 / 17 sessions (P0.1) - up from AX.2's +0.188 on n=571, so it GREW
        on more data. `regime_axes.py` reached this first on 08-07: "The RAW
        score separates where the INTEGRATED conviction does not."
        IT WAS JOURNALED NOWHERE - decompose() was a pure function main never
        called. LOG-ONLY: gates nothing, sizes nothing.
        `volatility_conf` rides along (AX.2: +0.065, never tested by P0.1
        because it was not emitted). `pair_conf` is NOT emitted - measured dead
        and structurally so.
        process is running. Resolved ONCE at import — a `git rev-parse` per
        journal line would put a subprocess in the trading loop, and a process
        runs one ruleset for its whole life anyway.
        WHY: every cross-date analysis of these rows has been pooling decisions
        from different engines with no way to say so. L3.2a could only emit
        `decision_hash: null`; the same gap was named on 07-29 about engine
        identity. Falls back to "unknown" rather than a partial hash — a wrong
        hash is worse than an absent one because it looks attributable.
        Log-only, no trading behaviour touched.

v1.1 — 2026-07-31 — N.2 + N.3: signal_ctx now carries `rrr` (reward:risk from the
        underlying levels, None when levels are absent — NOT 0.0, since "no stop"
        and "worst possible trade" must stay distinguishable), plus sweep-only
        `closes_beyond` and `sweep_age_bars`. These are FACTOR COLUMNS: they
        cannot be backfilled, so every session without them is a session of
        conditional data that will never exist. rrr in particular is what makes
        item F's MIN_RRR floor calibratable from its own rejections rather than
        vetoing invisibly.
v1.0 — 2026-07-18 — initial release.

WHY THIS EXISTS (ROADMAP Phase 3.1, verbatim):
    "Instrument first. Log at signal time, for EVERY signal (fired AND
     gate-blocked): trade type, regime, conviction, setup score, GEX context,
     fees estimate, and eventual outcome for fired ones. A gate you can't
     counterfactual is a gate you can't calibrate."

The 1-min OHLC tape is replayable forever; what is NOT reconstructible after
16:00 is what the option chain looked like at signal time — premium, bid/ask
spread, IV, greeks — and which gate disposed of the signal. This module makes
that perishable context durable. Without it, every session between now and the
Phase-3 calibration campaign is tape that can never become calibration data.

DESIGN RULES (non-negotiable):
  1. This module can NEVER crash the trading loop. Every public function
     swallows every exception (logged at DEBUG). A full disk, a bad payload,
     a permissions error — all degrade to "no journal line", never to a raised
     exception. The bot's behavior with this module present is byte-identical
     to its behavior with the module deleted.
  2. LOG-ONLY. Imports nothing from execution/, risk/, strategy/,
     notifications/. Holds no state beyond an open-file cache. Never reads
     trades.db, never touches the store.
  3. Append-only JSONL, one line per event:
         data/signal_journal/<YYYY-MM-DD>/<SYMBOL>.jsonl
     Self-locates the repo root (mirrors shadow/observer.py) — no /var/lib,
     no per-box path. Collected off-box by snapshot.sh / harvest like the
     other data/ products (add to the EOD chain when the volume justifies it).

EVENT VOCABULARY (the offline bucketer keys on `event`):
  scored        — emitted by risk/setup_scorer.score() for EVERY scored
                  signal, including below-B rejections (grade="REJECT").
                  Carries the full breakdown, thresholds, quote context.
  disposition   — emitted by main.attempt_new_entry for what happened AFTER
                  scoring: fired | sizing_rejected | invalid_signal.
                  Carries ORB retest_depth when the signal is an ORB.
  retest_check  — emitted by orb_engine._check_for_retest for every 1-min
                  candle examined while ARMED (defect G): the penetration
                  depth distribution INCLUDING near-misses (negative depth =
                  wick never entered the range). Raw px + orb_width; divide
                  by tape ATR offline (ATR-relative per defect G, never a
                  percentage).
  condor_plan   — condor plan created (regime + conviction at decision time).
  condor_leg    — condor leg trigger fired (regime + conviction at fire time).

Joining scored -> disposition -> trades.db outcome: events within the same
second for the same symbol/strategy are the same signal (the loop is
single-threaded per box; one signal per tick). `ts_et` is the join key.
"""

import json
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

# Self-locate: <repo>/analysis/signal_journal.py -> <repo>/data/signal_journal/
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT_ROOT = os.path.join(_REPO_ROOT, "data", "signal_journal")

try:
    from config import INSTRUMENT as _SYMBOL
except Exception:                                    # config unreadable — still never raise
    _SYMBOL = os.environ.get("OT_INSTRUMENT", "UNKNOWN")


def _round(x, nd=4):
    try:
        return round(float(x), nd)
    except Exception:
        return None


def contract_ctx(c) -> dict:
    """Quote context for one OptionContract — the perishable part. None-safe."""
    if c is None:
        return None
    try:
        bid, ask, mark = float(c.bid), float(c.ask), float(c.mark)
        mid = (bid + ask) / 2.0 if (bid > 0 or ask > 0) else mark
        spread = (ask - bid) if ask >= bid else 0.0
        return {
            "occ":        getattr(c, "symbol", ""),
            "strike":     _round(getattr(c, "strike", 0.0), 2),
            "type":       getattr(c, "option_type", ""),
            "bid":        _round(bid, 4),
            "ask":        _round(ask, 4),
            "mark":       _round(mark, 4),
            "mid":        _round(mid, 4),
            "spread":     _round(spread, 4),
            "spread_pct_of_mid": _round(spread / mid, 4) if mid else None,
            "iv":         _round(getattr(c, "iv", 0.0), 4),
            "delta":      _round(getattr(c, "delta", 0.0), 4),
            "theta":      _round(getattr(c, "theta", 0.0), 4),
            "volume":     int(getattr(c, "volume", 0) or 0),
            "oi":         int(getattr(c, "open_interest", 0) or 0),
        }
    except Exception:
        return None


def _rrr(signal):
    """Reward:risk from the underlying levels. None when levels are absent.

    None is deliberate and NOT 0.0: a signal with no stop has an UNKNOWN rrr,
    and recording that as zero would make it look like the worst possible trade
    in any later distribution. The two must stay distinguishable.
    """
    try:
        e = float(getattr(signal, "underlying_entry", 0.0) or 0.0)
        st = float(getattr(signal, "underlying_stop", 0.0) or 0.0)
        tg = float(getattr(signal, "underlying_target", 0.0) or 0.0)
        if e <= 0 or st <= 0 or tg <= 0:
            return None
        risk, reward = abs(e - st), abs(tg - e)
        return round(reward / risk, 4) if risk > 0 else None
    except Exception:                                          # noqa: BLE001
        return None


def signal_ctx(signal) -> dict:
    """Everything the OptionsSignal knows at signal time. None-safe."""
    if signal is None:
        return None
    try:
        d = {
            "strategy":         getattr(signal, "strategy_name", ""),
            "setup_type":       getattr(signal, "setup_type", ""),
            "direction":        getattr(signal, "direction", ""),
            "option_side":      getattr(signal, "option_side", ""),
            "underlying_entry": _round(getattr(signal, "underlying_entry", 0.0), 4),
            "underlying_stop":  _round(getattr(signal, "underlying_stop", 0.0), 4),
            "underlying_target": _round(getattr(signal, "underlying_target", 0.0), 4),
            "entry_premium":    _round(getattr(signal, "entry_premium", 0.0), 4),
            # N.2 2026-07-31 — risk:reward at SIGNAL time, computed here so every
            # consumer of signal_ctx gets it (scored, disposition, readiness).
            # Without this, item F's MIN_RRR floor would veto invisibly: there
            # would be no record of what the rrr WAS on the trades it blocked,
            # so the floor could never be calibrated from its own rejections.
            # This is a factor column — it cannot be backfilled, so every session
            # it is missing is a session of conditional data that never exists.
            "rrr":              _rrr(signal),
            # N.3 — sweep-only fields; absent (None) on every other strategy,
            # which is the honest encoding rather than a misleading 0.
            "closes_beyond":    getattr(signal, "closes_beyond", None),
            "sweep_age_bars":   getattr(signal, "sweep_age_bars", None),
            "conviction":       _round(getattr(signal, "conviction", 0.0), 4),
            "confluence":       list(getattr(signal, "confluence_factors", []) or []),
            "notes":            getattr(signal, "notes", ""),
            "contract":         contract_ctx(getattr(signal, "contract", None)),
        }
        if getattr(signal, "is_butterfly", False):
            d["is_butterfly"] = True
            d["net_debit"] = _round(getattr(signal, "net_debit", 0.0), 4)
            d["legs"] = {
                "lower":  contract_ctx(getattr(signal, "lower_contract", None)),
                "center": contract_ctx(getattr(signal, "center_contract", None)),
                "upper":  contract_ctx(getattr(signal, "upper_contract", None)),
            }
        return d
    except Exception:
        return None


def regime_ctx(regime, l1_scores=None) -> dict:
    """The regime context stamped onto every journalled event.

    ⚠️ AX.3's UNBUILT HALF (2026-08-07 → built 2026-08-17). Until now this
    carried ONLY the INTEGRATED label and conviction — and both are measured
    dead as entry-side quantities: `RGCV.nf` **1.00** vs `.ok` **0.34** in
    RANGING (an ANTI-signal), 1.00 vs 1.00 in trend.

    The RAW Layer-1 direction axis DOES separate: **nf 0.628 → ok 0.885, gap
    +0.257 on n=753 across 17 sessions** (P0.1, 2026-08-17), up from AX.2's
    +0.188 on n=571 — **it grew on more data.** `regime_axes.py`'s own header
    reached the conclusion first: *"The RAW score separates where the INTEGRATED
    conviction does not, which points at Layer-2 integration as a possible
    destroyer of signal."*

    **It was journaled NOWHERE.** A measured separator that drives nothing and
    is not even recorded cannot be confirmed forward. This emits it.

    ⚠️ LOG-ONLY. Gates nothing, sizes nothing, changes no trading behaviour.
    Emission is the PRECONDITION for testing it forward under the same
    pre-registered criterion, not a decision to use it.
    ⚠️ `volatility_conf` rides along — AX.2 measured it separating too (+0.065,
    n=571) and P0.1 never tested it, because it was not being emitted either.
    ⚠️ `pair_conf` is NOT emitted. It is MEASURED DEAD (+0.001) and the failure
    is structural, not tunable — `min()` over a sparse axis collapses to zero.
    Emitting it would invite exactly the re-litigation its own note forbids.
    """
    if regime is None:
        return None
    try:
        out = {
            "label":      str(getattr(regime, "primary_regime", "")),
            "conviction": _round(getattr(regime, "conviction", 0.0), 4),
        }
        if l1_scores:
            try:
                from analysis.regime_axes import decompose
                ax = decompose(l1_scores)
                out["direction"]        = ax.get("direction")
                out["direction_conf"]   = ax.get("direction_conf")
                out["direction_margin"] = ax.get("direction_margin")
                out["volatility"]       = ax.get("volatility")
                out["volatility_conf"]  = ax.get("volatility_conf")
            except Exception:                                  # noqa: BLE001
                # ⚠️ NEVER let a telemetry decomposition break a journal write.
                # The event still carries label+conviction; the axes are simply
                # absent, and absent is distinguishable from zero downstream.
                pass
        return out
    except Exception:
        return None


def vol_ctx(vol_state) -> dict:
    if vol_state is None:
        return None
    try:
        return {
            "atr":            _round(getattr(vol_state, "atr_current", 0.0), 4),
            "bb_width":       _round(getattr(vol_state, "bb_width_current", 0.0), 6),
            "vwap":           _round(getattr(vol_state, "vwap", 0.0), 4),
            "price_vs_vwap":  getattr(vol_state, "price_vs_vwap", ""),
        }
    except Exception:
        return None


def macro_ctx(macro) -> dict:
    if macro is None:
        return None
    try:
        return {
            "vix":        _round(getattr(macro, "vix", 0.0), 2),
            "vix_regime": getattr(macro, "vix_regime", ""),
            "is_fed_day": bool(getattr(macro, "is_fed_day", False)),
        }
    except Exception:
        return None


# ── v1.2 — RULESET STAMP (N.7) ────────────────────────────────────────────────
# Every analysis that pools journal rows across dates is pooling DECISIONS FROM
# DIFFERENT ENGINES, and until now nothing recorded which. 2026-08-07 alone
# changed the emission law (conviction_integrator v2.2), the regime set (sweep
# left the argmax), two dispatch gates (SWP.1, CNT.1), an exit gate (CNT.2) and
# two floors (SWP.2, CNT.3). A rejection ledger or gate calibration spanning
# that window averages six rulesets and cannot say so.
#
# This is the same gap named on 2026-07-29 about ENGINE IDENTITY, where the fix
# proposed then was exactly this: stamp the producer onto the row so quarantine
# becomes a WHERE clause instead of a 15-box log archaeology dig. L3.2a hit it
# again from the other side and could only emit `decision_hash: null`.
#
# Resolved ONCE at import, not per row: `git rev-parse` per journal line would
# add a subprocess to the trading loop, which is exactly the kind of cost that
# does not belong there. A process runs one ruleset for its whole life, so
# import time is the correct and only moment this can change.
# "unknown" when git is unavailable — NEVER a fabricated or partial hash, since
# a wrong hash is worse than an absent one: it would silently pool engines while
# LOOKING attributable.
def _resolve_ruleset() -> str:
    try:
        import subprocess                                        # noqa: PLC0415
        r = subprocess.run(
            ["git", "-C", os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
             "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5)
        return (r.stdout or "").strip() or "unknown"
    except Exception:                                            # noqa: BLE001
        return "unknown"


_RULESET = _resolve_ruleset()


def ruleset() -> str:
    """The commit this process is running. Stamped on every journal row."""
    return _RULESET


def journal(event: str, **sections):
    """
    Append one JSONL event line. Swallows ALL exceptions — a journal failure
    must never become a trading-loop failure. Sections are pre-built dicts
    (use the *_ctx helpers) or plain scalars.
    """
    try:
        now = datetime.now(tz=ET)
        row = {"ts_et": now.isoformat(timespec="seconds"),
               "symbol": _SYMBOL,
               "event": event,
               "ruleset": _RULESET}   # v1.2 — which engine made this decision
        for k, v in sections.items():
            if v is not None:
                row[k] = v
        day_dir = os.path.join(_OUT_ROOT, now.strftime("%Y-%m-%d"))
        os.makedirs(day_dir, exist_ok=True)
        path = os.path.join(day_dir, f"{_SYMBOL}.jsonl")
        with open(path, "a") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except Exception as e:                            # noqa: BLE001 — by design
        logger.debug(f"signal_journal write skipped: {e}")
