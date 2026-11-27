"""Continuous integration for a run's workspace: what passes now, and what used to.

A software company does not merge a change that breaks what already worked,
and does not keep a fix that makes the product worse. The harness does the
same, mechanically, with the pack's own commands:

- a **snapshot** runs the unit and acceptance suites and records, per test,
  whether it passed;
- a **regression** is a test that passed in the last snapshot and does not now;
- a **fix that regresses** is put back exactly as it was before the fix -
  `git reset` to the commit taken just before it - and its defect stays open
  with the reason.

Snapshots live in `.harness/ci.json` (hidden from agents, kept out of git).
Every function degrades rather than raises: a run with no pack has no unit
snapshot, a run with no suite no acceptance one, and both simply compare less.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from app.acceptance import junit, suite
from app.stacks import contract

logger = logging.getLogger(__name__)

CI_FILE = f"{contract.HARNESS_DIR}/ci.json"

Runner = Callable[[Sequence[str], str, str], dict[str, Any]]


@dataclass
class Snapshot:
    label: str
    commit: str = ""
    #: test name -> "passed" | "failed" | "skipped", per suite.
    unit: dict[str, str] = field(default_factory=dict)
    acceptance: dict[str, str] = field(default_factory=dict)
    unit_ran: bool = False
    acceptance_ran: bool = False
    #: Why the acceptance suite reached no test, when it reached none: the
    #: product did not build or start (`suite.the_product_did_not_start`).
    problem: str = ""
    #: Why the harness could not measure the product at all (its own refusal, a registry it could not resolve);
    #: "" when it measured. Such a snapshot judges no fix and replaces no baseline (A1, `unmeasured`).
    unmeasured: str = ""

    def passing(self) -> set[str]:
        return {
            f"{kind}: {name}"
            for kind, tests in (("unit", self.unit), ("acceptance", self.acceptance))
            for name, outcome in tests.items()
            if outcome == "passed"
        }

    def as_dict(self) -> dict[str, Any]:
        return vars(self).copy()


def _git(root: str | Path, *args: str) -> subprocess.CompletedProcess | None:
    from app.tools.version_control import _git as run_git

    return run_git(Path(root), *args)


def head(root: str | Path) -> str:
    result = _git(root, "rev-parse", "HEAD")
    return result.stdout.strip() if result is not None and result.returncode == 0 else ""


def _the_tree_is_clean(root: str | Path) -> bool:
    """Whether git records nothing changed and nothing untracked (ignored files aside)."""
    status = _git(root, "status", "--porcelain")
    return status is not None and status.returncode == 0 and not status.stdout.strip()


def commit(root: str | Path, message: str) -> str:
    """Commit everything as it stands; the commit HEAD now names (new or not), or "" when the work is not committed.

    Found in the launch review (LR.51): a commit that failed (an `index.lock`, a git that timed out) returned the old
    HEAD as if the work were in it, and a later reset to that commit discarded the work. Now the tree is checked: work
    left uncommitted answers "", which every caller treats as "no commit to go back to".
    """
    from app.tools.version_control import commit_all

    commit_all(root, message)
    # Tracked and staged changes against HEAD only: a failed commit leaves its staged work there, while a file another
    # thread writes after the add (parallel fixers) is untracked and is not this commit's.
    staged = _git(root, "diff", "--quiet", "HEAD")
    if staged is None or staged.returncode != 0:
        logger.warning("The workspace could not be committed (%s); its changes stay uncommitted", message[:60])
        return ""
    return head(root)


#: Between where a test lives and its name in a snapshot's key.
WHERE = " \u203a "

#: Which of two outcomes for one key is kept: the worse.
_RANK = {"passed": 0, "skipped": 1, "failed": 2}


#: A value a test's name carries that differs on every run: a uuid or a run of eight or more hex digits, as a
#: parametrized test gets from `uuid4().hex[:8]` in its id. Such a name never matches the one measured before.
_VOLATILE = re.compile(
    r"(?<![0-9A-Za-z])(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{8,})(?![0-9A-Za-z])"
)


def stable(key: str) -> str:
    """`key` with its per-run values replaced, so the same test has the same key on every run.

    Measured on a small-model run: an acceptance test was parametrized on a random user name
    (`test_ac1_signup[user_02dc5292-password123]`), so each measurement named it differently; every fix then
    "broke" the test that passed before it, and seven fixes - one of which had made three tests pass - were
    reverted for it.
    """
    return _VOLATILE.sub("~", key)


def outcomes_of(tests: Sequence[Any]) -> dict[str, str]:
    """Each test's outcome, keyed by where it lives and its name.

    Where a test lives is its file, or else the suites around it and its
    class: Node's reporter writes no file and the class "test" for every
    test, and only the `describe` block it sits in tells two apart.

    By name alone, two tests of the same name - "does not mutate the original
    array", written once per function - were one entry, and the second's
    outcome overwrote the first's. One run's 37 unit tests were recorded as 29,
    its sprint summaries counted 42 tests where there were 50, and a failing
    test could hide behind a passing one of the same name, which is the one
    thing a regression check must never allow. Where two still share a key the
    worse outcome is kept.
    """
    found: dict[str, str] = {}
    for test in tests or ():
        where = (getattr(test, "file", "") or "").strip() or WHERE.join(
            part for part in (
                (getattr(test, "within", "") or "").strip(), (getattr(test, "suite", "") or "").strip()
            ) if part
        )
        key = stable(f"{where}{WHERE}{test.name}" if where else test.name)
        outcome = str(getattr(test, "outcome", "") or "failed")
        kept = found.get(key)
        if kept is None or _RANK.get(outcome, 2) > _RANK.get(kept, 2):
            found[key] = outcome
    return found


def _bare(key: str) -> str:
    """The test's own name: the last part of a key, whatever came before it."""
    return key.rsplit(WHERE, 1)[-1] if WHERE in key else key


