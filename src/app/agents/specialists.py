"""Specialist Deep Agents (Step 5.3).

The Technical Lead (Step 5.2) delegates scoped tasks to one of six specialist
roles: UI/UX, database, backend, testing and quality engineering,
documentation, and security/reliability. Every specialist returns the same
shape — changed files, decisions, tests, documentation, risks, and blockers —
so the Technical Lead and Milestone Reviewer can process any specialist's
output the same way. Each specialist receives only the task and context it
needs; none of them can edit files outside the approved artifact directory
without a human approval (see `app.agents.role_agent`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, create_model, field_validator, model_validator

from app.agents.testability import TESTABILITY_RULE
from app.agents.testing_dependency_rule import TESTING_DEPENDENCY_RULE
from app.agents.structured_response import STRUCTURED_RESPONSE_RULE
from app.agents.role_agent import create_role_agent, default_repo_root
from app.agents.severity import validator_for as severity_in
from app.agents.specialist_roles import role_slug
from app.agents.technical_lead import SpecialistRole
from app.tools.agent_toolkit import (
    build_journal_read_tool,
    build_terminal_command_tool,
    build_validation_tool,
)

_STAGE = "implementation"

#: What each specialist is for. Every one of these is joined by the run's own
#: stack, which `describe_stack` puts at the top of the brief - so these say
#: what the role does and defer to the stack on what to build it with.
#:
#: They did not, and four of the six named tools unconditionally: the UI
#: specialist "MUST use `run_terminal_command` to install NPM dependencies,
#: compile the code (e.g. `npm run build` or `npx tsc`)", the backend
#: specialist "MUST ... start the development server", the database specialist
#: "MUST ... install required database drivers (e.g., Prisma, TypeORM)", and
#: the testing specialist "install testing frameworks (e.g., Jest, PyTest)".
#:
#: Each of those is a "MUST" that outranks the stack in the same conversation,
#: and the harness has been paying for all four:
#:
#: - one run: a "Web LocalStorage" product whose spec said "no server-side
#:   infrastructure" four times got a 3,696-byte `server.js`, and the milestone
#:   reviewer accepted it as the product. `_a_server_in_a_browser_only_product`
#:   catches that at review; this is where it came from.
#: - one run: `stack_selector` chose "Custom JS assert tests ... avoiding
#:   large dependencies" and `specialist_ui_ux_0` installed jest anyway, then
#:   spent four `npm test` calls on `TextEncoder is not defined`.
#: - the testing specialist's own round brief says "Do not install a test
#:   framework or add a dependency", so that agent was handed both sentences
#:   in one conversation.
#:
#: The mandate to write complete, working code rather than designs is kept -
#: that one is not in conflict with anything and the runs it fixed stay fixed.
_ROLE_DESCRIPTIONS: dict[SpecialistRole, str] = {
    "ui_ux": (
        "You are the UI and UX specialist. You MUST write complete, "
        "production-ready frontend code. Do NOT just 'design' or output "
        "snippets. Build and verify it the way this run's stack says: where the "
        "stack has a build step, run it with `run_terminal_command` and fix "
        "every compilation and linter error before returning; where the stack "
        "is plain HTML/CSS/JS with no build tooling, there is nothing to "
        "install or compile, and adding either contradicts the stack. "
        "CRITICAL: Do NOT write, run, or fix tests. Do NOT run test frameworks. "
        "Leave testing to the Testing specialist. Just return your structured "
        "response when the application code is complete. "
        "CRITICAL: Do NOT remove, disable, or 'separate' core application logic or "
        "UI logic in order to make testing easier or to satisfy headless test framework "
        "errors. The UI logic must be fully functional."
    ),
    "database": (
        "You are the Database specialist. You MUST write complete, executable "
        "schema files and migrations. Work in the data layer this run's stack "
        "actually chose: where it names a database server or an ORM, use "
        "`run_terminal_command` to install the driver, generate the client, run "
        "the migrations, and verify there are no syntax or type errors. Where "
        "the stack's storage lives in the client itself - storage built into "
        "the browser or the device - there is no server, no driver and no "
        "migration to run: model the data in the code the client loads."
    ),
    "backend": (
        "You are the Backend specialist. You MUST write fully functional server "
        "code, APIs, and domain logic. Do NOT just output 'designs' or "
        "scaffolds. Use `run_terminal_command` to install what the stack needs, "
        "compile, and verify the service starts without crashing, fixing errors "
        "iteratively. Where this run's stack has no server - storage in the "
        "browser, no backend framework - there is no service to start, and "
        "writing one creates a second data layer the product never talks to: "
        "implement the logic in the code the page loads instead."
    ),
    "testing": (
        "You are the Testing and Quality Engineering specialist. You define and "
        "run unit, integration, contract, end-to-end, accessibility, and "
        "security regression tests for the delegated task. Use the testing "
        "approach this run's stack chose, and the validation tool to actually "
        "run the tests rather than only describing them. Do NOT introduce a "
        "different test runner: one the stack did not choose fails on its own "
        "setup rather than on the product. If the stack names none, verify with "
        "the runner that ships with the stack's language. "
        "CRITICAL: Do NOT remove, disable, or 'separate' core application logic or "
        "UI logic to satisfy test environment limitations (e.g. headless test errors "
        "or a missing display). You must test the real UI logic end-to-end, "
        "through the real interface, with the driver the stack's own guidance "
        "names. Report "
        "every failure as a structured defect in the `defects` field, naming "
        "the specialist role that must fix it, so the workflow can track and "
        "route it."
    ),
    "documentation": (
        "You are the Documentation specialist. You write beginner-readable "
        "explanations, ADR usage docs, and operational runbooks for the "
        "delegated task. Use `run_terminal_command` to verify markdown formatting or generate site documentation if applicable."
    ),
    "security_reliability": (
        "You are the Security and Reliability specialist. You review and implement "
        "authorization, data isolation, secrets handling, retries, and "
        "observability for the delegated task. Use `run_terminal_command` to run static analysis tools or security linters."
    ),
}


class ReportedDefect(BaseModel):
    """One test failure, as reported by the Testing specialist (Step 5.4).

    This is the *agent-facing* defect shape, deliberately separate from
    `app.sprint.Defect`, which is the controller's tracking record. The
    difference matters: `Defect` also carries lifecycle fields (`status`,
    `regression_test`, `accepted_risk_reason`) that only the workflow may set.
    Exposing those to the model would let it declare its own defects fixed.

    `owner` is typed as `SpecialistRole` rather than a free string so the model
    must name one of the six real specialists. The plan's gate forbids
    accepting a sprint with unowned defects, and a defect owned by "the team"
    or "whoever wrote it" is exactly that - unroutable. That gate is what this
    field protects, and it still holds: `owner` stays required and stays one of
    the six. Only the spelling is forgiven - "Testing Specialist" and "backend
    service" name real roles and now reach them; "the team" still does not and
    is still refused.

    `ignore` rather than `forbid`, and aliases on `description` - for the
    reason spelled out on `VerificationRun` below, measured again on
    one run's `defect_fix_2_0`. The Testing specialist wrote a real,
    well-described defect as

        {"name": "LocalStorage Integration Failure in Unit Tests",
         "description": "addTask does not persist tasks to localStorage...",
         "status": "Unresolved"}

    `name` and `status` are not fields here, so `forbid` threw the whole answer
    away; `settled_answer` could then not recognise it as an answer, so the
    stage wrote it again, five times, until the repeat guard stopped the run.
    A defect the model described correctly was lost over the two keys it added
    around it. `status` in particular is the one field this shape deliberately
    withholds - so refusing it also taught the model nothing, because the
    answer it needed to send has no place to put what it was trying to say.
    Dropping the extra keys keeps the defect and keeps the withholding.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    description: str = Field(
        ...,
        validation_alias=AliasChoices("description", "name", "title", "summary", "defect"),
        description="Short summary of what is wrong.",
    )
    severity: Literal["blocking", "major", "minor"] = Field(..., description="Impact level of this failure.")
    reproduction_steps: str = Field(..., description="How to reliably reproduce the failure.")
    expected_behavior: str = Field(..., description="What should have happened.")
    actual_behavior: str = Field(..., description="What actually happened.")
    affected_files: list[str] = Field(default_factory=list, description="Files implicated in this failure.")
    owner: SpecialistRole = Field(..., description="Which specialist role must fix this defect.")
    regression_test_required: bool = Field(
        default=True,
        description="Whether closing this defect requires a new or updated regression test. Normally true.",
    )

    # "High" is not in this vocabulary and is in two of the other three the
    # same model is asked for elsewhere in the same run. See
    # `app.agents.severity`.
    _known_severity = field_validator("severity", mode="before")(
        severity_in("blocking", "major", "minor")
    )

    @field_validator("owner", mode="before")
    @classmethod
    def _role_slug(cls, value: Any) -> Any:
        """Accept the role written the way a person writes it.

        The prompt names the roles as slugs and the model answers "Testing
        Specialist", "Backend", "QA" - the same role, spelled for a reader.
        Refusing that loses the routing information it was trying to give.
        """
        return role_slug(value)


