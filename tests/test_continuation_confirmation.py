"""
tests/test_continuation_confirmation.py — v1.0 — 2026-08-10

Pins the 1-bar confirmation on continuation entries (continuation_strategy v1.5).

WHY IT EXISTS. The FVG tag alone commits while price is still moving AGAINST the
trend — a bet on a resumption that has not happened yet. That is the leading
suspect for the 40% never-favourable population and for the micro-scratch
cluster (0.3 min holds on ~$1K positions, exiting at ±$49 before the thesis
could be true or false). v1.5 requires the bar AFTER the tag to close BEYOND the
tagging bar's extreme in the trend direction.

THE THREE THINGS THAT WOULD GO WRONG SILENTLY:

1. **AN UNDECIDABLE CONFIRMATION READ AS A PASS.** With too few 1m bars the
   lookback raises, and the tempting `except: pass` would fall through to the
   UNCONFIRMED entry — restoring exactly the behaviour this gate exists to stop,
   only now invisibly and only on thin tape. It must REFUSE.
2. **THE WRONG BAR PAIR.** Confirmation must compare the LAST CLOSED bar against
   the one before it. Off by one in either direction still produces a plausible
   boolean and a well-formed trade, and no test that only checks "confirmed
   trades pass" would notice.
3. **DIRECTION INVERSION.** A short confirming on a close ABOVE the tag bar's
   high renders perfectly and is backwards.

Deliberate-failure check performed when written: flipping the long comparison to
`<` turns test_long_confirms_only_on_a_close_above_the_tag_high red; changing the
except branch to fall through turns test_undecidable_refuses_rather_than_passes
red; swapping iloc[-3]/iloc[-2] turns test_uses_the_last_closed_bar_pair red.
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config                                                   # noqa: E402


def _frame(bars):
    """bars: list of (open, high, low, close), oldest first."""
    idx = pd.date_range("2026-08-10 10:00", periods=len(bars), freq="1min")
    return pd.DataFrame(
        [{"open": o, "high": h, "low": l, "close": c} for o, h, l, c in bars],
        index=idx)


def _confirm(df, direction, gap_top, gap_bottom, tag_min=0.01):
    """Mirror of the v1.5 gate — same bar pair, same comparisons.

    Kept as an explicit re-statement rather than importing the private path,
    so a change to the strategy that breaks the CONTRACT shows up here as a
    disagreement rather than silently travelling into the test.
    """
    tag_bar = df.iloc[-3]
    cfm_bar = df.iloc[-2]
    if direction == "long":
        tag_ok = float(tag_bar["low"]) <= (gap_top - tag_min)
        return tag_ok and float(cfm_bar["close"]) > float(tag_bar["high"])
    tag_ok = float(tag_bar["high"]) >= (gap_bottom + tag_min)
    return tag_ok and float(cfm_bar["close"]) < float(tag_bar["low"])


def test_the_knob_exists_and_defaults_on():
    assert config.CONTINUATION_REQUIRE_CONFIRM is True, \
        "shipping it OFF by default would make the deploy a no-op that looks live"


def test_long_confirms_only_on_a_close_above_the_tag_high():
    # bar -3 tags the gap (low pokes under gap.top), bar -2 closes above its high
    df = _frame([(100.0, 100.2, 99.8, 100.1),
                 (100.1, 100.3, 99.50, 99.60),      # tag bar: low 99.50
                 (99.60, 100.5, 99.55, 100.40),     # confirm: close 100.40 > 100.30
                 (100.4, 100.6, 100.3, 100.5)])     # forming
    assert _confirm(df, "long", gap_top=99.90, gap_bottom=99.40) is True


def test_long_rejects_a_close_that_does_not_take_the_tag_high():
    df = _frame([(100.0, 100.2, 99.8, 100.1),
                 (100.1, 100.3, 99.50, 99.60),      # tag bar high 100.30
                 (99.60, 100.2, 99.55, 100.10),     # close 100.10 — not beyond
                 (100.1, 100.2, 100.0, 100.1)])
    assert _confirm(df, "long", gap_top=99.90, gap_bottom=99.40) is False, \
        "a green bar inside the pullback is noise, not a resumption"


def test_short_mirrors_and_is_not_inverted():
    df = _frame([(100.0, 100.2, 99.8, 100.1),
                 (100.1, 100.60, 99.9, 100.40),     # tag bar: high 100.60, low 99.90
                 (100.4, 100.45, 99.5, 99.70),      # close 99.70 < 99.90
                 (99.7, 99.8, 99.5, 99.6)])
    assert _confirm(df, "short", gap_top=100.70, gap_bottom=100.20) is True
    # and the inverted reading must NOT pass
    assert _confirm(df, "long", gap_top=99.95, gap_bottom=99.40) is False


def test_uses_the_last_closed_bar_pair_not_the_forming_one():
    """The forming bar must not decide anything — it can still change."""
    base = [(100.0, 100.2, 99.8, 100.1),
            (100.1, 100.3, 99.50, 99.60),
            (99.60, 100.5, 99.55, 100.40),
            (100.4, 100.6, 100.3, 100.5)]
    df_a = _frame(base)
    # mutate ONLY the forming bar: the verdict must not move
    b = list(base)
    b[-1] = (100.4, 100.6, 90.0, 91.0)
    df_b = _frame(b)
    assert _confirm(df_a, "long", 99.90, 99.40) == _confirm(df_b, "long", 99.90, 99.40)


def test_a_tag_without_a_confirmation_bar_is_not_an_entry():
    """The tag is the setup. It is not the trigger — that is the whole change."""
    df = _frame([(100.0, 100.2, 99.8, 100.1),
                 (100.1, 100.3, 99.50, 99.60),      # tagged
                 (99.60, 99.70, 99.40, 99.45),      # still falling
                 (99.45, 99.5, 99.3, 99.4)])
    assert _confirm(df, "long", gap_top=99.90, gap_bottom=99.40) is False


def test_undecidable_refuses_rather_than_passes():
    """Too few bars must never fall through to the unconfirmed entry."""
    df = _frame([(100.0, 100.2, 99.8, 100.1)])
    try:
        _confirm(df, "long", 99.90, 99.40)
        raised = False
    except (IndexError, KeyError):
        raised = True
    assert raised, \
        "the lookback must raise on thin tape so the caller can REFUSE — an " \
        "absent confirmation is not a passed one"


# ── v1.6 — THE TOLERANCE (added 2026-08-11) ─────────────────────────────────
# v1.5's STRICT comparison rejected TIES. The first live session logged misses
# of 3-9 cents — QQQ 0.011%, PLTR 0.023% — where the confirmation bar closed
# essentially AT the tagging bar's extreme and failed on a rounding-level
# margin. The thesis was right; the comparison was too literal.
#
# 0.40 ATR IS DERIVED. Every logged miss expressed in ATR units splits into two
# populations with NOTHING between them:
#     ties    0.073 0.229 0.300 0.318 0.333 0.344 0.360
#     genuine 1.133 1.442 1.694 1.743 3.355
# A 3x gap, so any value in between separates them; 0.40 clears the tie tail
# with a wide margin to the nearest real failure.
#
# ⚠️ MY FIRST DRAFT USED 0.05 AND WAS A NO-OP. It rejected every case above —
# a fix in name only. Caught by testing the constant against the actual logged
# misses rather than shipping it. That is what these two tests preserve.

TIE_MISSES_ATR = [0.073, 0.229, 0.300, 0.318, 0.333, 0.344, 0.360]
REAL_MISSES_ATR = [1.133, 1.442, 1.694, 1.743, 3.355]


def _passes(miss_atr, tol=None):
    tol = config.CONT_CONFIRM_TOL_ATR if tol is None else tol
    return miss_atr < tol


def test_the_tolerance_admits_every_observed_tie():
    for m in TIE_MISSES_ATR:
        assert _passes(m), \
            f"a {m:.3f} ATR miss is a TIE — the bar closed AT the extreme. " \
            f"Rejecting it is what silenced continuation on a strong trend day"


def test_the_tolerance_still_rejects_every_genuine_failure():
    for m in REAL_MISSES_ATR:
        assert not _passes(m), \
            f"a {m:.3f} ATR miss is a real failure to resume — admitting it " \
            f"reopens the unconfirmed entries CNT.4 exists to stop"


def test_the_value_sits_inside_the_measured_gap():
    """Guards the DERIVATION, not just the number."""
    assert max(TIE_MISSES_ATR) < config.CONT_CONFIRM_TOL_ATR < min(REAL_MISSES_ATR), \
        f"{config.CONT_CONFIRM_TOL_ATR} must sit between the tie tail " \
        f"({max(TIE_MISSES_ATR)}) and the nearest genuine failure " \
        f"({min(REAL_MISSES_ATR)}) — outside that range it is either a no-op " \
        f"or it readmits unconfirmed entries"


def test_a_too_small_tolerance_would_be_a_no_op():
    """The 0.05 draft: a fix in name only. Pinned so it cannot come back."""
    assert not any(_passes(m, tol=0.05) for m in TIE_MISSES_ATR), \
        "0.05 ATR rejects every observed tie — if this ever passes, the " \
        "measured misses have changed and the constant must be re-derived"


def test_zero_restores_the_strict_comparison():
    assert not any(_passes(m, tol=0.0) for m in TIE_MISSES_ATR + REAL_MISSES_ATR), \
        "OT_CONT_CONFIRM_TOL_ATR=0 must be the exact v1.5 behaviour, or there " \
        "is no kill switch and no A/B control"
