"""A builder that opens on code earlier stages wrote holds that code, and the plans of finished work only named.

Measured on one run: a later sprint's testing stage, writing unit tests for code two sprints had written, opened on a
153k-character memory that held the workflow's documents whole - the sprint plan with every sprint's long sections,
the milestone plan, the acceptance tests, the stack - and of the product only a package's empty `__init__`. The files
its tests were for were named as left out. Reading them crossed the summarising trigger, the summary dropped them,
it read them again: eleven summaries and fifty minutes. A fixer's memory already puts the code first and names the
other plans; a builder on written code now gets the same priority. A builder with no code written yet keeps the
documents as before.
"""
from __future__ import annotations

import re

from langchain_core.messages import HumanMessage
from langchain_core.runnables.config import var_child_runnable_config

from app.agents import project_memory
from app.analysis import project_memory as authorship

WINDOW_TOKENS = "131072"
WORDS = "The service keeps each record with its owner and its time of change, and answers in the agreed shape. "

#: The product two sprints wrote, by the stage that wrote each file; one file the setup wrote.
PRODUCT = {
    "service/app/__init__.py": ("", "stack_setup"),
    "service/app/main.py": ("from .routers import notes\n\napp = create_app()\n", "specialist_backend_1"),
    "service/app/models.py": ("class Note:\n    owner: str\n", "specialist_backend_1"),
    "service/app/schemas.py": ("class NoteIn:\n    title: str\n", "specialist_backend_1"),
    "service/app/auth.py": ("def current_user(token):\n    return token\n", "specialist_backend_1"),
    "service/app/database.py": ("def session():\n    return None\n", "specialist_backend_1"),
    "service/app/config.py": ("DATA_DIR = 'data'\n", "specialist_backend_1"),
    "service/app/routers/__init__.py": ("", "specialist_backend_1"),
    "service/app/routers/notes.py": ("def list_notes(user):\n    return []\n", "specialist_backend_1"),
    "web/src/App.tsx": ("export function App() { return null; }\n", "specialist_ui_ux_0"),
    "web/src/components/NoteList.tsx": ("export function NoteList() { return null; }\n", "specialist_ui_ux_0"),
    "web/src/components/NoteForm.tsx": ("export function NoteForm() { return null; }\n", "specialist_ui_ux_0"),
    "web/src/api.ts": ("export async function listNotes() { return []; }\n", "specialist_ui_ux_0"),
}
WRITTEN_BY_THE_SPRINTS = [path for path, (_, author) in PRODUCT.items() if author != "stack_setup"]


