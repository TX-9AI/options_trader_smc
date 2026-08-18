"""
tests/test_a2_cooccurrence_slim.py — v1.0 — 2026-08-04

Guards a2_cooccurrence v1.2's parse-time slim.

The dangerous failure here is not a crash. It is a future analysis reading a
field the slim drops: `.get()` returns None, the arithmetic degrades to zero,
and the tool prints a clean table describing nothing. So the load-bearing test
does not check a hardcoded list — it SCANS THE SOURCE for every `.get("…")` on a
record and asserts the slim keeps each one. Add a field to the analysis without
adding it to `_KEEP` and this goes red.

Deliberate-failure check performed when written: removing "price" from _KEEP
turns test_the_slim_covers_every_field_the_source_reads red; returning the
record unchanged from _slim turns test_the_slim_actually_drops_the_bulk red.
"""

import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_PATH = os.path.join(HERE, "a2_cooccurrence.py")
SRC = open(SRC_PATH).read()

_spec = importlib.util.spec_from_file_location("a2_cooc", SRC_PATH)
a2 = importlib.util.module_from_spec(_spec)
sys.path.insert(0, os.path.dirname(HERE))
_spec.loader.exec_module(a2)


def _fat():
    return {
        "sym": "AAA", "ts": "2026-08-04T10:00:00", "price": 100.0,
        "scores": {"TRENDING_BULL": 0.8, "RANGING": 0.7},
        "l2": {"regime": "TRENDING_BULL", "c": 0.9, "unused": "x"},
        # the bulk: per-factor breakdown and engine state, never read here
        "breakdown": {"pad": [0] * 5000},
        "engine_state": {"pad": [0] * 5000},
    }


def test_the_slim_covers_every_field_the_source_reads():
    """THE ONE THAT MATTERS. Scans the file for record `.get()` calls rather
    than trusting a list — a dropped field does not crash, it silently reads
    None and the tool prints a table describing nothing."""
    # EVERY `.get("…")` in the file, not just the ones on a variable named
    # r/rec/row. The first draft of this test matched those three names and
    # MISSED `seg[i].get("price")` — the deliberate-failure run exposed it by
    # dropping "price" from _KEEP and watching this test stay green while a
    # different one caught it. A guard that only looks where you expected the
    # bug is not a guard.
    read = set(re.findall(r'\.get\("([a-z_0-9]+)"', SRC))
    # keys read off the NESTED objects, not off the record itself
    read -= {"regime", "c"}
    kept = set(a2._KEEP) | {"l2"}
    missing = read - kept
    assert not missing, (
        f"a2_cooccurrence reads {sorted(missing)} but _slim drops it — "
        f"those values will silently read as None")


def test_the_slim_keeps_the_values_intact():
    s = a2._slim(_fat())
    assert s["sym"] == "AAA" and s["price"] == 100.0
    assert a2.sc(s, "TRENDING_BULL") == 0.8
    assert s["l2"]["regime"] == "TRENDING_BULL" and s["l2"]["c"] == 0.9


def test_the_slim_actually_drops_the_bulk():
    """The whole point: 17 sessions of full records is what the OOM killer
    reacted to."""
    fat, slim = _fat(), a2._slim(_fat())
    assert len(json.dumps(slim)) * 20 < len(json.dumps(fat)), \
        "the slim is not materially smaller — the OOM is not fixed"
    assert "breakdown" not in slim and "engine_state" not in slim


def test_a_record_missing_l2_survives():
    """Pre-v4.8 rows carry no l2 at all, and the co-occurrence section counts
    them as `no_l2` rather than skipping the file."""
    fat = _fat()
    fat.pop("l2")
    assert "l2" not in a2._slim(fat)


def test_a_malformed_l2_does_not_raise():
    fat = _fat()
    fat["l2"] = "not-a-dict"
    assert "l2" not in a2._slim(fat)
