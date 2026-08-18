"""
tests/test_condor_approach.py — v1.0 — 2026-08-04

Covers the condor approach telemetry end to end: the strategy-side maths, and
the offline verdict that decides item AI.

THE LOAD-BEARING TESTS are the two verdicts. The whole point of the tool is to
distinguish "the trigger is a little too far" (fit the parameter) from "the
trigger sits where price never goes" (fix the anchor) — opposite responses, and
before v-approachalways nothing could tell them apart, because the one branch
that reported approach fired zero times in a fleet-wide session.

Deliberate-failure check performed when written: averaging the two sides
instead of taking the closer one turns test_the_closer_side_is_what_counts red;
swapping the verdict thresholds turns both verdict tests red.
"""

import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(REPO, "tests", "condor_approach.py")
sys.path.insert(0, REPO)

from strategy.iron_condor_strategy import IronCondorStrategy as IC  # noqa: E402


class _Plan:
    underlying_at_decision = 100.0
    call_trigger_price = 105.0
    put_trigger_price = 95.0
    max_price_seen = 101.5
    min_price_seen = 98.0
    short_put_strike = 93
    short_call_strike = 107
    expected_move = 4.0
    decided_at = "11:11 ET"


# ── the strategy-side maths ─────────────────────────────────────────────────
def test_approach_is_the_fraction_of_the_required_journey():
    """Denominator is trigger-minus-spot-at-plan, so the number is comparable
    across a $30 symbol and a $900 one."""
    a = IC._approach(_Plan, None, 100.0)
    assert a["call_approach"] == 0.30      # 1.5 of the 5 points needed
    assert a["put_approach"] == 0.40       # 2.0 of the 5 points needed


def test_a_degenerate_trigger_is_none_not_zero():
    """A trigger at or inside spot has no journey. Zero would read as 'price
    went nowhere', which is the opposite of 'the question does not apply'."""
    class P(_Plan):
        call_trigger_price = 100.0
    assert IC._approach(P, None, 100.0)["call_approach"] is None


def test_the_text_form_carries_the_numbers_a_reader_needs():
    a = IC._approach(_Plan, None, 100.0)
    t = IC._approach_text(_Plan, a)
    for frag in ("approach call 30%", "put 40%", "spot@plan", "93/107"):
        assert frag in t, (frag, t)


def test_journalling_never_raises():
    """This module has never imported the journal and must not start being able
    to break the trading loop through it."""
    IC._journal_abandon(_Plan, {"call_approach": 0.3}, "regime_flip")


# ── the offline verdict ─────────────────────────────────────────────────────
def _world(tmp, approaches, cause="regime_flip", date="2026-08-04"):
    d = os.path.join(tmp, date)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "AAA.jsonl"), "w") as fh:
        for i, (ca, pa) in enumerate(approaches):
            fh.write(json.dumps({
                "ts_et": f"{date}T12:00:00", "symbol": "AAA",
                "event": "condor_abandon", "cause": cause,
                "approach": {"call_approach": ca, "put_approach": pa,
                             "spot_at_plan": 100.0, "max_seen": 101.0,
                             "min_seen": 99.0, "call_trigger": 105.0,
                             "put_trigger": 95.0, "short_put": 93,
                             "short_call": 107, "em_at_plan": 4.0,
                             "decided_at": "11:11 ET"},
            }) + "\n")
    return tmp


def _run(tmp, *extra):
    p = subprocess.run([sys.executable, TOOL, "--journal",
                        os.path.join(tmp, "*", "*.jsonl"),
                        "--since", "2026-01-01"] + list(extra),
                       capture_output=True, text=True, cwd=REPO)
    return p.stdout + p.stderr


def test_geometry_verdict_when_price_never_gets_close():
    out = _run(_world(tmp := tempfile.mkdtemp(), [(0.2, 0.15)] * 40))
    assert "GEOMETRY" in out, out[-900:]
    assert "ANCHOR is" in out or "midpoint" in out


def test_parameter_verdict_when_price_routinely_nearly_fires():
    out = _run(_world(tempfile.mkdtemp(), [(0.7, 0.5)] * 40))
    assert "PARAMETER" in out, out[-900:]
    assert "can be FITTED" in out


def test_the_middle_refuses_to_pick_a_story():
    out = _run(_world(tempfile.mkdtemp(), [(0.5, 0.45)] * 40))
    assert "NEITHER ESTABLISHED" in out, out[-900:]


def test_the_closer_side_is_what_counts():
    """A plan needs ONE side to fire. Averaging the two would report 0.45 for a
    plan whose call side reached 0.80 and call it 'neither established'."""
    out = _run(_world(tempfile.mkdtemp(), [(0.8, 0.1)] * 40))
    assert "PARAMETER" in out, out[-900:]


def test_thin_samples_are_refused_not_read():
    out = _run(_world(tempfile.mkdtemp(), [(0.2, 0.2)] * 5))
    assert "REFUSED" in out and "underpowered, not" in out


def test_an_empty_window_says_nothing_to_read_yet():
    """Sessions before v-approachalways reported only the regime — that is the
    gap, not a null."""
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(tmp)
        assert "Nothing to read" in out or "No condor_abandon rows" in out
