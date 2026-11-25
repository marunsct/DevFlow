"""The reviews of a finished sprint, and the QA lead's ruling on locked tests it still fails.

    security_review -> advice_review -> milestone_review
        (or, in parallel mode, review_worker x N -> review_gather -> milestone_review)
    acceptance_dispute: called from a test round or a re-plan

See `app.graph.nodes` for how these are registered and why their helpers are
imported from `app.graph.workflow` when they run.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.graph import acceptance_nodes
from app.graph.context import GraphContext
from app.graph.workflow import WorkflowGraphState

#: The workflow's logger: the nodes log as they did inside the builder.
logger = logging.getLogger("app.graph.workflow")


def _the_security_review(state: Any, config: RunnableConfig, ctx: GraphContext) -> tuple[dict[str, Any] | None, Any]:
    """(an update to hand back - paused or retrying - and None), or (None, the review)."""
    from app.graph.workflow import (
        SecurityReviewOutput, _changes_any_code, _record_document, _run_gated_agent,
        _the_files_this_milestone_changed, _without_findings_about_the_harness_s_files,
        build_security_review_request, create_security_reviewer_agent, render_security_review,
        with_the_facts,
    )

    outputs = state.get("specialist_outputs", {})
    changed_files = _the_files_this_milestone_changed(state, outputs)
    if not _changes_any_code(changed_files) and not state.get("pending_inner_thread_id"):
        return None, SecurityReviewOutput(status="passed", findings=[])
    agent = create_security_reviewer_agent(model=ctx.judgement_model, checkpointer=ctx.checkpointer, repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories)
    from app.agents import review_files

    root = state["repository"].root_path
    permissions = ("Permissions: All tools have read/write access to the repository scope. Validation tools are "
                   "restricted to a safe list of commands.")
    # The facts the work is built and judged under (plan CM.1).
    request = with_the_facts(build_security_review_request(changed_files, permissions, root, held=()), root)
    # The files under review held in its memory when today's request and memory do not show them all (LF.1284).
    from app.agents.security_reviewer import source_coverage

    held = review_files.held_for_review(review_files.under_review(root, changed_files), root, ctx.judgement_model,
                                        "security_review", review_files.opening_of(request),
                                        told_to_open=source_coverage(changed_files, root)[1]) or []
    if held:
        request = with_the_facts(build_security_review_request(changed_files, permissions, root, held=held), root)
    # The framework's own security guidance for the release this project uses (plan HK.9).
    from app.stacks import framework_guidance

    request = framework_guidance.for_the_security_review(
        request, getattr(state.get("stack_selection"), "technology_stack", None), root)
    update = _run_gated_agent(
        state,
        config,
        stage_name="security_review",
        agent=agent,
        initial_request=request,
        output_key="__security_review__",
        next_stage="security_review", # We re-enter to process the output
    )
    if "__security_review__" not in update:
        return update, None

    review: SecurityReviewOutput = update.pop("__security_review__")
    review = _without_findings_about_the_harness_s_files(review, state["repository"].root_path)

    # Rendered from the decision, like the architecture and milestone
    # reviews. This was the last reviewer still holding a write tool with
    # no document of its own to render - the same latent shape that ended
    # one run at stage three when the stack selector finally used it.
    # It had never misbehaved; neither had the stack selector, until it did.
    shown, not_shown = source_coverage(changed_files, state["repository"].root_path, held)
    _record_document(
        state,
        "docs/security_review.md",
        render_security_review(review, shown, not_shown),
    )
    return None, review


def security_review_node(state: WorkflowGraphState, config: RunnableConfig, ctx: GraphContext) -> dict[str, Any]:
    from app.graph.workflow import _handing_on, _in_parallel_mode, max_parallel

    if state.get("reviews_in_flight"):
        # A resume after a review in the fan-out paused or retried.
        return {"stage": "review_parallel"}
    if _in_parallel_mode() and max_parallel() > 1 and not state.get("pending_inner_thread_id"):
        due = ["security", *_advice_reviews_due(state)]
        if len(due) > 1:
            # Each review reads the finished sprint and none reads another's
            # verdict, so they run side by side; the milestone review, which
            # reads them all, waits for `review_gather`.
            logger.info("Running %d reviews side by side: %s", len(due), ", ".join(due))
            return {"stage": "review_parallel", "reviews_in_flight": due, "review_results": {}}
    handed_back, review = _the_security_review(state, config, ctx)
    if handed_back is not None:
        return handed_back
    from app.sprint.record import findings_of

    return _handing_on(
        stage="advice_review",
        security_review=review,
        sprint_findings=list(state.get("sprint_findings") or [])
        + findings_of(review, "security", state.get("milestone_revision_count", 0) + 1),
    )


def _advice_reviews_due(state: Any) -> list[str]:
    """The consulted specialists whose advice review this sprint and revision has not had.

    Only a role with an item due by now (`_the_items_due`): one whose items the sprint plan places in later sprints
    has nothing to check yet.
    """
    from app.agents.advice_review import roles_to_review

    cycle = f"{state.get('current_sprint_index', 0)}:{state.get('milestone_revision_count', 0)}"
    found = dict(state.get("advice_findings") or {}) if state.get("advice_review_cycle") == cycle else {}
    advice, specification = state.get("specialist_advice"), state.get("technical_specification")
    return [
        role for role in roles_to_review(advice, specification)
        if role not in found and _the_items_due(state, role)[0]
    ]


def _the_items_due(state: Any, role: str) -> tuple[list[str], str]:
    """One role's adopted items due by the end of this sprint, and why. See `advice_review.items_due` (SP.2)."""
    from app.agents.advice_review import items_due

    return items_due(
        state.get("specialist_advice"), state.get("technical_specification"), role, state.get("sprint_plan"),
        int(state.get("current_sprint_index") or 0), declined=dict(state.get("advice_declined") or {}),
    )


