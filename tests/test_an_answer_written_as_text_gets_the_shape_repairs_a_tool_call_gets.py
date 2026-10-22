"""An answer written as text gets the shape repairs a tool call's arguments get.

One run's sprint planner wrote a whole plan six times, each a near miss:
`test_strategy` as a sentence where a list was wanted, `rollback_notes` as a
list where a line was, a dependency as the number 1, and fields the schema has
no place for (`open_questions`, `sprint`). Each was refused, the model was told
which fields were wrong and looped, and the run failed - its error saying the
stage had written nothing, of six replies of 78,000 to 129,000 characters.
"""
from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage

from app.agents.scrum_master import SprintPlanOutput
from app.agents.settled_answer import _answer_in, validated_leniently

PLAN = {
    "sprints": [
        {
            "sprint": 1,
            "goal": "The service starts and every note operation works end to end",
            "user_value": "Programs can store and read notes",
            "in_scope": ["notes_api/main.py", "notes_api/db.py"],
            "out_of_scope": ["Authentication"],
            "dependencies": [],
            "acceptance_criteria": ["AC-1", "AC-2"],
            "test_strategy": "Run the acceptance suite; a missing title answers 422.",
            "security_checks": "No secrets in code.",
            "documentation_work": "README names start.sh.",
            "risks": "SQLite file locking.",
            "rollback_notes": ["Stop the service and remove the data directory."],
            "open_questions": ["PORT at runtime"],
        },
        {
            "goal": "Persistence across restarts",
            "user_value": "Notes survive a restart",
            "in_scope": ["notes_api/db.py"],
            "dependencies": [1],
            "acceptance_criteria": ["AC-6"],
        },
    ]
}
LOOPED = "\n\n" + json.dumps(PLAN, indent=2) + "\n\nThe response is complete and valid.\n" * 200


def test_the_plan_the_planner_wrote_is_taken_as_its_answer():
    with pytest.raises(Exception):
        SprintPlanOutput.model_validate(PLAN)

    answer = _answer_in(AIMessage(content=LOOPED, response_metadata={"finish_reason": "length"}), SprintPlanOutput)

    assert answer is not None
    first, second = answer.sprints
    assert first.test_strategy == ["Run the acceptance suite; a missing title answers 422."]
    assert first.rollback_notes == "Stop the service and remove the data directory."
    assert second.dependencies == ["1"]


def test_each_repair_on_its_own_and_nothing_else_changes():
    from pydantic import BaseModel, ConfigDict

    class Shape(BaseModel):
        model_config = ConfigDict(extra="forbid")
        items: list[str] = []
        note: str = ""
        count: int = 0
        flag: bool = False

    got = validated_leniently(Shape, {"items": "one\n- two", "note": ["a", "b"], "count": 3, "extra": 1})

    assert got.items == ["one", "two"] and got.note == "a\nb" and got.count == 3
    with pytest.raises(Exception):
        validated_leniently(Shape, {"count": "three"})


def test_a_stage_whose_replies_had_text_is_not_told_it_wrote_nothing():
    from app.graph.workflow import _missing_structured_response

    cut = AIMessage(content="x" * 112_000, response_metadata={"finish_reason": "length"})
    empty = AIMessage(content="", response_metadata={"finish_reason": "length"})

    told = _missing_structured_response("scrum_master", {"messages": [cut]}, attempts=3)

    assert "before writing anything" not in told and "112,000 characters" in told
    assert "repetition penalty" in told
    assert "before writing anything" in _missing_structured_response("scrum_master", {"messages": [empty]}, attempts=3)


def test_an_object_that_is_not_an_answer_to_the_schema_is_not_repaired_into_one():
    from app.agents.specialists import SpecialistOutput

    with pytest.raises(Exception):
        validated_leniently(SpecialistOutput, {"name": "app", "version": "1.0.0"})
