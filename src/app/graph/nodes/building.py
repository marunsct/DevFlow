"""A sprint's building: the technical lead's work orders and the specialists who carry them out.

    technical_lead -> specialist_dispatch -> ci_gate
        (or, in parallel mode, specialist_worker x N -> specialist_gather -> ci_gate)

See `app.graph.nodes` for how these are registered and why their helpers are
imported from `app.graph.workflow` when they run.
"""

from __future__ import annotations

import logging
import shlex
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.observability.degraded import degraded
from app.graph.context import GraphContext
from app.graph.workflow import WorkflowGraphState

#: The workflow's logger: the nodes log as they did inside the builder.
logger = logging.getLogger("app.graph.workflow")


def _the_specification_s_work_orders(state: Any, goal: str) -> Any:
    """Fast delivery's plan for the sprint, made from the specification; None for the lead."""
    from app.graph.workflow import _fast_delivery

    if not _fast_delivery():
        return None
    try:
        from app.graph import acceptance_nodes
        from app.graph.planned_work import work_orders_from_the_specification
        from app.stacks import contract

        root = state["repository"].root_path
        due = set(acceptance_nodes.criteria_due(state) or [])
        criteria = [
            f"{c.id}: {c.text}" for c in acceptance_nodes.suite.criteria(root) if not due or c.id in due
        ]
        unit = (contract.read(root) or {}).get("unit_test") or []
        # Quoted where an argument needs it: an argument holding a `;` joined with spaces read as a shell operator.
        return work_orders_from_the_specification(
            state.get("technical_specification"), goal, criteria, [shlex.join(map(str, unit))] if unit else [],
            root,
        )
    except Exception as error:  # noqa: BLE001 - the lead writes the plan
        degraded("work_orders_from_specification", error)
        return None


def _with_the_files_it_reads(state: Any, request: dict[str, Any], model: Any) -> dict[str, Any]:
    """The lead's request naming the files its memory holds numbered - the product's code and the sprint's due locked
    tests (`lead_files.for_the_plan`) - when today's request and memory would not show them all; as it is otherwise
    (`review_files.held_for_review`, the size gate of LF.1284). Never raises: `request` as it is."""
    try:
        from app.agents import lead_files, review_files
        from app.graph import acceptance_nodes

        root = state["repository"].root_path
        criteria = acceptance_nodes.suite.criteria(root)
        sprints = list(getattr(state.get("sprint_plan"), "sprints", None) or [])
        index = int(state.get("current_sprint_index") or 0)
        due = acceptance_nodes.criteria_due(state)
        due = [c.id for c in criteria] if due is None else due
        own = [str(i) for i in (getattr(sprints[index], "criteria", None) or [] if index < len(sprints) else [])
               if str(i) in due] or list(due)
        texts = [c.text for c in criteria if c.id in own]
        held = review_files.held_for_review(lead_files.for_the_plan(root, own, due, texts), root, model,
                                            "technical_lead", review_files.opening_of(request))
        return review_files.with_the_files_held(request, held, "technical_lead")
    except Exception as error:  # noqa: BLE001 - the lead reads for itself, as before
        degraded("lead_files_held", error)
        return request


def _the_advice_this_sprint_builds(state: Any) -> str:
    """The lead's section of the adopted advice the sprint plan places in this sprint, or "" (SP.2)."""
    from app.agents.advice_review import adopted_to_build, advice_for_the_lead, placed_in

    sprints = list(getattr(state.get("sprint_plan"), "sprints", None) or [])
    index = int(state.get("current_sprint_index") or 0)
    if not 0 <= index < len(sprints):
        return ""
    here = set(placed_in(sprints[index]))
    items = adopted_to_build(state.get("specialist_advice"), state.get("technical_specification"),
                             declined=dict(state.get("advice_declined") or {}))
    return advice_for_the_lead([line for line in items if line.split(":", 1)[0] in here])


