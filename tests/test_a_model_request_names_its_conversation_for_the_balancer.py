"""A request to a self-hosted model server names its run and stage, so a balancer keeps each conversation on one server.

Measured: olla in front of two llama.cpp instances had no session header to key on, hashed every request's first 512
bytes - nearly the same system-prompt opening for every stage - and sent 149 requests to one instance and 82 to the
other, at times queueing a request on one GPU while the other sat idle.
"""
from __future__ import annotations

import httpx
from langchain_core.messages import HumanMessage

from app import models
from app.observability.transcript import asked_for


def _a_model_server(address: str, seen: list[httpx.Request]) -> models.CompatibleChatOpenAI:
    def server(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={
            "id": "x", "object": "chat.completion", "created": 0, "model": "m",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
        })

    return models.CompatibleChatOpenAI(
        model="m", base_url=address, api_key="k", max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(server)),
    )


def _sent_in(stage: str, run: str | None, address: str = "http://gpu:9090/v1") -> httpx.Request:
    seen: list[httpx.Request] = []
    model = _a_model_server(address, seen)
    with asked_for(stage, run):
        model.invoke([HumanMessage(content="go on")])
    return seen[-1]


def test_a_request_in_a_stage_of_a_run_names_that_run_and_stage(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path))
    monkeypatch.delenv("MODEL_SESSION_HEADER", raising=False)
    monkeypatch.delenv("MODEL_SESSION_SCOPE", raising=False)

    request = _sent_in("defect_fix_2_3", "run-one")

    assert request.headers.get("X-Olla-Session-ID") == "run-one:defect_fix_2_3"


def test_two_stages_of_one_run_are_two_conversations(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path))
    monkeypatch.delenv("MODEL_SESSION_HEADER", raising=False)
    monkeypatch.delenv("MODEL_SESSION_SCOPE", raising=False)

    first =_sent_in("defect_fix_2_3", "run-one").headers.get("X-Olla-Session-ID")
    second = _sent_in("defect_fix_2_4", "run-one").headers.get("X-Olla-Session-ID")

    assert (first, second) == ("run-one:defect_fix_2_3", "run-one:defect_fix_2_4")


def test_a_hosted_api_is_never_sent_the_header(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path))
    monkeypatch.delenv("MODEL_SESSION_HEADER", raising=False)
    monkeypatch.delenv("OPENAI_ENDPOINT_KIND", raising=False)

    request = _sent_in("defect_fix_2_3", "run-one", address="https://api.openai.com/v1")

    assert "x-olla-session-id" not in request.headers


def test_an_empty_setting_sends_no_header(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path))
    monkeypatch.setenv("MODEL_SESSION_HEADER", "")

    request = _sent_in("defect_fix_2_3", "run-one")

    assert not any("session" in name.lower() for name in request.headers)


def test_another_balancer_s_header_name_is_used_when_set(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path))
    monkeypatch.setenv("MODEL_SESSION_HEADER", "X-Session-Affinity")
    monkeypatch.delenv("MODEL_SESSION_SCOPE", raising=False)

    request = _sent_in("architect", "run-one")

    assert request.headers.get("X-Session-Affinity") == "run-one:architect"
    assert "x-olla-session-id" not in request.headers


def _two_requests_in(stage: str, run: str) -> list[str | None]:
    seen: list[httpx.Request] = []
    model = _a_model_server("http://gpu:9090/v1", seen)
    with asked_for(stage, run):
        model.invoke([HumanMessage(content="go on")])
        model.invoke([HumanMessage(content="and on")])
    return [request.headers.get("X-Olla-Session-ID") for request in seen]


def test_by_conversation_every_request_of_a_stage_keeps_one_session(tmp_path, monkeypatch):
    """The default scope: one conversation keeps its server and its prompt cache."""
    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path))
    monkeypatch.delenv("MODEL_SESSION_HEADER", raising=False)
    monkeypatch.delenv("MODEL_SESSION_SCOPE", raising=False)

    sessions = _two_requests_in("defect_fix_2_3", "run-one")

    assert sessions == ["run-one:defect_fix_2_3", "run-one:defect_fix_2_3"]


def test_by_request_every_request_is_a_new_session(tmp_path, monkeypatch):
    """`request` scope: the balancer picks the least-busy server for each call, so no two requests share a session."""
    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path))
    monkeypatch.delenv("MODEL_SESSION_HEADER", raising=False)
    monkeypatch.setenv("MODEL_SESSION_SCOPE", "request")

    first, second = _two_requests_in("defect_fix_2_3", "run-one")

    assert first and second and first != second
    assert first.startswith("run-one:defect_fix_2_3:") and second.startswith("run-one:defect_fix_2_3:")
