"""On/off switches for features measured before they are trusted (plans MF.4, MF.5).

A feature behind a switch ships off: its module's `ON_BY_DEFAULT` says so, and
the environment variable of the switch's name - `on`/`off` - overrides it for
a Measure arm. `observability.provenance.SWITCHES` lists every switch, so each
run's KPI row says which were on.

An administrator can set a switch on the admin page (`/admin`). That setting is
stored with the other runtime settings and beats the environment, in every
process, within the settings cache's few seconds. A switch nobody set follows
the environment as before. Processes read the stored settings only when
`SWITCH_OVERRIDES_FROM_SETTINGS` is on (the compose file turns it on), so a
test or a script outside the services never queries a database for a switch.
"""

from __future__ import annotations

import os

_ON = ("1", "on", "true", "yes")
_OFF = ("0", "off", "false", "no")


def stored(name: str) -> bool | None:
    """The admin page's setting for switch `name`, or None when it has none or settings are not read here."""
    if str(os.environ.get("SWITCH_OVERRIDES_FROM_SETTINGS") or "").strip().lower() not in _ON:
        return None
    try:
        from app.server.runtime_settings import switch_overrides

        return switch_overrides().get(name)
    except Exception:  # noqa: BLE001 - the environment decides when the settings cannot be read
        return None


#: How long a run's own switch settings are trusted before they are read again.
RUN_OVERRIDES_TTL_SECONDS = 30.0
_RUN_OVERRIDES: dict[str, tuple[float, dict[str, bool]]] = {}


def for_the_run(name: str) -> bool | None:
    """The current run's own setting for switch `name`, or None (harness review HR2.E.1).

    Set when the run is started (`loop.sh bench --off NAME`), so two runs on one harness version can be the two arms
    of a measurement with no deploy between them. Read from the run's record by the run this call belongs to - the
    graph's config or the worker task, never the environment - so one run's setting cannot reach another's thread.
    Only where stored settings are read (`SWITCH_OVERRIDES_FROM_SETTINGS`), like the admin page's.
    """
    if str(os.environ.get("SWITCH_OVERRIDES_FROM_SETTINGS") or "").strip().lower() not in _ON:
        return None
    try:
        import time

        from app.models.model_pin import current_run_id

        run = current_run_id()
        if not run:
            return None
        now = time.monotonic()
        hit = _RUN_OVERRIDES.get(run)
        if hit is None or now - hit[0] >= RUN_OVERRIDES_TTL_SECONDS:
            from app.server.run_store import RunStore

            try:
                found = RunStore.shared().switch_overrides(run)
            except Exception:  # noqa: BLE001 - the last known settings, else none
                found = hit[1] if hit is not None else {}
            # A run with none is read again soon: its settings are stored just after it is created, and its first
            # stage must not keep an empty read for the whole TTL.
            hit = (now if found else now - RUN_OVERRIDES_TTL_SECONDS + 2.0, found)
            _RUN_OVERRIDES[run] = hit
        return hit[1].get(name)
    except Exception:  # noqa: BLE001 - the other settings decide when the run's cannot be read
        return None


def from_the_environment(name: str) -> bool | None:
    """The switch's environment variable as on (True) or off (False), or None when unset or not on/off."""
    value = str(os.environ.get(name) or "").strip().lower()
    if value in _ON:
        return True
    if value in _OFF:
        return False
    return None


