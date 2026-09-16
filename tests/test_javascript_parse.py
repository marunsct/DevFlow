"""JavaScript parsed by the parser that will load it.

`syntax_balance` counts brackets for the C family and says so: a structure
check, not a parse, unable to see a misplaced keyword. That is why a Python
file is refused and a JavaScript file was only warned about.

There is proof available and it costs nothing. `node --check` parses a file and
reports its syntax errors without executing a line, and Node is on every role's
allowlist because the products this harness builds are mostly JavaScript. Five
checks took 83 milliseconds in the worker container.

run-454adf22 is what it is for: `app.js` written with a stray `try`, and the
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
    """The edit that did this on run-e37a2bd8 removed an opening line and left
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
