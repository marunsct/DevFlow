"""The acceptance suite written and locked a sprint at a time (LF.1266, owner 2026-11-24).

Measured on a medium brief: the whole suite - 97 tests for 13 criteria - was written and locked before any code, one
account per test and seven copies of its helpers, and locked "with these still open". Its writers had nothing to write
against but the specification, and every sprint then worked beside tests of criteria not due until much later.

For a product the plan can split into more than one sprint, the criteria and the interface contract are still fixed up
front, but the sprint plan comes first, and each sprint's tests are written and locked by QA at that sprint's start -
against the criteria, the brief, the contract and the running product of the earlier sprints. Each lock is a new
version that only adds: the files locked with an earlier sprint stay exactly as they were, except through the repair
and dispute paths that already reopen a locked suite. A sprint's gate runs its own tests and the earlier ones
(`due_tests`); the whole suite runs at release, where every criterion has locked tests or is named as a gap.

A product whose criteria allow only one sprint (`max_sprints_for_criteria_count`) is written, locked and planned
exactly as before: the suite first, then the plan.

The record is kept in the suite's own state (`suite.STATE_FILE`): whether this run writes by sprint, decided once at
the first writing, and the addition open now - its criteria and the files locked before it - until the next lock.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path
from typing import Any, Sequence

from app.acceptance import suite

logger = logging.getLogger(__name__)

#: In the suite's state: this run writes its suite a sprint at a time.
BY_SPRINT = "written_by_sprint"
#: In the suite's state: the addition open now - {"criteria", "base", "sprint", "of", "at_release"}.
ADDING = "adding"
#: In the suite's state: the criteria the release asked QA for, once.
ASKED_AT_RELEASE = "asked_at_release"

#: Why a criterion the release could not get a locked test for is deferred: named among the release's cuts.
NEVER_WRITTEN = "no locked test was written for it before the release"


def writes_by_sprint(criteria_count: int, *, fast: bool) -> bool:
    """Whether a product with this many criteria has its suite written a sprint at a time: when it may be planned as
    more than one sprint."""
    from app.agents.scrum_master import max_sprints_for_criteria_count

    return criteria_count > 0 and max_sprints_for_criteria_count(criteria_count, fast=fast) > 1


def is_on(repo_root: str | Path | None) -> bool:
    """Whether this run's suite is written a sprint at a time. Never raises."""
    if not repo_root:
        return False
    try:
        return bool(suite._state(repo_root).get(BY_SPRINT))  # noqa: SLF001 - the suite's own record
    except Exception:  # noqa: BLE001 - unknown is the whole suite at once, as before
        return False


def decide(repo_root: str | Path, *, fast: bool) -> bool:
    """At the first writing: whether the suite is written a sprint at a time, recorded when it is. Never raises.

    Never for a suite locked before: a run whose whole suite is already locked goes on as it was locked.
    """
    try:
        if is_on(repo_root):
            return True
        state = suite._state(repo_root)  # noqa: SLF001
        if state.get("lock") or int(state.get("lock_version") or 0):
            return False
        if not writes_by_sprint(len(suite.criteria(repo_root)), fast=fast):
            return False
        suite._save_state(repo_root, {**state, BY_SPRINT: True})  # noqa: SLF001
        logger.info("The acceptance suite is written a sprint at a time: the sprints are planned first")
        return True
    except Exception:  # noqa: BLE001 - the whole suite at once, as before
        logger.debug("Could not decide how the suite is written", exc_info=True)
        return False


def still_to_write(repo_root: str | Path, ids: Sequence[str]) -> list[str]:
    """Of `ids`, the criteria of this product that no test names and that are not deferred, in order."""
    known = {criterion.id for criterion in suite.criteria(repo_root)}
    covered = suite.coverage(repo_root)
    excused = set(suite.deferred(repo_root))
    return [item for item in dict.fromkeys(str(i) for i in ids or ())
            if item in known and item not in excused and not covered.get(item)]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def open_for(repo_root: str | Path, ids: Sequence[str], *, sprint: int, of: int, at_release: bool = False) -> None:
    """Open the suite for the tests of `ids`, keeping what was locked before as the part that may not change."""
    state = suite._state(repo_root)  # noqa: SLF001
    base = dict(state.get("lock") or {})
    state[ADDING] = {"criteria": list(dict.fromkeys(str(i) for i in ids)), "base": base,
                     "sprint": int(sprint), "of": int(of), "at_release": bool(at_release)}
    if at_release:
        state[ASKED_AT_RELEASE] = sorted({*(state.get(ASKED_AT_RELEASE) or []), *map(str, ids)})
    suite._save_state(repo_root, state)  # noqa: SLF001
    suite.unlock(repo_root)


