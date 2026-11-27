"""Review findings survive an escalation (PQ.4).

A sprint the escalation accepted went on to the next sprint or the release with no code, milestone or security review
read: across 146 scored runs, 82 such sprints shipped code no review read, and on the 2026-11-25 product-quality audit
(cause C3) a code review's major findings on such a sprint reached neither a fixer nor the release, which read as plain
delivered. The review is now asked once, its major findings get one fix pass, and those still open are named at
release as known defects.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from app import ci, completion_verdict
from app.acceptance import suite
from app.acceptance.criteria import number
from app.graph import delivery, escalation
from app.stacks import pack_named
from app.stacks.scaffold import scaffold
from app.tools.version_control import initialise_repository

PACK = pack_named("browser-javascript")
CONFIG = {"configurable": {"thread_id": "t"}}
BRIEF = "# Brief\n## Features\n- Add a note\n- Delete a note\n"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
PRODUCT_FILE = "notes/src/notes.js"


class Runner:
    """Writes the report each test command would have written; outcomes are set per test."""

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


class Judge:
    """The judgement model: answers the one review call with `findings`, and counts the calls."""

    def __init__(self, findings: list[dict[str, Any]]) -> None:
        self.findings = findings
        self.calls = 0

    def invoke(self, messages, **kwargs):
        self.calls += 1
        return AIMessage(content=json.dumps({"approved": not self.findings, "findings": self.findings}))


class Builder:
    """The build model: rewrites the file it is asked for with `content`, and runs `then` after."""

    def __init__(self, content: str, then=lambda: None) -> None:
        self.content, self.then, self.calls = content, then, 0

    def invoke(self, messages, **kwargs):
        self.calls += 1
        self.then()
        return AIMessage(content=f"```js\n{self.content}```")


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
    # The last accepted sprint, then the sprint the escalation accepts: one change to the product.
    from app.graph import engineering

    engineering.accepted_state(str(tmp_path))
    (tmp_path / PRODUCT_FILE).write_text("export function remove(notes, id) { return []; }\n")
    ci.commit(tmp_path, "the stuck sprint's work")
    ci.save(tmp_path, ci.take(tmp_path, "after the stuck sprint"))
    return SimpleNamespace(root=tmp_path, runner=runner)


def _accepted(root: Path, judge: Any, builder: Any) -> dict[str, Any]:
    state = {
        "repository": SimpleNamespace(root_path=str(root)),
        "escalation": {"error": "Sprint 'Delete notes' exhausted its remediation attempts with defects still open."},
        "milestone_plan": SimpleNamespace(delegated_tasks=[
            SimpleNamespace(title="Delete notes", task_description="Remove a note", specialist_role="frontend"),
        ]),
        "review_policy": {},
        "decisions": [],
    }
    ctx = SimpleNamespace(judgement_model=judge, the_build_model=lambda state, stage, **kwargs: builder)
    return escalation.accept(state, CONFIG, ctx)


MAJOR = {"work_order": "Delete notes", "severity": "major", "file": PRODUCT_FILE,
         "problem": "remove() returns an empty list and drops every note, not only the one asked for",
         "fix": "keep every note whose id differs"}


def test_a_major_finding_the_fix_pass_could_not_change_is_a_known_defect_at_release(workspace) -> None:
    judge = Judge([MAJOR])
    unchanged = (workspace.root / PRODUCT_FILE).read_text()

    update = _accepted(workspace.root, judge, Builder(unchanged))

    assert judge.calls == 1, "one review call, never more"
    (issue,) = [line for line in update["known_issues"] if PRODUCT_FILE in line]
    assert "remove() returns an empty list" in issue
    # As the release states it: the escalation's known issue, with the decision that accepted the sprint.
    accepted_at = delivery._accepted_at_an_escalation(update)
    gap = f"An escalation left this open ({accepted_at}): {issue}"
    assert completion_verdict.verdict([gap]) == completion_verdict.DELIVERED_WITH_KNOWN_DEFECTS
    assert not completion_verdict.is_blocking(gap)


def test_a_major_finding_gets_one_fix_pass_that_is_kept_when_nothing_breaks(workspace) -> None:
    builder = Builder("export function remove(notes, id) { return notes.filter((n) => n.id !== id); }\n")

    update = _accepted(workspace.root, Judge([MAJOR]), builder)

    assert builder.calls == 1, "one rewrite of the one file named"
    assert "notes.filter" in (workspace.root / PRODUCT_FILE).read_text()
    (issue,) = [line for line in update["known_issues"] if PRODUCT_FILE in line]
    gap = f"An escalation left this open (DR-1): {issue}"
    assert completion_verdict.verdict([gap]) == completion_verdict.DELIVERED, "a note: the pass changed its file"
    decision = update["decisions"][-1]
    assert "1 given one fix pass" in decision["decision"]


def test_a_fix_pass_that_breaks_what_passed_is_put_back_and_its_finding_stays_open(workspace) -> None:
    def breaks_adding() -> None:
        workspace.runner.acceptance = {"[AC-1] adds": "failed", "[AC-2] deletes": "failed"}

    before = (workspace.root / PRODUCT_FILE).read_text()
    builder = Builder("export function remove() { throw new Error('x'); }\n", then=breaks_adding)

    update = _accepted(workspace.root, Judge([MAJOR]), builder)

    assert (workspace.root / PRODUCT_FILE).read_text() == before
    (issue,) = [line for line in update["known_issues"] if PRODUCT_FILE in line]
    assert completion_verdict.is_a_known_defect(issue)


def test_a_review_that_read_the_sprint_is_not_reported_as_no_review(workspace, monkeypatch) -> None:
    monkeypatch.setattr("app.observability.transcript.read_transcript",
                        lambda run_id, kinds=None: [{"stage": "technical_lead"}, {"stage": "escalation"}])

    update = _accepted(workspace.root, Judge([]), Builder(""))

    assert delivery._code_no_review_read("run-x", update) == []
    assert not any(PRODUCT_FILE in line for line in update["known_issues"])


def test_a_finding_about_a_later_sprint_s_criterion_is_not_carried(workspace) -> None:
    later = {**MAJOR, "problem": "deleting is not built: AC-2 belongs to it"}
    plan = SimpleNamespace(sprints=[SimpleNamespace(goal="Add", criteria=["AC-1"]),
                                    SimpleNamespace(goal="Delete", criteria=["AC-2"])])
    from app.graph.review_after_escalation import major_findings
    from app.agents.code_reviewer import CodeReviewOutput
    from app.graph.acceptance_nodes import criteria_only_later

    state = {"repository": SimpleNamespace(root_path=str(workspace.root)), "sprint_plan": plan,
             "current_sprint_index": 0}
    review = CodeReviewOutput.model_validate({"approved": False, "findings": [later, MAJOR]})

    kept = major_findings(review, lambda text: criteria_only_later(state, text))

    assert [f.problem for f in kept] == [MAJOR["problem"]]


class DeploymentModel:
    """The deployment's default model, the one every stage builds when a run names none: it answers the one review
    call with `findings` and a whole-file rewrite with `content`, and counts each."""

    def __init__(self, findings: list[dict[str, Any]], content: str) -> None:
        self.findings, self.content = findings, content
        self.reviews = self.rewrites = 0

    def invoke(self, messages, **kwargs):
        from app.agents.code_reviewer import ONE_CALL_SYSTEM_PROMPT

        if str(getattr(messages[0], "content", "")) == ONE_CALL_SYSTEM_PROMPT:
            self.reviews += 1
            return AIMessage(content=json.dumps({"approved": False, "findings": self.findings}))
        self.rewrites += 1
        return AIMessage(content=f"```js\n{self.content}```")


def _accepted_on_a_local_run(root: Path, monkeypatch, deployment: DeploymentModel) -> dict[str, Any]:
    """`_accepted` as the worker builds a local run's graph: no run model and no judgement model named, so every
    model the context holds is None and a stage builds the deployment's default model itself."""
    from app.graph.context import GraphContext

    monkeypatch.setattr("app.models.build_default_chat_model", lambda *args, **kwargs: deployment)
    state = {
        "repository": SimpleNamespace(root_path=str(root)),
        "escalation": {"error": "Sprint 'Delete notes' exhausted its remediation attempts with defects still open."},
        "milestone_plan": SimpleNamespace(delegated_tasks=[
            SimpleNamespace(title="Delete notes", task_description="Remove a note", specialist_role="frontend"),
        ]),
        "review_policy": {},
        "decisions": [],
    }
    ctx = GraphContext(model=None, judgement_model=None, planning_model=None, building_model=None,
                       checkpointer=None, repo_root=None)
    return escalation.accept(state, CONFIG, ctx)


