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


def test_a_read_after_a_compaction_is_not_told_it_already_has_the_lines(tmp_path, monkeypatch):
    """Measured on one gate run: 40 of 57 reads counted as redundant came after a
    compaction, each told "this returned nothing you did not already have" about
    text the summary had taken out of the conversation."""
    from app.agents import stage_memory
    from app.agents.workspace_backend import WorkspaceBackend

    monkeypatch.setattr(stage_memory, "current_stage_key", lambda: "thread-1")
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "app.py").write_text("value = 1\n" * 40)

    def read():
        return str(WorkspaceBackend(root_dir=str(root), virtual_mode=True).read("/app.py"))

    read()
    assert "already read" in read()

    _sent(_built(RequestKeepingSummarization, tmp_path), _conversation())

    after = read()
    assert "already read" not in after and "same bytes" not in after and "value = 1" in after


def _heavy_tail() -> list:
    """A stage whose last reads are large: measured live, three test files read again after each compaction."""
    messages = _conversation()
    for n in range(3):
        messages.append(AIMessage(content=f"Reading file {n}.", id=f"read-ai{n}", tool_calls=[{
            "id": f"read{n}", "name": "read_file", "args": {"file_path": f"shop/tests/test_{n}.py"}}]))
        messages.append(ToolMessage(content=("line of a test file\n" * 900), tool_call_id=f"read{n}", id=f"read-out{n}"))
    return messages


def test_a_compaction_leaves_a_tail_that_fits_its_ceiling(tmp_path):
    """Measured live: the fifteen messages kept held three file reads, every compaction left the
    request at or above its trigger, and a fix stage compacted eight times in 26 minutes."""
    middleware = RequestKeepingSummarization(
        _summariser(), backend=FilesystemBackend(root_dir=str(tmp_path)), trigger=("messages", 10),
        keep=("messages", 8), trim_tokens_to_summarize=1_000, most_kept_tokens=6_000,
    )
    messages = _heavy_tail()

    cutoff = middleware._determine_cutoff_index(messages)
    kept = messages[cutoff:]

    assert middleware.token_counter(kept) <= 6_000 or len(kept) <= 2
    assert getattr(kept[0], "type", None) != "tool", "a tool result is never parted from its call"
    assert cutoff > len(messages) - 8, "more is summarised than the count alone would"


def test_without_a_ceiling_the_count_alone_decides(tmp_path):
    middleware = _built(RequestKeepingSummarization, tmp_path)
    messages = _heavy_tail()

    assert middleware._determine_cutoff_index(messages) == middleware._lc_helper._determine_cutoff_index(messages)


def test_every_stage_s_compaction_has_the_ceiling():
    from app.agents.compaction import KEPT_TAIL_SHARE
    from app.agents.context_policy import ContextPolicy
    from app.agents.role_agent import _compaction_middleware

    (middleware,) = _compaction_middleware("specialist_testing")

    assert middleware._most_kept_tokens == int(ContextPolicy.from_environment().trigger_tokens * KEPT_TAIL_SHARE)


def test_a_stage_s_call_budget_counts_the_calls_a_summary_replaced(tmp_path):
    """Measured on one gate run: a fix stage made 41 calls against a budget of 40 and went on -
    after a compaction the count started again from the summary."""
    from app.agents.settled_answer import _model_calls_used

    middleware = _built(RequestKeepingSummarization, tmp_path)
    messages = _conversation()
    sent, _ = _sent(middleware, messages)
    kept_ai = sum(1 for m in sent if getattr(m, "type", None) == "ai")

    assert _model_calls_used(sent) == 12, f"12 calls made, {kept_ai} still in the conversation"


def test_replies_lost_to_reasoning_are_counted_across_a_compaction(tmp_path):
    """Measured on one gate run: a stage lost a reply, was compacted, lost another, and was treated as
    losing its first - thinking came back on for the reply after."""
    from app.agents.settled_answer import _replies_that_were_all_reasoning

    middleware = _built(RequestKeepingSummarization, tmp_path)
    messages = _conversation()
    messages.insert(3, AIMessage(content="", id="lost", response_metadata={"finish_reason": "length"}))
    sent, _ = _sent(middleware, messages)

    assert _replies_that_were_all_reasoning(sent) == 1
