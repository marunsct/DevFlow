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


#: A name a criterion puts in quotes - the control, field or label it names:
#: `a checkbox labelled "Done"`, `a button named “Delete”`.
_QUOTED = re.compile(r'"([^"\n]{1,60})"|\u201c([^\u201d\n]{1,60})\u201d')


def _names_only_later_criteria_quote(repo_root: str | Path, later: set[str]) -> dict[str, set[str]]:
    """Each name quoted by not-yet-due criteria and by no criterion due now."""
    from app.acceptance import suite

    quoted_by: dict[str, set[str]] = {}
    for criterion in suite.criteria(repo_root):
        for match in _QUOTED.finditer(criterion.text or ""):
            name = (match.group(1) or match.group(2) or "").strip()
            if name:
                quoted_by.setdefault(name, set()).add(criterion.id)
    return {name: ids for name, ids in quoted_by.items() if ids <= later}


def _declared_with_bodies(repo_root: str | Path) -> list[tuple[str, str, str]]:
    """(file, test title, the test's text up to the next declaration) for every locked test."""
    from app.acceptance import suite

    root = Path(repo_root)
    found: list[tuple[str, str, str]] = []
    for path in suite.suite_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        shown = path.relative_to(root).as_posix()
        marks = sorted(
            [(m.start(), m.group(2)) for m in suite._TITLED.finditer(text)]
            + [(m.start(), m.group(1)) for m in suite._NAMED.finditer(text)]
        )
        for index, (begins, title) in enumerate(marks):
            ends = marks[index + 1][0] if index + 1 < len(marks) else len(text)
            found.append((shown, title, text[begins:ends]))
    return found


def waiting_tests(repo_root: str | Path | None) -> dict[str, list[str]]:
    """Each locked test that cannot pass before a later sprint, by title, with what it waits on.

    A test waits on a criterion it carries that is not yet due - and on one
    whose control it drives, whatever it carries. Measured on one run: two
    tests tagged with sprint 1's "a task cannot be added without a title" were
    persistence tests that ticked "Done" and pressed "Delete", which sprint 2's
    criteria name. Judged with sprint 1, they failed it, and its fix stage
    built sprint 2's completion and deletion to make them pass.

    A control is a name a criterion quotes, and a test drives it when its own
    text quotes the same name. A name a criterion due now also quotes is this
    sprint's, so it never makes a test wait.
    """
    later = set(not_yet_due(repo_root))
    if not later or not repo_root:
        return {}
    try:
        names = _names_only_later_criteria_quote(repo_root, later)
        waiting: dict[str, set[str]] = {}
        for _, title, body in _declared_with_bodies(repo_root):
            needs = set(junit.tags_in(title)) & later
            for name, ids in names.items():
                if re.search(r"([\'\"`])" + re.escape(name) + r"\1", body):
                    needs |= ids
            if needs:
                waiting.setdefault(title, set()).update(needs)
    except Exception:  # noqa: BLE001 - unreadable means due
        logger.debug("Could not read which tests wait on a later sprint", exc_info=True)
        return {}
    return {title: _ordered(list(ids)) for title, ids in waiting.items()}


def waits_on(name: str, waiting: dict[str, list[str]]) -> list[str]:
    """What the test a runner reported as `name` waits on, or []. Runners prefix a test's groups."""
    for title, ids in waiting.items():
        if name == title or name.endswith(f" {title}") or name.endswith(title):
            return ids
    return []


def later_sprints_files(repo_root: str | Path | None) -> dict[str, list[str]]:
    """Each locked suite file whose every test waits on a later sprint, with what they wait on.

    A file holding one test this sprint can pass is this sprint's to read as well.
    """
    waiting = waiting_tests(repo_root)
    if not waiting:
        return {}
    try:
        per_file: dict[str, list[str]] = {}
        for name, title, _ in _declared_with_bodies(repo_root):
            per_file.setdefault(name, []).append(title)
    except Exception:  # noqa: BLE001 - unreadable means due
        return {}
    files: dict[str, list[str]] = {}
    for name, titles in per_file.items():
        tagged = [title for title in titles if junit.tags_in(title)]
        if tagged and all(title in waiting for title in tagged):
            files[name] = _ordered([item for title in tagged for item in waiting[title]])
    return files


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


def only_later_sprints_fail(repo_root: str | Path | None) -> bool:
    """Whether the project's last test reports fail only on tests that wait on a later sprint.

    False when nothing waits, when no report can be read, or when no failed test
    is listed at all - a run that crashed lists none, and that is a failure of
    its own. Measured on one run: sprint 2's `npm test` ran the unit tests and
    then the whole acceptance suite, so it exited 1 on sprint 3's filtering and
    layout tests alone; the round, rightly, reported no defect, and the harness
    recorded "the suite does not pass" as one - which spent the attempt.
    """
    waiting = waiting_tests(repo_root)
    if not waiting or not repo_root:
        return False
    failed: list[junit.TestResult] = []
    read_any = False
    for path in _reports(Path(str(repo_root))):
        if not path.exists():
            continue
        report = junit.read(path)
        read_any = read_any or bool(report.tests)
        failed.extend(test for test in report.tests if test.outcome == "failed")
    return read_any and bool(failed) and all(waits_on(test.name, waiting) for test in failed)


def note_on_failures(repo_root: str | Path | None, since: float) -> str:
    """What a test command's failures that belong to later sprints are, or "".

    Read from the reports the command wrote - any written at or after `since`
    (a wall-clock time) - so it does not depend on one runner's console output.
    """
    waiting = waiting_tests(repo_root)
    if not waiting:
        return ""
    root = Path(str(repo_root))
    failed: list[junit.TestResult] = []
    for path in _reports(root):
        try:
            if not path.exists() or path.stat().st_mtime < since:
                continue
        except OSError:
            continue
        failed.extend(test for test in junit.read(path).tests if test.outcome == "failed")
    if not failed:
        return ""
    theirs = [test for test in failed if waits_on(test.name, waiting)]
    if not theirs:
        return ""
    ids = _listed(_ordered([item for test in theirs for item in waits_on(test.name, waiting)]))
    if len(theirs) == len(failed):
        return (
            f"Every failing test here ({len(theirs)}) needs what a later sprint builds "
            f"({ids}). They are expected to fail until that sprint: this one is "
            "not asked to make them pass, so leave them failing."
        )
    return (
        f"{len(theirs)} of the {len(failed)} failing tests need what a later sprint "
        f"builds ({ids}) and are expected to fail until then - leave those. The other "
        f"{len(failed) - len(theirs)} are this sprint's."
    )


__all__ = [
    "SCOPE_FILE",
    "brief",
    "later_sprints_files",
    "not_yet_due",
    "waiting_tests",
    "waits_on",
    "note_on_failures",
    "only_later_sprints_fail",
    "record",
]
