#!/usr/bin/env python3
"""
tests/axis_crosstab.py — v1.0 — 2026-08-07

DOES THE CONJUNCTION SEPARATE WHERE ITS COMPONENTS DO NOT?

THE QUESTION, stated so it can fail. Across the whole book, `SETUP.nf ~=
SETUP.ok` and `RGCV.nf ~= RGCV.ok` — neither the setup score nor the regime
conviction distinguishes a trade that went favourable from one that never did.
When a score does not separate, NO THRESHOLD ON IT CAN, and the fix is to change
what the score measures rather than where the bar sits.

`pair_conf = min(direction_conf, volatility_conf)` is a genuinely different
function: it is low whenever EITHER axis is unsure, which neither component
reports on its own. **A conjunction CAN separate where its components do not.**
This is the test of that, and it is designed to be able to say no.

TWO OUTPUTS, and the second is the real one:
  1. The 3x3 CROSS-TAB — every (direction x volatility) cell with n, win rate,
     net $ and never-favourable rate. This is where "continuation makes money
     ONLY in RANGING" either resolves into a specific PAIR or does not.
  2. `pair_conf` SPLIT BY OUTCOME — `nf` (never favourable) vs `ok`, exactly the
     comparison the excursion report runs on setup_score and regime_conviction.
     **nf BELOW ok means a cutoff exists. nf ~= ok means this idea is dead** and
     should be recorded as dead rather than quietly re-litigated.

⚠️ THE NEVER-FAVOURABLE LABEL IS PRICE-PATH, NOT P&L. A trade counts as
favourable if `max_premium_seen` ever exceeded entry by the cut. That is
independent of stops, sizing and fills, so it cannot be contaminated by exit
logic — which is exactly why realized P&L is the wrong target here.

⚠️ THE SCORE VECTOR IS TAKEN FROM THE REPLAY CORPUS AT THE ENTRY TICK, not from
the trade row. The row stores the FUSED label and conviction; the axes need the
whole vector, which only the corpus has.

⚠️ TIMEZONE: `entry_time` is UTC by design, the corpus stamps ET wall-clock.
Converted with `zoneinfo`, never a fixed offset. Unmatched rows are DROPPED AND
COUNTED, never snapped to a neighbouring minute.

Read-only, stdlib only, streams the corpus, always exits 0.
USAGE
    python3 tests/axis_crosstab.py --since 2026-07-23
"""

import argparse
import collections
import glob
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis.regime_axes import decompose            # noqa: E402

REPLAY_GLOB = "~/day_trader_pro/reports/regime_replay_*.jsonl"
TRADES_GLOB = "~/day_trader_pro/trades/*/*.db"
DATE_RE = re.compile(r"regime_replay_(20\d\d-\d\d-\d\d)\.jsonl$")
TRADE_DATE_RE = re.compile(r"/trades/(20\d\d-\d\d-\d\d)/")
DIRS = ("BULL", "BEAR", "RANGE", "NEUTRAL")
VOLS = ("EXPANDING", "COMPRESSING", "NEUTRAL")

try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except Exception:                                                # noqa: BLE001
    _ET = None


def _hhmm(entry_time):
    if not entry_time or _ET is None:
        return None
    try:
        d = datetime.fromisoformat(str(entry_time).strip().replace("Z", "+00:00"))
    except Exception:                                            # noqa: BLE001
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(_ET).strftime("%H:%M")


