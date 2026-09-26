"""Parallel execution mode, driven through the controller it changes.

The linear dispatcher runs one delegated task per superstep and counts through
them with `specialist_task_index`. Parallel mode instead fans every independent
task out at once, so a milestone's three specialists call the model
concurrently, and a toggle in the settings chooses between the two.

Nothing exercised it. Three faults each of which ends a run were all reachable
on the first milestone of the first parallel run:

- the worker referred to `cast`, which the module never imported, so the first
  worker to run raised `NameError` before reaching its agent;
- the worker returned only its output, leaving `stage` as the fan-out sentinel
  the dispatcher had set, so the router fanned the same tasks out again on every
  pass - each worker producing a fresh fan-out - until the recursion limit;
- and a worker that paused for approval returned `stage` from inside a fan-out,
  where two workers writing one reducer-less key is `InvalidUpdateError` rather
  than a pause.

The dispatcher's own decision, `execution_mode`, also could not be saved at all:
it was absent from `runtime_settings.SETTABLE_KEYS`, which is the allowlist a
write is checked against. That has its own test in `test_settings_api.py`.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from app.graph import workflow as workflow_module
from app.graph.workflow import start_workflow

# The scripted-agent harness these tests drive the controller with. Imported
# rather than copied: a second copy of the fixture is a second thing to keep in
# step with the controller's stage names.
from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    ScriptedAgents,
    _approved_review,
    _document,
    _graph,
    _milestone,
    _milestone_review,
    _repository,
    _script_through_architecture,
    _security_review,
    _specialist,
    _sprint_plan,
    agents,
    approve_write_decision,
    pause_for_approval,
    responds_with,
    resume_pending_approval,
)


@pytest.fixture
def parallel(monkeypatch: pytest.MonkeyPatch) -> None:
    """Switch the dispatcher into parallel mode, leaving every other setting."""
    from app import config

    real = config.load_settings()
    monkeypatch.setattr(
        config,
        "load_settings",
        lambda *args, **kwargs: dataclasses.replace(real, execution_mode="parallel"),
    )


def _script_a_parallel_sprint(agents: ScriptedAgents, *roles: str) -> None:
    """One milestone with a task per role, then a clean verification round."""
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(_milestone(*roles))])
    for role in set(roles):
        # Two: the delegated task, and - for `testing` - the verification round.
        agents.script(f"specialist_{role}", [responds_with(_specialist())] * 2)
    if "testing" not in roles:
        agents.script("specialist_testing", [responds_with(_specialist())])
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])


class TestTheFanOutTerminates:
    def test_a_parallel_sprint_runs_every_task_once_and_completes(
        self, agents: ScriptedAgents, parallel: None, tmp_path: Any
    ) -> None:
        """The regression test for the fan-out loop.

        A worker that does not change `stage` leaves it as
        `specialist_dispatch_parallel`, and the router turns that into a fresh
        `Send` per task on every pass. Each worker then produces another fan-out,
        so the count of specialist calls grows with each superstep until the
        recursion limit ends the run. "Invoked once" is the assertion that says
        the fan-out closed.
        """
        _script_a_parallel_sprint(agents, "backend", "database", "ui_ux")

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-parallel")

        if state["stage"] == "failed":
            print("ERROR:", state.get("error"))
        assert state["stage"] == "complete"
        assert len(agents.requests["specialist_backend"]) == 1
        assert len(agents.requests["specialist_database"]) == 1
        assert len(agents.requests["specialist_ui_ux"]) == 1

    def test_every_worker_s_output_survives_the_superstep(
        self, agents: ScriptedAgents, parallel: None, tmp_path: Any
    ) -> None:
        """Three concurrent writers, three results.

        The outputs are one merged dictionary precisely so a fan-out cannot end
        with two of its three results discarded by a last-write-wins channel.
        """
        _script_a_parallel_sprint(agents, "backend", "database", "ui_ux")

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-parallel-outputs")

        assert set(state["specialist_outputs"]) == {
            "specialist_backend_0", "specialist_database_1", "specialist_ui_ux_2",
        }

    def test_a_milestone_with_one_task_still_works(
        self, agents: ScriptedAgents, parallel: None, tmp_path: Any
    ) -> None:
        """A fan-out of one is the case that hides reducer mistakes."""
        _script_a_parallel_sprint(agents, "backend")

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-parallel-one")

        assert state["stage"] == "complete"
        assert set(state["specialist_outputs"]) == {"specialist_backend_0"}


class TestPausingInsideAFanOut:
    def test_a_worker_that_pauses_pauses_the_run(
        self, agents: ScriptedAgents, parallel: None, tmp_path: Any
    ) -> None:
        """And does not take it down with `InvalidUpdateError`.

        A pause update carries `stage`, which has no reducer. Returned from a
        fan-out it is a concurrent write, and LangGraph refuses it: "can receive
        only one value per step". The pause is recorded on a merged key instead
        and the join node surfaces it.
        """
        _script_a_parallel_sprint(agents, "backend", "database")
        agents.script("specialist_backend", [
            pause_for_approval("api.py", "Backend write"),
            responds_with(_specialist()),
        ])

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-parallel-pause")

        assert state["stage"] == "awaiting_approval:specialist_backend_0"
        assert state["pending_approval"] is not None
        assert state["pending_approval"].artifact_path == "api.py"

    def test_resuming_does_not_run_the_tasks_that_already_finished(
        self, agents: ScriptedAgents, parallel: None, tmp_path: Any
    ) -> None:
        """A resumed fan-out re-derives itself from the plan.

        The paused stage name maps back to the dispatcher, exactly as in linear
        mode, and the dispatcher would rebuild the whole fan-out - re-running
        every task that had already finished and re-applying its edits. The
        tasks with outputs are therefore not re-sent.
        """
        graph = _graph()
        _script_a_parallel_sprint(agents, "backend", "database")
        agents.script("specialist_backend", [
            pause_for_approval("api.py", "Backend write"),
            responds_with(_specialist()),
        ])

        state = start_workflow(graph, _document(), _repository(tmp_path), "run-parallel-resume")
        assert state["stage"] == "awaiting_approval:specialist_backend_0"
        database_calls = len(agents.requests["specialist_database"])
        assert database_calls == 1, "the other task ran while the first was waiting"

        state = resume_pending_approval(graph, "run-parallel-resume", approve_write_decision())

        if state["stage"] == "failed":
            print("ERROR:", state.get("error"))
        assert len(agents.requests["specialist_database"]) == database_calls, (
            "the finished task was not run a second time"
        )
        assert state["stage"] == "complete"


class TestTheToggleIsHonoured:
    """Saving the setting is not the same as the dispatcher reading it.

    Three things had to line up and none of them did. `execution_mode` was
    missing from `runtime_settings.SETTABLE_KEYS`, so a write raised
    `ValueError: Not a settable key`. Once that was fixed the value was stored
    and displayed - and the dispatcher called bare `load_settings()`, which is a
    pure function of the environment it is handed and reads this container's own
    when handed nothing. The store is layered in by `effective_environment`, so
    without that step the toggle read `linear` on every dispatch no matter what
    the settings page said.
    """

    def test_execution_mode_is_a_settable_key(self):
        from app.server.runtime_settings import SETTABLE_KEYS

        assert SETTABLE_KEYS.get("execution_mode") == "EXECUTION_MODE"

    def test_the_stored_setting_is_what_the_dispatcher_dispatches_on(
        self, agents: ScriptedAgents, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """Set through the store's own layering, not by patching `load_settings`.

        Patching `load_settings` is what every other test here does, and it
        cannot catch this: it replaces the function the dispatcher was wrongly
        calling, so the wrong call site passes. This one leaves the call site
        alone and puts the value where an administrator's write puts it.
        """
        from app.server import runtime_settings

        monkeypatch.setattr(runtime_settings, "overrides",
                            lambda refresh=False: {"execution_mode": "parallel"})
        monkeypatch.setattr(runtime_settings, "secrets", lambda refresh=False: {})

        _script_a_parallel_sprint(agents, "backend", "database", "ui_ux")
        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-toggle")

        if state["stage"] == "failed":
            print("ERROR:", state.get("error"))
        assert state["stage"] == "complete"
        assert set(state["specialist_outputs"]) == {
            "specialist_backend_0", "specialist_database_1", "specialist_ui_ux_2",
        }
        # Which path ran, not just that some path did. Both modes finish three
        # tasks, so the outputs alone cannot tell them apart: `specialist_task_index`
        # is the linear dispatcher's counter and reaches the task count, and the
        # fan-out never touches it.
        assert state.get("specialist_task_index", 0) == 0, "the fan-out ran, not the counter"


class TestTheModesAgree:
    def test_linear_mode_is_unchanged_by_any_of_this(
        self, agents: ScriptedAgents, tmp_path: Any
    ) -> None:
        """The toggle adds a mode; it does not replace the one that worked."""
        _script_a_parallel_sprint(agents, "backend", "database", "ui_ux")

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-linear")

        assert state["stage"] == "complete"
        assert set(state["specialist_outputs"]) == {
            "specialist_backend_0", "specialist_database_1", "specialist_ui_ux_2",
        }


class TestTheOutputsReducer:
    """`specialist_outputs` has to merge concurrently *and* be resettable."""

    def test_entries_from_separate_writers_merge(self):
        merged = workflow_module._merge_or_reset({"a": 1}, {"b": 2})

        assert merged == {"a": 1, "b": 2}

    def test_an_empty_update_means_start_again(self):
        """`operator.ior` could not express this, and four nodes asked for it.

        `sprint_advance`, the re-plan, the blocked review and the run reset all
        hand on `specialist_outputs={}` to begin with a clean slate.
        `current |= {}` leaves the dictionary untouched, so every one of them
        carried the previous milestone's outputs forward - and
        `test_and_triage` builds the file list it hands the Test Engineer from
        exactly that dictionary.
        """
        assert workflow_module._merge_or_reset({"a": 1}, {}) == {}
        assert workflow_module._merge_or_reset({"a": 1}, None) == {}

    def test_it_survives_an_unset_channel(self):
        assert workflow_module._merge_or_reset(None, {"a": 1}) == {"a": 1}

    def test_a_second_sprint_does_not_inherit_the_first_s_outputs(
        self, agents: ScriptedAgents, tmp_path: Any
    ) -> None:
        """The behaviour the reducer exists for, through the graph.

        Two sprints, each delegating to a different role. If the reset does not
        take, the second sprint's state carries both - and the milestone review
        and the Test Engineer are both told the first sprint's files are part of
        this milestone's work.
        """
        from app.agents.scrum_master import SprintDefinition, SprintPlanOutput

        _script_through_architecture(agents, _approved_review())
        agents.script("scrum_master", [responds_with(SprintPlanOutput(sprints=[
            SprintDefinition(goal="Sprint 1: booking", user_value="Patients can book"),
            SprintDefinition(goal="Sprint 2: reminders", user_value="Patients are reminded"),
        ]))])
        agents.script("technical_lead", [
            responds_with(_milestone("backend")),
            responds_with(_milestone("ui_ux")),
        ])
        agents.script("specialist_backend", [responds_with(_specialist())])
        agents.script("specialist_ui_ux", [responds_with(_specialist())])
        agents.script("specialist_testing", [responds_with(_specialist())] * 4)
        agents.script("milestone_reviewer", [responds_with(_milestone_review())] * 2)
        agents.script("security_reviewer", [responds_with(_security_review())] * 2)

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-two-sprints")

        if state["stage"] == "failed":
            print("ERROR:", state.get("error"))
        assert state["stage"] == "complete"
        assert set(state["specialist_outputs"]) == {"specialist_ui_ux_0"}, (
            "the second sprint's outputs are its own"
        )
