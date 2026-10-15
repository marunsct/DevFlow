# How this harness is monitored, what that has found, and where to look next

**Written for:** whoever continues the harness-hardening loop from here, on a
different account and with none of this conversation's context.

**As of:** 2026-10-11 13:00 JST (stage 1 gate: 2 of 2 clean runs — STAGE 1 GATE PASSED!; active run on `tests/brief_medium.md`; start at
`docs/HANDOVER.md` §0), branch `harness-hardening-session`, pushed to the git
remote named `main` (`git push main harness-hardening-session`). Section 0 is
kept current by whoever runs the loop - **in the same commit as any change to
how runs are tested** (the gate, the cadence, the scripts, how a product's
tests are set up and run, what the healthy numbers are; owner, 2026-10-04).
Sections 1-10 are the method and history written on 2026-09-24 and still hold
unless section 0 says otherwise.

**What this document is not.** It is not a list of what to change. That lives
in `docs/harness-improvement-plan.md` (the current plan) and in the git
log of this branch, where every fix's commit message says what a run did and
why the change answers it.

---

## 0. Start here: the loop as it runs now

### 0.1 The standing instruction

Run a continuous audit / fix / deploy loop on this harness, and do not stop:

1. start a run of a brief;
2. audit its transcript, logs, database and tool calls closely - especially
   failed and unnecessary calls - every **~10 minutes in a run's first 40
   minutes** (so the early stop below can bite), then every **~18 minutes**
   (not more often; it costs tokens);
3. fix what the harness did wrong, **technology-agnostically**: the harness
   builds full-stack apps in any language or framework, so a fix must not
   assume JavaScript, npm or a browser. Language/framework guidance belongs in
   the `plugin_instructions` table and its seed, `src/app/plugins/seed.py`,
   never hard-coded in prompts. Product-agnostic too: a rule written into an
   agent's instructions must fit an API, a CLI or a service as well as the
   to-do app the test briefs describe - no examples from the brief ("task",
   "the add form"), no UI-only words (button, click, focus, keyboard) in a
   rule meant for every product. Phrase it over capabilities, entry points and
   paths, and give it a test that bans those words (whole-word match; see
   `tests/test_a_criterion_is_checked_per_action.py`);
4. add a test for every fix, **prove it fails on the unfixed code** (stash the
   fix or make it a no-op, run the test, restore), run the full suite;
5. commit, push, deploy, and start the next run.

**Early stop (operator, 2026-09-30).** Any bug found in a run's first 40
minutes: cancel it (`loop.sh cancel`), fix, deploy, start a new run - do not
wait for it to finish. A major harness bug or gap found at any point: cancel
immediately, fix, restart. So during the first 40 minutes check every ~10
minutes (`loop.sh wait 10`), not every 18.

**Mid-run deploys when defect fixed (owner instruction 2026-10-10 18:45 JST):**
When a harness defect is caught during a run, implement the fix and test immediately. Deploy mid-run (`loop.sh deploy`) and wait for orphan recovery to resume it (`loop.sh resumed`) once the fix is verified (not at an exact scheduled time), so that the run is not held on the same defect and we can observe the rest of the run for subsequent defects and improvements. Design each fix fully before deploying: trace every other path it touches and verify with tests proven to fail on the old code.

**The gate (since the 2026-10-03 redesign; `benchmarks/README.md`).** A run is
*clean* when its product scores 100% on the benchmark's hidden tests
(`loop.sh score`), the run needed no harness fix, and the product audit (0.4.1)
passes. Stage 1: `web-todo`, 2 consecutive clean runs. Stage 2: `notes-api`,
`wordstats-cli`, `textkit-lib`, 1 clean run each. Stage 3:
`fullstack-bookmarks`, 2 consecutive. Then `tests/brief_medium.md` and
`tests/brief_high.md`, audited by hand. A run in which anything was fixed
resets the count to zero, including a fix deployed while it ran. (Before the
redesign the gate was two clean hand-audited runs each of `tests/brief_low.md`,
`brief_medium.md` and `brief_high.md`.)

**Keep, and fix only where wrong:** dynamic agent instruction injection (the
`plugin_instructions` table, the seed and its middleware), the parallel/linear
execution toggle in settings, and the sprint summary.

**Stack selection and scaffolding:** Never force the model to pick only from
pre-existing scaffolds. If the best open-source option for a brief is not in the
existing scaffolding, allow the model to choose the ideal open-source stack,
and implement/extend scaffolding for open-source frameworks.

