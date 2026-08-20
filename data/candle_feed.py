"""
data/candle_feed.py  addendum v3.16 (see below); original header follows.
v3.16  2026-08-20  🔴 FEED.2 ROUTED EVERY 1h CANDLE TO THE WRONG SYMBOL FOR
       SIX DAYS, FLEET-WIDE. `symbol_map` was keyed on (dx_symbol, interval)
       and FEED.2 subscribes the SAME symbol at the SAME interval twice — RTH
       and extended. The second registration overwrote the first, so one
       lookup could not tell them apart and every 1h bar landed under the EXT
       store symbol. Measured 2026-08-20: plain QQQ and SPX 1h frozen at
       2026-08-14 while *_EXT 1h was current. Six days of stale higher-
       timeframe structure feeding structure_analyzer's swings and S/R, the
       pitchfork and its observer, and entry_snapshot — on every box that took
       FEED.2. Nothing raised. BARS_STALE warned every five minutes with
       `refused=False` and the bots traded on 08-14 bars regardless.
       FIX: the map key carries the extended-hours flag, and the ingest router
       reads `tho=true` off the echoed symbol — the attribute `_interval_of`
       deliberately discards is exactly the one the router needed.
       GUARD: the feed now REFUSES TO START if two subscriptions share a route
       key, if a subscription has no route, or if two subscriptions write the
       same (store_symbol, interval). The defect was not a typo; it was a
       route table that could silently lose an entry, and that must be
       impossible rather than merely fixed.
       ⚠️ The existing rows are not repaired by this — plain-symbol 1h history
       between 08-14 and the deploy is simply absent and DXFeed history is
       use-it-or-lose-it. Backfill on restart will refill what the API still
       serves.
v3.15  2026-08-18  TERM.1: read_chain_subs UNIONS AUXILIARY TENORS.
        Every chain snapshot to date carries a SINGLE expiry equal to the
        session date, so TERM STRUCTURE - the one thing options data says about
        WHEN the market expects movement rather than how much - is not
        computable. It also cannot be backfilled.
        `chain_subs` is CHECK (id = 1), a single row BY DESIGN, so extra
        expiries ride in a separate `chain_subs_aux` table and are unioned here.
        The returned `expiry` string still names the FRONT expiry only: every
        existing caller reads it that way and none of them changes.
        FAILS OPEN, DELIBERATELY. THIS FUNCTION DECIDES WHAT A LIVE TRADING BOX
        SUBSCRIBES TO. Missing, stale (>6h), malformed, or dropped mid-run, the
        front expiry comes back exactly as before - verified against real
        SQLite in tests/test_tenor_capture.py. Archival enrichment must never
        cost the bot its own chain.
        STALENESS BOUND because the session cap is real: v3.1 measured
        TastyTrade's unpublished limit near ~40 concurrent, and last week's
        strikes would burn budget for contracts nothing reads.
v3.14  2026-08-15  FEED.3: PRUNING IS OFF. `PRUNE_KEEP_ROWS=0` by default.
        THE BOUND WAS SIZED FOR THE LIVE LOOP and kept silently constraining
        analytical consumers that arrived later. Twice now: PF.2 found the boxes
        held 84 daily bars while the engine was handed 10 ("the history was
        never missing - the frame was"), and LIQ.6's 10-day section lookback
        landed on exactly the 240-row 1h ceiling with ZERO margin.
        AND IT WAS NEVER BUYING ANYTHING. Measured: a FULL YEAR of every
        interval with extended hours is **54 MB per box**, on an 8 GB root. Ten
        days is 1.5 MB. The pruner was tidiness, not capacity.
        The local store keeps what it collects; S3 is the archive and weekend
        reporting reads the bucket, so the box is no longer the deep copy of
        anything. OT_PRUNE_KEEP_ROWS=<n> re-enables a flat cap - kept as a
        mechanism rather than deleted so reversing it is one env var.
        THE POISON PURGE IS UNTOUCHED and must stay: it deletes BAD rows
        (non-positive prices, 2038-stamped DXFeed rollover junk), not OLD ones.
        ALSO FIXED HERE: the prune loop still unpacked a 3-TUPLE after FEED.2
        widened `self.subs` to four. It would have raised at runtime after
        PRUNE_EVERY_S inside the flush path, on a box in production - `--once`
        exits before the first prune and no test touched it. A test now asserts
        every consumer matches the declared arity.
v3.13  2026-08-15  FEED.2: THE OVERNIGHT TAPE WAS NEVER UNAVAILABLE - WE WERE
        ASKING DXFEED TO EXCLUDE IT. `subscribe_candle` takes
        `extended_trading_hours: bool = False`, and on False the SDK appends
        **`tho=true`** (trading-hours-only) to the symbol: `QQQ{=1h,tho=true}`.
        Every subscription this feed has ever made carried it, by default.
        THAT ONE DEFAULT produced every symptom chased on 08-15: ext=0 on 28 of
        29 boxes, a 1h store of 252 bars (36 sessions x 7 = RTH only), and
        LIQ.6's Asia and London sections with nothing to build from. NOT the
        session guard, NOT the warm lead, NOT S3, NOT an entitlement tier.
        A SEPARATE STREAM, NOT A FLAG ON `1h`. Plain 1h is read by
        structure_analyzer (swings + S/R), pitchfork + its observer, and
        entry_snapshot; flipping it in place would rebuild all of them on 24h
        bars with nothing announcing it. The extended stream lands under its own
        store symbol `<SYM>_EXT`, so NO existing consumer moves.
        NO SEPARATE COLLECTOR IS NEEDED. fromTime is now-16d and DXFeed streams
        HISTORY from there, so last night arrives on the 09:10 warm-lead
        connection that already happens - no 08:15 wake, no batches of five, no
        conductor change, no extra instance-hours.
        RETENTION IS EXACTLY AT THE EDGE: the pruner keeps 240 1h rows = 10.0
        days of 24h tape against SECTION_LOOKBACK_DAYS=10. Zero margin - a
        missed night eats straight into the ladder.
        OT_EXT_1H=0 disables the stream.
v3.12  2026-08-15  FEED.1: THE THIRD PURPOSE - a MAINTENANCE window.
        `_idle_outside_session` already said "THE DISTINCTION IS PURPOSE, NOT
        TIME" but had only TWO purposes, so `--once` was allowed at ANY hour.
        That is right for the EOD pull and wrong for what v3.9 actually
        protects against: a maintenance wake putting all 29 boxes on the wire
        for work needing no market data. **It cannot be a clock rule** - the
        08:15 overnight capture pass and a maintenance window fall on the same
        hours and want opposite behaviour.
        MODES: service (default, unchanged) | capture (gates as service; the
        name makes a capture wake distinguishable in the logs and gives a
        future window argument somewhere to live) | maintenance (HARD OFF,
        `--once` included).
        A SENTINEL FILE, not only env: `Environment=` is read once at import,
        so flipping a RUNNING feed would need a restart - and that restart
        window is exactly when the box is on the wire during the maintenance it
        should be excused from. `data/FEED_MAINTENANCE` is checked on every
        gate evaluation; touch to enter, rm to leave, nothing restarts.
        FAILS OPEN TO service on an unreadable flag - the one place in this
        repo that deliberately does. A stray socket is recoverable in seconds;
        a missed session is PERMANENT (DXFeed history is same-evening only,
        which is how 08-03 and 08-04 were lost).
        AND IT ANNOUNCES ITSELF AT WARNING, naming the mode and saying the tape
        is NOT being collected - the 08-03 loss was this gate firing silently
        at INFO and writing fourteen 38-byte header-only CSVs.
v3.11 — 2026-08-04 — ONE PREDICATE, `_idle_outside_session(once)`, called from
        both the reconnect gate and the RTH-over break. v3.9 wrote the condition
        inline twice and v3.10 had to patch both; a fourth caller would have had
        to remember a fourth time, and the whole incident was three independent
        clock checks in a chain, two of which blocked the same operation. Pure
        refactor — the decision is identical at both sites and service mode is
        byte-equivalent to v3.10.
        WHAT IT ENCODES: the gate exists to stop a box HOLDING a live
        subscription with no session to serve. Reports and backfills hold
        nothing, so they run outside RTH; the fleet-maintenance wake that
        prompted v3.9 is still blocked, because that runs in SERVICE mode.
v3.10 — 2026-08-04 — `--once` IS EXEMPT FROM BOTH RTH GATES. v3.9's gate never
        asked whether the run was a one-shot backfill, and neither did the
        RTH-over break inside the stream loop. A one-shot outside RTH therefore
        slept 60s at a time in the outer loop until `timeout 200` killed it,
        having subscribed to nothing and written nothing.
        WHAT IT COST: `pull_today_ohlc.sh` — the ONLY path the EOD candle
        retrieval has — calls exactly `candle_feed --once`. From 2026-08-03 every
        SAT-OUT box that eod_backfill woke produced a HEADER-ONLY csv: fourteen
        38-byte files on 08-04, the same signature on 08-03. **DXFeed history is
        same-evening only, so both sessions' sat-out tape is permanent loss.**
        Nothing raised. The log read `Feed idle — outside RTH` at INFO, four
        times, and then `0 bars`.
        BOTH SITES HAD TO MOVE TOGETHER. The inner break sits ABOVE the --once
        drain-exit, so fixing only the outer gate produces the identical hang one
        layer down with the backfill still undrained.
        WHY THE EXEMPTION IS RIGHT RATHER THAN A LOOPHOLE: v3.9 exists so a box
        does not HOLD a live socket when no session needs one. `--once` connects,
        pulls HISTORY from 09:30, flushes and exits — it holds nothing. The
        service path is untouched, so the maintenance-wake problem v3.9 solved
        stays solved.
v3.9 — 2026-08-01 — RTH GATE on the reconnect loop. The feed had NO time gate
        (Restart=always, no timer), so while a box was up it held a DXLink socket
        continuously. Invisible on a normal day — phase_report stops the
        instances at EOD — but every MAINTENANCE wake put 29 boxes back on the
        wire for work needing no market data. Now sleeps outside RTH and holds no
        subscriptions at all.
        SAFE FOR CHAIN ARCHIVAL, which is what made this look risky: Greeks and
        Quote ride this same socket, so idling also stops draining chain_marks —
        but chain_snapshot.snapshot() takes the chain as an ARGUMENT and runs
        inside main.py's tick loop, which already returns early on not is_rth()
        (main.py:1268). Archival only ever happens during RTH.
        Connects OT_FEED_WARM_LEAD_S (default 1200s = 20 min) BEFORE the open,
        covering the 09:15 fleet wake, because fetch_candles refuses on a stale
        heartbeat and a feed connecting at exactly 09:30 serves nothing for its
        first cycles.
        BOTH EDGES, not just the start. The top-of-loop gate decides whether to
        CONNECT; a second check on the existing flush cadence DISCONNECTS when
        the session ends, so a box left up overnight releases its subscriptions
        instead of streaming until something drops it. Buffered bars are flushed
        immediately before the break, so nothing is lost.

v3.8 — 2026-07-15 — SUBSCRIPTION FAULT-ISOLATION + EXCEPTIONGROUP UNWRAP.
        Each candle subscribe is now independent: one failing (symbol,tf)
        (e.g. an entitlement gap) is logged with its REAL cause and skipped
        instead of killing the whole stream. And the reconnect handler now
        unwraps asyncio's ExceptionGroup so the actual DXFeed error is
        logged, not 'unhandled errors in a TaskGroup'. This is what left XOM
        (and any entitlement-gapped symbol) dark and undiagnosable for two
        days. Additive to v3.7 (parser) / v3.5 (chunked chain) — no other
        behaviour changed.

v3.5 — 2026-07-14 — CHUNKED chain subscribes (75 symbols/frame). SPX/QQQ-sized
        0DTE chains in a single subscribe frame risk a websocket 1009
        (message too long) close that would bounce the whole socket, candles
        included — untested exposure until now because SPX never won a session
        slot during the v3.1 trial. No other change.
v3.4 — 2026-07-13 — CHAIN MARKS ON THE SAME SOCKET (Option 1b — session-cap fix).
        2026-07-13 proved TastyTrade's unpublished concurrent-session cap sits
        near ~40: 29 candle-feeds + per-box chain streamers (options_chain
        v3.1) could not all connect (~6-11 admitted, rest locked out). This
        release finishes the v3.0 doctrine — ONE producer, many readers — by
        carrying the options-chain Greeks/Quote subscriptions on the feed's
        EXISTING DXLink socket. Fleet steady state: 29 sessions total, the
        number proven safe for weeks. Mechanics:
        • options_chain (v3.2) writes the desired streamer-symbol set + expiry
          to a new chain_subs row in the store; the feed reconciles
          subscriptions every flush cycle (subscribe deltas; expiry rollover
          unsubscribes all Greeks/Quote and clears chain_marks).
        • Greeks/Quote events drain non-blocking each loop pass into
          latest-value buffers, flushed to a new chain_marks table on the
          existing 2 s flush cadence. Candle handling is UNCHANGED.
        • On socket reconnect, chain subscription state resets and
          re-reconciles automatically (same path as candle resubscribe).
        The bot process now opens ZERO DXLink connections.

options_trader_v3/data/candle_feed.py — THE single candle-feed producer. v3.0
v3.0 — 2026-07-10 — initial release (Yahoo-Finance purge; single shared TastyTrade
        candle feed / data stream mapping optimization). This service owns the
        ONLY DXLinkStreamer subscription on the box. Every other process (the
        trading bot, the shadow observer, the candle logger, query tools) reads
        the shared SQLite store this service maintains. One producer, many
        readers — it is FORBIDDEN for any consumer to open its own DXFeed
        stream.
v3.2 — 2026-07-13 — POISON-CANDLE GUARD (producer side). Reject at ingest any
        candle whose timestamp falls outside a sane window (kills the DXFeed
        signed-32-bit rollover bar: ts=2147483648xxx ms => year 2038) or whose
        OHLC contains a non-positive price. Observed live on GOOGL 2026-07-13:
        the junk bar entered the store, won the "latest bar" query in
        fetch_quote(), returned 0.0, and killed the bot's tick loop every tick
        while the unit still reported ACTIVE. Also adds FeedStore.purge_poison(),
        run at startup, so a box whose store was already poisoned self-heals on
        restart with no manual sqlite surgery across the fleet.
v3.3 — 2026-07-13 — CROSS-THREAD SQLITE FIX. FeedStore's connection is built on
        the MAIN thread but every write (_flush -> upsert_candles / heartbeat /
        commit / prune) is driven from the asyncio event-loop thread created by
        get_loop(). Python's sqlite3 rejects that by default, so candle-feed
        died on its FIRST flush on every start ("SQLite objects created in a
        thread can only be used in that same thread") and systemd's
        Restart=on-failure turned it into a crash-loop — which in turn piled up
        DXLink sessions until TastyTrade returned "The number of user sessions
        has exceeded the configured limit" (GOOGL, 2026-07-13). Connection now
        uses check_same_thread=False with an explicit threading.Lock
        serializing every write; still a single writer, so WAL semantics are
        unchanged.

Architecture (Mandate 2 of the Yahoo-Finance purge):
  - Runs as its own systemd unit: candle-feed.service (Before=optionsbot).
  - Reuses data.tasty_client.get_session() and get_loop() — one login, one
    background event loop, no duplication.
  - Subscribes ONCE to this box's symbol (config.INSTRUMENT) across every
    interval in config.TIMEFRAMES (1m, 5m, 15m, 1h, 1d) plus VIX (1m + 1d),
    with per-interval backfill start times deep enough to satisfy
    TIMEFRAMES[tf]["candles"] with margin (entitlement permitting — see
    FIRST-RUN CHECKLIST below).
  - Maintains a rolling in-memory buffer, last-write-wins per int(candle.time)
    (DXFeed re-sends/corrects bars — same mechanics proven in
    candle_logger._collect v1.x, consolidated here as a PERSISTENT
    subscription instead of a one-shot drain).
  - Flushes the buffer to an on-box SQLite store in WAL mode (one writer, many
    concurrent readers, atomic, survives consumer restarts):
        candles(symbol, interval, ts_epoch_ms, open, high, low, close, volume)
        feed_meta(symbol, interval, last_write_epoch)   -- staleness detection
    plus a global heartbeat row feed_meta('__feed__','heartbeat') updated on
    every flush cycle so readers can detect a dead feed even when no new bars
    are arriving (e.g. the forming 1d bar).
  - Keeps a bounded history per (symbol, interval): PRUNE_FACTOR x the largest
    configured count, pruned periodically.
  - Reconnects with backoff if the streamer drops; re-backfills from session
    open so corrected bars are re-applied.

Store location (producer and every consumer must resolve identically):
  $OT_FEED_DB if set, else <repo>/data/feed_store.db  (self-locating, same
  pattern as candle_logger's OHLC dir — no /var/lib permission trap).

DXFeed symbology:
  Equities/ETFs use the plain ticker. Index boxes may need a DXFeed-specific
  symbol — set OT_DXFEED_SYMBOL to override (e.g. OT_DXFEED_SYMBOL=SPX).
  VIX subscribes as $OT_DXFEED_VIX (default "VIX").
  Candle events arrive as 'QQQ{=1m}' — base symbol = split on '{'. Bars are
  stored under the BOT's symbol name (config.INSTRUMENT / "VIX"), not the
  DXFeed alias, so readers never need the mapping.

FIRST-RUN CHECKLIST (one box, before fleet deploy — mirrors candle_logger v1.x):
  1. History depth / entitlement: journalctl -u candle-feed | grep "backfill"
     — every interval must report >= its configured count (1h needs ~10
     trading days, 1d needs ~3 weeks). Thin entitlement on 1h/1d will surface
     here, NOT as a silent short window downstream. The persistent buffer
     accumulates over the session, so intraday depth grows on its own.
  2. VIX entitlement: grep "VIX" — if DXFeed lacks VIX on your entitlement,
     macro falls back stale->default-20 (fail-loud WARNING). See
     data/macro_data.py v3.0 header for the flagged alternative.
  3. Index symbology: SPX box — set OT_DXFEED_SYMBOL and confirm bars land.

Usage:
    python -m data.candle_feed                 # foreground (systemd runs this)
    python -m data.candle_feed --once          # single backfill+flush, then exit
                                               # (smoke test / pre-open warm)
"""
import argparse
import asyncio
import logging
import os
import json
import sqlite3
import traceback
import threading
import time as _time
from datetime import datetime, time as dtime, timedelta
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from tastytrade import DXLinkStreamer           # module-level so tests can patch
from tastytrade.dxfeed import Candle, Greeks, Quote

