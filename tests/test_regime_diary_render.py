"""
tests/test_regime_diary_render.py — v1.1 — 2026-08-04 (regime_diary v1.4)

Every fixture below reproduces a REAL row from the 16-session diary, so a
regression fails against the tape we actually have rather than a made-up shape.

The load-bearing test is the first one: TRENDING_BULL and TRENDING_BEAR rendered
as the same four characters ("TREN") in every diary line since v1.0, in both the
dominance row and the L2 row. That is not cosmetic — bull-vs-bear asymmetry is an
open question in this workstream and the report could not express it.

v1.1 — 2026-08-04 — labels are BULL / BEAR (operator's call) and the map moved
to utils/regime_labels.py, shared with replay_confluence and regime_confluence
after both were found to carry the identical truncation defect.

Deliberate-failure check performed when written: restoring
`k.split('_')[0][:4]` turns the first two tests red; dropping acceptance_detail
from the header turns test_acceptance_names_the_failing_check red.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.regime_diary import _md_block, _lab, LABEL   # noqa: E402
from utils.regime_labels import REGIME_LABELS, label   # noqa: E402


def _entry(**over):
    """2026-07-29 as the diary actually recorded it: TREN 17% / TREN 36%."""
    e = {
        "date": "2026-07-29",
        "tag": "DIRECTIONAL",
        "ticks": 11295,
        "n_symbols": 29,
        "symbols": ["AAPL", "AMD", "AMZN"],
        "dominance": {
            "TRENDING_BULL": 17.0, "TRENDING_BEAR": 36.0, "RANGING": 21.0,
            "BREAKOUT_VOLATILE": 16.0, "COMPRESSION": 5.0,
            "SWEEP_REVERSAL": 3.0,
        },
        "nonzero": {}, "all_zero_pct": 2.1,
        "flat_angle_p50": 14.1, "flat_angle_p90": 29.6,
        "acceptance": "4/5",
        "acceptance_detail": {"A1": True, "A2": False, "A3": True,
                              "A4": True, "A5": True},
        "l2": {"dominance": {"TRENDING_BULL": 37.0, "BREAKOUT_VOLATILE": 20.0,
                             "TRENDING_BEAR": 19.0, "RANGING": 18.0,
                             "COMPRESSION": 5.0, "SWEEP_REVERSAL": 1.0},
               "switches": 497, "l1_flips": 834, "stale_pct": 6.3},
    }
    e.update(over)
    return e


# ── the defect ──────────────────────────────────────────────────────────────
def test_bull_and_bear_are_distinguishable_in_the_dominance_row():
    block = _md_block(_entry())
    dom = [l for l in block.splitlines() if l.startswith("- dominance:")][0]
    assert "BULL 17%" in dom and "BEAR 36%" in dom, dom
    assert "TREN" not in dom, "bull and bear still collapse to one token"


def test_bull_and_bear_are_distinguishable_in_the_l2_row():
    """The L2 row had the same bug and is the row the freeze watch reads."""
    l2 = [l for l in _md_block(_entry()).splitlines() if l.startswith("- L2:")][0]
    assert "BULL 37%" in l2 and "BEAR 19%" in l2, l2
    assert "TREN" not in l2


def test_every_regime_has_a_unique_label():
    assert len(set(REGIME_LABELS.values())) == len(REGIME_LABELS)
    assert all(len(v) == 4 for v in REGIME_LABELS.values()), \
        "columns must stay aligned"


def test_the_diary_uses_the_shared_map_not_a_local_copy():
    """Three renderers had this defect independently. One map, or the next one
    invents a fourth abbreviation."""
    assert LABEL is REGIME_LABELS and _lab is label


def test_the_two_directional_labels_are_the_operators_words():
    assert REGIME_LABELS["TRENDING_BULL"] == "BULL"
    assert REGIME_LABELS["TRENDING_BEAR"] == "BEAR"


def test_unknown_keys_still_render_rather_than_raising():
    """A future regime must degrade to the old abbreviation, not KeyError a
    nightly report."""
    assert _lab("SOME_NEW_REGIME") == "SOME"


# ── acceptance, which had never varied in 16 sessions ───────────────────────
def test_acceptance_names_the_failing_check():
    head = _md_block(_entry()).splitlines()[0]
    assert "acceptance 4/5 (A2)" in head, head


def test_a_clean_day_names_nothing():
    e = _entry(acceptance="5/5",
               acceptance_detail={k: True for k in ("A1", "A2", "A3", "A4", "A5")})
    head = _md_block(e).splitlines()[0]
    assert "acceptance 5/5" in head and "(" not in head.split("acceptance")[1]


def test_two_failures_are_both_named():
    e = _entry(acceptance="3/5",
               acceptance_detail={"A1": True, "A2": False, "A3": True,
                                  "A4": False, "A5": True})
    assert "acceptance 3/5 (A2, A4)" in _md_block(e).splitlines()[0]


def test_old_rows_without_detail_do_not_break():
    e = _entry()
    e.pop("acceptance_detail")
    assert "acceptance 4/5" in _md_block(e).splitlines()[0]


# ── the churn ratio and the corpus-size tell ────────────────────────────────
def test_churn_cut_is_shown_and_points_the_right_way():
    """834 L1 flips / 497 committed switches = 1.68x churn REMOVED.

    The direction matters more than the digits: written the other way round it
    reads 0.60 and silently inverts "churn crushed 1.6x", the sentence this repo
    has used since the integrator shipped. Caught by this test failing on the
    first run with the ratio the wrong way up.
    """
    l2 = [l for l in _md_block(_entry()).splitlines() if l.startswith("- L2:")][0]
    assert "churn-cut 1.68x" in l2, l2


def test_churn_cut_is_omitted_rather_than_dividing_by_zero():
    e = _entry()
    e["l2"] = dict(e["l2"], switches=0)
    l2 = [l for l in _md_block(e).splitlines() if l.startswith("- L2:")][0]
    assert "churn-cut" not in l2


def test_ticks_per_symbol_exposes_a_degraded_corpus():
    """2026-08-03 as recorded: 15 symbols, 3645 ticks — 243/sym against a normal
    ~389. Both axes degraded, and the row said neither."""
    e = _entry(date="2026-08-03", n_symbols=15, ticks=3645)
    line = [l for l in _md_block(e).splitlines() if "symbols ·" in l][0]
    assert "15 symbols · 3645 ticks (243/sym)" in line, line
    full = [l for l in _md_block(_entry()).splitlines() if "symbols ·" in l][0]
    assert "(389/sym)" in full, full
