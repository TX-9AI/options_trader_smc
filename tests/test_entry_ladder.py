#!/usr/bin/env python3
"""
tests/test_entry_ladder.py — v1.0 — 2026-08-13   (FRC.2)

The operator's manual technique, in his worked example: *"if we are buying and
the spread is 1.95 to 2.35 then mark is 2.15 & the spread is .40... I would try
2.05, 2.10 and then 2.15."*

THE FAILURE THIS SUITE EXISTS TO PREVENT is not a wrong price — it is a FAKE
PROFIT. `paper_fill_price` books the posted price and assumes it fills. Shade
the limit without a fill test and every trade books 2.05 while no missed entry
is ever modelled: **the more aggressive the rung, the larger the manufactured
gain.** So the ladder is only ever half of this; `fill_model` is the other half,
and the tests below cover both together.

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python -m pytest tests/test_entry_ladder.py -q
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution.limit_ladder import (entry_ladder_prices, price_increment,     # noqa: E402
                                    round_to_increment)
from execution.fill_model import would_fill, walk_ladder                      # noqa: E402


# ── the operator's example, exactly ─────────────────────────────────────────

def test_operator_worked_example_buy():
    assert entry_ladder_prices(1.95, 2.35, "buy", symbol="QQQ") == [2.05, 2.10, 2.15]


def test_operator_worked_example_sell_is_mirrored():
    assert entry_ladder_prices(1.95, 2.35, "sell", symbol="QQQ") == [2.25, 2.20, 2.15]


def test_ladder_ends_at_the_mark():
    for side in ("buy", "sell"):
        assert entry_ladder_prices(1.95, 2.35, side, symbol="QQQ")[-1] == 2.15


def test_rungs_are_a_fraction_of_the_SPREAD_not_a_fixed_shade():
    """v1.0's shade was dropped because it moved a FIXED number of ticks
    'about a spread we cannot see'. A wide quote must shade wide and a narrow
    one narrow — otherwise this is the same defect wearing new clothes."""
    wide = entry_ladder_prices(1.00, 3.00, "buy", symbol="QQQ")
    narrow = entry_ladder_prices(1.98, 2.02, "buy", symbol="QQQ")
    assert (wide[-1] - wide[0]) > (narrow[-1] - narrow[0])


def test_a_rung_never_posts_through_the_far_side():
    for bid, ask in ((1.95, 2.35), (0.05, 0.10), (10.0, 10.02)):
        for side in ("buy", "sell"):
            for px in entry_ladder_prices(bid, ask, side, symbol="QQQ"):
                assert bid <= px <= ask


def test_unusable_quotes_return_an_empty_ladder():
    """Empty means the caller falls back to limit_at_mark — never to a guess."""
    for bid, ask in ((2.35, 1.95), (0, 0), (None, 2.0), (2.0, None), (-1, 2.0)):
        assert entry_ladder_prices(bid, ask, "buy", symbol="QQQ") == []


# ── venue increments: class AND price level ────────────────────────────────

def test_increment_depends_on_class_and_level():
    assert price_increment("QQQ", 2.15) == 0.01     # penny, under $3
    assert price_increment("QQQ", 4.20) == 0.05     # penny, over $3
    assert price_increment("SPX", 2.15) == 0.05     # non-penny, under $3
    assert price_increment("SPX", 4.20) == 0.10     # non-penny, over $3


def test_unknown_symbol_is_treated_as_NON_penny():
    """Conservative on purpose: a coarser increment is always a VALID price,
    while a finer one may be rejected or SILENTLY ADJUSTED by the venue — a
    fill at a price nobody chose, with nothing in the logs to explain it."""
    assert price_increment("ZZZZ", 2.15) == 0.05


def test_rounding_is_directional_and_in_the_traders_favour():
    """Nearest-rounding would make ~half the rungs MORE aggressive than
    specified. On a dime class that is a nickel of unrequested aggression per
    rung — a quarter of the edge this ladder exists to capture."""
    assert round_to_increment(2.13, "SPX", "buy") == 2.10
    assert round_to_increment(2.13, "SPX", "sell") == 2.15
    assert round_to_increment(4.23, "SPX", "buy") == 4.20
    assert round_to_increment(2.13, "QQQ", "buy") == 2.13     # penny, untouched


def test_nickel_class_produces_postable_prices():
    for px in entry_ladder_prices(1.95, 2.35, "buy", symbol="SPX"):
        assert abs(round(px / 0.05) * 0.05 - px) < 1e-9, f"{px} is not on a nickel"


def test_coarse_grid_collapses_rungs_rather_than_repeating_a_price():
    """Without this the ladder posts the same price three times and burns 45
    seconds pretending to walk."""
    dime = entry_ladder_prices(4.00, 4.40, "buy", symbol="SPX")
    assert len(dime) == len(set(dime)) and len(dime) < 3
    narrow = entry_ladder_prices(2.10, 2.20, "buy", symbol="SPX")
    assert len(narrow) == len(set(narrow))


# ── the fill model — the half that stops fake profit ───────────────────────

def test_buy_fills_only_when_the_ASK_comes_down_to_us():
    """THE CORE ASYMMETRY. To buy at L someone must OFFER at or below L — the
    ASK reaching down, not the mid drifting. Testing the mid would report a
    fill roughly twice as often and recreate the optimism being removed."""
    quotes = [{"bid": 2.00, "ask": 2.30}, {"bid": 1.98, "ask": 2.05}]
    assert would_fill("buy", 2.05, quotes)["fill_price"] == 2.05
    assert would_fill("buy", 2.00, quotes) is None      # ask never reached 2.00


def test_sell_fills_only_when_the_BID_comes_up_to_us():
    quotes = [{"bid": 2.00, "ask": 2.30}, {"bid": 2.25, "ask": 2.40}]
    assert would_fill("sell", 2.25, quotes)["fill_price"] == 2.25
    assert would_fill("sell", 2.30, quotes) is None


def test_a_resting_limit_gets_ITS_price_not_a_better_one():
    """A market gapping through does not improve a resting limit."""
    assert would_fill("buy", 2.05, [{"bid": 1.50, "ask": 1.60}])["fill_price"] == 2.05


def test_no_fill_returns_None_and_carries_no_price():
    """The shape makes 'fill at the last rung anyway' awkward on purpose — that
    silent degradation is exactly the failure this module replaces."""
    r = walk_ladder("buy", [2.05, 2.10, 2.15],
                    [[{"bid": 2.20, "ask": 2.30}]] * 3)
    assert r["filled"] is False and r["fill_price"] is None and r["rung"] is None
    assert r["rungs_tried"] == 3


def test_walk_stops_at_the_first_rung_that_fills():
    r = walk_ladder("buy", [2.05, 2.10, 2.15],
                    [[{"bid": 2.20, "ask": 2.30}],       # rung 1 misses
                     [{"bid": 2.00, "ask": 2.08}],       # rung 2 fills
                     [{"bid": 1.90, "ask": 1.95}]])
    assert r["filled"] and r["rung"] == 1 and r["fill_price"] == 2.10
    assert r["missed_rungs"] == 1


def test_garbage_quotes_are_skipped_not_treated_as_fills():
    bad = [{"bid": 0, "ask": 0}, {"bid": 3.0, "ask": 1.0}, {"bid": None, "ask": 2.0}]
    assert would_fill("buy", 2.05, bad) is None


# ── deliberate failure ─────────────────────────────────────────────────────

def test_deliberate_failure_the_fill_test_can_refuse():
    """If `would_fill` always returned a fill, every test above would pass and
    the ladder would manufacture profit. Prove refusal is reachable on a quote
    that plainly never came to us."""
    assert would_fill("buy", 1.00, [{"bid": 5.00, "ask": 5.10}]) is None
    assert would_fill("buy", 5.20, [{"bid": 5.00, "ask": 5.10}]) is not None


def test_deliberate_failure_the_increment_is_load_bearing():
    """Same quote, penny vs non-penny class, MUST differ.

    ⚠️ THE FIXTURE IS THE HARD PART, and I got it wrong twice. Both bid and ask
    must sit ON the nickel grid (1.90 / 2.20) so no penny PROOF fires, while the
    half-spread (0.15) puts the RUNGS off the grid so the class is the only
    deciding fact. A quote with an off-nickel bid or ask proves penny for BOTH
    symbols and makes the ladders identical — correct behaviour that looks like
    a failed test.
    """
    penny = entry_ladder_prices(1.90, 2.20, "buy", symbol="QQQ")
    coarse = entry_ladder_prices(1.90, 2.20, "buy", symbol="ZZZZ")
    assert penny == [1.97, 2.01, 2.05]
    assert coarse == [1.95, 2.00, 2.05]
    assert penny != coarse, "the venue increment is not changing the ladder"


def test_off_nickel_quote_proves_penny_regardless_of_class():
    """The asymmetric proof: an off-nickel quote can only ever REFINE the grid
    downward, never coarsen it. A non-penny class quoting 2.11 IS quoting in
    pennies, whatever any list says."""
    assert entry_ladder_prices(2.11, 2.19, "buy", symbol="ZZZZ") == \
        entry_ladder_prices(2.11, 2.19, "buy", symbol="QQQ")
