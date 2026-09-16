"""One canonical copy of every document the workflow writes itself.

run-84e05d4b: a specialist wrote `simple-to-do-list-app/docs/architecture_review.md`,
a copy of the review the workflow had already rendered to
`docs/architecture_review.md` from the reviewer's structured decision. Two files
with the same name and different contents, in a workspace where every later
stage is told to read the documents - and only one of them is ever updated
again.
"""

from __future__ import annotations

import pytest

from app.tools.repository import (
    WORKFLOW_DOCUMENTS,
    RepositoryToolError,
    write_approved_artifact,
)


@pytest.mark.parametrize("name", sorted(WORKFLOW_DOCUMENTS))
def test_the_workflow_still_writes_its_own_document(tmp_path, name: str) -> None:
    """`_record_document` writes exactly here; nothing may block that."""
    assert write_approved_artifact(tmp_path, f"docs/{name}", "# Generated\n")["status"]


@pytest.mark.parametrize(
    "path",
    [
        "proj/docs/architecture_review.md",
        "proj/technical_specification.md",
        "notes/sprint_plan.md",
        "docs/archive/milestone_review.md",
        "security_review.md",
    ],
)
def test_a_copy_anywhere_else_is_refused(tmp_path, path: str) -> None:
    with pytest.raises(RepositoryToolError) as caught:
        write_approved_artifact(tmp_path, path, "# copy\n")

    message = str(caught.value)
    assert "written by the workflow itself" in message
    assert "Read 'docs/" in message, "the message must name where the real one is"


def test_a_specialists_own_document_is_unaffected(tmp_path) -> None:
    assert write_approved_artifact(tmp_path, "proj/docs/design_notes.md", "# mine\n")["status"]
    assert write_approved_artifact(tmp_path, "docs/README.md", "# readme\n")["status"]
    assert write_approved_artifact(tmp_path, "docs/testing_results.md", "# results\n")["status"]
