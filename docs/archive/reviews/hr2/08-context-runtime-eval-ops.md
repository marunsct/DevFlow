# 08 Context, runtime, evaluation and loop operations (HR2 reviewer 08)

Read-only review, 2026-11-07/08. Evidence: all 536 stored transcripts (one pass, scripts in
`scratchpad/review2/m08/`: `agg.py`, `render.py`, `prefix2.py`, `ledger.py`, `clean.py`), `data/kpi/ledger.csv`
(230 rows), `data/bench` (263 scored runs, 205 mutation files), Postgres `runs`/`audit_log`, the code paths named
below. "Today" = the 24 runs whose first record is after 2026-11-06 15:00 UTC (21 finished, 2 live, 3 cancelled):
4,919 model requests, 215.9M prompt tokens, 12.1M completion tokens.

## 1. What exists

**Context (what a request carries).** `observability/transcript.py:345-410` `prompt_blocks` splits every request
into `system`, `environment_contract` (the tail of the system message), `tool_schemas`, `project_memory`,
`specification`, `request` (every human message before the first reply), `workspace` (the digest), `notes`
(bracketed harness notices) and `conversation`; the record keeps sizes, not text. `observability/prefix_breaks.py:34`
fixes the opening order `environment_contract, project_memory, specification, request` and names why a call could not
reuse the previous call's prefix (`tools_changed` .. `first_of_a_conversation`), written to the ledger as
`prefix_break_<reason>` and `uncached_tokens_<reason>` (ledger columns 16-29). Caps: `models/__init__.py:249-330`
`FIX_STAGE_REPLY_TOKENS` 12,000 and `PLAN_REVIEW_REPLY_TOKENS` 20,000 for the eight planning/review stage prefixes,
both in the `PREMIUM_MODEL_TUNING` bundle (`switches.py:78-79`; the bundle is on, `docker-compose.yml:44`); the cap
is sent as `max_tokens` (`__init__.py:598-606`), the diagnosis's ceiling fills in when no cap is set
(`model_guidance.ceiling_for`, `__init__.py:607-616`). Reply salvage (`models/reply_salvage.py`, `BUILT_IN`,
`switches.py:51`): a reply cut at the cap is re-sent with its own reasoning begun and closed (`reasoning_field` or
`think_tags`, `SHAPES` line 50), or continued from where its text stopped (`MOST_CONTINUATIONS` 2); support is
measured once per served model (`measure`, line 202). LF.683 today: the reasoning tag is read from the server the run is
pinned to (`capabilities.reasoning_tag_if_missing`, `capabilities.py:542`). Constrained output exists in one place:
`agents/structured_extraction.py:81` sends `response_format: json_schema` with no tools when a stage answered in
prose (`STRUCTURED_EXTRACTION`, same bundle, on); `capabilities.measure` (line 454) records whether the server takes
a schema. Tool withholding is text: 516 of today's requests (10.5%) carry "the tools that look are withheld ...
refused if called"; the tool list itself stays bound (`STABLE_TOOLS`, built in). Diagnosis
(`models/diagnostics.py:331 diagnose`, `deep_diagnosis.py`, `model_guidance.py`): stage-shaped checks pick a steering
profile and a ceiling per served model; `model_pin.py` pins a run to a server.

**Runtime.** One Celery task drives a run until it pauses or finishes (`server/tasks.py:56-67`); a pause sets a flag
the next model call sees and raises `RunCancelled` (`graph/workflow.py:4111`; recorded as a `model_error` reading
"was stopped; this stage's call is not made"); `run_kpis.py:217` leaves it out of `model_errors`. The deploy gate
(`models/call_gate.py`) holds new calls while `inflight/` drains, 20 min at most. `scripts/loop/ship_live.sh`: wait
while a run is in `principal_architect` (900 s, then go), pause every running run, `loop.sh deploy`, resume, check
the pool. `loop.sh deploy` (line 495-560) **builds the images after the runs are paused** (line 506-507), then
waits for the stage boundary (`BOUNDARY_WAIT`, 0 from ship-live), then the gate, then `up -d`. LF.688 today: a deploy
whose containers were not replaced says so and exits 2. Orphan sweep: `tasks.py:131-300` at start and every 90 s
(`_RECURRING_SWEEP_SECONDS`), a row untouched for 60 s with no live task (`manage.py:539,604`). `runs.paused_seconds`
is kept in Postgres (`server/run_store.py:103,478`) but **no KPI reads it**; `active_minutes` subtracts only silences
over 600 s (`run_kpis.py:44,274,292`), which LF.682 now reads as model time when they sit inside one call.

