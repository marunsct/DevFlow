"""How an installed library defines a function the product calls: its signature and docstring from the installed
files, for a fixer (plan FX.10, behind `USAGE_NOTES_FROM_THE_INSTALLED_PACKAGE`).

Measured on a medium run: two fixers in a row wrote a migration library's `upgrade` call with an argument list that
function does not have, and neither asked any of the lookup tools offered to them (0 calls in 571 requests); what
they needed was how the installed release defines the function, not a search for an error. Published work agrees:
code written for an API with no documentation in the prompt ran in its environment 42.6% of the time, and short,
exact documentation of the version in use helps most.

So the harness reads it, statically - nothing of the package is run - where `module_exports` reads only names:

- **an edit refused** by the language service for a name or attribute of an installed library (`for_a_refusal`): the
  refusal carries how the installed release defines the names that line calls, or, for a name it does not have, the
  nearest names it does;
- **the lines a defect locates** - a trace's frames in the product, `file:line` places - and, in the defect's files,
  the calls of a name its error writes (`for_a_fixer`): the fixer's brief carries the same note, and one example from
  the library's documentation where the lookup sources find it (through the one outbound gate, once per name a run,
  and only where the run's stuck lookups are on).

Python (`.venv` site-packages: `.py`, else `.pyi`) and JavaScript/TypeScript (`node_modules` type files) are read;
anything else gives nothing. Off, every request and refusal is as before.
"""
from __future__ import annotations

import ast
import difflib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from app.switches import is_on

logger = logging.getLogger(__name__)

SWITCH = "USAGE_NOTES_FROM_THE_INSTALLED_PACKAGE"
#: What opens the notes in a request or a refusal; the audit's switch-firing check reads it (`switch_firing.SIGNALS`).
HEADING = "How the installed libraries define the names this code calls"
#: Notes in one request or refusal, characters of each part, and of all of them.
MOST_NOTES = 3
MOST_SIGNATURE = 400
MOST_DOC = 700
MOST_CHARACTERS = 2_400
#: Characters of the one documentation example.
MOST_EXAMPLE = 600
#: Places a defect locates that are read, and files whose calls are matched to the error's names.
MOST_PLACES = 4
MOST_FILES = 4
#: Files deeper than this are not followed through a package's re-exports.
MOST_DEPTH = 4
#: Characters of a product file read.
MOST_FILE = 400_000


class _UsageNotes:
    """`USAGE_NOTES_FROM_THE_INSTALLED_PACKAGE` as the switch registry reads one: off in code until measured."""

    ON_BY_DEFAULT = False
    #: What the admin page says this switch does.
    explanation = ("A fixer, and an edit refused for a library's name, are shown how the installed release defines "
                   "the functions the code calls: the signature and docstring read from the installed files, and one "
                   "example from the library's documentation where the lookup sources find it.")

    @staticmethod
    def enabled() -> bool:
        return is_on(SWITCH, _UsageNotes.ON_BY_DEFAULT)


usage_notes_switch = _UsageNotes()


def enabled() -> bool:
    return usage_notes_switch.enabled()


@dataclass
class Usage:
    """How an installed package defines one name: as the code writes it, the package and its version, the signature
    and docstring - or, when it has no such name, the nearest names it has."""

    written: str
    package: str
    version: str = ""
    signature: str = ""
    doc: str = ""
    near: list[str] = field(default_factory=list)
    example: str = ""

    @property
    def found(self) -> bool:
        return bool(self.signature)

    def as_text(self) -> str:
        release = f"{self.package} {self.version}".strip()
        if not self.found:
            nearest = ", ".join(f"`{n}`" for n in self.near) or "none close"
            return (f"- `{self.written}`: the installed {release} has no such name; the nearest names it has: "
                    f"{nearest}.")
        lines = [f"- `{self.written}`, as the installed {release} defines it:", "  " + self.signature]
        lines += ["  " + line for line in self.doc.splitlines() if line.strip()]
        if self.example:
            lines.append("  " + self.example)
        return "\n".join(lines)


