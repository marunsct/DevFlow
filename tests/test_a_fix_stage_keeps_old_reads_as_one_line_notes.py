"""A fix stage keeps old reads as one-line notes and is not summarised by a model (plan FX.4, LF.1420).

Measured on one medium run's three failing fixers: 63 of 91 reads were reads again of a file that had not changed.
Each fixer was summarised twice; the first summary freed no room (41,578 tokens before it, 42,243 after), kept
descriptions of the files instead of what the fixer had found, and added a false lead the next steps followed.
"""
from __future__ import annotations

import re

import pytest
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deepagents.backends import FilesystemBackend
from deepagents.backends.utils import format_content_with_line_numbers

from app.agents import old_reads_stubbed
from app.agents.compaction import RequestKeepingSummarization
from app.observability import transcript

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
SUMMARY = "The fixer read the files."


@pytest.fixture(autouse=True)
def _a_fix_stage(monkeypatch):
    monkeypatch.setattr(transcript, "_stage_from_config", lambda fallback: "defect_fix_2_2")
    monkeypatch.setenv("FIX_STAGE_REPLY_CAP", "on")
    monkeypatch.setenv("FIX_STAGES_STUB_OLD_READS", "on")


def _file(n: int) -> list[str]:
    return [f"value_{n}_{k} = {k}  # a line of module {n}, long enough to weigh something" for k in range(1, 41)]


def _workspace(tmp_path, files=4):
    for n in range(files):
        (tmp_path / "svc").mkdir(exist_ok=True)
        (tmp_path / "svc" / f"m{n}.py").write_text("\n".join(_file(n)) + "\n", encoding="utf-8")
    return tmp_path


def _read(n: int, call: str) -> list:
    return [AIMessage(content=f"Reading module {n}.", id=f"ai-{call}", tool_calls=[{
                "id": call, "name": "read_file", "args": {"file_path": f"svc/m{n}.py"}}]),
            ToolMessage(content=format_content_with_line_numbers(_file(n)), tool_call_id=call, id=f"tool-{call}")]


def _ran(call: str) -> list:
    return [AIMessage(content="The migration never runs; checking the start-up.", id=f"ai-{call}", tool_calls=[{
                "id": call, "name": "run_terminal_command", "args": {"command": ["python", "-c", "import svc"]}}]),
            ToolMessage(content='{"returncode": 1, "stderr": "OperationalError: no such table: users"}',
                        tool_call_id=call, id=f"tool-{call}")]


def _built(tmp_path, *, trigger: int, fix_trigger: int | None):
    return RequestKeepingSummarization(
        GenericFakeChatModel(messages=iter([AIMessage(content=SUMMARY)] * 4)),
        backend=FilesystemBackend(root_dir=str(tmp_path / "ctx")),
        trigger=("tokens", trigger), keep=("messages", 4), trim_tokens_to_summarize=1_000,
        repo_root=str(tmp_path), fix_stage_trigger_tokens=fix_trigger,
    )


def _sent(middleware, messages) -> list:
    seen: list = []

    def handler(request):
        seen.append(request.messages)
        return ModelResponse(result=[AIMessage(content="done")])

    request = ModelRequest(model=GenericFakeChatModel(messages=iter([])), messages=messages,
                           state={"messages": messages}, tools=[])
    middleware.wrap_model_call(request, handler)
    return seen[-1]


def test_a_read_shown_again_later_unchanged_becomes_one_line(tmp_path):
    root = _workspace(tmp_path)
    messages = [HumanMessage(content="Fix defect 3.", id="opening"), *_read(0, "r1"), *_ran("c1"), *_read(0, "r2"),
                AIMessage(content="Now the change.", id="ai-last")]

    sent = _sent(_built(root, trigger=10**6, fix_trigger=None), messages)

    first, again = sent[2].content, sent[6].content
    assert first.startswith("[read `svc/m0.py` lines 1-40, unchanged")
    assert "value_0_1 = 1" in again, "the later read keeps the text"
    assert sent[4].content == messages[4].content, "a command's result stays"
    assert [m.content for m in sent if m.type == "ai"] == [m.content for m in messages if m.type == "ai"]


def test_at_its_trigger_a_fix_stage_s_reads_before_the_kept_tail_become_notes_and_no_summary_is_made(tmp_path):
    root = _workspace(tmp_path, files=16)
    (root / "svc" / "m1.py").write_text("changed = True\n", encoding="utf-8")
    messages: list = [HumanMessage(content="Fix defect 3.", id="opening")]
    for n in range(16):
        messages += _read(n, f"r{n}")
    messages += _ran("c1")

    sent = _sent(_built(root, trigger=1_000, fix_trigger=8_000), messages)

    assert not any(SUMMARY in str(m.content) for m in sent), "not summarised by a model"
    notes = [m.content for m in sent if m.type == "tool" and m.content.startswith("[read ")]
    assert len(notes) >= 12
    assert any(n.startswith("[read `svc/m0.py` lines 1-40, unchanged since") for n in notes)
    assert any(n.startswith("[read `svc/m1.py` lines 1-40; the file has changed since") for n in notes)
    assert "value_15_1 = 1" in sent[-3].content, "the kept tail is whole"
    assert "no such table: users" in sent[-1].content
    assert not BANNED.search(" ".join(notes))


def test_with_the_switch_off_a_fix_stage_s_reads_stay_whole(tmp_path, monkeypatch):
    monkeypatch.setenv("FIX_STAGES_STUB_OLD_READS", "off")
    root = _workspace(tmp_path)
    messages = [HumanMessage(content="Fix defect 3.", id="opening"), *_read(0, "r1"), *_read(0, "r2"),
                AIMessage(content="Now the change.", id="ai-last")]

    sent = _sent(_built(root, trigger=10**6, fix_trigger=None), messages)

    assert "value_0_1 = 1" in sent[2].content


def test_another_stage_s_reads_stay_whole(tmp_path, monkeypatch):
    monkeypatch.setattr(transcript, "_stage_from_config", lambda fallback: "code_review_1")
    root = _workspace(tmp_path)
    messages = [HumanMessage(content="Review.", id="opening"), *_read(0, "r1"), *_read(0, "r2"),
                AIMessage(content="Next.", id="ai-last")]

    sent = _sent(_built(root, trigger=10**6, fix_trigger=None), messages)

    assert "value_0_1 = 1" in sent[2].content


def test_a_fix_stage_s_trigger_follows_its_own_reply_cap():
    """On a 91,776-token window every stage holds back 32,000 for a reply: its ceiling is 53,775 and its conversation
    is rewritten at 43,020. A fix stage's replies are capped at 12,000."""
    assert old_reads_stubbed.fix_stage_trigger(53_775, 32_000, 0.8, ceiling_is_set=False) == 59_020
    assert old_reads_stubbed.fix_stage_trigger(53_775, 32_000, 0.8, ceiling_is_set=True) is None


def test_the_fix_stage_s_trigger_holds_only_while_its_replies_are_capped(monkeypatch):
    assert old_reads_stubbed.trigger_here(43_020, 59_020) == 59_020
    monkeypatch.setenv("FIX_STAGE_REPLY_CAP", "off")
    assert old_reads_stubbed.trigger_here(43_020, 59_020) == 43_020


def test_the_switch_is_registered():
    from app import switches
    from app.observability import provenance, switch_firing

    assert "FIX_STAGES_STUB_OLD_READS" in switches.EXPERIMENTS
    assert "FIX_STAGES_STUB_OLD_READS" in provenance.SWITCHES
    assert "FIX_STAGES_STUB_OLD_READS" in switch_firing.SIGNALS
