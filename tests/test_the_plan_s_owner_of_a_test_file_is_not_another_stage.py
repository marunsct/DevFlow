"""The stage a work order gives a test file to is not refused as "another stage".

Measured on one run. A work order listed `tests/app.test.js`, a file an
earlier stage had created and left as a placeholder. The stage the plan gave it
to asked to delete it, to write it again, and was told twice that it was "a
test that specialist_testing_3 wrote" and would be refused the same way.
"""

from __future__ import annotations

from pathlib import Path

from app.analysis import project_memory
from app.observability import transcript
from app.tools import repository
from app.tools.repository import _another_stage_s_test, record_work_order_files

TEST_FILE = "app/tests/app.test.js"


def _a_test_someone_else_created(root: Path, monkeypatch, running: str) -> None:
    target = root / TEST_FILE
    target.parent.mkdir(parents=True)
    target.write_text("import { test } from 'node:test';\ntest('a', () => {});\n", encoding="utf-8")
    monkeypatch.setattr(project_memory, "who_created", lambda r, shown: "specialist_testing_3")
    monkeypatch.setattr(transcript, "_stage_from_config", lambda default="": running)


def test_another_stage_s_test_is_still_another_stage_s(tmp_path: Path, monkeypatch) -> None:
    _a_test_someone_else_created(tmp_path, monkeypatch, running="specialist_testing_1")

    assert _another_stage_s_test(tmp_path, TEST_FILE) == "specialist_testing_3"


def test_the_stage_the_plan_gave_it_to_owns_it(tmp_path: Path, monkeypatch) -> None:
    _a_test_someone_else_created(tmp_path, monkeypatch, running="specialist_testing_1")
    record_work_order_files(tmp_path, {TEST_FILE: "specialist_testing_1"})

    assert _another_stage_s_test(tmp_path, TEST_FILE) == ""


def test_a_file_the_plan_gave_to_a_third_stage_is_not_this_one_s(tmp_path: Path, monkeypatch) -> None:
    _a_test_someone_else_created(tmp_path, monkeypatch, running="specialist_testing_1")
    record_work_order_files(tmp_path, {TEST_FILE: "specialist_backend_0"})

    assert _another_stage_s_test(tmp_path, TEST_FILE) == "specialist_testing_3"


def test_the_plan_is_read_from_the_workspace(tmp_path: Path) -> None:
    record_work_order_files(tmp_path, {TEST_FILE: "specialist_testing_1"})

    assert repository._the_plan_gave_it_to(tmp_path, TEST_FILE) == "specialist_testing_1"
    assert repository._the_plan_gave_it_to(tmp_path, "app/other.js") == ""
