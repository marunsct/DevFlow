"""The acceptance suite: where it lives, locking it, running it, reading it.

The suite is written by the QA stage from the numbered criteria, reviewed, and
then locked: its files are copied to `.harness/acceptance-snapshot/` with their
checksums, every write tool refuses to change them, and anything that changes
them anyway (a shell command, say) is put back before each run. Only the QA
stage, reopened through a recorded change, may change it again.

The harness runs it - the pack's command, or the command a QA stage declared
for a stack no pack covers - and reads the JUnit report, so "which criteria
pass" is decided by the runner's record and never by a model's summary of it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Sequence

from app.acceptance import junit
from app.acceptance.criteria import Criterion, from_records
from app.stacks import contract

logger = logging.getLogger(__name__)

STATE_FILE = f"{contract.HARNESS_DIR}/acceptance.json"
SNAPSHOT_DIR = f"{contract.HARNESS_DIR}/acceptance-snapshot"
#: Every version of the suite that was ever locked, `v1`, `v2`, ..., each next
#: to `vN.diff` - what changed from the version before. A lock replaces the
#: snapshot, so when QA repaired a reopened suite nothing showed what it
#: changed: one run's repair rewrote nine tests and no record said how.
LOCKS_DIR = f"{contract.HARNESS_DIR}/acceptance-locks"
RESULT_FILE = f"{contract.HARNESS_DIR}/acceptance-result.json"

#: The file a QA stage writes, for a stack no pack covers, to say how its
#: suite runs: {"command": [...], "report": "path/to/junit.xml"}.
DECLARED_COMMAND_FILE = "run.json"

#: Directories inside the acceptance directory that are a runner's or an
#: interpreter's, not the suite's.
_NOT_THE_SUITE = frozenset({"__pycache__", "node_modules", ".pytest_cache", "test-results"})

OUTPUT_TAIL_CHARS = 3_000

Runner = Callable[[Sequence[str], str, str], dict[str, Any]]


# --- where it lives ---------------------------------------------------------

def _state(repo_root: str | Path) -> dict[str, Any]:
    try:
        data = json.loads((Path(repo_root) / STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_state(repo_root: str | Path, data: dict[str, Any]) -> None:
    path = Path(repo_root) / STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def location(repo_root: str | Path) -> tuple[str, str] | None:
    """(project directory, acceptance directory inside it), or None."""
    record = contract.read(repo_root)
    if record:
        return str(record.get("project") or ""), str(record.get("acceptance_dir") or "acceptance")
    state = _state(repo_root)
    if state.get("project"):
        return str(state["project"]), str(state.get("acceptance_dir") or "acceptance")
    try:
        from app.tools.repository import pinned_project_directory

        project = pinned_project_directory(Path(repo_root))
    except Exception:  # noqa: BLE001
        project = None
    return (project, "acceptance") if project else None


def directory(repo_root: str | Path) -> Path | None:
    where = location(repo_root)
    if where is None:
        return None
    project, acceptance_dir = where
    return Path(repo_root) / project / acceptance_dir


def relative_directory(repo_root: str | Path) -> str:
    where = location(repo_root)
    return f"{where[0]}/{where[1]}" if where else ""


def suite_files(repo_root: str | Path) -> list[Path]:
    """The files the suite is made of: never its runner's report.

    A suite may write its JUnit report beside its tests. Locked with them,
    every run rewrote a locked file: measured on one run, each run of the
    suite was followed by "acceptance suite restored", the report put back
    as it was when the suite was locked.
    """
    root = directory(repo_root)
    if root is None or not root.is_dir():
        return []
    report = _the_report(repo_root)
    from app.analysis.walk import files_under

    return sorted(
        path for path in files_under(root, _NOT_THE_SUITE)
        if path.is_file() and not (set(path.relative_to(root).parts) & _NOT_THE_SUITE)
        and path != report
    )


def _the_report(repo_root: str | Path) -> Path | None:
    """Where the suite's runner writes its report, or None."""
    try:
        command = _command(repo_root)
    except Exception:  # noqa: BLE001 - an unreadable declaration declares no report
        return None
    if command is None:
        return None
    _, report, project = command
    return Path(repo_root) / project / report


# --- criteria ---------------------------------------------------------------

def save_criteria(
    repo_root: str | Path, criteria: list[Criterion], deferred: dict[str, str] | None = None
) -> None:
    from app.acceptance.criteria import as_records, render

    state = _state(repo_root)
    where = location(repo_root)
    if where:
        state["project"], state["acceptance_dir"] = where
    state["criteria"] = as_records(criteria)
    state["deferred"] = dict(deferred or state.get("deferred") or {})
    _save_state(repo_root, state)
    doc = Path(repo_root) / "docs" / "acceptance_criteria.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(render(criteria, state["deferred"]), encoding="utf-8")


def criteria(repo_root: str | Path) -> list[Criterion]:
    return from_records(_state(repo_root).get("criteria"))


def deferred(repo_root: str | Path) -> dict[str, str]:
    return dict(_state(repo_root).get("deferred") or {})


def defer(repo_root: str | Path, reasons: dict[str, str]) -> None:
    """Record criteria that will not be proven by the suite, each with why."""
    if not reasons:
        return
    current = criteria(repo_root)
    merged = {**deferred(repo_root), **reasons}
    save_criteria(repo_root, current, merged)


# --- coverage ---------------------------------------------------------------

#: A test declared with a free-text title: `test('[AC-3] ...')`, `it("...")`,
#: `test.describe('...')`, Go/Rust/Java names are identifiers like Python's.
_TITLED = re.compile(r"""\b(?:test|it|describe|scenario)(?:\.\w+)*\(\s*(['"`])(.+?)\1""")
_NAMED = re.compile(r"\b(?:def|func|fn|void|function)\s+(\w*(?:test|Test|TEST)\w*)")


def declared_tests(repo_root: str | Path) -> list[tuple[str, str]]:
    """(file, test name) for every test the suite's files declare."""
    root = Path(repo_root)
    found: list[tuple[str, str]] = []
    for path in suite_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        shown = path.relative_to(root).as_posix()
        for match in _TITLED.finditer(text):
            found.append((shown, match.group(2)))
        for match in _NAMED.finditer(text):
            found.append((shown, match.group(1)))
    return found



#: A runner's progress line: one mark per finished test, perhaps a percentage.
_PROGRESS_LINE = re.compile(r"^([.FEsxX]+)\s*(?:\[\s*\d+%\])?$")


def the_test_that_did_not_finish(repo_root: str | Path, output: str) -> str:
    """The test running when the suite was stopped - after the last one its progress marks - or "".

    One run's suite timed out with `FFF.F.F.FFF.` and nothing else: twelve
    tests had finished, the thirteenth ran the product's start script and never
    returned, and QA, not told which, decided the product was missing. Only
    for a runner that prints a mark per test, in the order the files declare.
    """
    marks = sum(
        len(match.group(1))
        for line in (output or "").splitlines()
        if (match := _PROGRESS_LINE.match(line.strip()))
    )
    tests = declared_tests(repo_root)
    if not marks or marks >= len(tests):
        return ""
    where, name = tests[marks]
    return f"`{name}` in `{where}`"


#: A finding that a test fails because the product does not have something yet.
_THE_PRODUCT_LACKS = re.compile(
    r"\b(?:(?:is|are)\s+not\s+(?:yet\s+)?implemented|not\s+yet\s+(?:implemented|built)|"
    r"(?:fails?|failing|returns?|answers?)\s+(?:with\s+)?(?:a\s+)?404|has\s+not\s+been\s+built)\b",
    re.I,
)
#: A finding about the test itself, which stays whatever else it says.
_THE_TEST_IS_AT_FAULT = re.compile(
    r"\b(?:assert\w*|weak|lenient|too\s+loose|wrong\s+(?:thing|criterion|endpoint|status)|contradict\w*|"
    r"no\s+test|missing\s+(?:a\s+)?test|named?|should\s+(?:check|test|assert|expect)|expects?\s+the\s+wrong|"
    r"flak\w*|never\s+(?:fails|finishes|returns))\b",
    re.I,
)


def findings_about_the_suite(findings: list[str]) -> list[str]:
    """The review findings that are about the tests: one saying only that a test fails because the product lacks it is dropped.

    The suite is written before the product, and its tests are meant to fail
    now. One run's QA lead sent the suite back with fifteen findings, every one
    "test_acN fails with 404 because ... is not implemented", and QA, sent back
    with them, tried again to write the product. A finding that also faults the
    test - a weak assertion, a wrong name, a contradiction - is kept.
    """
    return [
        finding for finding in findings
        if not _THE_PRODUCT_LACKS.search(finding) or _THE_TEST_IS_AT_FAULT.search(finding)
    ]

def coverage(repo_root: str | Path) -> dict[str, list[str]]:
    """Each criterion and change-request id, with the names of the tests that carry it."""
    covered: dict[str, list[str]] = {}
    for _, name in declared_tests(repo_root):
        for tag in junit.tags_in(name):
            covered.setdefault(tag, []).append(name)
    return covered


def gaps(repo_root: str | Path) -> list[str]:
    """Problems with the suite as written: criteria nothing tests, ids nothing defines."""
    known = {c.id for c in criteria(repo_root)}
    excused = set(deferred(repo_root))
    covered = coverage(repo_root)
    problems = [
        f"{c.id} (\"{c.text}\") has no test whose name carries `{c.id}`. "
        f"Write a test for it - or, where a test already checks exactly what it says, add its id to that "
        "test's name as the naming rule says."
        for c in criteria(repo_root)
        if c.id not in covered and c.id not in excused
    ]
    change_requests = set(_state(repo_root).get("change_requests") or [])
    for tag, names in sorted(covered.items()):
        if tag.startswith("AC-") and tag not in known:
            problems.append(f"`{names[0]}` names {tag}, which is not a criterion of this product.")
        if tag.startswith("CR-") and tag not in change_requests:
            problems.append(f"`{names[0]}` names {tag}, which is not an open change request.")
    return problems


# --- the lock ---------------------------------------------------------------

def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lock(repo_root: str | Path) -> dict[str, str]:
    """Freeze the suite as it stands, keeping it as a new version. Returns {relative path: checksum}."""
    root = Path(repo_root)
    snapshot = root / SNAPSHOT_DIR
    before = _the_files_of(snapshot)
    shutil.rmtree(snapshot, ignore_errors=True)
    checksums: dict[str, str] = {}
    for path in suite_files(repo_root):
        relative = path.relative_to(root).as_posix()
        checksums[relative] = _digest(path)
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    state = _state(repo_root)
    state["lock"] = checksums
    state["lock_version"] = _keep_this_version(root, snapshot, before)
    state.pop("repairing", None)
    _save_state(repo_root, state)
    return checksums


def repairing(repo_root: str | Path, tests: list[str]) -> None:
    """Record the tests a reopened suite is being repaired for, until it is locked again."""
    state = _state(repo_root)
    state["repairing"] = sorted({*state.get("repairing", []), *(str(t) for t in tests if str(t).strip())})
    _save_state(repo_root, state)


