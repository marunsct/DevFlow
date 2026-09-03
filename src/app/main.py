"""Command-line entry point for the product-development workflow.

This is the smallest thing that satisfies the plan's first Definition-of-Done
item: "A supplied product document can start a run." It reads a product brief,
describes the repository, builds the LangGraph controller, and drives the run to
one of its terminal states, stopping at every gate to ask a human what to do.

Two kinds of gate stop a run, and this CLI handles both (see `app.graph.workflow`
for why they are different mechanisms):

- **Mandatory approval** before any artifact is written. You approve, edit, or
  reject. There is no "run without approvals" flag; that gate is the point.
- **Optional user review** of a finished artifact, only when you enable it with
  `--review-specification` / `--review-sprint`. You approve, request changes, or
  explicitly skip. Skipping is recorded as a skip, never as an approval.

Known limitation - resume is single-process
-------------------------------------------
Runs are checkpointed with LangGraph's `InMemorySaver`, so state lives only in
this process. If you quit at a gate, the run is gone and must be restarted; you
cannot come back tomorrow and resume the same `--thread-id`. That is deliberate
sequencing, not an oversight: the workflow plan's Step 8.1 replaces in-memory
checkpointing with a durable checkpointer *after* graph behavior is proven
correct, and Phase 6 puts a web control plane in front of it. The graph itself
already resumes correctly by `thread_id`; only the storage is ephemeral.

Usage:
    python -m app.main --document path/to/brief.md
    python -m app.main --document brief.docx --review-specification --reviewer alice
    python -m app.main --document brief.md --auto-approve-writes   # non-interactive
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path
from typing import Any

from app.agents.approval import approve_write_decision, reject_write_decision
from app.documents import DocumentReadError, read_document
from app.graph.workflow import (
    APPROVAL_PAUSE_PREFIX,
    REVIEW_PAUSE_PREFIX,
    SPECIFICATION_REVIEW,
    SPRINT_REVIEW,
    approve_decision,
    build_workflow_graph,
    request_changes_decision,
    resume_pending_approval,
    resume_pending_review,
    skip_decision,
    start_workflow,
)
from app.tools.repository import RepositoryToolError, build_repository_context

MAX_GATES = 50
"""Refuse to keep looping after this many gates in one run.

