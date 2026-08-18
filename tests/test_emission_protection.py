"""
tests/test_emission_protection.py — v1.0 — 2026-08-06

Pins conviction_integrator v2.1's emission law (RGM.1 / F7). The defect these
guard against is subtle and was invisible for weeks: a gate that never opens
raises nothing, logs nothing, and breaks no test. Each assertion below fails if
the unprotected branch comes back.

Measured motivation: 96.9% of 8,345 label switches over 19 sessions came from
the below-theta_hold branch, at a median incumbent conviction of 0.08.
"""

import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _fresh(protect: bool):
    """Reimport the module so the env-read default is re-evaluated."""
    os.environ["OT_L2_PROTECT_BELOW_HOLD"] = "1" if protect else "0"
    import analysis.conviction_integrator as ci
    importlib.reload(ci)
    return ci


def _drive(integ, vectors, t0=1_754_481_600.0, step=60.0):
    st = None
    for i, ev in enumerate(vectors):
        st = integ.update(t0 + i * step, ev)
    return st


def _vec(**kw):
    base = {"SWEEP_REVERSAL": 0.0, "BREAKOUT_VOLATILE": 0.0, "COMPRESSION": 0.0,
            "TRENDING_BULL": 0.0, "TRENDING_BEAR": 0.0, "RANGING": 0.0}
    base.update(kw)
    return base


def test_flag_defaults_on_and_env_can_restore_v2_0():
    assert _fresh(True).IntegratorParams().protect_below_hold is True
    assert _fresh(False).IntegratorParams().protect_below_hold is False


def test_weak_challenger_cannot_take_the_label_below_hold():
    """THE DEFECT ITSELF. Commit TRENDING_BULL, let it fade under theta_hold,
    then offer a 0.05 challenger. v2.0 handed the label over; v2.1 must not."""
    ci = _fresh(True)
    integ = ci.ConvictionIntegrator()
    st = _drive(integ, [_vec(TRENDING_BULL=0.95)] * 15)
    assert st.regime == "TRENDING_BULL" and st.armed
    # starve the incumbent below theta_hold, with a weak challenger leading
    st = _drive(integ, [_vec(COMPRESSION=0.05)] * 40,
                t0=1_754_481_600.0 + 15 * 60)
    assert st.conviction < ci.IntegratorParams().theta_hold, "setup: must fade"
    assert st.regime == "TRENDING_BULL", (
        f"label handed to a sub-commit challenger: {st.regime} — the "
        f"unprotected branch is back")


def test_v2_0_control_does_hand_it_over():
    """The same stream under the old law MUST flip — otherwise the test above
    is passing for a reason unrelated to the fix."""
    ci = _fresh(False)
    integ = ci.ConvictionIntegrator()
    _drive(integ, [_vec(TRENDING_BULL=0.95)] * 15)
    st = _drive(integ, [_vec(COMPRESSION=0.05)] * 40,
                t0=1_754_481_600.0 + 15 * 60)
    assert st.regime != "TRENDING_BULL"


def test_committed_challenger_still_displaces():
    """Slow to abandon is not never to abandon: a real regime change must land."""
    ci = _fresh(True)
    integ = ci.ConvictionIntegrator()
    _drive(integ, [_vec(TRENDING_BULL=0.95)] * 15)
    st = _drive(integ, [_vec(BREAKOUT_VOLATILE=0.98)] * 30,
                t0=1_754_481_600.0 + 15 * 60)
    assert st.regime == "BREAKOUT_VOLATILE"


def test_cold_book_is_not_pinned_to_the_tiebreak_head():
    """Protection must ARM. SWEEP_REVERSAL is the deterministic tiebreak head
    and scores above zero on 4% of ticks — pinning a session to it would be a
    worse failure than the churn."""
    ci = _fresh(True)
    integ = ci.ConvictionIntegrator()
    st = _drive(integ, [_vec()] * 3)
    assert st.armed is False
    st = _drive(integ, [_vec(RANGING=0.30)] * 10, t0=1_754_481_600.0 + 3 * 60)
    assert st.armed is False, "nothing reached theta_commit; must stay unarmed"
    assert st.regime == "RANGING", "unarmed book must still follow argmax"


def test_shadow_tracks_the_other_law_and_counts_diverge():
    """The live A/B: both laws run every tick off the same conviction vector."""
    ci = _fresh(True)
    integ = ci.ConvictionIntegrator()
    _drive(integ, [_vec(TRENDING_BULL=0.95)] * 15)
    st = _drive(integ, [_vec(COMPRESSION=0.05)] * 40,
                t0=1_754_481_600.0 + 15 * 60)
    assert st.regime == "TRENDING_BULL"
    assert st.shadow_regime == "COMPRESSION", "shadow must model the OLD law"
    assert st.shadow_switches > st.switches


def test_integration_law_and_snapshot_are_untouched():
    """v2.1 changes WHICH BRANCH the displacement test runs in — nothing else.
    A conviction drift here means the fix leaked into the integrator."""
    a = _fresh(True).ConvictionIntegrator()
    b = _fresh(False).ConvictionIntegrator()
    vec = [_vec(TRENDING_BULL=0.8, RANGING=0.3)] * 12
    sa, sb = _drive(a, vec), _drive(b, vec)
    for r in sa.convictions:
        assert abs(sa.convictions[r] - sb.convictions[r]) < 1e-12, r
