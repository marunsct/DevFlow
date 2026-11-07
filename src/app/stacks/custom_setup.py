"""A stack no pack covers, set up by an agent and proven by the harness.

A pack is a setup known to work: files, an install and two smoke tests run
through the commands every later stage uses. A stack with no pack (Nuxt,
SvelteKit, Ktor, Quarkus ...) used to start with no setup at all, and its
runners were set up piecemeal by whichever stage needed one first - the
setting where 63% of measured defects were about tests and their setup.

Here a setup stage creates the project with the framework's own generator,
adds a unit runner and an acceptance runner that write JUnit XML and one smoke
test for each, and declares it all in `<project>/stack-setup.json`. The harness
then does exactly what it does for a pack: runs the install, runs each smoke
test through the declared command, reads each report. Only a setup that passes
is recorded - as a contract like a pack's, with the runner configuration it
proved kept as it was proven - so every later stage, gate and suite run treats
it the way it treats a pack. One that does not pass is sent back once with what
failed, and then left to the agents as before.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import logging
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any, Sequence

from app.acceptance import junit
from app.stacks import KINDS, StackPack, product_kind
from app.stacks import contract
from app.stacks.scaffold import Runner, ScaffoldResult, _step, sandbox_runner, where_it_failed

logger = logging.getLogger(__name__)

#: The name a proven setup's contract is recorded under.
PROVEN_SETUP = "proven-setup"
#: The file the setup stage writes in the project directory.
DECLARATION_FILE = "stack-setup.json"
#: How many times the setup stage is run before the setup is left to the agents.
ATTEMPTS = 2
#: The longest guide text kept from a declaration.
MAX_GUIDE = 1_500

#: Manifests that mean a project is already set up - a seeded codebase.
_MANIFESTS = (
    "package.json", "pyproject.toml", "requirements.txt", "setup.py", "go.mod", "Cargo.toml",
    "pom.xml", "build.gradle", "build.gradle.kts", "Gemfile", "composer.json", "mix.exs",
    "deno.json",
)

#: How an acceptance test meets each kind of product.
_MEETS = {
    "browser_app": "it opens the page in a real browser and acts on it as a person would",
    "fullstack": "it opens the page in a real browser, served with its own service running",
    "http_api": "it starts the service and sends it HTTP requests",
    "cli": "it runs the built program as a process and reads its output and exit code",
    "library": "it imports the library through its public interface only",
}


def enabled() -> bool:
    import os

    return os.environ.get("CUSTOM_STACK_SETUP", "true").strip().lower() not in {"0", "false", "no", "off"}


#: What a seeded product with no manifest is known to run by. Not stylesheets or headers, which run nothing.
_RUNNABLE_SUFFIXES = frozenset({
    ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".py", ".rb", ".go", ".rs", ".java", ".kt", ".scala", ".swift",
    ".php", ".c", ".cc", ".cpp", ".cs", ".ex", ".exs", ".lua", ".pl", ".sh", ".html", ".htm",
})


def _holds_runnable_code(project_root: Path) -> bool:
    from app.analysis.walk import files_under
    from app.tools.repository import IGNORED_DIRECTORIES

    return any(
        path.suffix.lower() in _RUNNABLE_SUFFIXES
        for path in files_under(project_root, IGNORED_DIRECTORIES, skip_hidden=True)
    )


def already_set_up(project_root: Path) -> bool:
    """Whether the project is built on as it is: it has a manifest, or it is a seeded product with code.

    A product runs without a manifest (a standard-library service and its
    launcher), and the setup stage would spend its calls on a project that
    already works. Only for a seed: the same files in a run that started empty
    are a setup stage's unfinished work. The setup's test commands are then not
    recorded, so the acceptance suite declares its own (`suite.DECLARED_COMMAND_FILE`)
    and installs are the agents', as for a seed with a manifest.
    """
    from app.acceptance.regression_contract import seeded

    return (
        any((project_root / name).exists() for name in _MANIFESTS)
        or any(project_root.glob("*.csproj"))
        or (seeded(project_root.parent) and _holds_runnable_code(project_root))
    )


def _stack_line(stack: Any) -> str:
    parts = [
        f"{label} {value}"
        for label, attribute in (
            ("language", "language"), ("framework", "framework"),
            ("frontend", "frontend_framework"), ("testing", "testing_framework"),
        )
        if (value := str(getattr(stack, attribute, "") or "").strip())
    ]
    return ", ".join(parts) or "the chosen stack"


#: The specification's sections the setup is made to agree with.
_SPECIFICATION_FOR_THE_SETUP = (
    ("file_plan", "Files"), ("testing", "Testing"), ("configuration", "Configuration"),
    ("library_usage", "Library calls"),
)
#: The most of the specification the setup request carries.
MOST_SPECIFICATION_CHARACTERS = 12_000


def what_the_specification_sets_up(specification: Any) -> str:
    """The specification's files, testing, configuration and library calls, as the setup stage reads them."""
    blocks = []
    for field, heading in _SPECIFICATION_FOR_THE_SETUP:
        entries = [str(entry).strip() for entry in getattr(specification, field, None) or [] if str(entry).strip()]
        if entries:
            blocks.append(f"{heading}:\n" + "\n".join(f"- {entry}" for entry in entries))
    text = "\n\n".join(blocks)
    if len(text) > MOST_SPECIFICATION_CHARACTERS:
        text = text[:MOST_SPECIFICATION_CHARACTERS] + "\n... (the rest is in /docs/technical_specification.md)"
    return text


def _a_layer_named(name: Any) -> str:
    """`name` when it is a pack that names its framework files, else "": an unknown layer is a hand-written setup."""
    from app.stacks import pack_named

    pack = pack_named(str(name or ""))
    return pack.name if pack is not None and pack.framework_files else ""


def runner_layer(kind: str, language: str) -> StackPack | None:
    """The pack whose runner layer a stack of `kind` and `language` no pack covers is set up on; None if none has one.

    The first pack of that kind and language that names its framework files (SF.2): its install, test commands,
    report paths and kept test configuration hold for any framework of its language; only those files differ.
    """
    from app.stacks.packs import ALL_PACKS

    kind, language = str(kind or "").strip().lower(), str(language or "").strip().lower()
    if not kind or not language:
        return None
    return next((pack for pack in ALL_PACKS
                 if pack.kind == kind and pack.language == language and pack.framework_files), None)


def write_runner_layer(project_root: Path, pack: StackPack, project: str, title: str) -> dict[str, str]:
    """Write `pack`'s runner layer and the setup's declaration; return the framework files left to write, with their job.

    The layer is every file and smoke test of the pack but its framework's own; the declaration is the pack's own
    commands, report paths, test folders and kept files, so nothing the agent writes can get those wrong (SF.2).
    """
    from app.stacks import python_package_name

    package = python_package_name(project)
    framework = {pack.filled(path, project, title, package): pack.filled(what, project, title, package)
                 for path, what in pack.framework_files.items()}
    for template in (pack.files, pack.smoke_files):
        for path, text in template.items():
            where = pack.filled(path, project, title, package)
            if where in framework:
                continue
            target = project_root / where
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(pack.filled(text, project, title, package), encoding="utf-8")
    commands = pack.commands(project, package)
    declaration = {
        "kind": pack.kind,
        "install": commands["install"],
        "unit_test": commands["unit_test"],
        "unit_report": pack.unit_report,
        "unit_dir": pack.unit_dir,
        "unit_pattern": pack.unit_pattern,
        "acceptance_test": commands["acceptance_test"],
        "acceptance_report": pack.acceptance_report,
        "acceptance_dir": pack.acceptance_dir,
        "acceptance_pattern": pack.acceptance_pattern,
        "kept_files": [pack.filled(path, project, title, package) for path in pack.kept_files],
        "smoke_files": [pack.filled(path, project, title, package) for path in pack.smoke_files],
        "acceptance_guide": pack.filled(pack.acceptance_guide, project, title, package)[:MAX_GUIDE],
        # Which pack's runners this is: its proven pack keeps that pack's checks (SF.1).
        "layer": pack.name,
    }
    (project_root / DECLARATION_FILE).write_text(json.dumps(declaration, indent=2) + "\n", encoding="utf-8")
    return framework


