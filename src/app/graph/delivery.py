"""Shipping: the evidence a review is shown, the release gate, and change requests.

    milestone accepted -> [sprint review, with evidence] -> next sprint ... -> release
    release -> [release review] -> complete
    a review's requested change -> change_request -> QA proves it -> the sprint again

A person reviewing a sprint is shown what a software company would show them:
which criteria now pass, what changed, screenshots of the product doing it, the
decisions taken and what is still open. A change they ask for becomes a change
request with its own acceptance test, so it is followed to closure rather than
read once and forgotten.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.acceptance import suite
from app.stacks import contract

logger = logging.getLogger(__name__)

#: Review point: the finished product, before the run completes.
RELEASE_REVIEW = "release"

#: How many times the release gate sends the last sprint back before it
#: escalates. The last sprint's own gate already required every criterion, so a
#: failure here is a regression or a change request added since.
MAX_RELEASE_ATTEMPTS = 2

MOST_SCREENSHOTS = 24
MOST_DIFF_LINES = 40


def _root(state: Any) -> str:
    return state["repository"].root_path


# --- evidence ----------------------------------------------------------------

def screenshots(root: str | Path) -> list[str]:
    """Workspace-relative paths of the screenshots the last acceptance run kept."""
    found = contract.the_pack(root)
    if found is None:
        return []
    pack, record = found
    if not pack.evidence_dir:
        return []
    base = Path(root) / str(record.get("project") or "") / pack.evidence_dir
    if not base.is_dir():
        return []
    shots = sorted(path for path in base.rglob("*.png") if path.is_file())
    return [path.relative_to(Path(root)).as_posix() for path in shots[:MOST_SCREENSHOTS]]


def _what_changed(root: str, since: str | None) -> str:
    if not since:
        return ""
    try:
        result = subprocess.run(
            ["git", "diff", "--stat", since, "HEAD", "--", ".", ":(exclude)docs"],
            cwd=root, capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    lines = result.stdout.strip().splitlines()
    if len(lines) > MOST_DIFF_LINES:
        lines = [*lines[: MOST_DIFF_LINES - 1], f"... and {len(lines) - MOST_DIFF_LINES + 1} more lines", lines[-1]]
    return "\n".join(lines)


def _previous_sprint_tag(root: str, sprint_number: int) -> str | None:
    """The tag the last sprint left, or the first commit."""
    try:
        if sprint_number > 1:
            tag = f"sprint-{sprint_number - 1}"
            check = subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", tag],
                cwd=root, capture_output=True, text=True, timeout=10, check=False,
            )
            if check.returncode == 0:
                return tag
        first = subprocess.run(
            ["git", "rev-list", "--max-parents=0", "HEAD"],
            cwd=root, capture_output=True, text=True, timeout=10, check=False,
        )
        return first.stdout.strip().splitlines()[0] if first.stdout.strip() else None
    except (OSError, subprocess.SubprocessError, IndexError):
        return None


def evidence(state: Any, sprint_number: int, goal: str, heading: str = "") -> str:
    """The page a reviewer reads: criteria, changes, screenshots, decisions, open items."""
    root = _root(state)
    saved = suite.last_result(root)
    lines = [f"# {heading or f'Sprint {sprint_number} review'}: {goal}", ""]
    criteria = list((saved.get("criteria") or {}).values()) + list((saved.get("change_requests") or {}).values())
    if criteria:
        lines += ["## Acceptance criteria", "", "| | Criterion | Status |", "|---|---|---|"]
        for entry in criteria:
            lines.append(f"| {entry.get('id')} | {entry.get('text')} | {str(entry.get('status', '')).upper()} |")
        lines += [
            "",
            f"Measured by the harness: `{saved.get('command')}` - {saved.get('passed', 0)} passed, "
            f"{saved.get('failed', 0)} failed.",
            "",
        ]
    changed = _what_changed(root, _previous_sprint_tag(root, sprint_number))
    if changed:
        lines += ["## What changed", "", "```", changed, "```", ""]
    shots = screenshots(root)
    if shots:
        lines += ["## Screenshots", ""] + [f"- `{path}`" for path in shots] + [""]
    decisions = [d for d in state.get("decisions") or [] if isinstance(d, dict)]
    if decisions:
        lines += ["## Decisions", ""]
        lines += [
            f"- **{d.get('id')}** {d.get('question')} - {d.get('decision')} ({d.get('decided_by')})"
            for d in decisions[-12:]
        ]
        lines.append("")
    open_items = [
        *(state.get("acceptance_open_problems") or []),
        *(f"{cid}: {text}" for cid, text in suite.change_requests(root).items()
          if (saved.get("change_requests") or {}).get(cid, {}).get("status") != "passed"),
    ]
    deferred = suite.deferred(root)
    if open_items or deferred:
        lines += ["## Open", ""]
        lines += [f"- {item}" for item in open_items]
        lines += [f"- {cid} deferred: {why}" for cid, why in deferred.items()]
        lines.append("")
    gaps = [str(gap) for gap in state.get("completion_gaps") or []]
    if gaps:
        # The release page must carry what the release knew it did not prove,
        # beside the counts it measured - a record that says "verified" over a
        # shipped gap is how a 1/10 product came to read as a success.
        # Initiative J.5: every record cites the verdict it actually got.
        lines += [
            "## Completion gaps", "",
            "What this release knows it did not prove - a completed run with these is not plain \"completed\":",
            "",
        ]
        lines += [f"- {gap}" for gap in gaps]
        lines.append("")
    return "\n".join(lines)


def write_evidence(state: Any, sprint_number: int, goal: str, heading: str = "") -> str:
    """Write the evidence page for this review; returns its workspace path."""
    relative = (
        "docs/reviews/release-evidence.md" if heading else f"docs/reviews/sprint-{sprint_number}-evidence.md"
    )
    try:
        target = Path(_root(state)) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(evidence(state, sprint_number, goal, heading), encoding="utf-8")
    except Exception:  # noqa: BLE001 - evidence must never stop a review
        logger.warning("Could not write the review evidence", exc_info=True)
    return relative


# --- the release gate --------------------------------------------------------

def _unit_tests_failing(root: str) -> list[str]:
    """The project's unit tests failing now, or [] - never raises."""
    try:
        from app import ci

        return ci.unit_failures(root)
    except Exception:  # noqa: BLE001 - a run that cannot be made holds nothing back
        logger.debug("Could not run the unit tests before release", exc_info=True)
        return []


