#!/usr/bin/env python3
"""
tests/conditional_tables.py — v1.6 — Conditional-probability tables from the

v1.6 — 2026-08-05 — DE-DUPLICATION. Each box's `trades.db` is CUMULATIVE, so a
  harvest that copies the whole file into every dated folder reproduces the same
  trade once per subsequent folder. This tool de-duplicated NOTHING — `trade_id`
  was not even in the SELECT. `trade_report` has been collapsing 1112 rows to
  388 unique for weeks; this tool was reading the 1112.
  WHY IT IS WORSE THAN INFLATED TOTALS: n drives the Wilson interval. A 3x
  duplication makes every interval about 1.7x too NARROW, so cells look decisive
  when they are not — and the 2026-08-05 read of
  `ORBStrategy x A [53%,61%]` vs `x B [37%,45%]` as NON-OVERLAPPING was made on
  exactly that inflated n.
  Rows without a `trade_id` fall back to a composite key rather than being
  dropped: a systematically id-less strategy would otherwise vanish from the
  tables entirely.
  THIS IS THE CONSUMER-SIDE GUARD ONLY. The source is the harvest, and the tool
  now says so out loud when duplication exceeds 25%.
v1.5 — 2026-08-05 — TWO FIXES, BOTH ABOUT SILENT ZEROS.
  (a) THE GLOB HAD NEVER MATCHED ANYTHING. Harvested files are named
      `<SYM>_trades_<date>.db`; this globbed `*_trades.db`, which requires the
      name to END in `_trades.db`. `excursion_report` hit the identical bug and
      documented it — "every consumer that globbed `*_trades_<date>.db`
      correctly; this file was the outlier" — and the fix was never carried
      across. Now `*_trades*.db`, which matches both spellings.
  (b) AN EMPTY LOAD NOW REFUSES LOUDLY. On 2026-08-05 a manual run printed
      "0 closed trades / 10 session(s) · no cell separated from chance yet"
      while the conductor's run of the same tool found 717 — a confident verdict
      on an empty corpus. A null result and a failed load must not share a
      sentence, least of all in the tool the Aug 8-9 calibration fits are read
      from. Exits rc=2 and names the cause.
v1.4 — 2026-08-05 — session spread on every cell (see Cell.spread_flag).
        fleet's own record: P(win), fee-adjusted expectancy, and sample counts
        per conditioning cell. The empirical substrate for placing the L3
        conviction bars (ROADMAP Phase 3): a bar belongs at the fee-adjusted-ROI
        zero crossing of exactly these cells.
v1.1 — 2026-07-23 — CONDUCTOR MODE. Adds --quiet: prints ONE headline line to
        stdout (the reports are still written in full to disk), so
        eod_conductor.py can capture it the same way it captures the excursion
        headline. The headline is deliberately honest — it names the best cell
        ONLY when that cell's Wilson 95% lower bound clears 50%, and the worst
        ONLY when its upper bound falls below 50%; otherwise it says no cell has
        separated from chance yet. Early sessions will say exactly that, and
        that is the correct output, not a failure. Also --min-n now applies to
        headline eligibility, and exit code is 0 whenever the report was written
        (an empty-but-valid day is not an error) so a quiet night can never mark
        the EOD chain as failed.
v1.0 — 2026-07-23 — initial. OFFLINE, control-server, stdlib-only (sqlite3 +
        json). Reads what already lands on 1-REPORTER; touches NO bot code and
        does not disturb the frozen baseline window.

        TWO SOURCES, each optional, both if present:

        (1) TRADES MODE (works tonight): per-symbol snapshot DBs at
            ~/day_trader_pro/trades/<date>/<SYMBOL>_<date>_trades.db
            (the EOD chain's product). Closed trades only. Dimensions:
            regime label x strategy x grade x direction x time bucket x
            VIX band x condor-leg flag. Emits one-dim marginals, the useful
            two-dim crosses, and full-tuple cells above --min-n.

        (2) JOURNAL MODE (matures once the jsonl harvest lands — the 07-18
            decision deferred wiring data/signal_journal/ into the EOD chain):
            <journal_root>/<date>/<SYM>.jsonl. Uses `scored` + `disposition`
            events: fire rate, grade distribution, and REJECT share by regime
            label and conviction decile — the counterfactual side the DBs
            cannot see ("a gate you can't counterfactual is a gate you can't
            calibrate").

        Honesty guards: Wilson 95% interval printed next to every P(win) so a
        7-sample 71% cell reads as the noise it is; cells below --min-n are
        suppressed from the cross tables (marginals always print with n).
        Fees default to $0 round-trip per contract (paper); set
        CT_FEES_RT_PER_CONTRACT to make expectancy fee-adjusted.

        Usage (control server):
          python3 -m tests.conditional_tables                      # all dates on disk
          python3 -m tests.conditional_tables --since 2026-07-20   # window
          python3 -m tests.conditional_tables --date 2026-07-22    # one day
          python3 -m tests.conditional_tables --quiet              # headline only
          CT_FEES_RT_PER_CONTRACT=1.30 python3 -m tests.conditional_tables
        Output: reports/conditional_tables_<first>_<last>.txt (+ .jsonl cells)
        under --reports-dir (default ~/day_trader_pro/reports).
"""

