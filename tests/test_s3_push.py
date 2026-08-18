#!/usr/bin/env python3
# options_trader_v3/tests/test_s3_push.py — v1.8
"""
Behavioural proof for warehouse/s3_push.py against planted archives.

CHANGELOG
    v1.8 — 2026-08-16 — ORB tests removed alongside the stage. They asserted
           real behaviour and passed; they are deleted because the FEATURE went,
           not because they failed. The stage-order assertions drop from eleven
           names to ten — an order test is only worth having if it covers the
           stages that actually exist.
    v1.7 — 2026-08-16 — WH.8a: regime_log + circuit_breaker_events. The check
           that matters is the ELEVEN-stage order assertion — it is only worth
           having if it covers every stage, and two new streams would otherwise
           slip in unordered.
    v1.6 — 2026-08-16 — WH.14: the liquidity ledger stream, and a re-assertion
           of the stage order now that a ninth stream exists — the ordering
           test is only worth having if it covers every stage, not the eight it
           was written against.
    v1.5 — 2026-08-13 — WH.6: the lock. The case that matters is the DELIBERATE
           contention one — a second pusher, with the lock already held, must
           not push and must not corrupt the first one's ledger.
    v1.4 — 2026-08-13 — WH.5: pins the STAGE ORDER. The fault it guards against
           is not a crash — every stream worked — it was that the bulk journal
           ran early and starved the small perishable streams behind it for a
           whole evening. Order is a correctness property here, so it is
           asserted rather than left to reading the source.
    v1.3 — 2026-08-13 — WH.4: prefix counters, incremental flush, and verify.
           The flush test is the important one — it asserts that a drain KILLED
           partway leaves progress behind, which is the failure v1.0-v1.2 would
           have hit silently the first time a journal backlog ran past
           TimeoutStartSec.
    v1.2 — 2026-08-13 — WH.3 coverage: journal/shadow jsonl trees, OHLC and EOD
           whole-file pushes, candle high-water marks, the VIX single-writer
           rule, and ORB capture-on-state. Includes the negative cases that
           matter — a non-ESTABLISHED ORB must NOT be captured, and a non-SPX
           box must NOT push VIX.
    v1.1 — 2026-08-13 — trades coverage, and a REAL idempotency test. The v1.0
           "lost ledger -> no duplicates" check passed by accident: both pushes
           ran inside the same second, so the envelope's `pushed_at_utc` — which
           v1.0 folded into the key hash — happened to match. It now forces the
           clock forward between pushes, which fails against v1.0 and passes
           against v1.1's content-only hash.
    v1.0 — 2026-08-12 — initial release, alongside s3_push v1.0.

No AWS, no moto: a stub client records every put and serves gets back, so the
verify path is exercised for real. Includes DELIBERATE-FAILURE cases — a stub
that corrupts on read, and one that rejects a put — because a verify step that
cannot be made to fail is not a verify step.
"""

import gzip
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

TMP = tempfile.mkdtemp(prefix="s3push_")
os.environ["OT_CHAIN_ROOT"] = os.path.join(TMP, "chain_snapshots")
os.environ["OT_WAREHOUSE_STATE"] = os.path.join(TMP, "state")

from warehouse import s3_push  # noqa: E402

s3_push.SRC_ROOT = os.environ["OT_CHAIN_ROOT"]
s3_push.LEDGER_PATH = os.path.join(os.environ["OT_WAREHOUSE_STATE"], "chain_ledger.json")

FAILS = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else "  <- " + str(detail)))
    if not cond:
        FAILS.append(name)


class StubS3:
    """Records objects. mangle=True corrupts on read; reject=True refuses puts."""

    def __init__(self, mangle=False, reject=False):
        self.store = {}
        self.puts = 0
        self.mangle = mangle
        self.reject = reject

    def put_object(self, Bucket, Key, Body):
        if self.reject:
            raise RuntimeError("AccessDenied (simulated)")
        self.puts += 1
        self.store[Key] = Body
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def get_object(self, Bucket, Key):
        data = self.store[Key]
        if self.mangle:
            data = data + b"tamper"

        class _B:
            def read(self_inner):
                return data

        return {"Body": _B()}