def record_the_setup_s_scope(root: Path, project: str, layer_files: dict[str, str] | None) -> None:
    """The files a layered setup stage is asked for, kept for `SETUP_SCOPE_GUARD`; cleared when there is no layer."""
    from app.tools.repository import SETUP_SCOPE_FILE

    path = Path(root) / SETUP_SCOPE_FILE
    try:
        if not layer_files:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"project": project, "files": sorted(layer_files)}), encoding="utf-8")
    except OSError:
        logger.debug("Could not record the setup's scope", exc_info=True)


def layered_setup(project_root: Path, stack: Any, kind: str, project: str, title: str, *, write: bool) -> dict[str, str] | None:
    """The framework files left to the setup stage when a runner layer covers this stack; None when none does.

    Written once, on the first attempt (`write`); a later attempt keeps what the first wrote and is asked for the
    same files again.
    """
    layer = runner_layer(kind, str(getattr(stack, "language", "") or ""))
    if layer is None:
        return None
    if write:
        return write_runner_layer(project_root, layer, project, title)
    from app.stacks import python_package_name

    package = python_package_name(project)
    return {layer.filled(path, project, title, package): layer.filled(what, project, title, package)
            for path, what in layer.framework_files.items()}


def build_setup_request(
    project: str, stack: Any, kind: str, problem: str = "", specification: Any = None,
    layer_files: dict[str, str] | None = None,
) -> dict[str, Any]:
    """What the setup stage is asked to do.

    With the specification's files, testing and configuration: the product is
    built from that document, so the setup uses the names it gives. Measured on
    one run: the specification planned one test runner configuration file and
    the setup created two others under names of its own, so every builder was
    handed a layout that was not the project's.
    """
    meets = _MEETS.get(kind, "it exercises the product the way its user meets it")
    planned = what_the_specification_sets_up(specification) if specification is not None else ""
    planned = (
        "\n--- What the specification already decided ---\n"
        "The product is built from this. Where it names a manifest, a runner configuration "
        "file, a test directory, a test command, a module system or a dependency version, set "
        "the project up with exactly that; decide only what it leaves open.\n" + planned + "\n"
        if planned else ""
    )
    again = (
        f"\n--- The last setup was not proven ---\n{problem}\nFix what failed, keep what works, "
        "run both smoke tests again through the declared commands, and update the declaration.\n"
        if problem else ""
    )
    if layer_files:
        wanted = "\n".join(f"- `{project}/{path}`: {what}" for path, what in layer_files.items())
        text = f"""--- Set up the project's framework: its runners are already set up ---
No ready-made setup exists for this stack ({_stack_line(stack)}), so `{project}/` is set up on its language's
runners: the install into the project's `.venv`, the unit and acceptance test runners with their reports, the
acceptance suite's configuration, an acceptance smoke test, and `{project}/{DECLARATION_FILE}`.
Leave those as they are: the harness proves the setup by running exactly the commands that file declares.

Write only these files, for this stack's own framework, so both smoke tests pass:
{wanted}

Ask `look_up_package` for the framework's current version, and `read_docs` for how it serves a route. You may run the
declared install and both smoke tests through the declared commands to check your files; then answer. Build nothing of
the product beyond what the smoke tests need: the sprints build the rest.
{planned}{again}"""
        return {"messages": [{"role": "user", "content": text}]}
    text = f"""--- Set up the project so its tests already run ---
No ready-made setup exists for this stack ({_stack_line(stack)}). Before anything of the
product is built, set up `{project}/` so that a unit test and an acceptance test both run.

First, before anything else, write `{project}/{DECLARATION_FILE}` (its shape is in step 4) with
the commands you intend to use, and keep it current as you go. The harness proves the setup from
that file alone: a setup that runs out of calls before writing it is started again from nothing.

1. Create the project in `{project}/` with the framework's own project generator where it has
   one, answering its questions with flags so it never waits for input. Before choosing a
   version, ask `look_up_package` what is current and which runtime it needs; where that is
   not the runtime this environment has, ask for it with `use_runtime` first. Read how the
   generator and the runners are set up today with `read_docs`.
2. Add a unit test runner and an acceptance test runner, each writing a JUnit XML report.
   An acceptance test meets this product the way its user does: {meets}. Any server the
   acceptance runner needs is started by the runner's own configuration; never start one
   yourself.
3. Write exactly one unit smoke test and one acceptance smoke test that pass on the project
   as generated, and run each through the command you will declare until it passes. Each
   declared command runs every test of its kind - its test directory, never the smoke test's
   file or name - because the harness removes the smoke tests itself after it has proven the
   setup: leave them in place, the proof runs them.
4. Bring `{project}/{DECLARATION_FILE}` up to date with what you ran, every path relative to `{project}/`:
   {{
     "kind": "{kind or 'one of ' + ', '.join(KINDS)}",
     "install": [["<program>", "<argument>", ...]],
     "build": ["<program>", "<argument>", ...],
     "unit_test": ["<program>", "<argument>", ...],
     "unit_report": "<where the unit runner writes JUnit XML>",
     "unit_dir": "<directory unit tests live in>",
     "unit_pattern": "<file name pattern of a unit test, e.g. *.test.ts>",
     "acceptance_test": ["<program>", "<argument>", ...],
     "acceptance_report": "<where the acceptance runner writes JUnit XML>",
     "acceptance_dir": "<directory of its own for acceptance tests>",
     "acceptance_pattern": "<file name pattern of an acceptance test>",
     "kept_files": ["<runner configuration files the two commands depend on>"],
     "smoke_files": ["<the unit smoke test>", "<the acceptance smoke test>"],
     "guide": "<how a unit test is written and run here, in a few sentences>",
     "acceptance_guide": "<how an acceptance test drives the product, in a few sentences>"
   }}

`build` is the command that compiles or builds the project before it runs, when it is built
at all; leave it out when nothing is. Build nothing of the product itself: write only the
smallest app the two smoke tests need, because the sprints build the rest, where it is
reviewed. The harness then
runs the install, the build and both smoke tests through exactly these commands; a setup whose smoke tests pass is kept as the project's
test setup for the rest of the run, and the smoke tests are removed.
{planned}{again}"""
    return {"messages": [{"role": "user", "content": text}]}


