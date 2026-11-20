# Documentation map

Six documents, each with one job. Read them in this order.

| Document | Job | Read it when |
|---|---|---|
| [STATE.md](STATE.md) | **Current status**: what is live, what is running, the last runs, the next action. Updated in every commit that changes any of those. | Always first. Ask it, not the agent, "what is the status?" |
| [PRODUCT.md](PRODUCT.md) | **The product, completely**: vision, architecture, pipeline, agents, stacks, verification, server, UI, deployment, security, how it is measured and built. | You need to understand how the product works or is built. Updated in the same commit as any change to how it works. |
| [improvement-plan.md](improvement-plan.md) | **What is open**: features being measured, items to build in order, items waiting on the owner, parked and rejected ideas. | Choosing what to build next. Finished work leaves this file. |
| [HANDOVER.md](HANDOVER.md) | **How to run, test, audit and deploy**: the rules, the loop, every command, pitfalls. For the agents that test and build. | Before you start a run, run a suite or deploy. |
| [owner-decisions.md](owner-decisions.md) | **Decisions of the owner still in force**, with status and trigger. | Before acting on any subject it lists. |
| [ARCHIVE.md](ARCHIVE.md) | **Where the old information is**: every archived file, what it answers, and where an old section reference now lives. | You need the history of a decision or fix. |

Also here: [measuring.md](measuring.md) (generated: one row per switch, with its runs on and off) and `archive/` (history,
never needed to operate the product).

**Reports** (audits, product reviews, research, the status-board history) are not documents: they are dated files in the
[reports/](../reports/README.md) folder at the root of the repository.

## Rules for keeping these true

1. A change that alters what is live, running or next updates `STATE.md` in the same commit.
2. A change that alters how the product works or is built updates `PRODUCT.md` in the same commit.
3. A finished item leaves `improvement-plan.md`; its history is in git and, if worth keeping, in `archive/`.
4. Nothing is left uncommitted at the end of a piece of work.
