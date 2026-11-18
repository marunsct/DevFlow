"""The fix stage: one defect at a time, or, in parallel mode, a batch fixed side by side.

    defect_remediation -> (defect_fix_worker x N -> defect_fix_gather) -> test_and_triage

See `app.graph.nodes` for how these are registered and why their helpers are
imported from `app.graph.workflow` when they run.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.observability.degraded import degraded
from app.graph import acceptance_nodes
from app.graph.context import GraphContext
from app.graph.workflow import WorkflowGraphState

#: The workflow's logger: the nodes log as they did inside the builder.
logger = logging.getLogger("app.graph.workflow")


def _the_fix_request(state: Any, config: RunnableConfig, cycle: Any, defect_index: int) -> tuple[dict[str, Any], list[tuple[int, Any]]]:
    """What one defect's fixer is asked, and the related failures bundled with it."""
    from app.graph.workflow import (
        APP_RUN_ID_KEY, _bundle_co_defects, _the_database_section, _the_last_attempt_section,
        _the_specification_for_the_fix, _the_stub_still_served_section, _the_unserved_code_section,
        _what_a_fix_stage_must_leave_alone, _what_the_criteria_s_tests_printed,
        _what_the_last_failure_printed, _what_the_unit_tests_printed, build_defect_fix_request,
        defect_fix_modes, mutation_guided, with_the_facts,
    )

    defect = cycle.defects[defect_index]
    from app.acceptance.junit import tags_in

    request = build_defect_fix_request(
        defect.description,
        defect.reproduction_steps,
        defect.expected_behavior,
        defect.actual_behavior,
        defect.affected_files,
        defect.regression_test_required,
        state["repository"].root_path,
        getattr(state.get("stack_selection"), "technology_stack", None),
        # What the failing command actually printed, alongside the prose
        # description of it. See `build_defect_fix_request`.
        # A failing criterion's own tests first: the last failing command may be another criterion's.
        _what_the_criteria_s_tests_printed(state["repository"].root_path, defect)
        or _what_the_unit_tests_printed(state["repository"].root_path, defect)
        or _what_the_last_failure_printed(config["configurable"].get(APP_RUN_ID_KEY), defect),
        caught_by=getattr(defect, "caught_by", ""),
        # Only for a defect that is not itself a failing criterion - nor a
        # mutation finding, whose product is not wrong (plan QM.2).
        done_already=(
            []
            if [t for t in tags_in(str(defect.description or "")) if t.startswith(("AC-", "CR-"))]
            or mutation_guided.is_a_finding(defect)
            else acceptance_nodes.done_by_the_definition(state)
        ),
        what_settles_it=mutation_guided.what_settles_it(defect, cycle.defects),
    )
    request["messages"][-1]["content"] += _what_a_fix_stage_must_leave_alone(state, defect)
    # What this attempt may write: test files only, for a first fix of a failing unit test beside a green suite.
    request["messages"][-1]["content"] += defect_fix_modes.briefing(state, config, defect_index)
    co_defects = _bundle_co_defects(cycle, defect_index)
    request["messages"][-1]["content"] += _the_specification_for_the_fix(state, defect, co_defects)
    if co_defects:
        batch_lines = [
            "\n--- Related failures owned by your role to resolve in this same fix ---",
            "The harness measures each one after your fix; one still failing goes to its own fix.",
        ]
        for pos, co_d in co_defects:
            batch_lines.append(f"- Failure {pos + 1}: {co_d.description}")
            batch_lines.append(f"  Expected: {co_d.expected_behavior}")
            batch_lines.append(f"  Actual: {co_d.actual_behavior}")
        request["messages"][-1]["content"] += "\n".join(batch_lines) + "\n"
    # A defect on its last permitted attempt gets a different shape of
    # work, not a third variation of the instruction that failed twice.
    # See `_the_last_attempt_section`.
    request["messages"][-1]["content"] += _the_last_attempt_section(cycle, defect_index)
    # Each earlier attempt as measured (plan PH.2), not a revert sentence.
    from app.agents import ledger as _ledger

    request["messages"][-1]["content"] += _ledger.earlier_attempts(defect, cycle.defects[:defect_index])
    request["messages"][-1]["content"] += _the_stub_still_served_section(state["repository"].root_path)
    request["messages"][-1]["content"] += _the_unserved_code_section(state["repository"].root_path)
    request["messages"][-1]["content"] += _the_database_section(state["repository"].root_path)
    # The layout the judges read too (plan CM.1); the stub and the code the
    # product does not run are the two sections above.
    request = with_the_facts(request, state["repository"].root_path, built=False)
    # Where the sprint stands (plan PH.1, off until measured).
    from app.agents import where_things_stand

    request = where_things_stand.with_it(request, state)
    # The defect's files' neighbours in the code graph (plan CG.2, off until measured).
    from app.analysis import project_graph

    request = project_graph.with_the_neighbourhood(request, state["repository"].root_path, [
        *(defect.affected_files or []), *(f for _, d in co_defects for f in (d.affected_files or []))])
    # The page as a person sees it, for a build model that reads images:
    # only the reviewer was shown it. Last, as it makes the request's text
    # a list of parts.
    from app.agents.page_screenshots import with_the_page_for_a_fixer

    request = with_the_page_for_a_fixer(request, state["repository"].root_path)
    # What this fixer was shown, so a later try can be compared with it (deep review F9): once a fixer, not on
    # each resume of its stage after a gated tool call (measured: every 6 to 10 seconds for one fixer).
    from app.observability import defect_ledger

    if not state.get("pending_inner_thread_id"):
        defect_ledger.shown(
            f"defect_fix_{state.get('test_round', 0)}_{defect_index}", defect, request["messages"][-1]["content"],
            round_=state.get("test_round", 0), index=defect_index, sprint=state.get("current_sprint_index", 0),
        )
    return request, co_defects


