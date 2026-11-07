# 07 The product: what the harness ships, judged as a customer would (HR2.PR)

Read as delivered: nine stored workspaces across six families - notes-api-falcon 6 `73e2cc6c` (0/9) and 9
`66e5a37c` (9/9), notes-api 4 `2e7d285b` (9/9), tasks-api 5 `94ad3d57` (10/10, quality 6/7), web-todo `7c0b4466`
(10/10) and `e49fedd5` (9/10), fullstack-bookmarks-py `4fa87240` (8/8) and `702d8f6b` (7/8), notes-api-hono
`8374fd12` (9/9). Copies are under `scratchpad/review2/ws/` (node_modules and .venv left out). Beside the nine, a
read-only sweep of all 104 stored workspaces (`scratchpad/review2/sweep.py`, result `sweep.json`,
`readme_by_date.txt`) counted the handoff files, start-script shapes and code-hygiene facts below.

## 1. What exists

The release is deterministic and lives in `src/app/graph/delivery.py`:
- The suite is re-run, then the product is started the way a stranger starts it - a copy of the project, a fresh
  HOME, the plain PATH (`src/app/acceptance/start_output.py:164-172`), `python3` swapped for the project's own
  interpreter only when the start command is the harness's guess (`start_output.py:66-69`). LF.676 (today) made this
  run even when the measurement was reused; before it, falcon 6 and falcon 3 shipped 0/9 with a green suite.
- Production build, then the project's own unit tests (`delivery.py:262-284`); a failing unit set may still ship
  under `RELEASE_WITH_FAILING_UNIT_TESTS` (built in, `delivery.py:299-306`), recorded as a gap.
- Handoff: `release_docs.complete_the_handoff` writes a `## Running it` block (and a route table when no document
  names the routes) and `what_the_handoff_lacks` holds the release back - **only on the clean path**:
  `delivery.py:289-291` is `if not failing: complete_the_handoff(root)`. `RELEASE_DOCS_REQUIRED` and
  `RELEASE_AUDITS` are in `PREMIUM_DEEP_VERIFICATION` (`src/app/switches.py:92`), on since the 10-22 all-on baseline,
  although `release_docs.py:33` and PN.1/PN.2 in the plan still say "off".
- Secret scan, licence listing (`docs/third-party-licences.md`), dependency audit as a CI step
  (`src/app/stacks/release_audits.py:43-53`).
- CI workflow and, for a service, a Dockerfile from the pack's own commands (`src/app/stacks/release.py:37-119`),
  never over a file the product has. A custom setup (no pack) writes none: `src/app/stacks/custom_setup.py:819`
  ("the Python pack's Dockerfile runs `uvicorn ...` for a Falcon product. Better none").
- Gaps the record carries (`delivery.py:342-420`): deferred criteria, reclassified tests, open problems, shipped
  failing unit tests, licences, unproven setup, escalation leftovers, "no review read the code", the release
  re-check, code the product does not run (`app.stacks.scaffold.code_the_product_does_not_run`), what the mutation
  probe noticed, contract lines unchecked. Scratch files are deleted (`repository.clear_the_throwaways_left_behind`,
  `repository.py:7413`), by scratch-shaped name only.
- Nothing runs a linter on the product (SL.7 proposes naming rules through linters; not built). Nothing reads the
  product's comments, its logging, its server choice, its data directory or its concurrency.
- Quality beside the hidden score: `benchmarks/tasks-api/quality/` (7 edge tests, QM.1) is the only family with one;
  the mutation score of the locked suite is recorded for every scored run (`kpi_ledger.py:171`).

## 2. Measured

Sweep of 104 stored workspaces (56 NON-DELIVERABLE, 32 DELIVERY-NOTES, 16 unlabelled):

