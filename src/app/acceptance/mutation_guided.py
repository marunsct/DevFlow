"""A deliberate change no test notices becomes a finding for the testing role to close (plan QM.2, behind `MUTATION_GUIDED_TESTS`).

The release probe (`app.acceptance.mutation`) already breaks the product on
purpose - a comparison turned round, a condition flipped, a constant moved by
one - and reports each change the locked suite did not notice. It runs once,
at release, and its survivors become a completion gap nobody acts on. Measured
on one finished run: the locked suite noticed 6 of 10 such changes, missing a
whitespace-only check and a connection setting, and the product shipped with
no test holding it to either.

With the switch on, the same probe runs when a sprint's due criteria all pass,
on the product's own source files that sprint changed, a few changes only and
only for a suite that drives no browser. A change neither the unit tests nor
the locked suite notices is one finding for the testing role: a unit test that
fails with the change and passes without it. The locked suite stays as it is;
no stage may edit it.

Settled without a model, as a language-service finding is asked again: the
harness makes that one change itself, runs the product's unit test command
(the stack contract's `unit_test`), and puts the file back. Settled only if
the unit tests fail with the change and pass without it. A change can behave
exactly as the original (an equivalent mutant), so the fixer may say so with a
reason, and the finding is closed as such. One the testing role cannot settle
within its tries is a completion gap, never an escalation: nothing the product
does is wrong.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Callable

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `MUTATION_GUIDED_TESTS` set to on or off overrides this.
ON_BY_DEFAULT = False
#: Changes tried per sprint, unless `MUTATION_GUIDED_TESTS_CHANGES` says otherwise.
CHANGES_PER_SPRINT = 6
#: Findings raised per sprint, at most: each is one fix stage of the testing role.
MOST_FINDINGS = 3
#: Fix stages one finding gets before it is a completion gap.
MOST_TRIES = 2
#: Which check raised the finding (`Defect.source`).
SOURCE = "mutation"
#: The role whose tests the finding asks for.
OWNER = "testing"
#: How a finding closed as a completion gap begins its reason.
A_GAP = "No unit test was made to notice it: "
#: How a finding the fixer judged equivalent begins its reason.
EQUIVALENT = "Equivalent, as the testing role judged it: "
#: What a fixer's decision begins with to say the change behaves the same.
_SAYS_EQUIVALENT = re.compile(r"^\s*equivalent\s*[:\-]\s*(?P<why>.+)$", re.I | re.S)
#: Words a reason for an equivalent change needs, at least: "it is" says nothing.
_A_REASON = 4


def enabled() -> bool:
    return is_on("MUTATION_GUIDED_TESTS", ON_BY_DEFAULT)


def changes_per_sprint() -> int:
    """`MUTATION_GUIDED_TESTS_CHANGES`, or `CHANGES_PER_SPRINT`; never below one."""
    try:
        return max(1, int(str(os.environ.get("MUTATION_GUIDED_TESTS_CHANGES") or CHANGES_PER_SPRINT).strip()))
    except ValueError:
        return CHANGES_PER_SPRINT


def is_a_finding(defect: Any) -> bool:
    return str(getattr(defect, "source", "") or "") == SOURCE


def _run_the_unit_tests(root: str | Path) -> set[str] | bool | None:
    """The unit tests that pass, by name from their reports; whether the command passed when no report names them.

    None when there is no command to run. By name, so a change is noticed beside a unit test that already fails:
    measured on every run of one day, the switch was on and never probed, because a test the model wrote always
    failed and the probe asked that all of them pass first.
    """
    from app.acceptance import junit
    from app.graph.workflow import _run_unit_tests_procedurally, _the_unit_reports
    from app.stacks import contract

    passed, _ = _run_unit_tests_procedurally(str(root))
    if passed is None:
        return None
    try:
        record = contract.read(root) or {}
        reports = [junit.read(path) for path in _the_unit_reports(str(root), record, list(record.get("unit_test") or []))]
    except Exception:  # noqa: BLE001 - the command's verdict stands
        reports = []
    named = [report for report in reports if report.found and report.tests]
    if not named:
        return passed
    return {test.name for report in named for test in report.tests if test.outcome == "passed"}


#: What a run that says only "all passed" counts as, among names.
_ALL = "(every unit test)"


def _passing(result: set[str] | bool | None) -> set[str] | None:
    """The tests a unit run passed, as names: `True` is all of them, `False` none, None unknown."""
    if result is None:
        return None
    if isinstance(result, bool):
        return {_ALL} if result else set()
    return set(result)


def _the_locked_suite(root: Path) -> Callable[[], set[str]] | None:
    """A runner of the locked suite returning the tests that passed; None when no suite is locked."""
    from app.acceptance import suite
    from app.acceptance.mutation import passing

    if not suite.is_locked(root):
        return None
    return lambda: passing(suite.run(root, save=False))


def _the_files_to_change(root: Path, project: Path, kept: set[str], changed: list[str]) -> list[Path]:
    """The product's own source files the sprint changed, as the release probe picks source files."""
    from app.acceptance.mutation import source_files

    named = {str(name).strip().replace("\\", "/").removeprefix("./").lstrip("/") for name in changed or []}
    return [path for path in source_files(project, kept) if path.relative_to(root).as_posix() in named]


