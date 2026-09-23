"""A product that stops loading when its storage is damaged.

Stored data is the one input a product cannot vouch for: it outlived the
process that wrote it, and a half-written write, a schema change between
versions, another tab or a user with developer tools can each leave it as
something the parser will not accept. Every parser this check knows raises on
that input rather than returning a default.

Measured across the stored workspaces: of 73 product files that parse JSON,
**17 contain no error handling of any kind**. Two read as:

    const stored = getLocalStorage().getItem('tasks');
    return stored ? JSON.parse(stored) : [];

The ternary guards `null` - the case that cannot happen twice - and not the
case that can. When storage holds something that is not JSON, load throws,
and a page whose whole state comes from that call renders nothing.

Raised as an open item by the session that ran on the other machine, against
run 9f14d645's `task-manager/app.js`, which does the same thing with a
comment explaining why it is safe.

Deliberately whole-file: a file that handles an error anywhere is left alone.
The question is whether failure was considered, and answering it per call
site needs the enclosing block, which no regex gets right across six
languages. It under-reports on purpose.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.integration_checks import (
    _persisted_data_parsed_without_a_guard,
    _source_files,
)

BARE = """\
export function loadTasks() {
    const stored = localStorage.getItem('tasks');
    return stored ? JSON.parse(stored) : [];
}
"""

GUARDED = """\
export function loadTasks() {
    try {
        const stored = localStorage.getItem('tasks');
        return stored ? JSON.parse(stored) : [];
    } catch (error) {
        return [];
    }
}
"""


def _project(root: Path, **files: str) -> list[Path]:
    for name, text in files.items():
        path = root / name.replace("__", ".")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return _source_files(root)


def test_the_bare_parse_is_reported(tmp_path: Path):
    files = _project(tmp_path, app__js=BARE)

    problems = _persisted_data_parsed_without_a_guard(files, tmp_path)

    assert len(problems) == 1
    assert "app.js" in problems[0]
    assert "line 3" in problems[0], "name where it is"
    assert "null is the case that cannot happen twice" in problems[0]


def test_a_guarded_parse_is_silent(tmp_path: Path):
    files = _project(tmp_path, app__js=GUARDED)

    assert _persisted_data_parsed_without_a_guard(files, tmp_path) == []


def test_error_handling_anywhere_in_the_file_is_enough(tmp_path: Path):
    """Deliberate under-reporting: the question is whether failure was met."""
    files = _project(tmp_path, app__js=BARE + "\nfunction save() { try { x() } catch (e) {} }\n")

    assert _persisted_data_parsed_without_a_guard(files, tmp_path) == []


def test_parsing_something_that_is_not_stored_is_not_this(tmp_path: Path):
    """A literal, or a response the code already owns, is not the risk."""
    files = _project(
        tmp_path, app__js="const config = JSON.parse('{\"a\": 1}');\nexport default config;\n"
    )

    assert _persisted_data_parsed_without_a_guard(files, tmp_path) == []


def test_reading_storage_without_parsing_is_not_this(tmp_path: Path):
    files = _project(tmp_path, app__js="export const name = localStorage.getItem('name');\n")

    assert _persisted_data_parsed_without_a_guard(files, tmp_path) == []


def test_a_test_file_is_not_the_product(tmp_path: Path):
    """The suite may do what it likes with storage; it is not what ships."""
    files = _project(tmp_path, app__test__js=BARE, app__js="export const a = 1;\n")

    assert _persisted_data_parsed_without_a_guard(files, tmp_path) == []


@pytest.mark.parametrize(
    "name, text",
    [
        ("app__py", "import json\ndef load():\n    return json.loads(open('t.json', 'r').read())\n"),
        ("app__js", "const d = readFileSync('t.json');\nexport const t = JSON.parse(d);\n"),
    ],
)
def test_it_reads_more_than_one_language(tmp_path: Path, name: str, text: str):
    files = _project(tmp_path, **{name: text})

    assert _persisted_data_parsed_without_a_guard(files, tmp_path) != []


def test_python_error_handling_counts_too(tmp_path: Path):
    files = _project(
        tmp_path,
        app__py=(
            "import json\n"
            "def load():\n"
            "    try:\n"
            "        return json.loads(open('t.json', 'r').read())\n"
            "    except ValueError:\n"
            "        return []\n"
        ),
    )

    assert _persisted_data_parsed_without_a_guard(files, tmp_path) == []


def test_the_finding_is_not_graded_as_breaking(tmp_path: Path):
    """The product works. It works until its storage is damaged."""
    from app.analysis.integration_checks import _severity_of

    files = _project(tmp_path, app__js=BARE)
    problem = _persisted_data_parsed_without_a_guard(files, tmp_path)[0]

    assert _severity_of(problem) == "untidy"


def test_it_is_registered(tmp_path: Path):
    """A check the summary never calls is a check that does not exist."""
    from app.analysis.integration_checks import _CHECKS

    assert any("stored data" in name for name, _ in _CHECKS)
