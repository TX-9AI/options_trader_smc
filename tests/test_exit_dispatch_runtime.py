#!/usr/bin/env python3
"""
tests/test_exit_dispatch_runtime.py — v1.0 — 2026-08-14   (AUDIT F1/F2/F4)

**THE FIRST SUITE ON THIS PATH THAT EXECUTES THE EVALUATOR.**

Every prior test on the TC.6/condor exit chain was a source-text or AST
assertion — it checked that a string APPEARED in the file. That is how a call
to a function that was never imported (F1), and a dispatch that never routed
the record to the branch under test (F2), sailed through 162 green tests: a
mention is not a binding, and hop 0 — the dispatch — was never asserted at
all. WORKING_AGREEMENT §20, one level up.

These tests construct records in BOTH shapes the engine actually sees —
  · FRESH: exactly the keys `_execute_condor_leg`'s make_record sets
    (no trail_activation key at all), and
  · REHYDRATED: every column present, unset ones None, as SELECT * returns —
and CALL evaluate(), asserting on the returned decision. The two shapes differ
in exactly the keys that kept breaking.

DELIBERATE-FAILURE VERIFICATION (run 2026-08-14, sandbox, stubbed broker):
against `3d9e82e` (pre-v4.21) this suite fails 6/6 —
  F1  NameError: is_trend_participation      (condor leg, legacy TC.6 row)
  F2a KeyError: 'trail_activation'           (fresh TC.6)
  F2b routed to _evaluate_sweep / post_target_trail   (rehydrated TC.6)
  F2c TypeError: float < None                (rehydrated TC.6 below nickel)
  F4  restart forgets the earned ratchet     (condor leg holds past its lock)
A suite that has never gone red is one nobody knows works; this one was born
red against the exact commit it exists to prevent recurring.

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python -m pytest tests/test_exit_dispatch_runtime.py -q
"""

import os
import sys
import datetime as _dt

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import execution.exit_engine as XE          # noqa: E402
from utils.time_utils import ET             # noqa: E402


# ── fixtures: freeze the clock mid-session, silence the sibling DB query ─────

class _FrozenDT(_dt.datetime):
    """12:30 ET — inside RTH, before every close window."""
    @classmethod
    def now(cls, tz=None):
        return _dt.datetime(2026, 8, 14, 12, 30, tzinfo=ET)


@pytest.fixture()
def engine(monkeypatch):
    monkeypatch.setattr(XE, "is_hard_close_time", lambda: False)
    monkeypatch.setattr(XE, "datetime", _FrozenDT)
    eng = XE.ExitEngine(paper_trading=True)
    # standalone by default — tests that need "formed" flip this themselves.
    # Patched so no test touches a trade DB.
    eng._condor_sibling_open = lambda record: False
    return eng


def _fresh_condor(**over):
    """A condor-leg record with exactly the keys _execute_condor_leg sets."""
    r = dict(
        trade_id="c" * 36, symbol="IWM", strategy="IronCondorStrategy",
        setup_type="Condor Leg 1 (call)", setup_grade="B", direction="neutral",
        option_side="call", is_butterfly=0,
        entry_premium=1.00, stop_premium=1.00 * 1.25, target_premium=0.05,
        underlying_entry=220.0, underlying_stop=0.0,
        contracts=1, is_condor_leg=1, condor_leg_num=1,
        entry_time="2026-08-14T15:00:00+00:00", status="open",
    )
    r.update(over)
    return r


def _fresh_tc6(**over):
    """A TC.6 record with exactly the keys _execute_condor_leg sets for
    _is_tcs — note: NO trail_activation key, stop_premium 0.0, nickel target."""
    r = dict(
        trade_id="t" * 36, symbol="NVDA", strategy="TrendCreditSpread",
        setup_type="trend_credit_short", setup_grade="B", direction="neutral",
        option_side="put", is_butterfly=0,
        entry_premium=0.55, stop_premium=0.0, target_premium=0.05,
        underlying_entry=100.0, underlying_stop=98.5,
        contracts=1, is_condor_leg=0, condor_leg_num=0,
        entry_time="2026-08-14T15:00:00+00:00", status="open",
    )
    r.update(over)
    return r


def _rehydrated(rec):
    """The SELECT * shape: every column present, unset ones None/0."""
    r = dict(rec)
    r.setdefault("trail_activation", None)
    r.setdefault("underlying_target", None)
    r["trail_stop"] = r.get("trail_stop", 0.0)
    r["current_premium"] = r["entry_premium"]
    return r


# ── F1: the condor evaluator must be CALLABLE mid-session ────────────────────

def test_condor_leg_evaluates_without_raising_and_holds(engine):
    """Pre-v4.21: NameError on is_trend_participation, every tick, every leg."""
    d = engine.evaluate(_fresh_condor(), current_premium=1.02, regime="RANGING")
    assert d.should_exit is False


