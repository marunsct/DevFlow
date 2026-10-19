"""A stage whose conversation is summarised keeps the request it was given.

Measured live: a fixer's conversation was compacted mid-stage. The summariser
trims what it summarises to its last few thousand tokens and starts that on a
human message; a stage's only human message is its opening request, far larger
than that, so nothing was left and the summary read "Previous conversation was
too long to summarize." That summary replaced the request too - which defect,
its failing tests, the warning that the served page was the scaffold's stub -
and the fixer went on to edit the copy nothing serves. Seven of eight
compactions on that run were empty, and every fix stage among them failed.
"""
from __future__ import annotations

import re

import pytest
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deepagents.backends import FilesystemBackend
from deepagents.middleware.summarization import SummarizationMiddleware

from app.agents.compaction import RequestKeepingSummarization

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

BRIEF = (
    "Fix defect 17: [AC-9] the acceptance suite says this does not work yet.\n"
    "--- Before this defect: the served app is still the scaffold's stub ---\n"
    + "The served entry is `shop/src/App.tsx`; the copy in `shop/frontend/src/` is never built.\n" * 400
)


#: A stage opens with more than one message of its own: measured live, the files
#: as they stood when it started, then the defect it is to fix.
FILES_AT_START = "The project's files as they stood when this stage started:\n" + "shop/src/App.tsx: export const App = () => null;\n" * 200


def _conversation() -> list:
    messages: list = [HumanMessage(content=FILES_AT_START, id="files"), HumanMessage(content=BRIEF, id="opening")]
    for n in range(12):
        messages.append(AIMessage(content=f"Writing part {n}.", id=f"ai{n}", tool_calls=[{
            "id": f"call{n}", "name": "write_artifact",
            "args": {"relative_path": f"shop/src/part{n}.tsx", "content": "export const x = 1;\n" * 60},
        }]))
        messages.append(ToolMessage(content="written " + "ok " * 300, tool_call_id=f"call{n}", id=f"tool{n}"))
    return messages


def _summariser():
    return GenericFakeChatModel(messages=iter([AIMessage(content="Parts 0-9 of the page were written.")] * 4))


def _built(cls, tmp_path):
    return cls(
        _summariser(),
        backend=FilesystemBackend(root_dir=str(tmp_path)),
        trigger=("messages", 10),
        keep=("messages", 4),
        trim_tokens_to_summarize=1_000,
    )


def _sent(middleware, messages, state=None):
    seen: list = []

    def handler(request):
        seen.append(request.messages)
        return ModelResponse(result=[AIMessage(content="done")])

    request = ModelRequest(model=_summariser(), messages=messages, state=state or {"messages": messages}, tools=[])
    result = middleware.wrap_model_call(request, handler)
    return seen[-1], result


def test_the_plain_summariser_loses_the_request(tmp_path):
    """The fault as it was: an empty summary in place of the request."""
    sent, _ = _sent(_built(SummarizationMiddleware, tmp_path), _conversation())
    assert "too long to summarize" in sent[0].content
    assert "Fix defect 17" not in sent[0].content


@pytest.fixture
def compacted(tmp_path):
    return _sent(_built(RequestKeepingSummarization, tmp_path), _conversation())


def test_the_request_is_carried_whole(compacted):
    sent, _ = compacted
    assert BRIEF in sent[0].content
    assert sum("Fix defect 17" in str(m.content) for m in sent) == 1


def test_every_message_of_the_opening_turn_is_carried(compacted):
    """The defect brief was the second of the stage's opening messages, and the first kept was the other."""
    sent, _ = compacted
    assert sent[0].content.index(FILES_AT_START) < sent[0].content.index(BRIEF)


def test_the_summary_says_what_was_done(compacted):
    sent, _ = compacted
    assert "too long to summarize" not in sent[0].content
    assert "Parts 0-9 of the page were written." in sent[0].content