def release(state: Any, config: RunnableConfig, ctx: Any) -> dict[str, Any]:
    """Every criterion that is not deferred must pass before the run completes."""
    from app.decisions import record_decision
    from app.graph.workflow import (
        APP_RUN_ID_KEY,
        _escalate_to_a_human,
        _handing_on,
        _review_enabled,
        _stop_if_cancelled,
    )

    _stop_if_cancelled(config["configurable"].get(APP_RUN_ID_KEY))
    root = _root(state)
    update: dict[str, Any] = {}
    failing: list[Any] = []
    summary = "There is no acceptance suite; the milestone reviews were the gate."
    if suite.is_locked(root):
        result = suite.run(root)
        failing = result.failing()
        summary = result.summary()
        if not result.ran:
            failing = failing or ["the suite did not run"]
        vacuous = suite.vacuous_green(root, result)
        if vacuous:
            # A green suite that proved nothing is not a green suite: zero
            # collected tests, or a declared test the runner never collected,
            # makes every "no failures" reading vacuous - including the
            # criteria a dispute deferred from tests that no longer run.
            # Nothing here is waivable by a deferred criterion or a spent
            # budget. See `suite.vacuous_green`.
            summary = "\n".join(vacuous) + "\n" + summary
            failing = [*vacuous, *failing]
    # The project's own unit tests too: they ship with the product and the CI
    # pipeline written below runs them first. Measured on one run: released
    # with every criterion passing or deferred while `npm test` failed on a
    # test a fix stage had written for a deferred criterion.
    unit_failing = [] if failing else _unit_tests_failing(root)
    if unit_failing:
        failing = unit_failing
        summary = (
            "The project's own unit tests do not all pass: "
            + "; ".join(unit_failing[:6])
            + (f" and {len(unit_failing) - 6} more" if len(unit_failing) > 6 else "")
            + ". They ship with the product and its CI pipeline runs them first. Fix the "
            "product where it is wrong, or the test where it asks for what the product was "
            "never meant to do."
        )
    if failing:
        attempts = int(state.get("release_attempts") or 0) + 1
        text = (
            "The product is not ready to release - the acceptance suite says:\n"
            + summary
            if not unit_failing else
            "The product is not ready to release. " + summary
        )
        if attempts <= MAX_RELEASE_ATTEMPTS:
            logger.warning("Release held back: acceptance criteria failing; the last sprint goes again")
            record_decision(
                state, update, point="release",
                question="Is the product ready to release?",
                options=["release", "fix the failing criteria first"],
                decision="fix the failing criteria first",
                rationale=summary,
            )
            return _handing_on(
                **update,
                stage="technical_lead",
                release_attempts=attempts,
                revision_comments=[*(state.get("revision_comments") or []), text],
                milestone_plan=None,
                specialist_outputs={},
                remediation=None,
                test_round=0,
                defect_cursor=0,
                milestone_revision_count=0,
            )
        return _escalate_to_a_human(state, error=text, release_attempts=attempts)

    deferred = suite.deferred(root)
    # What this release knows it did not prove, so no record of the run can
    # read as a plain success: the gaps ride the run record
    # (`completion_gaps`), the decision below, and every surface that shows
    # the completion. A criterion is deferred by a dispute or by QA; problems
    # the suite was locked with survived its rounds; a plan dispatched with
    # problems noted shipped with them; a setup that was never proven leaves
    # every later proof weaker. See Initiative J.4 in docs/improvement-plan.md.
    gaps: list[str] = []
    if not suite.is_locked(root):
        gaps.append("No acceptance suite was locked; the milestone reviews were the only gate.")
    for cid in sorted(deferred):
        gaps.append(f"{cid} ships deferred, unproven by the suite: {deferred[cid]}")
    reclassified = sorted(set(state.get("suite_reclassified_tests") or []))
    if reclassified:
        gaps.append(
            f"{len(reclassified)} locked test(s) were reclassified under dispute: "
            + ", ".join(reclassified[:5])
        )
    gaps.extend(
        f"The suite was locked with this still open: {problem}"
        for problem in state.get("acceptance_open_problems") or []
    )
    gaps.extend(
        f"The plan was dispatched with this noted against it: {problem}"
        for problem in state.get("work_order_problems") or []
    )
    unit_gap = _no_unit_tests_ran(root)
    if unit_gap:
        gaps.append(unit_gap)
    scaffolded = state.get("scaffold_result") or {}
    if scaffolded and not scaffolded.get("ok"):
        gaps.append(
            "The project setup was never proven: "
            + str(scaffolded.get("problem") or "its smoke tests did not pass")
        )
    # What the run itself set aside on the way: an escalation's open issues,
    # and review findings fast delivery recorded as risks instead of fixing.
    # They reached the record of each sprint and never the run's verdict, so a
    # run that carried them read as plain "completed" (Initiative AE).
    gaps.extend(f"An escalation left this open: {issue}" for issue in state.get("known_issues") or [])
    gaps.extend(_findings_recorded_as_risks(state))
    gaps.extend(_what_the_release_re_check_finds(state, root))
    gaps.extend(_code_the_product_does_not_run(root))
    if gaps:
        update["completion_gaps"] = gaps
    # What someone who did not write it needs to test and ship it, from the
    # stack pack's own verified commands. See `app.stacks.release`.
    from app.stacks import release as release_files

    # What a stage left behind that no suite runs and nothing uses is not part
    # of what is handed over. See `repository.clear_the_throwaways_left_behind`.
    from app.graph.workflow import _clear_the_throwaways

    _clear_the_throwaways(root)
    packaged = release_files.write(root).describe()
    record_decision(
        state, update, point="release",
        question="Is the product ready to release?",
        options=["release", "fix the failing criteria first"],
        decision="release",
        rationale=(
            "Every acceptance criterion passes"
            + (f", except those deferred: {', '.join(sorted(deferred))}" if deferred else "")
            + ".\n" + (f"{packaged}\n" if packaged else "") + summary
            + (
                "\nShips with gaps a plain 'completed' would hide:\n"
                + "\n".join(f"- {gap}" for gap in gaps)
                if gaps else ""
            )
        ),
    )
    goal = str(getattr(state.get("product_intake"), "product_name", "") or "the product")
    write_evidence({**state, **update}, len(getattr(state.get("sprint_plan"), "sprints", None) or []), goal, "Release")
    next_stage = "user_review_release" if _review_enabled(state, RELEASE_REVIEW) else "complete"
    return _handing_on(**update, stage=next_stage)


