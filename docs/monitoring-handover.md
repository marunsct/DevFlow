# How this harness is monitored, what that has found, and where to look next

**Written for:** whoever continues the harness-hardening loop from here, on a
different account and with none of this conversation's context.

**As of:** 2026-09-29, branch `harness-hardening-session`, pushed to the git
remote named `main` (`git push main harness-hardening-session`). Section 0 is
kept current by whoever runs the loop; sections 1-10 are the method and history
written on 2026-09-24 and still hold unless section 0 says otherwise.

**What this document is not.** It is not a list of what to change. That lives
in `docs/harness-hardening-plan.md` (the running findings log) and in the git
log of this branch, where every fix's commit message says what a run did and
why the change answers it.

---

## 0. Start here: the loop as it runs now

### 0.1 The standing instruction

Run a continuous audit / fix / deploy loop on this harness, and do not stop:

1. start a run of a brief;
2. audit its transcript, logs, database and tool calls closely - especially
   failed and unnecessary calls - every **15-20 minutes** (not more often; it
   costs tokens);
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

**The gate.** A run is *clean* when it completes and the audit finds no bug
and no improvement worth making. Two consecutive clean runs of
`tests/brief_low.md` move the loop to `tests/brief_medium.md`; two clean runs
of that move it to `tests/brief_high.md`; then the same there. A run in which
anything was fixed resets the count to zero, including a fix deployed while it
ran.

**Keep, and fix only where wrong:** dynamic agent instruction injection (the
`plugin_instructions` table, the seed and its middleware), the parallel/linear
execution toggle in settings, and the sprint summary.

**Never:** hard-code run ids (`tests/test_no_run_ids_in_the_source.py`
enforces it), read or reset the `admin` password, use the admin account for
the loop, write the settings table directly (settings need admin; the owner
configured the model endpoint `:8888` and parallel mode), print values from
`.env`, kill the owner's GPU processes (llama-server and friends), or add
knowledge/doc credentials to `sandbox._ENV_PASSTHROUGH`.

### 0.2 Where it stands

A new session or account starts at `docs/HANDOVER.md` (written 2026-10-01): the standing instruction, the current run, setting up on another desktop, and the security rules. Runs b69802cd, 391a8b68 and d9642862 (2026-10-01) ran on `qwen3.8-flash-next-coder-iq1_m` on port 9090; the owner switched back to `openai/gpt-oss-20b` on LM Studio at about 17:45 JST.

