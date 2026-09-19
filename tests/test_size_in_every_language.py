"""A brief that caps "lines of code" must mean it in every language.

`_COUNTED_SUFFIXES` held ten entries - HTML, CSS, JavaScript, TypeScript and
Python - and `_COLLECTED_SUFFIXES` was not much wider. A product in Go, Rust,
Java, C#, Ruby, PHP, Kotlin, Swift, Scala, Dart, Elixir or C++ therefore
reported a size of zero, and a workspace holding only Swift or Kotlin came
back "No HTML, CSS or JavaScript files were found to cross-check" - no size,
no evidence block, and a milestone reviewer that cannot block because it was
handed nothing.

That is B1, and root-cause class H: a rule written for the stack that happened
to be in front of it. Counting lines needs no per-language analyser - every
language has files, lines, blanks and comments - so the size half of B1 is
fixed here. The reference graph and entry-point rules are the rest of it.
"""

from __future__ import annotations

import pathlib

import pytest

from app.analysis.integration_checks import (
    _COLLECTED_SUFFIXES,
    _COUNTED_SUFFIXES,
    summarise_integration,
)
from app.tools.sandbox import TOOLCHAINS

#: One minimal program per language a stack selector can choose.
PROGRAMS = {
    "go": ("main.go", "package main\nfunc main() {}\n"),
    "rust": ("main.rs", "fn main() {}\n"),
    "java": ("App.java", "class App {}\n"),
    "kotlin": ("Main.kt", "fun main() {}\n"),
    "csharp": ("Program.cs", "class P {}\n"),
    "ruby": ("app.rb", "def f; 1; end\n"),
    "php": ("index.php", "<?php\nfunction f(){return 1;}\n"),
    "swift": ("main.swift", "func f() -> Int { 1 }\n"),
    "dart": ("main.dart", "void main() {}\n"),
    "elixir": ("m.ex", "defmodule M do\nend\n"),
    "scala": ("M.scala", "object M { def f = 1 }\n"),
    "python": ("app.py", "def f():\n    return 1\n"),
    "javascript": ("app.js", "function f() { return 1; }\n"),
    "typescript": ("app.ts", "export function f(): number { return 1; }\n"),
    "c": ("main.c", "int main() { return 0; }\n"),
    "cpp": ("main.cpp", "int main() { return 0; }\n"),
}


def _workspace(tmp_path: pathlib.Path, name: str, body: str) -> pathlib.Path:
    (tmp_path / "p").mkdir()
    (tmp_path / ".project-directory").write_text("p", encoding="utf-8")
    (tmp_path / "p" / name).write_text(body, encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("language", sorted(PROGRAMS))
def test_every_language_reports_a_size(tmp_path, language):
    name, body = PROGRAMS[language]
    root = _workspace(tmp_path, name, body)

    report = summarise_integration(root)

    assert "application:" in report, (
        f"a {language} product reports no size, so a line budget cannot be enforced"
    )
    assert "No HTML, CSS or JavaScript files" not in report


#: JavaScript and TypeScript are the two languages with an orphan rule: a
#: module no page loads and nothing imports is a left-over probe, not the
#: product, and is deliberately excluded from the total. So their fixtures
#: need the page that loads them, which is what a real product has anyway.
NEEDS_A_PAGE = {"javascript", "typescript"}


@pytest.mark.parametrize("language", sorted(PROGRAMS))
def test_the_file_is_actually_counted_not_just_listed(tmp_path, language):
    name, body = PROGRAMS[language]
    root = _workspace(tmp_path, name, body)
    if language in NEEDS_A_PAGE:
        (root / "p" / "index.html").write_text(
            f'<div id="a"></div><script src="{name}"></script>', encoding="utf-8"
        )

    report = summarise_integration(root)
    line = next(l for l in report.splitlines() if "application:" in l)

    assert "0 lines" not in line, f"{language}: {line.strip()}"


def test_every_toolchain_the_stack_can_choose_is_counted():
    """The set rule, against the languages a run can actually select."""
    # One representative suffix per toolchain key.
    suffix_for = {
        "javascript": ".js", "typescript": ".ts", "python": ".py", "go": ".go",
        "rust": ".rs", "java": ".java", "kotlin": ".kt", "csharp": ".cs",
        "ruby": ".rb", "php": ".php", "swift": ".swift", "dart": ".dart",
        "elixir": ".ex", "scala": ".scala", "c": ".c", "cpp": ".cpp",
    }
    missing = sorted(
        key for key in TOOLCHAINS
        if suffix_for.get(key) and suffix_for[key] not in _COUNTED_SUFFIXES
    )
    assert not missing, f"these languages report no size: {missing}"


def test_nothing_is_counted_that_is_not_collected():
    """A suffix counted but never collected can never appear in a count."""
    orphans = sorted(_COUNTED_SUFFIXES - _COLLECTED_SUFFIXES)
    assert not orphans, (
        f"counted but never collected, so the count silently omits them: {orphans}"
    )
