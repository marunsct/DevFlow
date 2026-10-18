"""The stages between an approved architecture and the first sprint plan.

    scaffold -> acceptance_author -> acceptance_review -> [user review] -> scrum_master

and the parts of every later stage that read the acceptance suite. Kept out of
`workflow.py` so the definition of done has one home; the graph builder wraps
each function in a node with the run's models and checkpointer.

The order is how a software company starts a product: the project is set up so
its tests run, QA writes the tests that decide when it is done from the agreed
criteria, a QA lead reviews them, and only then is the work planned - against
criteria every sprint can be measured by.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.acceptance import requests as acceptance_requests
from app.acceptance import suite
from app.acceptance.criteria import number
from app.stacks import contract, pack_named

logger = logging.getLogger(__name__)

#: How many times QA writes the suite before it is locked as it stands. Each
#: pass after the first is handed what the last review found.
MAX_ACCEPTANCE_ROUNDS = 3

#: Review point: the acceptance suite, before it is locked.
ACCEPTANCE_REVIEW = "acceptance_tests"


@dataclass
class Context:
    """What every node of the run is built with."""

    model: Any
    judgement_model: Any
    checkpointer: Any
    repo_root: str | None
    allow_subdirectories: bool = True


def _root(state: Any) -> str:
    return state["repository"].root_path


def _stack(state: Any) -> Any:
    return getattr(state.get("stack_selection"), "technology_stack", None)


# --- scaffold ------------------------------------------------------------------

def scaffold(state: Any, config: RunnableConfig, ctx: Context) -> dict[str, Any]:
    """Scaffold the chosen pack into the project directory, proven by its smoke tests."""
    from app.graph.workflow import (
        APP_RUN_ID_KEY,
        _escalate_to_a_human,
        _handing_on,
        _stop_if_cancelled,
    )

    _stop_if_cancelled(config["configurable"].get(APP_RUN_ID_KEY))
    root = _root(state)
    pack = pack_named(state.get("stack_pack"))
    update: dict[str, Any] = {}
    already_done = bool((state.get("scaffold_result") or {}).get("ok"))
    if pack is not None and not already_done:
        from app.stacks.scaffold import scaffold as scaffold_pack
        from app.tools.repository import pin_the_directory_the_product_names, pinned_project_directory

        title = str(getattr(state.get("product_intake"), "product_name", "") or "").strip()
        project = pinned_project_directory(Path(root)) or pin_the_directory_the_product_names(root, title)
        if project:
            from app.stacks import stated_module

            brief = getattr(state.get("document"), "text", "") or ""
            package = stated_module(brief) if pack.language == "python" else None
            result = scaffold_pack(root, pack, project, title or project, package=package)
            if not result.ok:
                # One retry of the whole scaffold: the commands inside a single
                # attempt are each retried once already, so a second attempt
                # covers the state around them - a worker recreated mid-install,
                # a registry blip longer than one command's retry.
                logger.warning(
                    "Scaffold %s was not kept (%s); trying the whole scaffold once more",
                    pack.name, result.problem,
                )
                result = scaffold_pack(root, pack, project, title or project, package=package)
            update["scaffold_result"] = {
                "ok": result.ok, "pack": pack.name, "project": project, "problem": result.problem,
            }
            if result.ok:
                logger.info("Scaffolded %s into %s/; its smoke tests passed", pack.title, project)
                _decide(
                    state, update, point="scaffold",
                    question="How is the project set up?",
                    options=[pack.title, "stop and ask"],
                    decision=pack.title,
                    rationale=(
                        f"The {pack.title} scaffold installed and passed its own unit and acceptance "
                        "smoke tests."
                    ),
                )
            else:
                # Fail closed. An unproven setup used to continue "left to the
                # agents": measured on one run, the acceptance smoke test ran
                # zero tests and exited 0, the scaffold was abandoned, its
                # files stayed with no contract behind them - "the harness
                # keeps this" in their own comments, and nothing kept them -
                # and a later sprint's tester switched the next sprint's tests
                # off, with nothing to put them back. A run whose setup was
                # never proven stops and says why: parked for a person when one
                # is watching, failed when not. See `app.graph.escalation`.
                logger.error("Scaffold %s could not be proven twice: %s", pack.name, result.problem)
                _decide(
                    state, update, point="scaffold",
                    question="How is the project set up?",
                    options=[pack.title, "stop and ask"],
                    decision="stop and ask",
                    rationale=(
                        f"The {pack.title} scaffold could not be proven after two full attempts: "
                        f"{result.problem}"
                    ),
                )
                return _escalate_to_a_human(
                    state,
                    error=(
                        f"The {pack.title} scaffold could not be proven after two full attempts: "
                        f"{result.problem}. Nothing is built on an unproven setup; every later "
                        "gate would inherit the doubt."
                    ),
                    **{key: value for key, value in update.items() if key != "stage"},
                )
    elif pack is None and not already_done:
        set_up = _set_up_a_stack_no_pack_covers(state, config, ctx)
        if set_up is not None:
            return set_up
    return _handing_on(**update, stage="acceptance_author")


def _set_up_a_stack_no_pack_covers(state: Any, config: RunnableConfig, ctx: Context) -> dict[str, Any] | None:
    """Have the testing specialist set the project up, and prove it like a pack; None to skip.

    See `app.stacks.custom_setup`. A setup that is not proven after
    `ATTEMPTS` is left to the agents, as every custom stack was before; so is a
    stage that ran out of attempts of its own - a setup is worth having, not
    worth a run.
    """
    from app.agents.specialists import create_specialist_agent
    from app.graph.workflow import _handing_on, _run_gated_agent, _the_stage_that_paused
    from app.stacks import custom_setup, product_kind
    from app.tools.repository import pin_the_directory_the_product_names, pinned_project_directory

    stack = _stack(state)
    previous = state.get("scaffold_result") or {}
    if not custom_setup.enabled() or stack is None or previous.get("left_to_the_agents"):
        return None
    root = _root(state)
    title = str(getattr(state.get("product_intake"), "product_name", "") or "").strip()
    project = pinned_project_directory(Path(root)) or pin_the_directory_the_product_names(root, title)
    if not project:
        return None
    project_root = Path(root) / project
    attempt = int(previous.get("setup_attempts") or 0)
    # A manifest found on the way back from the setup stage's own approval
    # pause is the one it wrote before pausing. Measured on one run: its
    # `npm install` waited for approval, the stage was entered again, found
    # the package.json it had just written, and handed on with nothing
    # installed and the setup never proven.
    resuming = str(_the_stage_that_paused(state) or "").startswith("stack_setup_")
    if attempt == 0 and not resuming and custom_setup.already_set_up(project_root):
        return None
    brief = getattr(state.get("document"), "text", "") or ""

    def left_to_the_agents(update: dict[str, Any], why: str) -> dict[str, Any]:
        custom_setup.leave_to_the_agents(project_root)
        update["scaffold_result"] = {
            "ok": False, "pack": None, "project": project, "problem": why, "left_to_the_agents": True,
        }
        _decide(
            state, update, point="scaffold", question="How is the project set up?",
            options=["a proven setup", "left to the agents"], decision="left to the agents",
            rationale=f"No pack covers this stack, and the setup could not be proven: {why}",
        )
        logger.warning("The custom stack's setup was not proven; left to the agents: %s", why)
        return _handing_on(**update, stage="acceptance_author")

    if attempt == 0 and not resuming:
        replayed = custom_setup.replay(project_root, stack)
        if replayed:
            proven = custom_setup.prove(root, project, stack, brief=brief, title=title or project)
            if proven.ok:
                update = {
                    "stack_pack": custom_setup.PROVEN_SETUP,
                    "scaffold_result": {"ok": True, "pack": custom_setup.PROVEN_SETUP, "project": project, "problem": ""},
                }
                _decide(
                    state, update, point="scaffold", question="How is the project set up?",
                    options=["a proven setup", "left to the agents"], decision="a proven setup",
                    rationale="No pack covers this stack; a setup proven in an earlier run on the same stack "
                    "was replayed and passed its unit and acceptance smoke tests again.",
                )
                logger.info("Replayed a setup proven in an earlier run on this stack in %s/", project)
                return _handing_on(**update, stage="acceptance_author")
            logger.warning("A setup proven in an earlier run did not prove here; asking the setup stage: %s", proven.problem)
            for relative in replayed:
                (project_root / relative).unlink(missing_ok=True)

    agent = create_specialist_agent(
        "testing", model=ctx.model, checkpointer=ctx.checkpointer,
        repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories,
    )
    update = _run_gated_agent(
        state, config,
        stage_name=f"stack_setup_{attempt}",
        agent=agent,
        initial_request=custom_setup.build_setup_request(
            project, stack, product_kind(stack, brief), str(previous.get("problem") or ""),
            specification=state.get("technical_specification"),
        ),
        output_key="__stack_setup__",
        next_stage="acceptance_author",
    )
    if "__stack_setup__" not in update:
        if update.get("stage") == "failed":
            return left_to_the_agents({}, str(update.get("error") or "the setup stage did not finish"))
        return update  # paused for approval, or retrying
    update.pop("__stack_setup__")
    update.pop("stage", None)
    result = custom_setup.prove(root, project, stack, brief=brief, title=title or project)
    if result.ok:
        update["stack_pack"] = custom_setup.PROVEN_SETUP
        update["scaffold_result"] = {"ok": True, "pack": custom_setup.PROVEN_SETUP, "project": project, "problem": ""}
        _decide(
            state, update, point="scaffold", question="How is the project set up?",
            options=["a proven setup", "left to the agents"], decision="a proven setup",
            rationale="No pack covers this stack; the setup stage's project installed and passed "
            "its own unit and acceptance smoke tests through the commands it declared.",
        )
        logger.info("Proved the custom stack's setup in %s/", project)
        return _handing_on(**update, stage="acceptance_author")
    if attempt + 1 < custom_setup.ATTEMPTS:
        update["scaffold_result"] = {
            "ok": False, "pack": None, "project": project, "problem": result.problem,
            "setup_attempts": attempt + 1,
        }
        logger.warning("The custom stack's setup was not proven; sent back: %s", result.problem)
        return _handing_on(**update, stage="scaffold")
    return left_to_the_agents(update, result.problem)


# --- acceptance author ---------------------------------------------------------

def acceptance_author(state: Any, config: RunnableConfig, ctx: Context) -> dict[str, Any]:
    """QA writes the acceptance suite from the numbered criteria."""
    from app.agents.specialists import create_specialist_agent
    from app.graph.workflow import _handing_on, _run_gated_agent

    root = _root(state)
    criteria = suite.criteria(root)
    if not criteria:
        brief = getattr(state.get("document"), "text", "") or ""
        criteria = number(brief, state.get("product_intake"))
        if not criteria:
            logger.warning("No acceptance criteria could be read from the brief or the intake")
            return _handing_on(stage="scrum_master")
        suite.save_criteria(root, criteria)
    suite.unlock(root)
    round_ = int(state.get("acceptance_round") or 0)
    feedback = [*(state.get("acceptance_feedback") or []), *(state.get("revision_comments") or [])]
    # Written by the build model in fast delivery, and reviewed by the
    # judgement model. See `app.delivery`.
    from app import delivery

    agent = create_specialist_agent(
        "testing", model=ctx.model if delivery.fast() else ctx.judgement_model, checkpointer=ctx.checkpointer,
        repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories,
    )
    request = acceptance_requests.build_author_request(
        root, criteria, _stack(state), feedback=feedback, change_requests=suite.change_requests(root),
        brief=getattr(state.get("document"), "text", "") or "",
        testability=_the_testability_advice(state),
    )
    update = _run_gated_agent(
        state, config,
        stage_name=f"acceptance_author_{round_}",
        agent=agent,
        initial_request=request,
        output_key="__acceptance_author__",
        next_stage="acceptance_review",
    )
    if "__acceptance_author__" not in update:
        return update
    output = update.pop("__acceptance_author__")
    reasons = acceptance_requests.not_automatable(getattr(output, "blockers", None) or [])
    # A criterion the suite has a test for is automatable: that test is how.
    # Deferring it takes it out of the release gate. One run's QA, repairing a
    # reopened suite and unable to fix the product, listed the product's bugs as
    # blockers - "AC-5: product bug, the filter buttons never fire" - and edit,
    # both filter criteria and persistence were deferred, each with tests in the
    # suite that were failing for exactly those bugs.
    tested = {criterion for criterion, names in suite.coverage(root).items() if names}
    refused = sorted(criterion for criterion in reasons if criterion in tested)
    if refused:
        logger.warning(
            "QA named %s as not automatable, but the suite tests %s; not deferred",
            ", ".join(refused), "them" if len(refused) > 1 else "it",
        )
    # And only a criterion of this product: one run's QA deferred "AC-14", with
    # nine criteria, and the release would have recorded it as set aside.
    known = {criterion.id for criterion in suite.criteria(root)}
    unknown = sorted(criterion for criterion in reasons if criterion not in known)
    if unknown:
        logger.warning("QA named %s as not automatable, which are not criteria here; ignored", ", ".join(unknown))
    reasons = {
        criterion: why for criterion, why in reasons.items() if criterion not in tested and criterion in known
    }
    if reasons:
        suite.defer(root, reasons)
        logger.info("QA marked %s as not automatable", ", ".join(sorted(reasons)))
    return {
        **update,
        "acceptance_round": round_ + 1,
        "acceptance_feedback": [],
        "revision_comments": [],
    }


# --- acceptance review ---------------------------------------------------------

def _scenarios(root: str) -> str:
    """`docs/acceptance_tests.md`: the suite in plain language, grouped by criterion."""
    covered = suite.coverage(root)
    deferred = suite.deferred(root)
    lines = [
        "# Acceptance tests",
        "",
        "The tests that decide when this product is done, grouped by the criterion each "
        "proves. Written by QA before the product was built; locked once approved.",
        "",
    ]
    for criterion in suite.criteria(root):
        lines.append(f"## {criterion.id}: {criterion.text}")
        if criterion.id in deferred:
            lines.append(f"- not tested automatically: {deferred[criterion.id]}")
        for name in covered.get(criterion.id, []):
            lines.append(f"- {name}")
        if criterion.id not in deferred and criterion.id not in covered:
            lines.append("- (no test)")
        lines.append("")
    for change_id, text in suite.change_requests(root).items():
        lines.append(f"## {change_id}: {text}")
        lines.extend(f"- {name}" for name in covered.get(change_id, []))
        lines.append("")
    return "\n".join(lines)


def acceptance_review(state: Any, config: RunnableConfig, ctx: Context) -> dict[str, Any]:
    """Check the suite mechanically, have a QA lead judge it, then lock it."""
    from app.agents.acceptance_reviewer import (
        build_acceptance_review_request,
        create_acceptance_reviewer_agent,
    )
    from app.graph.workflow import _handing_on, _record_document, _review_enabled, _run_gated_agent

    root = _root(state)
    rounds = int(state.get("acceptance_round") or 1)
    problems = suite.gaps(root)
    result = suite.run(root)
    if not result.ran:
        problems.append(
            f"The suite does not run: {result.problem}.\n{result.output[-1500:]}".strip()
        )
    problems.extend(suite.tests_that_broke_themselves(root, result))
    vacuous = suite.vacuous_green(root, result)
    problems.extend(vacuous)
    problems.extend(suite.tests_that_need_what_they_never_made(root, result))
    problems.extend(suite.locators_nobody_sees(root))
    problems.extend(suite.locators_that_pick_one(root))
    problems.extend(suite.locators_by_a_name_the_role_never_has(root))
    problems.extend(suite.tests_that_never_open_the_page(root))
    problems.extend(suite.tests_that_access_storage_before_opening_the_page(root))
    problems.extend(suite.tests_that_expect_what_they_never_gave(root))
    problems.extend(suite.tests_that_assert_an_unstated_order(root))
    problems.extend(suite.locators_that_contradict_their_assertions(root))
    problems.extend(
        suite.controls_never_found_by_name(root, getattr(state.get("document"), "text", "") or "")
    )
    problems.extend(suite.assertions_that_do_not_exist(root))
    problems.extend(suite.locators_that_do_not_exist(root))
    problems.extend(suite.tests_with_module_system_mismatch(root))
    problems.extend(suite.tests_with_unawaited_async_helpers(root))
    problems.extend(suite.locators_with_invalid_name_option(root))
    if not result.ran:
        if rounds < MAX_ACCEPTANCE_ROUNDS + 2:
            logger.warning("Acceptance suite could not run (exit %s); sent back to QA", result.exit_code)
            return _handing_on(stage="acceptance_author", acceptance_feedback=problems)
        logger.error("Acceptance suite failed to run after %d rounds: %s", rounds, result.problem)
        return _handing_on(
            stage="failed",
            error=f"The acceptance suite cannot run or load after {rounds} rounds: {result.problem}\n{result.output[-1000:]}",
        )
    if vacuous:
        # A suite that proved nothing is never locked, whatever was spent on
        # it: the round count waives advice, not evidence. A locked suite is
        # the run's definition of done, and an empty report defines nothing.
        # See `suite.vacuous_green`.
        if rounds < MAX_ACCEPTANCE_ROUNDS + 2:
            logger.warning("Acceptance suite proved nothing (%d reason(s)); sent back to QA", len(vacuous))
            return _handing_on(stage="acceptance_author", acceptance_feedback=problems)
        logger.error("Acceptance suite still proves nothing after %d rounds", rounds)
        return _handing_on(
            stage="failed",
            error=f"The acceptance suite proves nothing after {rounds} rounds: " + "; ".join(vacuous)[:1500],
        )
    if problems and rounds < MAX_ACCEPTANCE_ROUNDS:
        logger.info("Acceptance suite sent back to QA: %d problem(s)", len(problems))
        return _handing_on(stage="acceptance_author", acceptance_feedback=problems)

    findings: list[str] = []
    update: dict[str, Any] = {}
    if not problems:
        already_passing = [test.name for test in result.report.tests if test.outcome == "passed"]
        deferred = suite.deferred(root)
        deferred_text = (
            "--- Criteria QA says no automated test can check ---\n"
            + "\n".join(f"- {cid}: {why}" for cid, why in deferred.items())
            + "\nJudge whether each reason holds; a criterion that can be tested must be.\n\n"
            if deferred else ""
        )
        agent = create_acceptance_reviewer_agent(
            model=ctx.judgement_model, checkpointer=ctx.checkpointer,
            repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories,
        )
        request = build_acceptance_review_request(
            acceptance_requests.criteria_text(suite.criteria(root), deferred),
            acceptance_requests.suite_text(root),
            result.summary(),
            already_passing,
            deferred_text,
            brief=getattr(state.get("document"), "text", "") or "",
            testability=_the_testability_advice(state),
        )
        update = _run_gated_agent(
            state, config,
            stage_name=f"acceptance_review_{rounds}",
            agent=agent,
            initial_request=request,
            output_key="__acceptance_review__",
            next_stage="acceptance_review",
        )
        if "__acceptance_review__" not in update:
            return update
        review = update.pop("__acceptance_review__")
        update.pop("stage", None)
        if not review.approved and review.findings:
            findings = [str(item) for item in review.findings]
            from app import delivery

            # Fast delivery sends a suite back once; what is still open after
            # that is locked in as an open problem, as after the full count.
            if rounds < (2 if delivery.fast() else MAX_ACCEPTANCE_ROUNDS):
                logger.info("QA lead sent the acceptance suite back: %d finding(s)", len(findings))
                return _handing_on(**update, stage="acceptance_author", acceptance_feedback=findings)

    suite.lock(root)
    from app.graph.engineering import suite_locked

    suite_locked(root)
    open_problems = [*problems, *findings]
    _record_document(state, "docs/acceptance_tests.md", _scenarios(root))
    tests = len(result.report.tests)
    _decide(
        state, update, point="acceptance_tests",
        question="Is the acceptance suite a fair definition of done?",
        options=["lock it", "send it back to QA"],
        decision="lock it",
        rationale=(
            f"{tests} test(s) over {len(suite.criteria(root))} criteria; "
            + ("every criterion is covered and the QA lead approved."
               if not open_problems else
               f"locked after {rounds} round(s) with these still open: " + "; ".join(open_problems))
            + (f"\n{changed}" if (changed := suite.changes_at_this_lock(root)) else "")
        ),
    )
    logger.info("Acceptance suite locked: %d test(s)", tests)
    # A change request's tests go straight back to the sprint that asked for
    # them, carrying what must now pass. See `app.graph.delivery`.
    return_to = state.get("acceptance_return_to")
    if return_to:
        from app.graph.delivery import change_request_brief

        return _handing_on(
            **update,
            stage="technical_lead" if return_to == SPRINT_REPLAN else return_to,
            acceptance_return_to=None,
            acceptance_feedback=[],
            acceptance_open_problems=open_problems,
            acceptance_result=result.as_dict(),
            # Only a change request is planned again; a repaired suite goes
            # back to the round it was found in with that round's state.
            revision_comments=(
                change_request_brief(root) if return_to == "technical_lead"
                else list(state.get("revision_comments") or [])
            ),
        )
    next_stage = "user_review_acceptance" if _review_enabled(state, ACCEPTANCE_REVIEW) else "scrum_master"
    return _handing_on(
        **update,
        stage=next_stage,
        acceptance_feedback=[],
        acceptance_open_problems=open_problems,
        acceptance_result=result.as_dict(),
    )


# --- what later stages read --------------------------------------------------------

def criteria_due(state: Any) -> list[str] | None:
    """The criteria the current sprint must leave passing, or None for "all of them".

    A sprint delivers the criteria the plan assigned to it and keeps every
    earlier sprint's passing. A plan that assigned none makes the last sprint
    answer for all of them, and no earlier sprint for any.
    """
    plan = state.get("sprint_plan")
    sprints = list(getattr(plan, "sprints", None) or [])
    index = int(state.get("current_sprint_index") or 0)
    root = _root(state)
    known = [c.id for c in suite.criteria(root)]
    if not known:
        return []
    assigned_any = any(getattr(s, "criteria", None) for s in sprints)
    if not sprints or not assigned_any:
        return known if index >= len(sprints) - 1 else []
    due: list[str] = []
    for sprint in sprints[: index + 1]:
        for item in getattr(sprint, "criteria", None) or []:
            if item in known and item not in due:
                due.append(item)
    if index >= len(sprints) - 1:
        due.extend(item for item in known if item not in due)
    return due + list(suite.change_requests(root))


def criteria_brief(state: Any) -> str:
    """What the technical lead must plan this milestone to make pass, or ""."""
    root = _root(state)
    if not suite.criteria(root) or not suite.is_locked(root):
        return ""
    due = criteria_due(state) or []
    if not due:
        return ""
    texts = {c.id: c.text for c in suite.criteria(root)}
    texts.update(suite.change_requests(root))
    covered = suite.coverage(root)
    saved = suite.last_result(root)
    status = {
        **{k: v.get("status") for k, v in (saved.get("criteria") or {}).items()},
        **{k: v.get("status") for k, v in (saved.get("change_requests") or {}).items()},
    }
    lines = []
    for item in due:
        tests = covered.get(item, [])
        lines.append(
            f"- {item}: {texts.get(item, '')}"
            + (f" - currently {str(status[item]).upper()}" if status.get(item) else "")
            + (f"\n    tests: {'; '.join(tests[:4])}" if tests else "")
        )
    return (
        "\n\n--- Acceptance criteria this milestone must leave passing ---\n"
        + "\n".join(lines)
        + f"\nThe tests are in `{suite.relative_directory(root)}/` and are locked: read them to "
        "see exactly what each checks - the labels, routes, commands or names it uses - and "
        "plan work orders that make them pass. The milestone is not accepted until they do."
    )


def run_for_sprint(state: Any) -> tuple[suite.AcceptanceResult | None, list[str]]:
    """The harness's own run of the suite, and the ids due now. (None, []) when there is no suite."""
    root = _root(state)
    if not suite.criteria(root) or not suite.is_locked(root):
        return None, []
    due = criteria_due(state) or []
    return suite.run(root), due


