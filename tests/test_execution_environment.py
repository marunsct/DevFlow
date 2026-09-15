"""The stack selector must not choose a testing approach nothing can run.

Measured on run-3da8dd91: it selected "Manual (browser DevTools)" for a
client-side app. The technical lead faithfully delegated "Execute all Sprint 1
test cases manually in a browser against the completed index.html". The testing
specialist then found no browser - none is installed in the sandbox image and
none appears on any role's allowlist - and, unable to do the task yet told not
to substitute, began improvising an npm test harness instead.

Every stage behaved correctly given its input. The selection was impossible
from the start, and nothing in the pipeline knew what the sandbox could run.

A testing approach nothing can execute is not a testing approach: every later
stage that asks "did the tests pass?" gets no answer, and the milestone
reviewer treats an absent test run as a blocking finding.
"""

from __future__ import annotations

from app.agents.stack_selector import _SYSTEM_PROMPT, describe_execution_environment


def test_the_selector_is_told_there_is_no_browser():
    assert "NO browser and no display" in _SYSTEM_PROMPT


def test_the_selector_is_told_manual_testing_is_impossible():
    """Not merely inconvenient - there is no human looking at this workspace."""
    flat = " ".join(_SYSTEM_PROMPT.split())

    assert "'Manual browser testing' cannot be carried out here" in flat
    assert "no human sees this workspace either" in flat


def test_the_available_commands_are_listed():
    described = describe_execution_environment()

    assert "Available commands:" in described
    for command in ("jest", "pytest", "node" if "node" in described else "npm"):
        assert command in described


def test_the_list_comes_from_the_allowlist_not_a_copy():
    """Written out by hand it would drift from what the sandbox permits."""
    from app.tools.sandbox import allowed_executables

    described = describe_execution_environment()

    for command in allowed_executables("testing_specialist"):
        assert command in described, f"{command} is permitted but not described"


def test_no_browser_is_actually_available():
    """The premise of the whole rule. If this fails, the rule is now a lie."""
    from app.tools.sandbox import allowed_executables

    permitted = set()
    for role in ("testing_specialist", "ui_ux_specialist", "backend_specialist"):
        permitted |= allowed_executables(role)

    browsers = {"chromium", "chrome", "google-chrome", "firefox", "playwright", "puppeteer"}

    assert not (permitted & browsers), (
        "a browser is now available - update describe_execution_environment(), "
        "which currently tells the stack selector there is none"
    )


def test_the_selector_is_told_to_choose_something_that_runs():
    flat = " ".join(_SYSTEM_PROMPT.split())

    assert "runs headless and reports a pass or fail" in flat
    assert "unable to answer 'did this work?'" in flat


def test_the_old_browser_advice_is_gone():
    """It used to suggest a browser could execute tests without a framework."""
    assert "A browser and a language runtime" not in _SYSTEM_PROMPT


# --- the schema enforces what the prompt could not -----------------------
#
# The stack selector's prompt states, in as many words, that there is no
# browser and that "'Manual browser testing' cannot be carried out here by
# anyone". On run-78804673 it read that and chose "Manual browser testing".
#
# An instruction that has failed is not made truer by repetition. The same
# lesson as the architecture reviewer, which was told not to write a document
# and wrote one five times until the tool was taken away: remove the choice,
# do not argue for it.

import pytest
from pydantic import ValidationError

from app.agents.tools_models import TechnologyStack


def _stack(testing: str) -> TechnologyStack:
    return TechnologyStack(
        language="JavaScript", framework="none", database="localStorage",
        testing_framework=testing,
    )


@pytest.mark.parametrize(
    "impossible",
    [
        "Manual browser testing",
        "Manual (browser DevTools)",
        "Visual inspection by hand",
        "manual testing in the browser",
        "Browser testing with DevTools",
    ],
)
def test_an_unperformable_testing_approach_is_refused(impossible):
    with pytest.raises(ValidationError) as exc:
        _stack(impossible)

    assert "cannot be carried out in this environment" in str(exc.value)


@pytest.mark.parametrize("runnable", ["node:test", "pytest", "jest", "vitest"])
def test_a_runnable_approach_is_accepted(runnable):
    assert _stack(runnable).testing_framework == runnable


@pytest.mark.parametrize("absent", ["none", "None", "n/a", "", "nothing"])
def test_choosing_no_runner_is_refused(absent):
    """"None" is "manual testing" in a shorter word.

    Measured on run-2f252e4e: the selector answered "None", reasoning that
    "installing a test runner would consume the entire code budget", and
    shipped a checklist for a human who does not exist. `node --test` installs
    nothing and costs no lines, so there was no budget to consume.
    """
    with pytest.raises(ValidationError, match="A testing framework is required"):
        _stack(absent)


def test_the_refusal_says_what_to_choose_instead():
    """The model sees this message when it retries, so it has to be actionable."""
    with pytest.raises(ValidationError) as exc:
        _stack("Manual browser testing")

    message = str(exc.value)

    assert "runs headless and reports a pass or fail" in message
    # The message used to end "'none' is valid only if the product genuinely
    # needs no verification", which is the sentence the selector took up.
    assert "'none' is valid" not in message
    assert "install nothing" in message


def test_the_validator_explains_why_the_prompt_was_not_enough():
    import inspect

    # Wrapped across lines in the source, so compare without line breaks.
    source = " ".join(inspect.getsource(TechnologyStack).split())

    assert "run-78804673" in source
    assert "is not made truer by repetition" in source


def test_the_selector_prefers_a_runner_the_runtime_provides():
    """A runnable framework is not automatically the right one.

    The schema validator refuses testing approaches nothing can execute, which
    pushed run-cbd22a34 from "Manual browser testing" to Vitest - correct, but
    it installed 175 MB against a brief reading "No external dependencies
    beyond basic HTML/CSS/JS". `node --test` ships with the runtime, is on the
    testing specialist's allowlist, and passes the validator.

        run 2 (plain node harness)   46 MB workspace
        run 4 (vitest + jsdom)      221 MB workspace

    So the two rules are aligned: choose something that runs, and prefer the
    one that costs nothing to add.
    """
    from app.agents.stack_selector import _SYSTEM_PROMPT

    flat = " ".join(_SYSTEM_PROMPT.split())

    assert "Prefer a runner the runtime already provides" in flat
    assert "node --test" in flat
    assert "run-cbd22a34" in flat


def test_a_runtime_runner_still_passes_the_validator():
    """The preference is worthless if the schema then refuses the answer."""
    from app.agents.tools_models import TechnologyStack

    for runner in ("node --test", "node:test", "unittest"):
        stack = TechnologyStack(
            language="JavaScript", framework="none", database="localStorage",
            testing_framework=runner,
        )
        assert stack.testing_framework == runner
