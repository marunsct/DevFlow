"""A write importing a name an existing module does not export is refused once every planned file is written.

Measured on one run: three fixes in a row rewrote a route importing `{ StorageService }` from a module that exports
only a default instance; the guard excused the finding as "another file may not be written yet", each fix was
committed, broke the start, and was reverted. And the dispute's by-the-code check (LF.368) missed "the product never
loads the existing notes.json on startup", which reopened a locked restart test the brief requires.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app import delivery
from app.agents import suite_dispute
from app.analysis import language_service
from app.tools.repository import WORK_ORDER_FILES, RepositoryToolError, _refuse_if_it_adds_errors

FINDING = {"line": 1, "message": "Module '\"../services/storage.ts\"' has no exported member 'StorageService'. Did you "
                                 "mean to use 'import StorageService from \"../services/storage.ts\"' instead?"}


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / ".harness").mkdir()
    (tmp_path / "notes-api" / "src" / "routes").mkdir(parents=True)
    (tmp_path / "notes-api" / "src" / "services").mkdir()
    (tmp_path / "notes-api" / "src" / "services" / "storage.ts").write_text("export default new (class StorageService {})();\n")
    monkeypatch.setattr(delivery, "fast", lambda environment=None: True)
    monkeypatch.setattr(language_service, "underlined_any",
                        lambda root, target, content, project=None: SimpleNamespace(here=[FINDING] if content == "after" else []))
    return tmp_path


def _write(project):
    _refuse_if_it_adds_errors(project / "notes-api" / "src" / "routes" / "notes.ts", "notes-api/src/routes/notes.ts", "after", "")


def test_refused_with_the_checker_s_hint_when_the_module_exists_and_nothing_planned_is_unwritten(project):
    with pytest.raises(RepositoryToolError) as refused:
        _write(project)
    assert "has no exported member 'StorageService'" in str(refused.value) and "Did you mean" in str(refused.value)


def test_excused_while_a_planned_file_is_still_unwritten_or_the_module_does_not_exist(project):
    (project / WORK_ORDER_FILES).write_text(json.dumps({"notes-api/src/services/storage.ts": "specialist_backend_0",
                                                        "notes-api/src/app.ts": "specialist_backend_1"}))
    _write(project)
    (project / WORK_ORDER_FILES).unlink()
    (project / "notes-api" / "src" / "services" / "storage.ts").unlink()
    _write(project)


def test_a_dispute_reason_that_the_product_never_loads_its_data_keeps_the_test_locked():
    answer = SimpleNamespace(cannot_pass=[
        "[AC-6][AC-17] Notes survive a restart of the service: the product never loads the existing notes.json on "
        "startup, so no data is persisted across restarts as the test expects."])
    assert suite_dispute.tests_it_names(answer, ["[AC-6][AC-17] Notes survive a restart of the service"]) == []
