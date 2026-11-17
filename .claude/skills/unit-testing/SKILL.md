---
name: unit-testing
description: How tests are written, kept and removed in this harness, after Vladimir Khorikov's "Unit Testing Principles, Practices, and Patterns" (Manning, 2020). Load before writing a test for a fix, reviewing a test, or deleting/reworking tests in tests/ or langchain-ui/src/**/*.test.tsx.
---

# Unit testing in this harness

The principles below follow Vladimir Khorikov, *Unit Testing: Principles, Practices, and Patterns* (Manning, 2020),
in our own words, applied to this codebase: a LangGraph harness that builds products from a brief (graph nodes, a
sandbox that runs commands, stack packs, acceptance probes, prompts sent to models, a FastAPI app and a React UI).
Chapter references are given as (ch. N). Where AGENTS.md sets a rule, AGENTS.md wins.

## 1. Why a test exists (ch. 1)

The goal of the suite is sustainable growth: we can keep changing the harness quickly without regressions. A test is
code, and code is a liability, not an asset. It costs time to run, to read, to update on every refactor, and to
investigate when it raises a false alarm. Keep a test only when its value clearly exceeds those costs. A small
suite of valuable tests beats a large suite of mediocre ones, and no test is better than a bad test (ch. 7, ch. 8).

Coverage is a negative indicator only: low coverage means something is untested, but high coverage proves nothing.
An assertion-free test, or one that checks one of a function's several outputs, still counts as coverage (ch. 1).
Never add a test to raise a number.

## 2. The four pillars (ch. 4)

| Pillar | The question | In this harness |
|---|---|---|
| Protection against regressions | Would it fail if the behaviour broke? | It runs a meaningful amount of real code: a node, the sandbox, a probe, a pack's commands, including library code. |
| Resistance to refactoring | Does it stay green when the code is restructured but behaves the same? | It never reads `src/` as text, never pins a private name, never asserts which of our helpers was called. |
| Fast feedback | Is it quick? | No real model, no network, no sleeps. Real subprocesses only when the behaviour *is* the subprocess. |
| Maintainability | Is it short and easy to run? | Arrange is a few lines or a shared builder. No hand-tended external state. |

A test's value is the product of the four: zero on any one makes it worthless (ch. 4). The first three trade off
against each other. **Resistance to refactoring is not negotiable**: it is close to binary, and a test that breaks on
every refactor teaches people to ignore red. The real choice is between protection and speed, which is what separates
unit, integration and end-to-end tests (ch. 4, Test Pyramid).

False positives (red while the behaviour works) matter more as a code base grows, and this one is large. A false
positive comes from coupling to implementation details, so remove that coupling first (ch. 4).

Write tests black-box: from what the code is for. Read the code white-box only to find which branches the tests miss,
then test those branches through the behaviour (ch. 4).

## 3. Observable behaviour, never implementation details (ch. 5)

Code is observable behaviour when it gives a client an operation or a state that serves one of the client's goals.
Everything else is an implementation detail. In this harness, observable behaviour includes:

- a node's returned state update;
- the text of a defect or note that a fixer or the owner reads;
- the request body sent to a model;
- the argv and environment of a sandbox command;
- the files a scaffold writes or a release ships;
- a ledger entry, a score, an API response, what the UI renders for a given state.

Implementation details include private helpers, the order of internal calls, source text, and which module a function
lives in.

The following are forbidden in new tests, and are a reason to rework or delete old ones:

- **Reading source as text** (`Path(...).read_text()` on a `src/` file, `inspect.getsource`, `workflow_source()`) and
  asserting a string is in it. This is the book's most brittle example, a test that compares a class's source code to
  the "correct" version (ch. 4, listing 4.3). Call the code instead. Exceptions: files the harness ships as data (pack
  templates, Dockerfiles, prompts) and the repository guards in §7.
- **Asserting interactions between our own modules**, for example `assert_called_with` on our own helper (ch. 5).
- **Asserting interactions with a stub.** A stub feeds input. Checking that it was called is overspecification (ch. 5).
- **Exposing private state or methods only for a test** (ch. 11). Test them through the public behaviour that uses
  them. If a private function is too complex to reach that way, it is a missing abstraction: extract it as a public
  function of its own module and test that.
