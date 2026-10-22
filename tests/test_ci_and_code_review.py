"""CI between a batch and its tests, the code review, and the guard around a fix."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app import ci
from app.acceptance import suite
from app.acceptance.criteria import number
from app.graph import engineering
from app.stacks import pack_named
from app.stacks.scaffold import scaffold
from app.tools.version_control import initialise_repository

PACK = pack_named("browser-javascript")
CONFIG = {"configurable": {"thread_id": "t"}}
BRIEF = "# Brief\n## Features\n- Add a note\n- Delete a note\n"


class Runner:
    """Writes the report each command would have written; outcomes per test are set per call."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.unit: dict[str, str] = {"adds": "passed"}
        self.acceptance: dict[str, str] = {"[AC-1] adds": "passed", "[AC-2] deletes": "failed"}

    def __call__(self, argv, category, working_directory):
        if category == "test":
            unit = list(argv) == PACK.commands(working_directory)["unit_test"]
            tests = self.unit if unit else self.acceptance
            cases = "".join(
                f"<testcase name='{name}'>" + ("<failure message='no'/>" if outcome == "failed" else "") + "</testcase>"
                for name, outcome in tests.items()
            )
            target = self.root / working_directory / (PACK.unit_report if unit else PACK.acceptance_report)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"<testsuites><testsuite>{cases}</testsuite></testsuites>")
        return {"returncode": "0", "stdout": "", "stderr": ""}


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    initialise_repository(tmp_path)
    runner = Runner(tmp_path)
    smoke = Runner(tmp_path)
    smoke.acceptance = {"smoke": "passed"}
    assert scaffold(tmp_path, PACK, "notes", "Notes", run=smoke).ok
    suite.save_criteria(tmp_path, number(BRIEF))
    spec = tmp_path / "notes" / "acceptance" / "notes.spec.js"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("test('[AC-1] adds', ()=>{});\ntest('[AC-2] deletes', ()=>{});\n")
    suite.lock(tmp_path)
    monkeypatch.setattr("app.stacks.scaffold.sandbox_runner", lambda root: runner)
    monkeypatch.setattr("app.graph.workflow._stop_if_cancelled", lambda run_id: None)
    return SimpleNamespace(root=tmp_path, runner=runner)


def test_a_snapshot_records_every_test(workspace) -> None:
    snapshot = ci.take(workspace.root, "now")
    assert snapshot.unit == {"adds": "passed"} and snapshot.unit_ran
    assert snapshot.acceptance["[AC-2] deletes"] == "failed" and snapshot.acceptance_ran
    assert snapshot.passing() == {"unit: adds", "acceptance: [AC-1] adds"}


def test_a_regression_is_what_passed_and_no_longer_does(workspace) -> None:
    before = ci.take(workspace.root, "before")
    workspace.runner.acceptance = {"[AC-1] adds": "failed", "[AC-2] deletes": "passed"}
    after = ci.take(workspace.root, "after")
    # AC-2 starting to pass is progress, not a regression.
    assert ci.regressions(before, after) == ["acceptance: [AC-1] adds"]
    assert ci.regressions(None, after) == []


def test_a_suite_that_stops_running_regresses_everything_it_passed(workspace) -> None:
    before = ci.take(workspace.root, "before")
    after = ci.Snapshot(label="broken build", unit_ran=False, acceptance_ran=True, acceptance=before.acceptance)
    assert ci.regressions(before, after) == ["unit: adds"]


def test_the_ci_gate_turns_regressions_into_defects(workspace) -> None:
    engineering.accepted_state(str(workspace.root))
    workspace.runner.unit = {"adds": "failed"}
    state = {
        "repository": SimpleNamespace(root_path=str(workspace.root)),
        "milestone_plan": SimpleNamespace(delegated_tasks=[
            SimpleNamespace(title="Delete notes", task_description="", specialist_role="ui_ux"),
        ]),
    }

    update = engineering.ci_gate(state, CONFIG, None)

    assert update["stage"] == "code_review"
    (defect,) = update["review_defects"]
    assert "unit: adds" in defect.description and defect.owner == "ui_ux"
    assert "Regressed - passed when the last sprint was accepted or before this batch" in update["ci_report"]


