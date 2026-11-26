"""After a fixer's write, the tests that reach the files it changed run first; the defect's own only when those pass
(plan PF.3, behind `TESTS_REACHED_FIRST`).

The check after a write (`verify_after_write`) runs the defect's own tests and says whether they pass. A write that
broke a test which passed before - another criterion's, served by the same file - was found only at the measurement
after the stage, by the whole suite, and the whole fix was reverted for it: minutes of the fix round after the write
that caused it, with the fixer long gone.

With the switch on, each write the check is due for first runs the tests whose route or definitions the changed files
serve, from the code graph (`project_graph`, KG.4: an acceptance file's `tested_by`, a unit test's `unit_tests`):

- **acceptance tests** of the criteria those files are tested by, other than the defect's own, of which a test passed
  at the last measurement (`ci.load`), run file by file as the suite runs them (`per_file.each_file`);
- **unit tests**, when a changed file has unit tests that reach it and the unit tests passed before: the unit run.

A test that passed at the last measurement and fails now is a write that broke it: the write's reply names each (its
name, its file, the end of its message) and says the defect's own tests were not run, and the check counts as not
passed. When those pass, the defect's own tests run as before. Files no test reaches add nothing.

A transcript record (`RECORD_KIND`) per such check gives the seconds it took and what it found, for `loop.sh effects`.
Nothing here names a language, a framework or a runner: the graph says what reaches a file, and the tests run as the
suite's own command runs them. Never raises.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from app.switches import is_on

logger = logging.getLogger(__name__)

NAME = "TESTS_REACHED_FIRST"
#: `TESTS_REACHED_FIRST` set to on or off overrides this.
ON_BY_DEFAULT = False
#: How the write's reply opens when a test that reaches the changed files broke.
SAID = "The tests that reach the files you changed ran first"
#: The check's line when it does not pass, in place of `verify_after_write.FAILING`: it may be another test that failed.
FAILING = "The harness ran tests after the write: not all of them pass."
#: The defect's own tests, failing after the reached tests passed.
OWN_FAILING = "The tests that reach the files you changed still pass; this defect's own tests still fail."
#: Broken tests named in a reply, at most, and characters of each one's message.
MOST_NAMED = 4
MOST_MESSAGE = 300
RECORD_KIND = "tests_reached_first"


def enabled() -> bool:
    return is_on(NAME, ON_BY_DEFAULT)


def changed_files(root: str | Path, base: str) -> list[str]:
    """The workspace's files changed since `base`, committed or not, and the new files git does not ignore; the
    harness's own records left out."""
    from app import ci

    found: list[str] = []
    for args in (("diff", "--name-only", base, "--", "."), ("ls-files", "--others", "--exclude-standard")):
        done = ci._git(root, *args)
        if done is not None and done.returncode == 0:
            found += [line.strip() for line in done.stdout.splitlines() if line.strip()]
    return [path for path in dict.fromkeys(found) if not path.startswith((".harness/", "docs/"))]


def reached(graph: dict[str, dict[str, Any]], changed: Iterable[str]) -> tuple[dict[str, set[str]], set[str]]:
    """({acceptance test file: the criteria it carries for them}, {unit test file}) of the tests that reach `changed`
    by the code graph: those requesting their routes or selecting their text, those importing them, and the unit tests
    naming their definitions."""
    from app.analysis.routes_and_tests import tests_of

    acceptance: dict[str, set[str]] = {}
    unit: set[str] = set()
    for path in changed:
        if path not in graph:
            continue
        for test, criteria in tests_of(graph, path):
            acceptance.setdefault(test, set()).update(criteria)
        unit.update(graph[path].get("unit_tests") or [])
    return acceptance, unit


def _bare(name: str) -> str:
    from app import ci

    key = ci.stable(str(name))
    return key.rsplit(ci.WHERE, 1)[-1] if ci.WHERE in key else key


def broken_now(root: str | Path, base: str, defect: Any, run: Callable[..., dict[str, Any]] | None = None) -> list[str]:
    """Each test that reaches the files changed since `base`, passed at the last measurement and fails now, as
    "`name` (`file`): message"; [] when none broke, none reaches them, or nothing was measured before."""
    return _measured(root, base, defect, run)[0]