- **Leaking domain knowledge**, where the test recomputes the expected value with the same logic as the production
  code (ch. 11). Hard-code the expected result, worked out by other means.
- **Pinning exact wording** of text that no model and no product reads: log lines, comments, docstrings, UI copy.

## 4. Test doubles: only at the system's edges (ch. 2, 5, 8, 9)

This suite follows the classical (Detroit) school. A unit is a unit of *behaviour*, not a class. Tests may use many
real collaborators and are isolated only from each other (ch. 2). A test should tell a story a domain person would
recognise: "a unit run held to its time limit says so", not "helper X calls helper Y".

There are two kinds of out-of-process dependency (ch. 8):

- **Managed**: only the harness touches it, so its use is an implementation detail. Use the real one. In this harness
  that means the workspace on disk, `.harness/` contract files, the transcript, and the harness's own Postgres (use the
  real database engine, not an in-memory substitute — ch. 10).
- **Unmanaged**: other systems observe it, so what we send it is part of the contract. Mock it. In this harness that
  means the model endpoint, Docker, the network and package registries, and external services.

Rules for doubles:

- **Stubs** stand in for incoming data. **Mocks** check outgoing calls (ch. 5). Assert only on mocks of unmanaged
  dependencies, and only on calls that leave the system.
- **Mock at the very edge** (ch. 9). Assert on the last thing before the dependency, such as the actual `docker` argv
  or the actual request body to the model, not on an intermediate wrapper of ours.
- **Prefer a hand-written spy** (a small recording fake in `tests/`) to a mock library for edge dependencies. Spies
  shorten assertions and are reusable (ch. 9).
- **Check both directions**: the expected call happened, and no unexpected call happened, for example "exactly one
  container run" (ch. 9).
- **Don't rely on production code in assertions.** Compare against literals in the test, not against a constant
  imported from `src/`; otherwise the test checks nothing (ch. 9).
- **Mock only types we own** (ch. 9). Stub our own thin adapter (`sandbox_runner`, the chat-model factory), not deep
  internals of LangChain or Docker SDK objects.
- A `monkeypatch.setattr(our_module, "helper", ...)` that replaces our own logic is allowed only to cut off an
  unmanaged dependency behind it. The test must then assert the outcome, not the call.
- Never mock a concrete class to keep part of its behaviour (ch. 11). That signals two responsibilities in one class.

## 5. Styles and the four types of code (ch. 6, 7)

Prefer test styles in this order (ch. 6):

1. **Output-based**: call a pure function and check what it returns. This is the cheapest and least brittle style.
2. **State-based**: act, then check the resulting state (workspace files, the ledger, the contract record).
3. **Communication-based**: check messages sent to an unmanaged dependency. Use it only at the edge (§4).

Sort code by complexity or domain significance on one axis and number of collaborators on the other (ch. 7):

| | Few collaborators | Many collaborators |
|---|---|---|
| **Complex or domain-significant** | **Domain model and algorithms**: verdict rules, defect merging, runner-output readers, pack choice, scoring. Unit test thoroughly. | **Overcomplicated**: split it with the Humble Object pattern into a pure decision function plus a thin shell. Don't test it as it stands. |
| **Simple** | **Trivial**: dataclasses, constants, pass-throughs. Don't test. | **Controllers**: graph nodes and API routes that wire pieces together. Cover each with a few integration tests. |

When a fix lands in a big node, put the decision in a pure function (functional core) and let the node act on it
(mutable shell). Test the function output-based; the node needs only one integration test (ch. 6, 7). For conditional
logic in a controller, use the CanExecute/Execute pattern: a `can_x()` that the domain code also enforces as a
precondition. Use events or notes the domain returns, rather than the controller re-deriving them (ch. 7).

Test preconditions only when they have domain meaning, for example "a run never has a negative budget". Don't test
plumbing guards (ch. 7).

## 6. Shape of one test (ch. 3, 10)

- Use **Arrange, Act, Assert**, with one act per unit test. More than one act means more than one test. If the act
  needs two lines, that may reveal an API that leaks a step the caller must remember (ch. 3).
