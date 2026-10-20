# Research findings (unified)

> Consolidated 2026-10-19. Every piece of web research done for DevFlow's
> improvement work is here, newest first, and each part opens with a table
> linking its findings to items in `docs/improvement-plan.md`. Review findings
> (what the harness and its runs showed) are in `docs/review-findings.md`.
> Section numbers from the original files (§8, §11, §13.6, §15.1) are kept
> in the headings, so older references still resolve.

## Index

| Part | Topic | Date | Main plan items |
|---|---|---|---|
| [R8](#r8) | MinIO replacement: open-source S3-compatible storage | 2026-10-20 | [OS](improvement-plan.md#plan-os) |
| [R7](#r7) | Agent-to-agent communication in multi-agent systems | 2026-10-20 | [CM](improvement-plan.md#plan-cm) |
| [R1](#r1) | Frontier coding-agent harnesses and local-model techniques | 2026-10-19 | [AX](improvement-plan.md#plan-ax), [AY](improvement-plan.md#plan-ay), [AZ](improvement-plan.md#plan-az), [BA](improvement-plan.md#plan-ba), [BH](improvement-plan.md#plan-bh), [BJ](improvement-plan.md#plan-bj) |
| [R2](#r2) | Research digest R1–R21 (long-running harnesses, local serving, agent UX) | 2026-10-18 | [W](improvement-plan.md#plan-w), [X](improvement-plan.md#plan-x), [Y](improvement-plan.md#plan-y), [Z](improvement-plan.md#plan-z), [AA](improvement-plan.md#plan-aa), [AI](improvement-plan.md#plan-ai) |
| [R3](#r3) | Frontier harness research T1–T6 | 2026-10-18 | [M](improvement-plan.md#plan-m), [O](improvement-plan.md#plan-o), [Z](improvement-plan.md#plan-z), [L.7](improvement-plan.md#plan-l-7) |
| [R4](#r4) | Local-LLM research §8.1–8.7 | 2026-10-17/18 | [M](improvement-plan.md#plan-m), [N](improvement-plan.md#plan-n), [O](improvement-plan.md#plan-o), [S](improvement-plan.md#plan-s), [Q](improvement-plan.md#plan-q) |
| [R5](#r5) | UI/UX research-backed opportunities | 2026-10-18 | [Part 4](improvement-plan.md#plan-part-4), [Part 15](improvement-plan.md#plan-part-15), [Part 19](improvement-plan.md#plan-part-19) |
| [R6](#r6) | Earlier comparisons with other harnesses | 2026-10-04/09 | [E1](improvement-plan.md#plan-e1), [E2](improvement-plan.md#plan-e2) |

---

<a id="r8"></a>
## Part R8 — MinIO replacement: open-source S3-compatible object storage (2026-10-20, session 5)

Plan items: [OS](improvement-plan.md#plan-os). Full comparison: [`object-storage-plan.md`](object-storage-plan.md).

| Finding | Evidence | Plan |
|---|---|---|
| MinIO CE is no longer a viable dependency: images and binaries stopped Oct 2025, maintenance mode Dec 2025, repo archived Feb/Apr 2026; AIStor Free is commercial and single-node | [glukhov.org](https://glukhov.org/data-infrastructure/object-storage/minio-dead/), [WZ-IT (updated 2026-10-12)](https://wz-it.com/en/blog/minio-successor-s3-storage-comparison/) | OS.2 removes it |
| SeaweedFS: Apache-2.0, since 2015, release 4.45 on 2026-08-31; `weed mini` gives a single-process S3 with credentials and a pre-created bucket, documented for small production setups; S3 coverage includes versioning, object lock, bucket policy, presigned, multipart | [repo](https://github.com/seaweedfs/seaweedfs), [releases](https://github.com/seaweedfs/seaweedfs/releases), [weed mini](https://github.com/seaweedfs/seaweedfs/wiki/Quick-Start-with-weed-mini), [S3 API](https://github.com/seaweedfs/seaweedfs/wiki/Amazon-S3-API) | OS.0–OS.1 |
| RustFS: Apache-2.0, MinIO-like UX, but 1.0 GA only on 2026-09-16; critical advisories CVE-2025-68926 (hard-coded gRPC token, 9.8) and CVE-2026-62378 (console stored XSS leaking keys, 9.0) | [Linuxiac](https://linuxiac.com/rustfs-1-0-s3-compatible-object-storage-reaches-ga/), [GitLab advisory](https://advisories.gitlab.com/cargo/rustfs/CVE-2025-68926/), [Halo](https://cve.halosecurity.com/cve-advisory/cve-2026-62378-rustfs-console-stored-xss-exposes-credentials) | OS.8 re-evaluation |
| Garage: AGPL-3.0; no versioning, object lock or bucket policies; partial lifecycle | [S3 compatibility](https://garagehq.deuxfleurs.fr/documentation/reference-manual/s3-compatibility/) | not chosen |
| Ceph RGW: mature but disproportionate for one host | [WZ-IT](https://wz-it.com/en/blog/minio-successor-s3-storage-comparison/) | not chosen |

<a id="r7"></a>
## Part R7 — Agent-to-agent communication in multi-agent systems (2026-10-20, session 5)

Plan items: [CM](improvement-plan.md#plan-cm). Full assessment: [`agent-communication-feasibility.md`](agent-communication-feasibility.md).

| Finding | Evidence | Plan |
|---|---|---|
| Inter-agent misalignment is about a third of multi-agent failures, and communication-protocol fixes alone are insufficient; the largest single gain was objective-level verification (+15.6% on ProgramDev), and role or topology fixes gave +9.4% | MAST, NeurIPS 2025 — [arXiv 2503.13657](https://arxiv.org/html/2503.13657v3) | CM.1, CM.2 (facts, not chat) |
| Two coding agents with real-time messaging lost nearly half a single agent's capability; messaging had almost no effect (unanswered questions, broken commitments, overwrites after warnings) | CooperBench — [Stanford HAI, 2026-06-01](https://hai.stanford.edu/news/ai-coding-agents-fail-at-teamwork) | peer mailbox rejected |
| Every multi-agent variant degraded sequential planning 39–70%; tool-heavy tasks pay a disproportionate overhead; centralised control contains error amplification (4.4× vs 17.2×); diminishing returns past ~45% single-agent baseline | Google Research/MIT, 2026-01-28 — [blog](https://research.google/blog/towards-a-science-of-scaling-agent-systems-when-and-why-agent-systems-work/), [arXiv 2512.08296](https://arxiv.org/html/2512.08296v2) | harness stays the hub |
| Structured documents through a publish-subscribe pool beat free dialogue ("idle chatter", telephone-game distortion); revisions fall as roles are added | MetaGPT — [arXiv 2308.00352](https://arxiv.org/pdf/2308.00352) | CM.2 |
| Majority voting explains most of multi-agent debate's gains; debate is a martingale over beliefs | "Debate or Vote" — [arXiv 2508.17536](https://arxiv.org/abs/2508.17536v1) | debate rejected |
| A blackboard with a controller selecting who acts: removing the controller raised tokens ≈3.7× for a similar score (not tested on code or tools) | LbMAS — [arXiv 2507.01701](https://arxiv.org/html/2507.01701v1) | CM.2 routing is harness-controlled |
| Frontier practice: writes single-threaded; clean-context reviewers and escalation to a stronger model work; parallel-writer swarms do not | Cognition — [2026-04-22](https://cognition.com/blog/multi-agents-working), [Don't build multi-agents](https://cognition.com/blog/dont-build-multi-agents); Anthropic — [research system](https://www.anthropic.com/engineering/multi-agent-research-system) (subagents only via lead; most coding tasks a poor fit; ~15× chat tokens) | CM.5 |
| Claude Code agent teams (Feb 2026, experimental) add a mailbox and shared task list but are advised against for sequential work and same-file edits, at 3–5× tokens | [overview](https://www.morphllm.com/claude-code-agent-teams) | peer mailbox rejected |
| An uncertainty-triggered clarification step lifted resolve rate about +14 points on underspecified SWE-bench Verified for both Claude Sonnet 4.5 and Kimi K2.6; Kimi over-asked (8.7 questions per task) | "Ask or Assume?" — [arXiv 2603.26233](https://www.alphaxiv.org/abs/2603.26233) | CM.4 (bounded, retrieval first) |

---

<a id="r1"></a>
## Part R1 — Frontier coding-agent harnesses and local-model techniques (2026-10-19, session 4)

### R1.a Coverage: each top-15 technique → plan item

| # | Technique | Plan items |
|---|---|---|
| 1 | Feature ledger, one feature per turn, startup ritual | [AZ](improvement-plan.md#plan-az) |
| 2 | Deterministic stop gate on acceptance scripts | [AZ](improvement-plan.md#plan-az), [J](improvement-plan.md#plan-j), [AF](improvement-plan.md#plan-af) |
| 3 | Stable-prefix prompt layout, constant tools, slot pinning | [BA](improvement-plan.md#plan-ba), [AA](improvement-plan.md#plan-aa) |
| 4 | Context floor and live-context budget per turn | [BJ](improvement-plan.md#plan-bj), [O](improvement-plan.md#plan-o) |
| 5 | Three-tier compaction | [Z](improvement-plan.md#plan-z) |
| 6 | Edit format per model by measured well-formed rate; architect/editor split | [BH](improvement-plan.md#plan-bh), [Y](improvement-plan.md#plan-y), [BD](improvement-plan.md#plan-bd) |
| 7 | Minimal flat tool set per role, one action per turn | [BH](improvement-plan.md#plan-bh), [X](improvement-plan.md#plan-x) |
| 8 | Schema-constrained inter-role artifacts | [BB](improvement-plan.md#plan-bb), [M](improvement-plan.md#plan-m) |
| 9 | Model registry: parser, template, sampling, thinking per family | [BH](improvement-plan.md#plan-bh), [M](improvement-plan.md#plan-m) |
| 10 | Thinking budgets per role and turn | [AX](improvement-plan.md#plan-ax), [N](improvement-plan.md#plan-n) |
| 11 | Repair budget 2–3, then fresh-context restart | [AY](improvement-plan.md#plan-ay), [L.6](improvement-plan.md#plan-l-6) |
| 12 | Hard caps on injected instructions; compact prompt for local models | [BJ](improvement-plan.md#plan-bj), [X](improvement-plan.md#plan-x) |
| 13 | Loop and failure-class detection as hooks | [BC](improvement-plan.md#plan-bc), [L](improvement-plan.md#plan-l) |
| 14 | Rubric-based verification of hard work orders | [BI](improvement-plan.md#plan-bi) |
| 15 | Inference knobs (MTP, speculation, KV types) — owner advisory | [S](improvement-plan.md#plan-s), [BD](improvement-plan.md#plan-bd) |

### R1.b Technique → review finding → plan item (§15.1 of the session-4 review)

From the web research of this session (full report with ~95 primary sources:
`docs/research-findings.md`). Only techniques that bear on a
finding above are listed; each names the harness or paper it comes from.

| finding | technique in the field | source | what it means here |
|---|---|---|---|
| I1 lost replies | Thinking per role and per turn, **bounded** (`--reasoning-budget`, per-request `reasoning_budget_tokens`); gpt-oss low/medium/high = 37/53/61 SWE-bench Verified, so effort is a real dial; Aider's Qwen3 run with default thinking scored *lowest* (49.8%) with 58 malformed outputs and ~3× the cost; Kimi K2.5 ran Terminal-Bench non-thinking | llama.cpp server README; HF cards; aider.chat/2025/05/08/qwen3 | AX: budget by role; thinking off for routine edit loops, on and bounded for architect/reviews/repair |
| I2 fix loop | Repair gains come in the first 2–3 attempts, then decay 60–80% ("Debugging Decay Index"; "How Many Tries"; "Is Three the Magic Number"); fresh-context restarts at computed points beat continued debugging (Llama 3.1 8B 72.6→82.8%); parallel rollouts + verifier selection lift a 32B model Pass@1 34→51% hybrid Best@26 (R2E-Gym), Qwen3-Coder-30B-A3B Best@16 39.6→54.2 with repo-grounded rubrics (Agentic Rubrics); Agentless-style localise→repair→validate | arXiv papers cited in the report §9, §4 | AY: ≤3 in-context repairs, then restart with failure output; k=2–4 short candidates selected by the defect's tests; localisation before repair |
| I2 / I5 foundation | Anthropic's long-running-agent harness: initializer writes `init.sh`, a progress file and a **JSON feature list** (`passes:false`), every later session does env check + smoke test, implements **one feature**, verifies end-to-end (browser), commits; only the verifier flips `passes`; Terminal-Bench failure taxonomy: "command not found"/PATH is the largest failure class (24%), premature termination and step repetition are named classes | anthropic.com/engineering/effective-harnesses-for-long-running-agents; arXiv 2601.11868 | AZ: walking skeleton + slices; the locked suite is the JSON ledger; skeleton proof = the session-start ritual |
| I3 re-reads, I7 cache | Prefix caching needs: tools constant and ordered, static system prompt, dynamic state at the *end*, append-only transcript, canonical JSON; Claude Code splits its system prompt into a static cacheable prefix and a dynamic tail; llama.cpp `--cache-reuse 256`, `id_slot` pinning, `--slot-save-path` save/restore (ms), LRU eviction forces full reprocessing | platform.claude.com prompt-caching; arXiv 2609.00006; llama.cpp README + discussion #13606 | BA |
| I3 tools | Minimal flat tool set (3–6), MCP off for local models, `parallel_tool_calls=false`, one action per turn for ≤35B models; mini-SWE-agent (bash only) is the top SWE-bench Pro public scaffold; Factory Droid's +15 pts over Claude Code at fixed model came from minimal tools, simplified schemas, model-specific scaffolding, a plan tool, short timeouts | github.com/SWE-agent/mini-swe-agent; factory.com/news/terminal-bench; kilo.ai docs | AY step 5, BH |
| I4 decode cost | Native MTP where the model ships it (Qwen3.6-35B-A3B has MTP heads), n-gram speculation on whole-file-edit turns (output copies input), flash attention on, KV q8_0 safe for Qwen (KL 0.039) but not Gemma | vLLM/llama.cpp docs; localbench KL study 2026-04 | advisory to the owner (BD) — the harness only measures |
| I5 context | NoLiMa/RULER/Context Rot: effective context of open models is a fraction of the advertised window (Qwen3-30B-A3B RULER effective 64K; focused ~300-token inputs beat 113K inputs on every model); compaction helps small models (ACON −26–54% tokens, up to +46% task gain) | adobe-research/NoLiMa; NVIDIA RULER; Chroma 2025-07 | AZ: ≤24–32K live context per turn by design, not by compaction |
| I6 plan JSON | Codex and Claude Code keep user/work-order text verbatim and summarise only trajectories; schema-constrained artifacts with a short `rationale` field first do not lose reasoning (.txt rebuttal) | gist osolmaz; blog.dottxt.ai | BB: one order per call, schema-constrained |
| I9 tiers | Cognition "smart friend": a cheap primary forks to a stronger model for hard moments; mini-SWE roulette: alternating two models beat either alone (66.6%) | cognition.com/blog/multi-agents-working; swebench.com roulette | BD |
| edit format | Aider: `whole` 100% well-formed vs `diff` 92–95% on Qwen3-235B; lenient matching with fallbacks ≈9× fewer edit errors; architect/editor split lifts every model (+3–5 pts) | aider.chat edit-formats, unified-diffs, architect | BH: measure well-formed rate per model, choose whole-file below ~300 lines |
| model registry | vLLM/llama.cpp need the family's tool-call parser/template (hermes, qwen3_coder XML, mistral, glm47, openai-harmony) and sampling per mode; "protocol adherence isn't guaranteed" | docs.vllm.ai tool_calling; qwen.readthedocs.io | BH |
| verification | Deterministic gates beat self-assessment (Stop hooks, `/goal`, Hermes verify-on-stop); Playwright accessibility snapshots instead of screenshots; mutation testing: top agents detect <40% of realistic mutants | code.claude.com docs; playwright-mcp; SWE-Mutation 2026 | already in the harness (locked suite, AF mutation probe); keep |

### R1.c The full report
Companion to `docs/improvement-plan.md` Appendix 4 and `docs/review-findings.md` §15. Web research by this session; every claim cites its source; vendor-reported scores are marked as such.


Research date: 2026-10-19. All claims below were verified against the cited primary or near-primary sources during this session; dates are the source's own. Where a page was unreachable (Cursor indexing docs, Augment context-engine page, Factory redirect) the finding is attributed to the page that was actually read. Applicability ratings (H/M/L) are for a self-hosted LangGraph harness that builds whole apps from a brief with roles (PM, architect, tech lead, engineers, QA, reviewers), sprints/work orders, a sandbox, acceptance tests and a web UI, running on Ollama / vLLM / llama.cpp / LM Studio.

A recurring meta-finding: harness design moves scores by 10–20 points at fixed model (Terminal-Bench 2.0: Opus 4.6 scores 58.0% in Claude Code vs 74.4% in Terminus 2 vs 81.8% in ForgeCode — codex.danielvaughan.com 2026-04-09; Factory: Droid+Opus 58.8% vs Claude Code+Opus 43.2% — factory.com 2025-09-25), yet the Terminal-Bench paper itself says model choice usually matters more than scaffold (arXiv 2601.11868). Both are true: pick the best local model you can fit, then the harness is the lever that remains.

---

### 1. Claude Code / Claude Agent SDK and Anthropic's context-engineering guidance

**Context budget is the governing constraint.** Anthropic's best-practices doc states that performance degrades as context fills and that the window is "the most important resource to manage" (code.claude.com/docs/en/best-practices). The "Effective context engineering" post (2025-09-29, updated 2026-01-06) frames the goal as the smallest set of high-signal tokens, and describes context rot as a gradient, not a cliff. **Applicability: High** — every role agent in DevFlow should have an explicit token budget and a stated policy for what enters context.

**What loads at startup, measured.** Claude Code's interactive context-window doc enumerates a startup footprint of roughly: system prompt 4,200 tokens, auto-memory 680 (first 200 lines / 25 KB of MEMORY.md), env info 280, deferred MCP tool names 120, skill descriptions 450, global CLAUDE.md 320, project CLAUDE.md 1,800 (code.claude.com/docs/en/context-window). MCP tool schemas are deferred by default and loaded on demand via tool search; `ENABLE_TOOL_SEARCH=auto` loads them upfront only if they fit within 10% of the window. **Applicability: High** — publish only tool names + one-line descriptions to local models and expand schemas on demand; the harness paper (arXiv 2609.00006) notes Claude Code has 43 typed tools with deferred loading.

**Three-tier compaction.** (a) Tool-result clearing first ("microcompaction": older tool outputs are cleared before any summarization), (b) auto-compaction when the window nears its limit (default boundary 200K for 200K models, ~967K for 1M-window models; configurable via `/autocompact`, `autoCompactWindow`, env var; accepted range 100K–1M), (c) manual `/compact <focus>`. After compaction the system prompt, CLAUDE.md, auto-memory and MCP tools reload from disk; up to 5 most-recently modified files are re-read (files >5,000 tokens come back as a path reference only); invoked skill bodies are re-injected capped at 5,000 tokens per skill and 25,000 total; the skill *listing* does not reload. Path-scoped rules are summarized away. A "Compact Instructions" section in CLAUDE.md steers what survives. If a single tool output is so large the window refills immediately, auto-compaction stops after a few attempts with a thrashing error. (code.claude.com/docs/en/context-window, /how-claude-code-works, /model-config.) **Applicability: High** — implement exactly this ordering in LangGraph: prune stale tool outputs → summarize → re-inject role charter + work order + last-N touched files. The "re-read 5 files" and "cap per-file at ~5K tokens" are concrete defaults.

**Subagents = context isolation, not parallel writers.** A subagent runs in its own window with its own system prompt, returns only its final text (doc's worked example: 6,100 tokens of reads → 420-token result). Built-in Explore/Plan agents are read-only and skip CLAUDE.md to stay small. Defaults: 20 concurrent subagents, nesting depth 3, warning when combined subagent descriptions exceed ~15,000 tokens. The doc says to use the main conversation when "several phases share significant context, such as planning, implementing, and testing" and because a fresh subagent must re-gather context (code.claude.com/docs/en/sub-agents). **Applicability: High** — maps directly to DevFlow roles: research/QA/review as isolated subagents returning compact structured results; implementation stays single-threaded per work order.

**Verification loop as a first-class concept.** Glossary defines "verification loop" as the prerequisite for unattended runs: without a check the agent can run, "the only thing deciding the agent is finished is the agent itself." Four escalating gates: in-prompt ("run tests and iterate"), `/goal` (separate evaluator re-checks after every turn), a deterministic Stop hook that blocks the turn until a script passes (exit code 2 feeds stderr back as the next instruction; `stop_hook_active` guards infinite loops), and an adversarial review subagent that sees only the diff. The doc warns a reviewer "prompted to find gaps will usually report some," so tell it to flag only correctness-affecting gaps (code.claude.com/docs/en/best-practices, /hooks, /glossary). **Applicability: High** — DevFlow's QA/acceptance step should be a *deterministic* gate (script), with the LLM reviewer as a second, scoped opinion.

**Hooks are deterministic, prompts are advisory.** 33 hook events incl. PreToolUse, PostToolUse, Stop, SubagentStop, PreCompact/PostCompact, SessionStart; handler types: command, http, mcp_tool, prompt (30 s), agent (60 s). "Use hooks for actions that must happen every time with zero exceptions" (best-practices). **Applicability: High** — lint/format/test on PostToolUse; forbid edits to protected files; block Stop until the work order's acceptance script passes. Local models especially benefit because they follow prose rules less reliably.

**CLAUDE.md discipline.** Keep it short; for each line ask whether removing it would cause mistakes; "bloated CLAUDE.md files cause Claude to ignore your actual instructions"; after two failed corrections, `/clear` and rewrite the prompt. Path-scoped `.claude/rules/` load only when a matching file is read. AGENTS.md is read as a fallback. Auto-memory: Claude's own notes, first 200 lines / 25 KB loaded (code.claude.com/docs/en/best-practices, /memory). **Applicability: High** — the same discipline applies to DevFlow's per-role charters and project notes; path-scoped rules are a cheap way to give stack-pack guidance without bloating every prompt.

**Plan mode.** Read-only exploration, then an editable plan, then implementation; the doc cautions plan mode "adds overhead" and should be skipped when the diff could be described in one sentence (best-practices). **Applicability: Medium-High** — DevFlow already plans at the PM/architect level; the transferable rule is to make engineer-level planning conditional on change size.

**Long-running / multi-session harness (Anthropic, 2025-11-26).** Even Opus 4.5 in a loop failed to build a production-quality app from a one-line prompt. Observed failure modes: trying to one-shot the app and running out of context mid-feature; later sessions declaring the project done; marking features done without real testing; leaving messy environments. Fix: an **initializer agent** (first session) writes `init.sh`, `claude-progress.txt`, an initial git commit and a **JSON feature list** (200+ features for a claude.ai clone, each with `category`, `description`, `steps`, `passes:false`); **coding agents** (every later session) run `pwd`, read git log + progress file, pick the highest-priority failing feature, run `init.sh`, do a basic end-to-end check, implement **one feature**, verify end-to-end (Puppeteer MCP, "as a human user"), commit, update notes. Coding agents may only flip `passes`; editing/removing tests is forbidden. JSON was chosen over Markdown because the model was less likely to tamper with it. The two "agents" differ only by initial prompt — same system prompt, tools and harness (anthropic.com/engineering/effective-harnesses-for-long-running-agents). **Applicability: High** — this is almost exactly DevFlow's sprint/work-order shape. Concrete transfers: a machine-checked feature ledger in JSON that only a verifier node may mark passing; a session-start ritual (env check + smoke test before new work); one feature per engineer turn; `init.sh` generated by the architect role.

**Building effective agents (2024-12-19).** Prefer simple composable workflows (prompt chaining, routing, parallelization, orchestrator-workers, evaluator-optimizer) over frameworks; invest in the agent-computer interface: formats close to natural text, avoid line counting and heavy escaping, require absolute paths (fixed a real SWE-bench error class), poka-yoke tool arguments. **Applicability: High** for tool design under weak models.

**Agent SDK article (2025-09-29).** Start with agentic search (grep/glob/tail); semantic search is "usually faster… but less accurate, more difficult to maintain, and less transparent"; verify via rules-based feedback (lint, tests), visual feedback (screenshots via Playwright) and LLM-as-judge only where cost is justified (claude.com/resources/articles/building-agents-with-the-claude-agent-sdk). **Applicability: High.**

---

### 2. OpenAI Codex CLI / Codex cloud and AGENTS.md

**Sandbox + approvals as separate layers.** `sandbox_mode`: read-only / workspace-write / danger-full-access; `approval_policy`: untrusted / on-request / never; `--full-auto` = on-request approvals inside workspace-write sandbox. A model-based "automatic approval review" can pre-screen approval requests (learn.chatgpt.com/docs/glossary; codex.danielvaughan.com 2026-04-19). **Applicability: High** — DevFlow already has a sandbox; the transferable idea is making write-scope and approval-policy orthogonal config per role (QA read-only, engineer workspace-write).

**AGENTS.md discovery and byte cap.** Global `AGENTS.override.md`/`AGENTS.md` in CODEX_HOME, then repo root → cwd with closest file winning; `project_doc_max_bytes` defaults to 32 KiB and lower-level files are skipped once the cumulative size is reached (fast.io codex-context-window; Codex docs). **Applicability: High** — enforce a hard byte cap on everything injected as "project instructions" for local models.

**Compaction, measured.** From a source-code read (commit fa1d4c40, 2026-07-28) and 1,087 real compaction records: auto-compact fires at 90% of a resolved window that is itself 95% of raw; user messages are kept verbatim newest-first up to a 64,000-token budget; developer instructions, AGENTS.md and environment context are **re-injected fresh rather than summarized**; oversized tool outputs are truncated in place; assistant/tool content folds into an encrypted server-side summary. Median blob 15,820 chars (p90 23,672); consecutive compactions do not grow (median delta −168 chars). Worked examples: 174,871 → 3,368 tokens (≈52×), 226,661 → 19,537 (≈11.6×); the 174K compaction took 33.7 s (gist.github.com/osolmaz/a38acf6e522df67530e3ed47c80fdcd5). A separate deep-dive reports the trigger as effective window − 13,000 tokens with 20,000 reserved for output (~167K on 200K), post-compaction re-read of up to 5 recently edited files within a 50K budget, and a regression where v0.118 compacted ~2× as often as v0.116 (codex.danielvaughan.com 2026-04-14). Local (non-OpenAI providers) compaction runs a summarization prompt. **Applicability: High** — the "keep user/work-order text verbatim, re-inject instructions fresh, summarize only the agent's own trajectory" split is the right policy for small models whose summaries are lossy; budget the summary (~16–20K chars observed) and re-read last-edited files.

**Review mode.** `/review` performs an inline review without modifying the tree; recommended as a pre-commit check (Codex docs guide). **Applicability: Medium** — DevFlow's reviewer role is already this; the transfer is "diff-only, fresh context".

**Subagents cost more.** Codex docs state subagents "consume more tokens than comparable single-agent runs" and are behind a `multi_agent` feature flag. **Applicability: Medium** — budget subagent use.

**ACM (agent-directed compaction).** Li et al., arXiv 2607.23809 (2026-07-26): give the agent `manage_context` (summarize + offload raw messages to disk) and `query_memory` (retrieve by id) instead of threshold triggers. With a Qwen3.5-9B student distilled from a 397B teacher: SWE-bench Verified 0.489 → 0.530 (+8% rel.), BrowseComp-Plus 0.570 → 0.727, peak tokens −11–15% per task (paper says ~20%), more tool calls per episode (74.7 → 79.3 on SWE-bench). **Applicability: Medium** — the *lossless offload* idea (keep raw transcript on disk, give a `recall` tool) is cheap to implement in LangGraph even without the post-training; the agent-decides-when part needs training to pay off.

---

### 3. Other harnesses

**Cursor (Composer / semantic search).** Composer (2025-10-29) is an MoE model RL-trained in Cursor's own harness with grep, semantic search, file edit and terminal tools; training rewarded parallel tool calls and penalized unverified claims. Cursor's semantic-search study (2025-11-06): a custom embedding model trained from agent-session traces raised answer accuracy on Cursor Context Bench by 12.5% on average (6.5–23.5% by model); online A/B: code retention +0.3% overall, +2.6% on repos with 1,000+ files; dissatisfied follow-ups −2.2%; "the combination [grep + semantic] leads to the best outcomes" (cursor.com/blog/semsearch). **Applicability: Medium** — embeddings help mainly on large repos and conceptual queries; for greenfield apps built by DevFlow, repos are small for most of a run, so start with ripgrep + symbol map and add an embedding index only when the generated codebase crosses ~1K files.

**Devin / Cognition.** "Don't build multi-agents" (2025-06-12): share full traces not just task text; actions carry implicit decisions, so parallel writers conflict (Flappy Bird example); prefer single-threaded agents; compress with a dedicated (fine-tuned) model. Follow-up "Multi-agents: what's actually working" (2026-04-22): writes stay single-threaded; patterns that work are (1) a code-review loop with a clean context seeing only the diff — Devin Review averages 2 bugs/PR, 58% severe; (2) "smart friend": a cheap primary model forks full context to a stronger model for hard moments; (3) manager/child delegation via a map-reduce-and-manage structure, with failure modes: over-prescriptive managers, children assuming shared state, children not reporting back. Devin 2.0 (2025-04-03) adds Interactive Planning (research → editable plan), Devin Search and Devin Wiki (re-indexed ~every 2 h). **Applicability: High** — DevFlow's parallel/linear toggle should default to linear writes with parallel *read-only* roles; reviewer sees diff only; the "smart friend" pattern = route hard subtasks to the largest local model you have while a small MoE does routine turns.

**Windsurf / Cascade (now Devin Desktop).** Rules: global file capped at 6,000 chars, workspace rule files 12,000 chars each; activation modes `always_on`, `model_decision` (description only in prompt, body loaded on demand), `glob`, `manual`; AGENTS.md handled by the same engine; auto-generated memories stored per workspace (docs.devin.ai/desktop/cascade/memories). **Applicability: High** — hard character caps + four activation modes is a concrete, cheap design for DevFlow's stack packs and seed rules.

**Cline / Roo / Kilo (popular with local models).** Cline: "Use Compact Prompt" for local models is "roughly 10% the size" of the full system prompt and disables MCP tools, Focus Chain and MTP features; recommended Qwen3 Coder 30B A3B via LM Studio at 4-bit; set context to 262,144 if memory allows, halve if slow; keep tasks focused and start new tasks when context grows; auto-compact reuses the prompt cache so the cost is mostly the summary's output tokens; non-supported models fall back to rule-based truncation; checkpoints let you restore pre-summary state (cline.bot/blog/local-models 2025-08-28; docs.cline.bot running-models-locally, features/auto-compact). Roo Code: condensing triggers at 100% by default (80% shown as a sane lower value); reserves 30% of the window (20% output + 10% buffer) so history gets 70%; on context-limit error it cuts context by 25% and retries; a custom condensing prompt can list what must be preserved; condensing always uses the active model to avoid tool-format errors (roocodeinc.github.io intelligent-context-condensing). Kilo Code + Ollama: `qwen3-coder:30b` primary, `devstral:24b` alternative; "at least 32k" context "to get decent results"; 24 GB VRAM or 32 GB Apple RAM; local models are "more prone to loops, tool-use failures, and syntax errors"; disabling MCP tools helps (kilo.ai/docs/providers/ollama). **Applicability: High** — a dedicated *compact* prompt variant per role (≈10% of the full one), 32K minimum context, MCP off by default for local models, and a 25%-cut retry on overflow are all directly adoptable.

**Aider.** Edit formats: `whole`, `diff` (search/replace blocks, merge-conflict style), `diff-fenced` (Gemini), `udiff` (GPT-4 Turbo laziness), `editor-diff`/`editor-whole` for architect mode; lesser-known models default to `whole`. Unified diffs cut GPT-4 Turbo laziness ~3× (20% → 61% on a refactor benchmark); no line numbers; high-level whole-function replacement; flexible matching with fallbacks — disabling the fallbacks raised edit errors ~9× (aider.chat/docs/unified-diffs). Architect/editor (2024-09-26): separating reasoning from editing lifted every model, e.g. Sonnet 77.4 → 80.5 (self-edit), gpt-4o 71.4 → 75.2, gpt-4o-mini 55.6 → 60.2 with `whole`; o1-preview + DeepSeek (whole) 85.0. Repo map: tree-sitter symbols ranked by a dependency graph, default 1K tokens (`--map-tokens`), dynamically expanded when no files are in chat (aider.chat/docs/repomap). Qwen3-235B polyglot: `whole` 65.3% / 100% well-formed vs `diff` 61.3% / 94.7% on the same vLLM bf16 server; llama.cpp Q5_K_M whole 59.1%; OpenRouter default-thinking diff 49.8% with 58 malformed outputs (aider.chat/2025/05/08/qwen3). Aider has no automatic compaction and re-prompts on malformed edits up to 3 times (harness paper). **Applicability: High** — the single most reusable lesson: pick edit format per model from measured well-formed rate, keep a lenient matcher with fallbacks, and use architect/editor split so a strong local reasoner plans and a cheap model (or deterministic apply) edits.

**OpenHands (2026).** SDK V1 (MLSys 2026, arXiv 2511.03690): stateless agent, append-only event log with per-event files (median persist 0.20 ms, crash recovery ~7–32 ms), opt-in Docker/remote workspace, condensers. `LLMSummarizingCondenser` defaults: trigger at >120 events, keep first 4 verbatim, reduce to ~60 events; head/middle/tail split; summary records goals, progress, remaining work, critical files, failing tests; a PipelineCondenser chains pruning → summarizing → truncating (docs.openhands.dev/sdk/arch/condenser). Measured on SWE-bench Verified subset: per-turn cost settles at under half of baseline; resolve 54% vs 53% baseline (openhands.dev blog 2025-04-09). Microagents are now "skills" in `.agents/skills/<name>/SKILL.md` with `triggers` keywords and `paths` globs; AGENTS.md is always loaded in full, so keep it concise (docs.openhands.dev microagents-overview). Local-LLM guide: recommends Qwen3.6-35B-A3B; ≥24 GB VRAM quantized or ≥64 GB Apple unified; context ≥22,000, 32,768 recommended; Ollama default 4,096 "is too small for the system prompt"; vLLM with `--enable-prefix-caching`. Harness paper notes OpenHands runs an outer loop where an LLM judge reviews finished runs. **Applicability: High** — the event-sourced, resumable log plus a head/tail-preserving summarizer with a cheaper summarizer model is a good fit for a LangGraph checkpointer design; the 22K/32K floor is a hard requirement to enforce in DevFlow's "ready" check.

**SWE-agent / mini-SWE-agent.** mini: bash only, no tool-calling API, linear append-only history, stateless `subprocess.run` actions (swap for `docker exec`), ~100 lines, ">74%" on SWE-bench Verified (self-reported), used as the neutral "Bash Only" leaderboard scaffold and for RL/fine-tuning because it doesn't overfit to a scaffold (github.com/SWE-agent/mini-swe-agent). Model roulette (2025-08-19): randomly alternating GPT-5 and Sonnet 4 per turn scored higher than either alone (39 vs 33/32 on a 50-task subset; 66.6% on the full 500 when alternating); gains plateau around a 50-step limit (swebench.com/post-250820-mini-roulette). Scale's SWE-bench Pro public leaderboard (Sept 2026) marks its top three entries as mini-swe-agent runs. **Applicability: High** — for local models, a single `bash` tool with the edit expressed as a shell heredoc or a dedicated minimal edit tool removes a whole class of tool-schema failures; the alternating-model result suggests DevFlow's per-role model routing may itself add diversity/robustness.

**Gemini CLI.** `model.compressionThreshold` default 0.5 (compress at 50% of context); `tools.truncateToolOutputThreshold` 40,000 chars; `model.disableLoopDetection` default false (harness paper: aborts after 5 identical calls); `maxSessionTurns` −1; hierarchical GEMINI.md with `memoryDiscoveryMaxDirs` 200; checkpointing via `/restore <tool_call_id>`; `summarizeToolOutput` with a `tokenBudget` for `run_shell_command` (geminicli.com/docs/cli/settings, /reference/commands). **Applicability: High** — these are the most explicit *numeric* defaults in any harness: compress early (50%), hard-cap tool output (~40K chars), per-tool LLM summarization budget, identical-call loop breaker (5).

**Qwen Code.** Forked from Gemini CLI v0.8.2 and now independent; supports SubAgents, Agent Teams, auto-memory, auto-skills, hooks, plan mode, LSP, sandbox, git worktrees, local models via Ollama/vLLM, multi-protocol APIs (github.com/QwenLM/qwen-code). Qwen's own guidance: Hermes-style tool calls for Qwen3 (`--tool-call-parser hermes`), `qwen3_coder` XML parser for Qwen3-Coder/3.6, never ReAct stop-word templates with reasoning models, and "protocol adherence isn't guaranteed" so parse defensively (qwen.readthedocs.io function_call). **Applicability: High.**

**Kimi K2 / Kimi Code.** K2-Thinking claims stable tool use "across 200–300 sequential calls" with native INT4 QAT (vendor claim); K2.5: 1T/32B-active, 256K, SWE-bench Verified 76.8 (card), Terminal-Bench 2.0 50.8; for HLE-with-tools only the latest round of tool messages is kept once context exceeds a threshold; thinking off via `chat_template_kwargs: {thinking: False}` (huggingface.co/moonshotai). Kimi Code docs index lists desktop/CLI/VS Code surfaces and integrations with Claude Code, OpenCode, Codex and Hermes Agent, but architecture pages were not reachable. **Applicability: Low** for the model (too large for consumer GPUs); **Medium** for the "keep only the latest tool round once over budget" rule.

**Goose, Amp, Factory Droid, Augment.** Goose: MCP-native, multi-model config, `GOOSE_AUTO_COMPACT_THRESHOLD` (towardsai survey). Amp: multi-model routing per task, per-thread cloud machines; details on Oracle/Librarian subagents weren't on the reachable page. Factory Droid (2025-09-25): #1 on Terminal-Bench v0.1.1 at 58.8% with Opus 4.1 no-thinking vs Claude Code+Opus 43.2%; credited to "agent design": minimal tool set with simplified schemas and model-specific tool scaffolding, a three-tier prompt hierarchy (tool descriptions / system prompt / system notifications), session bootstrapping with system info, a plan tool that tracks done/next, ripgrep search, short default timeouts, opt-in background execution (factory.com/news/terminal-bench). Augment Auggie: 51.80% on SWE-bench Pro public vs Cursor 50.21%, Claude Code 49.75% (all Opus 4.5), credited to its semantic Context Engine; no ablation (augmentcode.com 2026-02-04). **Applicability: High** for Droid's list (it is a checklist of cheap harness wins), **Medium** for Augment (no ablation).

**Cross-harness survey (towardsai, 2026-09-24, 20 OSS harnesses at HEAD 2026-09-22).** 10 expose a settable compaction threshold, 2 switch-only, 1 hard-coded (Continue at 80%), 5 none (incl. Aider, Letta); Zed defaults to 90%. Harness source-code study (arXiv 2609.00006, 2026-07): no studied agent uses embedding retrieval; all rely on ripgrep/tree-sitter/glob plus Markdown context files; Claude Code splits its system prompt into a static cacheable prefix and a dynamic section; stuck detection ranges from Hermes (warn after 2 identical failures, halt after 8) to OpenCode (3 identical calls → user prompt) to Gemini CLI (abort after 5); SKILL.md supported by 9/11, MCP by 8/11; none built on LangChain/AutoGen. **Applicability: High** — adopt: settable threshold (default 50–80% for local models), static-prefix prompt split, identical-call loop breaker at 3–5.

---

### 4. Multi-agent vs single-agent evidence; what top 2026 submissions do

- **Harness effect at fixed model is large.** Terminal-Bench 2.0, Claude Opus 4.6: Claude Code 58.0%, Terminus 2 74.4% (up from 62.9% through community harness changes, model unchanged), Terminus-KIRA 74.7%, Meta-Harness 76.4%, ForgeCode 81.8%. Reported differentiators: schema field reordering/flattening, partial-read reminders, pre-loop environment snapshot (saves an estimated 2–5 turns), sub-agent decomposition, mandatory reviewer before submission (codex.danielvaughan.com 2026-04-09). **H.**
- **Terminal-Bench paper (arXiv 2601.11868, 2026-01-17).** 89 tasks, 32,155 trials; best 63% (Codex CLI + GPT-5.2); best open-weight at the time 36% (Terminus 2 + Kimi K2 Thinking). Turn count shows essentially no correlation with success; more tokens do not imply better results; command-level error rates 9.2–26.7%, with "command not found"/PATH failures the single largest class (24.1% of sampled failures) and invocation failures 35.1% overall. Failure taxonomy: Execution / Coherence / Verification, with named sub-causes Disobey Specification, Step Repetition, Unaware of Termination Conditions, Context Loss, Premature Termination, No or Incorrect Verification. **H** — DevFlow should bootstrap the sandbox (tool versions, PATH, package managers) into the first prompt and treat step repetition / premature termination as detectable, hookable failure classes.
- **Parallel rollouts + verifier selection.** R2E-Gym (2025-04): 32B agent Pass@1 34.4%, Pass@26 64.4%; execution-based and execution-free verifiers each plateau ~42–44% Best@k; hybrid reaches 51.0% Best@26; adding *test-agent* rollouts helps more than adding editing-agent rollouts. Agentic Rubrics (Scale AI, 2026-01-07): Best@16 on Qwen3-Coder-30B-A3B rollouts: random 39.6 → self-consistency 47.6 → agentic tests 49.0 → patch-classifier LLM judge 50.2 → repo-grounded rubrics 54.2 (oracle 65.6); rubrics cost ~$0.29/instance vs $0.52 for tests; judge capability barely matters (GPT-5-mini 52.6 vs GPT-5 high 55.0) but *rubric-writer* capability does (frontier ~54 vs open coders ~45). SWE-Master (2026-02): 32B RL model 61.4% Pass@1 → 70.8% with 8 rollouts selected by a learned simulated-test verifier (Pass@8 oracle 76.2%); sequential gains plateau around 125 turns. **M** — expensive locally, but *k=2–4 rollouts for the hardest work orders* selected by acceptance tests + a rubric judge is feasible and is the only proven way to lift a small model's effective pass rate by 10+ points without training.
- **Model alternation.** mini-SWE-agent roulette: alternating two models beat either alone (66.6% full-set) — **M** for DevFlow (alternate two local models per turn as a cheap diversity source).
- **Single-threaded writes.** Cognition 2026-04 and Anthropic's long-running-agent post both keep one writer; Anthropic lists "specialized roles (testing, QA, cleanup)" as an open question. **H** — keep DevFlow's parallel mode for research/review only.
- **Leaderboard context (self-reported, not comparable).** SWE-bench Verified is saturated at the top (Claude Opus 5 96%, Fable 5 95%); open-weight: DeepSeek V4 Pro 80.6, MiniMax M3 80.5, Qwen3.7 Max 80.4, Kimi K2.6 80.2, Qwen3.6-27B 77.2, Qwen3.6-35B-A3B 73.4, gpt-oss-120b 62.4, gpt-oss-20b 60.7, GLM-4.7-Flash 59.2, Devstral Small 2 (24B) 68.0 (benchlm.ai 2026-10-17; HF cards). SWE-bench Pro public (standardized, Scale, 2026-09): Qwen3-Coder-480B 38.7, MiniMax 2.1 36.8, Kimi K2 27.7, GLM-4.6 9.7 — Pro separates harness-tuned self-reports from reality.

---

### 5. Making smaller / local models reliable as agents

- **Minimal tool set, simplified schemas.** Anthropic: "if a human engineer can't say which tool to use, neither can the agent"; Factory: minimal tools + simplified schemas + model-specific scaffolding; mini-SWE-agent: bash only; Kilo: disable MCP tools for local models; Claude Code defers MCP schemas by default. **H** — give each DevFlow role 3–6 tools, flatten nested schemas, one canonical edit tool.
- **Native tool-call templates per family (vLLM `--tool-call-parser`).** hermes (Qwen2.5/QwQ/Qwen3 per Qwen docs), qwen3_xml / qwen3_coder (Qwen3-Coder, Qwen3.6), llama3_json / llama4_pythonic (small Llamas "struggle" with pythonic), mistral (Devstral 2: `--tool-call-parser mistral --enable-auto-tool-choice`, temp 0.15), deepseek_v3/v31, glm45/glm47 (GLM-4.7-Flash also `--reasoning-parser glm45`), kimi_k2, openai (gpt-oss; harmony format mandatory — "will not work correctly otherwise"), granite, mimo; `hf` generic parser for any checkpoint with a `response_template` (docs.vllm.ai tool_calling). llama.cpp: native handlers for Llama 3.x, Functionary, Hermes 2/3 + Qwen 2.5, Mistral Nemo, Firefunction, Command R7B, DeepSeek R1 (WIP, "reluctant to call tools"); generic fallback otherwise; `--jinja` + a tool-aware template required; `parallel_tool_calls` off by default (docs/function-calling.md). **H** — DevFlow's model registry should carry parser/template/sampling per model and refuse to run a model whose template lacks `tool_use` support unless the bash-only mode is selected.
- **Forced / constrained tool choice.** vLLM `tool_choice=required` or a named function is implemented with structured outputs and "guaranteed a validly-parsable function call," not a good one; in `auto` mode constraints apply only with `strict: true` or `--tool-strict-level`; first call is slower while the grammar compiles (docs.vllm.ai). **H** — use `required`/named choice on the turns where DevFlow needs a specific artifact (plan JSON, work order, test list); keep `auto` only for free exploration.
- **Structured outputs / grammars.** Ollama: pass a JSON schema in `format`, also via OpenAI `response_format`; recommend temperature 0 and echoing the schema in the prompt; still validate (docs.ollama.com structured-outputs). llama.cpp: `-j/--json-schema`, `--grammar`, GBNF. vLLM: `structured_outputs` (json/regex/grammar/choice/structural_tag), backend `auto` (xgrammar, guidance/llguidance, outlines); for Qwen3-Coder with reasoning you may need `enable_in_reasoning=True`. llguidance: ~50 µs average mask per token on JSON-Schema-Bench, <1% of masks over 1 ms; xgrammar fast when its precomputation fits but "tens to hundreds of ms" otherwise with seconds-to-minutes precompute; Outlines has large startup/memory cost; integrated in llama.cpp (b4613, 2025-02), vLLM (0.8.2), SGLang (0.4.4) (github.com/guidance-ai/llguidance). Practitioner guide: grammar constraints slow generation 30–80% depending on complexity; guarantee syntax not content; Gemma 4 may put JSON into `reasoning_content` unless thinking is disabled (insiderllm.com, 2026-05). Quality: "Let Me Speak Freely" reported reasoning declines under format constraints; .txt's rebuttal reproduced GSM8K 0.77 unstructured vs 0.78 structured once prompts were matched, and recommends a bounded `reasoning` field *before* the answer field plus an example of the structure (blog.dottxt.ai/say-what-you-mean). **H** — DevFlow: schema-constrain every inter-role artifact; put a short `rationale` field first; prefer JSON schema over free grammars; keep schemas flat (vLLM thread 2026-07: prefer JSON schema to BNF, avoid deep nesting/lookaheads).
- **Edit formats.** Evidence from Aider above: `whole` is the most well-formed for mid-size open models (100% vs 92–95% for diff on Qwen3-235B; 25–58 malformed outputs per run with diff), diff is 3–5× cheaper; architect/editor split lifts every model; lenient matching with fallbacks is worth ~9× fewer edit errors. Cognition's history: 2024 "edit apply model" (big model describes, small model rewrites file) failed on ambiguous instructions and the field moved to one model deciding and applying. Morph "Apply" sells exactly that merge step as a hosted model (no numbers on the docs page). **H** — DevFlow should (1) measure well-formed rate per model on a 20-task smoke set and pick whole vs search/replace per model automatically, (2) default small models to whole-file for files < ~300 lines and search/replace with lenient matching above that, (3) never require line numbers or JSON-escaped code.
- **One tool per turn / linear history.** mini-SWE-agent's one bash action per step with linear append-only history is what the Bash-Only leaderboard and the roulette experiment run on; Qwen docs warn that malformed/parallel calls "cannot be parsed" in production without fallbacks. **H** — for ≤35B local models default `parallel_tool_calls=false` and one action per turn; enable parallelism only for read-only tools on models that score well.
- **Short compact system prompts and few-shot.** Cline compact prompt ≈10% of full; Anthropic: minimal complete set of instructions, curated canonical examples rather than edge-case rules; Windsurf caps rule files at 6K/12K chars; Codex caps project docs at 32 KiB. **H.**
- **Thinking toggles and their cost.** Qwen3.6: thinking on by default, off via `chat_template_kwargs: {enable_thinking: false}`, `preserve_thinking` option; recommended sampling differs by mode (thinking general temp 1.0/top_p 0.95/presence 1.5; precise coding temp 0.6; instruct temp 0.7/top_p 0.8) (HF card). Qwen3-Coder-30B-A3B is non-thinking only (temp 0.7, top_p 0.8, top_k 20, rep 1.05, 65,536 output recommended). gpt-oss-20b: reasoning low/medium/high gives SWE-bench Verified 37.4 / 53.2 / 60.7. DeepSeek-V4-Flash: Non-think 73.7 → Think-High 78.6 → Think-Max 79.0 Verified; Terminal-Bench 49.1 → 56.6 → 56.9; Think-Max wants ≥384K context. Kimi K2.5 ran Terminal-Bench in *non-thinking* mode. Aider's Qwen3 run: default thinking via OpenRouter scored lowest (49.8%) with 58 malformed outputs and ~3× the cost. llama.cpp exposes `--reasoning-budget N` (−1 unlimited, 0 off), `--reasoning-budget-message`, `--reasoning-format` (`deepseek` moves thoughts to `reasoning_content`). CodeJudgeBench: thinking models judge code better and Qwen3-8B-thinking beat 70B trained judges. **H** — DevFlow should set thinking per role and per turn: on (bounded budget, e.g. 2–8K via `--reasoning-budget`) for PM/architect/reviewer/judge and for failing-test repair; off for routine edits and tool-heavy loops; always strip thinking from history except where the model card says to preserve it (Qwen `preserve_thinking`, GLM "Preserved Thinking mode" for multi-turn agentic runs).
- **Retry-with-validation loops.** Aider re-prompts up to 3× on malformed edits; Roo cuts context 25% and retries on overflow; Pi compact-and-retry once; Hermes verify-on-stop guard blocks a final answer without fresh verification evidence (harness paper). **H.**
- **Small-model tool-calling research.** TinyLLM (2025-11): 1–3B models far outperform <1B; best hybrid optimization reaches 65.7% overall / 55.6% multi-turn on BFCL. IFFC (2026-08): framing function calls as instruction-following with a small dedicated model beats native tool calling, especially for reasoning models, and survives aggressive quantization. "To Call or Not to Call" (2026-05): models' self-perceived need for tools mismatches true need, causing costly over-calling. BFCL v4 (2026-10): Kimi K2.5 68.3%, Granite 4.2 30B 61.4%, 2–3B models 25–67%. **M** — supports a dedicated tiny "dispatcher" model for tool-call formatting if DevFlow's main local model is a reasoning model, and supports budgeting tool calls.
- **Context floors.** Ollama default 4,096 (<24 GiB VRAM) / 32K (24–48 GiB) / 256K (≥48 GiB); Ollama docs: agents and coding tools "should be set to at least 64000 tokens" (docs.ollama.com/context-length). OpenHands ≥22K/32K; Kilo ≥32K; Roo ≥32K. Truncation in Ollama is silent and drops the start of the prompt, i.e. the system prompt (fast.io analysis). **H** — DevFlow's `ready` check must verify `ollama ps` CONTEXT ≥ 32K (ideally 64K) and that `num_ctx` is passed per request.

---

### 6. Local inference efficiency and cache-friendly harness design

- **Prefix caching: what it needs.** Anthropic's prompt-caching rules generalize to any prefix cache: cache order tools → system → messages; any change to tool definitions invalidates everything after; changing `tool_choice`, images, thinking/effort parameters invalidates system+messages; matching is exact; non-deterministic JSON key order in tool inputs silently breaks caches; put the breakpoint at the end of the stable prefix; tool results can be cached turn over turn (platform.claude.com prompt-caching). The harness paper found Claude Code splits its system prompt into a static cacheable prefix and a dynamic part. **H** — DevFlow rules: (1) tools and schemas constant for the whole session, in a fixed order; (2) system prompt static, with time/run-id/dynamic state appended at the *end* of the first user message, not the system prompt; (3) append-only transcript; (4) compaction re-injects the identical prefix; (5) canonical JSON serialization.
- **vLLM automatic prefix caching.** Block-level KV reuse for shared prefixes; reduces prefill/TTFT only, no benefit for long outputs or non-shared prefixes; OpenHands recommends `--enable-prefix-caching`; PrefixBench-H100 (2026-09-17) finds reuse "substantially" reduces TTFT but cache pressure erodes it, and effectiveness is insensitive to concurrency/output length (docs.vllm.ai, arXiv 2609.19657). **H** — prefill of a 25K-token prompt is 10–30 s on consumer hardware (fast.io), so a cache hit per turn is the biggest latency win available to DevFlow's multi-turn loops.
- **llama.cpp server caching.** `--cache-prompt` on by default; `--cache-reuse N` enables KV-shift reuse of chunks ≥N tokens (default 0 = off; set e.g. 256); `--cache-ram` (default 8192 MiB) with `--cache-idle-slots` saves idle slots to a RAM prompt cache; `--ctx-checkpoints` 32 per slot; `-sps` slot-prompt-similarity (default 0.10) picks the slot with the most similar cached prompt; `--slot-save-path` enables `POST /slots/{id}?action=save|restore` (tutorial: 72 tokens restored in 0.74 ms; identical prompt re-evaluates 1 token; a shared-system-prompt request reprocessed only the 12 differing tokens); maintainers report unstable automatic slot switching, so clients should pin `id_slot` per agent/thread; LRU eviction under contention forces full reprocessing (tools/server/README.md; discussion #13606, 2025-05-17, with 2026 comments). **H** — DevFlow should pin one slot per role-thread (`id_slot`), enable `--cache-reuse 256`, and save/restore slots across sprints.
- **Ollama.** `OLLAMA_NUM_PARALLEL` default 1 and RAM scales with parallel × context (4 parallel × 2K = 8K); `OLLAMA_KEEP_ALIVE` default 5 min (set −1 so the model is not reloaded between role turns); `OLLAMA_FLASH_ATTENTION` auto; `OLLAMA_KV_CACHE_TYPE` f16 default, q8_0 ≈ half memory with "very little quality loss," q4_0 ≈ quarter with small-to-medium loss, requires flash attention, global for all models (docs.ollama.com/faq). Ollama docs do not document cross-request KV reuse; treat it as best-effort. **H.**
- **KV-cache quantization quality.** KL-divergence vs f16 cache (localbench, 2026-04-24): Qwen3.6-27B q8_0 0.024, Qwen3.6-35B-A3B q8_0 0.039, Qwen q4_0 0.087–0.117 (worse on long documents 0.581); Gemma 4 31B q8_0 0.108, Gemma 4 26B-A4B q8_0 0.377 and q4_0 1.088 (68% top-1 agreement) — q8_0 is *not* lossless for Gemma. llama.cpp's function-calling doc warns extreme KV quant (q4_0) can degrade tool calling; Cline's LM Studio guide says leave KV quant off. **H** — DevFlow default: q8_0 KV only for Qwen-family, f16 for Gemma/others, never q4_0 for agentic roles.
- **Speculative decoding.** vLLM supports ngram (prompt-lookup), draft models, EAGLE-3, MTP, suffix decoding; llama.cpp `--spec-type` now covers draft-simple/eagle3/mtp and ngram-simple/map-k/mod/cache variants (`--spec-draft-n-max` default 3). Measured: EAGLE-3 ~2.3× at low concurrency on Llama 3.3-70B, 2.0–2.7× (Red Hat Speculators); external 1B draft 2.31× at batch 1 but 1.4× at batch 8 and ≈baseline at batch ≥32; acceptance 0.75–0.85 on pattern-heavy code vs 0.5–0.65 creative (premai 2026). Native MTP heads ship with Qwen3.6-35B-A3B (vLLM `qwen3_next_mtp`, 2 tokens; SGLang NEXTN 3 steps/4 draft), GLM-4.7-Flash (`--speculative-config.method mtp`), DeepSeek V3/V4; OpenHands cites up to 2× from ArcticInference. N-gram speculation is "instant" and zero-memory when output copies input — exactly the whole-file-edit and test-rerun case (vendor docs; no code-specific measured number found). **H** — enable the model's native MTP where available; enable ngram speculation for whole-file edit turns; keep batch size small per server.
- **Continuous batching / parallel slots.** llama.cpp `-cb` on by default, `-np` auto, unified KV by default; Ollama parallel default 1. DevFlow's parallel read-only roles can share a server only if context × parallel fits VRAM; OpenHands' vLLM examples assume TP=2. **M.**
- **Flash attention.** llama.cpp `-fa auto`; LM Studio/OpenHands: enable; required for KV quant in Ollama. **H (trivial).**
- **Cache-aware compaction.** TokenPilot (cited in the ACM write-up): 61–87% cost reduction with 79.2% cache hit rate; Cline notes its summarization reuses the prompt cache so only output tokens cost. **M** — compaction should be scheduled so the summary request itself hits the cached prefix.

---

### 7. Open-weight coding models for local agents (late 2026)

Scores are vendor/aggregator-reported unless noted; hardware from model cards or cited guides.

| Model | Size / active | Ctx | SWE-bench Verified | Terminal-Bench 2.0 | Fits one consumer GPU? |
|---|---|---|---|---|---|
| Qwen3.6-35B-A3B (Apache-2.0, Apr 2026) | 35B / 3B MoE, hybrid Gated-DeltaNet attention, MTP | 256K (1M YaRN) | 73.4 | 51.5 | Yes: Q4_K_M ≈18–20 GB → 24 GB GPU / M4 Pro 24 GB; Q5 → 32 GB (codex.danielvaughan.com 2026-04-16; HF) |
| Qwen3.6-27B dense | 27B | 256K | 77.2 (benchlm) | 59.3 | Q4 fits 24 GB tightly; 32–48 GB comfortable |
| Qwen3.5-27B dense | 27B | — | 75.0 | 41.6 | as above |
| Qwen3-Coder-30B-A3B (non-thinking) | 30.5B / 3.3B | 262K | n/a on card; Agentic Rubrics oracle pass@16 65.6 | — | Yes (Cline/Kilo default local model) |
| Qwen3-Coder-Next (Feb 2026) | 80B / 3B | — | "competitive" (report) | — | 48 GB+ |
| Devstral Small 2 (Apache-2.0, Dec 2025) | 24B dense | 256K | 68.0 | — | "single RTX 4090 or a Mac with 32GB RAM" (HF card); temp 0.15, mistral parser |
| Devstral 2 | 123B | 256K | 72.2 | — | No (TP=8 example) |
| GLM-4.7-Flash (MIT) | 30B / 3B | — | 59.2 | — | Yes; glm47 parser, MTP |
| GLM-5 / 5.1 | large | — | 77.8 / — | 56.2 / 63.5 | No |
| gpt-oss-20b (Apache-2.0) | 21B / 3.6B, MXFP4 | — | 60.7 (high) | — | Yes: 16 GB; harmony format mandatory |
| gpt-oss-120b | 117B / 5.1B | — | 62.4 | 19.1 (Vals mirror) | 80 GB |
| Gemma 4 31B (Apache-2.0, Jul 2026) | 31B dense | 256K | 52.0 (per Qwen comparison) | 42.9 | Yes at Q4; KV-quant sensitive |
| Gemma 4 26B-A4B | 26B / 4B | 256K | 17.4 | 34.2 | Yes, but weak agentically |
| DeepSeek V4 Flash (MIT) | 284B / 13B | 1M | 79.0 (Think Max) | 56.9 | No (FP4/FP8 weights, ~150 GB+) |
| Kimi K2.5 / K2.6 | 1T / 32B INT4 | 256K | 76.8 / 80.2 | 50.8 / 66.7 | No |
| MiniMax M2.5 / M2.7 | 229B / — | — | 80.2 / 75.4–80.5 | 57 (M2.7) | No |
| Llama 4 Maverick | 400B / 17B | — | 15.6 (aider polyglot), 5.2 SWE-Pro | — | No, and weak |

Aider polyglot (open models): DeepSeek-V3.2-Exp reasoner 74.2%, R1-0528 71.4%, Qwen3-235B 59.6%, Kimi K2 59.1%, Qwen3-32B 40.0%, gpt-oss-120b 41.8% (aider.chat/docs/leaderboards). Practical reading for DevFlow: on a single 24 GB GPU the realistic agentic choices are Qwen3.6-35B-A3B (best agentic numbers per VRAM, MTP for speed), Qwen3.6-27B (stronger on Verified, slower), Devstral Small 2 (strong Verified at 24B dense), Qwen3-Coder-30B-A3B (best-supported by Cline/Kilo/Qwen Code tooling), gpt-oss-20b (16 GB, weaker tool protocol). 48 GB opens Qwen3.6-27B at Q8 / Qwen3-Coder-Next. **Applicability: High** — DevFlow's model registry should encode these per-model parser/template/sampling/thinking defaults.

---

### 8. Context length vs quality for local models; practical budgets

- **NoLiMa (ICML 2025; adobe-research/NoLiMa).** Effective length = longest context with ≥85% of base score: Llama 3.3 70B 2K (32K score 42.7 vs base 97.3), Llama 3.1 8B 1K (32K: 14.2), Gemma 3 27B <1K (32K: 9.5), Mistral Large 2 2K, Command R+ <1K; 11 of 13 models fall below 50% of baseline at 32K when there is no lexical overlap between question and needle.
- **RULER (NVIDIA).** Threshold 85.6: Llama 3.1 70B effective 64K (128K: 66.6), Llama 3.1 8B 32K, Qwen3-32B >128K borderline (128K: 85.6), Qwen3-30B-A3B 64K (128K: 79.2), Qwen3-8B 32K (64K: 82.1), Qwen3-4B 32K, Mistral-Nemo 16K, GLM4-9B 64K, Qwen2.5-14B-1M >128K (92.2 at 128K). Qwen numbers are vendor-reported.
- **Chroma "Context Rot" (2025-07-14, 18 models incl. Qwen3-235B/32B/8B).** Reliability drops with length for all models; distractors hurt (one distractor already lowers accuracy); low needle–question similarity degrades fastest; focused ~300-token inputs beat full ~113K inputs on LongMemEval for every model; Qwen3-8B stopped attempting 4.21% of repeated-word tasks and emitted random words around 5,000 words.
- **Compression helps small models.** ACON (2025-10/2026-06): peak tokens −26–54% and up to +46% task gain for smaller LMs "attributed to reduced context distraction." SWE-Master's summary-based manager cut MiniMax-M2.1 peak context 55.4K → 28.5K with resolve rate 68.4 → 69.8. OpenHands condenser: ≤half cost, same resolve rate.
- **Vendor cards.** Qwen3 base pretraining at 32K (131K via YaRN); Qwen3-2507/3.6 at 256K; Qwen advises evaluating quality at each length before choosing generation length.

**Recommended budgets (synthesis, Applicability High):** serve ≥64K (minimum 32K) but *plan* every role turn to ≤24–32K of live context for ≤35B models; keep the high-signal material (work order, acceptance criteria, failing test output, the 1–3 files being edited) within the first ~8–16K and at the end; compact at 50–60% (Gemini CLI 0.5; Claude Code article advises ~60%); never rely on retrieval from the middle of a 100K transcript on a local model; measure your own model with a NoLiMa-style probe at 8/16/32K during `ready`.

---

### 9. Verification and quality loops

- **Deterministic gates beat self-assessment.** Anthropic: "if you can't verify it, don't ship it"; Stop hooks; `/goal` evaluator; Hermes verify-on-stop; ForgeCode mandatory reviewer; OpenCode feeds LSP diagnostics into every edit result (harness paper). **H.**
- **End-to-end browser verification.** Anthropic's long-running post says Puppeteer-MCP "as a human user" testing "dramatically improved" results and that unit tests/curl missed end-to-end failures; known gap: native alert modals. Playwright MCP exposes an *accessibility snapshot* ("better than screenshot"), no vision model needed, deterministic actions, ~70 tools, opt-in vision/network/storage/test-assertion capabilities (github.com/microsoft/playwright-mcp). **H** — for a harness that ships web apps, the QA role should drive Playwright snapshots (text, cheap for local models) rather than screenshots, and acceptance tests should be recorded as Playwright scripts the engineer cannot edit.
- **Self-repair retry budgets.** Debugging Decay Index (2025-07, 18 models incl. Llama 3.1 8B, Qwen2.5-Coder, DeepSeek-Coder 6.7B/16B, Codestral): most models lose 60–80% of debugging capability within 2–3 attempts; fresh restarts at computed points beat continued debugging (Llama 3.1 8B 72.56 → 82.82%; DeepSeek-Coder-V2 16B 84.1 → 92.1%). "How Many Tries" (2026-04, Llama 3.1 8B … Gemini 2.5 Pro): self-repair adds +4.9–17.1 pp (HumanEval) / +16–30 pp (MBPP), most gain in the first two rounds; assertion (logic) errors repaired only ~45%; CoT repair prompts +5.5 pp. "Is Three the Magic Number?" (2026-07): first 3–4 iterations capture most gains; orchestration and feedback design matter more than model choice. Aider: 3 re-prompts. **H** — DevFlow: cap in-context repair at 2–3 attempts, then *restart the work order in a fresh context* with the failing test output and a short diagnosis; treat assertion failures as the signal to escalate to the architect/stronger model.
- **LLM-as-judge for code.** CodeJudgeBench (2025-07): thinking judges > non-thinking; Qwen3-8B-thinking beat 70B trained judges; pairwise beats pointwise; judgments shift with response order; keep raw responses incl. comments. Agentic Rubrics: repo-grounded rubric + weak judge (GPT-5-mini 52.6 ≈ GPT-5 55.0) is the best verifier; execution-free verifiers overweight the agent's narration (dropping the trajectory cut Best@26 from 42.8 to 37.6). **H** — use a *rubric generated by the architect at work-order creation* (file-change, spec-alignment, integrity, runtime axes, weighted 1–3) and a thinking local judge grading pairwise where possible; never let the judge alone mark a feature passing.
- **Test quality / mutation testing.** SWE-Mutation (2026-05/06): top agents detect <40% of realistic mutants (Claude Sonnet 4.5 VRR 29.8–40.4%, RDR 63.7–71.7%; DeepSeek-V3.1 VRR 10.2%); worse for C/C++ and JS/TS. ClassEval study (2026-09): coverage is near ceiling for all configs and uninformative; executability is the first hurdle; model choice > prompt choice. MUTGEN (TSE 2026): mutation feedback in the prompt significantly beats coverage-driven generation; a 100%-coverage suite can have a 4% mutation score. **M** — add a lightweight mutation pass (e.g. mutmut/Stryker/cosmic-ray per stack pack) on the acceptance suite for the highest-priority features, and reject test suites that don't execute before counting them.
- **Hybrid verifier.** R2E-Gym: hybrid execution + judge 51.0 vs either alone ~42–44; adding test-agent rollouts is the cheapest lever. **M.**
- **Reviewer scoping.** Devin Review averages 2 bugs/PR with a clean, diff-only context; Anthropic warns gap-finders over-report — scope findings to correctness. **H.**

---

### 10. Memory and project knowledge across sessions

- **Files over vector stores.** Harness source study: none of 11 harnesses use embeddings; all use ripgrep/tree-sitter/glob + Markdown context files (arXiv 2609.00006). Anthropic: start agentic, add semantic search for speed/variety. Cursor: +12.5% accuracy on large repos with a *trained* embedding model. Augment: +1.6–2 pts on SWE-bench Pro, no ablation. **H** — DevFlow: ripgrep + tree-sitter symbol map first; optional embedding index gated on repo size.
- **Repo map.** Aider: 1K-token graph-ranked symbol map, expanded when nothing is in chat; Meta-Harness: snapshot the sandbox before the loop (saves 2–5 turns). **H** — architect role maintains a `REPO_MAP.md`/JSON regenerated per sprint; inject ≤1–2K tokens per engineer turn.
- **Progress files and ledgers.** Anthropic's `claude-progress.txt` + JSON feature list; Codex "memories"; Claude Code auto-memory (first 200 lines / 25 KB), subagent `memory: project` directories; Gemini CLI hierarchical GEMINI.md written by the model with ordinary edit tools; Windsurf auto-memories per workspace. **H** — give each DevFlow role a bounded memory file (cap ~25 KB, load first 200 lines) that survives compaction and is versioned in the project repo (Sprint Record).
- **Progressive disclosure.** Claude Code skills (descriptions at startup, body on use), OpenHands skills with `triggers`/`paths`, Windsurf `model_decision`/`glob`, Claude Code `.claude/rules/` with `paths:`. **H** — stack-pack guidance should load by path/keyword, not globally.
- **Avoid re-reading.** Claude Code re-reads only the 5 most-recently modified files after compaction and references, not reloads, files >5K tokens; Codex re-reads ≤5 files within 50K; OpenHands keeps the full event log on disk; ACM offloads raw messages and provides `query_memory`. **H** — DevFlow: file-read tool returns a hash + line count; if the file is already in context and unchanged (same hash), return "unchanged since turn N" instead of content.
- **Event-sourced state.** OpenHands V1's append-only per-event files cut system-attributable errors 61% in production and give ms-level crash recovery — a natural fit for LangGraph checkpointers. **M-H.**

---

### Top 15 transferable techniques (ranked by expected impact × ease for a local-model DevFlow)

1. **Feature ledger in JSON + one-feature-per-turn + session-start ritual** (`init.sh`, read progress, smoke test, pick highest-priority failing item; only the verifier flips `passes`). Evidence: Anthropic long-running harness post. Fixes the four observed failure modes directly.
2. **Deterministic stop gate**: a work order cannot close until its acceptance script (unit + Playwright accessibility-snapshot E2E) passes; LLM reviewer is a second, diff-only, correctness-scoped opinion. Evidence: Claude Code Stop hooks/`/goal`, Anthropic E2E finding, Devin Review, ForgeCode.
3. **Stable-prefix, append-only prompt layout + constant tool schemas + pinned llama.cpp slots / vLLM prefix caching** (`--cache-reuse`, `id_slot`, `--enable-prefix-caching`, `OLLAMA_KEEP_ALIVE=-1`). Evidence: Anthropic caching rules, llama.cpp README/#13606, PrefixBench. Biggest latency win per turn.
4. **Context floor and budget**: serve ≥64K (≥32K hard minimum, verified in `ready`), plan ≤24–32K live context per turn for ≤35B models, compact at 50–60%. Evidence: Ollama docs, OpenHands/Kilo/Roo floors, NoLiMa/RULER/Context Rot, Gemini CLI 0.5 default.
5. **Three-tier compaction**: prune stale tool outputs → summarize agent trajectory only (keep work-order/user text verbatim, re-inject role charter fresh) → re-read ≤5 last-edited files capped at ~5K tokens each; keep raw transcript on disk with a `recall` tool. Evidence: Claude Code, Codex measurements, OpenHands condenser (same resolve rate, ≤½ cost), ACM.
6. **Per-model edit-format selection by measured well-formed rate** (whole for small files/weak models, lenient search/replace otherwise; never line numbers) and **architect/editor split** so a thinking model plans and a cheap pass edits. Evidence: Aider benchmarks (3× laziness fix, 9× fewer errors from lenient matching, +3–5 pts from the split, 100% vs 92–95% well-formed).
7. **Minimal, flat tool set per role (3–6 tools), MCP off for local models, `parallel_tool_calls=false`, one action per turn** for ≤35B models. Evidence: Anthropic ACI guidance, Factory Droid, mini-SWE-agent, Kilo local guidance, Qwen parser warnings.
8. **Schema-constrained inter-role artifacts** (plan, work order, test list, review verdict) using JSON schema with a bounded `rationale` field first, via vLLM structured outputs / Ollama `format` / llama.cpp `--json-schema`, with `tool_choice=required` on artifact turns. Evidence: .txt rebuttal (no reasoning loss when prompted correctly), llguidance timings, vLLM docs.
9. **Model registry with per-family tool parser, chat template, sampling and thinking defaults** (hermes / qwen3_coder / mistral / glm47 / openai-harmony; Qwen temps by mode; gpt-oss effort levels; Devstral 0.15). Evidence: vLLM tool-calling doc, llama.cpp function-calling doc, HF cards.
10. **Thinking budgets per role and turn** (`--reasoning-budget`, `enable_thinking`): on and bounded for PM/architect/reviewer/judge and for repair-after-failure; off for routine edit loops; strip thinking from history unless the card says preserve. Evidence: gpt-oss 37→61 by effort, DeepSeek V4 +5 pts, Aider Qwen3 thinking run worst with 58 malformed outputs, CodeJudgeBench.
11. **Repair budget 2–3 then fresh-context restart with failing output** (and escalate assertion-type failures to the architect / stronger model). Evidence: Debugging Decay Index, "How Many Tries", "Is Three the Magic Number".
12. **Hard caps on injected instructions**: project rules ≤32 KiB total, role rules ≤12K chars, global ≤6K, path/keyword-triggered stack-pack rules, compact prompt variant ≈10% size for local models. Evidence: Codex `project_doc_max_bytes`, Windsurf caps, Cline compact prompt, Claude Code CLAUDE.md guidance.
13. **Loop and failure-class detection as hooks**: identical-call breaker at 3–5, stuck-after-N-failures, premature-termination check (ledger says failing but agent says done), PATH/tool-availability bootstrap in the first prompt. Evidence: Gemini CLI/OpenCode/Hermes, Terminal-Bench failure taxonomy (24% "command not found").
14. **Rubric-based verification**: architect writes a repo-grounded weighted rubric per work order; a thinking local judge grades pairwise; optional k=2–4 rollouts selected by acceptance tests + rubric for the hardest work orders. Evidence: Agentic Rubrics (+4 pts Best@16 at ~half the cost of test-based selection), R2E-Gym hybrid, SWE-Master TTS@8.
15. **Inference knobs with measured safety**: native MTP/EAGLE where the model ships it, ngram speculation on whole-file-edit turns, flash attention on, KV q8_0 only for Qwen-family (f16 for Gemma), never q4_0 for agent roles, `OLLAMA_NUM_PARALLEL` sized to VRAM. Evidence: vLLM/llama.cpp docs, localbench KL study, llama.cpp tool-calling warning, premai acceptance-rate data.

Honourable mentions: single-threaded writes with parallel read-only roles (Cognition); alternate two local models per turn as a diversity source (mini-SWE roulette); event-sourced per-event state files for crash recovery (OpenHands V1); embedding index only above ~1K files (Cursor).

---

### Sources

Anthropic / Claude Code
- https://anthropic.com/engineering/effective-harnesses-for-long-running-agents (2025-11-26)
- https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents (2025-09-29, upd. 2026-01-06)
- https://www.anthropic.com/engineering/building-effective-agents (2024-12-19)
- https://claude.com/resources/articles/building-agents-with-the-claude-agent-sdk (2025-09-29)
- https://code.claude.com/docs/en/context-window.md · /how-claude-code-works.md · /model-config.md · /best-practices.md · /sub-agents.md · /hooks.md · /glossary.md
- https://platform.claude.com/docs/en/build-with-claude/prompt-caching

OpenAI Codex
- https://learn.chatgpt.com/docs/glossary
- https://gist.github.com/osolmaz/a38acf6e522df67530e3ed47c80fdcd5 (compaction measurements, 2026-07/09)
- https://codex.danielvaughan.com/2026/04/14/context-compaction-deep-dive-codex-cli-claude-code-opencode/
- https://codex.danielvaughan.com/2026/04/19/openai-codex-cli-official-documentation-guide/
- https://codex.danielvaughan.com/2026/08/02/acm-agentic-context-management-long-horizon-tasks-codex-cli-compaction-external-memory-retrieval/
- https://fast.io/resources/codex-context-window.md

Cognition / Devin
- https://cognition.com/blog/dont-build-multi-agents (2025-06-12)
- https://cognition.com/blog/multi-agents-working (2026-04-22)
- https://cognition.com/blog/devin-2 (2025-04-03)
- https://docs.devin.ai/desktop/cascade/memories.md

Cursor / Augment / Factory / Amp
- https://cursor.com/blog/composer (2025-10-29) · https://cursor.com/blog/semsearch (2025-11-06)
- https://www.zenml.io/llmops-database/enhancing-ai-coding-agent-performance-with-custom-semantic-search
- https://augmentcode.com/blog/auggie-tops-swe-bench-pro (2026-02-04)
- https://factory.com/news/terminal-bench (2025-09-25)
- https://ampcode.com/manual

Cline / Roo / Kilo / Goose / Qwen Code / Gemini CLI / Kimi
- https://cline.bot/blog/local-models (2025-08-28) · https://docs.cline.bot/running-models-locally/overview.md · https://docs.cline.bot/running-models-locally/read-me-first · https://docs.cline.bot/features/auto-compact.md
- https://roocodeinc.github.io/Roo-Code/features/intelligent-context-condensing/ · https://roocodeinc.github.io/Roo-Code/advanced-usage/local-models/ · https://docs.ollama.com/integrations/roo-code.md
- https://kilo.ai/docs/providers/ollama
- https://github.com/block/goose
- https://github.com/QwenLM/qwen-code · https://qwen.readthedocs.io/en/latest/framework/function_call.html · https://qwen.readthedocs.io/en/latest/getting_started/concepts.html
- https://geminicli.com/docs/cli/settings/ · https://geminicli.com/docs/reference/commands · https://geminicli.com/docs/cli/configuration/
- https://www.kimi.com/help/kimi-code/code-docs-index

OpenHands / SWE-agent / Aider
- https://arxiv.org/abs/2511.03690 (OpenHands SDK, MLSys 2026) · https://docs.openhands.dev/sdk/arch/condenser · https://openhands.dev/blog/openhands-context-condensensation-for-more-efficient-ai-agents (2025-04-09) · https://docs.openhands.dev/openhands/usage/llms/local-llms · https://docs.openhands.dev/openhands/usage/prompting/microagents-overview
- https://github.com/SWE-agent/mini-swe-agent · https://www.swebench.com/bash-only.html · https://www.swebench.com/post-250820-mini-roulette.html (2025-08-19)
- https://aider.chat/docs/more/edit-formats.html · https://aider.chat/docs/unified-diffs.html · https://aider.chat/2024/09/26/architect.html · https://aider.chat/2025/05/08/qwen3.html · https://aider.chat/docs/leaderboards/ · https://aider.chat/docs/leaderboards/notes.html · https://aider.chat/docs/repomap.html

Harness studies / benchmarks
- https://arxiv.org/abs/2609.00006 (Harness Engineering, 11 systems, 2026-07)
- https://pub.towardsai.net/we-read-20-agent-harnesses-15-compact-your-context-automatically-10-let-you-set-when-2b36f2d57bf6 (2026-09-24)
- https://arxiv.org/abs/2601.11868 (Terminal-Bench, 2026-01-17) · https://codex.danielvaughan.com/2026/04/09/harness-performance-terminal-bench/
- https://www.benchlm.ai/benchmarks/terminal-bench-2 · https://benchlm.ai/benchmarks/swe-bench-verified · https://www.morphllm.com/swe-bench-pro · https://benchlm.ai/benchmarks/bfcl-v4
- https://arxiv.org/abs/2504.07164 (R2E-Gym) · https://arxiv.org/abs/2601.04171 (Agentic Rubrics) · https://arxiv.org/abs/2602.03411 (SWE-Master) · https://arxiv.org/abs/2607.23809 (ACM) · https://arxiv.org/abs/2510.00615 (ACON)

Small-model reliability / structured output / tool calling
- https://docs.vllm.ai/en/stable/features/tool_calling/ · https://docs.vllm.ai/en/stable/features/structured_outputs/ · https://discuss.vllm.ai/t/as-of-july-2026-what-are-some-general-tips-in-improving-the-speed-of-guided-decoding-in-vllm/2845
- https://github.com/guidance-ai/llguidance · https://docs.ollama.com/capabilities/structured-outputs · https://insiderllm.com/guides/structured-output-local-llms/
- https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md · https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md
- https://blog.dottxt.ai/say-what-you-mean.html · https://arxiv.org/abs/2408.02442
- https://arxiv.org/abs/2511.22138 (TinyLLM) · https://arxiv.org/abs/2608.22472 (IFFC) · https://arxiv.org/abs/2605.00737 (To Call or Not to Call)
- https://docs.morphllm.com/guides/apply

Inference efficiency
- https://docs.vllm.ai/en/stable/features/automatic_prefix_caching/ · https://arxiv.org/abs/2609.19657 (PrefixBench-H100)
- https://github.com/ggml-org/llama.cpp/discussions/13606 (KV cache reuse tutorial, 2025-05-17)
- https://docs.ollama.com/context-length · https://docs.ollama.com/faq · https://fast.io/resources/ollama-context-window.md
- https://localbench.substack.com/p/kv-cache-quantization-benchmark (2026-04-24)
- https://blog.premai.io/speculative-decoding-2-3x-faster-llm-inference-2026 · https://docs.vllm.ai/en/stable/features/speculative_decoding/

Models
- https://huggingface.co/Qwen/Qwen3.6-35B-A3B · https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct · https://arxiv.org/abs/2603.00729 (Qwen3-Coder-Next) · https://codex.danielvaughan.com/2026/04/16/qwen36-35b-a3b-local-agentic-coding-breakthrough/
- https://huggingface.co/mistralai/Devstral-Small-2-24B-Instruct-2512 · https://huggingface.co/mistralai/Devstral-2-123B-Instruct-2512
- https://huggingface.co/openai/gpt-oss-20b · https://huggingface.co/zai-org/GLM-4.7-Flash · https://huggingface.co/google/gemma-4-31B-it
- https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash · https://huggingface.co/moonshotai/Kimi-K2.5 · https://huggingface.co/moonshotai/Kimi-K2-Thinking · https://huggingface.co/MiniMaxAI/MiniMax-M2.5

Long context
- https://trychroma.com/research/context-rot (2025-07-14) · https://arxiv.org/abs/2502.05167 · https://github.com/adobe-research/NoLiMa · https://github.com/NVIDIA/RULER

Verification
- https://github.com/microsoft/playwright-mcp
- https://arxiv.org/abs/2604.10508 (How Many Tries) · https://huggingface.co/papers/2607.05197 (Is Three the Magic Number) · https://arxiv.org/abs/2506.18403 (Debugging Decay Index)
- https://arxiv.org/abs/2507.10535 (CodeJudgeBench) · https://benchmarklist.com/benchmarks/swe_mutation_can_llms_generate_reliable_test_suites_in_software_engineering/ · https://arxiv.org/abs/2506.02954 (MUTGEN) · https://arxiv.org/abs/2609.24341

Notes for the main session (worth saving to project memory): local-model defaults derived above — serve ≥64K ctx (32K hard floor, verified in `ready`), compact at 50–60%, q8_0 KV only for Qwen family, parallel_tool_calls off for ≤35B, repair budget 2–3 then fresh restart, Qwen3.6-35B-A3B / Qwen3.6-27B / Devstral Small 2 / Qwen3-Coder-30B-A3B as the 24 GB-class agentic candidates.

---

<a id="r2"></a>
## Part R2 — Research digest (2026-10-18, session 2; the R-numbers the plan cites)

**Linked plan items**

| R-number | Plan items citing it |
|---|---|
| R1 | [Appendix 2](improvement-plan.md#plan-appendix-2), [Part 11](improvement-plan.md#plan-part-11), [Appendix 2.2](improvement-plan.md#plan-appendix-2-2) |
| R2 | [Appendix 2](improvement-plan.md#plan-appendix-2), [Z](improvement-plan.md#plan-z), [AC](improvement-plan.md#plan-ac), [AD](improvement-plan.md#plan-ad), [Appendix 2.2](improvement-plan.md#plan-appendix-2-2) |
| R3 | [Appendix 2](improvement-plan.md#plan-appendix-2), [AD](improvement-plan.md#plan-ad), [Appendix 2.2](improvement-plan.md#plan-appendix-2-2) |
| R4 | [Appendix 2](improvement-plan.md#plan-appendix-2), [AD](improvement-plan.md#plan-ad), [Appendix 2.2](improvement-plan.md#plan-appendix-2-2) |
| R5 | [Appendix 2](improvement-plan.md#plan-appendix-2), [M (concrete)](improvement-plan.md#plan-m-concrete), [Appendix 2.2](improvement-plan.md#plan-appendix-2-2) |
| R6 | [Appendix 2](improvement-plan.md#plan-appendix-2), [M (concrete)](improvement-plan.md#plan-m-concrete), [Appendix 2.2](improvement-plan.md#plan-appendix-2-2) |
| R7 | [Appendix 2](improvement-plan.md#plan-appendix-2), [X](improvement-plan.md#plan-x), [AA](improvement-plan.md#plan-aa), [Appendix 2.2](improvement-plan.md#plan-appendix-2-2) |
| R8 | [Appendix 2](improvement-plan.md#plan-appendix-2), [Y](improvement-plan.md#plan-y), [Z](improvement-plan.md#plan-z), [Appendix 2.2](improvement-plan.md#plan-appendix-2-2) |
| R9 | [Appendix 2](improvement-plan.md#plan-appendix-2), [Z](improvement-plan.md#plan-z), [Appendix 2.2](improvement-plan.md#plan-appendix-2-2) |
| R10 | [W](improvement-plan.md#plan-w), [Appendix 2.2](improvement-plan.md#plan-appendix-2-2) |
| R11 | [W](improvement-plan.md#plan-w), [Z](improvement-plan.md#plan-z), [Appendix 2.2](improvement-plan.md#plan-appendix-2-2) |
| R12 | [X](improvement-plan.md#plan-x), [Appendix 2.2](improvement-plan.md#plan-appendix-2-2) |
| R13 | [X](improvement-plan.md#plan-x), [Appendix 2.2](improvement-plan.md#plan-appendix-2-2) |
| R14 | [M (concrete)](improvement-plan.md#plan-m-concrete), [Appendix 2.2](improvement-plan.md#plan-appendix-2-2) |
| R15 | [Y](improvement-plan.md#plan-y), [Appendix 2.2](improvement-plan.md#plan-appendix-2-2) |
| R16 | [Z](improvement-plan.md#plan-z), [Appendix 2.2](improvement-plan.md#plan-appendix-2-2) |
| R17 | [AA](improvement-plan.md#plan-aa), [Appendix 2.2](improvement-plan.md#plan-appendix-2-2) |
| R18 | [AB](improvement-plan.md#plan-ab), [Appendix 2.2](improvement-plan.md#plan-appendix-2-2) |
| R19 | [AI](improvement-plan.md#plan-ai), [Appendix 2.2](improvement-plan.md#plan-appendix-2-2) |
| R20 | [Part 11](improvement-plan.md#plan-part-11), [Appendix 2.2](improvement-plan.md#plan-appendix-2-2) |
| R21 | [Part 11](improvement-plan.md#plan-part-11), [Appendix 2.2](improvement-plan.md#plan-appendix-2-2) |

### 13.6 Research report digest (landed 17:45 JST) — frontier harnesses, local serving, agent UX
Full report from the web-research task (primary sources 2025-06→2026-10).
Kept here because the research tool's output is not otherwise persisted.
R-numbers are cited from `docs/improvement-plan.md` Appendix 2.

**Headline**: "one writer, many advisors." Local-model failures are
*interface* failures (tool-call format, edit format, context truncation,
quantization) more than reasoning failures.

- R1 Anthropic "Effective harnesses for long-running agents" (2025-11-26):
  initializer writes `init.sh`, progress file, initial commit, JSON feature
  list with every feature `passes:false`; each session reads progress, runs
  a basic e2e first, implements ONE feature, commits, logs. Adopt as
  backbone.
- R2 Anthropic "Harness design for long-running apps" (≈2026-03-24):
  planner (told NOT to over-specify implementation — errors cascade) /
  generator / evaluator negotiating "sprint contracts"; evaluator drives
  the app via Playwright; context *resets* needed (Sonnet 4.5 "context
  anxiety"); ~6 h/$200 per 16-feature app; evaluator "unnecessary
  overhead" when the task is within the generator's ability → for weaker
  local models the evaluator gives *more* lift.
- R3 Cognition "Multi-agents: what's actually working" (2026-04-22): works
  "when writes stay single-threaded"; clean-context Devin Review catches
  ~2 bugs/PR, 58% severe, even on Devin's own PRs; weak-primary +
  strong-advisor failed ("quality ceiling set by the primary"); Manager
  Devins: over-prescription and assumed shared state are the failure
  modes. "Don't build multi-agents" (2025-06-12): edit-apply lesson — a
  small model rewriting a whole file from a markdown explanation beat a
  large model emitting a diff (R15).
- R4 MAST (arXiv 2503.13657): 14 failure modes; spec/design 41.8%,
  inter-agent misalignment 36.9%, verification 21.3%; ChatDev 33.3% on
  ProgramDev, +9.4% from better prompts/topology; verifiers do low-level
  checks (compiles?) and miss the requirement.
- R5 "Flat score, amplified failures" (arXiv 2607.27275): INT4 looked free
  on τ²-bench scores but out-of-list tool-call names rose 19.5%→38.3%;
  community: Qwen3.6 Q4 breaks tool JSON/diffs, Q5_K_M/Q6 fix most,
  collapse past ~30k ctx (anecdotal). Single-turn HumanEval unaffected by
  Q4. → Q6/Q8/FP8 for the tool-calling implementer; Q4 OK for summarisers.
- R6 Ollama: since commit 0334ffa6 (2026-02-02) default `num_ctx` is
  VRAM-based (4,096 <24 GiB; 32,768 24–48; 262,144 above); docs recommend
  ≥64k for agents; `/v1` ignores `num_ctx` → set `OLLAMA_CONTEXT_LENGTH`.
  "#1 silent failure for local agents."
- R7 Cline v3.35 (2025-10-31): native tool calling only for frontier
  families; tool defs as API params cut tokens ~15%/request; local models
  get XML-in-prompt; issues #10843 (Qwen emits JSON into XML parser →
  loop), #13008 (syntax change broke Ollama+Qwen3.6-35B-A3B), #7424
  (Compact Prompt for local), PR #12835 (explicit xml tool mode). Lesson:
  tolerant multi-format parser; version-stable tool syntax.
- R8 aider: edit formats whole/diff/diff-fenced/udiff/patch/editor-*;
  unknown models default to `whole` ("easiest format"); leaderboard
  reports well-formed-edit % separately; llama3-70b 73.5% well-formed on
  diff (secondary); v0.19 udiff took GPT-4 Turbo 20%→61% on the laziness
  bench; `--architect`/`--editor-model`/`--weak-model`.
- R9 JetBrains "The Complexity Trap" (arXiv 2508.21433, 2025-08-29): LLM
  summarisation +15% trajectory length vs raw, +13% vs observation
  masking; masking halves cost at equal solve rate.
- R10 mini-SWE-agent (~100 lines, bash-only, >74% SWE-bench Verified) as
  control harness; same-harness open-model run 2026-02-17: MiniMax M2.5
  75.8%, GLM-5 72.8%, Kimi K2.5 70.8%, DeepSeek V3.2 70.0% vs Opus 4.5
  76.8%; vendor claims Qwen3.6-27B 77.2%, Qwen3.6-35B-A3B 73.4%, Devstral
  Small 2 68.0% (harness-dependent; OpenAI stopped reporting SWE-bench
  Verified 2026-02).
- R11 OpenHands condenser: up to 2× per-turn cost cut, event-sourced and
  replayable; default max_size=80 keep_first=4; SDK paper arXiv 2511.03690.
- R12/R13 Claude Code: plan mode = write tools not exposed; permission
  mode ladder; ExitPlanMode gate; hooks are enforcement, CLAUDE.md is
  advice; checkpoints miss bash side-effects → use git per step; subagents
  for read-only work.
- R14 vLLM `--enable-auto-tool-choice --tool-call-parser <family>`
  (qwen3_coder/qwen3_xml/llama3_json…); Qwen3.5/3.6 recipe: MTP-1 spec
  decoding for low-concurrency latency (disable prefix caching in that
  mode); llama.cpp `--jinja`, native handlers per family else Generic
  (more tokens), lazy GBNF grammars after tool trigger (PR #9639),
  `--chat-template-file` overrides; JSON Schema→GBNF automatic. Security:
  vLLM GHSA-79j6-g2m3-jgfw (`qwen3_coder` parser `eval()` RCE) — pin.
- R16 Ralph loop (Huntley 2025-07-14): fresh context per iteration, state
  in files/git, mandatory `--max-iterations` + completion promise.
- R17 Anthropic "Effective context engineering" (2025-09-29): attention
  budget, context rot, just-in-time retrieval, compaction + notes +
  subagents; Manus: KV-cache hit rate the key production metric, mask
  don't remove tools; Lost-in-the-middle (TACL 2024), Chroma context rot.
- R18 Cursor 2.0 (2025-10-29) 8 parallel agents; Plan mode 1.7/2.1 with
  clarifying-question UI → adapt only at planning on a single GPU.
- R19 Memory as plain markdown files navigated with file tools; `LESSONS.md`
  reviewer-appends/planner-reads.
- R20 UX: Jules plan approval + browser notifications + Planning Critic
  (−9.5% failures, vendor); Devin Interactive Planning (2025-04-03), Devin
  Review hunk grouping with confidence/severity (2026-01-21); Copilot draft
  PR as work surface, mission-control steering (2025-10-28); Codex
  evidence citations of terminal logs/tests; Lovable/Bolt/v0 live preview +
  versioned rollback mapped to commits.
- R21 Huang et al. arXiv 2512.14012 (2025-12-16): professional devs
  "control the agents through planning and supervision"; "The Work Behind
  Delegation" arXiv 2609.24234: supervisory demand to understand unwritten
  work; Chen et al. arXiv 2507.08149.
- Top-20 ranked recommendations from the report (verbatim order): 1 fix
  context sizing and verify at startup; 2 single writer; 3 feature list
  as source of truth; 4 one feature per fresh context with caps; 5
  clean-context evaluator that executes; 6 per-model tool-call adapter;
  7 grammar/JSON-schema constrained decoding for structured artifacts;
  8 per-model edit format by calibration; 9 architect/editor split; 10
  avoid INT4 for the tool-calling implementer; 11 remove tools instead of
  forbidding; 12 hooks over prompts; 13 stable short system prompt +
  prefix caching; 14 condensation with template + resets at 60–70%; 15
  loop detection → reset → escalate → human; 16 plan critic; 17 git
  per step + no-network container; 18 append-only event log → OTel; 19 UI
  essentials; 20 model selection on your own harness.
- Not verified by the report (do not copy specifics): Goose, Amp,
  Windsurf, Augment, Factory, Replit, Gemini CLI internals,
  CrewAI/LangGraph patterns, AgentCoder, Roo/Kilo internals, BFCL/Tau
  tables, OTel GenAI conventions, Langfuse.

Mapping to Appendix 2: #1→M.1/W.3; #2 already (work orders); #3→Part 11
plan-first (criteria as feature list) + existing locked suite; #4→Z.3;
#5→AD/AF (+ existing acceptance); #6/#7→M.1–M.2; #8/#9→Y; #10→M.6;
#11/#12→X; #13→AA/X.4; #14→Z; #15→existing L.5 + Z.3; #16→existing
L.7/validator (plan critic = judgement-model plan review, Q-amend);
#17→existing; #18→W.4; #19→Part 11; #20→W.

---

<a id="r3"></a>
## Part R3 — Frontier harness research (2026-10-18, session 1)

**Linked plan items**

| Theme | Plan items |
|---|---|
| T1 Context | [O](improvement-plan.md#plan-o), [Z](improvement-plan.md#plan-z), [AA](improvement-plan.md#plan-aa), [BJ](improvement-plan.md#plan-bj) |
| T2 Loop (plan first) | [L.7](improvement-plan.md#plan-l-7), [BB](improvement-plan.md#plan-bb), [UI 15.4](improvement-plan.md#plan-ui-15-4) |
| T3 Tools | [M](improvement-plan.md#plan-m), [X](improvement-plan.md#plan-x), [Y](improvement-plan.md#plan-y) |
| T4 Robustness (structured control plane) | [M](improvement-plan.md#plan-m) |
| T5 Quality (lint/test after every edit) | [D](improvement-plan.md#plan-d), [J](improvement-plan.md#plan-j), [P](improvement-plan.md#plan-p) |
| T6 Local realities | [S](improvement-plan.md#plan-s), [N](improvement-plan.md#plan-n), [AB](improvement-plan.md#plan-ab) |

### 11. Frontier harness research (subagent 8408a576 — COMPLETE)

Full report persisted on disk: .langchain/research/frontier-harness-report.md
(+ raw notes .langchain/research/notes.md). Method: direct fetches of official
docs/blogs/repos/arXiv (web_search unavailable); community-sourced claims
labeled. Products: Claude Code+SDK, Codex CLI/Cloud, Gemini CLI, Jules,
OpenHands SDK, SWE-agent/mini-swe-agent, Aider, Cline, Roo, Devin, Amp,
Cursor, Factory, Copilot agent, Deep Agents/Open SWE, MetaGPT/ChatDev/
Magentic-One, vLLM/llama.cpp, SWE-bench/Terminal-Bench/METR.

Key points by theme (URLs in the saved report):
- T1 Context: Claude Code startup budget (~4.2k sys prompt, memory index 25KB,
  tool NAMES only, skill one-liners); compaction ~95% w/ structured summary +
  DISK RE-INJECTION (CLAUDE.md, plan, 5 recent files as paths, skill bodies);
  Anthropic compact-2026-01-12 API (trigger ≥150k default, min 50k); Codex
  per-model 180k/244k, summary "for another LLM that resumes the task",
  effective 95%; Gemini 70% compress; OpenHands condenser replaces first half
  of events; tool-output management separate (clear old outputs FIRST, >10k
  chars → file+preview; ClearToolUsesEdit keep-3); subagents = context
  isolation (Codex cites context-rot); dissent: Amp compaction-free (Handoff/
  Fork), Cline /newtask + /deep-planning fresh task, Cognition single thread +
  fine-tuned compressor. ADOPTION: compact EARLIER (~50–60% of usable window
  for small models), summary written for the resuming LLM, re-inject from
  disk, cheap summarizer model, offload big outputs to files.
- T2 Loop: plan-first (Claude plan mode, Jules plan approval, Cline Plan/Act,
  Open SWE); LIVING TODO re-injected every ~6 msgs (Cline Focus Chain);
  orchestration: single-threaded lead + READ-ONLY subagents, parallel writers
  only w/ worktrees (Cognition+Codex+Claude converge); role pipelines w/
  FILE ARTIFACTS as interface (MetaGPT SOP) beat chatty roles (ChatDev);
  Magentic-One task/progress LEDGERS AS FILES + re-plan on error;
  verification in-loop: runnable checks, Claude /goal separate evaluator
  every turn, Stop hooks block turn-end until check passes; Devin "easy to
  verify"; Copilot CI iteration; RubricMiddleware. Escalation: Gemini loop
  detection, Jules auto-retry→fail+notify, Claude "corrected twice → /clear".
- T3 Tools: mini-swe-agent BASH-ONLY, no tool-calling API, linear history,
  >74% SWE-bench Verified w/ frontier, "any model"; SWE-agent ACI guardrails:
  LINT-GATED EDITS (invalid rejected at tool level), 100-line windowed reads,
  terse search (only files w/ ≥1 match), EXPLICIT empty-output message;
  Aider edit-format compliance: whole-file ~100% at 32B vs ~73% diff;
  read-before-edit + unique old_string (Claude Edit); repo maps (tree-sitter,
  ~1k tokens, dynamic) over blind reads; Codex sandbox matrix + auto_review
  classifier agent (fail-closed, open policy.md); Claude Auto mode separate
  classifier model. ADOPTION: bash-first FALLBACK execution mode for
  tool-call-unreliable models; whole-file default for weak editors; ACI
  micro-guardrails; small classifier call for dangerous actions (20-40B can
  classify itself cheaply).
- T4 Robustness: grammar-enforce CONTROL-PLANE decisions (plan JSON, todo,
  verdicts, finish) but NOT free-form coding turns; vLLM "guaranteed
  parsable — not high-quality" + describe schema in prompt;
  enable_in_reasoning caveat for Qwen3-Coder; --tool-strict-level
  function|parameter; ToolErrorMiddleware pattern (exception → sanitized
  error ToolMessage); OpenHands LLM_NUM_RETRIES=4 + LLM_DROP_PARAMS;
  prefix-stable prompts + vLLM --enable-prefix-caching / llama.cpp slot
  cache; ROUTING: Cursor Router (complexity predictor, 75% uplift bar,
  cache-miss cost; above-Fable satisfaction at −68% cost), Codex per-subagent
  model+effort, Amp Dial + role-pinned models + small system models for
  compaction, Gemini pro→flash fallback, OpenHands Index guidance
  (strongest for long/high-stakes, cheaper routine, stronger planning/
  debugging/review); Cursor Composer = harness-RL-trained own model;
  mini-roulette (random model switching per instance) BEAT either model alone.
- T5 Quality: auto-lint/auto-test after EVERY edit w/ error feedback (Aider);
  TDD-lite (/test-add failing tests first); adversarial reviewer subagent in
  FRESH context w/ NARROW correctness-gap rubric (reviewers over-report —
  restrict!); Writer/Reviewer split; /goal evaluator; Open SWE learns repo
  review preferences from historical feedback; METR: RELIABILITY not raw
  reasoning drives long-task completion (arXiv:2503.14499) — spend harness
  complexity on gates, not fancier prompts.
- T6 Local realities: OpenHands 2026 first local recommendation =
  Qwen3.6-35B-A3B CLASS (owner's model!): ≥24GB VRAM quantized, ctx ≥22k
  REQUIRED (4096 = broken), 32,768 + flash attention recommended, vLLM
  --enable-prefix-caching, speculation ≤2× (ArcticInference); documented
  failure "chatbot-only, refuses tools". Qwen3-Coder-30B-A3B: 60.4% SWE-bench
  Verified @ ~19GB Q4 (best-in-24GB); Qwen3.6-35B-A3B: Terminal-Bench 24.6%
  = 24GB champion; bash-only board: Qwen2.5-Coder-32B collapses to 9.0%
  (scaffolding matters!); DeepSWE-Preview-32.8B 58.8% (harness-trained small
  models closing gap). llama.cpp: -ctk q4_0 KV substantially degrades tool
  calling; native handler list; gpt-oss harmony-required.

Top-15 adoptable (ranked, full URLs in saved report): 1 grammar-enforced tool
calls/control-plane; 2 bash-first minimal toolset + text-parsed fallback;
3 ACI guardrails; 4 whole-file/validated search-replace + error-feedback
retry; 5 early structured compaction + disk re-injection; 6 tool-output
offload/clearing; 7 post-edit deterministic gates (lint→type→test, finish
blocked until green); 8 re-injected living todo list; 9 read-only subagents +
single writer per workstream; 10 role-pinned routing (cache-miss-aware);
11 plan-file-first workflow; 12 repo-map structural context (~1k dynamic);
13 evaluator/rubric loop for "done"; 14 AGENTS.md convention + prefix-stable
prompts + prefix caching; 15 container sandbox + allowlisted escalation,
fail-closed review.

Harness-status mapping (mine): already have ≈ 7,9(partly: parallel writers
exist but with work-order file separation),11(work orders/sprint record),
13(locked suite+dispute),14(AGENTS.md n/a internally; digest append-at-end),
15(argv-only sandbox stricter than bash). GAPS feeding the plan: #2 bash-first
fallback mode (M), #3 ACI micro-guardrails incl. explicit empty-output notice
(P), #4 whole-file default for weak editors w/ compliance data (P — the 100%
vs 73% number is the citation for replace_lines demotion), #5 earlier
compaction + disk re-injection (O — harness compaction trigger is 0.8×window;
research says 50–60% of USABLE for small models), #6 tool-output offload (O),
#8 todo cadence re-injection (R — verify task-list middleware cadence),
#10 role-pinned routing w/ effort tiers (Q), #12 repo map (already Tier 2 in
docs/improvement-plan.md — reinforce), narrow correctness-gap reviewer
rubric (Q/E2 milestone-review findings).
Bottom line quote: frontier consensus is MORE valuable on 20–40B local MoE —
"every mechanism substitutes harness engineering for model capability".

---

<a id="r4"></a>
## Part R4 — Local-LLM research report (2026-10-17/18, session 1)

**Linked plan items**

| Theme | Plan items |
|---|---|
| 8.1 Constrained/guided decoding | [M](improvement-plan.md#plan-m), [M amendment](improvement-plan.md#plan-m-amendment) |
| 8.2 Per-model tool-call quirks | [M](improvement-plan.md#plan-m), [BH](improvement-plan.md#plan-bh) |
| 8.3 Prompting/orchestration for small models | [E](improvement-plan.md#plan-e), [L.7](improvement-plan.md#plan-l-7), [X](improvement-plan.md#plan-x), [BB](improvement-plan.md#plan-bb) |
| 8.4 Serving performance | [S](improvement-plan.md#plan-s), [O](improvement-plan.md#plan-o), [AA](improvement-plan.md#plan-aa), [AB](improvement-plan.md#plan-ab), [BA](improvement-plan.md#plan-ba) |
| 8.5 Small-model failure modes | [L](improvement-plan.md#plan-l), [N](improvement-plan.md#plan-n), [R](improvement-plan.md#plan-r), [BC](improvement-plan.md#plan-bc) |
| 8.6 Model routing | [Q](improvement-plan.md#plan-q), [BD](improvement-plan.md#plan-bd) |
| 8.7 Top-12 recommendations | [M](improvement-plan.md#plan-m), [N](improvement-plan.md#plan-n), [O](improvement-plan.md#plan-o), [Q](improvement-plan.md#plan-q), [S](improvement-plan.md#plan-s) |

### 8. Full local-LLM research report (subagent d2176eb1 — COMPLETE, supersedes §4)

Sources verified by direct fetch 2026-10-17/18 (web_search was unavailable; built
from primary docs/papers/leaderboards).

#### 8.1 Constrained/guided decoding for tool calling and JSON
- vLLM: structured outputs via xgrammar or guidance/llguidance
  (--structured-outputs-config.backend, default auto); guided_* fields removed in
  v0.12.0 → structured_outputs object: json/regex/grammar/choice/structural_tag
  (schema enforced inside tags of free text). "Guaranteed validly-parsable — not
  high-quality"; ALSO specify schema in the prompt; first use of a named tool
  costs seconds of FSM compile (cached after). --tool-strict-level
  strict|allowed|open: strict constrains tool NAMES + ARGUMENTS via structural
  tags. https://docs.vllm.ai/en/latest/features/structured_outputs/ ,
  https://docs.vllm.ai/en/latest/features/tool_calling/
- Thinking vs grammar: Qwen3 Coder on vLLM DISABLES structured outputs while
  reasoning by default; need --structured-outputs-config.enable_in_reasoning=True
  (v0.11.2+). xgrammar uses the reasoning parser's end_token_id and SKIPS
  enforcement during reasoning. Reasoning-parsers doc = authoritative
  compatibility matrix: parsers per family (qwen3, glm45/glm47,
  minimax_m2_append_think, deepseek_r1, deepseek_v3, openai for gpt-oss);
  DeepSeek R1 tool calling ✗; native thinking_token_budget sampling param +
  --reasoning-config (reasoning_start/end) = built-in mitigation for "reasoning
  eats max_tokens"; server-wide --default-chat-template-kwargs
  '{"enable_thinking": false}'. https://docs.vllm.ai/en/latest/features/reasoning_outputs/
- llama.cpp/llama-server: GBNF grammars (root rule, token matching can permit
  <think>); response_format json_schema → GBNF automatically. Documented limits:
  additionalProperties defaults FALSE, unsupported features SILENTLY SKIPPED,
  properties + anyOf/oneOf unsupported, nested $refs broken, min/max int-only,
  patterns only as ^...$, schema NOT injected into prompt (model can't see it —
  describe structure in prompt too). grammar_eval_n/grammar_max_tokens,
  LLAMA_MAX_PARALLEL_GRAMMARS. https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md
  Stronger: build with -DLLAMA_LLGUIDANCE=ON (follows JSON Schema closely,
  additionalProperties default true, ERRORS instead of silently ignoring,
  ~50µs mean mask compute). https://github.com/ggml-org/llama.cpp/blob/master/docs/llguidance.md
- llama-server tool calls require --jinja; native handlers: Llama 3.1/3.2/3.3,
  Hermes 2/3, Qwen 2.5(-Coder), GPT-OSS (Harmony), Command-R7B, Firefunction-v2;
  DeepSeek R1 "WIP/reluctant"; generic fallback "may consume more tokens".
  Parallel tool calls DISABLED by default (send parallel_tool_calls: true).
  Extreme KV quantization (-ctk q4_0) "can significantly degrade tool call
  performance". https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md
  Per-request: reasoning_format, reasoning_effort (none disables),
  reasoning_budget, chat_template_kwargs {"enable_thinking": false}.
  https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- Best practice for :8888: native tool parser + structural enforcement
  (vLLM --tool-strict-level allowed|strict; llama-server --jinja + json_schema),
  restate schema in prompt, keep code/file bodies in PLAIN-TEXT fields not
  nested JSON strings (aider: 10–15% quality loss from JSON-wrapping code even
  when schema-valid https://aider.chat/2024-08-14/code-in-json.html),
  validate+retry client-side anyway
  (https://docs.langchain.com/oss/python/langchain/structured-output).

#### 8.2 Per-model tool-call format quirks
- Qwen3: enable_thinking = hard switch in chat template via chat_template_kwargs
  (differs Transformers/vLLM/SGLang). Qwen vLLM page: --reasoning-parser qwen3
  (v0.9.0+; v0.8.5 bug), custom non-thinking template, --enable-auto-tool-choice
  --tool-call-parser hermes. https://qwen.readthedocs.io/en/latest/deployment/vllm.html
  Function-calling guide recommends HERMES-STYLE template; stop-word (ReAct)
  templates unreliable for reasoning models (stop word inside thoughts);
  "corner cases where tool calls may be malformed… be prepared".
  https://qwen.readthedocs.io/en/latest/framework/function_call.html
  vLLM parser for Qwen3-Coder now qwen3_xml (renamed from qwen3_coder), parallel
  supported; hermes/hermes3 for Qwen2.5/Qwen3.
- Qwen3-Coder-30B-A3B-Instruct: 30.5B/3.3B-active, 128 experts/8; NON-THINKING
  only; 262,144 native ctx (1M YaRN); temp 0.7/top_p 0.8/top_k 20/rep 1.05;
  recommended max output 65,536; "if OOM reduce context to 32,768".
  https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct
- Qwen3-30B-A3B-Instruct-2507: non-thinking, 256K native; Aider-Polyglot 35.6,
  BFCL-v3 65.1 (vs GPT-4o 66.5!), TAU2-Retail 57.0 (τ² telecom 12.3 vs 29.8 —
  drops harder multi-turn); presence_penalty 0–2 for "endless repetition";
  16,384 output; RULER decay avg 86.8: ~97@32K → 82.5@256K → 72.8@1M. Don't
  enable YaRN if average ctx ≤32K ("may hurt short text").
- gpt-oss-20b: harmony format ONLY ("will not work correctly otherwise").
  Harmony: role hierarchy + channels analysis/commentary(final tool calls)/final;
  "Reasoning: high" literal line in system prompt. 21B/3.6B-active, 131,072 ctx
  YaRN, MXFP4; AIME'24 >20K CoT tokens/question avg; STRIP prior-turn reasoning
  in multi-turn. vLLM: --reasoning-parser gpt_oss --tool-call-parser openai; no
  parallel tool calls. https://huggingface.co/openai/gpt-oss-20b ,
  https://arxiv.org/html/2508.10925v1 , https://github.com/openai/harmony
- DeepSeek-R1 + distills: vLLM matrix tool calling ✗; llama.cpp "reluctant".
  Distill guidance: temp 0.5–0.7 (0.6) "prevent endless repetition and
  incoherent output"; AVOID system prompts (all instructions in user prompt);
  32,768 max gen; sometimes skip thinking → prefill "<think>\n". R1-Distill-
  Qwen-14B LiveCodeBench 53.1. Practical: run R1-distills as BASH-STYLE TEXT
  agents, not function-callers.
  https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-14B/raw/main/README.md
- Llama 3.x: vLLM llama3_json parser; "may generate parameters in a malformed
  format"; no parallel; pythonic parser "smaller Llama models frequently fail".
- GLM-4.6: 200K, tool use during inference (interleaved), temp 1.0/top_p .95/
  top_k 40; parsers glm45/glm47. MiniMax-M2 (230B/10B-active): MUST pass
  assistant history back WITH <think> blocks intact (removing "negatively
  affects"); SWE-bench Verified 69.4 (R2E-Gym/OpenHands, 128K, 100 steps),
  Terminal-Bench 46.3, LiveCodeBench 83.0. Cross-model SWE-bench Verified:
  GLM-4.6 68.0, Kimi-K2 69.2, DeepSeek-V3.2-Exp 67.8, Sonnet 4 72.7, Sonnet 4.5
  77.2, GPT-5 74.9.
- Harness-breaker summary: (1) reasoning consumes max_tokens → empty content
  (fix: thinking_token_budget / --reasoning-budget / disable; watch
  finish_reason=length); (2) malformed/hallucinated args despite "parseable"
  guarantees; (3) parallel tool calls unsupported (many parsers; llama.cpp
  default-off); (4) format mismatches (harmony-only; strip-vs-keep reasoning:
  gpt-oss STRIP, MiniMax KEEP); (5) thinking+structured-output conflict
  (enable_in_reasoning).

#### 8.3 Prompting/orchestration techniques for small models
- Scaffolding compensates for size: SWE-agent ACI → 12.5% SWE-bench pass@1
  (arXiv:2405.15793); Agentless 3-stage pipeline beat agent frameworks at
  ~$0.70/task (arXiv:2407.01489); mini-swe-agent ~100 lines, BASH-ONLY tool,
  strictly linear append-only history, >74% SWE-bench Verified w/ frontier,
  "runnable with literally any model" (github.com/SWE-agent/mini-swe-agent);
  AlphaCodium flow engineering 19%→44% pass@5 (arXiv:2401.08500).
- Generator–verifier / planner–executor: aider Architect/Editor 85.0% vs 79.7%
  baseline; EVERY pairing improved over solo (o1-mini 61.1→71.4 w/ DeepSeek
  editor; gpt-4o-mini 55.6→60.2); aider recommends --editor-model/architect
  "with models that have trouble following edit format instructions".
  Cognition: Claude Code used Haiku as edit-apply engine; Devin/SWE-1.5 built on
  RL'd small models for narrow well-specified subtasks
  (cognition.com/blog/dont-build-multi-agents).
- code-in-JSON degrades quality (Sonnet −13% even with zero syntax errors under
  schema enforcement — the constraint itself distracts). "Errors are tools" =
  12-Factor factor 7 (+ own your context window 3, tools are structured outputs
  4, own control flow 5, small focused agents 1, stateless reducer 6, compact
  errors 10). Anthropic Building Effective Agents: simplest composable pattern
  (chaining, ROUTING, orchestrator-workers, EVALUATOR-OPTIMIZER); ACI/tool design
  matters more than overall prompt (absolute paths fixed small-model tool-call
  failures). Self-consistency +17.9% GSM8K (arXiv:2203.11171); Reflexion 91%
  HumanEval (arXiv:2303.11366).
- τ-bench: tool-calling beats ReAct for gpt-4o (airline pass^1 0.420 TC vs
  0.325 ReAct); steep consistency decay pass^1→pass^4 0.460→0.225. BFCL V3
  state-based multi-turn taxonomy = canonical description of small-model tool-loop
  failure: missing implicit actions, poor environment-state tracking, loops
  terminated at max steps, over-cautious clarification
  (gorilla.cs.berkeley.edu/blogs/13_bfcl_v3_multi_turn.html). AgentBench: large
  commercial vs ≤70B OSS gap in long-term reasoning/decision-making/instruction-
  following (arXiv:2308.03688).
- Orchestration philosophy: one coherent context thread, compress rather than
  parallel-divergent (Cognition); Manus lessons: STABLE PROMPT PREFIXES for
  KV-cache, append-only context, MASK-DON'T-REMOVE tools, file system as
  externalized memory, RECITATION (rewrite plan each step into recent
  attention), keep wrong turns visible, avoid inference-time few-shot
  (manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus).
  Cline local-model guide: compact prompts, focused tasks, fresh task when
  context too large. plandex: plan-then-execute, diff sandbox, tree-sitter repo
  maps, multi-layer edit validation. Terminal-Bench (ICLR 2026)/Harbor: harness
  choice changes scores for the same model → route on YOUR benchmark.

#### 8.4 Serving performance for agentic workloads
- Prefix caching: vLLM APC hashes KV blocks (parent-hash + tokens + cache_salt);
  multi-round conversation = primary beneficiary; accelerates PREFILL only
  (docs.vllm.ai/en/latest/features/automatic_prefix_caching/). llama-server
  --cache-prompt DEFAULT ON (timings.cache_n reports reuse), --cache-reuse N
  (KV shifting), --slot-prompt-similarity, --cache-ram 8GiB default, slot cache
  save/restore, --context-shift disabled by default. Any prefix change
  (timestamp, dynamic tool list, reordered history) invalidates — Manus: KV-cache
  hit rate "the most important metric" for production agents (input:output
  ~100:1; cached tokens ~10× cheaper). OpenHands local guide: vLLM
  --enable-prefix-caching + Arctic suffix speculation ~2× speedups.
- Batching/MoE/speculation: vLLM V1 chunked prefill default; tune
  --max-num-batched-tokens (>8192 throughput), --max-num-seqs;
  --enable-expert-parallel for MoE multi-GPU; --cpu-offload-gb/--swap-space.
  Speculative decoding LOSSLESS: n-gram, suffix, EAGLE3, MTP, draft models;
  gains largest at low-medium QPS. llama.cpp: -np parallel slots, continuous
  batching, --kv-unified-per-slot, -fa, -ctk/-ctv (q4_0 KV degrades tool calls),
  experimental --tools agent loop.
- Context rot: Chroma (18 models incl. Qwen3-32B): degradation NON-UNIFORM with
  input length even on trivial tasks; needle position + similar distractors
  matter; NIAH overstates (research.trychroma.com/context-rot, arXiv:2507.13436).
  Lost-in-the-Middle: U-shaped — critical instructions at BEGINNING or END
  (arXiv:2307.03172). OpenHands: Ollama 4096 default "far too small"; ≥22K,
  32,768 w/ max_input_tokens=30000 headroom. aider: Qwen2.5-Coder-32B 72.2%
  BF16 → 51.9% @2K window (silent truncation; edit compliance 46.2%); q4_K_M/
  q2_K cost 5–10 points (aider.chat/2024-11-21/quantization.html).
  WORKING RECOMMENDATION: cap effective per-turn context ~32–64K even on
  128–256K models; ≥4–8K output headroom; no YaRN unless truly >32K; ≥Q4_K_M/Q5
  weights, f16/q8_0 KV.

#### 8.5 Small-model failure modes in multi-agent harnesses
- Loops/repetition: BFCL V3 (max-step loops, state tracking). presence_penalty
  0–2 (Qwen3), temp 0.5–0.7 (R1-distills), --reasoning-budget, harness stuck
  detection + step caps.
- Hallucinated tools/args: parseable ≠ correct; --tool-strict-level
  strict|allowed; generic llama.cpp handler misfires; validate args in harness,
  return error as tool result (12-factor).
- Whitespace-exact edit failures: aider edit-errors guide (malformed blocks,
  weak-model warnings, truncation; /undo, --editor-model, architect mode);
  plandex multi-layer validation + diff sandbox; SWE-agent ACI (line-numbered
  views, constrained edit commands). Mitigation stack: prefer whole-file or
  line-anchored edits for weak editors, apply-and-verify, architect/editor split.
- Multi-turn attention drift: "LLMs Get Lost in Multi-Turn Conversation"
  (arXiv:2505.06120): avg 39% performance drop multi-turn; early assumptions,
  premature final answers, "when they take a wrong turn, they get lost and do
  not recover". Mitigations: consolidate/re-anchor (re-state full task in fresh
  turns), condense history (OpenHands Context Condenser), fresh tasks per unit
  (Cline), Manus recitation + file-system memory.
- Thinking-budget exhaustion: gpt-oss >20K CoT; R1 skipping thinking.
  thinking_token_budget/--reasoning-budget; thinking off on execution turns;
  raise max_tokens (Qwen3-Coder 65,536); detect finish_reason=length → retry
  think-off/larger budget.
- History-format poisoning: strip prior reasoning for gpt-oss; KEEP <think> for
  MiniMax-M2; inconsistent handling silently collapses quality.
- Model-level regression: OpenHands "when it behaves like a chatbot only… the
  problem may be the model itself" — verify tool calling works before blaming
  harness; use community-confirmed models.

#### 8.6 Model routing (strong planner/reviewer + fast local executor)
- FrugalGPT (arXiv:2305.05176): cascades match best single model with up to 98%
  cost reduction or +4% accuracy at equal cost.
- RouteLLM (arXiv:2406.18665, LMSYS): preference-trained routers >2× cost cut
  without quality loss; transfer when models change.
- aider architect/editor (above): reasoning model plans, cheaper model edits —
  85.0% vs 79.7%; split also REPAIRS format compliance for weak editors.
- Cognition: route DECISIONS to strong models, MECHANICAL STEPS to fast ones.
- Anthropic: routing is first-class workflow pattern.
- Production: OpenHands SDK MultimodalRouter (rule-based) + route_task_to_model
  (LLM classifier, mid-conversation switch, history preserved)
  (docs.openhands.dev/sdk/guides/llm-routing, /llm-task-routing); mini-swe-agent
  model-agnostic via litellm. Benchmark caveat: same model + different harness =
  different score (Harbor/Terminal-Bench).

#### 8.7 Top-12 recommendations ([S]=server, [H]=harness)
1. [S] Match server tool/reasoning parsers to the model + turn on enforcement
   (vLLM --enable-auto-tool-choice --tool-call-parser {qwen3_xml|hermes|glm45|
   minimax_m2_append_think|openai} --reasoning-parser {...} --tool-strict-level
   allowed (+enable_in_reasoning=True if thinking on); llama.cpp --jinja,
   reasoning_format auto, json_schema). Removes largest failure class for zero
   prompt changes.
2. [H] Per-model thinking policy with budget guardrails: thinking off on
   execution/tool-heavy nodes; thinking_token_budget/--reasoning-budget; size
   max_tokens per vendor guidance; auto-retry on finish_reason=length with
   thinking disabled.
3. [H] Validate-and-retry with EXACT error feedback, capped 1–2, then escalate
   to stronger model (cascade). LangGraph conditional edges.
4. [H] Architect/Editor split: strongest model writes spec/plan/review; local
   MoE emits file edits; simple edit formats for executor. aider 85.0 vs 79.7;
   Cognition edit-apply precedent. Maps 1:1 onto PM/architect/lead vs specialist
   roles — specialist edits = the only thing the local model must get right.
5. [H] Keep code OUT of JSON strings; restate schemas in prompts (GBNF not shown
   to model; prompt-schema alignment improves quality).
6. [S+H] Cache-first context design: byte-stable system prompt + static tool
   definitions FIRST, append-only history, no timestamps/dynamic ordering in the
   cached prefix; verify via vLLM metrics or timings.cache_n; cache_salt for
   isolation. Payoff 2–10× cheaper/faster TTFT → funds retries/verification.
7. [H] Hard context budget ~32–64K effective + condense/recite: summarize older
   turns (OpenHands Condenser), rewrite current plan into recent context each
   step (Manus recitation), externalize to files, must-follow constraints at the
   END (lost-in-the-middle; context rot incl. Qwen3; 39% multi-turn decay +
   re-anchoring). Verify server real ctx (≥22–32K).
8. [S] Serving quality gates: ≥Q4_K_M/Q5 weights (BF16 72.2→q2_K 61.7), flash
   attention on, KV f16/q8_0 only, no YaRN under ~32K, vendor sampling presets
   (Qwen .7/.8/20/1.05; GLM/MiniMax 1.0/.95/40), aider-polyglot-style smoke
   benchmark after ANY server change.
9. [H] One task per turn, deterministic control flow in graph edges not model
   discretion; single coherent context per work item; compressed summaries
   between roles, not parallel divergent contexts; compact focused role prompts.
10. [S] Throughput for parallel agents: vLLM chunked prefill (default),
    --max-num-batched-tokens ≥8192, --enable-expert-parallel (MoE), n-gram/
    suffix/EAGLE/MTP speculation (lossless, biggest win at low QPS); llama.cpp
    -np slots sized to KV memory, --cache-ram, cross-slot prompt-cache reuse.
    OpenHands: ~2× from suffix speculation on Qwen3-Coder. Faster loops = more
    verification budget per task.
11. [H] Bash-first fallback executor for tool-call-unreliable models (R1
    distills): mini-swe-agent-style one-bash-tool loop, YAML/plain-text
    commands, linear append-only history, R1 sampling rules (temp 0.6, no system
    prompt, "<think>\n" prefill). Unlocks a whole model class.
12. [H] Router/cascade layer across the role graph: cheap-local-first with
    verifier-gated escalation (FrugalGPT/RouteLLM); OpenHands-style classifier
    per task type; planning/review on strongest accessible model, execution on
    local MoE. Measure per-node pass rates on YOUR benchmark.

Per-model cheat sheet: Qwen3-Coder-30B-A3B → vLLM qwen3_xml parser, no
thinking, .7/.8/20/1.05, max_tokens 65536, ctx ≤32–64K working set.
Qwen3-30B-A3B-2507 → same + presence_penalty ≤2 if looping. gpt-oss-20b →
harmony only; gpt_oss/openai parsers; strip prior reasoning; "Reasoning: low/
medium" per node. DeepSeek-R1-distill → bash-text loop, temp 0.6, no system
prompt, 32K cap. GLM-4.6 → glm45, 1.0/.95/40, keep think blocks. MiniMax-M2 →
minimax_m2_append_think, 1.0/.95/40, never strip <think>.

Mapping to our evidence: rec 1+5 ↔ A9/A3 (structured-output degradation,
hallucinated names); rec 2 ↔ A4/B3 (reasoning exhaustion — llama-server
--reasoning-budget and vLLM thinking_token_budget are the SERVER-side versions
of Initiative I); rec 4 ↔ C8 (local model drafts fine, fixes/reviews weak —
route fixes/reviews to judgement model); rec 6+7 ↔ B2/B4/F15 (prefill-bound,
60–120k prompts, 45–73% cache hits; effective-context cap 32–64K vs current
~100% of 126k window as input ceiling); rec 10 ↔ F10 (parallel vs 1-slot
server; owner's model is MTP GGUF = speculation-ready); Manus mask-don't-remove
↔ our tool-withholding changes the tool list mid-stage (cache invalidation +
confusion — consider instruction-level withholding); rec 12 ↔ existing two-tier
roles (extend: escalation for reverted fixes).

---

<a id="r5"></a>
## Part R5 — UI/UX research-backed opportunities (2026-10-18, UI audit)

**Linked plan items**

| Theme | Plan items |
|---|---|
| C1–Cn opportunities | [Part 4](improvement-plan.md#plan-part-4), [Part 11](improvement-plan.md#plan-part-11), [Part 15](improvement-plan.md#plan-part-15), [Part 19](improvement-plan.md#plan-part-19) |

### C. Research-backed opportunities (all URLs verified by subagent)
- C1 Mid-run steering/side chat (L): Devin Side Chats + takeover
  (docs.devin.ai/work-with-devin/devin-session-tools); Claude Code web "actively
  steer" (claude.com/resources/articles/claude-code-on-the-web). Harness dynamic
  instruction injection = exact backend hook. Composer at waiting/escalation
  points, injected at next stage boundary.
- C2 Timeline scrubbing/checkpoint time-travel (M): Devin time navigation;
  LangGraph time-travel docs (docs.langchain.com/oss/python/langchain/frontend/
  time-travel). Rewind exists as bare <select>+confirm (:509-529) → visual
  timeline w/ checkpoint ticks, scrub feed/artifacts, then rewind.
- C3 Parallel-agent lanes (M): Cursor multi-agent (cursor.com/help/ai-features/
  multi-agent, background-agents); Lovable subagents (docs.lovable.dev/features/
  subagents). Events carry stage → per-agent columns + filter + "N agents working".
- C4 In-gate artifact reading + diffs + versions (M): OpenHands Changes tab
  (docs.openhands.dev/openhands/usage/key-features); Lovable history
  (docs.lovable.dev/features/projects/history); Windsurf cascade diffs. Artifacts
  track revision (types:15-21) — render in gate, diff revisions, version list.
- C5 Proof-of-work delivery (S-M): Devin video recordings
  (docs.devin.ai/work-with-devin/testing-and-recordings); Cursor attaches videos/
  screenshots/logs. DeliveryPanel already shows criteria+screenshots (:182-192)
  but 128px uncickable thumbs (:79) → lightbox, per-sprint evidence, test excerpts.
- C6 Notifications & mobile monitoring (S): Claude Code iOS; Cursor Slack/GitHub/
  Linear; Devin Slack (docs.devin.ai/integrations/slack). Gate self-approves
  after timeout and UI never tells anyone (0 Notification/title/favicon code).
  Minimum: tab-title "(⏸ needs review)" + favicon badge + browser Notification
  on waiting/failed/completed; optional Slack/Telegram webhook.
- C7 Cost/budget cockpit (S-M): Devin ACU caps+usage dashboard
  (docs.devin.ai/admin/billing/usage); LangSmith rollups. Cost model already
  honest (fully_priced, unpriced_requests, waiting_for_budget types:40-69) —
  add spend-vs-ceiling bar, per-stage breakdown, parked-at-budget recovery flow.
- C8 Intake expectation-setting (S-M): Lovable Design Guidance
  (docs.lovable.dev/features/design-guidance); NN/g response times
  (nngroup.com/articles/response-times-3-important-limits). Forecast line
  ("typically 7.6h over 5 runs" Home:353-359) is a gem → step wizard + final
  review screen + ETA/milestone progress + expected-vs-elapsed per stage.
- C9 Trust/transparency (S-M): Microsoft Guidelines for Human-AI Interaction G1/
  G2/G11/G15 (microsoft.com/en-us/research/publication/guidelines-for-human-ai-
  interaction); Google PAIR Guidebook (pair.withgoogle.com/guidebook); Devin
  Session Insights; NN/g big-ball-of-mud-ai + 3-agent-context-roles. Decision log
  + plain-English already implement G11 → extend: why-at-gates, retry/escalation
  counts as trust signals (data exists), post-run Insights panel (OutcomesPanel = seed).
- C10 Keyboard-first (M): Devin CLI shortcuts (docs.devin.ai/cli/reference/
  keyboard-shortcuts); ⌘K palette (jump to run/phase/artifact, toggle view,
  pause/resume w/ typed confirm); gate shortcuts A/R.
- C11 Streaming-build polish (S): bolt.new/v0/Lovable live preview. True token
  streaming rejected for event volume (useStreamedText:3-18 — sound); extend
  illusion: per-stage typing indicator in wizard rail, document.title w/ stage,
  reveal artifacts on write_artifact events (type already distinguished
  activity.ts:245-247).
- C12 UX writing for waiting/failure (S): PAIR Errors; NN/g progress. activity.ts
  nails steady state; failure paths don't → toasts w/ retry, "Last activity 12s
  ago", "Reconnecting…" chip, error cards w/ Retry/Clone/next steps.

---

<a id="r6"></a>
## Part R6 — Earlier comparisons with other harnesses (2026-10-04 and 2026-10-09)

**Linked plan items**

| Source | Plan items |
|---|---|
| October plan §1 (SOTA comparison) | [E1](improvement-plan.md#plan-e1) |
| High-steering §2 (comparative matrix) | [E2](improvement-plan.md#plan-e2) |

### 1. Comparative Architectural Benchmark: Current Harness vs. SOTA Frameworks

To achieve consistent, production-grade performance and reduce benchmark execution times from 2–3+ hours down to 30–60 minutes for standard applications, the harness was evaluated against industry state-of-the-art (SOTA) agentic coding systems:

| Dimension | Current Harness | Leading SOTA Systems (SWE-agent, OpenHands, Aider, DeepSeek) | Architectural Gap & Opportunity |
|---|---|---|---|
| **Organizational Topology** | Rigid 14-stage corporate workflow (Architect → Arch Review → QA Author → QA Review → Scrum Master → Tech Lead → Dev → Test → Code Review → Acceptance → Defect Remediation → Milestone Review → Sprint Summary). 400–600 model calls per run. | **Dynamic / Adaptive Topology** (Aider, OpenHands): Single Planner + Executor loop, or lean Architect + Coder pair. Specialized roles invoked dynamically only when needed. Benchmark runs finish in 15–40 steps. | **High**: Simple applications (e.g. 10–16 criteria) suffer massive roundtrip latency. The harness should dynamically collapse stages for small/medium scopes. |
| **Acceptance Suite Verification** | Suite authoring produces tests with un-awaited promises or CSS selectors. Flaws trigger runtime crashes after development, invoking the **Acceptance Dispute Engine** (reopening suite for 3+ rounds, costing 30–45 mins). | **Pre-Emptive Static AST Validation** (SWE-bench / DeepSeek): Strict linters, AST tree-sitter checks, and floating-promise detectors validate tests *before* suite is accepted or executed. | **Critical (P0)**: Catch test defects statically before locking. Eliminates the multi-round dispute loop entirely. |
| **Context & Repo Representation** | Flat file lists in workspace digest (`MAX_FILES = 40`). High redundant read rate (12–18% of reads spent re-inspecting files). Agents frequently call `read_file` to find symbol definitions. | **Tree-Sitter RepoMap** (Aider): Dense topological map of exported symbols, signatures, and classes generated in <1,000 tokens using Tree-Sitter and PageRank. | **High (P1)**: Provide symbols and signatures in prompt context, slashing redundant tool calls and token spend. |
| **Execution Latency & Sandboxing** | Isolated command execution per tool call; default Playwright locator timeout of 30s causes failing test runs to burn 5–8 minutes per round. | **Persistent Daemon & Fast-Fail Timeouts** (OpenHands, SWE-agent): Persistent shell session with sub-second turnaround; strict 3–5s timeouts on UI element checks. | **High (P1)**: Fast-fail on UI mismatches; persist sandbox environment. |
| **Cross-Run Learning & Memory** | **Tabula Rasa**: Cross-run memory was previously dropped (Phase 4) due to prompt-injection concerns. Agents repeat known framework gotchas (e.g., missing `await` on custom helpers, unconfigured JSDOM globals) on every single run. | **Deterministic Skill & Case Distillation** (Voyager, Reflexion, ExpeL): Post-run reflection distills verified traps, patterns, and templates into deterministic, injection-safe rule stores. | **Critical (P0)**: Implement a Self-Learning Engine that extracts verified rules from Decision Records and saves them into Stack Pack knowledge bases. |

---


### 2. SOTA Comparative Research: How Leading Harnesses Solve This

We analyzed the architectural patterns of the top five autonomous coding harnesses: **SWE-agent** (Princeton), **OpenHands / OpenDevin** (All-Hands AI), **Aider** (Paul Gauthier), **DeepSeek Harness**, and **Claude Code** (Anthropic).

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   COMPARATIVE ARCHITECTURE MATRIX                                      │
├──────────────────┬─────────────────┬──────────────────────┬──────────────────────┬─────────────────────┤
│ Capability       │ SWE-agent       │ Aider                │ OpenHands            │ Our Harness Target  │
├──────────────────┼─────────────────┼──────────────────────┼──────────────────────┼─────────────────────┤
│ Tool-Level Parse │ Linter checked  │ Tree-sitter AST parse│ LSP diagnostic hook  │ Immediate Write-Time│
│ Gate             │ on file command │ on every git patch   │ on file save         │ Parse Rejection     │
├──────────────────┼─────────────────┼──────────────────────┼──────────────────────┼─────────────────────┤
│ Stage Exit Gate  │ Bash exit code  │ Reprompts model on   │ Task finish check    │ Pre-Exit Diagnostic │
│                  │ verification    │ linter error         │ against agent state  │ Interceptor (1-turn)│
├──────────────────┼─────────────────┼──────────────────────┼──────────────────────┼─────────────────────┤
│ Acceptance Suite │ Static baseline │ Test command         │ Pre-flight container │ Pre-Lock AST & Dry- │
│ Verification     │ check           │ verification         │ sanity check         │ Run Load Gate       │
├──────────────────┼─────────────────┼──────────────────────┼──────────────────────┼─────────────────────┤
│ Cognitive Memory │ File context in │ Repository map via   │ Working memory doc   │ Self-Contained Work │
│ Scaffolding      │ bash prompt     │ Tree-sitter (ctags)  │ in system prompt     │ Order Context Excerpt│
├──────────────────┼─────────────────┼──────────────────────┼──────────────────────┼─────────────────────┤
│ Defect Batching  │ N/A (single     │ Single conversational│ Multi-turn issue     │ True Role-Based     │
│                  │ agent loop)     │ patch session        │ remediation agent    │ Consolidated Session│
└──────────────────┴─────────────────┴──────────────────────┴──────────────────────┴─────────────────────┘
```

#### Key Architectural Insights:
1. **Aider's Syntax Gate Principle**: Aider never allows a broken edit onto the branch. If Tree-sitter detects an incomplete AST or syntax error after applying a replacement, Aider immediately rejects the diff and asks the LLM to provide a valid edit.
2. **SWE-agent's Action Feedback**: Tool feedback in SWE-agent is dense and actionable. When a tool fails or introduces a syntax error, the tool return is an explicit error message rather than an advisory warning.
3. **The Flaw in Our Previous Approach**: In `src/app/tools/repository.py`, `language_service.underlined_any` was returning an *advisory note* appended to successful tool output (`"Notes, never refusals"`). Lower-tier local models (and even reasoning frontier models) routinely ignore text notes when the tool indicates success.

---