**Evaluation.** 12 families, 8-15 hidden tests each (`benchmarks/README.md`); one quality set (tasks-api, 7 tests,
`score.py:165`); mutation for non-browser suites (`data/bench/mutation`, keys `score`, `score_with_unit_tests`).
`kpi_ledger.the_arm` (line 124) takes runs on exactly one commit and not mixed; `compare_arms` refuses under 2 runs an
arm (`MINIMUM_RUNS_PER_ARM`, line 109). `impact.py` (LF.681) leaves out spanning runs. `effects.py` reports each
mechanism's firing from transcript signals. `docs/measuring.md` is the one register (M1-M8).

**Operations.** `loop.sh` commands: ready, bench, score, audit, defects, effects, patterns, impact, suite-checks,
stack-misses, kpi, reads, timing, rewind (`--pause-only`), resume, deploy, ship-live, nightly (03:00 JST cron, skipped
while a run is live: ran 11-04, skipped 11-03 and 11-07). `audit_live.py` prints stage, tool failures, resumes,
duplicate executions, redundant reads (LF.689 today), stage order, failure signatures - nothing on tokens, cache,
salvage, caps or pauses. `docs/STATE.md` (150 lines), `HANDOVER.md` (1,055), `monitoring-handover.md` (1,483).

## 2. Measured

**Tokens per run and per stage (today).** Prefill/decode ratio 17.9 overall (ledger median over all runs 10.3).
Per run: 2.4M-47.3M prompt tokens; the same family differs 3-10x by how many fix rounds it took (fsb-py 6: 709
requests, 47.3M prompt; fsb-py RC14 1: 248 requests, 14.8M). Per stage family, share of today's prompt tokens:
acceptance_author 24.6% (995 requests, 53.2M), defect_fix_1 14.4%, specialist_testing 13.2% (364 requests, 28.5M
prompt for 240k completion - **prefill/decode 110**), stack_setup 9.0%, specialist_backend 8.4% (ratio 180),
defect_fix_2 8.3%, technical_lead 4.3%. The decode-heavy stages (architect, lead, architecture review, scrum master,
acceptance review) hold 57% of reasoning characters on 9% of prompt tokens; principal_architect alone 1.87M completion
tokens on 3.1M prompt (ratio 1.6). Reasoning = 36.1M characters ~ 9M tokens ~ 75% of all completion tokens.

**Blocks.** Mean share of a request: project_memory 22.8% (mean 57.9k chars, p90 105k), specification 22.8% (43.1k,
p90 68.7k), request 20.7%, conversation 11.7% (p90 94k; 122-151k in acceptance_author_1 and specialist_testing_1),
tool_schemas 11.4% (23-28k every request), system 8.2%, workspace 1.6%, environment_contract 0.9% (1,496 chars,
constant), notes 0.1%. In the builder and tester stages the memory is 95-105k chars a request (p90 107-124k):
specialist_backend_0 34.7% of its requests, specialist_testing_1 32.1%.

**Cache.** :8888 (llama.cpp): 2,829 responses, every one reports `cache_read`; cache share **78.5%** today (ledger
median 0.728 over 111 rows). :1234 (LM Studio): 1,983 responses, **0 report cached tokens** (it reports
`output_token_details.reasoning` instead, 2.88M tokens today); its share is unmeasurable from usage, and C1 now
records it as unknown. Prefix-break reasons today (21 benched runs, 3,445 classified calls): stable 70.1%,
first_of_a_conversation 14.5% (1,263 requests with `carried` 0, 25.7% of all - the architect's 229 parts, the fixers'
175 one-shots), opening_changed 12.3%, history_rewritten 2.7%, evicted 5, tools_changed 4, system_changed 3.
Uncached tokens by cause: stable 61.8M (the new suffix itself), opening_changed 10.7M, first_of_a_conversation 8.8M,
history_rewritten 2.6M, evicted 0.15M. So the opening (memory order, clock) still costs 10.7M uncached tokens a day
(5% of prompt) and the tools/system blocks cost nothing: the Appendix 9 ordering holds.

**Salvage and caps.** `salvaged` is "reasoning" or "continuation". Today 137 of 4,812 replies (2.8%): reasoning 131,
continuation 6; all stored 917 of 143,078 (0.64%) - today's rate is 4x the history, so the caps bite more on the
model now served. By stage today: technical_lead 36 of 152 replies (24%), defect_fix_1_* 26, scrum_master 9,
architecture_review 7, acceptance_review_2 5, acceptance_dispute 4. finish_reason=length only 4 today (the
unsalvaged one: principal_architect, 32k tokens, no cap applies). Reasoning per reply (median / p90 chars):
technical_lead 9,039 / 83,480; acceptance_review_2 40,645 / 78,426; scrum_master 12,158 / 77,487; acceptance_dispute
6,787 / 78,051; architecture_review 21,438 / 55,915; principal_architect 14,566 / 29,805. 78-83k characters is about
20k tokens: the p90 of four review stages sits exactly at the cap, so one reply in ten of them is a salvage
(a second call carrying up to 48k chars of reasoning back). Nothing records whether a salvaged answer was accepted
by the stage or re-asked.