def snap(ts_et, sym, n=3):
    return {
        "ts_et": ts_et,
        "symbol": sym,
        "event": "chain_snapshot",
        "expiry": "2026-08-12",
        "underlying": 431.25,
        "regime": "TRENDING_BULL",
        "n_calls": n,
        "n_puts": n,
        "contracts": [
            {"occ": "X%d" % i, "type": "C", "strike": 400 + i, "bid": 1.0, "ask": 1.1,
             "mark": 1.05, "delta": 0.5, "gamma": 0.01, "theta": -0.2, "vega": 0.03,
             "iv": 0.22, "oi": 10, "vol": 5}
            for i in range(n * 2)
        ],
    }


def write_archive(day, sym, records, partial_tail=False):
    d = os.path.join(os.environ["OT_CHAIN_ROOT"], day)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, sym + ".jsonl.gz")
    for r in records:
        with gzip.open(p, "ab") as f:
            f.write((json.dumps(r) + "\n").encode())
    if partial_tail:
        with gzip.open(p, "ab") as f:
            f.write(b'{"ts_et": "2026-08-12T14:5')  # no newline, mid-write
    return p


def reset():
    shutil.rmtree(os.environ["OT_CHAIN_ROOT"], ignore_errors=True)
    shutil.rmtree(os.environ["OT_WAREHOUSE_STATE"], ignore_errors=True)


print("\n=== s3_push v1.0 behavioural proof ===\n")

# 1 — a clean push of three snapshots
reset()
p = write_archive("2026-08-12", "SPX", [snap("2026-08-12T09:35:00-04:00", "SPX"),
                                        snap("2026-08-12T09:40:00-04:00", "SPX"),
                                        snap("2026-08-12T09:45:00-04:00", "SPX")])
s3 = StubS3()
led = {}
pushed, failed = s3_push.push_file(s3, "B", p, "2026-08-12", "SPX", led)
check("3 snapshots pushed", pushed == 3, pushed)
check("0 failed", failed == 0, failed)
check("ledger records 3 confirmed", led[p]["n"] == 3, led.get(p))
keys = sorted(s3.store)
check("hive dt= partition in key", all("/dt=2026-08-12/" in k for k in keys), keys[:1])
check("hive sym= partition in key", all("/sym=SPX/" in k for k in keys), keys[:1])
check("raw/ prefix", all(k.startswith("raw/chain_snapshots/") for k in keys), keys[:1])
body0 = json.loads(s3.store[keys[0]])
check("schema_version stamped", body0["schema_version"] == 1, body0.get("schema_version"))
check("gamma+vega survive the round trip",
      body0["record"]["contracts"][0]["gamma"] == 0.01
      and body0["record"]["contracts"][0]["vega"] == 0.03)
check("provenance carries host+line", "src_host" in body0 and body0["src_line"] == 0)

# 2 — resume: a second run over the same file pushes nothing
pushed2, _ = s3_push.push_file(s3, "B", p, "2026-08-12", "SPX", led)
check("re-run pushes 0 (ledger resume)", pushed2 == 0, pushed2)
check("no duplicate objects", len(s3.store) == 3, len(s3.store))

# 3 — append two more, only the new ones go
write_archive("2026-08-12", "SPX", [snap("2026-08-12T09:50:00-04:00", "SPX"),
                                    snap("2026-08-12T09:55:00-04:00", "SPX")])
pushed3, _ = s3_push.push_file(s3, "B", p, "2026-08-12", "SPX", led)
check("appended 2 -> pushed exactly 2", pushed3 == 2, pushed3)
check("5 objects total", len(s3.store) == 5, len(s3.store))

