#!/usr/bin/env python3
"""
tests/test_extended_hours.py — v1.0 — 2026-08-15   (FEED.2)

THE OVERNIGHT TAPE WAS NEVER UNAVAILABLE. WE WERE ASKING DXFEED TO EXCLUDE IT.

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python -m pytest tests/test_extended_hours.py -q

`TastytradeStreamer.subscribe_candle` takes `extended_trading_hours: bool =
False`, and when it is False the SDK appends **`tho=true`** — trading-hours-only
— to the DXFeed symbol: `QQQ{=1h,tho=true}`. Every subscription this feed has
ever made carried it, by taking the default.

**That one default produced every symptom** chased on 2026-08-15: `ext=0` on 28
of 29 boxes, a 1h store of 252 bars (36 sessions x 7 = RTH only), and LIQ.6's
Asia and London sections having nothing to build from. It is NOT the session
guard, NOT the warm lead, NOT S3, NOT an entitlement tier.

⚠️ A SEPARATE STREAM, NOT A FLAG ON THE EXISTING `1h`. Plain 1h is read by
`structure_analyzer` (swings + S/R), by `pitchfork` and its observer, and by
`entry_snapshot`. Flipping it in place would rebuild all of them on 24h bars
with nothing announcing it — the pitchfork is a v4.0 milestone. The extended
stream lands under its OWN store symbol so no existing consumer moves.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FEED_SRC = open(os.path.join(os.path.dirname(__file__), "..", "data",
                             "candle_feed.py"), encoding="utf-8").read()
MAIN_SRC = open(os.path.join(os.path.dirname(__file__), "..", "main.py"),
                encoding="utf-8").read()


def test_the_sdk_default_really_is_trading_hours_only():
    """The whole finding rests on this. Assert it against the INSTALLED SDK, not
    against documentation or memory — if a future version flips the default,
    this test says so rather than the fleet silently changing shape."""
    import inspect
    from tastytrade.streamer import DXLinkStreamer
    sig = inspect.signature(DXLinkStreamer.subscribe_candle)
    assert sig.parameters["extended_trading_hours"].default is False
    body = inspect.getsource(DXLinkStreamer.subscribe_candle)
    assert "tho=true" in body, \
        "the SDK no longer marks RTH-only with tho=true; re-verify FEED.2"


def test_an_extended_subscription_is_actually_requested():
    assert "extended_trading_hours=ext" in FEED_SRC
    assert "EXT_STORE_SYMBOL" in FEED_SRC


def test_every_other_stream_stays_RTH_only():
    """Blast radius is the point. Only ONE sub may carry extended=True."""
    import re
    appends = re.findall(r"self\.subs\.append\(\((.*?)\)\)", FEED_SRC, re.S)
    ext_true = [a for a in appends if "True" in a]
    assert len(appends) >= 3
    assert len(ext_true) == 1, f"expected exactly one extended sub, got {len(ext_true)}"


def test_the_extended_stream_has_its_own_store_symbol():
    """If it shared `1h`, structure_analyzer's swings, the pitchfork's forks and
    entry_snapshot would all silently rebuild on 24h bars."""
    assert 'EXT_STORE_SYMBOL = f"{INSTRUMENT}_EXT"' in FEED_SRC
    assert '_EXT", "1h"' in MAIN_SRC or 'f"{INSTRUMENT}_EXT", "1h"' in MAIN_SRC


def test_the_named_level_frame_prefers_EXT_and_falls_back_LOUDLY():
    """A box baked before FEED.2 has no _EXT rows. Falling back to RTH-only 1h
    is exactly today's behaviour — not a regression — but it must SAY so, or
    'the sections are inert here' becomes invisible again."""
    i = MAIN_SRC.index("def _named_level_frame(")
    seg = MAIN_SRC[i:i + 2600]
    assert "_EXT" in seg
    assert "logger.warning(" in seg
    flat = " ".join(seg.replace('"\n', "").replace('"', "").split())
    assert "Asia and London sections CANNOT build" in flat


def test_no_separate_collector_is_needed():
    """RESOURCE ANSWER. `subscribe_candle` sends `fromTime = now - 16 days` and
    DXFeed streams HISTORY from there; without tho=true that history includes
    overnight bars. The feed ALREADY connects at 09:10 on the warm lead, so last
    night's Asia and London arrive on a connection that happens anyway —
    **no 08:15 wake, no batches of five, no conductor change, no extra
    instance-hours.**"""
    import data.candle_feed as cf
    assert cf.BACKFILL_DAYS["1h"] >= 10, \
        "1h backfill must span the section lookback or history cannot cover it"


def test_retention_covers_the_section_lookback():
    """⚠️ EXACTLY AT THE EDGE, AND WORTH KNOWING. The pruner keeps 240 1h rows
    = 10.0 days of 24h tape, against SECTION_LOOKBACK_DAYS = 10. It fits with
    ZERO margin — a missed night eats directly into the ladder's depth."""
    import data.candle_feed as cf
    from analysis.liquidity_mapper import LiquidityMapper
    keep_rows = 240
    assert keep_rows / 24.0 >= LiquidityMapper.SECTION_LOOKBACK_DAYS


# ── FEED.3 — no pruning, and the tuple-shape trap ──────────────────────────

def test_every_subs_consumer_unpacks_the_SAME_arity():
    """⚠️ I FOUND ONE OF THESE BY ACCIDENT, NOT BY LOOKING.

    FEED.2 widened `self.subs` from a 3-tuple to a 4-tuple. The prune loop still
    unpacked THREE and would have raised at runtime — but only after
    `PRUNE_EVERY_S`, inside the flush path, on a box in production. Nothing in
    the test suite touched it and `--once` exits before the first prune.

    This asserts every consumer matches the declared arity, so widening the
    tuple again can never leave a straggler."""
    import re
    decl = re.search(r"self\.subs:\s*List\[Tuple\[([^\]]+)\]\]", FEED_SRC)
    arity = len(decl.group(1).split(","))
    unpacks = re.findall(r"for \(([^)]+)\) in self\.subs", FEED_SRC)
    assert unpacks, "no consumers found - did the loop shape change?"
    for u in unpacks:
        assert len(u.split(",")) == arity, \
            f"unpack '{u}' has {len(u.split(','))} names, declared arity is {arity}"


def test_pruning_is_off_by_default():
    """Measured: a FULL YEAR of every interval with extended hours is ~54 MB per
    box, on an 8 GB root. Ten days is 1.5 MB. **The pruner was tidiness, not
    capacity** — and the bound, sized for the live loop, silently constrained
    analytical consumers TWICE: PF.2 (84 daily bars held, 10 handed to the
    engine) and LIQ.6's 10-day lookback landing on the 240-row ceiling."""
    import data.candle_feed as cf
    assert cf.PRUNE_KEEP_ROWS == 0


def test_the_POISON_purge_is_untouched():
    """It deletes BAD rows — non-positive prices, 2038-stamped DXFeed rollover
    junk that would sort to the top of a DESC window and masquerade as the
    newest bar — not OLD ones. Disabling age-pruning must not disable it."""
    assert "DELETE FROM candles WHERE open <= 0" in FEED_SRC
    assert "purged %d poison candle row(s)" in FEED_SRC
