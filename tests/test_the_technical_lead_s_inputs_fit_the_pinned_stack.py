"""What the harness hands the technical lead and its specialists fits the stack the run pinned.

Per-role audit: the environment contract named the base allowlist on every run, so a C# run was told `cargo` and
`go` and never `dotnet`; the harness's own testing work order joined the pack's unit command with spaces, so the
argument `junit;LogFilePath=...` read as a shell `;` and the harness's own readiness check sent the plan back; and
fast delivery counted the scaffold's unchanged stub as a built file, so a two-file service was "half built" before
anything ran and the lead was called for the first plan.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from app.agents.environment_contract import build_environment_contract_middleware
from app.agents.principal_architect import TechnicalSpecificationOutput
from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
from app.analysis.work_orders import readiness_problems, with_a_testing_work_order
from app.graph.planned_work import work_orders_from_the_specification
from app.stacks import contract, pack_named
from app.tools.sandbox import pin_project_stack

PROJECT = "notes-api"

SPEC = TechnicalSpecificationOutput(
    product_scope="Notes.",
    file_plan=[
        f"{PROJECT}/src/App/Program.cs - the routes and the store",
        f"{PROJECT}/tests/UnitTests/NoteApiTests.cs - unit tests for the routes",
    ],
    function_contracts=["Program.cs: POST /notes stores a note"],
    test_cases=["NoteApiTests.cs: given no notes, when one is posted, then it is listed"],
)


class _Request:
    def __init__(self, system: str):
        from langchain_core.messages import SystemMessage

        self.messages = [{"role": "user", "content": "plan it"}]
        self.system_message = SystemMessage(content=system)
        self.captured: dict = {}

    def override(self, **changes):
        self.captured.update(changes)
        return self


def _the_commands_a_call_is_told(repo_root: Path) -> tuple[str, list[str]]:
    request = _Request("You are the lead.")
    build_environment_contract_middleware(str(repo_root)).wrap_model_call(request, lambda r: r)
    system = request.captured["system_message"].content
    listed = re.search(r"Available commands: ([^\n]*)\.\n", system).group(1)
    return system, [command.strip() for command in listed.split(",")]


def _a_scaffolded_workspace(root: Path, pack_name: str = "csharp-aspnet-api") -> Path:
    pack = pack_named(pack_name)
    for relative, content in pack.render(PROJECT, "Notes", "notes_api").items():
        target = root / PROJECT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    contract.write(root, pack, PROJECT, "Notes", "notes_api")
    pin_project_stack(root, pack.language)
    (root / ".project-directory").write_text(PROJECT, encoding="utf-8")
    return root


def test_a_run_pinned_to_a_language_outside_the_base_list_is_told_its_own_toolchain(tmp_path):
    pin_project_stack(tmp_path, "C#")

    _, told = _the_commands_a_call_is_told(tmp_path)

    assert "dotnet" in told
    assert "cargo" not in told and "go" not in told


def test_a_pinned_run_s_contract_names_no_product_word(tmp_path):
    pin_project_stack(tmp_path, "C#")

    system, _ = _the_commands_a_call_is_told(tmp_path)

    for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
        assert not re.search(rf"\b{re.escape(word)}\b", system, re.IGNORECASE), word


def test_two_calls_of_one_run_carry_the_same_contract_bytes(tmp_path):
    """The contract sits in the cached prefix: a byte that moves between calls re-prefills the whole prompt."""
    pin_project_stack(tmp_path, "C#")

    first, _ = _the_commands_a_call_is_told(tmp_path)
    second, _ = _the_commands_a_call_is_told(tmp_path)

    assert first == second


def test_the_harness_s_testing_work_order_keeps_an_argument_holding_a_semicolon_whole(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKFLOW_WORK_ORDER_READINESS", "on")
    root = _a_scaffolded_workspace(tmp_path)
    plan = MilestonePlanOutput(selected_sprint_goal="Notes", delegated_tasks=[SpecialistTask(
        specialist_role="backend", title="Routes", task_description="Write the routes.",
        files=[f"{PROJECT}/src/App/Program.cs"], test_cases=["given no notes, when one is posted, then it is listed"],
        acceptance_criteria=["A posted note is listed"],
    )])

    plan, added = with_a_testing_work_order(plan, str(root))

    testing = plan.delegated_tasks[-1]
    assert added and testing.specialist_role == "testing"
    argv = shlex.split(testing.verification[0])
    assert argv[:3] == ["dotnet", "test", "tests/UnitTests"]
    assert argv[-1].startswith("junit;LogFilePath=") and "MethodFormat=Class" in argv[-1]
    assert not [p for p in readiness_problems(plan, str(root)) if "verification" in p]


def test_a_model_written_command_joined_by_a_real_semicolon_is_still_sent_back(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKFLOW_WORK_ORDER_READINESS", "on")
    root = _a_scaffolded_workspace(tmp_path)
    plan = MilestonePlanOutput(selected_sprint_goal="Notes", delegated_tasks=[SpecialistTask(
        specialist_role="testing", title="Tests", task_description="Write the tests.",
        files=[f"{PROJECT}/tests/UnitTests/NoteApiTests.cs"], test_cases=["given no notes, then none are listed"],
        acceptance_criteria=["The tests run"], verification=["dotnet test tests/UnitTests ; echo done"],
    )])

    problems = [p for p in readiness_problems(plan, str(root)) if "verification" in p]

    assert problems and "shell" in problems[0]


def test_a_scaffold_s_unchanged_stub_does_not_count_as_a_built_file(tmp_path):
    root = _a_scaffolded_workspace(tmp_path)

    plan = work_orders_from_the_specification(SPEC, "Notes", ["AC-1: a note is stored"], ["dotnet test"], str(root))

    assert plan is not None
    assert f"{PROJECT}/src/App/Program.cs" in [f for task in plan.delegated_tasks for f in task.files]


def test_a_stub_the_team_has_changed_counts_as_built(tmp_path):
    root = _a_scaffolded_workspace(tmp_path)
    program = root / PROJECT / "src/App/Program.cs"
    program.write_text(program.read_text(encoding="utf-8") + "\n// the routes\n", encoding="utf-8")

    assert work_orders_from_the_specification(SPEC, "Notes", ["AC-1"], ["dotnet test"], str(root)) is None


def test_fast_delivery_plans_a_freshly_scaffolded_service_with_no_planning_call(tmp_path, monkeypatch):
    """The whole path: the stub is not counted as built, and the pack's own unit command passes readiness."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    from langgraph.checkpoint.memory import MemorySaver

    from app import delivery
    from app.agents.scrum_master import SprintDefinition, SprintPlanOutput
    from app.graph import workflow

    monkeypatch.setenv("WORKFLOW_WORK_ORDER_READINESS", "on")
    monkeypatch.setattr(delivery, "fast", lambda environment=None: True)
    root = _a_scaffolded_workspace(tmp_path)
    sprint = SprintDefinition(goal="Notes", user_value="notes", in_scope=["Build Program.cs"],
                              out_of_scope=[], acceptance_criteria=["works"], dependencies=[])
    state = {
        "repository": SimpleNamespace(root_path=str(root)),
        "sprint_plan": SprintPlanOutput(sprints=[sprint], success_measure_coverage=[]),
        "technical_specification": SPEC,
        "current_sprint_index": 0,
    }
    lead_s = MilestonePlanOutput(selected_sprint_goal="Notes", delegated_tasks=[])
    with patch("app.graph.workflow.create_technical_lead_agent", return_value=MagicMock()), \
         patch("app.graph.acceptance_nodes.sprint_already_done", return_value=""), \
         patch("app.server.agent_stream.AgentActivityStream", MagicMock()), \
         patch("app.graph.workflow._run_gated_agent", return_value={"milestone_plan": lead_s}) as asked:
        graph = workflow.build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(root))
        update = graph.nodes["technical_lead"].bound.invoke(
            state, {"configurable": {"thread_id": "t", "app_run_id": "run-lead"}})

    assert not asked.called
    assert f"{PROJECT}/src/App/Program.cs" in [f for task in update["milestone_plan"].delegated_tasks for f in task.files]
