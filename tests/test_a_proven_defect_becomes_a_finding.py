"""A defect the harness can demonstrate must not depend on a model restating it.

`summarise_integration` grades every cross-file problem it finds and puts the
worst tier in front of the milestone reviewer under a heading that says, in the
harness's own words, that each one "means a feature DOES NOT WORK" and "is a
blocking finding unless you can show it is not". Then it renders them into a
paragraph, and the only thing that can turn them into work is the reviewer
choosing to write them into `findings`.

Measured on one run. Three problems graded `BREAKS`, one of them

    simple-to-do-list-app/index.html references `style.css`, which does not
    exist in the workspace.

went into the review as evidence. The review came back `changes_required` with
that defect restated in prose and `findings: []`. `findings` is what the
workflow routes on and what the technical lead delegates from, so none of the
three became a task. The lead was handed the same paragraph three times, the
run reached `MAX_MILESTONE_REVISIONS` and failed, and the stylesheet was still
missing - confirmed against the stored workspace, which has no `style.css` at
all.

The existing answer to an empty `findings` is two fresh re-reviews and then the
prose. This adds a step before the prose: the harness raises the findings it can
prove itself. A reference either resolves against the filesystem or it does not,
and that is true whether or not a model agrees to write it down.

Only ever reached where the reviewer has already asked for changes, so it can
neither fail a sprint that was accepted nor invent a reason to revise one.
"""

from __future__ import annotations

import pytest

from app.agents.milestone_reviewer import (
    MAX_PROVEN_FINDINGS,
    MilestoneReviewFinding,
    MilestoneReviewOutput,
    findings_for_what_the_checks_proved,
    _files_named_in,
)
from app.analysis.integration_checks import problems_that_break_the_product


A_PAGE_MISSING_ITS_STYLESHEET = """<!doctype html>
<html>
<head><link rel="stylesheet" href="style.css"></head>
<body><ul id="tasks"></ul><script type="module" src="./app.js"></script></body>
</html>
"""


@pytest.fixture
def a_workspace(tmp_path):
    """The shape of one run's product: a page linking a file nobody wrote."""
    project = tmp_path / "todo-app"
    project.mkdir()
    (project / "index.html").write_text(A_PAGE_MISSING_ITS_STYLESHEET)
    (project / "app.js").write_text(
        "export function addTask(t) { document.getElementById('tasks').textContent = t; }\n"
    )
    return tmp_path


class TestWhatTheChecksCanProve:
    def test_a_reference_to_a_file_that_is_not_there_is_proven(self, a_workspace):
        problems = problems_that_break_the_product(a_workspace, "javascript", "")

        assert any("style.css" in problem for problem in problems), problems

    def test_the_untidy_tier_is_left_out(self, a_workspace):
        """Only the tier the harness itself calls broken becomes a blocking finding.

        Several checks in the registry are judgement - a dead CSS rule, an
        export no test mentions. Raising those as blocking would fail sprints
        over tidiness, which is the failure `_findings_that_block` exists to
        prevent.
        """
        problems = problems_that_break_the_product(a_workspace, "javascript", "")

        assert not any("no test mentions" in problem for problem in problems), problems

    def test_a_workspace_that_cannot_be_read_proves_nothing(self, tmp_path):
        """This runs on an error path; a second failure there is worse."""
        assert problems_that_break_the_product(tmp_path / "not-a-directory") == []

    def test_an_empty_workspace_proves_nothing(self, tmp_path):
        assert problems_that_break_the_product(tmp_path) == []


class TestTheFindingsTheHarnessRaises:
    def test_the_missing_stylesheet_becomes_a_blocking_finding(self, a_workspace):
        """The finding one run never got."""
        findings = findings_for_what_the_checks_proved(a_workspace, "javascript", "")

        missing = [f for f in findings if "style.css" in f.description]
        assert missing, [f.description for f in findings]
        assert missing[0].severity == "blocking"
        assert missing[0].category == "correctness"

    def test_the_finding_names_the_files_so_it_can_be_delegated(self, a_workspace):
        """`affected_files` is what scopes a specialist's work.

        A finding with no files is a finding the lead has to guess at, which is
        the prose problem again one level down.
        """
        findings = findings_for_what_the_checks_proved(a_workspace, "javascript", "")
        missing = next(f for f in findings if "style.css" in f.description)

        assert any(name.endswith("index.html") for name in missing.affected_files)
        assert "style.css" in missing.affected_files

    def test_the_remediation_says_restating_it_will_not_clear_it(self, a_workspace):
        """The reviewer wrote this defect down twice and it survived both times.

        A remediation that only says "fix it" invites another round of prose
        about it. This one says why the finding cannot be argued away.
        """
        findings = findings_for_what_the_checks_proved(a_workspace, "javascript", "")

        assert findings
        assert "until the files change" in " ".join(
            f.required_remediation for f in findings
        )

    def test_a_sound_workspace_raises_nothing(self, a_workspace):
        """The one property that matters for every run that is going fine."""
        (a_workspace / "todo-app" / "style.css").write_text("#tasks { padding: 1rem; }\n")

        findings = findings_for_what_the_checks_proved(a_workspace, "javascript", "")

        assert not [f for f in findings if "style.css" in f.description]

    def test_the_number_raised_at_once_is_capped(self, tmp_path, monkeypatch):
        """A lead handed thirty findings cannot act on them in one revision.

        The rest are not lost: the checks that found them still find them at
        the next review.
        """
        many = [f"page{index}.html references `gone{index}.css`." for index in range(30)]
        monkeypatch.setattr(
            "app.analysis.integration_checks.problems_that_break_the_product",
            lambda *args, **kwargs: many,
        )

        findings = findings_for_what_the_checks_proved(tmp_path)

        assert len(findings) == MAX_PROVEN_FINDINGS

    def test_a_problem_naming_no_file_is_still_raised(self, tmp_path, monkeypatch):
        """`affected_files` is optional, and a finding is worth more than a file."""
        monkeypatch.setattr(
            "app.analysis.integration_checks.problems_that_break_the_product",
            lambda *args, **kwargs: ["No test covers editing a task."],
        )

        findings = findings_for_what_the_checks_proved(tmp_path)

        assert len(findings) == 1
        assert findings[0].affected_files == []


