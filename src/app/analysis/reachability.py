"""Source files nothing the product runs reaches through its imports.

Measured on one run: every acceptance and unit test passed, and 1,883 of the
product's 3,167 lines were modules nothing imported. The service ran from one
`main.py` that defined its models, schemas, auth and routes again; the planned
`models.py`, `schemas.py`, `auth.py` and three router modules imported each
other and nothing imported them. The page ran from one `App.tsx` whose comment
read "In a real app, these would be imported from './pages/LoginPage'", and its
pages, components and contexts were the same kind of island. Tests measure
behaviour, so a second copy the product never loads passes every one of them -
and the next fixer may change the copy that does not run.

Decided from the files: the import graph from the pack's entrypoints, with one
row per language family in `FAMILIES`. Only for a pack whose code is wired by
imports (`StackPack.wired_by_imports`): a framework that loads modules by where
they sit or by name - file-system routes, autoloading, settings strings - would
read as unreached here, so its packs leave the flag off.
"""

from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from app.analysis.walk import files_under

#: Folders that are never the product's own code.
_NOT_CODE = (
    "node_modules", ".venv", "venv", ".git", "dist", "build", "__pycache__", ".harness",
    "test-results", "playwright-report", "coverage", ".pytest_cache", ".agent-home",
)

#: Folders tests live in, in every family.
_TEST_FOLDERS = frozenset({"tests", "test", "__tests__", "spec", "e2e"})


@dataclass(frozen=True)
class Family:
    """How one language family's files name the files they import."""

    suffixes: tuple[str, ...]
    #: (the importing file, the project root, aliases) -> the project files it imports.
    imports: Callable[[Path, str, Path, dict[str, str]], set[Path]]
    #: The names a file defines, to say which reached file a copy repeats.
    defines: re.Pattern[str]
    #: Globs of file names no import reaches by design: a package's marker, a
    #: type declaration, a tool's configuration.
    never_imported: tuple[str, ...]
    #: Folders a tool runs on its own, not through an import (migrations).
    run_by_a_tool: frozenset[str]


# --------------------------------------------------------------------------- python

_PY_FROM = re.compile(r"^[ \t]*from[ \t]+(\.*)([\w.]*)[ \t]+import[ \t]+(\([^)]*\)|[^\n#]+)", re.M)
_PY_IMPORT = re.compile(r"^[ \t]*import[ \t]+([\w.]+(?:[ \t]*,[ \t]*[\w.]+)*)", re.M)


def _python_module(base: Path, dotted: str) -> list[Path]:
    """The files `dotted` names under `base`: a module and every package on its way."""
    if not dotted:
        return [base / "__init__.py"]
    parts = dotted.split(".")
    found = []
    for at in range(1, len(parts) + 1):
        package = base.joinpath(*parts[:at])
        if (package / "__init__.py").is_file():
            found.append(package / "__init__.py")
    module = base.joinpath(*parts)
    if module.with_suffix(".py").is_file():
        found.append(module.with_suffix(".py"))
    return found


def _python_imports(path: Path, text: str, root: Path, _aliases: dict[str, str]) -> set[Path]:
    bases = [root, root / "src"]
    found: set[Path] = set()
    for match in _PY_FROM.finditer(text):
        dots, dotted, names = match.group(1), match.group(2), match.group(3)
        if dots:
            here = path.parent
            for _ in range(len(dots) - 1):
                here = here.parent
            candidates = [here]
        else:
            candidates = bases
        for base in candidates:
            found.update(_python_module(base, dotted))
            # `from package import module` names a module as much as a name.
            for name in re.findall(r"\w+", names.split(" as ")[0] if "(" not in names else names):
                found.update(
                    f for f in _python_module(base, f"{dotted}.{name}" if dotted else name)
                    if f.name != "__init__.py" or f.parent.name == name
                )
    for match in _PY_IMPORT.finditer(text):
        for dotted in re.split(r"[ \t]*,[ \t]*", match.group(1)):
            for base in bases:
                found.update(_python_module(base, dotted.strip()))
    return {f.resolve() for f in found}


# --------------------------------------------------------------------------- scripts

