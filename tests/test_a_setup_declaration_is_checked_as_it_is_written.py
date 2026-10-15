"""A setup declaration is checked as it is written, so the stage fixes it in the conversation it is in.

One run's setup stage declared one directory for both kinds of test, learned
so only after it had answered, and the setup was left to the agents.
"""

from __future__ import annotations

import json
import re

import pytest

from app.tools.repository import RepositoryToolError, write_approved_artifact

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

DECLARED = {
    "kind": "http_api",
    "install": [["npm", "install"]],
    "unit_test": ["npm", "test"],
    "unit_report": "test-results/unit.xml",
    "unit_dir": "tests/unit",
    "unit_pattern": "*.test.js",
    "acceptance_test": ["npm", "run", "test:acceptance"],
    "acceptance_report": "test-results/acceptance.xml",
    "acceptance_dir": "tests/acceptance",
    "acceptance_pattern": "*.test.js",
    "kept_files": ["tsconfig.json"],
    "smoke_files": ["tests/unit/smoke.test.js", "tests/acceptance/smoke.test.js"],
}


def _write(tmp_path, declared):
    (tmp_path / "notes-api").mkdir(exist_ok=True)
    return write_approved_artifact(tmp_path, "notes-api/stack-setup.json", json.dumps(declared))


def test_one_directory_for_both_kinds_of_test_is_refused_with_why(tmp_path):
    with pytest.raises(RepositoryToolError) as refused:
        _write(tmp_path, {**DECLARED, "acceptance_dir": "tests/unit"})

    assert "acceptance tests need a directory of their own" in str(refused.value)
    assert not (tmp_path / "notes-api" / "stack-setup.json").exists()
    assert not BANNED.search(str(refused.value))


def test_a_sound_declaration_is_written_before_the_files_it_names(tmp_path):
    _write(tmp_path, DECLARED)

    assert json.loads((tmp_path / "notes-api" / "stack-setup.json").read_text())["unit_dir"] == "tests/unit"
