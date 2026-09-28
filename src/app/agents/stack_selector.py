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
        f"--- Approved product intake (/docs/product_intake.md) ---\n{_truncate(product_intake_text)}\n\n"
        f"--- Tools and Models Comparison (/docs/tools_and_models.md) ---\n{_truncate(tools_models_text)}\n"
    )
    return {"messages": [{"role": "user", "content": brief}]}


def _describe_the_browser(runnable: list[str]) -> str:
    """What this environment can and cannot do with a browser, derived.

    This paragraph used to assert "There is NO browser and no display", which
    was true when it was written and became false on 2026-09-17: the
    `TESTABILITY_RULE` now makes Playwright mandatory for frontend UI code and
    the Dockerfile installs Chromium's system libraries for it.

    Nothing told this stage. So the stack selector was choosing a testing
    approach against a statement that a browser could not exist, while the
    specialist downstream was ordered to use one - and `_must_be_runnable`
    rejected the phrase "headless browser testing with Playwright" because
    Playwright was on no allowlist. Three copies of one fact, and a capability
    added to one of them.

    Derived from the allowlist rather than asserted, so the next capability
    change cannot leave a prompt lying. The half that is still true is stated
    separately: there is no display and no human, so a *manual* or *visual*
    check remains impossible however good the browser is.
    """
    automated = "playwright" in runnable
    if not automated:
        return (
            "- There is NO browser and no display. Nothing can open a page, click a\n"
            "  button, or read DevTools. 'Manual browser testing' cannot be carried\n"
            "  out here by anyone: no human sees this workspace either.\n"
        )
    return (
        "- A HEADLESS browser is available, through Playwright, and it is the\n"
        "  required way to test frontend UI code here. It installs as a test-only\n"
        "  dependency of the project, so a brief that forbids\n"
        "  external dependencies does not rule it out: a test-scoped package\n"
        "  ships to nobody and is not part of the product.\n"
        "- A PRODUCT WITH A USER INTERFACE NEEDS BOTH RUNNERS, AND NAMING BOTH\n"
        "  IS THE RIGHT ANSWER. They test different things and neither can do\n"
        "  the other's job: the built-in runner tests logic you can import and\n"
        "  call, and nothing built into a language runtime can open a page,\n"
        "  click a button or read what the DOM now says. So write both into\n"
        "  `testing_framework` - for example '<the language's built-in runner>\n"
        "  for the logic, Playwright for the page' - rather than choosing one and\n"
        "  leaving the\n"
        "  other to be discovered later.\n"
        "  Measured across the stored workspaces: 14 technical specifications\n"
        "  name Playwright and only 2 of their technology stacks agree. In the\n"
        "  other 12 this stage chose the built-in runner alone while the\n"
        "  architect, reading the same environment, chose Playwright, and the\n"
        "  architecture reviewer then reported the two documents as a\n"
        "  contradiction - which costs a revision round every time.\n"
        "- There is still NO display and NO human. Nothing watches the screen, so\n"
        "  'manual browser testing', 'visual inspection' and 'check it in DevTools'\n"
        "  remain impossible - not because a browser is missing, but because\n"
        "  nobody is there to look. Every check must report a pass or a fail by\n"
        "  itself.\n"
    )


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
        + _describe_the_browser(runnable)
        + "- There is no network except during dependency installation.\n"
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
        "  installed - for the part of the product it can actually reach. See\n"
        "  the browser paragraph above: this preference is about which runner\n"
        "  tests your LOGIC, and it does not remove the need for a browser\n"
        "  runner if the product has a page.\n"
        "  A runner that ships with the language's runtime costs nothing to\n"
        "  add; a third-party runner and its peers can pull in tens of\n"
        "  thousands of files. Observed: choosing an installed runner\n"
        "  over the runtime's built-in one for a small app took the workspace\n"
        "  from 46 MB to 221 MB, against a brief reading \"no external\n"
        "  dependencies\". Reach for\n"
        "  an installed framework when the product's size or risk earns it.\n"
        "- THAT IS AN ARGUMENT FOR THE BUILT-IN RUNNER, NOT AGAINST TESTING. A\n"
        "  built-in runner installs nothing, adds no dependency and costs no\n"
        "  lines of product code, so no size or dependency limit can rule it out.\n"
        "  'None' and 'manual testing' are the same answer and both are refused:\n"
        "  they mean nothing will ever answer 'did this work?', and every later\n"
        "  stage has to.\n"
        "  Observed: a selection that read the paragraph above still chose\n"
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
        # Holding a write tool as well is what ended run-0b18e403 at stage
        # three: the stage printed its answer into the conversation, wrote the
        # document, printed it again, wrote again - five identical writes
        # before the repeat guard stopped it. Taking the tool away settles it;
        # arguing with the model in the prompt did not, twice before.
        can_write=False,
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

    Measured on run-1bdbc08a, whose brief asked for a "Simple web-based
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


__all__ = [
    "StackSelectorOutput",
    "build_stack_selector_request",
    "create_stack_selector_agent",
    "the_browser_runner_this_stack_forgot",
]