def technical_lead_node(state: WorkflowGraphState, config: RunnableConfig, ctx: GraphContext) -> dict[str, Any]:
    from app.graph.workflow import (
        APP_RUN_ID_KEY, MAX_REMEDIATION_ATTEMPTS, _ASSIGNMENT_RETRIES, _READINESS_RETRIES,
        _UNTESTED_DECLINES, _a_dispute_is_due, _as_text, _carried_here, _carried_to_this_plan,
        _close_a_sprint_with_nothing_to_build, _hand_back, _handing_on, _max_structured_retries,
        _missing_upstream, _only_what_was_carried, _record_document, _record_the_owners, _run_gated_agent,
        _the_better_plan, _the_criteria_due, _the_fixes_to_keep, _the_last_failed_attempt_at_this_sprint,
        _the_later_sprints_brief, _what_a_plan_did, _what_this_sprint_builds,
        build_milestone_planning_request, build_milestone_revision_request, create_technical_lead_agent,
        render_document, start_remediation, unassigned_review_changes,
    )

    missing = _missing_upstream(state, "sprint_plan")
    if missing is not None:
        return missing
    agent = create_technical_lead_agent(model=ctx.planning_model, checkpointer=ctx.checkpointer, repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories)
    plan_text = _as_text(state.get("sprint_plan"))
    sprint_index = state.get("current_sprint_index", 0)
    sprints = state["sprint_plan"].sprints
    current_goal = sprints[sprint_index].goal if sprints and sprint_index < len(sprints) else ""

    # A failed attempt's locked tests are judged once before it is planned
    # again: one that no right product could pass goes back to QA. See
    # `app.agents.suite_dispute`.
    if _a_dispute_is_due(state):
        return _handing_on(stage="acceptance_dispute")

    # A sprint review that requested changes re-enters here. Reuse the
    # shared revision prompt so the lead sees its previous milestone plan
    # alongside the comments, rather than re-planning from scratch.
    # Blank comments are dropped before the truthiness test: `[""]` is a
    # truthy list, so a revision request carrying one empty string used to
    # send the lead down the revising branch with nothing to revise.
    revision_comments = [
        comment for comment in state.get("revision_comments", []) or [] if str(comment).strip()
    ]
    previous_milestone = state.get("milestone_plan")
    revising = bool(revision_comments) and previous_milestone is not None
    # Every criterion due already passes, but an earlier sprint carried work
    # here: the lead takes or declines each item, and a plan that takes none
    # closes the sprint. See `_only_what_was_carried`.
    nothing_else = "" if revising else str(state.get("nothing_left_but_carried") or "")
    if not revising and not nothing_else:
        from app.graph import acceptance_nodes as nothing_left

        why = nothing_left.sprint_already_done(state)
        if why:
            if not _carried_here(state):
                return _close_a_sprint_with_nothing_to_build(state, why)
            nothing_else = why
    if revising:
        request = build_milestone_revision_request(
            previous_milestone.model_dump_json(indent=2), revision_comments
        )
    else:
        request = build_milestone_planning_request(
            plan_text, current_goal, state["repository"].root_path,
            specification=state.get("technical_specification"),
            carried_forward=_carried_to_this_plan(state),
            lessons=state.get("lessons") or [],
            last_attempt=_the_last_failed_attempt_at_this_sprint(state),
        )
        # A seeded codebase's map, as it stands, so the plan builds on what exists (plan WS.7).
        from app.agents.code_map import with_the_map

        request = with_the_map(request, state["repository"].root_path)
        if _the_last_failed_attempt_at_this_sprint(state) is not None:
            # What the fixers of the last attempts tried on each cause, and how it ended (deep review 1.4): the cycle
            # that held it was cleared for this plan.
            from app.graph import cause_journal

            request["messages"][-1]["content"] += cause_journal.for_a_replan(
                state["repository"].root_path, state.get("current_sprint_index", 0))
        # The adopted specialist advice the sprint plan places in this sprint, whole (SP.2): the plan names only ids.
        request["messages"][-1]["content"] += _the_advice_this_sprint_builds(state)
    # The previous answer was not ready to hand out: say exactly why, with
    # the plan it was, so this attempt fixes it rather than starting over.
    from app.graph import acceptance_nodes

    due_brief = acceptance_nodes.criteria_brief(state)
    if due_brief:
        request["messages"][-1]["content"] += due_brief
    from app.agents.specification_rulings import with_the_rulings

    request = with_the_rulings(request, state["repository"].root_path)
    # A release held back hands on with no milestone plan, so the lead
    # plans afresh - and the planning request never read the comments:
    # a release held for a missing README or a credential in the code
    # cost two re-sprints that were told nothing. See `delivery.release`.
    if not revising and revision_comments and int(state.get("release_attempts") or 0) > 0:
        request["messages"][-1]["content"] += (
            "\n\nWhy the release was held back - the work this sprint must include:\n"
            + "\n".join(f"- {str(c).strip()}" for c in revision_comments[-3:])
        )
    # Recorded here too, not only when the builders start, so the lead's own
    # listing and snapshot tell a later sprint's tests from this one's.
    from app.agents.specialists import fixes_to_keep_section

    kept = fixes_to_keep_section(_the_fixes_to_keep(state))
    if kept:
        request["messages"][-1]["content"] += (
            "\n\n" + kept + "No work order undoes one of these, even to match the specification.\n"
        )
    later_brief = _the_later_sprints_brief(state)
    if later_brief:
        request["messages"][-1]["content"] += (
            "\n\n" + later_brief
            + "No work order builds what only those criteria need, even where this "
            "sprint's scope lists it: their sprint plans that work.\n"
        )
    if nothing_else:
        request["messages"][-1]["content"] += _only_what_was_carried(nothing_else)
    # What the harness set up and owns. Without it one run's lead wrote a
    # work order to edit the acceptance configuration, which the harness
    # put back - the whole work order wasted.
    from app.agents.specialists import project_contract

    owned = project_contract(state["repository"].root_path, with_reference_code=False)
    if owned:
        request["messages"][-1]["content"] += (
            "\n\n" + owned
            + "No work order may target a file the harness keeps or the locked acceptance "
            "suite; a change to either is put back."
        )
    unready = [str(p) for p in state.get("work_order_problems") or [] if str(p).strip()]
    if unready:
        from app.analysis.work_orders import readiness_feedback

        request["messages"][-1]["content"] += (
            readiness_feedback(unready)
            + (f"\n\nThe plan that was sent back:\n{state.get('unready_plan')}" if state.get("unready_plan") else "")
        )
    # Fast delivery: the work orders are made from the specification by the
    # harness, and held to the same definition of ready below. A plan sent
    # back is the lead's to write. See `app.graph.planned_work`.
    planned = (
        _the_specification_s_work_orders(state, current_goal)
        if not revising and not nothing_else and not unready and not state.get("pending_inner_thread_id")
        else None
    )
    if planned is not None:
        logger.info("Work orders made from the specification by the harness: %d", len(planned.delegated_tasks))
        # Fast delivery's own path makes no model call, so no event ever
        # carried stage="technical_lead" for it - the UI's sprint counter
        # (built by counting technical_lead visits, `runs.py`) silently
        # skipped the sprint this opened. One for the sprint that follows
        # wore its number instead: shown live, sprint 1 never had a
        # header, and the header that first appeared, over sprint 2's
        # planning, read "Sprint 1". Narrated the same way a deterministic
        # close already is (`models.call_gate._tell_the_run`), so the
        # stage is visible to anything built from the event stream.
        try:
            from app.server.agent_stream import AgentActivityStream

            AgentActivityStream(config["configurable"].get(APP_RUN_ID_KEY) or "", "technical_lead").publish_outcome(
                f"{len(planned.delegated_tasks)} work order(s) made from the specification; no planning call needed."
            )
        except Exception:  # noqa: BLE001 - narration is never load-bearing
            logger.debug("Could not narrate the harness-made work orders", exc_info=True)
        update = {"milestone_plan": planned, "stage": "specialist_dispatch", "pending_inner_thread_id": None}
    else:
        # The code and the sprint's locked tests held in its memory when today's request and memory do not show them
        # all (LF.1286).
        request = _with_the_files_it_reads(state, request, ctx.planning_model)
        update = _run_gated_agent(
            state,
            config,
            stage_name="technical_lead",
            agent=agent,
            initial_request=request,
            output_key="milestone_plan",
            next_stage="specialist_dispatch",
        )
    if _hand_back(update, "milestone_plan"):
        return update
    if not str(getattr(update["milestone_plan"], "selected_sprint_goal", "") or "").strip() and current_goal:
        update["milestone_plan"] = update["milestone_plan"].model_copy(update={"selected_sprint_goal": current_goal})
    if nothing_else and not list(getattr(update["milestone_plan"], "delegated_tasks", None) or []):
        decisions = [
            str(line) for line in getattr(update["milestone_plan"], "carried_forward_decisions", None) or []
            if str(line).strip()
        ]
        # Once: a lead that declines only because no test asks for the
        # item is asked again with that reason ruled out.
        from app.analysis.work_orders import declined_because_untested, untested_is_no_reason

        untested = declined_because_untested(decisions)
        carried = _carried_to_this_plan(state)
        # Silence is no decision either: one run's lead returned no work
        # orders and no decisions on eight carried items, and the sprint
        # closed as if it had declined them.
        unanswered = len(decisions) < len(carried)
        retries = dict(state.get("structured_retries") or {})
        asked = f"{_UNTESTED_DECLINES}:{state.get('current_sprint_index', 0)}"
        if (untested or unanswered) and not retries.get(asked):
            retries[asked] = 1
            problems = [untested_is_no_reason(untested)] if untested else []
            if unanswered:
                problems.append(
                    f"{len(carried)} item(s) were carried here and `carried_forward_decisions` "
                    f"records {len(decisions)}. Give one line per item: the work order that "
                    "takes it, or why it no longer holds."
                )
            logger.warning(
                "The lead answered %d of %d carried item(s), %d declined as untested; asking again",
                len(decisions), len(carried), len(untested),
            )
            return _handing_on(
                stage="technical_lead",
                structured_retries=retries,
                nothing_left_but_carried=nothing_else,
                work_order_problems=problems,
                unready_plan=update["milestone_plan"].model_dump_json(indent=2),
            )
        # The lead's decisions first: the record keeps the rationale's
        # first 1500 characters, and the suite's summary after them is long.
        return _close_a_sprint_with_nothing_to_build(
            state,
            "The lead took none of what earlier sprints carried here"
            + (": " + "; ".join(decisions) if decisions else ".")
            + "\n" + nothing_else,
        )
    # Only a readiness retry carries it on; a dispatched plan is a sprint's own.
    update["nothing_left_but_carried"] = None

    # Pinned before the readiness check, which checks each work order's files
    # against it. In parallel mode the specialists all start before a file
    # exists, and the directory was pinned by whichever wrote first. See
    # `pin_the_directory_a_plan_names`.
    try:
        from app.tools.repository import pin_the_directory_a_plan_names

        pin_the_directory_a_plan_names(
            state["repository"].root_path, update["milestone_plan"].model_dump_json()
        )
    except Exception:  # noqa: BLE001 - the first write still pins it
        logger.warning("Could not pin the project directory from the plan", exc_info=True)

    # The definition of ready: every work order complete enough for a
    # specialist who knows nothing but its brief. See `app.analysis.work_orders`.
    from app.analysis.work_orders import (
        readiness_problems,
        with_paths_inside_the_project,
        with_test_cases_from_its_criteria,
        with_the_project_directory_cd_dropped,
    )

    update["milestone_plan"] = with_test_cases_from_its_criteria(
        with_the_project_directory_cd_dropped(
            with_paths_inside_the_project(update["milestone_plan"], state["repository"].root_path),
            state["repository"].root_path,
        ),
        state.get("technical_specification"),
        _the_criteria_due(state),
    )
    if not revising:
        from app.analysis.work_orders import with_named_tests_given_to_testing
        from app.graph.drafting import planned_files

        update["milestone_plan"], given = with_named_tests_given_to_testing(
            update["milestone_plan"], state["repository"].root_path, _what_this_sprint_builds(state),
            planned_files(state.get("technical_specification")),
        )
        if given:
            logger.info("Test files the sprint names and no work order listed, given to testing: %s", ", ".join(given))
    # A testing order that writes nothing only runs the tests the round runs anyway (before a testing order is
    # added to a plan with none, so a plan is never left without one).
    from app.analysis.work_orders import with_run_only_testing_orders_left_to_the_test_round

    update["milestone_plan"], run_only = with_run_only_testing_orders_left_to_the_test_round(update["milestone_plan"])
    if run_only:
        logger.info("Testing work orders that write no file left to the test round: %s", "; ".join(run_only))
    from app.analysis.work_orders import with_a_testing_work_order

    update["milestone_plan"], added_testing = with_a_testing_work_order(
        update["milestone_plan"], state["repository"].root_path
    )
    if added_testing:
        logger.info("The plan had code and no testing work order; the harness added one")
        if not revising:
            # The test files the sprint names go to the order just added: measured on one run, they were given out
            # before it existed, nobody was given `test_cli.py`, and the plan was sent back for it.
            from app.analysis.work_orders import with_named_tests_given_to_testing
            from app.graph.drafting import planned_files

            update["milestone_plan"], given = with_named_tests_given_to_testing(
                update["milestone_plan"], state["repository"].root_path, _what_this_sprint_builds(state),
                planned_files(state.get("technical_specification")),
            )
            if given:
                logger.info("Test files the sprint names, given to the testing work order the harness added: %s",
                            ", ".join(given))
    # A unit test file is named where the project's runner collects it (LF.1263): measured, a work order put the
    # service's tests inside its package, where nothing ran them.
    from app.analysis.work_orders import with_tests_where_the_runner_collects

    update["milestone_plan"] = with_tests_where_the_runner_collects(update["milestone_plan"],
                                                                    state["repository"].root_path)
    # The harness's own repairs before the readiness check, not after it (HR2.P.1): 125 of 140 resends since 11-01
    # were for what these then fixed anyway - the locked suite's file on a work order (50), a command the sandbox
    # refuses (30). The check sees only what the harness cannot fix.
    from app.analysis.planned_commands import with_refused_commands_noted
    from app.analysis.work_orders import with_the_harness_s_files_left_out

    update["milestone_plan"] = with_the_harness_s_files_left_out(
        update["milestone_plan"], state["repository"].root_path
    )
    update["milestone_plan"] = with_refused_commands_noted(
        update["milestone_plan"], state["repository"].root_path
    )
    problems = readiness_problems(
        update["milestone_plan"],
        state["repository"].root_path,
        carried_forward=[] if revising else _carried_to_this_plan(state),
        # A revision answers the review's findings; the sprint's first plan
        # was the one held to the files its scope names, and those were
        # built - under the names that plan chose. One run's revision was
        # sent back twice for `pure-functions.mjs`, a name from the scope
        # the first plan had built as `app.mjs`.
        sprint_scope="" if revising else _what_this_sprint_builds(state),
        sprint_goals=[
            str(getattr(sprint, "goal", "") or "")
            for sprint in (getattr(state.get("sprint_plan"), "sprints", None) or [])
        ],
        sprint_index=state.get("current_sprint_index", 0),
    )
    if problems:
        retries = dict(state.get("structured_retries") or {})
        key = _READINESS_RETRIES
        attempted = retries.get(key, 0)
        best_plan, best_problems = _the_better_plan(
            (update["milestone_plan"], problems),
            (state.get("best_unready_plan") or "", list(state.get("best_unready_problems") or [])),
        )
        if attempted < _max_structured_retries():
            retries[key] = attempted + 1
            logger.warning(
                "Milestone plan is not ready to hand out (%d problem(s)); sending it "
                "back to the lead (attempt %d of %d): %s",
                len(problems), attempted + 2, _max_structured_retries() + 1,
                "; ".join(p[:80] for p in problems[:3]),
            )
            return _handing_on(
                stage="technical_lead",
                structured_retries=retries,
                revision_comments=revision_comments,
                nothing_left_but_carried=nothing_else or None,
                work_order_problems=problems,
                unready_plan=update["milestone_plan"].model_dump_json(indent=2),
                best_unready_plan=best_plan.model_dump_json(),
                best_unready_problems=best_problems,
            )
        if best_plan is not update["milestone_plan"]:
            logger.warning(
                "The last attempt was worse than an earlier one (%d problem(s) and "
                "%d work order(s), against %d and %d); dispatching the earlier plan",
                len(problems), len(update["milestone_plan"].delegated_tasks or []),
                len(best_problems), len(best_plan.delegated_tasks or []),
            )
            update["milestone_plan"], problems = best_plan, best_problems
            if not revising:
                # Kept from before: it gets the test files the scope names
                # as the plan just checked did. One run dispatched an
                # earlier plan that had never had them assigned.
                update["milestone_plan"], given = with_named_tests_given_to_testing(
                    update["milestone_plan"], state["repository"].root_path, _what_this_sprint_builds(state),
                    planned_files(state.get("technical_specification")),
                )
                if given:
                    problems = [p for p in problems if not p.startswith("The sprint's scope names")]
        logger.warning(
            "Milestone plan still not ready after %d attempts; dispatching it with "
            "the problems noted: %s", attempted + 1, "; ".join(p[:80] for p in problems[:3]),
        )
        plan = update["milestone_plan"]
        update["milestone_plan"] = plan.model_copy(update={
            "integration_notes": list(plan.integration_notes) + [
                f"Not ready when dispatched: {problem}" for problem in problems
            ]
        })
    update["work_order_problems"] = []
    update["unready_plan"] = ""
    update["best_unready_plan"] = ""
    update["best_unready_problems"] = []
    # A budget per plan, not per run. The success path clears the stage's
    # own key and nothing cleared this one, so sprint 1's three attempts
    # were still counted when sprint 2's plan arrived: measured on one run,
    # sprint 2's first unready plan was dispatched as "still not ready after
    # 3 attempts" without being sent back once.
    update["structured_retries"] = {
        key: count
        for key, count in (update.get("structured_retries", state.get("structured_retries")) or {}).items()
        if key != _READINESS_RETRIES
    }

    # A builder's work order goes to the role owning the domain most of its files are in (SK.1): measured, a backend
    # builder wrote the database models with none of the database specialist's guidance.
    from app.agents.domain_advice import with_roles_owning_their_domains

    update["milestone_plan"], moved = with_roles_owning_their_domains(update["milestone_plan"])
    if moved:
        logger.info("Work orders given to the role owning their files' domain: %s", "; ".join(moved))

    # A command the sandbox will refuse was noted on its work order before the readiness check (HR2.P.1).
    # And a command whose file another work order writes - see
    # `app.analysis.work_orders.with_borrowed_files_noted`.
    from app.analysis.work_orders import with_borrowed_files_noted

    update["milestone_plan"] = with_borrowed_files_noted(update["milestone_plan"])

    # Which stage owns each file the work orders list, so a specialist
    # writing another work order's file is told whose it is. A file two
    # work orders list has no single owner and is left open.
    _record_the_owners(
        state["repository"].root_path, list(getattr(update["milestone_plan"], "delegated_tasks", None) or []),
    )

    _record_document(
        state,
        "docs/milestone_plan.md",
        render_document("milestone_plan", o=update["milestone_plan"]),
    )

    milestone: MilestonePlanOutput = update["milestone_plan"]

    # A revision that assigns nothing is a revision that changes nothing.
    # The lead can satisfy "address every requested change" by writing it
    # into `integration_notes`, which no specialist is given - so the plan
    # reads as if the change were handled while the file stays untouched.
    unassigned = unassigned_review_changes(
        milestone, revising=revising, previous=previous_milestone
    )
    if unassigned:
        # Retry on a fresh conversation before giving up. Omitting the
        # assignments once is a lapse, not an inability - and failing the
        # whole run for it throws away every stage that came before. The
        # budget is shared with the structured-response retry because both
        # are the same remedy: abandon this conversation and ask again.
        retries = dict(state.get("structured_retries") or {})
        key = _ASSIGNMENT_RETRIES
        attempted = retries.get(key, 0)
        if attempted < _max_structured_retries():
            retries[key] = attempted + 1
            logger.warning(
                "Milestone revision assigned no task to the requested changes; "
                "re-planning on a fresh conversation (attempt %d of %d)",
                attempted + 2, _max_structured_retries() + 1,
            )
            return _handing_on(
                stage="technical_lead",
                structured_retries=retries,
                revision_comments=revision_comments,
            )
        return _handing_on(
            stage="failed",
            error=(
                f"{unassigned}\n\nThis was tried {attempted + 1} times, each on a "
                "fresh conversation."
            ),
        )

    # The same per-plan budget as the readiness retries above.
    update["structured_retries"] = {
        key: count
        for key, count in (update.get("structured_retries", state.get("structured_retries")) or {}).items()
        if key != _ASSIGNMENT_RETRIES
    }
    if revising and previous_milestone is not None:
        update["sprint_earlier_plans"] = [
            *(state.get("sprint_earlier_plans") or []),
            _what_a_plan_did(previous_milestone, state.get("remediation")),
        ]
    update["remediation"] = start_remediation(milestone.selected_sprint_goal, max_attempts=MAX_REMEDIATION_ATTEMPTS)
    update["specialist_task_index"] = 0
    # The parallel twin of the line above, and for the same reason: a plan
    # just stored has had no specialist run against it. Linear dispatch
    # counts through the tasks, so zeroing the counter is enough; the
    # parallel router instead subtracts the stage names that already produced
    # output, and a stage name is `specialist_{role}_{index}` - it carries no
    # plan identity. Leaving the previous plan's outputs in place therefore
    # told the router that this plan's tasks were done.
    #
    # Measured on one run, whose three plans produced the identical
    # names `specialist_ui_ux_0`, `specialist_backend_1`,
    # `specialist_testing_2`, because the lead assigns those roles in that
    # order every time. Sprint 1 ran all three; the two revisions the
    # milestone review asked for fanned out nothing and reached a test round
    # 174ms after the plan was stored. One of those plans was 16,959 output
    # tokens, and the work it described was eventually done by nine
    # `defect_fix` stages instead.
    #
    # Here rather than on the reviewer's `changes_required` edge, which is
    # where the omission was: its sibling `blocked` branch cleared this and
    # it did not. This is the one place every inbound path passes through.
    update["specialist_outputs"] = {}
    update["drafted_for_plan"] = False
    update["revision_comments"] = []
    # A plan's builders are sent back for unfinished work at most once each way (`unfinished_build`).
    update["unfinished_orders"] = {}
    update["builders_sent_back"] = []
    # And the changes its testing stages were refused, kept as their blockers (`testing_blockers`, LF.1310).
    from app.tools import testing_blockers

    testing_blockers.forget(state["repository"].root_path)
    return update


