#!/usr/bin/env python3
"""
tests/vwap_orientation_ledger.py — v1.6 — 2026-08-10

v1.6 — 2026-08-10 — VW.1f: THREE DEFECTS THE TOOL'S OWN FIRST REAL OUTPUT
       EXPOSED. All three rendered cleanly and none raised.
       (a) ~29 TRADES VANISHED. 304 rows minus 40 reported unjoinable leaves 264
           mappable, but only 235 joined. A trade that resolves to a family yet
           whose (symbol, family, direction) key matches no signal group was
           dropped with NO line anywhere — the exact gap "by cause" reporting
           was built to close. Now counted and listed as MAPPED BUT UNMATCHED.
       (b) THE MIXED-ERAS WARNING CRIED WOLF ON ITS FIRST OUTING. It fired on
           three ALL-PRE-BAKE dates because the totals held both kinds — and the
           9,596 "emitted" was exactly TCS's own total, TCS being the one track
           that always carried `dir`. The split was BY TRACK, not by date, and
           the warning told the operator to split dates at a bake not in range.
           Now warns only when a SINGLE TRACK holds both, which is what a real
           era mix looks like; otherwise it says explicitly that no action is
           needed.
       (c) THE VERDICT FLOOR TESTED THE WRONG THING. `tr < 3` on TOTAL trades
           let CONTINUATION print "orientation looks right" off a MISALIGNED arm
           of FIVE against an aligned arm of 228. A verdict rests on the SMALLER
           arm; a total floor does not constrain it. Now MIN_ARM_TRADES=8 on
           EACH arm. Compounding it and stated in the output: the per-group
           MAJORITY-ALIGNMENT collapse systematically SHRINKS the minority arm,
           so the method minimises the very population the verdict depends on.

v1.5 — 2026-08-08 — READ THE FIELD WHEN IT EXISTS. `trade_readiness` v1.6 now
       stamps `dir` on every track, so post-bake rows are READ rather than
       inferred — which matters most for SWEEP, whose direction lives in
       `ctx.liq_map` and could never be recovered offline (v1.4 had to pair
       readiness rows against staged picks to approximate it). The v1.4
       derivations are KEPT, not replaced: every session banked before that
       bake has no `dir` to read, and no fleet-side change can reach history.
       An emitted `""` (no intended side this tick) is now distinguished from a
       missing field, and `"neutral"` from both.

v1.4 — 2026-08-08 — THE JOIN LAYER, the fifth and final one — and this time the
       WHOLE remaining path was traced before anything was patched. v1.3's run
       (39,344 records) surfaced three stacked defects, none of them the filter:
       (1) DIRECTION EXISTS ON ONLY ONE TRACK. `readiness.factors.dir` is
           journaled ONLY by `_trend_credit_spread` (trade_readiness.py:569).
           Continuation (:331), sweep (:352), condor (:393 — has `side`, not
           `dir`) and butterfly (:414) journal NO direction field. So five of
           six strategies fell to `aligned() -> None` and 30,565 records were
           dumped into "undecidable" under a label that blamed the index/NONE
           case. The only strategy in the output table — TREND_CREDIT_SPREAD,
           7,201 signals — is the only track that carries `dir`. `discover()`
           compounded it: one TCS record made `readiness.factors.dir` print as
           found, masking that it is dead for the five strategies item E is
           actually about.
       (2) THE TRADE JOIN COULD NEVER MATCH. Journal groups key on track slugs
           (CONTINUATION, SWEEP, CONDOR_CALL...) while trade rows carry class
           names (ContinuationStrategy, SweepReversal, IronCondorStrategy...).
           Uppercasing both sides never makes SWEEPREVERSAL equal SWEEP, so
           `pnl_by` matched nothing — 304 trade rows, zero joined.
       (3) AND THE ONE DECIDABLE STRATEGY CANNOT HAVE TRADES. TCS's firing
           engine (vertical_spread_strategy.py) does not exist yet (v1.3 header,
           TC.4), so its 0-trade INSUFFICIENT verdict was arithmetically forced.
       FIXES: per-strategy DIRECTION RESOLVER (TCS from factors.dir;
       continuation from factors.label exactly as the emitter's own staged-pick
       path derives it, trade_readiness.py:763; condor_call -> SHORT and
       condor_put -> LONG on mechanism — a credit side's exposure is against
       the move toward it, NOT the call=long/put=short option-buyer reading;
       sweep from `staged.direction` on readiness_staged_pick rows, paired with
       the last market snapshot seen on that symbol within SNAP_MAX_AGE_S;
       butterfly undecidable BY DESIGN). Family-normalised trade join with
       condor legs attributed per side via setup_type. Undecidable is now
       REPORTED BY CAUSE so the counter can never lie about what it holds
       again, and unmatched trades are printed with their reason (ORB has no
       readiness track by design; ADOPTED rows have no signal ancestry).

v1.3 — 2026-08-08 — THE EVENT FILTER, the fourth layer. v1.2 resolved all five
       fields correctly and the run STILL returned 419 undecidable and ZERO
       decidable. Cause: the event whitelist accepted only
       ("scored","fired","entry","entered") — names predating trade_readiness
       v1.5 — while the records carrying `readiness.market` are named
       `readiness`, `readiness_would_fire` and `readiness_staged_pick`. On
       2026-08-06 alone that is 11,584 records skipped before their VWAP side
       was read; the 419 survivors were `scored` rows with no market section.
       The data was never missing: BELOW 5,058 / ABOVE 3,912 that same day.
       Now PREFIX-matched on `readiness*` rather than enumerated — an exact list
       is precisely what kept this tool three versions behind its own emitter.
       ⚠️ THE LESSON, and it cost four versions: I patched the layer that had
       just failed, four times, instead of tracing the whole path once. Field
       names, then depth, then paths, then the filter. Each fix was correct and
       each was one layer short.

v1.2 — 2026-08-08 — PATHS VERIFIED AGAINST THE EMITTER. v1.1 made discovery
       path-aware, which was necessary but not sufficient: I then GUESSED the
       paths (`vwap.vwap`, `factors.dir`) and the tool found neither across
       39,344 records. Reading `trade_readiness._journal()` settles it — it
       emits ONE section, `readiness=`, holding `market` and `factors`, so
       everything is TWO levels deep: `readiness.market.vwap`,
       `readiness.market.price_vs_vwap`, `readiness.factors.dir`. The field
       NAMES in the standing note were right; the DEPTH was wrong, which is why
       two flat renames and one shallow path all missed.
       There is NO price field — `dist_pct` replaces it and is better, being
       comparable across symbols.
       ⚠️ THE TOOL EARNED ITS KEEP HERE: it printed "(NOT FOUND)" per field and
       REFUSED rather than producing an empty ledger. A silent zero-row report
       would have read as "no misorientation" instead of "wrong key".

v1.1 — 2026-08-07 — PATH-AWARE DISCOVERY. This tool exited rc=1 for two nights
       against a schema that had never landed, and the diagnosis "three field
       renames" was wrong. `_first_key` tested `n in rec` — TOP-LEVEL keys only
       — while the journal nests these under sections: `readiness.strategy` and
       `factors.dir`. **No flat rename could have reached them.** CAND entries
       may now be DOTTED PATHS and every accessor goes through `dig()`, so the
       next schema section costs one tuple entry instead of another dead tool.
       Also added `pnl_usd`, which is what the trades table actually calls it.
       ⚠️ trade_readiness v1.5 (2026-08-05) is what began emitting
       `{vwap, price_vs_vwap, dist_pct}` at all — before it, VWAP was computed
       every tick by volatility_engine and NEVER WRITTEN DOWN. So this tool can
       only see sessions from that bake forward; earlier journals have no VWAP
       to read and their absence is not a finding.

WHAT THIS ANSWERS
    Backlog item E proposes a VWAP_FILTER_ACTIVE HARD GATE across the scored
    strategies: short requires price <= VWAP, long requires price >= VWAP.
    This tool asks the only question that should decide it — per strategy, would
    that gate have blocked winners or losers?

WHY PER STRATEGY, NOT FLEET-WIDE
    VWAP alignment is a TREND-FOLLOWING filter. Sweep Reversal is a MEAN-
    REVERSION strategy: it enters counter to an extension by design, so a long
    after a downside sweep is very likely BELOW VWAP at entry. A global gate
    would veto that setup structurally, not occasionally. Continuation is the
    opposite case — alignment is exactly what it wants. One number cannot serve
    both, which is why the output is split by strategy x direction x alignment
    and never aggregated into a single verdict.

THE RULE THIS TOOL OBEYS  (design principle, 2026-07-30)
    Outcomes may FALSIFY, never FIT. This prints evidence that a factor looks
    correctly or incorrectly ORIENTED for a given strategy. It does NOT emit a
    weight, a threshold, or a suggested value, and nothing in the live path
    reads its output. A verdict's only permitted next step is a design review
    whose conclusion must be justifiable on MECHANISM — "this is a trend filter
    on a reversion strategy" — not on the P&L that flagged it.

SAMPLE DISCIPLINE
    Small samples produce spurious signs. Any cell below MIN_CELL is printed as
    INSUFFICIENT and never given a verdict. One good session is not evidence.

USAGE (control server)
    python3 tests/vwap_orientation_ledger.py 2026-07-29
    python3 tests/vwap_orientation_ledger.py 2026-07-27 2026-07-28 2026-07-29
    python3 tests/vwap_orientation_ledger.py --schema 2026-07-29   # discovery only

Read-only. stdlib only. Touches no database and no fleet.
"""