**Model errors.** Today 102, every one `RunCancelled` (the pause marker), in 19 of 24 runs; by stage
principal_architect 41, architecture_review 14, technical_lead 12 - the long-thinking stages take the pauses. 84 were
followed by a request in the same stage. All stored: 779; after RunCancelled 361 the kinds are server-side:
"Engine protocol predict stream returned an error" 104, "No model loaded" 81, OpenAIConnectionError 50, "Free quota
exhausted" 21, "Lost connection" 17, timeouts 13, "Model unloaded by user" 12, model-not-found 20, llama-server
errors 18, invalid API key 10. The `model_errors` KPI (ledger sum 246) counts the owner's unloads and quota as the
harness's errors; it is on the regression list (`kpi_ledger.WORSE_WHEN_HIGHER`).

**Pauses, resumes, orphans.** Postgres `audit_log` since 11-06 15:00Z: run.pause 78, run.resume 73, run.rewind 5,
run.cancel 4, for 24 runs (3.3 pauses a run). `runs.paused_seconds` today 149.9 min over 21 paused runs (max a run
24.1 min; single pause max 12.7 min); the 7 days before: 2,152.7 min over 28 runs. Every pause under 10 min is inside
`active_minutes` (the ledger says wall 2,210 / active 2,172 today), so the time KPI carries ~2 h of deploy time it
cannot see. Orphan gaps today 37.1 min on three runs (14.2, 10.6, 12.3) - all long model calls by LF.682's reading;
last 7 days 3,398 min, three runs over 500 min each (ec3e81ab 945.6, 37f78b1b 728.3, 9790981c 553.1: runs left
paused over a night, not orphans). No `resumed` record today (288 in older files): a resume now rewrites
`provenance` (100 provenance records for 24 runs), so `audit_live`'s "resumed after its worker stopped" line and the
`resumes` KPI (0 today) no longer see deploy resumes.

**Can the measurement tell a change's effect?** Ledger rows since 11-05: 39; mixed 34, clean 5; 87 distinct SHAs
(none on more than 4 rows); today's 21 rows span ~50 SHAs (one run saw 8 commits). Clean runs per family on one SHA:
notes-api-hono 1+1, web-todo 1, fullstack-bookmarks-py 1, notes-api 1, notes-api-falcon 0, tasks-api 0. **No family
has two clean runs on any SHA**, so `compare_arms` refuses every pair (needs 2 an arm) and M1-M7 have no judgeable
arm. Hidden ceiling: 34 of the last 40 scored runs are 1.0; 4 false acceptances in the last 40. Family skew of the
scored set: notes-api-hono 93, tasks-api 54, web-todo 48, notes-api 19, fsb-py 19, falcon 8, wordstats-cli 6,
textkit-lib 5, tasks-api-change 2. Median active minutes a family: wordstats-cli 34.5, notes-api-js 45.3, textkit-lib
49.9, hono 55.8, falcon 61.6, notes-api 63.8, tasks-api 107.7, web-todo 126.5, fsb-py 139.6, tasks-api-change 151.1.
Mutation score, last 30 files: median 0.50 (last ten 0.27-0.75); the ledger has `mutation_score` and `quality_score`
columns (84-87) already.

**Tool withholding and unknown tools.** Today 0 of 3,908 tool calls named a tool absent from the request's list;
all stored 214 of 125,056 (0.17%), mostly invented names in review stages (edit_file from the lead/reviewers 62,
`changed_since_sprint`/`global_99`/`ReadFile` from the scrum master 66). The withheld-but-called case the first
review counted (22% of tool failures) is a refusal of a listed tool, not an unknown one; the transcript has no field
for it (`layer_tool_withheld` in the ledger counts the notice, not the refusals).

## 3. The first review's items in this area

