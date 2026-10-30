"""What a run ran on: the harness version, the served model and the switches on (plan MF.1).

No run recorded the harness commit or the model the server served; the
transcript names the client class (`CompatibleChatOpenAI`), not the model. And
no run has ever run on one harness version: 8 to 17 deploys and up to 11
rewinds each, every deploy a worker restart. So each segment of a run - its
start and every resume after a restart - writes one `provenance` record, and
the run's KPIs say which commits it ran on and whether it ran on more than one
(`mixed_versions`), so a comparison can leave mixed runs out.
"""

from __future__ import annotations

import importlib
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

#: The switches group 2's items ship behind, by environment name and the module that reads it.
SWITCHES: dict[str, str] = {
    "SHARED_FACTS": "app.agents.shared_facts",
    "DECISION_LEDGER": "app.agents.ledger",
    "FIX_CYCLE": "app.graph.bounded_fixes",
    "WHERE_THINGS_STAND": "app.agents.where_things_stand",
    "STATE_AT_DISPATCH": "app.agents.where_things_stand:state_at_dispatch",
    "RELEASE_DOCS_REQUIRED": "app.stacks.release_docs",
    "RELEASE_AUDITS": "app.stacks.release_audits",
    "ASSUMPTIONS_GATE": "app.agents.assumptions",
    "CHANGE_REQUEST_RUNS": "app.server.change_request_runs",
    "SCREENSHOT_RUBRIC": "app.acceptance.screenshot_rubric",
    "VERIFY_AFTER_WRITE": "app.graph.verify_after_write",
    "DEFECT_CALL_CAP": "app.graph.defect_budget",
    "LOCALISE_FIRST": "app.graph.localisation",
    "STABLE_TOOLS": "app.agents.stable_tools",
    "CANONICAL_MEMORY": "app.agents.canonical_memory",
    "STEERING_AT_THE_TAIL": "app.plugins.steering_at_the_tail",
    "INTERFACE_CLASH_CHECK": "app.agents.interface_clashes",
    "ASK_SPECIFICATION": "app.agents.ask_specification",
    "INTERFACE_CHANGES_NAMED": "app.agents.interface_changes",
    "PROJECT_GRAPH_FIXES": "app.analysis.project_graph:fixes_switch",
    "PROJECT_GRAPH_BUILDERS": "app.analysis.project_graph:builders_switch",
    "CODE_GRAPH_TOOL": "app.analysis.project_graph:tool_switch",
    "REGRESSION_CONTRACT": "app.acceptance.regression_contract",
    "LESSON_DISTILLER": "app.plugins.lesson_distiller",
    "MUTATION_GUIDED_TESTS": "app.acceptance.mutation_guided",
    "OBSERVATION_FOLDING": "app.agents.observation_folding",
    "REPLY_SALVAGE": "app.models.reply_salvage",
    "MODEL_GUIDANCE": "app.models.model_guidance",
    "STRUCTURED_EXTRACTION": "app.agents.structured_extraction",
    "BATCH_ACCEPTANCE_AUTHOR": "app.graph.acceptance_batches",
    "RELEASE_WITH_FAILING_UNIT_TESTS": "app.graph.release_with_failing_unit_tests",
    "KEEP_THE_BEST_ATTEMPT": "app.graph.best_attempt",
    "KEEP_NET_GAINS": "app.graph.net_gain",
    "PACKAGE_EXPORTS_NAMED": "app.analysis.package_exports",
    "PACK_ENTRY_EXPORTS_KEPT": "app.stacks.entry_exports",
    "HONO_NATIVE_TEST_RUNNER": "app.stacks.packs.node_hono_native_api",
    "START_DEFECT_NAMES_COMPILER_ERRORS": "app.stacks.compiler_errors",
    "SETTLE_WHEN_ACCEPTANCE_IS_GREEN": "app.graph.settle_when_green",
    "STALL_RULE": "app.graph.stalled_sprint",
    "BUILDER_FACTS": "app.graph.builder_facts",
    "MEASURE_ONCE": "app.acceptance.measured_once",
    "KEEP_THE_BEST_ON_A_REPLAN": "app.graph.best_attempt:keep_on_a_replan_switch",
    "FIRST_REREAD_ANSWERED": "app.agents.project_memory:first_reread_switch",
    "FIX_STAGE_CALL_CAP": "app.agents.settled_answer:fix_stage_call_cap",
    "FIX_STAGE_REPLY_CAP": "app.models:fix_stage_reply_cap_switch",
    "PLAN_REVIEW_REPLY_CAP": "app.models:plan_review_reply_cap_switch",
    "SALVAGED_REPLIES_TURN_THINKING_OFF": "app.agents.settled_answer:salvaged_replies_switch",
    "TARGETED_SUITE_REPAIR": "app.acceptance.suite:targeted_repair_switch",
    "STRUCTURED_DISPUTE_VERDICT": "app.agents.suite_dispute:structured_verdict_switch",
    "AGENT_LOOP_FIX_LIMITS": "app.graph.agent_loop_fix_limits",
    "SURRENDER_TO_REWRITE": "app.graph.surrender_to_rewrite",
    "KEPT_FIX_CANDIDATES": "app.graph.kept_fix_candidates",
    "CO_DEFECT_FAILURES_IN_REWRITES": "app.graph.co_defect_failures",
    "REPEATED_REWRITE_PROMPT_STOP": "app.graph.repeated_rewrite_prompts",
    "CONTRACT_SERVER_ERRORS_AT_A_ROUND": "app.acceptance.interface_contract:server_errors_at_a_round_switch",
    "LAST_TRY_ON_DEFERRED": "app.graph.last_try_on_deferred",
    "START_PROBE": "app.acceptance.start_probe",
    "EXTENSIONS_BEFORE_A_RUN": "app.stacks.imports_before_a_run",
    "NAMING_STANDARD": "app.stacks.naming",
    "REFUSALS_FOLDED": "app.agents.refusal_folding",
    "GUIDE_ANSWER_IN_SCHEMA": "app.models.guidance:answer_in_schema_switch",
    "GUIDE_STOP_WHEN_DONE": "app.models.guidance:stop_when_done_switch",
    "GUIDE_NO_REPETITION": "app.models.guidance:no_repetition_switch",
    "GUIDE_KEEP_TO_ROLE": "app.models.guidance:keep_to_role_switch",
    "GUIDE_EXACT_ARGUMENTS": "app.models.guidance:exact_arguments_switch",
    "GUIDE_ONE_PROGRAM_A_COMMAND": "app.models.guidance:one_program_a_command_switch",
    "GUIDE_PATHS_AS_GIVEN": "app.models.guidance:paths_as_given_switch",
    "GUIDE_HEED_REFUSALS": "app.models.guidance:heed_refusals_switch",
}