def _long(heading: str, sections: int, size: int) -> str:
    return f"# {heading}\n\n" + "".join(
        f"## {heading} part {n}\n" + (WORDS * (size // len(WORDS))) + "\n\n" for n in range(sections))


def _sprint_plan() -> str:
    sprints = [("Sign in and keep notes", "AC-1, AC-2, AC-3"), ("Share notes", "AC-4, AC-5, AC-6"),
               ("Unit tests for the service", "AC-7, AC-8")]
    body = "".join(
        f"### Sprint {n}: {goal}\n\n**Makes these acceptance criteria pass:** {criteria}\n\n**In scope:**\n"
        + (f"- finished work {n}: " + WORDS + "\n") * 120 + "\n"
        for n, (goal, criteria) in enumerate(sprints, 1))
    return "# Sprint Plan\n\n## Sprints\n\n" + body


def _project(root, written: bool):
    """A product's workspace as the harness leaves it: the workflow's documents, and `written` the sprints' code."""
    (root / ".harness").mkdir()
    docs = root / "docs"
    docs.mkdir()
    (docs / "technical_specification.md").write_text(_long("Specification", 30, 3_000))
    (docs / "sprint_plan.md").write_text(_sprint_plan())
    (docs / "acceptance_criteria.md").write_text(
        "# Acceptance criteria\n\n" + "".join(f"- AC-{n}: a person can do thing {n}\n" for n in range(1, 9)))
    (docs / "acceptance_tests.md").write_text(_long("Acceptance tests", 8, 2_500))
    (docs / "milestone_plan.md").write_text(_long("Milestones", 6, 2_000))
    (docs / "technology_stack.md").write_text(_long("Stack", 3, 2_000))
    (docs / "product_intake.md").write_text(_long("Intake", 2, 2_000))
    for path, (text, author) in PRODUCT.items():
        if author != "stack_setup" and not written:
            continue
        file = root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        # Each file a few kilobytes, as a product's modules are.
        file.write_text(text + ("\n# " + WORDS) * (5_000 // len(WORDS)) if path.endswith(".py")
                        else text + ("\n// " + WORDS) * (5_000 // len(WORDS)))
        authorship.record(root, path, author)
    return root


def _request() -> str:
    return ("--- Where things stand (written by the harness from what it measured) ---\n"
            + "Finished: " + ", ".join(f"`{path}`" for path in WRITTEN_BY_THE_SPRINTS) + "\n\n"
            "--- Your work order ---\nWrite unit tests for the service: `service/tests/test_notes.py`, "
            "`service/tests/test_auth.py`; the routers package, `service/app/routers/__init__.py`, gathers the routes. "
            "Unit tests for the service make AC-7 and AC-8 pass.\n")


def _opening_memory(root, stage: str, monkeypatch) -> str:
    """The opening request a stage's first model call is sent, as the project memory middleware hands it over."""
    monkeypatch.setenv("PROJECT_MEMORY", "on")
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", WINDOW_TOKENS)
    # As deployed: a request's memory sliced to the files it names. The documents held whole by their size alone.
    monkeypatch.setenv("SLICED_MEMORY", "on")
    monkeypatch.setenv("STABLE_STAGE_PREFIX", "off")
    middleware = project_memory.build_project_memory_middleware(str(root))
    sent = []

    class Request:
        def __init__(self, messages):
            self.messages, self.model = messages, None

        def override(self, messages):
            return Request(messages)

    token = var_child_runnable_config.set({"configurable": {"app_stage": stage}})
    try:
        middleware.wrap_model_call(Request([HumanMessage(content=_request())]), lambda request: sent.append(request))
    finally:
        var_child_runnable_config.reset(token)
    return sent[0].messages[0].content


def _held_whole(memory: str) -> set[str]:
    return set(re.findall(r"(?m)^=== (\S+) ===$", memory))


def test_a_later_sprint_s_builder_holds_the_code_it_builds_on(tmp_path, monkeypatch):
    root = _project(tmp_path, written=True)

    memory = _opening_memory(root, "specialist_testing_2", monkeypatch)

    assert set(WRITTEN_BY_THE_SPRINTS) <= _held_whole(memory)


def test_the_plans_of_finished_work_are_named_not_held(tmp_path, monkeypatch):
    root = _project(tmp_path, written=True)

    memory = _opening_memory(root, "specialist_testing_2", monkeypatch)

    held = _held_whole(memory)
    assert not {"docs/sprint_plan.md", "docs/milestone_plan.md", "docs/acceptance_tests.md",
                "docs/technology_stack.md"} & held
    assert "finished work 1:" not in memory
    named = memory.split("Not included here")[1]
    assert "docs/milestone_plan.md" in named and "docs/acceptance_tests.md" in named


def test_the_builder_keeps_its_own_sprint_and_the_criteria(tmp_path, monkeypatch):
    root = _project(tmp_path, written=True)

    memory = _opening_memory(root, "specialist_testing_2", monkeypatch)

    assert "docs/acceptance_criteria.md" in _held_whole(memory)
    assert "Sprint 3: Unit tests for the service" in memory and "finished work 3:" in memory
    assert "Specification part 0" in memory  # the specification's outline, its sections read by line


def test_a_builder_with_no_code_written_yet_keeps_the_documents(tmp_path, monkeypatch):
    root = _project(tmp_path, written=False)

    memory = _opening_memory(root, "specialist_backend_1", monkeypatch)

    assert {"docs/sprint_plan.md", "docs/acceptance_tests.md"} <= _held_whole(memory)