from config import INSTRUMENT, TIMEFRAMES
from data.tasty_client import get_session, get_loop

logger = logging.getLogger(__name__)

# ── Poison-candle sanity window (v3.2) ────────────────────────────────────────
# Any candle timestamp outside this window is junk. The observed failure is the
# signed-32-bit rollover (2**31 * 1000 = 2147483648000 ms => 2038-01-19), which
# is far in the future; a 0 / negative ts is equally invalid. Upper bound is
# computed at call time (now + 2 days) so a legitimately-fresh bar is never
# rejected for clock skew, while a 2038 bar always is.
TS_MS_MIN = 1_262_304_000_000        # 2010-01-01 — older than any bar we'd want


def _ts_ms_max() -> int:
    """Newest acceptable candle ts: now + 2 days (tolerates clock skew, kills 2038)."""
    return int((_time.time() + 172_800) * 1000)
ET = ZoneInfo("America/New_York")

# ─── Store location — single definition, imported by every reader ─────────────

def feed_db_path() -> str:
    """Resolve the shared store path. $OT_FEED_DB overrides; default is
    self-locating inside the repo's data/ dir so producer and consumers on the
    same checkout always agree."""
    env = os.environ.get("OT_FEED_DB", "").strip()
    if env:
        return env
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "feed_store.db")