@dataclass
class Declaration:
    kind: str
    install: tuple[tuple[str, ...], ...]
    unit_test: tuple[str, ...]
    unit_report: str
    unit_dir: str
    unit_pattern: str
    acceptance_test: tuple[str, ...]
    acceptance_report: str
    acceptance_dir: str
    acceptance_pattern: str
    kept_files: tuple[str, ...]
    smoke_files: tuple[str, ...]
    guide: str
    acceptance_guide: str
    #: The command that builds the project before it runs, when it has one.
    build: tuple[str, ...] = ()
    #: The pack whose runner layer the setup was made on (SF.2); "" for a setup written by hand.
    layer: str = ""


def _inside(path: Any) -> str | None:
    """`path` as a clean project-relative path, or None if it is not one."""
    if not isinstance(path, str) or not path.strip():
        return None
    clean = PurePosixPath(path.strip().replace("\\", "/"))
    if clean.is_absolute() or ".." in clean.parts:
        return None
    text = str(clean)
    return None if text in {".", ""} else text


def _argv(value: Any) -> tuple[str, ...] | None:
    # A command written as one string - `"npm test"`, `["node --test 'tests/*.test.ts'"]` -
    # is that command's words. One local model's setup declared every command so.
    if isinstance(value, str) and value.strip():
        value = [value]
    # One command wrapped as a list of commands: `[["node", "--test", ...]]`.
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], list):
        value = value[0]
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], str) and " " in value[0].strip():
        try:
            value = shlex.split(value[0])
        except ValueError:
            return None
    if isinstance(value, list) and value and all(isinstance(part, str) and part for part in value):
        return tuple(value)
    return None


def _inside_the_project(argv: tuple[str, ...] | None, project_root: Path) -> tuple[str, ...] | None:
    """`argv` with a leading project folder dropped from each path: declared commands run inside the project.

    Measured on a custom-stack baseline: `./notes-api/.venv/bin/pip install -e ./notes-api`, run inside `notes-api/`,
    became `notes-api/notes-api/...` and the setup was left to the agents. A folder of that name that exists inside
    the project - a package named like it - is left as written.
    """
    if not argv:
        return argv
    name = project_root.name
    fixed = []
    for token in argv:
        plain = str(token)
        for prefix in (f"./{name}/", f"{name}/"):
            rest = plain[len(prefix):]
            if plain.startswith(prefix) and not (project_root / name).is_dir():
                plain = rest or "."
                break
        if plain in (f"./{name}", name) and not (project_root / name).is_dir():
            plain = "."
        fixed.append(plain)
    return tuple(fixed)


def _commands(value: Any) -> tuple[tuple[str, ...] | None, ...]:
    """`install` as commands: a list of commands, or one command, or each string one command."""
    if isinstance(value, str):
        return (_argv(value),)
    if not isinstance(value, list):
        return (None,)
    if value and all(isinstance(item, str) for item in value):
        if any(" " in item.strip() for item in value):
            return tuple(_argv(item) for item in value)
        return (_argv(value),)
    return tuple(_argv(item) for item in value)


def _in_this_project(path: Any, project_root: Path) -> str | None:
    """`path` relative to the project, a leading project directory name taken off."""
    if isinstance(path, str):
        cleaned = path.strip().replace("\\", "/").lstrip("./")
        prefix = project_root.name + "/"
        if cleaned.startswith(prefix):
            path = cleaned[len(prefix):]
    return _inside(path)


#: What a declaration's `unit_dir` says for tests that sit beside the code: as a pack declares it.
BESIDE_THE_CODE = "."


def _the_project_itself(path: Any, project_root: Path) -> bool:
    """Whether `path` names the project's own folder: `.`, `./`, or its name, however written."""
    if not isinstance(path, str):
        return False
    cleaned = path.strip().replace("\\", "/").rstrip("/").removeprefix("./")
    return cleaned in {".", project_root.name}


def read_declaration(project_root: Path, fallback_kind: str = "") -> tuple[Declaration | None, str]:
    """The declaration, or (None, what is wrong with it)."""
    where = project_root / DECLARATION_FILE
    try:
        text = where.read_text(encoding="utf-8")
    except OSError:
        return None, f"`{DECLARATION_FILE}` was not written in `{project_root.name}/`."
    return _declared(text, project_root, fallback_kind, files_written=True)


def problems_with(text: str, project_root: Path) -> str:
    """What makes a declaration about to be written unusable; "" if nothing.

    Checked as it is written, so the stage fixes it in the conversation it is
    in. Measured on one run: the setup stage's second attempt declared one
    directory for both kinds of test, learned so only after it had answered,
    and the setup was left to the agents. The files it names may come after
    it, so they are not required to exist yet.
    """
    return _declared(text, project_root, "", files_written=False)[1]


#: Folders no runner's tests live in: dependencies, builds, the runners' own output.
_NOT_THE_PROJECT_S_TESTS = frozenset({
    "node_modules", ".venv", "venv", "dist", "build", "target", "coverage", "__pycache__",
    "test-results", "playwright-report",
})


def _within(name: str, directory: str) -> bool:
    folder = directory.strip("/")
    if folder == BESIDE_THE_CODE:
        return True
    return bool(folder) and (name == folder or name.startswith(folder + "/"))


def _tests_the_runners_never_collect(
    project_root: Path, paths: dict[str, Any], patterns: dict[str, str], smoke: list[Any],
) -> list[str]:
    """Problems for a smoke test outside its runner's directory, and for any test file no runner collects.

    Measured on one run: the setup wrote a unit test outside the declared unit
    directory. The unit runner matched nothing and wrote no report, the file was
    cleared at release as a throwaway, and the product shipped with no unit test.
    """
    from fnmatch import fnmatch

    unit_dir, acceptance_dir = str(paths.get("unit_dir") or ""), str(paths.get("acceptance_dir") or "")
    unit_pattern, acceptance_pattern = patterns.get("unit_pattern", ""), patterns.get("acceptance_pattern", "")
    problems: list[str] = []
    named = [name for name in smoke if name]
    if named and unit_dir and not (_within(named[0], unit_dir) and fnmatch(PurePosixPath(named[0]).name, unit_pattern)):
        problems.append(
            f"the unit smoke test `{named[0]}` must sit in `{unit_dir}` and match `{unit_pattern}`, "
            "where the unit runner collects it"
        )
    if len(named) > 1 and acceptance_dir and not _within(named[1], acceptance_dir):
        problems.append(f"the acceptance smoke test `{named[1]}` must sit in `{acceptance_dir}`")
    stray: list[str] = []
    for directory, subdirectories, files in os.walk(project_root):
        subdirectories[:] = [d for d in subdirectories if d not in _NOT_THE_PROJECT_S_TESTS and not d.startswith(".")]
        for file_name in files:
            relative = (Path(directory) / file_name).relative_to(project_root).as_posix()
            # Unit tests beside the code: only what the unit pattern names is the unit runner's.
            collected = unit_dir != BESIDE_THE_CODE or fnmatch(file_name, unit_pattern)
            if (collected and _within(relative, unit_dir)) or _within(relative, acceptance_dir):
                continue
            if any(p and fnmatch(file_name, p) for p in (unit_pattern, acceptance_pattern)):
                stray.append(relative)
    if stray:
        problems.append(
            "these test files sit outside both declared test directories, so no runner ever runs "
            "them: " + ", ".join(f"`{name}`" for name in sorted(stray)[:5])
            + "; move each into the directory of its runner, or remove it"
        )
    return problems


