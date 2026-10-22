"""The harness must not import through a path its dependency has deprecated.

`from langgraph.constants import Send` worked and warned:

    LangGraphDeprecatedSinceV10: Importing Send from langgraph.constants is
    deprecated. Please use 'from langgraph.types import Send' instead.
    Deprecated in LangGraph V1.0 to be removed in V2.0.

A warning in a suite of 4,800 tests is invisible, and the removal it announces
turns an import-time crash into every stage of every run failing at once. The
canonical location was confirmed against the API reference entry for
`langgraph.types.Send` rather than taken from the warning text.

Kept as a test rather than a lint rule because it is about this harness's own
dependency surface: the point is that a re-exported name which still works today
is not a name to keep using.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parent.parent / "src"

#: Module -> where its names live now. A module that only re-exports for
#: backwards compatibility belongs here whether or not it warns yet.
MOVED: dict[str, str] = {
    "langgraph.constants": "langgraph.types",
}


def _python_files() -> list[Path]:
    return sorted(
        path
        for path in SOURCE.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def test_there_is_source_to_check() -> None:
    """A scan over nothing passes, which is the wrong kind of green."""
    assert len(_python_files()) > 50


@pytest.mark.parametrize("path", _python_files(), ids=lambda p: p.name)
def test_no_module_imports_from_a_deprecated_path(path: Path) -> None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as error:  # a file that will not parse is its own failure
        pytest.fail(f"{path} does not parse: {error}")

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in MOVED:
            names = ", ".join(alias.name for alias in node.names)
            pytest.fail(
                f"{path.relative_to(SOURCE)}:{node.lineno} imports {names} from "
                f"{node.module}, which is deprecated. Import from "
                f"{MOVED[node.module]} instead."
            )
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in MOVED, (
                    f"{path.relative_to(SOURCE)}:{node.lineno} imports the "
                    f"deprecated module {alias.name}; use {MOVED[alias.name]}."
                )


def test_send_is_importable_from_where_the_harness_now_asks() -> None:
    """The replacement has to exist, or this test only moves the breakage."""
    from langgraph.types import Send as FromTypes

    from app.graph.workflow import Send as AsTheWorkflowImportsIt

    assert AsTheWorkflowImportsIt is FromTypes
