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

import re

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


def with_named_tests_given_to_testing(
    milestone: Any, repo_root: str | Path | None, sprint_scope: str, planned_paths: Sequence[str] = (),
) -> tuple[Any, list[str]]:
    """The plan, each test file its sprint names and no work order lists given to its testing work order; and those files.

    Measured on one run: the sprint's scope named the specification's three
    planned test files, the lead's plan gave them to nobody, and it was sent
    back three times for it - each time returning the same plan - and then
    started over. Which work order writes a test file is not a judgement: it
    is the testing one. The path is the one the specification plans, or the
    testing work order's own test directory.
    """
    from app.analysis.file_kinds import classify_file

    tasks = list(getattr(milestone, "delegated_tasks", None) or [])
    testing = next((i for i, task in enumerate(tasks) if _role(task) == _TESTING), None)
    if testing is None or not sprint_scope:
        return milestone, []
    project_dir = _pinned_project_directory(repo_root)
    unassigned = [
        name for name in _files_the_sprint_names_and_nobody_is_given(sprint_scope, tasks, repo_root, project_dir)
        if classify_file(name) == "test"
    ]
    if not unassigned:
        return milestone, []
    own = [str(f) for f in getattr(tasks[testing], "files", None) or [] if classify_file(str(f)) == "test"]
    beside = str(PurePosixPath(own[0]).parent) if own else ""
    given: list[str] = []
    for name in unassigned:
        planned = next((p for p in planned_paths if PurePosixPath(str(p)).name.lower() == name.lower()), None)
        given.append(str(planned) if planned else (f"{beside}/{name}" if beside and beside != "." else name))
    tasks[testing] = tasks[testing].model_copy(update={"files": [*(getattr(tasks[testing], "files", None) or []), *given]})
    return milestone.model_copy(update={"delegated_tasks": tasks}), given


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


#: `cd <dir> && <command>` or `cd <dir>; <command>`, the whole line.
_CD_THEN = re.compile(r"^\s*cd\s+(['\"]?)([^\s'\"&;]+)\1\s*(?:&&|;)\s*(\S.*)$")


def with_the_project_directory_cd_dropped(milestone: Any, repo_root: str | Path | None) -> Any:
    """The plan with `cd <the project directory> && <command>` written as `<command>`.

    A work order's command already runs in the project directory, and there is
    no shell to read `&&`. Measured on two runs in a row: the lead wrote every
    verification as `cd /simple-to-do-list-app && npm test` (or `&& npx
    playwright test --grep 'AC-1'`), the readiness check rightly refused each as
    "will not run as written", and each cost the whole plan a re-plan.

    Only a `cd` into the project directory itself, at the start of the line, is
    dropped: what follows is exactly the command the line meant. Any other
    shell use is left for the readiness check to report. Never raises.
    """
    project_dir = _pinned_project_directory(repo_root)
    if not project_dir:
        return milestone
    root = str(Path(repo_root or "")).rstrip("/")
    here = {project_dir, f"/{project_dir}", f"./{project_dir}", f"{root}/{project_dir}"}
    try:
        tasks = list(getattr(milestone, "delegated_tasks", None) or [])
        changed = False
        rewritten = []
        for task in tasks:
            commands = [str(c) for c in getattr(task, "verification", None) or []]
            kept = []
            for command in commands:
                found = _CD_THEN.match(command.strip().strip("`"))
                if found and found.group(2).rstrip("/") in here:
                    kept.append(found.group(3).strip())
                else:
                    kept.append(command)
            if kept != commands:
                changed = True
                task = task.model_copy(update={"verification": kept})
            rewritten.append(task)
        if not changed:
            return milestone
        return milestone.model_copy(update={"delegated_tasks": rewritten})
    except Exception:  # noqa: BLE001 - the readiness check still reports it
        return milestone


def _owned_by_the_harness(repo_root: str | Path | None, path: str) -> str:
    """`app.stacks.contract.owned_by_the_harness`, or "" when it cannot tell."""
    try:
        from app.stacks.contract import owned_by_the_harness

        return owned_by_the_harness(repo_root, path)
    except Exception:  # noqa: BLE001 - no contract: nothing is the harness's
        return ""


