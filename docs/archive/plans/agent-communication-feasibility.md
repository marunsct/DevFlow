# Agent-to-agent communication in DevFlow: feasibility and expected gain

*2026-10-20 · status: RESEARCH + PLAN (no code changed) · plan IDs CM.1–CM.5 proposed, not yet in `improvement-plan.md`*

## 1. Verdict

| Form of communication | Valid for DevFlow? | Why |
|---|---|---|
| **Free-form peer messaging** (mailbox, agents chat or negotiate while working) | **No** | Measured to give ~no gain on shared codebases; adds near-serial calls on a one- or two-slot server; weaker models handle it worst |
| **Debate rounds** between specialists | **No** | Gains are almost entirely explained by voting; debate itself does not improve expected correctness |
| **Harness-mediated, typed communication** (a shared ledger of decisions, contracts and blockers that the harness writes and routes) | **Yes — the highest-value form** | ~11 of 15 documented failures were "agent B lacked a fact agent A or the harness already had" |
| **Bounded ask-the-owner questions** (a builder or fixer asks the specification's owner, capped) | **Yes, behind a flag** | +14 points measured on underspecified coding tasks, but needs a cap: one open model over-asked 8.7×/task |
| **Fact parity for reviewers** (a reviewer sees the facts the builder was given) | **Yes — cheapest win** | Zero extra model calls; it would have prevented LF.40, LF.42 and LF.90 |

**One line:** communication helps DevFlow when it moves *facts* between agents through the harness. It hurts when agents exchange *conversation* among themselves.

## 2. How DevFlow's agents communicate today (verified in code)

- **No direct channel.** Each role agent is built fresh per stage. It receives one prompt the harness assembles from `WorkflowGraphState`, and it returns one structured response. There is no mailbox, blackboard or ask tool. A clarification call was removed earlier (`workflow.py:3825`, "Initiative Q.4").
- **Specialist advisors** (`specialist_advice.py`):
  - they are consulted one at a time, before the specification;
  - none sees another's advice;
  - the architect must adopt or decline every numbered item.
- **Builders** (`specialists.py`) receive the following, all of it static:
  - the work order;
  - the specification slice (≤16k chars);
  - an ownership note;
  - the planned interfaces of sibling work orders.
- **Builders never see a sibling's actual output:** not its `decisions`, `blockers` or `risks`.
- **Those outputs have one reader,** the milestone reviewer (`milestone_reviewer.what_the_specialists_reported`), at the end of the milestone.
- **Parallel mode avoids conflict by construction rather than by talking:**
  - file-sharing tasks are held back;
  - writes to another work order's files are refused;
  - sandbox commands are serialised.
  - Conflicts are found afterwards, at the CI gate, code review and the test round.
- **The deployment constraint is one or two model slots.** The owner's llama.cpp server had one slot with ~126–190k context (`PRODUCT.md:388`, `HANDOVER.md:525`); EF.2 (2026-10-20) reports 2 slots, but linear mode still measured 1.0× overlap, and fan-out was measured at 1.0–1.3× (Initiative AB). In practice every extra message is close to an extra serial call.
- **Budgets are already saturated:**
  - reasoning is 59–98% of output;
  - replies are lost at the ~30k output cap;
  - a planner's first request reached 223k chars.
- **Plan status:** Pillar 9, the "Curated Context Bus", was evaluated as GOOD and is still **NOT BUILT** (`improvement-plan.md:3841`, `:4109`).

### The documented failures are mostly missing-fact failures

| ID | What happened | Who had the fact | Outcome |
|---|---|---|---|
| LF.40 | Spec planned real-PostgreSQL types; every test runs on the file DB | Harness/setup | Run cancelled |
| LF.42 | Architecture reviewer, never told the file-DB fallback, demanded `DATABASE_URL` | Architect's prompt | Run cancelled |
| LF.90 | Security reviewer asked for `SECRET_KEY` from env; `auth.py` raised when unset | Builders' environment contract | Two fixes reverted |
| LF.25 | Architect didn't know the scaffold layout → two front ends | Scaffold | Fixer copied between them |
| LF.24 | Fixers and the dispute got the spec's headings only | Specification | Contract mismatches |
| (spec drift) | Service used `username`, spec said `full_name`; tests, disputes and fixes argued | Specification | Rework loops |
| (unread outputs) | One builder removed ES exports; the testing builder's blocker said so; read by nobody until the review | Sibling builder | Suite broken |
| LF.80/82 | Two fixers in turn "fixed" the same drift; neither knew the other's attempt; one broke 102 tests | Previous fixer | Regression |
| LF.44 | Fixers told "build failed", not why | CI gate | Wasted rounds |
| (scope) | Builders not told which locked tests were later sprints' | Sprint plan | Over-build, then deletion |
| (advice) | Advice adopted, then contradicted by the page check | Advisor and page check | Carried as owed work |

Each was fixed one at a time by piping the fact into the second agent's prompt. That is evidence for a **general** fact-routing mechanism, not for agents talking.

## 3. What the research says (2025–2026)

1. **Communication alone doesn't fix multi-agent failures.**
   - MAST (NeurIPS 2025) classified failures in 7 MAS frameworks. Inter-agent misalignment was about a third of them.
   - The authors state that communication-protocol fixes are often insufficient, because the root cause is agents failing to model what others need.
   - The largest single gain came from adding **objective-level verification: +15.6%** on ChatDev's ProgramDev. Role or topology fixes gave +9.4%.
2. **Coding agents that can message each other don't benefit.**
   - CooperBench (Stanford, 2026) covers 650+ tasks in four languages, run by two agents with real-time messaging.
   - Pairs lost nearly half the capability of a single agent.
   - Messaging had almost no effect: agents sent low-value status updates, ignored direct questions and overwrote code after acknowledging warnings.
3. **Sequential, tool-heavy work is where coordination hurts most.**
   - Google Research and MIT (Jan 2026) tested 180 configurations.
   - Every multi-agent variant degraded sequential planning by 39–70%.
   - Tool-heavy tasks pay a disproportionate overhead.
   - Centralised (hub) coordination contained error amplification at 4.4×, against 17.2× for independent agents.
   - Coordination gives diminishing or negative returns once the single-agent baseline passes about 45%.
   - DevFlow's pipeline is mostly sequential and tool-heavy.
4. **Structured documents beat dialogue.**
   - MetaGPT's design passes structured documents through a publish-subscribe pool instead of free chat, explicitly to avoid "idle chatter" and telephone-game distortion.
   - Its role ablation shows revisions falling from 10 to 2.5 as roles are added.
   - DevFlow already follows this pattern.
5. **Debate ≈ voting.** Majority voting explains most of multi-agent debate's gains, and debate itself is a martingale over agents' beliefs (Choi et al., NeurIPS 2025).
6. **A blackboard with a controller works and saves tokens.** In an LLM blackboard system, removing the control unit raised token cost about 3.7× for a similar score. This supports *harness-controlled* routing over free broadcast. Caveat: the study did not test code writing or tool use.
7. **What frontier products ship:**
   - **Cognition (Apr 2026):** writes stay single-threaded; reviewers with clean context and "smart friend" escalation work; parallel-writer swarms do not. How agents pass discoveries without overloading each other is called the main open problem.
   - **Anthropic's research system:** subagents talk only through the lead. Most coding tasks are a poor fit for multi-agent work. It costs about 15× chat tokens.
   - **Claude Code agent teams (Feb 2026, experimental):** do have a mailbox. Anthropic's guidance warns against using them for sequential work and same-file edits, at 3–5× token cost.
8. **Asking questions does pay off, when bounded.**
   - "Ask or Assume" (2026) used underspecified SWE-bench Verified.
   - A separate intent check that triggers questions lifted resolve rate by about +14 points for both Claude Sonnet 4.5 and Kimi K2.6, close to the fully specified ceiling.
   - Kimi asked 8.7 questions per task, so the trigger needs a cap.

## 4. Recommended design (harness-mediated, not peer-to-peer)

All items are flag-gated and measured per ADR-0010. IDs are proposals for the plan.

### CM.1 Fact parity for every judging stage — P0
- **Change:** a reviewer, dispute or acceptance stage receives the same environment contract, data-store facts, scaffold layout and sprint scope as the builder whose work it judges.
- **How:** implement this as one function both prompts call, plus a parity test that fails when the builder's fact blocks and the reviewer's diverge.
- **Cost:** 0 model calls, a few hundred tokens per prompt.
- **Evidence:** LF.40, LF.42, LF.90 (two cancelled runs, two reverted fixes).

### CM.2 Typed decision-and-contract ledger (builds Pillar 9) — P1
- **What it is:** a harness-owned file with typed, versioned entries — `requirement`, `interface_contract`, `decision`, `blocker`, `known_trap` — each with id, source, roles and version.
- **Writers:** the harness only, from structured outputs that already exist.
  - Spec API reference and locked suite → `interface_contract`.
  - Builders' `SpecialistOutput.decisions` that change an interface → `decision`.
  - `blockers` → `blocker`, addressed to the owning role.
  - A fixer's attempt and outcome → `decision` on that defect.
- **Readers:** each stage gets its role's slice under a hard character budget, ranked and with dropped entries named. Routing rules:
  - builders and fixers see open blockers addressed to them and decisions that touch their files;
  - a later fixer sees earlier attempts on the same defect (LF.80/82).
- **Not included:** reasoning, prose notes, model-written memory. Pillar 9 already rejected these because they drift and poison weaker models.
- **Cost:** 0 extra model calls; prompt growth capped (start at 4k chars per stage).
- **Overlaps:** EF.11 (builders shown the locked interface-contract lines) is the `interface_contract` slice of this ledger; build it as the first entry type. BJ's per-request input budget applies.
- **Evidence:** unread outputs, LF.80/82, spec drift, LF.24, the scope failure.

### CM.3 Mid-milestone blocker routing — P1
- **Linear mode:** a builder's `blocker` naming another work order's file or interface is routed to that work order's next visit (via CM.2), instead of waiting for the milestone review.
- **Parallel mode:** routing happens at the gather join. A conflicting `decision` (two work orders changing one interface) becomes a defect immediately, before the CI gate.
- **Cost:** 0 calls; it may save a whole fix round.
- **Overlaps:** EF.6 (a later work order adding an export or alias to a finished work order's file). CM.3 routes the need to the owner; EF.6 lets the later work order make it in linear mode. They are complementary: do EF.6 first, CM.3 covers parallel mode.

### CM.4 Bounded "ask the specification" tool — P2, behind a flag
- **What it is:** a builder or fixer may call `ask_specification(question)`.
  1. The harness first answers by retrieval from the spec, the ledger and the locked suite. That costs 0 model calls and resolves most questions about names and shapes.
  2. Only when retrieval finds nothing does one call go to the architect role. It has read-only context and must answer within the specification.
- **Persistence:** the answer is written to the ledger as a `decision`, so the question is asked once per run.
- **Caps:** at most 2 questions per work order and 1 per fix, a per-run ceiling, and the counters live in `stage_memory`.
- **Why behind a flag:** the evidence for asking is strong (+14 points), but weaker models over-ask. The owner's local model must be measured first.

### CM.5 Keep reviewers context-clean — ADOPTED principle
Reviewers keep receiving artefacts and facts, never the builder's reasoning or transcript. Clean context is a measured strength (Cognition's reviewer loop). CM.1 adds facts, not history.

### Rejected
- **Peer mailbox:** CooperBench measured no gain, it costs near-serial calls on one or two slots, and it removes harness control.
- **Specialist debate or negotiation rounds:** debate ≈ voting.
- **Broadcasting builders' reasoning:** it was already measured and rejected in Pillar 9 and the carry-over work.
- **Letting parallel builders coordinate edits by message:** the write guards and file-holdback already do this deterministically and cheaper.

## 5. Expected gain (hypotheses, to be measured)

| Item | Should reduce | Extra model calls | Prompt cost |
|---|---|---|---|
| CM.1 | Reviewer findings that contradict the environment; cancelled runs and reverted fixes of the LF.40/42/90 class | 0 | +0.5–1k chars per judging stage |
| CM.2 | Contract-mismatch defects; repeated fixes of one defect; spec-vs-code naming drift | 0 | ≤4k chars per stage (capped) |
| CM.3 | Fix rounds per milestone; time from blocker to fix | 0 | small |
| CM.4 | Builder guesses on underspecified points | ≤2 per work order, only when retrieval misses | small |

- **Efficiency:** CM.1–CM.3 add no model calls, so on the owner's local server they should be close to free in wall-clock time. The saving comes from avoided rework: each avoided fix round is one or more full specialist calls plus a CI gate and test round.
- **Quality:** the target is the failure class that cancelled runs, not polish.
- **What to measure (same brief, ≥3 runs per arm, flag on vs off):**
  - contract-mismatch defects per milestone;
  - fixes reverted for breaking something;
  - fix attempts per defect;
  - reviewer findings later withdrawn or contradicted by the environment;
  - wall-clock per accepted criterion;
  - tokens per accepted criterion;
  - for CM.4: questions per work order and the share answered by retrieval.
- **Kill criteria:** any item that raises tokens per accepted criterion by more than 5% without lowering at least one defect metric is turned off.

## 6. Implementation order and effort

| Step | Work | Effort |
|---|---|---|
| 1 | CM.1 fact-parity function and parity test | ½ day |
| 2 | CM.2 ledger schema, harness writers from existing structured outputs, role slicing, budget and drop note, flag | 2 days |
| 3 | CM.3 blocker and decision routing (linear visit and parallel gather) | 1 day |
| 4 | A/B on one benchmark brief (CM.1–3), then a decision | per loop cadence |
| 5 | CM.4 retrieval-first ask tool with caps, then A/B on the owner's local model | 1½ days + A/B |

Each step follows the repo rules:
- a test proven to fail on the old code;
- the banned-words test for any new prompt rule;
- technology-agnostic code, with stack facts only in packs;
- plan and Appendix M rows updated in the same commit.

## Sources
- MAST, "Why Do Multi-Agent LLM Systems Fail?" — https://arxiv.org/html/2503.13657v3
- Google Research, "Towards a science of scaling agent systems" (28 Jan 2026) — https://research.google/blog/towards-a-science-of-scaling-agent-systems-when-and-why-agent-systems-work/ ; paper https://arxiv.org/html/2512.08296v2
- Stanford HAI, "AI coding agents fail at teamwork" (CooperBench, 1 Jun 2026) — https://hai.stanford.edu/news/ai-coding-agents-fail-at-teamwork
- Cognition, "Multi-Agents: What's Actually Working" (22 Apr 2026) — https://cognition.com/blog/multi-agents-working ; "Don't Build Multi-Agents" — https://cognition.com/blog/dont-build-multi-agents
- Anthropic, "How we built our multi-agent research system" — https://www.anthropic.com/engineering/multi-agent-research-system
- Claude Code agent teams overview — https://www.morphllm.com/claude-code-agent-teams
- MetaGPT — https://arxiv.org/pdf/2308.00352
- "Debate or Vote" — https://arxiv.org/abs/2508.17536v1
- LLM blackboard MAS — https://arxiv.org/html/2507.01701v1
- "Ask or Assume? Uncertainty-Aware Clarification-Seeking in Coding Agents" — https://www.alphaxiv.org/abs/2603.26233
- DevFlow code/docs read: `graph/workflow.py`, `agents/specialists.py`, `specialist_advice.py`, `advice_review.py`, `milestone_reviewer.py`, `suite_dispute.py`, `graph/escalation.py`, `tools/repository.py`, `context_budget.py`, `docs/improvement-plan.md` (Pillar 9, Initiative AB, LF rows), `docs/monitoring-handover.md`, `docs/PRODUCT.md`, `docs/HANDOVER.md`
