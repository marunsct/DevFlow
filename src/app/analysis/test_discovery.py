"""Catch a test file the project's runner will never collect.

run-d3965815's security specialist wrote `todo-app/app.test_xss.mjs`: a real
test file, with real assertions, for a real XSS concern. Node's test runner
collects `*.test.mjs`, `*-test.mjs`, `*_test.mjs`, `test-*.mjs`, `test.mjs` and
anything under a `test/` directory. `app.test_xss.mjs` is none of those, so
`node --test todo-app/` ran one file and reported "# tests 1" while two test
files sat in the directory.

Nothing failed. That is what makes it worth catching at the write: a test that
is not collected does not error, it is simply absent, and every later stage -
the testing round, the milestone review, the defect loop - reads a green run
that never executed it. The harness's own file classifier had the same blind
spot and counted it as application code.

A warning, not a refusal. The name is legal, the content is fine, and a project
may have its own runner configuration this cannot see. What the specialist
needs is to be told the runner will skip it while it is still looking at the
file it just wrote.
"""

from __future__ import annotations

import re

#: Node's default patterns, as globs reduced to what they mean for a basename:
#: `*.test.?js`, `*-test.?js`, `*_test.?js`, `test-*.?js`, `test.?js`.
#: https://nodejs.org/api/test.html#running-tests-from-the-command-line
#:
#: The prefix form takes a HYPHEN only. This first read it as `test[-_]`, which
#: is the natural symmetry to draw from the suffix form and is wrong - verified
#: by running Node over six names in a directory:
#:
#:     ok  add-task-test.mjs   ok  add.test.mjs   ok  add_task_test.mjs
#:     ok  test-add-task.mjs   ok  test.mjs       --  test_add_task.mjs
#:
#: Five of six collected. run-04576307 wrote `test_add_task.mjs`,
#: `test_delete_task.mjs`, `test_edit_task.mjs`, `test_filter_tasks.mjs`,
#: `test_persistence.mjs` and `test_toggle_task.mjs` - six suites, none of
#: which Node runs, and this check called every one of them fine.
_NODE_TEST_NAME = re.compile(
    r"^(?:.+[.\-_]test|test|test-.+)\.[cm]?js$",
    re.IGNORECASE,
)

#: Extensions Node's runner considers at all.
_NODE_SUFFIXES = (".js", ".cjs", ".mjs")

#: What makes this Node's own runner's problem: the file imports `node:test`.
#:
#: Deliberately only that. Matching a bare top-level `test(` or `describe(`
#: would flag an application module that happens to call a function named
#: `test`, and matching vitest, jest or mocha would flag files whose runner has
#: entirely different discovery patterns and its own configuration file this
#: cannot read. A warning that is wrong about a file which runs perfectly well
#: is worse than no warning.
_DECLARES_TESTS = re.compile(
    r"""from\s+['"]node:test['"]|require\(\s*['"]node:test['"]"""
)


def _under_a_test_directory(relative_path: str) -> bool:
    parts = relative_path.replace("\\", "/").split("/")[:-1]
    return any(part.lower() in {"test", "tests", "__tests__"} for part in parts)


