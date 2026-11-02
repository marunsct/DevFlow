"""When the suite cannot reach the product, the harness starts it briefly and keeps what it wrote.

Measured on one run: a test the QA stage wrote started the server itself and threw its output away, so the defect said
only "Server did not start in time" through three fix rounds; the cause was a syntax error in the product's SQL, there
to read by simply running it. The helper the harness keeps reports its own service's last words; a test's own way of
starting one, or a suite that errors at setup, reports nothing.

So: the project's own start command, through the sandbox as every harness command goes, ended by the sandbox's short
time limit for the `start` category (a service does not exit by itself; no process is signalled from here). What it
wrote goes into the run's `server_log`, which the defects carry.

A project with no stack pack still has what it can say itself: its `start.sh`, its manifest's start script, a
`Procfile`, a `Makefile` target, or a conventional entry file by language (`_ENTRY_FILES`).
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: How what it wrote opens, in `server_log` and in a defect; what finds it there again.
START_MARK = "The harness started the product itself, with its own start command"
#: What the paragraph says of a product that ran on until the limit ended it.
STILL_RUNNING = "it was still running after"
#: How much of what it wrote is kept: the end of it, where a fatal error is.
MOST_OUTPUT = 2_000
#: The sandbox's category for this command: its time limit is `sandbox.TIMEOUTS["start"]`.
CATEGORY = "start"
#: The exit code of a command the sandbox stopped at its limit.
_TIMED_OUT = 124

#: A whole suite failing at its setup, in the words the runners use, or finding nothing listening.
_AT_SETUP = re.compile(r"failed on setup|error at setup|at setup of|\bbefore(?:All|Each)\b|\bbefore (?:all|each)\b|\bfixture\b|"
                       r"ECONNREFUSED|Connection refused|connect: connection refused", re.I)

#: A file whose presence names how the project runs, when it says nothing itself; first found wins.
_ENTRY_FILES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("manage.py", ("python3", "manage.py", "runserver", "--noreload")),
    ("app.py", ("python3", "app.py")),
    ("main.py", ("python3", "main.py")),
    ("server.py", ("python3", "server.py")),
    ("src/main.py", ("python3", "src/main.py")),
    ("server.js", ("node", "server.js")),
    ("index.js", ("node", "index.js")),
    ("app.js", ("node", "app.js")),
    ("src/server.js", ("node", "src/server.js")),
    ("src/index.js", ("node", "src/index.js")),
    ("main.go", ("go", "run", ".")),
    ("src/main.rs", ("cargo", "run")),
)
#: `Makefile` targets that mean "run it".
_A_MAKE_TARGET = re.compile(r"^(start|run|serve):", re.M)
#: A process type in a `Procfile` that serves.
_A_PROCFILE_LINE = re.compile(r"^web:\s*(.+)$", re.M)
#: Kinds of product that have nothing to start.
_NOTHING_TO_START = frozenset({"cli", "library"})


def _with_its_python(project: Path, argv: tuple[str, ...]) -> list[str]:
    """`argv`, on the project's own Python when it has one: the system's has none of its dependencies."""
    if argv[0] == "python3" and (project / ".venv" / "bin" / "python").exists():
        return [".venv/bin/python", *argv[1:]]
    return list(argv)


def command_for(repo_root: str | Path) -> tuple[list[str], str] | None:
    """(the project's start command, the project directory from the workspace), or None when it says of none. Never raises."""
    try:
        from app.acceptance import suite
        from app.stacks import contract

        found = contract.the_pack(repo_root)
        if found and found[0].kind in _NOTHING_TO_START:
            return None
        where = suite.location(repo_root)
        project_name = where[0] if where else ""
        project = Path(repo_root) / project_name
        if (project / "start.sh").is_file():
            return ["sh", "start.sh"], project_name
        if (project / "package.json").is_file():
            data = json.loads((project / "package.json").read_text(encoding="utf-8"))
            scripts = data.get("scripts") if isinstance(data, dict) else None
            if isinstance(scripts, dict) and str(scripts.get("start") or "").strip():
                return ["npm", "start"], project_name
        if (project / "Procfile").is_file():
            line = _A_PROCFILE_LINE.search((project / "Procfile").read_text(encoding="utf-8", errors="replace"))
            if line:
                return ["sh", "-c", line.group(1).strip()], project_name
        if (project / "Makefile").is_file():
            target = _A_MAKE_TARGET.search((project / "Makefile").read_text(encoding="utf-8", errors="replace"))
            if target:
                return ["make", target.group(1)], project_name
        for name, argv in _ENTRY_FILES:
            if (project / name).is_file():
                return _with_its_python(project, argv), project_name
        return None
    except Exception:  # noqa: BLE001 - nothing known to run
        logger.debug("Could not find the project's start command", exc_info=True)
        return None


def _data_variable(repo_root: str | Path) -> str:
    from app.stacks import contract

    found = contract.the_pack(repo_root)
    return str(getattr(found[0], "data_dir_env", "") or "DATA_DIR") if found else "DATA_DIR"


def _execute(repo_root: str | Path, argv: list[str], project: str, env: dict[str, str]) -> dict[str, Any]:
    """Through the sandbox, like the harness's other commands; the sandbox's time limit is what ends it."""
    from app.tools.sandbox import SandboxExecutor

    return SandboxExecutor.execute(
        argv, repo_root=str(repo_root), role_name="testing_specialist", category=CATEGORY, extra_env=env,
        working_directory=project or None, for_the_harness=True,
    )


#: Where the product is copied to be started as it is delivered: a folder under another name, inside the workspace.
AS_DELIVERED = ".harness/as-delivered"


def _as_delivered(repo_root: Path, project: str) -> str:
    """A copy of the project under the name `product`, hard-linked, for the start to run from; its path from the root.

    Measured on one run: a start script imported the application through the project folder's own name. Started
    from that folder it ran; the benchmark's copy under another name, which is what a customer unpacks, could not
    import it, and no hidden test ran. A hard link per file makes the copy cheap; `DATA_DIR` points elsewhere.
    """
    base = repo_root / AS_DELIVERED
    shutil.rmtree(base, ignore_errors=True)
    copy = base / "product"

    def link(source: str, target: str) -> None:
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)

    shutil.copytree(repo_root / project, copy, symlinks=True, copy_function=link)
    return copy.relative_to(repo_root).as_posix()


