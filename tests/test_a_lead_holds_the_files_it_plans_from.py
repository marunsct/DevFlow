"""The technical lead is handed the product's code and the sprint's locked tests in its memory, numbered (LF.1286).

Measured on one medium run: a later sprint's lead made 243 reads of 20 files over 159 model calls with 21 summaries -
`models.py` and `main.py` 27 times each, the sprint's locked tests 13-18 times each - because its memory held the plans
and every file it read was "Not included here"; a summary dropped the reads and it read them again. A product whose
files today's request and memory already show is planned exactly as before.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables.config import var_child_runnable_config

from app.acceptance import suite
from app.acceptance.criteria import number
from app.agents import project_memory
from app.agents.review_files import held_section
from app.agents.scrum_master import SprintDefinition, SprintPlanOutput
from workflow_node_stubs import run_node, two_work_orders

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
HELD = "Held whole in the project memory for this work"
BRIEF = "# Brief\n## Features\n- Sign up for an account\n- Set a priority on each record\n"


def _settings(monkeypatch, window: int) -> None:
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", str(window))
    monkeypatch.setenv("PROJECT_MEMORY", "on")
    monkeypatch.setenv("CANONICAL_MEMORY", "on")


def _a_product_in_its_second_sprint(root, files: int, size: int, specification: int) -> list[str]:
    """A locked suite (AC-1 in sprint 1, AC-2 in sprint 2), `files` code files of `size` characters, a specification."""
    (root / ".project-directory").write_text("proj\n")
    suite.save_criteria(root, number(BRIEF))
    (root / "proj" / "acceptance").mkdir(parents=True)
    (root / "proj" / "acceptance" / "accounts.spec.js").write_text(
        "test('[AC-1] signs up', async () => { /* sign up */ });\n")
    (root / "proj" / "acceptance" / "priority.spec.js").write_text(
        "test('[AC-2] sets a priority', async () => { /* priority */ });\n" + "// the priority checks\n" * 40)
    suite.lock(root)
    code = []
    for n in range(files):
        name = f"proj/app/part{n:02}.py"
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(f'PART_{n:02} = "part {n}"\n'
                                 + "".join(f"# what part {n} does, line {k}\n" for k in range(size // 32)))
        code.append(name)
    (root / "docs").mkdir(exist_ok=True)
    sections = "".join(f"## Section {k}\n" + "The product keeps its records.\n" * 30
                       for k in range(specification // 960))
    (root / "docs" / "technical_specification.md").write_text("# Specification\n" + sections)
    return code


def _the_lead_s_opening(monkeypatch, root) -> str:
    plan = SprintPlanOutput(sprints=[SprintDefinition(goal="Accounts", user_value="v", criteria=["AC-1"]),
                                     SprintDefinition(goal="Priorities", user_value="v", criteria=["AC-2"])])
    seen = run_node(monkeypatch, root, "technical_lead", answer=two_work_orders(), sprint_plan=plan,
                    current_sprint_index=1)
    ((stage, request),) = seen.requests
    assert stage == "technical_lead"
    return request["messages"][-1]["content"]


def test_a_lead_past_its_room_holds_the_code_and_the_sprint_s_tests_numbered(tmp_path, monkeypatch):
    _settings(monkeypatch, 65_536)
    code = _a_product_in_its_second_sprint(tmp_path, 8, 3_000, specification=58_000)

    opening = _the_lead_s_opening(monkeypatch, tmp_path)
    memory, held = project_memory.render_for_a_stage(tmp_path, None, opening, "technical_lead")

    assert HELD in opening and "`proj/acceptance/priority.spec.js`" in opening
    assert {*code, "proj/acceptance/priority.spec.js", "proj/acceptance/accounts.spec.js"} <= set(held)
    assert memory.index("=== proj/acceptance/priority.spec.js") < memory.index("=== docs/technical_specification.md")
    assert '     1\tPART_00 = "part 0"' in memory, "numbered, so a work order names a line without a read"


def test_a_lead_s_first_read_of_a_held_file_is_answered_from_the_memory(tmp_path, monkeypatch):
    """With the file numbered in the memory, a copy in the conversation is the one a summary deletes."""
    _settings(monkeypatch, 65_536)
    monkeypatch.setenv("FIRST_REREAD_ANSWERED", "on")  # built in: a held file's first read gets its numbered lines
    code = _a_product_in_its_second_sprint(tmp_path, 8, 3_000, specification=58_000)
    opening = _the_lead_s_opening(monkeypatch, tmp_path)
    middleware = project_memory.build_project_memory_middleware(str(tmp_path))

    class Request(SimpleNamespace):
        def override(self, **changes):
            return Request(**{**self.__dict__, **changes})

    token = var_child_runnable_config.set({"configurable": {"app_stage": "technical_lead"}})
    try:
        middleware.wrap_model_call(Request(messages=[HumanMessage(content=opening)], model=None), lambda r: None)
        read = SimpleNamespace(tool_call={"name": "read_file", "id": "r1", "args": {"file_path": code[0]}})
        answer = middleware.wrap_tool_call(read, lambda request: "the file from disk")
    finally:
        var_child_runnable_config.reset(token)

    assert isinstance(answer, ToolMessage) and project_memory.HELD_POINTER in answer.content
    assert "PART_00" not in answer.content


def test_a_lead_whose_files_fit_is_planned_as_before(tmp_path, monkeypatch):
    """Guard: a small product's lead request and memory carry nothing of this."""
    _settings(monkeypatch, 65_536)
    code = _a_product_in_its_second_sprint(tmp_path, 3, 300, specification=3_000)

    opening = _the_lead_s_opening(monkeypatch, tmp_path)
    memory, held = project_memory.render_for_a_stage(tmp_path, None, opening, "technical_lead")

    assert "Held whole in the project memory" not in opening
    assert "(numbered lines" not in memory
    assert set(code) <= set(held)


def test_what_a_lead_is_told_of_its_held_files_uses_none_of_the_banned_words():
    text = held_section(["proj/app/part00.py"], "technical_lead")

    assert HELD in text and "`proj/app/part00.py`" in text
    assert not BANNED.search(text)
