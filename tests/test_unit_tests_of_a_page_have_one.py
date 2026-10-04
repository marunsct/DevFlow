"""Unit tests of a browser product run with a browser's globals, set up once.

Four runs in a row spent their first sprint on the same thing while every
acceptance test passed: unit tests of code that touches the page, each with a
DOM built by hand - a `setup.js` that left `beforeEach` undefined,
`HTMLButtonElement is not defined`, a form the test could not find, thirteen
refused `node -e` probes of jsdom. The React pack's runner has always given its
tests a page; the plain pack gave none, and the harness's notes said both "you
MUST use Playwright" and "Do NOT use jsdom".

The pack now keeps `test-setup.mjs`, which every unit test process imports
first. Measured in the worker image on its Node 20: a module that touches the
page imports, a form submit, `new FormData(form)`, an aborted listener and
`DOMException` all behave as in a browser, and timers still tick.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.analysis.test_discovery import a_dom_built_by_hand, a_test_that_needs_a_dom
from app.plugins.seed import SEED_INSTRUCTIONS, SETUP
from app.stacks import contract, pack_named
from app.stacks.contract import HARNESS_DIR

BROWSER = pack_named("browser-javascript")


def test_every_unit_test_process_gets_the_page_first() -> None:
    files = BROWSER.render("notes", "Notes")
    manifest = json.loads(files["package.json"])

    assert "node --import ./test-setup.mjs --test" in manifest["scripts"]["test"]
    assert manifest["scripts"]["test"] == BROWSER.kept_scripts["test"]
    assert "test-setup.mjs" in BROWSER.kept_files
    setup = files["test-setup.mjs"]
    assert "from 'jsdom'" in setup and "url: 'http://localhost/'" in setup
    # The window's own event and form classes, or jsdom rejects what a test
    # hands back to the page.
    for name in ("'Event'", "'FormData'", "'AbortSignal'", "'DOMException'"):
        assert name in setup


def test_the_dom_s_version_runs_on_the_node_the_image_and_ci_use() -> None:
    from app.stacks.packs import _javascript as js
    from app.stacks.packs.browser_javascript import JSDOM

    # jsdom 27 and later need Node 22.
    assert int(JSDOM.split(".")[0]) <= 26 and js.NODE_MAJOR == "20"
    assert json.loads(BROWSER.render("n", "N")["package.json"])["devDependencies"]["jsdom"] == JSDOM


def test_the_scaffold_proves_a_module_that_touches_the_page_can_be_tested() -> None:
    smoke = BROWSER.smoke_files["tests/scaffold-smoke.test.js"]
    assert "await import('../src/main.js')" in smoke and "document.documentElement" in smoke


def test_the_guide_says_the_page_is_there_and_how_to_start_clean() -> None:
    guide = " ".join(BROWSER.guide.split())
    assert "test-setup.mjs" in guide and "document.body.innerHTML" in guide
    assert "Do not build a DOM of your own" in guide


@pytest.fixture
def scaffolded(tmp_path) -> Path:
    (tmp_path / HARNESS_DIR).mkdir(parents=True)
    (tmp_path / contract.CONTRACT_FILE).write_text(json.dumps({"pack": BROWSER.name, "project": "notes"}))
    (tmp_path / "notes" / "src").mkdir(parents=True)
    (tmp_path / "notes" / "src" / "view.js").write_text(
        "export function show(items) { document.querySelector('ul').innerHTML = items.join(''); }\n"
    )
    return tmp_path


def test_where_the_pack_gives_a_page_a_test_that_uses_it_is_not_sent_elsewhere(scaffolded) -> None:
    from app.tools.repository import _the_dom_unit_tests_get

    target = scaffolded / "notes" / "tests" / "view.test.js"
    test = "import { test } from 'node:test';\nimport { show } from '../src/view.js';\ntest('x', () => show([]));\n"

    target.parent.mkdir(parents=True)
    given = _the_dom_unit_tests_get(target)
    assert given == BROWSER.unit_dom
    assert a_test_that_needs_a_dom("notes/tests/view.test.js", test, target.parent, given) is None
    # Without a pack the note still says why it would throw.
    assert a_test_that_needs_a_dom("notes/tests/view.test.js", test, target.parent)


@pytest.mark.parametrize("setup", [
    "global.document = { querySelector: () => null };",
    "import { JSDOM } from 'jsdom';\nconst dom = new JSDOM('');\nglobal.window = dom.window;",
])
def test_a_second_page_is_named_as_one_where_the_pack_gives_a_page(setup) -> None:
    test = f"import {{ test }} from 'node:test';\n{setup}\ntest('x', () => {{}});\n"

    note = a_dom_built_by_hand("notes/tests/a.test.js", test, BROWSER.unit_dom)

    assert note and "test-setup.mjs" in note and "document.body.innerHTML" in note
    assert "Playwright" not in note


def test_a_test_using_the_given_page_is_left_alone() -> None:
    test = (
        "import { test, beforeEach } from 'node:test';\n"
        "beforeEach(() => { document.body.innerHTML = '<ul></ul>'; });\n"
        "test('x', () => {});\n"
    )
    assert a_dom_built_by_hand("notes/tests/a.test.js", test, BROWSER.unit_dom) is None


def test_the_third_second_page_is_refused_with_the_way_out(scaffolded) -> None:
    from app.tools.repository import RepositoryToolError, _refuse_a_hand_built_dom_again
    from app.tools.seen_content import MOCK_DOM_WARNINGS_BEFORE_REFUSING, record_mock_dom_warning

    relative = "notes/tests/again.test.js"
    for _ in range(MOCK_DOM_WARNINGS_BEFORE_REFUSING):
        record_mock_dom_warning(relative)
    test = "import { test } from 'node:test';\nglobal.document = {};\ntest('x', () => {});\n"

    with pytest.raises(RepositoryToolError) as raised:
        _refuse_a_hand_built_dom_again(relative, test, scaffolded / relative)

    assert "test-setup.mjs" in str(raised.value) and "npm install" not in str(raised.value)


# --- the stack's notes agree with the pack -------------------------------------------


def test_setting_a_runner_up_is_a_note_of_its_own() -> None:
    page = " ".join(SEED_INSTRUCTIONS["html"].split())
    assert "webServer" not in page and "npm i -D" not in page and "Do NOT use jsdom" not in page
    assert "webServer" in SEED_INSTRUCTIONS["html" + SETUP]
    assert "MUST EXIT" not in SEED_INSTRUCTIONS["javascript"]
    assert "MUST EXIT" in SEED_INSTRUCTIONS["javascript" + SETUP]
    # How a test is written is shown whoever set the runner up.
    assert "Assert on what it returned" in SEED_INSTRUCTIONS["javascript"]


def test_a_scaffolded_project_is_not_told_how_to_set_up_what_it_has(scaffolded, tmp_path_factory) -> None:
    from app.plugins.middleware import _with_the_setup_notes

    assert _with_the_setup_notes(["html", "javascript"], str(scaffolded)) == ["html", "javascript"]
    bare = tmp_path_factory.mktemp("bare")
    assert _with_the_setup_notes(["html"], str(bare)) == ["html", "html" + SETUP]


def test_the_guide_says_how_to_run_one_file_with_the_page() -> None:
    """A bare `node --test tests/x.test.js` skips the setup and reads as "this
    test needs a DOM built"; one fixer added a script to the product's manifest
    to get round it."""
    from app.tools.sandbox import validate_command

    guide = " ".join(BROWSER.guide.split())
    command = "node --import ./test-setup.mjs --test tests/<module>.test.js"
    assert command in guide
    assert validate_command(command.replace("<module>", "a").split(), "testing_specialist")


def test_a_kept_setup_is_described_as_what_runs_it() -> None:
    from app.agents.workspace_digest import _what_to_do_with

    assert "acceptance command" not in _what_to_do_with(contract.KEPT_SETUP)
    assert "test commands run it" in _what_to_do_with(contract.KEPT_SETUP)


def test_a_scaffolded_project_s_brief_does_not_ask_one_command_to_run_both_suites(scaffolded) -> None:
    from types import SimpleNamespace

    from app.agents.specialists import describe_stack

    stack = SimpleNamespace(
        language="JavaScript", framework="", frontend_framework="", database="",
        testing_framework="node:test", additional_tools=[],
    )
    assert "must run both suites" in describe_stack(stack)
    scaffolded_brief = describe_stack(stack, str(scaffolded))
    assert "must run both suites" not in scaffolded_brief
    assert "How the pieces load" not in scaffolded_brief
    assert "Build on exactly this" in scaffolded_brief