import glob
import json
import os
import sys
from collections import defaultdict
from datetime import datetime

JOURNAL_ROOT = os.path.expanduser("~/day_trader_pro/signal_journal")
REPORTS_ROOT = os.path.expanduser("~/day_trader_pro/reports")
MIN_CELL = 12          # below this a cell gets no verdict, only a count
MIN_ARM_TRADES = 8     # v1.6 — required on EACH arm, not on the total. A
                       # verdict about whether the gate blocks winners or losers
                       # rests entirely on the SMALLER arm.
SNAP_MAX_AGE_S = 120   # a staged_pick may borrow the symbol's last market
                       # snapshot if it is at most this stale (ticks are 15s;
                       # 120s matches the integrator's dt_max gap convention)

# Field-name candidates, most specific first. The journal and trade schemas have
# both drifted over the project's life, so this discovers rather than assumes —
# and prints what it found so a wrong guess is visible instead of silent.
# v1.1 — CANDIDATES MAY BE DOTTED PATHS. The real defect was never three wrong
# names: `_first_key` tested `n in rec`, i.e. TOP-LEVEL keys only, while the
# journal nests these under sections. `readiness.strategy` and `factors.dir` are
# where they actually live, and no flat rename could ever have reached them.
# Fixing the ACCESSOR rather than the names also means the next schema section
# costs one tuple entry instead of another dead tool.
CAND = {
    # v1.2 — VERIFIED AGAINST THE EMITTER, not guessed. `trade_readiness`
    # v1.5 `_journal()` emits ONE section, `readiness=`, containing
    # `market` (from `_market_snapshot`) and `factors` (from the scorer). So
    # everything is TWO levels deep. v1.1 guessed `vwap.vwap` and `factors.dir`
    # and found neither across 39,344 records — the field NAMES were right all
    # along, the DEPTH was wrong, which is why two flat renames and one shallow
    # path all missed.
    "vwap":      ("readiness.market.vwap", "vwap", "vwap_at_entry",
                  "session_vwap"),
    "rel":       ("readiness.market.price_vs_vwap", "price_vs_vwap",
                  "vwap_side", "price_vs_vwap_at_entry"),
    # NOTE: there is NO price field. `_market_snapshot` emits `dist_pct` —
    # signed % from VWAP — which is BETTER than a raw price here because it is
    # comparable across a $30 symbol and a $900 one. `aligned()` works from
    # `rel` alone, so price stays optional.
    "price":     ("readiness.market.dist_pct", "price", "underlying",
                  "underlying_price", "spot", "last"),
    "strategy":  ("readiness.strategy", "strategy", "setup", "strategy_name",
                  "setup_type"),
    # v1.4 — `readiness.factors.dir` is kept as a DISCOVERY candidate but is no
    # longer trusted as THE direction field: it exists on exactly one track
    # (trend_credit_spread). Direction is resolved per strategy by
    # `resolve_direction()` below; this candidate list only feeds the schema
    # printout.
    "direction": ("readiness.factors.dir", "direction", "side", "bias", "dir"),
    "symbol":    ("symbol", "sym", "ticker", "instrument"),
    "event":     ("event", "kind", "type"),
    "ts":        ("ts_et", "ts", "timestamp"),
    "pnl":       ("pnl", "pnl_usd", "realized_pnl", "profit", "pl", "net_pnl"),
}