# 4 — idempotency: same content re-pushed lands on the SAME key
s3b = StubS3()
led_b = {}
s3_push.push_file(s3b, "B", p, "2026-08-12", "SPX", led_b)
first_keys = set(s3b.store)
led_b.clear()  # simulate a lost ledger -> full re-push
s3_push.push_file(s3b, "B", p, "2026-08-12", "SPX", led_b)
check("lost ledger re-push creates NO duplicates (content-hash key)",
      set(s3b.store) == first_keys and len(s3b.store) == 5, len(s3b.store))

# 5 — a partially written trailing line is not pushed, and does not advance
reset()
p2 = write_archive("2026-08-12", "QQQ", [snap("2026-08-12T10:00:00-04:00", "QQQ"),
                                         snap("2026-08-12T10:05:00-04:00", "QQQ")],
                   partial_tail=True)
s3c = StubS3()
led_c = {}
pushed4, _ = s3_push.push_file(s3c, "B", p2, "2026-08-12", "QQQ", led_c)
check("partial tail: only complete lines push", pushed4 == 2, pushed4)
check("offset stops at the complete lines", led_c[p2]["n"] == 2, led_c.get(p2))

# 6 — DELIBERATE FAILURE: read-back mismatch must NOT confirm
reset()
p3 = write_archive("2026-08-12", "MU", [snap("2026-08-12T11:00:00-04:00", "MU")])
s3d = StubS3(mangle=True)
led_d = {}
pushed5, failed5 = s3_push.push_file(s3d, "B", p3, "2026-08-12", "MU", led_d)
check("tampered read-back -> 0 confirmed", pushed5 == 0, pushed5)
check("tampered read-back -> counted as failed", failed5 == 1, failed5)
check("tampered read-back -> ledger NOT advanced", p3 not in led_d, led_d)
check("the PUT did happen (so this proves VERIFY caught it)", s3d.puts == 1, s3d.puts)

# 7 — DELIBERATE FAILURE: rejected put must not confirm, and must not raise
s3e = StubS3(reject=True)
led_e = {}
pushed6, failed6 = s3_push.push_file(s3e, "B", p3, "2026-08-12", "MU", led_e)
check("rejected put -> 0 confirmed, no exception", pushed6 == 0 and failed6 == 1)
check("rejected put -> ledger untouched", led_e == {}, led_e)

# 8 — retry after an outage resumes and confirms
s3f = StubS3()
pushed7, failed7 = s3_push.push_file(s3f, "B", p3, "2026-08-12", "MU", led_e)
check("retry after outage confirms", pushed7 == 1 and failed7 == 0, (pushed7, failed7))

# 9 — a shrunk file restarts rather than skipping
led_f = {p3: {"n": 99, "last_sha": "x", "last_key": "x", "confirmed_utc": "x"}}
s3g = StubS3()
pushed8, _ = s3_push.push_file(s3g, "B", p3, "2026-08-12", "MU", led_f)
check("stale offset past EOF -> restart from 0", pushed8 == 1, pushed8)

# 10 — idle box: discover finds nothing, main() is silent and returns 0
reset()
os.makedirs(os.environ["OT_CHAIN_ROOT"], exist_ok=True)
check("idle box discovers no files", s3_push.discover() == [], s3_push.discover())
rc = s3_push.main([])
check("idle box main() returns 0", rc == 0, rc)

# 11 — ledger survives a round trip to disk
led_g = {"/x": {"n": 4, "last_sha": "abc", "last_key": "k", "confirmed_utc": "t"}}
check("ledger saves", s3_push.save_ledger(led_g, s3_push.LEDGER_PATH))
check("ledger reloads identically", s3_push.load_ledger(s3_push.LEDGER_PATH) == led_g)

# 12 — never raises even when the source root is nonsense
s3_push.SRC_ROOT = "/nonexistent/nope"
check("missing root -> empty discover, no raise", s3_push.discover("/nonexistent/nope") == [])
check("main() with missing root returns 0", s3_push.main([]) == 0)


