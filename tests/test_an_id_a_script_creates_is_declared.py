"""A styled id the script builds is not a dead rule.

`_dangling_id_selectors` reports a stylesheet rule for an element id nothing
declares. It meant to count an id the script creates - the comment said "An id
the script creates counts as declared" - and looked for it with `_ID_SELECTOR`,
which matches CSS `#name`.

A script does not write `#`. It writes

    node.id = 'error-notice'
    node.setAttribute('id', 'error-notice')
    container.innerHTML = `<div id="error-notice">…</div>`

so the only thing that ever counted was an id the script *queried* by selector,
and every element built at runtime read as undeclared. Most of what this harness
is asked to build renders its UI from script.

The suffix list was the second half of it: `.js`, `.mjs` and `.cjs` only, while
the class check beside it already read TypeScript and the component formats. A
product whose logic is in `.ts` had none of its ids counted at all.

Latent rather than realised, and worth saying so: across the 77 stored workspaces
this check produces two findings and both are genuine, because those products
happen to put every styled id in their markup. Both survive this change.

The true positive comes from run-b3cb2d80, which completed. Sprint 2 planned a
"non-blocking notice shown to user when storage is unavailable", `style.css` got
`#error-notice`, and `error-notice` appears in no other file in the workspace -
the feature was styled and never built.
"""

from __future__ import annotations

import pytest

from app.analysis.integration_checks import (
    _dangling_id_selectors,
    _source_files,
)

A_PAGE = (
    '<!doctype html><html><head><link rel="stylesheet" href="style.css"></head>'
    '<body><ul id="tasks"></ul>'
    '<script type="module" src="./app.js"></script></body></html>'
)

A_STYLESHEET = "#tasks { margin: 0; }\n#error-notice { color: red; }\n"


@pytest.fixture
def a_project(tmp_path):
    def _build(script: str, script_name: str = "app.js"):
        project = tmp_path / "app"
        project.mkdir(exist_ok=True)
        (project / "index.html").write_text(A_PAGE)
        (project / "style.css").write_text(A_STYLESHEET)
        (project / script_name).write_text(script)
        return tmp_path

    return _build


def _flags_the_notice(root):
    return any(
        "error-notice" in problem for problem in _dangling_id_selectors(_source_files(root), root)
    )


class TestEveryWayAScriptGivesAnElementAnId:
    @pytest.mark.parametrize(
        "script",
        [
            "const n = document.createElement('div'); n.id = 'error-notice';",
            "const n = document.createElement('div');\nn.id = \"error-notice\";",
            "el.setAttribute('id', 'error-notice');",
            "el.setAttribute(\"id\", \"error-notice\");",
            "document.body.innerHTML = `<div id=\"error-notice\">oops</div>`;",
            "container.insertAdjacentHTML('beforeend', '<p id=\"error-notice\"></p>');",
            "document.querySelector('#error-notice').hidden = false;",
        ],
    )
    def test_the_rule_is_not_called_dead(self, a_project, script):
        root = a_project(script)

        assert not _flags_the_notice(root), script

    def test_reading_an_element_is_not_creating_one(self, a_project):
        """`getElementById` does not declare an id, and must not count as doing so.

        If nothing creates `#error-notice`, the rule really is dead - and the
        script is also looking for an element that will never be there, which
        `_dangling_script_hooks` reports separately and grades as breaking. This
        check must not give that away.
        """
        root = a_project("const notice = document.getElementById('error-notice');")

        assert _flags_the_notice(root)

    @pytest.mark.parametrize(
        "name", ["app.js", "app.mjs", "app.cjs", "app.ts", "app.tsx", "app.jsx"]
    )
    def test_the_script_is_read_whatever_it_is_written_in(self, a_project, name):
        """`.ts` was not read at all, so none of its ids counted."""
        root = a_project("const n = document.createElement('div'); n.id = 'error-notice';", name)

        assert not _flags_the_notice(root), name


class TestTheFindingThatIsReal:
    def test_an_id_nothing_creates_is_still_reported(self, a_project):
        """run-b3cb2d80's `#error-notice`: styled, and in no other file."""
        root = a_project("document.getElementById('tasks').textContent = 'x';")

        assert _flags_the_notice(root)

    def test_it_says_both_things_it_checked(self, a_project):
        """"no HTML element declares it" was only half of what it looked at."""
        root = a_project("document.getElementById('tasks').textContent = 'x';")

        problem = _dangling_id_selectors(_source_files(root), root)[0]

        assert "no page declares it" in problem
        assert "no script creates it" in problem

    def test_it_offers_both_readings(self, a_project):
        """A dead rule and an unbuilt element need different fixes."""
        root = a_project("document.getElementById('tasks').textContent = 'x';")

        problem = _dangling_id_selectors(_source_files(root), root)[0]

        assert "never applies" in problem
        assert "never built" in problem

    def test_an_id_the_page_declares_is_silent(self, a_project):
        root = a_project("const x = 1;")

        problems = _dangling_id_selectors(_source_files(root), root)

        assert not any("`#tasks`" in problem for problem in problems)


class TestOtherStylesheetFormats:
    @pytest.mark.parametrize("name", ["style.css", "style.scss", "style.sass"])
    def test_a_preprocessed_stylesheet_is_read_too(self, tmp_path, name):
        """The class check beside this one already read these."""
        project = tmp_path / "app"
        project.mkdir()
        (project / "index.html").write_text(A_PAGE)
        (project / name).write_text(A_STYLESHEET)
        (project / "app.js").write_text("document.getElementById('tasks');")

        assert _flags_the_notice(tmp_path), name


class TestNotFallingOver:
    def test_no_stylesheet_reports_nothing(self, tmp_path):
        project = tmp_path / "app"
        project.mkdir()
        (project / "index.html").write_text(A_PAGE)
        (project / "app.js").write_text("const a = 1;")

        assert _dangling_id_selectors(_source_files(tmp_path), tmp_path) == []

    def test_an_empty_workspace_reports_nothing(self, tmp_path):
        assert _dangling_id_selectors([], tmp_path) == []
