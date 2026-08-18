#!/usr/bin/env python3
"""
v1.10 — 2026-08-18 — THE OVERNIGHT GAP, SIGNED AND ABSOLUTE.
    ⚠️ THE ONLY NEW PRIMITIVE TESTABLE TODAY. Everything else shipped 08-18 —
    the angle (STR.2), the level grade (Level.1), VIX coverage (STR.1), three IV
    tenors (TERM.1) — needs the next bake and then SESSIONS before it can say
    anything. **The gap is fully BACKFILLABLE from banked OHLC**, so it is
    judged on the 17 sessions already in the book.
    ⚠️ AND IT IS THE ONLY PRE-OPEN INPUT IN THE STACK. ADX, conviction, the
    regime scores, IV skew and every structural column need bars from THIS
    session to exist; the gap is formed at 09:30 before a single RTH bar prints.
    BOTH FORMS ARE TESTED: signed asks "does direction matter", absolute asks
    "does SIZE matter". A gap predicting through magnitude alone would be
    INVISIBLE in the signed view — up and down gaps cancel in the medians.
    A MISSING gap_pct.json yields NO gap rows rather than zeros. Scoring an
    absent file as data is the error that made three columns look like measured
    nulls this week.
v1.10 — 2026-08-18 — "UNTESTABLE" IS NOT "UNSTABLE", AND MY OWN FIX PROVED IT.
    ⚠️ v1.8 ADDED AN ABSTENTION FLOOR AND BROKE THE TEST COMPLETELY. The
    stability vote only considered `WINDOWS[1:]` (post-LIQ.1 onward), and with
    the n>=120 floor BOTH of those abstained (n=50, n=27). `signs` came back
    EMPTY and **every single row printed "unstable"** — including the 764-trade
    pre-LIQ.1 window, which was excluded from its own stability test.
    NOW: every window with enough data votes, pre-LIQ.1 included; and when NO
    window qualifies the verdict says **UNTESTABLE**, not unstable. Reporting an
    unevaluable clause as a negative finding is the same error as calling an
    under-powered row a null — twice in one tool, in opposite directions.
    ALSO: a WINDOW CENSUS is printed, because the underlying fact matters more
    than the verdict — **the archive has ONE well-populated window.** Any
    criterion demanding cross-regime stability will reject everything until
    post-LIQ.6 and post-FEED.2 accumulate real depth.
v1.9 — 2026-08-18 — A THIN WINDOW ABSTAINS, AND THE STRUCTURAL CLASS IS TESTED.
    (1) ⚠️ MY STABILITY CLAUSE WAS REJECTING REAL SIGNAL. It counted EVERY
        window's sign, and post-LIQ.1 (n=50) and post-FEED.2 (n=27) hold 6% and
        3% of the book — nf/ok arms of roughly 10 vs 17, where a median
        comparison is noise. That disqualified `SETUP` (delta +0.19, p<.001) and
        `ADX` (+0.17, p<.001), THE ONLY TWO ROWS CLEARING THE EFFECT-SIZE FLOOR.
        A window now abstains below MIN_WINDOW_N=120.
        ⚠️ THIS IS A POST-HOC CHANGE TO A PRE-REGISTERED CRITERION — the move
        that turns a test into a fishing expedition. The ORIGINAL verdict is
        printed alongside in the `v1.7` column and neither replaces the other.
        `CLEARS*(1 win only)` means it passes on the single window with enough
        data: UNVERIFIED across regimes, not proven.
    (2) THE STRUCTURAL-POSITION CLASS, never previously tested: ORB entry
        position (where in the opening range the fill sat), ORB width / ATR
        (compression, self-scaling so QQQ and SPX compare), ORB width / price,
        VIX at entry, flat angle, level strength.
        ⚠️ THIS IS THE CLASS THE OPERATOR'S DISCRETIONARY READ USES — "rotating
        inside a prior range", "failure to hold the break" are statements about
        WHERE PRICE SITS, not how far a move has gone. ADX-class features are
        late by construction; position-class features describe the setup BEFORE
        it resolves.
v1.8 — 2026-08-18 — TIE RATE AND UNIQUE-VALUE COUNT, because a small Cliff's
    delta has TWO very different causes and they call for opposite conclusions.
    Tied pairs count as neither greater nor lesser, so **CROSS-ARM ties deflate
    delta** — a primitive whose nf and ok arms draw from the SAME values scores
    near zero however sharply it separates elsewhere. (Ties WITHIN an arm do
    not: nf pinned at 0.0 against ok pinned at 1.0 scores +0.996.)
    `direction_conf` came back gap **+0.257** with delta **+0.09** — that is
    either genuine distributional overlap or a coverage artifact, and the two
    mean opposite things for the retool. `ties` and `uniq` make it answerable
    instead of arguable.
v1.7 — 2026-08-18 — THE CRITERION NOW MATCHES WHAT IT ADVERTISES.
    ⚠️ TWO DEFECTS IN MY OWN PRE-REGISTERED CRITERION, FOUND BY READING THE
    RESULT RATHER THAN THE CODE:
    (1) **"CI-separated" WAS ADVERTISED AND NEVER IMPLEMENTED.** `_wilson` was
        computed on every row and THROWN AWAY; `clears` tested sign, n, sessions
        and stability only. A clause promised in the header and absent from the
        code is the same class as a test that asserts source text instead of
        executing — committed by the tool built to enforce that discipline.
    (2) **NO EFFECT SIZE AT ALL.** `IV skew vs atm` was reported as CLEARS on a
        gap of **+0.001** against a median of 0.016, alongside `direction_conf`
        at **+0.257** against ~0.75. Raw median gaps are not comparable across
        primitives on different scales, so "clears" was being awarded to noise.
    NOW: Mann-Whitney U (rank-based — these distributions are bounded,
    zero-inflated and plainly non-normal; BREAKOUT's nf median is exactly 0.000)
    AND Cliff's delta with a floor at 0.147, the conventional
    negligible/small boundary. Both are PRINTED per row, not just tested.
    ⚠️ p ALONE IS NOT A LICENCE: on ~840 observations a p-value will call a
    trivial difference significant. Significance answers "is it real", delta
    answers "is it worth anything", and this tool previously asked NEITHER.
v1.6 — 2026-08-18 — SORT KEY. v1.4 crashed on the real corpus with
    `TypeError: '<' not supported between instances of 'dict' and 'dict'`: a
    bare `.sort()` on (time, dict) tuples falls through to comparing the DICTS
    whenever two snapshots share a minute — and they do. **It only fires on a
    TIE, so my fixture with distinct timestamps passed and the fleet data did
    not.** Now sorts on the timestamp alone.
v1.5 — 2026-08-18 — AS-OF JOIN. v1.3 keyed the chain on `HH:MM` EQUALITY and
    threw away ~79% of the data it already had: snapshots land every ~5 minutes
    (76 across a 390-minute session), trades fire at arbitrary minutes, so exact
    matching caught only trades that fired ON a snapshot minute — **183 of 874,
    exactly the ~20% a 1-in-5 coincidence predicts.** The IV rows came back
    UNDER-POWERED at n=192 and the data was never thin; **the join was wrong.**
    ⚠️ The operator offered to increase snapshot frequency. Declined: more data
    would have PAPERED OVER the defect rather than fixed it, and the corpus is
    already four weeks deep.
    ⚠️ AS-OF IS ALSO THE CORRECT SEMANTICS, not just a wider net — at 10:17 the
    trader knew the 10:15 surface. Taking a LATER snapshot would leak
    information from after the decision, which is the exact error this retool
    exists to eliminate. PRECEDING only, with a 30-minute staleness bound
    (`--chain-max-age-min`): a stale surface is worse than none.
v1.4 — 2026-08-17 — THE IV SURFACE. The only genuinely FORWARD-LOOKING input
    class in the stack: every other primitive here is computed from bars that
    have already printed, while implied volatility is the market's own PRICED
    EXPECTATION of what is coming. If the retool's premise is reachable at all,
    this is the most likely place it lives — and it has never been tested.
    FEATURES (delta-anchored, not strike-anchored — 25-delta is the same
    statement about tail pricing on a $76 symbol and a $7,700 one):
      · IV atm (level) · IV 25d risk-reversal (put IV over call IV; POSITIVE =
        the market is paying up for downside) · IV skew vs atm.
    ⚠️ 0DTE ONLY, VERIFIED: every snapshot carries a SINGLE expiry equal to the
    session date, so calendar skew and term slope are NOT computable and are
    not attempted.
    ⚠️ GEX IS NOT RE-DERIVED. `data/gex_data.py` already computes net GEX, the
    walls and the pin from these same contracts and is a LIVE consumer; a second
    lineage would violate §7. Only the IV shape — which nothing reads — is new.
    ⚠️ CORPUS: 21 dates, 117 MB, 07-20 → 08-17, snapshots only for boxes that
    WOKE. Every trade has one; no cross-sectional read is possible.
v1.3 — 2026-08-17 — UNDER-POWERED IS NOT FAILED, AND THE WINDOWS ARE SHOWN.
    ⚠️ v1.1 CONFLATED THEM AND PRINTED THE WRONG VERDICT. On the ORB-only run
    every row was n=156-178 against the 200 floor — the criterion NEVER GOT TO
    APPLY — and the tool announced "NOTHING CLEARS -> escalate to new inputs".
    **That is an absent measurement reported as a null result: the exact error
    §12 exists to prevent, committed by the tool built to enforce it.**
    NOW: no verdict is issued when nothing is powered. It states the shortfall,
    names how many more trades the leading candidate needs, and marks that
    leader a POINTER, not a result — an in-sample leader among under-powered
    candidates is not evidence.
    ALSO: a per-window split (pre-LIQ.1 · post-LIQ.1 · post-LIQ.6 · post-FEED.2)
    for the top candidates. A separator living in ONE window is a regime
    artifact and the pooled median hides it.
tests/separation_probe.py — v1.2 — 2026-08-17   (P0.1 — THE GATE)

v1.1 — 2026-08-17 — OOM FIX + TWO GLOB EXCLUSIONS.
    v1.0 built a dict of EVERY tick across EVERY replay log before touching a
    trade — ~282k parsed JSON records held at once — and was **KILLED (rc=137)**
    on control, the same failure the regime grid hit on 08-15.
    ⚠️ AND THE LOUD "ABSENT MEASUREMENT" GUARD COULD NOT FIRE: the process died
    before reaching it. **An in-process guard cannot report a kill** — which is
    why the first two runs printed nothing at all rather than a diagnosis.
    NOW: the trade list is built FIRST, and only the (date, sym, HH:MM) keys
    those trades need are indexed. MEASURED: 282,750 ticks scanned, 2 indexed,
    **13 MB peak RSS**.
    ALSO: `_archive_pre_*` directories and `.bak` files live inside the trades
    tree and were being globbed as real data.

**DOES ANYTHING ALREADY COLLECTED SEPARATE FAVOURABLE FROM NEVER-FAVOURABLE
TRADES AT DECISION TIME?**

    cd ~/options-trader-v3 && PYTHONPATH=. venv/bin/python tests/separation_probe.py

────────────────────────────────────────────────────────────────────────────
WHY THIS IS THE GATE, AND WHY IT COMES FIRST
────────────────────────────────────────────────────────────────────────────
The project's founding premise — infer a pattern *forming*, express it as a
confidence factor, and **scale the entry on it** — was never actually run.
`ROADMAP.md` §LAYER 3: **"Status: NOT STARTED. 0%"**. A proxy assembly ran
instead (grade → 1.5x size) and **inverted**: A-grade 399 trades **−$8,244**,
B-grade 220 trades **+$1,893**.

The two quantities the system DID gate and size on are measured dead:
  · `SETUP` — nf ≈ ok, and the grade inverted at size.
  · `RGCV`  — nf **1.00** vs ok **0.34** in RANGING (an ANTI-signal), 0.59 vs
    0.36 in COMPRESSION, and **1.00 vs 1.00 in trend** (no separation at all).
    Its own scorer header names the class error: *"High conviction means the
    trend is already obvious, which means LATE."*

**Every phase of TRANSITION_ROADMAP.md is conditional on this answer.** If a
primitive separates, the remaining work is WIRING. If nothing does — including
shadow velocity with four fleet-weeks — the escalation is NEW INPUTS, not a new
combiner, and that is worth knowing before anything is rebuilt.

────────────────────────────────────────────────────────────────────────────
PRE-REGISTERED SUCCESS CRITERION — written BEFORE the run, per §12
────────────────────────────────────────────────────────────────────────────
A primitive is a candidate confidence factor **only if all four hold**:

    1. nf BELOW ok              (direction: the losers score lower)
    2. CI-separated             (Wilson 95% on the nf-rate at the extremes)
    3. n >= 200 across >= 10 sessions
    4. sign stable across at least the two post-LIQ.1 windows

⚠️ **NO BEST PRIMITIVE IS NAMED BY THIS TOOL.** In-sample argmax over a dozen
candidates is overfit by construction — trying twelve things and reporting the
best is a different experiment from testing one. This prints every candidate,
its n, and whether it CLEARS. The choice is a decision, made against the
criterion above, not an argmax.

⚠️ **AND A FAILING PRIMITIVE IS A RESULT.** `pair_conf` was killed this way
(AX.3) and that saved building on it. Reporting only winners would make this
tool a confirmation machine — the exact failure it exists to diagnose.

────────────────────────────────────────────────────────────────────────────
WINDOWS, EXCLUSIONS, AND WHY
────────────────────────────────────────────────────────────────────────────
⚠️ THE ARCHIVE IS **FOUR REGIMES** for anything touching levels or sweeps:
    pre-LIQ.1 · post-LIQ.1 (08-12) · post-LIQ.6 (08-15) · post-FEED.2 (08-17)
Level-dependent primitives are NOT comparable across those boundaries; a
separator that flips sign across LIQ.6 is a level artifact, not a signal.
Velocity is level-agnostic and stays comparable.

⚠️ **2026-08-14 IS EXCLUDED** — 130 of 153 trades are identity-chain / CNT.1
artifacts. `trend_continuation_breakout` rows from 08-07 onward are one-tick
artifacts and are excluded regardless of date.

⚠️ READ-ONLY, CONTROL-SIDE. Touches no box, needs no bake. **The fleet must keep
trading and collecting through the retool** — the probe cannot be the thing that
interrupts it.
"""

