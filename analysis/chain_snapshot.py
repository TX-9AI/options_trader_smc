"""
analysis/chain_snapshot.py — full option-chain archival (LOG-ONLY, never trades).
v1.0 — 2026-07-23 — initial release.

WHY THIS EXISTS
    The bot already fetches the COMPLETE 0DTE chain every ~15s tick — bid, ask,
    mark, delta, gamma, theta, vega, IV, open interest and volume for every
    strike. Roughly 23,000 full-chain snapshots per fleet-day. Until this
    module, 100% of it was discarded except the single contract that happened
    to be selected, serialized into the signal_journal `scored` event — and
    even that dropped gamma and vega.

    Option chains are NOT reconstructible after the session. Unlike the 1-min
    OHLC tape (replayable forever) or swing pivots (deterministic from tape),
    a quote for a strike nobody selected is gone permanently at 16:00. There is
    no vendor, no backfill, no replay that recovers it.

    That makes every un-archived session a permanent hole in the dataset for:
      * ANY future strike-selection rule, tested retroactively instead of live
        (pitchfork rail-anchored strikes, liquidity-ranked, delta-based,
        VWAP-anchored on the names where VWAP works)
      * the IV surface and skew through the day
      * real bid/ask width by strike and hour — the noise band that trips a
        premium-relative stop
      * empirical theta decay and delta drift on 0DTE
      * the inputs to our own GEX calculation, currently computed then thrown
        away

DESIGN RULES (inherited verbatim from signal_journal.py — non-negotiable):
  1. This module can NEVER crash the trading loop. Every public function
     swallows every exception (logged at DEBUG). A full disk, a bad payload, a
     permissions error — all degrade to "no snapshot", never to a raised
     exception. The bot's behavior with this module present is byte-identical
     to its behavior with the module deleted.
  2. LOG-ONLY. Imports nothing from execution/, risk/, strategy/,
     notifications/. Gates nothing, scores nothing, reads no DB.
  3. NO EXTRA MARKET-DATA LOAD. It serializes an OptionsChain object the
     caller ALREADY has in hand. No fetch, no API call, no DXFeed subscription.
  4. Append-only gzipped JSONL, one line per snapshot:
         data/chain_snapshots/<YYYY-MM-DD>/<SYMBOL>.jsonl.gz
     Written with gzip mode "ab" — each line is its own gzip member, which is
     valid multi-member gzip and reads back transparently via gzip.open(),
     `zcat`, or pandas. Append-safe across restarts; no rewrite, no temp file.

CADENCE
    Default 5 minutes (OT_CHAIN_SNAPSHOT_MIN). Rationale: every-tick archival
    is ~28 MB/box/day (~420 MB/day fleet-wide) which is not worth it, while
    5-minute is ~1.4 MB/box/day (~21 MB/day fleet, ~40 MB/month gzipped) and
    still resolves any intraday question we have posed. Set to 0 to disable.

    The cadence is wall-clock aligned, not tick-aligned: a snapshot fires on
    the first tick at or after each 5-minute boundary. Restarts therefore do
    not shift the grid, and two boxes are directly comparable.
"""

import gzip
import json
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

# Self-locate: <repo>/analysis/chain_snapshot.py -> <repo>/data/chain_snapshots/
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT_ROOT = os.path.join(_REPO_ROOT, "data", "chain_snapshots")

try:
    from config import INSTRUMENT as _SYMBOL
except Exception:                       # config unreadable — still never raise
    _SYMBOL = os.environ.get("OT_INSTRUMENT", "UNKNOWN")

try:
    _INTERVAL_MIN = float(os.environ.get("OT_CHAIN_SNAPSHOT_MIN", "5"))
except Exception:
    _INTERVAL_MIN = 5.0

# Last wall-clock bucket written, e.g. "2026-07-23T14:35". Module-level so the
# cadence survives across calls without the caller holding state.
_last_bucket: str = ""


def _round(x, nd=4):
    try:
        return round(float(x), nd)
    except Exception:
        return None


def _contract_row(c) -> dict:
    """One contract, FULL fidelity. Includes gamma and vega, which the
    signal_journal contract context drops."""
    return {
        "occ":    getattr(c, "symbol", "") or "",
        "type":   getattr(c, "option_type", "") or "",
        "strike": _round(getattr(c, "strike", 0.0), 4),
        "bid":    _round(getattr(c, "bid", 0.0), 4),
        "ask":    _round(getattr(c, "ask", 0.0), 4),
        "mark":   _round(getattr(c, "mark", 0.0), 4),
        "delta":  _round(getattr(c, "delta", 0.0), 5),
        "gamma":  _round(getattr(c, "gamma", 0.0), 6),
        "theta":  _round(getattr(c, "theta", 0.0), 5),
        "vega":   _round(getattr(c, "vega", 0.0), 5),
        "iv":     _round(getattr(c, "iv", 0.0), 5),
        "oi":     int(getattr(c, "open_interest", 0) or 0),
        "vol":    int(getattr(c, "volume", 0) or 0),
    }


def _bucket(now: datetime) -> str:
    """Wall-clock aligned cadence bucket. 5-minute default -> 14:30, 14:35, ..."""
    if _INTERVAL_MIN <= 0:
        return ""
    slot = int(now.hour * 60 + now.minute) // int(max(_INTERVAL_MIN, 1))
    return f"{now.strftime('%Y-%m-%d')}#{slot}"


def snapshot(chain, underlying_price=None, regime=None, force: bool = False):
    """
    Archive one full chain snapshot if the cadence bucket has advanced.

    Args:
        chain:            an OptionsChain (needs .calls / .puts iterables)
        underlying_price: spot at snapshot time, if the caller has it
        regime:           optional regime label string, purely for convenience
                          when slicing the archive later
        force:            bypass the cadence (used by tests)

    Swallows ALL exceptions by design. Returns True if a line was written.
    """
    global _last_bucket
    try:
        if _INTERVAL_MIN <= 0 and not force:
            return False
        if chain is None:
            return False

        now = datetime.now(tz=ET)
        bucket = _bucket(now)
        if not force:
            if bucket == _last_bucket:
                return False

        calls = list(getattr(chain, "calls", None) or [])
        puts = list(getattr(chain, "puts", None) or [])
        if not calls and not puts:
            return False

        row = {
            "ts_et":   now.isoformat(timespec="seconds"),
            "symbol":  _SYMBOL,
            "event":   "chain_snapshot",
            "expiry":  getattr(chain, "expiry", "") or "",
            "underlying": _round(underlying_price, 4) if underlying_price else None,
            "regime":  regime if isinstance(regime, str) else None,
            "n_calls": len(calls),
            "n_puts":  len(puts),
            "contracts": [_contract_row(c) for c in calls]
                         + [_contract_row(c) for c in puts],
        }

        day_dir = os.path.join(_OUT_ROOT, now.strftime("%Y-%m-%d"))
        os.makedirs(day_dir, exist_ok=True)
        path = os.path.join(day_dir, f"{_SYMBOL}.jsonl.gz")
        # "ab" -> a new gzip member per line. Valid multi-member gzip, append
        # safe across restarts, readable by gzip.open / zcat / pandas.
        with gzip.open(path, "ab") as f:
            f.write((json.dumps(row, default=str) + "\n").encode("utf-8"))

        _last_bucket = bucket
        return True
    except Exception as e:                        # noqa: BLE001 — by design
        logger.debug(f"chain_snapshot write skipped: {e}")
        return False