def test_no_scaffold_and_no_suite_means_no_ci(tmp_path) -> None:
    state = {"repository": SimpleNamespace(root_path=str(tmp_path))}
    assert engineering.ci_gate(state, CONFIG, None)["stage"] == "test_and_triage"


def test_a_fix_that_breaks_what_passed_is_reverted(workspace) -> None:
    root = str(workspace.root)
    app = workspace.root / "notes" / "src" / "main.js"
    original = app.read_text()
    base = engineering.before_a_fix(root, "defect_fix_1_0")

    app.write_text("broken\n")
    (workspace.root / "notes" / "src" / "extra.js").write_text("// added by the fix\n")
    workspace.runner.acceptance = {"[AC-1] adds": "failed", "[AC-2] deletes": "failed"}

    broke = engineering.after_a_fix(root, base, "defect_fix_1_0", "Delete does nothing")

    assert broke == ["acceptance: [AC-1] adds"]
    assert app.read_text() == original
    assert not (workspace.root / "notes" / "src" / "extra.js").exists()
    # The locked suite and the harness's records are not the fix's to lose.
    assert suite.is_locked(root)


def test_a_fix_that_breaks_nothing_is_kept_and_committed(workspace) -> None:
    root = str(workspace.root)
    base = engineering.before_a_fix(root, "defect_fix_1_0")
    (workspace.root / "notes" / "src" / "main.js").write_text("// fixed\n")
    workspace.runner.acceptance = {"[AC-1] adds": "passed", "[AC-2] deletes": "passed"}

    assert engineering.after_a_fix(root, base, "defect_fix_1_0", "Delete does nothing") == []
    assert ci.head(root) != base
    assert ci.load(root, "latest").acceptance["[AC-2] deletes"] == "passed"


def test_a_fix_that_replaces_a_unit_test_without_dropping_coverage_is_kept(workspace) -> None:
    root = str(workspace.root)
    workspace.runner.unit = {"old_behavior_assertion": "passed"}
    base = engineering.before_a_fix(root, "defect_fix_1_0")
    (workspace.root / "notes" / "src" / "main.js").write_text("// fixed\n")
    workspace.runner.unit = {"new_behavior_assertion": "passed"}
    workspace.runner.acceptance = {"[AC-1] adds": "passed", "[AC-2] deletes": "passed"}

    assert engineering.after_a_fix(root, base, "defect_fix_1_0", "Fix behavior") == []
    assert ci.head(root) != base
    assert ci.load(root, "latest").unit["new_behavior_assertion"] == "passed"


def test_the_code_review_s_blocking_findings_become_owned_defects(workspace, monkeypatch) -> None:
    from app.agents.code_reviewer import CodeReviewFinding, CodeReviewOutput

    engineering.accepted_state(str(workspace.root))
    (workspace.root / "notes" / "src" / "notes.js").write_text("export function remove() { return []; }\n")
    ci.commit(workspace.root, "batch")
    # What the CI gate measures after the batch: `[AC-2] deletes` fails. A
    # finding becomes a defect only when a test or check shows it - see
    # `test_a_review_finding_needs_evidence`.
    ci.save(workspace.root, ci.take(workspace.root, "after the work orders"))
    review = CodeReviewOutput(approved=False, findings=[
        CodeReviewFinding(work_order="Delete notes", severity="blocking", file="notes/src/notes.js",
                          problem="remove() returns an empty list instead of removing one note, so [AC-2] deletes fails",
                          fix="filter by id"),
        CodeReviewFinding(work_order="Delete notes", severity="minor", problem="naming"),
    ])
    seen: list[Any] = []

    def gated(state, config, **kwargs):
        seen.append(kwargs["initial_request"]["messages"][0]["content"])
        return {kwargs["output_key"]: review, "stage": "code_review"}

    monkeypatch.setattr("app.graph.workflow._run_gated_agent", gated)
    monkeypatch.setattr("app.agents.code_reviewer.create_code_reviewer_agent", lambda *a, **k: object())
    state = {
        "repository": SimpleNamespace(root_path=str(workspace.root)),
        "milestone_plan": SimpleNamespace(delegated_tasks=[
            SimpleNamespace(title="Delete notes", task_description="Remove a note", specialist_role="backend"),
        ]),
        "review_defects": [],
    }

    update = engineering.code_review(state, CONFIG, SimpleNamespace(
        judgement_model=None, checkpointer=None, repo_root=None, allow_subdirectories=True,
    ))

    assert "remove()" in seen[0] and "Delete notes" in seen[0]
    assert update["stage"] == "test_and_triage"
    (defect,) = update["review_defects"]
    assert defect.severity == "blocking" and defect.owner == "backend"
    assert defect.affected_files == ["notes/src/notes.js"]