def _drafted_from_the_specification(state: Any, config: RunnableConfig, ctx: GraphContext) -> dict[str, Any] | None:
    """Fast delivery's build step, once per milestone plan; None when it does not apply.

    Writes each work order's files from the specification (`app.graph.drafting`)
    and records the work orders it completed; the rest go to the agent loop
    as before. Only for a run that approves its own writes: these writes are
    not put to a person.
    """
    from app.graph.workflow import (
        APP_RUN_ID_KEY, MOST_DIAGNOSTICS_FOR_A_PASS, _diagnostics_in_files_touched,
        _the_run_approves_its_own_writes, concurrent_requests,
    )

    from app import delivery

    if state.get("drafted_for_plan") or not delivery.fast():
        return None
    if state.get("pending_inner_thread_id") or state.get("specialist_outputs"):
        return None
    run_id = config["configurable"].get(APP_RUN_ID_KEY)
    specification = state.get("technical_specification")
    if specification is None or not _the_run_approves_its_own_writes(run_id):
        return {"drafted_for_plan": True, "stage": "specialist_dispatch"}
    from app.graph.drafting import draft_work_orders, in_work_orders_of_at_most, with_tests_the_specification_plans

    milestone = state.get("milestone_plan")
    if milestone is None:
        return None
    tasks, dropped = with_tests_the_specification_plans(list(milestone.delegated_tasks), specification)
    if dropped:
        logger.info(
            "Fast delivery: %d test file(s) the specification does not plan left out: %s",
            len(dropped), ", ".join(dropped[:6]),
        )
    tasks, split = in_work_orders_of_at_most(tasks)
    if split:
        logger.info("Fast delivery: %d work order(s) of more than three files split into parts", split)
    from app.graph.best_attempt import files_the_best_attempt_already_has

    kept = files_the_best_attempt_already_has(
        state["repository"].root_path,
        [str(path) for task in tasks for path in (getattr(task, "files", None) or [])],
        replans=int(state.get("sprint_replan_count") or 0),
    )
    drafted = draft_work_orders(
        tasks, specification, getattr(state.get("stack_selection"), "technology_stack", None),
        state["repository"].root_path, ctx.the_build_model(state, "drafting"), workers=concurrent_requests(),
        # The compiler's word on each draft, at once. See `drafting._repaired_where_the_compiler_says`.
        diagnose=lambda files: _diagnostics_in_files_touched(
            state, {"messages": []}, __import__("types").SimpleNamespace(changed_files=files), "drafting",
            most=MOST_DIAGNOSTICS_FOR_A_PASS,
        ),
        kept=kept,
        # The adopted advice of each file's domain (SK.1).
        advice=state.get("specialist_advice"),
    )
    outputs = {
        f"specialist_{tasks[index].specialist_role}_{index}": output for index, output in drafted.items()
    }
    update: dict[str, Any] = {"drafted_for_plan": True, "stage": "specialist_dispatch"}
    if outputs:
        update["specialist_outputs"] = outputs
    if dropped or split:
        update["milestone_plan"] = milestone.model_copy(update={"delegated_tasks": tasks})
    return update