| Item | State | Evidence and view |
|---|---|---|
| C1 unreported cache = unknown | BUILT | 111 rows now carry a share; today's :1234 runs none. Right. |
| C2 constrained answers | **partly built already** - `STRUCTURED_EXTRACTION` (on) sends `json_schema` when a stage answered in prose (`structured_extraction.py`) | The review listed it as "to build". What is left: the answer-only steps of `settled_answer` that still repair by reminder. Measure first: how many prose-answer reminders today vs schema re-asks (`effects` has no signal for it - add one). Reshape to "C2b: the schema re-ask first, the reminder second", switch. |
| C3 mask withheld tools | open, **low** | 0 unknown-tool calls today; withholding refusals not counted. Masking per call changes the tool list, which `prefix_breaks` would read as `tools_changed` (today 4 breaks). Only logit masking keeps the prefix, and LM Studio has no per-request logit bias; llama.cpp's `tool_choice` is read as `auto` (`structured_extraction.py:4-7`). Park until a refusal count shows waste. |
| C4 opening-stable memory + tail deltas | open; `CANONICAL_MEMORY` (PX.3) is on in the bundle | opening_changed is still 12.3% of calls and 10.7M uncached tokens a day. Next measure: which opening block changes (the ledger has only the reason, not the block) - HR2.C.3 below. |
| C6 repo map for large codebases | open | No large-codebase run exists to measure it on (tasks-api-change 2 runs). Build after E3's brownfield brief. |
| C7 finish reasons | BUILT (LF.677) | finish_reason None 0 today. |
| R1 rewind lineage | BUILT (LF.660) | 5 rewinds today, no duplicate executions reported. |
| R2 drain deploys | measured not needed | Confirmed: 102 cancellations, all refused before sending. But the cost moved, it did not vanish: the stage restarts from its checkpoint and the architect's parallel parts are lost (ship-live's own comment; 41 of 102 in principal_architect). See HR2.R.1-R.2. |
| R3 heartbeat orphans | measured not needed | Confirmed, 0 real orphans today. |
| R6 environment contract in the system block | BUILT (LF.675) | 1,496 chars constant in 4,029 requests. |
| E1 ledger integrity, impact excludes spanning | BUILT (LF.681) | Right, but with 87 SHAs in 39 runs nothing is left to compare (section 2). |
| E2 pass^k + Wilson | open | **reshape**: with 2 runs an arm pass^2 is 0, 0.25 or 1 - no interval helps. pass^k belongs to the RC count on one frozen SHA (k = runs per family), not to arms. For arms use counts, not a binary (HR2.E.3). |
| E3 held-out briefs | open | `tasks-api-change` exists (brownfield, 15 tests, 2 runs, 10/15 base); cli and lib families are the shortest runs (34-50 min) and the least run (5-6). |
| E4 20-30 hidden tests | open | ceiling unchanged: 34/40 at 1.0. |
| E5 mutation as a gate KPI | **column exists** (`mutation_score`, ledger col 86); not in `impact.KPIS` or the RC rule | add it to both (S). |
| E6 round-robin Measure batches | open | the precondition is a frozen SHA; see HR2.E.1. |
| Reviewer 06's "cache 0 bug" | fixed (C1) | - |

## 4. Research (what fits)

- **Manus, "Context engineering for AI agents" (2025-07-18, manus.im/blog):** KV-cache hit rate as the first production
  metric; append-only context, deterministic serialisation, mask tools by logits rather than remove them. Fit: our
  `prefix_breaks` already measures the hit rate by cause; the finding that 70% of calls are stable and the uncached
  tokens are mostly the new suffix means the next gain is in *what* the suffix carries (memory, conversation), not in
  the prefix order. Logit masking is out of reach on LM Studio (section 3, C3).
- **Anthropic, "Effective context engineering for AI agents" (2025-09-29):** compaction near the limit, structured
  notes outside the window, sub-agents with their own windows. Fit: the harness already keeps notes
  (`project_memory`) outside the conversation; what it lacks is *just-in-time* loading - the memory is 95-105k chars
  for every builder request (HR2.C.2 generalises M8).
- **llama.cpp server (tools/server/README):** `cache_prompt` on by default, `--cache-reuse N` reuses KV chunks after
  a shifted prefix (PX.6 notes it as owner advice), `--slot-save-path` saves a slot to disk, `/slots` shows per-slot
  state, `response_format` with `json_schema`/`grammar`, draft-model speculative decoding (`-md`, `--draft-p-min`).
  All are the owner's server settings; the harness may only *read* them (`/props`, `/slots`). Fit: a `/slots` read
  before each call would tell whether a stage's thread still holds its slot (PX.7's eviction question: 5 evictions
  today, so PX.7 and PX.8 stay parked - evidence for the Appendix 9 gate).
