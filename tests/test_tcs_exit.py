#!/usr/bin/env python3
"""
tests/test_tcs_exit.py — v1.0 — 2026-08-13   (TC.6)

Operator's spec: *"Exit should be breached (loss) or nickel close (profit)."*
No premium stop, no ratchet — and that is not a simplification. **The measured
EV was held to expiry, UNMANAGED** (+$0.52/spread, 90% terminal OK, 79%
recovered on the ORB-anchored runaway arm). A stop bolted on afterwards is a
different trade with a different expectancy, and paper results from it would not
transfer.

THE TWO FAILURES THIS SUITE EXISTS TO CATCH:
  1. A TC.6 leg reaching the condor's ratchet or 25% stop — then we would be
     paper-trading something other than what was measured, and the numbers would
     look fine while meaning nothing.
  2. A WICK through the boundary counting as a breach. Only a CLOSE decides
     acceptance — the operator's own rule, and the same distinction that made
     `tcs_floor_durability` v1.1 report 14.7% intraday against 56.1% terminal.

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python -m pytest tests/test_tcs_exit.py -q
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SRC = open(os.path.join(os.path.dirname(__file__), "..",
                        "execution", "exit_engine.py"), encoding="utf-8").read()


def condor_fn() -> str:
    start = SRC.index("    def _evaluate_condor_leg(")
    return SRC[start:SRC.index("\n    def ", start + 10)]


def line_of(needle: str) -> int:
    body = condor_fn()
    assert needle in body, f"{needle!r} not in _evaluate_condor_leg"
    return body[:body.index(needle)].count("\n")


# ── ladder order: a TC.6 leg must never reach the ratchet ───────────────────

def test_tcs_branch_returns_before_the_ratchet_and_the_25pct_stop():
    """THE ONE THAT MATTERS. If the TC.6 branch sits after the ratchet, a trend
    credit spread inherits the condor's stop and we are no longer trading what
    was measured."""
    tcs = line_of("if is_trend_participation(record):")
    ratchet = line_of("RATCHET SCOPE")
    stop = line_of('decision.exit_reason = f"condor_stop')
    tp = line_of("TIME-GATED TAKE PROFIT")
    assert tcs < ratchet, "the TC.6 branch runs AFTER the ratchet"
    assert tcs < stop, "the TC.6 branch runs AFTER the 25% stop"
    assert tcs < tp, "the TC.6 branch runs AFTER the take-profit"


def test_hard_close_still_outranks_everything():
    """15:45 is unconditional and must precede the TC.6 branch — a position
    cannot be held past the flatten by any exit rule."""
    assert line_of('decision.exit_reason = "hard_close_15:45_ET"') < \
        line_of("if is_trend_participation(record):")


def test_no_nickel_close_on_trend_participation():
    """Operator, 2026-08-14: "There should be no closing it short of a BREACH of
    that level or the SESSION HARD CLOSE cutoff." Revises the earlier
    breach-or-nickel spec. A nickel close is a PROFIT exit and caps a position
    whose measured EV was HELD TO EXPIRY, UNMANAGED."""
    seg = tcs_branch_source()
    assert "CONDOR_NICKEL_CLOSE" not in seg, (
        "a nickel close is back in the TC.6 branch — the only exits are a "
        "breach of the ORB bound and the 15:45 hard close")


def test_the_tcs_branch_returns_rather_than_falling_through():
    """Both TC.6 exits must `return decision`. A fall-through would drop the leg
    into the condor ladder below with no further guard."""
    body = condor_fn()
    seg = tcs_branch_source()
    # Counting returns proves nothing about the path that has none — that was
    # the v1.0 defect. Assert the branch ENDS in one.
    assert seg.rstrip().endswith("return decision")


# ── breach is a CLOSE, never a wick ────────────────────────────────────────

def test_breach_reads_the_CLOSE_column_only():
    body = condor_fn()
    seg = body[body.index("if is_trend_participation(record):"):]
    seg = seg[:seg.index("return decision", seg.index("tcs_breach"))]
    assert 'df_1m["close"]' in seg, "the breach rule is not reading closes"
    for wick in ('df_1m["high"]', 'df_1m["low"]'):
        assert wick not in seg, (
            f"the breach rule reads {wick} — a WICK through the boundary is a "
            "TOUCH, and only a CLOSE decides acceptance")


def test_breach_direction_is_side_aware():
    """A put spread sits BELOW the boundary so a close BELOW breaches; a call
    spread sits above so a close ABOVE breaches. Getting this backwards would
    exit every winner and hold every loser."""
    body = condor_fn()
    seg = body[body.index("if is_trend_participation(record):"):]
    m = re.search(r'_breached\s*=\s*\((.*?)\)\s*if\s*_side\s*==\s*"put"\s*else\s*\((.*?)\)', seg)
    assert m, "the side-aware breach expression is missing"
    assert "<" in m.group(1) and ">" in m.group(2), (
        "breach directions are inverted: put must breach on a close BELOW the "
        "boundary and call on a close ABOVE")


def test_missing_tape_is_reported_not_silently_passed():
    """A breach rule that cannot see price is INERT, and an inert stop must
    never look like a passing check."""
    body = condor_fn()
    seg = body[body.index("if is_trend_participation(record):"):]
    assert "logger.warning" in seg and "INERT" in seg, \
        "a missing 1m tape is not being reported"


# ── the branch is scoped to TC.6 only ──────────────────────────────────────

def test_ordinary_condor_legs_are_untouched():
    """`is_trend_credit` gates the whole branch, so a normal condor leg still
    gets ratchet, stop, TP and nickel."""
    body = condor_fn()
    assert body.count("is_trend_participation(record)") == 1
    for keeper in ("RATCHET SCOPE", "condor_stop", "condor_tp"):
        assert keeper in body, f"{keeper} was removed from the condor path"


def tcs_branch_source() -> str:
    """The TC.6 `if` block, sliced by AST rather than by text.

    A textual slice ran past the branch into condor code and made the guard
    below fail on the condor's OWN stop — a false positive that would have
    trained someone to loosen the check. The AST knows where the block ends.
    """
    import ast
    tree = ast.parse(SRC)
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and "is_trend_participation" in (
                ast.get_source_segment(SRC, node.test) or ""):
            return ast.get_source_segment(SRC, node) or ""
    raise AssertionError("the TC.6 branch is gone from exit_engine")


def test_no_premium_stop_inside_the_tcs_branch():
    """DELIBERATE FAILURE GUARD. If a future edit adds a premium stop here, the
    trade stops matching the measurement and this goes red."""
    seg = tcs_branch_source()
    for banned in ("CONDOR_STOP_LOSS_PCT", "CONDOR_RATCHET", "stop_level"):
        assert banned not in seg, (
            f"{banned} appears inside the TC.6 branch — the measured EV was "
            "HELD TO EXPIRY, UNMANAGED, and a stop changes the trade")


# ── the fall-through that shipped, and the test that missed it ─────────────

def test_the_branch_ENDS_in_a_return_not_just_contains_one():
    """⚠️ THE v1.0 TEST ASSERTED THE BRANCH CONTAINED TWO `return decision`
    STATEMENTS. IT DID. And it was still broken.

    Neither return covers the path where NEITHER breach NOR nickel fires — and
    that path fell through to the ratchet and the 25% condor stop. Observed live
    2026-08-14: a $0.06 credit sets stop_premium at $0.07 (credit x 1.25), so
    ONE CENT of widening closed the trade. Every TC.6 leg on the fleet stopped
    out within seconds of opening.

    Counting returns proves nothing about the path that has none. This asserts
    on the branch's LAST STATEMENT, which is the only thing that makes the
    ratchet unreachable.
    """
    import ast
    tree = ast.parse(SRC)
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and "is_trend_participation" in (
                ast.get_source_segment(SRC, node.test) or ""):
            last = node.body[-1]
            assert isinstance(last, ast.Return), (
                "the TC.6 branch does not END in a return — it falls through to "
                "the ratchet and the 25% stop, which is a different trade from "
                "the one that was measured")
            return
    raise AssertionError("the TC.6 branch is gone from exit_engine")


def test_every_path_out_of_the_branch_is_a_return():
    """Stronger form: no statement after the branch's own control flow can leak
    into the condor ladder."""
    import ast
    tree = ast.parse(SRC)
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and "is_trend_participation" in (
                ast.get_source_segment(SRC, node.test) or ""):
            src_seg = ast.get_source_segment(SRC, node)
            assert src_seg.rstrip().endswith("return decision")
            return


# ── the joint EV test ──────────────────────────────────────────────────────

def test_joint_ev_requires_rich_credit_at_low_pop_and_allows_thin_at_high():
    """THE SHAPE IS THE POINT. A flat credit floor and a flat POP floor are
    INDEPENDENT, and independent is the bug: POP >= 0.70 selects FAR strikes,
    far strikes pay little, and neither floor ever sees the other.
    credit/width > L*(1-POP)/POP links them."""
    import config
    L = config.TCS_LOSS_GIVEN_BREACH
    req = lambda pop: L * (1.0 - pop) / pop
    assert req(0.70) > req(0.80) > req(0.90) > req(0.95)
    assert req(0.70) > 0.20, "a POP-0.70 strike must pay richly"
    assert req(0.95) < 0.05, "a POP-0.95 strike may be thin"


def test_joint_ev_blocks_the_2026_08_14_live_fills():
    """Regression on real fills: NVDA sold a $5-wide for $0.06 and PLTR a
    $6-wide for $0.08 at 10:02 ET. Both must fail on EV ALONE, even at a
    generous POP."""
    import config
    L = config.TCS_LOSS_GIVEN_BREACH
    for credit, width, pop in ((0.06, 5.0, 0.96), (0.08, 6.0, 0.96)):
        assert credit / width <= L * (1.0 - pop) / pop, (
            f"credit {credit} on width {width} still clears the EV test")
    # and a real one still passes
    assert 0.55 / 5.0 > L * (1.0 - 0.90) / 0.90


def test_unresolvable_pop_is_a_skip_not_a_pass():
    """A missing ATR must never read as a safe trade — `_pop` returns 0.0 and
    the caller must SKIP, not divide by it."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "strategy",
                            "trend_credit_spread.py"), encoding="utf-8").read()
    i = src.index("pop = cv.pop(")
    assert "if pop <= 0.0:" in src[i:i + 400]
    assert "return None" in src[i:i + 600]


