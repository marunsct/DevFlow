"""A pack's entry file that stops exporting what the scaffold's own files import is a defect at once.

Measured on a small-model run: the Hono pack builds its app in `createApp()` in `src/app.ts`; drafting rewrote the file
with a default export and no `createApp`, and seven test files imported the missing name before one fix restored it.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.graph import acceptance_nodes
from app.stacks import contract, entry_exports, pack_named


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("PACK_ENTRY_EXPORTS_KEPT", "on")


def _project(tmp_path, app_ts: str):
    pack = pack_named("node-hono-api")
    contract.write(tmp_path, pack, "notes", "Notes")
    (tmp_path / "notes" / "src").mkdir(parents=True)
    (tmp_path / "notes" / "src" / "app.ts").write_text(app_ts)
    (tmp_path / ".project-directory").write_text("notes\n")


def test_the_hono_pack_names_the_export_its_smoke_test_and_server_import():
    pack = pack_named("node-hono-api")
    assert pack.required_exports == {"src/app.ts": ("createApp",)}
    assert "createApp" in pack.files["src/main.ts"] and "createApp" in pack.smoke_files["test/scaffold-smoke.spec.ts"]


@pytest.mark.parametrize("text", [
    "import { Hono } from 'hono';\nexport function createApp(): Hono { return new Hono(); }\n",
    "export const createApp = () => 1;\n",
    "const createApp = () => 1;\nexport { createApp };\n",
    "export async function createApp() {}\n",
])
def test_an_entry_file_that_still_exports_the_name_has_nothing_to_report(tmp_path, text):
    _project(tmp_path, text)
    assert entry_exports.what_the_entry_no_longer_exports(tmp_path) == []


@pytest.mark.parametrize("text", [
    "import { Hono } from 'hono';\nexport const app = new Hono();\nexport default app;\n",
    "function createApp() {}\nexport default createApp;\n",
    "",
])
def test_an_entry_file_that_dropped_the_name_is_reported(tmp_path, text):
    _project(tmp_path, text)
    assert entry_exports.what_the_entry_no_longer_exports(tmp_path) == [("notes/src/app.ts", "createApp")]


def test_a_missing_entry_file_is_reported_and_a_project_without_a_pack_is_not(tmp_path):
    _project(tmp_path, "")
    (tmp_path / "notes" / "src" / "app.ts").unlink()
    assert entry_exports.what_the_entry_no_longer_exports(tmp_path) == [("notes/src/app.ts", "createApp")]
    assert entry_exports.what_the_entry_no_longer_exports(tmp_path / "nowhere") == []


def test_the_round_raises_a_defect_naming_the_file_and_the_export(tmp_path, monkeypatch):
    _project(tmp_path, "export default function app() {}\n")
    monkeypatch.setattr(acceptance_nodes, "_root", lambda state: str(tmp_path))
    monkeypatch.setattr(acceptance_nodes, "_owner_for", lambda state, text: "backend")

    defects = acceptance_nodes.pack_contract_defects(SimpleNamespace())

    assert len(defects) == 1
    assert "notes/src/app.ts no longer exports `createApp`" in defects[0].description
    assert defects[0].affected_files == ["notes/src/app.ts"] and defects[0].owner == "backend"


def test_off_it_reports_nothing(tmp_path, monkeypatch):
    _project(tmp_path, "export default function app() {}\n")
    monkeypatch.setenv("PACK_ENTRY_EXPORTS_KEPT", "off")
    assert entry_exports.what_the_entry_no_longer_exports(tmp_path) == []


def test_a_required_export_the_start_file_calls_bare_that_now_needs_an_argument_is_a_defect(tmp_path):
    """Measured on one run: `createApp(storage)` took the store as a parameter; the start file calls `createApp()`, every
    handler read `undefined.storage` and answered 500, and two sprint attempts went on fixes to the routes."""
    pack = pack_named("node-hono-native-api")
    contract.write(tmp_path, pack, "notes", "Notes")
    (tmp_path / "notes" / "src").mkdir(parents=True)
    (tmp_path / "notes" / "src" / "app.ts").write_text(
        "import type { JsonStorage } from './storage/jsonStorage.ts';\nexport function createApp(storage: JsonStorage): Hono {\n  return new Hono();\n}\n")
    (tmp_path / ".project-directory").write_text("notes\n")
    assert entry_exports.what_the_start_file_cannot_call(tmp_path) == [("notes/src/app.ts", "createApp", "storage")]
    [defect] = acceptance_nodes.pack_contract_defects({"repository": SimpleNamespace(root_path=str(tmp_path))})
    assert "createApp(storage)" in defect.description and defect.affected_files == ["notes/src/app.ts"]


@pytest.mark.parametrize("text", [
    "export function createApp(): Hono { return new Hono(); }\n",
    "export function createApp(storage = new Store()) { return 1; }\n",
    "export const createApp = (options?: Options) => 1;\n",
])
def test_a_factory_callable_bare_is_left(tmp_path, text):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    (tmp_path / "notes" / "src").mkdir(parents=True)
    (tmp_path / "notes" / "src" / "app.ts").write_text(text)
    (tmp_path / ".project-directory").write_text("notes\n")
    assert entry_exports.what_the_start_file_cannot_call(tmp_path) == []


def test_a_contract_defect_is_settled_by_its_own_check_not_by_unit_tests(tmp_path):
    """Measured on one run: `createApp()` was made callable bare and the defect was left open because unrelated unit
    tests failed; the attempt was spent and the sprint planned again over a green suite."""
    from app.graph import workflow

    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    (tmp_path / "notes" / "src").mkdir(parents=True)
    app_ts = tmp_path / "notes" / "src" / "app.ts"
    app_ts.write_text("export function createApp(storage: Store): Hono { return new Hono(); }\n")
    (tmp_path / ".project-directory").write_text("notes\n")
    [defect] = acceptance_nodes.pack_contract_defects({"repository": SimpleNamespace(root_path=str(tmp_path))})
    assert entry_exports.still_raised(tmp_path, defect.description) is True
    assert workflow._the_defect_s_tests_in(str(tmp_path), "after defect_fix_1_0", defect) is False
    app_ts.write_text("export function createApp(): Hono { return new Hono(); }\n")
    assert entry_exports.still_raised(tmp_path, defect.description) is False
    assert workflow._the_defect_s_tests_in(str(tmp_path), "after defect_fix_1_0", defect) is True
    assert entry_exports.still_raised(tmp_path, "[AC-1] Create a note") is None