def test_a_local_run_with_no_judgement_model_named_still_has_the_sprint_reviewed(workspace, monkeypatch) -> None:
    """Measured on three runs of 2026-11-27: each accepted a sprint at an escalation and released "No review read the
    product's code"; no stored transcript holds the review's call, because a local run's context names no judgement
    model and the review was skipped on `None` instead of asking the deployment's model."""
    deployment = DeploymentModel([MAJOR], (workspace.root / PRODUCT_FILE).read_text())

    update = _accepted_on_a_local_run(workspace.root, monkeypatch, deployment)

    assert deployment.reviews == 1, "one review call, on the deployment's own model"
    (issue,) = [line for line in update["known_issues"] if PRODUCT_FILE in line]
    assert "remove() returns an empty list" in issue
    assert any(d["point"] == "code_review_after_escalation" for d in update["decisions"])


def test_a_local_run_s_major_finding_gets_its_one_fix_pass_on_the_deployment_s_model(workspace, monkeypatch) -> None:
    deployment = DeploymentModel([MAJOR], "export function remove(notes, id) { return notes.filter((n) => n.id !== id); }\n")

    update = _accepted_on_a_local_run(workspace.root, monkeypatch, deployment)

    assert deployment.rewrites == 1, "one rewrite of the one file named"
    assert "notes.filter" in (workspace.root / PRODUCT_FILE).read_text()
    assert "1 given one fix pass" in [d for d in update["decisions"]
                                      if d["point"] == "code_review_after_escalation"][0]["decision"]


