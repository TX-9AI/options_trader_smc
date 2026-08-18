#!/usr/bin/env python3
"""
tests/chain_reconstruction_check.py — v1.0 — Does a greek-based Taylor
        reconstruction of option premium survive the 5-minute gap between
        chain snapshots? This is the GATE on the strike-counterfactual harness
        (ROADMAP P5): it decides the architecture before a line of that harness
        is written.
v1.0 — 2026-07-23 — initial. OFFLINE, read-only, stdlib-only. Runs on the
        control server against harvested snapshots OR directly on a bot box
        against its own data/chain_snapshots/ — pass --root either way.

THE QUESTION
    analysis/chain_snapshot.py archives the full chain every 5 minutes. The
    engines decide every 15 seconds. So a counterfactual harness that wants to
    price a strike we did NOT trade, at a moment BETWEEN snapshots, has to
    reconstruct it. The candidate reconstruction is a second-order Taylor
    expansion off the previous snapshot's own greeks:

        P̂(t₁) = P₀ + δ·ΔS + ½·γ·ΔS² + θ·Δt

    where ΔS is the underlying move and Δt the elapsed time in CALENDAR days
    (the convention this codebase settled on after the exit_engine theta-units
    bug — RTH-minute theta overstated decay ~3.7x).

    If that prediction lands inside the bid/ask spread of the real quote at
    t₁, the reconstruction is indistinguishable from a fill and the harness can
    use it. If it does not, no amount of harness code fixes it and the answer
    is either two-tier archival (full chain at 5 min + an ATM window every
    tick) or an IV-path model.

    We can answer this with data already on disk, because every snapshot is
    both a prediction input AND the answer key for the previous one.

WHAT IT MEASURES
    For every consecutive snapshot pair and every strike present in both:
      * pure Taylor error       — δ/γ/θ only. This is what a FORWARD harness
                                  could actually use: it knows nothing about
                                  the future.
      * Taylor + vega·ΔIV       — DIAGNOSTIC ONLY, and it is cheating: it uses
                                  the IV we could not have known. Its purpose
                                  is to attribute blame. If adding it collapses
                                  the error, the missing piece is an IV path
                                  model, NOT more archival cadence — a very
                                  different (and cheaper) fix.
      * inside-spread rate      — |error| ≤ half-spread at t₁. THE verdict
                                  metric: an error smaller than the spread is
                                  an error you could not have traded around.

    Stratified by moneyness, time of day, and |ΔS|, because the answer is
    almost certainly "yes near the money, no in the tails" — and near the money
    is where we actually select strikes. A partial pass that covers the
    selection zone is a usable pass.

WHAT IT DELIBERATELY DOES NOT DO
    No fitting. No tuning a fudge factor until it passes. It reports the error
    of a fixed, published formula; a formula that needs a fitted correction to
    pass is not a reconstruction, it is a model, and it would have to be
    validated out-of-sample like any other.

USAGE
    python3 -m tests.chain_reconstruction_check                     # all dates
    python3 -m tests.chain_reconstruction_check --date 2026-07-24
    python3 -m tests.chain_reconstruction_check --symbol QQQ
    python3 -m tests.chain_reconstruction_check --root ~/options-trader/data/chain_snapshots
    python3 -m tests.chain_reconstruction_check --quiet             # verdict line only
"""

import argparse
import glob
import gzip
import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime

DEFAULT_ROOTS = [
    os.path.expanduser("~/day_trader_pro/chain_snapshots"),   # harvested (future)
    os.path.expanduser("~/options-trader/data/chain_snapshots"),  # box-local
    os.path.expanduser("~/options-trader-v3/data/chain_snapshots"),
]

MAX_GAP_MIN = 12.0     # a wider gap means a restart — not a fair test of a 5-min hop
MIN_PREMIUM = 0.10     # DEFAULT tradable floor — see --min-premium. Contracts
                       # priced below this are excluded from the verdict
                       # entirely: at $0.02 the inside-spread test measures the
                       # exchange's minimum tick, not our reconstruction, and
                       # thousands of untradable wing strikes would otherwise
                       # dominate the headline. We only care whether the
                       # reconstruction holds for contracts we would BUY.
CAL_MINUTES_PER_DAY = 1440.0


def pick_root(explicit):
    if explicit:
        return os.path.expanduser(explicit)
    for r in DEFAULT_ROOTS:
        if os.path.isdir(r):
            return r
    return DEFAULT_ROOTS[0]


