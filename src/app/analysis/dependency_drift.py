"""Third-party packages the code imports that no manifest declares (Initiative K.4).

Measured: one run's product imported `jsdom` in three files under an empty
`devDependencies`, a full `node_modules` and a lockfile of thirty-nine
packages - the bare install had landed it somewhere the product's own
commands never read, and a clean install (`npm ci`) provides none of it.
The runner failed and the failure looked like a code bug; it was a manifest
bug, and reconciling imports against manifests is arithmetic, not judgement.

So this module does the reconciliation deterministically, and the CI gate
bundles what it finds into one defect for the fixer (`engineering.
_what_the_manifests_do_not_declare`) instead of a model discovering it in a
failing runner at 3 a.m. Two languages, the ones the evidence is in and the
ones whose manifests have one obvious shape: JavaScript/TypeScript against
`package.json`, Python against `requirements*.txt` or `pyproject.toml`.
Another language's manifest joins when its evidence does.

Narrow, because it accuses: a language is only reconciled when a manifest
for it exists, builtins, relative specifiers and project-local modules are
never dependencies, and the Python side reports distribution names through
a small alias table - `yaml` must be declared `pyyaml`, and naming the
import instead would send the fixer to declare a package that does not
exist.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

from app.agents.brief_constraints import (
    _A_PACKAGE_NAME,
    _IMPORTS_A_PACKAGE,
    _A_SCRIPT,
    _NODE_BUILTIN,
    _not_the_product,
)
from app.analysis.walk import files_under

#: Python import names whose distribution is spelled differently. Only the
#: common ones: an unlisted alias reads as undeclared, and the bundled defect
#: is where that gets answered - a false positive costs one declaration, a
#: false negative is a runner that fails with nothing pointing at the cause.
_PYTHON_ALIASES = {
    "yaml": "pyyaml",
    "pil": "pillow",
    "bs4": "beautifulsoup4",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "skimage": "scikit-image",
    "dotenv": "python-dotenv",
    "dateutil": "python-dateutil",
    "attr": "attrs",
    "jwt": "pyjwt",
    "serial": "pyserial",
    "git": "gitpython",
    "openssl": "pyopenssl",
    "magic": "python-magic",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "fitz": "pymupdf",
    "lxml": "lxml",
    "websocket": "websocket-client",
    "nanoid": "nanoid",
}

_PY_IMPORT = re.compile(
    r"^[ \t]*(?:from[ \t]+([A-Za-z_][\w.]*)[ \t]+import|import[ \t]+([A-Za-z_][\w.]*))",
    re.M,
)

#: Code suffixes the CI gate asks about before running the reconciliation.
CODE_SUFFIXES: tuple[str, ...] = (*_A_SCRIPT, ".py")


def _the_package_in(specifier: str) -> str | None:
    """The package a bare JavaScript specifier names, or None when it is not one."""
    if specifier.startswith((".", "/", "#")) or "//" in specifier:
        return None
    if specifier.startswith("node:") or not _A_PACKAGE_NAME.match(specifier):
        return None
    name = (
        "/".join(specifier.split("/")[:2])
        if specifier.startswith("@")
        else specifier.split("/")[0]
    )
    return None if name in _NODE_BUILTIN else name


def _javascript_imports(project: Path) -> dict[str, str]:
    """package -> an importing file, relative to the project."""
    imported: dict[str, str] = {}
    for script in files_under(project, _not_the_product()):
        if script.suffix not in _A_SCRIPT or "node_modules" in script.parts:
            continue
        try:
            source = script.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for specifier in _IMPORTS_A_PACKAGE.findall(source):
            name = _the_package_in(specifier)
            if name:
                imported.setdefault(name, str(script.relative_to(project)))
    return imported


def _javascript_declared(project: Path) -> set[str] | None:
    """What `package.json` declares, or None when there is no manifest."""
    try:
        manifest = json.loads((project / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(manifest, dict):
        return None
    declared: set[str] = set()
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        section = manifest.get(key)
        if isinstance(section, dict):
            declared.update(str(name) for name in section)
    return declared


def _python_imports(project: Path) -> dict[str, str]:
    """top-level module -> an importing file, relative to the project."""
    imported: dict[str, str] = {}
    for script in files_under(project, _not_the_product()):
        if script.suffix != ".py":
            continue
        try:
            source = script.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for groups in _PY_IMPORT.findall(source):
            module = str(next((part for part in groups if part), "")).split(".")[0]
            if module:
                imported.setdefault(module, str(script.relative_to(project)))
    return imported


def _is_a_python_builtin_or_local(project: Path, module: str) -> bool:
    """Whether Python itself or this project provides the module."""
    if module in sys.stdlib_module_names:
        return True
    for candidate in (
        project / f"{module}.py",
        project / module / "__init__.py",
        project / "src" / f"{module}.py",
        project / "src" / module / "__init__.py",
    ):
        if candidate.exists():
            return True
    return False


def _a_requirement_name(line: str) -> str:
    """The distribution a requirement line names, without version or extras."""
    name = line.strip()
    if not name or name.startswith(("#", "-", "--")):
        return ""
    name = re.split(r"[\s;<>=!~@\[;]", name, 1)[0]
    return name.strip().lower()


def _python_declared(project: Path) -> set[str] | None:
    """What the Python manifests declare, or None when there is nothing to
    reconcile against. A `requirements*.txt` reconciles even when empty - it
    is the project saying "these are my dependencies"; a `pyproject.toml`
    only reconciles when it actually declares some, because a build-system
    header alone says nothing about them."""
    declared: set[str] | None = None
    for manifest in sorted(project.glob("requirements*.txt")):
        try:
            lines = manifest.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        declared = declared if declared is not None else set()
        declared.update(name for name in map(_a_requirement_name, lines) if name)
    try:
        import tomllib

        parsed = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
        from_project = [
            _a_requirement_name(str(item))
            for item in (
                (parsed.get("project") or {}).get("dependencies") or []
            )
        ]
        for group in ((parsed.get("project") or {}).get("optional-dependencies") or {}).values():
            from_project.extend(_a_requirement_name(str(item)) for item in group or [])
        from_poetry = [
            str(name).lower()
            for name in ((parsed.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
        ]
        found = {name for name in (*from_project, *from_poetry) if name}
        if found:
            declared = (declared or set()) | found
    except Exception:  # noqa: BLE001 - an unreadable pyproject declares nothing
        pass
    return declared


def _normalised(name: str) -> str:
    """A distribution's name as the package index compares them (PEP 503)."""
    return re.sub(r"[-_.]+", "-", str(name or "").strip().lower())


