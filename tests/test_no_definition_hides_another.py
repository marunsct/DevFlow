"""No function is defined twice in one scope.

Python keeps the second definition and drops the first without a word, and
pytest collects by name, so a test written twice under one name runs once. Three
test modules had this: `test_manage_cli.py` held two different tests called
`test_a_dry_run_reports_without_writing`, and the dry run of `reconcile_runs`
had never executed. In application code the same slip replaces behaviour.
"""

from __future__ import annotations

import ast
import collections
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _scopes(tree: ast.AST):
    yield tree
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def _defined_twice(source: str) -> list[str]:
    twice = []
    for scope in _scopes(ast.parse(source)):
        names = collections.Counter(
            node.name
            for node in scope.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            # An overload stub, or a property setter, shares its name on purpose.
            and not any(
                (isinstance(d, ast.Name) and d.id == "overload")
                or (isinstance(d, ast.Attribute) and d.attr in {"setter", "deleter", "overload"})
                or (isinstance(d, ast.Attribute) and d.attr == "register")
                for d in node.decorator_list
            )
        )
        twice += [name for name, count in names.items() if count > 1]
    return twice


@pytest.mark.parametrize(
    "path",
    sorted([*(ROOT / "src").rglob("*.py"), *(ROOT / "tests").rglob("*.py")]),
    ids=lambda p: str(p.relative_to(ROOT)),
)
def test_no_function_is_defined_twice(path: Path) -> None:
    twice = _defined_twice(path.read_text(encoding="utf-8"))

    assert not twice, f"{path.relative_to(ROOT)} defines these twice: {twice}"


def test_the_check_finds_a_hidden_test() -> None:
    source = "def test_a():\n    assert 1\n\n\ndef test_a():\n    assert 2\n"

    assert _defined_twice(source) == ["test_a"]


def test_the_check_finds_one_inside_a_class() -> None:
    source = "class T:\n    def test_a(self): ...\n    def test_a(self): ...\n"

    assert _defined_twice(source) == ["test_a"]


def test_a_property_setter_is_not_a_duplicate() -> None:
    source = (
        "class T:\n"
        "    @property\n    def x(self): ...\n"
        "    @x.setter\n    def x(self, v): ...\n"
    )

    assert _defined_twice(source) == []