- **LM Studio docs (api-changelog; structured-output):** `response_format` json_schema is supported through the
  OpenAI-compatible endpoint; usage carries prompt/completion tokens (0.3.24+) and reasoning tokens, no cached-token
  field; speculative decoding since 0.3.10. Fit: cache share on :1234 cannot come from usage. A per-call
  time-to-first-token against prompt size (the pace table `record_pace` already keeps tokens/seconds) would estimate it;
  marked as an estimate, never as a share (HR2.C.1).
- **tau-bench (Yao et al. 2024, arXiv 2406.12045):** pass^k = E[C(c,k)/C(n,k)], the chance all k trials pass;
  under independence (pass^1)^k. Fit: an RC criterion on a frozen SHA (n runs a family, report pass^k for k=2), not an
  arm statistic (E2 reshape).
- **SWE-bench Verified (OpenAI 2024-08) and its 2026 note ("increasingly contaminated; use SWE-bench Pro"); Epoch AI's
  review; SWE-rebench (timestamped, refreshed):** validate tests two-sidedly, and refresh the task set because a
  static set is tuned to. Fit: E3's held-out briefs must be *rotated*: a brief used to write an LF fix joins the
  training set and a fresh one replaces it (HR2.E.4).
- **MUTGEN (2025-06, arXiv 2506.02954), EvoGPT (2025-05), MuTAP (2023):** mutation score, not coverage, as the test
  quality metric (suites at 100% coverage with 4% mutation score). Fit: E5 - the column exists; make it a KPI.
- **Celery 5.5/5.6 (docs.celeryq.dev workers guide):** warm shutdown finishes in-flight tasks; `worker_soft_shutdown_
  timeout` bounds it; 5.6 keeps heartbeats during warm shutdown. Fit: our gate already drains at the call boundary; the
  loss is the *stage* restart, which no Celery setting addresses - HR2.R.2 moves the pause to a stage boundary.
- **LangGraph durable execution (docs.langchain.com, 2025-2026):** durability `sync|async|exit`; a resumed run restarts
  from the start of the interrupted node; time travel = `update_state(as_node=...)` then invoke from the checkpoint,
  a fork. Fit: forking one stage from a finished run's checkpoint with a switch flipped is a stage-level A/B that
  costs minutes (HR2.E.2); the runner has `rewind_points`/`rewind_run` already (`runner.py:1194-1240`).
- **OpenTelemetry GenAI conventions (Development status as of 2026-05):** `gen_ai.usage.input_tokens`,
  `output_tokens`, `cache_read.input_tokens`. Fit: our transcript already carries these per call; the gap is the
  *audit*, not the record (HR2.O.1). No exporter is needed now.

## 5. New items

**HR2.C.1 - cache share on a server that reports none, estimated from pace (doubtful, observability).** Evidence:
0 of 1,983 :1234 responses report a cache read; 41% of today's calls run there. Change: per call record
`time_to_first_token` (streaming is already in use: `streaming_spike.py`) and prompt tokens; a prefill that runs at the
server's measured cold rate is uncached, one 5x faster is cached; the ledger gets `cached_share_estimated` beside
`cached_token_share`, never in its place. Test: a response with TTFT 0.2 s on 40k prompt tokens on a server whose cold
prefill is 2k tok/s is counted as a cache hit; the ledger row keeps `cached_token_share` None. KPI: the Context-and-cost
arm (M3) can then be judged on both ports. Size S. Risk: an estimate, so labelled one.

**HR2.C.2 - memory by need in builder and tester stages (M8 generalised; doubtful, switch `MEMORY_BY_NEED`).**
Evidence: specialist_testing 28.5M prompt tokens for 240k completion today (ratio 110), specialist_backend ratio 180,
memory 95-105k chars a request (p90 124k); M8 measured the same for rewrites (median 64.6k). On :8888 this is 78%
cached, but each stage visit's first request and every opening change pay it in full (8.8M + 10.7M uncached tokens a
day), and on :1234 the whole of it may be prefill. Change: in `specialist_*`, `defect_fix_*` and `stack_setup` the
memory block holds the files the work order or defect names plus their imports and the specification sections they
cite; the rest is a one-line index the model can read on demand. Test: a work order naming two files gets a memory
block of those two files and their imports, under 25k chars, while the architect's request is unchanged. KPI: prompt
tokens and minutes per builder/tester/fix stage; hidden score and defects left open must not fall. Size M. Risk:
a builder missing a file it needed - the index and the read tool cover it; measure redundant reads.

**HR2.C.3 - name the opening block that broke the prefix (bug, measurement).** Evidence: `opening_changed` is 424
calls and 10.7M uncached tokens today, but `prefix_breaks.reason` (line 82) returns one word for four blocks, so
nothing says whether the memory, the specification or the request moved. Change: `opening_changed:<block>` with the
size delta, summed to `uncached_tokens_opening_<block>`. Test: two records whose `project_memory` size differs give
`opening_changed:project_memory`. KPI: the input to C4's design. Size S.

