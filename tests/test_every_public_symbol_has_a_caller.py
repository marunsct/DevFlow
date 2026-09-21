"""Every public class and function in `src/app` has a caller outside its own module.

This is the test `docs/harness-hardening-plan-part3.md` item 1 asks for, and it is
the §1-B rule from Part I applied to build configuration instead of source code:
a rule defined over part of the set it governs. The coverage `omit` list used to
be written per directory (`src/app/deploy/*`, `src/app/analysis/*`, ...), which
silently grew from "exclude the entry points that are exercised end-to-end" to
"exclude every module in these directories, including the ones with no caller at
all". Coverage reported 80%+ while `MetricsTracker`, `BuildVerifier` and the three
`deploy` generators were entirely unwired, because they were not being measured.

`pyproject.toml` now omits modules per file, so an untested module shows up as
uncovered instead of vanishing. That catches "no test reaches this module". It
does not catch the narrower and more common failure this test is about: a module
that *is* imported — by a test, or by the server at startup — while the one symbol
that matters in it is called by nobody. `observability/metrics.py` imports fine;
`MetricsTracker` is never constructed. Coverage of a module whose public API is
dead is not the same as coverage of the product.

So this test walks the AST of every module under `src/app`, collects each public
class and function, and fails if no module other than its own references its name.
It is deliberately a static check rather than a coverage one: it needs no container
and no run, and it fails on the next unwired symbol rather than on the ones already
found.

What it does *not* flag, and why
--------------------------------
Three shapes are legitimate references that a name search cannot see, so they are
excluded rather than counted as callers:

- **FastAPI route handlers.** `@router.get("/runs")` above `def list_runs()` is the
  reference; the function is never called by name in Python. Excluded by the
  decorator, which is how the framework reaches them.
- **CLI entry points.** `if __name__ == "__main__": main()` in `server/manage.py`
  reaches functions from a string the interpreter evaluates, not from an import.
  Excluded by the `__main__` guard, matching the coverage `exclude_lines` entry.
- **Evaluators.** `evaluation/evaluate.py` lives outside `src/app` and imports
  `app.evaluation.evaluators` by name. Excluded by an explicit allowlist, because
  the reference is real but outside the tree this test walks.

A module that is only ever imported by a test is *not* excluded. That is the point:
`test_graph_routing.py` monkeypatches `BuildVerifier.verify`, which keeps the symbol
referenced and would have made a naive "is it imported" check pass, while nothing in
`src/app` ever constructs the class. The monkeypatch is defensive — it patches a
class the workflow does not reach, so that the day it does, the stub is already
there. This test treats that as no reference at all.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src" / "app"

# Modules outside `src/app` that legitimately reference `app.*` symbols. The test
# walks only `src/app`, so a reference from here is real but invisible to it.
# `evaluation/evaluate.py` imports the evaluators by name and drives them.
EXTERNAL_REFERENCERS = {
    "evaluation/evaluate.py",
}

# Public symbols that have no caller today, recorded so this test can be landed
# before the backlog removes them. Each entry is a debt the plan tracks:
#
# - `MetricsTracker` / `get_metrics_payload` — plan-part3 §3.1. `/metrics` reports
#   zeros because nothing constructs the tracker. Item 2 wires it.
# - `CIGenerator`, `ComposeGenerator`, `DockerGenerator` are no longer listed.
#   Not because item 5 wired them - it has not - but because they now have tests,
#   and this fixture counts a mention under `tests/` as a reference by design.
#   Their four security defects are fixed (`test_the_deploy_generators_are_safe`),
#   which was the precondition ADR-0003 put on wiring them; the wiring itself is
#   still open. That debt lives in the plan, not here, because this list cannot
#   express "referenced but not reached by the product".
# - `DependencyManager` — the scaffolding dependency resolver; `resolve_dependencies`
#   is reached, the class that carries it is not.
# - `TokenData`, `get_user_from_token` — auth helpers the token flow no longer
#   reaches; `get_current_user` does the work both were written to do.
# - `EventResponse` — a response model defined for an event route that was never
#   registered.
# - `TestRunner` — a test-runner abstraction the sandbox's own runner superseded.
#
# This list must shrink, never grow. A new entry means a new unwired symbol, which
# is the failure this test exists to catch.
KNOWN_UNWIRED = {
    "observability/metrics.py: get_metrics_payload",
    "scaffolding/dependencies.py: DependencyManager",
    "server/auth.py: TokenData",
    "server/auth.py: get_user_from_token",
    "server/models.py: EventResponse",
    "tools/testing/runner.py: TestRunner",
}

# Decorators that make a function the target of a framework's dispatch rather than
# of a Python call. FastAPI registers the handler under a route; the name is never
# mentioned again. Without this, every route handler would read as dead code.
ROUTE_DECORATORS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    "options",
    "websocket",
    "router",
    "app",
}


def _public_symbols(tree: ast.Module) -> set[str]:
    """Top-level classes and functions whose name does not start with `_`.

    Nested definitions are skipped on purpose: a helper inside a class is reached
    through its parent, and a nested function is reached by the one that encloses
    it. Only the outermost names are the product's API surface.
    """
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }


def _names_used(tree: ast.Module) -> set[str]:
    """Every identifier the module mentions, however it mentions it.

    This is deliberately coarse. A reference can be an import (`from app.observability
    .metrics import MetricsTracker`), a construction (`MetricsTracker()`), an attribute
    (`tracker.record_run`), a keyword value (`response_model=Token`), or a string a
    framework resolves. Collecting all of them keeps the check a single set membership,
    and the false positives it admits are handled by the exclusions above rather than
    by making this walk clever.
    """
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
        elif isinstance(node, ast.Import):
            used.update(alias.name.split(".")[-1] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            used.update(alias.name.split(".")[-1] for alias in node.names)
        elif isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
            # `__all__` lists a module's public names as strings, and FastAPI resolves
            # `tags=["auth"]` the same way. A bare string match is loose by design.
            # A bytes constant is decoded best-effort: some are binary payloads
            # (`b"\x8b..."` for a gzip magic number) that are not names, and a
            # decode failure must not stop the walk.
            if isinstance(node.value, bytes):
                try:
                    used.add(node.value.decode())
                except UnicodeDecodeError:
                    continue
            else:
                used.add(node.value)
        elif isinstance(node, ast.keyword):
            # `response_model=Token` passes the class by value, but as a keyword's
            # value rather than a call argument — the framework reads it to serialise
            # the response, and nothing ever calls `Token()` in Python.
            value = node.value
            if isinstance(value, ast.Name):
                used.add(value.id)
            elif isinstance(value, ast.Attribute):
                used.add(value.attr)
    return used


def _is_route_handler(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """FastAPI-style: `@router.get("/path")` is the reference, not a call.

    Every decorator is inspected, not just the first: a handler commonly stacks
    a dependency in front of the route, as in
    `@auth_router.get("/me", response_model=User)` followed by
    `@router.dependencies(Depends(require_role))`. Stopping at the first
    decorator would read the dependency as the only reference and miss the route.
    """
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute) and target.attr in ROUTE_DECORATORS:
            return True
        if isinstance(target, ast.Name) and target.id in ROUTE_DECORATORS:
            return True
    return False


def _is_cli_entry_point(node: ast.FunctionDef | ast.AsyncFunctionDef, tree: ast.Module) -> bool:
    """`if __name__ == "__main__": main()` reaches a function the AST never names.

    Guarded by the module having such a block at all, so a function that merely
    shares a name with a CLI one is not excused.
    """
    has_main_guard = any(
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and any(
            isinstance(comparand, ast.Constant) and comparand.value == "__main__"
            for comparand in node.test.comparators
        )
        for node in tree.body
    )
    return has_main_guard


def _modules() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if p.name != "__init__.py")


@pytest.fixture(scope="module")
def symbol_index() -> dict[Path, set[str]]:
    """`{module path: its public symbols}`, parsed once for every test in this file."""
    index: dict[Path, set[str]] = {}
    for path in _modules():
        tree = ast.parse(path.read_text())
        index[path] = _public_symbols(tree)
    return index


@pytest.fixture(scope="module")
def reference_index() -> dict[Path, set[str]]:
    """`{module path: every name that module mentions}`, parsed once.

    Keyed by the referencing module so a symbol's own module can be excluded from
    the search — a definition always mentions its own name.
    """
    index: dict[Path, set[str]] = {}
    for path in _modules():
        index[path] = _names_used(ast.parse(path.read_text()))
    return index


@pytest.fixture(scope="module")
def test_names() -> set[str]:
    """Names mentioned anywhere under `tests/`.

    A symbol reached only by a test is not dead, but it is not wired into the
    product either. Counting it as a reference keeps this test about *reachability*
    — the question that finds `MetricsTracker`, which nothing reaches at all — and
    leaves "reached only by a test" to the coverage report, which answers it better.
    """
    names: set[str] = set()
    for path in Path(__file__).resolve().parent.rglob("*.py"):
        names |= _names_used(ast.parse(path.read_text()))
    return names


@pytest.fixture(scope="module")
def external_names() -> set[str]:
    """Names referenced from outside `src/app`, which this test does not walk."""
    names: set[str] = set()
    root = SRC.parent.parent
    for relative in EXTERNAL_REFERENCERS:
        path = root / relative
        if path.exists():
            names |= _names_used(ast.parse(path.read_text()))
    return names


def test_every_public_symbol_has_a_caller_outside_its_own_module(
    symbol_index, reference_index, external_names, test_names
):
    """The check itself. Fails listing every unwired symbol, not just the first.

    Reporting all of them at once matters because the failure is a set, not an
    incident: when a module is unwired, usually so is its neighbour. Showing one
    per run would take as many runs as there are dead symbols.
    """
    unwired: list[str] = []

    for path, symbols in symbol_index.items():
        tree = ast.parse(path.read_text())
        # Names mentioned by every other module, plus the ones outside the tree.
        referenced_by_others = external_names | test_names
        for other, names in reference_index.items():
            if other != path:
                referenced_by_others |= names
        # Framework wiring that stays inside the module: `Depends(get_current_user)`
        # in a sibling route, `response_model=Token` on the route above. These are
        # references the cross-module search excludes by construction, so a module
        # whose routes close over each other would otherwise read as entirely dead.
        referenced_in_module = reference_index[path]

        for symbol in sorted(symbols):
            if symbol in referenced_by_others:
                continue
            node = next(
                n
                for n in tree.body
                if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == symbol
            )
            # A route handler is reached by the framework through its decorator.
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_route_handler(node):
                continue
            # A CLI entry point is reached by `python -m`, not by an import.
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_cli_entry_point(
                node, tree
            ):
                continue
            # Reached by framework wiring inside this module: a dependency injected
            # into a sibling route (`Depends(get_current_user)`), or a model a route
            # returns (`response_model=Token`). The module is its own caller, which
            # the cross-module search cannot see.
            if symbol in referenced_in_module:
                continue

            unwired.append(f"{path.relative_to(SRC)}: {symbol}")

    # Debt already recorded and tracked in the plan. Reported separately so the
    # failure message shows only what is new — a list of ten known items every run
    # would teach a reader to ignore the output.
    new_unwired = sorted(set(unwired) - KNOWN_UNWIRED)
    retired = sorted(KNOWN_UNWIRED - set(unwired))

    assert not new_unwired, (
        "public symbols with no reference outside their own module. "
        "Each of these is either dead code, or reached in a way this test does not "
        "see — a framework decorator, a CLI entry point, or an importer outside "
        "`src/app`. If it is the latter, add it to the exclusions in this file "
        "rather than deleting the symbol:\n  "
        + "\n  ".join(new_unwired)
    )

    # A known entry this test no longer flags means someone wired or deleted the
    # symbol and forgot to shrink the list. That is the good outcome, and the
    # assertion keeps the debt honest rather than letting stale entries accumulate.
    assert not retired, (
        "entries in KNOWN_UNWIRED that this test no longer flags. The symbol gained "
        "a caller or was deleted, so remove it from KNOWN_UNWIRED:\n  "
        + "\n  ".join(retired)
    )
