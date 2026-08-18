"""
tests/test_tcs_floor_durability.py — v1.3 — 2026-08-04

Plants worlds with a known answer and asserts the tool recovers each, the same
way tests/test_a2_partition_recovers.py and tests/test_gap_pool.py do.

Two of these guard against ways the tool could be confidently WRONG rather than
merely empty:

  - DEDUP. The readiness track scores every tick, so one impulse appears on
    hundreds of consecutive journal rows. Counting them all would report a
    sample size that does not exist and weight a long-lived impulse hundreds of
    times. The test plants 200 rows describing ONE impulse and asserts n=1.

  - CLOSE, NOT WICK. A world where price wicks through the floor and closes
    back above it must read HELD, with the penetration recorded separately. If
    the two ever merge, the durability number silently becomes a stop-out
    statistic and stops answering the question the strategy asks.

v1.3 — 2026-08-04 — three tests for the matched control, including that the
SEED moves the control draw and nothing else. A seed that perturbed the measured
population would make the comparison meaningless while still printing a number.

v1.2 — 2026-08-04 — three tests for the terminal/intraday split and the strike
curve. The recovery case is the one that matters: v1.1 reported an 82% intraday
violation rate on the real corpus, and without this distinction that reads as an
82% LOSS rate for a trade that expires on the close.

v1.1 — 2026-08-04 — fixtures now carry `machine`/`r`, and four tests cover the
population filter. v1.0 shipped without it and its first real run measured every
floor the rolling lookback ever computed rather than the ones the strategy would
have traded — a confidently wrong number, which is the class this file exists to
prevent.

Deliberate-failure check performed when written: dropping the dedup key turns
test_one_impulse_counts_once red (n becomes 200); switching the break test from
close to low turns test_a_wick_through_the_floor_still_holds red; defaulting
--machine to ANY turns test_dormant_floors_are_excluded_by_default red.
"""

import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(REPO, "tests", "tcs_floor_durability.py")
DATE = "2026-07-30"


def _world(tmp, bars, floor=100.0, direction="long", sd=2.2, n_rows=1,
           sym="AAA", t0="14:00", machine="ARMED", r=0.62):
    """bars: list of (hhmm, close, high, low) AFTER the impulse."""
    jdir = os.path.join(tmp, "signal_journal", DATE)
    odir = os.path.join(tmp, "ohlc", DATE)
    os.makedirs(jdir, exist_ok=True)
    os.makedirs(odir, exist_ok=True)

    with open(os.path.join(jdir, f"{sym}.jsonl"), "w") as fh:
        for _ in range(n_rows):
            fh.write(json.dumps({
                "ts_et": f"{DATE}T{t0}:00",
                "readiness": {"strategy": "trend_credit_spread",
                              "machine": machine, "r": r,
                              "factors": {"floor_px": floor, "dir": direction,
                                          "sd_ratio": sd}},
            }) + "\n")

    with open(os.path.join(odir, f"{sym}_ohlc_{DATE}.csv"), "w") as fh:
        fh.write("timestamp,open,high,low,close\n")
        for hhmm, c, h, lo in bars:
            fh.write(f"{DATE}T{hhmm}:00,{c},{h},{lo},{c}\n")
    return tmp


def _run(tmp, *extra):
    p = subprocess.run(
        [sys.executable, TOOL,
         "--journal", os.path.join(tmp, "signal_journal", "*", "*.jsonl"),
         "--ohlc", os.path.join(tmp, "ohlc"),
         "--since", "2026-07-01"] + list(extra),
        capture_output=True, text=True, cwd=REPO)
    return p.stdout + p.stderr


def _held_bars():
    """Six bars that never close through 100.0 — the floor holds."""
    return [("14:0" + str(i), 101.0 + i, 102.0 + i, 100.5) for i in range(1, 7)]


def _broken_bars():
    """Closes back through the floor at 14:03."""
    return [("14:01", 101.0, 102.0, 100.5), ("14:02", 100.6, 101.0, 100.2),
            ("14:03", 99.0, 100.4, 98.5), ("14:04", 98.0, 99.5, 97.0),
            ("14:05", 97.5, 98.5, 97.0), ("14:06", 97.0, 98.0, 96.5)]


