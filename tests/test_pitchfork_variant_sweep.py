"""
tests/test_pitchfork_variant_sweep.py — v1.1 — 2026-08-04

v1.1 — 2026-08-04 — +2 tests for ACCEL per held bar (audit v1.5). The per-birth
rate the first real run printed was confounded by lifetime and made the most
FRAGILE variant look like the best-contained one.

Covers `pitchfork_filter_audit --variant-sweep` (§12 open question 2).

The load-bearing test is the second: the three variants must produce DIFFERENT
geometry on the same tape. Modified Schiff shifts the handle origin in time AND
price, Schiff in price only, Andrews not at all — so if the sweep printed three
identical rows it would mean `variant` was being swallowed somewhere between the
CLI and `build_fork`, and the whole comparison would be three runs of one
variant wearing three labels. That failure prints a clean-looking table.

Deliberate-failure check performed when written: hardcoding `variant=DEFAULT`
inside `_variant_sweep`'s replay call turns
test_the_three_variants_are_actually_different red; it leaves every other test
in this file green.
"""

import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(REPO, "tests", "pitchfork_filter_audit.py")


def _seg(a, b, n):
    """Linear leg, same helper shape tests/test_pitchfork_construct.py uses to
    build tapes that actually qualify — borrowed rather than reinvented, so the
    fixture births forks for the same reasons the construct tests do."""
    return [a + (b - a) * (i + 1) / n for i in range(n)]


def _tape(tmp, sym="AAA"):
    """Dated day-folders of 1-MINUTE bars, which the audit resamples to hourly —
    the real layout (`ohlc/<date>/<SYM>_ohlc_<date>.csv`), not a convenient one.
    Getting this wrong is why the first run of this fixture reported zero births
    on every variant and looked like a variant bug.

    Structure: repeated bullish cycles (low -> high -> higher low), so alternating
    pivots qualify and P2 sits above P0.
    """
    closes = [100.0]
    base = 100.0
    # Leg lengths are in MINUTES and are deliberately long: the audit resamples
    # to HOURLY, and §4.3's separation filter rejects pivots that land too close
    # together. The first draft used ~4-hour legs and every fork was rejected
    # SEPARATION — zero births on all three variants, which reads exactly like a
    # variant bug. ~10-15 hourly bars per leg clears it.
    for _ in range(3):
        closes += _seg(base, base - 14, 600)
        closes += _seg(base - 14, base + 20, 900)
        closes += _seg(base + 20, base - 4, 700)
        closes += _seg(base - 4, base + 10, 600)
        base = closes[-1]

    per_day = 390
    for start in range(0, len(closes), per_day):
        chunk = closes[start:start + per_day]
        if len(chunk) < 60:
            break
        day = f"2026-05-{1 + start // per_day:02d}"
        d = os.path.join(tmp, day)
        os.makedirs(d, exist_ok=True)
        rows = ["timestamp,open,high,low,close"]
        for i, c in enumerate(chunk):
            hh, mm = 9 + (30 + i) // 60, (30 + i) % 60
            rows.append(f"{day}T{hh:02d}:{mm:02d}:00,"
                        f"{c:.3f},{c + 0.4:.3f},{c - 0.4:.3f},{c:.3f}")
        with open(os.path.join(d, f"{sym}_ohlc_{day}.csv"), "w") as fh:
            fh.write("\n".join(rows) + "\n")
    return tmp


def _run(tmp, *extra):
    p = subprocess.run([sys.executable, TOOL, "--tape-root", tmp,
                        "--symbols", "AAA"] + list(extra),
                       capture_output=True, text=True, cwd=REPO)
    return p.stdout + p.stderr


def test_the_sweep_runs_and_names_all_three_variants():
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_tape(tmp), "--variant-sweep")
        assert "VARIANT SWEEP" in out, out[:1200]
        for v in ("andrews", "schiff", "modified_schiff"):
            assert v in out, (v, out[:1200])


def test_the_three_variants_are_actually_different():
    """THE ONE THAT MATTERS. If `variant` were swallowed between the CLI and
    build_fork the table would still print — three identical rows wearing three
    labels, and every other assertion here would pass."""
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_tape(tmp), "--variant-sweep")
        body = out.split("VARIANT SWEEP")[1].split("CAUSE OF DEATH")[0]
        rows = [l for l in body.splitlines()
                if any(l.strip().startswith(v) for v in
                       ("andrews", "schiff", "modified_schiff"))]
        assert len(rows) == 3, rows
        # strip the leading label; compare the numbers only
        numbers = {" ".join(l.split()[1:]) for l in rows}
        assert len(numbers) > 1, \
            "all three variants produced identical geometry — variant is being " \
            "swallowed before build_fork"


def test_acceleration_is_reported_per_birth_not_raw():
    """A variant that simply builds more forks would otherwise look worse for
    being more productive."""
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_tape(tmp), "--variant-sweep")
        assert "ACCEL/birth" in out, out[:1200]


def test_accel_is_reported_per_held_bar_too():
    """v1.5. Per-birth is confounded by lifetime: the first real 29-symbol run
    printed andrews 0.22 vs modified_schiff 0.67, a 3x gap — but andrews also
    had the shortest median life, so it simply had less time to be exceeded.
    Per held bar the same run is ~0.073 vs ~0.112."""
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_tape(tmp), "--variant-sweep")
        assert "ACCEL/held bar" in out, out[:1200]
        assert "READ ACCEL/HELD BAR FIRST" in out


def test_held_bar_denominator_is_not_the_birth_count():
    """If the two columns were identical the new one would be decoration."""
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_tape(tmp), "--variant-sweep")
        body = out.split("VARIANT SWEEP")[1].split("CAUSE OF DEATH")[0]
        rows = [l.split() for l in body.splitlines()
                if any(l.strip().startswith(v) for v in
                       ("andrews", "schiff", "modified_schiff"))]
        # columns: variant births cov accel/birth accel/held touch/birth life
        pairs = [(r[3], r[4]) for r in rows if len(r) >= 5]
        assert pairs, body
        assert any(a != b for a, b in pairs), \
            "per-birth and per-held-bar are identical — the denominator is wrong"


def test_coverage_is_median_not_mean():
    """AW measured mean 10.1% against median 5.3%, with half the symbols under
    5% — the mean describes a fleet nobody has."""
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_tape(tmp), "--variant-sweep")
        assert "med cov" in out
        assert "COVERAGE is median, not mean" in out


def test_the_sweep_states_that_it_decides_no_default():
    """§10 names the ten-parameter surface as the headline overfitting risk.
    A table that invited picking the prettiest coverage would be exactly that."""
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_tape(tmp), "--variant-sweep")
        assert "DECIDES NO DEFAULT" in out, out[-1200:]


def test_the_sweep_is_off_by_default():
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_tape(tmp))
        assert "VARIANT SWEEP" not in out
