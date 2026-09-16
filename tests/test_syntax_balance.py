"""A structurally broken file, caught where it was written.

run-e37a2bd8 lost a sprint to one edit. `confirmDeletePrompt` had its
`return new Promise((resolve) => {` removed and its closing `});` left behind.
The write was accepted; the break surfaced two stages later as "Syntax error in
app.mjs at line 206", and three remediation attempts edited around line 206 -
which is where the parser gave up, not where the mistake was. The sprint
exhausted its attempts and the run failed with the real fault untouched.

Everything needed to catch it existed at the moment of the write.
"""

from __future__ import annotations

import pytest

from app.analysis.syntax_balance import structural_problem

THE_BREAK = """export function confirmDeletePrompt(id, simulate = false) {
  if (simulate) return Promise.resolve(true);

    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
  });
}
"""


def test_the_edit_that_cost_a_sprint_is_caught() -> None:
    problem = structural_problem("app.mjs", THE_BREAK)

    assert problem and "never opened" in problem


def test_it_says_the_reported_line_is_not_the_wrong_line() -> None:
    """The whole failure was three attempts spent on a healthy line."""
    problem = structural_problem("app.mjs", THE_BREAK)

    assert "where it gave up" in problem


@pytest.mark.parametrize(
    "source",
    [
        # A regular expression holding unmatched brackets. `/[)}]/` is valid,
        # and a naive count reads it as a stray closer.
        "const re = /[)}\\]]/g;\nexport function f() { return re; }\n",
        # Brackets inside strings and template literals.
        'const s = "a ) b } c";\nconst t = `x ${a.b} y`;\nfunction f() { return 1; }\n',
        # Brackets inside comments.
        "// closes ) here\n/* and } here */\nfunction f() { return 1; }\n",
        # Arrow returning an object literal, and nested calls.
        "export const f = (a) => ({ v: a.map(x => [x, {y: 1}]) });\n",
        # JSX.
        "export const C = () => (<div className={'a'}>{items.map(i => <li/>)}</div>);\n",
    ],
)
def test_healthy_code_is_left_alone(source: str) -> None:
    """A false accusation here is worse than a missed break: it would stop a
    specialist saving correct work."""
    assert structural_problem("a.jsx", source) is None


def test_python_is_parsed_rather_than_counted() -> None:
    """`ast` is the real grammar, so a failure there is certain."""
    assert structural_problem("a.py", "def f(x):\n    return {'a': [1, 2]}\n") is None

    problem = structural_problem("a.py", "def f(x):\n  return (1\n")
    assert problem and "cannot parse" in problem


def test_indentation_errors_are_caught_in_python_where_braces_would_miss_them() -> None:
    problem = structural_problem("a.py", "def f():\nreturn 1\n")

    assert problem is not None


def test_files_with_no_grammar_here_are_not_judged() -> None:
    for name in ("notes.md", "styles.css", "data.json", "page.html"):
        assert structural_problem(name, "see ) here { and } there") is None


def test_an_empty_file_is_not_a_problem() -> None:
    assert structural_problem("a.js", "") is None
    assert structural_problem("a.js", "   \n\n") is None


def test_the_write_tools_use_it() -> None:
    import inspect

    from app.tools import repository

    source = inspect.getsource(repository)
    assert "_structural_note(relative_path, content)" in source
    assert source.count("_structural_note(") >= 3  # helper, write, edit