| Fact a customer meets | Count | Note |
|---|---|---|
| No README at all | 41 of 104 (39%) | last week 16 of 51; **every one NON-DELIVERABLE** (shipped under `may_ship` or an escalation), none clean |
| README median length | 12 lines | the harness's `## Running it` block and nothing else in 60 of 63 |
| README names `PORT`/`DATA_DIR` | 3 of 63 | the only two facts a stranger needs to start it |
| README names a route | 3 of 63 | `_routes_not_named` is satisfied by `docs/technical_specification.md`, so the table is never written into the README |
| README's command block | all 63 | `sh start.sh` is followed by the test commands in one block; `start.sh` `exec`s the server, so the block as written never reaches `pytest`/`npm test` |
| Dockerfile / CI workflow | 43 / 68 of 104 | custom setups (falcon, hono before its pack) ship none; the Dockerfile's `CMD` is the pack's own command, not `start.sh` - two start paths that drift (`HOST=0.0.0.0` in the image, `127.0.0.1` hard-wired in 21 of 68 `start.sh`) |
| `start.sh` without `PORT` | 12 of 68 | |
| `start.sh` running a bare `python3` | 6 of 68 | falcon 3 and 6 scored 0/9 for it (`ModuleNotFoundError: falcon` at the hidden tests' start); LF.676 now catches it at release |
| Pack template left in place | 16 | browser pack's 4-line `src/main.js` ("The page's entry point ... dataset.ready", `packs/browser_javascript.py:137`) beside the real `app.js`; falcon 6 shipped a 150-line scaffold `notes_api/main.py` (an ASGI wrapper of a `/health` app nothing serves) - `code_the_product_does_not_run` named neither |
| Deliberation comments in shipped code | 77 lines in 15 runs | `// Wait, spec says ...`, `// Actually, simpler:`, `// Let's use a flag` (hono 1 `app.ts:58-72`, bookmarks `5a3a8dcc` 27 lines) |
| Logging configured anywhere | 4 of 104 | `logger = logging.getLogger(__name__)` with no `basicConfig` in the rest: WARNING and above reach stderr by Python's last-resort handler, INFO never; falcon 6's `QuietHandler` suppresses every request line; tasks-api's catch-all answers 500 and logs nothing (LF.581's case, still shipped) |
| Bare/broad `except` | 61 in 26 runs | 23 `except: pass` |
| Data directory shipped inside the project | 20 (7 with a `.db`) | hono 1 ships `data/notes.json` with 12 of the suite's notes; `DATA_DIR` defaults to a relative `data` |
| Own unit tests failing at ship | 16 | notes-api 4: 7 `TestConcurrency` lock-timeout tests for a lock the store never takes (tests drafted before their code, memory `sum-recurring-notes`) |
| "No review read the product's code" | 19 | fast delivery accepted on the suite alone |
| Unit lines / product lines | median 1.17 (0 to 7.4) | tests mostly exercise behaviour through the framework's test client (falcon 9: 87 tests on 300 lines); the mutation probe still finds untested branches in 39 runs (57 notes) |
| Product size | median 381 lines in 3 files | all small-codebase evidence; nothing here is measured on a large one |

