"""What a release adds so someone who did not write the product can run and ship it.

A software company does not hand over a working tree and stop. It hands over
something another engineer can test and deploy without asking how: a CI
pipeline, and for a service, a container definition.

Both come from the stack pack, because the pack is the one place that knows
how this product installs, starts and is tested - and the CI pipeline runs
exactly the commands the harness ran, through `StackPack.commands`, so it
cannot describe a build nobody has seen pass. The generators this replaces
(`app/deploy`, removed) kept a second model of every stack beside the packs,
with its own guesses at entry points and test commands, and were never wired
in (ADR-0004 supersedes ADR-0003).

Written at the release stage, once the suite passes: never over a file the
product already has - a team that wrote its own pipeline or container keeps
it - and committed, so the release names exactly what it added. Nothing here
can build a container (the sandbox has no container runtime), and the release
record says so rather than implying it was proven.
"""

from __future__ import annotations

import json
import logging
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from app.stacks import StackPack
from app.stacks import contract

logger = logging.getLogger(__name__)

#: Where the CI workflow lands, relative to the workspace root: the root of the
#: repository the product is delivered in.
CI_WORKFLOW = ".github/workflows/{project}.yml"


def _run(command: str, indent: str = "      ") -> str:
    # JSON strings are YAML double-quoted scalars, so no command can break the file.
    return f"{indent}- run: {json.dumps(command)}"


def ci_workflow(pack: StackPack, project: str, title: str, package: str | None = None) -> str:
    """A CI pipeline that installs the product and runs its own two suites."""
    commands = pack.commands(project, package)
    lines = [
        f"# {title}: the commands the harness ran, run on every push.",
        f"name: {json.dumps(f'{title or project} CI')}",
        "on:",
        "  push:",
        "  pull_request:",
        "jobs:",
        "  test:",
        "    runs-on: ubuntu-latest",
        "    defaults:",
        "      run:",
        f"        working-directory: {json.dumps(project)}",
        "    steps:",
        "      - uses: actions/checkout@v4",
        *[step.rstrip("\n") for step in pack.ci_setup],
        *[_run(shlex.join(argv)) for argv in commands["install"]],
        *[_run(command) for command in pack.ci_prepare],
        _run(shlex.join(commands["unit_test"])),
        _run(shlex.join(commands["acceptance_test"])),
    ]
    return "\n".join(lines) + "\n"


def files_for(pack: StackPack, project: str, title: str, package: str | None = None) -> dict[str, str]:
    """Workspace-relative path -> content of everything a release of this pack adds."""
    files = {CI_WORKFLOW.format(project=project): ci_workflow(pack, project, title, package)}
    for relative, content in pack.render_release_files(project, title, package).items():
        files[f"{project}/{relative}" if project else relative] = content
    return files


@dataclass
class ReleaseFiles:
    written: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    #: Why the handoff has no release files, when it has none it should. Said
    #: in the release record: a release that silently lacks its CI pipeline
    #: reads exactly like one that has it.
    missing: str = ""
    #: True only when no pack covers the product: it was never promised release
    #: files, and its support tier says so already (Initiative AG).
    no_pack: bool = False

    @property
    def a_gap(self) -> str:
        """What the handoff lacks that its stack pack promised, or "" (Initiative BK)."""
        return self.missing if self.missing and not self.no_pack else ""

    def describe(self) -> str:
        if self.missing:
            return self.missing
        if not self.written and not self.kept:
            return ""
        parts = []
        if self.written:
            parts.append("Release files added from the stack pack: " + ", ".join(self.written) + ".")
        if self.kept:
            parts.append("The product's own " + ", ".join(self.kept) + " kept as written.")
        parts.append(
            "The CI pipeline runs the commands the harness ran; a container definition is "
            "written, not built here - the sandbox has no container runtime."
        )
        return " ".join(parts)


def write(repo_root: str | Path) -> ReleaseFiles:
    """Add the pack's release files to the workspace and commit them. Never raises."""
    outcome = ReleaseFiles()
    try:
        found = contract.the_pack(repo_root)
        if found is None:
            outcome.no_pack = True
            outcome.missing = (
                "No stack pack covers this product, so the release adds no CI pipeline or "
                "container definition: the handoff carries only what the agents wrote, and "
                "how to install, test and deploy it is not packaged."
            )
            return outcome
        pack, record = found
        project = str(record.get("project") or "")
        title = str(record.get("title") or project)
        root = Path(repo_root)
        for relative, content in files_for(pack, project, title, record.get("package")).items():
            target = root / relative
            if target.exists():
                # Ours from an earlier release (after a change request, say)
                # is not news; anything else is the product's own and stays.
                if target.read_text(encoding="utf-8", errors="replace") != content:
                    outcome.kept.append(relative)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            outcome.written.append(relative)
        if outcome.written:
            from app.tools.version_control import commit_all

            commit_all(root, f"Release: CI and deployment files from the {pack.title} pack")
    except Exception as error:  # noqa: BLE001 - a release is not held back by its packaging
        logger.warning("Could not add the release files", exc_info=True)
        outcome.missing = (
            f"Adding the release files failed ({type(error).__name__}: {str(error)[:200]}), so "
            + (f"only {', '.join(outcome.written)} were added and " if outcome.written else "")
            + "the handoff lacks the CI pipeline or container definition its stack pack provides."
        )
    return outcome


__all__ = ["CI_WORKFLOW", "ReleaseFiles", "ci_workflow", "files_for", "write"]
