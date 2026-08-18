#!/usr/bin/env python3
"""
tests/test_tenor_capture.py — v1.0 — 2026-08-18   (TERM.1)

THREE TENORS THAT ACTUALLY SPAN TIME, WITHOUT RISKING THE TRADING PATH.

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python -m pytest tests/test_tenor_capture.py -q

Every chain snapshot to 2026-08-18 carries a SINGLE expiry equal to the session
date, so **term structure is not computable** — and term structure is the one
thing options data says about *when* the market expects movement rather than
how much. It also **cannot be backfilled**: chain history is unavailable after
the session.

⚠️ THE COLLISION RULE IS THE POINT. On a monthly opex Friday 0DTE *is* the
weekly *is* the monthly; all three collapse to one date, the term slope is
undefined, and a naive `sorted(dates)[:3]` reports a successful three-expiry
capture while carrying one. **The day that yields the least information looks
the most normal.**

⚠️ AND THE SUBSCRIPTION PATH FAILS OPEN. `chain_subs` is `CHECK (id = 1)` — a
single row by design — and `read_chain_subs` decides what a LIVE TRADING BOX
subscribes to. Extra tenors ride in a separate table that is unioned in;
missing, stale or malformed, the front expiry behaves exactly as before.
**Archival enrichment must never cost the bot its own chain.**
"""

import json
import os
import sqlite3
import sys
import threading
import time
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.tenor_select import pick_tenors, describe          # noqa: E402


def _store(tmp):
    import data.candle_feed as cf
    c = sqlite3.connect(os.path.join(tmp, "s.db"))
    c.execute("CREATE TABLE chain_subs (id INTEGER PRIMARY KEY CHECK (id=1), "
              "expiry TEXT NOT NULL, symbols TEXT NOT NULL, "
              "updated_epoch REAL NOT NULL)")
    c.execute("INSERT INTO chain_subs VALUES (1,?,?,?)",
              ("2026-08-18", json.dumps([".F1", ".F2"]), time.time()))
    c.commit()

    class S:
        pass
    S.read_chain_subs = cf.FeedStore.read_chain_subs
    S._read_chain_subs_aux = cf.FeedStore._read_chain_subs_aux
    s = S()
    s.conn, s._lock = c, threading.Lock()
    return s, c


def test_monthly_opex_friday_does_not_collapse_to_one_date():
    """⚠️ THE CASE THAT BREAKS A NAIVE IMPLEMENTATION. 2026-08-21 is a third
    Friday: 0DTE, the weekly and the monthly are all that date."""
    picked = pick_tenors([date(2026, 8, 21), date(2026, 8, 24),
                          date(2026, 9, 18)], date(2026, 8, 21))
    assert len(picked) == len(set(picked)), "duplicate expiry"
    assert len(picked) == 3
    assert (picked[-1] - picked[0]).days >= 7, "the three must span real time"


def test_never_returns_duplicates_on_any_shape():
    for today, avail in (
            (date(2026, 8, 18), [date(2026, 8, 18), date(2026, 8, 19),
                                 date(2026, 8, 21), date(2026, 9, 18)]),
            (date(2026, 8, 18), [date(2026, 8, 21)]),
            (date(2026, 8, 18), [date(2026, 8, 21), date(2026, 8, 28)]),
            (date(2026, 8, 18), []),
    ):
        p = pick_tenors(avail, today)
        assert len(p) == len(set(p))


def test_past_expiries_are_never_selected():
    p = pick_tenors([date(2026, 8, 10), date(2026, 8, 21)], date(2026, 8, 18))
    assert all(d >= date(2026, 8, 18) for d in p)


def test_a_degenerate_pick_announces_itself():
    """A single-expiry chain is an honest statement about the symbol — but it
    must SAY so, or 'we captured tenors' hides 'we captured one'."""
    txt = describe(pick_tenors([date(2026, 8, 18)], date(2026, 8, 18)),
                   date(2026, 8, 18))
    assert "FEWER THAN 3" in txt


def test_aux_tenors_are_unioned_into_the_subscription(tmp_path):
    s, c = _store(str(tmp_path))
    assert len(s.read_chain_subs()[1]) == 2          # front only
    c.execute("CREATE TABLE chain_subs_aux (expiry TEXT PRIMARY KEY, "
              "symbols TEXT NOT NULL, updated_epoch REAL NOT NULL)")
    c.execute("INSERT INTO chain_subs_aux VALUES (?,?,?)",
              ("2026-08-21", json.dumps([".A1", ".A2"]), time.time()))
    c.commit()
    expiry, syms = s.read_chain_subs()
    assert len(syms) == 4
    assert expiry == "2026-08-18", \
        "the returned expiry must still name the FRONT — every caller reads it so"


