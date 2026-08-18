"""
analysis/liquidity_ledger.py — options_trader_v3 — v1.1 — AUDIT A2: THE RECORD
        NOW SURVIVES THE RESTART IT EXISTS TO OUTLIVE, AND NO CLOSED BAR IS
        SKIPPED.
v1.1 — 2026-08-15 — audit #2 fixes:
        (A2.3) `reset_for_session` cleared with no load-back — `write()` was
        a writer with NO READER, so every bake wiped the day's touch/hold/
        breach counts and the next write overwrote the good file with zeros
        (reproduced: (1,1) -> (0,0) across a restart). Reset now HYDRATES
        from the same-date JSON first, then merges the caller's seeds
        through add_level (which dedupes). Guards: schema_version and
        touch_tol_pct must match the running process — counts taken under a
        different zone mean something else (LIQ.7) and start clean, loudly.
        (A2.4) the wiring fed only `iloc[-2]` behind a single-stamp guard;
        any tick slower than ~75s silently DROPPED closed bars — and slow
        ticks correlate with busy tape, so the undercount landed exactly on
        the bars most likely to test levels (reproduced). Bar selection now
        lives HERE: `feed_frame(df_1m)` walks every closed bar newer than
        `last_bar_ts` (persisted, so the A2.3 hydrate also recovers the
        bake gap from the 60-bar 1m frame), skips the forming last row,
        and admits only this session's RTH bars (>= 09:30 ET, session
        date) — the session record stays a session record.
v1.0 — 2026-08-13 — THE MISSING OBJECT. `LiquidityMapper.analyze()` opens with
        `lmap = LiquidityMap()` and re-derives every pool from the candle window
        on EVERY CALL. Nothing survives a tick, so:
          · `touch_count` is NOT a running count — it is `len(cluster)`, i.e.
            how many bars in the lookback happened to sit at that level when the
            map was last rebuilt. A floor price hammers into five times today
            does not accumulate.
          · `swept` / `rejection_confirmed` are per-build snapshots. Same defect
            class LIQ.3 already fixed one level down, where `closes_beyond` was
            a birth-time snapshot that had to become a per-tick question.
          · a clean SINGLE-touch low that price respects three times never
            becomes a pool at all — `_find_pools` requires >=2 equal bars within
            EQUAL_LEVEL_PCT.
        So there was no object that could answer "is this floor holding?", and
        nothing was archived: the input to every named-level decision existed
        only in RAM. Same class as the chain archive before 2026-07-23.

        OPERATOR'S SPEC, 2026-08-13, verbatim on the part that matters:
        *"the wick counts as a touch, but only a close counts as acceptance or
        rejection."* Hence THREE counters per level, never one — `touches`
        (wick), `holds` (closed back on the origin side), `breaches` (closed
        beyond). A single number cannot say whether a level is being defended
        or given up, which is the entire question.

        *"It should live on the standalone bot boxes."* Written per-box under
        `data/liquidity_ledger/<date>/<SYMBOL>.json`, next to the chain archive
        and by the same convention. The bot owns its own level book; control is
        a consumer, never the source.

        RESET AT RTH OPEN, seeded with PDH/PDL and the prior session's extremes,
        carrying at least MIN_LEVELS_PER_SIDE highs and lows.

⚠️ FIRE-AND-FORGET. Every public entry point swallows every exception. A ledger
   failure must never reach the trading loop — `chain_snapshot.py` is the model
   and the reason: this is telemetry, and telemetry that can halt trading is a
   liability, not an asset.

⚠️ v1.0 WRITES AND DOES NOT GATE. Nothing reads this to make a decision yet.
   Prove the levels are the ones a human would have drawn before wiring them to
   anything that fires.

STATE, not an event log. The file is the CURRENT book, rewritten atomically on
change. Timing of individual touches is deliberately out of scope for v1 — the
counts are what the floor thesis needs, and an append log can be added later
without changing this schema.
"""

import json
import os
import tempfile
from typing import Dict, List, Optional