def _fixed_by_rewriting(
    state: Any, config: RunnableConfig, defect: Any, fix_model: Any, failed_tries: int = 0,
    after_a_surrender: bool = False, why: dict[str, str] | None = None, *, ctx: GraphContext,
) -> Any:
    """A fast-delivery fix by rewriting the defect's files, or None for the agent loop.

    After a failed fix, and with a judgement model of its own, several
    candidates are asked of the judgement model at once and the first the
    defect's tests pass is kept (`rewritten_fixes.fix_by_candidates`).
    """
    from app.graph.workflow import (
        APP_RUN_ID_KEY, MOST_DIAGNOSTICS_FOR_A_PASS, _diagnostics_in_files_touched, _fast_delivery,
        _the_defect_s_tests_pass,
        _the_fixes_to_keep_for, _the_run_approves_its_own_writes, _what_the_criteria_s_tests_printed,
        _what_the_last_failure_printed, _what_the_unit_tests_printed, defect_fix_modes, mutation_guided,
    )

    def declined(reason: str) -> None:
        if why is not None:
            why["why"] = reason

    if not _the_run_approves_its_own_writes(config["configurable"].get(APP_RUN_ID_KEY)):
        declined("the run does not approve its own writes")
        return None
    if mutation_guided.is_a_finding(defect):
        # A rewrite rewrites the files a failure points at - here the
        # product's own source, which the finding must leave as it is. A
        # new unit test is the agent loop's (plan QM.2).
        declined("a mutation finding: the product's source stays as it is")
        return None
    from types import SimpleNamespace

    from app.graph.rewritten_fixes import fix_by_candidates, fix_by_rewriting, files_to_fix, what_failed
    from app.tools.repository import _the_harness_s_own_or_the_locked_suite, just_asking

    from app.graph.bounded_fixes import the_candidate_model

    root = Path(state["repository"].root_path)
    def may_write(path: str) -> bool:
        with just_asking():
            return (_the_harness_s_own_or_the_locked_suite(root, root / path) is None
                    and defect_fix_modes.may_write(state, config, defect, root, path))

    # The defect's own failing tests first, as the agent loop's request does (HR F3).
    last_failure = (
        _what_the_criteria_s_tests_printed(str(root), defect)
        or _what_the_unit_tests_printed(str(root), defect)
        or _what_the_last_failure_printed(config["configurable"].get(APP_RUN_ID_KEY), defect)
    )
    # The other open defects, whose failures that point at a file go into its rewrite (behind `CO_DEFECT_FAILURES_IN_REWRITES`).
    from app.graph.co_defect_failures import open_besides

    co_defects = open_besides(state.get("remediation"), defect)
    # Carried from the candidates path into the rewrite that follows it,
    # so a retry that already asked where the defect lives - same defect,
    # same failure - does not ask again. None when candidates were never
    # tried: `fix_by_rewriting` localises for itself, as before, so a
    # defect this never reaches pays nothing extra for it.
    located: list[str] | None = None
    # A judgement model of its own, or with the fix cycle on the fix's own
    # model (plan AY step 2); None asks for no candidates.
    candidate_model = the_candidate_model(ctx.judgement_model, ctx.model, fix_model)
    if failed_tries >= 1 and candidate_model is not None and not after_a_surrender:
        try:
            from app.graph.localisation import localised

            failure = what_failed(defect, root, last_failure)
            located = localised(
                defect, failure, root, fix_model or ctx.model or ctx.building_model,
                files_to_fix(defect, failure, root, may_write), may_write,
            )
            kept = fix_by_candidates(
                defect, root, candidate_model, lambda: _the_defect_s_tests_pass(root, defect),
                specification=state.get("technical_specification"),
                stack=getattr(state.get("stack_selection"), "technology_stack", None),
                last_failure=last_failure, may_write=may_write, files=located, co_defects=co_defects,
                kept=_the_fixes_to_keep_for(state, defect),
            )
            if kept is not None:
                return kept
        except Exception as swallowed:  # noqa: BLE001 - one rewrite, or the agent loop, takes the defect
            degraded("fix.candidates", swallowed)
    # Candidates are in every delivery mode: they are kept only when the
    # defect's tests pass. A single rewrite in place of the agent loop is
    # fast delivery's.
    if not _fast_delivery() and not after_a_surrender:
        return None
    # Read only when nothing is written: the rewrite found no file it may write, or wrote none.
    declined("the rewrite found no file it may write, or wrote none")
    try:
        return fix_by_rewriting(
            defect, root, fix_model or ctx.model or ctx.building_model,
            specification=state.get("technical_specification"),
            stack=getattr(state.get("stack_selection"), "technology_stack", None),
            last_failure=last_failure, may_write=may_write, files=located, co_defects=co_defects,
            kept=_the_fixes_to_keep_for(state, defect),
            diagnose=lambda files: _diagnostics_in_files_touched(
                state, {"messages": []}, SimpleNamespace(changed_files=files), most=MOST_DIAGNOSTICS_FOR_A_PASS,
            ),
        )
    except Exception as error:  # noqa: BLE001 - the agent loop takes the defect
        degraded("fix.rewrite", error)
        declined(f"the rewrite raised {type(error).__name__}")
        return None


