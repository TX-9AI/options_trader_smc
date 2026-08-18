#!/usr/bin/env python3
"""
tests/slippage_audit.py — v1.1 — 2026-08-13   (FRC.1)

v1.1 — 2026-08-13 — PRICED ZERO OF 805 JOINED TRADES ON THE FIRST RUN.
        `contract` is nested under `signal` in a scored row, not at the top
        level — the SAME shape `scorer_backtest` already handles for `strategy`
        (`r.get("strategy") or (r.get("signal") or {}).get("strategy")`) and
        that `factor_sweep` reads correctly at line 138 (`con =
        sig.get("contract")`). I had two working references in the repo and
        matched neither.
        ALSO ADDED, because the failure was needlessly opaque: PER-FIELD miss
        counts. v1.0 had ONE counter for "spread or premium or qty missing", so
        the output said only that something failed, not which — and that cost a
        round trip on the box. A diagnostic that cannot name the failing field
        is not a diagnostic.

WHAT DOES THE BOOK LOOK LIKE ONCE YOU PAY THE SPREAD?

`config.PAPER_FILL_SLIPPAGE_PCT` is **0.0**, and commission is not modelled
anywhere. `limit_ladder.paper_fill_price` books the MARK and is explicit about
what it assumes: *"paper is now honest about PRICE but still optimistic about
FILL RATE — the residual gap to model later is no-fill risk, not slippage."*
Under a mark-limit policy that is a defensible baseline. **It is not the price a
crossed order gets.**

So every number produced today — the +$463 book, TC.7's +$0.52/spread, the POP
validation — is measured against a fill that may not happen at that price.

THIS DOES NOT NEED A FORWARD WEEK. `contract.spread_pct_of_mid` is already
journaled per scored trade and `contracts` is in trades.db, so the friction is
computable on the sessions ALREADY COLLECTED.

────────────────────────────────────────────────────────────────────────────
THE ARITHMETIC, stated so it can be argued with
────────────────────────────────────────────────────────────────────────────
Mark is the mid. Crossing to BUY pays the ask (mid + half spread); crossing to
SELL receives the bid (mid - half spread). A round trip therefore costs ONE FULL
SPREAD, not two:

    friction_usd = spread_pct_of_mid * entry_premium * contracts * 100

⚠️ THREE HONEST LIMITS, none of them hidden:
  1. The spread is measured AT ENTRY. Exit spreads on 0DTE are usually WIDER
     (less time, thinner books), so this is a LOWER BOUND on true friction.
  2. It assumes you cross BOTH ways. A mark-limit that fills costs nothing
     extra; the truth sits between this number and zero, and where it sits is a
     FILL-RATE question this tool cannot answer.
  3. Commission is NOT included — it is not in the data at all. Add it per
     contract separately.
  So read the output as: **"the book if every order crossed."** The real answer
  is bracketed by that and the current mark-based P&L.

WHY THE SUB-MINUTE COHORT IS BROKEN OUT: 279 of 843 trades close in under a
minute, ~218 of them `regime_flip` at a 0.3-minute median hold, for +$1,308
gross. A mark-limit posted and cancelled within eighteen seconds is exactly
where "assume it fills" is least true, and that cohort pays entry AND exit
friction on every one. If friction exceeds its gross, it is a pure-subtraction
population regardless of what the mark-based P&L says.

READ-ONLY. Imports the join from `scorer_backtest` — one join, one owner.

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python tests/slippage_audit.py --since 2026-07-23
"""

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.scorer_backtest import (load_scored, load_trades,                # noqa: E402
                                   JOIN_TOL_S, JOURNAL)

CONTRACT_MULTIPLIER = 100


def hold_minutes(raw):
    try:
        from datetime import datetime
        a = str(raw.get("entry_time") or "")
        b = str(raw.get("exit_time") or "")
        if not a or not b:
            return None
        fmt = "%Y-%m-%dT%H:%M:%S"
        return (datetime.strptime(b[:19], fmt)
                - datetime.strptime(a[:19], fmt)).total_seconds() / 60.0
    except Exception:                                          # noqa: BLE001
        return None


