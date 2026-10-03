# Redesign: build products the way a software company does

Started 2026-10-03 at the owner's request ("Implement all the above suggestions
and later start the testing improvement loop"). This file is the plan and its
progress record; keep the status table current.

## Why

About 70 runs on the simplest brief on 2026-10-03 produced no clean product.
Two causes sat under almost every finding:

1. **Done meant "the model's own tests pass".** The same stages wrote and
   rewrote the code and the tests, so products where nothing redrew after a
   delete, or whose page no test ever opened, were accepted.
2. **Quality was enforced by hand-written pattern checks.** Over 6,700 lines,
   mostly about JavaScript and HTML; each new one brought false positives, and
   none carries over to another kind of product.

## The target flow

```
intake -> [review] -> stack -> architecture -> architecture review -> [review]
  -> scaffold (stack pack, smoke-tested)
  -> acceptance author (QA writes one test or more per criterion)
  -> acceptance review (coverage check + reviewer) -> [review] -> LOCK
  -> sprint plan (vertical slices, each sprint names the criteria it makes pass)
  -> per sprint:
       work orders -> CI per batch (revert on regression) -> code review
       -> test round + harness-run acceptance suite -> fixes (escalation ladder)
       -> security review -> milestone review (cannot accept a red acceptance gate)
       -> [review with evidence] -> commit
  -> release gate (every criterion not deliberately deferred passes) -> [review] -> complete
```

`[review]` is a decision point. In **auto** mode the harness decides and writes a
decision record. In **approval** mode the same record is shown to the user, who
approves, requests changes (which become tracked change requests with their own
acceptance tests) or, where offered, picks an option.

## Components

| Component | Module | What it does |
|---|---|---|
| Stack packs | `app/stacks/` | One per kind of product and language: scaffold files, install/unit/acceptance commands, JUnit report paths, the acceptance-test guide, the files the harness keeps as set up, which cross-file check families apply. The core knows no language. |
| Scaffold | `app/stacks/scaffold.py`, node `scaffold` | Writes the pack into the project directory, installs, and runs the pack's own unit and acceptance smoke tests before any agent writes code. |
| Project contract | `app/stacks/contract.py` | Repairs the pack's commands and runner configuration after every stage, and describes them in every specialist request. |
| Acceptance criteria | `app/acceptance/criteria.py` | Numbers the intake's acceptance criteria and success measures as AC-1..n. |
| Acceptance suite | `app/acceptance/` | Author request, coverage check, lock (checksums plus a snapshot), harness-run suite with JUnit parsing, per-criterion results. |
| Gates | `graph/workflow.py` | Test rounds add the harness-run acceptance failures as defects; the milestone review cannot accept a sprint whose criteria are red; the release gate needs every criterion that has not been deliberately deferred. |
| Per-role models | `models/roles.py`, settings | A judgement model for architect, QA, reviewers and fixes; the default model for everything else. |
| Decision records | `app/decisions.py` | One record per decision point, in state, in `docs/decision_log.md`, and over the API and UI. |
| Change requests | `app/decisions.py` | A user's requested change becomes CR-n with its own acceptance test and is followed to closure. |
| CI and code review | `app/ci.py`, nodes `ci_gate`, `code_review` | Per work-order batch: build, unit and acceptance runs against the baseline; a batch that breaks what passed is reverted; a reviewer reads the diff. |
| Escalation ladder | `graph/workflow.py` | fix -> re-plan -> judgement model -> decision (auto: defer the criterion with a reason; approval: ask). |
| Check scoping | `analysis/integration_checks.py` | Each check has a family; only core checks and the pack's families run; only near-certain checks can block. |
| Benchmark | `benchmarks/`, `scripts/bench/` | Briefs across product kinds, hidden acceptance tests the harness never sees, and a scorer. |

## Status

| # | Phase | State |
|---|---|---|
| 1 | Stack packs, scaffold node, project contract | done (`d66a47e`, wired in the next commit) |
| 2 | Acceptance criteria, author, review, lock, runner | done |
| 3 | Acceptance gates in test rounds, milestone review, release | done |
| 4 | Per-role models | done |
| 5 | Decision records, modes, evidence package, change requests, UI | done |
| 6 | CI per batch with revert, code review, commits | done |
| 7 | Vertical-slice planning and the escalation ladder | done |
| 8 | Check scoping (core vs pack, blocking vs advisory), precision script | done |
| 9 | Benchmark briefs, hidden tests, scorer, loop gate | |
| 10 | Deploy, benchmark runs, restart the improvement loop | |
