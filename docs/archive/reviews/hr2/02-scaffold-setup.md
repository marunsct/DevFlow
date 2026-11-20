# HR2 review 02 - scaffold, stack packs, custom setup, proof, library, runner layer, environment contract

Read-only review, 2026-11-07 22:4x-23:5x JST. Data: 106 stored workspaces, 536 transcripts, `data/kpi/run-*.json`
(42 setup stages over 21 runs), `data/bench` (8 falcon, 19 fullstack-bookmarks-py), the proven-setup library in the
worker (6 live + 4 set-aside entries), `data/loop/nightly-*.log`, `loop.sh stack-misses`. Scripts used (scratchpad
`review2/measure_setup.py`, `measure2.py`, `measure_scaffold_time.py`) read transcripts and workspaces only.

## 1. What exists

Three tiers decided in `acceptance_nodes.py:217-319` (`scaffold` node) and `:337-455` (`_set_up_a_stack_no_pack_covers`):

- **Pack** (38 packs, `stacks/packs/__init__.py:34-73`): `scaffold.scaffold` (`scaffold.py:445-543`) writes
  `pack.render`, records the contract *unproven* first (`:479`, so the sandbox reads the pack's needs), runs install
  (one retry), writes the smoke files, runs unit and acceptance smoke through the pack's own commands (one retry each,
  `:505-518`), removes smoke files and reports, writes the contract, commits. A failed scaffold is retried whole once
  (`acceptance_nodes.py:260-269`) and then **fails closed** (`:286-314`, escalation). Seeded codebases are built on as
  they are (`:231-247`, `custom_setup.already_set_up`).
- **Custom setup** (`custom_setup.py`): library replay first (`replay`, `:1200-1237`; exact key, then canonical
  `language|framework|runner`, then a one-call model pick `_chosen_by` `:1155-1193`), proven by `prove` (`:854-1007`);
  a failing replay is set aside to `failed/` (`:1245-1268`, LF.684 persisted the marker). Then up to `ATTEMPTS=2`
  `stack_setup_<n>` stages of the testing specialist. **SF.2 runner layer** (`runner_layer` `:150-162`,
  `write_runner_layer` `:165-203`, `layered_setup` `:221-236`): when a pack of the same kind and language declares
  `framework_files`, the harness writes every pack file but the framework's own plus the declaration, and the stage is
  asked only for the framework files (`build_setup_request` `:265-280`). **Only one pack declares `framework_files`:
  `python_http_api.py:167-181`** (requirements, `{{package}}/main.py`, `start.sh`, the unit smoke test). Every other
  kind/language combination still takes the hand-written request (`:281-329`: generator, two runners, two smoke
  tests, a 15-key declaration).
- **Proof** (`prove`): declaration read and validated (`_declared` `:520-623`, ~14 checks, each the residue of a
  measured failure: LF.657-661, 672), install, optional build, unit and acceptance commands twice each, LF.672
  removes test files beyond the smoke tests and re-runs; on pass: kept files, `proven_code` (LF.666/673,
  `_the_setup_s_own_code` `:694-728`), contract with `extra={"setup": ...}`, commit, `remember` unless the smoke tests
  import product code the entry does not carry (LF.684, `_smoke_tests_import_the_product` `:1109-1133`).
- **Derived pack** (`pack_from` `:773-851`): a layered setup becomes its layer pack with the setup's commands, paths,
  kept files, `proven_code`, the framework sentences stripped from the guides (LF.665) and release files naming the
  layer's framework dropped (SF.1b); a hand-written setup is still the thin pack of the scaffolding plan §1.
- **Contract** (`contract.py`): `the_pack` (`:207-230`) falls back to `pack_from`; but `scaffold.py:68`, `:103`,
  `:258`, `delivery.py:121`, `server/runs.py:162` and `acceptance_nodes.py:228` still call `pack_named`, which has no
  entry for `proven-setup` (`stacks/__init__.py:738-744`) - SF.0a's remainder.
- **Scope guard** M6 (`setup_scope.py`, `repository.py:2098-2126`): off; refuses a code file in a `stack_setup` stage
  that is not asked for, a test, or `__init__.py`.