def _declared_in(text: str) -> set[str]:
    return {m.group(2) for m in _TITLED.finditer(text or "")} | {m.group(1) for m in _NAMED.finditer(text or "")}


def _skipped_in(text: str) -> set[str]:
    return {m.group(2) for m in _WRITTEN_SKIPPED.finditer(text or "")}


def tests_a_repair_would_drop(repo_root: str | Path, relative_path: str, content: str) -> list[str]:
    """The tests this file had when the suite was last locked that `content` drops, other than those under repair.

    Only while a reopened suite is being repaired. One run's repair, sent for
    one test, wrote the file back with that test alone in it: the seventeen
    other criteria lost their tests, and the suite went back for all of them.
    """
    state = _state(repo_root)
    if "lock" in state or "repairing" not in state:
        return []
    locked_version = Path(repo_root) / SNAPSHOT_DIR / relative_path
    if not locked_version.is_file():
        return []
    try:
        locked_text = locked_version.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    # A skipped stub holds no check to keep, and a test made into one is removed: measured on one run, a repair
    # refused for removing tests wrote them back as empty `test.skip(...)`, and was then refused removing those.
    before = _declared_in(locked_text) - _skipped_in(locked_text)
    under_repair = set(state.get("repairing") or [])
    return sorted(
        name for name in before - (_declared_in(content) - _skipped_in(content))
        if not any(name == test or name in test or test in name for test in under_repair)
    )


def _the_files_of(directory: Path) -> dict[str, str]:
    """{path relative to `directory`: text} for every file under it; {} if there is none."""
    if not directory.is_dir():
        return {}
    return {
        path.relative_to(directory).as_posix(): path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(directory.rglob("*")) if path.is_file()
    }


def _keep_this_version(root: Path, snapshot: Path, before: dict[str, str]) -> int:
    """Copy the snapshot just taken to the next version, with its diff from `before`. Never raises."""
    import difflib

    try:
        versions = root / LOCKS_DIR
        number = 1 + max(
            (int(path.name[1:]) for path in versions.glob("v*") if path.is_dir() and path.name[1:].isdigit()),
            default=0,
        )
        shutil.copytree(snapshot, versions / f"v{number}")
        if number > 1:
            after = _the_files_of(snapshot)
            diff = "".join(
                line
                for name in sorted(set(before) | set(after))
                for line in difflib.unified_diff(
                    before.get(name, "").splitlines(keepends=True),
                    after.get(name, "").splitlines(keepends=True),
                    fromfile=f"v{number - 1}/{name}", tofile=f"v{number}/{name}",
                )
            )
            (versions / f"v{number}.diff").write_text(diff, encoding="utf-8")
        return number
    except Exception:  # noqa: BLE001 - the lock stands without its history
        return 0


