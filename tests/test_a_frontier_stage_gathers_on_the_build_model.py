"""Fast delivery: a frontier stage gathers on the build model, and planning that only records runs on it.

Measured on one run: of a frontier model's 143 calls before any product was
built, 120 only gathered facts - a listing, a file, a page of documentation,
a package - each after 2 to 5 minutes of reasoning (77 minutes in all).
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
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
    scripted = {build: [_reply("ls"), _reply("read_docs"), _reply("Answer")], frontier: [_reply("Answer")]}
    asked = []

    def handler(request):
        asked.append("build" if request.model is build else "frontier")
        return scripted[request.model].pop(0)

    middleware = gathering.build_gathering_middleware(build, "Answer")
    request = _Request(model=frontier)

    replies = [middleware.wrap_model_call(request, handler) for _ in range(3)]

    assert asked == ["build", "build", "build", "frontier"]
    assert replies[2].result[-1].tool_calls[0]["name"] == "Answer", "the frontier's answer, not the build model's"


def test_after_the_frontier_s_turn_a_read_is_the_build_model_s_again_a_few_in_a_row():
    """A building stage on the frontier spent 40 minutes, half its turns reading."""
    build, frontier = object(), object()
    asked = []

    def handler(request):
        asked.append("build" if request.model is build else "frontier")
        if request.model is frontier:
            return _reply("write_artifact")
        return _reply("read_file") if len(asked) > 1 else _reply("edit_file")

    middleware = gathering.build_gathering_middleware(build, "Answer")
    replies = [middleware.wrap_model_call(_Request(model=frontier), handler) for _ in range(6)]

    names = [r.result[-1].tool_calls[0]["name"] for r in replies]
    assert names == ["write_artifact", *["read_file"] * gathering.MOST_IN_A_ROW, "write_artifact", "read_file"][:6]
    assert asked[:2] == ["build", "frontier"], "the build model's edit is never made"


def test_the_build_model_s_attempts_in_a_visit_are_bounded(monkeypatch):
    monkeypatch.setattr(gathering, "MOST_BUILD_TURNS", 4)
    build, frontier = object(), object()
    asked = []

    def handler(request):
        asked.append("build" if request.model is build else "frontier")
        return _reply("read_file")

    middleware = gathering.build_gathering_middleware(build, "Answer")
    for _ in range(8):
        middleware.wrap_model_call(_Request(model=frontier), handler)

    assert asked.count("build") == 4 and asked[-4:] == ["frontier"] * 4


def test_a_build_model_that_cannot_answer_hands_the_turn_to_the_frontier():
    build, frontier = object(), object()

    def handler(request):
        if request.model is build:
            raise RuntimeError("the build model server is down")
        return _reply("Answer")

    middleware = gathering.build_gathering_middleware(build, "Answer")
    reply = middleware.wrap_model_call(_Request(model=frontier), handler)
    middleware.wrap_model_call(_Request(model=frontier), lambda request: (_ for _ in ()).throw(AssertionError("asked the build model again")) if request.model is build else _reply("ls"))

    assert reply.result[-1].tool_calls[0]["name"] == "Answer"


def test_a_write_or_a_command_is_the_frontier_s_to_make():
    """Only reading is gathering: a stage on the frontier writes and runs on it."""
    for work in ("write_artifact", "edit_file", "run_validation", "run_terminal_command"):
        build, frontier = object(), object()
        scripted = {build: [_reply("read_file"), _reply("ls", work)], frontier: [_reply(work)]}
        asked = []

        def handler(request):
            asked.append("build" if request.model is build else "frontier")
            return scripted[request.model].pop(0)

        middleware = gathering.build_gathering_middleware(build, "Answer")
        replies = [middleware.wrap_model_call(_Request(model=frontier), handler) for _ in range(2)]

        assert asked == ["build", "build", "frontier"], work
        assert [c["name"] for c in replies[1].result[-1].tool_calls] == [work], "the frontier's call, not the build model's"


def test_only_agents_on_a_registered_judgement_model_gather():
    class Model:
        pass

    judgement, build, other = Model(), Model(), Model()
    gathering.gather_with(judgement, build)

    assert gathering.gatherer_for(judgement) is build
    assert gathering.gatherer_for(other) is None
    assert len(role_agent._gathering(judgement, Answer)) == 1
    assert role_agent._gathering(other, Answer) == []


def _on_two_models(monkeypatch, fast):
    """A run on a build model and a distinct judgement model, planning on the judgement model as the owner sets it."""
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    gathered = []
    monkeypatch.setattr("app.delivery.fast", lambda *a, **k: fast)
    monkeypatch.setattr("app.models.roles.plans_on_the_judgement_model", lambda *a, **k: True)
    monkeypatch.setattr("app.agents.thinking.without_reasoning",
                        lambda model: FakeListChatModel(responses=["unused"], name=f"quiet {model.name}"))
    monkeypatch.setattr(gathering, "gather_with", lambda judge, gatherer: gathered.append((judge.name, gatherer.name)))
    return gathered


def _built_on(monkeypatch, tmp_path, node, **state):
    from workflow_node_stubs import run_node

    seen = run_node(monkeypatch, tmp_path, node, two_models=True, **state)
    return [(factory, getattr(model, "name", model)) for factory, model in seen.agents]


@pytest.mark.parametrize("fast", [True, False], ids=["fast", "not-fast"])
def test_fast_delivery_keeps_the_specification_and_reviews_on_the_frontier_and_moves_the_rest(fast, tmp_path, monkeypatch):
    from app.agents.principal_architect import TechnicalSpecificationOutput
    from app.agents.product_manager import ProductManagerOutput
    from app.agents.specialist_advice import SpecialistAdvice
    from workflow_node_stubs import run_node

    gathered = _on_two_models(monkeypatch, fast)
    run_node(monkeypatch, tmp_path, "complete", two_models=True)
    # In every delivery mode, a stage on the judgement model gathers on the build model with reasoning off.
    assert gathered == [("judge", "quiet build")]

    intake = run_node(monkeypatch, tmp_path, "product_manager", two_models=True,
                      answer=ProductManagerOutput(product_name="Notes"),
                      document=SimpleNamespace(text="Notes.", source_path="brief.md", source_type="markdown", truncated=False))
    assert [getattr(m, "name", m) for _, m in intake.agents] == ["build" if fast else "judge"], "planning"

    consult = _built_on(monkeypatch, tmp_path, "specialist_consultation", consultation_roles=["backend"],
                        answer=SpecialistAdvice(recommendations=["Validate the body"]), document=SimpleNamespace(text=""))
    assert consult == [("create_specialist_advice_agent", "build" if fast else "judge")]

    architect = _built_on(monkeypatch, tmp_path, "principal_architect",
                          answer=TechnicalSpecificationOutput(product_scope="Notes."),
                          product_intake=ProductManagerOutput(product_name="Notes"), tools_models={"plan": "local"},
                          document=SimpleNamespace(text="Notes."))
    assert ("create_principal_architect_agent", "judge") in architect

    from app.agents.architecture_reviewer import ArchitectureReviewOutput

    review = _built_on(monkeypatch, tmp_path, "architecture_review", answer=ArchitectureReviewOutput(status="approved"),
                       technical_specification=TechnicalSpecificationOutput(product_scope="Notes."),
                       document=SimpleNamespace(text="Notes."))
    assert review == [("create_architecture_reviewer_agent", "judge")]


def test_the_testing_author_moves_to_the_build_model_in_fast_delivery():
    """In `acceptance_nodes`, not the graph."""
    author = inspect.getsource(acceptance_nodes)
    assert '"testing", model=ctx.model if delivery.fast() else ctx.judgement_model' in author


@pytest.mark.parametrize("fast, then", [(True, "escalation"), (False, "principal_architect")], ids=["fast", "not-fast"])
def test_fast_delivery_sends_the_specification_back_once(fast, then, tmp_path, monkeypatch):
    from app.agents.architecture_reviewer import ArchitectureReviewFinding, ArchitectureReviewOutput
    from app.agents.principal_architect import TechnicalSpecificationOutput
    from workflow_node_stubs import run_node

    monkeypatch.setattr("app.delivery.fast", lambda *a, **k: fast)
    blocking = ArchitectureReviewOutput(status="changes_required", findings=[ArchitectureReviewFinding(
        severity="blocking", description="No authentication described.", evidence="security",
        required_remediation="Describe it.")])

    seen = run_node(monkeypatch, tmp_path, "architecture_review", answer=blocking, architecture_revision_count=1,
                    technical_specification=TechnicalSpecificationOutput(product_scope="Notes."),
                    document=SimpleNamespace(text="Notes."))

    assert workflow._the_revision_limit() == (2 if fast else workflow.MAX_ARCHITECTURE_REVISIONS)
    assert seen.update["stage"] == then and seen.update["architecture_revision_count"] == 2


def test_fast_delivery_sends_the_suite_back_once():
    """In `acceptance_nodes`, not the graph."""
    assert "limit = 2 if delivery.fast() else MAX_ACCEPTANCE_ROUNDS" in inspect.getsource(acceptance_nodes)


def test_fast_delivery_is_read_from_the_mode_module_inside_the_graph(monkeypatch):
    """Inside the graph builder `delivery` names the sprint-evidence module; one
    review node called `delivery.fast()` there and failed."""
    from app import delivery

    monkeypatch.setattr(delivery, "fast", lambda environment=None: True)
    assert workflow._fast_delivery() is True


def test_a_gathering_turn_is_held_to_a_short_reply_and_a_cut_off_one_is_the_frontier_s():
    """A gathering turn ran on for 20,000 tokens - 7 minutes - and ended with no call."""
    from langchain_openai import ChatOpenAI

    build = ChatOpenAI(model="m", api_key="k", base_url="http://localhost:1/v1", max_tokens=20_000)
    frontier = object()
    used = []

    def handler(request):
        used.append(request.model)
        if request.model is frontier:
            return _reply("read_file")
        cut = AIMessage(content="", tool_calls=[{"name": "read_file", "args": {}, "id": "r"}],
                        response_metadata={"finish_reason": "length"})
        return SimpleNamespace(result=[cut])

    middleware = gathering.build_gathering_middleware(build, "Answer")
    middleware.wrap_model_call(_Request(model=frontier), handler)

    assert used[0].max_tokens == gathering.MOST_GATHERING_TOKENS and build.max_tokens == 20_000
    assert used[1] is frontier, "a cut-off gathering turn is the frontier's"


def test_a_build_model_that_keeps_not_gathering_is_offered_no_more_turns():
    """A specification stage's build model began the answer before nearly every judgement turn."""
    build, frontier = object(), object()
    asked = []

    def handler(request):
        asked.append("build" if request.model is build else "frontier")
        if request.model is frontier:
            return _reply("read_docs")
        return _reply("read_file") if asked.count("build") == 1 else _reply("Answer")

    middleware = gathering.build_gathering_middleware(build, "Answer")
    for _ in range(7):
        middleware.wrap_model_call(_Request(model=frontier), handler)

    # A read; then the frontier's turn after each of two misses; then the frontier alone.
    assert asked == ["build", "build", "frontier", "build", "frontier", "frontier", "frontier", "frontier", "frontier"]
