"""An answer saved as a file is refused with what the schema would reject in it.

One run's `defect_fix_1_0` wrote its structured response to
`structured_response.json` three times. Each was refused as "your structured
response, not an artifact" - and each had `exitcode` where the schema has
`exit_code`, so returning it would have been refused too, and nothing said so.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from app.tools.agent_toolkit import build_artifact_write_tool, what_the_schema_would_refuse


class Run(BaseModel):
    command: list[str]
    exit_code: int


class Answer(BaseModel):
    changed_files: list[str]
    verification: list[Run]


NEAR_MISS = json.dumps({
    "changed_files": ["svc/main.py"],
    "verification": [{"command": ["pytest"], "exitcode": 0}],
})


def test_the_objection_names_the_field_and_the_likely_misspelling() -> None:
    assert what_the_schema_would_refuse(NEAR_MISS, Answer) == (
        "verification.0.exit_code: Field required (you wrote `exitcode`)"
    )


def test_a_valid_answer_or_no_schema_has_no_objection() -> None:
    valid = json.dumps({"changed_files": [], "verification": [{"command": ["pytest"], "exit_code": 0}]})
    assert what_the_schema_would_refuse(valid, Answer) == ""
    assert what_the_schema_would_refuse(NEAR_MISS, None) == ""


def test_the_refusal_carries_it(tmp_path: Path) -> None:
    tool = build_artifact_write_tool(str(tmp_path), frozenset(Answer.model_fields), Answer)
    result = tool.invoke({"relative_path": "structured_response.json", "content": NEAR_MISS})

    assert "Return your structured response now instead" in result["error"]
    assert "(you wrote `exitcode`)" in result["error"]
    assert not (tmp_path / "structured_response.json").exists()