def _on_to_the_ci_gate(state: Any, **fields: Any) -> dict[str, Any]:
    """Every builder has finished: on to CI, unless a work order is not finished - then back to its builder, once
    an attempt, before any test runs (`app.graph.unfinished_build`, LF.1299) - or a testing stage was refused a
    change in a builder's files - then that builder is sent it, once an attempt (`app.tools.testing_blockers`,
    LF.1310)."""
    from app.graph import unfinished_build
    from app.tools import testing_blockers
    from app.graph.workflow import _handing_on

    sent = testing_blockers.joined(unfinished_build.after_the_build(state), testing_blockers.to_their_builders(state))
    if sent:
        return _handing_on(**{**fields, **sent, "specialist_task_index": 0}, stage="specialist_dispatch")
    return _handing_on(**fields, stage="ci_gate")


def _built_before_the_testing_fan_out(state: Any) -> dict[str, Any]:
    """In parallel mode, when only testing work orders are left: the update that sends the builders of a product that
    does not build back first, or marks that the testing work orders start on it; {} otherwise (PA.3)."""
    from app.graph import built_before_testing
    from app.graph.workflow import _specialist_stage_name, _tasks_without_an_output

    left = [_specialist_stage_name(task, index) for index, task in _tasks_without_an_output(state)]
    if not left or not all(built_before_testing.is_a_testing_work_order(stage) for stage in left):
        return {}
    return built_before_testing.before_the_testing_work_order(state, left[0]) or {}


