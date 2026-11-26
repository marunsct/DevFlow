"""A model call with no conversation to reuse, and each part of a side-by-side fan-out, goes out under a session of its
own, so a balancer can put it on an idle server (LF.1576).

Measured with olla over two llama.cpp instances of two slots each: every one-shot rewrite of a run went out with the
run's id alone as its session (no stage is known outside an agent), olla kept that one session on one instance, and
four calls sat on it for 214-656 s while the other instance was idle. An agent's own conversation still keeps
`<run>:<stage>` (`test_a_model_request_names_its_conversation_for_the_balancer`).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from langchain_core.messages import HumanMessage

from app import models
from app.models.model_pin import as_the_run
from app.observability.direct_calls import mapped_in_this_context
from app.observability.transcript import asked_for

HEADER = "X-Olla-Session-ID"


def _a_model_server(seen: list[httpx.Request]) -> models.CompatibleChatOpenAI:
    def server(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={
            "id": "x", "object": "chat.completion", "created": 0, "model": "m",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
        })

    return models.CompatibleChatOpenAI(
        model="m", base_url="http://gpu:9090/v1", api_key="k", max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(server)),
    )


@pytest.fixture
def by_conversation(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path))
    monkeypatch.delenv("MODEL_SESSION_HEADER", raising=False)
    monkeypatch.delenv("MODEL_SESSION_SCOPE", raising=False)


def test_one_shot_calls_of_a_run_with_no_stage_known_go_out_under_sessions_of_their_own(by_conversation):
    """The measured shape: a graph node's one-call rewrites named the run alone, and all shared one server."""
    seen: list[httpx.Request] = []
    model = _a_model_server(seen)

    with as_the_run("run-one"):
        model.invoke([HumanMessage(content="rewrite the first file")])
        model.invoke([HumanMessage(content="rewrite the second file")])

    first, second = (request.headers.get(HEADER) for request in seen)
    assert first != second
    assert first.startswith("run-one:") and second.startswith("run-one:")


@pytest.mark.parametrize("stage", ["", "defect_fix_2_3"], ids=["a graph node's fan-out", "a fan-out inside a stage"])
def test_each_part_of_a_side_by_side_fan_out_keeps_a_session_no_sibling_shares(by_conversation, stage):
    """Candidate fixes asked at once: each part its own session (for its own server), and a part's own second call
    (a retry) on the session it began on."""
    seen: list[httpx.Request] = []
    model = _a_model_server(seen)

    def a_part(number: int) -> list[str]:
        model.invoke([HumanMessage(content=f"candidate {number}")])
        model.invoke([HumanMessage(content=f"candidate {number}, again")])
        return [request.headers.get(HEADER) for request in seen
                if f"candidate {number}" in request.content.decode()]

    with asked_for(stage, "run-one"), ThreadPoolExecutor(max_workers=3) as pool:
        parts = mapped_in_this_context(pool, a_part, [1, 2, 3])

    assert all(len(set(sessions)) == 1 for sessions in parts)
    assert len({sessions[0] for sessions in parts}) == 3
    assert all(sessions[0].startswith(f"run-one:{stage}:" if stage else "run-one:") for sessions in parts)


def test_a_call_outside_any_run_still_names_a_session_of_its_own(by_conversation):
    """A measurement of the model outside a run sent no header, and the balancer hashed its identical openings onto
    one server."""
    seen: list[httpx.Request] = []
    model = _a_model_server(seen)

    model.invoke([HumanMessage(content="measure")])
    model.invoke([HumanMessage(content="measure")])

    first, second = (request.headers.get(HEADER) for request in seen)
    assert first and second and first != second
