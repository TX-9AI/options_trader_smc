"""
options_trader_v3/data/macro_data.py — VIX level, IV rank, and Fed/FOMC
calendar detection. v3.0
Fed days are a confluence modifier, not a hard block.
VIX level gates butterfly strategy and crisis mode.

v3.0 — 2026-07-10 — YAHOO-FINANCE PURGE / data stream mapping optimization. VIX now
        routes through the single shared TastyTrade feed: candle_feed.py
        subscribes "VIX" and _fetch_vix reads it via
        market_data.fetch_quote("VIX") (store-first, TastyTrade REST
        secondary). Fallback chain preserved: fresh -> stale snapshot ->
        conservative default 20.0, each step logged.
        ENTITLEMENT FLAG: if your DXFeed entitlement lacks the VIX index,
        the store path yields nothing and fetch_quote falls through to the
        TastyTrade REST market-data endpoint (InstrumentType.INDEX, "VIX") —
        that is the ONE sanctioned non-DXFeed alternative (same broker, no
        Yahoo). If BOTH fail on your entitlement, macro logs a WARNING and
        holds stale/default — verify on one box per the candle_feed FIRST-RUN
        CHECKLIST before fleet deploy.
"""

import logging
import json
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, List

import requests

from config import (
    VIX_LOW_THRESHOLD, VIX_BUTTERFLY_DISABLE, VIX_NO_ENTRY_THRESHOLD,
    MACRO_FETCH_INTERVAL_MIN, FOREX_FACTORY_URL, FED_EVENT_KEYWORDS,
    IV_RANK_HIGH
)

logger = logging.getLogger(__name__)


@dataclass
class MacroSnapshot:
    vix:            float = 0.0
    vix_regime:     str   = "UNKNOWN"   # LOW / NORMAL / ELEVATED / CRISIS
    iv_rank:        float = 0.0         # 0–100
    is_fed_day:     bool  = False
    fed_event_name: str   = ""
    macro_context:  str   = "NEUTRAL"   # RISK_ON / RISK_OFF / NEUTRAL

    # Derived gates
    butterfly_allowed:  bool = True
    butterfly_half_size: bool = False
    new_entries_allowed: bool = True

    fetched_at: float = 0.0


class MacroManager:
    """
    Manages VIX, IV rank, and economic calendar data.
    Refreshes on a configurable interval (default 60 min).
    """

    def __init__(self):
        self._snapshot: Optional[MacroSnapshot] = None
        self._last_fetch: float = 0

    def get(self, force: bool = False) -> MacroSnapshot:
        elapsed_min = (time.time() - self._last_fetch) / 60
        if force or self._snapshot is None or elapsed_min >= MACRO_FETCH_INTERVAL_MIN:
            self._snapshot = self._fetch()
            self._last_fetch = time.time()
        return self._snapshot

    def _fetch(self) -> MacroSnapshot:
        snap = MacroSnapshot(fetched_at=time.time())

        # ── VIX ───────────────────────────────────────────────────────────────
        snap.vix = self._fetch_vix()
        snap.vix_regime = self._classify_vix(snap.vix)

        # Derive gates from VIX
        if snap.vix >= VIX_NO_ENTRY_THRESHOLD:
            snap.new_entries_allowed = False
            snap.butterfly_allowed   = False
            snap.macro_context       = "RISK_OFF"
        elif snap.vix >= VIX_BUTTERFLY_DISABLE:
            snap.butterfly_allowed   = False
            snap.new_entries_allowed = True
            snap.macro_context       = "RISK_OFF"
        elif snap.vix >= 15:
            snap.butterfly_allowed      = True
            snap.butterfly_half_size    = True   # Half size butterfly
            snap.new_entries_allowed    = True
            snap.macro_context          = "NEUTRAL"
        else:
            snap.butterfly_allowed      = True
            snap.butterfly_half_size    = False
            snap.new_entries_allowed    = True
            snap.macro_context          = "RISK_ON"

        # ── Fed Calendar ──────────────────────────────────────────────────────
        is_fed, event_name = self._check_fed_day()
        snap.is_fed_day     = is_fed
        snap.fed_event_name = event_name
        if is_fed:
            # Fed days: disable butterfly (explosive moves expected)
            snap.butterfly_allowed = False
            logger.info(f"FED DAY detected: {event_name} — butterfly disabled")

        logger.info(
            f"Macro snapshot: VIX={snap.vix:.1f} [{snap.vix_regime}] "
            f"butterfly={'YES' if snap.butterfly_allowed else 'NO'} "
            f"fed_day={snap.is_fed_day} "
            f"entries={'YES' if snap.new_entries_allowed else 'NO'}"
        )
        return snap

    def _fetch_vix(self) -> float:
        """
        Fetch current VIX from the single shared TastyTrade feed
        (candle_feed subscribes "VIX"; fetch_quote reads the store first,
        TastyTrade REST market-data second — see v3.0 header for the
        entitlement flag). Falls back to stale value, then conservative
        default, fail-loud at each step.
        """
        try:
            from data.market_data import fetch_quote
            val = fetch_quote("VIX")
            if val is not None and float(val) > 0:
                logger.debug(f"VIX fetched via shared feed: {val:.2f}")
                return float(val)
        except Exception as e:
            logger.warning(f"shared-feed VIX fetch failed: {e}")

        # Use stale value if available
        if self._snapshot and self._snapshot.vix > 0:
            logger.warning("VIX unavailable from feed — using stale snapshot value")
            return self._snapshot.vix

        logger.warning("Could not fetch VIX — defaulting to 20 (conservative)")
        return 20.0

    def _classify_vix(self, vix: float) -> str:
        if vix < VIX_LOW_THRESHOLD:
            return "LOW"
        if vix < VIX_BUTTERFLY_DISABLE:
            return "NORMAL"
        if vix < VIX_NO_ENTRY_THRESHOLD:
            return "ELEVATED"
        return "CRISIS"

    def _check_fed_day(self) -> tuple:
        """
        Check Forex Factory JSON calendar for today's high-impact Fed events.
        Returns (is_fed_day, event_name).
        """
        try:
            resp = requests.get(FOREX_FACTORY_URL, timeout=10)
            if resp.status_code != 200:
                return False, ""

            events     = resp.json()
            today_str  = date.today().strftime("%m/%d/%Y")  # FF format
            today_date = date.today()

            for event in events:
                # FF dates: "Jun 21, 2026" format — normalize
                ev_date_str = event.get("date", "")
                try:
                    ev_date = datetime.strptime(ev_date_str, "%b %d, %Y").date()
                except ValueError:
                    continue

                if ev_date != today_date:
                    continue

                title    = event.get("title", "")
                impact   = event.get("impact", "")
                currency = event.get("currency", "")

                if currency != "USD":
                    continue
                if impact not in ("High",):
                    continue

                for keyword in FED_EVENT_KEYWORDS:
                    if keyword.lower() in title.lower():
                        logger.info(f"Fed event found: '{title}' impact={impact}")
                        return True, title

        except Exception as e:
            logger.warning(f"Fed calendar fetch failed: {e}")

        return False, ""


# Singleton
_macro_manager: Optional[MacroManager] = None


def get_macro_manager() -> MacroManager:
    global _macro_manager
    if _macro_manager is None:
        _macro_manager = MacroManager()
    return _macro_manager
