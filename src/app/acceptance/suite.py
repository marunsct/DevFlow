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
import time
import xml.etree.ElementTree as ET
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
#: Every saved measurement, one line each: when, what product (its fingerprint), and how it fared.
HISTORY_FILE = f"{contract.HARNESS_DIR}/acceptance-history.jsonl"

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
        and path != report and not (path.suffix == ".xml" and junit.read(path).tests)
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


def undefer_what_a_test_now_carries(repo_root: str | Path) -> list[str]:
    """Take off the deferred list the criteria some test's title now carries; the ids taken off. Never raises.

    QA defers a criterion when no test names it. Measured on a held-out run: QA deferred AC-14 and AC-15 in its first
    round, wrote two tests titled `[AC-14][AC-15]` in a later one, and the deferral stayed - the suite locked with a
    note saying the reason no longer held, and the release listed both as shipped unproven. Called as the suite is
    locked, so a deferral the harness makes later, for a criterion whose test fails, is not touched.
    """
    try:
        carried = coverage(repo_root)
        stale = sorted(cid for cid in deferred(repo_root) if carried.get(cid))
        if stale:
            undefer(repo_root, stale)
        return stale
    except Exception:  # noqa: BLE001 - a deferral that stays is what it was
        return []


def undefer(repo_root: str | Path, ids: list[str]) -> None:
    """Take criteria off the deferred list: a later measurement proved them (`last_try_on_deferred`)."""
    state = _state(repo_root)
    state["deferred"] = {c: why for c, why in (state.get("deferred") or {}).items() if c not in set(ids)}
    _save_state(repo_root, state)
    from app.acceptance.criteria import render

    doc = Path(repo_root) / "docs" / "acceptance_criteria.md"
    if doc.parent.is_dir():
        doc.write_text(render(criteria(repo_root), state["deferred"]), encoding="utf-8")


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
    state.pop("before_repair", None)
    state.pop("repair_bodies", None)
    _save_state(repo_root, state)
    return checksums


#: The mark in `repairing` for a repair that adds criterion ids to the names of tests it could not list first.
NAMING_REPAIR = "(criterion ids added to test names)"
#: How the deferrals the harness makes begin (`escalation`, `defer_what_is_beyond_repair`), as against a reason QA gave.
DEFERRED_BY_THE_HARNESS = ("could not be made to pass", "its locked test cannot pass")


#: Where QA's "the product is at fault" claims are kept in the suite's state (`graph.product_at_fault._CLAIMS`).
PRODUCT_AT_FAULT_CLAIMS = "product_at_fault_claims"
#: A Python test function and its body, to the next top-level definition.
_A_PYTHON_TEST_BODY = re.compile(r"^(?:async\s+)?def\s+(test_\w+)\s*\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)", re.M | re.S)


def _test_bodies(repo_root: str | Path) -> dict[str, str]:
    """Each acceptance test's own code by its name: the spec's title, or a Python test function's name."""
    found = {name: body for name, (body, _) in _the_tests_sources(repo_root).items()}
    for path in suite_files(repo_root):
        if path.suffix.lower() != ".py":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in _A_PYTHON_TEST_BODY.finditer(text):
            found.setdefault(match.group(1), match.group(0))
    return found


def tests_left_unrepaired(repo_root: str | Path) -> list[str]:
    """The tests a repair was sent for whose code it has not changed, as one problem; [] when none or no repair is open.

    Measured on one run: a repair sent for three tests a dispute ruled wrong changed one file and left two of the
    three as they were; locked again, the ruled-wrong test failed the rest of the run and a right product was escalated.
    """
    state = _state(repo_root)
    sent = state.get("repair_bodies") or {}
    if not sent:
        return []
    # A test QA examined and says is right - the product is at fault (`graph.product_at_fault`) - is left unchanged
    # on purpose, and is judged by that claim, not here.
    vouched = " ".join(str(claim) for claim in state.get(PRODUCT_AT_FAULT_CLAIMS) or ())
    now = _test_bodies(repo_root)
    left = [name for name, body in sent.items()
            if name in now and now[name].strip() == str(body).strip() and name not in vouched]
    if not left:
        return []
    return [
        "This repair was sent for " + ", ".join(f"`{name}`" for name in left) + " and has not changed "
        + ("it" if len(left) == 1 else "them") + ": each is exactly as it was locked. Repair each as its finding says - "
        "the fault named is in that test's own code."
    ]


def repairing(repo_root: str | Path, tests: list[str]) -> None:
    """Record the tests a reopened suite is being repaired for, until it is locked again."""
    state = _state(repo_root)
    state["repairing"] = sorted({*state.get("repairing", []), *(str(t) for t in tests if str(t).strip())})
    # Each named test's code as the repair began, so the lock can tell one it never changed (`tests_left_unrepaired`).
    bodies = _test_bodies(repo_root)
    kept = dict(state.get("repair_bodies") or {})
    for name in tests:
        if str(name) in bodies and str(name) not in kept:
            kept[str(name)] = bodies[str(name)]
    if kept:
        state["repair_bodies"] = kept
    if "before_repair" not in state:
        # What the locked suite measured before anything was changed, for `a_repair_that_made_it_worse`.
        last = last_result(repo_root)
        if last.get("ran"):
            passed, failed = int(last.get("passed") or 0), int(last.get("failed") or 0)
            state["before_repair"] = {"tests": passed + failed, "passed": passed}
    _save_state(repo_root, state)


def a_repair_that_made_it_worse(repo_root: str | Path, result: AcceptanceResult) -> str:
    """What a repair of a locked suite lost, measured against the suite before it; "" when it lost nothing.

    Measured on two runs: a repair sent for a few tests went from one open problem to three, and another dropped
    twenty browser tests from the run; one ended with a criterion deferred and its hidden test failed. A repair may
    change the tests it was sent for; it may not leave the suite running or passing less than it did.
    """
    before = _state(repo_root).get("before_repair") or {}
    if not before or not is_being_repaired(repo_root) or not result.ran:
        return ""
    tests = len(result.report.tests)
    passed = sum(1 for test in result.report.tests if test.outcome == "passed")
    if tests >= int(before.get("tests") or 0) and passed >= int(before.get("passed") or 0):
        return ""
    return (
        f"The repair left the suite worse than it was: it now runs {tests} test(s) and {passed} pass, where before the "
        f"repair it ran {before.get('tests')} and {before.get('passed')} passed. The suite as it was locked has been "
        "put back. Change only the tests named for repair, and keep every other test running as it was."
    )


def put_back_the_suite_before_the_repair(repo_root: str | Path) -> list[str]:
    """Put back every file of the suite as it was last locked, and remove what was added since. One line per file."""
    root = Path(repo_root)
    snapshot = root / SNAPSHOT_DIR
    if not snapshot.is_dir():
        return []
    kept = {path.relative_to(snapshot).as_posix() for path in snapshot.rglob("*") if path.is_file()}
    repairs = []
    for relative in sorted(kept):
        target = root / relative
        source = snapshot / relative
        if target.is_file() and _digest(target) == _digest(source):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        repairs.append(f"{relative} is back as it was locked.")
    for path in suite_files(repo_root):
        relative = path.relative_to(root).as_posix()
        if relative not in kept:
            path.unlink(missing_ok=True)
            repairs.append(f"{relative} was added by the repair and has been removed.")
    return repairs


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
    # A repair that adds an id to a name drops the old name: only one that leaves fewer tests is dropping any.
    if NAMING_REPAIR in under_repair and len(_declared_in(content) - _skipped_in(content)) >= len(before):
        return []
    return sorted(
        name for name in before - (_declared_in(content) - _skipped_in(content))
        if not any(name == test or name in test or test in name for test in under_repair)
    )


#: How few of a repaired test's assertions may remain, as a share of what it had: a repair may drop the wrong one.
LEAST_ASSERTIONS_KEPT = 0.5


#: A Python test function, at any indent (inside a `Test` class too): its name.
_A_PYTHON_TEST = re.compile(r"^[ \t]*(?:async[ \t]+)?def[ \t]+(test_\w+)[ \t]*\(", re.M)
#: A Python assertion: an `assert` statement or a `pytest.raises` block.
_A_PYTHON_ASSERTION = re.compile(r"^[ \t]*assert\b|\bpytest\.raises\s*\(", re.M)


def _the_tests_of(text: str) -> tuple[str, dict[str, str]]:
    """A suite file as its text before the first test, and {title: the test's text} for each test after.

    A JavaScript test by its `test(` call and title; a Python one by its `def test_...` name. Measured on the held-out
    family: its suite was Python, nothing here matched, the whole file read as text before the first test, and a
    repair that changed only its own tests was reviewed whole as though it had changed everything.
    """
    starts = [m.start() for m in _A_TEST_CALL.finditer(text)]
    titles = None
    if not starts:
        found = list(_A_PYTHON_TEST.finditer(text))
        starts, titles = [m.start() for m in found], [m.group(1) for m in found]
    if not starts:
        return text, {}
    tests: dict[str, str] = {}
    for at, start in enumerate(starts):
        block = text[start:starts[at + 1] if at + 1 < len(starts) else len(text)]
        if titles is not None:
            tests[titles[at]] = block
            continue
        titled = _A_TEST_TITLE.match(block)
        tests[titled.group(1) if titled else f"#{at}"] = block
    return text[:starts[0]], tests


def _assertions_in(block: str) -> int:
    """How many checks a test's text makes: `expect(` calls, or Python's `assert` lines and `pytest.raises`."""
    return block.count("expect(") + len(_A_PYTHON_ASSERTION.findall(block))


def only_the_repaired_tests_changed(repo_root: str | Path) -> bool:
    """Whether a reopened suite differs from its last lock only in the tests sent for repair, each still a check.

    Measured on one run: a repair sent for one test fixed it in a minute; the full review that followed raised four
    new findings about other tests, and locking again took fourteen minutes. What the review approved at the lock is
    unchanged, so a repair that changed only its own tests - same files, same text before the tests, the same tests
    by title (so with their criterion tags), each changed one under repair and keeping at least half its assertions - is judged
    by the harness's checks alone. Never raises.
    """
    try:
        state = _state(repo_root)
        under_repair = [str(name) for name in state.get("repairing") or []]
        if "lock" in state or not under_repair:
            return False
        root = Path(repo_root)
        locked = _the_files_of(root / SNAPSHOT_DIR)
        now = {path.relative_to(root).as_posix(): path.read_text(encoding="utf-8", errors="replace")
               for path in suite_files(repo_root)}
        if not locked or set(locked) != set(now):
            return False
        changed_any = False
        for name, text in now.items():
            if text == locked[name]:
                continue
            before_head, before = _the_tests_of(locked[name])
            after_head, after = _the_tests_of(text)
            if before_head != after_head or set(before) != set(after):
                return False
            for title, block in after.items():
                if block == before[title]:
                    continue
                if not any(title == test or title in test or test in title for test in under_repair):
                    return False
                had, has = _assertions_in(before[title]), _assertions_in(block)
                if has < 1 or has < had * LEAST_ASSERTIONS_KEPT:
                    return False
                changed_any = True
        return changed_any
    except Exception:  # noqa: BLE001 - then the review reads it whole, as before
        return False


class _TargetedSuiteRepair:
    """`TARGETED_SUITE_REPAIR` as the switch registry reads one: off in code, the compose file turns it on."""

    ON_BY_DEFAULT = False
    #: What the admin page says this switch does.
    explanation = ("A reopened suite whose repair changed only the tests sent for repair - each still tagged and still "
                   "asserting - is locked again on the harness's checks, without a second full review. Measured on one "
                   "run, that review raised four new findings and re-locking took fourteen minutes.")

    @staticmethod
    def enabled() -> bool:
        from app.switches import is_on

        return is_on("TARGETED_SUITE_REPAIR", _TargetedSuiteRepair.ON_BY_DEFAULT)


targeted_repair_switch = _TargetedSuiteRepair()


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


def is_being_repaired(repo_root: str | Path) -> bool:
    """Whether a suite locked before is open for repair: a product has been measured against it."""
    state = _state(repo_root)
    return "lock" not in state and bool(state.get("repairing"))


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
    #: The errors the product's server logged while the suite ran, from the whole output (`what_the_server_logged`).
    server_log: str = ""
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
            "server_log": self.server_log,
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
    runs = _the_runs(declared)
    if runs:
        return runs[0][0], runs[0][1], where[0]
    argv = declared.get("command") if isinstance(declared, dict) else None
    report = declared.get("report") if isinstance(declared, dict) else None
    if not (isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv) and isinstance(report, str)):
        return None
    return argv, report, where[0]


#: The shape a suite's own declaration of how it runs must have.
_THE_DECLARED_SHAPE = '{"command": ["<executable>", "<argument>", ...], "report": "<file>"}'
_SEVERAL_RUNNERS = (
    'when the suite needs several runners, list each with its own report under `runs`: {"runs": [{"command": [...], '
    '"report": "<file>"}, ...]}; each runs in turn and the harness reads each report as it finishes'
)


def _the_runs(declared: Any) -> list[tuple[list[str], str]]:
    """The (argv, report) of each runner a `run.json` lists under `runs`; [] when it lists none or any is unusable."""
    listed = declared.get("runs") if isinstance(declared, dict) else None
    if not isinstance(listed, list):
        return []
    runs: list[tuple[list[str], str]] = []
    for item in listed:
        argv = item.get("command") if isinstance(item, dict) else None
        report = item.get("report") if isinstance(item, dict) else None
        if not (isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv)):
            return []
        if not isinstance(report, str) or not report.strip() or report.rstrip().endswith("/"):
            return []
        runs.append((argv, report))
    return runs


