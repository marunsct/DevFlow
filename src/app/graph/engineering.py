"""CI and code review between a batch of work orders and its test rounds, and the
guard that keeps a defect fix from making the product worse.

    specialists -> ci_gate -> code_review -> test_and_triage -> fixes ...

The work orders of a milestone are committed as one batch. CI runs the unit and
acceptance suites and compares them with the state the last sprint was accepted
in: anything that passed then and fails now is a regression, recorded as a
defect. A senior engineer then reads the batch's diff against its work orders;
what blocks becomes a defect with an owner. Both reach the sprint's ordinary
fix loop through the first test round, so nothing new is needed to fix them.

A fix is different: it is one change, made to repair one thing, and a fix that
breaks something else while it is at it is reverted to exactly where it
started. Its defect stays open, with what the attempt broke, so the next try
knows.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig

from app import ci
from app.acceptance import suite
from app.agents.specialists import raised_by
from app.stacks import contract

logger = logging.getLogger(__name__)

#: How many regressions a CI run turns into defects; one broken build fails
#: every test, and fifty defects for one cause help nobody.
MOST_REGRESSION_DEFECTS = 6


def _root(state: Any) -> str:
    return state["repository"].root_path


def ci_applies(root: str) -> bool:
    """Whether there is anything to measure: a scaffolded project or a locked suite."""
    return contract.read(root) is not None or suite.is_locked(root)


def _tasks(state: Any) -> list[Any]:
    return list(getattr(state.get("milestone_plan"), "delegated_tasks", None) or [])


def _title(task: Any) -> str:
    return str(getattr(task, "title", "") or getattr(task, "task_description", "") or "")[:80]


def _owner_of(state: Any, work_order: str) -> str:
    tasks = _tasks(state)
    for task in tasks:
        if work_order and work_order.strip().lower() in _title(task).lower():
            return str(task.specialist_role)
    for task in tasks:
        if str(task.specialist_role) != "testing":
            return str(task.specialist_role)
    return "backend"


#: What a team's own test that regressed may be instead of a broken product.
#: Not said of the locked acceptance suite, which no fix may change.
#:
#: Measured on one run: sprint 1 wrote unit tests pinning a placeholder filter -
#: "returns all tasks regardless of mode - stub behaviour" - and sprint 4 was the
#: sprint that built filtering. Both tests were reported as regressions,
#: expected to "pass, as they did before"; the one fix tried put the placeholder
#: back, broke four acceptance criteria and was reverted, and the sprint failed
#: on exhausted attempts with 72 of 73 tests passing.
_OR_THE_TEST_IS_OUT_OF_DATE = (
    " Unless what it asserts is behaviour this sprint was meant to change - a "
    "placeholder, or an earlier rule, that this sprint's goal replaces. Then the "
    "test is out of date, not the product: change what it asserts to the behaviour "
    "this sprint delivers, keep the test's name (a test that disappears is counted "
    "as broken), and say in your answer that the test was out of date."
)


#: What a regressed test that no longer exists may be: replaced on purpose.
#:
#: Measured on one run: a batch replaced four unit tests of a placeholder with
#: tests of the behaviour that replaced it. CI reported the four as passing
#: before and failing now; four fix stages looked for a failing test, found
#: none, and one answered "unable to identify failure cause".
_GONE_ON_PURPOSE = (
    " If this sprint replaced what it tested on purpose, a test of the new "
    "behaviour may stand in its place: then nothing is broken - name that test in "
    "your answer and change nothing."
)


def _gone(after: Any, name: str) -> bool:
    """Whether the test `name` ("unit: key") did not run at all in `after`."""
    if after is None:
        return False
    kind, _, key = name.partition(": ")
    ran = after.unit_ran if kind == "unit" else after.acceptance_ran
    now = after.unit if kind == "unit" else after.acceptance
    return bool(ran) and ci._outcome_now(now, key) is None


def regression_defects(state: Any, lost: list[str], after: Any = None) -> list[Any]:
    """A defect for each test that passed before and does not now.

    `after` is the measurement that found them; with it, a test that did not run
    at all is described as gone rather than failing.
    """
    from app.agents.specialists import ReportedDefect

    owner = _owner_of(state, "")
    defects = []
    for name in lost[:MOST_REGRESSION_DEFECTS]:
        gone = _gone(after, name)
        unit = name.startswith("unit:")
        defects.append(ReportedDefect(
            description=(
                f"Regression: `{name}` passed before this batch of work orders and "
                + ("is gone now - no test of that name ran." if gone else "fails now.")
            ),
            severity="major",
            reproduction_steps=f"Run the {name.split(':', 1)[0]} tests in the project directory.",
            expected_behavior=(
                ("It still runs and passes." + (_GONE_ON_PURPOSE if unit else ""))
                if gone
                else "It passes, as it did before this sprint's work orders."
                + (_OR_THE_TEST_IS_OUT_OF_DATE if unit else "")
            ),
            actual_behavior=(
                "No test of that name ran after them: it was removed or renamed."
                if gone
                else "It fails after them."
            ),
            affected_files=[],
            owner=owner,
        ))
    if len(lost) > MOST_REGRESSION_DEFECTS:
        defects[-1].actual_behavior += f" ({len(lost) - MOST_REGRESSION_DEFECTS} more tests regressed with it.)"
    return defects


#: How many of the batch's files the language service reads at the gate, and
#: how many of its findings become defects. Each file costs about a second.
MOST_FILES_UNDERLINED = 12
MOST_UNDERLINED_DEFECTS = 6


#: How an underlined defect's description ends, so it can be read back.
FAILS_WHEN_IT_RUNS = " - this fails when the code runs."
_AN_UNDERLINED_DEFECT = re.compile(r"^(?P<file>\S+) line [\d, ]+: (?P<message>.+)" + re.escape(FAILS_WHEN_IT_RUNS) + "$", re.S)


def no_longer_underlined(root: str, description: str) -> str:
    """Why an underlined defect is already fixed, or "" when it still holds or cannot be told.

    The language service is asked again about the file the defect names. One
    run's round queued three defects for one missing export - the round's own,
    and the language service's in the two files that import it - and three for
    one undefined name; each went to a fixer of its own, five to eight minutes
    apiece, after the first had already fixed it. Never raises.
    """
    found = _AN_UNDERLINED_DEFECT.match(str(description or "").strip())
    if found is None:
        return ""
    try:
        from app.analysis.language_service import underlined_any
        from app.tools.repository import pinned_project_directory

        target = Path(root) / found.group("file")
        if not target.is_file():
            return f"{found.group('file')} no longer exists."
        pinned = pinned_project_directory(Path(root))
        project = Path(root) / pinned if pinned else None
        from app.analysis import compiler_check

        if target.suffix.lower() in compiler_check.SUFFIXES:
            errors = compiler_check.findings(root, pinned or "", [found.group("file")])
            if any(e["file"] == found.group("file") and e["message"] == found.group("message") for e in errors):
                return ""
            return f"The compiler no longer reports it in {found.group('file')}."
        now = underlined_any(root, target, target.read_text(encoding="utf-8", errors="replace"), project)
        if now is None:
            return ""
        if any(finding["message"] == found.group("message") for finding in now.here):
            return ""
        return f"The language service no longer underlines it in {found.group('file')}."
    except Exception:  # noqa: BLE001 - a defect not closed goes to a fixer as before
        return ""


def underlined_in_the_batch(state: Any, root: str, since: str) -> list[Any]:
    """Defects for what an IDE still underlines in the batch's files, once every work order is done.

    At the write these are notes, because a name may be defined by a file
    another work order has not written yet. At the gate every work order has
    finished, so a name nothing defines is a ReferenceError waiting in the
    product, and an import of a missing export fails as the module loads -
    certain, and named by file and line. See `app.analysis.language_service`.
    """
    from app.agents.specialists import ReportedDefect
    from app.analysis.language_service import ALL_SUFFIXES, underlined_any

    try:
        from app.tools.repository import pinned_project_directory

        pinned = pinned_project_directory(Path(root))
    except Exception:  # noqa: BLE001
        pinned = None
    project = Path(root) / pinned if pinned else None
    from app.analysis.file_kinds import is_scratch

    # A stage's throwaway script is not the product, and the harness removes
    # it: one run's round raised two defects against `tmp_test_run.js` and
    # `tmp_import_from_tests.mjs`, closed only because they were gone by then.
    files = [
        p for p in ci.changed_since(root, since)
        if p.lower().endswith(ALL_SUFFIXES) and not is_scratch(Path(p).name)
    ][:MOST_FILES_UNDERLINED]
    defects = []
    for relative in files:
        target = Path(root) / relative
        try:
            found = underlined_any(root, target, target.read_text(encoding="utf-8", errors="replace"), project)
        except Exception:  # noqa: BLE001 - a check that cannot run finds nothing
            found = None
        if found is None:
            continue
        grouped: dict[str, list[dict]] = {}
        for finding in found.here:
            grouped.setdefault(finding["message"], []).append(finding)
        for message, where in grouped.items():
            lines = ", ".join(str(f["line"]) for f in where[:6])
            defects.append(ReportedDefect(
                description=f"{relative} line {lines}: {message}{FAILS_WHEN_IT_RUNS}",
                severity="major",
                reproduction_steps=f"Read {relative} at line {lines}: `{where[0]['text']}`.",
                expected_behavior="Every name the code uses is defined or imported, and every import names something its module exports.",
                actual_behavior=f"{message} (the TypeScript language service, as an IDE would underline it)",
                affected_files=[relative],
                owner=_owner_of(state, ""),
            ))
    defects.extend(_what_the_compiler_says(state, root, since, pinned or ""))
    return defects[:MOST_UNDERLINED_DEFECTS]


def _what_the_compiler_says(state: Any, root: str, since: str, project: str) -> list[Any]:
    """Defects for what the compiler reports, when the batch changed code in a compiled language.

    The language service covers JavaScript, TypeScript and Python file by file;
    for a compiled language the compiler is the language service, asked once
    for the project now that every work order is done. See
    `app.analysis.compiler_check`.
    """
    from app.agents.specialists import ReportedDefect
    from app.analysis import compiler_check

    changed = [p for p in ci.changed_since(root, since) if p.lower().endswith(compiler_check.SUFFIXES)]
    if not changed:
        return []
    try:
        found = compiler_check.findings(root, project, changed)
    except Exception:  # noqa: BLE001 - a check that cannot run finds nothing
        found = []
    defects = []
    for finding in found:
        relative, line, message = finding["file"], finding["line"], finding["message"]
        defects.append(ReportedDefect(
            description=f"{relative} line {line}: {message}{FAILS_WHEN_IT_RUNS}",
            severity="major",
            reproduction_steps=f"Build the project: the compiler stops at {relative} line {line}.",
            expected_behavior="The project compiles: every name is defined or imported and every call matches what it calls.",
            actual_behavior=f"{message} (the compiler, as an IDE would underline it)",
            affected_files=[relative],
            owner=_owner_of(state, ""),
        ))
    return defects


def ci_gate(state: Any, config: RunnableConfig, ctx: Any) -> dict[str, Any]:
    """Commit the batch, run CI, and record what it broke."""
    from app.graph.workflow import APP_RUN_ID_KEY, _handing_on, _stop_if_cancelled

    _stop_if_cancelled(config["configurable"].get(APP_RUN_ID_KEY))
    root = _root(state)
    if not ci_applies(root):
        return _handing_on(stage="test_and_triage")
    titles = "; ".join(_title(task) for task in _tasks(state)) or "work orders"
    batch = ci.commit(root, f"Work orders: {titles}")
    accepted = ci.load(root, "accepted")
    # The last measurement before this batch, as well as the last accepted
    # sprint. Against the accepted state alone, CI was blind for the whole of
    # the first sprint - its baseline is the suite as locked, where nothing
    # passes - and on every re-plan: one run's re-planned batch broke all
    # seven acceptance tests that had passed, the page rendering nothing
    # but its heading, and CI reported no regression.
    before = ci.load(root, "latest")
    after = ci.take(root, "after the work orders")
    lost = list(dict.fromkeys([*ci.regressions(accepted, after), *ci.regressions(before, after)]))
    ci.save(root, after)
    underlined = underlined_in_the_batch(state, root, (before.commit if before else "") or (accepted.commit if accepted else ""))
    if lost:
        logger.warning("CI: %d test(s) regressed since the last accepted sprint or the last measurement", len(lost))
    report = (
        f"Unit tests: {sum(o == 'passed' for o in after.unit.values())} of {len(after.unit)} pass"
        + ("" if after.unit_ran else " (no unit report)")
        + f"; acceptance tests: {sum(o == 'passed' for o in after.acceptance.values())} of "
        f"{len(after.acceptance)} pass."
        + (("\nRegressed - passed when the last sprint was accepted or before this batch, fails now:\n"
            + "\n".join(f"- {n}" for n in lost)) if lost else "")
        + (("\nWhat an IDE underlines in the batch's files - each fails when the code runs:\n"
            + "\n".join(f"- {d.description}" for d in underlined)) if underlined else "")
    )
    return _handing_on(
        stage="code_review",
        ci_report=report,
        ci_batch_commit=batch,
        review_defects=[
            *raised_by("regression", regression_defects(state, lost, after)),
            *raised_by("language service", underlined),
        ],
    )


def _later_sprints(state: Any) -> str:
    """Each later sprint's goal and criteria, for a reviewer of this one."""
    sprints = list(getattr(state.get("sprint_plan"), "sprints", None) or [])
    index = int(state.get("current_sprint_index") or 0)
    texts = {c.id: c.text for c in suite.criteria(_root(state))}
    lines = []
    for number, sprint in enumerate(sprints[index + 1:], index + 2):
        ids = list(getattr(sprint, "criteria", None) or [])
        lines.append(
            f"- Sprint {number}: {getattr(sprint, 'goal', '')}"
            + "".join(f"\n    {cid}: {texts.get(cid, '')}" for cid in ids)
        )
    return "\n".join(lines)


