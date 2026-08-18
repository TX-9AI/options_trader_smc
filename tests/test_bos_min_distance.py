"""
tests/test_bos_min_distance.py — v1.0 — 2026-08-10

Pins the BOS protected-level minimum distance (exit_engine v4.15).

WHAT WENT WRONG, observed LIVE on 2026-08-10 rather than inferred:
  JPM  in $1.26 12:49 -> out **$0.00** 12:50 -> back in $1.26 the same minute.
       A null round trip: the exit condition was already true at entry.
  QQQ  one move fragmented into four scratches (+$30 / +$45.50 / +$35 / +$7),
       same strike, three minutes, each exit immediately followed by re-entry
       because the setup was still valid.
CAUSE: the protected level is seeded from the LOW of the first bar that closes
above entry. On a pullback entry that bar is the smallest, earliest part of the
resumption, so its low sits a hair under entry — the level lands INSIDE the
symbol's own noise band and the next ordinary wiggle fires it.

THE THREE FAILURES GUARDED HERE, and all three render perfectly if they break:

1. **RATCHET DIRECTION.** `low - min_dist` is NOT monotone. If ATR widens
   between bars, a new candidate can come out BELOW the previous level, which
   silently LOOSENS the stop exactly when volatility is rising. Longs must
   `max()`, shorts must `min()`.
2. **min_dist=0 MUST BE BYTE-IDENTICAL to the old behaviour**, or the kill
   switch is not a kill switch and there is no A/B control.
3. **DIRECTION MIRROR.** A short flooring on the wrong side puts the level
   nearer price rather than further, making the very problem worse while
   looking like the fix.

Deliberate-failure check performed when written: replacing max() with a bare
assignment turns test_level_ratchets_and_never_loosens red; dropping the
min(low, entry - min_dist) floor turns test_level_is_never_seeded_inside_the_noise
_band red.
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution.exit_engine import BOSTracker                     # noqa: E402


def _bars(rows):
    idx = pd.date_range("2026-08-10 12:45", periods=len(rows), freq="1min")
    return pd.DataFrame(
        [{"open": o, "high": h, "low": l, "close": c} for o, h, l, c in rows],
        index=idx)


def test_level_is_never_seeded_inside_the_noise_band():
    """The JPM $0.00 case: first up-bar's low sits a hair under entry."""
    entry = 352.50
    t_raw = BOSTracker("long", entry, min_dist=0.0)
    t_buf = BOSTracker("long", entry, min_dist=0.35)
    # bar closes above entry; its low is 4 cents under entry
    df = _bars([(352.4, 352.7, 352.46, 352.60),
                (352.6, 352.8, 352.5, 352.70),
                (352.7, 352.8, 352.6, 352.70)])
    t_raw.update(df)
    t_buf.update(df)
    assert t_raw.protected_level is not None
    assert t_buf.protected_level <= entry - 0.35 + 1e-9, \
        "the floored level must sit at least min_dist BELOW entry — a level " \
        "4 cents under entry is inside the noise and fires on any wiggle"
    assert t_buf.protected_level < t_raw.protected_level


def test_min_dist_zero_is_byte_identical_to_the_old_behaviour():
    """If this fails, the kill switch is not a kill switch."""
    df = _bars([(100.0, 100.4, 99.90, 100.30),
                (100.3, 100.6, 100.2, 100.50),
                (100.5, 100.6, 100.4, 100.45)])
    t = BOSTracker("long", 100.0, min_dist=0.0)
    t.update(df)
    # update() reads iloc[-2] — the last CLOSED bar — so the level is the
    # MIDDLE bar's low here, not the first bar's. My first draft asserted the
    # wrong bar and the failure was mine, not the code's.
    assert t.protected_level == 100.2, \
        "with min_dist=0 the level must be exactly the closed bar's low, as before"
    # and the RATCHET must not apply either: a later new-closing-high bar with a
    # LOWER low used to drag the level down, and min_dist=0 must keep doing that
    t.update(_bars([(100.5, 101.0, 99.00, 100.90),
                    (100.9, 101.1, 99.20, 101.00),
                    (101.0, 101.1, 101.0, 101.05)]))
    assert t.protected_level == 99.20, \
        "at min_dist=0 the level must still be assigned unconditionally — " \
        "adding a ratchet here would make the kill switch not a kill switch"


def test_level_ratchets_and_never_loosens():
    """low - min_dist is not monotone; a widening ATR must not slacken the stop."""
    t = BOSTracker("long", 100.0, min_dist=0.20)
    t.update(_bars([(100.0, 100.4, 99.95, 100.30),
                    (100.3, 100.5, 100.2, 100.40),
                    (100.4, 100.5, 100.3, 100.45)]))
    first = t.protected_level
    assert first == 99.80, "entry floor governs while the bar low sits above it"
    # THE CASE THAT ACTUALLY EXERCISES THE RATCHET: the new closing high must
    # be on a bar whose LOW is BELOW the existing level (99.80). While the low
    # stays above the entry floor, min(low, entry-min_dist) returns the floor
    # either way and ratchet vs no-ratchet are indistinguishable — my first
    # draft of this test had exactly that hole and the deliberate-failure check
    # caught it by PASSING when it should have gone red.
    t.update(_bars([(100.4, 100.5, 100.3, 100.45),
                    (100.4, 101.0, 99.10, 100.80),   # new high, low 99.10
                    (100.8, 101.0, 100.7, 100.90)]))
    assert t.protected_level == 99.80, \
        "the level must RATCHET: a new closing high on a bar with a lower low " \
        "would otherwise drag the stop DOWN, slackening it exactly when " \
        "volatility widens"


def test_short_mirrors_on_the_correct_side():
    entry = 352.50
    t = BOSTracker("short", entry, min_dist=0.35)
    df = _bars([(352.6, 352.54, 352.2, 352.40),
                (352.4, 352.5, 352.2, 352.30),
                (352.3, 352.4, 352.2, 352.25)])
    t.update(df)
    assert t.protected_level >= entry + 0.35 - 1e-9, \
        "a short's level must sit ABOVE entry by min_dist — flooring on the " \
        "wrong side moves it NEARER price and makes the problem worse"


def test_a_genuine_break_still_fires():
    """The floor must not become a licence to hold through real failure."""
    t = BOSTracker("long", 100.0, min_dist=0.20)
    t.update(_bars([(100.0, 100.4, 99.95, 100.30),
                    (100.3, 100.5, 100.2, 100.40),
                    (100.4, 100.5, 100.3, 100.45)]))
    fired = t.update(_bars([(100.4, 100.5, 100.3, 100.40),
                            (100.4, 100.45, 98.0, 98.50),
                            (98.5, 98.6, 98.4, 98.45)]))
    assert fired is True, "a close far below the floored level must still exit"