# ── TC.6 v2.1 entry shape ──────────────────────────────────────────────────

def tcs_src():
    return open(os.path.join(os.path.dirname(__file__), "..", "strategy",
                             "trend_credit_spread.py"), encoding="utf-8").read()


def test_no_em_floor_can_override_the_orb_bound():
    """DIS-INHERITED FROM THE CONDOR. `_select_beyond_rail` requires a strike to
    clear BOTH the rail and the min-distance, so whichever is further out wins.
    An EM-derived floor beyond the ORB high would push the strike past the
    operator's level — a FITTED PERCENTAGE overriding a STRUCTURAL one."""
    s = tcs_src()
    assert "CONDOR_EM_FLOOR_FRAC" not in s
    assert 'min_dist = float("inf") if side == "put" else float("-inf")' in s


def test_price_must_be_outside_the_range_at_entry():
    """Entry and exit must agree. The exit calls a close back through the bound
    INVALIDATION, so entering while price is already inside means the trade is
    born in the state its own exit calls dead — the CNT.1 failure shape."""
    s = tcs_src()
    assert "_outside = (current_price > bound if side == \"put\"" in s
    assert "back INSIDE the range" in s


def test_no_cooldown_gate():
    """Removed 2026-08-14: a timer stacked on nine substantive gates suppresses
    valid re-entries without preventing a single bad one. The loop it was added
    for is fixed at the source."""
    s = tcs_src()
    assert "TCS_COOLDOWN_MIN" not in s and "_last_fire" not in s


