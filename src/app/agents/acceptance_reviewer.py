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
from typing import Any, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field

from app.agents.role_agent import create_role_agent
from app.agents.structured_response import STRUCTURED_RESPONSE_RULE

_NAME = "acceptance_reviewer"
_STAGE = "acceptance"


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
    findings: list[str] = Field(
        default_factory=list,
        description=(
            "One line per problem, each starting with the criterion id it concerns "
            "(\"AC-3: the test only checks the list exists; it never checks the item "
            "was removed\"). Empty when approved."
        ),
    )


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
Each test runs alone, against a product that holds no data - nothing another
test created is there. A test that acts on something it never created (an item,
a record, an entry) can pass only on a product that ships with that data, which
no correct product does: it must create what it acts on first.

Then read the tests side by side. Two tests that take the same steps must expect
the same result: one that expects the newest record first and another that
expects the oldest first cannot both pass, whatever is built. A test may assert
only what its criterion states - an order, a count, a wording - and nothing the
criterion leaves open. Name every pair of tests whose expectations contradict,
and every test that asserts something its criterion leaves open.

Do not ask for style changes, more comments, or tests of things no criterion
asks for. Do not judge the product: whatever part of it is built, it is not the
standard, and tests of later features are expected to fail now. Never open its
files to decide what a test should expect.

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
    "AcceptanceReviewOutput",
    "build_acceptance_review_request",
    "create_acceptance_reviewer_agent",
]
