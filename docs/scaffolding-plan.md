# Scaffolding review and plan (SF)

Owner request, 2026-11-07 10:1x JST: review how the harness sets up a stack that no pack covers, research
better ways, and plan the implementation. This document is the review, the assessment on merit, and the plan.
Items are SF.n; each is built with a test proven to fail on the old code, bundled per phase, and measured on the
sentinels before the next phase (bundle-big-changes). Stack-specific knowledge stays in packs and `seed.py`.

## 1. What the harness does today (measured)

Three tiers, decided at the stack decision (`stacks/__init__.py:574-634`, `acceptance_nodes.py:217-448`):

1. **A pack fits** (38 packs: 15 http_api, 8 fullstack, 5 browser, 5 cli, 5 library; TS 12, Python 8, JS 5, Go 4,
   Rust 3, Ruby 2, PHP 2, Java 1, C# 1, Kotlin 0). The pack carries files, kept files, commands, layout, guides,
   ~20 regex and callable test-quality checks, probe runner, release files.
2. **No pack fits -> custom setup**: a library replay is tried once, then the testing specialist runs up to two
   `stack_setup_n` stages writing `stack-setup.json` plus a smoke test of each kind; `custom_setup.prove` runs
   install, unit and acceptance commands and requires one passing JUnit test each. A pass writes a
   `proven-setup` contract (a *derived pack*) and saves the entry to `/app/data/proven-setups/`.
3. **Proof fails twice -> left to the agents**: no contract, no kept files, no unit gate; QA declares its own
   runner in `acceptance/run.json`.

Measured over the 522 stored runs:

| | custom path | pack path |
|---|---|---|
| runs | 37 (27 with setup stages) | 485 |
| setup time | median ~18 min; tail 66, 102, 190, 230 min | pack scaffold 17-30 s |
| setup-stage tool failures | 5-13% (one run 21 of 170) | - |
| hidden score (scored runs) | mean 0.82, 15 of 20 full | mean 0.89, 178 of 227 full |

Three findings decide the plan:

- **Most custom runs were on stacks that have a pack now** (FastAPI, Hono, stdlib http.server). The path was
  taken because the pack did not exist yet or the selector missed it (LF.585, LF.586, LF.644, run-d1899b44).
  Selection misses are the cheapest cost to remove and the fixes so far have been one regex at a time.
- **A derived pack is blind.** `custom_setup.pack_from` fills only commands, layout, kept files and guides;
  every locator pattern, callable check, `probe_runner`, `finds_by_name`, `data_dir_env`, `typecheck`, release
  files and `known_errors` stay empty. LF.534, LF.537 and LF.552 are false acceptances from exactly this
  (27/27 green and 5 of 8 hidden lost; 33/33 green with a broken start.sh; 7 of 8 at a green suite). This is
  the score cost.
- **The tiers disagree.** `pack_named` readers (shared facts, stub and reachability checks, support tier) treat a
  proven setup as no pack; `contract.the_pack` readers treat it as a thin pack; design-time facts call
  `choose_pack(stack)` again and so a custom stack's architect never hears the layout the setup proved. The
  library's `_REPLAYED` set is per process (a `failed/` set-aside is lost on a worker restart), and `remember`
  keeps smoke tests that import product modules (SP.2a, filed, unbuilt).

## 2. What others do (research, 2026-11-07)

- **Repo-setup agents (Devin, Jules, OpenHands, Copilot coding agent)** do not scaffold; they prove a setup once
  with a validate step, snapshot it, and replay the snapshot. Our library replays commands and files, not an image.
- **2026 environment-setup research** (MEnvAgent, DockSmith, Repo2Run, SetupBench): the winning shape is a
  *reuse pool of verified setups with a patch step on retrieval*, a step budget with rollback, and validation by
  running the project's tests. Exact replay without patching is the weak form (reuse success 39% -> 25%).
  Multi-language setup from nothing is still hard (best agents 30-57%).
- **IDE agents (Cursor, Windsurf)**: run the official framework generator (`npm create vite`, `cargo new`,
  `rails new`), never write the files by hand. 7 of 11 ecosystems' generators emit a passing test on day one
  (Rust, Spring, Rails, Laravel, Phoenix, Swift lib, Flutter); Node, Python, Go, .NET need a runner layer added.
- **Template ecosystems** (devcontainer Templates/Features, Copier, Yeoman, Nx, Backstage) keep templates honest
  with *golden instantiation in CI*: generate, install, test, assert. Features are small, versioned, composed by
  type (`dependsOn`), the maintainable form; Backstage users report one big template per stack is "clumsy".
- **Composition by role, not by product** (Bazel toolchain types, devenv `languages.<x>`): declare the role
  (runtime, framework, unit runner, acceptance runner, release) and resolve each, so N languages x M frameworks
  does not need N*M hand-written packs.

## 3. Assessment of the owner's idea on merit

The idea - "if no scaffold is available, the agent sets the stack up" - is right and is already built; the
owner's standing rule (handover: never force the model to choose only from existing scaffolds; extend
scaffolding for open-source frameworks) stays. What is wrong is not the idea but its form:

