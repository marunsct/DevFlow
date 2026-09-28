"""Clickable controls carrying a `data-*` handle nothing in any script reads.

`_a_page_no_script_ever_touches` asks whether a page is wired at all, and says
so in its own docstring: it "requires that nothing touches the document
anywhere". A page wired for most of itself and dead in one corner is outside it
by design. This is that corner.

Run b0db10b1 shipped one. Its `index.html` carries

    <nav id="filter-buttons" aria-label="Filter tasks by status">
      <button data-filter="all" class="filter-btn active">All</button>
      <button data-filter="active" class="filter-btn">Active</button>
      <button data-filter="completed" class="filter-btn">Completed</button>

styled in `style.css`, and no script in the product mentions `data-filter`,
`filter-btn` or `filter-buttons`. The only `filter` in its JavaScript is
`tasks.filter(t => t.id !== taskId)` inside `deleteTask`. Tasks render, toggle
and delete; the three buttons respond to hover and do nothing.

"Filter functionality works correctly" is one of that brief's four acceptance
criteria. The milestone review found it and rated it Minor.
"""

from __future__ import annotations

import pytest

from app.analysis.integration_checks import (
    _a_control_group_no_script_operates,
    _source_files,
)

WIRED = """
document.getElementById('task-list').addEventListener('click', () => {});
"""


def _problems(root):
    return _a_control_group_no_script_operates(_source_files(root), root)


def _page(controls: str, nav_id: str | None = None) -> str:
    """A page wired for its task list, with `controls` beside it.

    `nav_id` wraps the controls in a properly closed container, because an
    unclosed tag is not a container and the check is right to say so.
    """
    body = controls
    if nav_id:
        body = f'<nav id="{nav_id}">\n{controls}</nav>\n'
    return (
        "<!doctype html><html><body>\n"
        '<ul id="task-list"></ul>\n'
        f"{body}"
        '<script src="app.js"></script>\n'
        "</body></html>\n"
    )


@pytest.fixture
def site(tmp_path):
    (tmp_path / "app.js").write_text(WIRED)
    return tmp_path


BUTTONS = (
    '<button data-filter="all" class="filter-btn">All</button>\n'
    '<button data-filter="active" class="filter-btn">Active</button>\n'
    '<button data-filter="completed" class="filter-btn">Completed</button>\n'
)


def test_the_dead_filter_group_that_shipped(site):
    (site / "index.html").write_text(
        _page(BUTTONS, nav_id="filter-buttons")
    )

    problems = _problems(site)

    assert len(problems) == 1, problems
    assert "3 clickable controls" in problems[0]
    assert "data-filter" in problems[0]


def test_a_script_reading_the_attribute_is_wiring(site):
    (site / "app.js").write_text(
        WIRED + "document.querySelectorAll('[data-filter]').forEach(b => b);\n"
    )
    (site / "index.html").write_text(_page(BUTTONS))
    assert _problems(site) == []


def test_a_script_reading_the_dataset_is_wiring(site):
    (site / "app.js").write_text(WIRED + "const which = btn.dataset.filter;\n")
    (site / "index.html").write_text(_page(BUTTONS))
    assert _problems(site) == []


def test_wiring_by_class_counts(site):
    (site / "app.js").write_text(
        WIRED + "document.querySelectorAll('.filter-btn').forEach(b => b);\n"
    )
    (site / "index.html").write_text(_page(BUTTONS))
    assert _problems(site) == []


def test_delegation_on_the_enclosing_container_counts(site):
    (site / "app.js").write_text(
        WIRED + "document.getElementById('filter-buttons').addEventListener('click', f);\n"
    )
    (site / "index.html").write_text(
        _page(BUTTONS, nav_id="filter-buttons")
    )
    assert _problems(site) == []


def test_an_inline_script_counts_as_wiring(tmp_path):
    (tmp_path / "app.js").write_text(WIRED)
    (tmp_path / "index.html").write_text(
        "<!doctype html><html><body>\n"
        '<ul id="task-list"></ul>\n' + BUTTONS +
        '<script type="module">\n'
        "document.querySelectorAll('[data-filter]').forEach(b => b);\n"
        "</script></body></html>\n"
    )
    assert _problems(tmp_path) == []


class TestWhatDoesNotCount:
    def test_a_suite_locating_the_control_is_not_an_alibi(self, site):
        """The exact shape that hid one run's dead buttons.

        `app.pw.spec.ts` holds `filterNav.locator('[data-filter="all"]')` for
        three buttons the product never wires. Reading a test as wiring lets a
        dead control take its alibi from the suite that should have caught it.
        """
        (site / "app.pw.spec.ts").write_text(
            "import { test } from '@playwright/test';\n"
            "test('filters', async ({ page }) => {\n"
            "  const nav = page.locator('#filter-buttons');\n"
            "  await nav.locator('[data-filter=\"all\"]').click();\n"
            "});\n"
        )
        (site / "index.html").write_text(
            _page(BUTTONS, nav_id="filter-buttons")
        )

        problems = _problems(site)

        assert len(problems) == 1, "a test vouched for an unwired control"

    def test_a_builtin_of_the_same_name_is_not_wiring(self, site):
        """`tasks.filter(...)` is `Array.prototype.filter`, not the feature."""
        (site / "app.js").write_text(
            WIRED + "function deleteTask(id, tasks) "
            "{ return tasks.filter(t => t.id !== id); }\n"
        )
        (site / "index.html").write_text(_page(BUTTONS))

        assert len(_problems(site)) == 1

    def test_a_single_control_is_not_a_group(self, site):
        (site / "index.html").write_text(
            _page('<button data-role="x" class="one">One</button>\n')
        )
        assert _problems(site) == []

    def test_a_page_nothing_wires_at_all_is_left_to_the_other_check(self, tmp_path):
        """Reporting the same page twice in different words helps nobody."""
        (tmp_path / "app.js").write_text("export const x = 1;\n")
        (tmp_path / "index.html").write_text(_page(BUTTONS))
        assert _problems(tmp_path) == []
