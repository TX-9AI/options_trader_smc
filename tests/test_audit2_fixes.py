"""
tests/test_audit2_fixes.py — v1.0 — 2026-08-15

EXECUTING tests for adversarial audit #2 fixes (A2.1-A2.9). Per
WORKING_AGREEMENT 21: every test here CALLS the real code and asserts on the
RESULT — mapper pools, ledger counts, manager counts — not on source text.
The two source asserts at the bottom are secondary reachability pins and say so.

DELIBERATE-FAILURE VERIFICATION: this suite must FAIL against HEAD `89cbaf6`
(the unpatched tree). Run performed at build time; the born-red result is
recorded in the BACKLOG entry.

Planted tape finds mechanisms, not frequencies (§12).
"""
import json
import os
import sys
import types
import datetime as _dt

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── broker SDK stub — module level, BEFORE any strategy import ────────────────
# On the boxes the real tastytrade imports and this block is a no-op; in a
# sandbox the strategy/position-manager import chains still resolve.
try:
    import tastytrade                                             # noqa: F401
except Exception:
    class _AnyAttr(types.ModuleType):
        def __getattr__(self, name):
            v = type(name, (), {"__getattr__": lambda s, n: s})()
            setattr(self, name, v)
            return v
    for _m in ("tastytrade", "tastytrade.instruments", "tastytrade.order",
               "tastytrade.session", "tastytrade.account",
               "tastytrade.streamer"):
        sys.modules.setdefault(_m, _AnyAttr(_m))

from analysis.liquidity_mapper import LiquidityMapper, LiquidityMap   # noqa: E402
import analysis.liquidity_ledger as LL                                # noqa: E402
from analysis.liquidity_ledger import LiquidityLedger                 # noqa: E402


# ── tape helpers ──────────────────────────────────────────────────────────────

def _bars(start_utc, end_utc, price_fn, freq="5min"):
    """OHLC frame in the shape fetch_candles serves: America/New_York index."""
    idx = pd.date_range(start=start_utc, end=end_utc, freq=freq, tz="UTC",
                        inclusive="left")
    rows = [(price_fn(t) + 0.10, price_fn(t) - 0.10, price_fn(t), price_fn(t), 100)
            for t in idx]
    df = pd.DataFrame(rows, index=idx,
                      columns=["high", "low", "close", "open", "volume"])
    df.index = df.index.tz_convert("America/New_York")
    return df


def _named(lmap):
    return {p.name: round(p.price, 2) for p in lmap.pools if p.is_named}


M = LiquidityMapper()


# ── A2.1 — truncation guard ──────────────────────────────────────────────────

def _tape_asia_spike(t):
    d, h, mi = t.date(), t.hour, t.minute
    if d == pd.Timestamp("2026-08-13").date():
        return 90.0
    if h < 8:
        return 101.0 if (h == 2 and mi == 0) else 97.0
    if h < 13:
        return 96.0
    return 95.0


def test_a21_left_truncated_section_is_not_admitted():
    """A section whose START slid off the frame edge must NOT become a pool.
    At HEAD it became `Asia High (R2) = 97.10` against a true high of 101.10."""
    full = _bars("2026-08-13 00:00", "2026-08-14 20:00", _tape_asia_spike)
    cut = pd.Timestamp("2026-08-14 13:35", tz="UTC")
    frame = full[full.index.tz_convert("UTC") < cut].tail(100)  # the live cap
    lmap = LiquidityMap()
    M._find_named_levels(lmap, frame)
    asia = [n for n in _named(lmap) if n.startswith("Asia High")]
    assert not asia, (
        f"truncated Asia admitted as {asia} — the frame starts 05:15 UTC, the "
        f"section starts 00:00, its 101.10 print is unprovable from this tape")


def test_a21_complete_sections_still_ladder():
    """The guard must not eat COMPLETE sections: a deep frame still produces
    the full ladder, wrong-price-free."""
    full = _bars("2026-08-13 00:00", "2026-08-14 20:00", _tape_asia_spike)
    lmap = LiquidityMap()
    M._find_named_levels(lmap, full)          # deep frame: everything complete
    names = _named(lmap)
    asia = {n: p for n, p in names.items() if n.startswith("Asia High")}
    assert asia and list(asia.values())[0] == 101.10, names