def _outcome_now(now: dict[str, str], key: str) -> str | None:
    """The outcome `key` has in `now`, by its full key or - for a snapshot taken
    before keys carried where a test lives - by name, passing only if every test
    of that name passes."""
    if key in now:
        return now[key]
    key = stable(key)  # a snapshot taken before keys were made stable
    if key in now:
        return now[key]
    name = _bare(key)
    same = [outcome for other, outcome in now.items() if _bare(other) == name]
    if not same:
        return None
    return "passed" if all(outcome == "passed" for outcome in same) else "failed"


#: Where the harness keeps its last unit run with the product's fingerprint (MEASURE_ONCE). The test round's unit run
#: (`workflow._run_unit_tests_procedurally`) and every snapshot here write and read the same record.
UNIT_RUN_FILE = f"{contract.HARNESS_DIR}/unit-result.json"


def the_unit_run_kept(root: str | Path, command: Sequence[Any]) -> dict[str, Any] | None:
    """The last unit run's record when the product and the command are as they were then; else None. Never raises.

    The record holds `passed` and `output`, and `unit` (each test's outcome) with `found` when the pack's report
    was read after the run.
    """
    try:
        from app.acceptance import measured_once
        from app.acceptance.unstable import fingerprint

        if not measured_once.enabled():
            return None
        saved = json.loads((Path(root) / UNIT_RUN_FILE).read_text(encoding="utf-8"))
        if not isinstance(saved, dict) or saved.get("command") != [str(part) for part in command]:
            return None
        if saved.get("fingerprint") != fingerprint(root):
            return None
        return saved
    except Exception:  # noqa: BLE001 - when in doubt, run them
        return None


def keep_the_unit_run(
    root: str | Path, command: Sequence[Any], passed: bool, output: str,
    unit: dict[str, str] | None = None, found: bool = False,
) -> None:
    """Keep this unit run with the product's fingerprint, for `the_unit_run_kept`. Never raises."""
    try:
        from app.acceptance import measured_once
        from app.acceptance.unstable import fingerprint

        if not measured_once.enabled():
            return
        record: dict[str, Any] = {"command": [str(part) for part in command], "fingerprint": fingerprint(root),
                                  "passed": bool(passed), "output": str(output or "")[-20_000:]}
        if unit is not None:
            record.update(unit=dict(unit), found=bool(found))
        target = Path(root) / UNIT_RUN_FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(record), encoding="utf-8")
    except Exception:  # noqa: BLE001 - the next run measures again
        pass