def test_the_code_review_is_told_what_later_sprints_deliver(tmp_path) -> None:
    from app.agents.code_reviewer import build_code_review_request

    suite.save_criteria(tmp_path, number(BRIEF))
    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "current_sprint_index": 0,
        "sprint_plan": SimpleNamespace(sprints=[
            SimpleNamespace(goal="Add notes", criteria=["AC-1"]),
            SimpleNamespace(goal="Delete notes", criteria=["AC-2"]),
        ]),
    }
    later = engineering._later_sprints(state)
    assert "Sprint 2: Delete notes" in later and "AC-2: Delete a note" in later
    assert "AC-1" not in later
    text = build_code_review_request("diff", "orders", "AC-1", "ci", later)["messages"][0]["content"]
    assert "NOT missing from this batch" in text


def test_a_finding_about_later_sprints_criteria_is_not_a_defect_now(workspace, monkeypatch) -> None:
    """Named by id - in any dash a model types. One run's sprint was sent back
    three times over 'AC‑2 ... AC‑5 fail', all four due in later sprints."""
    from app.agents.code_reviewer import CodeReviewFinding, CodeReviewOutput

    engineering.accepted_state(str(workspace.root))
    (workspace.root / "notes" / "src" / "notes.js").write_text("export function add() { return []; }\n")
    ci.commit(workspace.root, "batch")
    # The suite shows AC-1 failing, so that finding is shown and is a defect.
    workspace.runner.acceptance = {"[AC-1] adds": "failed", "[AC-2] deletes": "failed"}
    suite.run(workspace.root)
    review = CodeReviewOutput(approved=False, findings=[
        CodeReviewFinding(work_order="Add notes", severity="blocking", problem="AC‑2 fails: delete is not wired"),
        CodeReviewFinding(work_order="Add notes", severity="major", problem="AC-1 fails: add returns nothing"),
    ])
    monkeypatch.setattr("app.graph.workflow._run_gated_agent",
                        lambda state, config, **kwargs: {kwargs["output_key"]: review, "stage": "code_review"})
    monkeypatch.setattr("app.agents.code_reviewer.create_code_reviewer_agent", lambda *a, **k: object())
    state = {
        "repository": SimpleNamespace(root_path=str(workspace.root)),
        "milestone_plan": SimpleNamespace(delegated_tasks=[
            SimpleNamespace(title="Add notes", task_description="Add a note", specialist_role="backend"),
        ]),
        "sprint_plan": SimpleNamespace(sprints=[
            SimpleNamespace(goal="Add notes", criteria=["AC-1"]),
            SimpleNamespace(goal="Delete notes", criteria=["AC-2"]),
        ]),
        "current_sprint_index": 0,
        "review_defects": [],
    }

    update = engineering.code_review(state, CONFIG, SimpleNamespace(
        judgement_model=None, checkpointer=None, repo_root=None, allow_subdirectories=True,
    ))

    assert [d.description for d in update["review_defects"]] == ["Code review (Add notes): AC-1 fails: add returns nothing"]


