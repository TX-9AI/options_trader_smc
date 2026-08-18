#!/usr/bin/env python3
"""
analysis/pitchfork_observer.py — v1.0 — 2026-08-11 — PF.2

BOX-LOCAL PITCHFORK OBSERVATION. Builds the DAILY and HOURLY forks from the
box's OWN frames, caches them, and journals where price sits in each channel.

⚠️⚠️ EVALUATION DATE: **FRI 2026-08-14**. DELETE CRITERION: if no daily fork
builds on any box, the frame fix did not take and this overlay is inert — remove
it. Standing rule agreed 2026-08-12: an observer ships with an evaluation date
and a delete criterion, or it does not ship.

⚠️ WEIGHT 0. NOTHING GATES ON THIS. It scores nothing, vetoes nothing and is
read by no strategy. §11 of the white paper is explicit that v1 ships observing
only, and §12's stated risk is CONSUMER SPRAWL — "building more than one
application before any is proven would repeat the mistake of shipping four
engine changes into a frozen window". This module exists to answer ONE question
with data: when continuation fires, where was price relative to the rail?

WHY IT CAN SHIP DURING THE FREEZE. EPOCH 2 hands off L1/L2/entry logic Aug 17 →
Aug 30, but "everything else this epoch is offline or log-only". A weight-0
overlay that gates nothing IS log-only, so unlike the label-affecting items it
does not face the Mon Aug 17 deadline and can collect through the freeze.

⚠️ BOX-LOCAL BY DESIGN, and this is an architectural requirement, not a
convenience. Operator, 2026-08-11: "for the bots to remain independent and
modular, that has to take place on their boxes… they were designed to function
without a controller. The controller is only intended if you're running a fleet
of boxes." So the frames come from the box's own feed store, the fork is built
on the box, and the journal is written on the box. Nothing here reaches for the
control server, and a single box is complete on its own.

WHAT MADE THIS POSSIBLE TONIGHT: the boxes were found to hold **84 daily bars**
already (2026-06-11 → 08-11, verified on SPX and GLD), while
TIMEFRAMES["1d"]["candles"] handed the engines only 10. The history was never
missing — the frame was clipped. Raising that number is the whole prerequisite.

⚠️ THE ANCHOR IS §4.3.6 CONTAINMENT, NOT §4.3 PIVOT SELECTION. On the same
tapes the pivot rule refuses everything tested (SEPARATION, STRUCTURAL, or
FEWER_THAN_3_ALTERNATING_PIVOTS) while containment builds forks with 97-100% of
closes inside. Both are available; the variant and the anchor are logged on
every record so the choice is settled by data.

NEVER RAISES. Every entry point swallows, because an observation module must
not be able to affect a trading decision by failing.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# rebuild cadence — a DAILY fork changes only when a daily bar closes, so
# rebuilding every 15s tick is waste. 5 min matches chain_snapshot's grid.
REBUILD_MIN = float(os.environ.get("OT_PF_REBUILD_MIN", "5"))
OBSERVE = os.environ.get("OT_PF_OBSERVE", "1") == "1"

_cache: Dict[str, Any] = {"ts": 0.0, "forks": {}}


def _atr(df, n: int = 14) -> float:
    """Local ATR over the anchor frame. The pitchfork module owns no ATR
    definition (§4.3), and neither does this one beyond what it must pass in."""
    try:
        tail = df.tail(n + 1)
        tr, prev = [], None
        for _, r in tail.iterrows():
            if prev is not None:
                tr.append(max(float(r["high"]) - float(r["low"]),
                              abs(float(r["high"]) - prev),
                              abs(float(r["low"]) - prev)))
            prev = float(r["close"])
        return (sum(tr) / len(tr)) if tr else 0.0
    except Exception:                                          # noqa: BLE001
        return 0.0


def refresh(ctx: dict, symbol: str) -> Dict[str, Any]:
    """Rebuild both forks if the cadence has elapsed. Returns the cache."""
    if not OBSERVE:
        return {}
    now = time.time()
    if (now - _cache["ts"]) < REBUILD_MIN * 60.0 and _cache["forks"]:
        return _cache["forks"]
    try:
        from analysis.pitchfork import build_fork_contained, build_fork
    except Exception as exc:                                   # noqa: BLE001
        logger.debug("pitchfork import failed: %s", exc)
        return {}
    out: Dict[str, Any] = {}
    # ctx carries the frames under "data" (see build_context) — 1d and 1h are
    # the two ANCHOR timeframes; 5m/1m are deliberately excluded by §4.3 as
    # execution timeframes too noisy to anchor a persistent object.
    data = ctx.get("data") or {}
    for tf in ("1d", "1h"):
        df = data.get(tf)
        if df is None or len(df) < 12:
            continue
        atr = _atr(df)
        if atr <= 0:
            continue
        try:
            f = build_fork_contained(symbol, df, tf, atr)
            # §4.3 pivot rule logged ALONGSIDE, never instead — the anchor
            # choice is a measurement, not a decision made in this file.
            g = build_fork(symbol, df, tf, atr)
            out[tf] = {"contained": f, "pivot": g, "bars": len(df), "atr": atr}
        except Exception as exc:                               # noqa: BLE001
            logger.debug("pitchfork build failed %s %s: %s", symbol, tf, exc)
    _cache["ts"] = now
    _cache["forks"] = out
    return out


def _state(entry: Dict[str, Any], price: float) -> Optional[Dict[str, Any]]:
    f = entry.get("contained")
    if f is None or not price:
        return None
    try:
        idx = float(entry["bars"] - 1)
        if not f.is_born_by(int(idx)):
            return None                    # §4.4 — not yet knowable
        r = f.rails_at(idx)
        up, lo, ml = r["upper"], r["lower"], r["median"]
        w = up - lo
        return {
            "dir": f.direction, "variant": f.variant, "span": f.filters_passed,
            "born_idx": f.born_idx, "bars": entry["bars"],
            "upper": round(up, 4), "median": round(ml, 4), "lower": round(lo, 4),
            "width": round(w, 4),
            # THE NUMBER THE CONTINUATION JOIN NEEDS: 0% = on the lower tine,
            # 100% = on the upper, <0 or >100 = outside the channel.
            "pos_pct": (round((price - lo) / w * 100.0, 2) if w > 0 else None),
            "dist_ml_atr": (round((price - ml) / entry["atr"], 3)
                            if entry.get("atr") else None),
        }
    except Exception:                                          # noqa: BLE001
        return None


def rails_for(ctx: dict, symbol: str, tf: str = "daily"):
    """Rails + SLOPE for one timeframe, or None. The condor's only entry point.

    Returns {"upper","median","lower","slope","tf","pos_pct"} where `slope` is
    the rail's drift PER BAR of its own frame, signed.

    WHY THE SLOPE IS COMPUTED HERE and not by the caller: the rails are three
    linear functions of one index, so slope is `upper_at(i+1) - upper_at(i)` —
    exact, not fitted, and free. Deriving it anywhere else would mean a second
    place that knows the fork's geometry, which is the lineage split
    WORKING_AGREEMENT 7 forbids. `_state()` deliberately does not carry it
    because the journal records a POSITION, not a trajectory.

    Never raises. A missing, unborn or malformed fork returns None, and the
    caller's contract is that None means NO CONDOR.
    """
    if not OBSERVE:
        return None
    try:
        forks = refresh(ctx, symbol)
        entry = (forks or {}).get(tf)
        if not entry:
            return None
        f = entry.get("contained")
        if f is None:
            return None
        idx = float(entry["bars"] - 1)
        if not f.is_born_by(int(idx)):
            return None                    # 4.4 — not yet knowable
        r = f.rails_at(idx)
        nxt = f.rails_at(idx + 1.0)
        price = float(ctx.get("price") or 0.0)
        w = r["upper"] - r["lower"]
        return {
            "tf": tf,
            "upper": round(r["upper"], 4),
            "median": round(r["median"], 4),
            "lower": round(r["lower"], 4),
            # per-bar drift of the channel, signed. Any rail gives the same
            # number — they share one slope by construction.
            "slope": round(nxt["upper"] - r["upper"], 6),
            "pos_pct": (round((price - r["lower"]) / w * 100.0, 2)
                        if (w > 0 and price > 0) else None),
        }
    except Exception as exc:                                   # noqa: BLE001
        logger.debug("rails_for failed: %s", exc)
        return None


def snapshot(ctx: dict, symbol: str, journal=None) -> Optional[Dict[str, Any]]:
    """Build (cadenced) and journal one `pitchfork` observation. Never raises."""
    if not OBSERVE:
        return None
    try:
        price = float(ctx.get("price") or 0.0)
        forks = refresh(ctx, symbol)
        if not forks or price <= 0:
            return None
        rec: Dict[str, Any] = {}
        for tf, entry in forks.items():
            st = _state(entry, price)
            if st is not None:
                rec[tf] = st
            # record the §4.3 arm's verdict too, so the anchor comparison is
            # answerable from the journal rather than from a rerun
            rec.setdefault("pivot_built", {})[tf] = bool(entry.get("pivot"))
        if not rec:
            return None
        rec["price"] = round(price, 4)
        if journal is not None:
            try:
                journal("pitchfork", pitchfork=rec)
            except Exception:                                  # noqa: BLE001
                pass
        return rec
    except Exception as exc:                                   # noqa: BLE001
        logger.debug("pitchfork snapshot failed: %s", exc)
        return None


def stamp(ctx: dict, symbol: str) -> Optional[Dict[str, Any]]:
    """Compact fork state for stamping onto ANOTHER event (a disposition).

    This is what makes the continuation join possible: every fired trade
    carries where price sat in the channel at the moment it fired, so the
    comparison needs no timestamp alignment after the fact.
    """
    if not OBSERVE:
        return None
    try:
        price = float(ctx.get("price") or 0.0)
        forks = _cache.get("forks") or refresh(ctx, symbol)
        if not forks or price <= 0:
            return None
        out = {}
        for tf, entry in forks.items():
            st = _state(entry, price)
            if st is not None:
                out[tf] = {"pos_pct": st["pos_pct"], "dir": st["dir"],
                           "dist_ml_atr": st["dist_ml_atr"]}
        return out or None
    except Exception:                                          # noqa: BLE001
        return None
