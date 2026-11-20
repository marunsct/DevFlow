"""A test command run again with nothing changed is answered from its last result, not run again.

Measured on one run's acceptance suite writer: `npm run test:acceptance` was run three times in four minutes, the
second two seconds after the first result with nothing written between, the third after four reads. Each took about
64 seconds and gave the same 0 of 37. The sandbox already knew - the second and third results carried "the same
result as this command gave here ... and no file has changed since" - but that note was added after the command had
run again, so two minutes of the stage went on runs whose answer was known.

The existing guard against repeats (`sandbox.SUCCESSES_BEFORE_WITHHOLDING`, LF.174) withholds a command only after
three identical passes, and refuses it without its output. A failing suite never reaches it: failures are only
noted. This answers the very first unchanged repeat, pass or fail, with the real last result, so the stage loses
nothing it would have learned.

It answers only when it can tell nothing changed, and runs the command as before otherwise:

- the same command, in the same directory, by the same stage and role, in the test category, run by an agent;
- the run's ledger has recorded nothing since that result - no install, no build, no harness run, which can change
  what a test sees without changing a workspace file;
- the workspace's files are as they were when the result was taken, by path, size and modification time - and were
  the same before and after that run, so a file another stage wrote while it ran is never hidden. A file the command
  itself rewrites every run means its result is never reused.

The harness's own records (`.harness/`, the stage summaries, the project memory), the agent's home folder, `.git`,
installed and built directories and a test runner's own reports are not the work, so they are left out of the
comparison. Every other file counts, dotfiles too.
"""

from __future__ import annotations

import hashlib
import os
import threading
from collections import OrderedDict
from typing import Any, Sequence

from app.tools.repository import HARNESS_DIRECTORIES, HARNESS_FILES, HARNESS_HOME_FOLDER, IGNORED_DIRECTORIES

#: How many results are kept, across every workspace this process serves; the oldest goes first.
MOST_RESULTS_KEPT = 64

#: Directories at any depth that are not the work (see the module docstring), beside the installed and built ones.
_NOT_THE_WORK = frozenset({".git", HARNESS_HOME_FOLDER})

_KEPT: "OrderedDict[tuple, dict]" = OrderedDict()
_LOCK = threading.Lock()


def what_the_workspace_holds(repo_root: str) -> str | None:
    """A digest of every file of the work in `repo_root` - path, size, modification time - or None when unknown.

    None for anything it cannot read, so an unreadable workspace is never taken for an unchanged one.
    """
    from app.tools.sandbox import _RUNNER_OUTPUT_DIRECTORIES

    root = os.path.realpath(repo_root)
    if not os.path.isdir(root):
        return None

    def stop(error: OSError) -> None:
        raise error

    digest = hashlib.sha256()
    try:
        for directory, subdirectories, files in os.walk(root, onerror=stop):
            here = os.path.relpath(directory, root).replace(os.sep, "/")
            subdirectories[:] = sorted(
                name for name in subdirectories
                if name not in IGNORED_DIRECTORIES and name not in _RUNNER_OUTPUT_DIRECTORIES
                and name not in _NOT_THE_WORK
                and (name if here == "." else f"{here}/{name}") not in HARNESS_DIRECTORIES
            )
            digest.update(f"{here}/\n".encode("utf-8", "surrogateescape"))
            for name in sorted(files):
                if here == "." and name in HARNESS_FILES:
                    continue
                status = os.lstat(os.path.join(directory, name))
                digest.update(
                    f"{here}/{name}\0{status.st_size}\0{status.st_mtime_ns}\n".encode("utf-8", "surrogateescape"))
    except (OSError, ValueError):
        return None
    return digest.hexdigest()


def _key(repo_root: str, command: Sequence[str], where: str, stage: str, role: str) -> tuple:
    return (os.path.realpath(repo_root), tuple(str(part) for part in command), where, stage, role)


def keep(
    repo_root: str,
    command: Sequence[str],
    where: str,
    stage: str,
    role: str,
    *,
    entry: dict | None,
    outcome: dict,
    later_sprints: str,
    before: str | None,
) -> None:
    """Keep `outcome`, the result of a test run just recorded as `entry`, for an unchanged repeat. Never raises.

    `before` is `what_the_workspace_holds` just before the run. Kept only when the workspace held the same after it,
    the run finished with an exit code, and nothing refused it; otherwise any earlier result is dropped.
    """
    try:
        key = _key(repo_root, command, where, stage, role)
        after = what_the_workspace_holds(repo_root)
        finished = isinstance(entry, dict) and entry.get("returncode") is not None and not outcome.get("error")
        with _LOCK:
            _KEPT.pop(key, None)
            if not finished or before is None or after != before:
                return
            _KEPT[key] = {
                "at": entry["at"],
                "workspace": after,
                "outcome": {name: value for name, value in outcome.items() if name in ("returncode", "stdout", "stderr")},
                "later_sprints": later_sprints,
                "seconds": entry.get("duration_seconds"),
                "counts": {name: entry[name] for name in ("passed", "failed", "tests") if name in entry},
            }
            while len(_KEPT) > MOST_RESULTS_KEPT:
                _KEPT.popitem(last=False)
    except Exception:  # noqa: BLE001 - keeping a result must never fail the command
        return


def the_earlier_result(
    repo_root: str,
    command: Sequence[str],
    where: str,
    stage: str,
    role: str,
    *,
    latest: dict | None,
) -> dict | None:
    """The kept result that answers this command now, or None to run it. Never raises.

    `latest` is the run's last ledger entry: it must be this same command's run (or a repeat answered from it), so
    nothing - an install, a build, a harness run - has been recorded since the result was taken.
    """
    try:
        key = _key(repo_root, command, where, stage, role)
        with _LOCK:
            kept = _KEPT.get(key)
        if not kept or not isinstance(latest, dict):
            return None
        argv = [str(part) for part in command]
        if (latest.get("command") != argv or latest.get("working_directory") != where
                or latest.get("stage") != stage or latest.get("role") != role
                or latest.get("by") != "agent" or latest.get("category") != "test"
                or (latest.get("reused_from") or latest.get("at")) != kept["at"]):
            return None
        now = what_the_workspace_holds(repo_root)
        if now is None or now != kept["workspace"]:
            return None
        return {**kept, "outcome": dict(kept["outcome"]), "counts": dict(kept["counts"])}
    except Exception:  # noqa: BLE001 - unknown means run it
        return None


def the_mark(earlier: dict) -> str:
    """The line put before a result answered from `earlier`, saying it is the earlier result and what to do instead."""
    at = str(earlier.get("at") or "")[11:19]
    counts = earlier.get("counts") or {}
    tally = f" - {counts['passed']} of {counts['tests']} passed -" if "passed" in counts and "tests" in counts else ""
    passed = str(earlier.get("outcome", {}).get("returncode")) == "0"
    then = ("It passed then: this verification is finished, so give your answer, or change a file first."
            if passed else "Change what the failure names, or give your answer.")
    return (
        f"[Not run again: the same command gave the result below at {at} UTC{tally} and no file has changed since, "
        f"so running it again could only repeat it. {then}]"
    )


def answered_from(earlier: dict) -> dict[str, Any]:
    """The command's result answered from `earlier`: its own exit code and output, marked as the earlier result."""
    outcome = dict(earlier["outcome"])
    stdout = str(outcome.get("stdout") or "")
    outcome["stdout"] = the_mark(earlier) + ("\n\n" + stdout if stdout else "")
    return outcome
