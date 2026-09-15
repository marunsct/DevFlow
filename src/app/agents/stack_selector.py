"""Stack Selector Agent (Phase 2).

This role worker consumes the approved product intake and the Tools and Models
output, and produces a single unified TechnologyStack choice.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field

from app.agents.structured_response import STRUCTURED_RESPONSE_RULE
from app.agents.role_agent import create_role_agent
from app.agents.tools_models import TechnologyStack
from app.state import RepositoryContext

_STAGE = "stack_selector"
_NAME = "stack_selector"


class StackSelectorOutput(BaseModel):
    """Structured technology stack selection."""

    model_config = ConfigDict(extra="forbid")

    technology_stack: TechnologyStack = Field(..., description="The chosen integrated stack.")
    rationale: str = Field(..., description="Why this stack was chosen.")


def _truncate(text: str, max_chars: int | None = None) -> str:
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


def build_stack_selector_request(
    product_intake_text: str, tools_models_text: str, repository: RepositoryContext
) -> dict[str, list[dict[str, str]]]:
    """Build the Deep Agent input from the approved product intake and tools models."""
    brief = (
        # Deliberately not the repository's absolute path. That is the HOST's
        # path; inside the agent the workspace is rooted at "/". Quoting it here
        # and then telling the agent never to use it does not work - measured on
        # run-0b55ad49, agents retried `ls` against that exact string four times
        # in a row, and fed it to shell commands, every attempt failing with
        # path_not_found. The reliable fix is not to show it.
        f"Repository: branch {repository.branch}, commit {repository.commit}\n"
        f"The workspace is rooted at '/'; all paths you use are relative to it.\n\n"
        f"--- Approved product intake ---\n{_truncate(product_intake_text)}\n\n"
        f"--- Tools and Models Comparison ---\n{_truncate(tools_models_text)}\n"
    )
    return {"messages": [{"role": "user", "content": brief}]}


def describe_execution_environment() -> str:
    """What the sandbox can actually run, derived from the allowlist itself.

    The stack selector used to choose testing approaches the pipeline cannot
    perform. Measured on run-3da8dd91: it selected "Manual (browser DevTools)"
    for a client-side app, the technical lead faithfully delegated "execute all
    Sprint 1 test cases manually in a browser", and the testing specialist found
    no browser - none is installed and none is on any role's allowlist. Unable
    to do the task and told not to substitute, it began improvising an
    automated harness with npm instead.

    A testing approach nothing can execute is not a testing approach: every
    later stage that asks "did the tests pass?" gets no answer, and the
    milestone reviewer treats an absent test run as a blocking finding.

    Derived rather than written out, so the list cannot drift away from what the
    sandbox actually permits.
    """
    from app.tools.sandbox import allowed_executables

    runnable = sorted(allowed_executables("testing_specialist"))
    return (
        "The execution environment - what a specialist can actually run:\n"
        f"- Available commands: {', '.join(runnable)}.\n"
        "- There is NO browser and no display. Nothing can open a page, click a\n"
        "  button, or read DevTools. 'Manual browser testing' cannot be carried\n"
        "  out here by anyone: no human sees this workspace either.\n"
        "- There is no network except during dependency installation.\n"
        "- NOTHING IS RUNNING except the command you start. There is no database\n"
        "  server, no message broker, no cache and no application server waiting\n"
        "  to be connected to, and no way to start one that outlives a single\n"
        "  command. A brief may still *require* PostgreSQL, and you should still\n"
        "  choose it - but the design has to be verifiable without a live one:\n"
        "  data access behind an adapter the tests can substitute, migrations\n"
        "  written and reviewed rather than applied, and the logic that matters\n"
        "  tested against plain objects. A stack whose tests need a running\n"
        "  server produces no evidence here, and every later stage is asked\n"
        "  'did this work?'.\n"
        "- Container and deployment files can be WRITTEN but not BUILT. There is\n"
        "  no `docker` on any role's allowlist, because the daemon socket is\n"
        "  root on the host. A Dockerfile or a compose file is delivered and\n"
        "  reviewed as text, and 'the image was not built' is not a defect in\n"
        "  the work - it is a property of this environment. Do not plan a task\n"
        "  whose acceptance depends on building or running one.\n"
        "- Choose a testing approach from the list above, one that runs headless\n"
        "  and reports a pass or fail. If the product's constraints rule out every\n"
        "  such option, say so in your rationale and choose the lightest one that\n"
        "  still runs - a test nothing can execute leaves every later stage unable\n"
        "  to answer 'did this work?'.\n- Prefer a runner the runtime already provides over one that must be\n"
        "  installed. `node --test` and Python's `unittest` ship with their\n"
        "  runtimes and cost nothing to add; jest, vitest and their peers pull in\n"
        "  tens of thousands of files. Measured on run-cbd22a34: choosing vitest\n"
        "  over `node --test` for a to-do list took the workspace from 46 MB to\n"
        "  221 MB, against a brief reading \"no external dependencies\". Reach for\n"
        "  an installed framework when the product's size or risk earns it.\n"
        "- THAT IS AN ARGUMENT FOR THE BUILT-IN RUNNER, NOT AGAINST TESTING. A\n"
        "  built-in runner installs nothing, adds no dependency and costs no\n"
        "  lines of product code, so no size or dependency limit can rule it out.\n"
        "  'None' and 'manual testing' are the same answer and both are refused:\n"
        "  they mean nothing will ever answer 'did this work?', and every later\n"
        "  stage has to.\n"
        "  Measured on run-2f252e4e, which read the paragraph above and chose\n"
        "  'Testing Framework: None - manual browser testing via DevTools is\n"
        "  adequate for a 500-line app; installing a test runner would consume the\n"
        "  entire code budget'. There was nothing to install and no budget to\n"
        "  consume; the run shipped a checklist for a human who does not exist.\n"
        ""
    )


EXECUTION_ENVIRONMENT = describe_execution_environment()

_SYSTEM_PROMPT = f"""You are the Stack Selector for this workflow.

