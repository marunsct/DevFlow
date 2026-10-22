"""A delegated task that asks a specialist to change a file it cannot.

`PROJECT_LAYOUT` tells the Technical Lead these documents belong to the
workflow. One run shows a prompt is not enough: the lead delegated
"update `docs/milestone_review.md` with the test results", and
`specialist_documentation_1` spent twelve model calls on it - writing a
`# Task Status` note four times, byte-identical, explaining that the task
required updating a file the tool refuses, and rewriting the technical
specification three more times.

Refusing the whole milestone plan over one task would cost the other five.
Telling the specialist, in the brief it actually reads, costs nothing.
"""

from __future__ import annotations

import pytest

from app.agents.specialists import build_specialist_task_request
from app.tools.repository import WORKFLOW_DOCUMENTS


def _brief(task: str, criteria: list[str] | None = None) -> str:
    return build_specialist_task_request(task, criteria or [], "/")["messages"][0]["content"]


@pytest.mark.parametrize("name", sorted(WORKFLOW_DOCUMENTS))
def test_every_workflow_document_is_recognised(name: str) -> None:
    brief = _brief(f"Update docs/{name} with the latest results.")

    assert f"--- About docs/{name} ---" in brief
    assert "You cannot change it" in brief
    assert "`decisions`" in brief


def test_the_measured_task(tmp_path) -> None:
    brief = _brief(
        "Update docs/milestone_review.md with the test results for this milestone.",
        ["The file reflects the latest run"],
    )

    assert "docs/milestone_review.md" in brief
    assert "A note saying the task could not be done adds nothing" in brief


def test_a_document_named_only_in_the_criteria_is_caught(tmp_path) -> None:
    brief = _brief(
        "Record the outcome of this milestone.",
        ["docs/milestone_review.md lists every test that ran"],
    )

    assert "--- About docs/milestone_review.md ---" in brief


@pytest.mark.parametrize(
    "task",
    [
        "Write index.html with a task list and filter buttons.",
        "Add docs/README.md describing how to run the app.",
        "Update docs/testing_results.md with what the suite covers.",
        "Implement addTask and deleteTask in app.js.",
    ],
)
def test_an_ordinary_task_is_not_nagged(task: str) -> None:
    assert "--- About" not in _brief(task)


def test_two_documents_are_both_named() -> None:
    brief = _brief("Reconcile docs/sprint_plan.md against docs/milestone_plan.md.")

    assert "docs/milestone_plan.md, docs/sprint_plan.md" in brief
