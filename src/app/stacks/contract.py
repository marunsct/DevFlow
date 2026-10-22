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
import re
import logging
from pathlib import Path, PurePosixPath
from typing import Any

from app.stacks import StackPack, pack_named

logger = logging.getLogger(__name__)

#: The harness's own directory in a workspace. Hidden from agents (see
#: `repository.HARNESS_DIRECTORIES`) and kept out of the run's git history.
HARNESS_DIR = ".harness"
CONTRACT_FILE = f"{HARNESS_DIR}/stack-pack.json"
#: The project's dependency manifests as last installed. See `install_if_the_manifests_changed`.
INSTALLED_FILE = f"{HARNESS_DIR}/installed.json"


def write(
    repo_root: str | Path,
    pack: StackPack,
    project: str,
    title: str,
    package: str | None = None,
    *,
    scaffolded: bool = True,
    extra: dict[str, Any] | None = None,
) -> None:
    """Record the pack this run's project was built from.

    `scaffolded` is False when the run chose the pack and its scaffold could
    not be proven: see `scaffolded()`. `extra` is recorded beside the rest - a
    proven setup's own description (`app.stacks.custom_setup`).
    """
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
        "scaffolded": scaffolded,
        **(extra or {}),
    }
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def _the_manifests(repo_root: str | Path, project: str) -> str:
    """A digest of the project's dependency manifests as they are now."""
    import hashlib

    from app.tools.repository import PACKAGE_MANIFESTS

    folder = Path(repo_root) / project
    digest = hashlib.sha256()
    for name in sorted(PACKAGE_MANIFESTS):
        path = folder / name
        try:
            content = path.read_bytes() if path.is_file() else b""
        except OSError:
            content = b""
        if content:
            digest.update(name.encode() + b"\0" + content + b"\0")
    return digest.hexdigest()


def installed(repo_root: str | Path, runner: Any = None) -> None:  # noqa: ARG001 - the same shape as the installer
    """Record the manifests as installed now: the scaffold calls it after its own install. Never raises."""
    try:
        record = read(repo_root)
        if record is None:
            return
        path = Path(repo_root) / INSTALLED_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"manifests": _the_manifests(repo_root, str(record.get("project") or ""))}) + "\n",
                        encoding="utf-8")
    except Exception:  # noqa: BLE001 - the next measurement installs once more
        logger.debug("Could not record the install", exc_info=True)


#: How a failed install's note reads after its command, so the round can find it.
INSTALL_FAILED = "failed after the project's manifest changed"


def install_if_the_manifests_changed(repo_root: str | Path, runner: Any = None) -> list[str]:
    """Install the project's dependencies again when a manifest changed since the last install. Never raises.

    Measured live: fast delivery drafted `package.json` with a router in it, in
    one model call with no command after it, and nothing installed it; every
    test round built the page against the scaffold's `node_modules`, the build
    failed to resolve the import, and the product "did not start" round after
    round while its manifest was right. Run before each of the harness's own
    measurements; a failed install is tried again at the next one.
    """
    try:
        record = read(repo_root)
        commands = [list(argv) for argv in (record or {}).get("install") or []]
        if record is None or not commands:
            return []
        project = str(record.get("project") or "")
        now = _the_manifests(repo_root, project)
        try:
            kept = json.loads((Path(repo_root) / INSTALLED_FILE).read_text(encoding="utf-8")).get("manifests")
        except (OSError, ValueError, AttributeError):
            kept = None
        if kept == now:
            return []
        if runner is None:
            from app.stacks.scaffold import sandbox_runner

            runner = sandbox_runner(repo_root)
        for argv in commands:
            outcome = runner(argv, "install", project) or {}
            code = str(outcome.get("returncode", outcome.get("exit_code", "0")))
            if code not in ("0", "None", ""):
                said = (str(outcome.get("stderr") or "") + "\n" + str(outcome.get("stdout") or "")).strip()
                tail = "\n".join(line for line in said.splitlines() if line.strip())[-600:]
                logger.warning("A changed manifest could not be installed: `%s` exited %s: %s",
                               " ".join(argv), code, tail[-200:].replace("\n", " | "))
                # What the installer said: measured on one gate run, a JavaScript
                # package written into `requirements.txt` failed every install,
                # and the note said only that the command failed.
                return [f"`{' '.join(argv)}` {INSTALL_FAILED}"
                        + (f"; it ended:\n{tail}" if tail else ".")]
        installed(repo_root)
        logger.info("The project's manifest changed since its last install; installed again")
        return ["The project's dependencies were installed again: a manifest changed since the last install."]
    except Exception:  # noqa: BLE001 - the measurement goes on as it would have
        logger.debug("Could not check the project's install", exc_info=True)
        return []


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
    """The pack and its recorded contract, or None. Only ever reads.

    It once guessed a pack when no contract was written, from the words of the
    stack decision and the stack document, and wrote its guess down. Measured
    on two runs whose stack decision said no pack fits: one was given a
    JavaScript service's contract because its stack document explained why a
    JavaScript option was rejected, the other a Python service's for a product
    with a browser interface - and every suite run then wrote that pack's
    runner configuration into the project. Which pack a run was built from is
    the stack decision's to say, and only the scaffold writes it down.
    """
    record = read(repo_root)
    if record is None:
        return None
    pack = pack_named(record.get("pack"))
    if pack is None:
        # A stack no pack covers, set up by an agent and proven like a pack.
        from app.stacks.custom_setup import pack_from

        pack = pack_from(record)
    if pack is None:
        return None
    return pack, record