| | |
|---|---|
| brief | `tests/brief_low.md` |
| clean runs toward the gate | **0 of 2** on brief_low. run-a124957e failed 14:00 JST on 2026-10-03 (a proven problem was counted as reported too loosely; fixed `13264f2`); run-e58ff6ab started 14:06 JST on it. run-0cef92c0 completed 13:19 JST on 2026-10-03, product not clean (state split between two arrays loses data after reload; no harness fault); run-a124957e started 13:20 JST on `e5b4a53`. run-3528cef5 cancelled 12:53 JST on 2026-10-03 (rounds dropped proven problems after the first; fixed `e5b4a53`); run-0cef92c0 started 13:04 JST on it. run-de592ee9 failed 12:40 JST on 2026-10-03 (review revisions spent on real findings; no harness fault); run-3528cef5 started 12:42 JST on `8aea6dc`. run-0b81710f cancelled 12:14 JST on 2026-10-03 (numbered throwaways not swept, tester refused their delete; fixed `8aea6dc`); run-de592ee9 started 12:22 JST on it. run-0e0b4ae4 failed 11:36 JST on 2026-10-03 (runner collision hidden from its check by the Jest entry-point path; fixed `1a2074b`); run-0b81710f started 11:42 JST on it. run-82f10c90 cancelled 11:06 JST on 2026-10-03 (test server port did not match the runner's; fixed `a59d512`); run-0e0b4ae4 started 11:11 JST on it. run-582f6ab6 cancelled 10:30 JST on 2026-10-03 (duplicate-export refusal named one export of two; fixed `bcc6354`); run-82f10c90 started 10:35 JST on it. run-fb4af14e completed 09:57 JST on 2026-10-03, product not clean (a diff that parsed shipped in model.js; no description control; fixed `dc205aa`, `5d07338`); run-582f6ab6 started 10:09 JST on it. run-0d03c64c cancelled 09:23 JST on 2026-10-03 (tool text cut off at an over-escaped quote, refused without naming it; fixed `c5c7b22`); run-fb4af14e started 09:28 JST on it. run-3c2a7e6f completed 09:05 JST on 2026-10-03, product not clean (no task description anywhere in the UI; the check that should have named it ignored `await import` namespaces; fixed `c2d5b1b`); run-0d03c64c started 09:12 JST on it. run-6824c586 cancelled 08:28 JST on 2026-10-03 (a line edit's range ran over a closing bracket its content left out; fixed `b01ece4`); run-3c2a7e6f started 08:30 JST on it. run-23fce753 cancelled 07:47 JST on 2026-10-03 (JSON comma repair, a hole in the Jest check, a needless plan re-ask; fixed `fc3a91b`); run-6824c586 started 07:49 JST on it. run-1572742d cancelled 07:26 JST on 2026-10-03 (appending with `replace_lines` was refused; fixed `423bef1`); run-23fce753 started 07:28 JST on it. run-ac6af679 failed 07:03 JST on 2026-10-03, a regression of mine (the empty-sprint send-back produced a worse plan and the run was failed on it; fixed `ad23516` by folding the sprint in the workflow); run-1572742d started 07:12 JST on it. run-2dd6fede cancelled 07:00 JST on 2026-10-03 (Jest over ES-module tests, which the seed guidance contradicted and nothing diagnosed; fixed `4941ed6`); run-ac6af679 started 07:02 JST on it. run-8fda442d cancelled 06:38 JST on 2026-10-03 to deploy pin fixes (`9765f7c`) and a plan-check fix (`b5d9fdb`); run-2dd6fede started 06:45 JST on it. run-938594b7 failed 06:26 JST on 2026-10-03 (the review's revisions were shared with test re-plans, and two of its gating findings should not have gated; fixed `e30ccd1`); run-8fda442d started 06:33 JST on it. run-838a8246 cancelled 06:14 JST on 2026-10-03 (a browser spec opening a module page by `file://` went undiagnosed; now a cross-file finding, `b82f48e`); run-938594b7 started 06:16 JST on it. run-810f8156 cancelled 05:44 JST on 2026-10-03 (a refusal named the product's own module as a probe's destination; fixed `a22508e`); run-838a8246 started 05:46 JST on it. run-b9c91b67 cancelled 05:23 JST on 2026-10-03 (a suite switched off with `skip` was accepted; fixed `cd23f68`); run-810f8156 started 05:31 JST on it. Still 0 after run-8647e985 failed at 04:55 JST on 2026-10-03 and `25b9bc3` was deployed (regression-test rule, syntax for every language, runner collisions, empty sprints, the dependency finding); run-b9c91b67 started 05:13 JST on it. On the §0.7 build: run-1236224f cancelled at 15:08 JST (stack chose console assertions as its "testing framework"; fixed b38a670), run-557346a2 cancelled at 15:35 JST (intake deferred editing the brief requires; fixed 19c5033), run-1194558b failed at 15:59 JST (stack_selector reasoned past 25,000 output tokens twice; the model server is now LM Studio with GLM-4.7-Flash, which ignores `chat_template_kwargs` - the one-call switch-off now also sends `reasoning_effort: "none"`, 6cbba5d), run-1d397438 cancelled at 16:27 JST (the plugin middleware's framework lookup - an auxiliary model call with no reply cap, timeout or reasoning switch - reasoned 60,000+ tokens for 20 minutes in front of the architect's first call; now capped at 2,048 tokens / 180 s with reasoning off). When a stage's first call has no reply for longer than a full reply takes, read the tail of LM Studio's `~/.lmstudio/server-logs/<month>/<latest>.log` to see which request the server is actually generating. run-2566d1fd cancelled at 16:57 JST (architecture review returned `approved` over its own **major** finding - no edit flow in the spec - and routing read the status alone; a pass over gating findings is now routed as changes_required for the architecture and milestone reviews), run-6fcfc7ae cancelled at 17:12 JST (stack testing framework "None (not required for MVP)" passed the exact-match check and was rewritten to "None ... for the logic, Playwright for the page"; declining a runner in more words is now refused too), run-5b2c2067 cancelled at 17:27 JST (my 19c5033 deferral check deleted a deferral of authentication/sync/notifications: the model's measure "ease of use and error-free" made "use" required and prefix-matching hit "User"; now brief criteria only, whole-word match, and the item is marked, never removed), run-47afecb1 cancelled at 17:45 JST (the lead wrote test cases as {given, when, then} as the readiness feedback asked; the schema wanted strings, refused them, the next answer dropped them and the plan was dispatched "not ready" with no testing work order; work-order list fields now accept structured items), run-16dead51 cancelled at 18:15 JST (parallel mode: `specialist_gather` surfaced queued approval pauses by stage NAME, so `specialist_testing_4` was answered 11+ times while three `specialist_ui_ux_*` pauses waited from the fan-out's first minute; the testing task wrote the page, script and a server itself. Pauses now surface oldest first). The model is now `openai/gpt-oss-20b` (admin change 17:17 JST, 20,000 output tokens). To see the pause queue of a live run, list its checkpoints (thread id from `runs.thread_id`) and print `specialist_pauses` per checkpoint. run-03037887 cancelled at 18:42 JST (the pause fix held - no queued waits - but the test round edited the product's `app.js` itself, a fix no defect log or owner saw; a `test_round_*` stage may now change tests, test config, documents and manifests only), run-63904b9a cancelled at 19:00 JST (4-6 failed calls a run were `ls` or commands in the pinned project directory before anything was written into it; the directory is now created when it is pinned), run-7e536444 cancelled at 19:23 JST (the architect and the lead listed `/simple-to-do-list-app` before the plan pinned it - 6 failed calls; the directory is now pinned and created at intake from the product name, for a workspace with no project directory yet), run-bc144aa5 cancelled at 19:52 JST (pin worked, 0 failures through the lead; then the plan was dispatched after 3 readiness attempts with two work orders naming no files, and the security task wrote `index.html` three times over the interface task in the same superstep - 10 of 36 calls failed; the fan-out now reads the work orders' `files` and never runs a no-file task beside one that claims files), run-e9f9c022 cancelled at 20:28 JST (clean to the specialists, 3.7% failed; then four specialists wrote `package.json`, which only one work order declared - the work order declaring a package manifest now goes before the rest), run-721e9ff3 cancelled at 20:44 JST (0 failed calls, but the lead called `ls ./` about twenty times, each a success with the same listing, so no rung escalated; a query answered identically past four repeat notes is now withheld). The audit's failure rate does not show this kind of waste: read the lead's `loop.sh stage technical_lead` trace for repeated identical calls. run-d90f3448 cancelled at 21:20 JST (the `ls` withholding fired as designed; then the testing task wrote the backend task's `app.js`, the documentation task wrote the testing task's unit test, three tasks edited `package.json` - a specialist may now write only its own work order's files, or files no work order lists; `.work-order-files.json` holds the owners). Also seen there, not changed: the lead re-read lines 1-100 of two documents ~8 times (64% redundant reads) - the read ladder withholds content from the 3rd repeat and refuses only at 12; revisit if `openai/gpt-oss-20b` keeps doing it. run-e2c31c92 failed at 23:24 JST (the model server answered "No models loaded" while the operator switched models - not a harness fault; run-26946721 was cancelled at once for the same mismatch). On the §0.8 build: run-f4b91980 cancelled at 00:30 JST (repeated identical calls 26% -> 13%, answers saved as files 0, 4% failed; but the milestone review raised as blocking work the plan gives to a later sprint - reviews now judge a sprint against its own scope, 7af63ff), run-27a05b4c cancelled at 00:47 JST (generated framework notes described a typical project - `src/`, a bundler, Jest - against the harness's layout and the seeded notes, and names like "localstorage" got notes; generation now covers testing mechanics only, v3 marker, 3bd9588), run-a920a5c7 cancelled at 01:04 JST (v2 notes dropped as designed; 0 failed calls, but 35 of 36 `grep` calls over twelve runs left the mode unset and 28 answered with file names alone - one review searched its spec eight times and got its own file name back each time; `grep` now answers with the matching lines unless the model asks otherwise), run-f93c9f3b cancelled at 01:32 JST (the `grep` fix held and the architecture review approved first time; but 62 of 71 `glob` calls over twenty runs found nothing - 36 were bare fragments like `.js` or `taskStore`, which match only a file named exactly that. A wildcard-free pattern without a `/` is now searched as `**/*<fragment>*`, and an empty answer to one says `glob` matches file names only and points to `ls` and `grep`), run-9c7cd0c9 cancelled at 02:04 JST (MAJOR: the interface task, refused a write to the data task's `taskModel.js`, deleted it with `delete_artifact` - ownership and the test-round rule were checked on write and edit but not on delete or move; both now are, at both ends of a move. Also: the "thinking off" call after the lead's 25,000-token spiral reasoned another 12,372 tokens - `openai/gpt-oss-20b` ignores `reasoning_effort: "none"` (384-1,990 reasoning tokens on a probe) and honours "low" (64-70), while GLM honoured "none"; the value is now measured once per endpoint and model, logged as "Reasoning switch for ..."), run-ccc66650 cancelled at 02:54 JST (sprint 1 clean - 1.1% failed, Sprint Record complete; then MAJOR: the lead spiralled on sprint 2, the recovery call answered with no work orders and a blocker, and the empty plan went straight to a test round and two reviews - an empty plan is now not ready. The readiness retry count was also never reset, so sprint 2's unready replan was dispatched as "still not ready after 3 attempts" without being sent back; readiness and assignment retries are now per plan. And the lead's `src/app.js` - a path inside the project - recorded no owner for `simple-to-do-list-app/src/app.js`; a work order path whose first part is not the project, `docs`, an existing top-level entry or a near-spelling of the project is now read as inside the project), run-1f2247d0 cancelled at 03:21 JST (the measured reasoning switch held: the lead's recovery call answered in 162 reasoning tokens and 5 s, against 12,372 and 106 s before. But the lead wrote `test_cases: []` for all seven work orders three times running - the third with concrete acceptance criteria on each - and the plan was dispatched unready after ~7 minutes of re-planning; 54 readiness problems over 25 runs were this one. A code work order with no test cases now takes its acceptance criteria as them; one with neither is still sent back), run-192097fd cancelled at 03:48 JST (the testing work order wrote a stub `src/ui.js` that no work order listed, over the version another stage had written; over 25 runs testing specialists wrote product code nine times. The test round's rule - tests, test configuration, documents and manifests only - now holds the testing work order too, and it is told so in its brief; ownership is checked first because it names the owner. A testing stage may still delete code it created itself - its probe renamed out of the runner's way - and a move now carries the file's creation record), run-e32e3b81 cancelled at 06:15 JST in sprint 2 of 3 (sprint 1 accepted, 8/8 tests, the Sprint Record complete; sprint 2 sent back with two real majors. Then MAJOR: the backend's note on a repeated read - "You have already read lines ..." - was written into the text `read_file` numbers, so every real line of that read came out two numbers high; the stage's `replace_lines` at the numbers shown were refused, 12 times in this run and 50 against 47 successes over 25 runs, and when told the right line the model used it 3 times in 16. The agents' backend now holds the note back (`hold_notes`, `held_read_note`) and the path middleware puts it ahead of the numbered text. Also fixed: gpt-oss wrote its next turn (its end, start and channel delimiters, then a new reply) into a `blockers` item; the stage summary was refused and the Sprint Record would have been - accepted answers are now cut where a delimiter begins, and workflow documents drop a stray one), run-a2c9bf72 FAILED at 07:43 JST in sprint 1 (the numbering fix held - no shifted-line refusals; but sprint 1, the task store alone, was sent back three times and the run stopped. Two harness causes: every review finding went to the lead as a required change, so revisions took on suggestions - encrypt stored tasks, remove `@playwright/test` - and the encryption lost its key on reload, a new major; and the third review's blocking "no index.html" was sprint 2's work, which `later_sprint_work_in` could not see because it names no user action. A revision now requires only gating findings and lists the rest as not required; a finding whose named files a later sprint makes and this one does not is recorded as minor. Also: 17 of 52 `replace_lines` refusals over 25 runs pinned the right line without its last characters - a prefix of 8+ characters now pins it. Product audit: 145 lines, 14/14 of its own tests pass), run-482cd03b COMPLETED at 10:33 JST in 163 min (2 sprints, 2.8% failed calls, 13% redundant reads, the revision request listed only gating findings) but NOT clean on the product audit: editing changes the title only though the intake recorded title/description, and 4 of 20 unit tests were placeholders (`assert.ok(true)`, `1 + 1 === 2`) counted in "26 passed" - `a_suite_that_asserts_only_constants` now reports them at write time and to the reviewer, graded as breaking. Also fixed after it: the reasoning carry-over is append-only (see §0.9). run-e29a5d5d cancelled at 11:11 JST for the build below (self-reviewed with the owner's go-ahead): under auto-approve every queued parallel pause is now answered in one resume, each through its own stage's gate count (`_GateCount`); a small project's files go ahead of each stage's opening request (`project_snapshot`, 24,000 characters). run-bc6a22c6 cancelled at 11:37 JST: the stages before the lead made 1 tool call in all (snapshot working), but the lead's second attempt - six work orders covering the five modules of the sprint's scope - was sent back for three small problems and the third, after a reasoning spiral, was two work orders (page skeleton and manifest), which was dispatched. Now the best unready attempt is dispatched (`_the_better_plan`), a quoted `<` in a planned command is an argument (`shlex` punctuation mode), and a manifest- or config-only work order needs no test cases. run-48d4ab8d cancelled at 12:03 JST: batch approval worked - more than one specialist call in flight 45% of the specialists' time with two specialists (13-28% before) - but the backend work order's verification was `node --test .../tests/tasks.test.js`, a file the testing work order owned and had not written, and the backend specialist tried to write it seven times in 2.5 minutes. A work order whose verification names another work order's file is now told whose it is, not to write it, and to report the check that waits (`with_borrowed_files_noted`). run-50cce01c cancelled at 12:17 JST (MAJOR): `npm install jsdom` was refused as a product dependency - the refusal named `npm i -D` for a test-only package - and the backend specialist wrote its own `node_modules/jsdom/package.json` and `index.js`, both accepted. Writes, edits, deletes and moves inside a directory a tool fills (`INSTALLED_DIRECTORIES`: node_modules, .venv, venv, site-packages, __pycache__, .git, caches, .agent-home) are now refused. run-e2aea2bf cancelled at 12:53 JST: the snapshot showed in the test round - one call, `npm test`, three real defects - but `npm test` timed out twice in the first defect fix and was then refused for the rest of the run as "would time out again", five times, to the stages fixing the hang and the test rounds after them. A timeout now counts against a re-run only with nothing written since, as `failed_this_way_before` already counted failures. run-f94f95d2 cancelled at 13:10 JST: fastest yet - planning, sprint 1's build, test round, security and milestone review in ~10 minutes - but the sprint's scope named index.html, style.css, app.js, ui.js and model.js and the plan's work orders covered only the state and storage modules; the milestone review found it after the build. A file the sprint's goal, scope or criteria names, that no work order lists and that does not exist yet, is now a readiness problem; the file-name pattern also reads `state.test.js` whole. run-e3985f85 COMPLETED at 15:38 JST in 144 min (3 sprints, milestone accepted, 10% failed calls - mostly parse refusals keeping broken edits off disk) but NOT clean on the product audit: the brief's "Mark tasks as complete/incomplete" was never built - no toggle in the UI, model or events, and `save()` drops `completed` - so the Completed filter can never show a task. The intake listed it as an MVP candidate and the spec specified `toggleComplete`; no sprint planned it, because the plan was checked against the success measures alone and the brief's acceptance criteria never say "complete"; the last sprint's lead then "declined ... (future work)" with no sprint after it. The planner's checklist now carries the intake's MVP candidates after the measures, each to be assigned a sprint (`_what_the_sprints_must_deliver`). Also: sprint 3's second attempt spent four test/fix rounds on `play_debug_e2e.js`, a debugging script a fix stage wrote, and the "regression tests" written for it - the last a suite checking that another suite says `expect`. A defect whose files are all tests or throwaway scripts (`file_kinds.is_scratch`, which now also reads a `debug` segment anywhere in a name) needs no regression test and is not charged to the budget; the fix stage is told to delete a debugging script nothing runs and to fix a test in place, not write a test about it. The product shipped 11 throwaway scripts and ~10 debug suites. And a `replace_lines` refused for a parse error whose `content` carries `-`/`+` diff markers now says so (sent 5 times in two stages, each answered only "Unexpected token '-'"). run-b69802cd (first run on `qwen3.8-flash-next-coder-iq1_m`, started by the owner) cancelled at 16:28 JST: the worker logged "Framework instructions resolved for this stack: html, css, javascript, playwright, node, python, react, typescript, vanilla javascript, vue" for a vanilla HTML/CSS/JS stack. The selected section was matched word by word and it names what it rejects ("no TypeScript", "rules out Vue/Svelte/React/Alpine"), and `python3 -m http.server` under Additional tools brought the Python instructions ("You are working in a Python environment"). The section is now read clause by clause: a clause that rejects (no, not, without, rules out, instead of, ...) and the tools field select nothing, and a name the model extraction returns that the section only rejects is dropped. run-391a8b68 cancelled at 16:58 JST: the framework fix held (javascript, html, css, localstorage, node, playwright); but the product directory was pinned as `simple-to-do-list-app-greenfield-single-page-tas` - the new model's product name carries a description after an em dash, and the 48-character cut fell mid-word - and the architect spent three turns (~4 min at 2,000-4,000 output tokens a turn) on `ls`, `changed_since_sprint` and `glob` of the empty project. The directory is now the name before a spaced dash, colon or bracket, cut between words; an empty pinned project's snapshot says it is empty. Observed, not changed: on this model the specification took 17,332 of 20,000 output tokens in one call. run-d9642862 cancelled at 17:39 JST: directory, empty-project note and framework list all held, and the architecture review passed first time; but the sprint plan was handed back for "embedded", "sibling", "confirm" and "does" - the enumeration check (written for short success measures) was reading the intake's eight MVP feature *sentences*, added to the checklist by 2beaf2e, and "shows an empty list and does not error" made "does" a capability. An MVP feature now needs only a sprint assigned; auxiliaries and negations are not capabilities. (The "mobile" gaps were real: the plan said "phone".) The specification there took 19,611 of 20,000 output tokens - one more paragraph and it is cut off. The owner then switched back to gpt-oss on LM Studio; run-7cc2f3a6 started 17:47 JST. run-7cc2f3a6 cancelled at 17:59 JST: much faster on gpt-oss with the owner's thinking effort "medium" (sprint 1 built and two test rounds done in 10 minutes, 100-500 reasoning tokens a call), but 17.9% failed calls in the fix stages - mostly guards working (writes over unseen versions, deletes of another stage's tests, invalid JSON). The harness gap: `_edited` (edit_artifact, replace_lines) gave fewer notes than the write path, missing the three module-system notes, so `replace_lines` turning a test's imports into `require(...)` under `"type": "module"` went through in silence and the next round reported "require is not defined". The edit path now gives them. Also seen: a fix stage set `"jest": "echo 'skipped'"` to get past a failing runner; a later stage restored it - watch for it sticking. run-c49e59b0 cancelled at 18:15 JST: sprint 1 accepted and sprint 2 under test within 11 minutes; 21.7% failed calls, almost all guards (parse refusals, stale line numbers, writes over unseen versions). The harness gap: `replace_lines` refused `expect_start=" 1 | export class ..."` - the `N | ` gutter this module itself prints, copied back - though `find` already forgave gutters; pins now do too when every line sent carries one and none matches as sent. The stack there chose web components, so the tests ran a hand-written `HTMLElement` polyfill under Node - model choice, watch it. run-f1a81dbe cancelled at 18:31 JST: sprint 1 accepted in 10 minutes, 15.9% failed calls (guards); but the framework list read "html5, css3, javascript, css, html, ..." - the extraction returned versioned names, neither was stored, and notes were generated for both (spec trivia: `<canvas>`, `<video>`, animations, Flexbox) and appended to every prompt beside the seeded `html` and `css`. A name with a version written onto it is now read as the known name, in the model's answer and the word match, and preferred even when the versioned name is stored. No run since: at 22:44 JST LM Studio had been restarted with no model loaded, so the next run waits for the owner to load one. At 22:55 JST the owner pointed the settings at their unsloth server (`unsloth/Qwen3.6-35B-A3B-MTP-GGUF`, port 8888, context 126,000; the first save read port 888 and was corrected a minute later - check the address answers before starting). run-3bfa5ffc started 22:56 JST on build 1024cc3. run-3bfa5ffc cancelled at 23:09 JST, on its fourth architect pass with 0 failed calls: the stack named `node:test` alone, the workflow recorded "node:test for the logic, Playwright for the page" in the field, and the stage's rationale - left as written - still said "Playwright is not needed ... verified by opening the single HTML file in a browser". The architect specified Playwright as the field says; the reviewer raised stack-against-specification as blocking three reviews running, and the architect cannot edit the stack document. The correction now rewrites the rationale too (`the_rationale_for_the_corrected_runner`). When a review repeats one blocking finding, ask whether the stage it sends the work back to is able to change what the finding names. run-d749dad2 started 23:15 JST. run-d749dad2 cancelled at 23:37 JST: the rationale fix held (three reviews, each on a different real finding - editing deferred, a wrong toggle flow - and approval on the third), the sprint plan passed first time; then the lead's plan was handed back twice and dispatched "still not ready" because the sprint's scope said "task-store.mjs: createTask(), ..., store.read(), store.write()" and no work order "lists" `store.read` and `store.write` - the sprint-scope file check of 6ad21ff read any lower-case dotted name as a file. A name followed by `(` is now a call, and a name is a file only when its last part is an extension files are given (`file_kinds.FILE_EXTENSIONS`) or one the plan or workspace already uses. run-f79731fb started 23:44 JST. run-f79731fb FAILED at 00:58 JST (2026-10-02) in sprint 2's planning, after the cleanest sprint 1 of the day (architecture approved first time, no plan hand-backs, 4.8% failed calls, security and milestone review passed): the lead's answer was cut off at the 20,000-token output limit inside its tool call, the half-written call stayed in the conversation, and llama-server refused every request that carried it - 500 "Failed to parse tool call arguments as JSON" - so the nudge, the retry and the tools-withheld recovery call all failed in milliseconds. LM Studio accepted such a history. The request payload now drops a cut-off call nobody answered (`without_cut_off_tool_calls`). An instant 500 from the model server is the request being refused, not the model failing: read the error text. run-d7970a62 cancelled at 01:15 JST: the sprint plan was handed back for "confirming" - the enumeration check read "(verified by refreshing the browser and confirming data remains)" as a list; a noun paired with an -ing form is no longer one (`6d26d8e`). run-233fdf7c cancelled at 02:57 JST after 98 minutes: sprint 1 was the cleanest yet (no defects in the first test round, 1.5% failed calls), then the lead's sprint-2 replies ran to 13,000-17,500 tokens each while the server slowed from ~57 to ~14 tokens a second, and a reply that needed more than twenty minutes was cut off by the proxy in front of the unsloth server (HTTP 502 at exactly 1,200 s). The client resent the identical request, twenty minutes each. The local model is now built with the client's retries off and retried by `CompatibleChatOpenAI._generate`: at once and unchanged for a quick failure, with half the reply ceiling after a slow proxy cut-off (`7e53804`). If it recurs, the owner's levers are `model_max_output_tokens` and `thinking_effort`. run-dc13431f cancelled at 07:34 JST at the owner's request (changing the model), 270 minutes in and healthy: the halved-reply retry fired twice and both retries answered (13 and 4 minutes), sprint 1 passed its test round with no fix stages, 2.2% failed calls; the server ran at 10-13 tokens a second throughout. The owner then set `zai-org/glm-4.7-flash` on LM Studio; run-363bd192 cancelled 08:24 JST on 2026-10-02 (a reviewer lost a whole reply to reasoning on every visit; fixed 84b9a56); run-9ef59e5c cancelled 09:30 JST at the user's request to deploy ba720b2; run-c5acd7bb cancelled 09:45 JST (an additions-only patch sent as replace_lines content was not named as one; fixed 7c3aa8b); run-948bd1f6 cancelled 10:21 JST (line edits whose content repeated the lines around their range were refused; fixed cf16d08); run-2074e59f cancelled 10:37 JST (stack check accepted 'Custom asserts'; fixed bc869b7); run-398810a8 cancelled 10:52 JST (a test round deleted the project's manifest; fixed 9d8301c); run-da4ff621 cancelled 11:29 JST (probes named like tests could not be deleted; fixed a8c417e); run-8cf43ce9 FAILED 13:33 JST (milestone review on its last revision; one finding was contradicted by the command record, and the reviewer was told a test-only import broke the brief; fixed 995c7d7 and f8ba8e7); run-bb2ef75e cancelled 13:55 JST (a bulleted list in one list entry read as one success measure; fixed a00f87b); run-77f93adf cancelled 14:11 JST (npm --prefix read as a package install; patch wrapper line not named; fixed e1c4d46); run-4853e2ea FAILED 14:20 JST (architecture review required new sections the schema cannot hold; fixed ba9447f); run-792647ca cancelled 14:57 JST (range widening over a bare closing brace damaged package.json; fixed 309045a); run-c96abb2a cancelled 15:14 JST (failed sprint's record missing its last round; fixed 07e0ec1); run-23143d2c cancelled 16:00 JST (a hanging test re-run at the full limit each time; fixed c45e5e9); run-2c84a7c7 FAILED 16:18 JST (re-plans of a failed sprint were not told what it left open; fixed cf5b1f8); run-f5c5a91c FAILED 17:02 JST (sprint 2 never passed its unit tests in four attempts; no harness fault found, no code change); run-0c1f6fe6 cancelled 17:13 JST (unread whole-file writes refused and resent; the refusal now shows a short file; fixed 326e733); run-64f67f08 cancelled 17:32 JST (debugging scripts left in the product; now cleared before each test round; fixed dc791d4); run-959a2ddd cancelled 17:45 JST (a file written into the project directory nested in itself; fixed f4c2453); run-f8b894b7 FAILED 18:09 JST (milestone review; a test-only import was reported as a brief violation, and the manifest was moved to the workspace root; fixed c7ec3a4); run-516233e3 cancelled 18:29 JST (shortened line pins reported as not in the file; fixed 7620fb7); run-922a489e crashed the worker 18:51 JST (a command's process tree used all the container's memory; tree watchdog added 3e48fca; a cancelled orphan stayed running, fixed 9807ec2); run-e14ed41a FAILED 19:48 JST (milestone review rightly rejected a broken page; fixes ran out; no harness fault, wording tidy-up 0de9f94); run-70873082 cancelled 20:11 JST (end_line one off a correct expect_end; fixed 047836a); run-b39bb1d9 FAILED 20:23 JST (512 MB heap cap aborted the suite; a failing suite reported as passing; fixed beea8b0); run-fb20f62a cancelled 20:41 JST (accepted sprint filed as changes_required; fixed 39d8627); run-5063a1c9 FAILED 21:36 JST (sprints 1-2 accepted; sprint 3 never passed its regression tests in four attempts; no harness fault, no code change); run-3ba3901b COMPLETED 21:53 JST but not clean (a test round's defects_report.md shipped in the product; fixed f35b528); run-7302cbd7 cancelled 22:41 JST (a runner's setup file classified as product code; fixed 920bdae); run-542375ee FAILED 23:07 JST (review claimed the suite fails while its last run passed 18/18; fixed c063e38); run-623515a9 COMPLETED 23:41 JST but not clean (style.css shipped with an unpaired brace; fixed c14f0ab); run-5177a220 cancelled 23:58 JST (stack check accepted 'Custom harness'; fixed a64e3d8); run-269e3173 FAILED 00:13 JST on 2026-10-03 (an exhausted sprint failed the run with no re-plan; fixed 329aed4); run-9adf39e4 COMPLETED 00:35 JST on 2026-10-03 but the product fails the brief (no way to edit a task; accepted by the last review); new cross-file check 0fde5df; run-6c7a4f0f COMPLETED 00:50 JST on 2026-10-03 with a product that only adds tasks (garbled one-sprint plan built from; fixed 0a83c80); run-4baddfaa cancelled 01:21 JST (line range with both pins right and both numbers off; fixed 363e14a); run-fa7a963b-7a23-45ce-8533-1a69965838b8 started 01:22 JST on gpt-oss-20b. Known throughput cost, not a bug: in parallel mode with auto-approve every gated call pauses and the pauses drain one per superstep, so each write or command waits 60-100 s behind its siblings' (measured run-63904b9a after the oldest-first fix). The auto-approve loop in `runner.py` is also where per-stage gate budgets and loop detection live, so removing the pause is a redesign, not a fix. History: (run-fb102e16 looked clean, but the product audit found a sprint-summary counting bug and a missed empty-title-on-edit defect; both fixed, count reset. The next run failed 9 minutes in on `server closed the connection unexpectedly`: a worker forked by the Celery parent shared the parent's Postgres pool; fixed. run-ebde9fa1 completed, 2.4% failed calls, product tests 72+8 pass and match the summary, but it took three mid-run fixes and the product audit found the review accepting "full keyboard accessibility" while editing is pointer-only, and an edit path skipping the add form's description limit; count still 0) |
| current run | `data/loop/current_run.txt` (git-ignored; `loop.sh status`) |
| database | Postgres data lives in the repo at `./data/postgres` (bind mount, git-ignored), database `langchain`, table `runs` keyed by `run_id` |
| transcripts | `/app/data/transcripts/<run-id>*.jsonl` inside the worker (`appdata` volume) |
| workspaces | `runs.repo_root`, e.g. `/app/data/workspaces/default/workspace-<run-id>` |