def test_the_words_the_review_and_the_release_add_use_none_of_the_banned_ones() -> None:
    from app.agents.code_reviewer import ONE_CALL_SYSTEM_PROMPT, CodeReviewFinding
    from app.graph.review_after_escalation import USES_HEADING, known_issues

    finding = CodeReviewFinding(work_order="w", severity="major", file="a.js", problem="p")
    texts = [ONE_CALL_SYSTEM_PROMPT, *known_issues([finding], []), *known_issues([finding], ["a.js"]),
             *known_issues([finding], [], on_tests=True), USES_HEADING,
             completion_verdict.OPEN_REVIEW_FINDING, completion_verdict.REVIEW_FINDING_GIVEN_A_FIX,
             completion_verdict.REVIEW_FINDING_ON_TESTS]
    assert not [text for text in texts if BANNED.search(text)]


# --- The review's findings rest on the product, not on what the diff shows (LF.1645) ------------------------------
# Measured on its first live review: the diff held a stylesheet's change but not the unchanged entry file that
# imported it; a "blocking" finding called the import "not present in the provided changes", the fix pass added a
# second import, and a major finding about a unit test file's strength made a product whose hidden tests all passed
# "delivered with known defects".

STYLES = "notes/styles.css"
ENTRY = "notes/src/main.js"
TEST_FILE = "notes/tests/notes.test.js"


class RecordingJudge(Judge):
    """`Judge`, keeping the one request it was sent."""

    def invoke(self, messages, **kwargs):
        self.request = str(messages[-1].content)
        self.system = str(messages[0].content)
        return super().invoke(messages, **kwargs)


def _a_sprint_that_changed_the_stylesheet_and_a_test(root: Path) -> None:
    """The stuck sprint also changed the stylesheet the page links in an unchanged file, and a unit test file."""
    (root / STYLES).write_text(":root { --ink: #111; }\nbody { color: var(--ink); }\n")
    (root / TEST_FILE).parent.mkdir(parents=True, exist_ok=True)
    (root / TEST_FILE).write_text("import test from 'node:test';\ntest('renders the list', () => {});\n")
    ci.commit(root, "the stuck sprint's styling")
    ci.save(root, ci.take(root, "after the stuck sprint"))


