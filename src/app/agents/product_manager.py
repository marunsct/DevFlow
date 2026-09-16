"""Product Manager Deep Agent.

This module implements the first role worker in the workflow. Its job is not to
build code or change the app directly. Instead, it reads product documents and
repository context, identifies the product problem space, and returns a
structured intake artifact suitable for review by later workflow stages.

The big idea is easy to understand: each role agent is narrow and deliberate.
The Product Manager stays in discovery mode, while the runtime graph remains the
piece that decides when a write is allowed and when a human should review it.
Safety wiring (tools, approval gate, checkpointer) lives in `app.agents.role_agent`
and `app.agents.approval` so every future role agent shares it instead of
re-implementing it.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field

from app.agents.approval import (
    approve_write_decision as approve_write_decision,
)
from app.agents.approval import (
    edit_write_decision as edit_write_decision,
)
from app.agents.approval import (
    extract_pending_approval as _extract_pending_approval,
)
from app.agents.approval import (
    reject_write_decision as reject_write_decision,
)
from app.agents.approval import (
    resume_with_decision as resume_with_decision,
)
from app.agents.brief_constraints import constraint_lines
from app.agents.structured_response import STRUCTURED_RESPONSE_RULE
from app.agents.role_agent import create_role_agent, default_repo_root
from app.documents import DocumentContent
from app.state import HumanApprovalRequest, RepositoryContext

_STAGE = "intake"
_NAME = "product_manager"


class ProductManagerOutput(BaseModel):
    """Structured product-intake output returned by the Product Manager agent.

    The schema deliberately mirrors the product discovery fields named in the
    workflow plan. Every field is intended to be reviewable by a human and
    machine-readable by the later pipeline stages.
    """

    model_config = ConfigDict(extra="forbid")

    product_name: str = Field(..., description="Human-readable product identifier.")
    users_and_stakeholders: list[str] = Field(default_factory=list)
    problems_and_desired_outcomes: list[str] = Field(default_factory=list)
    core_workflows: list[str] = Field(default_factory=list)
    mvp_candidates: list[str] = Field(default_factory=list)
    deferred_scope: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    evidence_vs_assumptions: list[str] = Field(default_factory=list)
    success_measures: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


def with_the_constraints_the_brief_states(
    output: ProductManagerOutput, document_text: str
) -> ProductManagerOutput:
    """`output`, plus any constraint the brief states that it left out.

    `constraints` is an optional list field on a ten-field schema, and a local
    model fills it or does not. On run 0c5aabdb it did not: the brief carries a
    `## Technical Constraints` heading with four lines under it, and
    `docs/product_intake.md` rendered

        ## Constraints
        _Not specified._

    Nothing downstream reads the brief - the principal architect writes the
    specification from the intake, and it wrote "Backend: Express server" into
    a product whose brief says "No external dependencies beyond basic
    HTML/CSS/JS". Both stages did their work correctly on what they were given.
    The constraints were simply no longer in it.

    So they are put back from the document. The model's own list is kept and
    comes first, because it may have found a constraint stated as prose that
    no heading covers; the brief's lines are appended when they are not already
    there. Nothing is removed, and a brief that states no constraints leaves
    the output exactly as the model returned it.

    Matching is exact and case-insensitive. A model that paraphrased a
    constraint will see both its paraphrase and the brief's wording, which is
    the right way round: dropping either would lose the one that mattered.
    """
    stated = constraint_lines(document_text)
    if not stated:
        return output
    already = {line.strip().lower() for line in output.constraints}
    missing = [line for line in stated if line.strip().lower() not in already]
    if not missing:
        return output
    return output.model_copy(
        update={"constraints": [*output.constraints, *missing]}
    )


def _truncate(text: str, max_chars: int | None = None) -> str:
    """Truncate long text for local LLM context limits."""
    # Derived from the configured context window, not a fixed number: a
    # budget that does not move with the model is how every overflow in
    # this pipeline's history began.
    if max_chars is None:
        from app.agents.context_budget import ContextBudget

        max_chars = ContextBudget.resolve().document_budget_chars
    text = str(text or "")
    if len(text) <= max_chars:
        return text
    split = int(max_chars * 0.6)
    return (
        text[:split]
        + f"\n\n--- TRUNCATED ({len(text) - split} chars removed for context limits) ---\n\n"
        + text[len(text) - (max_chars - split):]
    )


def build_intake_request(
    document: DocumentContent, repository: RepositoryContext
) -> dict[str, list[dict[str, str]]]:
    """Build the Deep Agent input from a read product document and repo context.

    `create_product_manager_agent` only builds the graph; something still has to
    turn a `DocumentContent` (from `app.documents.read_document`) and a
    `RepositoryContext` (from `app.state`) into the first message the agent sees.
    Callers should pass this function's return value straight to `agent.invoke`.
    """
    brief = (
        # The NAME, never the path. `source_path` is where the upload landed on
        # the HOST - `/app/data/uploads/brief_low_752e3b83.md` - and inside the
        # agent every path is resolved against a workspace rooted at "/", so
        # reading it answers "not found" and writing it would build a mirror of
        # the host layout inside the workspace. Measured across runs 2b5def74,
        # da6c5e19 and 5d83e946: `product_manager` opens by trying to read that
        # exact string, every time, and gets an error for its first tool call.
        # This is the rule the comment below already states, applied to the
        # other path on the same line - it was written for the repository and
        # the document was left as it was.
        # "quoted below", never "in full": the text goes through `_truncate`,
        # and a brief that claims completeness it does not have tells an agent
        # not to read the real file precisely when it should.
        # No filename at all. The previous version showed the upload's
        # basename instead of its host path, on the reasoning that the name was
        # safe where the path was not. It is not: the stored name carries an
        # upload suffix (`brief_low_aa06a786.md`) and names nothing that exists
        # in a workspace rooted at "/". Measured on runs 2b5def74, da6c5e19,
        # 5d83e946 and again on run-36eb1260 - `product_manager` spends its
        # first two calls on `read_file` and then `glob` for that exact string,
        # and gets an error for both.
        #
        # A filename in a prompt is an affordance: it invites a read. The text
        # is already here in full, so naming a file buys nothing and costs the
        # stage its opening move. Provenance lives in the run record and in
        # docs/product_intake.md, where an auditor can use it and an agent
        # cannot mistake it for a path.
        f"Product document ({document.source_type}), quoted below - this text "
        f"is the document itself, not a file in the workspace\n"
        # Deliberately not the repository's absolute path. That is the HOST's
        # path; inside the agent the workspace is rooted at "/". Quoting it here
        # and then telling the agent never to use it does not work - measured on
        # run-0b55ad49, agents retried `ls` against that exact string four times
        # in a row, and fed it to shell commands, every attempt failing with
        # path_not_found. The reliable fix is not to show it.
        f"Repository: branch {repository.branch}, commit {repository.commit}\n"
        f"The workspace is rooted at '/'; all paths you use are relative to it.\n\n"
        f"--- Product document text ---\n{_truncate(document.text)}\n"
    )
    if document.truncated and document.truncation_note:
        brief += f"\nNote: {document.truncation_note}\n"
    return {"messages": [{"role": "user", "content": brief}]}


def extract_pending_approval(
    result: dict[str, Any],
    repo_root: str | Path,
    *,
    requested_by: str = _NAME,
) -> HumanApprovalRequest | None:
    """Product-Manager-flavored wrapper around the generic approval extractor.

    Kept here (instead of requiring callers to pass `stage="intake"` every
    time) so existing call sites and tests keep working unchanged.
    """
    return _extract_pending_approval(result, repo_root, requested_by=requested_by, stage=_STAGE)


_SYSTEM_PROMPT = f"""You are the Product Manager and UX discovery partner for this workflow.

