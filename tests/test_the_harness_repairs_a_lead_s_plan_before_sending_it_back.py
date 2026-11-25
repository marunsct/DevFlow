"""What is mechanical in a lead's plan the harness repairs itself; what needs judgement goes back as one more turn of
the lead's own conversation (plan PA.6).

Measured on a medium run: the lead made 12 plans in 4 visits. The reasons sent back were "No `testing` work order"
on a custom setup with no recorded contract, and "there is no shell here, so `&&` ... do nothing"; one plan had an
empty title. Each send-back was a fresh conversation of about 147,000 characters.
"""
from __future__ import annotations

import json
import re

from langchain_core.messages import AIMessage

from app.agents.technical_lead import SpecialistTask
from app.analysis.work_orders import readiness_problems, with_a_testing_work_order
from workflow_nodes import a_lead, a_plan, a_scripted_model

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _backend(**fields):
    return SpecialistTask(**{
        "specialist_role": "backend", "title": "Routes", "task_description": "Serve the notes over HTTP.",
        "files": ["notes-api/app/routes.py"], "interfaces": ["GET /notes -> 200 [Note]"],
        "test_cases": ["given no notes, GET /notes answers []"], **fields,
    })


def _a_custom_setup_declared_but_not_recorded(tmp_path):
    """A workspace whose setup stage wrote `stack-setup.json` and no contract was recorded for it."""
    (tmp_path / ".project-directory").write_text("notes-api\n")
    (tmp_path / "notes-api").mkdir()
    (tmp_path / "notes-api" / "stack-setup.json").write_text(json.dumps({
        "kind": "http_api", "unit_test": ["python", "-m", "pytest", "tests/unit"], "unit_dir": "tests/unit",
        "unit_pattern": "test_*.py", "acceptance_test": ["python", "-m", "pytest", "acceptance"],
        "acceptance_dir": "acceptance", "acceptance_pattern": "test_*.py",
    }))
    return tmp_path


def test_a_custom_setup_s_declared_unit_folder_names_the_testing_work_order(tmp_path):
    root = _a_custom_setup_declared_but_not_recorded(tmp_path)

    plan, added = with_a_testing_work_order(a_plan(_backend()), str(root))

    assert added
    testing = plan.delegated_tasks[-1]
    assert testing.specialist_role == "testing"
    assert testing.files == ["notes-api/tests/unit/test_routes.py"]
    assert testing.verification == ["python -m pytest tests/unit"]
    assert not any("testing` work order" in problem for problem in readiness_problems(plan, str(root)))


def _what_the_readiness_check_saw(tmp_path, plan):
    _, asked = a_lead(tmp_path, plan)
    return asked["readiness"][0]["plan"]


def test_a_verification_line_joined_by_a_shell_operator_reaches_the_check_as_separate_commands(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKFLOW_WORK_ORDER_READINESS", "on")
    plan = a_plan(_backend(verification=["python -m pytest -q && python -m mypy app", "cd app && python -m pytest"]))

    seen = _what_the_readiness_check_saw(tmp_path, plan)

    backend = next(order for order in seen.delegated_tasks if order.specialist_role == "backend")
    assert backend.verification == ["python -m pytest -q", "python -m mypy app", "python -m pytest"]
    assert "`python -m pytest` runs in `app/`" in backend.task_description
    assert not any("no shell" in problem for problem in readiness_problems(seen, str(tmp_path)))


def test_a_cd_that_leaves_the_project_is_left_for_the_check_to_report(tmp_path):
    plan = a_plan(_backend(verification=["cd /elsewhere && python -m pytest"]))

    seen = _what_the_readiness_check_saw(tmp_path, plan)

    backend = next(order for order in seen.delegated_tasks if order.specialist_role == "backend")
    assert backend.verification == ["cd /elsewhere && python -m pytest"]


def test_an_empty_title_is_filled_from_the_description_s_first_line(tmp_path):
    plan = a_plan(_backend(title="", task_description="Serve the notes over HTTP.\nThen the rest."))

    seen = _what_the_readiness_check_saw(tmp_path, plan)

    backend = next(order for order in seen.delegated_tasks if order.specialist_role == "backend")
    assert backend.title == "Serve the notes over HTTP."


def _a_plan_call(plan):
    return AIMessage(content="", tool_calls=[{"name": "MilestonePlanOutput", "args": plan.model_dump(),
                                              "id": f"plan-{len(plan.delegated_tasks)}", "type": "tool_call"}])


def test_what_still_needs_judgement_goes_back_as_one_more_turn_of_the_same_conversation(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKFLOW_WORK_ORDER_READINESS", "on")
    from app.agents import technical_lead

    unready = a_plan(_backend(files=[]))
    ready = a_plan(_backend(), SpecialistTask(
        specialist_role="testing", title="Tests", task_description="Write the tests.",
        files=["notes-api/tests/test_routes.py"], test_cases=["given no notes, GET /notes answers []"]))
    model = a_scripted_model(_a_plan_call(unready), _a_plan_call(ready))

    def built(**kwargs):
        return technical_lead.create_technical_lead_agent(**{**kwargs, "model": model})

    def gated(state, config, *, agent, initial_request, output_key, **kwargs):
        result = agent.invoke(initial_request, {"configurable": {"thread_id": "t:technical_lead:1"},
                                                "recursion_limit": 20})
        return {output_key: result["structured_response"], "inner_thread_ids": ["t:technical_lead:1"],
                "stage": "specialist_dispatch"}

    update, _ = a_lead(tmp_path, unready, patches={
        "app.graph.workflow.create_technical_lead_agent": built,
        "app.graph.workflow._run_gated_agent": gated,
        "app.analysis.work_orders.readiness_problems": readiness_problems,
    })

    assert update["stage"] == "specialist_dispatch"
    assert [order.specialist_role for order in update["milestone_plan"].delegated_tasks] == ["backend", "testing"]
    second = model.requests[-1]["messages"]
    said = [str(message.content) for message in second if message.type == "human"]
    # One conversation: the first request once, the lead's own first plan, then what is wrong with it.
    assert sum("Plan the sprint." in text for text in said) == 1
    assert any(message.type == "ai" and message.tool_calls for message in second)
    assert any("names no `files`" in text for text in said)


def test_the_turn_s_own_words_use_none_of_the_banned_words():
    from app.graph.plan_follow_up import _WHOLE_PLAN_AGAIN

    assert "Return the whole plan again" in _WHOLE_PLAN_AGAIN
    assert not BANNED.search(_WHOLE_PLAN_AGAIN)
