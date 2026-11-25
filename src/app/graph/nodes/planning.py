"""From the brief to the sprint plan: intake, tools, the stack, the specialists' advice and the sprints.

    product_manager -> tools_models -> stack_selector -> specialist_consultation
        -> (principal_architect ... acceptance) -> scrum_master

See `app.graph.nodes` for how these are registered and why their helpers are
imported from `app.graph.workflow` when they run.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.graph.context import GraphContext
from app.graph.workflow import WorkflowGraphState

#: The workflow's logger: the nodes log as they did inside the builder.
logger = logging.getLogger("app.graph.workflow")


def product_manager_node(state: WorkflowGraphState, config: RunnableConfig, ctx: GraphContext) -> dict[str, Any]:
    from app.graph.workflow import (
        PRODUCT_INTAKE_REVIEW, _hand_back, _record_document, _review_enabled, _run_gated_agent,
        build_intake_request, create_product_manager_agent, render_document,
        with_the_constraints_the_brief_states, with_the_measures_the_brief_states,
        with_the_workflows_its_measures_require, with_what_the_brief_requires_marked_in_deferred_scope,
    )

    agent = create_product_manager_agent(model=ctx.planning_model, checkpointer=ctx.checkpointer, repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories)
    request = build_intake_request(state["document"], state["repository"])
    # Each open question with the answer it assumes (plan IN.1, off until measured).
    from app.agents import assumptions

    request = assumptions.with_the_rule(request)
    # A seeded codebase's map, built from its files, so the intake knows what exists (plan WS.7).
    from app.agents.code_map import with_the_map

    request = with_the_map(request, state["repository"].root_path)
    # What products of this kind commonly offer, as cited suggestions: only with its switch and this run's consent
    # (plan HK.10); otherwise the request is as it was.
    from app.agents import product_research

    request = product_research.with_the_note(request, state, ctx.planning_model)
    update = _run_gated_agent(
        state,
        config,
        stage_name="product_manager",
        agent=agent,
        initial_request=request,
        output_key="product_intake",
        next_stage="tools_models",
    )
    if _hand_back(update, "product_intake"):
        return update

    # A suggestion from that research stays a suggestion, recorded as taken or left, before the brief's guards below.
    product_research.settled(state, update)
    # The brief's own constraints, put back before anything is rendered
    # from this. Every later stage reads the intake; none reads the brief.
    update["product_intake"] = with_the_constraints_the_brief_states(
        update["product_intake"], getattr(state.get("document"), "text", "") or ""
    )
    # Its acceptance criteria too, in the brief's words: the measures are
    # what every later stage checks itself against.
    update["product_intake"] = with_the_measures_the_brief_states(
        update["product_intake"], getattr(state.get("document"), "text", "") or ""
    )
    # And no contradiction between its own lists: a capability a success
    # measure names is a workflow, whatever the workflow list left out,
    # and a deferral that touches what the brief requires says so.
    update["product_intake"] = with_the_workflows_its_measures_require(update["product_intake"])
    update["product_intake"] = with_what_the_brief_requires_marked_in_deferred_scope(
        update["product_intake"], getattr(state.get("document"), "text", "") or ""
    )

    _record_document(
        state,
        "docs/product_intake.md",
        render_document("product_intake", o=update["product_intake"]),
    )
    assumptions.record(state, update)
    # The project directory, named once from the product, so no stage has
    # to derive it and none looks for it before it exists.
    from app.tools.repository import pin_the_directory_the_product_names

    pin_the_directory_the_product_names(
        state["repository"].root_path, getattr(update["product_intake"], "product_name", "")
    )
    # A product seeded at the root has just moved there: a reader of the decisions sees it.
    from app.stacks.seeded_product import record_the_move

    record_the_move(state, update)

    # After product manager finishes, optionally route to review
    # Or, with `INTAKE_ASKS_FIRST`, when the intake has questions and a person answers this run (deep review C8).
    from app.graph.workflow import APP_RUN_ID_KEY

    waits = assumptions.waits_for_answers(
        getattr(update["product_intake"], "open_questions", None),
        assumptions.asking() and assumptions.a_person_answers(config["configurable"].get(APP_RUN_ID_KEY)),
    )
    next_stage = ("user_review_product_intake" if _review_enabled(state, PRODUCT_INTAKE_REVIEW) or waits
                  else "tools_models")
    update["stage"] = next_stage
    return update


def tools_models_node(state: WorkflowGraphState, config: RunnableConfig, ctx: GraphContext) -> dict[str, Any]:
    from app.graph.workflow import (
        _hand_back, _handing_on, _max_structured_retries, _record_document, _run_gated_agent,
        build_tools_models_request, create_tools_models_agent, render_document,
    )

    agent = create_tools_models_agent(model=ctx.planning_model, checkpointer=ctx.checkpointer, repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories)
    intake = state.get("product_intake")
    if intake is None:
        # Send it back to the stage that owes the output, on a fresh
        # conversation, rather than failing here. Resuming re-enters *this*
        # node, where the intake is still missing - so telling the operator
        # to resume, as the first version of this guard did, was advice that
        # could not work. Measured on one run: resumed once, failed
        # again in the same place.
        retries = dict(state.get("structured_retries") or {})
        key = "product_manager:intake"
        attempted = retries.get(key, 0)
        if attempted < _max_structured_retries():
            retries[key] = attempted + 1
            return _handing_on(stage="product_manager", structured_retries=retries)
        # The stage before this one finished without returning its
        # structured response - on one run the product manager wrote
        # `docs/product_intake.md`, then reported "Product intake complete.
        # Here is the structured summary:" as prose. Reading the key
        # directly turned that into `KeyError: 'product_intake'` from deep
        # inside LangGraph, which says nothing about which stage failed or
        # what to do. Every sibling condition in this module returns a
        # recoverable error instead.
        return _handing_on(
            stage="failed",
            error=(
                "The product manager finished without returning its structured "
                "response, so there is no product intake for the next stage to "
                f"read. It was re-run {attempted} time(s) on a fresh conversation "
                "and did the same thing each time. Its document may still be in "
                "docs/. A model that writes the answer as prose instead of "
                "returning it through the response schema usually needs its "
                "reasoning settings checked - see Settings."
            ),
        )
    intake_text = (
        intake.model_dump_json(indent=2)
        if hasattr(intake, "model_dump_json")
        else json.dumps(intake, indent=2)
    )
    request = build_tools_models_request(intake_text, state["repository"])
    update = _run_gated_agent(
        state,
        config,
        stage_name="tools_models",
        agent=agent,
        initial_request=request,
        output_key="tools_models",
        next_stage="stack_selector",
    )
    if not _hand_back(update, "tools_models"):
        _record_document(
            state,
            "docs/tools_and_models.md",
            render_document("tools_and_models", o=update["tools_models"]),
        )
        # Pin every language the stack names, so the sandbox can open the
        # right toolchain to every role that writes code. The allowlist
        # cannot ask this stage directly - it is handed a role name and a
        # workspace - so the decision is recorded in the workspace the way
        # the project directory already is.
        #
        # Every field, not just `language`. A full-stack product names a
        # backend language and a frontend framework, and passing only the
        # first pinned `go` for a Go/TypeScript product - leaving every
        # role without `tsc`. `frontend_framework` was filled by the stack
        # selector, shown to specialists in prose, and reached no
        # allowlist, no timeout and no analyser.
        try:
            from app.tools.sandbox import pin_project_stack

            stack = getattr(update["tools_models"], "technology_stack", None)
            named = [
                str(getattr(stack, field, "") or "")
                for field in ("language", "frontend_framework", "framework")
            ] if stack else []
            if any(named):
                pin_project_stack(state["repository"].root_path, *named)
        except Exception:  # noqa: BLE001 - a run must not fail over a pin
            logger.warning("Could not pin the project stack", exc_info=True)
    return update


def stack_selector_node(state: WorkflowGraphState, config: RunnableConfig, ctx: GraphContext) -> dict[str, Any]:
    from app.graph.workflow import (
        _hand_back, _record_document, _run_gated_agent, _the_stack_pack_for, create_stack_selector_agent,
        render_document, the_browser_runner_this_stack_forgot, the_rationale_for_the_corrected_runner,
    )

    agent = create_stack_selector_agent(model=ctx.planning_model, checkpointer=ctx.checkpointer, repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories)
    # The brief's own constraints, quoted, not a model's summary of them.
    # This stage was given `product_intake` and `tools_models` and nothing
    # else, and on one run `ProductManagerOutput.constraints` came
    # back empty - so "No external dependencies beyond basic HTML/CSS/JS"
    # never reached the stage that picked Express. See
    # `app.agents.brief_constraints`.
    from app.agents.brief_constraints import constraints_note
    from app.stacks import supported_stacks_note

    document = state.get("document")
    constraints = constraints_note(getattr(document, "text", "") or "")
    # The toolchains this environment runs, so a library is chosen whose current release runs here (HK.1).
    from app.stacks.stack_facts import toolchains_section
    # Each candidate's current release, support window, open advisories, fit and pack, read first (HK.8).
    from app.stacks.stack_evidence import for_the_selector

    evidence = for_the_selector(state.get("tools_models"), state["repository"].root_path)
    request = {
        "messages": [
            {
                "role": "user",
                "content": (
                    f"{constraints}"
                    f"{supported_stacks_note()}"
                    f"{toolchains_section()}"
                    f"{evidence}"
                    f"Product Intake: {state['product_intake']}\n"
                    f"Tools: {state.get('tools_models')}"
                ),
            }
        ]
    }
    # The stack of a seeded codebase is the one its files are written in: the map says which (plan WS.7).
    from app.agents.code_map import with_the_map

    request = with_the_map(request, state["repository"].root_path)
    # What products of this kind commonly offer, as cited suggestions: only with its switch and this run's consent
    # (plan HK.10); otherwise the request is as it was.
    from app.agents import product_research

    request = product_research.with_the_note(request, state, ctx.planning_model)
    update = _run_gated_agent(
        state,
        config,
        stage_name="stack_selector",
        agent=agent,
        initial_request=request,
        output_key="stack_selection",
        next_stage="specialist_consultation",
    )
    if _hand_back(update, "stack_selection"):
        return update

    # The prompt tells this stage, in capitals, that a product with a user
    # interface needs both a logic runner and a browser runner and must name
    # both. One run named only `node --test`, for a brief asking for a
    # "web-based interface with HTML/CSS/JavaScript", and justified it with
    # "manual browser verification" - which the same prompt calls impossible
    # twice, there being no display and nobody to look at one. Its
    # specialists installed Playwright anyway, correctly, and the stack
    # document then disagreed with the product: a package the stack did not
    # name is a blocking finding. Enforced here because saying it was not
    # enough, and because the corrected value is derivable from the answer
    # the stage just gave.
    chosen = update.get("stack_selection")
    stack = getattr(chosen, "technology_stack", None)
    corrected = the_browser_runner_this_stack_forgot(stack)
    if corrected is not None:
        logger.warning(
            "Stack selection named '%s' for a product that runs in a "
            "browser; recording '%s' so the stack matches what the "
            "environment provides",
            getattr(stack, "testing_framework", ""), corrected,
        )
        update["stack_selection"] = chosen.model_copy(
            update={
                "technology_stack": stack.model_copy(
                    update={"testing_framework": corrected}
                ),
                # The prose with it, or the document argues against its
                # own field. See `the_rationale_for_the_corrected_runner`.
                "rationale": the_rationale_for_the_corrected_runner(
                    getattr(chosen, "rationale", ""), corrected
                ),
            }
        )

    # Rendered from the decision, like every other document the workflow
    # keeps. On one run this stage still wrote its own: it printed the
    # selection into the conversation, wrote `docs/technology_stack.md`,
    # printed it again, wrote again - five identical writes, and the repeat
    # guard ended the run at stage three. The same shape had already cost
    # earlier runs their technical lead and their architecture reviewer,
    # in the one stage that had not been converted.
    update.update(_the_stack_pack_for(state, update))
    _record_document(
        state,
        "docs/technology_stack.md",
        render_document("technology_stack", o=update["stack_selection"]),
    )
    return update


def specialist_consultation_node(state: WorkflowGraphState, config: RunnableConfig, ctx: GraphContext) -> dict[str, Any]:
    """Ask each specialist this product needs for advice, one per entry. See `app.agents.specialist_advice`."""
    from app.graph.workflow import (
        _as_text, _fast_delivery, _hand_back, _handing_on, _run_gated_agent,
        create_specialist_advice_agent,
    )

    from app.agents import domain_craft
    from app.agents.specialist_advice import advice_from, build_advice_request, roles_to_consult
    from app.stacks import framework_guidance

    brief = getattr(state.get("document"), "text", "") or ""
    roles = list(state.get("consultation_roles") or roles_to_consult(
        getattr(state.get("stack_selection"), "technology_stack", None), brief
    ))
    advice = dict(state.get("specialist_advice") or {})
    pending = [role for role in roles if role not in advice]
    if not pending:
        return _handing_on(stage="principal_architect", consultation_roles=roles, specialist_advice=advice)
    role = pending[0]
    agent = create_specialist_advice_agent(
        role, model=ctx.model if _fast_delivery() else ctx.judgement_model, checkpointer=ctx.checkpointer,
        repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories,
    )
    update = _run_gated_agent(
        state,
        config,
        stage_name=f"consult_{role}",
        agent=agent,
        # The framework's own security or testing guidance for its release, for those two roles (plan HK.9); the
        # data and service bars and the pack's design tokens (SK.2 with PQ.6 and PQ.9, off until measured).
        initial_request=framework_guidance.for_a_consultant(domain_craft.for_an_adviser(build_advice_request(
            role, brief, _as_text(state.get("product_intake")), _as_text(state.get("stack_selection"))
        ), role, state.get("stack_pack")), role, getattr(state.get("stack_selection"), "technology_stack", None),
            getattr(state.get("repository"), "root_path", None)),
        output_key="__advice__",
        next_stage="specialist_consultation",
    )
    if _hand_back(update, "__advice__"):
        return update
    advice[role] = advice_from(update.pop("__advice__"))
    logger.info(
        "Consulted the %s specialist before the specification: %d recommendation(s)",
        role, len(advice[role]),
    )
    return _handing_on(**{
        **update,
        "consultation_roles": roles,
        "specialist_advice": advice,
        "stage": "specialist_consultation" if len(pending) > 1 else "principal_architect",
    })


def _record_the_advice_the_plan_declines(state: Any, update: dict[str, Any], advice_ids: list[str]) -> None:
    """Each adopted advice item the sprint plan declines with a reason, as a change to the specification (SP.2).

    In the decision log, and kept in `advice_declined` so no sprint owes the item and no specialist checks it.
    """
    from app.agents.advice_review import declined_with_a_reason
    from app.decisions import record_decision

    known = dict(state.get("advice_declined") or {})
    declined = {
        ident: line for ident, line in declined_with_a_reason(
            getattr(update.get("sprint_plan"), "advice_declined", None) or [], advice_ids,
        ).items() if ident not in known
    }
    if not declined:
        return
    record_decision(
        state, update, point="technical_specification",
        question="Change the specification: decline adopted specialist advice " + ", ".join(declined) + "?",
        options=["build it", "decline it"],
        decision="decline " + ", ".join(declined),
        rationale="The specification adopted these items; the sprint plan declines them:\n"
        + "\n".join(f"- {line}" for line in declined.values()),
    )
    update["advice_declined"] = {**known, **declined}


def scrum_master_node(state: WorkflowGraphState, config: RunnableConfig, ctx: GraphContext) -> dict[str, Any]:
    from app.graph.workflow import (
        StageGaveNoAnswer, _as_text, _hand_back, _handing_on, _missing_upstream, _record_document,
        _run_gated_agent, _the_harness_s_sprint_plan, _the_plan_assigns_nothing,
        _what_the_sprints_must_deliver, _without_the_mvp_features, build_sprint_planning_request,
        capabilities_the_plan_never_names, create_scrum_master_agent, how_much_a_plan_leaves_out,
        render_document, unaccounted_success_measures, with_setup_folded_into_the_sprint_that_needs_it,
    )

    missing = _missing_upstream(state, "technical_specification")
    if missing is not None:
        return missing
    agent = create_scrum_master_agent(model=ctx.planning_model, checkpointer=ctx.checkpointer, repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories)
    spec_text = _as_text(state.get("technical_specification"))
    measures = _what_the_sprints_must_deliver(state.get("product_intake"))
    gaps_already_asked_about = list(state.get("sprint_plan_gaps") or [])
    built_ahead_asked_about = list(state.get("sprint_plan_built_ahead") or [])
    unsized_asked_about = list(state.get("sprint_plan_unsized") or [])
    # Every adopted advice item a sprint builds and a specialist checks, placed in a sprint or declined (SP.2).
    from app.agents.advice_review import adopted_to_build

    advice_to_place = adopted_to_build(
        state.get("specialist_advice"), state.get("technical_specification"),
        declined=dict(state.get("advice_declined") or {}),
    )
    unscheduled_asked_about = list(state.get("sprint_plan_unscheduled_advice") or [])
    from app.acceptance import by_sprint
    from app.acceptance import suite as acceptance_suite
    from app.acceptance.requests import criteria_text as numbered_criteria

    root_path = state["repository"].root_path
    request = build_sprint_planning_request(
        spec_text,
        root_path,
        success_measures=measures,
        gaps=gaps_already_asked_about,
        acceptance_criteria=(
            numbered_criteria(acceptance_suite.criteria(root_path), acceptance_suite.deferred(root_path))
            # Written a sprint at a time, the suite is planned before any test is written (LF.1266).
            if acceptance_suite.is_locked(root_path) or by_sprint.is_on(root_path)
            else ""
        ),
        built_ahead=built_ahead_asked_about,
        unsized=unsized_asked_about,
        adopted_advice=advice_to_place,
        unscheduled_advice=unscheduled_asked_about,
    )
    from app.agents.specification_rulings import with_the_rulings

    request = with_the_rulings(request, root_path)
    # Sent back at the plan gate: the owner's words, with the plan they read, in this request (plan WS.3).
    from app.graph import plan_gate

    owners_changes = plan_gate.owners_changes_to_the_plan(state)
    if owners_changes:
        request["messages"][-1]["content"] += plan_gate.the_owners_direction(
            owners_changes, _as_text(state.get("sprint_plan"))
        )
    try:
        update = _run_gated_agent(
            state,
            config,
            stage_name="scrum_master",
            agent=agent,
            initial_request=request,
            output_key="sprint_plan",
            next_stage="technical_lead",
        )
    except StageGaveNoAnswer as gave_none:
        update = _the_harness_s_sprint_plan(state, measures, root_path, str(gave_none))
        # The planner spent every way to answer: its plan is sized and given the advice here, never sent back to it.
        unsized_asked_about = unsized_asked_about or ["the harness wrote the plan"]
        unscheduled_asked_about = unscheduled_asked_about or ["the harness wrote the plan"]
    if not _hand_back(update, "sprint_plan"):
        earlier = state.get("sprint_plan") if gaps_already_asked_about else None
        if earlier is not None and how_much_a_plan_leaves_out(
            update["sprint_plan"], measures
        ) > how_much_a_plan_leaves_out(earlier, measures):
            # Asked once more, and the answer leaves out more than the plan
            # it replaces. One run's second plan dropped its coverage lines
            # altogether, and the run was failed for a plan that "assigns
            # none" when the first had assigned all ten. The milestone plan
            # already keeps the better of its attempts; so does this.
            logger.warning(
                "The re-planned sprint plan leaves out more than the plan it "
                "replaces; keeping the earlier plan"
            )
            update["sprint_plan"] = earlier
        update["sprint_plan"], folded = with_setup_folded_into_the_sprint_that_needs_it(
            update["sprint_plan"], measures
        )
        if folded:
            logger.warning(
                "Sprint plan held %d sprint(s) no success measure is assigned to; "
                "folded into the next sprint: %s",
                len(folded), "; ".join(goal[:80] for goal in folded),
            )
        from app.agents.scrum_master import with_capped_sprint_count
        criteria_count = len(acceptance_suite.criteria(root_path))
        from app import delivery

        update["sprint_plan"], capped_folded = with_capped_sprint_count(
            update["sprint_plan"], criteria_count, fast=delivery.fast()
        )
        if capped_folded:
            logger.info(
                "Sprint plan capped to lean sprint count for %d criteria; "
                "folded trailing sprint(s): %s",
                criteria_count, "; ".join(goal[:80] for goal in capped_folded),
            )
        unnamed = capabilities_the_plan_never_names(
            update["sprint_plan"], _without_the_mvp_features(measures)
        )
        unassigned = unaccounted_success_measures(update["sprint_plan"], measures)
        missing = [
            {"measure": n, "missing": unnamed.get(n, [])}
            for n in sorted(set(unassigned) | set(unnamed))
        ]
        if missing and not gaps_already_asked_about:
            # Once. A plan that omits a success measure is caught at the
            # milestone review otherwise, a full build cycle later and at
            # the cost of one of three revisions; a second planning call is
            # far cheaper. A second omission is let through with a warning
            # rather than looped on - the review is still there behind it.
            logger.warning(
                "Sprint plan left success measures %s unassigned; asking once more", missing
            )
            # The plan is kept, so the answer to this can be compared with it.
            return _handing_on(
                stage="scrum_master",
                sprint_plan_gaps=missing,
                sprint_plan=update["sprint_plan"],
            )
        criteria_to_assign = [
            c for c in acceptance_suite.criteria(root_path)
            if c.id not in acceptance_suite.deferred(root_path)
        ]
        if _the_plan_assigns_nothing(unassigned, measures) and not criteria_to_assign:
            # Not let through. A plan that leaves one measure out is judged
            # by the milestone review; a plan that assigns none has no
            # review that will ever look at the whole brief with a sprint
            # still to come. One run continued on such a plan - a single
            # foundation sprint - built it, and completed with a product
            # that could add a task and do nothing else that was asked for.
            #
            # Only when there are no acceptance criteria. With them, every
            # criterion is given to a sprint just below, whatever the plan
            # said, and each sprint is done only when its criteria pass -
            # so that product could no longer complete. Stopping here
            # threw away a plan the harness was about to complete itself.
            return _handing_on(
                stage="failed",
                error=(
                    f"The sprint plan assigns none of the {len(measures)} things the "
                    "release must deliver to any sprint, after being asked once "
                    "more. Building from it would deliver a product nothing was "
                    "planned to complete. Resume to plan the sprints again."
                ),
            )
        if missing:
            logger.warning(
                "Sprint plan still leaves success measures %s unassigned after one "
                "re-plan; continuing, and the milestone review will judge it", missing
            )
        update["sprint_plan_gaps"] = []
        update["current_sprint_index"] = 0
        # Every criterion of the locked suite belongs to exactly one sprint.
        from app.agents.scrum_master import with_every_criterion_assigned

        numbered = criteria_to_assign
        update["sprint_plan"], assignment_notes = with_every_criterion_assigned(
            update["sprint_plan"], [c.id for c in numbered], {c.id: c.text for c in numbered}
        )
        # Each criterion where a test of it can pass: a test proving a later
        # sprint's criterion too cannot pass before that sprint.
        from app.acceptance import suite as locked_suite
        from app.acceptance.junit import tags_in
        from app.agents.scrum_master import with_each_criterion_where_its_tests_can_pass

        update["sprint_plan"], moved = with_each_criterion_where_its_tests_can_pass(
            update["sprint_plan"],
            [list(tags_in(name)) for _, name in locked_suite.declared_tests(state["repository"].root_path)],
        )
        assignment_notes = [*assignment_notes, *moved]
        if assignment_notes:
            logger.info("Sprint plan's criteria adjusted: %s", "; ".join(assignment_notes))
        # Sprints sized by work (LF.1315): a sprint over the limit, or one with no criterion, is sent back once with
        # the reason; a second such plan is split by the harness in plan order. A delivery that allows one sprint
        # has no limit. See `sprints_not_sized_by_work`.
        from app.agents.scrum_master import (
            most_criteria_a_sprint, sprints_not_sized_by_work, with_sprints_sized_by_work,
        )

        unsized = sprints_not_sized_by_work(update["sprint_plan"], criteria_count, fast=delivery.fast())
        if unsized and not unsized_asked_about:
            logger.warning("Sprint plan's sprints are not sized by work; asking once more: %s", unsized)
            return _handing_on(
                stage="scrum_master",
                sprint_plan_unsized=unsized,
                sprint_plan=update["sprint_plan"],
            )
        split: list[str] = []
        if unsized:
            update["sprint_plan"], split = with_sprints_sized_by_work(
                update["sprint_plan"], criteria_count, fast=delivery.fast(),
                texts={c.id: c.text for c in numbered},
            )
            logger.warning("Sprint plan still not sized by work; split by the harness: %s", "; ".join(split))
        update["sprint_plan_unsized"] = []
        # Every adopted advice item in a sprint or declined with a reason (SP.2): a plan that places some nowhere is
        # sent back once naming them; a second one has them placed in its last sprint, which owes every adopted item
        # not yet built. See `scrum_master.advice_not_scheduled`.
        from app.agents.scrum_master import advice_not_scheduled, with_the_advice_scheduled

        advice_ids = [line.split(":", 1)[0] for line in advice_to_place]
        unscheduled = advice_not_scheduled(update["sprint_plan"], advice_ids)
        if unscheduled and not unscheduled_asked_about:
            logger.warning("Sprint plan places adopted advice in no sprint; asking once more: %s", unscheduled)
            return _handing_on(
                stage="scrum_master",
                sprint_plan_unscheduled_advice=unscheduled,
                sprint_plan=update["sprint_plan"],
            )
        update["sprint_plan"], advice_placed = with_the_advice_scheduled(update["sprint_plan"], unscheduled)
        if advice_placed:
            logger.warning("Sprint plan still places adopted advice in no sprint: %s", "; ".join(advice_placed))
        update["sprint_plan_unscheduled_advice"] = []
        # Once, as for the success measures: a sprint whose scope builds a
        # later sprint's criteria has its lead write work orders for them
        # and its builders build every sprint in the first. See
        # `scope_a_later_sprint_delivers`.
        from app.agents.scrum_master import scope_a_later_sprint_delivers

        ahead = scope_a_later_sprint_delivers(update["sprint_plan"], {c.id: c.text for c in numbered})
        if ahead and not built_ahead_asked_about:
            logger.warning("Sprint plan builds later sprints' work early; asking once more: %s", ahead)
            return _handing_on(
                stage="scrum_master",
                sprint_plan_built_ahead=ahead,
                sprint_plan=update["sprint_plan"],
            )
        if ahead:
            logger.warning(
                "Sprint plan still builds later sprints' work early after one re-plan; "
                "continuing, and each sprint's lead and builders are told what later "
                "sprints deliver: %s", ahead,
            )
        update["sprint_plan_built_ahead"] = []
        _record_the_advice_the_plan_declines(state, update, advice_ids)
        from app.decisions import record_decision

        planned = list(getattr(update["sprint_plan"], "sprints", None) or [])
        record_decision(
            state, update, point="sprint_plan",
            question="How is the work split into sprints?",
            decision=f"{len(planned)} sprint(s): " + "; ".join(
                f"{number}. {getattr(sprint, 'goal', '')}"
                + (f" ({', '.join(sprint.criteria)})" if getattr(sprint, "criteria", None) else "")
                for number, sprint in enumerate(planned, 1)
            ),
            rationale=(
                "Planned by the scrum master"
                + (f"; still unassigned after one re-plan: {missing}" if missing else
                   "; every success measure is assigned a sprint")
                + (f"; sprints split by the harness to at most {most_criteria_a_sprint(criteria_count, fast=delivery.fast())} "
                   f"criteria each: {'; '.join(split)}" if split else "")
                + (f"; {' '.join(advice_placed)}" if advice_placed else "")
                + "."
            )[:1500],
        )
        _record_document(
            state,
            "docs/sprint_plan.md",
            render_document("sprint_plan", o=update["sprint_plan"]),
        )
        from app.graph.workflow import SPRINT_PLAN_REVIEW, _review_enabled

        update = plan_gate.after_the_plan(update, _review_enabled(state, SPRINT_PLAN_REVIEW), bool(owners_changes))
        if update.get("stage") == "technical_lead":
            # Sprint 1's tests are written first where the suite is written a sprint at a time (LF.1266).
            from app.graph.acceptance_nodes import before_the_lead

            update["stage"] = before_the_lead(state)
    return update
