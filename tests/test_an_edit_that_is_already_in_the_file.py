"""An edit whose text is already in the file has succeeded, not failed.

Measured across 85 stored runs: the "could not find that text / already been
applied" answer fired 247 times in 46 of them - 2.9 per run, the largest single
failure class in the corpus. Two costs followed from answering it as an error.

The message opened with the failure and explained the success underneath, and
41 of the 247 stages re-sent the byte-identical edit as their very next call,
which cannot do anything but produce the same answer again.

It also ended "Read the file if you want to confirm it", and 65 stages did.
Eighteen of those reads came back refused by the repeated-read guard - the
harness inviting a read and then denying it - and the invitation was worthless
either way, because this branch only runs once `replace` has been located in
the file. The confirmation had already been made on the model's behalf.

So the answer is a success: the `find` is gone, the `replace` is present, and
the file reads the way the call asked for it to read. What it must not do is
claim the write, because nothing was written.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.repository import (
    RepositoryToolError,
    edit_approved_artifact,
    read_text_file,
)

BEFORE = """function saveTasks() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(tasks));
}
"""

FIND = (
    "function saveTasks() {\n"
    "  localStorage.setItem(STORAGE_KEY, JSON.stringify(tasks));\n"
    "}"
)
REPLACE = (
    "function saveTasks() {\n"
    "  const storage = global.localStorage || localStorage;\n"
    "  storage.setItem(STORAGE_KEY, JSON.stringify(tasks));\n"
    "}"
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "app.js").write_text(BEFORE, encoding="utf-8")
    return tmp_path


def _edit(root: Path, find: str = FIND, replace: str = REPLACE) -> dict:
    return edit_approved_artifact(root, "app.js", find, replace)


class TestItSucceeds:
    def test_the_second_send_is_not_an_error(self, project: Path) -> None:
        assert _edit(project)["status"] == "edited"

        assert _edit(project)["status"] == "already_applied"

    def test_it_does_not_raise(self, project: Path) -> None:
        _edit(project)
        try:
            _edit(project)
        except RepositoryToolError as exc:  # pragma: no cover - the regression
            pytest.fail(f"an edit already in the file raised: {exc}")

    def test_a_third_and_fourth_send_answer_the_same_way(self, project: Path) -> None:
        """run-0deeb8bf sent it four times; none of them should be a failure."""
        _edit(project)

        for _ in range(3):
            assert _edit(project)["status"] == "already_applied"


class TestItDoesNotClaimTheWrite:
    def test_the_status_is_not_edited(self, project: Path) -> None:
        _edit(project)

        assert _edit(project)["status"] != "edited"

    def test_the_file_is_not_changed_again(self, project: Path) -> None:
        _edit(project)
        before = (project / "app.js").read_text(encoding="utf-8")

        _edit(project)

        assert (project / "app.js").read_text(encoding="utf-8") == before
        assert before.count(REPLACE) == 1


class TestWhatItSays:
    def test_it_names_the_line_the_text_sits_on(self, project: Path) -> None:
        _edit(project)

        assert "at line 1" in _edit(project)["detail"]

    def test_it_does_not_send_the_model_to_read_the_file(self, project: Path) -> None:
        """The invitation that produced 65 reads, 18 of them refused."""
        _edit(project)
        detail = _edit(project)["detail"]

        assert "Read the file" not in detail
        assert "nothing to confirm" in detail

    def test_it_does_not_open_by_calling_this_a_failure(self, project: Path) -> None:
        _edit(project)
        detail = _edit(project)["detail"]

        assert "Could not find" not in detail
        assert detail.startswith("This edit is already in")

    def test_it_says_how_to_make_a_further_change_to_that_passage(
        self, project: Path
    ) -> None:
        """Without this, a stage that meant a second edit there just moves on."""
        _edit(project)

        assert "send the text that is there now as `find`" in _edit(project)["detail"]

    def test_it_reports_the_length(self, project: Path) -> None:
        """A stage editing towards a size limit needs this without a `wc -l`."""
        _edit(project)

        assert _edit(project)["lines"] == 4


class TestWhatStillFails:
    """The guards that keep this from swallowing a real miss."""

    def test_a_deletion_is_still_an_error(self, project: Path) -> None:
        """An empty `replace` is present in every file and proves nothing."""
        with pytest.raises(RepositoryToolError):
            _edit(project, "function nosuchthing() {}", "")

    def test_a_short_replacement_is_still_an_error(self, project: Path) -> None:
        """`}` says nothing about what was done."""
        with pytest.raises(RepositoryToolError):
            _edit(project, "function nosuchthing() {}", "}")

    def test_a_genuine_miss_is_still_an_error(self, project: Path) -> None:
        with pytest.raises(RepositoryToolError):
            _edit(
                project,
                "function neverWasHere() {\n  return 1;\n}",
                "function neverWasHere() {\n  return 2; // a long enough body\n}",
            )

    def test_a_first_edit_still_reports_edited(self, project: Path) -> None:
        read_text_file(project, "app.js")

        assert _edit(project)["status"] == "edited"