#: Fixes for faults the runs demonstrated, and savings that change no outcome: part of the base product, always on
#: (owner, 2026-10-29: "if it was a bug then it is fixed, no switch for bugs"). Not deployed, listed or recorded as
#: switches; a test may still set the old name's variable to check the code path it replaced.
BUILT_IN = frozenset({
    "FIX_CYCLE", "VERIFY_AFTER_WRITE", "DEFECT_CALL_CAP", "LOCALISE_FIRST", "STABLE_TOOLS", "INTERFACE_CLASH_CHECK",
    "INTERFACE_CHANGES_NAMED", "REPLY_SALVAGE", "RELEASE_WITH_FAILING_UNIT_TESTS", "KEEP_THE_BEST_ATTEMPT",
    "KEEP_NET_GAINS", "PACKAGE_EXPORTS_NAMED", "PACK_ENTRY_EXPORTS_KEPT", "HONO_NATIVE_TEST_RUNNER",
    "START_DEFECT_NAMES_COMPILER_ERRORS", "SETTLE_WHEN_ACCEPTANCE_IS_GREEN", "STALL_RULE", "MEASURE_ONCE",
    "KEEP_THE_BEST_ON_A_REPLAN", "FIRST_REREAD_ANSWERED", "FIX_STAGE_CALL_CAP", "CONTRACT_SERVER_ERRORS_AT_A_ROUND",
    "LAST_TRY_ON_DEFERRED", "START_PROBE", "EXTENSIONS_BEFORE_A_RUN", "REFUSALS_FOLDED",
    # A security fix (deep review 2026-11-18, E2): an install fetches no invented or days-old package.
    "DEPENDENCY_GATE",
    # Measured and kept: they change what a run proves or how it repairs, so they are quality, not options (owner,
    # 2026-11-05: bug fixes and changes that affect quality are always on, with no switch).
    "TARGETED_SUITE_REPAIR",
    "STRUCTURED_DISPUTE_VERDICT",
    "AGENT_LOOP_FIX_LIMITS",
    "SURRENDER_TO_REWRITE",
    "KEPT_FIX_CANDIDATES",
    "CO_DEFECT_FAILURES_IN_REWRITES",
    "REPEATED_REWRITE_PROMPT_STOP",
    "QA_SAYS_THE_PRODUCT_IS_AT_FAULT",
    "UNIT_TESTS_YIELD_TO_THE_LOCKED_SUITE",
    "SETTLE_SPEC_CONTRADICTIONS",
    "BRIEF_OVER_SPEC_ADDITIONS",
    "TESTS_OF_ACTIONS_WITHIN_A_VIEW",
    # A right ruling in the judge's own words is held to its test's criterion: on 11-13 three rulings on a name signed up
    # in 40 calls, and one on a lookup by text of only spaces (a false acceptance followed), were refused without it.
    # Measured so far: hidden 1.00 on (2 runs), 0.94 off (4); watch its minutes.
    "DISPUTE_QUOTES_THE_CRITERION",
    # The "Being measured" batch (LR.65, launch review, 2026-11-16): on in every run since release candidate 7 and
    # through the measurement runs of 11-16 (eight of nine full on hidden tests, every loss warned of); they check what a
    # suite proves, so they are quality and keep no switch.
    "NAMED_TEST_REWRITE",
    "TESTS_ONLY_WRITES",
    "MUTATION_TEST_RETENTION",
    "CONTRACT_LINE_COVERAGE",
    "CONTRACT_PROBE_AT_LOCK",
    "CONTRACT_UNREAD_LINES_AT_REVIEW",
    "CONTRACT_NON_NUMERIC_IDS",
    "CONTRACT_PROBE_WITH_A_RECORD",
    "CONTRACT_PROBE_WITH_A_BAD_BODY",
    "NAMING_FINDING_BEFORE_DEFERRAL",
    "SPEC_DRY_RUN",
    "ORDER_PROBE",
    "IDS_READ_WITHOUT_A_CREATE",
})

