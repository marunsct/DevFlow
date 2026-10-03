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


def sandbox_runner(repo_root: str | Path) -> Runner:
    """Run commands the way every other harness command runs: contained and recorded."""
    from app.tools.sandbox import SandboxExecutor

    def run(argv: Sequence[str], category: str, working_directory: str) -> dict[str, Any]:
        return SandboxExecutor.execute(
            list(argv),
            repo_root=str(repo_root),
            role_name="testing_specialist",
            category=category,
            working_directory=working_directory or None,
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

    for argv in pack.commands(project, package)["install"]:
        code = _step(result.steps, argv, run(argv, "install", project))
        if code != 0:
            # One retry: a registry hiccup is the commonest cause, and it passes.
            code = _step(result.steps, argv, run(argv, "install", project))
        if code != 0:
            result.problem = f"`{' '.join(argv)}` failed in {project}/."
            return result

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
            (project_root / report).unlink(missing_ok=True)
            code = _step(result.steps, argv, run(argv, "test", project))
            parsed = junit.read(project_root / report)
            if code != 0 or not parsed.found or parsed.passed < 1 or parsed.failed:
                result.problem = (
                    f"The {label} smoke test did not pass through `{' '.join(argv)}` "
                    f"(exit {code}, {parsed.passed} passed, {parsed.failed} failed, "
                    f"report {'found' if parsed.found else 'missing'})."
                )
                return result
    finally:
        for relative in smoke:
            (project_root / relative).unlink(missing_ok=True)
        for report in (pack.unit_report, pack.acceptance_report):
            (project_root / report).unlink(missing_ok=True)
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
