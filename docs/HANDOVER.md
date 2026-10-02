# Handover - the harness improvement loop

Written 2026-10-01 16:20 JST and last updated 07:41 JST (2026-10-02), for the next Claude Code session (a different
account on a different desktop) and for the owner. Read this first, then
`docs/monitoring-handover.md` §0 (mechanics and the full gate history),
§0.4.1 (product audit checklist), §0.7 (how a sprint runs) and §0.9 (where a
run's time goes).

Your previous session's memory does not travel with the account. Everything it
held that is not a secret is in this file.

## 1. The standing instruction

The owner wants a loop that never stops on its own:

1. Start a run (`scripts/loop/loop.sh start tests/brief_low.md`).
2. Audit it: transcripts, worker logs, the database, tool calls - especially
   failed and unnecessary ones.
3. Fix what you find **technology-agnostically**: the harness must build any
   product in any language or framework. Never fix for one stack, one product
   or one run.
4. Add tests, run the full suite (`loop.sh suite`).
5. Commit, push (`git push main harness-hardening-session` - the remote is
   named `main`), deploy (`loop.sh deploy`), start the next run.

**Gate.** Two consecutive clean runs on `tests/brief_low.md`, then two on
`tests/brief_medium.md`, then `tests/brief_high.md`. A run is clean only if
nothing needed fixing *and* the product audit passes. Any fix resets the count.
**Current count: 0 of 2 on brief_low.**

**Early stop.** A bug found in a run's first 40 minutes: cancel the run
(`loop.sh cancel`), fix, deploy, start again - do not wait for it to finish. A
major harness bug or gap at any time: cancel immediately.

**Cadence.** Check about every 10 minutes during a run's first 40 minutes, then
about every 18 (`loop.sh wait 10` / `loop.sh wait 18` in the background - one
wait, not a per-minute monitor). Every time you start a wait, tell the owner
when the next check reports, **in JST** (containers and transcripts log UTC;
JST = UTC+9).

**Product audit, every run, at the end.** `loop.sh product <run-id>`, then read
every product source file against the brief (§0.4.1). Check every brief
feature is built *and reachable by a user*, edge inputs, constraints, that the
tests exercise the real code, and that every claim in the sprint summaries and
the milestone review is true.

**Code rules.**
- No run ids in code, comments, prompts or tests. Evidence goes in commit
  messages and docstrings as "one run".
- No language- or framework-specific instructions in code. They belong in
  `src/app/plugins/seed.py` (the `plugin_instructions` table, injected
  dynamically). Rules for agents must be product-agnostic too: no examples
  from the test brief (to-do, task, add form), no UI-only words (button, click)
  in rules meant for every product. Each new prompt rule gets a test that bans
  such words.
- Preserve the owner's features: dynamic agent-instruction injection, the
  parallel/linear execution toggle (settings), the sprint summary, and the
  work orders / document templates / Sprint Record (§0.7). Fix them where
  wrong; never remove them.
- The CRITERION severity policy (minor vs blocking grading) awaits the
  owner's decision - do not change it on your own.
- Use the LangChain docs MCP server when changing LangChain/LangGraph behaviour.

**When the shell fails** for an infrastructure reason, stop retrying, schedule
a check about 10 minutes later, and resume. Order when it returns: deploy the
pending fix and start the next run first; commit and push afterwards. A git
step that fails must never stop the testing.

## 2. Where it stands (2026-10-01 16:20 JST)

| | |
|---|---|
| branch | `harness-hardening-session`, last code commit `423bef1`, pushed to `https://github.com/marunsct/DevFlow.git` |
| deployed | yes - the running image matches `423bef1` (it carries the TypeScript compiler 6.0.3 and the tree-sitter grammar pack) |
| current run | `run-23fce753-5bd9-4a48-a248-e8e01ea4d2fe` (see `data/loop/current_run.txt`), started 07:28 JST (2026-10-03) by the loop account, `brief_low.md`, auto-approve on, on gpt-oss-20b at LM Studio (the user switched back from glm-4.7-flash). run-1572742d was cancelled at 07:26 JST on 2026-10-03, 14 minutes in (a line edit at the line after a file's last was refused as "not a range" / "does not exist" where it could only mean add at the end; fixed `423bef1`). On that run the sprint fold worked (two setup sprints folded, three sprints left) and the Jest guidance worked (the test script was the flagged one, and no file imported a second runner). run-ac6af679 FAILED at 07:03 JST on 2026-10-03, one minute in, at the sprint plan: the empty-sprint rule of `25b9bc3` sent back a plan that had assigned every measure, the answer came back with no coverage lines, and the run was failed on the worse plan (fixed `ad23516`: a sprint no measure is assigned to is folded into its neighbour by the workflow, with nothing asked again, and a re-asked plan replaces the first only if it leaves out no more). run-2dd6fede was cancelled at 07:00 JST on 2026-10-03, 15 minutes in (all three test rounds spent on Jest started plainly in a `"type": "module"` project, where every `import` in a test is a SyntaxError; the JavaScript seed guidance told every project to use `node --test` whatever its stack chose and said nothing of what Jest needs; fixed `4941ed6`: the guidance names the stack's runner and what each needs for ES modules, and a cross-file finding names Jest started without it). run-8fda442d was cancelled at 06:38 JST on 2026-10-03, five minutes in, to deploy two fixes found in the transcript of the run before it (a line edit's pin with its quotes escaped twice was reported as not in the file; a pin on the line above the one being rewritten was answered by moving the edit there - `9765f7c`), and one from its own planning stage (a plan handed back for never delivering the verb "runs" - `b5d9fdb`). run-938594b7 FAILED at 06:26 JST on 2026-10-03, ten minutes in, on its second milestone review (a test re-plan had spent one of the review's three revisions; of the last review's gating findings one was the next sprint's work, editing, and one was a path traversal in `serve.js`, the server the browser suite's configuration starts; fixed `e30ccd1`: re-plans are counted on `sprint_replan_count`, the later-sprint filter reads what a finding says is missing, and a finding about a test runner's own server is recorded as minor). run-838a8246 was cancelled at 06:14 JST on 2026-10-03, 28 minutes in, on the second attempt at its only sprint (its browser spec opened the page by `file://` and the page loaded its code as ES modules, which a browser does not run from disk; three rounds guessed at the timeouts and nothing named the cause - now a blocking cross-file finding, `b82f48e`). Its plan had been sent back once by the new empty-sprint rule and came back as one sprint. run-810f8156 was cancelled at 05:44 JST on 2026-10-03, 13 minutes in (the delete refusal's way out for a probe named the product's own module as the place to move a co-located test to - `data.test.js` to `data.js`; fixed `a22508e`). run-b9c91b67 was cancelled at 05:23 JST on 2026-10-03, ten minutes in (a testing stage replaced a failing 72-line suite with one `skip(...)`, was answered "edited", and `npm test` then exited 0 having run nothing; fixed `cd23f68`: such a change is refused, an all-skipped run is not recorded as passing, and the stage a work order gives a test file to is not refused as "another stage"). On that run the new runner-collision finding did reach its test round, and the plan was a single sprint. run-8647e985 FAILED at 04:55 JST on 2026-10-03 on `363e14a` (milestone review on its last revision: three real findings - the form never called addTask, no edit control - and one the harness should not have let gate, that the test runners in devDependencies break the brief's rule on dependencies, which the check on disk had told the reviewer was not a finding). A root-cause study of the last 46 runs followed, at the user's request: 253 of 400 reported defects (63%) were about the tests and their setup, not the product; run-fa7a963b's three hours were the unit runner loading the browser specs (both collect `*.test.js`), 220 s per `npm test`, 76 times. Fixed together in `25b9bc3`: a defect a failing test command already catches needs no new test; every language is parsed at the write (TypeScript by its compiler; TOML/YAML/XML; page scripts; Java, Go, Rust, Ruby, PHP, Lua by grammar - the tier measured on ~4,000 real files); a runner loading another runner's files, a unit suite split between two runners and any file that does not parse are blocking cross-file findings; a sprint no success measure is assigned to is sent back once; the dependency finding above is recorded as minor. A second session (langchain-dd) audits read-only; this session drives. run-fa7a963b FAILED at 04:33 JST on 2026-10-03 on `363e14a` after 3 h 11 min with no harness fault found: sprint 1 was re-planned three times and its browser tests never imported the app module (a playwright.config.ts syntax error no stage found, then wrong import paths in the regression tests each fix added). run-9ef59e5c was cancelled at 09:30 JST at the user's request, healthy, to deploy `ba720b2`. run-c5acd7bb was cancelled at 09:45 JST (a patch of only '+' lines sent as `replace_lines` content was refused without being named as a patch, `7c3aa8b`). run-948bd1f6 was cancelled at 10:21 JST (24 line edits refused for breaking a file, most because the content repeated the lines just outside its range, `cf16d08`). run-2074e59f was cancelled at 10:37 JST (the stack check accepted 'Custom asserts' as a testing framework, `bc869b7`). run-398810a8 was cancelled at 10:52 JST (a test round deleted the project's package.json and could not write it back, `9d8301c`). run-da4ff621 was cancelled at 11:29 JST (a fix stage could not delete debugging scripts it had named like tests, `a8c417e`). run-8cf43ce9 FAILED at 13:33 JST (milestone review still required changes on the last revision of sprint 1: one real finding, the Playwright run never passed, and one the command record contradicted; fixes `995c7d7` and `f8ba8e7`). run-bb2ef75e was cancelled at 13:55 JST (four success measures sent as one bulleted list entry were read as one measure, `a00f87b`). run-77f93adf was cancelled at 14:11 JST (`npm --prefix <dir> install` refused as installing a package; a patch wrapper line in an edit not named, `e1c4d46`). run-4853e2ea FAILED at 14:20 JST (the architecture reviewer required new sections the specification's schema cannot hold, six revisions running, `ba9447f`). run-792647ca was cancelled at 14:57 JST (the range-widening rule from `cf16d08` widened over a bare closing brace and left package.json valid but wrong, `309045a`). run-c96abb2a was cancelled at 15:14 JST (a failed sprint's record left out the test round that ended it, `07e0ec1`). run-23143d2c was cancelled at 16:00 JST (a test with an endless loop was re-run at the full 300-second limit each time, `c45e5e9`). run-2c84a7c7 FAILED at 16:18 JST (sprint 1 re-planned three times by a lead never told what the failed attempt left open, `cf5b1f8`). run-f5c5a91c FAILED at 17:02 JST on `cf5b1f8` with no harness fault found: sprint 2 could not pass its own unit tests in four attempts (test files sharing global mock state); the re-plan note worked and the lead did plan fixes. run-0c1f6fe6 was cancelled at 17:13 JST (a whole-file write over an unread file was refused with 'read it first' and resent unread, `326e733`). run-64f67f08 was cancelled at 17:32 JST (fix stages' debugging scripts left in the product run after run; the harness now clears them before each test round, `dc791d4`). run-959a2ddd was cancelled at 17:45 JST (a write into the project directory nested inside itself was accepted, `f4c2453`). run-f8b894b7 FAILED at 18:09 JST (milestone review on its last revision: one real finding, a Node-only import in browser code, and one the harness caused by calling a test-only import a brief violation; a stage also moved the project manifest to the workspace root; fixed `c7ec3a4`). run-516233e3 was cancelled at 18:29 JST (a shortened expect_start a few lines from where it was asked for was reported as not in the file, `7620fb7`). run-922a489e CRASHED THE WORKER at 18:51 JST: the product's npm test forked workers that together used all the container's memory and the kernel killed the Celery worker (a command's whole process tree is now watched and stopped, `3e48fca`); the cancelled run then stayed 'running' because the resumed task returned on the cancel flag without recording it (`9807ec2`, test fix `37be917`). run-e14ed41a FAILED at 19:48 JST with no harness fault found: sprint 1 passed weak tests, the milestone review correctly found the page missing its form and loading a main.js that does not exist, and the fixes ran out (only a wording tidy-up followed, `0de9f94`). run-70873082 was cancelled at 20:11 JST (line edits with a correct expect_end and an end_line one off were refused, a dozen in one sprint, `047836a`). run-b39bb1d9 FAILED at 20:23 JST (the harness capped each Node process at 512 MB of heap and the suite aborted with exit 134; two test rounds reported that as passing; fixed `beea8b0`, which also gives the process-tree watchdog a budget from the container, not the per-process ceiling). run-fb20f62a was cancelled at 20:41 JST (a sprint the workflow accepted was filed with a review reading changes_required, `39d8627`). run-5063a1c9 FAILED at 21:36 JST on `39d8627` with no harness fault found: sprints 1 and 2 were accepted, sprint 3 failed its own regression tests through four attempts. run-3ba3901b COMPLETED at 21:53 JST in 17 minutes on `39d8627` - the first completed run of the day - and was NOT clean: the product meets the brief (261 code lines, 4 unit and 5 Playwright tests pass), but a test round's defects_report.md shipped in the project (fixed `f35b528`), sprint 2's summary counts 5 test cases where the product has 9 (it reports the last test command only; left as is), and editing accepts an empty title (a product defect the reviews missed). run-7302cbd7 was cancelled at 22:41 JST (jest.setup.js was classified as product code and refused to the testing work order seven times, `920bdae`). run-542375ee FAILED at 23:07 JST (the milestone review said the test suites fail, from reading a file; npm test passed 18 of 18 and the ledger said so; fixed `c063e38`). run-623515a9 COMPLETED at 23:41 JST in 28 minutes on `c063e38` and was NOT clean: the product meets the brief (257 code lines; 13 unit and 8 Playwright tests pass; editing rejects an empty title), but style.css shipped with a stray closing brace that drops the next rule (stylesheet braces are now checked, `c14f0ab`), RESPONSIVE.md describes CSS that is not in the stylesheet, and an unused e2e-test.html shipped. run-5177a220 was cancelled at 23:58 JST (the stack check accepted 'Custom harness' as a testing framework, `a64e3d8`). run-269e3173 FAILED at 00:13 JST on 2026-10-03 (a sprint out of remediation attempts failed the run outright, with no re-plan and no Sprint Record, because a passing round with a defect still open had used the last attempt unmarked; fixed `329aed4`). run-9adf39e4 COMPLETED at 00:35 JST on 2026-10-03 in 17 minutes and was NOT clean: the PRODUCT FAILS THE BRIEF - there is no way to edit a task (app.js listens for a 'taskEdited' event nothing dispatches), a task's description is stored and never shown, and 'npm run e2e' finds no tests - yet 24 unit tests pass and the last review accepted it. A cross-file check for listeners on events nothing dispatches was added (`0fde5df`); it reports this product. run-6c7a4f0f COMPLETED at 00:50 JST on 2026-10-03 in 9 minutes and the PRODUCT FAILS THE BRIEF: only adding a task works. The sprint plan arrived as one sprint with the rest of its JSON inside 'in_scope' strings and no deliverable assigned; it was built from, and edit, delete and filter exist only as exports nothing the page loads uses. Fixed `0a83c80`: such a plan is refused, a plan that assigns nothing twice fails the run, and a required action only unreached exports perform is a blocking cross-file finding. run-4baddfaa was cancelled at 01:21 JST (a line range with both pins right and both numbers off was refused with advice that would have replaced the wrong lines, `363e14a`). run-363bd192 was cancelled at 08:24 JST: the architecture reviewer lost a whole 25,000-token reply to reasoning on each of three visits (`84b9a56`). Cancelled today, each for a harness bug found in its first 40 minutes: run-b69802cd 16:28 (framework instructions, `a754eb7`), run-391a8b68 16:58 (empty project, directory name, `904ecf8`), run-d9642862 17:39 (MVP sentences word-checked, `c0fea69`), run-7cc2f3a6 17:59 (edit path missing the module-system notes, `ce4f12d`), run-c49e59b0 18:15 (a copied `N | ` gutter in a `replace_lines` pin, `ae2e040`), run-f1a81dbe 18:31 (`html5`/`css3` got generated notes, `1024cc3`), run-3bfa5ffc 23:09 (the stack document argued against the runner the workflow had recorded in it, `acf55ea`), run-d749dad2 23:37 (`store.read()` in a sprint's scope read as a file no work order lists, `6df0d5f`). run-f79731fb FAILED 00:58 on 2026-10-02 after a clean sprint 1 (a tool call cut off at the output limit stayed in the history and llama-server refused every later request, `8c856b0`). A session heartbeat (CronCreate, every 15 minutes) now re-prompts the loop after a failed turn such as an API 529; it dies with the session, so recreate it |
| model | changed by the owner at 07:41 JST on 2026-10-02: `zai-org/glm-4.7-flash` on LM Studio, `http://host.docker.internal:1234/v1`, `thinking_effort` medium, execution mode **parallel**, context 176,000, max output 20,000. Before it: `unsloth/Qwen3.6-35B-A3B-MTP-GGUF` on the unsloth server (:8888, key required, a proxy that cuts a reply off at 20 minutes), gpt-oss-20b and qwen on :9090. To check that the configured model is served at the configured address with the harness's own key, run the snippet in section 5 inside the worker |
| gate | 0 of 2 on brief_low |