# ─── Tunables ──────────────────────────────────────────────────────────────────

SESSION_OPEN_HM   = (9, 30)          # ET
FLUSH_INTERVAL_S  = 2.0              # buffer -> SQLite cadence (also heartbeat)
PRUNE_FACTOR      = 4                # legacy; unused while PRUNE_KEEP_ROWS is 0
# FEED.3: 0 = NO PRUNING (default). Set OT_PRUNE_KEEP_ROWS to a positive row
# count to re-enable a flat per-(symbol,interval) cap. Kept as a mechanism
# rather than deleted so it is one env var to reverse, not a code change.
PRUNE_KEEP_ROWS   = int(os.environ.get("OT_PRUNE_KEEP_ROWS", "0"))
# TERM.1: an auxiliary-tenor subscription older than this is ignored. Stale
# strikes burn socket budget against a measured ~40-session cap for contracts
# nothing reads.
AUX_MAX_AGE_S     = 6 * 3600
PRUNE_EVERY_S     = 300
RECONNECT_MIN_S   = 3

# Seconds BEFORE the RTH open at which the feed connects, so candle frames are
# warm when the bot's first tick asks for them. 20 min covers the 09:15 fleet
# wake. OT_FEED_WARM_LEAD_S=0 makes the gate exact-open; a large value
# effectively restores the old always-on behaviour.
from utils.time_utils import is_rth, seconds_until_rth_open   # RTH gate, 2026-08-01

FEED_WARM_LEAD_S = float(os.environ.get("OT_FEED_WARM_LEAD_S", "1200"))

# ── FEED MODE (FEED.1, 2026-08-15) — THE THIRD PURPOSE ───────────────────────
# `_idle_outside_session` already says the right thing: **"THE DISTINCTION IS
# PURPOSE, NOT TIME."** It only had TWO purposes — service (hold a socket for a
# live session) and one-shot (`--once`, pull history and exit). A `--once` run
# is therefore allowed at ANY hour, which is correct for the EOD pull and wrong
# for the thing v3.9 was actually protecting: **a maintenance wake that brings
# all 29 boxes up for work needing no market data.**
#
# Operator's requirement: a dedicated MAINTENANCE window where the whole fleet
# can be up for fleet updates "without involving the feed or using api
# resources". That cannot be expressed as a clock rule — maintenance and the
# overnight capture pass happen at the same hours and want opposite behaviour.
#
#   service      today's behaviour, unchanged. The default, so nothing moves.
#   capture      a scoped one-shot pull. Same as service for gating; the name
#                exists so a capture wake is DISTINGUISHABLE in the logs from a
#                trader wake, and so a future window argument has somewhere to
#                live.
#   maintenance  HARD OFF. No socket, no subscription, not even `--once`.
#
# ⚠️ AND IT MUST ANNOUNCE ITSELF. On 2026-08-03/04 the gate silently blocked the
# EOD pull: the log read `Feed idle — outside RTH` at INFO four times, then
# `0 bars`, and fourteen 38-byte header-only CSVs were written. Nothing raised,
# and DXFeed history is same-evening only, so BOTH SESSIONS ARE PERMANENTLY
# LOST. A maintenance-suppressed run must never look like a failed fetch: it
# logs at WARNING and says the mode by name.
# ⚠️ A SENTINEL FILE, NOT ONLY AN ENV VAR. `Environment=` in the unit is read
# ONCE AT IMPORT, so flipping the mode on a RUNNING feed would need a restart —
# and the restart window is precisely when the box is on the wire during the
# maintenance it is supposed to be excused from. The file is checked on every
# gate evaluation, so `touch`/`rm` takes effect on the next loop with nothing
# to restart and no race to lose.
MAINT_FLAG = os.environ.get(
    "OT_FEED_MAINT_FLAG",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "FEED_MAINTENANCE"))