def _fix_one(state: Any, config: RunnableConfig, defect_index: int, ctx: GraphContext) -> dict[str, Any]:
    """Route one open defect to its owner, measure the fix, and record what it settled."""
    from app.graph.workflow import (
        APP_RUN_ID_KEY, _a_contested_test_past_repair, _a_dispute_may_be_held_now,
        _a_locked_test_two_fixes_broke, _a_revert_escalates_this_fix,
        _closed_if_an_earlier_fix_resolved_it, _handing_on, _note_the_bundled, _noted_as_reverted,
        _one_more_failed_fix, _put_back_a_deliberate_change, _run_gated_agent, _settle_the_fix,
        _the_defect_s_tests_pass, _the_unit_tests_a_kept_fix_broke, _with_the_attempt,
        create_specialist_agent, defect_fix_modes, failed_fix_tries,
    )

    cycle = state["remediation"]
    defect = cycle.defects[defect_index]
    stage_name = f"defect_fix_{state.get('test_round', 0)}_{defect_index}"
    _put_back_a_deliberate_change(state)

    # Fixed already, by an earlier fix in this round: nothing for a fixer
    # to do, and a fixer told to fix what works finds other work.
    closed = _closed_if_an_earlier_fix_resolved_it(state, cycle, defect_index)
    if closed is not None:
        return closed
    # A defect that has spent its calls across attempts is not fixed again
    # (plan AY step 4, off until measured).
    from app.graph import defect_budget

    spent_out = defect_budget.spent_out(cycle, defect_index)
    if spent_out:
        from app.observability import defect_ledger

        defect_ledger.note(
            "left open", stage_name, defect=defect, round_=state.get("test_round", 0), index=defect_index,
            sprint=state.get("current_sprint_index", 0), detail=spent_out,
        )
        return {"defect_cursor": defect_index + 1}
    # Carried across an approval pause, as the commit it starts from is:
    # taken again on resume, the calls before the pause were not counted.
    started = (str(state.get("fix_started") or "") if state.get("pending_inner_thread_id") else "") or defect_budget.now()

    fix_model = ctx.the_build_model(
        state,
        stage_name,
        failed_fix_tries(cycle, defect_index),
        reasons=True,
        after_a_revert=_a_revert_escalates_this_fix(cycle, defect_index),
    )
    # A fix that breaks what passed before it is reverted to exactly where
    # it started. The commit it starts from is taken on the stage's first
    # entry and carried across an approval pause. See `app.graph.engineering`.
    from app.graph import engineering

    fix_base = (
        str(state.get("fix_base_commit") or "")
        if state.get("pending_inner_thread_id")
        else engineering.before_a_fix(state["repository"].root_path, stage_name)
    )
    # The mode this fix runs in: what it may write, and what is kept of it (`app.graph.defect_fix_modes`).
    defect_fix_modes.begin(state, config, cycle, defect_index, stage_name)
    # Fast delivery: the harness gathers what failed and the files it points
    # at, and the model rewrites each file in one call. See
    # `app.graph.rewritten_fixes`; a defect it cannot place goes to the agent loop.
    # A reverted fix whose own tests passed is measured a second time first (behind `KEPT_FIX_CANDIDATES`).
    from app.graph import kept_fix_candidates

    repo = Path(state["repository"].root_path)
    rewritten = None if state.get("pending_inner_thread_id") else (
        kept_fix_candidates.replayed(repo, defect, stage_name) or _fixed_by_rewriting(
            state, config, defect, fix_model, failed_fix_tries(cycle, defect_index), ctx=ctx,
        )
    )
    if rewritten is not None:
        update: dict[str, Any] = {}
        co_defects: list[tuple[int, Any]] = []
        fix_result: SpecialistOutput = rewritten
    else:
        agent = create_specialist_agent(
            defect.owner, model=fix_model,
            checkpointer=ctx.checkpointer, repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories,
        )
        request, co_defects = _the_fix_request(state, config, cycle, defect_index)
        # Each write followed by the defect's own tests (plan AY step 3, off until measured).
        from app.acceptance import mutant_check_in_stage
        from app.graph import verify_after_write

        root = Path(state["repository"].root_path)
        with verify_after_write.watching(
            config["configurable"].get(APP_RUN_ID_KEY), stage_name,
            # A mutation finding's write is answered by its own change (`MUTANT_CHECK_IN_THE_FIX_STAGE`).
            mutant_check_in_stage.check_for(root, defect, lambda: _the_defect_s_tests_pass(root, defect)),
            # A fix alone keeps the version its own tests passed at (A3, `best_checkpoint`); not a mutation finding's,
            # whose check is of its own change.
            **(mutant_check_in_stage.how_for(defect) or {"checkpoints_in": root}),
        ):
            update = _run_gated_agent(
                state,
                config,
                stage_name=stage_name,
                agent=agent,
                initial_request=request,
                output_key="__fix_result__",
                next_stage="defect_remediation",
            )
        if "__fix_result__" not in update:
            update["fix_base_commit"] = fix_base
            update["fix_started"] = started
            return update  # paused waiting for approval on this fix

        fix_result = update.pop("__fix_result__")
        # An answer that changed no file goes to the harness's rewrite once (behind `SURRENDER_TO_REWRITE`).
        from app.graph.surrender_to_rewrite import after_a_surrender

        from app.observability import defect_ledger as _surrender_ledger

        why: dict[str, str] = {}
        fix_result = after_a_surrender(fix_result,
            lambda: _fixed_by_rewriting(state, config, defect, fix_model, failed_fix_tries(cycle, defect_index),
                                        after_a_surrender=True, why=why, ctx=ctx),
            note=lambda outcome: _surrender_ledger.note(
                "rewrite after surrender", stage_name, defect=defect, index=defect_index,
                round_=state.get("test_round", 0),
                detail=outcome + (f": {why['why']}" if outcome == "declined" and why.get("why") else ""),
            ),
        )
    defect_fix_modes.end(config, stage_name)
    broke = engineering.after_a_fix(
        state["repository"].root_path, fix_base, stage_name, defect.description,
        contested=_a_contested_test_past_repair(state, cycle),
        on_revert=lambda lost: kept_fix_candidates.keep(
            repo, fix_base, defect, stage_name, lambda: _the_defect_s_tests_pass(repo, defect), lost),
    )
    # Ended worse than the best version it reached - reverted, or its own tests failing again: that version, measured
    # in its place (A3).
    from app.graph import best_checkpoint
    from app.graph.workflow import _the_defect_s_tests_in

    instead = best_checkpoint.instead_of(
        repo, config["configurable"].get(APP_RUN_ID_KEY), stage_name, fix_base, broke,
        lambda: _the_defect_s_tests_in(str(repo), f"after {stage_name}", defect),
        lambda against: engineering.after_a_fix(
            str(repo), against, stage_name, defect.description, contested=_a_contested_test_past_repair(state, cycle)),
    )
    from app.observability import defect_ledger

    if instead is not None:
        defect_ledger.note(
            "best checkpoint", stage_name, defect=defect, round_=state.get("test_round", 0), index=defect_index,
            sprint=state.get("current_sprint_index", 0),
            detail="its best version, where its own tests passed, was measured in place of how it ended: "
                   + (f"it broke {len(instead)} test(s) too, so the stage is reverted" if instead else "kept"),
        )
        if broke:
            broke = instead

    _note_the_bundled(
        co_defects, defect_index=defect_index, stage_name=stage_name,
        round_=state.get("test_round", 0), sprint=state.get("current_sprint_index", 0),
    )
    if broke:
        defect_ledger.note(
            "reverted", stage_name, defect=defect, round_=state.get("test_round", 0), index=defect_index,
            sprint=state.get("current_sprint_index", 0),
            detail=f"broke {len(broke)} test(s) that passed before it: {'; '.join(broke[:3])}",
        )
        noted = _one_more_failed_fix(_noted_as_reverted(cycle, [defect_index], broke), defect_index)
        noted = _with_the_attempt(noted, defect_index, stage_name, fix_result, f"reverted: it broke {'; '.join(broke[:3])}",
                                  defect_budget.calls_in(config["configurable"].get(APP_RUN_ID_KEY), stage_name, started))
        contested = _a_locked_test_two_fixes_broke(noted)
        if contested and _a_dispute_may_be_held_now(state, also=[contested]):
            logger.warning(
                "Two fixes were reverted for breaking the locked test %s; the QA lead "
                "judges the failing locked tests before the round goes on", contested,
            )
            return _handing_on(**{
                **update,
                "remediation": noted,
                "defect_cursor": defect_index + 1,
                "fix_base_commit": "",
                "stage": "acceptance_dispute",
                "dispute_returns_to": "test_and_triage",
                "dispute_reason": (
                    f"Fixes for these failures were reverted, twice, because each broke "
                    f"`{contested}`, which passed before. Two locked tests may ask for "
                    "opposite things: a test that cannot pass while another one does is "
                    "one to name."
                ),
            })
        return _handing_on(**{
            **update,
            "remediation": noted,
            "defect_cursor": defect_index + 1,
            "fix_base_commit": "",
        })
    settled, blames = _settle_the_fix(
        state, cycle, defect_index, stage_name, fix_result, measured=f"after {stage_name}",
    )
    if settled.get("remediation") is not None:
        after = settled["remediation"].defects[defect_index]
        settled["remediation"] = _with_the_attempt(
            settled["remediation"], defect_index, stage_name, fix_result,
            "fixed" if str(getattr(after, "status", "")) == "fixed" else "left open: its tests still fail",
            defect_budget.calls_in(config["configurable"].get(APP_RUN_ID_KEY), stage_name, started),
        )
    update.update(settled)
    update.update(_the_unit_tests_a_kept_fix_broke(state))
    if blames and _a_dispute_may_be_held_now(state):
        # The fix stage left its defect open and says a locked test is
        # what cannot pass - in its blockers, or among its decisions beside
        # a change that did not make it pass. That is the QA lead's to
        # judge, now - not after the attempt has spent its rounds on it.
        # See `_a_dispute_may_be_held_now`.
        logger.warning(
            "Stage %s left its defect open and blames the locked suite; the QA lead "
            "judges its failing tests before the round goes on", stage_name,
        )
        update["defect_cursor"] = defect_index + 1
        return _handing_on(**{**update, "stage": "acceptance_dispute", "dispute_returns_to": "test_and_triage"})
    # Advance past this defect whether or not it closed. A defect left open
    # (no regression test named) must not be retried inside this round; the
    # next test round counts it as another failed attempt, keeping the loop
    # bounded by MAX_REMEDIATION_ATTEMPTS.
    update["defect_cursor"] = defect_index + 1
    return update


