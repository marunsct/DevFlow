"""A stage that keeps losing whole replies to reasoning stops being asked for it.

Measured on one run. A reviewing stage was visited three times, and each time
its first reply was 25,000 output tokens of reasoning with no text and no tool
call - seven and a half minutes that produced nothing. Each verdict came from
the call after, with thinking switched off, in under a minute. Every other
stage of that run reasoned for a few hundred tokens a reply.

The recovery after a cut-off reply starts from nothing on every visit, so the
third visit paid what the first two had already shown would be wasted. What is
remembered is per run and per stage: one runaway reply changes nothing, and a
stage that reasons to an answer is never touched.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from app.agents import thinking


class _Answer(BaseModel):
    summary: str


class _Request:
    def __init__(self, messages: list, model: Any, tools: list | None = None, settings=None):
        self.messages = messages
        self.model = model
        self.tools = tools if tools is not None else [SimpleNamespace(name="read_file")]
        self.model_settings = settings or {}

    def override(self, **changes: Any) -> "_Request":
        return _Request(
            changes.get("messages", self.messages),
            changes.get("model", self.model),
            changes.get("tools", self.tools),
            changes.get("model_settings", self.model_settings),
        )


def _local_model():
    from app.models import CompatibleChatOpenAI

    return CompatibleChatOpenAI(
        base_url="http://model-server:8888/v1", api_key="k", model="m", max_tokens=10
    )


def _spiral() -> AIMessage:
    return AIMessage(content="", response_metadata={"finish_reason": "length"})


@pytest.fixture(autouse=True)
def _a_run(monkeypatch):
    """One run, whose current stage visit the test names."""
    thinking.forget_the_replies_that_were_all_reasoning()
    where = {"run": "a-run", "visit": "visit-1"}
    monkeypatch.setattr(thinking, "_this_run_and_visit", lambda: (where["run"], where["visit"]))
    monkeypatch.setattr(thinking, "least_reasoning_effort", lambda model: "none")
    yield where
    thinking.forget_the_replies_that_were_all_reasoning()


def _sent(messages: list, stage: str = "a_reviewer") -> _Request:
    from app.agents.settled_answer import build_settled_answer_middleware

    seen: dict[str, _Request] = {}

    def handler(request: _Request) -> Any:
        seen["request"] = request
        return SimpleNamespace(result=[])

    middleware = build_settled_answer_middleware(_Answer, stage, step_limit=40)
    middleware.wrap_model_call(_Request(messages, _local_model()), handler)
    return seen["request"]


def _thinking_is_off(request: _Request) -> bool:
    extra = (request.model_settings or {}).get("extra_body") or {}
    return (extra.get("chat_template_kwargs") or {}).get("enable_thinking") is False


_FIRST_CALL = [HumanMessage(content="Review the specification.")]
_AFTER_A_SPIRAL = [*_FIRST_CALL, _spiral()]


def test_a_stage_that_has_not_spiralled_is_asked_as_configured() -> None:
    assert not _thinking_is_off(_sent(_FIRST_CALL))


def test_one_visit_that_spiralled_does_not_switch_the_next_one_off(_a_run) -> None:
    """A single runaway reply is not a pattern."""
    _sent(_AFTER_A_SPIRAL)
    _a_run["visit"] = "visit-2"

    assert not _thinking_is_off(_sent(_FIRST_CALL))


def test_after_two_visits_that_spiralled_the_third_starts_without_reasoning(_a_run) -> None:
    _sent(_AFTER_A_SPIRAL)
    _a_run["visit"] = "visit-2"
    _sent(_AFTER_A_SPIRAL)
    _a_run["visit"] = "visit-3"

    third = _sent(_FIRST_CALL)

    assert _thinking_is_off(third)
    assert third.model_settings["extra_body"]["reasoning_effort"] == "none"


def test_its_tools_are_kept(_a_run) -> None:
    """It is the stage's ordinary work, not the answer-only call after a spiral."""
    _sent(_AFTER_A_SPIRAL)
    _a_run["visit"] = "visit-2"
    _sent(_AFTER_A_SPIRAL)
    _a_run["visit"] = "visit-3"

    assert [tool.name for tool in _sent(_FIRST_CALL).tools] == ["read_file"]


def test_two_cut_off_replies_in_one_visit_count_once(_a_run) -> None:
    _sent(_AFTER_A_SPIRAL)
    _sent(_AFTER_A_SPIRAL)
    _a_run["visit"] = "visit-2"

    assert not _thinking_is_off(_sent(_FIRST_CALL))


def test_another_stage_is_not_affected(_a_run) -> None:
    _sent(_AFTER_A_SPIRAL)
    _a_run["visit"] = "visit-2"
    _sent(_AFTER_A_SPIRAL)
    _a_run["visit"] = "visit-3"

    assert not _thinking_is_off(_sent(_FIRST_CALL, stage="an_architect"))


def test_another_run_starts_afresh(_a_run) -> None:
    _sent(_AFTER_A_SPIRAL)
    _a_run["visit"] = "visit-2"
    _sent(_AFTER_A_SPIRAL)
    _a_run.update(run="another-run", visit="visit-1")

    assert not _thinking_is_off(_sent(_FIRST_CALL))


def test_outside_a_run_nothing_is_remembered(_a_run) -> None:
    _a_run.update(run=None)
    _sent(_AFTER_A_SPIRAL)
    _a_run["visit"] = "visit-2"
    _sent(_AFTER_A_SPIRAL)

    assert not thinking.reasoning_keeps_running_out_for("a_reviewer")