Scores (`data/bench`, `data/kpi/ledger.csv`): mutation score of the locked suite median 0.67 over 202 runs,
notes-api-falcon 0.33 (7), tasks-api 0.58 (41); with the unit tests added, falcon 9 reaches 1.0 (`caught_with_unit_tests`
12/12) - the shipped unit tests are stronger than the locked suite. tasks-api quality set, 49 scored runs, failures by
test: 20 parallel creates all kept 17, a title of only spaces refused 12 (LF.255's catalogue rule since 10-24: still 12),
a non-boolean `done` changes nothing 10, a foreign id is never a 500 8, a missing field is never a 500 7, a 5,000-char
title 7, a password never stored as given 4.

What a customer notices that the hidden tests do not (from the nine products):
- **Concurrency**: every JSON-file store is load-modify-save per request with no lock (falcon 9 `main.py:190-260`,
  flask 4 `store.py` - its docstring claims `fcntl.flock` on writes and takes none; hono keeps a list in memory and
  rewrites the file); two uvicorn workers or two clients lose writes. wsgiref (falcon 6 and 9) serialises requests
  and hides it. The quality set's "created at once" test is the only measure, and only for tasks-api.
- **Server**: both falcon products serve production through `wsgiref.simple_server` (a development server, single
  thread, no keep-alive) while declaring `uvicorn[standard]`/`gunicorn` they never use.
- **Ids**: hono 1 allocates `max(id)+1`, so a deleted note's id is handed to the next note; a client that cached the
  old one sees a different note.
- **Sessions**: tasks-api keeps one token a user (`DELETE FROM tokens` on sign-in), so a second device signs the
  first out; tokens are stored as given. Not in the brief, but a customer with two tabs meets it in a minute.
- **Validation**: falcon 9 accepts `"title": " "` (no trim; the catalogue rule reached the spec and not the code);
  falcon 6 answers 500 on `GET /notes/abc` (`int(note_id)` unguarded; cf. notes-api `cf0ddc97` losing a hidden test to a
  500 on an empty title); hono answers 400 to a non-numeric id where the brief says 404.
- **Configuration**: falcon 6 `start.sh` refuses to start without `DATA_DIR` while its README says `sh start.sh`;
  bookmarks' `start.sh` rebuilds the page with Vite on every start; three products ignore `HOST` entirely.
- **Hygiene**: FastAPI `on_event` (deprecated) in 10 products; falcon 6's `conn.row_factory = None  # We handle dicts
  manually`; dead `_AsgiWrapper`; the hono factory takes `dataDir` and reads `process.env.DATA_DIR` in every handler
  instead.
- **Handoff**: DELIVERY-NOTES/NON-DELIVERABLE are JSON for the harness; `docs/` holds 1,491 lines of sprint plans,
  reviews and a security review whose one finding is a missing shutdown handler (`docs/security_review.md`); no
  document says what the product is, how to configure it, what it serves and what is known to be wrong, in that
  order, on one page.

## 3. The first review's items in this area

- **G4** (ASVS security review + scanner, switch): open; the measured products show the LLM review finds shutdown
  handlers and never the token-per-user, the unguarded `int()` or the lockless store. The deterministic half should
  come first (HR2.PR.6/7 below give it concrete checks); the LLM half stays measured.
- **G2** (brief check by routes): covered by LF.648; nothing new.
- **E5** (mutation score as a gate KPI): right, and the sweep adds: the shipped unit tests catch more than the locked
  suite (falcon 9: 0.75 vs 1.0) - `caught_with_unit_tests` belongs in the ledger beside `mutation_score`.
- **E4** (20-30 hidden tests a family, core + extended): reshape - the tasks-api quality set's seven tests are
  brief-agnostic (blank values, bad types, long values, foreign ids, parallel creates, restart) and should be one
  generated set for every HTTP family from its contract, not seven hand-written files a family (HR2.PR.9).
- **PN.2 / LF.189 / LF.530** (README written from the harness's facts): built, and wrong in two places - the clean-path
  condition (HR2.PR.1) and the route table satisfied by the specification (HR2.PR.2).
- **LF.255** (blank values in the catalogue): a prompt fix for a probe-shaped problem; 12 of 49 still fail. Reshape as a
  probe body (HR2.PR.8).
- **LF.580/581** (catch-all handlers that log nothing): the prompt rule reached the fixers; the shipped products still
  configure no logging (4 of 104). Reshape as a pack fact in the kept entry file (HR2.PR.5).
- **P5** (harness deletes its scratch): not built on merit; the template leftovers in HR2.PR.4 are a different class
  (the harness's own kept file, unchanged) and are safe to name as a gap.
- **F8/Q1** telemetry: nothing records what the release's own checks found per product; HR2.PR.10 gives the product
  side its score.

## 4. Research

- **BaxBench** (Vero et al., ICLR 2025; AutoBaxBench 12-2025): 392 backend tasks across 14 frameworks, security judged
  by running real exploits; the best model is 62% correct and exploits succeed on more than half of the correct
  programs; less popular frameworks do worse - which matches falcon 0.33 mutation and two 0/9 runs here. Fit:
  **execute, do not read** - a parallel-write probe and a bad-id probe are exploits in the same sense.
  https://arxiv.org/abs/2502.11844
- **Sonar, "Assessing the Quality and Security of AI-Generated Code" (arXiv 2508.14727, 08-2025)**: 4,442 Java tasks,
  five models: no correlation between functional pass rate and static quality/security; smells, bugs and
  vulnerabilities in all models. Fit: our hidden score at the ceiling says nothing about the 61 broad excepts.
  https://arxiv.org/pdf/2508.14727
- **Blyth et al., "Static Analysis as a Feedback Loop" (arXiv 2508.14419, 08-2025)**: linters fed back to the model
  raise quality beyond correctness. **Sun et al. (arXiv 2511.10271, 11-2025)**: practitioners rank maintainability and
  readability first, research ranks security and performance first. Fit: a linter at the CI gate with errors as
  defects (HR2.PR.6), never a model reading for style.
  https://arxiv.org/abs/2508.14419 https://arxiv.org/abs/2511.10271
- **Production readiness for small services** (Twelve-Factor: config in the environment, logs to stdout, dev/prod
  parity; OWASP cheat sheets: input validation, error handling that never leaks, logging; Google SRE basics: a health
  endpoint that tells the truth, graceful shutdown, one way to start it): the checks that are mechanical are the
  ones to keep - env names documented, a real server, logs on, one start path - and are the checklist in HR2.PR.10.
  https://engineering.ol.mit.edu/handbook/delivering/production-ready/
- **Products**: Replit Agent self-tests each feature and reports failures with the fix; reviewers find its code
  "functional but messy" (naming, scattered logic); Lovable scores on first-run design; Devin Review and Factory
  Droids route output through the team's own CI (lint, tests) and the advice is to review agent PRs with more
  suspicion, not less. None publishes a quality rubric; all rely on the repo's existing linters and tests. Fit: the
  product's own CI must carry the lint and the quality probes the harness ran, so a customer's first push is green.
  https://dev.to/pickuma/factory-ai-droids-review-how-far-autonomous-coding-agents-have-come-in-2026-4m00
  https://dev.to/tianayams/vibe-coding-in-production-a-critical-analysis-of-cursor-lovable-and-replit-1m77

## 5. New items

**HR2.PR.1 - The handoff is written for every product that ships (bug, S).**
Evidence: `delivery.py:289-291` completes and checks the README only when nothing fails; a release that then ships
under `may_ship` (`delivery.py:299-306`) or an exhausted hold never gets one - 41 of 104 products, 16 of 51 last week,
all NON-DELIVERABLE, including notes-api 4 (hidden 9/9). Change: `complete_the_handoff` runs after the ship decision,
once, for every product that goes out; the lack is a gap, never a hold, when the attempts are spent. Test: a state
with failing unit tests accepted for shipping leaves a README naming the start command (fails today: no README).
KPI: products without a README -> 0. Risk: none (append-only, no model call).

**HR2.PR.2 - A README a stranger can use: configuration, start, test, what it serves, what is known (quality, S).**
Evidence: 3 of 63 READMEs name `PORT`/`DATA_DIR`; 3 name a route (the route table is skipped because
`_the_product_s_documents` counts `docs/technical_specification.md`, `release_docs.py:107-148`); every block lists
`sh start.sh` then the tests in one fence, which cannot run as written (the start never returns). Change (all from
facts the harness holds): **Configuration** from the environment contract (`agents/environment_contract.py`: each
variable, default, meaning), **Start** on its own ("stays running; stop it with Ctrl-C"), **Test**, **What it
serves** from the locked contract regardless of `docs/`, **Known gaps** from the completion gaps in plain words
(DELIVERY-NOTES/NON-DELIVERABLE stay as JSON). Test: a workspace with a locked contract and a spec naming the routes
gets the table in the README; the README names every variable the contract declares (fails today). KPI: `handoff`
checklist in HR2.PR.10. Risk: none.

**HR2.PR.3 - One start path: the container runs `start.sh`, and `start.sh` honours HOST and PORT (quality, S).**
Evidence: 21 of 68 `start.sh` hard-wire `127.0.0.1` with no `HOST`; 12 read no `PORT`; the pack Dockerfile's `CMD`
is a second start command (`release.py`, pack `container` strings) with `HOST=0.0.0.0`, so the image and the script
diverge - and a custom setup ships no image for that reason (`custom_setup.py:819`). Change: every pack and the
custom setup's declaration write `start.sh` as `${HOST:-127.0.0.1}` / `${PORT:-...}` (the brief's default kept); the
Dockerfile `CMD` is `["sh", "start.sh"]` when the project has one, so a custom setup can ship an image too; the
stranger-start check (`start_output.py`) runs once more with `HOST=0.0.0.0` and probes `127.0.0.1` (bug: a script
that ignores HOST is "started" and unusable in a container). Test: a pack-less project with a declared start gets a
Dockerfile whose CMD is start.sh; a start.sh ignoring HOST is a gap (fails today). KPI: Dockerfiles 43 -> every
service; start.sh honouring HOST 47 -> 68. Risk: low; stack facts stay in packs/`seed.py`.

**HR2.PR.4 - The harness's own untouched templates and unserved modules do not ship (bug, S).**
Evidence: 16 products carry the browser pack's unchanged `src/main.js` stub beside `app.js`; falcon 6 shipped a
scaffold `notes_api/main.py` (150 lines, nothing serves it); `code_the_product_does_not_run` named neither. Change:
at release (beside `clear_the_throwaways_left_behind`), a kept pack file byte-equal to the pack's template whose
page/entry does not load it is deleted by the harness (its own file, unchanged) and a module no entry, start command,
test or import reaches is a gap naming it. Test: a workspace with the untouched `MAIN` and an `app.js` loaded by
`index.html` ships without the stub (fails today). KPI: template leftovers 16 -> 0. Risk: deletion is narrow
(byte-equal to the harness's template only); the gap for other dead modules is text, not deletion.

**HR2.PR.5 - Logging on, in the kept entry file (quality, S).**
Evidence: 4 of 104 products configure logging; the products' catch-all handlers answer 500 and log nothing
(LF.380/581's prompt rule did not reach the shipped code); falcon 6 silences request lines. Change: the pack's kept
entry (`wsgi.py`/`main.ts`/`server.js`: the file the harness owns) carries the stack's one-line logging setup to
stdout at INFO and an error handler that logs the traceback before answering 500 - pack data, like the health route
already is; the custom setup's declaration asks for the same line (a setup fact). Test: every pack's kept entry
contains its logging line (fails today for all). KPI: `logcfg` 4 -> 104; the suite's `server_log` non-empty on a 500
(LF.274 reads it). Risk: none.

**HR2.PR.6 - A linter at the CI gate, errors as defects (doubtful: switch `PRODUCT_LINT`, group Review gates, M).**
Evidence: 61 broad `except` in 26 runs, 23 `except: pass`, unused imports and dependencies (`uvicorn[standard]`,
`sys`, `Config`), 77 deliberation comments, no product linter anywhere (SL.7 is naming only). Change: per pack a
`lint` command as data (`ruff check --select E9,F63,F7,F82,F401,F841,E722,B`; `eslint --rule no-undef,no-unused-vars,
no-empty`; `go vet`; `cargo clippy -D warnings`), run at `ci_gate` on the files a sprint wrote; errors are defects
with the linter's line, the rest notes; the generated CI carries the same step. Research: static-analysis feedback
raises quality beyond tests (Blyth 2025; Sonar 2025). Test: a workspace with an unused import and a bare except
yields two defects under the switch (fails today). KPI: lint errors at release; fix minutes on lint defects;
hidden score unchanged. Risk: time on a small codebase (seconds); on a large one scope to the sprint's files.
Plus a deterministic comment check in the same step, stack-free: a comment line opening with a deliberation word
(`Wait,`, `Actually,`, `Let's`, `Hmm`, `Should we`) is a note for the builder to replace with the decision - a
prompt-free check, so no banned-word test is needed.

**HR2.PR.7 - A parallel-writes probe on the locked create line (quality, S-M).**
Evidence: "20 items created at once are all kept" is the most-failed quality test (17 of 49 tasks-api runs); every
JSON-file store read is load-modify-save with no lock (falcon 9, flask 4 whose docstring claims a lock it does not
take, hono); the quality set measures it for one family only. Change: the contract probes (`acceptance/
interface_contract.py`) gain one probe per contract write line with a body: N parallel creates, then the list line
counts them; fewer kept is a defect "N sent, M kept, k server errors" for the fixer; the architect's catalogue gets
one line ("a store every request writes is written under one lock or by one writer"). Test: a stub service that
drops concurrent writes gets the defect; the reference does not (fails today: no probe). KPI: quality
`items_created_at_once` 17/49 -> 0; the same probe's pass rate on every HTTP family. Risk: a probe needs the
create body - the body-shaped probes (`CONTRACT_PROBE_WITH_A_RECORD`, M1) already build it.

**HR2.PR.8 - Blank values as a probe body, not a catalogue line (bug, S).**
Evidence: LF.255 put "empty or only whitespace is missing" in the architect's catalogue on 10-24; 12 of 49 quality runs
still answer 201 to `"title": "   "`, falcon 9 and tasks-api 5 among today's. Change: `CONTRACT_PROBE_WITH_A_BAD_BODY`
sends, for every required text field the contract names, a whitespace-only value and expects the line's refusal
status; a 2xx is a defect. Test: a stub that accepts `" "` gets the defect (fails today). KPI: quality
`title_of_only_spaces` 12/49 -> 0. Risk: none; Q1 records its precision.

**HR2.PR.9 - One generated edge set for every HTTP family (evaluation, host side, M).**
Evidence: tasks-api's seven quality tests are the only ones; their shapes are brief-free (blank, bad type, long
value, foreign id, missing field, parallel creates, restart) and the families' contracts hold every fact needed.
Change: `loop.sh score` derives the edge set from the family's reference contract (bench.json names the create,
list, read lines) and records `quality_passed/total` for notes-api, falcon, hono, js, bookmarks too; the reference
must pass all. Test: the generated set passes on every reference. KPI: a quality score on every scored run (today 49
of 230 ledger rows). Risk: none to runs (host only).

