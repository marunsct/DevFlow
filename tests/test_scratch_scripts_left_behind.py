"""Throwaway debugging scripts still sitting in the product.

A stage that cannot see why a test fails writes a small script, runs it, and
learns something. That is good practice and this does not discourage it - what
it reports is the ones never cleaned up.

One run's `defect_fix_2_1` left twelve: `tmp_debug2.mjs` through
`tmp_debug6.mjs`, `tmp_full_test.mjs`, `tmp_run_test.mjs`, `tmp_print_tnew.mjs`
and more, beside an application of three files. Across the stored workspaces,
seven of fifty-five carry them.

They are not harmless. Four of that run's twelve end in `_test.mjs`, one of the
patterns `node --test` collects, so they became part of the suite the gates
read - and the stranded-tests finding listed them under "name them too", which
is the wrong instruction for a file whose place is the bin.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.integration_checks import (
    _scratch_scripts_left_behind as leftovers,
    _severity_of,
)


@pytest.fixture
def build(tmp_path: Path):
    def make(names: list[str]) -> tuple[list[Path], Path]:
        project = tmp_path / "app"
        for name in names:
            path = project / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("console.log('x');\n", encoding="utf-8")
        return [p for p in project.rglob("*") if p.is_file()], tmp_path

    return make


@pytest.mark.parametrize(
    "name",
    [
        "tmp_debug2.mjs",
        "tmp_test.mjs",
        "temp-check.mjs",
        "debug.js",
        "scratch.mjs",
        "test_debug.mjs",
        "app_debug3.js",
    ],
)
def test_a_scratch_name_is_reported(build, name: str):
    files, root = build([name])

    assert len(leftovers(files, root)) == 1


@pytest.mark.parametrize("name", ["app.js", "index.js", "app.test.mjs", "storage.mjs"])
def test_a_product_file_is_not(build, name: str):
    files, root = build([name])

    assert leftovers(files, root) == []


def test_a_deliberate_utility_directory_is_exempt(build):
    """Run cbd22a3's `tools/debug-linecount.mjs` counts the product's lines
    against the brief's 500-line cap - a utility the project meant to keep."""
    files, root = build(["tools/debug-linecount.mjs", "scripts/debug-run.mjs"])

    assert leftovers(files, root) == []


def test_it_is_untidy_rather_than_breaking(build):
    """Clutter, not a broken product - the reviewer should not block on it."""
    files, root = build(["tmp_debug.mjs"])

    assert _severity_of(leftovers(files, root)[0]) == "untidy"


def test_it_says_writing_one_was_fine(build):
    """The message must not discourage the practice, only the leftovers."""
    files, root = build(["tmp_debug.mjs"])

    note = leftovers(files, root)[0]
    assert "is the right move" in note
    assert "Delete the ones that have served their purpose" in note


def test_many_are_summarised_rather_than_all_listed(build):
    files, root = build([f"tmp_debug{i}.mjs" for i in range(9)])

    assert "and 3 more" in leftovers(files, root)[0]


def test_a_scratch_file_is_not_listed_as_a_stranded_test(tmp_path: Path):
    """"Name them too" is the opposite instruction for a file to be deleted."""
    from app.analysis.integration_checks import summarise_integration

    project = tmp_path / "app"
    project.mkdir()
    (project / "package.json").write_text(
        '{"name":"p","scripts":{"test":"node --test app.test.mjs"}}', encoding="utf-8"
    )
    (project / "app.test.mjs").write_text(
        "import { test } from 'node:test';\ntest('x', () => {});\n", encoding="utf-8"
    )
    (project / "tmp_debug_test.mjs").write_text("console.log('x');\n", encoding="utf-8")

    report = summarise_integration(str(tmp_path))

    if "Stranded:" in report:
        stranded = report.split("Stranded:", 1)[1].split(".")[0]
        assert "tmp_debug_test" not in stranded


def test_a_scratch_script_is_not_also_reported_as_an_orphan(tmp_path: Path):
    """"Nothing runs it" is the definition of a throwaway, not a finding.

    One run's report ran to 14 findings of which 10 were about its own
    temp files - four real problems buried in a list three times their length.
    """
    from app.analysis.integration_checks import summarise_integration

    project = tmp_path / "app"
    project.mkdir()
    (project / "index.html").write_text(
        '<!DOCTYPE html><script type="module" src="app.js"></script>', encoding="utf-8"
    )
    (project / "app.js").write_text(
        "document.title = 'x';\nexport const a = 1;\n", encoding="utf-8"
    )
    (project / "tmp_debug.mjs").write_text("console.log('probe');\n", encoding="utf-8")

    report = summarise_integration(str(tmp_path))

    assert "tmp_debug.mjs is never loaded" not in report
    assert "look like debugging scripts left behind" in report


def test_a_real_module_nothing_loads_is_still_an_orphan(tmp_path: Path):
    from app.analysis.integration_checks import summarise_integration

    project = tmp_path / "app"
    project.mkdir()
    (project / "index.html").write_text("<!DOCTYPE html><p>hi</p>", encoding="utf-8")
    (project / "helpers.js").write_text("export const a = 1;\n", encoding="utf-8")

    assert "helpers.js is never loaded" in summarise_integration(str(tmp_path))


def test_a_scratch_script_is_not_reported_against_the_module_type(tmp_path: Path):
    """Its remedy is deletion, not conversion to ESM."""
    from app.analysis.integration_checks import (
        _files_that_contradict_the_declared_module_type as contradictions,
    )

    project = tmp_path / "app"
    project.mkdir()
    (project / "package.json").write_text('{"name":"p","type":"module"}', encoding="utf-8")
    (project / "tmp_debug.js").write_text("const fs = require('fs');\n", encoding="utf-8")

    files = [p for p in project.rglob("*") if p.is_file()]

    assert contradictions(files, tmp_path) == []
