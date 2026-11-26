"""The project files a file's imports name, one resolver per way a language names them (plan KG.2).

Each language's row of `app.stacks.languages` names its resolver (`TreeReading.resolver`); the import texts come from
its syntax tree (`app.analysis.parsed_definitions`). A resolver names only files of the project: an import of a
package from a registry names none, and a name it cannot place is left out rather than guessed.

- `module_path`: the module the nearest `go.mod` declares, then the package folder the rest of the path names.
- `declared_package`: the package or namespace each file declares, and the type the import's last part names.
- `crate_modules`: `mod` declarations and `crate::`, `self::`, `super::` and the crate's own name, through the
  module files the nearest `Cargo.toml`'s `src/` holds.
- `relative_require`: a path relative to the file, and a path under a `lib/` folder on the way up.
- `autoload_namespace`: the `autoload` and `autoload-dev` `psr-4` prefixes of the nearest `composer.json`, then the
  declared namespaces.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Callable, Iterable

from app.analysis.parsed_definitions import Parsed


class Project:
    """What the resolvers look an import up in: the project's source files, each file's reading, and its manifests."""

    def __init__(self, root: Path, parsed: dict[Path, Parsed], texts: dict[Path, str] | None = None) -> None:
        self.root = root
        self.parsed = parsed
        self.texts = texts or {}
        self._words: dict[Path, frozenset[str]] = {}
        self.files = {os.path.normpath(str(path)) for path in parsed}
        self._namespaces: dict[str, list[Path]] | None = None
        self._nearest: dict[tuple[str, str], Path | None] = {}
        self._read: dict[Path, str] = {}
        self._in_folder: dict[str, list[Path]] | None = None

    def has(self, path: Path | str) -> Path | None:
        """The source file at `path`, normalised; None when the project has no such source file."""
        normal = os.path.normpath(str(path))
        return Path(normal) if normal in self.files else None

    def declaring(self, namespace: str) -> list[Path]:
        """The files that declare `namespace`."""
        if self._namespaces is None:
            self._namespaces = {}
            for path, parsed in self.parsed.items():
                for declared in parsed.namespaces:
                    self._namespaces.setdefault(declared, []).append(path)
        return self._namespaces.get(namespace, [])

    def in_folder(self, folder: Path) -> list[Path]:
        """The source files directly in `folder`."""
        if self._in_folder is None:
            self._in_folder = {}
            for path in self.parsed:
                self._in_folder.setdefault(os.path.normpath(str(path.parent)), []).append(path)
        return self._in_folder.get(os.path.normpath(str(folder)), [])

    def words_of(self, path: Path) -> frozenset[str]:
        """The names `path`'s text uses."""
        if path not in self._words:
            self._words[path] = frozenset(_WORD.findall(self.texts.get(path, "")))
        return self._words[path]

    def nearest(self, path: Path, name: str) -> Path | None:
        """The manifest `name` in `path`'s folder or the nearest one above it, within the workspace."""
        folder = path.parent
        key = (str(folder), name)
        if key not in self._nearest:
            found = None
            for candidate in (folder, *folder.parents):
                if (candidate / name).is_file():
                    found = candidate / name
                    break
                if candidate == self.root or not candidate.is_relative_to(self.root):
                    break
            self._nearest[key] = found
        return self._nearest[key]

    def text_of(self, manifest: Path) -> str:
        if manifest not in self._read:
            try:
                self._read[manifest] = manifest.read_text(encoding="utf-8", errors="replace")
            except OSError:
                self._read[manifest] = ""
        return self._read[manifest]


_WORD = re.compile(r"[A-Za-z_]\w*")


def _unquoted(text: str) -> str:
    return text.strip().strip("\"'`")


# --------------------------------------------------------------------------- module path and package folder

_MODULE_LINE = re.compile(r"^\s*module\s+(\S+)", re.M)


def module_path(path: Path, imports: Iterable[tuple[str, str]], project: Project) -> set[Path]:
    """An import path under the module of the nearest `go.mod` names the files of that package folder."""
    manifest = project.nearest(path, "go.mod")
    module = _MODULE_LINE.search(project.text_of(manifest)) if manifest else None
    if manifest is None or module is None:
        return set()
    name, found = module.group(1).strip("\"'"), set()
    for _capture, text in imports:
        spec = _unquoted(text)
        if spec != name and not spec.startswith(name + "/"):
            continue
        folder = manifest.parent / spec[len(name):].lstrip("/")
        found |= {f for f in project.in_folder(folder) if not f.name.endswith("_test.go")}
    return found


# --------------------------------------------------------------------------- declared package or namespace

_LEADING = ("global", "using", "import", "static")


def _declared_name(text: str) -> str:
    """`app.model.Note` from `import app.model.Note;`, `using static A.B;`, `using X = A.B;` or `import a.B as C`."""
    words = " ".join(text.split()).rstrip(";").strip().split(" ")
    while words and words[0] in _LEADING:
        words = words[1:]
    said = " ".join(words)
    if "=" in said:
        said = said.split("=", 1)[1]
    said = re.sub(r"\s+as\s+\w+$", "", said)
    return "".join(said.split())


