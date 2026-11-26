"""A working stage's steps are held to a step's reasoning budget, not the stage's (LF.1593, `STEP_SIZED_REASONING_BUDGET`).

Measured live with a 20,000-token reasoning budget of a 32,000-token cap: an acceptance-suite author's replies of
17,427, 20,076, 20,078, 18,626, 17,636 and 20,755 output tokens, four to five minutes each, each ending in one small
call (`ls .venv`, `cat requirements-dev.txt`). The conversation below is that stage's, as its transcript recorded it
(`tests/captured/`, long arguments and results cut at 240 characters).
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.models import CompatibleChatOpenAI

CAPTURED = json.loads((Path(__file__).parent / "captured"
                       / "an-acceptance-author-s-steps-under-a-20000-token-reasoning-budget.json").read_text())
SERVER = "http://model-server:2001/v1"
MODEL = "a-reasoning-model.gguf"
NAME = "STEP_SIZED_REASONING_BUDGET"


@pytest.fixture(autouse=True)
def _a_server_measured_to_enforce_a_budget(monkeypatch, tmp_path):
    from app.models import named_answer, reasoning_budget

    monkeypatch.setattr(named_answer, "HONOURED", set())
    monkeypatch.setattr(reasoning_budget, "ENFORCED", set())
    monkeypatch.setattr(reasoning_budget, "OFF_BUDGETS", {})
    monkeypatch.setenv("REASONING_BUDGET", "on")
    monkeypatch.setenv(NAME, "on")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RUN_TRANSCRIPT", "on")
    reasoning_budget.learnt((SERVER, MODEL), SimpleNamespace(reasoning_budget=True, reasoning_budget_usable=True,
                                                             template_thinking_switch=True))


def _client(cap: int = 32_000) -> CompatibleChatOpenAI:
    return CompatibleChatOpenAI(model=MODEL, base_url=SERVER, api_key="k", max_retries=0, max_tokens=cap,
                                extra_body={"chat_template_kwargs": {"enable_thinking": True}})


def _loop() -> list[dict]:
    """The stage's agent loop as recorded: its replies (after the first request that offered tools) and results."""
    first = next(i for i, r in enumerate(CAPTURED) if r["kind"] == "model_request" and r["tools"])
    return [r for r in CAPTURED[first:] if r["kind"] in ("model_response", "tool_result")]


def _replies() -> list[tuple[AIMessage, list[ToolMessage]]]:
    """Each reply of the loop, rebuilt as the model client returned it, with the tool results that answered it."""
    turns: list[tuple[AIMessage, list[ToolMessage]]] = []
    for record in _loop():
        if record["kind"] == "model_response":
            calls = [{"name": c["name"], "args": c["args"], "id": f"call-{len(turns)}-{n}", "type": "tool_call"}
                     for n, c in enumerate(record["tool_calls"])]
            usage = record["usage"]
            reply = AIMessage(content=record["text"], tool_calls=calls, usage_metadata=usage,
                              response_metadata={"reasoning_chars": record["reasoning_chars"]})
            turns.append((reply, []))
        else:
            reply, results = turns[-1]
            call = reply.tool_calls[len(results)]
            results.append(ToolMessage(content=record["content"], tool_call_id=call["id"], name=call["name"]))
    return turns


def _opening() -> list:
    return [SystemMessage(content="You write the acceptance suite."), HumanMessage(content="Write the suite.")]


def _after(*replies: int) -> list:
    """The conversation once the given replies (1 is the stage's first) and their results are in."""
    turns = _replies()
    messages = _opening()
    for number in replies:
        reply, results = turns[number - 1]
        messages += [reply, *results]
    return messages


def _offered(*names: str) -> list[dict]:
    return [{"type": "function", "function": {"name": name, "description": name,
                                              "parameters": {"type": "object", "properties": {}}}} for name in names]


WORKING = _offered(*next(r["tools"] for r in CAPTURED if r["kind"] == "model_request" and r["tools"]))
READING = _offered("ls", "read_file", "glob", "grep", "ArchitectureReviewOutput")


def _budget(messages: list, tools: list[dict] = WORKING, cap: int = 32_000) -> int:
    payload = _client(cap)._get_request_payload(messages, tools=tools)
    return payload["extra_body"]["reasoning_budget_tokens"]


def test_a_step_that_follows_tool_results_is_held_to_a_step_s_budget():
    """The call that reasoned 20,076 tokens before `ls .venv`: it followed the results of a 95-token listing."""
    assert _budget(_after(1, 2, 3, 4)) == 8_000


def test_the_stage_s_first_call_keeps_the_stage_s_budget():
    assert _budget(_opening()) == 20_000