def _what_is_installed(project: Path) -> tuple[dict[str, str], dict[str, set[str]]]:
    """From the project's own environment: import name -> distribution, and what each distribution requires.

    Read from the installed packages' records (`*.dist-info`: `METADATA`,
    `top_level.txt`), so nothing is run and no table is kept by hand. Measured
    on one run: the code imported `jose` and `starlette`, the manifest declared
    `python-jose` and `fastapi`, and both were reported undeclared - `jose` is
    what `python-jose` installs, and `starlette` is what `fastapi` requires -
    while the alias table knew neither.
    """
    provides: dict[str, str] = {}
    requires: dict[str, set[str]] = {}
    for site in [*project.glob("*/lib/python*/site-packages"), *project.glob("*/Lib/site-packages")]:
        if site.parts[len(project.parts)] not in {".venv", "venv", "env", ".env"}:
            continue
        for info in site.glob("*.dist-info"):
            try:
                metadata = (info / "METADATA").read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            found = re.search(r"^Name:\s*(\S+)", metadata, re.M)
            if not found:
                continue
            distribution = _normalised(found.group(1))
            requires[distribution] = {
                _normalised(re.split(r"[\s;<>=!~\[(]", line, 1)[0])
                for line in re.findall(r"^Requires-Dist:\s*(.+)$", metadata, re.M)
                if "extra ==" not in line
            }
            try:
                tops = (info / "top_level.txt").read_text(encoding="utf-8", errors="replace").split()
            except OSError:
                tops = []
            for top in tops or [found.group(1).replace("-", "_")]:
                provides.setdefault(top.strip().lower(), distribution)
    return provides, requires


def _what_a_clean_install_brings(declared: set[str], requires: dict[str, set[str]]) -> set[str]:
    """The declared distributions and everything they require, as installed here."""
    brought, todo = set(), [_normalised(name) for name in declared]
    while todo:
        name = todo.pop()
        if name in brought:
            continue
        brought.add(name)
        todo.extend(requires.get(name, ()))
    return brought


def _declares(declared: set[str], distribution: str) -> bool:
    """Whether a declared set covers a distribution, exact or dash-suffixed.

    `psycopg2-binary` declares `psycopg2`: what the code imports is the
    import name, what a manifest names is the distribution, and the two
    spellings differ by a suffix more often than the alias table knows.
    """
    lowered = distribution.lower()
    return any(
        name == lowered or name.startswith(f"{lowered}-") or lowered.startswith(f"{name}-")
        for name in declared
    )


