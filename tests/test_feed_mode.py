#!/usr/bin/env python3
"""
tests/test_feed_mode.py — v1.0 — 2026-08-15   (FEED.1)

A MAINTENANCE WINDOW THE FLEET CAN COME UP INSIDE WITHOUT TOUCHING THE WIRE.

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python -m pytest tests/test_feed_mode.py -q

`_idle_outside_session` already said the right thing — **"THE DISTINCTION IS
PURPOSE, NOT TIME"** — but it only had TWO purposes: service (hold a socket for
a live session) and one-shot (`--once`, pull history and exit). A `--once` run
was therefore allowed at ANY hour, which is correct for the EOD pull and wrong
for the case v3.9 was actually protecting against: **a maintenance wake putting
all 29 boxes on the wire for work that needs no market data.**

⚠️ AND IT CANNOT BE A CLOCK RULE. The overnight capture pass (08:15 ET) and a
maintenance window happen at the SAME HOURS and want OPPOSITE behaviour. Only
purpose separates them.

⚠️ THE SILENCE IS THE DANGER, NOT THE GATE. On 2026-08-03/04 this gate blocked
the EOD pull and said so at INFO: `Feed idle — outside RTH`, four times, then
`0 bars`, then fourteen 38-byte header-only CSVs. Nothing raised. **DXFeed
history is same-evening only, so both sessions are permanently lost.** A
maintenance-suppressed run must therefore be IMPOSSIBLE to mistake for a failed
fetch — it warns, names the mode, and says the data is not being collected.
"""

import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _mode(value):
    if value is None:
        os.environ.pop("OT_FEED_MODE", None)
    else:
        os.environ["OT_FEED_MODE"] = value
    import data.candle_feed as cf
    importlib.reload(cf)
    return cf


def _idle(cf, once, rth=False):
    """Mirror of the predicate. Kept honest by `test_mirror_matches_source`."""
    if cf.FEED_MODE == "maintenance":
        return True
    return not rth and not once


def test_the_default_is_service_so_nothing_moves():
    cf = _mode(None)
    assert cf.FEED_MODE == "service"


def test_maintenance_suppresses_even_a_once_run():
    """THE WHOLE POINT. `--once` was unconditionally allowed; that is exactly
    what a maintenance wake must not do."""
    cf = _mode("maintenance")
    assert _idle(cf, once=True) is True
    assert _idle(cf, once=False) is True
    assert _idle(cf, once=True, rth=True) is True   # even during RTH


def test_service_mode_is_byte_for_byte_the_old_behaviour():
    cf = _mode("service")
    assert _idle(cf, once=False, rth=False) is True    # idle outside RTH
    assert _idle(cf, once=False, rth=True) is False    # serve the session
    assert _idle(cf, once=True, rth=False) is False    # --once always allowed


def test_capture_gates_like_service():
    """`capture` exists to make an overnight-pull wake DISTINGUISHABLE in the
    logs from a trader wake, and to give a future window argument somewhere to
    live. It must not change gating today."""
    svc, cap = _mode("service"), _mode("capture")
    for once in (True, False):
        for rth in (True, False):
            assert _idle(svc, once, rth) == _idle(cap, once, rth)


def test_an_unknown_mode_falls_back_LOUDLY_to_service():
    """It must not silently become maintenance (a box that never feeds) NOR be
    accepted as-is. A typo in a unit file cannot be allowed to cost a session
    of tape that can never be recovered."""
    cf = _mode("mainenance")            # deliberate typo
    assert cf.FEED_MODE == "service"


def test_mirror_matches_source():
    src = open(os.path.join(os.path.dirname(__file__), "..", "data",
                            "candle_feed.py"), encoding="utf-8").read()
    # ⚠️ the gate calls `_maintenance_now()`, NOT the constant directly — the
    # sentinel file has to be consulted on every evaluation or a live flip
    # would need a restart.
    assert "if _maintenance_now():" in src
    assert "def _maintenance_now(" in src
    assert "return not is_rth() and not once" in src
    i = src.index("def _idle_outside_session(")
    seg = src[i:i + 2600]
    assert "logger.warning(" in seg, \
        "a suppressed run must not be silent - that is the 08-03 failure"


def test_the_warning_says_the_data_is_not_being_collected():
    """Naming the mode is not enough. The 08-03 log said `Feed idle — outside
    RTH` — accurate, and nobody read it as 'the tape is being lost'."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "data",
                            "candle_feed.py"), encoding="utf-8").read()
    i = src.index("def _idle_outside_session(")
    # ⚠️ NORMALISE THE SOURCE FIRST. The message is a multi-line implicit
    # concatenation, so a naive substring spans a line break and a quote pair
    # and fails on text that is actually present. Strip the seams, then assert.
    seg = src[i:i + 2600]
    flat = seg.replace('"\n', "").replace('"', "").replace("\n", " ")
    flat = " ".join(flat.split())
    assert "NO candles will be collected" in flat
    assert "DELIBERATE, not a fetch failure" in flat


# ── the sentinel: flipping the window without restarting anything ──────────

def test_the_sentinel_flips_live_with_no_restart():
    """⚠️ `Environment=` IN THE UNIT IS READ ONCE AT IMPORT. Flipping the mode
    on a RUNNING feed via env would need a restart — and the restart window is
    exactly when the box is on the wire during the maintenance it is supposed
    to be excused from. The file is checked on EVERY gate evaluation."""
    import tempfile
    d = tempfile.mkdtemp()
    flag = os.path.join(d, "FEED_MAINTENANCE")
    os.environ["OT_FEED_MAINT_FLAG"] = flag
    os.environ.pop("OT_FEED_MODE", None)
    cf = _mode(None)

    assert cf._maintenance_now() is False
    open(flag, "w").close()
    assert cf._maintenance_now() is True      # no reload, no restart
    os.remove(flag)
    assert cf._maintenance_now() is False


def test_it_fails_OPEN_to_service_on_an_unreadable_flag_path():
    """⚠️ THE ASYMMETRY IS DELIBERATE AND IT POINTS THE OTHER WAY FROM USUAL.
    Everywhere else in this repo a missing input fails CLOSED. Here it must
    fail OPEN — a box that cannot stat the flag keeps FEEDING.

    Because the costs are not symmetric: a stray socket during maintenance is
    recoverable in seconds, while a missed session is PERMANENT — DXFeed
    history is same-evening only, which is how 2026-08-03 and 08-04 were lost
    for good."""
    os.environ["OT_FEED_MAINT_FLAG"] = "/proc/self/mem/nope/cannot-stat"
    os.environ.pop("OT_FEED_MODE", None)
    cf = _mode(None)
    assert cf._maintenance_now() is False


def test_env_still_works_for_a_box_woken_INTO_maintenance():
    """The sentinel handles a live flip; env handles a box that should come up
    already excused, before anything could write a file to it."""
    os.environ["OT_FEED_MAINT_FLAG"] = "/nonexistent/flag"
    cf = _mode("maintenance")
    assert cf._maintenance_now() is True
