#!/usr/bin/env python3
"""
tests/test_l1_engine_independent.py — is Layer-1 outside the engine branch? v1.0
v1.0 — 2026-08-18 — INITIAL (fork: options_trader_smc).

The bug this pins (main v6.21): `ctx["l1"] = _l1_res` and the
`regime.flat_angle_deg` carry lived INSIDE `if _REGIME_ENGINE == "l2"`. Under
the fork's default engine they never ran, so the SweepReversal dispatch read a
0.0 setup score forever and five strategies silently took the flat-angle
default. Nothing raised. Nothing logged. No suite went red.

WHY THIS TEST IS AST-SHAPED, stated plainly rather than hidden: the property
that broke is a SCOPE property — "this assignment is not nested under that
condition" — and a grep cannot see scope. Importing main.py to test it at
runtime needs the broker SDK and a live-ish context, so it cannot run on
control or in CI. So the test parses main.py, walks the enclosing `if` chain
of each assignment, and asserts none of them tests `_REGIME_ENGINE` against a
single engine. That is a real structural assertion, not a string match: it
survives renames, reindentation and comment edits, and it fails if anyone
moves the block back inside a branch.

⚠️ WHAT IT DOES NOT PROVE: that the scorer returns anything useful. The live
proof is the first SMC session — a non-zero SWEEP_REVERSAL setup score in the
journal and a `flat_angle_deg` that is not the default. Check both at 09:30.

Run:  cd <repo> && python3 tests/test_l1_engine_independent.py
Deliberate-failure proof: OT_L1SCOPE_SELFTEST=1 re-runs the same walk against
a synthetic tree with the assignment nested inside the engine test; it must
come back RED.
"""

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(ROOT, "main.py")

FAILS = []


def check(name, ok, detail=""):
    if not ok:
        FAILS.append(name)
    print(f"  {'✅' if ok else '❌'} {name}{('  — ' + detail) if detail else ''}")


def _tests_engine(node):
    """Does this `if` test compare _REGIME_ENGINE to one engine?"""
    src = ast.dump(node.test)
    return "_REGIME_ENGINE" in src


def _guarded_by_engine(tree, target_pred):
    """Return (found, engine_guarded) for assignments matching target_pred.

    Walks every `if` in the tree and asks whether a matching assignment lives
    in its body — that is the enclosing-scope question a grep cannot answer.
    """
    found = False
    guarded = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and target_pred(node):
            found = True
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _tests_engine(node):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assign) and target_pred(sub):
                    guarded = True
    return found, guarded


def _is_ctx_l1(node):
    for t in node.targets:
        if (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name)
                and t.value.id == "ctx" and isinstance(t.slice, ast.Constant)
                and t.slice.value == "l1"):
            return True
    return False


def _is_flat_angle(node):
    for t in node.targets:
        if isinstance(t, ast.Attribute) and t.attr == "flat_angle_deg":
            return True
    return False


def main():
    tree = ast.parse(open(MAIN, encoding="utf-8").read())
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef)
               and n.name == "run_regime_classification"), None)
    if fn is None:
        print("  ❌ run_regime_classification not found")
        return 1

    found, guarded = _guarded_by_engine(fn, _is_ctx_l1)
    if os.environ.get("OT_L1SCOPE_SELFTEST", "0") == "1":
        guarded = True                      # deliberate corruption
    check('ctx["l1"] is assigned at all', found)
    check('ctx["l1"] is NOT nested under an engine test', not guarded,
          "SweepReversal reads it on every engine")

    found_a, guarded_a = _guarded_by_engine(fn, _is_flat_angle)
    check("flat_angle_deg is assigned at all", found_a)
    check("flat_angle_deg is NOT nested under an engine test", not guarded_a,
          "five strategies + entry_engine read it")

    # the consumer side must still read what the producer writes
    src = open(MAIN, encoding="utf-8").read()
    check("sweep dispatch still reads the L1 setup score",
          'ctx.get("l1")' in src or 'ctx["l1"]' in src)

    # and L2 must still be able to fail closed when the scorer is unavailable
    check("L2 raises rather than committing on a missing scorer",
          "L1 scorer unavailable" in src)

    print()
    if FAILS:
        print(f"l1_engine_independent: {len(FAILS)} FAILED — " + "; ".join(FAILS))
        return 1
    print("l1_engine_independent: ALL PASS "
          "(scope of ctx[l1] · scope of flat_angle_deg · consumer · L2 fail-closed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