def _one_advice_review(state: Any, config: RunnableConfig, role: str, ctx: GraphContext) -> tuple[dict[str, Any] | None, list[Any]]:
    """(an update to hand back, []) or (None, the role's findings)."""
    from app.graph.workflow import (
        _changes_any_code, _fixes_a_review_must_not_undo, _hand_back, _run_gated_agent,
        _the_files_this_milestone_changed, _this_sprint_s_scope_for_review, create_advice_reviewer_agent,
        with_the_facts,
    )

    from app.agents.advice_review import build_advice_review_request, findings_from

    specification = state.get("technical_specification")
    due, due_because = _the_items_due(state, role)
    changed_files = _the_files_this_milestone_changed(state, state.get("specialist_outputs", {}))
    if role == "database" and not state.get("pending_inner_thread_id") and not _changes_any_code(changed_files):
        return None, []
    milestone = state.get("milestone_plan")
    root = state["repository"].root_path

    def built(held: list[str]) -> dict[str, Any]:
        request = build_advice_review_request(
            role,
            due,
            str(getattr(milestone, "selected_sprint_goal", "") or ""),
            _this_sprint_s_scope_for_review(state),
            changed_files,
            held=held,
            due_because=due_because,
        )
        # The facts the work is built and judged under (plan CM.1).
        request = with_the_facts(request, root)
        request["messages"][-1]["content"] += _fixes_a_review_must_not_undo(state)
        # Its own domain in the changed files too, behind `SPECIALIST_DOMAIN_REVIEW` (plan SP.3).
        from app.agents.specialist_domain_review import with_the_domain_review

        return with_the_domain_review(request, role, specification)

    from app.agents import review_files

    request = built([])
    # The changed files held in its memory when today's memory does not hold them all (LF.1284).
    held = review_files.held_for_review(review_files.under_review(root, changed_files), root, ctx.judgement_model,
                                        f"advice_review_{role}", review_files.opening_of(request))
    if held:
        request = built(held)
    if role == "ui_ux":
        # The design QA loop: the page as a person sees it, for a model that can see.
        from app.models.vision import the_reviewer_reads_images

        if the_reviewer_reads_images():
            from app.agents.page_screenshots import with_the_page_screenshots

            request = with_the_page_screenshots(
                request,
                state["repository"].root_path,
                getattr(specification, "interface_design", None) or [],
            )
        else:
            # A reviewer that cannot see is given the page as measured facts (plan SP.4).
            from app.agents.page_facts import with_the_page_facts

            request = with_the_page_facts(request, root, getattr(specification, "interface_design", None) or [])
    agent = create_advice_reviewer_agent(
        role, model=ctx.judgement_model, checkpointer=ctx.checkpointer,
        repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories,
    )
    update = _run_gated_agent(
        state,
        config,
        stage_name=f"advice_review_{role}",
        agent=agent,
        initial_request=request,
        output_key="__advice_review__",
        next_stage="advice_review",
    )
    if _hand_back(update, "__advice_review__"):
        return update, []
    found = findings_from(role, update.pop("__advice_review__"), [line.split(":", 1)[0] for line in due])
    if found:
        logger.info("The %s specialist found %d adopted item(s) not built", role, len(found))
    return None, found


