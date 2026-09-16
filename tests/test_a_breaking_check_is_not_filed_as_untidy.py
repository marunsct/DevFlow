"""A check that finds a broken product must be graded as one.

`_severity_of` decides between BREAKS and untidy by matching a phrase from the
message against `_BREAKS_BEHAVIOUR`. A new check whose message matches no
marker is graded untidy, silently - the reviewer is handed "untidy rather than
broken - dead rules, unused files. Worth a minor finding, not a blocking one"
over a suite that never runs, or a page that throws on load.

That happened: all three checks added for run d6297b2f's failures landed in
the untidy bucket the day they were written, and the summary invited the
milestone reviewer to wave them through. These are the cases, pinned.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.integration_checks import (
    _commonjs_loaded_as_a_module,
    _files_that_contradict_the_declared_module_type,
    _severity_of,
    _tests_that_cannot_fail,
)

STRANDED = (
    "import assert from 'assert';\n"
    "export default function (t) {\n"
    "  t.test('addTask adds a task', () => { assert.ok(1); });\n"
    "}\n"
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    directory = tmp_path / "app"
    directory.mkdir()
    return directory


def test_a_suite_the_runner_never_calls_blocks(project: Path):
    (project / "app.test.mjs").write_text(STRANDED, encoding="utf-8")

    problems = _tests_that_cannot_fail(
        [project / "app.test.mjs"], project.parent
    )

    assert problems
    assert all(_severity_of(problem) == "BREAKS" for problem in problems)


def test_commonjs_behind_a_module_tag_blocks(project: Path):
    (project / "index.html").write_text(
        '<script type="module" src="a.js"></script>', encoding="utf-8"
    )
    (project / "a.js").write_text("module.exports = {};\n", encoding="utf-8")

    problems = _commonjs_loaded_as_a_module([project / "index.html"], project.parent)

    assert problems
    assert all(_severity_of(problem) == "BREAKS" for problem in problems)


def test_a_file_contradicting_the_declared_module_type_blocks(project: Path):
    (project / "package.json").write_text(
        '{"name":"p","type":"module"}', encoding="utf-8"
    )
    (project / "b.js").write_text("const x = require('y');\n", encoding="utf-8")

    problems = _files_that_contradict_the_declared_module_type(
        [project / "package.json", project / "b.js"], project.parent
    )

    assert problems
    assert all(_severity_of(problem) == "BREAKS" for problem in problems)


def test_every_marker_is_a_phrase_some_message_really_emits():
    """A marker matching nothing grades its own check untidy for ever.

    The comment on `_BREAKS_BEHAVIOUR` says each phrase is taken from a message
    this module actually emits rather than guessed at. This is that claim,
    checked.

    Two things make a naive source search wrong, and both are real here. The
    messages are built from adjacent string literals, so a phrase that spans
    the seam - "which does " "not exist in the workspace." - matches at runtime
    and never appears contiguously in the file; the seams are joined first.
    And several of the checks these markers grade live in `test_discovery`,
    not here, so both modules are searched.
    """
    import inspect
    import re

    from app.analysis import integration_checks, test_discovery

    source = inspect.getsource(integration_checks) + inspect.getsource(test_discovery)
    # Join adjacent string literals the way Python does before comparing.
    joined = re.sub(r'"\s*\n\s*"', "", source)

    # Each marker appears once in the list itself; a marker that is really
    # emitted appears at least twice.
    for marker in integration_checks._BREAKS_BEHAVIOUR:
        assert joined.count(marker) >= 2, f"no message emits {marker!r}"
