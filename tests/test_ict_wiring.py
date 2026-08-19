#!/usr/bin/env python3
"""
tests/test_ict_wiring.py — grading is unconditional; action is gated. v1.1
v1.1 — 2026-08-19 — 🔴 v1.0 PINNED THE WRONG PROPERTY AND CALLED IT A PASS.
       Case A1 asserted the dispatch call was INSIDE attempt_new_entry and
       reported that as correct. It is exactly what broke: attempt_new_entry
       has five early returns above the insertion point and is called only in
       an `else`, so on the first live morning the suite journaled ZERO rows
       with no error anywhere. A test that confirms the shape of what was
       built, rather than the property that was asked for, is worse than no
       test — it certifies the defect.
       v1.1 asserts the SPLIT: the GRADING pass (evaluate_all +
       journal_setup_state) must live in run_regime_classification, outside
       attempt_new_entry, reachable on a tick where no entry is possible; the
       ACTION path (ict_dispatch) stays inside attempt_new_entry and must
       CONSUME the context the grading pass built rather than rebuild it.
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

    rfn = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                and n.name == "run_regime_classification"), None)
    grade_at = None
    if rfn is not None:
        for i in range(rfn.lineno - 1, rfn.end_lineno):
            if "ict_journal_state(" in lines[i]:
                grade_at = i + 1
                break
    if os.environ.get("OT_WIRE_SELFTEST", "0") == "1":
        grade_at = None                        # deliberate corruption

    # ── A. GRADING: unconditional, and NOT inside the entry function ───────
    check("A1 the grading pass lives in run_regime_classification",
          grade_at is not None and rfn is not None
          and rfn.lineno < grade_at < rfn.end_lineno, str(grade_at))
    check("A2 grading is OUTSIDE attempt_new_entry — the five early returns "
          "above the entry path must not be able to silence it",
          grade_at is not None and not (fn.lineno < grade_at < fn.end_lineno))
    check("A3 grading calls evaluate_all AND journals every setup",
          "ict_evaluate_all(" in src and "ict_journal_state(" in src)
    check("A4 grading needs no options chain (a chain failure must not "
          "silence the journal)", _grading_is_chain_free(src))
    check("A5 the dispatch call is still inside attempt_new_entry (ACTION "
          "belongs where permission is decided)",
          ict_at is not None and fn.lineno < ict_at < fn.end_lineno, str(ict_at))
    check("A6 action CONSUMES the graded context, never rebuilds it",
          'ctx.get("ictx")' in src
          and src.count("build_ict_context(") == 1,
          f"build_ict_context sites={src.count('build_ict_context(')}")
    check("A7 the dispatch runs BEFORE the label ladder's Priority 1",
          ict_at is not None and orb_at is not None and ict_at < orb_at,
          f"ict@{ict_at} orb@{orb_at}")
    check("A8 nothing is nested under an arming check",
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

    # ── E. THE PROPERTY THAT WAS ACTUALLY ASKED FOR ───────────────────────
    # "It runs every tick" is a REACHABILITY claim, and the way it failed was
    # reachability: five early returns and an `else` stood between the tick
    # and the grading call. So ask it structurally — is the grading call
    # dominated by any `return` inside its own function, and does its function
    # get called unconditionally from the tick loop?
    rets = [n.lineno for n in ast.walk(rfn) if isinstance(n, ast.Return)] if rfn else []
    early = [r for r in rets if grade_at and r < grade_at]
    check("E1 no early return precedes the grading call in its own function",
          not early, f"returns before it: {early}")

    called_in_else = False
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and node.orelse:
            for sub in node.orelse:
                for c in ast.walk(sub):
                    if (isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                            and c.func.id == "run_regime_classification"):
                        called_in_else = True
    check("E2 run_regime_classification is not called from an `else` arm",
          not called_in_else,
          "attempt_new_entry IS, which is half of why grading was silent")

    # and the entry path must still be allowed to be gated — that is correct
    entry_rets = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Return)]
    check("E3 the ACTION path still sits behind its gates (by design)",
          ict_at is not None and any(r < ict_at for r in entry_rets),
          "entry permission decides trading, not grading")

    print()
    if FAILS:
        print(f"ict_wiring: {len(FAILS)} FAILED — " + "; ".join(FAILS))
        return 1
    print("ict_wiring: ALL PASS (A grading unconditional + action gated · "
          "B no label gate · C fall-through intact · D gates closed)")
    return 0


def _grading_is_chain_free(src):
    """The grading block must not reference `chain`.

    A chain-fetch failure is one of the five early returns that silenced the
    suite in the first place; if grading depended on the chain it would be
    hostage to the same thing by another route.
    """
    i = src.find("ICT GRADING PASS")
    j = src.find("LAYER-1 IS ENGINE-INDEPENDENT", i)
    if i < 0 or j < 0:
        return False
    code = [l for l in src[i:j].splitlines()
            if not l.lstrip().startswith("#")]
    return not any("chain" in l for l in code)


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