def with_the_harness_s_files_left_out(milestone: Any, repo_root: str | Path | None) -> Any:
    """The plan without the files the harness owns on any work order.

    For a plan dispatched although the definition of ready found such a file:
    a specialist handed `files: [<the harness's server>]` spends its stage on
    a change the harness puts back. Measured on one run: two work orders and
    a sprint goal aimed at the kept acceptance setup, then 35 refused calls
    across the stages that followed them. Never raises.
    """
    try:
        tasks = list(getattr(milestone, "delegated_tasks", None) or [])
        changed = False
        kept_out = []
        for task in tasks:
            files = [str(f) for f in getattr(task, "files", None) or []]
            owned = [f for f in files if _owned_by_the_harness(repo_root, f)]
            if owned:
                changed = True
                note = (
                    f"\n\n(Taken off this work order: {', '.join(f'`{f}`' for f in owned)} - "
                    "the harness owns it and puts back any change. Where the product fails a "
                    "test because of how it starts or what it serves, the fix is in the product.)"
                )
                task = task.model_copy(update={
                    "files": [f for f in files if f not in owned],
                    "task_description": str(getattr(task, "task_description", "") or "") + note,
                })
            kept_out.append(task)
        if not changed:
            return milestone
        return milestone.model_copy(update={"delegated_tasks": kept_out})
    except Exception:  # noqa: BLE001 - the write guards still refuse the change
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


#: A source file's extension -> the extension it compiles to.
_COMPILED_TO = {"ts": "js", "tsx": "jsx", "mts": "mjs", "cts": "cjs", "coffee": "js", "elm": "js"}


def _another_spelling_of(name: str, known: set[str]) -> bool:
    """Whether `name` is a file the project already has, or a work order lists, spelled otherwise.

    Same extension, and a stem that differs by a plural "s" or barely at all.
    Measured on one run: the specification called the stylesheet `style.css`,
    the scaffold had made `styles.css`, and a constraint the sprint plan quoted
    from the specification - "index.html + style.css + app.js" - was read as a
    file the sprint names and nobody is given. The lead's plan was sent back
    twice for it and dispatched unready on the third; giving `style.css` to a
    work order would have made a second stylesheet.
    """
    from difflib import SequenceMatcher

    stem, dot, extension = name.rpartition(".")
    if not dot or not stem:
        return False
    for other in known:
        other_stem, other_dot, other_extension = other.rpartition(".")
        if not other_dot or not other_stem:
            continue
        # The name a source file compiles to: one run's scope said `server.js`
        # for the planned `server.ts`, and the plan was sent back for it.
        if stem == other_stem and _COMPILED_TO.get(other_extension) == extension:
            return True
        if other_extension != extension:
            continue
        if stem.rstrip("s") == other_stem.rstrip("s"):
            return True
        if min(len(stem), len(other_stem)) >= 4 and SequenceMatcher(None, stem, other_stem).ratio() >= 0.85:
            return True
    return False


def _files_the_sprint_names_and_nobody_is_given(
    sprint_scope: str, tasks: Sequence[Any], repo_root: str | Path | None, project_dir: str
) -> list[str]:
    """Files the sprint's goal, scope or criteria name that no work order lists and that do not exist.

    Measured on one run: the sprint's scope named `index.html`, `style.css`,
    `app.js`, `ui.js` and `model.js`, the plan's work orders covered only the
    state and storage modules, and the gap was found by the milestone review
    after the whole sprint had been built and tested - a full cycle spent on a
    plan with no user interface in it. A file that already exists was built
    earlier and needs no work order. Never raises.
    """
    try:
        from app.analysis.integration_checks import files_named_in

        listed = {
            PurePosixPath(str(path)).name.lower()
            for task in tasks
            for path in getattr(task, "files", None) or []
        }
        base = Path(repo_root or "") / project_dir if project_dir else Path(repo_root or "")
        existing: set[str] = set()
        if repo_root and base.is_dir():
            from app.tools.repository import IGNORED_DIRECTORIES

            for path in base.rglob("*"):
                if path.is_file() and not any(part in IGNORED_DIRECTORIES for part in path.parts):
                    existing.add(path.name.lower())
        # What this project calls a file, beside what files are generally
        # called: `store.read()` in a scope is a call, not a file to hand out.
        in_use = {name.rsplit(".", 1)[-1] for name in listed | existing if "." in name}
        named = files_named_in(sprint_scope, in_use)
        known = listed | existing
        return sorted(
            name for name in named
            if name.lower() not in known and not _another_spelling_of(name.lower(), known)
        )
    except Exception:  # noqa: BLE001 - the plan is still checked for everything else
        return []


