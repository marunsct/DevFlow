"""A page that loads a module the browser cannot parse.

`<script src="app.js">` with no `type="module"` makes the browser parse the
file as a classic script. It reaches `export` on the first line and throws
`Uncaught SyntaxError: Unexpected token 'export'`, and nothing on the page
works at all. The suite never notices: `node --test` imports the module
directly and never opens the HTML.

Nine of the fifty-eight stored workspaces ship exactly this - a page dead on
arrival in a run whose tests pass. It is the most product-destroying class in
the corpus and the cheapest to fix: one attribute.

`_modules_loaded_as_plain_scripts` already finds it at a milestone review,
several stages after both files were written. This says it at the write of
whichever side comes second, and agrees with that check on all nine.
"""

from __future__ import annotations

import pytest

from app.tools.repository import write_approved_artifact

A_MODULE = "export function addTask(title) {}\n"
COMMONJS = "const fs = require('fs');\nmodule.exports = { addTask };\n"
A_PLAIN_PAGE = "<!doctype html><body><script src='app.js'></script></body>\n"
A_MODULE_PAGE = "<!doctype html><body><script type='module' src='app.js'></script></body>\n"


def _note(tmp_path, first, second) -> str:
    (tmp_path / "p").mkdir(exist_ok=True)
    write_approved_artifact(tmp_path, f"p/{first[0]}", first[1])
    return write_approved_artifact(tmp_path, f"p/{second[0]}", second[1]).get("note", "")


def test_writing_the_module_under_a_plain_tag_is_named(tmp_path):
    note = _note(tmp_path, ("index.html", A_PLAIN_PAGE), ("app.js", A_MODULE))
    assert "Unexpected token 'export'" in note
    assert 'Add `type="module"`' in note


def test_writing_the_plain_tag_over_a_module_is_named(tmp_path):
    """Whichever side is written second is the one that can act on it."""
    note = _note(tmp_path, ("app.js", A_MODULE), ("index.html", A_PLAIN_PAGE))
    assert "Unexpected token 'export'" in note


def test_it_says_the_suite_will_not_catch_it(tmp_path):
    """The reason this reaches a milestone review green is worth stating."""
    note = _note(tmp_path, ("index.html", A_PLAIN_PAGE), ("app.js", A_MODULE))
    assert "never opens the page" in note


def test_commonjs_behind_a_module_tag_is_the_mirror(tmp_path):
    note = _note(tmp_path, ("index.html", A_MODULE_PAGE), ("app.js", COMMONJS))
    assert "require is not defined" in note


@pytest.mark.parametrize(
    "page,script",
    [
        (A_MODULE_PAGE, A_MODULE),
        (A_PLAIN_PAGE, "function addTask(title) {}\n"),
    ],
)
def test_a_page_that_agrees_with_its_script_says_nothing(tmp_path, page, script):
    assert _note(tmp_path, ("index.html", page), ("app.js", script)) == ""


def test_an_export_in_a_comment_is_not_an_export(tmp_path):
    assert (
        _note(
            tmp_path,
            ("index.html", A_PLAIN_PAGE),
            ("app.js", "// export function a() {}\nfunction a() {}\n"),
        )
        == ""
    )


def test_an_inline_module_script_is_not_a_file_reference(tmp_path):
    """Run 3ddd443's page imported its module from an inline
    `<script type="module">`, which has no `src` to disagree about."""
    inline = "<!doctype html><body><script type='module'>import './app.js';</script></body>\n"
    assert _note(tmp_path, ("index.html", inline), ("app.js", A_MODULE)) == ""


def test_a_root_relative_src_resolves_to_the_same_file(tmp_path):
    """`src="/app.js"` is the Vite form; `Path("a") / "/b"` would throw the
    left side away and resolve to the wrong file entirely."""
    page = "<!doctype html><body><script type='module' src='/app.js'></script></body>\n"
    assert _note(tmp_path, ("index.html", page), ("app.js", A_MODULE)) == ""
    plain = "<!doctype html><body><script src='/app.js'></script></body>\n"
    assert _note(tmp_path, ("index.html", plain), ("app.js", A_MODULE)) != ""


def test_a_tag_pointing_at_a_file_that_is_not_there_says_nothing(tmp_path):
    (tmp_path / "p").mkdir()
    page = "<!doctype html><body><script src='missing.js'></script></body>\n"
    assert write_approved_artifact(tmp_path, "p/index.html", page).get("note", "") == ""


def test_a_stylesheet_is_not_a_script(tmp_path):
    (tmp_path / "p").mkdir()
    write_approved_artifact(tmp_path, "p/index.html", A_PLAIN_PAGE)
    assert "script" not in write_approved_artifact(
        tmp_path, "p/style.css", "body { margin: 0; }\n"
    ).get("note", "")
