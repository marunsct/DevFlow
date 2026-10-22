"""JavaScript parsed by the parser that will load it.

`syntax_balance` counts brackets for the C family and says so: a structure
check, not a parse, unable to see a misplaced keyword. That is why a Python
file is refused and a JavaScript file was only warned about.

There is proof available and it costs nothing. `node --check` parses a file and
reports its syntax errors without executing a line, and Node is on every role's
allowlist because the products this harness builds are mostly JavaScript. Five
checks took 83 milliseconds in the worker container.

One run is what it is for: `app.js` written with a stray `try`, and the
whole of `test_round_0` spent discovering `SyntaxError: Unexpected token 'try'`
at line 83, then a triage and a defect-fix stage routing it back.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.analysis.javascript_parse import parse_error
from app.tools.repository import (
    RepositoryToolError,
    edit_approved_artifact,
    write_approved_artifact,
)

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

GOOD = "export function loadTasks() {\n  try { return []; } catch (e) { return []; }\n}\n"
BROKEN = GOOD + "  } catch (e) {\n    tasks = [];\n  }\n"


@needs_node
def test_a_file_that_parses_says_nothing(tmp_path: Path) -> None:
    assert parse_error(tmp_path / "a.mjs", GOOD) is None


@needs_node
def test_a_syntax_error_is_named_with_its_line(tmp_path: Path) -> None:
    problem = parse_error(tmp_path / "a.mjs", BROKEN)

    assert problem is not None
    assert "line 4" in problem
    assert "SyntaxError" in problem


@needs_node
@pytest.mark.parametrize("name", ["a.jsx", "a.ts", "a.tsx", "a.py", "a.css"])
def test_what_node_does_not_parse_is_left_alone(tmp_path: Path, name: str) -> None:
    """Running this on TypeScript would report an error in a correct file."""
    assert parse_error(tmp_path / name, "const a: number = 1;\n") is None


@needs_node
def test_the_probe_file_never_survives(tmp_path: Path) -> None:
    parse_error(tmp_path / "a.mjs", BROKEN)
    parse_error(tmp_path / "a.mjs", GOOD)

    assert list(tmp_path.iterdir()) == []


@needs_node
def test_a_broken_write_is_refused_and_nothing_lands(tmp_path: Path) -> None:
    write_approved_artifact(tmp_path, "proj/package.json", '{"name": "p", "type": "module"}')
    write_approved_artifact(tmp_path, "proj/app.js", GOOD)

    with pytest.raises(RepositoryToolError) as caught:
        write_approved_artifact(tmp_path, "proj/app.js", BROKEN)

    assert "Node cannot parse" in str(caught.value)
    assert (tmp_path / "proj" / "app.js").read_text() == GOOD


@needs_node
def test_an_edit_that_breaks_the_file_is_refused(tmp_path: Path) -> None:
    """The edit that did this on one run removed an opening line and left
    its closing one, and the write was accepted."""
    write_approved_artifact(tmp_path, "proj/package.json", '{"name": "p", "type": "module"}')
    write_approved_artifact(tmp_path, "proj/app.js", GOOD)

    with pytest.raises(RepositoryToolError):
        edit_approved_artifact(
            tmp_path,
            "proj/app.js",
            "return []; } catch (e) { return []; }",
            "return []; } catch (e) {",
        )

    assert (tmp_path / "proj" / "app.js").read_text() == GOOD


@needs_node
def test_commonjs_in_a_cjs_file_parses(tmp_path: Path) -> None:
    """`.js` is ESM or CommonJS by the nearest package.json, so the check runs
    where the file will live. A probe somewhere else would invent errors."""
    write_approved_artifact(tmp_path, "proj/package.json", '{"name": "p", "type": "module"}')

    assert write_approved_artifact(
        tmp_path, "proj/legacy.cjs", "const a = require('./b');\nmodule.exports = a;\n"
    )["status"]


def test_a_missing_node_is_not_a_failure(tmp_path: Path, monkeypatch) -> None:
    """A write must never fail because a check could not run."""
    import app.analysis.javascript_parse as module

    monkeypatch.setattr(module, "_node", lambda: None)

    assert parse_error(tmp_path / "a.mjs", BROKEN) is None


# --- the fact the parser's own message is missing --------------------------


@needs_node
def test_a_duplicate_identifier_is_shown_both_declarations(tmp_path: Path) -> None:
    """Node names the second one. The agent needs the first.

    One run's `specialist_backend_2` had five consecutive edits refused,
    one of them `Identifier 'newTitle' has already been declared`, and still
    could not place the fault from a line number alone.
    """
    body = (
        "const newTitle = prompt('a');\n"
        "function go() {\n  return 1;\n}\n"
        "const newTitle = prompt('b');\n"
    )

    problem = parse_error(tmp_path / "a.mjs", body)

    assert problem is not None
    assert "declared on lines 1 and 5" in problem


@needs_node
def test_an_unexpected_brace_is_shown_where_the_block_is(tmp_path: Path) -> None:
    """A parser reports where it gave up, not where the mistake is."""
    body = "function a() {\n  if (x) {\n    run();\n  }\n}\n}\n"

    problem = parse_error(tmp_path / "b.mjs", body)

    assert problem is not None
    assert "brackets do not balance" in problem


@needs_node
def test_an_error_with_no_second_half_says_only_what_it_knows(tmp_path: Path) -> None:
    body = "const a = ;\n"

    problem = parse_error(tmp_path / "c.mjs", body)

    assert problem is not None
    assert "declared on lines" not in problem


@needs_node
def test_a_shadowed_name_in_an_inner_scope_is_not_a_duplicate(tmp_path: Path) -> None:
    """`const` inside a block is a new binding, and the file parses."""
    body = (
        "const newTitle = 'a';\n"
        "function go() {\n  const newTitle = 'b';\n  return newTitle;\n}\n"
    )

    assert parse_error(tmp_path / "d.mjs", body) is None


@needs_node
def test_a_name_exported_twice_names_both_exports(tmp_path: Path) -> None:
    """One run's stage was told "Duplicate export of 'FilterState'" at the
    `export { ... }` closing the file, five times, and never shown the
    `export const FilterState` near the top."""
    body = (
        "export const FilterState = { ALL: 'all' };\n"
        "function applyFilter(tasks) {\n  return tasks;\n}\n"
        "export { FilterState, applyFilter };\n"
    )

    problem = parse_error(tmp_path / "app.mjs", body)

    assert problem is not None
    assert "`FilterState` is exported on lines 1 and 5" in problem


@needs_node
def test_a_renamed_export_is_counted_by_its_exported_name(tmp_path: Path) -> None:
    body = (
        "export function run() {}\n"
        "function go() {}\n"
        "export { go as run };\n"
    )

    problem = parse_error(tmp_path / "app.mjs", body)

    assert problem is not None
    assert "`run` is exported on lines 1 and 3" in problem