# 13 — IDEMPOTENCY ACROSS A CLOCK CHANGE (this is the v1.0 bug, made visible)
reset()
p4 = write_archive("2026-08-12", "AAPL", [snap("2026-08-12T12:00:00-04:00", "AAPL")])
s3h = StubS3()
led_h = {}
s3_push._now_utc = lambda: "2026-08-12T16:00:00+00:00"
s3_push.push_file(s3h, "B", p4, "2026-08-12", "AAPL", led_h)
keys_first = set(s3h.store)
led_h.clear()                                   # ledger lost
s3_push._now_utc = lambda: "2026-08-12T16:05:11+00:00"   # clock has MOVED
s3_push.push_file(s3h, "B", p4, "2026-08-12", "AAPL", led_h)
check("re-push at a DIFFERENT second reuses the same key (no duplicate)",
      set(s3h.store) == keys_first and len(s3h.store) == 1, sorted(s3h.store))

# 14 — trades: mutation lands as a second object, unchanged rows cost nothing
import sqlite3 as _sq
dbp = os.path.join(TMP, "trades.db")
con = _sq.connect(dbp)
con.execute("CREATE TABLE trades (trade_id INTEGER PRIMARY KEY, symbol TEXT,"
            " entry_time TEXT, status TEXT, pnl_usd REAL, entry_snapshot TEXT)")
con.execute("INSERT INTO trades VALUES (1,'SPX','2026-08-12T14:23:16+00:00',"
            "'open',NULL,'{\"fvg\": []}')")
con.commit(); con.close()
s3t = StubS3()
led_t = {}
pt, ft = s3_push.push_trades(s3t, "B", dbp, led_t)
check("open trade pushed", pt == 1 and ft == 0, (pt, ft))
k = sorted(s3t.store)[0]
check("trade key buckets by ET trading day, not UTC date", "/dt=2026-08-12/" in k, k)
check("trade key partitions by symbol", "/sym=SPX/" in k, k)
body = json.loads(s3t.store[k])
check("all columns survive verbatim", body["record"]["entry_snapshot"] == '{"fvg": []}')
check("trade_id + status surfaced into envelope",
      body["trade_id"] == 1 and body["status"] == "open")

pt2, _ = s3_push.push_trades(s3t, "B", dbp, led_t)
check("unchanged trade re-push costs 0 objects", pt2 == 0 and len(s3t.store) == 1,
      (pt2, len(s3t.store)))

con = _sq.connect(dbp)
con.execute("UPDATE trades SET status='closed', pnl_usd=412.5 WHERE trade_id=1")
con.commit(); con.close()
pt3, _ = s3_push.push_trades(s3t, "B", dbp, led_t)
check("CLOSING the trade lands a SECOND object (change-data-capture)",
      pt3 == 1 and len(s3t.store) == 2, (pt3, len(s3t.store)))
states = sorted(json.loads(v)["status"] for v in s3t.store.values())
check("both states retrievable: open AND closed", states == ["closed", "open"], states)

# 15 — a missing/locked trades.db degrades to nothing, never raises
pn, fn = s3_push.push_trades(StubS3(), "B", "/nonexistent/trades.db", {})
check("missing trades.db -> 0/0, no raise", (pn, fn) == (0, 0), (pn, fn))


# ── WH.3 ────────────────────────────────────────────────────────────────────
import sqlite3 as _s3q
W = os.path.join(TMP, "wh3")
os.makedirs(W, exist_ok=True)
s3_push.JOURNAL_ROOT = os.path.join(W, "signal_journal")
s3_push.SHADOW_ROOT = os.path.join(W, "shadow")
s3_push.OHLC_ROOT = os.path.join(W, "OHLC")

def _mk(root, day, sym, lines, ext=".jsonl"):
    d = os.path.join(root, day); os.makedirs(d, exist_ok=True)
    p_ = os.path.join(d, sym + ext)
    with open(p_, "a") as f:
        for l in lines:
            f.write(l + "\n")
    return p_

# 16 — journal: ruleset and event lifted into the envelope
jp = _mk(s3_push.JOURNAL_ROOT, "2026-08-13", "SPX", [
    json.dumps({"ts_et": "2026-08-13T09:45:00-04:00", "symbol": "SPX",
                "event": "readiness", "ruleset": "0d70673", "readiness": {"x": 1}})])