def _declared(text: str, project_root: Path, fallback_kind: str, *, files_written: bool) -> tuple[Declaration | None, str]:
    try:
        data = json.loads(text)
    except ValueError as exc:
        return None, f"`{DECLARATION_FILE}` is not valid JSON: {exc}."
    if not isinstance(data, dict):
        return None, f"`{DECLARATION_FILE}` must hold one JSON object."
    problems: list[str] = []
    install = tuple(_inside_the_project(argv, project_root) for argv in _commands(data.get("install") or []))
    if any(argv is None for argv in install):
        problems.append("`install` must be a list of commands, each a list of strings")
    commands = {key: _inside_the_project(_argv(data.get(key)), project_root) for key in ("unit_test", "acceptance_test")}
    problems += [f"`{key}` must be a command: a list of strings" for key, argv in commands.items() if argv is None]
    paths = {
        key: _in_this_project(data.get(key), project_root)
        for key in ("unit_report", "unit_dir", "acceptance_report", "acceptance_dir")
    }
    # Tests beside the code are how packs declare them too. Measured on one run: `.` and the project's own name were
    # refused seven times as not "inside the project", and the setup was left to the agents.
    if _the_project_itself(data.get("unit_dir"), project_root):
        paths["unit_dir"] = BESIDE_THE_CODE
    for key, path in paths.items():
        if path is not None:
            continue
        if key == "acceptance_dir" and _the_project_itself(data.get(key), project_root):
            problems.append("`acceptance_dir` names the project itself: acceptance tests need a folder of their own in it, such as `acceptance`")
        else:
            problems.append(f"`{key}` must be a path inside the project")
    patterns = {key: str(data.get(key) or "").strip() for key in ("unit_pattern", "acceptance_pattern")}
    problems += [f"`{key}` must name a file pattern" for key, value in patterns.items() if not value or "/" in value]
    # A pattern is not a file the harness can keep - and `src/**/*.ts` would
    # keep the product's own code from every stage after this one.
    kept = [_in_this_project(name, project_root) for name in data.get("kept_files") or []
            if not (isinstance(name, str) and any(mark in name for mark in "*?["))]
    # A test's id (`test_main.py::test_save`) names the file it is in: measured, one read as a missing file and marked
    # a product at full hidden marks non-deliverable.
    smoke = [
        _in_this_project(name.split("::")[0] if isinstance(name, str) else name, project_root)
        for name in data.get("smoke_files") or []
    ]
    # A test command runs every test of its kind. Measured on the first custom-stack baseline: both commands named the
    # smoke test (`tests/test_store.py::test_store_smoke`); the proof passed with only the smoke tests there, the
    # contract kept the commands for every round, the smoke tests were removed - and no later test would have run.
    smoke_names = {name for name in smoke if name}
    for key, argv in commands.items():
        for token in argv or ():
            plain = str(token).split("::")[0].removeprefix("./")
            if "::" in str(token) or plain in smoke_names:
                problems.append(
                    f"`{key}` runs only `{token}`: it must run every test of its kind - name its test directory (or "
                    "let the runner find them) - since the smoke tests are removed once the setup is proven and the "
                    "sprints' tests must run through this same command"
                )
                break
    if any(name is None for name in kept):
        problems.append("every `kept_files` entry must be a path inside the project")
    if len(smoke) < 2 or any(name is None for name in smoke):
        problems.append("`smoke_files` must list the unit and the acceptance smoke test")
    wanted = [name for name in [*kept, *smoke] if name] if files_written else []
    # A folder is not a file the harness can keep, whether or not it exists: measured, a setup listed
    # `node_modules` under `kept_files`, the message said it "does not exist", the setup ran the install
    # to make it, and the same message came back - twice, the setup was left to the agents.
    folders = [name for name in wanted if (project_root / name).is_dir()]
    missing = [name for name in wanted if not (project_root / name).exists()]
    if folders:
        problems.append(
            "these declared entries are folders, and `kept_files` and `smoke_files` list files: "
            + ", ".join(f"`{name}`" for name in folders)
            + " - name the files you want kept, or leave the folder out (what `install` makes is made again)"
        )
    if missing:
        problems.append("these declared files do not exist: " + ", ".join(f"`{name}`" for name in missing))
    kind = str(data.get("kind") or "").strip().lower().replace("-", "_")
    if kind not in KINDS:
        kind = fallback_kind
    if kind not in KINDS and (files_written or data.get("kind")):
        problems.append(f"`kind` must be one of {', '.join(KINDS)}")
    build = _argv(data.get("build")) if data.get("build") else ()
    if build is None:
        problems.append("`build` must be one command, a list of strings")
    if paths.get("acceptance_dir") and paths.get("acceptance_dir") == paths.get("unit_dir"):
        problems.append("acceptance tests need a directory of their own, apart from the unit tests")
    if files_written and not problems:
        problems += _tests_the_runners_never_collect(project_root, paths, patterns, smoke)
    if problems:
        return None, f"`{DECLARATION_FILE}` cannot be used: " + "; ".join(problems) + "."
    return Declaration(
        kind=kind,
        install=tuple(argv for argv in install if argv),
        unit_test=commands["unit_test"] or (),
        unit_report=paths["unit_report"] or "",
        unit_dir=paths["unit_dir"] or "",
        unit_pattern=patterns["unit_pattern"],
        acceptance_test=commands["acceptance_test"] or (),
        acceptance_report=paths["acceptance_report"] or "",
        acceptance_dir=paths["acceptance_dir"] or "",
        acceptance_pattern=patterns["acceptance_pattern"],
        kept_files=tuple(name for name in kept if name),
        smoke_files=tuple(name for name in smoke if name),
        guide=str(data.get("guide") or "")[:MAX_GUIDE],
        acceptance_guide=str(data.get("acceptance_guide") or "")[:MAX_GUIDE],
        build=build or (),
        layer=_a_layer_named(data.get("layer")),
    ), ""


#: How a package manager names the manifest script a command runs: `npm test`,
#: `npm run test:e2e`, `yarn test`, `pnpm run unit`.
_RUNS_A_SCRIPT = re.compile(r"^(?:npm|yarn|pnpm)$")


def _scripts_the_commands_run(project_root: Path, commands: Sequence[Sequence[str]]) -> dict[str, str]:
    """The manifest scripts the declared commands run, as they were when proven."""
    try:
        scripts = json.loads((project_root / "package.json").read_text(encoding="utf-8")).get("scripts") or {}
    except (OSError, ValueError, AttributeError):
        return {}
    named: dict[str, str] = {}
    for argv in commands:
        if len(argv) < 2 or not _RUNS_A_SCRIPT.match(Path(argv[0]).name):
            continue
        name = argv[2] if argv[1] in {"run", "run-script"} and len(argv) > 2 else argv[1]
        if isinstance(scripts.get(name), str):
            named[name] = scripts[name]
    return named


def _the_language(stack: Any) -> str:
    """The language the stack names first, else one its frameworks are written in, or ""."""
    from app.stacks import _LANGUAGE_NAMES, _languages

    text = str(getattr(stack, "language", "") or "").lower()
    named = sorted(
        (match.start(), name) for name, pattern in _LANGUAGE_NAMES.items() if (match := pattern.search(text))
    )
    if named:
        return named[0][1]
    return min(_languages(stack), default="")


#: The setup's own code shown to the builders: short files, at most two, so the request stays small.
PROVEN_CODE_LINES = 30
_PROVEN_CODE_SUFFIXES = (".ts", ".mts", ".js", ".mjs", ".cjs", ".py", ".go", ".rs", ".java", ".kt", ".cs", ".rb", ".php",
                         ".ex", ".exs")
