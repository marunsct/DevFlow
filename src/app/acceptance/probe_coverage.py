"""Which contract lines each probe of the locked contract asked, and why it left the rest (harness review HR2.Q.9).

The three probes - a bare request that must not draw a 5xx (`server_error`), an unparsable body (`bad_body`) and a
field the criteria refuse empty (`emptied_field`) - found 3 of 1,421 gaps between them, and nothing said which lines
they had asked. Each probe now writes its coverage into `.harness/contract-probe.json`: the lines it considered, the
ones it probed, and each one it skipped or could not ask, with the reason. `loop.sh effects` reads it.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

COVERAGE_FILE = ".harness/contract-probe.json"


def coverage(
    *,
    considered: int,
    asked: Iterable[Any],
    report: Any = None,
    not_asked: Iterable[tuple[str, str]] = (),
    check_of: Any = None,
) -> dict[str, Any]:
    """One probe's coverage: lines considered, probed (a result came back), and skipped with the reason.

    `report` is the runner's report (tests with `outcome`, `name`, `message`); `check_of(test)` maps a test to the
    contract line it probed. A test skipped by the product's answer (a sign-in refused, no record made) is skipped with
    the skip's own message as its reason; a line asked with no test in the report is skipped as "no result".
    """
    asked = list(asked)
    skipped = [{"line": str(line), "reason": str(reason)} for line, reason in not_asked]
    probed: list[str] = []
    seen: set[str] = set()
    for test in getattr(report, "tests", None) or []:
        check = check_of(test) if check_of else None
        line = str(getattr(check, "line", "") or getattr(test, "name", ""))
        seen.add(line)
        if getattr(test, "outcome", "") == "skipped":
            reason = " ".join(str(getattr(test, "message", "") or "skipped by the probe").split())[:200]
            skipped.append({"line": line, "reason": reason})
        else:
            probed.append(line)
    if report is None and asked:
        skipped += [{"line": str(getattr(c, "line", c)), "reason": "the probe's runner wrote no report"} for c in asked]
    elif report is not None:
        skipped += [{"line": str(getattr(c, "line", c)), "reason": "no result"} for c in asked
                    if str(getattr(c, "line", c)) not in seen]
    return {"considered": int(considered), "asked": len(asked), "probed": len(probed), "skipped": skipped}


def write(root: Any, kind: str, record: dict[str, Any]) -> None:
    """Store `record` as the latest coverage of probe `kind`; a write that fails changes nothing about the probe."""
    try:
        path = Path(root) / COVERAGE_FILE
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            stored = {}
        stored[kind] = {"at": datetime.now(timezone.utc).isoformat(), **record}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(stored, indent=2), encoding="utf-8")
    except OSError:
        pass


def reason_a_line_is_not_probed(check: Any) -> str:
    """Why the bare-request probe does not ask a contract line."""
    kind = getattr(check, "kind", "")
    if kind == "page":
        return "page line"
    if kind == "command":
        return "command line"
    return "a route with a parameter or a write that needs a body, and the line allows no refusal"


__all__ = ["COVERAGE_FILE", "coverage", "reason_a_line_is_not_probed", "write"]
