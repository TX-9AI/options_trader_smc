"""
utils/mem_trace.py — v1.0 — 2026-08-07

IN-PROCESS tracemalloc for the live bot, gated by `OT_MEM_TRACE`.

WHY THIS EXISTS RATHER THAN THE STANDALONE PROBE. `tests/mem_tracer.py` drives
the real chain path in a SEPARATE process, and that shape failed four times in
one afternoon for reasons that were never about memory:
  1. run on the CONTROL box, which is not a trading box
  2. run before the box had pulled the file
  3. run through `tmux ... sh -c`, which reads neither .bashrc nor the systemd
     unit environment, so it started with no credentials and the wrong symbol
     (`OT_INSTRUMENT` defaulted to QQQ on the SPX box)
  4. the `xargs -0 ... env` workaround appended the environment AFTER the
     script's own arguments, so argparse rejected them and ECHOED EVERY SECRET
     to the terminal
Every one of those is the same root cause: a second process cannot easily
inherit the trading environment. **The bot already HAS it.** Running the trace
inside the bot removes the entire class.

WHAT IT MEASURES. The SPX leak: ~5.7 MB/min, SPX-only, 91% of RSS anonymous
private-dirty (so it IS the Python heap, which is what makes tracemalloc the
right tool). QQQ carries a comparable chain and was FLAT over a 16-minute
sample, so this is not chain size alone.

COST WHEN DISABLED: one module-level bool test per tick. `tracemalloc` is never
imported unless the flag is on, so the default path pays nothing.

COST WHEN ENABLED: tracemalloc itself adds roughly 10-30% memory overhead and
some per-allocation time. **On a 951 MB box that overhead is itself a risk** —
which is exactly why SPX was resized to 2 GiB first. Do NOT enable this
fleet-wide on the 1 GiB boxes.

USAGE (SPX box, in the systemd unit or an ExecStart env):
    OT_MEM_TRACE=1            enable, defaults below
    OT_MEM_TRACE_EVERY=40     snapshot cadence in ticks (~10 min at 15s)
    OT_MEM_TRACE_WARM=20      ticks before the reference snapshot is taken
    OT_MEM_TRACE_TOP=12       sites reported per dump
"""

import os

_ON = os.environ.get("OT_MEM_TRACE", "0").strip().lower() not in (
    "0", "false", "no", "off", "")
_EVERY = int(os.environ.get("OT_MEM_TRACE_EVERY", "40") or 40)
_WARM = int(os.environ.get("OT_MEM_TRACE_WARM", "20") or 20)
_TOP = int(os.environ.get("OT_MEM_TRACE_TOP", "12") or 12)

_n = 0
_ref = None
_tm = None
_PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096


def enabled() -> bool:
    return _ON


def _rss_mb() -> float:
    try:
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * _PAGE / (1024 * 1024)
    except Exception:                                            # noqa: BLE001
        return -1.0


def start(logger=None) -> None:
    """Call once at boot. No-op unless OT_MEM_TRACE is set."""
    global _tm
    if not _ON:
        return
    import tracemalloc                                            # noqa: PLC0415
    _tm = tracemalloc
    _tm.start(8)
    if logger:
        logger.info("MEM_TRACE ON — warm=%d ticks, dump every=%d, top=%d, "
                    "rss=%.0fMB", _WARM, _EVERY, _TOP, _rss_mb())


def tick(logger=None) -> None:
    """Call once per bot tick. Cheap bool test when disabled.

    The WARM reference matters: the first ticks allocate caches, interned
    strings and the chain structure that are SUPPOSED to persist. Diffing from
    tick 0 would report those as growth and name the wrong lines — the same
    warm-up discipline the offline probe uses.
    """
    global _n, _ref
    if not _ON or _tm is None:
        return
    _n += 1
    if _n == _WARM:
        import gc                                                 # noqa: PLC0415
        gc.collect()
        _ref = _tm.take_snapshot()
        if logger:
            logger.info("MEM_TRACE reference taken at tick %d (rss=%.0fMB)",
                        _n, _rss_mb())
        return
    if _ref is None or _n % _EVERY != 0:
        return
    import gc                                                     # noqa: PLC0415
    gc.collect()
    diff = _tm.take_snapshot().compare_to(_ref, "lineno")
    traced = sum(s.size_diff for s in diff) / 1048576.0
    rss = _rss_mb()
    if logger:
        logger.warning("MEM_TRACE tick=%d rss=%.0fMB traced_growth=%+.1fMB "
                       "since warm", _n, rss, traced)
        # If RSS climbs while TRACED does not, the retention is NOT in Python
        # objects — a C extension, allocator arena fragmentation, or unclosed
        # handles — and tracemalloc cannot see it. That divergence is a finding,
        # not a failure, and it must be said rather than left to inference.
        if traced < 1.0 and rss > 0:
            logger.warning("MEM_TRACE ** traced growth is flat while RSS is "
                           "%.0fMB — if RSS is climbing, the leak is NOT in "
                           "Python objects and needs a different tool", rss)
        for s in diff[:_TOP]:
            f = s.traceback[0]
            logger.warning("MEM_TRACE   %+9.0fKB %+7d objs  %s:%d",
                           s.size_diff / 1024, s.count_diff, f.filename,
                           f.lineno)