#: The premium features, one switch a bundle over the base product (owner, 2026-10-29: a free base version, these
#: behind a paid one). A feature follows its bundle; its own old variable is only a test's hook.
BUNDLES: dict[str, tuple[str, ...]] = {
    # The model's reasoning and replies tuned to the model serving the run: per-model guidance, reply caps, and
    # thinking switched off where it only burns time.
    "PREMIUM_MODEL_TUNING": (
        "MODEL_GUIDANCE", "STEERING_AT_THE_TAIL", "STRUCTURED_EXTRACTION", "FIX_STAGE_REPLY_CAP",
        "PLAN_REVIEW_REPLY_CAP", "SALVAGED_REPLIES_TURN_THINKING_OFF", "SALVAGED_PLANNING_THINKING_OFF", "THINKING_OFF_REPLY_CAP",
        "GUIDE_ANSWER_IN_SCHEMA",
        "GUIDE_STOP_WHEN_DONE", "GUIDE_NO_REPETITION", "GUIDE_KEEP_TO_ROLE", "GUIDE_EXACT_ARGUMENTS",
        "GUIDE_ONE_PROGRAM_A_COMMAND", "GUIDE_PATHS_AS_GIVEN", "GUIDE_HEED_REFUSALS",
    ),
    # What every stage knows of the project: shared facts, memory, the code graph, lessons from earlier runs.
    "PREMIUM_PROJECT_INTELLIGENCE": (
        "SHARED_FACTS", "CANONICAL_MEMORY", "WHERE_THINGS_STAND", "STATE_AT_DISPATCH", "PROJECT_GRAPH_FIXES",
        "PROJECT_GRAPH_BUILDERS", "CODE_GRAPH_TOOL", "BUILDER_FACTS", "LESSON_DISTILLER", "DECISION_LEDGER",
        "NAMING_STANDARD",
    ),
    # Verification beyond the acceptance suite: mutation-guided tests, the regression contract, page scoring,
    # release audits and documents, and the specification's assumptions asked before building.
    "PREMIUM_DEEP_VERIFICATION": (
        "MUTATION_GUIDED_TESTS", "REGRESSION_CONTRACT", "SCREENSHOT_RUBRIC", "RELEASE_AUDITS", "RELEASE_DOCS_REQUIRED",
        "ASSUMPTIONS_GATE", "ASK_SPECIFICATION",
    ),
    # Follow-up runs that change a finished product on request.
    "PREMIUM_CHANGE_REQUESTS": ("CHANGE_REQUEST_RUNS",),
}