def _cut(text: str, most: int) -> str:
    text = str(text or "").strip()
    if len(text) <= most:
        return text
    cut = text[:most]
    return cut[: cut.rfind("\n")] if "\n" in cut[most // 2:] else cut.rstrip() + " ..."


# --- Python: the installed files, read without running them ---------------------------------------------------------

def _site_packages(project: Path) -> list[Path]:
    found: list[Path] = []
    for base in (project, project.parent):
        found += sorted((base / ".venv" / "lib").glob("python*/site-packages"))
    return found


def _python_file(sites: list[Path], dotted: str) -> Path | None:
    parts = [p for p in dotted.split(".") if p]
    for site in sites:
        stem = site.joinpath(*parts)
        for candidate in (stem / "__init__.py", stem.with_suffix(".py"), stem / "__init__.pyi", stem.with_suffix(".pyi")):
            if candidate.is_file():
                return candidate
    return None


def _parsed(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError, ValueError):
        return None


def _is_an_overload(node: ast.AST) -> bool:
    return any((isinstance(d, ast.Name) and d.id == "overload") or (isinstance(d, ast.Attribute) and d.attr == "overload")
               for d in getattr(node, "decorator_list", []))


def _the_definition(body: list[ast.stmt], name: str) -> ast.AST | None:
    """The definition of `name` among `body`'s statements: a function (the one that is not an overload where there
    are several), a class, or an assignment."""
    found = [node for node in body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
             and node.name == name]
    if found:
        return next((node for node in found if not _is_an_overload(node)), found[0])
    for node in body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return node
    return None


def _the_module_of(dotted: str, path: Path, node: ast.ImportFrom) -> str:
    """The absolute module an `from ... import` in the module `dotted` (at `path`) names."""
    if not node.level:
        return str(node.module or "")
    package = dotted.split(".") if path.stem == "__init__" else dotted.split(".")[:-1]
    base = package[: len(package) - (node.level - 1)] if node.level > 1 else package
    return ".".join([*base, *([node.module] if node.module else [])])


def _python_defined(sites: list[Path], dotted: str, names: list[str], depth: int = 0) -> ast.AST | None:
    """The definition of `names` (a top-level name, then a member of it) in the installed module `dotted`, followed
    through the module's own imports of it."""
    path = _python_file(sites, dotted)
    tree = _parsed(path) if path is not None and depth <= MOST_DEPTH else None
    if tree is None or path is None:
        return None
    node = _the_definition(tree.body, names[0])
    if node is not None:
        if len(names) == 1:
            return node
        return _the_definition(node.body, names[1]) if isinstance(node, ast.ClassDef) and len(names) == 2 else None
    for statement in tree.body:
        if isinstance(statement, ast.ImportFrom):
            for alias in statement.names:
                if (alias.asname or alias.name) != names[0]:
                    continue
                module = _the_module_of(dotted, path, statement)
                if _python_file(sites, f"{module}.{alias.name}") is not None and len(names) > 1:
                    return _python_defined(sites, f"{module}.{alias.name}", names[1:], depth + 1)
                return _python_defined(sites, module, [alias.name, *names[1:]], depth + 1)
    return None


def _python_names(sites: list[Path], dotted: str) -> list[str]:
    """The public names the installed module `dotted` defines or imports at its top level."""
    path = _python_file(sites, dotted)
    tree = _parsed(path) if path is not None else None
    if tree is None:
        return []
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.Assign):
            names += [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names += [(a.asname or a.name).split(".")[0] for a in node.names if a.name != "*"]
    return sorted({n for n in names if not n.startswith("_")})


def _python_signature(node: ast.AST, name: str) -> tuple[str, str]:
    """(the signature, the docstring) of a definition, as its source writes them."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        returns = f" -> {ast.unparse(node.returns)}" if node.returns is not None else ""
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        return f"{prefix} {node.name}({ast.unparse(node.args)}){returns}", ast.get_docstring(node) or ""
    if isinstance(node, ast.ClassDef):
        bases = ", ".join(ast.unparse(b) for b in node.bases)
        init = _the_definition(node.body, "__init__")
        said = f"class {node.name}" + (f"({bases})" if bases else "")
        if isinstance(init, (ast.FunctionDef, ast.AsyncFunctionDef)):
            said += f"; {node.name}({ast.unparse(init.args)})"
        doc = ast.get_docstring(node) or (ast.get_docstring(init) if isinstance(init, ast.FunctionDef) else "") or ""
        return said, doc
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        return ast.unparse(node), ""
    return "", ""


def python_usage(project: Path, written: str) -> Usage | None:
    """How the installed package defines the dotted name `written` (`alembic.command.upgrade`), or None when no
    installed module holds it. Never raises."""
    try:
        sites = _site_packages(project)
        parts = [p for p in str(written or "").split(".") if p]
        if not sites or len(parts) < 2:
            return None
        for cut in range(len(parts) - 1, 0, -1):
            module = ".".join(parts[:cut])
            if _python_file(sites, module) is None:
                continue
            from app.analysis import installed_packages

            usage = Usage(written=written, package=parts[0],
                          version=installed_packages.installed_version(project, parts[0], "python"))
            node = _python_defined(sites, module, parts[cut:])
            if node is None:
                wanted = parts[cut]
                names = _python_names(sites, module)
                near = [n for n in names if wanted.lower() in n.lower() or n.lower() in wanted.lower()]
                usage.near = list(dict.fromkeys([*near, *difflib.get_close_matches(wanted, names, n=5, cutoff=0.6)]))[:6]
                return usage
            signature, doc = _python_signature(node, parts[-1])
            usage.signature, usage.doc = _cut(signature, MOST_SIGNATURE), _cut(doc, MOST_DOC)
            return usage
    except Exception:  # noqa: BLE001 - nothing is said
        logger.debug("Could not read %s from its installed files", written, exc_info=True)
    return None


def python_calls(content: str, lines: Iterable[int] | None = None) -> list[str]:
    """The dotted names of what `content` calls on `lines` (every line when None), as its imports name them:
    `command.upgrade(...)` after `from alembic import command` is `alembic.command.upgrade`."""
    try:
        tree = ast.parse(str(content or ""))
    except (SyntaxError, ValueError):
        return []
    imported: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported[alias.asname or alias.name.split(".")[0]] = alias.name if alias.asname else alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                if alias.name != "*":
                    imported[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    wanted = set(lines) if lines is not None else None
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or (wanted is not None and node.lineno not in wanted):
            continue
        chain: list[str] = []
        at: ast.AST = node.func
        while isinstance(at, ast.Attribute):
            chain.insert(0, at.attr)
            at = at.value
        if isinstance(at, ast.Name) and at.id in imported:
            found.append(".".join([imported[at.id], *chain]))
    return list(dict.fromkeys(found))


# --- JavaScript and TypeScript: the installed type files -------------------------------------------------------------

_SCRIPT_IMPORT = re.compile(
    r"""^\s*import\s+(?:type\s+)?(?:([A-Za-z_$][\w$]*)\s*,?\s*)?(?:\{([^}]*)\}|\*\s*as\s+([A-Za-z_$][\w$]*))?\s*"""
    r"""from\s*['"]([^'"]+)['"]""", re.M)
_SCRIPT_REQUIRE = re.compile(
    r"""(?:const|let|var)\s+(?:([A-Za-z_$][\w$]*)|\{([^}]*)\})\s*=\s*require\(\s*['"]([^'"]+)['"]\s*\)""")
_A_DOC_COMMENT = r"(?:/\*\*((?:[^*]|\*(?!/))*)\*/\s*)?"


def _script_names(listed: str) -> list[tuple[str, str]]:
    """(the name the code uses, the name the package exports) for each of an import's `{ a, b as c }`."""
    pairs = []
    for part in str(listed or "").split(","):
        part = re.sub(r"^\s*type\s+", "", part.strip())
        if not part:
            continue
        exported, _, used = part.partition(" as ") if " as " in part else part.partition(":")
        pairs.append(((used or exported).strip(), exported.strip()))
    return pairs


