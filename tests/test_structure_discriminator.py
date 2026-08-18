#!/usr/bin/env python3
"""
tests/test_structure_discriminator.py — v1.0 — 2026-08-14   (TCS.2 stage 1)

⚠️ THE BUG THIS CLOSES WAS LIVE, NOT HYPOTHETICAL.

`is_trend_credit` **IS NOT A COLUMN** in the trades table — 69 columns, and it is
not one of them. It was written into the in-memory record and never persisted.
`get_open_trades_live()` does `SELECT *`, so **any restart rehydrated an open
trend-participation position WITHOUT the flag**, `exit_engine`'s branch stopped
firing, and the leg dropped into the condor ladder with the ratchet and the 25%
premium stop.

That is the SAME failure as the 2026-08-14 identity fix, one level down: fixed
for the process that OPENED the trade, still broken for any process that
INHERITS it. **The hop that dropped it is a systemctl restart — which happens on
every bake.**

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python -m pytest tests/test_structure_discriminator.py -q
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy.structure import (Structure, of, is_trend_participation,   # noqa: E402
                                is_credit_vertical)

TC6 = {"strategy": "TrendCreditSpread", "setup_type": "trend_credit_short"}
CONDOR = {"strategy": "IronCondorStrategy", "setup_type": "condor_put"}


def test_the_flag_is_still_not_a_column():
    """THE PREMISE. If someone adds the column, this test tells them to revisit
    the derivation — it is not wrong to add it, but deriving must stay the
    authority, because rows opened BEFORE a migration rehydrate as None and
    None reads as False."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "database",
                            "trade_logger.py"), encoding="utf-8").read()
    m = re.search(r"CREATE TABLE IF NOT EXISTS trades\s*\((.*?)\n\s*\)", src, re.S)
    cols = [c[0] for c in re.findall(r"^\s+([a-z_]+)\s+(TEXT|REAL|INTEGER)",
                                     m.group(1), re.M)]
    assert "is_trend_credit" not in cols
    # and the fields the derivation DOES rely on must persist
    for needed in ("strategy", "setup_type"):
        assert needed in cols, f"the discriminator reads {needed}; it must persist"


def test_survives_a_restart_without_the_flag():
    """THE ONE THAT MATTERS. Same record, flag stripped — as `SELECT *` returns
    it after a restart."""
    assert is_trend_participation(dict(TC6, is_trend_credit=1)) is True
    assert is_trend_participation(TC6) is True, \
        "a rehydrated trend-participation leg is no longer recognised"


def test_pre_fix_rows_are_still_recognised():
    """Rows written before the 2026-08-14 identity fix carry
    `strategy="IronCondorStrategy"` with `setup_type="trend_credit_short"` — the
    strategy field is mislabelled and the setup type is the only surviving
    truth. All 108 of 08-14 look like this."""
    assert is_trend_participation(
        {"strategy": "IronCondorStrategy",
         "setup_type": "trend_credit_short"}) is True


def test_a_real_condor_leg_is_not_swept_up():
    assert is_trend_participation(CONDOR) is False
    assert of(CONDOR) is Structure.CONDOR_LEG
    assert is_credit_vertical(CONDOR) is True


def test_directional_trades_are_unaffected():
    for rec in ({"strategy": "ORBStrategy", "setup_type": "ORB Long"},
                {"strategy": "ContinuationStrategy",
                 "setup_type": "trend_continuation_breakout"},
                {"strategy": "SweepReversal", "setup_type": "sweep"}):
        assert of(rec) is Structure.DIRECTIONAL
        assert is_credit_vertical(rec) is False


def test_unknown_fails_CLOSED():
    """A misread must never hand a position a LOOSER exit than it earned.
    Unknown means ordinary directional management."""
    for rec in ({}, None, {"strategy": "SomethingNew"}, {"setup_type": ""}):
        assert of(rec) is Structure.DIRECTIONAL
        assert is_credit_vertical(rec) is False


def test_the_exit_engine_uses_the_derivation_not_the_raw_flag():
    src = open(os.path.join(os.path.dirname(__file__), "..", "execution",
                            "exit_engine.py"), encoding="utf-8").read()
    assert "is_trend_participation(record)" in src
    assert 'if bool(record.get("is_trend_credit")):' not in src, \
        "the exit still gates on the unpersisted flag"


def test_deliberate_failure_the_old_gate_would_fail_this():
    """Prove the fix is load-bearing: the previous predicate returns False on a
    rehydrated record, which is exactly the production bug."""
    old_gate = lambda r: bool((r or {}).get("is_trend_credit"))
    assert old_gate(TC6) is False          # the bug
    assert is_trend_participation(TC6) is True   # the fix