def changes_at_this_lock(repo_root: str | Path) -> str:
    """What the version locked last changed from the one before: a count and the diff; "" for the first."""
    number = int(_state(repo_root).get("lock_version") or 0)
    path = Path(repo_root) / LOCKS_DIR / f"v{number}.diff"
    if number < 2 or not path.is_file():
        return ""
    diff = path.read_text(encoding="utf-8", errors="replace")
    added = sum(1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---"))
    if not diff.strip():
        return f"Locked as version {number}, unchanged from version {number - 1}."
    return (
        f"Locked as version {number}: {added} line(s) added and {removed} removed since version "
        f"{number - 1} ({LOCKS_DIR}/v{number}.diff).\n{diff}"
    )


def unlock(repo_root: str | Path) -> None:
    """Open the suite for its QA stage. The snapshot stays until the next lock."""
    state = _state(repo_root)
    if state.pop("lock", None) is not None:
        _save_state(repo_root, state)


def is_locked(repo_root: str | Path) -> bool:
    return "lock" in _state(repo_root)


def is_protected(repo_root: str | Path, relative_path: str) -> bool:
    """Whether a workspace-relative path is inside the locked suite."""
    if not is_locked(repo_root):
        return False
    where = relative_directory(repo_root)
    if not where:
        return False
    path = relative_path.strip().lstrip("/").replace("\\", "/")
    return path == where or path.startswith(where + "/")


def restore(repo_root: str | Path) -> list[str]:
    """Put the locked suite back as it was locked. One line per repair."""
    state = _state(repo_root)
    checksums: dict[str, str] = state.get("lock") or {}
    if not checksums:
        return []
    root = Path(repo_root)
    snapshot = root / SNAPSHOT_DIR
    repairs: list[str] = []
    # A suite locked before its report was left out of it still lists it.
    report = _the_report(repo_root)
    for relative, wanted in checksums.items():
        target = root / relative
        source = snapshot / relative
        if target == report or (target.is_file() and _digest(target) == wanted):
            continue
        if not source.is_file():
            continue
        existed = target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        repairs.append(f"{relative} was {'changed' if existed else 'removed'}; the locked version is back.")
    for path in suite_files(repo_root):
        relative = path.relative_to(root).as_posix()
        if relative not in checksums:
            path.unlink(missing_ok=True)
            repairs.append(f"{relative} was added to the locked suite and has been removed.")
    if repairs:
        logger.warning("Acceptance suite restored: %s", "; ".join(repairs))
    return repairs


# --- running it -------------------------------------------------------------

@dataclass
class CriterionResult:
    id: str
    text: str
    status: str  # passed | failed | untested | deferred
    tests: list[dict[str, str]] = field(default_factory=list)


@dataclass
class AcceptanceResult:
    ran: bool
    exit_code: int = 1
    command: str = ""
    report: junit.Report = field(default_factory=junit.Report)
    criteria: dict[str, CriterionResult] = field(default_factory=dict)
    change_requests: dict[str, CriterionResult] = field(default_factory=dict)
    output: str = ""
    repairs: list[str] = field(default_factory=list)
    problem: str = ""
    #: What the product itself reported going wrong while the suite ran - a
    #: page's uncaught errors - from the pack's `runtime_report`.
    runtime_problems: list[str] = field(default_factory=list)
    #: What the product shows a person before any test touches it (a page's
    #: accessibility tree), from the same report; "" when not recorded.
    shows: str = ""
    #: How many pixels wider than a phone's screen (375px) the page is, from
    #: the same report; 0 when it fits or was not measured.
    phone_overflow: int = 0
    #: At a phone's width: controls drawn over each other, and ones under 24x24px (Initiative B).
    overlaps: list[str] = field(default_factory=list)
    small_targets: list[str] = field(default_factory=list)
    #: The serious and critical rules an accessibility engine found broken on
    #: the page as it loads - id, impact, help, count, where - from the same
    #: report; [] when none, or when it could not run.
    accessibility: list[dict[str, Any]] = field(default_factory=list)

    def failing(self, ids: Sequence[str] | None = None) -> list[CriterionResult]:
        wanted = set(ids) if ids is not None else None
        return [
            result for result in [*self.criteria.values(), *self.change_requests.values()]
            if result.status in {"failed", "untested"} and (wanted is None or result.id in wanted)
        ]

    def passing_ids(self) -> set[str]:
        return {
            result.id for result in [*self.criteria.values(), *self.change_requests.values()]
            if result.status == "passed"
        }

    def summary(self, ids: Sequence[str] | None = None) -> str:
        """A table of criteria and their status, for briefs and reviews."""
        if not self.ran:
            return f"The acceptance suite did not run: {self.problem or 'no report was written.'}"
        rows = []
        wanted = set(ids) if ids is not None else None
        for result in [*self.criteria.values(), *self.change_requests.values()]:
            if wanted is not None and result.id not in wanted:
                continue
            line = f"- {result.id} {result.status.upper()}: {result.text}"
            for test in result.tests:
                if test.get("outcome") == "failed":
                    message = test.get("message", "").strip().splitlines()
                    line += f"\n    failed: {test.get('name')} - {(message[0] if message else '')[:300]}"
                    page = page_it_failed_on(test.get("message", ""))
                    if page:
                        line += "\n    the page when it failed:\n" + "\n".join(
                            f"      {row}" for row in page.splitlines()
                        )
            rows.append(line)
        head = (
            f"Acceptance suite (`{self.command}`): {self.report.passed} passed, "
            f"{self.report.failed} failed, {self.report.skipped} skipped."
        )
        return head + self.runtime_note() + ("\n" + "\n".join(rows) if rows else "")

    def runtime_note(self) -> str:
        """What the product reported and showed by itself, before any test touched it, or ""."""
        note = ""
        if self.runtime_problems:
            note += (
                "\nBefore any test touched it, the product itself reported (fix these first: code "
                "that throws while the product loads stops everything after it, and the tests then "
                "fail for no reason of their own):\n"
                + "\n".join(f"  - {problem}" for problem in self.runtime_problems)
            )
        if self.shows and self.report.failed:
            note += (
                "\nWhat the product shows when it loads, before any test touches it - the tree the "
                "tests' locators search, so a control a test cannot find is absent here or named "
                "differently here:\n" + self.shows
            )
        return note

    def as_dict(self) -> dict[str, Any]:
        return {
            "ran": self.ran,
            "exit_code": self.exit_code,
            "command": self.command,
            "passed": self.report.passed,
            "failed": self.report.failed,
            "skipped": self.report.skipped,
            "criteria": {k: vars(v) for k, v in self.criteria.items()},
            "change_requests": {k: vars(v) for k, v in self.change_requests.items()},
            "repairs": self.repairs,
            "problem": self.problem,
            # What the runner said: a problem that reads "its output is below"
            # was saved with no output, and its cause had to be found by
            # running the command again by hand.
            "output": self.output,
            "runtime_problems": self.runtime_problems,
            "shows": self.shows,
            "phone_overflow": self.phone_overflow,
            "overlaps": self.overlaps,
            "small_targets": self.small_targets,
            "accessibility": self.accessibility,
        }


def _command(repo_root: str | Path) -> tuple[list[str], str, str] | None:
    """(argv, report path relative to the project, project) for this run's suite."""
    found = contract.the_pack(repo_root)
    if found is not None:
        pack, record = found
        return list(record.get("acceptance_test") or pack.acceptance_test), pack.acceptance_report, str(record.get("project"))
    suite_dir = directory(repo_root)
    where = location(repo_root)
    if suite_dir is None or where is None:
        return None
    try:
        declared = json.loads((suite_dir / DECLARED_COMMAND_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    argv = declared.get("command") if isinstance(declared, dict) else None
    report = declared.get("report") if isinstance(declared, dict) else None
    if not (isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv) and isinstance(report, str)):
        return None
    return argv, report, where[0]


#: The shape a suite's own declaration of how it runs must have.
_THE_DECLARED_SHAPE = '{"command": ["<executable>", "<argument>", ...], "report": "<file>"}'


def _what_the_declaration_gets_wrong(declared: Any) -> str:
    """What makes a parsed `run.json` unusable, naming the shape; "" when nothing does."""
    if not isinstance(declared, dict):
        return f"must be one JSON object, {_THE_DECLARED_SHAPE}"
    wrong: list[str] = []
    argv = declared.get("command")
    if not (isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv)):
        wrong.append(
            "`command` must be one command as a list of strings"
            + (" - not a `commands` list: when the suite needs several runners, one script runs "
               "them all and writes one report, and `command` runs that script"
               if "commands" in declared else "")
        )
    report = declared.get("report")
    if not isinstance(report, str) or not report.strip() or report.rstrip().endswith("/"):
        wrong.append("`report` must be the path of one JUnit XML file the command writes, relative to the project")
    return ("; ".join(wrong) + f". The shape is {_THE_DECLARED_SHAPE}") if wrong else ""


def problems_with_the_declared_command(text: str) -> str:
    """What makes a `run.json` about to be written unusable; "" if nothing. Checked as it is written."""
    try:
        declared = json.loads(text)
    except ValueError as error:
        return f"it is not valid JSON ({error}); it must be {_THE_DECLARED_SHAPE}"
    return _what_the_declaration_gets_wrong(declared)


def _why_no_command(repo_root: str | Path) -> str:
    """Why no command is known for this suite, naming what to change; never raises.

    "no command is known for this suite" was the whole of it. Measured on one
    run whose setup was left to the agents: the suite's `run.json` held a
    `commands` list of two runners and a report directory, and QA was sent back
    twice with that sentence and nothing it could act on.
    """
    base = "no command is known for this suite"
    try:
        suite_dir = directory(repo_root)
        if suite_dir is None or location(repo_root) is None:
            return base + ": no acceptance directory is set up for it yet"
        where = suite_dir / DECLARED_COMMAND_FILE
        shown = where.relative_to(Path(repo_root)).as_posix()
        if not where.is_file():
            return f"{base}: `{shown}` is not written; it says how the suite runs, as {_THE_DECLARED_SHAPE}"
        try:
            declared = json.loads(where.read_text(encoding="utf-8"))
        except ValueError as error:
            return f"{base}: `{shown}` is not valid JSON ({error}); it must be {_THE_DECLARED_SHAPE}"
        wrong = _what_the_declaration_gets_wrong(declared)
        if wrong:
            return f"{base}: `{shown}` {wrong}"
    except Exception:  # noqa: BLE001 - the short answer is still an answer
        return base
    return base


def _sandbox_runner(repo_root: str | Path) -> Runner:
    from app.stacks.scaffold import sandbox_runner

    return sandbox_runner(repo_root)


def run(repo_root: str | Path, *, runner: Runner | None = None, save: bool = True) -> AcceptanceResult:
    """Run the suite the way the harness always does, and read what it proved."""
    repairs = restore(repo_root)
    try:
        repairs += contract.enforce(repo_root)
    except Exception:  # noqa: BLE001 - a repair that fails leaves the run as it was
        logger.debug("Could not enforce the project contract", exc_info=True)
    # Kept with the run's repairs: an install that failed is why nothing it
    # declares is there, and the round raises it (`acceptance_nodes`).
    repairs += contract.install_if_the_manifests_changed(repo_root, runner)
    command = _command(repo_root)
    if command is None:
        result = AcceptanceResult(ran=False, repairs=repairs, problem=_why_no_command(repo_root))
        return _judged(repo_root, result, save)
    argv, report_path, project = command
    report_file = Path(repo_root) / project / report_path
    if not repairs:
        # Nothing was put back or installed, and the product is as it was when last measured: that run stands (MEASURE_ONCE).
        from app.acceptance.measured_once import saved_run_if_unchanged

        kept = saved_run_if_unchanged(repo_root, " ".join(argv), report_file)
        if kept is not None:
            return _judged(repo_root, kept, save)
    junit.clear(report_file)
    runtime_file = _runtime_report(repo_root, project)
    if runtime_file is not None:
        runtime_file.unlink(missing_ok=True)
    outcome = (runner or _sandbox_runner(repo_root))(argv, "test", project)
    try:
        code = int(str(outcome.get("returncode", "1")).strip() or 1)
    except ValueError:
        code = 1
    output = "\n".join(str(outcome.get(k) or "") for k in ("error", "stdout", "stderr") if outcome.get(k))
    report = junit.read(report_file)
    result = AcceptanceResult(
        ran=report.found,
        exit_code=code,
        command=" ".join(argv),
        report=report,
        output=output[-OUTPUT_TAIL_CHARS:],
        repairs=repairs,
        problem="" if report.found else "the runner wrote no report; its output is below",
    )
    if not report.tests:
        # No test ran because the product never started: the suite is not at
        # fault, and the product's own error is the defect (`the_product_did_not_start`).
        never_started = the_product_did_not_start(output, repo_root)
        if never_started:
            result.problem = never_started
    else:
        # Every test ran and each that failed did so because the service it
        # starts never came up: the same one cause (`every_failure_is_the_start`).
        never_started = every_failure_is_the_start(report, repo_root)
        if never_started:
            result.problem = never_started
    result.runtime_problems, result.shows = _read_runtime_report(runtime_file)
    result.phone_overflow = _read_phone_overflow(runtime_file)
    result.overlaps, result.small_targets = _read_layout_findings(runtime_file)
    result.accessibility = _read_accessibility(runtime_file)
    _with_the_pages_they_failed_on(repo_root, project, result)
    _with_the_errors_the_service_logged(repo_root, project, result)
    return _judged(repo_root, result, save)


#: How much of the page a failing test met is kept with it, and for how many
#: failing tests: enough to see what was there, bounded so a red suite's
#: summary stays readable.
FAILURE_PAGE_CHARS = 900
MOST_FAILURE_PAGES = 8


#: Where a failing test's message carries the page it failed on.
_PAGE_MARK = "\nWhat the page showed when this failed:\n"


def page_it_failed_on(message: str) -> str:
    """The page a failing test met, from its message, or ""."""
    text = str(message or "")
    return text.split(_PAGE_MARK, 1)[1].strip() if _PAGE_MARK in text else ""


def _with_the_pages_they_failed_on(repo_root: str | Path, project: str, result: AcceptanceResult) -> None:
    """Add to each failing test what the product showed when it failed, where the pack can tell.

    "Element not found" cannot say whether a control is absent, misnamed, or
    never appeared after the action before it; the page at that moment does.
    Never raises.
    """
    found = contract.the_pack(repo_root)
    if found is None or found[0].failure_pages is None:
        return
    pack = found[0]
    try:
        pages = pack.failure_pages(Path(repo_root) / project, pack.evidence_dir or "test-results")
    except Exception:  # noqa: BLE001 - the failures stand without their pages
        return
    if not pages:
        return
    tests = []
    added = 0
    for test in result.report.tests:
        page = (
            pages.get(test.name) or pages.get(test.name.split(" › ")[-1].strip())
            if test.outcome == "failed" and added < MOST_FAILURE_PAGES else None
        )
        if page:
            added += 1
            near = _a_near_miss(pack, test.message, page)
            test = replace(test, message=(
                f"{test.message}{_PAGE_MARK}{page[:FAILURE_PAGE_CHARS]}{near}"
            ))
        tests.append(test)
    result.report = replace(result.report, tests=tests)


#: Where a pack's acceptance setup writes what the service printed while the suite ran.
SERVICE_LOG = "test-results/service.log"
MOST_SERVICE_ERRORS = 2
_A_TRACEBACK = "Traceback (most recent call last):"
_A_SERVER_ERROR = re.compile(r"\b50\d\b|Internal Server Error", re.I)
_AN_EXCEPTION_LINE = re.compile(r"^[A-Za-z_][\w.]*(?:Error|Exception|Exit|Warning)\b.*$")
_SERVICE_ERRORS_MARK = "\nThe service logged this while the suite ran:\n"


def the_errors_a_service_logged(repo_root: str | Path, project: str) -> list[str]:
    """The last distinct errors the service logged, each as its exception line and where in the project it was raised.

    A test that meets a 500 learns only that the service failed; the traceback the service printed names the cause
    (measured: `TypeError: 'password' is an invalid keyword argument for Account`, a route and a model that disagreed
    on a field name, which fixers did not find in five rounds without it). Never raises.
    """
    try:
        text = (Path(repo_root) / project / SERVICE_LOG).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    found: dict[str, str] = {}
    for block in text.split(_A_TRACEBACK)[1:]:
        lines = [line.rstrip() for line in block.splitlines()]
        exception = next((line.strip() for line in reversed(lines) if _AN_EXCEPTION_LINE.match(line.strip())), "")
        if not exception:
            continue
        frames = [line.strip() for line in lines
                  if line.strip().startswith("File ") and ".py" in line and "site-packages" not in line]
        found.pop(exception, None)
        found[exception] = f"{exception}" + (f" ({frames[-1]})" if frames else "")
    return list(found.values())[-MOST_SERVICE_ERRORS:]


def _with_the_errors_the_service_logged(repo_root: str | Path, project: str, result: AcceptanceResult) -> None:
    """Add what the service logged to each failing test that met a server error. Never raises."""
    try:
        errors = the_errors_a_service_logged(repo_root, project)
        if not errors:
            return
        added = "".join(f"- {error[:400]}\n" for error in errors)
        tests = [
            replace(test, message=f"{test.message}{_SERVICE_ERRORS_MARK}{added}")
            if test.outcome == "failed" and _A_SERVER_ERROR.search(test.message or "")
            and _SERVICE_ERRORS_MARK not in (test.message or "") else test
            for test in result.report.tests
        ]
        result.report = replace(result.report, tests=tests)
    except Exception:  # noqa: BLE001 - the failures stand without it
        return


def _a_near_miss(pack: Any, message: str, page: str) -> str:
    if pack.near_misses is None:
        return ""
    try:
        return pack.near_misses(message, page) or ""
    except Exception:  # noqa: BLE001 - the failure stands without the hint
        return ""


#: How many of the product's own reported problems a result keeps.
MOST_RUNTIME_PROBLEMS = 10


def _runtime_report(repo_root: str | Path, project: str) -> Path | None:
    found = contract.the_pack(repo_root)
    if found is None or not found[0].runtime_report:
        return None
    return Path(repo_root) / project / found[0].runtime_report


#: How much of what the product shows a result keeps.
MOST_SHOWN_CHARS = 1_500


def _read_runtime_report(path: Path | None) -> tuple[list[str], str]:
    """(problems, what it shows) from the pack's runtime report; a bare list is problems only."""
    if path is None:
        return [], ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], ""
    if isinstance(data, list):
        data = {"problems": data}
    if not isinstance(data, dict):
        return [], ""
    problems = [str(item)[:400] for item in data.get("problems") or [] if str(item).strip()]
    return problems[:MOST_RUNTIME_PROBLEMS], str(data.get("shows") or "")[:MOST_SHOWN_CHARS]


def _read_phone_overflow(path: Path | None) -> int:
    """How far past a phone's width the page reached, from the pack's runtime report; 0 if unknown."""
    if path is None:
        return 0
    try:
        layout = json.loads(path.read_text(encoding="utf-8")).get("layout") or {}
        return max(0, int(layout.get("phoneOverflow") or 0))
    except (OSError, ValueError, AttributeError, TypeError):
        return 0