# ── v1.4: the two vocabularies, mapped instead of hoped equal ────────────────
# Journal side: `readiness.strategy` holds the TradeReadinessEngine track slug
# (STRATEGIES tuple, trade_readiness.py:287). Trade side: the `strategy` column
# holds each class's name() string (strategy/*.py). They have never been the
# same words, so v1.3's (symbol, strategy, direction) join matched nothing.
JOURNAL_FAMILY = {
    "CONTINUATION":        "CONTINUATION",
    "SWEEP":               "SWEEP",
    "CONDOR_CALL":         "CONDOR",
    "CONDOR_PUT":          "CONDOR",
    "BUTTERFLY":           "BUTTERFLY",
    "TREND_CREDIT_SPREAD": "TREND_CREDIT_SPREAD",
}
TRADE_FAMILY = {
    "SWEEPREVERSAL":        "SWEEP",
    "CONTINUATIONSTRATEGY": "CONTINUATION",
    "IRONCONDORSTRATEGY":   "CONDOR",
    "BUTTERFLYSTRATEGY":    "BUTTERFLY",
    # ORB is EXEMPT from the readiness engine by design (v1.0 header), so its
    # trades have no signal population to join. Counted and printed, not lost.
    "ORBSTRATEGY":          None,
    # broker_reconcile adoptions have no signal ancestry at all.
    "ADOPTED":              None,
}