# --- change requests ------------------------------------------------------------

def change_request(state: Any, config: RunnableConfig, ctx: Any) -> dict[str, Any]:
    """A reviewer's requested change becomes CR-n, proven by its own acceptance test."""
    from app.decisions import record_decision
    from app.graph.workflow import _handing_on

    root = _root(state)
    comments = [str(c).strip() for c in state.get("revision_comments") or [] if str(c).strip()]
    asked = comments[0] if comments else "(no comment given)"
    update: dict[str, Any] = {}
    if suite.is_locked(root) or suite.criteria(root):
        change_id = suite.add_change_request(root, asked)
        record_decision(
            state, update, point="change_request",
            question="What does the reviewer want changed?",
            decision=f"{change_id}: {asked}",
            rationale="Recorded as a change request; QA writes its acceptance test and the sprint is planned again to make it pass.",
            decided_by="user",
            comment=asked,
            affects=[change_id],
        )
        return _handing_on(
            **update,
            stage="acceptance_author",
            acceptance_return_to="technical_lead",
            acceptance_round=0,
            acceptance_feedback=[],
            revision_comments=comments,
            milestone_plan=None,
            specialist_outputs={},
            remediation=None,
            test_round=0,
            defect_cursor=0,
            milestone_revision_count=0,
        )
    # No suite to prove it with: the lead plans it from the comment, as before.
    return _handing_on(stage="technical_lead", revision_comments=comments)