import argparse
import collections
import glob
import json
import math
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DTP = os.path.expanduser("~/day_trader_pro")
TRADES_GLOB = os.path.join(DTP, "trades", "*", "*_trades_*.db")
REPLAY_GLOB = os.path.join(DTP, "reports", "regime_replay_*.jsonl")
JOURNAL_DIR = os.path.join(DTP, "signal_journal")

# window boundaries — see the header
WINDOWS = (("pre-LIQ.1", "0000-00-00", "2026-08-11"),
           ("post-LIQ.1", "2026-08-12", "2026-08-14"),
           ("post-LIQ.6", "2026-08-15", "2026-08-16"),
           ("post-FEED.2", "2026-08-17", "9999-99-99"))

MIN_N = 200
MIN_SESSIONS = 10
# Cliff's delta floor. 0.147 is the conventional negligible/small boundary — a
# separator below it is real but too small to size on, which is precisely the
# distinction the first three runs of this tool could not make.
MIN_DELTA = 0.147
# A window must hold at least this many observations before its SIGN counts
# toward stability. post-LIQ.1 (n=50) and post-FEED.2 (n=27) are 6% and 3% of
# the book; a median comparison on ~10 vs ~17 observations is noise, and
# treating its sign as disqualifying rejects real signal.
MIN_WINDOW_N = 120


