"""A reply cut off by the reply cap is salvaged from its own reasoning, where its model's server was measured to allow it.

Over nine runs 19 replies reasoned to the cap and wrote nothing - 10% of every
output token - and the recovery threw the reasoning away and then switched
thinking off for the stage. A cap on reasoning would have cut 74 replies that
finished past 16,000 tokens. So the reasoning is kept, closed, and the model
asked for the answer it was reasoning towards; whether its server continues a
begun reply is measured once per model and kept with it.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.models import registry, reply_salvage

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
REASONING = "The failing test asserts 201; the route returns 200. The fix is the status code in routes.py."


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("REPLY_SALVAGE", "on")
    reply_salvage.forget()
    yield
    reply_salvage.forget()


def _completion(content="", reasoning="", finish="stop", calls=None):
    return {"choices": [{"finish_reason": finish, "message": {
        "role": "assistant", "content": content, "reasoning_content": reasoning, "tool_calls": calls}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


class _Server:
    """Answers each request from `replies` in turn, keeping what was sent."""

    def __init__(self, replies):
        self.replies, self.sent = list(replies), []

    def create(self, **payload):
        self.sent.append(payload)
        return self.replies.pop(0)


def _model(server):
    def result_of(response):
        message = response["choices"][0]["message"]
        return ChatResult(generations=[ChatGeneration(
            message=AIMessage(content=message.get("content") or ""),
            generation_info={"finish_reason": response["choices"][0]["finish_reason"]})])

    return SimpleNamespace(
        model_name="local-model", openai_api_base="http://server/v1", client=server,
        root_client=SimpleNamespace(chat=SimpleNamespace(completions=server)),
        _get_request_payload=lambda messages, stop=None, **kw: {"model": "local-model", "messages": [
            {"role": "user", "content": "Fix the defect."}], "max_tokens": 32_768, **kw},
        _create_chat_result=result_of,
    )


def _cut(content=""):
    return ChatResult(generations=[ChatGeneration(
        message=AIMessage(content=content), generation_info={"finish_reason": "length"})])


def _supported(**overrides):
    reply_salvage.keep("local-model", reply_salvage.Support(shape="reasoning_field", tools=True, continuation=True,
                                                            model="local-model", **overrides))


def test_a_reply_that_reasoned_to_the_cap_is_answered_from_its_reasoning():
    _supported()
    server = _Server([_completion("Changed the status code to 201.")])
    reply_salvage.remember_reasoning(REASONING)

    result = reply_salvage.salvaged(_model(server), [HumanMessage(content="Fix the defect.")], _cut())

    assert result.generations[0].message.content == "Changed the status code to 201."
    assert result.generations[0].generation_info[reply_salvage.SALVAGED] == "reasoning"
    begun = server.sent[0]["messages"][-1]
    assert begun["role"] == "assistant" and REASONING in begun["reasoning_content"]
    assert begun["reasoning_content"].endswith(reply_salvage.ENOUGH)


def test_a_reply_that_finished_is_never_touched():
    _supported()
    server = _Server([])
    finished = ChatResult(generations=[ChatGeneration(message=AIMessage(content="done"),
                                                      generation_info={"finish_reason": "stop"})])

    assert reply_salvage.salvaged(_model(server), [], finished) is finished
    assert server.sent == []


def test_nothing_is_salvaged_where_the_server_was_measured_not_to_allow_it():
    reply_salvage.keep("local-model", reply_salvage.Support(shape="", model="local-model"))
    server = _Server([])
    reply_salvage.remember_reasoning(REASONING)
    cut = _cut()

    assert reply_salvage.salvaged(_model(server), [], cut) is cut
    assert server.sent == []


def test_nothing_is_salvaged_with_the_switch_off(monkeypatch):
    monkeypatch.setenv("REPLY_SALVAGE", "off")
    _supported()
    server = _Server([])
    reply_salvage.remember_reasoning(REASONING)
    cut = _cut()

    assert reply_salvage.salvaged(_model(server), [], cut) is cut


def test_a_salvage_that_reasons_again_and_answers_nothing_leaves_the_reply_to_the_usual_recovery():
    _supported()
    server = _Server([_completion("", reasoning="more thinking", finish="length"),
                      _completion("", reasoning="and more", finish="length")])
    reply_salvage.remember_reasoning(REASONING)
    cut = _cut()

    assert reply_salvage.salvaged(_model(server), [], cut) is cut


def test_text_cut_off_part_way_is_continued_from_where_it_stopped():
    _supported(echoes=True)
    server = _Server([_completion("def b():\n    return 2\n")])
    cut = _cut("def a():\n    return 1\n\n")

    result = reply_salvage.salvaged(_model(server), [], cut)

    assert result.generations[0].message.content == "def a():\n    return 1\n\ndef b():\n    return 2\n"
    assert server.sent[0]["messages"][-1]["content"] == "def a():\n    return 1\n\n"


def test_the_measurement_finds_the_shape_that_works_and_keeps_it_with_the_model():
    registry.record_edit_rates("local-model", {"whole": 1.0, "edit": 0.9})
    server = _Server([
        _completion("I think"),                     # reasoning_field: ignored
        _completion("391"),                         # think_tags: answered
        _completion("", calls=[{"function": {"name": "give_answer", "arguments": '{"value": 391}'}}]),
        _completion(" four, five, six"),            # continued, not repeated
    ])

    support = reply_salvage.measure(_model(server), "local-model")

    assert support.shape == "think_tags" and support.tools and support.continuation and not support.echoes
    kept = json.loads((registry.fitness_dir() / "local-model.json").read_text())
    assert kept[reply_salvage.RECORD_KEY]["shape"] == "think_tags"
    assert kept["edit"] == 0.9  # the model's other measurement is still there
    reply_salvage.forget()
    assert reply_salvage.recorded("local-model").shape == "think_tags"


def test_a_server_that_continues_nothing_is_kept_as_supporting_nothing():
    server = _Server([_completion("Let me think about 17 times 23 from the start..."), RuntimeError("400")])

    support = reply_salvage.measure(_model(server), "local-model")

    assert not support.salvages
    assert reply_salvage.describe(support) == "not supported by this server (measured)"


def test_what_the_model_is_told_uses_none_of_the_banned_words():
    assert not BANNED.search(reply_salvage.ENOUGH)


def test_text_stuck_repeating_one_unit_is_not_continued():
    """The first live continuation went on a drafted file ending `"never-issued-token-000..."` to the cap."""
    _supported()
    server = _Server([])
    cut = _cut('unknown_token = "never-issued-token-' + "0" * 2_000)

    assert reply_salvage.salvaged(_model(server), [], cut) is cut
    assert server.sent == []


def test_a_continuation_that_starts_repeating_stops_there():
    _supported()
    server = _Server([_completion("ab" * 400, finish="length"), _completion("never sent")])
    cut = _cut("def a():\n    return 1\n")

    result = reply_salvage.salvaged(_model(server), [], cut)

    assert len(server.sent) == 1
    assert result.generations[0].generation_info["finish_reason"] == "length"


def test_ordinary_text_is_not_taken_for_a_repetition():
    code = "".join(f"def handler_{n}(request):\n    return {{'value': {n}}}, 200\n\n" for n in range(40))
    assert not reply_salvage.repeating(code)
    assert reply_salvage.repeating("x = '" + "0" * 500)
    assert reply_salvage.repeating("ab" * 300)


def test_a_salvage_that_comes_back_empty_says_so(caplog):
    """Three cut-off replies of one run went unsalvaged with nothing to say whether salvage was tried."""
    import logging

    _supported()
    server = _Server([_completion("", reasoning="more", finish="length"), _completion("", reasoning="more", finish="length")])
    reply_salvage.remember_reasoning(REASONING)
    with caplog.at_level(logging.INFO, logger="app.models.reply_salvage"):
        reply_salvage.salvaged(_model(server), [], _cut())
    assert "could not be salvaged" in caplog.text


def test_a_shape_that_reasons_again_after_a_long_request_gives_way_to_the_other_and_it_is_kept():
    """Measured on one run: from the `reasoning_field` shape, a fix stage's long request reasoned again to the ceiling."""
    _supported()
    server = _Server([_completion("", reasoning="thinking again", finish="length"),
                      _completion("Changed the status code to 201.")])
    reply_salvage.remember_reasoning(REASONING)

    result = reply_salvage.salvaged(_model(server), [HumanMessage(content="Fix the defect.")], _cut())

    assert result.generations[0].message.content == "Changed the status code to 201."
    assert server.sent[1]["messages"][-1]["content"].startswith("<think>")
    assert all(p["max_tokens"] <= reply_salvage.SALVAGE_REPLY_TOKENS for p in server.sent)
    reply_salvage.forget()
    assert reply_salvage.recorded("local-model").long_shape == "think_tags"


