# HISTORY — incidents, audits, and completed specs

Resolved work, kept for the record. Read before re-litigating a fix: these describe why things are the way they are.

**Consolidated 2026-07-28.** Nothing was rewritten or summarised — each
former file is preserved verbatim as a section below, so historical
decisions stay on the record and fixes don't get quietly reverted.

## Contents

- **options_trader v3.0 — CHANGELOG**  <sub>(was `docs/CHANGELOG.md`)</sub>
- **DIAGNOSIS RESPONSE — DXLink session exhaustion — 2026-07-13**  <sub>(was `docs/DIAGNOSIS_session_exhaustion_2026-07-13.md`)</sub>
- **HANDOFF — DXLink session-exhaustion fix — state as of 2026-07-13 (night)**  <sub>(was `docs/HANDOFF_dxlink_fix_state.md`)</sub>
- **AUDIT — Paper→Live behavioral divergence · 2026-07-15**  <sub>(was `docs/AUDIT_paper_live_divergence_2026-07-15.md`)</sub>
- **AUDIT — Header/Changelog Compliance + Stale-Reference Sweep — 2026-07-23**  <sub>(was `docs/AUDIT_header_compliance_2026-07-23.md`)</sub>
- **FABLE SPEC — Live exit fill-confirmation (`_confirm_and_book_live_exit`)**  <sub>(was `docs/FABLE_SPEC_live_exit_fill_confirmation.md`)</sub>

---


<!-- ================= was: docs/CHANGELOG.md ================= -->

##### options_trader v3.0 — CHANGELOG
**2026-07-10 — Yahoo-Finance purge & data stream mapping optimization**
Built against options_trader_v2 `main` @ HEAD `a181dd2fd10c2f8c7c1cb97792edcea565afc71c`.
v2 repo preserved untouched; this tree is the new v3 repo root.

##### Why
The bot trades and logs on TastyTrade (DXLink/DXFeed) candles, but market data
was pulled from the legacy Yahoo-Finance client — a different series that
provably diverges from the traded tape (caught on the 5-minute opening range).
Every process now derives its data from the same TastyTrade feed the bot
trades on. The purge is total: the legacy-source residue grep (§6.4 of the
purge spec, run via `tests/verify_feed_v3.sh`) returns zero hits across code,
config, shell, docs, and requirements — including this changelog.

##### Architecture (one producer, many readers — per box)
- **NEW `data/candle_feed.py` v3.0 + `candle-feed.service`** — owns the box's
  ONLY DXLinkStreamer subscription: this box's symbol across 1m/5m/15m/1h/1d
  plus VIX (1m/1d). Per-interval backfill (session open for 1m; deeper for
  higher TFs), last-write-wins bar correction, reconnect w/ backoff, bounded
  rolling history, reuses get_session()/get_loop(). Persists to SQLite (WAL):
  `candles(symbol,interval,ts_epoch_ms,o,h,l,c,v)` + `feed_meta` (per-interval
  last_write + global heartbeat). Index boxes: `OT_DXFEED_SYMBOL` override;
  store path override: `OT_FEED_DB`.
- It is FORBIDDEN for any consumer (bot, shadow observer, candle logger,
  query tools) to open its own DXFeed stream.

##### Changed files (logic)
| File | v | Change |
|---|---|---|
| `data/candle_feed.py` | 3.0 | NEW — single producer service |
| `deploy/candle-feed.service` | 3.0 | NEW — reference unit (setup_ec2 generates the real one) |
| `data/market_data.py` | 3.0 | Rewritten as store READER. Contract preserved exactly: `fetch_candles`/`fetch_quote`/`fetch_all_candles` signatures + return shapes unchanged. Fail loud: None + WARNING on missing store or heartbeat > `OT_FEED_STALE_S` (120s). Young session returns real partial data; intraday windows never padded across the overnight gap (`OT_FEED_INTRADAY_SCOPE=continuous` escape hatch). Yahoo period map deleted. |
| `data/macro_data.py` | 3.0 | VIX via `fetch_quote("VIX")` (store-first, TastyTrade REST secondary — the one sanctioned non-DXFeed fallback). Stale→default-20 chain preserved, now WARNING-level. |
| `data/candle_logger.py` | 3.0 | Converted to store CONSUMER (no second subscription); same CSV output; its old subscribe/drain moved into candle_feed as a persistent stream. |
| `data/data_cache.py` | 3.0 | ONE surgical fix (staleness guard): refresh failing past 3× staleness ceiling ⇒ `get()` returns None — a dead feed can no longer be masked by an aging cached frame. |
| `setup_ec2.sh` | 3.2 | Yahoo dep dropped; installs/enables candle-feed.service; optionsbot `After=`/`Wants=` candle-feed; feed starts first. |
| `requirements.txt` | — | Yahoo dep removed; no new deps (sqlite3 stdlib). |
| `deploy/candle-logger.service` | 3.0 | Consumer notes; no creds needed by logger. |
| `test_candle_logger.py` | 3.0 | Rewritten for store-consumer design (synthetic store, offline). |
| `tests/test_market_data_contract.py` | 3.0 | NEW — seam contract acceptance test (§6.1), offline. |
| `tests/verify_feed_v3.sh` | 3.0 | NEW — ON-BOX acceptance gate: single-subscription proof, store health, ORB equivalence, zero-Yahoo grep. |

##### Comment/doc scrubs (no logic change)
`analysis/get_orb_range.py` (v3.0 entry), `analysis/orb_engine.py`,
`README.md` (v3.0 changelog + deps), `deploy/README_candle_logger.md`.

##### Repo-wide v3.0 bump (no logic change)
Every remaining .py/.sh received a `v3.0 — 2026-07-10` changelog entry citing
the purge, with title versions set to v3.0: all engines, strategies,
execution, risk, notifications, database, utils, main.py, config.py, query.py,
status.py, eod_summary.py, and all shell tooling.

##### NOT touched
Trading/risk/execution/strategy logic, `PAPER_TRADING` default (True),
Telegram, broker reconciliation, GEX, ORB engine logic — all behavior
unchanged above the data seam. The off-repo shadow observer rides the
preserved `get_cache()` seam with zero changes (restart it after deploy).

##### Verification status
- §6.1 Contract test: **17/17 PASS** offline (`python -m tests.test_market_data_contract`).
- §6.4 Zero-Yahoo grep: **CLEAN** repo-wide.
- §6.2 ORB equivalence + §6.3 single-subscription proof: **ON-BOX gates** —
  run `bash tests/verify_feed_v3.sh` on one box during RTH (paper) before
  fleet deploy. Also confirms backfill depth per interval (entitlement) and
  VIX entitlement per the candle_feed FIRST-RUN CHECKLIST.

---


<!-- ================= was: docs/DIAGNOSIS_session_exhaustion_2026-07-13.md ================= -->

##### DIAGNOSIS RESPONSE — DXLink session exhaustion — 2026-07-13

Verified against fleet HEAD `818d312` in a pinned worktree, the GOOGL HEAD `a42445e`,
and the **actual installed tastytrade SDK 13.0.0 source** (not its docs). Verdict up
front: **§3 is CONFIRMED with one correction and one addition. §1's causal chain is
half wrong — the mechanism that blocked the trades is not the regime.** Details, then
solutions.

---

##### 1 · The three questions, answered from code

##### Q1 — Is `fetch_chain()` genuinely opening a new DXLinkStreamer per tick?

**YES — confirmed, and it's worse than stated.** `main.py:775` calls
`get_chain_fetcher().fetch_chain()` under the comment "*Compute GEX every tick*",
unconditionally, every 15 s poll. That reaches `_async_fetch_greeks_quotes`
(`options_chain.py:218`): `async with DXLinkStreamer(session)` per call.

The addition: SDK 13.0.0's context entry does a **fresh REST call
(`GET /api-quote-tokens`) on every open** before dialing the websocket. So each tick
is: REST token fetch → TCP+TLS+WS handshake → SETUP → AUTH → subscribe → collect →
teardown. Per box, ~4 full connection lifecycles per minute, ~1,560 per RTH session.
×24–28 boxes.

`main.py:471` (entry path) is NOT a second churn source — `ctx.get("chain") or fetch`
reuses the tick's chain. Position management receives the same `ctx["chain"]`.

##### Q2 — Anything else opening DXLink connections?

**NO.** Full-tree enumeration at `818d312`: exactly two live openers —
`candle_feed.py:327` (persistent, one per box, correct) and `options_chain.py:218`
(per-tick, the problem). `gex_data` consumes the chain (confirmed — no streamer).
`check_sdk.py` is a manual diagnostic. The `observer/` tarballs cannot be grepped
(defect D) — if the shadow subsystem is running anywhere, it is unaudited; worth one
`fleet.py run "ss -tnp | grep -c 443"`-style check, but nothing in the *importable*
tree opens a third stream.

##### Q3 — Is there a teardown/close() bug making sessions leak?