#: How the failures of one unit run, grouped by what they say, begin; `the_distinct_causes` reads them back.
DISTINCT_CAUSES = "Distinct causes, most failing first:"
#: Characters of one failure's message shown.
MOST_MESSAGE = 600
#: A line of a failure that states the error: `SomeError: ...`, an assertion, what was expected and what came instead.
#: What came is kept too (LF.1316): a long node:assert message was cut to "expected: 1," and its "6 !== 1" and
#: "actual: 6," were left out, so the fixer of tests that shared one store never saw the count grow.
_STATES_THE_ERROR = re.compile(r"\b\w*(?:Error|Exception)\b|\bassert(?:ion)?\b|\bexpected\b|\bactual\b|\breceived\b"
                               r"|\bbut was\b|!==", re.I)
#: A line that only says where, or what the runner shows of the source: a frame, an argument's value, a source line.
_ONLY_SAYS_WHERE = re.compile(r'^(?:File "|at\s|\S+:\d+: in\b|>|self\s*=|\w+\s*=\s|_{5,}|\^+$|def\s)')


def _its_error_lines(message: str) -> list[str]:
    """The lines of a failure's message that state its error, in order; [] when none does.

    pytest marks them itself (`E   TypeError: ...`); other runners' messages are read for a stated error. Measured on
    one run: the report's message opened with the frame (`self = <...>`, `data_dir = '/tmp/...'`) and the first 600
    characters of twenty failures never reached the error, so the fixer was told twenty frames and no cause.
    """
    lines = [" ".join(line.split()) for line in str(message or "").splitlines()]
    marked = [line[2:] for line in lines if line.startswith("E ") and line[2:].strip()]
    if marked:
        return list(dict.fromkeys(marked))
    return list(dict.fromkeys(line for line in lines
                              if line and _STATES_THE_ERROR.search(line) and not _ONLY_SAYS_WHERE.match(line)))


def _what_it_says(message: str) -> str:
    """A failure's message as shown: whole when short, else its error lines; its start when none states one."""
    text = str(message or "").strip()
    if len(text) <= MOST_MESSAGE:
        return text
    stated = _its_error_lines(text)
    return ("\n  ".join(stated) if stated else text)[:MOST_MESSAGE]


#: A line that gives one of the values an assertion compared, after the assertion's own line (LF.1451): `Expected:`,
#: `Received:`, `Actual:`, Rust's `left:` / `right:`, `got` / `want`.
_A_COMPARED_VALUE = re.compile(r"^(?:expected|received|actual|left|right|got|want)\b(?:\s+\w+)?\s*:", re.I)
#: What a runner prints around a test that says nothing of why it failed: a bare `Failed`, `=== RUN` and `--- FAIL`
#: framing lines.
_SAYS_ONLY_THAT_IT_FAILED = re.compile(r"^(?:failed\.?|={3}\s|-{3}\s)", re.I)


def _its_cause(message: str, name: str = "") -> str:
    """The text a failure's cause is grouped by: its first stated error with the values it compared, else its first
    line that says more than that it failed or what the test is called.

    The first stated error alone grouped unlike failures (LF.1451): in several runners it is the assertion's generic
    header (`assertion \\`left == right\\` failed`, `Assert.Equal() Failure: Values differ`, a bare `Failed`), so a 500
    where a 422 was wanted and an empty list where two notes were were one cause, and every Go failure was `Failed`.
    """
    lines = [" ".join(line.split()) for line in str(message or "").splitlines()]
    stated = _its_error_lines(message)
    own = " ".join(str(name or "").split())
    first = stated[0] if stated else next(
        (line for line in lines if line and not _SAYS_ONLY_THAT_IT_FAILED.match(line) and line != own), "")
    if not first:
        first = next((line for line in lines if line), "")
    values: list[str] = []
    if first in lines:
        for line in lines[lines.index(first) + 1:]:
            if not _A_COMPARED_VALUE.match(line):
                break
            values.append(line)
    return "; ".join([first, *values[:3]])[:200]


