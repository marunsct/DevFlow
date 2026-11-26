"""The fix stage: one defect at a time, or, in parallel mode, a batch fixed side by side.

    defect_remediation -> (defect_fix_worker x N -> defect_fix_gather) -> test_and_triage

See `app.graph.nodes` for how these are registered and why their helpers are
imported from `app.graph.workflow` when they run.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from langchain_core.runnables import RunnableConfig

from app.observability.degraded import degraded
from app.graph import acceptance_nodes, mutation_gaps_bundled
from app.graph.context import GraphContext
from app.graph.workflow import WorkflowGraphState

#: The workflow's logger: the nodes log as they did inside the builder.
logger = logging.getLogger("app.graph.workflow")


def _the_fix_request(
    state: Any, config: RunnableConfig, cycle: Any, defect_index: int, model: Any = None, framing: int = 0,
) -> tuple[dict[str, Any], list[tuple[int, Any]]]:
    """What one defect's fixer is asked, and the related failures bundled with it.

    Its actual behaviour, its failing tests' output and the server's log are the latest measurement's
    (`fresh_evidence`). A request that, with the project memory it is given, is past its size target opens with the
    defect's evidence and the round's shared cause, and carries its standing context cut to what the defect touches
    (`fixer_request_shape`, LF.1270); one under it is as built. `model`: the fixer's, whose window sets the target;
    `framing`: its agent's system prompt and tool descriptions, which the target leaves room for (FX.3).

    Where the failure is handled is found first and named with its evidence (`localised_fix`, FX.2); its failing
    tests' output is printed once for each way they failed (`lean_fixer.failures_once`, FX.3).
    """
    from app.graph.workflow import (
        APP_RUN_ID_KEY, _bundle_co_defects, _the_database_section, _the_last_attempt_section,
        _the_specification_for_the_fix, _the_stub_still_served_section, _the_unserved_code_section,
        _what_a_fix_stage_must_leave_alone, _what_the_criteria_s_tests_printed,
        _what_the_last_failure_printed, _what_the_unit_tests_printed, build_defect_fix_request,
        defect_fix_modes, mutation_guided, with_the_facts,
    )
    from app.graph import fixer_request_shape as shape
    from app.graph import fresh_evidence
    from app.graph.fixer_request_shape import EVIDENCE, KEPT, STANDING, Part

    defect = cycle.defects[defect_index]
    root = state["repository"].root_path
    from app.acceptance import probes_at_release
    from app.acceptance.junit import tags_in

    co_defects = _bundle_co_defects(cycle, defect_index)
    # What the latest measurement says of it, not what the round that raised it said (LF.1270).
    shown = fresh_evidence.as_shown(root, defect, cycle.defects)
    brief_args = (
        shown.description,
        shown.reproduction_steps,
        shown.expected_behavior,
        shown.actual_behavior,
        shown.affected_files,
        shown.regression_test_required,
        root,
        getattr(state.get("stack_selection"), "technology_stack", None),
        # What the failing command actually printed, alongside the prose
        # description of it. See `build_defect_fix_request`.
        # A failing criterion's own tests first: the last failing command may be another criterion's.
        _what_the_criteria_s_tests_printed(root, defect)
        or fresh_evidence.what_its_tests_printed_now(root, defect)
        or _what_the_unit_tests_printed(root, defect)
        or _what_the_last_failure_printed(config["configurable"].get(APP_RUN_ID_KEY), defect),
    )
    brief_kwargs = dict(
        caught_by=getattr(defect, "caught_by", ""),
        # Only for a defect that is not itself a failing criterion - nor a
        # mutation finding, whose product is not wrong (plan QM.2) - nor a harness probe's finding, whose product is.
        done_already=(
            []
            if [t for t in tags_in(str(defect.description or "")) if t.startswith(("AC-", "CR-"))]
            or mutation_guided.is_a_finding(defect)
            or probes_at_release.carries_a_finding(defect)
            else acceptance_nodes.done_by_the_definition(state)
        ),
        what_settles_it=mutation_guided.what_settles_it(defect, mutation_gaps_bundled.not_bundled(cycle.defects, co_defects)),
    )
    # Each way its tests failed printed once, the other tests failing the same way one line each (FX.3).
    from app.agents import lean_fixer

    shown_args = (*brief_args[:8], lean_fixer.failures_once(brief_args[8]))
    request = build_defect_fix_request(*shown_args, **brief_kwargs)
    # A fixer is not offered the page viewer (FX.3): the section naming it is not its own.
    from app.agents.specialists import LOOK_BEFORE_CHANGING_THE_PAGE

    request["messages"][-1]["content"] = request["messages"][-1]["content"].replace(LOOK_BEFORE_CHANGING_THE_PAGE, "", 1)
    brief = request["messages"][-1]["content"]
    # Each part as it is added, for a request past its size target to be put in another order and cut.
    parts: list[Part] = []
    try:
        from app.agents.specialists import defect_fix_brief_parts

        pieces = defect_fix_brief_parts(*shown_args, **brief_kwargs)
        pieces["page"] = pieces["page"].replace(LOOK_BEFORE_CHANGING_THE_PAGE, "", 1)
        if "".join(pieces.values()) == brief:
            parts += [Part(KEPT, pieces["workspace"]), Part(STANDING, pieces["setup"]), Part(EVIDENCE, pieces["evidence"]),
                      Part(STANDING, pieces["page"]), Part(KEPT, pieces["settled"])]
    except Exception:  # noqa: BLE001 - the brief is one part
        parts = []
    if not parts:
        parts.append(Part(EVIDENCE, brief))

    def add(kind: str, text: str, cut: str | None = None) -> None:
        request["messages"][-1]["content"] += text
        if text:
            parts.append(Part(kind, text, cut))

    def added_by(change: Any) -> None:
        """What `change(request)` put before or after the request's text, as a standing part."""
        nonlocal request
        before = request["messages"][-1]["content"]
        request = change(request)
        after = request["messages"][-1]["content"]
        if not isinstance(after, str) or after == before:
            return
        if after.startswith(before):
            parts.append(Part(STANDING, after[len(before):]))
        elif after.endswith(before):
            parts.insert(0, Part(STANDING, after[: len(after) - len(before)]))

    left_alone = _what_a_fix_stage_must_leave_alone(state, defect)
    request["messages"][-1]["content"] += left_alone
    parts.extend(shape.split_mixed(left_alone))
    # What this attempt may write: test files only, for a first fix of a failing unit test beside a green suite.
    add(KEPT, defect_fix_modes.briefing(state, config, defect_index))
    # What the failing unit tests' own files show: a stand-in hiding a rule the locked suite shows the product keeps
    # (LF.1312), or tests that count records other tests of their file stored (LF.1316).
    add(KEPT, _what_the_failing_unit_tests_show(root, defect))
    specification = _the_specification_for_the_fix(state, defect, co_defects)
    add(STANDING, specification, cut=_the_specification_cut(state, specification, brief_args[8], shown))
    add(EVIDENCE, _the_bundled_section(co_defects, root, cycle.defects))
    # Its criterion's tests run on their own now, a server error nothing logged, the tests held for the QA lead (FX.1,
    # FX.7, FX.11).
    from app.graph import first_failure

    add(EVIDENCE, first_failure.for_a_fixer(state, defect))
    # Where the failure is handled: the route its tests reached, the product's frames in a trace, or one cheap
    # localisation call when neither places it and the defect names no file (FX.2).
    from app.graph import localised_fix

    named = [*(defect.affected_files or []), *(f for _, d in co_defects for f in (d.affected_files or []))]
    stage = f"defect_fix_{state.get('test_round', 0)}_{defect_index}"
    # Once a fixer: not on each resume of its stage after a gated tool call, alone or in a batch.
    first_visit = not state.get("pending_inner_thread_id") and not (state.get("queued_decisions") or {}).get(stage)
    located = localised_fix.where(
        root, "".join(p.text for p in parts if p.kind == EVIDENCE) + str((brief_args[8] or {}).get("output") or ""),
        named=named, defect=defect, model=model, ask=first_visit)
    add(EVIDENCE, localised_fix.section(located))
    if first_visit:
        localised_fix.noted(stage, located, defect)
    # A defect on its last permitted attempt gets a different shape of
    # work, not a third variation of the instruction that failed twice.
    # See `_the_last_attempt_section`.
    add(KEPT, _the_last_attempt_section(cycle, defect_index))
    # Each earlier attempt as measured (plan PH.2), not a revert sentence.
    from app.agents import ledger as _ledger

    add(KEPT, _ledger.earlier_attempts(defect, cycle.defects[:defect_index]))
    # What the changes reverted before this one broke: each test with its runner's words, and the change (LF.1547).
    from app.graph import what_a_revert_broke

    add(EVIDENCE, what_a_revert_broke.told(root, defect))
    # What was tried on its cause in earlier cycles too: a re-plan clears the cycle, not the journal (deep review 1.4).
    from app.graph import cause_journal

    add(KEPT, cause_journal.tried_before(root, defect, shown=(defect.attempts if _ledger.enabled() else ())))
    add(KEPT, _what_others_found(state, defect, defect_index, cycle, model, first_visit=first_visit))  # WL.4
    # The toolchain here and the versions the project resolved, mismatches first, in two lines (HK.1, HK.2).
    from app.stacks import stack_facts

    add(KEPT, stack_facts.for_a_fixer(root))
    # The installed API of libraries newer than the model, for the defect's files that use one (plan HK.7).
    from app.stacks import api_cards

    add(STANDING, api_cards.for_a_fixer(root, [*(defect.affected_files or []), *(f for _, d in co_defects for f in (
        d.affected_files or []))], "".join(p.text for p in parts if p.kind == EVIDENCE), model))
    # The web tools, for a fixer whose defect failed twice (plan WL.5, its switch): offered with the agent.
    from app.graph import web_tools_after_two_failed_fixes

    add(KEPT, web_tools_after_two_failed_fixes.said(cycle, defect_index, root))
    add(KEPT, _the_stub_still_served_section(root))
    # The files its evidence names and what they import: the facts about other files are cut past the target.
    touched = shape.the_files_it_touches(root, "".join(p.text for p in parts if p.kind == EVIDENCE), [
        *(defect.affected_files or []), *(f for _, d in co_defects for f in (d.affected_files or [])),
        *located.files])
    unserved = _the_unserved_code_section(root)
    add(STANDING, unserved, cut=shape.the_facts_cut(unserved, touched))
    add(STANDING, _the_database_section(root))
    # The layout the judges read too (plan CM.1); the stub and the code the product does not run are above.
    before = request["messages"][-1]["content"]
    request = with_the_facts(request, root, built=False)
    facts = request["messages"][-1]["content"][len(before):]
    # The rulings and the fixes undone for a start that broke bind every stage: kept whole; the layout facts are cut.
    parts.extend(shape.split_facts(facts, touched))
    # Where the sprint stands (plan PH.1, off until measured).
    from app.agents import where_things_stand

    added_by(lambda r: where_things_stand.with_it(r, state))
    # The defect's files' neighbours in the code graph (plan CG.2, off until measured).
    from app.analysis import project_graph

    added_by(lambda r: project_graph.with_the_neighbourhood(r, root, [
        *(defect.affected_files or []), *(f for _, d in co_defects for f in (d.affected_files or []))]))
    # Past its target, the standing sections that do not bear on this defect go first (FX.3).
    touches = lean_fixer.bearing_on(touched, shape.routes_called([
        str((brief_args[8] or {}).get("output") or ""), str(getattr(shown, "actual_behavior", "") or ""),
        str(getattr(shown, "reproduction_steps", "") or "")]), tags_in(str(defect.description or "")))
    request = _sized_to_its_target(request, parts, state, cycle, defect_index, model, framing=framing,
                                   touches=touches)
    # The page as a person sees it, for a build model that reads images:
    # only the reviewer was shown it. Last, as it makes the request's text
    # a list of parts.
    from app.agents.page_screenshots import with_the_page_for_a_fixer

    request = with_the_page_for_a_fixer(request, root)
    # What this fixer was shown, so a later try can be compared with it (deep review F9): once a fixer, not on
    # each resume of its stage after a gated tool call (measured: every 6 to 10 seconds for one fixer).
    from app.observability import defect_ledger

    if not state.get("pending_inner_thread_id"):
        defect_ledger.shown(
            f"defect_fix_{state.get('test_round', 0)}_{defect_index}", defect, request["messages"][-1]["content"],
            round_=state.get("test_round", 0), index=defect_index, sprint=state.get("current_sprint_index", 0),
        )
    return request, co_defects


