"""
analysis/entry_snapshot.py — the entry-time structural picture, captured. v1.2

v1.2 — 2026-08-04 — the v1.1 fix routed its logs through a helper, and the
        census still counted all five SILENT: it reads the HANDLER BODY, so a
        log behind an indirection is invisible to it. Logger calls are now
        inline; the helper only throttles. Hiding a log from the census would
        defeat the census.
v1.1 — 2026-08-04 — NO SILENT SWALLOWS. v1.0 shipped five `except: return
        None` handlers and the nightly census (tests/swallow_audit.py, backlog
        W.2) counted every one of them as SILENT — in TIER 1, the decision-input
        tier. That is the exact pattern the operator named as the go-live risk,
        added hours after saying so. Each except now routes through _quiet(),
        which logs at DEBUG once per site per process: loud enough that a broken
        capture is findable, quiet enough that it can never spam a session or
        become the reason a fill is not recorded. Behaviour is otherwise
        byte-identical — every handler still returns exactly what it returned.

v1.0 — 2026-08-04 — NEW. Captures, on every filled entry, the FVG zones and
        structural context AS THE LIVE ENGINE HELD THEM at that instant, so the
        TC.2 exit-mechanism bake-off (BoS vs trail vs 5m-FVG, counterfactual on
        identical entries) is computable from banked rows instead of guessed at.
        ROADMAP TC.2 names this precursor and flags it as pre-freeze safe;
        nothing in the repo produced it.

WHY IT CANNOT BE RECONSTRUCTED LATER, which is the whole argument for spending a
column on it:

  - **BoS can be** — and this file deliberately does NOT capture it. `BOSTracker`
    seeds from entry price and direction (both already on the trade row) and
    ratchets forward on closed 1m candles, so a BoS counterfactual is a pure
    function of the post-entry tape. Capturing it would be storage for nothing.
    Stated explicitly because the opposite was assumed before HEAD was read.
  - **The FVG anchor cannot.** The trail anchors to the nearest unfilled in-favor
    gap on the frame `_fvg_frame()` selects, and that frame is the LIVE rolling
    window (`TIMEFRAMES[tf]["candles"]`), which is CONTINUOUS across sessions on
    5m. A replay resampled from the banked RTH 1m tape is session-scoped, so a
    gap formed across the overnight boundary exists live and cannot exist
    offline. That is the same class of divergence defect S found in the replay's
    1m window, and it means an offline reconstruction is not the same object.
  - **Frame DEPTH cannot.** A vote taken on a starved frame is not the vote a
    warm frame would have cast (AK: three of four timeframes had never voted).
    Depth is provenance — it says whether the entry-time picture was even
    entitled to an opinion — and it is gone the moment the tick ends.

CONTRACT — this module is OBSERVABILITY ONLY.
  - It is called AFTER the fill is confirmed and the row is written. It cannot
    reach the entry decision, the size, the strike or any exit.
  - `build()` NEVER raises. A capture failure must never touch a live position;
    it returns a payload carrying `err` and the caller logs it. Silence is the
    failure mode this repo keeps paying for, so the caller gets a boolean and an
    error string rather than a swallowed exception.
  - It reads. It computes nothing the engines do not already compute, and it
    imports the exit engine's OWN gap finders rather than re-deriving them —
    a second lineage would make the counterfactual measure this file instead of
    the trail. The import is deliberately LAZY (inside the function): module-level
    it would drag the TastyTrade SDK into every offline consumer of `analysis/`,
    and the payload is read offline far more often than it is written.

PAYLOAD (JSON, one TEXT column `trades.entry_snapshot`; keys are short because
this is written once per trade and read by tooling, not by eye):

    v      schema version (int) — bump on any key change, never repurpose a key
    at     capture time, UTC ISO (same base as entry_time — never ET)
    px     underlying at capture
    dir    "long" / "short" / "neutral" (condor legs are neutral: no in-favor side)
    frame  "5m" / "1m" — the frame `_fvg_frame()` selected, i.e. the one the
           trail would actually anchor to on this tick
    anchor {t,b} of the nearest unfilled in-favor gap, or null if none existed —
           null is a REAL observation (the trail had no anchor and fell back to
           the percentage leash), not a missing value
    fvg    up to FVG_CAP most-recent gaps on the selected frame: t/b/d/i
    swing  seq / res / sup / hi / lo from the live StructureMap
    depth  bar count per timeframe as held at entry
    err    present ONLY on failure, with the exception text
"""

import json
import logging
from typing import Any, Dict, Optional

from utils.time_utils import ts_for_db

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# One DEBUG line per site per process. A capture failure must not spam a session
# (that is how three dead timeframes went unnoticed) and must not be invisible
# either (that is how everything in the 2026-07-27 week hid). See W.2.
_quiet_seen: set = set()


def _first(where: str) -> bool:
    """True the FIRST time a site fails, False forever after.

    The throttle is a helper but the logger call is left INLINE in every
    handler on purpose: tests/swallow_audit.py reads the handler body, so a
    log emitted through an indirection is counted SILENT. Hiding a log from
    the census would defeat the census — v1.1 was written that way and the
    audit caught it.
    """
    if where in _quiet_seen:
        return False
    _quiet_seen.add(where)
    return True

# Bound the row: the gap list is for reconstructing which zones existed, not an
# archive. Most recent first, so the cap drops the oldest and least relevant.
FVG_CAP = 12