def scaffolded(record: dict[str, Any] | None) -> bool:
    """Whether the harness set this contract's project up and proved it.

    False for a pack the run chose whose scaffold could not be proven: its
    linters and commands still apply, but no file is the harness's to keep -
    a setup that failed its own smoke test is the agents' to repair.
    """
    return bool(record) and record.get("scaffolded", True) is not False


def the_pack_above(path: str | Path | None) -> tuple[StackPack, dict[str, Any]] | None:
    """The pack that scaffolded the workspace `path` sits in, or None."""
    if not path:
        return None
    for folder in Path(path).resolve().parents:
        if (folder / CONTRACT_FILE).is_file():
            return the_pack(folder)
    return None


def kept_paths(repo_root: str | Path | None) -> frozenset[str]:
    """Workspace-relative paths of the files the harness keeps as set up."""
    found = the_pack(repo_root)
    if found is None or not scaffolded(found[1]):
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
    kept = kept_paths(repo_root)
    if path in kept or _another_spelling_of_a_kept(path, kept):
        return KEPT_SETUP
    try:
        from app.acceptance import suite

        if suite.is_protected(repo_root, path):
            return LOCKED_SUITE
    except Exception:  # noqa: BLE001 - an unreadable lock protects nothing
        logger.debug("Could not read the acceptance lock", exc_info=True)
    return ""


def _what_the_last_runs_said(repo_root: Path, record: dict[str, Any]) -> str:
    """The latest suite result and both test reports, as text."""
    project = Path(repo_root) / str(record.get("project") or "")
    texts = []
    for path in (
        Path(repo_root) / HARNESS_DIR / "acceptance-result.json",
        project / str(record.get("acceptance_report") or ""),
        project / str(record.get("unit_report") or ""),
    ):
        try:
            if path.is_file():
                texts.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\n".join(texts)


def released_because_it_fails(repo_root: str | Path | None, relative_path: str) -> bool:
    """Releases a proven setup's kept file the latest runs report an error in; whether it did.

    A setup is proven by its smoke tests passing, and a kept file those tests
    never read is kept unproven. One run's setup kept a `tsconfig.json` whose
    `lib` was a string where the compiler wants a list; the smoke tests ran
    without compiling, the build failed on it from then on, and every fix that
    reached for it was refused as "already works". A kept file the runs name
    in an error is the setup's defect, and the team's to fix: it is no longer
    kept, so it is not put back either. A stack pack's own files are verified
    packs and stay kept.
    """
    if not repo_root:
        return False
    record = read(repo_root)
    setup = (record or {}).get("setup")
    if not record or not isinstance(setup, dict) or not isinstance(setup.get("kept"), dict):
        return False
    project = str(record.get("project") or "")
    path = str(relative_path or "").strip().lstrip("/")
    name = path[len(project) + 1:] if project and path.startswith(project + "/") else path
    if name not in setup["kept"]:
        return False
    said = _what_the_last_runs_said(Path(repo_root), record)
    base = re.escape(PurePosixPath(name).name)
    if not re.search(rf"{base}(?:\(\d+,\d+\)|:\d+(?::\d+)?):?\s*(?:error|Error|ERROR)", said):
        return False
    setup["kept"].pop(name)
    (Path(repo_root) / CONTRACT_FILE).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    logger.warning("%s is reported in an error by the latest runs; released from the kept setup to be fixed", path)
    return True


def _another_spelling_of_a_kept(relative: str, kept: Any) -> str:
    """The kept file `relative` is another spelling of - same folder and name, another extension; else ""."""
    path = PurePosixPath(relative)
    stem = path.name.rsplit(".", 1)[0] if "." in path.name else ""
    if not stem or "." not in stem:
        # Only a name with a kind before its extension (`playwright.config`,
        # `vite.config`): `index.js` and `index.css` are two different files.
        return ""
    for name in kept:
        other = PurePosixPath(str(name))
        if other != path and other.parent == path.parent and other.name.rsplit(".", 1)[0] == stem:
            return str(name)
    return ""


def _the_files_that_shadow(root: Path, relative: str) -> list[Path]:
    """Files beside the kept `relative` with its name and another extension."""
    path = PurePosixPath(relative)
    folder = root / str(path.parent)
    if not folder.is_dir():
        return []
    return [
        candidate for candidate in sorted(folder.iterdir())
        if candidate.is_file() and candidate.name != path.name
        and _another_spelling_of_a_kept(str(PurePosixPath(str(path.parent)) / candidate.name).lstrip("./"), [relative])
    ]


