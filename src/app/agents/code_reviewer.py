"""The senior engineer who reviews a batch of work orders before it is tested.

In a software company no change is merged unread. The harness's CI has already
said what the change broke; this reviewer reads the diff against the work
orders it was meant to carry out and the acceptance criteria it serves, and
says what a test suite would not: a feature built but never wired to anything
a user can reach, a stub returning a fixed value, a work order quietly skipped,
data kept only in memory where it has to survive, a security hole.

Its findings are not opinions to argue with: each one that blocks becomes a
defect with an owner, fixed and re-tested in the sprint's own loop.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.role_agent import create_role_agent
from app.agents.structured_response import STRUCTURED_RESPONSE_RULE

_NAME = "code_reviewer"
_STAGE = "code_review"


class CodeReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_order: str = Field(..., description="The title of the work order the problem belongs to.")
    severity: Literal["blocking", "major", "minor"] = Field(
        ...,
        description=(
            "blocking: a user cannot do what the work order or a criterion requires, or data "
            "is lost or exposed. major: it works but wrongly or fragilely. minor: worth tidying."
        ),
    )
    file: str = Field(default="", description="The file the problem is in.")
    problem: str = Field(..., description="What is wrong, concretely, citing the code.")
    fix: str = Field(default="", description="What the owner should change.")
    quality_bar: bool = Field(
        default=False,
        description="True when the finding is one of the data and service bars, not a work order or criterion.",
    )


#: Findings from the data and service bars one review keeps, at most (PQ.9). The bars are checked beyond what any
#: criterion asks, so they are bounded: past this many, a review is restyling the product, not finding its faults.
MOST_BAR_FINDINGS = 3


class CodeReviewOutput(BaseModel):
    """The reviewer's verdict on the batch."""

    model_config = ConfigDict(extra="forbid")

    approved: bool = Field(..., description="True when nothing blocking or major was found.")
    findings: list[CodeReviewFinding] = Field(default_factory=list)

    @model_validator(mode="after")
    def _the_bars_bounded(self) -> "CodeReviewOutput":
        """The first `MOST_BAR_FINDINGS` bar findings, the most severe first; the rest dropped (PQ.9)."""
        bars = [finding for finding in self.findings if finding.quality_bar]
        if len(bars) <= MOST_BAR_FINDINGS:
            return self
        order = {"blocking": 0, "major": 1, "minor": 2}
        kept = {id(finding) for finding in sorted(bars, key=lambda f: order.get(f.severity, 3))[:MOST_BAR_FINDINGS]}
        self.findings = [finding for finding in self.findings if not finding.quality_bar or id(finding) in kept]
        return self


#: The data and service bars, checked where the batch's files store records or answer requests (PQ.9, cause C4 of
#: the 2026-11-25 product-quality audit). Measured on the stored products: a 500 for a forbidden or duplicate request,
#: a filter accepted and ignored, an error shape that differed by route, and none of the constraints, indexes or
#: owner columns the specification adopted - and the reviewer was told to raise nothing no criterion asks for.
QUALITY_BARS = """Where this batch's files store records or answer requests, also hold them to these bars, as the
specification states them, and mark each such finding `quality_bar: true`:
- every failure answers in the one error shape the specification gives;
- each failure has its own status: a record that is not there is not found (404), one that belongs to
  someone else is forbidden (403), and a case the code handles never answers as a server error (500);
- every record a user owns is checked against its owner on each read, change and removal;
- no input is accepted and then ignored: a filter, field or option the interface takes changes the answer;
- the constraints and indexes the specification adopted are declared where the records are stored.
Raise at most three of these, the most serious first, and none where the files touch no records or
requests. They add no rule the brief does not state: a bar the specification leaves open is not one."""


def the_standards(specification: Any) -> str:
    """What the specification adopted for records, contracts and errors, for the bars above; "" when none (PQ.9)."""
    if specification is None:
        return ""
    blocks = []
    for field, heading in _STANDARD_FIELDS:
        entries = [str(entry).strip() for entry in getattr(specification, field, None) or [] if str(entry).strip()]
        if entries:
            blocks.append(f"{heading}:\n" + "\n".join(f"- {entry}" for entry in entries))
    if not blocks:
        return ""
    text = "\n\n".join(blocks)
    if len(text) > MOST_STANDARD_CHARS:
        text = text[:MOST_STANDARD_CHARS].rsplit("\n", 1)[0] + "\n... (the rest is in /docs/technical_specification.md)"
    return f"--- What the specification adopted for records, requests and errors ---\n{text}\n\n"


_STANDARD_FIELDS: tuple[tuple[str, str], ...] = (
    ("domain_model", "Records, their constraints and indexes"),
    ("data_contracts", "Data shapes"),
    ("api_and_event_contracts", "Endpoints and the status of each answer"),
    ("error_catalogue", "Errors and their shape"),
)
#: The most of the specification one review request carries for the bars.
MOST_STANDARD_CHARS = 8_000


