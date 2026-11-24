"""Each stage's opening request is held to one input budget: evidence first, standing context cut to the work (LF.1274).

Measured (deep review 2026-11-24, D.14): a 91,776-token slot reserved 32,000 for the reply and was summarised from
about 43,000; the specification alone was about 34,000 tokens. After LF.1270 sized the agent-loop fixer's request,
the rewrite path's one-file fix requests were still 84,000-99,000 characters on a small static page and
75,000-97,000 on a small API (about 39,000 of them the project's other files), and every builder of a medium run's
first sprint, the lead, the planner, the reviews and the suite's author opened on 157,000-198,000 characters, about
60,000 of them the specification's sections beside the parts of it their requests already quoted.
"""
from __future__ import annotations

import json
import re
import runpy
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import HumanMessage
from langchain_core.runnables.config import var_child_runnable_config

from app.agents import project_memory
from app.graph import rewritten_fixes
from app.sprint import Defect

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
EFFECTS = Path(__file__).resolve().parent.parent / "scripts" / "loop" / "effects.py"
#: A window whose budget (room for ten working calls before the first summary) is about 60,000 characters.
WINDOW = "65536"
TARGET = 60_423

FILE = "from app.db import engine\n\n\ndef create_item(body):\n    return engine.insert(body)\n"
FAILURE = ("[AC-3] creates an item: AssertionError: assert 404 == 201\n"
           "  -> POST http://127.0.0.1:8000/api/items\n  at app/routes/items.py:4")