def code_review(state: Any, config: RunnableConfig, ctx: Any) -> dict[str, Any]:
    """A senior engineer reads the batch's diff; what blocks becomes a defect."""
    from app.acceptance.requests import criteria_text
    from app.agents.code_reviewer import build_code_review_request, create_code_reviewer_agent
    from app.agents.specialists import ReportedDefect
    from app.graph.acceptance_nodes import criteria_due
    from app.graph.workflow import _handing_on, _run_gated_agent

    root = _root(state)
    accepted = ci.load(root, "accepted")
    diff = ci.diff_since(root, accepted.commit if accepted else "")
    if not diff.strip():
        return _handing_on(stage="test_and_triage")
    due = set(criteria_due(state) or [])
    criteria = criteria_text([c for c in suite.criteria(root) if not due or c.id in due])
    orders = "\n".join(
        f"- {_title(task)} ({task.specialist_role}): {getattr(task, 'task_description', '')[:400]}"
        for task in _tasks(state)
    )
    later = _later_sprints(state)
    agent = create_code_reviewer_agent(
        model=ctx.judgement_model, checkpointer=ctx.checkpointer,
        repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories,
    )
    attempt = int(state.get("sprint_replan_count") or 0), int(state.get("milestone_revision_count") or 0)
    update = _run_gated_agent(
        state, config,
        stage_name=f"code_review_{attempt[0]}_{attempt[1]}",
        agent=agent,
        initial_request=build_code_review_request(diff, orders, criteria, str(state.get("ci_report") or ""), later),
        output_key="__code_review__",
        next_stage="code_review",
    )
    if "__code_review__" not in update:
        return update
    review = update.pop("__code_review__")
    update.pop("stage", None)
    from app.graph.acceptance_nodes import criteria_only_later

    later = [
        finding for finding in getattr(review, "findings", None) or []
        if criteria_only_later(state, f"{finding.problem} {finding.fix or ''}")
    ]
    if later:
        logger.info("Code review raised %d finding(s) about criteria later sprints deliver; not defects now", len(later))
    serious = [
        finding for finding in getattr(review, "findings", None) or []
        if finding.severity in {"blocking", "major"} and finding not in later
    ]
    # Only what a test or a check shows becomes a defect; the rest is advice for
    # the milestone review. See `what_shows_it`.
    shown = [(finding, what_shows_it(state, finding)) for finding in serious]
    found = [
        ReportedDefect(
            description=f"Code review ({finding.work_order}): {finding.problem}",
            severity="blocking" if finding.severity == "blocking" else "major",
            reproduction_steps=f"Read {finding.file or 'the files the work order names'}. {why}",
            expected_behavior=finding.fix or "What the work order asked for.",
            actual_behavior=finding.problem,
            affected_files=[finding.file] if finding.file else [],
            owner=_owner_of(state, finding.work_order),
        )
        for finding, why in shown
        if why
    ]
    advice = [
        f"{finding.file or finding.work_order}: {' '.join(str(finding.problem).split())}"
        + (f" Suggested: {' '.join(str(finding.fix).split())}" if finding.fix else "")
        for finding, why in shown
        if not why
    ]
    if found:
        logger.info("Code review found %d problem(s) a test or check shows; to fix", len(found))
    if advice:
        logger.info("Code review raised %d finding(s) no test or check shows; advice, not defects", len(advice))
    return _handing_on(
        **update,
        stage="test_and_triage",
        review_defects=[*(state.get("review_defects") or []), *raised_by("code review", found)],
        review_advice=[*(state.get("review_advice") or []), *advice][-MOST_REVIEW_ADVICE:],
    )


