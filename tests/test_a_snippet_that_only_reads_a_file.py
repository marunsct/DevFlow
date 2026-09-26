"""A snippet refused for executing code is usually only reading a file.

`node -e` and `python -c` are refused because they can execute arbitrary code,
and the refusal offers: "put the code in a file inside the project folder, run
the file, then remove it with `delete_artifact`". Three calls, and a scratch
file written into the product folder.

Across the 24 current-generation runs that refusal fired 31 times in 10 of
them, and almost every snippet was reading a file and printing part of it:

    node -e "const pkg = JSON.parse(require('fs').readFileSync('todo-app/package.json','utf8')); ..."
    node -e "const css = fs.readFileSync('/simple-to-do-list-app/style.css', 'utf8'); ..."
    node -e "import('./todo-app/app.js').then(m => console.log(Object.keys(m)))"

None of those needs to execute anything. `read_file` returns the file and
`grep` finds a name inside it, in one call, leaving nothing to delete.

The refusal itself is unchanged - what the snippet can do is why it is refused,
and that does not depend on what this one happened to be for. Only the advice
after it changes, and only when a file it names is really there.

Nothing here parses any language. Every language quotes a path the same way,
and the workspace decides whether a literal is one, so `ruby -e`, `php -r` and
`perl -e` are covered by the same reading.
"""

from __future__ import annotations

import pytest

from app.tools.sandbox import (
    CommandNotAllowed,
    _what_that_snippet_was_reading,
    validate_command,
)


@pytest.fixture
def a_project(tmp_path):
    """A workspace shaped like the runs this was measured on."""
    project = tmp_path / "todo-app"
    project.mkdir()
    (project / "package.json").write_text('{"type": "module"}\n')
    (project / "app.js").write_text("export const add = () => {};\n")
    (project / "style.css").write_text("body { margin: 0; }\n")
    return tmp_path


def _hint(root, *snippet):
    return _what_that_snippet_was_reading(["node", "-e", *snippet], str(root))


class TestTheSnippetsThatWereRefused:
    def test_the_package_json_read_that_fired_most(self, a_project):
        hint = _hint(
            a_project,
            "const pkg = JSON.parse(require('fs').readFileSync('todo-app/package.json','utf8')); "
            "console.log(pkg.scripts)",
        )

        assert "`todo-app/package.json`" in hint

    def test_a_relative_import_is_found_in_the_project(self, a_project):
        """`./app.js` is relative to a directory this validator is not told."""
        hint = _hint(
            a_project,
            "import('./app.js').then(m => console.log(Object.keys(m).join(', ')))",
        )

        assert "`todo-app/app.js`" in hint

    def test_an_absolute_workspace_path_is_found(self, a_project):
        hint = _hint(
            a_project,
            "const css = require('fs').readFileSync('/todo-app/style.css', 'utf8'); console.log(css)",
        )

        assert "`todo-app/style.css`" in hint

    def test_it_names_the_tool_that_does_it_in_one_call(self, a_project):
        hint = _hint(a_project, "require('fs').readFileSync('todo-app/app.js','utf8')")

        assert "`read_file`" in hint
        assert "`grep`" in hint

    def test_it_offers_rather_than_asserts_what_the_snippet_needs(self, a_project):
        """Some of these require the module and exercise it, which is not reading.

        Replaying the stored refusals, 21 of 36 named a file that is still on
        disk - and one of them was `const app=require('./app.js'); ... global
        .localStorage = ...`, which is executing it. A note that told that
        snippet it was only reading would be wrong about the one thing it is for.
        """
        hint = _hint(
            a_project,
            "const app = require('./app.js'); global.localStorage = {}; app.init();",
        )

        assert "names `todo-app/app.js`" in hint
        assert "If what you need is what is in it" in hint

    def test_it_keeps_the_route_for_a_snippet_that_must_run(self, a_project):
        hint = _hint(a_project, "require('./app.js').init()")

        assert "If you do need to execute it" in hint

    def test_it_says_there_is_nothing_left_to_delete(self, a_project):
        """The remedy it replaces ends in a scratch file inside the product."""
        hint = _hint(a_project, "require('fs').readFileSync('todo-app/app.js','utf8')")

        assert "nothing left to delete" in hint


