# docs/WAREHOUSE_LAYOUT.md — v2.0

*The specification for `s3://vertigo-warehouse-tx9ai`. What goes where, in what
shape, with what timestamps, and why. Read this before adding any stream.*

## CHANGELOG

- **v2.0 — 2026-08-16 — the spec catches up with what is actually running.**
  Every stream in the register is now MIGRATED, not planned, and three streams
  exist that v1.0 never mentioned: `liquidity_ledger` (LIQ.4), and
  `regime_log` + `circuit_breaker_events`, which **were specified in v1.0 and
  then silently never built** — found only when the reader was written and
  would have reproduced two permanently empty bundle sections. Adds §4a
  (measured volumes and cost), §5a (where processing happens), §6a (collection
  coverage vs `dt=` coverage — not the same thing), and records the first
  end-to-end read: **19 of 25 dates reproduce the control bundle exactly.**
  §11's benchmark is no longer hypothetical.

- **v1.0 — 2026-08-13 — initial specification.** Written after probing all 29
  boxes for every artifact they produce. Locks the conventions that are
  expensive to change later (key layout, timestamp policy, envelope fields) and
  records the operator decisions behind them. Chain snapshots were already
  migrated under these conventions (WH.1, 16,782 objects, reconciled exactly).

---

## 1. WHY THE LAYOUT IS SPLIT THIS WAY

The problem this store exists to fix: on control, `~/day_trader_pro/reports/`
holds analysis products that are **also the only copy of themselves** — the
23 MB `regime_replay_<date>.jsonl` files being the clearest case. Cache and
system-of-record are conflated, so "is it safe to delete this?" has no
answer.

Three top-level domains, split by *who owns the truth*:

| domain | contents | rebuildable? | deletion policy |
|---|---|---|---|
| `raw/` | box-emitted facts, immutable | **no** | never |
| `derived/` | control-produced analysis | yes, from `raw/` | free to delete |
| `meta/` | fleet context, schema registry | partly | never |

Anything in `derived/` can be regenerated. Nothing in `raw/` can. That single
distinction is the point of the split.

---

## 2. KEY CONVENTION

```
raw/<category>/dt=<YYYY-MM-DD>/sym=<SYM>/<epoch_ms>-<sha256[:16]>.json
```

**Category outermost.** Streams have incompatible schemas and are never scanned
together; in Athena terms they are separate tables.

**Date before symbol.** The dominant access pattern is day-scoped (reports 40
and 41 want one date, all symbols). With `dt=` first that is a single prefix
listing. With `sym=` first it would be 29 listings stitched together, because
S3 prefix matching is left-to-right only.

**Hive-style `dt=` / `sym=`** so Athena and Glue discover partitions without a
custom parser. Free to adopt now; expensive to retrofit.

**Content-hash suffix, not uuid4.** This is a deliberate deviation from
handoff decision #2, and it earns its place: a uuid makes every retry write a
duplicate object, while a content hash makes the push idempotent. Proven under
test — a deliberately erased ledger re-pushes and produces zero duplicates —
and proven in production, where 16,782 pushed objects reconciled to exactly
16,782 objects in the bucket.

**Three levels, not four, except where cardinality is tiny.** Partitioning on
a high-cardinality field (strategy, regime) fragments into many small objects
and per-file overhead dominates. `interval=` is the one sanctioned fourth
level: four or five distinct values, and queries essentially always pin one.

---

## 3. THE ENVELOPE

Every object is a wrapper around the source record. The source is preserved
**verbatim and untouched** inside `record`; everything else is provenance.

```json
{
  "schema_version": 1,
  "datatype": "chain_snapshot",
  "symbol": "SPX",
  "dt": "2026-08-13",
  "ts_epoch_utc_ms": 1786651740000,
  "ruleset": "0d70673",
  "event": "pitchfork",
  "src_host": "ip-172-31-33-112",
  "src_file": "SPX.jsonl",
  "src_line": 41,
  "pushed_at_utc": "2026-08-13T21:50:44+00:00",
  "record": { }
}
```

- **`ts_epoch_utc_ms`** — the normalized join key (§5). Added, never
  substituted: the source timestamp survives inside `record`, so a wrong
  conversion is recomputable rather than baked in.
- **`ruleset`** — present on signal-journal events, copied up for filtering.
  See §6.
- **`event`** — copied up where the stream is heterogeneous. Used for
  filtering, **never for partitioning**.
- **`src_*`** — which box, which file, which line. Makes any object traceable
  back to the thing that produced it.

