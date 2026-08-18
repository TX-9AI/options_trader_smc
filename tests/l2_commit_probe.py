"""
l2_commit_probe.py — does L2.5 actually COMMIT a label, or only import?

The 2026-07-29 fix (main v4.5) proved the IMPORT works: `L2 OK 25` on 29/29.
That is necessary and NOT sufficient. main.py only lets L2 override the v1.3
label when ALL of these hold:

    _L2_OK                                  <- import  (v4.5 fixed this)
    the integrator step does not raise      <- logs "L2.5 integrator step failed"
    st.regime is truthy AND NOT st.stale    <- LOGS NOTHING AT ALL

That third condition is the silent one, and `stale` only clears here:

    if all(evidence.get(r) is not None for r in INTEGRATED_REGIMES):
        self.stale = False

So a SINGLE None in the evidence vector, on every tick, keeps the book stale
forever and L2 never commits — while every REGIME line prints [v13] and nothing
warns. Since regime_confluence returns None for whole dimensions when `closes`
or `atr` are missing, and main.py passes closes=None unless df_1m has >=
RANGE_WINDOW_BARS rows, that is a live possibility rather than a theoretical one.

This probe drives the REAL classes over simulated ticks and reports which of the
three gates is open or shut. Read-only; touches no database, no network, no
fleet. Run on control or on a box.

    python3 l2_commit_probe.py
"""

import math
import os
import sys
from types import SimpleNamespace as NS

for _p in (os.path.expanduser("~/options-trader"),
           os.path.expanduser("~/options-trader-v3"),
           os.getcwd()):
    if os.path.isdir(os.path.join(_p, "analysis")):
        sys.path.insert(0, _p)
        REPO = _p
        break
else:
    print("cannot find an options_trader checkout (looked for ./analysis)")
    sys.exit(2)

from analysis.regime_confluence import (  # noqa: E402
    RegimeConfluenceScorer, RANGE_WINDOW_BARS,
)
from analysis.conviction_integrator import (  # noqa: E402
    ConvictionIntegrator, INTEGRATED_REGIMES,
)

print(f"repo: {REPO}")
print(f"RANGE_WINDOW_BARS = {RANGE_WINDOW_BARS}")
print(f"INTEGRATED_REGIMES ({len(INTEGRATED_REGIMES)}): {', '.join(INTEGRATED_REGIMES)}\n")


def mk_closes(n=30, base=100.0):
    """Trending tape — the easiest case for the classifier to label."""
    import random
    random.seed(3)
    return [base + 0.5 * i + random.gauss(0, 0.1) for i in range(n)]


def derive_atr(closes):
    d = [abs(closes[i] - closes[i - 1]) for i in range(1, len(closes))]
    return sum(d) / max(len(d), 1)


# Fixtures lifted from regime_confluence's own smoke test: a clean
# TRENDING_BULL state, i.e. the most favourable possible input.
VOL = NS(atr_current=0.6, atr_avg_20=0.4, is_expanding=True,
         price_vs_bb="ABOVE_UPPER", bb_width_pct=0.6,
         atr_state="EXPANDING", bb_state="EXPANDING")
TREND = NS(primary_adx=40, aligned_timeframes=4, total_timeframes=4,
           overall_direction="BULLISH", is_bullish=True,
           votes={"5m": NS(momentum="ACCELERATING")})
STRUCT = NS(structure_sequence="HH_HL")
LIQ = NS(pools=[], recent_sweep=None, sweep_age_bars=999)

scorer = RegimeConfluenceScorer()
closes = mk_closes(40)
atr = derive_atr(closes[-RANGE_WINDOW_BARS:])


def probe(label, closes_arg, atr_arg, ticks=12, dt=15.0):
    """Drive evidence -> integrator over `ticks` at `dt` seconds, as main.py does."""
    integ = ConvictionIntegrator()
    full_seen = committed = 0
    first_commit = None
    last = None

    for i in range(ticks):
        ev = scorer.evidence(VOL, TREND, STRUCT, LIQ,
                             closes=closes_arg, atr=atr_arg)
        nones = [r for r in INTEGRATED_REGIMES if ev.get(r) is None]
        if not nones:
            full_seen += 1
        st = integ.update(1000.0 + i * dt, ev)
        last = (st, ev, nones)
        # main.py's exact commit condition
        if st.regime and not st.stale:
            committed += 1
            if first_commit is None:
                first_commit = i

    st, ev, nones = last
    print(f"--- {label}")
    print(f"    evidence dims None      : {len(nones)}/{len(INTEGRATED_REGIMES)}"
          + (f"  -> {', '.join(nones)}" if nones else ""))
    print(f"    full vectors seen       : {full_seen}/{ticks}")
    print(f"    final stale             : {st.stale}")
    print(f"    final regime            : {st.regime!r}  conviction={st.conviction:.3f}")
    print(f"    COMMITTED (main.py rule): {committed}/{ticks}"
          + (f"  first at tick {first_commit}" if first_commit is not None else ""))
    verdict = "L2 COMMITS" if committed else "L2 NEVER COMMITS -> every REGIME line prints [v13]"
    print(f"    VERDICT: {verdict}\n")
    return committed > 0


print("=" * 68)
print("  CASE 1 — closes + atr SUPPLIED (main.py's happy path:")
print("           df_1m present with >= RANGE_WINDOW_BARS rows)")
print("=" * 68)
ok_full = probe("with closes+atr", closes, atr)

print("=" * 68)
print("  CASE 2 — closes=None, atr=None (main.py passes these whenever df_1m")
print("           is short or missing — e.g. the first minutes after a restart)")
print("=" * 68)
ok_none = probe("without closes/atr", None, None)

print("=" * 68)
print("  CASE 3 — restart gap: dt > dt_max (90s) between ticks")
print("=" * 68)
ok_gap = probe("120s tick gap", closes, atr, ticks=8, dt=120.0)

print("=" * 68)
print("  SUMMARY")
print("=" * 68)
print(f"  full evidence  : {'COMMITS' if ok_full else 'NEVER COMMITS'}")
print(f"  no closes/atr  : {'COMMITS' if ok_none else 'NEVER COMMITS'}")
print(f"  restart gap    : {'COMMITS' if ok_gap else 'NEVER COMMITS'}")
print()
if ok_full:
    print("  L2.5 is capable of committing. If production still logs [v13],")
    print("  the cause is the INPUTS (closes/atr absent, or evidence dims None),")
    print("  not the import and not the integrator.")
else:
    print("  L2.5 CANNOT commit even on ideal input — the defect is deeper than")
    print("  the import fix, and main v4.5 did not restore L2.5 in practice.")
sys.exit(0 if ok_full else 1)
