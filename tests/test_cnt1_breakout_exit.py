#!/usr/bin/env python3
"""
tests/test_cnt1_breakout_exit.py — v1.0 — 2026-08-14

CNT.1 SHIPPED HALF A FEATURE ON 2026-08-07 AND NOBODY NOTICED FOR A WEEK.

`continuation_strategy` (CNT.1) lets continuation OPEN on BREAKOUT_VOLATILE,
taking direction from the trend vote instead of the label and gating on ADX. It
tags those `trend_continuation_breakout`.

`exit_engine._evaluate_continuation`'s `still_trending` only ever accepted
TRENDING_BULL / TRENDING_BEAR.

**So a breakout continuation was BORN ALREADY FAILING ITS OWN EXIT TEST.** It
opens on tick N with the label at BREAKOUT_VOLATILE; on tick N+1 the exit reads
the SAME UNCHANGED LABEL, finds it is not TRENDING_*, and closes as
`regime_flip`. THE LABEL NEVER FLIPPED — the exit reason was a lie.

MEASURED LIVE 2026-08-14, and the timestamps are the proof:
    SMH  14:24:19 -> 14:24:34   (15s = exactly one tick)
         14:24:49 -> 14:25:04
         14:25:19 -> 14:25:34   ... eight in a row
P&L was symmetric noise (SMH's eight netted -$29, GS's eight +$331) because a
one-tick hold is one tick of random walk minus the spread. **The repetition was
a side effect; each trade was incoherent on its own.**

⚠️ THE DIAGNOSTIC TRAP THIS ALSO RECORDS: the obvious reading of eight identical
15-second trades is "churn — add a cooldown." A cooldown would have hidden the
loop and fixed nothing, which is WORSE than leaving it alone, because the
symptom is what exposed the defect. The operator caught that:
*"It's not a re-entry or cooldown problem... If they were profitable it wouldn't
be a problem."*

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python -m pytest tests/test_cnt1_breakout_exit.py -q
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SRC = open(os.path.join(os.path.dirname(__file__), "..", "execution",
                        "exit_engine.py"), encoding="utf-8").read()


def still_trending(setup_type, direction, regime, vote=None):
    """Mirrors the engine's test. Kept honest by
    `test_mirror_matches_the_engine_source` below."""
    rgm = (regime or "").upper()
    # F7: setup_type no longer decides; the TREND VOTE does. Default the vote to
    # the trade's own direction so the original CNT.1 cases read unchanged.
    # ⚠️ ONLY `None` (vote not supplied by an older test) defaults. An EMPTY or
    # NEUTRAL vote must stay empty and FAIL CLOSED, matching the engine:
    # `str(getattr(trend, "overall_direction", "") or "").upper()` yields "",
    # which agrees with no direction. Defaulting "" here made the mirror MORE
    # PERMISSIVE than the code it mirrors - caught by the fail-closed test.
    v = (vote if vote is not None
         else ("BULLISH" if direction == "long" else "BEARISH")).upper()
    agrees = ((direction == "long" and v == "BULLISH")
              or (direction == "short" and v == "BEARISH"))
    return (
        (direction == "long" and "TRENDING_BULL" in rgm) or
        (direction == "short" and "TRENDING_BEAR" in rgm) or
        ("BREAKOUT_VOLATILE" in rgm and agrees)
    )


# ── the defect ─────────────────────────────────────────────────────────────

def test_a_breakout_continuation_survives_its_own_entry_label():
    """THE ONE THAT MATTERS. A trade opened on BREAKOUT_VOLATILE must not be
    closed by BREAKOUT_VOLATILE on the next tick."""
    for direction in ("long", "short"):
        assert still_trending("trend_continuation_breakout", direction,
                              "BREAKOUT_VOLATILE"), (
            f"a {direction} breakout continuation still exits on the label it "
            f"was OPENED on — it is born failing its own exit test")


def test_a_genuine_flip_still_exits_a_breakout_continuation():
    """The fix must not make breakout trades unkillable. Any label that is
    neither its own nor its direction's still closes it."""
    for regime in ("RANGING", "COMPRESSION", "CHOP"):
        assert not still_trending("trend_continuation_breakout", "short", regime)