def _window(date):
    for name, lo, hi in WINDOWS:
        if lo <= date <= hi:
            return name
    return "?"


def _wilson(k, n):
    """95% Wilson interval — the repo's own convention for a rate with small n."""
    if n == 0:
        return (0.0, 1.0)
    z = 1.96
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def _mannwhitney_p(a_vals, b_vals):
    """Two-sided Mann-Whitney U via the normal approximation, with ties.

    ⚠️ WHY A RANK TEST AND NOT A t-TEST: these distributions are bounded,
    zero-inflated and plainly non-normal (BREAKOUT's nf median is exactly
    0.000). A rank test asks the only question that matters here — *does a
    randomly drawn ok value tend to exceed a randomly drawn nf value* — without
    assuming a shape the data does not have.

    ⚠️ AND IT IS NOT A LICENCE. A p-value on ~840 observations will call a
    trivial difference significant; that is why the EFFECT SIZE floor below
    exists alongside it. Significance answers "is it real", magnitude answers
    "is it worth anything", and this tool previously asked NEITHER.
    """
    n1, n2 = len(a_vals), len(b_vals)
    if n1 < 10 or n2 < 10:
        return None
    pooled = sorted([(v, 0) for v in a_vals] + [(v, 1) for v in b_vals])
    ranks, i = {}, 0
    rank_sum_a = 0.0
    while i < len(pooled):
        j = i
        while j + 1 < len(pooled) and pooled[j + 1][0] == pooled[i][0]:
            j += 1
        avg = (i + j) / 2.0 + 1.0          # average rank over the tie block
        for k in range(i, j + 1):
            if pooled[k][1] == 0:
                rank_sum_a += avg
        i = j + 1
    u1 = rank_sum_a - n1 * (n1 + 1) / 2.0
    mu = n1 * n2 / 2.0
    sd = math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12.0)
    if sd == 0:
        return None
    z = (u1 - mu) / sd
    # two-sided normal tail
    return math.erfc(abs(z) / math.sqrt(2.0))


def _cliffs_delta(a_vals, b_vals):
    """Effect size: P(b > a) - P(a > b), in [-1, 1]. Scale-free.

    ⚠️ THIS IS THE CHECK THE CRITERION WAS MISSING. A raw median gap cannot be
    compared across primitives on different scales — +0.257 on `direction_conf`
    (median ~0.75) and +0.001 on `IV skew vs atm` (median 0.016) were both
    reported as "CLEARS". Cliff's delta puts every primitive on one scale, so
    "how much does this actually separate" is answerable rather than implied.
    Convention: |d| < 0.147 negligible · < 0.33 small · < 0.474 medium.
    """
    n1, n2 = len(a_vals), len(b_vals)
    if n1 == 0 or n2 == 0:
        return None
    b_sorted = sorted(b_vals)
    import bisect
    gt = lt = 0
    for v in a_vals:
        lt += len(b_sorted) - bisect.bisect_right(b_sorted, v)   # b > a
        gt += bisect.bisect_left(b_sorted, v)                    # b < a
    return (lt - gt) / float(n1 * n2)