def test_a_holding_floor_reads_held():
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_world(tmp, _held_bars()))
        assert "floor HELD    : 1 (100.0%)" in out, out[:900]


def test_a_broken_floor_reads_broken():
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_world(tmp, _broken_bars()))
        assert "floor HELD    : 0 (0.0%)" in out, out[:900]


def test_one_impulse_counts_once():
    """200 journal rows, one impulse. The track scores every tick; counting the
    rows would invent a sample that does not exist."""
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_world(tmp, _held_bars(), n_rows=200))
        assert "impulses      : 1 distinct (deduped from 200 scored rows)" in out, \
            out[:900]


def test_a_wick_through_the_floor_still_holds():
    """Price trades to 98 but every close stays above 100 — the strike was
    threatened, not taken. Durability must say HELD and record the wick."""
    bars = [("14:01", 101.0, 102.0, 98.0), ("14:02", 100.5, 101.5, 99.0),
            ("14:03", 101.0, 102.0, 100.2), ("14:04", 101.5, 102.5, 100.9),
            ("14:05", 102.0, 103.0, 101.0), ("14:06", 102.5, 103.5, 101.5)]
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_world(tmp, bars))
        assert "floor HELD    : 1 (100.0%)" in out, out[:900]


def test_short_direction_is_mirrored():
    """A bear impulse fails when price closes ABOVE the floor."""
    bars = [("14:01", 99.0, 99.5, 98.0), ("14:02", 101.0, 101.5, 100.0),
            ("14:03", 102.0, 102.5, 101.0), ("14:04", 102.5, 103.0, 102.0),
            ("14:05", 103.0, 103.5, 102.5), ("14:06", 103.5, 104.0, 103.0)]
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_world(tmp, bars, direction="short"))
        assert "floor HELD    : 0 (0.0%)" in out, out[:900]


def test_an_impulse_with_no_forward_window_is_dropped_not_scored():
    """Armed at 15:58 there is nothing to measure. Scoring it either way would
    be a fabricated observation."""
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_world(tmp, [("15:59", 101.0, 101.5, 100.5)], t0="15:58"),
                   "--diagnose")
        assert "no_forward_window    1" in out, out[:900]


def test_thin_buckets_are_refused_not_reported():
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_world(tmp, _held_bars()))
        assert "REFUSED (under n=30)" in out, out[:900]


def test_dormant_floors_are_excluded_by_default():
    """v1.1, and it is the correction that mattered. The impulse lookback rolls
    on EVERY tick, so most floors the track computes belong to moments when it
    was DORMANT and the strategy would never have sold anything. Measuring their
    durability answers a question nobody asked — v1.0 did exactly that on its
    first real run and reported 5,129 'impulses'."""
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_world(tmp, _held_bars(), machine="DORMANT"), "--diagnose")
        assert "not_armed            1" in out, out[:900]


def test_any_reproduces_the_unfiltered_population():
    """Kept so the difference between the two populations can be SHOWN. It is
    not a mode anyone should read a result from."""
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_world(tmp, _held_bars(), machine="DORMANT"),
                   "--machine", "ANY")
        assert "floor HELD    : 1 (100.0%)" in out, out[:900]
        assert "NOT the traded population" in out


def test_staging_plus_admits_both_live_states():
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_world(tmp, _held_bars(), machine="STAGING"),
                   "--machine", "STAGING+")
        assert "floor HELD    : 1 (100.0%)" in out, out[:900]


def test_min_r_filters():
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_world(tmp, _held_bars(), r=0.40), "--min-r", "0.55",
                   "--diagnose")
        assert "below_min_r          1" in out, out[:900]