def test_the_not_exceeded_filter_is_dis_inherited():
    """⚠️ IT MADE THE BOUND DECORATIVE, not merely redundant.

    `session_low` <= `orb_low` < `orb_high` — the opening range is PART of the
    session — so requiring a put strike to clear BOTH the bound AND the session
    low collapses to the session low EVERY TIME. The strike was always placed
    below the ORB LOW and never at the specified level, so the ENTRY placed it
    somewhere the EXIT never referenced. Mirrored for calls.
    Safety is carried by POP >= 0.70 and the joint EV test, which ask the same
    question in sigma*sqrt(T) terms FROM NOW rather than backward-looking."""
    s_ = tcs_src()
    assert 'side, bound, extreme = "put", orb_high, None' in s_
    assert 'side, bound, extreme = "call", orb_low, None' in s_


def test_the_arithmetic_that_made_the_bound_decorative():
    """Pin the relationship itself, so nobody re-adds the filter without
    noticing it can only ever dominate."""
    orb_high, orb_low = 582.50, 578.10
    session_low = min(orb_low, 575.0)          # the range is part of the session
    assert session_low <= orb_low < orb_high
    # a put strike clearing BOTH collapses to the extreme
    assert min(orb_high, session_low) == session_low


def test_the_bound_is_the_orb_level_and_it_is_sovereign():
    """A bullish vote sells PUTS beneath the ORB HIGH — the level price broke
    from, which is the floor of that move and the RICHER strike because it sits
    closer to spot. Mirrored for a bearish vote at the ORB LOW.
    Nothing else may displace it: `extreme` is None, and the EM floor is a
    non-binding sentinel."""
    s_ = tcs_src()
    assert 'side, bound, extreme = "put", orb_high, None' in s_
    assert 'side, bound, extreme = "call", orb_low, None' in s_
    assert 'min_dist = float("inf") if side == "put" else float("-inf")' in s_


