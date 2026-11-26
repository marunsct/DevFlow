"""The four readers a role agent is offered describe themselves as they work in this harness (TR.4).

Measured over 26 runs (tool review 2026-11-26): `ls`, `read_file`, `glob` and `grep` carried the library's own
descriptions in about 5,600 requests each. They said `read_file` reads 100 lines when it reads 400, sent `grep`'s
regular expressions to an `execute` tool no stage has, told the stage to list a folder before every `edit_file` (no
stage has that tool either), and promised images as content blocks to a model that reads none.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool

from tests.a_role_agent import Answer, Scripted, Stopped

BANNED = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")


class Recording(Scripted):
    """Records each offered tool as the model is sent it: name, description and argument schema."""

    sent: list[dict[str, Any]] = []

    def bind_tools(self, tools: Any, **kwargs: Any) -> "Recording":
        self.sent = [convert_to_openai_tool(tool)["function"] for tool in tools]
        return super().bind_tools(tools, **kwargs)


def _the_readers_as_sent(tmp_path, monkeypatch) -> dict[str, dict[str, Any]]:
    from langgraph.checkpoint.memory import InMemorySaver

    from app.agents.role_agent import create_role_agent

    monkeypatch.setattr("app.plugins.middleware.get_plugin_instructions", lambda keys, role: "")
    model = Recording(replies=[], requests=[], offered=[], sent=[])
    agent = create_role_agent(
        name="probe", stage="probe", system_prompt="You are the probe.\n", response_format=Answer,
        model=model, repo_root=str(tmp_path), checkpointer=InMemorySaver(),
    )
    with pytest.raises(Stopped):
        agent.invoke({"messages": [{"role": "user", "content": "go"}]}, {"configurable": {"thread_id": "t"}})
    return {tool["name"]: tool for tool in model.sent if tool["name"] in {"ls", "read_file", "glob", "grep"}}


def test_no_reader_names_a_tool_no_stage_is_offered(tmp_path, monkeypatch):
    readers = _the_readers_as_sent(tmp_path, monkeypatch)

    assert set(readers) == {"ls", "read_file", "glob", "grep"}
    for name, tool in readers.items():
        text = json.dumps(tool)
        for absent in ("edit_file", "write_file", "execute", "`rg"):
            assert absent not in text, (name, absent)


def test_read_file_states_the_window_it_really_reads(tmp_path, monkeypatch):
    read = _the_readers_as_sent(tmp_path, monkeypatch)["read_file"]

    assert "400 lines" in read["description"]
    assert "100 lines" not in read["description"]
    assert read["parameters"]["properties"]["limit"]["default"] == 400


def test_grep_says_it_answers_with_lines_and_matches_an_expression(tmp_path, monkeypatch):
    grep = _the_readers_as_sent(tmp_path, monkeypatch)["grep"]

    assert grep["parameters"]["properties"]["output_mode"]["default"] == "content"
    assert "regular expression" in grep["description"]
    assert "regular expression" in grep["parameters"]["properties"]["pattern"]["description"]
    assert "not regex" not in (grep["description"] + grep["parameters"]["properties"]["pattern"]["description"]).lower()


def test_no_reader_promises_images_or_says_to_read_speculatively(tmp_path, monkeypatch):
    readers = _the_readers_as_sent(tmp_path, monkeypatch)

    text = json.dumps(readers).lower()
    assert "multimodal" not in text
    assert "speculatively" not in text
    assert "almost always" not in text


def test_the_readers_descriptions_use_none_of_the_banned_words(tmp_path, monkeypatch):
    readers = _the_readers_as_sent(tmp_path, monkeypatch)

    text = json.dumps(readers)
    for word in BANNED:
        assert not re.search(rf"\b{re.escape(word)}\b", text, re.IGNORECASE), word
