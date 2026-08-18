#!/usr/bin/env python3
"""
analysis/tenor_publish.py — v1.0 — 2026-08-18   (TERM.1 part 2)

PUBLISH A NARROW ATM BAND FOR THE AUXILIARY TENORS.

    from analysis.tenor_publish import publish_aux_tenors
    publish_aux_tenors(store_path, chain_map, spot, today)

────────────────────────────────────────────────────────────────────────────
WHY NARROW, AND WHY THAT IS THE WHOLE DESIGN
────────────────────────────────────────────────────────────────────────────
**Term structure needs ATM IV per tenor. It does not need the chain.**

The front expiry subscribes ~250 contracts because the bot TRADES it — it needs
strikes, walls, GEX, a delta ladder. The auxiliary tenors are archival: the only
question asked of them is *"what is implied vol at the money, out at this
date."* That is answerable from a handful of strikes around spot.

⚠️ THE COST DIFFERENCE IS THE REASON THIS IS AFFORDABLE AT ALL:
    full chains x3   ~750 subscriptions/box
    ATM bands  x2    ~270 subscriptions/box   ← this
`options_chain` v3.1 measured TastyTrade's unpublished concurrent-session cap
near **~40**, which is why the per-box streamer was removed entirely and the
store-reader architecture exists. And SPX has already been **OOM-killed at 419
MB** once on chain volume. Tripling subscriptions would walk straight back into
both. A narrow band does not.

⚠️ AND IT WRITES ONLY TO `chain_subs_aux`. `chain_subs` is `CHECK (id = 1)` and
belongs to the bot's own expiry. Nothing here can alter what the trading path
subscribes to; `candle_feed` v3.15 unions the aux rows and **fails open** if
this module never runs, writes garbage, or goes stale.
"""

import json
import sqlite3
import time
from datetime import date
from typing import Dict, List, Optional, Sequence

# strikes each side of spot, per auxiliary tenor. 4 -> ~9 strikes -> ~18
# contracts (calls+puts). Enough to interpolate ATM IV and see the near-money
# skew; far short of a chain.
ATM_BAND = 4


def _band_symbols(options, spot: float, band: int = ATM_BAND) -> List[str]:
    """Streamer symbols for the `band` strikes either side of spot.

    ⚠️ NEAREST-BY-DISTANCE, not a fixed dollar width. A $5 band is most of the
    tradeable range on a $76 symbol and a rounding error on a $7,700 one — the
    same error the pitchfork and butterfly work both hit. Rank by |strike-spot|
    and take the closest N, and the band self-scales.
    """
    if not options or spot <= 0:
        return []
    strikes = sorted({float(getattr(o, "strike_price", 0) or 0)
                      for o in options} - {0.0})
    if not strikes:
        return []
    nearest = sorted(strikes, key=lambda k: abs(k - spot))[:max(1, band * 2 + 1)]
    keep = set(nearest)
    out = []
    for o in options:
        try:
            if float(getattr(o, "strike_price", 0) or 0) in keep:
                sym = getattr(o, "streamer_symbol", "") or ""
                if sym:
                    out.append(sym)
        except Exception:                                      # noqa: BLE001
            continue
    return out


def publish_aux_tenors(store_path: str,
                       chain_map: Dict[date, Sequence],
                       spot: float,
                       today: Optional[date] = None,
                       band: int = ATM_BAND) -> Dict[str, int]:
    """Write an ATM band per auxiliary tenor. Returns {expiry: n_symbols}.

    ⚠️ NEVER RAISES INTO THE CALLER. This runs on the trading box; a failure
    here must cost archival data and nothing else.
    ⚠️ AND IT PRUNES ITS OWN STALE ROWS. A tenor that rolls off leaves a row
    naming strikes that no longer exist, and `candle_feed` would keep
    subscribing to them until the 6h staleness bound expired — burning socket
    budget against a hard cap for contracts nothing reads.
    """
    from analysis.tenor_select import pick_tenors

    out: Dict[str, int] = {}
    try:
        today = today or date.today()
        picked = pick_tenors(list(chain_map.keys()), today)
        if len(picked) < 2:
            return out                      # nothing auxiliary to publish
        aux = picked[1:]                    # [0] is the front — the bot's own

        rows = []
        for d in aux:
            syms = _band_symbols(chain_map.get(d) or [], spot, band)
            if syms:
                rows.append((d.isoformat(), json.dumps(sorted(set(syms))),
                             time.time()))
                out[d.isoformat()] = len(set(syms))
        if not rows:
            return out

        conn = sqlite3.connect(store_path, timeout=5.0)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chain_subs_aux (
                    expiry        TEXT PRIMARY KEY,
                    symbols       TEXT NOT NULL,
                    updated_epoch REAL NOT NULL
                );""")
            keep = tuple(r[0] for r in rows)
            conn.execute(
                "DELETE FROM chain_subs_aux WHERE expiry NOT IN "
                f"({','.join('?' * len(keep))})", keep)
            conn.executemany(
                "INSERT OR REPLACE INTO chain_subs_aux "
                "(expiry, symbols, updated_epoch) VALUES (?,?,?)", rows)
            conn.commit()
        finally:
            conn.close()
    except Exception:                                          # noqa: BLE001
        return out
    return out