---

## 4. STREAM REGISTER

Every artifact the boxes produce, its source shape, and its destination.
Measured across all 29 boxes on 2026-08-13; statuses updated 2026-08-16.

**Push order is perishable-first and it is load-bearing.** The stages run
trades → regime_log → circuit_breaker → eod → orb → ohlc → candles →
liquidity_ledger → chains → shadow → signal_journal. On 08-13 the journal ran
first and starved everything behind it under a 240s timeout: ohlc reached 108
objects instead of ~783 and eod 8 instead of ~58. Nothing was wrong in the
bucket; the order was. **Anything added goes before `shadow`, never after.**

| stream | source on box | timestamp field | warehouse prefix | status |
|---|---|---|---|---|
| chain snapshots | `data/chain_snapshots/<date>/<SYM>.jsonl.gz` (multi-member gzip, one snapshot/line) | `ts_et` — ISO w/ `-04:00` | `raw/chain_snapshots/dt=/sym=/` | **MIGRATED** (WH.1) |
| trades | `trades.db` → `trades` (84 cols, `trade_id`) | `entry_time` — ISO **`+00:00`** | `raw/trades/dt=/sym=/` | **MIGRATED** (WH.2) |
| regime log | `trades.db` → `regime_log` | `logged_at` | `raw/regime_log/dt=/sym=/` | **MIGRATED** (WH.8a) — ⚠️ specified in v1.0 and never built until the reader exposed it |
| circuit breaker | `trades.db` → `circuit_breaker_events` | `event_time` | `raw/circuit_breaker/dt=/sym=/` | **MIGRATED** (WH.8a) — same omission; no events yet, so the prefix is empty |
| signal journal | `data/signal_journal/<date>/<SYM>.jsonl` | `ts_et` — ISO w/ offset | `raw/signal_journal/dt=/sym=/` | **MIGRATED** (WH.3) — runs LAST |
| shadow observer | `data/shadow/<date>/<SYM>.jsonl` | ISO w/ offset | `raw/shadow/dt=/sym=/` | **MIGRATED** (WH.3) — ⚠️ **ends at the Layer-1 freeze**; the stage stays but goes inert |
| OHLC (daily CSV) | `data/OHLC/<date>/<SYM>.csv`, header `timestamp,open,high,low,close,volume` | `timestamp` — ISO w/ offset | `raw/ohlc/dt=/sym=/` | **MIGRATED** (WH.3) |
| candles (feed store) | `data/feed_store.db` → `candles` | `ts_epoch_ms` — epoch UTC | `raw/candles/dt=/sym=/interval=/` | **MIGRATED** (WH.3). FEED.2's extended tape needs no change: it is a separate store symbol and `SELECT DISTINCT symbol` picks it up as `sym=<SYM>_EXT` |
| EOD P&L | `~/eod/pnl_today.json`, `~/eod/trades_today.json` | `date_et` | `raw/eod/dt=/sym=/` | **MIGRATED** (WH.3) — **see §7** |
| ORB state | `orb_state.json`, `orb_range.json` | none | `raw/orb_state/`, `raw/orb_range/` | **MIGRATED** (WH.3) — **see §7**. ⚠️ `orb_range` has objects; **`orb_state` has ZERO** — unexplained, see §10 |
| liquidity ledger | `data/liquidity_ledger/<date>/<SYM>.json` (LIQ.4, rewritten every closed bar) | `date_et` | `raw/liquidity_ledger/dt=/sym=/` | **MIGRATED** (WH.14). Whole-file, but SAMPLED every 5 min by the timer, so the object count lands near the chain archive's rather than ~390/box/day — and the intraday **evolution** of the level book survives, not just its closing shape |
| bot log | `bot.log` + 6 rotated | — | — | **EXCLUDED** (§8) |

**Trades mutate.** A row is written at entry and rewritten at exit. The
content-hash key turns that into change-data-capture for free: each distinct
*state* of a row lands as its own immutable object, an unchanged row re-pushes
to the same key at zero cost, and a reader takes the latest per `trade_id`.
That is strictly more than `fleet_trades_<date>.json` preserves today, which
only ever sees the end state.

---

## 4a. MEASURED VOLUME AND COST (2026-08-16)

Read off the bucket by `day_trader_pro/warehouse_cost.py`, not estimated.
My own estimates were wrong in both directions — 1.6x under on objects and
2.4x over on bytes — which is why this section exists.

