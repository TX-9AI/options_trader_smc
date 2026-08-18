# SMC_TRUTHS.md — the structural core's definitional truth audit
**v1.0 — 2026-08-18 — fork: options_trader_smc · candidate QQQ. All
thresholds are STATED PRIORS.** Companion to `smc/primitives.py` +
`smc/smc_engine.py` v1.0. This is the fork's counterpart to the parent's
REGIME_TRUTHS (preserved in `docs/MECHANICS.md`): it defines what the tape IS,
per state, in decision-time structural terms — never in terms of trades,
premium, or outcomes (the core invariant is unchanged: trade outcomes never
feed back into classification).

## 0. What is different from the parent core, in one table

| axis | parent (L1/L2) | this core (SMC) |
|---|---|---|
| the quantity | persistence of indicator agreement (leaky argmax) | position + structure at this instant |
| lag class | confirmatory by assembly (the retool finding) | structural; anticipation via the setup lifecycle |
| confidence | how long winning evidence has persisted | fraction of structural conditions the label holds |
| indecision | low conviction on a best-fit label | honest RANGING-family label + a NONE setup |
| the gate | (never built — L3 0%) | REVOCATION: permission stands until disqualified |

## 1. Vocabulary (all decision-time, all readable at HEAD)

- **Dealing range** — the most recent confirmed swing high above price + swing
  low below it (5m anchor). External liquidity rests beyond both ends.
  **position_pct** ∈ [0,1] inside it; **sentinel −1.0 = no range** (the STR.2
  rule: a default that is also a legal reading poisons every probe).
- **Zone** — PREMIUM ≥ 0.62 · DISCOUNT ≤ 0.38 · EQUILIBRIUM ±0.05 of 0.50 ·
  MID otherwise · NONE on the sentinel. Priors, to be fitted.
- **Displacement** — a closed 1m candle whose range ≥ 1.75 rolling SDs
  (AWARE) / ≥ 2.0 (CONFIRM) — the TC.4 impulse yardstick as a pure function.
  Its wick extreme is the **origin**: durable floor (bull) / ceiling (bear).
- **BOS / CHoCH** — a 1m CLOSE crossing an unbroken remembered swing level:
  with the committed structure direction = BOS; against it = CHoCH.
  Close-based, never wick-based (a wick is a raid; a close is acceptance —
  the same rule the ORB stop and tcs_floor_durability use). Edge-triggered:
  a break prints exactly once, on the crossing bar. The engine OWNS its swing
  memory (bounded ratchet) because the analyzer's swing sets are recomputed
  with a length-derived lookback and levels vanish as frames grow — the
  pitchfork whitepaper's §4.1 failure mode, avoided by construction.
- **Draw on liquidity** — nearest UNSWEPT pool above and below (named or
  equal-H/L; external liquidity is external regardless of its name).
- **Inducement** — a minor unswept pool BETWEEN price and the dominant draw.
  Context only, weight-0: the A2 drift study is the standing warning against
  claiming forward content from position alone.
- **Raid (live)** — the current closed bar's WICK pierced an unswept pool
  while its CLOSE stayed inside — the purge in progress, BEFORE the mapper's
  reclaim confirmation. This is where anticipation lives.
- **POI** — an unmitigated in-favor FVG (the analyzer's own objects; order
  blocks reserved for the same slot, BACKLOG S.4).
- **Killzones** — names for the existing session windows (NY_AM 09:30–11:00 ·
  NY_LUNCH · NY_PM · WINDDOWN ≥14:00): one clock, not a second one to drift.

## 2. Label grammar (RegimeState-compatible; evaluation order is the order below)

| label | necessary (all) | corroborators (confidence = fraction held) |
|---|---|---|
| SWEEP_REVERSAL | confirmed sweep-reclaim (mapper, age ≤ 6, not invalidated) AND last shift is CHoCH | shift direction printed · swept level is NAMED |
| BREAKOUT_VOLATILE | CONFIRM displacement AND closes_beyond ≥ 2 through the level AND not reclaimed | SD ≥ 2.5 · last shift BOS |
| TRENDING_BULL/BEAR | committed 5m structure direction AND last shift BOS AND (15m aligned **or** CONFIRM displacement agreeing) | alignment · displacement · healthy position (a bull trend is bought in DISCOUNT/EQ/MID, not PREMIUM) |
| COMPRESSION | inside the dealing range AND squeeze (vol_state SQUEEZE, not expanding) | near equilibrium |
| RANGING | the residual honest state: inside the range, no committed displacement, no directional BOS | — |

**The load-bearing necessary condition:** a shift with NEITHER HTF alignment
NOR CONFIRM-tier displacement behind it is chop crossing a minor swing, not a
trend — without that gate every range rotation that clips a swing point would
print TRENDING, which is the parent core's A2 failure worn structurally.

## 3. The setup lifecycle (the anticipatory half)

```
NONE ──raid pierces a pool──────────────► FORMING (thesis = fade the raid)
NONE ──price within 0.75·ATR of a POI,
        structure directional───────────► FORMING (thesis = structure dir)
FORMING(raid) ──mapper reclaim ≤3 bars──► CONFIRMED
FORMING(poi)  ──POI tapped + close back─► CONFIRMED
FORMING|CONFIRMED ──acceptance through the invalidation,
        or CHoCH against the thesis that POST-DATES the setup──► REVOKED
REVOKED ──a fresh formation──────────────► FORMING   (not a permanent lockout)
```

**Revocation semantics are load-bearing** (operator, 2026-08-17): the signal
REVOKES rather than GRANTS, so it may take the bars it needs and costs nothing
until it fires. The shift-postdates-setup rule exists because a raid IS a move
against the coming thesis — counting the raid bar's own break as the
disqualifier revoked every setup one bar after it formed (caught by the
behavioral suite before it ever ran live).

## 4. What gates, what only journals

- The LABEL gates exactly what the old label gated (strategy regime gates,
  exit regime-flips) — same boundary, new quantity.
- The SETUP lifecycle journals every transition (`smc_setup`). Its only gate
  is the REVOCATION check at the entry choke point (`gate_block:smc_revoked`
  on refusal), flag `OT_SMC_REVOKE_GATES`.
- CONFIRMED does **not** admit or size anything yet. Sizing on any structural
  score waits for the parent transition roadmap's Phase-2 preconditions
  (separation with direction · selection-clean · window-stable · marginal-ROI
  placement · early-tolerant payoff). Nothing here is exempt from them.

## 5. Priors to fit (from the fork's own journal, never one session)

| knob | prior | fit from |
|---|---|---|
| DISPLACEMENT_SD_AWARE / CONFIRM | 1.75 / 2.0 | journaled displacement_sd distribution vs forward drift |
| PREMIUM_FLOOR / DISCOUNT_CEIL | 0.62 / 0.38 | position_pct at entries vs nf/ok split |
| OT_SMC_POI_APPROACH_ATR | 0.75 | FORMING→CONFIRMED conversion by approach distance |
| OT_SMC_ACCEPT_CLOSES | 2 | acceptance-vs-reclaim survival (mirrors SWEEP_ACCEPT_CLOSES) |
| sweep-age ceiling (label) | 6 bars | reclaim follow-through decay |
| swing-memory bound | 40/side | level-book depth vs break relevance |

Circularity guard unchanged: fit sessions ≠ acceptance sessions.
