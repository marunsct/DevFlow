# Work batching: splitting big work for models that cope badly with it

Owner request 2026-10-24 (during the first Ornith gate run): when a model finds a huge piece of
work hard, split it into smaller batches, dynamically; local models do not take reduced thinking
effort well, so find another way; research how others do it; apply it to every stage because the
products will get much more complex; add no defect; keep quality; suggest such changes without
being asked, because the owner does not watch every result.

Status: **designed, nothing built.** Rows WB.1-WB.8 in `docs/improvement-plan.md`.

## 1. What our own data says

From `loop.sh patterns` (292 transcripts since 2026-10-20) and the run in hand:

| Evidence | Number |
|---|---|
| One defect shown to a fixer | 333 stages, **56% fixed**, median 19.5k output tokens, **14% cut off** |
| Two or three defects | 17 stages, 53% fixed, median 58k tokens, 47% cut off |
| Four or more defects | 78 stages, **26% fixed**, median 73k tokens, **62% cut off** |
| p90 reply size, by stage | acceptance_review 24.9k, technical_lead 21.9k, scrum_master 18.9k, architecture_review 16.3k, principal_architect 15.8k |
| Replies cut off by the cap, by stage | technical_lead 11% (21 of 193), scrum_master 8%, architecture_review 6%, principal_architect 5% |
| Ornith, acceptance author, this run | 14 calls, 240k tokens (**17k a call**) - the whole suite, 39 tests, one reply at a time |
| Qwen, acceptance author, earlier runs | 22-74 calls for 26-97k tokens (**1-2k a call**) - the tool loop wrote it in small steps |
| Ornith, architect, this run | 21 calls, 286k tokens (13.6k a call) against 66-169k for Qwen |

Reading: the more a single call is asked to do, the more tokens it spends, the likelier it is cut
off, and (for fixes) the less often it succeeds. The defect-bundle rows are confounded - harder
defects get bundled - so they say "worth testing", not "proven". The Ornith/Qwen contrast is the
cleaner one: Qwen's loop happened to cut the work into small steps; Ornith, given the same
stage, reasons through the whole of it in each reply.

## 2. What others do (and what the research does not show)

