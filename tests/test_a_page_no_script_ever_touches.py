"""Controls on the page, and nothing anywhere that operates them.

`_page_hooks_that_do_not_exist` asks whether the ids a script reaches for
exist. This asks the other direction, and one run completed on it.

Its final sprint - "Finalize code, documentation, test coverage, and prepare
for deployment" - reduced `app.js` from 6,388 bytes to 2,345 by removing every
line of DOM code: no `getElementById`, no listener, no render, no `init`. What
was left is five pure functions over `localStorage` and an `export`.
`index.html` still carries `add-btn`, `task-input`, `filter-select` and
`task-list`, each referenced zero times.

Every gate passed it. `npm test` reported `# tests 9 # pass 9 # fail 0`,
because the suite imports those five functions directly and never opens the
page, and the cross-file checks reported no problems because each file is
individually fine. The page renders and does nothing at all when used.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.integration_checks import (
    _a_page_no_script_ever_touches as unwired,
    _severity_of,
)

PAGE = """<!DOCTYPE html>
<html><body>
<input id="task-input" />
<button id="add-btn">Add</button>
<select id="filter-select"><option>All</option></select>
<ul id="task-list"></ul>
<script type="module" src="app.js"></script>
</body></html>
"""

#: What one run shipped: data functions, no DOM.
PURE = """const STORAGE_KEY = "tasks";
function getTasks() { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || []; }
function addTask(text) { return { text }; }
export { addTask, getTasks };
"""

WIRED = PURE + """
document.getElementById('add-btn').addEventListener('click', () => addTask('x'));
"""


@pytest.fixture
def build(tmp_path: Path):
    def make(files: dict[str, str]) -> tuple[list[Path], Path]:
        project = tmp_path / "app"
        project.mkdir(exist_ok=True)
        written = []
        for name, content in files.items():
            path = project / name
            path.write_text(content, encoding="utf-8")
            written.append(path)
        return written, tmp_path

    return make


def test_a_page_nothing_operates_is_reported(build):
    files, root = build({"index.html": PAGE, "app.js": PURE})

    problems = unwired(files, root)

    assert len(problems) == 1
    assert "add-btn" in problems[0]


def test_it_blocks_rather_than_reading_as_untidy(build):
    """The product does not work; a reviewer must not wave it through."""
    files, root = build({"index.html": PAGE, "app.js": PURE})

    assert _severity_of(unwired(files, root)[0]) == "BREAKS"


def test_it_says_a_passing_suite_is_not_evidence(build):
    """One run's suite was 9/9 green over this exact product."""
    files, root = build({"index.html": PAGE, "app.js": PURE})

    assert "tests import the functions directly" in unwired(files, root)[0]


def test_a_wired_page_is_left_alone(build):
    files, root = build({"index.html": PAGE, "app.js": WIRED})

    assert unwired(files, root) == []


def test_an_inline_script_counts_as_wiring(build):
    page = PAGE.replace(
        '<script type="module" src="app.js"></script>',
        "<script>document.getElementById('add-btn').onclick = () => {};</script>",
    )
    files, root = build({"index.html": page, "app.js": PURE})

    assert unwired(files, root) == []


def test_a_script_wiring_by_class_is_left_alone(build):
    """Not every page is addressed by id, and this must not force that style."""
    by_class = PURE + "\ndocument.querySelector('.add').addEventListener('click', () => {});\n"
    files, root = build({"index.html": PAGE, "app.js": by_class})

    assert unwired(files, root) == []


def test_a_page_with_no_controls_is_not_a_user_interface(build):
    content_only = "<!DOCTYPE html><html><body><h1>About</h1><p>Text.</p></body></html>"
    files, root = build({"index.html": content_only, "app.js": PURE})

    assert unwired(files, root) == []


def test_a_single_control_is_below_the_floor(build):
    """One control is a fragment or a placeholder, not an interface."""
    one = '<!DOCTYPE html><html><body><button id="go">Go</button></body></html>'
    files, root = build({"index.html": one, "app.js": PURE})

    assert unwired(files, root) == []


def test_a_test_file_does_not_count_as_wiring_the_page(build):
    """One run's project was a page, a stylesheet and two test files."""
    files, root = build({
        "index.html": PAGE,
        "validate-html.test.mjs": "import assert from 'node:assert';\ndocument;\n",
    })

    assert len(unwired(files, root)) == 1


def test_a_framework_mount_counts_as_touching_the_page(build):
    react = "import ReactDOM from 'react-dom/client';\nReactDOM.createRoot(x).render(y);\n"
    files, root = build({"index.html": PAGE, "app.js": react})

    assert unwired(files, root) == []
