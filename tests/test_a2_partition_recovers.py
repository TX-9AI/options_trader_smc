"""
tests/test_a2_partition_recovers.py — v1.0 — 2026-08-01.

WHAT THIS PROVES
    tests/a2_partition.py claims it can separate three A2 hypotheses that all
    produce the same time-of-day signature. A tool that cannot recover a signal
    it PLANTED itself cannot be trusted on the corpus — and this repo has already
    shipped one analysis tool that printed a confident verdict with its
    discriminator silently missing (a2_characterise v1.0, breakdown-key defect).

    So: synthesize corpora where the answer is known by construction, and assert
    the tool reports it. Three worlds, each a superset of the last:

      A  H1 only          uniform violation rate in every cell, all day
      B  H1 + H2          uniform, plus a morning lift in EVERY gap class equally
                          (an opening drive needs no gap)
      C  H1 + H2 + H3     uniform, morning lift, plus continuation gaps inflated
                          AND reversal gaps pushed BELOW the midday baseline

    World C is the one that matters: the reversal-gap DEFICIT is the only
    fingerprint H1 and H2 cannot produce, because neither can subtract.

    A fourth case asserts the refusal discipline — thin cells must yield REFUSED,
    never a weak verdict.

Run: PYTHONPATH=. pytest tests/test_a2_partition_recovers.py -v
"""

import json
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

SYMS = [f"SYM{i}" for i in range(6)]
DATES = [f"2026-06-{d:02d}" for d in range(1, 15)]
CLASS_CYCLE = ("CONT", "FLAT", "REV")

# minutes-of-day for each bucket, chosen well inside the boundaries
BUCKET_TIMES = {
    "OPEN": [f"09:{m:02d}" for m in range(31, 60)] + [f"10:{m:02d}" for m in range(0, 39)],
    "DECAY": [f"10:{m:02d}" for m in range(41, 60)] + [f"11:{m:02d}" for m in range(0, 59)],
    "CLEAN": [f"{h:02d}:{m:02d}" for h in range(12, 16) for m in range(0, 59)],
}


def _gap_doc(tmp):
    """One gap record per (date, symbol), cycling the three classes so every cell
    of the grid gets population from every session."""
    sessions = {}
    for di, date in enumerate(DATES):
        rec = {}
        for si, sym in enumerate(SYMS):
            klass = CLASS_CYCLE[(di + si) % 3]
            rec[sym] = {"gap_pct": {"CONT": 0.8, "FLAT": 0.02, "REV": -0.8}[klass],
                        "prior_date": "2026-05-31", "prior_close": 100.0, "open": 100.5,
                        "prior_dir_70": 1, "prior_move_70_pct": 0.5,
                        "prior_dir_day": 1, "prior_move_day_pct": 0.5,
                        "gap_class": klass}
        sessions[date] = rec
    path = os.path.join(tmp, "gap_pct.json")
    with open(path, "w") as fh:
        json.dump({"flat_pct": 0.10, "prior_dir_minutes": 70,
                   "ohlc_root": "synthetic", "sessions": sessions}, fh)
    return path


def _write_corpus(tmp, rates, ticks_per_cell=40):
    """rates: {(bucket, class): violation_fraction}. Emits one jsonl per date in
    the layout a2_partition discovers (regime_replay_<date>.jsonl), with exactly
    the planted fraction of violating ticks per cell — deterministic, no RNG, so
    a failure is a tool defect and never a seed."""
    with open(os.path.join(tmp, "gap_pct.json")) as fh:
        sessions = json.load(fh)["sessions"]
    for date in DATES:
        lines = []
        for sym in SYMS:
            klass = sessions[date][sym]["gap_class"]
            for bucket, times in BUCKET_TIMES.items():
                frac = rates.get((bucket, klass), 0.0)
                n_viol = int(round(frac * ticks_per_cell))
                for i in range(ticks_per_cell):
                    viol = i < n_viol
                    trend = 0.80 if viol else 0.80
                    rng = 0.70 if viol else 0.20      # only RANGING decides it
                    lines.append(json.dumps({
                        "ts": times[i % len(times)], "sym": sym, "price": 100.0,
                        "scores": {"TRENDING_BULL": trend, "TRENDING_BEAR": 0.0,
                                   "RANGING": rng, "COMPRESSION": 0.1, "BREAKOUT": 0.1},
                        "breakdown": {"TRENDING": {"adx": 45.0},
                                      "RANGING": {"angle": 6.5}},
                    }))
        with open(os.path.join(tmp, f"regime_replay_{date}.jsonl"), "w") as fh:
            fh.write("\n".join(lines) + "\n")


