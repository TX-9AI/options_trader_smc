#!/usr/bin/env python3
"""
tests/test_engine_provenance.py — F.2a: is the entry core ON THE ROW? v1.0
v1.0 — 2026-08-18 — INITIAL (fork: options_trader_smc).

`regime_engine` existed as a column since v-eng (2026-07-30) and main.py's
changelog claimed trades carried it — but no caller ever set it, so every row
on every box holds the '' default. A column that is documented as persisted
and never written is the exact failure this repo keeps re-learning, and it is
invisible to import, to py_compile and to any grep for the column name.

So this test WRITES ROWS AND READS THE COLUMN BACK (WA §21 — exercise the
decision, never the source). Against a temp DB, never the real one.

Run:  cd <repo> && PYTHONPATH=. python3 tests/test_engine_provenance.py
Deliberate-failure proof: OT_PROV_SELFTEST=1 blanks the module tag mid-run;
case A must then go red. A test that has never failed proves nothing.
"""

import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database.trade_logger as TL          # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    if not ok:
        FAILS.append(name)
    print(f"  {'✅' if ok else '❌'} {name}{('  — ' + detail) if detail else ''}")


def _row_engine(db, trade_id):
    con = sqlite3.connect(db)
    try:
        cur = con.execute(
            "SELECT regime_engine FROM trades WHERE trade_id = ?", (trade_id,))
        r = cur.fetchone()
        return None if r is None else r[0]
    finally:
        con.close()


def _rec(tid, **kw):
    r = TL.make_record(trade_id=tid, symbol="QQQ", strategy="ORBStrategy",
                       option_side="call", contracts=1, entry_premium=1.0)
    r.update(kw)
    return r


def main():
    with tempfile.TemporaryDirectory() as td:
        db = os.path.join(td, "trades_test.db")

        # ── A. the stamp lands on a record that did not supply one ──────────
        TL.set_engine_tag("SMC")
        if os.environ.get("OT_PROV_SELFTEST", "0") == "1":
            TL._ENGINE_TAG = ""          # deliberate corruption
        lg = TL.TradeLogger(db_path=db, paper_trading=True)
        lg.log_entry(_rec("t-A"))
        got = _row_engine(db, "t-A")
        check("A: unstamped record gets the resolved tag", got == "SMC",
              f"regime_engine={got!r}")

        # ── B. a caller-supplied value WINS (never silently overwritten) ────
        lg.log_entry(_rec("t-B", regime_engine="L2"))
        got = _row_engine(db, "t-B")
        check("B: explicit caller value is not overwritten", got == "L2",
              f"regime_engine={got!r}")

        # ── C. no tag set → '' , which reads as NOT RECORDED, not as a lie ──
        TL.set_engine_tag("")
        lg.log_entry(_rec("t-C"))
        got = _row_engine(db, "t-C")
        check("C: empty tag leaves '' (honest 'not recorded')",
              (got or "") == "", f"regime_engine={got!r}")

        # ── D. the column survives the MIGRATION path, not just CREATE ──────
        # The real QQQ box has a trades table built long before this column
        # existed; the ALTER path is the one that will actually run there.
        db2 = os.path.join(td, "legacy.db")
        con = sqlite3.connect(db2)
        con.execute("CREATE TABLE trades (trade_id TEXT PRIMARY KEY, "
                    "symbol TEXT, status TEXT, entry_time TEXT)")
        con.commit()
        con.close()
        TL.set_engine_tag("SMC")
        lg2 = TL.TradeLogger(db_path=db2, paper_trading=True)
        cols = {r[1] for r in sqlite3.connect(db2)
                .execute("PRAGMA table_info(trades)")}
        check("D: migration adds regime_engine to a pre-existing table",
              "regime_engine" in cols)
        lg2.log_entry(_rec("t-D"))
        got = _row_engine(db2, "t-D")
        check("D2: and rows written after migration carry the tag",
              got == "SMC", f"regime_engine={got!r}")

    print()
    if FAILS:
        print(f"engine_provenance: {len(FAILS)} FAILED — " + "; ".join(FAILS))
        return 1
    print("engine_provenance: ALL PASS "
          "(A stamp · B caller wins · C honest blank · D migration path)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