def defect_remediation_node(state: WorkflowGraphState, config: RunnableConfig, ctx: GraphContext) -> dict[str, Any]:
    """Route open defects to the specialists who own them, then re-test.

    This is steps 4, 5 and 6 of the plan's loop. In linear mode defects are
    handled one at a time, `defect_cursor` marking progress, so a pause for
    approval midway resumes on the same defect instead of restarting the
    whole round. In parallel mode defects whose files do not meet are fixed
    side by side, as work orders are built (`_the_next_fix_batch`).

    A fix is only recorded as fixed when the specialist names a regression
    test (`mark_defect_fixed` enforces this). A fix with no named test
    leaves the defect open, which costs a remediation attempt on the next
    test round rather than silently closing an unverified fix.
    """
    from app.graph.workflow import _fixes_run_side_by_side

    # A batch already in flight is finished as a batch, whatever the mode reads now. Found in the launch review:
    # the mode is read at each visit, so switching to linear mid-batch left `fix_batch` set, never cleared, and a
    # later parallel visit re-entered it with old indices in a new round.
    if _fixes_run_side_by_side() or state.get("fix_batch"):
        return _the_next_fix_batch(state, config, ctx)

    cycle = state["remediation"]
    cursor = state.get("defect_cursor", 0)

    # Scan forward by absolute index rather than indexing into a list of
    # open defects: marking one fixed changes which defects are open, so a
    # position in that list would shift under us and skip a defect.
    defect_index = cursor
    while defect_index < len(cycle.defects) and cycle.defects[defect_index].status != "open":
        defect_index += 1

    if defect_index >= len(cycle.defects):
        # Every defect has been worked this round; go back and re-run tests.
        return {"stage": "test_and_triage", "defect_cursor": 0}
    return _fix_one(state, config, defect_index, ctx)


