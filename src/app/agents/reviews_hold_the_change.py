"""A review holds what the change touches, not whole files it has no room for (plan KG.8).

Behind `REVIEWS_HOLD_THE_CHANGE_AND_ITS_USES`, off in code until measured.

A code or security review whose changed files do not all fit its request and memory was told to open the rest
itself: measured, 71% of a security review's input and 46% of a code review's was re-reading those files. A reviewer
judges the change and whether what uses it still fits; the code graph knows both (KG.3).

With the switch on, each changed file a review is not shown whole - left out of the security review's source budget,
or not held in a review's memory past the size gate (`review_files.held_for_review`) - is given in the request as:

- each definition holding a changed line (against the commit the sprint was last accepted at; every definition of a
  file new since), innermost first, whole and numbered as in the file, while the room lasts - the rest by signature
  and lines;
- for each, the signatures of the definitions that use it in other files (file and lines), so a reviewer sees whether
  the callers still fit without reading them.

Changed files that fit are held whole as before; a product whose review fits as today is sent as today.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Iterable, Sequence

from app.analysis import graph_lookups
from app.switches import is_on

logger = logging.getLogger(__name__)

NAME = "REVIEWS_HOLD_THE_CHANGE_AND_ITS_USES"
#: `REVIEWS_HOLD_THE_CHANGE_AND_ITS_USES` set to on or off overrides this.
ON_BY_DEFAULT = False
#: The most characters of definitions held whole in one request.
MOST_CHARACTERS = 16_000
#: Users shown per definition, at most.
MOST_USERS = 6
#: How the section is headed; the switch-firing check reads it in the request.
SAID = "each with the signatures of what uses it"
HEADING = (f"--- The changed definitions of the files not shown whole above, {SAID} in other files "
           "(from the harness's code graph) ---")
#: What the admin page says this switch does.
explanation = ("A code or security review's changed files that do not fit its request are given as the definitions "
               "holding changed lines, whole and numbered, each with the signatures of what uses it in other files, "
               "instead of being left for the reviewer to read. Files that fit are held whole as before.")

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.M)


def enabled() -> bool:
    return is_on(NAME, ON_BY_DEFAULT)


def accepted_commit(root: str | Path) -> str:
    """The commit the sprint was last accepted at; "" when none is recorded."""
    try:
        from app import ci

        accepted = ci.load(root, "accepted")
        return str(getattr(accepted, "commit", "") or "") if accepted else ""
    except Exception:  # noqa: BLE001 - every definition is then changed
        return ""


def changed_lines(root: str | Path, file: str, since: str) -> set[int] | None:
    """The lines of `file` (as it is now) changed since `since`; None for every line (no commit to compare with, or
    a file new since)."""
    if not since:
        return None
    from app.tools.version_control import git_safely
    import subprocess

    try:
        done = subprocess.run([*git_safely(), "-C", str(root), "diff", "-U0", since, "--", file],
                              capture_output=True, text=True, errors="replace", timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0 or "\nnew file mode" in "\n" + done.stdout:
        return None
    if not done.stdout.strip():
        # Unchanged since, or not tracked at all (a file new since that was never added): only the second is a change.
        try:
            known = subprocess.run([*git_safely(), "-C", str(root), "cat-file", "-e", f"{since}:{file}"],
                                   capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            return set()
        return set() if known.returncode == 0 else None
    found: set[int] = set()
    for start, count in _HUNK.findall(done.stdout):
        first, many = int(start), int(count) if count else 1
        found.update(range(first, first + max(many, 1)))
    return found


def _changed(found: list[list[Any]], lines: set[int] | None) -> list[list[Any]]:
    """The definitions holding a changed line, innermost; every outermost one when all lines are changed."""
    if lines is None:
        return [row for row in found if not any(o is not row and o[2] <= row[2] and row[3] <= o[3] for o in found)]
    chosen: dict[tuple[int, int, str], list[Any]] = {}
    for line in sorted(lines):
        row = graph_lookups.innermost(found, line)
        if row is not None:
            chosen.setdefault((row[2], row[3], row[1]), row)
    return sorted(chosen.values(), key=lambda r: r[2])


def section(root: str | Path, files: Sequence[str], since: str = "", room: int = MOST_CHARACTERS
            ) -> tuple[str, list[str]]:
    """(the section, the files it gives) for the changed `files` (workspace-relative) a review is not shown whole;
    ("", []) with the switch off or nothing the graph reads. Never raises."""
    if not files or not enabled():
        return "", []
    try:
        from app.analysis.project_graph import build

        graph = build(root)
        used = 0
        parts: list[str] = []
        given: list[str] = []
        for wanted in files:
            file = graph_lookups.graph_key(graph, root, wanted)
            found = graph_lookups.rows(graph, file) if file else []
            if not found:
                continue
            lines = graph_lookups.text_lines(root, file)
            changed = _changed(found, changed_lines(root, file, since))
            if not changed:
                continue
            given.append(str(wanted))
            parts.append(f"=== {file} ({len(lines)} lines; its changed definitions) ===")
            for row in changed:
                body = graph_lookups.numbered(lines, row[2], row[3])
                if used + len(body) <= room:
                    used += len(body)
                    parts.append(f"[lines {row[2]}-{row[3]}]\n{body}")
                else:
                    parts.append(f"[lines {row[2]}-{row[3]}, not shown: the room is full - read them by range] "
                                 + graph_lookups.signature(lines, row))
                users = []
                for where, caller in graph_lookups.callers(graph, file, graph_lookups.key(row)):
                    if where == file:
                        continue
                    caller_row = graph_lookups.by_key(graph, where, caller) if caller else None
                    users.append(f"`{where}` lines {caller_row[2]}-{caller_row[3]}: "
                                 + graph_lookups.signature(graph_lookups.text_lines(root, where), caller_row)
                                 if caller_row else f"`{where}` (at its top)")
                if users:
                    parts.append(f"What uses `{graph_lookups.key(row)}` in other files:\n"
                                 + "\n".join(f"- {u}" for u in users[:MOST_USERS])
                                 + (f"\n- and {len(users) - MOST_USERS} more" if len(users) > MOST_USERS else ""))
        if not given:
            return "", []
        return (f"\n{HEADING}\n" + "\n".join(parts) + "\nJudge the change here: open a file only for lines this "
                "does not show.\n"), given
    except Exception:  # noqa: BLE001 - the review as before
        logger.debug("Could not hold a review's changed definitions", exc_info=True)
        return "", []


def for_files_not_shown(root: str | Path, not_shown: Sequence[str]) -> tuple[str, list[str]]:
    """(the section for the files a request's budget left out, those of them it does not give); ("", the files as
    given) with the switch off or none left out."""
    if not not_shown or not enabled():
        return "", list(not_shown)
    text, given = section(root, not_shown, accepted_commit(root))
    return text, [path for path in not_shown if path not in set(given)]


def with_the_change(request: dict[str, Any], root: str | Path, under_review: Iterable[str], held: Sequence[str] | None,
                    fits: bool, since: str = "") -> dict[str, Any]:
    """A review's request with the section for each file under review its memory does not hold; as it is when the
    review fits as today (`fits`) or the switch is off."""
    if fits or not enabled():
        return request
    rest = [path for path in under_review if path not in set(held or ())]
    text, _given = section(root, rest, since or accepted_commit(root))
    if text and request.get("messages") and isinstance(request["messages"][-1].get("content"), str):
        request["messages"][-1]["content"] += "\n" + text
    return request


def effects_lines(records: Iterable[Any]) -> list[str]:
    """`loop.sh effects` (KG.8): review stages given the changed definitions, and their reads and opening input tokens
    against the other reviews (medians)."""
    records = [r for r in records if isinstance(r, dict)]
    carried = graph_lookups.stages_carrying(records, SAID)
    head = "KG.8 reviews given the changed definitions and their uses"
    if not carried:
        return [f"     -  {head}: not reached"]
    stages = graph_lookups.per_stage(records)
    reviews = {s: v for s, v in stages.items() if s.startswith(("code_review", "security_review"))}

    def described(group: list[dict[str, int]]) -> str:
        return (f"reads {graph_lookups.median_of([s['reads'] for s in group])}, opening tokens "
                f"{graph_lookups.median_of([s['opening'] for s in group if s['opening']])}")

    on = [v for s, v in reviews.items() if s in carried]
    off = [v for s, v in reviews.items() if s not in carried]
    return [f"  {len(carried):>4}  {head} (medians: {described(on)}; other reviews {described(off)})"]


__all__ = ["HEADING", "MOST_CHARACTERS", "NAME", "ON_BY_DEFAULT", "SAID", "accepted_commit", "changed_lines",
           "effects_lines", "enabled", "explanation", "section", "with_the_change"]