def what_the_failing_unit_tests_say(tests: Sequence[Any]) -> str:
    """The failing tests of a runner's report, each with its message, then grouped by cause; "" when none failed.

    Grouped because one cause fails many tests: measured on one run, eighteen tests failed on a table their fixture
    never made and two on a call the test client does not offer; the fixer was shown the first and fixed neither.
    """
    failed = [test for test in tests or () if getattr(test, "outcome", "") == "failed"]
    if not failed:
        return ""
    listed = "Failing tests, from the runner's report:\n" + "\n".join(
        f"- {test.within + ' › ' if test.within else ''}{test.name}"
        f"{' (' + test.file + ')' if test.file else ''}: {_what_it_says(test.message)}"
        for test in failed[:12]
    ) + (f"\n... and {len(failed) - 12} more" if len(failed) > 12 else "")
    groups: dict[str, list[Any]] = {}
    for test in failed:
        groups.setdefault(_its_cause(test.message, getattr(test, "name", "")), []).append(test)
    if len(failed) < 2:
        return listed
    lines = []
    for cause, members in sorted(groups.items(), key=lambda item: -len(item[1]))[:6]:
        named = ", ".join(f"`{(m.within + ' › ') if m.within else ''}{m.name}`" for m in members[:2])
        lines.append(f"- {len(members)} failing, e.g. {named}: {cause or '(no message)'}")
    return listed + "\n" + DISTINCT_CAUSES + "\n" + "\n".join(lines)


def the_distinct_causes(output: str) -> str:
    """The grouped causes `what_the_failing_unit_tests_say` wrote into a run's output; "" when it wrote none."""
    _, found, after = str(output or "").rpartition(DISTINCT_CAUSES)
    if not found:
        return ""
    lines = []
    for line in after.splitlines()[1:]:
        if not line.startswith("- "):
            break
        lines.append(line)
    return (DISTINCT_CAUSES + "\n" + "\n".join(lines)) if lines else ""


def unit_outcomes_in_the_pack_s_report(root: str | Path) -> tuple[dict[str, str], bool] | None:
    """Each unit test's outcome in the pack's unit report as it is on disk, and whether one was found; None without a pack."""
    found = contract.the_pack(root)
    if found is None:
        return None
    pack, record = found
    parsed = junit.read(Path(root) / str(record.get("project") or "") / pack.unit_report)
    return outcomes_of(parsed.tests), parsed.found


#: The one name a unit run that failed without writing its report is recorded under.
UNIT_TESTS_DID_NOT_RUN = "the project's unit tests did not compile or start (their runner failed and wrote no report)"
#: The one name a unit run ended at the sandbox's time limit, its report unwritten, is recorded under (LF.1642).
UNIT_TESTS_DID_NOT_FINISH = "the project's unit tests did not finish (their run was ended at its time limit)"
#: Both names a unit run that reported no test of its own is recorded under.
UNIT_RUNS_WITHOUT_A_REPORT = (UNIT_TESTS_DID_NOT_RUN, UNIT_TESTS_DID_NOT_FINISH)


def unit_outcomes_of_a_run(unit: dict[str, str] | None, found: bool, failed_with_a_code: bool,
                           timed_out: bool = False) -> dict[str, str] | None:
    """The outcomes a unit run is recorded with: `unit` as its report read, or `UNIT_TESTS_DID_NOT_RUN` failed when the
    runner ran, failed with an exit code of its own and wrote no report - the tests did not compile or could not start
    - or `UNIT_TESTS_DID_NOT_FINISH` failed when the run was ended at its time limit before writing one.

    One rule for every path that runs the unit tests (LF.1619). Measured on a C# run: the test round's own run kept a
    build that failed as no outcomes at all, every snapshot after it read that, and three fixes whose test file did not
    compile were each reverted as "broke 17 tests", the compiler's words nowhere. Measured on a service run (LF.1642):
    four unit runs ended at the 300-second limit were kept as no outcomes, which `unit_failures` read as none failing.
    """
    if not found and timed_out:
        return {UNIT_TESTS_DID_NOT_FINISH: "failed"}
    if not found and failed_with_a_code:
        return {UNIT_TESTS_DID_NOT_RUN: "failed"}
    return unit