class VerificationRun(BaseModel):
    """One command a specialist ran to prove its work, and what happened.

    Free-text `tests` was the only evidence, so `["ran pytest, all green"]` was
    indistinguishable from having run it. This is checkable:
    `app.tools.sandbox.read_execution_ledger` holds what actually executed in
    this workspace, and a claim here that is absent there is one the model
    invented.
    """

    # `ignore`, not `forbid`, and aliases on `exit_code` - because the shape the
    # model sends here is the shape this harness handed it. `run_terminal_command`
    # returns {"stdout", "stderr", "returncode"}, so a model asked for
    # "the command you ran with its exit code" pastes that record back, and
    # `forbid` then rejected every key of it.
    #
    # One run died of exactly that. `specialist_testing_5` was refused
    # three times over `verification.0.exit_code`, `.exitCode`, `.returncode`,
    # `.stdout`, `.category` and `.working_directory`, could not produce a
    # valid answer, and so `settled_answer` could not recognise one and end the
    # stage - the model wrote the same answer five times and the run-level
    # repeat guard stopped the run at 758 events.
    #
    # What `forbid` was protecting is still protected: a claim here is checked
    # against `read_execution_ledger`, which is what makes it evidence rather
    # than assertion. Rejecting the answer outright never caught an invented
    # command; it only cost the stage its ability to finish.
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    command: list[str] = Field(
        # `["pytest", "-q"]` was the example, and `pytest` is not in the
        # execution image - an example is strong guidance, and this one pointed
        # at a program that is not there.
        description='The argv you ran, e.g. ["<program>", "<arg>", ...].'
    )
    exit_code: int = Field(
        validation_alias=AliasChoices("exit_code", "returncode", "exitCode", "return_code"),
        description="The `returncode` the tool returned. 0 means success.",
    )
    summary: str = Field(default="", description="One line on what it proved, or how it failed.")

    @field_validator("command", mode="before")
    @classmethod
    def _as_argv(cls, value: Any) -> Any:
        """Accept the command as a string as well as a list.

        The tool takes argv and the prompt asks for argv, but a model that just
        ran `node --test app.mjs` writes it back the way a person would. Turning
        that into a list is unambiguous and keeps the record, where refusing it
        loses the whole answer.
        """
        if isinstance(value, str):
            return value.split()
        return value


