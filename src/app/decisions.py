"""Decision records: every decision the run takes, who took it, and why.

A software company can say why its product is the way it is: who chose the
stack, who accepted the tests, who agreed a feature could wait. The harness
takes the same decisions - in auto mode by itself, in approval mode with the
user - and records each one the same way, so the two modes differ only in who
answers. The records travel in graph state (`decisions`), are rendered to
`docs/decision_log.md` in the workspace, and are served to the UI.
"""

from __future__ import annotations

import json

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

#: The decision points a run passes, in the order it reaches them.
POINTS = (
    "product_intake",
    "stack",
    "technical_specification",
    "scaffold",
    "acceptance_tests",
    "sprint_plan",
    "sprint",
    "escalation",
    "change_request",
    "release",
)


#: A rationale is kept whole up to this length - a diff of the suite, a defect
#: report - and only the rendered log shortens it. Callers used to cut it at
#: 1500 characters, and one run's decision log showed a suite summary where
#: the lead's own decisions had been: they came after the cut.
STORED_RATIONALE_CHARS = 20000
#: What the rendered log shows of a rationale; the rest is in `FULL_RECORDS`.
RENDERED_RATIONALE_CHARS = 2000
#: Every record, rationale whole, beside the rendered log.
FULL_RECORDS = ".harness/decisions.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_record(
    *,
    number: int,
    point: str,
    question: str,
    decision: str,
    rationale: str,
    options: list[str] | None = None,
    decided_by: str = "auto",
    comment: str = "",
    affects: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": f"DR-{number}",
        "point": point,
        "question": question,
        "options": list(options or []),
        "decision": decision,
        "rationale": str(rationale or "")[:STORED_RATIONALE_CHARS],
        "decided_by": decided_by,
        "comment": comment,
        "affects": list(affects or []),
        "decided_at": _now(),
    }


def record_decision(
    state: Any,
    update: dict[str, Any],
    *,
    point: str,
    question: str,
    decision: str,
    rationale: str,
    options: list[str] | None = None,
    decided_by: str = "auto",
    comment: str = "",
    affects: list[str] | None = None,
) -> dict[str, Any]:
    """Append one record to the decisions this update carries, and re-render the log."""
    existing = list(update.get("decisions") or state.get("decisions") or [])
    record = make_record(
        number=len(existing) + 1,
        point=point,
        question=question,
        decision=decision,
        rationale=rationale,
        options=options,
        decided_by=decided_by,
        comment=comment,
        affects=affects,
    )
    existing.append(record)
    update["decisions"] = existing
    logger.info("Decision %s at %s (%s): %s", record["id"], point, decided_by, decision)
    try:
        root = state["repository"].root_path
        from pathlib import Path

        target = Path(root) / "docs" / "decision_log.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(existing), encoding="utf-8")
        full = Path(root) / FULL_RECORDS
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001 - the record in state is the authority
        logger.debug("Could not write the decision log", exc_info=True)
    return record


def render(records: list[dict[str, Any]]) -> str:
    lines = [
        "# Decision log",
        "",
        "Every decision this run took, who took it and why. `auto` means the harness "
        "decided on its own; `user` means a person did.",
        "",
    ]
    for record in records:
        lines.append(f"## {record.get('id')}: {record.get('question')}")
        lines.append(f"- **Decision:** {record.get('decision')}")
        lines.append(f"- **Decided by:** {record.get('decided_by')}, {record.get('decided_at')}")
        if record.get("options"):
            lines.append(f"- **Options:** {'; '.join(record['options'])}")
        why = str(record.get("rationale") or "")
        if len(why) > RENDERED_RATIONALE_CHARS:
            why = (
                why[:RENDERED_RATIONALE_CHARS].rstrip()
                + f" ... (shortened here; the whole of it is {record.get('id')} in `{FULL_RECORDS}`)"
            )
        lines.append(f"- **Why:** {why}")
        if record.get("comment"):
            lines.append(f"- **Comment:** {record['comment']}")
        if record.get("affects"):
            lines.append(f"- **Affects:** {', '.join(record['affects'])}")
        lines.append("")
    return "\n".join(lines)
