"""A specialist has to be told which stack the product is being built on.

It used to receive its task, its acceptance criteria, and nothing about the
technology. Each specialist then guessed, and reasonable guesses differ.

Measured on one run, whose stack selection was Python / FastAPI /
PostgreSQL / pytest / React, the project directory ended up holding two
complete, incompatible backends:

    package.json    express, jsonwebtoken, mongoose   <- MongoDB, not PostgreSQL
    src/routes/auth.js, src/index.js, src/database.js
    tests/auth.test.js                                <- jest, not pytest
    main.py         FastAPI
    requirements.txt fastapi, pydantic, uvicorn

Both were sensible answers to "build the authentication endpoints". Neither
specialist was told a database and a test framework had already been chosen.
"""

from __future__ import annotations

import pytest

from app.agents.specialists import build_specialist_task_request, describe_stack
from app.agents.tools_models import TechnologyStack

STACK = TechnologyStack(
    language="Python",
    framework="FastAPI",
    frontend_framework="React",
    database="PostgreSQL",
    testing_framework="pytest",
    additional_tools=["Docker Compose"],
)


def _brief(stack=STACK) -> str:
    request = build_specialist_task_request(
        "Build the authentication endpoints", ["login works"], "/ws", stack
    )
    return request["messages"][0]["content"]


def test_every_chosen_technology_reaches_the_specialist():
    brief = _brief()

    for chosen in ("Python", "FastAPI", "React", "PostgreSQL", "pytest", "Docker Compose"):
        assert chosen in brief, chosen


def test_the_specialist_is_told_not_to_substitute_its_own_choice():
    brief = _brief()

    assert "Do not introduce a different language" in brief
    assert "say so as a blocker rather than switching" in " ".join(brief.split())


def test_the_task_and_criteria_still_reach_it():
    brief = _brief()

    assert "Build the authentication endpoints" in brief
    assert "login works" in brief


def test_the_host_path_is_not_quoted_to_the_agent():
    """Inside the agent the workspace is rooted at `/`.

    Quoting the host path sends agents looking under a root that does not exist
    for them - measured as seven failed reads and one failed `ls` on
    one run, every one for a file that was present.
    """
    brief = _brief()

    assert "/ws" not in brief
    assert "rooted at '/'" in brief


def test_a_run_without_a_recorded_stack_still_works():
    """Older checkpoints and fixtures carry no stack selection."""
    brief = _brief(stack=None)

    assert "Build the authentication endpoints" in brief
    assert "already decided" not in brief


def test_an_empty_stack_adds_no_section():
    class _Blank:
        language = framework = frontend_framework = database = testing_framework = ""
        additional_tools: list[str] = []

    assert describe_stack(_Blank()) == ""


def test_a_client_only_stack_omits_the_frontend_line():
    # `node --test` rather than "none": a testing framework is now required,
    # because "none" was how one run shipped a human checklist instead of
    # a suite. This test is about the frontend line, not the runner.
    stack = TechnologyStack(
        language="JavaScript", framework="none", database="localStorage",
        testing_framework="node --test",
    )

    described = describe_stack(stack)

    assert "Frontend framework" not in described
    assert "Language: JavaScript" in described


# --- the sibling builders ------------------------------------------------
#
# Putting the stack in `build_specialist_task_request` alone was not enough.
# Observed live on one run, whose stack chose
# "testing_framework: None - manual browser testing against a written
# checklist (zero dependencies)": the test round reasoned "Let me create a
# comprehensive test suite using Jest" and ran
#
#     npm init -y
#     npm install --save-dev jest jsdom
#
# creating the dependency the brief had ruled out. The test round and the
# defect-fix round build their own requests, and neither carried the stack.

# "manual browser testing" is now refused by the schema - there is no browser
# and no person watching the workspace - so this models the realistic
# zero-dependency choice instead: the runtime's own test runner.
NO_TEST_STACK = TechnologyStack(
    language="JavaScript",
    framework="None - vanilla single-page app",
    database="Browser localStorage",
    testing_framework="node:test (no dependencies)",
)