def test_the_exemption_is_now_symmetric_across_setup_types():
    """⚠️ REWRITTEN BY AUDIT F7. This used to assert that ONLY `_breakout`
    gained the exemption — which was the defect, not the contract. A standalone
    accelerating into a breakout IN ITS OWN DIRECTION was being closed while a
    breakout record survived the identical tape.

    The contract now: **setup_type is irrelevant; the trend vote decides.**"""
    for setup in ("trend_continuation_standalone", "trend_continuation_handoff",
                  "trend_continuation_breakout"):
        assert still_trending(setup, "long", "BREAKOUT_VOLATILE", "BULLISH")
        assert not still_trending(setup, "long", "BREAKOUT_VOLATILE", "BEARISH")


def test_ordinary_continuation_behaviour_is_unchanged():
    assert still_trending("trend_continuation_standalone", "long", "TRENDING_BULL")
    assert still_trending("trend_continuation_handoff", "short", "TRENDING_BEAR")
    assert not still_trending("trend_continuation_standalone", "long", "TRENDING_BEAR")


def test_a_missing_trend_vote_fails_CLOSED():
    """⚠️ REWRITTEN BY AUDIT F7. The old version guarded against a missing
    setup_type; setup_type no longer gates anything. The field that matters now
    is the TREND VOTE, and its absence must NOT hold a position open —
    `getattr(trend, "overall_direction", "")` is "" when the vote is
    unavailable, which cannot agree with any direction, so the trade exits.
    A missing input is never evidence the thesis survives."""
    assert not still_trending("trend_continuation_standalone", "long",
                              "BREAKOUT_VOLATILE", "")
    assert not still_trending("trend_continuation_breakout", "short",
                              "BREAKOUT_VOLATILE", "NEUTRAL")


# ── the mirror is only evidence if the engine still matches it ─────────────

def test_mirror_matches_the_engine_source():
    """⚠️ SUPERSEDED BY AUDIT F7 (v4.22). This asserted the v4.19 clause
    `(_is_breakout_cont and "BREAKOUT_VOLATILE" in rgm)` — the exemption scoped
    to setup_type. That scoping WAS the F7 defect: a standalone accelerating
    into its own breakout got closed while a breakout record survived the same
    tape, and a long survived a breakout going AGAINST it because the label
    carries no direction. The exemption is now gated on the TREND VOTE and
    setup_type is irrelevant here — see `test_f7_setup_type_no_longer_decides`.

    The CNT.1 behaviour this file was written for is unchanged: a breakout
    continuation still survives BREAKOUT_VOLATILE. Only the reason changed,
    from "because of its setup_type" to "because the vote still agrees"."""
    assert '"BREAKOUT_VOLATILE" in rgm and _vote_agrees' in SRC
    assert '_is_breakout_cont' not in SRC, \
        "setup_type is back in the exemption; F7 has regressed"


def test_the_flip_check_still_precedes_bos_exit():
    """Ordering is load-bearing: the flip block runs BEFORE bos_exit, which is
    why nothing else ever got a look at these trades. If that order changes,
    the reasoning in the changelog stops being true."""
    i_flip = SRC.index("still_trending = (")
    i_bos = SRC.index('exit_reason = f"bos_exit pnl=', i_flip)
    assert i_flip < i_bos


# ── deliberate failure ─────────────────────────────────────────────────────

def test_deliberate_failure_the_exemption_is_load_bearing():
    """Without the breakout clause the live case MUST fail. Proves the new
    term is doing the work rather than the test passing for another reason."""
    def without(setup_type, direction, regime):
        rgm = (regime or "").upper()
        return ((direction == "long" and "TRENDING_BULL" in rgm) or
                (direction == "short" and "TRENDING_BEAR" in rgm))
    assert not without("trend_continuation_breakout", "short", "BREAKOUT_VOLATILE")
    assert still_trending("trend_continuation_breakout", "short", "BREAKOUT_VOLATILE")