def _by_name(project: Project, namespace: str, name: str) -> list[Path]:
    files = project.declaring(namespace)
    return [f for f in files if name in project.parsed[f].top_names] or [f for f in files if f.stem == name]


def declared_package(path: Path, imports: Iterable[tuple[str, str]], project: Project, separator: str = ".") -> set[Path]:
    """An import names the files declaring its package or namespace: all of them for a namespace or a `.*`, else
    the one defining the type it names (a static import's member is the type's)."""
    found: set[Path] = set()
    for _capture, text in imports:
        name = _declared_name(text).lstrip(separator)
        found |= _declared_files(project, name, separator, path)
    return found


def _declared_files(project: Project, name: str, separator: str, importer: Path | None = None) -> set[Path]:
    wildcard = name.endswith(separator + "*")
    name = name.removesuffix(separator + "*")
    if not name:
        return set()
    if project.declaring(name) and (wildcard or separator == "."):
        # `a.b.*`, or a namespace a `using` opens whole: the files of it whose names the importer uses. All of them
        # would make every file of a large namespace a neighbour of each file that opens it.
        used = project.words_of(importer) if importer is not None else frozenset()
        return {f for f in project.declaring(name) if project.parsed[f].top_names & used}
    parts = name.split(separator)
    for cut in range(len(parts) - 1, 0, -1):
        namespace = separator.join(parts[:cut])
        if project.declaring(namespace):
            return set(_by_name(project, namespace, parts[cut]))
    return set()


# --------------------------------------------------------------------------- crate modules

_PACKAGE_NAME = re.compile(r"^\[package\][^\[]*?^\s*name\s*=\s*[\"']([^\"']+)[\"']", re.M | re.S)
_GENERIC = re.compile(r"<[^<>]*>")