def _framing_of(agent: Any) -> int:
    """The characters of a fixer agent's system prompt and tool descriptions as built (`create_role_agent`); 0 when
    it does not say."""
    framing = getattr(agent, "workflow_framing", 0)
    return framing if isinstance(framing, int) else 0


def _what_the_failing_unit_tests_show(root: Any, defect: Any) -> str:
    """`stand_in_tests` and `shared_store_tests` for a defect about the project's own failing unit tests; "" for any
    other."""
    try:
        from app.analysis import shared_store_tests, stand_in_tests
        from app.graph import settle_when_green

        if not settle_when_green._a_unit_test_failure(defect, settle_when_green.the_acceptance_command(root)):
            return ""
        return stand_in_tests.for_a_fixer(root, defect) + shared_store_tests.for_a_fixer(root, defect)
    except Exception:  # noqa: BLE001 - the request goes without it
        return ""


def _the_specification_cut(state: Any, specification: str, observed: Any, shown: Any) -> str | None:
    """The specification's part of a fix request with its API cut to the routes the defect's failing tests call; None
    when no route can be read, or no endpoint matches (the whole API is then the one shown)."""
    from app.graph import fixer_request_shape as shape

    return shape.specification_cut(state.get("technical_specification"), specification, [
        str((observed or {}).get("output") or ""), str(getattr(shown, "actual_behavior", "") or ""),
        str(getattr(shown, "reproduction_steps", "") or ""),
    ])


