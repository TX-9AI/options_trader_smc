"""
database/trade_logger.py — Options trade logging (SQLite). v3.16
v3.16  2026-08-18  F.2a — `regime_engine` IS NOW ACTUALLY WRITTEN. The column
        has existed since v-eng (2026-07-30) and main.py v4.8's changelog says
        "trades carry `regime_engine`" — but NO CALLER EVER SET IT. Every row
        on every box carries the '' default, so the one field that says which
        entry core produced a trade has been empty for the whole life of the
        column. Exactly the class this repo keeps re-learning: a quantity
        documented as persisted, never written, therefore untestable.
        Fixed CENTRALLY, not per-caller — main.py resolves the engine ONCE at
        startup and calls set_engine_tag(); log_entry stamps any record that
        did not supply a non-empty value. There are three log_entry call sites
        and a per-site fix would have missed the next one.
        ⚠️ Load-bearing for the QQQ SMC cutover: that box's history spans two
        entry cores, and without this column a pooled QQQ number is a number
        about two different systems. Rows written BEFORE this ships keep '' —
        honest ("not recorded"), and distinguishable from "L2".
v3.15  2026-08-17  SWALLOW T1: this file's silent handler(s) now announce
        themselves once. Behaviour unchanged in every case; only the silence
        was the defect.
v3.14  2026-08-17  TCS.4: log_entry FILTERS TO REAL COLUMNS AND WARNS.
        It INSERTed every key in the record, so a key with no column raised
        OperationalError and CRASH-LOOPED a live box (NFLX, 2026-08-17).
        A record key that is not a column is a BUG IN THE CALLER, but it must
        not be able to take a trading box down. Unknown keys are dropped.
        WARNED ONCE PER KEY NAME, because silently dropping a field that was
        SUPPOSED to persist is Pattern 2 - the class that produced this bug.
        Census run at the same time: `is_trend_credit` was the ONLY offender;
        this filter is a guardrail against the next one, not a fix for a
        population. PRAGMA is cached, not run per insert. FAILS OPEN if the
        schema cannot be read.
v3.13 — 2026-08-05 — the two v3.12 setters now LOG INSIDE their except bodies.
        The 2026-08-05 swallow census flagged both as new TIER-1 silent
        handlers (87 -> 89) the morning after W.2a's lesson was written down:
        the census reads the HANDLER BODY, so a bare `return False` is silent
        no matter what the caller does. No behaviour change — the callers still
        warn once per reason and nothing gates on the result.
v3.12 — 2026-08-04 — CONTRACT TELEMETRY (entry_delta/gamma/theta/iv,
        entry+exit bid/ask, exit_iv, chain_iv_rank) via set_entry_contract() /
        set_exit_contract(). TEN columns, not twelve: `entry_mark` and
        `chain_spot_at_entry` were dropped from the first cut because
        `entry_premium` and `underlying_entry` ALREADY HOLD THOSE FACTS. Two
        names for one value is how a report ends up quietly reading the stale
        one. Auto-migrates.
        Observability only — nothing gates on these.
        THE GAP IT CLOSES: every other instrument in this repo measures the
        UNDERLYING's path (MFE/MAE, floor durability, strike curves, regime
        labels) while the P&L is PREMIUM. Without the contract's own state,
        "wrong on direction", "right but theta ate it" and "IV crushed after
        the open" collapse into one number — and on 0DTE that is the whole game.
        NOTHING NEW IS FETCHED: OptionContract already carries bid/ask/mark/
        delta/gamma/theta/vega/iv and OptionsChain carries spot_price/iv_rank.
        They were read for strike selection and discarded.
        NULLS ARE LOAD-BEARING: rows from before this shipped must stay
        distinguishable from a capture that ran, so there are no defaults.
        See docs/MECHANICS.md "Contract telemetry" for what is collected and
        which reports read it.
v3.11 — 2026-08-04 — EXIT LATENCY (N.5): exit_submit_ts / exit_fill_ts /
        exit_latency_ms / exit_ladder_steps / exit_escalated /
        exit_mark_at_trigger, plus set_exit_latency() (returns a bool, same
        reason as v3.10). Auto-migrated; NULL on every pre-existing row and on
        any close that was never confirmed.
        WHY IT MOVED FORWARD FROM AUG 24 TO THE AUG 10 BAKE: the dataset only
        accrues in sessions recorded AFTER it deploys, and TC.2's stop-trigger
        decision (-40% vs 35% vs 25%) is explicitly "calibrate against measured
        ladder fill-latency". At Aug 24 that is ~5 paper sessions before live
        capital; at Aug 10 it is ~15. Identical argument to v3.10's.
        `exit_mark_at_trigger` IS THE MEASUREMENT and is an addition to N.5's
        four named fields: latency in milliseconds is not a cost until it is
        priced, and the cost is (mark when the exit fired) - (price it actually
        filled at). In PAPER the two are equal by construction — that equality
        is the plumbing proof, not a result.
        TELEMETRY ONLY — nothing reads these columns in the trading path.
v3.10 — 2026-08-04 — ENTRY SNAPSHOT: `entry_snapshot` (TEXT, JSON written by
        analysis/entry_snapshot.py) + set_entry_snapshot(), which RETURNS a
        boolean instead of discarding it. Auto-migrated; NULL on every
        pre-existing row and on any row whose capture failed.
        WHY: the TC.2 exit bake-off compares BoS / trail / 5m-FVG on IDENTICAL
        entries, and two of those three need the zone inventory the live engine
        held at entry. BoS does not — it re-derives from entry price and the
        post-entry tape — so only the FVG frame, its anchor, and the per-frame
        bar depth are stored. The 5m frame is CONTINUOUS across sessions while
        the banked tape is session-scoped RTH, so an offline reconstruction is
        a different object, not a cheaper one (same divergence class as defect
        S). Like v3.9 it pays off only in sessions recorded after it deploys,
        so its value decreases every session until the 2026-08-21 freeze.
        WHY IT RETURNS A BOOLEAN: update_fields() discards success, and
        AlertManager._send discarding an existing boolean is precisely what
        turned the blind-alert failure into a five-step hunt (item AU). A
        capture that silently no-ops would leave a column of NULLs that looks
        identical to "no trades taken".
        TELEMETRY ONLY — nothing reads this column in the trading path.
v3.9 — 2026-08-03 — MFE/MAE TIMESTAMPS: max_premium_seen_at /
        min_premium_seen_at (TEXT, UTC ISO via ts_for_db — the SAME base as
        entry_time, deliberately, because comparing a UTC field against an
        ET-offset one has already inverted one verdict here). Auto-migrated,
        NULL on every pre-existing row.
        WHY, and why it could not wait: v3.8 stored the excursion EXTREMES as
        values with no time attached. That is enough to measure HOW MUCH a
        winner gave back and useless for asking WHETHER IT COULD HAVE BEEN
        EXTENDED — a trade that peaked at minute 2 and bled for twenty minutes
        and one that ran to the exit and reversed on the last tick produce the
        identical (MFE, realized) pair, and they call for opposite fixes: the
        first says the leash is too loose, the second says the move simply
        turned. No quantity of additional sessions resolves that; only the
        timestamp does. It pays off ONLY in sessions recorded after it
        deploys, so its value is strictly decreasing until the 2026-08-21
        freeze.
        TELEMETRY ONLY — no trade mechanics touched. The timestamp advances
        only when the extreme itself advances (CASE on the pre-update row),
        so it marks WHEN the peak/trough was set, not when it was last
        re-confirmed. SQLite evaluates every SET right-hand side against the
        ORIGINAL row regardless of clause order, so the CASE reads the old
        extreme even though it is written alongside the new one — proven by
        test_mfe_timestamp_tracks_only_new_highs rather than asserted.
        Consumers MUST treat NULL as "not recorded" and never as zero or as
        entry time: every row banked before this deploy has it.
v3.1 — 2026-07-12 — F5 FIX (exit-reason integrity): new trail_stop column
        (schema + migration) + update_trail_stop(). The trail is now persisted
        separately; stop_premium is the immutable entry-time -25% floor.
        update_stop() removed — its only caller (position_manager) overwrote
        stop_premium with the trail, so every trail-armed exit was labeled
        'hard_stop_25pct'/'stop_hit'. Restart survivability preserved: the
        exit engine seeds its in-memory trail from trail_stop on recovery.
v3.0 — original release
v1.1 — 2026-06-27 — add orb_range_high, orb_range_low, current_premium
        columns to schema for ORB exit logic and live P&L display
v1.2 — 2026-07-02 — condor-leg support: spread columns (short/long strike,
        credit, width, is_condor_leg, condor_leg_num, is_broken_wing,
        short/long symbol) + get_open_trades() for concurrent condor legs.
v1.3 — 2026-07-02 — add generic update_fields() (used by the broken-wing roll
        to flag rolled/tested legs is_broken_wing).
v1.4 — 2026-07-06 — DEFINITIVE realized-P&L primitive: realized_pnl_today()
        (single source of truth for the daily-loss circuit breaker, status and
        query) with ET-correct session bucketing; today_summary() routed through
        it so displays and the halt can never disagree.
v1.5 — 2026-07-07 — expiry-aware orphan handling: get_open_trades_live() (open
        rows not yet expired — 0DTE and weeklies alike, plus unknown-expiry rows
        kept for safety) and close_expired_open_trades() (auto-close ONLY rows
        whose expiry date has passed — a weekly with time left is left alone).
        Keyed on the stored expiry (YYYY-MM-DD), never on entry date, so a
        multi-day weekly is never mistaken for a same-day ghost.
v1.6 — 2026-07-07 — broker reconciliation support: is_short_position column
        (schema + migration) so an adopted short survives a re-restart; and
        close_phantom() to close a DB row the broker no longer shows (broker is
        the source of truth for existence on live).
v3.8 — 2026-07-15 — MFE/MAE TELEMETRY: max_premium_seen / min_premium_seen
        columns (auto-migrated), updated in the same per-tick write as
        current_premium. The evidence base for exit-threshold tuning — pairs
        with exit_engine v3.8's runner refinements so 40% floor / 5m FVGs /
        clamp / sweep runner mode can be judged on excursion data, not vibes.
v3.7 — 2026-07-15 — MODE ISOLATION (audit defect Q). Every decision/session
        read is scoped to the current mode's rows via COALESCE(paper_trade,1):
        get_open_trade(s), close_expired_open_trades, get_session_losses,
        get_consecutive_losses, and _closed_today_rows — the DAILY_LOSS_LIMIT
        source of truth. A live bot can no longer adopt open paper positions or
        gate the real-money breaker on paper P&L (and paper stays clean of live
        rows symmetrically). Row WRITES are untouched — trade_id-keyed updates
        need no mode. Companion: configure.sh v2.0 archives trades.db on every
        mode switch so histories never mix in one file to begin with.
v3.6 — 2026-07-15 — close_phantom() accepts recovered exit_price/pnl_usd so a
        manually-closed-at-broker phantom books its REAL fill from order history
        (broker_reconcile.match_closing_fills) instead of a flagged $0.00.
v3.0 — 2026-07-10 — repo-wide v3.0 bump: Yahoo-Finance purge & data stream
        mapping optimization (all market data now flows from the single
        shared TastyTrade candle feed — see data/candle_feed.py). No logic
        change in this file.
"""
# v3.11 (2026-08-04, N.5) — trades table also captures the exit ladder's latency: exit_submit_ts, exit_fill_ts, exit_latency_ms, exit_ladder_steps, exit_escalated and exit_mark_at_trigger. Written by exit_engine.place_exit_order() — the ONE seam both paper and live close through — via set_exit_latency(). This is the dataset TC.2's stop-trigger decision reads. Auto-migrates. Observability only.
# v3.10 (2026-08-04) — trades table also captures entry_snapshot: the FVG zones, the frame the trail would anchor to, the live StructureMap levels and the per-timeframe bar depth, all as held at the moment of the fill. Written by analysis/entry_snapshot.py via set_entry_snapshot(); the TC.2 exit bake-off is not computable without it. Auto-migrates. Observability only.
# v-obs2 (2026-07-24) — trades table also captures swept_level_name + level_strength (what KIND of liquidity level a sweep fired against — named PDH/PDL/session vs equal-H/L). Sweep postmortems: does level conviction predict outcome? Auto-migrates.

