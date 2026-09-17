"""A note the model has ignored twice is not a note that needs rewording.

`_an_edit_that_undoes_an_earlier_one` says an edit put the file back where it
was and lets it through. That is right the first time and the second: measured
across every stored transcript, of the three stages ever to receive the note,
two stopped after one.

The third is what this is for. Run 1ae7671d's `test_round_1` was told five
times and went on swapping a single line between four spellings - `++nextId`,
`nextId; nextId++`, `nextId++`, `current.length > 0 ? ... : 1` and back - for
eight edits, while the stage grew to the longest in the run.

The threshold and the reasoning are the no-op write refusal's.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents import stage_memory
from app.tools.repository import (
    RepositoryToolError,
    edit_approved_artifact,
    write_approved_artifact,
)
from app.tools import seen_content

START = "function f() {\n  let id = ++n;\n  return id;\n}\n"
BACK_AND_FORTH = [
    ("let id = ++n;", "let id = n++;"),
    ("let id = n++;", "let id = ++n;"),
    ("let id = ++n;", "let id = n++;"),
]


@pytest.fixture(autouse=True)
def _forget():
    seen_content.forget_everything()
    stage_memory.forget_everything()
    yield
    seen_content.forget_everything()
    stage_memory.forget_everything()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "p").mkdir()
    write_approved_artifact(tmp_path, "p/app.js", START)
    return tmp_path


def _oscillate(project: Path) -> None:
    for find, replace in BACK_AND_FORTH:
        edit_approved_artifact(project, "p/app.js", find=find, replace=replace)


def test_the_first_two_are_allowed_with_a_note(project: Path):
    """One reversal is ordinary; the note is the right response to it."""
    first = edit_approved_artifact(project, "p/app.js", find="let id = ++n;", replace="let id = n++;")
    second = edit_approved_artifact(project, "p/app.js", find="let id = n++;", replace="let id = ++n;")

    assert first["status"] == "edited"
    assert second["status"] == "edited"
    assert "back into a state it already had" in str(second)


def test_the_third_is_refused(project: Path):
    _oscillate(project)

    with pytest.raises(RepositoryToolError) as raised:
        edit_approved_artifact(project, "p/app.js", find="let id = n++;", replace="let id = ++n;")

    assert "told that twice already" in str(raised.value)


def test_the_refusal_says_to_look_somewhere_else(project: Path):
    """If the passage were the problem, one of the versions tried would have worked."""
    _oscillate(project)

    with pytest.raises(RepositoryToolError) as raised:
        edit_approved_artifact(project, "p/app.js", find="let id = n++;", replace="let id = ++n;")

    assert "look at a different part of the code" in str(raised.value)


def test_nothing_is_written_when_it_is_refused(project: Path):
    _oscillate(project)
    before = (project / "p" / "app.js").read_text(encoding="utf-8")

    with pytest.raises(RepositoryToolError):
        edit_approved_artifact(project, "p/app.js", find="let id = n++;", replace="let id = ++n;")

    assert (project / "p" / "app.js").read_text(encoding="utf-8") == before


def test_a_genuinely_new_state_still_applies(project: Path):
    """The refusal is for going backwards, not for editing the same passage."""
    _oscillate(project)

    result = edit_approved_artifact(
        project, "p/app.js", find="let id = n++;", replace="let id = crypto.randomUUID();"
    )

    assert result["status"] == "edited"


def test_the_count_is_kept_per_file(project: Path):
    _oscillate(project)
    write_approved_artifact(project, "p/other.js", "const a = 1;\n")

    result = edit_approved_artifact(project, "p/other.js", find="const a = 1;", replace="const a = 2;")

    assert result["status"] == "edited"
