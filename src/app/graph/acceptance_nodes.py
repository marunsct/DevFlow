"""The stages between an approved architecture and the first sprint plan.

    scaffold -> acceptance_author -> acceptance_review -> [user review] -> scrum_master

or, for a product that may be planned as more than one sprint (LF.1266, `app.acceptance.by_sprint`):

    scaffold -> acceptance_author (numbers the criteria) -> scrum_master -> [plan gate] -> sprint_acceptance
    -> acceptance_author -> acceptance_review -> [user review] -> technical_lead, and `sprint_acceptance` again at
    each later sprint's start

and the parts of every later stage that read the acceptance suite. Kept out of
`workflow.py` so the definition of done has one home; the graph builder wraps
each function in a node with the run's models and checkpointer.

The order is how a software company starts a product: the project is set up so
its tests run, QA writes the tests that decide when it is done from the agreed
criteria, a QA lead reviews them, and only then is the work planned - against
criteria every sprint can be measured by.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.observability.degraded import degraded
from app.acceptance import requests as acceptance_requests
from app.acceptance import first_failing_step, start_output, suite
from app.acceptance.criteria import number
from app.graph import acceptance_batches, suite_by_file
from app.agents.shared_facts import with_the_facts
from app.stacks import compiler_errors, contract, pack_named
from app.graph.start_first import DEPENDENCIES_DO_NOT_INSTALL

logger = logging.getLogger(__name__)

#: How many times QA writes the suite before it is locked as it stands. Each
#: pass after the first is handed what the last review found.
MAX_ACCEPTANCE_ROUNDS = 3

#: A review finding that a test asserts too little to prove its criterion: a status alone, or a result never checked.
_TOO_WEAK = re.compile(
    r"\bonly (?:asserts?|checks?|verif(?:y|ies))\b|\b(?:does not|doesn't|never) (?:assert|check|verif(?:y|ies))\b"
    r"|\bwould pass even if\b"
    # A control the brief names, found only by something no person sees: the suite passes whatever the page calls it.
    # Measured on one run: it locked with both findings open and a hidden test finding the field by its label failed.
    r"|\bfinds a control by something no person sees\b|\bno test finds (?:any of them )?by that name\b",
    re.I,
)
#: Said with the findings sent back for strengthening: the rest of the suite is not rewritten.
STRENGTHEN_ONLY = (
    "Strengthen only the tests named below: keep each test and add the assertions it lacks - what the product "
    "returns and what it stores, not only the status - so it cannot pass on a product that gets this wrong. "
    "Change no other test."
)


#: Said with the tests sent back at the limit because no product could pass them.
REPAIR_ONLY = (
    "Repair only the tests named below, each only as far as its own code is wrong, so that it can pass once the "
    "product works. Change no other test and nothing any test checks."
)


#: Rounds past the review's limit a suite may take while each repair leaves fewer tests no product can pass (LR.27).
CANNOT_PASS_EXTRA_ROUNDS = 2


def cannot_pass_again(cannot: list[str], *, rounds: int, limit: int, last_sent: int | None) -> list[str]:
    """After the once-at-the-limit repair: send the tests no product can pass back again while repairs are working.

    Found in the launch review: after the one send-back the suite locked with such findings standing, and 76 of 190
    suites were later reopened for them at 20-30 minutes each, after a build and a test round. Before locking, a
    repair that left fewer of them goes back again, up to `CANNOT_PASS_EXTRA_ROUNDS` rounds past the limit; a repair
    that fixed none locks as before, with the findings recorded as open.
    """
    if not cannot or last_sent is None or rounds >= limit + CANNOT_PASS_EXTRA_ROUNDS or len(cannot) >= last_sent:
        return []
    return [REPAIR_ONLY, *cannot]


def cannot_pass_to_lock(cannot: list[str], *, rounds: int, limit: int, already_sent: bool = False) -> list[str]:
    """The harness's findings that a test can never pass, sent back once at the review's round limit; [] otherwise.

    A test no product can pass is a definition of done nobody meets: measured on one run, a suite locked at the limit
    with whole-page lookups of a per-record control and went back to its writers after a build and a test round.
    Once per suite, at the limit or past it: rounds that could not run take a suite beyond the limit, and an exact
    comparison never fired for it (see `too_weak_to_lock`).
    """
    return [REPAIR_ONLY, *cannot] if cannot and rounds >= limit and not already_sent else []


def too_weak_to_lock(findings: list[str], *, rounds: int, limit: int, already_sent: bool = False) -> list[str]:
    """The findings that a test is too weak, sent back once more at the review's round limit or after it; [] otherwise.

    Over 21 release-candidate runs 13 of 30 problems the suite locked with said a test only checked a status, and
    such a gap shipped a false acceptance. Once per suite: a suite whose rounds ran past the limit (five passes that
    could not run, on one run) reached the review beyond it, was never sent back, and locked with the gap open - a
    hidden test failed on it.
    """
    if rounds < limit or already_sent:
        return []
    return [finding for finding in findings if _TOO_WEAK.search(str(finding))]


#: Review point: the acceptance suite, before it is locked.
ACCEPTANCE_REVIEW = "acceptance_tests"


@dataclass
class Context:
    """The fields the stages here read from their context.

    The graph passes them `app.graph.context.GraphContext`, which has every one;
    this is the smaller shape a test builds by hand."""

    model: Any
    judgement_model: Any
    checkpointer: Any
    repo_root: str | None
    allow_subdirectories: bool = True



#: The defect raised when the product does not start for the suite. The unit tests
#: cannot answer for it - the suite starts the product on its own - so no probe of
#: them closes it.
THE_PRODUCT_DOES_NOT_START = "The product does not start for the acceptance suite, so no test can reach it."
#: The one defect for a service that died part-way through the suite (`suite.the_product_crashed_mid_suite`).
THE_PRODUCT_CRASHED = ("The product crashes while the acceptance suite runs: an unhandled error stops the service, and "
                       "every test after it finds nothing listening.")


def _the_install_that_failed(saved: dict[str, Any], state: Any) -> list[Any]:
    """A defect for the project's dependencies not installing, from the suite's last run; [] when they did.

    Measured on one gate run: a JavaScript package written into
    `requirements.txt` failed every install after it; nothing the manifest
    declared was installed, the product could not start, and no defect named
    the manifest - the note was logged and dropped.
    """
    from app.agents.specialists import ReportedDefect
    from app.analysis.manifests import MANIFEST_NAMES
    from app.stacks.contract import INSTALL_FAILED

    failed = [str(line) for line in saved.get("repairs") or [] if INSTALL_FAILED in str(line)]
    if not failed:
        return []
    root = Path(_root(state))
    try:
        from app.tools.repository import pinned_project_directory

        project = pinned_project_directory(root) or ""
    except Exception:  # noqa: BLE001
        project = ""
    base = root / project if project else root
    manifests = sorted(
        f"{project}/{path.name}" if project else path.name
        for path in (base.iterdir() if base.is_dir() else [])
        if path.is_file() and path.name in MANIFEST_NAMES
    )
    return [ReportedDefect(
        description=f"{DEPENDENCIES_DO_NOT_INSTALL}, so nothing its manifests declare is there: "
                    + failed[-1][:900],
        severity="blocking",
        reproduction_steps="Run the project's install command: it fails before the product can start.",
        expected_behavior="Every manifest lists only packages its own installer can find - each language's "
                          "packages in that language's manifest - and the install succeeds.",
        actual_behavior=failed[-1][:1500],
        affected_files=manifests,
        owner=_owner_for(state, failed[-1]),
        **_with_its_error_line(failed[-1], "other"),
    )]


def _the_build_that_fails(state: Any, reported: list[Any]) -> list[Any]:
    """A defect for the project's production build failing, with what the compiler said; [] when it builds. Never raises.

    As severe as a product that does not start: what would be shipped does not exist, whatever a suite running on a
    development server measured. `production_build` runs it only when the product changed.
    """
    from app.agents.specialists import ReportedDefect
    from app.stacks import production_build

    root = _root(state)
    said = production_build.failure(root)
    if not said or any(
        str(getattr(item, "description", "") or "").startswith(production_build.THE_PRODUCT_DOES_NOT_BUILD)
        for item in reported
    ):
        return []
    return [ReportedDefect(
        description=production_build.THE_PRODUCT_DOES_NOT_BUILD,
        severity="blocking",
        reproduction_steps=production_build.reproduce(root),
        expected_behavior="The production build finishes with no error, so that what it makes can be shipped.",
        actual_behavior=said,
        affected_files=production_build.files_named(root, said),
        owner=_owner_for(state, said),
        **_with_its_error_line(said, "compile_error"),
    )]


def _what_the_language_service_finds(state: Any) -> list[Any]:
    """The language service's certain findings in what this sprint changed, as the gate raises them; [] when none.

    Measured on one gate run: the product stopped on a name its module did not
    define, round after round; each round raised only "the suite fails ...",
    whose traceback names the importer, so every fix rewrote the importer.
    The gate had named the module, but it runs once per batch, not per round.
    """
    try:
        from app import ci
        from app.graph import engineering

        root = _root(state)
        accepted = ci.load(root, "accepted")
        since = (accepted.commit if accepted else "") or ci.first_commit(root)
        return [
            defect.model_copy(update={"source": "language service"})
            for defect in engineering.underlined_in_the_batch(state, root, since)
        ]
    except Exception as error:  # noqa: BLE001 - the round raises what it measured, as before
        degraded("check.language_service_at_round", error)
        return []

#: What opens the page snapshot in an acceptance defect's failure text
#: (`workflow._one_defect_per_root_error` reads it).
THE_PAGE_WHEN_IT_FAILED = "\nThe page when it failed:\n"

def _what_the_start_shows(root: str) -> str:
    """What the product printed and answered when started the way the suite starts it (`start_probe`); "" when off."""
    from app.acceptance.start_probe import what_the_start_shows

    return what_the_start_shows(root)


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
    from app.graph import runner_repair

    if runner_repair.pending(state):
        # The suite's runner crashed in the setup's own file: the setup stage repairs it (LF.1594).
        return runner_repair.repair(state, config, ctx)
    root = _root(state)
    pack = pack_named(state.get("stack_pack"))
    update: dict[str, Any] = {}
    already_done = bool((state.get("scaffold_result") or {}).get("ok"))
    seeded_project = None if already_done else _the_seeded_project_built_on_as_it_is(state, root)
    if seeded_project:
        # Not a pack around it either: a pack's kept files are put back over the
        # product's own, and its scaffold refuses a project with a manifest,
        # which stops the run as an unproven setup.
        update = {
            "stack_pack": None,
            "scaffold_result": {"ok": True, "pack": None, "project": seeded_project, "problem": ""},
        }
        _decide(
            state, update, point="scaffold", question="How is the project set up?",
            options=["built on as it is", "a new setup"], decision="built on as it is",
            rationale=f"`{seeded_project}/` holds the seeded product, with its code. The acceptance suite declares "
            "its own command, and no unit command is recorded for the unit gate.",
        )
        logger.info("%s/ holds the seeded product; it is built on as it is", seeded_project)
        return _handing_on(**update, stage="acceptance_author")
    if pack is not None and not already_done:
        from app.stacks.scaffold import scaffold as scaffold_pack
        from app.tools.repository import pin_the_directory_the_product_names, pinned_project_directory

        title = str(getattr(state.get("product_intake"), "product_name", "") or "").strip()
        project = pinned_project_directory(Path(root)) or pin_the_directory_the_product_names(root, title)
        if project:
            from app.stacks import stated_module

            brief = getattr(state.get("document"), "text", "") or ""
            package = stated_module(brief) if pack.language == "python" else None
            # The release line the brief asks for wins over the pack's own pin (LF.1311); a brief that asks for none
            # is scaffolded exactly as before.
            from app.stacks import stated_releases

            choice = stated_releases.choose(pack, brief, root)
            result = scaffold_pack(root, choice.pack, project, title or project, package=package)
            if not result.ok and choice.changed:
                # The setup on the asked line did not prove itself: set up on the pack's known-good pins, and say so.
                logger.warning("Scaffold %s on the brief's releases was not kept (%s); setting it up on the pack's "
                               "own pins", pack.name, result.problem)
                choice = stated_releases.fall_back(root, project, title or project, package, choice, result.problem)
                result = scaffold_pack(root, choice.pack, project, title or project, package=package)
            stated_releases.record(root, choice)
            if not result.ok:
                # One retry of the whole scaffold: the commands inside a single
                # attempt are each retried once already, so a second attempt
                # covers the state around them - a worker recreated mid-install,
                # a registry blip longer than one command's retry.
                logger.warning(
                    "Scaffold %s was not kept (%s); trying the whole scaffold once more",
                    pack.name, result.problem,
                )
                result = scaffold_pack(root, choice.pack, project, title or project, package=package)
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
                        "smoke tests." + (f" {choice.said}" if choice.said else "")
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


def _the_seeded_project_built_on_as_it_is(state: Any, root: str) -> str | None:
    """The pinned project, when it is a seeded product no setup has started on; None otherwise."""
    from app.acceptance.regression_contract import seeded
    from app.graph.workflow import _the_stage_that_paused
    from app.stacks import contract, custom_setup
    from app.tools.repository import pinned_project_directory

    project = pinned_project_directory(Path(root))
    if not project or not seeded(root) or state.get("scaffold_result") or contract.read(root) is not None:
        return None
    if str(_the_stage_that_paused(state) or "").startswith("stack_setup_"):
        return None
    return project if custom_setup.already_set_up(Path(root) / project) else None


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
        replayed = custom_setup.replay(project_root, stack, ctx.model)
        if replayed:
            proven = custom_setup.prove(root, project, stack, brief=brief, title=title or project)
            if proven.ok:
                custom_setup.noted(proven, replayed=True)
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
            set_aside = custom_setup.set_aside_what_did_not_prove(project_root)
            if set_aside:
                logger.warning("Set aside the proven setup %s: it did not prove, so it is not replayed again", set_aside)
            custom_setup.noted(proven, replayed=True, set_aside=set_aside)
            replay_failed: dict[str, Any] = {}
            _decide(
                state, replay_failed, point="scaffold", question="Does the setup proven in an earlier run hold here?",
                options=["replay it", "ask the setup stage"], decision="ask the setup stage",
                rationale=(f"The replayed setup{f' `{set_aside}`' if set_aside else ''} got as far as "
                           f"{proven.level or 'nothing'} and failed: {proven.problem}"
                           + (" It is set aside and not replayed again." if set_aside else "")),
            )
            if replay_failed.get("decisions"):
                state = {**state, "decisions": replay_failed["decisions"]}
            for relative in replayed:
                (project_root / relative).unlink(missing_ok=True)

    # On its language's runner layer when a pack of its kind and language has one (SF.2): the harness writes the
    # install, runners, reports, acceptance configuration and the declaration; the stage writes the framework's files.
    layer_files = custom_setup.layered_setup(
        project_root, stack, product_kind(stack, brief), project, title or project,
        write=attempt == 0 and not resuming,
    )
    custom_setup.record_the_setup_s_scope(Path(ctx.repo_root), project, layer_files)
    # With no layer, the stage starts from the harness's own draft of the declaration (PA.11).
    drafted = layer_files is None and custom_setup.write_draft_declaration(
        project_root, stack, product_kind(stack, brief), project)
    # What others found for the error the last setup failed on (plan WL.4 T2, behind `WEB_LOOKUP_WHEN_STUCK`).
    from app.graph import stuck_lookup

    problem = str(previous.get("problem") or "")
    problem += stuck_lookup.for_a_failed_setup(ctx.repo_root, problem, stack, f"stack_setup_{attempt}")
    agent = create_specialist_agent(
        "testing", model=ctx.model, checkpointer=ctx.checkpointer,
        repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories, setting_up_the_stack=True,
    )
    update = _run_gated_agent(
        state, config,
        stage_name=f"stack_setup_{attempt}",
        agent=agent,
        initial_request=custom_setup.build_setup_request(
            project, stack, product_kind(stack, brief), problem,
            specification=state.get("technical_specification"), layer_files=layer_files,
            drafted=drafted, repo_root=ctx.repo_root,
        ),
        output_key="__stack_setup__",
        next_stage="acceptance_author",
    )
    # A replay that failed is decided before the stage; its record goes with whatever the stage hands on.
    if state.get("decisions") and "decisions" not in update:
        update["decisions"] = list(state["decisions"])
    if "__stack_setup__" not in update:
        if update.get("stage") == "failed":
            return left_to_the_agents({}, str(update.get("error") or "the setup stage did not finish"))
        return update  # paused for approval, or retrying
    update.pop("__stack_setup__")
    update.pop("stage", None)
    result = custom_setup.prove(root, project, stack, brief=brief, title=title or project)
    custom_setup.noted(result)
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

def blockers_of_its_batch(blockers: list, group: list) -> list:
    """A batch writer's blockers about its own batch's criteria only; one naming none of them is kept as it is.

    Measured on one run: the first batch's writer listed "Part 2 and Part 3 will cover AC-7 ... AC-18" as a blocker,
    the harness read it as twelve criteria no test can check, and deferred them; the run built six of eighteen.
    """
    from app.acceptance.junit import tags_in

    own = {str(getattr(criterion, "id", "")) for criterion in group}
    kept: list = []
    for line in blockers:
        text = str(line)
        named = [tag for tag in tags_in(text) if tag.startswith("AC-")]
        if not named or acceptance_requests.the_harness_s_no_answer_line(text):
            kept.append(line)
            continue
        mine = [tag for tag in dict.fromkeys(named) if tag in own]
        if not mine:
            continue
        if len(mine) == len(set(named)):
            kept.append(line)
            continue
        reason = text.split(":", 1)[1].strip() if ":" in text else ""
        kept.append(f"{', '.join(mine)}: {reason}" if reason else ", ".join(mine))
    return kept


def _written_in_batches(state, config, agent, root, criteria, batches, round_, request_for, note_of=None):
    """The suite written a batch of criteria at a time; (the last update, every blocker), or (the pause, None).

    A batch is done when its criteria are covered, so a stage resumed after a pause or a deploy
    goes on at the first batch not done. Each batch has its own conversation. A criterion still
    without a test afterwards, and not set aside, is asked for once more, alone; what is still
    missing then is left to the review, as it is when the suite is written whole. `note_of(index, total, group,
    files)` says what each part is told (`acceptance_batches.note` when None).
    """
    from app.graph.workflow import _run_gated_agent

    note_of = note_of or acceptance_batches.note

    blockers: list = []
    update: dict = {}

    def write(name: str, group: list, note: str):
        nonlocal update
        done = _run_gated_agent(
            state, config, stage_name=f"acceptance_author_{round_}_{name}", agent=agent,
            initial_request=request_for(group, note), output_key="__acceptance_author__", next_stage="acceptance_review",
        )
        if "__acceptance_author__" not in done:
            return done
        blockers.extend(blockers_of_its_batch(getattr(done.pop("__acceptance_author__"), "blockers", None) or [], group))
        update = done
        return None

    for index, group in enumerate(batches):
        covered = suite.coverage(root)
        if all(criterion.id in covered for criterion in group):
            continue
        files = sorted({name for name, _ in suite.declared_tests(root)})
        paused = write(f"g{index}", group, note_of(index, len(batches), group, files))
        if paused is not None:
            return paused, None
    covered, set_aside = suite.coverage(root), set(suite.deferred(root)) | set(acceptance_requests.not_automatable(blockers))
    missing = [criterion for criterion in criteria if criterion.id not in covered and criterion.id not in set_aside]
    if missing:
        logger.info("Batched acceptance suite: %s still have no test; asked for once more", ", ".join(c.id for c in missing))
        files = sorted({name for name, _ in suite.declared_tests(root)})
        paused = write("fill", missing, note_of(len(batches), len(batches) + 1, missing, files))
        if paused is not None:
            return paused, None
    return update, blockers


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
        # The brief's requirement and constraint lines numbered as criteria, recorded once, when first numbered (PQ.1).
        from app.acceptance.brief_requirements import decision

        added = decision(brief, criteria)
        if added:
            from app.decisions import record_decision

            update = _writing_the_suite(state, config, ctx, root, criteria)
            record_decision(state, update, **added)
            return update
    return _writing_the_suite(state, config, ctx, root, criteria)


def _writing_the_suite(state: Any, config: RunnableConfig, ctx: Context, root: str, criteria: list) -> dict[str, Any]:
    """The rest of `acceptance_author`, once the criteria are numbered."""
    from app.agents.specialists import create_specialist_agent
    from app.graph.workflow import _handing_on, _run_gated_agent

    round_ = int(state.get("acceptance_round") or 0)
    feedback = [*(state.get("acceptance_feedback") or []), *(state.get("revision_comments") or [])]
    from app import delivery
    from app.acceptance import by_sprint

    # A product that may be planned as more than one sprint is planned first, and each sprint's tests are written at
    # its start (LF.1266): sprint 1's criteria are known when its tests are written.
    first_writing = round_ == 0 and not feedback and not state.get("acceptance_return_to")
    if (first_writing and not state.get("sprint_plan") and by_sprint.addition(root) is None
            and by_sprint.decide(root, fast=delivery.fast())):
        logger.info("The suite is written a sprint at a time: the sprints are planned before any test is written")
        return _handing_on(stage="scrum_master")
    suite.unlock(root)
    adding = by_sprint.addition(root)
    if adding is not None:
        wanted = set(adding.get("criteria") or [])
        criteria = [criterion for criterion in criteria if criterion.id in wanted] or criteria
    elif by_sprint.is_on(root):
        # Not an addition (a change request, a send-back at the acceptance gate): the criteria due now, never a later
        # sprint's, whose tests are written at its own start.
        later = by_sprint.criteria_not_yet_due(root)
        criteria = [criterion for criterion in criteria if criterion.id not in later] or criteria
    # Written by the build model in fast delivery, and reviewed by the
    # judgement model. See `app.delivery`.
    writer_model = ctx.model if delivery.fast() else ctx.judgement_model
    agent = create_specialist_agent(
        "testing", model=writer_model, checkpointer=ctx.checkpointer,
        repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories, writing_the_suite=True,
    )
    contract = getattr(state.get("technical_specification"), "interface_contract", None) or ()
    # PA.4: a suite written a file at a time gives each part only the contract lines its criteria use.
    by_file: list[bool] = [False]

    def request_for(group: list, note: str = "") -> dict:
        from app.agents.specification_rulings import with_the_rulings

        # The suite is written to the same answer the product is drafted to; the rest of the facts stay as they were here.
        return with_the_rulings(acceptance_requests.build_author_request(
            root, group, _stack(state), feedback=feedback, change_requests=suite.change_requests(root),
            brief=getattr(state.get("document"), "text", "") or "",
            testability=_the_testability_advice(state),
            interface_contract=suite_by_file.contract_for(group, contract) if by_file[0] else contract,
            specification=state.get("technical_specification"),
            batch_note=sprint_note + note,
            adding=bool(adding and adding.get("base")),
        ), root)

    # One sprint's part of a suite written a sprint at a time: its writers are told which part, and what is locked.
    sprint_note = (by_sprint.note(int(adding.get("sprint") or 1), int(adding.get("of") or 1), criteria,
                                  by_sprint.earlier_files(root))
                   if adding is not None else "")
    # Only a first writing, in the whole, is split: a repair is small and made against a built product.
    batches = acceptance_batches.plan(criteria) if round_ == 0 and not feedback else [criteria]
    note_of = None
    if len(batches) == 1 and round_ == 0 and not feedback and len(criteria) > 1:
        # PA.4: a suite whose one request would open past its author's room is written a file at a time.
        stage = f"acceptance_author_{round_}"
        share = suite_by_file.past_the_room(root, writer_model, request_for(criteria)["messages"][-1]["content"], stage,
                                            len(criteria))
        wanted = suite_by_file.parts(criteria, writer_model) if share is not None else [criteria]
        if len(wanted) > 1:
            batches, by_file[0] = wanted, True
            suite_by_file.record(stage, share, len(criteria), len(wanted))
            logger.info("The suite and its work fill %.2f of its author's room: %d criteria written in %d files", share,
                        len(criteria), len(wanted))

            def note_of(index, total, group, files):
                return suite_by_file.note(index, total, group, files, root)
    if len(batches) > 1:
        update, blockers = _written_in_batches(state, config, agent, root, criteria, batches, round_, request_for,
                                               note_of=note_of)
        if blockers is None:
            return update  # paused for approval, or retrying
    else:
        update = _run_gated_agent(
            state, config,
            stage_name=f"acceptance_author_{round_}",
            agent=agent,
            initial_request=request_for(criteria),
            output_key="__acceptance_author__",
            next_stage="acceptance_review",
        )
        if "__acceptance_author__" not in update:
            return update
        blockers = getattr(update.pop("__acceptance_author__"), "blockers", None) or []
    if adding is not None:
        # Only this sprint's criteria can be named as not automatable here: a later sprint's are written at its start.
        blockers = blockers_of_its_batch(blockers, criteria)
    from app.graph import product_at_fault

    blockers = product_at_fault.take_claims(root, blockers)
    reasons = acceptance_requests.not_automatable(blockers)
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
    from app.acceptance import sprint_scope

    later = set(sprint_scope.not_yet_due(root))
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
            lines.append("- (written when its sprint starts)" if criterion.id in later else "- (no test)")
        lines.append("")
    for change_id, text in suite.change_requests(root).items():
        lines.append(f"## {change_id}: {text}")
        lines.extend(f"- {name}" for name in covered.get(change_id, []))
        lines.append("")
    return "\n".join(lines)


def _the_specification_on_disk(root: str) -> str:
    """The recorded specification's text, or ""."""
    try:
        return (Path(root) / "docs" / "technical_specification.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _the_qa_lead_has_read_it(config: Any) -> bool:
    """Whether a QA lead's review of the suite has run in this run, from its transcript; True when unknown."""
    try:
        from app.observability.transcript import read_live
        from app.tracing import APP_RUN_ID_KEY

        run_id = ((config or {}).get("configurable") or {}).get(APP_RUN_ID_KEY)
        if not run_id:
            return True
        return any(str(r.get("stage") or "").startswith("acceptance_review_")
                   for r in read_live(run_id, {"model_request"}))
    except Exception:  # noqa: BLE001 - unknown is treated as read: the lock goes on as before
        return True


#: Said with a control disabled on load. Measured on one run: each fix that kept the control usable was reverted for
#: breaking the project's own unit tests, which asserted it was disabled, and the defect stayed open into a third
#: attempt - while a hidden test of the refusal clicks the control.
DISABLED_CONTROL_UNIT_TESTS = (
    " A unit test of the project's own that asserts the control is disabled holds the product to this fault: change "
    "it in the same fix, to check the refusal and its message instead."
)


#: The change that settles each accessibility rule without moving what the tests read. Measured on three runs: the
#: message shown when a list is empty was put inside the list as a plain element, breaking the `list` rule, and a fix
#: that turned it into a list item was reverted for breaking the tests that count the list's items.
ACCESSIBILITY_REMEDIES = {
    "list": ("A list holds only its items: put a message shown when it is empty, or any other element, beside the "
             "list - before or after it - never inside it, and leave the items themselves as they are."),
    "listitem": "A list item sits directly inside a list; an element marked as an item outside one is not an item.",
    # The same mistake under an explicit role: measured on one run, an empty-list message inside `<ul role="list">`
    # was reported as this rule, not `list`, got no remedy, and stayed open through three fix rounds.
    "aria-required-children": ("An element given a role that holds items (a list, a listbox, a menu, a table) holds "
                               "only those items: put a message shown when it is empty, or any other element, beside "
                               "it - before or after it - never inside it, and leave the items themselves as they are."),
    "color-contrast": ("Text needs a contrast of at least 4.5 to 1 with its background. Change the failing colour "
                       "where it is defined - in the page's own colour names (its design tokens) when it is one of "
                       "them - to the shade named below, rather than adding a new colour beside it."),
}

#: What axe-core says of one element whose text is too faint: its two colours and the ratio it wanted.
_A_CONTRAST_FAILURE = re.compile(
    r"foreground colou?r:\s*(#[0-9a-f]{6}|#[0-9a-f]{3})\b.*?background colou?r:\s*(#[0-9a-f]{6}|#[0-9a-f]{3})\b"
    r".*?expected contrast ratio of\s*([\d.]+)\s*:\s*1", re.I | re.S)


def _rgb(colour: str) -> tuple[int, int, int]:
    value = colour.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _luminance(rgb: tuple[int, int, int]) -> float:
    """WCAG relative luminance."""
    def channel(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(first: str, second: str) -> float:
    """The WCAG contrast ratio of two colours."""
    a, b = sorted((_luminance(_rgb(first)), _luminance(_rgb(second))), reverse=True)
    return (a + 0.05) / (b + 0.05)


def a_shade_that_reads(foreground: str, background: str, ratio: float) -> str:
    """The nearest shade of `background` - mixed toward black under light text, toward white under dark - that gives
    `foreground` at least `ratio`, or "" when none does.

    Measured on one run: white text on `#0d99ff` (2.99 to 1) stayed open through three fix rounds; each fix rewrote
    the stylesheet and kept the page's own colour name, which was the failing colour.
    """
    fg = _rgb(foreground)
    toward = (0, 0, 0) if _luminance(fg) > _luminance(_rgb(background)) else (255, 255, 255)
    bg = _rgb(background)
    for step in range(1, 101):
        mixed = tuple(round(c + (t - c) * step / 100) for c, t in zip(bg, toward))
        shade = "#" + "".join(f"{c:02x}" for c in mixed)
        if contrast(foreground, shade) >= ratio + 0.05:
            return shade
    return ""


def _the_shades_that_read(whys: list[str]) -> str:
    """For each faint pairing axe-core reported, the shade that reads, said once per pairing."""
    said: dict[tuple[str, str], str] = {}
    for why in whys:
        found = _A_CONTRAST_FAILURE.search(str(why or ""))
        if not found:
            continue
        foreground, background, ratio = found.group(1).lower(), found.group(2).lower(), float(found.group(3))
        if (foreground, background) in said:
            continue
        now = f"{foreground} on {background} reads at {contrast(foreground, background):.2f} to 1"
        shade = a_shade_that_reads(foreground, background, ratio)
        if shade:
            said[(foreground, background)] = (
                f"{now}; with the background at {shade} it reads at {contrast(foreground, shade):.2f} to 1")
            continue
        # A background already at black or white cannot move further: the text's colour moves instead.
        text = a_shade_that_reads(background, foreground, ratio)
        if text:
            said[(foreground, background)] = f"{now}; with the text at {text} it reads at {contrast(text, background):.2f} to 1"
    return (" The shades that read: " + "; ".join(said.values()) + ".") if said else ""


def what_the_lock_ran(result: Any, criteria: int) -> str:
    """The lock's count of tests, or why none ran: a product drafted but not starting yet answers no test at all.

    Measured on one run: a suite locked again after drafting read "0 test(s) over 18 criteria; every criterion is
    covered", which reads as a suite holding no tests; its eleven tests had found no product to reach.
    """
    tests = len(getattr(getattr(result, "report", None), "tests", None) or [])
    if not tests and str(getattr(result, "problem", "") or "").startswith(suite.PRODUCT_DID_NOT_START):
        return (f"no test ran against the product at this lock: it does not start yet, and the first test round "
                f"runs the suite against it; {criteria} criteria")
    return f"{tests} test(s) over {criteria} criteria"


def a_repair_left_the_sprint_green(root: str | Path, result: Any) -> bool:
    """Whether the repaired suite passes in full and the unit tests last passed on this same product. Never raises."""
    try:
        import json

        from app import ci
        from app.acceptance.unstable import fingerprint

        tests = list(getattr(getattr(result, "report", None), "tests", None) or [])
        if not getattr(result, "ran", False) or not tests or any(t.outcome != "passed" for t in tests):
            return False
        unit = json.loads((Path(root) / ci.UNIT_RUN_FILE).read_text(encoding="utf-8"))
        return bool(unit.get("passed")) and unit.get("fingerprint") == fingerprint(root)
    except Exception:  # noqa: BLE001 - planned again, as before
        return False


#: Why a suite repaired at a re-plan's entry goes back to the test round instead of the lead; "" when it does not.
GREEN, NEAR_GREEN = "green", "near green"


def why_measured_again(root: str | Path, result: Any) -> str:
    """GREEN for a full pass beside passing unit tests, NEAR_GREEN for a near-green run (`NEAR_GREEN_REPAIR_TO_ROUND`),
    "" to plan the sprint again. Never raises."""
    if a_repair_left_the_sprint_green(root, result):
        return GREEN
    from app.graph import near_green_repair

    return NEAR_GREEN if near_green_repair.applies(result) else ""


#: What a test round measures against when it follows a re-plan's entry: the plan was cleared for the lead's re-plan.
NO_NEW_PLAN = ("No new plan: the suite was repaired at the end of the last attempt, and the product is measured again "
               "as it stands.")


def the_plan_a_round_measures(state: Any) -> Any:
    """The sprint's plan, or one of no work orders naming the sprint's goal when the re-plan's entry cleared it.

    The round reads the plan, and finding none it sends the run back to the lead: measured in a review, a suite
    repaired green at a re-plan's entry went to the round with no plan and from there to the lead's re-plan anyway.
    """
    plan = state.get("milestone_plan")
    if plan is not None:
        return plan
    from app.agents.technical_lead import MilestonePlanOutput

    sprints = list(getattr(state.get("sprint_plan"), "sprints", None) or [])
    index = int(state.get("current_sprint_index") or 0)
    goal = str(getattr(sprints[index], "goal", "") or "") if index < len(sprints) else ""
    return MilestonePlanOutput(selected_sprint_goal=goal, integration_notes=[NO_NEW_PLAN])


def _the_suite_s_files(root: str | Path) -> dict[Path, str]:
    """Each file of the suite with its text now; {} when it cannot be read."""
    try:
        return {path: path.read_text(encoding="utf-8") for path in suite.suite_files(root)}
    except Exception:  # noqa: BLE001 - nothing to put back to
        return {}


def _write_the_suite_s_files(files: dict[Path, str]) -> None:
    for path, text in files.items():
        try:
            path.write_text(text, encoding="utf-8")
        except OSError:
            logger.debug("Could not write %s back", path, exc_info=True)


#: The suite as it ran before an at-the-limit send-back, and the once-per-lock send-backs: both cleared by every lock.
#: Before the advice the harness read in the suite's code, as the QA lead reads it.
ADVICE_HEADING = (
    "--- Review points the harness read in the tests' code (advice: a product may still pass them; send a test back "
    "for one only when you judge it right) ---"
)
BEFORE_THE_SEND_BACK = suite.BEFORE_THE_SEND_BACK
ONCE_AT_THE_LIMIT = suite.ONCE_AT_THE_LIMIT


def _keep_before_the_send_back(root: str | Path) -> None:
    """Keep the suite's files as they ran, before a send-back at the review's limit."""
    files = _the_suite_s_files(root)
    if not files:
        return
    try:
        target = Path(root) / BEFORE_THE_SEND_BACK
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({str(path): text for path, text in files.items()}), encoding="utf-8")
    except (OSError, TypeError):
        logger.debug("Could not keep the suite before its send-back", exc_info=True)


def _put_back_before_the_send_back(root: str | Path) -> bool:
    """Put back the suite as it ran before an at-the-limit send-back; whether there was one to put back.

    Found in a code review: a send-back at the limit (held only in part, no product could pass, too weak) returned a
    suite that might not run or might prove nothing, and with no rounds left the run failed, although the suite that
    ran before the send-back was lockable. Its files are put back (files the send-back added are removed) and it is
    reviewed again, when the once-per-lock send-backs are spent and it locks with what is open recorded.
    """
    target = Path(root) / BEFORE_THE_SEND_BACK
    try:
        kept = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(kept, dict) or not kept:
        return False
    for path in _the_suite_s_files(root):
        if str(path) not in kept:
            try:
                path.unlink()
            except OSError:
                logger.debug("Could not remove %s", path, exc_info=True)
    _write_the_suite_s_files({Path(path): text for path, text in kept.items()})
    target.unlink(missing_ok=True)
    logger.warning("The suite returned from a send-back at the limit could not be locked; the suite before it is back")
    return True


def _the_repair_measured(root: str | Path) -> tuple[list[str], Any, str]:
    """(the suite's gaps, its measurement, what a repair lost) after the tests a repair was not sent for are put back.

    The put-back may be what broke it: a test put back into a file the repair reshaped. Measured on one run, the suite
    then ran no test at all, and the whole repair of six tests was thrown away for the one put back - so a put-back
    that leaves the suite worse is undone first, and the repair is judged as it was written.
    """
    as_repaired = _the_suite_s_files(root)
    untouched = suite.put_back_tests_the_repair_was_not_sent_for(root)
    if untouched:
        logger.warning("Put back %d test(s) the repair was not sent for: %s", len(untouched), ", ".join(untouched[:8]))
    problems = suite.gaps(root)
    result = suite.run(root)
    worse = suite.a_repair_that_made_it_worse(root, result)
    if worse and untouched and as_repaired:
        _write_the_suite_s_files(as_repaired)
        kept = suite.run(root)
        if not suite.a_repair_that_made_it_worse(root, kept):
            logger.warning("Putting back %s broke the suite; the repair's version is kept", ", ".join(untouched[:4]))
            return suite.gaps(root), kept, ""
    return problems, result, worse


def acceptance_review(state: Any, config: RunnableConfig, ctx: Context) -> dict[str, Any]:
    """Check the suite mechanically, have a QA lead judge it, then lock it.

    First, before the suite is measured, a limit the specification sets on how often one client may call is reconciled
    with how often the suite calls (LF.1269, `app.acceptance.client_limits`): when the suite calls past it, the one
    finding is the specification's - ruled on and recorded as a decision, never sent to the suite's writers - and the
    measurement below already runs with the environment the ruling names. The lock never comes before it.
    """
    from app.acceptance import client_limits

    reconciled: dict[str, Any] = {}
    client_limits.reconcile_before_the_lock(state, reconciled)
    if not reconciled.get("decisions"):
        return _reviewed_and_locked(state, config, ctx)
    update = _reviewed_and_locked({**state, "decisions": reconciled["decisions"]}, config, ctx)
    if isinstance(update, dict) and not update.get("decisions"):
        update["decisions"] = reconciled["decisions"]
    return update


def _reviewed_and_locked(state: Any, config: RunnableConfig, ctx: Context) -> dict[str, Any]:
    from app.agents.acceptance_reviewer import (
        build_acceptance_review_request,
        create_acceptance_reviewer_agent,
    )
    from app.graph.workflow import _handing_on, _record_document, _review_enabled, _run_gated_agent

    root = _root(state)
    rounds = int(state.get("acceptance_round") or 1)
    from app.acceptance import by_sprint

    # A sprint's addition only adds (LF.1266): an earlier sprint's locked file it changed goes back as locked first.
    adding = by_sprint.addition(root)
    put_back_earlier = by_sprint.put_back_what_the_addition_changed(root)
    # Each test's code as the writers left it, before the harness renames, corrects or puts anything back: a test the
    # harness puts back is never one the writers "have not changed".
    written = suite.test_bodies(root)
    # A file the runner skips only for its name's separator is renamed, not sent back (five rounds once ran out on it).
    suite.rename_files_the_runner_skips(root)
    # So is a read of `request.baseURL`, left through three rounds although each named the corrected line.
    suite.correct_reads_of_the_fixture_s_baseurl(root)
    # A repair changes only the tests it was sent for: any other it rewrote goes back as the review approved it.
    problems, result, worse = _the_repair_measured(root)
    problems = [*put_back_earlier, *problems]
    if worse:
        # The repair's best measured version comes back - or, without one, the suite as it was locked - before anything
        # else reads this one; the writers are told what the repair lost and which version came back, so a worse suite
        # is never locked in place of the better one. The writers' version is recorded as measured first.
        suite.keep_the_best_of_the_repair(root, result)
        best = suite.the_best_of_the_repair(root)
        put_back = suite.put_back_the_best_of_the_repair(root)
        logger.warning("A repair left the suite worse; put back %d file(s) %s", len(put_back),
                       f"as the repair's best measured version ({best.get('passed')} of {best.get('tests')} passing)"
                       if best else "as locked")
        result = suite.run(root)
        # The gaps of the version now in place, not of the worse one taken out (design review: a gap that version made
        # by dropping a test's criterion tag was still sent after the put-back restored the tag).
        problems = [worse, *filter(None, [suite.what_a_put_back_undid(root, written)]), *suite.gaps(root)]
    # The suite as measured here, when no worse than before the repair and than its best so far, is the version a
    # later change that leaves it worse puts back (measured on one run: the harness's own rewrite of six tests was
    # lost to the lock that way, and the six went back for repair again).
    suite.keep_the_best_of_the_repair(root, result, put_back=bool(worse))
    if not result.ran:
        problems.append(
            f"The suite does not run: {result.problem}.\n{result.output[-1500:]}".strip()
        )
        if result.exit_code == 124 or "timed out" in f"{result.problem} {result.output}".lower():
            stuck = suite.the_test_that_did_not_finish(root, result.output)
            problems.append(
                "The suite never finished" + (f": it stopped at {stuck}, which never returned" if stuck else "")
                + ". A test that never finishes is one that waits for something that never ends - most "
                "often a product that keeps running, started by the test itself (a service, its server, "
                "its start script), which the suite's own setup already starts. Make that test check the "
                "running product instead. This is about the tests, not the product: nothing of the "
                "product is missing for this reason."
            )
    # A suite under repair has been locked before: the same rule as at a round, or a false finding found here locks it
    # with a problem "still open", which is a release gap.
    from app.acceptance import check_findings

    # Each mechanical finding with the check that raised it, to hold back one that came back unchanged after a repair.
    raised: list[tuple[str, str]] = []

    def _noted(check: str, found: Any) -> list[Any]:
        found = check_findings.noted(root, rounds, check, found)
        raised.extend((check, str(item)) for item in found)
        return found

    cannot_pass = suite.tests_that_cannot_pass(root, result)
    cannot = suite.findings_that_reopen(root, result, cannot_pass)
    # Each of the checks inside `tests_that_cannot_pass` recorded under its own name (HR2.Q.1).
    named = getattr(cannot_pass, "checks", {}) or {}
    for check in dict.fromkeys(named.get(str(f), "tests_that_cannot_pass") for f in cannot):
        _noted(check, [f for f in cannot if named.get(str(f), "tests_that_cannot_pass") == check])
    # A repair that left a test it was sent for exactly as it was goes back with the cannot-pass findings (and once
    # at the review's limit, `cannot_pass_to_lock`), recorded under the bucket's name. It says what the writers did,
    # not what a check suspects, so it is never held back as a repeat.
    # A test sent on a check's finding that no check that can reopen a suite raises now - corrected since, or its
    # fault gone with a shared helper - needed no change: it is settled, not sent back (measured on one run: four
    # rounds, 45 minutes, spent on a right test a corrected check no longer named). The repair it opened stays charged
    # (`suite_repairs`): it was opened on a finding that held then, and the charge is what stops a check that comes and
    # goes from reopening the suite without end (`may_repair` reopens only for a test never sent once it is spent).
    vacuous = suite.vacuous_green(root, result)
    still_found: list[str] | None = None
    if result.ran:
        try:
            still_found = [
                *cannot, *vacuous,
                *suite.tests_left_behind_by_their_own_change(root, result),
                *suite.tests_finding_a_per_record_control_on_the_whole_page(
                    root, result, getattr(state.get("document"), "text", "") or ""),
            ]
        except Exception as error:  # noqa: BLE001 - every test left as it was is sent back, as before
            degraded("repair.findings_that_still_hold", error)
            still_found = None
    settled = suite.tests_whose_finding_no_longer_holds(root, result, written, still_found)
    if settled:
        logger.warning("The finding %d test(s) were sent for repair on no longer holds; they stay as locked: %s",
                       len(settled), "; ".join(name[:80] for name in settled))
    unrepaired = suite.tests_left_unrepaired(root, result, written, still_found)
    check_findings.noted(root, rounds, "tests_that_cannot_pass", unrepaired)
    cannot = [*cannot, *unrepaired]
    problems.extend(cannot)
    # Against the specification's contract, before it is recorded at the lock (the rounds read the locked one).
    problems.extend(_noted("tests_that_want_json_from_a_204", suite.tests_that_want_json_from_a_204(
        root, getattr(state.get("technical_specification"), "interface_contract", None) or ())))
    problems.extend(_noted("tests_whose_success_status_the_contract_does_not_give",
                                         suite.tests_whose_success_status_the_contract_does_not_give(
        root, getattr(state.get("technical_specification"), "interface_contract", None) or ())))
    # A suite that proved nothing is evidence, not a check's suspicion: it is never held back as a repeat.
    problems.extend(check_findings.noted(root, rounds, "vacuous_green", vacuous))
    # Tests that pass a product that is not there (LR.23): assertions made only when the answer was good, and, at the
    # first writing before anything is built, tests that already pass.
    problems.extend(_noted("tests_guarded_by_the_answer", suite.tests_guarded_by_the_answer(root)))
    nothing_built = (not state.get("acceptance_return_to") and not int(state.get("current_sprint_index") or 0)
                     and not any(str(key).startswith("specialist_") for key in (state.get("specialist_outputs") or {})))
    problems.extend(_noted("tests_that_pass_before_the_product",
                                         suite.tests_that_pass_before_the_product(result, nothing_built)))
    # Kept by name, so no later status line reads a criterion as met on them alone (LF.1446).
    from app.acceptance import passed_unbuilt

    passed_unbuilt.record(root, result, nothing_built)
    # Too lenient rather than impossible: a suite that passes a product it
    # should fail. The review sends these back; a test round has nothing to
    # charge for them.
    problems.extend(_noted("locators_nobody_sees", suite.locators_nobody_sees(root)))
    problems.extend(_noted("locators_that_pick_one", suite.locators_that_pick_one(root)))
    # Read against the whole brief only once every criterion is due: while a later sprint's criteria are not, what the
    # brief names for them is written at that sprint's start (LF.1266).
    whole_brief = ("" if by_sprint.is_on(root) and by_sprint.criteria_not_yet_due(root)
                   else getattr(state.get("document"), "text", "") or "")
    problems.extend(_noted("controls_never_found_by_name",
        suite.controls_never_found_by_name(root, whole_brief)
    ))
    problems.extend(_noted("records_never_found_as_the_brief_shows_them",
        suite.records_never_found_as_the_brief_shows_them(root, whole_brief)
    ))
    partial = _noted("outputs_held_only_in_part",
                                   suite.outputs_held_only_in_part(root, whole_brief))
    partial = [*partial, *_noted("whitespace_tested_with_spaces_only",
                                                suite.whitespace_tested_with_spaces_only(root))]
    partial = [*partial, *_noted("words_broken_only_at_spaces",
                                                suite.words_broken_only_at_spaces(root))]
    problems.extend(partial)
    problems.extend(_noted("views_never_acted_within",
                                         suite.views_never_acted_within(root, whole_brief)))
    # Plan item 16: at a first writing only; a repair is told to change nothing but the tests it was sent for.
    from app.acceptance import contract_coverage

    # A line a later sprint's criteria reach has its test written at that sprint's start (LF.1266).
    if contract_coverage.enabled() and not state.get("acceptance_return_to") and not by_sprint.criteria_not_yet_due(root):
        missing_lines = contract_coverage.lines_with_no_test(
            root, getattr(state.get("technical_specification"), "interface_contract", None) or ())
        if missing_lines:
            problems.extend(_noted("contract_lines_with_no_test", [contract_coverage.finding(missing_lines)]))
    # A finding the review before raised the same, with a repair between, is not sent back to the writers again: it
    # goes to the QA lead as a suspected false positive (per-role audit 2026-11-20: one came back seven rounds).
    suspected = check_findings.withheld(root, rounds, raised) if result.ran and not vacuous else []
    if suspected:
        logger.warning("%d harness finding(s) came back unchanged after a repair: given to the QA lead, not the writers",
                       len(suspected))
        held = set(suspected)
        problems = [p for p in problems if str(p) not in held]
        cannot = [f for f in cannot if str(f) not in held]
        partial = [f for f in partial if str(f) not in held]
    if adding is not None:
        # The earlier sprints' tests are locked and put back as locked: what is found in them alone is for the paths
        # that reopen a locked suite, not for this sprint's writers.
        problems = [*put_back_earlier, *by_sprint.about_the_addition(
            root, [p for p in problems if p not in put_back_earlier])]
        cannot = by_sprint.about_the_addition(root, cannot)
        partial = by_sprint.about_the_addition(root, partial)
    if not result.ran:
        # A runner that crashed in the setup's own file is the setup's to repair, not the writers' (LF.1594).
        from app.graph import runner_repair

        if (to_the_setup := runner_repair.send_for_repair(state, root, result)) is not None:
            return _handing_on(**to_the_setup)
        if rounds < MAX_ACCEPTANCE_ROUNDS + 2:
            logger.warning("Acceptance suite could not run (exit %s); sent back to QA", result.exit_code)
            return _handing_on(stage="acceptance_author", acceptance_feedback=problems)
        if (kept := _kept_as_locked_before(state, root, f"the repaired suite cannot run: {result.problem}")) is not None:
            return kept
        if (left := _an_addition_left_out(state, root, f"its tests cannot run: {result.problem}")) is not None:
            return left
        if _put_back_before_the_send_back(root):
            return _handing_on(stage="acceptance_review", acceptance_feedback=[])
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
        if (kept := _kept_as_locked_before(state, root, "the repaired suite proves nothing: " + "; ".join(vacuous)[:1200])) is not None:
            return kept
        if (left := _an_addition_left_out(state, root, "its tests prove nothing: " + "; ".join(vacuous)[:1200])) is not None:
            return left
        if _put_back_before_the_send_back(root):
            return _handing_on(stage="acceptance_review", acceptance_feedback=[])
        logger.error("Acceptance suite still proves nothing after %d rounds", rounds)
        return _handing_on(
            stage="failed",
            error=f"The acceptance suite proves nothing after {rounds} rounds: " + "; ".join(vacuous)[:1500],
        )
    if problems and rounds < MAX_ACCEPTANCE_ROUNDS:
        logger.info("Acceptance suite sent back to QA: %d problem(s)", len(problems))
        return _handing_on(stage="acceptance_author", acceptance_feedback=problems)
    sent_back = suite._state(root)
    if partial and rounds >= MAX_ACCEPTANCE_ROUNDS and not sent_back.get("partial_strengthened_once"):
        logger.info("At the review's limit, %d output(s) held only in part go back once to be strengthened", len(partial))
        _keep_before_the_send_back(root)
        suite._save_state(root, {**sent_back, "partial_strengthened_once": True})
        return _handing_on(stage="acceptance_author", acceptance_feedback=[STRENGTHEN_ONLY, *partial])
    if repair := cannot_pass_to_lock(cannot, rounds=rounds, limit=MAX_ACCEPTANCE_ROUNDS,
                                     already_sent=bool(sent_back.get("cannot_pass_repaired_once"))):
        logger.info("At the review's limit, %d test(s) no product could pass go back once to be repaired", len(cannot))
        _keep_before_the_send_back(root)
        suite._save_state(root, {**suite._state(root), "cannot_pass_repaired_once": True, "cannot_pass_sent": len(cannot)})
        return _handing_on(stage="acceptance_author", acceptance_feedback=repair)
    if again := cannot_pass_again(cannot, rounds=rounds, limit=MAX_ACCEPTANCE_ROUNDS,
                                  last_sent=suite._state(root).get("cannot_pass_sent")):
        logger.info("The repair left %d test(s) no product could pass, fewer than before: sent back again", len(cannot))
        suite._save_state(root, {**suite._state(root), "cannot_pass_sent": len(cannot)})
        return _handing_on(stage="acceptance_author", acceptance_feedback=again)

    findings: list[str] = []
    # The QA lead's severity of each of its findings, when it read the suite this time (TG.2).
    graded: dict[str, str] | None = None
    update: dict[str, Any] = {}
    # Plan item 10: a repair that changed only the tests sent for it is judged by the checks above, not reviewed again.
    targeted = not problems and suite.targeted_repair_switch.enabled() and suite.only_the_repaired_tests_changed(root)
    if targeted:
        logger.info("The reopened suite changed only the tests sent for repair; locked again on the harness's checks")
    # A repair whose findings all stopped holding, with nothing changed, is the suite the QA lead approved at its lock.
    if settled and not problems and suite.is_as_last_locked(root):
        logger.info("The reopened suite is as it was locked and its findings no longer hold; locked again unread")
        targeted = True
    from app.acceptance.api_reference import api_reference
    from app.graph import product_at_fault

    specification = state.get("technical_specification")
    no_fault_found = product_at_fault.evidence(root, result, problems, [
        getattr(state.get("document"), "text", "") or "",
        *(getattr(specification, "interface_contract", None) or ()),
        *(criterion.text for criterion in suite.criteria(root)),
        api_reference(specification),
        _the_specification_on_disk(root),
    ]) if product_at_fault.enabled() else []
    targeted = targeted or bool(no_fault_found)
    # Findings held back from the writers are the QA lead's to judge: a suite with any is read, not locked unread.
    targeted = targeted and not suspected
    from app.graph import suite_gate

    # A person approved locking it as it stands, with the gating findings in front of them: locked, not read again (TG.2).
    approved_by_a_person = suite_gate.approved_as_it_stands(state)
    targeted = targeted or approved_by_a_person
    # At the limit with the harness's own problems still open, a suite the QA lead never read would be locked unread
    # (per-role audit: 3 of 30 runs, one a false acceptance): it is read once, and what it finds is handled as below.
    unread_at_the_limit = bool(problems) and rounds >= MAX_ACCEPTANCE_ROUNDS and not _the_qa_lead_has_read_it(config)
    # A gating finding of the QA lead's still open is settled only by its own reading of the suite (TG.2).
    unread_at_the_limit = unread_at_the_limit or (bool(problems) and suite_gate.the_qa_lead_reads_again(state))
    if unread_at_the_limit:
        logger.info("At the limit with %d problem(s) open and no review yet: the QA lead reads the suite once", len(problems))
    if (not problems or unread_at_the_limit) and not targeted:
        already_passing =[test.name for test in result.report.tests if test.outcome == "passed"]
        deferred = suite.deferred(root)
        deferred_text = (
            "--- Criteria QA says no automated test can check ---\n"
            + "\n".join(f"- {cid}: {why}" for cid, why in deferred.items())
            + "\nJudge whether each reason holds; a criterion that can be tested must be.\n\n"
            if deferred else ""
        )
        from app.agents.reviews_without_reasoning import the_review_model

        agent = create_acceptance_reviewer_agent(
            model=the_review_model(ctx.judgement_model), checkpointer=ctx.checkpointer,
            repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories,
        )
        later = by_sprint.criteria_not_yet_due(root) if by_sprint.is_on(root) else set()
        earlier = by_sprint.earlier_files(root)

        def built(held: list[str]) -> dict[str, Any]:
            request = build_acceptance_review_request(
                acceptance_requests.criteria_text([c for c in suite.criteria(root) if c.id not in later], deferred),
                acceptance_requests.suite_text(root, earlier=earlier, held=held),
                # A failure of a criterion this sprint builds once its tests are locked is named as expected (LF.1532).
                by_sprint.what_running_it_showed(root, result),
                already_passing,
                deferred_text,
                brief=getattr(state.get("document"), "text", "") or "",
                testability=_the_testability_advice(state),
            )
            # The facts the work is built and judged under (plan CM.1).
            request = with_the_facts(request, state["repository"].root_path)
            # What the tests are judged against, whole (see `app.acceptance.api_reference`).
            request["messages"][-1]["content"] += "\n" + api_reference(
                state.get("technical_specification"), getattr(state.get("document"), "text", "") or "")
            if adding is not None and earlier:
                request["messages"][-1]["content"] += "\n" + by_sprint.review_note(
                    list(adding.get("criteria") or []), by_sprint.new_files(root), earlier)
            if suspected:
                request["messages"][-1]["content"] += "\n" + check_findings.for_the_qa_lead(suspected)
            # What the harness read in the tests' code that a product may still pass: the QA lead's to weigh, never a
            # send-back by itself.
            if advice := suite.advice_about_the_suite(root):
                request["messages"][-1]["content"] += ("\n" + ADVICE_HEADING + "\n"
                                                       + "\n".join(f"- {item}" for item in advice) + "\n")
            return review_files.with_the_files_held(request, held, stage)

        from app.agents import review_files

        stage = f"acceptance_review_{rounds}"
        request = built([])
        # The suite's files held in its memory, numbered, when today's request and memory do not show them all
        # (LF.1286): measured on one medium run, each review of a 15-file suite read its files about four times each.
        held = review_files.held_for_review(
            review_files.under_review(root, [p.relative_to(Path(root)).as_posix() for p in suite.suite_files(root)
                                             if p.relative_to(Path(root)).as_posix() not in set(earlier)]),
            root, the_review_model(ctx.judgement_model), stage, review_files.opening_of(request))
        if held:
            request = built(held)
        update = _run_gated_agent(
            state, config,
            stage_name=stage,
            agent=agent,
            initial_request=request,
            output_key="__acceptance_review__",
            next_stage="acceptance_review",
        )
        if "__acceptance_review__" not in update:
            return update
        review = update.pop("__acceptance_review__")
        update.pop("stage", None)
        graded = {str(item): str(getattr(item, "severity", "") or "minor") for item in review.findings or []}
        if not review.approved and review.findings:
            findings = suite.findings_about_the_suite([str(item) for item in review.findings])
            findings = by_sprint.about_the_addition(root, findings)
            # The QA lead is the largest sender of send-backs (240 of 295 items left open at the lock): recorded
            # beside the harness's own checks so its settle rate is measured too (HR2.Q.1).
            check_findings.noted(root, rounds, "qa_lead", findings)
            if len(findings) < len(review.findings):
                logger.info(
                    "QA lead's review: %d of %d finding(s) were about the product, not the tests; not sent back",
                    len(review.findings) - len(findings), len(review.findings),
                )
        if not review.approved and findings:
            from app import delivery

            # Fast delivery sends a suite back once; what is still open after
            # that is locked in as an open problem, as after the full count.
            limit = 2 if delivery.fast() else MAX_ACCEPTANCE_ROUNDS
            if rounds < limit:
                logger.info("QA lead sent the acceptance suite back: %d finding(s)", len(findings))
                return _handing_on(**update, stage="acceptance_author", acceptance_feedback=findings)
            sent = bool(suite._state(root).get("strengthened_once"))
            if weak := too_weak_to_lock(findings, rounds=rounds, limit=limit, already_sent=sent):
                logger.info("At the review's limit, %d test(s) too weak to lock go back once to be strengthened", len(weak))
                _keep_before_the_send_back(root)
                suite._save_state(root, {**suite._state(root), "strengthened_once": True})
                return _handing_on(**update, stage="acceptance_author", acceptance_feedback=[STRENGTHEN_ONLY, *weak])
            # A test the QA lead says fails on a correct product is repaired once before the lock, in either delivery
            # mode, rather than found by fix rounds against it (LF.1442).
            from app.graph import suite_gate as _the_gate

            if repair := _the_gate.repair_before_the_lock(root, findings, graded):
                logger.info("At the review's limit, %d finding(s) of tests that fail on a correct product go back once "
                            "to be repaired", len(repair) - 1)
                _keep_before_the_send_back(root)
                return _handing_on(**update, stage="acceptance_author", acceptance_feedback=repair)

    if approved_by_a_person:
        findings = [*findings, *suite_gate.approved_qa_lead_findings(state)]
    # Thorough delivery locks no suite with a gating finding open: it waits for a person instead (TG.2).
    if (waiting := suite_gate.before_the_lock(state, update, root=root, problems=problems, findings=findings,
                                              graded=graded, cannot=cannot, raised=raised)) is not None:
        return waiting
    if suite.undefer_what_a_test_now_carries(root):
        logger.info("Deferred criteria a test now carries are no longer deferred")
    suite.lock(root)
    update.update(product_at_fault.settled(root, no_fault_found))
    if settled:
        _decide(
            state, update, point="acceptance_tests",
            question="The harness's finding these locked tests were sent for repair on no longer holds: do they change?",
            options=["they stay as they were locked", "QA repairs them"],
            decision="they stay as they were locked",
            rationale="No check that can reopen the suite names them now, on this measurement: "
                      + "; ".join(settled),
        )
    if no_fault_found:
        logger.warning("QA found no fault in the test(s) sent for repair, and the harness's checks agree; locked, nothing charged")
        _decide(
            state, update, point="acceptance_tests",
            question="QA found no fault in the tests a dispute sent back: is the failure the product's?",
            options=["the tests stay locked and the product is fixed", "QA repairs the tests"],
            decision="the tests stay locked and the product is fixed",
            rationale="; ".join(no_fault_found),
        )
    from app.acceptance.interface_contract import probe_at_the_lock, record_at_lock

    record_at_lock(root, getattr(state.get("technical_specification"), "interface_contract", None) or (),
                   specification=state.get("technical_specification"))
    contract_coverage.record_at_lock(root)
    from app.graph.engineering import suite_locked

    suite_locked(root)
    # After the lock is complete: the checks start the product, and their files are their own.
    if errors_at_lock := probe_at_the_lock(root):
        logger.warning("The contract's checks at the lock made the server fail on %d line(s)", len(errors_at_lock))
    open_problems = [*problems, *findings]
    if adding is not None and adding.get("base"):
        # A sprint's lock adds to the earlier ones: what they were locked with still open stays named.
        open_problems = list(dict.fromkeys([*(state.get("acceptance_open_problems") or []), *open_problems]))
    _record_document(state, "docs/acceptance_tests.md", _scenarios(root))
    tests = len(result.report.tests)
    _decide(
        state, update, point="acceptance_tests",
        question="Is the acceptance suite a fair definition of done?",
        options=["lock it", "send it back to QA"],
        decision="lock it",
        rationale=(
            what_the_lock_ran(result, len(suite.criteria(root))) + "; "
            + (("every criterion is covered; locked again on the harness's checks, without the QA lead's review."
                if targeted else "every criterion is covered and the QA lead approved.")
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

        stage = "technical_lead" if return_to == SPRINT_REPLAN else return_to
        measured_again = why_measured_again(root, result) if return_to == SPRINT_REPLAN else ""
        if measured_again == GREEN:
            # Measured three times in one day: a dispute at an attempt's end repaired the suite, it then passed in full
            # beside passing unit tests, and the sprint was planned again anyway - a lead's re-plan on a done product.
            logger.warning("The repaired suite passes in full and the unit tests pass: measured again, not planned again")
            stage = "test_and_triage"
        elif measured_again == NEAR_GREEN:
            # Of 45 near-green re-plans that beat the best, 19 got there from the repair alone, then re-planned for
            # about 25 more minutes (LR.53, `NEAR_GREEN_REPAIR_TO_ROUND`).
            from app.graph import near_green_repair

            passed, failed = near_green_repair.counts(result)
            logger.warning("The repaired suite passes %d of %d: measured again, not planned again", passed,
                           passed + failed)
            _decide(
                state, update, point="sprint",
                question="Is a sprint whose repaired suite is near green planned again?",
                options=["plan it again", "measure it again in a test round"],
                decision="measure it again in a test round",
                rationale=f"{near_green_repair.SAID}: {passed} of {passed + failed} locked test(s) pass.",
            )
            stage = "test_and_triage"
        if measured_again:
            # The re-plan's entry cleared the plan; the round needs one (`the_plan_a_round_measures`).
            update = {**update, "milestone_plan": the_plan_a_round_measures(state)}
        return _handing_on(
            **update,
            stage=stage,
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
    next_stage = "user_review_acceptance" if _review_enabled(state, ACCEPTANCE_REVIEW) else after_the_suite_is_locked(state)
    return _handing_on(
        **update,
        stage=next_stage,
        acceptance_feedback=[],
        acceptance_open_problems=open_problems,
        acceptance_result=result.as_dict(),
    )


# --- the suite written a sprint at a time (LF.1266) ------------------------------------

def after_the_suite_is_locked(state: Any) -> str:
    """Where a locked suite goes on to, past the acceptance gate: the plan, or - where the plan came first and the
    suite is written a sprint at a time - the sprint's technical lead."""
    from app.acceptance import by_sprint

    if by_sprint.is_on(_root(state)) and getattr(state.get("sprint_plan"), "sprints", None):
        return "technical_lead"
    return "scrum_master"


def before_the_lead(state: Any) -> str:
    """The stage a sprint starts at: its tests written first where the suite is written a sprint at a time, else
    straight to its technical lead, as always."""
    from app.acceptance import by_sprint

    try:
        return "sprint_acceptance" if by_sprint.is_on(_root(state)) else "technical_lead"
    except Exception:  # noqa: BLE001 - the lead, as before
        return "technical_lead"


def sprint_acceptance(state: Any, config: RunnableConfig, ctx: Context) -> dict[str, Any]:
    """At a sprint's start: its criteria's tests are written and locked by QA before its technical lead plans it.

    The tests are written against the criteria, the brief, the interface contract and the running product of the
    earlier sprints, and added to the locked suite as its next version: the earlier sprints' files stay as they were
    locked. A criterion a re-plan moved here from a later sprint has no test yet and is written now; one moved to a
    later sprint keeps its locked tests, which run when that sprint comes (`due_tests`).
    """
    from app.acceptance import by_sprint
    from app.graph.workflow import _handing_on

    root = _root(state)
    # The scope first: the review of these tests runs only what is due now.
    record_the_sprint_scope(state)
    due = [item for item in (criteria_due(state) or []) if item.startswith("AC-")]
    to_write = by_sprint.still_to_write(root, due)
    if not to_write:
        return _handing_on(stage="technical_lead")
    sprints = list(getattr(state.get("sprint_plan"), "sprints", None) or [])
    index = int(state.get("current_sprint_index") or 0)
    by_sprint.open_for(root, to_write, sprint=index + 1, of=max(len(sprints), 1))
    update: dict[str, Any] = {}
    _decide(
        state, update, point="acceptance_tests",
        question=f"Which tests does sprint {index + 1} add to the acceptance suite before it is built?",
        options=["QA writes them now, against the product built so far", "build without them"],
        decision="QA writes them now, against the product built so far",
        rationale=(f"The suite is written a sprint at a time; {', '.join(to_write)} "
                   f"{'is' if len(to_write) == 1 else 'are'} due now and no locked test names "
                   f"{'it' if len(to_write) == 1 else 'them'}. The tests locked before stay as they are."),
        affects=to_write,
    )
    logger.info("Sprint %d of %d: QA writes the tests of %s before the build", index + 1, len(sprints),
                ", ".join(to_write))
    return _handing_on(**update, stage="acceptance_author", acceptance_round=0, acceptance_feedback=[])


def _an_addition_left_out(state: Any, root: str | Path, why: str) -> dict[str, Any] | None:
    """A later sprint's addition that ran out of rounds unable to run or prove anything is left out, its criteria
    deferred, and the suite stays as the earlier sprints locked it; None for any other writing (a first writing still
    fails the run, as before)."""
    from app.acceptance import by_sprint
    from app.graph.workflow import _handing_on

    adding = by_sprint.addition(root)
    if adding is None or not adding.get("base"):
        return None
    for relative in by_sprint.new_files(root):
        (Path(root) / relative).unlink(missing_ok=True)
    by_sprint.put_back_what_the_addition_changed(root)
    criteria = list(adding.get("criteria") or [])
    suite.defer(root, {item: f"its tests could not be written for its sprint: {why}"[:400] for item in criteria})
    suite.lock(root)
    logger.warning("A sprint's addition to the suite could not be locked; left out, %s deferred", ", ".join(criteria))
    result = suite.run(root)
    return _handing_on(
        stage="release" if state.get("acceptance_return_to") == "release" else "technical_lead",
        acceptance_return_to=None,
        acceptance_feedback=[],
        acceptance_open_problems=list(state.get("acceptance_open_problems") or []),
        acceptance_result=result.as_dict(),
    )


def the_rest_written_before_the_release(state: Any) -> dict[str, Any] | None:
    """At release, where the suite is written a sprint at a time: QA writes, once, the tests of any criterion that has
    none; a criterion still without one is deferred, named among the release's cuts. None when there is nothing to
    write. Never raises."""
    try:
        from app.acceptance import by_sprint
        from app.graph.workflow import _handing_on

        root = _root(state)
        if not by_sprint.is_on(root):
            return None
        missing = by_sprint.still_to_write(root, [criterion.id for criterion in suite.criteria(root)])
        if not missing:
            return None
        asked = set(by_sprint.asked_at_release(root))
        if all(item in asked for item in missing):
            suite.defer(root, {item: by_sprint.NEVER_WRITTEN for item in missing})
            logger.warning("No locked test was written for %s before the release; deferred", ", ".join(missing))
            return None
        sprints = list(getattr(state.get("sprint_plan"), "sprints", None) or [])
        by_sprint.open_for(root, missing, sprint=max(len(sprints), 1), of=max(len(sprints), 1), at_release=True)
        logger.warning("At release %s have no locked test; QA writes them first", ", ".join(missing))
        return _handing_on(stage="acceptance_author", acceptance_return_to="release", acceptance_round=0,
                           acceptance_feedback=[])
    except Exception as error:  # noqa: BLE001 - the release goes on as it would have
        degraded("release.the_rest_written", error)
        return None


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
    from app.acceptance import passed_unbuilt

    unproven = passed_unbuilt.unproven(root, saved)
    lines = []
    for item in due:
        tests = covered.get(item, [])
        lines.append(
            f"- {item}: {texts.get(item, '')}"
            + (f" - currently {passed_unbuilt.shown(status[item], item, unproven)}" if status.get(item) else "")
            + (f"\n    tests: {'; '.join(tests[:4])}" if tests else "")
        )
    return (
        "\n\n--- Acceptance criteria this milestone must leave passing ---\n"
        + "\n".join(lines)
        + f"\nThe tests are in `{suite.relative_directory(root)}/` and are locked: read them to "
        "see exactly what each checks - the labels, routes, commands or names it uses - and "
        "plan work orders that make them pass. The milestone is not accepted until they do."
    )


def record_the_sprint_scope(state: Any) -> list[str] | None:
    """Record the sprint now built, the criteria it does not owe and the plan's criteria by sprint; the ids not yet
    due, or None when there is no plan to record. Never raises.

    Every run of the suite reads it (`app.acceptance.due_tests`): the due tests run, a later sprint's do not.
    """
    try:
        from app.acceptance import sprint_scope

        root = _root(state)
        sprints = list(getattr(state.get("sprint_plan"), "sprints", None) or [])
        index = int(state.get("current_sprint_index", 0) or 0)
        if not sprints or index >= len(sprints):
            return None
        due = criteria_due(state)
        later = [] if due is None else [c.id for c in suite.criteria(root) if c.id not in due]
        sprint_scope.record(
            root, sprint=index + 1, of=len(sprints), not_yet_due=later,
            sprints=[list(getattr(sprint, "criteria", None) or []) for sprint in sprints],
        )
        return later
    except Exception as error:  # noqa: BLE001 - the scope recorded before stands
        degraded("acceptance.sprint_scope_recorded", error)
        return None


def run_for_sprint(state: Any) -> tuple[suite.AcceptanceResult | None, list[str]]:
    """The harness's own run of the suite, and the ids due now. (None, []) when there is no suite.

    The sprint's scope is recorded from the state first, so the run takes the tests due now and no other.
    """
    root = _root(state)
    if not suite.criteria(root) or not suite.is_locked(root):
        return None, []
    due = criteria_due(state) or []
    record_the_sprint_scope(state)
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
    from app.acceptance import criteria as _criteria

    failing = [
        entries[item] for item in due
        if item in entries and entries[item].get("status") in {"failed", "untested"}
        # A criterion that only says the others hold has no test to run: untested is its normal state.
        and not (entries[item].get("status") == "untested" and _criteria.is_an_aggregate(entries[item].get("text") or ""))
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
    # A batch of fixes run side by side is measured as `defect_fix_{round}_batch` (`defect_fix_parallel_node`).
    measured_since = rf"(?:before|after) defect_fix_{int(state.get('test_round', 0) or 0)}_(?:\d+|batch)"
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
    # A page that does not draw records the way the brief shows them has work left, whatever the suite says.
    if suite.records_the_page_never_makes(root, getattr(state.get("document"), "text", "") or ""):
        return ""
    # Measured on this sprint's due tests, not the sprint before's (LF.1265).
    record_the_sprint_scope(state)
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


def pack_contract_defects(state: Any) -> list[Any]:
    """A defect for each export the pack's scaffold depends on that a stage's rewrite of its entry file dropped."""
    from app.agents.specialists import ReportedDefect
    from app.stacks import entry_exports

    root = _root(state)
    lost = entry_exports.what_the_entry_no_longer_exports(root)
    called_bare = entry_exports.what_the_start_file_cannot_call(root)
    changed = entry_exports.what_the_entry_no_longer_declares(root)
    if not lost and not called_bare and not changed:
        return []
    defects = []
    for path, written in changed:
        callers = entry_exports.callers_passing_arguments(root, path, written)
        calls = ("; ".join(f"{where} calls `{line}`" for where, line in callers) + ". Change those calls in the same "
                 f"fix to match `{written}`, or the product stops compiling and the fix is reverted.") if callers else ""
        defects.append(ReportedDefect(
            description=f"{path}{entry_exports.NO_LONGER_DECLARES}{written}`, the declaration the scaffold's build, start "
                        "file and tests rely on.",
            severity="blocking",
            reproduction_steps=f"Read {path}: its declaration differs from `{written}`.",
            expected_behavior=(f"{path} declares exactly `{written}`, as the scaffold wrote it; change what it does "
                               "inside, not how it is declared. The compiler reports this where the name is used, "
                               "not here." + (f" {calls}" if calls else "")),
            actual_behavior=f"{path} does not declare `{written}`.",
            affected_files=[path, *(where for where, _ in callers)],
            owner=_owner_for(state, ""),
        ))
    for path, name, needed in called_bare:
        defects.append(ReportedDefect(
            description=f"{path} declares `{name}({needed})`, but the scaffold's start file and unit smoke test call `{name}()` with no arguments, so `{needed}` is undefined on every request.",
            severity="blocking",
            reproduction_steps=f"Read {path} and the pack's start file: it calls `{name}()`.",
            # Optional, not removed: measured on one run, the defect said "takes no parameters", the run's own unit
            # tests called `createApp(dataDir)`, and five fixes that dropped the parameter were reverted for them.
            expected_behavior=(
                f"`{name}()` can be called with no arguments: make `{needed}` optional, with a default that makes "
                "what it needs itself (read the data directory from the environment, create the store inside it), as "
                "the pack's guide says. Callers that pass it keep working, so keep its name and its use."
            ),
            actual_behavior=f"`{name}` requires `{needed}`; called with none, it is undefined wherever it is used.",
            affected_files=[path],
            owner=_owner_for(state, ""),
        ))
    for path, name in lost:
        defects.append(ReportedDefect(
            description=f"{path} no longer exports `{name}`, which the scaffold's start file and unit smoke test import.",
            severity="major",
            reproduction_steps=f"Read {path}: it has no `export` of `{name}`.",
            expected_behavior=(
                f"{path} keeps exporting `{name}`: the harness's own files import it by that name, and so "
                "do the tests written for it. Add routes to what it builds; do not replace or rename it."
            ),
            actual_behavior=f"{path} does not export `{name}`.",
            affected_files=[path],
            owner=_owner_for(state, ""),
        ))
    return defects


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
        defined = interface_checks.where_selectors_are_defined(
            root, [where for rule in broken for where in rule.get("where") or []])
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
                + "".join(f" {ACCESSIBILITY_REMEDIES[rule.get('id')]}" for rule in broken
                          if rule.get("id") in ACCESSIBILITY_REMEDIES)
                + _the_shades_that_read([why for rule in broken if rule.get("id") == "color-contrast"
                                         for why in rule.get("why") or []])
            ),
            actual_behavior=listed[:1500] + (
                " Where those elements are made and styled: " + "; ".join(defined) if defined else ""),
            affected_files=sorted({line.split(":", 1)[0] for line in defined}),
            owner="ui_ux",
            regression_test_required=False,
        ))
    brief = str(getattr(state.get("document"), "text", "") or "")
    disabled = interface_checks.named_controls_disabled_on_load(brief, str(saved.get("shows") or ""))
    if disabled:
        where = interface_checks.where_controls_are_disabled(root)
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
                "what is missing." + DISABLED_CONTROL_UNIT_TESTS
            ),
            actual_behavior=(
                f"{named} disabled on load, as the page shows it."
                + (" The lines that disable a control, each to change so the control stays usable and the "
                   "action is refused with a message when it cannot go ahead: " + "; ".join(where) if where else "")
            ),
            affected_files=sorted({line.split(":", 1)[0] for line in where}),
            owner="ui_ux",
            regression_test_required=False,
        ))
    renamed = interface_checks.named_controls_renamed(brief, str(saved.get("shows") or ""))
    if renamed:
        listed = ", ".join(f'"{name}" is shown as "{shown}"' for name, shown in renamed)
        defects.append(ReportedDefect(
            description=(
                f"A control the brief names has another name on the page: {listed}. A person who asks for it "
                "by the brief's name - a screen reader, a voice command, a customer's own check - finds nothing."
            ),
            severity="major",
            reproduction_steps=(
                "Load the page and read what it shows: the harness's page check records each "
                "control with its accessible name before any test touches it."
            ),
            expected_behavior=(
                "Each control the brief names has exactly that accessible name. Anything shown beside it - a "
                "count, an icon - sits outside the name, in its own element."
            ),
            actual_behavior=f"{listed}, as the page shows it.",
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
    # The token stylesheet loaded, contrast in both schemes, styles that match the markup (PQ.5); the states the
    # specification names, shown (PQ.8, behind `INTERFACE_STATES_AS_CRITERIA`).
    from app.analysis import interface_style_checks

    defects += interface_style_checks.defects(root, saved.get("accessibility") or [])
    defects += interface_style_checks.states_defect(state, root)
    return defects


from app.acceptance.suite import what_the_server_logged  # noqa: E402 - kept here for its callers


#: A product frame in a logged stack: `(file://)?<path>:<line>`.
_A_PRODUCT_FRAME = re.compile(r"(?:file://)?((?:[\w@.-]+/)*[\w@.-]+\.(?:ts|tsx|js|mjs|cjs|py)):(\d+)")
#: A line that throws an error of its own making, and a handler that catches one, per language family.
_THROWS_ITS_OWN = re.compile(r"^\s*(?:throw\s+new\s+\w*Error\s*\(|raise\s+\w+\s*\()")
_A_HANDLER = re.compile(r"\bcatch\s*(?:\(\s*(\w*)\s*\))?\s*\{|^\s*except\b[^:]*?(?:\bas\s+(\w+))?\s*:")


def what_the_logged_frames_hide(root: str | Path, logged: str) -> str:
    """A note when the first product frame logged throws an error of its own in place of the one it caught; "".

    Measured on one run: the server logged `Error: Internal server error at NotesRepository.save
    (persistence.ts:44)`, and line 44 was `throw new Error('Internal server error')` inside `catch (_)`: the real
    cause - the folder the write needed did not exist - was thrown away, and the fixers saw only the replacement.
    """
    try:
        for match in _A_PRODUCT_FRAME.finditer(str(logged or "")):
            relative, number = match.group(1).lstrip("/"), int(match.group(2))
            if "node_modules" in relative:
                continue
            path = Path(root) / relative
            if not path.is_file():
                continue
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            if not 0 < number <= len(lines) or not _THROWS_ITS_OWN.match(lines[number - 1]):
                return ""
            above = "\n".join(lines[max(0, number - 4):number - 1])
            handler = _A_HANDLER.search(above)
            if handler is None:
                return ""
            caught = handler.group(1) or handler.group(2) or ""
            if caught and caught != "_" and re.search(rf"\b{re.escape(caught)}\b", lines[number - 1]):
                return ""  # it passes on what it caught
            return (f"`{relative}` line {number} throws its own error in place of the one it caught, so the real "
                    "cause is in no log: let the caught error through, or carry it (as its cause, or in the "
                    "message) while finding what fails.")
        return ""
    except Exception:  # noqa: BLE001 - the log stands as it was
        return ""


#: A test that received a server error status.
_A_5XX_RECEIVED = re.compile(r"\b(?:Received|received|status(?: code)?|got|returned)\b\W{0,12}(5\d\d)\b")

#: What a defect says when the service answered 5xx and logged nothing. Measured on one run: POST answered 500, the
#: error handler returned JSON without logging, and ten fix stages changed headers and middleware around a cause
#: none of them could see; each ended "its own tests still fail".
THE_SERVER_HID_THE_CAUSE = (
    "\nThe service answered a 5xx status and logged nothing while it did: its error handler hides the cause. First "
    "make that handler write the error it caught - message and stack - to the process's standard error, keeping the "
    "5xx answer, so the next measurement shows the cause; then fix the cause. A guess at the cause without that "
    "trace changes the wrong file."
)


def the_server_hid_the_cause(messages: list[str], logged: str, root: str | Path | None = None) -> str:
    """`THE_SERVER_HID_THE_CAUSE` when a failing test received a 5xx and the server logged nothing; else "".

    With `root`, the product's lines that answer 5xx from a `catch` are named: measured on one run, told only that
    the handler hid the cause, the next fixers rewrote other files and the log stayed empty.
    """
    from app.acceptance.what_went_wrong import states_a_cause

    # Whether the log states a cause, not whether it is empty: measured on a medium run, the saved log was five access
    # lines (`"POST /api/register HTTP/1.1" 500 Internal Server Error`) and this note was silenced for three fixers,
    # 77 minutes with no change kept (LF.1410).
    if states_a_cause(logged):
        return ""
    if not any(_A_5XX_RECEIVED.search(str(m or "")) for m in messages):
        return ""
    found = where_errors_become_5xx(root) if root is not None else []
    return THE_SERVER_HID_THE_CAUSE + (
        " It is answered here, from a catch that writes nothing: " + "; ".join(f"`{f}` line {n}" for f, n in found) + "."
        if found else ""
    )


#: A line answering a 5xx status, and a `catch`/`except`/`rescue` opening a few lines above it.
#: The status as a number, or as a named constant (`status.HTTP_500_INTERNAL_SERVER_ERROR`, `INTERNAL_SERVER_ERROR`,
#: `StatusCodes.Status500InternalServerError`): measured on a medium run, every handler answered the named constant and
#: none was found (LF.1410).
_A_5XX_ANSWER = re.compile(r"(?<![\w.])5\d\d(?![\w.])|\b\w*(?<![0-9])5\d\d(?:_?[A-Za-z]\w*)\b|\bINTERNAL_SERVER_ERROR\b"
                           r"|\bInternalServerError\b")
_A_CATCH = re.compile(r"\b(?:catch|except|rescue|recover)\b")
_A_LOG_CALL = re.compile(r"\b(?:console\.\w+|logger\.\w+|logging\.\w+|log\.\w+|print|eprintln!?|fmt\.Fprint\w*)\s*\(")
_SOURCE_SUFFIXES = (".ts", ".tsx", ".js", ".mjs", ".cjs", ".py", ".rb", ".go", ".rs", ".java", ".kt", ".php")


def where_errors_become_5xx(root: str | Path | None, most: int = 8) -> list[tuple[str, int]]:
    """(file, line) of the product's lines that answer 5xx inside a catch block that logs nothing. Never raises."""
    try:
        from app.analysis.file_kinds import classify_file
        from app.analysis.walk import files_under

        base = Path(str(root))
        found: list[tuple[str, int]] = []
        for path in sorted(files_under(base, ("node_modules", ".git", ".harness", "test-results", ".venv"))):
            relative = path.relative_to(base).as_posix()
            if path.suffix.lower() not in _SOURCE_SUFFIXES or classify_file(relative) != "application":
                continue
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            for at, line in enumerate(lines):
                if not _A_5XX_ANSWER.search(line):
                    continue
                window = lines[max(0, at - 6):at + 1]
                opened = max((i for i, w in enumerate(window) if _A_CATCH.search(w)), default=None)
                if opened is None or any(_A_LOG_CALL.search(w) for w in window[opened:]):
                    continue
                found.append((relative, at + 1))
                if len(found) >= most:
                    return found
        return found
    except Exception:  # noqa: BLE001 - a note without the lines is the note as before
        return []


def _the_start_that_fails(state: Any, reported: list[Any], command: str) -> list[Any]:
    """A defect for a product a green suite reached and its user cannot; [] otherwise.

    Measured on one run: the suite's own way of starting it passed 38 of 38, its start script could not run, the result
    said so, and with nothing failing no defect was raised.
    """
    from app.agents.specialists import ReportedDefect

    said = str((suite.last_result(_root(state)) or {}).get("problem") or "")
    if not said.startswith(suite.PRODUCT_DID_NOT_START) or any(
        str(getattr(item, "description", "") or "") == THE_PRODUCT_DOES_NOT_START for item in reported
    ):
        return []
    return [ReportedDefect(
        description=THE_PRODUCT_DOES_NOT_START,
        severity="blocking",
        reproduction_steps=f"The suite passes through `{command}`; use the product its user's way, as the failure says.",
        expected_behavior="The product works the way its user runs it, not only the way the suite reaches it.",
        actual_behavior=said[:1500],
        affected_files=[],
        owner=_owner_for(state, said),
        # Not a start the suite needs: the suite started it, so no other defect's fixer waits on this one.
        **_with_its_error_line(said, "other"),
    )]


#: The start of a defect for records the page never draws as the brief shows them.
RECORDS_NOT_AS_THE_BRIEF_SHOWS = "The page does not draw records the way the brief shows them"


def _records_the_page_never_makes(state: Any, reported: list[Any]) -> list[Any]:
    """A defect for each kind of record the brief shows that the page never makes; [] otherwise. See `suite`."""
    from app.agents.specialists import ReportedDefect

    found = suite.records_the_page_never_makes(_root(state), getattr(state.get("document"), "text", "") or "")
    if not found or any(
        str(getattr(item, "description", "") or "").startswith(RECORDS_NOT_AS_THE_BRIEF_SHOWS) for item in reported
    ):
        return []
    said = " ".join(found)
    return [ReportedDefect(
        description=f"{RECORDS_NOT_AS_THE_BRIEF_SHOWS}: {said}"[:600],
        severity="blocking",
        reproduction_steps="Read the page's markup, scripts and templates for the element each record is drawn as.",
        expected_behavior="Each record is drawn as the brief shows it, so it is found by its role.",
        actual_behavior=said[:1500],
        affected_files=[],
        owner=_owner_for(state, said),
        kind="probe_finding",
        evidence=[{"probe": "records drawn as the brief shows them", "request": str(item)[:300]} for item in found][:24],
    )]


def failing_due_defects(state: Any, reported: list[Any]) -> list[Any]:
    """A defect for each due criterion that fails and that the round did not report.

    The round is handed the suite's result and asked to report every failing
    criterion with its owner; this is the backstop for one it leaves out, so a
    red criterion can never reach the milestone review unreported.
    """
    failing, command = _failing_due(state)
    # Whether or not anything fails: a manifest that does not install ships a
    # product a clean checkout cannot run. Measured on one gate run: the
    # product ran on what an earlier install left, 31 of 34 tests passed, and
    # the `requirements.txt` it would have released failed every install.
    installs = [
        defect for defect in _the_install_that_failed(suite.last_result(_root(state)) or {}, state)
        if not any("do not install" in str(getattr(item, "description", "") or "") for item in reported)
    ]
    # Whether or not anything fails, too: a suite on a development server never goes through the build.
    installs = [*installs, *_the_build_that_fails(state, reported)]
    if not failing:
        return [*installs, *_the_start_that_fails(state, reported, command), *_records_the_page_never_makes(state, reported)]
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
    seen = f"{WHAT_THE_PRODUCT_SHOWS}{shown[:600]}" if shown else ""
    never_started = str(saved.get("problem") or "")
    if never_started.startswith(suite.PRODUCT_DID_NOT_START):
        # One defect for the one cause: nothing could be measured while it stands.
        compiled, compiler_said = compiler_errors.the_errors_found(_root(state))
        from app.sprint import cause as _cause

        defects.append(ReportedDefect(
            description=THE_PRODUCT_DOES_NOT_START,
            severity="blocking",
            reproduction_steps=f"Run `{command}` in the project directory: the product fails before any test runs.",
            expected_behavior="The product builds and starts, and the acceptance suite's tests run against it.",
            actual_behavior=(never_started[:1500] + _what_the_start_shows(_root(state))
                             + (f"\n\n{wrote}" if (wrote := start_output.in_text(str(saved.get("server_log") or ""))) else "")
                             + compiled),
            affected_files=[],
            owner=_owner_for(state, never_started),
            kind=_cause.START_FAILURE,
            # The error the start ended on, and each compiler error, as the start's evidence (deep review 1.1).
            evidence=[
                *([line] if (line := _cause.an_error_line(never_started)) else []),
                *(_cause.a_compiler_error(file, at, code, message) for file, at, code, message in compiler_said),
            ][:_cause.MOST_EVIDENCE],
        ))
        return defects + installs + _what_the_language_service_finds(state) + _records_the_page_never_makes(state, reported)
    if never_started.startswith(suite.PRODUCT_CRASHED):
        # One defect for the one cause, first: the criteria it took down are its symptoms, each failing only on a
        # connection to a service that was gone. A criterion with any other failure keeps its own defect.
        defects.append(ReportedDefect(
            description=THE_PRODUCT_CRASHED,
            severity="blocking",
            reproduction_steps=f"Run `{command}` in the project directory: the service exits part-way through the suite.",
            expected_behavior="The service keeps answering for the whole suite; an error in one request is answered, not fatal.",
            actual_behavior=never_started[:2200],
            affected_files=[],
            owner=_owner_for(state, never_started),
            **_with_its_error_line(never_started, "failing_test"),
        ))
        failing = [entry for entry in failing if not all(
            suite._THE_SERVICE_WAS_GONE.search(t.get("message") or "")
            for t in (entry.get("tests") or []) if t.get("outcome") == "failed")]
    # The same refusal everywhere (LR.53): measured on one run, 16 tests of 14 criteria all failed with `assert 401 ==
    # 201` - the product refused the token its own sign-in issued - and each criterion got a fixer of its own, shown
    # one test, who sent the file back unchanged; round 2 ran ten fixers in three hours. One cause, one defect.
    refused = one_refusal_for_all(failing)
    # One step many tests stop at with one answer (LF.1259): a shared helper's line, or the requests under one path,
    # raised once and ahead of the criteria it stops. Measured on one run: beside a rate limit, 8 tests threw a 401 at
    # the suite's helper and 13 were answered 404 under one prefix; each criterion got its own defect and fixer.
    steps = first_failing_step.clusters(failing, _root(state))
    if refused is not None:
        code, count = refused
        # Beside one refusal, only another status is another cause; any other failure is the refusal's symptom.
        steps = [step for step in steps if step.status and step.status != code]
        apart = _the_tests_of(steps)
        cause = ("the product refuses the credentials its own sign-in issues, or asks for some no client is given"
                 if code in ("401", "403") else A_LIMIT_THE_SUITE_MEETS if code == RATE_LIMITED else
                 "one thing the routes share answers it for every request - the way a body is read or checked, a field "
                 "every write needs, a lookup every route makes")
        defects.append(ReportedDefect(
            description=(f"{count} acceptance tests across {len(failing)} criteria are all answered {code} where they expect "
                         f"another answer: {cause}."),
            severity="blocking",
            reproduction_steps=f"Run `{command}`: every failing test's request is answered {code}.",
            expected_behavior="Each route answers as the interface says for a well-formed request.",
            actual_behavior=f"Every such call answers {code}. Find the one place the failing routes share that answers "
                            f"{code}, and fix it there; each criterion's own failures are measured again after."
                            + _what_one_of_them_said(state, code),
            affected_files=[],
            owner=_owner_for(state, f"refused {code}"),
            kind="failing_test",
            # Its own tests: those another status stops at a step of its own are that step's evidence.
            evidence=_the_failing_tests_of([
                {**entry, "tests": kept} for entry in failing
                if (kept := [t for t in entry.get("tests") or [] if id(t) not in apart])
            ]) if apart else _the_failing_tests_of(failing),
        ))
        defects.extend(a_step_many_tests_stop_at(state, step, command) for step in steps)
        return [*installs, *defects]
    defects.extend(a_step_many_tests_stop_at(state, step, command) for step in steps)
    stopped = _the_tests_of(steps)
    # A criterion every failing test of which stops at such a step is that step's, not raised again this round.
    failing = [entry for entry in failing if not (
        (failed := [t for t in entry.get("tests") or [] if t.get("outcome") == "failed"])
        and all(id(t) in stopped for t in failed))]
    # A page whose own script did not load, or threw while loading, is dead: every criterion on it fails for that one
    # cause. Measured on one run: the page's script answered 404, all 17 criteria were raised, and each got a fixer of
    # its own (19 calls each) shown only timeouts. As with a product that never starts, the round raises the one cause
    # alone; the next round measures again and raises whatever still fails.
    page_is_dead = any(_THE_PAGE_DID_NOT_RUN.search(str(p)) for p in problems)
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
        if page_is_dead:
            return [*installs, *defects]
    # From the whole run, kept as it ran: the saved output is its tail, and an early error was cut (LF.355).
    logged = str(saved.get("server_log") or "") or what_the_server_logged(str(saved.get("output") or ""))
    # A defect the round wrote itself about a failing criterion takes the place of the one below, so it carries this too.
    ids = {entry.get("id") for entry in failing}
    for said_of_it in (suite.what_a_stopped_service_wrote(logged), start_output.in_text(logged)):
        if not said_of_it:
            continue
        for item in reported:
            actual = str(getattr(item, "actual_behavior", "") or "")
            if said_of_it not in actual and ids & set(tags_in(str(getattr(item, "description", "") or ""))):
                item.actual_behavior = f"{actual}\n{said_of_it}".strip()
    for entry in failing:
        tests = entry.get("tests") or []
        failed = [t for t in tests if t.get("outcome") == "failed"] or tests
        # Its tests a shared step stops are that step's defect's.
        failed = [t for t in failed if id(t) not in stopped] or failed
        # A locked test that matched nothing through an item found by a text it may have lost to its own action: said
        # once, on the defect the round wrote itself for this criterion or on the one raised below.
        hint = suite.what_a_text_lost_to_an_action_tells_the_fixer(
            _root(state), [(str(t.get("name") or ""), str(t.get("message") or "")) for t in failed])
        if entry.get("id") in mentioned:
            for item in reported if hint else ():
                actual = str(getattr(item, "actual_behavior", "") or "")
                if hint not in actual and entry.get("id") in tags_in(str(getattr(item, "description", "") or "")):
                    item.actual_behavior = f"{actual}\n{hint}".strip()
            continue
        detail = the_failed_tests_line(failed)
        # What the page showed when the first of them failed: whether the
        # control is absent, misnamed, or never appeared after the action.
        met = next((suite.page_it_failed_on(t.get("message", "")) for t in failed if suite.page_it_failed_on(t.get("message", ""))), "")
        if met:
            detail += f"{THE_PAGE_WHEN_IT_FAILED}{met}"
        if hint:
            detail += f"\n{hint}"
        detail += server_log_block(_root(state), logged)
        hid = the_server_hid_the_cause([t.get("message") or "" for t in failed], logged, _root(state))
        detail += hid
        # What the page reported while it loaded is likely why this criterion fails too: measured on one run, the
        # page's own script answered 404, every criterion timed out waiting for a request it could never send, and the
        # fixers of each criterion - shown only the timeouts - spent 19 calls each without the cause.
        if problems:
            detail += f"\n{THE_PAGE_REPORTED_WHILE_LOADING}" + "; ".join(str(p) for p in problems)[:600]
        defects.append(ReportedDefect(
            description=f"[{entry.get('id')}] {entry.get('text')} - the acceptance suite says this does not work yet.",
            severity="major",
            reproduction_steps=f"Run `{command}` in the project directory and read the {entry.get('id')} tests.",
            expected_behavior=str(entry.get("text") or ""),
            actual_behavior=detail + seen,
            affected_files=sorted({f for f, _ in where_errors_become_5xx(_root(state))}) if hid
            else _the_files_its_5xx_logged(_root(state), failed, logged),
            owner=_owner_for(state, detail),
            kind="failing_test",
            evidence=_the_failing_tests_of([{**entry, "tests": failed}] if stopped else [entry]),
        ))
    return [*installs, *defects]


def _the_files_its_5xx_logged(root: Any, failed: list[dict], logged: str) -> list[str]:
    """The product files the server's logged trace names, for a criterion whose failed tests received a 5xx; [] for
    any other (LF.1401: such a defect named no file, and the rewrite after a surrender found none)."""
    if not any(_A_5XX_RECEIVED.search(str(t.get("message") or "")) for t in failed):
        return []
    from app.acceptance.logged_files import files_the_log_names

    return files_the_log_names(root, logged)


def _the_failing_tests_of(entries: list[dict]) -> list[dict[str, Any]]:
    """Each failing test of these criteria as evidence (deep review 2026-11-18, item 1.1); a criterion none of whose
    tests failed or ran is evidenced by its own id, so two such criteria are never one cause."""
    from app.sprint import cause as _cause

    found: list[dict[str, Any]] = []
    for entry in entries:
        tests = [t for t in entry.get("tests") or [] if t.get("outcome") == "failed"]
        found.extend(_cause.a_failing_test(t.get("name"), t.get("file"), entry.get("id")) for t in tests)
        if not tests:
            found.append(_cause.a_failing_test(f"no test of {entry.get('id')} passed", "", entry.get("id")))
    return found


def _with_its_error_line(text: str, kind: str) -> dict[str, Any]:
    """`kind`, and the error line `text` ends on as evidence, for a defect a failed install, build or start raised;
    {} when the text states no error."""
    from app.sprint import cause as _cause

    line = _cause.an_error_line(text)
    return {"kind": kind, "evidence": [line]} if line else {}


#: A load error that leaves the page without its script: the script itself failed to load, or threw while loading.
_THE_PAGE_DID_NOT_RUN = re.compile(r"(?:HTTP 404|request failed|ERR_\w+)[^;]*\.(?:m?js|ts|tsx|jsx)\b|uncaught", re.I)


#: Said before the page's own load errors, on each criterion's defect while they stand.
THE_PAGE_REPORTED_WHILE_LOADING = "While it loaded, before any test acted, the page itself reported: "

#: How a failing criterion's defect opens what the product's server logged while the suite ran (`server_log_block`).
SERVER_LOG_HEADING = "What the product's server logged while the suite ran:"
#: What the product shows when it loads, as a failing criterion's defect says it after the server's log: on a line of
#: its own (LF.1458), for the first line - the failed tests - to be replaced without it (`fresh_evidence`). It opened
#: with a space and sat at the end of that line; measured on one run, 15 briefs lost it, and the page at load, "No
#: bookmarks yet", read as the page the test met, which listed the bookmark.
PRODUCT_SHOWS_LABEL = "What the product shows when it loads, before any test touches it:"
WHAT_THE_PRODUCT_SHOWS = f"\n{PRODUCT_SHOWS_LABEL}\n"


def the_failed_tests_line(failed: list[dict]) -> str:
    """The line a failing criterion's defect opens with: its first three failed tests, each with what it said - its
    error and the values it got, past the runner's heading for the test (LF.1393)."""
    from app.acceptance.failure_said import what_it_said

    return "; ".join(
        f"{t.get('name')}: " + (what_it_said(t.get("message")) or "failed")
        for t in failed[:3]
    ) or "no test carrying this id ran"


def server_log_block(root: Any, logged: str) -> str:
    """What the product's server logged, as a failing criterion's defect carries it, with what its frames hide; ""
    when it logged nothing."""
    if not logged:
        return ""
    hidden = what_the_logged_frames_hide(root, logged)
    return f"\n{SERVER_LOG_HEADING}\n{logged}" + (f"\n{hidden}" if hidden else "")


def due_criteria_failing(state: Any) -> str:
    """What the milestone review must not accept: due criteria the suite says fail."""
    from app.acceptance.failure_said import what_it_said

    failing, command = _failing_due(state)
    if not failing:
        return ""
    lines = [
        f"- {entry.get('id')}: {entry.get('text')}"
        + "".join(
            # What each said past its runner's heading (LF.1461), not the heading.
            f"\n    {t.get('name')}: {what_it_said(t.get('message'), 200) or 'failed'}"
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


def _which_tests(state: Any, item: str) -> list[str]:
    """The tests a finding is about: the titles at the file and lines it names, else its first quoted name.

    Measured on one run: a file-level finding was known by its file, so an earlier false finding for the same file
    made a real one "already sent", and its criteria - read from tags the finding's text does not carry - were
    never deferred; fixers were sent a test fault.
    """
    try:
        titles = suite._the_tests_at(_root(state), item)  # noqa: SLF001 - the suite's own reading of a finding
    except Exception:  # noqa: BLE001 - known by its first name, as before
        titles = []
    return titles or [_which_test(item)]


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
    fresh = {name for item in broken for name in _which_tests(state, item)} - sent
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
    # Causes when the dispute counted them (one broken helper is one), tests before that.
    causes = state.get("suite_reclassified_causes")
    done = int(causes) if causes is not None else len(set(state.get("suite_reclassified_tests") or []))
    return max(0, most_reclassifications(_root(state)) - done)


#: A name defined in a suite as something its tests call or receive: a function, a fixture, a constant holding one.
_A_SUITE_DEFINITION = r"""(?:^|\n)[ \t]*(?:@pytest\.fixture[^\n]*\n[ \t]*)?(?:async\s+)?(?:def|function)\s+{name}\s*\(|(?:const|let|var)\s+{name}\s*=|^\s*{name}\s*=\s*\w"""
#: A name a ruling quotes, in backticks or as code: `_compute_words`, auth_token.
_A_QUOTED_NAME = re.compile(r"`([A-Za-z_][A-Za-z0-9_]{2,})`|\b([a-z_][a-z0-9_]*_[a-z0-9_]+)\b")


#: In the description of the one defect raised for one wrong answer behind many tests (`one_refusal_for_all`), and of
#: the one raised for one step many tests stop at (`a_step_many_tests_stop_at`).
ONE_CAUSE_MARK = "acceptance tests across"
_ANY_STATUS = first_failing_step.ANY_STATUS
_the_wrong_answer = first_failing_step.the_wrong_answer


def _what_one_of_them_said(state: Any, code: str) -> str:
    """For a server error behind every route, what one such request is answered, asked once by the contract's probe; "".

    The suite's failures name the status only. Measured on a Rust run: every route answered 500 "Missing request
    extension: Extension of type `AppState` was not found" - the cause, in the product's own words - and three sprint
    attempts were shown only "Expected: 201, Received: 500". Never raises.
    """
    if not str(code).startswith("5"):
        return ""
    try:
        from app.acceptance import interface_contract

        root = _root(state)
        interface_contract.server_errors(root)
        said = interface_contract.what_a_server_error_said(root)
        return f" One such request, sent again by the harness: {said[:900]}" if said else ""
    except Exception:  # noqa: BLE001 - the defect as it was
        return ""


#: The status a rate limit answers.
RATE_LIMITED = first_failing_step.RATE_LIMITED
#: What a rate limit refusing the suite is, said to the fixer.
A_LIMIT_THE_SUITE_MEETS = (
    "the product limits how often one client may call it (a sign-up or sign-in limit), and the acceptance suite, like "
    "any client, makes many calls from one address: once the limit is reached every later request is refused. Keep "
    "the limit, but size it for the use the brief describes - a suite that signs up an account per test is such use - "
    "or read it from the environment with a default that use passes"
)


def one_refusal_for_all(failing: list[dict]) -> tuple[str, int] | None:
    """(the status, how many tests) when nearly every failing test was refused the same way; None otherwise.

    Three criteria at least; three tests at least, and half of the failed tests, answered the same status where they
    expected another (`assert 401 == 201`, `assert 422 == 201`), or threw an error naming it (`first_failing_step`);
    and no failed test answered any other status: one cause, not one per criterion. Never raises.
    """
    try:
        tests = [t for entry in failing for t in (entry.get("tests") or []) if t.get("outcome") == "failed"]
        if len(failing) < 3 or not tests:
            return None
        # The answer each test got where it wanted another (`assert 422 == 201`, or a browser runner's `toBeOK()`
        # failing on `<- 500 ...`), or the refusal an error it threw names: the same wrong answer everywhere. Measured
        # on one run: 37 of 80 failing tests asserted 429 and 18 more threw "Login rate limited" at one line of the
        # suite's shared helper; read from the assertions alone the limit was under half and never raised.
        answered = first_failing_step.answers(tests)
        codes = [code for code in answered if code.isdigit()]
        if not codes:
            return None
        code = max(set(codes), key=codes.count)
        # Another status anywhere is another cause; a failure with none (a body read after a refused call: `KeyError:
        # 'id'`, measured beside 401s on one run) is the refusal's symptom.
        others = [t for t, answer in zip(tests, answered)
                  if (seen := answer or ((m := _ANY_STATUS.search(str(t.get("message") or ""))) and m.group(1)))
                  and seen != code]
        # Half the failed tests for a client error; a third for a server error, which breaks what every later step
        # reads (measured: every write answered 500 and the page tests, finding nothing saved, outnumbered them).
        share = 3 if code.startswith("5") else 2
        # A rate limit's 429 is no criterion's own answer: once it refuses, every later step of every test is refused,
        # so other answers beside it do not make it one cause among many. Measured on one run: 66 of 92 failing tests
        # were answered 429 by a sign-up limit of ten an hour, 26 others answered otherwise, so no one defect was raised;
        # each criterion got its own fixer for eight hours and the suite never moved past 17 of 97.
        if code == RATE_LIMITED and codes.count(code) >= 3 and codes.count(code) * 2 >= len(tests):
            return code, codes.count(code)
        if others or codes.count(code) < 3 or codes.count(code) * share < len(tests):
            return None
        return code, len(tests)
    except Exception:  # noqa: BLE001 - each criterion keeps its own defect
        return None


#: What a 404 on every route under one prefix tells the fixer to do first.
EVERY_ROUTE_UNDER_ONE_PREFIX = (
    "Every route the tests call under {prefix} is answered 404, whatever the method: compare the routes the service "
    "actually serves (its route table, or what it lists at start) with the paths the tests call. A prefix given twice "
    "(once where the routes are mounted and again in each route), or left out, answers 404 for every route under it."
)


def _what_the_step_means(cluster: Any) -> str:
    """What one answer at one step means, said to the fixer."""
    code = cluster.status
    if code in ("401", "403"):
        return ("the product refuses the credentials its own sign-in issues, or asks for some no client is given")
    if code == RATE_LIMITED:
        return A_LIMIT_THE_SUITE_MEETS
    if code == "404" and not cluster.helper:
        return EVERY_ROUTE_UNDER_ONE_PREFIX.format(prefix=cluster.step)
    if code:
        return ("one thing these requests share answers it for every one of them - the way a body is read or checked, "
                "a field every write needs, a lookup every route makes")
    return ("the suite's shared step fails the same way for each of them before any of their own checks runs: what "
            "that step needs from the product is missing, or answered otherwise than the step reads it")


def a_step_many_tests_stop_at(state: Any, cluster: Any, command: str) -> Any:
    """The one blocking defect for failing tests of several criteria that stop at one step with one answer.

    Measured on one run: 8 tests threw "Login failed with status 401" at one line of the suite's helper and 13 were
    answered 404 on every route under one prefix; each criterion got a defect and a fixer of its own, and the one
    cause of every 404 was raised as eight symptom defects beside it.
    """
    from app.agents.specialists import ReportedDefect
    from app.sprint import cause as _cause

    failures = cluster.failures
    # Names in backticks, so two steps in one helper file, or under one path, are never read as one cause.
    where = (f"the suite's shared step `{cluster.step}`" if cluster.helper else
             f"every request under `{cluster.step}`" if cluster.status == "404" else f"the request `{cluster.step}`")
    answer = f"answered {cluster.answer}" if cluster.status else "with one error"
    shown = "; ".join(
        f"{f.test.get('name')}: " + (f.thrown or " ".join(part for part in (f.request, f"answered {f.answer}") if part))[:200]
        for f in failures[:3])
    said = _what_one_of_them_said(state, cluster.status) if cluster.status else ""
    return ReportedDefect(
        description=f"{len(failures)} acceptance tests across {len(cluster.criteria)} criteria stop at {where}, {answer}.",
        severity="blocking",
        reproduction_steps=f"Run `{command}`: each of these tests stops at {where}, {answer}.",
        expected_behavior="The step answers as the interface says for a well-formed request, and each test goes on to "
                          "its own checks.",
        actual_behavior=(f"{(means := _what_the_step_means(cluster).rstrip('.'))[:1].upper()}{means[1:]}. Fix it in the one place these tests share; each "
                         f"criterion's own failures are measured again after. Criteria it stops: "
                         f"{', '.join(cluster.criteria)}. For example: {shown}" + said),
        affected_files=[],
        owner=_owner_for(state, f"refused {cluster.answer}" if cluster.status else shown),
        kind="failing_test",
        evidence=[_cause.a_failing_test(f.test.get("name"), f.test.get("file"), f.criterion) for f in failures],
    )


def _the_tests_of(clusters: list[Any]) -> set[int]:
    return {id(f.test) for cluster in clusters for f in cluster.failures}


def within_the_cap_by_cause(state: Any, groups: list[list[str]]) -> tuple[list[str], list[str], int]:
    """(the rulings a reclassification may still cover, the ones past the cap, how many causes were kept).

    As `within_the_cap`, but each group of `by_shared_cause` takes one place: a helper that broke six tests is one
    repair, not six.
    """
    room = reclassification_room(state)
    kept, past, causes = [], [], 0
    for group in groups:
        if causes < room:
            kept.extend(group)
            causes += 1
        else:
            past.extend(group)
    return kept, past, causes


def by_shared_cause(rulings: list[str], suite_text: str) -> list[list[str]]:
    """The rulings grouped by one helper of the suite they all blame; a ruling naming none is a group of its own.

    A helper is a name the suite defines that is not a test - a function, a fixture - and that the ruling quotes.
    Measured on two runs: one broken helper (`_compute_words` lost its `+`) and one fixture (`auth_token`, copied with
    the same username) each failed many tests, the cap counted every test, and right criteria were deferred. Grouped,
    one cause is one repair. Never raises; on any doubt each ruling stands alone.
    """
    try:
        groups: dict[str, list[str]] = {}
        alone: list[list[str]] = []
        for ruling in rulings:
            named = [a or b for a, b in _A_QUOTED_NAME.findall(str(ruling))]
            helper = next((n for n in dict.fromkeys(named) if not n.startswith("test")
                           and re.search(_A_SUITE_DEFINITION.format(name=re.escape(n)), suite_text, re.M)), None)
            if helper is None:
                alone.append([ruling])
            else:
                groups.setdefault(helper, []).append(ruling)
        return [*groups.values(), *alone]
    except Exception:  # noqa: BLE001 - each ruling its own cause, as before
        return [[ruling] for ruling in rulings]


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
        # Only the files that hold a disputed test: the others have no bearing on the dispute, and a service suite
        # runs each file with its own server (deep review 2026-10-26).
        disputed = {tag for name in names for tag in junit.tags_in(name)}
        runs = each_file(repo_root, contract.read(repo_root) or {}, sandbox_runner(repo_root), naming=disputed or None)
        outcome = {str(run.get("file")): str(run.get("outcome")) for run in runs}
    except Exception as error:  # noqa: BLE001 - a check that cannot run re-measures nothing
        degraded("measure.disputed_tests_file_by_file", error)
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


def tests_whose_service_stayed_up(repo_root: Any, lines: list[str]) -> tuple[list[str], list[str]]:
    """(the dispute's lines to act on, the tests that stay locked because the service they started stopped by itself).

    Measured on one run: the product exited on its first write under the restart test, the test saw only "fetch
    failed", and the dispute called it impossible. QA may not change the product, so the suite went back to QA for
    nothing. Only a test in a file that starts its own service can be the one the helper reported.
    """
    from app.stacks.packs._service import SERVICE_STOPPED_BY_ITSELF  # noqa: PLC0415 - a pack's text, read here alone

    saved = suite.last_result(repo_root) or {}
    # The saved output is the run's tail; the report kept from the whole run is with what the server logged.
    output = f"{saved.get('output') or ''}\n{saved.get('server_log') or ''}"
    if SERVICE_STOPPED_BY_ITSELF not in output:
        return list(lines), []
    texts = []
    for path in suite.suite_files(repo_root):
        try:
            texts.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    starting_its_own = [text for text in texts if "startService" in text]
    kept: list[str] = []
    locked: list[str] = []
    for line in lines:
        title = line.split("`")[1] if line.count("`") >= 2 else ""
        if title and any(title in text for text in starting_its_own):
            locked.append(title)
        else:
            kept.append(line)
    return kept, locked


#: What QA is held to when it repairs a locked suite.
REPAIR_RULE = (
    "Change the tests named above, and only as far as their own code is wrong. "
    "A test not named above that has the very same fault - the same wrong step, written the same "
    "way - is repaired the same way in this pass: a locked test that cannot pass is sent back "
    "once for its fault, not once for each test that has it. "
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
        *suite.findings_that_reopen(root, result, suite.tests_that_cannot_pass(root, result)),
        *suite.tests_left_behind_by_their_own_change(root, result),
        *suite.tests_finding_a_per_record_control_on_the_whole_page(
            root, result, getattr(state.get("document"), "text", "") or ""),
        *suite.vacuous_green(root, result),
        *_due_criteria_with_no_test(root, due),
    ]
    return acceptance_requests.acceptance_block(result, due), broken


def _due_criteria_with_no_test(root: str, due: list[str]) -> list[str]:
    """The suite's gaps for criteria due now that no locked test names: QA's to write, not a fixer's to build.

    Measured on a small-model run: the suite was locked with AC-15 untested, every round raised it as a product
    defect, the dispatch closed it at once (no test of it failed), and the sprint was planned again - four rounds
    and a re-plan in two minutes, at 17 of 18 with every test passing. A product change cannot give a criterion a
    test.
    """
    wanted = {str(item) for item in due or ()}
    if not wanted:
        return []
    try:
        return [gap for gap in suite.gaps(root) if gap.split(" ", 1)[0] in wanted]
    except Exception as error:  # noqa: BLE001 - a check that cannot run reopens nothing
        degraded("check.due_criteria_without_a_test", error)
        return []


#: Where a suite repaired for a failed attempt's dispute goes back to: the
#: sprint's planning, with no change request to brief it on.
SPRINT_REPLAN = "sprint_replan"


def _kept_as_locked_before(state: dict, root: Path, why: str) -> dict | None:
    """A repair that ran out of rounds keeps its best measured version, else the suite as last locked, and goes back
    where it came from; None when the suite was never locked (a first writing still fails the run).

    Measured on one run: a suite reopened after the build, for a locked test the product's own `conftest.py` skipped,
    went five rounds and then failed the run - a product passing every hidden test, its suite 22 of 22, never released.
    The suite it had been locked with is still a fair definition of done; what the repair could not settle is a gap.
    """
    from app.graph.workflow import _handing_on

    return_to = state.get("acceptance_return_to")
    if not return_to or not suite.is_being_repaired(root):
        return None
    # The repair's best measured version, when one was kept, rather than the lock: it ran no fewer tests and passed no
    # fewer than the suite before the repair, and one exit locking an older version than another would is a lost repair.
    best = suite.the_best_of_the_repair(root)
    put_back = suite.put_back_the_best_of_the_repair(root)
    kept = "the repair's best measured version" if best else "the suite as last locked"
    suite.lock(root)
    logger.warning("A repair ran out of rounds; %s is kept (%d file(s) put back)", kept, len(put_back))
    result = suite.run(root)
    return _handing_on(
        stage="technical_lead" if return_to == SPRINT_REPLAN else return_to,
        acceptance_return_to=None,
        acceptance_feedback=[],
        acceptance_open_problems=[f"The suite's repair ran out of rounds and {kept} was kept; {why}"],
        acceptance_result=result.as_dict(),
        revision_comments=list(state.get("revision_comments") or []),
    )


def _rewritten_in_one_call_each(state: Any, broken: list[str], model: Any) -> bool:
    """Whether the named tests were rewritten in place, one gathered call each (plan item 10 part 2, `NAMED_TEST_REWRITE`)."""
    from app.graph import rewritten_tests

    if not rewritten_tests.enabled():
        return False
    try:
        from app.acceptance.api_reference import api_reference
        from app.agents.specification_rulings import the_rulings_section

        # The test at the file and line a finding names, else its first quoted name. Measured on one run: a finding
        # named `notes.spec.js` line 142, its first quoted name was the file, no test had that title, and a one-line
        # repair went to QA's whole agent loop - about 20 minutes, twice.
        done = rewritten_tests.repair(
            _root(state), broken, model, which_test=lambda item: _which_tests(state, item)[0],
            reference=api_reference(state.get("technical_specification"),
                                    getattr(state.get("document"), "text", "") or "") + the_rulings_section(_root(state)),
            reason=str(state.get("dispute_reason") or ""),
        )
    except Exception as error:  # noqa: BLE001 - QA's agent loop repairs, as before
        degraded("repair.named_tests_rewritten_in_place", error)
        return False
    return done is not None


def reopen_the_suite_for(
    state: Any, broken: list[str], return_to: str = "test_and_triage", *, reclassifying: bool = False, model: Any = None, causes: int | None = None) -> dict[str, Any] | None:
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
    try:
        from app.acceptance import suite as _suite
        from app.acceptance import suite_repair

        # What sent them: a check's finding can be run again when the repair comes back, a dispute's ruling cannot.
        _suite.repairing(state["repository"].root_path, [name for item in broken for name in _which_tests(state, item)],
                         on=suite_repair.ON_A_JUDGEMENT if reclassifying else suite_repair.ON_THE_CHECKS)
    except Exception as error:  # noqa: BLE001 - the repair goes on without its guard
        degraded("guard.tests_under_repair", error)
    before = state.get("suite_reclassified_causes")
    before = int(before) if before is not None else len(set(state.get("suite_reclassified_tests") or []))
    reclassified = (
        {"suite_reclassified_tests": sorted({
            *(state.get("suite_reclassified_tests") or []), *map(_which_test, broken),
        }), "suite_reclassified_causes": before + (causes if causes is not None else len(set(map(_which_test, broken))))}
        if reclassifying
        else {}
    )
    # Rewritten where they stand, then straight to the review: QA's author loop is for what cannot be placed.
    rewritten = _rewritten_in_one_call_each(state, broken, model)
    # Only a dispute's repair may answer that the test is right: a harness check measured the fault of any other.
    from app.graph import product_at_fault

    no_fault_rule = product_at_fault.offered(
        state, _root(state), [_which_test(item) for item in broken]) if reclassifying and not rewritten else []
    return _handing_on(
        **update,
        **reclassified,
        stage="acceptance_review" if rewritten else "acceptance_author",
        acceptance_return_to=return_to,
        acceptance_round=1 if rewritten else 0,
        acceptance_feedback=[] if rewritten else [*broken, REPAIR_RULE, *no_fault_rule],
        **({"revision_comments": []} if rewritten else {}),
        suite_repairs=repairs + 1,
        suite_repaired_tests=sorted({*(state.get("suite_repaired_tests") or []),
                                     *(name for item in broken for name in _which_tests(state, item))}),
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
    named = [item for item in broken] + [title for item in broken for title in _which_tests(state, item)]
    return sorted({tag for item in named for tag in tags_in(item) if tag.startswith("AC-")})


def defer_what_is_beyond_repair(state: Any, criteria: list[str], broken: list[str]) -> None:
    """Defer the criteria `beyond_repair` names, each with why; never raises.

    Measured on one run: the persistence criteria's only test was beyond
    repair, each round still raised "the acceptance suite says this does not
    work yet" for them, and the sprint was planned again three times for
    criteria no fix could prove. Deferred, the next measurement reads them as
    deferred, and the release names them among what it did not prove.
    """
    if not criteria:
        return
    try:
        from app.acceptance.junit import tags_in

        reasons = {}
        for criterion in criteria:
            why = next((item for item in broken if criterion in tags_in(item)), "")
            reasons[criterion] = (
                "its locked test cannot pass whatever is built, and the suite may not be repaired again in "
                "this run" + (f": {why[:300]}" if why else "")
            )
        suite.defer(_root(state), reasons)
        # Which tests each was judged on, as they stand: the lock keeps the deferral while they stay so.
        suite.record_judged_unpassable(_root(state), {
            criterion: [name for item in broken if criterion in tags_in(item) for name in _which_tests(state, item)]
            for criterion in criteria
        })
        logger.warning("Deferred %s: their locked tests cannot pass and may not be repaired", ", ".join(criteria))
    except Exception as error:  # noqa: BLE001 - the round goes on with them set aside, as before
        degraded("defer_beyond_repair", error)


def beyond_repair_note(broken: list[str], criteria: list[str]) -> str:
    """What a test round is told about the locked tests `beyond_repair` names."""
    return (
        f"Locked tests that cannot pass whatever is built ({', '.join(criteria)}). The suite may not be "
        "repaired again in this run, so their failures are not defects in the product and no fix "
        "stage can close them: a defect that names only these criteria is set aside.\n"
        + "\n".join(f"- {item}" for item in broken)
    )


#: `suite.repairing`'s mark for a repair that adds criterion ids to names: the tests it renames cannot be listed first.
NAMING_REPAIR = suite.NAMING_REPAIR


class _NamingFindingSwitch:
    """`NAMING_FINDING_BEFORE_DEFERRAL` as the switch registry reads one: off until measured."""

    ON_BY_DEFAULT = False
    #: What the admin page says this switch does.
    explanation = ("At release, a criterion the harness deferred and no test's name carries goes back to QA once as a "
                   "naming finding, instead of shipping deferred.")

    @staticmethod
    def enabled() -> bool:
        from app.switches import is_on

        return is_on("NAMING_FINDING_BEFORE_DEFERRAL", _NamingFindingSwitch.ON_BY_DEFAULT)


naming_finding_switch = _NamingFindingSwitch()


def _naming_findings(root: str) -> dict[str, str]:
    """{criterion: what QA is told} for each deferred criterion the harness set aside and no test's name carries, not sent yet.

    A reason QA gave stays: its lead judged that reason at the review. These are the harness's own deferrals of a
    criterion it measured as untested, where what is missing may be only an id in a name.
    """
    state = suite._state(root)  # noqa: SLF001 - the suite's own record
    sent = set(state.get("naming_findings_sent") or [])
    carried = suite.coverage(root)
    texts = {c.id: c.text for c in suite.criteria(root)}
    return {
        cid: (f"{cid} (\"{texts.get(cid, '')}\") would ship deferred because no test's name carries `{cid}`. Where a "
              f"test already checks what it says, add `{cid}` to that test's name and change nothing else; where none "
              "does, write one.")
        for cid, why in suite.deferred(root).items()
        if not carried.get(cid) and cid not in sent and str(why).startswith(suite.DEFERRED_BY_THE_HARNESS)
    }


def naming_back_to_qa(state: Any) -> dict[str, Any] | None:
    """Back to QA with each criterion deferred only for want of a test carrying its id, once each, then to the release; None when none.

    Measured on recent runs: a criterion went out as "ships deferred, unproven" while the suite's tests were right and
    only its id was missing from a name. No repair budget is charged: nothing is judged, and each is sent once. Behind
    `NAMING_FINDING_BEFORE_DEFERRAL`. Never raises.
    """
    if not naming_finding_switch.enabled():
        return None
    try:
        from app.graph.workflow import _handing_on

        root = _root(state)
        found = _naming_findings(root)
        if not found:
            return None
        record = suite._state(root)  # noqa: SLF001 - the suite's own record
        record["naming_findings_sent"] = sorted({*(record.get("naming_findings_sent") or []), *found})
        suite._save_state(root, record)  # noqa: SLF001
        suite.repairing(root, [NAMING_REPAIR])
        logger.warning("Deferred only for want of an id in a test's name: %s; back to QA", ", ".join(sorted(found)))
        return _handing_on(
            stage="acceptance_author", acceptance_return_to="release", acceptance_round=0,
            acceptance_feedback=[*found.values(), REPAIR_RULE],
        )
    except Exception:  # noqa: BLE001 - the release goes on as it would have
        logger.debug("Could not send the naming findings back to QA", exc_info=True)
        return None


# --- decision records ------------------------------------------------------------

def _decide(state: Any, update: dict[str, Any], **record: Any) -> None:
    """Add a decision record to `update` (see `app.decisions`); never raises."""
    try:
        from app.decisions import record_decision

        record_decision(state, update, **record)
    except Exception:  # noqa: BLE001 - a record is evidence, not control flow
        logger.debug("Could not record a decision", exc_info=True)
