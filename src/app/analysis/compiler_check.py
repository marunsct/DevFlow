"""What the compiler says about a project in a compiled language, before its tests run.

JavaScript and TypeScript are read by the TypeScript language service and
Python by Pyright (`app.analysis.language_service`), file by file, as an IDE
underlines them. Every other language got a parse of each file it wrote and
nothing more, so a name nothing defines, a call with the wrong arguments or an
import of a package never added was first heard of as a failed build in a test
round - a round and a fix stage later.

For a compiled language the compiler is the language service: gopls, rust-
analyzer, the C# and Java language servers all report what the compiler
reports. So this asks the compiler, once for the whole project, through the
same sandbox and environment every stage's commands use (the project's own
dependency caches are found there), and keeps only errors - never a warning,
never a lint. A project whose toolchain is not installed, or whose check does
not finish, says nothing: a check that cannot run must not stand in a run's way.

Which languages have which check, and why the rest have none:

    Go          go test -run '^$' ./...    compiles code and tests, runs none
    Rust        cargo check --all-targets  the compiler front end, no codegen
    Java/Kotlin mvn test-compile, or gradle testClasses (the build the project has)
    C#          dotnet build               what the C# language server reports
    Swift       swift build
    PHP         PHPStan level 0, only when the project installed it: undefined
                classes, functions and methods. PHP itself has only `php -l`,
                a parse, which the write already does with its grammar.
    Ruby        nothing beyond the parse: no checker finds an undefined name in
                Ruby without running it; its tests are the check.
"""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

logger = logging.getLogger(__name__)

#: The most findings one check reports.
MOST_FINDINGS = 12

#: Runs one argv in the project: (argv, category, project directory relative to
#: the workspace) -> {"returncode", "stdout", "stderr"} or {"error"}.
Runner = Callable[[Sequence[str], str, str], dict]


@dataclass(frozen=True)
class Checker:
    language: str
    #: Source files this checker reads.
    suffixes: tuple[str, ...]
    #: project directory -> the command, or None when this project is not one it checks.
    command: Callable[[Path], list[str] | None]


def _exists(project: Path, *names: str) -> bool:
    return any((project / name).exists() for name in names)


def _gradle(project: Path) -> list[str] | None:
    if not _exists(project, "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"):
        return None
    # The installed Gradle, not a project's wrapper: the wrapper is a script the
    # project wrote, and the sandbox runs only the toolchain's own programs.
    return ["gradle", "--quiet", "--console=plain", "testClasses"]


def _phpstan(project: Path) -> list[str] | None:
    if not (project / "vendor" / "bin" / "phpstan").is_file():
        return None
    paths = [name for name in ("app", "src", "routes", "tests") if (project / name).is_dir()]
    if not paths:
        return None
    return ["vendor/bin/phpstan", "analyse", "--no-progress", "--error-format=raw", "--level=0", *paths]


CHECKERS: tuple[Checker, ...] = (
    Checker("go", (".go",), lambda p: ["go", "test", "-count=1", "-run", "^$", "./..."] if _exists(p, "go.mod") else None),
    Checker("rust", (".rs",), lambda p: ["cargo", "check", "--quiet", "--all-targets", "--message-format=short"]
            if _exists(p, "Cargo.toml") else None),
    Checker("java", (".java", ".kt", ".kts", ".scala"),
            lambda p: ["mvn", "--quiet", "--batch-mode", "-DskipTests", "test-compile"] if _exists(p, "pom.xml") else _gradle(p)),
    Checker("csharp", (".cs",), lambda p: ["dotnet", "build", "--nologo", "-v", "q", "-clp:NoSummary"]
            if any(p.glob("*.csproj")) or any(p.glob("*.sln")) else None),
    Checker("swift", (".swift",), lambda p: ["swift", "build"] if _exists(p, "Package.swift") else None),
    Checker("php", (".php",), _phpstan),
)

#: Every suffix some checker reads.
SUFFIXES = tuple(suffix for checker in CHECKERS for suffix in checker.suffixes)

