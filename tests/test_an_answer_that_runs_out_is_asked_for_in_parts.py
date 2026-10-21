"""An answer whose whole replies run out of room is asked for in parts, thinking left on (owner 2026-10-21).

One run's sprint planner wrote six whole replies of 33,000 tokens - reasoning
to the limit, or an answer that would not stop - and the run failed. A smaller
question is the lever that works on any model: the schema's fields a few at a
time, a list of objects one item at a time after an outline, each part seeing
the parts before it.
"""
from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.agents.answered_in_parts import answered_in_parts, parts_of
from app.agents.scrum_master import SprintPlanOutput


class PartWriter(BaseChatModel):
    """Answers each part from what the prompt asks for; keeps every prompt."""

    prompts: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "part-writer"

    def _generate(self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        prompt = str(messages[-1].content)
        self.prompts.append(prompt)
        asked = prompt.split("Write now:")[1]
        if "the outline of `sprints`" in asked:
            body: Any = {"items": ["The service and its notes", "Notes kept across restarts"]}
        elif (item := re.search(r"item (\d+) of", asked)):
            n = int(item.group(1))
            body = {"goal": f"Sprint {n} goal", "user_value": f"Value {n}", "test_strategy": "Run the suite.",
                    "dependencies": [n - 1] if n > 1 else []}
        else:
            body = {"open_questions": ["Which port?"], "success_measure_coverage": ["1: sprint 1"]}
        text = "<think>which fields</think>\n" + json.dumps(body) + "\nThat is the part."
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])


def test_a_plan_is_split_into_its_list_and_the_rest():
    assert parts_of(SprintPlanOutput) == [("sprints",), ("open_questions", "success_measure_coverage")]


def test_the_plan_is_written_an_outline_then_item_by_item_each_part_seeing_the_ones_before():
    model = PartWriter(prompts=[])

    plan = answered_in_parts(SprintPlanOutput, "Plan the sprints for the notes service.", model, "scrum_master")

    assert plan is not None
    assert [s.goal for s in plan.sprints] == ["Sprint 1 goal", "Sprint 2 goal"]
    assert plan.sprints[0].test_strategy == ["Run the suite."] and plan.sprints[1].dependencies == ["1"]
    assert plan.open_questions == ["Which port?"]
    outline, first, second, rest = model.prompts
    assert "Plan the sprints for the notes service." in outline
    assert "Sprint 1 goal" not in first and "Sprint 1 goal" in second and "Sprint 2 goal" in rest


def test_a_part_that_cannot_be_read_gives_no_answer():
    class SaysNothing(PartWriter):
        def _generate(self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="I cannot."))])

    assert answered_in_parts(SprintPlanOutput, "Plan the sprints.", SaysNothing(prompts=[]), "scrum_master") is None


def test_the_stage_asks_once_and_only_after_a_reply_that_ran_out():
    from app.graph import workflow

    class Agent:
        workflow_response_format = SprintPlanOutput
        workflow_model = PartWriter(prompts=[])

    request = {"messages": [{"role": "user", "content": "Plan the sprints."}]}
    finished = {"messages": [AIMessage(content="thinking", response_metadata={"finish_reason": "stop"})]}
    ran_out = {"messages": [AIMessage(content="x" * 50, response_metadata={"finish_reason": "length"})]}

    assert workflow._the_answer_in_parts("run-parts", "scrum_master", Agent(), request, finished) is None
    assert workflow._the_answer_in_parts("run-parts", "scrum_master", Agent(), request, ran_out) is not None
    assert workflow._the_answer_in_parts("run-parts", "scrum_master", Agent(), request, ran_out) is None


def test_the_part_prompts_use_none_of_the_banned_words():
    from app.agents import answered_in_parts as module

    banned = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
    model = PartWriter(prompts=[])
    answered_in_parts(SprintPlanOutput, "Plan.", model, "scrum_master")

    assert not banned.search(module._SYSTEM)
    for prompt in model.prompts:
        assert not banned.search(prompt.replace("Plan.", ""))


from pydantic import BaseModel as _Model


class _Decision(_Model):
    title: str
    decision: str


class _Spec(_Model):
    scope: str
    boundaries: str
    contracts: str
    files: str
    decisions: list[_Decision] = []


ECHO = {"scope": "SCOPE-TEXT-WRITTEN-EARLIER", "boundaries": "b", "contracts": "c", "files": "f"}


class SpecWriter(BaseChatModel):
    """Writes the scalar parts; for an item, echoes the earlier parts first - and, on the first ask, only them."""

    prompts: list[str] = []
    echo_only_first: bool = False

    @property
    def _llm_type(self) -> str:
        return "spec-writer"

    def _generate(self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        prompt = str(messages[-1].content)
        self.prompts.append(prompt)
        asked = prompt.split("Write now:")[1]
        if "the outline of `decisions`" in asked:
            text = json.dumps({"items": ["Store notes in SQLite"]})
        elif "item 1 of" in asked:
            again = "The last reply held no such object" in asked
            text = json.dumps(ECHO) if self.echo_only_first and not again else \
                json.dumps(ECHO) + "\n" + json.dumps({"title": "Storage", "decision": "SQLite under DATA_DIR"})
        else:
            text = json.dumps(ECHO)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])


def test_an_item_written_after_an_echo_of_the_parts_before_it_is_still_the_item():
    spec = answered_in_parts(_Spec, "Write the specification.", SpecWriter(prompts=[]), "principal_architect")

    assert spec is not None and spec.decisions[0].decision == "SQLite under DATA_DIR"


def test_an_item_that_came_back_as_an_echo_alone_is_asked_once_more_plainly():
    model = SpecWriter(prompts=[], echo_only_first=True)

    spec = answered_in_parts(_Spec, "Write the specification.", model, "principal_architect")

    assert spec is not None and spec.decisions[0].title == "Storage"
    assert any("Send only this part" in p for p in model.prompts)


def test_an_item_is_shown_the_names_of_the_parts_before_it_not_their_text():
    model = SpecWriter(prompts=[])
    answered_in_parts(_Spec, "Write the specification.", model, "principal_architect")

    item_prompt = next(p for p in model.prompts if "item 1 of" in p.split("Write now:")[1])
    assert "SCOPE-TEXT-WRITTEN-EARLIER" not in item_prompt and '"scope"' in item_prompt
