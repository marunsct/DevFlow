"""The Sprint Record: what a sprint planned, did, found, fixed and left open.

A software team closes a sprint with a record a newcomer can read: the backlog
and what became of each item, every defect with its cause and fix, what the
reviews raised and what was done about it, what is carried into the next
sprint, and what the team learned. This workflow's sprint summary carried the
headline numbers and a list of task descriptions - one run's "Features
Implemented" read "Review existing unit tests ..." - and review findings below
the gating severity were never written down: `sprint_advance_node` cleared the
review comments and the next sprint started without them.

Everything here is assembled from what the workflow and the harness recorded,
not from a model's account of itself, so the record cannot overstate:

- `work_order_outcomes` - each delegated task against the specialist output it
  produced, with the files it changed and the commands it ran
- `defect_log` - every tracked defect with reproduction, fix and the command
  the execution ledger confirms verified it
- `findings_of` / `with_dispositions` - every review finding of every round,
  and what became of it
- `carried_from` - the findings that did not block and were not fixed, handed
  to the next sprint's technical lead, who must take or decline each one
- `lessons_from` - the harness's own record of what failed repeatedly in this
  sprint, handed to the next lead and written into the record

Nothing here names a language, a framework or a kind of product.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any, Iterable, Mapping, Sequence

#: Severities that block a milestone - the same set the workflow gates on.
GATING = frozenset({"blocking", "major", "critical", "high"})

#: How many lessons one sprint hands on. Past a handful they stop being read.
MAX_LESSONS = 6


def _flat(text: Any) -> str:
    return " ".join(str(text or "").split())


def findings_of(review: Any, source: str, round_number: int) -> list[dict[str, Any]]:
    """One review's findings as records of the Sprint Record. Never raises."""
    out: list[dict[str, Any]] = []
    for finding in list(getattr(review, "findings", None) or []):
        severity = _flat(getattr(finding, "severity", "")).lower() or "unrated"
        remediation = _flat(
            getattr(finding, "required_remediation", "") or getattr(finding, "remediation", "")
        )
        out.append({
            "round": round_number,
            "source": source,
            "severity": severity,
            "description": _flat(getattr(finding, "description", "")),
            "remediation": remediation,
            "gating": severity in GATING,
        })
    return out


def with_dispositions(
    findings: Sequence[Mapping[str, Any]], *, completed: bool, more_sprints: bool
) -> list[dict[str, Any]]:
    """Each finding with what became of it, decided by where it sits in the sprint.

    A finding that blocked a round which was later accepted was fixed in a
    revision - the review that accepted the sprint had it in front of it as
    "what you said last time". One that did not block, from the last round of
    an accepted sprint, was neither fixed nor forgotten: it is carried forward,
    or listed as a known issue when no sprint follows. In a sprint that did not
    pass, everything from its last round is still open.
    """
    if not findings:
        return []
    last = max(int(f.get("round", 0) or 0) for f in findings)
    out: list[dict[str, Any]] = []
    for finding in findings:
        final_round = int(finding.get("round", 0) or 0) == last
        if not completed:
            disposition = "open - the sprint did not pass" if final_round else "sent back for revision"
        elif not final_round:
            disposition = "fixed in a revision" if finding.get("gating") else "superseded by a later review"
        elif finding.get("gating"):
            disposition = "open"
        else:
            disposition = "carried to the next sprint" if more_sprints else "known issue at release"
        out.append({**finding, "disposition": disposition})
    return out


def carried_from(
    findings: Sequence[Mapping[str, Any]], sprint_number: int
) -> list[str]:
    """The findings the next sprint's lead must take or decline, as one line each."""
    if not findings:
        return []
    last = max(int(f.get("round", 0) or 0) for f in findings)
    lines: list[str] = []
    seen: set[str] = set()
    for finding in findings:
        if int(finding.get("round", 0) or 0) != last or finding.get("gating"):
            continue
        description = _flat(finding.get("description"))
        if not description or description.lower() in seen:
            continue
        seen.add(description.lower())
        remediation = _flat(finding.get("remediation"))
        lines.append(
            f"{description} (sprint {sprint_number} {finding.get('source', 'review')} review, "
            f"{finding.get('severity', 'unrated')})" + (f" - suggested: {remediation}" if remediation else "")
        )
    return lines