A safety net, not a policy: the graph's own limits (architecture revisions,
remediation attempts, review reruns) are what actually bound the workflow. This
only stops a runaway interactive session if one of those limits is ever wired up
incorrectly, so a bug surfaces as a clear message instead of an endless prompt.
"""

_STAGE_MEANINGS = {
    "product_manager": "Reading the product document and extracting product understanding.",
    "tools_models": "Comparing frameworks, model providers, and infrastructure options.",
    "principal_architect": "Writing the technical specification and architecture decisions.",
    "architecture_review": "The architecture reviewer is checking security and feasibility.",
    "user_review_specification": "Waiting for your review of the technical specification.",
    "scrum_master": "Breaking approved architecture into independent vertical sprints.",
    "technical_lead": "Selecting one sprint and planning a small milestone.",
    "specialist_dispatch": "Specialists are implementing and testing the milestone.",
    "user_review_sprint": "Waiting for your review of the completed sprint.",
    "complete": "The run finished successfully.",
    "failed": "The run stopped and needs a human decision.",
}


def _describe_stage(stage: str) -> str:
    """Return a plain-language meaning for a stage, for humans reading the terminal."""
    if stage.startswith(APPROVAL_PAUSE_PREFIX):
        return f"Paused: {stage.removeprefix(APPROVAL_PAUSE_PREFIX)} wants to write an artifact and needs approval."
    if stage.startswith(REVIEW_PAUSE_PREFIX):
        return f"Paused: your optional review of '{stage.removeprefix(REVIEW_PAUSE_PREFIX)}' is open."
    return _STAGE_MEANINGS.get(stage, stage)


def _prompt(question: str, allowed: list[str]) -> str:
    """Ask the operator to choose one of `allowed`, repeating until they do.

    Reads from stdin. An EOF (piped input, closed terminal) is treated as the
    safest available answer - reject for a write, skip for an optional review -
    rather than silently defaulting to approval.
    """
    options = "/".join(allowed)
    while True:
        try:
            answer = input(f"{question} [{options}]: ").strip().lower()
        except EOFError:
            safe = "reject" if "reject" in allowed else allowed[-1]
            print(f"\nNo input available; choosing the safe default: {safe}")
            return safe
        if answer in allowed:
            return answer
        print(f"Please answer one of: {options}")


def _handle_approval_gate(state: dict[str, Any], *, auto_approve: bool) -> dict[str, Any]:
    """Show a pending artifact write and return the human's decision.

    `auto_approve` exists for unattended runs (CI, demos). It is deliberately
    opt-in and loudly announced: approving writes without a human contradicts
    the plan's Step 3.2 gate, so nobody should enable it by accident.
    """
    approval = state.get("pending_approval")
    if approval is None:
        print("A stage paused for approval but reported no approval request; rejecting to stay safe.")
        return reject_write_decision("No approval request payload was available to review.")

    print("\n--- Approval required before this file is written ---")
    print(f"  Requested by : {approval.requested_by}")
    print(f"  Stage        : {approval.stage}")
    print(f"  File path    : {approval.artifact_path}")
    print(f"  Risk level   : {approval.risk_level}")
    print(f"  Content      : {approval.notes}")

    if auto_approve:
        print("  Decision     : approve (--auto-approve-writes was set; no human reviewed this)")
        return approve_write_decision()

    choice = _prompt("Approve this write?", ["approve", "reject"])
    if choice == "approve":
        return approve_write_decision()
    return reject_write_decision("A human reviewer rejected this artifact write.")


def _handle_review_gate(state: dict[str, Any]) -> dict[str, Any]:
    """Show an open optional review session and return the human's decision."""
    review = state.get("pending_review")
    stage = state.get("stage", "")
    review_point = stage.removeprefix(REVIEW_PAUSE_PREFIX)

    print(f"\n--- Optional review: {review_point} ---")
    if review is not None:
        print(f"  Artifact  : {review.artifact_id}")
        print(f"  Revision  : {review.revision}")
        print(f"  Reviewer  : {review.reviewer}")
        if review.comments:
            print("  Previous comments:")
            for comment in review.comments:
                print(f"    - {comment}")

    choice = _prompt("Your decision?", ["approve", "changes", "skip"])
    if choice == "approve":
        return approve_decision()
    if choice == "skip":
        return skip_decision()

    try:
        comment = input("What must change? ").strip()
    except EOFError:
        comment = ""
    if not comment:
        print("A change request needs a comment; skipping this review instead.")
        return skip_decision()
    return request_changes_decision(comment)


def _print_summary(state: dict[str, Any]) -> None:
    """Print what the run produced and where it ended."""
    stage = state.get("stage", "unknown")
    print("\n=== Run summary ===")
    print(f"Final stage: {stage} - {_describe_stage(stage)}")

    produced = [
        ("Product intake", "product_intake"),
        ("Tools and models", "tools_and_models"),
        ("Technical specification", "technical_specification"),
        ("Architecture review", "architecture_review"),
        ("Sprint plan", "sprint_plan"),
        ("Milestone plan", "milestone_plan"),
    ]
    for label, key in produced:
        if state.get(key) is not None:
            print(f"  [x] {label}")

    specialist_outputs = state.get("specialist_outputs") or {}
    if specialist_outputs:
        print(f"  [x] Specialist results ({len(specialist_outputs)})")

    for point, review in (state.get("reviews") or {}).items():
        print(f"  Review '{point}': {review.status.value} (revision {review.revision})")

    remediation = state.get("remediation")
    if remediation is not None:
        print(f"  Remediation: attempt {remediation.attempt}/{remediation.max_attempts}, escalated={remediation.escalated}")

    if state.get("error"):
        print(f"\nError: {state['error']}")


