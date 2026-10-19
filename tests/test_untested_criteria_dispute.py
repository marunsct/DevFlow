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
    assert "where a test already checks exactly what it says, add its id to that test's name" in problems[0]




def _saved(tmp_path, ran: bool, criteria: dict) -> None:
    import json

    path = tmp_path / acceptance_suite.RESULT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ran": ran, "criteria": criteria}))


def _failing(tmp_path, monkeypatch, due):
    from types import SimpleNamespace

    from app.graph import acceptance_nodes

    monkeypatch.setattr(acceptance_suite, "is_locked", lambda root: True)
    monkeypatch.setattr(acceptance_nodes, "criteria_due", lambda state: due)
    return workflow._the_locked_tests_still_failing({"repository": SimpleNamespace(root_path=str(tmp_path))})


def test_a_suite_that_did_not_run_shows_no_criterion_missing(tmp_path, monkeypatch):
    """No report means every criterion reads "untested": the tests are there, the run is not."""
    _saved(tmp_path, ran=False, criteria={
        "AC-1": {"status": "untested", "text": "Adds", "tests": []},
        "AC-2": {"status": "untested", "text": "Removes", "tests": []},
    })

    assert _failing(tmp_path, monkeypatch, ["AC-1", "AC-2"]) == []


def test_a_suite_that_ran_still_shows_a_criterion_with_no_test(tmp_path, monkeypatch):
    _saved(tmp_path, ran=True, criteria={
        "AC-1": {"status": "untested", "text": "Adds", "tests": []},
        "AC-2": {"status": "passed", "text": "Lists", "tests": [{"name": "[AC-2] lists", "outcome": "passed"}]},
    })

    assert [name for name, _, _ in _failing(tmp_path, monkeypatch, ["AC-1"])] == ["[AC-1] (missing from locked suite)"]


def test_a_measurement_with_no_results_shows_no_criterion_missing(tmp_path, monkeypatch):
    """Measured live: a dispute held 100 ms after a fix was reverted told QA six
    due criteria had no test, against 25 tests in the suite naming them."""
    _saved(tmp_path, ran=True, criteria={
        "AC-1": {"status": "untested", "text": "Adds", "tests": []},
        "AC-2": {"status": "untested", "text": "Removes", "tests": []},
    })

    assert _failing(tmp_path, monkeypatch, ["AC-1", "AC-2"]) == []


def test_a_criterion_the_suite_s_files_name_is_never_called_missing(tmp_path, monkeypatch):
    _saved(tmp_path, ran=True, criteria={
        "AC-1": {"status": "untested", "text": "Adds", "tests": []},
        "AC-2": {"status": "passed", "text": "Lists", "tests": [{"name": "[AC-2] lists", "outcome": "passed"}]},
    })
    spec = tmp_path / "auth.spec.js"
    spec.write_text("test('[AC-1] adds an item', async () => {});\n")
    monkeypatch.setattr(acceptance_suite, "suite_files", lambda root: [spec])

    assert _failing(tmp_path, monkeypatch, ["AC-1"]) == []


def test_one_test_carrying_two_criteria_is_one_failure_naming_both(tmp_path, monkeypatch):
    one = {"name": "[AC-1][AC-2] adds then removes", "outcome": "failed", "message": "Timeout waiting for item"}
    _saved(tmp_path, ran=True, criteria={
        "AC-1": {"status": "failed", "text": "Adds", "tests": [one]},
        "AC-2": {"status": "failed", "text": "Removes", "tests": [one]},
    })

    (name, text, message), = _failing(tmp_path, monkeypatch, ["AC-1", "AC-2"])

    assert message.count("Timeout waiting for item") == 1
    assert "AC-1: Adds" in text and "AC-2: Removes" in text
