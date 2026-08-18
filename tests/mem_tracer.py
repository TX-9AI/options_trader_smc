#!/usr/bin/env python3
"""
tests/mem_tracer.py — v1.1 — 2026-08-07

Names the ALLOCATION SITE behind the SPX leak, instead of guessing at it.

WHAT IS ALREADY MEASURED (2026-08-07, option 14, two samples 16.4 min apart):
  fourteen boxes FLAT — most moved by kilobytes, MU −1.9 MB and NVDA −4.5 MB
  (a healthy allocator returning memory). SPX +93.5 MB = **5.7 MB/min**. QQQ is
  the control that closes it: comparable chain, also ALWAYS_ON, **+8 KB in 16
  minutes**. Growth is not proportional to chain size, it is BINARY — SPX
  retains, QQQ does not. All 15 boxes run the same code, so this is not the
  emission-law deploy.

THE ARITHMETIC THIS PROBE EXISTS TO CONFIRM OR KILL: 5.7 MB/min over a 15s tick
is ~1.4 MB retained per tick, and a 724-option SPX chain at ~2 KB/object is
~1.4 MB — the size of exactly one full chain build. That is a CONSISTENCY, not
evidence. Source reading already came up empty (`_struct_cache` is keyed by
symbol and overwritten; `chain_snapshot` holds one string bucket), which is
precisely why this measures rather than reads.

HOW IT WORKS. Drives the real per-tick sequence from main.py's GEX block —
`fetch_chain()` → `compute_gex()` → optional `chain_snapshot()` — under
`tracemalloc`, and diffs a WARM snapshot against a later one. Warm-up matters:
the first ticks allocate caches, interned strings and the chain structure that
are SUPPOSED to persist, and counting those as a leak is how a probe invents a
finding. Only growth AFTER the warm snapshot is reported.

Alongside each tick it samples RSS from /proc/self/statm, so the tracemalloc
total can be reconciled against real process growth. **If RSS climbs while the
traced total does not, the retention is NOT in Python objects** — it is a C
extension, an arena-fragmentation effect, or a fd/buffer, and the answer is a
different tool. That divergence is a finding in itself and the probe says so.

⚠️ MEMORY HAZARD — READ BEFORE RUNNING. This is a SECOND python process
carrying the same imports (~200 MB) on a 951 MB box that already sits at
73-79% used with ~206 MB available and ZERO SWAP. Running it beside a live
optionsbot can itself trigger the OOM killer, and the kernel picks the largest
RSS — which may be the live bot. Either stop optionsbot on SPX for the run, or
resize the box first. The probe refuses to start if available memory is below
--min-avail-mb.

⚠️ It fetches real market data and needs RTH for a 0DTE chain to exist. It
places NO orders, writes NO trades, and touches no position state.

USAGE (on the SPX box, RTH, with optionsbot stopped or the box resized)
    python3 tests/mem_tracer.py --ticks 40 --warm 8 --interval 15
    python3 tests/mem_tracer.py --ticks 20 --interval 5 --no-snapshot

CHANGELOG
  v1.1 — 2026-08-07 — prints the SYMBOL on line one, and ABORTS after 3 empty
         fetches instead of producing a meaningless table. Both were flagged
         after the first failed run and not shipped; the same gap then cost two
         more runs. Superseded for live use by MEM.2 (utils/mem_trace.py),
         which runs INSIDE the bot and so cannot have the environment problem
         at all — this file remains useful only where the environment is
         already correct.
  v1.0 — 2026-08-07 — first issue, after the two-sample RSS trace confirmed the
         leak is real, SPX-only and ~5.7 MB/min. Built to name a line rather
         than re-litigate `_fetch_current_premium`, which prior work already
         failed to convict.
"""

import argparse
import gc
import os
import sys
import time
import tracemalloc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PAGE = os.sysconf("SC_PAGE_SIZE")


def rss_mb() -> float:
    try:
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * PAGE / (1024 * 1024)
    except Exception:                                            # noqa: BLE001
        return -1.0


