"""
shadow/ — OBSERVE-ONLY conviction-scoring subsystem.
v1.0 — 2026-07-09 — initial release.

ISOLATION CONTRACT (non-negotiable):
  - This package places NO orders and imports NOTHING from execution/, risk/,
    strategy/, or notifications/. It must never gain such an import.
  - It runs in its OWN process (shadow-observer.service), so it shares zero
    in-memory state with optionsbot.service. It reads the same market data
    source (data_cache -> market_data) and the same analysis engines
    (volatility/trend/structure/liquidity) as fresh instances in its own
    process. Engine .analyze() calls return new state objects.
  - It writes ONLY to data/shadow/<YYYY-MM-DD>/<SYMBOL>.jsonl (gitignored)
    and its own journal output. It never opens trades.db (the EOD comparator
    opens it strictly read-only, mode=ro).
  - No file on the live execution path is modified by this subsystem.
"""
