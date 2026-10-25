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