#: Characters of the last unit run's own words a fixer is shown when the unit tests did not run.
MOST_UNIT_RUN_SAID = 1_200


def what_the_unit_run_said(root: str | Path) -> str:
    """What the last unit run kept said when it failed: the compiler's errors in it, one a line, else the end of its
    output; "" when the run kept passed or none is kept. Never raises (LF.1620)."""
    try:
        saved = json.loads((Path(root) / UNIT_RUN_FILE).read_text(encoding="utf-8"))
        if not isinstance(saved, dict) or saved.get("passed"):
            return ""
        output = str(saved.get("output") or "")
        from app.analysis.compiler_check import errors_in

        project = Path(root) / str((contract.read(root) or {}).get("project") or "")
        errors = errors_in(output, project, Path(root))
        if errors:
            return "\n".join(f"`{e['file']}` line {e['line']}: {e['message']}" for e in errors)[:MOST_UNIT_RUN_SAID]
        return output.strip()[-MOST_UNIT_RUN_SAID:]
    except Exception:  # noqa: BLE001 - said nothing
        return ""


def _run_unit(root: str | Path, runner: Runner | None) -> tuple[dict[str, str], bool]:
    """Each unit test's outcome now, and whether the runner's report was found.

    A unit run the harness could not take raises `NotMeasured` with why, and is not kept (A1).

    An unchanged product's last unit run stands (MEASURE_ONCE), whichever of the test round or a snapshot ran it.
    Found in a code review: the test round kept its unit run with the product's fingerprint, and every snapshot
    still ran the unit tests again on the product they had just measured - once more per fix stage.
    """
    found = contract.the_pack(root)
    if found is None:
        return {}, False
    pack, record = found
    project = str(record.get("project") or "")
    command = list(record.get("unit_test") or pack.unit_test)
    if runner is None:
        from app.stacks.scaffold import sandbox_runner

        runner = sandbox_runner(root)
    # An install made now changes what the tests run against, so the kept run no longer stands.
    installed_now = contract.install_if_the_manifests_changed(root, runner)
    kept = None if installed_now else the_unit_run_kept(root, command)
    if kept is not None and isinstance(kept.get("unit"), dict):
        logger.info("The product is as the unit tests last measured it; that run stands")
        return {str(name): str(outcome) for name, outcome in kept["unit"].items()}, bool(kept.get("found"))
    report = Path(root) / project / pack.unit_report
    from app.acceptance import unmeasured

    def measure() -> tuple[dict[str, Any], Any]:
        junit.clear(report)
        answered = runner(command, "test", project) or {}
        return answered, junit.read(report)

    not_installed = unmeasured.in_the_repairs(installed_now)
    outcome, parsed = unmeasured.once_more(
        measure, lambda measured: not_installed or unmeasured.why(measured[0], reached_tests=bool(measured[1].tests)))
    not_taken = not_installed or unmeasured.why(outcome, reached_tests=bool(parsed.tests))
    if not_taken:
        raise NotMeasured(not_taken)
    unit = outcomes_of(parsed.tests)
    from app.stacks.scaffold import _exit_code

    passed = _exit_code(outcome) == 0 if isinstance(outcome, dict) else False
    said = (str(outcome.get("stdout") or "") + str(outcome.get("stderr") or "")) if isinstance(outcome, dict) else ""
    # The runner ran, failed, and wrote no report: the tests did not compile or could not start. Before, that read
    # as none failing, and a release shipped unit tests that did not compile without a word (found on a language
    # sweep). One stable name, so an escalation's acceptance and the release compare it like any test.
    from app.tools.sandbox import held_to_its_time_limit

    unit = unit_outcomes_of_a_run(
        unit, parsed.found, isinstance(outcome, dict) and "returncode" in outcome and not passed,
        timed_out=held_to_its_time_limit(outcome)) or {}
    if isinstance(outcome, dict) and outcome.get("error"):
        # What the sandbox said when the command ended without a code of its own (a run held to its time limit): the
        # test round reads the kept record, and kept without this a unit run that never finished said "(no output)"
        # to three rounds of fixers (measured on a browser-and-service run: a test that blocked its own thread).
        said = (said.rstrip() + "\n" + str(outcome["error"])).strip()
    if not passed:
        # Read as the test round's own run reads, so the record says the same whichever ran it.
        said = (said.rstrip() + "\n" + what_the_failing_unit_tests_say(parsed.tests)).strip()
    keep_the_unit_run(root, command, passed, said, unit, parsed.found)
    return unit, parsed.found