s3j = StubS3(); ledj = {}
pj, fj = s3_push.push_jsonl_tree(s3j, "B", s3_push.JOURNAL_ROOT, "signal_journal", ledj)
check("journal line pushed", pj == 1 and fj == 0, (pj, fj))
kj = sorted(s3j.store)[0]
bj = json.loads(s3j.store[kj])
check("journal key: raw/signal_journal/dt=/sym=",
      kj.startswith("raw/signal_journal/dt=2026-08-13/sym=SPX/"), kj)
check("ruleset lifted into envelope", bj["ruleset"] == "0d70673", bj.get("ruleset"))
check("event lifted into envelope", bj["event"] == "readiness", bj.get("event"))
check("journal re-run pushes 0",
      s3_push.push_jsonl_tree(s3j, "B", s3_push.JOURNAL_ROOT, "signal_journal", ledj)[0] == 0)

# 17 — OHLC: ONE object per file, not per candle
_mk(s3_push.OHLC_ROOT, "2026-08-13", "SPX",
    ["timestamp,open,high,low,close,volume"] +
    ["2026-08-13T09:3%d:00-04:00,1,2,0,1,100" % i for i in range(9)], ext=".csv")
s3o = StubS3(); ledo = {}
po, fo = s3_push.push_whole_files(s3o, "B", s3_push.discover(s3_push.OHLC_ROOT, ".csv"), "ohlc", ledo)
check("OHLC day-file -> exactly 1 object (not 1/candle)", po == 1 and len(s3o.store) == 1, (po, len(s3o.store)))
check("OHLC content preserved verbatim",
      "timestamp,open,high,low,close,volume" in json.loads(list(s3o.store.values())[0])["record"])
check("OHLC unchanged re-run pushes 0",
      s3_push.push_whole_files(s3o, "B", s3_push.discover(s3_push.OHLC_ROOT, ".csv"), "ohlc", ledo)[0] == 0)

# 18 — candles: high-water mark, all intervals, VIX single-writer
fdb = os.path.join(W, "feed_store.db")
con = _s3q.connect(fdb)
con.execute("CREATE TABLE candles (symbol TEXT, interval TEXT, ts_epoch_ms INTEGER,"
            " open REAL, high REAL, low REAL, close REAL, volume REAL)")
for iv in ("1m", "5m"):
    for i in range(3):
        con.execute("INSERT INTO candles VALUES ('SPX',?,?,1,2,0,1,10)", (iv, 1786651740000 + i * 60000))
con.execute("INSERT INTO candles VALUES ('VIX','1m',1786651740000,1,2,0,1,10)")
con.commit(); con.close()

s3c = StubS3(); ledc = {}
pc, fc = s3_push.push_candles(s3c, "B", fdb, ledc, "NVDA")
check("non-SPX box does NOT push VIX",
      all("sym=VIX" not in k for k in s3c.store), sorted(s3c.store))
check("both intervals pushed as separate objects", pc == 2, pc)
check("interval= is a partition level",
      any("/interval=5m/" in k for k in s3c.store), sorted(s3c.store))
check("candles re-run pushes 0 (high-water mark)",
      s3_push.push_candles(s3c, "B", fdb, ledc, "NVDA")[0] == 0)

s3v = StubS3()
pv, _ = s3_push.push_candles(s3v, "B", fdb, {}, "SPX")
check("SPX box DOES push VIX", any("sym=VIX" in k for k in s3v.store), sorted(s3v.store))

# 20 — own_symbol reads the instrument off the OHLC tree
check("own_symbol() derives instrument from OHLC dir", s3_push.own_symbol() == "SPX", s3_push.own_symbol())


# ── WH.4 ────────────────────────────────────────────────────────────────────
class ListStub(StubS3):
    """StubS3 plus the paginator surface verify() uses."""
    def get_paginator(self, _op):
        store = self.store
        class _P:
            def paginate(self_inner, Bucket=None, Prefix="", **kw):
                yield {"Contents": [{"Key": k, "Size": len(v)}
                                    for k, v in store.items() if k.startswith(Prefix)]}
        return _P()

