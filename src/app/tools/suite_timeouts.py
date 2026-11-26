"""A run of a test suite that cannot finish within a command's limit, before it is run (LF.1589).

Measured on a page product, in the stage that writes its acceptance suite: the suite was run whole three times in
half an hour - `npm run test:e2e`, `npx playwright test`, `npx playwright test --reporter=line --workers=4` - and each
ran out of the 300-second limit. Nothing was built yet, so every browser test waited its whole limit of its own for an
element that was not there, and the suite as a whole could never finish. The timeout's reply said to run a smaller
part; each next command was a new spelling of the same run, so no check that compares argv saw a repeat.

Two answers, both read from the runner table (`app.stacks.test_runners`), never from a runner named here:

- `before_a_run`: in the stage that writes the suite, before the suite was ever locked (so before any builder ran),
  a run of a runner that has a per-test limit is held to its short one. Every test then fails at its first wait in
  seconds, and the run reports each test's own error - what that stage needs from it - within the limit.
- `refusal`: a test command whose run of the same tests, or more, ran out of the whole limit earlier in this stage is
  not run, unless something outside the suite has changed since; the reply says so and names a narrower run.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from app.stacks import test_runners

logger = logging.getLogger(__name__)

#: The stage that writes the acceptance suite (`acceptance_author_<round>`).
SUITE_WRITER = "acceptance_author"
#: The share of the limit an earlier run must have used to have run out of the whole of it, not of a shorter retry's.
WHOLE_LIMIT_SHARE = 0.9

HELD_PER_TEST = (
    "Each test was held to {seconds} seconds here (`{option}` added to the command): nothing the suite checks is "
    "built yet, so each test waits until its own limit for what is not there, and at the usual limits the whole run "
    "outlasts the limit of a command. A test stopped at that limit, or not finding what the product will show, fails "
    "for that reason alone. A syntax error, an import that does not resolve or an error thrown by the test's own code "
    "is still yours to correct. The harness runs the suite at its own limits."
)


def _never_locked(repo_root: str | Path) -> bool:
    """Whether the acceptance suite has never been locked: no builder has run yet. Never raises."""
    try:
        from app.acceptance import suite

        state = suite._state(repo_root)  # noqa: SLF001 - the suite's own record, read as `by_sprint` reads it
        return "lock" not in state and not int(state.get("lock_version") or 0)
    except Exception:  # noqa: BLE001 - unknown is "it may be built": nothing is changed
        return False


def before_a_run(
    command: Sequence[str], *, repo_root: str | Path, project_dir: str | Path, stage: str, category: str,
) -> tuple[Sequence[str], str]:
    """(the command to run, a note for its result): the command untouched and "" unless the rule above applies."""
    if isinstance(command, str) or category != "test" or not str(stage or "").startswith(SUITE_WRITER):
        return command, ""
    argv = [str(part) for part in command]
    call = test_runners.read(argv, project_dir)
    if call is None or not call.runner.per_test_limit or not _never_locked(repo_root):
        return command, ""
    held, option = test_runners.with_a_short_limit_per_test(argv, call)
    if not option:
        return command, ""
    return held, HELD_PER_TEST.format(seconds=call.runner.short_limit_ms // 1000, option=option)


def _when(entry: dict[str, Any]) -> float | None:
    try:
        return datetime.fromisoformat(str(entry.get("at"))).timestamp()
    except (TypeError, ValueError):
        return None


def _changed_outside_the_suite(repo_root: str | Path, project_dir: Path, since: float) -> bool:
    """Whether a file of the project outside the acceptance suite changed after `since`: the product or how the suite
    is set up, either of which can let a whole run finish. Never raises; unknown is "changed"."""
    try:
        from app.acceptance import suite
        from app.tools.sandbox import files_changed_since

        where = suite.directory(repo_root)
        the_suite = where.resolve() if where is not None else None
        for relative in files_changed_since(str(project_dir), since):
            if relative.startswith("... and "):
                return True
            path = (project_dir / relative).resolve()
            if the_suite is None or not path.is_relative_to(the_suite):
                return True
    except Exception:  # noqa: BLE001
        return True
    return False


def _a_test_to_name(repo_root: str | Path, project_dir: Path) -> tuple[str, str]:
    """(a criterion id one of the suite's tests carries, one of the suite's files relative to the project); "" for
    either when the suite has none. Never raises."""
    try:
        from app.acceptance import junit, suite

        declared = suite.declared_tests(repo_root)
    except Exception:  # noqa: BLE001
        return "", ""
    name = next((tag for _, title in declared for tag in junit.tags_in(title)), "")
    file = ""
    for shown, _ in declared:
        try:
            file = (Path(repo_root) / shown).resolve().relative_to(project_dir.resolve()).as_posix()
            break
        except ValueError:
            continue
    return name, file


def refusal(
    command: Sequence[str], *, repo_root: str | Path, project_dir: str | Path, where: str, stage: str,
    category: str, limit: int, entries: Sequence[dict[str, Any]],
) -> str:
    """Why this command is not run (the rule above), or "". `entries` are the agents' ledger entries, oldest first;
    `where` is the directory the command runs in as the ledger spells it. Never raises."""
    try:
        if isinstance(command, str) or category != "test" or not stage:
            return ""
        argv = [str(part) for part in command]
        project = Path(project_dir)
        call = test_runners.read(argv, project)
        if call is None:
            return ""
        wanted = test_runners.selection(call)
        for entry in reversed(list(entries)):
            spent = entry.get("duration_seconds")
            if (
                entry.get("stage") != stage
                or entry.get("working_directory") != where
                or not str(entry.get("error") or "").lstrip().startswith("Command timed out")
                or not isinstance(spent, (int, float)) or spent < limit * WHOLE_LIMIT_SHARE
            ):
                continue
            earlier_argv = [str(part) for part in entry.get("command") or []]
            earlier = test_runners.read(earlier_argv, project)
            if earlier is None or earlier.runner != call.runner or not wanted <= test_runners.selection(earlier):
                continue
            since = _when(entry)
            if since is None or _changed_outside_the_suite(repo_root, project, since):
                continue
            return _the_reply(argv, call, earlier_argv, earlier, limit, repo_root, project)
    except Exception:  # noqa: BLE001 - a guard must never fail the command
        logger.debug("Could not compare this run with the timed-out ones", exc_info=True)
    return ""


def _the_reply(
    argv: list[str], call: test_runners.RunnerCall, earlier: list[str], earlier_call: test_runners.RunnerCall,
    limit: int, repo_root: str | Path, project: Path,
) -> str:
    added = [word for word in call.arguments if word not in earlier_call.arguments and word != "--"]
    how = f" (what it adds, `{' '.join(added)}`, does not choose which tests run)" if added else ""
    name, file = _a_test_to_name(repo_root, project)
    forms = test_runners.narrower_forms(argv, call, name=name, file=file)
    fewer = (
        "Run fewer of them: " + " or ".join(f"`{form}`" for form in forms) + "."
        if forms else "Run fewer of them: one test file, or the tests whose names carry one criterion id."
    )
    return (
        f"Not run: `{' '.join(earlier)}` ran out of the {limit}-second limit earlier in this stage, and this command "
        f"runs the same tests or more{how}, with nothing outside the suite changed since, so it would run out again. "
        f"{fewer} A change to the product, or to how the suite is set up, lets the whole run be tried again."
    )
