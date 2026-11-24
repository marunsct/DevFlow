"""Where a Rust crate really declares a name, read from the crate's source where cargo put it, for an import the
compiler cannot resolve (the Rust half of `app.analysis.package_exports`, behind `PACKAGE_EXPORTS_NAMED`).

Measured on Rust runs, one compile round each: `use axum::extract::JsonRejection` (it is
`axum::extract::rejection::JsonRejection`), `sqlx::SqlitePoolOptions` (it is `sqlx::sqlite::SqlitePoolOptions`) and
`rusqlite::JournalMode` (there is none). rustc says the name is not where the code looks and not where it is, so each
rewrite guessed again; a hand-written known error answered each one after the round it cost. The crate's source is on
disk: the sandbox runs every command with HOME at the workspace's `.agent-home` and leaves CARGO_HOME unset, so cargo
unpacks each crate under `<workspace>/.agent-home/.cargo/registry/src/<index>/<crate>-<version>/`, which outlives the
command and which the worker reads as it reads the workspace.

The crate's public namespace is read statically - nothing of it is compiled or run: `pub mod` from the crate root,
the items each module declares `pub` (`struct`, `enum`, `trait`, `fn`, `type`, `const`, `static`, `union`, also inside a
macro invocation's body, where crates often declare them), `pub use a::b::C` and `pub use a::b as C`, and the globs
and module aliases of `pub use x::*` and `pub use other_crate::{self as name}` followed into the modules and the other
crates they name, a few hops deep. A `#[cfg]` is not read: an item behind a feature counts as declared.
"""
from __future__ import annotations

import difflib
import functools
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

#: How many hops a glob or alias is followed, crates read for one answer, files read of one crate, paths named.
MOST_HOPS = 4
MOST_CRATES = 16
MOST_FILES = 600
MOST_BYTES = 600_000
MOST_ENTRIES = 60_000
MOST_PATHS = 3
MOST_NEAREST = 8

#: Where cargo unpacks a crate's source under a home (`CARGO_HOME` unset), and the home the sandbox gives a command.
_REGISTRY_UNDER_A_HOME = (".cargo", "registry", "src")
_SANDBOX_HOME = ".agent-home"

_NOT_A_CRATE = frozenset({"crate", "self", "super", "std", "core", "alloc", "Self"})


# --- the source, without what does not declare anything ---------------------------------------------------------

_CHAR = re.compile(r"""b?'(?:\\u\{[0-9A-Fa-f]{1,6}\}|\\x[0-9A-Fa-f]{2}|\\.|[^\\'\n])'""")
_RAW_STRING = re.compile(r'b?r(#*)"')


def _strip(text: str) -> str:
    """The text with comments removed and every string and character literal emptied; braces in them are not code."""
    out: list[str] = []
    at, size = 0, len(text)
    while at < size:
        char = text[at]
        if text.startswith("//", at):
            end = text.find("\n", at)
            at = size if end < 0 else end
            continue
        if text.startswith("/*", at):
            depth, at = 1, at + 2
            while at < size and depth:
                if text.startswith("/*", at):
                    depth, at = depth + 1, at + 2
                elif text.startswith("*/", at):
                    depth, at = depth - 1, at + 2
                else:
                    at += 1
            out.append(" ")
            continue
        raw = _RAW_STRING.match(text, at) if char in "rb" and (at == 0 or not (text[at - 1].isalnum() or text[at - 1] == "_")) else None
        if raw:
            closing = '"' + raw.group(1)
            end = text.find(closing, raw.end())
            at = size if end < 0 else end + len(closing)
            out.append('""')
            continue
        if char == '"':
            at += 1
            while at < size and text[at] != '"':
                at += 2 if text[at] == "\\" else 1
            at += 1
            out.append('""')
            continue
        if char in "'b":
            literal = _CHAR.match(text, at)
            if literal and (char == "'" or text[at + 1:at + 2] == "'"):
                out.append("' '")
                at = literal.end()
                continue
        out.append(char)
        at += 1
    return "".join(out)


