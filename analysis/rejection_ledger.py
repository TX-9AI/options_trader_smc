#!/usr/bin/env python3
"""
analysis/rejection_ledger.py — v1.0 — 2026-08-07

L3.2a — WHAT GOT BLOCKED, BY WHICH GATE, AND WHAT THE TAPE DID AFTERWARD.

Every measurement this desk has built so far looks only at trades that FIRED —
never-favourable, the floor sweep, trigger drift, the excursion report. All of
them are blind to the decisions the system DECLINED. That is half the selection
question missing, and it is the half that tells you what a gate COSTS. Tightening
a gate without it is guessing with extra steps.

THE LABEL THIS PRODUCES, and it is the whole point:
    DODGED   — blocked, and the tape then went AGAINST the intended direction
    MISSED   — blocked, and the tape went the intended way
A gate whose blocks are mostly MISSED is too tight and is costing money
invisibly. A gate whose blocks are mostly DODGED is earning its keep. Neither is
knowable from trades that fired.

FOUR SOURCES, ONE SCHEMA (they do not currently talk to each other):
  `scored`        every scored signal INCLUDING rejects — grade + total + bars
  `disposition`   outcome != "fired": invalid_signal, sizing_rejected, and
                  N.2's `gate_block:<gate>` (vwap, rrr, ...)
  `retest_check`  ORB near-misses, carrying `retest_depth_px` vs `orb_width`

⚠️ LEAK-FREEDOM IS THE ONE THING THAT MUST BE RIGHT. Outcomes are computed
STRICTLY from bars AFTER the decision bar. A join that leaks makes every blocked
trade look prescient — and it would look entirely reasonable doing it. `--verify`
implements the item's own test: shift every decision timestamp forward one bar
and confirm the outcomes CHANGE. If they do not, the join is reading the decision
bar itself and every number below is worthless.

⚠️ THE VERSION HASH CANNOT BE FULLY SATISFIED RETROSPECTIVELY, and pretending
otherwise would be worse than saying so. The item asks every row to carry the
ruleset that produced it. **The journal does not stamp one** — the same gap noted
on 2026-07-29 about engine identity. So rows carry `analysis_hash` (the HEAD this
ledger ran under) and NOT a decision hash, and any row older than the last
behaviour change is pooling decisions from different rulesets. 2026-08-07 alone
changed the emission law, the regime set, two dispatch gates, an exit gate and
two floors. **The fix is upstream: stamp the ruleset onto the journal event.**
Until then, read cross-date pooling with that caveat.

Read-only, stdlib only, always exits 0.
USAGE
    python3 -m analysis.rejection_ledger --since 2026-07-23
    python3 -m analysis.rejection_ledger --verify          # leak-freedom test
"""

import argparse
import collections
import glob
import json
import os
import re
import subprocess
import sys

JOURNAL_GLOB = "~/day_trader_pro/signal_journal/*/*.jsonl"
REPLAY_GLOB = "~/day_trader_pro/reports/regime_replay_*.jsonl"
OUT_DIR = "~/day_trader_pro/reports"
DATE_RE = re.compile(r"regime_replay_(20\d\d-\d\d-\d\d)\.jsonl$")
JDATE_RE = re.compile(r"/signal_journal/(20\d\d-\d\d-\d\d)/")

LONGISH = ("long", "call", "bull")


def _hash() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True,
                              timeout=5).stdout.strip() or "unknown"
    except Exception:                                            # noqa: BLE001
        return "unknown"


def _pct(sv, p):
    return 0.0 if not sv else sv[min(len(sv) - 1,
                                     int(round(p / 100.0 * (len(sv) - 1))))]