Your role is to turn a supplied product brief and repository evidence into a clear product intake artifact.

Ground every conclusion in the product document and repository evidence. If evidence is missing, state it as an assumption instead of inventing certainty.

Responsibilities:
- Identify the product name and who the users or stakeholders are.
- Summarize problems, pain points, desired outcomes, and the value the product should create.
- Describe the main workflows and the likely MVP candidates.
- Call out deferred scope, constraints, evidence-vs-assumptions, success measures, and open product questions.
- Prioritize decision-worthy product clarity over speculative future features.

Constraints:
- Do not modify application source code.
- Do not change repo files except through the approved artifact tool.
- Do not write a document. The workflow renders `docs/product_intake.md` from the
  structured response you return, so your product intake reaches its readers
  either way - and only through that response. Writing it yourself
  produces the same work twice from one understanding, and the two
  copies then disagree.
- Do not claim a requirement is fact without evidence from the supplied brief or repository context.
- Every write_artifact call pauses for a human decision before anything is saved; never tell the user the artifact is saved until you see a tool result confirming a completed write.
- **Write the complete intake in ONE single write_artifact call.** Do NOT make follow-up edit calls to refine or improve it after the initial write. Once the write is confirmed, immediately return your structured response.
- Keep the output structured and concise.

Return the response in the required output schema only.

{STRUCTURED_RESPONSE_RULE}
"""


def create_product_manager_agent(
    model: str | BaseChatModel | None = None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    repo_root: str | Path | None = None,
        allow_subdirectories: bool = True,
) -> Any:
    """Create the Product Manager role worker using the Deep Agents runtime.

    This is a thin wrapper around `create_role_agent`: it supplies the
    Product-Manager-specific system prompt and output schema, and lets the
    shared factory handle tools, the approval gate, and checkpointing.
    """
    return create_role_agent(
        name=_NAME,
        stage=_STAGE,
        system_prompt=_SYSTEM_PROMPT,
        response_format=ProductManagerOutput,
        model=model,
        checkpointer=checkpointer,
        repo_root=repo_root, allow_subdirectories=allow_subdirectories,
        # Its document is rendered from the structured response, so it needs no
        # write tool - see `app.agents.artifact_document`.
        can_write=False,
    )


def _repo_root() -> Path:
    """Backward-compatible alias kept for any external callers of the old name."""
    return default_repo_root()


__all__ = [
    "ProductManagerOutput",
    "approve_write_decision",
    "build_intake_request",
    "create_product_manager_agent",
    "edit_write_decision",
    "extract_pending_approval",
    "reject_write_decision",
    "resume_with_decision",
]