def test_deliberate_failure_a_cooldown_would_not_have_fixed_this():
    """RECORDED AS A METHOD LESSON, not as executable coverage. Eight identical
    15-second trades read as churn; the obvious fix is a cooldown. But the
    trades were incoherent INDIVIDUALLY — a cooldown would have spaced out
    incoherent trades and hidden the evidence that exposed the defect.
    The symptom is not the bug."""
    entries = ["14:24:19", "14:24:49", "14:25:19", "14:25:49"]
    holds_sec = [15, 15, 15, 15]
    assert len(set(holds_sec)) == 1 and holds_sec[0] == 15, (
        "a hold time equal to the TICK INTERVAL, identical every time, is a "
        "structural exit firing immediately — not a market outcome")
    assert len(entries) == 4


# ── AUDIT F7 — the exemption was asymmetric, and direction-blind ────────────

def _still_trending(direction, rgm, vote):
    """Mirrors v4.22. Kept honest by `test_f7_mirror_matches_source`."""
    va = ((direction == "long" and vote == "BULLISH")
          or (direction == "short" and vote == "BEARISH"))
    return ((direction == "long" and "TRENDING_BULL" in rgm)
            or (direction == "short" and "TRENDING_BEAR" in rgm)
            or ("BREAKOUT_VOLATILE" in rgm and va))


def test_f7_a_standalone_survives_acceleration_into_a_breakout():
    """THE ASYMMETRY. v4.19 scoped the exemption to `_breakout` records, so a
    STANDALONE riding TRENDING_BULL that accelerated into BREAKOUT_VOLATILE —
    the strongest tape in its own direction — was closed as a regime_flip while
    a breakout record survived the IDENTICAL TAPE. Same market, opposite
    decision, on setup_type alone."""
    assert _still_trending("long", "BREAKOUT_VOLATILE", "BULLISH") is True
    assert _still_trending("short", "BREAKOUT_VOLATILE", "BEARISH") is True


def test_f7_a_breakout_AGAINST_the_trade_now_exits():
    """⚠️ THE OTHER HALF, AND THE MORE DANGEROUS ONE. BREAKOUT_VOLATILE carries
    NO DIRECTION, so the old label-only test let a LONG survive a violent move
    DOWN as long as the record was `_breakout`. The trend vote decides now."""
    assert _still_trending("long", "BREAKOUT_VOLATILE", "BEARISH") is False
    assert _still_trending("short", "BREAKOUT_VOLATILE", "BULLISH") is False


def test_f7_ordinary_behaviour_is_untouched():
    assert _still_trending("long", "TRENDING_BULL", "BULLISH") is True
    assert _still_trending("long", "TRENDING_BEAR", "BEARISH") is False
    assert _still_trending("long", "RANGING", "BULLISH") is False
    assert _still_trending("short", "COMPRESSION", "BEARISH") is False


def test_f7_setup_type_no_longer_decides():
    """The fix is that setup_type is IRRELEVANT here. Two records on the same
    tape with the same direction must get the same answer."""
    import ast
    tree = ast.parse(SRC)
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and any(
                getattr(t, "id", "") == "still_trending" for t in n.targets):
            seg = ast.get_source_segment(SRC, n) or ""
            assert "_is_breakout_cont" not in seg, \
                "setup_type still gates the breakout exemption"
            return
    raise AssertionError("still_trending is gone from exit_engine")


def test_f7_mirror_matches_source():
    assert '_vote_agrees = ((direction == "long" and _vote == "BULLISH")' in SRC
    assert '("BREAKOUT_VOLATILE" in rgm and _vote_agrees)' in SRC


def test_f7_deliberate_failure_the_old_logic_would_fail_these():
    """Prove the change is load-bearing against the v4.19 predicate."""
    def old(direction, rgm, is_breakout):
        return ((direction == "long" and "TRENDING_BULL" in rgm)
                or (direction == "short" and "TRENDING_BEAR" in rgm)
                or (is_breakout and "BREAKOUT_VOLATILE" in rgm))
    # standalone accelerating into its own breakout: old CLOSED it
    assert old("long", "BREAKOUT_VOLATILE", False) is False
    assert _still_trending("long", "BREAKOUT_VOLATILE", "BULLISH") is True
    # breakout AGAINST a long: old HELD it
    assert old("long", "BREAKOUT_VOLATILE", True) is True
    assert _still_trending("long", "BREAKOUT_VOLATILE", "BEARISH") is False