def _the_next_fix_batch(state: Any, config: RunnableConfig, ctx: GraphContext) -> dict[str, Any]:
    """Parallel mode: the next defects to fix, side by side, or the one to resume or fix alone.

    Sprint 1 of one run spent three hours on eleven fix stages one after
    another, against a model server that answered several requests at once.
    Defects whose files do not meet - and whose bundled related failures do
    not either - are fixed together, at most `max_parallel()`, exactly as
    work orders are staggered (`_that_do_not_share_a_file`). The workspace
    is committed once before the batch and measured once after it: a batch
    that broke what passed before is reverted whole, and its defects are
    then fixed one at a time in the same round, where a fix that breaks
    something is told so on its own.
    """
    from app.graph.workflow import (
        _closed_if_an_earlier_fix_resolved_it, _defects_to_fix_together, _the_stage_that_paused,
        _with_tried,
    )

    cycle = state["remediation"]
    if state.get("fix_batch"):
        # A batch in flight - a resume after one of its fixers paused.
        return {"stage": "defect_fix_parallel"}
    paused = _the_stage_that_paused(state)
    if paused and paused.startswith("defect_fix_"):
        # A defect being fixed alone paused for approval: it resumes alone.
        return _with_tried(state, _fix_one(state, config, int(paused.rsplit("_", 1)[1]), ctx), paused)
    tried = set(state.get("fixes_tried") or [])
    alone = set(state.get("fixes_one_at_a_time") or [])

    def name(index: int) -> str:
        return f"defect_fix_{state.get('test_round', 0)}_{index}"

    candidates = [
        index for index, defect in enumerate(cycle.defects)
        if defect.status == "open" and name(index) not in tried
    ]
    # A defect that has spent its calls is not fixed again, side by side or
    # alone (plan AY step 4): the batch never asked, and sent it on.
    from app.graph import defect_budget

    for index in list(candidates):
        spent_out = defect_budget.spent_out(cycle, index)
        if spent_out:
            from app.observability import defect_ledger

            defect_ledger.note(
                "left open", name(index), defect=cycle.defects[index], round_=state.get("test_round", 0),
                index=index, sprint=state.get("current_sprint_index", 0), detail=spent_out,
            )
            return _with_tried(state, {}, name(index))
    if not candidates:
        return {"stage": "test_and_triage", "defect_cursor": 0, "fixes_tried": [], "fixes_one_at_a_time": []}
    for index in candidates:
        closed = _closed_if_an_earlier_fix_resolved_it(state, cycle, index)
        if closed is not None:
            return _with_tried(state, closed, name(index))
    lone = [index for index in candidates if name(index) in alone]
    if lone:
        return _with_tried(state, _fix_one(state, config, lone[0], ctx), name(lone[0]))
    chosen = _defects_to_fix_together(cycle, candidates)
    if len(chosen) == 1:
        return _with_tried(state, _fix_one(state, config, chosen[0], ctx), name(chosen[0]))
    from app.graph import engineering

    base = engineering.before_a_fix(
        state["repository"].root_path, f"defect_fix_{state.get('test_round', 0)}_batch"
    )
    logger.info("Fixing %d defects side by side: %s", len(chosen), ", ".join(map(name, chosen)))
    return {"stage": "defect_fix_parallel", "fix_batch": chosen, "fix_base_commit": base,
            "fix_batch_started": defect_budget.now()}