def _maintenance_now() -> bool:
    """True if this box is in a maintenance window RIGHT NOW.

    Sentinel file first (live, no restart), env second (set at wake time).
    ⚠️ FAILS OPEN TO service ON AN UNREADABLE PATH: a box that cannot stat the
    flag must keep FEEDING, because the alternative is a silent tape loss that
    DXFeed's same-evening history makes permanent. A stray socket during
    maintenance is recoverable; a missing session is not.
    """
    try:
        if os.path.exists(MAINT_FLAG):
            return True
    except Exception:                                          # noqa: BLE001
        pass
    return FEED_MODE == "maintenance"


FEED_MODE = os.environ.get("OT_FEED_MODE", "service").strip().lower()
_VALID_FEED_MODES = ("service", "capture", "maintenance")
if FEED_MODE not in _VALID_FEED_MODES:
    # An unknown mode must not silently become "maintenance" (a box that never
    # feeds) NOR silently become "service" (a box on the wire during
    # maintenance). Fail to the DEFAULT and say so loudly.
    logging.getLogger(__name__).warning(
        "[feed-mode] OT_FEED_MODE=%r is not one of %s - falling back to "
        "'service'. Fix the unit/env; do not rely on this default.",
        FEED_MODE, ", ".join(_VALID_FEED_MODES))
    FEED_MODE = "service"
RECONNECT_MAX_S   = 60
VIX_SYMBOL        = os.environ.get("OT_DXFEED_VIX", "VIX")
VIX_INTERVALS     = ("1m", "1d")

# Backfill depth per interval: calendar days back from now that comfortably
# cover TIMEFRAMES count (RTH ~6.5h/day, ~78 5m bars, ~26 15m bars, ~7 1h bars).
# ── FEED.2 — the overnight (extended-hours) 1h stream ────────────────────────
# Stored under its OWN symbol so nothing that reads plain "1h" changes.
EXT_INTERVAL     = os.environ.get("OT_EXT_INTERVAL", "1h").strip()
EXT_STORE_SYMBOL = f"{INSTRUMENT}_EXT"
EXT_1H_ENABLED   = os.environ.get("OT_EXT_1H", "1").strip() not in ("0", "false", "")

BACKFILL_DAYS = {
    "1m":  1,      # today's session (plus yesterday if pre-open)
    "5m":  4,      # 100 bars ≈ 1.3 sessions -> 4 cal days covers weekends
    "15m": 6,      # 50 bars ≈ 2 sessions
    "1h":  16,     # 50 bars ≈ 8 sessions
    "1d":  30,     # 10 bars ≈ 2 weeks + margin
}


def _dxfeed_symbol() -> str:
    return os.environ.get("OT_DXFEED_SYMBOL", "").strip() or INSTRUMENT


def _explain_exc(e, _depth=0):
    """Flatten an exception (incl. ExceptionGroup / __cause__) to a readable line.
    v3.8 — asyncio TaskGroup wraps the real failure in an ExceptionGroup whose
    str() is just 'unhandled errors in a TaskGroup (1 sub-exception)', which hid
    XOM's actual stream-reject cause for two days."""
    if _depth > 5:
        return repr(e)
    parts = ["%s: %s" % (type(e).__name__, e)]
    subs = getattr(e, "exceptions", None)
    if subs:
        parts.append("[" + " | ".join(_explain_exc(x, _depth + 1) for x in subs) + "]")
    cause = getattr(e, "__cause__", None) or getattr(e, "__context__", None)
    if cause is not None and cause is not e:
        parts.append("<- caused by " + _explain_exc(cause, _depth + 1))
    return " ".join(parts)


def _base_symbol(event_symbol: str) -> str:
    """'QQQ{=5m}' -> 'QQQ'."""
    return (event_symbol or "").split("{")[0]


def _backfill_start(interval: str, now_et: Optional[datetime] = None) -> datetime:
    now_et = now_et or datetime.now(ET)
    days = BACKFILL_DAYS.get(interval, 4)
    if interval == "1m":
        # Today's session open; if pre-open, previous calendar day's open so the
        # most recent session is available (readers scope to one session).
        d = now_et.date()
        if now_et.time() < dtime(*SESSION_OPEN_HM):
            d = d - timedelta(days=1)
        return datetime.combine(d, dtime(*SESSION_OPEN_HM), tzinfo=ET)
    return now_et - timedelta(days=days)


# ─── SQLite store (WAL, one writer — this process) ────────────────────────────

