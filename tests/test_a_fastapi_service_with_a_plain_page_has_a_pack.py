"""A FastAPI service that serves a page in plain HTML and JavaScript is set up by a pack, not by the agents.

Measured on one run: the stack decision said "Python / FastAPI - no stack pack fits", agents set the stack up for
about 22 minutes, the suite writers spent about 80 minutes making two runners work by hand, and the run failed
because the suite could not start the product - while the product it had built passed every hidden test.
"""
from types import SimpleNamespace

from app.stacks import choose_pack
from app.stacks.packs import fullstack_frameworks

BRIEF = """A small bookmarks service with a page.
- The service serves the page at `/`.
- The page has a text field labelled "Title" and a button named "Save bookmark".
- `GET /api/bookmarks` answers 200 with an array of bookmarks.
## Technical Constraints
- Python for the service (FastAPI or the standard library); the page in HTML and JavaScript
"""


def _stack(frontend):
    return SimpleNamespace(language="Python", framework="FastAPI", frontend_framework=frontend,
                           database="SQLite", testing_framework="pytest")


def test_the_bookmarks_stack_gets_the_page_pack():
    pack = choose_pack(_stack("HTML and JavaScript"), BRIEF)
    assert pack is fullstack_frameworks.PAGE_FASTAPI
    assert pack.kind == "fullstack" and pack.language == "python"


def test_a_component_framework_still_gets_its_own_pack():
    assert choose_pack(_stack("React"), BRIEF) is fullstack_frameworks.REACT_FASTAPI


def test_the_pack_holds_a_page_its_unit_tests_and_a_service():
    files = fullstack_frameworks.PAGE_FASTAPI.files
    assert {"index.html", "src/main.js", "{{package}}/main.py", "playwright.config.js"} <= set(files)
    assert "tests/client/scaffold-smoke.test.js" in fullstack_frameworks.PAGE_FASTAPI.smoke_files
    assert "**/*.test.{ts,tsx,js}" in files["vite.config.ts"]


def test_a_page_left_unstated_is_not_taken_for_plain():
    assert choose_pack(_stack("not stated"), BRIEF) is not fullstack_frameworks.PAGE_FASTAPI
