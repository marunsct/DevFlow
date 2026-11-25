"""Every request a stage sends fits the context the model server gives it (LF.1499-LF.1502).

Measured on one fast run: a testing stage on a server that gives each request 93,184 tokens was summarised once at
61,115 reported input tokens, kept three messages behind its summary, and then went from 54,263 to 81,370 reported
tokens over nine calls with no second summary - the rule against summarising again too soon counted from the 15
messages the tail is configured to keep, not the three it kept, so 23 messages had to follow. Its next request was
96,754 tokens; the server refused it six times and the run failed, since no client recognised that refusal as a
context overflow to compact for.
"""

from __future__ import annotations

import re

import httpx
import pytest
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.exceptions import ContextOverflowError
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai.chat_models.base import OpenAIInvalidRequestError

from deepagents.backends import FilesystemBackend

from app.agents import stage_memory, tool_result_bound
from app.agents.compaction import RequestKeepingSummarization
from app.models import CompatibleChatOpenAI, request_fit, server_profile

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

#: The server's refusal as the run's transcript recorded it.
REFUSAL = ("Error code: 400 - {'error': {'code': 400, 'message': 'request (96754 tokens) exceeds the available "
           "context size (93184 tokens), try increasing it', 'type': 'exceed_context_size_error', "
           "'n_prompt_tokens': 96754, 'n_ctx': 93184}}")
BODY = {"error": {"code": 400, "message": "request (96754 tokens) exceeds the available context size (93184 tokens), "
                  "try increasing it", "type": "exceed_context_size_error", "n_prompt_tokens": 96754, "n_ctx": 93184}}

#: The stage's calls before its first summary, from the record: each reply's reported input and output tokens and
#: the characters of the results it was answered with.
BEFORE_THE_SUMMARY = [(32596, 126, [6230, 11745, 969]), (38715, 80, [6098]), (40968, 272, [28591]),
                      (56483, 287, [2709]), (57565, 3358, [786]), (61115, 126, [11888, 454])]
#: And after it: (reported input, reported output, the characters of the result that followed), call by call.
AFTER_THE_SUMMARY = [(38936, 74, 28442), (54263, 2668, 6783), (59435, 132, 458), (59696, 2905, 191),
                     (62676, 73, 28178), (77524, 770, 1540), (78848, 651, 1544), (80029, 634, 2051),
                     (81370, 77, 28276)]
#: The trigger, kept tail and room of that stage: a 91,776-token window holding back 32,000 for the reply.
TRIGGER = 43_020
WINDOW = 91_776
RESERVE = 32_000
ROOM = 61_184  # 91,776 less a third of it (30,592), the most a reply's reserve may take


@pytest.fixture(autouse=True)
def _fresh():
    request_fit.forget()
    yield
    request_fit.forget()


def _reply(n: int, input_tokens: int, output_tokens: int = 100, results: int = 1) -> AIMessage:
    """A reply of the record: a long one wrote an edit (about three characters a token), a short one ran the tests."""
    if output_tokens > 500:
        call = {"name": "edit_artifact", "args": {"file_path": "tests/App.test.tsx", "new": "e" * (output_tokens * 3)}}
    else:
        call = {"name": "run_terminal_command", "args": {"command": "npx vitest run"}}
    return AIMessage(
        content="Now let me run the tests.", id=f"ai{n}",
        tool_calls=[{"id": f"call{n}-{k}", **call} for k in range(results)],
        usage_metadata={"input_tokens": input_tokens, "output_tokens": output_tokens,
                        "total_tokens": input_tokens + output_tokens},
        response_metadata={"model_provider": "genericfakechatmodel"},
    )


def _result(n: int, k: int, size: int) -> ToolMessage:
    return ToolMessage(content=("x" * (size - 20)) + " 3 failed | 40 passed", tool_call_id=f"call{n}-{k}",
                       id=f"tool{n}-{k}")


def _opening() -> list:
    messages: list = [HumanMessage(content="Bring the unit tests in line with the components.\n" * 300, id="ask")]
    for n, (reported, output, sizes) in enumerate(BEFORE_THE_SUMMARY):
        messages.append(_reply(n, reported, output, results=len(sizes)))
        messages.extend(_result(n, k, size) for k, size in enumerate(sizes))
    return messages


def _middleware(tmp_path) -> RequestKeepingSummarization:
    return RequestKeepingSummarization(
        GenericFakeChatModel(messages=iter([AIMessage(content="## Found\nNone")] * 20)),
        backend=FilesystemBackend(root_dir=str(tmp_path)),
        trigger=("tokens", TRIGGER), keep=("messages", 15), most_kept_tokens=int(TRIGGER * 0.15),
        trim_tokens_to_summarize=4_000, reply_reserve_tokens=RESERVE, window_tokens=WINDOW,
    )