import argparse
import glob
import json
import math
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime

TRADES_ROOT_DEFAULT  = os.path.expanduser("~/day_trader_pro/trades")
JOURNAL_ROOT_DEFAULT = os.path.expanduser("~/day_trader_pro/signal_journal")
REPORTS_DIR_DEFAULT  = os.path.expanduser("~/day_trader_pro/reports")

FEES_RT = float(os.environ.get("CT_FEES_RT_PER_CONTRACT", "0.0"))

# ── dimension extractors ─────────────────────────────────────────────────────

def time_bucket(entry_time: str) -> str:
    """ET session bucket from the stored entry_time text (None-safe)."""
    if not entry_time:
        return "unknown"
    try:
        t = entry_time.strip().replace("T", " ")
        hhmm = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%H:%M:%S"):
            try:
                hhmm = datetime.strptime(t.split("+")[0].split(".")[0], fmt)
                break
            except ValueError:
                continue
        if hhmm is None:
            return "unknown"
        m = hhmm.hour * 60 + hhmm.minute
        if m < 9 * 60 + 30:   return "premarket"
        if m < 10 * 60 + 30:  return "0930-1030"
        if m < 11 * 60 + 30:  return "1030-1130"
        if m < 13 * 60:       return "1130-1300"
        if m < 14 * 60:       return "1300-1400"
        if m < 15 * 60 + 45:  return "1400-1545"
        return "1545+"
    except Exception:
        return "unknown"


def vix_band(v) -> str:
    try:
        v = float(v or 0.0)
    except (TypeError, ValueError):
        return "unknown"
    if v <= 0:  return "unknown"
    if v < 15:  return "vix<15"
    if v < 20:  return "vix15-20"
    if v < 27:  return "vix20-27"
    return "vix27+"


def conviction_decile(c) -> str:
    try:
        c = max(0.0, min(1.0, float(c)))
    except (TypeError, ValueError):
        return "unknown"
    lo = int(c * 10) * 10
    if lo == 100:
        lo = 90
    return f"conv{lo:02d}-{lo + 10:02d}"


def wilson(p_hat: float, n: int, z: float = 1.96):
    """Wilson 95% score interval — the honest error bar for small cells."""
    if n == 0:
        return (0.0, 1.0)
    denom  = 1.0 + z * z / n
    centre = (p_hat + z * z / (2 * n)) / denom
    half   = (z / denom) * math.sqrt(p_hat * (1 - p_hat) / n + z * z / (4 * n * n))
    return (max(0.0, centre - half), min(1.0, centre + half))


# ── trades mode ──────────────────────────────────────────────────────────────

TRADE_COLS = ("trade_id,symbol,strategy,setup_type,setup_grade,direction,regime,"
              "vix_at_entry,is_condor_leg,contracts,pnl_usd,entry_time,"
              "exit_reason,paper_trade")


