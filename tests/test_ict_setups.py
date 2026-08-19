"""
tests/test_ict_setups.py — behavioural suite for strategy/ict/. v1.0
v1.0 — 2026-08-18 — INITIAL (ICT setup suite). Script-mode like
        test_smc_core.py: `PYTHONPATH=. python3 tests/test_ict_setups.py`.
        Checks:
          A  context adapter: availability registry honest (core gaps named)
          B  scoring arithmetic: completeness caps, required-missing blocks
          C  Silver Bullet: FORMING today, fires only when G1 arrives;
             out-of-window refuses
          D  SweepMSS: full chain completes on today's surface; dispatch
             arming ladder (disarmed -> unvalidated -> armed+validated)
          E  size mapping tiers (displacement × bias only)
          F  afternoon debit cutoff -> wants_credit journaled, no signal
          G  DELIBERATE FAILURE: OT_ICT_SELFTEST corrupts the score and this
             suite proves it goes red (WA §20 — a test that cannot fail
             proves nothing)
        NOTE per handoff §3.5: this suite proves the MACHINERY. It is not
        the tape validation — that runs in backtest_harness --engine smc on
        real QQQ tape with the OPERATOR's pre-written pass condition, and
        only that arms a setup.
"""

import datetime as dt
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILS = []

def check(name, cond, detail=""):
    tag = "PASS" if cond else "FAIL"
    print(f"  [{tag}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def et(h, m):
    return dt.datetime(2026, 8, 18, h, m, tzinfo=dt.timezone.utc)  # tz irrelevant to clock reads


def fresh_ctx(**kw):
    from strategy.ict.context import ICTContext
    c = ICTContext(price=580.0)
    # a live raid reclaiming a named low + bullish CHoCH + CONFIRM displacement
    c.raid = {"thesis": "bullish", "wick_extreme": 578.4, "level_name": "PDL"}
    c.recent_sweep = {"pool_price": 578.8, "sweep_price": 578.4,
                      "direction": "low", "level_name": "PDL",
                      "invalidated": False}
    c.last_shift, c.last_shift_dir = "CHOCH", "bullish"
    c.displacement_sd, c.displacement_dir = 2.3, "bullish"
    c.displacement_origin = 578.9
    c.structure_dir_5m = "bullish"
    c.draw_above, c.draw_side = 583.5, "above"
    c.position_pct, c.zone = 0.22, "DISCOUNT"
    c.killzone = "NY_AM"
    c.sb_window = True
    c.minutes_since_open = 45.0
    g = types.SimpleNamespace(top=580.3, bottom=579.6, direction="bullish",
                              filled=False, index=40)
    c.fvgs_bull = [g]
    c.unavailable = {"fvg_births": "CORE_GAP:G1",
                     "displacement_fvg": "CORE_GAP:G2",
                     "breakers": "CORE_GAP:G3", "unicorns": "CORE_GAP:G3",
                     "impulse_leg": "CORE_GAP:G4", "amd": "CORE_GAP:G5",
                     "ote_zone": "DEGRADED:G4"}
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def main():
    from strategy.ict.context import build_context
    from strategy.ict.scoring import (SetupScore, Component, size_fraction,
                                      reset_journal_state, journal_setup_state)
    from strategy.ict.silver_bullet import SilverBulletSetup
    from strategy.ict.sweep_mss import SweepMSSSetup
    from strategy.ict import dispatch as disp

    print("A — context adapter honesty")
    c0 = build_context(now_et=et(10, 15), price=580.0)
    check("A1 core gaps registered", all(
        c0.unavailable.get(k, "").startswith(("CORE_GAP", "DEGRADED"))
        for k in ("fvg_births", "displacement_fvg", "breakers",
                  "impulse_leg", "amd")))
    check("A2 thin inputs registered, not zeroed",
          "smc_state" in c0.unavailable and "fvgs" in c0.unavailable)
    check("A3 sb clock reads inside window", c0.sb_window is True)
    c0b = build_context(now_et=et(11, 45), price=580.0)
    check("A4 sb clock reads outside window", c0b.sb_window is False)

    print("B — scoring arithmetic")
    sc = SetupScore(setup="T", direction="long", components=[
        Component("dir:a", 2.0, 1.0), Component("b", 2.0, 1.0),
        Component("c", 1.0, 0.0, available=False, required=True,
                  reason="CORE_GAP:G9")])
    check("B1 completeness capped by unavailable weight",
          abs(sc.completeness() - 4.0 / 5.0) < 1e-9, str(sc.completeness()))
    check("B2 score computed over available only", sc.score() == 1.0)
    check("B3 required-unavailable blocks firing",
          not sc.fire_eligible() and sc.missing_required() == ["c"])
    check("B4 bias reads dir: components only", sc.bias_quality() == 1.0)

    print("C — Silver Bullet: forming today, firing needs G1")
    sb = SilverBulletSetup()
    c1 = fresh_ctx()
    s1 = sb.evaluate(c1)
    check("C1 forms with honest phase", s1.phase() == "FORMING", s1.phase())
    check("C2 blocked exactly on fvg_in_window",
          s1.missing_required() == ["fvg_in_window"], str(s1.missing_required()))
    check("C3 completeness < 1 while G1 open", s1.completeness() < 1.0)
    c2 = fresh_ctx(fvg_births={1: "2026-08-18T14:31:00"})
    c2.unavailable = dict(c2.unavailable)
    c2.unavailable.pop("fvg_births")
    s2 = sb.evaluate(c2)
    # with births available the component exists but its VALUE is core-computed;
    # v1.0 leaves it 0 until the core snapshot carries it — still not READY.
    check("C4 birth availability alone does not fake a pass",
          not s2.fire_eligible())
    c3 = fresh_ctx(sb_window=False)
    s3 = sb.evaluate(c3)
    check("C5 outside window refuses", "window" in s3.missing_required())

    print("D — SweepMSS completes today; dispatch arming ladder")
    sm = SweepMSSSetup()
    s4 = sm.evaluate(fresh_ctx())
    check("D1 full chain fire-eligible on current surface",
          s4.fire_eligible(),
          f"score={s4.score()} comp={s4.completeness()} miss={s4.missing_required()}")
    reset_journal_state()
    rows = []
    jr = lambda kind, **kw: rows.append((kind, kw))
    os.environ.pop("OT_ICT_ARMED", None)
    sig = disp.ict_dispatch(fresh_ctx(), chain=None, now_et=et(10, 15), journal=jr)
    check("D2 disarmed returns no signal", sig is None)
    check("D3 disarmed still journals would_fire",
          any("would_fire:disarmed" in (kw.get("blocked") or "")
              for _, kw in rows), str([kw.get("blocked") for _, kw in rows]))
    check("D4 every setup journaled a state", len(rows) >= 7, str(len(rows)))
    os.environ["OT_ICT_ARMED"] = "1"
    reset_journal_state()
    rows.clear()
    sig = disp.ict_dispatch(fresh_ctx(), chain=None, now_et=et(10, 15), journal=jr)
    check("D5 armed but unvalidated refuses",
          sig is None and any("unvalidated" in (kw.get("blocked") or "")
                              for _, kw in rows))
    os.environ["OT_ICT_ICTSWEEPMSS_VALIDATED"] = "1"
    reset_journal_state()
    sig = disp.ict_dispatch(fresh_ctx(), chain=None, now_et=et(10, 15), journal=jr)
    check("D6 armed+validated produces a signal",
          sig is not None and sig.strategy_name == "ICTSweepMSS")
    check("D7 signal is honest about itself",
          sig is not None and 0 < sig.conviction < 1.0
          and "size_frac" in sig.notes and sig.underlying_stop < sig.underlying_entry
          < sig.underlying_target)
    check("D8 no regime label consulted", sig is not None and sig.regime == "")

    print("E — size mapping")
    check("E1 weak bias sizes zero", size_fraction(2.5, 0.4) == 0.0)
    check("E2 sub-AWARE displacement sizes zero", size_fraction(1.5, 0.9) == 0.0)
    check("E3 marginal tier", size_fraction(1.8, 0.6) == 0.33)
    check("E4 solid tier", size_fraction(2.1, 0.6) == 0.66)
    check("E5 full only when clean AND confirmed", size_fraction(2.1, 0.9) == 1.0)

    print("F — afternoon debit cutoff")
    reset_journal_state()
    rows.clear()
    sig = disp.ict_dispatch(fresh_ctx(), chain=None, now_et=et(13, 5), journal=jr)
    check("F1 post-cutoff fires nothing", sig is None)
    check("F2 wants_credit journaled",
          any("wants_credit" in (kw.get("blocked") or "") for _, kw in rows))
    os.environ.pop("OT_ICT_ARMED", None)
    os.environ.pop("OT_ICT_ICTSWEEPMSS_VALIDATED", None)

    print("G — deliberate failure (the suite can go red)")
    import importlib
    os.environ["OT_ICT_SELFTEST"] = "1"
    import strategy.ict.scoring as scoring_mod
    importlib.reload(scoring_mod)
    sc_bad = scoring_mod.SetupScore(setup="T", direction="long", components=[
        scoring_mod.Component("dir:a", 2.0, 0.1)])
    corrupted_detected = sc_bad.score() == 1.0   # selftest forces a perfect score
    os.environ.pop("OT_ICT_SELFTEST", None)
    importlib.reload(scoring_mod)
    check("G1 selftest corruption is visible to this suite", corrupted_detected)
    sc_ok = scoring_mod.SetupScore(setup="T", direction="long", components=[
        scoring_mod.Component("dir:a", 2.0, 0.1)])
    check("G2 honest arithmetic restored", abs(sc_ok.score() - 0.1) < 1e-9)

    print()
    if FAILS:
        print(f"ict_setups: {len(FAILS)} FAILURE(S): {FAILS}")
        sys.exit(1)
    print("ict_setups: ALL PASS (A context honesty · B scoring arithmetic · "
          "C SB gap-gated · D arming ladder · E size tiers · F debit cutoff · "
          "G deliberate-failure)")


if __name__ == "__main__":
    main()
