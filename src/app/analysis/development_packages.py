"""Product code that imports a package its manifest declares for development only (plan PQ.10).

Measured on a stored product: the service's own module imported a test client its manifest lists only among the
development packages, to give its tests a helper; its container installs without them, so the product would fail
at start. Nothing that runs during a build notices: the development packages are installed there.

One reader per language, named by the language table (`LanguageSupport.development_only`): what its manifests
declare for development only (and not for running too), and the packages a source file imports. A language with no
reader is not read. In a package that is bundled for a page (its manifest names a bundler) only the files its own
scripts start are read: a bundled page's imports are resolved at build time, where development packages belong.
"""
from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


@dataclass(frozen=True)
class Imported:
    """A product file's import of a package declared for development only."""

    file: str
    line: int
    package: str
    manifest: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line} imports `{self.package}`, declared for development only in {self.manifest}"


def _as_named(name: str) -> str:
    return name


@dataclass(frozen=True)
class Reader:
    #: The manifests it reads, by file name.
    manifests: tuple[str, ...]
    #: (development-only packages, the files only to be read in this package or None for all) of one manifest.
    declared: Callable[[Path], tuple[set[str], set[str] | None]]
    #: The packages a file's text imports, each with its line.
    imports: Callable[[str], list[tuple[int, str]]]
    #: The name an import is matched under, and a declared package's.
    key: Callable[[str], str] = _as_named


# --------------------------------------------------------------------------------------------------------------
# npm
# --------------------------------------------------------------------------------------------------------------

#: Packages that bundle a page's sources at build time.
_BUNDLERS = frozenset({"vite", "webpack", "rollup", "esbuild", "parcel", "next", "nuxt", "@angular/cli",
                       "@angular-devkit/build-angular", "react-scripts", "@sveltejs/kit", "astro", "@remix-run/dev"})
_JS_IMPORT = re.compile(
    r"""(?:^|[^\w$.])(?:import\s+(?:[\w$*{}\s,]+?\s+from\s+)?|export\s+[\w$*{}\s,]+?\s+from\s+|require\s*\(\s*|import\s*\(\s*)"""
    r"""["']([^"'\s]+)["']""", re.M)
_SCRIPT_FILE = re.compile(r"""(?:^|[\s"'=])((?:\./)?[\w./-]+\.(?:[cm]?js|[cm]?ts))\b""")


def _npm_declared(manifest: Path) -> tuple[set[str], set[str] | None]:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    runs = {name for key in ("dependencies", "peerDependencies", "optionalDependencies")
            for name in (data.get(key) or {})}
    development = set(data.get("devDependencies") or {}) - runs
    if not (_BUNDLERS & (runs | development)):
        return development, None
    started = {match.lstrip("./") for command in (data.get("scripts") or {}).values() if isinstance(command, str)
               for match in _SCRIPT_FILE.findall(command)}
    return development, started


def _npm_package(specifier: str) -> str:
    if specifier.startswith((".", "/", "node:")) or ":" in specifier:
        return ""
    parts = specifier.split("/")
    return "/".join(parts[:2]) if specifier.startswith("@") else parts[0]


def _npm_imports(text: str) -> list[tuple[int, str]]:
    found = []
    for match in _JS_IMPORT.finditer(text):
        package = _npm_package(match.group(1))
        if package:
            found.append((text.count("\n", 0, match.start(1)) + 1, package))
    return found


# --------------------------------------------------------------------------------------------------------------
# Python
# --------------------------------------------------------------------------------------------------------------

#: Groups of optional or grouped dependencies that are for development by their name.
_DEVELOPMENT_GROUP = re.compile(r"^(?:dev|devel|development|test|tests|testing|lint|typing|docs|ci)$", re.I)
_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_PY_IMPORT = re.compile(r"^[ \t]*(?:from[ \t]+([A-Za-z_]\w*)[\w.]*[ \t]+import\b|import[ \t]+([A-Za-z_]\w*))", re.M)


def _py_key(name: str) -> str:
    return re.sub(r"[-.]+", "_", name).lower()


