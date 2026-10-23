"""The acceptance suite run one file at a time, when the whole of it gives no answer.

A suite that hangs reports nothing: one run's locked suite timed out on its
first run (exit 124, no test reported) and a frontier model spent 38 minutes
running files one by one to find that the product's `start()` resolved before
its socket was bound. The harness can run them one by one itself, each with a
short limit (`sandbox.TIMEOUTS["probe"]`), and say which file does not finish
and what each failing file printed.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any, Callable, Sequence

#: Characters of one file's output kept.
MOST_OUTPUT_CHARACTERS = 2_500

Runner = Callable[[Sequence[str], str, str], dict[str, Any]]


def _the_command_for(argv: Sequence[str], file: str, directory: str, pattern: str) -> list[str]:
    """The suite's command with its file selection replaced by one file."""
    selects = [
        i for i, arg in enumerate(argv)
        if not str(arg).startswith("-") and (pattern and fnmatch.fnmatch(Path(str(arg)).name, pattern)
                                               or "*" in str(arg) or str(arg).rstrip("/") == directory.rstrip("/"))
    ]
    if not selects:
        return [*argv, file]
    command = [arg for i, arg in enumerate(argv) if i not in selects[1:]]
    command[selects[0]] = file
    return command


def _its_own_tests(report: Path, naming: set[str]) -> str:
    """`finished` when every test in the file's report that carries one of `naming` passed, `failed` when one did not; "" when none carries one.

    A file holds tests of several criteria. Judged by its exit code, a defect
    whose own tests passed stayed open while a sibling test of another
    criterion failed - measured on a gate run: AC-9's six tests passed, the
    file also held a later sprint's AC-8 test, and AC-9 was left open each
    round its fix was measured.
    """
    from app.acceptance import junit

    # By the test's own name: its suite is the file, and a file named for
    # several criteria would give each of its tests every one of them.
    own = [t for t in junit.read(report).tests if set(junit.tags_in(t.name)) & naming]
    if not own:
        return ""
    return "finished" if all(t.outcome in ("passed", "skipped") for t in own) else "failed"


def each_file(repo_root: str | Path, record: dict[str, Any], run: Runner, *, naming: set[str] | None = None) -> list[dict[str, str]]:
    """Each acceptance file's own run: its path, `finished`/`failed`/`hung`, and the end of its output.

    `naming`: only the files whose text names one of these (criterion ids, for one defect's check),
    each judged by its tests that carry one of them (`_its_own_tests`) when its report says.
    """
    project = str(record.get("project") or "")
    directory = str(record.get("acceptance_dir") or "")
    pattern = str(record.get("acceptance_pattern") or "*")
    argv = list(record.get("acceptance_test") or [])
    base = Path(repo_root) / project / directory
    if not argv or not base.is_dir():
        return []
    found: list[dict[str, str]] = []
    from app.analysis.walk import files_under

    # Not into `node_modules`: a suite with its own dependencies holds
    # thousands of files there, and a package's own `*.spec.js` is no test of
    # this product.
    for path in sorted(p for p in files_under(base, ("node_modules",)) if fnmatch.fnmatch(p.name, pattern)):
        relative = path.relative_to(Path(repo_root) / project).as_posix()
        if naming is not None:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if not any(name in text for name in naming):
                continue
        report = Path(repo_root) / project / str(record.get("acceptance_report") or "") if record.get("acceptance_report") else None
        if naming is not None and report is not None:
            from app.acceptance import junit

            junit.clear(report)
        outcome = run(_the_command_for(argv, relative, directory, pattern), "probe", project) or {}
        output = (str(outcome.get("stdout") or "") + str(outcome.get("stderr") or "") + str(outcome.get("error") or ""))
        code = str(outcome.get("returncode", ""))
        hung = code == "124" or "timed out" in output.lower()
        verdict = "finished" if code == "0" else "failed"
        if naming is not None and not hung and report is not None:
            verdict = _its_own_tests(report, naming) or verdict
        found.append({
            "file": f"{project}/{relative}" if project else relative,
            "outcome": "hung" if hung else verdict,
            "output": output.strip()[-MOST_OUTPUT_CHARACTERS:],
        })
    return found


def defects_from(runs: list[dict[str, str]], owner: str, limit_seconds: int) -> list[Any]:
    """One defect per acceptance file that hung or failed, owned by the role that writes the product."""
    from app.agents.specialists import ReportedDefect

    defects = []
    for run in runs:
        if run["outcome"] == "finished":
            continue
        hung = run["outcome"] == "hung"
        defects.append(ReportedDefect(
            description=(
                f"`{run['file']}` does not finish within {limit_seconds} s: the product, started for it, "
                "leaves a server, a timer or a connection open, or never becomes ready."
                if hung else f"`{run['file']}` fails. Its output ends:\n{run['output']}"
            ),
            severity="major",
            reproduction_steps=f"Run the acceptance suite on `{run['file']}` alone.",
            expected_behavior="The file's tests run to the end and pass.",
            actual_behavior=run["output"] or ("It was still running when stopped." if hung else "It exits non-zero."),
            affected_files=[],
            owner=owner,
        ))
    return defects