**HR2.PR.10 - A handoff checklist score beside hidden, quality and mutation (evaluation, host side, S-M).**
Evidence: nothing records whether a product is usable by a stranger; this review's sweep had to be written to see
41 missing READMEs. Change: `loop.sh score` computes `handoff_score` from the shipped files, no model: README with
configuration, start, test, routes; `start.sh` honours PORT/HOST/DATA_DIR (started once each way); no development
server as the product's server (a per-language table in `seed.py`: `wsgiref`, `http.server`, `SimpleHTTPServer`,
`php -S`, `webrick` outside a pack that chose it); no untouched template; no deliberation comment; logging configured;
no data directory shipped; unit tests green; lint errors 0; CI file present. Recorded in `data/bench/<run>.json` and
the ledger (`WORSE_WHEN_LOWER`), reported by `loop.sh audit`. Test: the tasks-api reference scores 1.0; a workspace
without a README scores less. KPI: the score itself, per family, per SHA. Risk: none (read-only).

**HR2.PR.11 - The data the harness's own runs wrote does not ship (bug, S).**
Evidence: 20 products carry `data/` inside the project (7 with a database), hono 1 with twelve suite-written notes;
`DATA_DIR` defaults to a relative `data` the harness's test runs filled. Change: at release the default data
directory the product declares (environment contract) is emptied when every file in it was written during the run
(mtime after the run began) and is in `.gitignore`; a product that ships seed data on purpose declares it. Test: a
project with `data/notes.json` written by a stage ships without it (fails today). KPI: data shipped 20 -> 0. Risk:
low; only files the run wrote, only under the declared default.

