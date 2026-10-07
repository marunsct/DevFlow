"""Builders were never told which locked tests belong to later sprints.

QA locks the acceptance suite for the whole product before the first sprint.
Measured on one run, whose sprint plan gave sprint 1 four criteria and deferred
editing, deleting, completing and filtering to sprint 2 by name: sprint 1's
backend specialist's first write already held all of them, it then spent thirty
minutes and a restart making seven later sprints' failing tests pass, and the
milestone review asked for that work to be taken out again over the size limit.

Every place a stage met the suite said "this is your work": the request, the
workspace listing ("read it for what the product must do"), the opening
snapshot (two later sprints' files inlined in full) and a test command's result
(their failures beside this sprint's). Each now says which tests are a later
sprint's.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.acceptance import sprint_scope, suite
from app.acceptance.criteria import Criterion
from app.agents.project_snapshot import project_snapshot
from app.agents.specialists import build_specialist_task_request
from app.tools.sandbox import SandboxExecutor

PROJECT = "notes"

CRITERIA = [
    Criterion("AC-1", "Notes can be added with a heading", "brief"),
    Criterion("AC-2", "An empty heading is rejected", "brief"),
    Criterion("AC-3", "A note can be renamed", "brief"),
    Criterion("AC-4", "Notes survive a reload", "brief"),
]

ADDING = """import { test } from '@playwright/test';
test('[AC-1] a note is added', async () => {});
test('[AC-2] an empty heading is rejected', async () => {});
"""

RENAMING = """import { test } from '@playwright/test';
// RENAMING-BODY
test('[AC-3] a note is renamed', async () => {});
"""

MIXED = """import { test } from '@playwright/test';
test('[AC-2] the error clears', async () => {});
test('[AC-4] notes survive a reload', async () => {});
"""


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / ".project-directory").write_text(f"{PROJECT}\n")
    harness = tmp_path / ".harness"
    harness.mkdir()
    (harness / "stack-pack.json").write_text(json.dumps({
        "pack": "any",
        "project": PROJECT,
        "acceptance_dir": "acceptance",
        "unit_report": "test-results/unit.xml",
        "acceptance_report": "test-results/acceptance.xml",
    }))
    suite_dir = tmp_path / PROJECT / "acceptance"
    suite_dir.mkdir(parents=True)
    (suite_dir / "adding.spec.js").write_text(ADDING)
    (suite_dir / "renaming.spec.js").write_text(RENAMING)
    (suite_dir / "mixed.spec.js").write_text(MIXED)
    (tmp_path / PROJECT / "app.js").write_text("export function add() { return 1; }\n")
    suite.save_criteria(tmp_path, CRITERIA)
    suite.lock(tmp_path)
    return tmp_path


def _sprint_one(root: Path) -> None:
    sprint_scope.record(root, sprint=1, of=2, not_yet_due=["AC-3", "AC-4"])


def _report(root: Path, cases: list[tuple[str, bool]], name: str = "acceptance.xml") -> Path:
    body = "".join(
        f'<testcase name="{title}" classname="x">'
        + ("" if passed else '<failure message="no">no</failure>')
        + "</testcase>"
        for title, passed in cases
    )
    path = root / PROJECT / "test-results" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'<testsuites><testsuite name="s">{body}</testsuite></testsuites>')
    return path


class TestWhichFilesAreALaterSprints:
    def test_a_file_whose_every_test_is_later(self, root):
        _sprint_one(root)

        assert sprint_scope.later_sprints_files(root) == {
            f"{PROJECT}/acceptance/renaming.spec.js": ["AC-3"]
        }

    def test_a_file_that_also_tests_a_due_criterion_is_this_sprints(self, root):
        _sprint_one(root)

        assert f"{PROJECT}/acceptance/mixed.spec.js" not in sprint_scope.later_sprints_files(root)

    def test_nothing_is_later_without_a_record(self, root):
        assert sprint_scope.later_sprints_files(root) == {}
        assert sprint_scope.brief(root) == ""

    def test_the_last_sprint_owes_everything(self, root):
        sprint_scope.record(root, sprint=2, of=2, not_yet_due=[])

        assert sprint_scope.later_sprints_files(root) == {}
        assert sprint_scope.brief(root, deferred=["anything"]) == ""


class TestTheBuildersRequest:
    def test_it_names_the_sprint_and_each_later_criterion(self, root):
        _sprint_one(root)

        text = sprint_scope.brief(root)

        assert "sprint 1 of 2" in text
        assert "- AC-3: A note can be renamed" in text
        assert "- AC-4: Notes survive a reload" in text
        assert "AC-1" not in text

    def test_it_names_the_files_that_are_wholly_later(self, root):
        _sprint_one(root)

        assert "renaming.spec.js" in sprint_scope.brief(root)

    def test_it_carries_what_the_sprint_plan_leaves_out(self, root):
        _sprint_one(root)

        text = sprint_scope.brief(root, deferred=["Renaming a note (deferred to Sprint 2)"])

        assert "This sprint's plan leaves out:\n- Renaming a note (deferred to Sprint 2)" in text

    def test_it_says_a_later_failure_is_no_reason_to_change_code(self, root):
        _sprint_one(root)

        assert "never a reason to change code now" in sprint_scope.brief(root)

    def test_the_rule_names_no_product(self, root):
        """The harness's own words must suit any product, not the one it was measured on."""
        sprint_scope.record(root, sprint=1, of=2, not_yet_due=["AC-9"])

        text = sprint_scope.brief(root).lower()

        for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
            assert not re.search(rf"\b{re.escape(word)}\b", text), word

    def test_it_reaches_the_request_after_the_criteria(self, tmp_path):
        request = build_specialist_task_request(
            "Build the adding flow", ["AC-1: Notes can be added"], str(tmp_path),
            later_sprints_brief="--- What later sprints build - not this sprint's work ---\nX\n\n",
        )

        content = request["messages"][0]["content"]
        assert content.index("--- Acceptance criteria ---") < content.index("--- What later sprints build")


