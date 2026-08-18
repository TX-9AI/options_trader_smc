"""
tests/test_candle_feed_once_exempt.py — v1.0 — 2026-08-04

Pins candle_feed v3.10: `--once` is exempt from BOTH RTH gates.

WHY SOURCE-LEVEL. Exercising `run()` needs a TastyTrade session, a DXLink
streamer and a live event loop; standing those up would test the mocks. The
change is two boolean conditions and they are the whole of it — and the failure
they caused was invisible at every level a normal test looks: no exception, no
non-zero exit, an INFO line reading `Feed idle — outside RTH`, and a 38-byte
CSV where a 16 KB one belonged. It cost two sessions of sat-out tape before
anyone read the box log, and DXFeed history is same-evening only, so it is
permanent.

THE SECOND GATE IS THE ONE THAT MATTERS. The RTH-over break inside the stream
loop sits ABOVE the `--once` drain-exit, so fixing only the outer gate reproduces
the identical hang one layer down with the backfill still undrained. A test that
checked one condition would have passed a broken fix.
"""

import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(REPO, "data", "candle_feed.py")).read()


def _run_body() -> str:
    """The body of `async def run(self, once=...)`, where both gates live."""
    i = SRC.index("async def run(self, once")
    return SRC[i:i + 12000]


def test_both_gates_go_through_the_one_predicate():
    """v3.11 — two sites, ONE predicate, so they cannot disagree again.

    v3.9 wrote the condition inline twice and v3.10 had to patch both. The
    whole incident was three independent clock checks in a chain; collapsing
    these two is what stops a fourth from being written by hand.
    """
    body = _run_body()
    n = len(re.findall(r"self\._idle_outside_session\(once\)", body))
    assert n == 2, (
        f"expected BOTH gates to call _idle_outside_session(once), found {n}. "
        f"The outer gate idles the reconnect loop; the inner one breaks the "
        f"stream loop ABOVE the --once drain-exit.")


def test_the_predicate_keys_on_purpose_not_only_the_clock():
    assert "def _idle_outside_session(once: bool)" in SRC
    assert "return not is_rth() and not once" in SRC


def test_no_bare_rth_gate_survives_in_run():
    """A bare `if not is_rth():` anywhere in run() is the v3.9 form and hangs a
    one-shot backfill again."""
    body = _run_body()
    bare = re.findall(r"if not is_rth\(\):", body)
    assert not bare, (
        "a bare `if not is_rth():` is back inside run() — a --once backfill "
        "outside RTH will sleep until its timeout and write a header-only csv")


def test_the_drain_exit_is_still_reachable():
    """The exemption is only useful if the one-shot can still terminate."""
    body = _run_body()
    assert '--once: backfill drained, exiting' in body
    # the inner break must not precede the drain check unconditionally
    brk = body.index("RTH over — closing DXLink socket")
    drain = body.index("--once: backfill drained")
    assert brk < drain, "layout changed — re-verify the break/drain ordering"
    guarded = body[brk - 300:brk]
    assert "_idle_outside_session(once)" in guarded, \
        "the RTH-over break is no longer exempt for --once, so the drain-exit " \
        "below it is unreachable on a one-shot run outside RTH"


def test_the_service_path_still_idles_outside_rth():
    """v3.9 exists so a maintenance wake does not put 29 boxes on the wire for
    work that needs no market data. The exemption must not undo that."""
    body = _run_body()
    assert "Feed idle — outside RTH" in body
    assert "RTH over — closing DXLink socket" in body


def test_the_header_records_what_it_cost():
    """The version header is the durable record of a silent, permanent data
    loss. If it goes, the next person reads a one-line boolean change."""
    assert "v3.11" in SRC[:4000]
    assert "same-evening only" in SRC[:4000]