import logging

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# Self-locate: <repo>/analysis/liquidity_ledger.py -> <repo>/data/liquidity_ledger/
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ⚠️ OVERRIDABLE, AND IT HAS TO BE. The A2.3 hydrate makes `reset_for_session`
# READ THIS PATH BACK, so anything that writes here is state the next run
# inherits. Under test that meant counts ACCUMULATED across invocations
# (`holds == 3` from one bar), and worse: `data/liquidity_ledger/` was not in
# .gitignore, so the deploy line's `git add -A` would have committed live fleet
# data into the repo - the MANIFEST.txt / trades.db precedent exactly.
# Tests point `OT_LEDGER_ROOT` at a temp dir; production is unchanged.
_OUT_ROOT = os.environ.get(
    "OT_LEDGER_ROOT", os.path.join(_REPO_ROOT, "data", "liquidity_ledger"))

# Operator: "capture at least 3 previous highs & lows".
MIN_LEVELS_PER_SIDE = 3
# A level is "touched" when a bar's wick reaches within this fraction of it.
# Not zero: an exact float equality on a price never fires.
# ── LIQ.7 (2026-08-15) — ONE DEFINITION OF A ZONE ────────────────────────────
# Was 0.0002 (2bp). Raised to 0.002 (20bp) to MATCH `within_pct(..., 0.002)`,
# the tolerance `liquidity_mapper._add_named_pool` already uses to decide two
# prices are the same level. Operator: *"Reach within a small margin of error is
# good enough. A level is a ZONE, not a fixed number."*
# ⚠️ THE OLD VALUE UNDERCOUNTED EXACTLY WHAT THE SIZING RULE REWARDS. On a $580
# underlying 2bp is 12 CENTS — a clean approach that reversed just short of the
# level did not register as a test at all, so the most-defended levels looked
# untested. 20bp is $1.16 there, which is the zone the rest of the system
# already treats as one level.
# ⚠️ AND IT CHANGES WHAT EVERY LEDGER NUMBER MEANS. Counts before and after this
# are not comparable; the ledger has collected nothing yet, so there is no
# history to invalidate.
TOUCH_TOL_PCT = float(os.environ.get("OT_LEDGER_TOUCH_TOL", "0.002"))


class Level:
    """One horizontal level and its running contact history.

    THREE COUNTERS, per the operator's rule. `touches` is wick contact and says
    nothing about who won; `holds` and `breaches` are decided by the CLOSE and
    are the only two that carry information about whether the level is being
    defended.
    """

    __slots__ = ("price", "kind", "name", "is_named", "touches", "holds",
                 "breaches", "first_seen", "last_touch", "last_result")

    def __init__(self, price: float, kind: str, name: str = "",
                 is_named: bool = False, first_seen: str = ""):
        self.price = round(float(price), 4)
        self.kind = kind                      # "high" | "low"
        self.name = name                      # PDH / PDL / PRIOR_HIGH_2 / ...
        self.is_named = bool(is_named)
        self.touches = 0
        self.holds = 0
        self.breaches = 0
        self.first_seen = first_seen
        self.last_touch = ""
        self.last_result = ""                 # "hold" | "breach" | ""

    def as_dict(self) -> dict:
        return {
            "price": self.price, "kind": self.kind, "name": self.name,
            "is_named": self.is_named, "touches": self.touches,
            "holds": self.holds, "breaches": self.breaches,
            "first_seen": self.first_seen, "last_touch": self.last_touch,
            "last_result": self.last_result,
        }