def specialist_dispatch_node(state: WorkflowGraphState, config: RunnableConfig, ctx: GraphContext) -> dict[str, Any]:
    from app.graph.workflow import (
        _handing_on, _missing_upstream, _record_the_owners, _run_gated_agent, _the_fixes_to_keep,
        _the_interface_design_for, _the_later_sprints_brief, build_specialist_task_request,
        create_specialist_agent, specification_for_the_work_order, with_the_facts,
    )

    missing = _missing_upstream(state, "milestone_plan")
    if missing is not None:
        return missing
    drafted = _drafted_from_the_specification(state, config, ctx)
    if drafted is not None:
        if "milestone_plan" in drafted or drafted.get("specialist_outputs"):
            # Split into parts: the owners are the parts'; and the orders drafted whole own nothing.
            plan = drafted.get("milestone_plan") or state.get("milestone_plan")
            _record_the_owners(state["repository"].root_path, list(getattr(plan, "delegated_tasks", None) or []),
                               done=(drafted.get("specialist_outputs") or {}))
        return drafted
    # On every dispatch, from the plan as it stands: a run resumed on a
    # plan whose table an earlier version recorded is put right here.
    _record_the_owners(
        state["repository"].root_path, list(getattr(state.get("milestone_plan"), "delegated_tasks", None) or []),
        done=(state.get("specialist_outputs") or {}),
    )

    # `effective_settings`, not `load_settings`. `load_settings` is a pure
    # function of the environment it is handed, and bare it reads this
    # container's own - which never carries anything an administrator
    # changed. The settings page writes `execution_mode` to the store, and
    # the store is layered in by `effective_environment`; without that step
    # the toggle saved correctly, displayed correctly and was read as
    # `linear` on every dispatch. `_effective_base_environment` is the same
    # source the model overrides above are layered on.
    from app.server.runtime_settings import effective_settings

    try:
        settings = effective_settings()
    except Exception:  # noqa: BLE001 - an unreachable store is the deployed config
        from app.config import load_settings

        logger.warning("Could not read the settings store; dispatching linearly", exc_info=True)
        settings = load_settings()
    if settings.execution_mode == "parallel":
        # A stage no node is named after. `_route_from_stage` turns it into
        # one `Send` per unfinished task; `specialist_gather` joins them.
        # The product builds before a testing work order starts (PA.3).
        return {**_built_before_the_testing_fan_out(state), "stage": "specialist_dispatch_parallel"}

    milestone = state["milestone_plan"]
    tasks = milestone.delegated_tasks
    index = state.get("specialist_task_index", 0)
    # A work order drafted from the specification is done already; one sent back unfinished is not.
    from app.graph import unfinished_build

    done = state.get("specialist_outputs") or {}
    sent_back = unfinished_build.pending(state)
    while (index < len(tasks) and f"specialist_{tasks[index].specialist_role}_{index}" in done
           and f"specialist_{tasks[index].specialist_role}_{index}" not in sent_back):
        index += 1
    if index >= len(tasks) and index != state.get("specialist_task_index", 0):
        return _on_to_the_ci_gate(state, specialist_task_index=index)

    # The product builds before a testing work order starts; a failure goes to its builders first (PA.3).
    from app.graph import built_before_testing

    went_on: dict[str, Any] = {}
    if index < len(tasks):
        before = built_before_testing.before_the_testing_work_order(state, f"specialist_{tasks[index].specialist_role}_{index}")
        if before and before.get("unfinished_orders"):
            return _handing_on(**before, specialist_task_index=0, stage="specialist_dispatch")
        went_on = before or {}

    if index < len(tasks):
        task = tasks[index]
        stage_name = f"specialist_{task.specialist_role}_{index}"
        agent = create_specialist_agent(
            task.specialist_role, model=ctx.the_build_model(state, stage_name), checkpointer=ctx.checkpointer, repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories
        )
        selection = state.get("stack_selection")
        request = build_specialist_task_request(
            task.task_description,
            task.acceptance_criteria,
            state["repository"].root_path,
            getattr(selection, "technology_stack", None),
            # The sibling tasks, so a specialist sharing a file with another
            # is told before it rewrites the file wholesale.
            other_tasks=tasks,
            work_order=task,
            interface_design=_the_interface_design_for(state, task),
            later_sprints_brief=_the_later_sprints_brief(state),
            earlier_fixes=_the_fixes_to_keep(state, task),
            specification_detail=specification_for_the_work_order(state.get("technical_specification"), task),
        )
        # The facts the work is built and judged under (plan CM.1).
        request = with_the_facts(request, state["repository"].root_path, built=False)
        # The adopted advice of the domains its files are in, and their guidance (SK.1); a craft checklist (SK.2).
        from app.agents import domain_advice, domain_craft

        request = domain_craft.with_it(domain_advice.with_it(request, state, task), state, task)
        # And what the work orders before it reported about its files (plan CM.3).
        from app.agents import ledger

        request = ledger.with_the_reports(request, done, task, tasks, leave_out=stage_name)
        # Where the sprint stands, from what the harness measured (plan PH.1, off until measured).
        from app.agents import where_things_stand

        request = where_things_stand.with_it(request, state, leave_out=stage_name)
        # Its files' neighbours in the code graph (plan CG.3, off until measured).
        from app.analysis import project_graph

        request = project_graph.with_the_slice(request, state["repository"].root_path, getattr(task, "files", None) or [])
        # What its work order still lacked when it was sent back (LF.1299).
        request = unfinished_build.with_what_is_missing(request, state, stage_name)
        update = _run_gated_agent(
            state,
            config,
            stage_name=stage_name,
            agent=agent,
            initial_request=request,
            output_key="__specialist_result__",
            next_stage="specialist_dispatch",
        )
        if "__specialist_result__" not in update:
            return {**update, **went_on}  # paused waiting for approval on this task

        outputs = dict(state.get("specialist_outputs", {}))
        # The interfaces it changed, read by the harness (plan PH.3, off until measured).
        from app.agents import interface_changes

        from app.tools import testing_blockers

        outputs[stage_name], built = unfinished_build.built_again(state, stage_name, testing_blockers.with_them(
            interface_changes.with_them(update.pop("__specialist_result__"), state["repository"].root_path),
            state["repository"].root_path, stage_name))
        update.update(built)
        update.update(went_on)
        update["specialist_outputs"] = outputs
        update["specialist_task_index"] = index + 1
        return update

    # Every delegated task is done, so the increment is built. CI and a
    # code review read it first (`app.graph.engineering`); verification is
    # then its own stage (Step 5.4): the Test Engineer runs the tests and
    # turns failures into tracked, owned defects.
    return _on_to_the_ci_gate(state)


