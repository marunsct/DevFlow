"""After a sprint's attempt fails, the QA lead says which locked tests no right product could pass.

Measured on one run: a locked test added one item and expected two in the list
- "Expected: 2, Received: 1" on a page showing exactly the one it made - through
every round of a sprint's first attempt, while the product's fixers, who may not
change the suite, spent the rounds on it. No mechanical check sees that shape.
"""

from __future__ import annotations

import json
import re
from types import SimpleNamespace

from app.acceptance import suite
from app.agents.suite_dispute import SuiteDispute, _SYSTEM_PROMPT, build_dispute_request
from app.agents.suite_dispute import tests_it_names as named_by
from app.graph import acceptance_nodes, workflow

BANNED = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")


def _measured(root, **criteria) -> None:
    path = root / suite.RESULT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ran": True, "criteria": {
        cid: {"id": cid, "text": f"criterion {cid}", "status": status, "tests": [
            {"name": f"[{cid}] does it", "outcome": status, "message": "Expected: 2 Received: 1"},
        ]} for cid, status in criteria.items()
    }}))


class TestWhatTheQaLeadSays:
    def test_each_test_it_names_by_its_exact_name(self) -> None:
        answer = SuiteDispute(cannot_pass=[
            "[AC-5] filters - it adds one entry and expects two in the list",
            "[AC-99] invented - not a failing test",
        ])

        named = named_by(answer, ["[AC-5] filters", "[AC-2] marks"])

        assert named == [
            "`[AC-5] filters` cannot pass for any product that does what its criterion says: "
            "it adds one entry and expects two in the list. Fix the test so that it checks what "
            "the criterion says."
        ]

    def test_an_empty_answer_names_none(self) -> None:
        assert named_by(SuiteDispute(), ["[AC-5] filters"]) == []

    def test_the_request_shows_each_failure_and_the_code(self) -> None:
        text = build_dispute_request(
            [("[AC-5] filters", "AC-5: Filter by status", "Expected: 2\nReceived: 1")], "test('x')", "Brief"
        )["messages"][0]["content"]

        assert "### [AC-5] filters" in text and "Expected: 2" in text and "test('x')" in text

    def test_the_prompt_names_no_product(self) -> None:
        for word in BANNED:
            assert not re.search(rf"\b{word}\b", _SYSTEM_PROMPT.lower()), word


class TestWhenADisputeIsDue:
    @staticmethod
    def _state(root, **extra):
        return {
            "repository": SimpleNamespace(root_path=str(root)),
            "current_sprint_index": 4,
            "sprint_attempts": [{"sprint_index": 4, "status": "Failed"}],
            **extra,
        }

    def test_after_a_failed_attempt_with_locked_tests_failing(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(suite, "is_locked", lambda root: True)
        _measured(tmp_path, **{"AC-1": "passed", "AC-5": "failed"})

        assert workflow._a_dispute_is_due(self._state(tmp_path))
        assert [name for name, _, _ in workflow._the_locked_tests_still_failing(self._state(tmp_path))] == [
            "[AC-5] does it"
        ]

    def test_not_twice_for_one_sprint_nor_once_repairs_are_spent(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(suite, "is_locked", lambda root: True)
        _measured(tmp_path, **{"AC-5": "failed"})

        assert not workflow._a_dispute_is_due(self._state(tmp_path, disputed_sprints=[4]))
        assert not workflow._a_dispute_is_due(
            self._state(tmp_path, suite_repairs=acceptance_nodes.MAX_SUITE_REPAIRS)
        )

    def test_not_on_a_first_attempt_nor_when_nothing_fails(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(suite, "is_locked", lambda root: True)
        _measured(tmp_path, **{"AC-5": "failed"})

        assert not workflow._a_dispute_is_due(self._state(tmp_path, sprint_attempts=[]))
        _measured(tmp_path, **{"AC-5": "passed"})
        assert not workflow._a_dispute_is_due(self._state(tmp_path))


def test_a_suite_repaired_for_a_dispute_goes_back_to_the_sprint_s_planning(tmp_path) -> None:
    state = {"repository": SimpleNamespace(root_path=str(tmp_path)), "decisions": []}

    reopened = acceptance_nodes.reopen_the_suite_for(
        state, ["`[AC-5] filters` cannot pass"], return_to=acceptance_nodes.SPRINT_REPLAN
    )

    assert reopened["stage"] == "acceptance_author"
    assert reopened["acceptance_return_to"] == acceptance_nodes.SPRINT_REPLAN


def test_a_test_named_by_its_title_and_file_is_named() -> None:
    """The QA lead's own words on one run, right about all three, none reopened."""
    answer = SuiteDispute(cannot_pass=[
        "ac-ac5.spec.js: filter tasks by status cannot create second task via checkbox toggle",
        "ac-ac12.spec.js: filtering tasks by status shows correct items relies on two tasks but only one exists",
    ])

    named = named_by(answer, [
        "[AC-5] filter tasks by status",
        "[AC-12] filtering tasks by status shows correct items",
        "[AC-2] can toggle",
    ])

    assert [line.split("`")[1] for line in named] == [
        "[AC-5] filter tasks by status", "[AC-12] filtering tasks by status shows correct items",
    ]
    assert named[0].endswith("cannot create second task via checkbox toggle. Fix the test so that it checks what the criterion says.")