Your role is to turn an approved product intake and a technology comparison 
into a definitive, unified technology stack for the project.

Responsibilities:
- Choose the primary language, framework, database, and testing framework.
- When the product has a user interface built separately from the backend, also
  choose `frontend_framework`. A brief naming both a backend and a frontend
  requirement needs both fields filled: a frontend named only in your rationale
  is not a selection, and no later stage reads the rationale. Leave it empty
  only when the product genuinely has no separate frontend.
- The choices must be cohesive and compatible with each other.
- Output the selection as a structured TechnologyStack.
- Do not write a document. The workflow renders `docs/technology_stack.md`
  from the selection you return, so a document you write is a second copy
  that can disagree with the one the run acts on.

A constraint in the intake is a boundary, not a preference:
- If the intake limits the technology - "only HTML/CSS/JavaScript", "no
  external dependencies", "no build step" - you may not select something
  outside that limit, however standard it is. Say what you would have chosen
  and why the constraint rules it out instead.
- Size the stack to the product. A project the intake caps at a few hundred
  lines does not carry the same tooling as a system with a team behind it, and
  every dependency you add is one the builders must install, configure and
  debug before they write any of the product.
- Observed on run-95ca3f72: an intake reading "single-page application using
  only HTML/CSS/JavaScript" and "code size capped at 500 lines" produced a
  stack with two test frameworks. Configuring them consumed the entire sprint
  and all three of its remediation attempts; the application itself was never
  started. A stack that cannot be stood up is worse than a plainer one that
  can.
- A tool for a feature the product does not have yet is not part of this
  stack. "Useful when we add notifications later" is a reason to choose it
  later; every dependency here is one the builders must install and configure
  before they write any of the product. Put those in the specification's
  future-work section instead, where they cost nothing.
- Prefer what the runtime already provides, but it must actually be present:
  see the execution environment below. A browser is not available.
- Prefer what the runtime already provides, and reach for a framework only when
  the product's size or risk actually calls for one.

{EXECUTION_ENVIRONMENT}
Constraints:
- Do not modify application source code and do not install dependencies.
- Ground choices in the provided product intake and tools models comparison.
- Keep the output structured and concise.
- Output ONLY the requested schema.

{STRUCTURED_RESPONSE_RULE}
"""


def create_stack_selector_agent(
    model: str | BaseChatModel | None = None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    repo_root: str | Path | None = None,
    allow_subdirectories: bool = True,
) -> Any:
    """Create the Stack Selector role worker."""
    return create_role_agent(
        name=_NAME,
        stage=_STAGE,
        system_prompt=_SYSTEM_PROMPT,
        response_format=StackSelectorOutput,
        model=model,
        checkpointer=checkpointer,
        repo_root=repo_root,
        allow_subdirectories=allow_subdirectories,
        # The workflow renders `docs/technology_stack.md` from the selection.
        # Holding a write tool as well is what ended run-0b18e403 at stage
        # three: the stage printed its answer into the conversation, wrote the
        # document, printed it again, wrote again - five identical writes
        # before the repeat guard stopped it. Taking the tool away settles it;
        # arguing with the model in the prompt did not, twice before.
        can_write=False,
    )


__all__ = [
    "StackSelectorOutput",
    "build_stack_selector_request",
    "create_stack_selector_agent",
]
