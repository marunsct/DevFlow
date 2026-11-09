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
    """Nothing says how the page is built: no guess."""
    silent = "A bookmarks service with a page. `GET /api/bookmarks` answers 200 with an array of bookmarks."
    assert choose_pack(_stack("not stated"), silent) is not fullstack_frameworks.PAGE_FASTAPI


def test_an_empty_page_field_that_nothing_frames_is_plain():
    # As the selector wrote it on the run after the pack was deployed.
    stack = SimpleNamespace(language="Python", framework="FastAPI", frontend_framework="",
                            database="JSON file on disk (under DATA_DIR)", product_kind="fullstack",
                            testing_framework="pytest for the service, Playwright for browser testing of the page")
    assert choose_pack(stack, BRIEF, rationale="FastAPI serves the JSON interface and the page.") is fullstack_frameworks.PAGE_FASTAPI


def test_an_empty_page_field_with_react_in_the_rationale_is_not_plain():
    stack = _stack("")
    assert choose_pack(stack, BRIEF, rationale="React was chosen over Vue for the page.") is not fullstack_frameworks.PAGE_FASTAPI


#: As the selector wrote it on a later run: the field "not stated", and a rationale ruling every framework out by name.
RULED_OUT = ("**Frontend framework: empty (plain HTML + JavaScript)** - The brief requires \"plain HTML and JavaScript "
             "served by the same service at /\" with no mention of a frontend framework or build step. No React, Vue, "
             "Svelte, Angular, or Vite is needed for this straightforward form-and-list UI.")


def test_frameworks_named_only_to_be_ruled_out_leave_the_page_plain():
    stack = SimpleNamespace(language="Python", framework="FastAPI", frontend_framework="not stated",
                            database="JSON file on disk (under DATA_DIR)", product_kind="fullstack",
                            testing_framework="pytest + httpx for API tests, Playwright for frontend E2E tests")
    assert choose_pack(stack, BRIEF, rationale=RULED_OUT) is fullstack_frameworks.PAGE_FASTAPI


def test_a_framework_chosen_beside_one_ruled_out_is_still_a_framework():
    rationale = "No Angular is needed; React was chosen for the page."
    assert choose_pack(_stack(""), BRIEF, rationale=rationale) is not fullstack_frameworks.PAGE_FASTAPI
