"""Tests for pre-lock acceptance suite static and load gates.

Verifies:
1. Tests with module system mismatches (CommonJS require in an ES module project) are caught before locking.
2. Un-awaited async helpers are detected before locking.
3. Acceptance review never locks an un-runnable suite that fails before executing tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.acceptance import suite


def test_module_system_mismatch_detected_for_require_in_esm(tmp_path: Path) -> None:
    project_dir = tmp_path / "my-app"
    project_dir.mkdir()
    acceptance_dir = project_dir / "acceptance"
    acceptance_dir.mkdir()

    # package.json declares ES modules
    (project_dir / "package.json").write_text(
        json.dumps({"name": "my-app", "type": "module"}),
        encoding="utf-8",
    )

    # Acceptance test authored with CommonJS require
    spec_file = acceptance_dir / "feature.spec.js"
    spec_file.write_text(
        "const { test, expect } = require('@playwright/test');\n"
        "test('proves [AC-1]', async ({ page }) => {});\n",
        encoding="utf-8",
    )

    harness_dir = tmp_path / ".harness"
    harness_dir.mkdir()
    (harness_dir / "acceptance.json").write_text(
        json.dumps({
            "project": "my-app",
            "acceptance_dir": "acceptance",
            "criteria": [{"id": "AC-1", "text": "Something works"}],
        }),
        encoding="utf-8",
    )

    from app.stacks import contract, pack_named

    contract.write(tmp_path, pack_named("browser-javascript"), "my-app", "My App")
    problems = suite.tests_with_module_system_mismatch(tmp_path)
    assert len(problems) == 1
    assert "require" in problems[0]
    assert "type" in problems[0]


def test_unawaited_async_helpers_detected(tmp_path: Path) -> None:
    project_dir = tmp_path / "my-app"
    project_dir.mkdir()
    acceptance_dir = project_dir / "acceptance"
    acceptance_dir.mkdir()

    spec_file = acceptance_dir / "feature.spec.js"
    spec_file.write_text(
        "import { test, expect } from '@playwright/test';\n"
        "const findElement = async (page, name) => page.getByRole('listitem');\n"
        "test('proves [AC-1]', async ({ page }) => {\n"
        "  const el = findElement(page, 'first');\n"
        "  await el.click();\n"
        "});\n",
        encoding="utf-8",
    )

    harness_dir = tmp_path / ".harness"
    harness_dir.mkdir()
    (harness_dir / "acceptance.json").write_text(
        json.dumps({
            "project": "my-app",
            "acceptance_dir": "acceptance",
            "criteria": [{"id": "AC-1", "text": "Something works"}],
        }),
        encoding="utf-8",
    )

    from app.stacks import contract, pack_named

    contract.write(tmp_path, pack_named("browser-javascript"), "my-app", "My App")
    problems = suite.tests_with_unawaited_async_helpers(tmp_path)
    assert len(problems) == 1
    assert "findElement" in problems[0]
    assert "await" in problems[0].lower()


def test_acceptance_review_refuses_to_lock_unrunnable_suite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.graph import acceptance_nodes
    from app.acceptance.suite import AcceptanceResult

    harness_dir = tmp_path / ".harness"
    harness_dir.mkdir()
    (harness_dir / "acceptance.json").write_text(
        json.dumps({
            "project": "my-app",
            "acceptance_dir": "acceptance",
            "criteria": [{"id": "AC-1", "text": "Something works"}],
        }),
        encoding="utf-8",
    )

    class DummyRepo:
        root_path = str(tmp_path)

    state = {
        "repository": DummyRepo(),
        "acceptance_round": acceptance_nodes.MAX_ACCEPTANCE_ROUNDS,
    }
    config = {"configurable": {"thread_id": "test", "run_id": "test-run"}}

    class DummyCtx:
        judgement_model = None
        checkpointer = None
        repo_root = str(tmp_path)
        allow_subdirectories = True

    unrunnable = AcceptanceResult(
        ran=False,
        exit_code=1,
        command="npm run test:acceptance",
        problem="the runner wrote no report; its output is below",
        output="ReferenceError: require is not defined in ES module scope",
    )
    monkeypatch.setattr(suite, "run", lambda root: unrunnable)
    monkeypatch.setattr(suite, "gaps", lambda root: [])

    update = acceptance_nodes.acceptance_review(state, config, DummyCtx())
    assert not suite.is_locked(tmp_path), "Acceptance suite must never be locked when the runner failed to execute"
    assert update.get("stage") == "acceptance_author"


def test_prelock_suite_validation_messages_ban_product_and_interface_words() -> None:
    import inspect
    import re
    from app.graph import acceptance_nodes

    source_suite = inspect.getsource(suite.tests_with_module_system_mismatch) + inspect.getsource(suite.tests_with_unawaited_async_helpers)
    source_nodes = inspect.getsource(acceptance_nodes.acceptance_review)

    for word in ("button", "click", "checkbox", "todo", "to-do", "task"):
        # Match whole words (case-insensitive) in error messages / prompt strings
        assert not re.search(rf"\b{word}s?\b", source_suite, re.IGNORECASE), f"Banned word {word} found in suite checks"






class TestCorrectCodeIsNotRefused:
    """Each was a correct suite the checks sent back to QA, reproduced before it was fixed."""

    def test_storage_seeded_through_add_init_script(self) -> None:
        from app.stacks.packs import _javascript as js

        code = (
            "import { test, expect } from '@playwright/test';\n"
            "test('[AC-1] a saved record is shown', async ({ page }) => {\n"
            "  await page.addInitScript(() => localStorage.setItem('records', '[]'));\n"
            "  await page.goto('/');\n"
            "});\n"
        )
        assert js.storage_before_page_open(code) == []

    def test_a_comment_that_names_storage(self) -> None:
        from app.stacks.packs import _javascript as js

        code = (
            "import { test, expect } from '@playwright/test';\n"
            "test('[AC-2] starts empty', async ({ page }) => {\n"
            "  // nothing is in localStorage at first\n"
            "  await page.goto('/');\n"
            "});\n"
        )
        assert js.storage_before_page_open(code) == []

    def test_helpers_awaited_together(self) -> None:
        from app.stacks.packs import _javascript as js

        code = (
            "async function add(page, title) { await page.getByLabel('Title').fill(title); }\n"
            "test('[AC-3] two', async ({ page }) => {\n"
            "  const done = await Promise.all([add(page, 'One'), add(page, 'Two')]);\n"
            "  add(page, 'Three').then(() => {});\n"
            "  return add(page, 'Four');\n"
            "});\n"
        )
        assert js.unawaited_helpers(code) == []

    def test_a_helper_still_used_unawaited_is_found(self) -> None:
        from app.stacks.packs import _javascript as js

        code = (
            "const find = async (page) => page.getByRole('listitem');\n"
            "test('[AC-3] one', async ({ page }) => {\n"
            "  const item = find(page);\n"
            "  find(page).click();\n"
            "});\n"
        )
        assert js.unawaited_helpers(code) == [(3, "find"), (4, "find")]

    def test_require_made_with_create_require(self, tmp_path) -> None:
        from app.stacks.packs import _javascript as js

        (tmp_path / "package.json").write_text(json.dumps({"type": "module"}))
        code = (
            "import { createRequire } from 'node:module';\n"
            "const require = createRequire(import.meta.url);\n"
            "const fixtures = require('./fixtures.json');\n"
        )
        assert js.module_system_mismatch(tmp_path, tmp_path / "a.spec.js", code) == []

    def test_require_in_a_comment(self, tmp_path) -> None:
        from app.stacks.packs import _javascript as js

        (tmp_path / "package.json").write_text(json.dumps({"type": "module"}))
        code = "// require('x') would fail here\nimport { test } from '@playwright/test';\n"
        assert js.module_system_mismatch(tmp_path, tmp_path / "a.spec.js", code) == []


def test_a_project_no_pack_set_up_is_not_checked_by_a_pack_s_rules(tmp_path: Path) -> None:
    project_dir = tmp_path / "my-app"
    (project_dir / "acceptance").mkdir(parents=True)
    (project_dir / "package.json").write_text(json.dumps({"type": "module"}))
    (project_dir / "acceptance" / "a.spec.js").write_text("const x = require('y');\n")
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "acceptance.json").write_text(json.dumps({
        "project": "my-app", "acceptance_dir": "acceptance", "criteria": [],
    }))

    assert suite.tests_with_module_system_mismatch(tmp_path) == []