def defect_fix_worker_node(state: dict, config: RunnableConfig, ctx: GraphContext) -> dict[str, Any]:
    """One defect's fixer, in a batch fixed side by side. See `_the_next_fix_batch`."""
    from app.graph.workflow import (
        APP_RUN_ID_KEY, _a_revert_escalates_this_fix, _as_a_queued_pause, _only_this_worker_s_pause,
        _run_gated_agent, _the_defect_s_tests_pass, create_specialist_agent, failed_fix_tries,
    )

    index = state["__fix_index"]
    cycle = state["remediation"]
    defect = cycle.defects[index]
    stage_name = f"defect_fix_{state.get('test_round', 0)}_{index}"
    agent = create_specialist_agent(
        defect.owner, model=ctx.the_build_model(
            state, stage_name, failed_fix_tries(cycle, index), reasons=True,
            after_a_revert=_a_revert_escalates_this_fix(cycle, index),
        ),
        checkpointer=ctx.checkpointer, repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories,
    )
    request, _ = _the_fix_request(state, config, cycle, index)
    temp_state: Any = dict(state)
    # A worker may only answer its own approval gate: see `specialist_worker_node`.
    temp_state.update(_only_this_worker_s_pause(state, stage_name))
    # Each write followed by the defect's own tests, as when fixed alone (plan AY step 3).
    from app.graph import verify_after_write

    root = Path(state["repository"].root_path)
    from app.graph import batch_file_claims

    with verify_after_write.watching(
        config["configurable"].get(APP_RUN_ID_KEY), stage_name, lambda: _the_defect_s_tests_pass(root, defect),
    ), batch_file_claims.holding(config["configurable"].get(APP_RUN_ID_KEY), stage_name):
        update = _run_gated_agent(
            temp_state, config, stage_name=stage_name, agent=agent, initial_request=request,
            output_key="__fix_result__", next_stage="defect_remediation",
        )
    answered_in_a_batch = bool((state.get("queued_decisions") or {}).get(stage_name))
    if "__fix_result__" not in update:
        # Queued, not returned, for the reason `specialist_worker_node` gives.
        return {"specialist_pauses": {stage_name: _as_a_queued_pause(
            state, stage_name, update, answered=answered_in_a_batch
        )}}
    finished: dict[str, Any] = {"specialist_outputs": {stage_name: update["__fix_result__"]}}
    if answered_in_a_batch:
        finished["specialist_pauses"] = {stage_name: None}
    return finished