# v-obs (2026-07-24) — trades table now captures adx_at_entry, regime_conviction, flat_angle_deg (regime context at entry, for tape-fingerprint analysis). Auto-migrates existing dbs via ALTER TABLE. Observability only — no trade-mechanics change.


import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime, timezone, timedelta

from config import DB_PATH, PAPER_TRADING
from utils.time_utils import ts_for_db, now_utc, now_et, ET

logger = logging.getLogger(__name__)
_WARNED_UNKNOWN_COLS: set = set()   # TCS.4: warn once per unknown key
# v3.16 (F.2a) — the RESOLVED entry-core tag for this process ("SMC"|"L2"|"v13"),
# set once by main.py via TradeLogger.set_engine_tag(). Empty until then, and an
# empty tag never overwrites anything: regime_engine='' means "not recorded".
_ENGINE_TAG: str = ""


def set_engine_tag(tag: str) -> None:
    """v3.16 (F.2a) — record WHICH entry core is running on this box.

    MODULE-level on purpose: it sets module state, and calling it must not
    require constructing a TradeLogger (which opens the DB and runs the
    migrations). main.py calls it once at import, after the engine is
    RESOLVED — so a box whose smc import failed and fell back stamps what
    actually ran, not what was asked for.
    """
    global _ENGINE_TAG
    _ENGINE_TAG = (tag or "").strip()
    logger.info("[schema] trade rows will carry regime_engine=%r", _ENGINE_TAG)