UNKNOWN = "unknown"


def harness_commit() -> str:
    """The commit this worker's image was built from (`HARNESS_COMMIT`, set by the build), or "unknown"."""
    return str(os.environ.get("HARNESS_COMMIT") or "").strip() or UNKNOWN


def switch(spec: str) -> Any:
    """The object a `SWITCHES` entry names - a module, or `module:attribute` for one of several in a module."""
    module, _, attribute = spec.partition(":")
    loaded = importlib.import_module(module)
    return getattr(loaded, attribute) if attribute else loaded


def switches_on() -> list[str]:
    """The group 2 switches that are on in this process, by name."""
    on = []
    for name, module in SWITCHES.items():
        try:
            if switch(module).enabled():
                on.append(name)
        except Exception:  # noqa: BLE001 - a switch that cannot be read is not on
            continue
    return on


def the_segment(record: Any = None, profile: Any = None) -> dict[str, Any]:
    """This segment's provenance, every value a plain scalar or list. Never raises."""
    segment: dict[str, Any] = {"harness_commit": harness_commit(), "switches_on": switches_on()}
    try:
        from app.models import _runtime_settings

        settings = _runtime_settings()
        segment["model_setting"] = str(getattr(settings, "model_name", "") or "")
        segment["max_output_tokens"] = getattr(settings, "model_max_output_tokens", None)
        segment["thinking_mode"] = str(getattr(settings, "thinking_mode", "") or "")
        segment["execution_mode"] = str(getattr(settings, "execution_mode", "") or "")
    except Exception:  # noqa: BLE001 - the rest stands
        logger.debug("Could not read the settings for the provenance record", exc_info=True)
    if profile is not None:
        segment["served_model"] = str(getattr(profile, "model", "") or "")
        segment["quantisation"] = str(getattr(profile, "quantisation", "") or "")
        segment["slots"] = getattr(profile, "slots", None)
        segment["slot_context"] = getattr(profile, "slot_context", None)
    if record is not None:
        segment["delivery_mode"] = str(getattr(record, "delivery_mode", "") or "")
        segment["local_only"] = bool(getattr(record, "local_only", False))
    return segment


def record_the_segment(run_id: str, record: Any = None, profile: Any = None) -> None:
    """Write this segment's provenance into the run's transcript. Never raises."""
    try:
        from app.observability.transcript import record as transcript_record

        transcript_record(run_id, "", "provenance", **the_segment(record, profile))
    except Exception:  # noqa: BLE001 - a record must never cost the run
        logger.debug("Could not record the run's provenance", exc_info=True)


def summary(records: list[dict]) -> dict[str, Any]:
    """The run's provenance from its transcript records, as the KPI row keeps it: scalars only."""
    segments = [r for r in records if r.get("kind") == "provenance"]
    commits = list(dict.fromkeys(str(r.get("harness_commit") or UNKNOWN) for r in segments))
    # Model calls before the first segment ran on a version nothing recorded - a run begun
    # before provenance existed, or a segment that failed to write - so it is not one version.
    first = next((i for i, r in enumerate(records) if r.get("kind") == "provenance"), len(records))
    if any(r.get("kind") in ("model_request", "model_response") for r in records[:first]):
        commits = list(dict.fromkeys([UNKNOWN, *commits]))
    last = segments[-1] if segments else {}
    switches = sorted({name for r in segments for name in (r.get("switches_on") or [])})
    return {
        "harness_commits": " ".join(commits),
        "mixed_versions": len(commits) > 1,
        "served_model": str(last.get("served_model") or ""),
        "quantisation": str(last.get("quantisation") or ""),
        "switches_on": " ".join(switches),
        "segments": len(segments),
    }


__all__ = ["SWITCHES", "harness_commit", "record_the_segment", "summary", "switches_on", "the_segment"]
