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


def test_the_forgiving_match_path_also_gets_the_note(tmp_path) -> None:
    """Two success returns, and the checks were on one of them.

    `edit_approved_artifact` succeeds in two places: the exact match, and the
    forgiving match that tolerates line numbers, JSON escaping or a different
    indent. The notes were attached to the exact path only.

    That cost run-3ddd443f. At 12:52:03 `test_round_0` removed a passage
    through the forgiving path and got no structural note; the edit left a
    brace unclosed, and `node --test` failed four times with "Unexpected end of
    input" before the next edit - through the exact path - finally reported it.
    """
    from app.tools.repository import edit_approved_artifact, write_approved_artifact

    write_approved_artifact(tmp_path, "p/app.js", "export function init() {\n  const f = 1;\n}\n")

    # An indent that does not match the file forces the forgiving path.
    result = edit_approved_artifact(tmp_path, "p/app.js", "    const f = 1;\n", "  if (x) {\n")

    assert "note" in result, "the forgiving path must carry the checks too"
    assert "do not balance" in result["note"]
    # And it must still explain why the match was forgiven.
    assert "detail" in result


def test_both_edit_paths_build_their_result_in_one_place() -> None:
    """A third success path must not be able to reopen this."""
    import inspect

    from app.tools import repository

    source = inspect.getsource(repository.edit_approved_artifact)

    assert source.count("_edited(") == 2
    assert '"status": "edited"' not in source, "the result shape belongs in _edited"


# --- imports that parse cleanly and fail at runtime -----------------------


def test_the_import_that_cost_a_sprint_is_caught() -> None:
    """run-82e1dbdb wrote this more than ten times.

    `import { assert } from 'node:test'` parses, looks right, and fails only
    when the test runs - so the sprint spent all three remediation attempts on
    it and ended with the defects still open. Nine of that run's twenty-six
    tool failures were this shape.
    """
    problem = structural_problem("app.test.mjs", "import { test, assert } from 'node:test';\n")

    assert problem and "does not export `assert`" in problem
    # It must list what the module does export, or the next guess is another guess.
    assert "describe" in problem and "it" in problem


def test_assert_is_named_as_a_default_export() -> None:
    """The specific confusion: `assert` exists, just not as a named import."""
    problem = structural_problem("a.mjs", "import { assert } from 'node:assert';\n")

    assert problem and "default* export" in problem
    assert "import assert from 'node:assert'" in problem


@pytest.mark.parametrize(
    "source",
    [
        "import assert from 'node:assert';\nimport { test } from 'node:test';\n",
        "import { strictEqual, ok, deepStrictEqual } from 'node:assert';\n",
        "import { strict as assert } from 'node:assert';\n",
        "import { describe, it, before, afterEach } from 'node:test';\n",
    ],
)
def test_correct_imports_are_silent(source: str) -> None:
    assert structural_problem("a.mjs", source) is None


def test_a_package_whose_exports_are_unknown_is_left_alone() -> None:
    """Guessing at a package's exports would produce false accusations, and on
    a write a false accusation costs more than a missed one."""
    assert structural_problem("a.mjs", "import { somethingOdd } from 'lodash';\n") is None
    assert structural_problem("a.mjs", "import { render } from './ui.js';\n") is None


def test_commonjs_in_an_mjs_file_is_caught() -> None:
    """Three of run-82e1dbdb's failures were "require is not defined in ES
    module scope"."""
    problem = structural_problem("a.mjs", "const x = require('./a.js');\n")

    assert problem and "require is not defined" in problem
    assert "import x from" in problem


def test_module_exports_in_an_mjs_file_is_caught() -> None:
    problem = structural_problem("a.mjs", "module.exports = { a: 1 };\n")

    assert problem and "module is not defined" in problem


def test_commonjs_in_a_cjs_file_is_correct() -> None:
    """The extension is what decides, and .cjs means CommonJS."""
    assert structural_problem("a.cjs", "const x = require('./a.js');\n") is None
    assert structural_problem("a.cjs", "module.exports = {};\n") is None


def test_a_word_ending_in_require_is_not_a_require_call() -> None:
    assert structural_problem("a.mjs", "const preRequire = 1;\nobj.require(x);\n") is None
