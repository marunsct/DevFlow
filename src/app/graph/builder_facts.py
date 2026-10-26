"""The facts a fixer is given after a failure, given to the drafting builder before it writes (behind `BUILDER_FACTS`).

Measured over a night of small-model runs on a TypeScript service: the faults that cost runs their first half hour - a
relative import written `./app.js` for `./app.ts`, a router handed to `app.use` for `app.route`, `json` imported from
`hono`, `hono/middleware` imported as a path - are each stated in the stack pack's guide or readable in the installed
package's files. The drafting stage, which writes most of the product one file per call, was shown neither: the agent
loop and the fixers were (`contract.describe`, `package_exports`), a round later. Drafting's compile check read the
language service, which does not report a router handed to `app.use`; `tsc` does (`compiler_errors`).

Three facts, all certain, none a guess: the pack's guide; for each package the project declares, the names its entry
really exports and the import paths it offers; and in the redraft, the compiler's own errors on the file. Nothing about
tests that fail, so the builder still builds to the specification.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Sequence

from app.switches import is_on

logger = logging.getLogger(__name__)

#: Off in code like every switch; the compose file turns it on.
ON_BY_DEFAULT = False

#: Bounds that keep a small model's request short.
MOST_GUIDE_CHARACTERS = 3_000
MOST_PACKAGES = 8
MOST_NAMES = 40
MOST_PATHS = 80
#: Packages that are tooling, not something the product's code imports.
_TOOLING = re.compile(r"^(?:@types/|typescript$|@playwright/|playwright$|ts-node$|tsx$|eslint|prettier|jest$|vitest$)")


def enabled() -> bool:
    return is_on("BUILDER_FACTS", ON_BY_DEFAULT)


def _pack_and_project(root: Path) -> tuple[Any, dict, Path] | None:
    from app.stacks import contract

    found = contract.the_pack(root)
    if found is None:
        return None
    pack, record = found
    project = str(record.get("project") or "")
    return pack, record, (root / project if project else root)


def _guide(pack: Any, record: dict) -> str:
    project = str(record.get("project") or "")
    text = pack.filled(pack.guide, project, record.get("title") or project, record.get("package"))
    return text[:MOST_GUIDE_CHARACTERS].strip()


def _script_packages(project: Path, for_a_test: bool) -> list[str]:
    try:
        manifest = json.loads((project / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    names = list((manifest.get("dependencies") or {}).keys())
    if for_a_test:
        names += list((manifest.get("devDependencies") or {}).keys())
    return [n for n in dict.fromkeys(names) if not _TOOLING.match(n)][:MOST_PACKAGES]


def _import_paths(project: Path, name: str) -> list[str]:
    try:
        exports = json.loads((project / "node_modules" / name / "package.json").read_text(encoding="utf-8")).get("exports")
    except (OSError, ValueError):
        return []
    if not isinstance(exports, dict):
        return []
    keys = [k for k in exports if k.startswith(".") and "*" not in k and k != "./package.json"]
    return sorted(name if k == "." else f"{name}/{k[2:]}" for k in keys)


def _python_packages(project: Path) -> list[str]:
    names: list[str] = []
    for requirements in sorted(project.glob("requirements*.txt")):
        try:
            lines = requirements.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            name = re.split(r"[\s<>=!~\[;]", line.strip(), maxsplit=1)[0]
            if name and not name.startswith(("#", "-")):
                names.append(name.lower().replace("-", "_"))
    return list(dict.fromkeys(names))[:MOST_PACKAGES]


def _package_lines(project: Path, path: str) -> list[str]:
    from app.analysis import package_exports

    try:
        from app.analysis.file_kinds import classify_file

        for_a_test = classify_file(path) == "test"
    except Exception:  # noqa: BLE001 - a test's packages are the larger set
        for_a_test = True
    lines: list[str] = []
    if path.endswith((".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")):
        for name in _script_packages(project, for_a_test):
            names = package_exports.script_package_exports(project, name) or []
            paths = [p for p in _import_paths(project, name) if p != name]
            if not names and not paths:
                continue
            line = f"- `{name}` exports: {_listed(names, MOST_NAMES, lambda n: n) or '(no names read)'}"
            if paths:
                line += f"; other import paths it offers: {_listed(paths, MOST_PATHS, lambda p: f'`{p}`')}"
            lines.append(line)
    elif path.endswith(".py"):
        for module in _python_packages(project):
            names = package_exports.python_package_exports(project, module)
            if names:
                lines.append(f"- `{module}` defines: {', '.join(names[:MOST_NAMES])}")
    return lines


def _listed(items: list[str], most: int, shown: Callable[[str], str]) -> str:
    """The items, at most `most`, saying how many more there are rather than letting a short list read as all of them."""
    text = ", ".join(shown(item) for item in items[:most])
    return f"{text} and {len(items) - most} more" if len(items) > most else text


def section(root: str | Path, path: str) -> str:
    """The pack's guide and the installed packages' real exports, for the request that drafts `path`; "" when off."""
    if not enabled():
        return ""
    try:
        found = _pack_and_project(Path(root))
        if found is None:
            return ""
        pack, record, project = found
        parts = []
        guide = _guide(pack, record)
        if guide:
            parts.append(f"--- How this stack is used in this project ---\n{guide}")
        packages = _package_lines(project, path)
        if packages:
            parts.append(
                "--- What the installed packages really export (read from their files) ---\n"
                + "\n".join(packages)
                + "\nImport a name or path from this list; one the list does not have, where nothing is said to be left"
                  " out, does not exist in that package."
            )
        return "\n\n".join(parts)
    except Exception:  # noqa: BLE001 - the request as it was
        logger.debug("Could not add the builder's facts", exc_info=True)
        return ""


Runner = Callable[[Sequence[str], str, str], dict]


def compiler_lines(repo_root: str | Path, paths: Sequence[str], runner: Runner | None = None) -> list[str]:
    """The compiler's errors on these drafted files, as the drafting repair reads findings; [] when off or clean."""
    if not enabled() or not paths:
        return []
    try:
        from app.stacks import compiler_errors, contract

        found = contract.the_pack(repo_root)
        if found is None or not getattr(found[0], "typecheck", ()):
            return []
        pack, record = found
        project = str(record.get("project") or "")
        if runner is None:
            from app.stacks.scaffold import sandbox_runner

            runner = sandbox_runner(repo_root)
        outcome = runner(list(pack.typecheck), "default", project) or {}
        wanted = set(paths)
        lines = []
        for file, line, _code, message in compiler_errors.parse(f"{outcome.get('stdout') or ''}\n{outcome.get('stderr') or ''}"):
            relative = f"{project}/{file}" if project else file
            if relative in wanted:
                lines.append(f"- In `{relative}` line {line}: {message}")
        return lines
    except Exception:  # noqa: BLE001 - the repair goes on with what it has
        logger.debug("Could not read the compiler's errors for the drafts", exc_info=True)
        return []


__all__ = ["ON_BY_DEFAULT", "compiler_lines", "enabled", "section"]