def _stage_index(stage_name: str) -> int | None:
    match = re.search(r"_(\d+)$", stage_name or "")
    return int(match.group(1)) if match else None


def work_order_outcomes(plan: Any, outputs: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Each delegated task against what its specialist actually returned."""
    tasks = list(getattr(plan, "delegated_tasks", None) or [])
    by_index: dict[int, Any] = {}
    for stage, output in (outputs or {}).items():
        index = _stage_index(str(stage))
        if index is not None:
            by_index[index] = output
    rows: list[dict[str, Any]] = []
    for index, task in enumerate(tasks):
        output = by_index.get(index)
        title = _flat(getattr(task, "title", "")) or _flat(
            next((line for line in str(getattr(task, "task_description", "")).splitlines() if line.strip()), "")
        )[:120] or "Untitled task"
        blockers = [_flat(b) for b in getattr(output, "blockers", None) or [] if _flat(b)]
        verification = [
            f"{' '.join(str(p) for p in getattr(run, 'command', []) or [])} (exit {getattr(run, 'exit_code', '?')})"
            for run in getattr(output, "verification", None) or []
        ]
        if output is None:
            outcome = "not run"
        elif blockers:
            outcome = "returned with blockers"
        else:
            outcome = "delivered"
        rows.append({
            "title": title,
            "role": str(getattr(task, "specialist_role", "") or "unassigned"),
            "outcome": outcome,
            "files_planned": [str(f) for f in getattr(task, "files", None) or []],
            "files_changed": [str(f) for f in getattr(output, "changed_files", None) or []],
            "verification": verification,
            "blockers": blockers,
        })
    return rows


def defect_log(cycle: Any) -> list[dict[str, Any]]:
    """Every tracked defect, numbered, with how it was fixed and what proved it."""
    rows: list[dict[str, Any]] = []
    for number, defect in enumerate(list(getattr(cycle, "defects", None) or []), 1):
        status = str(getattr(defect, "status", "open") or "open")
        verified = _flat(getattr(defect, "verified_by", ""))
        if status == "fixed":
            state = "fixed, verified" if verified else "fixed, unverified"
        elif status == "accepted_risk":
            state = "accepted risk"
        else:
            state = "open"
        rows.append({
            "id": f"D{number}",
            "severity": _flat(getattr(defect, "severity", "")) or "unrated",
            "state": state,
            "description": _flat(getattr(defect, "description", "")),
            "owner": _flat(getattr(defect, "owner", "")),
            "reproduction": _flat(getattr(defect, "reproduction_steps", "")),
            "expected": _flat(getattr(defect, "expected_behavior", "")),
            "actual": _flat(getattr(defect, "actual_behavior", "")),
            "files": [str(f) for f in getattr(defect, "affected_files", None) or []],
            "verified_by": verified,
            "regression_test": _flat(getattr(defect, "regression_test", "")),
            "resolution": _flat(getattr(defect, "resolution", "")),
        })
    return rows


def _error_of(content: Any) -> str:
    """The error a tool result reported, or "" if it reported none."""
    text = str(content or "").strip()
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict) and parsed.get("error"):
            return _flat(parsed["error"])
        return ""
    if text.startswith("Error"):
        return _flat(text)
    return ""


def _gist(error: str) -> str:
    """The first sentence of an error, with the names in it generalised."""
    first = re.split(r"(?<=[.!?])\s", error, maxsplit=1)[0]
    first = re.sub(r"'[^']{1,120}'", "'…'", first)
    return first[:160]


def lessons_from(entries: Iterable[Mapping[str, Any]], *, since: str | None = None) -> list[str]:
    """What failed more than once in this sprint, from the transcript's tool results.

    Grouped by tool and the first sentence of the error, with quoted names
    generalised so one mistake repeated on three files counts as one lesson.
    A mistake made once is noise; one made repeatedly is what the next
    sprint's work orders should design around.
    """
    calls: dict[str, str] = {}
    counts: Counter[tuple[str, str]] = Counter()
    for entry in entries or ():
        at = str(entry.get("at") or "")
        if since and at and at < since:
            continue
        kind = entry.get("kind")
        call_id = str(entry.get("call_id") or "")
        if kind == "tool_call":
            calls[call_id] = str(entry.get("tool") or "")
            continue
        if kind != "tool_result":
            continue
        error = _error_of(entry.get("content"))
        if not error:
            continue
        tool = str(entry.get("tool") or calls.get(call_id) or "a tool")
        counts[(tool, _gist(error))] += 1
    lessons = [
        f"`{tool}` failed {count} times: {gist}"
        for (tool, gist), count in counts.most_common()
        if count >= 2
    ]
    return lessons[:MAX_LESSONS]




def definition_of_done_gaps(plan: Any, outputs: Mapping[str, Any] | None, cycle: Any) -> list[str]:
    """What stops an accepted sprint from counting as done, or [] when nothing does.

    The milestone review accepts the work; this is the part of "done" that needs
    no judgement. Every work order has a result from the specialist it was given
    to, and no tracked defect is still open. A sprint missing either is not
    finished, however the review read it, and the next sprint must not start on
    top of it.
    """
    gaps: list[str] = []
    for number, row in enumerate(work_order_outcomes(plan, outputs), 1):
        if row["outcome"] == "not run":
            gaps.append(
                f"Work order {number} ({row['role']}: {row['title']}) has no result: the "
                "specialist it was given to never returned one."
            )
    for defect in defect_log(cycle):
        if defect["state"] == "open":
            gaps.append(f"Defect {defect['id']} is still open: {defect['description']}")
    return gaps


#: How many earlier fixes one request lists, the latest kept.
MAX_FIXES_TO_KEEP = 10


def _the_same_file(one: str, other: str) -> bool:
    """Whether two workspace paths name one file, however much of the path each gives."""
    a, b = str(one).strip().lstrip("./").lstrip("/"), str(other).strip().lstrip("./").lstrip("/")
    return bool(a and b) and (a == b or a.endswith("/" + b) or b.endswith("/" + a))


def fixes_to_keep(
    attempts: Iterable[Mapping[str, Any]], *, files: Sequence[str] = (), role: str = ""
) -> list[str]:
    """Each defect an earlier attempt fixed, as one line - for `files` or `role` when given.

    A defect that names files is kept for a request whose files include one of
    them; one that names none, for a request of the role that owned it. With
    neither given, every fixed defect is kept.

    Measured on one run: sprint 1 darkened three colours the specification gave
    for contrast. Sprint 3's restyle wrote one of them back, and sprint 4's work
    order - "fix all responsive and styling issues in styles.css to match the
    technical specification" - wrote all three back. Each time four checks raised
    the same failures again and fixers made the same changes again; nothing told
    the builders the specification's values had been found wanting.
    """
    lines: list[str] = []
    seen: set[str] = set()
    for attempt in attempts or ():
        for row in attempt.get("defect_log") or ():
            if not str(row.get("state") or "").startswith("fixed"):
                continue
            named = [str(f) for f in row.get("files") or [] if str(f).strip()]
            if files or role:
                if named:
                    if not any(_the_same_file(mine, theirs) for mine in files or () for theirs in named):
                        continue
                elif not role or str(row.get("owner") or "") != role:
                    continue
            description = " ".join(str(row.get("description") or "").split())[:220]
            if not description or description.lower() in seen:
                continue
            seen.add(description.lower())
            resolution = " ".join(str(row.get("resolution") or "").split())[:220]
            lines.append(f"{description} - fixed: {resolution}" if resolution else description)
    return lines[-MAX_FIXES_TO_KEEP:]


__all__ = [
    "GATING",
    "carried_from",
    "defect_log",
    "definition_of_done_gaps",
    "findings_of",
    "fixes_to_keep",
    "lessons_from",
    "with_dispositions",
    "work_order_outcomes",
]
