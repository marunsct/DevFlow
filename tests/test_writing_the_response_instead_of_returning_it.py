"""A stage that tries to deliver its answer by writing a file.

Run d6297b2f died of this. `defect_fix_1_0` requested
`docs/structured_response.md` five times in a row, carrying

    {"role":"Testing and Quality Engineering Specialist","output":{...}}

as its content, and the loop guard stopped the run at 814 events. Twenty model
calls in that run went into writing that file; run a7150a6c spent eight more on
`structured_response.json`.

Nothing refused it before, because nothing renders a file of that name - it
fell through every guard precisely by not being one of the workflow's own
documents. The write is auto-approved, the workflow still has no structured
response, the stage is asked again, and it writes the same file again.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.repository import (
    RepositoryToolError,
    edit_approved_artifact,
    write_approved_artifact,
)

RESPONSE = '{"role":"Testing and Quality Engineering Specialist","output":{}}'


@pytest.mark.parametrize(
    "path",
    [
        "docs/structured_response.md",
        "docs/structured_response.json",
        "structured_response.md",
        "simple-to-do-list-app/structured_response.json",
    ],
)
def test_writing_the_response_as_a_file_is_refused(tmp_path: Path, path: str):
    with pytest.raises(RepositoryToolError) as raised:
        write_approved_artifact(tmp_path, path, RESPONSE)

    assert "returned, not written" in str(raised.value)


def test_the_refusal_says_what_to_do_instead(tmp_path: Path):
    """The loop is a stage that does not know how to finish; tell it."""
    with pytest.raises(RepositoryToolError) as raised:
        write_approved_artifact(tmp_path, "docs/structured_response.md", RESPONSE)

    message = str(raised.value)
    assert "Stop calling tools" in message
    assert "return the structured response now" in message


def test_editing_it_is_refused_the_same_way(tmp_path: Path):
    with pytest.raises(RepositoryToolError) as raised:
        edit_approved_artifact(
            tmp_path, "docs/structured_response.md", find="a", replace="b"
        )

    assert "returned, not written" in str(raised.value)


def test_a_file_that_merely_mentions_the_words_is_allowed(tmp_path: Path):
    """The guard is on the name, not on the content or on a lookalike."""
    (tmp_path / "proj").mkdir()

    result = write_approved_artifact(
        tmp_path,
        "proj/structured_response_helper.js",
        "export function parseStructuredResponse() {}\n",
    )

    assert result["status"] == "written"


def test_the_workflow_documents_are_still_refused_by_their_own_rule(tmp_path: Path):
    """The new guard runs first and must not swallow the existing one."""
    with pytest.raises(RepositoryToolError) as raised:
        write_approved_artifact(tmp_path, "docs/product_intake.md", "# mine\n")

    assert "structured response of the stage that produces it" in str(raised.value)