def build_parser() -> argparse.ArgumentParser:
    """Define the command-line interface."""
    parser = argparse.ArgumentParser(
        prog="app.main",
        description="Run the agentic product-development workflow against a product document.",
    )
    parser.add_argument("--document", required=True, help="Path to the product brief (.md, .txt, or .docx).")
    parser.add_argument("--repo-root", default=None, help="Repository the agents may inspect (default: this repo).")
    parser.add_argument("--thread-id", default=None, help="Stable run id (default: a generated uuid).")
    parser.add_argument("--model", default=None, help="Model override; default comes from OPENAI_MODEL.")
    parser.add_argument("--reviewer", default="unassigned", help="Identity recorded on any review decision.")
    parser.add_argument(
        "--review-specification",
        action="store_true",
        help="Open an optional human review after the technical specification is approved.",
    )
    parser.add_argument(
        "--review-sprint",
        action="store_true",
        help="Open an optional human review after a sprint's tests pass.",
    )
    parser.add_argument(
        "--auto-approve-writes",
        action="store_true",
        help="Approve every artifact write without asking. For unattended runs only; no human reviews the content.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the workflow from the command line, returning a process exit code.

    Exit codes: 0 the run completed, 1 it ended in `failed` or hit the gate
    ceiling, 2 the inputs were unusable (bad document, bad repository root).
    """
    args = build_parser().parse_args(argv)

    repo_root = args.repo_root or str(Path(__file__).resolve().parents[2])

    try:
        document = read_document(args.document)
    except (FileNotFoundError, DocumentReadError) as exc:
        print(f"Could not read the product document: {exc}", file=sys.stderr)
        return 2

    try:
        repository = build_repository_context(repo_root)
    except RepositoryToolError as exc:
        print(f"Could not inspect the repository: {exc}", file=sys.stderr)
        return 2

    thread_id = args.thread_id or f"run-{uuid.uuid4()}"
    review_policy = {
        SPECIFICATION_REVIEW: args.review_specification,
        SPRINT_REVIEW: args.review_sprint,
    }

    print(f"Document   : {document.source_path} ({document.source_type}, {len(document.text)} chars)")
    if document.truncated:
        print(f"             {document.truncation_note}")
    print(f"Repository : {repository.root_path} @ {repository.branch} ({repository.status})")
    print(f"Run id     : {thread_id}")
    print(f"Reviews    : specification={args.review_specification}, sprint={args.review_sprint}")
    print("\nNote: this run is checkpointed in memory only. Quitting at a gate discards it.\n")

    graph = build_workflow_graph(model=args.model, repo_root=repo_root)

    state = start_workflow(
        graph,
        document,
        repository,
        thread_id,
        review_policy=review_policy,
        reviewer=args.reviewer,
    )

    # Each `invoke` above and below runs until the graph reaches a terminal
    # stage or pauses at a gate. This loop turns those pauses into prompts and
    # feeds the answers back in, until the run is genuinely finished.
    for _ in range(MAX_GATES):
        stage = state.get("stage", "")
        print(f"\nStage: {stage} - {_describe_stage(stage)}")

        if stage.startswith(APPROVAL_PAUSE_PREFIX):
            decision = _handle_approval_gate(state, auto_approve=args.auto_approve_writes)
            state = resume_pending_approval(graph, thread_id, decision)
            continue
        if stage.startswith(REVIEW_PAUSE_PREFIX):
            decision = _handle_review_gate(state)
            state = resume_pending_review(graph, thread_id, decision)
            continue
        break
    else:
        print(f"\nStopped after {MAX_GATES} gates without reaching a terminal stage.", file=sys.stderr)
        _print_summary(state)
        return 1

    _print_summary(state)
    return 0 if state.get("stage") == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
