#!/usr/bin/env python3
"""
tests/swallow_audit.py — v1.1 — 2026-08-04   (backlog item W.2)

v1.1 — 2026-08-04 — `--since <snapshot.json>` NAMES the new silent handlers
        instead of only counting them. The 2026-08-03 conductor warned "silent
        handlers ROSE 83 -> 87 — a new swallow was added" and then required a
        manual census to find out WHICH, every time it fires. An alarm that
        cannot point at what it detected gets read more slowly each time, which
        is the failure mode WORKING_AGREEMENT §17 is about. Identity is
        (file, func, guards) — NOT the line number, which shifts on any edit
        above it and would report the whole file as new.

WHY THIS EXISTS
    The week of 2026-07-27 produced seven defects that shared one shape: code
    that FAILED without saying so, and kept going with a plausible-looking
    result. None of them crashed. None broke a test. Every one was found by
    accident, days or weeks late.

        1. the L2 import guard swallowed an ImportError    -> 3 sessions on v1.3
        2. harvest discarded scp return values             -> 3 nights of chains lost
        3. the conductor checked only OHLC completeness    -> logged ✅ on empty classes
        4. selector's EXACTLY-N backfill hid a dead model  -> weeks of unranked picks
        5. `_REGIME_ENGINE == "L2"` vs a .lower()ed value  -> L2.5 NEVER ran, ever
        6. $DTP_REPORT_JSON unset -> emit wrote to cwd     -> 23-day frozen report
        7. _push_brief_flags had no mock guard             -> real SSH from a mock run

    Every check we had asked "does this code WORK?". None asked "does it RUN, and
    does it SAY SO when it doesn't?". This tool asks the second question.

WHAT IT REPORTS
    Every `except Exception` / bare `except` that does NOT re-raise, classified by
    how loud it is:
        pages       — calls notify/alert. Loudest. Rare, and usually correct.
        logs only   — leaves a trace someone could find later.
        SILENT      — no log, no alert. The failure is unobservable.

    Silence is NOT automatically a bug. A guarded optional import, a date parser
    returning None, a journal emit that must never kill a trade — all correctly
    silent. What matters is WHERE. The tool tiers by module, because a swallow in
    the risk breaker is a different animal from one in a status printout.

USAGE
    python3 tests/swallow_audit.py                 # tiered summary
    python3 tests/swallow_audit.py --critical      # only decision/order/risk paths
    python3 tests/swallow_audit.py --all           # every hit, grouped by file
    python3 tests/swallow_audit.py --json          # machine-readable, for diffing

    Point it at a sibling repo too:
    python3 tests/swallow_audit.py --root ~/day_trader_pro

DIFFING FOR NEW ONES
    `--json` output is stable and sorted, so committing a snapshot and diffing it
    turns "did we add a new silent failure?" into a mechanical check rather than
    a memory exercise. That is the durable value; the one-off census is not.

Read-only. stdlib only. Never imports the code it audits.
"""

import argparse
import ast
import json
import os
import sys

# Tier by consequence, not by line count. A silent swallow in the first group can
# cost money or corrupt the record; in the last it costs a cosmetic glitch.
TIERS = [
    ("1 — RISK / ORDERS / RECORD", (
        "risk/risk_manager.py", "risk/setup_scorer.py",
        "execution/exit_engine.py", "execution/entry_engine.py",
        "execution/position_manager.py", "execution/limit_ladder.py",
        "execution/order_confirm.py", "database/trade_logger.py",
        "strategy/", "selector.py", "orchestrator.py",
    )),
    ("2 — DATA CAPTURE / DECISION INPUTS", (
        "analysis/", "data/", "harvest.py", "eod_conductor.py",
        "consolidate_trades.py", "main.py",
    )),
    ("3 — DISPLAY / TOOLING", ()),      # everything else
]
SKIP_DIRS = ("/.git/", "__pycache__", "/venv/", "/tests/")


def tier_of(rel):
    for i, (_, pats) in enumerate(TIERS):
        if any(p in rel for p in pats):
            return i
    return len(TIERS) - 1


class Visitor(ast.NodeVisitor):
    def __init__(self):
        self.hits = []
        self._fn = "<module>"

    def visit_FunctionDef(self, node):
        prev, self._fn = self._fn, node.name
        self.generic_visit(node)
        self._fn = prev

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Try(self, node):
        for h in node.handlers:
            broad = h.type is None or (
                isinstance(h.type, ast.Name)
                and h.type.id in ("Exception", "BaseException"))
            if not broad:
                continue
            if any(isinstance(x, ast.Raise) for x in h.body):
                continue                       # re-raises: not swallowed
            dumped = " ".join(ast.dump(x) for x in h.body)
            pages = "notify" in dumped or "alert" in dumped.lower()
            logs = ("log" in dumped) or ("print" in dumped)
            only_pass = len(h.body) == 1 and isinstance(h.body[0], ast.Pass)
            loud = "pages" if pages else ("logs only" if logs else
                                          ("SILENT (pass)" if only_pass
                                           else "SILENT (no log)"))
            try:
                guarded = ast.unparse(node.body[0]).split("\n")[0][:70]
            except Exception:                  # noqa: BLE001 — py<3.9
                guarded = "?"
            self.hits.append({"line": h.lineno, "func": self._fn,
                              "loudness": loud, "guards": guarded,
                              "bare": h.type is None})
        self.generic_visit(node)