def _call(middleware, messages, event=None):
    seen: list = []

    def handler(request):
        seen.append(request.messages)
        return ModelResponse(result=[AIMessage(content="done")])

    state = {"messages": messages, **({"_summarization_event": event} if event else {})}
    request = ModelRequest(model=middleware._lc_helper.model, messages=messages, state=state, tools=[])
    result = middleware.wrap_model_call(request, handler)
    return getattr(result, "command", None)


def _summarised_once(tmp_path):
    middleware = _middleware(tmp_path)
    messages = _opening()
    command = _call(middleware, messages)
    assert command is not None, "the stage's first summary, at 61,115 reported tokens"
    return middleware, messages, command.update["_summarization_event"]


def test_the_server_s_refusal_names_what_was_sent_and_its_limit():
    error = OpenAIInvalidRequestError(REFUSAL, response=httpx.Response(400, request=httpx.Request("POST", "http://x")),
                                      body=BODY)

    assert request_fit.refused_for_size(error) == (96754, 93184)
    assert request_fit.refused_for_size(
        '400 - messages.2: Value error, "name" is only valid on role="tool" messages.') is None


def test_a_stage_summarised_once_is_summarised_again_before_it_outgrows_the_slot(tmp_path):
    middleware, messages, event = _summarised_once(tmp_path)

    again_at = None
    reported_before = []
    for n, (reported, output, size) in enumerate(AFTER_THE_SUMMARY, start=100):
        messages = [*messages, _reply(n, reported, output), _result(n, 0, size)]
        if _call(middleware, messages, event) is not None:
            again_at = reported
            break
        reported_before.append(reported)

    assert again_at is not None, "summarised again before the request the server refused"
    assert max(reported_before) < ROOM, f"no reply past the room went unsummarised: {reported_before}"


def test_a_request_past_the_room_is_summarised_whatever_its_summary_s_age(tmp_path):
    """The record's last request: a summary from before this fix (no kept tail on it), 18 messages since, and the
    last reply at 81,370 tokens with a 28,276-character result after it - sent whole, it was refused."""
    middleware, messages, event = _summarised_once(tmp_path)
    old = event["summary_message"]
    event = {**event, "summary_message": old.model_copy(update={"additional_kwargs": {
        k: v for k, v in old.additional_kwargs.items() if k != "harness_kept_tail"}})}
    for n, (reported, output, size) in enumerate(AFTER_THE_SUMMARY, start=100):
        messages = [*messages, _reply(n, reported, output), _result(n, 0, size)]

    assert _call(middleware, messages, event) is not None


class _Server:
    """The model server: counts a request at the rate measured on the refused one, refuses it past its limit."""

    RATE = 2.87

    def __init__(self, limit: int = 93_184):
        self.limit = limit
        self.sent: list[int] = []
        self.refused = 0

    def tokens(self, messages) -> int:
        return int(request_fit.request_chars(messages) / self.RATE)

    def __call__(self, model, messages, stop=None, run_manager=None, **kwargs):
        tokens = self.tokens(messages)
        self.sent.append(tokens)
        if tokens > self.limit:
            self.refused += 1
            body = {"error": {"code": 400, "message": f"request ({tokens} tokens) exceeds the available context "
                              f"size ({self.limit} tokens), try increasing it", "type": "exceed_context_size_error",
                              "n_prompt_tokens": tokens, "n_ctx": self.limit}}
            raise OpenAIInvalidRequestError(f"Error code: 400 - {body}", body=body,
                                            response=httpx.Response(400, request=httpx.Request("POST", "http://x")))
        reply = AIMessage(content="ok", usage_metadata={"input_tokens": tokens, "output_tokens": 5,
                                                        "total_tokens": tokens + 5})
        return ChatResult(generations=[ChatGeneration(message=reply)])


def _serve(monkeypatch, server: _Server) -> None:
    def paced(self, messages, stop=None, run_manager=None, **kwargs):
        return server(self, messages, stop=stop, run_manager=run_manager, **kwargs)

    monkeypatch.setattr(CompatibleChatOpenAI, "_generate_paced", paced)


def _client() -> CompatibleChatOpenAI:
    return CompatibleChatOpenAI(model="local", base_url="http://llama.example/v1", api_key="k", max_retries=0,
                                max_tokens=RESERVE)


def _the_record_s_last_request() -> list:
    """About 97,000 tokens: the opening, then the calls since the summary with their results."""
    messages: list = [HumanMessage(content="Project memory and request. " * 4_000, id="ask")]
    for n, (reported, output, size) in enumerate(AFTER_THE_SUMMARY, start=100):
        messages += [_reply(n, reported, output), _result(n, 0, size * 4 if size > 20_000 else size)]
    return messages


def test_a_request_past_the_slot_is_cut_before_it_is_sent(monkeypatch):
    server = _Server()
    _serve(monkeypatch, server)
    monkeypatch.setattr(server_profile, "current",
                        lambda: server_profile.from_props({"total_slots": 2,
                                                           "default_generation_settings": {"n_ctx": 93_184}}))
    model = _client()
    model.invoke([HumanMessage(content="Measure me. " * 2_000)])
    messages = _the_record_s_last_request()
    assert server.tokens(messages) > 93_184

    answer = model.invoke(messages)

    assert answer.content == "ok"
    assert server.refused == 0
    assert server.sent[-1] <= 93_184 - 31_061  # the slot less the reply's reserve (a third of the slot at most)