- **Environment** (`sandbox.py`): `_child_environment` `:1095-1135` (project `.venv/bin` first on PATH, `HOME` per
  workspace `.agent-home`, `TMPDIR`, Playwright cache, `TOOLCHAIN_ENVIRONMENT` `:985-996` with `GOTOOLCHAIN=local`,
  `ACCEPTANCE_PORT`); the toolchain pin `.project-stack` (`:1625-1830`, 17 languages, aliases, framework->language);
  `use_runtime` (`tools/runtimes.py:249-318`) downloads a Node/Go/Java/Python version per run; R6 (LF.675) puts the
  `cd <project>` form in the stable block.
- **Nightly** (`loop.sh nightly` `:606-614`, `verify_packs.py`): scaffolds every pack into `pack-check/<pack>`, then
  (LF.685) replays every library entry with `prove(keep=False)`.

Today's fixes in the area: LF.665, 666, 672, 673, 675, 684, 685, 686 (M6), SF.0c `stack-misses`, SF.1 layered pack.

## 2. Measured

**Pack scaffold time is not a cost.** Decision time minus the last model record before it, 70 pack runs: plain JS
page 5 s (n=16), Flask 8 s (15), FastAPI 11 s (12), Hono native 3 s (11), page+FastAPI 23 s (8), React+FastAPI 30 s,
Next 34 s; max 34 s. Nightly scaffold times 1-31 s. Nothing to gain there.

**Custom setup, 18 stored runs with `stack_setup` stages (11-02 to 11-07):**

| | hand-written request (12 runs, to falcon 3) | layered SF.2 (6 falcon runs 4-9) |
|---|---|---|
| proven | 1 of 12 (7570da3a, after 230 min) | **6 of 6** |
| left to the agents | 11 | 0 |
| setup minutes (both attempts) | median 14.0; 12.8, 12.8, 13.1, 13.8, 14.0, 15.5, 28.8, 29.9, 56.6, 102, 230 | **median 5.5**: 1.6, 3.0, 4.9, 6.0, 12.0, 22.2 |
| model calls | median 78 per run (14 of 24 stages stopped at the ~40-call cap) | 8-41 (one run 77) |
| lines written by the stage | median 950 (434-1402) | 66-137, except falcon 6: 1,118 |

