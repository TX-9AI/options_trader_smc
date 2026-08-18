# Options Trader SMC — Vertigo Capital
### Fork of options_trader_v3 · candidate box: **QQQ** · opened 2026-08-18

Automated 0-DTE / short-dated options day-trading box on the TastyTrade/DXFeed
stream. **This fork replaces the ENTRY-side quantity** — the confirmatory
Layer-1/Layer-2 conviction that the 2026-08-17 retool verdict retired — **with
an SMC/ICT structural core** that reads position and structure at decision
time: market structure (BOS/CHoCH), the dealing range and price's position in
it (premium/discount), draw on liquidity, displacement, unmitigated FVGs /
order blocks, live liquidity raids, and killzones.

**What is deliberately unchanged:** the exit stack (the measured winners —
confirmation is CORRECT at exits), execution (fill-confirmed entries/exits,
limit ladder, broker reconcile), risk, data layer, notifications, the S3
pusher, and every strategy's plumbing. The retool moves one boundary — the
quantity that decides entries — and must not touch exits.

## The core (smc/)

| file | role |
|---|---|
| `smc/primitives.py` | Pure functions: dealing range + premium/discount, displacement (SD-normalized), BOS/CHoCH classification, draw-on-liquidity, live raid detection, inducement, unmitigated-FVG filter, killzones. Reuses the salvaged engines' objects (SwingPoint, FairValueGap, OrderBlock, LiquidityPool/Sweep) — it composes, it does not re-derive. |
| `smc/smc_engine.py` | Stateful composer: per-TF structure state (its own swing-memory ratchet), the RegimeState-compatible label + STRUCTURAL confidence, and the anticipatory setup lifecycle **FORMING → CONFIRMED → REVOKED**, journaled on every transition (`smc_setup`). State persists to `data/smc_state.json`; fully reconstructible from tape. |

**Engine selection:** `OT_REGIME_ENGINE` — fork default **smc**; `l2` / `v13`
roll the box back to the parent repo's engines with no code change. Under
`smc`, the v1.3 classifier still runs and populates RegimeState's rich fields;
only `primary_regime`/`conviction` are overridden — the same boundary L2.5
overrode. Provenance: `[SMC c=..]` log tag, `engine="SMC"` on regime_log rows.

**The revocation gate** (permissive-until-disqualified, operator 2026-08-17):
entries stand UNLESS the active setup was REVOKED against the signal's
direction — acceptance through the setup's invalidation level, or a CHoCH
against the thesis that POST-DATES the setup. One gate at the post-dispatch
choke point (the afternoon-debit precedent); refused signals journal as
`gate_block:smc_revoked`. `OT_SMC_REVOKE_GATES=0` disarms the gate while
detection and journaling continue.

**Label mapping** (full grammar in `docs/SMC_TRUTHS.md`): TRENDING_BULL/BEAR ←
directional structure + BOS with HTF alignment or CONFIRM-tier displacement ·
SWEEP_REVERSAL ← confirmed sweep-reclaim + agreeing CHoCH · BREAKOUT_VOLATILE ←
displacement through external liquidity with acceptance · RANGING /
COMPRESSION ← inside the dealing range, no committed displacement, split on
the width axis. Existing strategy gates keep working unmodified.

## Documentation map
`docs/README.md` routes by question · behaviour → `docs/MECHANICS.md` (carried
from the parent — exits/execution are unchanged and its exit catalogue remains
authoritative) · the new core → `docs/SMC_TRUTHS.md` · work outstanding →
`docs/BACKLOG.md` · operating rules → `docs/WORKING_AGREEMENT.md` (carried,
with the fork-paths addendum) · history → `docs/HISTORY.md` · validation →
`docs/VALIDATION.md` · S3 → `docs/WAREHOUSE_LAYOUT.md`.

## Deployment
Same install chain as the parent (install.sh → setup_ec2.sh; candle-feed owns
the box's only DXFeed stream). **`config.py` must always default to
`PAPER_TRADING = True`.** **The candidate is the existing QQQ box, converted** — not a new
instance. That box already carries its IAM role, its S3 push timer, its
feed_store candle depth and a full legacy trade history under the old core,
and QQQ is already configured fleet-wide (strike increment 1, penny class,
an ALWAYS_ON daily trader). SPX remains the legacy daily anchor for the
head-to-head. Conversion steps and their ordering: BACKLOG F.2.

## Proof gates on this fork
`PYTHONPATH=. python3 tests/test_smc_core.py` — behavioral suite (anticipation,
confirmation, revocation decision, labels, deliberate-failure check).
`PYTHONPATH=. python3 tests/test_engine_provenance.py` — F.2a provenance
(writes rows, reads `regime_engine` back, covers the ALTER-TABLE path).
`PYTHONPATH=. python3 tests/canary_smc_core.py` — wiring canary (definition-
shaped per WA §20; calls the decision function per WA §21). The parent's
`check_versions.sh` still verifies every salvaged file; SMC coverage lives in
the canary rather than in new grep lines there.

## Security
Credentials live in the systemd environment only — never in source. Unchanged
from the parent.
