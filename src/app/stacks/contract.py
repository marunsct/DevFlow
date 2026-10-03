"""The project contract: which pack a run's project was scaffolded from.

Written once, by the scaffold, to `.harness/stack-pack.json` in the workspace -
a directory the agents never see. Every later stage reads it to learn the
commands the harness will run, where the reports land and which files the
harness keeps as set up; `enforce` puts those files back when a stage changed
them.

Putting back rather than refusing: a refusal costs the model a turn and teaches
it nothing it can use, and the configuration is not its to change - the same
commands have to keep meaning the same thing for the harness's own test runs
to mean anything.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.stacks import StackPack, pack_named

logger = logging.getLogger(__name__)

#: The harness's own directory in a workspace. Hidden from agents (see
#: `repository.HARNESS_DIRECTORIES`) and kept out of the run's git history.
HARNESS_DIR = ".harness"
CONTRACT_FILE = f"{HARNESS_DIR}/stack-pack.json"


def write(
    repo_root: str | Path, pack: StackPack, project: str, title: str, package: str | None = None
) -> None:
    """Record the pack this run's project was scaffolded from."""
    from app.stacks import python_package_name

    path = Path(repo_root) / CONTRACT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "pack": pack.name,
        "project": project,
        "title": title,
        "package": package or python_package_name(project),
        **pack.commands(project, package),
        "unit_report": pack.unit_report,
        "acceptance_report": pack.acceptance_report,
        "unit_dir": pack.unit_dir,
        "acceptance_dir": pack.acceptance_dir,
        "unit_pattern": pack.unit_pattern,
        "acceptance_pattern": pack.acceptance_pattern,
        "evidence_dir": pack.evidence_dir,
    }
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def read(repo_root: str | Path | None) -> dict[str, Any] | None:
    """The recorded contract, or None for a run no pack scaffolded."""
    if not repo_root:
        return None
    try:
        record = json.loads((Path(repo_root) / CONTRACT_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) and record.get("pack") else None


def the_pack(repo_root: str | Path | None) -> tuple[StackPack, dict[str, Any]] | None:
    """The pack and its recorded contract, or None."""
    record = read(repo_root)
    if record is None:
        return None
    pack = pack_named(record.get("pack"))
    if pack is None:
        return None
    return pack, record


def enforce(repo_root: str | Path) -> list[str]:
    """Put back any runner configuration or manifest script a stage changed.

    Returns one line per repair, for the log and for the next stage's brief.
    A project no pack scaffolded is left alone.
    """
    found = the_pack(repo_root)
    if found is None:
        return []
    pack, record = found
    project = str(record.get("project") or "")
    title = str(record.get("title") or project)
    root = Path(repo_root) / project
    if not root.is_dir():
        return []
    rendered = pack.render(project, title, record.get("package"))
    repairs: list[str] = []
    for relative in pack.kept_files:
        wanted = rendered.get(relative)
        if wanted is None:
            continue
        target = root / relative
        try:
            current = target.read_text(encoding="utf-8")
        except OSError:
            current = None
        if current != wanted:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(wanted, encoding="utf-8")
            repairs.append(
                f"{project}/{relative} was {'missing' if current is None else 'changed'}; "
                "it is the harness's test configuration and has been put back."
            )
    if pack.kept_scripts:
        repairs.extend(_put_back_the_scripts(root, project, pack))
    if repairs:
        logger.warning("Project contract repaired: %s", "; ".join(repairs))
    return repairs


def _put_back_the_scripts(root: Path, project: str, pack: StackPack) -> list[str]:
    manifest = root / "package.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # A manifest that does not parse is the product's defect, and the
        # cross-file checks name it; rewriting it here would hide whatever else
        # the stage put in it.
        return []
    if not isinstance(data, dict):
        return []
    scripts = data.get("scripts")
    if not isinstance(scripts, dict):
        scripts = {}
    changed = [name for name, command in pack.kept_scripts.items() if scripts.get(name) != command]
    if not changed:
        return []
    scripts.update(pack.kept_scripts)
    data["scripts"] = scripts
    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return [
        f"{project}/package.json script(s) {', '.join(repr(name) for name in changed)} "
        "were changed; the harness runs them and has put them back."
    ]


def describe(repo_root: str | Path | None) -> str:
    """The contract as a block for every stage that writes code or tests."""
    found = the_pack(repo_root)
    if found is None:
        return ""
    pack, record = found
    project = record.get("project") or ""

    def shown(argv: Any) -> str:
        return " ".join(str(part) for part in (argv or []))

    kept = ", ".join(f"`{project}/{name}`" for name in pack.kept_files)
    scripts = ", ".join(f"`{name}`" for name in pack.kept_scripts)
    return (
        "--- Project setup (already done; the harness owns it) ---\n"
        f"`{project}/` was scaffolded as: {pack.title}. Its tests already run.\n"
        f"- Unit tests: `{project}/{pack.unit_dir}/`, files named `{pack.unit_pattern}`; "
        f"run with `{shown(record.get('unit_test'))}` in `{project}/`.\n"
        f"- Acceptance tests: `{project}/{pack.acceptance_dir}/` belongs to QA and is locked; "
        "nothing else may change it. The harness runs it and reports which criteria pass.\n"
        f"- Kept by the harness: {kept}"
        + (f", and the manifest scripts {scripts}" if scripts else "")
        + ". They are test setup, not the product: do not change them, test them, run them "
        "yourself or build on them - one run's stage wrote a unit test that started the "
        "harness's server and hung for five minutes. Add dependencies the normal way; "
        "everything else in the project is yours.\n"
        f"{pack.filled(pack.guide, project, record.get('title') or project, record.get('package'))}\n\n"
    )
