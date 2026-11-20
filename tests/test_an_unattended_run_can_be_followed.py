"""An unattended run a person can follow from its page (plan WS.2).

The stream sent a tool's result as `str(ToolMessage)`: a command's output JSON-escaped inside a repr, with its exit
status a string to dig for and nothing tying the result to its call. The plan panel needs the current sprint's work
orders as done, working or open, which no route served.
"""
from __future__ import annotations

from types import SimpleNamespace

from langchain_core.tools import tool

from app.server.agent_stream import AgentActivityStream


class Recording(AgentActivityStream):
    def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
        super().__init__(*args, **kwargs)
        self.published: list[tuple[str, str, dict]] = []

    def _publish(self, event_type, message, metadata=None):  # noqa: ANN001
        self.published.append((event_type, message, metadata or {}))


@tool
def run_terminal_command(command: list[str]) -> dict:
    """Run one command."""
    return {"stdout": "2 passed\n1 failed", "stderr": "AssertionError: expected 3", "returncode": "1"}


@tool
def write_artifact(relative_path: str, content: str) -> dict:
    """Write one file."""
    return {"path": relative_path, "bytes": len(content)}


def _invoke(a_tool, args):
    stream = Recording("run-1", "specialist_backend_0")
    a_tool.invoke({"type": "tool_call", "name": a_tool.name, "args": args, "id": "call-1"},
                  config={"callbacks": [stream]})
    return stream.published


def test_a_command_s_result_is_its_output_with_its_exit_status_beside_it():
    (_, _, started), (kind, message, facts) = _invoke(run_terminal_command, {"command": ["npm", "test"]})

    assert kind == "tool_result"
    assert facts["exit_code"] == 1 and facts["tool"] == "run_terminal_command"
    assert message == "2 passed\n1 failed\n--- stderr ---\nAssertionError: expected 3"
    # The result and its call share one id, so the page puts each result under its own call.
    assert facts["call_id"] and facts["call_id"] == started["call_id"]


def test_any_other_result_is_its_own_text_not_the_message_s_repr():
    (_, _, _), (_, message, facts) = _invoke(write_artifact, {"relative_path": "src/app.py", "content": "x"})

    assert message == '{"path": "src/app.py", "bytes": 1}'
    assert "exit_code" not in facts


def test_a_command_s_output_is_still_clipped_and_says_so():
    from app.server.agent_stream import MAX_TEXT

    stream = Recording("run-1", "s")
    stream.on_tool_end(SimpleNamespace(content='{"stdout": "%s", "returncode": "0"}' % ("x" * 5000), name="execute"))
    _, message, facts = stream.published[-1]

    assert facts["exit_code"] == 0
    assert len(message) < MAX_TEXT + 100 and message.endswith("[+3,000 more characters]")


# -- the plan panel's route ------------------------------------------------------------------------------------------


def _state():
    task = lambda role, title, files: SimpleNamespace(specialist_role=role, title=title, task_description="", files=files)  # noqa: E731
    return {
        "sprint_plan": SimpleNamespace(sprints=[
            SimpleNamespace(goal="Sign-in", in_scope=["sign in"]),
            SimpleNamespace(goal="Export", in_scope=["export"]),
        ]),
        "current_sprint_index": 1,
        "sprint_attempts": [
            {"sprint_index": 0, "number": 1, "status": "Completed", "rounds": 1, "features": [], "defects": []},
            {"sprint_index": 1, "number": 1, "status": "Failed", "rounds": 3, "features": [], "defects": []},
        ],
        "test_round": 2,
        "milestone_plan": SimpleNamespace(delegated_tasks=[
            task("backend", "The export route", ["src/export.py"]),
            task("frontend", "The export view", ["web/export.tsx"]),
            task("testing", "The export tests", []),
        ]),
        "specialist_outputs": {"specialist_backend_0": SimpleNamespace(blockers=[], changed_files=["src/export.py"])},
        "remediation": SimpleNamespace(defects=[
            SimpleNamespace(status="open", description="CSV header", owner="backend"),
            SimpleNamespace(status="fixed", description="Empty file", owner="backend"),
        ]),
    }


def _client(monkeypatch, state, status="running", stages=()):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.server import runs
    from app.server.auth import get_current_active_user
    from app.server.events import RunEvent

    run = SimpleNamespace(run_id="run-1", tenant_id="t", status=status, current_stage="specialist_dispatch",
                          graph_state=lambda checkpointer=None: state)
    runner = SimpleNamespace(run_store=SimpleNamespace(load=lambda run_id: run if run_id == "run-1" else None),
                             checkpointer=None)
    history = [RunEvent(run_id="run-1", sequence=n, stage=stage, event_type="stage_change", message="")
               for n, stage in enumerate(stages, 1)]

    async def get_history(run_id):  # noqa: ARG001
        return history

    app = FastAPI()
    app.include_router(runs.create_runs_router(runner, SimpleNamespace(get_history=get_history), "/tmp", "/tmp"))
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(
        username="owner", role="operator", tenant_id="t")
    return TestClient(app)


def test_the_plan_says_which_work_orders_are_done_working_and_open_with_the_attempt_round_and_open_defects(monkeypatch):
    # The frontend's stage started in an earlier sprint's plan too: only a start since the newest plan counts.
    client = _client(monkeypatch, _state(), stages=[
        "specialist_testing_2", "technical_lead", "specialist_backend_0", "specialist_frontend_1"])

    plan = client.get("/api/runs/run-1/plan").json()

    assert [(w["title"], w["state"]) for w in plan["work_orders"]] == [
        ("The export route", "done"), ("The export view", "working"), ("The export tests", "open")]
    assert plan["work_orders"][0]["files"] == ["src/export.py"]
    assert (plan["sprint"], plan["planned_total"], plan["goal"]) == (2, 2, "Export")
    assert (plan["attempt"], plan["round"], plan["open_defects"]) == (2, 2, 1)


def test_a_finished_run_has_nothing_being_worked_on(monkeypatch):
    client = _client(monkeypatch, _state(), status="failed", stages=["technical_lead", "specialist_frontend_1"])

    plan = client.get("/api/runs/run-1/plan").json()

    assert [w["state"] for w in plan["work_orders"]] == ["done", "open", "open"]
    assert (plan["attempt"], plan["round"]) == (1, 3)


def test_before_sprints_are_planned_the_plan_is_empty(monkeypatch):
    plan = _client(monkeypatch, {}).get("/api/runs/run-1/plan").json()

    assert plan["sprint"] is None and plan["work_orders"] == [] and plan["attempt"] == 0