class NotMeasured(Exception):
    """The harness could not run the measurement at all; the message says why (`unmeasured`)."""


def unit_failures(root: str | Path, runner: Runner | None = None) -> list[str]:
    """The project's own unit tests that do not pass now, by name; [] when all pass or none ran."""
    try:
        unit, ran = _run_unit(root, runner)
    except NotMeasured:
        return []
    if not ran:
        return [name for name in UNIT_RUNS_WITHOUT_A_REPORT if unit.get(name) == "failed"]
    return sorted(name for name, outcome in unit.items() if outcome != "passed")


def take(
    root: str | Path,
    label: str,
    *,
    runner: Runner | None = None,
    acceptance: suite.AcceptanceResult | None = None,
) -> Snapshot:
    """Run the unit and acceptance suites now. `acceptance` reuses a run just made."""
    try:
        unit, unit_ran = _run_unit(root, runner)
        unit_not_taken = ""
    except NotMeasured as refused:
        unit, unit_ran, unit_not_taken = {}, False, str(refused)
        from app.acceptance import unmeasured

        unmeasured.record(root, label, unit_not_taken)
    if acceptance is None and suite.is_locked(root):
        acceptance = suite.run(root, runner=runner)
    tests = outcomes_of(acceptance.report.tests) if acceptance is not None else {}
    not_taken = unit_not_taken or str(getattr(acceptance, "unmeasured", "") or "")
    return Snapshot(
        label=label,
        commit=head(root),
        unit=unit,
        acceptance=tests,
        unit_ran=unit_ran,
        acceptance_ran=bool(acceptance is not None and acceptance.ran),
        problem=_unusable(acceptance),
        unmeasured=not_taken,
    )


def _unusable(acceptance: Any) -> str:
    """Why the product cannot be used: no test ran, or the suite passed and the product does not start its user's way.

    The second was dropped because tests had run. Measured in a deep review: settlement then closed a start defect on
    any snapshot, and a fix that broke the start while the suite stayed green was kept.
    """
    if acceptance is None:
        return ""
    problem = str(acceptance.problem or "")
    if not acceptance.report.tests or problem.startswith(suite.PRODUCT_DID_NOT_START):
        return problem[:1500]
    return ""


def save(root: str | Path, snapshot: Snapshot, *, accepted: bool = False) -> None:
    """Keep this snapshot as the latest, and as the last accepted state when `accepted`.

    A snapshot the harness could not take is not kept: the last measurement stays the baseline (A1).
    """
    if getattr(snapshot, "unmeasured", ""):
        logger.warning("Not keeping the measurement %r: it could not be taken (%s)", snapshot.label,
                       snapshot.unmeasured[:200])
        return
    path = Path(root) / CI_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data["latest"] = snapshot.as_dict()
    if accepted:
        data["accepted"] = snapshot.as_dict()
    # When each test first passed, and after which step, so a criterion can be
    # traced to the change that made it pass (plan BG.9). A test that fails
    # again and passes later keeps its first time.
    first = data.get("first_passed") if isinstance(data.get("first_passed"), dict) else {}
    now = datetime.now(timezone.utc).isoformat()
    for key in sorted(snapshot.passing()):
        first.setdefault(key, {"after": snapshot.label, "at": now})
    data["first_passed"] = first
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