class SpecialistOutput(BaseModel):
    """Structured result every specialist returns, regardless of role.

    One shared shape lets the Technical Lead and Milestone Reviewer integrate
    results from any specialist without role-specific parsing logic.
    """

    model_config = ConfigDict(extra="forbid")

    changed_files: list[str] = Field(
        default_factory=list,
        description="Files this specialist changed or proposes to change (paths only; actual edits go through review).",
    )
    decisions: list[str] = Field(default_factory=list, description="Notable decisions made while doing this task.")
    tests: list[str] = Field(default_factory=list, description="Tests added, updated, or run for this task.")
    verification: list[VerificationRun] = Field(
        default_factory=list,
        description=(
            "Commands you actually executed to prove this task works, with their exit codes. "
            "Leave empty only if you executed nothing. Do not describe commands here that you "
            "did not run - the workspace keeps its own record of every execution and the two "
            "are compared."
        ),
    )
    documentation: list[str] = Field(default_factory=list, description="Documentation added or updated for this task.")
    risks: list[str] = Field(default_factory=list, description="Risks introduced or discovered by this task.")
    blockers: list[str] = Field(default_factory=list, description="Anything preventing this task from being completed.")
    defects: list[ReportedDefect] = Field(
        default_factory=list,
        description=(
            "Test failures found during this task. Only the testing specialist normally fills this in; "
            "every other role should leave it empty and use `blockers` instead."
        ),
    )



def _an_answer_says_something(cls: Any, data: Any) -> Any:
    """Refuse a model's answer in which every field is empty.

    Every field of `SpecialistOutput` defaults to empty, so `{}` validated and
    ended the stage. On one run a defect-fix stage reasoned through a reply's
    whole output budget, was asked to answer with its tools withheld, wrote
    "fixed 1 of 3 ... let me write a debug script" - and called
    `SpecialistOutput` with `{}`. It named no fix and no regression test, so the
    defect stayed open, and the next fixer did the same: rounds 3, 4 and 5 on
    one defect while every test round in between reported none.

    Refused, the validation error goes back to the model on its next call, with
    its tools restored. Only for the answer a live agent sends: see
    `AGENT_ANSWER`.
    """
    if isinstance(data, dict) and not any(
        value not in (None, "", [], {}) for value in data.values()
    ):
        raise ValueError(
            "Every field of this answer is empty, so it reports nothing and cannot "
            "end the stage. Say what you changed (`changed_files`), what you ran and "
            "how it ended (`verification`), the regression test that proves a fix "
            "(`tests`), and anything unfinished or in your way (`blockers`). If the "
            "work is not finished, keep working - your tools are available again."
        )
    return data


#: The schema a live specialist agent answers with: `SpecialistOutput`, same
#: name and fields - so the tool the model calls is still `SpecialistOutput` -
#: that refuses an all-empty answer. The base class stays permissive, because
#: code and test doubles build empty instances on purpose.
AGENT_ANSWER = create_model(
    "SpecialistOutput",
    __base__=SpecialistOutput,
    __validators__={
        "_an_answer_says_something": model_validator(mode="before")(
            classmethod(_an_answer_says_something)
        )
    },
)


NO_SHELL_NOTE = (
    "There is no shell in this environment: `sh`, `bash` and shell scripts "
    "cannot be run, and nor can `cd`, pipes or `&&`. A build or test step must "
    "therefore be a script declared in the project's own manifest and run "
    "through its package manager, or a program run directly with "
    "`run_terminal_command` - never a .sh file. `make`, `pnpm` and `yarn` are "
    "not installed here either.\n"
)
"""The constraint that is invisible until a stage has already spent itself.

The first version of this offered "an npm/pnpm/yarn script, a Makefile target"
- and `make`, `pnpm` and `yarn` are all three absent from the execution image,
so three of its four suggestions were dead ends. Measured 2026-09-16 with
`shutil.which` inside the worker; see B2 in `docs/harness-improvement-plan.md`
for the full list. Advice has to name something that is there.

Measured on one run. The technical specification called for a shell build
script, so `simple-to-do-list-app/build.sh` became the most-written file of the
entire run - 22 writes and edits across several stages - for a file the sandbox
can never execute. `specialist_backend_0` then sent `sh ./build.sh` five times,
and `specialist_backend_8` wrote `docs/blocker.md` five times because being
blocked was all it had left to report. The run had completed a full sprint, a
test round, a security review and a milestone review before this ended it.

Nothing in any brief said a shell was unavailable. The allowlist says so, but
only once a command has already been refused - which is after the spec is
written, the task delegated and the script authored.
"""


def _no_code_on_the_command_line(stack: Any) -> str:
    """The inline-code refusal this stack's own toolchain will hand back, or "".

    Measured on one run: `specialist_backend_1`, `specialist_testing_2`
    and `specialist_ui_ux_0` each sent the byte-identical
    `node -e "import('./simple-to-do-list/app.js').then(...)"`, and each was
    refused. Three of the run's seven failed calls were that one command.

    The run-scoped counter did its job - the second and third were told "already
    refused 1/2 time(s) ... it will be refused every time" - and it could not
    possibly have helped: those three stages run in parallel, so stage two had
    already formed its command before stage one's refusal existed. No reactive
    message reaches a stage that has not made its call yet. Only the brief does.

    This is the shape `NO_SHELL_NOTE` exists for, whose docstring names the
    problem exactly: the allowlist says so, "but only once a command has already
    been refused". The same was true of every inline-eval flag.

    Derived from `_FORBIDDEN_ARGS` rather than spelled out here, so a language
    added to the boundary is named in the brief without a second edit, and
    filtered through `_installed` so it cannot warn against a program this image
    does not have.
    """
    from app.tools.sandbox import (
        _FORBIDDEN_ARGS,
        _WHY_THE_ARGUMENT_IS_REFUSED,
        TOOLCHAINS,
        _installed,
        _toolchain_key,
    )

    programs: set[str] = set()
    for attribute in ("language", "framework", "frontend_framework", "testing_framework"):
        key = _toolchain_key(str(getattr(stack, attribute, "") or ""))
        if key:
            programs |= TOOLCHAINS.get(key, frozenset())
    evaluators = {
        name
        for name in programs & set(_FORBIDDEN_ARGS)
        if _WHY_THE_ARGUMENT_IS_REFUSED.get(name) == "eval"
    }
    present, _absent = _installed(evaluators)
    if not present:
        return ""
    spellings = [
        f"`{name} {flag}`"
        for name in present
        for flag in sorted(_FORBIDDEN_ARGS[name])
    ]
    return (
        "Code cannot be handed to a program as an argument. This is refused "
        "every time, for what it is, and no edit to any file changes that: "
        + ", ".join(spellings)
        + ". To execute something once, write it to a file in the project "
        "folder, run the file, then remove it with `delete_artifact`. If what "
        "you actually need is what is already in a file, `read_file` and `grep` "
        "answer that in one call without running anything.\n"
    )


