#!/usr/bin/env python3
"""
tests/test_stack_separation.py — two stacks, one slot, named refusals. v1.0
v1.0 — 2026-08-19 — INITIAL (main v6.25 / config v4.22).

WHAT THIS EXISTS TO PREVENT, stated as the event rather than the rule:
on 2026-08-19 the SMC core labelled a runaway breakout RANGING at conviction
1.00 for an entire morning while the v1.3 classifier read BREAKOUT_VOLATILE
0.75 on the same ticks. CNT.6 then refused the ORB-runaway handoff — correctly,
on its own terms, because a continuation needs a trend to continue — and a
nine-point directional move went untraded by anything. One wrong premise,
every gate downstream reasoning perfectly to silence.

Four properties:

  A. THE LABEL IS NOT OVERRIDDEN by default. The legacy stack must read the
     same labels the parent fleet reads, or the A/B is not an A/B. Checked as
     SCOPE (the assignment is nested under the flag) plus the default value —
     the flag existing is not the same as the flag being consulted.
  B. OWNERSHIP IS BY PREFIX and read from LIVE records. A restart rehydrates
     positions from the DB and any in-process memory of who opened them is
     gone; ownership that depends on remembering is ownership that breaks on
     the shape this repo keeps breaking on.
  C. MUTUAL EXCLUSION IS NAMED IN BOTH DIRECTIONS. Not "a position is open" —
     `blocked_by_legacy_trade_active` and `blocked_by_smc_trade_active`, so
     "what did the other stack cost this one?" is a query rather than a guess.
     A silent stand-down is indistinguishable from "no setup occurred".
  D. THE LEGACY BLOCK IS EVALUATED BEFORE THE LADDER. Placed after, a legacy
     branch would consume the slot first and the block would be dead code that
     still reads correctly — the same ordering trap as the RANGING block.

Run:  cd <repo> && PYTHONPATH=. python3 tests/test_stack_separation.py
Deliberate-failure proof: OT_STACK_SELFTEST=1 asserts the OLD coupled
behaviour; case A must go red.
"""

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FAILS = []


def check(name, ok, detail=""):
    if not ok:
        FAILS.append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail else ''}")


def main():
    src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    import config

    # ── A. the label is not overridden by default ─────────────────────────
    want_off = os.environ.get("OT_STACK_SELFTEST", "0") != "1"
    check("A1 SMC_OVERRIDE_LABEL defaults OFF",
          (config.SMC_OVERRIDE_LABEL is False) is want_off,
          str(config.SMC_OVERRIDE_LABEL))

    guarded = False
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and "SMC_OVERRIDE_LABEL" in ast.dump(node.test):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assign):
                    for t in sub.targets:
                        if isinstance(t, ast.Attribute) and t.attr == "primary_regime":
                            guarded = True
    check("A2 the primary_regime assignment is NESTED under the flag",
          guarded, "the flag existing is not the flag being consulted")
    check("A3 conviction is not overridden outside the flag either",
          src.count("regime.conviction     = smc_st.confidence") == 1 and guarded)

    # ── B. ownership ──────────────────────────────────────────────────────
    import importlib.util
    spec = importlib.util.spec_from_file_location("_m", os.path.join(ROOT, "main.py"))
    # main.py imports the broker SDK; parse the helpers out instead of importing.
    ns = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in ("_stack_of",):
            exec(compile(ast.Module([node], []), "<ast>", "exec"), ns)
    stack_of = ns.get("_stack_of")
    check("B1 _stack_of exists", stack_of is not None)
    if stack_of:
        for name in ("ICTSweepMSS", "ICTSilverBullet", "ICTBreakerUnicorn"):
            check(f"B2 {name} → smc", stack_of(name) == "smc")
        for name in ("ORBStrategy", "ContinuationStrategy", "IronCondorStrategy",
                     "ButterflyStrategy", "SweepReversal", "TrendCreditSpread"):
            check(f"B3 {name} → legacy", stack_of(name) == "legacy")
        check("B4 an unknown future strategy defaults to legacy, not crash",
              stack_of("SomethingNew") == "legacy")
        check("B5 None/empty is handled", stack_of(None) == "legacy")

    check("B6 ownership is read from LIVE records, not remembered",
          "get_open_records()" in src,
          "a restart rehydrates from the DB")

    # ── C. named refusals, both directions ────────────────────────────────
    check("C1 the SMC stand-down is named",
          "blocked_by_legacy_trade_active" in src)
    check("C2 the LEGACY stand-down is named",
          "blocked_by_smc_trade_active" in src)
    check("C3 the refused ICT signal is journaled, not just counted",
          "signal=_sigj.signal_ctx(ict_sig)" in src)

    # ── D. ordering ───────────────────────────────────────────────────────
    lines = src.splitlines()
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "attempt_new_entry")

    def find(pred):
        for i in range(fn.lineno - 1, fn.end_lineno):
            if pred(lines[i]):
                return i + 1
        return None

    legacy_block = find(lambda l: "blocked_by_smc_trade_active" in l)
    orb_p1 = find(lambda l: "Priority 1: ORB" in l)
    check("D1 the legacy stand-down precedes the ladder's Priority 1",
          legacy_block and orb_p1 and legacy_block < orb_p1,
          f"block@{legacy_block} orb@{orb_p1}")

    print()
    if FAILS:
        print(f"stack_separation: {len(FAILS)} FAILED — " + "; ".join(FAILS))
        return 1
    print("stack_separation: ALL PASS (A no override · B prefix ownership from "
          "live records · C both refusals named · D block precedes the ladder)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
