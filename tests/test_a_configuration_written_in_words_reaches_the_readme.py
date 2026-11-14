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


# Measured on one release: `- Environment Variable: PORT (default: 3000). Used by ...` - a full stop after the
# bracket, the default inside it - matched nothing, and the README named no setting.
def test_a_full_stop_after_the_variable_and_a_bracketed_default_are_read(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technical_specification.md").write_text(
        "## Configuration\n"
        "- Environment Variable: PORT (default: 3000). Used by scripts/serve.mjs to set the port the server listens on.\n"
        "- File: index.html. Entry point.\n")
    assert release_docs._the_configuration(tmp_path) == [
        ("PORT", "3000", "Used by scripts/serve.mjs to set the port the server listens on")]


# Measured on one release: a library's README said how to install and test it and never how to call it - its calls
# are not locked as commands, so the usage section had nothing to show.
def test_a_library_s_readme_shows_its_calls_from_the_specification(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technical_specification.md").write_text(
        "## Interface Contract\n"
        "- AC-1 command import textkit -> textkit.slugify available\n"
        "- AC-3 command textkit.slugify(text='Hello, World!') -> 'hello-world'\n"
        "- AC-5 command textkit.truncate(text='Hello', limit=-1) -> ValueError\n\n## File Plan\n- x\n")
    section = release_docs._the_using_section("# Lib\n", [], tmp_path)
    assert section.startswith("\n## Using it")
    assert "textkit.slugify(text='Hello, World!')  # -> 'hello-world'" in section
    assert "import textkit  # -> textkit.slugify available" in section
    assert release_docs._the_using_section("# Lib\n", [], None) == "", "no specification, nothing to show"


# Measured on one release: `- PORT: The port ... Default: 3000. Environment variable: PORT.` - the name first, the
# variable said last - matched neither form, and the README named no setting.
def test_the_name_first_with_the_variable_said_last_is_read(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technical_specification.md").write_text(
        "## Configuration\n"
        "- PORT: The port number the server listens on. Default: 3000. Environment variable: PORT.\n"
        "- DATA_DIR: The directory where notes.json is stored. Default: ./data. Environment variable: DATA_DIR.\n"
        "- start.sh: The entry point script.\n"
        "- Hono: The web framework. Version: 4.13.17.\n")
    assert release_docs._the_configuration(tmp_path) == [
        ("PORT", "3000", "The port number the server listens on"),
        ("DATA_DIR", "./data", "The directory where notes.json is stored"),
    ]


# Three phrasings were added one release at a time; any other line that calls an upper-case name an environment
# variable or a setting is read too, and a line that is not about a setting is not.
def test_any_other_phrasing_of_a_setting_is_read(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technical_specification.md").write_text(
        "## Configuration\n"
        "- The environment variable `MAX_ITEMS` caps the list; default 100.\n"
        "- Setting LOG_LEVEL controls logging. Default: info.\n"
        "- Uses JSON for all responses.\n"
        "- File: README.md describes it.\n")
    found = release_docs._the_configuration(tmp_path)
    assert [name for name, _, _ in found] == ["MAX_ITEMS", "LOG_LEVEL"]
    assert found[1][1] == "info"


# Measured on one release: the contract's criterion ids were `AC-CLI-1`, and no line matched - the README of a
# command-line tool said nowhere how to run it.
def test_a_command_under_any_criterion_id_reaches_the_using_section(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technical_specification.md").write_text(
        "## Interface Contract\n"
        "- AC-CLI-1 command python -m wordstats <file> prints three lines to stdout -> exit 0\n"
        "- AC-CLI-2 command python -m wordstats <file> --top N prints N lines -> exit 0\n\n## File Plan\n")
    section = release_docs._the_using_section("# Tool\n", [], tmp_path)
    assert "python -m wordstats <file> prints three lines to stdout  # -> exit 0" in section


# Measured on one release: a library's contract wrote each call as itself, with no `command` word; none matched, and its
# README never said how to call it (handoff 0.833).
def test_a_call_written_without_the_command_word_reaches_the_using_section(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technical_specification.md").write_text(
        "## Interface Contract\n"
        "- AC-1 import textkit -> success\n"
        "- AC-2 hasattr(textkit, 'slugify') == True\n"
        "- AC-6 textkit.slugify('Hello, World!') -> 'hello-world'\n"
        "- AC-10 textkit.word_count('a  b') -> 2\n\n## File Plan\n")
    section = release_docs._the_using_section("# Lib\n", [], tmp_path)
    assert "textkit.slugify('Hello, World!')  # -> 'hello-world'" in section
    assert "textkit.word_count('a  b')  # -> 2" in section
    assert "hasattr" not in section and "import textkit  # -> success" not in section