def _the_testability_advice(state: Any) -> list[str]:
    """The testing specialist's advice the specification adopted. See `app.agents.specialist_advice`."""
    try:
        from app.agents.specialist_advice import adopted

        return adopted(state.get("specialist_advice"), state.get("technical_specification"), "testing")
    except Exception:  # noqa: BLE001 - a suite written without it is the suite there was
        return []


#: A failure met on the page itself: a control a test reached for, or the page it opened.
_ON_THE_PAGE = re.compile(r"\b(?:locator|page)\.\w+:|\bgetBy[A-Z]\w*\(|\bnet::ERR_")
#: A page file named in an error: the page's build failed, not the service's.
_A_PAGE_FILE = re.compile(r"[\w/.-]+\.(?:tsx|jsx|vue|svelte|astro)\b")


def _owner_for(state: Any, detail: str = "") -> str:
    """Who fixes a failing criterion when the test round did not say.

    In a product with a page and a service, a failure met on the page - a
    control that never appeared - is the page's specialist's. Measured on one
    run: every defect went to the backend specialist, every page test had failed
    its first control, and no fixer in two rounds ever wrote the page.
    """
    kind = getattr(_stack(state), "product_kind", "") or ""
    if kind == "browser_app":
        return "ui_ux"
    if kind == "fullstack" and (_ON_THE_PAGE.search(detail or "") or _A_PAGE_FILE.search(detail or "")):
        return "ui_ux"
    return "backend"


