"""A data file the product writes in its data directory is not a file a work order must be given.

Measured on one run: the sprint's scope named `notes.json`, which the specification says the service reads from
DATA_DIR and writes there, and the plan was sent back for a file no work order can write.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.analysis import work_orders
from app.stacks import contract, pack_named

SPEC = "- Load Notes Flow: On startup, persistence.loadNotes(dataDir) reads notes.json from DATA_DIR."


def _project(tmp_path, spec=SPEC):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes-api", "Notes")
    (tmp_path / "notes-api" / "src").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technical_specification.md").write_text(spec)
    return tmp_path


TASKS = [SimpleNamespace(files=["notes-api/src/app.ts"])]


def test_the_product_s_data_file_is_left_and_a_source_file_is_still_named(tmp_path):
    root = _project(tmp_path)
    scope = "Persist notes to notes.json and add src/persistence.ts for the store."
    named = work_orders._files_the_sprint_names_and_nobody_is_given(scope, TASKS, root, "notes-api")
    assert named == ["persistence.ts"]


def test_a_json_file_never_named_beside_the_data_directory_is_still_named(tmp_path):
    root = _project(tmp_path, spec="The service reads its settings from config.json at start.")
    named = work_orders._files_the_sprint_names_and_nobody_is_given("Write config.json.", TASKS, root, "notes-api")
    assert named == ["config.json"]
