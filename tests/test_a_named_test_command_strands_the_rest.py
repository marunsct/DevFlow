"""`node --test <file>` runs that file and nothing else.

One run reached its sixth milestone with `scripts.test` of
`node --test main.test.js` and a second suite at `tests/filter.test.js` - a
correct Node test name, in a directory bare `node --test` would recurse into,
which never ran once. Every gate read "# tests 4  # pass 4" and none of the
filter tests were among them.

The check that exists for this decided discovery by NAME, and by name
`filter.test.js` is collectable. It also looked only at files directly in the
project directory. Both are wrong, and the rule - verified against Node 24.21
in the run image, with `badname.mjs` beside `a.test.js`, the same pair under
`sub/`, and `c.test.js` and `deep/d.test.mjs` under `tests/` - is that a FILE
argument runs that file whatever it is called, a quoted PATTERN runs what it
matches, and a DIRECTORY argument runs nothing at all:

    node --test                            ->  every name match, recursively
    node --test badname.mjs                ->  # tests 1   (the file, name notwithstanding)
    node --test 'tests/**/*.test.js'       ->  # tests 1   (c.test.js)
    node --test 'tests/**/*.test.{js,mjs}' ->  # tests 2   (braces expand)
    node --test ./                         ->  Could not find './'
    node --test sub/                       ->  # fail 1    (ERR_UNSUPPORTED_DIR_IMPORT)

Node 20 searched a directory argument; this harness's own packs named
`tests/` until the image moved to Node 24, when each of them failed its smoke
test exactly that way.
"""

import json

import pytest

from app.analysis.integration_checks import _severity_of, _tests_the_project_never_runs


@pytest.fixture
def project(tmp_path):
    app = tmp_path / "app"
    (app / "tests").mkdir(parents=True)
    (app / "main.test.js").write_text("import {test} from 'node:test';\ntest('a',()=>{});\n")
    (app / "tests" / "filter.test.js").write_text(
        "import {test} from 'node:test';\ntest('b',()=>{});\n"
    )
    return tmp_path


def _check(root, command):
    app = root / "app"
    (app / "package.json").write_text(json.dumps({"scripts": {"test": command}}))
    return _tests_the_project_never_runs(
        [app / "package.json", app / "main.test.js", app / "tests" / "filter.test.js"], root
    )


def test_the_measured_case(project):
    found = _check(project, "node --test main.test.js")

    assert len(found) == 1
    assert "names main.test.js" in found[0]
    assert "is run directly and nothing else is searched" in found[0]
    assert "tests/filter.test.js" in found[0]
    assert _severity_of(found[0]) == "BREAKS"


def test_a_bare_command_recurses_and_strands_nothing(project):
    """Verified against Node: it finds the subdirectory suite by name."""
    assert _check(project, "node --test") == []


@pytest.mark.parametrize("command", ["node --test ./", "node --test .", "node --test tests/",
                                     "node --test main.test.js tests"])
def test_a_directory_argument_runs_nothing(project, command):
    """Node 24 loads a directory argument as a module and fails before any test runs."""
    found = _check(project, command)

    assert len(found) == 1
    assert "loads a directory argument as a module" in found[0]
    assert "node --test '" in found[0], "the message gives the form that works"
    assert _severity_of(found[0]) == "BREAKS"


def test_a_file_argument_runs_a_name_node_would_not_collect(tmp_path):
    """`node --test badname.mjs` runs it; only the un-named files are stranded."""
    app = tmp_path / "app"
    app.mkdir()
    (app / "test_bad.mjs").write_text("import {test} from 'node:test';\ntest('c',()=>{});\n")
    (app / "main.test.js").write_text("import {test} from 'node:test';\ntest('a',()=>{});\n")
    (app / "package.json").write_text(json.dumps({"scripts": {"test": "node --test test_bad.mjs"}}))

    found = _tests_the_project_never_runs(
        [app / "package.json", app / "test_bad.mjs", app / "main.test.js"], tmp_path
    )

    assert len(found) == 1
    assert "main.test.js" in found[0]
    assert "test_bad.mjs" not in found[0].split("Stranded:")[-1]


def test_naming_both_strands_nothing(project):
    assert _check(project, "node --test main.test.js 'tests/**/*.test.js'") == []


def test_a_pattern_covers_what_it_matches(project):
    found = _check(project, "node --test 'tests/**/*.test.js'")

    assert len(found) == 1
    assert "main.test.js" in found[0]
    assert "tests/filter.test.js" not in found[0]
    assert "`tests/**/*.test.js`" in found[0]


