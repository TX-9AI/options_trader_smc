"""
data/options_chain.py — Options chain data from TastyTrade SDK.
v3.3  2026-08-18  TERM.1: publish a NARROW ATM BAND for the weekly and
        monthly expiries so TERM STRUCTURE becomes computable. Every snapshot
        to date carried a SINGLE expiry equal to the session date - skew and IV
        level available, term slope impossible - and chain history cannot be
        retrieved afterwards, so each day collected single-expiry has no term
        structure permanently.
        ~9 STRIKES PER TENOR, NOT A CHAIN. Term structure needs ATM IV out at a
        date, not walls/GEX/a delta ladder. Full chains x3 would be ~750
        subs/box against the ~40 concurrent-session cap v3.1 measured - the
        constraint that removed the per-box streamer entirely - and SPX has
        already been OOM-KILLED at 419 MB on chain volume. ATM bands are ~270.
        PLACED AFTER THE CHAIN IS BUILT because spot is not known earlier;
        `chain.spot_price` is derived from the ATM strike further up, and an
        earlier call would have banded around 0.0 and published the lowest
        strikes on the board.
        WRITES ONLY TO `chain_subs_aux`. `chain_subs` is CHECK (id = 1) and
        belongs to the bot's own expiry; candle_feed v3.15 unions the aux rows
        and FAILS OPEN if this never runs or writes garbage.
v3.2 — 2026-07-13 — STORE READER (Option 1b — supersedes v3.1's own streamer).
        Live fleet test of v3.1 measured TastyTrade's unpublished session cap
        near ~40 concurrent: 29 candle-feeds + 29 per-box chain streamers do
        NOT fit (only ~6-11 chain streamers were admitted; the rest sat in
        backoff all afternoon). This release removes DXLink from the bot
        process ENTIRELY: candle_feed v3.4 carries the Greeks/Quote
        subscriptions on its existing socket and publishes latest values to a
        chain_marks table in the shared store; this module (a) publishes the
        desired streamer-symbol set + expiry to chain_subs, and (b) reads
        chain_marks like every other store consumer. Fleet steady state:
        29 sessions total — the number proven safe for weeks. Kept from v3.1:
        structure cache (OT_CHAIN_STRUCT_REFRESH_S), staleness ceiling
        (OT_CHAIN_STALE_S — stale marks are refused, never served), and the
        zero-mark FAIL-LOUD (bootstrap-aware: quiet for the first ticks after
        publishing subs while the feed populates). REQUIRES candle_feed v3.4
        on the box — fails loud with a version hint if the tables are absent.
v3.1 — 2026-07-13 — PERSISTENT CHAIN STREAMER (superseded same day; header kept
        for the record). Fail-loud + structure cache introduced here survive.
        The old code opened a NEW DXLinkStreamer websocket on EVERY fetch_chain()
        call — one full REST-token + connect + auth + subscribe + teardown cycle
        per 15 s tick per box. Across the fleet that saturated TastyTrade's
        (unpublished) concurrent-session pool: DXLink returned
        'user sessions has exceeded the configured limit' roughly once per tick
        on 24/29 boxes, quotes/Greeks came back empty, every contract kept
        mark=0.0, the mark>0.05 liquidity filters rejected every strike in every
        regime, and the fleet took ZERO trades on 2026-07-13 while logging a
        plausible-looking "no setup" day. Changes:
        1. ONE long-lived DXLinkStreamer per process (lazy connect on the shared
           tasty_client loop thread, held via AsyncExitStack). Subscriptions are
           RECONCILED (only never-seen symbols subscribed; expiry rollover
           unsubscribes all and resets). Steady state: 2 sessions/box
           (candle-feed + this), ZERO churn.
        2. Reconnect with EXPONENTIAL BACKOFF (5s → 60s cap) on stream failure —
           a saturated pool is never hammered at tick cadence again (the old
           retry-every-15s kept the pool full and made the outage self-sustaining).
        3. Latest-value Greeks/Quote maps persist across ticks (each tick drains
           pending events non-blocking; only never-seen symbols block briefly).
           If the stream is DOWN and the last event is older than
           OT_CHAIN_STALE_S, fetch_chain returns None — stale marks are never
           served as fresh (an open position priced off dead marks would trip
           the -25% floor on garbage).
        4. FAIL-LOUD: a built chain in which NO contract has mark>0 returns None
           with an ERROR log instead of a structurally-valid corpse. Silent
           zero-mark chains are what hid this outage for five hours.
        5. Chain STRUCTURE (REST strike list) is cached OT_CHAIN_STRUCT_REFRESH_S
           (default 30 min) — the 0DTE strike set is static intraday; only
           Greeks/marks need per-tick freshness, and those ride the stream.
        Env knobs: OT_CHAIN_STRUCT_REFRESH_S=1800 · OT_CHAIN_INIT_COLLECT_S=10 ·
        OT_CHAIN_RECONNECT_BASE_S=5 · OT_CHAIN_RECONNECT_MAX_S=60 ·
        OT_CHAIN_STALE_S=120.
v3.0 — 2026-07-03 — delta-band sweep selection (caller passes a strength-scaled
        target delta); ORB nearest-strike snap breaks toward higher/lower delta.
v3.0 — 2026-07-10 — repo-wide v3.0 bump: Yahoo-Finance purge & data stream
        mapping optimization (all market data now flows from the single
        shared TastyTrade candle feed — see data/candle_feed.py). No logic
        change in this file.

Chain fetching:  get_option_chain(session, symbol) → dict[date, list[Option]]
Greeks/marks:    read from the store's chain_marks table (candle_feed v3.4 owns
                 the one DXLink socket and publishes latest values)

Workflow:
  1. get_option_chain() returns all Option objects (no pricing)
  2. Filter to today's expiry (0DTE)
  3. Publish desired symbols to chain_subs; read Greeks/Quotes from chain_marks
  4. Build OptionsChain with fully populated OptionContract objects
"""