def change_request_brief(root: str) -> list[str]:
    """What the technical lead is told about open change requests after QA wrote their tests."""
    covered = suite.coverage(root)
    return [
        f"Change request {cid}: {text}. Its acceptance test"
        + (f" ({'; '.join(covered[cid])})" if covered.get(cid) else "")
        + " must pass before this sprint is accepted."
        for cid, text in suite.change_requests(root).items()
    ]



#: The decision fast delivery records when a milestone review's findings are
#: carried as risks instead of fixed; `release` finds them by it.
RECORDED_AS_RISKS = "record the findings as risks and go on"


def _findings_recorded_as_risks(state: Any) -> list[str]:
    """One gap per milestone review whose findings were recorded as risks, not fixed."""
    gaps = []
    for record in state.get("decisions") or []:
        if not isinstance(record, dict) or record.get("decision") != RECORDED_AS_RISKS:
            continue
        rationale = str(record.get("rationale") or "")
        findings = rationale.split("\n", 1)[1] if "\n" in rationale else rationale
        gaps.append(
            f"A milestone review's findings were recorded as risks, not fixed ({record.get('id')}): "
            + " ".join(findings.split())[:400]
        )
    return gaps


def _what_the_release_re_check_finds(state: Any, root: str) -> list[str]:
    """What the checks that read the files find breaking the product now, as gaps. Never raises.

    They ran at each milestone review, and later fixes can break what they
    passed; reading the files costs nothing beside a release. Not the locked
    suite's own files: it ran just now, which a static reading of it cannot
    overrule.
    """
    try:
        from app.analysis.integration_checks import problems_that_break_the_product

        locked = suite.relative_directory(root) if suite.is_locked(root) else ""
        found = problems_that_break_the_product(
            root,
            getattr(state.get("stack_selection"), "technology_stack", None),
            getattr(state.get("document"), "text", "") or "",
        )
    except Exception:  # noqa: BLE001 - a re-check that cannot run adds nothing
        logger.debug("Could not re-check the product at release", exc_info=True)
        return []
    found = [problem for problem in found if not (locked and locked in problem)]
    return [f"At release, reading the files still finds: {problem}"[:600] for problem in found[:8]]


def _code_the_product_does_not_run(root: str) -> list[str]:
    """A second copy nothing serves, and unit tests of other code, as gaps. Never raises."""
    try:
        from app.stacks.scaffold import code_the_product_does_not_run

        return [f"Code the product does not run: {problem}"[:600] for problem in code_the_product_does_not_run(root)]
    except Exception:  # noqa: BLE001
        return []


def _no_unit_tests_ran(root: Any) -> str:
    """A gap when the product's own unit command ran no test at all; "" otherwise or when unknown.

    Measured on one run: 2,863 lines of product code, and `npm test` exited 0 -
    the page runner passes with no tests and pytest's "no tests ran" is taken
    as success - so the product shipped with no unit test and no record said so.
    """
    try:
        from pathlib import Path

        from app.acceptance import junit
        from app.stacks import contract

        found = contract.the_pack(root)
        record = contract.read(root) or {}
        report = str(getattr(found[0], "unit_report", "") or "") if found else ""
        project = str(record.get("project") or "")
        if not report or not project:
            return ""
        parsed = junit.read(Path(root) / project / report)
    except Exception:  # noqa: BLE001 - the release says nothing it cannot measure
        return ""
    if not parsed.found or parsed.tests:
        return ""
    return "The product ships no unit tests: its unit test command ran none and exited as a pass."
