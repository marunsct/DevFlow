"""Behind its switch, carried reasoning stays on every tool-calling reply after an answer, so no sent message changes.

Found in the launch review (LR.52): an answer ended the stretch the reasoning belongs to, so every earlier tool-calling
reply lost its carried reasoning at once and the prompt changed from there on - the largest cause of uncached input.
"""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from app import models


def _conversation():
    call = AIMessage(content="", tool_calls=[{"name": "read_file", "args": {"path": "a"}, "id": "1"}],
                     additional_kwargs={models.REASONING_FIELD: "I will read a first."})
    messages = [HumanMessage(content="go"), call, AIMessage(content="done")]
    dicts = [{"role": "user", "content": "go"}, {"role": "assistant", "content": ""}, {"role": "assistant", "content": "done"}]
    return messages, dicts


def test_off_the_reasoning_before_an_answer_is_dropped_as_before(monkeypatch):
    monkeypatch.delenv("REASONING_KEPT_AFTER_AN_ANSWER", raising=False)
    messages, dicts = _conversation()
    models.with_the_reasoning_carried(messages, dicts)
    assert dicts[1]["content"] == ""


def test_on_it_stays_so_the_sent_message_never_changes(monkeypatch):
    monkeypatch.setenv("REASONING_KEPT_AFTER_AN_ANSWER", "on")
    messages, dicts = _conversation()
    models.with_the_reasoning_carried(messages, dicts)
    assert dicts[1]["content"] == "I will read a first."
