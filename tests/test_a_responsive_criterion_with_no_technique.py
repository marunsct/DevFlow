"""The one acceptance criterion nothing was checking, in either direction.

`_responsive_css_the_page_cannot_use` asks whether an existing `@media` block
can apply. Nothing asked whether the product does anything responsive at all,
so "Responsive design for mobile and desktop" - one of the four acceptance
criteria in the brief these runs are given - could be satisfied on paper by a
stylesheet that renders at one width and is scrolled sideways on a phone.

Breakpoints are not the only technique, and this is the failure mode to avoid:
One run's stylesheet has no `@media` in it and is fluid throughout, built
from `clamp()`, `min()` and viewport units. A check that demanded `@media`
would have filed a blocking finding against the best product this harness has
produced.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.integration_checks import (
    _a_responsive_criterion_nothing_implements,
    _source_files,
)

BRIEF = """# Product Brief

## Acceptance Criteria
- Responsive design for mobile and desktop
"""

PAGE = """<!doctype html>
<html><head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="style.css">
</head><body><div class="app"></div>
<script type="module" src="app.js"></script></body></html>
"""

FIXED = """
.app { width: 960px; margin: 0 auto; padding: 24px; }
h1 { font-size: 32px; }
"""


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text(PAGE, encoding="utf-8")
    (tmp_path / "style.css").write_text(FIXED, encoding="utf-8")
    (tmp_path / "app.js").write_text("export const V = 1;", encoding="utf-8")
    return tmp_path


def _run(root: Path, brief: str = BRIEF) -> list[str]:
    return _a_responsive_criterion_nothing_implements(_source_files(root), root, brief)


def test_a_fixed_width_product_is_reported(workspace: Path) -> None:
    problems = _run(workspace)

    assert len(problems) == 1, problems
    assert "answers to the width" in problems[0]


def test_a_breakpoint_satisfies_it(workspace: Path) -> None:
    (workspace / "style.css").write_text(
        FIXED + "@media (max-width: 600px) { .app { width: 100%; } }", encoding="utf-8"
    )

    assert _run(workspace) == []


def test_fluid_units_satisfy_it_without_any_breakpoint(workspace: Path) -> None:
    """Run-d483f554's shape. A check that demanded `@media` would have called
    the best product this harness has built broken."""
    (workspace / "style.css").write_text(
        ".app { max-width: min(48rem, 100%); padding: clamp(0.5rem, 3vw, 1.5rem); }",
        encoding="utf-8",
    )

    assert _run(workspace) == []


def test_a_wrapping_flex_row_satisfies_it(workspace: Path) -> None:
    (workspace / "style.css").write_text(
        ".row { display: flex; flex-wrap: wrap; }", encoding="utf-8"
    )

    assert _run(workspace) == []


def test_a_responsive_grid_satisfies_it(workspace: Path) -> None:
    (workspace / "style.css").write_text(
        ".grid { grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr)); }",
        encoding="utf-8",
    )

    assert _run(workspace) == []


def test_a_container_query_satisfies_it(workspace: Path) -> None:
    (workspace / "style.css").write_text(
        "@container (min-width: 20rem) { .app { display: grid; } }", encoding="utf-8"
    )

    assert _run(workspace) == []


def test_styles_inside_the_page_are_read_too(workspace: Path) -> None:
    (workspace / "style.css").unlink()
    (workspace / "index.html").write_text(
        PAGE.replace(
            '<link rel="stylesheet" href="style.css">',
            "<style>.app { padding: clamp(1rem, 4vw, 3rem); }</style>",
        ),
        encoding="utf-8",
    )

    assert _run(workspace) == []


def test_a_project_never_asked_to_be_responsive_is_silent(workspace: Path) -> None:
    assert _run(workspace, brief="# Brief\n\n- A command line tool\n") == []


def test_the_projects_own_documents_can_ask_for_it(workspace: Path) -> None:
    """Either place may be where it is stated."""
    (workspace / "docs").mkdir()
    (workspace / "docs" / "product_intake.md").write_text(
        "## Acceptance Criteria\n- The layout is responsive\n", encoding="utf-8"
    )

    assert len(_run(workspace, brief="")) == 1


def test_a_missing_viewport_tag_is_named_as_well(workspace: Path) -> None:
    (workspace / "index.html").write_text(
        PAGE.replace('<meta name="viewport" content="width=device-width, initial-scale=1">', ""),
        encoding="utf-8",
    )

    assert "viewport" in _run(workspace)[0]


def test_a_product_with_no_styles_at_all_is_left_alone(workspace: Path) -> None:
    """A different finding, and the size report already says what is there."""
    (workspace / "style.css").unlink()

    assert _run(workspace) == []
