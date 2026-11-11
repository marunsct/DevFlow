"""Product words in the harness's string literals do not spread: no file gains one, and no new file has any.

Per-role audit 3.5 item 4. Measured: 178 of 261 system-prompt variants (68%) held a banned word, and the existing
banned-words tests check only the strings each new rule names. The literals are counted per file (docstrings left out)
against `fixtures/product_words_in_source.json`, the count when this test was written. Cleaning a file lowers its
ceiling: lower the number there in the same commit, never raise it.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
ROOT = Path(__file__).resolve().parents[1]
CEILINGS = ROOT / "tests" / "fixtures" / "product_words_in_source.json"


def _hits(text: str) -> int:
    tree = ast.parse(text)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                docstrings.add(id(first.value))
    return sum(len(BANNED.findall(node.value)) for node in ast.walk(tree)
               if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings)


def test_no_file_gains_a_product_word():
    ceilings = json.loads(CEILINGS.read_text(encoding="utf-8"))
    grown = {}
    for path in sorted((ROOT / "src" / "app").rglob("*.py")):
        name = path.relative_to(ROOT).as_posix()
        found = _hits(path.read_text(encoding="utf-8"))
        if found > ceilings.get(name, 0):
            grown[name] = (ceilings.get(name, 0), found)
    assert not grown, f"product words added to string literals (ceiling, now): {grown}"


def test_the_count_sees_a_literal_and_leaves_a_docstring_out():
    assert _hits('"""A todo list."""\nRULE = "Name each task."\n') == 1
