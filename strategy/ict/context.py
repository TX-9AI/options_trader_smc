"""
strategy/ict/context.py — ICT structural-context contract + degraded adapter. v1.0
v1.0 — 2026-08-18 — INITIAL (ICT setup suite, HANDOFF_FABLE_ICT_SETUPS).

WHAT THIS FILE IS. The seven ICT setups do not read smc/ internals, main.py
ctx keys, or analyzer objects directly — they read ONE object, `ICTContext`,
defined here. That object is the **structural-context contract v0.1**
requested from the core owner (docs/ICT_CORE_SPEC.md is the request; this
dataclass is its concrete shape). WA §7: the setup files are owned by this
suite; smc/ and main.py are owned by the core thread. This boundary is how
two owners share one repo without reaching into each other's files.

TWO BUILDERS, ONE SHAPE.
  - `build_context()` below is the DEGRADED adapter: it fills every field
    that today's public surface can honestly supply (ctx["smc"] SMCState,
    structure_analyzer FVGs/OBs, liquidity_mapper pools/sweeps, a pure
    clock) and registers every field it CANNOT fill in `unavailable`,
    keyed by the core-gap number in ICT_CORE_SPEC.md. built_by="adapter".
  - When the core delivers the authoritative snapshot (SPEC item G7), it
    constructs this same dataclass with built_by="core" and the gaps
    filled. The setups do not change — availability flags flip.

HONESTY RULES (STR.2 lineage):
  - None / sentinel means NOT COMPUTED, never zero. A missing field scores
    as UNAVAILABLE in the scorer, which caps completeness — it never
    silently scores 0 as if measured.
  - The adapter never fabricates a core-owed quantity from a proxy without
    marking it: `ote_zone` from a single displacement CANDLE (not a named
    multi-bar leg) is registered as "DEGRADED:G4" — usable for FORMING
    journals, barred from CONFIRM by the setups that require the real leg.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

CONTRACT_VERSION = "0.1"

# Core-gap registry — numbers match docs/ICT_CORE_SPEC.md
G1_SB_WINDOW      = "CORE_GAP:G1"   # SB window authoritative + FVG-formed-inside rule
G2_DISP_FVG_LINK  = "CORE_GAP:G2"   # displacement leg -> the FVG it created
G3_BREAKER        = "CORE_GAP:G3"   # breaker / unicorn detection
G4_IMPULSE_LEG    = "CORE_GAP:G4"   # named multi-bar impulse leg (OTE basis)
G5_AMD_STATE      = "CORE_GAP:G5"   # AMD phase + true opens (needs EXT tape)
DEGRADED_G4       = "DEGRADED:G4"   # OTE from single displacement candle
THIN              = "THIN_DATA"


@dataclass
class ICTContext:
    """Everything an ICT setup may consult this tick. One object, versioned."""
    # ── provenance ──────────────────────────────────────────────────────
    contract_version: str = CONTRACT_VERSION
    built_by: str = "adapter"          # "adapter" (degraded) | "core"
    bar_ts: str = ""                   # ISO stamp of last CLOSED 1m bar
    price: float = 0.0

    # ── clock ───────────────────────────────────────────────────────────
    killzone: str = ""                 # smc.primitives.killzone()
    sb_window: Optional[bool] = None   # inside 09:45–11:30 ET (prior; env)
    minutes_since_open: float = -1.0

    # ── structure / regime-adjacent (available today via SMCState) ──────
    structure_dir_5m: str = "neutral"
    structure_dir_15m: str = "neutral"
    last_shift: str = ""               # "BOS" / "CHOCH" / ""
    last_shift_dir: str = ""           # "bullish" / "bearish"
    range_high: float = 0.0
    range_low: float = 0.0
    position_pct: float = -1.0         # -1.0 sentinel = no dealing range
    zone: str = "NONE"                 # PREMIUM/DISCOUNT/EQUILIBRIUM/MID/NONE
    draw_above: Optional[float] = None
    draw_below: Optional[float] = None
    draw_side: str = ""
    inducement_px: Optional[float] = None
    displacement_sd: float = 0.0       # 0.0 = none observed this lookback
    displacement_dir: str = ""
    displacement_origin: float = 0.0
    raid: Optional[dict] = None        # live raid (wick through, close inside)
    setup_phase: str = "NONE"          # core SetupState phase (context only)
    setup_thesis: str = ""

    # ── liquidity objects (available today) ─────────────────────────────
    fvgs_bull: List[Any] = field(default_factory=list)   # unmitigated, nearest first
    fvgs_bear: List[Any] = field(default_factory=list)
    order_blocks: List[Any] = field(default_factory=list)
    recent_sweep: Optional[dict] = None    # last CONFIRMED sweep from the mapper
    true_open_0930: Optional[float] = None # today's RTH open (computable from df_1m)

    # ── core-owed fields (None until the core delivers; see SPEC) ───────
    fvg_births: Optional[Dict[int, str]] = None   # G1: id(fvg) -> birth bar ts
    displacement_fvg: Optional[Any] = None        # G2: the gap the disp leg created
    breakers: List[Any] = field(default_factory=list)   # G3
    unicorns: List[Any] = field(default_factory=list)   # G3 (breaker ∩ FVG)
    impulse_leg: Optional[dict] = None            # G4: origin/extreme/dir/start_ts/end_ts
    ote_zone: Optional[Tuple[float, float]] = None  # G4-derived (adapter: DEGRADED)
    amd: Optional[dict] = None                    # G5: phase + true opens (midnight/08:30)

    # ── availability registry ───────────────────────────────────────────
    unavailable: Dict[str, str] = field(default_factory=dict)

    def has(self, name: str) -> bool:
        return name not in self.unavailable

    def journal_dict(self) -> dict:
        d = asdict(self)
        # objects (FVGs/OBs) don't asdict cleanly and would bloat the row
        d["fvgs_bull"] = len(self.fvgs_bull)
        d["fvgs_bear"] = len(self.fvgs_bear)
        d["order_blocks"] = len(self.order_blocks)
        d["breakers"] = len(self.breakers)
        d["unicorns"] = len(self.unicorns)
        return d


# ── the degraded adapter ─────────────────────────────────────────────────────

def _sb_clock(now_et, start_hm: Tuple[int, int], end_hm: Tuple[int, int]) -> bool:
    """Pure clock read for the Silver Bullet window. INTERIM (G1).

    The clock arithmetic is trivial and lives here; what the CORE owes is the
    authoritative window primitive plus the FVG-formed-inside-window rule,
    which needs FVG birth stamps this layer cannot see. When G1 lands this
    function defers to it (SPEC asks the core either to bless this read or
    supersede it — one clock, never two that drift)."""
    hm = (now_et.hour, now_et.minute)
    return start_hm <= hm < end_hm


def build_context(smc_state=None, structure=None, liq_map=None, df_1m=None,
                  now_et=None, price: float = 0.0,
                  sb_start: Tuple[int, int] = (9, 45),
                  sb_end: Tuple[int, int] = (11, 30)) -> ICTContext:
    """Assemble ICTContext from today's PUBLIC surface. Never raises.

    Anything it cannot compute lands in `unavailable` with a reason — the
    scorer turns that into capped completeness, not a silent zero.
    """
    c = ICTContext(price=float(price or 0.0))
    ua = c.unavailable

    # clock
    if now_et is not None:
        try:
            from smc.primitives import killzone as _kz
            c.killzone = _kz(now_et)
        except Exception as e:                      # pragma: no cover
            ua["killzone"] = THIN
            logger.warning("ict.context: killzone read failed: %s", e)
        c.sb_window = _sb_clock(now_et, sb_start, sb_end)
        try:
            mo = (now_et.hour - 9) * 60 + (now_et.minute - 30)
            c.minutes_since_open = float(mo)
        except Exception:
            ua["minutes_since_open"] = THIN
    else:
        ua["killzone"] = THIN
        ua["sb_window"] = THIN

    # SMCState pass-through (the core computed these this tick)
    if smc_state is not None:
        for src, dst in ((("structure_dir_5m",) * 2), (("structure_dir_15m",) * 2),
                         (("last_shift",) * 2), (("last_shift_dir",) * 2),
                         (("range_high",) * 2), (("range_low",) * 2),
                         (("position_pct",) * 2), (("zone",) * 2),
                         (("draw_above",) * 2), (("draw_below",) * 2),
                         (("draw_side",) * 2), (("inducement_px",) * 2),
                         (("displacement_sd",) * 2), (("displacement_dir",) * 2),
                         (("displacement_origin",) * 2), (("raid",) * 2)):
            if hasattr(smc_state, src):
                setattr(c, dst, getattr(smc_state, src))
        st = getattr(smc_state, "setup", None)
        if st is not None:
            c.setup_phase = getattr(st, "phase", "NONE")
            c.setup_thesis = getattr(st, "thesis", "")
        c.bar_ts = str(getattr(smc_state, "bar_ts", "") or "")
    else:
        ua["smc_state"] = THIN

    # analyzer objects
    if structure is not None:
        try:
            from smc.primitives import unmitigated_fvgs
            fvgs = getattr(structure, "fvgs", None) or []
            c.fvgs_bull = unmitigated_fvgs(fvgs, c.price, "bullish")
            c.fvgs_bear = unmitigated_fvgs(fvgs, c.price, "bearish")
        except Exception as e:                      # pragma: no cover
            ua["fvgs"] = THIN
            logger.warning("ict.context: fvg read failed: %s", e)
        c.order_blocks = list(getattr(structure, "order_blocks", None) or [])
    else:
        ua["fvgs"] = THIN
        ua["order_blocks"] = THIN

    if liq_map is not None:
        try:
            sweeps = getattr(liq_map, "sweeps", None) or []
            if sweeps:
                s = sweeps[-1]
                c.recent_sweep = {
                    "pool_price": float(getattr(s, "pool_price", 0.0) or 0.0),
                    "sweep_price": float(getattr(s, "sweep_price", 0.0) or 0.0),
                    "direction": str(getattr(s, "direction", "") or ""),
                    "level_name": str(getattr(s, "level_name", "")
                                      or getattr(s, "name", "") or ""),
                    "invalidated": bool(getattr(s, "invalidated", False)),
                }
        except Exception as e:                      # pragma: no cover
            ua["recent_sweep"] = THIN
            logger.warning("ict.context: sweep read failed: %s", e)
    else:
        ua["recent_sweep"] = THIN

    # today's 09:30 true open — computable from the RTH frame we already hold
    if df_1m is not None and len(df_1m) > 0:
        try:
            c.true_open_0930 = float(df_1m["open"].iloc[0])
        except Exception:
            ua["true_open_0930"] = THIN
    else:
        ua["true_open_0930"] = THIN

    # ── core-owed fields: register the gaps ─────────────────────────────
    ua["fvg_births"] = G1_SB_WINDOW
    ua["displacement_fvg"] = G2_DISP_FVG_LINK
    ua["breakers"] = G3_BREAKER
    ua["unicorns"] = G3_BREAKER
    ua["impulse_leg"] = G4_IMPULSE_LEG
    ua["amd"] = G5_AMD_STATE

    # DEGRADED OTE: retracement band of the single displacement CANDLE. This
    # is NOT the named multi-bar leg the model wants (G4) — it exists so the
    # journal can show near-misses before G4 lands. Marked, and the OTE setup
    # refuses to CONFIRM on it.
    if c.displacement_sd > 0 and c.displacement_dir in ("bullish", "bearish"):
        try:
            from smc.primitives import last_displacement  # noqa: F401  (doc anchor)
            # origin/extreme of the candle: adapter only knows origin + close side
            # via SMCState; band from origin toward price extreme is not
            # recoverable without the candle — so leave ote_zone None unless a
            # future core snapshot provides the leg. Registered as degraded-gap.
            ua["ote_zone"] = DEGRADED_G4
        except Exception:
            ua["ote_zone"] = DEGRADED_G4
    else:
        ua["ote_zone"] = DEGRADED_G4

    return c