def _touches_product_code(files: Sequence[str]) -> bool:
    """Whether a work order changes anything a test could exercise.

    A work order that only writes the package manifest or configuration has no
    behaviour of its own to give cases for. One run's plan was sent back for
    "work order 3 (backend: Create project package.json ...) has no
    `test_cases`" - one of three problems that cost a six-work-order plan its
    place to a two-work-order one. Nor does one that only restyles the
    product: one run's milestone revision changed a stylesheet, was sent back
    twice for "No `testing` work order", invented one to "execute unit tests"
    with no files, and was dispatched unready anyway. Styling is checked by
    the acceptance suite, where a person meets it. A work order that names no
    files is still held to it, as before.
    """
    if not files:
        return True
    try:
        from app.analysis.file_kinds import classify_file, is_presentation
        from app.tools.repository import PACKAGE_MANIFESTS
    except Exception:  # noqa: BLE001 - no way to tell, so hold it to the rule
        return True
    return any(
        PurePosixPath(path).name not in PACKAGE_MANIFESTS
        and classify_file(path) == "application"
        and not is_presentation(path)
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


#: Words that say nothing about which sprint a goal is.
_GOAL_NOISE = frozenset({
    "the", "and", "can", "with", "for", "their", "them", "each", "all", "via",
    "from", "into", "that", "this", "are", "has", "have", "user", "users",
})


def _goal_words(goal: str) -> frozenset[str]:
    return frozenset(
        word for word in re.findall(r"[a-z0-9]+", str(goal or "").lower())
        if len(word) > 2 and word not in _GOAL_NOISE
    )


def _alike(one: frozenset[str], other: frozenset[str]) -> float:
    return len(one & other) / len(one | other) if one and other else 0.0


def another_sprints_plan(milestone: Any, sprint_goals: Sequence[str], sprint_index: int) -> str:
    """Why this plan is for a different sprint than the one being planned, or "".

    The lead is told which sprint it is planning, by its goal, and nothing
    checked that the plan it returned was for that sprint. Measured over 889
    stored plans: twice a lead asked to plan sprint 1 returned sprint 2's goal
    word for word, and this rule names exactly those two and no other.

    A goal may be restated, so it is compared by its words with every sprint's
    goal, and named as another sprint's only when it is plainly closer to that
    one: half its words at least, and more than to the sprint being planned.
    Never raises.
    """
    try:
        goals = [str(goal or "") for goal in sprint_goals]
        if not 0 <= sprint_index < len(goals):
            return ""
        chosen = _goal_words(getattr(milestone, "selected_sprint_goal", "") or "")
        here = _alike(chosen, _goal_words(goals[sprint_index]))
        best, closest = max(
            ((_alike(chosen, _goal_words(goal)), number) for number, goal in enumerate(goals)
             if number != sprint_index),
            default=(0.0, -1),
        )
        if closest < 0 or best < 0.5 or best <= here:
            return ""
    except Exception:  # noqa: BLE001
        return ""
    return (
        f"The plan's `selected_sprint_goal` is sprint {closest + 1}'s goal, "
        f"'{goals[closest]}', and its work orders build that sprint. The sprint being "
        f"planned is sprint {sprint_index + 1}: '{goals[sprint_index]}'. Plan the "
        f"milestone for sprint {sprint_index + 1}, with its goal; sprint {closest + 1}'s "
        "work is that sprint's to plan, when it comes."
    )


#: A decision that declines, defers or skips what was carried.
_DECLINES = re.compile(r"\bdeclin|\bdefer|\bskip|\bignor|\bnot needed\b|\bnot required\b", re.I)
#: ...because no test asks for it.
_BECAUSE_UNTESTED = re.compile(
    r"\btests?\b|\btest suite\b|\bcriteri|\bacceptance\b|\bnot required\b|\bpass(?:es|ing)?\b", re.I
)


#: A decision that hands the item on: to a work order of this sprint, or to a
#: later sprint whose plan holds it.
_HANDED_ON = re.compile(
    r"\btask\s*\d|\bwork order\s*\d|->\s*(?:task|work order)|\u2192\s*(?:task|work order)"
    r"|\b(?:later|next|following|future) sprint\b|\bsprint\s*\d+'?s?\s+(?:in_scope|scope|plan)"
    r"|\b(?:defer\w*|left|moved|belongs?|scheduled|planned)\s+(?:\w+\s+){0,3}(?:to|for|in)\s+sprint\s*\d",
    re.I,
)


def declined_because_untested(decisions: Sequence[str]) -> list[str]:
    """The carried-forward decisions that decline an item because no test requires it.

    Measured on one run: a sprint whose criteria already passed was carried
    fifteen adopted interface and data items its specialists found missing, and
    its lead declined every one "not required by current sprint tests" - after
    being told that was no reason. The sprint closed with nothing built.

    A decision that hands the item on - into one of this sprint's work orders,
    or to the later sprint whose plan holds it - is not a decline for want of
    a test, whatever tests it mentions. Measured on another run: a lead that
    deferred validation "on scheduling grounds, not test grounds" to the
    sprint whose scope names it was sent back for it three times, twelve
    minutes a time.
    """
    return [
        d for d in decisions
        if _DECLINES.search(d) and _BECAUSE_UNTESTED.search(d) and not _HANDED_ON.search(d)
    ]


def untested_is_no_reason(declined: Sequence[str]) -> str:
    """The send-back for decisions that decline carried work because no test requires it."""
    shown = "; ".join(" ".join(str(d).split())[:120] for d in list(declined)[:4])
    more = f" and {len(declined) - 4} more" if len(declined) > 4 else ""
    return (
        f"{len(declined)} decision(s) decline carried work because no test requires it ({shown}{more}). "
        "That is not a reason: what the specification adopted is for the person who uses the "
        "product. Take each item that still holds into a work order for the role that owns it, "
        "or decline it with a reason it no longer holds - built already (say where), ruled out "
        "by the brief (say which line), or planned for a later sprint (say which)."
    )


def readiness_problems(
    milestone: Any,
    repo_root: str | Path | None,
    carried_forward: Sequence[str] = (),
    sprint_scope: str = "",
    sprint_goals: Sequence[str] = (),
    sprint_index: int = 0,
) -> list[str]:
    """What stops this plan being handed out as it stands. Never raises.

    `carried_forward` is what earlier sprints left for this one; each item needs
    a line in the plan's `carried_forward_decisions`, taking or declining it.
    `sprint_goals` are the sprint plan's goals in order, and `sprint_index` the
    one being planned. See `another_sprints_plan`.
    """
    if not readiness_enforced():
        return []
    elsewhere = another_sprints_plan(milestone, sprint_goals, sprint_index)
    if elsewhere:
        return [elsewhere]
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
                continue
            owner = _owned_by_the_harness(repo_root, path)
            if owner:
                problems.append(
                    f"{label}: file '{path}' is {owner}. No work order changes it, and a "
                    "change is put back. If the product fails a test because of how it "
                    "starts or what it serves, the fix is in a product file: name that one."
                )
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

    unassigned = _files_the_sprint_names_and_nobody_is_given(sprint_scope, tasks, repo_root, project_dir)
    if unassigned:
        problems.append(
            f"The sprint's scope names {', '.join(unassigned)} and no work order lists "
            f"{'it' if len(unassigned) == 1 else 'them'}. A file nobody is given is a file "
            "nobody writes: give each to the work order that builds it."
        )

    carried = [str(item) for item in carried_forward or () if str(item).strip()]
    decided = [str(d) for d in getattr(milestone, "carried_forward_decisions", None) or [] if str(d).strip()]
    if carried and len(decided) < len(carried):
        problems.append(
            f"{len(carried)} item(s) were carried forward from earlier sprints and "
            f"`carried_forward_decisions` records {len(decided)}. Give one line per item: "
            "the work order that takes it, or why it is declined."
        )
    untested = declined_because_untested(decided) if carried else []
    if untested:
        problems.append(untested_is_no_reason(untested))
    behaviour = [
        t for t in code_tasks
        if _touches_product_code([str(f) for f in getattr(t, "files", None) or [] if str(f).strip()])
    ]
    if behaviour and not any(_role(t) == _TESTING for t in tasks):
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
