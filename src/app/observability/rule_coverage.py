"""When a narrow rule met an input it could not read, and so did nothing (launch review LR.46).

Several checks rest on a closed reading of their input: a fixed list of user-action verbs, fields read from the words
after "with", a sign-in found by its path and spoken to with a bearer token, and test totals read from the summaries
of six runners. On the benchmark briefs and stacks each reading holds. Off them, the rule meets an input it does not
recognise and says nothing, and nothing says that it said nothing: a product whose runner prints its totals in a
form the ledger does not read is never compared against its last run, and that looks exactly like a product that
never regressed.

`could_not_apply(check, why)` writes one `rule_could_not_apply` record to the run's transcript at each such point, once
per run for each distinct input, and `lines(records)` is what the ten-minute audit prints of them. Observability
only: it changes no rule's answer. The count per check is the measure of where a rule should move behind the stack
pack interface, or be widened, first.
"""

from __future__ import annotations

import collections
import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)

#: The record kind in the transcript.
KIND = "rule_could_not_apply"

#: The checks that report here, each with the narrow reading it rests on.
ACTION_VERBS = "action_verbs"
FIELDS_GIVEN_WITH = "fields_given_with"
CONTRACT_SIGN_IN = "contract_sign_in"
RUNNER_TOTALS = "runner_totals"
CHECKS: dict[str, str] = {
    ACTION_VERBS: "user actions read from a closed list of verbs in the criteria's lists",
    FIELDS_GIVEN_WITH: "fields read from the words after 'add/create/enter ... with', answered from page controls",
    CONTRACT_SIGN_IN: "the contract probes sign in by a POST path's name and send the answer's token as a Bearer header",
    RUNNER_TOTALS: ("a test run's totals read from TAP, jest, vitest, pytest, playwright, cargo, go, Maven, .NET, RSpec "
                    "and PHPUnit summaries"),
}

#: Characters of a reason kept: enough to name the input, short enough for an audit line.
MAX_WHY = 300
#: Distinct (run, check, reason) remembered by this process, so a rule read on every check of a run records once.
_REMEMBERED = 4096
_seen: "collections.OrderedDict[tuple[str, str, str], None]" = collections.OrderedDict()


def _the_run_and_stage() -> tuple[str, str]:
    try:
        from app.models.model_pin import current_run_id
        from app.observability.transcript import _stage_from_config

        return str(current_run_id() or ""), str(_stage_from_config("") or "")
    except Exception:  # noqa: BLE001 - outside a run there is nothing to record against
        return "", ""


def could_not_apply(check: str, why: str, *, run_id: str | None = None, stage: str | None = None) -> bool:
    """Record that `check`'s narrow reading did not fit this input, and why. Never raises.

    True when a record was written; False outside a run, or when this run already has this reason for this check.
    """
    try:
        found_run, found_stage = _the_run_and_stage() if run_id is None or stage is None else ("", "")
        run = str(run_id or found_run or "")
        if not run:
            return False
        reason = " ".join(str(why or "").split())[:MAX_WHY]
        key = (run, str(check), reason)
        if key in _seen:
            return False
        _seen[key] = None
        while len(_seen) > _REMEMBERED:
            _seen.popitem(last=False)
        from app.observability.transcript import record

        record(run, stage if stage is not None else found_stage, KIND, check=str(check), why=reason)
        return True
    except Exception:  # noqa: BLE001 - a count must never fail the check it counts
        logger.debug("Could not record a rule that could not apply", exc_info=True)
        return False


def counts(records: Iterable[Any]) -> dict[str, list[str]]:
    """Check -> the distinct reasons it could not apply in these transcript records, in the order first seen."""
    found: dict[str, list[str]] = {}
    for entry in records:
        if not isinstance(entry, dict) or entry.get("kind") != KIND:
            continue
        reasons = found.setdefault(str(entry.get("check") or "?"), [])
        why = str(entry.get("why") or "")
        if why not in reasons:
            reasons.append(why)
    return found


def lines(records: Iterable[Any], examples: int = 2) -> list[str]:
    """The audit's lines: one summary of the counts per check, then a few of each check's reasons; [] with none."""
    found = counts(records)
    if not found:
        return []
    ordered = sorted(found.items(), key=lambda item: (-len(item[1]), item[0]))
    out = ["rules that could not apply (distinct inputs): "
           + ", ".join(f"{check} {len(reasons)}" for check, reasons in ordered)]
    for check, reasons in ordered:
        for why in reasons[:examples]:
            out.append(f"  {check}: {why[:160]}")
    return out


__all__ = ["ACTION_VERBS", "CHECKS", "CONTRACT_SIGN_IN", "FIELDS_GIVEN_WITH", "KIND", "RUNNER_TOTALS",
           "could_not_apply", "counts", "lines"]