def _project(root: Path, others: int, size: int) -> None:
    """A product whose items route is the defect's file, beside `others` route files of `size` characters each."""
    (root / "app" / "routes").mkdir(parents=True, exist_ok=True)
    (root / "app" / "routes" / "items.py").write_text(FILE)
    (root / "app" / "db.py").write_text("engine = None\n")
    for n in range(others):
        (root / "app" / "routes" / f"widget_{n}.py").write_text(f"# widgets {n}\n" + "x = 1\n" * (size // 6))


def _specification(resources: list[str]) -> SimpleNamespace:
    return SimpleNamespace(
        api_and_event_contracts=[f"{verb} /api/{name} - {what} {name}"
                                 for name in resources for verb, what in (("GET", "lists"), ("POST", "creates"))],
        data_contracts=[f"{name[:-1].capitalize()}: {{id, name, owner_id}}" for name in resources],
        error_catalogue=[f"404 when the {name[:-1]} does not exist" for name in resources],
        interface_design=["The page lists everything"],
    )


def _defect() -> Defect:
    return Defect(description="[AC-3] Create items - the acceptance suite says this does not work yet.",
                  expected_behavior="POST /api/items answers 201 with the item", actual_behavior=FAILURE,
                  affected_files=["app/routes/items.py"], severity="major", owner="backend",
                  reproduction_steps="Run the acceptance suite.")


def _rewrite_request(root: Path, monkeypatch, resources: list[str]) -> str:
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", WINDOW)
    monkeypatch.setenv("PROJECT_MEMORY", "on")
    return rewritten_fixes.fix_request(root, "app/routes/items.py", _defect(), FAILURE, _specification(resources),
                                       None, [], [])


def test_a_rewrite_on_a_medium_product_opens_with_its_evidence_within_its_budget(tmp_path, monkeypatch):
    _project(tmp_path, others=40, size=2_000)

    request = _rewrite_request(tmp_path, monkeypatch, ["items", *(f"widget{n}s" for n in range(60))])

    assert len(request) <= TARGET
    # The instruction where it was; the defect, what failed and the file to correct before any standing context.
    assert request.startswith("Correct the file `app/routes/items.py`")
    standing = request.index("--- Around this defect")
    assert request.index("--- The defect ---") < request.index("--- What failed ---") < standing
    assert request.index("--- `app/routes/items.py` as it is now ---\n" + FILE) < standing
    assert request.rstrip().endswith("If this file needs no change for this failure, reply with it unchanged.")
    # The API cut to the route its failing test calls, the rest named with where to read it.
    assert "POST /api/items - creates items" in request and "/api/widget1s" not in request
    assert "/docs/technical_specification.md" in request
    # The project: the file and what it imports, whole; the others named.
    project = request[request.index("--- The project ---"):]
    assert "=== app/routes/items.py ===" in project and "=== app/db.py ===" in project
    assert "=== app/routes/widget_7.py ===" not in project


def test_a_rewrite_on_a_small_product_is_asked_as_it_was_built(tmp_path, monkeypatch):
    _project(tmp_path, others=2, size=300)

    request = _rewrite_request(tmp_path, monkeypatch, ["items", "widgets"])

    assert "--- Around this defect" not in request
    assert request.index("--- The defect ---") < request.index("GET /api/widgets") < request.index("--- The project")
    assert "The page lists everything" in request and "=== app/routes/widget_1.py ===" in request


def test_what_a_fitted_rewrite_request_says_names_no_product_word(tmp_path, monkeypatch):
    _project(tmp_path, others=40, size=2_000)

    request = _rewrite_request(tmp_path, monkeypatch, ["items", *(f"widget{n}s" for n in range(60))])

    assert not BANNED.search(request)


WORDS = "The service keeps each record with its owner and its time of change, and answers in the agreed shape. "


def _specification_document(sections: int, size: int) -> str:
    return "# Technical specification\n\n" + "".join(
        f"## AC-{n} The service record contract\n" + WORDS * (size // len(WORDS)) + "\n\n"
        for n in range(1, sections + 1))


def _a_builder_s_memory(root: Path, monkeypatch, sections: int, switch: str = "on") -> tuple[str, str]:
    """A first-sprint builder's opening request and the memory the project memory middleware gives it, in a run whose
    transcript is under `root`/data; `switch` is `REQUEST_BUDGET_FOR_EVERY_STAGE`."""
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", WINDOW)
    monkeypatch.setenv("PROJECT_MEMORY", "on")
    monkeypatch.setenv("REQUEST_BUDGET_FOR_EVERY_STAGE", switch)
    monkeypatch.setenv("DATA_DIR", str(root / "data"))
    (root / "docs").mkdir()
    (root / "docs" / "technical_specification.md").write_text(_specification_document(sections, 3_000))
    (root / "service").mkdir()
    (root / "service" / "manifest.toml").write_text("[project]\nname = 'service'\n")
    # Its request shares words with every section's heading, as a builder's does.
    opening = ("--- Your work order ---\nWrite `service/app/items.py` so AC-3 passes.\n\n"
               "--- The specification for your files: build exactly to it ---\n" + WORDS * 100 + "\n")
    middleware = project_memory.build_project_memory_middleware(str(root))
    sent = []

    class Request:
        def __init__(self, messages):
            self.messages, self.model = messages, None

        def override(self, messages):
            return Request(messages)

    token = var_child_runnable_config.set({"configurable": {"app_stage": "specialist_backend_0",
                                                            "app_run_id": "run-builder"}})
    try:
        middleware.wrap_model_call(Request([HumanMessage(content=opening)]), lambda request: sent.append(request))
    finally:
        var_child_runnable_config.reset(token)
    return opening, sent[0].messages[0].content


def _budget_records(root: Path) -> list[dict]:
    path = root / "data" / "transcripts" / "run-builder.jsonl"
    return [r for r in map(json.loads, path.read_text().splitlines()) if r.get("kind") == "request_budget"]


def test_a_builder_whose_specification_fills_its_budget_holds_it_as_the_sections_its_request_points_at(
        tmp_path, monkeypatch):
    opening, sent = _a_builder_s_memory(tmp_path, monkeypatch, sections=30)

    assert len(sent) <= TARGET
    assert "=== docs/technical_specification.md (outline" in sent
    # The section its request names, and every other one named by line.
    assert "## AC-3 The service record contract\n" + WORDS in sent
    assert re.search(r"- lines \d+-\d+: AC-29 The service record contract", sent)


def test_a_builder_whose_specification_fits_holds_it_whole(tmp_path, monkeypatch):
    _, sent = _a_builder_s_memory(tmp_path, monkeypatch, sections=3)

    assert "=== docs/technical_specification.md ===" in sent


def test_with_the_switch_off_a_builder_s_memory_is_as_before_and_its_record_says_what_would_be_cut(
        tmp_path, monkeypatch):
    """Small runs open past the budget too and score every hidden test today: the cut for every stage is measured."""
    _, sent = _a_builder_s_memory(tmp_path, monkeypatch, sections=30, switch="off")

    assert len(sent) > TARGET
    # The digest as before: many more sections than the one its request names.
    assert all(f"## AC-{n} The service record contract\n" + WORDS in sent for n in (1, 3, 10))
    record, = _budget_records(tmp_path)
    assert record["applied"] is False and record["built"] > TARGET >= record["sent"]
    assert record["cut"] == ["docs/technical_specification.md as its outline and the sections this request points "
                             "at (read others by line)"]


def test_with_the_switch_on_the_record_says_the_memory_was_held_to_the_budget(tmp_path, monkeypatch):
    from app.observability import switch_firing

    _a_builder_s_memory(tmp_path, monkeypatch, sections=30)

    record, = _budget_records(tmp_path)
    assert record["applied"] is True
    assert switch_firing.fired([record]) == ["REQUEST_BUDGET_FOR_EVERY_STAGE"]


def test_a_request_past_its_budget_leaves_a_record_the_effects_report_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    product = tmp_path / "product"
    _project(product, others=40, size=2_000)
    token = var_child_runnable_config.set({"configurable": {"app_run_id": "run-budget", "app_stage": "defect_fix"}})
    try:
        _rewrite_request(product, monkeypatch, ["items", *(f"widget{n}s" for n in range(60))])
    finally:
        var_child_runnable_config.reset(token)
    records = [json.loads(line) for line in (tmp_path / "data" / "transcripts" / "run-budget.jsonl").read_text()
               .splitlines()]

    line, = runpy.run_path(str(EFFECTS))["budget_lines"](records)

    assert line.startswith("     1  LF.1274 opening requests past their input budget, cut to it (1 checked")
    assert "defect_fix 1" in line and "target 60,423" in line


def test_the_effects_report_counts_apart_the_memories_the_switch_would_have_cut():
    records = [{"kind": "request_budget", "stage": "specialist_backend_0", "target": 60_423, "built": 90_000,
                "sent": 59_000, "applied": False,
                "cut": ["docs/technical_specification.md as its outline and the sections this request points at "
                        "(read others by line)"]},
               {"kind": "request_budget", "stage": "defect_fix", "target": 60_423, "built": 30_000, "sent": 30_000}]

    lines = runpy.run_path(str(EFFECTS))["budget_lines"](records)

    assert lines[0] == "     0  LF.1274 opening requests past their input budget, cut to it (2 checked, none cut)"
    assert lines[1].startswith("     1  LF.1274 stage memories past the budget, sent as built "
                               "(REQUEST_BUDGET_FOR_EVERY_STAGE off; would be built median 90,000 -> sent 59,000")
    assert "specialist_backend 1" in lines[1] and "docs/technical_specification.md 1" in lines[1]


def test_the_effects_report_says_when_no_request_was_checked():
    line, = runpy.run_path(str(EFFECTS))["budget_lines"]([{"kind": "model_request"}])

    assert line.endswith("LF.1274 opening requests past their input budget, cut to it: not reached")
