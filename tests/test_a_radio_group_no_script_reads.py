"""A filter bar built from radios is a control group like any other.

`_CLICKABLE_WITH_DATA` requires a `data-*` attribute, so it sees
`<button data-filter="all">` and not `<input type="radio" name="filter">`.
Run-b0db10b1's dead filter bar was caught only because that run happened to
choose the first spelling; run-3c8e772e chose the second, and wired it, so
nothing was lost - but nothing would have reported it either.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.integration_checks import (
    _a_control_group_no_script_operates,
    _source_files,
)

PAGE = """<!doctype html>
<html><body>
  <form id="new-task"><input id="title"><button type="submit">Add</button></form>
  <section class="filter-bar" aria-label="Filter tasks">
    <label><input type="radio" name="filter" value="all" checked> All</label>
    <label><input type="radio" name="filter" value="active"> Active</label>
    <label><input type="radio" name="filter" value="completed"> Completed</label>
  </section>
  <ul id="task-list"></ul>
  <script type="module" src="app.js"></script>
</body></html>
"""

#: Wires the form and nothing else - the shape that makes this a partial
#: failure rather than a page nothing touches.
WIRED_ELSEWHERE = """
document.getElementById('new-task').addEventListener('submit', (e) => {
  e.preventDefault();
  document.getElementById('task-list').textContent = 'a task';
});
"""


def _workspace(tmp_path: Path, script: str, page: str = PAGE) -> Path:
    (tmp_path / "index.html").write_text(page, encoding="utf-8")
    (tmp_path / "app.js").write_text(script, encoding="utf-8")
    return tmp_path


def _run(root: Path) -> list[str]:
    return _a_control_group_no_script_operates(_source_files(root), root)


def test_a_radio_group_nothing_reads_is_reported(tmp_path) -> None:
    root = _workspace(tmp_path, WIRED_ELSEWHERE)

    problems = _run(root)

    assert len(problems) == 1, problems
    assert "`filter` group" in problems[0]
    assert "3 inputs" in problems[0]


def test_a_group_read_by_name_is_left_alone(tmp_path) -> None:
    root = _workspace(
        tmp_path,
        WIRED_ELSEWHERE
        + "document.querySelectorAll('input[name=\"filter\"]').forEach(r => "
          "r.addEventListener('change', () => render(r.value)));",
    )

    assert _run(root) == []


def test_getElementsByName_counts_as_wiring(tmp_path) -> None:
    root = _workspace(
        tmp_path,
        WIRED_ELSEWHERE + "for (const r of document.getElementsByName('filter')) {}",
    )

    assert _run(root) == []


def test_a_group_reached_through_its_container_is_left_alone(tmp_path) -> None:
    """`.filter-bar input` is the ordinary way to wire these, and the inputs
    themselves carry no class at all."""
    root = _workspace(
        tmp_path,
        WIRED_ELSEWHERE
        + "document.querySelector('.filter-bar').addEventListener('change', () => {});",
    )

    assert _run(root) == []


def test_the_array_method_is_not_evidence(tmp_path) -> None:
    """`tasks.filter(t => ...)` is `Array.prototype.filter`. Reading a bare
    group name as wiring is how this file's first version vouched for three
    dead buttons."""
    root = _workspace(
        tmp_path,
        WIRED_ELSEWHERE + "const open = tasks.filter(t => !t.done);",
    )

    assert len(_run(root)) == 1


def test_a_single_control_is_not_a_group(tmp_path) -> None:
    page = PAGE.replace(
        '<label><input type="radio" name="filter" value="active"> Active</label>', ""
    ).replace(
        '<label><input type="radio" name="filter" value="completed"> Completed</label>', ""
    )
    root = _workspace(tmp_path, WIRED_ELSEWHERE, page)

    assert _run(root) == []


def test_a_checkbox_group_counts_too(tmp_path) -> None:
    page = PAGE.replace('type="radio"', 'type="checkbox"')
    root = _workspace(tmp_path, WIRED_ELSEWHERE, page)

    assert len(_run(root)) == 1


def test_the_attribute_order_does_not_matter(tmp_path) -> None:
    page = PAGE.replace(
        '<input type="radio" name="filter" value="all" checked>',
        '<input name="filter" value="all" type="radio" checked>',
    )
    root = _workspace(tmp_path, WIRED_ELSEWHERE, page)

    assert len(_run(root)) == 1


def test_a_page_nothing_touches_at_all_is_left_to_the_other_check(tmp_path) -> None:
    """Reporting it twice in different words helps nobody."""
    root = _workspace(tmp_path, "export const VERSION = 1;")

    assert _run(root) == []


def test_buttons_carrying_data_attributes_still_work(tmp_path) -> None:
    """The original shape, unchanged."""
    page = PAGE.replace(
        '<label><input type="radio" name="filter" value="all" checked> All</label>',
        '<button data-filter="all">All</button>',
    ).replace(
        '<label><input type="radio" name="filter" value="active"> Active</label>',
        '<button data-filter="active">Active</button>',
    ).replace(
        '<label><input type="radio" name="filter" value="completed"> Completed</label>',
        '<button data-filter="completed">Completed</button>',
    )
    root = _workspace(tmp_path, WIRED_ELSEWHERE, page)

    problems = _run(root)

    assert len(problems) == 1
    assert "data-filter" in problems[0]