def _failing_due(state: Any) -> tuple[list[dict[str, Any]], str]:
    """The due criteria the harness's last run of the suite found failing, and its command."""
    root = _root(state)
    saved = suite.last_result(root)
    if not saved or not suite.is_locked(root):
        return [], ""
    due = criteria_due(state) or []
    entries = {**(saved.get("criteria") or {}), **(saved.get("change_requests") or {})}
    failing = [
        entries[item] for item in due
        if item in entries and entries[item].get("status") in {"failed", "untested"}
    ]
    if not saved.get("ran") and due:
        failing = [entries[item] for item in due if item in entries] or failing
    return failing, str(saved.get("command") or "")


def criteria_failing_now(state: Any, text: str) -> list[str]:
    """The criteria `text` names that the harness's last run of the suite found failing."""
    from app.acceptance.junit import tags_in

    saved = suite.last_result(_root(state)) or {}
    entries = {**(saved.get("criteria") or {}), **(saved.get("change_requests") or {})}
    return [
        tag for tag in tags_in(text)
        if (entries.get(tag) or {}).get("status") in {"failed", "untested"}
    ]


def passing_since_reported(state: Any, failing: list[str]) -> list[str]:
    """`failing` when every test of each passes in a measurement taken since, else [].

    `failing` is what a test round found failing when it reported a defect. A
    measurement taken by one of this round's fixes - `before` or `after` it, in
    CI's own labels - is later than that report; a fix CI reverted is never
    saved, so its passing tests cannot count.

    Measured on one run: two defects in one round had one cause, the first fix
    made every criterion of the second pass, and the second was handed to a
    fixer anyway. Told to fix what already worked, it spent its budget on a
    later sprint's criteria instead.
    """
    import re

    from app import ci
    from app.acceptance.junit import tags_in

    if not failing:
        return []
    latest = ci.load(_root(state), "latest")
    measured_since = rf"(?:before|after) defect_fix_{int(state.get('test_round', 0) or 0)}_\d+"
    if latest is None or not re.fullmatch(measured_since, str(latest.label or "")):
        return []
    for criterion in failing:
        outcomes = [
            outcome for key, outcome in (latest.acceptance or {}).items()
            if criterion in tags_in(key)
        ]
        if not outcomes or any(outcome != "passed" for outcome in outcomes):
            return []
    return list(failing)


