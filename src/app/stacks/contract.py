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
    if record is not None:
        pack = pack_named(record.get("pack"))
        if pack is not None:
            return pack, record
    return _infer_contract(repo_root)


def _infer_contract(repo_root: str | Path | None) -> tuple[StackPack, dict[str, Any]] | None:
    """Infer the pack and contract when CONTRACT_FILE was not written.

    If a scaffold failed its smoke test or was left to the agents, CONTRACT_FILE
    was not written. Every later stage (kept-file protections, QA locator and
    assertion linters, runtime reports, failure pages) relies on the pack.
    Inferring the pack from decisions or the technology stack document ensures
    the harness still protects kept files and lints acceptance tests.
    """
    if not repo_root:
        return None
    root = Path(repo_root)
    if not root.is_dir():
        return None

    from app.stacks.packs import ALL_PACKS
    from app.tools.repository import pinned_project_directory

    pack: StackPack | None = None

    # 1. From .harness/decisions.json (DR-1 or point == "stack")
    decisions_path = root / HARNESS_DIR / "decisions.json"
    if decisions_path.is_file():
        try:
            decisions_data = json.loads(decisions_path.read_text(encoding="utf-8"))
            if isinstance(decisions_data, list):
                for item in decisions_data:
                    if isinstance(item, dict) and item.get("point") == "stack":
                        rationale = str(item.get("rationale") or "")
                        options = [str(o) for o in (item.get("options") or [])]
                        decision = str(item.get("decision") or "")
                        for p in ALL_PACKS:
                            if p.name in rationale or p.title in options or p.title in decision:
                                pack = p
                                break
                    if pack is not None:
                        break
        except (OSError, ValueError):
            pass

    # 2. From docs/technology_stack.md
    if pack is None:
        tech_path = root / "docs" / "technology_stack.md"
        if tech_path.is_file():
            try:
                content = tech_path.read_text(encoding="utf-8")
                for p in ALL_PACKS:
                    if p.title in content or p.name in content:
                        pack = p
                        break
            except OSError:
                pass

    if pack is None:
        return None

    project = pinned_project_directory(root) or ""
    if not project:
        from app.tools.repository import _NON_PROJECT_DIRECTORIES, IGNORED_DIRECTORIES

        for child in sorted(root.iterdir()):
            if (
                child.is_dir()
                and not child.name.startswith(".")
                and child.name not in _NON_PROJECT_DIRECTORIES
                and child.name not in IGNORED_DIRECTORIES
                and (
                    (child / "package.json").is_file()
                    or (child / "pyproject.toml").is_file()
                    or (child / "go.mod").is_file()
                )
            ):
                project = child.name
                break

    from app.stacks import python_package_name

    title = project.replace("-", " ").replace("_", " ").title() if project else pack.title
    package = python_package_name(project) if pack.language == "python" else None
    record = {
        "pack": pack.name,
        "project": project,
        "title": title,
        "package": package or (python_package_name(project) if project else None),
        **pack.commands(project, package),
        "unit_report": pack.unit_report,
        "acceptance_report": pack.acceptance_report,
        "unit_dir": pack.unit_dir,
        "acceptance_dir": pack.acceptance_dir,
        "unit_pattern": pack.unit_pattern,
        "acceptance_pattern": pack.acceptance_pattern,
        "evidence_dir": pack.evidence_dir,
    }
    try:
        (root / CONTRACT_FILE).parent.mkdir(parents=True, exist_ok=True)
        (root / CONTRACT_FILE).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
    return pack, record


def the_pack_above(path: str | Path | None) -> tuple[StackPack, dict[str, Any]] | None:
    """The pack that scaffolded the workspace `path` sits in, or None."""
    if not path:
        return None
    for folder in Path(path).resolve().parents:
        if (folder / CONTRACT_FILE).is_file() or (folder / "docs" / "technology_stack.md").is_file():
            found = the_pack(folder)
            if found is not None:
                return found
    return None


def kept_paths(repo_root: str | Path | None) -> frozenset[str]:
    """Workspace-relative paths of the files the harness keeps as set up."""
    found = the_pack(repo_root)
    if found is None:
        return frozenset()
    pack, record = found
    project = str(record.get("project") or "")
    return frozenset(f"{project}/{name}" if project else name for name in pack.kept_files)


#: What `owned_by_the_harness` answers, one phrase per owner.
HARNESS_RECORDS = "the harness's own records"
KEPT_SETUP = "test setup the harness keeps"
LOCKED_SUITE = "the locked acceptance suite"


def owned_by_the_harness(repo_root: str | Path | None, relative_path: str) -> str:
    """Who owns this workspace-relative path when the team does not, or "".

    The one answer to the question, for every place that asks it: the write
    guards that refuse a change, the definition of ready that refuses a work
    order, and the digest that tells a stage what is there. Three copies of
    this set would drift the way every duplicated rule in this harness has.
    """
    path = str(relative_path or "").strip().lstrip("/").replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    if not path or not repo_root:
        return ""
    if path == HARNESS_DIR or path.startswith(HARNESS_DIR + "/"):
        return HARNESS_RECORDS
    if path in kept_paths(repo_root):
        return KEPT_SETUP
    try:
        from app.acceptance import suite

        if suite.is_protected(repo_root, path):
            return LOCKED_SUITE
    except Exception:  # noqa: BLE001 - an unreadable lock protects nothing
        logger.debug("Could not read the acceptance lock", exc_info=True)
    return ""


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
