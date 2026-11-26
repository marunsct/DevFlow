"""A review's memory held to its room keeps the code under review over setup files (LF.1567, `OPENING_ROOM_FOR_REVIEWS`).

Measured on the code review the switch was built on (93K slot, an opening at 1.16 of its summary trigger): cut to its
room, the memory held the migration tool's environment script and migration, the manifest, and - outside the review
altogether - the tool's settings file, both requirements files, a package marker and a module nobody reviewed, while
it left out the batch's page, its two form components, its hook and its authentication module. Cut that way the
switch could not be measured: a smaller memory that drops the code it is about is not the same review. The request,
the system prompt and the workspace are that review's, rebuilt from the transcript.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables.config import var_child_runnable_config

from app.agents import project_memory, review_files

CAPTURED = json.loads((Path(__file__).parent / "captured" / "code_review_opening.json").read_text("utf-8"))
PROJECT = "task-management-dashboard/"


class _Request:
    def __init__(self, messages, system: str, tools: list):
        self.messages, self.model, self.tools = messages, None, tools
        self.system_message = SystemMessage(content=system)

    def override(self, messages):
        return _Request(messages, self.system_message.content, self.tools)


def _cut(tmp_path, monkeypatch) -> str:
    """The review's first call as sent with the switch on."""
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "91776")
    monkeypatch.setenv("MODEL_MAX_OUTPUT_TOKENS", "32000")
    monkeypatch.setenv("PROJECT_MEMORY", "on")
    monkeypatch.setenv("REQUEST_BUDGET_FOR_EVERY_STAGE", "off")
    monkeypatch.setenv("OPENING_ROOM_FOR_REVIEWS", "on")
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
    token = var_child_runnable_config.set({"configurable": {"app_stage": CAPTURED["stage"], "app_run_id": "run-cut"}})
    try:
        project_memory.build_project_memory_middleware(str(root)).wrap_model_call(request, sent.append)
    finally:
        var_child_runnable_config.reset(token)
    return sent[0].messages[0].content


def test_no_file_outside_the_review_is_held_whole(tmp_path, monkeypatch):
    sent = _cut(tmp_path, monkeypatch)
    under_review = set(review_files.held_named_in(CAPTURED["opening_messages"][0]))
    whole = [path for path in re.findall(r"^=== (\S+) ===$", sent, re.M) if not path.startswith("docs/")]

    assert under_review
    assert [path for path in whole if path not in under_review] == []


def test_the_batch_s_page_and_its_form_are_held_numbered(tmp_path, monkeypatch):
    sent = _cut(tmp_path, monkeypatch)

    assert f"=== {PROJECT}src/App.tsx (numbered lines, under review) ===" in sent
    assert f"=== {PROJECT}src/components/Login.tsx (numbered lines, under review) ===" in sent
