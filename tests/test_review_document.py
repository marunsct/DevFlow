"""The review document and the review decision are one thing.

Every reviewer used to be asked for the same information twice - a Markdown
artifact for a person, a structured response for the router - with nothing
reconciling them.

Observed on run-95ca3f72: `docs/milestone_review.md` carried a complete
four-row findings table while `MilestoneReviewOutput.findings` was `[]`. The
workflow routes on the structured field, so it sent the technical lead back to
re-plan against an empty revision request and failed the run after three
attempts. The findings existed; they were in the other copy.
"""

from __future__ import annotations

from app.agents.review_document import render_milestone_review


class _Finding:
    def __init__(self, severity, category, description, remediation):
        self.severity = severity
        self.category = category
        self.description = description
        self.required_remediation = remediation


class _Review:
    def __init__(self, status="changes_required", findings=(), evidence="checked things"):
        self.status = status
        self.findings = list(findings)
        self.acceptance_evidence = evidence
        self.documentation_reviewed = True
        self.tests_reviewed = False


def test_every_finding_reaches_the_document():
    review = _Review(
        findings=[
            _Finding("minor", "docs", "README cites a missing script", "add it"),
            _Finding("blocking", "testing", "npm test exits 1", "fix the manifest"),
        ]
    )

    document = render_milestone_review(review, "Project Setup")

    assert "npm test exits 1" in document
    assert "README cites a missing script" in document
    assert "fix the manifest" in document


def test_the_worst_finding_is_listed_first():
    review = _Review(
        findings=[
            _Finding("suggestion", "style", "rename a variable", "rename it"),
            _Finding("blocking", "testing", "no tests ran", "run them"),
        ]
    )

    document = render_milestone_review(review, "Sprint 1")

    assert document.index("no tests ran") < document.index("rename a variable")


def test_a_review_with_no_findings_says_so_rather_than_leaving_a_blank():
    """The shape that failed run-95ca3f72 must be visible in the document."""
    review = _Review(findings=[], evidence="the root package.json test script is exit 1")

    document = render_milestone_review(review, "Sprint 1")

    assert "No structured findings were recorded" in document
    assert "the root package.json test script is exit 1" in document


def test_the_status_is_the_one_the_workflow_routes_on():
    assert "## Status: changes_required" in render_milestone_review(_Review(), "x")
    assert "## Status: accepted" in render_milestone_review(_Review(status="accepted"), "x")


def test_a_pipe_in_a_finding_does_not_break_the_table():
    review = _Review(
        findings=[_Finding("major", "build", 'run `a | b`', "use\na pipeline")]
    )

    document = render_milestone_review(review, "x")
    table_rows = [line for line in document.splitlines() if line.startswith("| **")]

    assert len(table_rows) == 1
    # Four cells, so five unescaped delimiters. The pipe inside the finding is
    # escaped and therefore does not split a cell.
    assert table_rows[0].replace("\\|", "").count("|") == 5
    assert "\\|" in table_rows[0]


def test_what_was_reviewed_is_recorded():
    document = render_milestone_review(_Review(), "x")

    assert "Documentation reviewed: yes" in document
    assert "Tests reviewed: no" in document


def test_the_reviewer_is_not_told_to_write_a_document():
    """It wrote the findings into the artifact and returned an empty schema."""
    from app.agents.milestone_reviewer import _SYSTEM_PROMPT

    assert "write_artifact" not in _SYSTEM_PROMPT
    assert "Do not write a review document" in _SYSTEM_PROMPT


class _ArchFinding:
    def __init__(self, severity, description, evidence, remediation):
        self.severity = severity
        self.description = description
        self.evidence = evidence
        self.required_remediation = remediation


class _ArchReview:
    def __init__(self, status="changes_required", findings=(), conditions=(), risks=()):
        self.status = status
        self.findings = list(findings)
        self.approval_conditions = list(conditions)
        self.accepted_risks = list(risks)


