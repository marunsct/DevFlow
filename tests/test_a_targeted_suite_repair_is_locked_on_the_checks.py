"""A reopened suite whose repair changed only the tests sent for it is locked again without a second full review.

Plan item 10. Measured on one run: a repair sent for one test fixed it in a minute; the full review that followed raised
four new findings about other tests, and locking again took fourteen minutes.
"""
from __future__ import annotations

import inspect

from app.acceptance import suite
from app.graph import acceptance_nodes
from app.stacks import contract, pack_named

HEAD = "import { test, expect } from '@playwright/test';\n"
BROKEN = "test('[AC-2] lists', async ({ request }) => {\n  expect(1).toBe(1);\n  expect(mine.length).toBe(2);\n});\n"
FIXED = "test('[AC-2] lists', async ({ request }) => {\n  expect(1).toBe(1);\n  expect(ours.length).toBe(2);\n});\n"
OTHER = "test('[AC-3] fetches', async ({ request }) => {\n  expect(2).toBe(2);\n});\n"


def _locked(tmp_path):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    spec = folder / "api.spec.js"
    spec.write_text(HEAD + BROKEN + OTHER)
    suite.lock(tmp_path)
    suite.unlock(tmp_path)
    suite.repairing(tmp_path, ["[AC-2] lists"])
    return spec


def test_a_repair_of_its_own_test_only_is_targeted(tmp_path):
    spec = _locked(tmp_path)
    spec.write_text(HEAD + FIXED + OTHER)
    assert suite.only_the_repaired_tests_changed(tmp_path) is True


def test_a_change_to_another_test_or_the_helpers_is_reviewed_whole(tmp_path):
    spec = _locked(tmp_path)
    spec.write_text(HEAD + FIXED + OTHER.replace("toBe(2)", "toBe(3)"))
    assert suite.only_the_repaired_tests_changed(tmp_path) is False
    spec.write_text(HEAD + "const helper = 1;\n" + FIXED + OTHER)
    assert suite.only_the_repaired_tests_changed(tmp_path) is False


def test_a_repair_that_drops_most_assertions_is_reviewed_whole(tmp_path):
    spec = _locked(tmp_path)
    spec.write_text(HEAD + "test('[AC-2] lists', async ({ request }) => {\n  await request.get('/notes');\n});\n" + OTHER)
    assert suite.only_the_repaired_tests_changed(tmp_path) is False


def test_nothing_under_repair_or_an_unchanged_suite_is_not_targeted(tmp_path):
    spec = _locked(tmp_path)
    assert suite.only_the_repaired_tests_changed(tmp_path) is False  # unchanged
    suite.lock(tmp_path)
    assert suite.only_the_repaired_tests_changed(tmp_path) is False  # locked, nothing under repair


def test_the_review_skips_its_model_review_for_one(monkeypatch):
    source = inspect.getsource(acceptance_nodes.acceptance_review)
    assert "targeted = not problems and suite.targeted_repair_switch.enabled() and suite.only_the_repaired_tests_changed(root)" in source
    assert "if not problems and not targeted:" in source


PY_HEAD = "import httpx\n\n\nclass TestItems:\n"
PY_BROKEN = "    def test_ac5_mark_done(self, base_url):\n        r = httpx.patch(f'{base_url}/items/1', json={'done': 1})\n        assert r.status_code == 200\n        assert r.json()['done'] is True\n\n"
PY_FIXED = "    def test_ac5_mark_done(self, base_url):\n        r = httpx.patch(f'{base_url}/items/1', json={'done': True})\n        assert r.status_code == 200\n        assert r.json()['done'] is True\n\n"
PY_OTHER = "    def test_ac6_delete(self, base_url):\n        assert httpx.delete(f'{base_url}/items/1').status_code == 204\n"


def test_a_python_suite_s_repair_of_its_own_test_is_targeted(tmp_path):
    """Measured on the held-out family: a Python suite's repair read as a change to everything and was reviewed whole."""
    contract.write(tmp_path, pack_named("python-http-api"), "tasks", "Tasks")
    folder = tmp_path / "tasks" / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    spec = folder / "test_items.py"
    spec.write_text(PY_HEAD + PY_BROKEN + PY_OTHER)
    suite.lock(tmp_path)
    suite.unlock(tmp_path)
    suite.repairing(tmp_path, ["test_ac5_mark_done"])
    spec.write_text(PY_HEAD + PY_FIXED + PY_OTHER)
    assert suite.only_the_repaired_tests_changed(tmp_path) is True
    spec.write_text(PY_HEAD + PY_FIXED + PY_OTHER.replace("204", "200"))
    assert suite.only_the_repaired_tests_changed(tmp_path) is False