# 21 — counters accrue per dt=/sym= prefix
reset()
pc1 = write_archive("2026-08-12", "SPX", [snap("2026-08-12T09:35:00-04:00", "SPX"),
                                          snap("2026-08-12T09:40:00-04:00", "SPX")])
s3k = ListStub(); ledk = {}; cnt = {}
s3_push.push_file(s3k, "B", pc1, "2026-08-12", "SPX", ledk, cnt)
pfx = "raw/chain_snapshots/dt=2026-08-12/sym=SPX/"
check("counter keyed by dt=/sym= prefix", pfx in cnt, list(cnt))
check("counter n matches objects pushed", cnt[pfx]["n"] == 2, cnt.get(pfx))
check("counter bytes are non-zero", cnt[pfx]["bytes"] > 0, cnt.get(pfx))

# 22 — verify agrees when S3 holds everything
short, loc, rem = s3_push.verify(s3k, "B", cnt)
check("verify: no short prefixes on a clean push", short == [], short)
check("verify: local and s3 totals agree", loc == rem == 2, (loc, rem))

# 23 — DELIBERATE FAILURE: an object vanishing from S3 must be reported SHORT
s3k.store.pop(sorted(s3k.store)[0])
short2, loc2, rem2 = s3_push.verify(s3k, "B", cnt)
check("verify CATCHES a missing object", len(short2) == 1 and rem2 == 1, (short2, rem2))

# 24 — DELIBERATE FAILURE: a truncated object must be reported SHORT (bytes)
s3m = ListStub(); ledm = {}; cntm = {}
s3_push.push_file(s3m, "B", pc1, "2026-08-12", "SPX", ledm, cntm)
k0 = sorted(s3m.store)[0]
s3m.store[k0] = b"x"                       # same count, far fewer bytes
short3, _, _ = s3_push.verify(s3m, "B", cntm)
check("verify CATCHES truncation via BYTES (count alone would pass)",
      len(short3) == 1, short3)

# 25 — incremental flush: a drain killed partway leaves progress on disk
reset()
os.makedirs(os.environ["OT_WAREHOUSE_STATE"], exist_ok=True)
lp = os.path.join(os.environ["OT_WAREHOUSE_STATE"], "flush_probe.json")
s3_push._OPEN.clear(); s3_push._SINCE_FLUSH[0] = 0
s3_push.FLUSH_EVERY = 2
led_f = s3_push.load_ledger(lp)
pf = write_archive("2026-08-12", "MU", [snap("2026-08-12T09:3%d:00-04:00" % i, "MU")
                                        for i in range(4)])
s3f = ListStub(); cf = {}
s3_push.push_file(s3f, "B", pf, "2026-08-12", "MU", led_f, cf)
on_disk = s3_push.load_ledger(lp)
check("ledger persisted MID-drain, not only at the end",
      on_disk.get(pf, {}).get("n", 0) >= 2, on_disk)
s3_push.FLUSH_EVERY = 200


# 26 — stage order: perishable-and-small first, bulk last
import inspect as _insp
_src = _insp.getsource(s3_push.main)
_order = [n for n in ("trades", "eod", "ohlc", "candles",
                      "chain_snapshots", "shadow", "signal_journal")
          if '("%s"' % n in _src]
_pos = {n: _src.index('("%s"' % n) for n in _order}
check("stage order is declared for all 7 streams", len(_order) == 7, _order)
check("trades runs before signal_journal", _pos["trades"] < _pos["signal_journal"])
check("eod runs before signal_journal", _pos["eod"] < _pos["signal_journal"])
check("ohlc runs before signal_journal (the starvation that happened)",
      _pos["ohlc"] < _pos["signal_journal"])
check("candles runs before signal_journal", _pos["candles"] < _pos["signal_journal"])
check("signal_journal is LAST", _pos["signal_journal"] == max(_pos.values()))