import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from types import SimpleNamespace
from datetime import date, datetime
from typing import Optional, List, Dict
from decimal import Decimal

from tastytrade.instruments import get_option_chain, Option as TTOption, OptionType

from data.tasty_client import get_session, run_async, TastyClientError
from config import (
    INSTRUMENT, STRIKE_INCREMENT, CONTRACT_MULTIPLIER,
    SWEEP_DELTA_TOLERANCE, ORB_STRIKE_DELTA_BIAS
)
from utils.math_utils import round_to_strike, floor_to_strike, ceil_to_strike

logger = logging.getLogger(__name__)

# ── transport knobs (env-overridable, OT_ convention) ─────────────────────────
OT_CHAIN_STRUCT_REFRESH_S = float(os.environ.get("OT_CHAIN_STRUCT_REFRESH_S", "1800"))
OT_CHAIN_STALE_S          = float(os.environ.get("OT_CHAIN_STALE_S",          "120"))
OT_CHAIN_BOOTSTRAP_S      = float(os.environ.get("OT_CHAIN_BOOTSTRAP_S",      "30"))

def _feed_db_path() -> str:
    """Same resolution as data/candle_feed.feed_db_path (kept import-free so this
    module never drags the feed's SDK surface into the bot process)."""
    p = os.environ.get("OT_FEED_DB")
    if p:
        return os.path.expanduser(p)
    return os.path.expanduser("~/options-trader/data/feed_store.db")


@dataclass
class OptionContract:
    """A single option contract with pricing and greeks."""
    symbol:         str     = ""    # OCC symbol
    underlying:     str     = ""
    expiry:         str     = ""    # YYYY-MM-DD
    option_type:    str     = ""    # "C" or "P"
    strike:         float   = 0.0
    bid:            float   = 0.0
    ask:            float   = 0.0
    mark:           float   = 0.0
    delta:          float   = 0.0
    gamma:          float   = 0.0
    theta:          float   = 0.0
    vega:           float   = 0.0
    iv:             float   = 0.0
    open_interest:  int     = 0
    volume:         int     = 0
    streamer_symbol: str    = ""    # DXFeed streamer symbol