class LiquidityLedger:
    """Session-scoped, persistent level book for ONE symbol on ONE box."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.date = ""
        self.levels: List[Level] = []
        self.last_bar_ts = ""     # A2.4 — newest CLOSED bar fed, ISO w/ offset.
        self._dirty = False

    # ── session lifecycle ────────────────────────────────────────────────────

    def reset_for_session(self, date: str, seeds=None) -> None:
        """Clear and reseed. Called at RTH open.

        `seeds` is an iterable of (price, kind, name, is_named). The CALLER
        supplies them because the ledger must not own a second definition of
        what a prior high is — `LiquidityMapper` already owns that, and a
        competing derivation here is exactly the second-lineage failure
        WORKING_AGREEMENT 7 forbids.
        """
        try:
            self.date = date
            self.levels = []
            self.last_bar_ts = ""
            # A2.3 — a restart happens on every bake, and this reset used to be
            # the wipe: write() had no reader, so the "running record" lost its
            # morning on every mid-session restart and then OVERWROTE the good
            # file with zeros. Same-date state is hydrated back first; the
            # caller's seeds then merge through add_level (which dedupes), so
            # new mapper levels still join.
            self._hydrate_same_date(date)
            for s in (seeds or []):
                self.add_level(*s, first_seen=date)
            self._dirty = True
        except Exception as e:                                 # noqa: BLE001
            logger.debug("ledger reset skipped: %s", e)

    def _hydrate_same_date(self, date: str) -> None:
        """Load this symbol's same-date book back from disk, if one exists."""
        path = os.path.join(_OUT_ROOT, date, f"{self.symbol}.json")
        try:
            if not os.path.exists(path):
                return
            with open(path) as f:
                payload = json.load(f)
            if payload.get("schema_version") != SCHEMA_VERSION:
                logger.warning("[ledger] %s: schema %s != %s — starting clean",
                               path, payload.get("schema_version"),
                               SCHEMA_VERSION)
                return
            # LIQ.7 — counts taken under a different zone MEAN something else.
            if float(payload.get("touch_tol_pct", -1)) != TOUCH_TOL_PCT:
                logger.warning("[ledger] %s: touch_tol %s != running %s — "
                               "counts are not comparable, starting clean",
                               path, payload.get("touch_tol_pct"),
                               TOUCH_TOL_PCT)
                return
            for d in payload.get("levels", []):
                lv = Level(d["price"], d["kind"], d.get("name", ""),
                           d.get("is_named", False), d.get("first_seen", ""))
                lv.touches, lv.holds = int(d.get("touches", 0)), int(d.get("holds", 0))
                lv.breaches = int(d.get("breaches", 0))
                lv.last_touch = d.get("last_touch", "")
                lv.last_result = d.get("last_result", "")
                self.levels.append(lv)
            self.last_bar_ts = str(payload.get("last_bar_ts", "") or "")
            logger.info("[ledger] hydrated %d level(s) for %s from disk "
                        "(restart survival, last bar %s)",
                        len(self.levels), date, self.last_bar_ts or "n/a")
        except Exception as e:                                 # noqa: BLE001
            logger.warning("[ledger] hydrate failed (%s) — starting clean", e)
            self.levels = []
            self.last_bar_ts = ""

    def add_level(self, price: float, kind: str, name: str = "",
                  is_named: bool = False, first_seen: str = "") -> None:
        try:
            if not price or price <= 0 or kind not in ("high", "low"):
                return
            for lv in self.levels:
                if lv.kind == kind and abs(lv.price - price) <= \
                        abs(price) * TOUCH_TOL_PCT:
                    return                                     # already held
            self.levels.append(Level(price, kind, name, is_named,
                                     first_seen or self.date))
            self._dirty = True
        except Exception as e:                                 # noqa: BLE001
            logger.debug("ledger add_level skipped: %s", e)

    # ── the update, and the whole point of the module ────────────────────────

    def feed_frame(self, df_1m) -> int:
        """Feed every CLOSED session bar newer than `last_bar_ts`. Returns count.

        A2.4 — the old wiring fed only `iloc[-2]` behind a one-stamp guard: it
        prevented refeeding ONE bar but could not see a GAP, so any tick slower
        than ~75s silently dropped closed bars — on exactly the busy tape most
        likely to be testing levels. This walks the whole frame instead:
          · the LAST row is the forming bar and is never fed;
          · a bar is fed once — `last_bar_ts` (persisted, so a restart plus the
            A2.3 hydrate recovers the bake gap from the 60-bar frame);
          · only THIS session's RTH bars (index date == self.date, >= 09:30 ET)
            — the session record stays a session record; the frame also carries
            yesterday/pre-market rows and those are not the session.
        Timestamps compare as strings: same session, same UTC offset, one
        format — and the DST changeover never lands inside RTH.
        """
        try:
            if df_1m is None or getattr(df_1m, "empty", True) or len(df_1m) < 2:
                return 0
            fed = 0
            for ts, row in df_1m.iloc[:-1].iterrows():         # [-1] is FORMING
                if str(ts.date()) != self.date:
                    continue
                if (ts.hour, ts.minute) < (9, 30):             # index is ET
                    continue
                stamp = str(ts)
                if self.last_bar_ts and stamp <= self.last_bar_ts:
                    continue
                self.on_closed_bar(float(row["high"]), float(row["low"]),
                                   float(row["close"]), ts=stamp)
                fed += 1
            return fed
        except Exception as e:                                 # noqa: BLE001
            logger.debug("ledger feed_frame skipped: %s", e)
            return 0

    def on_closed_bar(self, high: float, low: float, close: float,
                      ts: str = "") -> None:
        """Apply ONE CLOSED bar to every level.

        THE RULE, and it is the operator's, not an interpretation:
          · WICK reaches the level            -> touches += 1
          · CLOSE beyond it                   -> breaches += 1   (acceptance)
          · CLOSE back on the origin side     -> holds    += 1   (rejection)
        A bar that never reaches the level does nothing at all — it is neither
        a hold nor a breach, and counting it as either is how a level that was
        simply far away starts looking defended.

        ⚠️ CLOSED BARS ONLY. Feeding a forming bar would count a wick that has
        not finished printing and a close that is not a close.
        """
        try:
            high, low, close = float(high), float(low), float(close)
            # A2.4 — the ledger's own high-water mark for "which bars have I
            # consumed". Set HERE (not only in feed_frame) so the invariant
            # holds on every entry point, and so write() persists it for the
            # restart hydrate.
            if ts and ts > (self.last_bar_ts or ""):
                self.last_bar_ts = ts
                self._dirty = True
            for lv in self.levels:
                tol = abs(lv.price) * TOUCH_TOL_PCT
                if lv.kind == "high":
                    reached = high >= lv.price - tol
                    accepted = close > lv.price + tol
                else:
                    reached = low <= lv.price + tol
                    accepted = close < lv.price - tol
                if not reached:
                    continue
                lv.touches += 1
                lv.last_touch = ts
                if accepted:
                    lv.breaches += 1
                    lv.last_result = "breach"
                else:
                    lv.holds += 1
                    lv.last_result = "hold"
                self._dirty = True
        except Exception as e:                                 # noqa: BLE001
            logger.debug("ledger on_closed_bar skipped: %s", e)

    # ── read side (nothing gates on this in v1) ──────────────────────────────

    def floors_below(self, price: float) -> List[Level]:
        """Levels below `price`, nearest first. The floor thesis' input."""
        try:
            out = [lv for lv in self.levels
                   if lv.kind == "low" and lv.price < price]
            return sorted(out, key=lambda lv: -lv.price)
        except Exception:                                      # noqa: BLE001
            return []

    def ceilings_above(self, price: float) -> List[Level]:
        try:
            out = [lv for lv in self.levels
                   if lv.kind == "high" and lv.price > price]
            return sorted(out, key=lambda lv: lv.price)
        except Exception:                                      # noqa: BLE001
            return []

    def coverage(self) -> Dict[str, int]:
        highs = sum(1 for lv in self.levels if lv.kind == "high")
        lows = sum(1 for lv in self.levels if lv.kind == "low")
        return {"highs": highs, "lows": lows,
                "meets_minimum": int(highs >= MIN_LEVELS_PER_SIDE
                                     and lows >= MIN_LEVELS_PER_SIDE)}

    # ── persistence ──────────────────────────────────────────────────────────

    def write(self, force: bool = False) -> bool:
        """Atomic rewrite of the current book. Returns True if it wrote.

        Atomic because a strategy may read this file while the loop writes it;
        a half-written JSON would be read as a corrupt or EMPTY level set, and
        an empty level set is indistinguishable from "no levels found" — a
        silent wrong answer rather than a loud failure.
        """
        try:
            if not self._dirty and not force:
                return False
            if not self.date:
                return False
            day_dir = os.path.join(_OUT_ROOT, self.date)
            os.makedirs(day_dir, exist_ok=True)
            path = os.path.join(day_dir, f"{self.symbol}.json")
            payload = {
                "schema_version": SCHEMA_VERSION,
                "symbol": self.symbol,
                "date": self.date,
                "coverage": self.coverage(),
                "touch_tol_pct": TOUCH_TOL_PCT,
                "last_bar_ts": self.last_bar_ts,
                "levels": [lv.as_dict() for lv in self.levels],
            }
            fd, tmp = tempfile.mkstemp(dir=day_dir, suffix=".tmp")
            with os.fdopen(fd, "w") as f:
                json.dump(payload, f, default=str)
            os.replace(tmp, path)                  # atomic on POSIX
            self._dirty = False
            return True
        except Exception as e:                                 # noqa: BLE001
            logger.debug("ledger write skipped: %s", e)
            return False


_LEDGER: Optional[LiquidityLedger] = None


def get_ledger(symbol: str = "") -> LiquidityLedger:
    global _LEDGER
    if _LEDGER is None:
        _LEDGER = LiquidityLedger(symbol or os.environ.get("OT_INSTRUMENT", "?"))
    return _LEDGER