# 27 — the lock: one pusher at a time
reset()
os.makedirs(os.environ["OT_WAREHOUSE_STATE"], exist_ok=True)
s3_push.LOCK_PATH = os.path.join(os.environ["OT_WAREHOUSE_STATE"], "s3_push.lock")
h1 = s3_push.acquire_lock(0)
check("first caller takes the lock", h1 is not None)
h2 = s3_push.acquire_lock(0)
check("SECOND caller is refused while it is held", h2 is None)
import time as _t
_t0 = _t.time()
h3 = s3_push.acquire_lock(2)
check("a waiting caller gives up after its budget", h3 is None and _t.time() - _t0 >= 2,
      round(_t.time() - _t0, 1))
h1.close()
h4 = s3_push.acquire_lock(0)
check("lock is reacquirable once released", h4 is not None)
h4.close()

# 28 — a held lock must not let a second run touch the ledger
reset()
p5 = write_archive("2026-08-12", "GS", [snap("2026-08-12T09:35:00-04:00", "GS")])
held = s3_push.acquire_lock(0)
s3_push._OPEN.clear()
lp2 = os.path.join(os.environ["OT_WAREHOUSE_STATE"], "contend.json")
led_x = s3_push.load_ledger(lp2)
led_x[p5] = {"n": 1, "last_sha": "sentinel", "confirmed_utc": "t"}
s3_push.save_ledger(led_x, lp2)
blocked = s3_push.acquire_lock(0)
check("contending run cannot proceed", blocked is None)
check("the first run's ledger entry is intact",
      s3_push.load_ledger(lp2)[p5]["last_sha"] == "sentinel")
held.close()


# 29 — liquidity ledger (LIQ.4) reaches the warehouse
reset()
s3_push.LIQ_ROOT = os.path.join(TMP, "liquidity_ledger")
d = os.path.join(s3_push.LIQ_ROOT, "2026-08-17")
os.makedirs(d, exist_ok=True)
book = {"symbol": "SPX", "date_et": "2026-08-17",
        "levels": [{"price": 7777.5, "touches": 3}]}
json.dump(book, open(os.path.join(d, "SPX.json"), "w"))
s3l = ListStub(); ledl = {}; cntl = {}
pl, fl = s3_push.push_whole_files(
    s3l, "B", s3_push.discover(s3_push.LIQ_ROOT, ".json"), "liquidity_ledger", ledl, cntl)
check("liquidity ledger pushed", pl == 1 and fl == 0, (pl, fl))
kl = sorted(s3l.store)[0]
check("ledger key: raw/liquidity_ledger/dt=/sym=",
      kl.startswith("raw/liquidity_ledger/dt=2026-08-17/sym=SPX/"), kl)
check("ledger content preserved verbatim",
      "7777.5" in json.loads(s3l.store[kl])["record"])
check("unchanged ledger re-push costs 0",
      s3_push.push_whole_files(s3l, "B", s3_push.discover(s3_push.LIQ_ROOT, ".json"),
                               "liquidity_ledger", ledl, cntl)[0] == 0)
# the ledger is rewritten every closed bar — a CHANGED book must land separately
book["levels"].append({"price": 7760.0, "touches": 1})
json.dump(book, open(os.path.join(d, "SPX.json"), "w"))
pl2, _ = s3_push.push_whole_files(
    s3l, "B", s3_push.discover(s3_push.LIQ_ROOT, ".json"), "liquidity_ledger", ledl, cntl)
check("a CHANGED level book lands as its own object (evolution survives)",
      pl2 == 1 and len(s3l.store) == 2, len(s3l.store))

# 30 — stage order still holds with NINE streams
_src2 = _insp.getsource(s3_push.main)
_names = ("trades", "eod", "ohlc", "candles", "liquidity_ledger",
          "chain_snapshots", "shadow", "signal_journal")