Runs b69802cd, 391a8b68 and d9642862 were on qwen; the current one is back on gpt-oss. Expect behaviour the gpt-oss runs did
not show, and separate "the model did something odd" from "the harness let it"
before fixing. The reasoning switch is measured once per endpoint and model and
logged by the worker as `Reasoning switch for ...`; check it chose sensibly.

**What `2beaf2e`, `a754eb7`, `904ecf8`, `c0fea69` and `ce4f12d` changed - verify them on this run:**
- An `edit_artifact`/`replace_lines` result now carries the same
  module-system notes as a write (CommonJS under `"type": "module"`, etc.).
- A `replace_lines` pin copied with the harness's own `N | ` gutter is
  accepted (`ae2e040`).
- `docs/technology_stack.md` does not argue against its own testing field:
  when the worker logs "Stack selection named ... recording ...", the
  rationale must not say the browser runner is not needed (`acf55ea`), and
  the architecture review must not loop on that contradiction.
- A "Milestone plan is not ready" warning names real files only: a method
  such as `store.read()` in the sprint's scope is not a file (`6df0d5f`).
- The framework list holds `html` and `css`, never `html5` or `css3`
  beside them (`1024cc3`). Two generated rows named `html5` and `css3`
  are still in `plugin_instructions`; they are no longer selected.
