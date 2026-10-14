"""Fast delivery: a frontier stage gathers on the build model, and planning that only records runs on it.

Measured on one run: of a frontier model's 143 calls before any product was
built, 120 only gathered facts - a listing, a file, a page of documentation,
a package - each after 2 to 5 minutes of reasoning (77 minutes in all).
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

from langchain_core.messages import AIMessage
from pydantic import BaseModel

from app.agents import gathering, role_agent
from app.graph import acceptance_nodes, workflow


class Answer(BaseModel):
    text: str


class _Request(SimpleNamespace):
    def override(self, **changes):
        return _Request(**{**self.__dict__, **changes})


def _reply(*calls):
    return SimpleNamespace(result=[AIMessage(content="", tool_calls=[{"name": n, "args": {}, "id": n} for n in calls])])


def test_gathering_turns_run_on_the_build_model_and_the_answer_on_the_frontier():
    build, frontier = object(), object()
    scripted = {build: [_reply("ls"), _reply("read_docs"), _reply("Answer")], frontier: [_reply("Answer"), _reply("ls")]}
    asked = []

    def handler(request):
        asked.append("build" if request.model is build else "frontier")
        return scripted[request.model].pop(0)

    middleware = gathering.build_gathering_middleware(build, "Answer")
    request = _Request(model=frontier)

    replies = [middleware.wrap_model_call(request, handler) for _ in range(4)]

    assert asked == ["build", "build", "build", "frontier", "frontier"]
    assert replies[2].result[-1].tool_calls[0]["name"] == "Answer", "the frontier's answer, not the build model's"
    assert replies[3].result[-1].tool_calls[0]["name"] == "ls", "the rest of the visit stays with the frontier"


def test_a_build_model_that_cannot_answer_hands_the_turn_to_the_frontier():
    build, frontier = object(), object()

    def handler(request):
        if request.model is build:
            raise RuntimeError("the build model server is down")
        return _reply("Answer")

    reply = gathering.build_gathering_middleware(build, "Answer").wrap_model_call(_Request(model=frontier), handler)

    assert reply.result[-1].tool_calls[0]["name"] == "Answer"


def test_only_agents_on_a_registered_judgement_model_gather():
    class Model:
        pass

    judgement, build, other = Model(), Model(), Model()
    gathering.gather_with(judgement, build)

    assert gathering.gatherer_for(judgement) is build
    assert gathering.gatherer_for(other) is None
    assert len(role_agent._gathering(judgement, Answer)) == 1
    assert role_agent._gathering(other, Answer) == []


def test_fast_delivery_keeps_the_specification_and_reviews_on_the_frontier_and_moves_the_rest():
    source = inspect.getsource(workflow)
    assert "planning_model = judgement_model if plans_on_the_judgement_model() and not _fast_delivery() else model" in source
    assert "gather_with(judgement_model, building_model)" in source
    consult = source[source.index("def specialist_consultation_node"):source.index("def principal_architect_node")]
    assert "model=model if _fast_delivery() else judgement_model" in consult
    assert "create_principal_architect_agent(model=judgement_model" in source
    assert "create_architecture_reviewer_agent(model=judgement_model" in source
    author = inspect.getsource(acceptance_nodes)
    assert '"testing", model=ctx.model if delivery.fast() else ctx.judgement_model' in author


def test_fast_delivery_sends_the_specification_and_the_suite_back_once():
    assert "revision_count >= (2 if _fast_delivery() else MAX_ARCHITECTURE_REVISIONS)" in inspect.getsource(workflow)
    assert "rounds < (2 if delivery.fast() else MAX_ACCEPTANCE_ROUNDS)" in inspect.getsource(acceptance_nodes)


def test_fast_delivery_is_read_from_the_mode_module_inside_the_graph(monkeypatch):
    """Inside the graph builder `delivery` names the sprint-evidence module; one
    review node called `delivery.fast()` there and failed."""
    from app import delivery

    monkeypatch.setattr(delivery, "fast", lambda environment=None: True)
    assert workflow._fast_delivery() is True