def test_a_call_where_only_the_answer_is_allowed_keeps_the_stage_s_budget():
    from app.models.named_answer import naming

    with naming("SpecialistOutput"):
        assert _budget(_after(1, 2, 3, 4)) == 20_000


def test_a_stage_offered_only_reads_and_its_answer_keeps_the_stage_s_budget():
    assert _budget(_after(1, 2, 3, 4), tools=READING) == 20_000


def test_a_step_cut_at_its_budget_that_only_read_raises_the_next_one():
    """The 17,427-token reply that ended in `ls` and `glob`: held to 8,000 it would have been cut and only read."""
    assert _budget(_after(1, 2)) == 16_000


def test_a_step_cut_at_its_budget_that_ran_a_command_does_not_raise_the_next_one():
    assert _budget(_after(1, 2, 3, 4, 5)) == 8_000


def test_a_step_after_one_that_was_not_cut_is_back_at_a_step_s_budget():
    assert _budget(_after(1, 2, 3)) == 8_000


def test_the_raises_never_pass_the_stage_s_budget():
    assert _budget(_after(1, 2, 2)) == 20_000


def test_the_raises_stop_after_two():
    """Replies whose reasoning the server ended (its words for that close the reasoning), each before one listing."""
    ended = ("x" * 400 + "\n\nI have reasoned enough about this. I will give my answer now, from what I have worked out "
             "above.")
    messages = _after(1)
    for number in range(3):
        call = {"name": "ls", "args": {"path": "."}, "id": f"ended-{number}", "type": "tool_call"}
        messages += [AIMessage(content="", tool_calls=[call], additional_kwargs={"reasoning_content": ended}),
                     ToolMessage(content="No files found", tool_call_id=call["id"], name="ls")]

    assert _budget(messages, cap=64_000) == 32_000


def test_with_the_switch_off_a_step_keeps_the_stage_s_budget(monkeypatch):
    monkeypatch.setenv(NAME, "off")

    assert _budget(_after(1, 2, 3, 4)) == 20_000


def test_the_run_s_transcript_says_when_a_stage_s_step_budget_changes_as_the_switch_acting(tmp_path):
    from app.observability import switch_firing, transcript

    with transcript.asked_for("acceptance_author_0", "run-r"):
        for replies in ((1, 2, 3, 4), (1, 2, 3, 4, 5), (1, 2)):
            _budget(_after(*replies))

    records = [json.loads(line) for line in (tmp_path / "transcripts" / "run-r.jsonl").read_text().splitlines()]
    steps = [r for r in records if r["kind"] == "step_reasoning_budget"]
    assert [(r["stage"], r["budget"]) for r in steps] == [("acceptance_author_0", 8_000), ("acceptance_author_0", 16_000)]
    assert NAME in switch_firing.fired(steps)


def test_the_effects_line_gives_each_stage_kind_s_steps_with_the_switch_off():
    from app.models.step_budget import effects_lines

    lines = effects_lines(CAPTURED)

    assert f"{NAME} off" in lines[0]
    assert lines[1].split() == ["acceptance_author:", "11", "replies,", "93,197", "reasoning,", "117,834", "output,",
                                "3", "at", "their", "budget"]


def test_the_effects_line_reads_the_step_budget_a_stage_was_sent_with_the_switch_on():
    from app.models.step_budget import effects_lines

    stage = "acceptance_author_0"
    held = [{"kind": "provenance", "stage": "", "switches_on": str(["REASONING_BUDGET", NAME])},
            {"kind": "reasoning_budget", "stage": stage, "message": "reasoning held to a budget of 20,000 tokens"},
            {"kind": "model_request", "stage": stage, "tools": ["ls", "write_artifact"]},
            {"kind": "model_response", "stage": stage, "usage": {"output_tokens": 300}, "reasoning_chars": 800},
            {"kind": "tool_result", "stage": stage},
            {"kind": "step_reasoning_budget", "stage": stage, "budget": 8_000,
             "message": "reasoning held to a step budget of 8,000 tokens of the stage's 20,000"},
            {"kind": "model_request", "stage": stage, "tools": ["ls", "write_artifact"]},
            {"kind": "model_response", "stage": stage, "usage": {"output_tokens": 8_100}, "reasoning_chars": 32_000}]

    lines = effects_lines(held)

    assert f"{NAME} on" in lines[0] and "step budgets sent: 1" in lines[0]
    assert lines[1].split() == ["acceptance_author:", "1", "replies,", "8,000", "reasoning,", "8,100", "output,",
                                "1", "at", "their", "budget"]
