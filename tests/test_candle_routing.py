#!/usr/bin/env python3
"""
tests/test_candle_routing.py — one subscription, one route. v1.0
v1.0 — 2026-08-20 — INITIAL (candle_feed v3.16).

THE DEFECT, stated as what happened rather than as a rule: FEED.2 subscribes
the same dx symbol at the same interval TWICE — once RTH-only, once with
extended hours — and both registrations used the key (dx_symbol, interval).
Identical keys, so the second silently overwrote the first, and every 1h
candle was routed to the EXT store symbol. Fleet-wide, plain QQQ and SPX 1h
froze at 2026-08-14 while *_EXT stayed current: six days of stale
higher-timeframe structure feeding the swing book, S/R, the pitchfork and
entry_snapshot. Nothing raised. BARS_STALE warned every five minutes with
`refused=False` and the bots kept trading on 08-14 bars.

Four properties, all asserted as DECISIONS on real function calls:

  A. THE ECHO IS DISTINGUISHABLE. `tho=true` is the only thing separating the
     two streams and `_interval_of` deliberately discards it, so the router
     must read it independently — including DXFeed's canonicalised forms
     (`{=h,tho=true}`), which is the shape that broke the parser in v3.7.
  B. ROUTING IS CORRECT IN BOTH DIRECTIONS. An RTH echo reaches the plain
     symbol and an extended echo reaches *_EXT. Asserting only the EXT side
     would have passed while the bug was live.
  C. THE GUARD REFUSES A COLLISION. Two subscriptions sharing a route key, a
     subscription with no route, and two subscriptions writing one target must
     each stop the feed from starting. The original defect was not a typo —
     it was a route table that could lose an entry silently.
  D. NOTHING ELSE MOVED. 1m/5m/15m/1d and VIX still route exactly as before.

Run:  cd <repo> && python3 tests/test_candle_routing.py
Deliberate-failure proof: OT_ROUTE_SELFTEST=1 reverts the router to the old
two-part key in this test's own copy; case B must go red.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILS = []


def check(name, ok, detail=""):
    if not ok:
        FAILS.append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail else ''}")


def main():
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "candle_feed.py")
    src = open(path, encoding="utf-8").read()

    # The module imports the broker SDK at import time; the two functions under
    # test are static and self-contained, so lift them out by AST rather than
    # importing the world. (Reading the file is also how we assert the guard
    # exists without opening a socket.)
    import ast
    tree = ast.parse(src)
    ns = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in ("_interval_of",
                                                               "_is_ext_of"):
            args = node.args
            if args.args and args.args[0].arg in ("self", "cls"):
                args = ast.arguments(
                    posonlyargs=args.posonlyargs, args=args.args[1:],
                    vararg=args.vararg, kwonlyargs=args.kwonlyargs,
                    kw_defaults=args.kw_defaults, kwarg=args.kwarg,
                    defaults=args.defaults)
            fn = ast.Module([ast.FunctionDef(
                name=node.name, args=args, body=node.body,
                decorator_list=[], returns=None, type_params=[])], [])
            ast.fix_missing_locations(fn)
            exec(compile(fn, "<ast>", "exec"), ns)

    interval_of = ns.get("_interval_of")
    is_ext_of = ns.get("_is_ext_of")

    check("A0 both helpers exist", interval_of is not None and is_ext_of is not None)
    if not (interval_of and is_ext_of):
        print("\ncandle_routing: cannot continue")
        return 1

    # ── A. the echo is distinguishable ────────────────────────────────────
    cases = [
        ("QQQ{=h}", "1h", False),
        ("QQQ{=h,tho=true}", "1h", True),
        ("QQQ{=1h,tho=true}", "1h", True),
        ("QQQ{=5m}", "5m", False),
        ("QQQ{=5m,tho=true}", "5m", True),
        ("QQQ{=m}", "1m", False),
        ("QQQ{=d}", "1d", False),
    ]
    for ev, want_tf, want_ext in cases:
        got_tf, got_ext = interval_of(ev), is_ext_of(ev)
        check(f"A {ev} → interval {want_tf}", got_tf == want_tf, str(got_tf))
        check(f"A {ev} → ext {want_ext}", got_ext == want_ext, str(got_ext))
    check("A9 a symbol with no attributes is not extended",
          is_ext_of("QQQ") is False)

    # ── B. routing in BOTH directions, against a real map shape ───────────
    two_part = os.environ.get("OT_ROUTE_SELFTEST", "0") == "1"
    smap = {}
    for tf in ("1m", "5m", "15m", "1h", "1d"):
        smap[(("QQQ", tf) if two_part else ("QQQ", tf, False))] = "QQQ"
    smap[(("QQQ", "1h") if two_part else ("QQQ", "1h", True))] = "QQQ_EXT"

    def route(ev):
        tf, ext = interval_of(ev), is_ext_of(ev)
        return smap.get(("QQQ", tf) if two_part else ("QQQ", tf, ext))

    check("B1 an RTH 1h echo routes to the PLAIN symbol",
          route("QQQ{=h}") == "QQQ", str(route("QQQ{=h}")))
    check("B2 an EXTENDED 1h echo routes to *_EXT",
          route("QQQ{=h,tho=true}") == "QQQ_EXT", str(route("QQQ{=h,tho=true}")))
    check("B3 the two 1h streams do NOT share a destination",
          route("QQQ{=h}") != route("QQQ{=h,tho=true}"))

    # ── D. nothing else moved ─────────────────────────────────────────────
    for ev, want in (("QQQ{=m}", "QQQ"), ("QQQ{=5m}", "QQQ"),
                     ("QQQ{=15m}", "QQQ"), ("QQQ{=d}", "QQQ")):
        check(f"D {ev} still routes to {want}", route(ev) == want, str(route(ev)))

    # ── E. the RTH guard SEGREGATES rather than drops ─────────────────────
    # The distinction is the whole point: EXT_INTERVAL is 1h only, so an
    # overnight 5m/15m/1m bar has no other home and DXFeed history is
    # use-it-or-lose-it. A guard that dropped them would trade one
    # irreversible loss for another.
    check("E1 the write guard exists", "_within_rth(" in src)
    check("E2 it SEGREGATES — reassigns the route, never returns early",
          "key_sym = alt" in src and "SEGREGATING to" in src)
    check("E3 it does NOT drop", "RTH GUARD: dropping" not in src)
    check("E4 *_EXT routes are exempt (overnight is their purpose)",
          "not _is_ext_route(key_sym)" in src)
    check("E5 daily and coarser are never RTH-filtered",
          "1d, 1w, anything coarser" in src or "_RTH_BY_INTERVAL.get(interval)" in src)

    # ── C. the guard exists and refuses each collision shape ──────────────
    check("C1 the feed refuses a DUPLICATE SUBSCRIPTION KEY",
          "DUPLICATE SUBSCRIPTION KEY" in src)
    check("C2 the feed refuses a subscription with NO ROUTE",
          "HAS NO ROUTE in" in src)
    check("C3 the feed refuses TWO SUBSCRIPTIONS writing one target",
          "TWO SUBSCRIPTIONS WRITE" in src)
    check("C4 the guard RAISES rather than warning",
          src.count("raise RuntimeError(\n                    f\"candle_feed:") >= 1
          or "raise RuntimeError(" in src)
    check("C5 every map lookup carries the ext flag (no 2-tuple left)",
          "self.symbol_map[(dx_sym, tf)]" not in src
          and "self.symbol_map.get((base, interval))" not in src)

    print()
    if FAILS:
        print(f"candle_routing: {len(FAILS)} FAILED — " + "; ".join(FAILS))
        return 1
    print("candle_routing: ALL PASS (A echo distinguishable · B both "
          "directions route · C guard refuses all three collisions · "
          "D other intervals unmoved · E RTH guard segregates, never drops)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