_ATTRIBUTE = re.compile(r"#!?\[(?:[^\[\]]|\[[^\[\]]*\])*\]")
_ITEM = re.compile(
    r"^(?P<vis>pub(?:\s*\([^)]*\))?\s+)?(?:(?:default|unsafe|async|const|extern(?:\s+\"\")?)\s+)*"
    r"(?P<kind>(?:struct|enum|union|trait|fn|type|const|static|mod|impl)\b|macro_rules\s*!)\s*(?:mut\s+|ref\s+)?"
    r"(?P<name>[A-Za-z_]\w*)?"
)
_USE = re.compile(r"^(?P<vis>pub(?:\s*\([^)]*\))?\s+)?use\s+(?P<tree>[^;]*)$", re.S)


def _head(text: str) -> str:
    return " ".join(_ATTRIBUTE.sub(" ", text).split())


_TOKEN = re.compile(r"::|[{},*]|r#[A-Za-z_]\w*|[A-Za-z_]\w*")


def use_paths(tree: str) -> list[tuple[tuple[str, ...], str | None, bool]]:
    """Each path a `use` tree names, as (segments, alias, is a glob): `a::{b, c::D as E, self as f, g::*}`."""
    tokens = [token.removeprefix("r#") for token in _TOKEN.findall(tree)]
    found: list[tuple[tuple[str, ...], str | None, bool]] = []

    def one(at: int, prefix: tuple[str, ...]) -> int:
        segments = list(prefix)
        while at < len(tokens):
            token = tokens[at]
            if token == "::":
                at += 1
            elif token == "{":
                at += 1
                while at < len(tokens) and tokens[at] != "}":
                    at = one(at, tuple(segments))
                    if at < len(tokens) and tokens[at] == ",":
                        at += 1
                return at + 1
            elif token == "*":
                found.append((tuple(segments), None, True))
                return at + 1
            elif token in ("}", ","):
                return at
            else:
                segments.append(token)
                at += 1
                if at < len(tokens) and tokens[at] == "as" and at + 1 < len(tokens):
                    alias, at = tokens[at + 1], at + 2
                else:
                    alias = None
                if at < len(tokens) and tokens[at] == "::":
                    continue
                if segments[-1] == "self" and len(segments) > 1:
                    segments.pop()
                    alias = alias or segments[-1]
                found.append((tuple(segments), alias, False))
                return at
        return at

    at = 0
    while at < len(tokens):
        moved = one(at, ())
        at = moved if moved > at else at + 1
    return found


# --- one crate's modules ---------------------------------------------------------------------------------------

@dataclass
class Module:
    #: Names declared `pub` here: items, and the names a `pub use` gives.
    names: set[str] = field(default_factory=set)
    #: Each child module, and whether it is `pub`.
    children: dict[str, bool] = field(default_factory=dict)
    #: Each `pub use` path: (segments, alias, is a glob).
    reexports: list[tuple[tuple[str, ...], str | None, bool]] = field(default_factory=list)
    #: The names any `use` brings in, private ones too, by the path they stand for: for a path that starts at one.
    imported: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass
class Crate:
    name: str
    modules: dict[tuple[str, ...], Module]


def _public(visibility: str | None) -> bool:
    return bool(visibility) and visibility.strip() == "pub"


def _declare(crate_modules: dict, module: tuple[str, ...], child: str, visibility: str | None) -> None:
    """`module` has the child module `child`; `pub` when any of its declarations is (`#[cfg]` pairs declare it twice)."""
    children = crate_modules.setdefault(module, Module()).children
    children[child] = children.get(child, False) or _public(visibility)