_SCRIPT_SPECIFIER = re.compile(
    r"""(?:^|\n)[ \t]*(?:import|export)\b[^;\n]*?from[ \t]*['"]([^'"]+)['"]"""
    r"""|(?:^|\n)[ \t]*import[ \t]*['"]([^'"]+)['"]"""
    r"""|\bimport\(\s*['"]([^'"]+)['"]\s*\)"""
    r"""|\brequire\(\s*['"]([^'"]+)['"]\s*\)"""
)
_SCRIPT_TRIED = (
    "", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".vue", ".svelte",
    "/index.ts", "/index.tsx", "/index.js", "/index.jsx", "/index.mjs",
)
#: A TypeScript module imported by the name it compiles to: `./a.js` is `a.ts`.
_COMPILED_NAME = re.compile(r"\.(?:m?js|jsx)$")


def _script_file(base: Path) -> Path | None:
    for suffix in _SCRIPT_TRIED:
        candidate = Path(str(base) + suffix) if suffix else base
        if candidate.is_file():
            return candidate
    if _COMPILED_NAME.search(base.name):
        stem = Path(_COMPILED_NAME.sub("", str(base)))
        for suffix in (".ts", ".tsx", ".mts"):
            if Path(str(stem) + suffix).is_file():
                return Path(str(stem) + suffix)
    return None


def _script_imports(path: Path, text: str, root: Path, aliases: dict[str, str]) -> set[Path]:
    found: set[Path] = set()
    for match in _SCRIPT_SPECIFIER.finditer(text):
        specifier = next((g for g in match.groups() if g), "")
        if specifier.startswith("."):
            target = _script_file((path.parent / specifier).resolve())
        else:
            prefix = next((p for p in aliases if specifier.startswith(p)), None)
            if prefix is None:
                continue
            target = _script_file((root / aliases[prefix] / specifier[len(prefix):]).resolve())
        # A stylesheet or an image is imported too; only code is followed.
        if target is not None and family_of(target.name) == "script":
            found.add(target.resolve())
    return found


def _script_aliases(root: Path) -> dict[str, str] | None:
    """`compilerOptions.paths` prefixes -> folders; None when one is declared and cannot be read."""
    aliases: dict[str, str] = {}
    for name in ("tsconfig.json", "jsconfig.json", "tsconfig.app.json"):
        config = root / name
        if not config.is_file():
            continue
        text = config.read_text(encoding="utf-8", errors="replace")
        if '"paths"' not in text:
            continue
        try:
            options = json.loads(re.sub(r"(?m)^\s*//.*$", "", text)).get("compilerOptions") or {}
        except ValueError:
            return None
        base = str(options.get("baseUrl") or ".")
        for pattern, targets in (options.get("paths") or {}).items():
            if not targets or not str(pattern).endswith("*") or not str(targets[0]).endswith("*"):
                return None
            aliases[str(pattern)[:-1]] = str(Path(base) / str(targets[0])[:-1])
    return aliases


FAMILIES: dict[str, Family] = {
    "python": Family(
        suffixes=(".py",),
        imports=_python_imports,
        defines=re.compile(r"^[ \t]*(?:async[ \t]+)?(?:def|class)[ \t]+([A-Za-z]\w*)", re.M),
        never_imported=("__init__.py", "__main__.py"),
        run_by_a_tool=frozenset({"migrations", "alembic"}),
    ),
    "script": Family(
        suffixes=(".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte"),
        imports=_script_imports,
        defines=re.compile(
            r"^[ \t]*(?:export[ \t]+)?(?:default[ \t]+)?(?:async[ \t]+)?"
            r"(?:function\*?[ \t]+([A-Za-z_$][\w$]*)|class[ \t]+([A-Za-z_$][\w$]*)"
            r"|(?:const|let)[ \t]+([A-Za-z_$][\w$]*)[ \t]*(?::[^=\n]+)?=[ \t]*(?:async[ \t]*)?(?:\(|function))",
            re.M,
        ),
        never_imported=("*.d.ts", "*.config.*"),
        run_by_a_tool=frozenset({"public"}),
    ),
}


