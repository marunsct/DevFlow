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
from dataclasses import dataclass, field
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
            rows.append(line)
        head = (
            f"Acceptance suite (`{self.command}`): {self.report.passed} passed, "
            f"{self.report.failed} failed, {self.report.skipped} skipped."
        )
        return head + ("\n" + "\n".join(rows) if rows else "")

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
    return _judged(repo_root, result, save)


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
