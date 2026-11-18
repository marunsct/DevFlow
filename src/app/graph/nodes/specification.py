"""The specification: the principal architect writes it and the architecture review reads it.

    principal_architect -> architecture_review -> (user_review_specification) -> scaffold

See `app.graph.nodes` for how these are registered and why their helpers are
imported from `app.graph.workflow` when they run.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig

from app.graph.context import GraphContext
from app.graph.workflow import WorkflowGraphState

#: The workflow's logger: the nodes log as they did inside the builder.
logger = logging.getLogger("app.graph.workflow")


def principal_architect_node(state: WorkflowGraphState, config: RunnableConfig, ctx: GraphContext) -> dict[str, Any]:
    from app.graph.workflow import (
        MAX_SPECIFICATION_REPAIRS, _a_model_to_revise_with, _as_text, _collect_required_changes,
        _fast_delivery, _hand_back, _incomplete_specification_sections, _missing_upstream,
        _record_document, _run_gated_agent, _settings_it_cannot_start_without, _the_layout_repair,
        _the_review_s_findings_are_open, _the_scaffold_s_layout, _the_served_files_the_plan_leaves_out,
        _the_startup_repair, _with_the_sections_it_dropped, build_architecture_request,
        build_architecture_revision_request, create_principal_architect_agent, render_specification,
    )

    missing = _missing_upstream(state, "product_intake", "tools_models")
    if missing is not None:
        return missing
    agent = create_principal_architect_agent(model=ctx.judgement_model, checkpointer=ctx.checkpointer, repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories)

    # A rejected specification must come back with the reasons attached,
    # otherwise the architect reproduces the version that was rejected.
    required_changes = _collect_required_changes(state)
    previous_specification = state.get("technical_specification")
    if required_changes and previous_specification is not None:
        request = build_architecture_revision_request(
            previous_specification_text=previous_specification.model_dump_json(indent=2) if hasattr(previous_specification, "model_dump_json") else __import__("json").dumps(previous_specification, indent=2),
            required_changes=required_changes,
            product_intake_text=_as_text(state.get("product_intake")),
            tools_and_models_text=_as_text(state.get("tools_models")),
            stack_selection_text=_as_text(state.get("stack_selection")),
            repository=state["repository"],
            document=state["document"],
            advice=state.get("specialist_advice"),
        )
    else:
        request = build_architecture_request(
            _as_text(state.get("product_intake")),
            _as_text(state.get("tools_models")),
            _as_text(state.get("stack_selection")),
            state["repository"],
            state["document"],
            advice=state.get("specialist_advice"),
        )

    # The open questions' assumed answers, recorded at intake (plan IN.1).
    from app.agents import assumptions

    request["messages"][-1]["content"] += assumptions.block(state)
    # Fast delivery: the architect writes the core and the other sections
    # are written from it at once. See `app.graph.specification_parts`.
    in_parts = _fast_delivery() and not (required_changes and previous_specification is not None)
    if in_parts:
        from app.graph.specification_parts import CORE_NOTE

        request["messages"][-1]["content"] += CORE_NOTE
    # One naming standard, before any name is written (NAMING_STANDARD).
    from app.stacks.naming import standard_for

    naming = standard_for(getattr(state.get("stack_selection"), "technology_stack", None))
    if naming:
        request["messages"][-1]["content"] += "\n\n" + naming
    # The layout the scaffold will set up, before the file plan is written:
    # cheaper than the repair after it, which on one run never ran. A revision is
    # told too: measured, sent back over the harness's files, it had nothing to answer from.
    request["messages"][-1]["content"] += _the_scaffold_s_layout(state)
    # The reading done first, by the harness and the build model, and
    # handed over: the architect's reasoning goes on the specification,
    # not on which page to read next. See `app.agents.research_brief`.
    research = str(state.get("architect_research") or "")
    if not research:
        try:
            from app.agents.research_brief import research_notes

            research = research_notes(
                getattr(state.get("stack_selection"), "technology_stack", None),
                getattr(state.get("document"), "text", "") or "",
                ctx.building_model if isinstance(ctx.building_model, BaseChatModel) else None,
            )
        except Exception:  # noqa: BLE001 - the architect reads for itself, as before
            logger.warning("Could not do the architect's reading before it began", exc_info=True)
            research = ""
    if research:
        request["messages"][-1]["content"] += "\n\n" + research
    from app.tools.research import researched

    def parts_context() -> str:
        # The advice numbered with its ids and the rule for answering it, as the architect's own request has it
        # (HR2.D.1): as raw JSON it carried no ids, and 224 rounds over 120 runs were spent asking for them.
        from app.agents.specialist_advice import advice_block

        advice = advice_block(state.get("specialist_advice")) if state.get("specialist_advice") else ""
        return "\n\n".join([
            *(f"--- {title} ---\n{_as_text(state.get(key))[:20_000]}"
              for title, key in (("Product intake", "product_intake"), ("Stack", "stack_selection"))
              if state.get(key)),
            *([advice[:20_000]] if advice else []),
        ]) + _the_scaffold_s_layout(state)  # These calls write the sections that name the runner, the start and the files.

    update = None
    # Fast delivery revises in place: only the sections the review's
    # changes touch are rewritten. See `specification_parts.revised_in_place`.
    # No model named means the deployment's own, as the parts writer below
    # already resolves it. Measured live on a local-only run: with none
    # named this path never ran, and the architect's whole-document
    # revision was cut at the output cap three times running.
    revision_model = (
        _a_model_to_revise_with(ctx.judgement_model) if _fast_delivery() and required_changes else ctx.judgement_model
    )
    if (
        _fast_delivery() and required_changes and previous_specification is not None
        and hasattr(previous_specification, "model_dump") and isinstance(revision_model, BaseChatModel)
    ):
        from app.graph.specification_parts import revised_in_place

        revised = revised_in_place(
            previous_specification, "\n".join(f"- {change}" for change in required_changes),
            revision_model, parts_context(),
        )
        if revised is not None:
            update = {"technical_specification": revised, "stage": "architecture_review"}
    if update is None:
        with researched(bool(research)):
            update = _run_gated_agent(
                state,
                config,
                stage_name="principal_architect",
                agent=agent,
                initial_request=request,
                output_key="technical_specification",
                next_stage="architecture_review",
            )
    if research and isinstance(update, dict):
        update["architect_research"] = research
    if not _hand_back(update, "technical_specification") and in_parts:
        from app.graph.specification_parts import with_the_parts_written

        update["technical_specification"] = with_the_parts_written(
            update["technical_specification"], ctx.judgement_model, parts_context(),
        )
    if not _hand_back(update, "technical_specification"):
        # Consumed: the revision request above already delivered them, so
        # a later rerun must not re-apply stale comments.
        update["revision_comments"] = []
        if _the_review_s_findings_are_open(state):
            update["architecture_review_applied"] = state.get("architecture_revision_count", 0)

        # And after a review: a revision sends the sections it changes, and
        # the rest are the previous specification's. One run's architect,
        # sent back on a 60,000-character specification, spent its revision
        # reading that specification out of its own saved conversation to
        # write all of it again.
        if (state.get("specification_repair_count", 0) or required_changes) and previous_specification is not None:
            update["technical_specification"] = _with_the_sections_it_dropped(
                update.get("technical_specification"), previous_specification
            )

        # Rendered from the decision the pipeline routes on, so the
        # document and the structured answer cannot disagree. See
        # `app.agents.specification_document`.
        _record_document(
            state,
            "docs/technical_specification.md",
            render_specification(
                update["technical_specification"],
                getattr(state.get("product_intake"), "product_name", ""),
            ),
        )

        missing = _incomplete_specification_sections(update.get("technical_specification"))
        repairs = state.get("specification_repair_count", 0)
        # The layout first, on a budget of its own: a file plan that puts the
        # product where the scaffold serves nothing dooms every stage after
        # it. Measured live: this check came last in a chain sharing two
        # repairs, both went to earlier problems, and a specification
        # planning `backend/app/` and `frontend/src/` against a scaffold
        # serving the package's `main.py` and `src/App.tsx` was approved -
        # 28 files were drafted where nothing served them.
        served = [] if missing else _the_served_files_the_plan_leaves_out(update.get("technical_specification"), state)
        layout_repairs = state.get("layout_repair_count", 0) or 0
        required = [] if (missing or served) else _settings_it_cannot_start_without(
            update.get("technical_specification")
        )
        if served and layout_repairs < MAX_SPECIFICATION_REPAIRS:
            update["layout_repair_count"] = layout_repairs + 1
            update["stage"] = "principal_architect"
            update["revision_comments"] = [_the_layout_repair(served, state)]
        elif required and repairs < MAX_SPECIFICATION_REPAIRS:
            update["specification_repair_count"] = repairs + 1
            update["stage"] = "principal_architect"
            update["revision_comments"] = [_the_startup_repair(required)]
        elif missing and repairs < MAX_SPECIFICATION_REPAIRS:
            # Straight back to the architect with the exact field names,
            # without spending an architecture-review cycle on it.
            update["specification_repair_count"] = repairs + 1
            update["stage"] = "principal_architect"
            update["revision_comments"] = [
                "Your structured response left these required sections empty: "
                + ", ".join(missing)
                + ". The document `docs/technical_specification.md` on disk already holds the completed sections. "
                "Do not repeat the existing sections or return the whole document. "
                "Return only the missing fields: "
                + ", ".join(missing)
                + ". Unchanged sections are automatically preserved."
            ]
        elif not missing:
            # Testing nobody here can carry out: a person's check, or an
            # assertion that exits 0 whatever it finds. Same bounded repair
            # path, same reason - the architect can fix it in one pass, and
            # a review cycle would only relay it.
            from app.agents.principal_architect import testing_nobody_can_run

            from app.agents.specialist_advice import what_the_specification_owes

            unrunnable = testing_nobody_can_run(update.get("technical_specification"))
            owed = what_the_specification_owes(
                update.get("technical_specification"), state.get("specialist_advice")
            )
            if owed and not unrunnable and repairs < MAX_SPECIFICATION_REPAIRS:
                # The specialists were asked; an answer that ignores them
                # leaves the advice where nobody reads it.
                update["specification_repair_count"] = repairs + 1
                update["stage"] = "principal_architect"
                update["revision_comments"] = [
                    "The specification does not answer the specialists' advice:\n"
                    + "\n".join(f"- {problem}" for problem in owed)
                    + "\nThe document `docs/technical_specification.md` on disk already holds the completed sections. "
                    "Do not return the whole specification from the beginning or repeat unchanged sections. "
                    "Return only `specialist_advice_decisions` answering those items; unchanged sections are automatically preserved."
                ]
            elif unrunnable and repairs < MAX_SPECIFICATION_REPAIRS:
                update["specification_repair_count"] = repairs + 1
                update["stage"] = "principal_architect"
                update["revision_comments"] = [
                    "The `testing` section plans checks nothing in this environment "
                    "can carry out:\n"
                    + "\n".join(f"- {entry}" for entry in unrunnable)
                    + "\nNo person watches the workspace and there is no display, so a "
                    "manual or visual check never happens, and an assertion written "
                    "to a console or log exits 0 whatever it finds. Every check must be "
                    "an automated test run by the runner the technology stack names, "
                    "which fails the command when a test fails. "
                    "The document `docs/technical_specification.md` on disk already holds the completed sections. "
                    "Do not return the whole specification from the beginning. "
                    "Return only `testing` with those checks corrected; unchanged sections are automatically preserved."
                ]
            else:
                update["specification_repair_count"] = 0
    return update


def architecture_review_node(state: WorkflowGraphState, config: RunnableConfig, ctx: GraphContext) -> dict[str, Any]:
    from app.graph.workflow import (
        SPECIFICATION_REVIEW, _GATING_SEVERITIES, _a_brief_feature_the_specification_defers,
        _a_pass_over_its_own_findings, _a_success_measure_the_specification_drops,
        _approved_once_the_harness_s_findings_are_settled, _as_text,
        _a_kept_signature_the_specification_calls_otherwise,
        _behaviour_the_specification_gives_kept_files, _contract_lines_nothing_can_read,
        _decided_after_one_revision, _findings_that_block, _format_finding, _hand_back, _missing_upstream,
        _record_document, _review_enabled, _run_gated_agent, _the_revision_limit,
        _the_same_command_in_another_order, _the_setup_for_the_review, build_architecture_review_request,
        create_architecture_reviewer_agent, render_architecture_review,
    )

    missing = _missing_upstream(state, "technical_specification")
    if missing is not None:
        return missing
    spec_text = _as_text(state.get("technical_specification"))
    settled = _approved_once_the_harness_s_findings_are_settled(state, spec_text)
    if settled is not None:
        return settled
    # `ONE_DESIGN_REVIEW` (LR.42): after one revision the deterministic gates decide, not a second review.
    once = _decided_after_one_revision(state, spec_text)
    if once is not None:
        return once
    agent = create_architecture_reviewer_agent(model=ctx.judgement_model, checkpointer=ctx.checkpointer, repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories)
    previous_review = state.get("architecture_review")
    request = build_architecture_review_request(
        spec_text,
        state["repository"].root_path,
        getattr(state.get("document"), "text", "") or "",
        earlier=list(
            (previous_review.get("findings") if isinstance(previous_review, dict) else getattr(previous_review, "findings", None))
            or []
        ),
        revision=state.get("architecture_revision_count", 0),
        environment=_the_setup_for_the_review(state),
    )
    update = _run_gated_agent(
        state,
        config,
        stage_name="architecture_review",
        agent=agent,
        initial_request=request,
        output_key="architecture_review",
        next_stage="scrum_master",  # placeholder; always overridden below
    )
    if _hand_back(update, "architecture_review"):
        return update

    review: ArchitectureReviewOutput = update["architecture_review"]
    reviewer_approved = review.status == "approved"
    fired: list[str] = []

    coverage_finding = _a_success_measure_the_specification_drops(state, spec_text)
    if coverage_finding is not None:
        review = review.model_copy(
            update={"findings": [*review.findings, coverage_finding], "status": "changes_required"}
        )
        update["architecture_review"] = review
        update["specification_coverage_checked"] = True
        fired.append("coverage")
    deferral_finding = _a_brief_feature_the_specification_defers(state, spec_text)
    if deferral_finding is not None:
        review = review.model_copy(
            update={"findings": [*review.findings, deferral_finding], "status": "changes_required"}
        )
        update["architecture_review"] = review
        update["specification_deferrals_checked"] = True
        fired.append("deferrals")
    unread_finding = _contract_lines_nothing_can_read(state)
    if unread_finding is not None:
        review = review.model_copy(
            update={"findings": [*review.findings, unread_finding], "status": "changes_required"}
        )
        update["architecture_review"] = review
        update["specification_contract_lines_checked"] = True
        fired.append("contract")
    order_finding = _the_same_command_in_another_order(state, spec_text)
    if order_finding is not None:
        review = review.model_copy(
            update={"findings": [*review.findings, order_finding], "status": "changes_required"}
        )
        update["architecture_review"] = review
        update["specification_command_order_checked"] = True
        fired.append("order")
    kept_finding = _behaviour_the_specification_gives_kept_files(state, spec_text)
    if kept_finding is not None:
        review = review.model_copy(
            update={"findings": [*review.findings, kept_finding], "status": "changes_required"}
        )
        update["architecture_review"] = review
        update["specification_kept_files_checked"] = True
        fired.append("kept")
    signature_finding = _a_kept_signature_the_specification_calls_otherwise(state, spec_text)
    if signature_finding is not None:
        review = review.model_copy(
            update={"findings": [*review.findings, signature_finding], "status": "changes_required"}
        )
        update["architecture_review"] = review
        update["specification_signatures_checked"] = True
        fired.append("signature")

    review = _a_pass_over_its_own_findings(
        review, state["repository"].root_path, "approved", "architecture_review"
    )
    update["architecture_review"] = review
    # The reviewer approved and only the workflow's checks sent it back: the revision is checked by them alone.
    update["approved_but_for_the_harness"] = fired if reviewer_approved and fired else []

    # Rendered from the decision, not written by the reviewer as a second
    # copy that can disagree with it. See `app.agents.review_document`.
    _record_document(state, "docs/architecture_review.md", render_architecture_review(review))

    blocking = _findings_that_block(review, state["repository"].root_path)
    if review.status != "approved" and review.findings and not blocking:
        # Findings, but none of them gate. See `_findings_that_block`.
        logger.info(
            "Stage architecture_review asked for changes over %d finding(s), none "
            "above %s; recording them and continuing",
            len(review.findings),
            "/".join(sorted(_GATING_SEVERITIES)),
        )

    if review.status == "approved" or (review.findings and not blocking):
        from app.decisions import record_decision

        record_decision(
            state, update, point="technical_specification",
            question="Is the specification ready to build from?",
            options=["approve", "send it back to the architect"],
            decision="approve",
            rationale=(
                "The architecture reviewer approved it."
                if review.status == "approved"
                else f"Approved with {len(review.findings)} finding(s), none of them blocking."
            ),
        )
        # The mandatory gate passed. Only now may an optional human review
        # session run; it can never substitute for this gate.
        update["stage"] = (
            "user_review_specification" if _review_enabled(state, SPECIFICATION_REVIEW) else "scaffold"
        )
    else:
        revision_count = state.get("architecture_revision_count", 0) + 1
        update["architecture_revision_count"] = revision_count
        # Fast delivery revises once: blocking findings still open after
        # that are decided as risks, as they are after the full count.
        limit = _the_revision_limit()
        if revision_count >= limit:
            # Decided, not stopped: see `app.graph.escalation`. The run used
            # to fail here - one stored run after six revisions - although
            # the acceptance suite, written from the brief, is what decides
            # whether the product works. Open design points are a risk to
            # record, or a question for the person who asked to be asked.
            outstanding = [_format_finding(f) for f in blocking]
            update["stage"] = "escalation"
            update["error"] = None
            update["escalation"] = {
                "kind": "design",
                "findings": outstanding,
                "error": (
                    f"The architecture reviewer still asked for changes to the specification "
                    # The count the run stopped at: fast delivery's two, not the full limit (review D8).
                    f"after {revision_count} revision{'s' if revision_count != 1 else ''}."
                ),
            }
        else:
            update["stage"] = "principal_architect"
    return update
