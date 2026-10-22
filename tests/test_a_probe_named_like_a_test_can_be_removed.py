"""A debugging script with a test's name is clutter, and can be deleted.

Measured on one run: a fix stage wrote `test_load.js`, `test_run.js` and
`test_form.js` to see what the page did - each imports the product and ends in
`console.log` - and had four deletes refused because the names are ones a
runner collects. Two were left in the product.

The protection is for evidence. A file that registers no test and asserts
nothing is not evidence of anything.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.test_discovery import holds_no_test
from app.tools.repository import RepositoryToolError, delete_approved_artifact

PROBE = (
    "import { JSDOM } from 'jsdom';\n"
    "const dom = new JSDOM(`<!DOCTYPE html><html></html>`);\n"
    "global.window = dom.window;\n"
    "import('./storage.js').then(({ load }) => {\n"
    "  console.log('load', load());\n"
    "});\n"
)

SUITE = (
    "import { test } from 'node:test';\n"
    "import assert from 'node:assert';\n"
    "import { load } from './storage.js';\n"
    "test('loads nothing from an empty store', () => {\n"
    "  assert.deepStrictEqual(load(), []);\n"
    "});\n"
)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr("app.observability.transcript._stage_from_config", lambda fallback: "defect_fix_2_1")
    (tmp_path / "the-app").mkdir()
    return tmp_path


def test_a_probe_with_a_test_s_name_is_deleted(workspace) -> None:
    (workspace / "the-app" / "test_load.js").write_text(PROBE, encoding="utf-8")

    delete_approved_artifact(workspace, "the-app/test_load.js")

    assert not (workspace / "the-app" / "test_load.js").exists()


def test_a_real_suite_is_still_kept(workspace) -> None:
    (workspace / "the-app" / "test_load.js").write_text(SUITE, encoding="utf-8")

    with pytest.raises(RepositoryToolError) as caught:
        delete_approved_artifact(workspace, "the-app/test_load.js")

    assert "is a test" in str(caught.value)
    assert (workspace / "the-app" / "test_load.js").exists()


@pytest.mark.parametrize("content", [
    SUITE,
    "test('x', () => {});\n",
    "describe('store', () => {});\n",
    "def test_load():\n    pass\n",
    "func TestLoad(t *testing.T) {}\n",
    "#[test]\nfn loads() {}\n",
    "const out = run();\nif (out !== 1) throw new Error('wrong');\n",
])
def test_anything_that_could_be_a_test_counts_as_one(content) -> None:
    assert not holds_no_test(content)


def test_a_script_that_only_prints_holds_no_test() -> None:
    assert holds_no_test(PROBE)
