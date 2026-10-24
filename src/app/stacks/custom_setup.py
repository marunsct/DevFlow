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
import logging
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
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


def already_set_up(project_root: Path) -> bool:
    """Whether the project already has a manifest: a seeded codebase is built on as it is."""
    return any((project_root / name).exists() for name in _MANIFESTS) or any(project_root.glob("*.csproj"))


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


def build_setup_request(
    project: str, stack: Any, kind: str, problem: str = "", specification: Any = None,
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
   as generated, and run each through the command you will declare until it passes.
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
            if _within(relative, unit_dir) or _within(relative, acceptance_dir):
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
    install = _commands(data.get("install") or [])
    if any(argv is None for argv in install):
        problems.append("`install` must be a list of commands, each a list of strings")
    commands = {key: _argv(data.get(key)) for key in ("unit_test", "acceptance_test")}
    problems += [f"`{key}` must be a command: a list of strings" for key, argv in commands.items() if argv is None]
    paths = {
        key: _in_this_project(data.get(key), project_root)
        for key in ("unit_report", "unit_dir", "acceptance_report", "acceptance_dir")
    }
    problems += [f"`{key}` must be a path inside the project" for key, path in paths.items() if path is None]
    patterns = {key: str(data.get(key) or "").strip() for key in ("unit_pattern", "acceptance_pattern")}
    problems += [f"`{key}` must name a file pattern" for key, value in patterns.items() if not value or "/" in value]
    # A pattern is not a file the harness can keep - and `src/**/*.ts` would
    # keep the product's own code from every stage after this one.
    kept = [_in_this_project(name, project_root) for name in data.get("kept_files") or []
            if not (isinstance(name, str) and any(mark in name for mark in "*?["))]
    smoke = [_in_this_project(name, project_root) for name in data.get("smoke_files") or []]
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


def pack_from(record: dict[str, Any]) -> StackPack | None:
    """The pack a proven setup's contract describes, or None if it is not one."""
    setup = record.get("setup")
    if record.get("pack") != PROVEN_SETUP or not isinstance(setup, dict):
        return None
    try:
        kind = str(setup["kind"])
        stack = dict(setup.get("stack") or {})
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
) -> ScaffoldResult:
    """Prove the declared setup the way a pack's scaffold is proven, and record it if it passes."""
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
        else:
            result.problem = (
                f"The {label} smoke test did not pass through `{' '.join(argv)}` "
                f"(exit {code}, {parsed.passed} passed, {parsed.failed} failed, report "
                f"`{report}` {'found' if parsed.found else 'missing'}). Its output ended:\n"
                f"{result.steps[-1]['output'][-1200:]}"
            )
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


def remember(stack: Any, replayable: dict[str, Any]) -> None:
    """Keep a proven setup for later runs on the same stack: under the stack's own wording, and findable by what it is."""
    try:
        directory = library_directory()
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{library_key(stack)}.json").write_text(json.dumps(replayable), encoding="utf-8")
    except (OSError, TypeError, ValueError):
        logger.debug("Could not keep the proven setup", exc_info=True)


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
                f"{number}. stack: {path.stem.replace('-', ' ')[:110]}; unit test: {' '.join(declared.get('unit_test') or [])}; "
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
    return written


def leave_to_the_agents(project_root: Path) -> None:
    """Remove the declaration of a setup that was never proven; the agents build on the rest."""
    (project_root / DECLARATION_FILE).unlink(missing_ok=True)


__all__ = [
    "ATTEMPTS", "DECLARATION_FILE", "PROVEN_SETUP", "already_set_up", "leave_to_the_agents",
    "build_setup_request", "enabled", "library_key", "pack_from", "problems_with", "prove", "read_declaration",
    "remember", "replay", "canonical_key", "canonical_key_of",
]
