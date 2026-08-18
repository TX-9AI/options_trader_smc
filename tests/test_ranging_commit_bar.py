"""
tests/test_ranging_commit_bar.py — v1.0 — 2026-08-10

Pins RGM.4: the per-regime commit bar (conviction_integrator v2.3).

WHY. `theta_commit` was ONE number applied to scores on DIFFERENT SCALES.
Measured over 209,061 ticks: L1 sees a range on 24.2% of ticks — the same share
as TRENDING_BULL's 23.5% — and L2 emits RANGING on 2%. 83.2% of the failed
RANGING runs failed on the CEILING: peak EVIDENCE never reached 0.65 either, and
conviction asymptotes to its evidence, so no tau change could reach it.
RANGING evidence p90 0.779 / max 0.982 — it never pegs. TRENDING p90 1.000.

0.60 IS DERIVED. tau_up 780 was fitted so commits land at ~17-19 bars: past the
12-15 bar window where TRENDS hold a false-flat angle, inside the 24-29 bar
window where true ranges do. At RANGING's p90 evidence, theta 0.65 commits at
23.4 bars (LATE, outside the design), 0.60 at 19.1 (the designed window), 0.50
at 13.3 (INSIDE the impostor window — rejected). So this RESTORES the timing the
tau was fitted to produce; it is not a loosening.

THE THREE FAILURES GUARDED, all silent:
  1. A REGRESSION TO THE GLOBAL BAR. If the override map is emptied or the
     lookup reverts to `p.theta_commit`, RANGING simply goes quiet again — no
     error, and it reads as "no ranges today".
  2. THE ARMING SITE. `armed` must also use the challenger's own bar. Using the
     global there keeps the book unarmed through exactly the ranging sessions
     this change exists to admit.
  3. DRIFT PAST THE IMPOSTOR WINDOW. Any value at or below ~0.55 puts commits
     inside the 12-15 bar false-flat zone, which is what tau_up 780 exists to
     exclude. The bar may move; it may not move THAT far.

Deliberate-failure check performed when written: emptying
theta_commit_by_regime turns test_ranging_has_its_own_bar red; setting it to
0.50 turns test_the_bar_stays_out_of_the_impostor_window red.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.conviction_integrator import IntegratorParams          # noqa: E402
from analysis.regime_classifier import Regime                        # noqa: E402

RANGING_P90_EVIDENCE = 0.779      # measured, 209,061 ticks
TAU_UP_RANGING = 780.0
IMPOSTOR_TOP_BARS = 15.0          # trends hold a false flat 12-15 bars


def _commit_bars(theta, evidence=RANGING_P90_EVIDENCE, tau=TAU_UP_RANGING):
    """Bars of sustained evidence before conviction reaches `theta`."""
    r = theta / evidence
    if r >= 1.0:
        return float("inf")
    return (-tau * math.log(1.0 - r)) / 60.0


def test_ranging_has_its_own_bar():
    p = IntegratorParams()
    assert p.commit_bar(Regime.RANGING) < p.theta_commit, \
        "RANGING must carry a LOWER bar — its evidence never pegs, so the " \
        "global 0.65 is unreachable and the regime goes dark"


def test_every_other_regime_keeps_the_global_bar():
    p = IntegratorParams()
    for r in (Regime.TRENDING_BULL, Regime.TRENDING_BEAR,
              Regime.BREAKOUT_VOLATILE, Regime.COMPRESSION):
        assert p.commit_bar(r) == p.theta_commit, \
            f"{r} was not measured as blocked — changing its bar is unevidenced"


def test_an_unknown_or_missing_regime_falls_back():
    p = IntegratorParams()
    assert p.commit_bar(None) == p.theta_commit
    assert p.commit_bar("NOT_A_REGIME") == p.theta_commit


def test_the_bar_stays_out_of_the_impostor_window():
    """THE GUARD THAT MATTERS. tau_up 780 exists to exclude false flats."""
    p = IntegratorParams()
    bars = _commit_bars(p.commit_bar(Regime.RANGING))
    assert bars > IMPOSTOR_TOP_BARS, \
        f"at p90 evidence this bar commits in {bars:.1f} bars — inside the " \
        f"12-15 bar window where TRENDS hold a false flat. The whole point of " \
        f"tau_up 780 is to sit past it; a lower theta gives that away silently"


def test_the_bar_restores_the_designed_timing():
    """17-19 bars is what the tau was fitted to produce."""
    p = IntegratorParams()
    bars = _commit_bars(p.commit_bar(Regime.RANGING))
    assert 16.0 <= bars <= 20.0, \
        f"commits at {bars:.1f} bars; the integrator's own comment fits tau_up " \
        f"to ~17-19. This change RESTORES that timing, it does not loosen it"


def test_the_old_global_bar_committed_too_late():
    """Documents WHY this changed: 0.65 had drifted outside the design."""
    assert _commit_bars(0.65) > 20.0, \
        "if 0.65 lands inside the designed window the premise is wrong"


def test_the_knob_can_restore_the_old_behaviour():
    os.environ["OT_L2_THETA_COMMIT_RANGING"] = "0.65"
    try:
        p = IntegratorParams()
        assert p.commit_bar(Regime.RANGING) == 0.65
    finally:
        del os.environ["OT_L2_THETA_COMMIT_RANGING"]