def advice_review_node(state: WorkflowGraphState, config: RunnableConfig, ctx: GraphContext) -> dict[str, Any]:
    """Each consulted specialist checks its adopted advice against this sprint. See `app.agents.advice_review`."""
    from app.graph.workflow import _handing_on

    if state.get("reviews_in_flight"):
        return {"stage": "review_parallel"}
    # One review per sprint and per milestone revision: a revised sprint is
    # checked again, from nothing.
    cycle = f"{state.get('current_sprint_index', 0)}:{state.get('milestone_revision_count', 0)}"
    found = dict(state.get("advice_findings") or {}) if state.get("advice_review_cycle") == cycle else {}
    pending = _advice_reviews_due(state)
    if not pending:
        return _handing_on(stage="milestone_review", advice_findings=found, advice_review_cycle=cycle)
    role = pending[0]
    handed_back, findings = _one_advice_review(state, config, role, ctx)
    if handed_back is not None:
        return handed_back
    found[role] = findings
    from app.agents.specialist_domain_review import sprint_findings

    return _handing_on(**{
        "advice_findings": found,
        "advice_review_cycle": cycle,
        "sprint_findings": list(state.get("sprint_findings") or [])
        + sprint_findings(found[role], state.get("milestone_revision_count", 0) + 1),
        "stage": "advice_review" if len(pending) > 1 else "milestone_review",
    })


def review_worker_node(state: dict, config: RunnableConfig, ctx: GraphContext) -> dict[str, Any]:
    """One review of the finished sprint, beside the others. See `security_review_node`."""
    from app.graph.workflow import _as_a_queued_pause, _only_this_worker_s_pause

    item = state["__review_item"]
    stage_name = "security_review" if item == "security" else f"advice_review_{item}"
    temp_state: Any = dict(state)
    # A worker may only answer its own approval gate: see `specialist_worker_node`.
    temp_state.update(_only_this_worker_s_pause(state, stage_name))
    if item == "security":
        handed_back, review = _the_security_review(temp_state, config, ctx)
        result: dict[str, Any] = {"security_review": review}
    else:
        handed_back, findings = _one_advice_review(temp_state, config, item, ctx)
        result = {"advice": findings}
    answered_in_a_batch = bool((state.get("queued_decisions") or {}).get(stage_name))
    if handed_back is not None:
        return {"specialist_pauses": {stage_name: _as_a_queued_pause(
            state, stage_name, handed_back, answered=answered_in_a_batch
        )}}
    finished: dict[str, Any] = {"review_results": {item: result}}
    if answered_in_a_batch:
        finished["specialist_pauses"] = {stage_name: None}
    return finished


def review_gather_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:  # noqa: ARG001
    """Where the reviews join: surface a pause, send what is left, or record them all for the milestone review."""
    from app.graph.workflow import (
        _QUEUED_AT, _handing_on, _queued_pauses, _reviews_pending, _the_pause_to_surface,
    )

    pauses = _queued_pauses(state)
    if pauses:
        first = _the_pause_to_surface(pauses)
        surfaced = {key: value for key, value in pauses[first].items() if key != _QUEUED_AT}
        return {**surfaced, "specialist_pauses": {first: None}, "queued_decisions": {}}
    if _reviews_pending(state):
        return {
            "stage": "review_parallel",
            "pending_decision": None,
            "pending_inner_thread_id": None,
            "pending_approval": None,
            "queued_decisions": {},
        }
    from app.agents.specialist_domain_review import sprint_findings
    from app.sprint.record import findings_of

    results = state.get("review_results") or {}
    revision = state.get("milestone_revision_count", 0) + 1
    findings = list(state.get("sprint_findings") or [])
    review = (results.get("security") or {}).get("security_review")
    if review is not None:
        findings += findings_of(review, "security", revision)
    cycle = f"{state.get('current_sprint_index', 0)}:{state.get('milestone_revision_count', 0)}"
    found = dict(state.get("advice_findings") or {}) if state.get("advice_review_cycle") == cycle else {}
    for item in state.get("reviews_in_flight") or []:
        if item != "security":
            found[item] = list((results.get(item) or {}).get("advice") or [])
            findings += sprint_findings(found[item], revision)
    return _handing_on(
        stage="milestone_review",
        security_review=review if review is not None else state.get("security_review"),
        advice_findings=found,
        advice_review_cycle=cycle,
        sprint_findings=findings,
        reviews_in_flight=[],
        review_results={},
    )