def enforce(repo_root: str | Path) -> list[str]:
    """Put back any runner configuration or manifest script a stage changed.

    Returns one line per repair, for the log and for the next stage's brief.
    A project no pack scaffolded is left alone, and so is one whose scaffold
    could not be proven: its setup is the agents' to repair.
    """
    found = the_pack(repo_root)
    if found is None or not scaffolded(found[1]):
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
    for relative in pack.kept_files:
        for shadow in _the_files_that_shadow(root, relative):
            # Another spelling of a kept file is read in its place: measured on
            # one gate run, a drafted `playwright.config.ts` beside the kept
            # `playwright.config.js` was the one Playwright loaded - no base
            # URL, no report - and every test failed "Invalid URL" with the
            # harness counting none of them.
            shadow.unlink(missing_ok=True)
            repairs.append(
                f"{project}/{shadow.relative_to(root).as_posix()} was read in place of the harness's "
                f"{project}/{relative}; it has been removed - the harness's configuration is the one that runs."
            )
    if pack.kept_scripts:
        repairs.extend(_put_back_the_scripts(root, project, pack))
    repairs.extend(_put_back_the_toolchain(root, project, pack, rendered))
    if repairs:
        logger.warning("Project contract repaired: %s", "; ".join(repairs))
    return repairs


#: A package a file imports: `from 'x'`, `import 'x'`, `import('x')`, `require('x')`.
_IMPORTED = re.compile(r"""(?:\bfrom\s+|\bimport\s*\(?\s*|\brequire\s*\(\s*)['"]([^'"./][^'"]*)['"]""")


def _the_package(specifier: str) -> str:
    parts = specifier.split("/")
    return "/".join(parts[:2]) if specifier.startswith("@") else parts[0]


def _put_back_the_toolchain(root: Path, project: str, pack: StackPack, rendered: dict[str, str]) -> list[str]:
    """Put back the pack's version of every package the harness's own kept files import.

    Measured live: a drafted manifest pinned `@playwright/test` 1.45.0, `vite`
    5.4.2 and `vitest` 2.0.0 over the scaffold's 1.64.0, ^7 and ^3.2; once it
    was installed, Playwright 1.45 hung under the runtime here and every
    acceptance run timed out with no output. The kept files were written for
    the pack's versions, as its scripts were. The product's own packages are
    left as they are.
    """
    try:
        wanted_manifest = json.loads(rendered.get("package.json") or "")
        manifest = root / "package.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict) or not isinstance(wanted_manifest, dict):
        return []
    imported = {
        _the_package(found)
        for relative in pack.kept_files
        for found in _IMPORTED.findall(rendered.get(relative) or "")
    }
    sections = ("dependencies", "devDependencies")
    changed: list[str] = []
    for section in sections:
        for name, version in (wanted_manifest.get(section) or {}).items():
            if name not in imported:
                continue
            here = next((s for s in sections if name in (data.get(s) or {})), None)
            if here == section and data[section][name] == version:
                continue
            if here is not None and here != section:
                del data[here][name]
            data.setdefault(section, {})[name] = version
            changed.append(f"{name} {version}")
    if not changed:
        return []
    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return [
        f"{project}/package.json had changed the toolchain the harness's own files import; put back "
        + ", ".join(changed) + "."
    ]


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


def _where_dependencies_go(project: str, record: dict[str, Any]) -> str:
    """Where this project's install reads its dependencies from, said once for every stage that writes code.

    "Add dependencies the normal way" left the choice to the model, and a
    Python project has two normal ways: measured on five gate runs in a row,
    drafting declared its packages in `pyproject.toml` while the pack's
    install read only `requirements.txt`, and the product did not start until
    a fix round moved them.
    """
    installs = [[str(part) for part in argv] for argv in record.get("install") or [] if argv]
    files: list[str] = []
    for argv in installs:
        for index, arg in enumerate(argv):
            if arg in ("-r", "--requirement") and index + 1 < len(argv):
                files.append(argv[index + 1])
    javascript = any(argv and argv[0] in ("npm", "pnpm", "yarn", "bun") for argv in installs)
    if files:
        named = " and ".join(f"`{project}/{name}`" if project else f"`{name}`" for name in dict.fromkeys(files))
        return (f"Declare every Python package the code imports in {named} - the install reads only "
                f"{'these' if len(files) > 1 else 'this'}, so a package listed anywhere else (a "
                "`pyproject.toml` included) is never installed; a test-only tool goes in the "
                "development file where there is one."
                + (" JavaScript packages go in `package.json`, which the install's `npm install` reads."
                   if javascript else ""))
    if installs:
        shown_install = " && ".join(" ".join(argv) for argv in installs)
        return (f"Declare every package the code imports in the manifest this install reads "
                f"(`{shown_install}`), in the same change that imports it.")
    return "Declare every package the code imports in the project's manifest, in the same change that imports it."


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
        "harness's server and hung for five minutes. "
        + _where_dependencies_go(project, record)
        + " Everything else in the project is yours.\n"
        f"{pack.filled(pack.guide, project, record.get('title') or project, record.get('package'))}\n\n"
    )