**HR2.C.4 - a salvage records its outcome; caps set from the measured p90 (bug, then doubtful).** Evidence: 137
salvages today (2.8%, 4x the history); technical_lead 24% of replies; four review stages' p90 reasoning sits at the
20k cap; a salvage re-sends up to 48k chars of reasoning and nothing records whether the stage took the answer.
Change (bug): the next request in the same stage records `after_salvage: accepted|re-asked|cut_again`, summed to a
`salvage_success_rate` KPI; `loop.sh effects` gets the line. Then (switch `CAPS_FROM_THE_DIAGNOSIS`): the per-stage cap
is the served model's measured p90 reply for that stage family (kept with its diagnosis, `fitness_dir`), floored at
`SMALLEST_REPLY_CAP`, instead of the two constants. Test: a diagnosis recording p90 24k for `technical_lead` sends
`max_tokens` 24,000; a stage with no measurement keeps 20,000. KPI: salvages per run, planning minutes. Size S + M.

**HR2.C.5 - the schema re-ask before the reminder (C2 reshaped; doubtful).** Evidence: `STRUCTURED_EXTRACTION` is on
and sends a schema only after a prose answer was already reminded (`structured_extraction.py:1-18`); the first review
listed C2 as unbuilt. Change: when the server's `json_schema_answers` capability is measured true, an answer-only step
(no tools offered) is asked with the schema on the *first* call. Test: a stage whose request offers no tools sends
`response_format` on its first payload when the capability is true, and not when it is false. KPI: prose-answer
reminders per run (add the signal to `effects.py`). Size S. Risk: a schema the server's converter refuses - it already
falls back.

**HR2.R.1 - `active_minutes` subtracts the recorded pauses (bug).** Evidence: `runs.paused_seconds` is kept
(`run_store.py:478`) and never read by `run_kpis.py`; today 149.9 paused minutes sit inside `active_minutes` (max
single pause 12.7 min < the 600 s orphan threshold); the 7 days before carried 2,152 min. Change: the KPI job reads
`paused_seconds` for the run and takes it off `active_minutes`, writing `paused_minutes` as its own column; `impact.py`
and `compare_arms` read the corrected column. Test: a run with wall 60 min and paused 300 s reports active 55.0 and
paused 5.0. KPI: every time KPI. Size S.

**HR2.R.2 - the pause lands at a stage boundary, in the runner, not in the script (bug-class, waste).** Evidence:
78 pauses for 24 runs today; 41 of the 102 cancelled calls were in `principal_architect` and 14 in
`architecture_review` although `ship_live.sh` waits up to 900 s for the architect (then deploys anyway) and
`rewind --pause-only` can be called directly; a cancelled architect loses its parallel parts and the revision starts
over (ship-live's own measured case: ten rewrites lost, four findings found again). Change: `runner.pause_run` takes
`at="boundary"`: the flag is honoured only when the graph is between nodes (the checkpoint the gate loop already
sees, `runner.py:174`), with a ceiling of one stage; `ship_live` passes it and the 900 s loop goes. The build
(HR2.R.3) runs before the flag is set. Test: a pause requested while a node runs is applied at the node's end and the
transcript shows no `RunCancelled`. KPI: `RunCancelled` per run (today 4.3), paused minutes, architect restarts.
Size M. Risk: a stage that runs 40 min delays the deploy - the ceiling keeps today's behaviour as the fallback.

**HR2.R.3 - build before the pause (bug-class, waste).** Evidence: `ship_live.sh` pauses every run, then
`loop.sh deploy` builds both images (`loop.sh:506-507`) before `up -d` (line 554); the build runs inside the paused
window, and its duration is not logged; pause-to-resume gaps today were 2-12.7 min a pause, 150 min in all. Change:
`loop.sh deploy` splits into `build` (no pause needed, prints its seconds) and `swap`; ship-live builds first, pauses,
swaps, resumes; tonight's Docker Desktop hang is caught at the build, before any run is touched (the `docker info`
timeout 20 s probe goes in the same place). Test: ship-live with a failing build touches no run (no pause in
`audit_log`). KPI: paused minutes a deploy. Size S.

**HR2.R.4 - `model_errors` by kind (bug, measurement).** Evidence: of 779 stored model_error records, 361 are
pauses (already excluded), 93 are the owner's unload/no-model, 21 quota, 80 connection/lost, 13 timeouts, 104 engine
stream errors - all counted as `model_errors` and flagged as regressions. Change: classify the error text into
`server_unavailable`, `owner_action`, `request_rejected`, `timeout`; only `request_rejected` stays in
`WORSE_WHEN_HIGHER`; the audit prints the kinds. Test: "No model loaded" counts as owner_action, not model_errors.
Size S.

