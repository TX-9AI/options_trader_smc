"""
tests/test_liq_named_pools.py — v1.1 — 2026-08-15
v1.1 — 2026-08-15 — A2.6: the two session-pool FLAG tests replaced by a
        BEHAVIOR test. The old ones asserted a knob the LIQ.6 ladder never
        read and stayed green while production emitted session rungs — a
        test describing a world that no longer existed.
v1.0 — 2026-08-11

Pins LIQ.1 + SWP.4 — the three defects that zeroed the SWEEP setup score on
textbook raids. All three were found by running the REAL code over a fabricated
tape carrying an engineered PDL sweep; none was visible in production logs,
because every relevant refusal path logs at DEBUG against a fleet on INFO.

WHAT EACH GUARD PROTECTS, and why each failure is SILENT:

1. **LONDON/ASIA AS SWEEPABLE POOLS.** London runs 07:00-16:00 UTC against RTH
   13:30-20:00 — a 2.5 HOUR OVERLAP — so from 09:30 to 12:00 ET "London High"
   is set by the price being traded right now. Sweeping it is sweeping a level
   RTH just made. Nothing errors; the sweep simply means nothing. It also
   explains the shadow observer's 61.3% London share: London was NEAREST
   because it TRACKED PRICE.

2. **THE DEDUPE TIEBREAK.** A PDH/PDL almost always also sits on an
   equal-high/low cluster, so one raid makes two sweeps with identical kind,
   pool_price and bars_ago. They collide on the dedupe key; `mins < cmins` is
   FALSE on equality, so the first-inserted won — and unnamed pools are found
   first. Result: `swept_named_level` EMPTY, `veto_loc` hard-veto, SWEEP SCORE
   EXACTLY 0.000 on a perfect raid. Measured 0.000 -> 1.000 with the fix.

3. **THE RECOVERY ANCHOR.** Measured from the wick extreme, a DEEPER rejection
   made the entry look FARTHER away — the gate penalised the quality it should
   reward. Anchored to the reclaimed LEVEL it reads 0.11% instead of 2.4%.

Deliberate-failure check performed when written: reverting the tiebreak to
`mins < cmins` turns test_named_sweep_survives_the_dedupe red; restoring the
wick anchor turns test_recovery_is_anchored_to_the_level red.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analysis.liquidity_mapper as LM                            # noqa: E402
from analysis.liquidity_mapper import LiquidityMapper, LiquiditySweep  # noqa: E402
import config                                                     # noqa: E402


def _sweep(named, bars_ago=2, tf="15m", pool=95.94):
    return LiquiditySweep(pool_price=pool, sweep_price=pool - 0.44,
                          kind="low_sweep", rejection_candles=2,
                          rejection_pct=0.014, confirmed=True, bar_index=1,
                          bars_ago=bars_ago, timeframe=tf,
                          swept_named_level=named)


def test_named_sweep_survives_the_dedupe():
    """THE ZEROING BUG. Unnamed first, named second, identical everything else."""
    out = LiquidityMapper._dedupe_sweeps([_sweep(""), _sweep("PDL")])
    assert len(out) == 1
    assert out[0].swept_named_level == "PDL", \
        "the NAMED twin must win a tie — losing it empties swept_named_level, " \
        "which hard-vetoes veto_loc and makes the SWEEP score exactly 0.000"


def test_a_genuinely_fresher_sweep_still_wins():
    """The fix must not make 'named' outrank RECENCY — only break ties."""
    out = LiquidityMapper._dedupe_sweeps(
        [_sweep("PDL", bars_ago=9), _sweep("", bars_ago=1)])
    assert out[0].swept_named_level == "", \
        "a materially fresher sweep must still win; the named preference is a " \
        "TIEBREAK, not an override"


def test_session_pools_are_governed_by_structure_not_a_knob():
    """A2.6 (2026-08-15) — this test used to assert NAMED_POOLS_INCLUDE_SESSIONS
    is False, and it stayed GREEN while the LIQ.6 ladder emitted session rungs
    unconditionally: the knob was dead and the test described a world that no
    longer existed. Sessions are ON by LIQ.6 doctrine (rule 1). The protection
    LIQ.1 actually needs — a still-forming section is NEVER a pool, so a level
    cannot be set by the price currently being traded — is a STRUCTURAL rule,
    executed against the real mapper in tests/test_audit2_fixes.py
    (test_a21_left_truncated_section_is_not_admitted,
    test_a25_winter_forming_rth_is_never_a_pool)."""
    assert not hasattr(LM, "NAMED_POOLS_INCLUDE_SESSIONS"), \
        "the dead knob is back — remove it or WIRE it; a switch that gates " \
        "nothing plus a green test is the renders-cleanly failure class"
    assert 'environ.get("OT_LIQ_SESSION_POOLS"' not in open(LM.__file__).read(), \
        "the env knob is being READ again — changelog mentions are history " \
        "and stay; a live read is the dead switch coming back"


def test_recovery_is_anchored_to_the_level():
    assert config.SWEEP_RECOVERY_FROM_POOL is True, \
        "anchored to the wick extreme, a DEEPER rejection reads as a FARTHER " \
        "entry — the gate then refuses the best setups it will ever see"


def test_liveness_gate_is_on_and_the_backstop_is_bounded():
    """SWP.5 — the clock is a BACKSTOP now, not the test."""
    assert config.SWEEP_LIVENESS_GATE is True, \
        "with this off the gate reverts to pure age, which discarded 32.9% of " \
        "still-live theses across 90 symbol-days"
    assert 24 <= config.SWEEP_STALE_HARD_BARS <= 96, \
        "the backstop must stay bounded — 'the level still holds' cannot be " \
        "allowed to mean 'all week'. 48 bars (4h) is a PRIOR, not a measurement"


def test_invalidation_is_a_running_check_not_a_birth_snapshot():
    """LIQ.3 — the field the gate reads must be recomputed, not frozen."""
    import analysis.liquidity_mapper as _lm
    src = open(_lm.__file__).read()
    assert "_mark_liveness" in src and "sweep_invalidated" in src, \
        "the running liveness check is what replaces the clock — `closes_beyond` " \
        "alone is a BIRTH-TIME snapshot over the 2-3 bars after the raid"
    assert "closes_beyond_live" in src, \
        "the running count must be a SEPARATE field: overwriting closes_beyond " \
        "would destroy the birth-time value veto_accept depends on"


def test_the_anchor_choice_changes_the_verdict():
    """Documents the magnitude, using the measured fabricated-raid numbers."""
    pool, wick, price, cap = 95.94, 93.80, 96.05, 0.02
    from_wick = (price - wick) / wick
    from_pool = (price - pool) / pool
    assert from_wick > cap, f"the wick anchor refuses this raid ({from_wick:.3f})"
    assert from_pool < cap, f"the level anchor admits it ({from_pool:.3f})"