def family_of(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    return next((name for name, row in FAMILIES.items() if suffix in row.suffixes), "")


def _defined(text: str, family: Family) -> set[str]:
    return {next((g for g in m.groups() if g), "") for m in family.defines.finditer(text)} - {""}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _is_a_test(relative: str, is_unit_test: Callable[[str], bool]) -> bool:
    """A test by the pack's own names for one, or by the folder it sits in."""
    return is_unit_test(Path(relative).name) or bool(_TEST_FOLDERS & set(Path(relative).parts[:-1]))


@dataclass(frozen=True)
class Unreached:
    """Files of one served folder nothing the product runs imports."""

    entrypoint: str
    files: tuple[str, ...]
    lines: int
    #: (an unreached file, the reached file that defines the same names, those names)
    repeats: tuple[str, str, tuple[str, ...]] | None


def unreached_modules(
    project: Path,
    entrypoints: Iterable[str],
    is_unit_test: Callable[[str], bool] = lambda _name: False,
    kept: Iterable[str] = (),
) -> list[Unreached]:
    """For each served folder, its source files nothing reaches from an entrypoint. Never raises.

    Roots are the entrypoints, and every file that imports one directly - the
    launcher that mounts a page component, the module that starts a service's
    app. The files looked at are those of the entrypoint's family under its
    top folder, which is where the plan put the product's modules; tests,
    tool configuration and what a tool runs by itself are not imports' to reach.
    """
    try:
        return _unreached(project.resolve(), list(entrypoints), is_unit_test, set(kept))
    except Exception:  # noqa: BLE001 - a check that cannot read the files accuses nothing
        return []


def _unreached(
    project: Path, entrypoints: list[str], is_unit_test: Callable[[str], bool], kept: set[str]
) -> list[Unreached]:
    aliases = _script_aliases(project)
    files = [p.resolve() for p in files_under(project, _NOT_CODE) if family_of(p.name)]
    texts = {path: _read(path) for path in files}
    by_family: dict[str, list[str]] = {}
    for entrypoint in entrypoints:
        name = family_of(entrypoint)
        if name and (project / entrypoint).is_file() and Path(entrypoint).parent.as_posix() not in ("", "."):
            by_family.setdefault(name, []).append(entrypoint)
    found: list[Unreached] = []
    for name, served in by_family.items():
        family = FAMILIES[name]
        if name == "script" and aliases is None:
            continue  # imports through a mapping this cannot read: it would accuse what they reach
        mine = [path for path in files if family_of(path.name) == name]
        edges = {path: family.imports(path, texts[path], project, aliases or {}) for path in mine}
        roots = {(project / e).resolve() for e in served}
        roots |= {path for path, targets in edges.items() if targets & roots}
        reached: set[Path] = set()
        queue = list(roots)
        while queue:
            current = queue.pop()
            if current in reached:
                continue
            reached.add(current)
            queue.extend(t for t in edges.get(current, ()) if t not in reached)
        for entrypoint in served:
            top = project / Path(entrypoint).parts[0]
            candidates = []
            for path in mine:
                if path in reached or not path.is_relative_to(top):
                    continue
                relative = path.relative_to(project).as_posix()
                if (
                    relative in kept
                    or any(fnmatch.fnmatchcase(path.name, glob) for glob in family.never_imported)
                    or family.run_by_a_tool & set(Path(relative).parts[:-1])
                    or _is_a_test(relative, is_unit_test)
                ):
                    continue
                candidates.append(path)
            if not candidates:
                continue
            reached_here = [p for p in reached if p in texts and p.is_relative_to(top)]
            found.append(Unreached(
                entrypoint=entrypoint,
                files=tuple(sorted(p.relative_to(project).as_posix() for p in candidates)),
                lines=sum(1 for p in candidates for line in texts[p].splitlines() if line.strip()),
                repeats=_the_copy_repeated(candidates, reached_here, texts, family, project),
            ))
    return found


def _the_copy_repeated(
    unreached: list[Path], reached: list[Path], texts: dict[Path, str], family: Family, project: Path
) -> tuple[str, str, tuple[str, ...]] | None:
    """The unreached file and the reached one sharing the most defined names (two or more), or None."""
    best: tuple[int, str, str, tuple[str, ...]] | None = None
    defined = {path: _defined(texts[path], family) for path in reached}
    for path in unreached:
        names = _defined(texts[path], family)
        for other, theirs in defined.items():
            shared = tuple(sorted(names & theirs))
            if len(shared) >= 2 and (best is None or len(shared) > best[0]):
                best = (
                    len(shared),
                    path.relative_to(project).as_posix(),
                    other.relative_to(project).as_posix(),
                    shared,
                )
    return best[1:] if best else None