def _read_layout_findings(path: Path | None) -> tuple[list[str], list[str]]:
    """(controls drawn over each other, controls too small to tap) at a phone's width, from the runtime report."""
    if path is None:
        return [], []
    try:
        layout = json.loads(path.read_text(encoding="utf-8")).get("layout") or {}
    except (OSError, ValueError, AttributeError):
        return [], []

    def kept(key: str) -> list[str]:
        found = layout.get(key) if isinstance(layout, dict) else None
        return [str(item)[:160] for item in (found if isinstance(found, list) else [])[:5]]

    return kept("overlaps"), kept("smallTargets")


def _read_accessibility(path: Path | None) -> list[dict[str, Any]]:
    """The accessibility rules the page probe found broken, from its report; [] if none or unknown."""
    if path is None:
        return []
    try:
        found = json.loads(path.read_text(encoding="utf-8")).get("layout", {}).get("accessibility") or []
    except (OSError, ValueError, AttributeError):
        return []
    kept = []
    for rule in found if isinstance(found, list) else []:
        if isinstance(rule, dict) and rule.get("id"):
            kept.append({
                "id": str(rule.get("id"))[:80],
                "impact": str(rule.get("impact") or "")[:20],
                "help": str(rule.get("help") or "")[:200],
                "count": int(rule.get("count") or 0) if str(rule.get("count") or "0").isdigit() else 0,
                "where": [str(item)[:120] for item in (rule.get("where") or [])[:3]],
                "why": [str(item)[:240] for item in (rule.get("why") or [])[:3]],
            })
    return kept[:10]


def _judged(repo_root: str | Path, result: AcceptanceResult, save: bool) -> AcceptanceResult:
    excused = deferred(repo_root)
    by_tag: dict[str, list[junit.TestResult]] = {}
    for test in result.report.tests:
        for tag in test.tags:
            by_tag.setdefault(tag, []).append(test)
    # A criterion due now is judged by its tests that can pass now: one that
    # also needs a later sprint's work fails until then, whatever it carries.
    # See `sprint_scope.waiting_tests`. A criterion with no other test keeps
    # them all, as before.
    from app.acceptance import sprint_scope

    waiting = sprint_scope.waiting_tests(repo_root)

    def judge(item_id: str, text: str) -> CriterionResult:
        tests = by_tag.get(item_id, [])
        if waiting:
            tests = [t for t in tests if not sprint_scope.waits_on(t.name, waiting)] or tests
        if item_id in excused:
            status = "deferred"
        elif not tests:
            status = "untested"
        elif any(t.outcome == "failed" for t in tests) or all(t.outcome == "skipped" for t in tests):
            status = "failed"
        else:
            status = "passed"
        return CriterionResult(
            id=item_id, text=text, status=status,
            tests=[{"name": t.name, "outcome": t.outcome, "message": t.message} for t in tests],
        )

    for criterion in criteria(repo_root):
        result.criteria[criterion.id] = judge(criterion.id, criterion.text)
    for change_id, text in (_state(repo_root).get("change_requests") or {}).items():
        result.change_requests[change_id] = judge(change_id, str(text))
    if save:
        try:
            path = Path(repo_root) / RESULT_FILE
            path.parent.mkdir(parents=True, exist_ok=True)
            saved = result.as_dict()
            # The product this measured, so a later probe can tell "unchanged" (`unstable`).
            from app.acceptance.unstable import fingerprint

            saved["fingerprint"] = fingerprint(repo_root)
            path.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
        except OSError:
            logger.debug("Could not save the acceptance result", exc_info=True)
    return result


def _source_bugs_by_suffix() -> dict[str, tuple[str, ...]]:
    """Per test-file suffix, the patterns of a test's own source that no product can pass."""
    from app.stacks.packs import _javascript

    return {suffix: _javascript.TEST_SOURCE_BUGS for suffix in (".js", ".mjs", ".cjs", ".ts", ".mts", ".tsx", ".jsx")}


_SOURCE_BUGS = _source_bugs_by_suffix()
#: Where a test's body begins in a spec file: `test('name'`, `it("name"`.
_A_TEST_STARTS = re.compile(r"""^\s*(?:test|it)(?:\.\w+)?\(\s*(['"`])(.+?)\1""", re.M)


def _the_tests_sources(repo_root: str | Path) -> dict[str, tuple[str, str]]:
    """Each acceptance test's own body by its name, with its file's suffix; {} when it cannot be read."""
    found: dict[str, tuple[str, str]] = {}
    try:
        for path in suite_files(repo_root):
            text = path.read_text(encoding="utf-8", errors="replace")
            starts = list(_A_TEST_STARTS.finditer(text))
            for index, match in enumerate(starts):
                end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
                found.setdefault(match.group(2).strip(), (text[match.start():end], path.suffix.lower()))
    except Exception:  # noqa: BLE001 - the failure messages alone, as before
        return {}
    return found


def tests_that_broke_themselves(repo_root: str | Path, result: AcceptanceResult) -> list[str]:
    """Failures caused by the tests' own code, by the pack's own patterns.

    Before the product is built every test fails, so "it fails" says nothing;
    why it fails says a lot. A missing control, endpoint or function is the
    product not existing yet. An error the test's own code throws means the
    test can never pass, whatever is built - and a suite locked with one is a
    definition of done no product can meet.
    """
    found = contract.the_pack(repo_root)
    if found is None:
        return []
    patterns = [re.compile(pattern, re.I | re.M) for pattern in found[0].test_bugs]
    sources = _the_tests_sources(repo_root)
    broken = []
    for test in result.report.tests:
        if test.outcome != "failed":
            continue
        message = test.message or ""
        body, suffix = sources.get(str(test.name or "").strip(), ("", ""))
        written = next((p for p in _SOURCE_BUGS.get(suffix, ()) if re.search(p, body)), None)
        if written is not None:
            line = next((l.strip() for l in body.splitlines() if re.search(written, l)), "")
            broken.append(
                f"`{test.name}` cannot pass whatever is built: its own code `{line[:200]}` keeps a "
                "promise as a value where the value was meant - await it. Fix the test so that it "
                "can pass once the product works."
            )
            continue
        if any(pattern.search(message) for pattern in patterns):
            first = next((line.strip() for line in message.splitlines() if line.strip()), "")
            broken.append(
                f"`{test.name}` fails because of an error in the test's own code, not because the "
                f"product is unbuilt: {first[:300]}. Fix the test so that it can pass once the "
                "product works."
            )
    return broken


def tests_left_behind_by_their_own_change(repo_root: str | Path, result: AcceptanceResult) -> list[str]:
    """Failed tests that looked for a change through a locator found by the text it replaced.

    See the pack's `locator_left_behind`: the page shows the new text, the
    locator was found by the old, so the test cannot pass on a product that
    made the change.
    """
    found = contract.the_pack(repo_root)
    if found is None:
        return []
    pack = found[0]
    broken = []
    for test in result.report.tests:
        if test.outcome != "failed":
            continue
        left = pack.locator_left_behind(test.message or "") if pack.locator_left_behind else None
        if left is not None:
            old, new = left
            broken.append(
                f"`{test.name}` looks for \"{new}\" through a locator it found by \"{old}\". The page "
                f"it failed on shows \"{new}\" and no longer shows \"{old}\", so the change was made "
                "and the test cannot see it. Find the item again by the text it shows now."
            )
            continue
        value = pack.filtered_by_a_field_value(test.message or "") if pack.filtered_by_a_field_value else None
        if value is not None:
            broken.append(
                f"`{test.name}` looks inside an item found by the text \"{value}\", and the page it "
                f"failed on shows \"{value}\" only as the value of a field - a field's value is not "
                "the text of what holds it, so the item stops matching the moment it is edited. Find "
                "what the edit shows by its label or name on the page, not inside the item."
            )
    return broken


def tests_the_runner_never_ran(repo_root: str | Path, result: AcceptanceResult) -> list[str]:
    """Tests the suite's files declare for a criterion that the runner's report never lists.

    Counted from the text, a test is there; the runner may never collect it. One
    run's suite left a test unclosed, so the next two - its only tests of two
    criteria - were written inside its body: Playwright never registered them,
    the criteria read "untested" from the day the suite was locked, and each
    round handed them to the product's fixers, who cannot change the suite.

    Only titles that name a criterion and hold no template expression, so a
    title built at run time is not taken for one that never ran.
    """
    if not result.ran or not result.report.found or not result.report.tests:
        return []
    reported = [test.name for test in result.report.tests]
    missing = []
    for shown, name in declared_tests(repo_root):
        if not junit.tags_in(name) or "${" in name:
            continue
        # A title read from the text stops at an escaped quote - `a task\'s`
        # reads as `a task\` - so what precedes the escape is what is matched.
        if any(name.split("\\", 1)[0] in ran for ran in reported):
            continue
        missing.append(
            f"`{name}` in {shown} is written but the runner never ran it: it is not in the "
            "runner's report at all, so its criterion is untested whatever is built. "
            + (_a_file_the_runner_does_not_collect(repo_root, shown)
               or "A test written inside another test's body, or after a block left unclosed, is never "
                  "collected. Make it a test of its own.")
        )
    return missing


def _a_file_the_runner_does_not_collect(repo_root: str | Path, shown: Any) -> str:
    """Why a file's tests never run when its name is not one the runner collects; "" when it is, or unknown.

    Measured on a small-model run: a TypeScript service's QA wrote `api.spec.ts` where the runner collects
    `*.spec.js`; four rounds said only "make it a test of its own", the model kept the file, and the run
    failed with a suite that proved nothing.
    """
    try:
        from fnmatch import fnmatch

        pattern = str((contract.read(repo_root) or {}).get("acceptance_pattern") or "")
        name = Path(str(shown)).name
        if pattern and not fnmatch(name, pattern):
            return (f"The file's name is the reason: the runner collects only files matching `{pattern}` in the "
                    f"acceptance folder, and `{name}` does not match, so nothing in it ever runs. Put its tests in a "
                    f"file whose name matches `{pattern}` (write the test code in the language that pattern names).")
    except Exception:  # noqa: BLE001 - the general advice stands
        return ""
    return ""


#: What a runner prints when the product it should test never came up: the
#: server it starts exited, or the build that server serves failed.
_NEVER_STARTED = re.compile(
    r"(?:webServer was not able to start|Process from config\.webServer|Timed out waiting \d+ms from config\.webServer|Build failed in|"
    r"\berror during build\b|Address already in use|EADDRINUSE|"
    r"(?:server|service) (?:exited|did not start|failed to start))",
    re.I,
)
#: The start of every "the product did not start" problem.
PRODUCT_DID_NOT_START = "The product did not start for the acceptance suite"

#: A line of a failed start that says what went wrong, rather than where.
_STATES_A_CAUSE = re.compile(
    r"\berror\b|\bfailed\b|cannot find|could not|not found|not exported|unresolved|no module named|"
    r"syntaxerror|typeerror|referenceerror|importerror|is not defined|required",
    re.I,
)

