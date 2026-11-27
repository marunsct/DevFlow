"""A stage is summarised past its measured opening, not at a trigger its opening already fills (LF.1606).

Measured live: a backend builder on a server giving each request 93,184 tokens, 32,000 of them held for the reply,
opened at 34,468 reported tokens (system prompt, tool schemas, specification, project memory and request). Its
summary trigger was 44,147: 0.8 of an input ceiling that took 6,000 tokens off for the system prompt and tool
schemas, compared with a count that holds the whole opening. After its first summary every request restarted at
36,000-42,000 tokens and was summarised again 8 messages later at 46,000-52,000, about every 75 seconds; the stage read
the same five files 5-6 times each in 50 calls and made one edit. The room the slot gives a request beside the reply
is 62,123 tokens, and the request-fit guard (LF.1500) compacts at once before a request would pass it.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.models import request_fit, server_profile

SLOT = 93_184
RESERVE = "32000"
ROOM = 62_123  # the slot less the most a reply's reserve may take, a third of it (31,061)

#: The stage's first calls, from the record: (reported input, reported output, the characters of each result).
FIRST_CALLS = [(34_468, 119, [1_405, 5_653, 652]), (38_149, 117, [1_327, 10_860, 12_537]),
               (46_137, 139, [17_252, 13_007, 1_564]), (55_153, 253, [3_413]), (56_635, 80, [11_485])]
#: After its first summary: the same files read again, one a call.
AFTER_THE_SUMMARY = [(40_402, 220, 9_768), (43_322, 77, 8_938), (45_903, 63, 12_537), (50_149, 203, 1_564)]
#: And past that, more of them, until the request nears the room.
FURTHER = [(52_192, 34, 10_860), (55_900, 60, 13_007), (59_000, 60, 17_252)]


@pytest.fixture
def stage(monkeypatch, tmp_path):
    """The stage's summariser as `role_agent` builds it, on the slot and reply reserve of the record."""
    request_fit.forget()
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "100000")
    monkeypatch.setenv("MODEL_MAX_OUTPUT_TOKENS", RESERVE)
    for name in ("CTX_SOFT_TRIGGER_RATIO", "CTX_MAX_TOKENS", "SUMMARISE_LATER_WITH_HEADROOM",
                 "REPLY_ROOM_SIZED_PER_ROLE", "FIX_STAGES_STUB_OLD_READS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(server_profile, "current", lambda: SimpleNamespace(slot_context=SLOT))
    monkeypatch.setattr(server_profile, "read_for", lambda: None)
    note = AIMessage(content="## Found\nNone\n## Decided\nNone\n## Changed\nNone\n## Left\nFix the page's start.")
    monkeypatch.setattr("app.agents.role_agent.build_default_chat_model",
                        lambda *a, **k: GenericFakeChatModel(messages=iter([note] * 40)))
    from app.agents.role_agent import _compaction_middleware

    (middleware,) = _compaction_middleware("specialist_backend")
    yield middleware
    request_fit.forget()


def _reply(n: int, reported: int, output: int, results: int) -> AIMessage:
    return AIMessage(
        content="Reading the files the acceptance suite checks.", id=f"ai{n}",
        tool_calls=[{"id": f"call{n}-{k}", "name": "read_file", "args": {"file_path": f"app/file{n}-{k}.js"}}
                    for k in range(results)],
        usage_metadata={"input_tokens": reported, "output_tokens": output, "total_tokens": reported + output},
        response_metadata={"model_provider": "genericfakechatmodel"},
    )


def _result(n: int, k: int, size: int) -> ToolMessage:
    return ToolMessage(content="\n".join(f"{i:>4}  const value{i} = {i};" for i in range(size // 24))[:size],
                       tool_call_id=f"call{n}-{k}", id=f"tool{n}-{k}")


def _call(middleware, messages, event=None):
    """One model call through the summariser: what the model was sent, and the summary event when one was made."""
    seen: list = []

    def handler(request):
        seen.append(request.messages)
        return ModelResponse(result=[AIMessage(content="done")])

    state = {"messages": messages, **({"_summarization_event": event} if event else {})}
    request = ModelRequest(model=middleware._lc_helper.model, messages=messages, state=state, tools=[])
    result = middleware.wrap_model_call(request, handler)
    command = getattr(result, "command", None)
    return seen[-1], (command.update["_summarization_event"] if command is not None else None)


def _summarised_once(middleware):
    messages: list = [HumanMessage(content="Make the page pass its acceptance suite.\n" * 2_200, id="ask")]
    for n, (reported, output, sizes) in enumerate(FIRST_CALLS):
        messages.append(_reply(n, reported, output, len(sizes)))
        messages.extend(_result(n, k, size) for k, size in enumerate(sizes))
    _, event = _call(middleware, messages)
    assert event is not None, "the first summary, past the room as on the record"
    return messages, event


def _read_on(messages, calls, start):
    for n, (reported, output, size) in enumerate(calls, start=start):
        messages = [*messages, _reply(n, reported, output, 1), _result(n, 0, size)]
    return messages


def test_the_files_a_stage_just_read_stay_whole_while_its_request_has_room(stage):
    messages, event = _summarised_once(stage)
    messages = _read_on(messages, AFTER_THE_SUMMARY, start=100)

    sent, summarised = _call(stage, messages, event)

    assert summarised is None, "summarised at about 51,000 tokens of a 62,123-token room"
    assert [m.id for m in sent[-8:] if m.type == "tool"] == ["tool100-0", "tool101-0", "tool102-0", "tool103-0"]


def test_the_stage_is_still_summarised_before_its_request_passes_the_room(stage):
    messages, event = _summarised_once(stage)
    messages = _read_on(messages, AFTER_THE_SUMMARY, start=100)
    whole_at = []
    summarised_at = None
    for n, call in enumerate(FURTHER, start=200):
        messages = _read_on(messages, [call], start=n)
        _, summarised = _call(stage, messages, event)
        if summarised is not None:
            summarised_at = call[0]
            break
        whole_at.append(call[0])

    assert summarised_at is not None, f"never summarised; kept whole at {whole_at}"
    assert all(reported + 32_000 < SLOT for reported in whole_at), whole_at


@pytest.mark.parametrize(("opening", "room", "trigger"), [
    (34_468, ROOM, 56_592),     # the record's builder: 22,124 tokens of conversation, not about 9,700
    (12_000, 150_000, 122_400),  # a small opening on a large window
])
def test_the_trigger_sits_past_the_opening_within_the_room(opening, room, trigger):
    from app.agents.summary_trigger import trigger_past_the_opening

    assert trigger_past_the_opening(opening, room, 0.8) == trigger


def test_an_opening_that_fills_the_room_keeps_the_configured_trigger():
    """A large codebase's opening near the room: summarising past it gains nothing, so nothing is changed here."""
    from app.agents.summary_trigger import trigger_past_the_opening

    assert trigger_past_the_opening(60_000, ROOM, 0.8) is None