# ── TCS.1 de-coupling ──────────────────────────────────────────────────────

def test_tc6_does_not_import_or_instantiate_the_condor():
    """It used to instantiate `IronCondorStrategy` purely to borrow five of its
    methods — so TC.6 could not exist without the condor, and a condor change
    reached it silently."""
    import ast
    # ⚠️ AST, NOT SUBSTRING. A substring check matches the COMMENT that explains
    # the removal — WORKING_AGREEMENT 20: an absence canary tests for a
    # DEFINITION, never for a mention. This one caught its own comment.
    tree = ast.parse(tcs_src())
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            assert "iron_condor" not in (n.module or ""), \
                "TC.6 imports the condor again"
    code = "\n".join(l for l in tcs_src().split("\n")
                     if not l.lstrip().startswith("#"))
    assert "IronCondorStrategy.__new__" not in code
    assert "self._sel" not in code


def test_tc6_uses_no_CONDOR_constants():
    """Six `CONDOR_*` knobs governed a trade that is not a condor. Changing one
    for the condor silently retuned this one, and nothing said so."""
    import re
    s = tcs_src()
    code = "\n".join(l for l in s.split("\n")
                     if not l.strip().startswith("#") and "CONDOR_" in l)
    assert not re.search(r"\bCONDOR_[A-Z_]+\b", code), \
        f"TC.6 still reads a condor constant: {code[:200]}"


def test_the_tcs_defaults_equal_the_condor_values_they_replaced():
    """⚠️ THIS IS A DE-COUPLING, NOT A RE-TUNE. If these ever diverge it must be
    a DECISION, recorded — not a drift nobody noticed."""
    import config as c
    for tcs, condor in (("TCS_MIN_POP", "CONDOR_MIN_POP"),
                        ("TCS_MAX_QUOTE_WIDTH", "CONDOR_MAX_QUOTE_WIDTH"),
                        ("TCS_POP_BAR_MIN", "CONDOR_POP_BAR_MIN"),
                        ("TCS_NICKEL_REF", "CONDOR_NICKEL_CLOSE"),
                        ("TCS_WING_WIDTH_SPX", "CONDOR_WING_WIDTH_SPX"),
                        ("TCS_WING_WIDTH_QQQ", "CONDOR_WING_WIDTH_QQQ")):
        assert abs(float(getattr(c, tcs)) - float(getattr(c, condor))) < 1e-9, \
            f"{tcs} has drifted from {condor}"


def test_the_shared_math_has_exactly_one_implementation():
    """Both strategies must DELEGATE. A second copy in either recreates the
    divergence the module was created to remove."""
    ic = open(os.path.join(os.path.dirname(__file__), "..", "strategy",
                           "iron_condor_strategy.py"), encoding="utf-8").read()
    for fn, shared in (("_liquidity_rank", "cv.liquidity_rank"),
                       ("_pop", "cv.pop"),
                       ("_quote_ok", "cv.quote_ok"),
                       ("_select_beyond_rail", "cv.select_beyond_rail")):
        i = ic.index(f"def {fn}(")
        body = ic[i:i + 700]
        assert shared in body, f"condor's {fn} no longer delegates to {shared}"


def test_the_credit_math_flag_is_named_for_what_it_does():
    """`is_iron_condor` never meant "this is a condor" — it selected CREDIT
    SPREAD math. That name is why TC.6 had to declare itself a condor to get
    correct arithmetic. Both names now address ONE field, so a missed rename
    cannot make a signal a credit vertical to one half of the system and a debit
    to the other."""
    from strategy.base_strategy import OptionsSignal
    s1 = OptionsSignal(strategy_name="X", setup_type="y", direction="neutral")
    s1.is_credit_vertical = True
    assert s1.is_iron_condor is True
    s2 = OptionsSignal(strategy_name="X", setup_type="y", direction="neutral")
    s2.is_iron_condor = True
    assert s2.is_credit_vertical is True
    s2.net_credit, s2.stop_loss_pct = 0.60, 0.25
    assert abs(s2.stop_premium() - 0.75) < 1e-9, "credit math not selected"
