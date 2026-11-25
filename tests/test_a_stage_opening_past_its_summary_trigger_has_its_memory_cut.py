"""A stage whose opening fills its summary trigger is given its memory cut to the request's budget (PA.1).

Measured on a medium run's first-sprint builders: a 21,451-character system prompt, 23,564 characters of tool
descriptions and a 134,786-character first message (the project memory 102,415 of it) - 47,124 tokens against a
summary trigger of 43,020. The backend builder was summarised 8 times in 48 replies and read one file 9 times; its
budget record said the memory would be cut from 128,334 characters to 76,313, and nothing was cut because
`REQUEST_BUDGET_FOR_EVERY_STAGE` is off. Small runs open past the budget too, with framing far from their trigger, and
stay as they are.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables.config import var_child_runnable_config

from app.agents import project_memory

#: A 91,776-token slot with 32,000 held for the reply: summary trigger 43,020 tokens, input budget 75,300 characters.
WINDOW, REPLY = "91776", "32000"
TARGET = 75_300
WORDS = "The service keeps each record with its owner and its time of change, and answers in the agreed shape. "
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _specification(sections: int, size: int) -> str:
    return "# Technical specification\n\n" + "".join(
        f"## AC-{n} The service record contract\n" + WORDS * (size // len(WORDS)) + "\n\n"
        for n in range(1, sections + 1))


class _Request:
    """A model call as the agent makes it: its messages, its system prompt and its tools."""

    def __init__(self, messages, system: str, tools: list):
        self.messages, self.model, self.tools = messages, None, tools
        self.system_message = SystemMessage(content=system)

    def override(self, messages):
        return _Request(messages, self.system_message.content, self.tools)


def _tool(n: int, size: int) -> dict:
    return {"type": "function", "function": {"name": f"tool_{n}", "description": "x" * size,
                                             "parameters": {"type": "object", "properties": {}}}}


def _opening_memory(root: Path, monkeypatch, *, system: int, tools: int, stage: str = "specialist_backend_1") -> str:
    """The memory a stage opens on, its request past its input budget, with a system prompt of `system` characters
    and `tools` characters of tool descriptions; `REQUEST_BUDGET_FOR_EVERY_STAGE` off."""
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", WINDOW)
    monkeypatch.setenv("MODEL_MAX_OUTPUT_TOKENS", REPLY)
    monkeypatch.setenv("PROJECT_MEMORY", "on")
    monkeypatch.setenv("REQUEST_BUDGET_FOR_EVERY_STAGE", "off")
    monkeypatch.setenv("DATA_DIR", str(root / "data"))
    (root / "docs").mkdir()
    (root / "docs" / "technical_specification.md").write_text(_specification(18, 3_000))
    (root / "service" / "app").mkdir(parents=True)
    (root / "service" / "manifest.toml").write_text("[project]\nname = 'service'\n")
    for name in ("records", "owners", "changes"):
        (root / "service" / "app" / f"{name}.py").write_text(f"# {name}\n" + "VALUE = 1\n" * 900)
    opening = ("--- Your work order ---\nWrite `service/app/items.py` so AC-3 passes.\n\n"
               "--- The specification for your files: build exactly to it ---\n" + WORDS * 100 + "\n")
    sent = []
    middleware = project_memory.build_project_memory_middleware(str(root))
    request = _Request([HumanMessage(content=opening)], "s" * system, [_tool(n, tools // 8) for n in range(8)])
    token = var_child_runnable_config.set({"configurable": {"app_stage": stage, "app_run_id": "run-opening"}})
    try:
        middleware.wrap_model_call(request, lambda r: sent.append(r))
    finally:
        var_child_runnable_config.reset(token)
    return sent[0].messages[0].content


def _records(root: Path) -> list[dict]:
    path = root / "data" / "transcripts" / "run-opening.jsonl"
    return [r for r in map(json.loads, path.read_text().splitlines()) if r.get("kind") == "request_budget"]


def test_a_builder_whose_prompt_and_tools_fill_its_trigger_opens_on_the_memory_cut_to_its_budget(tmp_path, monkeypatch):
    sent = _opening_memory(tmp_path, monkeypatch, system=21_000, tools=24_000)

    assert len(sent) <= TARGET
    # The specification as its outline and the section its request names.
    assert "=== docs/technical_specification.md (outline" in sent
    assert "## AC-3 The service record contract\n" + WORDS in sent
    assert "## AC-15 The service record contract\n" + WORDS not in sent
    record, = _records(tmp_path)
    assert record["applied"] is True and record["built"] > TARGET >= record["sent"]


def test_the_suite_writer_s_opening_is_cut_the_same_way(tmp_path, monkeypatch):
    sent = _opening_memory(tmp_path, monkeypatch, system=21_000, tools=24_000, stage="acceptance_author_2")

    assert len(sent) <= TARGET
    assert "## AC-15 The service record contract\n" + WORDS not in sent


def test_an_opening_with_room_left_before_its_trigger_is_as_today(tmp_path, monkeypatch):
    """The same request and memory with a small prompt: past the budget, short of the trigger, sent as built."""
    sent = _opening_memory(tmp_path, monkeypatch, system=2_000, tools=1_000)

    assert len(sent) > TARGET
    assert all(f"## AC-{n} The service record contract\n" + WORDS in sent for n in (1, 3, 15))
    record, = _records(tmp_path)
    assert record["applied"] is False and "message" not in record


def test_the_record_of_a_cut_by_size_says_why_and_is_not_counted_as_the_switch(tmp_path, monkeypatch):
    from app.observability import switch_firing

    _opening_memory(tmp_path, monkeypatch, system=21_000, tools=24_000)

    record, = _records(tmp_path)
    assert "summary trigger" in record["message"]
    assert switch_firing.fired([record]) == []
    assert not BANNED.search(record["message"])


def _memory_after_a_summary(root: Path, monkeypatch, *, system: int, tools: int) -> str:
    """A builder past its room that rewrote a file and was summarised: the memory of its call after the summary, when
    its memory is chosen again (LF.1288)."""
    from deepagents.backends import FilesystemBackend
    from langchain.agents.middleware.types import ModelRequest, ModelResponse
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage, ToolMessage

    from app.agents import stage_memory
    from app.agents.compaction import RequestKeepingSummarization

    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", WINDOW)
    monkeypatch.setenv("MODEL_MAX_OUTPUT_TOKENS", REPLY)
    monkeypatch.setenv("PROJECT_MEMORY", "on")
    monkeypatch.setenv("REQUEST_BUDGET_FOR_EVERY_STAGE", "off")
    monkeypatch.setenv("DATA_DIR", str(root / "data"))
    stage_memory.forget_everything()
    (root / "docs").mkdir()
    (root / "docs" / "technical_specification.md").write_text(_specification(12, 3_000))
    (root / "service" / "app").mkdir(parents=True)
    for n in range(12):
        (root / "service" / "app" / f"part{n:02}.py").write_text(f"def part{n:02}():\n    return {n}\n"
                                                                  + "# what it does\n" * 500)
    written = "service/app/part00.py"
    opening = HumanMessage(content="--- Your work order ---\nWrite `service/app/part00.py` so AC-3 passes.\n"
                                   + WORDS * 100, id="opening")
    middleware = project_memory.build_project_memory_middleware(str(root))
    framing = ("s" * system, [_tool(n, tools // 8) for n in range(8)])

    def call(messages):
        sent = []
        middleware.wrap_model_call(_Request(messages, *framing), lambda r: sent.append(r))
        return sent[-1].messages[0].content

    def summarised(messages):
        model = GenericFakeChatModel(messages=iter([AIMessage(content="The stage wrote its file.")] * 2))
        summary = RequestKeepingSummarization(model, backend=FilesystemBackend(root_dir=str(root)),
                                              trigger=("messages", 10), keep=("messages", 4),
                                              trim_tokens_to_summarize=1_000)
        seen = []

        def handler(request):
            seen.append(request.messages)
            return ModelResponse(result=[AIMessage(content="ok")])

        summary.wrap_model_call(ModelRequest(model=model, messages=messages, state={"messages": messages}, tools=[]),
                                handler)
        return seen[-1]

    token = var_child_runnable_config.set({"configurable": {"app_stage": "specialist_backend_1",
                                                            "app_run_id": "run-opening",
                                                            "thread_id": "specialist_backend_1-visit"}})
    try:
        call([opening])
        (root / written).write_text("def part00():\n    return 'written'\n")
        conversation = [opening]
        for n in range(3):
            conversation += [AIMessage(content="", id=f"ai{n}", tool_calls=[
                                 {"id": f"w{n}", "name": "write_artifact",
                                  "args": {"relative_path": written, "content": "x"}}]),
                             ToolMessage(content="written", tool_call_id=f"w{n}", id=f"t{n}")]
        conversation += [AIMessage(content="On.", id="on0"), HumanMessage(content="Go on.", id="h0"),
                         AIMessage(content="On.", id="on1"), HumanMessage(content="Go on.", id="h1")]
        return call(summarised(conversation))
    finally:
        var_child_runnable_config.reset(token)
        stage_memory.forget_everything()


def test_after_a_summary_the_memory_chosen_again_keeps_the_room_its_opening_was_given(tmp_path, monkeypatch):
    """Rendered whole again at its first summary, a builder cut at its opening was back past its trigger."""
    after = _memory_after_a_summary(tmp_path, monkeypatch, system=21_000, tools=24_000)

    memory = after.split("\n\nThe request this stage was given")[0]
    assert "=== service/app/part00.py (numbered lines) ===\n     1\tdef part00():\n     2\t    return 'written'" in memory
    # Within what the budget leaves beside its request of about 10,100 characters.
    assert len(memory) <= TARGET - 10_000


def test_after_a_summary_a_stage_with_room_is_given_its_memory_as_today(tmp_path, monkeypatch):
    after = _memory_after_a_summary(tmp_path, monkeypatch, system=2_000, tools=1_000)

    memory = after.split("\n\nThe request this stage was given")[0]
    assert "=== service/app/part00.py (numbered lines) ===" in memory
    assert len(memory) > TARGET