def probe(
    repo_root: str | Path, changed: list[str], *, count: int | None = None,
    run_unit: Callable[[], set[str] | bool | None] | None = None,
    run_suite: Callable[[], set[str]] | None = None,
) -> list[dict]:
    """The deliberate changes no test noticed, each a site with the line it changed; [] when none or it cannot run.

    Neither the unit tests nor the locked suite (when one is locked): a change
    the suite notices is a behaviour a test already holds the product to.
    Changes the workspace in place, one file at a time, journalled first and
    put back in a `finally` - whatever the runner raises - so no change is
    ever left in the product. `run_unit` and `run_suite` are the runners, the
    contract's unit command and the locked suite by default. Never raises.
    """
    from app.acceptance import mutation

    root = Path(repo_root)
    try:
        from app.stacks import contract

        mutation.restore_an_interrupted_probe(root)
        found = contract.the_pack(root)
        if found is None or found[0].kind in mutation.BROWSER_KINDS:
            return []
        project = root / str(found[1].get("project") or "")
        files = _the_files_to_change(root, project, set(found[0].kept_files), changed)
        if not files:
            return []
        from app.acceptance import mutation_equivalents
        run_unit = run_unit or (lambda: _run_the_unit_tests(root))
        run_suite = run_suite if run_suite is not None else _the_locked_suite(root)
        before = _passing(run_unit())
        if not before:
            # A finding is settled by a unit test that passes without the change;
            # with none passing now, nothing could settle it.
            logger.info("Mutation-guided tests: no unit test passes now; nothing probed")
            return []
        held = run_suite() if run_suite is not None else set()
        # Without the changes already judged equivalent, so the few a sprint tries are changes worth asking about
        # (`EQUIVALENT_MUTANTS_REMEMBERED`).
        candidates = mutation_equivalents.without_the_known(root, project, mutation.sites(files, project))
        chosen = mutation.spread(candidates, count or changes_per_sprint())
    except Exception:  # noqa: BLE001 - a probe that cannot run finds nothing
        logger.debug("Could not probe what the tests notice", exc_info=True)
        return []
    survivors: list[dict] = []
    tried = 0
    for site in chosen:
        if len(survivors) >= MOST_FINDINGS:
            break
        path = project / site["file"]
        try:
            line = path.read_bytes().decode("utf-8").splitlines()[site["line"] - 1]
        except (OSError, UnicodeDecodeError, IndexError):
            continue
        original = mutation._journal_before_changing(root, project, site)
        tried += 1
        try:
            after = _passing(run_unit())
            noticed = after is None or bool(before - after)
            if not noticed and run_suite is not None:
                noticed = bool(held - run_suite())
        except Exception:  # noqa: BLE001 - an unmeasured change is no finding
            logger.debug("A change could not be measured", exc_info=True)
            continue
        finally:
            mutation._restore_and_close_the_journal(root, path, original)
        if not noticed:
            survivors.append({**site, "file": path.relative_to(root).as_posix(), "text": line})
    if tried:
        # The last unit run measured a changed product; its report should not
        # be the one left behind.
        try:
            run_unit()
        except Exception:  # noqa: BLE001 - the product is already as it was
            logger.debug("Could not run the unit tests after the probe", exc_info=True)
    logger.info("Mutation-guided tests: %d of %d deliberate change(s) went unnoticed", len(survivors), tried)
    return survivors


def _where(site: dict) -> str:
    return (f"`{site['file']}` line {site['line']}, column {site['column']}: "
            f"`{site['original']}` made `{site['replacement']}`")


def defect(site: dict, sprint_goal: str = "") -> Any:
    """One finding for the testing role, as the controller tracks it."""
    from app.sprint import Defect

    where = _where(site)
    return Defect(
        description=(
            f"No test notices a deliberate change to {where}. The unit tests and the acceptance "
            "suite all still pass with it, so no test holds the product to that behaviour."
        ),
        severity="minor",
        reproduction_steps=(
            f"In `{site['file']}` line {site['line']}, replace `{site['original']}` with "
            f"`{site['replacement']}` and run the product's unit tests: every one still passes. "
            "The harness put the line back as it was.\n"
            f"The line reads: {site.get('text', '')}"
        ),
        expected_behavior=(
            "A unit test that fails with that change and passes without it - one that checks "
            "what the product does where that line decides it."
        ),
        actual_behavior=(
            f"The unit tests pass whether the line has `{site['original']}` or `{site['replacement']}`."
        ),
        affected_files=[],
        owner=OWNER,
        # Settled by the harness's own check (`settled`), not by a named test.
        regression_test_required=False,
        source=SOURCE,
    )