MIN_PROVEN_CODE_LINES = 3
#: The harness's own scratch files for a command's inline code (`tmp-inline-<hash>.py`): never the product's.
_SCRATCH = "tmp-inline-"
_A_COMMENT_LINE = re.compile(r"^\s*(#|//|/\*|\*|--)")


def _code_of(text: str) -> list[str]:
    """The lines of `text` that are code: not blank, not a comment, not part of a Python docstring."""
    lines: list[str] = []
    closing = ""
    for line in text.splitlines():
        stripped = line.strip()
        if closing:
            if closing in stripped:
                closing = ""
            continue
        if not stripped or _A_COMMENT_LINE.match(line):
            continue
        opener = next((q for q in ('"""', "\'\'\'") if stripped.startswith(q)), "")
        if opener:
            if stripped.count(opener) < 2:
                closing = opener
            continue
        lines.append(stripped)
    return lines


_NOT_WALKED = {"node_modules", "vendor", "target", "build", "dist", "__pycache__", "venv", "bin", "obj"}


def _the_setup_s_own_code(project_root: Path, declared: Declaration) -> dict[str, str]:
    """The product code the setup wrote and leaves in place - neither kept nor a smoke test nor a test - as proven.

    Measured on a stack no pack covers: the specification, written before the setup, created the application with the
    framework's other server interface; the builders followed it, and the product the setup had proven to start no
    longer started. What the setup's own entry did is the one fact proven to run.
    """
    skipped = {*declared.kept_files, *declared.smoke_files}
    tests = tuple(f"{folder.strip('/')}/" for folder in (declared.unit_dir, declared.acceptance_dir) if folder.strip("/"))
    found: dict[str, str] = {}
    try:
        candidates = []
        for folder, folders, files in os.walk(project_root):
            depth = len(Path(folder).relative_to(project_root).parts)
            folders[:] = sorted(name for name in folders
                                if depth < 3 and not name.startswith(".") and name not in _NOT_WALKED)
            candidates.extend(Path(folder) / name for name in files)
        for path in sorted(candidates):
            relative = path.relative_to(project_root).as_posix()
            if (not relative.endswith(_PROVEN_CODE_SUFFIXES) or relative in skipped or relative.startswith(tests)
                    or "test" in relative.rsplit("/", 1)[-1].lower() or relative.rsplit("/", 1)[-1].startswith(".")):
                continue
            if relative.rsplit("/", 1)[-1].startswith(_SCRATCH):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            code = _code_of(text)
            # A file of a docstring or comments alone says nothing of how the application is made (measured: a
            # package's one-line `__init__.py` and a harness scratch file were recorded, the entry was not).
            if MIN_PROVEN_CODE_LINES <= len(code) <= PROVEN_CODE_LINES:
                found[relative] = text
            if len(found) == 2:
                break
    except OSError:
        logger.debug("Could not read the setup's own code", exc_info=True)
    return found


def _tests_beyond_the_smoke_tests(project_root: Path, parsed: Any, smoke_files: tuple[str, ...]) -> list[str]:
    """The test files whose failing tests are not the setup's smoke tests, when every smoke test passed; [] else."""
    def file_of(test: Any) -> str:
        if test.file:
            return str(test.file).replace("\\", "/").lstrip("./")
        module = str(test.suite or "")
        for smoke in smoke_files:
            if module == smoke.rsplit(".", 1)[0].replace("/", ".") or module.startswith(
                    smoke.rsplit(".", 1)[0].replace("/", ".") + "."):
                return smoke
        parts = module.split(".")
        for cut in range(len(parts), 0, -1):
            for suffix in _PROVEN_CODE_SUFFIXES:
                candidate = "/".join(parts[:cut]) + suffix
                if (project_root / candidate).is_file():
                    return candidate
        return ""

    smoke = set(smoke_files)
    mine = [t for t in parsed.tests if file_of(t) in smoke]
    if not mine or any(t.outcome == "failed" for t in mine):
        return []
    others = sorted({file_of(t) for t in parsed.tests if t.outcome == "failed" and file_of(t) not in smoke})
    if not others or "" in others:
        return []
    return others


_A_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _without_the_framework(text: str, frameworks: tuple[str, ...]) -> str:
    """`text` with each sentence that names one of `frameworks` left out, its line breaks kept."""
    words = [re.compile(rf"(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])", re.I) for name in frameworks if name]
    lines = []
    for line in str(text or "").splitlines():
        kept = [sentence for sentence in _A_SENTENCE_END.split(line) if not any(word.search(sentence) for word in words)]
        if kept or not line.strip():
            lines.append(" ".join(kept))
    return "\n".join(lines).strip()


def pack_from(record: dict[str, Any]) -> StackPack | None:
    """The pack a proven setup's contract describes, or None if it is not one."""
    setup = record.get("setup")
    if record.get("pack") != PROVEN_SETUP or not isinstance(setup, dict):
        return None
    try:
        kind = str(setup["kind"])
        stack = dict(setup.get("stack") or {})
        layer = _a_layer_named(setup.get("layer"))
        if layer:
            # Proven on a pack's runner layer: that pack, with this setup's commands, paths and kept files and none of
            # its framework (SF.1). It keeps the pack's test-bug patterns, known errors, entrypoint and release files.
            import dataclasses

            from app.stacks import pack_named

            base = pack_named(layer)
            return dataclasses.replace(
                base,
                name=PROVEN_SETUP,
                title=f"Proven setup for {setup.get('stack_line') or 'this stack'} on the {base.title} runners",
                frameworks=(),
                files=dict(setup.get("kept") or {}),
                install=tuple(tuple(argv) for argv in setup.get("install") or []),
                unit_test=tuple(setup["unit_test"]),
                acceptance_test=tuple(setup["acceptance_test"]),
                unit_report=str(setup["unit_report"]),
                acceptance_report=str(setup["acceptance_report"]),
                unit_dir=str(setup["unit_dir"]),
                acceptance_dir=str(setup["acceptance_dir"]),
                acceptance_pattern=str(setup["acceptance_pattern"]),
                unit_pattern=str(setup["unit_pattern"]),
                kept_files=tuple(dict(setup.get("kept") or {})),
                kept_scripts=dict(setup.get("kept_scripts") or {}),
                smoke_files={},
                stack={**dict(base.stack), **stack},
                framework_files={},
                proven_code=dict(setup.get("proven_code") or {}),
                # The pack's guide is written for its own framework: measured, a Falcon product's builders were told
                # to test routes through FastAPI's test client, and the setup's own guide was dropped. The setup's
                # guide first, then the pack's with every sentence naming its framework left out.
                guide="\n".join(part for part in (str(setup.get("guide") or "").strip(),
                                                   _without_the_framework(base.guide, base.frameworks)) if part),
                acceptance_guide=_without_the_framework(base.acceptance_guide, base.frameworks)
                or str(setup.get("acceptance_guide") or ""),
                # A release file that names the pack's own framework (its server command) fits no other framework:
                # measured, the Python pack's Dockerfile runs `uvicorn ...` for a Falcon product. Better none.
                release_files={path: text for path, text in base.release_files.items()
                               if not any(word in text.lower() for word in base.frameworks)},
            )
        return StackPack(
            name=PROVEN_SETUP,
            title=f"Proven setup for {setup.get('stack_line') or 'this stack'}",
            kind=kind,
            language=str(setup.get("language") or ""),
            frameworks=(),
            files=dict(setup.get("kept") or {}),
            install=tuple(tuple(argv) for argv in setup.get("install") or []),
            unit_test=tuple(setup["unit_test"]),
            acceptance_test=tuple(setup["acceptance_test"]),
            unit_report=str(setup["unit_report"]),
            acceptance_report=str(setup["acceptance_report"]),
            unit_dir=str(setup["unit_dir"]),
            acceptance_dir=str(setup["acceptance_dir"]),
            acceptance_pattern=str(setup["acceptance_pattern"]),
            unit_pattern=str(setup["unit_pattern"]),
            kept_files=tuple(dict(setup.get("kept") or {})),
            kept_scripts=dict(setup.get("kept_scripts") or {}),
            smoke_files={},
            guide=str(setup.get("guide") or ""),
            acceptance_guide=str(setup.get("acceptance_guide") or "")
            or f"An acceptance test meets the product the way its user does: {_MEETS.get(kind, '')}.",
            stack=stack,
            production_build=tuple(setup.get("build") or ()),
            proven_code=dict(setup.get("proven_code") or {}),
        )
    except (KeyError, TypeError):
        logger.debug("Unreadable proven setup in the contract", exc_info=True)
        return None


