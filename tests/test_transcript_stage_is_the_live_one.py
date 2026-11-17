"""A tool call is filed under the stage that made it, not the agent's phase.

One role agent is built and reused for many stages: a single `implementation`
agent serves every specialist and every test round. Middleware is constructed
with the agent, so a stage name captured there is the phase. The stage that is
actually running is only knowable at invoke time, from the config.

Measured across runs 60-66 before this: 2,416 of 2,594 tool records (93%) said
`implementation` or `intake` while the model call that asked for them named the
specialist. Every "which stage spent these calls" question read wrong.
"""

from unittest.mock import patch

from app.observability.transcript import _stage_from_config
from app.tracing import APP_STAGE_KEY


def _with_config(configurable):
    return patch("langgraph.config.get_config", return_value={"configurable": configurable})


def test_the_live_stage_wins_over_the_one_the_agent_was_built_with():
    with _with_config({APP_STAGE_KEY: "specialist_testing_1"}):
        assert _stage_from_config("implementation") == "specialist_testing_1"


def test_the_construction_time_name_is_used_when_the_invoke_carried_none():
    with _with_config({}):
        assert _stage_from_config("implementation") == "implementation"


def test_an_empty_stage_in_the_config_does_not_erase_the_fallback():
    with _with_config({APP_STAGE_KEY: ""}):
        assert _stage_from_config("implementation") == "implementation"


def test_no_config_at_all_is_not_an_error():
    with patch("langgraph.config.get_config", side_effect=RuntimeError("outside a run")):
        assert _stage_from_config("implementation") == "implementation"


def test_the_inner_agent_config_carries_the_stage():
    from app.graph.workflow import _inner_agent_config

    config = _inner_agent_config("t:1", "run-1", [], stage="specialist_ui_ux_0")
    assert config["configurable"][APP_STAGE_KEY] == "specialist_ui_ux_0"


def test_the_inner_agent_config_omits_the_key_when_no_stage_is_given():
    from app.graph.workflow import _inner_agent_config

    assert APP_STAGE_KEY not in _inner_agent_config("t:1", "run-1", [])["configurable"]


class _AnswersOnTheReminder:
    """No answer to the request, an answer to the reminder: both inner invokes in one stage."""

    def __init__(self):
        self.configs = []

    def invoke(self, request, config=None):  # noqa: ARG002
        self.configs.append(config)
        return {"messages": [], "structured_response": "answer" if len(self.configs) > 1 else None}


def _a_stage_runs(tmp_path, agent, **state):
    from types import SimpleNamespace

    from app.graph.workflow import _run_gated_agent

    return _run_gated_agent(
        {"stage": "specialist_ui_ux_0", "repository": SimpleNamespace(root_path=str(tmp_path)), **state},
        {"configurable": {"thread_id": "outer"}},
        stage_name="specialist_ui_ux_0", agent=agent, initial_request={"messages": [{"role": "user", "content": "build"}]},
        output_key="out", next_stage="next",
    )


def test_every_role_agent_invoke_in_the_workflow_names_its_stage(tmp_path, monkeypatch):
    """The bug was a missing argument at a call site, so guard the call sites.

    `_inner_agent_config` has three callers and `resume_with_decision` one:
    the stage's own invoke, the reminder for its answer, and the resume after
    an approval. A fourth written without the stage is how the transcript came
    to record a run's calls under the wrong names in the first place.
    """
    agent = _AnswersOnTheReminder()
    _a_stage_runs(tmp_path, agent)
    assert len(agent.configs) == 2
    assert [config["configurable"][APP_STAGE_KEY] for config in agent.configs] == ["specialist_ui_ux_0"] * 2

    resumed = []
    monkeypatch.setattr(
        "app.graph.workflow.resume_with_decision",
        lambda *args, **kwargs: resumed.append(kwargs) or {"messages": [], "structured_response": "answer"},
    )
    _a_stage_runs(tmp_path, _AnswersOnTheReminder(),
                  pending_decision={"type": "approve"}, pending_inner_thread_id="outer:specialist_ui_ux_0:1")
    assert resumed[0]["stage"] == "specialist_ui_ux_0"