def _dedup_key(t: dict):
    """Identity of a trade, for de-duplication across date folders.

    `trade_id` when present. A row without one falls back to a composite of the
    fields that cannot collide for two genuinely different trades — DROPPING it
    would be worse than double-counting, because a systematically id-less
    strategy would vanish from the tables entirely.
    """
    tid = t.get("trade_id")
    if tid:
        return ("id", tid)
    return ("composite", t.get("symbol"), t.get("entry_time"),
            t.get("exit_reason"), t.get("pnl_usd"), t.get("contracts"))


def load_trades(trades_root: str, dates):
    """Read every closed row from each box's per-day DB.

    v1.5 — THE GLOB WAS WRONG AND HAD NEVER MATCHED ANYTHING. Harvested files
    are named `<SYM>_trades_<date>.db`, and `*_trades.db` requires the name to
    END in `_trades.db` — so this matched ZERO files. `excursion_report` hit the
    identical bug and documented it ("every consumer that globbed
    `*_trades_<date>.db` correctly; this file was the outlier"); the fix was
    never carried across to here.
    `*_trades*.db` matches both spellings, so a future rename in either
    direction does not silently empty the corpus again.
    """
    rows, seen, dup = [], set(), 0
    for d in dates:
        for db in sorted(glob.glob(os.path.join(trades_root, d, "*_trades*.db"))):
            try:
                con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
                cur = con.execute(
                    f"SELECT {TRADE_COLS} FROM trades "
                    "WHERE pnl_usd IS NOT NULL AND exit_reason IS NOT NULL")
                for r in cur.fetchall():
                    t = dict(zip(TRADE_COLS.split(","), r), _date=d)
                    k = _dedup_key(t)
                    if k in seen:
                        dup += 1
                        continue
                    seen.add(k)
                    rows.append(t)
                con.close()
            except sqlite3.Error as e:
                print(f"  warn: {os.path.basename(db)}: {e}", file=sys.stderr)
    return rows, dup


def trade_dims(t: dict) -> dict:
    return {
        "regime":   (t.get("regime") or "unknown"),
        "strategy": (t.get("strategy") or t.get("setup_type") or "unknown"),
        "grade":    (t.get("setup_grade") or "unknown"),
        "direction": (t.get("direction") or "unknown"),
        "bucket":   time_bucket(t.get("entry_time")),
        "vix":      vix_band(t.get("vix_at_entry")),
        "condor_leg": "leg" if t.get("is_condor_leg") else "single",
    }


class Cell:
    # v1.4 — `dates` is not decoration. Without it a cell reports n=48 with a
    # confidence interval and NO WAY TO SEE that all 48 came from two sessions.
    # The 2026-08-05 headline named BREAKOUT_VOLATILE x ORBStrategy x B at n=48,
    # P(win) 25%, interval excluding 50% — a starve candidate on its face, and
    # the tool could not say whether it was a standing pattern or two bad days.
    # trade_report and excursion_report both carry a SESSION SPREAD block for
    # exactly this; the conditional table, which is the tool a DISABLE decision
    # would actually be read from, did not.
    __slots__ = ("n", "wins", "pnl", "dates")

    def __init__(self):
        self.n, self.wins, self.pnl = 0, 0, 0.0
        self.dates = defaultdict(int)

    def add(self, net, date=""):
        self.n += 1
        self.wins += 1 if net > 0 else 0
        self.pnl += net
        if date:
            self.dates[date] += 1

    @property
    def sessions(self) -> int:
        return len(self.dates)

    @property
    def top_share(self) -> float:
        """Fraction of the cell contributed by its single busiest date."""
        return (max(self.dates.values()) / self.n) if self.n and self.dates else 0.0

    def spread_flag(self) -> str:
        """The warning a reader needs BEFORE acting on this cell.

        Deliberately mirrors the excursion report's wording: an underpowered or
        concentrated cell is an ABSENT MEASUREMENT, not a null result. A cell
        that is 80%+ one date is a one-day event wearing a multi-session label.
        """
        if self.sessions < 3:
            return f"  <- {self.sessions} SESSION(S), not a standing pattern"
        if self.top_share >= 0.80:
            return f"  <- SINGLE-SESSION ({self.top_share:.0%} on one date)"
        return ""