def prove(
    repo_root: str | Path,
    project: str,
    stack: Any,
    *,
    brief: str = "",
    title: str = "",
    run: Runner | None = None,
    keep: bool = True,
) -> ScaffoldResult:
    """Prove the declared setup the way a pack's scaffold is proven, and record it if it passes.

    `keep=False` proves it and stops there - no contract, commit or library entry is written: how the nightly check
    replays each library entry on an empty project (scaffolding plan SF.0b).
    """
    root = Path(repo_root)
    project_root = root / project
    result = ScaffoldResult(ok=False, pack=PROVEN_SETUP, project=project)
    declared, problem = read_declaration(project_root, product_kind(stack, brief))
    if declared is None:
        result.problem = problem
        return result
    run = run or sandbox_runner(root)

    for argv in declared.install:
        code = _step(result.steps, argv, run(list(argv), "install", project))
        if code != 0:
            code = _step(result.steps, argv, run(list(argv), "install", project))
        if code != 0:
            result.problem = f"`{' '.join(argv)}` failed in {project}/: {where_it_failed(result.steps[-1]['output'], 1200)}"
            return result

    # The build too: a smoke test can pass without compiling anything, and
    # the configuration the build reads is then kept unproven. One run's kept
    # `tsconfig.json` had `lib` as a string where the compiler wants a list,
    # and the product could not be built from then on.
    if declared.build:
        code = _step(result.steps, declared.build, run(list(declared.build), "build", project))
        if code != 0:
            result.problem = (
                f"`{' '.join(declared.build)}` failed in {project}/: {where_it_failed(result.steps[-1]['output'], 1200)}"
            )
            return result

    for label, argv, report in (
        ("unit", declared.unit_test, declared.unit_report),
        ("acceptance", declared.acceptance_test, declared.acceptance_report),
    ):
        for _attempt in range(2):
            junit.clear(project_root / report)
            code = _step(result.steps, argv, run(list(argv), "test", project))
            parsed = junit.read(project_root / report)
            if code == 0 and parsed.found and parsed.passed >= 1 and not parsed.failed:
                break
            beyond = _tests_beyond_the_smoke_tests(project_root, parsed, declared.smoke_files)
            if beyond:
                # Measured on a setup stage: it wrote the product's acceptance tests beside its smoke test, the proof
                # ran them all on a product not yet written, and two attempts were "not proven" on 15 and 10 tests
                # that were never the setup's. The suite's writers write those, after the setup; these go, and the
                # runners are asked again.
                for relative in beyond:
                    (project_root / relative).unlink(missing_ok=True)
                result.steps.append({"command": "remove " + ", ".join(beyond), "exit_code": 0,
                                     "output": "test files beyond the smoke tests: the suite's writers write those"})
                junit.clear(project_root / report)
                code = _step(result.steps, argv, run(list(argv), "test", project))
                parsed = junit.read(project_root / report)
                if code == 0 and parsed.found and parsed.passed >= 1 and not parsed.failed:
                    break
        else:
            result.problem = (
                f"The {label} smoke test did not pass through `{' '.join(argv)}` "
                f"(exit {code}, {parsed.passed} passed, {parsed.failed} failed, report "
                f"`{report}` {'found' if parsed.found else 'missing'}). Its output ended:\n"
                f"{result.steps[-1]['output'][-1200:]}"
            )
            return result

    if not keep:
        result.ok = True
        return result
    kept = {name: (project_root / name).read_text(encoding="utf-8", errors="replace") for name in declared.kept_files}
    # What a later run on the same stack replays instead of asking an agent
    # (`replay`): the declaration and every file it names, as proven.
    replayable = {
        "declaration": (project_root / DECLARATION_FILE).read_text(encoding="utf-8", errors="replace"),
        "files": {
            name: (project_root / name).read_text(encoding="utf-8", errors="replace")
            for name in (*declared.kept_files, *declared.smoke_files)
        },
    }
    proven_code = _the_setup_s_own_code(project_root, declared)
    for relative in declared.smoke_files:
        (project_root / relative).unlink(missing_ok=True)
    for report in (declared.unit_report, declared.acceptance_report):
        junit.clear(project_root / report)
    (project_root / DECLARATION_FILE).unlink(missing_ok=True)

    setup = {
        "kind": declared.kind,
        "language": _the_language(stack),
        "stack_line": _stack_line(stack),
        "stack": {
            key: str(getattr(stack, key, "") or "")
            for key in ("language", "framework", "frontend_framework", "testing_framework")
            if getattr(stack, key, "")
        },
        "install": [list(argv) for argv in declared.install],
        "build": list(declared.build),
        "unit_test": list(declared.unit_test),
        "acceptance_test": list(declared.acceptance_test),
        "unit_report": declared.unit_report,
        "acceptance_report": declared.acceptance_report,
        "unit_dir": declared.unit_dir,
        "acceptance_dir": declared.acceptance_dir,
        "unit_pattern": declared.unit_pattern,
        "acceptance_pattern": declared.acceptance_pattern,
        "kept": kept,
        "kept_scripts": _scripts_the_commands_run(project_root, [declared.unit_test, declared.acceptance_test]),
        "guide": declared.guide,
        "acceptance_guide": declared.acceptance_guide,
        "layer": declared.layer,
        "proven_code": proven_code,
        # The acceptance smoke test that passed: the shape QA's tests copy
        # (`app.acceptance.requests`), kept though the file itself is removed.
        "acceptance_example": next(
            (text for name, text in replayable["files"].items()
             if name in declared.smoke_files and name.startswith(f"{declared.acceptance_dir}/")),
            "",
        ),
    }
    pack = pack_from({"pack": PROVEN_SETUP, "setup": setup})
    if pack is None:
        result.problem = "The proven setup could not be recorded."
        return result
    contract.write(root, pack, project, title or project, extra={"setup": setup})
    try:
        from app.tools.version_control import commit_all

        commit_all(root, f"Scaffold: {pack.title}")
    except Exception:  # noqa: BLE001 - history is a convenience, not the setup
        logger.debug("Could not commit the proven setup", exc_info=True)
    # The setup's own short code its smoke tests import goes with the entry; anything more and the entry is not kept.
    for name in _smoke_tests_import_the_product(project_root, declared, replayable["files"]):
        if name in proven_code:
            replayable["files"][name] = proven_code[name]
    beyond = _smoke_tests_import_the_product(project_root, declared, replayable["files"])
    if beyond:
        logger.warning("The proven setup is not kept for later runs: its smoke tests import %s, the product's own "
                       "code, which a later project does not have", ", ".join(beyond[:3]))
    else:
        remember(stack, replayable)
    result.ok = True
    return result


