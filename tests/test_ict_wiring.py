#!/usr/bin/env python3
"""
tests/test_ict_wiring.py — is the ICT branch actually AHEAD of the ladder? v1.0
v1.0 — 2026-08-19 — INITIAL (G6/G8).

Four properties, every one of which fails SILENTLY if it breaks — the bot runs,
logs look normal, and the only symptom is that ICT never trades:

  A. THE BRANCH IS BEFORE THE LADDER. If it lands after Priority 1, ORB takes
     every tick it wants and the ICT ranking is decorative. This is a SCOPE and
     ORDER property inside one function, so it is checked by AST line position,
     not by grep.
  B. THE BRANCH CONSULTS NO REGIME LABEL. Operator 2026-08-18: a label may be
     used by a setup that earns something from it, never as a silent
     precondition. Checked as a GATE SHAPE (a comparison), because prose in
     this repo legitimately names `primary_regime` while explaining the rule —
     the SWP.1 trap, which has already been sprung twice on this codebase.
  C. THE LADDER STILL FALLS THROUGH. Every ladder branch must respect a signal
     already taken, or ORB will overwrite an ICT signal one line later.
  D. THE GATES DEFAULT CLOSED. config must register all seven names, the
     cutoff must be 11:30, and arming must be OFF out of the box. A registered
     name is what subjects a debit setup to the cutoff at all.

Run:  cd <repo> && PYTHONPATH=. python3 tests/test_ict_wiring.py
Deliberate-failure proof: OT_WIRE_SELFTEST=1 inverts A; the suite must go red.
"""

import ast
import os
import re
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
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "attempt_new_entry"), None)
    if fn is None:
        print("  FAIL  attempt_new_entry not found")
        return 1

    lines = src.splitlines()

    def line_of(pred, lo=fn.lineno, hi=fn.end_lineno):
        for i in range(lo - 1, min(hi, len(lines))):
            if pred(lines[i]):
                return i + 1
        return None

    ict_at = line_of(lambda l: "ict_dispatch(" in l and "=" in l)
    orb_at = line_of(lambda l: "Priority 1: ORB" in l)
    if os.environ.get("OT_WIRE_SELFTEST", "0") == "1":
        ict_at, orb_at = orb_at, ict_at        # deliberate corruption

    check("A1 the ICT dispatch call is inside attempt_new_entry",
          ict_at is not None and fn.lineno < ict_at < fn.end_lineno, str(ict_at))
    check("A2 it runs BEFORE the label ladder's Priority 1",
          ict_at is not None and orb_at is not None and ict_at < orb_at,
          f"ict@{ict_at} orb@{orb_at}")
    check("A3 the context is built from the core's ctx, not re-derived",
          "build_ict_context(" in src)
    check("A4 it runs every tick — not nested under an arming check",
          _not_gated_by_arming(fn), "arming lives in the suite, not in main")

    body = "\n".join(lines[fn.lineno - 1:fn.end_lineno])
    seg = body[:body.find("Priority 1: ORB")] if "Priority 1: ORB" in body else body
    check("B1 the ICT branch makes no regime-label comparison",
          not re.search(r"primary_regime\s*(==|!=|\bin\b)", seg),
          "gate shape, not the bare word")

    check("C1 ORB respects a signal already taken",
          "if signal is None and orb_confirmed" in src)
    check("C2 a None from ICT leaves the ladder reachable",
          "if ict_sig is not None:" in src)
    check("C3 the import is guarded and pages on failure",
          "_ICT_OK = False" in src and "ICT SUITE UNAVAILABLE" in src)
    check("C4 preemption of a confirmed ORB is journaled",
          "preempted:ict_ranked_first" in src)

    import config
    names = {n for n in config.DEBIT_DIRECTIONAL_STRATEGIES if n.startswith("ICT")}
    check("D1 all seven ICT names registered for the debit cutoff",
          len(names) == 7, str(sorted(names)))
    check("D2 the registered names match the suite's NAME constants",
          _suite_names() == names, str(sorted(_suite_names() ^ names)))
    check("D3 the debit cutoff is 11:30",
          tuple(config.DEBIT_DIRECTIONAL_CUTOFF_ET) == (11, 30),
          str(config.DEBIT_DIRECTIONAL_CUTOFF_ET))
    check("D4 the butterfly is NOT registered (exempt by absence)",
          not any("utterfly" in n for n in config.DEBIT_DIRECTIONAL_STRATEGIES))
    check("D5 arming defaults CLOSED", config.ICT_ARMED is False)
    check("D6 every per-setup validation gate defaults CLOSED",
          not any(config.ICT_VALIDATED.values()))

    print()
    if FAILS:
        print(f"ict_wiring: {len(FAILS)} FAILED — " + "; ".join(FAILS))
        return 1
    print("ict_wiring: ALL PASS (A pre-ladder position · B no label gate · "
          "C fall-through intact · D gates closed)")
    return 0


def _not_gated_by_arming(fn):
    """Is the ict_dispatch call free of any enclosing ARMED/VALIDATED test?

    A scope question, so it is answered from the tree. If dispatch were nested
    under an arming check the suite would never journal a FORMING state while
    disarmed — and that journal is the only data the priors are ever fitted
    from, which is the whole reason this branch runs on every tick.
    """
    for node in ast.walk(fn):
        if not isinstance(node, ast.If):
            continue
        test = ast.dump(node.test).upper()
        if "ARMED" not in test and "VALIDATED" not in test:
            continue
        for sub in ast.walk(node):
            if (isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Name)
                    and sub.func.id == "ict_dispatch"):
                return False
    return True


def _suite_names():
    out = set()
    d = os.path.join(ROOT, "strategy", "ict")
    for f in sorted(os.listdir(d)):
        if not f.endswith(".py"):
            continue
        for line in open(os.path.join(d, f), encoding="utf-8"):
            m = re.match(r'\s*NAME\s*=\s*"([^"]+)"', line)
            if m:
                out.add(m.group(1))
    return out


if __name__ == "__main__":
    sys.exit(main())
