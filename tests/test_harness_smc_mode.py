#!/usr/bin/env python3
"""
tests/test_harness_smc_mode.py — does --engine smc actually change anything? v1.0
v1.0 — 2026-08-18 — INITIAL (fork: options_trader_smc).

Two properties of backtest_harness v1.3, both of which would fail SILENTLY —
the run would print a full report either way, and the report would look right:

  A. THE ENGINE IS ACTUALLY DRIVING. `build_regime_timeline(..., smc=engine)`
     must produce the SMC core's labels, not the v1.3 classifier's. A wiring
     mistake here yields a replay that is titled "SMC" and measures the old
     core — the worst possible outcome, because the acceptance test would then
     answer a question nobody asked.
  B. THE REVOCATION GATE IS MEASURED. The strategy census never reaches
     attempt_new_entry, where the gate lives on the box, so v1.3 asks
     entry_permitted() itself. If that recording is wrong the replay shows
     label changes and silently omits the withdrawal mechanism — which IS the
     mechanism under test.

The census path imports the broker SDK transitively (data.options_chain), so
this test STUBS `tastytrade` in sys.modules before importing. That is
deliberate and narrow: it lets the census branch be exercised off-box, and it
touches nothing the census actually computes. On control the real SDK is
present and the same code runs unstubbed.

Run:  cd <repo> && PYTHONPATH=. python3 tests/test_harness_smc_mode.py
Deliberate-failure proof: OT_HARNESS_SELFTEST=1 makes the engine permit
everything; case B must then go red.
"""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── stub the broker SDK so the census branch is reachable off-box ──────────
for _name in ("tastytrade", "tastytrade.instruments", "tastytrade.session",
              "tastytrade.market_data", "tastytrade.dxfeed",
              "tastytrade.streamer", "tastytrade.account", "tastytrade.order",
              "tastytrade.utils"):
    if _name not in sys.modules:
        _m = types.ModuleType(_name)
        _m.__getattr__ = lambda k: type(k, (), {})
        sys.modules[_name] = _m

from datetime import datetime, timedelta          # noqa: E402
from zoneinfo import ZoneInfo                     # noqa: E402

import numpy as np                                # noqa: E402
import pandas as pd                               # noqa: E402

import tests.backtest_harness as BH               # noqa: E402
from smc.smc_engine import SMCEngine, SetupState  # noqa: E402

ET = ZoneInfo("America/New_York")
FAILS = []


def check(name, ok, detail=""):
    if not ok:
        FAILS.append(name)
    print(f"  {'✅' if ok else '❌'} {name}{('  — ' + detail) if detail else ''}")


def _tape(days=2, n=390, seed=5):
    rng = np.random.default_rng(seed)
    rows, idx = [], []
    base = datetime(2026, 8, 17, 9, 30, tzinfo=ET)
    px = 560.0
    for d in range(days):
        start = base + timedelta(days=d)
        for i in range(n):
            px += rng.normal(0.01, 0.08)
            o = px
            c = px + rng.normal(0, 0.05)
            h = max(o, c) + abs(rng.normal(0, 0.05))
            l = min(o, c) - abs(rng.normal(0, 0.05))
            idx.append(start + timedelta(minutes=i))
            rows.append([o, h, l, c, 100000.0])
            px = c
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"],
                        index=pd.DatetimeIndex(idx))


class _AlwaysRevoked(SMCEngine):
    """A core whose gate is CLOSED in both directions, so the census must
    record every directional setup as revoked. Nothing else is changed —
    labels still come from the real classify path."""

    def entry_permitted(self, direction):
        if os.environ.get("OT_HARNESS_SELFTEST", "0") == "1":
            return True                      # deliberate corruption
        return False


class _Sig:
    def __init__(self, side):
        self.option_side = side
        self.strategy_name = "stub"

    def is_valid(self):
        return True