def scan(root):
    out = []
    for dirpath, _, files in os.walk(root):
        if any(s in dirpath + "/" for s in SKIP_DIRS):
            continue
        for fn in sorted(files):
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, root)
            try:
                tree = ast.parse(open(path, encoding="utf-8").read())
            except Exception:                  # noqa: BLE001
                continue
            v = Visitor()
            v.visit(tree)
            for h in v.hits:
                h.update({"file": rel, "tier": tier_of(rel)})
                out.append(h)
    return sorted(out, key=lambda h: (h["tier"], h["file"], h["line"]))


def _ident(h):
    """Stable identity for diffing. Line numbers move whenever anything above
    them changes, so including one would report an entire file as new after a
    single-line edit — the same false-alarm class the tool exists to prevent."""
    return (h["file"], h["func"], h["guards"])


def _report_new(hits, snapshot_path):
    """Print the silent handlers present now and absent from the snapshot.

    Exit 0 when nothing was added, 1 when something was — so a caller can gate
    on the code, and the OUTPUT still names them either way. Prints its own
    verdict rather than relying on the exit status alone (the 2026-08-01
    laundered-green lesson).
    """
    try:
        with open(snapshot_path) as fh:
            prior = json.load(fh)
    except Exception as exc:                                 # noqa: BLE001
        print(f"  cannot read snapshot {snapshot_path}: "
              f"{type(exc).__name__}: {exc}")
        return 2

    now_sil   = [h for h in hits if h["loudness"].startswith("SILENT")]
    prior_sil = {_ident(h) for h in prior
                 if str(h.get("loudness", "")).startswith("SILENT")}
    added = [h for h in now_sil if _ident(h) not in prior_sil]

    print(f"  silent now: {len(now_sil)}   in snapshot: {len(prior_sil)}   "
          f"NEW: {len(added)}")
    if not added:
        print("  ✓ no silent handler added since the snapshot")
        return 0
    print(f"\n{'-' * 76}")
    for h in sorted(added, key=lambda x: (x["tier"], x["file"], x["line"])):
        bare = " [BARE]" if h["bare"] else ""
        print(f"  TIER {h['tier'] + 1}  {h['file']}:{h['line']}  "
              f"{h['func']}{bare}")
        print(f"          guards: {h['guards']}")
    print(f"{'-' * 76}")
    print("  A new silent handler is not automatically a defect — but it is a "
          "decision\n  someone should have made on purpose. Classify each one.")
    return 1


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--critical", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--since", default=None, metavar="SNAPSHOT.json",
                    help="name the silent handlers added since a prior --json "
                         "snapshot (identity = file+func+guards, not line)")
    a = ap.parse_args(argv[1:])

    hits = scan(os.path.expanduser(a.root))

    if a.since:
        return _report_new(hits, os.path.expanduser(a.since))

    if a.json:
        print(json.dumps(hits, indent=1, sort_keys=True))
        return 0

    silent = [h for h in hits if h["loudness"].startswith("SILENT")]
    print(f"root: {a.root}")
    print(f"swallowing handlers: {len(hits)}   silent: {len(silent)}   "
          f"logs-only: {sum(1 for h in hits if h['loudness'] == 'logs only')}   "
          f"pages: {sum(1 for h in hits if h['loudness'] == 'pages')}\n")

    for i, (name, _) in enumerate(TIERS):
        tier = [h for h in hits if h["tier"] == i]
        tsil = [h for h in tier if h["loudness"].startswith("SILENT")]
        print(f"  TIER {name:<34} {len(tier):>4} handlers, {len(tsil):>4} silent")
    if a.critical or a.all:
        show = [h for h in silent if h["tier"] == 0] if a.critical else silent
        print(f"\n{'-' * 76}")
        print("  SILENT handlers"
              f"{' in TIER 1 (risk / orders / record)' if a.critical else ''}")
        print(f"{'-' * 76}")
        last = None
        for h in show:
            if h["file"] != last:
                print(f"\n  {h['file']}")
                last = h["file"]
            flag = " [BARE]" if h["bare"] else ""
            print(f"    L{h['line']:<6} {h['func']:<30}{flag}")
            print(f"           guards: {h['guards']}")
    else:
        print("\n  --critical for the tier-1 detail, --all for everything, "
              "--json to diff against a committed snapshot.")

    print("\n  Silence is not automatically a bug — a guarded optional import or")
    print("  a journal emit that must never kill a trade is correctly silent.")
    print("  The question is whether a FAILURE here would change a decision,")
    print("  an order, or the record. If yes, it must log or page.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
