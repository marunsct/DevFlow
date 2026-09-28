"""ES modules a page loads without `type="module"`.

The browser parses the file as a classic script, hits `export` or `import` on
the first line, and throws `Uncaught SyntaxError: Unexpected token 'export'`.
Nothing on the page works - and nothing in the test suite notices, because
`node --test` imports the module directly and never loads the HTML.

One run's milestone reviewer read both files and called it blocking:
`index.html` line 33 was `<script src="app.js">` and `app.js` opens with
`export { addTask, ... }`. It was right, the specialist fixed it, and it is
decidable from those two files - so it should not have needed a model.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.integration_checks import (
    _modules_loaded_as_plain_scripts,
    _severity_of,
    _source_files,
)

MODULE = "export function addTask(t) {}\nexport function loadTasks() { return []; }\n"
CLASSIC = "function addTask(t) {}\nwindow.addTask = addTask;\n"


def _check(tmp_path: Path, html: str, script: str = MODULE, name: str = "app.js") -> list[str]:
    project = tmp_path / "app"
    project.mkdir()
    (project / "index.html").write_text(html, encoding="utf-8")
    (project / name).write_text(script, encoding="utf-8")
    return _modules_loaded_as_plain_scripts(_source_files(tmp_path), tmp_path)


def test_the_run_01f03ed9_shape_is_reported(tmp_path: Path) -> None:
    (problem,) = _check(tmp_path, '<html><body><script src="app.js"></script></body></html>')

    assert "plain <script> tag" in problem
    assert 'type="module"' in problem
    assert "test suite cannot catch this" in problem


def test_it_counts_as_breaking_the_product(tmp_path: Path) -> None:
    (problem,) = _check(tmp_path, '<html><script src="app.js"></script></html>')

    assert _severity_of(problem) == "BREAKS"


def test_a_module_tag_is_correct(tmp_path: Path) -> None:
    assert _check(tmp_path, '<html><script type="module" src="app.js"></script></html>') == []


def test_a_classic_script_is_correct(tmp_path: Path) -> None:
    assert _check(tmp_path, '<html><script src="app.js"></script></html>', CLASSIC) == []


@pytest.mark.parametrize(
    "tag",
    [
        "<script type='module' src='app.js'></script>",
        '<SCRIPT TYPE="MODULE" SRC="app.js"></SCRIPT>',
        '<script defer type="module" src="app.js"></script>',
    ],
)
def test_the_tag_is_read_however_it_is_written(tmp_path: Path, tag: str) -> None:
    assert _check(tmp_path, f"<html>{tag}</html>") == []


def test_an_inline_script_has_no_src_to_judge(tmp_path: Path) -> None:
    assert _check(tmp_path, "<html><script>const a = 1;</script></html>") == []


def test_a_src_that_points_at_nothing_is_reported_elsewhere(tmp_path: Path) -> None:
    """`_broken_local_references` owns that; this must not double up."""
    project = tmp_path / "app"
    project.mkdir()
    (project / "index.html").write_text(
        '<html><script src="missing.js"></script></html>', encoding="utf-8"
    )

    assert _modules_loaded_as_plain_scripts(_source_files(tmp_path), tmp_path) == []