class TestATestCommandsResult:
    def test_every_failure_a_later_sprints(self, root):
        _sprint_one(root)
        since = time.time() - 1
        _report(root, [("[AC-1] a note is added", True), ("[AC-3] a note is renamed", False)])

        note = sprint_scope.note_on_failures(root, since)

        assert "Every failing test here (1)" in note
        assert "AC-3" in note
        assert "leave them failing" in note

    def test_some_failures_this_sprints(self, root):
        _sprint_one(root)
        since = time.time() - 1
        _report(root, [("[AC-1] a note is added", False), ("[AC-3] a note is renamed", False)])

        note = sprint_scope.note_on_failures(root, since)

        assert "1 of the 2 failing tests" in note
        assert "The other 1 are this sprint's" in note

    def test_only_this_sprints_failures_say_nothing(self, root):
        _sprint_one(root)
        since = time.time() - 1
        _report(root, [("[AC-1] a note is added", False)])

        assert sprint_scope.note_on_failures(root, since) == ""

    def test_a_report_from_an_earlier_command_is_not_read(self, root):
        _sprint_one(root)
        path = _report(root, [("[AC-3] a note is renamed", False)])
        old = time.time() - 600
        os.utime(path, (old, old))

        assert sprint_scope.note_on_failures(root, time.time() - 1) == ""

    def test_the_executor_adds_it_to_a_failed_command(self, root, monkeypatch):
        _sprint_one(root)

        def _run(cls, *args, **kwargs):
            _report(root, [("[AC-1] a note is added", True), ("[AC-3] a note is renamed", False)])
            return {"returncode": "1", "stdout": "1 failed", "stderr": ""}

        monkeypatch.setattr(SandboxExecutor, "_run", classmethod(_run))

        outcome = SandboxExecutor.execute(
            ["npm", "run", "test:acceptance"], str(root), "backend_specialist", "test",
            working_directory=PROJECT,
        )

        assert "a later sprint" in (outcome.get("note") or "")


class TestWhatAStageIsShown:
    def test_the_snapshot_holds_back_a_later_sprints_file(self, root):
        _sprint_one(root)

        text = project_snapshot(root)

        assert "RENAMING-BODY" not in text
        assert "renaming.spec.js (AC-3)" in text
        assert "[AC-1] a note is added" in text

    def test_without_a_record_the_snapshot_shows_it(self, root):
        assert "RENAMING-BODY" in project_snapshot(root)

    def test_the_listing_labels_a_later_sprints_file(self, root):
        from app.agents.workspace_digest import _entry_for

        _sprint_one(root)
        name = f"{PROJECT}/acceptance/renaming.spec.js"

        line = _entry_for(root, name, root / name, RENAMING)[0]

        assert "a later sprint builds (AC-3)" in line
        assert "read it for what the product must do" not in line

    def test_the_listing_keeps_the_label_of_a_file_due_now(self, root):
        from app.agents.workspace_digest import _entry_for

        _sprint_one(root)
        name = f"{PROJECT}/acceptance/adding.spec.js"

        line = _entry_for(root, name, root / name, ADDING)[0]

        assert "read it for what the product must do" in line


class TestTheWorkflowRecordsIt:
    def _state(self, root: Path, index: int) -> dict:
        sprints = [
            SimpleNamespace(criteria=["AC-1", "AC-2"], out_of_scope=["Renaming (deferred to Sprint 2)"]),
            SimpleNamespace(criteria=["AC-3", "AC-4"], out_of_scope=[]),
        ]
        return {
            "repository": SimpleNamespace(root_path=str(root)),
            "sprint_plan": SimpleNamespace(sprints=sprints),
            "current_sprint_index": index,
        }

    def test_sprint_one_records_what_it_does_not_owe(self, root):
        from app.graph.workflow import _the_later_sprints_brief

        text = _the_later_sprints_brief(self._state(root, 0))

        assert sprint_scope.not_yet_due(root) == ["AC-3", "AC-4"]
        assert "Renaming (deferred to Sprint 2)" in text

    def test_the_last_sprint_owes_everything(self, root):
        from app.graph.workflow import _the_later_sprints_brief

        _sprint_one(root)
        text = _the_later_sprints_brief(self._state(root, 1))

        assert sprint_scope.not_yet_due(root) == []
        assert text == ""
