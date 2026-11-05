"""A fixer's memory holds the product's code first and the plans only as far as its defect needs them.

Measured over 64 fix attempts: every fixer opened on about 164k characters - work orders, rationale, open
questions, the sprint plan - with the failure it had to fix about 2k of it; the attempts left open read twice
as many files and reasoned nearly three times as long as those that fixed their defect.
"""
from app.agents import project_memory

SPEC = "# Technical specification\n\n" + "".join(
    f"## Section {n}\n" + ("Words about something unrelated. " * 60) + "\n\n" for n in range(40)
) + "## Storage\nNotes are saved to DATA_DIR/notes.json and read back on start.\n"


def _project(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technical_specification.md").write_text(SPEC)
    (tmp_path / "docs" / "sprint_plan.md").write_text("# Sprint plan\n" + "Plans. " * 2000)
    (tmp_path / "docs" / "milestone_plan.md").write_text("# Milestone plan\n" + "Milestones. " * 2000)
    (tmp_path / "docs" / "acceptance_criteria.md").write_text("# Acceptance criteria\n- AC-1 Notes survive a restart\n")
    (tmp_path / "notes_api").mkdir()
    (tmp_path / "notes_api" / "storage.py").write_text("def save(note):\n    pass\n")
    return tmp_path


def test_a_fixer_gets_the_code_and_not_the_plans(tmp_path):
    root = _project(tmp_path)
    text, held = project_memory.render(root, 200_000, focus="Storage: notes do not survive", for_a_fixer=True)

    assert "notes_api/storage.py" in held
    assert "docs/sprint_plan.md" not in held and "Plans. Plans." not in text
    assert "Milestones." not in text
    assert "DATA_DIR/notes.json" in text  # the specification section the defect points at
    assert text.index("=== notes_api/storage.py") < text.index("technical_specification")
    assert len(text) < 30_000


def test_other_stages_keep_the_documents(tmp_path):
    root = _project(tmp_path)
    text, held = project_memory.render(root, 200_000, focus="")
    assert "docs/sprint_plan.md" in held
