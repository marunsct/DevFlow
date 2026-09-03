"""The LangGraph controller that turns independent role agents into a workflow.

Each module under `app.agents` is a narrow role worker that knows how to do one
job. Nothing in that package decides what runs next, enforces a review gate, or
resumes a paused run - an LLM deciding those things is exactly what the workflow
plan forbids. `app.graph.workflow` owns them instead, as explicit graph edges.
"""

from app.graph.workflow import (
    APPROVAL_PAUSE_PREFIX,
    REVIEW_PAUSE_PREFIX,
    SPECIFICATION_REVIEW,
    SPRINT_REVIEW,
    WorkflowGraphState,
    approve_decision,
    build_workflow_graph,
    request_changes_decision,
    resume_pending_approval,
    resume_pending_review,
    skip_decision,
    start_workflow,
)

__all__ = [
    "APPROVAL_PAUSE_PREFIX",
    "REVIEW_PAUSE_PREFIX",
    "SPECIFICATION_REVIEW",
    "SPRINT_REVIEW",
    "WorkflowGraphState",
    "approve_decision",
    "build_workflow_graph",
    "request_changes_decision",
    "resume_pending_approval",
    "resume_pending_review",
    "skip_decision",
    "start_workflow",
]
