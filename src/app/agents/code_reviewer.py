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
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field

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


class CodeReviewOutput(BaseModel):
    """The reviewer's verdict on the batch."""

    model_config = ConfigDict(extra="forbid")

    approved: bool = Field(..., description="True when nothing blocking or major was found.")
    findings: list[CodeReviewFinding] = Field(default_factory=list)


_SYSTEM_PROMPT = f"""You are the senior engineer reviewing a batch of changes before it is tested.

You are given the diff, the work orders it was meant to carry out, and the
acceptance criteria the sprint serves. Read the diff against them. Look for
what a passing test suite would not reveal:
- a work order not carried out, or carried out only in part;
- code that is written but never reached - a function nothing calls, a control
  nothing wires up, an endpoint nothing routes to;
- a placeholder or stub returning a fixed value where real behaviour belongs;
- data that must survive kept only in memory, or saved and never read back;
- input a user controls reaching storage, markup or a command unchecked.

Report only real problems, each tied to its work order, with the file and what
to change. Do not ask for style changes, comments, renames or tests of things no
criterion asks for. If the batch does what its work orders say, approve it.

Read files with your tools when the diff is not enough.

{STRUCTURED_RESPONSE_RULE}"""


def build_code_review_request(
    diff: str,
    work_orders: str,
    criteria: str,
    ci_report: str,
) -> dict[str, list[dict[str, str]]]:
    content = (
        "The workspace is rooted at '/'; all paths you use are relative to it.\n\n"
        f"--- Work orders in this batch ---\n{work_orders}\n\n"
        f"--- Acceptance criteria this sprint serves ---\n{criteria or '(none recorded)'}\n\n"
        f"--- What CI measured after the batch ---\n{ci_report}\n\n"
        f"--- The diff ---\n{diff or '(no product files changed)'}\n\n"
        "Review the batch."
    )
    return {"messages": [{"role": "user", "content": content}]}


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
    "CodeReviewFinding",
    "CodeReviewOutput",
    "build_code_review_request",
    "create_code_reviewer_agent",
]
