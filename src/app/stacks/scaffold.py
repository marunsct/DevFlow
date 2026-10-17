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
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from app.acceptance import junit
from app.stacks import StackPack
from app.stacks import contract

logger = logging.getLogger(__name__)

#: How much of a failing command's output a result keeps.
OUTPUT_TAIL_CHARS = 2_000

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
    entrypoint = str(getattr(pack, "entrypoint", "") or "") if pack else ""
    if not entrypoint or entrypoint in (getattr(pack, "kept_files", ()) or ()):
        return None
    try:
        project = str(record.get("project") or "")
        rendered = pack.render(
            project,
            str(record.get("title") or ""),
            str(record.get("package") or "") or None,
        ).get(entrypoint)
        if rendered is None:
            return None
        current = (Path(repo_root) / project / entrypoint).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    return f"{project}/{entrypoint}" if current == rendered else None



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