def dig(rec, path):
    """Read a dotted path out of a nested record. None if any hop is missing.

    `rec.get("readiness.strategy")` returns None on a nested dict — silently,
    which is exactly how this tool exited rc=1 for two nights against a schema
    that had never landed flat.
    """
    if not path:
        return None
    cur = rec
    for hop in str(path).split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(hop)
        if cur is None:
            return None
    return cur


def _first_key(rec, names):
    for n in names:
        if dig(rec, n) is not None:
            return n
    return None


def discover(records, want):
    """Map logical field -> actual key, from real records."""
    found = {}
    for logical in want:
        for rec in records:
            k = _first_key(rec, CAND[logical])
            if k:
                found[logical] = k
                break
    return found


def load_journal(dates):
    recs = []
    for d in dates:
        for path in sorted(glob.glob(os.path.join(JOURNAL_ROOT, d, "*.jsonl"))):
            sym = os.path.basename(path).split(".")[0]
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:      # noqa: BLE001 — a half-flushed tail line
                        continue
                    r.setdefault("_sym", sym)
                    r.setdefault("_date", d)
                    recs.append(r)
    return recs


def load_trades(dates):
    out = []
    for d in dates:
        p = os.path.join(REPORTS_ROOT, f"fleet_trades_{d}.json")
        if not os.path.isfile(p):
            continue
        try:
            data = json.load(open(p, encoding="utf-8"))
        except Exception as exc:           # noqa: BLE001
            print(f"  ! could not read {p}: {exc}")
            continue
        rows = data if isinstance(data, list) else (
            data.get("trades") or data.get("rows") or [])
        if isinstance(rows, dict):
            rows = list(rows.values())
        for r in rows:
            if isinstance(r, dict):
                r.setdefault("_date", d)
                out.append(r)
    return out


def _parse_ts(v):
    try:
        return datetime.fromisoformat(str(v)).timestamp()
    except Exception:                      # noqa: BLE001
        return None


def _norm_dir(v):
    d = str(v or "").upper()
    if d.startswith("L"):
        return "LONG"
    if d.startswith("S") and not d.startswith("SIDE"):
        return "SHORT"
    return None


_SRC = {"emitted": 0, "derived": 0}   # v1.5 — era provenance, printed below
# v1.6 (VW.1f-b) — PER-TRACK provenance. v1.5 warned "MIXED ERAS" whenever the
# TOTALS held both, and on its first real run that fired against three
# all-pre-bake dates: the 9,596 "emitted" was EXACTLY TCS's own total, because
# TCS is the one track that always carried `dir`. The split was BY TRACK, not by
# date, and the warning told the operator to "split the dates at the bake" when
# no bake was in range. An alarm that cries wolf on its first outing is the
# thing this project keeps paying for. A genuine era mix shows up as a SINGLE
# TRACK holding both.
_SRC_BY_TRACK = defaultdict(lambda: {"emitted": 0, "derived": 0})


