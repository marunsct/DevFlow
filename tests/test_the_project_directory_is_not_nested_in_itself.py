"""Nothing is written into the project directory nested inside itself.

Measured on one run: a test read `simple-to-do-list-app/simple-to-do-list-app/
index.html` - a workspace-relative path used from inside the project - and
failed with ENOENT. The fix stage wrote a second copy of the page at that path
and a test asserting the copy exists.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.repository import PROJECT_MARKER, RepositoryToolError, write_approved_artifact

PAGE = "<!DOCTYPE html>\n<html><body><main id=\"app\"></main></body></html>\n"


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "the-app").mkdir()
    (tmp_path / PROJECT_MARKER).write_text("the-app\n", encoding="utf-8")
    return tmp_path


def test_the_doubled_path_is_refused_and_the_real_one_named(workspace) -> None:
    with pytest.raises(RepositoryToolError) as caught:
        write_approved_artifact(workspace, "the-app/the-app/index.html", PAGE)

    message = str(caught.value)
    assert "inside itself" in message
    assert "The file is 'the-app/index.html'" in message
    assert not (workspace / "the-app" / "the-app").exists()


def test_the_real_path_is_written(workspace) -> None:
    write_approved_artifact(workspace, "the-app/index.html", PAGE)

    assert (workspace / "the-app" / "index.html").read_text(encoding="utf-8") == PAGE


def test_a_subdirectory_with_another_name_is_fine(workspace) -> None:
    write_approved_artifact(workspace, "the-app/src/the-app.css", "body { margin: 0; }\n")

    assert (workspace / "the-app" / "src" / "the-app.css").exists()