def what_settles_it(defect: Any) -> str:
    """What the fixer of a finding is told settles it; "" for any other defect."""
    if not is_a_finding(defect):
        return ""
    return (
        "--- What settles this finding ---\n"
        "The product is not wrong here: its tests are too weak to notice the change described "
        "above. Add or strengthen a unit test in the product's own unit tests - not the locked "
        "acceptance suite, which no stage may edit - that checks the behaviour that line "
        "decides, so it fails with the change and passes on the code as it is now. Change no "
        "product file, and name the test in your `tests` field. The harness then makes the "
        "change itself, runs the unit tests and puts the line back: the finding is settled "
        "only if they fail with the change and pass without it.\n"
        "If the change cannot alter anything the product does - it behaves the same in every "
        "case - change nothing, and write one decision that begins `Equivalent:` and says why."
    )


_A_SITE = re.compile(
    r"`(?P<file>[^`]+)` line (?P<line>\d+), column (?P<column>\d+): `(?P<original>[^`]+)` made `(?P<replacement>[^`]+)`"
)
_THE_LINE = re.compile(r"^The line reads: (?P<text>.*)$", re.M)


def site_of(defect: Any) -> dict | None:
    """The change a finding describes, as a site; None when its text is not a finding's."""
    found = _A_SITE.search(str(getattr(defect, "description", "") or ""))
    if not found:
        return None
    line = _THE_LINE.search(str(getattr(defect, "reproduction_steps", "") or ""))
    return {
        "file": found["file"], "line": int(found["line"]), "column": int(found["column"]),
        "original": found["original"], "replacement": found["replacement"],
        "text": line["text"] if line else "",
    }


def _located(root: Path, site: dict) -> dict | None:
    """The site where the line stands now: at its number if unchanged, else the line with its text; None if gone.

    A fix that adds a line above it moves it; the change is the same change
    wherever the line now is.
    """
    try:
        lines = (root / site["file"]).read_bytes().decode("utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    column, original = site["column"], site["original"]

    def at(number: int, col: int) -> bool:
        return 1 <= number <= len(lines) and lines[number - 1][col:col + len(original)] == original

    text = site.get("text") or ""
    if at(site["line"], column) and (not text or lines[site["line"] - 1] == text):
        return site
    if not text:
        return None
    for number, line in enumerate(lines, start=1):
        if line.strip() == text.strip():
            moved = column + (len(line) - len(line.lstrip())) - (len(text) - len(text.lstrip()))
            if at(number, moved):
                return {**site, "line": number, "column": moved}
    return None


def settled(
    repo_root: str | Path, defect: Any, *, run_unit: Callable[[], set[str] | bool | None] | None = None,
) -> bool | None:
    """Whether the unit tests now fail with the finding's change and pass without it; None when it cannot say.

    Makes the change, runs the unit tests, puts the file back - in a
    `finally`, journalled first - then runs them again on the product as it
    is, so the run left behind measured the real product. Never raises.
    """
    from app.acceptance import mutation

    root = Path(repo_root)
    try:
        mutation.restore_an_interrupted_probe(root)
        site = site_of(defect)
        if site is None:
            return None
        site = _located(root, site)
        if site is None:
            return None
        run_unit = run_unit or (lambda: _run_the_unit_tests(root))
        original = mutation._journal_before_changing(root, root, site)
        try:
            with_the_change = run_unit()
        finally:
            mutation._restore_and_close_the_journal(root, root / site["file"], original)
        without_it = run_unit()
    except Exception:  # noqa: BLE001 - unmeasured is not settled
        logger.debug("Could not check a mutation finding", exc_info=True)
        return None
    with_the_change, without_it = _passing(with_the_change), _passing(without_it)
    if with_the_change is None or without_it is None:
        return None
    # A unit test that passes without the change and fails with it, whatever else fails.
    return bool(without_it - with_the_change)


def equivalent_because(fix_result: Any) -> str:
    """The fixer's reason the change behaves the same as the original; "" when it gave none."""
    from app.acceptance import mutation_equivalents

    # The usual spellings of the verdict, not only the one prefix the request names (`EQUIVALENT_MUTANTS_REMEMBERED`).
    normalised = mutation_equivalents.enabled()
    for said in [*(getattr(fix_result, "decisions", None) or []), *(getattr(fix_result, "blockers", None) or [])]:
        found = _SAYS_EQUIVALENT.match(str(said or ""))
        why = found["why"] if found else (mutation_equivalents.says_equivalent(said) if normalised else "")
        if why and len(why.split()) >= _A_REASON:
            return " ".join(why.split())[:400]
    return ""


def the_gap(defect: Any) -> str:
    """The completion gap a finding closed unsettled leaves; "" for any other."""
    reason = str(getattr(defect, "accepted_risk_reason", "") or "")
    if not is_a_finding(defect) or getattr(defect, "status", "") != "accepted_risk" or not reason.startswith(A_GAP):
        return ""
    site = site_of(defect)
    where = _where(site) if site else str(getattr(defect, "description", "") or "")[:200]
    return f"No test holds the product to a behaviour a deliberate change showed: {where}. {reason}"


__all__ = [
    "A_GAP", "CHANGES_PER_SPRINT", "EQUIVALENT", "MOST_FINDINGS", "MOST_TRIES", "ON_BY_DEFAULT", "OWNER",
    "SOURCE", "changes_per_sprint", "defect", "enabled", "equivalent_because", "is_a_finding", "probe",
    "settled", "site_of", "the_gap", "what_settles_it",
]
