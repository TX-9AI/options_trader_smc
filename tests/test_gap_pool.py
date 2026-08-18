"""
tests/test_gap_pool.py — v1.0 — 2026-08-04 (gap_outcome_join v1.5)

Plants worlds with a KNOWN answer and asserts the tool recovers each — the same
discipline tests/test_a2_partition_recovers.py uses.

The one that matters is the third: a row where CONT and REV point in OPPOSITE
directions must come back NOT POOLABLE. Pooling those two arms averages a real
positive against a real negative and reports a null, which is the single way a
LARGER sample is worse than a smaller one — and in the pooled table it is
completely invisible. A pooling flag without this check would have made the
Aug 13 read arrive sooner and wronger.

Deliberate-failure check performed when written, and it earned its keep twice:
forcing `verdict = "poolable"` turns test_opposite_arms_are_refused red, and
`pooling = False` turns five of seven red. The FIRST attempt at both assertions
matched the section's own explanatory prose rather than the verdict rows, so a
broken tool still passed — the asserts are now anchored on `-> NOT POOLABLE`
and `UNDERPOWERED — CONT n=`. Widening `band` from quadrature to `hc + hr` does
NOT turn anything red at the planted 1.20 separation, which is worth stating
rather than claiming a check that does not exist.
"""

import json
import os
import subprocess
import sys
import tempfile

TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "gap_outcome_join.py")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _world(tmp, cont_r, rev_r, flat_r, n_per_cell=40, strategy="ORBStrategy"):
    """Write a gap lookup and fleet_trades files with planted per-class R.

    One symbol per gap class keeps the join trivial; the tool's join logic is
    already covered elsewhere and is not what these tests are about.
    """
    reports = os.path.join(tmp, "reports")
    os.makedirs(reports, exist_ok=True)
    sym_class = {"AAA": "CONT", "BBB": "REV", "CCC": "FLAT"}
    r_by_class = {"CONT": cont_r, "REV": rev_r, "FLAT": flat_r}

    sessions, trades_by_date = {}, {}
    for i in range(n_per_cell):
        date = f"2026-08-{(i % 20) + 5:02d}"
        sessions.setdefault(date, {})
        trades_by_date.setdefault(date, [])
        for sym, cls in sym_class.items():
            sessions[date][sym] = {"gap_class": cls, "gap_pct": 0.5}
            # alternate a fixed spread around the planted mean so sd > 0 and
            # the CI is real rather than degenerate
            bump = 0.25 if i % 2 else -0.25
            r = r_by_class[cls] + bump
            trades_by_date[date].append({
                "status": "closed", "symbol": sym, "strategy": strategy,
                "pnl_usd": r * 1000.0, "max_loss": 1000.0,
                "entry_time": f"{date}T14:00:00+00:00",
            })

    with open(os.path.join(reports, "gap_pct.json"), "w") as fh:
        json.dump({"sessions": sessions}, fh)
    for date, trades in trades_by_date.items():
        with open(os.path.join(reports, f"fleet_trades_{date}.json"), "w") as fh:
            json.dump({"trades": trades}, fh)
    return reports


def _run(reports, *extra):
    """Run the real CLI. TRADES_GLOB is a module constant with no flag, so it is
    overridden through the environment-free route: a tiny driver that patches it
    before calling main(). Testing the installed entry point rather than an
    importable copy is the point."""
    driver = (
        "import sys; sys.path.insert(0, %r);"
        "import tests.gap_outcome_join as g;"
        "g.TRADES_GLOB = %r;"
        "sys.exit(g.main(['gap_outcome_join', '--gaps', %r, '--since',"
        " '2026-07-23'] + %r))"
        % (REPO, os.path.join(reports, "fleet_trades_*.json"),
           os.path.join(reports, "gap_pct.json"), list(extra))
    )
    p = subprocess.run([sys.executable, "-c", driver],
                       capture_output=True, text=True, cwd=REPO)
    return p.stdout + p.stderr


def test_unpooled_shows_three_classes():
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_world(tmp, 0.20, 0.20, -0.20))
        assert "CONT" in out and "REV" in out and "FLAT" in out
        assert "GAP" not in out.split("READING IT")[0]


def test_pooling_merges_the_two_gap_arms_and_grows_n():
    """40 per class unpooled -> 80 in the GAP column. That doubling (a tripling
    on the real fleet's class mix) is the entire reason the flag exists."""
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_world(tmp, 0.20, 0.20, -0.20), "--pool", "gapflat")
        assert "GAP" in out
        assert "n=80" in out, out[:1200]


def test_homogeneous_arms_are_reported_poolable():
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_world(tmp, 0.20, 0.20, -0.20), "--pool", "gapflat")
        leg = out.split("POOL LEGITIMACY")[1]
        assert "-> poolable" in leg, leg[:600]
        assert "-> NOT POOLABLE" not in leg


def test_opposite_arms_are_refused():
    """THE ONE THAT MATTERS. CONT +0.60, REV -0.60 pools to ~0.00 — a null
    manufactured from two real, opposite effects. The pooled cell alone cannot
    show this; the verdict must."""
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_world(tmp, 0.60, -0.60, 0.0), "--pool", "gapflat")
        leg = out.split("POOL LEGITIMACY")[1]
        # Anchored on the VERDICT ARROW, not the bare phrase: the section's own
        # closing prose explains what NOT POOLABLE means, so a bare substring
        # test passes even when every verdict says the opposite. Found by the
        # deliberate-failure run — forcing verdict="poolable" left this test
        # green, which is the same assert-your-own-boilerplate trap that has
        # bitten the changelog-prose canaries.
        assert "-> NOT POOLABLE" in leg, leg[:600]


def test_a_refused_row_still_prints_its_pooled_cell():
    """Withholding the number silently would be its own failure — the row is
    flagged, not hidden."""
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_world(tmp, 0.60, -0.60, 0.0), "--pool", "gapflat")
        assert "n=80" in out.split("POOL LEGITIMACY")[0]


def test_thin_arms_report_underpowered_not_poolable():
    """Absence of evidence is not permission."""
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_world(tmp, 0.20, 0.20, -0.20, n_per_cell=10),
                   "--pool", "gapflat")
        leg = out.split("POOL LEGITIMACY")[1]
        assert "UNDERPOWERED — CONT n=" in leg, leg[:600]   # the row, not the prose


def test_pooling_is_off_by_default():
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(_world(tmp, 0.60, -0.60, 0.0))
        assert "POOL LEGITIMACY" not in out