def _pct(sv, p):
    return 0.0 if not sv else sv[min(len(sv) - 1,
                                     int(round(p / 100.0 * (len(sv) - 1))))]


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", default=REPLAY_GLOB)
    ap.add_argument("--trades", default=TRADES_GLOB)
    ap.add_argument("--since", default="")
    ap.add_argument("--nf-cut", type=float, default=2.0,
                    help="%% favourable excursion required to count as 'ok'")
    a = ap.parse_args(argv[1:])

    # score vectors by (date, sym, hh:mm)
    vec = {}
    for path in sorted(glob.glob(os.path.expanduser(a.replay))):
        m = DATE_RE.search(path)
        if not m or (a.since and m.group(1) < a.since):
            continue
        date = m.group(1)
        for line in open(path, errors="ignore"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:                                    # noqa: BLE001
                continue
            sc, ts, sym = r.get("scores"), r.get("ts"), r.get("sym")
            if sc and ts and sym:
                vec.setdefault((date, sym, str(ts)[:5]), sc)
    if not vec:
        print(f"no score vectors under {a.replay}")
        return 0

    cells = collections.defaultdict(lambda: {"n": 0, "win": 0, "pnl": 0.0, "nf": 0})
    conf_nf, conf_ok = [], []
    dconf_nf, dconf_ok, vconf_nf, vconf_ok = [], [], [], []
    by_setup = collections.defaultdict(lambda: collections.Counter())
    seen = matched = no_exc = 0

    for db in sorted(glob.glob(os.path.expanduser(a.trades))):
        m = TRADE_DATE_RE.search(db)
        if not m or (a.since and m.group(1) < a.since):
            continue
        date = m.group(1)
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT * FROM trades WHERE status='closed'").fetchall()
            con.close()
        except Exception:                                        # noqa: BLE001
            continue
        for row in rows:
            seen += 1
            r = dict(row)
            key = (date, r.get("symbol"), _hhmm(r.get("entry_time")))
            sc = vec.get(key)
            if sc is None:
                continue
            matched += 1
            ax = decompose(sc)
            ent = float(r.get("entry_premium") or 0.0)
            mx = r.get("max_premium_seen")
            if ent <= 0 or mx is None:
                no_exc += 1
                continue
            mfe_pct = (float(mx) - ent) / ent * 100.0
            never = mfe_pct < a.nf_cut
            c = cells[(ax["direction"], ax["volatility"])]
            c["n"] += 1
            c["pnl"] += float(r.get("pnl_usd") or 0.0)
            if float(r.get("pnl_usd") or 0.0) > 0:
                c["win"] += 1
            if never:
                c["nf"] += 1
                conf_nf.append(ax["pair_conf"])
                dconf_nf.append(ax["direction_conf"])
                vconf_nf.append(ax["volatility_conf"])
            else:
                conf_ok.append(ax["pair_conf"])
                dconf_ok.append(ax["direction_conf"])
                vconf_ok.append(ax["volatility_conf"])
            st = (r.get("setup_type") or "?")[:26]
            by_setup[st][f'{ax["direction"]}/{ax["volatility"]}'] += 1

    print(f"closed trades: {seen}   matched to a score vector: {matched}   "
          f"no excursion telemetry: {no_exc}")
    if not conf_nf and not conf_ok:
        print("nothing scored — check --since and that trades carry "
              "max_premium_seen")
        return 0

    print(f"\n=== 3x3 CROSS-TAB (never-favourable cut = {a.nf_cut:.0f}% MFE) ===")
    print(f"  {'direction':<10}{'volatility':<14}{'n':>6}{'win%':>7}"
          f"{'net $':>11}{'never-fav':>11}")
    for d in DIRS:
        for v in VOLS:
            c = cells.get((d, v))
            if not c or not c["n"]:
                continue
            n = c["n"]
            thin = "  <- thin" if n < 15 else ""
            print(f"  {d:<10}{v:<14}{n:>6}{100.0*c['win']/n:>6.0f}%"
                  f"{c['pnl']:>11.0f}{100.0*c['nf']/n:>10.0f}%{thin}")

    MIN_ARM = 15

    def split(nf, ok, name):
        nf, ok = sorted(nf), sorted(ok)
        # v1.0 — REFUSE ON A THIN OR EMPTY ARM. The first planted run had
        # n_nf=0, `_pct([], 50)` returned 0.0, and the verdict logic read a
        # +0.900 gap out of an empty list and printed "SEPARATES". A tool that
        # announces a finding from no data is the laundered-green failure this
        # repo keeps catching; refuse loudly instead.
        if len(nf) < MIN_ARM or len(ok) < MIN_ARM:
            print(f"  {name:<18} REFUSED — arms too thin "
                  f"(nf={len(nf)}, ok={len(ok)}, need {MIN_ARM} each). "
                  f"Not a null result, an absent measurement.")
            return
        mn, mo = _pct(nf, 50), _pct(ok, 50)
        gap = mo - mn
        verdict = ("SEPARATES — a cutoff exists to find" if gap >= 0.05 else
                   "does NOT separate — no threshold will fix it"
                   if abs(gap) < 0.05 else
                   "INVERTED — higher score, worse outcome")
        print(f"  {name:<18} nf p50={mn:.3f}  ok p50={mo:.3f}  "
              f"gap={gap:+.3f}   {verdict}")

    print(f"\n=== THE TEST — median by outcome (n_nf={len(conf_nf)}, "
          f"n_ok={len(conf_ok)}) ===")
    split(dconf_nf, dconf_ok, "direction_conf")
    split(vconf_nf, vconf_ok, "volatility_conf")
    split(conf_nf, conf_ok, "pair_conf")
    print("\n  READ THE THIRD LINE AGAINST THE FIRST TWO. The claim is that the")
    print("  CONJUNCTION separates where its COMPONENTS do not. If pair_conf's")
    print("  gap is no better than the best component, it adds nothing and the")
    print("  idea is dead — record it as dead rather than re-litigating it.")
    print("  'never favourable' is a PRICE-PATH label, independent of stops and")
    print("  fills, so it cannot be contaminated by exit logic.")

    print("\n=== WHERE EACH SETUP ACTUALLY LIVES (top pair per setup) ===")
    for st, ctr in sorted(by_setup.items(), key=lambda kv: -sum(kv[1].values())):
        tot = sum(ctr.values())
        top = ctr.most_common(2)
        detail = "  ".join(f"{k} {100.0*c/tot:.0f}%" for k, c in top)
        print(f"  {st:<28}{tot:>5}   {detail}")
    return 0


if __name__ == "__main__":
    try:
        rc = main(sys.argv)
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        rc = 0
    sys.exit(rc)
