"""
strategy/ict/ — the ICT setup suite (seven setups, ranked, scored). v1.0
v1.0 — 2026-08-18 — INITIAL. Ownership per WORKING_AGREEMENT §7: this
package's files belong to the setup suite; smc/ and main.py belong to the
core. The suite consumes ONE surface — strategy/ict/context.ICTContext —
and asks for what the core owes via docs/ICT_CORE_SPEC.md, never by
reaching into internals.

Entry point for main.py:  strategy.ict.dispatch.ict_dispatch
First-light surface:      strategy.ict.dispatch.evaluate_all
Context builder (interim): strategy.ict.context.build_context
"""

from strategy.ict.context import ICTContext, build_context           # noqa: F401
from strategy.ict.dispatch import ict_dispatch, evaluate_all, RANKED  # noqa: F401
from strategy.ict.scoring import SetupScore, size_fraction            # noqa: F401
