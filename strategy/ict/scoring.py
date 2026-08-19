"""
strategy/ict/scoring.py — continuous setup scoring + ICT size mapping. v1.0
v1.0 — 2026-08-18 — INITIAL (ICT setup suite, HANDOFF_FABLE_ICT_SETUPS).

THE CENTRAL REQUIREMENT (handoff §2.1): score a setup CONTINUOUSLY as its
preconditions accumulate, be honest that the score is <100%, and never
report certainty the inputs cannot support. Concretely:

  score        = Σ(weight·value over AVAILABLE components) / Σ(weight, available)
  completeness = Σ(weight over AVAILABLE components)       / Σ(weight, all)

Both are journaled on every state change. FIRING requires all three:
  score ≥ OT_ICT_SCORE_FLOOR  AND  completeness ≥ OT_ICT_COMPLETENESS_FLOOR
  AND every REQUIRED component available AND passing its own floor.
A component whose input the context registers as unavailable contributes
NOTHING to score and CAPS completeness — it can never be mistaken for a
measured zero (STR.2). This is how "3-of-4 formed is a STATE" becomes a
number the journal can carry, and how a CORE_GAP shows up as capped
completeness instead of a silently weaker score.

SIZING (handoff §2.1): size is a function of ICT BIAS QUALITY and
DISPLACEMENT only — never of the legacy conviction number. Tiers are stated
PRIORS (env-tunable, named in the changelog, fitted later from this box's
own journal per §3.4):
  bias < 0.50 or displacement < AWARE(1.75)          -> 0.00 (no trade)
  displacement ≥ CONFIRM(2.0) and bias ≥ 0.85        -> 1.00
  displacement ≥ CONFIRM(2.0) or  bias ≥ 0.75        -> 0.66
  otherwise                                           -> 0.33
The fraction scales the strategy's base risk; it never exceeds 1.0 — no
anticipatory signal sizes UP past baseline until the sizing preconditions
in RETOOL_VERDICT Q4 pass on this box's own data.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── priors (env wins; config.py documents these — SPEC item G8) ─────────────
def _envf(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default

SCORE_FLOOR         = _envf("OT_ICT_SCORE_FLOOR", 0.65)
COMPLETENESS_FLOOR  = _envf("OT_ICT_COMPLETENESS_FLOOR", 0.75)
SIZE_BIAS_MIN       = _envf("OT_ICT_SIZE_BIAS_MIN", 0.50)
SIZE_BIAS_STRONG    = _envf("OT_ICT_SIZE_BIAS_STRONG", 0.75)
SIZE_BIAS_CLEAN     = _envf("OT_ICT_SIZE_BIAS_CLEAN", 0.85)
SIZE_SD_AWARE       = _envf("OT_ICT_SIZE_SD_AWARE", 1.75)
SIZE_SD_CONFIRM     = _envf("OT_ICT_SIZE_SD_CONFIRM", 2.0)
SIZE_FRAC_MARGINAL  = _envf("OT_ICT_SIZE_FRAC_MARGINAL", 0.33)
SIZE_FRAC_SOLID     = _envf("OT_ICT_SIZE_FRAC_SOLID", 0.66)

# deliberate-failure hook (WA §20-style): corrupts the score arithmetic so the
# behavioural suite can prove it goes red. Never set outside tests.
_SELFTEST = os.environ.get("OT_ICT_SELFTEST", "0") == "1"


@dataclass
class Component:
    """One scored precondition of a setup."""
    name: str
    weight: float
    value: float = 0.0        # 0..1, meaningful only when available
    available: bool = True
    required: bool = False
    floor: float = 0.5        # a REQUIRED component must also pass its floor
    reason: str = ""          # why unavailable / diagnostic note


@dataclass
class SetupScore:
    """A setup's full scored state this tick — the journal payload."""
    setup: str
    direction: str = ""       # "long" / "short" / "" (undetermined)
    components: List[Component] = field(default_factory=list)
    blocked: str = ""         # non-score block (e.g. afternoon_debit), set by dispatch

    # -- arithmetic ---------------------------------------------------------
    def score(self) -> float:
        num = sum(c.weight * c.value for c in self.components if c.available)
        den = sum(c.weight for c in self.components if c.available)
        if _SELFTEST:
            num = den  # forces a perfect score — the suite must catch this
        return round(num / den, 4) if den > 0 else 0.0

    def completeness(self) -> float:
        den = sum(c.weight for c in self.components)
        num = sum(c.weight for c in self.components if c.available)
        return round(num / den, 4) if den > 0 else 0.0

    def missing_required(self) -> List[str]:
        return [c.name for c in self.components
                if c.required and (not c.available or c.value < c.floor)]

    def phase(self) -> str:
        """DORMANT / FORMING / READY — the continuous-lifecycle read."""
        if self.blocked:
            return "BLOCKED"
        if self.fire_eligible():
            return "READY"
        s = self.score()
        if s > 0.0 and any(c.available and c.value > 0 for c in self.components):
            return "FORMING"
        return "DORMANT"

    def fire_eligible(self) -> bool:
        return (not self.blocked
                and not self.missing_required()
                and self.score() >= SCORE_FLOOR
                and self.completeness() >= COMPLETENESS_FLOOR)

    def bias_quality(self) -> float:
        """Fraction of available DIRECTIONAL weight agreeing with `direction`.

        Directional components carry names prefixed 'dir:'. With no direction
        or no directional components, quality is 0.0 — which sizes to zero,
        the honest default."""
        if not self.direction:
            return 0.0
        num = den = 0.0
        for c in self.components:
            if not c.name.startswith("dir:") or not c.available:
                continue
            den += c.weight
            num += c.weight * c.value
        return round(num / den, 4) if den > 0 else 0.0

    def journal_dict(self) -> dict:
        return {
            "setup": self.setup,
            "direction": self.direction,
            "phase": self.phase(),
            "score": self.score(),
            "completeness": self.completeness(),
            "bias_quality": self.bias_quality(),
            "missing_required": self.missing_required(),
            "blocked": self.blocked,
            "components": {c.name: {
                "w": c.weight, "v": round(c.value, 4) if c.available else None,
                "avail": c.available, "req": c.required,
                **({"reason": c.reason} if c.reason else {}),
            } for c in self.components},
        }