def test_the_architecture_review_document_carries_its_findings():
    """Same two-copy structure as the milestone review; on run-c4f17841 the
    copies happened to agree, which is luck rather than a property."""
    from app.agents.review_document import render_architecture_review

    review = _ArchReview(
        findings=[
            _ArchFinding("blocking", "CI workflow is not present", "ADR-07", "add one"),
            _ArchFinding("minor", "naming is inconsistent", "section 4", "rename"),
        ],
        conditions=["migrations reviewed before release"],
        risks=["no rate limiting in the MVP"],
    )

    document = render_architecture_review(review)

    assert "CI workflow is not present" in document
    assert "ADR-07" in document
    assert document.index("CI workflow") < document.index("naming is inconsistent")
    assert "migrations reviewed before release" in document
    assert "no rate limiting in the MVP" in document
    assert "## Status: changes_required" in document


def test_the_architecture_table_column_is_evidence_not_category():
    """Its findings carry `evidence`; a milestone finding carries `category`."""
    from app.agents.review_document import render_architecture_review

    document = render_architecture_review(
        _ArchReview(findings=[_ArchFinding("major", "d", "ADR-03", "r")])
    )

    assert "| Severity | Evidence | Description | Required remediation |" in document


def test_an_architecture_review_with_no_findings_says_so():
    from app.agents.review_document import render_architecture_review

    document = render_architecture_review(_ArchReview(status="changes_required"))

    assert "states no change" in document


def test_the_architecture_reviewer_is_not_told_to_write_a_document():
    from app.agents.architecture_reviewer import _SYSTEM_PROMPT

    assert "docs/architecture_review.md`. Use that path verbatim" not in _SYSTEM_PROMPT
    assert "Do not write a review document" in _SYSTEM_PROMPT


def test_a_reviewer_whose_document_is_generated_holds_no_write_tool():
    """Telling it not to write was not enough; it kept the tool and used it.

    Measured on run-c826ae90: the architecture reviewer was instructed "Do not
    write a review document", still held `write_artifact`, and wrote
    `docs/architecture_review.md` five times in a row - printing its structured
    response into the conversation as prose between each write and never
    returning it - until the repeat guard stopped the stage.

    Removing the instruction that used to close the prompt ("once the write is
    confirmed, immediately return your structured response") took away the cue
    that told it when to stop. Both halves are fixed: no write tool, and an
    explicit instruction to return the response rather than print it.
    """
    import inspect

    from app.agents import architecture_reviewer, milestone_reviewer

    for module in (architecture_reviewer, milestone_reviewer):
        source = inspect.getsource(module)
        assert "can_write=False" in source, module.__name__


def test_both_reviewers_are_told_to_return_rather_than_print():
    from app.agents.architecture_reviewer import _SYSTEM_PROMPT as arch
    from app.agents.milestone_reviewer import _SYSTEM_PROMPT as milestone

    for prompt in (arch, milestone):
        flat = " ".join(prompt.split())
        assert "You have no write tool and need none" in flat
        assert "a response written into the conversation is not returned" in flat


def test_a_role_that_can_write_still_gets_its_tools():
    """Every other role writes artifacts and must keep the tool."""
    import inspect

    from app.agents.role_agent import create_role_agent

    assert inspect.signature(create_role_agent).parameters["can_write"].default is True


def test_every_reviewer_is_read_only():
    """A reviewer's decision is its output; a document it writes is a second
    copy that can disagree with the one the workflow routes on.

    The security reviewer was the last one still holding a write tool with no
    rendered document of its own. It had never misbehaved - neither had the
    stack selector, until run-0b18e403 ended at stage three when it finally
    used the tool it had always had.
    """
    import inspect

    from app.agents import architecture_reviewer, milestone_reviewer, security_reviewer

    for module in (architecture_reviewer, milestone_reviewer, security_reviewer):
        assert "can_write=False" in inspect.getsource(module), module.__name__


def test_every_review_has_a_rendered_document():
    """If the agent cannot write one, the workflow must produce one, or the
    review leaves no record a person can read."""
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)

    for document in (
        "docs/architecture_review.md",
        "docs/security_review.md",
    ):
        assert document in source, document