def test_a_client_of_another_server_is_not_held_to_the_build_server_s_slot(monkeypatch):
    """A hosted judgement model beside a local build model: the local server's slot is not the hosted one's."""
    server = _Server(limit=1_000_000)
    _serve(monkeypatch, server)
    monkeypatch.setattr(server_profile, "current",
                        lambda: server_profile.from_props({"default_generation_settings": {"n_ctx": 93_184}}))
    monkeypatch.setattr(server_profile, "read_for", lambda: ("http://llama.example/v1", "local"))
    hosted = CompatibleChatOpenAI(model="hosted", base_url="https://hosted.example/v1", api_key="k", max_retries=0)
    messages = _the_record_s_last_request()

    hosted.invoke(messages)

    assert server.sent == [server.tokens(messages)]


def test_a_request_refused_for_its_size_is_cut_harder_and_sent_again(monkeypatch):
    """A server with no profile (or one that gives less than it says): the refusal is answered, not repeated."""
    server = _Server(limit=70_000)
    _serve(monkeypatch, server)
    monkeypatch.setattr(server_profile, "current", lambda: None)

    answer = _client().invoke(_the_record_s_last_request())

    assert answer.content == "ok"
    assert server.refused == 1
    assert server.sent[1] < server.sent[0] and server.sent[1] <= 70_000


def test_a_refusal_with_nothing_left_to_cut_is_a_context_overflow(monkeypatch):
    """So the summariser's overflow fallback summarises the conversation, and the stage knows it for an overflow."""
    server = _Server(limit=1_000)
    _serve(monkeypatch, server)
    monkeypatch.setattr(server_profile, "current", lambda: None)

    with pytest.raises(ContextOverflowError):
        _client().invoke([HumanMessage(content="Project memory and request. " * 400)])
    assert server.refused == 1


def test_one_result_too_large_for_the_room_is_cut_at_the_tool(monkeypatch, tmp_path):
    monkeypatch.setenv("CTX_JOURNAL_ROOT", str(tmp_path))
    with stage_memory.remembering("testing-stage"):
        request_fit.calibrate(("http://llama.example/v1", "local"), int(81_370 * 2.87), 81_370)
        monkeypatch.setattr(server_profile, "current",
                            lambda: server_profile.from_props({"default_generation_settings": {"n_ctx": 93_184}}))
        request_fit.before_sending(("http://llama.example/v1", "local"), [HumanMessage(content="x")], None, RESERVE)
        whole = "line of output\n" * 20_000 + "Tests  3 failed | 40 passed"
        usual = "line of output\n" * 1_800 + "Tests  3 failed | 40 passed"

        cut = tool_result_bound.bounded("run_terminal_command", ToolMessage(content=whole, tool_call_id="c1"))
        kept = tool_result_bound.bounded("run_terminal_command", ToolMessage(content=usual, tool_call_id="c2"))

    assert len(cut.content) < len(whole) / 4
    assert cut.content.endswith("Tests  3 failed | 40 passed")
    reference = re.search(r"saved as (\S+);", cut.content).group(1)
    assert (tmp_path / reference).read_text() == whole
    assert kept.content == usual


def test_what_the_model_reads_of_a_cut_holds_to_the_house_rules(monkeypatch, tmp_path):
    monkeypatch.setenv("CTX_JOURNAL_ROOT", str(tmp_path))
    fitted, _ = request_fit.fitted([_reply(1, 10), _result(1, 0, 50_000), _reply(2, 10), _result(2, 0, 50_000)],
                                   20_000)
    with stage_memory.remembering("testing-stage"):
        request_fit.calibrate(None, 100_000, 40_000)
        monkeypatch.setattr(server_profile, "current",
                            lambda: server_profile.from_props({"default_generation_settings": {"n_ctx": 60_000}}))
        bounded = [tool_result_bound.bounded(tool, ToolMessage(content="y" * 400_000, tool_call_id="c")).content
                   for tool in ("read_file", "grep")]
    said = " ".join(m.content.replace("x", "").replace("y", "") for m in fitted) + " ".join(
        b.replace("y", "") for b in bounded)

    assert "left out" in said
    assert not BANNED.search(said)


def test_the_stage_reads_llama_cpp_s_refusal_as_a_context_overflow():
    """The stage's own overflow handling knew providers' wordings but not llama.cpp's, so another client's refusal
    reached it as an unhandled crash."""
    from app.graph.workflow import _is_context_overflow

    error = ValueError("Error code: 400 - {'error': {'code': 400, 'message': 'request (96754 tokens) exceeds the "
                       "available context size (93184 tokens), try increasing it', 'type': 'exceed_context_size_error'}}")
    assert _is_context_overflow(error)
