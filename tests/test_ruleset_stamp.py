"""
tests/test_ruleset_stamp.py — v1.0 — 2026-08-07

Pins N.7: every signal_journal row carries the ruleset that produced it.

WHY IT MATTERS MORE THAN IT LOOKS. Every cross-date analysis of these rows —
L3.2a's rejection ledger, any future gate calibration, the readiness digest —
pools decisions made by DIFFERENT ENGINES. 2026-08-07 alone changed the emission
law, the regime set, two dispatch gates, an exit gate and two floors. Without
this stamp the pooling is invisible and the analysis cannot even warn about it;
L3.2a could only emit `decision_hash: null`. The same gap was named on 07-29
about engine identity, where the proposed fix was exactly this.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis import signal_journal as sj      # noqa: E402


def test_ruleset_is_resolved_and_non_empty():
    r = sj.ruleset()
    assert isinstance(r, str) and r, "ruleset must never be empty"


def test_ruleset_is_never_a_partial_hash():
    """"unknown" is the ONLY acceptable fallback. A truncated or fabricated hash
    would look attributable while silently pooling engines — worse than absent."""
    r = sj.ruleset()
    assert r == "unknown" or (4 <= len(r) <= 40 and all(
        c in "0123456789abcdef" for c in r)), f"suspicious ruleset {r!r}"


def test_every_row_carries_it():
    with tempfile.TemporaryDirectory() as d:
        sj._OUT_ROOT = d
        sj.journal("disposition", outcome="gate_block:vwap")
        found = [os.path.join(dp, f) for dp, _dn, fn in os.walk(d) for f in fn]
        assert found, "no journal file written"
        row = json.loads(open(found[0]).readline())
        assert row.get("ruleset") == sj.ruleset()
        assert row.get("event") == "disposition"


def test_resolution_happens_once_not_per_row():
    """A `git rev-parse` per journal line would put a subprocess in the trading
    loop. A process runs one ruleset for its whole life, so import time is the
    only moment it can change."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "analysis",
                            "signal_journal.py")).read()
    i = src.index("def journal(")
    assert "_resolve_ruleset()" not in src[i:], (
        "ruleset is being resolved inside journal() — that is a subprocess per "
        "row in the trading loop")