_THE_UNIT_RUNNER_IS_NOT_THE_ONLY_ONE = (
    "The testing framework above is the unit suite's. If this product has a web "
    "UI, the end-to-end runner that the testability rule requires is ADDITIONAL "
    "to it, not a competing choice: both belong in the project, the end-to-end "
    "runner belongs in the manifest's development dependencies, and its presence "
    "there is not a deviation from this stack. Do not remove it and do not "
    "report it as a stack violation. What IS a defect is a test file nothing in "
    "the project can run, so the manifest's test command must run both suites.\n"
)
"""Reconciles the two rules in this brief that told a stage opposite things.

`describe_stack` says "Do not introduce a different language, framework,
database or test runner". `TESTABILITY_RULE`, in the same brief, says "FOR
FRONTEND WEB UI CODE ONLY: YOU MUST USE Playwright (`@playwright/test`) ...
Install it using `npm i -D @playwright/test`". For a UI product whose stack
names a unit runner - which is every UI product, because a stack records one
testing framework - those cannot both be satisfied, and nothing said which won.

Measured on one run, which oscillated and then shipped the wreckage.
`defect_fix_4_6` added a `test:e2e` script; `specialist_backend_1` then made
`test` run both suites, which is exactly what the cross-file check asks for.
The next test round raised "@playwright/test installed despite stack choosing
node --test - Playwright tests should use the chosen stack or be removed", and
`defect_fix_2_0` obeyed it: out went the script, the `test:e2e` entry and both
devDependencies.

It could not finish the job. `delete_artifact` refuses a test file - "tests are
part of what this run delivers" - so the 396-line spec and its config stayed.
Every action left a check firing, and the run completed with "Nothing in the
project runs them at all" outstanding as a blocking-grade finding against the
delivered product.

Stated here because all three request builders take `describe_stack` - the
specialist task, the test round that raised the defect, and the defect fix that
acted on it - so one place reaches every stage in that loop.

Worded without naming a tool. The testability rule names it, and for a stack
whose UI is not JavaScript the runner is a different program; what has to be
said is that an end-to-end runner and a unit runner are not rivals.
"""


#: Languages where a module system is a choice the files must share.
_HAS_A_MODULE_SYSTEM = ("javascript", "typescript")


def _how_the_pieces_load(stack: Any) -> str:
    """The one cross-cutting choice the stack does not record, or "".

    The stack decides the language, the framework, the database and the test
    runner. It does not decide how a module is loaded, and nothing else does
    either - the specification is silent on it in every stored run but one.
    So each specialist chooses alone: the page gets a plain `<script>` tag,
    the application file gets `export`, the suite gets `import`, and the three
    do not agree.

    That disagreement is the most expensive recurring failure in this harness.
    Five separate cross-file checks exist to catch its shapes, and six runs each spent
    rounds on it.

    What is stated here is not a preference. Both combinations work, and a
    stage is free to pick either - what cannot work is picking differently in
    three files, which is what happens when nobody says so.
    """
    language = str(getattr(stack, "language", "") or "").lower()
    if not any(name in language for name in _HAS_A_MODULE_SYSTEM):
        return ""
    return (
        "How the pieces load each other is one choice, not three. The page, "
        "the application file and the tests must share it, and only two "
        "combinations hold together:\n"
        "- ES modules: the file uses `export`, the page loads it with "
        '`<script type="module" src="...">`, and the tests `import` from it.\n'
        "- CommonJS: the file assigns `module.exports` or browser globals, the "
        "page loads it with a plain `<script src=\"...\">`, and the tests "
        "`require` it.\n"
        "Mixing them is the single most expensive mistake made in this "
        "workspace: `export` behind a plain script tag throws on page load, "
        "and `module.exports` behind `type=\"module\"` throws too - in both "
        "cases the tests still pass, because they import the file directly and "
        "never open the page. Read what is already there before you write, and "
        "match it.\n"
    )


def project_contract(repository_root: str) -> str:
    """How the project was set up and which parts the harness owns, or "".

    Every stage that writes code or tests is told the same thing: the commands,
    where unit tests go, that the acceptance suite is locked. See
    `app.stacks.contract`.
    """
    try:
        from app.stacks.contract import describe

        return describe(repository_root)
    except Exception:  # noqa: BLE001 - a brief without it is the brief as it was
        return ""


def describe_stack(stack: Any) -> str:
    """The chosen stack, as the one specialists must build on.

    A specialist used to be given its task, its acceptance criteria and nothing
    about the technology. Each one then guessed, and reasonable guesses differ.

    Measured on one run, whose stack selection was Python / FastAPI /
    PostgreSQL / pytest / React: the project directory ended up holding two
    complete, incompatible backends. One specialist wrote `package.json` with
    express, jsonwebtoken and mongoose plus `src/routes/auth.js` and a jest
    suite; another wrote `main.py` with FastAPI and a `requirements.txt`. Both
    were sensible answers to "build the authentication endpoints". Neither was
    told that a database and a test framework had already been chosen, or that
    the other existed.

    Returns an empty string when no stack was recorded, so an older run or a
    test fixture without one is unaffected.
    """
    if stack is None:
        return ""
    fields = (
        ("Language", "language"),
        ("Framework", "framework"),
        ("Frontend framework", "frontend_framework"),
        ("Database", "database"),
        ("Testing framework", "testing_framework"),
    )
    lines = [
        f"- {label}: {value}"
        for label, attribute in fields
        if (value := getattr(stack, attribute, "") or "")
    ]
    extra = list(getattr(stack, "additional_tools", None) or [])
    if extra:
        lines.append(f"- Other tools: {', '.join(str(tool) for tool in extra)}")
    if not lines:
        return ""
    return (
        "--- The technology stack for this project (already decided) ---\n"
        + "\n".join(lines)
        + "\nBuild on exactly this. Do not introduce a different language, "
        "framework, database or test runner, even if one would suit your task "
        "better - other specialists are building the rest of this product on "
        "the stack above, and a second one in the same directory means neither "
        "works. If your task cannot be done on this stack, say so as a blocker "
        "rather than switching.\n"
        + _THE_UNIT_RUNNER_IS_NOT_THE_ONLY_ONE
        + _how_the_pieces_load(stack)
        + NO_SHELL_NOTE
        + _no_code_on_the_command_line(stack)
        + "\n"
    )