| Source | What it says | What we take |
|---|---|---|
| [Anthropic, Building effective agents](https://www.anthropic.com/research/building-effective-agents) | Prompt chaining "trade[s] off latency for higher accuracy, by making each LLM call an easier task"; orchestrator-workers fits work whose subtasks "you can't predict"; "find the simplest solution possible, and only increas[e] complexity when needed"; get "ground truth" from the environment each step; include stopping conditions. | Split only where it demonstrably helps; a fixed chain where the units are known (criteria, files, sections); verify each step against something real (the suite runs). |
| Aider architect/editor mode (aider.chat docs; not opened here, known from secondary write-ups such as [this summary](https://leaderboard.steel.dev/leaderboards/aider/)) | One model plans, another writes the edits. Secondary sources report o3 + GPT-4.1 at 83% on the Polyglot benchmark and R1 + Sonnet nearly 10 points over either alone; I could not confirm the figures from Aider's own pages. | "Think once, then write": a plan call that reasons, then writing calls that carry the plan and little else. |
| [Agentless](https://arxiv.org/html/2407.01489v2) | A fixed pipeline - localise (file, function, line), repair with small edits, validate - matched agent systems on SWE-bench Lite at a fraction of the cost (reported 27-32% at $0.34-0.70). | Small, localised units with a check after each. |
| [ReWOO](https://arxiv.org/pdf/2305.18323) | Plan once, run workers, do not re-feed history each step; reported token cuts of 64-80% (summaries disagree). A static plan cannot improvise. | The plan is a list of units; each worker sees its unit and the core, not the whole conversation. Keep a fallback to the old path. |
| [Cognition, Don't Build Multi-Agents](https://cognition.ai/blog/dont-build-multi-agents) and [the 2026 follow-up](https://cognition.com/blog/multi-agents-working) | Parallel writers make conflicting implicit decisions (their Flappy Bird example). What works: "writes stay single-threaded and the additional agents contribute intelligence rather than actions"; a clean-context reviewer gave "a notable improvement"; manager-and-children splitting of big work took "more context engineering than expected". | **Batches write one after another, each carrying what earlier ones declared.** Parallel only for sections that share a fixed core. A clean-context reviewer at the end for big outputs. |
| [ThoughtTerminator](https://arxiv.org/html/2504.13367v1) | Reasoning models are badly calibrated on how long to think; reminding them of the remaining budget and forcing an answer at the limit cut overthinking sharply while generally keeping or slightly improving accuracy (figures from summaries). | A soft per-call reasoning budget is a different thing from a lower effort setting, but it is still a cap: measure per model before using it. |
| [Token Tax, ICML 2026](https://icml.cc/virtual/2026/67957) (via a [summary](https://tianpan.co/blog/2026/04/12/the-planning-tax-why-your-agent-spends-more-tokens-thinking-than-doing)) | On three 7-8B open models, bigger reasoning budgets raised cost over 110% with negligible quality gains; planning every 4-8 steps beat planning at every step. | Plan once per batch, not once per tool call. |
| LongWriter / AgentWrite and outline-then-expand work (from search summaries, papers not opened), and the input-side [divide-and-conquer study](https://arxiv.org/html/2506.16411v2) | Models struggle with very long single outputs; planned pieces give long, coherent output; an outline-then-expand pipeline distorts meaning less than one pass; chunking let smaller models beat larger ones on long inputs (an inference for outputs). | Shared outline (core), then pieces. |
| [OpenHands condenser](https://openhands.dev/blog/openhands-context-condensensation-for-more-efficient-ai-agents) | Summarise old turns, keep recent ones; reported up to 2x lower per-turn cost. | We already compact; batches add a second way to keep context small. |
| [llama.cpp reasoning budget](https://github.com/ggml-org/llama.cpp/pull/25961) | Recent builds take a per-request `reasoning_budget_tokens` (and a message injected when it runs out), but a server flag overrides the request, and builds after April 2026 had hang reports when the budget defaults to unlimited. | Verify on the owner's build before relying on it; never change the owner's server. |

**What none of this shows:** a direct measurement of splitting code-writing stages for small local
models. The closest are the long-output and long-context papers (an inference for output
length) and Agentless. So the design measures on our own benchmarks before anything is on by
default, and keeps the old single-call path as the fallback.

## 3. Design: one mechanism, every stage

**Work plan.** A stage that produces a list of things declares `items` (each with an id and a size
estimate), an optional `core` (what every batch must agree with), and how a batch's output joins
the others. One small module, no stage-specific logic in it.

**Batch size is measured, then adjusted.**
1. *The model's capacity* - the deep diagnosis gains one check: the most items of a stage-shaped
   task the model finishes in one reply, without repeating itself, cutting off or breaking the
   format (try 4, 8, 16, 32; keep the largest that passes two of three). Kept with the model in
   its fitness record, like the guides and tier.
2. *The work's size at run time* - items times the stage's own estimate against the capacity.
   Small product, strong model: one batch, which is today's request, unchanged. Large product or
   weaker model: several. (This is the "small and large codebases" rule: switch by measured size.)
3. *Evidence during the run* - a reply over a stage's own ceiling, a cut-off, a loop or a coverage
   hole in a batch halves the next batch (full, half, single). Never more than a fixed number of
   batches; past it, batches grow rather than multiply.

**Batches run in order and carry what came before.** The carry is compact: names, signatures,
fixtures and ids declared so far, never the earlier batches' full text. Independent sections that
share a fixed core may run side by side, as the specification's parts already do.

**Reasoning stays whole.** One planning call keeps its full reasoning; batch calls are not given a
lower effort by default. A soft per-call budget from the model's measurement is available but off
until a probe shows it costs no quality on that model.

**Every batched stage verifies mechanically, then falls back.**
- Coverage: every item id appears exactly once; missing ones are asked for again, alone (the
  LF.247 pattern: keep what was written, ask again for the rest).
- A check from the environment where one exists: the suite imports and collects, names are unique,
  the runner passes the setup's smoke test.
- Any failure the checks cannot repair: the stage runs today's single-call path and records
  `batching_fell_back`. Batching can cost time; it cannot be worse than the code it replaces.

**Each stage has its own switch** (`BATCH_<STAGE>`, code default off, owner override on the
settings page next to the guides), plus a master `WORK_BATCHING`. Same convention as the guides.

## 4. Stage by stage

| Stage | Unit | Coverage check | Existing precedent | Why here |
|---|---|---|---|---|
| Acceptance author | acceptance criterion (`AC-n`), grouped by area | each `AC-n` has a test | `suite.criteria(root)` already lists them; the runner is proven by the setup | 17k tokens a call on Ornith, whole suite in one go |
| Defect fix | defects per fixer | each defect has a stage | defect bundle size already exists | 1 defect: 56% fixed, 14% cut; 4+: 26%, 62% (first thing to check: what sets the bundle size today) |
| Principal architect | spec section; for big products, component by component | no empty section | `specification_parts` (core + parts), LF.215 revisions | 13.6k tokens a call on Ornith; big products will exceed any single reply |
| Technical lead, scrum master | milestone | every work order has an owner file set | none | p90 21.9k and 18.9k; 11% and 8% cut off |
| Reviews (acceptance, architecture, milestone, security) | file group, for large codebases | each file read by one reviewer | SZ size work (project map ranking) | p90 16-25k; clean-context reviewer per Cognition |
| Drafting | file | - | already one call per file | nothing to do |

## 5. How this avoids new defects

The owner will not read every test result, so the safeguards have to run by themselves.

1. **Shadow first.** The first deploy only *plans*: it records what each stage would split into
   (`work_split` transcript record: items, capacity, planned batches) and acts on none of it.
   I read a run's records against reality before anything is on.
2. **Identity at the top end.** With capacity at or above the work, the request must be
   byte-identical to today's. A test proves it per stage, so a strong model sees no change.
3. **Tests per stage, each proven to fail on the old code:** the split is a partition (union is
   the items, no overlap, order kept, no batch over the cap); odd replies (empty list, missing
   key, invented keys, extra keys, fenced JSON, prose) keep what was written and re-ask the rest;
   a batch cut off or looping halves the next; a coverage hole re-asks only the missing; the
   fallback path runs after two failures. These are the cases that found LF.247 and LF.248.
4. **Resumable.** Batch progress is part of the stage's saved state, so a deploy or an orphaned
   worker resumes at batch k, not from the start (mid-run deploys are common here).
5. **Budget guard.** A stage whose batches have used 1.5 times what the old single call would
   have is stopped and run the old way.
6. **A quality gate before default-on, per stage (MF.4):** a frozen SHA, two tasks-api runs, hidden
   score, quality set and mutation score. It must not lower any of them and must lower minutes,
   tokens a call or cut-offs; otherwise it is parked. A harder benchmark follows, since this is for
   larger products.
7. **Watched without anyone watching.** `loop.sh effects` reports, per switch: times fired, times
   fallen back, tokens a call before and after, coverage re-asks. An audit raises a line when
   fallbacks pass 20% or a stage re-asks more than once.

## 6. Build order (after the running gate run; nothing here touches it)

| Row | What | Why first |
|---|---|---|
| WB.8 | `loop.sh scan`: tokens a call and minutes a stage against the last five runs' medians, longest replies, redundant reads, a model's outliers; run at every audit | Cheap, no deploy, and it is how suggestions surface without a bug |
| WB.1 | The work-plan module, the capacity check in the diagnosis, shadow records, `effects` lines | Everything else rests on it; inert |
| WB.2 | Acceptance author batches | Largest per-call cost on this model; the unit and the coverage check are exact |
| WB.3 | Fixer bundle size set by capacity | Strongest existing evidence; first read what sets it today |
| WB.4 | Specification core and parts by size | For products larger than one reply |
| WB.5 | Work orders and sprint planning per milestone | |
| WB.6 | Review sharding for large codebases | |
| WB.7 | Settings page: capacity, per-stage switches, last fallbacks | |

One bundle at a time: validate, build, a fail-on-old test per row, the suite, one deploy.

## 7. Why this was not suggested earlier

Three honest reasons.
1. **I treated "reply too long" as the model's output problem.** Everything built for it
   (salvage, the 40k ceiling, the guides, the reasoning probe) limits, recovers or steers the
   *reply*. Splitting reduces the *work in the reply*, an input-side lever I never put on the
   list - and it is the lever you had already named in other words ("small and large codebases",
   "switch approach by measured size").
2. **At the 01:37 and 01:47 audits I saw 50k-token replies and filed them under "model
   behaviour, not a harness defect".** The question I should have asked is what in our request
   makes one call that big. The numbers were on hand: Qwen's acceptance author made 22-74 small
   calls, Ornith 14 large ones, for the same stage.
3. **The audit has no line for cost.** Its checklist is loops, failures, send-backs - defects.
   `loop.sh patterns` already prints the reply sizes and the defects-per-fixer table above, and
   the handover says to read it at each deep analysis; I did not run it at these audits. Nothing
   in the routine prompted a suggestion unless something was broken.

The fix is procedural, so it holds without anyone remembering: every audit runs `loop.sh patterns`
(and `loop.sh scan` once WB.8 exists), the report carries an "improvement" line whether or not
anything failed, and open suggestions are listed in `docs/STATE.md` so they survive a new session.

## Sources

[Anthropic: Building effective agents](https://www.anthropic.com/research/building-effective-agents) ·
[Aider leaderboard summary](https://leaderboard.steel.dev/leaderboards/aider/) ·
[Agentless](https://arxiv.org/html/2407.01489v2) · [ReWOO](https://arxiv.org/pdf/2305.18323) ·
[Cognition: Don't Build Multi-Agents](https://cognition.ai/blog/dont-build-multi-agents) ·
[Cognition: Multi-Agents, what's actually working](https://cognition.com/blog/multi-agents-working) ·
[ThoughtTerminator](https://arxiv.org/html/2504.13367v1) ·
[Token Tax (ICML 2026)](https://icml.cc/virtual/2026/67957) ·
[When does divide and conquer work for long context](https://arxiv.org/html/2506.16411v2) ·
[OpenHands condenser](https://openhands.dev/blog/openhands-context-condensensation-for-more-efficient-ai-agents) ·
[llama.cpp reasoning budget PR](https://github.com/ggml-org/llama.cpp/pull/25961)