def _run(home, gaps_path):
    """Invoke the tool exactly as the operator would — one line, no imports.
    HOME is redirected so the tool's own ~/day_trader_pro/reports auto-discovery
    is what finds the corpus; only the gap lookup is passed explicitly."""
    out = subprocess.run(
        [sys.executable, os.path.join(REPO, "tests", "a2_partition.py"),
         "--gaps", gaps_path],
        cwd=home, capture_output=True, text=True,
        env={**os.environ, "HOME": home, "PYTHONPATH": REPO})
    return out.stdout + out.stderr


@pytest.fixture
def world(tmp_path):
    def build(rates, ticks_per_cell=40):
        # the tool auto-discovers under ~/day_trader_pro/reports
        rep = tmp_path / "day_trader_pro" / "reports"
        rep.mkdir(parents=True, exist_ok=True)
        gaps = _gap_doc(str(rep))
        _write_corpus(str(rep), rates, ticks_per_cell)
        return _run(str(tmp_path), gaps), str(rep)
    return build


def _uniform(rate):
    return {(b, c): rate for b in ("OPEN", "DECAY", "CLEAN") for c in CLASS_CYCLE}


def test_world_a_horizon_only(world):
    """Uniform rate everywhere. H1 supported; H2 and H3 must NOT be claimed."""
    out, _ = world(_uniform(0.10))
    assert "H1 HORIZON     SUPPORTED" in out, out
    assert "H2 DRIVE       NOT SUPPORTED" in out, out
    assert "H3 GAP         NOT SUPPORTED" in out, out


def test_world_b_drive_without_gap(world):
    """Morning lift in every gap class equally — a drive needs no gap. H1 and H2
    fire; H3 must not, because gap class does not move the morning rate."""
    rates = _uniform(0.10)
    for c in CLASS_CYCLE:
        rates[("OPEN", c)] = 0.35
    out, _ = world(rates)
    assert "H1 HORIZON     SUPPORTED" in out, out
    assert "H2 DRIVE       SUPPORTED" in out, out
    assert "H3 GAP         NOT SUPPORTED" in out, out


def test_world_c_all_three_including_the_deficit(world):
    """The real target. Continuation gaps inflated, reversal gaps pushed BELOW the
    midday baseline. All three must be reported — 'both' is the expected answer,
    not a muddle the tool should collapse into one winner."""
    rates = _uniform(0.10)
    rates[("OPEN", "FLAT")] = 0.35
    rates[("OPEN", "CONT")] = 0.60
    rates[("OPEN", "REV")] = 0.01      # the deficit
    out, _ = world(rates)
    assert "H1 HORIZON     SUPPORTED" in out, out
    assert "H2 DRIVE       SUPPORTED" in out, out
    assert "H3 GAP         CONFIRMED" in out, out


def test_deficit_alone_is_not_read_as_confirmation(world):
    """Reversal deficit WITHOUT continuation inflation is anomalous, not proof.
    Guards against the tool declaring H3 on half its evidence."""
    rates = _uniform(0.10)
    rates[("OPEN", "REV")] = 0.01
    out, _ = world(rates)
    assert "H3 GAP         ANOMALOUS" in out, out
    assert "H3 GAP         CONFIRMED" not in out, out


def test_thin_cells_are_refused_not_guessed(world):
    """a2_characterise v1.0's failure mode, asserted against. Below the floor the
    tool must say REFUSED and reach no conclusion."""
    out, _ = world(_uniform(0.10), ticks_per_cell=1)
    assert "H1 HORIZON     REFUSED" in out, out
    assert "H2 DRIVE       REFUSED" in out, out
    assert "H3 GAP         REFUSED" in out, out
    assert "SUPPORTED" not in out and "CONFIRMED" not in out, out
