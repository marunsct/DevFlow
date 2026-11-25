"""The QA lead who reviews the acceptance suite before it is locked.

The suite decides when the product is done, so a weak test is a weak definition
of done: a test that checks a heading exists "proves" a feature that was never
built. The harness has already checked what can be checked mechanically - every
criterion has a test, the suite runs, which tests pass before anything is built -
and hands that over. This reviewer judges what cannot be: whether each test
would fail if its criterion were not met.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents.role_agent import create_role_agent
from app.agents.severity import validator_for as severity_in
from app.agents.structured_response import STRUCTURED_RESPONSE_RULE
from app.acceptance.requests import TESTS_ASSUME_ONLY_WHAT_THEY_MADE  # one text for the writer and its reviewer

_NAME = "acceptance_reviewer"
_STAGE = "acceptance"


#: The QA lead's severities, the milestone reviewer's words (`app.agents.severity`). Blocking and major gate: in thorough
#: delivery a suite is not locked with one open (`app.graph.suite_gate`).
SEVERITIES = ("blocking", "major", "minor", "suggestion")


class AcceptanceReviewFinding(BaseModel):
    """One problem with the suite, and how much it matters."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(
        ...,
        description=(
            "The problem, starting with the criterion id it concerns (\"AC-3: the test only checks the list "
            "exists; it never checks the item was removed\")."
        ),
    )
    # Absent, the finding locks at the round limit as every finding did before severities (TG.2).
    severity: Literal["blocking", "major", "minor", "suggestion"] = Field(
        default="minor", description="How much the problem matters; see the rule on severities."
    )
    _known_severity = field_validator("severity", mode="before")(severity_in(*SEVERITIES))

    def __str__(self) -> str:
        return self.description


class AcceptanceReviewOutput(BaseModel):
    """Whether the suite is a fair definition of done, and what is wrong if not."""

    model_config = ConfigDict(extra="forbid")

    approved: bool = Field(
        ...,
        description=(
            "True when every criterion's tests would fail if that criterion were not met. "
            "False when any test is too weak, tests the wrong thing, or is missing."
        ),
    )
    findings: list[AcceptanceReviewFinding] = Field(
        default_factory=list,
        description="One entry per problem, each with its severity. Empty when approved.",
    )

    @field_validator("findings", mode="before")
    @classmethod
    def _a_line_is_a_finding(cls, value: Any) -> Any:
        """A finding written as one line, as the schema once asked, is that finding at the default severity."""
        if not isinstance(value, list):
            return value
        return [{"description": item} if isinstance(item, str) else item for item in value]


#: How the QA lead grades each finding (TG.2): what a finding breaks, not how much there is to change.
SEVERITY_RULE = """Give every finding a severity, by what it breaks in the definition of done:
- blocking: no product could pass the test - it contradicts another test,
  asserts something no correct product does, or stops the suite from finishing;
- major: a criterion whose tests would still pass if the product did not meet
  it, or a criterion with no test;
- minor: a test that checks the right result less closely than it could;
- suggestion: anything else worth saying.
A blocking or major finding can keep the suite from being locked until it is
resolved, so give those two only to what makes passing the suite a wrong
measure of done."""


