# docs/ — index (fork: options_trader_smc)

Eight files, by function. Start here. Updated 2026-08-18 at the fork: the
parent's ROADMAP/TRANSITION_ROADMAP/FILE_MAP/whitepaper stay in
options_trader_v3 where they govern; this fork's plan lives in BACKLOG.md and
its core's definitions in SMC_TRUTHS.md.

| file | read it when you want to know… |
|---|---|
| **SMC_TRUTHS.md** | The fork's entry core: structural vocabulary, label grammar, the FORMING/CONFIRMED/REVOKED lifecycle, priors to fit. |
| **MECHANICS.md** | How the bot decides, sizes, and exits — carried from the parent VERBATIM. Exits/execution are unchanged on this fork, so its exit catalogue and ORB model remain authoritative. Its REGIME_TRUTHS section describes the l2/v13 ROLLBACK engines, not the fork default. |
| **BACKLOG.md** | What still needs doing on the fork, with status and gates. |
| **WORKING_AGREEMENT.md** | How we work. Carried from the parent; see the fork-paths addendum at the end. |
| **VALIDATION.md** | How we validate — replay/calibration against tape (carried; the harnesses drive whatever engines are deployed, including this fork's). |
| **HISTORY.md** | Why salvaged things are the way they are (carried). Read before re-litigating a fix. |
| **WAREHOUSE_LAYOUT.md** | The S3 warehouse spec the box's pusher writes into (carried). |
| **README.md** (this file) | The router. |

**Adding docs: don't create a new file.** Work outstanding → BACKLOG. Completed
work → HISTORY. Behaviour → MECHANICS (salvaged) or SMC_TRUTHS (the core).
The sprawl the parent consolidated away grew one well-intentioned file at a
time — the rule carries to the fork.
