"""
tests/test_runner_refinements.py — exit_engine v3.8 / config v2.0 /
trade_logger v3.8.

  1. Floor: directional stop_premium is entry × (1 − MAX_LOSS_PCT) = ×0.60 at
     the new 40% default; butterfly stays ×0.75 (25%).
  2. Hard-stop label is truthful to the record's ACTUAL floor (old 25%
     records keep saying 25%; new 40% records say 40%).
  3. FVG floor clamp: a gap hugging price cannot set a floor tighter than
     FVG_FLOOR_MAX_LOCK_PCT of current premium — both trails.
  4. Post-target fallback is 75% of current (leash no longer inverts).
  5. Sweep runner mode: at ≥ +100% there is NO target_hit — the post-target
     trail governs; env-off restores the hard TP.
  6. 5m frame selection: 5m preferred when present, 1m fallback, config-off
     restores 1m.
  7. Telemetry: max/min premium seen tracked across ticks in one write.

Run: PYTHONPATH=. pytest tests/test_runner_refinements.py -v
"""

import sys
import os
import uuid

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as cfg                                  # noqa: E402
from execution import exit_engine as xe               # noqa: E402
from execution.exit_engine import ExitEngine          # noqa: E402
from strategy.base_strategy import OptionsSignal      # noqa: E402


def engine(monkeypatch):
    monkeypatch.setattr(xe, "get_trade_logger", lambda: None)
    # the container clock may be past 15:45 ET — neutralize the hard-close
    # gate so these tests exercise the rules below it
    monkeypatch.setattr(xe, "is_hard_close_time", lambda: False)
    return ExitEngine(paper_trading=True)


def orb_record(entry=2.00, floor_pct=None, **kw):
    floor_pct = cfg.MAX_LOSS_PCT if floor_pct is None else floor_pct
    rec = {
        "trade_id":         uuid.uuid4().hex,
        "strategy":         "ORBStrategy",
        "entry_premium":    entry,
        "stop_premium":     round(entry * (1 - floor_pct), 4),
        "target_premium":   entry * 2.0,
        "trail_activation": entry * 1.5,
        "contracts":        1,
        "direction":        "long",
        "underlying_entry": 6200.0,
        "underlying_target": 6220.0,
    }
    rec.update(kw)
    return rec


# 1 — floors from config
def test_floor_values_by_strategy():
    assert cfg.MAX_LOSS_PCT == pytest.approx(0.40)
    sig = OptionsSignal.__new__(OptionsSignal)
    sig.is_butterfly = False
    sig.is_iron_condor = False
    sig.entry_premium = 2.00
    sig.stop_loss_pct = cfg.MAX_LOSS_PCT
    assert sig.stop_premium() == pytest.approx(1.20)      # entry × 0.60
    assert cfg.BUTTERFLY_STOP_LOSS_PCT == pytest.approx(0.25)


# 2 — truthful dynamic label
def test_hard_stop_label_matches_record_floor(monkeypatch):
    eng = engine(monkeypatch)
    # new-era record: 40% floor
    d = eng._evaluate_orb(orb_record(entry=2.00), current_premium=1.19, df_1m=None)
    assert d.should_exit and "hard_stop_40%" in d.exit_reason
    # legacy record carrying its entry-time 25% floor
    d = eng._evaluate_orb(orb_record(entry=2.00, floor_pct=0.25),
                          current_premium=1.49, df_1m=None)
    assert d.should_exit and "hard_stop_25%" in d.exit_reason


# 3 — FVG floor clamp (both trails)
def test_fvg_floor_clamped(monkeypatch):
    eng = engine(monkeypatch)
    rec = orb_record(entry=1.00)
    # An FVG so close it implies a floor at ~99% of current premium:
    tight_fvg = type("F", (), {"top": 6219.5, "bottom": 6219.0})()
    monkeypatch.setattr(xe, "_nearest_unfilled_fvg_in_favor",
                        lambda *a, **k: tight_fvg)
    df = pd.DataFrame({"close": [6219.8]})
    current = 2.00  # +100% — deep in profit
    trail = eng._update_fvg_trail(rec["trade_id"], current, rec, df, "long")
    assert trail <= current * cfg.FVG_FLOOR_MAX_LOCK_PCT + 1e-9
    # post-target trail: same clamp
    rec2 = orb_record(entry=1.00)
    trail2 = eng._update_post_target_trail(rec2["trade_id"], current, rec2,
                                           df, "long")
    assert trail2 <= current * cfg.FVG_FLOOR_MAX_LOCK_PCT + 1e-9


# 4 — post-target fallback = 75% of current, matching pre-target
def test_post_target_fallback_is_75(monkeypatch):
    assert cfg.POST_TARGET_TRAIL_LOCK_PCT == pytest.approx(0.75)
    eng = engine(monkeypatch)
    rec = orb_record(entry=1.00)
    trail = eng._update_post_target_trail(rec["trade_id"], 2.40, rec,
                                          None, "long")   # no df → fallback
    assert trail == pytest.approx(2.40 * 0.75)


# 5 — sweep runner mode: no more +100% guillotine
def test_sweep_runner_mode(monkeypatch):
    eng = engine(monkeypatch)
    rec = orb_record(entry=1.00)
    rec["strategy"] = "SweepReversalStrategy"
    # at +140%, above target — runner mode must NOT hard-exit
    monkeypatch.setattr(xe, "SWEEP_POST_TARGET_TRAIL", True)
    d = eng._evaluate_sweep(rec, current_premium=2.40, df_1m=None)
    assert d.should_exit is False
    assert d.new_trail_stop == pytest.approx(2.40 * 0.75)
    # env-off restores the hard TP for A/B
    monkeypatch.setattr(xe, "SWEEP_POST_TARGET_TRAIL", False)
    rec2 = orb_record(entry=1.00)
    rec2["strategy"] = "SweepReversalStrategy"
    d = eng._evaluate_sweep(rec2, current_premium=2.40, df_1m=None)
    assert d.should_exit and "target_hit" in d.exit_reason


# 6 — FVG frame selection
def test_fvg_frame_selection(monkeypatch):
    df1 = pd.DataFrame({"close": [1, 2, 3]})
    df5 = pd.DataFrame({"close": [1, 2, 3, 4]})
    monkeypatch.setattr(xe, "USE_5M_FVG_TRAIL", True)
    assert ExitEngine._fvg_frame(df1, df5) is df5
    assert ExitEngine._fvg_frame(df1, None) is df1        # graceful fallback
    monkeypatch.setattr(xe, "USE_5M_FVG_TRAIL", False)
    assert ExitEngine._fvg_frame(df1, df5) is df1         # A/B off → 1m


# 7 — MFE/MAE telemetry
def test_mfe_mae_telemetry(tmp_path):
    from database.trade_logger import TradeLogger, make_record
    from utils.time_utils import ts_for_db
    tl = TradeLogger(db_path=str(tmp_path / "t.db"), paper_trading=True)
    rec = make_record(trade_id="tele-1", symbol="SPX", strategy="ORBStrategy",
                      contracts=1, entry_premium=1.00, expiry="2099-12-31",
                      paper_trade=1, status="open", entry_time=ts_for_db())
    tl.log_entry(rec)
    for p in (1.00, 1.80, 0.90, 1.20):
        tl.update_current_premium("tele-1", p)
    row = tl.get_open_trade()
    assert row["max_premium_seen"] == pytest.approx(1.80)   # the MFE
    assert row["min_premium_seen"] == pytest.approx(0.90)   # the MAE
    assert row["current_premium"]  == pytest.approx(1.20)
