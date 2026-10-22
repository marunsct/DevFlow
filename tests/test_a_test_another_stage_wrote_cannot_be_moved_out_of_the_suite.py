"""In a run, a test this stage did not write cannot be moved to a name no runner collects.

The delete of such a test is refused; the refusal used to offer a rename and
then a delete as the way out. Measured on a gate run: a fixer was refused
deleting a unit-test file drafting had written, moved it to
`test___init__.py.bak`, and the suite it was fixing lost the test.
"""
from __future__ import annotations

import re
from unittest import mock

import pytest

from app.tools import repository
from app.tools.repository import RepositoryToolError, delete_approved_artifact, move_approved_artifact

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _project(tmp_path):
    (tmp_path / "items-api" / "tests").mkdir(parents=True)
    (tmp_path / "items-api" / "tests" / "test_init.py").write_text("def test_imports():\n    import items_api\n")
    return tmp_path


def _in_a_stage(created_by=""):
    return mock.patch.multiple(repository, _a_stage_is_running=lambda: True,
                               _this_stage_created=lambda root, shown: created_by == "this")


def test_in_a_run_the_move_is_refused_and_the_delete_offers_no_way_round(tmp_path):
    root = _project(tmp_path)
    with _in_a_stage():
        with pytest.raises(RepositoryToolError) as moved:
            move_approved_artifact(root, "items-api/tests/test_init.py", "items-api/tests/test_init.py.bak")
        with pytest.raises(RepositoryToolError) as deleted:
            delete_approved_artifact(root, "items-api/tests/test_init.py")

    assert "no runner collects it" in str(moved.value)
    assert "move_artifact" not in str(deleted.value)
    assert (root / "items-api" / "tests" / "test_init.py").exists()
    assert not BANNED.search(repository.TEST_MOVED_OUT_OF_THE_SUITE + str(deleted.value))


def test_a_stage_may_move_its_own_test_and_a_test_may_be_renamed_as_a_test(tmp_path):
    root = _project(tmp_path)
    with _in_a_stage():
        move_approved_artifact(root, "items-api/tests/test_init.py", "items-api/tests/test_package.py")
    with _in_a_stage(created_by="this"):
        move_approved_artifact(root, "items-api/tests/test_package.py", "items-api/tests/test_package.py.bak")
    assert (root / "items-api" / "tests" / "test_package.py.bak").exists()
