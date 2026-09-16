"""The lead is told which role owns test files, and why it matters.

Only the `testing` specialist is given the validation tool that runs a suite;
every other role falls back on a raw terminal command, and it is the only role
told which runner this run's stack chose.

Measured across the stored transcripts: 18 of 143 delegated specialist tasks
were test-only work handed to another role, across 14 runs - most often
`backend`, including on products with no backend at all. On run d6297b2f that
stage ran 47 model calls, wrote its tests in a different module system from the
suite already in the project, and the testing specialist spent the next stage
undoing it.
"""

from __future__ import annotations

from app.agents.specialists import create_specialist_agent  # noqa: F401 - import guard
from app.agents.technical_lead import _SYSTEM_PROMPT

#: The prompt is line-wrapped, so a phrase may span a newline.
FLAT = " ".join(_SYSTEM_PROMPT.split())


def test_the_prompt_says_test_files_belong_to_the_testing_role():
    assert "Test files are the `testing` role's work" in FLAT


def test_it_says_this_holds_whatever_the_tests_cover():
    """A UI component's tests are testing work, not ui_ux work."""
    assert "whatever part of the product the tests cover" in FLAT


def test_it_gives_the_reason_the_role_matters():
    """A rule with no reason is one a model weighs against its own judgement."""
    assert "validation tool" in FLAT


def test_it_says_not_to_invent_work_for_an_absent_role():
    assert "has nothing to delegate" in FLAT


def test_only_the_testing_role_has_the_validation_tool():
    """The claim the prompt makes must stay true of the specialists."""
    import inspect

    from app.agents import specialists

    source = inspect.getsource(specialists)
    assert 'if role == "testing":' in source
    assert "build_validation_tool" in source