def _names(requirements: Iterable[str]) -> set[str]:
    return {m.group(1) for line in requirements if isinstance(line, str)
            if not line.strip().startswith(("#", "-")) if (m := _REQUIREMENT_NAME.match(line))}


def _requirements_file(path: Path) -> set[str]:
    return _names(path.read_text(encoding="utf-8").splitlines()) if path.is_file() else set()


def _python_declared(manifest: Path) -> tuple[set[str], set[str] | None]:
    runs: set[str] = set()
    development: set[str] = set()
    if manifest.name == "pyproject.toml":
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        project = data.get("project") or {}
        runs |= _names(project.get("dependencies") or [])
        for group, requirements in (project.get("optional-dependencies") or {}).items():
            (development if _DEVELOPMENT_GROUP.match(group) else runs).update(_names(requirements))
        for group, requirements in (data.get("dependency-groups") or {}).items():
            if _DEVELOPMENT_GROUP.match(group):
                development |= _names(requirements)
        poetry = (data.get("tool") or {}).get("poetry") or {}
        runs |= set(poetry.get("dependencies") or {}) - {"python"}
        development |= set(poetry.get("dev-dependencies") or {})
        for group, table in (poetry.get("group") or {}).items():
            if _DEVELOPMENT_GROUP.match(group):
                development |= set((table or {}).get("dependencies") or {})
    else:
        runs |= _requirements_file(manifest)
        folder = manifest.parent
        for name in ("requirements-dev.txt", "requirements-test.txt", "requirements_dev.txt", "dev-requirements.txt",
                     "test-requirements.txt"):
            development |= _requirements_file(folder / name)
    if manifest.name == "pyproject.toml":
        runs |= _requirements_file(manifest.parent / "requirements.txt")
    return {name for name in development if _py_key(name) not in {_py_key(n) for n in runs}}, None


def _python_imports(text: str) -> list[tuple[int, str]]:
    return [(text.count("\n", 0, m.start()) + 1, m.group(1) or m.group(2)) for m in _PY_IMPORT.finditer(text)]


#: Each reader by the name the language table gives it (`LanguageSupport.development_only`).
READERS: dict[str, Reader] = {
    "npm": Reader(("package.json",), _npm_declared, _npm_imports),
    "python": Reader(("pyproject.toml", "requirements.txt"), _python_declared, _python_imports, _py_key),
}


def imported_in(project: Path, sources: dict[Path, str]) -> tuple[list[Imported], int]:
    """Every import in `sources` (the product's own files, no tests) of a package the nearest manifest of its language
    declares for development only, and how many manifests declared any. Never raises."""
    from app.stacks.languages import LANGUAGES

    found: list[Imported] = []
    declaring: set[Path] = set()
    cache: dict[Path, tuple[set[str], set[str] | None] | None] = {}
    for path, text in sources.items():
        for row in LANGUAGES:
            reader = READERS.get(row.development_only) if isinstance(row.development_only, str) else None
            if reader is None or path.suffix.lower() not in row.suffixes:
                continue
            manifest = _nearest(path, project, reader.manifests)
            if manifest is None:
                continue
            if manifest not in cache:
                try:
                    cache[manifest] = reader.declared(manifest)
                except Exception:  # noqa: BLE001 - a manifest that cannot be read declares nothing
                    cache[manifest] = None
            declared = cache[manifest]
            if not declared or not declared[0]:
                continue
            development, only = declared
            declaring.add(manifest)
            within = path.relative_to(manifest.parent).as_posix()
            if only is not None and within not in only:
                continue
            keys = {reader.key(name): name for name in development}
            for line, package in reader.imports(text):
                if reader.key(package) in keys:
                    found.append(Imported(path.relative_to(project).as_posix(), line, package,
                                          manifest.relative_to(project).as_posix()))
            break
    return found, len(declaring)


def _nearest(path: Path, project: Path, names: tuple[str, ...]) -> Path | None:
    folder = path.parent
    while True:
        for name in names:
            if (folder / name).is_file():
                return folder / name
        if folder == project or project not in folder.parents:
            return None
        folder = folder.parent


__all__ = ["Imported", "READERS", "imported_in"]
