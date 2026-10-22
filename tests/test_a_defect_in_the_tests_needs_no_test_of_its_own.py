"""A defect that lies only in tests or throwaway scripts needs no regression test.

A regression test proves a change to the product. Measured on one run, whose
last sprint spent four rounds on a debugging script and the tests written
about it:

    defect_fix_1_5  repaired play_debug_e2e.js, and - told it MUST add a
                    regression test - wrote debug_e2e_innerhtml_regression.test.js
    defect_fix_2_6  repaired play_debug_e2e.js again, wrote
                    play_debug_e2e_regression.test.js
    test_round_2    both suites pass; reports that the new suite asserts nothing
    defect_fix_3_7  wrote play_debug_e2e_regression_test_has_expect.test.js,
                    which reads the suite before it and checks it says `expect`

Every round was on the probes, none on the product.
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from app.agents.specialists import build_defect_fix_request
from app.analysis.file_kinds import is_scratch
from app.analysis.integration_checks import _scratch_scripts_left_behind
from app.graph.workflow import _a_round_that_found_a_product_defect, _needs_a_regression_test


def _reported(*files: str, required: bool = True):
    return types.SimpleNamespace(affected_files=list(files), regression_test_required=required)


# --- what counts as a throwaway --------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "app/play_debug_e2e.js",
        "app/run_debug_console.js",
        "app/tmp_get_tasks.js",
        "app/temp_open_file.js",
        "app/src/temp_count.js.probe",
        "app/check-debug2.mjs",
        "app/debug.js",
        "tool/tmp_check.py",
    ],
)
def test_a_name_that_says_it_is_thrown_away(path: str) -> None:
    assert is_scratch(path)


@pytest.mark.parametrize(
    "path",
    ["app/src/ui.js", "app/debugger.js", "app/src/debugPanel.js", "app/storage.test.js", ""],
)
def test_a_name_that_does_not(path: str) -> None:
    assert not is_scratch(path)


def test_the_leftover_report_finds_a_debug_segment_anywhere(tmp_path: Path) -> None:
    """Only the prefixed names were recognised, so `play_debug_e2e.js` and
    `run_debug_console.js` stayed in the product unreported."""
    project = tmp_path / "app"
    project.mkdir()
    for name in ("play_debug_e2e.js", "run_debug_console.js", "app.js"):
        (project / name).write_text("console.log(1);\n", encoding="utf-8")
    files = [path for path in project.iterdir()]

    report = " ".join(_scratch_scripts_left_behind(files, tmp_path))

    assert "play_debug_e2e.js" in report and "run_debug_console.js" in report
    assert "app/app.js" not in report


# --- the requirement --------------------------------------------------------


def test_a_defect_in_a_test_needs_no_regression_test() -> None:
    assert not _needs_a_regression_test(
        _reported("app/src/__tests__/play_debug_e2e_regression.test.js")
    )


def test_a_defect_in_a_debugging_script_needs_none_either() -> None:
    assert not _needs_a_regression_test(_reported("app/play_debug_e2e.js"))


def test_a_defect_that_touches_the_product_still_does() -> None:
    assert _needs_a_regression_test(_reported("app/src/storage.js", "app/src/storage.test.js"))


def test_an_unlocated_defect_still_does() -> None:
    """Not knowing where it is is not knowing it is only the tests."""
    assert _needs_a_regression_test(_reported())


def test_the_reporter_saying_none_is_needed_is_kept() -> None:
    assert not _needs_a_regression_test(_reported("app/src/storage.js", required=False))


def test_a_round_that_found_only_a_debugging_script_spends_no_budget() -> None:
    defects = [_reported("app/play_debug_e2e.js"), _reported("app/src/a.test.js")]

    assert not _a_round_that_found_a_product_defect(defects)
    assert _a_round_that_found_a_product_defect([*defects, _reported("app/src/ui.js")])


# --- what the fix stage is told ----------------------------------------------


def _brief(files: list[str], required: bool) -> str:
    request = build_defect_fix_request(
        "Test lacks assertions", "npm test", "it asserts", "it does not", files, required, "/"
    )
    return request["messages"][0]["content"]


def test_a_debugging_script_is_to_be_deleted_not_repaired() -> None:
    brief = _brief(["app/play_debug_e2e.js"], False)

    assert "'app/play_debug_e2e.js' is named like a debugging script" in brief
    assert "`delete_artifact`" in brief
    assert "MUST also add" not in brief


def test_a_defect_in_a_test_is_fixed_in_that_test() -> None:
    brief = _brief(["app/src/__tests__/x_regression.test.js"], False)

    assert "Do not write another test about it" in brief
    assert "delete_artifact" not in brief


def test_a_product_defect_keeps_its_requirement() -> None:
    assert "MUST also add or update a regression test" in _brief(["app/src/ui.js"], True)


def test_a_product_defect_the_reporter_excused_reads_as_before() -> None:
    brief = _brief(["app/src/ui.js"], False)

    assert "A regression test is not required for this defect" in brief
