"""Under `STEERING_AT_THE_TAIL` the owner's steering note goes after the transcript; the system message stays as it was (plan PX.5).

A note added mid-stage was appended to the system message, so every later
call carried a changed start and the server prefilled it again. Off, the
note is in the system message as before.
"""
from __future__ import annotations

import os
from unittest import mock

from langchain_core.messages import HumanMessage, SystemMessage

from app.plugins import middleware

NOTE = "\n\nThe owner's direction for this run: keep the API paths as the brief writes them."


class _Request:
    def __init__(self, system_message, messages):
        self.system_message, self.messages = system_message, messages

    def override(self, **changes):
        return _Request(changes.get("system_message", self.system_message), changes.get("messages", self.messages))


def _sent(tmp_path, switch):
    built = middleware.build_plugin_instructions_middleware(str(tmp_path), "backend")
    request = _Request(SystemMessage(content="You build the service."), [HumanMessage(content="Build it.")])
    sent = []
    with mock.patch.dict(os.environ, {"STEERING_AT_THE_TAIL": switch}), \
         mock.patch.object(middleware, "_extract_stack_keywords", lambda root: []), \
         mock.patch("app.server.steering.as_instructions", lambda root, stage, run: NOTE):
        built.wrap_model_call(request, lambda r: sent.append(r))
    return sent[0]


def test_on_the_note_is_the_last_message_and_the_system_message_is_unchanged(tmp_path):
    sent = _sent(tmp_path, "on")
    assert sent.system_message.content == "You build the service."
    assert sent.messages[-1] == {"role": "user", "content": NOTE.strip()}


def test_off_the_note_is_in_the_system_message_as_before(tmp_path):
    sent = _sent(tmp_path, "")
    assert NOTE.strip() in sent.system_message.content and len(sent.messages) == 1