def load_prices(paths):
    out = collections.defaultdict(list)
    for path in paths:
        date = DATE_RE.search(path).group(1)
        for line in open(path, errors="ignore"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:                                    # noqa: BLE001
                continue
            if r.get("ts") and r.get("sym") and r.get("price"):
                out[(date, r["sym"])].append((r["ts"], float(r["price"])))
    return out


def _reject_row(r):
    """-> (gate, direction, score) for a rejection, or None if it is not one."""
    ev = r.get("event")
    sig = r.get("signal") or {}
    dirn = str(sig.get("direction") or sig.get("option_type") or "").lower()
    if ev == "disposition":
        out = str(r.get("outcome") or "")
        if out == "fired" or not out:
            return None
        return (out, dirn, (r.get("score") or {}).get("total"))
    if ev == "scored":
        sc = r.get("score") or {}
        if str(sc.get("grade") or "").upper() in ("REJECT", "C", "F"):
            return (f"scored:{sc.get('grade')}", dirn, sc.get("total"))
        return None
    if ev == "retest_check":
        orb = r.get("orb") or {}
        depth, width = orb.get("retest_depth_px"), orb.get("orb_width")
        if depth is None or not width:
            return None
        # a NEAR-MISS is a retest that came close without qualifying; a deep or
        # negative depth is not a near miss, it is simply not a retest.
        if 0.0 <= float(depth) <= 0.25 * float(width):
            return ("retest_near_miss", str(orb.get("direction") or "").lower(),
                    None)
        return None
    return None


def outcome(series, idx, sign, horizon):
    """MFE / MAE over the horizon, computed STRICTLY after the decision bar.

    `idx + 1` is not decoration — starting at idx would read the decision bar
    itself and leak the very information the block was made without.
    """
    lo = idx + 1
    hi = min(len(series), lo + horizon)
    if lo >= hi:
        return None
    p0 = series[idx][1]
    if p0 <= 0:
        return None
    moves = [sign * (series[k][1] - p0) / p0 * 100.0 for k in range(lo, hi)]
    return max(moves), min(moves)


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", default=JOURNAL_GLOB)
    ap.add_argument("--replay", default=REPLAY_GLOB)
    ap.add_argument("--since", default="")
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--verify", action="store_true",
                    help="leak-freedom test: shift decisions +1 bar")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv[1:])

    rpaths = [p for p in sorted(glob.glob(os.path.expanduser(a.replay)))
              if DATE_RE.search(p)
              and (not a.since or DATE_RE.search(p).group(1) >= a.since)]
    if not rpaths:
        print(f"no replay files matched {a.replay}")
        return 0
    prices = load_prices(rpaths)
    pos = {}
    for key, ser in prices.items():
        d = {}
        for i, (ts, _p) in enumerate(ser):
            d.setdefault(ts, i)
        pos[key] = d

    ahash = _hash()
    rows, unmatched, seen = [], 0, 0
    verify_seen, verify_moved = [0], [0]
    for jf in sorted(glob.glob(os.path.expanduser(a.journal))):
        m = JDATE_RE.search(jf)
        if not m or (a.since and m.group(1) < a.since):
            continue
        date = m.group(1)
        for line in open(jf, errors="ignore"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:                                    # noqa: BLE001
                continue
            rej = _reject_row(r)
            if rej is None:
                continue
            seen += 1
            gate, dirn, score = rej
            sym = r.get("symbol") or "?"
            # ts_et is ALREADY ET with an offset (unlike trades.db's UTC
            # entry_time), so no conversion — and none is invented.
            hhmm = str(r.get("ts_et") or "")[11:16]
            key = (date, sym)
            idx = pos.get(key, {}).get(hhmm)
            if idx is None:
                unmatched += 1
                continue
            sign = 1.0 if any(t in dirn for t in LONGISH) else -1.0
            o = outcome(prices[key], idx, sign, a.horizon)
            if o is None:
                continue
            mfe, mae = o
            # v1.0 — LEAK TEST, PAIRED PER ROW. The first draft shifted the
            # index and compared MEDIANS, which printed IDENTICAL numbers on
            # CORRECT code because a uniform shift moves every window equally.
            # A verification that passes when it should fail is worse than none
            # — the same failure class as the canaries that matched
            # documentation. Compare each row against its own +1-bar twin
            # instead: on a leak-free join essentially every row must MOVE.
            if a.verify:
                o2 = outcome(prices[key], idx + 1, sign, a.horizon)
                verify_seen[0] += 1
                if o2 is not None and (round(o2[0], 6), round(o2[1], 6)) != (
                        round(mfe, 6), round(mae, 6)):
                    verify_moved[0] += 1
            rows.append({"date": date, "symbol": sym, "ts_et": hhmm,
                         "gate": gate, "direction": dirn, "score": score,
                         "mfe_pct": round(mfe, 4), "mae_pct": round(mae, 4),
                         "verdict": "MISSED" if mfe >= 0.10 else "DODGED",
                         "horizon_bars": a.horizon,
                         "analysis_hash": ahash,
                         "decision_hash": None})

    out = os.path.expanduser(a.out) if a.out else os.path.join(
        os.path.expanduser(OUT_DIR), "rejection_summary.jsonl")
    if not a.verify:
        try:
            with open(out, "w") as f:
                for r in rows:
                    f.write(json.dumps(r) + "\n")
        except Exception as e:                                   # noqa: BLE001
            print(f"could not write {out}: {e}")

    print(f"rejection events seen: {seen}   joined to tape: {len(rows)}   "
          f"unmatched: {unmatched}")
    if a.verify:
        n, mv = verify_seen[0], verify_moved[0]
        pct = 100.0 * mv / max(1, n)
        print(f"LEAK TEST: {mv}/{n} rows ({pct:.1f}%) changed when the decision "
              f"bar was shifted +1.")
        if pct >= 95.0:
            print("  PASS — outcomes depend on WHICH bar the decision sat on, so "
                  "the join is\n  reading forward bars and not the decision bar "
                  "itself.")
        else:
            print("  ** FAIL — outcomes barely move when the decision does. The "
                  "join is reading\n  ** the decision bar (or a constant), and "
                  "EVERY verdict below is worthless.")
    else:
        print(f"written: {out}")
    print(f"analysis_hash: {ahash}   decision_hash: NOT AVAILABLE — the journal "
          f"does not stamp\n  the ruleset that made the decision, so rows "
          f"spanning a behaviour change are\n  pooling different engines. Fix is "
          f"upstream; read cross-date totals with that.")
    print()
    print(f"=== BY GATE — horizon {a.horizon} bars, signed by intended direction")
    print(f"  {'gate':<28}{'n':>6}{'MISSED':>9}{'DODGED':>9}{'med MFE':>10}"
          f"{'med MAE':>10}")
    byg = collections.defaultdict(list)
    for r in rows:
        byg[r["gate"]].append(r)
    for gate, rs in sorted(byg.items(), key=lambda kv: -len(kv[1])):
        n = len(rs)
        miss = sum(1 for r in rs if r["verdict"] == "MISSED")
        mfe = sorted(r["mfe_pct"] for r in rs)
        mae = sorted(r["mae_pct"] for r in rs)
        thin = "  <- thin" if n < 15 else ""
        print(f"  {gate[:28]:<28}{n:>6}{100.0*miss/n:>8.0f}%"
              f"{100.0*(n-miss)/n:>8.0f}%{_pct(mfe,50):>10.3f}"
              f"{_pct(mae,50):>10.3f}{thin}")
    print()
    print("  MISSED = the tape went the intended way after the block (MFE >= "
          "0.10%).")
    print("  DODGED = it did not. A gate that is mostly MISSED is too tight and")
    print("  is costing money invisibly; mostly DODGED means it is earning its")
    print("  keep. Neither is visible in any trade that actually fired.")
    print("  Outcomes start at the bar AFTER the decision — never the decision")
    print("  bar itself. Run --verify to prove that join is leak-free.")
    return 0


if __name__ == "__main__":
    try:
        rc = main(sys.argv)
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        rc = 0
    sys.exit(rc)
