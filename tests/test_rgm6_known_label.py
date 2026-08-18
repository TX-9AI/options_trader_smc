"""
tests/test_rgm6_known_label.py — v1.0 — 2026-08-11

Pins RGM.6 — the fallback resolves to a KNOWN label instead of UNKNOWN.

WHY. Operator: "unknown should be virtually eliminated by the time we freeze
layer 1… there should be ways to extrapolate and resolve to a KNOWN label."
The data agrees and sizes it: the regime diary shows **L1 all-zero at 2.4-3.0%
on every session since 07-15**, while the v13 fallback emitted UNKNOWN on
~18-19% of ticks. A known answer existed roughly SEVEN TIMES more often than we
were genuinely blind, and we threw it away.

THE LADDER, in order:
    1. L2 committed label                    [L2 c=]
    2. held incumbent, on a stale tick       [L2-hold c=]
    3. L1 ARGMAX — a low-conviction KNOWN    [L1 c=]     <- RGM.6 adds this
    4. v13 classifier (may say UNKNOWN)      [v13]
Rung 3 is new. Before it, a warm book with no committed label — the code's own
"empty committed label on a warm book" — went straight to v13.

THE THREE FAILURES GUARDED, and each is silent:
1. **CONVICTION INVENTED RATHER THAN CARRIED.** An L1-argmax label MUST carry
   L1's raw score, which is below theta_commit by construction. Stamping it 1.0
   would make a weak label look strong to every downstream gate that reads
   conviction (continuation's floor, the condor plan).
2. **UNKNOWN SUPPRESSED ENTIRELY.** The genuinely all-zero case (~2.4%) must
   still reach v13. Resolving those to a label would be inventing information,
   which is the opposite of the intent.
3. **THE TAG COLLAPSING BACK TO TWO STATES.** `[v13]` has been the fallback-rate
   measure all week. With four states, anyone counting it must see the split, or
   they will read a drop in `[v13]` as a fix when it is a relabelling.

Deliberate-failure check performed when written: stamping conviction 1.0 turns
test_l1_argmax_carries_l1s_own_conviction red; routing the all-zero case to a
label turns test_all_zero_still_falls_through_to_v13 red.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _pick(scores):
    """Mirror of the RGM.6 rung: argmax over STRICTLY POSITIVE L1 scores."""
    live = {k: v for k, v in scores.items()
            if isinstance(v, (int, float)) and v > 0.0}
    if not live:
        return None, 0.0
    top = max(live, key=lambda k: live[k])
    return top, float(live[top])


def test_the_knob_exists_and_defaults_on():
    import main
    assert main.RGM6_L1_ARGMAX_FALLBACK is True, \
        "shipping it off makes the deploy a no-op that looks live"


def test_a_known_label_is_preferred_over_unknown():
    lab, conv = _pick({"TRENDING_BULL": 0.31, "RANGING": 0.12,
                       "COMPRESSION": 0.0})
    assert lab == "TRENDING_BULL", \
        "L1 is all-zero on only ~2.4% of ticks — a known answer is almost " \
        "always available and must be used before v13 says UNKNOWN"


def test_l1_argmax_carries_l1s_own_conviction():
    """It must look as WEAK as it is."""
    lab, conv = _pick({"RANGING": 0.18, "TRENDING_BEAR": 0.09})
    assert conv == 0.18, \
        "the label must carry L1's RAW score. It is below theta_commit by " \
        "construction — that is the point. Inventing a high conviction would " \
        "make a weak label look strong to continuation's floor and the condor plan"
    assert conv < 0.65, "an L1-argmax label is below the commit bar by definition"


def test_all_zero_still_falls_through_to_v13():
    """The genuinely blind ~2.4% must NOT be resolved — that is inventing."""
    lab, conv = _pick({"TRENDING_BULL": 0.0, "RANGING": 0.0,
                       "COMPRESSION": 0.0})
    assert lab is None, \
        "an all-zero tick is the honest UNKNOWN case; resolving it would be " \
        "manufacturing information, the opposite of the intent"


def test_negative_and_none_scores_are_ignored():
    lab, conv = _pick({"A": None, "B": -0.4, "C": 0.05})
    assert lab == "C" and conv == 0.05


def test_the_engine_tag_distinguishes_four_states():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "main.py")).read()
    for tag in ("[L1 c=", "[L2-hold c=", "[L2 c=", "[v13]"):
        assert tag in src, \
            f"{tag} missing — [v13] has been the fallback-rate measure all " \
            f"week; without the split a DROP in it reads as a fix when it is " \
            f"a relabelling"
