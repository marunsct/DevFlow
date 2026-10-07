"""Which of the locked acceptance tests belong to a later sprint.

QA writes and locks the acceptance suite for the whole product before the first
sprint, so every sprint's builders work beside the tests of criteria later
sprints deliver. Nothing told them which those were. Measured on one run, whose
sprint plan gave sprint 1 four criteria and deferred editing, deleting,
completing and filtering to sprint 2 by name: sprint 1's backend specialist's
first write of the product's module, made before it had run anything, already
held all of them. It then ran the whole suite, saw seven failures - every one a
later sprint's test - and spent the next thirty minutes and a restart making
them pass. Sprint 1's test round passed all 23 tests; the milestone review found
the product 84 lines over the brief's size limit and asked for the later
sprints' work to be taken out again, which sprint 2 would then have built a
second time.

A stage met that suite in three places, and each said "this is your work": the
workspace listing labelled every locked file "read it for what the product must
do", a stage's opening snapshot inlined two later sprints' files in full, and a
test command's output listed their failures beside this sprint's with nothing to
tell them apart. The workflow records the sprint's scope here when its builders
start, and each of those places reads it - as does the builders' own request.

Nothing here decides anything. A missing or unreadable record means every test
is treated as due, which is what happened before this existed.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Sequence

from app.acceptance import junit
from app.stacks import contract

logger = logging.getLogger(__name__)

SCOPE_FILE = f"{contract.HARNESS_DIR}/sprint-scope.json"

#: How many criteria and files one note names before "and N more".
MAX_NAMED = 8


def _ordered(ids: Sequence[str]) -> list[str]:
    """`AC-2` before `AC-10`."""

    def key(item: str) -> tuple[str, int, str]:
        match = re.match(r"([A-Za-z]+)-(\d+)$", item)
        return (match.group(1).upper(), int(match.group(2)), item) if match else (item, 0, item)

    return sorted(dict.fromkeys(ids), key=key)


def _listed(items: Sequence[str]) -> str:
    shown = ", ".join(items[:MAX_NAMED])
    return shown + (f" and {len(items) - MAX_NAMED} more" if len(items) > MAX_NAMED else "")


def record(repo_root: str | Path, *, sprint: int, of: int, not_yet_due: Sequence[str]) -> None:
    """Record the sprint now being built and the criteria it does not owe. Never raises."""
    try:
        path = Path(repo_root) / SCOPE_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        # Replaced whole, never truncated in place: parallel builders each
        # record it as they start, and a reader must never see half of it.
        staged = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}")
        staged.write_text(
            json.dumps(
                {"sprint": int(sprint), "of": int(of), "not_yet_due": _ordered([str(i) for i in not_yet_due])},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(staged, path)
    except Exception:  # noqa: BLE001 - a missing record treats every test as due
        logger.debug("Could not record the sprint scope", exc_info=True)


def _read(repo_root: str | Path | None) -> dict:
    if not repo_root:
        return {}
    try:
        data = json.loads((Path(repo_root) / SCOPE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def not_yet_due(repo_root: str | Path | None) -> list[str]:
    """The criteria a later sprint builds, as recorded for the sprint now being built."""
    items = _read(repo_root).get("not_yet_due")
    return [str(item) for item in items] if isinstance(items, list) else []


def later_sprints_files(repo_root: str | Path | None) -> dict[str, list[str]]:
    """Each locked suite file whose every tagged test is a later sprint's, with those criteria.

    A file that also tests a criterion due now is not one: it is this sprint's
    to read as well.
    """
    later = set(not_yet_due(repo_root))
    if not later:
        return {}
    try:
        from app.acceptance import suite

        per_file: dict[str, set[str]] = {}
        for name, test in suite.declared_tests(repo_root):
            per_file.setdefault(name, set()).update(junit.tags_in(test))
    except Exception:  # noqa: BLE001 - unreadable means due
        return {}
    return {
        name: _ordered(list(tags))
        for name, tags in per_file.items()
        if tags and tags <= later
    }


def brief(repo_root: str | Path | None, deferred: Sequence[str] = ()) -> str:
    """The section of a builder's request that says what later sprints build, or "".

    `deferred` is the sprint plan's own list of what this sprint leaves out.
    """
    scope = _read(repo_root)
    later = not_yet_due(repo_root)
    if not later:
        return ""
    try:
        from app.acceptance import suite

        texts = {c.id: c.text for c in suite.criteria(repo_root)}
    except Exception:  # noqa: BLE001 - the ids alone still say it
        texts = {}
    where = (
        f"This is sprint {scope.get('sprint')} of {scope.get('of')}. "
        if scope.get("sprint") and scope.get("of") else ""
    )
    lines = [
        "--- What later sprints build - not this sprint's work ---",
        where
        + "The locked acceptance suite was written for the whole product, so it also "
        "holds the tests of criteria later sprints deliver. Those tests fail until "
        "their sprint comes, and that is expected:",
        *(f"- {item}: {texts[item]}" if texts.get(item) else f"- {item}" for item in later),
    ]
    files = list(later_sprints_files(repo_root))
    if files:
        lines.append(f"Every test in {_listed(files)} is a later sprint's.")
    leaves_out = [" ".join(str(item).split()) for item in deferred or () if str(item).strip()]
    if leaves_out:
        lines.append("This sprint's plan leaves out:")
        lines.extend(f"- {item}" for item in leaves_out)
    lines.append(
        "Build what this sprint's criteria need and nothing a later sprint is planned "
        "to deliver. Work built early is reviewed and counted against the project's "
        "limits before it is due, and its own sprint builds it anyway. A failing "
        "test of a later criterion is never a reason to change code now."
    )
    return "\n".join(lines) + "\n\n"


def _reports(repo_root: Path) -> list[Path]:
    """The JUnit reports a project's test commands write."""
    found: list[Path] = []
    record = contract.read(repo_root)
    if record:
        project = repo_root / str(record.get("project") or "")
        for key in ("unit_report", "acceptance_report"):
            if record.get(key):
                found.append(project / str(record[key]))
        return found
    try:
        from app.acceptance import suite

        command = suite._command(repo_root)
    except Exception:  # noqa: BLE001 - no report, no note
        command = None
    if command:
        found.append(repo_root / command[2] / command[1])
    return found