#: How much code review advice a sprint keeps for its milestone review.
MOST_REVIEW_ADVICE = 12


def what_shows_it(state: Any, finding: Any) -> str:
    """What demonstrates a code review finding, as a sentence; "" when nothing does.

    A reviewer reads a diff and can be wrong. Measured on one run: "the form
    submit handler does not sanitize user input" - on a page that renders with
    `textContent` - became a defect, its fixer escaped the input before
    storing it, and the page then showed "&amp;" where a user typed "&": a
    real bug, made by fixing an unreal one. Another finding said a test
    command's flags were in the wrong order; they were not, and a fix stage
    was spent finding that out.

    Shown means: a criterion due now that the finding names fails in the
    harness's last run of the suite; a test the finding names fails in the
    measurement after this batch; or what an IDE underlines in this batch is
    in the finding's file. Never raises: nothing readable shows nothing.
    """
    text = f"{getattr(finding, 'problem', '')} {getattr(finding, 'fix', '') or ''}"
    try:
        from app.graph.acceptance_nodes import criteria_due, criteria_failing_now

        due = set(criteria_due(state) or [])
        failing = [item for item in criteria_failing_now(state, text) if not due or item in due]
        if failing:
            return f"The acceptance suite shows {', '.join(failing)} failing."
    except Exception:  # noqa: BLE001
        pass
    try:
        latest = ci.load(_root(state), "latest")
        if latest is not None:
            for name, outcome in {**latest.unit, **latest.acceptance}.items():
                bare = ci._bare(name)
                if outcome != "passed" and len(bare) >= 12 and bare in text:
                    return f"`{bare}` fails in the measurement after this batch."
    except Exception:  # noqa: BLE001
        pass
    named = str(getattr(finding, "file", "") or "").strip()
    if named:
        for defect in state.get("review_defects") or []:
            if str(getattr(defect, "source", "")) != "language service":
                continue
            if any(str(f).endswith(named) or named.endswith(str(f)) for f in getattr(defect, "affected_files", None) or []):
                return "An IDE underlines code in this file in this batch."
    return ""


