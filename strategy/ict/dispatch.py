"""
strategy/ict/dispatch.py — ranked ICT dispatch, the one function main wires. v1.0
v1.0 — 2026-08-18 — INITIAL (ICT setup suite, HANDOFF_FABLE_ICT_SETUPS).

CONTRACT WITH main.py (SPEC G6 — the wiring itself is the core owner's):
  - Called BEFORE the label-keyed priority ladder in attempt_new_entry.
    Never gated on `primary_regime` — a Silver Bullet must not be discarded
    because the label read COMPRESSION (handoff §3.2.1). Any label use
    inside a setup is an explicit scored component, never a precondition.
  - Signature:  ict_dispatch(ictx, chain=None, now_et=None, journal=None)
                -> Optional[OptionsSignal]
    `journal` is main's `_sigj.journal` callable; `ictx` is built by
    context.build_context() from ctx["smc"]/structure/liq (or, once G7
    lands, handed over by the core snapshot).
  - Returns None on every non-fire path; journals EVERY setup's state
    transitions either way (a setup that never fires still leaves the
    record the priors get fitted from — handoff §5.6).
  - When it returns a signal while ORB's window is live, main journals the
    ORB preemption (`orb_preempted_by=ICTSilverBullet`) so the
    counterfactual stays measurable (§4.2 dispatch decision).

ARMING — three independent gates, all default SAFE:
  1. OT_ICT_ARMED=1            master switch (default 0: evaluate + journal
                               only — first-light mode)
  2. OT_ICT_<NAME>_VALIDATED=1 per setup, set ONLY after the harness run
                               against real tape passes the condition the
                               OPERATOR wrote before the run (§3.5)
  3. the afternoon debit cutoff: DEBIT_DIRECTIONAL setups refuse to fire
     past 11:30 ET (prior; env OT_ICT_DEBIT_CUTOFF), journaling
     `wants_credit` so F.14 (credit expression) is built against measured
     demand. This is belt-and-braces WITH main's _afternoon_debit_blocked —
     the config-set registration (SPEC G8) remains required so the fleet
     gate covers these names too.
"""

from __future__ import annotations

import logging
import os
from typing import Callable, List, Optional, Tuple

from strategy.ict.scoring import SetupScore, journal_setup_state
from strategy.ict.silver_bullet import SilverBulletSetup
from strategy.ict.judas_po3 import JudasPO3Setup
from strategy.ict.model_2022 import Model2022Setup
from strategy.ict.sweep_mss import SweepMSSSetup
from strategy.ict.breaker_unicorn import BreakerUnicornSetup
from strategy.ict.ote_confluence import OTEConfluenceSetup
from strategy.ict.ob_fvg import OBFVGSetup

logger = logging.getLogger(__name__)

RANKED = [SilverBulletSetup(), JudasPO3Setup(), Model2022Setup(),
          SweepMSSSetup(), BreakerUnicornSetup(), OTEConfluenceSetup(),
          OBFVGSetup()]
assert [s.RANK for s in RANKED] == sorted(s.RANK for s in RANKED), \
    "ICT dispatch order must match declared ranks"


def _armed() -> bool:
    return os.environ.get("OT_ICT_ARMED", "0") == "1"


def _validated(name: str) -> bool:
    return os.environ.get(f"OT_ICT_{name.upper()}_VALIDATED", "0") == "1"


def _debit_cutoff() -> Tuple[int, int]:
    raw = os.environ.get("OT_ICT_DEBIT_CUTOFF", "11:30")
    try:
        h, m = raw.split(":")
        return int(h), int(m)
    except (ValueError, AttributeError):
        return (11, 30)


def _past_debit_cutoff(now_et) -> bool:
    if now_et is None:
        return False        # no clock -> do not invent a block; main's gate stands
    return (now_et.hour, now_et.minute) >= _debit_cutoff()


def evaluate_all(ictx) -> List[SetupScore]:
    """Score every setup this tick — the journal/first-light surface."""
    out = []
    for s in RANKED:
        try:
            out.append(s.evaluate(ictx))
        except Exception as e:                      # pragma: no cover
            logger.warning("ict.dispatch: %s evaluate failed: %s", s.NAME, e)
            out.append(SetupScore(setup=s.NAME, blocked=f"evaluate_error:{e}"))
    return out


def ict_dispatch(ictx, chain=None, now_et=None, journal=None):
    """Evaluate ranked, journal transitions, return at most one signal."""
    scores = evaluate_all(ictx)
    signal = None
    for setup, sc in zip(RANKED, scores):
        if sc.fire_eligible() and signal is None:
            if setup.DEBIT_DIRECTIONAL and _past_debit_cutoff(now_et):
                sc.blocked = "wants_credit:afternoon_debit_cutoff"
            elif not _armed():
                sc.blocked = "would_fire:disarmed"
            elif not _validated(setup.NAME):
                sc.blocked = f"would_fire:unvalidated:{setup.NAME}"
            else:
                try:
                    signal = setup.generate_signal(ictx, sc, chain)
                except Exception as e:              # pragma: no cover
                    logger.warning("ict.dispatch: %s generate failed: %s",
                                   setup.NAME, e)
                    sc.blocked = f"generate_error:{e}"
        journal_setup_state(sc, journal)
    return signal