def _measured(root: str | Path, base: str, defect: Any,
              run: Callable[..., dict[str, Any]] | None = None) -> tuple[list[str], bool]:
    """(`broken_now`'s answer, whether any reached test was run)."""
    from app import ci
    from app.acceptance.junit import tags_in
    from app.analysis import project_graph
    from app.graph.first_failure import _its_criteria

    before = ci.load(root, "latest")
    changed = changed_files(root, base)
    if before is None or not changed:
        return [], False
    acceptance, unit = reached(project_graph.build(root), changed)
    passed = {_bare(key) for key, outcome in before.acceptance.items() if outcome == "passed"}
    passing_criteria = {tag for name in passed for tag in tags_in(name)}
    naming = {c for criteria in acceptance.values() for c in criteria} & passing_criteria
    naming -= _its_criteria(defect)
    broken: list[str] = []
    ran_any = False
    if naming:
        from app.acceptance import per_file
        from app.stacks import contract

        if run is None:
            from app.stacks.scaffold import sandbox_runner

            run = sandbox_runner(root)
        contract.enforce(root)
        ran_any = True
        for ran in per_file.each_file(root, contract.read(root) or {}, run, naming=naming, with_tests=True):
            tests = ran.get("tests") or []
            if ran.get("outcome") == "hung" or (not tests and ran.get("outcome") == "failed"):
                broken.append(f"`{ran.get('file')}` did not run to the end: "
                              + " ".join(str(ran.get("output") or "").split())[-MOST_MESSAGE:])
                continue
            broken += [f"`{t.get('name')}` (`{ran.get('file')}`): "
                       + " ".join(str(t.get("message") or "").split())[:MOST_MESSAGE]
                       for t in tests if t.get("outcome") == "failed" and _bare(t.get("name") or "") in passed]
    if unit and before.unit_ran and any(outcome == "passed" for outcome in before.unit.values()):
        ran_any = True
        broken += [f"`{name}` (a unit test)" for name in ci.unit_failures(root)
                   if before.unit.get(name) == "passed" or (name == ci.UNIT_TESTS_DID_NOT_RUN)]
    return broken, ran_any


def said(broken: list[str]) -> str:
    """The write's reply for tests it broke."""
    shown = "\n".join(f"- {line}" for line in broken[:MOST_NAMED])
    more = f"\n- and {len(broken) - MOST_NAMED} more" if len(broken) > MOST_NAMED else ""
    return (f"{SAID}, before this defect's own: {len(broken)} that passed before fail now.\n{shown}{more}\n"
            "Your change broke them, and this defect's own tests were not run. Make these pass again, keeping what "
            "your defect needs; the harness runs them again after your next write.")


class _Watch:
    """A fix stage's check after a write with the reached tests first."""

    def __init__(self, root: str | Path, base: str, defect: Any, check: Callable[[], bool | None],
                 then: Callable[[], str] | None, run_id: str | None, stage: str) -> None:
        self.root, self.base, self.defect, self.own, self.own_then = root, base, defect, check, then
        self.run_id, self.stage = run_id, stage
        self.broken: list[str] = []

    def check(self) -> bool | None:
        started = time.monotonic()
        try:
            self.broken, ran = _measured(self.root, self.base, self.defect)
        except Exception as error:  # noqa: BLE001 - the defect's own tests answer, as before
            from app.observability.degraded import degraded

            degraded("tests_reached_first", error)
            self.broken, ran = [], False
        if ran:
            self._note(time.monotonic() - started)
        if self.broken:
            return False
        return self.own()

    def then(self) -> str:
        if self.broken:
            return said(self.broken)
        now = self.own_then() if self.own_then is not None else ""
        return OWN_FAILING + ("\n" + now if now else "")

    def _note(self, seconds: float) -> None:
        try:
            from app.observability.transcript import record

            record(self.run_id, self.stage, RECORD_KIND, message=SAID if self.broken else "", seconds=round(seconds, 1),
                   broke=len(self.broken))
        except Exception:  # noqa: BLE001 - the check goes on unrecorded
            logger.debug("Could not record a check of the reached tests", exc_info=True)


def first(root: str | Path, base: str, defect: Any, check: Callable[[], bool | None], how: dict[str, Any], *,
          run_id: str | None = None, stage: str = "") -> tuple[Callable[[], bool | None], dict[str, Any]]:
    """`check` and the rest of `verify_after_write.watching`'s arguments (`how`), with the reached tests run first when
    the switch is on; both as they are when it is off or the fix has no commit to compare with."""
    if not enabled() or not base:
        return check, how
    from app.graph.verify_after_write import PASSED

    watch = _Watch(root, base, defect, check, how.get("then"), run_id, stage)
    return watch.check, {**how, "then": watch.then, "says": (PASSED, FAILING)}


def effects_lines(records: Iterable[Any]) -> list[str]:
    """`loop.sh effects` (PF.3): checks after a write that ran the reached tests first, those that found a broken test,
    and the median seconds they took."""
    from statistics import median

    seen = [r for r in records if isinstance(r, dict) and r.get("kind") == RECORD_KIND]
    head = "PF.3 checks after a write that ran the tests reaching its files first"
    if not seen:
        return [f"     -  {head}: not reached"]
    broke = [r for r in seen if int(r.get("broke") or 0)]
    seconds = [float(r.get("seconds") or 0) for r in seen]
    return [f"  {len(seen):>4}  {head} ({len(broke)} found a test the write broke; median {median(seconds):g} s)"]


__all__ = ["FAILING", "NAME", "ON_BY_DEFAULT", "OWN_FAILING", "RECORD_KIND", "SAID", "broken_now", "changed_files",
           "effects_lines", "enabled", "first", "reached", "said"]
