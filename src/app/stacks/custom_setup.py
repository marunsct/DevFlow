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
import shlex
import logging
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Sequence

from app.acceptance import junit
from app.stacks import KINDS, StackPack, product_kind
from app.stacks import contract
from app.stacks.scaffold import Runner, ScaffoldResult, _step, sandbox_runner

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
product is built, set up `{project}/` so that a unit test and an acceptance test both run:

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
4. Write `{project}/{DECLARATION_FILE}`, every path relative to `{project}/`:
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
at all; leave it out when nothing is. Build nothing of the product itself. The harness then
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
        data = json.loads(where.read_text(encoding="utf-8"))
    except OSError:
        return None, f"`{DECLARATION_FILE}` was not written in `{project_root.name}/`."
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
    missing = [name for name in [*kept, *smoke] if name and not (project_root / name).is_file()]
    if missing:
        problems.append("these declared files do not exist: " + ", ".join(f"`{name}`" for name in missing))
    kind = str(data.get("kind") or "").strip().lower().replace("-", "_")
    if kind not in KINDS:
        kind = fallback_kind
    if kind not in KINDS:
        problems.append(f"`kind` must be one of {', '.join(KINDS)}")
    build = _argv(data.get("build")) if data.get("build") else ()
    if build is None:
        problems.append("`build` must be one command, a list of strings")
    if paths.get("acceptance_dir") and paths.get("acceptance_dir") == paths.get("unit_dir"):
        problems.append("acceptance tests need a directory of their own, apart from the unit tests")
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
            result.problem = f"`{' '.join(argv)}` failed in {project}/: {result.steps[-1]['output'][-800:]}"
            return result

    # The build too: a smoke test can pass without compiling anything, and
    # the configuration the build reads is then kept unproven. One run's kept
    # `tsconfig.json` had `lib` as a string where the compiler wants a list,
    # and the product could not be built from then on.
    if declared.build:
        code = _step(result.steps, declared.build, run(list(declared.build), "build", project))
        if code != 0:
            result.problem = (
                f"`{' '.join(declared.build)}` failed in {project}/: {result.steps[-1]['output'][-1200:]}"
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
    result.ok = True
    return result


def leave_to_the_agents(project_root: Path) -> None:
    """Remove the declaration of a setup that was never proven; the agents build on the rest."""
    (project_root / DECLARATION_FILE).unlink(missing_ok=True)


__all__ = [
    "ATTEMPTS", "DECLARATION_FILE", "PROVEN_SETUP", "already_set_up", "leave_to_the_agents",
    "build_setup_request", "enabled", "pack_from", "prove", "read_declaration",
]