class FeedStore:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # check_same_thread=False + an explicit lock (v3.3).
        # The store is constructed on the MAIN thread but every write
        # (_flush -> upsert_candles/heartbeat/commit) is driven from the asyncio
        # event-loop thread created by get_loop(). Python's sqlite3 rejects that
        # by default:
        #   ProgrammingError: SQLite objects created in a thread can only be
        #   used in that same thread.
        # which killed candle-feed on its first flush, every start (GOOGL,
        # 2026-07-13). We remain a SINGLE writer — the lock serializes access so
        # allowing cross-thread use is safe.
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS candles (
                symbol      TEXT NOT NULL,
                interval    TEXT NOT NULL,
                ts_epoch_ms INTEGER NOT NULL,
                open REAL, high REAL, low REAL, close REAL, volume REAL,
                PRIMARY KEY (symbol, interval, ts_epoch_ms)
            );""")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS feed_meta (
                symbol   TEXT NOT NULL,
                interval TEXT NOT NULL,
                last_write_epoch REAL NOT NULL,
                PRIMARY KEY (symbol, interval)
            );""")
        # ── v3.4: chain-marks transport (Option 1b) ──────────────────────────
        # chain_subs: single row WRITTEN BY THE BOT (options_chain v3.2) naming
        # the streamer symbols + expiry it wants live marks for. chain_marks:
        # latest-value Greeks/Quote per option symbol, WRITTEN BY THE FEED.
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS chain_subs (
                id            INTEGER PRIMARY KEY CHECK (id = 1),
                expiry        TEXT NOT NULL,
                symbols       TEXT NOT NULL,          -- JSON list
                updated_epoch REAL NOT NULL
            );""")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS chain_marks (
                streamer_symbol TEXT PRIMARY KEY,
                bid REAL, ask REAL,
                delta REAL, gamma REAL, theta REAL, vega REAL, iv REAL,
                updated_epoch REAL NOT NULL
            );""")
        self.conn.commit()

    def upsert_candles(self, rows: List[Tuple]):
        """rows: (symbol, interval, ts_ms, o, h, l, c, v). Last write wins."""
        if not rows:
            return
        with self._lock:
            self._upsert_candles_locked(rows)

    def _upsert_candles_locked(self, rows: List[Tuple]):
        self.conn.executemany(
            "INSERT OR REPLACE INTO candles "
            "(symbol, interval, ts_epoch_ms, open, high, low, close, volume) "
            "VALUES (?,?,?,?,?,?,?,?)", rows)
        now = _time.time()
        touched = {(r[0], r[1]) for r in rows}
        self.conn.executemany(
            "INSERT OR REPLACE INTO feed_meta (symbol, interval, last_write_epoch) "
            "VALUES (?,?,?)", [(s, i, now) for (s, i) in touched])

    def purge_poison(self) -> int:
        """Delete any poison rows already in the store (v3.2). Runs at feed
        startup so a box whose DB was poisoned before this guard existed
        self-heals on restart — no manual sqlite surgery across the fleet."""
        with self._lock:
            cur = self.conn.execute(
                "DELETE FROM candles WHERE open <= 0 OR high <= 0 OR low <= 0 "
                "OR close <= 0 OR ts_epoch_ms < ? OR ts_epoch_ms > ?",
                (TS_MS_MIN, _ts_ms_max()))
            self.conn.commit()
            n = cur.rowcount or 0
        if n:
            logger.warning("purged %d poison candle row(s) from the store", n)
        return n

    def heartbeat(self):
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO feed_meta (symbol, interval, last_write_epoch) "
                "VALUES ('__feed__','heartbeat',?)", (_time.time(),))

    def commit(self):
        with self._lock:
            self.conn.commit()

    # ── v3.4: chain-marks transport ───────────────────────────────────────────
    def read_chain_subs(self):
        """(expiry, [streamer_symbols]) requested by the bot, or ("", []).

        ⚠️ TERM.1 (2026-08-18): the returned symbol list is the FRONT expiry
        UNIONED with any auxiliary tenors. `chain_subs` is `CHECK (id = 1)` — a
        single row by design — so extra expiries ride in a SEPARATE table and
        the front-expiry contract is untouched. The returned `expiry` string
        still names the FRONT expiry only: every existing caller reads it that
        way and none of them changes.

        ⚠️ FAILS OPEN, DELIBERATELY. A missing, empty or malformed aux table
        returns the front expiry exactly as before. **This function decides what
        a live trading box subscribes to** — the auxiliary tenors are archival
        enrichment and must never be able to cost the bot its own chain.
        """
        with self._lock:
            row = self.conn.execute(
                "SELECT expiry, symbols FROM chain_subs WHERE id=1").fetchone()
        if not row:
            return "", []
        try:
            expiry = row[0] or ""
            syms = json.loads(row[1] or "[]")
        except (ValueError, TypeError):
            return "", []
        try:
            aux = self._read_chain_subs_aux()
            if aux:
                seen = set(syms)
                for s in aux:
                    if s not in seen:
                        seen.add(s)
                        syms.append(s)
        except Exception:                                      # noqa: BLE001
            pass          # archival enrichment never costs the bot its chain
        return expiry, syms

    def _read_chain_subs_aux(self):
        """Extra-tenor streamer symbols, or [] if the table is absent/stale.

        ⚠️ STALENESS BOUND. An aux row older than the front expiry's own update
        is a leftover from a previous session — subscribing to last week's
        strikes wastes socket budget against a measured ~40-session cap and
        pollutes `chain_marks` with contracts nothing reads.
        """
        cur = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='chain_subs_aux'")
        if not cur.fetchone():
            return []
        cutoff = _time.time() - AUX_MAX_AGE_S
        rows = self.conn.execute(
            "SELECT symbols FROM chain_subs_aux WHERE updated_epoch >= ?",
            (cutoff,)).fetchall()
        out = []
        for r in rows:
            try:
                out.extend(json.loads(r[0] or "[]"))
            except (ValueError, TypeError):
                continue
        return out

    def upsert_chain_quotes(self, rows):
        """rows: (streamer_symbol, bid, ask, epoch) — preserves greeks columns."""
        if not rows:
            return
        with self._lock:
            self.conn.executemany(
                "INSERT INTO chain_marks (streamer_symbol, bid, ask, updated_epoch) "
                "VALUES (?,?,?,?) ON CONFLICT(streamer_symbol) DO UPDATE SET "
                "bid=excluded.bid, ask=excluded.ask, "
                "updated_epoch=excluded.updated_epoch", rows)

    def upsert_chain_greeks(self, rows):
        """rows: (streamer_symbol, delta, gamma, theta, vega, iv, epoch) —
        preserves quote columns."""
        if not rows:
            return
        with self._lock:
            self.conn.executemany(
                "INSERT INTO chain_marks (streamer_symbol, delta, gamma, theta, "
                "vega, iv, updated_epoch) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(streamer_symbol) DO UPDATE SET "
                "delta=excluded.delta, gamma=excluded.gamma, theta=excluded.theta, "
                "vega=excluded.vega, iv=excluded.iv, "
                "updated_epoch=excluded.updated_epoch", rows)

    def clear_chain_marks(self):
        with self._lock:
            self.conn.execute("DELETE FROM chain_marks")
            self.conn.commit()

    def prune(self, symbol: str, interval: str, keep: int):
        with self._lock:
            self._prune_locked(symbol, interval, keep)

    def _prune_locked(self, symbol: str, interval: str, keep: int):
        self.conn.execute("""
            DELETE FROM candles WHERE symbol=? AND interval=? AND ts_epoch_ms NOT IN
            (SELECT ts_epoch_ms FROM candles WHERE symbol=? AND interval=?
             ORDER BY ts_epoch_ms DESC LIMIT ?)""",
            (symbol, interval, symbol, interval, keep))

    def bar_count(self, symbol: str, interval: str) -> int:
        with self._lock:
            cur = self.conn.execute(
                "SELECT COUNT(*) FROM candles WHERE symbol=? AND interval=?",
                (symbol, interval))
            return int(cur.fetchone()[0])

    def close(self):
        try:
            self.conn.commit()
            self.conn.close()
        except Exception:
            pass


# ─── The producer ──────────────────────────────────────────────────────────────

