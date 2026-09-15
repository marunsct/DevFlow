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