- A sprint plan is handed back only for a success measure's own list items
  (an MVP feature needs only a sprint assigned), and never for a function
  word such as "does" - check the worker's "Sprint plan left success
  measures" warning, if any, names real capabilities.
- The project directory is the product's name alone, cut between words
  (it was `...-single-page-tas`), and early stages do not `ls`/`glob` an
  empty project - the snapshot now says it is empty.
- The worker's "Framework instructions resolved for this stack: ..." line
  must name only what the stack chose - no framework the stack document
  rejects, and no language that appears only as a tool command.
- The sprint planner's checklist now holds the intake's MVP candidates after
  its success measures, each to be assigned a sprint. In
  `docs/sprint_plan.md` every MVP feature should have a coverage line.
- A defect whose affected files are all tests or throwaway scripts
  (`file_kinds.is_scratch`) needs no regression test and is not charged to the
  remediation budget; the fix stage is told to delete a debugging script and
  to fix a test in place. Watch for `defect_fix_*` stages still writing
  "regression tests" for probes, and count `tmp_*`, `*debug*` and `*.probe`
  files in the final product.
- A `replace_lines` refused for a parse error whose content carries `-`/`+`
  diff markers says so.

**The last completed run, `run-e3985f85`** (gpt-oss-20b, 144 min, accepted):
NOT clean. The brief's "Mark tasks as complete/incomplete" was never built,
and the product shipped about 21 debug scripts and debug suites. Both are
addressed by `2beaf2e`. Also seen and not changed: the milestone review had the
whole brief and still accepted a product missing a brief feature - a model
judgement miss. If it recurs, look for a deterministic check.