def what_it_wrote(repo_root: str | Path) -> str:
    """A paragraph for `server_log`: how the project's own start command ended and what it wrote; "" when none could run. Never raises."""
    data = ""
    try:
        command = command_for(repo_root)
        if command is None:
            return ""
        argv, project = command
        from app.tools.sandbox import _a_free_port, timeout_for

        data = tempfile.mkdtemp(prefix="start-output-")
        try:
            where = _as_delivered(Path(repo_root), project)
        except OSError:
            where = project  # a copy that cannot be made: started where it is, as before
        outcome = _execute(repo_root, argv, where, {
            "PORT": str(_a_free_port()), "HOST": "127.0.0.1", _data_variable(repo_root): data,
        }) or {}
        try:
            code = int(str(outcome.get("returncode")).strip())
        except ValueError:
            return ""  # refused, or never started: it says nothing of the product
        wrote = "\n".join(str(outcome.get(k) or "").strip() for k in ("stdout", "stderr") if str(outcome.get(k) or "").strip())
        how = (f"{STILL_RUNNING} {timeout_for(CATEGORY, repo_root)} seconds, when it was ended" if code == _TIMED_OUT
               else f"it stopped by itself with exit code {code}")
        return f"{START_MARK} (`{' '.join(argv)}`): {how}. It wrote:\n{wrote[-MOST_OUTPUT:] or '(nothing)'}"
    except Exception:  # noqa: BLE001 - the defect goes out as it was
        logger.debug("Could not start the product to see what it writes", exc_info=True)
        return ""
    finally:
        if data:
            shutil.rmtree(data, ignore_errors=True)
        shutil.rmtree(Path(repo_root) / AS_DELIVERED, ignore_errors=True)