def defect_fix_gather_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
    """Where a batch of fixes joins: surface a pause, or measure the batch once and settle each fix."""
    from app.graph.workflow import (
        APP_RUN_ID_KEY, _QUEUED_AT, _a_dispute_may_be_held_now, _bundle_co_defects, _fix_batch_pending,
        _handing_on, _note_the_bundled, _noted_as_reverted, _put_back_a_deliberate_change, _queued_pauses,
        _settle_the_fix, _the_pause_to_surface, _the_unit_tests_a_kept_fix_broke, _with_the_attempt,
    )

    pauses = _queued_pauses(state)
    if pauses:
        first = _the_pause_to_surface(pauses)
        surfaced = {key: value for key, value in pauses[first].items() if key != _QUEUED_AT}
        return {**surfaced, "specialist_pauses": {first: None}, "queued_decisions": {}}
    if _fix_batch_pending(state):
        return {
            "stage": "defect_fix_parallel",
            "pending_decision": None,
            "pending_inner_thread_id": None,
            "pending_approval": None,
            "queued_decisions": {},
        }
    from app.graph import engineering
    from app.observability import defect_ledger

    # Before the batch is measured: a mutation check cut short left its change (plan QM.2).
    _put_back_a_deliberate_change(state)
    cycle = state["remediation"]
    batch = list(state.get("fix_batch") or [])
    round_ = state.get("test_round", 0)
    names = [f"defect_fix_{round_}_{index}" for index in batch]
    outputs = state.get("specialist_outputs") or {}
    # Each fixer's change told apart by the files it wrote, newest writer first: a broken batch is put back fixer by
    # fixer until what is left breaks nothing, and only those put back are reverted (A3).
    from app.graph import batch_file_claims

    run_id = config["configurable"].get(APP_RUN_ID_KEY)
    fixers = sorted(
        ((name, batch_file_claims.written_by(run_id, name)) for name in names),
        key=lambda fixer: -batch_file_claims.last_write_at(run_id, fixer[0]),
    )
    broke, put_back = engineering.after_a_batch(
        state["repository"].root_path, str(state.get("fix_base_commit") or ""),
        f"defect_fix_{round_}_batch",
        "; ".join(str(cycle.defects[index].description)[:40] for index in batch), fixers,
    )
    batch_file_claims.forget(run_id, names)
    tried = list(dict.fromkeys([*(state.get("fixes_tried") or []), *names]))
    for index, stage_name in zip(batch, names):
        _note_the_bundled(
            _bundle_co_defects(cycle, index), defect_index=index, stage_name=stage_name,
            round_=round_, sprint=state.get("current_sprint_index", 0),
        )
    reverted = [(index, stage_name) for index, stage_name in zip(batch, names) if stage_name in put_back]
    if broke:
        whole = len(reverted) == len(batch)
        for index, stage_name in reverted:
            defect_ledger.note(
                "reverted", stage_name, defect=cycle.defects[index], round_=round_, index=index,
                sprint=state.get("current_sprint_index", 0),
                detail=(f"its batch broke {len(broke)} test(s) that passed before it" if whole else
                        f"its change broke {len(broke)} test(s) that passed before the batch; the rest of the batch "
                        "was kept") + f": {'; '.join(broke[:3])}; fixed alone next",
            )
        logger.warning(
            "Reverted %d of a batch of %d fixes: it broke %d test(s); fixing them one at a time",
            len(reverted), len(batch), len(broke),
        )
        cycle = _noted_as_reverted(cycle, [index for index, _ in reverted], broke, in_a_batch=whole)
        alone_next = sorted({*(state.get("fixes_one_at_a_time") or []), *(name for _, name in reverted)})
        if whole:
            return _handing_on(
                stage="defect_remediation", remediation=cycle, fix_batch=[], fix_base_commit="",
                fixes_one_at_a_time=alone_next,
            )
    settled_cycle = cycle
    blamed = False
    update: dict[str, Any] = {}
    if broke:
        update["fixes_one_at_a_time"] = alone_next
    for index, stage_name in zip(batch, names):
        if stage_name in put_back:
            continue
        result = outputs.get(stage_name)
        if result is None:
            continue
        settled, blames = _settle_the_fix(
            {**state, "specialist_outputs": {**outputs, **update.get("specialist_outputs", {})}},
            settled_cycle, index, stage_name, result, measured=f"after defect_fix_{round_}_batch",
        )
        if settled.get("remediation") is not None:
            # Recorded as a fix alone records it, so the call cap and the next
            # fixer's earlier attempts see a batched attempt too.
            from app.graph import defect_budget

            after = settled["remediation"].defects[index]
            settled["remediation"] = _with_the_attempt(
                settled["remediation"], index, stage_name, result,
                "fixed" if str(getattr(after, "status", "")) == "fixed" else "left open: its tests still fail",
                defect_budget.calls_in(config["configurable"].get(APP_RUN_ID_KEY), stage_name,
                                       str(state.get("fix_batch_started") or "")),
            )
        settled_cycle = settled["remediation"]
        update["specialist_outputs"] = settled["specialist_outputs"]
        blamed = blamed or blames
    update.update(remediation=settled_cycle, fix_batch=[], fix_base_commit="", fix_batch_started="", fixes_tried=tried)
    update.update(_the_unit_tests_a_kept_fix_broke(state))
    if blamed and _a_dispute_may_be_held_now(state):
        logger.warning("A fix in the batch blames the locked suite; the QA lead judges its failing tests")
        return _handing_on(**update, stage="acceptance_dispute", dispute_returns_to="test_and_triage")
    return _handing_on(**update, stage="defect_remediation")