def acceptance_dispute_node(state: WorkflowGraphState, config: RunnableConfig, ctx: GraphContext) -> dict[str, Any]:
    """The QA lead judges a failed attempt's locked tests. See `app.agents.suite_dispute`."""
    from app.graph.workflow import (
        _hand_back, _handing_on, _run_gated_agent, _the_locked_tests_still_failing, _this_attempt,
        _with_the_api, _with_the_reason, create_suite_dispute_agent, criteria_past_the_cap,
        past_the_cap_with_their_criteria, with_the_facts,
    )

    from pathlib import Path

    from app.acceptance import suite as acceptance_suite
    from app.acceptance.requests import shares_one_service
    from app.agents.suite_dispute import build_dispute_request, tests_it_names
    from app.graph.acceptance_nodes import SPRINT_REPLAN, reopen_the_suite_for

    # Held mid-attempt, it goes back to the attempt: a repaired suite to the
    # round, and nothing to repair to the remediation it interrupted.
    returns_to = state.get("dispute_returns_to")
    # Keyed by the attempt it judges: the one running, or at a re-plan the one that just failed.
    disputed = sorted({*map(str, state.get("disputed_sprints") or []),
                       _this_attempt(state, judging_the_last=not returns_to)})
    carry_on = "defect_remediation" if returns_to else "technical_lead"
    failing = _the_locked_tests_still_failing(state)
    if not failing:
        return _handing_on(stage=carry_on, disputed_sprints=disputed, dispute_returns_to=None, dispute_reason=None)
    root = state["repository"].root_path
    code = "\n\n".join(
        f"--- {path.relative_to(Path(root)).as_posix()} ---\n{path.read_text(encoding='utf-8', errors='replace')}"
        for path in acceptance_suite.suite_files(root)
    )[:16000]
    # What the runner's own matching rules out in a failing test's code: told to the judge, and never kept as sound.
    shown_by_the_code = acceptance_suite.what_the_code_shows_of(root, [name for name, _, _ in failing])
    # What may explain a failing test's failure without ruling the test out: weighed by the judge, never reopened alone.
    suggested_by_the_code = acceptance_suite.what_the_code_suggests_of(root, [name for name, _, _ in failing])
    agent = create_suite_dispute_agent(
        model=ctx.judgement_model, checkpointer=ctx.checkpointer,
        repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories,
    )
    update = _run_gated_agent(
        state,
        config,
        stage_name="acceptance_dispute",
        agent=agent,
        # The facts the work is built and judged under (plan CM.1).
        initial_request=with_the_facts(_with_the_api(_with_the_reason(
            build_dispute_request(failing, code, getattr(state.get("document"), "text", "") or "",
                                  measured=acceptance_suite.the_suite_s_own_words_when_last_measured(root),
                                  shared_service=shares_one_service(root),
                                  found_in_the_code=list(dict.fromkeys(finding for _, finding in shown_by_the_code)),
                                  suggested_by_the_code=list(dict.fromkeys(item for _, item in suggested_by_the_code))),
            str(state.get("dispute_reason") or ""),
        ), state), state["repository"].root_path),
        output_key="__suite_dispute__",
        next_stage="acceptance_dispute",
    )
    if _hand_back(update, "__suite_dispute__"):
        return update
    from app.agents.specification_rulings import _the_specification

    standard = "\n".join((
        getattr(state.get("document"), "text", "") or "",
        _the_specification(state.get("technical_specification"), root),
        *(criterion for _, criterion, _ in failing),
    ))
    refused: list[tuple[str, str]] = []
    answer = update.pop("__suite_dispute__")
    named = tests_it_names(
        answer, [name for name, _, _ in failing], standard=standard, refused=refused,
        criteria_of={name: criterion for name, criterion, _ in failing},
    )
    called_wrong = list(named)
    # A test the harness read cannot pass is named even when the judge kept it.
    for name, finding in shown_by_the_code:
        if not any(f"`{name}`" in item for item in named):
            logger.warning("The dispute kept `%s`, which its own code shows cannot pass; it is reopened", name)
            named.append(f"`{name}` cannot pass for any product that does what its criterion says: {finding} "
                         "Fix the test so that it checks what the criterion says.")
    passed_alone: list[str] = []
    # The executable leg before a reclassification (Initiative J.2): each
    # named test is run alone against the delivered surface in the
    # project's own runner. One that passes alone is not unpassable - the
    # suite run failed it for order or shared state - and stays locked.
    if named and not state.get("pending_inner_thread_id"):
        named, passed_alone = acceptance_nodes.tests_that_fail_alone(root, named)
        if passed_alone:
            logger.warning(
                "Disputed test(s) %s pass when run alone; they stay locked",
                ", ".join(passed_alone),
            )
    named, service_stopped = acceptance_nodes.tests_whose_service_stayed_up(root, named)
    if service_stopped:
        logger.warning(
            "Disputed test(s) %s saw their service stop by itself; they stay locked",
            ", ".join(service_stopped),
        )
    # And the cap: this run may reclassify this many locked tests, period.
    # Past it the tests stay as they are and the run carries them to its
    # release rather than rewriting what it is checked against.
    # One cause, one place under the cap: rulings that blame one helper of the suite are grouped.
    from app.graph import contested_tests

    contesting = contested_tests.enabled()
    repairs = contested_tests.proposed_repairs(answer) if contesting else []
    groups = acceptance_nodes.by_shared_cause(named, code)
    if contesting:
        # And rulings quoting the same code at fault, written inline in several tests (CONTESTED_TESTS_CONFIRMED).
        groups = contested_tests.by_shared_expression(groups, repairs, root)
    named, past_the_cap, causes = acceptance_nodes.within_the_cap_by_cause(state, groups)
    # Past the cap, a ruling the harness confirms by running the repair it quotes still goes to QA's repair.
    confirmed: list[str] = []
    if past_the_cap and contesting and repairs and not state.get("pending_inner_thread_id"):
        confirmed, past_the_cap, confirmed_causes, _ = contested_tests.confirmed_past_the_cap(
            root, groups, past_the_cap, repairs)
        named = [*named, *confirmed]
        causes += confirmed_causes
    if past_the_cap:
        logger.warning(
            "Disputed test(s) %s are past this run's reclassification cap; they stay as they are",
            ", ".join(past_the_cap),
        )
        # Carried to the release as the cap means, not re-planned against: measured on one run, the same two
        # tests the dispute called wrong (a character count off by one) failed every sprint after the cap, and the
        # sprint was planned again for hours on a product that counted right. Their criteria are deferred with why,
        # as a locked test beyond repair is, so the rounds stop raising them and the release names them.
        beyond = criteria_past_the_cap(failing, past_the_cap)
        if beyond:
            acceptance_nodes.defer_what_is_beyond_repair(state, beyond, [
                f"{line}: the dispute judged it wrong, and this run may reclassify no more tests"
                for line in past_the_cap_with_their_criteria(failing, past_the_cap)])
    missing = [
        f"`{name}` is missing from the locked suite; no test checks what the criterion says. Add a test for `{name.split()[0]}` or tag an existing test that proves it."
        for name, _, _ in failing
        if "missing from locked suite" in name
    ]
    to_repair = [*named, *missing]
    update.pop("stage", None)

    def _the_outcome(reopened: bool) -> None:
        # One decision per dispute with every way it ended (harness review HR2.Q.4): until now each was a warning.
        from app.decisions import record_decision
        from app.graph import dispute_outcomes

        record = dispute_outcomes.outcome(
            shown=[name for name, _, _ in failing], called_wrong=called_wrong, refused=refused,
            passed_alone=passed_alone, service_stopped=service_stopped, past_the_cap=past_the_cap,
            missing=missing, reopened=reopened, confirmed=confirmed,
        )
        dispute_outcomes.write(root, record, sprint=_this_attempt(state))
        record_decision(
            state, update, point="acceptance_dispute",
            question="Can the locked tests the attempt still fails pass for a product that meets its criteria?",
            decision=dispute_outcomes.summary(record),
            rationale=json.dumps(record)[:4000],
        )

    if to_repair:
        logger.warning("The QA lead / harness identifies %d locked test(s)/missing criteria cannot pass; reopening the suite", len(to_repair))
        reopened = reopen_the_suite_for(
            state, to_repair, return_to=returns_to or SPRINT_REPLAN, reclassifying=True, model=ctx.judgement_model,
            causes=causes + len(missing),
        )
        if reopened is not None:
            _the_outcome(True)
            return _handing_on(**{**update, **reopened, "disputed_sprints": disputed, "dispute_returns_to": None, "dispute_reason": None})
    if confirmed:
        # Confirmed, but the suite may not be repaired again: carried to the release as contested tests, with why,
        # rather than planned against again.
        beyond = criteria_past_the_cap(failing, confirmed)
        if beyond:
            acceptance_nodes.defer_what_is_beyond_repair(state, beyond, [
                f"{line}: the harness confirmed the dispute's ruling, and the suite may not be repaired again"
                for line in past_the_cap_with_their_criteria(failing, confirmed)])
    _the_outcome(False)
    return _handing_on(**update, stage=carry_on, disputed_sprints=disputed, dispute_returns_to=None, dispute_reason=None)
