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

from app.tools.repository import HARNESS_DIRECTORIES, HARNESS_FILES
from app.tools.sandbox import _RUNNER_OUTPUT_DIRECTORIES
from app.tools.version_control import _IGNORED


@pytest.mark.parametrize("name", sorted(HARNESS_FILES))
def test_every_harness_file_is_ignored_by_the_sprint_history(name: str):
    assert name in _IGNORED, (
        f"{name} is hidden from every check and still committed to the product"
    )


@pytest.mark.parametrize("directory", sorted(_RUNNER_OUTPUT_DIRECTORIES))
def test_every_runner_output_directory_is_ignored_too(directory: str):
    """A test runner's output is not the work either.

    Measured on run-fbe23618's first sprint:
    `todo-app/test-results/.last-run.json` was committed alongside the
    product, and a reviewer reading that diff has to work out for itself that
    it is not part of the work.

    `repository._iter_repo_files` already prunes this exact list from every
    listing and digest, so git was again the one place nobody had looked.
    """
    assert f"{directory}/" in _IGNORED, (
        f"{directory} is pruned from every listing and still committed"
    )


@pytest.mark.parametrize("directory", sorted(HARNESS_DIRECTORIES))
def test_every_harness_directory_is_ignored_too(directory: str):
    """`docs/stage_summaries/` is written for the dashboard, not for delivery.

    One file per gated stage, so a run leaves dozens - every specialist task,
    test round and defect fix. They were reaching the agents twice over: the
    digest prepended to every model call listed them, sorted ahead of the
    project because `docs/` sorts first, against a forty-file cap; and git
    committed them into the sprint history a reviewer reads as the work.
    """
    assert f"{directory}/" in _IGNORED, (
        f"{directory} holds the harness's own records and is still committed"
    )


def test_a_harness_directory_is_pruned_from_every_listing(tmp_path):
    """Hidden from the agents, not only from git.

    The digest is the expensive one: it is rebuilt and prepended on every model
    call, so bookkeeping there is paid for once per call for the rest of the run.
    """
    from app.agents.workspace_digest import render_workspace_digest
    from app.tools.repository import list_repository_files

    (tmp_path / "docs" / "stage_summaries").mkdir(parents=True)
    (tmp_path / "docs" / "stage_summaries" / "product_manager.md").write_text("# s\n")
    (tmp_path / "docs" / "technical_specification.md").write_text("# spec\n")
    (tmp_path / "app.js").write_text("console.log(1)\n")

    listed = list_repository_files(str(tmp_path))
    digest = render_workspace_digest(str(tmp_path))

    assert not [name for name in listed if "stage_summaries" in name]
    assert "stage_summaries" not in digest
    assert any("app.js" in name for name in listed), "the product is still listed"
    assert any("technical_specification" in name for name in listed), (
        "the workflow's own documents are not bookkeeping - agents read them"
    )


def test_the_product_is_not_ignored_with_it():
    """The list must not grow into anything the run actually delivers."""
    for kept in ("app.js", "index.html", "package.json", "styles.css", "app.test.mjs",
                 "tests/", "e2e/", "src/", "spec/"):
        assert kept not in _IGNORED, f"{kept} is part of what the run delivers"


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