def test_a21_analyze_accepts_and_uses_named_df():
    """`analyze(named_df=...)` must feed named levels from the DEEP frame while
    pools/sweeps keep the live frames. Born-red at HEAD: TypeError."""
    full = _bars("2026-08-13 00:00", "2026-08-14 20:00", _tape_asia_spike)
    cut = pd.Timestamp("2026-08-14 13:35", tz="UTC")
    live = full[full.index.tz_convert("UTC") < cut].tail(100)
    lmap = M.analyze(live, live, 95.0, named_df=full)
    names = _named(lmap)
    assert any(n.startswith("Asia High") and p == 101.10
               for n, p in names.items()), names


# ── A2.5 — winter DST ────────────────────────────────────────────────────────

def _tape_winter(t):
    d, h = t.date(), t.hour
    if d == pd.Timestamp("2027-01-13").date():
        return 88.0
    if h < 8:
        return 89.0
    if h < 13:
        return 89.5
    return 92.0 + (h - 13) * 0.5


def test_a25_winter_forming_rth_is_never_a_pool():
    """2027-01-14 (EST): at 15:30 ET the session is OPEN. HEAD admitted today's
    forming RTH extreme as `NY High (R1)` because idx[-1].hour hit 20."""
    full = _bars("2027-01-13 00:00", "2027-01-14 20:35", _tape_winter)
    lmap = LiquidityMap()
    M._find_named_levels(lmap, full)
    # An offender is ANY named pool sitting on a price printed during TODAY'S
    # open RTH (>= 14:30 UTC on the 14th) — however the section mask sliced it.
    today_rth = full[full.index.tz_convert("UTC") >=
                     pd.Timestamp("2027-01-14 14:30", tz="UTC")]
    rth_prints = {round(h, 2) for h in today_rth["high"]}
    offenders = {n: p for n, p in _named(lmap).items() if p in rth_prints}
    assert not offenders, (
        f"today's FORMING RTH extreme published as a pool mid-session: "
        f"{offenders}")


def test_a25_winter_closed_ny_is_admitted_next_day():
    """Yesterday's winter NY session (14:30-21:00 UTC) is complete and must
    still ladder — the fix narrows admission, it must not kill NY in winter."""
    def tape(t):
        d, h = t.date(), t.hour
        if d == pd.Timestamp("2027-01-13").date():
            return 94.0 if 14 <= h < 21 else 88.0
        return 89.0 if t.hour < 13 else 90.0
    full = _bars("2027-01-13 00:00", "2027-01-14 15:00", tape)
    lmap = LiquidityMap()
    M._find_named_levels(lmap, full)
    # Yesterday's RTH extreme and yesterday's full-day extreme are the SAME
    # print here, so the collision merge (correctly) names it `PDH (R2)` — the
    # doctrine's norm. What must hold: the 94.10 level EXISTS as a rung.
    assert any(p == 94.10 and "(R" in n
               for n, p in _named(lmap).items()), _named(lmap)


# ── A2.6 — sessions are ON by doctrine; forming never a pool ─────────────────

def test_a26_session_rungs_present_by_default_no_dead_knob():
    """LIQ.6 rule 1: sessions ARE named pools — and the dead flag is GONE.
    The invariant LIQ.1 actually protects is pinned by the two tests above:
    a still-forming section is never a pool."""
    import analysis.liquidity_mapper as LM
    assert not hasattr(LM, "NAMED_POOLS_INCLUDE_SESSIONS"), \
        "the dead knob is back — it gated nothing and its test asserted the " \
        "opposite of production"
    full = _bars("2026-08-13 00:00", "2026-08-14 20:00", _tape_asia_spike)
    lmap = LiquidityMap()
    M._find_named_levels(lmap, full)
    assert any("(R" in n for n in _named(lmap)), "no session rungs emitted"


# ── A2.7 — a collision never deletes a fact ──────────────────────────────────