#: A place in a file, as runtimes print one in a trace: `path:12`, `path:12:5`,
#: `path(12)`, `path(12,5)`, `File "path", line 12`, `path:line 12`.
_A_PLACE = re.compile(
    r"""(?P<path>(?:[A-Za-z]:)?[\w@~.$/\\-]*?[\w$-]+\.[A-Za-z][A-Za-z0-9]{0,7})"""
    r"""(?=",\s*line\s+\d+|:line\s+\d+|:\d+|\(\d+(?:,\s*\d+)?\))"""
)
#: The product's frames kept from a failed start, the ones nearest the error.
MOST_PRODUCT_FRAMES = 4
#: Files of the product looked at, at most, to tell its frames from the rest.
_MOST_PRODUCT_FILES = 20_000

#: A start that failed opening its data file: SQLite's own words, in any
#: language's binding, or a missing file of a database's suffix.
_A_DATA_FILE_NOT_OPENED = re.compile(
    r"unable to open (?:the )?database file|SQLITE_CANTOPEN|"
    r"(?:ENOENT|no such file or directory|cannot find the path)[^\n]{0,160}\.(?:db|sqlite3?)\b|"
    r"\.(?:db|sqlite3?)\b[^\n]{0,160}(?:ENOENT|no such file or directory|cannot find the path)",
    re.I,
)


def _the_product_s_files(root: str | Path | None) -> list[str]:
    """The workspace's files, by path from its root, outside the folders a tool fills."""
    if not root:
        return []
    import os

    from app.tools.repository import INSTALLED_DIRECTORIES

    base = Path(root)
    found: list[str] = []
    for directory, folders, names in os.walk(base):
        folders[:] = [f for f in folders if f not in INSTALLED_DIRECTORIES and not f.startswith(".")]
        found.extend(Path(directory, name).relative_to(base).as_posix() for name in names)
        if len(found) >= _MOST_PRODUCT_FILES:
            break
    return found


def _names_the_product(line: str, root: str | Path | None, files: list[str]) -> bool:
    """Whether a trace line names a place in one of the product's own files.

    Whatever the language: a file of the product, not one in a folder a tool
    fills, by its path from the workspace, from a folder inside it, from the
    root of another mount, or - as a JVM prints it - by its name alone.
    """
    from app.tools.repository import INSTALLED_DIRECTORIES

    prefix = str(Path(root)).rstrip("/") + "/" if root else ""
    names = {path.rsplit("/", 1)[-1] for path in files}
    for match in _A_PLACE.finditer(line):
        place = match.group("path").replace("\\", "/")
        if prefix and place.startswith(prefix):
            place = place[len(prefix):]
        while place.startswith("./"):
            place = place[2:]
        place = place.lstrip("/")
        if not place or any(part in INSTALLED_DIRECTORIES for part in place.split("/")):
            continue
        if "/" not in place:
            if place in names:
                return True
            continue
        if any(path == place or path.endswith("/" + place) or place.endswith("/" + path) for path in files):
            return True
    return False


def _where_its_data_lives(root: str | Path | None) -> str:
    """The run's pack's own words on where the product keeps its data, or ""."""
    try:
        from app.stacks.contract import the_pack

        found = the_pack(root) if root else None
        return " ".join(str(found[0].data_store or "").split()) if found else ""
    except Exception:  # noqa: BLE001 - a hint without it is the hint as it was
        return ""

#: A service's own words that it is up and taking requests, across servers and languages.
_LISTENING = re.compile(
    r"Listening at|listening on|Uvicorn running on|Running on https?://|Server (?:is )?(?:running|listening|started)|"
    r"Now listening on|Application startup complete|started server on|Puma starting|Started \w+ in \d",
    re.I,
)
#: An HTTP status a request was answered with, as clients and test runners print it.
_AN_HTTP_STATUS = re.compile(
    r"HTTP Error ([45]\d\d)|\b([45]\d\d) (?:Not Found|NOT FOUND|Method Not Allowed|Internal Server Error)\b|"
    r"\bstatus(?: code)?[\s:=]+([45]\d\d)\b",
)


def _it_listened_and_answered(text: str) -> str:
    """The HTTP status the readiness request was answered with, when the output shows the service listening; else "".

    A service that started and listened, and answered the suite's readiness
    request with an error status, was reported as never having started.
    Measured on a measured run: gunicorn listened, the readiness request to
    the health route answered 404 for thirty seconds, the suite said "did not
    start", and four fixes in two sprint attempts rewrote start-up code and
    password hashing - each reverted - while the routes were never registered.
    The 404 sat in the output past the six cause lines the excerpt keeps.
    """
    if not _LISTENING.search(text):
        return ""
    found = _AN_HTTP_STATUS.search(text)
    return next((group for group in found.groups() if group), "") if found else ""


#: A start that failed for want of a setting: a required field, an unset variable, a missing secret.
_A_MISSING_SETTING = re.compile(
    r"Field required|environment variable[^\n]{0,60}(?:not set|is required|missing)|"
    r"(?:KeyError|Missing|missing|not set)[^\n]{0,40}(?:SECRET|_KEY|TOKEN|PASSWORD|DSN|DATABASE_URL)\b|"
    r"(?:SECRET|_KEY|TOKEN|PASSWORD|DATABASE_URL)[^\n]{0,40}(?:is not set|is required|must be set|not defined)",
    re.I,
)


def every_failure_is_the_start(report: Any, root: str | Path | None = None) -> str:
    """The problem to record when every failing test failed because the product never came up; "" otherwise.

    A suite that starts the service per test (a fixture, a `beforeAll`) runs
    every test, and each fails at its setup with the service's own crash.
    The check above, asked only when no test ran, never saw it: measured on a
    gate run, a startup crash in one module (`main.py` calling a function
    `database.py` does not define) became six criterion defects, six fixers
    each rewrote their criterion's files, and all six were left open. Tests
    that need no service may pass; one failure for any other reason means
    the product started for it, and the failures are its own.
    """
    failed = [t for t in getattr(report, "tests", None) or () if t.outcome == "failed"]
    if not failed or not all(_NEVER_STARTED.search(t.message or "") for t in failed):
        return ""
    return the_product_did_not_start(failed[0].message, root)


def the_product_did_not_start(output: str, root: str | Path | None = None) -> str:
    """The problem to record when no test ran because the product never came up; "" otherwise.

    Measured on one run: a fix rewired the page, the build it served then
    failed ("App" is not exported by "src/App.tsx"), Playwright's web server
    never started, and the zero tests that ran were read as a suite that
    collects nothing - so the suite went back to QA, who cannot fix a build.
    """
    text = str(output or "")
    if not _NEVER_STARTED.search(text):
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    first = next((i for i, line in enumerate(lines) if _NEVER_STARTED.search(line) or re.search(r"\berror\b", line, re.I)), 0)
    # Where it started failing, and where it ended: a traceback names its cause
    # on its last line, and six lines from the first one were all frames.
    # Measured live: a service that needed a secret the suite does not set
    # crashed on `jwt_secret_key  Field required`, and the defect showed only
    # the frames of uvicorn's start.
    head = lines[first:first + 3]
    ending = [line for line in lines[-8:] if line not in head]
    # And between them, the lines that say what went wrong. Measured live: a
    # page's build failed, the head was Playwright's own "was not able to
    # start" and the ending a Node error object's file list; the build's line
    # naming its cause - an import that does not resolve - sat between and was
    # cut, so its fixers were told the build failed and not why.
    between = lines[first + 3:max(first + 3, len(lines) - 8)]
    kept = {i for i, line in enumerate(between) if _STATES_A_CAUSE.search(line)}
    kept = set(sorted(kept)[:6])
    # And the frames in the product's own code, with the line each ran.
    # Measured live: a service stopped at start-up on "unable to open database
    # file"; the excerpt kept only frames inside its installed packages, and
    # the one product file it named was a deprecation warning's - which the
    # fix then rewrote, while the cause sat in the module that opens the
    # database.
    files = _the_product_s_files(root)
    frames = [i for i, line in enumerate(between) if files and _names_the_product(line, root, files)]
    for i in frames[-MOST_PRODUCT_FRAMES:]:
        kept.add(i)
        if i + 1 < len(between) and not _A_PLACE.search(between[i + 1]):
            kept.add(i + 1)
    causes = [between[i][:300] for i in sorted(kept)]
    middle = ("\n...\n" + "\n".join(causes)) if causes else ""
    excerpt = ("\n".join(head) + middle + ("\n...\n" + "\n".join(ending) if ending else ""))[:2_400]
    hint = ""
    answered = _it_listened_and_answered(text)
    if answered:
        # Ahead of the excerpt: a defect carries the first 1,500 characters of
        # this, and the cause is the one thing a fixer must not lose.
        lead = (
            f"The product started - its output shows it listening - but the request the suite makes to see that "
            f"it is up was answered {answered}. How it starts is not what is wrong: the route that request asks "
            "for is not served. Check that the routes are registered with the application the start command "
            "runs; a route defined in a module nothing imports is never served."
        )
        return f"{PRODUCT_DID_NOT_START}: no test could reach it. {lead} Its output:\n{excerpt}"
    if _A_DATA_FILE_NOT_OPENED.search(text):
        guide = _where_its_data_lives(root)
        hint = (
            "\nThe product could not open its data file. It builds the file's path from where it is told to keep "
            "its data, not from the folder it happens to start in, and creates that folder if it is missing."
            + (f" This setup says: {guide[:700]}" if guide else "")
        )
    elif _A_MISSING_SETTING.search(text):
        hint = (
            "\nThe product needs a setting that the suite does not give it: the suite sets only `PORT` and "
            "`DATA_DIR`. A secret or key the product needs to start has a development default, or is "
            "generated at its first start and kept under `DATA_DIR`."
        )
    return f"{PRODUCT_DID_NOT_START}: no test could reach it. Its output:\n{excerpt}{hint}"


def vacuous_green(repo_root: str | Path, result: AcceptanceResult) -> list[str]:
    """Reasons this result proves nothing even though the runner complained of nothing.

    Every gate that reads "no failures" as "done" is vacuous when the runner
    collected none of what the suite declares: zero tests and exit 0 is green
    to every count, and each criterion reads "untested" - which a dispute can
    defer and a release then ship. Measured on one run: the scaffold's own
    smoke test ran zero tests, exited 0, and the setup was left to the agents.
    Unlike the round's other problems, these are never waivable by a round
    count or spent with a repair budget: a round count can waive advice, but
    it cannot make an empty report into evidence.
    """
    if not result.ran:
        return []  # a suite that never ran is each gate's own problem, reported there
    if str(result.problem or "").startswith(PRODUCT_DID_NOT_START):
        return []  # the product's failure, raised as its defect - not the suite's
    if not result.report.tests:
        return [
            f"The suite's runner ran and reported zero tests (exit {result.exit_code}, "
            f"`{result.command}`): nothing was proven. A runner that collects none of the "
            "suite's tests - a discovery pattern its runtime does not expand, a configuration "
            "that switches the suite off, a report written empty - exits without complaint. "
            "Zero tests is not a green suite: find what the runner stopped collecting and "
            "make it run the tests that are written."
        ]
    if criteria(repo_root) and not any(junit.tags_in(test.name) for test in result.report.tests):
        return [
            f"The suite's runner ran {len(result.report.tests)} test(s) and not one of them names "
            "an acceptance criterion in its title (a title carries its criterion as its "
            "[AC-n] tag): tests that name no criterion prove no criterion, and every criterion "
            "reads \"untested\" whatever they show. Point each test at the criterion it checks."
        ]
    return [*tests_the_runner_never_ran(repo_root, result), *tests_the_runner_skipped(repo_root, result)]