def load_snapshots(root, dates, symbols):
    """{(date, symbol): [snapshot, ...]} sorted by timestamp."""
    out = defaultdict(list)
    if not os.path.isdir(root):
        return out
    for day in sorted(os.listdir(root)):
        if dates and day not in dates:
            continue
        if not (len(day) == 10 and day[4] == "-"):
            continue
        for path in sorted(glob.glob(os.path.join(root, day, "*.jsonl.gz"))):
            sym = os.path.basename(path).split(".")[0]
            if symbols and sym not in symbols:
                continue
            try:
                with gzip.open(path, "rt", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            row = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if row.get("event") == "chain_snapshot":
                            out[(day, sym)].append(row)
            except OSError as e:
                print(f"  warn: {path}: {e}", file=sys.stderr)
    for key in out:
        out[key].sort(key=lambda r: r.get("ts_et") or "")
    return out


def parse_ts(s):
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def moneyness_bucket(strike, spot, opt_type):
    """Signed distance from spot, in percent, from the OPTION's perspective."""
    if not spot:
        return "unknown"
    pct = (strike - spot) / spot * 100.0
    if opt_type.lower().startswith("p"):
        pct = -pct                      # OTM puts sit below spot
    a = abs(pct)
    if a <= 0.25:  return "ATM(<0.25%)"
    if pct > 0:
        if a <= 1.0: return "OTM 0.25-1%"
        if a <= 2.0: return "OTM 1-2%"
        return "OTM >2%"
    if a <= 1.0: return "ITM 0.25-1%"
    if a <= 2.0: return "ITM 1-2%"
    return "ITM >2%"


def hour_bucket(ts):
    m = ts.hour * 60 + ts.minute
    if m < 10 * 60:      return "0930-1000"
    if m < 11 * 60:      return "1000-1100"
    if m < 12 * 60:      return "1100-1200"
    if m < 13 * 60:      return "1200-1300"
    if m < 14 * 60:      return "1300-1400"
    if m < 15 * 60:      return "1400-1500"
    return "1500-1600"


def move_bucket(dS, spot):
    if not spot:
        return "unknown"
    p = abs(dS) / spot * 100.0
    if p < 0.05: return "|ΔS|<0.05%"
    if p < 0.15: return "|ΔS|0.05-0.15%"
    if p < 0.30: return "|ΔS|0.15-0.30%"
    return "|ΔS|>0.30%"


class Acc:
    """Error accumulator for one stratum."""
    __slots__ = ("n", "inside", "abs_err", "abs_err_iv", "pct_err", "ratio")

    def __init__(self):
        self.n = 0
        self.inside = 0
        self.abs_err, self.abs_err_iv, self.pct_err, self.ratio = [], [], [], []

    def add(self, err, err_iv, prem, half_spread):
        self.n += 1
        self.abs_err.append(abs(err))
        self.abs_err_iv.append(abs(err_iv))
        if prem >= MIN_PREMIUM:
            self.pct_err.append(abs(err) / prem * 100.0)
        if half_spread > 0:
            self.ratio.append(abs(err) / half_spread)
            if abs(err) <= half_spread:
                self.inside += 1

    def row(self, label):
        if not self.n:
            return f"  {label:<20} (no samples)"
        med = statistics.median(self.abs_err)
        p90 = (statistics.quantiles(self.abs_err, n=10)[8]
               if len(self.abs_err) >= 10 else max(self.abs_err))
        med_iv = statistics.median(self.abs_err_iv)
        pct = statistics.median(self.pct_err) if self.pct_err else float("nan")
        ins = self.inside / self.n * 100.0 if self.n else 0.0
        return (f"  {label:<20} n={self.n:<7} inside-spread={ins:5.1f}%  "
                f"|err| med=${med:5.3f} p90=${p90:5.3f}  "
                f"med%={pct:5.1f}%  (+vega·ΔIV med=${med_iv:5.3f})")


def analyse(snapshots, min_premium=MIN_PREMIUM):
    overall   = Acc()
    by_money  = defaultdict(Acc)
    by_hour   = defaultdict(Acc)
    by_move   = defaultdict(Acc)
    by_symbol = defaultdict(Acc)
    pairs = 0
    skipped = [0]

    for (day, sym), rows in sorted(snapshots.items()):
        for a, b in zip(rows, rows[1:]):
            ta, tb = parse_ts(a.get("ts_et")), parse_ts(b.get("ts_et"))
            if not ta or not tb:
                continue
            dt_min = (tb - ta).total_seconds() / 60.0
            if dt_min <= 0 or dt_min > MAX_GAP_MIN:
                continue
            s0, s1 = a.get("underlying"), b.get("underlying")
            if not s0 or not s1:
                continue
            dS = float(s1) - float(s0)
            dt_days = dt_min / CAL_MINUTES_PER_DAY
            pairs += 1

            later = {(c.get("occ") or f"{c.get('type')}|{c.get('strike')}"): c
                     for c in (b.get("contracts") or [])}
            for c0 in (a.get("contracts") or []):
                key = c0.get("occ") or f"{c0.get('type')}|{c0.get('strike')}"
                c1 = later.get(key)
                if c1 is None:
                    continue
                p0, p1 = c0.get("mark"), c1.get("mark")
                if not p0 or p1 is None or p0 <= 0:
                    continue
                if float(p1) < min_premium or float(p0) < min_premium:
                    skipped[0] += 1
                    continue
                d, g = c0.get("delta") or 0.0, c0.get("gamma") or 0.0
                th, vg = c0.get("theta") or 0.0, c0.get("vega") or 0.0
                pred = p0 + d * dS + 0.5 * g * dS * dS + th * dt_days
                err = pred - float(p1)
                d_iv = (c1.get("iv") or 0.0) - (c0.get("iv") or 0.0)
                err_iv = (pred + vg * d_iv * 100.0) - float(p1)

                bid, ask = c1.get("bid") or 0.0, c1.get("ask") or 0.0
                half = (ask - bid) / 2.0 if ask > bid > 0 else 0.0

                overall.add(err, err_iv, float(p1), half)
                by_symbol[sym].add(err, err_iv, float(p1), half)
                by_money[moneyness_bucket(c0.get("strike") or 0.0, float(s0),
                                          c0.get("type") or "")].add(
                    err, err_iv, float(p1), half)
                by_hour[hour_bucket(tb)].add(err, err_iv, float(p1), half)
                by_move[move_bucket(dS, float(s0))].add(err, err_iv, float(p1), half)

    return overall, by_money, by_hour, by_move, by_symbol, pairs, skipped[0]


def verdict(overall, by_money):
    """PASS / PARTIAL / FAIL, plus the architectural consequence of each."""
    if overall.n == 0:
        return ("NO DATA", "no comparable snapshot pairs yet — the archive needs "
                           "at least one full session (and, on control, a harvest "
                           "step; see ROADMAP P5)")
    ins = overall.inside / overall.n * 100.0
    zone = [b for b in ("ATM(<0.25%)", "OTM 0.25-1%", "ITM 0.25-1%") if b in by_money]
    zone_n = sum(by_money[b].n for b in zone)
    zone_in = sum(by_money[b].inside for b in zone)
    zone_pct = (zone_in / zone_n * 100.0) if zone_n else 0.0

    if ins >= 80:
        return ("PASS", f"{ins:.1f}% of reconstructions land inside the spread — "
                        f"build ChainReplay as a drop-in behind the existing "
                        f"PremiumModel seam in tests/backtest_harness.py")
    if zone_pct >= 80:
        return ("PARTIAL", f"overall {ins:.1f}% but {zone_pct:.1f}% within ±1% of "
                           f"spot — usable for STRIKE SELECTION (which lives in "
                           f"that zone); restrict the counterfactual grid to it "
                           f"and state the boundary in the harness header")
    return ("FAIL", f"only {ins:.1f}% inside the spread ({zone_pct:.1f}% near the "
                    f"money) — 5-minute cadence cannot carry the harness. Compare "
                    f"the +vega·ΔIV column: if it is much smaller, the fix is an "
                    f"IV-path model; if not, it is two-tier archival (full chain "
                    f"at 5 min + ATM window every tick)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--root")
    ap.add_argument("--date", action="append")
    ap.add_argument("--symbol", action="append")
    ap.add_argument("--min-premium", type=float, default=MIN_PREMIUM,
                    help="exclude contracts quoted below this from the verdict "
                         "(default %(default)s) — untradable wings otherwise "
                         "swamp the inside-spread rate with tick noise")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    root = pick_root(args.root)
    snaps = load_snapshots(root, set(args.date or []), set(args.symbol or []))
    (overall, by_money, by_hour, by_move, by_symbol,
     pairs, skipped) = analyse(snaps, args.min_premium)
    tag, why = verdict(overall, by_money)
    head = (f"CHAIN-RECON [{tag}]: {overall.n} strike-hops over {pairs} snapshot "
            f"pairs (>=${args.min_premium:.2f}) — {why}")

    if args.quiet:
        print(head)
        return 0

    print("=" * 78)
    print("CHAIN PREMIUM RECONSTRUCTION CHECK — P̂ = P₀ + δ·ΔS + ½γ·ΔS² + θ·Δt")
    print(f"root: {root}   sessions: {len({d for d, _ in snaps})}   "
          f"symbols: {len({s for _, s in snaps})}")
    print(f"tradable floor: ${args.min_premium:.2f}  "
          f"({skipped} sub-floor strike-hops excluded)")
    print("The verdict metric is inside-spread rate: an error smaller than the")
    print("half-spread is an error you could not have traded around anyway.")
    print("The +vega·ΔIV column is DIAGNOSTIC — it uses future IV and a forward")
    print("harness cannot. It exists to tell you whether residual error is IV")
    print("drift (fixable with a model) or cadence (fixable only with data).")
    print("=" * 78)
    print("\n── overall " + "─" * 60)
    print(overall.row("ALL"))
    for title, table in (("moneyness", by_money), ("time of day", by_hour),
                         ("underlying move", by_move), ("symbol", by_symbol)):
        print(f"\n── by {title} " + "─" * max(1, 58 - len(title)))
        for k in sorted(table, key=lambda k: -table[k].n):
            print(table[k].row(k))
    print("\n" + "=" * 78)
    print(head)
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
