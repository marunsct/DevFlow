"""The quality score finds a development-only package imported by the product, and counts deliberation comments (PQ.10).

Measured on the product quality audit of 2026-11-25: a service's own module imported the test client its manifest
lists only among the development packages, and its container installs without them, so it would fail at start; and a
route handler carried 14 comment lines of the model's own deliberation ("Spec says...", "Let's assume...").
"""

from __future__ import annotations

import json
from pathlib import Path

from app.analysis import product_quality

NAME = "no development-only package imported by product code"

SERVICE_MANIFEST = json.dumps({
    "name": "notes", "type": "module", "scripts": {"start": "node src/index.js", "test": "node --test"},
    "dependencies": {"express": "^5.1.0"}, "devDependencies": {"@playwright/test": "1.64.0", "supertest": "^7.3.2"},
})
APP = ("import express from 'express';\nimport request from 'supertest';\nimport { join } from 'node:path';\n"
       "import { readNotes } from './store.js';\n\nexport const app = express();\n")
TEST = "import request from 'supertest';\nimport { app } from '../src/app.js';\n"


def _workspace(root: Path, files: dict[str, str]) -> Path:
    (root / ".project-directory").write_text("product\n")
    for name, text in files.items():
        path = root / "product" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "technical_specification.md").write_text("")
    return root


def _check(result: product_quality.QualityScore, name: str = NAME) -> product_quality.Check:
    (found,) = [c for p in result.parts for c in p.checks if c.name == name]
    return found


def test_a_service_module_importing_a_development_only_package_fails_the_check(tmp_path):
    workspace = _workspace(tmp_path, {"package.json": SERVICE_MANIFEST, "src/app.js": APP,
                                      "src/store.js": "export const readNotes = () => [];\n",
                                      "tests/app.test.js": TEST})

    result = product_quality.score_workspace(workspace)

    check = _check(result)
    assert check.passed == 0.0
    assert check.evidence == ["src/app.js:2 imports `supertest`, declared for development only in package.json"]
    assert result.counts["development-only imports"] == 1


def test_only_the_tests_importing_development_packages_pass_the_check(tmp_path):
    workspace = _workspace(tmp_path, {"package.json": SERVICE_MANIFEST,
                                      "src/app.js": APP.replace("import request from 'supertest';\n", ""),
                                      "tests/app.test.js": TEST})

    assert _check(product_quality.score_workspace(workspace)).passed == 1.0


def test_a_bundled_page_s_imports_are_left_to_its_build_and_its_server_still_read(tmp_path):
    manifest = json.dumps({"name": "board", "scripts": {"dev": "vite", "build": "vite build",
                                                        "start": "node server.js"},
                           "dependencies": {"express": "^5"},
                           "devDependencies": {"vite": "^7", "react": "^19", "supertest": "^7"}})
    workspace = _workspace(tmp_path, {
        "package.json": manifest,
        "src/main.js": "import { createRoot } from 'react';\ncreateRoot(document.body);\n",
        "server.js": "import express from 'express';\nimport request from 'supertest';\n",
    })

    check = _check(product_quality.score_workspace(workspace))

    assert check.evidence == ["server.js:2 imports `supertest`, declared for development only in package.json"]


def test_a_python_service_importing_a_package_of_its_test_group_fails_the_check(tmp_path):
    pyproject = ('[project]\nname = "notes"\ndependencies = ["fastapi>=0.110", "SQLAlchemy"]\n\n'
                 '[project.optional-dependencies]\ntest = ["pytest", "httpx", "Faker>=20"]\n')
    workspace = _workspace(tmp_path, {
        "pyproject.toml": pyproject,
        "app/main.py": "from fastapi import FastAPI\nimport sqlalchemy\nfrom faker import Faker\n",
        "tests/test_main.py": "import pytest\nimport httpx\n",
    })

    check = _check(product_quality.score_workspace(workspace))

    assert check.evidence == ["app/main.py:3 imports `faker`, declared for development only in pyproject.toml"]


def test_a_file_the_stack_pack_keeps_is_not_read_as_the_product_s_import(tmp_path):
    """Measured on a page product: the pack's own serving script imports the bundler, a development package."""
    manifest = json.dumps({"name": "board", "scripts": {"build": "vite build", "start": "node scripts/serve.mjs"},
                           "dependencies": {"react": "^19"}, "devDependencies": {"vite": "^7"}})
    workspace = _workspace(tmp_path, {"package.json": manifest, "src/main.js": "import React from 'react';\n",
                                      "scripts/serve.mjs": "import { preview } from 'vite';\n"})

    kept = product_quality.score(workspace / "product", harness_files={"scripts/serve.mjs"})
    as_the_product = product_quality.score(workspace / "product")

    assert _check(kept).passed == 1.0 and _check(as_the_product).passed == 0.0


def test_a_product_with_no_development_packages_declared_is_not_held_to_the_check(tmp_path):
    workspace = _workspace(tmp_path, {"app/main.py": "import os\n"})

    assert _check(product_quality.score_workspace(workspace)).passed is None


DELIBERATING = """export function create(req, res) {
  const validation = validate(req.body);
  if (!validation.valid) {
    // Return the first error message found as per spec examples
    // Spec says: {"error": "Title must not be empty"} etc.
    // Looking at spec examples, it seems to return one error object.
    // Let's assume we return the first error for simplicity
    // unless the test expects all.
    return res.status(422).json({ error: validation.errors[0] });
  }
  // Keep the stored order: newest first.
  // The list is read again after each write.
  return res.status(201).json(save(req.body));
}
"""


def test_comment_blocks_that_think_aloud_are_counted_and_ordinary_comments_are_not(tmp_path):
    workspace = _workspace(tmp_path, {"src/routes.mjs": DELIBERATING, "src/store.mjs": "// Reads the file.\n"})

    assert product_quality.score_workspace(workspace).counts["deliberation comment lines"] == 5
