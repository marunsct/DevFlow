"""The stack chose one runner and the specification chose the other.

Measured across the stored workspaces: 14 technical specifications name
Playwright and only 2 of their technology stacks agree. In the other 12 the
stack selector chose the built-in runner alone while the architect, reading
the same environment description, chose Playwright - and the architecture
reviewer then reported the two documents as a contradiction.

Seen live on run-83c41ea1, whose first architecture review opened with:

    technology_stack.md selects 'node --test' as the testing framework. The
    technical_specification.md (testing section and ADR-003) selects
    Playwright with detailed justification.

Neither stage was wrong. The environment description told the selector to
prefer a runner the runtime provides, and told it that Playwright is the
required way to test frontend UI - and never said how those combine. The
answer is both, which is what the delivered products actually contain:
run-ed05e20e shipped `app.test.mjs` under `node --test` and `app.spec.js`
under Playwright, and passed both.
"""

from __future__ import annotations

import pytest

from app.agents.stack_selector import describe_execution_environment
from app.agents.tools_models import TechnologyStack


@pytest.fixture(scope="module")
def environment() -> str:
    return describe_execution_environment()


def test_the_selector_is_told_a_ui_product_needs_both(environment: str):
    assert "NEEDS BOTH RUNNERS" in environment
    assert "naming both" in environment.lower()


def test_it_says_why_neither_runner_can_do_the_others_job(environment: str):
    """A rule with no reason is one a model argues itself out of."""
    assert "nothing built into a language runtime can open a page" in environment


def test_the_preference_for_a_built_in_runner_is_scoped(environment: str):
    """Unqualified, it is the instruction that produced the contradiction."""
    assert "does not remove the need for a browser" in environment
    # And the preference itself survives - it is right about logic.
    assert "ships with the language's runtime" in environment


def test_the_answer_the_prompt_recommends_actually_validates():
    """A prompt that recommends a value the schema rejects is worse than none."""
    stack = TechnologyStack(
        language="JavaScript",
        framework="Vanilla HTML/CSS/JavaScript",
        database="Browser localStorage",
        testing_framework="node --test for the logic, Playwright for the page",
    )

    assert "node --test" in stack.testing_framework
    assert "Playwright" in stack.testing_framework


@pytest.mark.parametrize(
    "answer",
    [
        "node --test and Playwright",
        "Playwright (page) + node --test (logic)",
        "pytest for the logic, Playwright for the page",
    ],
)
def test_every_shape_of_naming_both_is_accepted(answer: str):
    stack = TechnologyStack(
        language="Python",
        framework="FastAPI",
        database="PostgreSQL",
        testing_framework=answer,
    )

    assert stack.testing_framework == answer


def test_manual_testing_is_still_refused():
    """The rung this must not weaken."""
    with pytest.raises(Exception):
        TechnologyStack(
            language="JavaScript",
            framework="Vanilla",
            database="Browser localStorage",
            testing_framework="Manual browser testing via DevTools",
        )


def test_the_two_prompts_no_longer_disagree():
    """The page stack's guidance and the selector's environment, side by side.

    The specialists' browser guidance now lives in the seed row for a page, not
    in a rule every stack reads; the two must still name the same runner, and
    both must still want the built-in runner for the logic.
    """
    from app.plugins.seed import SEED_INSTRUCTIONS

    environment = describe_execution_environment()
    page = SEED_INSTRUCTIONS["html"]
    for text in (page, environment):
        assert "Playwright" in text, "both must name the browser runner"
    assert "built-in runner" in environment
    assert "node --test" in SEED_INSTRUCTIONS["javascript"]
