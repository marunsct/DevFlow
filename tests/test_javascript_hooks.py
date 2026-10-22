"""The ids and data attributes a script reaches for, against what pages declare.

One run is the first run of this harness to reach `complete`. It shipped a
to-do app that could not add a task and rendered nothing:

    app.js:    document.getElementById("task-form")
    index.html: <form id="add-task-form">

    app.js:    filterBtn.dataset.status
    index.html: <button id="filter-all" class="filter-button">

`getElementById` returns null, the `if (!form) return;` around it swallows that,
and `dataset.status` is `undefined`. Nothing throws. The architecture review,
the security review, three passing tests and the milestone review all accepted
it, because the tests exercised `addTask` and `loadTasks` directly and nothing
exercised the two files together.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.integration_checks import _hooks_javascript_reaches_for, _source_files


def _findings(tmp_path: Path, files: dict[str, str]) -> list[str]:
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return _hooks_javascript_reaches_for(_source_files(tmp_path), tmp_path)


MEASURED_PAGE_HTML = """<!DOCTYPE html>
<html><body>
<form id="add-task-form"><input id="task-title"></form>
<div id="filters">
  <button id="filter-all" class="filter-button">All</button>
</div>
<ul id="task-list"></ul>
<script type="module" src="./app.js"></script>
</body></html>
"""


def test_an_id_no_page_declares_is_reported(tmp_path: Path) -> None:
    findings = _findings(
        tmp_path,
        {
            "app/index.html": MEASURED_PAGE_HTML,
            "app/app.js": 'const form = document.getElementById("task-form");\n',
        },
    )

    assert any("task-form" in f for f in findings)


def test_a_data_attribute_no_element_sets_is_reported(tmp_path: Path) -> None:
    findings = _findings(
        tmp_path,
        {
            "app/index.html": MEASURED_PAGE_HTML,
            "app/app.js": "const s = btn.dataset.status;\n",
        },
    )

    assert any("data-status" in f for f in findings)


def test_an_id_the_page_declares_is_fine(tmp_path: Path) -> None:
    findings = _findings(
        tmp_path,
        {
            "app/index.html": MEASURED_PAGE_HTML,
            "app/app.js": (
                'document.getElementById("add-task-form");\n'
                'document.getElementById("task-list");\n'
                'document.querySelector("#filter-all");\n'
            ),
        },
    )

    assert findings == []


def test_an_id_the_script_creates_is_fine(tmp_path: Path) -> None:
    """A script that builds an element and names it does not need a page to."""
    findings = _findings(
        tmp_path,
        {
            "app/index.html": MEASURED_PAGE_HTML,
            "app/app.js": (
                'const el = document.createElement("div");\n'
                'el.id = "toast";\n'
                'document.getElementById("toast").textContent = "hi";\n'
            ),
        },
    )

    assert findings == []


def test_a_data_attribute_the_script_sets_is_fine(tmp_path: Path) -> None:
    findings = _findings(
        tmp_path,
        {
            "app/index.html": MEASURED_PAGE_HTML,
            "app/app.js": "btn.dataset.taskId = task.id;\nconst id = btn.dataset.taskId;\n",
        },
    )

    assert findings == []


def test_a_camel_case_dataset_name_maps_to_its_attribute(tmp_path: Path) -> None:
    """`dataset.taskId` reads `data-task-id`; that is the platform's rule."""
    findings = _findings(
        tmp_path,
        {
            "app/index.html": '<div id="a" data-task-id="1"></div>',
            "app/app.js": "const id = el.dataset.taskId;\n",
        },
    )

    assert findings == []


def test_a_project_with_no_html_ids_is_left_alone(tmp_path: Path) -> None:
    """React and Vue build their DOM from templates this cannot read, and a
    script-only page declares its own ids as it goes. Flagging either is noise.
    """
    findings = _findings(
        tmp_path,
        {
            "app/index.html": '<div class="root"></div><script src="./app.js"></script>',
            "app/app.js": 'document.getElementById("anything");\n',
        },
    )

    assert findings == []


def test_a_test_file_is_not_judged(tmp_path: Path) -> None:
    """A test may name an id it is about to create in a fixture."""
    findings = _findings(
        tmp_path,
        {
            "app/index.html": MEASURED_PAGE_HTML,
            "app/app.test.mjs": 'document.getElementById("fixture-root");\n',
        },
    )

    assert findings == []


def test_a_root_relative_script_src_is_resolved_against_the_project(tmp_path):
    """`Path("proj") / "/src/main.jsx"` is `/src/main.jsx` - pathlib drops the left.

    Every root-relative reference therefore resolved outside the workspace and
    was reported missing. That is Vite's own convention for an entry point, so
    a React or Vue product tripped a blocking finding on its first file -
    which is what `tests/brief_medium.md` invites, naming React or Vue.js in
    its constraints.
    """
    from app.analysis.integration_checks import summarise_integration

    project = tmp_path / "dashboard"
    (project / "src").mkdir(parents=True)
    (project / "index.html").write_text(
        '<!DOCTYPE html><div id="root"></div>'
        '<script type="module" src="/src/main.jsx"></script>',
        encoding="utf-8",
    )
    (project / "src" / "main.jsx").write_text(
        "import { createRoot } from 'react-dom/client';\n"
        "createRoot(document.getElementById('root')).render(null);\n",
        encoding="utf-8",
    )

    assert "does not exist in the workspace" not in summarise_integration(str(tmp_path))


def test_a_root_relative_reference_to_nothing_is_still_reported(tmp_path):
    from app.analysis.integration_checks import summarise_integration

    project = tmp_path / "dashboard"
    project.mkdir()
    (project / "index.html").write_text(
        '<!DOCTYPE html><script type="module" src="/src/main.jsx"></script>',
        encoding="utf-8",
    )

    assert "does not exist in the workspace" in summarise_integration(str(tmp_path))
