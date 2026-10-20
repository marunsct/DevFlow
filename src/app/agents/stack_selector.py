"""Stack Selector Agent (Phase 2).

This role worker consumes the approved product intake and the Tools and Models
output, and produces a single unified TechnologyStack choice.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field

from app.agents.structured_response import STRUCTURED_RESPONSE_RULE
from app.agents.testing_dependency_rule import TESTING_DEPENDENCY_RULE
from app.agents.role_agent import create_role_agent
from app.tools.docs import docs_tools
from app.tools.web_search import web_tools
from app.tools.mcp_tools import tools_for as mcp_tools_for
from app.tools.package_registry import lookup_tools
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
        # one run, agents retried `ls` against that exact string four times
        # in a row, and fed it to shell commands, every attempt failing with
        # path_not_found. The reliable fix is not to show it.
        f"Repository: branch {repository.branch}, commit {repository.commit}\n"
        f"The workspace is rooted at '/'; all paths you use are relative to it.\n\n"
        f"--- Approved product intake (/docs/product_intake.md) ---\n{_truncate(product_intake_text)}\n\n"
        f"--- Tools and Models Comparison (/docs/tools_and_models.md) ---\n{_truncate(tools_models_text)}\n"
    )
    return {"messages": [{"role": "user", "content": brief}]}


# The environment description moved to `app.agents.environment_contract` so
# every stage can be told the same derived truth, not only this one; the
# selector keeps the fuller text with its selection-specific paragraphs.
from app.agents.environment_contract import describe_execution_environment  # noqa: E402

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
- Observed: an intake asking for a single page built with only the platform's
  built-in languages, and "code size capped at 500 lines", produced a stack
  with two test frameworks. Configuring them consumed the entire sprint
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

{TESTING_DEPENDENCY_RULE}
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
        # Holding a write tool as well is what ended one run at stage
        # three: the stage printed its answer into the conversation, wrote the
        # document, printed it again, wrote again - five identical writes
        # before the repeat guard stopped it. Taking the tool away settles it;
        # arguing with the model in the prompt did not, twice before.
        can_write=False,
        # Versions move faster than any model's training: see `app.tools.package_registry`.
        extra_tools=[*lookup_tools(), *docs_tools(), *web_tools(), *mcp_tools_for("stack_selector")],
    )



#: A browser runner named in `testing_framework`. Matched on word boundaries so
#: "playwright" inside a longer word does not count.
_NAMES_A_BROWSER_RUNNER = re.compile(
    r"(?<![a-z0-9])(playwright|cypress|puppeteer|selenium|webdriver|testcafe|nightwatch)"
    r"(?![a-z0-9])",
    re.I,
)

#: What a stack says about itself when the product runs in a browser. Read from
#: the stage's own answer rather than from the brief: the model has just decided
#: what this product is, and its own words for that are a better signal than
#: keyword-matching a document it was summarising.
_A_BROWSER_PRODUCT = re.compile(
    r"(?<![a-z0-9])(html|css|dom|browser|localstorage|sessionstorage|indexeddb|spa"
    r"|single[-\s]page|react|vue|angular|svelte|frontend|front[-\s]end)(?![a-z0-9])",
    re.I,
)


def the_browser_runner_this_stack_forgot(stack: Any) -> str | None:
    """`testing_framework` with the browser runner added, or None if fine.

    The prompt above already says this, in capitals and with the measurement
    behind it: "A PRODUCT WITH A USER INTERFACE NEEDS BOTH RUNNERS, AND NAMING
    BOTH IS THE RIGHT ANSWER ... write both into `testing_framework`". This
    enforces it, because saying it was not enough.

    Measured on one run, whose brief asked for a "Simple web-based
    interface with HTML/CSS/JavaScript". The stack came back with
    `testing_framework: node --test` and a rationale ending "adequately verified
    by testing its core logic and manual browser verification" - a method the
    same prompt calls impossible twice over, because there is no display and
    nobody to look at one.

    Its specialists then did the right thing: `package.json` ran
    `test:unit && test:e2e` with `@playwright/test` declared. So the delivered
    product was correct and the stack document disagreed with it, which is a
    blocking finding - `_a_test_runner_the_stack_did_not_choose` reports a
    package the stack did not name. That fires against every UI run whose
    specialists behave well, and the fix is for the stack to say what the
    environment actually provides.

    Keyed on the stack's own description of the product, not on the brief. A
    stack that already names any browser runner is left exactly as it is, and so
    is one for a product with no browser in it.
    """
    declared = str(getattr(stack, "testing_framework", "") or "").strip()
    if not declared or _NAMES_A_BROWSER_RUNNER.search(declared):
        return None
    about = " ".join(
        str(getattr(stack, field, "") or "")
        for field in ("framework", "frontend_framework", "database", "language")
    )
    if not _A_BROWSER_PRODUCT.search(about):
        return None
    # The example the prompt itself gives, so the document reads the way the
    # instruction asked for.
    return f"{declared} for the logic, Playwright for the page"


#: Where one sentence of a rationale ends and the next begins.
_BETWEEN_SENTENCES = re.compile(r"(?<=[.!?])\s+")

#: A sentence saying the product is checked by a person looking at it.
_CHECKED_BY_HAND = re.compile(
    r"\bmanual(?:ly)?\b[^.!?]*\b(?:test|verif|check|inspect|browser)"
    r"|\b(?:test|verif|check|inspect)\w*\b[^.!?]*\bmanual(?:ly)?\b",
    re.I,
)


def the_rationale_for_the_corrected_runner(rationale: str, corrected: str) -> str:
    """The rationale, once the workflow has added the browser runner it argued against.

    `the_browser_runner_this_stack_forgot` corrects one field and the stage's
    prose was left as written - and the prose is where the stage explained why
    it had left the runner out. One run's document then read, eleven lines
    apart, "Testing framework: node:test for the logic, Playwright for the
    page" and "Playwright is not needed because this product has no separate
    frontend layer to automate ... verified by opening the single HTML file in
    a browser". The architect specified Playwright, as the field says; the
    reviewer raised the contradiction with the rationale as blocking three
    reviews running, and the architect cannot edit this document.

    So the case against is taken out with the field it argued for: every
    sentence naming a browser runner - the stack named none, so each is about
    not using one - and every sentence that has the product checked by hand.
    What was recorded, and why, is said in its place.
    """
    paragraphs: list[str] = []
    for paragraph in str(rationale or "").split("\n"):
        if not paragraph.strip():
            paragraphs.append(paragraph)
            continue
        kept = [
            sentence
            for sentence in _BETWEEN_SENTENCES.split(paragraph)
            if not _NAMES_A_BROWSER_RUNNER.search(sentence)
            and not _CHECKED_BY_HAND.search(sentence)
        ]
        if kept:
            paragraphs.append(" ".join(kept))
    note = (
        f"Testing framework, as recorded by the workflow: {corrected}. This product "
        "runs in a browser, and nothing here can open it and look: there is no display "
        "and nobody watching, so what the browser shows is tested by a browser runner, "
        "beside the runner the logic uses. A runner used only for testing is not part "
        "of what ships, so a limit on the product's dependencies or size does not "
        "rule it out."
    )
    body = "\n".join(paragraphs).rstrip()
    return f"{body}\n\n{note}" if body else note


__all__ = [
    "StackSelectorOutput",
    "build_stack_selector_request",
    "create_stack_selector_agent",
    "the_browser_runner_this_stack_forgot",
    "the_rationale_for_the_corrected_runner",
]