def test_a_violation_that_recovers_by_the_bell_is_terminal_OK():
    """THE v1.2 DISTINCTION. Price closes through the floor at 14:03 and closes
    back above it by the last bar. Intraday says violated; terminal says fine.
    A defined-risk 0DTE spread expires on the second, not the first — merging
    them is how an 82% intraday violation rate gets mistaken for an 82% loss
    rate."""
    bars = [("14:01", 101.0, 102.0, 100.5), ("14:03", 98.0, 100.4, 97.5),
            ("14:10", 99.0, 99.5, 98.0), ("15:00", 100.5, 101.0, 99.5),
            ("15:30", 101.5, 102.0, 101.0), ("15:45", 102.0, 102.5, 101.5)]
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_world(tmp, bars))
        assert "floor HELD    : 0 (0.0%)" in out, out[:900]
        assert "terminal OK   : 1 (100.0%)" in out, out[:900]
        assert "recovered     : 1 (100.0%)" in out, out[:900]


def test_a_violation_that_stays_broken_fails_both():
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_world(tmp, _broken_bars()))
        assert "floor HELD    : 0 (0.0%)" in out, out[:900]
        assert "terminal OK   : 0 (0.0%)" in out, out[:900]
        assert "recovered     : 0 (0.0%)" in out, out[:900]


def test_the_strike_curve_prices_distance():
    """Terminal close is 98.0 against a floor of 100.0 — a 2% breach. A strike
    AT the floor fails; a strike 3% beyond it (97.0) survives. The curve must
    show exactly that crossing, because that crossing IS the rule."""
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_world(tmp, _broken_bars()))
        curve = out.split("STRIKE CURVE")[1]
        rows = {l.split("%")[0].strip(): l for l in curve.splitlines()
                if l.strip().startswith(("0.", "1.", "2.", "3."))}
        assert "100.0%" in rows["0.00"], rows.get("0.00")
        assert "0.0%" in rows["3.00"], rows.get("3.00")


def test_the_matched_control_reports_and_is_seeded():
    """v1.3. Without a control, 62% terminal survival is an absolute with nothing
    to beat — in a trending tape a recent low holds terminally a lot of the time
    simply because trends trend."""
    with tempfile.TemporaryDirectory() as tmp:
        w = _world(tmp, _held_bars())
        a = _run(w, "--control", "matched")
        b = _run(w, "--control", "matched")
        assert "MATCHED CONTROL" in a, a[:900]
        assert "impulse minus control, TERMINAL:" in a
        assert a == b, "same seed must give the same control draw"


def test_a_different_seed_moves_the_draw_only():
    """The real observation must be identical across seeds; only the control
    changes. If the seed touched the measured population the comparison would
    be meaningless."""
    with tempfile.TemporaryDirectory() as tmp:
        w = _world(tmp, _held_bars())
        a = _run(w, "--control", "matched", "--seed", "1")
        b = _run(w, "--control", "matched", "--seed", "2")
        head = lambda o: o.split("MATCHED CONTROL")[0]
        assert head(a) == head(b), "the measured population must not move"


def test_the_control_is_actually_DRAWN_not_anchored():
    """Found by the deliberate-failure run: replacing rng.choice with elig[0]
    left every other control test GREEN. Determinism and 'the head does not
    move' are both satisfied by a fixed anchor, so neither of them proves the
    draw is a draw. This does — across several seeds the control section must
    take at least two distinct values on a tape with many eligible anchors.
    """
    bars = [(f"{9 + i // 60:02d}:{i % 60:02d}", 100.0 + (i % 7) - 3,
             102.0 + (i % 7) - 3, 97.0 + (i % 7) - 3) for i in range(120)]
    with tempfile.TemporaryDirectory() as tmp:
        w = _world(tmp, bars, floor=99.0, t0="09:00")
        seen = {(_run(w, "--control", "matched", "--seed", str(s))
                 .split("MATCHED CONTROL")[1][:200]) for s in range(1, 9)}
        assert len(seen) > 1, "the control anchor is fixed, not drawn"


def test_control_is_off_by_default():
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_world(tmp, _held_bars()))
        assert "MATCHED CONTROL" not in out


def test_min_sd_filters():
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_world(tmp, _held_bars(), sd=1.0), "--min-sd", "1.5",
                   "--diagnose")
        assert "below_min_sd         1" in out, out[:900]
