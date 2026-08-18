#!/usr/bin/env python3
"""
tests/test_liquidity_ledger.py — v1.1 — 2026-08-15
v1.1 — 2026-08-15 — A2.4: the wiring pins moved to the NEW truth — bar
        selection lives in the ledger (`feed_frame`, forming row excluded,
        `last_bar_ts` guard) and main calls it; the old pins asserted the
        gap-dropping `iloc[-2]` feed and would have held the defect in place.
v1.0 — 2026-08-13

The operator's rule is the whole specification: *"the wick counts as a touch,
but only a close counts as acceptance or rejection."* Every test below exists
because that sentence has three distinct outcomes per bar and a naive
implementation collapses them into two.

THE FAILURE THIS SUITE EXISTS TO PREVENT: counting a bar that never reached the
level as a HOLD. That is how a level price never went near starts looking
defended, and it would make every floor in the book look strong.

DELIBERATE-FAILURE CHECKS INCLUDED AND RUN — a fixture that cannot go red is
not evidence.

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python -m pytest tests/test_liquidity_ledger.py -q
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis import liquidity_ledger as LL                    # noqa: E402
import pytest                                                  # noqa: E402
import tempfile                                                # noqa: E402

# ── TEST ISOLATION (2026-08-15) ──────────────────────────────────────────────
# ⚠️ THE A2.3 HYDRATE MADE THESE TESTS STATEFUL. `reset_for_session` now READS
# BACK `<root>/<date>/<sym>.json`, so a test that writes it inherits its own
# previous run - `test_the_zone_cuts_BOTH_ways` reported `holds == 3` from a
# SINGLE bar because three invocations had stacked up. The hydrate is correct
# in production (it is the whole point of the restart fix); a test that shares
# state with its own history is not.
# ⚠️ AND IT WAS WRITING INTO THE REPO. `data/liquidity_ledger/` was not
# gitignored, so the deploy line's `git add -A` would have swept live fleet
# output into a commit - the MANIFEST.txt / trades.db precedent exactly. Now
# ignored, and the root is env-overridable so tests never touch it.
os.environ.setdefault("OT_LEDGER_ROOT", tempfile.mkdtemp(prefix="ledger_test_"))


@pytest.fixture(autouse=True)
def _isolate_ledger_root(monkeypatch, tmp_path):
    """A FRESH root per test, so no test can see another's file."""
    monkeypatch.setattr(LL, "_OUT_ROOT", str(tmp_path / "ledger"))


def fresh(tmp_root=None):
    led = LL.LiquidityLedger("QQQ")
    led.reset_for_session("2026-08-13", seeds=[
        (500.0, "low", "PDL", True),
        (495.0, "low", "PRIOR_LOW_2", False),
        (490.0, "low", "PRIOR_LOW_3", False),
        (510.0, "high", "PDH", True),
        (515.0, "high", "PRIOR_HIGH_2", False),
        (520.0, "high", "PRIOR_HIGH_3", False),
    ])
    return led


def lvl(led, price, kind):
    return next(l for l in led.levels
                if l.kind == kind and abs(l.price - price) < 0.01)


# ── the three outcomes ──────────────────────────────────────────────────────

def test_wick_touch_that_closes_back_is_a_HOLD():
    """Price stabs 500 and closes above it. Touch + hold, no breach."""
    led = fresh()
    led.on_closed_bar(high=503.0, low=499.0, close=502.0, ts="10:00")
    l = lvl(led, 500.0, "low")
    assert (l.touches, l.holds, l.breaches) == (1, 1, 0)
    assert l.last_result == "hold"


def test_close_beyond_is_a_BREACH():
    led = fresh()
    led.on_closed_bar(high=503.0, low=497.0, close=498.0, ts="10:01")
    l = lvl(led, 500.0, "low")
    assert (l.touches, l.holds, l.breaches) == (1, 0, 1)
    assert l.last_result == "breach"


def test_bar_that_never_reaches_counts_NOTHING():
    """THE ONE THAT MATTERS. A bar well above the level is neither a hold nor a
    touch. Counting it as a hold would make every distant level look defended."""
    led = fresh()
    led.on_closed_bar(high=509.0, low=505.0, close=507.0, ts="10:02")
    l = lvl(led, 500.0, "low")
    assert (l.touches, l.holds, l.breaches) == (0, 0, 0)
    assert l.last_result == ""


def test_highs_mirror_lows():
    led = fresh()
    led.on_closed_bar(high=511.0, low=505.0, close=508.0, ts="10:03")   # hold
    led.on_closed_bar(high=512.0, low=508.0, close=511.5, ts="10:04")   # breach
    h = lvl(led, 510.0, "high")
    assert (h.touches, h.holds, h.breaches) == (2, 1, 1)