def _renamed(stem: str) -> str:
    """The stem with any test/spec fragment taken out, ready for `.test`.

    `app.test_xss` would otherwise become `app-test_xss.test.mjs`, which names
    testing twice and reads like a mistake of its own.
    """
    cleaned = re.sub(r"[.\-_]+", "-", stem)
    cleaned = re.sub(r"(?<![a-z0-9])(test|spec)(?![a-z0-9])", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned or "suite"


def undiscoverable_test(relative_path: str, content: str) -> str | None:
    """Why the runner will skip this test file, or None if it will not.

    Only JavaScript, and only Node's own runner, because those are the patterns
    that are documented rather than guessed. A stack whose runner is configured
    elsewhere - a `jest.config.js`, a `vitest.config.ts` - is left alone; this
    cannot read that configuration and a wrong warning about a file that runs
    perfectly well is worse than no warning.
    """
    path = relative_path.replace("\\", "/")
    name = path.rsplit("/", 1)[-1]
    if not name.lower().endswith(_NODE_SUFFIXES):
        return None
    if not content or not _DECLARES_TESTS.search(content):
        return None
    if _under_a_test_directory(path) or _NODE_TEST_NAME.match(name):
        return None
    stem, suffix = name.rsplit(".", 1)
    suggestion = f"{_renamed(stem)}.test.{suffix}"
    return (
        f"This file declares tests, and `node --test` will not collect it: the "
        f"name '{name}' matches none of the patterns it looks for "
        f"(*.test.{suffix}, *-test.{suffix}, *_test.{suffix}, test-*.{suffix}, "
        f"test.{suffix}, or anything under a test/ directory). It will not "
        f"fail - it will simply never run, and every later stage will read a "
        f"green result that did not include it. Rename it to "
        f"'{suggestion}', or move it into a test/ directory."
    )


#: A relative import - `./app.js`, `../src/store.mjs`. The one thing a test of
#: this project's code always has and a test of its documentation never does.
_RELATIVE_IMPORT = re.compile(
    r"""(?:from|import)\s*\(?\s*['"](\.[^'"]*)['"]"""
    r"""|require\(\s*['"](\.[^'"]*)['"]"""
)


def tests_nothing_of_the_project(relative_path: str, content: str) -> str | None:
    """Why this test file tests no project code, or None if it does.

    run-84e05d4b wrote `simple-to-do-list-app/app.test.js` with four passing
    tests:

        package.json has correct name
        README.md exists and contains title
        docs folder contains required markdown files
        README contains Features section

    Four green assertions, none of which touched a line of application code -
    there was none in the project to touch. The test round passed, the security
    review passed, and the milestone review raised two minor issues about
    paths. A run can reach its end this way having built nothing, with every
    gate reporting success, because every gate asks whether the tests pass and
    none asks what they test.

    The signal is exact: a test of this project's code imports this project's
    code. `node:test`, `assert`, `fs` and `path` are the standard library; a
    file that imports only those and reads files by name is asserting about
    the repository, not exercising it.

    A framework import is not required - run-a7150a6c wrote `app.test.mjs`
    importing only `fs`, reading `index.html`, and throwing if a `<link>` tag
    was missing. A file the project calls a test and that imports none of the
    project is the same finding whether or not it uses `node:test`.

    A note, not a refusal. A smoke test that boots a built artifact and pokes
    it over HTTP legitimately imports nothing relative, and refusing that would
    be worse than letting a documentation test through.
    """
    # A framework import, or a name that says "test". Requiring the import
    # missed the shape run-a7150a6c produced: `app.test.mjs` importing only
    # `fs`, reading `index.html`, and throwing if a `<link>` tag is absent.
    # No `node:test`, so the first version of this check said nothing - about a
    # file called `app.test.mjs` that tests no application code at all.
    from app.analysis.file_kinds import is_test

    if not _DECLARES_TESTS.search(content or "") and not is_test(relative_path):
        return None
    if not (content or "").strip():
        return None
    if _RELATIVE_IMPORT.search(content):
        return None
    return (
        "This file declares tests and imports nothing from the project, so it "
        "cannot be exercising any of its code - `node:test`, `assert`, `fs` and "
        "`path` are the standard library. Tests that only read files by name "
        "assert that the repository looks a certain way, which passes whether "
        "or not the product works. Import the module under test "
        "(`import { addTask } from './app.js'`) and assert on what it does."
    )


#: A browser API being built by hand in a test file.
#:
#: `localStorage` and `sessionStorage` are deliberately NOT here. They are a
#: string-keyed map with four methods, a mock of one is complete in five lines,
#: and it does not collapse the way a `document` stub does. Including them
#: meant run-740edb6b's `addTask.test.mjs` - which mocks `localStorage`, sets
#: up no DOM, and fails with `document is not defined` - was told its
#: localStorage mock was the problem. The note was wrong about the file it
#: fired on, and the right note for that file could not fire.
_HAND_ROLLED_DOM = re.compile(
    r"""\bglobal(?:This)?\.(document|window|navigator)\s*="""
)

#: A real DOM already in use. The optional path suffix matters:
#: `global-jsdom/register` is the ordinary way to load one.
_HAS_A_REAL_DOM = re.compile(
    r"""['"](?:jsdom|happy-dom|linkedom|global-jsdom)(?:/[\w./-]*)?['"]"""
)


def a_dom_built_by_hand(relative_path: str, content: str) -> str | None:
    """Why this test's hand-built browser API will not hold, or None.

    Three runs have lost remediation rounds to the same thing. A browser
    product is tested with `node --test`, which has no DOM, so the specialist
    writes one:

        global.document = { getElementById: (id) => ({ innerHTML: '', ... }) }

    It works until the code under test touches something the mock does not
    have, and then the failure is `TypeError: Cannot read properties of
    undefined (reading 'children')` inside application code - which reads as an
    application bug and is not one. run-d3965815 spent three remediation
    rounds and its whole sprint on exactly that; run-0deeb8bf and run-84e05d4b
    lost stages to the same shape.

    The sandbox grants a network to the `install` category, so `npm install
    jsdom` genuinely works here - measured on run-84e05d4b, "added 39
    packages". A real DOM is available and costs one command.

    `--save-dev`, because `tests/brief_low.md` says "No external dependencies
    beyond basic HTML/CSS/JS" and means the product's. A test tool left in
    `dependencies` is a runtime dependency the product does not have, which
    `integration_checks._manifest_defects` reports as a defect of its own - so
    advice that put it there would trade one finding for another.

    A note, not a refusal. A tiny stub for one function is a reasonable thing
    to write, and this cannot tell that from a mock that is about to collapse.
    """
    if not _DECLARES_TESTS.search(content or ""):
        return None
    if not _HAND_ROLLED_DOM.search(content):
        return None
    if _HAS_A_REAL_DOM.search(content):
        return None
    return (
        "This test builds a browser API by hand (`global.document = ...`). That "
        "holds only until the code under test touches something the mock does "
        "not have, and the failure then looks like an application bug inside "
        "application code - three runs of this harness have lost whole sprints "
        "to it. `npm install --save-dev jsdom` works here - dependency installs "
        "are the one thing with network access - so use a real DOM instead. "
        "`--save-dev` matters: a brief that says \"no external dependencies\" "
        "means the product's, and a test tool left in `dependencies` is "
        "reported as a runtime dependency the product does not have."
    )


#: A browser global used outside a `typeof x !== "undefined"` guard.
_UNGUARDED_DOM = re.compile(
    r"""(?<![\w.$])(document|window)\s*\.""" 
)
_DOM_GUARD = re.compile(r"""typeof\s+(document|window)\s*!==?\s*['"]undefined['"]""")

#: Something in the test that provides a DOM: a real one, or a stub.
_PROVIDES_A_DOM = re.compile(
    r"""(?:global(?:This)?\.(?:document|window)\s*=)"""
    r"""|['"](?:jsdom|happy-dom|linkedom|global-jsdom)(?:/[\w./-]*)?['"]"""
)


def a_test_that_needs_a_dom(relative_path: str, content: str, project: "Path | None" = None) -> str | None:
    """Why this test will throw `document is not defined`, or None.

    Four runs have ended a stage on it - run-0deeb8bf, run-d3965815,
    run-84e05d4b and run-740edb6b, whose `addTask.test.mjs` imported `addTask`
    from a module whose render path calls `document.getElementById`, mocked
    `localStorage` and nothing else, and reported

        not ok 1 - addTask persists a new task
          error: 'document is not defined'
          name: 'ReferenceError'

    for every test in the file. The module guards its top level with `typeof
    document !== "undefined"`, so the import succeeds and the failure arrives
    only when a function is called - which is why no syntax or import check
    sees it.

    A note, and deliberately a soft one: a test may call only the DOM-free
    exports of a module that has DOM code elsewhere, and that works. What can
    be said without guessing is that the module reaches for `document`, the
    test provides none, and this is the error that follows if the path taken
    touches it.
    """
    from pathlib import Path

    if not _DECLARES_TESTS.search(content or "") and not _is_test_name(relative_path):
        return None
    if _PROVIDES_A_DOM.search(content or ""):
        return None
    here = Path(relative_path).parent
    base = project or here
    for match in _RELATIVE_IMPORT.finditer(content or ""):
        specifier = next((g for g in match.groups() if g), "")
        if not specifier:
            continue
        for suffix in ("", ".js", ".mjs", ".cjs"):
            candidate = (base / (specifier + suffix)).resolve()
            if not candidate.is_file():
                continue
            try:
                module = candidate.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                break
            if not _UNGUARDED_DOM.search(module):
                break
            return (
                f"`{specifier}` uses `document` or `window`, and this test sets up "
                "neither. Node has no DOM, so any test that reaches that code "
                "fails with `ReferenceError: document is not defined` - not at "
                "import, which is why no other check sees it, but when the "
                "function is called. Either call only the parts that do not "
                "touch the page, or `npm install --save-dev jsdom` and assign "
                "`global.document` from it."
            )
        break
    return None


def _is_test_name(relative_path: str) -> bool:
    from app.analysis.file_kinds import is_test

    return is_test(relative_path)


__all__ = [
    "a_dom_built_by_hand",
    "a_test_that_needs_a_dom",
    "tests_nothing_of_the_project",
    "undiscoverable_test",
]
