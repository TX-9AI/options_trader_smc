#!/usr/bin/env python3
"""
tests/butterfly_wing_sweep.py — v1.0 — 2026-08-15   (BFLY.2)

DOES A WIDER TENT BUY A BETTER TRADE? Priced on real archived chains.

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python tests/butterfly_wing_sweep.py --since 2026-07-23

────────────────────────────────────────────────────────────────────────────
THE QUESTION, AND WHY IT IS NOT OBVIOUS
────────────────────────────────────────────────────────────────────────────
A narrow tent is CHEAPER IN DOLLARS — that intuition is correct. But the gate
is a RATIO, `debit / wing`, and cost falls more slowly than max profit does as
the wings narrow: the body sits near the money and stays expensive while the
payoff shrinks with the width. So the narrow tent is cheaper to buy and worse
to own.

Measured on the fleet 2026-08-14: QQQ tents priced at **0.41-0.57 of wing**
(p50 0.54) against a ceiling of 0.50, and NVDA at **0.62-0.82**. At a ratio of
0.54 you risk 0.54 to win 0.46 — **the asymmetry has INVERTED**, and the 0.50
ceiling is exactly the point where it does. Those rejections are correct.

⚠️ **AND THE WING IS FIXED, SO IT IS NOT A CHOICE ANYONE MADE PER TRADE.**
`config` defines only `BUTTERFLY_WING_SPX = 25` and `BUTTERFLY_WING_QQQ = 5`;
every other symbol takes the QQQ default of 5 STRIKE INCREMENTS regardless of
price, expected move or volatility. A pin on a quiet day and a pin on a violent
day get identical wings — when the whole question is how much of the
distribution lands inside them.

────────────────────────────────────────────────────────────────────────────
WHAT THIS MEASURES, PER WING WIDTH
────────────────────────────────────────────────────────────────────────────
  · **debit ratio** `debit / wing` — what the existing gate reads
  · **max profit** `wing - debit` in dollars — what widening actually buys
  · **zone width** the profitable span at expiry, as a FRACTION OF EM — the
    honest stand-in for "probability of profit": a butterfly wins anywhere
    between its breakevens, so a zone that covers more of the expected move is
    a higher-POP trade in the only sense that matters here
  · **REALIZED** — the terminal outcome from the tape. We know where price
    actually closed, so every candidate is settled, not modelled.

⚠️ ASSUMPTIONS, STATED: priced at MID with no slippage (FRC.1 says the real
spread is material, so absolute dollars here are OPTIMISTIC — the RANKING
across widths is what survives); a 5-minute chain cadence, so intra-window
quote movement is invisible; and every candidate is held to the 15:45 flatten,
which is what `BUTTERFLY_TP_PCT` would cut short in production.

⚠️ **NO BEST WIDTH IS NAMED.** The in-sample argmax is overfit by construction —
the same discipline `spread_counterfactual` and the floor sweep already apply.
This prints the curve. A width gets chosen by a PRE-REGISTERED rule against
held-out sessions, or not at all.
"""

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.spread_counterfactual import (session_path, ohlc_root,          # noqa: E402
                                         load_group_chain, nearest)

WIDTHS = (2, 3, 5, 8, 12, 16)          # in STRIKE INCREMENTS, 5 is today's default
CONTRACT_MULT = 100


def pin_events(journal_dir, date, sym):
    """[(minute, pin_strike)] from the journaled butterfly evaluations.

    Reads the PIN the engine actually identified rather than re-deriving one —
    re-deriving would be a second lineage of the GEX logic (WORKING_AGREEMENT 7)
    and would answer a different question than the one the fleet asked.
    """
    import json
    out = []
    path = os.path.join(journal_dir, date, f"{sym}.jsonl")
    if not os.path.isfile(path):
        return out
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if "Butterfly" not in line and "butterfly" not in line:
                    continue
                try:
                    r = json.loads(line.strip())
                except Exception:                              # noqa: BLE001
                    continue
                sig = r.get("signal") or {}
                if "Butterfly" not in str(sig.get("strategy", "")):
                    continue
                conf = " ".join(sig.get("confluence") or [])
                if "GEX pin @" not in conf:
                    continue
                try:
                    pin = float(conf.split("GEX pin @")[1].split("(")[0].strip())
                except Exception:                              # noqa: BLE001
                    continue
                ts = r.get("ts_et") or ""
                if len(ts) >= 16:
                    out.append((int(ts[11:13]) * 60 + int(ts[14:16]), pin))
    except Exception:                                          # noqa: BLE001
        pass
    return out