- the agent writes the whole setup from nothing (slow, variable, the research's weakest form);
- what it proves is kept as a thin pack that the rest of the harness treats as blind or as no pack;
- the saved setup is replayed verbatim and never patched, tested in CI, or promoted.

Recommendation: **build adjusted.** Keep agent-driven setup as the last resort; put a deterministic generator
layer before it, make a proven setup a first-class pack composed from the harness's own layers, and give the
library the patch step and golden tests the research shows matter. Order by the owner's rule (quality first):
score-affecting blindness first, time second.

## 4. Plan

### Phase SF.0 - bug fixes, always on (one bundle)

Progress: SF.0a facts part BUILT 2026-11-07 (`shared_facts.facts_from_the_workspace` reads `contract.the_pack`; `tests/test_a_proven_setup_gets_the_facts_a_pack_gets.py`), committed, not deployed (held until the RC14 runs finish, owner 11-07).

- **SF.0a One tier reading.** Every `pack_named(...)` reader (`shared_facts.py:214`, `scaffold.py:68/103/258`,
  `delivery.py:121`, `server/runs.py:162`, `acceptance_nodes.py:228`) reads `contract.the_pack` so a proven setup
  gets layout facts, stub and reachability checks, and a "proven setup" support tier. Design-time facts
  (`workflow.py:4876, 4989, 5235`) read the contract when one exists. Test: a proven-setup workspace yields the
  same facts block a pack does.
- **SF.0b Library hygiene.** `_REPLAYED` persisted in `.harness/`; `remember` refuses an entry whose smoke tests
  import anything but kept or smoke files (SP.2a); `verify_packs` replays each library entry on an empty project
  nightly and sets aside one that fails (the devcontainer `test.sh` pattern). Tests: a restart between replay and
  proof still sets the entry aside; an entry importing a product module is not kept.
- **SF.0c Selection misses measured, not patched.** `loop.sh` gains `stack-misses`: every stored run whose
  decision said "no stack pack fits" while `choose_pack` now fits one, with the selector's text. Each new miss
  class gets its own test; the three fixed tonight become its first rows. No prompt change.

### Phase SF.1 - a proven setup is a composed pack (switch `COMPOSED_SETUP`, measured)

- **SF.1a Layers.** Split what packs already share into named layers in `stacks/packs/_layers.py`:
  runtime (Node, Python, Go, ...: install, memory, `code_runs_in`, manifests), unit runner (node:test, vitest,
  pytest, go test, xunit...: command, JUnit flags, patterns, `test_bugs`), acceptance runner (Playwright page,
  Playwright request, pytest+httpx: config, probe runner, kept files, readiness route, page checks, `finds_by_name`),
  release (Dockerfile and CI per runtime). Existing packs are expressed as compositions where they already are
  (`_javascript.py`, `_python.py`, `_fullstack.py` hold most of it); no pack's files or commands change. Test:
  every pack's `files`, `commands` and patterns are byte-identical before and after.
- **SF.1b `pack_from` composes.** A proven setup declares its runtime, unit runner and acceptance runner (the
  setup request already asks for exactly these); `pack_from` fills every empty field from those layers, so a
  derived pack gets the page checks, probe runner, readiness route, `data_dir_env`, `known_errors` and release
  files of its layers. LF.552's borrow of `browser-javascript` goes. Test: the derived pack of a Playwright+vitest
  setup has `locators_nobody_sees`, `probe_runner == "playwright"` and a Dockerfile; a run-time replay of LF.534's
  and LF.552's stored suites now reports their page findings.
- Measure on the custom-path sentinels (a stack with no pack, e.g. Kotlin/Ktor service, Elixir/Phoenix): hidden
  score and false-acceptance rate against the 0.82 / 5-of-20 baseline. Keep on at no loss.

### Phase SF.2 - generator-first setup (switch `GENERATOR_FIRST_SETUP`, measured)

Progress 2026-11-07 (moved ahead of HR Phase 1: five point fixes in two hours - LF.657, 658, 659, 661, 662 - each followed by the next mechanical failure; falcon baseline 2 hidden 0/9). Built as a runner layer first: a pack names its `framework_files` (path -> what it must do); `custom_setup.runner_layer(kind, language)` finds the pack whose install, runners, report flags and kept test configuration a stack of that kind and language reuses. Steps 1-4 BUILT 13:2x: `write_runner_layer` writes the pack's neutral files and the declaration from its own commands; `layered_setup` + the narrowed request ask the setup stage only for the framework files; wired into `_set_up_a_stack_no_pack_covers`. Proven end to end in the worker: a Falcon project on the layer passed install, unit and acceptance smoke through `prove()`. Always on (quality). Measure on falcon 4 and later baselines: setup proven, minutes, hidden score, against falcon 1-3 (0 of 5 attempts proven after LF.657, hidden 0/9). SF.2 measured on its first live run (falcon 4): the setup proven on its first attempt in about 3 minutes. SF.1 BUILT 13:2x for layered setups: the declaration names its layer pack; `pack_from` builds the proven pack as that pack (test-bug patterns, known errors, entrypoint, release files kept) with the setup's commands, paths and kept files (`tests/test_a_proven_setup_on_a_layer_keeps_its_pack_s_checks.py`). Hand-written setups are built as before. Verified live on falcon 5 (proven first attempt, ~11 min): its pack carries 5 test-bug patterns, 3 known errors, the pytest probe and the entrypoint. SF.1b: a release file naming the base pack's framework (the Python Dockerfile runs `uvicorn`) is dropped rather than shipped wrong.

Progress 2026-11-07 15:1x: LF.665 (a layered setup's guide named FastAPI to a Falcon product) and LF.666 (the setup's proven entry code is a fact every builder sees; falcon 5's specification overrode it) - SF.1 fixes found by falcon 5.

- **SF.2a Generator table** in `seed.py` (stack knowledge belongs there): per ecosystem the official
  non-interactive create command with pinned flags, whether it emits a test, and which unit-runner layer to add.
  Covered: Node/TS (`npm create vite`), Python (none: the Python runtime layer's skeleton), Go (`go mod init`),
  Rust (`cargo new`), Java/Kotlin (Spring Initializr zip), .NET (`dotnet new`), Ruby (`rails new`), PHP
  (`laravel new`), Elixir (`mix phx.new`), Dart (`flutter create`).
- **SF.2b Harness runs the generator, the agent adds the rest.** The scaffold node runs the generator itself
  (deterministic, logged, one retry), then the setup stage is asked only for what the generator left out: the
  unit-runner layer if missing, the acceptance-runner layer (always the harness's own), two smoke tests and the
  declaration. Seeded codebases skip the generator (`already_set_up`). The proof is unchanged. Test: a request
  after a generator run names only the missing layers; a generator failure falls back to today's stage.
- **SF.2c Budget and rollback** (Repo2Run): the setup stage gets a step budget and a rollback of the project
  tree to the generator's output when a step pollutes it (today a failed attempt deletes everything and starts
  over). Test: a polluting install is undone and the second attempt starts from the generated tree.
- Measure: setup minutes and proof pass rate against the 18-min median, the 100+-min tail and the proof failures
  in LF.256-258, 519, 551, 558. Keep on at no loss of score.

### Phase SF.3 - the library learns (switch `SETUP_PATCH_ON_REPLAY`, measured)

- **SF.3a Patch step on replay** (MEnvAgent): retrieve the nearest entry (today's `_chosen_by`), then one bounded
  agent call patches it against this brief's stack line and specification (versions, package names, the
  acceptance runner's port and data dir) before `prove`; a failed patch falls back to verbatim replay, then to
  generator-first. Test: an entry for Hono 4.13 replayed for "Hono 4.14 with Jest" is patched, not replayed as is.
- **SF.3b Promotion** (SP.3): an entry proven on two runs is emitted as a pack module skeleton (a composition of
  layers plus its framework delta) into `stacks/packs/proposed/` for review, with its golden test; it does not
  load until moved. Test: the emitted module scaffolds in `verify_packs`.
- **SF.3c Harvest** (SP.2): a run that passed all hidden tests on a custom stack contributes its proven setup
  with the run's score attached, so retrieval prefers entries with a scored history.

### Not planned

- Image snapshots (Devin/Jules form): our workspaces are per-run directories in one worker image; a per-stack
  base image cache is the OpenHands lock-tag pattern and worth a separate review once SF.2 shows which runtimes
  recur. Noted, not built.
- Restricting the selector to packs (SL.1 `allowed_packs`): against the owner's rule; stays PROPOSED.

## 5. Order, measurement and risks

Order: SF.0 (one bundle, this week) -> SF.1 (quality; the false-acceptance class) -> SF.2 (time) -> SF.3.
Each phase: targeted fail-on-old tests per item, full suite, one deploy at a run boundary, two runs per sentinel
family on the frozen SHA before judging (MF.4), KPIs from `loop.sh impact`: hidden score, false acceptances,
setup minutes, proof pass rate, setup-stage tool failures. A phase that moves no score or KPI is parked.

Risks: SF.1a is a refactor on a live loop (mitigated by the byte-identity test and a switch); generators need the
network and drift in versions (pin flags, keep today's stage as fallback); the patch step reintroduces agent
variance (budget, rollback, verbatim fallback); local models hallucinate constraints in setup (SetupBench) - the
generator and the harness's own acceptance layer remove most of what they would have to invent.

Both codebase sizes: a seeded or large codebase never runs a generator and is patched, not rebuilt; the
acceptance-runner layer is added beside the existing tests, as `already_set_up` does today.