def _frames(ctx: Dict[str, Any]):
    """The two frames the trail chooses between, plus the vote frames for depth."""
    data = ctx.get("data") or {}
    df_1m = ctx.get("df_1m")
    df_5m = ctx.get("df_5m")
    return df_1m, df_5m, data


def _depths(df_1m, df_5m, data) -> Dict[str, Optional[int]]:
    out: Dict[str, Optional[int]] = {}
    for name, frame in (("1m", df_1m), ("5m", df_5m),
                        ("15m", data.get("15m")), ("1h", data.get("1h"))):
        try:
            out[name] = int(len(frame)) if frame is not None else None
        except Exception as exc:                             # noqa: BLE001
            if _first(f"depth:{name}"):
                logger.debug("entry_snapshot depth:%s failed (%s: %s) — field "
                             "omitted; once per process", name,
                             type(exc).__name__, exc)
            out[name] = None
    return out


def _swing(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Structural context from the LIVE StructureMap — not recomputed.

    `hi`/`lo` are the most recent swing points the analyzer confirmed, which is
    what a structure-based exit would key off; `res`/`sup` are its nearest
    levels to price. All five can legitimately be None early in a session, and
    None is recorded as None rather than 0.0 — a real level is never exactly
    zero, so a zero here would be indistinguishable from "not formed yet".
    """
    smap = ctx.get("structure")
    if smap is None:
        return {}

    def _last(points):
        try:
            return round(float(points[-1].price), 4) if points else None
        except Exception as exc:                             # noqa: BLE001
            if _first("swing:last"):
                logger.debug("entry_snapshot swing:last failed (%s: %s)",
                             type(exc).__name__, exc)
            return None

    def _lvl(value):
        try:
            return round(float(value), 4) if value is not None else None
        except Exception as exc:                             # noqa: BLE001
            if _first("swing:level"):
                logger.debug("entry_snapshot swing:level failed (%s: %s)",
                             type(exc).__name__, exc)
            return None

    return {
        "seq": getattr(smap, "structure_sequence", None),
        "res": _lvl(getattr(smap, "nearest_resistance", None)),
        "sup": _lvl(getattr(smap, "nearest_support", None)),
        "hi":  _last(getattr(smap, "swing_highs", None)),
        "lo":  _last(getattr(smap, "swing_lows", None)),
    }


def build(ctx: Dict[str, Any], direction: str) -> Dict[str, Any]:
    """Build the entry-time snapshot. NEVER raises — see the module contract."""
    payload: Dict[str, Any] = {"v": SCHEMA_VERSION, "at": ts_for_db()}
    try:
        direction = (direction or "").lower()
        df_1m, df_5m, data = _frames(ctx)
        price = float(ctx.get("price") or 0.0)

        payload["px"] = round(price, 4)
        payload["dir"] = direction
        payload["depth"] = _depths(df_1m, df_5m, data)
        payload["swing"] = _swing(ctx)

        # LAZY, and the module docstring says why. ExitEngine._fvg_frame is a
        # staticmethod, so no engine is constructed and no broker session is
        # touched — we are asking the exit engine which frame IT would use.
        from execution.exit_engine import (            # noqa: PLC0415
            ExitEngine, _find_1m_fvgs, _nearest_unfilled_fvg_in_favor,
        )

        frame = ExitEngine._fvg_frame(df_1m, df_5m)
        payload["frame"] = "5m" if (frame is not None and frame is df_5m) else "1m"

        gaps = _find_1m_fvgs(frame) if frame is not None else []
        payload["fvg"] = [
            {"t": round(float(g.top), 4), "b": round(float(g.bottom), 4),
             "d": g.direction, "i": int(g.index)}
            for g in gaps[:FVG_CAP]
        ]

        # A condor leg has no in-favor side, so it gets no anchor by definition —
        # recorded as null, which is the honest answer rather than an arbitrary
        # side. Its gap list is still worth having: the zones bound where the
        # underlying had room to travel toward either short strike.
        anchor = None
        if direction in ("long", "short") and frame is not None and price > 0:
            g = _nearest_unfilled_fvg_in_favor(frame, current_price=price,
                                               direction=direction)
            if g is not None:
                anchor = {"t": round(float(g.top), 4),
                          "b": round(float(g.bottom), 4)}
        payload["anchor"] = anchor

    except Exception as exc:                                 # noqa: BLE001
        if _first("build"):
            logger.debug("entry_snapshot build failed (%s: %s) — payload "
                         "carries err and the caller warns",
                         type(exc).__name__, exc)
        payload["err"] = f"{type(exc).__name__}: {exc}"

    return payload


def to_json(ctx: Dict[str, Any], direction: str) -> str:
    """Serialised `build()`. Also never raises — a payload that cannot be
    serialised still returns valid JSON carrying the reason, because a row with
    unparseable text in this column would be worse than a row with none."""
    payload = build(ctx, direction)
    try:
        return json.dumps(payload, separators=(",", ":"))
    except Exception as exc:                                 # noqa: BLE001
        if _first("serialise"):
            logger.debug("entry_snapshot serialise failed (%s: %s)",
                         type(exc).__name__, exc)
        return json.dumps({"v": SCHEMA_VERSION, "at": ts_for_db(),
                           "err": f"serialise {type(exc).__name__}: {exc}"})