def test_a27_more_extreme_rung_keeps_the_pdh_fact():
    """PDH 100.00 vs a more-extreme rung 100.15 inside the 0.2% zone: HEAD
    replaced the name wholesale and PDH vanished from the map."""
    lmap = LiquidityMap()
    M._add_named_pool(lmap, 100.00, "high", "PDH")
    M._add_named_pool(lmap, 100.15, "high", "Asia High (R2)")
    names = _named(lmap)
    assert len(names) == 1
    (name, price), = names.items()
    assert price == 100.15, "the outer price wins — operator's rule"
    assert "PDH" in name and "(R2)" in name, (
        f"a fact was deleted: {name!r} — both facts must survive the collision")


def test_a27_shipped_direction_unchanged():
    """The already-shipped merge (existing more extreme, rung arrives) still
    reads `PDH (R2)` at PDH's price."""
    lmap = LiquidityMap()
    M._add_named_pool(lmap, 100.15, "high", "PDH")
    M._add_named_pool(lmap, 100.00, "high", "NY High (R2)")
    names = _named(lmap)
    assert names == {"PDH (R2)": 100.15}, names


# ── A2.3 — the record survives the restart ───────────────────────────────────

@pytest.fixture()
def ledger_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(LL, "_OUT_ROOT", str(tmp_path))
    return tmp_path


def test_a23_restart_hydrates_same_date(ledger_dir):
    led = LiquidityLedger("T")
    led.reset_for_session("2026-08-14", seeds=[(100.0, "high", "PDH", True)])
    led.on_closed_bar(100.05, 99.3, 99.6, ts="2026-08-14 10:00:00-04:00")
    assert led.write()
    led2 = LiquidityLedger("T")                     # the bake
    led2.reset_for_session("2026-08-14",
                           seeds=[(100.0, "high", "PDH", True),
                                  (95.0, "low", "PDL", True)])
    lv = next(l for l in led2.levels if l.kind == "high")
    assert (lv.touches, lv.holds) == (1, 1), \
        "the morning's counts were wiped by the restart"
    assert led2.last_bar_ts == "2026-08-14 10:00:00-04:00", \
        "last_bar_ts did not survive — the bake gap cannot be recovered"
    assert any(l.kind == "low" for l in led2.levels), \
        "new seeds must still merge in after hydration"


def test_a23_tolerance_change_starts_clean(ledger_dir, monkeypatch):
    led = LiquidityLedger("T2")
    led.reset_for_session("2026-08-14", seeds=[(100.0, "high", "PDH", True)])
    led.on_closed_bar(100.05, 99.3, 99.6, ts="t")
    led.write()
    path = os.path.join(str(ledger_dir), "2026-08-14", "T2.json")
    payload = json.load(open(path))
    payload["touch_tol_pct"] = 0.0002               # the pre-LIQ.7 era
    json.dump(payload, open(path, "w"))
    led2 = LiquidityLedger("T2")
    led2.reset_for_session("2026-08-14", seeds=[(100.0, "high", "PDH", True)])
    lv = led2.levels[0]
    assert lv.touches == 0, \
        "counts taken under a different zone are NOT comparable (LIQ.7)"


# ── A2.4 — no closed bar is skipped ──────────────────────────────────────────

def _mk1m(rows, start="2026-08-14 09:30"):
    idx = pd.date_range(start, periods=len(rows), freq="1min",
                        tz="America/New_York")
    return pd.DataFrame(rows, index=idx, columns=["high", "low", "close"])


def test_a24_gap_between_ticks_is_recovered(ledger_dir):
    """Two bars close between ticks (a slow tick): the middle bar's touch must
    be counted. HEAD's iloc[-2] + one-stamp guard lost it (reproduced)."""
    led = LiquidityLedger("T3")
    led.reset_for_session("2026-08-14", seeds=[(100.0, "high", "PDH", True)])
    t1 = _mk1m([(99.5, 99.0, 99.2), (99.4, 99.0, 99.1)])
    t2 = _mk1m([(99.5, 99.0, 99.2), (100.05, 99.3, 99.6),
                (99.7, 99.2, 99.4), (99.6, 99.1, 99.3)])
    led.feed_frame(t1)
    led.feed_frame(t2)
    lv = led.levels[0]
    assert lv.touches == 1 and lv.holds == 1, (
        f"the 09:31 bar (wick 100.05) was dropped: touches={lv.touches}")