def specialist_worker_node(state: dict, config: RunnableConfig, ctx: GraphContext) -> dict[str, Any]:
    """Worker node for executing a single specialist task in parallel mode."""
    from app.graph.workflow import (
        _as_a_queued_pause, _only_this_worker_s_pause, _run_gated_agent, _specialist_stage_name,
        _the_fixes_to_keep, _the_interface_design_for, _the_later_sprints_brief,
        build_specialist_task_request, create_specialist_agent, specification_for_the_work_order,
        with_the_facts,
    )

    task = state["__worker_task"]
    index = state["__worker_index"]
    stage_name = _specialist_stage_name(task, index)

    # `dict(state)`, with no `cast`: `cast` was never imported, so the first
    # parallel worker to run raised `NameError` before it reached its agent.
    # The annotation it was borrowing is not needed - this dictionary is
    # handed to helpers that read it with `.get`.
    temp_state: Any = dict(state)

    agent = create_specialist_agent(
        task.specialist_role, model=ctx.the_build_model(state, stage_name), checkpointer=ctx.checkpointer, repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories
    )
    selection = state.get("stack_selection")
    request = build_specialist_task_request(
        task.task_description,
        task.acceptance_criteria,
        state["repository"].root_path,
        getattr(selection, "technology_stack", None),
        # The sibling tasks, from the plan rather than a local list: this node
        # is handed one task at a time. Wiring only the linear site left this
        # one without them, and this is the parallel site - the mode where
        # specialists really do run at once, so the one where a file two tasks
        # share matters most. Measured on one run, whose plan named
        # `app.js` in four of six tasks and whose `app.js` was written by five
        # stages, with no brief mentioning the overlap.
        other_tasks=list(
            getattr(state.get("milestone_plan"), "delegated_tasks", None) or ()
        ),
        work_order=task,
        interface_design=_the_interface_design_for(state, task),
        later_sprints_brief=_the_later_sprints_brief(state),
        earlier_fixes=_the_fixes_to_keep(state, task),
        specification_detail=specification_for_the_work_order(state.get("technical_specification"), task),
    )
    # The facts the work is built and judged under (plan CM.1).
    request = with_the_facts(request, state["repository"].root_path, built=False)
    # The adopted advice of the domains its files are in, and their guidance (SK.1); a craft checklist (SK.2).
    from app.agents import domain_advice, domain_craft

    request = domain_craft.with_it(domain_advice.with_it(request, state, task), state, task)
    # What the work orders finished before it reported about its files (plan CM.3), as the linear builder gives:
    # found in the launch review, the parallel site left it out, although a deferred work order sharing a file
    # runs after the one it shares it with.
    from app.agents import ledger

    request = ledger.with_the_reports(
        request, state.get("specialist_outputs") or {}, task,
        list(getattr(state.get("milestone_plan"), "delegated_tasks", None) or ()), leave_out=stage_name)
    # Where the sprint stands, and the work order's slice of the code graph
    # (plans PH.1, CG.3; off until measured).
    from app.agents import where_things_stand
    from app.analysis import project_graph

    request = where_things_stand.with_it(request, state, leave_out=stage_name)
    request = project_graph.with_the_slice(request, state["repository"].root_path, getattr(task, "files", None) or [])
    # What its work order still lacked when it was sent back (LF.1299).
    from app.graph import unfinished_build

    request = unfinished_build.with_what_is_missing(request, state, stage_name)

    # A worker may only answer its *own* approval gate.
    #
    # `pending_decision` and `pending_inner_thread_id` are single fields, and
    # every worker in the superstep is handed a copy of the one state that
    # holds them. On a resume the dispatcher re-sends every task that has no
    # output yet, so without this each of those workers resumed whichever
    # inner thread happened to be stored there - a sibling's - and executed
    # the gated call that was waiting on it.
    #
    # Measured on one run: one `call_id` recorded three times under
    # three stage names, with three `tool_result` records microseconds apart,
    # one reporting `"status": "edited"` and the other two "already contains
    # the text you asked to put there". Every call that was multiplied was a
    # gated one - write_artifact 4, replace_lines 5, edit_artifact 3,
    # run_terminal_command 2 - and every ungated one ran exactly once, which
    # is the signature of the shared field rather than of three models
    # choosing the same call in the same second. `run_terminal_command` in
    # that list means the shell commands ran three times too.
    #
    # The cost was not only the duplicate work. The repeated-read tally is
    # per stage, and three executions raised it three times each, so the
    # read refusals and the withholding rungs fired at a third of the
    # repetition they are meant to describe.
    temp_state.update(_only_this_worker_s_pause(state, stage_name))

    update = _run_gated_agent(
        temp_state,
        config,
        stage_name=stage_name,
        agent=agent,
        initial_request=request,
        output_key="__specialist_result__",
        next_stage="specialist_dispatch", # doesn't matter for the map-reduce worker
    )

    answered_in_a_batch = bool((state.get("queued_decisions") or {}).get(stage_name))
    if "__specialist_result__" not in update:
        # Paused, waiting on a human for one of this task's writes. The pause
        # is recorded rather than returned: a pause update carries `stage`,
        # and `stage` has no reducer, so two workers pausing in one superstep
        # is `InvalidUpdateError: Can receive only one value per step` - the
        # fan-out dying instead of pausing. `specialist_gather` reads these
        # and surfaces them one at a time.
        return {"specialist_pauses": {stage_name: _as_a_queued_pause(
            state, stage_name, update, answered=answered_in_a_batch
        )}}

    # One key of a merged dictionary, so every worker's result survives the
    # superstep. Returning `stage` here instead is what made the fan-out
    # loop: the dispatcher left `stage` as `specialist_dispatch_parallel`,
    # the worker did not change it, and the router fanned the same tasks out
    # again on every pass until the recursion limit ended the run.
    from app.agents import interface_changes

    from app.tools import testing_blockers

    output, built = unfinished_build.built_again(state, stage_name, testing_blockers.with_them(
        interface_changes.with_them(update["__specialist_result__"], state["repository"].root_path),
        state["repository"].root_path, stage_name))
    finished: dict[str, Any] = {"specialist_outputs": {stage_name: output}, **built}
    if answered_in_a_batch:
        # Its pause was answered in a batch and never surfaced, so its queue
        # entry is still there; left, `specialist_gather` would surface a
        # pause for a task that has finished.
        finished["specialist_pauses"] = {stage_name: None}
    return finished


