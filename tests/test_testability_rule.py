"""The design rule that makes a headless test suite affordable.

Four runs of the same brief paid for its absence: the app entry point touched
the DOM at module scope, so nothing in it could be imported by a test. See
`app.agents.testability` for what each run spent.
"""

from __future__ import annotations

import pytest

from app.agents.testability import TESTABILITY_RULE


def _flat(text: str) -> str:
    """Prompt text wraps; wording assertions must not depend on where."""
    return " ".join(text.split())


def test_the_rule_names_the_thing_that_breaks_a_headless_test() -> None:
    flat = _flat(TESTABILITY_RULE)

    assert "module that reads or writes the DOM while it is being loaded" in flat
    # The wiring must not run on import. Asserted by the requirement rather than
    # by one phrasing of it, so strengthening the wording does not fail this.
    assert "Guard the call so importing the file does not run it" in flat


def test_every_specialist_that_writes_code_is_given_the_rule() -> None:
    """Not the one role that happened to hit it.

    The same mistake - fixing where a symptom appeared instead of the class it
    belonged to - has cost this workflow three separate runs.
    """
    from app.agents.specialists import _ROLE_DESCRIPTIONS, _system_prompt

    missing = [
        role.value if hasattr(role, "value") else str(role)
        for role in _ROLE_DESCRIPTIONS
        if _flat(TESTABILITY_RULE) not in _flat(_system_prompt(role))
    ]

    assert not missing, f"specialists without the testability rule: {missing}"


def test_the_architect_designs_against_it_too() -> None:
    """A boundary the specialists cannot draw after the fact."""
    from app.agents.principal_architect import _SYSTEM_PROMPT

    assert _flat(TESTABILITY_RULE) in _flat(_SYSTEM_PROMPT)


@pytest.mark.parametrize("phrase", ["document", "window", "localStorage"])
def test_the_rule_is_concrete_about_which_globals(phrase: str) -> None:
    """A rule that says 'be testable' changes nothing; naming the globals does."""
    assert phrase in TESTABILITY_RULE


def test_the_rule_requires_a_guarded_bootstrap() -> None:
    """The half that did not land on run-2b5def74.

    The application came back correctly shaped - pure functions, an adapter,
    every DOM reference inside `init()` - and still could not be imported,
    because `init()` was called bare at the end of the file.
    """
    flat = _flat(TESTABILITY_RULE)

    assert "typeof document !== 'undefined'" in flat
    assert "bare `init();` at the end of the file is the whole problem" in flat


def test_the_rule_requires_exports() -> None:
    """A test that cannot import the functions copies them, and a copy passes
    whatever the application does."""
    flat = _flat(TESTABILITY_RULE)

    assert "EXPORT the pure functions" in flat
    assert "a copy passes whatever your code does" in flat


def test_the_rule_says_a_module_system_is_not_a_dependency() -> None:
    """The decision that caused every copy-test in run-2b5def74.

    Its specification said "No module system (no ES modules, no CommonJS) -
    single global scope" and, two lines later, "Tests run with a single
    command: node --test tests/". Those cannot both hold - a runner can only
    test what it can import - and the reason given was a "no external
    dependencies" constraint that native modules never breached.
    """
    flat = _flat(TESTABILITY_RULE)

    assert "A MODULE SYSTEM IS NOT AN EXTERNAL DEPENDENCY" in flat
    assert "install nothing and add no package" in flat


def test_the_rule_explains_what_the_choice_costs() -> None:
    """A prohibition without its reason gets argued away by the next agent."""
    flat = _flat(TESTABILITY_RULE)

    assert "a test runner can only test what it can import" in flat


def test_the_rule_requires_the_logic_to_be_in_its_own_file() -> None:
    """run-2f252e4e specified pure functions, an adapter and an `init()` - the
    structural half of this rule, correctly - and then put all of it inside a
    `<script>` tag in a single `index.html`. Getting the shape right does not
    help if nothing can open the file."""
    flat = _flat(TESTABILITY_RULE)

    assert "THE LOGIC MUST LIVE IN A FILE A TEST CAN OPEN" in flat
    assert "no runner can import it" in flat


def test_the_rule_requires_the_module_type_to_be_declared() -> None:
    """run-da6c5e19 got everything else right and still could not be tested:
    ES module exports under a guarded bootstrap, in their own file, with
    nothing declaring what kind of file it was."""
    flat = _flat(TESTABILITY_RULE)

    assert "IF YOU USE `export`, DECLARE IT" in flat
    assert '{"type": "module"}' in flat
    assert "Neither installs anything" in flat


def test_the_rule_answers_the_copy_that_imports_the_module_anyway() -> None:
    """run-5d83e946 satisfied every structural clause and copied the code.

    It exported the pure functions, declared `{"type": "module"}`, guarded the
    bootstrap, and imported the real module nine times - to assert
    `typeof mod.addTask === 'function'` and nothing else, with every
    behavioural assertion running against inline copies. The standing clause
    ("if you find yourself writing 'this test defines the same logic inline'")
    addresses the case where importing is impossible; this run could import.
    """
    flat = _flat(TESTABILITY_RULE)

    assert "CALL THE FUNCTION YOU IMPORTED" in flat
    # Checking an export exists must be named as not-a-test, since that is the
    # spelling the copy hides behind.
    assert "has checked that an export exists, which is not testing it" in flat
    # And the excuse that produced it: an awkward-to-call function is a reason
    # to change the function, not to reimplement it in the test.
    assert "CHANGE THE FUNCTION, NOT THE TEST" in flat


def test_the_rule_asks_for_the_script_that_runs_the_tests() -> None:
    """Five of the nine delivered workspaces that ship a manifest alongside
    tests have no `test` script, so `npm test` answers "missing script: test".

    The cross-file check reports it at review and the reviewer has called it
    minor in every run it appeared in; sometimes a later sprint fixes it and
    sometimes it ships. Saying it where the manifest is written costs nothing.
    """
    flat = _flat(TESTABILITY_RULE)

    assert "MUST SAY HOW TO RUN THE TESTS" in flat
    assert '"scripts": {"test"' in flat
    assert "missing script: test" in flat


def test_the_rule_rejects_an_assertion_that_only_checks_it_did_not_throw() -> None:
    """Measured on run-44e9fc83: `saveTasks` was covered only by
    `doesNotThrow`, inside a describe block named "saveTasks + loadTasks
    round-trip", and replacing its whole body with `return tasks` left all 33
    tests passing. Persistence was an acceptance criterion of that brief.

    The copy-test detector is silent here - the suite imports the module
    correctly - and a static check for weak assertions was written, measured
    against mutation ground truth, and found to contradict it, so none shipped.
    """
    flat = _flat(TESTABILITY_RULE)

    assert "IT DID NOT THROW" in flat
    assert "doesNotThrow" in flat
    # The rule must give a test the specialist can apply itself, not just a
    # prohibition.
    assert "would any test fail" in flat
