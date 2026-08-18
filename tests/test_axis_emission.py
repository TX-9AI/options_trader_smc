#!/usr/bin/env python3
"""
tests/test_axis_emission.py — v1.0 — 2026-08-17   (P0.3 / AX.3)

THE MEASURED SEPARATOR IS NOW RECORDED. IT STILL GATES NOTHING.

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python -m pytest tests/test_axis_emission.py -q

`regime_ctx` stamped every journalled event with ONLY the INTEGRATED label and
conviction — and both are measured dead as entry-side quantities:
`RGCV.nf` **1.00** vs `.ok` **0.34** in RANGING (an ANTI-signal), 1.00 vs 1.00
in trend.

The RAW Layer-1 direction axis DOES separate: **nf 0.628 → ok 0.885, gap
+0.257, n=753 across 17 sessions** (P0.1, 2026-08-17) — up from AX.2's +0.188
on n=571. **It grew on more data, which is what a real effect does.**

⚠️ AND IT WAS JOURNALED NOWHERE. `regime_axes.decompose()` is a pure function
that `main.py` never called. A measured separator that drives nothing and is not
even recorded **cannot be confirmed forward**. That was AX.3's unbuilt half,
open since 2026-08-07.

⚠️ LOG-ONLY. Gates nothing, sizes nothing, changes no trading behaviour. **The
fleet must keep trading and collecting through the retool** — this emits and
gets out of the way.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SCORES = {"TRENDING_BULL": 0.90, "TRENDING_BEAR": 0.00, "RANGING": 0.30,
          "BREAKOUT_VOLATILE": 0.20, "COMPRESSION": 0.00, "SWEEP_REVERSAL": 0.0}


class _R:
    primary_regime = "TRENDING_BULL"
    conviction = 0.81


def test_the_axes_are_emitted_when_scores_are_present():
    from analysis.signal_journal import regime_ctx
    out = regime_ctx(_R(), SCORES)
    assert out["direction_conf"] == 0.90
    assert out["direction"] == "BULL"
    assert "volatility_conf" in out


def test_the_raw_axis_is_NOT_the_integrated_conviction():
    """The whole point. If these were the same number there would be nothing to
    emit — and `regime_axes.py`'s own header says the raw score separates where
    the integrated one does not."""
    from analysis.signal_journal import regime_ctx
    out = regime_ctx(_R(), SCORES)
    assert out["conviction"] == 0.81
    assert out["direction_conf"] == 0.90
    assert out["direction_conf"] != out["conviction"]


def test_pair_conf_is_NOT_emitted():
    """⚠️ MEASURED DEAD (+0.001 vs direction_conf's +0.188) and the failure is
    STRUCTURAL, not tunable: `min()` over a sparse axis collapses to zero.
    Emitting it would invite exactly the re-litigation its own note forbids."""
    from analysis.signal_journal import regime_ctx
    out = regime_ctx(_R(), SCORES)
    assert "pair_conf" not in out


def test_backward_compatible_without_scores():
    """Seven call sites; a caller that cannot supply scores must still journal."""
    from analysis.signal_journal import regime_ctx
    out = regime_ctx(_R())
    assert out == {"label": "TRENDING_BULL", "conviction": 0.81}


def test_a_broken_decomposition_never_breaks_a_journal_write():
    """⚠️ TELEMETRY MUST NOT BE ABLE TO KILL A WRITE. The event still carries
    label+conviction; the axes are simply ABSENT — and absent is
    distinguishable from zero downstream, which a default of 0.0 would not be."""
    from analysis.signal_journal import regime_ctx
    out = regime_ctx(_R(), {"TRENDING_BULL": "not-a-number"})
    assert out["label"] == "TRENDING_BULL"
    assert "conviction" in out


def test_the_helper_returns_None_on_every_malformed_ctx():
    """It runs inside journal writes on every event; raising there would take
    out telemetry across the fleet."""
    import main
    class _L:
        scores = SCORES
    assert main._l1_scores({"l1": _L()}) == SCORES
    for bad in ({}, {"l1": None}, None,
                {"l1": type("X", (), {"scores": {}})()},
                {"l1": type("X", (), {"scores": 7})()}):
        assert main._l1_scores(bad) is None


def test_every_call_site_passes_the_scores():
    """A site left on the old signature emits no axes and is invisible — the
    gap would look like sparse data rather than a missed edit."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "main.py"),
               encoding="utf-8").read()
    assert "regime_ctx(regime)" not in src, \
        "a call site still uses the old signature and will emit no axes"
    assert src.count("regime_ctx(regime, _l1_scores(ctx))") >= 7