@dataclass
class OptionsChain:
    """Full 0DTE chain snapshot."""
    underlying:     str = ""
    expiry:         str = ""
    spot_price:     float = 0.0
    iv_rank:        float = 0.0
    calls:          List[OptionContract] = field(default_factory=list)
    puts:           List[OptionContract] = field(default_factory=list)


class OptionsChainFetcher:
    """
    Fetches the 0DTE options chain from TastyTrade and populates
    Greeks/marks from the shared store (chain_marks, fed by candle_feed v3.4).

    v3.2: pure STORE READER. The feed (candle_feed v3.4) owns the one DXLink
    socket; this class publishes the desired symbol set to chain_subs and reads
    latest marks from chain_marks. No async, no websockets, no sessions.
    """

    def __init__(self):
        # chain-structure cache: symbol -> (monotonic_fetched, chain_map)
        self._struct_cache: Dict[str, tuple] = {}
        # last-published subscription request (avoid rewriting an unchanged row)
        self._published: tuple = ("", frozenset())
        self._published_at: float = 0.0        # wall time of last publish
        self._db_ro = None                     # cached read-only connection

    def fetch_chain(self, symbol: str = INSTRUMENT,
                    expiry: Optional[str] = None) -> Optional[OptionsChain]:
        """
        Fetch the 0DTE options chain with Greeks and marks.

        Args:
            symbol: Underlying symbol (QQQ, SPY, SPX)
            expiry: YYYY-MM-DD — defaults to today (0DTE)

        Returns:
            OptionsChain or None on failure
        """
        today      = date.today()
        target_date = date.fromisoformat(expiry) if expiry else today
        today_str  = target_date.isoformat()

        try:
            session = get_session()

            # Step 1: chain STRUCTURE (REST) — cached; the 0DTE strike set is
            # static intraday. v3.1: was fetched every tick for no benefit.
            chain_map = self._get_chain_structure(session, symbol)

            if not chain_map:
                logger.warning(f"Empty option chain for {symbol}")
                return None

            # Step 2: Find today's expiration
            options_today: List[TTOption] = chain_map.get(target_date, [])

            if not options_today:
                # Try to find the nearest available expiry
                available = sorted(chain_map.keys())
                future    = [d for d in available if d >= target_date]
                if future:
                    target_date   = future[0]
                    today_str     = target_date.isoformat()
                    options_today = chain_map[target_date]
                    logger.info(f"No 0DTE for {today}, using nearest: {today_str}")
                else:
                    logger.warning(f"No options expiring on or after {today_str}")
                    return None

            logger.info(f"Found {len(options_today)} options for {symbol} {today_str}")

            # Step 3: Build OptionContract list (no pricing yet)
            calls_raw: List[OptionContract] = []
            puts_raw:  List[OptionContract] = []

            for opt in options_today:
                oc = OptionContract(
                    symbol       = opt.symbol,
                    underlying   = symbol,
                    expiry       = today_str,
                    option_type  = "C" if opt.option_type == OptionType.CALL else "P",
                    strike       = float(opt.strike_price),
                    streamer_symbol = opt.streamer_symbol or "",
                )
                if opt.option_type == OptionType.CALL:
                    calls_raw.append(oc)
                else:
                    puts_raw.append(oc)

            # Step 4: publish subs + read Greeks/quotes from the store (v3.2)
            streamer_syms = [
                oc.streamer_symbol for oc in calls_raw + puts_raw
                if oc.streamer_symbol
            ]

            if streamer_syms:
                greeks_map, quote_map = self._fetch_greeks_and_quotes(
                    session, streamer_syms, expiry=today_str
                )
                self._apply_market_data(calls_raw, greeks_map, quote_map)
                self._apply_market_data(puts_raw,  greeks_map, quote_map)

            # Step 5: Sort by strike
            calls_raw.sort(key=lambda c: c.strike)
            puts_raw.sort(key=lambda c: c.strike)

            chain = OptionsChain(
                underlying = symbol,
                expiry     = today_str,
                calls      = calls_raw,
                puts       = puts_raw,
            )

            # Populate spot_price from ATM call (nearest delta to 0.50)
            liquid_calls = [c for c in chain.calls if c.delta > 0 and c.mark > 0]
            if liquid_calls:
                try:
                    atm = min(liquid_calls, key=lambda c: abs(c.delta - 0.50))
                    chain.spot_price = atm.strike
                except Exception:
                    pass

            # v3.1 FAIL-LOUD: a chain with zero live marks is a corpse, not data.
            # Serving it lets every liquidity filter reject every strike while
            # the logs look like a quiet no-setup day (2026-07-13). Callers
            # already handle None correctly; None is also strictly safer for an
            # OPEN position than zero marks (premium=0 would trip the -25%
            # floor on garbage).
            if not any(c.mark > 0 for c in chain.calls + chain.puts):
                if self._in_bootstrap():
                    logger.info(
                        f"Chain warming: {symbol} {today_str} — subs published "
                        f"{time.time() - self._published_at:.0f}s ago, waiting "
                        f"for the feed to populate chain_marks"
                    )
                else:
                    logger.error(
                        f"Chain FAIL-LOUD: {symbol} {today_str} built with ZERO "
                        f"live marks ({len(chain.calls)}C/{len(chain.puts)}P) — "
                        f"feed marks absent/stale; returning None instead of a "
                        f"corpse (is candle-feed v3.4 healthy?)"
                    )
                return None

            logger.info(
                f"Chain built: {symbol} {today_str} "
                f"calls={len(chain.calls)} puts={len(chain.puts)} "
                f"spot~=${chain.spot_price:.0f}"
            )

            # ── TERM.1 (2026-08-18) — AUXILIARY TENORS, ARCHIVAL ONLY ────────
            # Publish a NARROW ATM BAND for the weekly and monthly so TERM
            # STRUCTURE becomes computable. Every snapshot to date carried a
            # SINGLE expiry equal to the session date, which leaves skew and IV
            # level available and the term slope impossible — and chain history
            # cannot be retrieved afterwards, so a day collected single-expiry
            # has no term structure permanently.
            # ⚠️ PLACED HERE, AFTER THE CHAIN IS BUILT, BECAUSE SPOT IS NOT
            # KNOWN EARLIER. `chain.spot_price` is derived from the ATM strike
            # further up this function; an earlier call site would have banded
            # around 0.0 and published the lowest strikes on the board.
            # ⚠️ ~9 STRIKES PER TENOR, NOT A CHAIN. Term structure needs ATM IV
            # out at a date — not walls, GEX or a delta ladder. Full chains x3
            # would be ~750 subs/box against the ~40 concurrent-session cap
            # v3.1 measured (the constraint that removed the per-box streamer
            # entirely), and SPX has already been OOM-KILLED at 419 MB on chain
            # volume. ATM bands are ~270 and clear both.
            # ⚠️ WRITES ONLY TO `chain_subs_aux`. `chain_subs` is CHECK (id = 1)
            # and belongs to the bot's own expiry; nothing here can change what
            # the trading path subscribes to, and candle_feed v3.15 fails open
            # if this never runs or writes garbage.
            try:
                from analysis.tenor_publish import publish_aux_tenors
                _aux = publish_aux_tenors(_feed_db_path(), chain_map,
                                          float(chain.spot_price or 0),
                                          target_date)
                if _aux:
                    logger.info("[tenor] aux ATM bands: %s",
                                ", ".join(f"{k}={v}" for k, v in _aux.items()))
            except Exception:                                  # noqa: BLE001
                pass          # archival enrichment never touches the chain path

            return chain

        except Exception as e:
            logger.error(f"Failed to fetch chain for {symbol}: {e}")
            return None

    def _get_chain_structure(self, session, symbol: str):
        """v3.1 — REST strike-list, cached OT_CHAIN_STRUCT_REFRESH_S. On a REST
        failure with a warm cache, serve the cache and warn (structure is
        static intraday; marks ride the stream and stay fresh regardless)."""
        now = time.monotonic()
        cached = self._struct_cache.get(symbol)
        if cached and (now - cached[0]) < OT_CHAIN_STRUCT_REFRESH_S:
            return cached[1]
        try:
            chain_map = run_async(get_option_chain(session, symbol))
            # FRC.3 — the VENUE'S price grid, fetched ONCE PER SYMBOL PER
            # PROCESS. Static instrument metadata, not a quote.
            # ⚠️ THE GUARD IS THE POINT. The first version had this comment and
            # NO CACHE CHECK, so it fired an extra SDK call on EVERY
            # fetch_chain() — and fetch_chain is called from three places in the
            # tick loop. That is hundreds of needless API calls per box per
            # session and real rate-limit exposure, on a live path, described by
            # a comment that claimed the opposite.
            # Best-effort: a failure here must never stop a chain fetch, and a
            # failed attempt is remembered so it is not retried every tick
            # either — a broken fetch must not become the same hot loop.
            try:
                from execution.tick_size import (cache_venue_rule,
                                                 mark_fetch_failed,
                                                 needs_venue_rule)
                if needs_venue_rule(symbol):
                    from tastytrade.instruments import NestedOptionChain
                    # `get`, not `a_get` — this SDK build has no `a_get`, and
                    # `get` is a COROUTINE despite the sync-looking name
                    # (inspect.iscoroutinefunction is True), so it goes through
                    # run_async like every other SDK call here. Both verified
                    # against the installed package; either mistake raises into
                    # the except and falls back to the PENNY_CLASSES guess
                    # FOREVER, silently.
                    _noc = run_async(NestedOptionChain.get(session, symbol))
                    _noc = _noc[0] if isinstance(_noc, list) and _noc else _noc
                    if not cache_venue_rule(symbol, getattr(_noc, "tick_sizes", None)):
                        mark_fetch_failed(symbol)
            except Exception as _tex:                          # noqa: BLE001
                try:
                    from execution.tick_size import mark_fetch_failed
                    mark_fetch_failed(symbol)
                except Exception:                              # noqa: BLE001
                    pass
                logger.debug("tick-size fetch skipped for %s: %s", symbol, _tex)
            if chain_map:
                self._struct_cache[symbol] = (now, chain_map)
            return chain_map
        except Exception as e:
            if cached:
                logger.warning(f"Chain structure refresh failed ({e}) — serving "
                               f"cached structure ({now - cached[0]:.0f}s old)")
                return cached[1]
            raise

    def _fetch_greeks_and_quotes(
        self,
        session,
        streamer_symbols: List[str],
        expiry: str = ""
    ) -> tuple:
        """
        v3.2 — publish the desired symbol set to chain_subs (only when it
        changes), then read latest Greeks/Quotes from chain_marks. Rows older
        than OT_CHAIN_STALE_S are refused. Returns (greeks_map, quote_map)
        shaped exactly like the old streamer maps (attribute access), so
        _apply_market_data is unchanged.
        """
        self._publish_desired_subs(expiry, streamer_symbols)
        return self._read_marks(streamer_symbols)

    def _publish_desired_subs(self, expiry: str, streamer_symbols: List[str]):
        want = (expiry, frozenset(streamer_symbols))
        if want == self._published:
            return
        try:
            conn = sqlite3.connect(_feed_db_path(), timeout=3.0)
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS chain_subs (
                        id            INTEGER PRIMARY KEY CHECK (id = 1),
                        expiry        TEXT NOT NULL,
                        symbols       TEXT NOT NULL,
                        updated_epoch REAL NOT NULL
                    );""")
                conn.execute(
                    "INSERT OR REPLACE INTO chain_subs (id, expiry, symbols, "
                    "updated_epoch) VALUES (1, ?, ?, ?)",
                    (expiry, json.dumps(sorted(streamer_symbols)), time.time()))
                conn.commit()
            finally:
                conn.close()
            self._published = want
            self._published_at = time.time()
            logger.info(f"Chain subs published: {len(streamer_symbols)} symbols, "
                        f"expiry {expiry} — feed will subscribe within a flush cycle")
        except Exception as e:
            logger.warning(f"Chain subs publish failed: {e}")

    def _ro_conn(self):
        if self._db_ro is None:
            self._db_ro = sqlite3.connect(
                f"file:{_feed_db_path()}?mode=ro", uri=True, timeout=3.0)
        return self._db_ro

    def _read_marks(self, streamer_symbols: List[str]) -> tuple:
        greeks_map: Dict[str, object] = {}
        quote_map:  Dict[str, object] = {}
        try:
            floor = time.time() - OT_CHAIN_STALE_S
            cur = self._ro_conn().execute(
                "SELECT streamer_symbol, bid, ask, delta, gamma, theta, vega, iv,"
                " updated_epoch FROM chain_marks WHERE updated_epoch >= ?", (floor,))
            rows = {r[0]: r for r in cur.fetchall()}
        except sqlite3.OperationalError as e:
            # table absent (feed still on <= v3.3) or db missing entirely
            self._db_ro = None
            logger.error(f"chain_marks unreadable ({e}) — is candle_feed v3.4 "
                         f"running on this box?")
            return {}, {}
        except Exception as e:
            self._db_ro = None
            logger.warning(f"chain_marks read failed: {e}")
            return {}, {}

        for sym in streamer_symbols:
            r = rows.get(sym)
            if r is None:
                continue
            _, bid, ask, delta, gamma, theta, vega, iv, _ep = r
            if (bid or 0) > 0 or (ask or 0) > 0:
                quote_map[sym] = SimpleNamespace(
                    event_symbol=sym, bid_price=bid or 0.0, ask_price=ask or 0.0)
            if any((delta, gamma, theta, vega, iv)):
                greeks_map[sym] = SimpleNamespace(
                    event_symbol=sym, delta=delta or 0.0, gamma=gamma or 0.0,
                    theta=theta or 0.0, vega=vega or 0.0, volatility=iv or 0.0)
        return greeks_map, quote_map

    def _in_bootstrap(self) -> bool:
        """True during the grace window right after publishing a new sub set —
        the feed needs a flush cycle or two to subscribe and populate."""
        return (time.time() - self._published_at) < OT_CHAIN_BOOTSTRAP_S

    def _apply_market_data(
        self,
        contracts: List[OptionContract],
        greeks_map: Dict[str, object],
        quote_map:  Dict[str, object]
    ):
        """Apply Greeks and Quote data to OptionContract objects."""
        for oc in contracts:
            sym = oc.streamer_symbol

            greek = greeks_map.get(sym)
            if greek:
                oc.delta = float(greek.delta or 0)
                oc.gamma = float(greek.gamma or 0)
                oc.theta = float(greek.theta or 0)
                oc.vega  = float(greek.vega  or 0)
                oc.iv    = float(greek.volatility or 0)

            quote = quote_map.get(sym)
            if quote:
                bid = float(quote.bid_price or 0)
                ask = float(quote.ask_price or 0)
                oc.bid  = bid
                oc.ask  = ask
                oc.mark = (bid + ask) / 2 if bid > 0 and ask > 0 else (bid or ask)

    # ─── Strike Selection ─────────────────────────────────────────────────────

    def select_orb_strike(self, chain: OptionsChain, direction: str,
                           target_strike: int,
                           delta_bias: str = ORB_STRIKE_DELTA_BIAS
                           ) -> Optional[OptionContract]:
        """Nearest liquid strike to target_strike. When strikes bracket the target
        equally, break toward the higher- (more ITM/participation) or lower-
        (further OTM) |delta| per delta_bias."""
        contracts = chain.calls if direction == "long" else chain.puts
        candidates = [c for c in contracts if c.mark > 0.05]
        if not candidates:
            logger.warning("No liquid contracts in chain")
            return None
        min_dist = min(abs(c.strike - target_strike) for c in candidates)
        nearest = [c for c in candidates
                   if abs(c.strike - target_strike) <= min_dist + 1e-6]
        if len(nearest) == 1:
            best = nearest[0]
        elif delta_bias == "lower":
            best = min(nearest, key=lambda c: abs(c.delta))
        else:  # "higher" — more ITM / more directional participation
            best = max(nearest, key=lambda c: abs(c.delta))
        logger.info(
            f"ORB strike: {best.option_type} {best.strike} "
            f"mark=${best.mark:.2f} delta={best.delta:.3f} (bias={delta_bias})"
        )
        return best

    def select_sweep_strike(self, chain: OptionsChain,
                             direction: str,
                             target_delta: float,
                             tolerance: float = SWEEP_DELTA_TOLERANCE
                             ) -> Optional[OptionContract]:
        """Select the OTM strike whose |delta| is nearest target_delta (the caller
        scales target_delta by reversal strength). Prefers strikes within
        +/- tolerance of the target; falls back to the nearest available."""
        pool = chain.calls if direction == "long" else chain.puts
        liquid = [c for c in pool if c.mark > 0.05 and 0.0 < abs(c.delta) <= 0.55]
        if not liquid:
            return None
        band = [c for c in liquid if abs(abs(c.delta) - target_delta) <= tolerance]
        pick_from = band if band else liquid
        best = min(pick_from, key=lambda c: abs(abs(c.delta) - target_delta))
        logger.info(
            f"Sweep strike: {best.option_type} {best.strike} "
            f"mark=${best.mark:.2f} delta={best.delta:.3f} "
            f"(target={target_delta:.2f}{'' if band else ', band empty->nearest'})"
        )
        return best

    def select_butterfly_strikes(self, chain: OptionsChain,
                                  direction: str,
                                  current_price: float,
                                  wing_width_strikes: int
                                  ) -> Optional[Dict[str, OptionContract]]:
        """Select center (ATM) ± wing_width butterfly strikes."""
        center_strike = round_to_strike(current_price, STRIKE_INCREMENT)
        lower_strike  = center_strike - wing_width_strikes * STRIKE_INCREMENT
        upper_strike  = center_strike + wing_width_strikes * STRIKE_INCREMENT

        contracts = chain.calls if direction == "call" else chain.puts

        def find_strike(target: int) -> Optional[OptionContract]:
            candidates = [c for c in contracts if c.mark > 0 and c.strike == target]
            if candidates:
                return candidates[0]
            liquid = [c for c in contracts if c.mark > 0]
            if not liquid:
                return None
            return min(liquid, key=lambda c: abs(c.strike - target))

        lower  = find_strike(lower_strike)
        center = find_strike(center_strike)
        upper  = find_strike(upper_strike)

        if not all([lower, center, upper]):
            logger.warning(
                f"Butterfly: could not find all strikes "
                f"{lower_strike}/{center_strike}/{upper_strike}"
            )
            return None

        logger.info(
            f"Butterfly: {direction.upper()} "
            f"{lower.strike}/{center.strike}/{upper.strike} "
            f"marks={lower.mark:.2f}/{center.mark:.2f}/{upper.mark:.2f}"
        )
        return {"lower": lower, "center": center, "upper": upper}

    def get_iv_rank(self, chain: OptionsChain) -> float:
        """Estimate IV rank. Falls back to ATM call IV."""
        if chain.iv_rank > 0:
            return chain.iv_rank
        if chain.calls:
            atm = min(chain.calls, key=lambda c: abs(c.delta - 0.5))
            return atm.iv * 100
        return 0.0


# Singleton
_fetcher: Optional[OptionsChainFetcher] = None


def get_chain_fetcher() -> OptionsChainFetcher:
    global _fetcher
    if _fetcher is None:
        _fetcher = OptionsChainFetcher()
    return _fetcher