def _cut_at(input_tokens):
    message = AIMessage(content="", usage_metadata={"input_tokens": input_tokens, "output_tokens": 40_000,
                                                    "total_tokens": input_tokens + 40_000})
    return ChatResult(generations=[ChatGeneration(message=message, generation_info={"finish_reason": "length"})])


def test_the_kept_reasoning_is_cut_to_what_fits_beside_the_request(monkeypatch):
    """Measured on one run: a salvage was refused as "Message too long: 149266 tokens exceeds the context"."""
    from app.models import server_profile

    _supported()
    monkeypatch.setattr(server_profile, "current", lambda: server_profile.ServerProfile(slot_context=131_072))
    server = _Server([_completion("Fixed.")])
    reply_salvage.remember_reasoning("r" * 200_000)

    reply_salvage.salvaged(_model(server), [], _cut_at(100_000))

    kept = server.sent[0]["messages"][-1]["reasoning_content"]
    assert len(kept) <= (131_072 - 100_000 - reply_salvage.SALVAGE_REPLY_TOKENS - 1_024) * 3 + len(reply_salvage.ENOUGH) + 2


def test_a_request_that_leaves_no_room_is_not_salvaged(monkeypatch):
    from app.models import server_profile

    _supported()
    monkeypatch.setattr(server_profile, "current", lambda: server_profile.ServerProfile(slot_context=131_072))
    server = _Server([])
    reply_salvage.remember_reasoning("r" * 200_000)
    cut = _cut_at(120_000)

    assert reply_salvage.salvaged(_model(server), [], cut) is cut
    assert server.sent == []


def test_the_begun_reply_the_server_echoes_is_not_taken_for_the_answer():
    """Measured on one run: salvaged fix answers began `<think>` and the model's own reasoning, read as prose."""
    reply_salvage.keep("local-model", reply_salvage.Support(shape="think_tags", tools=True, continuation=True,
                                                            long_shape="think_tags", model="local-model"))
    reply_salvage.remember_reasoning(REASONING)
    echoed = reply_salvage.begun_reply("think_tags", REASONING)["content"] + '{"changed_files": ["app/routes.py"]}'
    server = _Server([_completion(echoed)])

    result = reply_salvage.salvaged(_model(server), [HumanMessage(content="Fix the defect.")], _cut())

    assert result.generations[0].message.content == '{"changed_files": ["app/routes.py"]}'


def test_a_leading_closed_reasoning_block_is_taken_off_the_answer_too():
    message = AIMessage(content="<think>\nhalf a word of reasoning\n</think>\n\nThe answer.")
    reply_salvage._without_the_reasoning_it_was_given(message, {"content": "something else"})
    assert message.content == "The answer."