_A_CRITERION = re.compile(r"\[([A-Z]+-\d+)\]")


def first_passes(root: str | Path) -> dict[str, dict[str, str]]:
    """Each acceptance criterion's first passing test: after which step and when (plan BG.9).

    The earliest of the tests that carry the criterion's id in their name.
    """
    try:
        first = json.loads((Path(root) / CI_FILE).read_text(encoding="utf-8")).get("first_passed") or {}
    except (OSError, ValueError, AttributeError):
        return {}
    found: dict[str, dict[str, str]] = {}
    for key, when in sorted(first.items(), key=lambda item: str((item[1] or {}).get("at", ""))):
        if not key.startswith("acceptance: ") or not isinstance(when, dict):
            continue
        for criterion in _A_CRITERION.findall(key):
            found.setdefault(criterion, {"test": key.removeprefix("acceptance: "), **{k: str(v) for k, v in when.items()}})
    return found


def load(root: str | Path, which: str = "latest") -> Snapshot | None:
    try:
        data = json.loads((Path(root) / CI_FILE).read_text(encoding="utf-8")).get(which)
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(data, dict):
        return None
    known = {key: data[key] for key in Snapshot.__dataclass_fields__ if key in data}
    return Snapshot(**known)


def regressions(before: Snapshot | None, after: Snapshot) -> list[str]:
    """Tests that passed before and do not pass now, as "unit: name" / "acceptance: name".

    A suite that did not run at all now, having run before, counts every test
    it had passing - a broken build breaks all of them.
    """
    if before is None or getattr(after, "unmeasured", ""):
        # A measurement not taken says nothing broke or passed (A1).
        return []
    lost: list[str] = []
    for kind, was, now, ran in (
        ("unit", before.unit, after.unit, after.unit_ran),
        ("acceptance", before.acceptance, after.acceptance, after.acceptance_ran),
    ):
        ran_before = before.unit_ran if kind == "unit" else before.acceptance_ran
        if not ran_before:
            continue
        for name, outcome in was.items():
            if outcome != "passed":
                continue
            if not ran or _outcome_now(now, name) != "passed":
                lost.append(f"{kind}: {name}")
    return lost


def revert_to(root: str | Path, commit_id: str) -> bool:
    """Put the workspace back exactly as it was at `commit_id`. Ignored files stay."""
    if not commit_id:
        return False
    reset = _git(root, "reset", "--hard", "--quiet", commit_id)
    if reset is None or reset.returncode != 0:
        logger.warning("Could not reset the workspace to %s", commit_id)
        return False
    _git(root, "clean", "-fd", "--quiet")
    # A clean that failed leaves the fix's new files beside the reverted ones (LR.51): reported, not called a revert.
    if not _the_tree_is_clean(root):
        logger.warning("The workspace still differs from %s after the reset and clean", commit_id)
        return False
    return True


def restore_paths(root: str | Path, commit_id: str, paths: Sequence[str]) -> bool:
    """Put `paths` back as they were at `commit_id`: a file it did not have is removed. All or nothing.

    Found in the launch review (LR.51): "git could not show this file at that commit" was read as "the commit did
    not have it", so a commit id git could not read deleted every file it was asked to restore and answered done;
    and a checkout that failed half way left the files already put back changed. Now an unreadable commit touches
    nothing, and a failure part way puts every file back as it was before the call.
    """
    if not commit_id:
        return False
    readable = _git(root, "cat-file", "-e", f"{commit_id}^{{commit}}")
    listed = _git(root, "ls-tree", "-r", "-z", "--full-tree", "--name-only", commit_id, "--", *paths) if paths else None
    if readable is None or readable.returncode != 0 or (paths and (listed is None or listed.returncode != 0)):
        return False
    had = {name for name in (listed.stdout.split("\0") if listed is not None else []) if name}
    base = Path(root)
    before: dict[str, bytes | None] = {}
    try:
        for path in paths:
            before[path] = (base / path).read_bytes() if (base / path).is_file() else None
    except OSError:
        return False

    def put_back() -> None:
        for path, data in before.items():
            try:
                if data is None:
                    (base / path).unlink(missing_ok=True)
                else:
                    (base / path).parent.mkdir(parents=True, exist_ok=True)
                    (base / path).write_bytes(data)
            except OSError:
                continue

    for path in paths:
        if path in had:
            done = _git(root, "checkout", "--quiet", commit_id, "--", path)
            restored = done is not None and done.returncode == 0
        else:
            try:
                (base / path).unlink(missing_ok=True)
                restored = True
            except OSError:
                restored = False
        if not restored:
            put_back()
            return False
    return True


