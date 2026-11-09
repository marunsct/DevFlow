"""A fix for "no exported member" is made in the module that should export it, not in the test that imports it.

Measured on one run: a test imported `makePersistence` from `../src/store.js`, which did not exist. The failure text named
`src/store.js`; the file is `store.ts`, so it was not found, and the fix rewrote only the test - defining a stand-in for the
missing function inside it. The type error went away, the suite passed, and the feature was never built.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.graph import rewritten_fixes

FAILURE = (
    "notes-api/tests/sqlite.store.test.ts line 6: Module '\"../src/store.js\"' has no exported member 'makePersistence'.\n"
    "notes-api/tests/sqlite.store.test.ts(6,10): error TS2305"
)


def _project(root: Path) -> None:
    (root / "notes-api" / "src").mkdir(parents=True)
    (root / "notes-api" / "tests").mkdir()
    (root / "notes-api" / "src" / "store.ts").write_text("export const loadNotes = () => [];\n")
    (root / "notes-api" / "tests" / "sqlite.store.test.ts").write_text("import { makePersistence } from '../src/store.js';\n")


def _defect(description="The language service: line 6"):
    return SimpleNamespace(description=description, affected_files=["notes-api/tests/sqlite.store.test.ts"])


def _files(root: Path, failure: str, defect=None) -> list[str]:
    return rewritten_fixes.files_to_fix(defect or _defect(), failure, root, lambda path: True)


def test_a_compiled_name_stands_for_its_typescript_source():
    assert rewritten_fixes._its_typescript_sources("src/store.js") == ["src/store.ts", "src/store.tsx"]
    assert rewritten_fixes._its_typescript_sources("src/a.mjs") == ["src/a.mts"]
    assert rewritten_fixes._its_typescript_sources("src/store.py") == []


def test_the_module_that_should_export_it_is_the_file_to_fix_and_the_test_is_left_alone(tmp_path):
    _project(tmp_path)

    assert _files(tmp_path, FAILURE) == ["notes-api/src/store.ts"]


def test_the_runtime_wording_of_a_missing_export_does_the_same(tmp_path):
    _project(tmp_path)
    failure = ("notes-api/tests/sqlite.store.test.ts:6\nSyntaxError: The requested module '../src/store.js' "
               "does not provide an export named 'makePersistence'")

    assert _files(tmp_path, failure) == ["notes-api/src/store.ts"]


def test_a_name_in_a_failure_that_is_only_compiled_output_still_finds_its_source(tmp_path):
    _project(tmp_path)
    (tmp_path / "notes-api" / "src" / "app.ts").write_text("export const app = 1;\n")
    failure = "TypeError: cannot read properties\n    at handler (notes-api/src/app.js:12:5)"

    assert "notes-api/src/app.ts" in _files(tmp_path, failure, SimpleNamespace(description="x", affected_files=[]))


def test_an_ordinary_failure_in_a_test_is_fixed_where_it_always_was(tmp_path):
    _project(tmp_path)
    failure = "notes-api/tests/sqlite.store.test.ts:6\nAssertionError: expected 1 to be 2"

    found = _files(tmp_path, failure, _defect("The unit tests fail. It says: expected 1 to be 2"))

    assert found == ["notes-api/tests/sqlite.store.test.ts"]


def test_when_the_exporter_cannot_be_found_nothing_changes(tmp_path):
    _project(tmp_path)
    (tmp_path / "notes-api" / "src" / "store.ts").unlink()

    assert _files(tmp_path, FAILURE) == _files(tmp_path, "no module named here")
