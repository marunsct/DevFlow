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

import logging
from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.middleware.filesystem import (
    FilesystemMiddleware,
    FilesystemPermission,
)
from deepagents.middleware.summarization import SummarizationMiddleware
from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel

from app.agents.context_policy import ContextPolicy
from app.agents.context_store import build_context_backend
from app.models import build_default_chat_model
from app.tools.agent_toolkit import (
    HUMAN_APPROVAL_TOOLS,
    build_artifact_edit_tool,
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


def _clip_for_review(text: str, limit: int = 200) -> str:
    """Shorten a value for an approval description without losing its shape."""
    text = str(text or "")
    return text[:limit] + ("..." if len(text) > limit else "")


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
        target = (Path(repo_root) / relative_path).resolve()

        # `edit_artifact` carries `find`/`replace`, not `content`. Reading only
        # `content` showed a reviewer an empty summary for every edit, which is
        # the one case where seeing what changes matters most.
        if "find" in args or "replace" in args:
            change = (
                f"Replacing: {_clip_for_review(args.get('find', ''))}\n"
                f"With: {_clip_for_review(args.get('replace', '')) or '(deletes the passage)'}"
            )
            risk_level = "low (changes one passage, leaves the rest of the file intact)"
        else:
            change = f"Proposed content summary: {_clip_for_review(args.get('content', ''))}"
            risk_level = (
                "medium (replaces the whole of an existing file)"
                if target.exists()
                else "low (new file)"
            )

        return (
            f"Agent: {agent_name} (stage: {stage})\n"
            f"Proposed file path: {relative_path}\n"
            f"{change}\n"
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
        if tool_name in ("write_artifact", "edit_artifact"):
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


logger = logging.getLogger(__name__)


_WORKSPACE_READ_TOOLS = ["ls", "read_file", "glob", "grep"]
"""The built-in filesystem tools a role agent is allowed to see.

Deliberately read-only. Writing is `write_artifact` and nothing else, because
that is the call the approval gate interrupts on.
"""


def _workspace_filesystem_middleware(repo_root: str) -> FilesystemMiddleware:
    """Point the built-in filesystem tools at the run's real workspace.

    `create_deep_agent` always installs `FilesystemMiddleware`, and by default it
    registers nine tools (`ls`, `read_file`, `glob`, `grep`, `write_file`,
    `edit_file`, `delete`, `execute`, plus `task`) over an in-memory
    `StateBackend` that has nothing to do with the repository.

    This used to be handled by denying read and write on every path. The tools
    stayed *advertised* though, so the model kept calling them and kept getting
    `permission denied`. In one run that was 10 of 24 tool calls, and it was not
    merely wasteful: the architect tried `write_file` for the specification,
    concluded from the denial that it had no way to write at all, and spent its
    remaining turns asking the human for permission instead of returning its
    structured response. The stage then failed with "failed to produce a
    structured response", which reads like a context-limit problem and is not.

    So instead of denying the tools, give them a backend that works. Rooting a
    `FilesystemBackend` at the workspace in virtual mode means `/docs/spec.md` -
    exactly the path shape the middleware's own prompt teaches the model to use -
    resolves inside this run's directory and nowhere else.

    Only the read tools are registered. That grants nothing new: an agent could
    already read any file under the root through `read_repository_file`
    (`allow_subdirectories` narrows *listing* depth, never read access).
    """
    return FilesystemMiddleware(
        backend=FilesystemBackend(root_dir=repo_root, virtual_mode=True),
        tools=list(_WORKSPACE_READ_TOOLS),
    )


def _compaction_middleware(agent_name: str) -> list:
    """Summarise this agent's history before it outgrows the model's window.

    Returns an empty list when compaction is disabled or cannot be built, so a
    failure here degrades to "no compaction" rather than "no agent".

    The thread id is not known at construction time - `_run_gated_agent` mints
    one per attempt - so the context directory is keyed by agent name. That is
    stable per role and adequate: the content is scratch space for the
    summariser, not run state.
    """
    policy = ContextPolicy.from_environment()
    if not policy.enabled:
        return []

    try:
        from app.config import load_settings
        from app.server.runtime_settings import effective_environment

        if policy.compaction_model:
            environment = dict(effective_environment())
            environment["OPENAI_MODEL"] = policy.compaction_model
            summariser = build_default_chat_model(load_settings(environment))
        else:
            # The run's own model. Never a hardcoded hosted model id: this
            # deployment may serve a local endpoint, where an OpenAI model name
            # with no base URL or key fails on every compaction.
            summariser = build_default_chat_model()

        return [
            SummarizationMiddleware(
                summariser,
                backend=build_context_backend(agent_name),
                trigger=("tokens", policy.trigger_tokens),
                keep=("messages", policy.keep_recent_messages),
                trim_tokens_to_summarize=policy.trim_tokens_to_summarize,
            )
        ]
    except Exception:  # noqa: BLE001 - see docstring
        logger.warning(
            "Could not build compaction middleware for %s; continuing without it",
            agent_name, exc_info=True,
        )
        return []


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
        build_artifact_edit_tool(resolved_repo_root),
        *(extra_tools or []),
    ]

    # Inject directory instructions dynamically so every agent knows the artifact layout rules.
    full_system_prompt = (
        f"{system_prompt}\n\n"
        "CRITICAL DIRECTORY RULES:\n"
        "- Write all document artifacts (intakes, specs, plans, reports) inside the `docs/` folder (e.g., `docs/spec.md`).\n"
        "- Write all code artifacts inside the `<product_name>/` folder (based on the determined product name).\n"
        "\n"
        "HOW TO WRITE:\n"
        "- `write_artifact` CREATES a file, or replaces one completely. Its\n"
        "  `relative_path` is relative to the workspace root: `docs/spec.md`.\n"
        "- `edit_artifact` CHANGES part of a file that already exists. Give it the\n"
        "  exact passage to replace and what to replace it with. Use this for\n"
        "  every revision to an existing document: it leaves the rest of the file\n"
        "  untouched, so nothing is lost and you do not have to reproduce work\n"
        "  that is already correct.\n"
        "- Revising an existing document? Read the section you need with\n"
        "  `read_repository_file` (it takes `start_line` and `line_count`, so you\n"
        "  can read part of a long file), then `edit_artifact` that passage.\n"
        "  Do NOT rewrite a long document from memory to change part of it, and\n"
        "  NEVER save your revision under a new name like `spec_v2.md` - two\n"
        "  versions of one document contradict each other and a reviewer reads\n"
        "  both.\n"
        "- You already have permission to write. Call `write_artifact` directly.\n"
        "  Never ask whether you should write a file, and never stop to request\n"
        "  approval - approval is handled outside this conversation.\n"
        "\n"
        "PATHS - every path is inside the workspace:\n"
        "- `docs/spec.md` and `/docs/spec.md` mean the same file. A leading slash\n"
        "  reads as 'from the workspace root', which is what you mean by it.\n"
        "- `ls`, `glob`, `grep`, `read_file` (read-only): browse from `/`. The\n"
        "  intake is `/docs/product_intake.md`; `ls('/')` shows everything.\n"
        "- The long absolute path quoted as the repository root elsewhere in this\n"
        "  brief is the HOST's path and does not exist here - passing it returns\n"
        "  `path_not_found`. Never use it; start from the workspace root.\n"
        "- Shell commands already run inside the workspace directory, so use\n"
        "  ordinary relative paths (`thehub/`). Do not prefix them with `/`.\n"
        "\n"
        "ARTIFACTS ARE NOT YOUR STRUCTURED RESPONSE:\n"
        "- Artifact content must be human-readable Markdown: headings, prose,\n"
        "  lists, tables. A person reads these files.\n"
        "- NEVER pass JSON as `write_artifact` content, and never save your\n"
        "  structured response to a file. The structured response is returned\n"
        "  through the response schema, separately, and is not an artifact.\n"
        "- Write each artifact ONCE. After a write_artifact tool result comes\n"
        "  back, that file is saved and correct. Do not write it again, do not\n"
        "  'confirm' it with a second write, and never overwrite good Markdown\n"
        "  with a serialized copy of your answer. Return your structured\n"
        "  response instead.\n"
    )

    # Compaction. Built here rather than at module scope so a policy change
    # takes effect on the next agent, not the next restart. The context
    # directory is keyed by agent name (not thread id), which is stable per
    # role; see `_compaction_middleware` for why that is deliberate.
    middleware = _compaction_middleware(name)
    middleware = [*middleware, _workspace_filesystem_middleware(resolved_repo_root)]

    return create_deep_agent(
        model=selected_model,
        tools=tools,
        system_prompt=full_system_prompt,
        response_format=response_format,
        middleware=middleware,
        # Writes stay denied at the permission layer as well as absent from the
        # tool list. `write_artifact` is the only mutation path, and it is the
        # one the approval gate is wired to; a built-in write would slip past it.
        permissions=[
            FilesystemPermission(operations=["write"], paths=["/**"], mode="deny"),
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