**NO client-side leak — read the SDK's actual lifecycle.** `__asynccontextmanager__`
nests `AsyncClient` → `aconnect_ws` → `create_task_group`. On BOTH the happy path and
the error path (the `_reader` task raises `TastytradeError("Fatal streamer error: …")`
on the ERROR frame — which surfaces exactly as your logged *"unhandled errors in a
TaskGroup (1 sub-exception)"*), the stack unwinds through the context managers and the
websocket is closed. Python is releasing the sockets.

**The pile-up is server-side accounting, and the protocol explains it.** The SDK's
SETUP message negotiates `keepaliveTimeout: 60` — DXLink holds a session slot up to
60 s around each connection's lifecycle. With a 15 s redial cadence, each churning box
plausibly occupies **2–4 session slots at once** (one live + recently-closed slots
still inside their timeout window). 24 churning boxes × 2–4 + 29 persistent
candle-feeds ≈ **75–140 slots demanded** against an unpublished cap. I searched; the
cap is genuinely not published anywhere (developer docs, SDK repos, help center). We
know only: 29 persistent feeds alone ran fine for weeks → cap > 29; last-week's
steady state with churn also ran → the tip into failure was likely marginal.

**This also explains your two dead ends.** Restarting one box does nothing because the
pool is an account-level resource kept saturated by everyone else's redials. And the
failure is self-sustaining: **every rejected attempt is itself a short-lived session**
(the ERROR arrives after connect), so 24 boxes retrying every 15 s hold the pool at
the ceiling indefinitely. It will not heal while the bots run. Stopping the fleet was
the right call and is the only thing that drains it.

---

##### 2 · CORRECTION to §1 — the causal chain that actually blocked the trades

The handoff's chain says: *no Greeks → GEX empty → regime degrades to UNKNOWN →
hard gate → no trades.* **The regime link is wrong, and your own fleet table proves
it:** most boxes sat in RANGING/COMPRESSION, not UNKNOWN.

The classifier's signature is `classify(vol_state, trend_state, structure, liq_map,
macro, trigger)` — **it consumes nothing chain- or GEX-derived.** Regimes were
computed normally all day off the (healthy) candle store. The GOOGL log line you
quoted is that one box's dispatch message, not the fleet mechanism.

**The real kill path is the liquidity filter.** With the streamer rejected,
`_fetch_greeks_and_quotes` returns `({}, {})`, `_apply_market_data` never runs a
merge, and every contract keeps `mark = 0.0`. Then:

- `options_chain.py:299` — `candidates = [c for c in contracts if c.mark > 0.05]` → **empty**
- `options_chain.py:327` — sweep delta-band: `c.mark > 0.05 and 0 < |delta| ≤ 0.55` → **empty** (delta is also 0)
- `:353/:356` — condor legs: `c.mark > 0` → **empty**

So in **every** regime, every strategy's strike selection returned nothing and
`generate_signal` returned None — a perfectly plausible-looking "no setup" day.
Butterflies were additionally dead at the GEX gate (no gamma → no PINNING). Spot~$0
is cosmetic fallout (`spot_price` comes from the ATM-call scan at `:165`, which needs
deltas).

**Why this correction matters:** when validating the fix, the green signal is
**marks > 0 and a successful strike selection log**, not regime labels. Watching
regimes would pass/fail for the wrong reasons.

---

##### 3 · Problem C (the four crash-loopers) — explained, no new work needed

AAPL/NFLX/TSLA (17 restarts), GLD (14), blank regime, `sess_errs = 0`. The math
identifies the cause: the loop's error breaker exits the process at **30 errors**, one
per 15 s tick = **7.5 min per death cycle** (+ restart delay). RTH 9:30 → sweep at
~11:45 is 135 min ≈ **17–18 cycles. The table says 17 and 14.** That is the
poison-candle kill loop (`fetch_quote` → year-2038 row wins "latest", `close=0.0` →
`ValueError` in `run_analysis`) — which fires **before** the GEX fetch in the tick,
which is exactly why those four boxes show `sess_errs = 0` and blank regime.

Hypothesis for why only these four of 28 poison-carrying boxes crash-loop: their
poison row landed in the **1m** table (the one `fetch_quote` reads); the other boxes'
poison sits in other timeframes. One-line verification per box:
`sqlite3 ~/options-trader/data/feed_store.db "SELECT tf, COUNT(*) FROM candles WHERE ts > 2000000000000 GROUP BY tf"`
— expect `1m` rows on exactly AAPL/NFLX/TSLA/GLD.

**Remedy: the already-shipped candle_feed v3.2/v3.3 + `purge_poison()`** (running on
GOOGL). These four need the fleet bake, nothing new. Do not build anything for C.

---

##### 4 · Solutions, with tradeoffs

**Option 2 (centralize chain on control) — REJECT.** Single point of failure for 29
deliberately-independent bots, and 1-REPORTER is credential-free by design
(`validate_regime.sh`: "no credentials, no live path"). Breaking that isolation to
dodge a session cap is trading a transport problem for an architecture regression.
Keep in the drawer only if the cap proves brutally low (<40).

**Option 3 (REST for Greeks/marks) — REJECT as primary, keep as backstop.** Marks via
REST exist (the `fetch_quote` fallback already uses it). Greeks via REST: could not
confirm availability; moot under the recommendation below. REST polling for 110
strikes per box per tick would just move the throttling problem to the REST rate
limiter.

**Option 4 (throttle chain fetches) — necessary hygiene, insufficient alone.** The
chain *structure* is static intraday and never needed re-fetching every 15 s. But
while HOLDING a position the exit engine prices premiums off chain marks every tick —
throttling stales the exact data the −25% floor and trails read. Any throttle must be
state-aware (flat: slow; in-position: fast), at which point in-position churn returns.
Component, not solution.

**Option 1 (persistent per-box chain streamer) — the RIGHT SHIP-TONIGHT FIX.** One
long-lived `DXLinkStreamer` inside `options_chain`, opened lazily on first use,
subscriptions updated (subscribe new strikes / unsubscribe stale) instead of
reconnecting, reconnect-with-backoff on error. Steady state: **58 persistent sessions
(2/box), zero churn.** Risk: the cap is unknown — 58 could still sit above it. But the
evidence is on our side: last week ran 29 persistent + heavy churn without errors, so
the cap comfortably exceeds 29 + churn-overlap; 58 clean sessions is *less* demand
than that. Smallest change, contained in one file, per-box isolation untouched,
provable on one box in minutes.

**Option 1b (consolidate Greeks/Quote into candle-feed) — the RIGHT DESTINATION.**
The handoff names the gap itself: v3.0 consolidated **candles only**. Doctrine says
one producer, many readers — finish it: candle-feed subscribes Greeks+Quote for the
box's chain symbols on its **existing** socket, writes them to the store;
`options_chain` becomes a pure store reader like `market_data`. **29 total sessions —
the number proven safe for weeks.** Cost: bigger build — a desired-symbols handshake
(options_chain writes the strike list to a store table; the feed reconciles
subscriptions each flush cycle), a greeks/quotes schema, staleness semantics, and
`verify_feed_v3.sh` extensions. Touches the most protected file on the box.

##### Recommendation

**Ship Option 1 now, schedule 1b as the v3 completion.** Tonight's goal is trading
tomorrow with zero churn and minimal blast radius; that is Option 1 in one file
(`options_chain.py`), testable on QQQ-TEST against live DXLink before any fleet
motion. 1b is the architecturally correct end state but touches candle_feed — the one
component that worked flawlessly today — and deserves an unhurried build + the
verify-feed acceptance gate, not a market-holiday-eve rush. If you want, 1 → 1b
becomes invisible later: consumers never see the transport.

Add one cheap piece of Option 4 to Option 1 regardless: rebuild the chain
*structure* (REST strike list) at most every N minutes; the persistent stream keeps
Greeks/marks per-tick fresh continuously. And one **fail-loud guard** (today's real
lesson): if a built chain has zero contracts with `mark > 0`, log ERROR and return
`None` instead of a plausible-looking dead chain — `attempt_new_entry` already
handles a None chain correctly. Silent structural validity with dead values is what
hid this for five hours.

---

##### 5 · Re-arm sequence (proposed — no action taken)

1. Fleet stays STOPPED (bots). Candle-feeds keep running — they are innocent and
   their sessions are stable.
2. Let the pool drain ≥ 15 min from the last bot stop (covers any lingering timeout
   windows several times over).
3. I build Option 1 (+ zero-mark fail-loud + structure-refresh throttle) as a
   complete `options_chain.py`, versioned, with an offline test + a live single-box
   acceptance script.
4. Prove on QQQ-TEST during RTH: `sess_errs = 0` over 30+ min, marks > 0, one
   successful strike-selection log, `ss -tn | grep -c :443` shows exactly 2
   persistent connections.
5. Bake fleet-wide **together with the already-shipped v3.1–v3.3 + butterfly fix**
   (28 boxes are still on `818d312` and carry the poison landmine + the four
   crash-loopers).
6. Restart the fleet staged — 5 boxes, watch 10 min, then the rest — so if 58
   sessions does brush the cap, it shows up at +10, not +29.

**Awaiting your go on Option 1 before writing any code.**

---


<!-- ================= was: docs/HANDOFF_dxlink_fix_state.md ================= -->

##### HANDOFF — DXLink session-exhaustion fix — state as of 2026-07-13 (night)

**Purpose: resume-from-here document.** If this thread dies, give this file (plus
`DIAGNOSIS_session_exhaustion_2026-07-13.md`) to the next session. Diagnosis SETTLED,
**cap MEASURED, Option 1b BUILT and offline-verified 11/11.** What remains is
deployment. Do not re-derive §1–§3.

---

##### 1 · Incident + diagnosis (settled — do not re-diagnose)

2026-07-13: zero trades fleet-wide. Confirmed root cause: `options_chain.py` opened a
new DXLinkStreamer per 15 s tick per box (each open = fresh REST token + full WS
lifecycle); ~24 boxes' churn saturated TastyTrade's session pool. No client-side leak
(SDK 13.0.0 teardown verified clean); server-side 60 s keepalive windows × redial
cadence. **Kill mechanism (corrected):** regime never degraded — empty quote maps →
`mark=0.0` → the `mark > 0.05` liquidity filters rejected every strike in every
regime. Validate with marks + strike selection, never regime labels.

**Problem C** (AAPL/NFLX/TSLA/GLD crash loops, 17/17/17/14 restarts): poison candle
in the 1m table → `fetch_quote` ValueError → 30-error breaker → 7.5-min death cycles
(135 RTH min ≈ 17 ✓). Healed automatically by candle_feed ≥ v3.2 `purge_poison()` in
the fleet bake. No new work.

##### 2 · The cap was MEASURED — this drove the design

**Option 1** (persistent streamer per box, `options_chain` v3.1) was built, verified,
and fleet-tested 07-13 afternoon. Result: with 29 candle-feeds holding sessions, only
**~6–11 of 29 chain streamers were ever admitted** (AMZN/CRM/DIA/LLY/MU/SMH stable;
AAPL/GS/PLTR/TLT/XOM connected-then-died; 16 locked out in backoff all afternoon).
**Empirical concurrent-session cap ≈ 40–45.** Option 1's 58 steady-state sessions do
not fit. v3.1 behaved perfectly within itself — backoff held retries at the 60 s cap
(~25 errs/30 min vs ~120 before), fail-loud refused every corpse chain — it is simply
arithmetic-blocked. **Jason green-lit Option 1b.**

##### 3 · What is BUILT and VERIFIED (deploy these two files together)

**`data/candle_feed.py` v3.4** — chain marks on the feed's EXISTING socket:
- New store tables: `chain_subs` (single row: expiry + JSON symbol list, written by
  the bot) and `chain_marks` (latest bid/ask/greeks per streamer symbol, written by
  the feed; quote and greeks upserts each preserve the other's columns).
- `_reconcile_chain_subs()` every 2 s flush cycle: subscribes deltas; expiry rollover
  → `unsubscribe_all(Greeks/Quote)` + clear marks table + resubscribe. Socket
  reconnect resets chain state and re-reconciles (same path as candle resubscribe).
- Greeks/Quote events drain non-blocking each loop pass; marks ride the existing
  flush. **Candle logic byte-untouched** (verified by diff: only the import line and
  version banner changed).

**`data/options_chain.py` v3.2** — pure store reader; **the bot process now opens
ZERO DXLink connections** (import removed; `main.py` imports clean on 3.12 AND 3.14 —
and yes, removing the import initially reproduced the exact P0-1 annotation bug from
the 07-12 audit; caught by the 3.12 test discipline, annotations fixed):
- Publishes desired symbols+expiry to `chain_subs` (only on change); reads
  `chain_marks` with the staleness ceiling (`OT_CHAIN_STALE_S=120` — stale marks are
  refused, never served).
- Kept from v3.1: structure cache (`OT_CHAIN_STRUCT_REFRESH_S=1800`), zero-mark
  FAIL-LOUD — now **bootstrap-aware** (`OT_CHAIN_BOOTSTRAP_S=30`: quiet INFO while
  the feed populates after a fresh subscribe; ERROR after).
- Old feed on the box (≤v3.3) → helpful error: "is candle_feed v3.4 running?".

**Fleet steady state: exactly 29 DXLink sessions (one per box, the feed's).**
Verified offline 11/11 end-to-end (real FeedStore + real CandleFeed machinery driven
by a fake streamer + real reader): subs publish → feed subscribe (both types, exact
set) → events → flush → marks rows → chain built with correct mark/greeks →
steady-state reconcile subscribes nothing → expiry rollover unsubscribes+clears →
stale refusal → missing-table hint. Plus ORB 10/10, contract 17/17, theta 7/7.

##### 4 · Fleet state right now

- 29 `optionsbot` units STOPPED (some may have been restarted for the v3.1 test —
  re-stop before baking). `candle-feed` units RUNNING everywhere (v3.3-era on 28
  boxes, whatever GOOGL has).
- Repo `origin/main` has everything through options_chain **v3.1**; v3.4 feed +
  v3.2 chain are in this session's outputs, NOT yet pushed.

##### 5 · REMAINING STEPS

1. **Push BOTH files** to `github.com/TX-9AI/options_trader_v3` → `data/` folder:
   `candle_feed.py` (v3.4) + `options_chain.py` (v3.2). They ship as a pair — v3.2
   bot with v3.3 feed fails loud (safe, but trades nothing).
2. **Prove on ONE box** (any; QQQ-TEST fine). Single line:
   `cd ~/options-trader && git pull --ff-only && sudo systemctl restart candle-feed && sleep 5 && sudo systemctl restart optionsbot`
   (feed restart is safe: `subscribe_candle` backfills from the session start on
   reconnect). Acceptance after ~10 min RTH:
   - `journalctl -u optionsbot --since "-10 min" | grep -m1 "Chain subs published"` → once
   - `journalctl -u candle-feed --since "-10 min" | grep -m1 "chain marks: subscribed"` → present
   - `journalctl -u optionsbot --since "-10 min" | grep "Chain built" | tail -2` → real spot, real counts
   - `journalctl -u optionsbot --since "-10 min" | grep -c "exceeded the configured limit"` → 0
   - `ss -tn state established '( dport = :443 )' | tail -n +2 | wc -l` → ~1–3, flat
3. **Fleet bake** (devtools 25 RTH-safe / 23 after-hours) — rides with everything
   the 28 boxes still lack from 07-12/07-13. Then restart candle-feed AND optionsbot
   on all (feed restart is required for v3.4 tables/subscriptions):
   `python3 fleet.py run "cd ~/options-trader && sudo systemctl restart candle-feed && sleep 5 && sudo systemctl restart optionsbot"`
4. **Staged**: 5 boxes → 10 min watch (same acceptance) → remaining 24. Expected
   total account sessions: 29. Headroom vs measured cap: ~11–16.
5. After first clean session: exit_reason labels sane (F5 newly fleet-wide), replay
   diary L2 tracks flowing (devtools 40).

##### 6 · Open threads (not blocking re-arm)

- **`verify_feed_v3.sh`** — not yet extended for chain_marks/chain_subs checks;
  worth one section once the fleet is stable (freshness + row counts).
- **`options_chain` v3.1** — superseded same-day by v3.2; its header records both.
  If anyone finds v3.1 running anywhere, it is safe (backoff + fail-loud) but
  session-hungry — upgrade it.
- **Problem C verification** — run the sqlite one-liner on AAPL/NFLX/TSLA/GLD to
  confirm the 1m-table hypothesis (curiosity only; the fix ships regardless).
- **`observer/` tarballs** (defect D) — still ungreppable; confirmed nothing in the
  importable tree opens a third DXLink stream, but the tarballs remain unaudited.
- **Session cap** — unpublished (searched dev docs/SDKs/help center). Design margin,
  not knowledge: 29 proven safe for weeks, 58 almost certainly fine, churn never again.
- The full 07-12 audit findings register (F4 named-levels starvation, F27 condor
  Leg-2 gates, etc.) lives in `AUDIT_options_trader_v3_2026-07-12.md` — untouched by
  this incident.

##### 7 · Standing constraints (unchanged)

Complete files only, never patches · version header bumped on every change · clone
repo + read HEAD before writing · single-line commands for mobile · PAPER_TRADING
default True · trading/risk/strategy logic untouched (this was transport-only) ·
one box proves it before the fleet.

---


<!-- ================= was: docs/AUDIT_paper_live_divergence_2026-07-15.md ================= -->

##### AUDIT — Paper→Live behavioral divergence · 2026-07-15

**Scope:** every `paper_trading` / `PAPER_TRADING` / `paper_trade` branch in the
repo, plus every live order-placement and P&L-booking path, audited for
behavior that changes — or breaks — when `OT_PAPER_TRADING` flips to `False`.
Prompted by the 15:45 hard-close `$0.00` booking bug (fixed in exit_engine
v3.4/v3.5): the question was *what else is of that species*.

**Verdict in one line:** the EXIT side is now fill-confirmed and safe (v3.5),
the reconcile side recovers truth (v3.6) — but the **ENTRY side has the same
submission-equals-fill disease**, the **broken-wing roll opens a fictional
position in live**, and **paper and live rows share one trades.db with no mode
filter**, so two weeks of paper history will contaminate the live daily-loss
breaker on day one.

Files audited: `main.py`, `execution/entry_engine.py`, `execution/exit_engine.py`,
`execution/position_manager.py`, `execution/broker_reconcile.py`,
`strategy/condor_roll.py`, `database/trade_logger.py`, `risk/risk_manager.py`,
`risk/session_guard.py`, `data/tasty_client.py`, `notifications/alert_manager.py`,
`status.py`, `eod_summary.py`, `query.py`, `config.py`, `configure.sh`.

---

##### 🔴 CRITICAL — will misbehave or lose position-truth in live

##### L1 — Entries book on SUBMISSION, not on broker fill (all three entry paths)

The entry side never got the FillResult treatment. Every live entry path
records the position as open — at a price that is not the fill — the moment
the order is *accepted*, exactly the class of bug that produced the $0.00
exits.

**L1a · Condor legs** (`main._execute_condor_leg`): places the 2-leg vertical
as a LIMIT at mid-credit, then books
`fill_credit = response.order.price or net_credit` immediately. `.price` on a
just-placed order is the *limit you asked for*, not a fill, and a mid-credit
limit is precisely the kind of order that sits unfilled. Consequences of a
never-filled entry: a DB position that does not exist at the broker, managed
every tick, "closed" at 15:45 with real close orders the broker rejects, and
`notify_leg_filled()` advances the condor legging state machine on a fill that
never happened — Leg 2 can arm off a fictional Leg 1.

**L1b · Single legs** (`entry_engine._place_single_leg`): MARKET order, then
`fill_price = float(placed.price or signal.entry_premium)`. A market order has
no `.price`, so this **always** books the signal-time mark as the entry — the
recorded entry premium in live is never the actual fill. Stops/targets and P&L
all key off a number the broker never printed. (Market orders nearly always
fill, so position existence is usually fine — the *price* is what's wrong.)

**L1c · Butterfly** (`entry_engine._place_butterfly`) — broken three ways:
1. **Wrong price sign.** The debit is sent as a POSITIVE `price` with
   `price_effect=DEBIT`. Verified against the SDK (v8+ through 13.x):
   `NewOrder.price` is **signed** (negative=debit, positive=credit) and
   `price_effect` is silently ignored. A positive-priced opening fly demands a
   *credit* to buy a debit spread — it will never fill.
2. **Fill check that can't succeed.** It reads `placed.status` immediately
   after submission, looking for "Filled" — the status at that instant is
   Received/Routed. So even a correctly priced order goes: place → sleep →
   cancel → re-place → cancel → give up.
3. **Double-position race.** If the first order fills during the sleep, the
   `delete_order` fails (exception swallowed with `pass`) and attempt 2 places
   a **second** butterfly.

**Fix shape:** an entry-side mirror of exit_engine v3.5 —
`_confirm_entry_fill(order_id)` polling to a bounded deadline, record written
ONLY on a confirmed fill at the broker's per-leg net fill price, signed limit
prices, cancel-and-resolve on timeout. Until then the deliberate "entry logic
is v2.5" stance in the README should be read as **live entries are not
validated**.

##### L2 — Broken-wing roll opens a FICTIONAL vertical in live

`strategy/condor_roll._execute_roll` step 2 carries the comment "*live order
placement mirrors _execute_condor_leg*" — **but no order is placed**. The code
writes the rolled vertical's DB record and moves on. In live: the real
untested vertical is closed (correctly, fill-confirmed via v3.5), then the bot
books and "manages" a new vertical that was never opened at the broker. The
rolled structure's risk-free math is fiction; reconcile will eventually flag
the ghost. Secondary: step 1 books the close at `plan.close_cost` instead of
the confirmed `fill.fill_price` it *just received* from the v3.5 close.

**Fix shape:** place the rolled vertical as a real signed-credit limit order
with fill confirmation before writing the record; book step 1 at
`fill.fill_price`. Alternatively gate `check_and_execute_roll` behind
`paper_trading` until built — a silent no-roll is strictly safer live than a
ghost position.

##### L3 — One trades.db, no mode filter: paper history contaminates live truth

There is **no `paper_trade` filter** in the queries that matter:

- `realized_pnl_today()` — **the DAILY_LOSS_LIMIT source of truth** — sums
  every closed row. On switch day, two weeks of paper habits plus any paper
  rows closed that ET day gate the *live* breaker. A red paper morning can
  halt real-money entries; a green one can mask a real-money halt.
- `get_open_trades()` / `get_open_trades_live()` — startup recovery and the
  position manager hand any still-open paper rows (unexpired weeklies, or
  rows with unknown expiry, which are deliberately kept) to the LIVE bot,
  which manages them, submits real close orders for them, collects broker
  rejects and pages until reconcile phantoms them — and the phantom booking
  then *also* lands in live realized P&L.
- The only DB wipe in the system is on **instrument** change, paper mode only.
  **Mode** change wipes nothing and archives nothing.

**Fix shape (small, do first):** mode-aware queries — filter
`paper_trade = (0 if live else 1)` in `get_open_trades` and
`_closed_today_rows` — plus a `configure.sh` step on switching to LIVE that
archives `trades.db → trades_paper_YYYY-MM-DD.db` (preserving the two weeks of
paper data rather than mixing or deleting it).

---

##### 🟡 MODERATE — expectation and hygiene

##### M1 — Paper fills are perfect; live fills are not
`PAPER_FILL_SLIPPAGE_PCT = 0.0`: paper enters AND exits at the exact
mid/mark, both sides, every time. Live pays spread crossing on entry, and the
v3.5 close buys through the mark by `LIVE_CLOSE_LIMIT_BUFFER` to get filled.
Two weeks of paper P&L is therefore a structurally *optimistic* estimate —
materially so on wide SPX spreads. Not a bug; a calibration warning. Consider
a nonzero paper slippage (even 1–2%) so paper stats stop flattering.

##### M2 — Dashboards report mixed modes
`status.py`, `eod_summary.py`, and the risk manager's session stats aggregate
paper and live rows together (`query.py` at least prints the flag per trade).
After L3's filter lands this mostly resolves itself; until then, switch-day
dashboards lie.

##### M3 — Live-only code paths have never executed
`get_open_option_positions()` is written version-robustly (sync on tastytrade
12.x, coroutine on 13.x) but its field access has only been verified against
SDK source, never a live account — same for every live order path. Reconcile
now auto-enables with LIVE (v3.6/config v1.8), which makes the tiny-account
shakedown *more* important, not less: first live session should be 1 contract,
minimal width, watching `journalctl` and Telegram.

---

##### ✅ VERIFIED SAFE across the switch (so you don't re-audit them)

- **Exits** — fill-confirmed (v3.5): submit → bounded poll → book only on the
  broker's net fill; partials weighted; idempotent resume; verticals close as
  2-leg spread orders with signed debit limits; butterfly closes are
  marketable limits. Acceptance tests A–E pass.
- **15:45→16:00 flatten retry + paging** — mode-agnostic, books only via
  `_execute_exit`, which refuses unconfirmed fills.
- **Reconcile (v3.6)** — auto-follows mode; interval sweeps
  (`BROKER_RECONCILE_INTERVAL_MIN`, default 10) plus 15:45/15:50/15:57
  wind-down passes; phantom P&L recovered from order history; fail-safe on
  bad/empty broker reads; paper never reconciles.
- **DAILY_LOSS_LIMIT mechanics** — DB-seeded, restart-proof, net-based
  (content is compromised by L3 until filtered, but the mechanism is sound).
- **Regime/conviction/session gates, candle feed, sizing** — mode-agnostic by
  construction; single TastyTrade/DXFeed feed serves both modes identically.

---

##### Recommended order of work before cash

1. **L3** — mode-filter the two queries + archive-on-switch in configure.sh.
   Smallest change, prevents day-one contamination no matter what else ships.
2. **L1** — entry-side fill confirmation (mirror of exit v3.5). Condor legs
   first (the strategy you actually run), then single-leg price readback, then
   butterfly (or gate butterflies off in live until rebuilt).
3. **L2** — real order in the roll, or gate the roll to paper.
4. **M1** — nonzero paper slippage so the next two weeks of paper predict live.
5. Tiny-account live shakedown (1 contract) with reconcile auto-on, per the
   v3.5 spec's acceptance criteria.

---


<!-- ================= was: docs/AUDIT_header_compliance_2026-07-23.md ================= -->

##### AUDIT — Header/Changelog Compliance + Stale-Reference Sweep — 2026-07-23

Scope: full clone of `options_trader_v3` at HEAD `5740a05`. Every .py/.sh/.md read;
title-vs-newest-changelog verified per the standing convention (title line == newest
dated entry). All fixes are doc/comment-only **except one real bug** (§3).
Post-fix: `check_versions.sh` **0 red / 89 green**, test suite **37/37 pass**.

##### 1. Mis-numbered / duplicate changelog entries (relabeled, titles synced)

| File | Was | Now | Why |
|---|---|---|---|
| `risk/risk_manager.py` | `v1.4 — 2026-07-23` (full-budget condor sizing) | **v3.2** (+ v3.3, see §3) | File was already at v3.1; v1.4 was non-monotonic and duplicated the 2026-07-02 v1.4 |
| `strategy/butterfly_strategy.py` | `v1.4 — 2026-07-14` (discount gate); title v3.0 | **v3.2**, title v3.2 | v3.1 (07-12) already existed |
| `status.py` | second `v1.12 — 2026-07-20` | **v1.13**, title v1.13 | Duplicated the 2026-07-06 v1.12; in-code `# v1.12 fix` comments re-pointed |

