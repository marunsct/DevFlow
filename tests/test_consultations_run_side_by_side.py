"""In parallel mode the specialists' consultations before the specification are asked side by side (LF.1595).

Measured on one run: four consultations one after another - database, backend, security, testing - took about seven
minutes with two model slots free, though each reads only the brief, the intake, the stack and the repository and
none another's advice. Now they go together up to the run's cap (`HARNESS_MAX_PARALLEL` and the server's slots);
linear mode and a cap of one still ask them in turn.
"""

from __future__ import annotations

import dataclasses
import threading

import pytest

from app.agents.approval import approve_write_decision
from app.agents.specialist_advice import SpecialistAdvice
from app.graph.workflow import resume_pending_approval, start_workflow
from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    ScriptedAgents,
    _approved_review,
    _document,
    _graph,
    _repository,
    _script_through_sprint,
    _spec,
    agents,
    pause_for_approval,
    responds_with,
)
from test_the_specialists_advise_before_the_specification import TestThroughTheGraph as Consulting

ADVICE = {
    "database": ["Give every record an id."],
    "backend": ["Answer a missing record with 404."],
    "security_reliability": ["Escape every title before it is shown."],
}


@pytest.fixture
def parallel(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config

    real = config.load_settings()
    monkeypatch.setattr(
        config, "load_settings", lambda *args, **kwargs: dataclasses.replace(real, execution_mode="parallel"),
    )


class _Overlap:
    """How many advisers were answering at once, at most: each waits a moment for another to join it."""

    def __init__(self, wait: float) -> None:
        self.wait = wait
        self.now = 0
        self.peak = 0
        self.lock = threading.Condition()

    def around(self, agent):
        overlap = self

        class _Timed:
            def invoke(self, payload, config=None):
                with overlap.lock:
                    overlap.now += 1
                    overlap.peak = max(overlap.peak, overlap.now)
                    overlap.lock.notify_all()
                    overlap.lock.wait_for(lambda: overlap.now >= 2, timeout=overlap.wait)
                try:
                    return agent.invoke(payload, config)
                finally:
                    with overlap.lock:
                        overlap.now -= 1

        return _Timed()


def _consulting(agents: ScriptedAgents, monkeypatch, roles: list[str], overlap: _Overlap) -> None:
    from app.graph import workflow as workflow_module

    Consulting._consulting(monkeypatch, agents, roles)
    monkeypatch.setattr(
        workflow_module, "create_specialist_advice_agent",
        lambda role, *args, **kwargs: overlap.around(agents.agent(f"advisor_{role}")),
    )
    Consulting._script_the_stack(agents)
    ids = {"database": "DB-1", "backend": "BE-1", "security_reliability": "SR-1"}
    agents.script("principal_architect", [responds_with(_spec(
        specialist_advice_decisions=[f"{ids[role]}: adopted" for role in roles],
    ))])
    agents.script("architecture_review", [responds_with(_approved_review())])
    _script_through_sprint(agents, advice=[ids[role] for role in roles])


def test_the_specialists_are_asked_side_by_side_up_to_the_cap(agents, monkeypatch, parallel, tmp_path) -> None:
    monkeypatch.setenv("HARNESS_MAX_PARALLEL", "2")
    overlap = _Overlap(wait=2.0)
    _consulting(agents, monkeypatch, list(ADVICE), overlap)
    for role, lines in ADVICE.items():
        agents.script(f"advisor_{role}", [responds_with(SpecialistAdvice(recommendations=lines))])

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-consulted-side-by-side")

    assert state["stage"] == "complete", state.get("error")
    assert overlap.peak == 2
    assert {role: len(agents.requests[f"advisor_{role}"]) for role in ADVICE} == {role: 1 for role in ADVICE}
    assert state["specialist_advice"] == ADVICE
    assert "DB-1:" in agents.last_request_text("principal_architect")
    assert not state.get("consultations_in_flight")


@pytest.mark.parametrize("mode, cap", [("linear", "6"), ("parallel", "1")])
def test_linear_mode_or_a_cap_of_one_asks_them_in_turn(agents, monkeypatch, tmp_path, mode, cap) -> None:
    from app import config

    real = config.load_settings()
    monkeypatch.setattr(config, "load_settings", lambda *args, **kwargs: dataclasses.replace(real, execution_mode=mode))
    monkeypatch.setenv("HARNESS_MAX_PARALLEL", cap)
    overlap = _Overlap(wait=0.3)
    _consulting(agents, monkeypatch, ["database", "backend"], overlap)
    for role in ("database", "backend"):
        agents.script(f"advisor_{role}", [responds_with(SpecialistAdvice(recommendations=ADVICE[role]))])

    state = start_workflow(_graph(), _document(), _repository(tmp_path), f"run-consulted-in-turn-{mode}")

    assert state["stage"] == "complete", state.get("error")
    assert overlap.peak == 1
    assert state["specialist_advice"] == {role: ADVICE[role] for role in ("database", "backend")}


def test_a_paused_consultation_resumes_and_a_finished_one_is_not_asked_again(
    agents, monkeypatch, parallel, tmp_path,
) -> None:
    monkeypatch.setenv("HARNESS_MAX_PARALLEL", "2")
    overlap = _Overlap(wait=2.0)
    _consulting(agents, monkeypatch, ["database", "backend"], overlap)
    # One answer each: a second request to either adviser fails the run.
    agents.script("advisor_database", [responds_with(SpecialistAdvice(recommendations=ADVICE["database"]))])
    agents.script("advisor_backend", [
        pause_for_approval("docs/backend-notes.md"),
        responds_with(SpecialistAdvice(recommendations=ADVICE["backend"])),
    ])
    graph = _graph()

    paused = start_workflow(graph, _document(), _repository(tmp_path), "run-consultation-paused")
    state = resume_pending_approval(graph, "run-consultation-paused", approve_write_decision())

    assert paused["stage"] == "awaiting_approval:consult_backend"
    assert paused["specialist_advice"] == {"database": ADVICE["database"]}
    assert overlap.peak == 2
    assert state["stage"] == "complete", state.get("error")
    assert len(agents.requests["advisor_database"]) == 1
    assert len(agents.requests["advisor_backend"]) == 2
    assert state["specialist_advice"] == {role: ADVICE[role] for role in ("database", "backend")}