def _sized_to_its_target(request: dict[str, Any], parts: list[Any], state: Any, cycle: Any, defect_index: int,
                         model: Any, framing: int = 0, touches: Any = None) -> dict[str, Any]:
    """`request` as built when it and its project memory are within the size target; reshaped past it (LF.1270).
    The target leaves room for the fixer's `framing` within half its summary trigger, and past it the standing
    sections `touches` says do not bear on the defect go first (FX.3). Never raises: the request as built."""
    try:
        from app.agents import project_memory, request_budget
        from app.graph import fixer_request_shape as shape

        content = request["messages"][-1]["content"]
        target = request_budget.fixer_target(model, framing)
        stage = f"defect_fix_{state.get('test_round', 0)}_{defect_index}"
        # Once a fixer, as its `shown` record: not on each resume of its stage after a gated tool call.
        first_visit = not state.get("pending_inner_thread_id")
        if len(content) > target:
            memory = 0  # past it on its own: the memory is cut whatever it would be
        else:
            if not project_memory.enabled():
                if first_visit:
                    request_budget.noted(stage, built=len(content), target=target)
                return request
            memory = len(project_memory.render_for_a_stage(state["repository"].root_path, model, content, stage,
                                                           framing=framing)[0])
            if memory + 2 + len(content) <= target:
                if first_visit:
                    request_budget.noted(stage, built=len(content) + memory + 2, target=target)
                return request
        least = int(target * shape.MEMORY_LEAST_SHARE) if project_memory.enabled() else 0
        if least:
            # Room to hold where the failure is handled whole (FX.2): what does not bear on the defect makes way.
            from app.graph import localised_fix

            least = max(least, localised_fix.room_for(state["repository"].root_path, content, target))
        # The round that raised this round's defects: a fix stage runs under the next round's number.
        raised_in = int(state.get("test_round", 0) or 0) - 1
        cause = shape.the_round_s_cause(cycle, defect_index, raised_in if raised_in >= 0 else None)
        fitted = request_budget.fit(parts, target=target, memory=least, cause=cause, touches=touches)
        shaped = fitted.text
        if first_visit:
            # With the memory it is given then, as `project_memory.render_for_a_stage` cuts it for a reshaped request.
            given = (len(project_memory.render_for_a_stage(state["repository"].root_path, model, shaped, stage,
                                                           framing=framing)[0]) + 2
                     if project_memory.enabled() else 0)
            request_budget.noted(stage, built=len(content) + (memory + 2 if memory else 0), sent=len(shaped) + given,
                                 target=target, fitted=fitted)
        logger.info("Fix request for defect %d is past its size target (%d characters with its memory, target %d); "
                    "evidence first, standing context cut to %d characters", defect_index,
                    len(content) + memory, target, len(shaped))
        request["messages"][-1]["content"] = shaped
    except Exception:  # noqa: BLE001 - the request as built
        logger.debug("Could not size the fix request to its target", exc_info=True)
    return request


def _the_bundled_section(co_defects: list[tuple[int, Any]], root: Any = None, defects: Any = ()) -> str:
    """The related failures bundled with a fix, as its fixer is shown them; "" when none.

    Mutation findings in the same file are listed with their line, change and what settles each
    (`MUTATION_GAPS_BUNDLED`); any other related failure with what it expected and what happened - as the latest
    measurement says it (`fresh_evidence`).
    """
    from app.acceptance import mutation_guided
    from app.graph import fresh_evidence

    others = [(pos, d) for pos, d in co_defects if not mutation_guided.is_a_finding(d)]
    lines = []
    if others:
        lines = [
            "\n--- Related failures owned by your role to resolve in this same fix ---",
            "The harness measures each one after your fix; one still failing goes to its own fix.",
        ]
        for pos, co_d in others:
            lines.append(f"- Failure {pos + 1}: {co_d.description}")
            lines.append(f"  Expected: {co_d.expected_behavior}")
            lines.append(f"  Actual: {fresh_evidence.actual_behavior_now(root, co_d, defects)}")
    return ("\n".join(lines) + "\n" if lines else "") + mutation_gaps_bundled.section(co_defects)


