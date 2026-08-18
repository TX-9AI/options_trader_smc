#!/usr/bin/env python3
"""
tests/canary_smc_core.py — SMC wiring canary. v1.0
v1.0 — 2026-08-18 — INITIAL (fork: options_trader_smc).

Proves the SMC core is WIRED, in two layers:

1. SHAPE-OF-DEFINITION greps (WORKING_AGREEMENT §20 — never bare mentions,
   which changelogs legitimately contain): the engine selector admits smc,
   the override branch exists, the revocation gate exists at the entry
   choke point, run_analysis binds ctx before the Level.1/A2.6b writes.
2. A DECISION-LEVEL behavioral call (WA §21): entry_permitted() is CALLED
   on a revoked state and the returned decision asserted — not the source.

main.py itself cannot be imported off-box (TastyTrade SDK), so its checks
are shape-scoped; the engine's behavior is fully exercised in
tests/test_smc_core.py. Run:
    cd <repo> && PYTHONPATH=. python3 tests/canary_smc_core.py
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

fails = []
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check(name, ok):
    if not ok:
        fails.append(name)
    print(f"  {'✅' if ok else '❌'} {name}")


main_src = open(os.path.join(ROOT, "main.py")).read()

# selector shape: the assert tuple, not a mention of "smc"
check("selector admits smc (assert tuple)",
      re.search(r'assert _REGIME_ENGINE in \("l2", "v13", "smc"\)', main_src)
      is not None)

# override branch shape: the engine-gated conditional
check("smc override branch (engine-gated conditional)",
      'if _REGIME_ENGINE == "smc" and _smc_engine is not None:' in main_src)

# revocation gate shape: the call site of the decision function
check("revocation gate calls entry_permitted(",
      "_smc_engine.entry_permitted(" in main_src)

# ctx bound before the Level.1/A2.6b writes: the dict binding must appear
# BEFORE the first ctx["gap"] write inside run_analysis
m_bind = main_src.find('ctx = {\n        "price":     price,')
m_gap = main_src.find('ctx["gap"] = measure_gap')
check("run_analysis binds ctx before ctx[\"gap\"] write",
      0 < m_bind < m_gap)

# journal event emitted on setup transitions
check('setup transitions journal ("smc_setup" call site)',
      '_sigj.journal("smc_setup"' in main_src)

# fork default engine is smc (shape: the getenv default, not a mention)
check("fork default engine is smc (getenv default)",
      'os.environ.get("OT_REGIME_ENGINE", "SMC")' in main_src)

# ── behavioral: the decision function, called ────────────────────────────────
from smc.smc_engine import SMCEngine, SetupState  # noqa: E402

eng = SMCEngine()
eng._setup = SetupState(phase="REVOKED", thesis="bearish", basis="raid",
                        anchor=100.0, invalidation=100.0, since_bar=5)
check("entry_permitted(bearish) is False on a bearish-revoked setup",
      eng.entry_permitted("bearish") is False)
check("entry_permitted(bullish) is True on a bearish-revoked setup",
      eng.entry_permitted("bullish") is True)
eng._setup = SetupState()
check("entry_permitted defaults to True with no setup (permissive)",
      eng.entry_permitted("bullish") is True
      and eng.entry_permitted("bearish") is True)

if fails:
    print(f"\ncanary_smc_core: {len(fails)} FAILED")
    sys.exit(1)
print("\ncanary_smc_core: ALL PASS")
sys.exit(0)
