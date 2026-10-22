"""Every skip and xfail in the suite says why, and the suite tells a flaky test from a broken one (plan CH.3)."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SKIPPERS = {"skip", "skipif", "xfail", "importorskip"}


def _name(node: ast.AST) -> str:
    return node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", "")


def test_every_skip_and_xfail_states_its_reason():
    bare = []
    for path in sorted((ROOT / "tests").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # A decorator written bare, `@pytest.mark.skip`, says nothing at all.
            for decorator in getattr(node, "decorator_list", None) or []:
                if isinstance(decorator, ast.Attribute) and decorator.attr in _SKIPPERS and "pytest" in ast.unparse(decorator):
                    bare.append(f"{path.name}:{decorator.lineno}")
            if not isinstance(node, ast.Call) or _name(node.func) not in _SKIPPERS:
                continue
            owner = node.func.value if isinstance(node.func, ast.Attribute) else None
            if owner is None or "pytest" not in ast.unparse(owner):
                continue
            has_reason = any(k.arg in ("reason", "msg") for k in node.keywords)
            said = [a for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            if _name(node.func) == "skipif":
                said = said[1:] if node.args and said and node.args[0] is said[0] else []
            if not has_reason and not said and not (_name(node.func) in ("skip", "xfail") and node.args):
                bare.append(f"{path.name}:{node.lineno}")
    assert not bare, f"skips and xfails with no reason: {bare}"


def test_the_kinds_have_owners_and_the_suite_reruns_failures_alone():
    assert "| Kind |" in (ROOT / "tests" / "SKIPS.md").read_text(encoding="utf-8")
    loop = (ROOT / "scripts" / "loop" / "loop.sh").read_text(encoding="utf-8")
    assert 'echo "flaky (passed alone): $t"' in loop and 'echo "FAILED alone too: $t"' in loop
