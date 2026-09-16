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
    edit_approved_artifact,
    write_approved_artifact,
)


@pytest.mark.parametrize("name", sorted(WORKFLOW_DOCUMENTS))
def test_the_workflow_still_writes_its_own_document(tmp_path, name: str) -> None:
    """`_record_document` writes exactly here; nothing may block that."""
    assert write_approved_artifact(
        tmp_path, f"docs/{name}", "# Generated\n", by_the_workflow=True
    )["status"]


@pytest.mark.parametrize("name", sorted(WORKFLOW_DOCUMENTS))
def test_an_agent_cannot_change_one_at_the_canonical_path(tmp_path, name: str) -> None:
    """Succeeding would be no better than failing: the next run of the stage
    that produces it rewrites the file whole.

    run-84e05d4b's `specialist_documentation_2` spent six consecutive model
    calls and ninety seconds failing to edit `docs/tools_and_models.md`.
    """
    write_approved_artifact(tmp_path, f"docs/{name}", "# Generated\n", by_the_workflow=True)

    with pytest.raises(RepositoryToolError) as caught:
        write_approved_artifact(tmp_path, f"docs/{name}", "# mine\n")
    assert "rewrites it whole every time" in str(caught.value)

    with pytest.raises(RepositoryToolError):
        edit_approved_artifact(tmp_path, f"docs/{name}", "Generated", "Mine")

    assert (tmp_path / "docs" / name).read_text() == "# Generated\n"


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


# --- the near-miss spelling, between the exact name and an explicit _v2 ----


@pytest.mark.parametrize(
    "name", ["tech_specification.md", "technicalspecification.md", "tools_and_model.md"]
)
def test_a_name_a_reader_would_confuse_is_noted(tmp_path, name: str) -> None:
    """run-454adf22 wrote `docs/tech_specification.md`, 470 bytes, beside the
    workflow's `docs/technical_specification.md`, 5,847 bytes.

    The harm is the one `technical_specification_v2.md` caused: a reviewer with
    two specifications read the differences between them as contradictions,
    reported a blocking finding that existed only because the second file did,
    and the run stopped unresolved.
    """
    note = write_approved_artifact(tmp_path, f"docs/{name}", "# doc\n").get("note") or ""

    assert "very close to" in note


@pytest.mark.parametrize(
    "name",
    [
        "QA_report.md",
        "testing_results.md",
        "architecture_notes.md",
        "task_manager_test_plan.md",
        "README.md",
        "api_reference.md",
    ],
)
def test_a_document_of_its_own_is_not_nagged(tmp_path, name: str) -> None:
    note = write_approved_artifact(tmp_path, f"docs/{name}", "# doc\n").get("note") or ""

    assert "very close to" not in note


def test_a_note_and_not_a_refusal(tmp_path) -> None:
    """It cannot tell a careless near-duplicate from a deliberate companion:
    `security_review_notes.md` is a reasonable thing to write."""
    result = write_approved_artifact(tmp_path, "docs/security_review_notes.md", "# n\n")

    assert result["status"] == "written"
    assert (tmp_path / "docs" / "security_review_notes.md").is_file()


def test_the_note_reaches_an_edit_of_one_too(tmp_path) -> None:
    """This is the path that had no `relative_parts` and raised NameError."""
    write_approved_artifact(tmp_path, "docs/tech_specification.md", "# a\n# b\n")

    result = edit_approved_artifact(tmp_path, "docs/tech_specification.md", "# a", "# A")

    assert result["status"] == "edited"
    assert "very close to" in (result.get("note") or "")


def test_an_ordinary_document_edit_still_works(tmp_path) -> None:
    write_approved_artifact(tmp_path, "docs/notes.md", "# one\n# two\n")

    assert edit_approved_artifact(tmp_path, "docs/notes.md", "# one", "# ONE")["status"]


def test_the_refusal_names_the_channel_that_works(tmp_path) -> None:
    """The first version said "put your own work in a file of its own", and the
    model found the worst way round it.

    Refused the specification, `specialist_ui_ux_0` wrote
    `docs/specification_update.md` instead - in run-04576307 and again in
    run-01f03ed9, written once each and never read by anything. A specialist's
    `decisions`, `risks` and `blockers` reach the workflow and the next stage;
    a sibling document reaches nobody.
    """
    write_approved_artifact(
        tmp_path, "docs/technical_specification.md", "# spec\n", by_the_workflow=True
    )

    with pytest.raises(RepositoryToolError) as caught:
        write_approved_artifact(tmp_path, "docs/technical_specification.md", "# mine\n")

    message = str(caught.value)
    assert "`blockers`" in message and "`risks`" in message and "`decisions`" in message
    assert "reaches nobody" in message


# --- the way round the write refusal --------------------------------------


def test_a_workflow_document_cannot_be_moved_out_of_the_way(tmp_path) -> None:
    """How run-01f03ed9 got round the refusal.

    It moved `docs/architecture_review.md` to `docs/old_architecture_review.md`,
    which left the canonical path vacant, then wrote
    `docs/architecture_review_new.md` - allowed, because the file it would have
    superseded was no longer there. The workflow's own document was gone, and
    every stage that read it in between found nothing.
    """
    from app.tools.repository import move_approved_artifact

    write_approved_artifact(
        tmp_path, "docs/architecture_review.md", "# review\n", by_the_workflow=True
    )

    with pytest.raises(RepositoryToolError) as caught:
        move_approved_artifact(
            tmp_path, "docs/architecture_review.md", "docs/old_architecture_review.md"
        )

    assert "written by the workflow" in str(caught.value)
    assert "`blockers`" in str(caught.value)
    assert (tmp_path / "docs" / "architecture_review.md").is_file()


def test_nothing_can_be_moved_onto_a_workflow_document(tmp_path) -> None:
    """The other direction overwrites it just as thoroughly."""
    from app.tools.repository import move_approved_artifact

    write_approved_artifact(tmp_path, "docs/sprint_plan.md", "# plan\n", by_the_workflow=True)
    write_approved_artifact(tmp_path, "docs/notes.md", "# mine\n")

    with pytest.raises(RepositoryToolError):
        move_approved_artifact(tmp_path, "docs/notes.md", "docs/sprint_plan.md")

    assert (tmp_path / "docs" / "sprint_plan.md").read_text() == "# plan\n"


@pytest.mark.parametrize("name", sorted(WORKFLOW_DOCUMENTS))
def test_a_workflow_document_cannot_be_deleted(tmp_path, name: str) -> None:
    from app.tools.repository import delete_approved_artifact

    write_approved_artifact(tmp_path, f"docs/{name}", "# generated\n", by_the_workflow=True)

    with pytest.raises(RepositoryToolError) as caught:
        delete_approved_artifact(tmp_path, f"docs/{name}")

    assert "rewrites it whole" in str(caught.value)
    assert (tmp_path / "docs" / name).is_file()


def test_an_ordinary_file_still_moves_and_deletes(tmp_path) -> None:
    from app.tools.repository import delete_approved_artifact, move_approved_artifact

    write_approved_artifact(tmp_path, "proj/a.js", "export const a = 1;\n")

    assert move_approved_artifact(tmp_path, "proj/a.js", "proj/b.js")["status"] == "moved"
    assert delete_approved_artifact(tmp_path, "proj/b.js")["status"]
