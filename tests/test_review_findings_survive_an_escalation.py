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


def test_the_words_the_review_and_the_release_add_use_none_of_the_banned_ones() -> None:
    from app.agents.code_reviewer import ONE_CALL_SYSTEM_PROMPT, CodeReviewFinding
    from app.graph.review_after_escalation import known_issues

    finding = CodeReviewFinding(work_order="w", severity="major", file="a.js", problem="p")
    texts = [ONE_CALL_SYSTEM_PROMPT, *known_issues([finding], []), *known_issues([finding], ["a.js"]),
             completion_verdict.OPEN_REVIEW_FINDING, completion_verdict.REVIEW_FINDING_GIVEN_A_FIX]
    assert not [text for text in texts if BANNED.search(text)]
