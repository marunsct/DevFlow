"""Every module under `src/app` is imported by the product, not only by its tests.

`test_every_public_symbol_has_a_caller` counts a mention in `tests/` as a
caller, by design - and that is how a whole package can sit unwired while
looking reached: the deploy generators, the old scaffolder and a build
verifier were each imported by a test and by nothing the harness runs. The
routing tests even patched two of them "defensively", which read as though the
graph called them. All were removed in the review of 2026-10-04
(docs/harness-improvement-plan.md, R5); this fails on the next one.

A module counts as reached when another module under `src/app` imports it, when
it is an entry point a process is started with, or when a script in this
repository imports it. A test's import does not count.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

#: Started by a process, not imported: the command-line entry point.
ENTRY_POINTS = {"app.main"}

#: Outside `src/app`, and imported by name.
SCRIPT_DIRECTORIES = ("scripts", "evaluation")


def _name(path: Path) -> str:
    parts = path.relative_to(SRC).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _imports(path: Path) -> set[str]:
    """Every module this file imports, as dotted names, wherever the import sits."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
            # `from app.stacks import release` imports the module `app.stacks.release`.
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith("app."):
            # `importlib.import_module("app.x")`, a Celery task path, a patch target.
            found.add(node.value.split(":", 1)[0])
    return found


def test_every_module_is_imported_by_something_the_harness_runs() -> None:
    modules = {
        _name(path): path
        for path in (SRC / "app").rglob("*.py")
        if "__pycache__" not in path.parts
    }
    imported_by: dict[str, set[str]] = {name: set() for name in modules}
    for name, path in modules.items():
        for target in _imports(path):
            if target in imported_by and target != name:
                imported_by[target].add(name)
    for directory in SCRIPT_DIRECTORIES:
        for path in (ROOT / directory).rglob("*.py"):
            for target in _imports(path):
                if target in imported_by:
                    imported_by[target].add(str(path.relative_to(ROOT)))

    unreached = sorted(
        name for name, users in imported_by.items()
        if not users and name not in ENTRY_POINTS and name.count(".") >= 1
        and not modules[name].name == "__init__.py"
    )
    assert not unreached, (
        "Modules nothing in the harness imports - only tests, or nothing at all. Wire "
        "each into the code that needs it, or delete it:\n  " + "\n  ".join(unreached)
    )