# --- the guard around a fix -----------------------------------------------------------

def before_a_fix(root: str, stage_name: str) -> str:
    """Commit the workspace as the fix will find it; the commit to revert to."""
    if not ci_applies(root):
        return ""
    base = ci.commit(root, f"Before {stage_name}")
    latest = ci.load(root, "latest")
    if latest is None or latest.commit != base:
        # Something changed since the last measurement (a test round edited
        # tests, say), so measure what the fix starts from.
        ci.save(root, ci.take(root, f"before {stage_name}"))
    return base


def after_a_fix(root: str, base: str, stage_name: str, description: str) -> list[str]:
    """Measure the fix. A fix that broke what passed before it is reverted; returns what it broke."""
    if not base or not ci_applies(root):
        return []
    before = ci.load(root, "latest")
    after = ci.take(root, f"after {stage_name}")
    lost = ci.regressions(before, after)
    if lost and ci.revert_to(root, base):
        logger.warning("Reverted %s: it broke %d test(s) that passed before it", stage_name, len(lost))
        return lost
    ci.save(root, after)
    ci.commit(root, f"Fix: {description[:60]}")
    return []


def accepted_state(root: str) -> None:
    """Measure the workspace as the sprint is accepted: the next sprint's baseline."""
    if not ci_applies(root):
        return
    try:
        ci.save(root, ci.take(root, "accepted"), accepted=True)
    except Exception:  # noqa: BLE001 - a missing baseline only means fewer regressions found
        logger.warning("Could not measure the accepted state", exc_info=True)


def suite_locked(root: str) -> None:
    """The first baseline: the scaffold and the locked suite, before any feature."""
    if not ci_applies(root):
        return
    try:
        commit_id = ci.commit(root, "Acceptance suite locked")
        ci.save(root, ci.Snapshot(label="suite locked", commit=commit_id), accepted=True)
    except Exception:  # noqa: BLE001
        logger.debug("Could not record the first baseline", exc_info=True)
