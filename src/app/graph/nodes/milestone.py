"""The milestone review: whether the sprint is accepted, sent back or escalated.

    security_review / advice_review / review_gather -> milestone_review
        -> user_review_sprint, sprint_advance, release, technical_lead or escalation

See `app.graph.nodes` for how these are registered and why their helpers are
imported from `app.graph.workflow` when they run.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.graph.context import GraphContext
from app.graph.workflow import WorkflowGraphState

#: The workflow's logger: the nodes log as they did inside the builder.
logger = logging.getLogger("app.graph.workflow")


def milestone_review_node(state: WorkflowGraphState, config: RunnableConfig, ctx: GraphContext) -> dict[str, Any]:
    """Review the milestone, and keep its findings for the Sprint Record.

    Every exit that produced a verdict carries it as `milestone_review`; its
    findings join the sprint's history here, once, not at each exit.
    """
    from app.graph.workflow import _missing_upstream

    missing = _missing_upstream(state, "milestone_plan")
    if missing is not None:
        return missing
    result = _review_the_milestone(state, config, ctx)
    review = result.get("milestone_review") if isinstance(result, dict) else None
    if review is not None and review is not state.get("milestone_review"):
        from app.sprint.record import findings_of

        result["sprint_findings"] = list(state.get("sprint_findings") or []) + findings_of(
            review, "milestone", state.get("milestone_revision_count", 0) + 1
        )
    return result


def _review_the_milestone(state: WorkflowGraphState, config: RunnableConfig, ctx: GraphContext) -> dict[str, Any]:
    from app.graph.workflow import (
        FAST_MILESTONE_REVISIONS, MAX_MILESTONE_REVISIONS, MILESTONE_REVIEW_NEXT_STAGE, RECORDED_AS_RISKS,
        SPRINT_REVIEW, _GATING_SEVERITIES, _a_brief_requirement_the_run_never_built,
        _a_pass_over_its_own_findings, _a_red_suite_the_review_called_green,
        _accepted_when_nothing_in_it_gates, _as_text, _escalate_to_a_human, _fast_delivery,
        _findings_a_later_sprint_builds, _findings_about_a_server_only_the_tests_start,
        _findings_about_the_harness_s_files_made_minor, _findings_about_the_locked_suite_made_minor,
        _findings_no_measure_holds, _findings_the_command_record_contradicts,
        _findings_the_dependency_check_contradicts, _fixes_a_review_must_not_undo, _handing_on,
        _max_structured_retries, _milestone_changes_requested, _milestone_findings_that_block,
        _missing_upstream, _record_review_document, _record_sprint_summary, _review_enabled,
        _run_gated_agent, _security_graded_by_its_own_review, _the_code_review_s_advice,
        _the_files_this_milestone_changed, _this_review_s_advice_findings, _this_sprint_s_scope_for_review,
        _with_the_api, build_defect_report, build_milestone_review_request,
        create_milestone_reviewer_agent, findings_for_what_the_checks_proved, with_the_facts,
    )

    missing = _missing_upstream(state, "milestone_plan")
    if missing is not None:
        return missing
    milestone = state["milestone_plan"]
    outputs = state.get("specialist_outputs", {})
    changed_files = _the_files_this_milestone_changed(state, outputs)
    test_evidence = "\n".join(test for output in outputs.values() for test in output.tests) or "(none recorded)"
    cycle = state.get("remediation")
    defect_report = build_defect_report(cycle) if cycle else "No remediation cycle data."

    # Include security findings in the defect report if any exist
    sec_review = state.get("security_review")
    if sec_review and sec_review.status == "findings":
        defect_report += "\n\n--- Security Findings ---\n"
        for f in sec_review.findings:
            defect_report += f"[{f.severity}] {f.category}: {f.description}\nRemediation: {f.remediation}\n\n"

    # The measured suite, run on the review's first entry only: a resume
    # after an approval pause is the same review of the same code.
    from app.graph import acceptance_nodes

    acceptance_text = (
        acceptance_nodes.acceptance_text_for(state)
        if not state.get("pending_inner_thread_id")
        else ""
    )
    agent = create_milestone_reviewer_agent(model=ctx.judgement_model, checkpointer=ctx.checkpointer, repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories)
    request = build_milestone_review_request(
        milestone.selected_sprint_goal,
        changed_files,
        test_evidence,
        defect_report,
        state["repository"].root_path,
        getattr(state.get("stack_selection"), "technology_stack", None),
        getattr(state.get("document"), "text", "") or "",
        # The blockers, risks and decisions the specialists recorded. They
        # were written into state and read by nothing - see
        # `what_the_specialists_reported`.
        outputs,
        # And what this reviewer itself said last round. Without it every
        # review is a fresh opinion of the same code, and two runs died at
        # the revision limit chasing one - see `what_you_said_last_time`.
        # Only on a re-review of the same milestone. `sprint_advance_node`
        # resets `milestone_revision_count` but leaves `milestone_review`
        # in state, so on the first review of a new sprint that field
        # still holds the last sprint's verdict - and handing a reviewer
        # another milestone's findings as "what you found last time" is
        # worse than handing it nothing.
        previous_review=(
            state.get("milestone_review")
            if state.get("milestone_revision_count", 0)
            else None
        ),
        revisions_used=state.get("milestone_revision_count", 0),
        revisions_allowed=FAST_MILESTONE_REVISIONS if _fast_delivery() else MAX_MILESTONE_REVISIONS,
        sprint_scope=_this_sprint_s_scope_for_review(state),
        acceptance=acceptance_text,
        specialist_findings=_this_review_s_advice_findings(state),
    )
    # The facts the work is built and judged under (plan CM.1).
    request = with_the_facts(request, state["repository"].root_path)
    # And what the design review approved the specification on, as the builders were told (LF.1512).
    from app.agents.design_review_conditions import with_the_conditions

    request = with_the_conditions(request, state)
    request["messages"][-1]["content"] += _fixes_a_review_must_not_undo(state)
    request["messages"][-1]["content"] += _the_code_review_s_advice(state)
    # The contract the code is held to, whole: a service that drifted from
    # it (`username` where the specification said `full_name`) is the
    # review's to catch, and it saw only the specification's headings.
    _with_the_api(request, state)
    # The changed files held in its memory when today's request and memory do not show them all (LF.1284).
    from app.agents import review_files

    review_files.with_the_files_held(request, review_files.held_for_review(
        review_files.under_review(state["repository"].root_path, changed_files), state["repository"].root_path,
        ctx.judgement_model, "milestone_review", review_files.opening_of(request)))
    # The page as a person sees it, for a reviewer whose model can see. See
    # `app.agents.page_screenshots`; a model that cannot is not sent them.
    from app.models.vision import the_reviewer_reads_images

    if the_reviewer_reads_images():
        from app.agents.page_screenshots import with_the_page_screenshots

        request = with_the_page_screenshots(
            request,
            state["repository"].root_path,
            getattr(state.get("technical_specification"), "interface_design", None) or [],
        )
    update = _run_gated_agent(
        state,
        config,
        stage_name="milestone_review",
        agent=agent,
        initial_request=request,
        output_key="__milestone_review__",
        next_stage="milestone_review", # We re-enter to process the output
    )
    if "__milestone_review__" not in update:
        return update

    # Each filter in turn, and what it dropped or moved recorded under its name (harness review HR2.G.1): until
    # now they only logged, and 6 of 21 send-backs over 40 runs were relabelled accepted with no record.
    from app.acceptance.check_findings import filtered as _what_it_filtered

    root = state["repository"].root_path
    review_round = int(state.get("milestone_revision_count", 0) or 0) + 1

    def _through(name: str, before: Any, after: Any) -> Any:
        return _what_it_filtered(root, review_round, f"milestone:{name}", before, after)

    review = update.pop("__milestone_review__")
    review = _through("a_later_sprint_builds", review, _findings_a_later_sprint_builds(review, state))
    review = _through("security_graded_by_its_own_review", review,
                      _security_graded_by_its_own_review(review, state.get("security_review")))
    # What another review of this sprint recorded is not repeated as a finding that does not hold it (PA.17).
    from app.agents.milestone_reviewer import without_repeats_of_other_reviews

    review = _through("repeats_another_review", review,
                      without_repeats_of_other_reviews(review, state.get("sprint_findings")))
    review = _through("the_dependency_check_contradicts", review, _findings_the_dependency_check_contradicts(review, state))
    review = _through("about_the_harness_s_files", review, _findings_about_the_harness_s_files_made_minor(review, root))
    review = _through("about_the_locked_suite", review, _findings_about_the_locked_suite_made_minor(review, root))
    review = _through("a_server_only_the_tests_start", review, _findings_about_a_server_only_the_tests_start(review, root))
    review = _through("the_command_record_contradicts", review, _findings_the_command_record_contradicts(review, root))
    review = _through("no_measure_holds", review, _findings_no_measure_holds(review, root))
    review = _through("a_pass_over_its_own_findings", review,
                      _a_pass_over_its_own_findings(review, root, "accepted", "milestone_review"))
    review = _through("nothing_in_it_gates", review, _accepted_when_nothing_in_it_gates(review, root))
    # This round's findings, in the state the sprint record below reads, so
    # a sprint that ends on this review records the review that ended it.
    from app.sprint.record import findings_of

    state = {
        **state,
        "sprint_findings": list(state.get("sprint_findings") or [])
        + findings_of(review, "milestone", state.get("milestone_revision_count", 0) + 1),
    }

    # The document is rendered here, from the decision the workflow routes
    # on, rather than written by the reviewer as a second copy that can
    # disagree with it. See `app.agents.review_document`.
    _record_review_document(state, review, milestone.selected_sprint_goal)

    if review.status == "blocked":
        summary = _record_sprint_summary(state, "Failed", "Blocked by review")
        return _handing_on(
            **summary,
            stage=MILESTONE_REVIEW_NEXT_STAGE["blocked"],
            milestone_review=review,
            milestone_plan=None,
            specialist_outputs={},
            remediation=None,
            test_round=0,
            defect_cursor=0,
            milestone_revision_count=state.get("milestone_revision_count", 0) + 1,
        )
    elif review.status == "changes_required" and (
        not review.findings
        or _milestone_findings_that_block(state, review)
    ):
        # A `changes_required` carrying nothing above the gating severities
        # falls through to the accepted path below - the same hole that
        # cost one run six architecture rounds, fixed for every
        # reviewer rather than the one that happened to fail. An empty
        # `findings` still enters here, because the branch below has its
        # own message for a review that asked for changes and said nothing.
        findings_text = _milestone_changes_requested(review)
        if findings_text is None:
            return _handing_on(
                stage="failed",
                error=(
                    "The milestone review asked for changes but did not say what "
                    "to change: `findings` was empty and it recorded no evidence "
                    "either. Resume to re-run the review."
                ),
                milestone_review=review,
            )
        if not review.findings:
            # The reviewer described a defect only in `acceptance_evidence`.
            # `_findings_that_block` reads `findings`, so gating would be
            # bypassed and the lead would be handed prose it cannot act on
            # deterministically - the failure behind one run, where a
            # browser-breaking defect survived three revisions because it was
            # never turned into a task. Ask the reviewer again on a fresh
            # conversation before falling back to the evidence below.
            retries = dict(state.get("structured_retries", {}))
            attempted = retries.get("milestone_review:findings", 0) + 1
            retries["milestone_review:findings"] = attempted
            if attempted < _max_structured_retries():
                logger.warning(
                    "Milestone review requested changes with no structured "
                    "findings; re-reviewing on a fresh conversation "
                    "(attempt %d of %d)",
                    attempted + 1,
                    _max_structured_retries(),
                )
                return _handing_on(
                    stage="milestone_review",
                    structured_retries=retries,
                    milestone_review=review,
                )
            logger.warning(
                "Milestone review still has no structured findings after %d "
                "attempts; raising the ones the checks can prove",
                attempted,
            )
            # Two fresh conversations have now declined to structure this
            # review, so stop asking a model for something the workspace
            # already answers. The cross-file checks decide these by reading
            # the files, and `summarise_integration` has already told this
            # reviewer that each one "means a feature DOES NOT WORK".
            #
            # Measured on one run: three proven defects, including an
            # `index.html` linking a `style.css` that was not there, went in
            # as evidence and came back as prose with `findings: []`. Prose
            # is not a task, so the lead was handed a paragraph three times
            # and the run failed with all three defects still in place.
            proven = findings_for_what_the_checks_proved(
                state["repository"].root_path,
                getattr(state.get("stack_selection"), "technology_stack", None),
                getattr(state.get("document"), "text", "") or "",
            )
            if proven:
                logger.info(
                    "Raising %d milestone finding(s) the cross-file checks "
                    "proved: %s",
                    len(proven),
                    "; ".join(finding.description[:80] for finding in proven),
                )
                review = review.model_copy(update={"findings": proven})
                # Re-rendered so the revision request the lead receives names
                # the findings rather than the prose they replaced.
                findings_text = _milestone_changes_requested(review) or findings_text
            else:
                logger.warning(
                    "Nothing the checks can prove either; falling back to the "
                    "recorded evidence"
                )
        revision_count = state.get("milestone_revision_count", 0) + 1
        # Fast sends a sprint back once, as the architecture review does:
        # one run's milestone review sent a sprint whose every acceptance
        # test passed back twice, 35 minutes a round.
        if revision_count >= FAST_MILESTONE_REVISIONS and _fast_delivery():
            # Fast delivery (owner, 2026-10-15): the review's findings
            # become the sprint's recorded risks, carried to the next
            # sprint with the rest of its findings, and the sprint goes on
            # to the checks below - a red suite, a criterion due that
            # fails or a sprint not done still stop it. One run's reviews
            # found new, different findings each round while every test
            # passed; the third would have stopped the run for a person.
            from app.decisions import record_decision

            risked: dict[str, Any] = {}
            record_decision(
                state, risked, point="milestone_review",
                question=f"The review still asks for changes after {revision_count - 1} revision(s): stop or go on?",
                options=["stop for a person", RECORDED_AS_RISKS],
                decision=RECORDED_AS_RISKS,
                rationale="Fast delivery. Every test the sprint is measured by is checked next; the "
                "open findings are carried to the next sprint:\n" + findings_text[:3000],
            )
            logger.warning(
                "Milestone review still asks for changes after %d revision(s); fast delivery records "
                "its %d finding(s) as risks and goes on to the checks",
                revision_count - 1, len(review.findings or []),
            )
            state = {**state, **risked, "milestone_revision_count": revision_count}
        elif revision_count >= MAX_MILESTONE_REVISIONS:
            # This sprint ends here, so it gets a summary like every other
            # ending. Measured on one run, which failed exactly here:
            # `docs/` held the plan, the review and the specification, and no
            # `sprint_1_summary.md` at all - the one document a reader opens
            # to ask what the sprint did and why it stopped. The four paths
            # that record a summary are the ones that go through
            # `_replan_or_escalate`, a blocked review, a sprint advance or
            # completion; a review that runs out of revisions is a fifth, and
            # it is the one this run took.
            summary = _record_sprint_summary(
                state,
                "Failed",
                f"the milestone review still required changes after "
                f"{MAX_MILESTONE_REVISIONS} revisions",
            )
            return _escalate_to_a_human(
                state,
                error=(
                    f"The milestone review still required changes after "
                    f"{MAX_MILESTONE_REVISIONS} revisions, so the run stopped "
                    f"rather than revising indefinitely.\n\n{findings_text}"
                ),
                milestone_revision_count=revision_count,
                milestone_review=review,
                **summary,
            )
        else:
            return _handing_on(
                stage="technical_lead",
                revision_comments=state.get("revision_comments", []) + [findings_text],
                milestone_revision_count=revision_count,
                milestone_review=review,
            )

    if review.status != "accepted" and review.findings:
        logger.info(
            "Stage milestone_review asked for changes over %d finding(s), none "
            "above %s; recorded and continuing",
            len(review.findings),
            "/".join(sorted(_GATING_SEVERITIES)),
        )

    # Before anything is accepted: the ledger's own count of the suite. A
    # review that reports a passing suite over a measured failing one is the
    # worst outcome in this pipeline, because nothing after it looks again.
    # See `_a_red_suite_the_review_called_green` for the run this is measured
    # on. Bounded by the same revision limit as every other send-back, so a
    # suite that cannot be made to pass ends the run rather than looping.
    red = _a_red_suite_the_review_called_green(state)
    if red:
        revision_count = state.get("milestone_revision_count", 0) + 1
        if revision_count < MAX_MILESTONE_REVISIONS:
            logger.warning(
                "Milestone review accepted a sprint whose measured suite is "
                "failing; sending it back: %s",
                red[:160],
            )
            return _handing_on(
                stage="technical_lead",
                revision_comments=state.get("revision_comments", []) + [red],
                milestone_revision_count=revision_count,
                milestone_review=review,
            )
        summary = _record_sprint_summary(
            state,
            "Failed",
            f"the suite was still failing after {MAX_MILESTONE_REVISIONS} revisions",
        )
        return _escalate_to_a_human(
            state,
            error=(
                f"The sprint's own test suite was still failing after "
                f"{MAX_MILESTONE_REVISIONS} revisions.\n\n{red}"
            ),
            milestone_revision_count=revision_count,
            milestone_review=review,
            **summary,
        )

    # The acceptance suite is the definition of done: a sprint whose due
    # criteria fail is not accepted, whatever the review read. Measured by
    # the harness's run of the locked suite, not reported by a model.
    not_passing = acceptance_nodes.due_criteria_failing(state)
    if not_passing:
        revision_count = state.get("milestone_revision_count", 0) + 1
        if revision_count < MAX_MILESTONE_REVISIONS:
            logger.warning("Milestone review would accept failing acceptance criteria; sending it back")
            return _handing_on(
                stage="technical_lead",
                revision_comments=state.get("revision_comments", []) + [not_passing],
                milestone_revision_count=revision_count,
                milestone_review=review,
            )
        summary = _record_sprint_summary(
            state,
            "Failed",
            f"acceptance criteria still failing after {MAX_MILESTONE_REVISIONS} revisions",
        )
        return _escalate_to_a_human(
            state,
            error=(
                f"Acceptance criteria were still failing after {MAX_MILESTONE_REVISIONS} "
                f"revisions.\n\n{not_passing}"
            ),
            milestone_revision_count=revision_count,
            milestone_review=review,
            **summary,
        )

    sprint_index = state.get("current_sprint_index", 0)
    sprints = state.get("sprint_plan").sprints if state.get("sprint_plan") else []
    has_more_sprints = sprint_index < len(sprints) - 1

    # The definition of done: the part of "finished" that needs no judgement.
    # A sprint with a work order that never returned, or a defect still
    # open, is not finished however the review read it, and the next sprint
    # must not start on top of it. Bounded like every other send-back.
    from app.sprint.record import definition_of_done_gaps

    gaps = definition_of_done_gaps(milestone, outputs, cycle)
    if gaps:
        gaps_text = "The sprint is not done:\n" + "\n".join(f"- {gap}" for gap in gaps)
        revision_count = state.get("milestone_revision_count", 0) + 1
        if revision_count < MAX_MILESTONE_REVISIONS:
            logger.warning("Milestone accepted but not done; sending it back: %s", gaps_text[:200])
            return _handing_on(
                stage="technical_lead",
                revision_comments=state.get("revision_comments", []) + [gaps_text],
                milestone_revision_count=revision_count,
                milestone_review=review,
            )
        summary = _record_sprint_summary(state, "Failed", "the sprint was not done: " + "; ".join(gaps))
        return _escalate_to_a_human(
            state,
            error=f"The sprint was accepted but is not done after {MAX_MILESTONE_REVISIONS} revisions.\n\n{gaps_text}",
            milestone_revision_count=revision_count,
            milestone_review=review,
            **summary,
        )

    # Adopted specialist advice found not built when due (SP.1): sent back once, then an open gap of the product.
    sent_back, noted = _the_adopted_advice_owed(state, review, MAX_MILESTONE_REVISIONS)
    if sent_back is not None:
        return sent_back
    state = {**state, **noted}

    # Accepted: the tests ran, the reviewer read them and said yes. This is
    # the only point in a sprint where the workflow has an opinion that the
    # work is sound, so it is the only sensible thing to record as a state
    # worth returning to. Never fails the sprint that has just passed.
    try:
        from app.tools.version_control import commit_milestone

        commit_milestone(
            state["repository"].root_path,
            sprint=sprint_index + 1,
            goal=milestone.selected_sprint_goal,
            summary=_as_text(review.acceptance_evidence),
        )
    except Exception:  # noqa: BLE001 - history is a convenience, not the run
        logger.warning("Could not record a commit for this sprint", exc_info=True)

    # The last sprint is the only place the whole brief is the question.
    # Every milestone review before this one is scoped to its own
    # milestone, and deferring a requirement out of one is legitimate -
    # that is what a sprint plan is for. Nothing asked the other question,
    # and `complete_node` returns `{"stage": "complete"}` and nothing else,
    # so a requirement deferred out of every milestone in turn was never
    # checked at all. Three completed runs shipped with no way to edit a
    # task that way: three runs.
    if not has_more_sprints:
        unbuilt = _a_brief_requirement_the_run_never_built(state)
        if unbuilt:
            revision_count = state.get("milestone_revision_count", 0) + 1
            if revision_count < MAX_MILESTONE_REVISIONS:
                logger.warning(
                    "The last sprint was accepted with a brief requirement "
                    "unbuilt; sending it back rather than completing: %s",
                    unbuilt[:160],
                )
                return _handing_on(
                    **noted,
                    stage="technical_lead",
                    revision_comments=state.get("revision_comments", []) + [unbuilt],
                    milestone_revision_count=revision_count,
                    milestone_review=review,
                )
            return _escalate_to_a_human(
                state,
                error=(
                    "The last sprint was accepted, but the brief has a "
                    f"requirement this run never built.\n\n{unbuilt}"
                ),
                milestone_revision_count=revision_count,
                milestone_review=review,
            )

    # A decision like any other, and the page the sprint's reviewer reads.
    from app.decisions import record_decision
    from app.graph import delivery

    accepted: dict[str, Any] = {}
    record_decision(
        state, accepted, point="sprint",
        question=f"Is sprint {sprint_index + 1} done?",
        options=["accept", "send it back"],
        decision="accept",
        rationale=(
            "The milestone review accepted it and every acceptance criterion due by "
            "this sprint passes. " + _as_text(review.acceptance_evidence)
        )[:1500],
    )
    delivery.write_evidence({**state, **accepted}, sprint_index + 1, milestone.selected_sprint_goal)
    from app.graph import engineering

    engineering.accepted_state(state["repository"].root_path)

    if _review_enabled(state, SPRINT_REVIEW):
        next_stage = "user_review_sprint"
    elif has_more_sprints:
        next_stage = "sprint_advance"
    else:
        next_stage = "release"

    return _handing_on(**{**noted, **accepted}, stage=next_stage, milestone_review=review)


def _the_adopted_advice_owed(state: Any, review: Any, most_revisions: int) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """(the send-back to the lead, or None; what to record whichever way) for adopted advice not built (SP.1).

    The specialists' "not built" lines that name an adopted item due by this sprint are owed work, not opinions:
    each is sent back to the lead once, like any gating finding, while revisions remain. One the lead declined with
    a reason when it was sent back is a change to the specification, recorded in the decision log. One still not
    built after its send-back - or with no revision left to send it in - is recorded as an open gap: a decision,
    and a note of the release. Measured on one medium run: sprint 2's database and security specialists found
    eleven adopted items not built, recorded as minor; the sprint was accepted and the product shipped without them.
    """
    from app.agents.advice_review import (
        declined_with_a_reason, item_owed, open_gap, owed_and_not_built, send_back_text,
    )
    from app.decisions import record_decision
    from app.graph.workflow import _handing_on, _this_review_s_advice_findings

    found = _this_review_s_advice_findings(state)
    noted: dict[str, Any] = {}
    if not any(found.values()):
        return None, noted
    sent = [str(ident) for ident in state.get("advice_sent_back") or []]
    declined = dict(state.get("advice_declined") or {})
    plan = state.get("milestone_plan")
    newly = {
        ident: line for ident, line in declined_with_a_reason(
            [*(getattr(plan, "review_task_assignments", None) or []),
             *(getattr(plan, "carried_forward_decisions", None) or [])], sent,
        ).items() if ident not in declined
    }
    if newly:
        declined.update(newly)
        noted["advice_declined"] = declined
        record_decision(
            state, noted, point="technical_specification",
            question="Change the specification: decline adopted specialist advice " + ", ".join(newly) + "?",
            options=["build it", "decline it"],
            decision="decline " + ", ".join(newly),
            rationale="The specification adopted these items; sent back as not built, the lead declined them:\n"
            + "\n".join(f"- {line}" for line in newly.values()),
        )
    now, still = owed_and_not_built(found, sent_back=sent, declined=declined)
    revision_count = int(state.get("milestone_revision_count", 0) or 0) + 1
    if now and revision_count < most_revisions:
        logger.warning("Milestone accepted with %d adopted advice item(s) not built; sending them back once", len(now))
        return _handing_on(
            **noted,
            stage="technical_lead",
            revision_comments=list(state.get("revision_comments") or []) + [send_back_text(now)],
            milestone_revision_count=revision_count,
            milestone_review=review,
            advice_sent_back=sent + [item_owed(line) for line in now],
        ), noted
    recorded = {item_owed(gap.split("): ", 1)[-1]) for gap in state.get("advice_open_gaps") or []}
    sprint = int(state.get("current_sprint_index", 0) or 0) + 1
    gaps = [line for line in [*still, *now] if item_owed(line) not in recorded]
    if gaps:
        logger.warning("%d adopted advice item(s) still not built after one send-back; recorded as open gaps", len(gaps))
        record_decision(
            {**state, **noted}, noted, point="sprint",
            question=f"Sprint {sprint}: adopted specialist advice is still not built after its one send-back. "
            "Hold the sprint, or go on with it recorded as an open gap?",
            options=["hold the sprint", "go on, recorded as an open gap"],
            decision="go on, recorded as an open gap",
            rationale="Each item was sent back once, or no revision was left to send it in; the specialist's line:\n"
            + "\n".join(f"- {line}" for line in gaps),
        )
        noted["advice_open_gaps"] = [*(state.get("advice_open_gaps") or []), *(open_gap(line, sprint) for line in gaps)]
    return None, noted