def passing_in_the_round(state: Any, failing: list[str]) -> list[str]:
    """`failing` when each passes in the harness's run of the suite for this round, else [].

    For a defect an earlier round reported: the round's own run of the locked
    suite is later than that report, whoever's fix it measures. Measured on one
    run: the second of two defects with one cause had its fix reverted, the
    first fix had already made its criterion pass, and the defect stayed open
    through two green rounds until the sprint failed on "exhausted remediation
    attempts" with all of its own criteria passing.
    """
    if not failing:
        return []
    saved = suite.last_result(_root(state)) or {}
    if not saved.get("ran"):
        return []
    entries = {**(saved.get("criteria") or {}), **(saved.get("change_requests") or {})}
    if all((entries.get(criterion) or {}).get("status") == "passed" for criterion in failing):
        return list(failing)
    return []


def done_by_the_definition(state: Any) -> list[str]:
    """The criteria due now when every one of them passes in the harness's last run, else [].

    For a fix stage working on something other than a criterion: the brief's
    definition of done holds, so what it is fixing is the team's own code and
    unit tests disagreeing, not what a user meets.
    """
    root = _root(state)
    if not suite.is_locked(root):
        return []
    saved = suite.last_result(root) or {}
    if not saved.get("ran"):
        return []
    excused = suite.deferred(root)
    due = [c for c in (criteria_due(state) or []) if c not in excused]
    entries = {**(saved.get("criteria") or {}), **(saved.get("change_requests") or {})}
    if not due or any((entries.get(c) or {}).get("status") != "passed" for c in due):
        return []
    return due


