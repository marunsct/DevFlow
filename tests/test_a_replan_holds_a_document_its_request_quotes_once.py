"""A lead's re-plan holds a document its request quotes whole once, in the request (LF.1566).

Measured on a re-plan under `LEAD_REPLAN_REQUEST_SMALLER`: the lead's request quoted the sprint plan under
`--- Approved sprint plan (/docs/sprint_plan.md) ---` while its memory held `docs/sprint_plan.md` whole again; the
rule that leaves such a document out (LF.1469) was applied to every opening but a re-plan's. The request is that
re-plan's and the workspace the files its memory held whole, both from the transcript.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables.config import var_child_runnable_config

from app.agents import project_memory, stage_memory

CAPTURED = json.loads((Path(__file__).parent / "captured" / "technical_lead_replan_opening.json").read_text("utf-8"))
SPRINT_PLAN = "docs/sprint_plan.md"


class _Request:
    def __init__(self, messages):
        self.messages, self.model = messages, None

    def override(self, messages):
        return _Request(messages)


def _replanned(tmp_path, monkeypatch, run: str):
    """The re-plan's memory middleware after its first call, and the text that call was sent."""
    # A window wide enough for the memory to hold every document whole, as the run's did.
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "131072")
    monkeypatch.setenv("PROJECT_MEMORY", "on")
    monkeypatch.setenv("LEAD_REPLAN_REQUEST_SMALLER", "on")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    root = tmp_path / "workspace"
    for path, text in CAPTURED["files"].items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text, encoding="utf-8")
    memory = project_memory.build_project_memory_middleware(str(root))
    sent: list = []
    token = var_child_runnable_config.set({"configurable": {"app_stage": "technical_lead", "app_run_id": run}})
    try:
        memory.wrap_model_call(_Request([HumanMessage(content=CAPTURED["opening_request"])]), sent.append)
    finally:
        var_child_runnable_config.reset(token)
    return memory, "\n".join(str(m.content) for m in sent[0].messages)


def test_the_re_plan_s_memory_does_not_hold_the_sprint_plan_its_request_quotes(tmp_path, monkeypatch):
    with stage_memory.remembering("a-re-plan"):
        _, sent = _replanned(tmp_path, monkeypatch, "run-replan-once")
    stage_memory.forget_everything()

    assert f"=== {SPRINT_PLAN} " not in sent
    assert project_memory.QUOTED_WHOLE_SAID + SPRINT_PLAN in sent
    assert sent.count("--- Approved sprint plan (/docs/sprint_plan.md) ---") == 1


def test_a_read_of_the_quoted_sprint_plan_is_pointed_at_the_request(tmp_path, monkeypatch):
    with stage_memory.remembering("a-re-plan-reading"):
        memory, _ = _replanned(tmp_path, monkeypatch, "run-replan-read")
        answer = memory.wrap_tool_call(
            SimpleNamespace(tool_call={"name": "read_file", "id": "r1", "args": {"file_path": "/" + SPRINT_PLAN}}),
            lambda request: ToolMessage(content="the file", tool_call_id="r1"))
    stage_memory.forget_everything()

    assert "quoted whole in your request" in answer.content
