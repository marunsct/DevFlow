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


def commit(root: str | Path, message: str) -> str:
    """Commit everything as it stands; the commit HEAD now names (new or not)."""
    from app.tools.version_control import commit_all

    commit_all(root, message)
    return head(root)


#: Between where a test lives and its name in a snapshot's key.
WHERE = " \u203a "

#: Which of two outcomes for one key is kept: the worse.
_RANK = {"passed": 0, "skipped": 1, "failed": 2}


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
        key = f"{where}{WHERE}{test.name}" if where else test.name
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
    name = _bare(key)
    same = [outcome for other, outcome in now.items() if _bare(other) == name]
    if not same:
        return None
    return "passed" if all(outcome == "passed" for outcome in same) else "failed"


def _run_unit(root: str | Path, runner: Runner | None) -> tuple[dict[str, str], bool]:
    found = contract.the_pack(root)
    if found is None:
        return {}, False
    pack, record = found
    project = str(record.get("project") or "")
    report = Path(root) / project / pack.unit_report
    junit.clear(report)
    if runner is None:
        from app.stacks.scaffold import sandbox_runner

        runner = sandbox_runner(root)
    contract.install_if_the_manifests_changed(root, runner)
    runner(list(record.get("unit_test") or pack.unit_test), "test", project)
    parsed = junit.read(report)
    return outcomes_of(parsed.tests), parsed.found


def unit_failures(root: str | Path, runner: Runner | None = None) -> list[str]:
    """The project's own unit tests that do not pass now, by name; [] when all pass or none ran."""
    unit, ran = _run_unit(root, runner)
    if not ran:
        return []
    return sorted(name for name, outcome in unit.items() if outcome != "passed")


def take(
    root: str | Path,
    label: str,
    *,
    runner: Runner | None = None,
    acceptance: suite.AcceptanceResult | None = None,
) -> Snapshot:
    """Run the unit and acceptance suites now. `acceptance` reuses a run just made."""
    unit, unit_ran = _run_unit(root, runner)
    if acceptance is None and suite.is_locked(root):
        acceptance = suite.run(root, runner=runner)
    tests = outcomes_of(acceptance.report.tests) if acceptance is not None else {}
    return Snapshot(
        label=label,
        commit=head(root),
        unit=unit,
        acceptance=tests,
        unit_ran=unit_ran,
        acceptance_ran=bool(acceptance is not None and acceptance.ran),
        problem=str(acceptance.problem or "")[:1500] if acceptance is not None and not acceptance.report.tests else "",
    )


def save(root: str | Path, snapshot: Snapshot, *, accepted: bool = False) -> None:
    """Keep this snapshot as the latest, and as the last accepted state when `accepted`."""
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
    if before is None:
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
    return True


def restore_paths(root: str | Path, commit_id: str, paths: Sequence[str]) -> bool:
    """Put `paths` back as they were at `commit_id`: a file it did not have is removed."""
    if not commit_id:
        return False
    for path in paths:
        existed = _git(root, "cat-file", "-e", f"{commit_id}:{path}")
        if existed is not None and existed.returncode == 0:
            done = _git(root, "checkout", "--quiet", commit_id, "--", path)
            if done is None or done.returncode != 0:
                return False
        else:
            try:
                (Path(root) / path).unlink(missing_ok=True)
            except OSError:
                return False
    return True


def changed_since(root: str | Path, commit_id: str) -> list[str]:
    """Workspace-relative paths changed between `commit_id` and HEAD that still exist."""
    if not commit_id:
        return []
    result = _git(root, "diff", "--name-only", commit_id, "HEAD", "--", ".", ":(exclude)docs")
    if result is None or result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip() and (Path(root) / line.strip()).is_file()]


def diff_since(root: str | Path, commit_id: str, max_chars: int = 30_000) -> str:
    """The product's committed changes since `commit_id`, for a reviewer. The
    workflow's own documents are left out; commit first to include new files."""
    if not commit_id:
        return ""
    result = _git(root, "diff", commit_id, "HEAD", "--", ".", ":(exclude)docs")
    text = result.stdout if result is not None and result.returncode == 0 else ""
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n... (diff cut at {max_chars} characters; read the files for the rest)"
    return text