_SYSTEM_PROMPT = f"""You are the QA lead reviewing an acceptance suite before it is locked.

The suite is the product's definition of done: once locked, the product is
finished when these tests pass, and nobody may change them. Your job is to make
sure passing them means the criteria are really met.

Where the brief states the interface - labels, endpoints, commands, names -
a test must use exactly those; a test that invents its own does not check what
the customer will. For each criterion, read the tests whose names carry its id
and ask one question: if the product did not do this - the feature missing, half-built, or
wrong - would one of these tests fail? A test that only checks something
exists, checks a value the test itself set, or would pass on an empty product is
not enough. A test that checks the result a user would see is.

Where the brief's interface says what kind of thing a record is shown as - an
item of a list, a row of a table, an element of a returned array - check that
the tests find records that way. A suite that finds them by any shape passes a
product that ignores the one the customer named.

Where the brief has a view that shows only the records in some state, check that
a test changes a record's state while that view is shown and expects the record
to leave or join it at once. A suite that only checks each view as it is first
chosen passes a product whose views go stale the moment a record changes.

Then ask the opposite: could a product that does meet the criterion pass it?
{TESTS_ASSUME_ONLY_WHAT_THEY_MADE}

Then read the tests side by side. Two tests that take the same steps must expect
the same result: one that expects the newest record first and another that
expects the oldest first cannot both pass, whatever is built. A test may assert
only what its criterion states - an order, a count, a wording - and nothing the
criterion leaves open. Name every pair of tests whose expectations contradict,
and every test that asserts something its criterion leaves open.

A test must never start a product that keeps running - a service, or the server
a page is served from - itself: the suite's own setup starts it before the tests
and stops it after, and a test that runs its start command waits for a process
that never ends, so the whole suite stops there with no result for any test.
Name every test that does, and ask for it to check the running product instead.
A program that runs and exits is run by its tests, as its user runs it.

{SEVERITY_RULE}

Do not ask for style changes, more comments, or tests of things no criterion
asks for. Do not judge the product: whatever part of it is built, it is not the
standard, and tests of later features are expected to fail now. Never open its
files, even one a test imports, to decide what a test should expect.

Read the test files with your tools. Return `approved: true` only when every
criterion that is not deferred is properly tested.

{STRUCTURED_RESPONSE_RULE}"""


def build_acceptance_review_request(
    criteria_text: str,
    suite_text: str,
    run_summary: str,
    already_passing: list[str],
    deferred_text: str,
    brief: str = "",
    testability: Sequence[str] = (),
) -> dict[str, list[dict[str, str]]]:
    passing = (
        "--- Tests that already pass, before anything is built ---\n"
        + "\n".join(f"- {name}" for name in already_passing)
        + "\nA test that passes on an empty product cannot fail when its feature is "
        "missing, unless the scaffold already does what it checks. Look at each.\n\n"
        if already_passing
        else ""
    )
    from app.acceptance import actions_within_a_view

    content = (
        "The workspace is rooted at '/'; all paths you use are relative to it.\n\n"
        + (f"--- The brief, as the customer wrote it ---\n{brief.strip()[:12_000]}\n\n" if brief.strip() else "")
        + f"--- Acceptance criteria ---\n{criteria_text}\n\n"
        f"{deferred_text}"
        + (
            "--- The testability advice the specification adopted ---\n"
            + "\n".join(f"- {' '.join(str(line).split())}" for line in testability if str(line).strip())
            + "\nA test that goes against an item here - finds a control by another name, acts "
            "on data it never created, confirms a control the action takes away - is a finding.\n\n"
            if any(str(line).strip() for line in testability or ())
            else ""
        )
        + f"--- The suite as written ---\n{suite_text}\n\n"
        f"--- What running it showed ---\n{run_summary}\n\n"
        f"{passing}"
        "Review the suite. For each criterion, would its tests fail if the product did "
        "not meet it?"
        + actions_within_a_view.review_rule()
    )
    return {"messages": [{"role": "user", "content": content}]}


def create_acceptance_reviewer_agent(
    model: str | BaseChatModel | None = None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    repo_root: str | Path | None = None,
    allow_subdirectories: bool = True,
) -> Any:
    """Create the QA lead role worker."""
    return create_role_agent(
        name=_NAME,
        stage=_STAGE,
        system_prompt=_SYSTEM_PROMPT,
        response_format=AcceptanceReviewOutput,
        model=model,
        checkpointer=checkpointer,
        repo_root=repo_root,
        allow_subdirectories=allow_subdirectories,
        can_write=False,
    )


__all__ = [
    "AcceptanceReviewFinding",
    "AcceptanceReviewOutput",
    "SEVERITIES",
    "SEVERITY_RULE",
    "build_acceptance_review_request",
    "create_acceptance_reviewer_agent",
]
