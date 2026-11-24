"""Which locked acceptance tests a run of the suite takes during a sprint, and in what order (LF.1265).

Measured on a medium brief: the whole suite was locked before any code and all of it ran at every measurement of every
sprint, the 53 tests not due until sprint 3 included. They ran first, because their files sorted first, and spent the
product's sign-up allowance before sprint 1's own tests reached it. A sprint answers for its own criteria and every
earlier sprint's; nothing else it is measured on can tell it anything.

So while a sprint is built, a run of the suite takes only the due tests - those carrying a criterion due now - with the
earliest sprint's files first where the runner keeps the order it is given. A pack says how its runner is asked for
that (`StackPack.acceptance_selection`); a pack that cannot ask runs the whole suite, as before, and what the run
reports of tests not yet due is set aside all the same. The last sprint and the release take every test. A product
planned as one sprint is run exactly as it always was.

Nothing here runs anything: `choose` decides from the recorded sprint scope and the suite's declared tests, and
`suite.run` acts on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from app.acceptance import junit

#: A pack's way to ask its runner for some tests: (the suite's command, the ids whose tests run - () for every test,
#: the suite's files relative to the project in the order to run them - () to keep the runner's own) -> the command
#: that runs them, or None when this runner cannot be asked (the whole suite runs).
Selecting = Callable[[Sequence[str], Sequence[str], Sequence[str]], "tuple[str, ...] | None"]


@dataclass(frozen=True)
class Selection:
    """What one run of the suite takes."""

    #: The criterion and change-request ids whose tests run; () for every test.
    due: tuple[str, ...]
    #: The suite's files, relative to the project, earliest sprint's first; () to keep the runner's own order.
    files: tuple[str, ...]
    #: The criteria a later sprint delivers: their tests are not run, and not counted.
    not_yet_due: tuple[str, ...]


def choose(
    *,
    not_yet_due: Sequence[str],
    sprints: Sequence[Sequence[str]],
    tests: Sequence[tuple[str, Sequence[str]]],
) -> Selection | None:
    """What a run takes; None when it is the whole suite in the runner's own order - as a run always was.

    `tests` is (file relative to the project, the ids its name carries) for every test the suite declares. Only the
    due tests run while anything is not yet due - and only when some test carries a due criterion, since a run that
    holds no test proves nothing. With everything due, the files are put in sprint order when the plan has more than
    one sprint and that order differs from the runner's.
    """
    later = {str(item) for item in not_yet_due or ()}
    rank = {item: index for index, group in enumerate(sprints or ()) for item in group}
    last = len(sprints or ())
    ranked: dict[str, int] = {}
    holds_a_due_test: set[str] = set()
    due_ids: list[str] = []
    for file, tags in tests:
        carried = [str(tag) for tag in tags]
        due_here = [tag for tag in carried if tag not in later]
        if due_here:
            holds_a_due_test.add(file)
            due_ids.extend(tag for tag in due_here if tag not in due_ids)
        ranked[file] = min(ranked.get(file, last), *(rank.get(tag, last) for tag in carried or [""]))
    if later:
        if not holds_a_due_test:
            return None
        files = sorted(holds_a_due_test, key=lambda name: (ranked.get(name, last), name))
        return Selection(due=tuple(due_ids), files=tuple(files), not_yet_due=tuple(sorted(later)))
    if sum(1 for group in sprints or () if group) < 2:
        return None
    files = sorted(ranked, key=lambda name: (ranked[name], name))
    if files == sorted(ranked):
        return None
    return Selection(due=(), files=tuple(files), not_yet_due=())


def carried_only_by_later_sprints(tags: Sequence[str], not_yet_due: Sequence[str]) -> bool:
    """Whether a test with these ids is a later sprint's alone: it names criteria, and none of them is due."""
    later = set(not_yet_due or ())
    return bool(tags) and all(tag in later for tag in tags)


def without_the_not_yet_due(report: junit.Report, not_yet_due: Sequence[str]) -> junit.Report:
    """`report` without the tests that are a later sprint's alone: a runner that cannot be asked ran them anyway."""
    if not not_yet_due:
        return report
    kept = [test for test in report.tests if not carried_only_by_later_sprints(test.tags, not_yet_due)]
    if len(kept) == len(report.tests):
        return report
    return junit.Report(tests=kept, found=report.found)


def held(report: junit.Report, selection: Selection, covered: dict[str, list[str]]) -> bool:
    """Whether a run that asked for `selection` reported what it asked for.

    A runner that matched fewer tests than were due - a name the filter did not read as the harness does - would make
    a due criterion read "untested", and its tests would be written again. Then the whole suite is run instead.
    """
    if not report.tests:
        return False
    reported = {tag for test in report.tests for tag in test.tags}
    return all(item in reported for item in selection.due if covered.get(item))


__all__ = ["Selecting", "Selection", "carried_only_by_later_sprints", "choose", "held", "without_the_not_yet_due"]
