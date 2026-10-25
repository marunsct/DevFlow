"""What an installed package really exports, read from its files, for a name an import asks for that it does not have (behind `PACKAGE_EXPORTS_NAMED`).

Measured over one night with a small model: it imported `createClient` and `createTestClient` from `hono/testing`,
which exports one name, `testClient`; the compiler said the name was missing and not which exist, so each rewrite guessed
again and four runs ended with a product that did not build. The harness can read the package: this reads the type
file the package's manifest points at (TypeScript and JavaScript) or the package's `__init__.py` (Python), statically -
nothing of the package is run.

The answer is the names a statement of the form `export ...` or a top-level definition gives, followed through
`export * from './x'` to a few files deep; a package it cannot read gives None and the finding goes out as it was.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from app.switches import is_on

#: Off in code like every switch; the compose file turns it on.
ON_BY_DEFAULT = False

#: How many files `export * from` is followed through, and how many names are listed.
MOST_DEPTH = 3
MOST_NAMES = 60


def enabled() -> bool:
    return is_on("PACKAGE_EXPORTS_NAMED", ON_BY_DEFAULT)


# --- JavaScript and TypeScript ---------------------------------------------------

_DECLARED = re.compile(
    r"^\s*export\s+(?:declare\s+)?(?:default\s+)?(?:abstract\s+)?"
    r"(?:async\s+)?(?:function\*?|class|const|let|var|interface|type|enum|namespace)\s+([A-Za-z_$][\w$]*)",
    re.M,
)
_LISTED = re.compile(r"^\s*export\s*(?:type\s*)?\{([^}]*)\}(?:\s*from\s*['\"]([^'\"]+)['\"])?", re.M)
_STAR = re.compile(r"^\s*export\s*\*\s*(?:as\s+([A-Za-z_$][\w$]*)\s*)?from\s*['\"]([^'\"]+)['\"]", re.M)
_DEFAULT = re.compile(r"^\s*export\s+default\b", re.M)
_TYPE_FILES = (".d.ts", ".d.mts", ".d.cts", ".ts", ".mts", ".cts")


def _split(specifier: str) -> tuple[str, str]:
    """`hono/testing` -> ("hono", "./testing"); `@hono/node-server` -> ("@hono/node-server", ".")."""
    parts = specifier.split("/")
    size = 2 if specifier.startswith("@") else 1
    name = "/".join(parts[:size])
    rest = "/".join(parts[size:])
    return name, ("./" + rest if rest else ".")


def _types_of(entry: object) -> str:
    """The `types` path in an `exports` entry, however its conditions nest."""
    if isinstance(entry, str):
        return entry if entry.endswith(_TYPE_FILES) else ""
    if isinstance(entry, dict):
        if isinstance(entry.get("types"), str):
            return entry["types"]
        for value in entry.values():
            found = _types_of(value)
            if found:
                return found
    return ""


def _type_file(package: Path, subpath: str) -> Path | None:
    try:
        manifest = json.loads((package / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {}
    exports = manifest.get("exports")
    found = ""
    if isinstance(exports, dict):
        found = _types_of(exports.get(subpath)) if subpath in exports else (
            _types_of(exports) if subpath == "." and not any(k.startswith(".") for k in exports) else ""
        )
    if not found and subpath == ".":
        found = str(manifest.get("types") or manifest.get("typings") or "")
    candidates = [package / found] if found else []
    stem = subpath[2:] if subpath != "." else ""
    candidates += [package / f"{stem}{ext}" for ext in _TYPE_FILES] if stem else []
    candidates += [package / stem / f"index{ext}" for ext in _TYPE_FILES]
    return next((path for path in candidates if path.is_file()), None)


def _resolve(importer: Path, specifier: str) -> Path | None:
    stem = (importer.parent / specifier).resolve()
    base = stem.with_suffix("") if stem.suffix in (".js", ".mjs", ".cjs", ".ts", ".mts", ".cts") else stem
    options = [Path(f"{base}{ext}") for ext in _TYPE_FILES] + [base / f"index{ext}" for ext in _TYPE_FILES]
    return next((path for path in options if path.is_file()), None)


def _names_of_type_file(path: Path, depth: int, seen: set[Path]) -> list[str]:
    if path in seen or depth > MOST_DEPTH:
        return []
    seen.add(path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    names = list(_DECLARED.findall(text))
    for listed, _source in _LISTED.findall(text):
        for part in listed.split(","):
            name = re.split(r"\s+as\s+", re.sub(r"^\s*type\s+", "", part.strip()))[-1].strip()
            if name and name != "default":
                names.append(name)
    if _DEFAULT.search(text):
        names.append("default")
    for alias, source in _STAR.findall(text):
        if alias:
            names.append(alias)
        elif source.startswith("."):
            target = _resolve(path, source)
            if target is not None:
                names += _names_of_type_file(target, depth + 1, seen)
    return names


def script_package_exports(project: Path, specifier: str) -> list[str] | None:
    """The names a JavaScript or TypeScript package's entry exports, or None when it cannot be read here."""
    if not enabled() or not specifier or specifier.startswith((".", "/", "node:")):
        return None
    name, subpath = _split(specifier)
    for base in (project, project.parent):
        package = base / "node_modules" / name
        if package.is_dir():
            entry = _type_file(package, subpath)
            if entry is None and subpath == ".":
                entry = _type_file(base / "node_modules" / "@types" / name.replace("@", "").replace("/", "__"), ".")
            if entry is not None:
                names = sorted(dict.fromkeys(_names_of_type_file(entry, 0, set())))
                return names[:MOST_NAMES]
    return None