#: The switches an operator may set beside the bundles, each in a group that says what it is for (owner, 2026-11-05:
#: only improvements that do not affect quality have a switch, and switches are grouped). "Being measured" holds
#: verification checks built and tested but never measured in a run: on together as one measured batch from release
#: candidate 7; each that holds moves to `BUILT_IN`, each that hurts is reworked or removed - none keeps its switch.
GROUPS: dict[str, tuple[str, ...]] = {
    # How much of a long conversation a model is sent: cost and cache, not what the run proves.
    "Context and cost": ("OBSERVATION_FOLDING", "STABLE_STAGE_PREFIX", "BATCH_ACCEPTANCE_AUTHOR",
                         "REASONING_KEPT_AFTER_AN_ANSWER", "LEAN_TOOL_LISTS", "SLICED_MEMORY",
                         "LEAN_PROMPTS_FOR_STRONG_MODELS"),
    # Fewer calls on mutation findings: time, not what the run proves.
    "Efficiency": ("EQUIVALENT_MUTANTS_REMEMBERED", "MUTANT_CHECK_IN_THE_FIX_STAGE", "REVIEWS_WITHOUT_REASONING",
                   "HARNESS_FINDINGS_RECHECKED", "NEAR_GREEN_REPLANNED_ONCE", "STABLE_MEMORY_ORDER",
                   "NEAR_GREEN_REPAIR_TO_ROUND", "FIX_STAGES_THAT_CLOSE_NOTHING", "ONE_DESIGN_REVIEW",
                   "SPRINT_TIME_BUDGET", "MUTATION_GAPS_BUNDLED"),
    # What a stack's setup stage may write (docs/measuring.md M6): measured off and on before it is kept.
    "Setup scope": ("SETUP_SCOPE_GUARD",),
    # Which review findings may send a sprint back (docs/measuring.md M7).
    "Review gates": ("MILESTONE_EVIDENCE_GATE", "DESIGN_REVISION_CROSS_CHECKED", "INTAKE_ASKS_FIRST"),
    # Contract probes the release adds to a green round: what a product must survive that no locked test asks.
    "Contract probes": ("CONCURRENT_WRITE_PROBE", "WRONG_SHAPE_BODY_PROBE", "EDGE_PROBE", "PAGE_PROBE"),
    # Which of the product's own unit tests may hold a run: one that keeps failing beside a green suite is set aside.
    "Unit test signal": ("UNIT_TEST_QUARANTINE",),
    # The order the product's files are first written in: what each is shown of the files it depends on.
    "Drafting order": ("DRAFTING_IN_WAVES",),
    # How a cause the fixes keep missing is worked: one diagnosis call before its third fix (deep review 1.4).
    "Recurring causes": ("DIAGNOSE_A_RECURRING_CAUSE",),
    # A stuck fixer is shown what others found for its error, looked up by the harness (plan WL.4): off until measured.
    # The web tools offered to the stages that read documentation (plan WL.3). Each run's "Internet lookups" choice
    # sets both for that run (`app.internet_lookups`).
    "Internet lookups": ("WEB_LOOKUP_WHEN_STUCK", "WEB_TOOLS_OFFERED"),
}
#: Every grouped switch, in the admin page's order.
EXPERIMENTS = tuple(name for members in GROUPS.values() for name in members)
#: The grouped switches deployed on, each with why.
#: Measured switches taken off for what they cost. Empty: `TESTS_ONLY_WRITES` was taken off on a second costly case
#: (one first fix attempt, about 4.5 minutes) and put back the same day on what it saves: of the runs scored that day,
#: 9 with it on shipped no failing unit test, and 3 of the 8 with it off shipped 2, 10 and 10 (quality before cost,
#: owner 2026-11-05). Its cost stays bounded: it covers only the first attempt at a failing unit test.
TAKEN_OFF_FOR_COST: frozenset[str] = frozenset()
EXPERIMENTS_ON: dict[str, str] = {
    "NEAR_GREEN_REPLANNED_ONCE": "measured over 175 past re-plans (LR.53): later re-plans of a near-green sprint beat the "
                                 "best in 4 of 27 cases at about 34 minutes each, 21 of 22 such runs scored every hidden "
                                 "test; on, and kept only if live runs lose no hidden test by it (docs/measuring.md M14)",
    "OBSERVATION_FOLDING": "owner 11-17: built switches go on, measured against the scored runs before them; off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
    "STABLE_STAGE_PREFIX": "owner 11-17: built switches go on, measured against the scored runs before them; off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
    "REASONING_KEPT_AFTER_AN_ANSWER": "owner 11-17: built switches go on, measured against the scored runs before them; off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
    "EQUIVALENT_MUTANTS_REMEMBERED": "owner 11-17: built switches go on, measured against the scored runs before them; off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
    "MUTANT_CHECK_IN_THE_FIX_STAGE": "owner 11-17: built switches go on, measured against the scored runs before them; off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
    "REVIEWS_WITHOUT_REASONING": "owner 11-17: built switches go on, measured against the scored runs before them; off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
    "HARNESS_FINDINGS_RECHECKED": "owner 11-17: built switches go on, measured against the scored runs before them; off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
    "SETUP_SCOPE_GUARD": "owner 11-17: built switches go on, measured against the scored runs before them; off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
    "MILESTONE_EVIDENCE_GATE": "owner 11-17: built switches go on, measured against the scored runs before them; off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
    "DESIGN_REVISION_CROSS_CHECKED": "owner 11-17: built switches go on, measured against the scored runs before them; off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
    "STABLE_MEMORY_ORDER": "owner 11-17: built switches go on, measured against the scored runs before them; off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
    "NEAR_GREEN_REPAIR_TO_ROUND": "owner 11-17: built switches go on, measured against the scored runs before them; off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
    "FIX_STAGES_THAT_CLOSE_NOTHING": "owner 11-17: built switches go on, measured against the scored runs before them; off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
    "CONCURRENT_WRITE_PROBE": "owner 11-17: built switches go on, measured against the scored runs before them; off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
    "WRONG_SHAPE_BODY_PROBE": "owner 11-17: built switches go on, measured against the scored runs before them; off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
    "UNIT_TEST_QUARANTINE": "deep review 11-18 (B6): built switches go on, measured against the scored runs before them; off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
    "PAGE_PROBE": "deep review 11-18 (B5): built switches go on, measured against the scored runs before them; off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
    "EDGE_PROBE": "deep review 11-18 (B1): built switches go on, measured against the scored runs before them; off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
    "ONE_DESIGN_REVIEW": "owner 11-17: built switches go on, measured against the scored runs before them; off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
    "SPRINT_TIME_BUDGET": "owner 11-17: built switches go on, measured against the scored runs before them; off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
    "LEAN_TOOL_LISTS": "deep review 2026-11-18 (C5): five tools never or almost never called in about 3,500 offers each over 30 runs; on, and off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
    "SLICED_MEMORY": "deep review 2026-11-18 (C3): fixers averaged 164k characters a request and builders 269k, most of it project memory; on, and off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
    "LEAN_PROMPTS_FOR_STRONG_MODELS": "deep review 2026-11-18 (C7): acts only for a model the diagnosis measured strong, which the local models are not; on, and off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
    "DRAFTING_IN_WAVES": "deep review 2026-11-18 (1.6): files drafted side by side, blind to each other, disagreed on shared state and declared one interface twice; on, and off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
    "DIAGNOSE_A_RECURRING_CAUSE": "deep review 2026-11-18 (1.4): the fix rate fell from 29% at a first attempt to 22% and 11%, and one run was planned again three times with the same change; on, and off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
    "INTAKE_ASKS_FIRST": "deep review 2026-11-18 (C8): an earlier audit traced all four false acceptances it found to an intake or a specification that overrode the brief; on, and off at once if a run it fires in loses a hidden test or takes 1.5x its family's 5-run active minutes (docs/measuring.md M15)",
}
_GROUP_OF = {name: group for group, members in GROUPS.items() for name in members}