def script_calls(content: str, lines: Iterable[int] | None = None) -> list[tuple[str, str]]:
    """(the package specifier, the name it exports) for each package name `content` calls on `lines` (every line when
    None): a named import called, or a member of a namespace or default import (`z.object(...)`)."""
    text = str(content or "")
    named: dict[str, tuple[str, str]] = {}
    whole: dict[str, str] = {}
    for found in _SCRIPT_IMPORT.finditer(text):
        default, listed, namespace, specifier = found.groups()
        if specifier.startswith((".", "/")):
            continue
        for used, exported in _script_names(listed or ""):
            named[used] = (specifier, exported)
        for alias in (default, namespace):
            if alias:
                whole[alias] = specifier
    for found in _SCRIPT_REQUIRE.finditer(text):
        alias, listed, specifier = found.groups()
        if specifier.startswith((".", "/")):
            continue
        if alias:
            whole[alias] = specifier
        for used, exported in _script_names(listed or ""):
            named[used] = (specifier, exported)
    all_lines = text.splitlines()
    chosen = [all_lines[n - 1] for n in (lines if lines is not None else range(1, len(all_lines) + 1))
              if 0 < n <= len(all_lines)]
    calls: list[tuple[str, str]] = []
    for line in chosen:
        if re.match(r"\s*(?:import\b|export\s+\*)", line):
            continue
        for alias, specifier in whole.items():
            for member in re.findall(rf"(?<![\w$.]){re.escape(alias)}\s*\.\s*([A-Za-z_$][\w$]*)\s*[(<]", line):
                calls.append((specifier, member))
        for used, pair in named.items():
            if re.search(rf"(?<![\w$.]){re.escape(used)}\s*[(<]", line):
                calls.append(pair)
    return list(dict.fromkeys(calls))


