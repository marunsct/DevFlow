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


QUOTED = ("Plan the sprint.\n\n--- From the approved technical specification: the contracts your work orders copy from "
          "(/docs/technical_specification.md has the rest) ---\nComponent boundaries:\n- app.py serves the API\n\n"
          "API and event contracts:\n- POST /notes -> 201\n\n--- Next part ---\nmore\n")
DOC = ("# Technical specification\n\n## Product Scope\nNotes.\n\n## Component Boundaries\n- app.py serves the API\n"
       + ("x " * 3000) + "\n\n## API and Event Contracts\n- POST /notes -> 201\n" + ("y " * 3000)
       + "\n\n## Data Contracts\nA note is {id, title}.\n\n## Open Questions\nNone.\n")


def test_sections_the_request_quotes_are_not_held_twice(tmp_path):
    """Measured on three runs: the technical lead's request quoted the specification's contract sections (~31k
    characters) while its memory held the whole specification again."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technical_specification.md").write_text(DOC)
    text, _ = project_memory.render(tmp_path, 400_000, focus=QUOTED)
    assert "## Component Boundaries" not in text and "x x x" not in text and "y y y" not in text
    assert "## Data Contracts" in text and "## Open Questions" in text
    assert "Component Boundaries" in text  # named as quoted in the request
    whole, _ = project_memory.render(tmp_path, 400_000, focus="Plan the sprint.")
    assert "x x x" in whole


def test_the_lead_s_quote_uses_the_document_s_own_headings():
    from app.agents import technical_lead

    assert ("api_and_event_contracts", "API and event contracts") in technical_lead._CONTRACT_SECTIONS


def test_a_planning_stage_is_not_given_the_harness_s_kept_files(tmp_path):
    """Measured on one run: the technical lead's memory held the harness's `test-setup.mjs` (44k characters) and
    `playwright.setup.mjs` (8k) - files no work order may change."""
    root = _project(tmp_path)
    (root / "notes_api" / "test-setup.mjs").write_text("// harness\n" + "setup(); " * 3000)
    text, held = project_memory.render(root, 400_000, focus="Plan the sprint.",
                                       kept_out=("notes_api/test-setup.mjs",))
    assert "notes_api/test-setup.mjs" not in held and "setup(); setup();" not in text
    assert "notes_api/test-setup.mjs" in text  # named as the harness's
    assert "notes_api/storage.py" in held


def test_the_planning_stages_are_named():
    assert project_memory.planning_stage("technical_lead") and project_memory.planning_stage("scrum_master")
    assert not project_memory.planning_stage("specialist_backend_0")
    assert not project_memory.planning_stage("acceptance_author_0")
