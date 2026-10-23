"""A stage's old writes are shortened behind the kept tail, and - with `OBSERVATION_FOLDING` - its old long results folded.

`role_agent` configures argument shortening for exactly one reason: a
`write_artifact` call carries the whole file, and once written that copy is
redundant. deepagents shortens only `write_file` and `edit_file`, names no
stage here has, so it never fired: every file a stage wrote stayed whole in
every later request until the summariser ran.
"""
from __future__ import annotations

import re

from deepagents.backends import FilesystemBackend
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents import observation_folding
from app.agents.compaction import RequestKeepingSummarization

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
CONTENT = "line of the written file\n" * 400
RESULT = "a line the search returned\n" * 200


def _middleware(tmp_path, keep: int = 4):
    return RequestKeepingSummarization(
        GenericFakeChatModel(messages=iter([AIMessage(content="summary")])),
        backend=FilesystemBackend(root_dir=str(tmp_path)),
        trigger=("tokens", 10_000_000), keep=("messages", keep),
        truncate_args_settings={"trigger": ("messages", 3), "keep": ("messages", keep), "max_length": 2_000},
    )


def _conversation(turns: int) -> list:
    messages: list = [HumanMessage(content="Fix the defect.", id="h0")]
    for n in range(turns):
        messages.append(AIMessage(content="", id=f"a{n}", tool_calls=[
            {"id": f"w{n}", "name": "write_artifact", "args": {"relative_path": f"app/f{n}.py", "content": CONTENT}},
        ]))
        messages.append(ToolMessage(content=RESULT, tool_call_id=f"w{n}", name="search_text", id=f"t{n}"))
    return messages


def test_an_old_write_artifact_call_is_shortened(tmp_path):
    messages = _conversation(12)
    sent, modified = _middleware(tmp_path)._truncate_args(messages, 0)

    assert modified
    first = sent[1].tool_calls[0]["args"]
    assert first["relative_path"] == "app/f0.py"
    assert len(first["content"]) < 100
    # The kept tail is whole.
    assert sent[-2].tool_calls[0]["args"]["content"] == CONTENT


def test_a_small_conversation_is_sent_as_it_is(tmp_path):
    messages = _conversation(1)[:2]
    sent, modified = _middleware(tmp_path)._truncate_args(messages, 0)

    assert not modified and sent is messages


def test_the_boundary_moves_in_steps_so_the_opening_of_the_request_stays_the_same(tmp_path):
    """The model server reuses its cache only for an unchanged opening."""
    middleware = _middleware(tmp_path)
    one, _ = middleware._truncate_args(_conversation(12), 0)
    two, _ = middleware._truncate_args(_conversation(12) + _conversation(1)[1:], 0)

    assert [m.tool_calls for m in one[:20] if isinstance(m, AIMessage)] == \
           [m.tool_calls for m in two[:20] if isinstance(m, AIMessage)]
    assert observation_folding.boundary(25) == 20 and observation_folding.boundary(9) == 0


def test_old_long_results_are_folded_when_the_switch_is_on(tmp_path, monkeypatch):
    monkeypatch.setenv("OBSERVATION_FOLDING", "on")
    sent, modified = _middleware(tmp_path)._truncate_args(_conversation(12), 0)

    assert modified
    old = sent[2].content
    assert old.startswith(RESULT[:100]) and observation_folding.FOLDED in old and len(old) < 800
    assert sent[-1].content == RESULT  # the kept tail is whole


def test_results_are_kept_whole_when_the_switch_is_off(tmp_path, monkeypatch):
    monkeypatch.delenv("OBSERVATION_FOLDING", raising=False)
    sent, _ = _middleware(tmp_path)._truncate_args(_conversation(12), 0)

    assert all(m.content == RESULT for m in sent if isinstance(m, ToolMessage))


def test_a_short_result_is_never_folded(tmp_path, monkeypatch):
    monkeypatch.setenv("OBSERVATION_FOLDING", "on")
    messages = _conversation(12)
    for m in messages:
        if isinstance(m, ToolMessage):
            m.content = "exit 0"
    sent, _ = _middleware(tmp_path)._truncate_args(messages, 0)

    assert all(m.content == "exit 0" for m in sent if isinstance(m, ToolMessage))


def test_a_fold_lets_the_file_be_read_again_without_a_repeat_notice(monkeypatch):
    from app.agents import stage_memory

    monkeypatch.setattr(stage_memory, "current_stage_key", lambda: "thread-fold")
    stage_memory.store("repeated_reads", {})["app/f0.py"] = 3
    observation_folding.a_read_was_folded(2)

    assert stage_memory.store("repeated_reads", {}) == {}
    stage_memory.forget_everything()


def test_the_folded_line_uses_none_of_the_banned_words():
    assert not BANNED.search(observation_folding.folded_result("read_file", RESULT))
