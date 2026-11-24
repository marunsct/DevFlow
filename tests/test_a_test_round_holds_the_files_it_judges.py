"""A test round is handed the milestone's changed files in its memory, numbered (LF.1286).

Measured on one medium run: each test round's testing stage, told the milestone's changed files by name only, read the
same 13-20 files 3.5-7 times each and was summarised 5-12 times a round (47 summaries over six rounds); its memory held
the plans first and named the code as not included, so a summary dropped each read and the stage read it again. A
product whose files today's request and memory already show gets the round exactly as before.
"""
from __future__ import annotations

from app.agents import project_memory
from app.agents.specialists import SpecialistOutput
from workflow_node_stubs import run_a_test_round

HELD = "Held whole in the project memory for this work"


def _settings(monkeypatch, window: int) -> None:
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", str(window))
    monkeypatch.setenv("PROJECT_MEMORY", "on")
    monkeypatch.setenv("CANONICAL_MEMORY", "on")


def _a_milestone(root, files: int, size: int, specification: int) -> list[str]:
    changed = []
    for n in range(files):
        name = f"app/routes/r{n:02}.py"
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(f'VALUE_{n:02} = "route {n}"\n'
                                 + "".join(f"# what route {n} does, line {k}\n" for k in range(size // 32)))
        changed.append(name)
    (root / "docs").mkdir(exist_ok=True)
    sections = "".join(f"## Section {k}\n" + "The product keeps its records.\n" * 30
                       for k in range(specification // 960))
    (root / "docs" / "technical_specification.md").write_text("# Specification\n" + sections)
    return changed


def _the_round_s_opening(monkeypatch, root, changed: list[str]) -> str:
    seen = run_a_test_round(monkeypatch, root, failing_due=["AC-1"],
                            specialist_outputs={"specialist_backend_0": SpecialistOutput(changed_files=changed)})
    return seen.request["messages"][-1]["content"]


def test_a_test_round_past_its_room_holds_the_changed_files_numbered(tmp_path, monkeypatch):
    _settings(monkeypatch, 65_536)
    changed = _a_milestone(tmp_path, 12, 3_000, specification=58_000)

    opening = _the_round_s_opening(monkeypatch, tmp_path, changed)
    memory, held = project_memory.render_for_a_stage(tmp_path, None, opening, "test_round_1")

    assert HELD in opening and "`app/routes/r11.py`" in opening
    assert set(changed) <= set(held)
    assert memory.index("=== app/routes/r00.py") < memory.index("=== docs/technical_specification.md")
    assert '     1\tVALUE_00 = "route 0"' in memory


def test_a_test_round_whose_files_fit_is_as_before(tmp_path, monkeypatch):
    """Guard: a small product's round request and memory carry nothing of this."""
    _settings(monkeypatch, 65_536)
    changed = _a_milestone(tmp_path, 3, 300, specification=3_000)

    opening = _the_round_s_opening(monkeypatch, tmp_path, changed)
    memory, held = project_memory.render_for_a_stage(tmp_path, None, opening, "test_round_1")

    assert "Held whole in the project memory" not in opening and "(numbered lines" not in memory
    assert set(changed) <= set(held)
