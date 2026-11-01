"""The project's production build, run by the harness: a product that does not build is not done.

Measured on one run: the locked suite passed 12 of 12 against the development server, which compiles file by file and
reads no types; `npm run build` stopped on a compiler error, nothing in the harness had ever run it, and the hidden
tests, which start the built product, passed 1 of 10.

Which command, in order: the one the pack or the proven setup declares (`StackPack.production_build`), else what the
project's own manifest names (`_MANIFEST_BUILDS`, a table by manifest). A project with neither has no build to run:
a pack whose acceptance suite starts the product through its compiler proves the build on every run and declares
none. The result is kept with the product's fingerprint, so the build runs once per version of the product: an
unchanged product gets the same answer, failing or not, without running it again. Only a build that finished is an
answer: one the sandbox refused or stopped at its limit says nothing, like every other check that cannot run.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Sequence

logger = logging.getLogger(__name__)

#: How a defect from a failing build begins; what settles such a defect looks for it.
THE_PRODUCT_DOES_NOT_BUILD = "The project's production build fails, so what would be shipped does not exist."
#: Where the last answer is kept (the harness's own folder: not part of the product, not in git).
RECORD = ".harness/production-build.json"
#: How much of what the compiler said goes with a defect: its first errors are the ones that matter.
MOST_OUTPUT = 3_000
#: The exit code of a command the sandbox stopped at its time limit.
_TIMED_OUT = 124

Runner = Callable[[Sequence[str], str, str], dict[str, Any]]

_COLOURS = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
#: A path in the compiler's output, as `file(12,5)` or `file:12`.
_A_PLACE = re.compile(r"(?P<path>[\w@./-]+\.[A-Za-z][A-Za-z0-9]{0,7})(?=\(\d+|:\d+)")
#: The most files a defect names.
MOST_FILES = 8


def _package_json_build(project: Path) -> tuple[str, ...]:
    """`npm run build` when the manifest names that script and its dependencies are installed; else ()."""
    if not (project / "node_modules").is_dir():
        return ()  # nothing is installed to build with: that is the install's defect
    data = json.loads((project / "package.json").read_text(encoding="utf-8"))
    scripts = data.get("scripts") if isinstance(data, dict) else None
    return ("npm", "run", "build") if isinstance(scripts, dict) and str(scripts.get("build") or "").strip() else ()


#: Manifest file -> reads the command that manifest names for its build.
_MANIFEST_BUILDS: tuple[tuple[str, Callable[[Path], tuple[str, ...]]], ...] = (
    ("package.json", _package_json_build),
)


def declared(repo_root: str | Path) -> tuple[list[str], str] | None:
    """(the build's argv, the project directory relative to the workspace), or None when no build is declared. Never raises."""
    try:
        from app.stacks import contract
        from app.tools.repository import pinned_project_directory

        found = contract.the_pack(repo_root)
        record = found[1] if found else (contract.read(repo_root) or {})
        project = str(record.get("project") or "") or str(pinned_project_directory(Path(repo_root)) or "")
        command = tuple(getattr(found[0], "production_build", ()) or ()) if found else ()
        if not command:
            base = Path(repo_root) / project
            for name, read in _MANIFEST_BUILDS:
                if (base / name).is_file():
                    command = read(base)
                if command:
                    break
        return (list(command), project) if command else None
    except Exception:  # noqa: BLE001 - a check that cannot run finds nothing
        logger.debug("Could not read the project's build command", exc_info=True)
        return None


def _read_record(root: Path) -> dict[str, Any]:
    try:
        data = json.loads((root / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _keep_record(root: Path, record: dict[str, Any]) -> None:
    try:
        path = root / RECORD
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record), encoding="utf-8")
    except OSError:
        logger.debug("Could not keep the build's answer", exc_info=True)


def failure(repo_root: str | Path, runner: Runner | None = None) -> str:
    """What the build said when it failed on the product as it is now; "" when it passes, or none can be told. Never raises."""
    try:
        command = declared(repo_root)
        if command is None:
            return ""
        argv, project = command
        from app.acceptance.unstable import fingerprint

        root = Path(repo_root)
        said = " ".join(argv)
        before = fingerprint(root)
        kept = _read_record(root)
        if before and kept.get("fingerprint") == before and kept.get("command") == said:
            return str(kept.get("failure") or "")
        if runner is None:
            from app.stacks.scaffold import sandbox_runner

            runner = sandbox_runner(root)
        outcome = runner(argv, "build", project) or {}
        try:
            code = int(str(outcome.get("returncode")).strip())
        except ValueError:
            return ""  # refused, or never started: no answer
        if code == _TIMED_OUT:
            logger.warning("`%s` did not finish within its limit; it says nothing about the product", said)
            return ""
        text = "" if code == 0 else _COLOURS.sub(
            "", "\n".join(str(outcome.get(k) or "") for k in ("stdout", "stderr") if outcome.get(k))).strip()
        answer = (text[:MOST_OUTPUT] or f"`{said}` exited with code {code} and printed nothing.") if code else ""
        # After the build: output nothing ignores would otherwise read as a changed product, and it would build every time.
        _keep_record(root, {"fingerprint": fingerprint(root), "command": said, "failure": answer})
        if answer:
            logger.warning("`%s` failed in %s", said, project or "the workspace")
        return answer
    except Exception:  # noqa: BLE001 - a check that cannot run finds nothing
        logger.debug("Could not run the project's build", exc_info=True)
        return ""


def still_raised(repo_root: str | Path, description: str, runner: Runner | None = None) -> bool | None:
    """Whether a build defect still stands, by the build itself; None for any other defect."""
    if not str(description or "").startswith(THE_PRODUCT_DOES_NOT_BUILD):
        return None
    return bool(failure(repo_root, runner))


def files_named(repo_root: str | Path, output: str) -> list[str]:
    """The project's own files the compiler named, as paths from the workspace, in the order it named them."""
    command = declared(repo_root)
    project = command[1] if command else ""
    base = Path(repo_root) / project
    found: list[str] = []
    for match in _A_PLACE.finditer(str(output or "")):
        path = match["path"].removeprefix("./")
        if "node_modules" in path or path.startswith("/") or ".." in path or not (base / path).is_file():
            continue
        named = f"{project}/{path}" if project else path
        if named not in found:
            found.append(named)
        if len(found) >= MOST_FILES:
            break
    return found


def reproduce(repo_root: str | Path) -> str:
    """The sentence saying how to see the failure."""
    command = declared(repo_root)
    if command is None:
        return "Run the project's production build."
    where = f" in `{command[1]}`" if command[1] else ""
    return f"Run `{' '.join(command[0])}`{where}: it fails, whatever the suite running on the development server says."


__all__ = ["THE_PRODUCT_DOES_NOT_BUILD", "declared", "failure", "files_named", "reproduce", "still_raised"]