def _use_paths(text: str, prefix: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    """Each path a `use` tree names: `a::{b, c::{d, self}}` is a::b, a::c::d and a::c."""
    said = re.sub(r"\s+as\s+\w+", "", text).replace(" ", "").replace("\n", "").strip()
    if not said:
        return []
    opening = said.find("{")
    if opening == -1:
        parts = tuple(p for p in said.split("::") if p and p != "*")
        if parts and parts[-1] == "self":
            parts = parts[:-1]
        return [prefix + parts]
    head = tuple(p for p in said[:opening].split("::") if p)
    inner, depth, start, found = said[opening + 1:said.rfind("}")], 0, 0, []
    for at, char in enumerate(inner + ","):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        elif char == "," and depth == 0:
            found += _use_paths(inner[start:at], prefix + head)
            start = at + 1
    return found


def _module_folder(file: Path) -> Path:
    """The folder a module file's own `mod` declarations and child modules sit in."""
    return file.parent if file.name in ("lib.rs", "main.rs", "mod.rs") else file.parent / file.stem


def _module_file(project: Project, folder: Path, name: str) -> Path | None:
    return project.has(folder / f"{name}.rs") or project.has(folder / name / "mod.rs")


def crate_modules(path: Path, imports: Iterable[tuple[str, str]], project: Project) -> set[Path]:
    """`mod x;` names `x.rs` or `x/mod.rs` beside it; a path from `crate`, `self`, `super` or the crate's own name
    names the deepest module file it walks through, else the crate's root file."""
    imports = list(imports)
    manifest = project.nearest(path, "Cargo.toml")
    if manifest is None:
        return set()
    source = manifest.parent / "src"
    package = _PACKAGE_NAME.search(project.text_of(manifest))
    crate_name = package.group(1).replace("-", "_") if package else ""
    crate_root = project.has(source / "lib.rs") or project.has(source / "main.rs")
    here = _module_folder(path)
    declared_here = {_unquoted(text) for capture, text in imports if capture == "import.module"}
    found: set[Path] = set()
    for capture, text in imports:
        if capture == "import.module":
            module = _module_file(project, here, _unquoted(text))
            if module:
                found.add(module)
            continue
        if capture == "import.path":
            said = text
            while _GENERIC.search(said):
                said = _GENERIC.sub("", said)
            paths = [tuple(p for p in said.replace(" ", "").split("::") if p)]
        else:
            paths = _use_paths(text)
        for parts in paths:
            target = _crate_path(project, parts, path, here, source, crate_name, crate_root, declared_here)
            if target is not None:
                found.add(target)
    return found


def _crate_path(project: Project, parts: tuple[str, ...], path: Path, here: Path, source: Path, crate_name: str,
                crate_root: Path | None, declared_here: set[str]) -> Path | None:
    if not parts:
        return None
    first, rest = parts[0], parts[1:]
    if first == "crate" or (crate_name and first == crate_name):
        folder = source
        fallback = crate_root if first == "crate" else project.has(source / "lib.rs")
    elif first == "self":
        folder, fallback = here, None
    elif first == "super":
        folder = here
        while rest[:1] == ("super",):
            rest = rest[1:]
            folder = folder.parent
        folder = folder.parent
        fallback = (project.has(folder.with_suffix(".rs")) or project.has(folder / "mod.rs")
                    or project.has(folder / "lib.rs") or project.has(folder / "main.rs"))
    elif first in declared_here:
        folder, fallback, rest = here, None, parts
    else:
        return None
    deepest = None
    for name in rest:
        module = _module_file(project, folder, name)
        if module is None:
            break
        deepest, folder = module, folder / name
    return deepest or fallback


# --------------------------------------------------------------------------- relative require

def relative_require(path: Path, imports: Iterable[tuple[str, str]], project: Project) -> set[Path]:
    """`require_relative` names a file relative to the requiring one; `require` a file under a `lib/` folder in the
    requiring file's folder or one above it."""
    found: set[Path] = set()
    for capture, text in imports:
        spec = _unquoted(text)
        if not spec:
            continue
        named = spec if spec.endswith(".rb") else spec + ".rb"
        if capture == "import.relative":
            target = project.has(path.parent / named)
        else:
            target = None
            for folder in (path.parent, *path.parent.parents):
                target = project.has(folder / "lib" / named)
                if target is not None or folder == project.root or not folder.is_relative_to(project.root):
                    break
        if target is not None:
            found.add(target)
    return found


# --------------------------------------------------------------------------- autoload namespace

def _use_names(text: str) -> list[str]:
    """Each name a `use` statement imports: `use A\\{B, C as D};` is A\\B and A\\C."""
    said = " ".join(text.split()).rstrip(";").strip()
    said = re.sub(r"^use\s+(?:function\s+|const\s+)?", "", said)
    said = re.sub(r"\s+as\s+\w+", "", said).replace(" ", "")
    if "{" in said:
        head, inner = said.split("{", 1)
        return [head + part for part in inner.rstrip("}").split(",") if part]
    return [part for part in said.split(",") if part]


def _psr4(project: Project, manifest: Path) -> list[tuple[str, list[Path]]]:
    try:
        declared = json.loads(project.text_of(manifest) or "{}")
    except ValueError:
        return []
    found: list[tuple[str, list[Path]]] = []
    for section in ("autoload", "autoload-dev"):
        prefixes = ((declared.get(section) or {}).get("psr-4") or {}) if isinstance(declared, dict) else {}
        for prefix, folders in prefixes.items():
            folders = [folders] if isinstance(folders, str) else list(folders or [])
            found.append((str(prefix), [manifest.parent / str(f) for f in folders]))
    return sorted(found, key=lambda item: -len(item[0]))


def autoload_namespace(path: Path, imports: Iterable[tuple[str, str]], project: Project) -> set[Path]:
    """A class name names the file its `psr-4` prefix maps it to, else the file declaring its namespace that
    defines it. A name written without a leading backslash outside a `use` is read in the file's own namespace."""
    manifest = project.nearest(path, "composer.json")
    prefixes = _psr4(project, manifest) if manifest else []
    own = project.parsed[path].namespaces[:1] if path in project.parsed else ()
    found: set[Path] = set()
    for capture, text in imports:
        if capture == "import":
            for name in _use_names(text):
                found |= _autoloaded(project, prefixes, name.lstrip("\\"))
            continue
        said = "".join(text.split())
        # Written without a leading backslash, a name is first read in the file's own namespace.
        for name in [said.lstrip("\\")] if said.startswith("\\") or not own else [f"{own[0]}\\{said}", said]:
            target = _autoloaded(project, prefixes, name)
            if target:
                found |= target
                break
    return found


def _autoloaded(project: Project, prefixes: list[tuple[str, list[Path]]], name: str) -> set[Path]:
    for prefix, folders in prefixes:
        if name.startswith(prefix):
            for folder in folders:
                target = project.has(folder / (name[len(prefix):].replace("\\", "/") + ".php"))
                if target:
                    return {target}
    return _declared_files(project, name, "\\")


RESOLVERS: dict[str, Callable[[Path, Iterable[tuple[str, str]], Project], set[Path]]] = {
    "module_path": module_path,
    "declared_package": declared_package,
    "crate_modules": crate_modules,
    "relative_require": relative_require,
    "autoload_namespace": autoload_namespace,
}


def resolved(path: Path, resolver: str, project: Project) -> set[Path]:
    """The project files `path`'s imports name, by its language's resolver; the file itself is never one. Never
    raises."""
    parsed = project.parsed.get(path)
    how = RESOLVERS.get(resolver)
    if parsed is None or how is None or not parsed.imports:
        return set()
    try:
        return {target for target in how(path, parsed.imports, project) if target != path}
    except Exception:  # noqa: BLE001 - an import this cannot place names nothing
        return set()


__all__ = ["Project", "RESOLVERS", "resolved"]