NOT_IN_THE_DIFF = {"work_order": "Delete notes", "severity": "blocking", "file": ENTRY,
                   "problem": "The diff only shows a change to the stylesheet. The import of styles.css is not present "
                              "in the provided changes, so the page has none of its colours.",
                   "fix": "Add import './styles.css' to main.js."}
ON_A_TEST_FILE = {"work_order": "Delete notes", "severity": "major", "file": TEST_FILE,
                  "problem": "The work order specifies browser tests that check the page's colours; this file only "
                             "checks that the list renders.",
                  "fix": "Check the colours in a browser test."}


def test_the_review_is_shown_the_unchanged_lines_that_name_a_changed_file(workspace) -> None:
    _a_sprint_that_changed_the_stylesheet_and_a_test(workspace.root)
    judge = RecordingJudge([])

    _accepted(workspace.root, judge, Builder(""))

    assert 'notes/index.html:' in judge.request, "the unchanged page that links the stylesheet"
    assert '<link rel="stylesheet" href="styles.css">' in judge.request


def test_the_review_is_told_absence_from_the_diff_is_not_absence_from_the_product(workspace) -> None:
    judge = RecordingJudge([])

    _accepted(workspace.root, judge, Builder(""))

    assert "Absence from the diff is not absence from the product" in " ".join(judge.system.split())


def test_a_finding_the_product_s_files_contradict_gets_no_fix_pass_and_is_no_known_issue(workspace) -> None:
    _a_sprint_that_changed_the_stylesheet_and_a_test(workspace.root)
    before = (workspace.root / ENTRY).read_text()
    builder = Builder("import './styles.css';\n")

    update = _accepted(workspace.root, Judge([NOT_IN_THE_DIFF]), builder)

    assert builder.calls == 0, "no rewrite of a file to add what the product already has"
    assert (workspace.root / ENTRY).read_text() == before
    assert not [line for line in update["known_issues"] if ENTRY in line]
    decision = [d for d in update["decisions"] if d["point"] == "code_review_after_escalation"][0]
    assert "notes/index.html" in decision["rationale"], "the line that contradicts it is named"


def test_a_major_finding_on_the_product_s_own_tests_is_a_note_not_a_known_defect(workspace) -> None:
    _a_sprint_that_changed_the_stylesheet_and_a_test(workspace.root)
    # As measured: the fix pass left the test file as it was, so the finding stayed open.
    builder = Builder((workspace.root / TEST_FILE).read_text())

    update = _accepted(workspace.root, Judge([ON_A_TEST_FILE]), builder)

    (issue,) = [line for line in update["known_issues"] if TEST_FILE in line]
    assert "only checks that the list renders" in issue, "the reader is still told"
    gap = f"An escalation left this open ({delivery._accepted_at_an_escalation(update)}): {issue}"
    assert completion_verdict.verdict([gap]) == completion_verdict.DELIVERED
    assert builder.calls == 0, "a test file's strength is no defect of the product to rewrite"


def _finding(problem: str) -> Any:
    from app.agents.code_reviewer import CodeReviewFinding

    return CodeReviewFinding(work_order="w", severity="blocking", file="web/src/App.tsx", problem=problem)


SOURCES = {"web/src/main.tsx": "import './styles.css';\nimport { App } from './App.js';\n",
           "web/src/App.tsx": "import './index.css';\nexport function App() { return null; }\n"}


@pytest.mark.parametrize("problem", [
    "The required import of styles.css, which defines the tokens used by index.css, is not present in the provided "
    "changes.",
    "styles.css is never imported, so its tokens are undefined.",
    "App.tsx does not import styles.css.",
    "Missing import of styles.css in the page.",
])
def test_a_claim_that_a_file_is_not_imported_is_contradicted_by_the_line_that_imports_it(problem) -> None:
    from app.graph.review_after_escalation import contradicted

    assert contradicted(_finding(problem), SOURCES) == "web/src/main.tsx:1"


@pytest.mark.parametrize("problem", [
    "styles.css is imported, but its dark colours are not defined.",
    "The import of theme.css is not present anywhere, so the page has no theme.",
    "The title is required, and App.tsx has no check for an empty one.",
])
def test_a_finding_that_claims_no_absence_the_files_contradict_stands(problem) -> None:
    from app.graph.review_after_escalation import contradicted

    assert contradicted(_finding(problem), SOURCES) == ""
