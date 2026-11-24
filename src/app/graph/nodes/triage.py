"""A sprint's test round: the tests run, and what fails becomes owned defects.

    test_and_triage -> defect_remediation, or security_review once it passes,
        or technical_lead / escalation when its attempts run out (`_replan_or_escalate`)

See `app.graph.nodes` for how these are registered and why their helpers are
imported from `app.graph.workflow` when they run.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.observability.degraded import degraded
from app.graph.context import GraphContext
from app.graph.workflow import WorkflowGraphState
from app.sprint import cause

#: Problems the cross-file check proved that one round raises as defects of their own; the rest ride on the last one.
#: Measured on one run: 138 and 151 in a round, each its own fixer, and the run ended on the graph's step limit.
MOST_PROVEN_PER_ROUND = 10


def at_most(problems: list[Any], most: int) -> list[Any]:
    """`problems` as at most `most` defects: the first `most - 1` as they are, and the last naming the rest, so none is
    lost and no round queues more fixers than the graph can step through."""
    if len(problems) <= most:
        return list(problems)
    kept, rest = list(problems[: most - 1]), list(problems[most - 1:])
    named = "; ".join(str(getattr(p, "description", "") or "")[:160] for p in rest[:6])
    last = rest[0]
    more = f" (and {len(rest) - 1} more of the same check: {named}{'; ...' if len(rest) > 6 else ''})"
    return kept + [last.model_copy(update={"description": f"{getattr(last, 'description', '')}{more}"})]


#: Defects one source - the test round, the acceptance suite, the page check, a review - raises into fixers in one
#: round; the rest ride on the last, as `at_most` bundles them. Measured on one medium run: 14 and 15 fixers queued in
#: one round from the test round and the acceptance suite, uncapped while the cross-file check was capped, and the
#: run's graph met its step limit in the fix round.
MOST_FROM_ONE_SOURCE_PER_ROUND = MOST_PROVEN_PER_ROUND

_SEVERITY_RANK = {"blocking": 2, "major": 1}


def _size_of_its_cause(defect: Any) -> tuple[int, int]:
    """How large a cause is, for keeping the largest: a blocking one first, then the most that measured it."""
    return (_SEVERITY_RANK.get(str(getattr(defect, "severity", "") or ""), 0),
            len(getattr(defect, "evidence", None) or ()))


def at_most_of_each_source(reported: list[Any], most: int = MOST_FROM_ONE_SOURCE_PER_ROUND) -> list[Any]:
    """`reported` with each source's defects at most `most`: an over-full source keeps its largest causes and bundles
    the rest into one defect of its own (`at_most`), in the place its first defect had. A source within `most` is
    left as it is, in its order."""
    by_source: dict[str, list[Any]] = {}
    for defect in reported:
        by_source.setdefault(str(getattr(defect, "source", "") or ""), []).append(defect)
    capped: dict[str, list[Any] | None] = {
        source: at_most(sorted(group, key=_size_of_its_cause, reverse=True), most)
        for source, group in by_source.items() if len(group) > most
    }
    if not capped:
        return list(reported)
    kept: list[Any] = []
    for defect in reported:
        source = str(getattr(defect, "source", "") or "")
        if source not in capped:
            kept.append(defect)
        elif capped[source] is not None:
            kept.extend(capped[source] or [])
            capped[source] = None
    return kept

#: The workflow's logger: the nodes log as they did inside the builder.
logger = logging.getLogger("app.graph.workflow")


def test_and_triage_node(state: WorkflowGraphState, config: RunnableConfig, ctx: GraphContext) -> dict[str, Any]:
    from app.graph.workflow import (
        Defect, MAX_REMEDIATION_ATTEMPTS, RemediationLimitExceeded, SpecialistOutput,
        _a_round_that_found_a_product_defect, _a_suite_failure_the_round_did_not_report,
        _clear_the_throwaways, _closed_by_this_round_s_measurement, _defects_a_later_sprint_builds,
        _defects_only_about, _defects_only_about_deferred, _diagnosed_file_by_file, _each_defect_once,
        _failing_criteria_it_names, _handing_on, _missing_upstream, _mutation_findings_set_aside,
        _needs_a_new_test, _one_defect_per_cause, _one_defect_per_failing_tests,
        _one_defect_per_root_error, _only_mutation_findings_open,
        _only_unit_tests_open_beside_a_green_suite, _proven_problems_the_round_left_out,
        _put_back_a_deliberate_change, _refreshed_by_the_round, _run_gated_agent,
        _run_unit_tests_procedurally, _the_files_this_milestone_changed, _the_mutation_probe,
        _the_served_app_is_the_scaffold_s_stub, _the_test_command_this_stage_left_failing,
        _the_failing_unit_tests, _the_unit_tests_fail, _this_attempt, _what_later_sprints_build, _with_the_contract_s_server_errors,
        _with_a_page_check_defect, _with_the_lock_s_server_errors, build_test_run_request, create_specialist_agent,
        is_sprint_acceptable, raised_by, record_test_run, start_remediation, superseded_by_one_cause,
        the_round_s_measurement, with_the_facts,
    )

    missing = _missing_upstream(state, "milestone_plan")
    if missing is not None:
        return missing
    """Run the tests for this milestone and triage every failure into a tracked defect.

    This is steps 2 and 3 of the plan's remediation loop. It runs after each
    implementation or fix round, so `test_round` gives every round its own
    inner thread id - reusing one thread would make the Test Engineer
    re-read a stale conversation instead of testing the current state.

    Outcomes:
    - failures found -> `defect_remediation` routes each defect to its owner
    - clean run -> the acceptance gate (`is_sprint_acceptable`) decides
      whether the sprint may be accepted at all
    - attempts exhausted -> `failed`, carrying the defect report as evidence
    """
    milestone = state["milestone_plan"]
    test_round = state.get("test_round", 0)
    outputs = state.get("specialist_outputs", {})
    # A worker that died with a deliberate change in the product left it
    # there; the round must not measure it (plan QM.2, off until measured).
    _put_back_a_deliberate_change(state)
    # The harness runs the locked acceptance suite once per round, on the
    # round's first entry (a resume after an approval pause is the same
    # round), and hands the measured result to the test engineer.
    from app.graph import acceptance_nodes

    acceptance_text = ""
    beyond_repair: list[str] = []
    #: Why this round's measurement could not be taken, when it could not: the round then charges no attempt (A1).
    not_measured = ""
    if not state.get("pending_inner_thread_id"):
        # Before the round, not after a pause inside it: the stages that
        # wrote these have all finished, and the round should measure the
        # product without them.
        _clear_the_throwaways(state["repository"].root_path)
        from app.acceptance import unmeasured

        unmeasured.taken(state["repository"].root_path)  # an earlier stage's record is not this round's
        acceptance_text, cannot_pass = acceptance_nodes.acceptance_for_round(state)
        not_measured = unmeasured.last(state["repository"].root_path)
        # A locked test that cannot pass whatever is built is not a
        # product defect: no fix can close it. Repaired by QA first.
        reopened = acceptance_nodes.reopen_the_suite_for(state, cannot_pass, model=ctx.judgement_model)
        if reopened is not None:
            return reopened
        # And once the suite may not be repaired again, the round is told,
        # and its defects about them go to no fixer.
        beyond_repair = acceptance_nodes.beyond_repair(state, cannot_pass)
        if beyond_repair:
            logger.warning(
                "Locked tests of %s cannot pass and the suite's repairs are spent; "
                "their failures are not product defects", ", ".join(beyond_repair),
            )
            acceptance_text = "\n\n".join(
                part for part in (acceptance_text, acceptance_nodes.beyond_repair_note(cannot_pass, beyond_repair))
                if part
            )
            acceptance_nodes.defer_what_is_beyond_repair(state, beyond_repair, cannot_pass)
    failing_due, _ = acceptance_nodes._failing_due(state)
    # The round is the harness's own only on evidence: a locked suite whose
    # last run happened and passes everything due, the unit tests run and
    # passed, and nothing else proven wrong. Anything unknown - no locked
    # suite, a run that wrote no report, no unit command, a check that
    # failed to answer - is the testing specialist's round, as before.
    saved_run = acceptance_nodes.suite.last_result(state["repository"].root_path) or {}
    skip_agent = (
        not state.get("pending_inner_thread_id")
        and acceptance_nodes.suite.is_locked(state["repository"].root_path)
        and bool(saved_run.get("ran"))
        and not failing_due
        and not cannot_pass
        and not state.get("review_defects")
    )
    if skip_agent:
        unit_ok, _ = _run_unit_tests_procedurally(state["repository"].root_path)
        skip_agent = unit_ok is True
    still_proven: list[str] = []
    if skip_agent:
        try:
            from app.agents.specialists import what_the_files_already_prove

            still_proven = what_the_files_already_prove(
                state["repository"].root_path,
                getattr(state.get("stack_selection"), "technology_stack", None),
                [
                    *(getattr(milestone, "milestone_scope", None) or ()),
                    *(
                        getattr(task, "task_description", "")
                        for task in (getattr(milestone, "delegated_tasks", None) or ())
                    ),
                ],
                _what_later_sprints_build(state),
                getattr(state.get("document"), "text", "") or "",
            )
        except Exception as swallowed:  # noqa: BLE001 - a check that cannot answer is no evidence
            degraded("triage.what_the_files_prove", swallowed)
            skip_agent = False

    from app import delivery

    harness_round = (
        delivery.fast()
        and not state.get("pending_inner_thread_id")
        and acceptance_nodes.suite.is_locked(state["repository"].root_path)
        and bool(saved_run.get("ran"))
        and not cannot_pass
    )
    if harness_round and not (skip_agent and not still_proven):
        # Fast delivery: the harness's measurement is the round. What
        # fails becomes a defect below, without a model reading it -
        # the failing criteria, the proven problems, the review's
        # findings; and the unit tests, here.
        unit_ok, unit_output = _run_unit_tests_procedurally(state["repository"].root_path)
        logger.info(
            "test_round_%d: run by the harness (fast delivery); unit tests %s",
            test_round, {True: "pass", False: "fail", None: "not recorded"}[unit_ok],
        )
        beside_a_green_suite = not failing_due and int(saved_run.get("failed") or 0) == 0
        # Beside a green locked suite, a unit test failing in two product states is set aside, not raised (B6).
        from app.graph import unit_test_quarantine

        raised = unit_ok is False and (not beside_a_green_suite or unit_test_quarantine.raised_beside_a_green_suite(
            state["repository"].root_path))
        harness_defects: list[Any] = (
            [] if not raised else [_the_unit_tests_fail(
                milestone, unit_output, beside_a_green_suite=beside_a_green_suite,
                failing=_the_failing_unit_tests(state["repository"].root_path),
            )]
        )
        if failing_due:
            # The suite ran and locked criteria failed: ask whether what it
            # ran against is still the scaffold's stub (Initiative K.3).
            from app.stacks.scaffold import entrypoint_is_still_the_stub

            if (stubbed := entrypoint_is_still_the_stub(state["repository"].root_path)) is not None:
                harness_defects.append(
                    _the_served_app_is_the_scaffold_s_stub(
                        stubbed, _the_unit_tests_fail(milestone, "").owner
                    )
                )
        update = {
            "__test_result__": SpecialistOutput(
                changed_files=[],
                defects=harness_defects,
                decisions=["The harness ran this round itself (fast delivery)."],
            )
        }
    elif (diagnosed := _diagnosed_file_by_file(state, saved_run, milestone, test_round)) is not None:
        update = {"__test_result__": diagnosed}
    elif skip_agent and not still_proven:
        logger.info(
            "test_round_%d: all acceptance criteria due and unit tests passed procedurally with 0 defects; skipping specialist LLM invocation",
            test_round,
        )
        update = {
            "__test_result__": SpecialistOutput(
                changed_files=[],
                defects=[],
                decisions=[
                    "The harness ran this round itself: the locked suite passes every criterion "
                    "due, and the unit tests pass."
                ],
            )
        }
    else:
        changed_files = _the_files_this_milestone_changed(state, outputs)

        agent = create_specialist_agent(
            "testing", model=ctx.judgement_model, checkpointer=ctx.checkpointer, repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories
        )
        request = build_test_run_request(
            milestone.selected_sprint_goal,
            changed_files,
            state["repository"].root_path,
            getattr(state.get("stack_selection"), "technology_stack", None),
            # The plan's own prose, so a file it named and nobody wrote is found
            # here rather than at the milestone review, where it costs a
            # revision. Both of the last two runs ended that way.
            planned=[
                *(getattr(milestone, "milestone_scope", None) or ()),
                *(
                    getattr(task, "task_description", "")
                    for task in (getattr(milestone, "delegated_tasks", None) or ())
                ),
            ],
            later_sprints=_what_later_sprints_build(state),
            brief=getattr(state.get("document"), "text", "") or "",
            acceptance=acceptance_text,
        )
        # The facts the work is built and judged under (plan CM.1).
        request = with_the_facts(request, state["repository"].root_path)
        # The milestone's changed files held in its memory, numbered, when today's request and memory do not show
        # them all (LF.1286): measured on one medium run, each round read the same 13-20 files 3.5-7 times each,
        # summarised 5-12 times a round.
        from app.agents import review_files

        root = state["repository"].root_path
        request = review_files.with_the_files_held(request, review_files.held_for_review(
            review_files.under_review(root, changed_files), root, ctx.judgement_model, f"test_round_{test_round}",
            review_files.opening_of(request)), "test_round")
        update = _run_gated_agent(
            state,
            config,
            stage_name=f"test_round_{test_round}",
            agent=agent,
            initial_request=request,
            output_key="__test_result__",
            next_stage="test_and_triage",
        )
        if "__test_result__" not in update:
            return update  # paused waiting for approval on a test artifact

    test_result: SpecialistOutput = update.pop("__test_result__")
    # Asked whenever the locked suite is green, whatever else the round found: measured on one run, failing unit
    # tests kept every round from being clean and the checks were never asked before release. And when it is near
    # green with the product answering (a test passed): measured on a Java run, the best round was 9 of 10, the sprint
    # was accepted from there, and `GET /notes/abc` answering 500 shipped - the check was never asked of a product
    # that started.
    from app.graph.near_green_once import near_green

    passed, failed = int(saved_run.get("passed") or 0), int(saved_run.get("failed") or 0)
    green = not failing_due and failed == 0
    if green or (passed > 0 and near_green(passed, failed)):
        test_result = _with_the_contract_s_server_errors(state, test_result, milestone)
    if green:
        test_result = _with_a_page_check_defect(state, test_result, milestone)
        from app.acceptance import order_probe

        order_probe.at_a_green_round(state["repository"].root_path)
    test_result = _with_the_lock_s_server_errors(state, test_result, milestone)
    # CI's regressions and the code review's findings for this batch, once.
    reported: list[ReportedDefect] = _each_defect_once(
        [*raised_by("test round", test_result.defects), *(state.get("review_defects") or [])]
    )
    if len(reported) < len(test_result.defects):
        logger.warning(
            "test_round_%d reported %d defect(s), %d of them repeats; keeping %d",
            test_round, len(test_result.defects),
            len(test_result.defects) - len(reported), len(reported),
        )
    # Read after the round, so a problem it fixed - a test config is its to
    # change - is not reported back to it as still there.
    try:
        from app.agents.specialists import what_the_files_already_prove

        still_proven = what_the_files_already_prove(
            state["repository"].root_path,
            getattr(state.get("stack_selection"), "technology_stack", None),
            [
                *(getattr(milestone, "milestone_scope", None) or ()),
                *(
                    getattr(task, "task_description", "")
                    for task in (getattr(milestone, "delegated_tasks", None) or ())
                ),
            ],
            _what_later_sprints_build(state),
            getattr(state.get("document"), "text", "") or "",
        )
        left_out = _proven_problems_the_round_left_out(still_proven, reported, milestone, state["repository"].root_path)
    except Exception as swallowed:  # noqa: BLE001 - the round's own report stands
        degraded("triage.proven_problems_left_out", swallowed)
        left_out = []
    if left_out:
        logger.warning(
            "test_round_%d left out %d problem(s) it was handed as proven; recording them as defects",
            test_round, len(left_out),
        )
        reported = reported + raised_by("cross-file check", at_most(left_out, MOST_PROVEN_PER_ROUND))
    # How the page is presented, where a script can prove it: an interface
    # nothing styles, or a page that does not fit the phone the brief asks
    # for. Before the later-sprint filter, so a plan that styles later keeps
    # that work for the sprint that builds it.
    try:
        reported = reported + raised_by("page check", acceptance_nodes.interface_defects(state))
    except Exception as swallowed:  # noqa: BLE001 - the round's own report stands
        degraded("triage.page_presentation", swallowed)
    # What the pack's scaffold depends on and a rewrite dropped (PACK_ENTRY_EXPORTS_KEPT).
    try:
        reported = reported + raised_by("pack contract", acceptance_nodes.pack_contract_defects(state))
    except Exception as swallowed:  # noqa: BLE001 - the round's own report stands
        degraded("triage.pack_entry_exports", swallowed)
    reported, later_work = _defects_a_later_sprint_builds(reported, state)
    if later_work:
        logger.warning(
            "test_round_%d reported %d defect(s) about work a later sprint builds; "
            "left for that sprint, not fixed in this one: %s",
            test_round, len(later_work),
            "; ".join(str(getattr(item, "description", ""))[:60] for item in later_work[:4]),
        )
    reported, unfixable = _defects_only_about(reported, beyond_repair, state["repository"].root_path)
    if unfixable:
        logger.warning(
            "test_round_%d reported %d defect(s) only about locked tests that cannot pass and may "
            "not be repaired again; set aside: %s",
            test_round, len(unfixable),
            "; ".join(str(getattr(item, "description", ""))[:60] for item in unfixable[:4]),
        )
    reported, deferred_only = _defects_only_about_deferred(reported, state["repository"].root_path)
    if deferred_only:
        logger.warning(
            "test_round_%d reported %d defect(s) only about deferred criteria; set aside: %s",
            test_round, len(deferred_only),
            "; ".join(str(getattr(item, "description", ""))[:60] for item in deferred_only[:4]),
        )
    try:
        unreported_criteria = acceptance_nodes.failing_due_defects(state, reported)
        # Nor the backstop's own for them: deferred above, they are no fix stage's.
        unreported_criteria, _ = _defects_only_about(unreported_criteria, beyond_repair)
        unreported_criteria, _ = _defects_only_about_deferred(unreported_criteria, state["repository"].root_path)
    except Exception as swallowed:  # noqa: BLE001 - the round's own report stands
        degraded("triage.acceptance_suite_compare", swallowed)
        unreported_criteria = []
    logger.info("test_round_%d: %s", test_round, the_round_s_measurement(state["repository"].root_path))
    from app.graph import best_attempt

    best_attempt.note(state["repository"].root_path)
    if best_attempt.after_a_redraft(
        state["repository"].root_path, test_round=test_round, replans=int(state.get("sprint_replan_count") or 0),
    ):
        # The redraft left the product clearly worse than its best: the best is back, so the sprint is planned
        # again at once, not after a whole round of fixers on the wreck (KEEP_THE_BEST_ATTEMPT).
        spent = state.get("remediation") or start_remediation(
            milestone.selected_sprint_goal, max_attempts=MAX_REMEDIATION_ATTEMPTS
        )
        return _replan_or_escalate(
            state,
            {"remediation": spent, "test_round": test_round + 1, "pending_approval": None,
             "pending_inner_thread_id": None, "pending_decision": None},
            spent,
            "the redraft left the product worse than its best; the best was put back",
        )
    if unreported_criteria:
        logger.warning(
            "test_round_%d raised %d defect(s) for failing acceptance criteria its report left out",
            test_round, len(unreported_criteria),
        )
        reported = reported + raised_by("acceptance suite", unreported_criteria)
    # One problem, one fixer. See `_one_defect_per_cause`.
    reported = _one_defect_per_cause(reported)
    # One root cause, one fixer: criteria that meet the same first
    # failure share no words to bundle by, only the layer they fail at.
    # See `_one_defect_per_root_error` (Initiative L.1).
    reported = _one_defect_per_root_error(reported)
    # One set of failing tests, one fixer: the criteria they carry are settled together.
    from app.acceptance import suite as _the_suite

    reported = _one_defect_per_failing_tests(reported, _the_suite.last_result(state["repository"].root_path) or {})
    if not reported:
        unreported = _a_suite_failure_the_round_did_not_report(
            state["repository"].root_path, f"test_round_{test_round}",
            but_the_acceptance_suite=bool(unfixable),
        )
        if unreported is not None:
            logger.warning(
                "test_round_%d reported no defects, but its last run of the suite "
                "failed; recording that as a defect", test_round,
            )
            reported = raised_by("test command", [unreported])
    # A product that does not build or start: what says why goes to its one start defect (deep review 1.5).
    from app.graph import start_first

    reported = start_first.folded(reported)
    # A product that starts: its foundation smoked before any fixer of one criterion is sent (LF.1268).
    from app.graph import foundation_first

    reported, smoke = foundation_first.at_the_round(state, reported, test_round)
    # An error the stack pack knows, given its cause (`app.stacks.known_errors`).
    from app.stacks.known_errors import with_known_causes

    reported = with_known_causes(state["repository"].root_path, reported)
    # A resolved package this toolchain cannot run, as the stated cause (HK.2, `app.stacks.toolchain_fit`).
    from app.stacks.toolchain_fit import with_fit_causes

    reported = with_fit_causes(state["repository"].root_path, reported)
    # No source queues more fixers a round than the graph can step through, once the one-cause rules above have
    # merged what is one problem (LF.1261).
    capped = at_most_of_each_source(reported)
    if len(capped) < len(reported):
        logger.warning("test_round_%d raised %d defect(s); bundled to %d, at most %d from one source",
                       test_round, len(reported), len(capped), MOST_FROM_ONE_SOURCE_PER_ROUND)
    reported = capped
    cycle = state.get("remediation") or start_remediation(
        milestone.selected_sprint_goal, max_attempts=MAX_REMEDIATION_ATTEMPTS
    )
    # An earlier round's defect whose criteria this round's measurement
    # finds passing is fixed, whichever fix did it, and does not count
    # against the sprint as still open.
    cycle = _closed_by_this_round_s_measurement(state, cycle, test_round)
    cycle = foundation_first.settled_by_the_round(cycle, smoke, test_round, state.get("current_sprint_index", 0))
    # The test command this round left failing, if it left one. See
    # `_needs_a_new_test`.
    caught_by, _ = _the_test_command_this_stage_left_failing(
        state["repository"].root_path, f"test_round_{test_round}"
    )

    # The model reports what it found; only the workflow may set lifecycle
    # state, so every incoming defect starts as "open" regardless.
    new_defects = [
        Defect(
            description=item.description,
            severity=item.severity,
            reproduction_steps=item.reproduction_steps,
            expected_behavior=item.expected_behavior,
            actual_behavior=item.actual_behavior,
            affected_files=item.affected_files,
            owner=item.owner,
            regression_test_required=_needs_a_new_test(item, caught_by),
            caught_by=caught_by,
            source=str(getattr(item, "source", "") or ""),
            failing_criteria=_failing_criteria_it_names(state, item),
            found_in_round=test_round,
            # What measured it, and the key of its cause (deep review 2026-11-18, item 1.1).
            kind=str(getattr(item, "kind", "") or "") or cause.kind_by_source(getattr(item, "source", "")),
            evidence=list(getattr(item, "evidence", None) or []),
            cause_key=cause.cause_key(getattr(item, "kind", ""), getattr(item, "evidence", None)),
        )
        for item in reported
    ]

    from app.observability import defect_ledger

    # A defect this round raises again - one check's, still open from an
    # earlier round - refreshes that one instead of queueing a second fixer
    # for it. Both still count as this round's findings.
    cycle, repeated = _refreshed_by_the_round(cycle, new_defects, test_round)
    cycle = superseded_by_one_cause(cycle, new_defects)
    new_defects = [item for item in new_defects if not any(item is again for again in repeated)]
    measured = [*new_defects, *repeated]
    for again in repeated:
        defect_ledger.note("raised again", f"test_round_{test_round}", defect=again, round_=test_round,
                            index=-1, sprint=state.get("current_sprint_index", 0),
                            detail="the same check's open defect was refreshed with this round's output")
    for position, item in enumerate(new_defects, start=len(cycle.defects)):
        defect_ledger.note("raised", f"test_round_{test_round}", defect=item, round_=test_round, index=position,
                            sprint=state.get("current_sprint_index", 0))
    if not measured and not not_measured:
        # A fix nothing could measure was left open, unverified, for this round to decide: it measured the product and
        # found nothing wrong. A round that raised anything leaves them open, to be measured or fixed again.
        from app.sprint import closed_by_a_round_that_found_nothing

        cycle, closed = closed_by_a_round_that_found_nothing(cycle, test_round)
        for index in closed:
            defect_ledger.note("closed by the round's measurement", f"test_round_{test_round}",
                               defect=cycle.defects[index], round_=test_round, index=index,
                               sprint=state.get("current_sprint_index", 0),
                               detail="its fix was unverified; this round found nothing wrong")
    # Mutation findings the sprint has no round for are gaps, not a reason
    # to re-plan it (plan QM.2); a no-op for a cycle with none.
    cycle, mutation_gaps = _mutation_findings_set_aside(state, cycle, test_round)
    # Half or more of the round says the work is not built: those defects are their work orders' builders', once an
    # attempt, and the round charges nothing (`unfinished_build`, LF.1299). Thorough delivery only.
    from app.graph import unfinished_build

    to_builders = unfinished_build.at_a_round(state, measured)
    try:
        cycle = record_test_run(
            cycle,
            command=["specialist", "testing", f"round-{test_round}"],
            passed=not measured,
            summary=f"{len(measured)} defect(s) found" if measured else "all applicable tests passed",
            new_defects=new_defects,
            # A round with only mutation findings open charges nothing (plan QM.2).
            # Nor does a round whose measurement the harness could not take (A1): measured, a memory refusal
            # failed every criterion of a round and the sprint was planned again.
            charge_the_budget=_a_round_that_found_a_product_defect(measured) and not (
                _only_mutation_findings_open(cycle, measured)
            ) and not not_measured and not to_builders,
        )
        cycle = unfinished_build.superseded(cycle, to_builders)
    except RemediationLimitExceeded as exc:
        # The same exit as every other exhausted sprint: planned again,
        # as often as the revision limit allows, with this round on its
        # record. Failing the run from here skipped both.
        logger.warning("Sprint is out of remediation attempts: %s", exc)
        try:
            from app.sprint import TestRunRecord

            spent = cycle.model_copy(update={
                "test_runs": [
                    *cycle.test_runs,
                    TestRunRecord(
                        command=["specialist", "testing", f"round-{test_round}"],
                        passed=not new_defects,
                        summary=f"{len(new_defects)} defect(s) found",
                    ),
                ],
                "defects": [*cycle.defects, *new_defects],
                "escalated": True,
            })
        except Exception:  # noqa: BLE001 - the cycle as it stood is still evidence
            spent = cycle
        return _replan_or_escalate(
            state,
            {
                "remediation": spent,
                "test_round": test_round + 1,
                "pending_approval": None,
                "pending_inner_thread_id": None,
                "pending_decision": None,
            },
            spent,
            "exhausted remediation attempts",
        )

    base_update: dict[str, Any] = {
        "remediation": cycle,
        "test_round": test_round + 1,
        "pending_approval": None,
        "pending_inner_thread_id": None,
        "pending_decision": None,
        "review_defects": [],
        # A fix round starts with none of its defects worked: a stage's name repeats in a later attempt's round.
        "fixes_tried": [],
    }
    if mutation_gaps:
        base_update["mutation_gaps"] = mutation_gaps
    if to_builders:
        # Built by the builders of their work orders, then measured by the next round; the faults the round found
        # stay open for the fix round after it.
        return _handing_on(**base_update, **unfinished_build.sent_to_the_builders(state, to_builders, test_round))

    if cycle.escalated:
        return _replan_or_escalate(
            state, base_update, cycle, "exhausted remediation attempts"
        )

    if any(defect.status == "open" for defect in cycle.defects):
        # The fix round before closed nothing and the product is as the round before measured it: another round
        # starts where that one did, so the attempt ends here (LR.53, `FIX_STAGES_THAT_CLOSE_NOTHING`).
        from app.graph import unchanged_fix_round

        if unchanged_fix_round.ends_the_attempt(
            state["repository"].root_path, cycle, attempt=_this_attempt(state), test_round=test_round,
        ):
            logger.warning("test_round_%d: %s", test_round, unchanged_fix_round.SAID)
            return _replan_or_escalate(state, base_update, cycle, unchanged_fix_round.SAID)
        # Far past the sprint's time budget, the round starts no fix round: the attempt ends (`sprint_time_budget`).
        from app.graph import sprint_time_budget

        past = sprint_time_budget.stops_the_fix_round(state, stage=f"test_round_{test_round}")
        if past:
            return _replan_or_escalate(state, base_update, cycle, past)
        if _only_unit_tests_open_beside_a_green_suite(state, cycle):
            # The due criteria pass and only unit tests the model wrote fail: probe now, once an attempt, so
            # its findings join this fix round. Measured on every run of one day: with a failing unit test
            # nearly always open, the probe below - nothing open - was never reached (MUTATION_GUIDED_TESTS).
            probed = _the_mutation_probe(state, cycle, test_round)
            if probed.get("stage"):
                return _handing_on(**{**base_update, **probed})
            base_update.update(probed)
        return _handing_on(**base_update, stage="defect_remediation", defect_cursor=0)

    # Tests pass and nothing is open. The acceptance gate is still the
    # authority on whether this sprint may be accepted - it also refuses a
    # fix with missing regression coverage or an undocumented accepted risk.
    if not is_sprint_acceptable(cycle):
        return _replan_or_escalate(
            state, base_update, cycle,
            "missing regression coverage or an unaccepted risk",
        )

    # Plan QM.2, off until measured: the product exists and its due
    # criteria pass, so a deliberate change no test notices is now a
    # finding for the testing role, before any review reads the sprint.
    probed = _the_mutation_probe(state, cycle, test_round)
    if probed.get("stage"):
        return _handing_on(**{**base_update, **probed})
    return _handing_on(**base_update, **probed, stage="security_review")


def _replan_or_escalate(
    state: WorkflowGraphState,
    base_update: dict[str, Any],
    cycle: Any,
    why: str,
) -> dict[str, Any]:
    """Hand a failed sprint back to be planned again, but only so often.

    `baf753d` changed both of these paths from `stage="failed"` to
    `stage="technical_lead"`, so a sprint that exhausts its remediation
    attempts is planned again instead of ending the run. That is a better
    default and it is kept.

    What it did not add is a bound. `milestone_revision_count` was
    incremented on the way out, and the only place that compares it to
    `MAX_MILESTONE_REVISIONS` is `milestone_review_node` - which this path
    never reaches: `technical_lead` leads to `specialist_dispatch` and back
    to `test_and_triage`, and an unfixable defect exhausts a fresh cycle
    every time. `test_a_defect_that_never_gets_fixed_escalates_instead_of_looping`
    is the test that says so, and it is right.

    So the re-plan is bounded by the same limit as every other revision, and
    past it the run escalates to a human carrying the defect report - which
    is what it did before the feature, at the first failure instead of the
    last.

    The same limit, and a count of its own. It used to add to
    `milestone_revision_count`, the milestone review's, so a sprint whose
    tests took one re-plan reached its review with a revision already
    spent. Measured on one run: one re-plan, then two reviews - the first
    blocked on a `require` in an ES module, which was fixed; the second
    raised four findings, none of them the first's - and the run ended
    "after 3 revisions", ten minutes in, on the first review whose findings
    nobody had been given a chance to fix.
    """
    from app.graph.workflow import (
        MAX_MILESTONE_REVISIONS, _escalate_to_a_human, _handing_on, _record_sprint_summary,
        an_unfinished_sprint, build_defect_report,
    )

    revision_count = state.get("sprint_replan_count", 0) + 1
    # One decision from one measurement (LR.26, `end_of_attempt`): the best attempt back first if this one is
    # worse, then settle (green for this sprint, only unit tests open), stop (the attempts stalled), or re-plan.
    from app.graph import end_of_attempt, sprint_time_budget

    decision = end_of_attempt.decide(state["repository"].root_path, getattr(cycle, "defects", None),
                                     replans=revision_count - 1, best_history=state.get("sprint_best_history"),
                                     budget=sprint_time_budget.measure(state))
    best_history = decision.best_history
    if decision.outcome != end_of_attempt.REPLAN:
        why = f"{why}; {decision.why}"
        revision_count = MAX_MILESTONE_REVISIONS + 1
    # Every defect still open ends its story here: the ledger had it
    # raised and nothing after, which reads like a round cut short.
    from app.observability import defect_ledger

    ending = "escalated to a person" if revision_count > MAX_MILESTONE_REVISIONS else "the sprint is planned again"
    for index, defect in enumerate(getattr(cycle, "defects", None) or []):
        if getattr(defect, "status", "") == "open":
            defect_ledger.note(
                "left open", f"test_round_{state.get('test_round', 0)}", defect=defect,
                round_=state.get("test_round", 0), index=index,
                sprint=state.get("current_sprint_index", 0), detail=f"{why}; {ending}",
            )
    # The sprint as this round leaves it, not as it entered it. `state`
    # still holds the cycle from before the round just recorded, so a
    # summary written from it left out the round that ended the sprint and
    # the defect it found: one run's record read "Failed: exhausted
    # remediation attempts" over six of six tests passed, two bugs found,
    # two fixed, none open.
    state = {**state, **base_update, "remediation": cycle}  # type: ignore[assignment]
    if revision_count > MAX_MILESTONE_REVISIONS:
        summary = _record_sprint_summary(
            state, "Failed", f"{why}; revision limit reached"
        )
        # Failed, not parked at the sprint review. `_escalate_to_a_human`
        # sends a run to `user_review_sprint` when that review is switched
        # on, and that gate asks one question - accept this sprint? - whose
        # approve path is `sprint_advance`. Offering it a sprint whose tests
        # never passed invites a human to accept, in one click, work that
        # was never shown to work; it also drops `error` on that branch, so
        # the reviewer is asked without being told what is unresolved.
        # `test_a_blocked_sprint_never_reaches_its_optional_review` is the
        # test that says so. The cycle stays on the state either way: it is
        # the evidence for whoever reads the failure. Only the re-plan below
        # clears it, because the next attempt needs a fresh one.
        return _escalate_to_a_human(
            state,
            error=an_unfinished_sprint(getattr(cycle, "sprint_goal", "?"), state.get("sprint_replan_count", 0),
                                       why, build_defect_report(cycle)),
            **{**base_update, **summary},
        )
    summary = _record_sprint_summary(state, "Failed", why)
    # Merged, not passed twice. `base_update` already carries
    # `remediation` and `test_round`, and naming them again beside
    # `**base_update` is a TypeError - "got multiple values for keyword
    # argument 'remediation'" - raised inside the node, which took the run
    # down on the one path that exists to rescue it.
    return _handing_on(
        **{**base_update, **summary, "remediation": None, "test_round": 0},
        stage="technical_lead",
        milestone_plan=None,
        specialist_outputs={},
        defect_cursor=0,
        sprint_replan_count=revision_count,
        sprint_best_history=best_history,
    )
