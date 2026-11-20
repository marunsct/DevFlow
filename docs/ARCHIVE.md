# Archive: where the old information is

Everything that is finished, superseded or purely historical lives under `docs/archive/`. Nothing in it is needed to
understand or operate the product today - [PRODUCT.md](PRODUCT.md) explains the product, [STATE.md](STATE.md) says where
it stands, [improvement-plan.md](improvement-plan.md) lists what is open, and [HANDOVER.md](HANDOVER.md) says how to run
and test it. Come here only to look up *why* something is the way it is, or what an old fix or review found.

Archived on 2026-11-20 when the documents were consolidated. Files are moved, never edited, so a reference in a code
comment (for example "monitoring-handover §8.3" or "improvement-plan.md §E1") is found in the file named below.

## Which file answers which question

| I want to know... | Read | What it holds |
|---|---|---|
| Why a fix or feature exists; what each `LF.n` / `RL` / `PH` / `CG` item did; the dated plan of record | [plans/improvement-plan-until-2026-11-20.md](archive/plans/improvement-plan-until-2026-11-20.md) | The full improvement plan: Appendix M (every improvement), the `LF.1`-`LF.1159` fix rows with their tests, the appendices for each initiative (efficiency audit, agent communication, discipline layer, prefix-cache discipline, customer stacks, internet lookups WL, workspace view WS), parts D-E (earlier plans merged) |
| How the loop was run day to day in October-November; what monitoring found; the run log | [operations/monitoring-handover-until-2026-11-20.md](archive/operations/monitoring-handover-until-2026-11-20.md) | The old testing and monitoring handbook with its run-by-run findings (§6, §8), pitfalls and disk hygiene |
| What a fix since 2026-11-20 measured and changed | [plans/fix-log.md](archive/plans/fix-log.md) | The append-only fix log (one row per fix, after the rows of the archived plan); searched by `loop.sh blind-spots` and the switch gate |
| The old operator handbook and the narrative of each session | [operations/HANDOVER-until-2026-11-20.md](archive/operations/HANDOVER-until-2026-11-20.md) | The old handover (rules, accounts, commands, "where it stands" by date, parked items) - the operator login line is removed here |
| Sections of the handbooks from before 2026-10-14 and the status file before 2026-11-17 | [operations/](archive/operations/) | `handover-before-2026-10-14.md`, `monitoring-before-2026-10-14.md`, `STATE-before-2026-11-17.md` |
| The product document as it was before the consolidation | [product/PRODUCT-until-2026-11-20.md](archive/product/PRODUCT-until-2026-11-20.md) | The 2026-10-04 product description refreshed 2026-10-19 |
| Why the architecture is shaped the way it is | [decisions/architecture-decisions.md](archive/decisions/architecture-decisions.md) | ADR-0001 to ADR-0005 and later: each decision, options, rationale (ADR-0005, the company-shaped pipeline, first) |
| The harness reviews and what they measured | [reviews/harness-review.md](archive/reviews/harness-review.md), [reviews/hr2/](archive/reviews/hr2/) | The first review (every capability measured and planned) and the second review's nine area reports |
| Launch readiness, sprint endings, test-fault attribution | [reviews/launch-review-2026-11-16.md](archive/reviews/launch-review-2026-11-16.md), [reviews/sprint-ending-2026-11-14.md](archive/reviews/sprint-ending-2026-11-14.md), [reviews/test-fault-attribution-2026-11-12.md](archive/reviews/test-fault-attribution-2026-11-12.md) | The launch plan (LR items), how a sprint should end, telling a test's fault from the product's |
| The evidence behind early decisions; all web research done for the harness | [reviews/review-findings.md](archive/reviews/review-findings.md), [reviews/research-findings.md](archive/reviews/research-findings.md) | The unified evidence log (2026-10-18 to 10-21) and the unified research findings |
| How many agents are needed; what each role earns; reasoning cost | [reviews/single-writer-review.md](archive/reviews/single-writer-review.md), [reviews/per-role-audit-2026-11-10.md](archive/reviews/per-role-audit-2026-11-10.md), [reviews/reasoning-cost-review-2026-11-11.md](archive/reviews/reasoning-cost-review-2026-11-11.md) | The single-writer review, the per-role audit of the 30 runs scored by 2026-11-10, the reasoning-cost design review |
| Designs that were planned and built (or dropped) | [plans/](archive/plans/) | `backing-services-plan.md` (Postgres/Redis/lifecycle), `object-storage-plan.md` (SeaweedFS), `scaffolding-plan.md` (SF), `work-batching.md` (WB), `agent-communication-feasibility.md` |
| The three colour themes of the UI, as screenshots | [ui/](archive/ui/) | Paper, graphite and contrast themes for the home, run, runs and settings pages |
| The history of the status board and of each run's product review | [../reports/](../reports/README.md) | Not archived in `docs/`: reports live in the `reports/` folder |

## Old reference -> where it is now

Code comments and tests still cite old section numbers. They are valid; find them here:

| Old reference | Now |
|---|---|
| `docs/improvement-plan.md` (any `§`, Appendix, `LF.n`, `PH.n`, `CG.n`, `RL.n`, `E1`, `R5`) | `docs/archive/plans/improvement-plan-until-2026-11-20.md` |
| `docs/monitoring-handover.md §n` (6.2 sandbox installs, 8.3 workspace after a run, 0.3.1 login) | `docs/archive/operations/monitoring-handover-until-2026-11-20.md` (the current mechanics are in [HANDOVER.md](HANDOVER.md)) |
| `docs/HANDOVER.md` old sections | `docs/archive/operations/HANDOVER-until-2026-11-20.md` |
| `docs/PRODUCT.md §n` as written before 2026-11-20 | `docs/archive/product/PRODUCT-until-2026-11-20.md` |
| `docs/work-batching.md`, `docs/backing-services-plan.md`, `docs/scaffolding-plan.md`, `docs/object-storage-plan.md` | `docs/archive/plans/` |
| `docs/architecture-decisions.md` | `docs/archive/decisions/architecture-decisions.md` |
| `docs/harness-review.md`, `docs/review-findings.md`, `docs/research-findings.md`, `docs/single-writer-review.md` | `docs/archive/reviews/` |
| `docs/reviews/hr2/...`, `docs/reviews/*.md` | `docs/archive/reviews/hr2/...`, `docs/archive/reviews/*.md` |

## What stays outside the archive

| File | Why it is not archived |
|---|---|
| [PRODUCT.md](PRODUCT.md) | The one document that explains the product |
| [STATE.md](STATE.md) | Current status; tests hold it under 150 lines and 16,000 characters |
| [improvement-plan.md](improvement-plan.md) | What is being measured and what is to be built |
| [HANDOVER.md](HANDOVER.md) | The handbook for agents that run and test the product; holds the operator login line the loop scripts read |
| [owner-decisions.md](owner-decisions.md) | The owner's decisions still in force; AGENTS.md sends agents here before they act on any of them |
| [measuring.md](measuring.md) | Generated by `scripts/loop/loop.sh measuring`: one row per switch with its runs on and off; a test holds it to the switch list |
