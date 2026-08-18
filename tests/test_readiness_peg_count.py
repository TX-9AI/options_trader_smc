"""
tests/test_readiness_peg_count.py — v1.0 — 2026-08-05

Pins readiness_digest v1.2: the headline's pegged count and the FIT SUGGESTIONS
list measure the SAME thing.

WHAT WAS WRONG. `npeg` counted peg rates on the RAW `_val` series; the fits
measure the RAMPED output. So the number in the Telegram headline could
disagree with the list it tells you to go read — and the headline is what people
act on. On 2026-08-05 it reported "9 pegged factor(s)".

WHY THE RAMPED OUTPUT IS THE RIGHT ONE. The module's own premise: "a
corroborator pegged at its bound is a constant wearing new clothes." A RAW value
at its bound is often just what that factor IS — a binary corroborator is 0 or 1
by construction, and flagging it says nothing. A RAMPED output at its bound is
the term contributing nothing that varies, which is the actual alarm and the
thing the Aug 8-9 fits are sized against.

Deliberate-failure check performed when written: restoring the raw `_val` count
turns test_the_headline_counts_ramps_not_raw_values red.
"""

import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(REPO, "tests", "readiness_digest.py")).read()


def test_the_headline_counts_ramps_not_raw_values():
    """THE ONE THAT MATTERS. One definition, shared with the fits."""
    assert "npeg = len(fits)" in SRC, \
        "the headline must count the same pegged ramps the FIT SUGGESTIONS " \
        "list, or it sends people to a list that disagrees with it"


def test_the_raw_val_count_is_gone():
    assert not re.search(r'npeg = sum\(1 for k in per.*_val', SRC, re.S), \
        "the raw `_val` peg count is back — a binary corroborator is 0 or 1 " \
        "by construction and flagging it says nothing"


def test_the_wording_says_ramps():
    """`pegged factor(s)` invited exactly the confusion this fixes."""
    assert "pegged ramp(s)" in SRC
    assert "pegged factor(s) — see FIT" not in SRC


def test_the_fits_still_measure_the_ramped_output():
    """The fits were always right; this must not drift the other way."""
    assert "rv = fac.get(ramped)" in SRC
    body = SRC[SRC.index("rv = fac.get(ramped)"):][:400]
    assert "PEG_ALARM" in body and "PEG_HI" in body


def test_the_alarm_threshold_is_still_stated():
    assert "PEG_ALARM = 0.60" in SRC