class TestEveryLanguageQuotesAPathTheSameWay:
    @pytest.mark.parametrize(
        "argv",
        [
            ["python3", "-c", "import json; print(json.load(open('todo-app/package.json')))"],
            ["ruby", "-e", "puts File.read('todo-app/app.js')"],
            ["php", "-r", "echo file_get_contents('todo-app/style.css');"],
            ["perl", "-e", "open(F, '<', 'todo-app/app.js'); print <F>;"],
            ["node", "--input-type=module", "-e", "import {readFileSync} from 'fs'; readFileSync('todo-app/app.js')"],
        ],
    )
    def test_the_file_is_named_whatever_the_runtime(self, a_project, argv):
        hint = _what_that_snippet_was_reading(argv, str(a_project))

        assert "todo-app/" in hint, argv


class TestSayingNothingWhenItCannotHelp:
    def test_a_snippet_naming_no_file_is_silent(self, a_project):
        assert _hint(a_project, "console.log(1 + 1)") == ""

    def test_a_file_that_does_not_exist_is_silent(self, a_project):
        """A path the workspace does not have is not something `read_file` solves."""
        assert _hint(a_project, "require('fs').readFileSync('nowhere/absent.json')") == ""

    def test_a_snippet_that_writes_is_still_only_described_by_what_exists(
        self, a_project
    ):
        """This says what is readable; it does not claim the snippet only reads."""
        hint = _hint(
            a_project,
            "require('fs').writeFileSync('todo-app/app.js', 'x')",
        )

        assert "`todo-app/app.js`" in hint
        assert "this snippet reads" not in hint

    @pytest.mark.parametrize(
        "literal", ["utf8", "Exports:", ", ", "module", "  ", "1.5", "a.b.c.d.e.f.g"]
    )
    def test_a_literal_that_is_not_a_path_is_ignored(self, a_project, literal):
        assert _hint(a_project, f"console.log('{literal}')") == ""

    def test_no_workspace_is_silent(self):
        assert _what_that_snippet_was_reading(["node", "-e", "read('a.js')"], None) == ""

    def test_a_workspace_that_does_not_exist_does_not_raise(self, tmp_path):
        assert _what_that_snippet_was_reading(
            ["node", "-e", "read('a.js')"], str(tmp_path / "gone")
        ) == ""

    def test_the_list_is_capped(self, a_project):
        """Past a couple, the snippet was doing something this cannot summarise."""
        hint = _hint(
            a_project,
            "['todo-app/package.json','todo-app/app.js','todo-app/style.css']"
            ".forEach(f => console.log(require('fs').readFileSync(f)))",
        )

        assert hint.count("`todo-app/") <= 3


class TestTheRefusalItself:
    def test_it_is_still_refused(self, a_project):
        """What the snippet can do is why it is refused, whatever this one was for."""
        with pytest.raises(CommandNotAllowed) as raised:
            validate_command(
                ["node", "-e", "require('fs').readFileSync('todo-app/app.js','utf8')"],
                "testing_specialist",
                str(a_project),
            )

        assert "is not permitted" in str(raised.value)

    def test_the_hint_reaches_the_refusal(self, a_project):
        with pytest.raises(CommandNotAllowed) as raised:
            validate_command(
                ["node", "-e", "require('fs').readFileSync('todo-app/app.js','utf8')"],
                "testing_specialist",
                str(a_project),
            )

        assert "`read_file` returns that without running anything" in str(raised.value)

    def test_the_original_advice_is_kept(self, a_project):
        """A snippet that really does need to run still needs to be told how."""
        with pytest.raises(CommandNotAllowed) as raised:
            validate_command(
                ["node", "-e", "require('fs').readFileSync('todo-app/app.js','utf8')"],
                "testing_specialist",
                str(a_project),
            )

        assert "Put the code in a file inside the project folder" in str(raised.value)

    def test_a_snippet_naming_nothing_gets_the_refusal_unchanged(self, a_project):
        with pytest.raises(CommandNotAllowed) as raised:
            validate_command(
                ["node", "-e", "console.log(process.version)"],
                "testing_specialist",
                str(a_project),
            )

        assert "already in the workspace" not in str(raised.value)

    def test_a_permitted_command_is_unaffected(self, a_project):
        """The validator must still pass what it always passed."""
        assert validate_command(
            ["node", "--test", "todo-app/app.test.js"], "testing_specialist", str(a_project)
        )[0].endswith("node")