## 3. Setting up on a new desktop

1. `git clone https://github.com/marunsct/DevFlow.git` and
   `git checkout harness-hardening-session`. Name the remote `main`
   (`git remote rename origin main`) so the push command above works.
2. **`.env`** - copy it from the old machine yourself, by a private route. It
   holds secrets: never commit it, print it, or paste it into a chat. (The old
   machine's `/home/arun/harness-handover-2026-09-19.zip` contains a `.env` too
   - treat it the same way.)
3. **Database** - Postgres data lives in `./data/postgres` (git-ignored). Copy
   that directory across to keep runs, settings and users, or start fresh: a
   fresh database's admin password comes from `ADMIN_PASSWORD` in `.env` or is
   printed once in the app log. Transcripts and workspaces live in the Docker
   volume `appdata` and do not travel; they are only needed for history.
4. `docker compose build app worker && docker compose up -d`. Containers:
   `langchain-app-1`, `langchain-worker-1`, `langchain-db-1`, `langchain-redis-1`.
5. Model server: the owner sets `model_name`, the base URL and the reasoning
   settings in the admin UI's settings. A model on the host is reached from the
   containers as `host.docker.internal`.
6. Loop operator account (do not use the admin account for the loop):
   `docker exec langchain-app-1 python -m app.server.manage create-user harness-test --password <choose one> --role operator`,
   then `export LOOP_USER=harness-test LOOP_PASSWORD=<it>` in your shell. Never
   commit the password. Delete the account when the loop ends.
