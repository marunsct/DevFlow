"""A file a stage reads reaches the model whole the first time (LF.1465).

Measured on one medium run: a testing stage, ten to fifteen messages into its conversation after a summary, read
`routes/auth.py` (10,466 characters) and the very next request carried it as its first 300 characters and "the rest was
left out because it is older than the latest steps". deepagents answers "every message is recent" for a conversation
of at most its kept count, and the harness's override took that as a cutoff and folded the first ten messages - 294
reads in four runs. The conversation here is the real one of that call, captured from the transcript.
"""
from __future__ import annotations

import json
from pathlib import Path

from deepagents.backends import FilesystemBackend
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents import observation_folding
from app.agents.compaction import RequestKeepingSummarization

CAPTURED = Path(__file__).parent / "captured" / "test_round_reads_after_a_summary.json"


def _middleware(tmp_path):
    # As `role_agent` configures it: the kept tail of 15 messages, the argument trigger crossed.
    return RequestKeepingSummarization(
        GenericFakeChatModel(messages=iter([AIMessage(content="summary")])),
        backend=FilesystemBackend(root_dir=str(tmp_path)),
        trigger=("tokens", 10_000_000), keep=("messages", 15),
        truncate_args_settings={"trigger": ("tokens", 1), "keep": ("messages", 15), "max_length": 2_000},
    )


def _captured() -> list:
    out: list = []
    for m in json.loads(CAPTURED.read_text(encoding="utf-8")):
        if m["type"] == "human":
            out.append(HumanMessage(content=m["content"]))
        elif m["type"] == "ai":
            out.append(AIMessage(content=m["content"], tool_calls=m["tool_calls"]))
        else:
            out.append(ToolMessage(content=m["content"], tool_call_id=m["tool_call_id"], name=m["name"]))
    return out


def test_the_reads_of_a_conversation_of_eleven_messages_reach_the_model_whole(tmp_path, monkeypatch):
    monkeypatch.setenv("OBSERVATION_FOLDING", "on")
    messages = _captured()
    assert len(messages) == 11

    sent, _ = _middleware(tmp_path)._truncate_args(messages, 100_000)

    reads = {m.tool_call_id: m.content for m in sent if isinstance(m, ToolMessage)}
    assert all(observation_folding.FOLDED not in text for text in reads.values())
    auth = next(m for m in messages if isinstance(m, ToolMessage) and "Authentication route handlers" in m.content)
    assert len(reads[auth.tool_call_id]) == 10_466


def test_a_result_no_reply_follows_is_never_folded(tmp_path, monkeypatch):
    """Past the kept count too: the last reply's results are what the model is about to read."""
    monkeypatch.setenv("OBSERVATION_FOLDING", "on")
    captured = _captured()
    first_reply, last_reply = captured[1:5], captured[5:]
    # The same real reads asked for again and again, then the last reply's reads, unseen.
    messages = [captured[0], *first_reply * 5, *last_reply]
    # One reply asking for more files than the kept tail holds.
    many = AIMessage(content="", tool_calls=[{"name": "read_file", "args": {"file_path": f"f{n}.py"}, "id": f"m{n}"}
                                             for n in range(20)])
    messages = [*messages, many, *[ToolMessage(content=captured[6].content, tool_call_id=f"m{n}", name="read_file")
                                   for n in range(20)]]

    sent, _ = _middleware(tmp_path)._truncate_args(messages, 100_000)

    assert all(observation_folding.FOLDED not in m.content for m in sent[-20:])
    # Results the model has seen, behind the kept tail, are folded as before.
    assert observation_folding.FOLDED in sent[2].content