TRADE_GROUPINGS = [
    ("regime",),
    ("strategy",),
    ("grade",),
    ("bucket",),
    ("vix",),
    ("condor_leg",),
    ("regime", "strategy"),
    ("strategy", "grade"),
    ("strategy", "bucket"),
    ("regime", "bucket"),
    ("regime", "strategy", "grade"),
]


def build_trade_tables(rows):
    tables = {g: defaultdict(Cell) for g in TRADE_GROUPINGS}
    for t in rows:
        try:
            net = float(t["pnl_usd"]) - FEES_RT * float(t.get("contracts") or 0)
        except (TypeError, ValueError):
            continue
        d = trade_dims(t)
        for g in TRADE_GROUPINGS:
            tables[g][tuple(d[k] for k in g)].add(net, (t.get("entry_time") or "")[:10])
    return tables


# ── journal mode ─────────────────────────────────────────────────────────────

def load_journal(journal_root: str, dates):
    """scored/disposition counters keyed by (regime label, conviction decile)."""
    scored  = defaultdict(lambda: defaultdict(int))   # key -> grade -> n
    fired   = defaultdict(int)
    reject  = defaultdict(int)                        # sizing_rejected+invalid
    total_events = 0
    for d in dates:
        for jf in sorted(glob.glob(os.path.join(journal_root, d, "*.jsonl"))):
            try:
                with open(jf, encoding="utf-8") as fh:
                    for line in fh:
                        try:
                            ev = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        total_events += 1
                        reg = ev.get("regime") or {}
                        key = ((reg.get("label") or "unknown"),
                               conviction_decile(reg.get("conviction")))
                        kind = ev.get("event") or ev.get("kind") or ""
                        if kind == "scored":
                            grade = ((ev.get("score") or {}).get("grade")
                                     or "REJECT")
                            scored[key][grade] += 1
                        elif kind == "disposition":
                            out = ev.get("outcome") or ""
                            if out == "fired":
                                fired[key] += 1
                            elif out in ("sizing_rejected", "invalid_signal"):
                                reject[key] += 1
            except OSError as e:
                print(f"  warn: {os.path.basename(jf)}: {e}", file=sys.stderr)
    return scored, fired, reject, total_events


# ── report ───────────────────────────────────────────────────────────────────

def fmt_cell(key, c: Cell) -> str:
    p = c.wins / c.n if c.n else 0.0
    lo, hi = wilson(p, c.n)
    exp = c.pnl / c.n if c.n else 0.0
    name = " × ".join(key)
    return (f"  {name:<46} n={c.n:<4} sess={c.sessions:<3} P(win)={p:5.1%} "
            f"[{lo:4.0%},{hi:4.0%}]  E[net]=${exp:8.2f}  Σ=${c.pnl:9.2f}"
            f"{c.spread_flag()}")


def build_headline(dates, rows, tables, min_n):
    """One honest line. Names a cell ONLY when its Wilson 95% interval clears
    50% — otherwise it reports that nothing has separated from chance, which is
    the expected (and correct) answer for the first weeks of sample.

    v1.4 — the line now carries SESSION COUNT and a concentration flag. The
    Wilson interval answers "is this distinguishable from chance", which is a
    question about n. It says nothing about whether the n came from eight
    sessions or two, and a cell drawn from two days is a fact about those days.
    Both questions have to be answered before a cell can justify DISABLING a
    combination, and this line is where that decision gets read from.
    """
    base = f"CT: {len(rows)} closed trades / {len(dates)} session(s)"
    best = worst = None
    for g in TRADE_GROUPINGS:
        for key, c in tables[g].items():
            if c.n < min_n:
                continue
            p = c.wins / c.n
            lo, hi = wilson(p, c.n)
            exp = c.pnl / c.n
            label = " × ".join(key)
            if lo > 0.50 and (best is None or exp > best[0]):
                best = (exp, f"{label} n={c.n} sess={c.sessions} "
                             f"P(win)={p:.0%} [{lo:.0%},{hi:.0%}] "
                             f"E=${exp:,.2f}{c.spread_flag()}")
            if hi < 0.50 and (worst is None or exp < worst[0]):
                worst = (exp, f"{label} n={c.n} sess={c.sessions} "
                              f"P(win)={p:.0%} [{lo:.0%},{hi:.0%}] "
                              f"E=${exp:,.2f}{c.spread_flag()}")
    parts = [base]
    if best:
        parts.append(f"best: {best[1]}")
    if worst:
        parts.append(f"worst: {worst[1]}")
    if not best and not worst:
        parts.append(f"no cell separated from chance yet (min-n={min_n})")
    return " · ".join(parts)