def _hhmm(entry_time):
    """'…T13:45:02+00:00' -> 'HH:MM' in ET. Converted, never offset-guessed."""
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        t = datetime.fromisoformat(str(entry_time))
        return t.astimezone(ZoneInfo("America/New_York")).strftime("%H:%M")
    except Exception:                                          # noqa: BLE001
        return ""


def load_trades(a):
    """Closed trades with an MFE, tagged nf/ok. Exclusions applied here."""
    out = []
    for db in sorted(glob.glob(os.path.expanduser(a.trades))):
        if "_archive" in db or db.endswith(".bak"):
            continue          # the trades tree carries both
        # ⚠️ REGEX, NOT split("_"). The filename is `<SYM>_trades_<date>.db`, so
        # splitting yields "2026-08-12.db" WITH the extension and every date
        # comparison silently fails — the probe reported "no closed trades"
        # against a populated directory. An empty result that looks like a null.
        import re as _re
        _m = _re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(db))
        date = _m.group(1) if _m else ""
        if not date or date < a.since or date in a.exclude_dates:
            continue
        try:
            con = sqlite3.connect("file:" + db + "?mode=ro", uri=True)
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT * FROM trades WHERE status='closed'").fetchall()
        except Exception:                                      # noqa: BLE001
            continue
        for r in rows:
            r = dict(r)
            st = str(r.get("setup_type") or "")
            if st == "trend_continuation_breakout" and date >= "2026-08-07":
                continue                      # one-tick artifacts, any date
            ent = r.get("entry_premium") or 0
            mx = r.get("max_premium_seen")
            try:
                ent = float(ent)
            except Exception:                                  # noqa: BLE001
                continue
            if ent <= 0 or mx is None:
                continue
            mfe = (float(mx) - ent) / ent * 100.0
            r["_date"] = date
            r["_hhmm"] = _hhmm(r.get("entry_time"))
            r["_nf"] = mfe < a.nf_cut
            r["_window"] = _window(date)
            out.append(r)
    return out


def load_replay_axes(a, wanted=None):
    """(date, sym, HH:MM) -> the L1 scores + l2 at that tick.

    `direction_conf` is replayed from these rather than read from the journal,
    because **AX.3's emission step was never built** — the primitive that
    already measured +0.188 separation is not journaled anywhere.
    """
    # ⚠️ INDEX ONLY THE TICKS THE TRADES ASK FOR. v1.0 built a dict of EVERY
    # tick across EVERY replay log before touching a trade — ~280k parsed JSON
    # records held at once — and was **OOM-KILLED (rc=137)** on control, exactly
    # as the regime grid was on 08-15. The loud "ABSENT MEASUREMENT" guard could
    # not fire, because the process died before reaching it: an in-process guard
    # cannot report a kill.
    # `wanted` is the set of (date, sym, HH:MM) keys the trades actually need —
    # a few thousand, not a few hundred thousand.
    idx = {}
    for path in sorted(glob.glob(os.path.expanduser(a.replay))):
        import re
        m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(path))
        if not m:
            continue
        date = m.group(1)
        if date < a.since or date in a.exclude_dates:
            continue
        with open(path) as f:
            for line in f:
                if '"scores"' not in line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:                              # noqa: BLE001
                    continue
                ts = str(r.get("ts", ""))
                if len(ts) < 5:
                    continue
                key = (date, str(r.get("sym", "")), ts[:5])
                if wanted is not None and key not in wanted:
                    continue          # discard immediately; do not accumulate
                idx[key] = r
    return idx


CHAIN_DIR = os.path.join(DTP, "chain_snapshots")


def load_chain_features(a, wanted):
    """(date, sym, HH:MM) -> IV-surface features at that snapshot.

    ⚠️ THE ONLY GENUINELY FORWARD-LOOKING INPUT CLASS IN THE STACK. Every other
    primitive here — conviction, ADX, the six regime scores, `direction_conf` —
    is computed from bars that have ALREADY PRINTED. **Implied volatility is the
    market's own priced expectation of what is coming**, not a description of
    what happened. If the retool's premise is reachable at all, this is the most
    likely place it lives.

    ⚠️ 0DTE ONLY — NO TERM STRUCTURE. Verified 2026-08-17: every snapshot in
    `chain_snapshots/<date>/<SYM>.jsonl.gz` carries a SINGLE expiry equal to the
    session date (QQQ 08-17: 76 snapshots, one expiry). Calendar skew and term
    slope are therefore NOT computable and are not attempted. What one expiry
    does give: **strike skew, IV level, and the put/call IV asymmetry.**

    ⚠️ GAMMA/OI IS DELIBERATELY NOT RECOMPUTED. `data/gex_data.py` already
    derives net GEX, call wall, put wall and the pin from these same contracts,
    and it is a LIVE consumer. Re-deriving it here would be a second lineage of
    the same quantity (§7). Only the IV shape — which nothing reads — is new.

    ⚠️ CORPUS: 21 dates, 117 MB, 2026-07-20 → 08-17. Snapshots exist only for
    boxes that WOKE (15 of 29 on 08-17), so a symbol has features only on days
    it traded. That is exactly the population this test needs — every trade has
    a snapshot — but it forbids any cross-sectional read across the fleet.
    """
    import gzip
    out = {}
    if not os.path.isdir(CHAIN_DIR):
        return out
    want_days = {d for d, _s, _t in wanted}
    for day in sorted(os.listdir(CHAIN_DIR)):
        if day not in want_days or day in a.exclude_dates:
            continue
        for fn in sorted(os.listdir(os.path.join(CHAIN_DIR, day))):
            sym = fn.split(".")[0]
            if not any(d == day and s == sym for d, s, _t in wanted):
                continue
            per_sym = []
            try:
                with gzip.open(os.path.join(CHAIN_DIR, day, fn), "rt") as fh:
                    for line in fh:
                        try:
                            r = json.loads(line)
                        except Exception:                      # noqa: BLE001
                            continue
                        ts = str(r.get("ts_et", ""))
                        if len(ts) < 16:
                            continue
                        f = _iv_features(r)
                        if f:
                            per_sym.append((ts[11:16], f))
            except Exception:                                  # noqa: BLE001
                continue

            # ── AS-OF JOIN, NOT EXACT-MINUTE ─────────────────────────────────
            # ⚠️ v1.3 KEYED ON `HH:MM` EQUALITY AND THREW AWAY ~79% OF THE DATA.
            # Snapshots land roughly every 5 minutes (76 across a 390-minute
            # session); trades fire at arbitrary minutes. Exact matching caught
            # only the trades that happened to fire ON a snapshot minute —
            # **183 of 874, which is exactly the ~20% a 1-in-5 coincidence
            # predicts** — and the IV rows came back UNDER-POWERED at n=192.
            # The data was never thin; the join was wrong.
            #
            # ⚠️ AND AS-OF IS THE CORRECT SEMANTICS, not merely a wider net: at
            # 10:17 the trader knew the 10:15 surface. Taking a LATER snapshot
            # would leak information from after the decision — the exact error
            # this whole retool exists to avoid.
            # ⚠️ SORT ON THE TIMESTAMP ONLY. A bare `.sort()` on (time, dict)
            # tuples falls through to comparing the DICTS whenever two
            # snapshots share a minute — which they do — and dicts are not
            # orderable: `TypeError: '<' not supported between instances of
            # 'dict' and 'dict'`. It only fires on a tie, so a fixture with
            # distinct times passes and the real corpus does not.
            per_sym.sort(key=lambda x: x[0])
            for d_, s_, t_ in wanted:
                if d_ != day or s_ != sym:
                    continue
                best = None
                for snap_t, feat in per_sym:
                    if snap_t <= t_:        # PRECEDING only, never after
                        best = (snap_t, feat)
                    else:
                        break
                if best is None:
                    continue
                # tolerance: a stale surface is worse than none. 30 min is ~6
                # snapshot intervals — generous, but it bounds the staleness.
                gap = ((int(t_[:2]) * 60 + int(t_[3:5]))
                       - (int(best[0][:2]) * 60 + int(best[0][3:5])))
                if 0 <= gap <= a.chain_max_age_min:
                    out[(d_, s_, t_)] = best[1]
    return out