def test_the_milestone_review_s_finding_about_later_criteria_is_made_minor(workspace) -> None:
    from app.agents.milestone_reviewer import MilestoneReviewFinding, MilestoneReviewOutput
    from app.graph.workflow import _findings_a_later_sprint_builds

    state = {
        "repository": SimpleNamespace(root_path=str(workspace.root)),
        "sprint_plan": SimpleNamespace(sprints=[
            SimpleNamespace(goal="Add and keep notes", criteria=["AC-1"], in_scope=[], out_of_scope=[]),
            SimpleNamespace(goal="Delete notes", criteria=["AC-2"], in_scope=[], out_of_scope=[]),
        ]),
        "current_sprint_index": 0,
    }
    finding = MilestoneReviewFinding(
        severity="major", category="testing",
        description="Acceptance tests AC‑2 fail; also make sure saving is called after each action",
        required_remediation="Wire the delete handler.",
    )
    review = MilestoneReviewOutput(
        status="changes_required", findings=[finding], acceptance_evidence="",
        documentation_reviewed=True, tests_reviewed=True,
    )

    moved = _findings_a_later_sprint_builds(review, state)

    assert moved.findings[0].severity == "minor"
    assert moved.findings[0].description.startswith("Planned for a later sprint (AC-2)")


def test_a_batch_that_breaks_what_passed_before_any_sprint_was_accepted_is_a_regression(workspace) -> None:
    """One run's re-planned first sprint broke all seven acceptance tests that
    had passed; the only accepted state was the suite as locked, where nothing
    passes, so CI reported nothing."""
    engineering.suite_locked(str(workspace.root))
    workspace.runner.acceptance = {"[AC-1] adds": "passed", "[AC-2] deletes": "passed"}
    ci.save(workspace.root, ci.take(workspace.root, "after a fix"))
    workspace.runner.acceptance = {"[AC-1] adds": "failed", "[AC-2] deletes": "passed"}
    state = {
        "repository": SimpleNamespace(root_path=str(workspace.root)),
        "milestone_plan": SimpleNamespace(delegated_tasks=[
            SimpleNamespace(title="Render the list", task_description="", specialist_role="ui_ux"),
        ]),
    }

    update = engineering.ci_gate(state, CONFIG, None)

    (defect,) = update["review_defects"]
    assert "acceptance: [AC-1] adds" in defect.description and "before this batch" in defect.description


def test_a_test_round_s_defects_about_a_later_sprint_are_not_fixed_in_this_one(workspace) -> None:
    """One run's sprint 1 owned AC-1 and passed it; its round reported ten
    defects, each a later sprint's work, and its fix stages began building them."""
    from app.agents.specialists import ReportedDefect
    from app.graph.workflow import _defects_a_later_sprint_builds

    state = {
        "repository": SimpleNamespace(root_path=str(workspace.root)),
        "sprint_plan": SimpleNamespace(sprints=[
            SimpleNamespace(goal="Add and keep notes", criteria=["AC-1"], in_scope=[], out_of_scope=[]),
            SimpleNamespace(goal="Delete notes", criteria=["AC-2"], in_scope=[], out_of_scope=[]),
        ]),
        "current_sprint_index": 0,
    }

    def defect(description: str, steps: str = "") -> ReportedDefect:
        return ReportedDefect(
            description=description, severity="blocking", reproduction_steps=steps,
            expected_behavior="", actual_behavior="", affected_files=[], owner="ui_ux",
        )

    later_by_id = defect("Missing control", "Run the suite; [AC-2] removes a note fails")
    later_by_action = defect("Missing a way to delete notes")
    due = defect("A note added is not shown", "Run the suite; [AC-1] adds a note fails")
    unrelated = defect("The page throws on load")

    kept, moved = _defects_a_later_sprint_builds([later_by_id, later_by_action, due, unrelated], state)

    assert moved == [later_by_id, later_by_action]
    assert kept == [due, unrelated]


def test_without_later_sprints_every_defect_is_kept(workspace) -> None:
    from app.agents.specialists import ReportedDefect
    from app.graph.workflow import _defects_a_later_sprint_builds

    state = {
        "repository": SimpleNamespace(root_path=str(workspace.root)),
        "sprint_plan": SimpleNamespace(sprints=[
            SimpleNamespace(goal="Add and delete notes", criteria=["AC-1", "AC-2"], in_scope=[], out_of_scope=[]),
        ]),
        "current_sprint_index": 0,
    }
    item = ReportedDefect(
        description="Missing a way to delete notes", severity="blocking", reproduction_steps="[AC-2]",
        expected_behavior="", actual_behavior="", affected_files=[], owner="ui_ux",
    )

    assert _defects_a_later_sprint_builds([item], state) == ([item], [])


