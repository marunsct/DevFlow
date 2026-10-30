"""Behind `STABLE_STAGE_PREFIX` (off until measured), the start of a stage's calls is the same bytes call after call.

A server's prompt cache reuses a byte-identical prefix: the system prompt, then the opening messages with the project
memory. The memory was already taken once per visit; the instructions the plugins append to the system prompt were
read again on every call, so a stack document written mid-stage, an approved lesson or one failed keyword lookup (an
empty list for a call) rewrote the system prompt and the server prefilled the whole conversation again. On a model that
reports its cache, 71% of prompt tokens were served from it. Two consecutive calls of one stage, with a write and a
changed instruction between them, now build the same prefix up to the varying tail; and a small product's long
documents are held as their digest, so the memory is not mostly documents.
"""
from __future__ import annotations

import re
from unittest import mock

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents import project_memory, stable_prefix
from app.plugins import middleware

from tests.test_the_project_is_held_in_memory import workspace  # noqa: F401 - the fixture

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
SPEC = "You build the service."


class _Request:
    def __init__(self, system_message, messages, model=None):
        self.system_message, self.messages, self.model = system_message, messages, model

    def override(self, **changes):
        return _Request(changes.get("system_message", self.system_message), changes.get("messages", self.messages), self.model)


def _two_calls(workspace, monkeypatch, switch):  # noqa: F811
    """What the model was sent on two consecutive calls of one stage, a write and a changed instruction between them."""
    monkeypatch.setenv("STABLE_STAGE_PREFIX", switch)
    plugins = middleware.build_plugin_instructions_middleware(str(workspace), "backend")
    memory = project_memory.build_project_memory_middleware(str(workspace))
    sent = []
    texts = iter(["Use the framework's router.", "", "Use the framework's router.\nAnd lessons approved since."])

    def call(messages):
        request = _Request(SystemMessage(content=SPEC), messages)
        plugins.wrap_model_call(request, lambda r: memory.wrap_model_call(r, lambda m: sent.append(m)))

    with mock.patch.object(middleware, "_extract_stack_keywords", lambda root: ["fw"]), \
         mock.patch.object(middleware, "get_plugin_instructions", lambda keys, role: next(texts)), \
         mock.patch("app.server.steering.as_instructions", lambda root, stage, run: ""):
        call([HumanMessage(content="Fix it")])
        (workspace / "notes-api" / "src" / "store.ts").write_text("export const store = 2;\n")
        call([HumanMessage(content="Fix it")])   # the keyword lookup failed for a call: no instructions
        call([HumanMessage(content="Fix it")])   # and a lesson was approved since
    return sent


def _prefix(sent):
    return sent.system_message.content, sent.messages[0].content


def test_three_consecutive_calls_build_the_same_prefix_up_to_the_varying_tail(workspace, monkeypatch):  # noqa: F811
    calls = _two_calls(workspace, monkeypatch, "on")

    assert _prefix(calls[0]) == _prefix(calls[1]) == _prefix(calls[2])
    assert calls[0].system_message.content == f"{SPEC}\n\nUse the framework's router."
    # What a call adds is at the end of that call, after the transcript, and only what it adds.
    tails = [[m["content"] for m in call.messages[1:] if isinstance(m, dict)] for call in calls]
    assert not any(stable_prefix.ADDED_NOTE in text for text in tails[0] + tails[1])
    assert f"{stable_prefix.ADDED_NOTE}\nAnd lessons approved since." in tails[2]
    assert tails[1][-1].startswith("[Project memory update]")


def test_without_the_switch_the_system_prompt_changes_with_the_instructions(workspace, monkeypatch):  # noqa: F811
    calls = _two_calls(workspace, monkeypatch, "off")

    assert calls[0].system_message.content != calls[1].system_message.content
    assert calls[0].system_message.content != calls[2].system_message.content


def test_the_held_instructions_are_the_first_a_stage_read_and_a_changed_text_is_added_whole():
    held: dict = {}
    with mock.patch.dict("os.environ", {"STABLE_STAGE_PREFIX": "on"}):
        assert stable_prefix.held_instructions("", held) == ("", "")
        assert stable_prefix.held_instructions("A", held) == ("A", "")
        assert stable_prefix.held_instructions("A", held) == ("A", "")
        assert stable_prefix.held_instructions("", held) == ("A", "")
        assert stable_prefix.held_instructions("B", held) == ("A", f"{stable_prefix.ADDED_NOTE}\nB")
    with mock.patch.dict("os.environ", {"STABLE_STAGE_PREFIX": "off"}):
        assert stable_prefix.held_instructions("B", {}) == ("B", "")


def test_the_note_that_adds_instructions_carries_none_of_the_banned_words():
    assert not BANNED.search(stable_prefix.ADDED_NOTE)


def _long_spec():
    return "# Spec\n" + "".join(f"\n## Section {n}\n" + "line of the section\n" * 120 for n in range(12))


def test_a_small_product_holds_long_documents_as_their_digest(workspace, monkeypatch):  # noqa: F811
    (workspace / "docs" / "technical_specification.md").write_text(_long_spec())
    monkeypatch.setenv("STABLE_STAGE_PREFIX", "on")
    short, held = project_memory.render(workspace, 200_000)
    monkeypatch.setenv("STABLE_STAGE_PREFIX", "off")
    whole, _ = project_memory.render(workspace, 200_000)

    assert "outline and the sections this request points at" in short and "Outline:" in short
    assert len(short) < len(whole) / 2
    assert "export const store = 1;" in short and "export const store = 1;" in whole
    assert "notes-api/src/store.ts" in held


def test_a_product_of_twenty_files_or_more_keeps_its_documents_whole(workspace, monkeypatch):  # noqa: F811
    (workspace / "docs" / "technical_specification.md").write_text(_long_spec())
    for n in range(stable_prefix.SMALL_PRODUCT_FILES):
        (workspace / "notes-api" / "src" / f"module_{n}.ts").write_text(f"export const m{n} = {n};\n")
    monkeypatch.setenv("STABLE_STAGE_PREFIX", "on")
    memory, _ = project_memory.render(workspace, 400_000)

    assert "Outline:" not in memory and "## Section 11" in memory


def test_a_project_with_no_product_yet_keeps_its_documents_whole(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technical_specification.md").write_text(_long_spec())
    monkeypatch.setenv("STABLE_STAGE_PREFIX", "on")
    memory, _ = project_memory.render(tmp_path, 400_000)

    assert "## Section 11" in memory
    assert stable_prefix.document_limit({"docs/technical_specification.md": "x"}) is None


@pytest.mark.parametrize("switch", ["on", "off"])
def test_the_digest_of_a_document_is_the_same_bytes_for_the_same_request(workspace, monkeypatch, switch):  # noqa: F811
    (workspace / "docs" / "technical_specification.md").write_text(_long_spec())
    monkeypatch.setenv("STABLE_STAGE_PREFIX", switch)

    assert project_memory.render(workspace, 200_000, "Fix Section 3")[0] == project_memory.render(workspace, 200_000, "Fix Section 3")[0]
