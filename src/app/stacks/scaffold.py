"""Write a pack into the project directory and prove its tests run.

The order is the point: files, install, then the pack's own two smoke tests -
one unit, one acceptance - through exactly the commands the harness will use
for the rest of the run. Only a scaffold whose smoke tests pass is kept as one;
the smoke tests are then removed, because a test that asserts nothing about the
product has no place in it.

A scaffold that cannot be proven (no network for the install, a toolchain the
image lacks) is not a reason to fail the run: the result says why, and the run
continues the way every run did before packs existed.
"""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from app.acceptance import junit
from app.stacks import StackPack
from app.stacks import contract

logger = logging.getLogger(__name__)

#: How much of a failing command's output a result keeps: enough that the line
#: naming the error is still in it, ahead of a tool's closing advice.
OUTPUT_TAIL_CHARS = 6_000

#: Runs one argv in a directory of the workspace: (argv, category, working
#: directory relative to the workspace) -> {"returncode", "stdout", "stderr"}
#: or {"error"}. Injected so tests need no toolchain.
Runner = Callable[[Sequence[str], str, str], dict[str, Any]]


@dataclass
class ScaffoldResult:
    ok: bool
    pack: str
    project: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    problem: str = ""


def entrypoint_is_still_the_stub(repo_root: str | Path) -> str | None:
    """The declared entrypoint's workspace-relative path while it is still the stub; else None.

    The dominant live failure was a served app that was still the scaffold's
    stub: everything the run drafted sat in files nothing served, and 31 of 35
    locked tests failed against the stub with no measurement ever saying so -
    the fixers chased criteria one by one and could not exit (Initiative K.3).
    The comparison is byte for byte against what `StackPack.render` produced
    for this project's names, which is exactly what the scaffold wrote.

    None - nothing to accuse - when the run has no contract, was not
    scaffolded by a pack, the pack declares no entrypoint or keeps the file
    itself, the rendered stub is unknown, or the file changed, went missing
    or cannot be read.
    """
    from app.stacks import contract, pack_named

    record = contract.read(repo_root)
    if not record or not record.get("scaffolded", True):
        return None
    pack = pack_named(str(record.get("pack") or ""))
    if not pack:
        return None
    declared = [str(e) for e in (getattr(pack, "entrypoint", "") or "", *(getattr(pack, "entrypoints", ()) or ())) if e]
    kept = getattr(pack, "kept_files", ()) or ()
    project = str(record.get("project") or "")
    title = str(record.get("title") or "")
    package = str(record.get("package") or "") or None
    try:
        rendered_files = pack.render(project, title, package)
    except (OSError, ValueError):
        return None
    for entrypoint in declared:
        if entrypoint in kept:
            continue
        # Declared with the package's placeholder, rendered with its name.
        path = pack.filled(entrypoint, project, title, package)
        rendered = rendered_files.get(path)
        if rendered is None:
            continue
        try:
            current = (Path(repo_root) / project / path).read_text(encoding="utf-8")
        except OSError:
            continue
        if current == rendered:
            return f"{project}/{path}"
    return None



def _served_entrypoints(repo_root: str | Path) -> tuple[str, list[str]]:
    """(the project folder, its pack's entrypoints as project-relative paths); ("", []) when unknown."""
    from app.stacks import contract, pack_named

    record = contract.read(repo_root) or {}
    pack = pack_named(str(record.get("pack") or ""))
    if not pack:
        return "", []
    project = str(record.get("project") or "")
    title = str(record.get("title") or "")
    package = str(record.get("package") or "") or None
    declared = [str(e) for e in (getattr(pack, "entrypoint", "") or "", *(getattr(pack, "entrypoints", ()) or ())) if e]
    return project, list(dict.fromkeys(pack.filled(e, project, title, package) for e in declared))