def _what_others_found(state: Any, defect: Any, defect_index: int, cycle: Any = None, model: Any = None, *,
                       first_visit: bool = True) -> str:
    """What others found for a fixer's error (plan WL.4, behind its switch): an install's error the registry does not
    explain (T2), a build error the round before had too (T3), or the error of a defect an attempt left open (T1).
    `model`, the fixer's, makes the one condensing call when `STUCK_LOOKUP_CONDENSED` is on (plan HK.3).
    `first_visit` false on a resume of the stage: the same block, its ledger records not written again (LF.1506)."""
    from app.analysis import installed_usage
    from app.graph import stuck_lookup

    round_ = int(state.get("test_round", 0) or 0)
    return stuck_lookup.for_a_fixer(
        state["repository"].root_path, defect, list(getattr(cycle, "defects", None) or [defect]),
        getattr(state.get("stack_selection"), "technology_stack", None), round_=round_,
        sprint=int(state.get("current_sprint_index", 0) or 0), stage_name=f"defect_fix_{round_}_{defect_index}",
        model=model, first_visit=first_visit) + installed_usage.for_a_fixer(state["repository"].root_path, defect)  # FX.10, its switch


def _diagnosed_if_it_keeps_failing(state: Any, defect: Any, ctx: GraphContext) -> None:
    """One diagnosis-only call before the fix of a cause that has already failed twice, kept in the fix journal for the
    fixer to read (behind `DIAGNOSE_A_RECURRING_CAUSE`, deep review 1.4). Never raises."""
    try:
        from app.graph import cause_journal

        cause_journal.diagnosed(
            state["repository"].root_path, defect, str(getattr(defect, "actual_behavior", "") or ""),
            ctx.a_model_to_call(), sprint=state.get("current_sprint_index", 0),
        )
    except Exception:  # noqa: BLE001 - the fix goes on without it
        logger.debug("Could not diagnose before the fix", exc_info=True)


