"""A request a model server refuses for its images goes again without them, and the model is kept as reading none.

Measured on one run: fixers were sent the page's screenshots because the served model's capability record said it
read images (its model card's task, image-text-to-text, stood), while the server held no vision part. The server
answered every request with a 500 "image input is not supported - hint: ... provide the mmproj"; a 500 looked like a
passing fault, the same request was asked again until the stage, and then the run, failed. The capability probe had
met the same 500 and kept nothing, because only a 4xx counted as a refusal.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

import httpx
import openai
import pytest
from langchain_core.messages import HumanMessage

from app import models
from app.models import capabilities, image_refusal

#: The server's answer, exactly as the run's fixers met it.
REFUSED = ("Error code: 500 - {'error': {'code': 500, 'message': 'image input is not supported - hint: if this is "
           "unexpected, you may need to provide the mmproj', 'type': 'server_error'}}")
REFUSED_BODY = {"error": {"code": 500, "message": "image input is not supported - hint: if this is unexpected, you may "
                          "need to provide the mmproj", "type": "server_error"}}
MODEL = "qwen3.6-35b-a3b"
ANSWER = {"id": "x", "object": "chat.completion", "created": 0, "model": MODEL,
          "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}]}
PICTURE = {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="}}
BANNED = re.compile(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path / "gate"))
    monkeypatch.setattr(models.time, "sleep", lambda seconds: None)
    image_refusal.forget()
    yield
    image_refusal.forget()


def _has_a_picture(body: dict) -> bool:
    return any(isinstance(m.get("content"), list) and any(p.get("type") == "image_url" for p in m["content"])
               for m in body["messages"])


def _server_without_vision(sent: list):
    """llama.cpp without a projector, as measured: a 500 for any request with an image, an answer otherwise."""
    def serve(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(body)
        if _has_a_picture(body):
            return httpx.Response(500, json=REFUSED_BODY)
        return httpx.Response(200, json=ANSWER)

    return serve


def _client(serve) -> models.CompatibleChatOpenAI:
    return models.CompatibleChatOpenAI(model=MODEL, base_url="http://model-server:8080/v1", api_key="k", max_retries=0,
                                       http_client=httpx.Client(transport=httpx.MockTransport(serve)))


def _a_fix_request() -> list:
    return [HumanMessage(content=[{"type": "text", "text": "Fix the defect: the list overflows on a phone."
                                   "\n\n--- How the page looks now ---\nAfter this text are screenshots."}, PICTURE])]


@pytest.mark.parametrize("said", [
    REFUSED,
    # Kept in model records, cut where they were kept, as the probe met them on other servers (LM Studio, a hosted
    # text-only model).
    "Error code: 400 - {'error': {'message': 'Image provided but current GGUF model d",
    "Error code: 400 - {'error': {'message': 'The provided messages contain images, b",
])
def test_a_server_s_own_words_for_refusing_images_are_recognised(said):
    assert image_refusal.says_images_are_refused(RuntimeError(said)) is True


@pytest.mark.parametrize("said", [
    "Error code: 503 - model_unavailable",
    "Error code: 500 - {'error': {'message': 'Failed to parse tool call arguments as JSON'}}",
    "Error code: 400 - {'error': {'message': 'Context size has been exceeded.'}}",
])
def test_other_failures_are_not_taken_for_an_image_refusal(said):
    assert image_refusal.says_images_are_refused(RuntimeError(said)) is False


def test_a_request_refused_for_its_images_is_answered_without_them():
    sent: list = []

    reply = _client(_server_without_vision(sent)).invoke(_a_fix_request())

    assert reply.content == "ok"
    assert [_has_a_picture(body) for body in sent] == [True, False]  # one refusal, then once without, no repeats
    text = sent[-1]["messages"][-1]["content"]
    assert "the list overflows on a phone" in text and "could not be shown" in text
    assert not BANNED.search(text)


def test_the_rest_of_the_stage_s_calls_are_sent_no_images():
    sent: list = []
    model = _client(_server_without_vision(sent))
    model.invoke(_a_fix_request())
    sent.clear()

    model.invoke(_a_fix_request())

    assert [_has_a_picture(body) for body in sent] == [False]


def test_a_model_whose_server_refused_its_images_is_kept_as_reading_none():
    from app.models.registry import merge_into_fitness

    merge_into_fitness(MODEL, {capabilities.FOUND_KEY: {"reads_images": {
        "value": True, "source": "model card", "note": "its task is image-text-to-text"}}})

    _client(_server_without_vision([])).invoke(_a_fix_request())

    assert capabilities.value(MODEL, "reads_images") is False


# --- the capability record ---------------------------------------------------


def _probed(serve) -> SimpleNamespace:
    return SimpleNamespace(model_name=MODEL, root_client=openai.OpenAI(
        base_url="http://model-server:8080/v1", api_key="k", max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(serve))))


def _fill(monkeypatch, serve, *, card: bool | None, server: bool | None) -> dict:
    monkeypatch.setattr(capabilities, "look_up", lambda names: {} if card is None else {
        "reads_images": capabilities._found(card, "model card", "its task is image-text-to-text")})
    monkeypatch.setattr(capabilities, "from_the_server", lambda: {} if server is None else {
        "reads_images": capabilities._found(server, "server", "/props")})
    monkeypatch.setattr("app.models.diagnostics.the_model_answers", lambda model: True)
    return capabilities.fill(_probed(serve), MODEL, MODEL)


def test_an_image_probe_refused_with_a_500_records_that_the_model_reads_none(monkeypatch):
    found = _fill(monkeypatch, _server_without_vision([]), card=True, server=None)

    assert found["reads_images"]["value"] is False and found["reads_images"]["source"] == "measured"


def test_a_server_that_holds_no_vision_part_beats_the_model_card(monkeypatch):
    found = _fill(monkeypatch, _server_without_vision([]), card=True, server=False)

    assert found["reads_images"]["value"] is False


def test_a_model_card_s_yes_alone_is_not_taken(monkeypatch):
    def does_not_answer_the_probe(request: httpx.Request) -> httpx.Response:
        if _has_a_picture(json.loads(request.content)):
            raise httpx.ConnectError("Connection refused")
        return httpx.Response(200, json=ANSWER)

    _fill(monkeypatch, does_not_answer_the_probe, card=True, server=None)

    assert capabilities.value(MODEL, "reads_images") is None