def test_counts_accumulate_across_bars():
    """The defect in LiquidityMapper this module exists to fix: `touch_count`
    was rebuilt each call and never accumulated."""
    led = fresh()
    for _ in range(4):
        led.on_closed_bar(high=503.0, low=499.5, close=502.0, ts="10:05")
    l = lvl(led, 500.0, "low")
    assert l.touches == 4 and l.holds == 4 and l.breaches == 0


def test_one_bar_can_touch_several_levels():
    led = fresh()
    led.on_closed_bar(high=501.0, low=489.0, close=494.0, ts="10:06")
    assert lvl(led, 500.0, "low").breaches == 1     # closed below 500
    assert lvl(led, 495.0, "low").breaches == 1     # closed below 495
    assert lvl(led, 490.0, "low").holds == 1        # wicked 489, closed above


# ── lifecycle, coverage, persistence ────────────────────────────────────────

def test_reset_clears_and_reseeds():
    led = fresh()
    led.on_closed_bar(high=503.0, low=499.0, close=502.0)
    assert lvl(led, 500.0, "low").touches == 1
    led.reset_for_session("2026-08-14", seeds=[(400.0, "low", "PDL", True)])
    assert len(led.levels) == 1 and led.date == "2026-08-14"
    assert lvl(led, 400.0, "low").touches == 0


def test_coverage_reports_the_minimum():
    led = fresh()
    assert led.coverage() == {"highs": 3, "lows": 3, "meets_minimum": 1}
    thin = LL.LiquidityLedger("QQQ")
    thin.reset_for_session("2026-08-13", seeds=[(500.0, "low", "PDL", True)])
    assert thin.coverage()["meets_minimum"] == 0


def test_duplicate_seed_is_not_added_twice():
    led = fresh()
    n = len(led.levels)
    led.add_level(500.0, "low", "PDL", True)
    assert len(led.levels) == n


def test_write_is_atomic_and_readable(tmp_path, monkeypatch):
    monkeypatch.setattr(LL, "_OUT_ROOT", str(tmp_path))
    led = fresh()
    led.on_closed_bar(high=503.0, low=499.0, close=502.0, ts="10:07")
    assert led.write() is True
    p = tmp_path / "2026-08-13" / "QQQ.json"
    payload = json.loads(p.read_text())
    assert payload["schema_version"] == LL.SCHEMA_VERSION
    assert payload["symbol"] == "QQQ" and payload["coverage"]["meets_minimum"] == 1
    rec = next(l for l in payload["levels"]
               if l["kind"] == "low" and abs(l["price"] - 500.0) < 0.01)
    assert (rec["touches"], rec["holds"], rec["breaches"]) == (1, 1, 0)
    assert not [f for f in os.listdir(p.parent) if f.endswith(".tmp")], \
        "a temp file survived — the rename was not atomic"


def test_write_is_a_noop_when_nothing_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(LL, "_OUT_ROOT", str(tmp_path))
    led = fresh()
    assert led.write() is True
    assert led.write() is False


def test_floors_below_is_nearest_first():
    led = fresh()
    got = [l.price for l in led.floors_below(505.0)]
    assert got == [500.0, 495.0, 490.0]
    assert led.floors_below(400.0) == []


# ── fire-and-forget ─────────────────────────────────────────────────────────

def test_garbage_never_raises():
    """A ledger failure must never reach the trading loop."""
    led = fresh()
    for bad in ((None, None, None), ("x", "y", "z"), (float("nan"),) * 3):
        led.on_closed_bar(*bad)
    led.add_level(0, "low")
    led.add_level(500.0, "sideways")
    led.reset_for_session("2026-08-13", seeds=[(None, None)])
    assert True


# ── deliberate failure ──────────────────────────────────────────────────────

def test_deliberate_failure_the_reach_test_is_real():
    """If `reached` were always True, the never-reached bar would score a HOLD
    and test_bar_that_never_reaches_counts_NOTHING would go red. Prove that
    outcome is actually reachable rather than assumed."""
    led = fresh()
    led.on_closed_bar(high=509.0, low=505.0, close=507.0)
    assert lvl(led, 500.0, "low").holds == 0, (
        "a bar 5 points above the level scored a hold — the reach test is not "
        "being applied")
    led.on_closed_bar(high=503.0, low=499.0, close=502.0)
    assert lvl(led, 500.0, "low").holds == 1, (
        "a genuine wick touch did NOT score a hold — the reach test is now too "
        "strict, which is the opposite failure and equally silent")