def _fixed_by_rewriting(
    state: Any, config: RunnableConfig, defect: Any, fix_model: Any, failed_tries: int = 0,
    after_a_surrender: bool = False, why: dict[str, str] | None = None, *, ctx: GraphContext,
    surrendered: Any = None, stage: str = "", since: str = "", beside: Callable[[str], str] | None = None,
) -> Any:
    """A fast-delivery fix by rewriting the defect's files, or None for the agent loop.

    After a failed fix, and with a judgement model of its own, several
    candidates are asked of the judgement model at once and the first the
    defect's tests pass is kept (`rewritten_fixes.fix_by_candidates`).

    After a surrender, `surrendered` is the answer of the stage `stage` that began at `since`: the files it wrote,
    tried to write or named are the rewrite's too (`surrender_evidence`, LF.1401), and a rewrite that finds no file
    says which rule left out which file (LF.1402). `beside`, for a fixer of a batch, names the other fixer that holds
    or wrote a file, which this rewrite then leaves alone (LF.1404).
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
    # Reverted twice for breaking the same test: not rewritten a third time; the tool-using fixer takes it (LF.1547).
    from app.graph import what_a_revert_broke

    again = what_a_revert_broke.repeated(state["repository"].root_path, defect)
    if again:
        from app.observability import defect_ledger

        defect_ledger.note("rewrite skipped", stage or "defect_fix", defect=defect, detail=again)
        declined(again)
        return None
    from types import SimpleNamespace

    from app.graph.rewritten_fixes import fix_by_candidates, fix_by_rewriting, files_to_fix, what_failed
    from app.tools.repository import _the_harness_s_own_or_the_locked_suite, just_asking

    from app.graph.bounded_fixes import the_candidate_model

    root = Path(state["repository"].root_path)
    # The rule that refused each file this stage may not write, for a decline to name (LF.1402).
    not_writable: dict[str, str] = {}

    def may_write(path: str) -> bool:
        with just_asking():
            if _the_harness_s_own_or_the_locked_suite(root, root / path) is not None:
                not_writable[path] = "the harness keeps it: the locked acceptance suite or the harness's own record"
                return False
            if not defect_fix_modes.may_write(state, config, defect, root, path):
                not_writable[path] = "this attempt may write tests only"
                return False
            other = beside(path) if beside is not None else ""
            if other:
                not_writable[path] = f"another fix of its batch is changing it ({other})"
                return False
            return True

    # The defect's own failing tests first, as the agent loop's request does (HR F3).
    from app.graph import fresh_evidence

    last_failure = (
        _what_the_criteria_s_tests_printed(str(root), defect)
        or fresh_evidence.what_its_tests_printed_now(str(root), defect)
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
    # The fix's own model, else the one its stage builds when the run names none: in a local run both the run's
    # model and its judgement model are None, and no candidate was ever asked (`context.a_model_to_call`).
    candidate_model = the_candidate_model(ctx.judgement_model, ctx.model, ctx.a_model_to_call(fix_model))
    if failed_tries >= 1 and candidate_model is not None and not after_a_surrender:
        try:
            from app.graph.localisation import localised

            failure = what_failed(defect, root, last_failure)
            located = localised(
                defect, failure, root, fix_model or ctx.model or ctx.building_model,
                files_to_fix(defect, failure, root, may_write), may_write,
            )
            # A stuck defect: as many candidates as the server has room for, each held to the regression set (PF.2).
            from app.graph import candidate_fixes_when_stuck

            count = candidate_fixes_when_stuck.width(failed_tries, located)
            stuck = candidate_fixes_when_stuck.Stuck(root, defect, stage, count) if count else None
            kept = fix_by_candidates(
                defect, root, candidate_model, lambda: _the_defect_s_tests_pass(root, defect),
                specification=state.get("technical_specification"),
                stack=getattr(state.get("stack_selection"), "technology_stack", None),
                last_failure=last_failure, may_write=may_write, files=located, co_defects=co_defects,
                kept=_the_fixes_to_keep_for(state, defect),
                **({"candidates": count, "holds": stuck.holds, "seed_base": failed_tries * 10} if stuck else {}),
            )
            if stuck is not None:
                stuck.note(kept is not None)
            if kept is not None:
                return kept
        except Exception as swallowed:  # noqa: BLE001 - one rewrite, or the agent loop, takes the defect
            degraded("fix.candidates", swallowed)
    # Candidates are in every delivery mode: they are kept only when the
    # defect's tests pass. A single rewrite in place of the agent loop is
    # fast delivery's.
    if not _fast_delivery() and not after_a_surrender:
        return None
    if after_a_surrender and located is None:
        # The files the fixer that gave up was aiming at are the rewrite's too, after the defect's own (LF.1401).
        from app.graph import surrender_evidence
        from app.graph.localisation import localised

        refused: dict[str, str] = {}
        try:
            failure = what_failed(defect, root, last_failure)
            aimed = surrender_evidence.aimed_at(config["configurable"].get(APP_RUN_ID_KEY), stage, since, surrendered)
            located = localised(
                defect, failure, root, fix_model or ctx.model or ctx.building_model,
                files_to_fix(defect, failure, root, may_write, aimed_at=aimed, refused=refused), may_write,
            )
        except Exception as error:  # noqa: BLE001 - the rewrite gathers for itself, as before
            degraded("fix.rewrite_after_surrender", error)
            located = None
        if located is not None and not located:
            declined(surrender_evidence.why_none({**refused, **{p: r for p, r in not_writable.items() if p in refused}}))
            return None
    # Read only when nothing is written; the rewrite says what each file came to (LF.1403).
    declined("the rewrite found no file it may write, or wrote none")
    told: dict[str, str] = {}
    try:
        rewritten = fix_by_rewriting(
            defect, root, fix_model or ctx.model or ctx.building_model,
            specification=state.get("technical_specification"),
            stack=getattr(state.get("stack_selection"), "technology_stack", None),
            last_failure=last_failure, may_write=may_write, files=located, co_defects=co_defects,
            kept=_the_fixes_to_keep_for(state, defect), why=told,
            diagnose=lambda files: _diagnostics_in_files_touched(
                state, {"messages": []}, SimpleNamespace(changed_files=files), most=MOST_DIAGNOSTICS_FOR_A_PASS,
            ),
        )
    except Exception as error:  # noqa: BLE001 - the agent loop takes the defect
        degraded("fix.rewrite", error)
        declined(f"the rewrite raised {type(error).__name__}")
        return None
    if rewritten is None and told.get("why"):
        declined(told["why"])
    return rewritten


def _repaired_forward(
    state: Any, config: RunnableConfig, defect: Any, fix_model: Any, asked: Any, files: list[str], *, ctx: GraphContext,
) -> Any:
    """The fix's own model rewriting only the files its fix changed, handed what the fix broke (LF.1271); None when
    declined: a run that does not approve its own writes, a mutation finding, or a rewrite that wrote nothing.

    Bounded by the rewrite's own limits (`rewritten_fixes.MOST_FILES` files, `MOST_PASSES` passes), and synchronous:
    the fix is still in the workspace, unjudged, so it cannot wait on an approval.
    """
    from app.graph.workflow import APP_RUN_ID_KEY, _the_run_approves_its_own_writes, mutation_guided

    if (not files or mutation_guided.is_a_finding(defect)
            or not _the_run_approves_its_own_writes(config["configurable"].get(APP_RUN_ID_KEY))):
        return None
    from app.graph.rewritten_fixes import fix_by_rewriting
    from app.tools.repository import _the_harness_s_own_or_the_locked_suite, just_asking

    root = Path(state["repository"].root_path)

    def may_write(path: str) -> bool:
        with just_asking():
            return path in files and _the_harness_s_own_or_the_locked_suite(root, root / path) is None

    try:
        return fix_by_rewriting(
            asked, root, fix_model or ctx.model or ctx.building_model,
            specification=state.get("technical_specification"),
            stack=getattr(state.get("stack_selection"), "technology_stack", None),
            may_write=may_write, files=[path for path in files if may_write(path)],
        )
    except Exception as error:  # noqa: BLE001 - reverted as before
        degraded("fix.repair_forward", error)
        return None


def _rewritten_after_a_surrender(
    state: Any, config: RunnableConfig, defect_index: int, stage_name: str, fix_model: Any, fix_result: Any,
    since: str, *, ctx: GraphContext, beside: Callable[[str], str] | None = None,
) -> Any:
    """`fix_result`, or the harness's rewrite's answer when it changed no file (behind `SURRENDER_TO_REWRITE`).

    An answer that changed no file - a surrender, or the harness's record of a fixer that gave no answer - goes to
    the rewrite once, fixed alone or in a batch (LF.1404: measured on one medium run, two batch fixers that read for
    17 and 19 calls and ended with no answer never got it). `beside`: a batch fixer's filter of the files another
    fixer of its batch holds."""
    from app.graph.surrender_to_rewrite import after_a_surrender
    from app.graph.workflow import failed_fix_tries
    from app.observability import defect_ledger

    defect = state["remediation"].defects[defect_index]
    tries = failed_fix_tries(state["remediation"], defect_index)
    why: dict[str, str] = {}
    return after_a_surrender(
        fix_result,
        lambda: _fixed_by_rewriting(state, config, defect, fix_model, tries, after_a_surrender=True, why=why, ctx=ctx,
                                    surrendered=fix_result, stage=stage_name, since=since, beside=beside),
        note=lambda outcome: defect_ledger.note(
            "rewrite after surrender", stage_name, defect=defect, index=defect_index,
            round_=state.get("test_round", 0),
            detail=outcome + (f": {why['why']}" if outcome == "declined" and why.get("why") else ""),
        ),
    )


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
    # A failing test no fix in this sprint can make pass goes to the QA lead before the fixer (FX.11, LF.1413).
    from app.graph import first_failure

    held = first_failure.held_as_a_dispute(state, cycle, defect_index)
    if held is not None:
        return held
    # A defect that has spent its calls across attempts is not fixed again
    # (plan AY step 4, off until measured).
    from app.graph import defect_budget

    spent_out = defect_budget.spent_out(cycle, defect_index, state["repository"].root_path)
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
    # Where the defect's tests fail as the fix finds them, to read its progress against (LF.1272).
    from app.graph import judged_fixes

    if not state.get("pending_inner_thread_id"):
        judged_fixes.remember_before(state["repository"].root_path, stage_name, defect)
    # The mode this fix runs in: what it may write, and what is kept of it (`app.graph.defect_fix_modes`).
    defect_fix_modes.begin(state, config, cycle, defect_index, stage_name)
    # Fast delivery: the harness gathers what failed and the files it points
    # at, and the model rewrites each file in one call. See
    # `app.graph.rewritten_fixes`; a defect it cannot place goes to the agent loop.
    # A reverted fix whose own tests passed is measured a second time first (behind `KEPT_FIX_CANDIDATES`).
    from app.graph import kept_fix_candidates

    repo = Path(state["repository"].root_path)
    if not state.get("pending_inner_thread_id"):
        _diagnosed_if_it_keeps_failing(state, defect, ctx)
    replay = None if state.get("pending_inner_thread_id") else kept_fix_candidates.replayed(repo, defect, stage_name)
    rewritten = None if state.get("pending_inner_thread_id") else (replay or _fixed_by_rewriting(
        state, config, defect, fix_model, failed_fix_tries(cycle, defect_index), ctx=ctx, stage=stage_name,
    ))
    # How the change measured below was made: a revert of the harness's own rewrite counts toward its repeats (LF.1547).
    made_by = "replay" if replay is not None else "rewrite" if rewritten is not None else "agent"
    if rewritten is not None:
        update: dict[str, Any] = {}
        co_defects: list[tuple[int, Any]] = []
        fix_result: SpecialistOutput = rewritten
    else:
        from app.graph import web_tools_after_two_failed_fixes

        agent = create_specialist_agent(
            defect.owner, model=fix_model,
            checkpointer=ctx.checkpointer, repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories,
            web_tools_for_this_fix=web_tools_after_two_failed_fixes.tools_for(
                cycle, defect_index, stage_name, root=state["repository"].root_path,
                resumed=bool(state.get("pending_inner_thread_id"))),
            fixing=True,
        )
        request, co_defects = _the_fix_request(state, config, cycle, defect_index, model=fix_model,
                                               framing=_framing_of(agent))
        # Each write followed by the defect's own tests (plan AY step 3, off until measured).
        from app.acceptance import mutant_check_in_stage
        from app.graph import verify_after_write

        root = Path(state["repository"].root_path)
        # A mutation finding's write is answered by its own change (`MUTANT_CHECK_IN_THE_FIX_STAGE`).
        check_after_a_write = mutant_check_in_stage.check_for(root, defect, lambda: _the_defect_s_tests_pass(root, defect))
        # A fix alone keeps the version its own tests passed at (A3, `best_checkpoint`); not a mutation finding's,
        # whose check is of its own change.
        # Still failing, the write's reply says how, and what the server printed (FX.7).
        how_after_a_write = mutant_check_in_stage.how_for(defect)
        if not how_after_a_write:
            # The tests that reach the files a write changed run before the defect's own (PF.3, `TESTS_REACHED_FIRST`).
            from app.graph import tests_reached_first

            check_after_a_write, how_after_a_write = tests_reached_first.first(
                root, fix_base, defect, check_after_a_write,
                {"checkpoints_in": root, "then": lambda: first_failure.after_a_write(root, defect)},
                run_id=config["configurable"].get(APP_RUN_ID_KEY), stage=stage_name)
        with verify_after_write.watching(
            config["configurable"].get(APP_RUN_ID_KEY), stage_name, check_after_a_write, **how_after_a_write,
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

        answered = update.pop("__fix_result__")
        fix_result = _rewritten_after_a_surrender(
            state, config, defect_index, stage_name, fix_model, answered, started, ctx=ctx)
        if fix_result is not answered:
            made_by = "rewrite"
    defect_fix_modes.end(config, stage_name)
    # A fix that stopped the product is handed back to its own model once before it is reverted (LF.1271).
    from app.graph import what_a_revert_broke

    repair = judged_fixes.ForwardRepair(
        str(repo), fix_base, defect,
        lambda asked, files: _repaired_forward(state, config, defect, fix_model, asked, files, ctx=ctx))
    broke = engineering.after_a_fix(
        state["repository"].root_path, fix_base, stage_name, defect.description,
        contested=_a_contested_test_past_repair(state, cycle),
        on_revert=lambda lost: (
            # What it broke and its change, kept for the next fixer of this defect (LF.1547), before it is reverted.
            what_a_revert_broke.record(repo, fix_base, defect, stage_name, lost, made_by),
            kept_fix_candidates.keep(
                repo, fix_base, defect, stage_name, lambda: _the_defect_s_tests_pass(repo, defect), lost))[-1],
        repair_forward=repair.attempt,
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

    if repair.tried:
        defect_ledger.note(
            judged_fixes.REPAIRED_FORWARD, stage_name, defect=defect, round_=state.get("test_round", 0),
            index=defect_index, sprint=state.get("current_sprint_index", 0), detail=repair.said(broke),
        )
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
        noted = _with_the_attempt(noted, defect_index, stage_name, fix_result,
                                  repair.outcome(f"reverted: it broke {'; '.join(broke[:3])}", broke),
                                  defect_budget.calls_in(config["configurable"].get(APP_RUN_ID_KEY), stage_name, started),
                                  root=state["repository"].root_path, sprint=state.get("current_sprint_index", 0))
        # A schema finding whose fix broke a test that passed is doubtful: set aside, not fixed again (LF.1547).
        noted = what_a_revert_broke.set_aside_if_doubtful(
            repo, noted, defect_index, broke, stage=stage_name, round_=state.get("test_round", 0),
            sprint=state.get("current_sprint_index", 0))
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
    from app import ci
    from app.graph.workflow import SETTLED_AS

    settled, blames = _settle_the_fix(
        state, cycle, defect_index, stage_name, fix_result, measured=f"after {stage_name}",
        # Whether any file of the product changed since the fix began, from the repository: not the fixer's own list.
        changed_nothing=ci.unchanged_since(state["repository"].root_path, fix_base),
    )
    settled_as = settled.pop(SETTLED_AS, "")
    if settled.get("remediation") is not None:
        after = settled["remediation"].defects[defect_index]
        settled["remediation"] = _with_the_attempt(
            settled["remediation"], defect_index, stage_name, fix_result,
            repair.outcome(settled_as or ("fixed" if str(getattr(after, "status", "")) == "fixed"
                                          else "left open: its tests still fail"), broke),
            defect_budget.calls_in(config["configurable"].get(APP_RUN_ID_KEY), stage_name, started),
            root=state["repository"].root_path, sprint=state.get("current_sprint_index", 0),
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
    handled one at a time, each fix stage recorded as worked this round
    (`fixes_tried`), so a pause for approval midway resumes on the same defect
    instead of restarting the whole round. In parallel mode defects whose files
    do not meet are fixed side by side, as work orders are built
    (`_the_next_fix_batch`).

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
    # While the product does not build or start, only that is fixed (deep review 1.5).
    from app.graph import start_first

    waiting = start_first.held_back(cycle.defects)

    # The latest test round's defects first, then those carried over (`order_of_fixes`).
    return _the_next_in_the_fix_order(state, config, ctx, cycle, waiting)


def _worked_this_round(state: Any, cycle: Any) -> set[str]:
    """The fix stages this round has worked: those recorded as tried, and those with an attempt recorded on a defect.

    The attempts are the cycle's own record, kept across a deploy: a round resumed from a state that has no record of
    what it tried does not work again a defect whose attempt this round is on it. A stage's name carries its round and
    its defect's index, so another round's attempts never match.
    """
    worked = {str(name) for name in state.get("fixes_tried") or []}
    for defect in cycle.defects:
        worked.update(str(attempt.get("stage") or "") for attempt in getattr(defect, "attempts", None) or []
                      if isinstance(attempt, dict))
    return worked


def _the_attempt_ends_past_its_budget(state: Any, cycle: Any) -> dict[str, Any] | None:
    """The end-of-attempt decision, in place of the next fixer, once the sprint has run far past its time budget.

    Measured on one run: the budget was read only when an attempt ended, and a sprint ran 891 active minutes against
    its 126 because its attempt kept sending fixers. See `sprint_time_budget.stops_the_fix_round`. None while the
    round may go on, or when the budget is off or not measured.
    """
    from app.graph import sprint_time_budget

    why = sprint_time_budget.stops_the_fix_round(state, stage=f"defect_fix_{state.get('test_round', 0)}")
    if not why:
        return None
    from app.graph.nodes.triage import _replan_or_escalate

    return _replan_or_escalate(state, {
        "remediation": cycle, "pending_approval": None, "pending_inner_thread_id": None, "pending_decision": None,
        "defect_cursor": 0, "fixes_tried": [], "fixes_one_at_a_time": [], "fix_batch": [], "fix_base_commit": "",
    }, cycle, why)


def _the_next_in_the_fix_order(
    state: Any, config: RunnableConfig, ctx: GraphContext, cycle: Any, waiting: set[int],
) -> dict[str, Any]:
    """One at a time: the first defect in the order `order_of_fixes.ordered` gives that is open, not waiting, and
    not yet worked in this round; a fix paused for approval resumes on its own defect.

    Measured on one run: the choice was a position - the defect after the last one worked - in an order read again at
    each visit. A deploy mid-round, or a defect raised again and regrouped, changed the order, and the defects it put
    ahead of that position were never sent: ten defects of a round, its root cause among them, skipped. What this round
    has worked is recorded by name instead (`fixes_tried`, as parallel mode records it), so whatever the order reads at
    a visit, each open defect is reached once a round.
    """
    from app.graph import order_of_fixes
    from app.graph.workflow import _the_stage_that_paused, _with_tried

    round_ = state.get("test_round", 0)

    def name(index: int) -> str:
        return f"defect_fix_{round_}_{index}"

    paused = _the_stage_that_paused(state)
    if paused and paused.startswith("defect_fix_"):
        # Answered after an approval pause: the paused fixer goes on, whatever the order reads now.
        return _with_tried(state, _fix_one(state, config, int(paused.rsplit("_", 1)[1]), ctx), paused)
    worked = _worked_this_round(state, cycle)
    order = order_of_fixes.ordered(cycle.defects, range(len(cycle.defects)))
    upcoming = [index for index in order
                if cycle.defects[index].status == "open" and index not in waiting and name(index) not in worked]
    if not upcoming:
        return {"stage": "test_and_triage", "defect_cursor": 0, "fixes_tried": []}
    # Far past the sprint's time budget, no further fixer is sent: the attempt ends (`sprint_time_budget`).
    stopped = _the_attempt_ends_past_its_budget(state, cycle)
    if stopped is not None:
        return stopped
    order_of_fixes.note_the_order(state, cycle, sorted(upcoming), upcoming, name(upcoming[0]))
    return _with_tried(state, _fix_one(state, config, upcoming[0], ctx), name(upcoming[0]))


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

    # While the product does not build or start, only that is fixed: one fixer with every reason it does not, not one
    # per criterion each failing the same way (deep review 1.5). The others wait for a product that starts.
    from app.graph import start_first

    waiting = start_first.held_back(cycle.defects)
    if waiting:
        logger.info("The product does not build or start: %d defect(s) wait for it to start", len(waiting))
    candidates = [
        index for index, defect in enumerate(cycle.defects)
        if defect.status == "open" and name(index) not in tried and index not in waiting
    ]
    # A defect that has spent its calls is not fixed again, side by side or
    # alone (plan AY step 4): the batch never asked, and sent it on.
    from app.graph import defect_budget

    for index in list(candidates):
        spent_out = defect_budget.spent_out(cycle, index, state["repository"].root_path)
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
    # A failing test no fix in this sprint can make pass goes to the QA lead before any fixer (FX.11, LF.1413); the
    # round comes back to its defect after the dispute.
    from app.graph import first_failure

    for index in candidates:
        held = first_failure.held_as_a_dispute(state, cycle, index)
        if held is not None:
            return held
    # Far past the sprint's time budget, no further fixer is sent: the attempt ends (`sprint_time_budget`).
    stopped = _the_attempt_ends_past_its_budget(state, cycle)
    if stopped is not None:
        return stopped
    # The latest test round's defects first, then those carried over; with `FIX_ORDER_CRITERIA_FIRST` on, failing
    # criteria and release findings first within each. None is left out.
    from app.graph import order_of_fixes

    raised = candidates
    candidates = order_of_fixes.ordered(cycle.defects, candidates)
    order_of_fixes.note_the_order(state, cycle, raised, candidates, f"defect_fix_{state.get('test_round', 0)}_batch")
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
    from app.graph import judged_fixes

    for index in chosen:
        # Where each defect's tests fail as its batch finds them (LF.1272).
        judged_fixes.remember_before(state["repository"].root_path, name(index), cycle.defects[index])
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
    from app.graph import web_tools_after_two_failed_fixes

    fix_model = ctx.the_build_model(
        state, stage_name, failed_fix_tries(cycle, index), reasons=True,
        after_a_revert=_a_revert_escalates_this_fix(cycle, index),
    )
    agent = create_specialist_agent(
        defect.owner, model=fix_model,
        checkpointer=ctx.checkpointer, repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories,
        web_tools_for_this_fix=web_tools_after_two_failed_fixes.tools_for(
            cycle, index, stage_name, root=state["repository"].root_path,
            resumed=bool((state.get("queued_decisions") or {}).get(stage_name))),
        fixing=True,
    )
    if not (state.get("queued_decisions") or {}).get(stage_name):
        _diagnosed_if_it_keeps_failing(state, defect, ctx)
    request, _ = _the_fix_request(state, config, cycle, index, model=fix_model,
                                  framing=_framing_of(agent))
    temp_state: Any = dict(state)
    # A worker may only answer its own approval gate: see `specialist_worker_node`.
    temp_state.update(_only_this_worker_s_pause(state, stage_name))
    # Each write followed by the defect's own tests, as when fixed alone (plan AY step 3).
    from app.graph import verify_after_write

    root = Path(state["repository"].root_path)
    from app.graph import batch_file_claims

    run_id = config["configurable"].get(APP_RUN_ID_KEY)
    from app.graph import first_failure

    with verify_after_write.watching(
        run_id, stage_name, lambda: _the_defect_s_tests_pass(root, defect),
        # Still failing, the write's reply says how, and what the server printed (FX.7).
        then=lambda: first_failure.after_a_write(root, defect),
    ), batch_file_claims.holding(run_id, stage_name):
        update = _run_gated_agent(
            temp_state, config, stage_name=stage_name, agent=agent, initial_request=request,
            output_key="__fix_result__", next_stage="defect_remediation",
        )
        if "__fix_result__" in update:
            # A fixer of a batch that changed nothing gets the rewrite a fixer alone gets, on the files no other fixer
            # of its batch holds; what it writes is this fixer's when the batch is measured (LF.1404).
            its_own = update["__fix_result__"]
            update["__fix_result__"] = _rewritten_after_a_surrender(
                state, config, index, stage_name, fix_model, its_own, str(state.get("fix_batch_started") or ""),
                ctx=ctx, beside=lambda path: batch_file_claims.held_by_another(run_id, stage_name, path),
            )
            if update["__fix_result__"] is not its_own:
                batch_file_claims.written_by_a_rewrite(
                    run_id, stage_name, list(getattr(update["__fix_result__"], "changed_files", None) or []))
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
    from app import ci
    from app.graph.workflow import SETTLED_AS

    # The repository tells only whether the batch as a whole changed anything; one fixer's writes are not told apart.
    batch_changed_nothing = ci.unchanged_since(state["repository"].root_path, str(state.get("fix_base_commit") or ""))
    for index, stage_name in zip(batch, names):
        if stage_name in put_back:
            continue
        result = outputs.get(stage_name)
        if result is None:
            continue
        settled, blames = _settle_the_fix(
            {**state, "specialist_outputs": {**outputs, **update.get("specialist_outputs", {})}},
            settled_cycle, index, stage_name, result, measured=f"after defect_fix_{round_}_batch",
            changed_nothing=True if batch_changed_nothing is True else None,
        )
        settled_as = settled.pop(SETTLED_AS, "")
        if settled.get("remediation") is not None:
            # Recorded as a fix alone records it, so the call cap and the next
            # fixer's earlier attempts see a batched attempt too.
            from app.graph import defect_budget

            after = settled["remediation"].defects[index]
            settled["remediation"] = _with_the_attempt(
                settled["remediation"], index, stage_name, result,
                settled_as or ("fixed" if str(getattr(after, "status", "")) == "fixed" else "left open: its tests still fail"),
                defect_budget.calls_in(config["configurable"].get(APP_RUN_ID_KEY), stage_name,
                                       str(state.get("fix_batch_started") or "")),
                root=state["repository"].root_path, sprint=state.get("current_sprint_index", 0),
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
