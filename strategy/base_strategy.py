"""
strategy/base_strategy.py — Abstract base and OptionsSignal for all strategies.
v3.0 — original release
v1.1 — 2026-06-27 — added orb_range_high/low fields to OptionsSignal for
        strategy-aware exit routing in exit_engine.py
v1.2 — 2026-06-30 — added 4-leg fields for IronCondorStrategy (RANGING
        regime fallback when no GEX pin available for butterfly)
v3.0 — 2026-07-10 — repo-wide v3.0 bump: Yahoo-Finance purge & data stream
        mapping optimization (all market data now flows from the single
        shared TastyTrade candle feed — see data/candle_feed.py). No logic
        change in this file.
"""
# v-obs2 (2026-07-24) — OptionsSignal carries swept_level_name + level_strength for sweep level postmortems.

# v-obs (2026-07-24) — OptionsSignal carries adx_at_signal + flat_angle_deg so entry records can store the regime context the tape-analysis needs.


from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List

from data.options_chain import OptionContract, OptionsChain
from analysis.orb_engine import ORBData


@dataclass
class OptionsSignal:
    """
    A candidate options trade proposal.
    Validated and sized before reaching execution.
    """
    # ── Strategy identity ────────────────────────────────────────────────
    strategy_name:  str   = ""
    setup_type:     str   = ""

    # ── Direction ─────────────────────────────────────────────────────
    direction:      str   = ""      # "long" or "short" (of the UNDERLYING)
    option_side:    str   = ""      # "call" or "put"

    # ── Underlying price levels ─────────────────────────────────────────────
    underlying_entry:   float = 0.0
    underlying_stop:    float = 0.0
    underlying_target:  float = 0.0
    underlying_tp50:    float = 0.0

    # ── ORB range boundaries (ORB trades only) ──────────────────────────────
    orb_range_high: float = 0.0
    orb_range_low:  float = 0.0

    # ── Option details (single-leg) ───────────────────────────────────────
    strike:         float = 0.0
    expiry:         str   = ""
    entry_premium:  float = 0.0
    contract:       Optional[OptionContract] = None

    # ── Butterfly legs (3-leg) ─────────────────────────────────────────
    is_butterfly:        bool  = False
    lower_contract:      Optional[OptionContract] = None
    center_contract:     Optional[OptionContract] = None
    upper_contract:      Optional[OptionContract] = None
    butterfly_direction: str   = ""
    net_debit:           float = 0.0
    max_profit:          float = 0.0

    # ── Iron Condor legs (4-leg) ─────────────────────────────────────
    # Credit spread: sell short put + buy long put (lower side)
    #                sell short call + buy long call (upper side)
    # ⚠️ RENAMED FROM `is_iron_condor` (TCS.1, 2026-08-14). It NEVER meant "this
    # is a condor" — every use below selects CREDIT-SPREAD MATH: validity by four
    # legs, stop as a RISING spread value, TP as decay toward zero. The old name
    # is why TrendCreditSpread had to declare itself a condor to get correct
    # arithmetic, which is the coupling that produced the 2026-08-14 identity
    # bug. `is_iron_condor` is kept as a read/write ALIAS below so no caller
    # breaks mid-flight.
    is_credit_vertical:   bool  = False
    short_put_contract:   Optional[OptionContract] = None
    long_put_contract:    Optional[OptionContract] = None
    short_call_contract:  Optional[OptionContract] = None
    long_call_contract:   Optional[OptionContract] = None
    net_credit:           float = 0.0   # Total credit received (premium collected)
    max_loss_condor:      float = 0.0   # Wing width - net credit (per side, worse side)
    expected_move:        float = 0.0   # ATM straddle-derived expected move at entry
    expected_move_mult:   float = 0.0   # short strike distance / expected move (guardrail check)

    # ── Risk / sizing ────────────────────────────────────────────────
    contracts:      int   = 0
    total_cost:     float = 0.0
    max_loss:       float = 0.0
    stop_loss_pct:  float = 0.25
    tp_pct:         float = 1.0

    # ── Quality ─────────────────────────────────────────────────────
    confluence_factors: List[str] = field(default_factory=list)
    conviction:     float = 0.0
    setup_grade:    str   = "B"

    # ── Context ──────────────────────────────────────────────────────
    regime:         str   = ""
    adx_at_signal:  float = 0.0    # v-obs: ADX at entry, for tape-context analysis
    flat_angle_deg: float = 0.0    # v-obs: flat-angle at entry (0 if unavailable)
    swept_level_name: str = ""     # v-obs: name of swept level (PDH/PDL/session) — '' if equal-H/L
    level_strength:   float = 0.0  # v-obs: 0..1 conviction of the swept level (named+touches)
    vix_at_signal:  float = 0.0
    is_fed_day:     bool  = False
    notes:          str   = ""

    @property
    def is_orb(self) -> bool:
        return self.strategy_name == "ORBStrategy"

    @property
    def is_sweep(self) -> bool:
        return self.strategy_name == "SweepReversal"

    @property
    def is_valid(self) -> bool:
        if self.is_butterfly:
            return (
                self.butterfly_direction in ("call", "put") and
                self.net_debit > 0 and
                self.lower_contract is not None and
                self.center_contract is not None and
                self.upper_contract is not None
            )
        if self.is_credit_vertical:
            return (
                self.net_credit > 0 and
                self.short_put_contract is not None and
                self.long_put_contract is not None and
                self.short_call_contract is not None and
                self.long_call_contract is not None
            )
        return (
            self.option_side in ("call", "put") and
            self.strike > 0 and
            self.entry_premium > 0 and
            self.underlying_entry > 0
        )

    @property
    def is_iron_condor(self) -> bool:
        """Back-compat alias. ⚠️ Both names address ONE field — a caller setting
        either gets identical behaviour, so a missed rename cannot produce a
        signal that is a credit vertical to one half of the system and a debit
        to the other. That divergence is precisely what the rename exists to
        make impossible."""
        return self.is_credit_vertical

    @is_iron_condor.setter
    def is_iron_condor(self, v: bool) -> None:
        self.is_credit_vertical = bool(v)

    def stop_premium(self) -> float:
        """Premium level at which we exit (25% loss)."""
        if self.is_butterfly:
            return self.net_debit * (1 - self.stop_loss_pct)
        if self.is_credit_vertical:
            # For a credit spread, "loss" means the spread VALUE rises
            # (we sold it, so rising value = losing money). Stop level
            # is expressed here as the spread value at which we exit.
            return self.net_credit * (1 + self.stop_loss_pct)
        return self.entry_premium * (1 - self.stop_loss_pct)

    def trail_activation_premium(self) -> float:
        """Premium level at which trailing stop activates (50% TP)."""
        if self.is_butterfly:
            return self.net_debit + self.max_profit * 0.5
        if self.is_credit_vertical:
            # Condor profits as the spread value DECAYS toward zero.
            # 50% TP = spread value has decayed to 50% of credit received.
            return self.net_credit * 0.5
        return self.entry_premium * (1 + self.tp_pct * 0.5)

    def target_premium(self) -> float:
        """Full TP premium target."""
        if self.is_butterfly:
            return self.net_debit + self.max_profit * self.tp_pct
        if self.is_credit_vertical:
            # TP = spread value has decayed to (1 - tp_pct) of credit.
            # e.g. tp_pct=0.50 means close at 50% of max profit captured,
            # i.e. spread value has fallen to 50% of the credit received.
            return self.net_credit * (1 - self.tp_pct)
        return self.entry_premium * (1 + self.tp_pct)


class BaseOptionsStrategy(ABC):
    """Abstract base for all options strategies."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def generate_signal(self, *args, **kwargs) -> Optional[OptionsSignal]: ...

    def _add_confluence(self, signal: OptionsSignal, factor: str):
        signal.confluence_factors.append(factor)