7. Tests: a Python venv at `.venv` with the project installed, and Node on the
   host (some tests run `node --check`). Then `loop.sh suite`.

## 4. Commands

```sh
scripts/loop/loop.sh status              # current run + anything live
scripts/loop/loop.sh start [brief]       # needs LOOP_USER / LOOP_PASSWORD
scripts/loop/loop.sh cancel [run-id]
scripts/loop/loop.sh wait [minutes]      # blocks until the run ends or N minutes, then audits
scripts/loop/loop.sh audit [run-id]      # failures, redundant reads, stage order
scripts/loop/loop.sh stage <stage>       # trace one stage
scripts/loop/loop.sh timing [run-id]     # model vs tool time, reasoning share
scripts/loop/loop.sh product [run-id]    # the generated product, the harness's claims, its own tests
scripts/loop/loop.sh deploy              # rebuild, restart, verify the image matches the tree
scripts/loop/loop.sh suite               # full suite -> data/loop/suite.log (~2.5 min)

docker exec langchain-db-1 psql -U postgres -d langchain -tAc "<sql>"   # tables: runs, runtime_settings, ...
docker compose logs --since 20m worker   # model calls, stage failures
```

The current run id is in `data/loop/current_run.txt` (git-ignored). A run the
owner starts from the UI is not written there: put its id in by hand. A run
started by the admin account may refuse a cancel from the operator account; if
so, ask the owner to cancel it from the UI.

