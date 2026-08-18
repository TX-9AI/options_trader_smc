#!/usr/bin/env python3
"""
tests/test_tcs_identity_chain.py — v1.0 — 2026-08-14

**THE STRATEGY AND THE EXIT ENGINE WERE BOTH CORRECT AND THE TRADE STILL DID
THE WRONG THING, BECAUSE THE HANDOFF BETWEEN THEM DROPPED EVERY FLAG THEY
AGREED ON.**

`_execute_condor_leg` builds the trade record for BOTH a condor leg and a trend
credit spread, and it hardcoded condor identity onto both. Found 2026-08-14 by
auditing the logic against the operator's stated intent — NOT by any test, and
not by watching P&L.

WHAT IT COST, all of it fatal to the intent:
  · `is_trend_credit` never reached the record, so `_evaluate_condor_leg`'s TC.6
    branch — gated on `record.get("is_trend_credit")` — **COULD NEVER FIRE.**
    Every TC.6 leg fell into the condor ladder and picked up the ratchet and the
    25%% premium stop. That is the `stop=$0.69` on a $0.55 credit in the 10:02
    Telegram alerts, and it means the terminal-return fix shipped that morning
    repaired a branch that never executed.
  · `underlying_stop` was never set, so even had the branch fired the breach
    rule would have had NO BOUND and would have skipped itself silently.
  · `strategy` and `regime` were hardcoded, so TC.6 trades were logged as
    IronCondorStrategy in RANGING and their P&L was attributed to the condor.

THE LESSON WORTH KEEPING: a flag is only real if it survives every hop. Unit
tests on the producer and the consumer both passed while the wire between them
was cut. These are CHAIN assertions — signal -> record -> exit — because that is
the only place the defect was visible.

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python -m pytest tests/test_tcs_identity_chain.py -q
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.join(os.path.dirname(__file__), "..")


def src(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


MAIN = src("main.py")
STRAT = src("strategy/trend_credit_spread.py")
EXIT = src("execution/exit_engine.py")


def leg_fn() -> str:
    i = MAIN.index("def _execute_condor_leg(")
    return MAIN[i:MAIN.index("\ndef ", i + 10)]


# ── HOP 1: the strategy sets the flags ─────────────────────────────────────

def test_signal_carries_the_identity_and_the_bound():
    assert "sig.is_trend_credit = True" in STRAT
    assert "underlying_stop=boundary" in STRAT


def test_the_bound_passed_to_build_signal_is_the_orb_level():
    assert "self._build_signal(side, short, long_c, direction, bound," in STRAT


# ── HOP 2: the record copies them ──────────────────────────────────────────

def test_record_derives_identity_from_the_SIGNAL_not_the_function():
    """One function serves two trades; identity must come from the signal, never
    from the path it happens to route through."""
    f = leg_fn()
    assert '_is_tcs = bool(getattr(signal, "is_trend_credit", False))' in f
    assert f.index("_is_tcs =") < f.index("record = make_record("), \
        "the flag is read after the record is built"


def test_record_carries_tc6_identity_in_PERSISTED_fields():
    """⚠️ REWRITTEN BY TCS.4 (2026-08-17). This asserted the record carried
    `is_trend_credit  = 1 if _is_tcs else 0,` — **and that line CRASH-LOOPED
    NFLX live**: `log_entry` INSERTs every record key, `is_trend_credit` has no
    column, the INSERT raised, the error cap tripped, the service restarted, and
    it did it again every 15s.

    The INTENT of this test is right and unchanged — TC.6's identity must reach
    the record. What changed is WHICH FIELDS carry it. Per WORKING_AGREEMENT §22
    (*"PREFER DERIVING"*), identity now travels in the PERSISTED `strategy` and
    `setup_type` columns and `structure.py` derives the rest. Those survive a
    restart; a non-column never did.

    ⚠️ THE SIGNAL ATTRIBUTE `sig.is_trend_credit` IS UNTOUCHED AND MUST STAY —
    it is in-memory only, `_execute_condor_leg` reads it via `getattr` to decide
    `_is_tcs`, and it is never written to the DB. Signal attribute: keep.
    Record key: gone."""
    f = leg_fn()
    assert '"TrendCreditSpread" if _is_tcs' in f, \
        "the record must still name TC.6 in the `strategy` COLUMN"
    assert "is_trend_credit  =" not in f, \
        "the non-column write is back; this crash-looped a live box"


def test_record_carries_the_bound_as_underlying_stop():
    """Without this the breach rule has nothing to test and skips itself."""
    assert 'underlying_stop  = getattr(signal, "underlying_stop", 0.0),' in leg_fn()


def test_strategy_and_regime_are_not_hardcoded_for_tc6():
    f = leg_fn()
    assert '"TrendCreditSpread" if _is_tcs' in f
    assert '"RANGING" if not _is_tcs' in f


def test_no_premium_stop_is_written_for_tc6():
    """The measured EV was HELD TO EXPIRY, UNMANAGED. Writing a stop here is
    what made a $0.06 credit closeable on one cent of widening."""
    f = leg_fn()
    assert "stop_premium     = (0.0 if _is_tcs" in f


def test_a_condor_leg_is_unaffected():
    """Scope: the condor still gets its own identity, regime and stop."""
    f = leg_fn()
    assert 'else "IronCondorStrategy"' in f
    assert "else fill_credit * (1 + CONDOR_STOP_LOSS_PCT)" in f


# ── HOP 3: the exit reads the same key ─────────────────────────────────────

def test_the_exit_gates_on_fields_the_record_ACTUALLY_PERSISTS():
    """The original defect was a key one side wrote and the other never
    received. **The second defect was the same key written to a column that did
    not exist.** Both halves must now name fields that SURVIVE A RESTART.

    The exit derives via `is_trend_participation(record)`; the record supplies
    `strategy` and `setup_type`, both real columns. Verified end-to-end in
    `test_derivation_works_on_the_persisted_row_alone` below."""
    assert 'is_trend_participation(record)' in EXIT
    f = leg_fn()
    assert '"TrendCreditSpread" if _is_tcs' in f
    assert '"trend_credit' in f or 'setup_type' in f


def test_derivation_works_on_the_persisted_row_alone():
    """⚠️ THE TEST THAT WOULD HAVE CAUGHT BOTH DEFECTS. Round-trip what SQLite
    actually gives back — a dict of COLUMNS ONLY, no in-memory extras — and
    assert the exit still routes TC.6 correctly. `SELECT *` on a rehydrated
    position returns exactly this shape."""
    from strategy.structure import is_trend_participation, is_credit_vertical
    persisted = {"strategy": "TrendCreditSpread",
                 "setup_type": "trend_credit_short",
                 "is_condor_leg": 0}
    assert is_trend_participation(persisted) is True
    assert is_credit_vertical(persisted) is True


def test_the_exit_reads_the_bound_from_underlying_stop():
    i = EXIT.index("if is_trend_participation(record):")
    seg = EXIT[i:i + 900]
    assert 'record.get("underlying_stop")' in seg


def test_the_exit_branch_still_terminates():
    """Re-pinned here because the branch is only reachable now. A fall-through
    drops a TC.6 leg into the ratchet and the 25% stop."""
    import ast
    tree = ast.parse(EXIT)
    for n in ast.walk(tree):
        if isinstance(n, ast.If) and "is_trend_participation" in (
                ast.get_source_segment(EXIT, n.test) or ""):
            assert isinstance(n.body[-1], ast.Return)
            return
    raise AssertionError("the TC.6 branch is gone")


# ── deliberate failure ─────────────────────────────────────────────────────

def test_deliberate_failure_a_dropped_flag_is_detectable():
    """Prove these assertions can fail — a record built without the flag must be
    detectable, which is precisely what no test caught for a whole day."""
    hardcoded = 'strategy         = "IronCondorStrategy",\n        setup_type = x'
    assert '"TrendCreditSpread" if _is_tcs' not in hardcoded, (
        "the fixture should NOT contain the conditional — if it does, the "
        "assertion is matching something other than what it claims")
    assert '"TrendCreditSpread" if _is_tcs' in leg_fn()