def test_deliberate_failure_close_decides_not_the_wick():
    """Two bars with the SAME wick and different closes must score
    differently. If they do not, the close is not being read."""
    led = fresh()
    led.on_closed_bar(high=503.0, low=497.0, close=502.0)    # wick under, hold
    led.on_closed_bar(high=503.0, low=497.0, close=498.0)    # same wick, breach
    l = lvl(led, 500.0, "low")
    assert (l.touches, l.holds, l.breaches) == (2, 1, 1), (
        "identical wicks with opposite closes scored the same — the CLOSE is "
        "not deciding acceptance")


# ── LIQ.4 WIRING + LIQ.7 tolerance ─────────────────────────────────────────

def test_liq7_tolerance_matches_the_mappers_zone():
    """⚠️ ONE DEFINITION OF A ZONE. The ledger shipped at 0.0002 (2bp) while
    `liquidity_mapper._add_named_pool` uses `within_pct(..., 0.002)` (20bp) to
    decide two prices are the SAME LEVEL. On a $580 underlying 2bp is 12 CENTS —
    a clean approach that reversed just short of the level did not register as a
    test at all, so **the most-defended levels looked untested**, which is
    exactly what the sizing rule is meant to reward."""
    import analysis.liquidity_ledger as L
    assert abs(L.TOUCH_TOL_PCT - 0.002) < 1e-9


def test_the_zone_cuts_BOTH_ways():
    """A close slightly beyond the nominal price is still INSIDE the zone, so it
    is a HOLD, not a breach. A zone that only widened the touch test but not the
    acceptance test would count defended levels as broken."""
    from analysis.liquidity_ledger import LiquidityLedger
    led = LiquidityLedger("QQQ")
    led.reset_for_session("2026-08-17", seeds=[(580.0, "high", "PDH", True)])
    lv = led.levels[0]
    led.on_closed_bar(581.5, 580.2, 581.0)      # inside the +/-1.16 band
    assert lv.holds == 1 and lv.breaches == 0
    led.on_closed_bar(583.0, 580.5, 582.5)      # genuinely beyond
    assert lv.breaches == 1


def test_the_ledger_is_actually_wired_into_run_analysis():
    """It was built, tested and COLLECTING NOTHING since 2026-08-13. Every
    unwired session is level history that cannot be recovered later."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "main.py"),
               encoding="utf-8").read()
    assert "def _feed_liquidity_ledger(" in src
    i = src.index("liq_map   = get_liquidity_mapper().analyze(")
    assert "_feed_liquidity_ledger(" in src[i:i + 300], \
        "the ledger is not fed from run_analysis"


def test_only_CLOSED_bars_are_fed_and_only_once():
    """`df_1m`'s last row is the FORMING bar on most ticks. A2.4 moved bar
    selection INTO the ledger: `feed_frame` excludes the forming row and
    guards with the persisted `last_bar_ts` — the old iloc[-2] + one-stamp
    guard silently DROPPED closed bars on any tick slower than ~75s. The
    behavior itself is executed in tests/test_audit2_fixes.py; this pins the
    wiring's assembly."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "main.py"),
               encoding="utf-8").read()
    i = src.index("def _feed_liquidity_ledger(")
    seg = src[i:i + 3600]
    assert ".feed_frame(df_1m)" in seg, "the gap-safe feed is not wired"
    assert "df_1m.iloc[-2]" not in seg, "the gap-dropping single-bar feed is back"
    lsrc = open(os.path.join(os.path.dirname(__file__), "..",
                             "analysis", "liquidity_ledger.py"),
                encoding="utf-8").read()
    j = lsrc.index("def feed_frame(")
    lseg = lsrc[j:j + 2600]
    assert "iloc[:-1]" in lseg, "the forming last row is being fed"
    assert "last_bar_ts" in lseg, "no guard against re-feeding or gaps"


def test_seeds_come_from_the_mapper_not_re_derived():
    """LIQ.6 changed what a named pool IS. The ledger must take whatever the
    mapper currently names — rung suffixes included — rather than holding a
    second opinion about levels (WORKING_AGREEMENT 7)."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "main.py"),
               encoding="utf-8").read()
    i = src.index("def _feed_liquidity_ledger(")
    seg = src[i:i + 2600]
    assert 'getattr(liq_map, "pools"' in seg
    assert "PDH" not in seg and "prev_day_high" not in seg, \
        "the ledger is re-deriving level names instead of reading the mapper"