def group_of(name: str) -> str:
    """What a switch is for: "Bundles" for a premium bundle, else its group's name; "" for none."""
    return "Bundles" if name in BUNDLES else _GROUP_OF.get(name, "")


_BUNDLE_OF = {member: bundle for bundle, members in BUNDLES.items() for member in members}


def bundle_of(name: str) -> str:
    """The premium bundle a feature belongs to, or ""."""
    return _BUNDLE_OF.get(name, "")


def operated() -> tuple[str, ...]:
    """The switches an operator sets - the bundles and the experiments - in the order the admin page lists them."""
    return (*BUNDLES, *EXPERIMENTS)


_SAID_OFF: set[str] = set()


def _built_in(name: str) -> bool:
    """A built-in fix is on; only its variable set off on the host (a test's hook, or an operator's deliberate lever)
    turns it off, and that is logged once.

    Found in the launch review: a stored admin setting or a run's setting from before the fix was built in turned a
    bug fix off with no trace in the run's record. Those are no longer read for a built-in fix.
    """
    environment = from_the_environment(name)
    if environment is False and name not in _SAID_OFF:
        _SAID_OFF.add(name)
        import logging

        logging.getLogger(__name__).warning("Built-in fix %s is off: its variable is set off on this host", name)
    return True if environment is None else environment


def is_on(name: str, default: bool) -> bool:
    """Whether switch `name` is on.

    The run's own setting first (HR2.E.1), then its own admin setting or variable (a test's hook, or a setting stored before the bundles); then a built-in
    fix is on, and a bundled feature follows its bundle's setting or variable; else `default`.
    """
    if name in BUILT_IN:
        return _built_in(name)
    run = for_the_run(name)
    if run is not None:
        return run
    setting = stored(name)
    if setting is not None:
        return setting
    environment = from_the_environment(name)
    if environment is not None:
        return environment
    if name in BUILT_IN:
        return True
    bundle = bundle_of(name)
    if bundle:
        chosen = for_the_run(bundle)
        if chosen is None:
            chosen = stored(bundle)
        if chosen is None:
            chosen = from_the_environment(bundle)
        if chosen is not None:
            return chosen
    return default


__all__ = ["BUILT_IN", "BUNDLES", "EXPERIMENTS", "EXPERIMENTS_ON", "GROUPS", "bundle_of", "for_the_run", "group_of", "from_the_environment", "is_on", "operated", "stored"]