**HR2.R.5 - a resume writes a `resumed` record again (bug, observability).** Evidence: 73 resumes today, 0
`resumed` records (288 in older files; 100 provenance rewrites instead); `audit_live` and the `resumes` KPI read
`resumed`. Change: the resume path appends the record it used to (or the audit and KPI read provenance segments). Test:
a transcript with two provenance segments reports `resumes 1`. Size S.

**HR2.E.1 - per-run switch arms on one SHA (quality of measurement; the least run time).** Evidence: 87 SHAs in 39
runs since 11-05; no family has two clean runs on one SHA; `compare_arms` needs 2 an arm; M1-M7 are unjudgeable, and
each off arm today needs a deploy that itself marks the live run mixed. Change: a run carries its own switch overrides
(`runs.switches`, set at `loop.sh bench --off SWITCH` / the run page; `switches.is_on` reads the run's overrides first,
`provenance` already records which switches were on); `the_arm` takes `(sha, switch, state)`. Then one frozen SHA
serves both arms on both ports at once, interleaved per family: four runs a family give 2+2 with no deploy between
them. Test: two runs on one SHA, one with `MILESTONE_EVIDENCE_GATE` off, fall into different arms. Size M. Risk: a
run-level override that leaks into another run's worker thread - the override is read from the run record the task
holds, not the environment.

**HR2.E.2 - stage-level A/B by forking a checkpoint (doubtful tooling).** Evidence: the Context-and-cost and
Efficiency switches (M3, M4, M8, HR2.C.2) change tokens and minutes of particular stages, and the hidden score cannot
move on a ceiling of 34/40; a whole run costs 35-150 min. Change: `loop.sh fork <run> <stage> --off SWITCH` forks a
finished run's checkpoint before `<stage>` (LangGraph `update_state(as_node)` + invoke from the checkpoint, as
`rewind_run` does, `runner.py:1204`) into a scratch run that stops at the stage's end; `kpi` reports the stage's
tokens, minutes, tool failures and - for the acceptance author - the locked suite's checks, side by side. Test: a fork
of a stored run reports the stage's KPIs and leaves the original's status untouched. KPI: per-stage. Size M. Risk:
a stage whose outcome depends on later stages - the hidden score still needs full runs; this is for the
efficiency arms only.

**HR2.E.3 - arm comparison on counts, not on a binary (E2 reshaped; bug, measurement).** Evidence: 34 of 40 runs
score 1.0; two runs an arm give 0, 0.5 or 1. Change: `compare_arms` reports hidden tests failed (count), false
acceptances, defects left open, mutation score, paused-corrected active minutes, prompt tokens by stage family - each
with min-max over the arm; pass^k (k = runs a family) goes to the RC report on the frozen SHA only. Test: two arms
scoring (1.0, 0.9) and (1.0, 1.0) report "1 hidden test lost" rather than equal means. Size S.

**HR2.E.4 - rotate the held-out set (E3 reshaped; quality of measurement).** Evidence: SWE-bench Verified's 2026 note
and SWE-rebench: a static set is tuned to; LF.569/579/599 were written after specific hidden failures; hono is 93 of
263 scored runs. Change: `benchmarks/<family>/bench.json` carries `held_out_since`; `loop.sh bench` refuses a held-out
family for a learning run; the first LF fix that cites one of its hidden tests retires it to the learning set and the
log names the next held-out brief to write. Test: a family marked held-out refuses `bench` unless `--measure`. Size S
(+ the briefs themselves, L).

**HR2.E.5 - mutation score and quality score in `impact.KPIS` and the RC rule (E5; bug, measurement).** Evidence:
ledger columns 86-87 exist; `impact.KPIS` has hidden_score, fix_rate, active_minutes, defect_fix_stages...; median
mutation 0.50 and falling (0.58 before). Change: add both, more is better; the RC count requires mutation >= the
family's median of its last ten. Test: an impact report flags a change after which mutation fell by a quarter. Size S.

