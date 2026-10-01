"""Work orders: what a specialist is handed, and the check before it is handed.

A software team gives a developer who is new to a codebase more than one line
of intent. The technical lead writes the ticket so it can be done without
guessing: which files, which contracts, the steps, the edge cases, how it will
be tested and how to check it. This workflow's specialists are that new
developer on every task - they start each one knowing nothing of the codebase
but what the brief says - and the weaker the model, the more the brief has to
carry.

`SpecialistTask` carries those fields. This module does two things with them.

`readiness_problems` is the definition of ready: a check, before dispatch, that
a plan is complete enough to hand out. Only what can be decided without
judgement - a code task that names no files, a file outside the project, a
task nothing will test, a command the sandbox will refuse. A plan that fails it
goes back to the lead once, with the list; one that still fails is dispatched
anyway with the problems written onto it, because a lead that cannot produce
the field is better served by a note than by a failed run.

`brief_for` renders one task's work order for the specialist that does it, and
`contract_for_testing` gives the testing task every other task's interfaces and
test cases - contract first: the tests are written against what the plan says
the code will do, at the same time as the code, not against whatever the code
turns out to do.

Nothing here names a language, a framework or a kind of product.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence

#: Roles whose task is not code the product runs, so they need not name files
#: or test cases.
_NOT_CODE = frozenset({"documentation"})
#: The role that turns other tasks' test cases into tests.
_TESTING = "testing"


def _role(task: Any) -> str:
    return str(getattr(task, "specialist_role", "") or "")


def _label(index: int, task: Any) -> str:
    title = str(getattr(task, "title", "") or "").strip()
    if not title:
        first = next((line.strip() for line in str(getattr(task, "task_description", "")).splitlines() if line.strip()), "")
        title = first[:70] + ("..." if len(first) > 70 else "")
    return f"work order {index} ({_role(task)}: {title})"


def _outside_the_project(path: str, project_dir: str) -> str:
    """Why `path` is not a place this task may write, or ""."""
    clean = str(PurePosixPath(path.strip().lstrip("/")))
    if not clean or clean == ".":
        return "is empty"
    if clean.split("/", 1)[0] == "docs":
        return "is inside docs/, which the workflow writes and no task may"
    if project_dir and not (clean == project_dir or clean.startswith(project_dir + "/")):
        return f"is outside the project directory '{project_dir}/'"
    return ""


def with_borrowed_files_noted(milestone: Any) -> Any:
    """The plan with each work order told which files its `verification` borrows.

    A work order can be told to verify with a file another work order writes -
    usually the tests. Measured on one run: the backend work order said
    "Verify with: node --test simple-to-do-list-app/tests/tasks.test.js", the
    testing work order owned that file and had not written it yet, and the
    backend specialist tried to write it seven times in two and a half
    minutes, refused each time as another work order's file. The plan asked
    for something the specialist was not allowed to do.

    In linear mode the testing task runs after the code it tests; in parallel
    mode it may not have reached the file. Either way the specialist is told up
    front whose the file is and what to do when it is not there. Never raises.
    """
    try:
        tasks = list(getattr(milestone, "delegated_tasks", None) or [])
        owners: dict[str, tuple[int, Any]] = {}
        for index, task in enumerate(tasks, 1):
            for path in getattr(task, "files", None) or []:
                cleaned = str(PurePosixPath(str(path).strip().lstrip("/")))
                if cleaned and cleaned != ".":
                    owners.setdefault(cleaned, (index, task))
        if not owners:
            return milestone
        changed = False
        noted = []
        for index, task in enumerate(tasks, 1):
            borrowed: dict[str, tuple[int, Any]] = {}
            for command in getattr(task, "verification", None) or []:
                for token in _words_of(str(command)):
                    for path, (owner_index, owner) in owners.items():
                        if owner_index != index and (path == token or path.endswith("/" + token)):
                            borrowed.setdefault(path, (owner_index, owner))
            if borrowed:
                lines = [
                    f"`{path}` is written by {_label(owner_index, owner)}"
                    for path, (owner_index, owner) in borrowed.items()
                ]
                task = task.model_copy(update={
                    "task_description": str(getattr(task, "task_description", "") or "")
                    + "\n\nYour verification uses files another work order writes: "
                    + "; ".join(lines) + ". It may not exist yet when you get there. Do not "
                    "write it yourself - a file another work order owns is refused. If it "
                    "is not there, finish your own work, run the checks you can, and say in "
                    "your answer which check waits on that work order."
                })
                changed = True
            noted.append(task)
        return milestone.model_copy(update={"delegated_tasks": noted}) if changed else milestone
    except Exception:  # noqa: BLE001 - a note must never cost the plan
        return milestone


def _words_of(command: str) -> list[str]:
    """The path-like words of a command line, without quotes or a leading `./`."""
    import shlex

    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    return [
        str(PurePosixPath(word.lstrip("./") if word.startswith("./") else word.lstrip("/")))
        for word in words
        if "/" in word or "." in word.lstrip(".")
    ]


def with_test_cases_from_its_criteria(milestone: Any) -> Any:
    """The plan with each code work order that has no test cases given its
    acceptance criteria as them.

    Test cases are "the cases that prove the acceptance criteria", and the
    testing task writes tests from them. The lead leaves them out more than
    anything else: over 25 runs, 54 readiness problems were a work order with
    no `test_cases`. Sending the plan back rarely helped. On one run the lead
    answered `test_cases: []` for all seven work orders three times running -
    the third time with concrete, checkable acceptance criteria on every one -
    and the plan was dispatched unready after about seven minutes of re-planning.

    Only where there are criteria to take them from: a code work order with
    neither is still sent back. Never raises.
    """
    try:
        tasks = list(getattr(milestone, "delegated_tasks", None) or [])
        changed = False
        rewritten = []
        for task in tasks:
            role = _role(task)
            criteria = [str(c) for c in getattr(task, "acceptance_criteria", None) or [] if str(c).strip()]
            cases = [str(c) for c in getattr(task, "test_cases", None) or [] if str(c).strip()]
            if role not in _NOT_CODE and role != _TESTING and not cases and criteria:
                task = task.model_copy(update={"test_cases": criteria})
                changed = True
            rewritten.append(task)
        if not changed:
            return milestone
        return milestone.model_copy(update={"delegated_tasks": rewritten})
    except Exception:  # noqa: BLE001 - the readiness check still reports it
        return milestone


def with_paths_inside_the_project(milestone: Any, repo_root: str | Path | None) -> Any:
    """The plan with each work order's files named from the workspace root.

    Once the project directory exists the lead often names files the way the
    project sees them: `src/app.js`, `index.html`, `tests/unit/task.test.js`.
    Measured over 25 runs: five readiness problems were a path like that, each
    one a whole re-plan; and a plan dispatched unready recorded `src/app.js` as
    its backend task's file, which matches nothing the specialists write, so no
    one owned `simple-to-do-list-app/src/app.js` for that sprint.

    Only a path that cannot mean anything else is rewritten: its first part is
    not the project directory, not `docs`, not something at the top of the
    workspace already, and not a near-spelling of the project's name - that one
    is a second project, and the readiness check says so. Never raises.
    """
    project_dir = _pinned_project_directory(repo_root)
    if not project_dir:
        return milestone
    try:
        tasks = list(getattr(milestone, "delegated_tasks", None) or [])
        root = Path(repo_root or "")
        changed = False
        rewritten = []
        for task in tasks:
            files = [str(f) for f in getattr(task, "files", None) or []]
            inside = [_inside_the_project(path, project_dir, root) for path in files]
            if inside != files:
                changed = True
                task = task.model_copy(update={"files": inside})
            rewritten.append(task)
        if not changed:
            return milestone
        return milestone.model_copy(update={"delegated_tasks": rewritten})
    except Exception:  # noqa: BLE001 - the readiness check still reports it
        return milestone


def _inside_the_project(path: str, project_dir: str, root: Path) -> str:
    clean = str(PurePosixPath(path.strip().lstrip("/"))) if path.strip() else ""
    if not clean or clean == ".":
        return path
    first = clean.split("/", 1)[0]
    if first in {project_dir, "docs", "..", "."}:
        return path
    if SequenceMatcher(None, first.lower(), project_dir.lower()).ratio() >= _NEAR_SPELLING:
        return path
    try:
        if (root / first).exists():
            return path
    except OSError:
        return path
    return f"{project_dir}/{clean}"


#: How alike a first directory and the project's name must be to be read as a
#: misspelling of it rather than a directory inside it.
_NEAR_SPELLING = 0.8


def _pinned_project_directory(repo_root: str | Path | None) -> str:
    try:
        from app.tools.repository import pinned_project_directory

        return (pinned_project_directory(Path(repo_root or "")) or "").strip("/")
    except Exception:  # noqa: BLE001 - no pin: paths are not checked against one
        return ""


def _touches_product_code(files: Sequence[str]) -> bool:
    """Whether a work order changes anything a test could exercise.

    A work order that only writes the package manifest or configuration has no
    behaviour of its own to give cases for. One run's plan was sent back for
    "work order 3 (backend: Create project package.json ...) has no
    `test_cases`" - one of three problems that cost a six-work-order plan its
    place to a two-work-order one. A work order that names no files is still
    held to it, as before.
    """
    if not files:
        return True
    try:
        from app.analysis.file_kinds import classify_file
        from app.tools.repository import PACKAGE_MANIFESTS
    except Exception:  # noqa: BLE001 - no way to tell, so hold it to the rule
        return True
    return any(
        PurePosixPath(path).name not in PACKAGE_MANIFESTS and classify_file(path) == "application"
        for path in files
    )


def readiness_enforced() -> bool:
    """Whether an unready plan is sent back. `WORKFLOW_WORK_ORDER_READINESS=off` disables it.

    On by default. The switch exists for the whole-graph routing tests, whose
    scripted plans predate work orders; nothing in a real run turns it off.
    """
    import os

    return os.environ.get("WORKFLOW_WORK_ORDER_READINESS", "on").strip().lower() not in {
        "0", "off", "false", "no",
    }


def readiness_problems(
    milestone: Any, repo_root: str | Path | None, carried_forward: Sequence[str] = ()
) -> list[str]:
    """What stops this plan being handed out as it stands. Never raises.

    `carried_forward` is what earlier sprints left for this one; each item needs
    a line in the plan's `carried_forward_decisions`, taking or declining it.
    """
    if not readiness_enforced():
        return []
    try:
        tasks = list(getattr(milestone, "delegated_tasks", None) or [])
    except Exception:  # noqa: BLE001
        return []
    if not tasks:
        # Measured on one run: the lead reasoned to its reply ceiling, answered
        # from the recovery call with no work orders and a blocker - the tests
        # "are not yet available; unable to define concrete implementation" -
        # and the sprint went straight to a test round, a security review and
        # a milestone review of work nobody had been given.
        return [
            "The plan hands out no work orders, so nothing in this sprint gets built. "
            "Give the work orders that deliver the sprint goal. Something not yet "
            "known or not yet built is not a reason to plan nothing: give it to a "
            "work order to build or find out, and say what that work order depends "
            "on in its brief."
        ]
    project_dir = _pinned_project_directory(repo_root)
    problems: list[str] = []
    code_tasks = [t for t in tasks if _role(t) not in _NOT_CODE and _role(t) != _TESTING]

    for index, task in enumerate(tasks, 1):
        role = _role(task)
        label = _label(index, task)
        files = [str(f) for f in getattr(task, "files", None) or [] if str(f).strip()]
        if role not in _NOT_CODE and not files:
            problems.append(
                f"{label} names no `files`. List every file it creates or changes, as a "
                "path inside the project directory."
            )
        for path in files:
            why = _outside_the_project(path, project_dir)
            if why:
                problems.append(f"{label}: file '{path}' {why}.")
        if (
            role not in _NOT_CODE
            and role != _TESTING
            and not (getattr(task, "test_cases", None) or [])
            and _touches_product_code(files)
        ):
            problems.append(
                f"{label} has no `test_cases`. Give the given/when/then cases that prove its "
                "acceptance criteria - the testing task writes the tests from them."
            )
        try:
            from app.analysis.planned_commands import commands_the_sandbox_would_refuse

            refused = commands_the_sandbox_would_refuse(
                "\n".join(f"`{c}`" for c in getattr(task, "verification", None) or []),
                f"{role}_specialist",
                repo_root,
            )
        except Exception:  # noqa: BLE001
            refused = []
        for note in refused:
            problems.append(f"{label} `verification`: {note}")

    carried = [str(item) for item in carried_forward or () if str(item).strip()]
    decided = [str(d) for d in getattr(milestone, "carried_forward_decisions", None) or [] if str(d).strip()]
    if carried and len(decided) < len(carried):
        problems.append(
            f"{len(carried)} item(s) were carried forward from earlier sprints and "
            f"`carried_forward_decisions` records {len(decided)}. Give one line per item: "
            "the work order that takes it, or why it is declined."
        )
    if code_tasks and not any(_role(t) == _TESTING for t in tasks):
        problems.append(
            "No `testing` work order. A milestone that changes code needs one, which "
            "writes automated tests from the other work orders' `test_cases` and "
            "`interfaces`."
        )
    return problems


def readiness_feedback(problems: Sequence[str]) -> str:
    """The note that sends an unready plan back to the lead."""
    listed = "\n".join(f"- {problem}" for problem in problems)
    return (
        "\n\nYOUR PREVIOUS PLAN WAS NOT READY TO HAND OUT. A specialist starts each "
        "task knowing only its work order, so each one must be complete. Fix these "
        "and return the whole plan again:\n" + listed
    )


def _section(heading: str, items: Iterable[Any], numbered: bool = False) -> str:
    kept = [" ".join(str(item).split()) for item in items or () if str(item).strip()]
    if not kept:
        return ""
    lines = (
        [f"{n}. {item}" for n, item in enumerate(kept, 1)] if numbered else [f"- {item}" for item in kept]
    )
    return f"--- {heading} ---\n" + "\n".join(lines) + "\n\n"


def brief_for(task: Any) -> str:
    """One task's work order, as the sections of a specialist's brief."""
    try:
        return (
            _section("Files you own in this task", getattr(task, "files", None) or [])
            + _section("Interfaces to implement or call, exactly as written", getattr(task, "interfaces", None) or [])
            + _section("Steps", getattr(task, "steps", None) or [], numbered=True)
            + _section("Edge cases and the rule for each", getattr(task, "edge_cases", None) or [])
            + _section("Test cases your work will be checked against", getattr(task, "test_cases", None) or [])
            + _section("Verify with", getattr(task, "verification", None) or [])
            + _section("Out of scope - do not change", getattr(task, "out_of_scope", None) or [])
        )
    except Exception:  # noqa: BLE001 - a brief without the order still has the task
        return ""


def contract_for_testing(task: Any, tasks: Sequence[Any]) -> str:
    """For the testing task: every other work order's interfaces and test cases."""
    if _role(task) != _TESTING:
        return ""
    blocks: list[str] = []
    for index, other in enumerate(tasks or (), 1):
        if other is task or _role(other) in (_TESTING, *_NOT_CODE):
            continue
        interfaces = [str(i) for i in getattr(other, "interfaces", None) or [] if str(i).strip()]
        cases = [str(c) for c in getattr(other, "test_cases", None) or [] if str(c).strip()]
        if not interfaces and not cases:
            continue
        lines = [f"{_label(index, other)}:"]
        lines += [f"  interface: {i}" for i in interfaces]
        lines += [f"  case: {c}" for c in cases]
        blocks.append("\n".join(lines))
    contract = (
        "--- The contract you are testing ---\n"
        "The other work orders in this milestone promise these interfaces and these "
        "cases. Write the tests against them as written - the code is being written "
        "from the same work orders at the same time. A test that fails because the "
        "code does not match the contract is a defect to report, not a test to "
        "change.\n\n" + "\n\n".join(blocks) + "\n\n"
    ) if blocks else ""
    # The write tools refuse product code to this task - see
    # `_a_tester_changing_the_product` - so say it before the first try.
    return contract + _THE_TESTING_TASK_S_FILES


_THE_TESTING_TASK_S_FILES = (
    "--- What is yours to change ---\n"
    "Tests, test configuration and the package manifest. The product code belongs "
    "to the other work orders, even where it is not written yet: write the test "
    "against the interface as given, and if the code it needs is missing or does "
    "not match, say exactly what in `blockers`.\n\n"
)


__all__ = [
    "brief_for",
    "contract_for_testing",
    "readiness_feedback",
    "readiness_problems",
    "with_borrowed_files_noted",
    "with_paths_inside_the_project",
    "with_test_cases_from_its_criteria",
]
