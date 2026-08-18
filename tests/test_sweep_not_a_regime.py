"""
tests/test_sweep_not_a_regime.py — v1.0 — 2026-08-07

Pins RGM.3: SWEEP_REVERSAL is an EVENT OVERLAY and is no longer integrated into
the regime argmax. The scorer is untouched.

WHY, in one line each:
  - `docs/MECHANICS.md:304` heads its section "SWEEP_REVERSAL (event overlay —
    hard-veto triple x age-decay)". It is the only one of the six the
    documentation does not call a regime.
  - It is the only scorer with an AGE-DECAY soft-necessary, `0.5 ** (age / 3)`,
    so its score halves every three minutes BY CONSTRUCTION and cannot win an
    argmax against states that peg at 1.0.
  - Measured 2026-08-07 over 11,231 ticks: non-zero on 22% of ticks, yet
    p90 0.0, max 0.265, dominant on 1%.

THE TWO FAILURES THESE GUARD AGAINST, and they pull in opposite directions:
  1. SWEEP creeping back into `INTEGRATED_REGIMES` — the label returns and the
     event starts winning ticks again.
  2. Someone "tidying up" `_sweep` out of regime_confluence because sweep is
     "no longer a regime" — that would silently disable SWP.1's dispatch gate,
     which reads exactly that score. The scorer is load-bearing NOW IN A NEW
     WAY, and nothing in its own file says so.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.conviction_integrator import (          # noqa: E402
    INTEGRATED_REGIMES, _TIEBREAK_ORDER, ConvictionIntegrator,
)


def test_sweep_is_not_integrated():
    assert "SWEEP_REVERSAL" not in INTEGRATED_REGIMES
    assert len(INTEGRATED_REGIMES) == 5


def test_sweep_is_not_the_tiebreak_head():
    """It WAS the head, so an all-zero tick emitted SWEEP_REVERSAL — the
    least-supported regime won precisely the ticks the engine knew nothing
    about (4.2% of them, measured)."""
    assert "SWEEP_REVERSAL" not in _TIEBREAK_ORDER
    head = min(_TIEBREAK_ORDER, key=_TIEBREAK_ORDER.get)
    assert head == "BREAKOUT_VOLATILE", f"tie-break head is now {head}"


def test_sweep_cannot_be_emitted_even_when_it_is_the_only_live_regime():
    """The behavioural assertion, not a structural one: drive the REAL
    integrator with SWEEP pegged at 1.0 and everything else at zero for 40
    ticks. Before RGM.3 this emitted SWEEP_REVERSAL at high conviction."""
    ig = ConvictionIntegrator()
    t = 1_754_481_600.0
    ev = {"SWEEP_REVERSAL": 1.0, "TRENDING_BULL": 0.0, "TRENDING_BEAR": 0.0,
          "RANGING": 0.0, "BREAKOUT_VOLATILE": 0.0, "COMPRESSION": 0.0}
    st = None
    for k in range(40):
        st = ig.update(t + k * 15, ev)
    assert "SWEEP_REVERSAL" not in ig.C, "sweep re-entered the conviction book"
    assert st.regime != "SWEEP_REVERSAL"


def test_an_extra_evidence_key_is_ignored_not_fatal():
    """Layer 1 still SCORES six regimes and hands all six over. The integrator
    must tolerate the extra key rather than KeyError — otherwise RGM.3 takes the
    engine down on the first live tick."""
    ig = ConvictionIntegrator()
    st = ig.update(1_754_481_600.0,
                   {"SWEEP_REVERSAL": 0.9, "TRENDING_BULL": 0.8,
                    "TRENDING_BEAR": 0.0, "RANGING": 0.0,
                    "BREAKOUT_VOLATILE": 0.0, "COMPRESSION": 0.0})
    assert st.regime in INTEGRATED_REGIMES


def test_the_scorer_still_exists_and_still_runs():
    """SWP.1's dispatch gate reads `scores["SWEEP_REVERSAL"]`. If someone
    removes `_sweep` because sweep "isn't a regime any more", the sweep trade
    goes dark again and NOTHING raises — the gate just never opens, which is
    exactly how it stayed shut for weeks the first time."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "analysis",
                            "regime_confluence.py")).read()
    assert "def _sweep(" in src, "the sweep SCORER was removed — SWP.1 is now dead"
    assert "SWEEP_REVERSAL" in src


def test_stale_no_longer_waits_on_sweep():
    """Side benefit worth pinning: `stale` clears only when EVERY integrated
    dimension is non-None. With sweep out, a None sweep score can no longer pin
    the book stale — the exact failure mode that made L2 unreachable before."""
    ig = ConvictionIntegrator()
    t = 1_754_481_600.0
    ev = {"SWEEP_REVERSAL": None, "TRENDING_BULL": 0.8,
          "TRENDING_BEAR": 0.1, "RANGING": 0.1,
          "BREAKOUT_VOLATILE": 0.1, "COMPRESSION": 0.1}
    # TWO ticks: the first has no `dt` to integrate over, so the book cannot
    # warm on it regardless of evidence. My first draft of this test asserted
    # on one tick and failed against CORRECT code — the same shape as the
    # canaries that matched documentation earlier today.
    ig.update(t, ev)
    st = ig.update(t + 15.0, ev)
    assert st.stale is False, "a None sweep score still pins the book stale"