# --- Python ----------------------------------------------------------------------

def _site_packages(project: Path) -> list[Path]:
    found: list[Path] = []
    for base in (project, project.parent):
        found += sorted((base / ".venv" / "lib").glob("python*/site-packages"))
    return found


def python_package_exports(project: Path, dotted: str) -> list[str] | None:
    """The public names an installed Python module defines at its top level, or None when it cannot be read here."""
    if not enabled() or not dotted or dotted.startswith("."):
        return None
    parts = dotted.split(".")
    for site in _site_packages(project):
        stem = site.joinpath(*parts)
        for candidate in (stem / "__init__.py", stem.with_suffix(".py")):
            if not candidate.is_file():
                continue
            try:
                tree = ast.parse(candidate.read_text(encoding="utf-8", errors="replace"))
            except (SyntaxError, OSError):
                return None
            names: list[str] = []
            listed: list[str] | None = None
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.append(node.name)
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            if target.id == "__all__" and isinstance(node.value, (ast.List, ast.Tuple)):
                                listed = [e.value for e in node.value.elts if isinstance(e, ast.Constant)]
                            else:
                                names.append(target.id)
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    names.append(node.target.id)
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    names += [(a.asname or a.name).split(".")[0] for a in node.names if a.name != "*"]
            chosen = listed if listed else [n for n in names if not n.startswith("_")]
            return sorted(dict.fromkeys(chosen))[:MOST_NAMES]
    return None


# --- the tool a model can look with ------------------------------------------------

def _project_of(repo_root: str | Path) -> Path:
    root = Path(repo_root)
    try:
        from app.tools.repository import pinned_project_directory

        pinned = pinned_project_directory(root)
    except Exception:  # noqa: BLE001 - the workspace root is searched instead
        pinned = None
    return root / pinned if pinned else root


def exports_of(repo_root: str | Path, module: str) -> dict:
    """What the installed package or module `module` exports, for the tool; {"error": ...} when it cannot be read."""
    module = str(module or "").strip()
    if not module or module.startswith((".", "/")):
        return {"error": "Name an installed package or one of its subpaths, as an import writes it "
                         "(`hono/testing`, `@hono/node-server`, `fastapi`, `jwt`); for a file of this project, read it."}
    project = _project_of(repo_root)
    for read in (script_package_exports, python_package_exports):
        names = read(project, module)
        if names is not None:
            return {"module": module, "exports": names,
                    "note": "Only these names exist; import from this list or write the function yourself."}
    return {"error": f"`{module}` is not installed in this project, or its files cannot be read. "
                     "Install it first, or check the name with look_up_package."}


def exports_tools(repo_root: str | Path) -> list:
    """The `module_exports` tool as a list, empty when it is switched off."""
    if not enabled():
        return []
    from langchain_core.tools import tool

    @tool
    def module_exports(module: str) -> dict:
        """Read the names an installed package really exports, before importing a name from it.

        Use it whenever you are about to import something from a package you are not sure of: a name you remember
        may not exist (a test client, a helper). Reads the installed files; runs nothing.

        Args:
            module: the package or subpath as an import writes it - `hono/testing`, `@hono/node-server`,
                `fastapi`, `jwt`, `sqlalchemy.orm`.
        """
        return exports_of(repo_root, module)

    return [module_exports]
