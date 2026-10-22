"""A stage's structured response is not an artifact.

An agent asked for a structured response and given a write tool sometimes does
both: it writes the answer to disk and then returns it. The file is not a
product artifact, nothing reads it, and the stage has usually finished its real
work by then - so the write is followed by nothing, and the repeat guard ends
the run.

Measured on one run: `defect_fix_2_1` wrote `final_output.json` containing
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

# The real specialist schema, so the fixture cannot pass a case the
# production one would fail.
FIELDS = frozenset(
    {"changed_files", "decisions", "tests", "blockers", "verification",
     "defects", "documentation", "risks"}
)


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

    assert "writing_tools(resolved_repo_root, _answer_fields(response_format), response_format)" in (
        inspect.getsource(create_role_agent)
    )


def test_a_truncated_answer_is_still_recognised(write) -> None:
    """The case that matters most is the one that does not parse.

    One run wrote a 3,344-byte answer that ended `...}] }` - truncated,
    almost certainly against the output ceiling. `json.loads` raised, the check
    read that as "not the answer", and the write went through. It was then
    written four more times and the run died at 627 events.

    A model that ran out of room mid-answer is exactly the one about to write
    it again.
    """
    truncated = (
        '{"changed_files":["app.js"],"decisions":["did a thing"],'
        '"tests":[],"verification":[{"command":["node","--test"],'
        '"returncode":1,"stdout":"TAP version 13'
    )

    result = write.invoke({"relative_path": "docs/structured_response.json", "content": truncated})

    assert "structured response" in result["error"]


def test_nested_keys_do_not_count(write) -> None:
    """`verification: [{"command": ...}]` must not contribute `command`.

    Without depth-awareness the scan reads every quoted key in the file, and a
    data file with one schema word nested anywhere would be refused.
    """
    from app.tools.agent_toolkit import _top_level_keys

    text = '{"data":[{"tests":1,"decisions":2}],"other":{"blockers":3}}'

    assert _top_level_keys(text) == ["data", "other"]

    result = write.invoke({"relative_path": "p/data.json", "content": text})
    assert "error" not in result


def test_a_brace_inside_a_string_does_not_shift_the_depth() -> None:
    from app.tools.agent_toolkit import _top_level_keys

    text = '{"decisions":["it printed { and } oddly"],"tests":[]}'

    assert _top_level_keys(text) == ["decisions", "tests"]


def test_an_escaped_quote_inside_a_value_is_survived() -> None:
    from app.tools.agent_toolkit import _top_level_keys

    text = '{"decisions":["he said \\\\"no\\\\" twice"],"tests":[]}'

    assert _top_level_keys(text) == ["decisions", "tests"]