def addition(repo_root: str | Path | None) -> dict[str, Any] | None:
    """The addition open now, or None. Never raises."""
    if not repo_root:
        return None
    try:
        found = suite._state(repo_root).get(ADDING)  # noqa: SLF001
    except Exception:  # noqa: BLE001
        return None
    return found if isinstance(found, dict) else None


def asked_at_release(repo_root: str | Path) -> list[str]:
    return [str(item) for item in suite._state(repo_root).get(ASKED_AT_RELEASE) or []]  # noqa: SLF001


def earlier_files(repo_root: str | Path | None) -> list[str]:
    """The suite's files locked before the addition open now (workspace-relative); [] when none is open."""
    adding = addition(repo_root)
    return sorted((adding or {}).get("base") or {})


def is_an_earlier_sprint_s(repo_root: str | Path, relative_path: str) -> bool:
    """Whether a workspace-relative path is a file locked with an earlier sprint, while a later sprint's tests are
    written. Never raises."""
    try:
        path = relative_path.strip().lstrip("/").replace("\\", "/")
        return path in set(earlier_files(repo_root))
    except Exception:  # noqa: BLE001 - nothing refused on a record that cannot be read
        return False


def put_back_what_the_addition_changed(repo_root: str | Path) -> list[str]:
    """Each file locked with an earlier sprint that the addition changed or removed, put back as locked; one line each.

    The lock only adds: an earlier sprint's tests change only through a repair or a dispute. Never raises.
    """
    base = dict((addition(repo_root) or {}).get("base") or {})
    if not base:
        return []
    root = Path(repo_root)
    snapshot = root / suite.SNAPSHOT_DIR
    put_back: list[str] = []
    for relative, wanted in sorted(base.items()):
        try:
            target, source = root / relative, snapshot / relative
            if not source.is_file() or (target.is_file() and _digest(target) == wanted):
                continue
            existed = target.exists()
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            put_back.append(
                f"`{relative}` is locked with an earlier sprint's tests and was "
                f"{'changed' if existed else 'removed'}; it is back as it was locked. Put this sprint's tests, and "
                "any helper they need, in new files of their own."
            )
        except OSError:
            logger.debug("Could not put back %s", relative, exc_info=True)
    if put_back:
        logger.warning("An addition to the locked suite changed %d earlier file(s); put back", len(put_back))
    return put_back


def new_files(repo_root: str | Path) -> list[str]:
    """The suite's files the addition open now added (workspace-relative); [] when none is open."""
    adding = addition(repo_root)
    if adding is None:
        return []
    base = set(adding.get("base") or {})
    root = Path(repo_root)
    return [path.relative_to(root).as_posix() for path in suite.suite_files(repo_root)
            if path.relative_to(root).as_posix() not in base]


def _named_in(finding: str, files: Sequence[str], titles: Sequence[str]) -> bool:
    return any(name in finding or Path(name).name in finding for name in files) or any(
        title in finding for title in titles if len(title) >= 6)


def about_the_addition(repo_root: str | Path, findings: Sequence[Any]) -> list[Any]:
    """`findings` without those about the earlier sprints' locked tests alone, while an addition is open, and without
    those about later sprints' criteria alone.

    A finding that names an earlier file or test and nothing the addition wrote is not the writers' to act on: those
    files are put back as locked. Such a test is repaired through the paths that reopen a locked suite.
    """
    from app.acceptance.junit import tags_in

    if not is_on(repo_root):
        return list(findings)
    later = criteria_not_yet_due(repo_root)
    # One that names only criteria whose sprint has not started is that sprint's writers' to act on.
    findings = [finding for finding in findings
                if not ((named := {t for t in tags_in(str(finding)) if t.startswith("AC-")}) and named <= later)]
    adding = addition(repo_root)
    if adding is None or not adding.get("base"):
        return list(findings)
    base = set(adding.get("base") or {})
    declared = suite.declared_tests(repo_root)
    earlier_titles = [name for file, name in declared if file in base]
    added = [file for file, _ in declared if file not in base] + new_files(repo_root)
    added_titles = [name for file, name in declared if file not in base]
    kept = []
    for finding in findings:
        text = str(finding)
        if _named_in(text, sorted(base), earlier_titles) and not _named_in(text, added, added_titles):
            continue
        kept.append(finding)
    if len(kept) < len(findings):
        logger.info("%d finding(s) about earlier sprints' locked tests are not the addition's", len(findings) - len(kept))
    return kept


