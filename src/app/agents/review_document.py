"""Render a review's document from its decision, so the two cannot disagree.

Every reviewer used to be asked for the same information twice: once as a
Markdown artifact for a person to read, and once as a structured response for
the workflow to route on. Nothing reconciled them.

Observed on one run: the milestone reviewer wrote a complete four-row
findings table into `docs/milestone_review.md` - the root `package.json`
overriding the test script, duplicate CI installs, a wrong line-count path, a
README citing a script that does not exist - and returned
`MilestoneReviewOutput.findings == []`. The workflow routes on the structured
field, so it joined an empty list, sent the technical lead back to re-plan
against a revision request containing nothing, and failed the run after three
attempts. The findings existed the whole time; they were in the other copy.

The document is now generated from the decision. The reviewer returns one
thing, so there is nothing to keep in step - and the document a person reads is
by construction the one the workflow acted on.
"""

from __future__ import annotations

from typing import Any

from app.agents.severity import rank_of

#: Order findings are presented in, worst first. A reader scanning the table
#: should meet the blocking ones before the suggestions.
#: Worst first. This used to be a four-word table covering one reviewer's
#: vocabulary, so every security finding - critical, high, medium, low, info -
#: fell through to the default and the security table came out in whatever
#: order the model happened to list them, with the critical ones as likely last
#: as first. `app.agents.severity` ranks every vocabulary, which is the whole
#: reason it exists.
_UNRANKED = 9


def _severity_rank(finding: Any) -> int:
    rank = rank_of(getattr(finding, "severity", ""))
    return _UNRANKED if rank is None else rank


def _cell(text: Any) -> str:
    """One table cell: no raw pipe or newline may break the row."""
    return str(text or "").replace("|", "\\|").replace("\n", " ").strip() or "-"


def _findings_table(findings: list[Any], *, context_column: str, context_field: str) -> str:
    ordered = sorted(
        findings,
        key=_severity_rank,
    )
    rows = [
        f"| Severity | {context_column} | Description | Required remediation |",
        "|---|---|---|---|",
    ]
    for finding in ordered:
        rows.append(
            "| **{severity}** | {context} | {description} | {remediation} |".format(
                severity=_cell(getattr(finding, "severity", "")).title(),
                context=_cell(getattr(finding, context_field, "")),
                description=_cell(getattr(finding, "description", "")),
                remediation=_cell(getattr(finding, "required_remediation", "")),
            )
        )
    return "\n".join(rows)


def render_milestone_review(review: Any, milestone_goal: str) -> str:
    """The Markdown a person reads, built from the decision the workflow routes on."""
    findings = list(getattr(review, "findings", None) or [])
    status = str(getattr(review, "status", "") or "unknown")

    parts = [f"# Milestone Review: {milestone_goal or 'Milestone'}", ""]

    parts.append("## Findings")
    if findings:
        parts.append(
            _findings_table(findings, context_column="Category", context_field="category")
        )
    else:
        # Said plainly rather than left blank. A review that requires changes
        # and records no findings is the exact shape that failed one run,
        # and a reader should be able to see it in the document.
        parts.append(
            "No structured findings were recorded."
            if status == "accepted"
            else (
                "No structured findings were recorded. The account below is the "
                "only statement of what needs to change."
            )
        )
    parts.append("")

    parts.append("## Acceptance Evidence")
    parts.append(str(getattr(review, "acceptance_evidence", "") or "None recorded."))
    parts.append("")

    parts.append("## What Was Reviewed")
    parts.append(
        f"- Documentation reviewed: {'yes' if getattr(review, 'documentation_reviewed', False) else 'no'}"
    )
    parts.append(
        f"- Tests reviewed: {'yes' if getattr(review, 'tests_reviewed', False) else 'no'}"
    )
    parts.append("")

    parts.append(f"## Status: {status}")
    parts.append("")
    parts.append(
        "<!-- Generated from the reviewer's structured decision. Editing this "
        "file does not change the workflow's routing. -->"
    )
    return "\n".join(parts)


def render_architecture_review(review: Any) -> str:
    """The Markdown for a specification review, built from its decision.

    The architecture reviewer has the same two-copy structure the milestone
    reviewer had - a prose artifact and a schema, asked for separately. On
    one run the two happened to agree, which is luck rather than a
    property: nothing reconciles them, and the milestone reviewer's copies
    disagreed on one run badly enough to fail the run.

    Its findings carry `evidence` - the spec section or ADR - where a milestone
    finding carries `category`, so the table's middle column differs.
    """
    findings = list(getattr(review, "findings", None) or [])
    status = str(getattr(review, "status", "") or "unknown")

    parts = ["# Architecture Review", ""]

    parts.append("## Findings")
    if findings:
        parts.append(
            _findings_table(findings, context_column="Evidence", context_field="evidence")
        )
    else:
        parts.append(
            "No findings were recorded."
            if status == "approved"
            else (
                "No findings were recorded, so this review states no change for "
                "the architect to make."
            )
        )
    parts.append("")

    for heading, attribute, empty in (
        ("Approval Conditions", "approval_conditions", "None."),
        ("Accepted Risks", "accepted_risks", "None recorded."),
    ):
        parts.append(f"## {heading}")
        entries = list(getattr(review, attribute, None) or [])
        parts.extend([f"- {entry}" for entry in entries] if entries else [empty])
        parts.append("")

    parts.append(f"## Status: {status}")
    parts.append("")
    parts.append(
        "<!-- Generated from the reviewer's structured decision. Editing this "
        "file does not change the workflow's routing. -->"
    )
    return "\n".join(parts)


__all__ = ["render_architecture_review", "render_milestone_review"]