class CandleFeed:
    """Persistent single subscription -> in-memory last-write-wins buffer ->
    periodic flush to the shared store."""

    def __init__(self, store: FeedStore):
        self.store = store
        self.dx_symbol = _dxfeed_symbol()
        # (dxfeed_symbol, interval) -> store symbol name
        self.symbol_map: Dict[Tuple[str, str], str] = {}
        # (dx_sym, interval, start, extended_trading_hours)
        self.subs: List[Tuple[str, str, datetime, bool]] = []
        for tf in TIMEFRAMES.keys():
            self.subs.append((self.dx_symbol, tf, _backfill_start(tf), False))
            # v3.16 — the key now carries the EXTENDED-HOURS FLAG, because
            # (dx_symbol, interval) is NOT unique: FEED.2 subscribes the same
            # symbol+interval twice and the second registration used to
            # overwrite the first. Three-tuple, one entry per subscription.
            self.symbol_map[(self.dx_symbol, tf, False)] = INSTRUMENT
        for tf in VIX_INTERVALS:
            self.subs.append((VIX_SYMBOL, tf, _backfill_start(tf), False))
            self.symbol_map[(VIX_SYMBOL, tf, False)] = "VIX"

        # ── FEED.2 (2026-08-15) — THE OVERNIGHT STREAM ───────────────────────
        # ⚠️ THE TAPE WAS NEVER UNAVAILABLE. WE WERE ASKING DXFEED TO EXCLUDE IT.
        # `subscribe_candle(..., extended_trading_hours=False)` is the SDK
        # DEFAULT, and when it is False the SDK appends **`tho=true`**
        # (trading-hours-only) to the symbol: `QQQ{=1h,tho=true}`. Every
        # subscription this feed has ever made carried it.
        #
        # That single default is what produced `ext=0` on 28 of 29 boxes, an
        # RTH-only 1h store (252 bars = 36 sessions x 7), and LIQ.6's Asia and
        # London sections having nothing to build from. It is NOT the session
        # guard, NOT the warm lead, NOT S3, NOT an entitlement tier.
        #
        # ⚠️ A SEPARATE STREAM, NOT A FLAG ON THE EXISTING 1h. `1h` is read by
        # structure_analyzer's swings and S/R, by the pitchfork and its observer,
        # and by entry_snapshot. Flipping it in place would silently rebuild all
        # of them on 24h bars — the pitchfork is a v4.0 milestone and its forks
        # would change shape overnight with nothing announcing it. This lands
        # under its OWN store symbol so **no existing consumer moves at all**;
        # only the named-level frame reads it.
        if EXT_1H_ENABLED:
            self.subs.append((self.dx_symbol, EXT_INTERVAL,
                              _backfill_start(EXT_INTERVAL), True))
            self.symbol_map[(self.dx_symbol, EXT_INTERVAL, True)] = EXT_STORE_SYMBOL
        # ── v3.16 — COLLISION GUARD. REFUSE TO START ON A DUPLICATE ROUTE ───
        # The FEED.2 defect was not that someone wrote a wrong key; it was that
        # TWO subscriptions could legally resolve to the SAME store target and
        # nothing said so. Six days of stale 1h structure followed, fleet-wide,
        # with no error. A route table that can silently lose an entry must not
        # be allowed to start.
        # Two invariants, both cheap and both checked before a socket opens:
        #   1. no two SUBSCRIPTIONS share a map key (one would overwrite the
        #      other, which is exactly what happened)
        #   2. no two map keys point at the SAME (store_symbol, interval) —
        #      two live streams writing one table is a silent merge
        _seen_keys, _seen_targets = set(), {}
        for (_ds, _tf, _st, _ex) in self.subs:
            _k = (_ds, _tf, bool(_ex))
            if _k in _seen_keys:
                raise RuntimeError(
                    f"candle_feed: DUPLICATE SUBSCRIPTION KEY {_k} — two "
                    f"subscriptions resolve to one route and one would "
                    f"silently overwrite the other (the FEED.2 defect, "
                    f"2026-08-14..20). Refusing to start.")
            _seen_keys.add(_k)
            _tgt = (self.symbol_map.get(_k), _tf)
            if _tgt[0] is None:
                raise RuntimeError(
                    f"candle_feed: SUBSCRIPTION {_k} HAS NO ROUTE in "
                    f"symbol_map — its candles would be dropped. Refusing "
                    f"to start.")
            if _tgt in _seen_targets:
                raise RuntimeError(
                    f"candle_feed: TWO SUBSCRIPTIONS WRITE {_tgt} — "
                    f"{_seen_targets[_tgt]} and {_k}. One stream would "
                    f"silently merge into the other's table. Refusing to "
                    f"start.")
            _seen_targets[_tgt] = _k
        logger.info("candle_feed routes verified: %d subscription(s), "
                    "%d distinct store target(s)",
                    len(_seen_keys), len(_seen_targets))

        # buffer[(store_symbol, interval)][ts_ms] = row tuple
        self.buffer: Dict[Tuple[str, str], Dict[int, Tuple]] = {}
        self._unmapped_seen: set = set()   # v3.7: warn-once on unmapped candles
        self.backfill_logged: Dict[Tuple[str, str], bool] = {}
        # ── v3.4 chain-marks state (reset on every socket (re)connect) ────────
        self._chain_expiry: str = ""
        self._chain_subscribed: set = set()
        self._quotes_buf: Dict[str, tuple] = {}    # sym -> (sym,bid,ask,epoch)
        self._greeks_buf: Dict[str, tuple] = {}    # sym -> (sym,d,g,t,v,iv,epoch)

    def _interval_of(self, event_symbol: str) -> Optional[str]:
        """Map DXFeed's echoed candle symbol back to OUR config timeframe key.

        'AAPL{=5m}'            -> '5m'
        'AAPL{=5m,tho=true}'   -> '5m'    (attributes stripped)
        'AAPL{=m,tho=true}'    -> '1m'    (DXFeed canonicalizes 1m -> m)
        'AAPL{=h,tho=true}'    -> '1h'
        'AAPL{=d,tho=true}'    -> '1d'

        v3.7 — TWO bugs that each SILENTLY DROP EVERY CANDLE (feed stays 'active',
        authenticated, streaming, store takes ZERO writes; bots read yesterday's
        bars; no ORB range for today; fleet EXPIRED/UNKNOWN; not one error logged
        — recurred every morning 07-13/14/15):
        (1) DXFeed echoes the symbol back WITH ATTRIBUTES ('...,tho=true'); the
            old parser returned '5m,tho=true' and never matched symbol_map.
        (2) DXFeed CANONICALIZES a leading 1: we subscribe '1m'/'1h'/'1d', it
            echoes 'm'/'h'/'d'. 1m is what fetch_quote() reads (the bot's price).
        """
        if "{=" not in (event_symbol or ""):
            return None
        token = event_symbol.split("{=", 1)[1].rstrip("}")
        token = token.split(",", 1)[0].strip()      # drop ',tho=true' etc.
        return {"m": "1m", "h": "1h", "d": "1d", "s": "1s"}.get(token, token)

    @staticmethod
    def _is_ext_of(event_symbol: str) -> bool:
        """v3.16 — IS THIS ECHO FROM THE EXTENDED-HOURS SUBSCRIPTION?

        🔴 THE BUG THIS EXISTS FOR. FEED.2 subscribes the SAME dx symbol at the
        SAME interval twice — once RTH-only, once with extended_trading_hours —
        and registered both in `symbol_map` under `(dx_symbol, interval)`. The
        keys are identical, so the second assignment silently overwrote the
        first and EVERY 1h candle was routed to the EXT store symbol. Measured
        2026-08-20 across the fleet: plain `QQQ`/`SPX` 1h frozen at 2026-08-14
        while `*_EXT` 1h was current — SIX DAYS of stale higher-timeframe
        structure feeding structure_analyzer's swings and S/R, the pitchfork
        and its observer, and entry_snapshot. Nothing raised; BARS_STALE warned
        every five minutes with `refused=False` and the bots kept trading on
        08-14 bars.
        `tho=true` is the ONLY thing that distinguishes the two echoes, and
        `_interval_of` deliberately discards it. So read it here instead: the
        attribute the parser drops is exactly the attribute the router needs.
        """
        if "{=" not in (event_symbol or ""):
            return False
        attrs = event_symbol.split("{=", 1)[1].rstrip("}")
        return "tho=true" in attrs.replace(" ", "").lower()

    def _on_candle(self, c: Candle):
        ev_sym = getattr(c, "event_symbol", "")
        base = _base_symbol(ev_sym)
        interval = self._interval_of(ev_sym) or ""
        is_ext = self._is_ext_of(ev_sym)
        key_sym = self.symbol_map.get((base, interval, is_ext))
        if key_sym is None:
            # v3.7: NEVER drop a candle silently. This branch swallowed the whole
            # feed on 07-13/14/15 (unparsed interval) with no log anywhere. Warn
            # once per distinct unmapped key so a future echo-format change is
            # visible within one line instead of a wasted session.
            if ev_sym and (base, interval, is_ext) not in self._unmapped_seen:
                self._unmapped_seen.add((base, interval, is_ext))
                logger.warning(
                    "DROPPING candles: event_symbol=%r -> (base=%r, interval=%r, "
                    "ext=%r) NOT in symbol_map %r — storing nothing for it",
                    ev_sym, base, interval, is_ext,
                    sorted(self.symbol_map.keys()))
            return
        if c.time is None or c.open is None:
            return

        # ── POISON GUARD (v3.2) ───────────────────────────────────────────────
        # DXFeed intermittently emits a junk candle: timestamp at the signed
        # 32-bit rollover (2147483648xxx ms => year 2038) with all prices 0.0.
        # Observed live on GOOGL 2026-07-13 (1m, then 15m). It is fatal
        # downstream: fetch_quote() sorts by ts DESC, so the 2038 row wins, its
        # age computes NEGATIVE (passes the freshness check), and it returns
        # close=0.0. run_analysis() treats 0.0 as falsy -> "Could not fetch
        # current price" -> the tick loop dies EVERY TICK while the unit still
        # reports ACTIVE. Silent, total. Reject it at the door: bad data must
        # never enter the store.
        try:
            ts_ms = int(c.time)
            o, h, l, cl = float(c.open), float(c.high), float(c.low), float(c.close)
        except (TypeError, ValueError):
            return

        if not (TS_MS_MIN <= ts_ms <= _ts_ms_max()):
            logger.warning(
                "REJECTED poison candle %s %s: insane ts=%d (%.1f) — outside sane window",
                key_sym, interval, ts_ms, ts_ms / 1000.0)
            return
        if o <= 0 or h <= 0 or l <= 0 or cl <= 0:
            logger.warning(
                "REJECTED poison candle %s %s ts=%d: non-positive price "
                "(o=%.4f h=%.4f l=%.4f c=%.4f)", key_sym, interval, ts_ms, o, h, l, cl)
            return

        row = (key_sym, interval, ts_ms, o, h, l, cl,
               float(getattr(c, "volume", 0) or 0))
        self.buffer[(key_sym, interval)] = self.buffer.get((key_sym, interval), {})
        self.buffer[(key_sym, interval)][ts_ms] = row

    # ── v3.4: chain-marks handlers ─────────────────────────────────────────
    def _on_quote(self, q: Quote):
        sym = getattr(q, "event_symbol", "") or ""
        if not sym:
            return
        try:
            bid = float(q.bid_price or 0)
            ask = float(q.ask_price or 0)
        except (TypeError, ValueError):
            return
        self._quotes_buf[sym] = (sym, bid, ask, _time.time())

    def _on_greeks(self, g: Greeks):
        sym = getattr(g, "event_symbol", "") or ""
        if not sym:
            return
        try:
            row = (sym, float(g.delta or 0), float(g.gamma or 0),
                   float(g.theta or 0), float(g.vega or 0),
                   float(g.volatility or 0), _time.time())
        except (TypeError, ValueError):
            return
        self._greeks_buf[sym] = row

    async def _reconcile_chain_subs(self, streamer):
        """Every flush cycle: make the socket's Greeks/Quote subscriptions match
        what the bot requested via chain_subs. Expiry rollover unsubscribes all
        and clears the marks table (yesterday's 0DTE symbols are dead air)."""
        expiry, symbols = self.store.read_chain_subs()
        if not symbols:
            return
        if expiry != self._chain_expiry:
            if self._chain_subscribed:
                logger.info("chain marks: expiry rollover %s -> %s — resubscribing",
                            self._chain_expiry or "(none)", expiry)
                await streamer.unsubscribe_all(Greeks)
                await streamer.unsubscribe_all(Quote)
            self._chain_subscribed.clear()
            self._quotes_buf.clear()
            self._greeks_buf.clear()
            self.store.clear_chain_marks()
            self._chain_expiry = expiry
        new = [s for s in symbols if s not in self._chain_subscribed]
        if new:
            # v3.5: CHUNKED subscribes. An SPX 0DTE chain is hundreds of
            # strikes; one giant subscribe frame risks a websocket 1009
            # (message too long) that would bounce the ENTIRE socket —
            # candles included. 75 symbols per frame is comfortably small.
            for i in range(0, len(new), 75):
                chunk = new[i:i + 75]
                await streamer.subscribe(Greeks, chunk)
                await streamer.subscribe(Quote,  chunk)
            self._chain_subscribed.update(new)
            logger.info("chain marks: subscribed %d new symbols (%d total, expiry %s)",
                        len(new), len(self._chain_subscribed), expiry)

    def _flush(self):
        rows: List[Tuple] = []
        for bucket in self.buffer.values():
            rows.extend(bucket.values())
        self.buffer = {}
        self.store.upsert_candles(rows)
        # v3.4: chain marks ride the same flush cadence
        q, g = list(self._quotes_buf.values()), list(self._greeks_buf.values())
        self._quotes_buf.clear()
        self._greeks_buf.clear()
        self.store.upsert_chain_quotes(q)
        self.store.upsert_chain_greeks(g)
        self.store.heartbeat()
        self.store.commit()
        return len(rows) + len(q) + len(g)

    def _log_backfill_depth(self):
        """One-time per (symbol, interval): report depth vs required count so
        entitlement gaps surface in the journal (FIRST-RUN CHECKLIST #1)."""
        for (dx_sym, tf, _start, _ext) in self.subs:
            sym = self.symbol_map[(dx_sym, tf, bool(_ext))]
            if self.backfill_logged.get((sym, tf)):
                continue
            n = self.store.bar_count(sym, tf)
            need = TIMEFRAMES.get(tf, {}).get("candles", 0) if sym == INSTRUMENT else 1
            level = logging.INFO if n >= need else logging.WARNING
            logger.log(level, "backfill %s %s: %d bars in store (need %d)%s",
                       sym, tf, n, need, "" if n >= need else "  << SHORT — check entitlement")
            self.backfill_logged[(sym, tf)] = True

    @staticmethod
    def _idle_outside_session(once: bool) -> bool:
        """Should this run stand down because no session needs serving?

        ONE predicate, TWO call sites (the reconnect gate and the RTH-over
        break). v3.9 wrote the same condition inline in both places and v3.10
        had to patch both; a third caller would have had to remember a third
        time. It is a method so the two can never disagree again.

        THE DISTINCTION IS PURPOSE, NOT TIME — which is the whole lesson of
        2026-08-01..08-04. What the gate protects against is a box HOLDING a
        live DXLink subscription when there is no session to serve it: the
        maintenance wake that put 29 boxes on the wire for work needing no
        market data. A `--once` run holds nothing. It connects, pulls HISTORY
        from 09:30, flushes and exits, and history does not stop existing at
        16:00 — so gating it on the clock blocked the ONLY path the EOD candle
        retrieval has, silently, for two sessions.

        SERVICE MODE (once=False) is unchanged from v3.9 in every respect.

        ── FEED.1 (2026-08-15) — THE THIRD PURPOSE ────────────────────────────
        MAINTENANCE is HARD OFF and overrides everything, `--once` included.
        It exists because the operator needs a window where all 29 boxes can be
        up for fleet updates with nothing on the wire — and that CANNOT be a
        clock rule, because the overnight capture pass runs at the same hours
        and wants the opposite.

        ⚠️ IT ANNOUNCES ITSELF AT WARNING. The 2026-08-03/04 loss was a silent
        gate: `Feed idle — outside RTH` at INFO, then `0 bars`, then fourteen
        38-byte header-only CSVs, and DXFeed history is same-evening only so
        both sessions are gone. **A suppressed run must never be mistakable for
        a failed fetch**, so this says the mode by name and says the data is
        NOT being collected.
        """
        if _maintenance_now():
            if not getattr(CandleFeed, "_maint_said", False):
                CandleFeed._maint_said = True
                logger.warning(
                    "[feed-mode] MAINTENANCE - standing down completely, "
                    "%s. NO candles will be collected on this box until "
                    "OT_FEED_MODE is cleared. This is DELIBERATE, not a fetch "
                    "failure; if you expected tape, the mode is wrong.",
                    "including this --once run" if once else "service mode")
            return True
        return not is_rth() and not once

    async def run(self, once: bool = False):
        session = get_session()
        backoff = RECONNECT_MIN_S
        while True:
            # ── RTH GATE (2026-08-01) ─────────────────────────────────────────
            # Do not hold a DXLink socket when there is no session to serve it.
            #
            # WHY: this loop had no time gate at all — `Restart=always`, no timer
            # — so while a box was UP the feed subscribed continuously. That is
            # invisible on a normal day (phase_report stops the instances at EOD,
            # so nothing is running), but it means every MAINTENANCE wake put 29
            # boxes back on the wire at once for work that needs no market data.
            #
            # WHY THIS IS SAFE FOR CHAIN ARCHIVAL — the thing that made this
            # look risky. Greeks/Quote for the option chain ride this same
            # socket ("one producer, many readers"), so idling here also stops
            # draining chain_marks. But `analysis.chain_snapshot.snapshot()`
            # takes the chain as an ARGUMENT and is called from inside main.py's
            # tick loop — which ALREADY returns early on `not is_rth()`
            # (main.py:1268). Chain archival therefore only ever happens during
            # RTH. Gating here cannot cost a snapshot.
            #
            # The bot has had exactly this sleep-and-continue since it was
            # written; the feed simply never got the same treatment.
            #
            # LEAD-IN, not a hard 09:30: the bot's fetch_candles refuses on a
            # stale heartbeat, so a feed that connects exactly at the open serves
            # nothing for its first cycles. Connect FEED_WARM_LEAD_S early
            # (default 20 min, covering the 09:15 fleet wake) so the frames are
            # warm when the first tick asks.
            # v3.9 — `--once` IS EXEMPT. The gate below is about not HOLDING a
            # live socket when no session needs one. A one-shot backfill is the
            # opposite operation: it connects, pulls HISTORY from 09:30, flushes
            # and exits. History does not stop existing at 16:00, and this is the
            # only path the EOD candle retrieval has.
            # WHAT IT COST: the gate landed 2026-08-01 and `--once` was never
            # excluded, so from 08-03 every sat-out box woken by eod_backfill
            # entered this branch, slept 60s at a time until `timeout 200` killed
            # it, and wrote a HEADER-ONLY csv. Two sessions of sat-out tape, and
            # DXFeed history is same-evening only — permanent at midnight.
            # It logged INFO the whole time and nothing raised.
            if self._idle_outside_session(once):
                _until = seconds_until_rth_open()
                if _until > FEED_WARM_LEAD_S:
                    _nap = min(60.0, _until - FEED_WARM_LEAD_S)
                    logger.info(
                        f"Feed idle — outside RTH, no subscriptions held. "
                        f"Open in {_until/60:.0f} min (connecting "
                        f"{FEED_WARM_LEAD_S/60:.0f} min early). Sleeping "
                        f"{_nap:.0f}s."
                    )
                    await asyncio.sleep(_nap)
                    continue
                # inside the lead-in window: fall through and connect warm
            try:
                async with DXLinkStreamer(session) as streamer:
                    # v3.4: fresh socket — chain subscriptions must be rebuilt
                    self._chain_expiry = ""
                    self._chain_subscribed.clear()
                    # v3.8: subscribe each (symbol, tf) INDEPENDENTLY. A single
                    # failing subscribe_candle used to throw out of the whole
                    # `async with`, killing the ENTIRE stream — so one bad symbol
                    # or timeframe (e.g. an entitlement gap on XOM) took down all
                    # candles, for two days, with only a wrapped "unhandled errors
                    # in a TaskGroup" to show for it. Now a failure is logged with
                    # its REAL cause (see _explain_exc) and skipped.
                    ok_subs = 0
                    for (dx_sym, tf, start, ext) in self.subs:
                        try:
                            await streamer.subscribe_candle(
                                [dx_sym], tf, start_time=start,
                                extended_trading_hours=ext)
                            logger.info("subscribed %s %s from %s%s", dx_sym, tf,
                                        start.isoformat(),
                                        "  [EXTENDED HOURS]" if ext else "")
                            ok_subs += 1
                        except Exception as sub_e:
                            logger.error("SUBSCRIBE FAILED %s %s: %s — continuing without it",
                                         dx_sym, tf, _explain_exc(sub_e))
                    if ok_subs == 0:
                        raise RuntimeError("no candle subscriptions succeeded")
                    logger.info("%d/%d candle subscriptions live", ok_subs, len(self.subs))
                    await self._reconcile_chain_subs(streamer)
                    backoff = RECONNECT_MIN_S
                    last_flush = 0.0
                    last_prune = _time.time()
                    quiet_since: Optional[float] = None
                    while True:
                        try:
                            c = await asyncio.wait_for(streamer.get_event(Candle), timeout=1.0)
                            self._on_candle(c)
                            quiet_since = None
                        except asyncio.TimeoutError:
                            if quiet_since is None:
                                quiet_since = _time.monotonic()
                        # v3.4: drain any queued Greeks/Quote events, non-blocking
                        while True:
                            g = streamer.get_event_nowait(Greeks)
                            if g is None:
                                break
                            self._on_greeks(g)
                        while True:
                            q = streamer.get_event_nowait(Quote)
                            if q is None:
                                break
                            self._on_quote(q)
                        now = _time.monotonic()
                        if now - last_flush >= FLUSH_INTERVAL_S:
                            await self._reconcile_chain_subs(streamer)
                            n = self._flush()
                            last_flush = now
                            if n:
                                logger.debug("flushed %d bars", n)

                            # v3.9 — SESSION IS OVER: drop the socket. The gate at
                            # the top of the reconnect loop only decides whether
                            # to CONNECT; without this the feed would stream on
                            # past 16:00 for as long as the box happened to stay
                            # up. That is the case that matters — the operator
                            # must be able to FORGET a box is up and have it not
                            # be a problem, which is this project's standing rule
                            # about anything depending on someone remembering.
                            # Rides the existing flush cadence rather than adding
                            # a timer: we are already here, once per cycle.
                            # Flushed first (above), so no buffered bar is lost.
                            # v3.9 — `and not once` here too, and this one is the
                            # blocker a naive fix would have missed. This break
                            # sits ABOVE the --once drain-exit, so a one-shot run
                            # outside RTH would connect, break out on its first
                            # flush cycle, return to the outer loop, hit the gate
                            # again and sleep — the same hang, one layer down,
                            # with the backfill still undrained. Both sites had
                            # to move together or neither works.
                            if self._idle_outside_session(once):
                                logger.info(
                                    "RTH over — closing DXLink socket and "
                                    "releasing all subscriptions until the next "
                                    "session."
                                )
                                break
                            self._log_backfill_depth()
                            if once and quiet_since is not None and (now - quiet_since) > 8.0:
                                logger.info("--once: backfill drained, exiting")
                                return
                        # ── FEED.3 (2026-08-15) — PRUNING IS OFF BY DEFAULT ──
                        # ⚠️ THE BOUND WAS SIZED FOR THE LIVE LOOP AND KEPT
                        # SILENTLY CONSTRAINING ANALYTICAL CONSUMERS THAT
                        # ARRIVED LATER. It has now bitten twice: PF.2 found the
                        # boxes held 84 daily bars while the engine was handed
                        # 10 ("the history was never missing - the frame was"),
                        # and LIQ.6's 10-day section lookback landed on exactly
                        # the 240-row 1h ceiling with ZERO margin.
                        #
                        # AND IT WAS NEVER BUYING ANYTHING. Measured: a FULL
                        # YEAR of every interval, extended hours, is **54 MB per
                        # box** - on an 8 GB root. Ten days is 1.5 MB. The
                        # pruner was tidiness, not capacity.
                        #
                        # Operator's call: no pruning. The local store keeps
                        # what it collects; S3 is the archive and the weekend
                        # reporting reads the bucket, so the box no longer has
                        # to be the deep copy of anything.
                        # ⚠️ THE POISON PURGE IS UNTOUCHED AND MUST STAY - it
                        # deletes BAD rows (non-positive prices, 2038-stamped
                        # DXFeed rollover junk), not OLD ones. Different method,
                        # different purpose.
                        if PRUNE_KEEP_ROWS and _time.time() - last_prune >= PRUNE_EVERY_S:
                            for (dx_sym, tf, _s, _e) in self.subs:
                                sym = self.symbol_map[(dx_sym, tf, bool(_e))]
                                self.store.prune(sym, tf, PRUNE_KEEP_ROWS)
                            self.store.commit()
                            last_prune = _time.time()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._flush()
                # v3.8: UNWRAP. asyncio TaskGroup raises an ExceptionGroup whose
                # str() is only "unhandled errors in a TaskGroup (1 sub-exception)"
                # — the real DXFeed cause is in .exceptions and was thrown away,
                # leaving XOM in a 60s reconnect loop with NO diagnosable reason
                # for two days (07-13 -> 07-15).
                logger.error("feed stream error: %s — reconnecting in %ds",
                             _explain_exc(e), backoff)
                logger.debug("feed stream traceback:\n%s",
                             "".join(traceback.format_exception(type(e), e, e.__traceback__)))
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, RECONNECT_MAX_S)


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true",
                    help="backfill, flush, exit (smoke test)")
    ap.add_argument("--db", default=None, help="override store path")
    args = ap.parse_args()

    if args.db:
        os.environ["OT_FEED_DB"] = args.db
    store = FeedStore(feed_db_path())
    logger.info("candle_feed v3.8 — store=%s symbol=%s (dxfeed=%s) vix=%s",
                feed_db_path(), INSTRUMENT, _dxfeed_symbol(), VIX_SYMBOL)
    store.purge_poison()   # v3.2: self-heal any pre-existing poison rows

    feed = CandleFeed(store)
    loop = get_loop()
    fut = asyncio.run_coroutine_threadsafe(feed.run(once=args.once), loop)
    try:
        fut.result()          # blocks for service lifetime
    except KeyboardInterrupt:
        fut.cancel()
    finally:
        store.close()


if __name__ == "__main__":
    main()