_WARNED_SCHEMA_READ: set = set()    # SWALLOW T1: warn once if PRAGMA fails


@dataclass
class TradeRecord(dict):
    """
    Options trade record. Inherits from dict so it works as both
    a typed object and a sqlite3.Row-compatible mapping.
    """
    pass


def make_record(**kwargs) -> TradeRecord:
    r = TradeRecord()
    r.update(kwargs)
    return r


class TradeLogger:
    """SQLite-backed trade log for options_trader."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS trades (
        trade_id          TEXT PRIMARY KEY,
        symbol            TEXT,
        strategy          TEXT,
        setup_type        TEXT,
        setup_grade       TEXT,
        setup_score       REAL,
        direction         TEXT,
        option_side       TEXT,
        is_butterfly      INTEGER DEFAULT 0,
        strike            REAL,
        lower_strike      REAL,
        center_strike     REAL,
        upper_strike      REAL,
        expiry            TEXT,
        contracts         INTEGER,
        entry_premium     REAL,
        exit_premium      REAL,
        current_premium   REAL DEFAULT 0.0,
        net_debit         REAL,
        max_profit        REAL,
        total_cost        REAL,
        max_loss          REAL,
        stop_premium      REAL,
        trail_activation  REAL,
        trail_stop        REAL DEFAULT 0.0,
        target_premium    REAL,
        underlying_entry  REAL,
        underlying_stop   REAL,
        underlying_target REAL,
        orb_range_high    REAL DEFAULT 0.0,
        orb_range_low     REAL DEFAULT 0.0,
        short_strike      REAL DEFAULT 0.0,
        long_strike       REAL DEFAULT 0.0,
        credit_received   REAL DEFAULT 0.0,
        spread_width      REAL DEFAULT 0.0,
        is_condor_leg     INTEGER DEFAULT 0,
        condor_leg_num    INTEGER DEFAULT 0,
        is_broken_wing    INTEGER DEFAULT 0,
        is_short_position INTEGER DEFAULT 0,
        short_symbol      TEXT,
        long_symbol       TEXT,
        pnl_usd           REAL,
        pnl_pct           REAL,
        regime            TEXT,
        vix_at_entry      REAL,
        adx_at_entry      REAL DEFAULT 0.0,
        regime_conviction REAL DEFAULT 0.0,
        flat_angle_deg    REAL DEFAULT 0.0,
        -- A2.6b (2026-08-18): the overnight gap, MEASURED. NULL default, not
        -- 0.0 -- a gap of exactly zero is a real reading (the market opened
        -- unchanged) and a numeric default would be indistinguishable from it.
        -- That confusion is what made flat_angle_deg, level_strength and
        -- vix_at_entry look like measured nulls rather than empty columns.
        gap_pct           REAL,
        swept_level_name  TEXT DEFAULT '',
        level_strength    REAL DEFAULT 0.0,
        entry_snapshot    TEXT,
        exit_submit_ts    TEXT,
        exit_fill_ts      TEXT,
        exit_latency_ms   INTEGER,
        exit_ladder_steps INTEGER,
        exit_escalated    INTEGER,
        exit_mark_at_trigger REAL,
        is_fed_day        INTEGER DEFAULT 0,
        status            TEXT DEFAULT 'open',
        exit_reason       TEXT,
        order_id          TEXT,
        lower_symbol      TEXT,
        center_symbol     TEXT,
        upper_symbol      TEXT,
        option_symbol     TEXT,
        paper_trade       INTEGER DEFAULT 1,
        entry_time        TEXT,
        exit_time         TEXT,
        notes             TEXT
    );

    CREATE TABLE IF NOT EXISTS circuit_breaker_events (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        event_time      TEXT,
        reason          TEXT,
        session_losses  INTEGER,
        notes           TEXT
    );

    CREATE TABLE IF NOT EXISTS regime_log (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        logged_at     TEXT,
        regime        TEXT,
        conviction    REAL,
        macro_context TEXT,
        adx           REAL,
        trigger       TEXT,
        engine        TEXT
    );
    """

    def __init__(self, db_path: str = DB_PATH,
                 paper_trading: bool = PAPER_TRADING):
        self.db_path = db_path
        # v3.7 (defect Q): every read that drives DECISIONS or SESSION TRUTH is
        # scoped to the CURRENT MODE's rows. Paper and live share one schema,
        # but a live bot must never manage paper positions or gate its daily
        # loss limit on paper P&L — and vice versa. paper_trade defaults to 1
        # in the schema, so legacy rows count as paper (safe: live sees none).
        self._mode_flag = 1 if paper_trading else 0
        self._ensure_db()

    def _ensure_db(self):
        import os
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.executescript(self.SCHEMA)
        # Migrate existing DBs — add columns if missing
        for col, definition in [
            ("current_premium", "REAL DEFAULT 0.0"),
            ("max_premium_seen", "REAL"),
            ("min_premium_seen", "REAL"),
            # v3.9 — WHEN each extreme was set (UTC ISO). NULL = not recorded;
            # never read it as zero or as entry time.
            ("max_premium_seen_at", "TEXT"),
            ("min_premium_seen_at", "TEXT"),
            ("orb_range_high",  "REAL DEFAULT 0.0"),
            ("orb_range_low",   "REAL DEFAULT 0.0"),
            ("short_strike",    "REAL DEFAULT 0.0"),
            ("long_strike",     "REAL DEFAULT 0.0"),
            ("credit_received", "REAL DEFAULT 0.0"),
            ("spread_width",    "REAL DEFAULT 0.0"),
            ("is_condor_leg",   "INTEGER DEFAULT 0"),
            ("condor_leg_num",  "INTEGER DEFAULT 0"),
            ("is_broken_wing",  "INTEGER DEFAULT 0"),
            ("short_symbol",    "TEXT"),
            ("long_symbol",     "TEXT"),
            ("is_short_position", "INTEGER DEFAULT 0"),
            ("trail_stop",      "REAL DEFAULT 0.0"),
            ("adx_at_entry",      "REAL DEFAULT 0.0"),   # v-obs: regime context at entry
            ("regime_conviction", "REAL DEFAULT 0.0"),
            ("flat_angle_deg",    "REAL DEFAULT 0.0"),
            ("gap_pct",           "REAL"),          # A2.6b
            ("swept_level_name",  "TEXT DEFAULT ''"),   # v-obs: swept level kind (sweep postmortems)
            ("level_strength",    "REAL DEFAULT 0.0"),
            # v3.10 — entry-time FVG/structure picture as JSON. NO DEFAULT and
            # no empty-string sentinel: NULL means "not captured", and that has
            # to stay distinguishable from a capture that ran and found nothing
            # (which writes a real payload with "anchor":null).
            ("entry_snapshot",    "TEXT"),
            # v3.11 (N.5) — exit ladder latency. NULLs are load-bearing here:
            # a close that never confirmed has no fill instant, and inventing
            # one would put a zero-latency row in the exact population the
            # trigger decision is measured on.
            ("exit_submit_ts",      "TEXT"),
            ("exit_fill_ts",        "TEXT"),
            ("exit_latency_ms",     "INTEGER"),
            ("exit_ladder_steps",   "INTEGER"),
            ("exit_escalated",      "INTEGER"),
            ("exit_mark_at_trigger", "REAL"),
            ("regime_engine",     "TEXT DEFAULT ''"),   # v-eng: WHICH engine labelled this
            # v3.12 — CONTRACT TELEMETRY. Every one of these values was already
            # in memory at fill time (OptionContract carries bid/ask/mark/delta/
            # gamma/theta/vega/iv; OptionsChain carries spot_price/iv_rank) and
            # was read for strike selection and then DISCARDED. Nothing new is
            # fetched, subscribed or computed.
            # WHY IT MATTERS: every instrument in this repo measures the
            # UNDERLYING's path, but the P&L is PREMIUM. Without these, "wrong
            # on direction", "right but theta ate it" and "IV crushed" are one
            # number — and on 0DTE they are the whole game.
            # NULL means NOT CAPTURED and is load-bearing: rows written before
            # this shipped must stay distinguishable from a capture that ran.
            # No defaults, for the same reason entry_snapshot has none.
            ("entry_delta",       "REAL"),
            ("entry_gamma",       "REAL"),
            ("entry_theta",       "REAL"),
            ("entry_iv",          "REAL"),
            ("entry_bid",         "REAL"),
            ("entry_ask",         "REAL"),
            ("exit_bid",          "REAL"),
            ("exit_ask",          "REAL"),
            ("exit_iv",           "REAL"),
            ("chain_iv_rank",     "REAL"),
        ]:
            try:
                conn.execute(f"ALTER TABLE trades ADD COLUMN {col} {definition}")
                conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists
        # v-eng (2026-07-30) — regime_log gains `engine`. Until now NOTHING in the
        # data said which engine produced a label: L2.5 vs the v1.3 fallback was
        # recoverable only from a [L2 c=..]/[v13] tag in bot.log, so on 2026-07-30
        # the question "has L2.5 ever run?" needed a fleet-wide log grep across
        # 138k-line files. It also means every session's first ~25 minutes are
        # v1.3-labelled by design (the RANGING/COMPRESSION 1m warm-up), and no fit
        # could exclude them without this column. Provenance belongs in the row.
        try:
            conn.execute("ALTER TABLE regime_log ADD COLUMN engine TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass
        conn.commit()
        conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _columns(self) -> set:
        """Real column names of `trades`, cached. PRAGMA once, not per insert."""
        if getattr(self, "_cols_cache", None) is None:
            try:
                with self._connect() as conn:
                    self._cols_cache = {r[1] for r in
                                        conn.execute("PRAGMA table_info(trades)")}
            except Exception as exc:                           # noqa: BLE001
                # ⚠️ FAIL OPEN: if the schema cannot be read, insert everything
                # exactly as before rather than dropping fields on a guess.
                # ⚠️ AND SAY SO — SWALLOW T1, 2026-08-17. This handler was
                # SILENT when it shipped, which meant the crash-loop guard could
                # DISABLE ITSELF WITH NO WORD: a failed PRAGMA sends log_entry
                # straight back to inserting every record key, which is the
                # exact condition that crash-looped NFLX the day before. A guard
                # that can turn itself off quietly is not a guard.
                if not _WARNED_SCHEMA_READ:
                    _WARNED_SCHEMA_READ.add(1)
                    logger.warning(
                        "[schema] could not read the `trades` column list (%s) - "
                        "FAILING OPEN: every record key will be inserted, so an "
                        "unknown key will raise on the INSERT again. The TCS.4 "
                        "guard is NOT active on this box until this clears.", exc)
                return set(TradeRecord.__annotations__) if hasattr(
                    TradeRecord, "__annotations__") else set()
        return self._cols_cache

    def log_entry(self, record: TradeRecord):
        """Insert a new open trade into the database."""
        record["entry_time"] = ts_for_db()
        record["status"]     = "open"

        # ── v3.16 (F.2a) — STAMP THE ENGINE, CENTRALLY ──────────────────────
        # A caller that already set a non-empty value wins; otherwise the
        # resolved startup tag is written. Done HERE rather than at the three
        # call sites because the fourth one, whenever it is added, will not
        # remember — and an unstamped row is indistinguishable from a
        # pre-v3.16 row, which is the ambiguity this exists to remove.
        if not str(record.get("regime_engine") or "").strip() and _ENGINE_TAG:
            record["regime_engine"] = _ENGINE_TAG

        # ── TCS.4 (2026-08-17) — FILTER TO REAL COLUMNS, AND SAY SO ─────────
        # ⚠️ THIS FUNCTION CRASH-LOOPED A LIVE BOX. It INSERTed every key in the
        # record; `is_trend_credit` has no column, so the INSERT raised
        # OperationalError, the loop error counter hit its cap, the service shut
        # down, restarted, and did it again — every 15s for the rest of NFLX's
        # session on 2026-08-17.
        # A record key that is not a column is a BUG IN THE CALLER, but it must
        # not be able to take a trading box down. Unknown keys are dropped.
        # ⚠️ AND LOUDLY — ONCE PER KEY NAME. Silently dropping a field that was
        # SUPPOSED to persist would be the worse failure: that is Pattern 2, the
        # class that produced `is_trend_credit` in the first place. A drop is
        # visible or it is a new silent defect.
        cols         = [k for k in record.keys() if k in self._columns()]
        dropped      = [k for k in record.keys() if k not in self._columns()]
        for k in dropped:
            if k not in _WARNED_UNKNOWN_COLS:
                _WARNED_UNKNOWN_COLS.add(k)
                logger.warning(
                    "[schema] record key %r has NO COLUMN in `trades` and was "
                    "DROPPED from the insert. The trade is still logged. If this "
                    "field was meant to persist, ADD THE COLUMN - do not rely on "
                    "reading it back, it will be None on every restart.", k)
        values       = [record[k] for k in cols]
        placeholders = ", ".join(["?"] * len(cols))
        col_names    = ", ".join(cols)

        with self._connect() as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO trades ({col_names}) VALUES ({placeholders})",
                values
            )
        logger.info(f"Trade logged: {record.get('trade_id', '')[:8]} entry")

    def log_exit(self, trade_id: str, exit_price: float,
                  pnl_usd: float, exit_reason: str):
        """Update an open trade with exit details."""
        entry_prem = self._get_field(trade_id, "entry_premium") or 0
        pnl_pct    = (exit_price - entry_prem) / entry_prem if entry_prem > 0 else 0

        with self._connect() as conn:
            conn.execute("""
                UPDATE trades SET
                    status       = 'closed',
                    exit_premium = ?,
                    pnl_usd      = ?,
                    pnl_pct      = ?,
                    exit_reason  = ?,
                    exit_time    = ?
                WHERE trade_id = ?
            """, (exit_price, pnl_usd, pnl_pct,
                  exit_reason, ts_for_db(), trade_id))
        logger.info(
            f"Trade closed: {trade_id[:8]} "
            f"exit=${exit_price:.2f} pnl=${pnl_usd:+.2f}"
        )

    def update_trail_stop(self, trade_id: str, new_trail: float):
        """v3.1 — persist the ratcheted trail SEPARATELY from stop_premium.
        stop_premium is the IMMUTABLE entry-time -25% floor; the old
        update_stop() overwrote it with the trail, which made the exit
        engine's floor checks fire at the trail level and label every
        trail-armed exit 'hard_stop_25pct'/'stop_hit' — poisoning exit_reason
        distributions. Recovery seeds the in-memory trail from this column."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE trades SET trail_stop=? WHERE trade_id=?",
                (new_trail, trade_id)
            )

    def update_current_premium(self, trade_id: str, premium: float,
                               ts: Optional[str] = None):
        """Update live mark price every tick — and the per-trade MFE/MAE
        telemetry: max/min premium ever seen while open, and (v3.9) WHEN each
        extreme was set. This is the evidence base for tuning every exit
        threshold (was the floor hit by trades that then recovered? how much
        did trails give back vs capture — and did the peak come early or at
        the exit?).
        SQLite scalar MAX/MIN keep it one write; COALESCE seeds on first tick.
        The _at columns use CASE on the PRE-UPDATE row, so they advance only
        when the extreme itself advances rather than on every re-confirming
        tick. SQLite evaluates all SET right-hand sides against the original
        row, so the CASE sees the old extreme even though the new one is
        assigned in the same statement.
        ts is injectable for tests; production passes None and gets ts_for_db()
        — the same UTC base as entry_time, never a local or ET clock."""
        stamp = ts or ts_for_db()
        with self._connect() as conn:
            conn.execute(
                "UPDATE trades SET current_premium=?, "
                "max_premium_seen_at=CASE WHEN max_premium_seen IS NULL "
                "    OR ? > max_premium_seen THEN ? ELSE max_premium_seen_at END, "
                "min_premium_seen_at=CASE WHEN min_premium_seen IS NULL "
                "    OR ? < min_premium_seen THEN ? ELSE min_premium_seen_at END, "
                "max_premium_seen=MAX(COALESCE(max_premium_seen, ?), ?), "
                "min_premium_seen=MIN(COALESCE(min_premium_seen, ?), ?) "
                "WHERE trade_id=?",
                (premium,
                 premium, stamp,
                 premium, stamp,
                 premium, premium, premium, premium, trade_id)
            )

    def set_entry_snapshot(self, trade_id: str, payload: str) -> bool:
        """v3.10 — persist the entry-time snapshot JSON. Returns True only if a
        row was actually updated.

        It RETURNS rather than logs-and-swallows on purpose (item AU): a caller
        that cannot tell "wrote it" from "wrote nothing" produces a column of
        NULLs that reads exactly like a quiet session. rowcount is checked
        because a wrong trade_id is a silent no-op in SQLite, not an error.
        """
        if not trade_id or not payload:
            return False
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "UPDATE trades SET entry_snapshot=? WHERE trade_id=?",
                    (payload, trade_id))
                return cur.rowcount > 0
        except Exception as exc:                             # noqa: BLE001
            logger.warning("entry_snapshot write failed for %s: %s: %s",
                           trade_id[:8], type(exc).__name__, exc)
            return False

    # ── v3.12 — contract telemetry ──────────────────────────────────────────
    def set_entry_contract(self, trade_id: str, c: dict) -> bool:
        """Persist the CONTRACT's own state at entry. Returns True on a write.

        `entry_delta` IS A SELECTOR OUTPUT, NOT A MARKET OBSERVATION — the
        strike chooser picked it. So "0.30-delta entries do worse" is partly a
        statement about the selector, not about the market, and any analysis
        that reads it must say so. Recorded here rather than discovered in three
        weeks.

        BID AND ASK, NOT MARK. Mark is already stored as `entry_premium`, and
        spot at entry as `underlying_entry` — both predate this. Adding them
        again would have created two names for one fact, which is how a report
        ends up silently reading the stale one. The BID/ASK PAIR is what is
        genuinely new: mark is the midpoint, fills are not, and the spread is
        the only thing that can turn the floor sweep's declared "ASSUMES: no
        slippage" into a measured quantity — and the basis for the
        paper-vs-live fill comparison once live trading starts.
        """
        if not trade_id or not isinstance(c, dict):
            return False
        cols = ("entry_delta", "entry_gamma", "entry_theta", "entry_iv",
                "entry_bid", "entry_ask", "chain_iv_rank")
        vals = [c.get(k) for k in cols]
        if all(v is None for v in vals):
            return False
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "UPDATE trades SET "
                    + ", ".join(f"{k}=?" for k in cols)
                    + " WHERE trade_id=?", (*vals, trade_id))
                conn.commit()
                return cur.rowcount > 0
        except Exception as exc:                                 # noqa: BLE001
            # v3.13 — logged INLINE. The W.2 swallow census reads the HANDLER
            # BODY, so a bare `return False` here reads as a silent TIER-1
            # handler — and the 2026-08-05 census caught this one the morning
            # after the lesson was written down. The caller already warns once
            # per reason; this line exists so the census can see the handler is
            # not swallowing, and so a DB-level failure is distinguishable from
            # "the row was not there".
            logger.debug("set_entry_contract failed (%s: %s) for %s",
                         type(exc).__name__, exc, trade_id[:8])
            return False

    def set_exit_contract(self, trade_id: str, c: dict) -> bool:
        """Persist the contract's state at the CONFIRMED close.

        `exit_iv` beside `entry_iv` is the IV-crush measurement — the most
        likely explanation for the 10:00-11:00 phase being the worst on the
        board, and currently indistinguishable from being wrong on direction.
        """
        if not trade_id or not isinstance(c, dict):
            return False
        cols = ("exit_bid", "exit_ask", "exit_iv")
        vals = [c.get(k) for k in cols]
        if all(v is None for v in vals):
            return False
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "UPDATE trades SET "
                    + ", ".join(f"{k}=?" for k in cols)
                    + " WHERE trade_id=?", (*vals, trade_id))
                conn.commit()
                return cur.rowcount > 0
        except Exception as exc:                                 # noqa: BLE001
            # v3.13 — inline, same reason as set_entry_contract above.
            logger.debug("set_exit_contract failed (%s: %s) for %s",
                         type(exc).__name__, exc, trade_id[:8])
            return False

    def set_exit_latency(self, trade_id: str, submit_ts: str, fill_ts: str,
                         latency_ms: int, ladder_steps: int,
                         escalated: bool, mark_at_trigger=None) -> bool:
        """v3.11 (N.5) — persist the exit ladder's latency telemetry.

        Returns True only if a row was actually updated, for the same reason
        set_entry_snapshot does (item AU): a silent no-op UPDATE would leave a
        column of NULLs that reads exactly like a session with no exits.

        Called ONLY on a confirmed close. An unconfirmed close deliberately
        writes nothing — a close that never filled has no fill instant, and a
        fabricated one would land a zero-latency row inside the very population
        the stop-trigger decision is measured on.
        """
        if not trade_id or not submit_ts or not fill_ts:
            return False
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "UPDATE trades SET exit_submit_ts=?, exit_fill_ts=?, "
                    "exit_latency_ms=?, exit_ladder_steps=?, exit_escalated=?, "
                    "exit_mark_at_trigger=? WHERE trade_id=?",
                    (submit_ts, fill_ts, int(latency_ms), int(ladder_steps),
                     1 if escalated else 0,
                     None if mark_at_trigger is None else float(mark_at_trigger),
                     trade_id))
                return cur.rowcount > 0
        except Exception as exc:                             # noqa: BLE001
            logger.warning("exit_latency write failed for %s: %s: %s",
                           trade_id[:8], type(exc).__name__, exc)
            return False

    def update_fields(self, trade_id: str, **fields):
        """Generic field updater (used by the broken-wing roll to flag legs)."""
        if not fields:
            return
        sets = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values()) + [trade_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE trades SET {sets} WHERE trade_id=?", vals)

    def get_open_trade(self) -> Optional[TradeRecord]:
        """Return the single open trade if any."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM trades WHERE status='open' "
                "AND COALESCE(paper_trade,1)=? ORDER BY entry_time DESC LIMIT 1",
                (self._mode_flag,)
            ).fetchone()
        if row:
            return make_record(**dict(row))
        return None

    def get_open_trades(self) -> List[TradeRecord]:
        """Return ALL open trades (oldest first). Supports concurrent condor
        legs; every other strategy holds at most one at a time."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status='open' "
                "AND COALESCE(paper_trade,1)=? ORDER BY entry_time ASC",
                (self._mode_flag,)
            ).fetchall()
        return [make_record(**dict(r)) for r in rows]

    def get_open_trades_today(self) -> List[TradeRecord]:
        """Deprecated alias — retained for safety. Prefer get_open_trades_live().
        A 0DTE bot that also trades weeklies can hold a position across sessions
        (expiry days out), so 'entered today' is the WRONG liveness test; use
        expiry instead."""
        return self.get_open_trades_live()

    @staticmethod
    def _expiry_date(expiry) -> str:
        """Normalize a stored expiry to 'YYYY-MM-DD'. Entries store this format
        already; tolerate a stray full timestamp. Returns '' if unknown."""
        if not expiry:
            return ""
        s = str(expiry).strip()
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            return s[:10]
        try:
            return datetime.fromisoformat(s).strftime("%Y-%m-%d")
        except Exception:
            return ""

    def get_open_trades_live(self) -> List[TradeRecord]:
        """Open rows that have NOT expired — expiry today or later (0DTE AND
        weeklies), plus any row whose expiry is unknown (kept deliberately: never
        abandon a possibly-live position). These are what startup recovery
        resumes managing."""
        today_et = now_et().strftime("%Y-%m-%d")
        out = []
        for r in self.get_open_trades():
            exp = self._expiry_date(r.get("expiry", ""))
            if exp == "" or exp >= today_et:
                out.append(r)
        return out

    def close_expired_open_trades(
        self, exit_reason: str = "expired_orphan_autoclosed"
    ) -> List[TradeRecord]:
        """Reconcile TRULY EXPIRED orphans only: any status='open' row whose
        expiry date has passed (expiry < today ET). A weekly still in its life is
        left ALONE — its expiry is in the future. Rows with an unknown expiry are
        also left open (never guess a live position dead). Each closed row gets
        status='closed', an explicit exit_reason, exit_time now, and pnl_usd
        forced to 0.0 (true settlement is unknowable — flag for manual review) so
        it leaves 'open' and is never 'recovered' again. Returns the rows closed
        (for alerting)."""
        today_et = now_et().strftime("%Y-%m-%d")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status='open' "
                "AND COALESCE(paper_trade,1)=?", (self._mode_flag,)
            ).fetchall()
            expired = []
            for r in rows:
                exp = self._expiry_date(r["expiry"])
                if exp != "" and exp < today_et:
                    expired.append(make_record(**dict(r)))
            if expired:
                ids = [r["trade_id"] for r in expired]
                placeholders = ",".join("?" * len(ids))
                conn.execute(
                    f"UPDATE trades SET status='closed', "
                    f"exit_reason=?, exit_time=?, "
                    f"pnl_usd=COALESCE(pnl_usd, 0.0) "
                    f"WHERE trade_id IN ({placeholders})",
                    [exit_reason, ts_for_db(), *ids]
                )
        for r in expired:
            logger.warning(
                f"Auto-closed EXPIRED orphan {r.get('trade_id','')[:8]} "
                f"(expiry {self._expiry_date(r.get('expiry',''))}, "
                f"{str(r.get('option_side','')).upper()} {r.get('strike',0)}) "
                f"— {exit_reason}"
            )
        return expired

    def close_phantom(self, trade_id: str,
                      reason: str = "phantom_closed_at_broker",
                      exit_price: float = None,
                      pnl_usd: float = None) -> None:
        """Close a DB row the broker no longer shows open. On LIVE, the broker is
        the source of truth for existence: if a row is open in our DB but absent
        at the broker, it has closed there (or never truly filled) and we must
        stop 'managing' it.

        v3.6: when the caller RECOVERED the real close from broker order history
        (see broker_reconcile.match_closing_fills), pass exit_price + pnl_usd and
        the row books the TRUTH — realized P&L the DAILY_LOSS_LIMIT breaker can
        trust. Without them, pnl_usd is forced to 0.0 (the real fill is unknown —
        flag for review) with an explicit reason, as before."""
        with self._connect() as conn:
            if pnl_usd is not None:
                conn.execute(
                    "UPDATE trades SET status='closed', exit_reason=?, exit_time=?, "
                    "exit_price=?, pnl_usd=? WHERE trade_id=?",
                    (reason, ts_for_db(), exit_price, float(pnl_usd), trade_id),
                )
                logger.warning(
                    f"Closed phantom {trade_id[:8]} — {reason} "
                    f"(RECOVERED fill @ {exit_price} pnl=${pnl_usd:+.2f})"
                )
                return
            conn.execute(
                "UPDATE trades SET status='closed', exit_reason=?, exit_time=?, "
                "pnl_usd=COALESCE(pnl_usd, 0.0) WHERE trade_id=?",
                (reason, ts_for_db(), trade_id),
            )
        logger.warning(f"Closed phantom {trade_id[:8]} — {reason} (fill unknown, pnl=0.0 FLAGGED)")

    def get_session_losses(self) -> int:
        today = now_utc().strftime("%Y-%m-%d")
        with self._connect() as conn:
            row = conn.execute("""
                SELECT COUNT(*) as n FROM trades
                WHERE status='closed'
                AND pnl_usd < 0
                AND date(entry_time) = ?
                AND COALESCE(paper_trade,1) = ?
            """, (today, self._mode_flag)).fetchone()
        return row["n"] if row else 0

    def get_consecutive_losses(self) -> int:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT pnl_usd FROM trades
                WHERE status='closed'
                AND COALESCE(paper_trade,1) = ?
                ORDER BY exit_time DESC
                LIMIT 10
            """, (self._mode_flag,)).fetchall()
        count = 0
        for row in rows:
            if row["pnl_usd"] < 0:
                count += 1
            else:
                break
        return count

    def log_circuit_breaker(self, reason: str, session_losses: int, notes: str = ""):
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO circuit_breaker_events
                (event_time, reason, session_losses, notes)
                VALUES (?, ?, ?, ?)
            """, (ts_for_db(), reason, session_losses, notes))

    def log_regime(self, regime: str, conviction: float,
                   macro_context: str, adx: float, trigger: str,
                   engine: str = ""):
        """engine (v-eng): "L2" when the committed integrator label drove this
        row, "v13" when the v1.3 classifier did. Defaulted so any older caller
        still works — but an empty value means UNKNOWN provenance, not L2."""
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO regime_log
                (logged_at, regime, conviction, macro_context, adx, trigger, engine)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (ts_for_db(), regime, conviction, macro_context, adx, trigger,
                  engine))

    def _get_field(self, trade_id: str, field: str):
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {field} FROM trades WHERE trade_id=?", (trade_id,)
            ).fetchone()
        return row[field] if row else None

    # ── DEFINITIVE closed-P&L accounting ──────────────────────────────────────
    # Single source of truth for realized (closed) P&L. Every consumer — the
    # daily-loss circuit breaker, status.py, query.py, EOD — references THESE
    # methods, never an in-memory copy and never a parallel re-sum. That is what
    # lets any bot reference its definitive day P&L immediately and survive any
    # restart: the number lives in trades.db, not in process memory.
    @staticmethod
    def _et_date(iso_ts: str) -> str:
        """ET calendar date ('YYYY-MM-DD') for a stored UTC ISO timestamp.
        Bucketing by ET (not UTC) so a late-session trade never lands on the
        wrong day."""
        try:
            dt = datetime.fromisoformat(iso_ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(ET).strftime("%Y-%m-%d")
        except Exception:
            return ""

    def _closed_today_rows(self) -> List[sqlite3.Row]:
        """Closed trades whose ET session date is today. Coarse UTC prefilter
        keeps the scan tiny; the exact match is done by ET date in Python."""
        today_et = now_et().strftime("%Y-%m-%d")
        lower = (now_utc() - timedelta(days=1)).strftime("%Y-%m-%d")
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM trades
                WHERE status='closed' AND pnl_usd IS NOT NULL
                AND date(entry_time) >= ?
                AND COALESCE(paper_trade,1) = ?
            """, (lower, self._mode_flag)).fetchall()
        return [r for r in rows if self._et_date(r["entry_time"]) == today_et]

    def realized_pnl_today(self) -> float:
        """DEFINITIVE realized net closed P&L for today's ET session (wins
        offset losses). This is the number the daily loss limit gates on."""
        return float(sum((r["pnl_usd"] or 0.0) for r in self._closed_today_rows()))

    def today_summary(self) -> dict:
        """Counts + net P&L for today's ET session. total_pnl is identical to
        realized_pnl_today() — one computation, so displays and the circuit
        breaker can never disagree."""
        rows = self._closed_today_rows()
        wins   = sum(1 for r in rows if (r["pnl_usd"] or 0) > 0)
        losses = sum(1 for r in rows if (r["pnl_usd"] or 0) < 0)
        total_pnl = float(sum((r["pnl_usd"] or 0.0) for r in rows))
        return {"total": len(rows), "wins": wins, "losses": losses,
                "total_pnl": total_pnl}


_trade_logger: Optional[TradeLogger] = None


def get_trade_logger() -> TradeLogger:
    global _trade_logger
    if _trade_logger is None:
        _trade_logger = TradeLogger()
    return _trade_logger