def _script_declaration(path: Path, name: str, depth: int, seen: set[Path]) -> tuple[str, str] | None:
    """(the declaration, its doc comment) of `name` in a type file, followed through `export * from` and
    `export { name } from` to `MOST_DEPTH` files deep."""
    from app.analysis import package_exports

    if path in seen or depth > MOST_DEPTH:
        return None
    seen.add(path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    declared = re.compile(
        _A_DOC_COMMENT + r"(?P<declaration>^[ \t]*(?:export\s+)?(?:declare\s+)?(?:default\s+)?(?:abstract\s+)?"
        rf"(?:async\s+)?(?:function\*?\s+{re.escape(name)}\b|(?:const|let|var)\s+{re.escape(name)}\s*:"
        rf"|class\s+{re.escape(name)}\b|interface\s+{re.escape(name)}\b|{re.escape(name)}\??\s*[<(]))", re.M)
    found = declared.search(text)
    if found:
        body = text[found.start("declaration"):][:MOST_SIGNATURE * 2]
        statement = re.split(r";\s*$|\{\s*$", body, maxsplit=1, flags=re.M)[0]
        doc = "\n".join(re.sub(r"^\s*\*\s?", "", line) for line in (found.group(1) or "").splitlines()).strip()
        return " ".join(statement.split()), doc
    for listed, source in package_exports._LISTED.findall(text):  # noqa: SLF001 - the exports reader's own patterns
        if source.startswith(".") and any(exported == name or used == name for used, exported in _script_names(listed)):
            target = package_exports._resolve(path, source)  # noqa: SLF001
            if target is not None:
                return _script_declaration(target, name, depth + 1, seen)
    for alias, source in package_exports._STAR.findall(text):  # noqa: SLF001
        if not alias and source.startswith("."):
            target = package_exports._resolve(path, source)  # noqa: SLF001
            got = _script_declaration(target, name, depth + 1, seen) if target is not None else None
            if got is not None:
                return got
    return None


def script_usage(project: Path, specifier: str, name: str) -> Usage | None:
    """How the installed JavaScript or TypeScript package `specifier` declares `name`, from its type files; None when
    it is not installed here or has no type file. Never raises."""
    try:
        from app.analysis import installed_packages, package_exports

        package, subpath = package_exports._split(specifier)  # noqa: SLF001
        for base in (project, project.parent):
            directory = base / "node_modules" / package
            if not directory.is_dir():
                continue
            entry = package_exports._type_file(directory, subpath)  # noqa: SLF001
            if entry is None:
                return None
            usage = Usage(written=f"{specifier}: {name}", package=package,
                          version=installed_packages.installed_version(project, package, "script"))
            got = _script_declaration(entry, name, 0, set())
            if got is None:
                names = package_exports._names_of_type_file(entry, 0, set())  # noqa: SLF001
                usage.near = difflib.get_close_matches(name, sorted(set(names)), n=5, cutoff=0.6)
                return usage
            usage.signature, usage.doc = _cut(got[0], MOST_SIGNATURE), _cut(got[1], MOST_DOC)
            return usage
    except Exception:  # noqa: BLE001 - nothing is said
        logger.debug("Could not read %s from %s's installed files", name, specifier, exc_info=True)
    return None


# --- what a file calls, read against what is installed ---------------------------------------------------------------

_PYTHON_SUFFIXES = (".py", ".pyi")
_SCRIPT_SUFFIXES = (".js", ".mjs", ".cjs", ".jsx", ".ts", ".mts", ".cts", ".tsx")


def usages_on(project: Path, path: str, content: str, lines: Iterable[int] | None = None) -> list[Usage]:
    """How the installed libraries define what the file at `path` (its `content`) calls on `lines`."""
    lower = str(path).lower()
    if lower.endswith(_PYTHON_SUFFIXES):
        found = [python_usage(project, written) for written in python_calls(content, lines)]
    elif lower.endswith(_SCRIPT_SUFFIXES):
        found = [script_usage(project, specifier, name) for specifier, name in script_calls(content, lines)]
    else:
        return []
    return [usage for usage in found if usage is not None]


def _section(usages: list[Usage], intro: str) -> str:
    kept: list[str] = []
    size = 0
    for usage in usages[:MOST_NOTES]:
        text = usage.as_text()
        if kept and size + len(text) > MOST_CHARACTERS:
            break
        kept.append(text)
        size += len(text)
    if not kept:
        return ""
    return f"--- {HEADING} ---\n{intro}\n" + "\n".join(kept) + "\n"


def _unique(usages: Iterable[Usage]) -> list[Usage]:
    seen: set[str] = set()
    kept = []
    for usage in usages:
        if usage.written not in seen:
            seen.add(usage.written)
            kept.append(usage)
    return kept


# --- an edit refused ---------------------------------------------------------------------------------------------------

#: A finding that names an installed module's missing attribute: Pyright's `"x" is not a known attribute of module "m"`.
_NOT_AN_ATTRIBUTE_OF = re.compile(r"\"(\w+)\" is not a known attribute of module \"([\w.]+)\"")


def for_a_refusal(project: Path, path: str, content: str, findings: list[dict[str, Any]]) -> str:
    """For an edit the language service refused: how the installed libraries define the names its refused lines
    call, and for a name a library does not have, the nearest names it has; "" when off or none is a library's.
    Never raises."""
    if not enabled():
        return ""
    try:
        usages: list[Usage] = []
        for finding in findings:
            said = _NOT_AN_ATTRIBUTE_OF.search(str(finding.get("message") or ""))
            if said and str(path).lower().endswith(_PYTHON_SUFFIXES):
                usage = python_usage(project, f"{said.group(2)}.{said.group(1)}")
                if usage is not None:
                    usages.append(usage)
        lines = [int(f["line"]) for f in findings if str(f.get("line") or "").isdigit()]
        if lines:
            usages += usages_on(project, path, content, lines)
        return _section(_unique(usages), "Read from the installed files, for the lines refused:")
    except Exception:  # noqa: BLE001 - the refusal as it was
        logger.debug("Could not read the refused names' usage", exc_info=True)
        return ""


# --- a fixer's brief ---------------------------------------------------------------------------------------------------

#: A place a trace or a defect names: `File "app/db.py", line 12` or `app/db.py:12` (`:12:5`, `(12,5)`).
_A_PLACE = re.compile(r"File \"([^\"]+)\", line (\d+)|((?:[\w.@~+-]+/)*[\w.@~+-]+\.[A-Za-z]{1,4})[:(](\d+)")
#: Words an error writes a function or an attribute by: `upgrade()`, `'visit_ARRAY'`, `` `sessionmaker` ``.
_A_NAME_WRITTEN = re.compile(r"\b([A-Za-z_]\w{2,})\(\)|['\"`]([A-Za-z_]\w{2,})['\"`]")
#: Where installed packages' own files live: a frame there is not the product's.
_INSTALLED = re.compile(r"site-packages/|node_modules/|/\.venv/|/vendor/|/\.cargo/|/gems/|/pkg/mod/")


def _the_product_file(project: Path, root: Path, written: str) -> Path | None:
    """The product file a place writes: as it is, or the shortest tail of it found under the project."""
    if _INSTALLED.search(written):
        return None
    parts = [p for p in Path(written).parts if p not in {"/", ".", ".."}]
    for start in range(len(parts)):
        tail = Path(*parts[start:])
        for base in (project, root):
            candidate = base / tail
            if candidate.is_file():
                return candidate
    return None


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:MOST_FILE]
    except OSError:
        return ""