| prefix | objects | GB | avg KB |
|---|---|---|---|
| `raw/shadow` | 399,349 | 0.365 | 1.0 |
| `raw/signal_journal` | 280,713 | 0.169 | 0.6 |
| `raw/chain_snapshots` | 17,935 | 0.820 | 47.9 |
| `raw/regime_log` | 9,009 | 0.003 | 0.4 |
| `raw/candles` | 3,139 | 0.012 | 4.1 |
| `raw/trades` | 1,375 | 0.003 | 2.5 |
| `raw/ohlc` | 812 | 0.018 | 23.8 |
| `raw/eod` | 88 | 0.001 | 10.7 |
| `raw/orb_range` | 81 | 0.000 | 0.3 |
| **total** | **712,501** | **1.392** | |

**~23,750 objects/day · 0.046 GB/day · ~11.7 GB/year. About $2.82/month —
88% of it PUT requests, 5% storage.** Post-Layer-1-freeze, when shadow stops,
that falls to roughly 10,400 objects/day and ~$1.40/month.

**Note which column matters for which question.** The journal and shadow
dominate OBJECT COUNT; chains dominate BYTES. A compaction candidate is chosen
by bytes; a latency problem is caused by count.

### The compaction and Athena decision

**Against Parquet compaction, against a Glue crawler, for Athena but gated.**

- Compaction would save money that does not exist, and it **cannot refund PUTs
  already made** — the lever on cost is batching at push time, not repacking
  afterwards. The real argument for compaction is query LATENCY across many
  small files, and no report has demonstrated that pain. Revisit when one must
  scan more than a month of journal or chains and is measurably too slow.
- **Partition projection, never a crawler.** A crawler costs money on a
  schedule and adds a moving part.
- Enable Athena when a specific report needs SQL, and create the workgroup with
  a **per-query data-scan limit** so a runaway query cannot surprise the bill.
  Sequential/stateful reports — replay integration, MFE/MAE excursions, run
  lengths, pitchfork geometry — stay Python; SQL would be a downgrade.

### The one real billing-surprise vector

**Versioning is ON and there is no lifecycle rule.** Noncurrent versions
accumulate with nobody deciding — the only line item here that grows unbidden.
Content-hash keys make overwrites rare, so it is slow, but it is unbounded.
A billing alarm is the actual protection and is independent of every design
choice above.

---

## 5. TIMESTAMP POLICY

**Operator's rule: all raw data stored in UTC; all user-facing reports
rendered in Eastern.**

This is mechanically safe here, because probing found **no naive-local
timestamps anywhere in the system**. Every stream carries either an explicit
offset or an epoch:

- `trades` — ISO with `+00:00`, already UTC
- `chain_snapshots`, `signal_journal`, `shadow`, `OHLC` — ISO with explicit
  `-04:00`, converts exactly
- `feed_store` — epoch-ms UTC
- `eod` — `date_et`, an ET *date* string (not an instant)

The DST hazard — a repeated wall-clock hour each November, unrecoverable after
the fact — **does not apply to this data**. Worth stating plainly, because the
next stream added might not inherit that property.

**Reports must label their timezone.** A P&L table rendering bare ET times
with no label reintroduces downstream the ambiguity the storage rule removes.

### Joining across streams

The join between chains and trades is **as-of, never equality**: chains land
on a 5-minute cadence, trades fire whenever they fire. The correct join is
"the most recent chain at or before this trade," which bounds chain staleness
at five minutes relative to any trade. For 0DTE that is a real limit on what
the join can support and should be stated in any analysis that relies on it.

`trades.entry_snapshot` may already carry chain state at entry. If so, the
chain↔trade join is a **verification target** before it is a construction
problem. Unresolved.

---

## 5a. WHERE PROCESSING HAPPENS

| operation | where | why |
|---|---|---|
| append | **box only** | write-once objects; nothing in S3 is ever mutated |
| dedup / collapse | **the reader, once** | see the warning below |
| poison filtering | **box at write AND control at read** | deletion is impossible |
| aggregation | **reports only** | operator's decision; storage stays dumb |
| **S3** | **storage, no compute, ever** | logic there would have no tests, no version control and no changelog |

**⚠️ DEDUP CURRENTLY HAPPENS TWICE, WITH DIFFERENT RULES.**
`warehouse_reader.latest_per_trade()` keeps the newest `pushed_at_utc`;
`trade_report.py` independently keeps the **most-filled row**. They usually
agree and are not the same rule. One of them should go — report 41 should
consume already-collapsed bundles.