def test_a24_forming_bar_and_offsession_rows_never_fed(ledger_dir):
    """The last row is FORMING and pre-9:30/foreign-date rows are not the
    session: none of them may touch the book, and a refeed must not double."""
    led = LiquidityLedger("T4")
    led.reset_for_session("2026-08-14", seeds=[(100.0, "high", "PDH", True)])
    rows = [(100.5, 99.0, 99.2),        # 09:28 pre-market — excluded
            (100.5, 99.0, 99.2),        # 09:29 pre-market — excluded
            (100.05, 99.3, 99.6),       # 09:30 RTH — the one real touch
            (100.9, 99.0, 99.2)]        # 09:31 FORMING — excluded
    df = _mk1m(rows, start="2026-08-14 09:28")
    assert led.feed_frame(df) == 1
    assert led.feed_frame(df) == 0      # idempotent on the same frame
    lv = led.levels[0]
    assert (lv.touches, lv.holds) == (1, 1), (lv.touches, lv.holds)


# ── A2.2 — the count the announcement needs, and why the old site was dead ───

def _pm_with(records):
    """A PositionManager wired to a stub logger (SDK stubbed at module top)."""
    from execution.position_manager import PositionManager
    pm = PositionManager(paper_trading=True)
    stub = types.SimpleNamespace(get_open_trades=lambda: list(records))
    pm._trade_logger = stub
    pm._open_records = []
    return pm


_LEG = {"trade_id": "x" * 36, "is_condor_leg": 1, "status": "open",
        "symbol": "IWM", "strategy": "IronCondorStrategy"}


def test_a22_open_condor_leg_count_executes():
    pm = _pm_with([_LEG])
    assert pm.open_condor_leg_count() == 1
    assert _pm_with([]).open_condor_leg_count() == 0


def test_a22_why_the_old_site_was_dead():
    """With an open leg in the DB, has_open_position() is True — so
    attempt_new_entry (the ONLY caller of the old announcement path) cannot
    run. This is the reachability fact the F5 tests never asserted."""
    pm = _pm_with([_LEG])
    assert pm.has_open_position() is True


def test_a22_announcement_fires_from_a_reachable_state(caplog):
    """The warning itself, executed: legs open, no plan in memory."""
    import logging
    from strategy.iron_condor_strategy import IronCondorStrategy
    o = IronCondorStrategy()
    with caplog.at_level(logging.WARNING):
        o.report_orphaned_plan(1)
    assert any("NO PLAN" in r.message for r in caplog.records)
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        o.report_orphaned_plan(1)                    # latched — silent
    assert not caplog.records
    o._last_reset_date = "2000-01-01"
    o._reset_if_new_day()                            # a new day re-arms it
    assert o._orphan_said is False


# ── secondary reachability pins (source asserts, and they say so) ────────────

def _main_src():
    return open(os.path.join(os.path.dirname(__file__), "..", "main.py"),
                encoding="utf-8").read()


def test_a22_announce_call_lives_in_the_manage_branch():
    """SOURCE PIN (secondary): the announce call must sit inside the
    has_open_position branch — the executing tests above prove the parts; this
    pins their assembly point in main."""
    src = _main_src()
    i = src.index("pos_mgr.manage_open_position(")
    j = src.index("attempt_new_entry(ctx, regime, state)")
    seg = src[i:j]
    assert "report_orphaned_plan(" in seg and "open_condor_leg_count()" in seg


def test_a21_named_frame_reaches_the_mapper():
    """SOURCE PIN (secondary): run_analysis passes the deep frame through."""
    src = _main_src()
    i = src.index("liq_map   = get_liquidity_mapper().analyze(")
    assert "named_df=_named_level_frame()" in src[i:i + 200]