**HR2.PR.12 - A development server is not the product's server (quality, S).**
Evidence: both falcon products serve through `wsgiref.simple_server` while declaring `uvicorn`/`gunicorn` unused;
the pack products never do (the pack's start is data). Change: the custom setup's declaration names the server and
`seed.py`'s per-language table of development servers refuses it as the declared start (the setup is proven with a
real one); the stranger-start check names a development server in the start command as a gap for pack-less
products. Test: a declared start of `python -m wsgiref...`/`python -m http.server` is refused (fails today). KPI:
falcon mutation and hidden unchanged; `handoff_score` server line. Risk: none for packs.

## 6. Priority order

1. **HR2.PR.1** (handoff on every ship) + **HR2.PR.2** (README content) - one bundle, no model calls, removes the
   largest visible defect (39% of products without a README, 95% without configuration) at zero run time.
2. **HR2.PR.10** (handoff score) + **HR2.PR.9** (edge set every family) - host side, in parallel: every later item in
   this area is judged by them, and they end the ceiling problem for product quality the way E4/E5 do for tests.
3. **HR2.PR.7** + **HR2.PR.8** (parallel-writes and blank-value probes) - execution over prompt; expected: quality
   failures 17+12 of 49 -> near 0, a few fix minutes a run where they fire.
4. **HR2.PR.4**, **HR2.PR.11**, **HR2.PR.5**, **HR2.PR.3**, **HR2.PR.12** - small release and pack fixes, one bundle at
   a run boundary; expected: template leftovers, shipped data, silent 500s, divergent start paths to zero.
5. **HR2.PR.6** (lint, switch) - measured on two runs a family; keep if lint errors fall and the hidden score holds.

Expected effect on score: none of these lowers a hidden score (they add checks after the suite or write files the
tests never read); PR.7/PR.8 raise the quality score; PR.3/PR.12 remove the class that produced two 0/9 runs.
