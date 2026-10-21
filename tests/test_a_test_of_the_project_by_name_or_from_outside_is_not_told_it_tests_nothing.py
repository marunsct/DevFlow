"""A test that imports the project by name, or tests it from outside, is not told it tests nothing.

The check knew only relative imports (`./app.js`), so every Python test file
- `from notes_api.db import insert` - was told it imports nothing from the
project, and one run's black-box acceptance suite, which meets the product over
HTTP as it is meant to, was told to import the module under test in another
language's syntax.
"""
from __future__ import annotations

import json

from app.analysis import test_discovery as discovery

DOC_TEST = "import os\n\ndef test_readme():\n    assert os.path.exists('README.md')\n"


def _project(root):
    (root / "notes-api" / "notes_api").mkdir(parents=True)
    (root / "notes-api" / "notes_api" / "__init__.py").write_text("")
    (root / "notes-api" / "tests").mkdir()
    (root / "notes-api" / "acceptance").mkdir()
    return root / "notes-api"


def test_a_python_test_importing_the_project_by_name_is_a_test_of_it(tmp_path):
    project = _project(tmp_path)
    target = project / "tests" / "test_db.py"
    content = "from notes_api.db import insert\n\ndef test_insert():\n    assert insert('a')\n"

    assert discovery.tests_nothing_of_the_project("notes-api/tests/test_db.py", content, target) is None


def test_the_acceptance_suite_tests_from_outside_by_design(tmp_path):
    project = _project(tmp_path)
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "acceptance.json").write_text(json.dumps({"project": "notes-api", "acceptance_dir": "acceptance"}))
    target = project / "acceptance" / "test_acceptance.py"
    content = "import httpx\n\ndef test_create(base_url):\n    assert httpx.post(base_url + '/notes').status_code == 201\n"

    assert discovery.tests_nothing_of_the_project("notes-api/acceptance/test_acceptance.py", content, target) is None


def test_a_test_of_the_repository_s_files_is_still_told_and_in_no_one_language_s_words(tmp_path):
    project = _project(tmp_path)
    note = discovery.tests_nothing_of_the_project("notes-api/tests/test_docs.py", DOC_TEST, project / "tests" / "test_docs.py")

    assert note and "imports nothing from the project" in note
    assert "./app.js" not in note and "node:test" not in note