class TestReadingFilesOutOfAProblemSentence:
    @pytest.mark.parametrize("problem, expected", [
        (
            "todo-app/index.html references `style.css`, which does not exist.",
            ["todo-app/index.html", "style.css"],
        ),
        ("src/main.jsx is loaded by nothing at all.", ["src/main.jsx"]),
        ("No test names `edit`, which the documents require.", []),
        ("app.js and app.test.mjs disagree.", ["app.js", "app.test.mjs"]),
    ])
    def test_the_paths_a_sentence_names(self, problem, expected):
        assert _files_named_in(problem) == expected

    def test_a_file_named_twice_is_listed_once(self):
        assert _files_named_in("app.js imports app.js") == ["app.js"]


class TestWhatTheLeadReceives:
    def test_the_revision_request_becomes_tasks_rather_than_a_paragraph(
        self, a_workspace
    ):
        """End to end on the text the technical lead is actually sent.

        Without findings, `_milestone_changes_requested` falls back to the
        reviewer's prose under "It recorded no structured findings" - what
        one run's lead got three times. With them it renders one line per
        defect in the severity/category/remediation form the lead delegates from.
        """
        from app.graph.workflow import _milestone_changes_requested

        prose = MilestoneReviewOutput(
            status="changes_required",
            findings=[],
            acceptance_evidence="Reviewed the project files: the stylesheet is missing.",
            documentation_reviewed=True,
            tests_reviewed=True,
        )
        assert "recorded no structured findings" in _milestone_changes_requested(prose)

        proven = prose.model_copy(
            update={
                "findings": findings_for_what_the_checks_proved(
                    a_workspace, "javascript", ""
                )
            }
        )
        text = _milestone_changes_requested(proven)

        assert "recorded no structured findings" not in text
        assert "[blocking] correctness:" in text
        assert "style.css" in text

    def test_the_proven_findings_gate_the_sprint(self, a_workspace):
        """They must reach `_findings_that_block`, or nothing changes.

        `changes_required` over findings none of which gate falls through to the
        accepted path. A proven broken reference that did that would be worse
        than the prose: it would read as approval.
        """
        from app.graph.workflow import _findings_that_block

        review = MilestoneReviewOutput(
            status="changes_required",
            findings=findings_for_what_the_checks_proved(a_workspace, "javascript", ""),
            acceptance_evidence="checked",
            documentation_reviewed=True,
            tests_reviewed=True,
        )

        assert _findings_that_block(review, str(a_workspace))

    def test_every_raised_finding_validates_against_the_schema(self, a_workspace):
        """A finding the model would have been rejected for is not usable either.

        `severity` and `category` are constrained Literals with forgiving
        validators, and the workflow puts this object where a model's own answer
        goes - into state, into `docs/milestone_review.md`, into the revision
        request. It has to be the same shape.
        """
        findings = findings_for_what_the_checks_proved(a_workspace, "javascript", "")

        assert findings
        for finding in findings:
            assert isinstance(finding, MilestoneReviewFinding)
            MilestoneReviewFinding.model_validate(finding.model_dump())


class TestWhereTheWorkflowAsks:
    def test_the_fallback_proves_before_it_settles_for_prose(self):
        """Order matters: the prose fallback must be the last resort, not the first.

        Checked on the source because the node is a closure over the compiled
        graph and cannot be called on its own. What is asserted is the ordering
        the fix depends on - the proving happens after the retries are spent and
        before the revision count that ends the run is incremented.
        """
        import inspect

        from app.graph import workflow

        source = inspect.getsource(workflow)
        start = source.index("Milestone review still has no structured findings")
        end = source.index(
            'revision_count = state.get("milestone_revision_count", 0) + 1', start
        )
        fallback = source[start:end]

        assert "findings_for_what_the_checks_proved" in fallback
        assert "model_copy" in fallback, "the review must carry the findings onward"
        assert "_milestone_changes_requested" in fallback, "the text must be re-rendered"