def criteria_only_later(state: Any, text: str) -> list[str]:
    """The criteria `text` names when every one of them is due in a later sprint, else [].

    A review finding that names only criteria a later sprint delivers is about
    that sprint's work, however it is worded. Matching its words against the
    later sprints' goals misses one that also mentions this sprint's work in
    passing; the ids it cites do not.
    """
    from app.acceptance.junit import tags_in

    named = [tag for tag in tags_in(str(text or "")) if tag.startswith("AC-")]
    if not named:
        return []
    due = criteria_due(state)
    if due is None:
        return []
    known = {c.id for c in suite.criteria(_root(state))}
    if any(tag in due or tag not in known for tag in named):
        return []
    return named


def sprint_already_done(state: Any) -> str:
    """Why this sprint has nothing left to build, or "".

    When every criterion due by a sprint already passes - an earlier sprint
    built more than its share - a team closes the sprint rather than invent
    work for it. Measured on one run with seven sprints: all nine criteria
    passed by the third, and each later sprint's lead was sent back for
    planning no work orders until it invented one ("noop_backend"), which was
    then built, reviewed, tested and accepted - four times over.

    Only at a sprint's first planning - never on a re-plan, a revision or a
    release retry, which each come back here with a reason to build - for a
    sprint that was given criteria of its own (or the last, which answers for
    all of them), with no change asked of it, and only on a run of the suite
    made now, not on a remembered one. The first version checked only for
    requested changes: one run's sprint 1, re-planned because its unit tests
    failed, came back with none and was accepted without its reviews.
    """
    root = _root(state)
    if not suite.is_locked(root):
        return ""
    if [c for c in state.get("revision_comments") or [] if str(c).strip()]:
        return ""
    if state.get("escalation") or state.get("work_order_problems"):
        return ""
    if any(int(state.get(key) or 0) for key in ("sprint_replan_count", "milestone_revision_count", "release_attempts")):
        return ""
    sprints = list(getattr(state.get("sprint_plan"), "sprints", None) or [])
    index = int(state.get("current_sprint_index") or 0)
    if any(
        isinstance(entry, dict) and entry.get("sprint_index") == index
        for entry in state.get("sprint_attempts") or []
    ):
        return ""
    if not sprints or index >= len(sprints):
        return ""
    own = list(getattr(sprints[index], "criteria", None) or [])
    if not own and index < len(sprints) - 1:
        return ""
    excused = suite.deferred(root)
    due = [c for c in (criteria_due(state) or []) if c not in excused]
    if not due:
        return ""
    result = suite.run(root)
    if not result.ran or result.runtime_problems:
        return ""
    passing = result.passing_ids()
    if any(criterion not in passing for criterion in due):
        return ""
    return (
        f"Every criterion due by sprint {index + 1} already passes ({', '.join(due)}), on a run of "
        "the acceptance suite made at the start of the sprint, so there is nothing left to build "
        "for it.\n" + result.summary(due)
    )


