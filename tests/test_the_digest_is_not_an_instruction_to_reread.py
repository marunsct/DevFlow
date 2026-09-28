"""After a stage's first call, the workspace digest is a status line, not a brief.

The digest is appended as the final message of every model call. That position
is right for the prefix cache - everything before it is unchanged from call to
call - but the last message is the one a model answers, and it ended "Read the
files you actually need." After a tool result, that is an instruction to read.

It was obeyed. On one run `specialist_backend_1` wrote `app.js` at 06:26:02
and then opened seven of its next nine turns as though arriving for the first
time - "Both files already exist from a prior run. Let me read ... and verify" -
re-issuing the same `read_file` pair, `wc -l`, `node --check` and `grep
innerHTML` while its history grew from 32 messages to 51. Across the twelve runs
before it, 20 to 49% of every `read_file` came back as content the stage
already had.

Nothing here is about any language: the digest lists whatever the workspace
holds.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents.workspace_digest import (
    _a_refresh,
    build_workspace_digest_middleware,
    render_workspace_digest,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "task-manager").mkdir()
    (tmp_path / "task-manager" / "app.js").write_text(
        "export function addTask(t) {\n  return t;\n}\n", encoding="utf-8"
    )
    (tmp_path / "task-manager" / "package.json").write_text('{"name": "x"}\n', encoding="utf-8")
    return tmp_path


class _Request:
    def __init__(self, messages: list) -> None:
        self.messages = messages

    def override(self, **changes):
        return _Request(changes.get("messages", self.messages))


def _last_message(messages: list, repo: Path) -> str:
    seen = {}

    def handler(final):
        seen["messages"] = final.messages
        return SimpleNamespace(result=[])

    build_workspace_digest_middleware(str(repo)).wrap_model_call(_Request(messages), handler)
    last = seen["messages"][-1]
    return last["content"] if isinstance(last, dict) else last.content


#: The production shape once a stage has acted: task, reply, tool result.
AFTER_A_TOOL_RESULT = [
    HumanMessage(content="Create app.js."),
    AIMessage(content="", tool_calls=[{"name": "read_file", "args": {"file_path": "a"}, "id": "c1"}]),
    ToolMessage(content="@@ lines 1-3 of 3 @@ ...", tool_call_id="c1"),
]


class TestTheOpeningCall:
    def test_it_still_says_to_read_what_you_need(self, workspace: Path) -> None:
        """Before the model has done anything, orienting it is the point."""
        last = _last_message([HumanMessage(content="Create app.js.")], workspace)

        assert "Read the files you actually need" in last

    def test_a_carried_summary_does_not_count_as_having_acted(self, workspace: Path) -> None:
        """A restart can put several messages in front of a stage that has done nothing."""
        opening = [HumanMessage(content="What the last attempt found..."), HumanMessage(content="Create app.js.")]

        assert "Read the files you actually need" in _last_message(opening, workspace)


class TestEveryLaterCall:
    def test_it_no_longer_tells_the_model_to_read(self, workspace: Path) -> None:
        """The regression: the instruction that was being obeyed."""
        last = _last_message(AFTER_A_TOOL_RESULT, workspace)

        assert "Read the files you actually need" not in last

    def test_it_says_it_is_not_a_new_request(self, workspace: Path) -> None:
        last = _last_message(AFTER_A_TOOL_RESULT, workspace)

        assert "not a new request" in last
        assert "carry on from where you left off" in last

    def test_it_is_still_current(self, workspace: Path) -> None:
        """The reason it is sent on every call at all: it shows what was just written."""
        (workspace / "task-manager" / "app.test.js").write_text("test\n", encoding="utf-8")

        assert "app.test.js" in _last_message(AFTER_A_TOOL_RESULT, workspace)

    def test_it_is_still_the_last_message(self, workspace: Path) -> None:
        """Moving it earlier would change the prompt prefix on every call and
        throw away the model server's prefix cache for the whole conversation."""
        last = _last_message(AFTER_A_TOOL_RESULT, workspace)

        assert last.startswith("The workspace as it stands now")

    def test_it_works_on_dict_messages_too(self, workspace: Path) -> None:
        as_dicts = [
            {"role": "user", "content": "Create app.js."},
            {"role": "assistant", "content": "ok"},
        ]

        assert "not a new request" in _last_message(as_dicts, workspace)


class TestTheDetection:
    @pytest.mark.parametrize(
        ("messages", "acted"),
        [
            ([], False),
            ([HumanMessage(content="x")], False),
            ([HumanMessage(content="x"), AIMessage(content="y")], True),
            ([{"role": "user", "content": "x"}], False),
            ([{"role": "assistant", "content": "y"}], True),
            ([{"type": "ai", "content": "y"}], True),
        ],
    )
    def test_an_ai_message_is_what_marks_a_later_call(self, messages, acted) -> None:
        assert _a_refresh(messages) is acted


class TestTheListingItselfIsUnchanged:
    def test_both_forms_carry_the_same_files(self, workspace: Path) -> None:
        opening = render_workspace_digest(workspace)
        refresh = render_workspace_digest(workspace, refresh=True)

        for name in ("task-manager/app.js", "task-manager/package.json"):
            assert name in opening and name in refresh

    def test_the_default_is_the_opening_form(self, workspace: Path) -> None:
        """Every existing caller keeps what it had."""
        assert "Read the files you actually need" in render_workspace_digest(workspace)