def main():
    df = _tape()
    vix = pd.DataFrame({"open": 15.0, "high": 15.0, "low": 15.0,
                        "close": 15.0, "volume": 0.0}, index=df.index)

    # ── A. the engine drives the label ────────────────────────────────────
    BH._SMC_TRANSITIONS.clear()
    BH._SMC_ERRORS.clear()
    BH._SMC_LAST["phase"] = None
    eng = SMCEngine(state_dir=None)
    tl_smc = BH.build_regime_timeline(df, vix, set(), 1, None, eng)
    tl_v13 = BH.build_regime_timeline(df, vix, set(), 1, None, None)

    check("smc mode produces a timeline", len(tl_smc) > 100, str(len(tl_smc)))
    labels_smc = {str(v[0]) for v in tl_smc.values()}
    labels_v13 = {str(v[0]) for v in tl_v13.values()}
    check("labels differ from the v1.3 classifier's",
          labels_smc != labels_v13 or
          [v[0] for v in tl_smc.values()] != [v[0] for v in tl_v13.values()],
          f"smc={sorted(labels_smc)} v13={sorted(labels_v13)}")
    check("no SMC tick errors (a mixed-engine run is not an SMC run)",
          not BH._SMC_ERRORS, "; ".join(BH._SMC_ERRORS[:2]))
    check("conviction is the structural fraction, in [0,1]",
          all(0.0 <= float(v[1].conviction) <= 1.0 for v in tl_smc.values()))

    # ── B. the gate verdict is recorded per census setup ──────────────────
    stats = {n: {"evals": 0, "setups": 0, "valid": 0, "invalid": 0,
                 "raised": 0, "last_error": "", "by_regime": {},
                 "permitted": 0, "revoked": 0, "revoked_at": []}
             for n in ("Continuation", "SweepReversal", "IronCondor")}
    census = {
        "bs": BH.PremiumModel(dte=0),
        "cont": type("C", (), {"generate_signal": lambda *a, **k: _Sig("call")})(),
        "sweep": type("S", (), {"generate_signal": lambda *a, **k: _Sig("put")})(),
        "condor": None,
        "condor_mod": sys.modules[__name__],
        "condor_run": lambda *a, **k: None,       # direction-neutral: never gated
        "stats": stats,
    }
    BH._SMC_TRANSITIONS.clear()
    BH._SMC_LAST["phase"] = None
    BH.build_regime_timeline(df, vix, set(), 1, census, _AlwaysRevoked(state_dir=None))

    cont, sweep, condor = stats["Continuation"], stats["SweepReversal"], stats["IronCondor"]
    check("the census ran", cont["setups"] > 0, f"setups={cont['setups']}")
    check("a closed gate records REVOKED, not permitted",
          cont["revoked"] > 0 and cont["permitted"] == 0,
          f"permitted={cont['permitted']} revoked={cont['revoked']}")
    check("both directions are gated (call and put)",
          sweep["revoked"] > 0, f"sweep revoked={sweep['revoked']}")
    check("each revocation records when, which way, and the setup state",
          bool(cont["revoked_at"]) and len(cont["revoked_at"][0]) == 5,
          str(cont["revoked_at"][:1]))
    check("a direction-neutral setup is never gated",
          condor["revoked"] == 0)

    # ── C. an open gate must NOT be recorded as revoked ────────────────────
    for st in stats.values():
        st.update({"permitted": 0, "revoked": 0, "revoked_at": [], "setups": 0,
                   "evals": 0, "by_regime": {}})
    BH._SMC_LAST["phase"] = None
    BH.build_regime_timeline(df, vix, set(), 1, census, SMCEngine(state_dir=None))
    check("a permissive engine records permitted, not revoked",
          stats["Continuation"]["permitted"] > 0,
          f"permitted={stats['Continuation']['permitted']} "
          f"revoked={stats['Continuation']['revoked']}")

    print()
    if FAILS:
        print(f"harness_smc_mode: {len(FAILS)} FAILED — " + "; ".join(FAILS))
        return 1
    print("harness_smc_mode: ALL PASS (engine drives · gate measured both "
          "directions · neutral exempt · permissive not mislabelled)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
