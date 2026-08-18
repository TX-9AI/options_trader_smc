#!/usr/bin/env python3
"""
tests/test_flat_angle_wiring.py — v1.0 — 2026-08-18   (STR.2)

COMPUTED, RECORDED IN THE EVIDENCE, NEVER DELIVERED.

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python -m pytest tests/test_flat_angle_wiring.py -q

`trades.flat_angle_deg` came back from the separation probe as **100% ties on
ONE unique value** — read as "the angle does not separate outcomes."

It is not that. **Five strategies already ask for it** — orb, butterfly,
continuation and sweep (twice) — via
`signal.flat_angle_deg = getattr(regime, 'flat_angle_deg', 0.0)`.
**`RegimeState` had no such attribute**, so all five took the default.

And the quantity was never missing: `regime_confluence.flat_angle_deg()` runs on
every RANGING/COMPRESSION evaluation and its result lands in the breakdown dict
as `{"angle": ...}`. **Computed, recorded in the evidence, and never carried to
the consumer** — the same shape as `direction_conf`, which separated on the live
book and was journaled nowhere. That is now three instances of the same defect
class in one week.

⚠️ WHY THIS ONE MATTERS MORE THAN THE OTHERS: the angle is a STRUCTURAL read,
not a magnitude one. It is the slope of the recent window in ATR units — the
closest thing collected to *"is price going anywhere, or just rotating?"* That
is the class the operator reads charts with, and the class the probe has never
been able to test because the column was empty.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def test_regime_state_now_has_the_attribute_five_strategies_read():
    from analysis.regime_classifier import RegimeState
    assert hasattr(RegimeState(), "flat_angle_deg")


def test_the_default_cannot_be_mistaken_for_a_flat_tape():
    """⚠️ THE SUBTLE PART. **0.0 degrees IS the flattest possible reading**, so a
    0.0 default is indistinguishable from a genuinely flat market — precisely
    the confusion that produced this bug. A negative sentinel cannot be read as
    a measurement."""
    from analysis.regime_classifier import RegimeState
    assert RegimeState().flat_angle_deg < 0


def test_the_sentinel_survives_the_strategies_or_idiom():
    """Strategies write `getattr(regime, 'flat_angle_deg', 0.0) or 0.0`. A
    sentinel of 0.0 would be swallowed by the `or`; -1.0 is truthy and reaches
    the trade record intact, so "not computed" stays visible downstream."""
    val = -1.0
    assert (val or 0.0) == -1.0
    assert (0.0 or 0.0) == 0.0          # a real flat reading still records 0.0


def test_main_lifts_the_angle_out_of_the_breakdown():
    src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    assert "regime.flat_angle_deg = float(_a)" in src
    assert '("RANGING", "COMPRESSION")' in src, \
        "the angle is produced under those two keys only"


def test_the_producer_still_exists_and_still_records_the_angle():
    """If the breakdown key is renamed, the wiring silently reverts to the
    sentinel and the column goes empty again — with nothing raising."""
    conf = open(os.path.join(ROOT, "analysis", "regime_confluence.py"),
                encoding="utf-8").read()
    assert "def flat_angle_deg(" in conf
    assert '"angle": round(ang, 2)' in conf


def test_all_five_readers_are_still_wired():
    n = 0
    for fn in os.listdir(os.path.join(ROOT, "strategy")):
        if fn.endswith(".py"):
            s = open(os.path.join(ROOT, "strategy", fn), encoding="utf-8").read()
            n += s.count("signal.flat_angle_deg")
    assert n >= 5, f"expected >=5 readers, found {n}"


def test_telemetry_cannot_break_the_regime_path():
    """⚠️ This runs on every tick inside the regime path on a live box."""
    src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    i = src.index("regime.flat_angle_deg = float(_a)")
    seg = src[i:i + 400]
    assert "except Exception" in seg
