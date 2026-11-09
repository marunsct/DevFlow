"""A specification's settings written in prose reach the README, and "no settings" is not scored as undocumented.

Measured on four of eleven releases: specifications wrote `- Environment Variable: PORT (number) - ... Default: 3000.`,
which the README writer did not read, so the README named no setting; and a static page whose specification said
"Environment Variable: None" was scored as failing to document its configuration.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest import mock

from app.stacks import release_docs

SPEC = """# Spec

## Configuration
- Environment Variable: PORT (string/number) - The TCP port the HTTP server listens on. Default: 3000. Used by: start.sh.
- Environment Variable: DATA_DIR (string) - Where notes.json is stored. Default: 'data/'. Used by: src/storage.ts.
- File: notes-api/start.sh - Executable entrypoint script.
- Dependency: hono v4 - The framework.

## Next
"""


def _score():
    path = Path(__file__).resolve().parents[1] / "scripts" / "bench" / "score.py"
    spec = importlib.util.spec_from_file_location("score_for_config", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_prose_entries_are_read_with_their_defaults(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technical_specification.md").write_text(SPEC)
    assert release_docs._the_configuration(tmp_path) == [
        ("PORT", "3000", "The TCP port the HTTP server listens on"),
        ("DATA_DIR", "data/", "Where notes.json is stored"),
    ]


def test_the_readme_gets_a_configuration_table(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technical_specification.md").write_text(SPEC)
    (tmp_path / ".project-directory").write_text("app")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "README.md").write_text("# App\n\nRun `npm start`.\n")
    with mock.patch.object(release_docs, "enabled", return_value=True), \
         mock.patch.object(release_docs, "_ways_to_run", return_value=["npm start"]):
        release_docs.complete_the_handoff(tmp_path)
    readme = (tmp_path / "app" / "README.md").read_text()
    assert "## Configuration" in readme and "| `PORT` | 3000 |" in readme and "| `DATA_DIR` | data/ |" in readme


def test_a_specification_that_reads_no_setting_is_not_scored_against_the_readme(tmp_path):
    score = _score()
    (tmp_path / "docs").mkdir()
    (tmp_path / "app").mkdir()
    spec = tmp_path / "docs" / "technical_specification.md"
    spec.write_text("## Configuration\n- Environment Variable: None. The page reads no environment variables.\n")
    assert score._it_has_configuration(tmp_path / "app") is False
    spec.write_text(SPEC)
    assert score._it_has_configuration(tmp_path / "app") is True
    spec.write_text("## Configuration\n- variable: `PORT`; type: int; default: 8000\n")
    assert score._it_has_configuration(tmp_path / "app") is True