def _task_names_a_workflow_document(task_description: str, criteria: list[str]) -> str:
    """Warn a specialist whose task asks it to change a file it cannot, or "".

    `PROJECT_LAYOUT` tells the Technical Lead these documents are the
    workflow's and must not be written. One run shows a prompt is not
    enough: the lead delegated "update `docs/milestone_review.md` with the test
    results", and `specialist_documentation_1` spent twelve model calls on it -
    writing a `# Task Status` note four times, byte-identical, explaining that
    the task requires updating a file the tool refuses, and rewriting the
    technical specification three times.

    Refusing the whole milestone plan over one task would cost the other five.
    Telling the specialist, in the brief it actually reads, costs nothing and
    reaches the stage that is about to waste itself.
    """
    from app.tools.repository import WORKFLOW_DOCUMENTS

    haystack = " ".join([task_description, *criteria]).lower()
    named = sorted(
        name for name in WORKFLOW_DOCUMENTS if name.lower() in haystack
    )
    if not named:
        return ""
    listed = ", ".join(f"docs/{name}" for name in named)
    return (
        f"--- About {listed} ---\n"
        "This task names a document the workflow writes itself, from the "
        "structured response of the stage that produces it, and rewrites whole "
        "every time that stage runs. You cannot change it - the tool refuses - "
        "and a copy beside it is read by nobody. Do the part of this task that "
        "is real work, and put anything that belongs in that document into your "
        "structured response instead: `decisions` for what you did, `risks` and "
        "`blockers` for what is wrong. Those reach the workflow. A note saying "
        "the task could not be done adds nothing - this paragraph is already "
        "that note.\n\n"
    )


#: How many shared files one note names. Past a couple the two tasks are the same
#: task and the lead's plan is the thing to fix, not the wording of a note.
MAX_SHARED_FILES_NAMED = 3


def _a_file_another_specialist_is_also_given(
    task_description: str,
    acceptance_criteria: Sequence[str],
    other_tasks: Sequence[Any],
) -> str:
    """The note for a file this task shares with another specialist's, or "".

    In parallel mode these specialists run at the same time, so a whole-file
    `write_artifact` from one discards whatever the other has just written. The
    workspace lock serialises the writes; it cannot make them agree.

    Measured across the 27 current-generation runs: 157 writes were one stage
    writing content byte-identical to what a *different* stage had already
    written. One run is the clearest - three specialists each wrote the same
    `package.json`, the same `app.js`, the same test file and the same
    `jest.config.cjs`. Two of each three produced nothing, having each paid a
    model call to generate it.

    The cause is upstream: of 25 stored sprint plans, 17 assign the same file to
    more than one specialist. `_SYSTEM_PROMPT` in `technical_lead` now asks for one
    owner per file, and this is what the specialist is told when the plan does it
    anyway - a note rather than a refusal, because two tasks touching one file is
    sometimes the right plan and never this stage's fault.
    """
    try:
        from app.analysis.planned_files import paths_a_plan_named

        mine = set(paths_a_plan_named([task_description, *acceptance_criteria]))
        if not mine:
            return ""
        theirs: set[str] = set()
        for other in other_tasks or ():
            description = str(getattr(other, "task_description", "") or "")
            if description and description == task_description:
                continue  # this task itself
            theirs.update(
                paths_a_plan_named(
                    [description, *(getattr(other, "acceptance_criteria", None) or ())]
                )
            )
        shared = sorted(mine & theirs)
    except Exception:  # noqa: BLE001 - a brief is better without this than absent
        return ""
    if not shared:
        return ""
    named = ", ".join(f"`{name}`" for name in shared[:MAX_SHARED_FILES_NAMED])
    return (
        f"--- A file another specialist is also working on ---\n"
        f"{named} is named by another task in this sprint, and that specialist may "
        "be running right now. Change only the part of it your task covers, with "
        "`edit_artifact` or `replace_lines`. A whole-file `write_artifact` would "
        "discard their work, and it is the most common wasted call in this "
        "pipeline: across the stored runs 157 writes were one stage writing "
        "byte-for-byte what another had already written. If your task cannot be "
        "done without rewriting the file, say so in your structured response "
        "rather than doing it.\n\n"
    )


def build_specialist_task_request(
    task_description: str,
    acceptance_criteria: list[str],
    repository_root: str,
    stack: Any = None,
    other_tasks: Sequence[Any] = (),
    work_order: Any = None,
) -> dict[str, list[dict[str, str]]]:
    """Build the Deep Agent input for one delegated specialist task.

    `work_order` is the `SpecialistTask` itself, whose files, interfaces, steps,
    edge cases, test cases and verification commands are the rest of the
    ticket - see `app.analysis.work_orders`. The testing task is also given the
    other tasks' interfaces and test cases, so it writes tests against the
    contract while the code is written from it.
    """
    from app.analysis.work_orders import brief_for, contract_for_testing

    criteria_text = "\n".join(f"- {criterion}" for criterion in acceptance_criteria)
    order = ""
    if work_order is not None:
        order = brief_for(work_order) + contract_for_testing(work_order, list(other_tasks or ()))
    brief = (
        # Deliberately not the host repository path. Inside the agent the
        # workspace is rooted at "/", and quoting the host path here sends
        # agents looking for files under a root that does not exist for them.
        f"The workspace is rooted at '/'; all paths you use are relative to it.\n\n"
        f"{describe_stack(stack)}"
        f"{project_contract(repository_root)}"
        f"--- Delegated task ---\n{task_description}\n\n"
        f"--- Acceptance criteria ---\n{criteria_text}\n\n"
        f"{order}"
        f"{_task_names_a_workflow_document(task_description, acceptance_criteria)}"
        f"{_a_file_another_specialist_is_also_given(task_description, acceptance_criteria, other_tasks)}"
        f"**CRITICAL INSTRUCTION**: All application code lives in ONE project directory at the workspace root. Run `ls` FIRST: if a project directory already exists, write into that exact directory, spelled exactly as it already is. Only create one if none exists, naming it after this product in lowercase-with-hyphens. Never scaffold directly in the workspace root, never use a generic name like 'nest-app', and never create a second project directory. Documentation that ships with the product goes inside that project directory beside the code it describes. `docs/` is the workflow's own directory and writing anything into it is refused.\n"
    )
    return {"messages": [{"role": "user", "content": brief}]}