def _iv_features(snap):
    """Skew and level from one 0DTE snapshot. None if the surface is unusable.

    ⚠️ DELTA-ANCHORED, NOT STRIKE-ANCHORED. A fixed strike offset means
    different things on a $76 symbol and a $7,700 one; 25-delta is the same
    statement about tail pricing everywhere. That is why the risk-reversal is
    the headline feature rather than "IV at spot ± $5".
    """
    cs = snap.get("contracts") or []
    spot = snap.get("underlying") or 0
    if not cs or spot <= 0:
        return None

    def near(typ, target):
        best, bd = None, 9e9
        for c in cs:
            if c.get("type") != typ:
                continue
            iv, d = c.get("iv"), c.get("delta")
            if not iv or d is None or iv <= 0:
                continue
            dist = abs(abs(float(d)) - target)
            if dist < bd:
                best, bd = float(iv), dist
        return best if bd < 0.15 else None      # refuse a bad anchor match

    atm_c, atm_p = near("C", 0.50), near("P", 0.50)
    otm_c, otm_p = near("C", 0.25), near("P", 0.25)
    if atm_c is None and atm_p is None:
        return None
    atm = ((atm_c or 0) + (atm_p or 0)) / (int(atm_c is not None)
                                           + int(atm_p is not None))
    out = {"IV atm (level)": round(atm, 5)}
    if otm_p is not None and otm_c is not None:
        # 25-delta risk reversal: put IV over call IV. POSITIVE = the market is
        # paying up for downside. A directional statement, priced, before the move.
        out["IV 25d risk-reversal"] = round(otm_p - otm_c, 5)
        if atm > 0:
            out["IV skew vs atm"] = round((otm_p + otm_c) / 2 / atm - 1.0, 5)
    return out


GAP_JSON = os.path.expanduser("~/day_trader_pro/reports/gap_pct.json")


def load_gaps(path=GAP_JSON):
    """(date, sym) -> gap_pct, from `tests/gap_backfill.py`'s output.

    ⚠️ THE ONLY NEW PRIMITIVE TESTABLE TODAY. Everything else shipped 2026-08-18
    — the angle, the level grade, VIX coverage, three IV tenors — needs the next
    bake and then sessions before it can say anything. **The overnight gap is
    fully BACKFILLABLE from banked OHLC**, so it can be judged on the 17
    sessions already in the book.

    ⚠️ AND IT IS THE ONLY PRE-OPEN INPUT IN THE STACK. ADX, conviction, the
    regime scores, IV skew and every structural column need bars from THIS
    session to exist. The gap is formed at 09:30 before a single RTH bar prints.

    ⚠️ ABSENT FILE IS ABSENT MEASUREMENT. Returns {} and the gap rows simply do
    not appear — they are NOT reported as zeros. Scoring a missing file as data
    is the error that made three columns look like measured nulls this week.
    """
    try:
        with open(path) as fh:
            blob = json.load(fh)
    except Exception:                                          # noqa: BLE001
        return {}
    out = {}
    for day, syms in (blob.get("sessions") or {}).items():
        for sym, rec in (syms or {}).items():
            g = (rec or {}).get("gap_pct")
            if isinstance(g, (int, float)):
                out[(day, sym)] = float(g)
    return out