def write_report(out_txt, out_jsonl, dates, rows, tables,
                 journal_stats, min_n):
    lines = []
    push = lines.append
    push("=" * 78)
    push(f"CONDITIONAL TABLES — {dates[0]} → {dates[-1]}  "
         f"({len(dates)} session(s), {len(rows)} closed trades, "
         f"fees=${FEES_RT:.2f}/contract RT)")
    push("The L3 bar belongs at the fee-adjusted expectancy zero crossing of")
    push("these cells. Expect most cells ≈ coin flip; the edge is the few that")
    push("persistently are not. Wilson 95% intervals are the honesty check —")
    push("do NOT act on a cell whose interval still straddles 50%.")
    push("=" * 78)

    cells_out = []
    for g in TRADE_GROUPINGS:
        push("")
        push(f"── by {' × '.join(g)} " + "─" * max(1, 60 - 6 * len(g)))
        table = tables[g]
        shown = 0
        for key in sorted(table, key=lambda k: -table[k].n):
            c = table[key]
            if len(g) > 1 and c.n < min_n:
                continue
            push(fmt_cell(key, c))
            shown += 1
            p = c.wins / c.n
            lo, hi = wilson(p, c.n)
            cells_out.append({"group": list(g), "key": list(key), "n": c.n,
                              "p_win": round(p, 4),
                              "wilson95": [round(lo, 4), round(hi, 4)],
                              "expectancy_net": round(c.pnl / c.n, 2),
                              "pnl_net_total": round(c.pnl, 2)})
        if shown == 0:
            push(f"  (all cells below min-n={min_n})")

    scored, fired, reject, total_events = journal_stats
    push("")
    push("── journal (counterfactual side) " + "─" * 44)
    if total_events == 0:
        push("  no journal events found — the signal journal is not harvested")
        push("  off-box yet (deliberate 07-18 deferral). These tables light up")
        push("  automatically once data/signal_journal/<date>/ is pulled to the")
        push("  journal root. The DB tables above cannot see REJECTs; this")
        push("  section is where the counterfactual calibration will live.")
    else:
        push(f"  {total_events} events")
        keys = sorted(set(scored) | set(fired) | set(reject))
        for key in keys:
            grades = scored.get(key, {})
            n_sc = sum(grades.values())
            n_f, n_r = fired.get(key, 0), reject.get(key, 0)
            gtxt = " ".join(f"{g}:{n}" for g, n in sorted(grades.items()))
            push(f"  {key[0]:<18} {key[1]:<12} scored={n_sc:<4} "
                 f"fired={n_f:<4} rejected={n_r:<4} [{gtxt}]")

    push("")
    push("=" * 78)
    text = "\n".join(lines) + "\n"
    os.makedirs(os.path.dirname(out_txt), exist_ok=True)
    with open(out_txt, "w", encoding="utf-8") as fh:
        fh.write(text)
    with open(out_jsonl, "w", encoding="utf-8") as fh:
        for c in cells_out:
            fh.write(json.dumps(c) + "\n")
    return text