## 5. Things that bite

- There is no source mount: a restart deploys nothing. A deploy wipes
  `docker logs` and the worker's `/tmp`.
- Orphan recovery resumes any `running` run after a deploy. Cancel a
  superseded one, or it competes for the worker and the model server.
- Do not edit `src/` while the suite runs (tests that read source see shifted
  lines and fail). Do not edit `loop.sh` while a `wait` is running.
- Suite baseline: about 7,855 pass, 16 skip, and three
  `tests/test_codebase_seeding_api.py` tests fail for want of S3 credentials.
  Any other failure is real.
- Auth is a form-encoded `POST /api/auth/token`; there is no JSON login.
- Transcript `model_request` records are windowed; use the `carried` offset
  for absolute message positions.
- Never start a run while the model server's loaded model differs from
  `runtime_settings.model_name`. The owner changes both without saying so:
  compare them before every `loop.sh start`. Check passively, with
  `curl <base url>/v1/models` - `lms ps` wakes LM Studio's background service
  when the app is closed. With no model loaded, do not load one: leave one
  long background watcher on that endpoint, on `runtime_settings` and on
  live runs, and start when they agree.
- Scheduled heartbeats and background waits belong to the session. After a
  restart there are none: start the wait (or the watcher) again.
- A model server that needs a key answers 401 to a bare `curl`. Ask through
  the harness's own settings instead, inside the worker, and print names only:

  ```sh
  docker compose exec -T worker python - <<'PY'
  import json, urllib.request
  from app.models import _runtime_settings
  s = _runtime_settings()
  r = urllib.request.Request(s.openai_base_url.rstrip("/") + "/models",
      headers={"Authorization": f"Bearer {s.openai_api_key}"} if s.openai_api_key else {})
  served = [m.get("id") for m in json.load(urllib.request.urlopen(r, timeout=10)).get("data", [])]
  print(s.model_name, "at", s.openai_base_url, "served:", s.model_name in served)
  PY
  ```
- A test must reproduce the state production really produces. Prove a new
  test fails on the old code before trusting it.

## 6. Security rules

- Never print or copy secret values from `.env`. Change only the keys that
  need changing, and back the file up first.
- Do not kill the owner's GPU or model processes (llama-server, Bonsai,
  unsloth, the server on port 9090, LM Studio), and do not take over the
  port-8888 server. Do not change the owner's model-server settings.
- Never add knowledge or documentation credentials to
  `sandbox._ENV_PASSTHROUGH`.
- Do not read or reset the admin password, use the admin account, escalate
  the loop account, or write the settings table directly.
- Credentials once committed in removed `scratch/` files are still in git
  history. Never repeat them; recommend rotation; rewrite history only if the
  owner asks.
- API keys that appear in `ps` output or logs are never repeated.
- For GitHub tokens, the owner uses their own terminal.
- Never route shell work through another command-running tool to get around
  the safety check.

## 7. Open and parked

- **Throughput** (§0.9): a brief_low run takes 2.5-3 hours, nearly all of it
  model time. Proposals measured but not built: two-step lead planning,
  per-role reasoning effort (the owner's setting), one sprint for a small
  brief (conflicts with the product design).
- In parallel mode with auto-approve, gated calls pause and drain one per
  superstep - a redesign of the runner's auto-approve loop, not a fix.
- Parked (§0.5.1): wildcard arguments are not expanded (commands run without
  a shell); tools are offered when command execution is disabled; duplicate
  `test/` and `tests/` suites.
- Delete the `harness-test` operator account when the loop ends.