**HR2.O.1 - the ten-minute audit reads what it cannot see today (bug, observability).** Evidence: today's audits
could not have seen 137 salvages, 102 pause cancellations, 150 paused minutes, a 110:1 prefill/decode stage, or
:1234's unknown cache; `audit_live.py` prints none of them. Change: five lines - `salvaged n (stage: n)`,
`replies at the cap n`, `pauses n / paused min`, `prefill:decode this stage` with the memory block's size, `cache
share x% | unknown (server reports none)`; a stage over 60:1 or a memory block over 80k chars is named. Test: a
transcript with one salvaged reply and one RunCancelled prints both lines. Size S.

**HR2.O.2 - STATE.md's live and last-runs blocks generated from the data (ops; quality of the handover).** Evidence:
`docs/STATE.md` line 7 says "As of 2026-10-29 13:20 JST" while its Live block is from 11-04 and today's runs are
absent; three documents (STATE 150, HANDOVER 1,055, monitoring-handover 1,483 lines) repeat the run log. Change:
`loop.sh state` writes the As-of line, the live runs (status, stage, port, SHA, mixed) and the last three scored
runs from Postgres, `data/bench` and the ledger into marked blocks of STATE.md; the hand-written part is the next
action and what is off. Test: the generated block names the live runs Postgres lists. Size S.

**HR2.O.3 - the nightly runs on the idle port, or on a schedule gap it makes (ops).** Evidence: the nightly skipped
itself on 11-03 and 11-07 ("a run is live"); with two ports a run is nearly always live, so pack verification and
`check_the_library` (LF.685) run every third night at best. Change: the nightly skips only when *both* ports are busy;
`verify_packs` uses a scratch workspace and no model, so a live run on the other port is not touched. Test: with one
live run the nightly proceeds. Size S.

## 6. Priority order and expected effect

1. **HR2.R.1, R.4, R.5, C.4 (bug part), E.3, E.5, O.1** - a day's work, host and KPI code only, no run-time cost.
   Effect: the time KPI loses ~7 min/run of invisible pause time (10% of a 70-min run); the arm report becomes
   readable; the audit sees salvage, pauses and prefill waste in its window.
2. **HR2.E.1 per-run arms** (M), then **R.3 build-before-pause** and **R.2 boundary pause** (S + M). Effect: a frozen
   SHA can serve all of M1-M7's arms on both ports at once - roughly 4 runs a family per switch instead of 4 runs plus
   two deploys that mix the neighbours; pauses fall from 3.3 a run to the deploys that remain, and the architect's
   lost parts (41 cancellations today) go. Expected minutes: 5-12 a deploy, ~2 h a day at today's cadence.
3. **How to run the measurement arms with the least run time**, given one frozen SHA and HR2.E.1:
   - Order the switches by expected effect in minutes and run them as *pairs on both ports* on the two shortest
     families that exercise the mechanism (wordstats-cli 34 min and textkit-lib 50 min for Context/Efficiency and
     M7; notes-api/falcon 62 min for M6 and M1; web-todo/fsb-py only for M1's browser checks): on-port A / off-port B,
     then swapped, so 4 runs give 2+2 and the port is balanced.
   - Judge M3/M4/M8/HR2.C.2 on HR2.E.2's stage forks first (minutes each); send only the survivors to full runs.
   - M1's thirteen checks are one group: one off arm of 2 runs on the two families where its checks fire most
     (web-todo, tasks-api), not 2 per family.
   - M2's three bundles: measure the bundle with the largest token share first (`PREMIUM_PROJECT_INTELLIGENCE`,
     memory and graph), the others only if it moves something.
   - Budget: M7 + M6 + M1 + one bundle = 8 + 4 + 4 + 4 = 20 runs ~ 22 h on two ports, instead of the 2-per-family
     rule's 6 families x 2 arms x 7 rows = 84 runs.
4. **HR2.C.2 memory by need** (M, switch) and **C.4's measured caps** - the largest token lever in the data
   (specialist stages' 28.5M + 15.2M prompt tokens today) and the salvage rate; judged on stage forks, then two runs.
5. **HR2.C.3, C.5, C.1** - cheap measurement and the schema-first re-ask; **E.4, O.2, O.3** - the loop's hygiene.
   C3 (masking) and PX.7/PX.8 (slots) stay parked on the evidence: 5 evictions and 0 unknown-tool calls today.

Sources: manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus (2025-07-18);
anthropic.com/engineering/effective-context-engineering-for-ai-agents (2025-09-29); llama.cpp tools/server/README
(mvysny.github.io/llama-server-endpoints summary); lmstudio.ai/docs/developer/api-changelog and
/docs/developer/openai-compat/structured-output; arxiv.org/abs/2406.12045 (tau-bench); openai.com/index/introducing-
swe-bench-verified; epoch.ai/benchmarks/swe-bench-verified/review; arxiv.org/abs/2506.02954 (MUTGEN);
docs.celeryq.dev/en/v5.6.3 workers guide; docs.langchain.com/oss/python/langgraph/durable-execution;
opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans.