def _what_the_declaration_gets_wrong(declared: Any) -> str:
    """What makes a parsed `run.json` unusable, naming the shape; "" when nothing does."""
    if not isinstance(declared, dict):
        return f"must be one JSON object, {_THE_DECLARED_SHAPE}"
    if "runs" in declared:
        return "" if _the_runs(declared) else (
            "`runs` must list at least one runner, each with a `command` as a list of strings and a `report` file: "
            + _SEVERAL_RUNNERS)
    wrong: list[str] = []
    argv = declared.get("command")
    if not (isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv)):
        wrong.append(
            "`command` must be one command as a list of strings"
            + (f" - not a `commands` list: {_SEVERAL_RUNNERS}" if "commands" in declared else "")
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


#: How a suite runner marks what the product's server printed: Playwright's `webServer` prefix.
_A_SERVER_LINE = re.compile(r"^\[WebServer\] ?(.*)$")
#: A server line that states an error, and a stack frame.
_STATES_AN_ERROR = re.compile(r"\b(?:\w*Error|Exception|Traceback|panic|FATAL)\b")
_A_FRAME = re.compile(r"^\s*at\s")
#: Lines of the server's log a defect carries, at most.
MOST_SERVER_LINES = 12


def what_the_server_logged(output: str) -> str:
    """The errors the product's server logged while the suite ran, with their frames in the product's own files; "".

    Measured on one run: `POST /notes` answered 500 and the server logged `Error: Internal server error at
    NotesRepository.save (src/services/persistence.ts:44)` under Playwright's `[WebServer]` prefix; no fixer was
    shown it, and five in a row changed nothing or chased the tests.
    """
    kept: list[str] = []
    for line in str(output or "").splitlines():
        match = _A_SERVER_LINE.match(line.strip())
        if match is None:
            continue
        text = match.group(1).rstrip()
        if _A_FRAME.match(text):
            if "node_modules" in text or "node:internal" in text or not kept:
                continue
        elif not _STATES_AN_ERROR.search(text):
            continue
        if text not in kept:
            kept.append(text)
        if len(kept) >= MOST_SERVER_LINES:
            break
    return "\n".join(part for part in ("\n".join(kept)[:1_500], what_a_stopped_service_wrote(output)) if part)


#: The most of a stopped service's report a defect carries: its own 2,000 characters of output and the line before them.
STOPPED_SERVICE_CHARS = 2_200


def what_a_stopped_service_wrote(output: str) -> str:
    """The restart helper's last report of a service that stopped by itself under a test, with what it wrote; "".

    Measured on one run: a test saw only a closed connection and the report sat in the suite's output, which no fixer is
    shown, while the service's own fatal error named the cause.
    """
    from app.stacks.packs._service import SERVICE_STOPPED_BY_ITSELF  # noqa: PLC0415 - a pack's text, read here alone

    text = str(output or "")
    at = text.rfind(SERVICE_STOPPED_BY_ITSELF)
    return text[at:at + STOPPED_SERVICE_CHARS].strip() if at >= 0 else ""


#: Folders whose XML is no suite's report.
_NOT_THE_SUITE_S = frozenset({"node_modules", ".venv", "venv", ".git", "__pycache__", "site-packages"})


#: A runner's own count of what it ran: `5 failed`, `2 passed`, `12 tests`.
_TESTS_COUNTED = re.compile(r"\b\d+\s+(?:passed|failed|tests?)\b", re.I)


def _no_report(project_dir: Path, report_path: str, started: float, command: str = "", output: str = "") -> str:
    """Why a run left no report: where it was looked for and the JUnit files this run did write.

    Measured on one run: the browser runner ran every test and printed its counts, but its command asked for the report
    in a form the runner does not read; five rounds were told only where the report was missing, and the run failed.
    """
    written: list[str] = []
    if project_dir.is_dir():
        for found in sorted(project_dir.rglob("*.xml")):
            try:
                relative = found.relative_to(project_dir)
                if _NOT_THE_SUITE_S & set(relative.parts) or found.stat().st_mtime < started:
                    continue
                if junit.read(found).tests:
                    written.append(f"`{relative.as_posix()}`")
            except OSError:
                continue
    problem = f"the runner wrote no report at `{report_path}`, relative to the project, which is where `report` says it is"
    if written:
        problem += f". This run did write {', '.join(written[:5])}"
    if command and _TESTS_COUNTED.search(_AN_ANSI_COLOUR.sub("", output or "")):
        from app.plugins.seed import JUNIT_REPORTS  # noqa: PLC0415 - the runners' own forms are the seed's to know

        problem += (
            f". `{command}` ran its tests - its output counts them - and still wrote nothing there, so the fault is how "
            f"that command asks for its report, not the tests. {JUNIT_REPORTS}"
        )
    return (
        problem + f". A runner that empties its output folder deletes a report another runner left there: {_SEVERAL_RUNNERS}; "
        "its output is below"
    )


def _declared_runs(repo_root: str | Path) -> list[tuple[list[str], str]]:
    """The runners this suite's `run.json` lists, when it lists more than one and no pack decides; else []."""
    suite_dir = directory(repo_root)
    if suite_dir is None or contract.the_pack(repo_root) is not None:
        return []
    try:
        runs = _the_runs(json.loads((suite_dir / DECLARED_COMMAND_FILE).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return []
    return runs if len(runs) > 1 else []


def _run_each(
    runs: list[tuple[list[str], str]], run_one: Runner, project: str, project_dir: Path,
) -> tuple[dict[str, Any], str]:
    """Run each runner, reading its report as it finishes: a later runner may empty the folder it sits in.

    Every test goes into the first runner's report, which is what the rest of the harness reads. Returns the combined
    outcome and the report no run wrote, or "" when each wrote its own.
    """
    code, said, suites, missing = 0, [], [], ""
    for argv, report_path in runs:
        report_file = project_dir / report_path
        junit.clear(report_file)
        outcome = run_one(argv, "test", project)
        try:
            code = max(code, int(str(outcome.get("returncode", "1")).strip() or 1))
        except ValueError:
            code = max(code, 1)
        said.extend(str(outcome.get(k)) for k in ("error", "stdout", "stderr") if outcome.get(k))
        try:
            root = ET.fromstring(report_file.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ET.ParseError):
            missing = missing or report_path
            continue
        suites.extend(list(root) if root.tag == "testsuites" else [root])
    first = project_dir / runs[0][1]
    junit.clear(first)
    if not missing:
        whole = ET.Element("testsuites")
        whole.extend(suites)
        first.parent.mkdir(parents=True, exist_ok=True)
        first.write_bytes(ET.tostring(whole, encoding="utf-8"))
    return {"returncode": str(code), "stdout": "\n".join(said)}, missing


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
    several = _declared_runs(repo_root)
    shown = " && ".join(" ".join(each) for each, _ in several) or " ".join(argv)
    if not repairs:
        # Nothing was put back or installed, and the product is as it was when last measured: that run stands (MEASURE_ONCE).
        from app.acceptance.measured_once import saved_run_if_unchanged

        kept = saved_run_if_unchanged(repo_root, shown, report_file)
        if kept is not None:
            if save:
                # The product's own start is asked of a reused measurement too. Measured on one run: the setup wrote
                # the whole product, nothing changed after the lock, and every later measurement - the release's
                # included - reused the one taken just before the lock, when this check does not run; `start.sh`
                # ran a bare `python3` without the framework, and the product scored 0 of 9 with 33 of 33 locked.
                _the_product_s_own_start(repo_root, kept)
            return _judged(repo_root, kept, save)
    junit.clear(report_file)
    runtime_file = _runtime_report(repo_root, project)
    if runtime_file is not None:
        runtime_file.unlink(missing_ok=True)
    started = time.time() - 1
    run_one = runner or _sandbox_runner(repo_root)
    unwritten_by = " ".join(argv)
    if several:
        outcome, unwritten = _run_each(several, run_one, project, Path(repo_root) / project)
        report_path = unwritten or report_path
        unwritten_by = next((" ".join(each) for each, report in several if report == unwritten), unwritten_by)
    else:
        outcome = run_one(argv, "test", project)
    try:
        code = int(str(outcome.get("returncode", "1")).strip() or 1)
    except ValueError:
        code = 1
    output = "\n".join(str(outcome.get(k) or "") for k in ("error", "stdout", "stderr") if outcome.get(k))
    report = junit.read(report_file)
    result = AcceptanceResult(
        ran=report.found,
        exit_code=code,
        command=shown,
        report=report,
        output=output[-OUTPUT_TAIL_CHARS:],
        server_log=what_the_server_logged(output),
        repairs=repairs,
        problem="" if report.found else _no_report(
            Path(repo_root) / project, report_path, started, unwritten_by, output
        ),
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
        else:
            crashed = the_product_crashed_mid_suite(report, output)
            if crashed:
                result.problem = crashed
    result.runtime_problems, result.shows = _read_runtime_report(runtime_file)
    result.phone_overflow = _read_phone_overflow(runtime_file)
    result.overlaps, result.small_targets = _read_layout_findings(runtime_file)
    result.accessibility = _read_accessibility(runtime_file)
    _with_what_may_hide_it(result)
    _with_the_pages_they_failed_on(repo_root, project, result)
    _with_the_errors_the_service_logged(repo_root, project, result)
    # A measurement the run keeps, not a probe's run on a product broken on purpose.
    if save:
        from app.acceptance import start_output

        start_output.add_to(repo_root, result)
        _the_product_s_own_start(repo_root, result)
    return _judged(repo_root, result, save)


def _the_product_s_own_start(repo_root: str | Path, result: AcceptanceResult) -> None:
    """A green locked suite whose product's own start command fails is a product that did not start.

    A suite's runner may start the product its own way. Measured on one run: `start.sh` passed the server an option it
    does not have, the suite passed 33 of 33, and no test of the benchmark's hidden suite could run.
    """
    from app.acceptance import start_output

    report = result.report
    if result.problem or not report.tests or report.failed or not is_locked(repo_root):
        return
    unusable = start_output.how_it_is_used_fails(repo_root)
    if unusable:
        result.problem = f"{PRODUCT_DID_NOT_START}: {unusable}"
        return
    wrote = start_output.what_it_wrote(repo_root)
    stopped = re.search(r"it stopped by itself with exit code (\d+)", wrote)
    if stopped and int(stopped.group(1)) != 0:
        result.problem = (
            f"{PRODUCT_DID_NOT_START} through its own start command, though the suite's way of starting it passed: "
            f"{wrote}"
        )
        result.server_log = "\n".join(part for part in (str(result.server_log or ""), wrote) if part)


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


#: A browser's word that it found the element and it cannot be seen.
_FOUND_BUT_HIDDEN = re.compile(r"Received:\s*hidden|unexpected value \"hidden\"")
_WHAT_MAY_HIDE_IT = (
    "\nThe element is on the page with its text, and the browser cannot see it. When its own style hides nothing, a "
    "parent is the cause: an element with no width or height counts as hidden, and a parent in a flexible layout can "
    "shrink to nothing. Measure the width of each parent in turn, from the element up, before changing its text or style."
)


def _with_what_may_hide_it(result: AcceptanceResult) -> None:
    """Add to each failure of an element found and hidden where to look: measured, fixers read its own style for hours."""
    report = result.report
    if not any(test.outcome == "failed" and _FOUND_BUT_HIDDEN.search(test.message or "") for test in report.tests):
        return
    result.report = replace(report, tests=[
        replace(test, message=f"{test.message}{_WHAT_MAY_HIDE_IT}")
        if test.outcome == "failed" and _FOUND_BUT_HIDDEN.search(test.message or "") else test
        for test in report.tests
    ])


#: Where a pack's acceptance setup writes what the service printed while the suite ran.
SERVICE_LOG = "test-results/service.log"
MOST_SERVICE_ERRORS = 2
_A_TRACEBACK = "Traceback (most recent call last):"
_A_SERVER_ERROR = re.compile(r"\b50\d\b|Internal Server Error", re.I)
_AN_EXCEPTION_LINE = re.compile(r"^[A-Za-z_][\w.]*(?:Error|Exception|Exit|Warning)\b.*$")
_SERVICE_ERRORS_MARK = "\nThe service logged this while the suite ran:\n"
UNLOGGED_SERVER_ERROR = (
    "- nothing: the service logged no error for this server error. Something in the product answers it without "
    "logging what failed - a catch-all error handler, or a `try` that turns any exception into a 500. Make it log "
    "the exception with its traceback (or let it propagate) first: the next run of the suite then shows the cause "
    "here.\n"
)


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
        if errors:
            added = "".join(f"- {error[:400]}\n" for error in errors)
        elif (Path(repo_root) / project / SERVICE_LOG).is_file():
            # A log was kept and holds no error: the product answered the 500 without logging what failed. Measured
            # on one run: a catch-all error handler returned a bare 500, and fixes went at sign-in blind for an hour.
            added = UNLOGGED_SERVER_ERROR
        else:
            return
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
            _keep_in_the_history(repo_root, result, saved["fingerprint"])
        except OSError:
            logger.debug("Could not save the acceptance result", exc_info=True)
    return result


def _keep_in_the_history(repo_root: str | Path, result: AcceptanceResult, product: str) -> None:
    """Add this measurement to the history; warn when the same product measured worse than it did before.

    Measured on one run: the suite passed 17 of 17, ten minutes later 3 of 17 with not a line of the product changed
    - a compiled copy of a change already undone was running - and only the latest result was kept, so nothing showed
    the fall. The same product cannot honestly measure worse: the place it runs in changed.
    """
    import datetime

    passed = sum(1 for test in result.report.tests if test.outcome == "passed")
    entry = {
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "product": product, "ran": bool(result.ran), "tests": len(result.report.tests), "passed": passed,
    }
    path = Path(repo_root) / HISTORY_FILE
    earlier = [] if not path.is_file() else [
        line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    for line in reversed(earlier):
        try:
            before = json.loads(line)
        except ValueError:
            continue
        if before.get("product") == product and before.get("ran") and result.ran:
            if passed < int(before.get("passed") or 0):
                logger.warning(
                    "The same product measured worse than it did at %s: %d of %d passing, now %d of %d. Nothing in the"
                    " product changed, so what it runs on did - a stale cache, a leftover change or process.",
                    before.get("at"), before.get("passed"), before.get("tests"), passed, entry["tests"],
                )
                entry["worse_than_the_same_product_at"] = before.get("at")
            break
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def same_product_measured_worse(repo_root: str | Path) -> list[dict[str, Any]]:
    """The history's measurements that fared worse than the same product had; [] when none."""
    path = Path(repo_root) / HISTORY_FILE
    found = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("worse_than_the_same_product_at"):
                found.append(entry)
    return found


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


#: A matcher handed a promise turned to text: the test compared the promise, not its value, and no product changes
#: that. Measured on one run: `String(res?.headerValue('content-type'))` failed two right tests against `text/html`.
_A_PROMISE_RECEIVED = re.compile(r"Received(?: string| value)?:\s*\"\[object Promise\]\"")
#: A matcher given no value: the product answered without what the test reads, which is the product's to fix.
_A_MATCHER_MET_NOTHING = re.compile(r"Matcher error:[\s\S]{0,200}?Received(?: has value)?:\s*(?:undefined|null)\b")
#: The product answered something that is not JSON where JSON was read - its error page, a plain-text status. The
#: runner quotes the start of what it was given. Measured on one run: nine tests read an "Internal Server Error" as
#: JSON, and the suite went back to its writers for about 40 minutes instead of the product to its fixers.
_THE_PRODUCT_ANSWERED_NOT_JSON = re.compile(r"Unexpected token [^\n]{0,8}, \"[^\n]{0,40}\"\.{3} is not valid JSON")


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
        # The runner's own words only: the page tree and the service log the harness appends carry the product's
        # errors (`TypeError` on a page, a traceback), which are the product's. And a matcher met a value the product
        # never gave - `expect(received).toMatch(expected)` ... `Received has value: undefined` - is the product's
        # too: measured on one run, a missing `Location` header reopened the suite twice as "the test's own code".
        said = message.split(_PAGE_MARK, 1)[0].split(_SERVICE_ERRORS_MARK, 1)[0]
        if _A_PROMISE_RECEIVED.search(said):
            broken.append(
                f"`{test.name}` cannot pass whatever is built: its matcher received `[object Promise]` - the test "
                "turned a call that returns a promise into text before awaiting it. Await the call and compare its "
                "value. Fix the test so that it can pass once the product works."
            )
            continue
        if _A_MATCHER_MET_NOTHING.search(said) or _THE_PRODUCT_ANSWERED_NOT_JSON.search(said):
            continue
        if any(pattern.search(said) for pattern in patterns):
            first = next((line.strip() for line in said.splitlines() if line.strip()), "")
            broken.append(
                f"`{test.name}` fails because of an error in the test's own code, not because the "
                f"product is unbuilt: {first[:300]}. Fix the test so that it can pass once the "
                "product works."
            )
    return broken


#: A test's own setup calling something with arguments it does not take, in each runtime's words.
_A_CALL_IT_DOES_NOT_TAKE = re.compile(
    r"(?P<callee>[A-Za-z_$][\w$.]*)\(\) (?:got an unexpected keyword argument|takes \d+ positional|"
    r"missing \d+ required positional)|(?P<js>[A-Za-z_$][\w$.]*) is not a (?:function|constructor)")
#: How many tests sharing one setup failure make it the setup's, not one test's.
SHARED_SETUP_FAILURES = 2


def tests_broken_by_their_own_setup(repo_root: str | Path, result: AcceptanceResult | None) -> list[str]:
    """Tests that fail in a setup they share, calling something the product does not define with arguments it rejects.

    Measured on one run: 18 tests failed at setup with `Client.__init__() got an unexpected keyword argument 'app'` -
    a test library's call the installed version no longer takes. No product change could reach them, and six fix
    stages went at the product for about 45 minutes before a dispute sent the suite back. A call to something the
    product defines (its own app factory) is the product's to answer for, and is left alone.
    """
    if result is None or not result.ran:
        return []
    from app.acceptance import start_output

    groups: dict[str, list[str]] = {}
    for test in result.report.tests:
        message = str(test.message or "")
        if test.outcome != "failed" or not start_output._AT_SETUP.search(message):
            continue
        found = _A_CALL_IT_DOES_NOT_TAKE.search(message)
        if found:
            groups.setdefault(found.group(0), []).append(str(test.name))
    if not groups:
        return []
    sources = _the_product_s_own_sources(repo_root)
    problems = []
    for said, names in groups.items():
        if len(names) < SHARED_SETUP_FAILURES:
            continue
        found = _A_CALL_IT_DOES_NOT_TAKE.search(said)
        callee = (found.group("callee") or found.group("js") or "").split(".")
        name = next((part for part in callee if part and part not in ("__init__", "prototype")), "")
        if not name or re.search(rf"(?:\bclass|\bdef|\bfunction|\bconst|\blet|\bvar)\s+{re.escape(name)}\b", sources):
            continue
        problems.append(
            f"{len(names)} tests fail in the setup they share, before any of them reaches the product: `{said}`. "
            f"`{name}` is not part of the product - it is a library the suite calls - so no change to the product "
            f"can make these pass. Fix the shared setup so it calls `{name}` the way the installed version takes: "
            + ", ".join(f"`{n}`" for n in names[:4]) + (" and more" if len(names) > 4 else "") + "."
        )
    return problems[:3]


def _the_product_s_own_sources(repo_root: str | Path) -> str:
    """The text of the product's own source files, the suite and installed packages left out."""
    where = location(repo_root)
    project = Path(repo_root) / where[0] if where else None
    if project is None or not project.is_dir():
        return ""
    suite_dir = directory(repo_root)
    texts = []
    for path in project.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _PAGE_SOURCES:
            continue
        relative = path.relative_to(project)
        if _NOT_THE_PAGE_S & set(relative.parts) or (suite_dir is not None and suite_dir in path.parents):
            continue
        try:
            texts.append(path.read_text(encoding="utf-8", errors="replace")[:200_000])
        except OSError:
            continue
    return "\n".join(texts)


#: A page runner refusing a locator that matched several elements, and the name it was asked for, in its own words.
_MATCHED_SEVERAL = re.compile(
    r"""strict mode violation:.{0,120}?name\s*[=:]\s*['"]([^'"]{1,60})['"].{0,60}?resolved to (\d+) elements""",
    re.I | re.S)


def tests_finding_a_per_record_control_on_the_whole_page(
    repo_root: str | Path, result: AcceptanceResult | None, brief_text: str
) -> list[str]:
    """Failed tests that looked for a control every record has across the whole page, so the runner found several.

    Measured on one run: the brief gave each bookmark a "Delete" control, three tests asked the whole page for it, the
    runner refused with "resolved to 4 elements", and fixers went at a product that drew one per bookmark as it should.
    A control the brief gives the page once is the product's to answer for when it is drawn twice, and is left alone.
    """
    if result is None or not getattr(result, "ran", False):
        return []
    problems = []
    for test in getattr(getattr(result, "report", None), "tests", None) or ():
        if test.outcome != "failed":
            continue
        found = _MATCHED_SEVERAL.search(str(test.message or ""))
        if not found or not found.group(1):
            continue
        name = found.group(1)
        if not re.search(rf"\beach\b[^.\n]*\"{re.escape(name)}\"", brief_text or "", re.I):
            continue
        problems.append(
            f"`{test.name}` looks for \"{name}\" across the whole page, and the brief gives one to each record, so it "
            f"found {found.group(2)} and the runner refused. No product can pass it. Find the record first, then the "
            f"\"{name}\" inside it."
        )
    return problems[:6]


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


def rename_files_the_runner_skips(repo_root: str | Path) -> list[str]:
    """Rename suite files the runner skips only for their name's separator (`delete_spec.js` for `*.spec.js`); what moved.

    Measured on one run: QA wrote five files named `<x>_spec.js` where the runner collects `*.spec.js`. Told each
    time that the name was the reason, it wrote right-named copies of three and left two, and after five rounds the
    run failed with a suite that proved nothing. Only a pattern `*<suffix>` whose suffix starts with a dot, only a
    name that ends in `_` or `-` and the rest of that suffix, and only when the right name is free. Never raises.
    """
    try:
        from fnmatch import fnmatch

        record = contract.read(repo_root) or {}
        pattern = str(record.get("acceptance_pattern") or "")
        if not (pattern.startswith("*.") and "*" not in pattern[1:]):
            return []
        suffix = pattern[1:]
        folder = Path(repo_root) / str(record.get("project") or "") / str(record.get("acceptance_dir") or "")
        if not folder.is_dir():
            return []
        moved: list[str] = []
        for path in sorted(folder.rglob("*")):
            name = path.name
            if not path.is_file() or "node_modules" in path.parts or fnmatch(name, pattern):
                continue
            for separator in ("_", "-"):
                if name.endswith(separator + suffix[1:]) and len(name) > len(suffix):
                    target = path.with_name(name[: -len(suffix)] + suffix)
                    if not target.exists():
                        path.rename(target)
                        root = Path(repo_root)
                        moved.append(f"{path.relative_to(root).as_posix()} -> {target.relative_to(root).as_posix()}")
                    break
        if moved:
            logger.warning("Renamed suite files the runner skipped by their names: %s", "; ".join(moved))
        return moved
    except Exception:  # noqa: BLE001 - the review's own finding stands
        logger.debug("Could not rename the suite files the runner skips", exc_info=True)
        return []


#: A test's fixture argument written as one destructured object: `async ({ request, page }) =>`.
_THE_FIXTURE_ARGUMENT = re.compile(r"async\s*\(\s*\{([^{}()]*)\}\s*\)\s*=>")


def correct_reads_of_the_fixture_s_baseurl(repo_root: str | Path) -> list[str]:
    """Put `baseURL` for `request.baseURL` in each test that reads it, adding `baseURL` to its fixtures; what changed.

    Measured on two runs: told the exact lines to change (`reads_of_what_the_test_does_not_have`), QA left
    `request.baseURL` - `undefined` on every product - through three review rounds and the suite was locked with
    it. The correction is mechanical and the harness makes it, as it renames a file the runner skips. Only in a
    test whose fixtures are one destructured object it can read; any other is left to the review's finding.
    Never raises.
    """
    changed: list[str] = []
    try:
        if contract.the_pack(repo_root) is None:
            return []
        root = Path(repo_root)
        for path in suite_files(repo_root):
            if path.suffix.lower() not in (".js", ".mjs", ".cjs", ".ts", ".mts", ".cts"):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if not _THE_FIXTURE_S_BASEURL.search(text):
                continue
            starts = [m.start() for m in _A_TEST_CALL.finditer(text)] + [len(text)]
            pieces, done, at = [], 0, 0
            for begin, end in zip(starts, starts[1:]):
                block = text[begin:end]
                argument = _THE_FIXTURE_ARGUMENT.search(block)
                if not _THE_FIXTURE_S_BASEURL.search(block) or argument is None:
                    continue
                names = [part.strip() for part in argument.group(1).split(",") if part.strip()]
                head = block[:argument.end()]
                if "baseURL" not in names:
                    inner = argument.group(1)
                    spaced = inner.rstrip() + ", baseURL" + inner[len(inner.rstrip()):]
                    head = block[:argument.start(1)] + spaced + block[argument.end(1):argument.end()]
                pieces += [text[at:begin], head, _THE_FIXTURE_S_BASEURL.sub("baseURL", block[argument.end():])]
                at, done = end, done + 1
            if done:
                path.write_text("".join(pieces) + text[at:], encoding="utf-8")
                changed.append(f"{path.relative_to(root).as_posix()}: `request.baseURL` -> `baseURL` in {done} test(s)")
        if changed:
            logger.warning("Corrected reads of the request fixture's baseURL: %s", "; ".join(changed))
    except Exception:  # noqa: BLE001 - the review's own finding stands
        logger.debug("Could not correct the reads of request.baseURL", exc_info=True)
    return changed


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


#: A request that found nothing listening, or a connection cut: what every test after the service exited sees.
_THE_SERVICE_WAS_GONE = re.compile(r"\b(?:ECONNREFUSED|ECONNRESET|socket hang up|Connection refused|Connection reset|"
                                   r"RemoteDisconnected|connect: connection refused)\b", re.I)
#: The last words of a process that died of an unhandled error, in any of the runtimes the packs start.
_A_PROCESS_DIED = re.compile(r"(?m)^(?:\[WebServer\]\s*)?(?:Node\.js v\d+|Traceback \(most recent call last\)|panic: |"
                             r"thread '[^']*' panicked|Segmentation fault|Aborted \(core dumped\)|Fatal error: )")
#: The start of every "the product crashed while the suite ran" problem.
PRODUCT_CRASHED = "The product crashed while the acceptance suite ran"


def the_product_crashed_mid_suite(report: Any, output: str) -> str:
    """The problem to record when the service died of an error part-way through and later tests found it gone; "".

    Measured on one run: two saves raced on one temp file, the second `rename` failed, the rejection went unhandled
    and Node exited mid-suite; the same product measured 15 of 16 in one round and 3 of 16 in another, every test
    after the crash failed with `ECONNREFUSED`, and each became a criterion defect whose fixer looked at its own
    route. Only when at least one test passed (the product started) and at least one failed on a connection.
    """
    tests = list(getattr(report, "tests", None) or ())
    if not any(t.outcome == "passed" for t in tests):
        return ""
    gone = [t for t in tests if t.outcome == "failed" and _THE_SERVICE_WAS_GONE.search(t.message or "")]
    died = _A_PROCESS_DIED.search(str(output or ""))
    if not gone or not died:
        return ""
    start = str(output).rfind("\n", 0, max(0, died.start() - 1200)) + 1
    trace = str(output)[start:died.end() + 200].strip()
    return (f"{PRODUCT_CRASHED}: the service died of an unhandled error after {sum(t.outcome == 'passed' for t in tests)} "
            f"test(s) had passed, and {len(gone)} later test(s) found nothing listening. Its last output:\n{trace[-1800:]}")


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


#: A runner's own words for what it could not find or load.
_THE_RUNNER_COULD_NOT = re.compile(
    r"^.*(?:not found|no such file|cannot find|could not find|does not exist|\bERROR:|\bError:).*$", re.I | re.M)


def _where_the_runner_looked(repo_root: str | Path, result: AcceptanceResult) -> str:
    """The folder each command runs in, where the suite's files are, and what the runner said it could not find.

    Measured on one run: two commands named `test_api.py` while it sat in the suite's folder, pytest said "file or
    directory not found", and two rounds were told only that zero tests ran.
    """
    where = location(repo_root)
    said = list(dict.fromkeys(
        " ".join(line.split())[:200] for line in _THE_RUNNER_COULD_NOT.findall(_AN_ANSI_COLOUR.sub("", result.output or ""))
    ))[:3]
    text = ""
    if where:
        text += (f" Each command runs in `{where[0]}/`, so every path in it is relative to that folder; the suite's "
                 f"files are in `{where[0]}/{where[1]}/`, which a command names as `{where[1]}/<file>`.")
    if said:
        text += " The runner said: " + " | ".join(f"`{line}`" for line in said)
    return text


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
            + _where_the_runner_looked(repo_root, result)
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


def _page_checks(repo_root: str | Path) -> Any:
    """The pack whose page checks apply: this run's, or for a run with none a browser pack when its suite is one.

    Only a JavaScript browser suite takes a pack's patterns: they are written in that runner's calls.
    """
    found = contract.the_pack(repo_root)
    # A pack with its own page patterns decides; one without any - a setup derived from a proven replay, or a pack
    # for a stack with no page - borrows the browser pack's when the suite drives a browser. Measured on one run: a
    # replayed setup's derived pack kept every page check silent, and a hidden test by label timed out.
    if found is not None and (found[0].finds_by_name or found[0].locators_nobody_sees):
        return found[0]
    for path in suite_files(repo_root):
        try:
            if "@playwright/test" in path.read_text(encoding="utf-8", errors="replace"):
                from app.stacks import pack_named

                return pack_named("browser-javascript")
        except OSError:
            continue
    return None


#: A label lookup a failure names as matching several controls.
_NOT_EXACT_LABEL = re.compile(r"""getByLabel\(['"`]([^'"`]+)['"`]\) resolved to \d+ elements""")


#: How a brief says a record is shown, the role that means, and how a test finds it so.
_KINDS_OF_RECORD = (
    (re.compile(r"\b(?:items? of a list|list items?)\b", re.I), "an item of a list", "listitem",
     re.compile(r"""\b(?:getByRole|get_by_role)\s*\(\s*['"`]listitem['"`]|\blocator\s*\(\s*['"`][^'"`]*\bli\b""")),
    (re.compile(r"\b(?:rows? of a table|table rows?)\b", re.I), "a row of a table", "row",
     re.compile(r"""\b(?:getByRole|get_by_role)\s*\(\s*['"`]row['"`]|\blocator\s*\(\s*['"`][^'"`]*\btr\b""")),
)


def records_never_found_as_the_brief_shows_them(repo_root: str | Path, brief_text: str) -> list[str]:
    """Each kind of thing the brief shows records as - an item of a list, a row of a table - that no page test asks for.

    Measured on one run: the brief said each record is an item of a list, the product drew plain containers, and the
    suite, finding them by a class, passed while 5 of 8 hidden tests failed. Only a suite that drives a browser.
    """
    texts = []
    for path in suite_files(repo_root):
        try:
            texts.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    suite_text = "\n".join(texts)
    if "playwright" not in suite_text.lower():
        return []
    return [
        f"The brief shows records as {kind} and no test finds them so. A test that finds them another way, such as by a class, passes whatever the "
        f"product draws. Find each record by its role, `{role}`, in a test that reads it."
        for said, kind, role, asked in _KINDS_OF_RECORD
        if said.search(brief_text or "") and not asked.search(suite_text)
    ]


#: What makes each kind of record in a page's sources, in markup, a script or a template: `<li>`, `createElement('li')`,
#: `role="listitem"`; `<tr>`, `insertRow(`, `role="row"`.
_MADE_BY = {
    "listitem": re.compile(r"""<li\b|['"`]li['"`]|role\s*=\s*['"]listitem['"]""", re.I),
    "row": re.compile(r"""<tr\b|['"`]tr['"`]|\binsertRow\s*\(|role\s*=\s*['"]row['"]""", re.I),
}
#: Sources a page is made from.
_PAGE_SOURCES = frozenset({".html", ".htm", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".py",
                           ".jinja", ".j2", ".erb", ".ejs", ".hbs", ".php", ".rb", ".go", ".cs", ".java"})
#: Folders whose files are no part of the page.
_NOT_THE_PAGE_S = frozenset({"node_modules", ".venv", "venv", ".git", "__pycache__", "site-packages", "test-results",
                             "dist", "build", "coverage", ".harness", "playwright-report"})


def records_the_page_never_makes(repo_root: str | Path, brief_text: str) -> list[str]:
    """Each kind of record the brief shows - an item of a list, a row of a table - that nothing in the page's sources makes.

    Measured on one run: the brief said each record is an item of a list, the page drew plain containers, the suite
    found them by a class, and the finding that said so was still open when the suite was locked at its round cap. The
    suite passed 25 of 25 and 5 of 8 hidden tests failed. This reads the product, not the tests, so a lenient suite
    cannot hide it. Only for a product with a page.
    """
    kinds = [(kind, role) for said, kind, role, _ in _KINDS_OF_RECORD if said.search(brief_text or "")]
    where = location(repo_root)
    project = Path(repo_root) / where[0] if where else None
    if not kinds or project is None or not project.is_dir():
        return []
    suite_dir = directory(repo_root)
    texts: list[str] = []
    has_a_page = False
    for path in project.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _PAGE_SOURCES:
            continue
        relative = path.relative_to(project)
        if _NOT_THE_PAGE_S & set(relative.parts) or (suite_dir is not None and suite_dir in path.parents):
            continue
        if any(part in {"tests", "test", "e2e", "e2e-tests", "__tests__", "spec"} for part in relative.parts[:-1]):
            continue
        if re.match(r"(?:test_|.*[._-](?:test|spec)\.)", path.name, re.I):
            continue
        has_a_page = has_a_page or path.suffix.lower() in {".html", ".htm", ".vue", ".svelte", ".jsx", ".tsx"}
        try:
            texts.append(path.read_text(encoding="utf-8", errors="replace")[:400_000])
        except OSError:
            continue
    if not has_a_page:
        return []
    sources = "\n".join(texts)
    return [
        f"The brief shows each record as {kind}, and nothing in the page's sources makes one: no element, script or "
        f"template creates the `{role}` the brief describes. Draw each record as {kind}, so a person, a screen reader "
        "and a test find it by its role."
        for kind, role in kinds
        if not _MADE_BY[role].search(sources)
    ]


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
    pack = _page_checks(repo_root)
    if pack is None or not pack.locators_nobody_sees:
        return []
    patterns = [re.compile(pattern) for pattern in pack.locators_nobody_sees]
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


def page_assertions_without_await(repo_root: str | Path) -> list[str]:
    """Each suite file with Playwright page assertions written without `await`, as one problem per file.

    A page assertion waits and returns a promise. Measured on one run: dozens unawaited in one suite - each passes a
    product that fails it, or fails detached at a line the test never reached - and two fixers chased that failure.
    """
    from app.stacks.packs import _javascript

    root = Path(repo_root)
    problems = []
    for path in suite_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = _javascript.unawaited_page_assertions(text)
        if lines:
            problems.append(
                f"`{path.relative_to(root).as_posix()}` line(s) {', '.join(map(str, lines[:200]))} assert on the page "
                "without `await`. A page assertion waits for the page and returns a promise: unawaited, the test does "
                "not wait for it, so it passes a product that fails it or fails at a line it never reached. Put "
                "`await` before each `expect(...)` of the page."
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


#: A sentence of the brief about narrowing what a view shows.
_A_FILTERING_SENTENCE = re.compile(r"[^.\n]*\bfilter[^.\n]*", re.I)
#: A state-changing step on the page: ticking, unticking, typing and confirming, or a further press.
_A_CHANGING_STEP = re.compile(r"\.(?:check|uncheck|setChecked|press|click|fill|dblclick)\s*\(")
_AN_ASSERTION = re.compile(r"\bexpect(?:\.soft)?\s*\(")


def views_never_acted_within(repo_root: str | Path, brief_text: str) -> list[str]:
    """The narrowing views the brief names that no browser test acts within, as one problem.

    Measured on two runs: the brief named filters "All", "Active" and "Completed"; the suite tested each filter and the
    action that changes an item's state, but never the action while a narrowing filter was on. The product left a
    completed item in the Active view and a hidden test of exactly that failed both times. A prompt rule asking for the
    test was on and did not make the writers write it, so the locked suite is checked. Choosing another filter is not
    an action within the view.
    """
    quoted: list[str] = []
    for sentence in _A_FILTERING_SENTENCE.findall(brief_text or ""):
        quoted += re.findall(r'"([^"\n]{1,40})"', sentence)
    every = list(dict.fromkeys(quoted))
    narrowing = [n for n in every if n.strip().lower() not in ("all", "show all")]
    if not narrowing:
        return []
    texts = []
    for path in suite_files(repo_root):
        try:
            texts.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    suite_text = "\n".join(texts)
    if "playwright" not in suite_text.lower():
        return []

    def a_filter(names: list[str]) -> str:
        alternatives = "|".join(re.escape(n) for n in names)
        return (r"""(?:getByRole\s*\(\s*['"]button['"]\s*,\s*\{\s*name\s*:\s*(?:['"`]|/\^?)(?:""" + alternatives
                + r""")|getByText\s*\(\s*['"`](?:""" + alternatives + r""")['"`])""")

    any_filter, a_narrowing_one = re.compile(a_filter(every)), re.compile(a_filter(narrowing))
    starts = [m.start() for m in _A_TEST_DECLARED.finditer(suite_text)]
    for begin, end in zip(starts, starts[1:] + [len(suite_text)]):
        body = suite_text[begin:end]
        # A filter's locator kept in a name and clicked later is clicked all the same.
        held = {m.group(1): bool(a_narrowing_one.match(body, m.end()))
                for m in re.finditer(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:await\s+)?page\.", body)
                if any_filter.match(body, m.end())}
        filter_clicks: list[tuple[int, int, bool]] = []
        for m in re.finditer(r"\.click\s*\(", body):
            before = body[max(0, m.start() - 160):m.start()]
            direct = list(any_filter.finditer(before))
            name = re.search(r"([A-Za-z_$][\w$]*)\s*$", before)
            # `getByRole('button', { name: 'Active' }).click()`: the locator and its click in one statement.
            if direct and ";" not in before[direct[-1].end():] and before.rstrip().endswith(")"):
                filter_clicks.append((m.start(), m.end(), bool(a_narrowing_one.match(before, direct[-1].start()))))
                continue
            if name and name.group(1) in held:
                filter_clicks.append((m.start(), m.end(), held[name.group(1)]))
        # A view narrowed by typing into a field the brief names: `getByLabel('Filter by tag').fill('work')`. Measured on
        # one run: the check knew only views chosen by pressing a control and called a right suite incomplete.
        for m in re.finditer(r"\.fill\s*\(\s*([^)]*)\)", body):
            before = body[max(0, m.start() - 200):m.start()]
            statement = before[before.rfind(";") + 1:]
            named = [n for n in every if re.search(r"""['"`]""" + re.escape(n) + r"""['"`]""", statement)]
            if named:
                cleared = bool(re.fullmatch(r"""\s*(?:''|""|``)\s*""", m.group(1)))
                filter_clicks.append((m.start(), m.end(), not cleared and any(n in narrowing for n in named)))
        filter_clicks.sort()
        is_a_filter_click = {start for start, _, _ in filter_clicks}
        for start, stop, narrows in filter_clicks:
            if not narrows:
                continue
            for step in _A_CHANGING_STEP.finditer(body, stop):
                if step.start() in is_a_filter_click:
                    break  # another view was chosen first
                if _AN_ASSERTION.search(body, step.end()):
                    return []
                break
    shown = ", ".join(f'"{n}"' for n in narrowing[:4])
    return [
        f"The brief narrows what the page shows ({shown}), and no test takes an action while such a view is on. A "
        "test of each view and a test of the action apart pass a product that leaves the wrong thing showing when the "
        "two meet. Add a test that chooses a narrowing view, changes an item in it, and checks what that view shows "
        "afterward."
    ]


def controls_never_found_by_name(repo_root: str | Path, brief_text: str) -> list[str]:
    """Each control the brief names that no test finds by that name, as one problem.

    Measured on one run: the brief gave every item a box labelled "Done", the
    product gave it no label, and the locked suite - which found the box by a
    class - passed; the benchmark's hidden tests, which find it by "Done",
    failed twice. A suite that never asks for a name cannot tell a product that
    gave it from one that did not.
    """
    from app.analysis.interface_checks import controls_the_brief_names

    pack = _page_checks(repo_root)
    if pack is None or not pack.finds_by_name:
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
            for template in pack.finds_by_name
        )
    ]
    loose = [
        name for name in names
        if name not in missing and _longer_names(name, names)
        and re.search(r"""\bgetByLabel\s*\(\s*['"`]""" + re.escape(name) + r"""['"`]\s*\)""", suite_text)
    ]
    problems = [
        f'A test asks for the label "{name}" without `exact: true`, which also matches '
        + ", ".join(f'"{other}"' for other in _longer_names(name, names))
        + ", so no product the brief describes can pass it. Find it with `{ exact: true }`."
        for name in loose
    ]
    # A role lookup by a name the brief gives, without `exact: true`, matches any control whose name contains it.
    # Measured on one run: `getByRole('button', { name: 'Delete' })` passed a product naming each "Delete <title>",
    # and the hidden test finding exactly "Delete" timed out - a false acceptance.
    by_part = [
        name for name in names
        if name not in missing and re.search(
            r"""\bgetByRole\s*\(\s*['"`]\w+['"`]\s*,\s*\{(?![^{}]*\bexact\s*:\s*true)[^{}]*\bname\s*:\s*['"`]"""
            + re.escape(name) + r"""['"`][^{}]*\}""", suite_text)
    ]
    problems += [
        f'A test finds "{name}" by its role and that name without `exact: true`, which matches any control whose name '
        f'only contains "{name}" - one named "{name} and more" passes it, so a product that names it otherwise does '
        f'too. Find it with `{{ name: \'{name}\', exact: true }}`.'
        for name in by_part
    ]
    if not missing:
        return problems
    return [
        *problems,
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


#: A sentence of a criterion that gives each record a named control: `Each has a button named "Delete"`.
_EACH_HAS = re.compile(r"\beach\b[^.\n]*", re.I)


def whole_page_lookups_of_a_per_record_control(repo_root: str | Path) -> list[str]:
    """Tests asking the whole page for a control every record has. See the pack's `whole_page_lookups`."""
    found = contract.the_pack(repo_root)
    if found is None or found[0].whole_page_lookups is None:
        return []
    per_record = sorted({name for c in criteria(repo_root) for sentence in _EACH_HAS.findall(str(c.text))
                         for name in re.findall(r'"([^"]+)"', sentence)})
    if not per_record:
        return []
    root = Path(repo_root)
    problems = []
    for path in suite_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hits = list(found[0].whole_page_lookups(text, per_record))
        if not hits:
            continue
        lines = text.splitlines()
        named = next((n for n in per_record if n in lines[hits[0] - 1]), per_record[0]) if 0 < hits[0] <= len(lines) else per_record[0]
        where = ", ".join(str(line) for line in hits[:8]) + (" ..." if len(hits) > 8 else "")
        problems.append(
            f"`{path.relative_to(root).as_posix()}` line(s) {where} ask the whole page for \"{named}\", and the brief gives "
            "one to each record: once the page holds more than one, the lookup matches several and the runner refuses "
            f"it. Find the record first, then the \"{named}\" inside it."
        )
    return problems[:6]


def locators_matching_a_pattern_as_text(repo_root: str | Path) -> list[str]:
    """Where the suite gives a locator a pattern as plain text. See the pack's `locators_matching_a_pattern_as_text`."""
    found = contract.the_pack(repo_root)
    if found is None or found[0].locators_matching_a_pattern_as_text is None:
        return []
    root = Path(repo_root)
    problems = []
    for path in suite_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hits = list(found[0].locators_matching_a_pattern_as_text(text))
        if not hits:
            continue
        lines = text.splitlines()
        snippet = lines[hits[0] - 1].strip()[:160] if 0 < hits[0] <= len(lines) else ""
        where = ", ".join(str(line) for line in hits[:8]) + (" ..." if len(hits) > 8 else "")
        problems.append(
            f"`{path.relative_to(root).as_posix()}` line(s) {where} (`{snippet}`) give a locator `^` or `$` inside a "
            "string. A string is matched as text, so it looks for those characters and finds nothing: a test acting "
            "on it can never pass, and one expecting it hidden passes whatever the page shows. Write the pattern as "
            "a regular expression (`/^B$/`), or give the plain text."
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
#: The text just before an options object handed to a helper that is given the fixture: `fetchJSON(request, '/x', `.
_OPTIONS_OF_A_CALL_GIVEN_THE_FIXTURE = re.compile(
    r"\b[A-Za-z_$][\w$]*\s*\(\s*request\s*,(?:[^;{}]|\$\{[^}]*\})*,\s*$"
)
_USES_THE_REQUEST_FIXTURE = re.compile(r"\brequest\s*\.\s*(?:post|put|patch|delete|fetch|get|head)\s*\(")


def _the_start_of_the_object_around(text: str, at: int) -> int:
    """Where the object literal that holds position `at` opens, or -1."""
    depth = 0
    for i in range(at, -1, -1):
        ch = text[i]
        if ch == "}":
            depth += 1
        elif ch == "{":
            if depth == 0:
                return i
            depth -= 1
    return -1


def _the_object_around(text: str, at: int) -> str:
    """The object literal `{ ... }` that holds position `at`, or ""."""
    start = _the_start_of_the_object_around(text, at)
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


#: An assignment of a response: from the `request` fixture (group 2 "request") or a plain `fetch(` (group 2 "fetch").
_A_RESPONSE_ASSIGNED = re.compile(
    r"\b(?:const|let|var)?\s*(\w+)\s*=\s*await\s+(?:(request)\s*\.\s*(?:post|put|patch|delete|fetch|get|head)\s*\(|(?<![.\w])(fetch)\s*\()"
)


def _the_kind_assigned(text: str, name: str, at: int) -> str:
    """"request" or "fetch": what the last assignment of `name` before position `at` called; "" when none.

    Measured on one run: one spec named a fixture response `getResp` in one test and a `fetch` response `getResp`
    in another, and a file-wide reading of the name sent QA to repair the right one. The last assignment of any kind
    counts: measured on one run, a test's `const res = await createNote(...)` kept the kind of the `res` inside that
    helper, and its right `res.body.title` was called a fixture response.
    """
    last = None
    for last in re.finditer(rf"(?<![.\w$]){re.escape(name)}\s*=(?![=>])", text[:at]):
        pass
    response = _A_RESPONSE_ASSIGNED.match(text, last.start()) if last else None
    return (response.group(2) or response.group(3) or "") if response else ""


#: Corrected lines quoted with a finding, at most.
MOST_CORRECTED_LINES = 4


def _the_lines_corrected(text: str, lines: list[int], correct: Any) -> str:
    """` Each line as it should read: ...` for the lines a check names, or "" (deep review B8).

    Measured on one run: told what was wrong with two tests, QA's repair fixed one reading and kept the other, and the
    suite's repairs were spent. A check that knows the exact correction hands it over.
    """
    source = text.splitlines()
    pairs = []
    for number in lines[:MOST_CORRECTED_LINES]:
        if 0 < number <= len(source):
            before = source[number - 1].strip()
            after = correct(before)
            if after and after != before:
                pairs.append(f"line {number}: `{before[:160]}` -> `{after[:160]}`")
    return (" Each line as it should read - " + "; ".join(pairs) + ".") if pairs else ""


def _within_a_comment(text: str, at: int) -> bool:
    """Whether position `at` of JavaScript source is inside a `//` or `/* */` comment (strings are not told apart)."""
    line_start = text.rfind("\n", 0, at) + 1
    if "//" in text[line_start:at] and not re.search(r"https?:$", text[line_start:at].split("//")[0]):
        return True
    return text.rfind("/*", 0, at) > text.rfind("*/", 0, at)


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
            if _within_a_comment(text, match.start()):
                # Measured on one run: "Playwright's request fixture does not read a `body:` option, so we reach the
                # service directly" above a correct `fetch(...)` call was read as the misuse, and the locked suite
                # was reopened for a test that passed.
                continue
            literal = _the_object_around(text, match.start())
            opening = _the_start_of_the_object_around(text, match.start())
            # Not a plain `fetch(` call's options: `body:` is how `fetch` is given one.
            if opening >= 0 and _OPTIONS_OF_A_FETCH_CALL.search(text[max(0, opening - 300):opening]):
                continue
            # Only the options handed straight to the fixture: a table's row `{ method, path, body }`, sent later as
            # `data: row.body`, is how a right table-driven suite reads (deep review, acceptance A5).
            before = text[max(0, opening - 300):opening] if opening >= 0 else ""
            if not (_OPTIONS_OF_A_FIXTURE_CALL.search(before) or _OPTIONS_OF_A_CALL_GIVEN_THE_FIXTURE.search(before)):
                continue
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
        lines = sorted({
            text.count("\n", 0, match.start()) + 1 for match in uncalled.finditer(text)
            if _the_kind_assigned(text, match.group(0).split(".")[0].strip(), match.start()) == "request"
        })
        # `.body` read as the parsed answer: measured on one run, `created.body.id` was `undefined`, the next request
        # went to `/notes/undefined` and answered 400, and two attempts of fixes went on a test no product passes.
        as_the_body = re.compile(rf"\b({'|'.join(map(re.escape, names))})\s*\.\s*body\b(?=\s*[.\[])")
        body_lines = sorted({
            text.count("\n", 0, match.start()) + 1 for match in as_the_body.finditer(text)
            if _the_kind_assigned(text, match.group(1), match.start()) == "request"
        })
        if body_lines:
            problems.append(
                f"`{path.relative_to(root).as_posix()}` line(s) {', '.join(map(str, body_lines[:8]))}: a response "
                "from the `request` fixture is read as `.body.<field>`. On Playwright's response `body()` is a method "
                "that gives the raw bytes, so `.body.id` is `undefined` on every product and every request built "
                "from it fails. Read the parsed answer: `(await res.json()).id`, or `const data = await res.json()`."
                + _the_lines_corrected(text, body_lines, lambda line: as_the_body.sub(lambda m: f"(await {m.group(1)}.json())", line))
            )
        if not lines:
            continue
        where = ", ".join(str(n) for n in lines[:8]) + (" ..." if len(lines) > 8 else "")
        problems.append(
            f"`{path.relative_to(root).as_posix()}` line(s) {where}: a response from the `request` fixture is read as "
            "`.status`, `.ok`, `.statusText` or `.headers` without calling it. On Playwright's response these are "
            "methods, so the assertion compares a function and fails on every product. Call it: `res.status()`."
            + _the_lines_corrected(text, lines, lambda line: uncalled.sub(lambda m: m.group(0) + "()", line))
        )
    return problems[:6]


#: `request.newContext(` or `test.request.newContext(`: a context made from the name `request`.
_A_NEW_CONTEXT = re.compile(r"\b((?:test\s*\.\s*)?request)\s*\.\s*newContext\s*\(")
#: `request` imported from Playwright as the module's API (`import { request } ...`), not taken as the fixture.
_REQUEST_IMPORTED = re.compile(
    r"""(?:import\s*\{[^}]*\brequest\b(?!\s+as\b)[^}]*\}\s*from|\{[^}]*\brequest\b(?!\s*:)[^}]*\}\s*=\s*require\s*\()\s*['"]@playwright/test['"]"""
)
#: A test body that takes the `request` fixture: `async ({ request }) =>` or `async ({ page, request }) =>`.
_TAKES_THE_FIXTURE = re.compile(r"async\s*\(\s*\{[^}]*\brequest\b[^}]*\}")


def contexts_made_from_the_fixture(repo_root: str | Path) -> list[str]:
    """Tests that call `newContext` on the `request` fixture, which has no such method.

    Measured on five runs: every one in a restart test, reaching the second service through
    `request.newContext({ baseURL: second.baseURL })` (once `test.request.newContext`). `newContext` belongs to the
    `request` the module exports, not to the fixture a test is given, so the call throws "is not a function" on every
    product. It throws only once the first service has run, after the review that locks the suite, so the suite was
    reopened after the first draft. Found by its shape: the call inside a test that takes the fixture, or in a file
    that never imports `request` from Playwright.
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
        imported = bool(_REQUEST_IMPORTED.search(text))
        lines = []
        for match in _A_NEW_CONTEXT.finditer(text):
            opened = [m for m in re.finditer(r"\btest(?:\.\w+)?\s*\(", text[: match.start()])]
            body_start = opened[-1].start() if opened else 0
            takes_it = bool(_TAKES_THE_FIXTURE.search(text, body_start, match.start()))
            if "." in match.group(1) or takes_it or not imported:
                lines.append(text.count("\n", 0, match.start()) + 1)
        if not lines:
            continue
        lines = sorted(set(lines))
        problems.append(
            f"`{path.relative_to(root).as_posix()}` line(s) {', '.join(map(str, lines[:8]))}: `newContext` is called "
            "on the `request` fixture, which has no such method, so the test throws \"is not a function\" on every "
            "product. The fixture already reaches any address: send each request to the full URL, "
            "`await request.get(second.baseURL + '/items')`, and drop the new context."
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
            lines = sorted({
                text.count("\n", 0, m.start()) + 1 for m in called.finditer(text)
                if _the_kind_assigned(text, m.group(0).split(".")[0].strip(), m.start()) == "fetch"
            })
            if lines:
                problems.append(
                    f"`{shown}` line(s) {', '.join(map(str, lines[:8]))}: a `fetch` response's `status`, `ok` or "
                    "`statusText` is called like a method. On a `fetch` response these are values, so the call throws "
                    "on every product. Read it without the call: `res.status`."
                    + _the_lines_corrected(text, lines, lambda line: re.sub(called.pattern + r"\s*\)", lambda m: m.group(0)[:m.group(0).rindex("(")].rstrip(), line))
                )
    return problems[:6]


#: `request.baseURL`: Playwright's request fixture has no such property.
_THE_FIXTURE_S_BASEURL = re.compile(r"\brequest\s*\.\s*baseURL\b")
#: The server's `PORT` read in the test process, which the suite never gives it.
_THE_SERVER_S_PORT = re.compile(r"\bprocess\s*\.\s*env\s*\.\s*PORT\b|\bprocess\s*\.\s*env\s*\[\s*['\"]PORT['\"]\s*\]")


def reads_of_what_the_test_does_not_have(repo_root: str | Path) -> list[str]:
    """Tests that read `request.baseURL`, or the server's `PORT` in the test process: each is never what it means.

    Measured on one run: both AC-15 tests read `request.baseURL` - `undefined`, the fixture has no such property - and
    one compared it with `process.env.PORT ?? '3000'`; the suite gives `PORT` only to the server it starts. Both failed
    on every product and went to the product's fixers. Only in a suite run by a pack's runner configuration, which
    starts the server with `PORT` and hands the tests `baseURL`.
    """
    if contract.the_pack(repo_root) is None:
        return []
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
        for pattern, why in (
            (_THE_FIXTURE_S_BASEURL,
             "reads `request.baseURL`, which Playwright's `request` fixture does not have - it is `undefined` on every "
             "product. The address the suite reaches is the test's `baseURL` argument: `async ({ request, baseURL }) "
             "=>`."),
            (_THE_SERVER_S_PORT,
             "reads `process.env.PORT` in the test. The suite gives `PORT` only to the server it starts, so the test "
             "never has it and compares with its own fallback. The address, port included, is the test's `baseURL` "
             "argument."),
        ):
            lines = sorted({text.count("\n", 0, m.start()) + 1 for m in pattern.finditer(text)
                            if not _within_a_comment(text, m.start())})
            if lines:
                corrected = (_the_lines_corrected(text, lines, lambda line: _THE_FIXTURE_S_BASEURL.sub("baseURL", line))
                             if pattern is _THE_FIXTURE_S_BASEURL else "")
                problems.append(f"`{shown}` line(s) {', '.join(map(str, lines[:8]))}: the test {why}{corrected}")
        # The server's data directory, read in the test: measured on one run, a restart test started a service on
        # `process.env.DATA_DIR` to read what it wrote through `request`; the suite gives that variable only to the
        # server, so the service started on a fresh folder and read nothing on every product.
        variable = str(getattr((contract.the_pack(repo_root) or (None,))[0], "data_dir_env", "") or "")
        if variable:
            reads = re.compile(rf"\bprocess\s*\.\s*env\s*(?:\.\s*{re.escape(variable)}\b|\[\s*['\"]{re.escape(variable)}['\"]\s*\])")
            lines = sorted({text.count("\n", 0, m.start()) + 1 for m in reads.finditer(text)
                            if not _within_a_comment(text, m.start())})
            if lines:
                problems.append(
                    f"`{shown}` line(s) {', '.join(map(str, lines[:8]))}: the test reads `process.env.{variable}`. The "
                    f"suite gives `{variable}` only to the server it starts, so the test never has it and a service "
                    "started on it begins on a fresh folder. A restart test writes through the service it started "
                    "itself and restarts on that service's `dataDir`: `const first = await startService(); ... "
                    "await startService({ dataDir: first.dataDir })`."
                )
    return problems[:6]


#: An assertion that a response's content type is JSON.
_ASSERTS_JSON_CONTENT = re.compile(r"content-type['\"`]?\s*\]?[\s\S]{0,160}?(?:application/)?json", re.I)
#: A DELETE request: the fixture's call, or a table entry a loop sends.
_A_DELETE_CALL = re.compile(r"\.delete\s*\(")
_A_DELETE_ENTRY = re.compile(r"method\s*:\s*['\"`]delete['\"`]", re.I)
#: The answer whose headers a test reads, and a name given a DELETE's answer.
_HEADERS_READ_OF = re.compile(r"\b([A-Za-z_$][\w$]*)\s*\.\s*headers\s*\(")
_A_DELETE_S_ANSWER = re.compile(r"\b([A-Za-z_$][\w$]*)\s*=\s*await\s+[\w$.]+\.delete\s*\(")
#: Where a test is declared.
_A_TEST_CALL = re.compile(r"\btest\s*\(")


def _inside_a_loop_over_a_delete(text: str, start: int) -> bool:
    """Whether the test declared at `start` sits inside a `for` loop whose entries, declared before it, include a DELETE.

    The loop must enclose the test - its brace still open where the test starts: measured in the deep review
    (acceptance A6), a `for (` inside the previous test's body counted, and a right JSON check was flagged.
    """
    header = text.rfind("for (", max(0, start - 300), start)
    if header < 0:
        return False
    between = text[header:start]
    return between.count("{") > between.count("}") and bool(_A_DELETE_ENTRY.search(text[:header]))


def _asserted_to_answer_with_an_error(block: str, name: str) -> bool:
    """Whether the test asserts the answer `name` has a 4xx or 5xx status, and no success one."""
    codes = [int(code) for code in re.findall(
        rf"\b{re.escape(name)}\s*\.\s*status\s*\(\s*\)\s*\)\s*\.\s*(?:toBe|toEqual)\s*\(\s*(\d{{3}})\s*\)", block)]
    return bool(codes) and all(code >= 400 for code in codes)


def tests_that_want_json_from_a_204(repo_root: str | Path, contract_lines: Sequence[str] = ()) -> list[str]:
    """Tests asserting a JSON content type on a DELETE the interface contract answers with 204 only (no body).

    Measured on one run (hidden 5/9): a test looped over every endpoint, the DELETE included, asserting `content-type`
    contains `application/json`; the contract said `DELETE /notes/{id} -> 204 or 404`, and every fix that made delete
    right broke the test and was reverted, eight times. `contract_lines`: the specification's, before the suite is
    locked; the locked contract after.
    """
    from app.acceptance import interface_contract

    checks = interface_contract.parse(list(contract_lines))[0] if contract_lines else interface_contract.the_locked_contract(repo_root)
    empty = [c for c in checks if c.kind == "http" and c.method == "DELETE"
             and 204 in (c.statuses or (c.status,)) and not any(200 <= x < 300 and x != 204 for x in (c.statuses or (c.status,)))]
    if not empty:
        return []
    root = Path(repo_root)
    problems: list[str] = []
    for path in suite_files(repo_root):
        if path.suffix.lower() not in (".js", ".mjs", ".cjs", ".ts", ".mts", ".cts"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        starts = [m.start() for m in _A_TEST_CALL.finditer(text)]
        lines: list[int] = []
        for at, start in enumerate(starts):
            block = text[start:starts[at + 1] if at + 1 < len(starts) else len(text)]
            if not _ASSERTS_JSON_CONTENT.search(block):
                continue
            looped = _inside_a_loop_over_a_delete(text, start)
            if looped or _A_DELETE_ENTRY.search(block):
                lines.append(text.count("\n", 0, start) + 1)
            elif _A_DELETE_CALL.search(block):
                # Measured on one run: a lifecycle test read the list's content type and later sent a DELETE. When
                # the test names the answers it reads, only a DELETE's own answer counts.
                read = set(_HEADERS_READ_OF.findall(block))
                # And a delete asserted to answer with an error is not the 204: measured on one run, a delete of a
                # missing note answering 404 as JSON was called a JSON check on a 204.
                the_204 = {name for name in read & set(_A_DELETE_S_ANSWER.findall(block))
                           if not _asserted_to_answer_with_an_error(block, name)}
                if not read or the_204:
                    lines.append(text.count("\n", 0, start) + 1)
        if lines:
            problems.append(
                f"`{path.relative_to(root).as_posix()}` line(s) {', '.join(map(str, lines[:8]))}: a test asserts a JSON "
                f"content type on a DELETE the interface contract answers with 204 (`{empty[0].line}`). A 204 has no "
                "body and so no content type: the test fails on every product that keeps the contract. Leave the "
                "DELETE out of the content-type check, or check it only on the 404 answer."
            )
    return problems[:6]


#: `const res = await request.post('/notes'`: the name, the verb and the literal path (to its first `?`, quote or `${`).
_A_NAMED_CALL = re.compile(
    r"""\b(?:const|let|var)?\s*([A-Za-z_$][\w$]*)\s*=\s*await\s+request\s*\.\s*(get|post|put|patch|delete)\s*\(\s*['"`]([^'"`?]*)"""
)
#: `expect(res.status()).toBe(200)` or `.toEqual(200)`: the name and the status.
_A_STATUS_ASSERTED = re.compile(r"expect\s*\(\s*([A-Za-z_$][\w$]*)\s*\.\s*status\s*\(\s*\)\s*\)\s*\.\s*(?:toBe|toEqual)\s*\(\s*(\d{3})\s*\)")
#: A loop entry naming a call: `{ method: 'post', path: '/notes' ... }` (`url:` too), either key first.
_AN_ENTRY = re.compile(
    r"""\{(?:[^{}]|\{[^{}]*\})*?\bmethod\s*:\s*['"`](get|post|put|patch|delete)['"`](?:[^{}]|\{[^{}]*\})*?"""
    r"""\b(?:path|url)\s*:\s*['"`]([^'"`?]*)(?:[^{}]|\{[^{}]*\})*\}"""
    r"""|\{(?:[^{}]|\{[^{}]*\})*?\b(?:path|url)\s*:\s*['"`]([^'"`?]*)['"`](?:[^{}]|\{[^{}]*\})*?"""
    r"""\bmethod\s*:\s*['"`](get|post|put|patch|delete)(?:[^{}]|\{[^{}]*\})*\}""",
    re.I,
)
#: An entry that says its own status (`status: 201`), which a loop then asserts instead of one number for all.
_AN_ENTRY_S_OWN_STATUS = re.compile(r"\b(?:status|expected\w*)\s*:\s*\d{3}")


def _the_successes_by_route(checks: Sequence[Any]) -> list[tuple[str, re.Pattern[str], set[int], str]]:
    """Each route of the contract: its method, its path as a pattern, the 2xx statuses it may answer, and a line."""
    routes: dict[tuple[str, str], list[Any]] = {}
    for check in checks:
        if getattr(check, "kind", "") == "http" and check.method and check.path:
            routes.setdefault((check.method.upper(), check.path.rstrip("/") or "/"), []).append(check)
    found = []
    for (method, path), lines in routes.items():
        ok = {x for c in lines for x in (c.statuses or (c.status,)) if 200 <= x < 300}
        if not ok:
            continue
        pattern = re.compile(
            "^" + re.sub(r"\\\{[^}]*\\\}|/:[A-Za-z_]\w*", lambda m: "/[^/]+" if m.group(0).startswith("/") else "[^/]+",
                         re.escape(path)) + "/?$"
        )
        found.append((method, pattern, ok, next(c.line for c in lines if set(c.statuses or (c.status,)) & ok)))
    return found


def _the_route(routes: list[tuple[str, re.Pattern[str], set[int], str]], method: str, path: str):
    path = re.sub(r"\$\{[^}]*\}", "x", path).rstrip("/") or "/"
    return next(((ok, line) for m, pattern, ok, line in routes if m == method.upper() and pattern.match(path)), None)


def tests_whose_success_status_the_contract_does_not_give(
    repo_root: str | Path, contract_lines: Sequence[str] = ()
) -> list[str]:
    """Tests asserting a success status the interface contract never gives for that call.

    Measured on one run: a test looped over `GET /health` and `POST /notes` asserting `status()` is 200 for both; the
    contract says `POST /notes -> 201`, so the test fails on every product that keeps it. It named no criterion, so the
    rounds counted every criterion green beside a red suite. Only a 2xx asserted where the contract gives another 2xx
    for the same method and path is named: a refusal a test sends on purpose (a 400 for a missing field) may be on a
    line of its own or none. `contract_lines`: the specification's, before the suite is locked; the locked contract
    after.
    """
    from app.acceptance import interface_contract

    checks = interface_contract.parse(list(contract_lines))[0] if contract_lines else interface_contract.the_locked_contract(repo_root)
    routes = _the_successes_by_route(checks)
    if not routes:
        return []
    root = Path(repo_root)
    problems: list[str] = []
    for path in suite_files(repo_root):
        if path.suffix.lower() not in (".js", ".mjs", ".cjs", ".ts", ".mts", ".cts"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        starts = [m.start() for m in _A_TEST_CALL.finditer(text)]
        wrong: list[str] = []
        for at, start in enumerate(starts):
            block = text[start:starts[at + 1] if at + 1 < len(starts) else len(text)]
            line_of = lambda offset: text.count("\n", 0, start + offset) + 1  # noqa: E731
            calls = [(call.start(), call.group(1), call.group(2), call.group(3)) for call in _A_NAMED_CALL.finditer(block)]
            entries = [
                ((m.group(1) or m.group(4)), (m.group(2) if m.group(1) else m.group(3)), m.group(0))
                for m in _AN_ENTRY.finditer(block)
            ]
            for asserted in _A_STATUS_ASSERTED.finditer(block):
                name, status = asserted.group(1), int(asserted.group(2))
                if not 200 <= status < 300:
                    continue
                # The call the name was last given before the assertion: one name may hold several answers in turn.
                named = next(((verb, where) for at_, held, verb, where in reversed(calls)
                              if held == name and at_ < asserted.start()), None)
                if named and not named[1].startswith(("http", "$")):
                    route = _the_route(routes, *named)
                    if route and status not in route[0]:
                        wrong.append(f"line {line_of(asserted.start())}: `{named[0].upper()} {named[1]}` asserted {status}, "
                                     f"the contract gives {'/'.join(map(str, sorted(route[0])))} (`{route[1]}`)")
                    continue
                for method, where, entry in entries:
                    if _AN_ENTRY_S_OWN_STATUS.search(entry):
                        continue
                    route = _the_route(routes, method, where)
                    if route and status not in route[0]:
                        wrong.append(f"line {line_of(asserted.start())}: every entry of its loop asserted {status}, but "
                                     f"`{method.upper()} {where}` is given {'/'.join(map(str, sorted(route[0])))} (`{route[1]}`)")
        if wrong:
            problems.append(
                f"`{path.relative_to(root).as_posix()}`: a test asserts a success status the interface contract does "
                f"not give for that call - {'; '.join(sorted(set(wrong))[:6])}. It fails on every product that keeps "
                "the contract. Assert the status the contract gives for each call; in a loop over several, give each "
                "entry its own expected status."
            )
    return problems[:6]


#: A string or template literal: its body.
_A_LITERAL = r"(?:`((?:[^`\\]|\\.)*)`|'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\")"
#: `field: <literal>` inside a request's `data: { ... }`.
_A_FIELD_SENT = re.compile(r"\b(\w+)\s*:\s*" + _A_LITERAL)
#: `data: {` - where a request's fields begin.
_DATA_OPENS = re.compile(r"\bdata\s*:\s*\{")
#: `.title.startsWith(<literal>)`, `.title.includes(...)`, `.title.endsWith(...)`, or `.title === <literal>`.
_A_FIELD_FILTERED = re.compile(
    r"\.(\w+)\s*(?:\.\s*(startsWith|includes|endsWith)\s*\(\s*" + _A_LITERAL + r"\s*\)|===\s*" + _A_LITERAL + r")")
_INTERPOLATED = re.compile(r"\$\{([^}]*)\}")
#: A helper called with the fixture first, and the rest of its arguments: `createNote(request, 'a', 'b')`.
_A_CALL_GIVEN_THE_FIXTURE = re.compile(r"\b[A-Za-z_$][\w$]*\s*\(\s*request\s*,([^;]*?)\)\s*;")


def _the_brace_that_closes(text: str, after: int) -> int:
    """Where the `{` just before `after` closes, past quoted and template text; the end of `text` if it never does."""
    depth, at, quote = 1, after, ""
    while at < len(text):
        char = text[at]
        if quote:
            if char == "\\":
                at += 1
            elif char == quote:
                quote = ""
        elif char in "'\"`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if not depth:
                return at
        at += 1
    return len(text)


def _literal_of(match: re.Match[str], first: int) -> str:
    return next((g for g in match.groups()[first:first + 3] if g is not None), "")


def _as_made(template: str) -> str:
    """A sent value with each `${expr}` as a token of its own, the same for the same expression."""
    return _INTERPOLATED.sub(lambda m: "\x00" + " ".join(m.group(1).split()) + "\x00", template)


def _as_sought(template: str, made: set[str]) -> str:
    """A filter as a pattern: `${expr}` the test also sent is that token; any other may be anything."""
    parts, last = [], 0
    for m in _INTERPOLATED.finditer(template):
        parts.append(re.escape(template[last:m.start()]))
        expr = " ".join(m.group(1).split())
        parts.append(re.escape("\x00" + expr + "\x00") if expr in made else ".*")
        last = m.end()
    parts.append(re.escape(template[last:]))
    return "".join(parts)


def tests_that_filter_for_what_they_never_made(repo_root: str | Path) -> list[str]:
    """Tests that look in a list for values by a pattern none of the values they sent could match.

    Measured on one run: a test created `list-a-${slug}` and `list-b-${slug}`, kept the notes whose title
    `startsWith(`list-${slug}-`)` and expected two - none of its titles starts so, and no product can pass it. The QA
    lead read the test twice and called it sound. Found by its shape: the fields a test sends in `data: { ... }`,
    the same field filtered by a literal, each `${expr}` the test also sent held fixed and any other free.
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
        starts = [m.start() for m in _A_TEST_CALL.finditer(text)]
        found: list[str] = []
        for at, start in enumerate(starts):
            block = text[start:starts[at + 1] if at + 1 < len(starts) else len(text)]
            sent: dict[str, list[str]] = {}
            for opened in _DATA_OPENS.finditer(block):
                end = _the_brace_that_closes(block, opened.end())
                for field in _A_FIELD_SENT.finditer(block[opened.end():end]):
                    sent.setdefault(field.group(1), []).append(_literal_of(field, 1))
            # And what it sends through a helper given the fixture, by position, not field: measured on one run,
            # `createNote(request, 'QA-crud-title', ...)` then `n.title === 'QA-crud-title'` was flagged as never sent.
            through_a_helper = [
                _literal_of(value, 0)
                for call in _A_CALL_GIVEN_THE_FIXTURE.finditer(block)
                for value in re.finditer(_A_LITERAL, call.group(1))
            ]
            if not sent:
                continue
            for wanted in _A_FIELD_FILTERED.finditer(block):
                field, how = wanted.group(1), wanted.group(2) or "==="
                literal = _literal_of(wanted, 2) if wanted.group(2) else _literal_of(wanted, 5)
                values = (sent.get(field) or []) + (through_a_helper if sent.get(field) or through_a_helper else [])
                if not values or not literal:
                    continue
                made = {" ".join(e.split()) for v in values for e in _INTERPOLATED.findall(v)}
                pattern = _as_sought(literal, made)
                rule = {"startsWith": f"{pattern}", "endsWith": f".*{pattern}$", "includes": f".*{pattern}",
                        "===": f"{pattern}$"}[how]
                if any(re.match(rule, _as_made(v), re.S) for v in values):
                    continue
                line = text.count("\n", 0, start + wanted.start()) + 1
                shown = ", ".join(f"`{v}`" for v in values[:4])
                found.append(f"line {line}: it keeps the `{field}` values that {how if how != '===' else 'equal'} "
                             f"`{literal}`, and none it sent ({shown}) could")
        if found:
            problems.append(
                f"`{path.relative_to(root).as_posix()}`: a test looks for values none of the values it sent could be - "
                + "; ".join(found[:6])
                + ". It fails on every product. Look for what the test itself sent."
            )
    return problems[:6]


#: A service a test starts with the harness's helper: its name, and what it was started with.
_A_SERVICE_STARTED = re.compile(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*await\s+startService\s*\(([^)]*)\)")


#: A write the test sends to the suite's own server: the `request` fixture with a path, not another service's address.
_A_WRITE_TO_THE_SUITE_S_SERVER = re.compile(r"""\brequest\s*\.\s*(?:post|put|patch)\s*\(\s*['"`]/""")


def tests_that_restart_on_data_they_never_wrote(repo_root: str | Path) -> list[str]:
    """Restart tests that start a service on a fresh data folder, send it nothing, and restart on that folder.

    Measured on one run: the restart test wrote its record through the `request` fixture - the suite's own server,
    with its own data folder - then started a service on a fresh folder, stopped it, started a second on that folder
    and read the record from it: 404 on every product, and the only acceptance test left failing. A service whose
    `baseURL` the test never uses received nothing, so the one restarted on its `dataDir` starts empty.
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
        starts = [m.start() for m in _A_TEST_CALL.finditer(text)]
        for at, start in enumerate(starts):
            block = text[start:starts[at + 1] if at + 1 < len(starts) else len(text)]
            for started in _A_SERVICE_STARTED.finditer(block):
                name, given = started.group(1), started.group(2)
                if "dataDir" in given:
                    continue
                # One service, no restart: the test writes through the suite's own server and reads the record back
                # from a service it started on a fresh folder, which never saw the write. Measured on one run: the
                # QA lead named this at the lock, and the test failed on every product until the attempt ran out.
                elsewhere = _A_WRITE_TO_THE_SUITE_S_SERVER.search(block[:started.start()])
                to_it = re.search(rf"\b(?:post|put|patch)\s*\(\s*`?\$?\{{?\s*{re.escape(name)}\s*\.\s*baseURL", block)
                read_back = re.search(rf"\b{re.escape(name)}\s*\.\s*baseURL\b", block[started.end():])
                if elsewhere and read_back and not to_it:
                    line = text.count("\n", 0, start + started.start()) + 1
                    problems.append(
                        f"`{path.relative_to(root).as_posix()}` line {line}: the test writes through `request` to "
                        f"the suite's own server, then reads the record back from `{name}`, a service it started on a "
                        f"fresh data folder. `{name}` never saw that write, so it answers without the record on every "
                        f"product. Write through `{name}.baseURL`, stop it, start a second service on `{name}.dataDir`, "
                        "and read the record from that one."
                    )
                    break
                if re.search(rf"\b{re.escape(name)}\s*\.\s*baseURL\b", block):
                    continue
                if not re.search(rf"dataDir\s*:\s*{re.escape(name)}\s*\.\s*dataDir\b", block[started.end():]):
                    continue
                line = text.count("\n", 0, start + started.start()) + 1
                problems.append(
                    f"`{path.relative_to(root).as_posix()}` line {line}: the test starts `{name}` on a fresh data "
                    f"folder and never sends it anything (`{name}.baseURL` is not used), then starts a service on "
                    f"`{name}.dataDir` and reads from it. What it wrote through `request` went to the suite's own "
                    f"server, whose data folder is another one, so the restarted service starts empty on every "
                    f"product. Write through `{name}.baseURL` before `{name}.stop()` - `await request.post({name}"
                    f".baseURL + '/...', {{ data: {{ ... }} }})` - and read the same record back from the second "
                    "service."
                )
                break
    return problems[:6]


#: A path on the suite's own server, in quotes: `'/notes'`, `` `${baseURL}/notes` ``. A query, an interpolated piece or
#: another service's address is not one, so `/notes?tag=mine` and `${svc.baseURL}/notes` are left alone.
_THE_SUITE_S_PATH = r"""['"`](?:\$\{\s*(?:baseURL|baseUrl|BASE_URL|BASE|base)\s*\})?(/[\w./-]*)['"`]"""
_A_WRITE_TO_A_PATH = re.compile(
    r"\.(?:post|put|patch)\s*\(\s*" + _THE_SUITE_S_PATH
    + r"|\bfetch\s*\(\s*" + _THE_SUITE_S_PATH + r"""\s*,[^;]{0,200}?method\s*:\s*['"`](?:post|put|patch)['"`]""",
    re.I,
)
#: A read of a path. What follows the path is kept: options may narrow the list.
_A_READ_OF_A_PATH = r"(?:\.get|\bfetch)\s*\(\s*" + _THE_SUITE_S_PATH + r"\s*(\)|,[^;]{0,200}?\))"
_A_RESPONSE_READ = re.compile(r"\b([A-Za-z_$][\w$]*)\s*=\s*await\s+[\w$.]*?" + _A_READ_OF_A_PATH)
_READ_DIRECTLY = re.compile(r"await\s*\(\s*await\s+[\w$.]*?" + _A_READ_OF_A_PATH + r"\s*\)\s*\.\s*json\s*\(\s*\)")
#: A count or an empty list asserted exactly. `.not`, a computed number and `toBeGreaterThanOrEqual` do not match.
_AN_EXACT_COUNT = re.compile(
    r"expect\s*\(\s*(?P<read>\(?\s*await[^;\n]*?|[A-Za-z_$][\w$]*(?:\s*\.\s*length)?)\s*\)\s*\.\s*"
    r"(?P<how>(?:toBe|toEqual|toStrictEqual|toHaveLength)\s*\(\s*(?P<count>\d+)\s*\)|(?:toEqual|toStrictEqual)\s*\(\s*\[\s*\]\s*\))"
)
#: A list scoped to someone: the count is that someone's, and no other test's writes reach it.
_SCOPED_TO_SOMEONE = re.compile(
    r"authorization|bearer|cookie|\btoken\b|storageState|extraHTTPHeaders|newContext|sign_?-?in|log_?-?in|sign_?-?up|register",
    re.I,
)
_NARROWING_OPTIONS = re.compile(r"\b(?:params|headers)\s*:")
_A_CLEARING_CALL = r"\b\w*(?:clear|clean|reset|wipe|empty|purge|truncate|removeall|deleteall)\w*\s*\("
_DELETES_IN_A_LOOP = (r"(?:\bfor\s*\(|\.forEach\s*\(|\.map\s*\()[\s\S]{0,300}?"
                      r"""(?:\.delete\s*\(|method\s*:\s*['"`]delete['"`])""")
_A_HOOK = re.compile(r"\b(?:beforeEach|beforeAll|afterEach|afterAll)\s*\(")
_A_NAMED_HELPER = re.compile(
    r"(?:\bfunction\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{|"
    r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*(\{)?)"
)
#: How far a hook's own text is read for what it does.
_MOST_OF_A_HOOK = 800
#: The failure a shared list gives: more came back than the test expected, or an empty list that was not.
_EXPECTED_A_COUNT = re.compile(r"Expected(?: length)?:\s*(\d+)\s*\n\s*Received(?: length)?:\s*(\d+)")
_AN_ANSI_COLOUR = re.compile(r"\x1b\[[0-9;]*m")


def _the_helpers_in(text: str) -> dict[str, str]:
    """{name: its body} of each function a file defines by name, a body with no braces ending with its line."""
    helpers: dict[str, str] = {}
    for found in _A_NAMED_HELPER.finditer(text):
        name = found.group(1) or found.group(2)
        braced = found.group(1) is not None or found.group(3) is not None
        end = _the_brace_that_closes(text, found.end()) if braced else text.find("\n", found.end())
        helpers[name] = helpers.get(name, "") + text[found.end():end if end > found.end() else len(text)]
    return helpers


def _without_helper_bodies(text: str) -> str:
    """The text with each helper's body blanked, keeping every position: a helper writes only when it is called."""
    kept = list(text)
    for found in _A_NAMED_HELPER.finditer(text):
        if found.group(1) is None and found.group(3) is None:
            continue
        end = _the_brace_that_closes(text, found.end())
        if end > found.end():
            kept[found.end():end] = " " * (end - found.end())
    return "".join(kept)


def _paths_written_in(text: str) -> set[str]:
    return {(m.group(1) or m.group(2)).rstrip("/") or "/" for m in _A_WRITE_TO_A_PATH.finditer(text)}


def _the_list_read_by(block: str, read: str, at: int) -> str | None:
    """The route whose whole list `read` is at `at`, or None when it is anything else: filtered, narrowed, reassigned."""
    direct = _READ_DIRECTLY.search(read)
    if direct:
        return None if _NARROWING_OPTIONS.search(direct.group(2)) else direct.group(1).rstrip("/") or "/"
    held = re.fullmatch(r"\(?\s*await\s+([A-Za-z_$][\w$]*)\s*\.\s*json\s*\(\s*\)\s*\)?", read.strip())
    if held:
        response = held.group(1)
    else:
        assignments = list(re.finditer(rf"(?<![.\w$]){re.escape(read)}\s*=(?![=>])", block[:at]))
        if not assignments:
            return None
        rest = block[assignments[-1].end():at]
        statement = rest.split(";", 1)[0].split("\n", 1)[0].strip()
        bound = re.fullmatch(r"\(?\s*await\s+([A-Za-z_$][\w$]*)\s*\.\s*json\s*\(\s*\)\s*\)?", statement)
        if bound:
            response = bound.group(1)
        else:
            whole = _READ_DIRECTLY.fullmatch(statement)
            if not whole or _NARROWING_OPTIONS.search(whole.group(2)):
                return None
            return whole.group(1).rstrip("/") or "/"
    reads = list(re.finditer(rf"(?<![.\w$]){re.escape(response)}\s*=(?![=>])", block[:at]))
    if not reads:
        return None
    made = _A_RESPONSE_READ.match(block, reads[-1].start())
    if made is None or _NARROWING_OPTIONS.search(made.group(3)):
        return None
    return made.group(2).rstrip("/") or "/"


def _more_came_back(message: str, count: str | None) -> bool:
    """Whether a failure's message shows the shared list's fault: more records than expected, not fewer."""
    plain = _AN_ANSI_COLOUR.sub("", message)
    if count is None:
        return bool(re.search(r"^\s*-\s*Array \[\]\s*$", plain, re.M) and re.search(r"^\s*\+\s*Array \[", plain, re.M))
    return any(int(wanted) == int(count) and int(got) > int(wanted) for wanted, got in _EXPECTED_A_COUNT.findall(plain))


#: A page's list counted exactly: `expect(page.getByRole('listitem')...).toHaveCount(2)`, or through a name bound to it.
_A_LIST_ITEMS = re.compile(r"""getByRole\(\s*['"]listitem['"]\s*\)(?P<narrowed>(?:\s*\.\s*filter\(\s*\{[^}]*\}\s*\))*)""")
_A_PAGE_COUNT = re.compile(r"""expect\(\s*(?P<read>[^;]*?)\s*\)\s*\.\s*toHaveCount\(\s*(?P<count>\d+)\s*\)""", re.S)
_HAS_TEXT = re.compile(r"""hasText:\s*(['"])((?:(?!\1).)+)\1""")
_A_FILTER_TYPED = re.compile(
    r"""getBy(?:Label|Role|Placeholder)\([^)]*(?:filter|search)[^)]*\)\s*\.\s*fill\(\s*(['"`])((?:(?!\1).)*)\1""", re.I)


def page_tests_that_count_a_shared_list(repo_root: str | Path, result: AcceptanceResult | None = None) -> list[str]:
    """Page tests that count every item of a list, or the items a value other tests also give, on a shared service.

    Measured on three full-stack runs: a test expected `getByRole('listitem')` to hold exactly 2 while every test adds
    records to the one service the suite starts; another narrowed the list by the tag "A" that five tests gave their
    records and expected exactly 2. `tests_that_count_a_list_other_tests_write_to` reads API routes only, so both were
    locked and charged to the product. Until the lock, the shape; once locked, a failing test only when its own message
    shows more came back than it expected; a passing test never.
    """
    from app.acceptance.requests import _A_SHARED_SERVICE  # noqa: PLC0415 - requests imports this module

    found = contract.the_pack(repo_root)
    if found is None or getattr(found[0], "kind", "") != "fullstack" or "fullstack" not in _A_SHARED_SERVICE:
        return []
    known = result is not None and result.ran and bool(result.report.tests)
    failing = {t.name: t.message for t in result.report.tests if t.outcome == "failed"} if known else {}
    # Unlike the API check, the shape is enough until the lock: at the lock the starting page passes some tests while
    # every count meets an empty list, so proof that more came back cannot exist yet (measured: locked again).
    needs_proof = known and is_locked(repo_root)
    root = Path(repo_root)
    problems: list[str] = []
    for path in suite_files(repo_root):
        if path.suffix.lower() not in (".js", ".mjs", ".cjs", ".ts", ".mts", ".cts"):
            continue
        try:
            text = _A_COMMENT_LINE.sub("", path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        hooks = "\n".join(text[m.start():m.start() + _MOST_OF_A_HOOK] for m in _A_HOOK.finditer(text))
        if re.search(_A_CLEARING_CALL, hooks, re.I) or re.search(_DELETES_IN_A_LOOP, hooks, re.I):
            continue
        starts = [m.start() for m in _A_TEST_DECLARED.finditer(text)]
        blocks = [(start, text[start:starts[at + 1] if at + 1 < len(starts) else len(text)])
                  for at, start in enumerate(starts)]
        for at, (start, block) in enumerate(blocks):
            others = "\n".join(b for n, (_, b) in enumerate(blocks) if n != at)
            bound = {m.group(1): m.group(2) for m in re.finditer(
                r"""(?:const|let|var)\s+(\w+)\s*=\s*(page\s*\.\s*getByRole\(\s*['"]listitem['"]\s*\)[^;\n]*)""", block)}
            titled = _A_DECLARED_TITLE.match(block)
            title = titled.group(1).strip() if titled else ""
            for count in _A_PAGE_COUNT.finditer(block):
                if int(count.group("count")) < 1:
                    continue
                read = count.group("read").strip()
                # A bound locator, narrowed further where it is read: `filteredItems.filter({ hasText: tag })`.
                named = re.match(r"(\w+)([\s\S]*)", read)
                expression = bound[named.group(1)] + named.group(2) if named and named.group(1) in bound else read
                items = _A_LIST_ITEMS.search(expression)
                if items is None:
                    continue
                narrowing = expression[items.start():]
                # Narrowed by a value held in a name or made at run time, not a quoted one: the test's own, as far as
                # its text shows. Measured on one run: six counts narrowed by a unique tag in a name were sent back.
                if ".filter(" in narrowing and not _HAS_TEXT.search(narrowing):
                    continue
                before = block[:count.start()]
                # A test that empties the list first knows what it holds, as the API check allows.
                if re.search(_A_CLEARING_CALL, before, re.I) or re.search(_DELETES_IN_A_LOOP, before, re.I):
                    continue
                values = [m.group(2) for m in _HAS_TEXT.finditer(narrowing)]
                # A list narrowed by typing into the page's filter: the value last typed there, if any is left.
                typed = [m.group(2) for m in _A_FILTER_TYPED.finditer(before)]
                if typed and typed[-1].strip():
                    values.append(typed[-1])
                shared = [v for v in values if re.search(rf"""(['"`]){re.escape(v)}\1""", others)]
                if values and not shared:
                    continue
                if known:
                    messages = [m for name, m in failing.items() if title and title in name]
                    if not messages or (needs_proof and not any(_more_came_back(m, count.group("count")) for m in messages)):
                        continue
                line = text.count("\n", 0, start + count.start()) + 1
                what = (f"the list's items narrowed by '{shared[0]}', a value other tests give their records too"
                        if shared else "every item of the page's list")
                problems.append(
                    f"`{path.relative_to(root).as_posix()}` line {line}: `{title}` counts {what} "
                    f"(`toHaveCount({count.group('count')})`), but the suite starts one service for all its tests, so "
                    "other tests' records are in that list as well and the count holds on no product once they run. "
                    "Count only this test's own records: give them a title or value no other test uses, and narrow "
                    "the list by it."
                )
    return problems[:6]


def tests_that_count_a_list_other_tests_write_to(repo_root: str | Path, result: AcceptanceResult | None = None) -> list[str]:
    """Tests that assert an exact length or an empty list on a route other tests of the suite also write to.

    Measured on one run: a test expected `/notes` to hold exactly 2 and received 8, because the suite shares one
    service and its data among all its tests. No fixer could satisfy it, and the run spent six fix stages before any
    dispute. Left alone: a list filtered first, a count compared with an earlier count, a test or a file on a service
    of its own, a test that empties the list first, a list scoped to a signed-in user, a route nothing else writes to.

    The kept packs give every service and full-stack suite one server for the whole run, one worker in file order, and
    no fresh store per test, so this holds for those kinds only; a suite with no pack is not assumed to share anything.

    Once results are known, a passing test is never named: an earlier test may have cleaned up after itself, so the
    count is fragile but works, and reopening a working suite costs more than the risk. Once the product answers (the
    suite is locked, or anything passed), a failing test is named only if its own message shows more came back than
    expected: fewer, or a failure before the count, is the product's to answer for. Before that, nothing is known and
    the shape alone is named, while it costs the writer one round.
    """
    from app.acceptance.requests import _A_SHARED_SERVICE  # noqa: PLC0415 - requests imports this module

    found = contract.the_pack(repo_root)
    if found is None or getattr(found[0], "kind", "") not in _A_SHARED_SERVICE:
        return []
    root = Path(repo_root)
    texts: dict[Path, str] = {}
    for path in suite_files(repo_root):
        if path.suffix.lower() not in (".js", ".mjs", ".cjs", ".ts", ".mts", ".cts"):
            continue
        try:
            texts[path] = _A_COMMENT_LINE.sub("", path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    helpers: dict[str, str] = {}
    for text in texts.values():
        for name, body in _the_helpers_in(text).items():
            helpers[name] = helpers.get(name, "") + "\n" + body

    def calls(block: str) -> set[str]:
        return {name for name in helpers if re.search(rf"(?<![.\w$]){re.escape(name)}\s*\(", block)}

    written_by_helper = {name: _paths_written_in(_without_helper_bodies(body)) for name, body in helpers.items()}
    for _ in range(3):  # A helper that calls a helper.
        for name, body in helpers.items():
            for called in calls(body) - {name}:
                written_by_helper[name] |= written_by_helper[called]
    clearing = [name for name, body in helpers.items() if re.search(_DELETES_IN_A_LOOP, body, re.I)]

    def clears(block: str) -> bool:
        return bool(re.search(_A_CLEARING_CALL, block, re.I) or re.search(_DELETES_IN_A_LOOP, block, re.I)
                    or any(re.search(rf"(?<![.\w$]){re.escape(name)}\s*\(", block) for name in clearing))

    # A test's blocks by file, and which of them write to which route, leaving out files on a server of their own.
    blocks: dict[Path, list[tuple[int, str]]] = {}
    writers: dict[str, set[tuple[Path, int]]] = {}
    for path, text in texts.items():
        starts = [m.start() for m in _A_TEST_DECLARED.finditer(text)]
        if not starts:
            continue
        hooks = "\n".join(text[m.start():m.start() + _MOST_OF_A_HOOK] for m in _A_HOOK.finditer(text))
        if "startService(" in text[:starts[0]].replace(" ", "") or re.search(r"\bstartService\s*\(", hooks):
            continue
        blocks[path] = [(start, text[start:starts[at + 1] if at + 1 < len(starts) else len(text)])
                        for at, start in enumerate(starts)]
        for start, block in blocks[path]:
            paths = _paths_written_in(_without_helper_bodies(block))
            for name in calls(block):
                paths |= written_by_helper[name]
            for route in paths:
                writers.setdefault(route, set()).add((path, start))

    known = result is not None and result.ran and bool(result.report.tests)
    failing = {t.name: t.message for t in result.report.tests if t.outcome == "failed"} if known else {}
    needs_proof = known and (is_locked(repo_root) or any(t.outcome == "passed" for t in result.report.tests))

    problems: list[str] = []
    for path, tests in blocks.items():
        text = texts[path]
        if _SCOPED_TO_SOMEONE.search(text):
            continue
        hooks = "\n".join(text[m.start():m.start() + _MOST_OF_A_HOOK] for m in _A_HOOK.finditer(text))
        if clears(hooks):
            continue
        for start, block in tests:
            if re.search(r"\bstartService\s*\(", block):
                continue
            titled = _A_DECLARED_TITLE.match(block)
            title = titled.group(1).strip() if titled else ""
            for count in _AN_EXACT_COUNT.finditer(block):
                # `expect(list.length).toBe(2)` reads the list `.length` hangs from; `expect(list).toHaveLength(2)` and
                # `expect(list).toEqual([])` read the list itself. `expect(note.id).toBe(2)` is neither.
                read = count.group("read").strip()
                of_a_length = re.fullmatch(r"(.+?)\s*\.\s*length", read, re.S)
                of_the_list = count.group("how").startswith("toHaveLength") or count.group("count") is None
                if of_the_list == bool(of_a_length):
                    continue
                route = _the_list_read_by(block, of_a_length.group(1).strip() if of_a_length else read, count.start())
                if route is None or clears(block[:count.start()]):
                    continue
                others = writers.get(route, set()) - {(path, start)}
                if not others:
                    continue
                if known:
                    messages = [m for name, m in failing.items() if title and title in name]
                    if not messages:
                        continue
                    if needs_proof and not any(_more_came_back(m, count.group("count")) for m in messages):
                        continue
                line = text.count("\n", 0, start + count.start()) + 1
                wanted = "an empty list" if count.group("count") is None else f"exactly {count.group('count')}"
                problems.append(
                    f"`{path.relative_to(root).as_posix()}` line {line}: `{title}` expects {wanted} from the whole "
                    f"list at `{route}`, and other tests in the suite write to `{route}` as well. They all share one "
                    "service and its data for the whole run, so that count depends on what ran before it and no "
                    "product can be made to answer it. Keep only the records this test made - give them a value of "
                    "its own and `.filter` on it - and count those, or compare with a count it read first "
                    "(`before.length + 1`), or use `toBeGreaterThanOrEqual`."
                )
                break
    return problems[:6]


#: A Python function, test or helper, at any indent; its body runs to the next one at the same indent or less.
_A_PYTHON_DEF = re.compile(r"^([ \t]*)(?:async[ \t]+)?def[ \t]+(\w+)[ \t]*\(", re.M)
#: A request that writes to a path: `client.post("/notes"`, `httpx.post(f"{base}/notes"`, `requests.put(BASE + "/notes"`.
_A_PYTHON_WRITE = re.compile(
    r"\.(?:post|put|patch)\(\s*(?:[\w.]+\s*\+\s*)?f?[\"'](?:\{[^}\"']*\})?(/[^\"'?{}]*)")
#: A request that reads one, assigned: `resp = client.get("/notes")`.
_A_PYTHON_READ = re.compile(
    r"\b(\w+)\s*=\s*[\w.]+\.get\(\s*(?:[\w.]+\s*\+\s*)?f?[\"'](?:\{[^}\"']*\})?(/[^\"'?{}]*)[\"']\s*\)")
#: `assert len(notes) == 2`, `assert len(resp.json()) == 2`, `assert notes == []`.
_A_PYTHON_EXACT_COUNT = re.compile(
    r"^[ \t]*assert[ \t]+(?:len\((?P<read>[\w.]+(?:\(\))?)\)[ \t]*==[ \t]*(?P<count>\d+)"
    r"|(?P<empty>[\w.]+(?:\(\))?)[ \t]*==[ \t]*\[\])[ \t]*$", re.M)
#: pytest's own words for a failed comparison: `assert 3 == 2`.
_PYTHON_COMPARED = re.compile(r"\bassert (\d+) == (\d+)\b")


def _python_defs(text: str) -> dict[str, str]:
    """Each function's name and its whole text, its decorators' lines included."""
    found: dict[str, str] = {}
    marks = list(_A_PYTHON_DEF.finditer(text))
    for at, mark in enumerate(marks):
        indent = len(mark.group(1).expandtabs())
        end = len(text)
        for later in marks[at + 1:]:
            if len(later.group(1).expandtabs()) <= indent:
                end = text.rfind("\n", 0, later.start()) + 1 or later.start()
                break
        begin = mark.start()
        while True:
            above = text.rfind("\n", 0, max(begin - 1, 0))
            line = text[above + 1:begin].strip() if begin else ""
            if not line.startswith("@"):
                break
            begin = above + 1
        found[mark.group(2)] = text[begin:end]
    return found


def _python_route_counted(block: str, read: str, at: int) -> str | None:
    """The route a counted list was read from, when the test reads it straight from one; None otherwise."""
    name = read.removesuffix(".json()").removesuffix("()")
    response = name
    if not read.endswith(".json()"):
        bound = list(re.finditer(rf"\b{re.escape(name)}\s*=\s*(\w+)\.json\(\)\s*$", block[:at], re.M))
        if not bound:
            return None
        response = bound[-1].group(1)
    reads = [m for m in _A_PYTHON_READ.finditer(block[:at]) if m.group(1) == response]
    return reads[-1].group(2).rstrip("/") or "/" if reads else None


#: A count of every row of a table, with no condition naming the records a test made.
_A_WHOLE_TABLE_COUNT = re.compile(r"select\s+count\s*\(\s*\*\s*\)\s+from\s+[`\"\[]?(\w+)[`\"\]]?(?![^'\"\n]*\bwhere\b)", re.I)
#: What a failed equality of counts reports: `assert 19 == 0`.
_A_COUNT_TOO_HIGH = re.compile(r"assert\s+(\d+)\s*==\s*(\d+)")


def tests_that_count_every_row_of_a_shared_table(repo_root: str | Path, result: AcceptanceResult | None) -> list[str]:
    """Failed Python tests that counted every row of a table and found more than they expected.

    Every test shares one service and its data, so a whole-table count holds what the tests before it made. Measured
    on one run: `SELECT COUNT(*) FROM accounts` expected 0 after a refused signup and found 19 - four fix rounds and a
    re-planned sprint went at a product that was right. Only a test that failed with a count above the one it
    expected is named.
    """
    if result is None or not getattr(result, "ran", False):
        return []
    failing = {t.name: str(t.message or "") for t in result.report.tests if t.outcome == "failed"}
    if not failing:
        return []
    root = Path(repo_root)
    problems = []
    for path in suite_files(repo_root):
        if path.suffix.lower() != ".py":
            continue
        try:
            text = re.sub(r"^[ \t]*#.*$", "", path.read_text(encoding="utf-8", errors="replace"), flags=re.M)
        except OSError:
            continue
        for name, body in _python_defs(text).items():
            message = next((m for test, m in failing.items() if test == name or test.endswith(f"::{name}") or test.endswith(f".{name}")), None)
            counted = _A_WHOLE_TABLE_COUNT.search(body)
            high = _A_COUNT_TOO_HIGH.search(message or "")
            if message is None or not counted or not high or int(high.group(1)) <= int(high.group(2)):
                continue
            problems.append(
                f"`{path.relative_to(root).as_posix()}`: `{name}` counts every row of `{counted.group(1)}` and expects "
                f"{high.group(2)}, but the suite's other tests write to the same store and it found {high.group(1)} - no "
                "product can make that count come out. Count only the records this test made (a value of its own in a "
                "`WHERE`), or compare with a count it read first."
            )
    return problems[:6]


def python_tests_that_count_a_list_other_tests_write_to(
    repo_root: str | Path, result: AcceptanceResult | None = None
) -> list[str]:
    """`tests_that_count_a_list_other_tests_write_to` for a suite written in Python, with the same rules.

    Measured on one run: a pytest suite created one note in one test, two in the next, and asserted the list held
    exactly 2; it held 3, and two fix stages over half an hour went at a product that was right. The check read only
    JavaScript suites.
    """
    from app.acceptance.requests import _A_SHARED_SERVICE  # noqa: PLC0415 - requests imports this module

    found = contract.the_pack(repo_root)
    if found is None or getattr(found[0], "kind", "") not in _A_SHARED_SERVICE:
        return []
    root = Path(repo_root)
    files: dict[Path, dict[str, str]] = {}
    for path in suite_files(repo_root):
        if path.suffix.lower() != ".py":
            continue
        try:
            text = re.sub(r"^[ \t]*#.*$", "", path.read_text(encoding="utf-8", errors="replace"), flags=re.M)
        except OSError:
            continue
        files[path] = _python_defs(text)
    helpers = {name: body for defs in files.values() for name, body in defs.items() if not name.startswith("test")}

    def writes(block: str, seen: frozenset[str] = frozenset()) -> set[str]:
        routes = {m.group(1).rstrip("/") or "/" for m in _A_PYTHON_WRITE.finditer(block)}
        for name, body in helpers.items():
            if name not in seen and re.search(rf"(?<![.\w]){re.escape(name)}\s*\(", block):
                routes |= writes(body, seen | {name})
        return routes

    def clears(block: str) -> bool:
        return bool(re.search(_A_CLEARING_CALL, block, re.I))

    tests = {(path, name): body for path, defs in files.items() for name, body in defs.items() if name.startswith("test")}
    writers: dict[str, set[tuple[Path, str]]] = {}
    for key, body in tests.items():
        for route in writes(body):
            writers.setdefault(route, set()).add(key)

    known = result is not None and result.ran and bool(result.report.tests)
    failing = {t.name: t.message for t in result.report.tests if t.outcome == "failed"} if known else {}
    needs_proof = known and (is_locked(repo_root) or any(t.outcome == "passed" for t in result.report.tests))

    problems: list[str] = []
    for (path, name), body in tests.items():
        fixtures = "\n".join(b for b in files[path].values() if "fixture" in b.split("def", 1)[0])
        if _SCOPED_TO_SOMEONE.search(body) or clears(fixtures):
            continue
        for count in _A_PYTHON_EXACT_COUNT.finditer(body):
            read = count.group("read") or count.group("empty")
            route = _python_route_counted(body, read, count.start())
            if route is None or clears(body[:count.start()]):
                continue
            if not writers.get(route, set()) - {(path, name)}:
                continue
            if known:
                messages = [m for test, m in failing.items() if test == name or test.endswith(("." + name, "::" + name))]
                if not messages:
                    continue
                wanted_count = count.group("count")
                if needs_proof and not any(
                    wanted_count is not None and int(wanted) == int(wanted_count) and int(got) > int(wanted)
                    for m in messages for got, wanted in _PYTHON_COMPARED.findall(m)
                ):
                    continue
            text = path.read_text(encoding="utf-8", errors="replace")
            line = text.count("\n", 0, max(text.find(count.group(0).strip()), 0)) + 1
            wanted = "an empty list" if count.group("count") is None else f"exactly {count.group('count')}"
            problems.append(
                f"`{path.relative_to(root).as_posix()}` line {line}: `{name}` expects {wanted} from the whole list at "
                f"`{route}`, and other tests in the suite write to `{route}` as well. They all share one service and "
                "its data for the whole run, so that count depends on what ran before it and no product can be made to "
                "answer it. Keep only the records this test made - give them a value of its own and filter on it - "
                "and count those, or compare with a count it read first (`len(before) + 1`), or assert `>=`."
            )
            break
    return problems[:6]


#: A test's title, from its declaration.
_A_TEST_TITLE = re.compile(r"""test\s*\(\s*['"`]([^'"`]*)['"`]""")


#: A test's declaration, not a regular expression's `.test(`: that would cut a test in two where it reads the file.
_A_TEST_DECLARED = re.compile(r"(?<![.\w$])(?:test|it)(?:\.(?:only|fixme|fail|slow))?\s*\(")
_A_DECLARED_TITLE = re.compile(r"""(?:test|it)(?:\.\w+)?\s*\(\s*['"`]([^'"`]*)['"`]""")
#: A comment's whole line: what it reads is not read.
_A_COMMENT_LINE = re.compile(r"^[ \t]*(?://|#).*$", re.M)
#: What reads a file's text. Not `existsSync`, `statSync` or `accessSync`: that a kept file is there, or may be run, is
#: true on every product.
_A_TEXT_READ = re.compile(r"\b(?:readFile(?:Sync)?|createReadStream)\s*\(")
_A_PYTHON_OPEN = re.compile(r"(?<![.\w])open\s*\(")
_A_PYTHON_READ_ON = re.compile(r"\.(?:read_text|read_bytes|open)\s*\(")
_A_JS_ASSERTION = re.compile(r"\b(?:expect(?:\.soft)?|assert(?:\.\w+)?)\s*\(")
_A_PYTHON_ASSERTION_LINE = re.compile(r"^[ \t]*assert\b", re.M)
_AN_ASSIGNMENT = re.compile(r"(?:^|(?<=[\s;{(]))(?:(?:const|let|var)\s+)?([A-Za-z_$][\w$]*)(?:[ \t]*:[ \t]*[\w<>\[\]| ]+?)?[ \t]*=(?![=>])", re.M)
_A_WITH_AS = re.compile(r"^[ \t]*with\s+(.+?)\s+as\s+(\w+)\s*:", re.M)
#: In a path's expression: a string, or a name that is not called or looked into (`path.join`, `process.env`).
_A_PATH_PIECE = re.compile(
    r"""(['"`])((?:\\.|(?!\1).)*)\1|(?<![\w.$])([A-Za-z_$][\w$]*)(?![\w$]*\s*[.(\['"`])""", re.S)
_A_NAME_IN_A_STRING = re.compile(r"\$?\{([A-Za-z_$][\w$]*)\}")
#: The longest expression followed; a quote a regular expression left open must not swallow the file.
_MOST_EXPRESSION = 2000


def _expression_at(text: str, at: int, stops: str) -> str:
    """`text` from `at` to the first of `stops` outside brackets and strings, or the bracket that closes around it."""
    while at < len(text) and text[at] in " \t\n":
        at += 1
    depth, quote, here, end = 0, "", at, min(len(text), at + _MOST_EXPRESSION)
    while here < end:
        character = text[here]
        if quote:
            if character == "\\":
                here += 1
            elif character == quote:
                quote = ""
        elif character in "'\"`":
            quote = character
        elif character in "([{":
            depth += 1
        elif character in ")]}":
            if not depth:
                break
            depth -= 1
        elif not depth and character in stops:
            break
        here += 1
    return text[at:here]


def _assignments(text: str) -> dict[str, str]:
    """{name: the expression last assigned to it} in `text`, a `with ... as name` among them."""
    found = {m.group(1): _expression_at(text, m.end(), ";\n") for m in _AN_ASSIGNMENT.finditer(text)}
    found.update({m.group(2): m.group(1) for m in _A_WITH_AS.finditer(text)})
    return found


def _path_parts(expression: str, defined: dict[str, str], seen: tuple[str, ...] = ()) -> list[str]:
    """The folders and file `expression` names, following each name it uses to what was assigned to it."""
    parts: list[str] = []

    def named(name: str) -> None:
        if name in defined and name not in seen:
            parts.extend(_path_parts(defined[name], defined, (*seen, name)))

    for match in _A_PATH_PIECE.finditer(expression):
        if match.group(3) is not None:
            named(match.group(3))
            continue
        for at, piece in enumerate(_A_NAME_IN_A_STRING.split(match.group(2))):
            if at % 2:
                named(piece)
            else:
                parts.extend(part for part in re.split(r"[\\/]", piece) if part not in ("", ".", ".."))
    return parts


def _the_kept_file_named(parts: list[str], kept: frozenset[str]) -> str | None:
    """The kept file a path names, by its whole tail: `fixtures/start.sh` is not the kept `start.sh`."""
    for path in kept:
        mine = path.split("/")
        if parts and (mine[-len(parts):] == parts or (len(mine) > 1 and parts[-len(mine):] == mine)):
            return mine[-1]
    return None


def _the_kept_file_read(text: str, defined: dict[str, str], kept: frozenset[str], python: bool) -> str | None:
    """The kept file whose text `text` reads, else None."""
    arguments = [_expression_at(text, m.end(), ",;") for m in (_A_PYTHON_OPEN if python else _A_TEXT_READ).finditer(text)]
    if python:
        for match in _A_PYTHON_READ_ON.finditer(text):
            start = match.start()
            while start:
                character = text[start - 1]
                if character in ")]":
                    closing, opening, depth = character, "(" if character == ")" else "[", 0
                    while start:
                        start -= 1
                        depth += (text[start] == closing) - (text[start] == opening)
                        if not depth:
                            break
                elif character.isalnum() or character in "_.":
                    start -= 1
                else:
                    break
            arguments.append(text[start:match.start()])
    return next((name for name in (_the_kept_file_named(_path_parts(a, defined), kept) for a in arguments) if name), None)


def _a_kept_file_s_text_asserted(block: str, before_the_tests: str, kept: frozenset[str], python: bool) -> str | None:
    """The kept file whose text the test `block` asserts on, directly or through the variables holding it; else None."""
    defined = {**_assignments(before_the_tests), **_assignments(block)}
    holding: dict[str, str] = {}
    for name, expression in defined.items():
        read = _the_kept_file_read(expression, defined, kept, python)
        if read:
            holding[name] = read
    for _ in defined:  # what is made from the text holds it too: `script.split("\n")`, `f.read()`
        more = {
            name: next(holding[held] for held in holding if re.search(rf"(?<![\w$.]){re.escape(held)}\b", expression))
            for name, expression in defined.items()
            if name not in holding and any(re.search(rf"(?<![\w$.]){re.escape(held)}\b", expression) for held in holding)
        }
        if not more:
            break
        holding.update(more)
    asserted = (
        [_expression_at(block, m.end(), "\n") for m in _A_PYTHON_ASSERTION_LINE.finditer(block)] if python
        else [_expression_at(block, m.end(), "") for m in _A_JS_ASSERTION.finditer(block)]
    )
    for assertion in asserted:
        direct = _the_kept_file_read(assertion, defined, kept, python)
        if direct:
            return direct
        for name, read in holding.items():
            if re.search(rf"(?<![\w$.]){re.escape(name)}\b", assertion):
                return read
    return None


def tests_that_assert_a_kept_file_s_text(repo_root: str | Path, result: AcceptanceResult | None = None) -> list[str]:
    """Tests that read a file the harness keeps and assert what it contains: its text is not the product's to change.

    Measured on one run: a test read `./start.sh` and expected it to match `/DATA_DIR/`; the harness's start file
    reads nothing but its service, and `contract.enforce` puts it back before every run, so the test failed on every
    product and no fixer could reach it. The criterion such a test is for is proven by what the service does when
    started through the kept file - it answers on `PORT`, keeps its data under `DATA_DIR` - which the suite's own
    server already shows.
    """
    kept = contract.kept_paths(repo_root)
    if not kept:
        return []
    # Only a test that fails: one that passes against the kept file proves nothing, but costs nothing either, and
    # measured on one run a green suite was reopened for it, QA spent three rounds, and locked with it as it was.
    failing = ({t.name for t in result.report.tests if t.outcome == "failed"}
               if result is not None and result.ran and result.report.tests else None)
    root = Path(repo_root)
    problems: list[str] = []
    for path in suite_files(repo_root):
        python = path.suffix.lower() == ".py"
        if not python and path.suffix.lower() not in (".js", ".mjs", ".cjs", ".ts", ".mts", ".cts"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        text = _A_COMMENT_LINE.sub("", text)
        starts = [m.start() for m in (_A_PYTHON_TEST if python else _A_TEST_DECLARED).finditer(text)]
        before_the_tests = text[:starts[0]] if starts else ""
        for at, start in enumerate(starts):
            block = text[start:starts[at + 1] if at + 1 < len(starts) else len(text)]
            if failing is not None:
                titled = (_A_PYTHON_TEST if python else _A_DECLARED_TITLE).match(block)
                title = titled.group(1).strip() if titled else ""
                if not title or not any(title in name for name in failing):
                    continue
            name = _a_kept_file_s_text_asserted(block, before_the_tests, kept, python)
            if name is None:
                continue
            line = text.count("\n", 0, start) + 1
            problems.append(
                f"`{path.relative_to(root).as_posix()}` line {line}: the test reads `{name}` and asserts what it "
                f"contains. The harness keeps that file and puts it back before every run, so its text is not the "
                "product's to change and the test cannot pass on any product. Test what the file does instead, by "
                "reaching the running service - it answers on the suite's address and keeps its data under `DATA_DIR` "
                "- not by reading the file. That the file exists, may be run or starts the service can stay."
            )
    return problems[:6]


#: A call that signs a user in with a literal username: `_signin(base_url, "ana", "pw")`, `logIn(request, 'ana', 'pw')`.
_A_SIGN_IN_AS = re.compile(
    r"""\b\w*(?:sign_?in|log_?in|authenticate|obtain_?token|get_?token)\w*\s*\(\s*(?:[A-Za-z_][\w.]*\s*,\s*)?(['"`])([^'"`\n]+)\1""",
    re.I,
)
#: Anything that creates a user.
_CREATES_A_USER = re.compile(r"sign_?up|register|create_?(?:user|account)|/users\b|/accounts\b", re.I)
#: A block that expects a refusal: signing in as someone unknown is the point of it.
_EXPECTS_A_REFUSAL = re.compile(r"\b40[0134]\b|\b422\b|toBeGreaterThanOrEqual\(\s*400|>=\s*400")


def tests_that_sign_in_as_nobody(repo_root: str | Path) -> list[str]:
    """Tests that sign in as a user the suite never creates: refused on every product that checks credentials.

    Measured on two runs of the held-out family: QA wrote tests that signed in as `ac3user` through a helper and
    never signed that user up, here or in any fixture. Every product answered 401, the test round raised the tests
    as product defects, and a fix round and a dispute were spent before QA was sent back; in the second run seven
    tests had the fault. Found by its shape: a test that signs in with a literal username, mentions no sign-up or
    registration anywhere, expects no refusal, and whose username appears nowhere else in the suite (so no fixture
    seeds it).
    """
    root = Path(repo_root)
    texts: dict[Path, str] = {}
    for path in suite_files(repo_root):
        if path.suffix.lower() not in (".py", ".js", ".mjs", ".cjs", ".ts", ".mts", ".cts"):
            continue
        try:
            texts[path] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    everything = "\n".join(texts.values())
    problems: list[str] = []
    for path, text in texts.items():
        python = path.suffix.lower() == ".py"
        starts = [m.start() for m in (_A_PYTHON_TEST if python else _A_TEST_CALL).finditer(text)]
        for at, start in enumerate(starts):
            block = text[start:starts[at + 1] if at + 1 < len(starts) else len(text)]
            if _CREATES_A_USER.search(block) or _EXPECTS_A_REFUSAL.search(block):
                continue
            for match in _A_SIGN_IN_AS.finditer(block):
                name = match.group(2)
                if name.startswith("/") or not name.strip():
                    continue
                signing_in = sum(1 for m in _A_SIGN_IN_AS.finditer(everything) if m.group(2) == name)
                if everything.count(match.group(1) + name + match.group(1)) > signing_in:
                    continue  # the name is used somewhere that is not a sign-in: a fixture or a call may create it
                line = text.count("\n", 0, start + match.start()) + 1
                problems.append(
                    f"`{path.relative_to(root).as_posix()}` line {line}: the test signs in as `{name}`, a user nothing "
                    "in the suite creates. Every test starts from an empty product, so the sign-in is refused on every "
                    "product that checks credentials. Create the user first, through the product as a person would, "
                    "and sign in as that user."
                )
                break
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


def _the_project_dir(repo_root: str | Path) -> Path | None:
    found = location(repo_root)
    return (Path(repo_root) / found[0]) if found and found[0] else None


def page_load_problems(repo_root: str | Path) -> list[str]:
    """What the page itself reported when the page check loaded it - console errors, uncaught errors; [] for none."""
    try:
        from app.stacks.packs._javascript import PAGE_LOAD_REPORT

        project = _the_project_dir(repo_root)
        if project is None:
            return []
        data = json.loads((project / PAGE_LOAD_REPORT).read_text(encoding="utf-8"))
        return [str(item) for item in (data.get("problems") or []) if str(item).strip()][:8]
    except (OSError, ValueError, AttributeError):
        return []


def what_the_criteria_s_tests_printed(repo_root: str | Path, tags: Any) -> dict[str, str] | None:
    """The failing tests of the criteria `tags` names, with what each printed, from the suite's last run; else None.

    For a fixer of a failing criterion. Measured on one run: the fixer of "[AC-5] Delete a note" was shown, as the
    machine's own output to believe, a run of two other criteria's tests that a different stage had made.
    """
    wanted = [t for t in tags or () if str(t).startswith(("AC-", "CR-"))]
    if not wanted:
        return None
    found = last_result(repo_root)
    failing = []
    for tag in wanted:
        entry = (found.get("criteria") or {}).get(tag) or (found.get("change_requests") or {}).get(tag) or {}
        failing += [t for t in entry.get("tests") or [] if t.get("outcome") == "failed"]
    if not failing:
        return None
    names = list(dict.fromkeys(str(t.get("name") or "") for t in failing))
    output = "\n\n".join(f"{t.get('name')}:\n{t.get('message') or '(no message)'}" for t in failing)
    # What the page said when it loaded. Measured on one run: its own script never loaded ("Failed to load module
    # script ... MIME type of text/css"), the page check recorded it, and six fixers of the failing page tests,
    # never shown it, each guessed at why a link was not visible.
    reported = page_load_problems(repo_root)
    if reported:
        output += "\n\nWhen the page itself loaded, it reported:\n" + "\n".join(f"- {item}" for item in reported)
    return {"command": "the acceptance suite's last run: " + ", ".join(names), "output": output,
            "title": "What its failing tests printed"}


#: How a unit-test defect opens (`_raise_defects_from_report`): only those get the unit report's failures.
_A_UNIT_TEST_DEFECT = re.compile(r"^\s*The unit tests fail\b", re.I)
MOST_UNIT_FAILURES_SHOWN = 8


def what_the_unit_tests_printed(repo_root: str | Path, description: str) -> dict[str, str] | None:
    """For a unit-test defect: its failing tests and what each printed, from the last unit report; else None.

    The tests the description names, or every failing one when it names none (at most eight). Measured on 2026-11-07:
    521 of 625 fixer requests were shown "the last failing command" - perhaps another defect's - and LF.607 covered
    acceptance criteria only. The JUnit report holds each failing test's message on every stack.
    """
    if not _A_UNIT_TEST_DEFECT.search(str(description or "")):
        return None
    try:
        found = contract.the_pack(repo_root)
        where = location(repo_root)
        if found is None or where is None or not found[0].unit_report:
            return None
        from app.acceptance import junit

        report = junit.read(Path(repo_root) / where[0] / found[0].unit_report)
    except Exception:  # noqa: BLE001 - the fixer falls back to the last failing command
        return None
    failing = [t for t in report.tests if t.outcome == "failed"]
    if not failing:
        return None
    named = [t for t in failing if str(t.name or "").split("::")[-1].split(".")[-1] in str(description)]
    shown = (named or failing)[:MOST_UNIT_FAILURES_SHOWN]
    output = "\n\n".join(f"{t.name}:\n{(t.message or '(no message)').strip()}" for t in shown)
    return {"command": "the unit tests' last run: " + ", ".join(str(t.name) for t in shown), "output": output,
            "title": "What its failing tests printed"}


def last_result(repo_root: str | Path) -> dict[str, Any]:
    try:
        return json.loads((Path(repo_root) / RESULT_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}



_SAYS_IT_FAILS = re.compile(r"\b(fails?|failing|failed|does not pass|cannot pass)\b", re.IGNORECASE)


def open_problems_still_true(repo_root: str | Path, problems: list[str]) -> list[str]:
    """The lock's open problems less those the latest measurement contradicts.

    A note that a named test fails is no longer true once that test passes: shipping it reads as a broken
    product when the suite ran green. A note naming any test still failing, or about a test's strength
    rather than its outcome, is kept.
    """
    outcomes: dict[str, str] = {}
    for criterion in (last_result(repo_root).get("criteria") or {}).values():
        for test in (criterion or {}).get("tests") or []:
            name = str((test or {}).get("name") or "").strip()
            if len(name) >= 12:
                outcomes[name] = str(test.get("outcome") or "")
    kept = []
    for problem in problems:
        text = str(problem)
        named = [name for name in outcomes if name in text]
        if (named and _SAYS_IT_FAILS.search(text)
                and all(outcomes[name] == "passed" for name in named)):
            continue
        kept.append(problem)
    return kept

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


#: The fewest failing tests that make one identical message a measurement of the suite rather than a coincidence.
FEWEST_IDENTICAL_FAILURES = 5
#: A message shorter than this says too little to be found in a file and mean anything.
_FEWEST_WORDS_IN_THE_MESSAGE = 3
#: Larger files in the product are not read for the message.
_MOST_PRODUCT_FILE_BYTES = 512_000
#: What a run leaves in the project rather than what the product is made of: a report quotes every failure.
_LEFT_BY_A_RUN = frozenset({".xml", ".log", ".html"})
#: A failure's own line, as runners print it: `RuntimeError: ...`, `Error: ...`, with a place or a marker before it.
_AN_ERROR_LINE = re.compile(r"^(?:E\s+)?(?:[^\s:]+:\d+(?::\d+)?:?\s+)?(?P<kind>[\w.$]*(?:Error|Exception)\w*)(?: \[\w+\])?:\s*(?P<said>.+)$")
#: A message about what the product did or did not do: its reply, its connection, its time, or something that failed.
#: A setup helper's message about the product is the product's fault in the suite's words. What is left says of the
#: suite's own state that something was never set.
_SPEAKS_OF_THE_PRODUCT = re.compile(
    r"\b(?:answer\w*|respon[ds]\w*|repl(?:y|ies|ied)|status|unreachable|reach\w*|time[sd]?[ -]?out|in time|within|wait\w*|"
    r"ready|connect\w*|refused|reset|unavailable|health\w*|fail\w*|could not|cannot|can't|unable|crash\w*|exit\w*|died|"
    r"stopped|errors?|invalid|rejected|denied|unauthori[sz]ed|forbidden)\b", re.I)
#: A line that raises, in the languages' own words; an assertion's message is the test checking, and is not here.
_RAISES = re.compile(r"\b(?:raise|throw|panic!?|bail!?|\w*Fatal\w*)\b|\w*(?:Error|Exception)\s*\(")
_AN_ASSERTION = re.compile(r"\b(?:assert\w*|expect\w*|\w*\.fail|fail)\s*\(|\bassert\b")
#: Reading what the product answered, on or just above the line that raises.
_READS_A_REPLY = re.compile(r"\b(?:status\w*|response|resp|res|reply|answer|fetch\w*|urlopen|ok|json)\b", re.I)
_ONLY_COMMENTARY = re.compile(r"""^\s*(?:#|//|/\*|\*|["'`])""")


def _what_it_says(message: str) -> str:
    """The words a failure says, without its kind or what the harness added; "" for an assertion's."""
    said = str(message or "").split(_PAGE_MARK, 1)[0].split(_SERVICE_ERRORS_MARK, 1)[0]
    lines = [line.strip() for line in said.splitlines() if line.strip()]
    for line in lines:
        found = _AN_ERROR_LINE.match(line)
        if found:
            return "" if found.group("kind").lower().startswith("assert") else found.group("said").strip()
    return lines[0] if lines else ""


def _the_suite_file_that_raises(repo_root: str | Path, said: str) -> tuple[str, int] | None:
    """The suite's file and line raising exactly `said`, a whole literal, before reading any reply; None when none does."""
    root = Path(repo_root)
    for path in suite_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace").replace("\\'", "'").replace('\\"', '"')
        except OSError:
            continue
        lines = text.splitlines()
        for at, line in enumerate(lines):
            start = line.find(said)
            if start < 1 or line[start - 1] not in "'\"`" or line[start + len(said):start + len(said) + 1] not in ("'", '"', "`"):
                continue
            kept = [item for item in lines[max(0, at - 3):at] if item.strip() and not _ONLY_COMMENTARY.match(item)]
            raising = _RAISES.search(line) or (kept and _RAISES.search(kept[-1]))
            near = " ".join([*kept[-2:], line.replace(said, "")])
            if raising and not _AN_ASSERTION.search(near) and not _READS_A_REPLY.search(near):
                return path.relative_to(root).as_posix(), at + 1
    return None


#: How many lines bringing in a helper a finding quotes; the rest are counted.
_MOST_LINES_BRINGING_IN_A_HELPER = 8


def _the_lines_that_bring_in(repo_root: str | Path, helper: str) -> list[str]:
    """Each line of the suite's other files naming the helper's file, as `path:line: text`. Never raises.

    By the file's name, in whatever words a language brings a file in with, so nothing here knows a language. The
    name alone over-reads a line that merely mentions it, which a reader can see in the line quoted.
    """
    root = Path(repo_root)
    names_it = re.compile(rf"(?<![\w-]){re.escape(Path(helper).stem)}(?![\w-])")
    found: list[str] = []
    for path in suite_files(repo_root):
        relative = path.relative_to(root).as_posix()
        if relative == helper:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        found += [f"{relative}:{at}: {line.strip()[:120]}" for at, line in enumerate(lines, start=1)
                  if names_it.search(line) and not _ONLY_COMMENTARY.match(line)]
    return found


def _how_the_helper_is_brought_in(repo_root: str | Path, helper: str) -> str:
    """The sentence quoting the lines that bring the helper in, or saying that none does."""
    lines = _the_lines_that_bring_in(repo_root, helper)
    if not lines:
        return f" No other file of the suite names `{Path(helper).name}`."
    shown = "; ".join(f"`{line}`" for line in lines[:_MOST_LINES_BRINGING_IN_A_HELPER])
    more = len(lines) - _MOST_LINES_BRINGING_IN_A_HELPER
    return f" The suite's other files name it at: {shown}" + (f"; and {more} more." if more > 0 else ".")


def _the_product_says(repo_root: str | Path, said: str) -> bool:
    """Whether `said` is written in the project outside its suite and what a run leaves there."""
    where = location(repo_root)
    project = Path(repo_root) / (where[0] if where else "")
    the_suite = {path.resolve() for path in suite_files(repo_root)}
    report = _the_report(repo_root)
    for relative in _the_product_s_files(project):
        path = project / relative
        if (path.resolve() in the_suite or path == report or path.suffix.lower() in _LEFT_BY_A_RUN
                or set(Path(relative).parts) & _NOT_THE_SUITE):
            continue
        try:
            if path.stat().st_size <= _MOST_PRODUCT_FILE_BYTES and said in path.read_text(encoding="utf-8", errors="replace"):
                return True
        except OSError:
            continue
    return False


def _one_message_of_the_suite_s_own(repo_root: str | Path, messages: Sequence[str], passed: int, problem: str) -> tuple[str, str]:
    """(the one message, the suite's file raising it) when no test passed and all failed with it; ("", "") otherwise."""
    if passed or problem or len(messages) < FEWEST_IDENTICAL_FAILURES:
        return "", ""
    if any(_SERVICE_ERRORS_MARK in message for message in messages):
        return "", ""  # the product was reached: it logged an error while a test ran
    said = {_what_it_says(message) for message in messages}
    only = next(iter(said)) if len(said) == 1 else ""
    if (len(only.split()) < _FEWEST_WORDS_IN_THE_MESSAGE or _NEVER_STARTED.search(only) or _THE_SERVICE_WAS_GONE.search(only)
            or _SPEAKS_OF_THE_PRODUCT.search(only)):
        return "", ""
    helper = _the_suite_file_that_raises(repo_root, only)
    if not helper or _the_product_says(repo_root, only):
        return "", ""
    return only, helper


def a_message_of_the_suite_s_own(repo_root: str | Path, result: Any) -> bool:
    """Whether this run has the shape `the_suite_failed_in_its_own_words` needs the start's evidence for. Never raises."""
    try:
        tests = list(getattr(getattr(result, "report", None), "tests", None) or ())
        return bool(_one_message_of_the_suite_s_own(
            repo_root, [str(t.message or "") for t in tests if t.outcome == "failed"],
            sum(t.outcome == "passed" for t in tests), str(getattr(result, "problem", "") or ""))[0])
    except Exception:  # noqa: BLE001 - no finding, as before
        logger.debug("Could not read the failures for a message of the suite's own", exc_info=True)
        return False


def _the_finding(repo_root: str | Path, messages: Sequence[str], passed: int, problem: str, server_log: str, runtime: Sequence[Any]) -> list[str]:
    """The one finding of `the_suite_failed_in_its_own_words`, from what either form of a measurement holds."""
    from app.acceptance import start_output

    said, raised_at = _one_message_of_the_suite_s_own(repo_root, messages, passed, problem)
    if not said or runtime:
        return []
    helper, line = raised_at
    # The product's own start ran on, and it logged no error of its own during the suite: a product that cannot start,
    # or that answered with errors, is the product's, however the suite words it.
    started = start_output.in_text(server_log)
    if start_output.STILL_RUNNING not in started or str(server_log).replace(started, "").strip():
        return []
    return [
        f"`{helper}` at line {line} raises the one message all {len(messages)} failing tests failed with: \"{said}\". "
        f"{_how_the_helper_is_brought_in(repo_root, helper).strip()} No test passed, "
        "those words are written in the suite's own files and nowhere in the product, and the product kept running when "
        "the harness started it with its own start command. So no test reached the product, and what the tests assert "
        "has not been tried. Look at how the suite's helpers are loaded and shared between its files: a test may be "
        "reading a separate copy of a helper, or state its setup never gave it. Fix that without changing what any test "
        "asserts."
    ]


def the_suite_failed_in_its_own_words(repo_root: str | Path, result: Any) -> list[str]:
    """The finding when every failing test failed in one message of the suite's own and none reached the product; [].

    Measured on one run: all 46 locked tests failed with one sentence raised by a helper of the suite, from a second
    copy of its module with empty state. The review locked it, a dispute judged only what the tests assert, and fixers
    who may not edit the suite spent over 45 minutes. All of these must hold, so that a product at fault stays the
    product's: enough failures, no pass, one message that is a whole literal raised (not asserted) in the suite before
    any reply is read, absent from the product, not speaking of an answer, a connection, a wait or a failure; no error
    logged by the service; and the harness's own start of the product (`start_output`) still running at its limit.

    Not before a first lock: nothing is built, and a right suite's own setup says the same of a product that is not
    there. Never raises.
    """
    try:
        tests = list(getattr(getattr(result, "report", None), "tests", None) or ())
        return _the_finding(
            repo_root, [str(t.message or "") for t in tests if t.outcome == "failed"],
            sum(t.outcome == "passed" for t in tests), str(getattr(result, "problem", "") or ""),
            str(getattr(result, "server_log", "") or ""), list(getattr(result, "runtime_problems", None) or ()))
    except Exception:  # noqa: BLE001 - no finding, as before
        logger.debug("Could not weigh the suite's own message", exc_info=True)
        return []


def the_suite_s_own_words_when_last_measured(repo_root: str | Path) -> list[str]:
    """`the_suite_failed_in_its_own_words` for the saved measurement, for those who hold no result. Never raises."""
    try:
        saved = last_result(repo_root) or {}
        tests = {str(test.get("name")): test
                 for key in ("criteria", "change_requests") for criterion in (saved.get(key) or {}).values()
                 for test in criterion.get("tests") or []}
        return _the_finding(
            repo_root, [str(test.get("message") or "") for test in tests.values() if test.get("outcome") == "failed"],
            int(saved.get("passed") or 0), str(saved.get("problem") or ""), str(saved.get("server_log") or ""),
            list(saved.get("runtime_problems") or ()))
    except Exception:  # noqa: BLE001 - no finding, as before
        logger.debug("Could not read the saved measurement for the suite's own message", exc_info=True)
        return []


def _longer_names(name: str, names: Sequence[str]) -> list[str]:
    """The other names that hold `name`: a label lookup that is not exact matches those too."""
    return [other for other in names if other != name and name.lower() in other.lower()]


def tests_whose_label_also_matches_a_longer_name(repo_root: str | Path, result: Any) -> list[str]:
    """Failed tests whose label lookup matched two controls because one criterion's name holds another's. Never raises.

    Measured on one run: a test asked for the label "Tag" and the page rightly also had "Filter by tag". A lookup that
    is not exact matches both and refuses, so no right page could pass, and a fixer spent its budget on the page.
    """
    try:
        from app.analysis.interface_checks import controls_the_brief_names

        criteria = json.loads((Path(repo_root) / ".harness" / "acceptance.json").read_text(encoding="utf-8"))["criteria"]
        names = controls_the_brief_names("\n".join(str(c.get("text") or "") for c in criteria))
        problems = []
        for test in getattr(getattr(result, "report", None), "tests", None) or ():
            if test.outcome != "failed":
                continue
            for name in _NOT_EXACT_LABEL.findall(str(test.message or "")):
                longer = _longer_names(name, names)
                if longer:
                    problems.append(
                        f"`{test.name}` asks for the label \"{name}\" without `exact: true`, which also matches "
                        + ", ".join(f'"{other}"' for other in longer)
                        + ", so no product the brief describes can pass it. Find it with `{ exact: true }`. "
                        "This is about the test, not the product."
                    )
        return list(dict.fromkeys(problems))[:6]
    except Exception:  # noqa: BLE001 - no criteria, nothing to say
        return []


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
    from app.acceptance import ids_read_without_a_create, spec_dry_run

    # These have measured what they say: the spec was run with the product stood in for, or a failure of this run is
    # part of the finding. `findings_that_reopen` leaves them alone.
    # Which check raised each finding, so the review records it under its own name (HR2.Q.1: 36 checks were one
    # bucket in `.harness/check-findings.jsonl`).
    checks: dict[str, str] = {}
    measured = [
        *_by(checks, "spec_dry_run", spec_dry_run.findings(repo_root)),
        *_by(checks, "tests_that_broke_themselves", tests_that_broke_themselves(repo_root, result)),
        *_by(checks, "tests_broken_by_their_own_setup", tests_broken_by_their_own_setup(repo_root, result)),
        *_by(checks, "tests_that_need_what_they_never_made", tests_that_need_what_they_never_made(repo_root, result)),
        *_by(checks, "tests_that_assert_a_kept_file_s_text", tests_that_assert_a_kept_file_s_text(repo_root, result)),
        *_by(checks, "tests_that_count_a_list_other_tests_write_to", tests_that_count_a_list_other_tests_write_to(repo_root, result)),
        *_by(checks, "page_tests_that_count_a_shared_list", page_tests_that_count_a_shared_list(repo_root, result)),
        *_by(checks, "python_tests_that_count_a_list_other_tests_write_to", python_tests_that_count_a_list_other_tests_write_to(repo_root, result)),
        *_by(checks, "tests_that_count_every_row_of_a_shared_table", tests_that_count_every_row_of_a_shared_table(repo_root, result)),
        *_by(checks, "the_suite_failed_in_its_own_words", the_suite_failed_in_its_own_words(repo_root, result)),
        *_by(checks, "tests_whose_label_also_matches_a_longer_name", tests_whose_label_also_matches_a_longer_name(repo_root, result)),
    ]
    # These read a test's text, and text is a guess at what it does.
    read_from_text = [
        *_by(checks, "ids_read_without_a_create", ids_read_without_a_create.findings(repo_root)),
        *_by(checks, "assertions_that_do_not_exist", assertions_that_do_not_exist(repo_root)),
        *_by(checks, "locators_that_do_not_exist", locators_that_do_not_exist(repo_root)),
        *_by(checks, "locators_by_a_name_the_role_never_has", locators_by_a_name_the_role_never_has(repo_root)),
        *_by(checks, "locators_with_invalid_name_option", locators_with_invalid_name_option(repo_root)),
        *_by(checks, "locators_matching_a_pattern_as_text", locators_matching_a_pattern_as_text(repo_root)),
        *_by(checks, "whole_page_lookups_of_a_per_record_control", whole_page_lookups_of_a_per_record_control(repo_root)),
        *_by(checks, "page_assertions_without_await", page_assertions_without_await(repo_root)),
        *_by(checks, "requests_with_a_fetch_body", requests_with_a_fetch_body(repo_root)),
        *_by(checks, "responses_read_without_the_call", responses_read_without_the_call(repo_root)),
        *_by(checks, "contexts_made_from_the_fixture", contexts_made_from_the_fixture(repo_root)),
        *_by(checks, "fetch_calls_written_like_the_fixture", fetch_calls_written_like_the_fixture(repo_root)),
        *_by(checks, "reads_of_what_the_test_does_not_have", reads_of_what_the_test_does_not_have(repo_root)),
        *_by(checks, "tests_that_want_json_from_a_204", tests_that_want_json_from_a_204(repo_root)),
        *_by(checks, "tests_that_filter_for_what_they_never_made", tests_that_filter_for_what_they_never_made(repo_root)),
        *_by(checks, "tests_whose_success_status_the_contract_does_not_give", tests_whose_success_status_the_contract_does_not_give(repo_root)),
        *_by(checks, "tests_that_restart_on_data_they_never_wrote", tests_that_restart_on_data_they_never_wrote(repo_root)),
        *_by(checks, "tests_that_sign_in_as_nobody", tests_that_sign_in_as_nobody(repo_root)),
        *_by(checks, "tests_that_never_open_the_page", tests_that_never_open_the_page(repo_root)),
        *_by(checks, "tests_that_access_storage_before_opening_the_page", tests_that_access_storage_before_opening_the_page(repo_root)),
        *_by(checks, "tests_that_expect_what_they_never_gave", tests_that_expect_what_they_never_gave(repo_root)),
        *_by(checks, "tests_that_assert_an_unstated_order", tests_that_assert_an_unstated_order(repo_root)),
        *_by(checks, "locators_that_contradict_their_assertions", locators_that_contradict_their_assertions(repo_root)),
        *_by(checks, "tests_with_module_system_mismatch", tests_with_module_system_mismatch(repo_root)),
        *_by(checks, "tests_with_unawaited_async_helpers", tests_with_unawaited_async_helpers(repo_root)),
    ]
    return _CannotPass([*measured, *read_from_text], read_from_text, checks)


class _CannotPass(list):
    """The one list every caller reads, knowing which of its findings were only read from a test's text."""

    def __init__(self, found: Sequence[str], read_from_text: Sequence[str], checks: dict | None = None) -> None:
        super().__init__(found)
        self.read_from_text = list(read_from_text)
        #: Each finding's text -> the name of the check that raised it.
        self.checks = dict(checks or {})


def _by(checks: dict, name: str, findings: Sequence[str]) -> list[str]:
    """`findings`, each remembered in `checks` as raised by `name`."""
    found = list(findings or [])
    for text in found:
        checks.setdefault(str(text), name)
    return found


#: A line a finding points at: `line 12`, `line(s) 12, 14`.
_LINES_NAMED = re.compile(r"\bline(?:\(s\))?\s+(\d+(?:,\s*\d+)*)")
#: Where a generated title's fixed part ends: `${...}`.
_A_TITLE_S_VARIABLE = "${"
#: Where a kept note is written; the harness's own folder, read at release.
NOTES_FILE = f"{contract.HARNESS_DIR}/suite-notes.json"
#: How a note opens.
NOT_ACTED_ON = "Read in a locked test's text and not acted on, because the test named does not fail in the last measurement"


def _the_tests_at(repo_root: str | Path, finding: str) -> list[str]:
    """The titles of the tests a finding points at, by the file and lines it names, or by its own `name`; [] for none."""
    root = Path(repo_root)
    quoted = re.findall(r"`([^`]+)`", str(finding))
    if not quoted:
        return []
    path = root / quoted[0] if (root / quoted[0]).is_file() else None
    if path is None:
        # A file named from elsewhere than the workspace, or not a file at all: then it is the test's own title.
        files = [item for item in suite_files(repo_root) if item.as_posix().endswith("/" + quoted[0].removeprefix("./"))]
        if not files:
            return [] if re.search(r"\.\w{1,5}$", quoted[0]) else [quoted[0].strip()]
        path = files[0]
    text = path.read_text(encoding="utf-8", errors="replace")
    python = path.suffix.lower() == ".py"
    starts = [(match.start(), match.group(1 if python else 2).strip())
              for match in (_A_PYTHON_TEST if python else _A_TEST_STARTS).finditer(text)]
    lengths = [text.count("\n", 0, at) + 1 for at, _ in starts]
    titles: list[str] = []
    for group in _LINES_NAMED.findall(str(finding)):
        for line in (int(number) for number in group.split(",")):
            before = [index for index, first in enumerate(lengths) if first <= line]
            if before and starts[before[-1]][1] not in titles:
                titles.append(starts[before[-1]][1])
    return titles


def _fails(title: str, failing: Sequence[str]) -> bool:
    fixed = title.split(_A_TITLE_S_VARIABLE, 1)[0].strip()
    return bool(fixed) and any(fixed in name for name in failing)


def findings_that_reopen(repo_root: str | Path, result: Any, found: Sequence[str]) -> list[str]:
    """Of `found`, those that may send a suite already locked back to QA; the others are kept as notes. Never raises.

    Before a first lock, everything goes to QA as it always did: nothing has measured the tests yet. After it, a
    finding read from a test's text reopens the suite only when the test it names fails in the last measurement. A
    locked test that passes on the product is the answer to what its text was suspected of: text patterns raised five
    false findings in two days, each reopening a right suite for 10 to 60 minutes. A finding that names no test, and
    one a check measured, are not judged here and act as before. So does everything when the suite gave no results at
    all (a broken test file can be why); but a product that did not start has measured nothing about any test, and a
    finding waits for a measurement that has.
    """
    try:
        reading = getattr(found, "read_from_text", None)
        if reading is None or not is_locked(repo_root):
            return list(found)
        report = getattr(result, "report", None)
        tests = list(getattr(report, "tests", None) or ())
        nothing_measured = str(getattr(result, "problem", "") or "").startswith(PRODUCT_DID_NOT_START)
        if not tests and not nothing_measured:
            return list(found)
        failing = [] if nothing_measured else [str(t.name) for t in tests if t.outcome == "failed"]
        kept: list[str] = []
        notes: list[str] = []
        for finding in found:
            titles = _the_tests_at(repo_root, finding) if finding in reading else []
            if not titles or any(_fails(title, failing) for title in titles):
                kept.append(finding)
            else:
                notes.append(f"{NOT_ACTED_ON}: {finding}")
        if notes:
            logger.warning("%d finding(s) read in the locked tests' text left as notes: the tests they name do not fail", len(notes))
            _keep_notes(repo_root, notes)
        return kept
    except Exception:  # noqa: BLE001 - as before: every finding acts
        logger.debug("Could not weigh the findings against the measurement", exc_info=True)
        return list(found)


def _keep_notes(repo_root: str | Path, notes: Sequence[str]) -> None:
    path = Path(repo_root) / NOTES_FILE
    merged = list(dict.fromkeys([*notes_kept(repo_root), *notes]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged), encoding="utf-8")


def notes_kept(repo_root: str | Path) -> list[str]:
    """The findings `findings_that_reopen` left as notes in this run; never a release gap."""
    try:
        data = json.loads((Path(repo_root) / NOTES_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [str(item) for item in data] if isinstance(data, list) else []