def discover_dates(trades_root, journal_root, since, only_date):
    seen = set()
    for root in (trades_root, journal_root):
        if os.path.isdir(root):
            for name in os.listdir(root):
                if len(name) == 10 and name[4] == "-" and name[7] == "-":
                    seen.add(name)
    dates = sorted(seen)
    if only_date:
        dates = [d for d in dates if d == only_date]
    elif since:
        dates = [d for d in dates if d >= since]
    return dates


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--since")
    ap.add_argument("--date")
    ap.add_argument("--trades-root",  default=TRADES_ROOT_DEFAULT)
    ap.add_argument("--journal-root", default=JOURNAL_ROOT_DEFAULT)
    ap.add_argument("--reports-dir",  default=REPORTS_DIR_DEFAULT)
    ap.add_argument("--min-n", type=int, default=5,
                    help="suppress cross-table cells below this sample count")
    ap.add_argument("--quiet", action="store_true",
                    help="print ONLY the headline line (reports still written) "
                         "— this is how eod_conductor.py calls it")
    args = ap.parse_args()

    dates = discover_dates(args.trades_root, args.journal_root,
                           args.since, args.date)
    if not dates:
        # Not an error: a fresh install or a holiday has no dated folders, and
        # the conductor must never be marked failed by a quiet night.
        print(f"CT: no dated folders yet under {args.trades_root}")
        return 0

    rows, dup = load_trades(args.trades_root, dates)
    # v1.6 — THE APPENDING-LOG PROBLEM, MADE VISIBLE. Each box's trades.db is
    # CUMULATIVE, so a harvest that copies the whole file into every date folder
    # reproduces the same trade once per subsequent folder. Nothing here
    # de-duplicated: `trade_id` was not even SELECTed. `trade_report` has been
    # collapsing 1112 rows to 388 unique for weeks — this tool was reading the
    # 1112.
    # WHY IT IS WORSE THAN INFLATED TOTALS: n drives the Wilson interval. A 3x
    # duplication makes every interval ~1.7x too NARROW, so cells look decisive
    # when they are not — in the tool the Aug 8-9 calibration fits are read from.
    if dup:
        share = dup / (dup + len(rows))
        print(f"CT: de-duplicated {dup:,} repeated row(s) "
              f"({share:.0%} of everything read) -> {len(rows):,} unique trades."
              + ("  ⚠️ HIGH — the harvest is copying cumulative DBs into every "
                 "dated folder; fix the SOURCE, this is only the consumer-side "
                 "guard." if share >= 0.25 else ""))
    # v1.5 — REFUSE LOUDLY ON AN EMPTY LOAD. On 2026-08-05 this printed
    # "CT: 0 closed trades / 10 session(s) · no cell separated from chance yet"
    # — a confident verdict on an empty corpus, while the conductor's run of the
    # SAME tool that afternoon found 717 trades. A null result and a failed load
    # are indistinguishable in that sentence, and this is the tool the Aug 8-9
    # calibration fits get read from.
    # The dated folders exist (checked above) but held no matching DB, so this
    # is a PATH or NAMING fault, not a quiet night — and it says which.
    if dates and not rows:
        found = sum(len(glob.glob(os.path.join(args.trades_root, d, "*")))
                    for d in dates)
        print(f"CT: 🚨 LOAD FAILED — {len(dates)} dated folder(s) under "
              f"{args.trades_root} but ZERO trade rows read "
              f"({found} file(s) present, none matched *_trades*.db).")
        print("    This is NOT a null result. Check the path and the DB "
              "filenames before reading any verdict from this tool.")
        return 2

    tables = build_trade_tables(rows)
    journal_stats = load_journal(args.journal_root, dates)

    stem = f"conditional_tables_{dates[0]}_{dates[-1]}"
    out_txt   = os.path.join(args.reports_dir, stem + ".txt")
    out_jsonl = os.path.join(args.reports_dir, stem + ".jsonl")
    text = write_report(out_txt, out_jsonl, dates, rows, tables,
                        journal_stats, args.min_n)
    headline = build_headline(dates, rows, tables, args.min_n)
    if args.quiet:
        print(headline)
    else:
        print(text)
        print(headline)
        print(f"written: {out_txt}\nwritten: {out_jsonl}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
