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
})

#: The premium features, one switch a bundle over the base product (owner, 2026-10-29: a free base version, these
#: behind a paid one). A feature follows its bundle; its own old variable is only a test's hook.
BUNDLES: dict[str, tuple[str, ...]] = {
    # The model's reasoning and replies tuned to the model serving the run: per-model guidance, reply caps, and
    # thinking switched off where it only burns time.
    "PREMIUM_MODEL_TUNING": (
        "MODEL_GUIDANCE", "STEERING_AT_THE_TAIL", "STRUCTURED_EXTRACTION", "FIX_STAGE_REPLY_CAP",
        "PLAN_REVIEW_REPLY_CAP", "SALVAGED_REPLIES_TURN_THINKING_OFF", "GUIDE_ANSWER_IN_SCHEMA",
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

#: Features being measured, each its own switch (owner, 2026-10-29): bundled, they could not be measured apart. Off
#: until a measurement says on; on as a measured arm once one has, watched until it moves to a bundle or the base.
EXPERIMENTS = (
    "OBSERVATION_FOLDING", "BATCH_ACCEPTANCE_AUTHOR", "TARGETED_SUITE_REPAIR", "STRUCTURED_DISPUTE_VERDICT",
    # The defect fix loop (deep-review plan items 9, 11, 15).
    "AGENT_LOOP_FIX_LIMITS", "SURRENDER_TO_REWRITE", "KEPT_FIX_CANDIDATES", "CO_DEFECT_FAILURES_IN_REWRITES",
    "REPEATED_REWRITE_PROMPT_STOP",
    # Prefix stability and the second half of targeted QA repair (plan items 14 and 10).
    "STABLE_STAGE_PREFIX", "NAMED_TEST_REWRITE",
    # Tests-only writes beside a green suite and mutation findings (plan items 12 and 13).
    "TESTS_ONLY_WRITES", "MUTANT_CHECK_IN_THE_FIX_STAGE", "MUTATION_TEST_RETENTION", "EQUIVALENT_MUTANTS_REMEMBERED",
    # The interface contract at the review, the lock and the release, and naming before deferral (plan items 16, 17).
    "CONTRACT_LINE_COVERAGE", "CONTRACT_PROBE_AT_LOCK", "CONTRACT_UNREAD_LINES_AT_REVIEW", "CONTRACT_NON_NUMERIC_IDS",
    "CONTRACT_PROBE_WITH_A_RECORD", "NAMING_FINDING_BEFORE_DEFERRAL",
)
#: The experiments deployed on, each with the measurement that turned it on.
EXPERIMENTS_ON = {
    # 54 re-locks over 60 runs: 35 touched only the one or two tests sent for repair, so the full review after them
    # changed nothing; the 19 that touched more all ended at full hidden scores. On 2026-10-29, owner agreeing; the
    # mutation score is watched for a weaker suite.
    "TARGETED_SUITE_REPAIR": "re-locks that changed only the repaired tests: 35 of 54",
    # Tonight's prose reading of the dispute was wrong twice (LF.405, LF.411); on 2026-10-29 as the A/B arm, owner
    # agreeing; its disputes are compared with the prose reading's.
    "STRUCTURED_DISPUTE_VERDICT": "prose reading wrong in 2 disputes tonight; A/B against it",
    # The defect fix loop, measured as one group (owner's backlog rule, 2026-10-31): the last held-out run spent five
    # hours in one sprint on 8+ reverted fixes and the same defect re-dispatched; the off baseline is the two runs
    # before it (both at full hidden scores). Ablate one switch at a time only if the group does not help.
    "AGENT_LOOP_FIX_LIMITS": "fix-loop group arm: one sprint spent 8+ reverts and five hours",
    "SURRENDER_TO_REWRITE": "fix-loop group arm",
    "KEPT_FIX_CANDIDATES": "fix-loop group arm",
    "CO_DEFECT_FAILURES_IN_REWRITES": "fix-loop group arm",
    "REPEATED_REWRITE_PROMPT_STOP": "fix-loop group arm",
}

_BUNDLE_OF = {member: bundle for bundle, members in BUNDLES.items() for member in members}


def bundle_of(name: str) -> str:
    """The premium bundle a feature belongs to, or ""."""
    return _BUNDLE_OF.get(name, "")


def operated() -> tuple[str, ...]:
    """The switches an operator sets - the bundles and the experiments - in the order the admin page lists them."""
    return (*BUNDLES, *EXPERIMENTS)


def is_on(name: str, default: bool) -> bool:
    """Whether switch `name` is on.

    Its own admin setting or variable first (a test's hook, or a setting stored before the bundles); then a built-in
    fix is on, and a bundled feature follows its bundle's setting or variable; else `default`.
    """
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
        chosen = stored(bundle)
        if chosen is None:
            chosen = from_the_environment(bundle)
        if chosen is not None:
            return chosen
    return default


__all__ = ["BUILT_IN", "BUNDLES", "EXPERIMENTS", "EXPERIMENTS_ON", "bundle_of", "from_the_environment", "is_on", "operated", "stored"]