# --- the library of proven setups ----------------------------------------------
#
# Measured on one run: the setup stage took 37 minutes and was not proven
# twice, and the run went on without a proven setup - for a stack an earlier
# run had already set up and proven. A setup that passes is kept, keyed by its
# stack, and a later run on the same stack replays it and proves it again
# before any agent is asked.


def library_directory() -> Path:
    return Path(os.environ.get("PROVEN_SETUP_LIBRARY") or "/app/data/proven-setups")


def library_key(stack: Any) -> str:
    """The exact wording of the stack, as a file name. Kept so an entry written before `canonical_key` is found."""
    return re.sub(r"[^a-z0-9]+", "-", _stack_line(stack).lower()).strip("-")[:120] or "stack"


#: What a stack is made of, by the names the stack selector uses for them. A table, not a rule: a name missing
#: here falls back to the first word the selector wrote, and the entry is then found only by that word.
_LANGUAGES = (
    ("typescript", ("typescript",)), ("javascript", ("javascript", "node.js", "nodejs")), ("python", ("python",)),
    ("ruby", ("ruby",)), ("go", ("golang", "go")), ("rust", ("rust",)), ("java", ("java",)), ("kotlin", ("kotlin",)),
    ("php", ("php",)), ("csharp", ("c#", "csharp", ".net")),
)
_FRAMEWORKS = (
    ("hono", ("hono",)), ("express", ("express",)), ("fastify", ("fastify",)), ("koa", ("koa",)),
    ("nest", ("nestjs", "nest.js")), ("fastapi", ("fastapi",)), ("flask", ("flask",)), ("django", ("django",)),
    ("stdlib", ("standard library", "standard-library", "stdlib", "http.server", "net/http")),
    ("sinatra", ("sinatra",)), ("rails", ("rails",)), ("gin", ("gin",)), ("spring", ("spring",)),
    ("axum", ("axum",)), ("actix", ("actix",)), ("laravel", ("laravel",)),
)
_UNIT_RUNNERS = (
    ("vitest", ("vitest",)), ("jest", ("jest",)), ("mocha", ("mocha",)),
    ("nodetest", ("node:test", "node --test", "node test runner", "node's test runner")),
    ("pytest", ("pytest",)), ("unittest", ("unittest",)), ("rspec", ("rspec",)), ("minitest", ("minitest",)),
    ("gotest", ("go test", "testing package")), ("phpunit", ("phpunit",)), ("junit", ("junit",)),
)
#: An acceptance runner is not the unit runner: named only when nothing else is.
_ONLY_ACCEPTANCE = ("playwright",)


def _first_of(table: tuple, text: str) -> str:
    """The canonical name whose alias appears earliest in `text`; "" when none does."""
    best, at = "", len(text) + 1
    for name, aliases in table:
        for alias in aliases:
            found = re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text)
            if found and found.start() < at:
                best, at = name, found.start()
    return best


def canonical_key_of(text: str) -> str:
    """`language|framework|unit runner` of a stack described in words, or "" when its language is not known."""
    lowered = str(text or "").lower().replace("-", " ").replace("_", " ")
    language = _first_of(_LANGUAGES, lowered)
    if not language:
        return ""
    framework = _first_of(_FRAMEWORKS, lowered) or _word_after("framework", lowered) or "none"
    runner = _first_of(_UNIT_RUNNERS, lowered) or ("playwright" if "playwright" in lowered else "none")
    return f"{language}|{framework}|{runner}"


def _word_after(label: str, text: str) -> str:
    """The word that follows `label` in a file name or a sentence - how a framework outside the table is named."""
    found = re.search(rf"(?<![a-z0-9]){label}[ :]+([a-z0-9][a-z0-9.]*)", text)
    return found.group(1).strip(".") if found else ""


def canonical_key(stack: Any) -> str:
    framework = str(getattr(stack, "framework", "") or "")
    parts = [str(getattr(stack, "language", "") or ""), f"framework {framework}", str(getattr(stack, "testing_framework", "") or "")]
    return canonical_key_of(" ".join(parts))


def _entry_for(stack: Any) -> Path | None:
    """The library file for this stack: its exact wording, else the newest entry of the same language, framework and runner."""
    directory = library_directory()
    exact = directory / f"{library_key(stack)}.json"
    if exact.is_file():
        return exact
    wanted = canonical_key(stack)
    if not wanted or not directory.is_dir():
        return None
    entries = [(path, canonical_key_of(path.stem)) for path in directory.glob("*.json")]
    matches = [path for path, key in entries if key == wanted]
    if not matches:
        # An old entry's file name was cut at 120 characters, often before its runner: language and framework alone
        # then decide, and the proof the caller runs rejects a wrong runner.
        language, framework, _runner = wanted.split("|")
        matches = [path for path, key in entries if key == f"{language}|{framework}|none"]
    return max(matches, key=lambda path: path.stat().st_mtime, default=None)


_IMPORTED = re.compile(r"^\s*(?:from\s+([A-Za-z_][\w.]*)\s+import|import\s+([A-Za-z_][\w.]*))|"
                       r"(?:require\(|from\s+)['\"](\.{1,2}/[^'\"]+)['\"]", re.M)


def _smoke_tests_import_the_product(project_root: Path, declared: Declaration, files: dict[str, str]) -> list[str]:
    """The product modules a proven setup's smoke tests import - neither kept nor smoke files - or [] (SF.0b, SP.2a).

    A smoke test that imports the product's own module passes in the run that wrote both, and fails in every later
    run the entry is replayed into: the module is not there. Read for Python imports and relative JavaScript ones.
    """
    replayed = {Path(name).as_posix() for name in files}
    found = []
    for smoke in declared.smoke_files:
        text = str(files.get(smoke) or "")
        for python_name, _, relative in (m.groups() for m in _IMPORTED.finditer(text)):
            name = python_name or _
            if relative:
                target = os.path.normpath((Path(smoke).parent / relative).as_posix()).replace("\\", "/")
                candidates = [target + suffix for suffix in ("", ".js", ".ts", ".mjs", "/index.js", "/index.ts")]
            elif name:
                top = name.split(".")[0]
                candidates = [f"{top}.py", f"{top}/__init__.py"] if (project_root / top).exists() or (
                    project_root / f"{top}.py").exists() else []
            else:
                continue
            existing = [c for c in candidates if (project_root / c).is_file()]
            if existing and not any(c in replayed for c in candidates):
                found.append(existing[0])
    return sorted(set(found))


def remember(stack: Any, replayable: dict[str, Any]) -> None:
    """Keep a proven setup for later runs on the same stack: under the stack's own wording, and findable by what it is."""
    try:
        directory = library_directory()
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{library_key(stack)}.json").write_text(json.dumps(replayable), encoding="utf-8")
    except (OSError, TypeError, ValueError):
        logger.debug("Could not keep the proven setup", exc_info=True)


