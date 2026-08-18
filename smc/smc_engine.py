"""
smc/smc_engine.py — the SMC/ICT structural core (stateful). v1.0
v1.0 — 2026-08-18 — INITIAL (fork: options_trader_smc, candidate QQQ).

WHAT THIS IS. The replacement ENTRY-side quantity the 2026-08-17 retool
verdict called for ("RETOOL WITH A NEW CORE — lagging is assembled, not
structural"). It does NOT smooth an argmax over indicator agreement; it
reads POSITION and STRUCTURE — the input class the operator's own QQQ
2026-08-17 range call used and the class P0.1 proved was never collected:

  - market structure state per timeframe (BOS/CHoCH over confirmed swings)
  - the dealing range and price's position in it (premium/discount)
  - draw on liquidity (nearest untapped pool each side) + inducement
  - displacement (SD-normalized impulse) and its durable origin
  - unmitigated FVGs / order blocks as points of interest
  - liquidity raids AS THEY HAPPEN (anticipatory, before the reclaim)
  - killzone clock

WHAT IT EMITS, and the two contracts it honors:

  1. A RegimeState-COMPATIBLE label + confidence, so every salvaged
     consumer (strategy gates, exit regime-flips, status, journal) keeps
     working unmodified. Mapping (definitional, see docs/SMC_TRUTHS.md):
       TRENDING_BULL/_BEAR  <- HTF structure directional + last shift BOS
       SWEEP_REVERSAL       <- confirmed sweep-reclaim + CHoCH agreeing
       BREAKOUT_VOLATILE    <- displacement THROUGH external liquidity
                               with acceptance (closes beyond)
       RANGING              <- inside the dealing range, no live
                               displacement, structure MIXED/none
       COMPRESSION          <- RANGING and range width contracting toward
                               equilibrium (vol_state narrow/squeeze)
     Confidence is STRUCTURAL: fraction of structural conditions the label
     holds, not persistence of winning. It is logged AND gates exactly as
     the old conviction did (the fleet runs gates wide open; nothing sizes
     on it — Phase-2 preconditions in the parent repo's transition roadmap
     apply before any sizing).

  2. An ANTICIPATORY SETUP LIFECYCLE, journaled every transition:
       FORMING    a raid of a pool is in progress, or price is approaching
                  an unmitigated POI (FVG/OB) with structure intact
       CONFIRMED  the LTF shift printed (CHoCH after the raid; or the POI
                  tapped and a 1m close back in the thesis direction)
       REVOKED    permissive-until-disqualified (operator, 2026-08-17):
                  the signal is a REVOCATION signal — it costs nothing
                  until it fires, so it may take the bars it needs.
                  Fires when the market ESTABLISHES the disqualifier:
                  acceptance through the setup's invalidation level, or
                  structure shifting against the thesis.
     Setups gate nothing unless OT_SMC_REVOKE_GATES=1 (fork default ON):
     then a REVOKED state blocks NEW entries in the revoked direction —
     the QQQ-08-17 acceptance behavior ("withdraw permission before the
     second and third entries, using only tape available at each instant").

STATE + RESTART. Structure direction per timeframe and the active setup
persist to data/smc_state.json (warm-loaded at boot). Like the pitchfork
(whitepaper §8), the state is fully reconstructible from tape — the file
is a startup optimization, not a correctness requirement. WA §22 applies:
nothing management/exit-side reads a field only this object holds.

WHAT IT MUST NOT DO (inherited invariants):
  - Trade outcomes never feed back into classification (the core
    invariant, unchanged).
  - It does not touch exits. Confirmation is CORRECT at exits and the
    exit stack is the measured winner — the retool moves the ENTRY
    boundary only.
  - No per-evaluate counters (07-20 audit): ages derive from bar stamps.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from typing import Optional

from smc import primitives as _prim
from smc.primitives import (
    DealingRange, Displacement, LiquidityDraw, StructureEvent,
    dealing_range, zone_of, last_displacement,
    draw_on_liquidity, raid_in_progress, inducement, unmitigated_fvgs,
    killzone, DISPLACEMENT_SD_CONFIRM,
)


def classify_break_dyn(prior: str, brk: str) -> str:
    """Late-bound classify_break so tests can monkeypatch primitives."""
    return _prim.classify_break(prior, brk)

logger = logging.getLogger(__name__)

# env knobs (config.py carries the documented defaults; env wins — the same
# OT_RC_*/OT_TR_* convention, so a bound correction is an env flip not a bake)
def _envf(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default

SMC_ACCEPT_CLOSES = int(_envf("OT_SMC_ACCEPT_CLOSES", 2))
SMC_POI_APPROACH_ATR = _envf("OT_SMC_POI_APPROACH_ATR", 0.75)
SMC_REVOKE_GATES = os.environ.get("OT_SMC_REVOKE_GATES", "1") == "1"


@dataclass
class SetupState:
    """The anticipatory setup lifecycle. One active setup per box."""
    phase: str = "NONE"           # NONE / FORMING / CONFIRMED / REVOKED
    thesis: str = ""              # "bullish" / "bearish"
    basis: str = ""               # "raid" / "poi"
    anchor: float = 0.0           # the pool price or POI midpoint
    invalidation: float = 0.0     # acceptance beyond this = REVOKED
    since_bar: int = -1           # bar index of the last phase change
    detail: str = ""


@dataclass
class SMCState:
    """Everything the SMC core knows this tick. ctx["smc"] carries it."""
    label: str = "RANGING"
    confidence: float = 0.0
    structure_dir_5m: str = "neutral"
    structure_dir_15m: str = "neutral"
    last_shift: str = ""          # "BOS" / "CHOCH" / ""
    last_shift_dir: str = ""
    range_high: float = 0.0
    range_low: float = 0.0
    position_pct: float = -1.0    # -1.0 sentinel = no dealing range (STR.2 rule)
    zone: str = "NONE"
    draw_above: Optional[float] = None
    draw_below: Optional[float] = None
    draw_side: str = ""
    inducement_px: Optional[float] = None
    displacement_sd: float = 0.0
    displacement_dir: str = ""
    displacement_origin: float = 0.0
    raid: Optional[dict] = None
    poi_count: int = 0
    killzone: str = ""
    setup: SetupState = field(default_factory=SetupState)

    def journal_dict(self) -> dict:
        d = asdict(self)
        d["setup"] = asdict(self.setup)
        return d


class SMCEngine:
    """Stateful composer over the salvaged engines' outputs.

    update() is called once per tick from main.py's classification path
    with the SAME state objects the old core consumed — no new data is
    fetched and no engine is re-run. The only inputs are ctx contents.
    """

    STATE_FILENAME = "smc_state.json"

    def __init__(self, state_dir: Optional[str] = None):
        self._dir5 = "neutral"     # committed structure direction, 5m swings
        self._dir15 = "neutral"    # committed structure direction, 15m swings
        self._last_shift = ("", "")   # (kind, direction)
        self._last_shift_bar = -1     # bar index the shift printed on
        self._setup = SetupState()
        # v1.0 — the engine OWNS its swing memory. The analyzer's swing sets
        # are recomputed per frame with a length-derived lookback, so levels
        # appear and vanish as the frame grows (the pitchfork whitepaper's
        # §4.1 failure mode). Levels observed are accumulated here and marked
        # broken on a close CROSSING them — edge-triggered, so a break prints
        # exactly once, on the bar that crossed. Bounded (no unbounded growth).
        self._seen_highs = {}      # round(price,4) -> last index observed
        self._seen_lows = {}
        self._broken = set()       # levels already broken (never re-fire)
        self._prev_close = None
        self._state_path = None
        if state_dir:
            self._state_path = os.path.join(state_dir, self.STATE_FILENAME)
            self._load()

    # ── persistence (optimization only — reconstructible from tape) ─────────
    def _load(self):
        try:
            if self._state_path and os.path.exists(self._state_path):
                with open(self._state_path) as f:
                    d = json.load(f)
                self._dir5 = d.get("dir5", "neutral")
                self._dir15 = d.get("dir15", "neutral")
                self._last_shift = tuple(d.get("last_shift", ["", ""]))
                s = d.get("setup") or {}
                self._setup = SetupState(**{k: s.get(k, getattr(SetupState(), k))
                                            for k in SetupState().__dict__})
        except Exception as exc:                                # noqa: BLE001
            logger.warning("smc_state load failed (%s) — cold start; state "
                           "is reconstructible from tape", exc)

    def save(self):
        try:
            if not self._state_path:
                return
            with open(self._state_path, "w") as f:
                json.dump({"dir5": self._dir5, "dir15": self._dir15,
                           "last_shift": list(self._last_shift),
                           "setup": asdict(self._setup)}, f)
        except Exception:                                       # noqa: BLE001
            pass                       # persistence must never break the path

    # ── the tick ────────────────────────────────────────────────────────────
    def update(self, price: float, df_1m, df_5m, structure, liq_map,
               vol_state=None, now_et=None) -> SMCState:
        st = SMCState()
        st.killzone = killzone(now_et) if now_et is not None else ""

        swings_h = getattr(structure, "swing_highs", None) or []
        swings_l = getattr(structure, "swing_lows", None) or []
        pools = getattr(liq_map, "pools", None) or []

        # 1 · structure shift: accumulate observed swings, break on a close
        #     CROSSING an unbroken level (prev_close on one side, close on
        #     the other) — edge-triggered, judged vs the engine's own memory
        for s in swings_h:
            self._seen_highs[round(s.price, 4)] = s.index
        for s in swings_l:
            self._seen_lows[round(s.price, 4)] = s.index
        # bound the memory: keep the 40 most recently observed per side
        for book in (self._seen_highs, self._seen_lows):
            if len(book) > 40:
                for k in sorted(book, key=book.get)[:len(book) - 40]:
                    book.pop(k, None)
        ev = self._detect_break(df_1m)
        if ev is not None:
            self._last_shift = (ev.kind, ev.direction)
            self._last_shift_bar = ev.bar_index
            self._dir5 = ev.direction
        st.last_shift, st.last_shift_dir = self._last_shift
        st.structure_dir_5m = self._dir5
        # 15m direction from the analyzer's own sequence read (HH_HL / LH_LL)
        seq = getattr(structure, "structure_sequence", "NEUTRAL")
        # v1.0 — NOT latched: MIXED/NEUTRAL reads as neutral NOW. Latching a
        # stale HH_HL across a mixed stretch made every minor bullish swing
        # crossing in chop "HTF-aligned" and printed TRENDING inside a range.
        self._dir15 = ("bullish" if seq == "HH_HL"
                       else "bearish" if seq == "LH_LL" else "neutral")
        st.structure_dir_15m = self._dir15

        # 2 · dealing range + premium/discount
        dr = dealing_range(swings_h, swings_l, price, timeframe="5m")
        if dr is not None:
            st.range_high, st.range_low = dr.high, dr.low
            st.position_pct = round(dr.position_pct(price), 4)
            st.zone = zone_of(st.position_pct)

        # 3 · liquidity: draw, inducement, live raid
        draw = draw_on_liquidity(pools, price)
        st.draw_above, st.draw_below = draw.above, draw.below
        st.draw_side = draw.nearest_side(price)
        st.inducement_px = inducement(pools, price, draw)
        st.raid = raid_in_progress(df_1m, pools, price)

        # 4 · displacement
        disp = last_displacement(df_1m)
        if disp is not None:
            st.displacement_sd = disp.sd
            st.displacement_dir = disp.direction
            st.displacement_origin = disp.origin

        # 5 · points of interest (unmitigated in-favor FVGs)
        fvgs = getattr(structure, "fvgs", None) or []
        favored = ("bullish" if self._dir5 == "bullish"
                   else "bearish" if self._dir5 == "bearish" else "")
        pois = unmitigated_fvgs(fvgs, price, direction=favored)
        st.poi_count = len(pois)

        # 6 · label + structural confidence (see SMC_TRUTHS for the grammar)
        st.label, st.confidence = self._label(st, liq_map, vol_state, disp)

        # 7 · setup lifecycle (anticipatory; revocation semantics)
        self._setup = self._advance_setup(self._setup, st, price, df_1m,
                                          liq_map, pois, vol_state)
        st.setup = self._setup
        return st

    def _detect_break(self, df_1m) -> Optional[StructureEvent]:
        """Edge-triggered structure break vs the engine's swing memory.

        A bullish break = the last CLOSE crossed above an unbroken observed
        swing high (prev_close <= level < close); bearish mirrored. All
        levels crossed in one bar are marked broken; the event reports the
        farthest one. Close-based, never wick-based.
        """
        if df_1m is None or len(df_1m) < 2:
            return None
        close = float(df_1m["close"].iloc[-1])
        prev = (self._prev_close if self._prev_close is not None
                else float(df_1m["close"].iloc[-2]))
        self._prev_close = close
        idx = len(df_1m) - 1
        up = [lv for lv in self._seen_highs
              if lv not in self._broken and prev <= lv < close]
        dn = [lv for lv in self._seen_lows
              if lv not in self._broken and close < lv <= prev]
        if up:
            for lv in up:
                self._broken.add(lv)
            lv = max(up)
            return StructureEvent(kind=classify_break_dyn(self._dir5,
                                                          "bullish"),
                                  direction="bullish", level=lv,
                                  bar_index=idx)
        if dn:
            for lv in dn:
                self._broken.add(lv)
            lv = min(dn)
            return StructureEvent(kind=classify_break_dyn(self._dir5,
                                                          "bearish"),
                                  direction="bearish", level=lv,
                                  bar_index=idx)
        return None

    # ── label grammar ───────────────────────────────────────────────────────
    def _label(self, st: SMCState, liq_map, vol_state, disp):
        conds = []

        sweep = getattr(liq_map, "recent_sweep", None)
        sweep_live = (sweep is not None
                      and getattr(sweep, "reclaimed", False)
                      and not getattr(liq_map, "sweep_invalidated", False)
                      and getattr(liq_map, "sweep_age_bars", 999) <= 6)
        if sweep_live and st.last_shift == "CHOCH":
            # sweep-reclaim + structure shift agreeing = the reversal state
            conds = [True,
                     st.last_shift_dir != "",           # shift printed
                     bool(getattr(sweep, "swept_named_level", ""))]
            return "SWEEP_REVERSAL", round(sum(conds) / len(conds), 3)

        # displacement THROUGH external liquidity with acceptance = breakout
        if (disp is not None and disp.sd >= DISPLACEMENT_SD_CONFIRM
                and sweep is not None
                and getattr(sweep, "closes_beyond", 0) >= SMC_ACCEPT_CLOSES
                and not getattr(sweep, "reclaimed", False)):
            conds = [True, disp.sd >= 2.5, st.last_shift == "BOS"]
            return "BREAKOUT_VOLATILE", round(sum(conds) / len(conds), 3)

        if self._dir5 in ("bullish", "bearish") and st.last_shift == "BOS":
            aligned = (self._dir15 == self._dir5)
            # CONFIRM-tier displacement only (>= 2.0 SD, TC.4's own
            # vocabulary for "a real committed move") — an AWARE-tier blip
            # is not sufficient evidence to call a trend.
            with_disp = (st.displacement_dir == self._dir5
                         and st.displacement_sd >= DISPLACEMENT_SD_CONFIRM)
            # NECESSARY: a shift with neither HTF alignment nor displacement
            # behind it is chop crossing a minor swing, not a trend. Without
            # this gate every range rotation that clips a swing point would
            # print TRENDING — the confirmatory core's own A2 failure, worn
            # structurally. Falls through to the RANGING family instead.
            if aligned or with_disp:
                healthy_pos = (  # trend continuation wants discount in a bull
                    st.zone in ("DISCOUNT", "EQUILIBRIUM", "MID")
                    if self._dir5 == "bullish"
                    else st.zone in ("PREMIUM", "EQUILIBRIUM", "MID"))
                conds = [True, aligned, with_disp, healthy_pos]
                label = ("TRENDING_BULL" if self._dir5 == "bullish"
                         else "TRENDING_BEAR")
                return label, round(sum(conds) / len(conds), 3)

        # inside the dealing range, no live displacement -> RANGING; hand off
        # to COMPRESSION on the same width axis the old core used (narrow +
        # contracting is a coil, not a range — REGIME_TRUTHS' own handoff)
        narrow = bool(vol_state is not None
                      and getattr(vol_state, "bb_state", "") == "SQUEEZE"
                      and not getattr(vol_state, "is_expanding", False))
        in_range = st.position_pct >= 0
        if narrow and in_range:
            conds = [True, abs(st.position_pct - 0.5) <= 0.25]
            return "COMPRESSION", round(sum(conds) / len(conds), 3)
        conds = [in_range, st.displacement_sd < DISPLACEMENT_SD_CONFIRM,
                 st.last_shift != "BOS" or self._dir5 == "neutral"]
        return "RANGING", round(sum(conds) / max(len(conds), 1), 3)

    # ── setup lifecycle ─────────────────────────────────────────────────────
    def _advance_setup(self, s: SetupState, st: SMCState, price: float,
                       df_1m, liq_map, pois, vol_state) -> SetupState:
        bar = (len(df_1m) - 1) if df_1m is not None else -1

        # REVOCATION first — permissive-until-disqualified means the
        # disqualifier is checked before anything new is proposed.
        if s.phase in ("FORMING", "CONFIRMED") and s.invalidation > 0:
            close = (float(df_1m["close"].iloc[-1])
                     if df_1m is not None and len(df_1m) else price)
            accepted = ((s.thesis == "bullish" and close < s.invalidation)
                        or (s.thesis == "bearish" and close > s.invalidation))
            # v1.0 — the shift must POST-DATE the setup. A raid IS a move
            # against the coming thesis; counting the raid bar's own break
            # (or any earlier one) as the disqualifier revoked every setup
            # one bar after it formed. Only a shift printed AFTER since_bar
            # is evidence against the setup.
            shifted_against = (st.last_shift == "CHOCH"
                               and st.last_shift_dir != s.thesis
                               and st.last_shift_dir != ""
                               and self._last_shift_bar > s.since_bar)
            if accepted or shifted_against:
                return SetupState(phase="REVOKED", thesis=s.thesis,
                                  basis=s.basis, anchor=s.anchor,
                                  invalidation=s.invalidation, since_bar=bar,
                                  detail=("acceptance" if accepted
                                          else "structure_shift"))

        # CONFIRMATION of a forming raid setup: the reclaim printed
        if s.phase == "FORMING" and s.basis == "raid":
            sweep = getattr(liq_map, "recent_sweep", None)
            if (sweep is not None and getattr(sweep, "reclaimed", False)
                    and getattr(liq_map, "sweep_age_bars", 999) <= 3):
                return SetupState(phase="CONFIRMED", thesis=s.thesis,
                                  basis="raid", anchor=s.anchor,
                                  invalidation=s.invalidation, since_bar=bar,
                                  detail="reclaim")

        # CONFIRMATION of a forming POI setup: tapped and closed back in favor
        if s.phase == "FORMING" and s.basis == "poi" and df_1m is not None \
                and len(df_1m):
            lo = float(df_1m["low"].iloc[-1])
            hi = float(df_1m["high"].iloc[-1])
            close = float(df_1m["close"].iloc[-1])
            tapped = (lo <= s.anchor <= hi)
            back_in = ((s.thesis == "bullish" and close > s.anchor)
                       or (s.thesis == "bearish" and close < s.anchor))
            if tapped and back_in:
                return SetupState(phase="CONFIRMED", thesis=s.thesis,
                                  basis="poi", anchor=s.anchor,
                                  invalidation=s.invalidation, since_bar=bar,
                                  detail="poi_tap")

        # NEW FORMATION — only when nothing is active (REVOKED clears when a
        # fresh formation appears; a revocation is not a permanent lockout,
        # it is "not this one")
        if s.phase in ("NONE", "REVOKED", "CONFIRMED"):
            raid = st.raid
            if raid is not None:
                thesis = "bearish" if raid["kind"] == "high_raid" else "bullish"
                # invalidation = acceptance beyond the raided pool
                return SetupState(phase="FORMING", thesis=thesis, basis="raid",
                                  anchor=raid["pool"],
                                  invalidation=raid["pool"], since_bar=bar,
                                  detail=f"raid:{raid['name']}")
            if pois and st.structure_dir_5m in ("bullish", "bearish"):
                atr = float(getattr(vol_state, "atr_current", 0.0) or 0.0)
                g = pois[0]
                mid = (g.top + g.bottom) / 2.0
                if atr > 0 and abs(price - mid) <= SMC_POI_APPROACH_ATR * atr:
                    thesis = st.structure_dir_5m
                    inval = g.bottom if thesis == "bullish" else g.top
                    return SetupState(phase="FORMING", thesis=thesis,
                                      basis="poi", anchor=mid,
                                      invalidation=inval, since_bar=bar,
                                      detail="fvg_approach")
        return s

    # ── the gate main.py consults (revocation semantics) ────────────────────
    def entry_permitted(self, direction: str) -> bool:
        """True unless the active setup was REVOKED against this direction.

        Directions: "bullish"/"bearish" (a neutral structure — condor — is
        never blocked here). This is deliberately a REVOCATION check, not a
        grant: absent any setup state, permission stands (operator,
        2026-08-17 — "allow ORB entries until it establishes unfavorable
        conditions").
        """
        if not SMC_REVOKE_GATES:
            return True
        s = self._setup
        if s.phase != "REVOKED":
            return True
        return direction != s.thesis
