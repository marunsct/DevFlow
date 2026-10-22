"""A model provider out of quota parks the run for a person; it does not fail it.

One run's frontier provider answered every call with 403 "Free quota exhausted"
once the account's free tier was spent. The stage was tried again and again,
each attempt refused alike, and the run was recorded as failed - though its
work was sound and it went on from the same checkpoint once a model with quota
was set. A refusal for want of quota or credit is now not retried, and the run
waits as it does at its spending ceiling (`waiting_for_budget`), with a message
saying what to do.
"""

from __future__ import annotations

import httpx
import openai
import pytest

from app.models.quota import out_of_quota

_BODY = {
    "error": {
        "message": 'Free quota exhausted. To continue accessing the model on a paid basis, '
                   'please add funds or disable the "use free tier only" mode.',
        "type": "insufficient_quota",
    }
}


def _status_error(cls: type[openai.APIStatusError], status: int, body: dict) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://models.example/v1/chat/completions")
    response = httpx.Response(status, request=request, json=body)
    return cls(f"Error code: {status} - {body}", response=response, body=body)


def quota_refusal() -> openai.APIStatusError:
    return _status_error(openai.PermissionDeniedError, 403, _BODY)


def test_a_refusal_for_want_of_quota_is_told_apart_from_a_rate_limit():
    assert out_of_quota(quota_refusal())
    assert out_of_quota(_status_error(openai.RateLimitError, 429, {"error": {
        "message": "You exceeded your current quota, please check your plan.", "code": "insufficient_quota",
    }}))
    assert out_of_quota(_status_error(openai.APIStatusError, 402, {"error": {"message": "pay"}}))
    assert not out_of_quota(_status_error(openai.RateLimitError, 429, {"error": {
        "message": "Rate limit reached for requests per minute. Try again in 2s.",
    }}))
    assert not out_of_quota(_status_error(openai.PermissionDeniedError, 403, {"error": {
        "message": "This model is not available in your region.",
    }}))
    assert not out_of_quota(ValueError("no structured response"))


def test_a_refusal_wrapped_by_another_error_is_still_seen():
    try:
        try:
            raise quota_refusal()
        except openai.APIStatusError as inner:
            raise RuntimeError("the stage could not finish") from inner
    except RuntimeError as outer:
        assert out_of_quota(outer)


def test_a_stage_refused_for_want_of_quota_is_not_tried_again(agents, tmp_path):  # noqa: F811
    from test_graph_routing import _document, _graph, _repository

    calls = []

    def refuse(payload, config=None):  # noqa: ARG001
        calls.append(payload)
        raise quota_refusal()

    agents.agent("product_manager")  # the role exists
    import test_graph_routing

    original = test_graph_routing._FakeAgent.invoke

    def invoke(self, payload, config=None):
        if self.role == "product_manager":
            return refuse(payload, config)
        return original(self, payload, config)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(test_graph_routing._FakeAgent, "invoke", invoke)
        from app.graph.workflow import start_workflow

        with pytest.raises(openai.PermissionDeniedError):
            start_workflow(_graph(), _document(), _repository(tmp_path), "run-out-of-quota")

    assert len(calls) == 1


from test_graph_routing import agents  # noqa: E402,F401 - fixture


@pytest.fixture
def runner(run_store, redis_container, monkeypatch):
    from app.server.events import EventBus
    from app.server.redis_client import reset_clients
    from app.server.runner import WorkflowRunner

    reset_clients()
    monkeypatch.setenv("CHECKPOINTER_TYPE", "memory")
    return WorkflowRunner(EventBus(), run_store=run_store)


def _register(runner, run_id: str):
    record = runner.register_run(
        run_id=run_id, thread_id=f"thread-{run_id}", document_names=["brief.md"],
        document_paths=["/tmp/brief.md"], owner="alice", tenant_id="acme",
    )
    record.status = "running"
    runner.run_store.save(record)
    return record


async def test_the_run_waits_for_a_person_instead_of_failing(runner, monkeypatch):
    from app.server import runner as runner_module

    def refused(*args, **kwargs):
        raise quota_refusal()

    monkeypatch.setattr(runner_module, "build_workflow_graph", lambda **kwargs: object())
    monkeypatch.setattr(runner_module, "start_workflow", refused)
    record = _register(runner, "run-quota")

    await runner._run_loop(record, document=None, repository=None)

    stored = runner.run_store.load("run-quota")
    assert stored.status == runner_module.BUDGET_PAUSE_STATUS
    assert stored.status in runner_module.RESUMABLE_STATUSES
    assert stored.error.startswith("The model provider refused the call because the account's quota")
    assert "resume" in stored.error


async def test_any_other_error_still_fails_the_run(runner, monkeypatch):
    from app.server import runner as runner_module

    def broken(*args, **kwargs):
        raise _status_error(openai.PermissionDeniedError, 403, {"error": {"message": "region"}})

    monkeypatch.setattr(runner_module, "build_workflow_graph", lambda **kwargs: object())
    monkeypatch.setattr(runner_module, "start_workflow", broken)
    record = _register(runner, "run-other")

    await runner._run_loop(record, document=None, repository=None)

    assert runner.run_store.load("run-other").status == "failed"


def test_the_guidance_names_no_unit_of_work():
    import re

    from app.server.runner import _explain_failure

    message = _explain_failure(quota_refusal())
    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", message, re.IGNORECASE)
