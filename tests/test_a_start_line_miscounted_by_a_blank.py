"""A range whose end is right and whose start was miscounted is applied.

Reads come back without line numbers, so a model counts them. One run's
`specialist_backend_2` read lines 201-254 of `app.js`, whose line 201 is blank,
and sent `start_line=201` for the comment on line 202, with `end_line=254` and an
`expect_end` naming line 254 correctly. It was refused, re-read the file, and
sent the identical call again.
"""

from __future__ import annotations

import pytest

from app.tools.repository import RepositoryToolError, replace_approved_lines

_FILE = (
    "export function render() {}\n"   # 1
    "\n"                              # 2
    "// -- Initialization --\n"       # 3
    "export function init() {\n"      # 4
    "  render();\n"                   # 5
    "}\n"                             # 6
    "if (ok) {\n"                     # 7
    "  init();\n"                     # 8
    "}\n"                             # 9
)

_NEW = "// -- Initialization --\nexport function init() {\n  render([]);\n}\n"


@pytest.fixture
def project(tmp_path):
    (tmp_path / "app.js").write_text(_FILE, encoding="utf-8")
    return tmp_path


def _read(project) -> str:
    return (project / "app.js").read_text(encoding="utf-8")


def test_a_blank_line_taken_for_none_is_forgiven(project):
    result = replace_approved_lines(
        project, "app.js", 2, 9, _NEW,
        expect_start="// -- Initialization --", expect_end="  init();\n}",
    )

    assert result["status"] == "edited"
    assert _read(project) == "export function render() {}\n\n" + _NEW
    assert "Line 2 was miscounted" in result["detail"]


def test_a_multi_line_expect_end_may_pin_its_first_or_its_last_line(project):
    """Callers send the pin and what follows it, or the range's last lines."""
    from app.tools.repository import _the_lines_expect_end_may_pin

    assert _the_lines_expect_end_may_pin("  init();\n}\n") == ["init();", "}"]
    assert _the_lines_expect_end_may_pin("}") == ["}"]


def test_an_end_that_is_wrong_too_is_still_refused(project):
    with pytest.raises(RepositoryToolError):
        replace_approved_lines(
            project, "app.js", 2, 8, _NEW,
            expect_start="// -- Initialization --", expect_end="}",
        )
    assert _read(project) == _FILE


def test_a_start_too_far_away_is_not_taken_for_a_miscount(project, tmp_path):
    far = "\n" * 10 + _FILE
    (project / "app.js").write_text(far, encoding="utf-8")
    with pytest.raises(RepositoryToolError):
        replace_approved_lines(
            project, "app.js", 1, 19, _NEW,
            expect_start="// -- Initialization --", expect_end="}",
        )
    assert _read(project) == far


def test_an_ambiguous_start_is_refused(project):
    doubled = "// -- Initialization --\n" + _FILE
    (project / "app.js").write_text(doubled, encoding="utf-8")
    with pytest.raises(RepositoryToolError):
        replace_approved_lines(
            project, "app.js", 3, 10, _NEW,
            expect_start="// -- Initialization --", expect_end="}",
        )
    assert _read(project) == doubled