def test_the_test_round_is_told_the_stack():
    from app.agents.specialists import build_test_run_request

    brief = build_test_run_request("Sprint 1", ["app.js"], "/ws", NO_TEST_STACK)
    content = brief["messages"][0]["content"]

    assert "node:test" in content
    assert "Browser localStorage" in content
    assert "/ws" not in content


def test_the_test_round_is_told_not_to_install_a_framework():
    from app.agents.specialists import build_test_run_request

    content = build_test_run_request("Sprint 1", [], "/ws", NO_TEST_STACK)["messages"][0]["content"]
    flat = " ".join(content.split())

    assert "Do not install a test framework" in flat
    assert "initialising a package manager" in flat
    assert "report that as a blocker instead of installing it" in flat


def test_the_defect_fix_round_is_told_the_stack():
    from app.agents.specialists import build_defect_fix_request

    content = build_defect_fix_request(
        "broken", "run it", "works", "fails", ["app.js"], True, "/ws", NO_TEST_STACK
    )["messages"][0]["content"]

    assert "node:test" in content
    assert "/ws" not in content


def test_both_builders_work_without_a_stack():
    """Older checkpoints carry none."""
    from app.agents.specialists import build_defect_fix_request, build_test_run_request

    assert "Sprint 1" in build_test_run_request("Sprint 1", [], "/ws")["messages"][0]["content"]
    assert "broken" in build_defect_fix_request(
        "broken", "r", "e", "a", [], False, "/ws"
    )["messages"][0]["content"]


def _stack(**overrides):
    """A complete TechnologyStack payload, so a test can vary one field."""
    from app.agents.tools_models import TechnologyStack

    base = {}
    for name, field in TechnologyStack.model_fields.items():
        annotation = str(field.annotation)
        if "list" in annotation:
            base[name] = []
        else:
            base[name] = "x"
    base["testing_framework"] = "pytest"
    base.update(overrides)
    return base


# --- "None" is the same answer as "manual" --------------------------------


@pytest.mark.parametrize("value", ["None", "none", "n/a", "na", "", "nothing", "-"])
def test_no_testing_framework_is_refused(value: str) -> None:
    """The previous message licensed it outright - it ended "'none' is valid
    only if the product genuinely needs no verification".

    Measured on one run: the selector answered "None", citing the size
    guidance that warns against *installed* runners, and shipped a checklist
    for a human who does not exist. A built-in runner costs nothing, so no
    product here needs no verification.
    """
    import pydantic

    from app.agents.tools_models import TechnologyStack

    with pytest.raises(pydantic.ValidationError, match="A testing framework is required"):
        TechnologyStack.model_validate(_stack(testing_framework=value))


@pytest.mark.parametrize("value", ["node --test", "pytest", "unittest", "vitest"])
def test_a_real_runner_is_accepted(value: str) -> None:
    from app.agents.tools_models import TechnologyStack

    assert TechnologyStack.model_validate(_stack(testing_framework=value))


def test_the_refusal_names_the_free_option() -> None:
    """A refusal a model cannot act on just moves the failure one step later."""
    import pydantic

    from app.agents.tools_models import TechnologyStack

    with pytest.raises(pydantic.ValidationError) as caught:
        TechnologyStack.model_validate(_stack(testing_framework="None"))

    message = str(caught.value)
    assert "ship a test runner with their runtime" in message
    assert "nothing to install" in message


def test_the_selector_is_told_the_size_argument_does_not_rule_out_testing() -> None:
    """It read "prefer a built-in runner over an installed one" and concluded
    "prefer no runner at all", quoting the dependency evidence back."""
    from app.agents.stack_selector import EXECUTION_ENVIRONMENT

    flat = " ".join(EXECUTION_ENVIRONMENT.split())

    assert "ARGUMENT FOR THE BUILT-IN RUNNER, NOT AGAINST TESTING" in flat
    assert "no size or dependency limit can rule it out" in flat