def resolve_direction(track, rec):
    """(direction, undecidable_cause) for one readiness record.

    v1.4 — direction is a PER-TRACK property, not a field. Only
    trend_credit_spread journals `factors.dir`; the rest are resolved the same
    way the emitter itself resolves them in `_staged_pick`:
      continuation  — from `factors.label` (TRENDING_BULL -> LONG,
                      TRENDING_BEAR -> SHORT; trade_readiness.py:763). Outside
                      a trending label the track is hard-vetoed to r=0 and has
                      no intended side this tick — undecidable is the truth.
      condor sides  — ON MECHANISM: a call CREDIT is sold ABOVE and profits if
                      price stays below it (short exposure); a put credit is
                      the mirror (long). NOTE this is the OPPOSITE of the
                      option-buyer call=long/put=short reading — passing the
                      raw `side` through aligned() would have silently
                      inverted every condor row.
      butterfly     — neutral BY DESIGN; never decidable, counted as such.
      sweep         — direction is NOT journaled on readiness rows (it lives in
                      ctx.liq_map, trade_readiness.py:754). It IS journaled on
                      `readiness_staged_pick` rows as `staged.direction`; those
                      are handled by the caller via snapshot pairing.
    """
    t = str(track or "").upper()
    # v1.5 — PREFER THE EMITTED FIELD. trade_readiness v1.6 stamps `dir` on
    # every track, from sources an offline tool cannot reach (sweep's direction
    # lives in ctx.liq_map and was never written down before). Post-bake rows
    # are therefore read, not inferred. The derivations below are KEPT, not
    # replaced: every session banked before that bake has no `dir` to read, and
    # a fleet-side change can never reach history. "neutral" is a real answer —
    # butterfly is sideless by design — and is distinguished here from "".
    _emitted = dig(rec, "readiness.factors.dir")
    if _emitted is not None:
        _SRC["emitted"] += 1
        _SRC_BY_TRACK[str(track or "?").upper()]["emitted"] += 1
        if str(_emitted).upper() == "NEUTRAL":
            return None, f"{t.lower()}: neutral by design (emitted)"
        d = _norm_dir(_emitted)
        if d:
            return d, None
        # An emitted "" means the track had NO intended side this tick — an
        # honest absence, and a different fact from the field being missing.
        return None, f"{t.lower()}: no intended side this tick (emitted empty)"
    _SRC["derived"] += 1
    _SRC_BY_TRACK[t]["derived"] += 1
    if t == "TREND_CREDIT_SPREAD":
        d = _norm_dir(dig(rec, "readiness.factors.dir"))
        return (d, None) if d else (None, "tcs: factors.dir unparseable")
    if t == "CONTINUATION":
        label = str(dig(rec, "readiness.factors.label") or "").upper()
        if label.endswith("TRENDING_BULL"):
            return "LONG", None
        if label.endswith("TRENDING_BEAR"):
            return "SHORT", None
        return None, "continuation: non-trending label, no intended side"
    if t == "CONDOR_CALL":
        return "SHORT", None
    if t == "CONDOR_PUT":
        return "LONG", None
    if t == "BUTTERFLY":
        return None, "butterfly: neutral by design"
    if t == "SWEEP":
        return None, "sweep: dir not on readiness rows (staged picks only)"
    return None, "unknown track: no direction rule"


def aligned(rel, direction, vwap, price):
    """True when the E gate would PERMIT this entry.

    Gate as specified: long requires price >= VWAP, short requires price <= VWAP.
    Returns None when undecidable — notably price_vs_vwap == "NONE", the cash-index
    case from the 2026-07-17 zero-volume fix, where the gate is specified inert.
    v1.4 — direction arrives pre-resolved as LONG/SHORT from
    `resolve_direction()`. The CALL/PUT branch is retained for raw trade-row
    input only; NEVER feed a credit-spread side through it — a call credit is
    SHORT exposure, the inverse of what this buyer's-eye reading assumes.
    """
    d = (direction or "").upper()
    is_long = d.startswith("L") or "BULL" in d or d == "CALL"
    is_short = (d.startswith("S") and not d.startswith("SIDE")) \
        or "BEAR" in d or d == "PUT"
    if not (is_long or is_short):
        return None
    if rel:
        r = str(rel).upper()
        if r in ("NONE", "", "UNKNOWN"):
            return None
        if r.startswith("ABOVE"):
            return True if is_long else False
        if r.startswith("BELOW"):
            return False if is_long else True
        return None
    try:
        if vwap in (None, 0) or price is None:
            return None
        return (price >= vwap) if is_long else (price <= vwap)
    except Exception:                      # noqa: BLE001
        return None