#: A test declared skipped in the text, in the spellings of the runners that use titled tests:
#: `test.skip(`, `it.fixme(`, `describe.todo(` and `xit(`; group 2 is its title.
_WRITTEN_SKIPPED = re.compile(
    r"""(?:\b(?:test|it|describe|scenario)(?:\.\w+)*\.(?:skip|fixme|todo)|\bx(?:it|test|describe))\(\s*(['"`])(.+?)\1""")


def tests_the_runner_skipped(repo_root: str | Path, result: AcceptanceResult) -> list[str]:
    """Tests of a criterion the runner reports skipped, when written skipped or when no test failed.

    A skipped test still carries its criterion's name, so every count by name
    reads the criterion as tested. Measured on one run: a repair turned nine
    tests into `test.skip(...)` with empty bodies, the suite was locked, and
    each round charged those criteria to the product while nothing measured
    them. A test skipped after another failed is a runner skipping the rest of
    a serial group, and is named only when the text itself skips it.
    """
    if not result.ran or not result.report.found or not result.report.tests:
        return []
    skipped = [test for test in result.report.tests if test.outcome == "skipped" and junit.tags_in(test.name)]
    if not skipped:
        return []
    written: list[str] = []
    for path in suite_files(repo_root):
        try:
            written.extend(m.group(2) for m in _WRITTEN_SKIPPED.finditer(path.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    nothing_failed = not any(test.outcome == "failed" for test in result.report.tests)
    # A criterion another of its tests ran for is tested; its stub left beside it proves nothing either way.
    # Measured on the same run: QA wrote the tests in a new file, left the stubs, and the review refused the
    # suite for the stubs alone until its rounds ran out.
    ran = {tag for test in result.report.tests if test.outcome != "skipped" for tag in junit.tags_in(test.name)}
    named: list[str] = []
    for test in skipped:
        untested = [tag for tag in junit.tags_in(test.name) if tag not in ran]
        if not untested or not (nothing_failed or any(name.split("\\", 1)[0] in test.name for name in written)):
            continue
        named.append(
            f"`{test.name}` is skipped: the runner reports it skipped, so it proves nothing about "
            f"{', '.join(untested)} whatever is built. A skipped test is no test - write its "
            "checks and let it run; it fails until the product does what it checks, which is how the suite "
            "starts. A criterion no automated test can check is deferred with its reason instead.")
    return named


def tests_that_need_what_they_never_made(repo_root: str | Path, result: AcceptanceResult) -> list[str]:
    """Locked tests that can pass only on a product that ships with data, by the pack's reader.

    Every test starts from an empty product. One that acts on something it
    never created fails on every product that meets its criterion, and each
    fix round spends itself on it. Judged on evidence the run has: the page
    the test failed on, the page as it first loads, and the pages the other
    tests failed on. See the JavaScript packs' `needs_what_it_never_made`.
    """
    found = contract.the_pack(repo_root)
    if found is None or found[0].needs_what_it_never_made is None or not result.shows:
        return []
    failures = []
    for test in result.report.tests:
        message = test.message or ""
        if test.outcome == "failed" and _PAGE_MARK in message:
            before, _, page = message.partition(_PAGE_MARK)
            failures.append((test.name, before, page))
    try:
        reasons = found[0].needs_what_it_never_made(failures, result.shows)
    except Exception:  # noqa: BLE001 - the failures stand as they are
        return []
    return [
        f"`{name}` can pass only on a product that already holds data: {why}. Every test "
        "starts from an empty product, so a test must first create, through the product as "
        "a user would, whatever it then acts on."
        for name, why in reasons.items()
    ]


#: An assertion call in a test: `.toBeVisible(`, `.not.toHaveText(`, `.notToHaveAttribute(`, `.not(`.
_ASSERTION_CALL = re.compile(r"\.((?:not[A-Z]|to[A-Z])[A-Za-z]*|not)\s*\(")


def _ends_an_expectation(text: str, at: int) -> bool:
    """Whether the `.toX(` at `at` is called on an `expect(...)`, not on an ordinary value.

    `toString`, `toUpperCase` and `toISOString` are the language's own; one
    run's suite built unique titles with `Math.random().toString(36)` in a
    helper, and was sent back three times and locked with "calls `toString`,
    which the installed test runner does not define" against four files.
    """
    start = text.rfind("expect", max(0, at - 2000), at)
    if start == -1:
        return False
    opening = text.find("(", start, at)
    if opening == -1:
        return False
    depth = 0
    for index in range(opening, at):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return bool(_ONLY_MODIFIERS.fullmatch(text[index + 1:at]))
    return False


#: What may stand between `expect(...)` and its matcher.
_ONLY_MODIFIERS = re.compile(r"\s*(?:\.\s*(?:not|resolves|rejects)\s*)*")


def assertions_that_do_not_exist(repo_root: str | Path) -> list[str]:
    """Where the suite calls an assertion its runner does not define, by the pack's reader.

    Such a test cannot pass whatever is built, and until the product exists it
    fails before reaching the call - so the run that locks the suite never
    sees it. Measured on one run: two locked tests called
    `expect(...).toBeUnchecked()`; once the product was built they failed with
    "toBeUnchecked is not a function", for ever.
    """
    found = contract.the_pack(repo_root)
    if found is None or found[0].assertion_names is None:
        return []
    pack, record = found
    known = pack.assertion_names(Path(repo_root) / str(record.get("project") or ""))
    if not known:
        return []
    root = Path(repo_root)
    problems = []
    for path in suite_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in _ASSERTION_CALL.finditer(text):
            if match.group(1) in known or not _ends_an_expectation(text, match.start()):
                continue
            line = text.count("\n", 0, match.start()) + 1
            problems.append(
                f"`{path.relative_to(root).as_posix()}` line {line} calls `{match.group(1)}`, which the "
                "installed test runner does not define, so the test can never pass whatever is built. "
                "Use one it defines (for the opposite of a check, `not.` before it)."
            )
    return problems[:6]


def locators_nobody_sees(repo_root: str | Path) -> list[str]:
    """Where the suite finds a control by something no person sees, by the pack's patterns.

    The suite is the definition of done, and it is only as strict as the way it
    finds things. Measured on one run: QA found a field the brief called
    "labelled" by its placeholder, the product gave it a placeholder and no
    label, the locked suite passed - and three of the benchmark's hidden tests,
    which find the field by its label, failed. A product a person (or a screen
    reader) cannot use the way the brief says passed its own definition of done.

    Every line, once per file. Naming only the first let QA fix that line and
    hear of the next one a round later: one run's suite was sent back for
    line 16 of a file and then for line 21 of the same file, and spent the
    rounds it had on a fault it could have fixed in one.
    """
    found = contract.the_pack(repo_root)
    if found is None or not found[0].locators_nobody_sees:
        return []
    patterns = [re.compile(pattern) for pattern in found[0].locators_nobody_sees]
    root = Path(repo_root)
    problems = []
    for path in suite_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hits = sorted({text.count("\n", 0, match.start()) + 1
                       for pattern in patterns for match in pattern.finditer(text)})
        if not hits:
            continue
        snippet = text.splitlines()[hits[0] - 1].strip()[:160]
        where = ", ".join(str(line) for line in hits[:12]) + (" ..." if len(hits) > 12 else "")
        problems.append(
            f"`{path.relative_to(root).as_posix()}` finds a control by something no person sees "
            f"on line(s) {where} (`{snippet}`). Find each by the label or name the brief gives it, "
            "exactly; where the brief gives none, by its role and the name a person reads."
        )
    return problems[:6]


def locators_that_do_not_exist(repo_root: str | Path) -> list[str]:
    """Where the suite calls locator methods the test runner does not define.

    Acceptance tests run before anything is built and fail before reaching
    the call - so the run that locks the suite never sees it. Once the product
    is built and the page loads, the test fails with "is not a function".
    Measured on one run: tests called locator methods from another test library
    instead of the runner's defined locator methods, locking a suite no product
    could ever pass.
    """
    found = contract.the_pack(repo_root)
    if found is None or not found[0].locators_that_do_not_exist:
        return []
    patterns = [re.compile(pattern) for pattern in found[0].locators_that_do_not_exist]
    root = Path(repo_root)
    problems = []
    for path in suite_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hits = sorted({text.count("\n", 0, match.start()) + 1
                       for pattern in patterns for match in pattern.finditer(text)})
        if not hits:
            continue
        lines = text.splitlines()
        snippet = lines[hits[0] - 1].strip()[:160]
        where = ", ".join(str(line) for line in hits[:8]) + (" ..." if len(hits) > 8 else "")
        called = sorted({m.group(0).split("(")[0].strip() for p in patterns for m in p.finditer(text)})
        called_str = ", ".join(f"`{c}`" for c in called[:3])
        problems.append(
            f"`{path.relative_to(root).as_posix()}` calls {called_str}, which the test runner does not "
            f"define, on line(s) {where} (`{snippet}`). Use a locator method defined by the project's "
            "test framework."
        )
    return problems[:6]


def locators_that_pick_one(repo_root: str | Path) -> list[str]:
    """Where the suite acts on whichever of several matching controls comes first.

    A locator that matches two controls refuses to act, which is how a test
    notices a page that shows one control twice. Measured on one run: every
    filter was pressed through a selector handed to the page, which acts on the
    first match; the product drew each filter twice, the locked suite passed,
    and the benchmark's hidden test that finds the filter by its name failed on
    "resolved to 2 elements".
    """
    found = contract.the_pack(repo_root)
    if found is None or not found[0].locators_that_pick_one:
        return []
    patterns = [re.compile(pattern) for pattern in found[0].locators_that_pick_one]
    root = Path(repo_root)
    problems = []
    for path in suite_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        hits = sorted({text.count("\n", 0, match.start()) + 1
                       for pattern in patterns for match in pattern.finditer(text)})
        if not hits:
            continue
        snippet = lines[hits[0] - 1].strip()[:160]
        where = ", ".join(str(line) for line in hits[:8]) + (" ..." if len(hits) > 8 else "")
        problems.append(
            f"`{path.relative_to(root).as_posix()}` acts on whichever match comes first, on "
            f"line(s) {where} (`{snippet}`), so a page that shows the same control twice still "
            "passes. Find each control with a locator that refuses more than one match - by the "
            "label or name the brief gives it - and act on that locator."
        )
    return problems[:6]


def locators_that_contradict_their_assertions(repo_root: str | Path) -> list[str]:
    """Where a test finds something by a text and then asserts it does not show that text.

    It can pass only on a page that keeps the text hidden in what it finds. See
    the pack's `contradicting_locators`. Measured on one run: a fix stage did
    exactly that for the locked suite, and the customer's check failed on it.
    """
    found = contract.the_pack(repo_root)
    if found is None or found[0].contradicting_locators is None:
        return []
    root = Path(repo_root)
    problems = []
    for path in suite_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line, name, said in found[0].contradicting_locators(text)[:3]:
            problems.append(
                f"`{path.relative_to(root).as_posix()}` line {line} asserts that what `{name}` finds "
                f"does not show \"{said}\", but `{name}` finds it by showing \"{said}\": it matches "
                "only while that text is still somewhere in it, so the test can pass only on a page "
                "that keeps the old text hidden. Find the item again by the text it shows now."
            )
    return problems[:6]


def locators_by_a_name_the_role_never_has(repo_root: str | Path) -> list[str]:
    """Where the suite finds something by a name its role never takes from what it shows.

    Such a locator matches nothing on a page that shows exactly what the brief
    asks, so the test can never pass. See the pack's `locators_by_a_missing_name`.
    """
    found = contract.the_pack(repo_root)
    if found is None or not found[0].locators_by_a_missing_name:
        return []
    patterns = [re.compile(pattern) for pattern in found[0].locators_by_a_missing_name]
    root = Path(repo_root)
    problems = []
    for path in suite_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hits = sorted({text.count("\n", 0, match.start()) + 1
                       for pattern in patterns for match in pattern.finditer(text)})
        if not hits:
            continue
        snippet = text.splitlines()[hits[0] - 1].strip()[:160]
        where = ", ".join(str(line) for line in hits[:12])
        problems.append(
            f"`{path.relative_to(root).as_posix()}` finds an element by a name its role never "
            f"takes from what it shows, on line(s) {where} (`{snippet}`): the locator matches "
            "nothing on a page that shows that text, so the test can never pass. Find it by "
            "its role and filter it by the text it shows."
        )
    return problems[:6]


def tests_that_never_open_the_page(repo_root: str | Path) -> list[str]:
    """Tests that act on the page with nothing that opens it. See the pack's `opens_no_page`."""
    found = contract.the_pack(repo_root)
    if found is None or found[0].opens_no_page is None:
        return []
    root = Path(repo_root)
    problems = []
    for path in suite_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line, title in list(found[0].opens_no_page(text))[:4]:
            problems.append(
                f"`{path.relative_to(root).as_posix()}` line {line}: `{title}` acts on the page and "
                "nothing opens it - every test starts on a blank page, so it can never pass. Open "
                "the page first, in the test or in a `beforeEach`."
            )
    return problems[:6]


def tests_that_access_storage_before_opening_the_page(repo_root: str | Path) -> list[str]:
    """Tests or helpers that access storage before opening the page. See the pack's `storage_before_page_open`."""
    found = contract.the_pack(repo_root)
    if found is None or found[0].storage_before_page_open is None:
        return []
    root = Path(repo_root)
    problems = []
    for path in suite_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line, storage_name, context in list(found[0].storage_before_page_open(text))[:4]:
            problems.append(
                f"`{path.relative_to(root).as_posix()}` line {line}: {context} accesses `{storage_name}` "
                "before opening the page with `goto`. Every test starts on a blank page where storage access "
                "is forbidden and throws a browser SecurityError. Navigate with `await page.goto('/')` "
                "first before touching storage."
            )
    return problems[:6]


def tests_that_expect_what_they_never_gave(repo_root: str | Path) -> list[str]:
    """Tests that look for a value they made and never gave the product. See the pack's `expects_what_it_never_gave`."""
    found = contract.the_pack(repo_root)
    if found is None or found[0].expects_what_it_never_gave is None:
        return []
    root = Path(repo_root)
    problems = []
    for path in suite_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line, title, value in list(found[0].expects_what_it_never_gave(text))[:4]:
            problems.append(
                f"`{path.relative_to(root).as_posix()}` line {line}: `{title}` looks for `{value}`, a "
                "value the test made itself and never gave the product - it is not entered, sent or "
                "passed on before it is looked for - so no product can show it and the test can never "
                "pass. Give the product the value first, as a user would, or look for one it was given."
            )
    return problems[:6]


#: Words a criterion uses when it does state an order.
_STATES_AN_ORDER = re.compile(
    r"\b(?:order|ordered|orders|first|last|top|bottom|newest|oldest|latest|earliest|recent|"
    r"sort|sorted|sorts|chronological|ascending|descending|before|after|above|below|sequence|position)\b",
    re.I,
)


def tests_that_assert_an_unstated_order(repo_root: str | Path) -> list[str]:
    """Tests that assert what two places of a list show when no criterion they carry states an order.

    Measured on one run: the locked list test expected the newest item first and
    the locked removal test expected the oldest first; neither criterion said
    anything about order, and each fix that made one pass broke the other. A
    test that holds the product to an order the criteria leave open is a
    contradiction waiting for its partner. See the pack's `positions_it_asserts`.
    """
    found = contract.the_pack(repo_root)
    if found is None or found[0].positions_it_asserts is None:
        return []
    texts = {c.id: c.text for c in criteria(repo_root)}
    root = Path(repo_root)
    problems = []
    for path in suite_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line, title, positions in found[0].positions_it_asserts(text):
            carried = junit.tags_in(title)
            if _STATES_AN_ORDER.search(" ".join(texts.get(item, "") for item in carried)):
                continue
            problems.append(
                f"`{path.relative_to(root).as_posix()}` line {line}: `{title}` checks what "
                f"{len(positions)} places of a list show - an order - but "
                f"{', '.join(carried) or 'no criterion it carries'} states none. Another test may "
                "expect another order from the same steps, and no product can pass both. Check that "
                "each one is there, not where it is."
            )
    return problems[:6]


def controls_never_found_by_name(repo_root: str | Path, brief_text: str) -> list[str]:
    """Each control the brief names that no test finds by that name, as one problem.

    Measured on one run: the brief gave every item a box labelled "Done", the
    product gave it no label, and the locked suite - which found the box by a
    class - passed; the benchmark's hidden tests, which find it by "Done",
    failed twice. A suite that never asks for a name cannot tell a product that
    gave it from one that did not.
    """
    from app.analysis.interface_checks import controls_the_brief_names

    found = contract.the_pack(repo_root)
    if found is None or not found[0].finds_by_name:
        return []
    names = controls_the_brief_names(brief_text)
    if not names:
        return []
    texts = []
    for path in suite_files(repo_root):
        try:
            texts.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    if not texts:
        return []
    suite_text = "\n".join(texts)
    missing = [
        name for name in names
        if not any(
            re.search(template.replace("{name}", re.escape(name)), suite_text)
            for template in found[0].finds_by_name
        )
    ]
    if not missing:
        return []
    return [
        "The brief names these controls and no test finds any of them by that name: "
        + ", ".join(f'"{name}"' for name in missing)
        + ". A test that finds a control another way passes whatever the product calls it - "
        "or when it gives it no name at all. Find each by the exact name the brief gives it, "
        "in a test that uses it."
    ]


def tests_with_module_system_mismatch(repo_root: str | Path) -> list[str]:
    """Suite files that use a module system their runtime will not load them as. See the pack's `module_system_mismatch`.

    Such a file throws as it loads, before any of its tests runs - so before
    anything is built it fails exactly as an unbuilt product makes it fail, and
    the suite would be locked with it.
    """
    found = contract.the_pack(repo_root)
    where = location(repo_root)
    if found is None or found[0].module_system_mismatch is None or where is None:
        return []
    project_root = Path(repo_root) / where[0]
    root = Path(repo_root)
    problems = []
    for path in suite_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line, why in list(found[0].module_system_mismatch(project_root, path, text))[:1]:
            problems.append(f"`{path.relative_to(root).as_posix()}` line {line} {why}")
    return problems[:6]


def tests_with_unawaited_async_helpers(repo_root: str | Path) -> list[str]:
    """Where the suite uses one of its async helpers without awaiting it. See the pack's `unawaited_helpers`."""
    found = contract.the_pack(repo_root)
    if found is None or found[0].unawaited_helpers is None:
        return []
    root = Path(repo_root)
    problems = []
    for path in suite_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line, helper in list(found[0].unawaited_helpers(text))[:4]:
            problems.append(
                f"`{path.relative_to(root).as_posix()}` line {line}: async helper `{helper}` is called "
                f"without `await`. An async function returns a Promise; await the result before using "
                f"it (e.g. `await {helper}(...)`)."
            )
    return problems[:6]


def locators_with_invalid_name_option(repo_root: str | Path) -> list[str]:
    """Where the suite passes a locator an option it ignores. See the pack's `locators_with_an_ignored_option`."""
    found = contract.the_pack(repo_root)
    if found is None or found[0].locators_with_an_ignored_option is None:
        return []
    root = Path(repo_root)
    problems = []
    for path in suite_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hits = list(found[0].locators_with_an_ignored_option(text))
        if not hits:
            continue
        lines = text.splitlines()
        snippet = lines[hits[0] - 1].strip()[:160] if 0 < hits[0] <= len(lines) else ""
        where = ", ".join(str(line) for line in hits[:8]) + (" ..." if len(hits) > 8 else "")
        problems.append(
            f"`{path.relative_to(root).as_posix()}` line(s) {where} (`{snippet}`) calls "
            "`locator(..., { name: ... })`. `locator()` does not accept a name option; "
            "use `getByRole('role', { name: '...' })` or `locator('...', { hasText: '...' })` instead."
        )
    return problems[:6]


#: A key of a `fetch`-style options object, which Playwright's `request` fixture does not read.
_BODY_KEY = re.compile(r"\bbody\s*:")
_FETCH_STYLE_SIBLING = re.compile(r"\b(?:method|headers)\s*:")
_JSON_KEY = re.compile(r"\bjson\s*:")
#: The text just before an options object handed straight to the fixture: `request.post('/x', ` and the like.
_OPTIONS_OF_A_FIXTURE_CALL = re.compile(
    r"\brequest\s*\.\s*(?:post|put|patch|delete|fetch|get|head)\s*\((?:[^;{}]|\$\{[^}]*\})*,\s*$"
)
_USES_THE_REQUEST_FIXTURE = re.compile(r"\brequest\s*\.\s*(?:post|put|patch|delete|fetch|get|head)\s*\(")


def _the_object_around(text: str, at: int) -> str:
    """The object literal `{ ... }` that holds position `at`, or ""."""
    depth = 0
    start = -1
    for i in range(at, -1, -1):
        ch = text[i]
        if ch == "}":
            depth += 1
        elif ch == "{":
            if depth == 0:
                start = i
                break
            depth -= 1
    if start < 0:
        return ""
    depth = 0
    for j in range(start, min(len(text), start + 4_000)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[start:j + 1]
    return ""


def requests_with_a_fetch_body(repo_root: str | Path) -> list[str]:
    """Tests that hand Playwright's `request` fixture a `fetch`-style `body:`, which it does not read.

    Measured on two runs of a small model: every write in the locked suite was `request.fetch(url, { method: 'POST',
    headers: {...}, body: JSON.stringify(note) })` - Playwright's request API takes `data`, so the service received no
    body and answered 400; the whole suite was red on a product that passed every hidden test, and the run was stopped
    as failed after the fixers were spent on it. The misuse is found by its shape: an object literal with a `body:` and a
    `method:` or `headers:` beside it, in a file that calls the `request` fixture.
    """
    root = Path(repo_root)
    problems: list[str] = []
    for path in suite_files(repo_root):
        if path.suffix.lower() not in (".js", ".mjs", ".cjs", ".ts", ".mts", ".cts"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not _USES_THE_REQUEST_FIXTURE.search(text):
            continue
        lines: list[int] = []
        as_json: list[int] = []
        for match in _BODY_KEY.finditer(text):
            literal = _the_object_around(text, match.start())
            if literal and _FETCH_STYLE_SIBLING.search(literal):
                lines.append(text.count("\n", 0, match.start()) + 1)
        # `json:` is `route.fulfill`'s option, not the request fixture's: `request.post(path, { json: note })`
        # sends no body either. Measured on a small-model run: QA rewrote a working `data:` as `json:`.
        for match in _JSON_KEY.finditer(text):
            opening = text.rfind("{", 0, match.start())
            if opening >= 0 and not text[opening + 1:match.start()].strip() and _OPTIONS_OF_A_FIXTURE_CALL.search(
                text[max(0, opening - 300):opening]
            ):
                as_json.append(text.count("\n", 0, match.start()) + 1)
        named = "`json:`" if as_json and not lines else "`body:` in fetch-style options"
        lines = sorted(set(lines + as_json))
        if not lines:
            continue
        where = ", ".join(str(n) for n in lines[:8]) + (" ..." if len(lines) > 8 else "")
        problems.append(
            f"`{path.relative_to(root).as_posix()}` line(s) {where}: a request body is passed as {named}, "
            "which Playwright's `request` fixture does not read - the service receives no body "
            "and answers 400, on every product (a `json:` option is not read either; only `route.fulfill` has one). "
            "Send it as `data: { ... }` (`request.post(path, { data: note })`); `headers` may stay, `method` is the "
            "function's name."
        )
    return problems[:6]


#: A response the `request` fixture returned: `const res = await request.post(...)`.
_A_FIXTURE_RESPONSE = re.compile(
    r"\b(?:const|let|var)\s+(\w+)\s*=\s*await\s+request\s*\.\s*(?:post|put|patch|delete|fetch|get|head)\s*\("
)
#: What Playwright's response has as methods; read without the call each is a function, never the value.
_RESPONSE_METHODS = ("status", "ok", "statusText", "headers")


def responses_read_without_the_call(repo_root: str | Path) -> list[str]:
    """Tests that read the `request` fixture's `status`, `ok`, `statusText` or `headers` as a property.

    Measured on a small-model run: `expect(response.status).toBe(201)` beside `expect(resp.status()).toBe(200)` in the
    same file. On Playwright's response these are methods, so the assertion compares a function with 201 and fails on
    every product - a red test charged to the product. Found by its shape: a name assigned from `await request.<verb>(`
    read as `<name>.status` with no call after it.
    """
    root = Path(repo_root)
    problems: list[str] = []
    for path in suite_files(repo_root):
        if path.suffix.lower() not in (".js", ".mjs", ".cjs", ".ts", ".mts", ".cts"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        names = sorted(set(_A_FIXTURE_RESPONSE.findall(text)))
        if not names:
            continue
        uncalled = re.compile(
            rf"\b(?:{'|'.join(map(re.escape, names))})\s*\.\s*(?:{'|'.join(_RESPONSE_METHODS)})\b(?!\s*\()"
        )
        lines = sorted({text.count("\n", 0, match.start()) + 1 for match in uncalled.finditer(text)})
        if not lines:
            continue
        where = ", ".join(str(n) for n in lines[:8]) + (" ..." if len(lines) > 8 else "")
        problems.append(
            f"`{path.relative_to(root).as_posix()}` line(s) {where}: a response from the `request` fixture is read as "
            "`.status`, `.ok`, `.statusText` or `.headers` without calling it. On Playwright's response these are "
            "methods, so the assertion compares a function and fails on every product. Call it: `res.status()`."
        )
    return problems[:6]


#: A plain `fetch(` call - not the fixture's `request.fetch(` - with the text up to its options object.
_OPTIONS_OF_A_FETCH_CALL = re.compile(r"(?<![.\w])fetch\s*\((?:[^;{}]|\$\{[^}]*\})*,\s*$")
_DATA_KEY = re.compile(r"\bdata\s*:")
#: A response `fetch` returned: `const res = await fetch(...)`.
_A_FETCH_RESPONSE = re.compile(r"\b(?:const|let|var)\s+(\w+)\s*=\s*await\s+fetch\s*\(")
#: On a `fetch` response these are values, not methods: called, each throws "is not a function".
_FETCH_RESPONSE_VALUES = ("status", "ok", "statusText")


def fetch_calls_written_like_the_fixture(repo_root: str | Path) -> list[str]:
    """Tests that call `fetch` the way Playwright's `request` fixture is called: a `data:` body, or `res.status()`.

    The mirror of `requests_with_a_fetch_body` and `responses_read_without_the_call`. Measured on two runs of a
    small model, in the test that restarts the service and so calls `fetch` itself: one passed its body as
    `data: {...}`, which `fetch` does not send - the product answered 400 - and one called `res.status()`, a number on
    a `fetch` response. Each was found only after the suite was locked, spent its repairs, and its criteria shipped
    unproven.
    """
    root = Path(repo_root)
    problems: list[str] = []
    for path in suite_files(repo_root):
        if path.suffix.lower() not in (".js", ".mjs", ".cjs", ".ts", ".mts", ".cts"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        shown = path.relative_to(root).as_posix()
        as_data = []
        for match in _DATA_KEY.finditer(text):
            opening = text.rfind("{", 0, match.start())
            literal = _the_object_around(text, match.start())
            # Its own keys only: a note sent as `data: { title, body }` has a `body:` of its own.
            own = literal[1:-1]
            while re.search(r"\{[^{}]*\}", own):
                own = re.sub(r"\{[^{}]*\}", "", own)
            if opening >= 0 and literal and not _BODY_KEY.search(own) and _OPTIONS_OF_A_FETCH_CALL.search(
                text[max(0, opening - 300):opening]
            ):
                as_data.append(text.count("\n", 0, match.start()) + 1)
        if as_data:
            problems.append(
                f"`{shown}` line(s) {', '.join(map(str, sorted(set(as_data))[:8]))}: a `fetch` call passes its body as "
                "`data:`, which only Playwright's `request` fixture reads - `fetch` sends no body, and the service "
                "answers 400 on every product. With `fetch`, send `body: JSON.stringify(...)` with a "
                "`'Content-Type': 'application/json'` header."
            )
        names = sorted(set(_A_FETCH_RESPONSE.findall(text)))
        if names:
            called = re.compile(
                rf"\b(?:{'|'.join(map(re.escape, names))})\s*\.\s*(?:{'|'.join(_FETCH_RESPONSE_VALUES)})\s*\("
            )
            lines = sorted({text.count("\n", 0, m.start()) + 1 for m in called.finditer(text)})
            if lines:
                problems.append(
                    f"`{shown}` line(s) {', '.join(map(str, lines[:8]))}: a `fetch` response's `status`, `ok` or "
                    "`statusText` is called like a method. On a `fetch` response these are values, so the call throws "
                    "on every product. Read it without the call: `res.status`."
                )
    return problems[:6]


def is_an_acceptance_run(repo_root: str | Path, entry: Any) -> bool:
    """Whether a ledger entry is a run of the locked acceptance suite.

    The suite runs red by design until the last sprint: it holds every
    criterion, and a sprint delivers some of them. Checks that read the
    ledger's last test run as "the sprint's suite" must leave these runs to the
    acceptance gate, which judges them criterion by criterion. One run's first
    sprint was sent back three times, and escalated, because the last run in
    the ledger was the acceptance suite failing on later sprints' criteria.
    """
    if not is_locked(repo_root):
        return False
    argv = [str(part) for part in (entry.get("command") if isinstance(entry, dict) else None) or []]
    if not argv:
        return False
    command = _command(repo_root)
    if command is not None and argv == [str(part) for part in command[0]]:
        return True
    where = location(repo_root)
    if where is None:
        return False
    acceptance_dir = where[1].strip("/")
    return any(
        part.rstrip("/").endswith(acceptance_dir) or f"{acceptance_dir}/" in part
        for part in argv[1:]
    )


def last_result(repo_root: str | Path) -> dict[str, Any]:
    try:
        return json.loads((Path(repo_root) / RESULT_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# --- change requests ----------------------------------------------------------

def add_change_request(repo_root: str | Path, text: str) -> str:
    """Record a requested change as CR-n, to be proven by its own test."""
    state = _state(repo_root)
    requests: dict[str, str] = dict(state.get("change_requests") or {})
    change_id = f"CR-{len(requests) + 1}"
    requests[change_id] = text.strip()
    state["change_requests"] = requests
    _save_state(repo_root, state)
    return change_id


def change_requests(repo_root: str | Path) -> dict[str, str]:
    return dict(_state(repo_root).get("change_requests") or {})


def tests_that_cannot_pass(repo_root: str | Path, result: AcceptanceResult) -> list[str]:
    """Locked tests no product can pass, by every check that says so; one list for every caller.

    The review that locks the suite and each test round kept a list each, and
    the round's lacked four of the review's checks. A review that has spent its
    rounds locks the suite with its problems open, so a test only the review
    named - one holding the product to an order no criterion states - was then
    failed against the product and charged to it as a defect no fix could
    close. Checks that make a suite too lenient are not here: a suite that
    passes too much never charges the product for anything, so they stay with
    the review.
    """
    return [
        *tests_that_broke_themselves(repo_root, result),
        *tests_that_need_what_they_never_made(repo_root, result),
        *assertions_that_do_not_exist(repo_root),
        *locators_that_do_not_exist(repo_root),
        *locators_by_a_name_the_role_never_has(repo_root),
        *locators_with_invalid_name_option(repo_root),
        *requests_with_a_fetch_body(repo_root),
        *responses_read_without_the_call(repo_root),
        *fetch_calls_written_like_the_fixture(repo_root),
        *tests_that_never_open_the_page(repo_root),
        *tests_that_access_storage_before_opening_the_page(repo_root),
        *tests_that_expect_what_they_never_gave(repo_root),
        *tests_that_assert_an_unstated_order(repo_root),
        *locators_that_contradict_their_assertions(repo_root),
        *tests_with_module_system_mismatch(repo_root),
        *tests_with_unawaited_async_helpers(repo_root),
    ]