**⚠️ POISON CANNOT BE DELETED, ONLY FILTERED.** `raw/` carries no Delete
permission by design, so a bad row that reaches S3 is permanent. The box-side
purge (`feed_store`: non-positive prices, 2038-stamped DXFeed rollover bars)
runs at startup and every `PRUNE_EVERY_S`, while the pusher runs every 5
minutes — **so a poisoned bar written and pushed before the next purge is in
the bucket forever.** The mitigation is a declared read-side validity filter,
optionally with a `meta/quarantine/` key list. This is a decision still to be
made, not a bug to be fixed.


---

## 6. TWO KINDS OF VERSION, AND THEY ARE NOT THE SAME

- **`schema_version`** — the shape of the stored object. Ours, stamped by the
  pusher. Bumped when the envelope or key convention changes.
- **`ruleset`** — a hash the signal journal already carries, fingerprinting
  *the deployed logic that produced the event*. Not ours; the bot's.

Discovered 2026-08-13: most boxes carry `0d70673`, but TLT shows `97864a4` and
XOM `45c2f78` — because their latest journals predate a deploy. **Pooling
journal events across a deploy boundary without grouping by `ruleset` blends
incompatible decision logic** — the same failure class as pooling per-regime
stats across a code change. The marker was already in the data; nothing had
catalogued it.

`meta/schema/<category>/v<N>.json` records what each `schema_version` meant, so
the number always has a referent.

---

## 6a. COLLECTION COVERAGE IS NOT `dt=` COVERAGE

The bucket holds `dt=` partitions reaching back to **2026-07-06**. It began
**collecting on 2026-08-13**. Those are different facts and confusing them
produces false alarms.

The first push shipped every row then sitting in each box's `trades.db`, and
those rows carry `entry_time` values from weeks earlier. But `trim_trade_dbs`
prunes those DBs, so **pre-08-13 dates hold only whatever happened to survive
on the boxes** — partial by construction, and meaningless to compare against a
complete local bundle.

A reader deriving its floor from the earliest partition therefore excludes
nothing. **The floor is the collection start date.** Anything before it is
reported as OUT OF COVERAGE — a third category, never counted as either a match
or a divergence, so that the word "divergent" keeps meaning something.


---

## 7. STREAMS THAT DO NOT FIT THE PATTERN

**EOD P&L — one day only, overwritten per session.** `pnl_today.json` carries
no date in its filename and is rewritten each session the box runs. A box idle
since mid-July still holds July's file (SMCI: `date_et` 2026-07-15). Nothing
older survives anywhere. It is small, but it is the P&L record, and the loss
is silent.

**ORB state — ephemeral, and there is no log.** `orb_state.json` is rewritten
**every tick** via `open(path, "w")`. Every historical ORB state the fleet has
ever produced is already gone. Three states: `IN_PROGRESS` (09:30 → the
opening candle closes) → `ESTABLISHED` → `EXPIRED` past
`ORB_NO_ENTRY_AFTER_ET`, with an `attempt` counter that increments on
re-establishment.

*Operator's instruction: capture a snapshot after the range is ESTABLISHED but
before it expires.* **Implemented as capture-on-state, not capture-on-clock:**
the 5-minute pusher writes `orb_state` whenever `state == ESTABLISHED`, and the
content-hash key collapses identical repeats into one object. No fixed window
to miss if a timer runs late, and each distinct `attempt` lands separately, so
re-establishment history is preserved rather than sampled. `orb_range.json` is
a second file with its own status and last-valid range; both are captured.

**VIX — every box logs it, one box owns it.** `feed_store` carries VIX 1m
candles on all 29 boxes, so a naive push would write 29 identical copies into
29 `sym=` partitions. *Operator's decision: SPX is the sole VIX writer;
excluded on the other 28.* Safe because **SPX and QQQ trade every day without
exception** — SPX is always awake. That property makes SPX and QQQ the
reliable anchors for any future job that must land on exactly one box.

---

## 8. WHAT IS DELIBERATELY NOT WAREHOUSED

- **`bot.log`** — *operator's decision: leave it on the box.* Measured at
  253–299 MB per box across 7 rotated files, ~8 GB fleet-wide, roughly 12× the
  entire `data/` footprint. Rotation already bounds it, so exporting was never
  disk relief; it would only buy archival depth, and a lifetime of it is not
  wanted. The cost is accepted knowingly: the "why" behind any session older
  than seven rotations is unrecoverable.