def avail_mb() -> float:
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 1024.0
    except Exception:                                            # noqa: BLE001
        pass
    return -1.0


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=40)
    ap.add_argument("--warm", type=int, default=8,
                    help="ticks before the reference snapshot (caches settle)")
    ap.add_argument("--interval", type=float, default=15.0)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--frames", type=int, default=8)
    ap.add_argument("--no-snapshot", action="store_true",
                    help="skip chain_snapshot(); isolates the archival path")
    ap.add_argument("--no-gex", action="store_true")
    ap.add_argument("--min-avail-mb", type=float, default=320.0)
    a = ap.parse_args(argv[1:])

    av = avail_mb()
    print(f"MemAvailable: {av:.0f} MB   (threshold {a.min_avail_mb:.0f})")
    if 0 <= av < a.min_avail_mb:
        print("REFUSING TO START — too little headroom. This probe is a second")
        print("~200 MB process on a box with no swap; starting it here risks an")
        print("OOM kill of the LIVE bot, which the kernel would pick as the")
        print("largest RSS. Stop optionsbot on this box, or resize it, then")
        print("re-run. Override with --min-avail-mb 0 only if you mean it.")
        return 0

    # v1.1 — ANNOUNCE THE SYMBOL ON LINE ONE. v1.0 ran on the SPX box against
    # QQQ (OT_INSTRUMENT was unset under `tmux sh -c`) and the only clue was an
    # error three lines down. A wrong-instrument run must be obvious immediately.
    try:
        from config import INSTRUMENT
        print(f"TRACING SYMBOL: {INSTRUMENT}   (from OT_INSTRUMENT)")
    except Exception as e:                                       # noqa: BLE001
        print(f"could not resolve INSTRUMENT: {e}")

    from data.options_chain import get_chain_fetcher
    fetcher = get_chain_fetcher()
    _empty = 0
    compute_gex = None
    if not a.no_gex:
        from data.gex_data import compute_gex

    tracemalloc.start(a.frames)
    ref = None
    r0 = rss_mb()
    print(f"tick   RSS_MB   traced_MB   note")

    for i in range(a.ticks):
        try:
            chain = fetcher.fetch_chain()
            price = None
            if chain is not None:
                price = getattr(chain, "underlying_price", None) or \
                        getattr(chain, "spot", None)
                if compute_gex is not None and price:
                    compute_gex(chain, price)
                if not a.no_snapshot:
                    from analysis.chain_snapshot import snapshot as csnap
                    csnap(chain, underlying_price=price, regime=None)
            if chain is None:
                _empty += 1
        except Exception as e:                                   # noqa: BLE001
            print(f"  tick {i}: call failed: {e}")
            _empty += 1
        # v1.1 — ABORT ON REPEATED EMPTY FETCHES. v1.0 looped 40 times against a
        # dead fetcher and printed a plausible-looking table that meant nothing —
        # the same laundered-output failure this repo keeps catching elsewhere.
        if _empty >= 3:
            print(f"\nABORTING after {_empty} empty/failed fetches — no chain is "
                  "reaching this process, so nothing below would mean anything.")
            print("Check: right box? RTH? OT_INSTRUMENT and TT_* present in THIS "
                  "process (a tmux `sh -c` inherits neither .bashrc nor the "
                  "systemd unit environment)?")
            return 0

        cur, _peak = tracemalloc.get_traced_memory()
        note = ""
        if i == a.warm:
            gc.collect()
            ref = tracemalloc.take_snapshot()
            note = "<-- REFERENCE (warm)"
        print(f"{i:4d}  {rss_mb():7.1f}  {cur/1048576:9.1f}   {note}")
        if i < a.ticks - 1:
            time.sleep(a.interval)

    if ref is None:
        print("\nnever reached the warm tick — raise --ticks above --warm")
        return 0

    gc.collect()
    late = tracemalloc.take_snapshot()
    diff = late.compare_to(ref, "lineno")
    traced_growth = sum(s.size_diff for s in diff) / 1048576.0
    rss_growth = rss_mb() - r0
    span = (a.ticks - a.warm)

    print(f"\n=== GROWTH SINCE THE WARM SNAPSHOT ({span} ticks) ===")
    print(f"  traced (python objects): {traced_growth:+.1f} MB "
          f"= {traced_growth/max(1,span):+.2f} MB/tick")
    print(f"  RSS (whole process)    : {rss_growth:+.1f} MB over the full run")
    if traced_growth < 1.0 and rss_growth > 10.0:
        print("  ** RSS GREW WHILE TRACED MEMORY DID NOT. The retention is NOT")
        print("  ** in Python objects — suspect a C extension, allocator arena")
        print("  ** fragmentation, or unclosed handles. This probe cannot see")
        print("  ** it; that is the finding. Next tool, not next guess.")

    print(f"\n=== TOP {a.top} ALLOCATION SITES BY GROWTH ===")
    for s in diff[:a.top]:
        f = s.traceback[0]
        print(f"  {s.size_diff/1024:+9.0f} KB  {s.count_diff:+7d} objs  "
              f"{f.filename}:{f.lineno}")
    print(f"\n=== FULL TRACEBACK FOR THE TOP SITE ===")
    if diff:
        for line in diff[0].traceback.format():
            print("  " + line)

    print("\n  A site growing here is where memory is RETAINED, not necessarily")
    print("  where the bug is — the bug is whatever still holds the reference.")
    print("  Compare against a QQQ run before concluding it is SPX-specific:")
    print("  QQQ was FLAT on the fleet trace, so the same site growing there")
    print("  too would mean the probe, not the box, is the odd one out.")
    return 0


if __name__ == "__main__":
    try:
        rc = main(sys.argv)
    except KeyboardInterrupt:
        rc = 0
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        rc = 0
    sys.exit(rc)