Why the hand-written setups were left to the agents (the proof's problem text): declaration never written (2),
declared files missing / smoke test outside its runner's directory (3), `pip` refused for the role (1), `./notes-api/`
path doubled (1, LF.659), runner found 0 tests (2), stray test files (1), unit smoke failed (1). Every one is a
*mechanical* disagreement between the stage and the proof - the class SF.2 removes by writing the runners itself.

**Hidden scores by setup tier** (`data/bench`): left-to-agents runs 1.0 x6, 0.375 (false acceptance), 0.0 (false
acceptance), 2 unscored; proven runs 1.0 x5, 0.875 (FA), 0.0 (FA, falcon 6 = LF.676). The tier does not predict the
score; the false acceptances do (4 of 16 scored custom runs = 25%, against 11% overall in HR §1).

**The library has never replayed successfully.** No stored decision says "replayed" (`SCAFFOLD DECISIONS`: 7 "a proven
setup (setup stage)", 0 replayed, 11 left). The `failed/` folder shows three falcon entries set aside on 11-07 at
02:09, 07:31 and 08:37 UTC - each a run that paid replay + proof, then the setup stage. The live falcon entry
(written 09:33 UTC by falcon 9) **cannot replay either**: its declaration is layered (`layer: python-http-api`,
install `pip install -r requirements.txt -r requirements-dev.txt`) and its `files` are only `pytest.ini`,
`acceptance/conftest.py`, `start.sh` and the two smoke tests - no `requirements.txt`, no `requirements-dev.txt`, no
`notes_api/main.py`; the unit smoke imports `notes_api.main`. `replay` (`:1219-1226`) writes only the entry's files,
never the layer (`write_runner_layer` is called only on the stage path, `acceptance_nodes.py:410-413`), and `remember`
keeps only `kept_files + smoke_files` (`:939-944`), never the framework files the stage was asked for. Under LF.684
the entry would now carry `main.py` (<=30 lines) or not be kept at all - and still fail at install. The next falcon
run will pay this again and set the entry aside.

**The nightly check has not run for 9 packs since 10-29, nor the library check ever.** `nightly.log`: 15 of 18
nights "skipped: a run is live" (the loop is never-stopping), and the three that ran: 10-29 all 37 ok; 10-30 and
11-04 **crashed at `go-gin-api`** with `FileExistsError` from `verify_packs.py:29-30` (`shutil.rmtree(...,
ignore_errors=True)` silently failed - a Go module cache under the previous check's `.agent-home` is read-only - then
`mkdir`). So go-gin, java-spring, csharp-aspnet, rust-axum, ruby x2, php x2 and the whole library block were never
reached, and the log's summary line is empty (`nightly.log` 10-30, 11-04). The 92-pins-a-major-behind report is
the only part that completes.

**The layered stage reads the whole product plan.** Falcon 7-9 `stack_setup_0` first request: 89-99k characters in
all; project memory 55-69k (it holds `docs/technical_specification.md` whole, with its `Component Boundaries` and
file plan), the request 7-10k of which 6-9k is `--- What the specification already decided ---` built from
`file_plan`, `testing`, `configuration`, `library_usage` (`custom_setup.py:121-139`). The stage is asked for four
files. Falcon 6 wrote 1,118 lines of product (LF.686's case); falcon 4, 5, 7, 8, 9 wrote only the four. The reason
the spec block exists ("the setup created runner config under names of its own", `:243-249`) no longer holds on a
layer: the harness writes the runner configuration. KPI: setup stages are 1.0-1.9M input tokens for 30-41 calls
(`data/kpi`): ~45k tokens a call, of which the memory is ~17k.

**Setup-stage tool failures** (42 stages): 11 are the stall guard refusing a withheld tool (`read_file` 4,
`write_artifact` 3, `run_terminal_command` 3, `edit_artifact` 1) and 9 are `/app/pyproject.toml` or
`/pyproject.toml` not found (the stage addressing the workspace root instead of the project). Both are the
hand-written path; the layered runs have 0-2.

**Selection misses** (`loop.sh stack-misses`): 24 custom runs; 15 now fit a pack (14 FastAPI+page, 1 Hono) and 9
are Falcon (no pack, by design). No open miss class.

**`loop.sh effects` reports nothing about setup**: `effects.py` has no row for replay, layer, proof, scope guard or
set-aside - the mechanisms this area built today are the "built but unmeasured" class of HR finding 3.

## 3. The first review's items in this area

| Item | State | Evidence |
|---|---|---|
| SF.0a one tier reading | **part open** | facts built (`shared_facts`); `scaffold.py:68/103/258`, `delivery.py:121`, `runs.py:162`, `acceptance_nodes.py:228` still `pack_named`: a proven setup has no stub check, no second-copy check, no reachability, and its support tier reads as no pack |
| SF.0b library hygiene | **built, but the library still cannot replay** | LF.684/685; the layered entry lacks the layer's non-kept files (§2); the nightly library check has never executed |
| SF.0c stack-misses | built | 15 fixed, 9 Falcon |
| SF.1 composed pack | built for layered setups only | hand-written setups stay thin (`pack_from` `:823-848`): 1 of 7 proven runs |
| SF.2 runner layer | built for **one pack** | `framework_files` only in `python_http_api.py`; `runner_layer` returns None for every other kind/language |
| SF.2a generator table / **SF.2b** harness-run generators | open - **reshape** (see §5, HR2.SS.3) | the measured cause of setup time was the runner/declaration disagreement, which the layer removes; generators add network, version drift and a layout that fights the layer's kept files |
| SF.2c budget and rollback | open | 14 of 24 hand-written stages hit the call cap; on a layer, 1 of 7 |
| SF.3a patch on replay | open - premature | replay has never succeeded once; patch what replays first |
| SF.3b promotion, SF.3c harvest | open | no entry has replayed twice |
| M6 `SETUP_SCOPE_GUARD` | built, off | incidence 1 of 6 layered runs; its on arm (2 falcon runs) cannot show a score effect at that rate - judge it on its own KPI (lines beyond the asked files, §5 HR2.SS.4) and remove the temptation (HR2.SS.2) |
| HR R6 environment contract | built (LF.675) | setup-stage env failures are the hand-written path's |
| HR D2 setup-owned sections | open (other area) | the spec written before the setup contradicted it (LF.666); D2 is the fix of the class, HR2.SS.2 is its setup-side half |

Wrong in the scaffolding plan §1: "setup time median ~18 min" was measured over 37 runs of which most are now pack
runs; on the 12 hand-written runs still custom it is 14 min with a tail to 230, and on the layer 5.5 min.

## 4. Research (searched 2026-11-07; what fits)

- **Repo2Run** (arXiv 2502.13681, NeurIPS 2025): 86.0% of 420 Python repos built; the ablation that matters here:
  removing rollback 86.0 -> 83.6%, removing the Dockerfile synthesiser 86.0 -> 13.8%. The deterministic
  synthesiser, not the agent, carries the result - our runner layer is that synthesiser.
- **MEnvAgent** (arXiv 2601.22859, ICML 2026 submission; MEnvBench 10 languages, 1,000 tasks): a *reuse pool* of
  verified environments, nearest by an adaptation cost, patched incrementally, verified by running tests, added back
  to the pool; +8.6% F2P, -43% time against building from nothing. Our library is the pool; it has no working replay
  yet, so the patch step (SF.3a) has nothing to patch.
- **EnvBench** (JetBrains, ICLR 2025 workshop; 994 repos): best agent 6.7% Python / 29.5% JVM; iterative beats
  one-shot and "LLM approaches without error feedback produce broken setup scripts". **EvoConfig** (arXiv 2601.16489)
  78.1% on EnvBench by *diagnosing the agent's actions after execution* and re-prioritising its fixes - our proof's
  problem text is that diagnosis; it is written for the second attempt only, never recorded as a KPI.
- **SetupBench** (arXiv 2507.09063, 93 tasks, 7 ecosystems): OpenHands 38.9-57.4% on repository setup; failure
  modes: incomplete tooling, *hallucinated task constraints*, non-persistent environment changes; 38-89% of actions
  unnecessary. Our hand-written stages (median 78 calls, 14 of 24 at the cap) match the last figure.
- **HerAgent** (arXiv 2602.07871): success graded on an *Environment Maturity Hierarchy* (install < tests run < the
  entry point runs), not one bit. Our proof already has three levels (install, unit, acceptance) plus LF.662/676's
  own-start check; what is missing is recording which level a setup reached.
- **DockSmith** (arXiv 2602.00592): cross-task success memory and a loop-detection controller for a 30B model;
  F2P 39.7% on Multi-Docker-Eval (ACL 2026 Findings), whose authors find dependency resolution the least stable step.
- **SWE-smith** (NeurIPS 2025 D&B): an agent attempts install+tests, a developer writes the Dockerfile from that
  trajectory - setups are *harvested* from successful agent runs (our SP.2/SF.3c, unbuilt).
- **devcontainer Features** (containers.dev distribution spec): each Feature versioned by semver, `dependsOn`
  composition, an optional `test/<feature>/test.sh` run in CI. Our packs have the test (`verify_packs`) but it does
  not run (§2); the library entries have no version or dependency fields.
- **Nix devenv / Dagger**: lockfiles and modules; the OpenHands lock-tag image cache is the same idea. Not for this
  harness's per-run directories (scaffolding plan "Not planned" stands).

Fit: the research favours (1) a deterministic synthesiser (the layer) over agent-written setups, (2) a working reuse
pool before any patch step, (3) grading the proof by level and recording it, (4) golden tests that run. None of it
favours running framework generators before the agent (SF.2b) - every cited system *reuses verified setups or
synthesises them*; generators appear only in IDE tooling for humans.

## 5. New items (HR2.SS.n = scaffold-setup)

**HR2.SS.1 A layered library entry carries its layer, and replay writes the layer first.** *Bug, always on.*
Evidence §2: the live falcon entry and 3 set-aside ones lack `requirements.txt`, `requirements-dev.txt` and the
entry module; replay has succeeded 0 times in 106 workspaces. Change: `remember` keeps, for a layered declaration,
the framework files the stage was asked for (`layer_files`, already known at `acceptance_nodes.py:410`) beside kept
and smoke files; `replay` calls `write_runner_layer` for an entry whose declaration names a layer, then writes the
entry's files over it; `check_the_library` does the same so the nightly replays the same way a run does. The LF.684
import check then passes for the layer's own smoke test. Test (fails on old code): a layered entry remembered from a
proven project, replayed into an empty project with a stub runner, has `requirements.txt` and `<package>/main.py` and
proves; `check_the_library` on that entry returns ok. KPI: replay successes (new `effects` row), setup minutes on the
second run of a stack (expected 5.5 -> ~1 min, the proof alone). Size S. Risk: low.

**HR2.SS.2 The layered setup stage reads the setup, not the product.** *Quality fix, always on.* Evidence §2: 89-99k
characters for four files; the spec block's reason (`:243-249`) does not apply on a layer; falcon 6 wrote the product;
LF.666 shows the spec contradicting the setup. Change: on a layer, `build_setup_request` carries `configuration` and
`library_usage` only (the runner, test and file plan are the layer's), and the stage's project memory holds the
project's files and `docs/technology_stack.md`, not the specification (memory `focus`/`kept_out` already exist,
`project_memory.py:470-500`). The hand-written request keeps its block. Test: a layered request names none of the
specification's `file_plan` entries; its memory holds no `technical_specification.md`. Banned-word test for the new
sentence. KPI: setup input tokens (~45k -> ~25k a call), lines written beyond the asked files (M6's KPI). Size S.
Risk: the stage loses the configuration's env names - kept via `configuration`.

**HR2.SS.3 `framework_files` on every pack that can be a layer; SF.2b reshaped to "generator only where the layer has
no pack".** *Quality fix (pack data), always on.* Evidence: 1 of 38 packs is a layer; the measured gain (12 -> 6 of 6
proven, 14 -> 5.5 min) is confined to Python http_api; the 11 hand-written failures were all mechanical. Change: each
service pack built on `_service.py` (`go-http-api`, `rust-axum-api`, `java-spring-api`, `csharp-aspnet-api`,
`ruby-sinatra-api`, `php-slim-api`, `node-http-api`, `node-hono-api`, `node-nest-api`, `python-flask-api`) and the
page, CLI and library packs declare their framework files (the service's entry + manifest + start script + unit
smoke); `runner_layer` prefers the pack whose `frameworks` the stack names a sibling of, else the first. A pack's
`framework_files` must be a subset of its `files`+`smoke_files` (test over `ALL_PACKS`). Judgement on SF.2b against
M6: **park SF.2b**. On a layer the agent writes 3-4 files in 1.6-6 min when it stays in scope; a generator would
write its own manifest and layout over the layer's kept files, needs the network, drifts (92 of 219 pins are a major
behind already), and the research in §4 reuses or synthesises, never generates. Where no pack of the kind and
language exists (Elixir, Kotlin, Dart, Swift) there is no layer either and the generator is the whole setup -
that is the hand-written path's problem, and SF.2a's table belongs in `seed.py` as guidance for it, not as a
harness step. Test: `runner_layer("http_api", "go")` is a pack; a Go stack no pack covers gets a layered request
naming only its framework files. KPI: proven rate and minutes on the next non-Python custom family (E3's held-out
briefs should include one). Size M. Risk: a pack's framework file list wrong -> caught by the subset test and
`verify_packs`.

**HR2.SS.4 Setup telemetry: replay attempt, proof level reached, lines beyond scope, in `effects` and the decision.**
*Bug (measurement), always on.* Evidence: replay failures are invisible (no decision, no transcript record, no log
retained - 3 set-asides found only by `failed/` mtimes); `effects.py` has no setup row; M6 has no KPI source but a
hand count. Change: the scaffold decision's rationale names the replay attempt and its problem; `prove` records the
level reached (declaration / install / build / unit / acceptance / start) in `scaffold_result` and the transcript as a
`setup` record; `record_the_setup_s_scope` is read by `effects` to count code lines a `stack_setup` stage wrote
outside `files` (guard on or off). Test: a replay that fails leaves a decision naming the entry and the step. KPI:
feeds M6, SS.1, SS.3. Size S.

**HR2.SS.5 The nightly verify runs to the end, and runs at all.** *Bug, always on.* Evidence §2: crashed at
`go-gin-api` on both of the last two runs; skipped 15 of 18 nights; library check never executed. Change:
`verify_packs.py` removes the previous check's folder with permissions restored (`chmod -R u+w` then `rmtree`, or a
fresh folder name per night) and continues past one pack's failure; `loop.sh nightly` runs the pack check in a
throwaway container of the worker image (`docker compose run --rm worker python - < verify_packs.py`) instead of
exec-ing into the live worker, so a live run no longer skips it (CPU-capped; pins report unchanged). Test (fails on
old): a read-only file left in `pack-check/<pack>` does not stop the check; the summary line is written when a pack
raises. KPI: nights with a complete summary. Size S. Risk: a second container's installs compete with a live run's -
cap with `--cpus`, run at 03:00 JST as now.

**HR2.SS.6 SF.0a remainder: the six `pack_named` readers read `contract.the_pack`.** *Bug, always on* (the plan's own
item, re-stated because it is half done). Evidence §3. Test: a proven-setup workspace whose entry file is still the
layer's stub is named by `entrypoint_is_still_the_stub`; `support_tier` says "proven setup". Size S.

**HR2.SS.7 Proof levels recorded as the pack's needs, not retried blind.** *Doubtful - switch `SETUP_PROOF_FEEDBACK`.*
Evidence: EvoConfig/EnvBench (§4): error feedback is what moves setup success; today the second attempt gets the
proof's last 1,200 characters (`:883`, `:924-929`) and the hand-written path's second attempts fail 11 of 12.
Change: the retry request carries the level reached, the exact declared command and the three lines
`where_it_failed` found, plus the one rule the check broke (from `_declared`'s problem list), and the attempt keeps
the generated tree (SF.2c's rollback: delete only what the failed step wrote, from the write log). Measured on the
hand-written path only (the layer rarely retries). KPI: second-attempt proven rate. Size M.

Not proposed, with reasons: shared tool caches across runs (`HOME` is per workspace, `sandbox.py:1117-1119`) - pack
installs are 3-34 s, the saving is seconds; image snapshots (plan "Not planned" stands); restricting the selector to
packs (owner's rule).

## 6. Priority order and expected effect

1. **HR2.SS.5** (nightly runs and completes) - 9 packs unverified for 9 days and a library check that has never run; a
   bad pin found at night instead of by a run paying its scaffold twice and then failing closed (`:286-314`).
2. **HR2.SS.1** (replay works) - every second run of a custom stack: 5.5 min -> ~1 min, and SF.3 becomes possible.
3. **HR2.SS.4** (telemetry) - without it M6, SS.1 and SS.3 cannot be judged; one day's work with SS.1.
4. **HR2.SS.2** (the stage reads the setup) - -20k tokens a call x 8-40 calls; removes the falcon-6 temptation at its
   cause, so M6 is measured on top of it (expect the guard to fire ~never, which is the right outcome for a guard).
5. **HR2.SS.3** (layers for every pack; SF.2b parked) - the next custom family that is not Python http_api gets the
   6-of-6 / 5.5-min result instead of 1-of-12 / 14 min; needs one held-out custom brief in another language (E3).
6. **HR2.SS.6** (one tier) - closes the derived pack's blindness for stub/second-copy checks; score, not time.
7. **HR2.SS.7** (proof feedback, switch) - only the hand-written path; measure after SS.3 shrinks that path.

Bundle: SS.5 + SS.1 + SS.4 + SS.6 as one SF.0 bundle (all bugs, all small); SS.2 + SS.3 as the SF.2 bundle; SS.7 in
Phase 3 behind its switch. Each with its fail-on-old test and the suite; deploy at a run boundary.