def interface_defects(state: Any) -> list[Any]:
    """Defects in how the page is presented that a script can prove, for its UI/UX owner.

    Only once the page renders something - before then there is nothing to
    style. See `app.analysis.interface_checks` for why these are checked at all.
    """
    from app.agents.specialists import ReportedDefect
    from app.analysis import interface_checks

    root = _root(state)
    saved = suite.last_result(root) or {}
    if not saved.get("ran") or not str(saved.get("shows") or "").strip():
        return []
    defects = []
    sheet = interface_checks.nobody_styled_it(root)
    if sheet:
        defects.append(ReportedDefect(
            description=(
                "The interface is not styled: the only stylesheet is the one the scaffold "
                "wrote, and nothing else styles the page."
            ),
            severity="major",
            reproduction_steps=(
                f"Read {sheet}: it resets box sizing, the font and the page width, and the "
                "page has no other stylesheet and no style block."
            ),
            expected_behavior=(
                "The page is styled to the interface design in the technical specification: "
                "its layout at a phone's width and a desktop's, each control's states, the "
                "feedback after each action, and its visual style."
            ),
            actual_behavior="The page shows the browser's own defaults.",
            affected_files=[sheet],
            owner="ui_ux",
            # The check itself is the test: it runs on every round.
            regression_test_required=False,
        ))
    broken = [rule for rule in saved.get("accessibility") or [] if isinstance(rule, dict) and rule.get("id")]
    if broken:
        listed = "; ".join(
            f"{rule.get('id')} ({rule.get('impact')}): {rule.get('help')} - {rule.get('count')} element(s)"
            + (f", e.g. {', '.join(rule.get('where') or [])}" if rule.get("where") else "")
            + "".join(
                f". {where}: {why}"
                for where, why in zip(rule.get("where") or [], rule.get("why") or [])
                if why
            )
            for rule in broken
        )
        defects.append(ReportedDefect(
            description=(
                f"An accessibility check of the page finds {len(broken)} serious or critical "
                "rule(s) broken: " + ", ".join(str(rule.get("id")) for rule in broken) + "."
            ),
            severity="major",
            reproduction_steps=(
                "Load the page and run axe-core on it, as the harness's page check does before "
                "every run of the acceptance suite; its report is in the suite's output."
            ),
            expected_behavior=(
                "Every control has a name a screen reader announces, text has enough contrast "
                "to read, and the page's structure is announced correctly."
            ),
            actual_behavior=listed[:1500],
            affected_files=[],
            owner="ui_ux",
            regression_test_required=False,
        ))
    brief = str(getattr(state.get("document"), "text", "") or "")
    disabled = interface_checks.named_controls_disabled_on_load(brief, str(saved.get("shows") or ""))
    if disabled:
        named = ", ".join(f'"{name}"' for name in disabled)
        defects.append(ReportedDefect(
            description=(
                f"A control the brief names is disabled when the page loads: {named}. A person "
                "cannot use it and is not told why."
            ),
            severity="major",
            reproduction_steps=(
                "Load the page and read what it shows: the harness's page check records each "
                "control with its state before any test touches it."
            ),
            expected_behavior=(
                "Every control the brief names can be used. An action that cannot go ahead - a "
                "required field left empty - is refused when it is tried, with a message saying "
                "what is missing."
            ),
            actual_behavior=f"{named} disabled on load, as the page shows it.",
            affected_files=[],
            owner="ui_ux",
            regression_test_required=False,
        ))
    overflow = int(saved.get("phone_overflow") or 0)
    if overflow > 0 and interface_checks.asks_for_small_screens(brief):
        defects.append(ReportedDefect(
            description=(
                f"At a phone's width (375px) the page is {overflow}px wider than the screen, "
                "so it scrolls sideways."
            ),
            severity="major",
            reproduction_steps=(
                "Load the page in a 375px-wide window and compare the document's scroll "
                "width with the window's width."
            ),
            expected_behavior="Everything fits a phone's width, as the brief asks.",
            actual_behavior=f"The document is {overflow}px wider than a 375px window.",
            affected_files=[],
            owner="ui_ux",
            # The check itself is the test: it runs on every round.
            regression_test_required=False,
        ))
    return defects