def price_fly(rows, side, center, inc, width_n):
    """(debit, wing_dollars) at MID, or None if any leg is unpriced."""
    wing = inc * width_n
    legs = {}
    for k, tag in ((center, "c"), (center - wing, "lo"), (center + wing, "hi")):
        c = rows.get((side, round(k, 4)))
        if not c:
            return None
        bid, ask = float(c.get("bid") or 0), float(c.get("ask") or 0)
        mid = (bid + ask) / 2.0
        if mid <= 0:
            return None
        legs[tag] = mid
    debit = legs["lo"] + legs["hi"] - 2.0 * legs["c"]
    if debit <= 0:
        return None
    return debit, wing


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-07-23")
    ap.add_argument("--journal", default=os.path.expanduser(
        "~/day_trader_pro/signal_journal"))
    ap.add_argument("--inc", type=float, default=0.0,
                    help="strike increment; 0 = infer from the chain")
    a = ap.parse_args(argv[1:])

    root = ohlc_root()
    if not root or not os.path.isdir(a.journal):
        print("no OHLC or journal root — ABSENT MEASUREMENT, not a null.")
        return 0

    dates = sorted(d for d in os.listdir(a.journal)
                   if len(d) == 10 and d >= a.since)
    agg = {w: {"n": 0, "ratio": [], "maxp": [], "zone": [], "real": []}
           for w in WIDTHS}
    pins_seen, sessions, skips = 0, set(), collections.Counter()

    for date in dates:
        paths = session_path(date, root)
        jdir = os.path.join(a.journal, date)
        if not os.path.isdir(jdir):
            continue
        for fn in sorted(os.listdir(jdir)):
            if not fn.endswith(".jsonl"):
                continue
            sym = fn[:-6]
            bars = paths.get(sym) or []
            if not bars:
                continue
            pins = pin_events(a.journal, date, sym)
            if not pins:
                continue
            settle = bars[-1][3]                     # last close of the session
            # EM proxy: the session's own realised range, so "zone as a fraction
            # of EM" is measured against what the day actually did.
            em = max(1e-9, max(b[1] for b in bars) - min(b[2] for b in bars))
            snaps = load_group_chain(date, sym, [m for m, _ in pins])

            for minute, pin in pins:
                rows = nearest(snaps, minute)
                if not rows:
                    skips["no chain at that minute"] += 1
                    continue
                pins_seen += 1
                sessions.add(date)
                strikes = sorted({k for (_s, k) in rows})
                inc = a.inc or (min((b - x for x, b in zip(strikes, strikes[1:])
                                     if b > x), default=0.0))
                if inc <= 0:
                    skips["strike increment unresolvable"] += 1
                    continue
                for side in ("put", "call"):
                    for w in WIDTHS:
                        got = price_fly(rows, side, pin, inc, w)
                        if not got:
                            skips[f"unpriced legs at {w}x"] += 1
                            continue
                        debit, wing = got
                        ratio = debit / wing
                        maxp = wing - debit
                        # profitable zone at expiry = between the breakevens
                        zone = 2.0 * (wing - debit)
                        pnl = (max(0.0, wing - abs(settle - pin)) - debit) * CONTRACT_MULT
                        d = agg[w]
                        d["n"] += 1
                        d["ratio"].append(ratio)
                        d["maxp"].append(maxp)
                        d["zone"].append(zone / em)
                        d["real"].append(pnl)

    def med(v):
        return sorted(v)[len(v) // 2] if v else 0.0

    print("=" * 82)
    print("  BUTTERFLY WING SWEEP — priced on archived chains, settled on tape")
    print(f"  {len(sessions)} session(s)   {pins_seen} pin observation(s)"
          f"   since {a.since}")
    print("=" * 82)
    if not pins_seen:
        print("\n  NO PIN OBSERVATIONS. Skip reasons:")
        for k, v in skips.most_common(6):
            print(f"    {k:34s} {v:,}")
        print("\n  ABSENT MEASUREMENT, not a null.")
        return 0

    print(f"\n  {'wing':>5} {'n':>6} {'debit/wing':>11} {'max profit':>11}"
          f" {'zone/EM':>9} {'realized $':>11} {'win%':>6}")
    print("  " + "-" * 74)
    for w in WIDTHS:
        d = agg[w]
        if not d["n"]:
            continue
        wins = sum(1 for x in d["real"] if x > 0)
        star = "  <- today's default" if w == 5 else ""
        print(f"  {w:>4}x {d['n']:>6} {med(d['ratio']):>11.2f}"
              f" {med(d['maxp']):>11.2f} {med(d['zone']):>9.2f}"
              f" {sum(d['real']):>11,.0f} {100.0*wins/d['n']:>5.0f}%{star}")

    print("\n  HOW TO READ IT")
    print("  · debit/wing is what the gate tests. The ceiling is 0.50, and 0.50")
    print("    is where the asymmetry INVERTS — above it you risk more than you")
    print("    can win. A width that lands well under 0.50 passes ON MERIT.")
    print("  · zone/EM is the honest POP stand-in: the profitable span at expiry")
    print("    as a fraction of what the day actually moved.")
    print("  · realized $ settles every candidate on the tape. Priced at MID with")
    print("    NO SLIPPAGE, so the dollars are OPTIMISTIC — the RANKING survives,")
    print("    the magnitudes do not.")
    print("\n  ⚠️ NO BEST WIDTH IS NAMED. The in-sample argmax is overfit by")
    print("     construction. Pre-register a rule or hold out sessions.")
    if skips:
        print("\n  SKIPS")
        for k, v in skips.most_common(6):
            print(f"    {k:34s} {v:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
