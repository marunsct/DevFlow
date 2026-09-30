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

from app.agents.project_layout import PROJECT_LAYOUT
from app.agents.workspace_backend import WorkspaceBackend
from app.agents.settled_answer import build_settled_answer_middleware

#: `app.graph.workflow.INNER_AGENT_RECURSION_LIMIT` is the hard ceiling, in
#: supersteps, on a single `invoke`. It is not what a stage should be warned
#: about: with `auto_approve` every gated tool interrupts and resumes through a
#: fresh invoke, so that ceiling is re-armed each time and a stage crosses it
#: without ever meeting it. The budget worth warning about is the one that
#: actually accumulates - see `app.agents.settled_answer._model_calls_used`.
from app.agents.settled_answer import MODEL_CALLS_PER_STAGE
from app.agents.repeated_queries import build_repeated_query_middleware
from app.agents.task_list import build_task_list_middleware
from app.agents.text_tool_calls import build_text_tool_call_middleware
from app.observability.transcript import build_transcript_middleware
from app.agents.workspace_digest import build_workspace_digest_middleware
from app.plugins.middleware import build_plugin_instructions_middleware
from app.agents.line_batches import build_line_batch_middleware
from app.agents.workspace_paths import build_workspace_path_middleware
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

from app.agents.context_budget import MAX_TOOL_ARG_CHARS, ContextBudget
from app.agents.context_policy import ContextPolicy
from app.agents.context_store import build_context_backend
from app.models import build_default_chat_model
from app.tools.agent_toolkit import (
    HUMAN_APPROVAL_TOOLS,
    build_artifact_delete_tool,
    build_artifact_move_tool,
    build_artifact_edit_tool,
    build_artifact_write_tool,
    build_line_replace_tool,
    build_repository_read_tools,
    build_sprint_history_tool,
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
        # Not every approve/reject tool runs a command. `delete_artifact` names
        # a path, and describing it as "Command: None" tells the reviewer
        # nothing about what is being removed - which is the one fact that
        # matters for a deletion.
        if command is None and args.get("relative_path"):
            return (
                f"Agent: {agent_name} (stage: {stage})\n"
                f"Tool: {tool_name}\n"
                f"File: {args['relative_path']}\n"
                f"Workspace: {repo_root}\n"
                "This permanently removes the file. Approve only if it is a temporary\n"
                "helper and not part of the deliverable.\n"
                "Allowed decisions: approve, reject"
            )
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


def _answer_fields(response_format: Any) -> frozenset[str]:
    """Field names of a stage's response schema, for the write tool.

    Used to recognise the stage's own answer being written to disk instead of
    returned - see `agent_toolkit._is_the_stages_own_answer`. Returns an empty
    set for a stage with no schema, which switches the check off.
    """
    fields = getattr(response_format, "model_fields", None)
    if not isinstance(fields, dict):
        return frozenset()
    return frozenset(fields)


def writing_tools(
    repo_root: str, answer_fields: frozenset[str] = frozenset(), schema: Any = None
) -> list[BaseTool]:
    """The mutation tools a writing role gets - always as a set.

    Create, change and remove belong together. Handed the first two and told
    scratch files must not be kept, an agent improvises the third: on
     A named list is here so the invariant is one thing
    to test rather than one call site to remember.
    """
    return [
        build_artifact_write_tool(repo_root, answer_fields, schema),
        build_artifact_edit_tool(repo_root),
        build_line_replace_tool(repo_root),
        build_artifact_delete_tool(repo_root),
        build_artifact_move_tool(repo_root),
    ]


_SUBAGENT_PROFILE_REGISTERED = False


def _disable_the_general_purpose_subagent() -> None:
    """Take the `task` tool away from every role agent.

    `create_deep_agent` installs a general-purpose subagent spawner by default.
    No role here needs one: each is a single stage with one structured answer,
    and the tools it may use are chosen deliberately - the filesystem set is
    narrowed to `ls`, `read_file`, `glob` and `grep` a few lines below, and
    every mutating call is gated. `task` arrived with none of that.

    What it cost, measured on  The stage produced
    a valid sprint plan at 15:23:30, then in the same turn called `task`, and
    the subagent it spawned ran `glob {'pattern': '**/*'}` 835 times over
    eleven and a half minutes - 802 tool calls in one stage, against 21
    assistant messages. Zero globs occurred before the first `task` call.

    The parent's `recursion_limit` does not reach inside a subagent, so nothing
    bounded it: no GraphRecursionError was ever raised. The settled-answer
    middleware could not stop it either - it reads the LAST message, and by
    then the stage was writing prose about creating files it has no tools to
    create.

    Registered under the provider key rather than the model identifier, so it
    survives a change of model - which this deployment does regularly.
    """
    global _SUBAGENT_PROFILE_REGISTERED
    if _SUBAGENT_PROFILE_REGISTERED:
        return
    try:
        from deepagents.profiles.harness.harness_profiles import (
            GeneralPurposeSubagentProfile,
            HarnessProfile,
            register_harness_profile,
        )

        register_harness_profile(
            "openai",
            HarnessProfile(
                general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)
            ),
        )
        _SUBAGENT_PROFILE_REGISTERED = True
    except Exception:  # noqa: BLE001 - an agent without this is the old behaviour
        logger.warning(
            "Could not disable the general-purpose subagent; the `task` tool "
            "will be available and is not bounded by the stage recursion limit",
            exc_info=True,
        )


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
    `FilesystemBackend` at the workspace in virtual mode means `/docs/NAME.md` -
    exactly the path shape the middleware's own prompt teaches the model to use -
    resolves inside this run's directory and nowhere else.

    Only the read tools are registered, and they are the agent's only readers:
    reading grants nothing new, since any file under the root is the
    workspace's own (`allow_subdirectories` narrows *listing* depth, never read
    access).
    """
    return FilesystemMiddleware(
        # `WorkspaceBackend`, not `FilesystemBackend`: the run's own package
        # caches live inside the workspace because container mode mounts
        # nothing else, and without this they appear in every listing an agent
        # makes. See `app.agents.workspace_backend`.
        # `hold_notes`: `read_file` numbers the text it is given, so a note
        # written into it shifts every line - see `held_read_note`.
        backend=WorkspaceBackend(root_dir=repo_root, virtual_mode=True, hold_notes=True),
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
    budget = ContextBudget.resolve()
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
                # Shorten large tool-call arguments in older messages before
                # resorting to summarisation. Left unset - which it was - the
                # trigger defaults to None and this never fires at all, so the
                # only relief available was the expensive one.
                #
                # It is also the better-aimed relief for this pipeline. The
                # bulkiest thing in an agent's history is artifact content: a
                # `write_artifact` call carries the whole document in its
                # arguments, so one 51 KB specification occupies ~13k tokens of
                # every subsequent request for the rest of the stage. The file
                # is on disk the moment the call returns; the copy in the
                # transcript is redundant once the agent has moved past it.
                truncate_args_settings={
                    "trigger": ("tokens", budget.truncate_args_trigger_tokens),
                    "keep": ("messages", policy.keep_recent_messages),
                    "max_length": MAX_TOOL_ARG_CHARS,
                },
            )
        ]
    except Exception:  # noqa: BLE001 - see docstring
        logger.warning(
            "Could not build compaction middleware for %s; continuing without it",
            agent_name, exc_info=True,
        )
        return []


def _documents_the_workflow_owns() -> str:
    """The `docs/` filenames an agent must not write, named in the prompt.

    The writing rules used to tell every specialist to put its reports in
    `docs/`, and the workflow owns nine files in there - it renders each from
    the structured response of the stage that produces it and rewrites it
    whole every time. An agent that writes one is refused, correctly, but
    nothing had told it which names were taken, so it found out by spending a
    call.

    Measured across runs 60-67: 31 such calls, from 13 different stages - every
    kind of specialist, plus two test rounds. Not one stage's mistake; the
    instruction to write into `docs/` with no list of what is already claimed.

    Read from the manifest rather than restated, so the prompt cannot fall out
    of step with the refusal. See `app.analysis.document_manifest`.
    """
    from app.tools.repository import WORKFLOW_DOCUMENTS

    return ", ".join(f"`{name}`" for name in sorted(WORKFLOW_DOCUMENTS))


_WRITING_RULES = (
    # One section per question, each said once. It had grown to about 9,000
    # characters: the directory rules twice (here and in PROJECT_LAYOUT, which
    # contradicted them - "Documents go in the workspace's `docs/`" beside
    # "Writing ANY file into `docs/` is refused"), the tool guide twice (a
    # bullet list and a table saying the same), and measurements meant for
    # the people maintaining this file rather than for the model reading it.
    # A small model given 91 rules follows fewer of them.
    "CRITICAL DIRECTORY RULES:\n"
    "- Application files go inside ONE top-level project folder: the one the\n"
    "  workspace listing names, spelled exactly as it is there. Never create a\n"
    "  second one.\n"
    "- `docs/` is the WORKFLOW's directory, not yours. It holds only these files,\n"
    "  each rendered from a stage's structured response: "
    + _documents_the_workflow_owns()
    + ".\n"
    "  Read them; writing anything into `docs/` is refused. What the next stage\n"
    "  needs from you goes in your structured response; documentation that\n"
    "  ships with the product goes in the project folder beside the code it\n"
    "  describes.\n"
    "- Scratch files (debug scripts, probes) go in the project directory; remove\n"
    "  them with `delete_artifact` when done. NEVER write a script whose purpose\n"
    "  is to delete another script.\n"
    + PROJECT_LAYOUT
    + "\n\n"
    "HOW TO WRITE - one tool for every file job:\n"
    "  list      `ls`, `glob`         what is there\n"
    "  search    `grep`               which file contains it\n"
    "  read all  `read_file`          a file; every line comes with its number\n"
    "  read part `read_file` + offset/limit, for the section of a long file\n"
    "  create    `write_artifact`     a new file\n"
    "  replace   `write_artifact`     a whole file, again\n"
    "  change lines `replace_lines`   lines by number, from a read you just made.\n"
    "                                 Pass `expect_start` (the first line as you\n"
    "                                 read it) and `expect_end` (the last line as\n"
    "                                 you read it, NOT the new text) so a range\n"
    "                                 that moved is still found\n"
    "  change    `edit_artifact`      one exact passage to its replacement\n"
    "  cut       `edit_artifact` with an empty replacement - that passage only\n"
    "  remove    `delete_artifact`    a whole file (tests are kept, not deleted)\n"
    "  relocate  `move_artifact`      rename or move, bytes unchanged\n"
    "- To revise a long file, read the part you need and change that part. Never\n"
    "  rewrite it from memory, and never save a revision under a new name\n"
    "  (`spec_v2.md`): two versions contradict each other.\n"
    "- You already have permission to write; approval is handled outside this\n"
    "  conversation. Never ask for it.\n"
    "\n"
    "PATHS - every path is inside the workspace:\n"
    "- `docs/NAME.md` and `/docs/NAME.md` are the same file.\n"
    "- Shell commands already run in the workspace directory: give them relative\n"
    "  paths, never ones starting with `/`.\n"
    "- A long absolute path quoted as the repository root is the HOST's path and\n"
    "  does not exist here. Never use it.\n"
    "\n"
    "ARTIFACTS ARE NOT YOUR STRUCTURED RESPONSE:\n"
    "- Files hold content a person reads or a program runs. Your result is\n"
    "  returned by calling your answer tool - never written to a file, never\n"
    "  printed as JSON text.\n"
    "- Write each file once. A successful write is saved; do not write it again\n"
    "  to confirm it.\n"
)

_READ_ONLY_RULES = (
    "YOUR OUTPUT:\n"
    "- You have no file-writing or editing tools, and need none. Everything you\n"
    "  produce travels in your structured response, and the workflow renders any\n"
    "  document from it. Do not look for a write tool, and do not report that one\n"
    "  is missing - nothing is missing.\n"
    "- You may read anything in the workspace with `ls`, `read_file`, `glob` and\n"
    "  `grep`, and reading widely before you answer is the whole of your job.\n"
)


#: What every stage's answer tool says about itself. It used to be the schema
#: class's docstring - notes for the people maintaining the class, such as
#: "Structured product-intake output returned by the Product Manager agent.
#: The schema deliberately mirrors ..." - so the one tool that ends a stage
#: never said that it does. On 2026-09-30, 35 failed calls were a stage writing
#: its answer into a file (`final_response.json`, `structured_response.json`).
ANSWER_TOOL_DESCRIPTION = (
    "Finish this stage: call this tool once, when your work is done, with your "
    "complete result as its arguments. It is the only way your result reaches the "
    "workflow - a file you write is not read as your result, and neither is JSON "
    "printed as text."
)


def the_answer_tool(response_format: Any) -> Any:
    """`response_format` as a tool strategy whose tool describes what it is for.

    A tool strategy is what the agent built from a bare schema already - the
    answer arrives as a call to a tool named after the schema - so only the
    description changes. Anything that is not a schema class is returned as
    it came.
    """
    if not isinstance(response_format, type):
        return response_format
    from langchain.agents.structured_output import ToolStrategy

    strategy = ToolStrategy(schema=response_format)
    for spec in strategy.schema_specs:
        spec.description = ANSWER_TOOL_DESCRIPTION
    return strategy


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
    can_write: bool = True,
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

    # A role whose document the workflow generates has no reason to hold a
    # the architecture reviewer was told "do not write a review document",
    # kept `write_artifact`, and wrote `docs/architecture_review.md` five times
    # in a row - printing its structured response as prose between each write
    # and never returning it - until the repeat guard stopped the stage.
    # Taking the tool away settles it; arguing with the model in the prompt did
    # not.
    tools = [
        # No second reader. `inspect_repository` and `read_repository_file`
        # duplicated `ls`/`glob` and `read_file` under other parameter names
        # (start_line/line_count against offset/limit), and inspect ran a fixed
        # search for this harness's own vocabulary in every product. On
        # 2026-09-30 they took 90 of 2,604 calls; a small model choosing among
        # two tools that do one job is a choice it can get wrong.
        # Read-only, and the cheap answer to a question every stage otherwise
        # works out by re-reading the workspace.
        build_sprint_history_tool(resolved_repo_root),
        *(writing_tools(resolved_repo_root, _answer_fields(response_format), response_format) if can_write else []),
        *(extra_tools or []),
    ]

    # The directory and write-tool rules are only true for an agent that has
    # workflow now renders - was handed "CRITICAL DIRECTORY RULES: Write all
    # document artifacts ... inside `docs/`" alongside "Do not write a
    # document", went looking for the tool, and reported "I don't have a
    # `write_artifact` tool or any file-writing/editing tools available"
    # instead of returning its structured response. Contradictory instructions
    # cost a stage; withholding the irrelevant half costs nothing.
    full_system_prompt = f"{system_prompt}\n\n" + (_WRITING_RULES if can_write else _READ_ONLY_RULES)

    # Compaction. Built here rather than at module scope so a policy change
    # takes effect on the next agent, not the next restart. The context
    # directory is keyed by agent name (not thread id), which is stable per
    # role; see `_compaction_middleware` for why that is deliberate.
    middleware = _compaction_middleware(name)
    middleware = [
        *middleware,
        # Ahead of the filesystem middleware so the path is already
        # root-relative by the time its tools resolve it.
        # First, so it wraps every other middleware and records the result the
        # model is actually given - notices, refusals and rewrites included.
        # `on_tool_end` fires before any of that and sees only what the tool
        # returned. See `app.observability.transcript`.
        build_transcript_middleware(stage),
        # Outermost of the model-call wrappers, so a call the server failed to
        # parse becomes a real tool call before anything downstream looks for
        # one. See `app.agents.text_tool_calls`.
        build_text_tool_call_middleware(),
        build_workspace_path_middleware(resolved_repo_root),
        # After the path rewrite, so it groups a reply's edits by the path the
        # tool will resolve. See `app.agents.line_batches`.
        build_line_batch_middleware(resolved_repo_root),
        # After the path rewrite so both see the same request the model will.
        build_workspace_digest_middleware(resolved_repo_root),
        build_plugin_instructions_middleware(resolved_repo_root),
        _workspace_filesystem_middleware(resolved_repo_root),
        # After the filesystem middleware, so it sees the tool results the
        # model will. `read_file` has its own, better notice in the backend;
        # this covers the listings and searches beside it, which had none.
        build_repeated_query_middleware(),
        # Only where there is a schema to recognise an answer by. A stage with
        # no response format has nothing to be finished with, so there is
        # nothing for this to decide. See `app.agents.settled_answer`.
        *(
            [build_settled_answer_middleware(response_format, name, MODEL_CALLS_PER_STAGE)]
            if response_format is not None
            else []
        ),
        # Last, so it cannot displace anything the rest of the chain depends
        # on, and empty unless `HARNESS_TASK_LIST` is on. See
        # `app.agents.task_list` for why it is opt-in and what would earn it a
        # default.
        *build_task_list_middleware(),
    ]

    _disable_the_general_purpose_subagent()
    agent = create_deep_agent(
        model=selected_model,
        tools=tools,
        system_prompt=full_system_prompt,
        response_format=the_answer_tool(response_format),
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

    # Kept on the agent because the compiled graph does not expose it, and the
    # workflow needs it to recognise an answer the model wrote into the
    # conversation instead of returning. Set here, once, rather than threaded
    # through the fifteen places that build an agent - reaching fourteen of
    # fifteen is the mistake this codebase has made four times.
    agent.workflow_response_format = response_format
    return agent


__all__ = [
    "create_role_agent",
    "writing_tools",
    "default_repo_root",
    "describe_artifact_write",
    "describe_tool_call",
]