def build_test_run_request(
    milestone_goal: str,
    changed_files: list[str],
    repository_root: str,
    stack: Any = None,
    planned: Sequence[str] = (),
    later_sprints: str = "",
    brief: str = "",
    acceptance: str = "",
) -> dict[str, list[dict[str, str]]]:
    """Build the Testing specialist's input for one verification round (Step 5.4).

    `acceptance` is the harness's own run of the locked acceptance suite, made
    just before this round: every failing criterion that is due is a defect to
    report, with its owner.

    This is the loop's step 2, "the Test Engineer runs the tests applicable to
    that increment", and it is a separate invocation from the testing task the
    Technical Lead may have delegated during implementation. Every failure it
    finds must come back as a structured `ReportedDefect` so the controller can
    track and route it, rather than as prose in `blockers` that nothing can act
    on.

    The cross-file checks are handed over with the brief, which they were not
    before. `summarise_integration` ran in one place - as evidence for the
    milestone reviewer - so a defect it proves could only be raised after the
    test rounds had finished and a green suite had already been reported, and
    fixing it then costs a whole milestone revision.

    Measured on one run, which failed its first sprint in eight minutes.
    Its plan delegated "Create style.css with basic responsive CSS rules",
    `index.html` linked that file, no tool call in the run ever touched it, and
    `_broken_local_references` proves that by reading the two files. The suite
    was green, the test rounds reported nothing, and the milestone reviewer
    raised it as blocking three times until the run hit the revision limit.

    This stage is where a defect is supposed to be found, and it was the one
    stage not told. A problem here enters the remediation cycle that already
    exists for defects, inside the sprint, instead of costing a revision of it.

    Only the tier `summarise_integration` itself calls breaking. The judgement
    ones - a dead CSS rule, an export no test mentions - are not defects and
    would turn this stage's report into a style review.
    """
    files_text = "\n".join(f"- {name}" for name in changed_files) or "- (none reported)"

    proven = what_the_files_already_prove(repository_root, stack, planned, later_sprints, brief)
    proven_text = ""
    if proven:
        proven_text = (
            "--- Already proven by reading the files, before you run anything ---\n"
            "Each of these was decided by comparing two files in this workspace, "
            "not by judgement, so none of them depends on your agreement and none "
            "will be fixed by a passing suite. Report every one as a defect, with "
            "the role that must fix it:\n"
            + "\n".join(f"- {problem}" for problem in proven)
            + "\n\n"
        )
    brief = (
        f"The workspace is rooted at '/'; all paths you use are relative to it.\n\n"
        f"{describe_stack(stack)}"
        f"{project_contract(repository_root)}"
        f"--- Milestone under test ---\n{milestone_goal}\n\n"
        f"--- Files changed in this milestone ---\n{files_text}\n\n"
        f"{acceptance}"
        f"{proven_text}"
        "Run the unit, integration, contract, end-to-end, accessibility, and security "
        "tests that apply to this increment, using the testing approach this project "
        "already chose. Use the run_validation tool to actually execute them.\n\n"
        "Do not install a test framework or add a dependency. If the stack above names "
        "no testing framework, that was a decision - the product is meant to be "
        "verified the way the stack says, and initialising a package manager or "
        "installing a package here creates the very dependency the brief ruled out. If you cannot run a check without "
        "new tooling, report that as a blocker instead of installing it.\n\n"
        "Report EVERY failure in the `defects` field, each with a severity, reproduction "
        "steps, expected behavior, actual behavior, affected files, and the specialist "
        "role that must fix it. If everything passes, return an empty `defects` list. "
        # The write tools refuse product code in a test round - see
        # `_a_tester_changing_the_product` - so say it before the first try.
        "You do not change product code yourself: a fault in it is a defect for the "
        "role that owns the file, which is how the fix gets an owner and a record. "
        "Tests, test configuration and the package manifest are yours to change.\n\n"
        # One run's last test round saw its suite print "QuotaExceededError is
        # not defined" three times, called it "a non-fatal warning" under
        # `risks`, and passed the milestone. The product's storage error
        # handler named a class that does not exist, so the failure path the
        # brief asked for threw instead of recovering; every test passed
        # because none of them reached it with a real failure.
        "A passing exit code is not the whole result: read what the run printed. An "
        "error the product itself reports while the tests pass - a name that is not "
        "defined, an exception it caught and logged, a stack trace - is a defect in "
        "the code that printed it, not a risk. The suite passed because no assertion "
        "looks at that path. Report it in `defects`.\n\n"
        # One run shipped, through two test rounds, a security review and two
        # milestone reviews, a product whose add form refused an empty title and
        # whose inline edit saved one: clearing a title and pressing Enter left a
        # task with no name. Every suite tested edit with a new non-empty value.
        "A rule the product enforces on one path must hold on every path that sets "
        "the same value. If creating something refuses an empty, oversized or "
        "malformed value, send that value through every other way the product "
        "changes it - update, import, a second interface to the same data. A path "
        "that lets through what another refuses is a defect."
    )
    return {"messages": [{"role": "user", "content": brief}]}


