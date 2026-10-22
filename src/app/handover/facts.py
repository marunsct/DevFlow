"""One model of what a run recorded, for the documents written from it (plan DT.1).

Every number and name a handover document states comes from here, and here
only reads what the harness already recorded in the workspace: the stack
contract, the locked criteria and their last measurement, the unit tests'
report, the interface contract, the decisions, the commit. Nothing is asked of
a model, and nothing is written - it is assembled on demand for a finished
run, so a run's own behaviour is untouched.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _quietly(what: str, read: Any, default: Any) -> Any:
    try:
        return read()
    except Exception:  # noqa: BLE001 - a fact that cannot be read is left out, never invented
        logger.debug("Could not read %s for the handover facts", what, exc_info=True)
        return default


def _unit_tests(root: Path, record: dict[str, Any]) -> list[dict[str, Any]]:
    from app.acceptance import junit

    report = str(record.get("unit_report") or "")
    if not report:
        return []
    found = junit.read(root / str(record.get("project") or "") / report)
    return [{"name": t.name, "file": t.file or t.suite, "outcome": t.outcome, "seconds": round(t.seconds or 0.0, 3),
             "message": (t.message or "").strip()[:600]} for t in found.tests]


def document_facts(repo_root: str | Path, *, run_id: str = "", completion_gaps: list[str] | None = None) -> dict[str, Any]:
    """The run's recorded facts as one dict; a part the workspace does not hold is empty. Never raises."""
    from app import ci
    from app.acceptance import interface_contract, suite
    from app.stacks import contract

    root = Path(repo_root)
    record = _quietly("the stack contract", lambda: contract.read(root) or {}, {})
    measured = _quietly("the suite's last result", lambda: suite.last_result(root) or {}, {})
    criteria_text = {c.id: c.text for c in _quietly("the criteria", lambda: suite.criteria(root), [])}
    deferred = _quietly("the deferrals", lambda: suite.deferred(root), {})
    contract_lines: dict[str, list[str]] = {}
    for check in _quietly("the interface contract", lambda: interface_contract.the_locked_contract(root), []):
        contract_lines.setdefault(check.criterion, []).append(check.line)
    criteria = []
    for cid, entry in (measured.get("criteria") or {}).items():
        criteria.append({
            "id": cid,
            "text": (entry or {}).get("text") or criteria_text.get(cid, ""),
            "status": (entry or {}).get("status") or "untested",
            "tests": [dict(t) for t in (entry or {}).get("tests") or []],
            "contract": contract_lines.get(cid, []),
            "deferred": deferred.get(cid, ""),
        })
    for cid, text in criteria_text.items():
        if cid not in {c["id"] for c in criteria}:
            criteria.append({"id": cid, "text": text, "status": "untested", "tests": [],
                             "contract": contract_lines.get(cid, []), "deferred": deferred.get(cid, "")})
    criteria.sort(key=lambda c: int(c["id"].split("-")[-1]) if c["id"].split("-")[-1].isdigit() else 0)
    decisions = _quietly("the decisions", lambda: json.loads((root / ".harness" / "decisions.json").read_text(encoding="utf-8")), [])
    return {
        "run_id": run_id,
        "product": str(record.get("title") or record.get("project") or ""),
        "project": str(record.get("project") or ""),
        "pack": str(record.get("pack") or ""),
        "commit": _quietly("the commit", lambda: ci.head(root), ""),
        "unit_command": " ".join(map(str, record.get("unit_test") or [])),
        "acceptance_command": str(measured.get("command") or " ".join(map(str, record.get("acceptance_test") or []))),
        "acceptance": {"passed": int(measured.get("passed") or 0), "failed": int(measured.get("failed") or 0),
                       "skipped": int(measured.get("skipped") or 0), "ran": bool(measured.get("ran"))},
        "criteria": criteria,
        "unit_tests": _quietly("the unit tests", lambda: _unit_tests(root, record), []),
        "decisions": [{"id": d.get("id"), "point": d.get("point"), "question": d.get("question"),
                       "decision": d.get("decision"), "decided_by": d.get("decided_by")}
                      for d in decisions if isinstance(d, dict)],
        "completion_gaps": list(completion_gaps or []),
    }


__all__ = ["document_facts"]