def test_the_trading_path_survives_every_aux_failure(tmp_path):
    """⚠️ THIS IS THE ONE THAT MATTERS. `read_chain_subs` decides what a LIVE
    box subscribes to. Missing, stale, malformed or dropped mid-run, the front
    expiry must come back untouched."""
    s, c = _store(str(tmp_path))
    c.execute("CREATE TABLE chain_subs_aux (expiry TEXT PRIMARY KEY, "
              "symbols TEXT NOT NULL, updated_epoch REAL NOT NULL)")

    c.execute("INSERT INTO chain_subs_aux VALUES (?,?,?)",
              ("2026-08-21", json.dumps([".A1"]), time.time() - 99999))
    c.commit()
    assert len(s.read_chain_subs()[1]) == 2, "stale aux must be ignored"

    c.execute("UPDATE chain_subs_aux SET symbols=?, updated_epoch=?",
              ("not-json", time.time()))
    c.commit()
    assert len(s.read_chain_subs()[1]) == 2, "malformed aux must be ignored"

    c.execute("DROP TABLE chain_subs_aux")
    c.commit()
    assert len(s.read_chain_subs()[1]) == 2, "a dropped table must not raise"


# ── TERM.1 part 2 — the publisher ──────────────────────────────────────────

class _Opt:
    def __init__(self, k, tag="X"):
        self.strike_price = k
        self.streamer_symbol = f".{tag}{k}"


def test_the_atm_band_self_scales_across_underlyings():
    """⚠️ NEAREST-BY-DISTANCE, NOT A FIXED DOLLAR WIDTH. A $5 band is most of
    the tradeable range on a $76 symbol and a rounding error on a $7,700 one —
    the same scaling error the pitchfork and butterfly work both hit."""
    from analysis.tenor_publish import _band_symbols
    for spot, step in ((600.0, 1.0), (6000.0, 25.0), (76.0, 0.5)):
        opts = [_Opt(spot + i * step) for i in range(-15, 16)]
        assert len(_band_symbols(opts, spot, band=4)) == 9


def test_the_front_expiry_is_never_republished(tmp_path):
    """The bot owns the front expiry via `chain_subs`. Publishing it again as an
    aux row would double-subscribe it against a hard session cap."""
    from analysis.tenor_publish import publish_aux_tenors
    db = str(tmp_path / "s.db")
    cm = {date(2026, 8, 18): [_Opt(600)], date(2026, 8, 19): [_Opt(600)],
          date(2026, 9, 18): [_Opt(600)]}
    out = publish_aux_tenors(db, cm, 600.0, date(2026, 8, 18))
    assert "2026-08-18" not in out
    assert set(out) == {"2026-08-19", "2026-09-18"}


def test_rolled_off_tenors_are_pruned(tmp_path):
    """⚠️ A tenor that rolls off leaves a row naming strikes that no longer
    exist, and the feed would keep subscribing to them until the 6h staleness
    bound expired — burning socket budget for contracts nothing reads."""
    from analysis.tenor_publish import publish_aux_tenors
    db = str(tmp_path / "s.db")
    publish_aux_tenors(db, {date(2026, 8, 19): [_Opt(600)],
                            date(2026, 9, 18): [_Opt(600)]},
                       600.0, date(2026, 8, 18))
    publish_aux_tenors(db, {date(2026, 8, 26): [_Opt(600)],
                            date(2026, 9, 18): [_Opt(600)]},
                       600.0, date(2026, 8, 25))
    c = sqlite3.connect(db)
    rows = {r[0] for r in c.execute("SELECT expiry FROM chain_subs_aux")}
    assert "2026-08-19" not in rows


def test_the_publisher_never_raises_into_the_trading_loop(tmp_path):
    """⚠️ THIS RUNS ON A LIVE BOX. A failure must cost archival data and
    nothing else."""
    from analysis.tenor_publish import publish_aux_tenors
    db = str(tmp_path / "s.db")
    for path, cm, spot in (("/proc/nope/s.db", {date(2026, 8, 19): [_Opt(600)]}, 600.0),
                           (db, {}, 600.0),
                           (db, {date(2026, 8, 19): [_Opt(600)]}, 0.0),
                           (db, {date(2026, 8, 18): [_Opt(600)]}, 600.0),
                           (db, {date(2026, 8, 19): [object()]}, 600.0)):
        assert publish_aux_tenors(path, cm, spot, date(2026, 8, 18)) == {}


def test_chain_subs_is_never_written_by_the_publisher(tmp_path):
    """`chain_subs` is CHECK (id = 1) and belongs to the bot's own expiry."""
    from analysis.tenor_publish import publish_aux_tenors
    db = str(tmp_path / "s.db")
    publish_aux_tenors(db, {date(2026, 8, 19): [_Opt(600)],
                            date(2026, 9, 18): [_Opt(600)]},
                       600.0, date(2026, 8, 18))
    c = sqlite3.connect(db)
    names = {r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "chain_subs_aux" in names
    assert "chain_subs" not in names
