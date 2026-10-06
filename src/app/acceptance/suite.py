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
    root = directory(repo_root)
    if root is None or not root.is_dir():
        return []
    return sorted(
        path for path in root.rglob("*")
        if path.is_file() and not (set(path.relative_to(root).parts) & _NOT_THE_SUITE)
    )


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
        f"{c.id} (\"{c.text}\") has no test whose name carries `{c.id}`."
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
    """Freeze the suite as it stands. Returns {relative path: checksum}."""
    root = Path(repo_root)
    snapshot = root / SNAPSHOT_DIR
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
    _save_state(repo_root, state)
    return checksums


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
    for relative, wanted in checksums.items():
        target = root / relative
        source = snapshot / relative
        if target.is_file() and _digest(target) == wanted:
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
            "runtime_problems": self.runtime_problems,
            "shows": self.shows,
            "phone_overflow": self.phone_overflow,
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
    command = _command(repo_root)
    if command is None:
        result = AcceptanceResult(ran=False, repairs=repairs, problem="no command is known for this suite")
        return _judged(repo_root, result, save)
    argv, report_path, project = command
    report_file = Path(repo_root) / project / report_path
    report_file.unlink(missing_ok=True)
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
    result.runtime_problems, result.shows = _read_runtime_report(runtime_file)
    result.phone_overflow = _read_phone_overflow(runtime_file)
    result.accessibility = _read_accessibility(runtime_file)
    _with_the_pages_they_failed_on(repo_root, project, result)
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
            })
    return kept[:10]


def _judged(repo_root: str | Path, result: AcceptanceResult, save: bool) -> AcceptanceResult:
    excused = deferred(repo_root)
    by_tag: dict[str, list[junit.TestResult]] = {}
    for test in result.report.tests:
        for tag in test.tags:
            by_tag.setdefault(tag, []).append(test)

    def judge(item_id: str, text: str) -> CriterionResult:
        tests = by_tag.get(item_id, [])
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
            path.write_text(json.dumps(result.as_dict(), indent=2) + "\n", encoding="utf-8")
        except OSError:
            logger.debug("Could not save the acceptance result", exc_info=True)
    return result


def tests_that_broke_themselves(repo_root: str | Path, result: AcceptanceResult) -> list[str]:
    """Failures caused by the tests' own code, by the pack's own patterns.

    Before the product is built every test fails, so "it fails" says nothing;
    why it fails says a lot. A missing control, endpoint or function is the
    product not existing yet. An error the test's own code throws means the
    test can never pass, whatever is built - and a suite locked with one is a
    definition of done no product can meet.
    """
    found = contract.the_pack(repo_root)
    if found is None or not found[0].test_bugs:
        return []
    patterns = [re.compile(pattern, re.I | re.M) for pattern in found[0].test_bugs]
    broken = []
    for test in result.report.tests:
        if test.outcome != "failed":
            continue
        message = test.message or ""
        if any(pattern.search(message) for pattern in patterns):
            first = next((line.strip() for line in message.splitlines() if line.strip()), "")
            broken.append(
                f"`{test.name}` fails because of an error in the test's own code, not because the "
                f"product is unbuilt: {first[:300]}. Fix the test so that it can pass once the "
                "product works."
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
            "runner's report at all, so its criterion is untested whatever is built. A test "
            "written inside another test's body, or after a block left unclosed, is never "
            "collected. Make it a test of its own."
        )
    return missing


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


#: An assertion call in a test: `.toBeVisible(`, `.not.toHaveText(`.
_ASSERTION_CALL = re.compile(r"\.(to[A-Z][A-Za-z]*)\s*\(")


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
            if match.group(1) in known:
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
        for pattern in patterns:
            match = pattern.search(text)
            if match is None:
                continue
            line = text.count("\n", 0, match.start()) + 1
            snippet = text.splitlines()[line - 1].strip()[:160]
            problems.append(
                f"`{path.relative_to(root).as_posix()}` line {line} finds a control by something no "
                f"person sees (`{snippet}`). Find it by the label or name the brief gives it, "
                "exactly; where the brief gives none, by its role and the name a person reads."
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