def test_condor_leg_stop_still_fires(engine):
    d = engine.evaluate(_fresh_condor(), current_premium=1.30, regime="RANGING")
    assert d.should_exit and d.exit_reason.startswith("condor_stop")


def test_legacy_tc6_row_takes_the_tcs_branch(engine):
    """Pre-identity-fix rows: strategy=IronCondorStrategy, setup trend_credit_*.
    Must reach the TC.6 branch (no premium stop), not the condor ladder."""
    rec = _fresh_condor(setup_type="trend_credit_short", stop_premium=0.0,
                        underlying_stop=225.0, option_side="call")
    d = engine.evaluate(_rehydrated(rec), current_premium=1.30, regime="TRENDING_BULL")
    assert d.should_exit is False, (
        "legacy TC.6 row picked up a condor exit: %s" % d.exit_reason)


# ── F2: TrendCreditSpread records must route to the condor evaluator ─────────

def test_fresh_tc6_routes_and_holds_no_keyerror(engine):
    """Pre-v4.21: routed to _evaluate_sweep -> KeyError 'trail_activation' on
    the FIRST management tick of every freshly opened TC.6."""
    d = engine.evaluate(_fresh_tc6(), current_premium=0.55)
    assert d.should_exit is False


def test_tc6_has_no_premium_stop_even_widened(engine):
    """+45%% widening must NOT exit — breach or 15:45 only (operator's spec).
    Pre-v4.21 the sweep path put this record in the post-target trail."""
    d = engine.evaluate(_rehydrated(_fresh_tc6()), current_premium=0.80)
    assert d.should_exit is False, d.exit_reason
    assert d.new_trail_stop is None, "a debit trail was applied to a credit leg"


def test_tc6_breach_fires_on_closed_bar(engine):
    """Put spread, boundary 98.50; a 1m CLOSE below it is thesis death."""
    df = pd.DataFrame({"close": [99.2, 98.1]})
    d = engine.evaluate(_rehydrated(_fresh_tc6()), current_premium=0.80, df_1m=df)
    assert d.should_exit and d.exit_reason.startswith("tcs_breach")


def test_tc6_below_nickel_holds_no_typeerror(engine):
    """Pre-v4.21: TypeError (float < None) the moment a rehydrated winner
    decayed under $0.05 — a crash at maximum profit. Post-fix: HOLDS, because
    the operator's revised spec is breach-or-15:45, nothing else."""
    d = engine.evaluate(_rehydrated(_fresh_tc6()), current_premium=0.04)
    assert d.should_exit is False


# ── F4: the earned ratchet must survive a restart ────────────────────────────

def test_condor_ratchet_persists_and_reseeds(engine, monkeypatch):
    rec = _rehydrated(_fresh_condor())
    # leg runs to +45%: lock tier -> stop at entry*(1-LOCK_PCT), emitted for
    # persistence via new_trail_stop (the trail_stop column channel).
    d1 = engine.evaluate(dict(rec), current_premium=0.55, regime="RANGING")
    assert d1.should_exit is False
    assert d1.new_trail_stop is not None and d1.new_trail_stop < 1.25, (
        "earned ratchet was not emitted for persistence")
    locked = d1.new_trail_stop

    # RESTART: a brand-new engine, record rehydrated WITH the persisted level.
    eng2 = XE.ExitEngine(paper_trading=True)
    eng2._condor_sibling_open = lambda record: False
    rec2 = dict(rec); rec2["trail_stop"] = locked
    d2 = eng2.evaluate(rec2, current_premium=locked + 0.05, regime="RANGING")
    assert d2.should_exit and d2.exit_reason.startswith("condor_stop"), (
        "restart forgot the earned ratchet: %s" % d2.exit_reason)

    # CONTROL (the pre-v4.21 behaviour): no persisted level -> base stop only,
    # the same tick HOLDS. If this control ever starts exiting, the seed is
    # reading something it should not.
    eng3 = XE.ExitEngine(paper_trading=True)
    eng3._condor_sibling_open = lambda record: False
    rec3 = dict(rec); rec3["trail_stop"] = 0.0
    d3 = eng3.evaluate(rec3, current_premium=locked + 0.05, regime="RANGING")
    assert d3.should_exit is False


def test_formed_condor_does_not_emit_or_apply_ratchet(engine):
    """v4.17 scope must survive v4.21: while the sibling is open, base floor
    ONLY — no tier applied, no level emitted for persistence."""
    engine._condor_sibling_open = lambda record: True
    rec = _rehydrated(_fresh_condor())
    d = engine.evaluate(dict(rec), current_premium=0.55, regime="RANGING")
    assert d.should_exit is False
    assert d.new_trail_stop is None, "formed branch persisted a ratchet level"
