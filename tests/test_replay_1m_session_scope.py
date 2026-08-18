"""
tests/test_replay_1m_session_scope.py — v1.0 — 2026-08-01.

THE DEFECT THIS EXISTS FOR (found 2026-08-01 working item S):
    replay_confluence v1.2 added the ADX-warmup bookmark — prior sessions of 1m
    tape prepended so the resampled 5m/15m/1h carry ADX-14 / EMA-50 history from
    the target day's first tick. That part is correct and is the whole point of
    the bookmark. But `s1m` was then sliced out of the SAME concatenated frame,
    so the 25-bar 1-minute close window handed to the scorer straddled the
    overnight gap for the opening 25 bars of every replayed session.

    market_data v3.1 session-scopes the 1m frame ONLY, deliberately — the
    "no overnight padding" rule. tests/test_market_data_contract.py already
    asserts that contract on the LIVE path. The replay violated the identical
    contract, which is the live-vs-replay divergence class WORKING_AGREEMENT §10
    exists to catch:

        live   : < 25 one-minute bars until ~09:55 -> closes=None
                 -> RANGING and COMPRESSION go UNSCORED for the first 25 minutes
        replay : scored both from 09:30 off a gap-spanning regression

    Every offline artifact built with the bookmark on therefore contained opening
    ticks the live engine could not have produced.

WHY NOTHING CAUGHT IT:
    the bookmark made the replay MORE correct on the frames anyone was looking at
    (ADX went from 0.0 to warm), so the fix that introduced the 1m contamination
    was validated by the improvement it also delivered.

THE RULE THIS ENFORCES:
    warm history belongs to the RESAMPLE. The 1-minute close window is scoped to
    the session under test, and `closes` is None below RANGE_WINDOW_BARS — the
    same shape main.py passes.

Run: PYTHONPATH=. pytest tests/test_replay_1m_session_scope.py -v
"""

import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.regime_confluence import RANGE_WINDOW_BARS  # noqa: E402
from tests.replay_confluence import replay_symbol  # noqa: E402

PRIOR_DATE = "2026-07-20"
TARGET_DATE = "2026-07-21"
SYMBOL = "SCOPETEST"


def _write_session(root, date, base, drift, seed):
    """390 one-minute bars, 09:30–15:59 ET, in the layout the replay walks."""
    rnd = random.Random(seed)
    day_dir = os.path.join(root, date)
    os.makedirs(day_dir, exist_ok=True)
    path = os.path.join(day_dir, f"{SYMBOL}_ohlc_{date}.csv")
    px = base
    with open(path, "w") as fh:
        fh.write("timestamp,open,high,low,close,volume\n")
        for i in range(390):
            hh = 9 + (30 + i) // 60
            mm = (30 + i) % 60
            px += drift + rnd.uniform(-0.15, 0.15)
            o = px
            c = px + rnd.uniform(-0.08, 0.08)
            hi = max(o, c) + rnd.uniform(0, 0.06)
            lo = min(o, c) - rnd.uniform(0, 0.06)
            fh.write(f"{date}T{hh:02d}:{mm:02d}:00-04:00,"
                     f"{o:.2f},{hi:.2f},{lo:.2f},{c:.2f},1000\n")
    return path


@pytest.fixture(scope="module")
def tape(tmp_path_factory):
    """Prior session trends up and closes near 105; target session GAPS DOWN to
    99 and chops. The gap is what a straddling regression would swallow."""
    root = str(tmp_path_factory.mktemp("ohlc"))
    _write_session(root, PRIOR_DATE, 100.0, 0.013, seed=7)
    target = _write_session(root, TARGET_DATE, 99.0, 0.0, seed=11)
    return target


def _recs(target, warm_sessions):
    recs, _ = replay_symbol(target, warmup=20, use_v13=False,
                            warm_sessions=warm_sessions)
    return recs


def test_opening_ticks_are_unscored_for_ranging(tape):
    """The core contract: with the bookmark ON, RANGING is not scored until the
    target session itself has RANGE_WINDOW_BARS bars — exactly as live."""
    recs = _recs(tape, warm_sessions=1)
    assert recs, "no ticks replayed"
    assert recs[0]["ts"] == "09:30", "warm replay should still score from the open"
    opening = recs[: RANGE_WINDOW_BARS - 1]
    scored = [r["ts"] for r in opening if r["scores"].get("RANGING") is not None]
    assert not scored, f"RANGING scored on gap-spanning windows at {scored}"


def test_compression_follows_the_same_rule(tape):
    """COMPRESSION reads the same 1m window, so it must go unscored identically —
    the pair is what main.py's starvation path nulls together."""
    recs = _recs(tape, warm_sessions=1)
    opening = recs[: RANGE_WINDOW_BARS - 1]
    scored = [r["ts"] for r in opening if r["scores"].get("COMPRESSION") is not None]
    assert not scored, f"COMPRESSION scored on gap-spanning windows at {scored}"


def test_ranging_resumes_once_the_session_has_a_full_window(tape):
    """Not merely absent — the window must actually arrive. Guards against a fix
    that silently nulls RANGING for the whole session."""
    recs = _recs(tape, warm_sessions=1)
    later = [r for r in recs[RANGE_WINDOW_BARS:] if r["scores"].get("RANGING") is not None]
    assert len(later) > 300, f"RANGING should score after the window fills; got {len(later)}"


def test_htf_warming_is_untouched(tape):
    """The bookmark's actual job. Cold replay is trend-blind at the open (the
    v1.2 defect); warm replay is not. If this fails the fix over-corrected and
    threw away the warm resample along with the 1m contamination."""
    cold = {r["ts"]: r for r in _recs(tape, warm_sessions=0)}
    warm = {r["ts"]: r for r in _recs(tape, warm_sessions=1)}
    cold_adx = cold["09:50"]["breakdown"].get("TRENDING", {}).get("adx")
    warm_adx = warm["09:50"]["breakdown"].get("TRENDING", {}).get("adx")
    assert cold_adx == 0.0, f"expected cold replay trend-blind at 09:50, got {cold_adx}"
    assert warm_adx and warm_adx > 10.0, f"expected warm ADX at 09:50, got {warm_adx}"


def test_fix_is_inert_when_the_bookmark_is_off(tape):
    """--warm-sessions 0 has no prior tape to leak, so the scoped slice must not
    change a single score. Inertness is half of item S's validation criteria."""
    recs = _recs(tape, warm_sessions=0)
    assert recs, "no ticks replayed"
    unscored = [r["ts"] for r in recs if r["scores"].get("RANGING") is None]
    # only the first bars of the run, before the window fills, may be unscored
    assert all(t <= recs[RANGE_WINDOW_BARS]["ts"] for t in unscored), \
        f"unexpected unscored ticks with the bookmark off: {unscored[:5]}"


def test_replay_does_not_slice_1m_from_the_warm_frame(tape):
    """Source-level guard. The behavioural tests above pass if someone reverts the
    slice AND the window happens to fill; this asserts the construct itself."""
    here = os.path.dirname(os.path.abspath(__file__))
    src = open(os.path.join(here, "replay_confluence.py")).read()
    assert "s1m = df1m.iloc[: i + 1]" not in src, \
        "s1m is being sliced from the warm concatenated frame again"
    assert "s1m = df1m.loc[score_start:t]" in src, \
        "s1m must be scoped to the target session"
