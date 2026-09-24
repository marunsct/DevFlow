"""Three harness files were being committed into the product's git history.

The workspace root carries the harness's own bookkeeping beside the work:
`.project-directory` pins which folder the project lives in, `.project-stack`
records the toolchain the run chose, and `.project-memory.json` holds which
stage last wrote each file.

`git ls-files` on run-07cd52ae's workspace listed all three, so every sprint
commit carried them and a delivered repository would hand whoever receives it
three files that mean nothing to them.

Nothing reads them through git - they are read from disk - so ignoring them
costs nothing. `repository.HARNESS_FILES` already hides the same three from
every listing, every digest and every cross-file check; the generated
`.gitignore` is the fourth place they should never appear, and the test below
ties the two lists together so a fourth file added to one reaches the other.
"""

from __future__ import annotations

import pytest

from app.tools.repository import HARNESS_FILES
from app.tools.version_control import _IGNORED


@pytest.mark.parametrize("name", sorted(HARNESS_FILES))
def test_every_harness_file_is_ignored_by_the_sprint_history(name: str):
    assert name in _IGNORED, (
        f"{name} is hidden from every check and still committed to the product"
    )


def test_the_product_is_not_ignored_with_it():
    """The list must not grow into anything the run actually delivers."""
    for kept in ("app.js", "index.html", "package.json", "styles.css", "app.test.mjs"):
        assert kept not in _IGNORED


def test_the_dependency_directories_are_still_ignored():
    """The reason this file existed before the harness files joined it."""
    for ignored in ("node_modules/", ".agent-home/", "__pycache__/", ".venv/"):
        assert ignored in _IGNORED


def test_it_is_written_when_a_workspace_is_initialised(tmp_path):
    """A list nothing writes out is a list that ignores nothing."""
    import inspect

    from app.tools import version_control

    source = inspect.getsource(version_control)
    assert '.gitignore").write_text(_IGNORED' in source