def note_on_failures(repo_root: str | Path | None, since: float) -> str:
    """What a test command's failures that belong to later sprints are, or "".

    Read from the reports the command wrote - any written at or after `since`
    (a wall-clock time) - so it does not depend on one runner's console output.
    """
    later = set(not_yet_due(repo_root))
    if not later:
        return ""
    root = Path(str(repo_root))
    failed: list[junit.TestResult] = []
    for path in _reports(root):
        try:
            if not path.is_file() or path.stat().st_mtime < since:
                continue
        except OSError:
            continue
        failed.extend(test for test in junit.read(path).tests if test.outcome == "failed")
    if not failed:
        return ""
    theirs = [test for test in failed if test.tags and set(test.tags) <= later]
    if not theirs:
        return ""
    ids = _listed(_ordered([tag for test in theirs for tag in test.tags]))
    if len(theirs) == len(failed):
        return (
            f"Every failing test here ({len(theirs)}) tests a criterion a later sprint "
            f"builds ({ids}). They are expected to fail until that sprint: this one is "
            "not asked to make them pass, so leave them failing."
        )
    return (
        f"{len(theirs)} of the {len(failed)} failing tests test criteria a later sprint "
        f"builds ({ids}) and are expected to fail until then - leave those. The other "
        f"{len(failed) - len(theirs)} are this sprint's."
    )


__all__ = [
    "SCOPE_FILE",
    "brief",
    "later_sprints_files",
    "not_yet_due",
    "note_on_failures",
    "record",
]