#: Folders that are never the product's own code.
_NOT_CODE = (
    "node_modules", ".venv", "venv", ".git", "dist", "build", "__pycache__", ".harness",
    "test-results", "playwright-report", "coverage", ".pytest_cache",
)
_FAMILIES = {
    "python": (".py",),
    "script": (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte"),
}


def _a_unit_test(name: str, pack: Any) -> bool:
    """Whether a file name is one the pack's unit runners collect (pack data, Initiative AO.10)."""
    from fnmatch import fnmatch

    names = (*(getattr(pack, "unit_test_names", ()) or ()), getattr(pack, "unit_pattern", "") or "")
    return any(glob and fnmatch(name, glob) for glob in names)


def _family(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return next((name for name, suffixes in _FAMILIES.items() if suffix in suffixes), "")


def _second_copies(entrypoints: list[str], files: list[str]) -> list[tuple[str, str, str, list[str]]]:
    """(entrypoint, its folder, the copy, the copy's files) for each folder repeating two or more files of a served folder."""
    found = []
    for entrypoint in entrypoints:
        folder = Path(entrypoint).parent.as_posix()
        if folder in ("", "."):
            continue
        name = Path(folder).name
        served = {
            Path(f[len(folder) + 1:]).with_suffix("").as_posix()
            for f in files if f.startswith(folder + "/")
        }
        copies: dict[str, list[str]] = {}
        for f in files:
            if f.startswith(folder + "/"):
                continue
            parts = Path(f).parts
            for at in range(len(parts) - 1):
                if parts[at] != name:
                    continue
                rest = Path(*parts[at + 1:]).with_suffix("").as_posix()
                if rest in served:
                    copies.setdefault(Path(*parts[: at + 1]).as_posix(), []).append(f)
                break
        for copy, mirrored in sorted(copies.items()):
            if len(mirrored) >= 2:
                found.append((entrypoint, folder, copy, mirrored))
    return found


def folders_nothing_serves(repo_root: str | Path) -> list[str]:
    """The folders (relative to the workspace) that repeat files of a served folder and are never run. Never raises.

    The project memory and the stage's reading leave them to the end: they
    filled the memory beside the served copy and were read as though they
    were the product (Initiative AQ).
    """
    try:
        project, entrypoints = _served_entrypoints(repo_root)
        root = Path(repo_root) / project
        if not entrypoints or not root.is_dir():
            return []
        from app.acceptance import suite
        from app.analysis.walk import files_under

        acceptance = suite.directory(repo_root)
        files = [
            path.relative_to(root).as_posix()
            for path in files_under(root, _NOT_CODE)
            if _family(path.name) and not (acceptance and path.is_relative_to(acceptance))
        ]
        return [f"{project}/{copy}".strip("/") for _e, _f, copy, _m in _second_copies(entrypoints, files)]
    except Exception:  # noqa: BLE001
        return []


def code_the_product_does_not_run(repo_root: str | Path) -> list[str]:
    """Code beside the served app that the product never runs, and unit tests that only test it. Never raises.

    Measured on one run: the drafted page sat in `frontend/src/` and the
    drafted service in `backend/app/` while the scaffold served `src/` and the
    package's `main.py`. Fixes were made in both trees - one fix rewrote a
    migration file nothing ran - and the unit tests imported the unserved
    service, so their result said nothing about the product the acceptance
    suite measured. Two findings, each decided from the files:

    - a folder that repeats the relative paths of two or more files in a served
      entrypoint's folder is a second copy nothing serves;
    - unit tests in an entrypoint's language, none of which names that
      entrypoint's folder, test other code.
    """
    try:
        project, entrypoints = _served_entrypoints(repo_root)
        root = Path(repo_root) / project
        if not entrypoints or not root.is_dir():
            return []
        from app.stacks import contract, pack_named

        pack = pack_named(str((contract.read(repo_root) or {}).get("pack") or ""))
        from app.acceptance import suite
        from app.analysis.walk import files_under

        acceptance = suite.directory(repo_root)
        files = [
            path.relative_to(root).as_posix()
            for path in files_under(root, _NOT_CODE)
            if _family(path.name) and not (acceptance and path.is_relative_to(acceptance))
        ]
        problems: list[str] = []
        for entrypoint, folder, copy, mirrored in _second_copies(entrypoints, files):
            problems.append(
                f"`{project}/{copy}/` repeats {len(mirrored)} files of the served `{project}/{folder}/` "
                f"(e.g. `{project}/{mirrored[0]}`), and nothing serves it: the product runs from "
                f"`{project}/{entrypoint}`. Change the served copy; the other is never built or run."
            )
        for family in sorted({_family(e) for e in entrypoints} - {""}):
            tests = [f for f in files if _family(f) == family and _a_unit_test(Path(f).name, pack)]
            served_folders = {
                Path(e).parent.name for e in entrypoints
                if _family(e) == family and Path(e).parent.as_posix() not in ("", ".")
            }
            if not tests or not served_folders:
                continue
            # Fixtures count: a test can reach the app through a helper the pack names.
            helpers = [f for f in files if Path(f).name in (getattr(pack, "test_helpers", ()) or ())]
            texts = [(root / f).read_text(encoding="utf-8", errors="replace") for f in [*tests, *helpers]]
            if not any(re.search(rf"\b{re.escape(n)}\b", text) for n in served_folders for text in texts):
                problems.append(
                    f"The unit tests ({len(tests)} file(s), e.g. `{project}/{tests[0]}`) never name "
                    f"{', '.join(f'`{n}`' for n in sorted(served_folders))}, where the served code lives: "
                    "they test other code, and their result says nothing about the product. Point them "
                    "at the served code."
                )
        return problems
    except Exception:  # noqa: BLE001 - a check that cannot read the files accuses nothing
        logger.debug("Could not compare the served code with the rest", exc_info=True)
        return []


def sandbox_runner(repo_root: str | Path) -> Runner:
    """Run the harness's own commands: contained and recorded like a stage's.

    The environment is exactly a stage's - the sandbox gives every command a
    free port in `ACCEPTANCE_PORT`, so the smoke test proves the path the
    agents will take. It used to pass the port itself, and a configuration
    that only worked when given one passed the smoke test and failed every run
    an agent started. What differs is only that the guards steering an agent
    away from repeating itself do not apply: the harness's measurements are
    never withheld (see `sandbox._FOR_THE_HARNESS`), and these runs are used by
    the scaffold, the acceptance suite and CI alike.
    """
    from app.tools.sandbox import SandboxExecutor

    def run(argv: Sequence[str], category: str, working_directory: str) -> dict[str, Any]:
        return SandboxExecutor.execute(
            list(argv),
            repo_root=str(repo_root),
            role_name="testing_specialist",
            category=category,
            working_directory=working_directory or None,
            for_the_harness=True,
        )

    return run


def _exit_code(outcome: dict[str, Any]) -> int:
    if "error" in outcome and "returncode" not in outcome:
        return 1
    try:
        return int(str(outcome.get("returncode", "1")).strip() or 1)
    except ValueError:
        return 1


def _tail(outcome: dict[str, Any]) -> str:
    text = "\n".join(
        str(outcome.get(key) or "") for key in ("error", "stdout", "stderr") if outcome.get(key)
    )
    return text[-OUTPUT_TAIL_CHARS:]


_AN_ERROR_LINE = re.compile(r"\berror\b|\bfailed\b|exception", re.I)


def where_it_failed(output: str, limit: int = 1200) -> str:
    """The first line that names an error, the two after it, and the output's last lines.

    A tool's last lines are often its boilerplate. Measured on one run: an
    install failed on "Multiple top-level packages discovered in a flat-layout",
    and the record kept the last 800 characters - which began "...covery." and
    went on through pip's advice and its note that the error came from a
    subprocess - so neither the stage nor the decision record had the cause.
    """
    lines = [line.rstrip() for line in str(output or "").splitlines() if line.strip()]
    if not lines:
        return ""
    # The most telling of the lines that name an error, by length: a tool's
    # generic ones ("subprocess-exited-with-error", "finished with status
    # 'error'") are short, and the one that says what went wrong is not.
    named = [i for i, line in enumerate(lines) if _AN_ERROR_LINE.search(line)]
    tail = lines[-6:]
    first = max(named, key=lambda i: (len(lines[i]), -i)) if named else None
    if first is None or first >= len(lines) - 6:
        return "\n".join(lines[-12:])[-limit:]
    head = lines[first:first + 3]
    return ("\n".join(head) + "\n...\n" + "\n".join(line for line in tail if line not in head))[:limit]


def _step(steps: list, argv: Sequence[str], outcome: dict[str, Any]) -> int:
    code = _exit_code(outcome)
    steps.append({"command": " ".join(argv), "exit_code": code, "output": _tail(outcome)})
    return code


def _unproven(
    root: Path, pack: StackPack, project: str, title: str, package: str | None, result: ScaffoldResult
) -> ScaffoldResult:
    """`result`, after recording the pack its files came from as not proven.

    The files are on disk, written from this pack, and the run's tests will be
    written for its runners: without a contract the pack's checks of those
    tests were all off. Recorded as not scaffolded, nothing in it is the
    harness's to keep or put back - a setup that failed its own smoke test is
    the agents' to repair. See `contract.scaffolded`.
    """
    try:
        contract.write(root, pack, project, title, package, scaffolded=False)
    except OSError:
        logger.debug("Could not record the unproven scaffold", exc_info=True)
    return result


def already_set_up(project_root: Path, pack: StackPack) -> bool:
    """Whether the project already has this pack's manifest - a seeded codebase."""
    manifests = [name for name in pack.files if "/" not in name and name in {
        "package.json", "pyproject.toml", "requirements.txt", "go.mod", "Cargo.toml",
    }]
    return any((project_root / name).exists() for name in manifests)


def scaffold(
    repo_root: str | Path,
    pack: StackPack,
    project: str,
    title: str,
    *,
    run: Runner | None = None,
    package: str | None = None,
) -> ScaffoldResult:
    """Scaffold `pack` into `<repo_root>/<project>` and prove it works.

    `package` is the importable name the brief gives the product, when it
    gives one (`app.stacks.stated_module`); otherwise it is derived from the
    project directory's name.
    """
    root = Path(repo_root)
    project_root = root / project
    result = ScaffoldResult(ok=False, pack=pack.name, project=project)
    if already_set_up(project_root, pack):
        result.problem = f"{project}/ already has a project manifest; it is built on as it is."
        return result
    run = run or sandbox_runner(root)

    project_root.mkdir(parents=True, exist_ok=True)
    for relative, content in pack.render(project, title, package).items():
        target = project_root / relative
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    # Recorded before the first command, as not yet proven: the sandbox reads
    # the pack's needs from it (`sandbox._process_memory`), and a toolchain
    # that needs more than every pack gets failed its own smoke test without.
    _unproven(root, pack, project, title, package, result)

    for argv in pack.commands(project, package)["install"]:
        code = _step(result.steps, argv, run(argv, "install", project))
        if code != 0:
            # One retry: a registry hiccup is the commonest cause, and it passes.
            code = _step(result.steps, argv, run(argv, "install", project))
        if code != 0:
            result.problem = f"`{' '.join(argv)}` failed in {project}/."
            return _unproven(root, pack, project, title, package, result)
    from app.stacks import contract as _contract

    _contract.installed(root)

    smoke = pack.rendered_smoke_files(project, title, package)
    for relative, content in smoke.items():
        target = project_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    try:
        commands = pack.commands(project, package)
        for label, argv, report in (
            ("unit", commands["unit_test"], pack.unit_report),
            ("acceptance", commands["acceptance_test"], pack.acceptance_report),
        ):
            junit.clear(project_root / report)
            code = _step(result.steps, argv, run(argv, "test", project))
            parsed = junit.read(project_root / report)
            if code != 0 or not parsed.found or parsed.passed < 1 or parsed.failed:
                # One retry, as for the install. Measured on one run, started a
                # minute after the worker was recreated: the acceptance smoke
                # test failed once (0 passed, 1 failed) on a pack every other
                # run proves, the scaffold was left to the agents, and its
                # files stayed with no contract behind them - "the harness
                # keeps this" in their own comments, and nothing kept them. A
                # later sprint's tester then switched the next sprint's tests
                # off in the runner configuration, and nothing put it back.
                junit.clear(project_root / report)
                code = _step(result.steps, argv, run(argv, "test", project))
                parsed = junit.read(project_root / report)
            if code != 0 or not parsed.found or parsed.passed < 1 or parsed.failed:
                result.problem = (
                    f"The {label} smoke test did not pass through `{' '.join(argv)}` "
                    f"(exit {code}, {parsed.passed} passed, {parsed.failed} failed, "
                    f"report {'found' if parsed.found else 'missing'})."
                )
                return _unproven(root, pack, project, title, package, result)
    finally:
        for relative in smoke:
            (project_root / relative).unlink(missing_ok=True)
        for report in (pack.unit_report, pack.acceptance_report, pack.runtime_report):
            if report:
                junit.clear(project_root / report)
        if pack.evidence_dir:
            shutil.rmtree(project_root / pack.evidence_dir, ignore_errors=True)

    contract.write(root, pack, project, title, package)
    try:
        from app.tools.version_control import commit_all

        commit_all(root, f"Scaffold: {pack.title}")
    except Exception:  # noqa: BLE001 - history is a convenience, not the scaffold
        logger.debug("Could not commit the scaffold", exc_info=True)
    result.ok = True
    return result