def criteria_not_yet_due(repo_root: str | Path | None) -> set[str]:
    """The criteria whose sprint has not started, as recorded (`sprint_scope`)."""
    from app.acceptance import sprint_scope

    return set(sprint_scope.not_yet_due(repo_root))


# --- what QA is told --------------------------------------------------------------

#: The existing rule (the suite dispute's): the product's code never decides what a test expects.
def _the_product_s_code_is_not_the_standard() -> str:
    from app.agents.suite_dispute import THE_PRODUCT_S_CODE_IS_NOT_THE_STANDARD

    return THE_PRODUCT_S_CODE_IS_NOT_THE_STANDARD


#: How the product stands when a later sprint's tests are written: the earlier sprints' work runs.
EARLIER_SPRINTS_BUILT = (
    "The product the earlier sprints built is running, and their tests are locked: they stay exactly as they are. "
    "Write the tests of this sprint's criteria now - they decide when this sprint is done. "
)

#: The rule a later sprint's writers run the suite by, in place of "nothing is built".
RUN_AN_ADDITION_ONCE = (
    "- Run the suite once. This sprint's tests must RUN, and FAIL where they need what this sprint builds: the "
    "builders write it after these tests are locked, so a feature answering wrongly or not at all is right for now. "
    "A syntax error, an import that does not resolve, \"no tests found\", or an error the test's own code throws - a "
    "helper called with the wrong arguments, a name the test never defined - is yours to fix before you finish: read "
    "why each test failed, not only that it did.\n"
)


def note(sprint: int, of: int, group: Sequence[Any], earlier: Sequence[str]) -> str:
    """What the writers of one sprint's part of the suite are told, after its criteria."""
    ids = ", ".join(str(getattr(criterion, "id", criterion)) for criterion in group)
    if sprint >= of:
        part = f"This is the last sprint's part (sprint {sprint} of {of}): the tests of the criteria above, {ids}."
    else:
        part = (f"This is sprint {sprint}'s part, of {of}: the tests of the criteria above, {ids}. Later sprints' "
                "criteria are written at their own sprint's start; leave them to it.")
    lines = [
        "--- This suite is written a sprint at a time ---",
        part,
    ]
    if earlier:
        named = ", ".join(f"`{name}`" for name in list(earlier)[:12]) + (
            f" and {len(earlier) - 12} more" if len(earlier) > 12 else "")
        lines.append(
            f"The earlier sprints' tests are locked, in {named}. They stay exactly as they are: a change to one of "
            "those files is put back. Put this sprint's tests in new files beside them, named in the same way; use "
            "their helpers and fixtures by importing them, and write any new helper in a new file of your own. Each "
            "test name carries the id of the criterion it proves."
        )
        lines.append(
            "Write each test from its criterion, the brief and the interface contract. "
            + _the_product_s_code_is_not_the_standard()
        )
    else:
        lines.append(
            "Also write what later sprints' tests will share - helpers, fixtures, how the product is started - in "
            "files of their own, so later parts can import them and leave them as they are."
        )
    return "\n".join(lines) + "\n\n"


def review_note(group: Sequence[str], added: Sequence[str], earlier: Sequence[str]) -> str:
    """What the QA lead is told when it reviews one sprint's addition to a locked suite."""
    if not earlier:
        return ""
    return (
        "--- This review is of one sprint's addition ---\n"
        f"The suite is written a sprint at a time. This sprint adds the tests of {', '.join(group)}, in "
        + (", ".join(f"`{name}`" for name in added) or "new files")
        + ". The earlier sprints' files are locked and not under review: judge the new tests only, and name a finding "
        "by the new test it is about.\n\n"
    )


__all__ = [
    "ADDING", "ASKED_AT_RELEASE", "BY_SPRINT", "EARLIER_SPRINTS_BUILT", "NEVER_WRITTEN", "RUN_AN_ADDITION_ONCE",
    "about_the_addition", "addition", "asked_at_release", "criteria_not_yet_due", "decide", "earlier_files",
    "is_an_earlier_sprint_s", "is_on", "new_files", "note", "open_for", "put_back_what_the_addition_changed",
    "review_note", "still_to_write", "writes_by_sprint",
]