##### 2. Stale title lines synced (no new version — matches the 07-16 precedent)

`analysis/trend_engine.py` → v3.2 · `analysis/structure_analyzer.py` → v3.0 ·
`data/market_data.py` v3.0 → v3.2 · `database/trade_logger.py` → v3.8 ·
`configure.sh` "v1.5" banner → v2.0 · `validate_regime.sh` v2.0 → **v2.2** (new entry:
removed two retired `data/harvest` paths from its Data block — the layout that
`migrate_data_layout.sh` deliberately rmdir'd) · `snapshot.sh` duplicate v1.1 line deduped.

##### 3. REAL BUG found and fixed — `risk_manager` v3.3

The 07-23 full-budget change renamed the sizing variable but left the **success-path
`logger.info` f-string referencing the deleted old name** → `NameError` on **every
condor-leg sizing that produces ≥1 contract** at fleet risk levels. Reproduced
(`spread_width=5.0, credit=0.50, risk=$1050` → NameError), fixed, re-verified
(B: 2 contracts, A: 3 contracts, clean log). The `check_versions` absence canary was
**legitimately RED at HEAD** on exactly this and the deploy shipped anyway — the
canary works; the pre-push gate of "run it and read the reds" is the part that slipped.
Lesson also encoded: changelog **prose** that names a canary-absence-checked token
re-trips the canary (same trap the `_orb_quality` comment already documents).

##### 4. `check_versions.sh` → v3.7

Label-correction sweep entry + prose refs updated ("risk v1.4"→v3.2, "status v1.12"→
v1.13, line-173 canary description). Fingerprints (code greps) unchanged.

##### 5. README.md — manifest re-synced + discarded-process references corrected

- Manifest rows: `main` v4.0→**v4.2** (chain archival), `config` "v3.3 stale"→**v3.9
  current**, `exit_engine` "v3.8 un-bumped"→**v4.1** (condor v2 + continuation rework),
  `entry_engine` →v3.9, `position_manager` →v3.9, `limit_ladder` →v1.3,
  `condor_roll` →v3.8, `risk_manager` →v3.3, `butterfly` →v3.2, `status` →v1.13,
  `trend_engine` +v3.2, `market_data` +v3.2.
- **Condor section**: "half the grade budget" (retired 07-23 → full budget), "pending
  leg is cancelled" (retired → **pauses**, iron_condor v3.2), per-leg exits updated to
  the v4.1 ratchet + time-gated TP.
- **Continuation exit table**: −40% floor → **−25% `CONTINUATION_STOP_LOSS_PCT`**;
  theta-bleed row added (v4.0 enabled it); trail now 5m-FVG-anchored.
- **Shadow section**: timers `shadow-start`/`shadow-stop` marked **RETIRED 2026-07-22**
  (edge-trigger fired while boxes were stopped overnight); enable-at-boot noted;
  **fleet-wide (29-box)** rollout supersedes "QQQ box only".
- **`validate_regime.sh` row**: "executing copy lives at `~/validate_regime.sh`, sync
  manually" **deleted** — contradicted the 07-23 repoint (repo copy is canonical);
  devtools wrapper numbers corrected **40–44 → 42–46** (v1.18 renumber).
- Defect U: dated resolution note appended.

##### 6. `docs/EXIT_RULES.md` — was frozen at exit_engine v3.8 (2026-07-15)

Now synced to **v4.1**: universal hard close reflects the 15:40 mark-limit → 15:45
MARKET escalation; condor section carries the ratcheting stop + time-gated TP@25% and
the leg-2 **pause** (was "cancelled"); a full **Trend Continuation** section added
(it had none — the strategy postdated the doc); summary corrected to six strategies /
four hard TPs (with the sweep +100% default-replacement noted).

##### 7. `shadow_devtools.sh` → v1.2

Timer status/banner items now label `shadow-start`/`shadow-stop` **RETIRED
(disabled = healthy)** so the menu can never read as "broken timers, go fix them."

##### 8. Flagged, not changed (your call)

- **`tests/validate_regime.sh` is a byte-identical duplicate of the root copy**
  (nothing references it — zero hits repo-wide). Per your loose-files principle it
  should be deleted; I synced it identically for now so it can't drift ahead, but one
  canonical copy is the right end state.
- `tests/a2_cooccurrence.py` / `ramp_calibration.py` keep read-only `data/harvest`
  **fallback globs explicitly marked legacy** — harmless (they read nothing there now);
  left in place. `tests/regime_diary.py`'s usage example still shows `--harvest
  .../data/harvest` in a docstring; low-priority.
- Defect Z (`fleet_trades` cross-date contamination) remains OPEN per the README.

---


<!-- ================= was: docs/FABLE_SPEC_live_exit_fill_confirmation.md ================= -->

##### FABLE SPEC — Live exit fill-confirmation (`_confirm_and_book_live_exit`)

**Repo:** `github.com/TX-9AI/options_trader_v3` · **Owner of this file after build:** Fable
**Status:** paper side is DONE and deployed; this is the LIVE half only.
**Hard rule:** do not touch the paper path or the shared contract below — build only
the live method. One owner per file: you own `_confirm_and_book_live_exit` and the
broker-polling helpers; the seam it plugs into is fixed.

---

##### The one-sentence problem

When the bot closes a position in **live/cash** mode, it must book P&L **only after the
broker confirms the fill, at the broker's actual fill price** — never at a mark, never at
entry, never a fabricated `$0.00`, and an unconfirmed close must remain an **open
position**, not a booked row.

##### Why this exists (the bug that motivated it)

On 2026-07-15 the 15:45 hard-close flattened ~8 condor legs and logged **every one at
`pnl=+$0.00`**. Root cause: `flatten_all` booked P&L on order *submission success*, at a
fallback price (entry premium), with **no fill confirmation**. In paper that's a
reconcilable bookkeeping error. In live it is a position-truth catastrophe: the DB says
flat, the broker may not be, P&L is fiction, and the `DAILY_LOSS_LIMIT` circuit breaker
(which halts on realized P&L) is now reading fabricated numbers. This spec closes that
hole for live trading.

##### What is already done (do not redo, do not change)

`execution/exit_engine.py` v3.4 and `execution/position_manager.py` v3.4 now use a shared
result contract. **This is the seam. It is fixed. Build to it.**

```python
@dataclass
class FillResult:
    confirmed:  bool                      # True ONLY on a real, completed close
    fill_price: Optional[float] = None    # ACTUAL close price; None iff not confirmed
    order_id:   Optional[str]   = None    # broker order id (live)
    partial:    bool            = False   # partially filled, remainder still working
    detail:     str             = ""      # human-readable status for logs/alerts
```

- `place_exit_order(record, reason, mark_price=None) -> FillResult`
  - **PAPER (built, frozen):** simulates the fill at `mark_price`, returns
    `FillResult(confirmed=True, fill_price=mark_price)`. One pass — a simulated close
    always succeeds; no polling, no retry, no reuse.
  - **LIVE (your job):** calls `self._confirm_and_book_live_exit(record, reason, mark_price)`.
- `_execute_exit` (position_manager) books **only** when `fill.confirmed and fill.fill_price
  is not None`, using `fill.fill_price`. On `confirmed=False` it books nothing and returns
  `False`, and `flatten_all` retries every tick 15:45→16:00 and escalates. **You do not need
  to touch any of this** — return a correct `FillResult` and the accounting is handled.
- `_submit_live_close(record) -> bool` already exists: it submits the SELL_TO_CLOSE / spread
  order via the tastytrade SDK and returns submit success. **Submission is not a fill** — it
  is provided for you to call as step 1, nothing more.
- Current live stub raises `NotImplementedError` on purpose, so cash cannot be enabled until
  you ship this. That is the safety property; preserve it until the real thing is proven.

##### What you must build

Implement `ExitEngine._confirm_and_book_live_exit(self, record, reason, mark_price) ->
FillResult` with this contract:

1. **Submit** the close (use `_submit_live_close(record)` or inline equivalent) and **capture
   the broker order id.** If submission fails → `FillResult(confirmed=False,
   detail="submit failed")`.
2. **Poll** broker order status for that order id on a **bounded** loop:
   - poll interval and total deadline configurable (propose `LIVE_FILL_POLL_SECONDS` and
     `LIVE_FILL_DEADLINE_SECONDS` in `config.py`; sensible defaults e.g. 2s / 30s);
   - terminal states: `filled`, `partially_filled`, `rejected`, `cancelled`, `expired`;
   - respect API rate limits (this runs during the session-limited window).
3. **Book only on a confirmed FULL fill:** return `FillResult(confirmed=True,
   fill_price=<broker fill price>, order_id=...)`. The fill price is the broker's, read back
   from the filled order — **not** `mark_price`, which is context only.
4. **Partial fills:** either (a) track the remainder to completion and return the
   quantity-weighted average fill price once fully closed, or (b) return
   `FillResult(confirmed=False, partial=True, detail=...)` and let the caller retry — pick
   one and document it. Never book a partial as if it were whole.
5. **Not filled by deadline / rejected / error:** return `FillResult(confirmed=False,
   detail=<why>)`. The position **stays open**; the 15:45→16:00 retry loop will re-attempt
   and page. Never fabricate a price, never mark closed.
6. **Spreads (condor legs):** a leg is a two-legged vertical. Confirm the **spread** closed
   (both legs), and return the **net** spread fill price on the same credit basis the P&L
   math expects (`_execute_exit` computes `entry_prem - fill_price` for credit-signed
   positions — so `fill_price` must be the net spread value, matching how the paper mark is
   `short_mark - long_mark`).

##### Acceptance tests (must pass before cash)

- **A — happy path:** submitted → filled → `FillResult(confirmed=True)` with the broker fill
  price; DB row closes; P&L matches `(entry - fill) * contracts * 100` for a credit spread.
- **B — the orphan test (the whole point):** submit an order that does **not** fill by the
  deadline → `confirmed=False`, **P&L booked = none**, DB row **still open**, alert fired.
  A submitted-but-unfilled order must **never** produce a `$0.00` (or any) booked close.
- **C — reject:** broker rejects → `confirmed=False`, position open, no booking.
- **D — partial:** partial then complete → single correct net fill price; or documented
  retry. Never books the partial as whole.
- **E — paper untouched:** `PAPER_TRADING=True` still books the simulated mark in one pass;
  no polling path entered.

##### What you'll need from Jason

- Live tastytrade **API credentials** for a funded but **tiny** account (test with 1
  contract / minimal width). Jason has offered these — request them for the test account,
  not production size.
- Confirmation of the tastytrade SDK's order-status object shape (fields for state, filled
  quantity, average fill price) — verify against the live SDK, do not assume.

##### Guardrails

- Complete files, never patches; bump the header of every file you change with what changed.
- Clone repo HEAD and read before editing — this file's paper seam is v3.4; build on it.
- Do not weaken the fail-loud stub until the acceptance tests pass; a half-built live path
  must still refuse to book rather than book an orphan.
- `PAPER_TRADING` default stays `True`. Nothing you build may change paper behavior.

---



---

## APPENDIX — migrated from the root README (2026-07-28)

These sections described shipped work and rollout state that had gone stale in
the README. Preserved here verbatim.

<!-- ================= was: README.md § READ THIS FIRST — entry logic v2.5 ================= -->

## ⚠️ READ THIS FIRST — the entry logic is v2.5, and that is deliberate

The regime architecture is mid-migration. Three eras coexist in this tree, and the honest
label for what is *running today* is neither v2 nor v3:

| | Gating model | Result |
|---|---|---|
| **v1** | Boolean gates, permissive | Fired into hostile tape. Sold into uptrends. Got faked out. |
| **v2** | Boolean gates + an `UNKNOWN` regime with **hard veto** | Over-corrected. Most of RTH classified `UNKNOWN`; the veto skipped clean trending setups; **the trade sample starved the very analysis loop meant to fix it.** |
| **v2.5** (to 2026-07-21) | v2's cascade, but `UNKNOWN`'s **veto power removed for the ORB** | Sample restored. The safety was removed before the replacement was built. |
| **v3-label — RUNNING NOW** (landed main.py v4.0, 2026-07-21; `main.py` now v4.2) | **L1 confluence → L2 conviction integrator's committed label** drives `primary_regime`. `UNKNOWN` is gone from live emission (indecision = a low conviction number on a best-fit label). **The conviction NUMBER is still observe-only — gates run wide open.** | The v3 *label* machinery is live; the v3 *bars* (L3) are not. Rollback: `OT_REGIME_ENGINE=v13`. |
| **v3 — TARGET** | Weighted confluence → per-regime conviction → `fires iff regime ∈ permissive AND C ≥ bar(trade_type)` | Bars placed empirically at the marginal fee-adjusted-ROI zero crossing. |

**State it plainly (updated 2026-07-22):** the regime *label* is now the v3 spine (L1→L2, see
§Regime engine), but the conviction number still gates nothing — so the honest label for the
*entry gating* remains v2.5. v3.2 shipped ROADMAP **Phase 2's permissive set** for the ORB
(`_orb_ok_regimes` in `main.py` is the ROADMAP Phase-2 table verbatim, plus `UNKNOWN` and
`SWEEP_REVERSAL` under the switch) **without Phase 2's conviction bar.** The gate opened; the
thing meant to replace it has not landed.

Consequently, **a confirmed ORB break+retest fires in every regime the classifier can emit,
including `UNKNOWN`.** The only thing between a confirmed setup and an order is
`setup_scorer`'s B-threshold (0.55), inside which `regime_conviction` is a 20%-weighted
dimension that contributes **exactly 0.0 under `UNKNOWN`**.

This is intentional — it is how labeled tape gets generated for the Phase-3 calibration.
**It is also why the fleet stays in paper.** `PAPER_TRADING` defaults to `True` and must not
be flipped on any box until the conviction bars exist. See `ROADMAP.md` §Risks.

Sweep, butterfly, condor, and trend continuation are **untouched** by this: they still
self-gate and still do not fire under `UNKNOWN` (continuation hard-requires a *trending*
regime, a strictly higher bar). Set `ORB_FIRES_REGARDLESS_OF_REGIME = False` to restore strict
v2 gating.

---

---

<!-- ================= was: README.md § DAY-ZERO ROLLOUT — 2026-07-18 build ================= -->

## 📦 DAY-ZERO ROLLOUT — 2026-07-18 build (deploy state)

> **SINCE DAY ZERO (2026-07-20 → 07-22) — everything below in this section is now historical; these landed after it:**
> - **2026-07-20:** `orb_engine` **v3.9** — stale-retest timeout restored *correctly*: real 1m bars (deduped on candle ts, break candle excluded, fires on the 13th post-break bar), and expiry **re-arms** instead of terminating (the SMH missed-short fix; the old timeout counted 15-s loop ticks as bars and died in ~3 min). `status.py` **v1.12** — daily-loss banner reads the limit via the runtime env chain (the false "$200 LIMIT HIT" display bug).
> - **2026-07-21:** `main.py` **v4.0** — **L2.5 live**: the L1→L2 committed label now drives `primary_regime` (see §Regime engine). `sweep_reversal_strategy` **v3.2** — **ORB-ownership gate**: a sweep may fire only after the ORB has *released* price (stale/runaway/EXPIRED/past 11:00), not merely after a break registered (CVX 07-21 09:55 double-ownership fix).
> - **2026-07-27 (excavation deploy):** `regime_confluence` **v1.3** (all four non-`_trending`
>   scorers rebuilt as accumulating evidence; `_sweep` gains `trend_state`), `config` **v4.0**
>   (`SWEEP_DELTA_STRONG` 0.12), `REGIME_TRUTHS` **v0.3**, `check_versions` **v3.8**.
>   **Consequence:** this changes the L1 score DISTRIBUTION, not just its labels — every
>   downstream threshold calibrated against the old shape (setup grade bars,
>   `CONTINUATION_CONV_FLOOR`, `_sweep_target_delta` endpoints, condor regime self-gating)
>   is now calibrated against a distribution that no longer exists. **The frozen-baseline
>   window resets to this deploy**, and the L1 knob freeze moves out one week.
> - **2026-07-22 (one fleet deploy, commit `3530b3c` era, 8 files):** `regime_confluence` **v1.2** ramp de-saturation promoted to defaults **and, riding the same push, the mark-limit execution workstream** — new `execution/limit_ladder.py` v1.2, `entry_engine` v3.8 (mark-limit entries), mark-limit exit closes in `exit_engine`, `FLATTEN_WINDOW_OPEN_ET=(15,40)` in config + `time_utils`. **Consequence:** label-gated regime metrics stay attributable to v1.2; P&L / fill-dependent stats are confounded by both changes. The ~2-week frozen-baseline window gets **one week added to its back end** to preserve a clean stretch.


Monday 2026-07-18 is **day zero** on a materially changed engine, and the start of the
~2-week hands-off baseline window (regime labels trusted, L2 weights frozen, condor behavior
confirmed) that gates the pitchfork. What lands and how:

**Already live on the fleet (Fri 2026-07-17):**
- `trend_engine` v3.1 — intraday-primary tf_weights, the dead-4h TRENDING fix (confirmed via
  journal: AVGO threw TRENDING_BEAR conviction 0.52).

**Landing this deploy pass (fleet flat, one `devtools` option-23 FULL wake→bake→restart→STOP,
catching the 19 asleep boxes):**
- `volatility_engine` VWAP zero-volume guard — SPX NaN→"BELOW" false-signal fix (commit `cf5def8`).
- Iron condor premium-rich band-approach triggers + roll-gets-first-refusal (commit `792d802`).
- Trend Continuation strategy — NEW, paper-first on all boxes from Monday (the 2-week baseline is
  its proving ground).
- Signal journal instrumentation (v1.0 module + `setup_scorer` v1.3 + `main.py` v3.9 +
  `orb_engine` v3.7) — **log-only, zero behavior change.**

**Deploy discipline:** full-file drop-ins, never `git apply` patches (patch desyncs against
uncertain server versions burned ~a dozen turns). **The deploy gate is
`python3 -c "import ast; ast.parse(open('<f>').read())"` on the box** — NOT pytest (wrong-venv /
no-pytest on boxes burned this repeatedly). After the pull, `bash check_versions.sh | grep
MISSING` must print nothing; the canary set now fingerprints every day-zero change plus the
instrumentation, so a stale sync surfaces immediately. **Parity invariant:** the same engines
must reach the control checkout (`~/options-trader-v3`) so the replay harness scores Monday's
tape with the bot that traded it — pull + `check_versions.sh` on control right after the fleet.

**Path note:** the 29 boxes deploy to `~/options-trader` (no `-v3`); the control server checkout
is `~/options-trader-v3`.

**Also activated this pass (2026-07-18):** the shadow observer, **on the live QQQ paper box**
(→ **superseded 2026-07-22: rolled out fleet-wide, all 29 boxes** — still zero new DXFeed
subscriptions, each observer reads its own box's shared store)
(the real fleet instance, `OT_INSTRUMENT=QQQ`, `~/options-trader`) — **not a separate QQQ-TEST
instance.** This is deliberate and is the whole point of the one-producer/many-readers design:
the observer opens **no DXFeed of its own**, it reads the shared store that the QQQ box's own
`candle-feed.service` already fills. One feed, two readers (bot + observer) — no 11th
subscription. Installed as `shadow-observer.service` — **enabled at boot since 2026-07-22; the original
`shadow-start`/`shadow-stop` timers (09:00 / 16:30 ET) are RETIRED**: edge-triggered timers
fire while the overnight-stopped boxes are off (which is why the observer collected exactly
one session ever); the service self-gates on RTH instead. Env supplied via a `.d/env.conf` drop-in copied from
`optionsbot.service` (secrets never leave the box), running **stage 1 (primitives measure-only)**.
Smoke-tested clean; dormant until Monday 09:00 ET. Stays at stage 1 for several sessions
(velocity verification against `data/OHLC/`) before stage 2 is considered.

**Deliberately NOT in this pass:** the offline-replay bookmark (defect S — build and prove inert
on the tester first); observer *fleet* deployment (one live box — QQQ — is the whole ask, not all
29); shadow-observer service-unit templatizing (defect D service-half); any gate change. Monday's
engine *decisions* are exactly what was approved Friday.

**The Monday habit:** after the EOD conductor runs on control, `cd ~/day_trader_pro &&
./label_day.sh` to tag the session's trend/sweep/pin/breakout symbols — this is what fills the
Layer-1 Tier-B tape gaps (see `docs/REPLAY_VALIDATION.md` and `ROADMAP.md` L1.7).

---

---

<!-- ================= was: README.md § Data — one producer, many readers (v3.0) ================= -->

### Data — one producer, many readers (shipped, v3.0)

Every process on a box — bot, engines, ORB range, candle logger, shadow observer, VIX —
reads **one** SQLite (WAL) store, written by **one** DXFeed subscription held exclusively by
`data/candle_feed.py` (`candle-feed.service`). No consumer may open its own stream.

`data/market_data.py` is a pure store *reader* preserving the exact v2 contract
(`fetch_candles` / `fetch_quote` / `fetch_all_candles`), which is why every downstream engine
required zero changes. Readers **fail loud**: `None` + `WARNING` when the store is missing or
the heartbeat exceeds `OT_FEED_STALE_S` (120s). A dead feed surfaces as "no data," never as
stale numbers driving a decision.

The purge is real and verified: **zero `yfinance` imports repo-wide.** It is the load-bearing
prerequisite for everything else — calibrating conviction against ROI on a feed the bot
doesn't trade is calibrating a board it never plays on.

---

<!-- ================= was: README.md § Signal journal — Phase-3.1 (v1.0) ================= -->

### Signal journal — Phase-3.1 instrumentation (shipped, v1.0, 2026-07-18)

`analysis/signal_journal.py` is a **log-only** subsystem that makes the *perishable* part of
every trading decision durable. The 1-min OHLC tape can be replayed forever; what evaporates at
16:00 is what the option chain looked like at signal time — premium, bid/ask spread, IV, greeks
— and which gate disposed of each signal. Without it, every session between now and the Phase-3
calibration campaign is tape that can never *become* calibration data. ROADMAP Phase 3.1 states
the rule: *"a gate you can't counterfactual is a gate you can't calibrate."*

It writes append-only JSONL to `data/signal_journal/<YYYY-MM-DD>/<SYMBOL>.jsonl` (gitignored,
self-locating repo root like the shadow observer). Event vocabulary:

| event | emitted by | carries |
|---|---|---|
| `scored` | `setup_scorer` v1.3 | every scored signal **including below-B REJECTs** — grade, total, both thresholds, full breakdown, regime conviction, and the signal's quote context (bid/ask/mark/spread/IV/greeks) |
| `disposition` | `main.py` v3.9 | what happened after scoring: `fired` / `sizing_rejected` / `invalid_signal`; ORB dispositions carry `retest_depth_px` + its ATR-relative form |
| `retest_check` | `orb_engine` v3.7 | per-armed-candle retest penetration depth in PX (**negative = near-miss**) + `orb_width` — the defect-G distribution |
| `condor_plan` / `condor_leg` | `main.py` v3.9 | regime conviction at condor decision/fire time — the condor bypasses the score path, so without these its Phase-3 bar could never be calibrated |

**Design guarantee:** every emission is wrapped so any failure (full disk, bad payload,
permissions) degrades to a missing log line, never a raised exception. The trading loop is
byte-identical whether the journal is present, absent, or broken. It imports nothing from
`execution/`, `risk/`, `strategy/`, or `notifications/`, never opens `trades.db`, and places no
orders. Join key across events: `ts_et` + symbol (one signal per tick, single-threaded per box).

Collection: journal files ride `snapshot.sh` today; an EOD-conductor collection phase will be
added when volume justifies it — **deliberately not wired into the conductor chain yet**, which
is finally flawless and stays untouched until any addition is proven inert on the tester.

---

---

<!-- ================= was: README.md § Mark-limit execution (2026-07-22) ================= -->

### Mark-limit execution (2026-07-22, `execution/limit_ladder.py` v1.2, now v1.3) — never cross the spread

Before this, single-leg entries **and** exits were MARKET orders and spread closes used a fixed
$0.10 buffer past mark — on a $0.20 0DTE contract with a $0.05 spread that is ~25% of premium
round-trip, larger than any edge being captured. Every decision in this system is made at the
mark; now the fill targets it too:

- **OPENS** post a limit **at the mark**, re-priced to the fresh mark every tick (~15s). An
  entry that never fills costs nothing — the strategy re-signals next tick.
- **CLOSES** post at the mark and **re-anchor every retry tick**, so a stop chases a falling
  market down instead of parking at a stale price. The exit *trigger* (e.g. −40%) decides WHEN
  to start closing; it never anchors WHERE the limit sits.
- **The one exception — EOD flatten:** 15:40 ET opens the flatten window with mark-limit
  reposts; **15:45 ET sends MARKET, no exceptions** (an unfilled 0DTE at the bell is an expiry,
  and an assignment on a short leg). `FLATTEN_WINDOW_OPEN_ET=(15,40)`,
  `limit_ladder.hard_close_order_mode()`, `time_utils.is_hard_close_time()`.
- **Paper parity:** paper books the same mark the live limit would post
  (`paper_fill_price`). Paper is now honest about **price** but still optimistic about **fill
  rate** — the residual paper↔live gap is no-fill risk, not slippage. ⚠️ This *supersedes* the
  defect-R uniform 1% paper slippage for single-leg and butterfly entries and the
  `LIVE_CLOSE_LIMIT_BUFFER` close pricing; see defects R and T.

---

<!-- ================= was: README.md § Fill-confirmed exits (v3.4/v3.5) ================= -->

### Fill-confirmed exits (v3.4/v3.5, 2026-07-15) — a close is only real when the broker says so

The 2026-07-15 hard close booked ~8 condor legs at `pnl=+$0.00` because
`flatten_all` treated order *submission* as a fill and booked at a fallback
price. That entire class of bug is now closed:

- **The shared contract:** `place_exit_order()` returns a `FillResult`
  (`confirmed / fill_price / order_id / partial`). `_execute_exit()` books P&L
  **only** when `confirmed=True` with a real price. Unconfirmed → the row
  stays OPEN and the 15:45→16:00 retry loop re-attempts and pages.
- **PAPER:** simulates the fill at the last-known mark in one pass; no mark →
  declines and retries next tick rather than inventing a price. Unchanged
  behavior, now formalized.
- **LIVE (`_confirm_and_book_live_exit`, v3.5):** submit → capture the broker
  order id → poll to a bounded deadline (`LIVE_FILL_POLL_SECONDS` /
  `LIVE_FILL_DEADLINE_SECONDS`) → book **only** the broker's net fill price
  read from per-leg fills. Never the mark, never entry, never $0.00.
  Unfilled at deadline → cancel, resolve the cancel/fill race, stay open,
  page once. **Partials:** filled portion stashed, remainder resubmitted next
  tick at a fresh mark, booked once at the quantity-weighted net price. A
  working order id is resumed on re-entry — retry ticks can never
  double-submit. Verticals close as one 2-leg spread order (previously the
  long leg was orphaned); spread closes are marketable **limits** (tastytrade
  rejects MARKET on spreads) with the vertical debit capped at spread width;
  limit prices follow the SDK's **signed** convention (negative=debit). **2026-07-22: close limit *pricing* superseded by the mark-limit policy above (post at mark, re-price per tick) — the buffer is retired; the FillResult confirmation contract is unchanged.**
  Acceptance tests: `tests/test_live_fill_confirmation.py` (A–E per
  `FABLE_SPEC_live_exit_fill_confirmation.md`) — all pass; tiny-account live
  validation still required before cash.

Theta protection is deliberately narrow (v1.5). The v1.3 check fired on the first green tick —
58 of 77 exits were theta-bleed at a **median 60-second hold**, capping trends while the day's
P&L came from the few trades that reached the trail. Decay is projected per **calendar** day
(1440 min); v1.3 divided by the 390-minute RTH day and overstated decay ~3.7×.

---

---

---

## FLEET STATE — 2026-08-13 (the eleven-change bake)

<!-- was: docs/FLEET_STATE_2026-08-13.md v1.0, folded in 2026-08-14. docs/README.md: completed work goes to HISTORY, not a new file. -->

**WHERE THE FLEET STANDS AFTER 2026-08-13.**

Baked `7efd320` across **29/29 boxes**, all services active, then the hotfix
`e639099` on top. This is the largest single-day behavioural change in the
project's history: **eleven changes that alter what trades**, landing together
because the alternative on the table that morning was regressing the fleet to
options_trader v2 and restarting from the primitive engine.

---

### 0. THE FINDING THAT DROVE EVERYTHING

The operator's own summary, and it is the most accurate sentence written all day:

> *"I demanded so much confluence for a decision that it ended up simply being
> confirmation instead (the move has happened)."*

Six independent measurements point at it:

| evidence | reading |
|---|---|
| grade A 399 trades **−$21/trade** vs grade B 220 at **+$9** | high score = worse |
| `reg.conviction` pegged at 1.00: **−$25/trade**; lowest band **+$17** | high conviction = late |
| handoff × conviction 1.00: **n=128, −$6,623** | one band > the whole strategy's loss |
| handoff 52% never-favorable vs standalone 33% | the relaxed-gate path is the bad half |
| MFE at **89% of hold**, 81% late | the move is over when we exit |
| scorer separates "will it go green", not "will it pay" | it grades favorability, not profit |

**⚠️ AND THE DIRECT TEST STILL HAS NOT RUN.** `factor_sweep` found
`derived.confluence_count` takes only TWO values across 619 trades — 3 and 4.
There is no low-confluence population anywhere in the sample. **You cannot
measure the cost of a filter you never relax**, which is precisely how a
confirmation requirement hides inside what looks like a confluence model. The
diagnosis is well-supported by proxies; it is not yet directly measured.

---

### 1. BEHAVIOURAL CHANGES — these alter what trades

### GRD.1 — continuation stops buying 1.5× size
`risk/setup_scorer.py` v1.7

**Why.** `ContinuationStrategy` had no entry in `STRATEGY_PROFILES` and fell to
`"default"`, where `regime_conviction` 0.30 and `signal_quality` 0.25 weighted
**the same number twice** (continuation sets `signal.conviction =
regime.conviction`). Add `vwap_alignment` and `liquidity_clear`, both measured
constants at 1.000, and **~90% of the grade was duplicate or constant.**

**What changed.** Explicit profile: `regime_conviction` 0.55 (the old 0.30+0.25
on one number), `grade_b` **0.55 UNCHANGED** so the fire boundary is provably
identical — verified over 200,000 random signals, zero divergence. `grade_a`
**1.01**, above the maximum achievable 1.00, so no continuation setup earns the
1.5× multiplier until an input is proven to separate.

**Expected benefit.** ~**+$2,748** on the 18-session sample. Sizing only.

**Tuning.** No env knob. To restore A-grades, lower `grade_a` below 1.0 — but
only after a scorer input demonstrably separates. **Second-order effect to
watch:** smaller continuation losses mean fewer daily-loss-breaker trips, so
boxes may stay alive longer and trade further into the afternoon.

**Verification.** No continuation trade should carry a 1.5× multiplier.

---

### STOP FLOOR 0.25 → 0.15
`config.py` v4.7 · `OT_CONT_STOP_PCT`

**Why.** The `max_loss_floor / ContinuationStrategy` cohort is **66 trades over
9 sessions at a 0% win rate.** A 15% floor stops all 66 with **ZERO winners
cut** — net delta **+8.85** units of entry premium against +2.25 at 25%. Meets
the pre-registered cheapest-threshold-catching-no-winners rule rather than an
in-sample argmax.

**⚠️ What this cohort is.** BY DEFINITION the trades where NO structural stop
fired — not regime_flip, not bos_exit, not insurance_stop. The thesis was still
technically intact and the premium died anyway. Zero winners cut over 9 sessions
is evidence it cost nothing; it is not proof it cannot.

**Tuning.** `OT_CONT_STOP_PCT` is the per-box override; the repo default is the
fleet lever. If winners start getting cut, 0.20 is the next stop up.

---

### AFD.1 — no long premium after 11:00
`main.py` v6.2 · `config.py` v4.6 · `OT_DEBIT_CUTOFF_ET`, `OT_DEBIT_BLOCK_ACTIVE`

**Why.** Operator: *"The only other Long that can fire is either part of a
butterfly or an iron condor vertical spread from 11 o'clock onwards."* Measured,
843 trades / 15 sessions: open 09:30-10:00 **+$10,717.50** against 10:00-11:00
**−$8,715** and 11:00-14:00 **−$1,539.50**, on a whole book of **+$463**.

**What changed.** ORB / Continuation / SweepReversal refused past 11:00. Placed
AFTER the signal is chosen — one gate instead of three, the refused signal is
fully formed so the journal records `gate_block:afternoon_debit`, and condor legs
never reach it (they route through `_execute_condor_leg` earlier), so the credit
path is exempt **by construction** rather than by a list entry that could rot.

**Expected benefit.** ~**+$2,901** on continuation alone across 18 sessions.

**⚠️ Known trade-off.** It also removes the 12:00 hour, which was continuation's
only positive afternoon hour (**+$1,225**, n=81 — about four trades a session, so
possibly noise). A 13:00 cutoff would have saved more on this sample. The
operator chose 11:00 on structural grounds (theta), not P&L, and that reasoning
survives a noisy cell.

**Tuning.** `OT_DEBIT_CUTOFF_ET="13:00"` moves the hour with no deploy.
`OT_DEBIT_BLOCK_ACTIVE=0` disables it.

**⚠️ NOT ADDRESSED:** the 10:00 hour, **−$8,715** — still the largest single
negative in the book and untouched by this change.

---

### PF.5 — the condor anchors on the daily pitchfork
`strategy/iron_condor_strategy.py` · `main.py` v6.3 · `analysis/pitchfork_observer.py`

**Why.** The pitchfork has been built, live and **unconsumed** since 2026-08-12 —
full geometry, lifecycle, and an observer journaling rails, with exactly ONE call
site (`main.py:2091`) and **nothing ever reading the rails back.** The white
paper pre-registered condor strikes as the first consumer because strike
placement produces a credit directly comparable on identical tape.

**What changed.** Short strikes anchor on the rails. A strike qualifies only if
beyond the RAIL, beyond the surviving `0.80 × EM` MINIMUM DISTANCE (retained so a
rail on top of spot cannot produce a strike with no room — the ~3-week bleed
`v-dualfloor` fixed), and **beyond the SESSION EXTREME** (new: a level price has
already traded through is a level the market has PROVEN it can reach). Leg order
from the fork's slope. **NO FORK → NO CONDOR.**

**Daily, not hourly**, and deliberately: a daily fork is invalidated only by
DAILY closes, so an intraday session cannot move the rail a spread was sold
against. The hourly fork has a p50 lifetime of 5 bars and a k=3 confirmation lag.

**Expected behaviour, not benefit.** Measured coverage 2026-08-12: **13 daily
forks across 7 of 15 boxes**, so roughly half the fleet is condor-ineligible.
**And the daily `pos_pct` runs p10 40.8 / p50 74.2 / p90 98.5** — price lives in
the upper half and essentially never visits the lower daily tine. **Expect mostly
call-side standalones and few completed two-sided condors.** That is arguably
correct: if price never approaches the lower tine, the put side was never rich.

**Tuning.** `OT_CONDOR_REQUIRE_FORK=0` restores condors without a fork.
`OT_CONDOR_PF_ANCHOR=0` reverts to the dual floor. `OT_CONDOR_PF_TF=hourly`
switches frames. `OT_CONDOR_PF_FLAT` sets the slope epsilon below which leg
ordering falls back to proximity.

---

### PF.6 — POP floor and quote-width floor
`config.py` v4.9/v4.10 · `OT_CONDOR_MIN_POP`, `OT_CONDOR_MAX_QUOTE_WIDTH`

**Why.** Operator: *"There should be a reasonable expectation of trade success
better than 50-50... somewhere near the 70 to 80% range."*

**POP = Φ(z), z = distance / (σ·√bars_left)**, horizon to the **15:45 flatten**
(a condor leg is closed there, so using the bell overstates T). Driftless and
normal deliberately — a drift term is a forecast, and this system's directional
forecasts do not separate. Degenerate inputs return 0.0 and FAIL; a missing ATR
must never read as safe.

**⚠️ VALIDATED OUT-OF-SAMPLE.** TC.7's handoff arm, terminal-OK against measured
EV: **58%→−0.23 · 54%→−0.33 · 63%→−0.24 · 67%→−0.09**, then **76%→+0.33 ·
78%→+0.32 · 88%→+0.35**. **Every cell below 70% lost money; every cell at 76%+
made it.** Nobody searched for 0.70 — it is a stated risk preference, not an
argmax, **which is exactly why it must NOT be re-tuned on this same data.**

**Honest cost.** On the STANDALONE arm the sub-70 cells were marginally POSITIVE
(+0.08 at 61%, +0.04 at 69%), so the floor gives up ~$0.12/spread there.

**Quote-width floor 0.25 of mid.** A RANKING never refuses — it returns the
least-bad strike even when every candidate is broken, and on 0DTE a nickel of
noise on a wide quote trips the stop on the QUOTE rather than on price. **0.25 is
a stated PRIOR reasoned from an adjacent population** (factor_sweep's worst
continuation quintile ran 0.13-0.88 at −$37/trade; the two best under 0.043) —
debit entries, not condor shorts. The rejected-leg log is what would fit it
properly.

**Tuning.** `OT_CONDOR_MIN_POP` 0.70 → 0.75/0.80 tightens toward the top of the
band. `OT_CONDOR_MAX_QUOTE_WIDTH` loosens if legs are being refused too often —
the skip log prints the width that failed.

---

### CND.7 — the ratchet no longer closes untested legs
`execution/exit_engine.py` v4.17 · `OT_CONDOR_RATCHET_STANDALONE_ONLY`

**Why, and this is the sharpest defect found all day.** The base −25% stop only
ever fires on the TESTED side, because a credit spread's value RISES as price
approaches your short. **The ratchet does the opposite: it tightens the UNTESTED
side's stop to breakeven at +20% and +20%-locked at +40% precisely BECAUSE that
side is winning.** On the reversal the tested leg stops at −25% **and the
untested leg hits its ratcheted stop too** — a leg price never went near, closed
by a stop that exists only because it was profitable. **That is the double-stop:
5 of 14 condor symbol-days had BOTH sides stopped.** And it fires BEFORE the roll
can ever be used, because the roll needs a tested side.

**What changed.** While `_condor_sibling_open()` is true, the base floor is the
ONLY stop. No tier, and the stored high-water is neither applied nor updated, so
a leg returning to standalone resumes from a level it genuinely earned.

**Preserved.** `condor_stop` went **0% → 19% win** after the ratchet shipped —
but that came mostly from STANDALONES (18 of 46 legs never got a second side).
Scoping keeps the gain where it was measured.

**⚠️ Accepted cost.** An untested leg that runs to +40% and reverses now gives it
back rather than locking +20%.

**Not changed, deliberately:** the adverse-regime-flip exit is direction-aware —
a call spread exits only on TRENDING_BULL, which IS price rising toward that
short strike — so it already fires only on the threatened side.

---

### VERTICALS HOLD TO 15:45
`config.py` v4.12 · `OT_VERTICAL_HOLD_1545`

**Why.** The flatten ladder opens at 15:40 so a DEBIT position gets a mark-limit
phase before the 15:45 cross. **A short vertical has the opposite sign** — it
decays TOWARD the holder, so 15:40-15:45 is the steepest part of its curve.
Operator: *"It's 5 more minutes of exponentially rising profit curve."*

**Why the ladder was NOT moved globally.** Opening it at 15:45 forces every EOD
exit marketable — the exact failure `time_utils` v3.8 fixed, and expensive on a
book whose widest spread quintile already costs −$37/trade.

**⚠️ NOT held past 15:45, and this is a hard limit.** Every instrument except SPX
is AMERICAN-STYLE and PHYSICALLY SETTLED, so a spread finishing BETWEEN the
strikes assigns the short and leaves an unhedged overnight stock position.
"Defined risk" is true at settlement, not through assignment — **and the paper
engine has no assignment model, so it would report a clean result that does not
survive going live.**

---

### TC.6 — the trend credit spread
`strategy/trend_credit_spread.py` v1.0 · `main.py` v6.4 · `OT_TCS_ACTIVE`

**Why.** The afternoon needed a vehicle. AFD.1 blocks long premium, the condor
self-gates to RANGING, and the butterfly needs PINNING GEX — so a **trending**
afternoon had nothing.

**The trade.** After an ORB runaway, sell a defined-risk vertical BEYOND the
broken boundary. Price broke the range and never retested, so the boundary IS the
floor of that move and the level `orb_structure_stop` already calls thesis death.
**Structure and invalidation become the same event.**

**Measured** (`spread_counterfactual --anchor orb`, runaway-handoff arm, 18
sessions): EV positive at EVERY offset; the 0.00% cell — the strike AT the
boundary — **n=30, +$0.52/spread, 90% terminal OK, 79% RECOVERED**, entry sitting
p50 +0.91% above the boundary. **The STANDALONE control was mostly NEGATIVE on
the same anchor**, because without a runaway the boundary sits at or above the
fill 64% of the time. **Runaway-specific by construction.**

**Exit: BREACH OR NICKEL, nothing else.** No premium stop, no ratchet — **the
measured EV was HELD TO EXPIRY, UNMANAGED**, so a stop bolted on is a different
trade. Breach is a CLOSED BAR beyond the boundary; a wick is a touch.

**⚠️ HIGHEST-RISK ITEM TOMORROW.** Never executed a live order. Fires through
`_execute_condor_leg`. Defers when a condor plan holds the symbol.

**Tuning.** `OT_TCS_ACTIVE=0` kills it — **for defects, not for bad trades.**
Operator: *"bad trades are still good data."* It only fires after a runaway on a
trending afternoon, so observations will be scarce; killing it on the first loser
leaves nothing to read.

---

### GRD.2 — continuation populates `underlying_target`
`strategy/continuation_strategy.py` v1.7

**Why.** `trend_strike_plan` has ALWAYS computed the target and USED IT to pick
the strike, then discarded it. **The bot was never target-free; it was
target-blind**, and three consumers sat inert on 77% of fleet volume: `_rrr()`
returned None on every continuation signal (why `rrr` appears in ORB's scorer
table and nowhere else, and why MIN_RRR was structurally inert);
`_pools_in_path` scans `entry < p < target`, so with 0.0 a LONG's window is
**empty by construction** and `liquidity_clear` was a STRUCTURAL constant at
1.000; and `_update_post_target_trail` is guarded on `> 0`, so continuation
always fell back to the blunt 85% trail instead of the FVG floor past 100% TP.

**⚠️ NOT A TAKE-PROFIT.** The no-target design stands. This is the R denominator
and the trail's reference. A test asserts no exit fires on reaching it.

**⚠️ The entry gate barely moves — arithmetic, not opinion.** `liq_score` at
weight 0.20 removes AT MOST 0.20 from a total whose p50 is 0.885 against a 0.55
bar. Even 4+ blocking pools leaves 0.685 and still fires. **The real change is
the exit trail.**

**Verification signatures — the only per-change attribution available tomorrow:**
`rrr` appearing in the scorer breakdown · `liquidity_clear` moving off 1.000 ·
`post_target_trail` appearing in `exit_reason`.

---

### SWP.3 — the approach corroborator's sign is refuted
`analysis/trade_readiness.py` v1.9 · `SWEEP_APPR_W`

**Why.** Three independent measurements: **LIQ.1** (the London level TRACKS PRICE
rather than being approached by it), **ANT.1** (appr_val −41%, appr_touches
−45%), **ANT.2** (fitted weights −0.39 / −0.40).

**Not inverted.** `1 - appr_val` asserts "far from any named level = ready",
nonsense for a SWEEP. The likelier mechanism is that **proximity is PRE-sweep**:
price near a pool means the sweep has not happened, so the term was scoring the
setup's ABSENCE. Sign wrong, form unknown — removed from the composite, KEPT in
the journal.

**⚠️ The renormalisation was the real risk.** The four weights summed to exactly
1.0 and the stage/arm bars are ABSOLUTE. Dropping 0.25 without redistributing
would compress every sweep score by a quarter and make the arm bar effectively
unreachable — **the track would go quiet while looking like a correction.**
0.30/0.20/0.25 → **0.400/0.267/0.333**.

**LOG-ONLY** — `main.py:2045` discards `assess_all()`'s return, so no trade
changes today. It stops every FUTURE fit inheriting a backwards term.

**⚠️ Tuning warning.** Raising `SWEEP_APPR_W` alone pushes the sum past 1.0 and
inflates every score against the absolute bars. **Change all four together or not
at all.**

---

### FRC.3 — the venue's price grid, on every order path
`execution/tick_size.py` · `limit_ladder.py` v1.4 · `data/options_chain.py`

**Why.** Option increments are class- AND level-dependent, and `round(px, 2)`
posts UNPOSTABLE limits on nickel/dime classes. An invalid limit is rejected —
or **silently adjusted by the venue, which is a fill at a price nobody chose with
nothing in the logs to explain it.**

**Resolution order, so order time never guesses:** venue rule
(`NestedOptionChain.tick_sizes`, authoritative, cached per symbol) → quote proof
(an off-nickel bid PROVES penny; **asymmetric**, refines downward only) →
`PENNY_CLASSES` last resort, **which logs a warning**. Every resolution records
its source.

**And the bigger fix:** `limit_at_mark` prices EVERY exit plus the 15:40-15:44
reposts — far more orders than the entry ladder — and it was doing `round(px, 2)`.

**🔴 HOTFIX `e639099`.** The first version had the comment *"once per symbol per
session"* and **no cache check**, firing an extra SDK call on every
`fetch_chain()` — called from three places in the tick loop. `needs_venue_rule()`
now guards it, and a failed attempt counts as answered so a broken fetch does not
become the same hot loop.

---

### 2. SHIPPED INERT — built, tested, not active

| item | state | to activate |
|---|---|---|
| **LIQ.4** liquidity ledger | built, **NOT WIRED** — collects nothing | needs a tick-path call + RTH reset |
| **FRC.2** entry limit ladder | `OT_ENTRY_LADDER=0` | **do NOT enable before the fill model gates paper fills** |
| `fill_model.would_fill()` | built, unused | the gate FRC.2 depends on |

**⚠️ WHY FRC.2 MUST STAY OFF.** `paper_fill_price` books the posted price and
assumes it fills. Shade the limit without a fill test and every trade books the
aggressive rung while **no missed entry is ever modelled** — the more aggressive
the rung, the larger the manufactured gain. **Rung 1 would look like the best
change this system has ever made and be entirely fake.**

---

### 3. TOOLING — read-only, no behaviour

`slippage_audit` (FRC.1) · `spread_counterfactual` (TC.7, anchors: entry / orb /
floor) · `factor_sweep` v1.1 (ET hours, monotone band floor, `--setup-type`) ·
`orb_conversion` v1.1 (trade_id dedupe) · `scorer_backtest` v1.2 (raw row +
dedupe) · `credit_edge` v1.2 (touch trigger, per-side OTM guard, effective-n) ·
WORKING_AGREEMENT **§20** (an absence canary tests for a definition, never a
mention).

---

### 4. THE NUMBER THAT REFRAMES EVERYTHING — FRC.1

**Gross +$2,156 over 800 trades = +$2.70/trade, against average friction of
$126/trade. The system's edge is ~2% of the round-trip spread it trades in.**

The −$98,454 headline is a **worst case** assuming every order crosses; the bot
posts mark-limits. **But the relative ranking is valid regardless**, and the
quintile table is decisive: **Q5 carries $60,185 — 60% of ALL friction — for
−$169 of gross.** Q4+Q5 together are 79% of friction against −$6,337.

**Cutting them removes four-fifths of transaction cost AND improves gross.** It
is a pre-entry filter needing no forecast. **This is the largest unbuilt lever on
the board.**

---

### 5. WHAT TO WATCH TOMORROW

Read the first session as **"did anything break"**, not "which change helped."
Eleven behavioural changes in one bake; attribution is not available except for
GRD.2's three signatures.

**Expected, not defects:** `Condor: NO PLAN — no usable daily pitchfork` on ~half
the boxes · `liquidity_clear` off 1.000 · `STRATEGY: BLOCKED — … afternoon debit
cutoff` after 11:00 · few or zero `[tcs]` lines (runaway + trending is rare).

**Actual defects:** any traceback · `[tick] NO VENUE RULE` on a symbol that
should have one · TC.6 firing repeatedly on one symbol · condors going to zero
fleet-wide.

---

### 6. THE NEXT GATE — FRIDAY 2026-08-28

Operator's schedule, set 2026-08-13:

1. **Fri Aug 28** — evaluate paper P&L impact after the bugs are worked out.
2. **Resume L1 dial freezing.** L2 is mostly complete — a few verifications
   remain; chatter is nearly eliminated.
3. **Then L3.**
4. **Then final trade adjustments + stop-quality evaluation.**
5. **Then live cash, reduced size for the first week.**

**The two weeks to Aug 28 are a measurement window.** The changes are in; the
question is what they do. Resist re-tuning on the first bad session — most of
today's thresholds are stated priors rather than fits, and re-fitting them on the
data that motivated them is how an out-of-sample validation becomes an in-sample
one.