def what_the_files_already_prove(
    repository_root: str,
    stack: Any = None,
    planned: Sequence[str] = (),
    later_sprints: str = "",
    brief: str = "",
) -> list[str]:
    """The problems a test round is handed as proven, before it runs anything.

    One list for the brief and for the workflow that reads the round's answer,
    so a problem the round leaves out can be told from one it was never shown.
    Never raises.
    """
    proven = []
    try:
        from app.analysis.integration_checks import problems_that_break_the_product

        # With the operator's brief, as the milestone review has it: the checks
        # that compare the product against it quote its lines, not the run's
        # restatement of them.
        proven = problems_that_break_the_product(repository_root, stack, brief)
        # A requirement a later sprint builds is not this sprint's defect. See
        # `planned_for_a_later_sprint`.
        from app.analysis.integration_checks import planned_for_a_later_sprint

        proven = [p for p in proven if not planned_for_a_later_sprint(p, later_sprints)]
    except Exception:  # noqa: BLE001 - a brief is better without them than absent
        proven = []
    try:
        from app.analysis.planned_files import files_the_plan_named_that_are_missing

        # The one comparison the workspace cannot make against itself. A file
        # planned and never written is referenced by nothing, so nothing on disk
        # is inconsistent and no check that reads only the workspace can see it.
        # One run finished a "single-page application" with no HTML file,
        # 34 tests passing, and three test rounds reporting no defect.
        #
        # Where a locked acceptance suite measures the product, it can see that
        # case (a page with no HTML fails every criterion), and a file the plan
        # named and nobody wrote says something about the plan, not about
        # whether the product works. One run's first sprint passed its criteria
        # and was still handed `src/storage.js` as a proven defect three rounds
        # running.
        from app.analysis.integration_checks import _behaviour_is_measured

        if not _behaviour_is_measured(Path(repository_root)):
            proven = proven + files_the_plan_named_that_are_missing(planned, repository_root)
    except Exception:  # noqa: BLE001 - same reason
        pass
    return proven


def _observed_output(observed: dict[str, str] | None) -> str:
    """The last failing command and what it printed, or "" if there is none."""
    if not observed or not observed.get("output"):
        return ""
    return (
        "--- What the last failing command actually printed ---\n"
        f"$ {observed.get('command', '')}\n"
        f"{observed['output']}\n\n"
        "The description above is another specialist's reading of a failure and "
        "may be out of date or wrong about the cause; this is the machine's own "
        "output. Where the two disagree, believe this, and reproduce it yourself "
        "before changing anything.\n\n"
    )


def build_defect_fix_request(
    description: str,
    reproduction_steps: str,
    expected_behavior: str,
    actual_behavior: str,
    affected_files: list[str],
    regression_test_required: bool,
    repository_root: str,
    stack: Any = None,
    observed: dict[str, str] | None = None,
    caught_by: str = "",
) -> dict[str, list[dict[str, str]]]:
    """Build the input that routes one tracked defect to the specialist who owns it.

    This is the loop's steps 4 and 5: the Technical Lead routes the defect, and
    the owning specialist fixes it *and* adds a regression test. The regression
    test is not optional politeness - the plan's gate refuses to accept a sprint
    with missing regression coverage, so the request states that requirement
    explicitly and the specialist must name the test in its `tests` field.

    `observed` is what the last failing command actually printed, from
    `app.observability.transcript.last_failing_command`. Everything above it in
    this brief is the *reporting* specialist's prose reading of a failure, and
    prose drifts: on one run `defect_fix_2_1` was briefed to find a
    "Syntax error in createElementFallback ... Unexpected token '}'" in a file
    that had no syntax error, while the suite was failing on a different line
    for a different reason. Both belong in the brief - the prose carries the
    judgement about which failure matters, the output carries the facts.
    """
    files_text = "\n".join(f"- {name}" for name in affected_files) or "- (none identified)"
    regression_clause = (
        # "Fails before your fix and passes after it" was read, by one run, as
        # a request for a test that expects the failure: it wrote "import fails
        # before fix" and asserted that the error occurred.
        "You MUST also add or update a regression test - one that asserts the correct "
        "behaviour this defect broke, so it would fail on the code as it was and passes "
        "on yours - and name that test in your `tests` field. A fix with no named "
        "regression test cannot be accepted."
        if regression_test_required
        else _not_the_product_clause(affected_files)
        or _already_caught_clause(caught_by)
        or "A regression test is not required for this defect, but name any test you did run."
    )
    brief = (
        f"The workspace is rooted at '/'; all paths you use are relative to it.\n\n"
        f"{describe_stack(stack)}"
        f"{project_contract(repository_root)}"
        "A test failure has been assigned to you to fix.\n\n"
        f"--- Defect ---\n{description}\n\n"
        f"--- Reproduction steps ---\n{reproduction_steps}\n\n"
        f"--- Expected behavior ---\n{expected_behavior}\n\n"
        f"--- Actual behavior ---\n{actual_behavior}\n\n"
        f"--- Affected files ---\n{files_text}\n\n"
        f"{_observed_output(observed)}"
        f"{regression_clause}\n\n"
        "Fix only this defect. If you cannot fix it, say why in `blockers` rather than "
        "claiming it is resolved."
    )
    return {"messages": [{"role": "user", "content": brief}]}


def _already_caught_clause(caught_by: str) -> str:
    """What replaces the new-test requirement when a test command already fails, or ""."""
    if not caught_by:
        return ""
    return (
        f"`{caught_by}` already fails because of this, so the test for it exists: that "
        "command passing is the proof of your fix. Add no new test for this defect. "
        "Find what makes the command fail - the product, or a test that is "
        "itself wrong - fix that, run the command again, and name it in your `tests` "
        "field."
    )


