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
| branch | `harness-hardening-session`, last code commit `eede7fa`, pushed to `https://github.com/marunsct/DevFlow.git` |
| deployed | yes - the running image matches `eede7fa` (deployed 10:16 JST on 2026-10-04): plan review R1-R6 and the loop fixes since (latest: assertions the runner does not define are refused before the lock, and tests that cannot pass are repaired after it) |
| current run | `run-e5048126-8478-4292-9ec6-5b7d47102210`, `web-todo`, started 10:17 JST (2026-10-04), auto mode, gpt-oss-20b, no judgement model. Driven from session `langchain-cb`. run-dded3a26 was cancelled 10:11 JST: its locked suite called a matcher that does not exist (fixed `eede7fa`). |
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
