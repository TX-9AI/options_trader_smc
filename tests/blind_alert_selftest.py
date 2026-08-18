#!/usr/bin/env python3
"""
tests/blind_alert_selftest.py — v1.2 — 2026-08-01

BLIND-ALERT DRILL. Runs ON A BOT BOX and fires the real alert path end to end.

v1.1 — 2026-08-01 — THE DRILL REPORTED "sent" ON 29 BOXES WHILE NOTHING LEFT THE
       MACHINE, and every layer was complicit:
         1. setup_ec2.sh bakes TELEGRAM_TOKEN / TELEGRAM_CHAT_ID into the systemd
            unit as Environment= lines. There is no env file to source.
         2. A non-interactive SSH command inherits none of them, so
            config.telegram_configured() is False.
         3. TelegramSender.send() returns False and logs at DEBUG.
         4. AlertManager._send DISCARDED that bool (fixed in v1.9).
         5. This file then hardcoded `check("sent the DRILL blind alert", True)`.
       Five layers, five chances to notice, none taken. An alarm-tester that
       cannot observe its own failure is worse than no tester — and this is the
       tool built to catch exactly that class of silent failure.
       FIXED HERE: the send checks the REAL return value, and the drill sources
       credentials from the bot unit when the ambient environment lacks them —
       the same fallback day_trader_pro/verify_creds_remote.py::_env() already
       uses (which is why option 54 works and this did not). Reporting whether
       Telegram is even reachable now happens BEFORE anything is sent.

WHY THIS EXISTS
    The blind alert is the one that pages when the bot is still running but can
    no longer see. If it is broken, the failure mode is silence — the operator
    learns it never worked at the exact moment they needed it. An alarm that has
    never fired is an alarm nobody knows works, so it gets exercised on purpose.

    It walks the ACTUAL production path, not a mock:
        market_data.record_blindness()  ->  the same recorder every blind return
                                            in fetch_candles funnels through
        BlindnessLatch.update()         ->  the same latch main.py runs, held to
                                            the same tick and time thresholds
        AlertManager.send_blind_alert() ->  the same function, same formatting,
                                            same Telegram sender
        AlertManager.send_sight_restored_alert()  ->  the recovery notice

    Only two things differ from a real outage: the blindness record is synthetic,
    and drill=True prefixes an unmistakable marker.

THE DRILL MARKER IS NOT COSMETIC
    Telegram here is an EMERGENCY SERVICES channel — nothing routine goes to it.
    A test that looks like a real alert IS a false alarm, and a channel that has
    cried wolf once gets read more slowly forever. Every message this sends
    leads with a DRILL prefix.

WHAT IT VERIFIES, beyond "a message arrived"
    - the latch does NOT fire early (asserts silence below the threshold)
    - it fires exactly once, and holds the FIRST snapshot
    - open positions are read from the live trades.db and rendered — so the
      operator sees the real format, including whether the manage-manually line
      would appear on this box
    - the recovery notice still carries duration and cause after the reset

USAGE (on a bot box, repo root — single line)
    python3 tests/blind_alert_selftest.py
    python3 tests/blind_alert_selftest.py --no-send     # dry run, prints only

Places no orders. Writes nothing. Sends two Telegram messages unless --no-send.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DRILL_CAUSE = "DRILL_BARS_STALE"
BOT_UNIT = "/etc/systemd/system/optionsbot.service"
TELEGRAM_VARS = ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID")


def _hydrate_env_from_unit() -> list:
    """Populate Telegram credentials from the bot unit when the ambient
    environment lacks them.

    setup_ec2.sh writes them as `Environment=VAR=value` inside
    /etc/systemd/system/optionsbot.service, so systemd hands them to the SERVICE
    and a manual SSH run gets nothing. Mirrors the fallback in
    day_trader_pro/verify_creds_remote.py::_env() — that is why option 54 can
    verify Telegram from a fan-out and why this drill could not.

    Returns the names it had to recover, so the drill can SAY that it did rather
    than silently paper over a real environment difference.
    """
    recovered = []
    for var in TELEGRAM_VARS:
        if os.environ.get(var):
            continue
        try:
            out = subprocess.run(
                ["sudo", "grep", f"^Environment={var}=", BOT_UNIT],
                capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:                                         # noqa: BLE001
            continue
        if out:
            os.environ[var] = out.split("=", 2)[2]
            recovered.append(var)
    return recovered


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-send", action="store_true",
                    help="exercise the path and print, but send no Telegram")
    a = ap.parse_args(argv[1:])

    # BEFORE importing config — telegram_configured() reads the environment at
    # import time, so hydrating afterwards would be too late.
    recovered = _hydrate_env_from_unit()

    from config import INSTRUMENT, PAPER_TRADING, telegram_configured
    from data.market_data import clear_blindness, last_blindness, record_blindness
    from utils.blindness_latch import ALERT, RECOVERED, BlindnessLatch

    instrument = os.environ.get("OT_INSTRUMENT", INSTRUMENT)
    print(f"blind-alert drill | {instrument} | "
          f"{'PAPER' if PAPER_TRADING else 'LIVE CASH'}")
    if recovered:
        print(f"  note: recovered {', '.join(recovered)} from {BOT_UNIT} — the "
              f"ambient\n        environment did not have them (manual run, not "
              f"the service).")

    fails = []


    def check(label, cond):
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
        if not cond:
            fails.append(label)

    # ── 0. can we send at all? asked BEFORE anything claims it sent ─────────
    configured = telegram_configured()
    check("Telegram is configured (token + chat id present)", configured)
    if not configured and not a.no_send:
        print("     Nothing below can reach Telegram. This is the exact condition "
              "that made\n     the drill report success on 29 boxes while sending "
              "nothing.")

    # ── 1. the recorder ──────────────────────────────────────────────────────
    clear_blindness()
    check("clean start: last_blindness() is None", last_blindness() is None)
    record_blindness(DRILL_CAUSE, instrument, "5m",
                     newest_bar="DRILL-SYNTHETIC", age_s="930", limit_s="900", bars=100)
    snap = last_blindness()
    check("record_blindness stored a record", snap is not None)
    check("cause round-tripped", (snap or {}).get("cause") == DRILL_CAUSE)

    # ── 2. the latch, at production thresholds ───────────────────────────────
    latch = BlindnessLatch()
    t = 1_000.0
    early = latch.update(snap, t)
    check("does NOT page on the first blind tick", early is None)

    verdict = None
    for i in range(1, 40):
        verdict = latch.update(snap, t + i * 20)
        if verdict:
            break
    check("pages once the threshold is met", verdict == ALERT)
    check("held the FIRST snapshot", (latch.snapshot or {}).get("cause") == DRILL_CAUSE)

    # ── 3. open positions, read live so the real format is visible ───────────
    descs = []
    try:
        from database.trade_logger import get_trade_logger
        rows = get_trade_logger().get_open_trades_live()
        descs = [getattr(r, "position_desc", None) or str(r) for r in rows]
        check(f"read open positions from trades.db ({len(descs)} open)", True)
    except Exception as e:                                        # noqa: BLE001
        check(f"read open positions from trades.db — {e}", False)

    if descs and not PAPER_TRADING:
        print("     NOTE: this box is LIVE with open positions, so the real "
              "alert would\n           carry the GO TO TASTYTRADE instruction.")

    # ── 4. the send ──────────────────────────────────────────────────────────
    if a.no_send:
        print("  [SKIP] --no-send: not sending Telegram")
    else:
        from notifications.alert_manager import get_alert_manager
        am = get_alert_manager()
        sent = am.send_blind_alert(instrument, latch.snapshot,
                                   open_positions=descs, paper=PAPER_TRADING,
                                   blind_for_s=latch.blind_for_s(t + 200),
                                   drill=True)
        # v1.1 — the REAL return, not True. This assertion is the whole point of
        # the release: if the message did not reach Telegram, the drill FAILS.
        check("DRILL blind alert actually reached Telegram", bool(sent))

    # ── 5. recovery, including the fields the reset must not eat ─────────────
    rec = latch.update(None, t + 300)
    check("recovery fires once", rec == RECOVERED)
    check("recovery kept the duration", latch.last_outage_s > 0)
    check("recovery kept the cause", latch.last_outage_cause == DRILL_CAUSE)
    if not a.no_send:
        from notifications.alert_manager import get_alert_manager
        sent2 = get_alert_manager().send_sight_restored_alert(
            instrument, latch.last_outage_s, latch.last_outage_cause, drill=True)
        check("DRILL recovery notice actually reached Telegram", bool(sent2))

    clear_blindness()
    print(f"\n{'DRILL PASSED' if not fails else 'DRILL FAILED: ' + ', '.join(fails)}")
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
