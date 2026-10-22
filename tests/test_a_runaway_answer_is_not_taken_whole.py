"""An answer read out of a runaway reply keeps each entry once.

One run's `defect_fix_1_0` ended with a reply that opened a correct response
object and then wrote the same lines of its `tests` list over and over - 100,189
characters - until the 25,000-token reply ceiling cut it off mid-string. The
object was closed, it validated, and it was taken as the answer with every
repetition in it.
"""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage

from app.agents.settled_answer import _answer_in, _without_repeats
from app.agents.specialists import SpecialistOutput
from app.graph.workflow import _answer_written_into_the_conversation

LOOP = [
    "tests/tasks.test.js - updateTask regression suite (9 new unit tests):",
    "  - updates the title of an existing task",
    "  - preserves createdAt when updating title/description",
    "",
]


def _runaway() -> str:
    head = (
        "```json\n{\n"
        '  "changed_files": ["app/tasks.js", "app/app.js"],\n'
        '  "decisions": ["Chose inline editing."],\n'
        '  "tests": [\n'
    )
    body = "".join(f"    {json.dumps(line)},\n" for line in LOOP * 400)
    # Cut off mid-string, as the ceiling left it.
    return head + body + '    "  - updates the ti'


def test_the_settled_answer_path_keeps_each_entry_once() -> None:
    answer = _answer_in(AIMessage(content=_runaway()), SpecialistOutput)

    assert answer is not None
    assert answer.tests[: len(LOOP)] == LOOP
    assert len(answer.tests) <= len(LOOP) + 1


def test_the_workflow_path_keeps_each_entry_once() -> None:
    result = {"messages": [AIMessage(content=_runaway())]}

    answer = _answer_written_into_the_conversation(result, SpecialistOutput)

    assert answer is not None
    assert len(answer.tests) <= len(LOOP) + 1
    assert answer.changed_files == ["app/tasks.js", "app/app.js"]


class TestTheCleaning:
    def test_order_and_first_occurrence_are_kept(self) -> None:
        assert _without_repeats(["b", "a", "b", "c", "a"]) == ["b", "a", "c"]

    def test_it_reaches_nested_lists(self) -> None:
        payload = {"defects": [{"steps": ["x", "x", "y"]}, {"steps": ["x", "x", "y"]}]}

        assert _without_repeats(payload) == {"defects": [{"steps": ["x", "y"]}]}

    def test_distinct_entries_are_all_kept(self) -> None:
        payload = {"tests": ["a", "b"], "risks": ["a"]}

        assert _without_repeats(payload) == payload

    def test_scalars_are_untouched(self) -> None:
        assert _without_repeats({"status": "approved", "count": 3}) == {
            "status": "approved",
            "count": 3,
        }
