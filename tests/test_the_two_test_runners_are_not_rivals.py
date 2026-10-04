"""One brief must not mandate a tool and forbid it in the same breath.

`describe_stack` tells every stage "Do not introduce a different language,
framework, database or test runner". `TESTABILITY_RULE`, in the same brief, says
"FOR FRONTEND WEB UI CODE ONLY: YOU MUST USE Playwright (`@playwright/test`) ...
Install it using `npm i -D @playwright/test`".

A stack records one testing framework, so for every UI product those two cannot
both be satisfied, and nothing in the brief said which won.

Measured on one run, which oscillated and then shipped the result:

    #1308  defect_fix_4_6        added a `test:e2e` script
    #1728  specialist_backend_1  made `test` run both suites
    #1814  defect_fix_2_0        removed the script, the entry and both
                                 devDependencies

The last one was obeying a defect the test round raised - "@playwright/test
installed despite stack choosing node --test ... Playwright tests should use the
chosen stack or be removed" - and it could not finish, because `delete_artifact`
refuses a test file. The 396-line spec and its config stayed, and the run
completed with a blocking-grade finding against the delivered product:
"`package.json` runs `node --test app.test.mjs`, which cannot run
`simple-to-do-list/e2e/app.spec.ts` ... Nothing in the project runs them at all."

Every action open to that stage left a check firing. That is the shape this
tests against: not one rule being wrong, but two being irreconcilable.
"""

from __future__ import annotations

import pytest


class Stack:
    language = "JavaScript"
    framework = "None (Vanilla HTML/CSS/JavaScript)"
    frontend_framework = ""
    database = "Browser localStorage"
    testing_framework = "node --test"
    additional_tools: tuple[str, ...] = ()


def _described() -> str:
    from app.agents.specialists import describe_stack

    return describe_stack(Stack())


def test_the_stack_note_says_the_two_runners_coexist() -> None:
    described = _described()

    assert "ADDITIONAL" in described, (
        "the brief forbids a second test runner and mandates one, without "
        "saying that a unit runner and an end-to-end runner are not rivals"
    )
    assert "not a deviation from this stack" in described


def test_the_note_forbids_reporting_it_as_a_violation() -> None:
    """The defect that started the oscillation was exactly this report."""
    described = _described()

    assert "do not report it as a stack violation" in described.lower()


def test_the_note_still_requires_one_command_to_run_both() -> None:
    """Keeping the runner is only half of it.

    A spec nothing runs is what the cross-file check reports, and it is what the
    run actually shipped.
    """
    described = _described()

    assert "run both suites" in described


def test_the_reconciliation_names_no_tool() -> None:
    """The testability rule names the tool; this must not.

    For a stack whose UI is not JavaScript the end-to-end runner is a different
    program, and a stack note that hardcoded one would be wrong there.
    """
    from app.agents.specialists import _THE_UNIT_RUNNER_IS_NOT_THE_ONLY_ONE

    lowered = _THE_UNIT_RUNNER_IS_NOT_THE_ONLY_ONE.lower()
    for tool in ("playwright", "cypress", "selenium", "puppeteer", "node --test"):
        assert tool not in lowered, f"the stack note hardcodes `{tool}`"


@pytest.mark.parametrize(
    "builder",
    ("build_specialist_task_request", "build_test_run_request", "build_defect_fix_request"),
)
def test_every_stage_in_the_loop_is_told(builder: str) -> None:
    """The specialist wrote it, the test round objected, the defect fix removed it.

    All three take `describe_stack`, so all three must carry the reconciliation;
    telling only the specialist would leave the objection coming back.
    """
    import inspect

    from app.agents import specialists

    source = inspect.getsource(getattr(specialists, builder))

    assert "describe_stack(stack)" in source, (
        f"{builder} no longer includes the stack note, so it would not receive "
        "the reconciliation either"
    )


def test_the_mandate_a_stage_reads_really_does_require_the_runner() -> None:
    """The premise of this file, asserted rather than assumed.

    If the testability rule ever stops mandating an end-to-end runner for UI
    code, there is no contradiction left to reconcile and this whole file should
    be revisited rather than kept passing.
    """
    from app.agents.testability import TESTABILITY_RULE
    from app.plugins.seed import SEED_INSTRUCTIONS

    # Every stack is told a user interface is verified through the real one...
    assert "verify it through the real interface with an automated driver" in " ".join(
        TESTABILITY_RULE.split()
    )
    # ...and a page's own guidance names the runner and how to install it.
    assert "with Playwright" in SEED_INSTRUCTIONS["html"]
    assert "npm i -D @playwright/test" in SEED_INSTRUCTIONS["html:setup"]


def test_the_specialist_prompt_carries_the_mandate() -> None:
    """Both halves of the contradiction have to reach one stage.

    The rule is in the system prompt and the stack note is in the request; a
    specialist reads both, which is why the reconciliation has to be in one of
    them rather than left to inference.
    """
    import inspect

    from app.agents import specialists

    module = inspect.getsource(specialists)

    assert "{TESTABILITY_RULE}" in module
    assert "describe_stack(stack)" in module
