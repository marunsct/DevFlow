"""Fast delivery: the same stages and records, each doing less (`app.delivery`).

Measured on one run of a five-route notes service: 13 hours, 1,081 model
calls one after another, 2.8 million output tokens (half reasoning), four
sprints for eighteen criteria, about forty tool calls per work order, and
5,058 lines of tests for 549 of product.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app import delivery
from app.agents.principal_architect import TechnicalSpecificationOutput
from app.agents.scrum_master import SprintDefinition, SprintPlanOutput, with_capped_sprint_count
from app.graph import drafting

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


# --- the setting ---------------------------------------------------------------

def test_the_mode_is_read_from_the_setting_and_defaults_to_thorough():
    assert delivery.mode({"DELIVERY_MODE": "fast"}) == "fast"
    assert delivery.mode({"DELIVERY_MODE": " FAST "}) == "fast"
    assert delivery.mode({}) == "thorough"
    assert delivery.mode({"DELIVERY_MODE": "quick"}) == "thorough"
    assert delivery.fast({"DELIVERY_MODE": "fast"}) and not delivery.fast({})


def test_the_setting_is_saved_and_the_deployment_chooses_fast():
    from pathlib import Path

    from app.server.runtime_settings import SETTABLE_KEYS

    assert SETTABLE_KEYS["delivery_mode"] == "DELIVERY_MODE"
    assert "DELIVERY_MODE: ${DELIVERY_MODE:-fast}" in Path("docker-compose.yml").read_text()


# --- 1. one sprint for a small product ------------------------------------------

def _sprint(n: int) -> SprintDefinition:
    return SprintDefinition(
        goal=f"Goal {n}", user_value="v", in_scope=[f"part {n}"], criteria=[f"AC-{n}"],
        out_of_scope=[f"Delete (Sprint {n + 1})", "Authentication - never in this release"],
    )


def test_a_small_product_is_one_sprint_and_keeps_what_it_now_owns():
    plan = SprintPlanOutput(sprints=[_sprint(1), _sprint(2), _sprint(3), _sprint(4)])

    capped, folded = with_capped_sprint_count(plan, 18, fast=True)

    (only,) = capped.sprints
    assert len(folded) == 3
    assert only.criteria == ["AC-1", "AC-2", "AC-3", "AC-4"]
    assert only.out_of_scope == ["Authentication - never in this release"], "nothing it now builds is out of scope"
    assert len(with_capped_sprint_count(plan, 18)[0].sprints) == 4, "thorough is unchanged"


# --- 5. building without reasoning ----------------------------------------------

def test_a_build_model_is_copied_with_reasoning_off(monkeypatch):
    from app.agents import thinking
    from app.models import CompatibleChatOpenAI

    model = CompatibleChatOpenAI(model="build", base_url="http://localhost:8888/v1", api_key="k")
    monkeypatch.setattr(thinking, "answering_without_reasoning", lambda m: {"extra_body": {"reasoning_effort": "none"}})

    quiet = thinking.without_reasoning(model)

    assert quiet is not model and quiet.extra_body == {"reasoning_effort": "none"}
    assert model.extra_body is None, "the configured model is left as it is"
    monkeypatch.setattr(thinking, "answering_without_reasoning", lambda m: {})
    assert thinking.without_reasoning(model) is model


# --- 2 and 4. drafting from the specification ------------------------------------

SPEC = TechnicalSpecificationOutput(
    product_scope="Notes.",
    file_plan=[
        "notes/src/store.ts - keeps notes; exports createStore(dir): Store",
        "notes/tests/unit/store.test.ts - unit tests for the store",
    ],
    function_contracts=["notes/src/store.ts createStore(dir: string): Store - loads notes.json"],
    library_usage=["node:fs - import { readFileSync } from 'node:fs'"],
)


class _Model:
    def __init__(self, replies: dict[str, str]):
        self.replies, self.asked = replies, []

    def invoke(self, messages):
        text = messages[-1].content
        self.asked.append(text)
        path = re.search(r"Write the file `([^`]+)`", text).group(1)
        return SimpleNamespace(content=self.replies.get(path, ""))


def _order(role: str, *files: str):
    from app.agents.technical_lead import SpecialistTask

    return SpecialistTask(specialist_role=role, task_description=f"build the {role} part",
                          acceptance_criteria=["works"], files=list(files))


def test_each_file_is_written_in_one_call_from_its_specification(tmp_path):
    model = _Model({"notes/src/store.ts": "Here it is:\n```ts\nexport function createStore() {}\n```\n"})
    written = {}

    drafted = drafting.draft_work_orders(
        [_order("backend", "notes/src/store.ts")], SPEC, None, str(tmp_path), model,
        write=lambda root, path, content: written.setdefault(path, content),
    )

    assert written == {"notes/src/store.ts": "export function createStore() {}\n"}
    assert drafted[0].changed_files == ["notes/src/store.ts"]
    request = model.asked[0]
    assert "createStore(dir: string): Store - loads notes.json" in request
    assert "import { readFileSync } from 'node:fs'" in request
    assert not BANNED.search(request.split("--- The work order it belongs to ---")[0])
    assert not BANNED.search(request.split("\n\n")[-1])


def test_a_work_order_with_a_file_not_drafted_is_left_to_the_agent_loop(tmp_path):
    model = _Model({"notes/src/store.ts": "```ts\nexport const a = 1\n```"})

    def write(root, path, content):
        if path.endswith("page.ts"):
            raise ValueError("TypeScript cannot parse this file")

    drafted = drafting.draft_work_orders(
        [_order("backend", "notes/src/store.ts"), _order("ui_ux", "notes/src/page.ts")],
        SPEC, None, str(tmp_path), model, write=write,
    )

    assert list(drafted) == [0]


def test_tests_are_the_ones_the_specification_plans():
    orders = [_order("testing", "notes/tests/unit/store.test.ts", "notes/tests/integration/launcher.test.ts")]

    kept, dropped = drafting.with_tests_the_specification_plans(orders, SPEC)

    assert kept[0].files == ["notes/tests/unit/store.test.ts"]
    assert dropped == ["notes/tests/integration/launcher.test.ts"]
    no_plan = TechnicalSpecificationOutput(product_scope="x")
    assert drafting.with_tests_the_specification_plans(orders, no_plan) == (orders, [])


def test_a_reply_s_file_is_its_longest_fenced_block():
    assert drafting.the_content_in("intro\n```\nshort\n```\nthen\n```ts\nlonger content\n```") == "longer content\n"
    assert drafting.the_content_in("plain text file") == "plain text file\n"
    assert drafting.the_content_in("") == ""


# --- the graph -------------------------------------------------------------------

from test_graph_routing import (  # noqa: E402,F401 - `agents` is a fixture
    _approved_review,
    _document,
    _graph,
    _milestone_review,
    _repository,
    _script_through_architecture,
    _security_review,
    _specialist,
    _sprint_plan,
    agents,
    responds_with,
)


@pytest.fixture
def fast(monkeypatch):
    from app.graph import workflow

    monkeypatch.setattr(delivery, "fast", lambda environment=None: True)
    monkeypatch.setattr(workflow, "_the_run_approves_its_own_writes", lambda run_id: True)
    monkeypatch.setattr("app.agents.specialists.what_the_files_already_prove", lambda *a, **k: [])


def _with_files(*files: str):
    from test_graph_routing import _milestone

    plan = _milestone("backend")
    task = plan.delegated_tasks[0].model_copy(update={"files": list(files)})
    return plan.model_copy(update={"delegated_tasks": [task]})


def test_a_drafted_work_order_runs_no_agent_and_the_run_completes(agents, fast, tmp_path, monkeypatch):
    monkeypatch.setattr(drafting, "_draft_one", lambda *a, **k: "export const ok = true\n")
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(_with_files("acme/src/app.ts"))])
    agents.script("specialist_testing", [responds_with(_specialist())])
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])
    from app.graph.workflow import start_workflow

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-fast")

    assert state["stage"] == "complete", state.get("error")
    assert not agents.requests.get("specialist_backend"), "the work order was drafted, not run"
    (written,) = tmp_path.rglob("app.ts")  # under the project directory, as any write is
    assert written.read_text() == "export const ok = true\n"


def test_a_run_that_puts_its_writes_to_a_person_is_not_drafted(agents, tmp_path, monkeypatch):
    from app.graph import workflow

    monkeypatch.setattr(delivery, "fast", lambda environment=None: True)
    monkeypatch.setattr("app.agents.specialists.what_the_files_already_prove", lambda *a, **k: [])
    drafts = []
    monkeypatch.setattr(drafting, "_draft_one", lambda *a, **k: drafts.append(a) or "x\n")
    assert workflow._the_run_approves_its_own_writes(None) is False
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(_with_files("acme/src/app.ts"))])
    agents.script("specialist_backend", [responds_with(_specialist())])
    agents.script("specialist_testing", [responds_with(_specialist())])
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])

    state = workflow.start_workflow(_graph(), _document(), _repository(tmp_path), "run-attended")

    assert state["stage"] == "complete", state.get("error")
    assert drafts == [] and len(agents.requests["specialist_backend"]) == 1


# --- 3. the harness runs the test round --------------------------------------------

def test_a_failing_unit_run_is_the_product_s_defect():
    from app.graph.workflow import _the_unit_tests_fail
    from test_graph_routing import _milestone

    defect = _the_unit_tests_fail(_milestone("testing", "backend"), "FAIL store.test.ts > keeps ids\n" * 3)

    assert defect.owner == "backend"
    assert "FAIL store.test.ts > keeps ids" in defect.description


def test_a_fix_reasons_as_configured_and_a_build_does_not():
    """One run's fixes without reasoning broke 62 passing tests in one fix and
    reported edits they never made."""
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)
    chooser = source[source.index("def _the_build_model("):source.index("def _the_model_for_this_attempt(")]
    assert "quiet = model if reasons else building_model" in chooser
    assert source.count("failed_fix_tries(cycle, defect_index), reasons=True)") == 1
    assert source.count("failed_fix_tries(cycle, index), reasons=True)") == 1
    assert "_the_build_model(state, stage_name)," in source, "a work order still builds without reasoning"


def test_a_draft_the_compiler_reports_an_error_in_is_drafted_again_with_it(tmp_path):
    """One run's drafts declared a variable twice; a test round found it half an hour later."""
    model = _Model({"notes/src/store.ts": "```ts\nexport const a = 1;\nexport const a = 2;\n```"})
    written, reported = {}, [["- In `notes/src/store.ts` line 2: Cannot redeclare block-scoped variable 'a'."], []]

    def write(root, path, content):
        written[path] = content
        model.replies[path] = "```ts\nexport const a = 1;\n```"

    drafting.draft_work_orders(
        [_order("backend", "notes/src/store.ts")], SPEC, None, str(tmp_path), model,
        write=write, diagnose=lambda files: reported.pop(0),
    )

    assert written["notes/src/store.ts"] == "export const a = 1;\n"
    assert "Cannot redeclare block-scoped variable 'a'" in model.asked[1]


def test_a_draft_refused_for_its_errors_is_drafted_once_more_with_them(tmp_path):
    model = _Model({"notes/src/store.ts": "```ts\nexport const a = 1;\n```"})
    attempts = []

    def write(root, path, content):
        attempts.append(content)
        if len(attempts) == 1:
            raise ValueError("Refusing to write 'notes/src/store.ts': it would add errors the language service "
                             "is sure of - line 2: Cannot redeclare block-scoped variable 'a'.")

    drafted = drafting.draft_work_orders([_order("backend", "notes/src/store.ts")], SPEC, None, str(tmp_path), model, write=write)

    assert list(drafted) == [0] and len(attempts) == 2
    assert "Cannot redeclare block-scoped variable 'a'" in model.asked[1]


def test_the_worker_runs_a_run_in_its_own_delivery_mode():
    from pathlib import Path

    source = Path("src/app/server/tasks.py").read_text()
    assert 'with delivery.for_the_run(getattr(record, "delivery_mode", "")):' in source
    assert "delivery_mode" in Path("src/app/server/run_store.py").read_text()
