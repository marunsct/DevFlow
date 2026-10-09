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




