"""Under `OPENING_ROOM_FOR_REVIEWS` a review whose opening fills its summary trigger is given its memory within its
room, and its request names only what is held (LF.1472).

Measured on one medium run (93K slot): the code review opened on a 9,585-character system prompt, 7,666 characters of
tool descriptions, a 46,781-character request and an 85,035-character memory - 1.16 of its summary trigger - and its
memory was sent whole, as every review's is (`render_for_a_review`); so were the lead's (173,770 characters in all).
The request, the system prompt and the workspace are that review's, rebuilt from the transcript; the tool
descriptions are stood in for by their measured size.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables.config import var_child_runnable_config

from app.agents import opening_room, project_memory, review_files

CAPTURED = json.loads((Path(__file__).parent / "captured" / "code_review_opening.json").read_text("utf-8"))
#: The run's slot: 91,776 tokens, 32,000 held for the reply.
WINDOW, REPLY = "91776", "32000"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


class _Request:
    def __init__(self, messages, system: str, tools: list):
        self.messages, self.model, self.tools = messages, None, tools
        self.system_message = SystemMessage(content=system)

    def override(self, messages):
        return _Request(messages, self.system_message.content, self.tools)


def _opened(tmp_path, monkeypatch, switch: str) -> tuple[str, list[dict]]:
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", WINDOW)
    monkeypatch.setenv("MODEL_MAX_OUTPUT_TOKENS", REPLY)
    monkeypatch.setenv("PROJECT_MEMORY", "on")
    monkeypatch.setenv("REQUEST_BUDGET_FOR_EVERY_STAGE", "off")
    monkeypatch.setenv("OPENING_ROOM_FOR_REVIEWS", switch)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    root = tmp_path / "workspace"
    for path, text in CAPTURED["files"].items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text, encoding="utf-8")
    size = CAPTURED["tool_schema_characters"]
    tools = [{"type": "function", "function": {"name": f"tool_{n}", "description": "x" * (size // 8 - 90),
                                               "parameters": {"type": "object", "properties": {}}}} for n in range(8)]
    request = _Request([HumanMessage(content=CAPTURED["opening_messages"][0])], CAPTURED["system_prompt"], tools)
    sent: list = []
    token = var_child_runnable_config.set({"configurable": {"app_stage": CAPTURED["stage"], "app_run_id": "run-review"}})
    try:
        project_memory.build_project_memory_middleware(str(root)).wrap_model_call(request, sent.append)
    finally:
        var_child_runnable_config.reset(token)
    path = tmp_path / "data" / "transcripts" / "run-review.jsonl"
    records = [r for r in map(json.loads, path.read_text().splitlines()) if r.get("kind") == "request_budget"]
    return sent[0].messages[0].content, records


def test_on_the_review_s_memory_is_cut_to_its_room_and_says_so(tmp_path, monkeypatch):
    whole, _ = _opened(tmp_path / "off", monkeypatch, "off")
    cut, records = _opened(tmp_path / "on", monkeypatch, "on")

    assert len(cut) < len(whole) - 30_000
    assert records[-1]["applied"] and "so the files it holds were cut to its budget" in records[-1]["message"]


def test_on_the_request_names_only_the_files_the_memory_holds(tmp_path, monkeypatch):
    cut, _ = _opened(tmp_path, monkeypatch, "on")
    named = review_files.held_named_in(cut[cut.index("--- Work orders in this batch ---"):])

    assert named
    assert all(f"=== {path} " in cut for path in named)


def test_off_the_review_s_memory_is_whole_as_before(tmp_path, monkeypatch):
    whole, records = _opened(tmp_path, monkeypatch, "off")

    assert opening_room.for_reviews_switch.ON_BY_DEFAULT is False
    assert records[-1]["sent"] == records[-1]["built"]


def test_what_it_says_uses_none_of_the_banned_words():
    assert not BANNED.search(opening_room.SAID_FOR_A_REVIEW + opening_room.for_reviews_switch.explanation)