def _not_the_product_clause(affected_files: list[str]) -> str:
    """What to do about a defect that lies only in tests or throwaway scripts, or "".

    The workflow already drops the regression-test requirement for these (see
    `workflow._needs_a_regression_test`); this says what replaces it. Without
    it, one run's fix stages repaired a debugging script four rounds running
    and wrote a "regression test" for it each time, and the next round tested
    those.
    """
    from app.analysis.file_kinds import is_scratch, is_test

    names = [str(name) for name in affected_files or [] if str(name).strip()]
    if not names or not all(is_test(name) or is_scratch(name) for name in names):
        return ""
    throwaway = [name for name in names if is_scratch(name) and not is_test(name)]
    tests = [name for name in names if is_test(name)]
    parts = []
    if throwaway:
        listed = ", ".join(f"'{name}'" for name in throwaway)
        parts.append(
            f"{listed} {'is' if len(throwaway) == 1 else 'are'} named like a debugging "
            "script, which is not part of what this run delivers. If nothing in the "
            "product, its manifest or its tests runs it, the fix is to delete it with "
            "`delete_artifact` - not to repair it, and not to write tests for it."
        )
    if tests:
        parts.append(
            "A defect in a test is not a defect in the product, so the corrected test is "
            "its own proof: fix it, run it, and name it in your `tests` field. Do not "
            "write another test about it."
        )
    else:
        parts.append("No regression test is needed; name any test you did run.")
    return " ".join(parts)


#: Only the testing role is given `run_validation` - it runs under the testing
#: allowlist, which carries jest, vitest, mocha and tsc, so handing it to every
#: role would widen their allowlists by the back door.
#:
#: The shared responsibilities used to say "use `run_terminal_command` (or
#: `run_validation`)" to all six, so four of them were pointed at a tool they
#: do not hold. That is the one run fault - the scrum master spent a stage
#: reporting "I don't have a `write_artifact` tool" instead of answering - and
#: the reason `role_agent` withholds the writing rules from a read-only agent.
_VALIDATION_NOTE = (
    "- `run_validation` runs the project's test command inside the project "
    "directory for you, which is the one place the project's own test command "
    "resolves correctly. "
    "Prefer it over `run_terminal_command` for running tests.\n"
)


def _system_prompt(role: SpecialistRole) -> str:
    """Build the full system prompt for one specialist role."""
    role_description = _ROLE_DESCRIPTIONS[role]
    validation = _VALIDATION_NOTE if role == "testing" else ""
    return f"""{role_description}

Responsibilities:
- Complete only the delegated task and its stated acceptance criteria; do not
  expand scope on your own initiative.
- Report every changed file, notable decision, added or updated test, added or
  updated documentation, risk, and blocker.
- Prove your work by running it. Write the code, then use `run_terminal_command`
  to build it, start it, or test it, and record every command you ran in
  `verification` with its exit code. A task reported complete with an empty
  `verification` list is a task nobody checked.
{validation}- If a command's output was truncated, call `read_command_output` with the
  reference in the truncation pointer to see the part that was cut. The real
  error is usually there.
- If you cannot verify something (a test, a security property), say so as a
  risk or blocker instead of asserting it is fine.
- **NEVER remove or disable application logic** merely to make a test pass in the
  test environment. If the environment lacks something the product needs, fix the
  test setup with the tooling this run's stack guidance names, never the product.

Beginner documentation requirement:
- Any non-obvious code or configuration you describe must explain purpose,
  inputs, outputs, control flow, failure behavior, and security assumptions in
  your `documentation` field or inline comments you propose.

Constraints:
- You may use the `run_terminal_command` tool to execute shell commands, build code, install dependencies, and perform end-to-end development.
- There is no shell, so `cd`, `&&`, `|` and `$(...)` do not work and `cd` is not
  a program you can run. To act on a subdirectory, pass `working_directory` -
  for a project directory named `myapp`, run `["<program>", "<args>"]` with
  `working_directory="myapp"` rather than trying to change into it first.
- Commands run at the workspace root unless you pass `working_directory`. Run
  package-manager and test commands in the project directory, not at the root:
  the root has no manifest of yours, and creating one there makes a second
  project that disagrees with the real one.
- Every write_artifact call pauses for a human decision before anything is
  saved; never claim the artifact is saved until a tool result confirms it.
- **Write the complete artifact in ONE single write_artifact call.** Do NOT
  make follow-up edit calls to refine, fix typos, or improve the document after
  the initial write. The document must be complete and correct before you write
  it. Once the write is confirmed, immediately return your structured response.
- Keep the output structured and concise.

{TESTABILITY_RULE}

{TESTING_DEPENDENCY_RULE}

Return the response in the required output schema only.

{STRUCTURED_RESPONSE_RULE}
"""


def create_specialist_agent(
    role: SpecialistRole,
    model: str | BaseChatModel | None = None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    repo_root: str | Path | None = None,
        allow_subdirectories: bool = True,
) -> Any:
    """Create one specialist role worker.

    The `testing` specialist gets one extra tool (`run_validation`) so it can
    actually execute an allowlisted test command instead of only describing
    what should be tested; every other specialist gets the same narrow
    read/write tools as any other role agent.
    """
    resolved_repo_root = str(repo_root) if repo_root is not None else str(default_repo_root())

    # One execution path only. The previous `get_execution_tools` helpers ran
    # `subprocess.run(shell=True)` directly on the host with no containment, and
    # sat alongside the sandboxed tool as a silent fallback whenever the
    # container runtime was missing - which is exactly what happened in the
    # shipped image. Everything now goes through the contained executor.
    extra_tools = [
        build_terminal_command_tool(resolved_repo_root, role_name=f"{role}_specialist"),
        # Paired with the command tool, never on its own: only a command can
        # produce the truncation pointer this reads back. The root is passed so a
        # lost pointer can be answered with this run's own entries.
        build_journal_read_tool(resolved_repo_root),
    ]

    if role == "testing":
        extra_tools.append(build_validation_tool(resolved_repo_root))

    return create_role_agent(
        name=f"specialist_{role}",
        stage=_STAGE,
        system_prompt=_system_prompt(role),
        response_format=AGENT_ANSWER,
        model=model,
        checkpointer=checkpointer,
        repo_root=repo_root, allow_subdirectories=allow_subdirectories,
        extra_tools=extra_tools,
    )


__all__ = [
    "ReportedDefect",
    "SpecialistOutput",
    "build_defect_fix_request",
    "build_specialist_task_request",
    "build_test_run_request",
    "create_specialist_agent",
]
