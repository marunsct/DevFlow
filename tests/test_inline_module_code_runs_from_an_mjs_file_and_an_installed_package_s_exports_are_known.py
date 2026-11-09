"""Inline `node -e` code written as a module runs from a `.mjs` file; a missing export of an installed package is refused.

Measured on one run: two fixers' probes (`node -e "import { Hono } from 'hono'; ..."`) failed with "Failed to load the
ES module: tmp-inline-....cjs" and each concluded "cannot run tests in this environment"; and `import bodyLimit from
'hono/body-limit'` (the package exports only `{ bodyLimit }`) was written twice, broke the start twice, and was
reverted twice because the write guard excused every package import as possibly not written yet.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app import delivery
from app.analysis import language_service
from app.tools import agent_toolkit
from app.tools.repository import RepositoryToolError, _refuse_if_it_adds_errors


def test_module_code_on_the_command_line_is_saved_as_mjs_and_script_code_as_cjs(tmp_path):
    (tmp_path / ".harness").mkdir()
    (tmp_path / "notes-api").mkdir()
    esm = ["node", "-e", "import { Hono } from 'hono'; const app = new Hono(); console.log(typeof app.fetch);"]
    rewritten, _ = agent_toolkit._code_on_the_command_line_as_a_file(esm, str(tmp_path), "notes-api")
    assert rewritten[1].endswith(".mjs"), rewritten
    cjs = ["node", "-e", "const m = require('./dist/app.js'); console.log(Object.keys(m));"]
    rewritten, _ = agent_toolkit._code_on_the_command_line_as_a_file(cjs, str(tmp_path), "notes-api")
    assert rewritten[1].endswith(".cjs"), rewritten


FINDING = {"line": 3, "message": "Module '\"hono/body-limit\"' has no default export. Did you mean to use "
                                 "'import { bodyLimit } from \"hono/body-limit\"' instead?"}


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / ".harness").mkdir()
    (tmp_path / "notes-api" / "src" / "middleware").mkdir(parents=True)
    monkeypatch.setattr(delivery, "fast", lambda environment=None: True)
    monkeypatch.setattr(language_service, "underlined_any",
                        lambda root, target, content, project=None: SimpleNamespace(here=[FINDING] if content == "after" else []))
    return tmp_path


def _write(project):
    _refuse_if_it_adds_errors(project / "notes-api" / "src" / "middleware" / "bodyLimit.ts",
                              "notes-api/src/middleware/bodyLimit.ts", "after", "")


def test_a_missing_export_of_an_installed_package_is_refused_with_the_checker_s_hint(project):
    (project / "notes-api" / "node_modules" / "hono").mkdir(parents=True)
    with pytest.raises(RepositoryToolError) as refused:
        _write(project)
    assert "has no default export" in str(refused.value) and "import { bodyLimit }" in str(refused.value)


def test_a_package_not_installed_yet_is_still_excused(project):
    _write(project)
