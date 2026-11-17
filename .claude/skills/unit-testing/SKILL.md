---
name: unit-testing
description: How tests are written, kept and removed in this harness, after Vladimir Khorikov's "Unit Testing Principles, Practices, and Patterns". Load before writing a test for a fix, reviewing a test, or deleting/reworking tests in tests/.
---

# Unit testing in this harness

The principles below follow Vladimir Khorikov, *Unit Testing Principles, Practices, and Patterns* (Manning, 2020), in
our own words, applied to this codebase (a LangGraph harness that builds products: graph nodes, a sandbox, stack
packs, acceptance probes, prompts sent to models). Where AGENTS.md sets a rule, AGENTS.md wins.

## 1. Why a test exists

A test is worth keeping only if it protects behaviour someone depends on - a run's outcome, a request the model is
sent, a command the sandbox runs, a file a product ships, a score. The goal is sustainable growth of the harness: the
suite lets us change it quickly and safely. A test that does not serve that goal is a cost (it runs, it breaks on
refactors, it is read) with no return, and is removed.

## 2. The four pillars - score every test on all four

| Pillar | The question | In this harness |
|---|---|---|
| Protection against regressions | Would it fail if the behaviour broke? | It exercises real code paths (a node, the sandbox, a probe, a pack's commands), not a stub of them. |
| Resistance to refactoring | Does it stay green when the code is restructured but behaves the same? | It never reads `src/` as text, never pins a private name, never asserts which helper was called. |
| Fast feedback | Does it run in milliseconds to a second? | No real model, no network, no sleeps; real subprocesses only where the behaviour is the subprocess. |
| Maintainability | Is it short and readable, with cheap setup? | Arrange is a few lines or a shared builder (`tests/workflow_nodes.py`). |

A test's value is the product of the four: near zero on any one makes it near worthless. Resistance to refactoring is
not negotiable - a test that breaks on every refactor teaches people to ignore red, which is worse than no test.
Between the other three you trade: an end-to-end node test gives more protection and less speed; that is fine.

## 3. Test observable behaviour, never implementation details

Observable behaviour = what a client of the code can see: a node's returned update, a defect's text the fixer reads,
the request a model is sent, the argv and environment a sandbox command gets, the files a scaffold writes, a ledger
entry, a score. Implementation details = private helpers, the order of internal calls, the exact source text, which
module a function lives in.

Forbidden in new tests, and a reason to rework or delete old ones:

- Reading a source file and asserting a string is in it (`Path(...workflow.py).read_text()`, `inspect.getsource`).
  Call the code instead. The only exceptions: a test of the source *as data the harness ships* (a pack template, a
  Dockerfile the sandbox builds), and the repository-wide guards in §7.
- Asserting a private function was called, or with what (`mock.assert_called_with` on our own code).
- Pinning exact wording of text no model and no product reads (log lines, comments, docstrings, UI copy).
- Testing a private function directly when a public entry point reaches it. A private function too complex to reach
  is a missing abstraction: extract it as a public function of its own module and test that.

## 4. Mocks: only at the system's edges

Classical (Detroit) school: the unit is a unit of *behaviour*, not a class; tests share real collaborators and are
isolated only from each other.

- Mock only **unmanaged out-of-process dependencies** - things other systems see: the model endpoint, Docker, the
  network, a remote registry. Stub them at the boundary (`sandbox_runner`, the chat model, `subprocess.run` for
  `docker`).
- **Managed dependencies** (our own files, the workspace on disk, the transcript, the contract under `.harness/`) are
  used for real, in `tmp_path`.
- Never mock our own modules to check how they talk to each other. A `monkeypatch.setattr(module, "helper", ...)` that
  replaces our own logic is acceptable only to cut off an unmanaged dependency behind it, and the test must then assert
  the outcome, not the call.
- Stubs feed input; mocks check output. Assert interactions only with the unmanaged dependency, and only the ones
  that leave the system (the docker argv, the request body sent to the model).

## 5. Styles, best first

1. **Output-based**: call a pure function, check its return value. Prefer it; design for it (functional core,
   imperative shell - the decision is a pure function, the I/O wraps it).
2. **State-based**: act, then check the state that results (files in the workspace, the ledger, the contract record).
3. **Communication-based**: check messages sent to an unmanaged dependency. Use only at the edge (§4).

## 6. Shape of one test

- Arrange-Act-Assert, one act per test. Several acts in a row is several tests - unless it is one scenario whose
  steps cannot be separated (a round, then the next round).
- Name it as a fact about the behaviour, in plain words: `test_a_unit_run_held_to_its_time_limit_says_so`, not
  `test_run_unit_tests_procedurally_error_branch`.
- The docstring says what went wrong in a measured run that this test guards (no run ids - AGENTS.md).
- Parameterise variants of one fact (`pytest.mark.parametrize`) rather than copying the test.
- Shared arrange goes in a builder (`tests/workflow_nodes.py`, `tests/workflow_node_stubs.py`, `tests/the_fix_stage.py`),
  not in a base class and not in a fixture that hides what the test is about.
- No `if` in a test. No sleeps for synchronisation; use a barrier or a returned value.

## 7. What earns no test

- Trivial code: a dataclass field, a constant, a one-line pass-through, a re-export.
- A plain wording change - a UI label, a log line, a comment (owner, 2026-11-17).
- Configuration values restated (a timeout equals 300) unless a measured failure hangs on the value.
- Code that exists only to make a test possible (code pollution): remove the hook and test through the public path.

What does keep a test even though it looks like text:

- **Prompt rules** (AGENTS.md): each new instruction to a model gets a test that the model is told it and a test that
  bans the words task, tasks, to-do, todo, button, click, checkbox. The prompt is observable behaviour - it is what the
  model reads.
- **Defect and note text a fixer reads**: assert the facts it must carry (the file, the line, the error), not its
  exact sentence.
- **Pack templates and sandbox images**: files the harness ships into a product or builds an image from.
- Repository guards that keep a whole-codebase rule (no run ids in code, prompt hygiene, product words ceiling).

## 8. Unit, integration, end-to-end here

- **Unit**: one behaviour, in memory, in milliseconds - a parser, a reader of runner output, a verdict rule.
- **Integration**: a graph node through `run_node` with the model stubbed; the sandbox with `subprocess.run` stubbed;
  a scaffold with a fake runner writing real files. Cover the longest happy path and every edge the unit tests cannot.
- **End-to-end**: a real run on a benchmark, scored by hidden tests - the loop's own job, not the suite's.
- Fail fast: an impossible state raises at once (or is refused with a reason), so it needs no test of every
  downstream symptom.

## 9. A fix's test (AGENTS.md)

Write it from the measured failure, run it against the old code, see it fail for the right reason, then fix. Assert
the behaviour the failure broke - not the line you changed.

## 10. Reviewing or reorganising the suite

For each test ask, in order: does it test observable behaviour (§3)? Would it survive a refactor (§2)? Does it guard
something §7 says needs no test? Then:

- **Keep** - a behaviour test, fast, readable.
- **Rework** - right behaviour, wrong method (reads source, mocks our own code): rewrite through the public path with
  the same facts asserted, and prove it with a meaning-changing mutation of the code.
- **Merge** - several tests of one fact: one parameterised test.
- **Delete** - pins text nothing reads, restates a constant, tests a mock, duplicates a stronger test.

Never weaken a test to make a refactor pass; never delete a test that is the only guard of a measured failure without
moving its assertion somewhere stronger.
