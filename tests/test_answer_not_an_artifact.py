"""A stage's structured response is not an artifact.

An agent asked for a structured response and given a write tool sometimes does
both: it writes the answer to disk and then returns it. The file is not a
product artifact, nothing reads it, and the stage has usually finished its real
work by then - so the write is followed by nothing, and the repeat guard ends
the run.

Measured on run-2bcdc19b: `defect_fix_2_1` wrote `final_output.json` containing
`{"changed_files": [], "decisions": [...]}` - its own schema - five times in
twenty seconds. The second and later writes were answered "This file already
contained exactly this content ... Do not write it again; continue with your
response", and it wrote it three more times. The prompts say the same in words.
Both lost; only a refusal stopped it.
"""

from __future__ import annotations

import tempfile

import pytest

from app.tools.agent_toolkit import build_artifact_write_tool

FIELDS = frozenset({"changed_files", "decisions", "tests", "blockers"})


@pytest.fixture
def write():
    return build_artifact_write_tool(tempfile.mkdtemp(), FIELDS)


def test_the_answer_written_as_a_file_is_refused(write) -> None:
    result = write.invoke(
        {
            "relative_path": "final_output.json",
            "content": '{"changed_files": [], "decisions": ["could not run tests"]}',
        }
    )

    assert "structured response" in result["error"]
    assert "Nothing was written" in result["error"]
    # It must say what to do instead, or it is just another refusal.
    assert "Return your structured response now" in result["error"]


def test_the_path_does_not_matter(write) -> None:
    """A different name is the same answer. Matching on `final_output.json`
    would be a game of whack-a-mole with the model's naming."""
    result = write.invoke(
        {
            "relative_path": "simple-to-do-list-app/result.json",
            "content": '{"decisions": ["a"], "tests": ["b"]}',
        }
    )

    assert "structured response" in result["error"]


@pytest.mark.parametrize(
    ("path", "content"),
    [
        # A real manifest: none of its keys are schema fields.
        ("p/package.json", '{"name": "app", "version": "1.0.0"}'),
        # One matching key is not enough - a data file may share a word.
        ("p/data.json", '{"changed_files": []}'),
        # A key outside the schema means this is not the answer.
        ("p/fix.json", '{"changed_files": [], "decisions": [], "extra": 1}'),
        # Not JSON at all.
        ("p/app.js", "const changed_files = [];\nconst decisions = [];\n"),
        # A JSON array, not an object.
        ("p/list.json", '["changed_files", "decisions"]'),
    ],
)
def test_ordinary_files_are_written(write, path: str, content: str) -> None:
    result = write.invoke({"relative_path": path, "content": content})

    assert "error" not in result, result


def test_a_stage_with_no_schema_switches_the_check_off() -> None:
    """Some stages have no structured response; nothing to recognise."""
    unguarded = build_artifact_write_tool(tempfile.mkdtemp())

    result = unguarded.invoke(
        {"relative_path": "out.json", "content": '{"changed_files": [], "decisions": []}'}
    )

    assert "error" not in result


def test_the_fields_come_from_the_stage_schema() -> None:
    from pydantic import BaseModel, Field

    from app.agents.role_agent import _answer_fields

    class Out(BaseModel):
        changed_files: list[str] = Field(default_factory=list)
        decisions: list[str] = Field(default_factory=list)

    assert _answer_fields(Out) == frozenset({"changed_files", "decisions"})
    assert _answer_fields(None) == frozenset()


def test_every_writing_role_gets_the_check() -> None:
    import inspect

    from app.agents.role_agent import create_role_agent

    assert "writing_tools(resolved_repo_root, _answer_fields(response_format))" in (
        inspect.getsource(create_role_agent)
    )