def failing_due_defects(state: Any, reported: list[Any]) -> list[Any]:
    """A defect for each due criterion that fails and that the round did not report.

    The round is handed the suite's result and asked to report every failing
    criterion with its owner; this is the backstop for one it leaves out, so a
    red criterion can never reach the milestone review unreported.
    """
    failing, command = _failing_due(state)
    if not failing:
        return []
    from app.acceptance.junit import tags_in
    from app.agents.specialists import ReportedDefect

    mentioned: set[str] = set()
    said = []
    for item in reported:
        text = " ".join(
            str(getattr(item, name, "") or "")
            for name in ("description", "reproduction_steps", "expected_behavior", "actual_behavior")
        )
        mentioned.update(tags_in(text))
        said.append(text)
    defects = []
    # First, and on its own: what the product reported itself while it loaded.
    # It is usually the one cause behind every red criterion, and a fix aimed
    # at any single criterion's "element not found" never finds it.
    saved = suite.last_result(_root(state)) or {}
    problems = [
        p for p in saved.get("runtime_problems") or []
        if not any(str(p)[:80] in text for text in said)
    ]
    # Each fix is handed one defect, so each carries what the product shows:
    # "element not found" cannot tell an absent control from a misnamed one.
    shown = str(saved.get("shows") or "")
    seen = f" What the product shows when it loads, before any test touches it:\n{shown[:600]}" if shown else ""
    never_started = str(saved.get("problem") or "")
    if never_started.startswith(suite.PRODUCT_DID_NOT_START):
        # One defect for the one cause: nothing could be measured while it stands.
        defects.append(ReportedDefect(
            description="The product does not start for the acceptance suite, so no test can reach it.",
            severity="blocking",
            reproduction_steps=f"Run `{command}` in the project directory: the product fails before any test runs.",
            expected_behavior="The product builds and starts, and the acceptance suite's tests run against it.",
            actual_behavior=never_started[:1500],
            affected_files=[],
            owner=_owner_for(state, never_started),
        ))
        return defects
    if problems:
        defects.append(ReportedDefect(
            description="The product reports errors by itself while it loads, before any test touches it.",
            severity="blocking",
            reproduction_steps=f"Run `{command}` in the project directory; its output lists them before the tests.",
            expected_behavior="The product loads without an uncaught error, a console error or a failed request.",
            actual_behavior="; ".join(str(p) for p in problems)[:1200],
            affected_files=[],
            # Errors the page reports while it loads are the page's.
            owner=_owner_for(state, "page.load: " + "; ".join(str(p) for p in problems)),
        ))
    for entry in failing:
        if entry.get("id") in mentioned:
            continue
        tests = entry.get("tests") or []
        failed = [t for t in tests if t.get("outcome") == "failed"] or tests
        detail = "; ".join(
            f"{t.get('name')}: " + (((t.get("message") or "").strip().splitlines() or ["failed"])[0][:300])
            for t in failed[:3]
        ) or "no test carrying this id ran"
        # What the page showed when the first of them failed: whether the
        # control is absent, misnamed, or never appeared after the action.
        met = next((suite.page_it_failed_on(t.get("message", "")) for t in failed if suite.page_it_failed_on(t.get("message", ""))), "")
        if met:
            detail += f"\nThe page when it failed:\n{met}"
        defects.append(ReportedDefect(
            description=f"[{entry.get('id')}] {entry.get('text')} - the acceptance suite says this does not work yet.",
            severity="major",
            reproduction_steps=f"Run `{command}` in the project directory and read the {entry.get('id')} tests.",
            expected_behavior=str(entry.get("text") or ""),
            actual_behavior=detail + seen,
            affected_files=[],
            owner=_owner_for(state, detail),
        ))
    return defects


def due_criteria_failing(state: Any) -> str:
    """What the milestone review must not accept: due criteria the suite says fail."""
    failing, command = _failing_due(state)
    if not failing:
        return ""
    lines = [
        f"- {entry.get('id')}: {entry.get('text')}"
        + "".join(
            f"\n    {t.get('name')}: {((t.get('message') or '').strip().splitlines() or ['failed'])[0][:200]}"
            for t in (entry.get("tests") or []) if t.get("outcome") == "failed"
        )
        for entry in failing
    ]
    return (
        f"The acceptance suite (`{command}`) says these criteria, due by the end of this "
        "sprint, do not work yet. The sprint is not done until they pass:\n" + "\n".join(lines)
    )


def acceptance_text_for(state: Any) -> str:
    """Run the suite now and describe it for a test round or a review; "" without a suite."""
    return acceptance_for_round(state)[0]


#: How often one run may reopen its locked suite to repair tests that can
#: never pass. Each is a recorded decision; more means the suite, not a test,
#: is the problem, and the escalation ladder decides.
MAX_SUITE_REPAIRS = 2

#: The most repairs in all, counting the ones a test never sent for repair
#: before earns past `MAX_SUITE_REPAIRS`. The budget is there to stop a QA
#: stage that cannot fix the same tests going round; it is not a reason to
#: build against a test nobody was ever asked to fix. Measured on one run: both
#: repairs went on tests a harness check had wrongly named (since fixed), and
#: when two login tests then called `.json()` on a plain object - a TypeError
#: no product can pass - the suite could not be reopened, and two fix stages in
#: turn answered "a bug in the locked test".
MAX_SUITE_REPAIRS_IN_ALL = 4


def _which_test(item: str) -> str:
    """The test a "cannot pass" finding is about: its first `quoted` name, else the finding."""
    found = re.search(r"`([^`]+)`", str(item))
    return (found.group(1) if found else str(item)).strip()[:300]


def may_repair(state: Any, broken: list[str]) -> bool:
    """Whether the suite may be reopened for `broken`: within the budget, or a test never sent before.

    Every caller asks this one question - the round, the dispute, the
    beyond-repair note - so they cannot disagree about whether a repair is due.
    """
    repairs = int(state.get("suite_repairs") or 0)
    if not broken:
        return repairs < MAX_SUITE_REPAIRS
    if repairs < MAX_SUITE_REPAIRS:
        return True
    sent = set(state.get("suite_repaired_tests") or [])
    fresh = {_which_test(item) for item in broken} - sent
    return bool(fresh) and repairs < MAX_SUITE_REPAIRS_IN_ALL

#: The most locked tests one run's disputes may reclassify when the suite is
#: small; a bigger suite gets a tenth of it. The cap exists to stop
#: reclassify-to-ship - seven of thirty-three audited runs were falsely
#: accepted, and this was the path the worst of them traveled - not to forbid
#: correcting a genuinely wrong test. See Initiative J.2 in
#: docs/improvement-plan.md.
MOST_RECLASSIFICATIONS = 2