def located_usages(repo_root: str | Path, defect: Any) -> list[Usage]:
    """How the installed libraries define what the lines a defect locates call, then the calls in its files of a name
    its error writes."""
    from app.analysis import installed_packages

    root = Path(repo_root)
    project = installed_packages.project_of(root)
    text = f"{getattr(defect, 'description', '') or ''}\n{getattr(defect, 'actual_behavior', '') or ''}"
    usages: list[Usage] = []
    places: dict[Path, set[int]] = {}
    for found in _A_PLACE.finditer(text):
        written, line = (found.group(1), found.group(2)) if found.group(1) else (found.group(3), found.group(4))
        file = _the_product_file(project, root, written)
        if file is not None and (file in places or len(places) < MOST_PLACES):
            places.setdefault(file, set()).add(int(line))
    for file, lines in places.items():
        usages += usages_on(project, file.name, _read(file), sorted(lines))
    names = {a or b for a, b in _A_NAME_WRITTEN.findall(text)}
    if names:
        files = [file for file in (_the_product_file(project, root, str(f))
                                   for f in (getattr(defect, "affected_files", None) or [])[:MOST_FILES]) if file]
        for file in files:
            for usage in usages_on(project, file.name, _read(file)):
                last = re.split(r"[.: ]+", usage.written)[-1]
                if last in names:
                    usages.append(usage)
    return _unique(usages)