def _command_words(command: Any) -> str:
    """A declared command as words: one argv list, a list of them (a setup may declare several), or a string."""
    if isinstance(command, str):
        return command
    if isinstance(command, (list, tuple)):
        return " ".join(_command_words(part) for part in command)
    return ""


def _chosen_by(model: Any, stack: Any) -> Path | None:
    """The library entry a model picks as the closest to this stack, or None. Never raises, and asks at most once.

    The names a stack selector uses vary from run to run, and a table of aliases cannot keep up with them; reading
    two lines and saying "that one is close enough" is what a model does easily. A wrong pick costs nothing but the
    proof the caller runs on the replayed files, which no agent is asked to read.
    """
    try:
        entries = sorted(library_directory().glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)[:12]
        if not entries or model is None:
            return None
        lines = []
        for number, path in enumerate(entries, 1):
            record = json.loads(path.read_text(encoding="utf-8"))
            declared = json.loads(record.get("declaration") or "{}") if isinstance(record.get("declaration"), str) else {}
            lines.append(
                f"{number}. stack: {path.stem.replace('-', ' ')[:110]}; unit test: {_command_words(declared.get('unit_test'))}; "
                f"files: {', '.join(sorted(record.get('files') or {}))[:120]}"
            )
        from langchain_core.messages import HumanMessage

        from app.agents.thinking import without_reasoning

        asked = (
            "Setups proven in earlier runs, each for a stack:\n" + "\n".join(lines)
            + f"\n\nThis run's stack: {_stack_line(stack)}.\n\nWhich one is close enough to start from: the same "
            "language and framework, and a test runner the project can use as it stands? Reply with its number alone, "
            "or 0 if none is."
        )
        from app.observability.direct_calls import config_for_this_run

        reply = without_reasoning(model).invoke([HumanMessage(content=asked)], **config_for_this_run("stack_setup"))
        text = reply.content if isinstance(reply.content, str) else " ".join(str(part) for part in reply.content)
        found = re.search(r"\d+", text or "")
        number = int(found.group(0)) if found else 0
        return entries[number - 1] if 1 <= number <= len(entries) else None
    except Exception:  # noqa: BLE001 - nothing is replayed, and the agent sets the project up as before
        logger.debug("Could not ask for a library entry", exc_info=True)
        return None


#: The library entry each project was last given by `replay`, so a replay that does not prove can be set aside.
_REPLAYED: dict[str, Path] = {}


def replay(project_root: Path, stack: Any, model: Any = None) -> list[str]:
    """Write a setup proven in an earlier run for this stack into `project_root`; the paths written, or [].

    A stack the selector worded differently from the run that proved the setup still finds it (same language,
    framework and unit runner): measured, three Python entries and a Hono one sat in the library unused because
    each run's wording differed. The caller proves the replayed files again before any agent is asked, so a
    wrong match is rejected there.
    """
    entry = _entry_for(stack) or _chosen_by(model, stack)
    if entry is None:
        return []
    try:
        record = json.loads(entry.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    files = record.get("files") if isinstance(record, dict) else None
    if not isinstance(files, dict) or not isinstance(record.get("declaration"), str):
        return []
    written: list[str] = []
    for name, text in {**files, DECLARATION_FILE: record["declaration"]}.items():
        relative = _in_this_project(name, project_root)
        if relative is None or not isinstance(text, str):
            continue
        target = project_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        written.append(relative)
    if written:
        _REPLAYED[str(project_root)] = entry
        # Kept on disk too: a worker restarted between the replay and its proof (a deploy) forgot it, and an entry
        # that no longer proves was never set aside (scaffolding plan SF.0b).
        try:
            marker = _replayed_marker(project_root)
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(str(entry), encoding="utf-8")
        except OSError:
            logger.debug("Could not keep which entry was replayed", exc_info=True)
    return written


def _replayed_marker(project_root: Path) -> Path:
    """Where the replayed entry's path is kept: the workspace's harness folder, above the project."""
    return project_root.parent / ".harness" / f"replayed-setup-{project_root.name}"


def set_aside_what_did_not_prove(project_root: Path) -> str:
    """Move the library entry replayed into `project_root` to the library's `failed/` folder; its name, or "".

    A proven setup that no longer proves is replayed again on every run of its stack. Measured on one night: the same
    entry, whose install ran a bare `pip` with no project environment, failed its proof on three runs in a row and cost
    each 15 to 25 minutes before the setup stage was asked. Kept, not deleted: what it was stays readable.
    """
    entry = _REPLAYED.pop(str(project_root), None)
    marker = _replayed_marker(project_root)
    if entry is None:
        try:
            entry = Path(marker.read_text(encoding="utf-8").strip())
        except OSError:
            entry = None
    marker.unlink(missing_ok=True)
    if entry is None or not entry.is_file():
        return ""
    try:
        failed = entry.parent / "failed"
        failed.mkdir(parents=True, exist_ok=True)
        entry.replace(failed / entry.name)
        return entry.name
    except OSError:
        return ""


def check_the_library(scratch: Path, run_for: Any = None) -> list[tuple[str, bool, str]]:
    """Each library entry replayed on an empty project and proven; one that fails is set aside. (name, ok, problem).

    The devcontainer `test.sh` pattern (scaffolding plan SF.0b): an entry that no longer proves - a toolchain or a
    pinned version moved under it - is found at night, not by the next run that replays it and pays its proof first.
    `run_for(project_root)` gives the runner for a project; the sandbox's by default.
    """
    results: list[tuple[str, bool, str]] = []
    for entry in sorted(library_directory().glob("*.json")):
        try:
            record = json.loads(entry.read_text(encoding="utf-8"))
            declaration = json.loads(record["declaration"])
            files = dict(record.get("files") or {})
        except (OSError, ValueError, KeyError, TypeError):
            results.append((entry.name, False, "unreadable"))
            continue
        workspace = scratch / entry.stem[:60]
        shutil.rmtree(workspace, ignore_errors=True)
        project_root = workspace / "product"
        project_root.mkdir(parents=True)
        for name, text in {**files, DECLARATION_FILE: record["declaration"]}.items():
            relative = _in_this_project(name, project_root)
            if relative is not None and isinstance(text, str):
                (project_root / relative).parent.mkdir(parents=True, exist_ok=True)
                (project_root / relative).write_text(text, encoding="utf-8")
        stack = SimpleNamespace(product_kind=str(declaration.get("kind") or ""))
        run = run_for(workspace) if run_for else None
        proved = prove(workspace, "product", stack, run=run, keep=False)
        if not proved.ok:
            failed = entry.parent / "failed"
            failed.mkdir(parents=True, exist_ok=True)
            entry.replace(failed / entry.name)
        results.append((entry.name, proved.ok, proved.problem))
        shutil.rmtree(workspace, ignore_errors=True)
    return results


def leave_to_the_agents(project_root: Path) -> None:
    """Remove the declaration of a setup that was never proven; the agents build on the rest."""
    (project_root / DECLARATION_FILE).unlink(missing_ok=True)


__all__ = [
    "ATTEMPTS", "DECLARATION_FILE", "PROVEN_SETUP", "already_set_up", "leave_to_the_agents",
    "build_setup_request", "enabled", "library_key", "pack_from", "problems_with", "prove", "read_declaration",
    "remember", "replay", "canonical_key", "canonical_key_of", "set_aside_what_did_not_prove",
]