def test_the_packs_own_unit_command_strands_nothing(project):
    """The JavaScript packs' unit command: Node's own names under `tests/`, as a pattern."""
    from app.stacks.packs import _javascript as js

    (project / "app" / "main.test.js").unlink()
    (project / "app" / "tests" / "deep").mkdir()
    deep = project / "app" / "tests" / "deep" / "test-store.mjs"
    deep.write_text("import {test} from 'node:test';\ntest('c',()=>{});\n")
    app = project / "app"
    (app / "package.json").write_text(json.dumps({"scripts": {"test": js.UNIT_SCRIPT}}))

    assert _tests_the_project_never_runs(
        [app / "package.json", app / "tests" / "filter.test.js", deep], project
    ) == []


def test_flags_are_not_mistaken_for_paths(project):
    assert _check(project, "node --test --experimental-test-coverage") == []


def test_another_runner_is_left_alone(project):
    """Jest and friends decide discovery in configuration this cannot read."""
    assert _check(project, "jest") == []


def test_a_badly_named_test_is_still_caught_under_a_bare_command(tmp_path):
    """The original finding, which must keep working: one run's six files."""
    app = tmp_path / "app"
    app.mkdir()
    (app / "package.json").write_text(json.dumps({"scripts": {"test": "node --test"}}))
    (app / "test_add_task.mjs").write_text("import {test} from 'node:test';\ntest('a',()=>{});\n")

    found = _tests_the_project_never_runs(
        [app / "package.json", app / "test_add_task.mjs"], tmp_path
    )

    assert len(found) == 1
    assert "test_add_task.mjs" in found[0]
    assert "the prefix form takes a hyphen" in found[0]


def test_an_aggregator_that_imports_the_suites_strands_nothing(tmp_path):
    """A named entry point that imports the tests runs them.

    One run's `run-tests.mjs` installs a localStorage stub the individual
    files need and then imports them:

        global.localStorage = { ... };
        import './tests/add.test.js';
        import './tests/filter.test.js';

    Without following that, this check reported all four imported suites as
    never executed - four wrong findings out of ten, for tests that run on
    every `npm test`. A wrong finding sends the run chasing a problem that is
    not there, which is worse than the silence it replaced.
    """
    app = tmp_path / "app"
    (app / "tests").mkdir(parents=True)
    (app / "tests" / "add.test.js").write_text(
        "import {test} from 'node:test';\ntest('a',()=>{});\n"
    )
    (app / "tests" / "filter.test.js").write_text(
        "import {test} from 'node:test';\ntest('b',()=>{});\n"
    )
    (app / "tests" / "orphan.test.js").write_text(
        "import {test} from 'node:test';\ntest('c',()=>{});\n"
    )
    (app / "run-tests.mjs").write_text(
        "global.localStorage = {};\n"
        "import './tests/add.test.js';\n"
        "import './tests/filter.test.js';\n"
    )
    (app / "package.json").write_text(
        json.dumps({"scripts": {"test": "node --test run-tests.mjs"}})
    )

    found = _tests_the_project_never_runs(
        [
            app / "package.json",
            app / "run-tests.mjs",
            app / "tests" / "add.test.js",
            app / "tests" / "filter.test.js",
            app / "tests" / "orphan.test.js",
        ],
        tmp_path,
    )

    stranded = found[0].split("Stranded: ")[-1] if found else ""
    assert "tests/add.test.js" not in stranded
    assert "tests/filter.test.js" not in stranded
    assert "tests/orphan.test.js" in stranded


def test_an_aggregator_chain_is_followed_to_the_end(tmp_path):
    """The import graph, not just its first level."""
    app = tmp_path / "app"
    (app / "tests").mkdir(parents=True)
    (app / "tests" / "deep.test.js").write_text(
        "import {test} from 'node:test';\ntest('d',()=>{});\n"
    )
    (app / "tests" / "index.js").write_text("import './deep.test.js';\n")
    (app / "run-tests.mjs").write_text("import './tests/index.js';\n")
    (app / "package.json").write_text(
        json.dumps({"scripts": {"test": "node --test run-tests.mjs"}})
    )

    found = _tests_the_project_never_runs(
        [
            app / "package.json",
            app / "run-tests.mjs",
            app / "tests" / "index.js",
            app / "tests" / "deep.test.js",
        ],
        tmp_path,
    )

    assert found == []


def test_a_cycle_between_aggregators_terminates(tmp_path):
    """Two files importing each other must not hang the check."""
    app = tmp_path / "app"
    app.mkdir()
    (app / "a.mjs").write_text("import './b.mjs';\n")
    (app / "b.mjs").write_text("import './a.mjs';\n")
    (app / "lonely.test.js").write_text("import {test} from 'node:test';\ntest('x',()=>{});\n")
    (app / "package.json").write_text(json.dumps({"scripts": {"test": "node --test a.mjs"}}))

    found = _tests_the_project_never_runs(
        [app / "package.json", app / "a.mjs", app / "b.mjs", app / "lonely.test.js"], tmp_path
    )

    assert "lonely.test.js" in found[0]