def specialist_gather_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:  # noqa: ARG001
    """Where the parallel fan-out joins, and the only writer of `stage` in it.

    Every worker converges here by a static edge, so this runs once after
    the whole fan-out regardless of how many tasks there were - which is
    what makes it safe to set `stage` at all.

    A worker that paused left its pause here instead of on `stage`. They are
    surfaced one at a time, the longest-waiting first (`_the_pause_to_surface`): the run pauses, a human
    answers, the dispatcher re-derives the fan-out, and the tasks that
    already have outputs are not re-sent. Several pauses therefore drain one
    after another rather than racing each other for one `stage` value.
    """
    from app.graph.workflow import (
        _QUEUED_AT, _queued_pauses, _tasks_without_an_output, _the_pause_to_surface,
    )

    pauses = _queued_pauses(state)
    if pauses:
        first = _the_pause_to_surface(pauses)
        # The pause update verbatim - not through `_handing_on`, which clears
        # exactly the pause fields this has to carry.
        #
        # Only the surfaced pause is drained. Emptying the whole queue threw
        # away the other workers' paused inner threads, and because
        # `pending_inner_thread_id` is a single field they then resumed the
        # surfaced stage's thread instead of their own and re-ran its gated
        # call - see `specialist_worker_node`. `_merge_or_reset` merges, so a
        # subset cannot remove a key and an empty dict would reset the lot;
        # one key set to `None` says "this one is answered" and leaves the
        # rest queued for the supersteps after it.
        surfaced = {key: value for key, value in pauses[first].items() if key != _QUEUED_AT}
        return {**surfaced, "specialist_pauses": {first: None}, "queued_decisions": {}}

    # Nothing is paused. A task the fan-out held back because it shares a
    # file with one that was running has not been dispatched yet, and this
    # is its next pass - `_that_do_not_share_a_file` promises one. Handing on
    # to the tests here skipped it: the deferred task was only ever run
    # because the resume path used to send the whole pending set at the
    # first approval, which also switched the staggering off. Now that a
    # resume staggers too, this is the only way a deferred task gets its
    # turn.
    #
    # No pause is outstanding at this point - any worker that paused in
    # this superstep left an entry in the queue above - so the decision and
    # thread from the last surfaced pause belong to a stage that has since
    # finished, and are cleared rather than carried into a fresh dispatch.
    if _tasks_without_an_output(state):
        return {
            # The product builds before a testing work order starts (PA.3).
            **_built_before_the_testing_fan_out(state),
            "stage": "specialist_dispatch_parallel",
            "pending_decision": None,
            "pending_inner_thread_id": None,
            "pending_approval": None,
            "queued_decisions": {},
        }
    return _on_to_the_ci_gate(state, specialist_pauses={}, queued_decisions={})