_WITH_TOOLS = ("Read files with your tools when the diff is not enough. Do not repeat a tool call that returns no new "
               "information. If a tool tells you you already have the file or it has not changed, use what you have or "
               "answer immediately.")

_THE_REVIEW = f"""You are the senior engineer reviewing a batch of changes before it is tested.

You are given the diff, the work orders it was meant to carry out, and the
acceptance criteria the sprint serves. Read the diff against them. Look for
what a passing test suite would not reveal:
- a work order not carried out, or carried out only in part;
- code that is written but never reached - a function nothing calls, a control
  nothing wires up, an endpoint nothing routes to;
- a placeholder or stub returning a fixed value where real behaviour belongs;
- data that must survive kept only in memory, or saved and never read back;
- input a user controls reaching storage, markup or a command unchecked.

{QUALITY_BARS}

Judge the batch against its own work orders and this sprint's criteria, and the
bars above: work the plan gives to a later sprint is not missing yet. Report only real
problems, each tied to its work order by its title, with the file's full path
and what to change. Beyond the bars, do not ask for style changes, comments, renames or tests of things no
criterion asks for. If the batch does what its work orders say, approve it."""

_SYSTEM_PROMPT = f"""{_THE_REVIEW}

{_WITH_TOOLS}

{STRUCTURED_RESPONSE_RULE}"""

#: The same review asked in one call with no tools, after a sprint accepted at an escalation (PQ.4): what the diff
#: and the request show is all it reads.
ONE_CALL_SYSTEM_PROMPT = f"""{_THE_REVIEW}

You have no tools in this review: judge what the diff and this request show. Answer with one JSON object and
nothing else, in this shape:
{{"approved": true or false, "findings": [{{"work_order": "...", "severity": "blocking, major or minor",
"file": "...", "problem": "...", "fix": "...", "quality_bar": true or false}}]}}"""


def build_code_review_request(
    diff: str,
    work_orders: str,
    criteria: str,
    ci_report: str,
    later: str = "",
    held: Sequence[str] = (),
    standards: str = "",
) -> dict[str, list[dict[str, str]]]:
    """`later` is what the plan gives to later sprints. One run's review raised
    a later sprint's features as missing; each finding became a defect, and the
    fix loop would have built the next sprint inside this one.

    `held`: the changed files the project memory holds for this review, numbered (`review_files.held_for_review`,
    LF.1284); the diff then leaves out the new files among them (`ci.diff_since`), since a new file's diff is the
    file again with a `+` on every line. Only for a product whose files today's request and memory do not show.

    `standards`: what the specification adopted for records, requests and errors (`the_standards`), which the data and
    service bars are checked against (PQ.9)."""
    later_text = (
        f"--- Planned for later sprints, so NOT missing from this batch ---\n{later}\n"
        "Do not report anything listed here as missing or incomplete.\n\n"
        if later.strip() else ""
    )
    content = (
        "The workspace is rooted at '/'; all paths you use are relative to it.\n\n"
        f"--- Work orders in this batch ---\n{work_orders}\n\n"
        f"--- Acceptance criteria this sprint serves ---\n{criteria or '(none recorded)'}\n\n"
        f"{later_text}"
        f"{standards}"
        f"--- What CI measured after the batch ---\n{ci_report}\n\n"
        f"--- The diff ---\n{diff or _NO_DIFF[bool(held)]}\n\n"
        + _where_the_files_are(held)
        + "Review the batch."
    )
    return {"messages": [{"role": "user", "content": content}]}


_NO_DIFF = ("(no product files changed)", "(only new files, held whole in the project memory: see below)")


def _where_the_files_are(held: Sequence[str]) -> str:
    if not held:
        return ""
    from app.agents.review_files import held_section

    return (held_section(held) + "A new file among them is left out of the diff above: its diff would be the whole "
            "file again. A changed one is in the diff as what changed.\n\n")


def create_code_reviewer_agent(
    model: str | BaseChatModel | None = None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    repo_root: str | Path | None = None,
    allow_subdirectories: bool = True,
) -> Any:
    return create_role_agent(
        name=_NAME,
        stage=_STAGE,
        system_prompt=_SYSTEM_PROMPT,
        response_format=CodeReviewOutput,
        model=model,
        checkpointer=checkpointer,
        repo_root=repo_root,
        allow_subdirectories=allow_subdirectories,
        can_write=False,
    )


__all__ = [
    "MOST_BAR_FINDINGS",
    "ONE_CALL_SYSTEM_PROMPT",
    "QUALITY_BARS",
    "the_standards",
    "CodeReviewFinding",
    "CodeReviewOutput",
    "build_code_review_request",
    "create_code_reviewer_agent",
]