def _trade_group(t, tmap):
    """(symbol, family, direction) for one trade row, or (None, reason)."""
    sym = str(dig(t, tmap.get("symbol")) or "").upper()
    raw_strat = str(dig(t, tmap.get("strategy")) or "").upper()
    fam = TRADE_FAMILY.get(raw_strat, "UNMAPPED")
    if fam is None:
        return None, ("orb: no readiness track by design"
                      if raw_strat == "ORBSTRATEGY" else
                      "adopted: no signal ancestry")
    if fam == "UNMAPPED":
        return None, f"unmapped trade strategy: {raw_strat or '(empty)'}"
    direc = _norm_dir(dig(t, tmap.get("direction")))
    if direc is None and fam == "CONDOR":
        # Condor trade rows say direction="neutral"; the leg is recoverable
        # from setup_type ("... Call Credit" / "... Put Credit") and maps to
        # the side's exposure exactly as resolve_direction does.
        st = str(t.get("setup_type") or "").upper()
        if "CALL" in st:
            direc = "SHORT"
        elif "PUT" in st:
            direc = "LONG"
    if direc is None:
        return None, f"{fam.lower()}: direction unresolvable"
    return (sym, fam, direc), None


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    schema_only = "--schema" in argv
    if not args:
        print(__doc__.strip().split("USAGE")[1].strip())
        return 2

    jrecs = load_journal(args)
    trades = load_trades(args)
    print(f"dates: {', '.join(args)}")
    print(f"journal records: {len(jrecs)}   trade rows: {len(trades)}")
    if not jrecs:
        print("\nNo journal records found. Expected "
              f"{JOURNAL_ROOT}/<date>/<SYM>.jsonl — is the date harvested?")
        return 1

    jmap = discover(jrecs, ("vwap", "rel", "price", "strategy",
                            "direction", "symbol", "event", "ts"))
    tmap = discover(trades, ("strategy", "direction", "symbol", "pnl")) if trades else {}
    print("\n--- discovered journal fields ---")
    for k in ("event", "symbol", "strategy", "direction", "vwap", "rel", "price"):
        print(f"    {k:<10} -> {jmap.get(k) or '(NOT FOUND)'}")
    print("    (direction is resolved PER STRATEGY — see DIRECTION COVERAGE)")
    if trades:
        print("--- discovered trade fields ---")
        for k in ("symbol", "strategy", "direction", "pnl"):
            print(f"    {k:<10} -> {tmap.get(k) or '(NOT FOUND)'}")
    if schema_only:
        return 0

    missing = [k for k in ("rel",) if k not in jmap]
    if missing and "vwap" not in jmap:
        print(f"\nCannot proceed: no VWAP-side field found ({missing}). "
              "Add the real key name to CAND at the top of this file.")
        return 1

    # ── outcomes keyed by (symbol, FAMILY, direction) ───────────────────────
    pnl_by = defaultdict(list)
    trades_dropped = defaultdict(int)
    if trades and tmap.get("pnl"):
        for t in trades:
            key, why = _trade_group(t, tmap)
            if key is None:
                trades_dropped[why] += 1
                continue
            try:
                pnl_by[key].append(float(dig(t, tmap["pnl"]) or 0.0))
            except Exception:              # noqa: BLE001
                pass

    # ── SIGNAL-level alignment, then TRADE-level P&L attributed ONCE ────────
    # v1.0 note: an early cut summed every matching trade into every matching
    # signal, inflating P&L by the signal count. Each trade is now counted once.
    # Journal rows carry no trade id, so a trade inherits the MAJORITY alignment
    # of its (symbol, family, direction) group — an approximation, and labelled
    # as one. It is sound for a per-strategy orientation read and NOT sound for
    # anything that needs per-trade precision.
    sig = defaultdict(lambda: {"aligned": 0, "misaligned": 0})
    undecidable = defaultdict(int)
    coverage = defaultdict(lambda: {"decided": 0, "undecided": 0})
    last_snap = {}   # _sym -> (epoch, rel, vwap, dist_pct): staged-pick pairing
    for r in jrecs:
        # v1.3 — THE EVENT FILTER WAS THE LAST LAYER, and it silently discarded
        # everything that matters. It accepted only ("scored","fired","entry",
        # "entered") — names from before `trade_readiness` v1.5 existed. The
        # journal's readiness events are `readiness`, `readiness_would_fire` and
        # `readiness_staged_pick`, and ONLY THOSE carry `readiness.market`.
        # Prefix-matched rather than enumerated: `readiness_*` is a growing
        # family and an exact list is what put this tool three versions behind
        # its own emitter.
        _ev = str(dig(r, jmap["event"]) or "").lower() if jmap.get("event") else ""
        if _ev and not (_ev.startswith("readiness")
                        or _ev in ("scored", "fired", "entry", "entered")):
            continue
        sym = str(r.get("_sym", "")).upper()
        ts = _parse_ts(dig(r, jmap.get("ts")))

        # v1.4 — remember each symbol's latest market snapshot so staged picks
        # (which carry direction but NO market section) can borrow it. File
        # order is append order per symbol, so "last seen" is time order.
        rel_here = dig(r, jmap.get("rel"))
        if rel_here is not None:
            last_snap[sym] = (ts, rel_here, dig(r, jmap.get("vwap")),
                              dig(r, jmap.get("price")))

        if _ev == "readiness_staged_pick":
            # SWEEP's only direction carrier (continuation picks also land
            # here, harmlessly — their readiness rows already decide).
            track = str(dig(r, "staged.strategy") or "").upper()
            if track != "SWEEP":
                continue
            direc = _norm_dir(dig(r, "staged.direction"))
            if direc is None:
                undecidable["staged_pick: direction unparseable"] += 1
                coverage[track]["undecided"] += 1
                continue
            snap = last_snap.get(sym)
            fresh = (snap is not None
                     and (ts is None or snap[0] is None
                          or abs(ts - snap[0]) <= SNAP_MAX_AGE_S))
            if not fresh:
                undecidable["sweep staged_pick: no fresh market snapshot"] += 1
                coverage[track]["undecided"] += 1
                continue
            ok = aligned(snap[1], direc, snap[2], snap[3])
            if ok is None:
                undecidable["NONE side (index, gate inert by spec)"] += 1
                coverage[track]["undecided"] += 1
                continue
            coverage[track]["decided"] += 1
            sig[(sym, "SWEEP", direc)]["aligned" if ok else "misaligned"] += 1
            continue

        track = str(dig(r, jmap.get("strategy")) or "UNKNOWN").upper()
        fam = JOURNAL_FAMILY.get(track, track)
        direc, cause = resolve_direction(track, r)
        if direc is None:
            undecidable[cause] += 1
            coverage[track]["undecided"] += 1
            continue
        ok = aligned(rel_here, direc,
                     dig(r, jmap.get("vwap")), dig(r, jmap.get("price")))
        if ok is None:
            undecidable["NONE side (index, gate inert by spec)"] += 1
            coverage[track]["undecided"] += 1
            continue
        coverage[track]["decided"] += 1
        sig[(sym, fam, direc)]["aligned" if ok else "misaligned"] += 1

    # v1.6 (VW.1f-a) — TRADES THAT MAP BUT NEVER MATCH WERE VANISHING. The
    # first real run joined 235 of 264 mappable rows and the other ~29 left NO
    # LINE ANYWHERE: they resolved to a family fine, so `_trade_group` accepted
    # them, but their (symbol, family, direction) key had no signal group to
    # land in. "not joinable BY CAUSE" therefore reported 40 and stayed silent
    # about the rest — the exact gap by-cause reporting was built to close.
    _matched_keys = set()

    cells = defaultdict(lambda: {"n": 0, "trades": 0, "wins": 0, "pnl": 0.0})
    for key, counts in sig.items():
        _, fam, direc = key
        al = "ALIGNED" if counts["aligned"] >= counts["misaligned"] else "MISALIGNED"
        c = cells[(fam, direc, al)]
        c["n"] += counts["aligned"] + counts["misaligned"]
        if key in pnl_by:
            _matched_keys.add(key)
        for v in pnl_by.get(key, []):        # each trade consumed exactly once
            c["trades"] += 1
            c["pnl"] += v
            c["wins"] += 1 if v > 0 else 0

    print("\n--- DIRECTION COVERAGE (per track: decided / undecided) ---")
    for track in sorted(coverage):
        cv = coverage[track]
        print(f"    {track:<22} {cv['decided']:>7} / {cv['undecided']}")
    # v1.5 — THE ERA SPLIT, printed because pooling across it is the standing
    # hazard. Rows from before the trade_readiness v1.6 bake have no `dir` and
    # are DERIVED; rows after it are READ. The two are not the same measurement
    # — sweep in particular is only decidable post-bake on ordinary readiness
    # rows — so a mixed run silently changes basis partway through. Naming the
    # mix is cheaper than a caveat nobody reads.
    src_emitted, src_derived = _SRC["emitted"], _SRC["derived"]
    if src_emitted or src_derived:
        print(f"    [era] direction READ from the emitter: {src_emitted}  |  "
              f"DERIVED offline (pre-v1.6 rows): {src_derived}")
        _mixed = sorted(k for k, v in _SRC_BY_TRACK.items()
                        if v["emitted"] and v["derived"])
        if _mixed:
            print(f"    ⚠ MIXED ERAS — these tracks hold BOTH: {', '.join(_mixed)}")
            print("      A single track reading two ways IS a date mix. Split the")
            print("      dates at the bake before reading its counts as a trend.")
        elif src_emitted and src_derived:
            print("    (no track holds both — the emitted/derived split is BY TRACK,")
            print("     not by date. TCS always carried `dir`; the rest did not until")
            print("     the v1.6 bake. Not an era mix, no action.)")
    print("--- undecidable, BY CAUSE ---")
    for cause in sorted(undecidable):
        print(f"    {undecidable[cause]:>7}  {cause}")
    if trades_dropped:
        print("--- trade rows not joinable, BY CAUSE ---")
        for why in sorted(trades_dropped):
            print(f"    {trades_dropped[why]:>7}  {why}")
    _orphan = {k: v for k, v in pnl_by.items() if k not in _matched_keys}
    if _orphan:
        _n = sum(len(v) for v in _orphan.values())
        print(f"--- trade rows MAPPED BUT UNMATCHED: {_n} ---")
        print("    these resolved to a family but their (symbol, family, direction)")
        print("    key had NO signal group — so they are neither joined nor reported")
        print("    as unjoinable. v1.5 dropped them silently.")
        for k in sorted(_orphan, key=lambda x: -len(_orphan[x]))[:8]:
            print(f"    {len(_orphan[k]):>7}  {k[0]} {k[1]} {k[2]}")

    print("\n" + "=" * 74)
    print("  WOULD THE E GATE HAVE BLOCKED WINNERS OR LOSERS?  (per strategy)")
    print("=" * 74)
    print(f"  {'STRATEGY':<20}{'DIR':<6}{'ALIGNMENT':<12}"
          f"{'SIGNALS':>8}{'TRADES':>7}{'WINS':>6}{'P&L':>11}")
    for (fam, direc, al), c in sorted(cells.items()):
        print(f"  {fam:<20}{direc:<6}{al:<12}{c['n']:>8}{c['trades']:>7}"
              f"{c['wins']:>6}{c['pnl']:>11.2f}")
    print("  (trades inherit their group's majority alignment — approximate, "
          "sound for orientation, not for per-trade precision)")

    print("\n" + "-" * 74)
    print("  ORIENTATION READ  (falsification only — no weights suggested)")
    print("-" * 74)
    strategies = sorted({s for s, _, _ in cells})
    for strat in strategies:
        a = sum(c["n"] for (s, _, al), c in cells.items()
                if s == strat and al == "ALIGNED")
        m = sum(c["n"] for (s, _, al), c in cells.items()
                if s == strat and al == "MISALIGNED")
        apnl = sum(c["pnl"] for (s, _, al), c in cells.items()
                   if s == strat and al == "ALIGNED")
        mpnl = sum(c["pnl"] for (s, _, al), c in cells.items()
                   if s == strat and al == "MISALIGNED")
        tr = sum(c["trades"] for (s2, _, _), c in cells.items() if s2 == strat)
        if strat == "TREND_CREDIT_SPREAD" and tr == 0:
            print(f"  {strat:<22} {a + m} signals, 0 trades — EXPECTED: its "
                  "firing engine (vertical_spread_strategy.py, TC.4) does not "
                  "exist yet. Signal-side orientation only.")
        # v1.6 (VW.1f-c) — THE FLOOR MUST HOLD ON BOTH ARMS. v1.5 tested
        # TOTAL trades >= 3, so the first real run printed
        # "orientation looks right" for CONTINUATION off a MISALIGNED arm of
        # FIVE trades against an aligned arm of 228. A verdict rests on the
        # SMALLER arm; a floor on the total does not constrain it at all.
        # Compounding it, the per-group MAJORITY-ALIGNMENT collapse
        # systematically SHRINKS the minority arm — so the method minimises the
        # very population the verdict depends on, and that is stated below
        # rather than left for the reader to infer.
        _tr_a = sum(c["trades"] for (s2, _, al), c in cells.items()
                    if s2 == strat and al == "ALIGNED")
        _tr_m = sum(c["trades"] for (s2, _, al), c in cells.items()
                    if s2 == strat and al == "MISALIGNED")
        if a + m < MIN_CELL or min(_tr_a, _tr_m) < MIN_ARM_TRADES:
            print(f"  {strat:<22} INSUFFICIENT (signals {a + m}; trades "
                  f"aligned {_tr_a} / misaligned {_tr_m}, need "
                  f"{MIN_ARM_TRADES} on EACH) — no verdict")
            continue
        if mpnl > 0 and mpnl >= apnl:
            print(f"  {strat:<22} GATE WOULD HAVE BLOCKED NET WINNERS "
                  f"(misaligned P&L {mpnl:+.2f} vs aligned {apnl:+.2f}) "
                  f"-> orientation looks WRONG for this strategy")
        elif mpnl < 0:
            print(f"  {strat:<22} gate would have blocked net losers "
                  f"(misaligned P&L {mpnl:+.2f}) -> orientation looks right")
        else:
            print(f"  {strat:<22} inconclusive "
                  f"(aligned {apnl:+.2f} / misaligned {mpnl:+.2f})")

    print("\n  Reminder: a verdict here licenses a DESIGN REVIEW, not a dial.")
    print("  Any change must be defensible on mechanism, not on this P&L.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