def _read_file(crate_modules: dict, path: Path, module: tuple[str, ...], directory: Path, budget: list[int]) -> None:
    """Read `path` as `module`, its child modules' files from `directory`, into `crate_modules`."""
    if budget[0] <= 0 or not path.is_file():
        return
    budget[0] -= 1
    try:
        if path.stat().st_size > MOST_BYTES:
            return
        text = _strip(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return
    # Each open brace: ("mod", module, directory) for an inline module, "open" for one whose items count for the
    # module around it (a macro invocation, an `extern` block), "shut" for a body (a function, an impl, a type).
    frames: list[tuple] = []
    current, here = module, directory
    crate_modules.setdefault(module, Module())
    shut = 0
    start = 0
    at = 0
    while at < len(text):
        char = text[at]
        if char not in "{};":
            at += 1
            continue
        if shut:
            if char == "{":
                shut += 1
            elif char == "}":
                shut -= 1
            at += 1
            start = at
            continue
        head = _head(text[start:at])
        used = _USE.match(head) if head else None
        if used and char == "{":
            # A use tree's braces: the statement runs to its `;`.
            end = text.find(";", at)
            end = len(text) if end < 0 else end
            used = _USE.match(_head(text[start:end]))
            at = end
            char = ";"
        if char == ";":
            if used:
                target = crate_modules.setdefault(current, Module())
                for segments, alias, glob in use_paths(used.group("tree")):
                    if not segments:
                        continue
                    if not glob and segments[-1] not in ("self",):
                        target.imported[alias or segments[-1]] = segments
                    if _public(used.group("vis")):
                        target.reexports.append((segments, alias, glob))
                        if not glob:
                            target.names.add(alias or segments[-1])
            else:
                item = _ITEM.match(head) if head else None
                if item and item.group("name"):
                    kind = item.group("kind")
                    if kind == "mod":
                        child = current + (item.group("name"),)
                        read_before = child in crate_modules
                        _declare(crate_modules, current, item.group("name"), item.group("vis"))
                        found = None if read_before else next((candidate for candidate in (here / f"{item.group('name')}.rs",
                                                                  here / item.group("name") / "mod.rs")
                                      if candidate.is_file()), None)
                        if found is not None:
                            _read_file(crate_modules, found, child, here / item.group("name"), budget)
                    elif kind not in ("impl",) and not kind.startswith("macro_rules") and _public(item.group("vis")):
                        crate_modules.setdefault(current, Module()).names.add(item.group("name"))
        elif char == "{":
            item = _ITEM.match(head) if head else None
            if item and item.group("kind") == "mod" and item.group("name"):
                name = item.group("name")
                _declare(crate_modules, current, name, item.group("vis"))
                frames.append(("mod", current, here))
                current, here = current + (name,), here / name
                crate_modules.setdefault(current, Module())
            elif item and (item.group("kind") in ("impl", "fn", "trait", "struct", "enum", "union", "type", "const",
                                                   "static") or item.group("kind").startswith("macro_rules")):
                if item.group("name") and item.group("kind") not in ("impl",) and _public(item.group("vis")) \
                        and not item.group("kind").startswith("macro_rules"):
                    crate_modules.setdefault(current, Module()).names.add(item.group("name"))
                shut = 1
            else:
                frames.append(("open",))
        elif char == "}":
            if frames:
                frame = frames.pop()
                if frame[0] == "mod":
                    current, here = frame[1], frame[2]
        at += 1
        start = at


def _crate_root(directory: Path) -> Path | None:
    """The crate's library root: `[lib] path` in its manifest, else `src/lib.rs`."""
    try:
        manifest = (directory / "Cargo.toml").read_text(encoding="utf-8", errors="replace")
        library = re.search(r"^\[lib\][^\[]*?^path\s*=\s*\"([^\"]+)\"", manifest, re.M | re.S)
    except OSError:
        library = None
    for candidate in ([directory / library.group(1)] if library else []) + [directory / "src" / "lib.rs"]:
        if candidate.is_file():
            return candidate
    return None


@functools.lru_cache(maxsize=64)
def _crate(directory: str, name: str) -> Crate | None:
    """One unpacked crate's modules, or None when it has no library root here. A registry's crate never changes."""
    root = _crate_root(Path(directory))
    if root is None:
        return None
    modules: dict[tuple[str, ...], Module] = {}
    _read_file(modules, root, (), root.parent, [MOST_FILES])
    return Crate(name=name, modules=modules)


# --- the registry ---------------------------------------------------------------------------------------------

_UNPACKED = re.compile(r"^(?P<name>.+?)-(?P<version>\d+\.\d+\.\d+\S*)$")


def _version_key(version: str) -> tuple:
    return tuple(int(part) if part.isdigit() else -1 for part in re.split(r"[.+-]", version))


def _normal(name: str) -> str:
    return name.replace("-", "_")


def _locked(project: Path) -> dict[str, set[str]]:
    """The versions the project's `Cargo.lock` pins, by crate name as code writes it."""
    for base in (project, project.parent):
        try:
            text = (base / "Cargo.lock").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found: dict[str, set[str]] = {}
        for name, version in re.findall(r'^name\s*=\s*"([^"]+)"\s*\nversion\s*=\s*"([^"]+)"', text, re.M):
            found.setdefault(_normal(name), set()).add(version)
        return found
    return {}


class Registry:
    """The crates cargo unpacked for this project, by name as code writes it (`axum_core` for `axum-core`)."""

    def __init__(self, project: Path) -> None:
        unpacked: dict[str, list[tuple[tuple, Path, str]]] = {}
        for base in (project, project.parent):
            source = base / _SANDBOX_HOME
            source = source.joinpath(*_REGISTRY_UNDER_A_HOME)
            if not source.is_dir():
                continue
            for index in sorted(source.iterdir()):
                try:
                    entries = list(os.scandir(index))
                except OSError:
                    continue
                for entry in entries:
                    found = _UNPACKED.match(entry.name)
                    if found and entry.is_dir():
                        unpacked.setdefault(_normal(found.group("name")), []).append(
                            (_version_key(found.group("version")), Path(entry.path), found.group("version")))
            break
        locked = _locked(project)
        self._chosen: dict[str, tuple[Path, str]] = {}
        for name, versions in unpacked.items():
            pinned = [v for v in versions if v[2] in locked.get(name, set())] or versions
            best = max(pinned, key=lambda v: v[0])
            self._chosen[name] = (best[1], best[2])
        self._read: dict[str, Crate | None] = {}

    def __contains__(self, name: str) -> bool:
        return _normal(name) in self._chosen

    def version(self, name: str) -> str:
        return self._chosen.get(_normal(name), (None, ""))[1]

    def crate(self, name: str) -> Crate | None:
        name = _normal(name)
        if name not in self._read:
            if name not in self._chosen or len(self._read) >= MOST_CRATES:
                return None
            self._read[name] = _crate(str(self._chosen[name][0]), name)
        return self._read[name]


def _resolve(registry: Registry, crate: Crate, module: tuple[str, ...], segments: tuple[str, ...],
             depth: int = 0) -> tuple[Crate, tuple[str, ...]] | None:
    """The crate and module path a `use` path written in `module` of `crate` stands for; None when not read here."""
    if not segments or depth > MOST_HOPS:
        return None
    first, rest = segments[0], segments[1:]
    if first == "crate":
        return crate, rest
    if first == "self":
        return crate, module + rest
    if first == "super":
        base = list(module)
        while segments and segments[0] == "super":
            if base:
                base.pop()
            segments = segments[1:]
        return crate, tuple(base) + segments
    if module + (first,) in crate.modules:
        return crate, module + segments
    imported = crate.modules.get(module, Module()).imported.get(first)
    if imported and imported != segments[:len(imported)]:
        return _resolve(registry, crate, module, imported + rest, depth + 1)
    if first not in _NOT_A_CRATE and first in registry:
        other = registry.crate(first)
        return (other, rest) if other is not None else None
    return None


def namespace(registry: Registry, crate: Crate) -> list[tuple[str, ...]]:
    """Every public path of the crate, from its root (`("extract", "rejection", "JsonRejection")`), bounded."""
    found: list[tuple[str, ...]] = []
    seen: set[tuple] = set()

    def walk(owner: Crate, module: tuple[str, ...], shown: tuple[str, ...], hops: int) -> None:
        key = (owner.name, module, shown)
        if key in seen or len(found) >= MOST_ENTRIES or len(shown) > 12:
            return
        seen.add(key)
        here = owner.modules.get(module)
        if here is None:
            return
        found.extend(shown + (name,) for name in sorted(here.names))
        for child, public in sorted(here.children.items()):
            if public:
                found.append(shown + (child,))
                walk(owner, module + (child,), shown + (child,), hops)
        if hops >= MOST_HOPS:
            return
        for segments, alias, glob in here.reexports:
            target = _resolve(registry, owner, module, segments)
            if target is None:
                continue
            walk(target[0], target[1], shown if glob else shown + (alias or segments[-1],), hops + 1)

    walk(crate, (), (), 0)
    return list(dict.fromkeys(found))


# --- the answer to a compiler's error ------------------------------------------------------------------------

#: rustc's words for a name a path does not have: the import it could not resolve, and the name and where it looked.
_UNRESOLVED_IMPORT = re.compile(r"unresolved import `([^`]+)`")
_NOT_IN = re.compile(
    r"(?:\bno|could not find|cannot find(?: [a-z]+(?:, [a-z]+)*(?: or [a-z]+)?(?: type)?)?) `([A-Za-z_]\w*)` in "
    r"(?:(?:module|crate|enum) )?`([^`]+)`"
)
_A_PATH = r"[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*"


@dataclass(frozen=True)
class Asked:
    crate: str
    module: tuple[str, ...]
    name: str


def _what_was_asked(message: str, importer: Path, line_number: int) -> Asked | None:
    """The crate, module and name a rustc error says an import or path asked for, or None when it names none."""
    found = _UNRESOLVED_IMPORT.search(message)
    if found:
        segments = tuple(part for part in found.group(1).split("::") if part)
        if len(segments) >= 2:
            return Asked(segments[0], segments[1:-1], segments[-1])
    found = _NOT_IN.search(message)
    if found is None:
        return None
    name, where = found.group(1), tuple(part for part in found.group(2).split("::") if part)
    if len(where) > 1:
        return Asked(where[0], where[1:], name)
    container = where[0]
    try:
        source = _strip(importer.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        source = ""
    lines = source.splitlines()
    line = lines[line_number - 1] if 0 < line_number <= len(lines) else ""
    # On the line: `a::b::container::name` names the crate the container is in.
    written = re.search(rf"\b({_A_PATH})::{re.escape(container)}::{re.escape(name)}\b", line)
    if written:
        segments = tuple(written.group(1).split("::")) + (container,)
        return Asked(segments[0], segments[1:], name)
    # A `use` of the file that brings the container in: `use sqlx::sqlite;`, `use sqlx::{sqlite::{self, X}}`.
    for statement in re.findall(r"\buse\s+([^;]*);", source):
        for segments, alias, glob in use_paths(statement):
            if glob or not segments:
                continue
            if (alias or segments[-1]) == container and len(segments) > 1:
                return Asked(segments[0], segments[1:], name)
            if container in segments[:-1] and segments[-1] == name:
                cut = segments.index(container) + 1
                return Asked(segments[0], segments[1:cut], name)
    return Asked(container, (), name)


def where_it_is(project: Path, importer: Path, finding: dict) -> str:
    """A sentence naming where the crate a rustc error is about really declares the name, or which names it has; "".

    "" when the error names no path into a crate, or the crate's source is not unpacked here.
    """
    message = str(finding.get("message") or "")
    try:
        line_number = int(finding.get("line") or 0)
    except (TypeError, ValueError):
        line_number = 0
    asked = _what_was_asked(message, importer, line_number)
    if asked is None or asked.crate in _NOT_A_CRATE:
        return ""
    registry = Registry(project)
    crate = registry.crate(asked.crate)
    if crate is None:
        return ""
    paths = namespace(registry, crate)
    label = f"`{asked.crate}` {registry.version(asked.crate)}".rstrip()
    wanted = asked.module + (asked.name,)
    where = sorted({path for path in paths if path[-1] == asked.name}, key=lambda path: (len(path), path))
    if where:
        shown = ", ".join(f"`{'::'.join((asked.crate,) + path)}`" for path in where[:MOST_PATHS])
        if wanted in where:
            return (f" {label}'s source declares `{'::'.join((asked.crate,) + wanted)}`, so it is most likely behind a "
                    "cargo feature this project does not turn on: add that feature to the crate in `Cargo.toml`")
        return (f" {label}'s source declares `{asked.name}` publicly at: {shown} - import it from there"
                f" (not `{'::'.join((asked.crate,) + wanted)}`)")
    names = sorted({path[-1] for path in paths})
    in_module = [path[-1] for path in paths if path[:-1] == asked.module]
    lowered = asked.name.lower()
    nearest = [name for name in names if lowered in name.lower() or name.lower() in lowered and len(name) > 3]
    nearest += difflib.get_close_matches(asked.name, names, n=MOST_NEAREST, cutoff=0.75)
    nearest = list(dict.fromkeys(nearest))[:MOST_NEAREST]
    sentence = f" {label}'s source has no public `{asked.name}` anywhere"
    if nearest:
        sentence += f"; the nearest names it has: {', '.join(f'`{n}`' for n in nearest)}"
    if in_module and asked.module:
        sentence += (f"; `{'::'.join((asked.crate,) + asked.module)}` has: "
                     f"{', '.join(f'`{n}`' for n in list(dict.fromkeys(in_module))[:20])}")
    if nearest or (in_module and asked.module):
        return sentence + " - use one of those, or write it yourself"
    return sentence + " - write it yourself, or take it from another crate"


__all__ = ["Registry", "namespace", "use_paths", "where_it_is"]