**Never:** hard-code run ids (`tests/test_no_run_ids_in_the_source.py`
enforces it), read or reset the `admin` password, use the admin account for
the loop, write the settings table directly (settings need admin; the owner
sets the model, its endpoint and parallel mode - now `openai/gpt-oss-20b` on
LM Studio `:1234`, see 0.3.1), print values from `.env`, kill the owner's GPU
processes (llama-server and friends), load a model yourself, add
knowledge/doc credentials to `sandbox._ENV_PASSTHROUGH`, or commit or alter
`docs/logs.md` (the owner's own file; it always shows as modified).

### 0.2 Where it stands

A new agent, session or account starts at `docs/HANDOVER.md`: the first ten minutes, the standing instruction, the current state, what to verify on the next run, setting up on another desktop, and the security rules. The gate row below is the full run history, newest first.

| | |
|---|---|
| brief | the benchmark in `benchmarks/` the gate is on (`benchmarks/README.md`); `data/loop/current_brief.txt` |
| clean runs toward the gate | **stage 1 (web-todo) passed.**
  - **2026-10-12 13:40 JST:** the owner directed testing on `tests/brief_medium.md`, parallel mode first, then linear.
  - **run-c83ee867** (13:40-14:34 JST) FAILED in sprint planning: two lost replies; the second ended the stage before thinking could be switched off for the rest of the visit. Fixed in `b0c092c` (the settled-answer hook jumps back to the model after a lost reply). **run-c7a1f6cf** (21:19 JST - 07:11 JST 2026-10-13) FAILED at 9 h 52 min: a defect-fix stage exhausted its retries (fixed in `2e4e2ef`: fix and work-order stages fall back to blocked, leaving the defect open). Deployed `79089ea` (Node 24, Angular/Nest/Rails/Laravel packs; 27 of 27 verified in the live worker) at 08:15 JST; run-d1899b44 (08:19 JST) CANCELLED at 44 min: no pack fitted because the selector left the frontend field unstated while naming the pack in its rationale (fixed in `e95d943`). run-23896345 (brief_medium, parallel) started 09:07 JST on `e95d943`. Scaffold proven (`fullstack-react-fastapi`); the owner set an LM Studio reasoning budget of 7,500 at about 10:03 JST and no reply has been lost to reasoning since. Sprint 1 was dispatched as one work order because a thinner unready plan outranked a fuller one (fixed in `70c2e66`). A false 'acts on the page' finding on an API test reopened the locked suite twice (fixed in `fbe6bb4`). Those fixes and the parallel stagger fix were deployed into the run at 11:56 JST and it resumed. `58600ee` (pushed 12:19 JST, deploy between runs; HANDOVER §2.0): `look_up_package`, a proven setup for a stack no pack covers (`stack_setup_<n>`, contract pack `proven-setup`), and `use_runtime` per-project runtimes. `d9fd387` (pushed 12:53 JST, also between runs): compiler checks for Go/Rust/Java/C#/Swift/PHP, `look_at_page`, `read_docs`, opt-in MCP servers, eight CLI/library packs (35 in all), unknown frameworks no longer matched to another pack, `loop.sh freshness|lessons|nightly`, and `benchmarks/notes-api-hono`. Suite-repair budget fix `e985111` deployed into run-23896345 at 13:57 JST from branch `live-run-23896345` (live code + that fix only); it resumed. Two locked login tests can never pass (`res.json` on a plain object) and the budget had been spent on the earlier false finding. At 14:20 JST the dispute it allowed reopened the suite for them (DR-10). **14:36 JST: PAUSED by the owner to change the model** - the worker container is stopped (`docker compose stop worker`), the run still reads `running` in the database. To continue: the owner switches the model in LM Studio and the harness settings, then `loop.sh ready` (ALL READY), `docker compose start worker`, `loop.sh resumed`. **14:40 JST: resumed** on `qwen3.8-flash-next-iq2_xs` (llama-server, `host.docker.internal:9090`); readiness was checked in the app container first (`docker compose exec -T app python - < scripts/loop/model_ready.py`), since `loop.sh ready` needs the worker and starting it resumes the run. The rest of this run is on that model. 15:19 JST: suite relocked (DR-11, 54 tests, login tests repaired) with a new test calling undefined `getTask`; reopened at once (DR-12, repair 4 of 4). 16:16 JST: the test-file name check `4774f20` deployed from `live-run-23896345` (live code + `e985111` + `4774f20`); the run resumed. **16:21 JST: CANCELLED by the owner** (admin account, from the UI) at 7h14m, in sprint 1's acceptance repair (`acceptance_author_2`); afterwards the model server on port 9090 did not answer and LM Studio listed no model. Next run waits for the owner's model choice and `loop.sh ready`. The owner asked to resume it on `unsloth/Qwen3.8-27B-GGUF` (`host.docker.internal:8888`, set by the owner). Writing its row directly was refused by the session's safety check, so pause/resume was built (`2ea697d`: resume accepts `cancelled`), deployed from `live-run-23896345` at 16:41 JST, and the run was resumed through `POST /api/runs/{id}/resume` at 16:42 JST; it is in `acceptance_author_2` again. 17:16 JST: the owner's settings moved the model to `Atria-Dawn-Preview` (`https://api.atria-asi.ai/v1`, hosted) and the run followed at once (settings are read per call). Its gateway returned 502 after ~5-6 min on long calls - three times in a row on one review call (17:43-17:53) - so the run was PAUSED through the API at 17:54 JST (it stopped at 17:57 after its real task was revoked by hand, see the task-id fix). It is `paused` in `acceptance_review_3`; resume with the Resume button or `POST /api/runs/{id}/resume` once the model is settled. 18:44 JST: resumed on `qwen3.8-max-0902` (Qwen cloud) after the owner fixed its key (the stored key had been Atria's - the reason for per-endpoint keys). 19:27 JST: everything deployed (`c7dada5`: parallel fixes and reviews, two model tiers, detailed specification, per-endpoint keys) and the run resumed on it. 20:23 JST: two tiers - build model `AtomicChat/Ornith-1.5-35B-A3B-GGUF` (port 8888), frontier `qwen3.8-max-0902` (Qwen cloud); paused and resumed through the API so the frontier is used (logged "Judgement stages run on qwen3.8-max-0902"). **20:34 JST: a second run, run-63d016f6 (`notes-api-hono`), started beside it.** `data/loop/current_run.txt` now names run-63d016f6; for run-23896345 pass its id: `loop.sh status <run>`, `loop.sh wait <minutes> <run>`. 20:39 and 21:02 JST: Qwen cloud's free quota ran out for `qwen3.8-max-0902`, then `qwen3.8-max` (403 'Free quota exhausted'); run-23896345 failed twice and was resumed; the owner moved the frontier to `kimi-k3` at about 21:05 JST. Fixed in `526b5b4`: a provider out of quota is not retried and parks the run as `waiting_for_budget`. **21:07 JST: the owner asked for one run at a time, the newest (it plans with the detailed specification): run-23896345 PAUSED** (resumable). run-63d016f6 CANCELLED at 21:13 JST (46 min, major): its stack chose Hono but was given the Express pack because 'node' was found inside '@hono/node-server' and the record was rewritten to Express. Fixed in `12fef11`. run-c2e62179 (`notes-api-hono`, kimi-k3 frontier) started 21:21 JST on it: no pack fits, stack TypeScript/Hono, so the proven-setup path runs live for the first time. `read_docs` found nothing for `@hono/node-server` (no README in the npm record; hono's record is 6 MB); fixed in the commit after `12fef11` (READMEs from jsDelivr) and deployed mid-run. The owner reported the frontier serves 1M in / 300k out: its reply ceiling had been the default model's (read from the process environment). Fixed with a `JUDGEMENT_MAX_OUTPUT_TOKENS` setting ('Longest reply' under the frontier model) and the ceiling resolved from the model's own environment; deployed mid-run. The context budget (compaction, document budgets) still follows the default model's window - conservative, not wrong. 22:35 JST: on resume the run moved to the owner's new frontier `qwen3.8-flash` (`token-plan.maas.qwencloudapi.com`), which refused ToolStrategy's forced tool call in thinking mode (400) - the run FAILED. Fixed in the next commit (tool offered with `tool_choice: auto` for that server and model, reasoning kept; verified live that auto works there), deployed, and the run resumed. 22:44-23:24 JST: the setup stage `stack_setup_0` was skipped after its own approval pause (its package.json counted as a seeded codebase) - setup never proven for this run; fixed `2915a36`. The owner asked (a) whether the specification is enough for the local model - three gaps found and fixed in `f008ec4` - and (b) for a rewind to any stage - `d5e6465`. Both deployed 23:24 JST with the run resumed. The owner went to bed asking the loop to continue without stopping. 23:40 JST: QA could not launch the product - tsx's IPC pipe under TMPDIR=<workspace>/.agent-home was 112 chars (> 107 Unix socket limit), `listen EINVAL`. Fixed (short per-workspace TMPDIR under /tmp), deployed mid-run. Noted: `tests/test_sandbox_in_container.py::test_only_what_a_build_needs_is_passed` fails when run alone (passes in the full suite) - order-dependent, pre-existing. 00:50 JST: budgets follow settings and each model's window (deployed). 01:45-02:10 JST: sprint 1 on Ornith; the work order received its specification slice. Fixed: `#!` files are made executable (`3faf790`, no role may chmod); a suite's declared JUnit report is not locked with the suite (each run had been 'restored'). Both deployed mid-run ~02:20 JST. 04:02 JST: sprint 1 ACCEPTED (committed 766e7c2): parallel fixes ('Fixing 2 defects side by side') and parallel reviews ('Running 4 reviews side by side') both seen live. Rewind points grouped (79 -> 27) `9446812`. Sprint 2's lead was sent back 3 times (~12 min each) by a too-broad 'declined because untested' check; fixed `f3623eb` (handed to a work order or a later sprint is not a decline), deployed 05:01 JST. 05:27: runner configs with a qualifier (`vitest.unit.config.ts`) are config, not product code (testing work order refused 5x). ~07:00: escalation seen live - `specialist_testing_3` went to the judgement model after 2 restarts on Ornith. 07:35: sprint 2 acceptance 11 passed / 8 failed (sprint 1: 7/12). Runner reports are not 'claimed but never written' (deployed 09:13). Ornith loses ~2 replies to reasoning at the start of most visits (20k reply cap, medium effort) - the owner's setting, reported, not changed. 09:49: quoted paths unquoted (`e4aa4c4`). ~10:05: sprint 2 attempt 1 failed (dispute: no test unpassable) -> re-plan. Owner asked whether the spec is detailed enough: of 10 defects, 2 were the builder ignoring the spec, 2 spec design calls (`Number(id)` after `/^\d+$/`, `exec tsx` child process), 4 test-setup drift (setup never saw the spec; fixed `f008ec4`), 2 unbuilt. Gap found and fixed: fixers were given no spec extract (`1be28a8`, deployed 10:25 JST). ~10:40 JST: the owner judged 13 h for 1.5 sprints not competitive; fast delivery built (`e55dd6f`). run-c2e62179 PAUSED as the thorough baseline (13.3 h, 1,081 calls, 2.84 M output tokens) and notes-api-hono to restart on fast. 11:33 JST: run-dd3efe2a was started although `ready` said NOT ALL READY (a `| tail` swallowed the verdict) and cancelled within seconds; `loop.sh start` now refuses unless ALL READY. The owner's settings now name `qwen3.8-flash-next-coder-iq1_m` on :9090 as the build model, which answers 403 to the saved key - waiting for the owner. 11:50-12:05 JST: the owner's Strata server (:9090) refuses Host host.docker.internal (DNS-rebinding guard); the owner chose a harness fix - requests name the server as the owner does, and localhost/127.0.0.1 settings are reached via host.docker.internal from a container (`reached_from_here`). ALL READY at 12:00; run-d3b2b40c started but on THOROUGH: the stored delivery_mode was 'thorough', saved 11:47 by a settings page loaded before the field existed (payload default) - cancelled, fixed `61d8205`. Waiting for the owner to choose Fast on the settings page. 12:27 JST: run-a560d2f9 (notes-api-hono, FAST) started. 12:49 JST: the framework-instructions call (`plugins/middleware._extraction_model`) built its own client from the setting as written - `http://localhost:9090/v1` reached the container itself, so the stack's instructions were absent for the run. Cancelled at 13:00 JST (33 min, inside the 40-minute window); fixed by reaching it through `reached_from_here` like every other client; restarted on the fix. Seen in that run: the frontier (qwen3.8-flash) takes ~2 min per thinking call, so tools_models took 15 min; `read_docs` refuses `node:test` (a `node:` built-in is not a package name). 13:05 JST: run-92027c2a (notes-api-hono, FAST) started on `c85602d`. `read_docs` now answers a runtime built-in (`node:test`, `bun:test`) from the runtime's documentation, or says it is built in (pushed). 13:25 JST: run-92027c2a's tools_models sent its answer's `technology_stack` as a JSON string six times running (~12k output tokens, 2.5 min each); CANCELLED 13:27 (22 min). Fixed in `app.models.tool_arguments`: a tool call's argument the tool's schema wants as an object or list, sent as a string of JSON that parses to it, is decoded in `CompatibleChatOpenAI._generate`. Restarted on the fix. 13:36 JST: run-46c9bd90 (notes-api-hono, FAST) started on `9fdd0eb`; both fixes seen live (tools_models answered first time; 'Framework instructions resolved ... hono'). `look_up_package` now reads `typescript@5` / `fastapi==0.115` as the package (deployed mid-run). Seen live: `typescript@5` answered 7.0.2 without saying it is not a 5.x; the answer now says so (next commit; held from the live run until the specification stage ends, since a deploy restarts a stage from its start). 14:49 JST: the specification (after ~50 min of research, one 37.8k-token reply lost to reasoning) sent eleven list fields as paragraphs of prose - 20 validation errors, the whole answer to write again. `tool_arguments` now reads prose where a list of strings is wanted one item per line (`dc2777a`). 14:59 JST: the retry's 40k-token answer was also lost and the stage started over - not reasoning: both lost replies ended `finish_reason: tool_calls` with ~21k tokens of call whose arguments were not strict JSON, so the client filed them as invalid calls nobody reads. Fixed: `tool_arguments` reads an invalid call to a known tool leniently (raw line breaks in strings, unclosed brackets) and makes it a call again, logging 'read leniently'. Deployed 15:07 JST with `4a34aea` and `dc2777a`; the stage restarted (5 min lost). 15:23 and 15:33 JST: two more ~37k-token specification replies ended `tool_calls` with ~15k tokens after reasoning and NO call and NO invalid call recorded, and no 'read leniently' log - the call is lost before the invalid list. Diagnostics added: the transcript keeps invalid calls whole; an unreadable one logs where it fails; `with_every_call_the_server_sent` compares the server's raw tool calls with the parsed message and files any dropped one as invalid ('kept nowhere' warning), so the lenient reader gets it. The stage reached attempt 3 of 3 at 15:33; deployed 15:41 JST. 15:57 JST: the cause shown - the answer call's arguments STOP mid-object (`...}]\n\n, "file_plan": ` at 35,184 characters) with the reply marked finished; and `function_contracts` came as objects where the schema wants lines. Fixed: `tool_arguments.what_arrived_whole` keeps the whole fields of a cut-off answer per (run, stage, tool), the answer is refused with `cut_off_notice` (kept fields, fields still to send), and the next call is joined to what was kept; an object where a line is wanted is rendered `key: value; ...`. The owner asked why research is slow and approved: carry research across restarts, a research budget per stage visit, batched package lookups. Built in `app.tools.research`: 8 documentation reads and 12 package lookups per stage visit (past that the stage is told to write from what it has), `look_up_package` takes several comma-separated names, and what was found is in `carry_over_note` for a fresh attempt. 16:07 JST: another answer cut off (106,740 characters); deployed 16:15 JST; the run had FAILED at ~16:12 (attempts spent) and was resumed through the API at 16:19. 16:32 JST: cut off in `implementation_order` at 63,199 characters, 15 fields kept; 16:40 the rest arrived and was joined - the specification was ACCEPTED and the run moved to architecture_review. Specification stage total ~3 h (mostly lost answers). 16:52 JST: architecture review sent it back; the revision began reading its own 60k-character specification out of `conversation_history/` to write all of it again. Fixed: a revision after review sends only the sections it changes and every list section it leaves out is kept from the previous one (`_with_the_sections_it_dropped`, now all list sections and review revisions too). Deployed 17:05 JST; the revision then sent only its changed sections and the spec passed review 2 (17:40). 18:16 JST: PAUSED for the owner to change the local model; build model now `google/gemma-4-26b-a4b-qat` (LM Studio, host.docker.internal:1234), ALL READY, resumed ~18:20. Measured: frontier qwen3.8-flash ~60 tok/s, 120 of its 143 pre-build calls were gathering (77 min). Owner asked for the frontier only where its reasoning is needed - built (`app.agents.gathering`, fast planning on the build model, one revision/send-back each; HANDOVER §2.0x) and deployed 18:37 JST while the run was in acceptance_author_0. Seen live: acceptance tests on Gemma (calls 5-30 s), review gathered in 4 turns on Gemma then written by the frontier; suite locked 19:04 (10 tests, 27 min vs 1 h 55 baseline); sprint plan folded to 1 sprint. 19:19 JST: the technical lead (now Gemma) was sent back 3 times for the spec's planned test files the scope names (boot-failure/concurrency/contract .test.ts), returning the same plan each time, then started over. Fixed: `with_named_tests_given_to_testing` gives such files to the testing work order at the specification's planned path before the readiness check. Deployed 19:34 JST; it fired, but the dispatch then chose an earlier 'better' plan that never had them assigned - fixed in the next commit (pushed, held from the live run to avoid restarting the code review). 19:38 JST: 'Drafted 7 of 7 work order(s) from the specification (7 of 7 files)' in ~75 s - fast drafting live for the first time; code_review_0_0 (frontier, gathering on Gemma) followed. 20:00-20:38 JST: the locked suite timed out (exit 124, `start()` resolved before the socket bound); test_round_0 ran on the frontier (no result to read) for ~38 min and found it. 20:39 JST: fixes on Gemma (reasoning off) struggled - malformed argv `["npm\", \"run\", \"build\"],category:"]` refused repeatedly, wrong edit argument names, a fix claimed without a proving command. Fixed: a string list sent as one string holding its own text is split back (`tool_arguments._the_list_it_held`). Deployed 20:57 JST. 21:15 JST: Gemma fixes without reasoning broke 62 passing tests in one fix (reverted) and claimed edits never made; fixes now reason as configured (`_the_build_model(..., reasons=True)`), drafting stays reasoning-off; deployed 21:20 JST. 21:57: AC-1/2/7/8/9/11/12 passed once (defects closed as already fixed), then the build broke again. 22:15 JST: found that the proven setup's kept `tsconfig.json` has `"lib": "ES2023"` (TS5024) - its smoke tests ran `node --test` without compiling, so it was never exercised, and fixers were refused it as 'already works'. Fixed: `contract.released_because_it_fails` releases a proven setup's kept file the latest runs report an error in (stack packs' own files stay kept). Deployed ~22:25 JST. Root cause fixed next (pushed, not deployed - only a new setup uses it): a setup declares an optional `build` command and the proof runs it after the install, before the smoke tests (`custom_setup.prove`). 22:44 JST: 7/10 tests, 14/18 criteria pass (AC-6/14/15/17 open). 22:58: `tsconfig.json` released live and fixed. 23:21: Gemma wraps a call's arguments - `run_terminal_command {"args": {...}}` - fixed: `tool_arguments._unwrapped`; deployed 23:26 JST. 23:30 JST the owner asked: everything the harness can do, the harness does. Plan (HANDOVER §2.0y): 1 fixes by rewriting (`app.graph.rewritten_fixes` - the harness gathers the defect's files and failure output, one call per file, compiler diagnostics fed back, agent loop fallback); 2 compile-and-repair after drafting (`drafting._repaired_where_the_compiler_says`); 3 a suite with no answer run file by file (`app.acceptance.per_file`, sandbox category `probe` 60 s); 4 harness sprint plan and work orders; 5 specification in parallel parts; 6 no model code review in fast. 1-3 deployed 23:49 JST. 4 (work orders from the specification, `app.graph.planned_work`; the sprint plan stays the scrum master's for now) and 6 (`engineering.code_review` returns at once in fast) deployed ~00:10 JST 2026-10-15. 5 (specification in parallel parts) designed with the research, not built yet. 2026-10-15 ~00:50 JST, owner: memory of documents too, kept current, plus the 4 next steps - built: `app.agents.project_memory` (every role agent: docs then product files, budget 30% of the model's window, mtime+size checked on every use, a read of a held unchanged file answered with a pointer; also in rewrite fixes); candidate fixes (`rewritten_fixes.fix_by_candidates`, 3 at once on the judgement model after a failed fix, kept by the defect's own tests via `per_file.each_file(naming=...)`); `repository._refuse_if_it_adds_errors` (fast; new same-file language-service errors refuse a product write; drafting and rewrites redraft with them); `app.graph.specification_parts` (architect writes CORE, 3 parts at once). Deployed 00:15 JST. 00:17: run-46c9bd90's suite passed 10/10 (all 18 criteria). ~00:50 JST: delivery mode made per run (HANDOVER §2.0x) and the quality-neutral optimisations on in both modes; deployed ~01:00 JST. `loop.sh start` with `DELIVERY=thorough` starts a thorough run. NOTE: `.gitignore` ignores `fix_*.py` - a module named that way is never committed. Idea queued: when the suite times out, the harness times each acceptance file itself instead of a frontier round. 00:47 JST 2026-10-15: run-46c9bd90 on sprint 2 (1 of 2 work orders drafted); `specialist_testing_1`, escalated to the judgement model, made its first 12 turns - writes and test runs - on Gemma through the gathering middleware. Fixed: only read-only calls (`gathering.GATHERING_TOOLS`) are gathering; deployed mid-run (seen live: 'Gathered in 1 turn(s)'). 01:33 JST: sprint 1 was planned again - three harness test rounds each raised 'The unit tests fail. The runner's output ends: (no output)': the unit command writes JUnit to a file and prints nothing, so the fixers guessed. Fixed: `_run_unit_tests_procedurally` clears and reads the unit reports (the pack's, and any .xml the command names) and appends each failing test and its message; an exception says why instead of an empty failure. Deployed mid-run. 01:36 JST: on the sprint's re-plan the harness made its plan from the specification again - every planned file, plus the kept `package.json`/`package-lock.json`/`tsconfig.json` (sent back 3 times, then dispatched) - and drafting rewrote the built product whole (src/*.ts, README, tests; uncommitted over 605b8dc, left to the run's own tests). Fixed in `app.graph.planned_work`: files the harness keeps are left out, and once half the planned files exist the product is built and the lead plans the change (`BUILT_SHARE`). Deployed 01:47 JST; on resume the plan already dispatched redrafted 20 of 21 files (19 min, frontier: the re-planned sprint is escalated). 02:42 JST: `specialist_testing_3` on the frontier, 40 min, ~2-3 min a turn, half its turns reads. Fixed: after the judgement model's first turn the build model is offered each next turn again (`gathering.MOST_IN_A_ROW` 3, `MOST_BUILD_TURNS` 30); pushed, deployed at the next stage boundary (02:50 JST). 03:09 JST: the unit defect now carries its failing tests (README.md lacks a PORT default, etc.), but the rewrite fix rewrote `src/index.ts` - `files_to_fix` took only `file:line` locations (the stack). Fixed: a file the failure names plainly that exists is taken too, in the order named (`rewritten_fixes._A_FILE_NAMED`). Deployed 03:34 JST. 03:46 JST: the sprint planned a fourth time - round 2 again 'unit tests fail ... (no output)' while all 109 unit tests passed (`fail 0`). Root cause of every such round: the sandbox runner answers `returncode` as TEXT ('0') and `_run_unit_tests_procedurally` compared it with 0. Fixed with `scaffold._exit_code`; deployed at once. Seen after: 'unit tests pass', test_round_1 skipped the model round, security and advice reviews, milestone review asked for one missing test (PUT unknown id + invalid title is 404). 05:37 JST: run FAILED in technical_lead - the checkpoint write of the lead's answer raised 'Type is not msgpack serializable: AIMessage' (reproduced only by an integer outside 64 bits; none in the transcript's args, so likely in the message's metadata). Fixed: `checkpointing._StorableSerializer` stores such integers as text inside the message and logs where; any other unstorable write logs its unusual values before raising. Deployed and the run resumed through the API (05:53 JST); not seen again. 06:26 JST: a gathering turn on Gemma ran to 20,000 tokens (7 min) with no call. Fixed: gathering replies are held to `gathering.MOST_GATHERING_TOKENS` (2,000) and a cut-off one (`finish_reason: length`) is the judgement model's turn. Deployed 07:10 JST. 07:40: AC-24 fixed, test_round_3 all pass. 08:16: milestone review 2 sent it back again (concurrent DELETE answers 204 twice; `process.exit(1)` inside `start()`; minors) - revision 2 of `MAX_MILESTONE_REVISIONS` 3; at 3 the run escalates to a person even with every test passing (open question for the owner: in fast, carry the findings forward as recorded risks instead). 08:34: the lead (Gemma) left `selected_sprint_goal` out of every answer - refused 8 times in 12 min. Fixed: the field is optional and the node fills it with the sprint's own goal. Deployed at once (08:41 JST); plan dispatched. ~09:00 JST, owner answered yes: in fast, a milestone review still asking for changes at the limit records its findings as risks and goes on (HANDOVER §2.0x); deployed at the next stage boundary (09:23 JST). **09:58 JST: run-46c9bd90 COMPLETED and released** - review 3 accepted; the brief check then raised a false 'must fix' for `search`/`filter` from tools_and_models' 'Replacement criteria: ... or search/filter/pagination enters scope. None of these is in the current acceptance criteria' and the escalation auto-accepted it as a known issue (DR-6). Fixed: `integration_checks._NOT_A_REQUIREMENT` skips replacement-criteria and out-of-scope lines. Score: 9/9 hidden tests (1.0), locked suite 10/10. Wall 1,222 min (20.4 h, inflated by ~12 bugs fixed live and 23 restarts), 1,277 model calls, 2.80 M output tokens (65% reasoning); defect_fix 225 model-min, specialists 190, architect 157, lead 122. Next: a fresh fast notes-api-hono run on everything deployed. **10:04 JST: run-72d4c9ee (notes-api-hono, FAST) started**; at 10:14 already in principal_architect (intake to consultations in 10 min). 10:25: the build model began the answer before nearly every judgement turn (cut at 2,000 tokens, ~25 s each). Fixed: after `gathering.MOST_MISSES` (2) non-gathering attempts in a row the judgement model takes the rest of the visit. Deployed mid-run (seen live 10:41). ~10:45 JST, owner: a per-run 'Use the frontier model' choice (off = every stage on the local model) - built; and the pages use the whole window (shell uncapped, start form and Settings in two columns, wider run-page rails on large screens). The UI now type-checks and builds on the host (`cd langchain-ui && npm ci && npm run build`). The owner started a separate run (low brief, local model) at ~10:50 JST - NOT to be monitored; deploys still restart its current stage. 11:02 JST: run-72d4c9ee's architect asked for documentation 8 more times after its share was spent. Fixed: `research.build_research_share_middleware` stops offering `read_docs`/`look_up_package` once the share is used; deployed at the specification's end (a cut-off answer's kept fields are in process memory). ~11:25 JST the owner asked to look at their run (run-e3a83a33, low brief, FAST, local model only - `lfm2.5-24b-a2b`, which the owner's settings now name as the build model for every run): its architect sent list sections as one JSON object in a string, and a list cut off mid-entry - every answer refused (attempt 3 of 3). Fixed in `tool_arguments`: an object where a list is wanted becomes its list (one key holding a list) or one line per key; a cut-off list string is closed and its unfinished last entry dropped. Also: with no frontier model the specification parts were handed `None` (`'NoneType' object has no attribute 'invoke'`) - they now build the default model; a part that comes back short logs why. run-72d4c9ee: two of three parts came back empty (unlogged), so the architect was sent back for those sections - 1.2 h without a specification. All deployed ~11:35 JST. 11:50 JST: the owner's run's architect (LFM) still took itself to be writing the product - its request carried the code-writing stages' 'Run `ls` FIRST ... write into that exact directory'. Fixed: planning stages (architect, scrum master, lead) get `project_layout.PLANNED_PROJECT_DIRECTORY` (where the product lives, every planned path inside it, writes no file). Deployed ~12:00 JST. The owner paused their run at 11:55. 12:00, owner: why 2 h and no development - 113 min wall, ~100 in the architect (71 model-min, 217k output tokens, 63% reasoning; the answer cut off twice; two parts empty so it was sent back and researched again; 4 of my deploys restarted the stage, ~33 min). Owner: read on the local model, the frontier only writes. Built `app.agents.research_brief` (see HANDOVER); pushed, deployed at run-72d4c9ee's next stage boundary (12:27 JST, specification done after 2 h 23 min). 12:52: review sent it back; the revision's research found 1 of 7 libraries - `Hono`/`Playwright`/`TypeScript` asked as written. Fixed: `package_registry.look_up` retries a missed capitalised name in lowercase (deployed 13:09). 13:33 JST: specification accepted after one revision (2 h 50 min after start); stack_setup_0 (build model) wrote the product's own files (types/validation/store/app/server + unit tests) despite 'Build nothing of the product itself' - ~7 min, drafting rewrites them. Candidate fix (not built): cap the application files a setup stage may write (a generator-less stack may need one entry point for the acceptance smoke test, so not a blanket refusal). 13:52: the setup was not proven - its `stack-setup.json` wrote commands as one string, paths under `notes-api/`, globs in kept_files (plus `install: ["tsc","npm"]` and an empty unit report, which only the model can fix). Fixed in `custom_setup.read_declaration`: a command as one string is split (shlex), a list of strings with spaces is one command each, a leading project-directory name is taken off, a pattern in kept_files is dropped. Deployed ~14:00 JST during stack_setup_1. 14:20: setup 2 still not proven - each test command wrapped as a list of one command (`[["node","--test",...]]`); left to the agents, the run went on to acceptance_author_0. Fixed: one command wrapped in a list is unwrapped. 16:03 JST: run-72d4c9ee in acceptance_author_2 for ~90 min, 116 failed calls (33%) on LFM: 53 shell command lines (`cd /workspace/x && cmd 2>&1 | head -80`), 25 writes to `/workspace/notes-api/...`. Fixed in `workspace_paths.rewrite_tool_arguments`: `as_a_command` (cd DIR && -> working_directory; 2>&1, | head/tail -N dropped; any other shell construct left to be refused) and `without_an_invented_root_for_a_new_file` (a write path's invented first segment taken off when its directory exists). The owner's run-30f805ca (THOROUGH, local only, LFM): 56 of 75 min in the architect - 87% reasoning at ~48 tok/s; it announces the answer and calls glob instead (~20 min); LM Studio 'Context size has been exceeded' at ~54k tokens though Settings say 131k (owner to check). Deployed ~16:13 JST. ~16:30, two more: (1) `settled_answer._nothing_new_lately` - when the last 5 tool results from at least two different tools all gave nothing new (repeat refusals, same bytes, same listing), the tools are withheld and the answer is the only move (one tool repeating stays the repeat rung's); (2) owner asked whether project memory helped: in run-46c9bd90 reads per model call fell 0.34 -> 0.19 after it (baseline thorough 0.76), but the average request grew 44k -> 95k tokens; the 'answer a held read with a pointer' never fired (0 in every run) because the path middleware adds a default `limit` - fixed. Memory itself is rebuilt from disk on every call, so it is whole after a pause/resume; in-process stage memory (research ledger and findings, cut-off answer fields, gathering counts) is not - a resumed stage starts those afresh; `architect_research` is in the graph state and survives.
  - **`6314d91`:** fixes from the review of the 35 commits since `9c41cba`:
    - no guessed contracts (two of three medium runs had been given a wrong pack's runner files);
    - honest batching, and unknown is not passed;
    - suite checks moved into the packs and their false positives fixed;
    - reviews for code in any language;
    - the real 12-hour limit.
  - **New packs:** `browser-vue`, `fullstack-{react,vue}-{express,fastapi}`, all scaffolded with smoke tests passing.
  - **Playwright pinned to 1.64.0** in the packs, the image and the scorer; the image had installed the newest release on every deploy, so packs pinned to 1.63 found no browser, and three of four web-todo runs' scaffolds were left to the agents.
  - **Before this:** **stage 1 (web-todo): 2 of 2 clean runs (STAGE 1 GATE PASSED!).** Next: Stage 2 (`notes-api`, `wordstats-cli`, `textkit-lib`: 1 clean run each); active run on `tests/brief_medium.md`. Latest: run-fd3a244d-4cd5-41c2-897a-0c326bc2598d (17:16-23:17 JST, 2026-10-11) FAILED at 361 min (exactly 6h / 21,600s) on `tests/brief_medium.md` due to Celery soft time limit (`SoftTimeLimitExceeded`) firing during Sprint 2 test round 2 while healthy progress was being made (7.5% failure rate, 0 duplicate calls, 1,031 tool calls, 1,064 LOC generated). Unhandled exceptions in `execute_workflow_run` were recorded with raw class strings instead of using `_explain_failure`. Fix: 1) Raised default `CELERY_TASK_SOFT_TIME_LIMIT` to 43,200s (12h) and `CELERY_TASK_TIME_LIMIT` to 43,500s across `tasks.py`, `docker-compose.yml`, and `.env.example`; 2) Formatted unhandled worker task exceptions through `_explain_failure` in `execute_workflow_run`; 3) Added regression test `tests/test_progress_and_tasks.py:test_unhandled_exception_marks_run_failed_with_explained_message`. Before: run-fdc1385c-e858-4caf-922a-c75534fb2907 (12:59-16:45 JST, 2026-10-11) FAILED at 226 min on `tests/brief_medium.md` in test_and_triage_node (`test_round_0`): agent exhausted its call budget without producing structured response, and exhausted structured retries; `workflow.py` did not include `test_round_` in `_STAGES_THAT_MAY_RETURN_BLOCKED`, raising `ValueError`. Fix: added `test_round_` to `_STAGES_THAT_MAY_RETURN_BLOCKED` and added `_blocked_when_retries_exhausted` so test_and_triage proceeds with procedural checks/defects rather than failing the run. Regression test in `tests/test_run_recovery.py`. Before: run-5aadbddd-7e10-4790-8611-6f3289b015f2 (06:14-07:34 JST, 2026-10-11) COMPLETED cleanly in 80m, score 10/10 (1.0), locked suite 10 passed / 0 failed (100%), 81 unit tests pass, 482 LOC (well within 500 budget cap). No harness fixes during run, product audit clean, working tree clean. Clean run 2 of 2. Before: run-49dec2db-57e8-4600-b003-807ad7760511 (00:42-06:08 JST, 2026-10-11) COMPLETED cleanly, score 10/10 (1.0), locked suite 16 passed / 0 failed (100%), 54 unit tests pass, 426 LOC (well within 500 budget cap). No harness fixes during run, product audit passed, working tree clean. Clean run 1 of 2. Before: run-0d60b2d6-4ecd-406d-baef-23f552e1f6a8 (18:58-22:54 JST, 2026-10-10) score 10/10 (1.0), locked suite 17 passed / 0 failed (100%), 95 unit tests pass. 524 LOC (exceeded 500 budget cap by 24 lines). FAILED at 234 min in technical_lead milestone revision 3: Call 1 spent 25,000 output tokens reasoning in <think> tags (finish_reason: length, content ""). Call 2 (thinking off) produced 93,578 chars of text until finish_reason: length. _nudge_for_the_structured_response returned None; _run_gated_agent did not update result, leaving it pointing to Call 1. out_of_room evaluated to True, bypassing fresh conversation restart and raising ValueError on attempt 1. Also technical_lead._SYSTEM_PROMPT had contradictory write_artifact instructions with can_write=False. Fixes: 1) _nudge_for_the_structured_response preserves invoke result via out_result and updates result in _run_gated_agent so that text-producing nudges are retried on a fresh conversation; 2) removed contradictory write_artifact prompt rules from technical_lead; 3) regression test tests/test_nudge_preserves_reply_for_restart.py (proven failing on old code, 3/3 passed). Gate count resets to 0 of 2. Before: run-d96ae4c7-44f0-4691-b12a-e3613918acda (12:15-17:32 JST, 2026-10-10) COMPLETED, score 10/10 (1.0). Product audit clean (323 LOC under 500 budget cap, 47 unit tests pass, git working tree completely clean). Not clean: locked acceptance suite had `locator('button', { name: 'Edit' })` and `locator('button', { name: 'Delete' })` asserting `toHaveCount(1)`. In Playwright, `locator()` ignores the `name` option, matching all buttons (`locator('button')`), which had count 2 in Sprint 2 where both Edit and Delete buttons exist. The locked suite held tests failing on `expected: 1, received: 2`, trapping specialists in 102 minutes of defect remediation until auto-escalation deferred criteria. Fix: added `locators_with_invalid_name_option` in `src/app/acceptance/suite.py`, checked in `acceptance_review_node` and `acceptance_for_round` in `src/app/graph/acceptance_nodes.py`, updated `PLAYWRIGHT_LOCATORS_RULE` in `src/app/stacks/packs/_javascript.py`. Regression test `tests/test_locators_with_invalid_name_option.py` (proven failing on old code, 3/3 passed, zero banned words, zero run IDs). Clean gate count resets to 0 of 2. Before: run-1c696369-dc64-4892-bab5-3b3b1e98ea2a (21:39-22:14 JST, 2026-10-09) CANCELLED at 35m in sprint 2 (early stop rule). Sprint 1 passed in <20 min with dynamic 2-sprint cap and batch defect remediation verified. Deadlock in sprint 2: QA omitted tags for `[AC-9]`, `[AC-10]`, `[AC-11]`, `[AC-13]` in `app.spec.js` (even though test code checked the elements). These were reported as `status: untested`. `_failing_due` treated `untested` as defects and handed them to product fixers. Product tests passed (18/18 unit, 11/11 acceptance), but developers cannot edit the locked suite. When attempt 1 failed, `_the_locked_tests_still_failing` checked only `outcome == "failed"`, skipping criteria with 0 tests. Thus `_a_dispute_is_due` returned `False`, dispute never reopened the suite, and attempt 2 repeated the identical failure. Fix: 1) `src/app/acceptance/requests.py`: prompt rule requiring bracketed IDs for all criteria, including multi-criteria test titles (`[AC-2][AC-9]`); 2) `src/app/acceptance/suite.py`: `gaps` feedback directs adding `[{c.id}]` to an existing test title if already tested; 3) `src/app/graph/workflow.py`: `_the_locked_tests_still_failing` includes untested due criteria so dispute triggers, and `acceptance_dispute_node` reopens the suite to repair missing tests; 4) `src/app/agents/suite_dispute.py`: `tests_it_names` matches criterion tags. Added regression tests `tests/test_untested_criteria_dispute.py` (banned-word checks passing). Full suite: 9,759 passed, 3 S3 failed. Clean count resets to 0 of 2. Before: run-e9e4ecbf-f67f-43f7-82ff-392eb713ce1c (20:05-21:26 JST, 2026-10-09) FAILED at 1h21m in sprint 1 entering security_review_node with `NameError: name 'Path' is not defined` (`src/app/graph/workflow.py:7521`) when filtering non-empty changed_files. Cause: `Path` was not imported in `security_review_node` or at module level (only `PurePosixPath` was imported). In unit tests with empty changed_files, list comprehension never evaluated `Path(f)`. Once real changed files arrived, it threw `NameError`. Fix: imported `Path` at module top and inside `security_review_node` in `src/app/graph/workflow.py`; added `tests/test_security_review_imports.py` (verified to fail on old code, passes on new code). Clean gate count resets to 0 of 2. Before: run-38352564-85bb-408d-ac10-c31756a9a51d (18:59-19:42 JST, 2026-10-09) CANCELLED at 43m in sprint 1 due to two fatal issues: 1) transient scaffold acceptance smoke test failure left .harness/stack-pack.json unwritten; when missing, contract.the_pack returned None, disabling all stack pack lints and kept-file protections; 2) QA authored acceptance test helper resetPage: `await page.evaluate(() => localStorage.clear()); await page.goto('/');`. On Playwright's initial about:blank document, accessing storage throws `SecurityError: Failed to read the 'localStorage' property from 'Window': Access is denied for this document.`, failing 8 tests on line 5 before opening the app. Fixes: 1) Fallback pack inference in contract.the_pack (src/app/stacks/contract.py): infers pack and project from .harness/decisions.json or docs/technology_stack.md and self-heals by persisting CONTRACT_FILE; 2) Added storage_before_page_open in src/app/stacks/packs/_javascript.py and tests_that_access_storage_before_opening_the_page in src/app/acceptance/suite.py and src/app/graph/acceptance_nodes.py: rejects storage calls preceding page.goto. Updated PLAYWRIGHT_LOCATORS_RULE (zero banned words). Clean gate count resets to 0 of 2. Before: run-9af1e8ed-4d46-443c-945c-c25ae93d5ec5 (17:54-18:43 JST, 2026-10-09) FAILED at 49m in sprint 1 (attempt 2 defect remediation). Root cause: batch defect remediation bundled a co-defect that required a regression test with a primary defect that did not require one, and called `mark_defect_fixed` with `regression_test=""`, raising an uncaught `ValueError`. Fix: `_bundle_co_defects` only bundles open defects with matching `regression_test_required` status, and `_apply_batch_co_defect_fixes` leaves co-defects requiring regression tests open instead of raising when no regression test is provided. Clean gate count resets to 0 of 2. Before: run-61290727-a45a-4633-a75e-0681f13d4cc8 (16:20-17:42 JST, 2026-10-09) CANCELLED at 1h22m in sprint 1 (attempt 3 defect fix loop). Root cause: QA authored 14 acceptance tests calling `getByRole('textarea', ...)`. In W3C ARIA specifications, `<textarea>` has role `textbox`; `textarea` is an HTML tag, not an ARIA role. Playwright strictly matches valid ARIA roles, so `getByRole('textarea')` can never match any element in any browser. Navigation failure before build hid this from pre-lock review. Fix: added HTML tags mistakenly used as roles (`textarea`, `input`, `select`, `dropdown`, `field`) to `LOCATORS_THAT_DO_NOT_EXIST` and updated `PLAYWRIGHT_LOCATORS_RULE`. Clean count resets to 0 of 2. Before: run-66699bc2-1787-4765-a326-ddec1b29c4bb (13:02-15:53 JST, 2026-10-09) CANCELLED at 2h51m in sprint 1 (attempt 3 defect fix loop). Root cause: QA authored `page.getByLabelText` (Testing Library method, not in Playwright). Before the product was built, tests failed on navigation (`ERR_CONNECTION_REFUSED`), hiding `page.getByLabelText is not a function` from the initial suite run, so the suite was locked. Once built, the locked tests could never pass and developers could not edit the locked suite, looping defect fixes. Fix: added `locators_that_do_not_exist` and `PLAYWRIGHT_LOCATORS_RULE` to stack packs, checked and rejected before locking in `acceptance_review`, and included in `acceptance_for_round` broken tests. Clean count resets to 0 of 2. Before: run-4eb14786-2602-4b8d-824f-d5b223024573 (08:56-12:26 JST, 2026-10-09) COMPLETED, score 10/10 (1.0), locked suite 16 passed / 0 failed, product audit clean (484 LOC under 500 budget cap, 21 unit tests pass, git working tree completely clean, release evidence and decisions committed). Before: run-5a07ea78 started 20:38 JST. Before: run-9751a7e1 started 20:09 JST, cancelled 20:30 in code_review_0_0 (model looped 14 identical `read_file` calls for a file it already had, failing to course-correct from the refusal; `f5411a1`). At 14:12 JST (2026-10-08) the owner set the model to `openai/gpt-oss-20b` (thinking effort medium, parallel); `loop.sh ready` said ALL READY at 14:14. No run started: the owner moved the loop to a different agent, whose first step is `loop.sh bench web-todo` (`docs/HANDOVER.md` §0). run-d211dc86 (14:10) was cancelled within seconds - started while LM Studio served gpt-oss and the settings still named qwen, because `loop.sh ready` exited 0 when not ready (`344b4a9`: it exits 1). `bc8e360` deployed 14:09 (one cause one defect; review findings need evidence; unstated orders checked before the lock). Latest: run-7b219f82 (07:47-13:57 JST, `97d9dd1`) cancelled by the owner in sprint 2's second revision; its first plan passed the scope check and sprint 1's builders stayed in scope; not clean - sprint 1's first fix stage, sent a code-review defect about the unit test command, ran the whole suite and began building later sprints' features: fix stages were never told what later sprints build (`d833edb`, deployed mid-run 08:55). Sprint 1's first attempt then failed over a code-review finding two fixers left without a regression test (the per-fix regression-test policy is the owner's decision); its re-plan was sent back twice for `style.css`, the specification's spelling of the project's `styles.css` (`8da1e0d`, deployed mid-run 09:38). Sprint 1 then passed on its second attempt. In sprint 2 the locked delete test wanted new items last and the locked list test wanted them first; two fixes were reverted for breaking the list test, and the dispute would have waited for the attempt to fail (`60971c5`, deployed mid-run 11:16). It fired on the next revert: the QA lead named the test and QA repaired it within the attempt. Sprint 2's attempt then failed over "the suite does not pass" - this project's `npm test` also runs the acceptance suite, which before the last sprint always fails on later sprints' tests, though every sprint-2 criterion passed (`351d1ec`, deployed mid-run 12:20). Its scaffold had been "left to the agents" after one failed acceptance smoke test (the run started a minute after a deploy), so no contract kept or restored the pack's files; a sprint 2 tester's edit_artifact added `grepInvert` for sprint 3's criteria to playwright.config.js, QA's three attempts to remove it were refused as outside the suite, and AC-5/12/15/16 were judged beyond repair (`1dde0ed`, smoke test retried once; to deploy after the run). A residual gap: a scaffold that fails twice still leaves its files unkept, with comments that say the harness keeps them. Latest: run-0e484d19 (00:17-07:44 JST, 2026-10-08, `6ff499e`) COMPLETED, hidden tests 10/10, locked suite 25/0, 407 code lines, 106 unit tests green, product audit clean (repository committed, nothing stray); NOT clean - seven harness fixes deployed during it, below; the plan check sent its first plan back (sprint 1's scope built completion, editing, deletion and filtering) and sprint 1's builders then built only sprint 1; not clean - two locked tests tagged with sprint 1's AC-7 drove sprint 2's "Done" and "Delete", so sprint 1's fix stage built completion and deletion (`c3a5fca`), and a duplicate defect answered `blockers: ["None"]` was logged left open (`f3d2409`); both deployed mid-run 01:48, resumed 01:50; sprints 1 and 2 accepted at their first review; sprint 3's first attempt failed over a regression defect a fixer had already resolved - the next two fixers changed nothing and answered "None. All sprint-2 tests pass." / "None - does not reproduce", read as blockers, and no check closes a regression defect by its test (`9cc524a`, deployed mid-run 03:34, resumed 03:35). Sprints 3 (second attempt) accepted; sprint 4's work order said to match the specification and its UI specialist wrote back all three colours sprint 1 had darkened for contrast - seven defects in one round, the second time in the run a later sprint undid a fix (`fa8da1a`: builders and the lead now hear the earlier fixes, over the specification; deployed mid-run 04:56, resumed 04:57). Then sprint 4's locked responsive test proved to have a logic error (switches to Active and expects no items though its item is active); every fixer in two rounds, three of them on defects already fixed, named it and left its defect open, and the dispute waited for the attempt to fail (`4bdf05c`, deployed mid-run about 05:55). A page-check contrast defect, already fixed, went to a fixer in two rounds - nothing closed a page-check defect by measurement (`cc875e7`, deployed mid-run 06:21, resumed 06:23). The QA lead's dispute then reopened the suite and QA repaired the responsive test; sprint 4's second attempt had no defects. A fixer that changed the stylesheet and named the test bug only among its decisions slipped past `4bdf05c` (`548a63d`). Its final reviews asked for the contrast fixes to be undone to match the specification (`97d9dd1`). Both deployed 07:46, between runs. Gap seen: the plan check's action table has no persistence, so sprint 1 still built storage early (minor). Latest: run-379e32c0 (23:24-00:06 JST, `3b01d8a`) cancelled at sprint 1's builders - the scope record, the builders' later-sprints section, the listing labels and the snapshot all held, but the sprint plan's own sprint 1 scope listed sprint 2's edit, delete and filter work (and sprint 2's listed it again), the lead copied it into the work orders and the backend specialist built it; the plan is now checked and asked for once more, and the lead hears what later sprints deliver (`6ff499e`). Before it: run-d43cb02c (21:00-23:14 JST, `0054496`) cancelled in sprint 1's revision - sprint 1's builders built every sprint's features (their first write held edit, delete, completion and filters, which the plan deferred to sprint 2), spent 30 minutes and a restart on later sprints' failing tests, and the milestone review then found the product 84 lines over the brief's limit and had the revision delete that work again for sprint 2 to rebuild: builders were never told which locked tests are a later sprint's (`3b01d8a`). Earlier in it, not clean - at 22:10 the rewrite guard refused its backend specialist a rewrite that dropped a `wrapper` it had added itself (4 of the guard's 8 refusals in all stored runs were on files only the refused stage had written); it spent its last calls on line edits and was restarted (`46be22f`, deployed mid-run about 22:33). Before it: run-041ae93b (20:32) cancelled at 20:57 - a generated Playwright note told QA to install browsers the harness had installed (`0054496`). Latest: run-1a89a0d8 (14:25-20:12 JST) FAILED in sprint 2's second attempt - a fix stage lost its reply to the output limit and then the reply after it, and the run raised (`38ef971`); hidden tests 10/10 on what it built, locked suite 9/0; not clean - sprint 1 sent back twice over the 500-line cap, and in the second revision the stage given the largest file read it once and reported cuts it never made (`8812c97`, deployed mid-run 16:54); the first stage asked was out of calls and claimed it again (`7556a2c`, 17:21); with thinking switched off after a lost reply, 35% of calls repeated the one before (`7cc1910`, 18:24); a fix stage sent the same refused empty answer ~50 times, 51 calls past its budget, unseen by the budget stop (`374a576`, 19:09). At the owner's request: thinking off for one reply after a lost one, not the rest of the visit (`c0e9b56`), and a rule to write in calls, not reasoning (`6277701`). Before: run-f7f82c39 (12:15-14:15 JST, 2026-10-07, `c0c42d5`, `qwen3.6-35b-a3b-mtp`) COMPLETED, hidden tests 10/10, locked suite 18/0, no harness fix during the run - NOT clean: the product audit found the repository's last commit was the release's CI files, with the release decision, release evidence and last sprint summary uncommitted, as in every finished run (`6ff9456`). Before: run-23928a49 started 08:26 JST (2026-10-07) on `cf4a1be`, COMPLETED 11:55 (the owner switched to qwen3.6-35b-a3b-mtp at 11:35, mid-run), hidden tests 10/10, locked suite 15/1 (AC-13 deferred), not clean - locked tests that never open the page (`34750f4`, deployed mid-run 09:15); edit tests filtering by a field's value (`42ce7b0`, 10:00); the locked AC-13 test looked for a title it made and never typed, deferred since sprint 1 (`ad0102f`, 11:29); with the suite's repairs spent, rounds 3-6 of sprint 3's fourth attempt each raised it for a fixer who could only call it a test bug (`69d3931`, deployed after it ended); product audit: sprint 3's record showed a sixth "Completed" attempt that never ran - the escalation's acceptance of the fifth (`c0c42d5`); a fix stage's notes `blocker.txt` and `verification.log` shipped (parked, 0.5.1). Before: run-b801a757 (07:50) cancelled at 08:21 - a dispute over the next sprint's unbuilt tests rewrote nine valid ones (`cf4a1be`). Before: run-3ae10313 (07:13) cancelled at 07:45 - "If invalid, the form disables" slipped the disabling check (`b1c4b41`). Before: run-7430e26b (06:57) cancelled at 07:08 - locked tests found list items by a name they never have (`6f58849`). Before: run-dedab9c1 (02:42-06:50) COMPLETED 10/10, not clean - released with a failing unit test (`101991b`); earlier in it - a lead that answered nothing about carried work closed its sprint (`0d35c1a`, deployed mid-run 03:32); disabling advice carried as owed (`7592d33`, `3ccf6b5`, deployed mid-run); unpassable locked filter tests (`bf36b9d`, the dispute stage, deployed mid-run 05:17; its name match loosened `4506b51`, 05:45; once per failed attempt `f529bf1`, 06:31). Before: run-a96fcb20 (02:15) cancelled at 02:37 - an axe contrast defect with no colours or ratio failed sprint 1's attempt over 25 passing tests (`8e9b842`). Before: run-932cbd58 (01:57) cancelled at 02:10 - toString read as an undefined assertion (`c926823`). Before: run-aa4e1f47 (00:22-01:52) cancelled in sprint 4, benchmark 9/10 - a specification that disabled "Add task" until a title was typed set code review against the page check (`fd62bcd`); earlier in it, not clean - carried work declined because no test requires it (`635d470`, deployed mid-run 01:03); locked edit tests left behind by their own change (`d0b1a2f`, deployed mid-run 01:31). Before: run-f3957015 (00:05) cancelled at 00:17 - the brief's interface section was not criteria, so QA's refusal test was turned away (`19369b2`). Before: run-7d8e02b6 (21:43-23:56) COMPLETED 8/10, false acceptance - a disabled named control and a self-contradicting locked edit test (`f4defca`, `2a60ddf`, `5680d34`); earlier in it, not clean - duplicate underlined defects each went to a fixer (`91418e4`, deployed mid-run 23:11). Before: run-2fb10bf1 (18:54-21:35) cancelled at the last sprint's third attempt, benchmark 10/10, not clean - security findings re-graded above the security review (`1ad5047`), line-number gutters written into the page (`284f3ca`); earlier in it - adopted advice the specialists found not built was dropped by sprints closed with nothing to build (`dcb7703`, deployed mid-run 19:37); plans sent back over fifteen carried items (`07b8f88`, deployed mid-run 20:24); out-of-brief review findings and advice (`dde0955`, deployed mid-run 21:12). Before: run-d6479ae6 (18:36) cancelled at 18:48 - the suite check named one offending line per file per round (`aed2c41`). Before: run-da5f08f4 (16:34-18:12) COMPLETED 7/10, false acceptance - the locked suite never found "Done" by its label and acted on the first of two filters (`117e7d6`, `f23e586`). Before: run-d4d24a3f (16:07) cancelled at 16:32 - the digest listed the harness's parse probe (`16161bf`). Before: run-755f003d (14:49-16:06) COMPLETED 10/10, not clean - a malformed locked suite went to product fixers until `a1684db` reopened it for QA. Before: run-976139d8 (14:33) cancelled at 14:47 in sprint 1 - criteria listed as bare numbers were guessed into the wrong sprints (`af3678e`). Before: run-32f01312 (14:06) cancelled at 14:31 in sprint 2 - a failed sprint's record counted a unit run only (`dc03b73`). Before: run-c336827c (2026-10-06 13:48-14:01 JST, gpt-oss-20b) COMPLETED 10/10 in 14 minutes, not clean - the harness put AC-3 in a sprint that excluded it (`f9ba962`). Before: run-72ab020e (2026-10-06 05:10-13:35 JST) COMPLETED, hidden tests 10/10, not clean - 14 harness fixes mid-run (`2b9d799` through `fd8dd47`), the owner switched qwen3.6 to gpt-oss-20b at 11:44, AC-5/AC-8 deferred by an auto escalation on a locked test that could not pass (`fd8dd47`). Runs: fa27ea5b cancelled 22:05 (slow red suite; `40b48f3`); 58190cd3 cancelled 22:23 (code review scope, serving script; `e6eb039`); a4ea15b5 cancelled 00:48 at sprint 3/5, 7 of 9 criteria passing (due-only test rounds, server refusal advice, kept config; `57b1fc8`); run-56e37323 56e37323 cancelled 01:23 (ledger red-suite gate read the acceptance run; `a12fa5f`); run-1264ac2e started 01:29 JST. 1264ac2e cancelled 01:50 (locked tests broken by their own helper; `1aa4eee`); run-84832a29 started 01:55 JST, cancelled 02:52 at sprint 3 (work orders on kept files; loop paused for the plan review, R1-R6 `88356da`..`be0be78`); run-e6294473 started 03:17 JST, cancelled 03:28 (acceptance port picked per Playwright process, so every agent-run suite hit ERR_CONNECTION_REFUSED; `baba502`); run-a8a952c4 started 03:35 JST, cancelled 04:02 (page threw on load and agents saw only 'element not found'; page check `3e4909b`); run-36ad4578 started 04:04 JST, cancelled 05:52 at 7 of 8 tests (agents could not see what the page renders; `4216193`); run-85fcf530 started 05:54 JST, cancelled 06:30 after sprint 1 accepted (the harness's own suite run was withheld as an agent repeat; `27e0714`, with `aa8c02c`); run-d3827f72 started 06:37 JST, completed 07:10, score 7/10 (not clean: placeholder locator in QA's suite, `3c41ab2`; size count, `6534294`); run-34237d1b started 07:24 JST, scored 10/10 at 08:07 but not clean (sprints with nothing left invented work; `7389b23`), cancelled 08:08; run-97036e80 started 08:09 JST, cancelled 08:40 (milestone review blocked on later criteria written AC\u2011n; `e01059a`); run-2466fb53 started 08:47 JST, cancelled 09:22 (sprint 1 stuck; failing tests now carry the page they failed on, `2226632`); run-6f8bed24 started 09:24 JST, cancelled 09:45 (re-planned sprint closed without work; `61bac8a`); run-dded3a26 started 09:50 JST, cancelled 10:11 (locked tests called toBeUnchecked; `eede7fa`); run-e5048126 started 10:17 JST, cancelled 10:52 (CI blind to a re-plan's regressions before any accepted sprint; `1bb78d9`); run-4e3e12c2 started 10:58 JST, cancelled 11:26 to deploy R7 (`467872b`, IDE-grade checks); run-7106082c started 11:28 JST, cancelled 12:33 (9/9 criteria but sprint 1 looped on its own unit tests; `578d74f`); run-9676bcd5 started 12:35 JST, completed 13:09, 10/10 hidden tests, not clean (audit: Sprint Record counts, unrun probes shipped; `f895d4a`); run-b88ce47a started 13:18 JST, cancelled 14:05 in sprint 2 fix round 4 (unit tests of the page churned on hand-built DOMs; kept jsdom setup and agreeing notes, `80e97e7`); run-1cbcdad2 started 14:07 JST, cancelled 14:25 in sprint 1 with 9/9 criteria passing (briefs still asked one command to run both suites; kept-file label untrue; no one-file unit command; `dca01ed`); run-5cfba2c8 started 14:27 JST, cancelled 14:59 in sprint 1 at 2/9 (fix stages did not connect a locator with a label one colon off; refusal advice left a probe named like the product; `f8bc9eb`, `dc91cf5`); run-eb409cbe started 15:00 JST, completed 18:23, scored 2/10 (not clean: list items, fake controls for unpassable locked tests; `2944517`, `1e39bf2`); run-142bada9 started 10:19 JST on 2026-10-05, cancelled 10:42 (a wedged model call held for up to 1800 s; pace bound `1ea4567`); run-2edd7b8f started 10:49 JST, cancelled 11:32 (specification sent back twice for refusing manual checks; `31e5dd7`); run-2922a051 started 11:39 JST, cancelled 12:01 at the owner's request to change the model (no finding); loop paused until the new model is served; run-a5127a41 started 13:27 JST on `qwen3.8-flash-next-q2_0` (:9090); not clean (Playwright callback shape missing from the guide, `8c8fb44`; sprint plan handed back over phrasing, `b75e850`), cancelled 16:36 in sprint 1 of 7 (false proven problem: node --test behind --import, `fbaceab`); run-4e5ce7a8 started 16:38 JST, cancelled 16:58 at the owner's request to change the model (no finding); loop paused until the new model is served; run-d4481a2c started 17:11 JST on `qwen3.8-27b@iq3_xxs` (LM Studio :1234), cancelled 18:20 (spiral recovery withheld QA's tools, so it answered with an empty suite; `b60b701`); run-1da84bd0 started 18:22 JST, FAILED 20:06 (second lost reply in a visit, regression from b60b701, fixed `c5c00b5`; also `removeChildren` underline `a221020`); waiting for the served model to match the settings; run-676fcf35 started 20:19 JST on `qwen3.6-35b-a3b-mtp` (LM Studio :1234), cancelled 20:44 (locked suite used a CSS role selector; `c3f9284`); run-3dca4304 started 20:46 JST, cancelled 21:41 (test round's defects were later sprints' work; `663a2fb`); run-4247b032 started 21:43 JST; not clean (verification `cd ... &&`, `1d06ea4`), deployed mid-run at 22:31 and 23:18 (orphan recovery resumed it each time); COMPLETED 23:58 JST, 10/10 hidden tests, not clean (`1d06ea4`, `dc8c03f`, `9c36688`; product audit: sprint summaries `9e36d48`, CI test keys `7be890a`); run-ee564419 started 00:11 JST on 2026-10-06, COMPLETED 01:46 with no harness fix but 9/10 hidden tests (false acceptance: state change inside a status view untested; `8a5aa61`); run-68049cc9 started 01:53 JST; not clean (repeated already-applied edit, `a9feb1c`), deployed mid-run at 03:18 and 04:41 and resumed; cancelled 05:07 (QA's product-bug blockers deferred four tested criteria; `d1668b1`); run-72ab020e started 05:10 JST; not clean (an unknown criterion id deferred, `2b9d799`), deployed mid-run at 05:46 and resumed. |
 Runs: fa27ea5b cancelled 22:05 (slow red suite; `40b48f3`); 58190cd3 cancelled 22:23 (code review scope, serving script; `e6eb039`); a4ea15b5 cancelled 00:48 at sprint 3/5, 7 of 9 criteria passing (due-only test rounds, server refusal advice, kept config; `57b1fc8`); run-56e37323 56e37323 cancelled 01:23 (ledger red-suite gate read the acceptance run; `a12fa5f`); run-1264ac2e started 01:29 JST. 1264ac2e cancelled 01:50 (locked tests broken by their own helper; `1aa4eee`); run-84832a29 started 01:55 JST, cancelled 02:52 at sprint 3 (work orders on kept files; loop paused for the plan review, R1-R6 `88356da`..`be0be78`); run-e6294473 started 03:17 JST, cancelled 03:28 (acceptance port picked per Playwright process, so every agent-run suite hit ERR_CONNECTION_REFUSED; `baba502`); run-a8a952c4 started 03:35 JST, cancelled 04:02 (page threw on load and agents saw only 'element not found'; page check `3e4909b`); run-36ad4578 started 04:04 JST, cancelled 05:52 at 7 of 8 tests (agents could not see what the page renders; `4216193`); run-85fcf530 started 05:54 JST, cancelled 06:30 after sprint 1 accepted (the harness's own suite run was withheld as an agent repeat; `27e0714`, with `aa8c02c`); run-d3827f72 started 06:37 JST, completed 07:10, score 7/10 (not clean: placeholder locator in QA's suite, `3c41ab2`; size count, `6534294`); run-34237d1b started 07:24 JST, scored 10/10 at 08:07 but not clean (sprints with nothing left invented work; `7389b23`), cancelled 08:08; run-97036e80 started 08:09 JST, cancelled 08:40 (milestone review blocked on later criteria written AC\u2011n; `e01059a`); run-2466fb53 started 08:47 JST, cancelled 09:22 (sprint 1 stuck; failing tests now carry the page they failed on, `2226632`); run-6f8bed24 started 09:24 JST, cancelled 09:45 (re-planned sprint closed without work; `61bac8a`); run-dded3a26 started 09:50 JST, cancelled 10:11 (locked tests called toBeUnchecked; `eede7fa`); run-e5048126 started 10:17 JST, cancelled 10:52 (CI blind to a re-plan's regressions before any accepted sprint; `1bb78d9`); run-4e3e12c2 started 10:58 JST, cancelled 11:26 to deploy R7 (`467872b`, IDE-grade checks); run-7106082c started 11:28 JST, cancelled 12:33 (9/9 criteria but sprint 1 looped on its own unit tests; `578d74f`); run-9676bcd5 started 12:35 JST, completed 13:09, 10/10 hidden tests, not clean (audit: Sprint Record counts, unrun probes shipped; `f895d4a`); run-b88ce47a started 13:18 JST, cancelled 14:05 in sprint 2 fix round 4 (unit tests of the page churned on hand-built DOMs; kept jsdom setup and agreeing notes, `80e97e7`); run-1cbcdad2 started 14:07 JST, cancelled 14:25 in sprint 1 with 9/9 criteria passing (briefs still asked one command to run both suites; kept-file label untrue; no one-file unit command; `dca01ed`); run-5cfba2c8 started 14:27 JST, cancelled 14:59 in sprint 1 at 2/9 (fix stages did not connect a locator with a label one colon off; refusal advice left a probe named like the product; `f8bc9eb`, `dc91cf5`); run-eb409cbe started 15:00 JST, completed 18:23, scored 2/10 (not clean: list items, fake controls for unpassable locked tests; `2944517`, `1e39bf2`); run-142bada9 started 10:19 JST on 2026-10-05, cancelled 10:42 (a wedged model call held for up to 1800 s; pace bound `1ea4567`); run-2edd7b8f started 10:49 JST, cancelled 11:32 (specification sent back twice for refusing manual checks; `31e5dd7`); run-2922a051 started 11:39 JST, cancelled 12:01 at the owner's request to change the model (no finding); loop paused until the new model is served; run-a5127a41 started 13:27 JST on `qwen3.8-flash-next-q2_0` (:9090); not clean (Playwright callback shape missing from the guide, `8c8fb44`; sprint plan handed back over phrasing, `b75e850`), cancelled 16:36 in sprint 1 of 7 (false proven problem: node --test behind --import, `fbaceab`); run-4e5ce7a8 started 16:38 JST, cancelled 16:58 at the owner's request to change the model (no finding); loop paused until the new model is served; run-d4481a2c started 17:11 JST on `qwen3.8-27b@iq3_xxs` (LM Studio :1234), cancelled 18:20 (spiral recovery withheld QA's tools, so it answered with an empty suite; `b60b701`); run-1da84bd0 started 18:22 JST, FAILED 20:06 (second lost reply in a visit, regression from b60b701, fixed `c5c00b5`; also `removeChildren` underline `a221020`); waiting for the served model to match the settings; run-676fcf35 started 20:19 JST on `qwen3.6-35b-a3b-mtp` (LM Studio :1234), cancelled 20:44 (locked suite used a CSS role selector; `c3f9284`); run-3dca4304 started 20:46 JST, cancelled 21:41 (test round's defects were later sprints' work; `663a2fb`); run-4247b032 started 21:43 JST; not clean (verification `cd ... &&`, `1d06ea4`), deployed mid-run at 22:31 and 23:18 (orphan recovery resumed it each time); COMPLETED 23:58 JST, 10/10 hidden tests, not clean (`1d06ea4`, `dc8c03f`, `9c36688`; product audit: sprint summaries `9e36d48`, CI test keys `7be890a`); run-ee564419 started 00:11 JST on 2026-10-06, COMPLETED 01:46 with no harness fix but 9/10 hidden tests (false acceptance: state change inside a status view untested; `8a5aa61`); run-68049cc9 started 01:53 JST; not clean (repeated already-applied edit, `a9feb1c`), deployed mid-run at 03:18 and 04:41 and resumed; cancelled 05:07 (QA's product-bug blockers deferred four tested criteria; `d1668b1`); run-72ab020e started 05:10 JST; not clean (an unknown criterion id deferred, `2b9d799`), deployed mid-run at 05:46 and resumed. |
| current run | `data/loop/current_run.txt` (git-ignored; `loop.sh status`) |
| database | Postgres data lives in the repo at `./data/postgres` (bind mount, git-ignored), database `langchain`, table `runs` keyed by `run_id` |
| transcripts | `/app/data/transcripts/<run-id>*.jsonl` inside the worker (`appdata` volume) |
| workspaces | `runs.repo_root`, e.g. `/app/data/workspaces/default/workspace-<run-id>` |

Healthy numbers on recent `web-todo` runs (2026-10-04): 11-19% of tool calls
failed - most of them guards working as designed (work-order ownership, parse
refusals, `node -e` refused) - 0 duplicate executions, 0-15% redundant reads,
sprint 1 reaching 9/9 acceptance criteria within ~20 minutes. On brief_low
before the redesign: 1.7-6% failed, 8-19% redundant reads.

### 0.3 The scripts

All in `scripts/loop/`, all documented in their own headers. The Python ones
run **inside the worker** and are piped in on stdin, so nothing is copied into
the container and a redeploy (which wipes the worker's `/tmp`) costs nothing.

| script | what it is for |
|---|---|
| `loop.sh` | the one entry point: `status`, `bench <benchmark>` (a gate run, e.g. `bench web-todo`), `start [brief]` (a brief file; defaults to `tests/brief_low.md`), `wait [minutes]`, `cancel [run-id]`, `score [run] [benchmark]` (also records the harness's own verdict and flags a false acceptance), `mutate [run] [n]` (n small changes to the product; how many the run's locked suite catches), `bench-report` (false acceptances per benchmark across `data/bench/`), `audit`, `stage <name> [HH:MM]`, `reads`, `timing`, `product [run-id]`, `checks`, `defects [run-id]`, `asked [run-id] <stage> [visit] [--full] [--system]`, `failures [run-id] [--full]`, `ready`, `resumed`, `deploy`, `suite`. Its header documents each. `bench`, `start` and `cancel` need `LOOP_USER`/`LOOP_PASSWORD` in the environment (the account is in 0.3.1). |
| `audit_live.py` | the 15-minute check: failure rate, duplicate executions (must be 0; a call a restart cut off before its result is counted apart as `[+N re-run after a restart ... expected]`), the times the run was resumed after its worker stopped, redundant reads, stage order, failures per stage, failure signatures with an example each. Says *where* to look. |
| `defects.py` | `loop.sh defects [run-id]`: each sprint attempt's defect queue - the check that raised each defect (`test round`, `acceptance suite`, `language service`, `code review`, `page check`, `regression`, `cross-file check`, `test command`) and every event after it (closed without a fixer, closed by the round's measurement, fixed with the fixer's account, left open - with no regression test, or still open when the attempt ended and why - reverted). Reads the transcript's `defect` records (from `cd06dd8`; older runs have none; a defect raised before a mid-run deploy shows as `raised before the ledger`). Duplicates show as one story under several sources. |
| `asked.py` | `loop.sh asked [run-id] <stage>`: what a stage was told (each message, cut at 3000 characters unless `--full`; the system prompt with `--system`), the calls it made, and its final structured answer. A stage visited several times lists its visits; a third argument picks one. Replaces the ad-hoc transcript snippets. |
| `failures.py` | `loop.sh failures [run-id]`: each failing acceptance test of the last measurement, with its criterion, the error and call log, and the page as the product showed it when the test failed - what tells a stale locator, a missing `page.goto` and a product bug apart. |
| `stage_trace.py` | every model reply, tool call and result of one stage, in order. Says *why*: the model's words just before a failed call usually name the harness message it misread. `HH:MM` is UTC (JST - 9) and skips earlier sprints of the same stage name. |
| `product_audit.py` | the product half of the audit (`loop.sh product [run-id]`): the product files, code lines per file (counted as the brief's line cap is), the intake's acceptance criteria, what the harness claimed (sprint summary counts, milestone acceptance evidence), and the product's own test command run once. Prints evidence; the reading is the checklist in 0.4.1. |
| `redundant_reads.py` | re-reads by (stage, file) and which notice answered them. One pair with many re-reads has twice been a misleading harness message. |
| `scripts/audit_run.py` | the older whole-run audit (predates this loop): separates *refusals that prevented damage* from *failures that cost the run*, and runs the cross-file checks over the product. Use it on a finished run; see section 5. |
| `model_ready.py` | `loop.sh ready`: is the model the settings name served at the address they name (and the judgement model, when one is set)? Prints one line per model, never a key; the last line must be `ALL READY` before any `bench`/`start`. |
| `verify_packs.py` | scaffolds stack packs for real in the worker (`docker compose exec -T worker python - [pack ...] < scripts/loop/verify_packs.py`): install, unit smoke test, acceptance smoke test, through a run's own commands and sandbox. Run it after changing a pack, the image's toolchains or a pinned version; every pack must pass. |
| `await_resume.sh` | `loop.sh resumed`: after a deploy while a run was live, waits up to 10 minutes for orphan recovery to resume it (the worker making model calls again). |

Records the harness keeps for an audit (from `969d6e6`..`70c50cc`, 2026-10-07):

- **Worker log lines** read `[time: LEVEL/process] [run-xxxxxxxx stage] message`:
  the run (first 12 characters) and stage from the graph's config, or the run
  the worker task executes; `[- -]` for a line outside any run. Filter a run's
  lines with `grep "\[run-xxxxxxxx "` instead of by time window.
- **Each defect carries its source**, shown in the Sprint Record as
  `- [STATUS] description - raised by <source> (Owner: role)`.
- **Every locked suite version** is kept in `<workspace>/.harness/acceptance-locks/vN/`
  with `vN.diff` from the version before; the decision that re-locks a reopened
  suite quotes the diff.
- **Decision rationales are whole** in state and in `<workspace>/.harness/decisions.json`;
  only `docs/decision_log.md` shortens one past 2000 characters, saying so.
- **Mid-run hidden score, operator only**: `LOOP_SHADOW_SCORE=1 loop.sh wait N`
  adds a shadow score to each check. Off by default - a score in view mid-run
  invites tuning the harness to the benchmark. `score` deletes the hidden tests
  and its working copy from the worker as soon as it finishes.

### 0.3.1 Taking over: the account, the model, and what does not travel

**The loop's operator account** (recorded here at the owner's request,
2026-10-07, so any agent can run the scripts; the owner deletes it when
development completes):

| | |
|---|---|
| user | `harness-test` (role `operator`) |
| password | `loop-test-only-pw-2026` |
| where it lives | the local Postgres only (`./data/postgres`); it is not a production credential |

`bench`, `start` and `cancel` read it from the environment - export it once per
shell, or put it before the command:

```sh
export LOOP_USER=harness-test LOOP_PASSWORD=loop-test-only-pw-2026
LOOP_USER=harness-test LOOP_PASSWORD=loop-test-only-pw-2026 scripts/loop/loop.sh bench web-todo
```

If a rebuilt database has lost it, recreate it with the same values (never
use, read or reset the `admin` account instead):

```sh
docker exec langchain-app-1 python -m app.server.manage create-user harness-test \
  --password loop-test-only-pw-2026 --role operator
```

**The rest of what a new agent needs:**

- **Where:** the repo is `/home/arun/Desktop/langchain`, branch
  `harness-hardening-session`, git remote named `main`
  (`git push main harness-hardening-session`). Containers `langchain-app-1`,
  `langchain-worker-1`, `langchain-db-1`, `langchain-redis-1`; the API on
  `http://localhost:8000`. Tests run from `.venv` (`loop.sh suite`).
- **The model (the owner's choice; they change it without saying so):**
  `openai/gpt-oss-20b` on LM Studio since 14:12 JST on 2026-10-08 (before it
  `qwen3.6-35b-a3b-mtp` from 11:35 JST on 2026-10-07: 2,100-3,700 output
  tokens and 19-32 s a call against gpt-oss's 400-840 and 5-8 s, which is why
  those runs took 5-8 hours), `http://host.docker.internal:1234/v1` from the
  containers, context 131,000, thinking effort medium, execution mode
  parallel, no judgement model. `loop.sh ready` before every run; it exits 1
  unless its last line is `ALL READY` - then start nothing and wait for the
  owner. Never load a model or change their settings.
- **Suite baseline (2026-10-08):** 9,687 pass, 29 skip, and the three
  `tests/test_codebase_seeding_api.py` S3 failures, in about 3 minutes.
- **Thinking (since `c0e9b56`, 2026-10-07):** a reply lost to reasoning (25,000 output tokens, nothing else) switches
  thinking off for the next reply only - the log says "for the next reply"; a second loss in one visit keeps it off
  for the rest of that visit ("for the rest of this visit"). While it is off, three identical calls running withhold
  that tool. Audit thinking with `loop.sh timing` (reasoning share, spirals).
- **After a mid-run deploy:** `loop.sh resumed`, then `loop.sh status`. The
  audit counts a call a restart cut off apart (`re-run after a restart`).
- **Waiting:** one `loop.sh wait 10` (first 40 minutes) or `wait 18`, run so
  its output reaches you when it ends (a background task you are notified
  about, or the foreground with a long enough timeout - never a forgotten
  `&`); tell the owner when it reports, in JST. Never edit `loop.sh` while a
  wait runs (`pgrep -f "loop.sh wait"` first).
- **Two agents in one tree:** before any commit, deploy, start or cancel,
  check for edits that are not yours (`git status`) and another agent's waits
  (`pgrep -af "loop.sh"`; in Claude Code also `ListAgents`). One agent drives
  (commits, deploys, starts, cancels); any other audits read-only and passes
  its findings to the driver. If the driver has gone, take the role so the
  loop does not stall.
- **Nothing in a session's scratchpad travels.** Every helper the loop uses
  is in `scripts/loop/`; put a new one there, not in `/tmp`.
- **Awaiting the owner's decision - do not change on your own:** the
  thinking budget (thinking effort/mode per role - the biggest time lever,
  0.9); the CRITERION severity policy (minor vs blocking grading); the `node -e`
  policy (one-off command-line code is refused); whether a browser test must
  cover every action the brief names; whether every fix must add a
  regression test; whether CLI products get the UI/UX consultation; deleting
  `harness-test` when the loop ends.

### 0.4 One iteration, step by step

```sh
export LOOP_USER=harness-test LOOP_PASSWORD=loop-test-only-pw-2026   # the operator account (0.3.1)
scripts/loop/loop.sh ready                             # last line must be ALL READY; otherwise start nothing
scripts/loop/loop.sh bench web-todo                    # the benchmark the gate is on; prints the run id and JST start
scripts/loop/loop.sh wait 10                           # first 40 minutes; then `wait 18`
scripts/loop/loop.sh score                             # when it ends: the hidden tests
scripts/loop/loop.sh product                           # then the product audit (0.4.1)
scripts/loop/loop.sh mutate                            # a finished run: how strong its locked suite is (~1 min a change)
scripts/loop/loop.sh bench-report                      # false acceptances across every scored run
```

`score` prints `FALSE ACCEPTANCE` when the harness finished a run whose product
fails hidden tests: that is a harness finding even when no transcript shows a
fault. `mutate` says how well the locked tests check what they check; it cannot
see a requirement no test checks (run-eb409cbe's suite caught 5 of 6 changes yet
the product scored 2/10). Do not edit `loop.sh` while a `wait` runs: bash reads
the script as it goes, and the wait dies with a syntax error.

Before `bench`, check the served model matches the settings (`loop.sh ready`;
the manual check is in `docs/HANDOVER.md` §5). After `deploy`, the worker's `/tmp` is empty: anything copied there for
auditing has to be copied again.

Then, for every failure signature and every stage that looks wrong:

1. `loop.sh failures` for the failing tests with their pages, `loop.sh defects`
   for what each round queued and how it ended, `loop.sh asked <stage>` for
   what a stage was told and answered, and `loop.sh stage <stage>` to read the
   replies around a failure. Decide:
   guard working as designed (a refused repeat, a parse refusal that kept a
   broken file off disk) - or a harness message that is wrong, misleading or
   missing. Only the second is a finding.
2. Also read the product: `docker compose exec -T worker sh -c "cd <repo_root>/<project> && npm test"`
   (or the stack's equivalent) and the review documents in `<repo_root>/docs/`.
   A reviewer or checker that reports working code as broken is a finding
   (several of the fixes on this branch were false positives in
   `src/app/analysis/*`).
3. Fix in `src/`, add a test named for the behaviour, prove it fails on the
   old code, then `loop.sh suite` (do not edit `src/` while it runs).
4. Commit with a message that says what the run did and why the change
   answers it; `git push main harness-hardening-session`.
5. `loop.sh deploy` **between runs** (0.1: no deploys into a live run since
   2026-10-08). In a run's first 40 minutes a bug means cancel, fix, deploy,
   start again; later, only a major bug cancels the run - anything else waits
   for the batch after it. (Orphan recovery resumes a live run across a
   deploy, and `loop.sh resumed` waits for it, if one is ever unavoidable.)
6. When the run ends, `loop.sh score`, then **audit the generated product
   before counting the run** (0.4.1). Then: if it scored 100% and nothing was
   found in the run or the product, count it toward the gate; otherwise the
   count is 0. `loop.sh bench` the next one.
7. Record the run in the gate row of 0.2 and the status table of
   `docs/HANDOVER.md`, and anything that changed how runs are tested in this
   section; commit and push.

### 0.4.1 Audit the generated product - every run, at the end (and mid-run when needed)

A run can look clean in its transcript and still ship a wrong product, or a
harness document that describes it wrongly. Standing instruction from the
owner (2026-09-30): audit the generated files at the end of every run, and
whenever a mid-run finding touches the product. A run is not clean until this
is done.

```sh
scripts/loop/loop.sh product [run-id]    # evidence: files, code lines, claims, real test result
```

Then read the product itself - every source file, not only the tests - against
the brief (`tests/brief_*.md`) and check:

1. **Every brief requirement is really built and reachable by a user.** A pure
   function with no UI wiring is not a feature. Try the obvious edge of each:
   empty input, whitespace, the value another path refuses (an add form that
   rejects an empty title while inline edit saves one was shipped past every
   review on run-fb102e16).
2. **The brief's constraints hold**: line caps (the script counts non-blank,
   non-comment lines as the harness check does), "no external dependencies"
   (a test runner in devDependencies is allowed), the stack it names.
3. **The tests exercise the real code**: they import the product module or load
   the real page; a suite that only asserts the repository's shape is not
   evidence.
4. **The repository holds its own record**: `git -C <workspace> status --short` is empty at the end - the release
   decision, release evidence and last sprint summary are committed (they were not before `6ff9456`).
5. **Hallucinations - every claim the harness or an agent made is true**:
   sprint summary counts against the real test result (run-fb102e16's
   summaries said 36 test cases for 36 unit + 10 browser tests - a harness
   counting bug), milestone-review acceptance evidence against the code it
   cites, README/docs against what exists, "tests added" against the files.
6. **Classify each finding.** A harness document or check that is wrong is a
   harness bug: fix it in `src/`. A product defect every stage missed is a
   finding about the pipeline: ask what instruction or check would have
   caught it in general (not for this product), and add that. Either way the
   run is not clean.

Always say when the next check will report (JST). If shell commands stop
working (the tool-approval check can fail transiently), schedule a retry about
10 minutes later rather than waiting for a person.

### 0.5 Things that bite

- Deploy = `docker compose build app worker && docker compose up -d app worker`.
  There is no source mount; a restart deploys nothing. `loop.sh deploy`
  compares the image's files with the working tree.
- Orphan recovery resumes any `running` run after a deploy. A superseded run
  comes back and competes for the two worker slots and the single model
  server: cancel it with `POST /api/runs/{id}/cancel`.
- Auth is a form-encoded `POST /api/auth/token`; there is no JSON login.
- Containers log UTC; the host is JST (+9). Transcript times are UTC.
- The full suite (`loop.sh suite`) takes about 3 minutes here: 9,687 pass,
  29 skip (2026-10-08), and three `tests/test_codebase_seeding_api.py` tests
  fail for want of S3 credentials. Tests that need the TypeScript compiler or
  Pyright skip on the host; run those inside the worker after a deploy. Any other failure is real - unless `src/` was edited while the
  suite ran (tests that read source with `inspect` then see shifted lines).
- A tool call id run twice, or a stage that restarts, is always worth a trace.
- A run that fails on `psycopg.OperationalError: ... server closed the
  connection unexpectedly` while `db` logs nothing is two processes on one
  socket, not a database fault. Check with a socket-to-pid map inside
  `worker` (`/proc/net/tcp` port 5432 against `/proc/<pid>/fd`): a socket held
  by both pid 1 and a pool child is the defect. Every shared pool and the
  worker's runner are per process (`app.server.process_local`); a new one must
  be too.

### 0.5.1 Parked: known, not fixed

- A stage's own notes shipped in the product: one run's fix stage, unable to find a fault, wrote
  `blocker.txt` and `verification.log` instead of answering with its blocker. 4 such files in 199
  stored products (`blocker.txt`, `verification.log`, `defect_fix_notes.txt`, `ui.mock.txt`). Not
  fixed: judged by name, a rule would also remove a product's own fixtures (a log reader's sample
  logs). Watch for it in the product audit.
- Tools are still offered when command execution is disabled; the duplicate
  `test/` and `tests/` suites seen in run 71d58b84 are not addressed.
- Commands run without a shell, so a wildcard argument reaches the program
  as written: `node --test tests/unit/*.js` fails with "Could not find" on
  Node 20, which does not expand it itself. 4 calls in 25 runs (to
  run-ccc66650), each recovered on the next call by naming the files.
  Expanding wildcards in the harness would also rewrite arguments that are
  patterns on purpose (a `grep` regex), so it is left until it costs more.
- A milestone review may ask for later sprints' work to be removed. Seen once (2026-10-07):
  sprint 1 had built every sprint's features, the product was 84 lines over the brief's
  500-line limit, and the review's required remediation was to delete the later sprints'
  features - which the lead planned and the revision began, for sprint 2 to build again.
  The cause, builders never told which locked tests are a later sprint's, is fixed
  (`app.acceptance.sprint_scope`, `3b01d8a`), so this should not recur. If a review
  asks for it again, the reviewer and the lead need to be told that work a later sprint's
  criteria need is never deleted, only made smaller.
- The plan check (`work_a_later_sprint_delivers`) reads the user-action table, which has
  no persistence: one run's sprint 1 still built storage that sprint 3's criterion
  (persist between refreshes) delivers. Minor - storage is a few lines - so not fixed.
- A scaffold whose smoke test fails twice (`1dde0ed` retries it once) is "left to the
  agents": no `.harness/stack-pack.json`, so the pack's files are neither protected nor
  restored, though their own comments say the harness keeps them. Seen once, after one
  failure on a worker recreated a minute earlier; if it recurs, the files' comments or the
  contract need to follow the outcome.

### 0.6 Removed on 2026-09-29

`scratch/` (`check_run.py`, `get_run_logs.py`, `get_runs.py`,
`resume_run.py`, `run_monitor.py`, `start_run_api.py`, `run_logs.json`,
`worker.log`) and the root-level `audit_output.txt`. They logged in as
`admin`/`dev`, named fixed run ids and the old `langchain_auth` database, and
carried plain-text credentials; everything they did is covered by
`scripts/loop/`. **Those credentials remain in git history and should be
treated as exposed and rotated.**

### 0.7 How a sprint runs now (work orders, templates, the Sprint Record) - 2026-09-30

Built at the operator's request, modelled on how a software team hands work to a
developer who is new to the codebase. The loop was paused for it; audit the next
runs against this section.

**Every document comes from a template.** `src/app/doc_templates/templates/*.md.j2`
holds one Jinja template per workflow document (the nine in `docs/`, the sprint
summary, the stage summaries). A model supplies the content of each section; the
template fixes the headings, their order, the labels inside a record and what an
empty section says, so a different model produces the same document shape.
`tests/test_document_templates.py` fails if a schema field is not placed in its
template or if the heading skeleton varies with the content. The sprint panel in
the UI parses `sprint_N_summary.md`; its template's header comment says which
lines must not change.

**The technical lead writes work orders.** `SpecialistTask` now carries `title`,
`files`, `interfaces`, `steps`, `edge_cases`, `test_cases`, `verification` and
`out_of_scope`. The lead is given the specification's contract sections to copy
from. Each specialist's brief shows its own work order; the `testing` specialist
also gets every other work order's interfaces and test cases and writes the tests
against them while the code is written (contract first).

**Definition of ready** (`app.analysis.work_orders.readiness_problems`), checked
before dispatch: a code work order with no `files` or no `test_cases`, a file
outside the pinned project directory or in `docs/`, code with no `testing` work
order, a `verification` command the sandbox refuses, or carried-forward items with
no `carried_forward_decisions`. An unready plan goes back to the lead once with the
list and the plan it was (log line: "Milestone plan is not ready to hand out");
after the retry budget it is dispatched with the problems in `integration_notes`.
`WORKFLOW_WORK_ORDER_READINESS=off` disables it - only the test suite does that.
Commands a task names are also checked against the sandbox and a refusal is
written onto the task (`app.analysis.planned_commands`).

**Definition of done** (`app.sprint.record.definition_of_done_gaps`), checked when
the milestone review accepts: every work order returned a result and no tracked
defect is open. A gap sends the sprint back (bounded by `MAX_MILESTONE_REVISIONS`,
then escalates) - the next sprint never starts on an unfinished one.

**The Sprint Record** (`docs/sprint_N_summary.md`) keeps the old header, test
counts, "Planned", "Features Implemented" (task titles now) and "Defect Summary",
and adds: Work Orders (outcome, files planned vs changed, verification, blockers),
Defect Log (reproduction, expected/actual, how it was fixed, what verified it,
regression test), Review Findings (every round of the milestone and security
reviews, with a disposition), Carried Forward, and Lessons for the Next Sprint.
Everything in it comes from state, the execution ledger and the transcript, not
from an agent's account.

**Carry-forward and lessons.** Non-blocking findings from a sprint's last review
round are handed to the next sprint's lead, who must take or decline each in
`carried_forward_decisions`. Tool failures repeated in a sprint (from the
transcript) are handed on as lessons. Both reach the lead's request under
"Carried forward from earlier sprints" and "What went wrong earlier in this run".

**What to audit on the next runs:** does the lead fill the work-order fields (read
`docs/milestone_plan.md` - "not stated" everywhere means it did not); how often
the readiness check bounces a plan and whether the second plan fixes it; whether
specialists follow their work orders (fewer refused commands, fewer files outside
`files`); whether the Sprint Record's dispositions and carried items match what
the reviews said; and whether a carried item is actually taken in the next sprint.

**The intake keeps the brief's acceptance criteria** (19c5033). They join the
success measures verbatim, a comma list without "and" counts as a list, and a
deferred item naming (whole word) a capability the brief's own acceptance
criteria require is marked `(the brief requires X: "..." - only what goes
beyond that is deferred)`; nothing is removed. Audit `docs/product_intake.md`
first on every run: nothing the brief's acceptance criteria require may appear
unmarked under Deferred scope, nor as an exclusion in the specification's
Product Scope (run-557346a2 deferred "Task editing" for "Users can add, edit,
delete tasks"). Also check the marks are right: a mark on an unrelated item
means the matching is too loose again.

---

### 0.8 What the model is given (review of 2026-09-30, commits 6719aec..15a6241)

A review of 23 runs (2,604 tool calls) found most of the struggle was context,
not capability: 26% of calls repeated a read/list/search the stage had already
made, and failed calls were led by missing files, answers written to files and
line-number edits. What changed, and what to audit on the next runs:

- **Locked dependencies.** Both images install `uv.lock` exactly (`uv export
  --frozen`); production had been running 38 packages the suite never saw,
  including deepagents 0.7.20, whose `read_file` has no line numbers. Check
  after any deploy: `docker exec langchain-worker-1 python -c "import
  importlib.metadata as m; print(m.version('deepagents'))"` equals the lock.
- **Reasoning carried across tool calls** (`app.models.with_the_reasoning_carried`):
  the tail of each of the last four tool-calling replies' reasoning is sent back
  in that reply's `content` (LM Studio ignores every reasoning field). Audit:
  the repeated-identical-call share should fall well below 26%.
- **Tools**: `inspect_repository` and `read_repository_file` removed from role
  agents; the answer tool's description now says it is the only way to finish.
  Audit: "answer saved as a file" refusals.
- **Prompts**: writing rules ~9,100 -> ~5,000 chars, testing rules halved, a
  framework block shared by several seeded modules injected once; generated
  framework notes now describe the tool, not the product, and rows generated
  under the old prompt are regenerated. Specialist system prompt ~25,300 ->
  ~12,500 chars before framework notes.
- **Saved models** (settings page): every applied model configuration is kept
  and can be picked again; credentials are never stored with it.
- **Model settings are the operator's.** The review found gpt-oss-20b loaded
  with 10 experts per token (trained with 4). The loaded model and
  `runtime_settings.model_name` must agree before a run starts - check
  `/v1/models` on the model server; do not start a run while they differ, or
  LM Studio either refuses it or unloads the operator's model to serve it.

### 0.9 Why a run takes ~3 hours (review of 2026-10-01, run-482cd03b)

163 minutes for a 347-line app: 1,024 model calls, 950 tool calls. The model
is busy 98% of the wall clock; tools 2%, idle ~0%. Measure a run with
`loop.sh timing [run-id]` (per phase, per stage family, model vs tool time,
reasoning share, how far model calls overlapped) and LM
Studio's `print_timing` lines (`prompt eval time = ... / N tokens` is the
part of the prompt re-read; `f_keep` is the share of the cache kept).

- 91% of output tokens are reasoning (838k of 918k). gpt-oss at its default
  effort reasons ~1,000 tokens before each tool call; "low" measured 6-25x less
  on a probe. Effort is the operator's setting - propose an A/B, do not change it.
- The first reasoning carry-over (last 4 replies) re-wrote the prompt 4 replies
  back every call: median 6,390 prompt tokens re-read per request vs 1,068
  before, 44 min a run vs 6. Now append-only, per OpenAI's gpt-oss guidance
  (keep analysis since the last final message). Check `f_keep` stays ~0.9.
- 82% of tool calls look (read/ls/glob/grep), 8% write. `ui.js` was read 60
  times across 27 stages; every stage starts fresh on a ~10-file product.
- Parallel mode overlaps model calls only 1.0-1.3x (>1 in flight 13-28% of
  specialist time): every gated write/command pauses and pauses drain one per
  superstep. LM Studio's 8 slots go unused.
- The lead spends ~37 min a run: one huge structured plan, 94% reasoning, the
  25k ceiling hit almost every run.
- Verification is the biggest phase (62 min: 7 test rounds, 6 defect fixes).

Implemented after a self-review the owner asked for: the whole small product in
each stage's opening request (`app.agents.project_snapshot`), and, instead of
approving in-line, every queued parallel pause answered in one resume under
auto-approve (`queued_parallel_pauses`, `_GateCount`) - linear and attended runs
never have a queued pause and are unchanged. Not implemented: two-step lead
planning (measure first), per-role reasoning effort (the operator's setting -
an A/B with thinking mode on / effort low needs no code), one sprint for a
small brief (sprints and the Sprint Record are the product's design).

**2026-10-08: why runs went from 1-3 hours to 5-8.** From 2026-10-07 the
owner's model was `qwen3.6-35b-a3b-mtp`, with 2,100-3,700 output tokens and
19-32 s per call. gpt-oss-20b runs at 400-840 tokens and 5-8 s. Thinking stayed
on, and sprints now really are sprints: the scope fixes keep each sprint to
its own criteria, so there are more rounds. Back on gpt-oss-20b (since 14:12
JST, 2026-10-08), expect calls about 4× faster. The thinking budget remains the
owner's decision and the biggest lever.

**2026-10-10: run-b30deacb-081d-4ce5-b10c-c6bc39f6b25b early stop & empirical post-mortem (24 min wall clock).**
Started at 11:42 JST on 2026-10-10, caught and failed at 12:06 JST (24 min).
- Outcome: Acceptance suite failed to run with `ENOENT: Could not read package.json` (exit 254) in rounds 1-5.
- Root cause: Premature contract inference in architecture stages. `contract.the_pack()` ran during workspace file checks in `principal_architect` and `architecture_review`, triggering `_infer_contract()` which persisted `.harness/stack-pack.json` to disk before the `scaffold` node ran. When the `scaffold` node ran in `src/app/graph/acceptance_nodes.py`, `if pack is not None and contract.read(root) is None:` evaluated to false because `.harness/stack-pack.json` already existed. Scaffolding was completely skipped, leaving `simple-to-do-list-app/` with no `package.json`, `index.html`, or dependencies.
- Fix: In `src/app/graph/acceptance_nodes.py`, replaced the flawed `contract.read(root) is None` gate with `already_done = bool((state.get("scaffold_result") or {}).get("ok"))` and `if pack is not None and not already_done:`.
- Verified by `tests/test_scaffold_not_skipped_by_inferred_contract.py` (proven failing on old code, 1/1 passed, zero banned words, zero run IDs).

---

### 0.10 How a product is tested now (2026-10-04)

`docs/PRODUCT.md` describes the whole product; this is what a monitor needs to
know about its testing, and what changed most recently.

- **A stack pack scaffolds every project and keeps its test setup**
  (`src/app/stacks/packs/`). For `browser-javascript`: `playwright.config.js`,
  `playwright.setup.mjs` (the page check), `test-setup.mjs` (a jsdom page for
  unit tests), `scripts/serve.mjs`, and the manifest scripts `start`, `test`,
  `test:acceptance`. Agents are refused writes to them and the workspace digest
  labels them "the project's test commands run it". The scaffold proves itself
  with two smoke tests before any agent writes.
- **Acceptance suite.** Written by QA from the criteria, then locked
  (`acceptance/`); the harness runs it every round. A failing test carries what
  the page showed when it failed, and - when nothing on the page matches its
  locator but something differs only in case, punctuation or role - a
  "Nearly there" line naming it (`near_misses` in the JavaScript packs). The
  page check records uncaught errors, console errors, failed requests and HTTP
  errors on load (`test-results/page-load.json`).
- **One-off scripts.** Code on the command line (`node -e`, `python -c`) is
  refused; the refusal says to put it in a file named `tmp-<what it checks>`.
  Files named as throwaways (`file_kinds.is_scratch`) that a stage created and
  nothing references are swept before every test round and at release; any
  other name is taken for the product and ships.
- **Unit tests** use the pack's runner. In `browser-javascript`, `npm test` is
  `node --import ./test-setup.mjs --test ... tests/`, so every test file has
  `document`, `window`, `localStorage` and the page's own `Event`/`FormData`
  classes (jsdom 26.1.0 - the last release for the image's Node 20). One file:
  `node --import ./test-setup.mjs --test tests/<module>.test.js`; a bare
  `node --test` skips the page. A test that builds a page of its own is told to
  use the one it has, and refused on the third time in a stage. `browser-react`
  gets the same from Vitest's jsdom environment.
- **Instructions follow the pack.** Seed rows `<key>:setup` (how to install and
  configure runners) are left out where a pack set the project up, and so are
  the stack block's rules for projects that set themselves up (one command
  running both suites, the module-system choice).
- **IDE-grade checks.** The TypeScript language service (JavaScript/TypeScript)
  and Pyright (Python) report names nothing defines, missing exports and
  imports, and use before declaration: a note on every write, a defect at the
  CI gate once the batch is done.
- **CI gate.** Regressions are measured against both the last accepted state
  and the last measurement; a fix that breaks a passing test is reverted; code
  review runs on each batch.

**Watch on the next runs:** unit-test churn on page code (five web-todo runs in
a row before `80e97e7`; should now be gone); probes named like the product
(`src/import-ui.mjs` in run-5cfba2c8, beside twelve `tmp-*` ones the sweep
handles) - the refusal now names the throwaway form; fix rounds that circle a
locked test whose locator nearly matches the page (six stages in run-5cfba2c8;
the "Nearly there" line should end it); agents adding their own scripts to
the manifest; a fullstack run churning on unit tests of its page
code (`fullstack-node` has no unit DOM yet; see
`docs/harness-improvement-plan.md` §3).

## 1. The loop, in the order it must happen

```
start a run  ->  read its transcript and its product  ->  find what the
harness did wrong  ->  fix it with a test  ->  run the suite  ->  commit and
push  ->  rebuild and deploy  ->  start the next run
```

Four ordering rules, each of which has cost a stage or an hour when broken:

1. **Never rebuild the worker while a run is executing.** Replacing the
   container kills the in-flight Celery task. The run is not lost - the graph
   checkpoints at every node and the startup sweep recovers and resumes it -
   but it costs that stage's work and two minutes of orphan-recovery grace,
   and it muddies whatever the run was being observed for. Check first:

   ```sh
   docker exec langchain-db-1 psql -U postgres -d langchain -tAc \
     "select run_id, status, left(updated_at,16) from runs
      where status in ('running','waiting_for_approval','waiting_for_review');"
   ```

   Ten rows come back and none of them matter: nine attended runs parked at
   approval gates on 18 September and one waiting for review since the 14th.
   They have no live task. Look at `updated_at` - anything older than an hour
   is parked, not running.

2. **Never edit `src/` while the suite is running.** Several tests assert on
   `inspect.getsource(...)`, and a module imported before an edit keeps its
   old line numbers, so the assertion fails on code that is correct. This
   produced three phantom regressions on the other machine before it was
   understood.

3. **Never run two suites at once.** They share one testcontainers Postgres.
   Two concurrent sessions is what turned one stuck suite into two, and the
   instinct to "start another run to compare" is exactly what a silent hang
   produces.

4. **Deploy before starting the run you intend to observe**, or you are
   measuring the previous build. **Check first whether the source is actually
   mounted**, because it decides what "deploy" means:

   ```sh
   docker inspect langchain-worker-1 \
     --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}'
   ```

   - A `./src -> /app/src` line means the dev overlay is up and the source is
     live. A `docker compose restart worker app` is then enough, because the
     only stale thing is the modules the running process imported at start.
   - **No such line means the stack was started from the base file alone and
     `/app/src` is baked into the image.** A restart then deploys nothing at
     all: `docker compose build app worker` followed by `up -d app worker`.

   On 2026-09-26 the stack was up without the overlay, and only the base file
   had been used. A restart would have looked like a deploy and changed
   nothing - the worker would have kept running the previous commit while
   every later measurement was attributed to the new one.

5. **A setting that saves is not a setting that is read.** Deploying
   `execution_mode` exposed three independent breakages in one toggle: it was
   missing from `runtime_settings.SETTABLE_KEYS` so a write raised
   `ValueError`; the mode it selected crashed and then looped; and the
   dispatcher called bare `load_settings()`, which reads the container's own
   environment, so the stored value was never consulted. The store row said
   `parallel` while the worker said `linear`.

   After changing a setting, check the value where the code reads it, in the
   container that reads it:

   ```sh
   docker exec langchain-worker-1 python3 -c "
   import sys; sys.path.insert(0,'/app/src')
   from app.server.runtime_settings import effective_settings
   print(effective_settings().execution_mode)"
   ```

   `effective_settings()` is the store-aware one. `load_settings()` is
   deliberately a pure function of the environment handed to it, so a bare
   call anywhere in the product is this bug.

6. **A dashboard that is down looks exactly like a harness with nothing to
   report.** `/metrics` returned HTTP 500 for an unknown length of time, and
   every `STAGE_DURATION` recording in the worker failed with it - 17 per run,
   one per stage. The cause was a single file:

   ```
   RuntimeError: Read beyond file size detected, file is corrupted.
   ```

   `prometheus_client` names each process's mmap file after `os.getpid()`,
   `PROMETHEUS_MULTIPROC_DIR` is inside the persistent volume, and a
   container's PIDs start from 1 again on every restart - so a fresh process
   opened `histogram_9.db` written by a different PID 9 days earlier. One of
   49 files, and it took out every metric in both containers.

   The fix names files per process generation, and removes unreadable ones at
   startup. Nothing stops it happening again through some other route, so
   check the endpoint itself rather than trusting that a quiet dashboard is a
   quiet harness:

   ```sh
   curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/metrics
   curl -s http://localhost:8000/metrics | grep -c stage_duration_seconds
   ```

   A 500, or a zero count while a run is executing, means the multiprocess
   directory - not the harness. List it and read each file:

   ```sh
   docker exec langchain-worker-1 python3 -c "
   from pathlib import Path
   from prometheus_client.mmap_dict import MmapedDict
   for f in sorted(Path('/app/data/prometheus').glob('*.db')):
       try: list(MmapedDict.read_all_values_from_file(str(f)))
       except Exception as e: print('unreadable:', f.name, e)"
   ```

   `read_all_values_from_file` returns a generator, so it must be consumed.
   Calling it without `list(...)` reads nothing and every corrupt file looks
   fine - which is a mistake made once already, inside the fix for this.

---

## 2. Running the suite

```sh
cd /home/arun/Desktop/langchain
ENV=development TEST_TIMEOUT_SECONDS=240 timeout 1200 \
  python3 -m pytest -q --no-cov -p no:randomly -p no:cacheprovider \
  > /tmp/suite.txt 2>&1
tail -20 /tmp/suite.txt
```

Every part of that matters:

- **`> /tmp/suite.txt` rather than `| tail`.** Piping `pytest -q` to `tail`
  buffers everything until the end, so a running suite and a hung one look
  identical: no output, one process, no way to tell. Two runs were lost to
  this for 32 and 11 minutes. Redirect, then read the file - the `[ NN%]`
  markers tell you where it is.
- **`ENV=development`** or the suite refuses to start: `JWT_SECRET_KEY is not
  set`.
- **`--no-cov`** because `addopts` in `pyproject.toml` sets
  `--cov-fail-under=80`, and a partial run always fails that.
- **`TEST_TIMEOUT_SECONDS`** drives the hang guard added to
  `tests/conftest.py`: `faulthandler.dump_traceback_later(..., exit=True)`
  around every test. A hang becomes a stack trace naming the test instead of
  an unbounded wait. Set `0` to disable.

**Expected result on this machine: about 4,671 passing, 3 failing, 6 skipped,
in under three minutes.**

The three failures are environmental and must not be chased:
`tests/test_codebase_seeding_api.py` needs S3 credentials this host does not
provide (`botocore.exceptions.NoCredentialsError` against the
`langchain-artifacts` bucket). Verify that claim rather than trusting it -
`git stash`, run that file, `git stash pop`, and confirm the same three fail.
That is how they were cleared here.

**Stale baselines to ignore.** `/tmp/base2.txt` and `/tmp/base_fresh.txt`
were captured on the other machine with a partial mount and carry 78 failures
including 32 `test_graph_routing` errors, which are artefacts of the
invocation. Diffing against them invents regressions.

---

## 3. Starting a run

The cheapest way is to clone a finished run: it carries the same brief,
reviewer, review policy, model choices and unattended mode, so consecutive
runs are comparable.

```sh
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode "username=$LOOP_USER" --data-urlencode "password=$LOOP_PASSWORD" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

NEW=$(curl -s -X POST http://localhost:8000/api/runs/<finished-run-id>/clone \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])")

curl -s -X POST "http://localhost:8000/api/runs/$NEW/start" \
  -H "Authorization: Bearer $TOKEN"
```

`harness-test` is an operator account created for this loop. It exists only in
the local Postgres volume and is not a production credential. Delete it when
the loop ends.

The brief throughout has been `tests/brief_low.md`: a to-do list with add,
edit, delete, filtering, persistence and responsive design, capped at 500
lines of code. Keep using it. Every number in this document and in the
findings log is against that brief, and changing it invalidates the
comparison.

The model is whatever `runtime_settings` points at:

```sh
docker exec langchain-db-1 psql -U postgres -d langchain -tAc \
  "select key, value from runtime_settings;"
```

Currently `unsloth/Qwen3.6-35B-A3B-MTP-GGUF` at
`http://host.docker.internal:8888/v1`. **Confirm the endpoint answers before
starting a run**, or the run stalls with nothing in the log:

```sh
docker exec langchain-worker-1 bash -lc \
  'curl -s -m 10 -o /dev/null -w "%{http_code}\n" \
   -H "Authorization: Bearer $OPENAI_API_KEY" \
   http://host.docker.internal:8888/v1/models'
```

Note that `.env` points `OPENAI_BASE_URL` at port **1234** (LM Studio), which
is usually not running, while the runtime settings point at **8888**. The
runtime settings win for runs. Do not "fix" the mismatch without checking
which server is actually up.

---

## 4. Watching a run while it runs

### 4.1 The three commands

**State:**

```sh
docker exec langchain-db-1 psql -U postgres -d langchain -tAc \
  "select status, current_stage, left(updated_at,19) from runs
   where run_id='<run-id>';"
```

**Progress, from the transcript, which is the authoritative record:**

```sh
docker exec langchain-worker-1 /opt/venv/bin/python - <<'PY'
import json, collections
p = '/app/data/transcripts/<run-id>.jsonl'
mc = 0; last = None; stages = []; tools = collections.Counter(); errs = collections.Counter()
for line in open(p, encoding='utf-8', errors='replace'):
    try: r = json.loads(line)
    except Exception: continue
    k = r.get('kind')
    if k == 'model_request':
        mc += 1
        if r.get('stage') != last: stages.append([r.get('stage'), 0]); last = r.get('stage')
        stages[-1][1] += 1
    elif k == 'tool_call': tools[r.get('tool')] += 1
    elif k == 'tool_result':
        c = str(r.get('content') or '')
        if c.lstrip().startswith('{"error"') or c.startswith('Error:'): errs[c[:70]] += 1
print('model calls:', mc, '| tool calls:', sum(tools.values()), '| failed:', sum(errs.values()))
print(' -> '.join(f'{s}({n})' for s, n in stages))
print(dict(tools.most_common(6)))
for e, n in errs.most_common(6): print(f'  {n} {e}')
PY
```

**Events worth being interrupted for**, as a filter on the worker log rather
than raw tailing:

```sh
docker compose logs worker --since 1m -f 2>&1 | grep -E --line-buffered \
  "Traceback|ERROR|CRITICAL|Task .* succeeded|Task .* failed|withholding its tools|\
restarted|Resumed run|escalat|MUST FIX|brief requirement|Committed sprint|paused"
```

That filter is deliberate. It covers the *failure* signatures as well as the
happy path, because a filter that greps only for success stays silent through
a crash and silence looks identical to "still running".

### 4.1.1 After a run dies, ask what the worker recorded

A task that fails permanently is written to a Redis dead-letter list, and for
most of this harness's life nothing read it. Nine entries had accumulated over
thirteen days before anything reported them, including two runs killed by a
`SyntaxError` in `sandbox.py` and two by SIGKILL:

```sh
docker exec langchain-worker-1 python3 -m app.server.manage failed-tasks
```

It reports and changes nothing. `--clear` forgets them, and is worth passing
once a batch has been dealt with, so the next report is only new failures.

This is the first place to look when a run's own `error` field says nothing
useful, because a task killed by the pool never got to write one.

### 4.2 Telling slow from stuck

This is the single most useful diagnostic skill here, because on a 35-billion
parameter model a legitimate model call can take three and a half minutes and
a stuck run looks the same.

```sh
docker exec langchain-worker-1 stat -c "%y" /app/data/transcripts/<run-id>.jsonl
docker exec langchain-worker-1 date -u "+%H:%M:%S"
```

If the transcript was written in the last couple of minutes, the run is
working. Note that the containers log UTC and the host is in JST (+0900);
comparing the two directly has caused a false alarm here (a run "stuck for 15
minutes" was 70 seconds old).

For a process rather than a run, **CPU time is the test**:

```sh
ps -eo pid,etime,time,pcpu,cmd | grep pytest
```

A process with 4 seconds of CPU after 32 minutes of wall clock is blocked,
not computing. That one line is what identified the deadlock in §6.1.

---

## 5. Auditing a finished run

```sh
docker cp langchain-worker-1:/app/data/transcripts/<run-id>.jsonl /tmp/run.jsonl
ENV=development python3 scripts/audit_run.py /tmp/run.jsonl \
  /app/data/workspaces/default/workspace-<run-id> tests/brief_low.md
```

**Pass the brief as the third argument.** Two of the cross-file checks compare
the product against the operator's brief rather than the run's restatement of
it, and without it they fall back to the run's own documents - which is
precisely what a run that redefined a requirement out of existence has already
edited. The script says so when the brief is missing, but it is easy to
ignore.

### 5.1 The numbers that matter, and what they have been

| number | meaning | history |
|---|---|---|
| failures that cost the run | the one to drive down | 11.8% corpus average -> 2.6% -> 1.5% -> 0.4% on the other machine -> 2.0% -> **1.0%** on `977eedf8` |
| refusals that prevented damage | the checks working; **not waste** | 8 on `977eedf8` |
| identical repeats in a stage | a stage re-asking an answered question | 5, or 1.6% of model calls |
| read repeat / read withheld notices | the read ladder doing its work | 44 / 18 |

Refusals and failures are counted separately on purpose. A refusal is the
harness stopping something bad; counting it as waste makes a working check
look like a defect, and that mistake has been made in this repo before.

### 5.2 The other half: the product itself

**Every run in this harness's history that shipped something broken shipped it
with a green suite.** A green suite is not evidence. Check the product
directly:

```sh
docker exec langchain-worker-1 /opt/venv/bin/python -c "
import sys; sys.path.insert(0,'/app/src')
from pathlib import Path
from app.analysis.integration_checks import summarise_integration
print(summarise_integration('<workspace>', None, Path('/tmp/brief.md').read_text()))
"
```

And read what the product actually exports, because that is the question the
documents can lie about:

```sh
docker exec langchain-worker-1 bash -lc \
  "grep -oE 'export (async )?function [a-zA-Z]+' <workspace>/<project>/app.js"
```

On `977eedf8` that listed `addTask, deleteTask, toggleTask, editTaskTitle,
filterTasks, loadTasks, saveTasks, init` - and the presence of
`editTaskTitle` is the whole story of that run (see §7.1).

---

## 6. What monitoring has actually found

Ordered by how much each cost to find, because that is the best guide to
where to look next.

### 6.1 A deadlock that only fires on a fresh database

**Found by:** noticing a pytest process with 4 seconds of CPU after 32
minutes, then querying `pg_stat_activity` in the testcontainers Postgres.

```
pid 77 | idle in transaction | SELECT pg_advisory_xact_lock($1)
pid 78 | active | Lock | virtualxid | CREATE INDEX CONCURRENTLY IF NOT EXISTS ...
```

The schema lock added to serialise `CREATE TABLE` is transaction-scoped.
LangGraph's `PostgresSaver.setup()` runs three `CREATE INDEX CONCURRENTLY`
statements, which cannot run inside a transaction block, so they run on
another connection and wait for every overlapping transaction to end -
including the one holding the lock, which is waiting for `setup()` to return.

**Why it hid:** the indexes use `IF NOT EXISTS`, so it fires on a fresh
database and never on an established one. In production that is a cold start,
which reads as "the service took two goes to start". In the suite it is every
session, because testcontainers gives each one a new database. And the test
file it stopped at **passes in six seconds on its own** - it needs an earlier
test to have left a connection holding the lock, so bisecting by file would
never have found it.

**The lesson to carry:** when something hangs, look at CPU time first and the
database's own lock views second. Do not bisect by test file; an interaction
bug is invisible to that.

### 6.2 The harness instructing and then punishing the same thing

This is the most common defect class in this codebase - **five instances
found so far** - and the one to suspect first when a run is blocked by
something that looks correct.

- `TESTABILITY_RULE` tells the model to declare a Playwright `webServer`; two
  checks then reported the resulting `server.mjs` as blocking.
- Four role prompts said "All documentation goes in the `docs/` directory"
  while the tool refused every write there.
- The environment description told the stack selector Playwright is required
  for UI and, separately, to prefer the runtime's built-in runner, without
  saying how they combine: 14 specifications named Playwright and only 2 of
  their stack documents agreed.
- A timed-out Playwright run was answered with "there is no browser to open a
  page with", seven minutes before 34 browser tests ran in the same sandbox.
- `_the_test_command_will_not_run_this` fired 215 times on files that are not
  tests, telling `app.js` 83 times that its assertions never execute.

**How to find them:** when a check blocks something, ask *"which of our own
instructions produces a file that trips this?"* and grep the prompts for the
thing being refused.

### 6.3 Checks that read the run's own account of itself

`56faee7` is the most important change in the branch and the shape is worth
internalising. The brief says "Users can add, edit, delete tasks". A run
recorded in its own specification that "'Edit' refers to toggling completion
status; inline text editing is deferred", and from that point every document
enumerated create, update, complete and delete. Every check read those
documents and agreed. `edit` is absent from four of the eight products stored
on the other machine.

A run may *defer* a requirement and say so - that path exists and reports it.
What it may not do is redefine one out of existence. **Any check that reads
`docs/` is reading something the run can edit.** When adding a check, ask
what it would say about a run that had quietly rewritten the requirement.

### 6.4 State that outlives the call that set it

Three instances, all subtle:

- `_LAST_FAILING_FIELDS` is module-level, so a stage that answered in prose
  was logged with some earlier stage's field names and "(unknown)".
- A test double defined `WorkflowRunner.shared()`, a method that existed
  nowhere else, so every test passed and the deploy raised `AttributeError`.
- The transcript's delta recording trimmed nothing, because the tests grew a
  conversation by appending to its end and the harness injects a message
  before the end.

**The rule:** where a test patches a boundary, one test somewhere must assert
that the boundary is spelled the way the code spells it, with nothing
patched.

### 6.5 Measurements that killed an obvious idea

Keep doing this. Each cost an hour and saved days.

- **Inlining small files into every request.** 46% of reads are redundant,
  five files are 78% of them, so inlining looks obvious. But only 13% of
  reads are whole files under 16 KB, and the one role already handed its
  source inline still made 13 `read_file` calls. Rejected.
- **Playwright correlating with failure.** Two failed runs blocked on a
  Playwright suite nothing ran, so the harness looked like the cause. Of the
  eight stored products, the only earlier one that installed Playwright is
  also the only earlier one that built and tested `edit`. Rejected.
- **The security reviewer rubber-stamping.** Three of 41 reviews returned
  `passed` with no tool call - but that role is handed its source inline, so a
  review with no reads has still read the code. Rejected.
- **Carrying the reasoning of replies that also wrote text** (2026-10-07,
  `qwen3.6-35b-a3b-mtp`). `with_the_reasoning_carried` puts the last 800
  characters of a reply's reasoning into the next request only when the reply
  had no text, and this model writes a line of text with most calls: 59 of
  87 tool-calling replies with reasoning in one run had theirs dropped. The
  harness also attaches a fresh workspace message to every call, so for
  this model's chat template every earlier reply sits before the latest
  user message, and the template strips the reasoning of all of them. A
  reply's text is all the next call sees. It looked like the cause of
  10,000-token replies that ended in re-reading the same file. But across
  five runs the next call repeated the last one 0-7.7% of the time after a
  reply whose reasoning was dropped, against 0-5.9% (34% in one run) when it
  was carried. Rejected.

---

## 7. What is working and must not be rebuilt

Each of these was verified against live output, not inferred.

### 7.1 The brief check, end to end on `977eedf8`

At the end of sprint one the product had `addTask, deleteTask, toggleTask,
filterTasks` and no way to edit - the same defect as the other machine's runs
7, 8, 11 and 14. The cross-file check fed the milestone reviewer a finding
quoting both the requirement and the architecture-review line that deferred
it. Two sprints later the product exports `editTaskTitle` and ships
`app.edit.spec.ts`. The last-sprint brief gate never fired, because the
reviewer caught it first, which is the cheaper path. **Both mechanisms are
needed; only one has now been exercised.**

### 7.2 Budget-edge tool withholding

`specialist_backend_1` reached 38 of its 40 model calls with no answer
written. Its tools were withheld, leaving it bound to the structured-output
tool only; it answered; the run continued with no stage restart. Fired 9
times across the other machine's runs 13 and 14, both of which had zero
restarts, against run 12's three restarts and death at 13.5 million tokens.

### 7.3 Orphan recovery, its grace, and auto-resume

A run touched in the last 120 seconds is logged as "too recent to call
abandoned" rather than judged - verified on this run's first seconds. A
genuinely abandoned run is marked failed and put back on the queue
automatically, with three safety properties: nothing resumes unless a worker
answered and did not claim the task, a run resumes at most once per worker
process, and an OOM-killed worker resumes nothing.

### 7.4 The read ladder

Note, then withhold the bytes with an anchor, then refuse the read entirely
past twice the exit threshold. Verified live in the deployed image. The read
refusals fired twice on `977eedf8` and 18 withholdings.

---

## 8. Where to look next, in priority order

1. **`replace_lines` is the least reliable tool** - 27 of 46 calls errored on
   the other machine, 58.7%. Its stale-line-number message has since been
   improved to name where the line moved to, but the rate has not been
   re-measured since. Measure it on the next two runs and decide whether the
   tool earns its place beside `edit_artifact`.
2. **Reads are still 70% of tool calls.** Every mechanism aimed at this has
   helped and none has changed the shape: 55% of all reads across 13 runs
   asked for a file nothing had touched since that stage last read it. The
   project memory (purpose and interface per file, carried between stages)
   deployed too late to be measured. **Measure it**: the §22.1 method in the
   hardening plan, on runs produced by the same brief.
3. **Nothing marks a failed run's workspace as not deliverable.** Run
   `6b511391`'s product fails 5 of its own 45 tests and sits in the
   workspaces directory looking like everything else.
4. **The repeat-timeout refusal never escalates.** It reached "already timed
   out 8 time(s)" on the same argv with identical wording each time.
5. **Test code is 2.4x the product** on `977eedf8`: 965 lines of tests
   against 402 of application code. Counted separately so no budget was
   breached, but worth a measurement of its own.
6. **The task list is built and switched off.** `HARNESS_TASK_LIST=true`
   enables `TodoListMiddleware`. No measurement supports it yet; §25 of the
   hardening plan records the experiment that would decide it.
7. **`mkdir` is the one doubled-path shape the guard cannot catch.**
   `strip_a_doubled_working_directory` rewrites an argument that repeats its
   own `working_directory`, but only when the path as given does not exist
   and the stripped one does - which is what makes it safe rather than
   clever. A command that *creates* a path defeats that test, because
   neither path exists yet. Measured across every stored transcript: 972
   commands ran with a `working_directory`, 60 repeated it, and the guard
   silently corrected 59 of them. The one it could not was
   `mkdir -p todo-app/e2e` with the working directory already `todo-app`, on
   run `07cd52ae`, which left an empty `todo-app/todo-app/e2e` in the
   delivered product. Cost is clutter, not breakage, and at one occurrence
   in 972 it is recorded rather than fixed. If it is fixed, the test to use
   is the *parent* directory's existence, not the target's.
8. **Part I items 3, 4, 5, 6, 10, 11, 13-16** of the hardening plan, and
   Part III item 5 - wiring the `deploy/` generators, whose security defects
   are fixed but which nothing calls.

---

## 9. Things that will waste your time if nobody tells you

- **`current_stage` is empty in the `runs` table** for much of a run's life.
  It is set at approval gates. Use the transcript, not that column.
- **The `runs` table has 150+ rows**, nearly all from before this loop. Sort
  by `updated_at` and ignore anything older than the current session.
- **`docker ps` filtered on names misses the testcontainers** - they get
  random names like `pedantic_perlman`. Filter on the image
  (`redis:7-alpine`, `postgres:15-alpine`) and exclude `langchain-`.
- **`pgrep -f pytest` matches your own shell command**, so it reports
  processes that do not exist. Use `ps -eo pid,cmd | awk '$2=="python3" &&
  /pytest/'`.
- **A `docker compose restart worker` does not pick up a Dockerfile change.**
  Rebuild, then `up -d`.
- **The dev overlay bounds uvicorn's graceful shutdown to 5 seconds.** Without
  that, a source edit triggers a reload that waits for the run event stream to
  close, which never happens, and the API hangs unhealthy while the worker
  carries on - so nothing tells you the API has gone.
- **Chromium is in the worker image now**, at
  `/home/appuser/.cache/ms-playwright`, shared by every run. If a run starts
  downloading its own copy, that cache has gone missing and every run will
  pay 650 MB again.

---

## 10. Disk, and the two commands that reclaim it

```sh
docker run --rm -v langchain_appdata:/v alpine du -sh /v/*
docker compose exec worker python -m app.server.manage workspaces
docker compose exec worker python -m app.server.manage checkpoints
```

`python -m app.server.manage` is the entry point - there is no top-level
`manage.py`. `--help` lists the rest: `recover-orphans`, `reconcile-runs`,
`list-users`, `clear-run-overrides` and the account commands.

The `workspaces` and `checkpoints` subcommands report size, age and run
status, and each takes a flag to delete. Neither has been run in anger.

History here: the volume reached 11.8 GB for about 90 runs, of which 8.5 GB
was per-run Chromium copies and 0.9 GB `node_modules`. Both were cleared and
the image-level browser cache means the Chromium half will not come back.
Transcripts are about 500 MB and are **the evidence base for every
measurement in the findings log** - do not delete those.