def how_it_is_used_fails(repo_root: str | Path) -> str:
    """What the pack's way of using a product with nothing to start said, when it failed; "" otherwise. Never raises."""
    try:
        from app.acceptance import suite
        from app.stacks import contract

        found = contract.the_pack(repo_root)
        where = suite.location(repo_root)
        if found is None or where is None or not found[0].how_it_is_used:
            return ""
        package = str(found[1].get("package") or "")
        argv = [part.replace("{{package}}", package) for part in found[0].how_it_is_used]
        outcome = _execute(repo_root, argv, where[0], {}) or {}
        try:
            code = int(str(outcome.get("returncode")).strip())
        except ValueError:
            return ""  # refused, or never run: it says nothing of the product
        if code in (0, _TIMED_OUT):
            return ""
        wrote = "\n".join(str(outcome.get(k) or "").strip() for k in ("stdout", "stderr") if str(outcome.get(k) or "").strip())
        return (
            f"`import {package}` from the project folder, as its user would, finds no code there (exit code {code}), "
            f"though the suite's way of reaching it passed. The package's files belong in `{package}/` inside the "
            f"project, not at the project's top. {wrote[-MOST_OUTPUT:]}"
        ).strip()
    except Exception:  # noqa: BLE001 - the run stands without it
        logger.debug("Could not use the product as its user would", exc_info=True)
        return ""


def in_text(text: str) -> str:
    """The paragraph `what_it_wrote` made, from a `server_log` or a defect's text; "" when it is not there."""
    said = str(text or "")
    at = said.rfind(START_MARK)
    return said[at:at + MOST_OUTPUT + 400].strip() if at >= 0 else ""


def the_suite_could_not_reach_it(result: Any) -> bool:
    """Whether this run of the suite says the product did not start, or the whole suite errored at its setup."""
    from app.acceptance import suite

    if str(getattr(result, "problem", "") or "").startswith(suite.PRODUCT_DID_NOT_START):
        return True
    tests = list(getattr(getattr(result, "report", None), "tests", None) or ())
    if not tests:
        return int(getattr(result, "exit_code", 0) or 0) != 0
    failed = [t for t in tests if t.outcome == "failed"]
    if any(suite._NEVER_STARTED.search(t.message or "") for t in failed):
        return True  # one test's own way of starting it, with the rest of the suite fine
    return bool(failed) and not any(t.outcome == "passed" for t in tests) and all(
        _AT_SETUP.search(t.message or "") for t in failed)


def add_to(repo_root: str | Path, result: Any) -> None:
    """Add what the start wrote to `result.server_log`, for a locked suite that could not reach the product. Never raises.

    Not before the lock: nothing is built yet, and QA's rounds have no fixer to tell. Once per version of the product:
    the same product wrote the same thing a moment ago. One message of the suite's own is asked about too, and also while
    a locked suite is being repaired (the product exists then): the finding it may become needs what the start did.
    """
    try:
        from app.acceptance import suite
        from app.acceptance.unstable import unchanged_since_the_suite_measured

        locked = suite.is_locked(repo_root)
        its_own = (locked or suite.is_being_repaired(repo_root)) and suite.a_message_of_the_suite_s_own(repo_root, result)
        if not its_own and not (locked and the_suite_could_not_reach_it(result)):
            return
        kept = in_text(str((suite.last_result(repo_root) or {}).get("server_log") or ""))
        wrote = kept if kept and unchanged_since_the_suite_measured(repo_root) else what_it_wrote(repo_root)
        if wrote and wrote not in str(result.server_log or ""):
            result.server_log = "\n".join(part for part in (str(result.server_log or ""), wrote) if part)
    except Exception:  # noqa: BLE001 - the run stands without it
        logger.debug("Could not add what the start wrote", exc_info=True)


__all__ = ["START_MARK", "STILL_RUNNING", "add_to", "command_for", "how_it_is_used_fails", "in_text", "the_suite_could_not_reach_it", "what_it_wrote"]