def row(label, n, gross, fric, width=34):
    net = gross - fric
    flip = "  <- SIGN FLIPS" if (gross > 0 and net <= 0) else ""
    print(f"  {label:<{width}}{n:>6}{gross:>12,.0f}{fric:>12,.0f}"
          f"{net:>12,.0f}{flip}")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-07-23")
    ap.add_argument("--commission", type=float, default=0.0,
                    help="per contract per side, added on top. NOT in the data "
                         "— supply it or it is omitted and said so.")
    a = ap.parse_args(argv[1:])

    dates = sorted(d for d in os.listdir(JOURNAL)
                   if len(d) == 10 and d >= a.since)
    joined, seen, no_spread = [], set(), 0
    miss = collections.Counter()      # WHICH field failed, not just that one did
    for date in dates:
        sc = load_scored(date)
        idx = collections.defaultdict(list)
        for s in sc:
            idx[(s["sym"], s["strategy"])].append(s)
        for t in load_trades(date, seen):
            best, bd = None, JOIN_TOL_S + 1
            for s in idx.get((t["sym"], t["strategy"])) or []:
                d = abs((s["ts"] - t["ts"]).total_seconds())
                if d < bd:
                    best, bd = s, d
            if best is None or bd > JOIN_TOL_S:
                continue
            raw = t.get("raw") or {}
            # `contract` is nested under `signal`, NOT at the top of the scored
            # row — the same shape scorer_backtest already handles for
            # `strategy`. v1.0 read raw["contract"] and priced ZERO of 805
            # joined trades. Fall back to the top level in case the emitter
            # ever flattens it.
            _sig = (best.get("raw") or {}).get("signal") or {}
            con = _sig.get("contract") or (best.get("raw") or {}).get("contract") or {}
            spct = con.get("spread_pct_of_mid")
            prem = raw.get("entry_premium")
            qty = raw.get("contracts")
            if spct is None:
                miss["spread_pct_of_mid"] += 1
            if not prem:
                miss["entry_premium"] += 1
            if not qty:
                miss["contracts"] += 1
            if spct is None or not prem or not qty:
                no_spread += 1
                continue
            fric = (float(spct) * float(prem) * float(qty) * CONTRACT_MULTIPLIER
                    + a.commission * float(qty) * 2)
            joined.append({**t, "fric": fric, "spct": float(spct),
                           "hold": hold_minutes(raw),
                           "exit": raw.get("exit_reason") or ""})

    print("=" * 88)
    print("  SLIPPAGE AUDIT (FRC.1) — the book if every order CROSSED the spread")
    print(f"  {len(dates)} session(s) since {a.since}   {len(joined)} trades priced"
          f"   {no_spread} lacked a spread/premium/qty")
    print(f"  commission modelled: "
          f"{('$%.2f/contract/side' % a.commission) if a.commission else 'NONE (not in the data)'}")
    print("=" * 88)
    if miss:
        print("  missing per field: " + " · ".join(f"{k} {v}" for k, v in
                                                   miss.most_common()))
    if not joined:
        print("\n  nothing priced. ABSENT MEASUREMENT, not a null.")
        print("  The per-field counts above name WHICH lookup failed — a single")
        print("  lumped counter said only that something did, which cost a")
        print("  round trip.")
        return 0

    gross = sum(j["pnl"] for j in joined)
    fric = sum(j["fric"] for j in joined)
    print(f"\n  {'':34}{'n':>6}{'gross $':>12}{'friction $':>12}{'net $':>12}")
    row("WHOLE BOOK", len(joined), gross, fric)

    print(f"\n  BY STRATEGY")
    by = collections.defaultdict(lambda: [0, 0.0, 0.0])
    for j in joined:
        c = by[j["strategy"]]
        c[0] += 1; c[1] += j["pnl"]; c[2] += j["fric"]
    for k, (n, g, f) in sorted(by.items(), key=lambda kv: kv[1][1]):
        row(k, n, g, f)

    print(f"\n  BY HOLD TIME  <- the sub-minute cohort is the point")
    buckets = [("under 1 min", lambda h: h is not None and h < 1),
               ("1-5 min", lambda h: h is not None and 1 <= h < 5),
               ("5-30 min", lambda h: h is not None and 5 <= h < 30),
               ("30+ min", lambda h: h is not None and h >= 30),
               ("unknown", lambda h: h is None)]
    for label, test in buckets:
        g = [j for j in joined if test(j["hold"])]
        if g:
            row(label, len(g), sum(x["pnl"] for x in g),
                sum(x["fric"] for x in g))

    print(f"\n  BY EXIT REASON (top 8 by trade count)")
    ex = collections.defaultdict(lambda: [0, 0.0, 0.0])
    for j in joined:
        c = ex[j["exit"].split(":")[0][:32] or "(none)"]
        c[0] += 1; c[1] += j["pnl"]; c[2] += j["fric"]
    for k, (n, g, f) in sorted(ex.items(), key=lambda kv: -kv[1][0])[:8]:
        row(k, n, g, f)

    print(f"\n  BY SPREAD QUINTILE — the friction gate's own evidence")
    js = sorted(joined, key=lambda j: j["spct"])
    q = max(1, len(js) // 5)
    for i in range(5):
        g = js[i * q:(i + 1) * q] if i < 4 else js[4 * q:]
        if g:
            row(f"{g[0]['spct']:.4f}..{g[-1]['spct']:.4f}", len(g),
                sum(x["pnl"] for x in g), sum(x["fric"] for x in g))

    print("\n" + "=" * 88)
    print("  HOW TO READ THIS. Friction here assumes you CROSS BOTH WAYS. A")
    print("  mark-limit that fills costs nothing extra, so the truth sits")
    print("  between this net and the gross — and WHERE it sits is a FILL-RATE")
    print("  question this tool cannot answer. The spread is also measured AT")
    print("  ENTRY, and 0DTE exit spreads are usually wider, so the friction")
    print("  column is a LOWER BOUND.")
    print("  A cohort whose sign FLIPS is one whose edge is smaller than its")
    print("  own transaction cost — that is a selection finding, not a fill")
    print("  finding, and it does not go away by filling better.")
    print("=" * 88)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
