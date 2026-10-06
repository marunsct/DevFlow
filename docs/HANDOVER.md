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

1. Start a run (`scripts/loop/loop.sh bench <name>` from `benchmarks/`, or
   `scripts/loop/loop.sh start <brief>` for a brief with no hidden tests).
2. Audit it: transcripts, worker logs, the database, tool calls - especially
   failed and unnecessary ones.
3. Fix what you find **technology-agnostically**: the harness must build any
   product in any language or framework. Never fix for one stack, one product
   or one run.
4. Add tests, run the full suite (`loop.sh suite`).
5. Commit, push (`git push main harness-hardening-session` - the remote is
   named `main`), deploy (`loop.sh deploy`), start the next run.

**Gate (since the 2026-10-03 redesign, `docs/redesign-software-company.md`).**
A run is clean when its product scores 100% on its benchmark's hidden tests
(`loop.sh score`) and the run needed no harness fix; any fix resets the current
stage's count. Stages, in order (`benchmarks/README.md`):
1. `web-todo`: two consecutive clean runs.
2. `notes-api`, `wordstats-cli`, `textkit-lib`: one clean run each.
3. `fullstack-bookmarks`: two consecutive clean runs.
4. `tests/brief_medium.md`, then `tests/brief_high.md`, audited by hand as before.
Still read the product and the transcripts after every run: the score says
whether it works, not whether the harness wasted calls getting there.
**Current: stage 1 (web-todo), 0 of 2.**

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
| branch | `harness-hardening-session`, last code commit `cf4a1be`, pushed to `https://github.com/marunsct/DevFlow.git`. `docs/PRODUCT.md` describes the whole product. |
| deployed | the running image matches `cf4a1be` (deployed 08:25 JST on 2026-10-07). It adds: a dispute judges only the tests of criteria due by the sprint, and counts a named test only with a reason (`cf4a1be`); and, from `b1c4b41` (07:49): a control disabled on a condition is caught in any wording - any form of disabling and a condition word, either order (`b1c4b41`); and, from `6f58849` (07:12): a test that finds a list item (or a list, paragraph, generic) by a name sends the suite back, at review and on every round once locked (`6f58849`, verified in a browser: 0 matches); and, from `101991b` (06:56): release holds back while the project's own unit tests fail (`101991b`); and, from `f529bf1` (06:31): a dispute is judged once per failed attempt, not once per sprint (`f529bf1`); and, from `4506b51` (05:45): a disputed test is matched by its title too (`4506b51`); and, from `bf36b9d` (05:17): a new stage, `acceptance_dispute` - before a sprint whose attempt failed is planned again, once per sprint, the QA lead names the locked tests still failing that no product meeting the criterion could pass, and they go back to QA through the suite's repair (`bf36b9d`); and, from `3ccf6b5` (04:45): advice that disables a control until something is done - "enabled only when" too - is left out when the advice is read and never counted as owed (`7592d33`, `3ccf6b5`); and, from `0d35c1a` (03:32): a lead that answers nothing about carried work is asked again once before the sprint closes (`0d35c1a`); and, from `8e9b842` (02:41): an accessibility defect quotes what axe measured for each element - for contrast the two colours, the ratio and the ratio needed - proven with real Playwright on a product (`8e9b842`); and, from `c926823` (02:14): only a matcher on expect(...) counts as an assertion the runner must define - toString and the like no longer send a suite back (`c926823`); and, from `fd62bcd` (01:56): a specification line that disables a control until something is done goes back to the architect (`fd62bcd`); and, from `d0b1a2f` (01:31): a test that fails looking for its own change through a locator found by the text it replaced - the page showing the new text - reopens the suite for QA (`d0b1a2f`); and, from `635d470` (01:03): a plan that declines carried work because no test requires it is not ready, and one that would close the sprint is asked again once (`635d470`); and, from `19369b2` (00:21): a brief's interface section is numbered as acceptance criteria, line by line - web-todo now has 16 criteria, notes-api 18, textkit-lib 11 (`19369b2`); and, from `5680d34` (00:04): a control the brief names that the page shows disabled on load is a UI/UX defect, and advice may not disable one (`f4defca`); a test that asserts what a text-found locator finds does not show that text is sent back (`2a60ddf`); the lead is told an untested item is no reason to decline it (`5680d34`); the lead's decisions on carried work come first in the decision record (`8c8c321`); and, from `91418e4` (23:11): a defect the language service raised is checked again before a fixer is sent, and closed when an earlier fix resolved it (`91418e4`); and, from `284f3ca` (21:42): a milestone review's security finding gates only when the sprint's security review graded something high or critical (`1ad5047`); no copied read_file line-number gutter is written into a file - an edit's replace loses the gutter its find was matched without, and content numbered in order is written without it (`284f3ca`); and, from `dde0955` (21:12): a security finding naming only the harness's kept files is left out of the review handed on, the security reviewer is told data kept in its own user's browser is that user's, and advice may not add a rule the brief does not state that refuses or limits what a person may do (`dde0955`); and, from `07b8f88` (20:24): each specialist's findings are carried as one item, and a plan that finishes a failed sprint is not carried again what its first plan decided (`07b8f88`); and, from `dcb7703` (19:37): what the specialists find not built joins the sprint's findings as minor ones and is carried to the next sprint's lead, who takes or declines it even when that sprint's criteria already pass (`dcb7703`); and, from `06da143` (18:53): every line a suite finds a control by something no person sees is named in one round, not the first per file (`aed2c41`); a list item a model bulleted itself renders with one bullet (`06da143`); and, from `f23e586` (18:35): every control the brief names must be found by that name in the locked suite, and a suite that acts on whichever match comes first or finds a control by a CSS class, id or attribute is sent back to QA, which is now given the brief's control names up front (`117e7d6`); product code may not replace a method every browser defines, and an edit or write to a page whose newlines arrived as backslash-n is written with real newlines (`f23e586`); the owner's specialist requests, first live in this build: consultation before the specification (`d80064a`), UI/UX defects for an unstyled page or one wider than a phone (`9a6e733`), screenshots for a reviewer whose model reads images (`419516a`, `MODEL_READS_IMAGES`), testing and security & reliability advice (`5331020`), axe-core in every page pack (`e6d873c`), and a per-sprint check of adopted advice (`a1fa495`). Before them, `16161bf`: the harness's momentary files are kept out of every listing a stage sees (`16161bf`); a suite goes back to QA for tests the runner never collects or refuses (`a1684db`); a folded sprint's criteria are carried into its neighbour (`20e2ab8`); a bare number under a sprint's acceptance_criteria is its criterion (`af3678e`); a failed sprint is counted from the harness's latest measurement (`dc03b73`); a failed sprint is counted from the harness's latest measurement (`dc03b73`); a sprint keeps the criteria its plan names under `acceptance_criteria`, and a guess weighs the words that tell sprints apart (`f9ba962`); a sprint the run went on from without some criteria is recorded as such, with the counts it went on with (`fe470e5`); a browser suite is told to click a control that leaves the page (`fd8dd47`); a regressed test that no longer runs is described as gone, not failing (`7892bed`); a fragment written over a whole module is refused on the first send (`e4669d1`); code given to node --check is named as code (`db1f230`); and before them: a regressed unit test may be out of date, pinning behaviour the sprint replaces (`382d6b7`); a milestone plan made for a different sprint is sent back (`8f41dfa`, evidence corrected in `37ad3f4`: 2 of 889 stored plans, not this run); the harness's own records are left out of every name search for a stage (`529145f`); a defect an earlier fix in its round resolved is closed without a fixer (`64d9252`), and an earlier round's open defect the next round measures fixed is closed (`5ddec8f`); a repeated query is stopped under the budget warning and for every read-only tool (`155bf5c`); the suite no longer pings this host's model servers (`f9d5455`); a defect fixer is handed only a failing command's output that the same command has not passed since, read from every command tool (`eea20a9`); the thinking-off notice and log say it lasts the rest of the stage (`1c474c5`); and before them: everything through `fbaceab` (pace bound, the owner's six review items, benchmarks, Playwright guide, sprint-plan phrasing, node --test detection); a stage keeps its tools after a reply lost to reasoning (`b60b701`) and thinking stays off for the rest of that visit (`c5c00b5`, fixing a regression b60b701 caused); journal references without .log (`3ebf7dc`); not.toBeChecked() in browser guides (`d2f5416`); a call of a method no built-in type has is underlined (`a221020`); a locked suite that finds elements by a CSS selector on role is sent back (`c3f9284`); a test round's defects about later sprints' work are left to them (`663a2fb`); a cd into the project directory is dropped from verification (`1d06ea4`); a stage may delete a test file it created itself (`dc8c03f`); a sprint's revisions are not held to its scope's file names (`9c36688`); a sprint summary covers every plan it ran (`9e36d48`); CI snapshots key tests by file and name (`7be890a`); the acceptance suite tests a record changing state inside a view (`8a5aa61`); a repeated already-applied edit is treated as a loop (`a9feb1c`); QA is told a review finding about the product is not its to fix (`b01c3a4`); a criterion the suite tests is never deferred as not automatable (`d1668b1`), nor an id that is no criterion (`2b9d799`); CI keys tell same-named tests apart by their enclosing suites (`a68fafb`) |
| current run | `run-23928a49-48df-492b-9c82-91a72d0523ba`, `web-todo`, started 08:26 JST (2026-10-07) on `cf4a1be`, model `openai/gpt-oss-20b` on LM Studio :1234, auto mode. run-b801a757 (07:50) was cancelled at 08:21: the first live dispute was shown every failing locked test, the QA lead named nine bare - eight the next sprint's unbuilt work - and QA rewrote nine valid tests (`cf4a1be`). run-3ae10313 (07:13) was cancelled at 07:45 (`b1c4b41`). Last: `run-dedab9c1` (02:42-06:50) COMPLETED, benchmark 10/10, locked 15/18 with AC-5, AC-12, AC-15 deferred (three locked filter tests that add one item and expect two), unit 35/36 - released with `npm test` failing (`101991b`); not clean: a lead that answered nothing about carried work (`0d35c1a`), disabling advice carried as owed (`7592d33`, `3ccf6b5`), unpassable locked tests (`bf36b9d`, `4506b51`, `f529bf1`), all deployed mid-run. Before it: run-a96fcb20 (02:15) cancelled at 02:37 (`8e9b842`). Before: `run-aa4e1f47` (00:22-01:52) CANCELLED in sprint 4, benchmark 9/10 (fails only the refusal of an empty title), locked 15/16: the UI/UX advice disabled "Add task" until a title was typed despite the rule, the architect adopted it, and code review and the page check then demanded opposite things (`fd62bcd`); earlier, carried work declined as untested (`635d470`) and two locked edit tests left behind by their own change (`d0b1a2f`, which reopened the suite and let sprint 3 pass). Before it: run-f3957015 (00:05) cancelled at 00:17 (`19369b2`). Before: `run-7d8e02b6` (21:43-23:56) COMPLETED, benchmark 8/10 - FALSE ACCEPTANCE, locked 9/9, unit 24/24, 433 lines: the interface design disabled "Add task" until a title was typed, so the customer's refusal check timed out (`f4defca`); the locked edit test asserted an item found by its old title no longer showed it, and a fix stage hid the old title in the item (`2a60ddf`); the last sprint declined every adopted UI/UX item because "the test suite passes" (`5680d34`); duplicate underlined defects each went to a fixer (`91418e4`, deployed mid-run). Before it: `run-2fb10bf1` (18:54-21:35) CANCELLED at the last sprint's third attempt, benchmark 10/10, locked 9/9, unit 34/34, 376 lines; not clean: adopted advice found not built was dropped by sprints closed with nothing to build (`dcb7703`), fifteen carried items sent plans back (`07b8f88`), out-of-brief review findings and advice - the harness's own server, browser-kept data, unique titles (`dde0955`) - the milestone review re-grading security findings above the security review (`1ad5047`), and read_file line numbers written into the page by edits matched without them (`284f3ca`). Before it: run-d6479ae6 (18:36) was cancelled at 18:48 (`aed2c41`). Before: `run-da5f08f4` (16:34-18:12) COMPLETED, benchmark 7/10 - FALSE ACCEPTANCE, locked 9/9, unit 14/14, 286 lines: the locked suite found the brief's "Done" box by a class and pressed the filters with `page.click('text=...')`; the product gave the box no label and drew every filter twice (`117e7d6`); a fix stage also rewrote `document.querySelector` in the product for a unit test's undefined selector, and `index.html` shipped literal backslash-n in its head (`f23e586`). Before it: `run-755f003d` (14:49-16:06) COMPLETED, benchmark 10/10, locked 9/9, unit 18/18, 231 lines; not clean - its locked suite left a test unclosed and was reopened for QA only after the mid-run deploy of `a1684db`. run-976139d8 (14:33) was cancelled at 14:47 in sprint 1: its planner listed criteria as bare numbers, so edit and delete were guessed into sprint 1 (`af3678e`). run-32f01312 (14:06) was cancelled at 14:31 in sprint 2: its failed sprint's record counted a unit run only, '17 tests, 16 passed, 0 failed' over a failing acceptance criterion (`dc03b73`). Last: `run-c336827c-1641-4c69-b610-76194effc453` (13:48-14:01 JST, 2026-10-06, gpt-oss-20b) COMPLETED in 14 minutes, benchmark 10/10, locked suite 5/5, unit 7/7, 274 lines; sprint 1 built everything and sprints 2-5 closed as already built. Not clean: the harness assigned AC-3 (edit) to sprint 1, which put editing out of scope, ignoring the ids the plan listed (`f9ba962`). Before it: run-72ab020e COMPLETED 10/10, not clean (14 fixes, model switched mid-run). |
| model | changed by the owner at about 11:44 JST on 2026-10-06: `openai/gpt-oss-20b` on LM Studio, `http://host.docker.internal:1234/v1`, reasoning effort low, execution mode **parallel**. Before it, from 2026-10-05: `qwen3.6-35b-a3b-mtp` on the same LM Studio, thinking effort medium (it lost whole replies to reasoning - 4 in run-72ab020e, 6 to 17 minutes each); before that `zai-org/glm-4.7-flash` (2026-10-02). Earlier: `unsloth/Qwen3.6-35B-A3B-MTP-GGUF` on the unsloth server (:8888, key required, a proxy that cuts a reply off at 20 minutes), gpt-oss-20b and qwen on :9090. To check that the configured model is served at the configured address with the harness's own key, run the snippet in section 5 inside the worker |
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
