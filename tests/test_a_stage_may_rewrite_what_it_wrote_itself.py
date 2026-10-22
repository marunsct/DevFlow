"""A stage was refused a rewrite of its own code as though another task owned it.

`_a_rewrite_that_drops_what_the_file_defines` names a definition a whole-file
write would remove and refuses the second such write, because in parallel mode
the definition may be another task's, written minutes ago. Measured over every
stored run: eight refusals, four of them on a file no other stage had ever
written. In one, a backend specialist created `app.js`, added a `wrapper` to
its own edit-mode function, and was refused the rewrite that took it out
again. It spent its last calls on line-number edits, ran out of its call
budget and was started again from nothing.

A name is the stage visit's own when the visit created the file, or added the
name in a change to a file it had also changed last. Everything else stays
protected exactly as before.
"""

from __future__ import annotations

import pytest

from app.agents import stage_memory
from app.tools import repository
from app.tools.repository import (
    RepositoryToolError,
    edit_approved_artifact,
    write_approved_artifact,
)

PATH = "todo-app/app.js"

WITH_A_HELPER = """export function loadItems() { return []; }
export function saveItems(items) { return items; }
export function init() {
  const wrapper = document.createElement('span');
  return wrapper;
}
"""

WITHOUT_IT = """export function loadItems() { return []; }
export function saveItems(items) { return items; }
export function init() {
  return document.createElement('span');
}
"""


@pytest.fixture(autouse=True)
def a_clean_tally():
    stage_memory.forget_everything()
    repository._LOSSES_OUTSIDE_A_RUN.clear()
    repository._LAST_CHANGE.clear()
    yield
    stage_memory.forget_everything()
    repository._LOSSES_OUTSIDE_A_RUN.clear()
    repository._LAST_CHANGE.clear()


@pytest.fixture
def root(tmp_path):
    (tmp_path / "todo-app").mkdir()
    return tmp_path


def _as(visit: str, call, *args):
    with stage_memory.remembering(visit):
        return call(*args)


def _drop_it_twice(root, visit: str):
    """The second rewrite is the one the guard refuses when it protects the name."""
    first = _as(visit, write_approved_artifact, str(root), PATH, WITHOUT_IT)
    _as(visit, write_approved_artifact, str(root), PATH, WITH_A_HELPER)
    return first, _as(visit, write_approved_artifact, str(root), PATH, WITHOUT_IT)


class TestItsOwnCode:
    def test_a_file_it_created_can_lose_a_name_twice(self, root):
        _as("visit-a", write_approved_artifact, str(root), PATH, WITH_A_HELPER)

        _, second = _drop_it_twice(root, "visit-a")

        assert second["status"] == "written"
        assert "wrapper" not in (root / PATH).read_text()

    def test_nothing_says_another_task_may_own_it(self, root):
        _as("visit-a", write_approved_artifact, str(root), PATH, WITH_A_HELPER)

        first, second = _drop_it_twice(root, "visit-a")

        for result in (first, second):
            assert "another task may own" not in (result.get("note") or "")

    def test_a_name_it_added_by_an_edit_is_its_own(self, root):
        """The run's case: the name came in by an edit, not the creating write."""
        _as("visit-a", write_approved_artifact, str(root), PATH, WITHOUT_IT)
        _as(
            "visit-a", edit_approved_artifact, str(root), PATH,
            "  return document.createElement('span');",
            "  const wrapper = document.createElement('span');\n  return wrapper;",
        )

        _, second = _drop_it_twice(root, "visit-a")

        assert second["status"] == "written"

    def test_a_fragment_of_its_own_file_is_still_refused(self, root):
        """Sent as the whole file by mistake, it loses the stage's own work too."""
        many = "".join(f"export function step{i}() {{ return {i}; }}\n" for i in range(12))
        _as("visit-a", write_approved_artifact, str(root), PATH, many)

        with pytest.raises(RepositoryToolError):
            _as("visit-a", write_approved_artifact, str(root), PATH, "export function step0() { return 0; }\n")


class TestSomeoneElsesCodeIsStillProtected:
    def test_a_file_another_visit_wrote(self, root):
        _as("visit-b", write_approved_artifact, str(root), PATH, WITH_A_HELPER)

        with pytest.raises(RepositoryToolError) as raised:
            _drop_it_twice(root, "visit-a")

        assert "`wrapper`" in str(raised.value)

    def test_a_file_written_before_any_stage(self, root):
        """A project's setup, or anything outside a run, is nobody's to drop."""
        write_approved_artifact(str(root), PATH, WITH_A_HELPER)

        with pytest.raises(RepositoryToolError):
            _drop_it_twice(root, "visit-a")

    def test_a_restart_of_the_same_stage_is_another_visit(self, root):
        """A later sprint reuses stage names; its code is not the earlier one's."""
        _as("visit-a", write_approved_artifact, str(root), PATH, WITH_A_HELPER)

        with pytest.raises(RepositoryToolError):
            _drop_it_twice(root, "visit-a-again")

    def test_a_name_another_visit_added_in_between(self, root):
        """Its own edit after theirs must not make their name its own."""
        _as("visit-a", write_approved_artifact, str(root), PATH, WITHOUT_IT)
        _as(
            "visit-b", edit_approved_artifact, str(root), PATH,
            "  return document.createElement('span');",
            "  const wrapper = document.createElement('span');\n  return wrapper;",
        )
        _as(
            "visit-a", edit_approved_artifact, str(root), PATH,
            "export function init() {", "export function init() {\n  const ready = true;",
        )

        result = _as(
            "visit-a", write_approved_artifact, str(root), PATH,
            WITHOUT_IT.replace("export function init() {", "export function init() {\n  const ready = true;"),
        )

        assert "`wrapper`" in (result.get("note") or "")

    def test_only_the_other_tasks_names_are_listed(self, root):
        _as("visit-b", write_approved_artifact, str(root), PATH, WITHOUT_IT)
        _as(
            "visit-a", edit_approved_artifact, str(root), PATH,
            "export function init() {",
            "export function mine() { return 1; }\nexport function init() {",
        )
        _as(
            "visit-a", edit_approved_artifact, str(root), PATH,
            "export function mine() { return 1; }",
            "export function mine() { return 1; }\nexport function also() { return 2; }",
        )

        result = _as(
            "visit-a", write_approved_artifact, str(root), PATH,
            "export function loadItems() { return []; }\nexport function init() { return 0; }\n",
        )

        note = result.get("note") or ""
        assert "`saveItems`" in note
        assert "`also`" not in note