- **Aggregations.** Storage holds facts; reports do the aggregating. Which
  trades count as closed, how a regime buckets, what window an excursion
  measures — each is a judgement, and journal shapes have already changed
  several times. Reprocessing forward is always possible; un-aggregating is
  not. **Compaction is not aggregation**: repacking the same rows into Parquet
  is lossless and rebuildable, and stays available as a read-performance option
  without touching the system of record.

---

## 9. RETENTION

| domain | retention |
|---|---|
| `raw/` | **never expires** |
| `derived/` | ages aggressively — regenerates on demand |
| `meta/` | never expires (small) |

No lifecycle rules are configured yet; storage-class transitions wait until
there is a query pattern to tune against. Size is not a constraint: all 29
boxes hold ~661 MB of `data/` combined, which is cents per month.

**The box-side scrub stays gated on CONFIRMED-PRESENT-IN-S3, never on age.**
Age-based deletion removes the local copy of exactly the record whose push
silently failed. Local retention must also exceed the reconciliation window.

**Correction to the original case for the scrub:** it was partly justified by
SPX sitting at 91% root while the fleet sits at 75%. That justification does
not hold. SPX's composition is identical to every other box; the difference is
a 2 GB `/swapfile` the others lack, almost certainly a deliberate OOM
mitigation. The scrub will not change SPX's disk picture. The warehouse stands
on durability and centralization.

---

## 10. OPEN ITEMS

1. **`feed_store` vs `OHLC` overlap.** Both carry candles. *Operator: retain
   everything `feed_store` collects, all intervals.* Whether `data/OHLC/` is
   then redundant, or is the authoritative daily record with `feed_store` as a
   rolling window, is undecided. `feed_store` is pruned (~240 1m bars), so it
   is a window, not an archive — which argues they are complementary.
2. **`entry_snapshot`** — does it already carry chain state at entry? Changes
   whether the chain↔trade join is built or verified.
3. **OHLC `volume` carries decimals** (`591522.792061`). Unusual for share
   volume. Understand before anyone sums it.
4. ~~**Cost ceiling.** Still unestimated~~ — **CLOSED, see §4a.** ~$2.82/month,
   88% of it PUT requests.
5. **`derived/` and `meta/` are specified but unbuilt.** Nothing writes to
   them yet.
6. **`raw/orb_state` has ZERO objects while `raw/orb_range` has 81.** Both go
   through the same capture, gated on `ESTABLISHED`. §7's claim that capturing
   on state rather than on a clock means no window can be missed was **too
   confident — a state can be short-lived too.** Needs a live check of what
   `orb_state.json`'s `state` field actually reads during RTH.
7. **Dedup happens twice with different rules** (§5a). One implementation
   should go.
8. **Poison is unfilterable once pushed** (§5a). The read-side rule is
   undecided.
9. **No lifecycle rule for noncurrent versions** (§4a) — the only line item
   that grows without anyone deciding.

---

## 11. THE CAUTION THIS DOCUMENT INHERITS

The chain archive was built 2026-07-23 and, as far as anyone knows, nothing
read it before the warehouse migration. A store makes collection cheap and
analysis merely *feel* imminent.

**Reports 40 (excursion, MFE/MAE) and 41 (trade breakdown) are the named
benchmarks.** Until one of them runs end-to-end against warehouse data, this
is a very well-organised pile.

### Where that stands, 2026-08-16

**The read path exists and is proven at the bundle level.**
`day_trader_pro/warehouse_reader.py` rebuilds `fleet_trades_<date>.json` from
S3, and `--all` reports **19 of 25 dates reproducing the control pipeline
exactly** — every date from 07-22 onward, including 08-14 at 153 trades and
net +5839.50 from 178 stored states. The six divergences all sit before that
boundary and are explained by §6a plus consolidate_trades' pre-v1.2 cumulative
bundles — except **07-15 and 07-21, where S3 holds MORE than the local bundle**,
which points the other way and is unexplained.

It deliberately **imports `_stats` and `_load_selection` from
`consolidate_trades` rather than reimplementing them.** If it computed its own
win-rate the comparison would test two *arithmetics* as well as two *sources*
and a mismatch would be ambiguous.

**But no REPORT has been run from the warehouse yet.** The bundle matching is
necessary and not sufficient: report 40 reads the per-box DBs directly rather
than the bundle, and report 41 globs every bundle, so neither has been
exercised. **The pile is now well-organised AND readable — and still unread.**
Dual-write stays until report OUTPUTS are diffed; `OT_EOD_PULL=0` is gated on
that and on nothing else.