_pos2 = {n: _src2.index('("%s"' % n) for n in _names if '("%s"' % n in _src2}
check("all EIGHT stages are declared", len(_pos2) == 8, sorted(_pos2))
check("liquidity_ledger runs before the bulk streams",
      _pos2["liquidity_ledger"] < _pos2["signal_journal"]
      and _pos2["liquidity_ledger"] < _pos2["chain_snapshots"], _pos2)
check("signal_journal is STILL last", _pos2["signal_journal"] == max(_pos2.values()))


# 31 — regime_log + circuit_breaker: append-only tables reach the warehouse
reset()
dbp2 = os.path.join(TMP, "trades2.db")
con = _s3q.connect(dbp2)
con.execute("CREATE TABLE regime_log (id INTEGER PRIMARY KEY, logged_at TEXT,"
            " regime TEXT, conviction REAL, macro_context TEXT, adx REAL,"
            " trigger TEXT, engine TEXT)")
con.execute("INSERT INTO regime_log VALUES (1,'2026-08-14T13:45:00+00:00',"
            "'TRENDING_BULL',0.75,'RISK_ON',28.4,'breakout','L2')")
con.execute("CREATE TABLE circuit_breaker_events (id INTEGER PRIMARY KEY,"
            " event_time TEXT, reason TEXT)")
con.execute("INSERT INTO circuit_breaker_events VALUES (1,"
            "'2026-08-14T18:02:00+00:00','daily_loss')")
con.commit(); con.close()

s3rg = ListStub(); ledrg = {}; cntrg = {}
pr_, fr_ = s3_push.push_table(s3rg, "B", dbp2, "regime_log", "logged_at",
                              "regime_log", ledrg, "SPX", cntrg)
check("regime_log row pushed", pr_ == 1 and fr_ == 0, (pr_, fr_))
krg = sorted(s3rg.store)[0]
check("regime_log key buckets by ET trading day",
      krg.startswith("raw/regime_log/dt=2026-08-14/sym=SPX/"), krg)
brg = json.loads(s3rg.store[krg])
check("every regime_log column survives",
      brg["record"]["conviction"] == 0.75 and brg["record"]["engine"] == "L2")
check("regime_log re-push costs 0 (append-only, stable hash)",
      s3_push.push_table(s3rg, "B", dbp2, "regime_log", "logged_at",
                         "regime_log", ledrg, "SPX", cntrg)[0] == 0)

pb_, _ = s3_push.push_table(s3rg, "B", dbp2, "circuit_breaker_events",
                            "event_time", "circuit_breaker", ledrg, "SPX", cntrg)
check("circuit_breaker row pushed to its own prefix",
      pb_ == 1 and any("raw/circuit_breaker/" in k for k in s3rg.store), sorted(s3rg.store))

# an older box without the table must degrade, not raise
con = _s3q.connect(os.path.join(TMP, "bare.db")); con.execute("CREATE TABLE x (a)"); con.commit(); con.close()
check("a missing table -> 0/0, no raise",
      s3_push.push_table(ListStub(), "B", os.path.join(TMP, "bare.db"),
                         "regime_log", "logged_at", "regime_log", {}, "SPX", {}) == (0, 0))

# 32 — stage order with ELEVEN streams
_src3 = _insp.getsource(s3_push.main)
_n11 = ("trades", "regime_log", "circuit_breaker", "eod", "ohlc",
        "candles", "liquidity_ledger", "chain_snapshots", "shadow", "signal_journal")
_p11 = {n: _src3.index('("%s"' % n) for n in _n11 if '("%s"' % n in _src3}
check("all TEN stages are declared", len(_p11) == 10, sorted(_p11))
check("the two new tables run before the bulk streams",
      max(_p11["regime_log"], _p11["circuit_breaker"]) < _p11["chain_snapshots"], _p11)
check("signal_journal is STILL last", _p11["signal_journal"] == max(_p11.values()))

shutil.rmtree(TMP, ignore_errors=True)
print("\n" + ("ALL CHECKS PASSED" if not FAILS else "FAILURES: " + ", ".join(FAILS)))
sys.exit(1 if FAILS else 0)
