"""
tests/test_pitchfork_uniqueness_scan.py — v1.0 — 2026-08-04

Guards pitchfork v1.2's §4.3.5 scan. Two things must both hold: the scan must
recover forks the take-the-last-three reading loses (or it is not worth having),
and it must be INERT while off (or the head-to-head it exists to enable is
already contaminated).
"""
import sys, os
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import analysis.pitchfork as pf  # noqa: E402

ATR = 4.0


def _frame(prices):
    idx = pd.date_range("2026-07-01", periods=len(prices), freq="h")
    return pd.DataFrame({"high": [p + 0.2 for p in prices],
                         "low": [p - 0.2 for p in prices],
                         "close": prices}, index=idx)


def _zig(points, seg):
    out = [points[0]]
    for a, b in zip(points, points[1:]):
        out += list(np.linspace(a, b, seg + 1))[1:]
    return out


def _clean():
    """Wide alternating structure; the newest triple qualifies on its own."""
    return _frame(_zig([100, 125, 108, 136, 116, 146], 9))


def _spoiled():
    """Same structure, then a recent swing that makes the NEWEST triple fail
    structurally while an older qualifying triple still sits behind it."""
    return _frame(_zig([100, 125, 108, 136, 116, 146], 9)
                  + _zig([146, 120, 150, 122], 4))


def test_scan_recovers_a_fork_the_last_three_reading_loses():
    df = _spoiled()
    assert pf.build_fork("X", df, "1h", ATR, uniqueness_scan=False) is None
    assert pf.last_reject_reason() is not None
    fork = pf.build_fork("X", df, "1h", ATR, uniqueness_scan=True)
    assert fork is not None, "the scan must find the older qualifying triple"
    assert "uniqueness_scan" in fork.filters_passed


def test_scan_is_inert_when_the_newest_triple_already_qualifies():
    df = _clean()
    off = pf.build_fork("X", df, "1h", ATR, uniqueness_scan=False)
    on = pf.build_fork("X", df, "1h", ATR, uniqueness_scan=True)
    assert off is not None and on is not None
    for attr in ("origin_idx", "origin_price", "slope", "born_idx", "direction"):
        assert getattr(off, attr) == getattr(on, attr), \
            f"{attr} differs — the scan changed a fork it should not have touched"
    assert "uniqueness" in off.filters_passed


def test_default_is_off_so_the_head_to_head_is_not_pre_contaminated():
    df = _spoiled()
    assert pf.build_fork("X", df, "1h", ATR) is None, \
        "v1.2 must ship dark; a default-on scan would make the A/B unmeasurable"


def test_scan_depth_reports_how_far_back_it_went():
    assert pf.build_fork("X", _clean(), "1h", ATR, uniqueness_scan=True) is not None
    assert pf.last_scan_depth() == 1, "no scan needed on a clean triple"
    assert pf.build_fork("X", _spoiled(), "1h", ATR, uniqueness_scan=True) is not None
    assert pf.last_scan_depth() > 1, "a recovered fork must report the depth"


def test_off_reports_depth_one_not_zero():
    """The audit compares depths across readings; off must be a real 1."""
    pf.build_fork("X", _spoiled(), "1h", ATR, uniqueness_scan=False)
    assert pf.last_scan_depth() == 1


def test_scan_cannot_reach_an_unconfirmed_pivot():
    """§4.4 — candidates come from the already-confirmed list, so scanning back
    can only reach pivots knowable at now_idx. Truncating the frame must not
    change a fork built with an explicit earlier now_idx."""
    df = _clean()
    n = len(df) - 5
    full = pf.build_fork("X", df, "1h", ATR, now_idx=n, uniqueness_scan=True)
    trunc = pf.build_fork("X", df.iloc[:n + 1], "1h", ATR, uniqueness_scan=True)
    assert (full is None) == (trunc is None)
    if full is not None:
        assert full.slope == pytest.approx(trunc.slope)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