#: How each compiler writes an error, each as (file, line, message).
_ERRORS = (
    # dotnet: path(12,5): error CS0103: The name 'x' does not exist ... [project.csproj]
    re.compile(r"^(?P<file>[^\s()]+\.cs)\((?P<line>\d+),\d+\): error (?P<code>\w+): (?P<msg>.+?)(?:\s+\[[^\]]+\])?$"),
    # maven javac: [ERROR] /path/X.java:[12,5] cannot find symbol
    re.compile(r"^\[ERROR\] (?:file://)?(?P<file>\S+\.(?:java|kt|scala)):\[(?P<line>\d+),\d+\] (?P<msg>.+)$"),
    # kotlinc: e: file:///path/X.kt:12:5 Unresolved reference: foo
    re.compile(r"^e: (?:file://)?(?P<file>\S+\.kts?):(?P<line>\d+):\d+ (?P<msg>.+)$"),
    # phpstan raw: /path/X.php:12:Call to an undefined method ...
    re.compile(r"^(?P<file>\S+\.php):(?P<line>\d+):(?P<msg>.+)$"),
    # go, rust (short), swift, javac via gradle: path:12:5: [error[E0425]:|error:] message
    re.compile(
        r"^(?:vet: )?(?P<file>[^\s:]+\.(?:go|rs|swift|java|scala)):(?P<line>\d+)(?::\d+)?:\s*"
        r"(?P<level>error(?:\[\w+\])?:|warning(?:\[\w+\])?:|note:)?\s*(?P<msg>.+)$"
    ),
)


def checker_for(project: Path, files: Sequence[str] = ()) -> tuple[Checker, list[str]] | None:
    """The checker for this project and its command, or None.

    With `files`, only a checker that reads one of them: a stage that changed
    nothing in a compiled language is not made to wait for its compiler.
    """
    for checker in CHECKERS:
        if files and not any(str(name).lower().endswith(checker.suffixes) for name in files):
            continue
        command = checker.command(project)
        if command:
            return checker, command
    return None


def _relative(path: str, project: Path, workspace: Path) -> str:
    """A compiler's path as a path relative to the workspace."""
    path = path.removeprefix("file://")
    candidate = Path(path)
    if candidate.is_absolute():
        for base in (project.resolve(), Path("/workspace") / project.name):
            try:
                return (project / candidate.relative_to(base)).relative_to(workspace).as_posix()
            except ValueError:
                continue
        try:
            return candidate.relative_to(workspace.resolve()).as_posix()
        except ValueError:
            return candidate.as_posix()
    return (project / path.removeprefix("./")).relative_to(workspace).as_posix()


def errors_in(output: str, project: Path, workspace: Path) -> list[dict]:
    """Every error a compiler's output names, as {file, line, message, code}, deduplicated."""
    found: list[dict] = []
    seen: set[tuple[str, int, str]] = set()
    lines = output.splitlines()
    for index, raw in enumerate(lines):
        line = raw.strip()
        for pattern in _ERRORS:
            match = pattern.match(line)
            if not match:
                continue
            level = (match.groupdict().get("level") or "").lower()
            if level.startswith(("warning", "note")):
                break
            message = match.group("msg").strip()
            if message.lower().startswith(("warning", "note:")):
                break
            # javac names what it could not find on the line after.
            following = lines[index + 1].strip().removeprefix("[ERROR]").strip() if index + 1 < len(lines) else ""
            if following.startswith("symbol:"):
                message = f"{message} ({' '.join(following.split())})"
            code = match.groupdict().get("code") or ((match.groupdict().get("level") or "error").rstrip(":"))
            entry = (_relative(match.group("file"), project, workspace), int(match.group("line")), message)
            if entry not in seen:
                seen.add(entry)
                found.append({"file": entry[0], "line": entry[1], "message": message, "code": code})
            break
        if len(found) >= MOST_FINDINGS:
            break
    return found


def findings(
    workspace: str | Path, project: str, files: Sequence[str] = (), *, run: Runner | None = None,
) -> list[dict]:
    """The compiler's errors for `project` (relative to `workspace`), or [] when it cannot say.

    `files` are workspace-relative paths a stage changed; see `checker_for`.
    """
    root = Path(workspace)
    directory = root / project if project else root
    if not directory.is_dir():
        return []
    chosen = checker_for(directory, files)
    if chosen is None:
        return []
    checker, command = chosen
    if run is None:
        from app.stacks.scaffold import sandbox_runner

        run = sandbox_runner(root)
    try:
        outcome = run(command, "build", project)
    except Exception:  # noqa: BLE001 - a check that cannot run says nothing
        logger.debug("The %s compiler check could not run", checker.language, exc_info=True)
        return []
    if "returncode" not in outcome or str(outcome.get("returncode")).strip() == "0":
        return []
    output = f"{outcome.get('stdout') or ''}\n{outcome.get('stderr') or ''}"
    return errors_in(output, directory, root)


def toolchain_present(language: str) -> bool:
    """Whether this environment has the compiler for `language`."""
    executable = {"go": "go", "rust": "cargo", "java": "javac", "csharp": "dotnet", "swift": "swift", "php": "php"}
    return shutil.which(executable.get(language, language)) is not None


__all__ = ["CHECKERS", "Checker", "SUFFIXES", "checker_for", "errors_in", "findings", "toolchain_present"]
