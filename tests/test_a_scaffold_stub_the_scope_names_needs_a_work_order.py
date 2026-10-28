"""A file the sprint's scope names that is still the scaffold's stub needs a work order like any unbuilt file.

Measured on one run: the scope named `src/app.ts` - "complete Hono app with all six endpoints" - and no work order
listed it; the check passed it as a file that already existed, and the first draft passed 2 of 18 criteria against the
scaffold's stub.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.analysis import work_orders
from app.stacks import contract, pack_named

SCOPE = "- src/app.ts — complete Hono app with all six endpoints, validation, error handling\n- src/storage.ts — persistence"
TASKS = [SimpleNamespace(files=["notes-api/src/storage.ts"])]


def _scaffolded(tmp_path):
    pack = pack_named("node-hono-native-api")
    contract.write(tmp_path, pack, "notes-api", "Notes")
    for relative, text in pack.render("notes-api", "Notes", None).items():
        target = tmp_path / "notes-api" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    return tmp_path


def test_the_stub_entrypoint_is_named_as_nobody_s(tmp_path):
    root = _scaffolded(tmp_path)
    assert work_orders._files_the_sprint_names_and_nobody_is_given(SCOPE, TASKS, root, "notes-api") == ["app.ts"]


def test_a_built_entrypoint_is_not(tmp_path):
    root = _scaffolded(tmp_path)
    (root / "notes-api" / "src" / "app.ts").write_text("export function createApp() { /* built */ }\n")
    assert work_orders._files_the_sprint_names_and_nobody_is_given(SCOPE, TASKS, root, "notes-api") == []