def first_commit(root: str | Path) -> str:
    """The workspace's first commit, or "" when it has none."""
    result = _git(root, "rev-list", "--max-parents=0", "HEAD")
    if result is None or result.returncode != 0:
        return ""
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def changed_since(root: str | Path, commit_id: str) -> list[str]:
    """Workspace-relative paths changed between `commit_id` and HEAD that still exist."""
    if not commit_id:
        return []
    result = _git(root, "diff", "--name-only", commit_id, "HEAD", "--", ".", ":(exclude)docs")
    if result is None or result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip() and (Path(root) / line.strip()).is_file()]


#: Paths a fix stage's measurement and the harness write that are not the product (LF.1444): the workflow's documents,
#: the harness's records, test reports, caches, and the file a command line's code was saved to (`tmp-inline-*`).
NOT_THE_PRODUCT = (":(exclude)docs", ":(exclude,glob).harness/**", ":(exclude,glob)**/test-results/**",
                   ":(exclude,glob)**/__pycache__/**", ":(exclude,glob)**/tmp-inline-*")


def unchanged_since(root: str | Path, commit_id: str) -> bool | None:
    """Whether the product is exactly as `commit_id` left it: no file of it changed since, committed or not; None when
    git cannot say (no commit to compare with, git refused). Files git ignores and `NOT_THE_PRODUCT` are not changes.

    Read over the whole workspace (LF.1444), a fixer whose two edits were both refused counted as a change because the
    harness had saved its one `python3 -c` command to `tmp-inline-<hash>.py`; it was settled "its own tests still
    fail", and the next fixer was told the change it never made was measured and failed.
    """
    if not commit_id:
        return None
    committed = _git(root, "diff", "--quiet", commit_id, "HEAD", "--", ".", *NOT_THE_PRODUCT)
    if committed is None or committed.returncode not in (0, 1):
        return None
    if committed.returncode == 1:
        return False
    status = _git(root, "status", "--porcelain", "--", ".", *NOT_THE_PRODUCT)
    if status is None or status.returncode != 0:
        return None
    return not status.stdout.strip()


def new_since(root: str | Path, commit_id: str) -> list[str]:
    """Workspace-relative paths added between `commit_id` and HEAD that still exist (the workflow's documents aside)."""
    if not commit_id:
        return []
    result = _git(root, "diff", "--name-only", "--diff-filter=A", commit_id, "HEAD", "--", ".", ":(exclude)docs")
    if result is None or result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip() and (Path(root) / line.strip()).is_file()]


def diff_since(root: str | Path, commit_id: str, max_chars: int = 30_000, leaving_out: Sequence[str] = ()) -> str:
    """The product's committed changes since `commit_id`, for a reviewer. The
    workflow's own documents are left out; commit first to include new files.

    `leaving_out`: files the reviewer is handed whole another way (new files its project memory holds, LF.1284), so
    each is not sent a second time as a diff of every line."""
    if not commit_id:
        return ""
    excluded = [f":(exclude,literal){path}" for path in leaving_out if str(path or "").strip()]
    result = _git(root, "diff", commit_id, "HEAD", "--", ".", ":(exclude)docs", *excluded)
    text = result.stdout if result is not None and result.returncode == 0 else ""
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n... (diff cut at {max_chars} characters; read the files for the rest)"
    return text
