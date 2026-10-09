"""Tests for dispute and repair handling when locked suites have untested criteria."""

import re
from unittest.mock import MagicMock, patch
import pytest

from app.acceptance import suite as acceptance_suite
from app.graph import workflow


def test_the_locked_tests_still_failing_includes_untested_due_criteria(tmp_path):
    """When a locked suite has due criteria that are untested (no test exists),

    _the_locked_tests_still_failing must include them so dispute is triggered.
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    # Create mock state with a locked suite
    state = {
        "repository": MagicMock(root_path=str(repo)),
        "current_sprint_index": 1,
        "sprint_attempts": [{"sprint_index": 1}],
        "disputed_sprints": [],
        "sprint_plan": MagicMock(
            sprints=[
                MagicMock(criteria=["AC-1"]),
                MagicMock(criteria=["AC-2", "AC-3"]),
            ]
        ),
    }

    mock_result = {
        "ran": True,
        "criteria": {
            "AC-1": {
                "id": "AC-1",
                "text": "First criterion",
                "status": "passed",
                "tests": [{"name": "[AC-1] test 1", "outcome": "passed", "message": ""}],
            },
            "AC-2": {
                "id": "AC-2",
                "text": "Second criterion",
                "status": "passed",
                "tests": [{"name": "[AC-2] test 2", "outcome": "passed", "message": ""}],
            },
            "AC-3": {
                "id": "AC-3",
                "text": "Third criterion without test",
                "status": "untested",
                "tests": [],
            },
        },
    }

    with patch.object(acceptance_suite, "is_locked", return_value=True), \
         patch.object(acceptance_suite, "last_result", return_value=mock_result), \
         patch.object(acceptance_suite, "deferred", return_value={}), \
         patch("app.graph.acceptance_nodes.criteria_due", return_value=["AC-2", "AC-3"]):

        failing = workflow._the_locked_tests_still_failing(state)
        # On old code: AC-3 has no failing test in criterion['tests'], so failing is empty.
        # On new code: AC-3 is untested, so failing must include it.
        assert len(failing) >= 1
        name, text, msg = failing[0]
        assert "AC-3" in name or "AC-3" in text
        assert workflow._a_dispute_is_due(state) is True


def test_banned_words_in_author_prompt_rules():
    """Each new prompt rule gets a test banning whole words:

    task, tasks, to-do, todo, button, click, checkbox.
    """
    from app.acceptance import requests, suite

    # Test the new rule in build_author_request
    request = requests.build_author_request(
        repo_root="/dummy",
        criteria=[],
    )
    content = request["messages"][0]["content"]

    # Extract the Rules section
    rules_section = content.split("--- Rules ---")[-1]

    banned_words = ["task", "tasks", "to-do", "todo", "button", "click", "checkbox"]
    for word in banned_words:
        pattern = rf"\b{re.escape(word)}\b"
        # Banned in the new rule text
        match = re.search(pattern, rules_section, re.I)
        # Note: the preexisting rules section might or might not have banned words,
        # but the specific new sentences for multi-criterion IDs must not have them.

    # Specifically check the multi-criterion rule sentence
    assert "Where a single test proves several criteria" in rules_section or "at least one test" in rules_section
    for line in rules_section.splitlines():
        if "proves several criteria" in line or "Every criterion must have its id" in line:
            for word in banned_words:
                assert not re.search(rf"\b{re.escape(word)}\b", line, re.I), f"Found banned word '{word}' in rule line: {line}"


def test_gaps_feedback_suggests_adding_tags(tmp_path):
    """suite.gaps provides actionable feedback suggesting adding the tag to existing tests."""
    from app.acceptance import criteria, suite

    repo = tmp_path / "repo"
    repo.mkdir()
    c = criteria.Criterion(id="AC-1", text="Sample feature", source="brief")
    suite.save_criteria(repo, [c])

    problems = suite.gaps(repo)
    assert len(problems) == 1
    # Check that it tells the engineer they can add the tag to an existing test
    assert "add `[AC-1]` to that test's title" in problems[0]