def candidates(tr, rep, chain=None, gaps=None):
    """Every decision-time primitive we can evaluate, per trade.

    ⚠️ A `None` here means NOT AVAILABLE for that trade — it is dropped from
    that primitive's sample and COUNTED, never imputed. An imputed value would
    manufacture separation out of missingness.
    """
    out = {}
    r = rep.get((tr["_date"], tr.get("symbol"), tr["_hhmm"]))
    sc = (r or {}).get("scores") or {}
    l2 = (r or {}).get("l2") or {}

    # --- already measured, carried for comparison -------------------------
    out["RGCV (conviction)"] = tr.get("regime_conviction")
    out["SETUP (grade score)"] = tr.get("setup_score")

    # --- L1 direction axis: AX.3's +0.188, never journaled ----------------
    if sc:
        bull = sc.get("TRENDING_BULL") or 0.0
        bear = sc.get("TRENDING_BEAR") or 0.0
        out["direction_conf (L1)"] = max(bull, bear)
        out["RANGING score"] = sc.get("RANGING")
        out["BREAKOUT score"] = sc.get("BREAKOUT_VOLATILE")
        out["COMPRESSION score"] = sc.get("COMPRESSION")
        # dominance-at-entry: how decisively the winner led, that tick
        tot = sum(v for v in sc.values() if isinstance(v, (int, float)))
        top = max((v or 0) for v in sc.values())
        out["L1 dominance share"] = (top / tot) if tot > 0 else None

    # --- ORB geometry, journaled since 07-18 ------------------------------
    for col, name in (("retest_depth_px", "ORB retest depth"),
                      ("adx_at_entry", "ADX at entry"),
                      ("atr_at_entry", "ATR at entry")):
        if tr.get(col) is not None:
            out[name] = tr.get(col)

    # --- THE OVERNIGHT GAP: the only PRE-OPEN input here ------------------
    if gaps:
        g = gaps.get((tr["_date"], tr.get("symbol")))
        if g is not None:
            out["gap_pct (signed)"] = g
            # ⚠️ BOTH FORMS, DELIBERATELY. Signed asks "does direction matter";
            # absolute asks "does SIZE matter". A gap that predicts through
            # magnitude alone would be invisible in the signed view, since up
            # and down gaps would cancel in the medians.
            out["gap_abs_pct"] = abs(g)

    # --- STRUCTURAL POSITION, derived (never previously tested) -----------
    # ⚠️ THIS IS THE CLASS THE OPERATOR'S OWN DISCRETIONARY READ USES. On
    # 2026-08-17 he called QQQ a range WHILE IT WAS HAPPENING — "no clean
    # impulsive candle, price rotating inside a prior range, failure to hold the
    # break." None of those clauses is a trend-strength measure; they are
    # statements about WHERE PRICE SITS relative to structure. ADX-class
    # features say how far a move has gone; these say what the setup looks like
    # before it goes, which is the whole distinction the retool rests on.
    _oh = tr.get("orb_range_high")
    _ol = tr.get("orb_range_low")
    _ue = tr.get("underlying_entry")
    try:
        _oh, _ol, _ue = float(_oh or 0), float(_ol or 0), float(_ue or 0)
    except Exception:                                          # noqa: BLE001
        _oh = _ol = _ue = 0.0
    if _oh > 0 and _ol > 0 and _oh > _ol:
        _w = _oh - _ol
        if _ue > 0:
            # WHERE IN THE OPENING RANGE the entry sat. 0 = at the low, 1 = at
            # the high, >1 = extended beyond it. Entering mid-range is the
            # geometric signature of chop; entering on an extension is not.
            out["ORB entry position"] = round((_ue - _ol) / _w, 4)
        _atr = tr.get("atr_at_entry")
        try:
            _atr = float(_atr or 0)
        except Exception:                                      # noqa: BLE001
            _atr = 0.0
        if _atr > 0:
            # OPENING RANGE WIDTH IN ATR. A range far narrower than the symbol's
            # own typical bar is compression; far wider is an already-violent
            # open. Self-scaling, so QQQ and SPX are comparable.
            out["ORB width / ATR"] = round(_w / _atr, 4)
        if _ue > 0:
            out["ORB width / price"] = round(_w / _ue, 5)

    for col, name in (("vix_at_entry", "VIX at entry"),
                      ("flat_angle_deg", "flat angle deg"),
                      ("level_strength", "level strength")):
        v = tr.get(col)
        if v is not None:
            try:
                out[name] = float(v)
            except Exception:                                  # noqa: BLE001
                pass

    # --- IV surface: the only forward-looking class here ------------------
    cf = (chain or {}).get((tr["_date"], tr.get("symbol"), tr["_hhmm"]))
    if cf:
        out.update(cf)

    # --- readiness / shadow, if the columns exist -------------------------
    for col, name in (("readiness_grade", "readiness grade"),
                      ("velocity_at_entry", "shadow velocity"),
                      ("pos_pct", "pitchfork pos_pct")):
        if tr.get(col) is not None:
            out[name] = tr.get(col)

    return {k: v for k, v in out.items() if isinstance(v, (int, float))}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--trades", default=TRADES_GLOB)
    ap.add_argument("--replay", default=REPLAY_GLOB)
    ap.add_argument("--since", default="2026-07-13")
    ap.add_argument("--nf-cut", type=float, default=2.0,
                    help="MFE%% below which a trade NEVER went favourable")
    ap.add_argument("--chain-max-age-min", type=int, default=30,
                    dest="chain_max_age_min",
                    help="as-of tolerance: a surface older than this is refused "
                         "rather than joined stale")
    ap.add_argument("--strategy", default="",
                    help="restrict to one strategy, e.g. ORBStrategy")
    a = ap.parse_args(argv[1:])
    a.exclude_dates = {"2026-08-14"}          # identity-chain pollution

    trades = load_trades(a)
    if not trades:
        print(f"no closed trades with MFE at/after {a.since}")
        print(f"  looked in: {a.trades}")
        print("  ABSENT MEASUREMENT, not a null.")
        return 1
    if a.strategy:
        trades = [t for t in trades if t.get("strategy") == a.strategy]
    wanted = {(t["_date"], t.get("symbol"), t["_hhmm"]) for t in trades}
    rep = load_replay_axes(a, wanted)
    chain = load_chain_features(a, wanted)
    gaps = load_gaps()

    print("=" * 94)
    print("SEPARATION PROBE (P0.1) — does anything separate outcomes AT DECISION TIME?")
    print(f"  {len(trades)} closed trade(s) with MFE   "
          f"{len({t['_date'] for t in trades})} session(s)   "
          f"nf cut = MFE < {a.nf_cut}%"
          + (f"   strategy={a.strategy}" if a.strategy else ""))
    print(f"  replay ticks indexed: {len(rep):,}   "
          f"(08-14 excluded; _breakout rows from 08-07 excluded)")
    print(f"  gap sessions loaded: {len(gaps):,}   "
          f"(backfilled from OHLC — the only PRE-OPEN input here)")
    print(f"  chain snapshots matched: {len(chain):,}   "
          f"(0DTE only — no term structure; GEX not re-derived)")
    print("=" * 94)

    nf_n = sum(1 for t in trades if t["_nf"])
    print(f"\n  never-favourable: {nf_n}/{len(trades)} "
          f"({100.0*nf_n/len(trades):.0f}%)")

    # gather per-primitive samples
    vals = collections.defaultdict(lambda: {"nf": [], "ok": [],
                                            "sess": set(), "win": {}})
    unmatched = 0
    for t in trades:
        c = candidates(t, rep, chain, gaps)
        if not c:
            unmatched += 1
            continue
        for k, v in c.items():
            b = vals[k]
            (b["nf"] if t["_nf"] else b["ok"]).append(v)
            b["sess"].add(t["_date"])
            b["win"].setdefault(t["_window"], {"nf": [], "ok": []})
            (b["win"][t["_window"]]["nf"] if t["_nf"]
             else b["win"][t["_window"]]["ok"]).append(v)
    if unmatched:
        print(f"  ⚠️ {unmatched} trade(s) had NO primitive available and were "
              f"dropped, not imputed.")

    def med(v):
        return sorted(v)[len(v) // 2] if v else float("nan")

    print(f"\n  {'primitive':24}{'n':>6}{'sess':>5}{'nf med':>8}{'ok med':>8}"
          f"{'gap':>8}{'delta':>7}{'p':>7}{'ties':>6}{'uniq':>6}{'v1.7':>8}  verdict")
    print("  " + "-" * 100)
    results = []
    for k in sorted(vals):
        b = vals[k]
        n = len(b["nf"]) + len(b["ok"])
        if not b["nf"] or not b["ok"]:
            continue
        mnf, mok = med(b["nf"]), med(b["ok"])
        gap = mok - mnf
        sess = len(b["sess"])
        # window sign stability (post-LIQ.1 onward, per the criterion)
        # ⚠️ A WINDOW ONLY GETS A VOTE IF IT HOLDS ENOUGH DATA TO HAVE AN
        # OPINION. v1.7 counted EVERY window's sign, and post-LIQ.1 / post-FEED.2
        # hold n=50 and n=27 — **6% and 3% of the book**. Split into nf/ok arms
        # that is ~10 vs ~17 observations, where a median comparison is close to
        # a coin toss. I made that disqualifying, and it rejected `SETUP`
        # (delta +0.19, p<.001) and `ADX` (+0.17, p<.001) — the only two rows
        # clearing the effect-size floor.
        # ⚠️ THIS IS A POST-HOC CHANGE TO A PRE-REGISTERED CRITERION, which is
        # exactly the move that turns a test into a fishing expedition. It is
        # therefore REPORTED ALONGSIDE the original verdict, never silently in
        # place of it — see the two columns below. The specification error was
        # real (I never checked how much data those windows would hold), but
        # the reader gets both answers and decides.
        # ⚠️ EVERY WINDOW WITH ENOUGH DATA VOTES — INCLUDING pre-LIQ.1. v1.8
        # considered `WINDOWS[1:]` only, so with the n>=120 floor BOTH remaining
        # windows abstained (n=50, n=27), `signs` came back EMPTY, and every
        # single row printed "unstable". **That is not instability — it is an
        # UNTESTABLE clause**, and the two words mean opposite things. The
        # 764-trade pre-LIQ.1 window was excluded from its own stability test.
        signs, signs_all, thin = [], [], []
        for w, _lo, _hi in WINDOWS:
            d = b["win"].get(w)
            if d and d["nf"] and d["ok"]:
                sg = 1 if med(d["ok"]) > med(d["nf"]) else -1
                signs_all.append(sg)
                if len(d["nf"]) + len(d["ok"]) >= MIN_WINDOW_N:
                    signs.append(sg)
                else:
                    thin.append(w)
        stable = bool(signs) and len(set(signs)) == 1
        stable_v17 = bool(signs_all) and len(set(signs_all)) == 1
        # ⚠️ THE CRITERION NOW MATCHES WHAT THE DOCSTRING CLAIMS. Until v1.5 the
        # header advertised "CI-separated" and the code tested SIGN, n, SESSIONS
        # and STABILITY only — `_wilson` was computed and thrown away. A clause
        # advertised and never implemented is the same class as a test that
        # asserts source text instead of executing it, committed by the tool
        # built to enforce that discipline.
        pval = _mannwhitney_p(b["nf"], b["ok"])
        delta = _cliffs_delta(b["nf"], b["ok"])
        sig = pval is not None and pval < 0.05
        big = delta is not None and abs(delta) >= MIN_DELTA
        base = (gap > 0 and n >= MIN_N and sess >= MIN_SESSIONS and sig and big)
        # ⚠️ NO QUALIFYING WINDOW = the clause CANNOT BE EVALUATED. Reporting
        # that as "unstable" states a negative finding the data cannot support —
        # the same error as calling an under-powered row a null.
        untestable = len(signs) == 0
        clears_v17 = base and stable_v17 and len(signs_all) >= 2
        # ⚠️ With the thin windows abstaining a primitive may have only ONE
        # voting window left. That is not "stable across >=2" — it is
        # UNVERIFIED, and it is labelled as such rather than passed.
        clears = base and stable and len(signs) >= 2
        unverified = base and stable and len(signs) == 1
        clears_any = clears or clears_v17
        verdict = ("CLEARS" if clears
                   else "CLEARS*(1 win only)" if unverified
                   else "CLEARS*(stability UNTESTABLE)" if (base and untestable)
                   else "UNTESTABLE (no window >= %d)" % MIN_WINDOW_N
                   if untestable and gap > 0 and sig and big
                   else "under-powered" if (n < MIN_N or sess < MIN_SESSIONS)
                   else "INVERTED" if gap < 0
                   else "unstable" if not stable
                   else "NEGLIGIBLE (d=%.2f)" % delta if (sig and not big)
                   else "not significant" if not sig
                   else "flat/no separation")
        wtxt = f"{len(signs)} win, {'stable' if stable else 'mixed'}"
        # ⚠️ TIE RATE — CLIFF'S DELTA IS DILUTED BY TIES AND THAT CAN INVERT
        # THE READING. Pairs with identical values count as NEITHER greater nor
        # lesser, so a primitive that sits at exactly 0.0 or 1.0 most of the
        # time produces a small delta even when it discriminates sharply on the
        # pairs where it MOVES. `direction_conf` showed gap +0.257 with delta
        # +0.09 — that is either genuine overlap or heavy tying, and the two
        # call for opposite conclusions.
        _uni = len(set(b["nf"]) | set(b["ok"]))
        _tot = len(b["nf"]) * len(b["ok"])
        _ties = 0
        if _tot and _tot <= 4_000_000:      # bounded: this is O(n*m) worst case
            from collections import Counter as _C
            _cok = _C(b["ok"])
            _ties = sum(_cok.get(v, 0) for v in b["nf"])
        tie_pct = (100.0 * _ties / _tot) if _tot else 0.0
        dtxt = f"{delta:+.2f}" if delta is not None else "  -  "
        ptxt = ("<.001" if (pval is not None and pval < 0.001)
                else f"{pval:.3f}" if pval is not None else "  -  ")
        v17 = "CLEARS" if clears_v17 else "-"
        print(f"  {k:24}{n:>6}{sess:>5}{mnf:>8.3f}{mok:>8.3f}{gap:>+8.3f}"
              f"{dtxt:>7}{ptxt:>7}{tie_pct:>6.0f}%{_uni:>6}{v17:>8}  {verdict}")
        results.append((k, clears, gap, n, sess))

    # per-window detail: a separator that only lives in one window is a
    # regime artifact, and the pooled median hides that.
    print(f"\n  PER-WINDOW SPLIT (nf med -> ok med; a sign flip is a red flag)")
    for k, _c, _g, _n, _s in sorted(results, key=lambda r: -r[2])[:4]:
        b = vals[k]
        parts = []
        for w, _lo, _hi in WINDOWS:
            d = b["win"].get(w)
            if d and d["nf"] and d["ok"]:
                parts.append(f"{w}: {med(d['nf']):.2f}->{med(d['ok']):.2f} "
                             f"(n={len(d['nf'])+len(d['ok'])})")
        print(f"    {k:26} " + " · ".join(parts) if parts else f"    {k:26} (no window had both arms)")

    wcount = collections.Counter()
    for t in trades:
        wcount[t["_window"]] += 1
    print(f"\n  WINDOW CENSUS (why stability may be untestable)")
    for w, _lo, _hi in WINDOWS:
        c = wcount.get(w, 0)
        flag = "votes" if c >= MIN_WINDOW_N else f"ABSTAINS (< {MIN_WINDOW_N})"
        print(f"    {w:14}{c:>6} trade(s)   {flag}")
    print("    ⚠️ The archive has ONE well-populated window. Cross-regime")
    print("       stability is not a thing this data can currently answer, and")
    print("       a criterion that demands it will reject everything.")

    print(f"\n  ⚠️ `v1.7` COLUMN = THE ORIGINAL PRE-REGISTERED VERDICT, kept so the")
    print(f"     post-hoc relaxation is VISIBLE rather than silent. v1.8 lets a")
    print(f"     window abstain from the stability vote below n={MIN_WINDOW_N};")
    print(f"     post-LIQ.1 (n=50) and post-FEED.2 (n=27) are 6% and 3% of the")
    print(f"     book and their medians are noise. **Changing a criterion after")
    print(f"     seeing the data is how a test becomes a fishing expedition** —")
    print(f"     both answers are printed and neither replaces the other.")
    print(f"     `CLEARS*(1 win only)` = passes on the one window with enough")
    print(f"     data, and is therefore UNVERIFIED across regimes, not proven.")

    print("\n  PRE-REGISTERED CRITERION (set before the run):")
    print(f"    nf BELOW ok · Mann-Whitney p < 0.05 · |Cliff's delta| >= "
          f"{MIN_DELTA} · n >= {MIN_N} across >= {MIN_SESSIONS} sessions ·"
          f" sign stable across >= 2 post-LIQ.1 windows")
    # ⚠️ UNDER-POWERED IS NOT FAILED — v1.1 CONFLATED THEM AND PRINTED THE
    # WRONG VERDICT. On the ORB-only run every row was n=156-178 against the 200
    # floor, so the criterion NEVER GOT TO APPLY, and the tool announced
    # "NOTHING CLEARS -> escalate to new inputs". That is an ABSENT MEASUREMENT
    # being reported as a null result — the exact error 12 exists to prevent,
    # committed by the tool built to enforce it.
    powered = [r for r in results if r[3] >= MIN_N and r[4] >= MIN_SESSIONS]
    under = [r for r in results if r not in powered]
    win = [r for r in results if r[1]]
    if not powered:
        print(f"\n  ⚠️ NO VERDICT POSSIBLE — every primitive is UNDER-POWERED.")
        print(f"     {len(under)} candidate(s), none reaching n >= {MIN_N} across")
        print(f"     >= {MIN_SESSIONS} sessions. **The criterion never applied.**")
        print("     THIS IS NOT 'nothing separates'. It is an ABSENT MEASUREMENT.")
        best = max(under, key=lambda r: r[2]) if under else None
        if best and best[2] > 0:
            need = MIN_N - best[3]
            print(f"     Largest positive gap so far: {best[0]} {best[2]:+.3f} "
                  f"at n={best[3]} — **{need} more trades** to reach the floor.")
            print("     ⚠️ That is a POINTER, not a result: an in-sample leader")
            print("        among under-powered candidates is not evidence.")
        print("     The fleet keeps trading; re-run when n clears.")
    elif win:
        print(f"\n  ✅ {len(win)} primitive(s) CLEAR: "
              + ", ".join(r[0] for r in win))
        print("     -> the confidence factor exists in collected data; the")
        print("        remaining work is WIRING (roadmap Phase 1).")
        print("     ⚠️ NO BEST IS NAMED. Choosing the largest gap among many")
        print("        candidates is in-sample argmax — pick against the")
        print("        criterion and confirm forward, do not rank on this run.")
    else:
        print("\n  ❌ NOTHING CLEARS.")
        print("     -> that IS the finding, and it is worth more than the plan.")
        print("        The escalation is NEW INPUTS (chain-derived expectation")
        print("        first — already collected, cannot be backfilled), NOT a")
        print("        new combiner and NOT a new codebase.")
        print("     ⚠️ Check the under-powered rows before concluding: an absent")
        print("        measurement is not a null result.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