Healthy numbers on recent brief_low runs: 1.7-6% of tool calls failed (most of
those guards working), 0 duplicate executions, 8-19% redundant reads, three or
fewer architecture reviews.

### 0.3 The scripts

All in `scripts/loop/`, all documented in their own headers. The Python ones
run **inside the worker** and are piped in on stdin, so nothing is copied into
the container and a redeploy (which wipes the worker's `/tmp`) costs nothing.

| script | what it is for |
|---|---|
| `loop.sh` | the one entry point: `status`, `start [brief]`, `wait [minutes]`, `cancel [run-id]`, `audit`, `stage <name> [HH:MM]`, `reads`, `product [run-id]`, `deploy`, `suite`. Run with no argument for help. |
| `audit_live.py` | the 15-minute check: failure rate, duplicate executions (must be 0), redundant reads, stage order, failures per stage, failure signatures with an example each. Says *where* to look. |
| `stage_trace.py` | every model reply, tool call and result of one stage, in order. Says *why*: the model's words just before a failed call usually name the harness message it misread. `HH:MM` is UTC (JST - 9) and skips earlier sprints of the same stage name. |
| `product_audit.py` | the product half of the audit (`loop.sh product [run-id]`): the product files, code lines per file (counted as the brief's line cap is), the intake's acceptance criteria, what the harness claimed (sprint summary counts, milestone acceptance evidence), and the product's own test command run once. Prints evidence; the reading is the checklist in 0.4.1. |
| `redundant_reads.py` | re-reads by (stage, file) and which notice answered them. One pair with many re-reads has twice been a misleading harness message. |
| `scripts/audit_run.py` | the older whole-run audit (predates this loop): separates *refusals that prevented damage* from *failures that cost the run*, and runs the cross-file checks over the product. Use it on a finished run; see section 5. |

`loop.sh start` logs in with `LOOP_USER` / `LOOP_PASSWORD` from the
environment; no credential is stored in the repository. The loop's operator
account (currently `harness-test`) exists only in the local database and must
be deleted when the loop ends. On a fresh database, create one:

```sh
docker exec langchain-app-1 python -m app.server.manage create-user <name> \
  --password <password> --role operator
```

### 0.4 One iteration, step by step

```sh
export LOOP_USER=harness-test LOOP_PASSWORD=...        # the operator account
scripts/loop/loop.sh start                             # prints the run id and JST start time
scripts/loop/loop.sh wait 18                           # prints "next report by HH:MM JST", then the audit
```

Then, for every failure signature and every stage that looks wrong:

1. `loop.sh stage <stage>` and read the replies around the failure. Decide:
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
5. `loop.sh deploy`. A run that already has a finding may be resumed on the
   new code (orphan recovery does it); a run that could still be clean should
   be left to finish first.
6. When the run ends, **audit the generated product before counting the run**
   (0.4.1). Then: if nothing was found in the run or the product, count it
   toward the gate; otherwise the count is 0. `loop.sh start` the next one.

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
4. **Hallucinations - every claim the harness or an agent made is true**:
   sprint summary counts against the real test result (run-fb102e16's
   summaries said 36 test cases for 36 unit + 10 browser tests - a harness
   counting bug), milestone-review acceptance evidence against the code it
   cites, README/docs against what exists, "tests added" against the files.
5. **Classify each finding.** A harness document or check that is wrong is a
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
- The full suite takes about 2.5 minutes here: roughly 7,330 pass, 16 skip,
  and three `tests/test_codebase_seeding_api.py` tests fail for want of S3
  credentials. Any other failure is real - unless `src/` was edited while the
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

- Tools are still offered when command execution is disabled; the duplicate
  `test/` and `tests/` suites seen in run 71d58b84 are not addressed.
- Commands run without a shell, so a wildcard argument reaches the program
  as written: `node --test tests/unit/*.js` fails with "Could not find" on
  Node 20, which does not expand it itself. 4 calls in 25 runs (to
  run-ccc66650), each recovered on the next call by naming the files.
  Expanding wildcards in the harness would also rewrite arguments that are
  patterns on purpose (a `grep` regex), so it is left until it costs more.

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

---

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