- **No `if` in a test** (ch. 3).
- **Name the test as a fact** in plain words a domain person could read: `test_a_unit_run_held_to_its_time_limit_says_so`.
  Don't name it after a method (`test_run_unit_tests_procedurally_error_branch`), and don't use "should" (ch. 3).
- The docstring says which measured failure the test guards. No run ids (AGENTS.md).
- **Parameterise** variants of one fact with `pytest.mark.parametrize`. Keep the positive case separate when the
  parameters stop saying which case is which (ch. 3).
- **Reuse arrange code through factory functions** that take what the test cares about as arguments, with defaults
  for the rest: an Object Mother such as `tests/workflow_nodes.py` `reported(...)` or `run_node(...)`. Don't use shared
  mutable fixtures, base-class setup, or constructor-time state. Changing one test's setup must never break another
  test (ch. 3, 10).
- Integration tests on the database: clean data at the **start** of the test, use a separate unit of work for each of
  arrange, act and assert, and don't run tests that share a database in parallel (ch. 10).

## 7. What earns no test

- **Trivial code** (ch. 7): a field, a constant, a one-line pass-through, a re-export.
- **A plain wording change**: a UI label, a log line, a comment (owner, 2026-11-17).
- **A configuration value restated** ("the timeout is 300"), unless a measured failure hangs on that value.
- **A failure that fails fast on its own** (ch. 8): if a mistake crashes at once and corrupts nothing, the crash is the
  test.
- **Code pollution** (ch. 11): flags or hooks in `src/` that exist only for tests. Remove the hook and test through the
  public path.
- **Diagnostic logging** (ch. 8). Logging only developers read is an implementation detail. Logs the owner relies on
  (support logging, such as the run log, sprint record and audit lines) are behaviour.
- **Simple reads** (ch. 10). Test only the complex or important ones. Writes carry the risk.
- **A repository or mapper on its own** (ch. 10). Cover it through the integration test that uses it.

These look like text but still earn a test:

- **Prompt rules** (AGENTS.md). Each new instruction to a model gets two tests: one that the model is told the rule,
  and one that the text avoids the banned words task, tasks, to-do, todo, button, click and checkbox. A prompt is
  observable behaviour, because it is what the model reads.
- **Defect and note text a fixer reads.** Assert the facts it must carry (the file, the line, the error), not its exact
  sentence.
- **Pack templates and sandbox images.** These are files the harness ships or builds from.
- **Repository guards** that enforce a codebase-wide rule: no run ids, prompt hygiene, the product-word ceiling.

## 8. Unit, integration, end-to-end here (ch. 2, 8)

- **Unit test**: one behaviour, fast, isolated from other tests. Examples: a parser, a runner-output reader, a
  verdict rule, defect merging.
- **Integration test**: a controller run for real with only unmanaged dependencies stubbed. Examples: a graph node
  through `run_node` with the model stubbed; the sandbox with `subprocess.run` stubbed and the docker argv asserted; a
  scaffold writing real files. Cover the longest happy path plus the edge cases that unit tests can't reach (ch. 8).
- **End-to-end test**: a real run on a benchmark, scored by hidden tests. That is the loop's job, not the suite's.

## 9. A fix's test (AGENTS.md)

1. Write the test from the measured failure.
2. Run it against the old code and see it fail for the right reason.
3. Fix the code.

Assert the behaviour the failure broke, not the line you changed.

## 10. Reviewing or reorganising the suite (ch. 4, 7)

For each test, ask in order:

1. Does it test observable behaviour (§3)?
2. Would it survive a refactor (§2)?
3. Does §7 say it earns no test?
4. Is it testing the right quadrant (§5)?

Then decide:

- **Keep**: a behaviour test that is fast and readable.
- **Rework**: the right behaviour tested the wrong way (reads source, mocks our own code, recomputes the expected
  value). Rewrite it through the public path with the same facts asserted. Prove the rework with a mutation of the
  code under test that changes its meaning: the test must fail.
- **Merge**: several tests of one fact become one parameterised test.
- **Delete**: pins text nothing reads, restates a constant, tests a mock, duplicates a stronger test, or covers
  trivial code.

Never weaken a test to make a refactor pass. Never delete the only guard of a measured failure without first moving
its assertion into a stronger test.