def test_the_files_this_stage_wrote_are_named(compacted):
    sent, _ = compacted
    assert "`shop/src/part0.tsx`" in sent[0].content


def test_a_second_compaction_still_carries_it(tmp_path):
    middleware = _built(RequestKeepingSummarization, tmp_path)
    messages = _conversation()
    _, result = _sent(middleware, messages)
    event = result.command.update["_summarization_event"]
    later = messages + _conversation()[1:]
    sent, _ = _sent(middleware, later, state={"messages": later, "_summarization_event": event})
    assert sent[0].additional_kwargs.get("lc_source") == "summarization"
    assert BRIEF in sent[0].content
    assert sent[0].content.count("Fix defect 17") == 1


def test_the_words_it_adds_hold_to_the_house_rules(compacted):
    sent, _ = compacted
    added = sent[0].content.replace(BRIEF, "").replace(FILES_AT_START, "")
    assert not BANNED.search(added)


def test_a_stage_agent_has_this_summariser_and_no_other(tmp_path, monkeypatch):
    """deepagents swaps its own summariser for one of the same name and adds any other."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("CTX_COMPACTION_ENABLED", raising=False)
    from deepagents.graph import _apply_custom_middleware
    from deepagents.middleware.summarization import create_summarization_middleware

    from app.agents.role_agent import _compaction_middleware

    ours = _compaction_middleware("backend")
    assert len(ours) == 1 and isinstance(ours[0], RequestKeepingSummarization)
    default = create_summarization_middleware(_summariser(), FilesystemBackend(root_dir=str(tmp_path)))
    stack = _apply_custom_middleware([default], ours, core_names={default.name})
    summarisers = [m for m in stack if isinstance(m, SummarizationMiddleware)]
    assert summarisers == ours


def test_the_opening_turn_is_carried_within_a_budget_keeping_its_request_whole(tmp_path):
    """Measured live: carrying the whole opening turn - a 27,000-character snapshot of
    the files at the stage's start, then the request - left a compacted conversation
    so near the trigger that one fix stage was compacted 10 times in 28 calls."""
    big_files = "The project's files as they stood when this stage started:\n" + ("x = 1\n" * 12_000)
    messages = [HumanMessage(content=big_files, id="files"), HumanMessage(content=BRIEF, id="opening"),
                *_conversation()[2:]]
    sent, _ = _sent(_built(RequestKeepingSummarization, tmp_path), messages)

    assert BRIEF in sent[0].content
    assert "x = 1\nx = 1" not in sent[0].content


def test_a_conversation_just_compacted_is_not_compacted_again_at_once(tmp_path):
    """Its kept tail already sits near the trigger: two calls later it was compacted again."""
    middleware = RequestKeepingSummarization(
        _summariser(), backend=FilesystemBackend(root_dir=str(tmp_path)),
        trigger=("messages", 5), keep=("messages", 4), trim_tokens_to_summarize=1_000,
    )
    messages = _conversation()
    _, result = _sent(middleware, messages)
    event = result.command.update["_summarization_event"]

    two_more = messages + [AIMessage(content="One more.", id="ai-x"), HumanMessage(content="next", id="h-x")]
    sent, again = _sent(middleware, two_more, state={"messages": two_more, "_summarization_event": event})

    assert not hasattr(again, "command")  # no new compaction: the summary stands
    assert sent[0].content == event["summary_message"].content


def test_a_conversation_that_has_grown_again_is_compacted_again(tmp_path):
    middleware = RequestKeepingSummarization(
        _summariser(), backend=FilesystemBackend(root_dir=str(tmp_path)),
        trigger=("messages", 5), keep=("messages", 4), trim_tokens_to_summarize=1_000,
    )
    messages = _conversation()
    _, result = _sent(middleware, messages)
    event = result.command.update["_summarization_event"]

    grown = messages + _conversation()[2:]
    _, again = _sent(middleware, grown, state={"messages": grown, "_summarization_event": event})

    assert hasattr(again, "command")