def size_fraction(displacement_sd: float, bias_quality: float) -> float:
    """ICT size mapping — displacement + bias ONLY (handoff §2.1). A prior."""
    if bias_quality < SIZE_BIAS_MIN or displacement_sd < SIZE_SD_AWARE:
        return 0.0
    if displacement_sd >= SIZE_SD_CONFIRM and bias_quality >= SIZE_BIAS_CLEAN:
        return 1.0
    if displacement_sd >= SIZE_SD_CONFIRM or bias_quality >= SIZE_BIAS_STRONG:
        return SIZE_FRAC_SOLID
    return SIZE_FRAC_MARGINAL


# ── journaling: once-per-change, injected sink ───────────────────────────────
# main.py owns the signal journal; dispatch passes its `journal` callable in
# (SPEC item G6). Fallback is the logger, so nothing here imports main.

_last_state: Dict[str, tuple] = {}

def journal_setup_state(sc: SetupScore,
                        journal: Optional[Callable] = None) -> bool:
    """Emit `ict_setup` when (phase, score band, direction) changed. Score is
    banded to 0.05 so a drifting float doesn't spam a row per tick — the same
    once-per-episode idiom the feed warnings use. Returns True if emitted."""
    band = round(sc.score() * 20) / 20
    key = (sc.phase(), band, sc.direction, tuple(sorted(sc.missing_required())))
    if _last_state.get(sc.setup) == key:
        return False
    _last_state[sc.setup] = key
    payload = sc.journal_dict()
    try:
        if journal is not None:
            journal("ict_setup", **payload)
        else:
            logger.info("ict_setup %s", payload)
    except Exception as e:                          # pragma: no cover
        logger.warning("ict_setup journal failed: %s", e)
    return True


def reset_journal_state() -> None:
    """Test/backtest hook — a replay must not inherit live episode state."""
    _last_state.clear()
