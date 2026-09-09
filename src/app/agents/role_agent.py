"""Shared Deep Agent factory for narrow, safe workflow role workers.

Every role agent in this workflow (Product Manager, Tools and Models Architect,
Principal Architect, Senior Architect Reviewer, Scrum Master, Technical Lead,
and each specialist) needs the same safety wiring:

- a bounded set of repository read tools plus one controlled artifact-write tool
- the inert built-in filesystem tools denied, so the model cannot rely on them
- a human-approval gate on every artifact write (see `app.agents.approval`)
- a checkpointer, so a paused approval can be resumed later

Centralizing that wiring here means each role module only supplies what makes
it different: its name, its system prompt, and its structured output schema.
Without this, every new role would copy the same ~30 lines of `create_deep_agent`
configuration, and any future safety fix would need to be applied in every copy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from deepagents.middleware.filesystem import FilesystemPermission
from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel

from app.models import build_default_chat_model
from app.tools.agent_toolkit import (
    HUMAN_APPROVAL_TOOLS,
    build_artifact_write_tool,
    build_repository_read_tools,
)


def default_repo_root() -> Path:
    """Return the repository root for this workspace.

    Computed relative to this file (four levels up: agents/ -> app/ -> src/ ->
    repo root) so every role agent shares one source of truth instead of each
    module hard-coding its own path.
    """
    return Path(__file__).resolve().parents[3]


def describe_artifact_write(repo_root: str, agent_name: str, stage: str):
    """Build the interrupt description shown to a human before an artifact write.

    Binding `repo_root` in a closure lets us check whether the proposed file
    already exists, which is the signal used for risk level: overwriting an
    existing artifact is riskier than creating a brand new one. `agent_name`
    and `stage` are included so a reviewer looking at several paused approvals
    can tell which role and workflow stage each one came from.
    """

    def describe(tool_call: dict[str, Any], state: Any, runtime: Any) -> str:  # noqa: ARG001
        args = tool_call.get("args", {})
        relative_path = args.get("relative_path", "<unknown path>")
        content = args.get("content", "")
        summary = content[:200] + ("..." if len(content) > 200 else "")
        target = (Path(repo_root) / relative_path).resolve()
        risk_level = "medium (overwrites an existing file)" if target.exists() else "low (new file)"
        return (
            f"Agent: {agent_name} (stage: {stage})\n"
            f"Proposed file path: {relative_path}\n"
            f"Proposed content summary: {summary}\n"
            f"Risk level: {risk_level}\n"
            "Allowed decisions: approve, edit, reject"
        )

    return describe


def describe_tool_call(repo_root: str, agent_name: str, stage: str, tool_name: str):
    """Build the interrupt description shown to a human for a risky tool call."""

    def describe(tool_call: dict[str, Any], state: Any, runtime: Any) -> str:  # noqa: ARG001
        args = tool_call.get("args", {})
        command = args.get("command")
        if isinstance(command, list):
            rendered = " ".join(str(part) for part in command)
        else:
            rendered = str(command)
        return (
            f"Agent: {agent_name} (stage: {stage})\n"
            f"Tool: {tool_name}\n"
            f"Command: {rendered}\n"
            f"Workspace: {repo_root}\n"
            f"Category: {args.get('category', 'default')}\n"
            "This executes code inside the workspace. Approve only if the command is expected.\n"
            "Allowed decisions: approve, reject"
        )

    return describe


def _interrupt_config(
    tools: list[BaseTool], repo_root: str, agent_name: str, stage: str
) -> dict[str, dict[str, Any]]:
    """Map every risky tool this agent holds to its approval gate.

    Built from the tools actually attached rather than from a fixed literal, so
    adding a tool to an agent cannot silently add an ungated capability.
    """
    config: dict[str, dict[str, Any]] = {}
    for tool_obj in tools:
        tool_name = getattr(tool_obj, "name", None)
        if tool_name not in HUMAN_APPROVAL_TOOLS:
            continue
        if tool_name == "write_artifact":
            config[tool_name] = {
                "allowed_decisions": ["approve", "edit", "reject"],
                "description": describe_artifact_write(repo_root, agent_name, stage),
            }
        else:
            # Editing a command before it runs would let a reviewer approve one
            # thing and execute another, so execution gates are approve/reject.
            config[tool_name] = {
                "allowed_decisions": ["approve", "reject"],
                "description": describe_tool_call(repo_root, agent_name, stage, tool_name),
            }
    return config


def create_role_agent(
    *,
    name: str,
    stage: str,
    system_prompt: str,
    response_format: type[BaseModel],
    model: str | BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    repo_root: str | Path | None = None,
        allow_subdirectories: bool = True,
    extra_tools: list[BaseTool] | None = None,
) -> Any:
    """Create a narrow, safe Deep Agent for one workflow role.

    Args:
        name: stable role identifier (e.g. "product_manager"). Used as the
            compiled graph's name and shown in approval descriptions.
        stage: workflow stage this role operates in (e.g. "intake"). Shown in
            approval descriptions so a reviewer knows where a paused write
            came from.
        system_prompt: the role-specific instructions. Safety constraints
            (no source edits, gated writes) are the same for every role, so
            callers only need to describe the role's job here.
        response_format: the structured output schema this role must return.
        model: optional model override; defaults to the local dev model from
            `app.config.load_settings()` via `build_default_chat_model()`.
        checkpointer: optional shared checkpointer; defaults to a fresh
            `InMemorySaver()`. Pass the same instance across calls to let a
            paused run be resumed by a different agent object later.
        repo_root: optional repository root override, mainly for tests so they
            do not write into the real project's `docs/generated` directory.
        allow_subdirectories: whether the agent can read files from subdirectories.
        extra_tools: additional read-only or narrow tools specific to this
            role (e.g. a validation-runner tool for the testing specialist).

    Returns:
        A compiled LangGraph graph (the same shape `create_deep_agent` always
        returns), ready to `.invoke(...)`.
    """
    # `load_dotenv()` is idempotent and cheap; calling it here guarantees local
    # `.env` values are present even if this agent is constructed before any
    # other module has loaded the environment.
    load_dotenv()

    resolved_repo_root = str(repo_root) if repo_root is not None else str(default_repo_root())
    selected_model = model if model is not None else build_default_chat_model()

    tools = [
        *build_repository_read_tools(resolved_repo_root, allow_subdirectories=allow_subdirectories),
        build_artifact_write_tool(resolved_repo_root),
        *(extra_tools or []),
    ]

    # Inject directory instructions dynamically so every agent knows the artifact layout rules.
    full_system_prompt = (
        f"{system_prompt}\n\n"
        "CRITICAL DIRECTORY RULES:\n"
        "- Write all document artifacts (intakes, specs, plans, reports) inside the `docs/` folder (e.g., `docs/spec.md`).\n"
        "- Write all code artifacts inside the `<product_name>/` folder (based on the determined product name).\n"
    )

    return create_deep_agent(
        model=selected_model,
        tools=tools,
        system_prompt=full_system_prompt,
        response_format=response_format,
        # See `app.agents.product_manager` for why this denies the built-in
        # filesystem tools rather than trying to "allow" real repo paths: the
        # default backend is an in-memory `StateBackend`, not the real repo.
        permissions=[
            FilesystemPermission(operations=["read", "write"], paths=["/**"], mode="deny"),
        ],
        # Every high-risk tool call pauses for a human decision - not just the
        # artifact write. Gating is by what a call can do, so command execution
        # and validation runs are included: both can execute code, and both were
        # previously ungated while the far safer file write was not.
        interrupt_on=_interrupt_config(tools, resolved_repo_root, name, stage),
        checkpointer=checkpointer,
        name=name,
    )


__all__ = [
    "create_role_agent",
    "default_repo_root",
    "describe_artifact_write",
    "describe_tool_call",
]