def most_reclassifications(repo_root: Any) -> int:
    """The reclassification cap: two, or a tenth of a bigger locked suite."""
    try:
        locked = len({name for _, name in suite.declared_tests(repo_root)})
    except Exception:  # noqa: BLE001 - no suite to count; the floor stands
        locked = 0
    return max(MOST_RECLASSIFICATIONS, locked // 10)


def reclassification_room(state: Any) -> int:
    """How many more locked tests this run's disputes may reclassify."""
    done = len(set(state.get("suite_reclassified_tests") or []))
    return max(0, most_reclassifications(_root(state)) - done)


def within_the_cap(state: Any, names: list[str]) -> tuple[list[str], list[str]]:
    """(the disputed tests a reclassification may still cover, the ones past the cap).

    A test past the cap stays exactly as it is - failing where it fails - and
    the run carries it to its release rather than rewriting what it is checked
    against. The QA lead's own ordering decides which fit.
    """
    room = reclassification_room(state)
    return list(names[:room]), list(names[room:])


def tests_that_fail_alone(repo_root: Any, names: list[str]) -> tuple[list[str], list[str]]:
    """(the disputed tests that still fail when run alone, the ones that pass alone).

    The executable leg of a reclassification (Initiative J.2): before the
    suite is reopened for a test the QA lead calls unpassable, the harness
    runs each acceptance file alone against the delivered surface, in the
    project's own runner, with no model in the loop. A named test whose file
    passes alone is not unpassable - the suite run failed it for order or
    shared state - and it stays locked. A test that cannot be re-measured (no
    runner, no file, no criterion tag) is left on the failing list: unknown is
    not passed.
    """
    from app.acceptance import junit
    from app.acceptance.per_file import each_file
    from app.stacks.scaffold import sandbox_runner

    if not names:
        return [], []
    try:
        tagged: dict[str, set[str]] = {}
        for shown, declared in suite.declared_tests(repo_root):
            for tag in junit.tags_in(declared):
                tagged.setdefault(tag, set()).add(shown)
        runs = each_file(repo_root, contract.read(repo_root) or {}, sandbox_runner(repo_root))
        outcome = {str(run.get("file")): str(run.get("outcome")) for run in runs}
    except Exception:  # noqa: BLE001 - a check that cannot run re-measures nothing
        logger.warning("Could not re-measure the disputed tests file by file", exc_info=True)
        return list(names), []
    if not outcome or not tagged:
        return list(names), []
    still: list[str] = []
    passed: list[str] = []
    for name in names:
        files: set[str] = set()
        for tag in junit.tags_in(name):
            files |= tagged.get(tag, set())
        results = [outcome.get(shown) for shown in files]
        if results and all(result == "finished" for result in results):
            passed.append(name)
        else:
            still.append(name)
    return still, passed


#: What QA is held to when it repairs a locked suite.
REPAIR_RULE = (
    "Change only the tests named above, and only as far as their own code is wrong. "
    "Every other test, and what each test checks, stays exactly as it is: the suite is "
    "being repaired, not rewritten."
)


def acceptance_for_round(state: Any) -> tuple[str, list[str]]:
    """Run the suite now: its description for a test round, and the tests that cannot pass.

    "Cannot pass" is decided the way the review that locked the suite decides
    it - an error the test's own code throws, or an assertion its runner does
    not define - but on a product that now exists, which reaches lines the
    run before anything was built never did; and, once the product shows it,
    a test waiting for something only data brings, having created none.
    """
    result, due = run_for_sprint(state)
    if result is None:
        return "", []
    root = _root(state)
    broken = [
        *suite.tests_that_broke_themselves(root, result),
        *suite.tests_left_behind_by_their_own_change(root, result),
        *suite.vacuous_green(root, result),
        *suite.assertions_that_do_not_exist(root),
        *suite.locators_that_do_not_exist(root),
        *suite.locators_by_a_name_the_role_never_has(root),
        *suite.locators_with_invalid_name_option(root),
        *suite.tests_that_never_open_the_page(root),
        *suite.tests_that_access_storage_before_opening_the_page(root),
        *suite.tests_that_expect_what_they_never_gave(root),
        *suite.tests_that_need_what_they_never_made(root, result),
    ]
    return acceptance_requests.acceptance_block(result, due), broken


#: Where a suite repaired for a failed attempt's dispute goes back to: the
#: sprint's planning, with no change request to brief it on.
SPRINT_REPLAN = "sprint_replan"


def reopen_the_suite_for(
    state: Any, broken: list[str], return_to: str = "test_and_triage", *, reclassifying: bool = False
) -> dict[str, Any] | None:
    """Send tests that can never pass back to QA, then back to `return_to`; None when spent.

    `reclassifying` marks the reopen a dispute's - a judgement about what the
    product is checked against, counted against the run's reclassification cap
    and named in its release gaps - rather than a repair the harness's own
    checks sent for (Initiative J.2).
    """
    from app.acceptance.junit import tags_in
    from app.graph.workflow import _handing_on

    repairs = int(state.get("suite_repairs") or 0)
    if not broken or not may_repair(state, broken):
        return None
    update: dict[str, Any] = {}
    _decide(
        state, update, point="acceptance_tests",
        question="The locked suite has tests that cannot pass whatever is built: how does the run go on?",
        options=["QA repairs those tests and the suite is reviewed and locked again", "build against it as it is"],
        decision="QA repairs those tests and the suite is reviewed and locked again",
        rationale="; ".join(broken),
        affects=sorted({tag for item in broken for tag in tags_in(item) if tag.startswith("AC-")}),
    )
    logger.warning("Reopening the locked suite: %d test(s) cannot pass", len(broken))
    reclassified = (
        {"suite_reclassified_tests": sorted({
            *(state.get("suite_reclassified_tests") or []), *map(_which_test, broken),
        })}
        if reclassifying
        else {}
    )
    return _handing_on(
        **update,
        **reclassified,
        stage="acceptance_author",
        acceptance_return_to=return_to,
        acceptance_round=0,
        acceptance_feedback=[*broken, REPAIR_RULE],
        suite_repairs=repairs + 1,
        suite_repaired_tests=sorted({*(state.get("suite_repaired_tests") or []), *map(_which_test, broken)}),
    )


def beyond_repair(state: Any, broken: list[str]) -> list[str]:
    """The criteria of locked tests that cannot pass, once the suite may not be repaired again; else [].

    Measured on one run: with its two repairs spent, the round's check named
    the locked test that looked for a value it never entered - and the list
    went nowhere. The test engineer found the same fault by reading the
    evidence, reported it as a defect, and two fix stages in turn answered
    "a test bug; this stage cannot change the locked suite".
    """
    from app.acceptance.junit import tags_in

    if not broken or may_repair(state, broken):
        return []
    return sorted({tag for item in broken for tag in tags_in(item) if tag.startswith("AC-")})


def beyond_repair_note(broken: list[str], criteria: list[str]) -> str:
    """What a test round is told about the locked tests `beyond_repair` names."""
    return (
        f"Locked tests that cannot pass whatever is built ({', '.join(criteria)}). The suite may not be "
        "repaired again in this run, so their failures are not defects in the product and no fix "
        "stage can close them: a defect that names only these criteria is set aside.\n"
        + "\n".join(f"- {item}" for item in broken)
    )


# --- decision records ------------------------------------------------------------

def _decide(state: Any, update: dict[str, Any], **record: Any) -> None:
    """Add a decision record to `update` (see `app.decisions`); never raises."""
    try:
        from app.decisions import record_decision

        record_decision(state, update, **record)
    except Exception:  # noqa: BLE001 - a record is evidence, not control flow
        logger.debug("Could not record a decision", exc_info=True)
