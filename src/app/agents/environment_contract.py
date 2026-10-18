"""The environment every stage runs in, told to every stage.

Only the stack selector was told the truth about the sandbox:
`describe_execution_environment()` reached no one else. Measured on one run,
the consequences arrived in three stages at once - a specification demanded a
PostgreSQL server and startup migrations on a machine with no database (its
own sandbox logged the readiness probe refused), an acceptance suite was
written against services that cannot start, and a fixer burned thirty calls on
install/list loops because a bare install landed in a user site the
acceptance server's interpreter never reads.

One contract, derived from the allowlist so it cannot drift from what the
sandbox permits, delivered to every role agent as the same append-at-end,
byte-stable block the workspace digest uses (Initiative K.1). The selector
keeps the fuller text with its selection-specific paragraphs; every stage
gets the facts and the substitution rule.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


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
        # Evidence, kept out of the prompt (X.4): 14 stored specifications
        # named Playwright and only 2 of their stacks agreed; the reviewer
        # then reported the two documents as a contradiction, a revision
        # round each time.
        "- There is still NO display and NO human. Nothing watches the screen, so\n"
        "  'manual browser testing', 'visual inspection' and 'check it in DevTools'\n"
        "  remain impossible - not because a browser is missing, but because\n"
        "  nobody is there to look. Every check must report a pass or a fail by\n"
        "  itself.\n"
    )


def describe_execution_environment() -> str:
    """What the sandbox can actually run, derived from the allowlist itself.

    The stack selector used to choose testing approaches the pipeline cannot
    perform. Measured on one run: it selected "Manual (browser DevTools)"
    for a client-side app, the technical lead faithfully delegated "execute all
    Sprint 1 test cases manually in a browser", and the testing specialist found
    no browser - none is installed and none is on any role's allowlist. Unable
    to do the work and told not to substitute, it began improvising an
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
        "  the work - it is a property of this environment. Do not plan work\n"
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


def _describe_the_browser_for_a_stage(runnable: list[str]) -> str:
    """The browser facts without the selector's selection-specific guidance.

    Worded without the product words the prompts are tested against: the
    contract reaches every stage of every run, whatever the product turns out
    to be, so it presupposes no interface vocabulary of its own.
    """
    if "playwright" in runnable:
        return (
            "- A HEADLESS browser is available, through Playwright, and it is the\n"
            "  required way to test frontend UI code here. It installs as a\n"
            "  test-only dependency of the project.\n"
            "- There is still NO display and NO human: nothing watches a screen,\n"
            "  so every check must report a pass or a fail by itself.\n"
        )
    return (
        "- There is NO browser and no display: nothing can open a page here, and\n"
        "  no human sees this workspace. Every check must report a pass or a\n"
        "  fail by itself.\n"
    )


def the_environment_contract() -> str:
    """The facts every stage needs about the sandbox, in stable bytes.

    Derived on every call from the same allowlist the sandbox enforces, so a
    capability added or removed cannot leave the contract lying; computed once
    at import into `ENVIRONMENT_CONTRACT`, so every call a process makes
    carries identical bytes and the prefix cache is never broken by it.
    """
    from app.tools.sandbox import allowed_executables

    runnable = sorted(allowed_executables("testing_specialist"))
    return (
        "The execution environment, stated once for every stage - reference, not a request:\n"
        f"- Available commands: {', '.join(runnable)}.\n"
        + _describe_the_browser_for_a_stage(runnable)
        + "- There is no network except during dependency installation.\n"
        "- NOTHING IS RUNNING except the command you start. There is no database\n"
        "  server, no message broker, no cache and no application server waiting\n"
        "  to be connected to, and no way to start one that outlives a single\n"
        "  command. Anything a design needs that this environment does not\n"
        "  provide must sit behind an adapter its tests can substitute, with\n"
        "  migrations written and reviewed rather than applied and the logic\n"
        "  that matters testable against plain objects.\n"
        "- Container and deployment files can be WRITTEN but not BUILT: there is\n"
        "  no `docker` on any role's allowlist. 'The image was not built' is a\n"
        "  property of this environment, not a defect in the work.\n"
        "- An install must land in the interpreter environment the product's own\n"
        "  commands use: a package installed where those commands cannot see it\n"
        "  is not installed.\n"
    )


#: The contract, computed on first use and byte-stable for the life of the
#: process afterwards. Not at import: `app.tools.sandbox` resolves its output
#: budget through `app.agents`, so a module-level call back into the sandbox
#: allowlist would import a half-built `sandbox` and fail every first import
#: of it. First use is an agent build or a model call, long after every
#: module is loaded. See `the_environment_contract`.
_cached_contract: str | None = None


def environment_contract_text() -> str:
    """The contract's bytes, computed once per process."""
    global _cached_contract
    if _cached_contract is None:
        _cached_contract = the_environment_contract()
    return _cached_contract


def build_environment_contract_middleware() -> Any:
    """Put the environment contract in every call's system prompt (or, with none, after the conversation).

    Built as middleware rather than added to each request builder for the
    reason the workspace digest was: there are thirteen of those, and reaching
    twelve of thirteen is the specific mistake this codebase has made four
    times. Placed outside the digest middleware, so the appended tail reads
    stable bytes first and the listing that changes last - the prefix cache
    breaks no earlier than it did before.

    Never raises into a call: a contract that cannot be attached costs the
    stage nothing but the hint.
    """
    from langchain.agents.middleware import AgentMiddleware

    class EnvironmentContractMiddleware(AgentMiddleware):
        """Append the contract to the request, not to stored history."""

        name = "EnvironmentContractMiddleware"

        def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
            messages = getattr(request, "messages", None)
            if not isinstance(messages, list):
                return handler(request)
            if os.environ.get("ENVIRONMENT_CONTRACT", "1").lower() in ("0", "false", "off"):
                return handler(request)
            try:
                # In the system prompt when there is one: the same bytes every
                # call, so they belong in the cached prefix. Appended after the
                # history they were re-prefilled on every call (Initiative AA).
                system = getattr(request, "system_message", None)
                if system is not None and isinstance(getattr(system, "content", None), str):
                    from langchain_core.messages import SystemMessage

                    request = request.override(
                        system_message=SystemMessage(content=f"{system.content}\n\n{environment_contract_text()}")
                    )
                else:
                    request = request.override(
                        messages=[*messages, {"role": "user", "content": environment_contract_text()}]
                    )
            except Exception:  # noqa: BLE001 - never fail a call over a hint
                return handler(request)
            return handler(request)

    return EnvironmentContractMiddleware()


__all__ = [
    "build_environment_contract_middleware",
    "describe_execution_environment",
    "environment_contract_text",
    "the_environment_contract",
]