def test_the_round_filters_before_the_due_criteria_backstop() -> None:
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)
    assert source.index("_defects_a_later_sprint_builds(reported, state)") < source.index(
        "acceptance_nodes.failing_due_defects(state, reported)"
    )


def test_a_review_finding_nothing_shows_is_advice(workspace, monkeypatch) -> None:
    """See `test_a_review_finding_needs_evidence`: an unshown finding is advice, not a defect."""
    from app.agents.code_reviewer import CodeReviewFinding, CodeReviewOutput

    engineering.accepted_state(str(workspace.root))
    (workspace.root / "notes" / "src" / "notes.js").write_text("export function add(t) { return t; }\n")
    ci.commit(workspace.root, "batch")
    review = CodeReviewOutput(approved=False, findings=[
        CodeReviewFinding(work_order="Add notes", severity="blocking", file="notes/src/notes.js",
                          problem="add() does not sanitize its input", fix="escape it"),
    ])
    monkeypatch.setattr("app.graph.workflow._run_gated_agent",
                        lambda state, config, **kw: {kw["output_key"]: review, "stage": "code_review"})
    monkeypatch.setattr("app.agents.code_reviewer.create_code_reviewer_agent", lambda *a, **k: object())
    state = {
        "repository": SimpleNamespace(root_path=str(workspace.root)),
        "milestone_plan": SimpleNamespace(delegated_tasks=[
            SimpleNamespace(title="Add notes", task_description="Add a note", specialist_role="backend"),
        ]),
        "review_defects": [],
    }

    update = engineering.code_review(state, CONFIG, SimpleNamespace(
        judgement_model=None, checkpointer=None, repo_root=None, allow_subdirectories=True,
    ))

    assert update["review_defects"] == []
    assert update["review_advice"] == ["notes/src/notes.js: add() does not sanitize its input Suggested: escape it"]
def test_the_code_review_is_told_not_to_repeat_reads() -> None:
    from app.agents.code_reviewer import _SYSTEM_PROMPT
    assert "do not repeat a tool call" in _SYSTEM_PROMPT.lower()


def test_fast_delivery_leaves_the_code_review_to_the_tests(workspace, monkeypatch) -> None:
    """Only a finding a test or check shows became a defect; one run's review took
    16 minutes of a frontier model and raised one finding, advice."""
    from app import delivery

    engineering.accepted_state(str(workspace.root))
    (workspace.root / "notes" / "src" / "notes.js").write_text("export function remove() { return []; }\n")
    ci.commit(workspace.root, "batch")
    reviewed: list[Any] = []
    monkeypatch.setattr("app.graph.workflow._run_gated_agent", lambda *a, **k: reviewed.append(k) or {})
    monkeypatch.setattr("app.agents.code_reviewer.create_code_reviewer_agent", lambda *a, **k: object())
    monkeypatch.setattr(delivery, "fast", lambda environment=None: True)
    state = {"repository": SimpleNamespace(root_path=str(workspace.root)), "review_defects": []}

    update = engineering.code_review(state, CONFIG, SimpleNamespace(
        judgement_model=None, checkpointer=None, repo_root=None, allow_subdirectories=True))

    assert update["stage"] == "test_and_triage" and reviewed == []


def test_revert_note_contains_no_banned_words() -> None:
    import re
    from app.graph.workflow import _noted_as_reverted
    from app.sprint import RemediationCycle, Defect

    cycle = RemediationCycle(sprint_goal="goal", defects=[Defect(
        description="d", severity="major", reproduction_steps="",
        expected_behavior="", actual_behavior="initially failed",
        owner="ui_ux",
    )])
    updated = _noted_as_reverted(cycle, [0], ["unit: tests/app.test.js › sample"])
    text = updated.defects[0].actual_behavior
    banned = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")
    for word in banned:
        assert not re.search(rf"\b{re.escape(word)}\b", text, re.IGNORECASE), f"Banned word {word!r} found in revert note: {text}"