def undeclared(project: Path) -> list[tuple[str, str, str]]:
    """(package, importing file, language) for every import no manifest declares.

    Sorted, so the bundled defect names the same order every time. Only a
    language with a manifest is reconciled: no `package.json`, nothing to
    accuse JavaScript against; no Python manifest that declares anything,
    nothing to accuse Python against.
    """
    project = Path(project)
    found: list[tuple[str, str, str]] = []

    js_declared = _javascript_declared(project)
    if js_declared is not None:
        for name, file in sorted(_javascript_imports(project).items()):
            if not _declares(js_declared, name):
                found.append((name, file, "javascript"))

    py_declared = _python_declared(project)
    if py_declared is not None:
        provides, requires = _what_is_installed(project)
        brought = _what_a_clean_install_brings(py_declared, requires)
        for module, file in sorted(_python_imports(project).items()):
            if _is_a_python_builtin_or_local(project, module):
                continue
            distribution = provides.get(module.lower()) or _PYTHON_ALIASES.get(module.lower(), module.lower())
            if _declares(py_declared, distribution) or _normalised(distribution) in brought:
                continue
            found.append((distribution, file, "python"))

    return found


#: How the bundled defect begins, so it can be told apart and checked again.
OPENING = "The code imports packages no manifest declares:"
#: A package the defect names: "`name` (imported in `file`)".
_NAMED = re.compile(r"`([^`]+)` \(imported in `")


def still_undeclared(project: Path, description: str) -> list[str] | None:
    """The packages a bundled defect names that are still undeclared; None when it is not one."""
    if not str(description or "").startswith(OPENING):
        return None
    named = _NAMED.findall(description)
    now = {name.lower() for name, _, _ in undeclared(Path(project))}
    return [name for name in named if name.lower() in now]


#: Where each language's packages are declared, in the order a project is
#: likeliest to keep them; the first that exists is the one to change.
MANIFESTS = {
    "javascript": ("package.json",),
    "python": ("requirements.txt", "pyproject.toml"),
}


def _the_manifests(found: Sequence[tuple[str, str, str]], project: Path | None) -> list[str]:
    """The manifest each language in `found` is declared in, relative to the project."""
    chosen: list[str] = []
    for language in dict.fromkeys(language for _, _, language in found):
        names = MANIFESTS.get(language, ())
        here = next((n for n in names if project is not None and (Path(project) / n).is_file()), None)
        if here is None and project is not None and language == "python":
            here = next((m.name for m in sorted(Path(project).glob("requirements*.txt"))), None)
        if here or names:
            chosen.append(here or names[0])
    return list(dict.fromkeys(chosen))


def _where_each_belongs(found: Sequence[tuple[str, str, str]], project: Path | None) -> str:
    """"declare `a` in `package.json`; `b`, `c` in `requirements.txt`" - each language's packages in its own manifest.

    Measured on one gate run: the defect named both manifests and listed the
    packages by importing file only, and the fix put a JavaScript package
    into `requirements.txt`, which then failed to install.
    """
    parts = []
    for language in dict.fromkeys(language for _, _, language in found):
        manifest = (_the_manifests([item for item in found if item[2] == language], project) or ["its manifest"])[0]
        names = ", ".join(f"`{name}`" for name, _, lang in found[:8] if lang == language)
        if names:
            parts.append(f"declare {names} in `{manifest}` ({language} packages)")
    return "; ".join(parts) or "declare each in its language's manifest"


def the_bundled_defect(found: Sequence[tuple[str, str, str]], *, owner: str, project: Path | None = None) -> Any:
    """One defect naming every undeclared import, for the fixer to declare.

    Bundled, because thirteen defects from one root cause were the measured
    failure this replaces: one missing declaration is one declaration to add,
    whoever added the imports. Its files are the manifests, where the change
    is: measured on one gate run, it named the importing files, and the fix
    rewrote `database.py`, `main.py` and a page component and left the
    manifests as they were - the defect open by construction.
    """
    from app.agents.specialists import ReportedDefect

    named = "; ".join(f"`{name}` (imported in `{file}`)" for name, file, _ in found[:8])
    extra = f" and {len(found) - 8} more" if len(found) > 8 else ""
    return ReportedDefect(
        description=(
            f"{OPENING} {named}{extra}. "
            "A clean install provides none of them - this fails when the code runs."
        ),
        severity="major",
        reproduction_steps=(
            "Read the imports named above, then the manifests: no entry declares them."
        ),
        expected_behavior=(
            "Every third-party package the code imports is declared by a manifest "
            "a clean install reads: " + _where_each_belongs(found, project) + "."
        ),
        actual_behavior=(
            f"Undeclared: {named}{extra} (the harness's manifest reconciliation)"
        ),
        affected_files=_the_manifests(found, project),
        owner=owner,
    )


__all__ = ["CODE_SUFFIXES", "MANIFESTS", "OPENING", "still_undeclared", "the_bundled_defect", "undeclared"]