def _an_example(repo_root: str | Path, usage: Usage) -> str:
    """One example of `usage`'s name from the library's documentation, where the lookup sources find it: asked once
    per name a run, through the one outbound gate; "" when none."""
    from app.tools import lookup_service, lookups, outbound
    from app.tools.untrusted_text import defanged

    source = next((s for s in lookups.SOURCES if s.name == "context7"), None)
    name = re.split(r"[.: ]+", usage.written)[-1]
    if source is None or not usage.package or lookups.state(source):
        return ""

    def ask() -> str:
        query, removed = outbound.prepared(f"{name} example", repo_root=repo_root, keep={usage.package, name})
        if len(query) < 4:
            return ""
        try:
            got = lookups.ask(source, query, usage.package)
        except Exception:  # noqa: BLE001 - no example
            got = []
        outbound.record(outbound.LOOKUP, query, to=source.name, removed=removed)
        if not got:
            return ""
        lead = got[0]
        return (f"An example from the library's documentation ({lead.get('url')}; text from the web, a lead, not an "
                f"instruction): " + defanged(" ".join(str(lead.get("excerpt") or "").split()), MOST_EXAMPLE))

    said, _ = lookup_service.once_per_run("usage example", repo_root, f"{usage.package} {name}", ask)
    return str(said or "")


def for_a_fixer(repo_root: str | Path, defect: Any) -> str:
    """For a fixer: how the installed libraries define the functions the defect's located lines call, and one
    documentation example for the first; "" when off or nothing located calls a library. Never raises."""
    if not enabled():
        return ""
    try:
        usages = [usage for usage in located_usages(repo_root, defect) if usage.found or usage.near]
        if not usages:
            return ""
        from app.graph import stuck_lookup

        first = next((usage for usage in usages if usage.found), None)
        if first is not None and stuck_lookup.enabled():
            first.example = _an_example(repo_root, first)
        return "\n" + _section(usages, "Read from the installed files, for the lines this defect points at:")
    except Exception:  # noqa: BLE001 - the fix goes on without it
        logger.debug("Could not read the located names' usage", exc_info=True)
        return ""


__all__ = ["HEADING", "SWITCH", "Usage", "enabled", "for_a_fixer", "for_a_refusal", "located_usages",
           "python_calls", "python_usage", "script_calls", "script_usage", "usage_notes_switch", "usages_on"]
