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
        "to it. Mocking the DOM is no longer permitted. You MUST write a browser-based "
        "test using Playwright (`npm install -D @playwright/test`) to verify the "
        "end-to-end functionality including UI logic with a real browser. Do NOT "
        "remove or disable the UI logic."
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
                "function is called. You MUST write a browser-based test using "
                "Playwright (`npm install -D @playwright/test`) to verify the UI "
                "logic in a real browser context. Do NOT delete UI logic."
            )
        break
    return None


def _is_test_name(relative_path: str) -> bool:
    from app.analysis.file_kinds import is_test

    return is_test(relative_path)


__all__ = [
    "a_dom_built_by_hand",
    "a_test_that_needs_a_dom",
    "a_suite_that_only_checks_things_exist",
    "tests_nothing_of_the_project",
    "tests_the_runner_will_never_call",
    "undiscoverable_test",
]


#: Calls that make a test able to fail. Deliberately broad across runners:
#: `node:assert`, Jest/Vitest `expect`, chai's `should`/`expect`, and a bare
#: `throw` written by hand, which is how run-a7150a6c's test asserted.
_AN_ASSERTION = re.compile(
    r"""(?<![\w.$])assert\s*[.(]"""
    r"""|(?<![\w.$])expect\s*\("""
    r"""|(?<![\w.$])should\s*[.(]"""
    r"""|\.(?:toBe|toEqual|toMatch|toThrow|toContain|toHaveBeenCalled)\w*\s*\("""
    r"""|(?<![\w.$])(?:strictEqual|deepStrictEqual|deepEqual|notEqual|ok|ifError|throws|rejects|match)\s*\("""
    # `t.ok(...)` and `t.assert.ok(...)`: an assertion on some object. Wrong in
    # the first case - `assertions_called_on_the_test_module` says so - but an
    # attempt at one either way, so "this suite cannot fail" must not also fire
    # and contradict it.
    r"""|(?<![\w.$])\w+\.(?:assert\.)?(?:strictEqual|deepStrictEqual|deepEqual|notEqual|notStrictEqual|equal|ok|ifError|throws|rejects|match|fail)\s*\("""
    r"""|(?<![\w.$])throw\s+new\s+\w*Error"""
    r"""|(?<![\w.$])process\.exit\s*\(\s*1\s*\)""",
    re.MULTILINE,
)

#: A registered test, in the spellings the runners this harness sees accept.
_A_TEST_CASE = re.compile(
    r"""(?<![\w.$])(?:test|it)\s*(?:\.\w+\s*)?\(\s*['"`]([^'"`]{0,120})['"`]""",
    re.MULTILINE,
)


def a_test_that_asserts_nothing(relative_path: str, content: str) -> str | None:
    """Why this test file cannot fail, or None if it can.

    Run f81808a4 wrote `simple-to-do-list-app/main.test.js` as its whole
    suite, 164 bytes:

        import assert from 'node:assert';
        import { test } from 'node:test';
        import './main.js';

        test('main.js loads without error', () => {
          // no assertions needed
        });

    `node --test` reports "# pass 1  # fail 0", the test round reports a
    passing suite, and nothing in the product has been checked. `assert` is
    imported and never called. The file imports the project, so
    `tests_nothing_of_the_project` is satisfied by it; it runs, so
    `undiscoverable_test` is satisfied; and it passes, so every gate that
    asks whether the tests pass is satisfied too.

    The same shape as that check's own finding, one level in: there, tests
    that touched no project code; here, tests that make no claim at all.

    Only when the file registers test cases and contains no assertion
    anywhere. A helper module beside the suite has no test cases and is not
    this; a file with ten assertions and one empty case is weaker than it
    looks but is not a suite that cannot fail, and saying so would put a
    finding on most real test files.
    """
    from app.analysis.file_kinds import is_test

    # Both gates, not either. `is_test` alone would reach a helper module
    # beside the suite; the case pattern alone would reach an application
    # module that calls a function named `test`, which is the false positive
    # `_DECLARES_TESTS` above is written to avoid.
    if not is_test(relative_path):
        return None
    cases = _A_TEST_CASE.findall(content)
    if not cases:
        return None
    if _AN_ASSERTION.search(content):
        return None
    named = ", ".join(f"'{name}'" for name in cases[:3] if name)
    return (
        f"{relative_path} registers {len(cases)} test case(s)"
        + (f" ({named})" if named else "")
        + " and contains no assertion of any kind, so the suite cannot fail. "
        "It reports a pass whatever the application does, and every gate that "
        "asks whether the tests pass will be satisfied by it. Give each case a "
        "check that would fail if the behaviour it names were broken."
    )


#: `export default function (t) {` / `export default (t) => {` /
#: `module.exports = function (t) {`. The runner imports the module; it never
#: calls what the module exports.
_AN_EXPORTED_ENTRY_POINT = re.compile(
    r"""^\s*(?:export\s+default\s+(?:async\s+)?(?:function\b[^(]*)?\(|"""
    r"""export\s+default\s+(?:async\s+)?\w+\s*=>|"""
    r"""module\.exports\s*=\s*(?:async\s+)?function\b)""",
    re.M,
)

#: A test case registered at the module's own top level - no leading
#: indentation. This is the shape the runner actually runs.
_A_TEST_CASE_AT_TOP_LEVEL = re.compile(
    r"""^(?:await\s+)?(?:test|it|describe)\s*(?:\.\w+\s*)?\(\s*['"`]""",
    re.M,
)

#: A test case in any of its spellings, including `t.test(...)` on a context
#: object. `_A_TEST_CASE` excludes a dotted prefix on purpose - it asks whether
#: a suite asserts anything, and `assert.test` is not a case. Here the question
#: is whether cases exist at all, and a case registered on the context object
#: is still a case that will not run.
_A_TEST_CASE_IN_ANY_FORM = re.compile(
    r"""(?<![\w$])(?:\w+\.)?(?:test|it|describe)\s*(?:\.\w+\s*)?"""
    r"""\(\s*['"`]([^'"`]{0,120})['"`]""",
    re.M,
)


def tests_the_runner_will_never_call(relative_path: str, content: str) -> str | None:
    """Why this file's cases never run, or None if they do.

    Run d6297b2f's test round hit `ReferenceError: describe is not defined` -
    a Jest-shaped suite under `node --test` - and fixed it by moving every case
    inside a default-exported function:

        export default function (t) {
          t.test('addTask adds a new task with unique id', () => {
            assert.strictEqual(result.length, 1);

    `npm test` then returned 0:

        # tests 1   # suites 0   # pass 1   # fail 0

    That one passing test is the *file*, not anything in it. `node --test`
    imports a test file and runs the cases that register themselves while it
    loads; it does not call the module's default export, so the seven cases in
    that function - all with real assertions over real behaviour - never ran.
    Verified on Node 24.20.0 and consistent with Node 20: a file of this shape
    containing `assert.strictEqual(1, 2)` reports `pass 1, fail 0`.

    This is worse than a suite with no assertions, which
    `a_test_that_asserts_nothing` catches. The assertions are there, they are
    good, and the green tick says they hold. Every gate that asks whether the
    tests pass is satisfied by a file that ran none of them.

    Requires both halves, so a file with an exported helper alongside ordinary
    top-level cases is left alone: cases exist, and *none* of them is at the
    top level where the runner would find it.
    """
    if not _AN_EXPORTED_ENTRY_POINT.search(content):
        return None
    cases = _A_TEST_CASE_IN_ANY_FORM.findall(content)
    if not cases:
        return None
    if _A_TEST_CASE_AT_TOP_LEVEL.search(content):
        return None
    named = ", ".join(f"'{name}'" for name in cases[:3] if name)
    return (
        f"{relative_path} registers {len(cases)} test case(s)"
        + (f" ({named})" if named else "")
        + " inside a function it exports, and nothing at the file's top level. "
        "`node --test` imports a test file and runs whatever registers itself "
        "while it loads - it never calls the export. The run reports `# tests "
        "1 # pass 1` for the file itself and none of the cases execute, so the "
        "suite is green however broken the application is. Call `test(...)` at "
        "the top level of the file instead, importing it from 'node:test'."
    )


#: `assert.strictEqual(typeof addTask, 'function')` and its spellings. An
#: existence check: true the moment the export exists, whatever it does.
_ONLY_CHECKS_IT_EXISTS = re.compile(
    # `'undefined'` is deliberately absent. `typeof window !== 'undefined'` is
    # feature detection, which application code does constantly and which is
    # not an assertion about anything; including it reported run 551640d3's
    # `app.js` as a suite that only checks things exist.
    r"""typeof\s+\w+\s*(?:,\s*|===?\s*)['"](?:function|object)['"]"""
    r"""|['"](?:function|object)['"]\s*===?\s*typeof\s+\w+"""
    # Bare truthiness only: `assert(value)` or `assert(value, "message")`.
    # NOT `assert.deepStrictEqual(tasks, [])` - an earlier version allowed an
    # optional `.method` here and so matched nearly every real assertion,
    # which the sweep across the stored workspaces caught as three false
    # positives on suites that check behaviour perfectly well.
    r"""|(?<![\w.$])assert\s*\(\s*\w+\s*(?:,\s*['"][^'"]*['"]\s*)?\)"""
    r"""|\.toBeDefined\s*\(\s*\)|\.toBeTruthy\s*\(\s*\)"""
    r"""|\.to\.exist\b""",
)


def a_suite_that_only_checks_things_exist(relative_path: str, content: str) -> str | None:
    """Why this suite proves nothing, or None if it proves something.

    `a_test_that_asserts_nothing` catches a suite with no assertion at all.
    This catches the next shape along: every assertion is an existence check,
    so the suite is green the moment the exports exist and says nothing
    whatever about what they do.

    Run 1c9854c7 wrote `app.test.js` as five cases of exactly one form:

        test('loadTasks is a function', () => {
          assert.strictEqual(typeof loadTasks, 'function');
        });

    against an `app.js` whose five exported functions were each an empty body
    and a `// TODO` comment. `npm test` reported `# tests 5 # pass 5 # fail 0`,
    and every gate that asks whether the tests pass was satisfied by a product
    that does nothing at all.

    Requires that *every* assertion be of this kind. A suite that checks an
    export exists and then checks what it returns is doing the first as a
    guard, which is reasonable and common; the failure is a suite where that
    guard is the whole of it.
    """
    assertions = _AN_ASSERTION.findall(content)
    if len(assertions) < 2:
        return None
    existence = _ONLY_CHECKS_IT_EXISTS.findall(content)
    if len(existence) < len(assertions):
        return None
    cases = _A_TEST_CASE_IN_ANY_FORM.findall(content)
    named = ", ".join(f"'{name}'" for name in cases[:3] if name)
    return (
        f"{relative_path} has {len(assertions)} assertion(s) and every one of "
        "them only checks that something exists - `typeof x === 'function'` and "
        "the like"
        + (f" ({named})" if named else "")
        + ". The suite passes the moment the exports are declared, whatever "
        "their bodies do, so it cannot fail for a stub or an empty function "
        "and is not evidence that anything works. Assert what each function "
        "returns or changes, for an input you choose."
    )


#: What `node:test` actually exports. Everything else an agent reaches for on
#: it - `strictEqual` and friends - lives on `node:assert`.
_ASSERTIONS_NOT_ON_NODE_TEST = (
    "strictEqual", "deepStrictEqual", "deepEqual", "notDeepStrictEqual",
    "notStrictEqual", "notEqual", "equal", "ok", "ifError", "match",
    "doesNotMatch", "throws", "doesNotThrow", "rejects", "doesNotReject", "fail",
)

#: `import <name> from 'node:test'` / `const <name> = require('node:test')`.
#: Only the default binding: `import { test } from 'node:test'` is correct and
#: names the function, not the module.
_DEFAULT_IMPORT_OF_NODE_TEST = re.compile(
    r"""import\s+(\w+)\s*(?:,\s*\{[^}]*\}\s*)?from\s+['"]node:test['"]"""
    r"""|(?:const|let|var)\s+(\w+)\s*=\s*require\(\s*['"]node:test['"]\s*\)""",
)

#: The named-import form of the same confusion: `import { test, assert } from
#: 'node:test'`. `node:test` exports no such name, so the binding is
#: `undefined` and the first call on it throws.
_NAMED_IMPORTS_FROM_NODE_TEST = re.compile(
    r"""import\s*(?:\w+\s*,\s*)?\{([^}]*)\}\s*from\s+['"]node:test['"]"""
    r"""|(?:const|let|var)\s*\{([^}]*)\}\s*=\s*require\(\s*['"]node:test['"]\s*\)""",
)

#: `test('name', (t) => {` / `it('name', async (t) => {` - the context
#: parameter's name, so assertion calls on it can be recognised.
_TEST_CONTEXT_PARAMETER = re.compile(
    r"""(?<![\w.$])(?:test|it)\s*\(\s*['"`][^'"`]*['"`]\s*,\s*"""
    r"""(?:async\s+)?(?:\(\s*(\w+)|(\w+)\s*=>)""",
)

#: Names an agent reaches for on `node:test` that belong to `node:assert`.
#: A deliberate list rather than "anything not exported": Node adds exports
#: between versions, and a warning that is wrong about a working import is
#: worse than no warning.
_ASSERTION_NAMES = ("assert", "expect", "strict", *(_ASSERTIONS_NOT_ON_NODE_TEST))


def assertions_called_on_the_test_module(relative_path: str, content: str) -> str | None:
    """Why every test in this file throws TypeError, or None if they do not.

    Run f81808a4 wrote `simple-to-do-list-app/main.test.js` with

        import assert from 'node:test';
        ...
        assert.test('addTask creates a new task', () => {
          assert.strictEqual(tasks.length, 1);

    `assert.test(...)` registers the case, because the default export of
    `node:test` is the test function and it carries `.test`. `strictEqual` is
    not on it, so every case fails:

        # tests 4   # pass 0   # fail 4   TypeError

    Four real tests over real behaviour, none of which ran, and a defect-fix
    round spent on a one-word import. The assertion methods live on
    `node:assert`; `node:test` exports `test`, `describe`, `it`, the hooks,
    `mock` and `run`.

    Exact rather than heuristic: this fires only on the *default* binding of
    `node:test` with an assertion method called on it. `import { test } from
    'node:test'` is the correct form and names the function, not the module.
    """
    # The test context is the third spelling of this confusion, and the one
    # that cost run f81808a4 most. Verified in the run image on Node 20.20.2:
    #
    #     t.ok -> undefined   t.equal -> undefined   t.assert -> object
    #
    # so `t.ok(...)` throws and `t.assert.ok(...)` is the correct form.
    for match in _TEST_CONTEXT_PARAMETER.finditer(content):
        parameter = match.group(1) or match.group(2)
        if not parameter:
            continue
        for method in _ASSERTIONS_NOT_ON_NODE_TEST:
            # `t.assert.ok(` is correct and must not match: after `t.` comes
            # `assert`, not the method name.
            if re.search(rf"(?<![\w.$]){re.escape(parameter)}\.{method}\s*\(", content):
                return (
                    f"{relative_path} calls `{parameter}.{method}(...)` on a test's "
                    f"context. Node's context object has no `{method}` - it is "
                    "`undefined`, so the call throws `TypeError` and the test fails "
                    "without ever checking what it claims to. Use "
                    f"`{parameter}.assert.{method}(...)`, or import `node:assert` "
                    "and call it there."
                )

    # The named form first: `import { test, assert } from 'node:test'` binds
    # `assert` to undefined, and the first call on it throws. Run f81808a4
    # wrote both forms in turn, for the same file, an hour apart.
    for match in _NAMED_IMPORTS_FROM_NODE_TEST.finditer(content):
        names = (match.group(1) or match.group(2) or "").replace("\n", " ")
        for binding in (part.strip().split(" as ")[-1].strip() for part in names.split(",")):
            if binding in _ASSERTION_NAMES:
                return (
                    f"{relative_path} imports `{binding}` from `node:test`, which "
                    f"does not export it - `{binding}` is `undefined` here, and the "
                    "first call on it throws. The assertion methods are on "
                    "`node:assert`. Import the two separately: `import {{ test }} "
                    f"from 'node:test'` and `import {binding} from 'node:assert'`."
                ).replace("{{", "{").replace("}}", "}")

    match = _DEFAULT_IMPORT_OF_NODE_TEST.search(content)
    if not match:
        return None
    name = match.group(1) or match.group(2)
    if not name:
        return None
    used = [
        method
        for method in _ASSERTIONS_NOT_ON_NODE_TEST
        if re.search(rf"(?<![\w.$]){re.escape(name)}\.{method}\s*\(", content)
    ]
    if not used:
        return None
    return (
        f"{relative_path} imports `node:test` as `{name}` and then calls "
        f"`{name}.{used[0]}(...)`. That method is on `node:assert`, not "
        "`node:test`, so every test here throws `TypeError` the moment it runs - "
        "they are registered and reported as failures, not as passes. Import the "
        "two separately: `import { test } from 'node:test'` and `import "
        f"{name} from 'node:assert'`."
    )


_NAMED_LOCAL_IMPORT = re.compile(
    r"""import\s*\{([^}]*)\}\s*from\s*['"](\.[^'"]*)['"]"""
    r"""|(?:const|let|var)\s*\{([^}]*)\}\s*=\s*require\(\s*['"](\.[^'"]*)['"]""",
)


def _declares(source: str, name: str) -> str | None:
    """The parameter list of `name` as written in `source`, or None."""
    for form in (
        rf"function\s+{re.escape(name)}\s*\(",
        rf"(?:const|let|var)\s+{re.escape(name)}\s*=\s*(?:async\s*)?\(",
        rf"(?:const|let|var)\s+{re.escape(name)}\s*=\s*(?:async\s*)?function\s*\(",
    ):
        opening = re.search(form, source)
        if opening:
            return _balanced(source, opening.end() - 1)
    return None


def _balanced(source: str, opening: int) -> str | None:
    """What sits between the bracket at `opening` and its partner, or None."""
    depth = 0
    for index in range(opening, len(source)):
        character = source[index]
        if character in "([{":
            depth += 1
        elif character in ")]}":
            depth -= 1
            if depth == 0:
                return source[opening + 1 : index]
    return None


def _separate_arguments(text: str) -> list[str]:
    """`text` split on the commas that are not inside a bracket or a string."""
    found: list[str] = []
    current = ""
    depth = 0
    quote: str | None = None
    for character in text:
        if quote:
            current += character
            if character == quote:
                quote = None
            continue
        if character in "\"'`":
            quote = character
            current += character
            continue
        if character in "([{":
            depth += 1
        elif character in ")]}":
            depth -= 1
        if character == "," and depth == 0:
            found.append(current)
            current = ""
        else:
            current += character
    if current.strip():
        found.append(current)
    return [argument for argument in found if argument.strip()]


def a_call_the_signature_does_not_accept(
    relative_path: str, content: str, project: "Path | None" = None
) -> str | None:
    """Why a call in this test passes more than the function takes, or None.

    JavaScript drops extra arguments in silence, so the mismatch never raises
    on its own - the test either fails somewhere unrelated or, worse, passes
    on a premise that was never established.

    Run 9bd3a091 wrote

        addTask(storage, 'Active Task', '', false)

    against `addTask({ title, description = '' }, storage)`. Every argument
    landed one place left: `storage` arrived as the destructured parameter and
    the string `'Active Task'` as the storage, and all three cases died on
    `storage.setItem is not a function` - the run's only discoverable suite,
    nothing of the product tested. The same call was written into two files.

    Run 9506d3ab is the quieter half of the pair: `addTask('Completed Task
    1', '', true)` against `addTask(title, description)`. The `true` meant to
    mark the task complete was dropped, nothing threw, and the assertions
    about completed tasks ran against tasks that were never completed.

    Only when the import is local and resolvable, the definition is plain
    enough to read, and it takes no rest parameter - a signature this cannot
    read with certainty is one it says nothing about.
    """
    if not _is_test_name(relative_path):
        return None
    if project is None:
        return None
    for match in _NAMED_LOCAL_IMPORT.finditer(content):
        names, module = match.group(1), match.group(2)
        if names is None:
            names, module = match.group(3), match.group(4)
        source = _module_named(project, module)
        if source is None:
            continue
        for name in (part.strip().split(" as ")[-1].strip() for part in names.split(",")):
            if not name.isidentifier():
                continue
            declared = _declares(source, name)
            if declared is None or "..." in declared:
                continue
            takes = len(_separate_arguments(declared))
            for call in re.finditer(rf"(?<![.\w]){re.escape(name)}\s*\(", content):
                arguments = _balanced(content, call.end() - 1)
                if arguments is None:
                    continue
                passes = len(_separate_arguments(arguments))
                if passes > takes:
                    return (
                        f"This calls `{name}` with {passes} arguments and "
                        f"`{name}` is declared as `{name}({declared.strip()})`, "
                        f"which takes {takes}. JavaScript discards the extra "
                        "ones without a word, so the call does not fail here - "
                        "it either dies further in on an argument that arrived "
                        "in the wrong position, or passes while the thing it "
                        "meant to set up never happened. Read the definition "
                        "and call it the way it is written."
                    )
    return None


def _module_named(project: "Path", specifier: str) -> str | None:
    """The text of the local module `specifier` resolves to, or None."""
    target = project / specifier
    for candidate in (
        target,
        *(target.with_suffix(suffix) for suffix in (".js", ".mjs", ".cjs")),
        *(target.parent / (target.name + suffix) for suffix in (".js", ".mjs", ".cjs")),
    ):
        try:
            if candidate.is_file():
                return candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return None


def a_suite_calling_a_global_node_does_not_define(
    relative_path: str, content: str, project: "Path | None" = None
) -> str | None:
    """Why every case in this suite throws before it runs, or None.

    Jest, Vitest and Mocha inject `test`, `it` and `describe` as globals.
    `node --test` does not - they are exports of `node:test`, and a file that
    calls one without importing it throws on the first case. Verified in the
    worker image on Node 20.20.2: a well-formed suite with a real assertion,
    using `describe`/`it` and importing neither, reports

        # ReferenceError: describe is not defined
        # pass 0   # fail 1

    `_suites_calling_a_global_node_does_not_define` already finds this, at a
    milestone review. It cost run d6297b2f and run 0afef410 a round each
    before that, and four of the fifty-eight stored workspaces still carry it.
    This is the same question asked at the write, where one import fixes it.

    The patterns are the cross-file check's own, imported rather than copied,
    so the two cannot drift - `test_the_two_readings_of_a_suite_global_agree`
    pins them together.
    """
    if not _is_test_name(relative_path):
        return None
    try:
        from app.analysis.integration_checks import (
            _CALLS_A_SUITE_GLOBAL,
            _DEFINES_ITS_OWN,
            _IMPORTS_FROM_NODE_TEST,
            _PROVIDES_TEST_GLOBALS,
        )
    except Exception:  # noqa: BLE001
        return None
    if not relative_path.lower().endswith((".js", ".mjs", ".cjs")):
        return None
    called = _CALLS_A_SUITE_GLOBAL.search(content)
    if not called or _IMPORTS_FROM_NODE_TEST.search(content):
        return None
    if _DEFINES_ITS_OWN.search(content):
        return None
    # A project whose runner does provide the globals is not affected, so this
    # can only speak where it is true. The manifest is rarely beside the suite
    # - `src/sprint2.test.js` and `tests/tasks.test.js` both sit a level below
    # the `package.json` that declares vitest - so this walks up to find it,
    # which is the difference between agreeing with the cross-file check and
    # reporting three working suites as broken.
    if project is not None:
        try:
            for directory in (project, *project.parents[:3]):
                for neighbour in directory.iterdir():
                    low = neighbour.name.lower()
                    if low.startswith(("jest.config", "vitest.config", ".mocharc")):
                        return None
                    if neighbour.name == "package.json":
                        manifest = neighbour.read_text(
                            encoding="utf-8", errors="replace"
                        ).lower()
                        if any(
                            re.search(rf"(?<![\w-]){runner}(?![\w-])", manifest)
                            for runner in _PROVIDES_TEST_GLOBALS
                        ):
                            return None
        except OSError:
            return None
    name = called.group(1)
    return (
        f"This calls `{name}(...)` and nothing imports `{name}`. Jest and "
        f"Vitest inject it as a global; `node --test` does not - it is an "
        f"export of `node:test`, so every case in this file throws "
        f"`ReferenceError: {name} is not defined` and the suite cannot run at "
        f"all. Add `import {{ {name} }} from 'node:test';` at the top."
    )


def a_name_this_test_defines_instead_of_importing(
    relative_path: str, content: str, project: "Path | None" = None
) -> str | None:
    """Why this suite tests a copy rather than the product, or None.

    A test that reimplements what it is testing passes whatever the
    application does - the assertions are real, the logic is real, and none of
    it is connected to the product. Every gate downstream reads the pass.

    `_redefined_instead_of_imported` finds it at a milestone review, and run
    1cd4597b is why that is not enough: `crud.test.mjs` and `filter.test.mjs`
    each defined their own `loadTasks` beside an import of the module that
    exports it, the finding was reported at the end of two consecutive
    sprints, and both files still carried it. Five more workspaces end this
    way, run 1ae7671d with eight files.

    The evidence is all there at the write: the file names a relative module,
    so that module is on disk, and whether it defines a name that module
    already exports is decidable then. That is what separates this from the
    findings 4t says cannot move earlier.

    Shares its patterns with the cross-file check by import rather than by
    copy; `test_the_two_readings_of_a_redefined_name_agree` pins the pair.
    """
    if not _is_test_name(relative_path):
        return None
    if project is None:
        return None
    try:
        from app.analysis.file_kinds import is_application
        from app.analysis.integration_checks import (
            _TOP_LEVEL_CONST_FN,
            _TOP_LEVEL_FUNCTION,
            _names_bound_from_a_relative_module,
        )
    except Exception:  # noqa: BLE001
        return None

    defined = set(_TOP_LEVEL_FUNCTION.findall(content)) | set(
        _TOP_LEVEL_CONST_FN.findall(content)
    )
    if not defined:
        return None
    imported = _names_bound_from_a_relative_module(content)
    # The module is not always beside the suite: `src/manual_regression.test.js`
    # and `tests/tasks.test.js` both sit a level below the file they copy from,
    # and looking only in the suite's own directory missed both. Bounded, so a
    # large repository is not walked on every write.
    try:
        neighbours = [
            path
            for directory in (project, *project.parents[:2])
            for path in sorted(directory.iterdir())
            if path.is_file()
            and path.suffix.lower() in {".js", ".mjs", ".cjs", ".ts"}
            and is_application(path.name)
        ]
    except OSError:
        return None
    for path in neighbours:
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        theirs = set(_TOP_LEVEL_FUNCTION.findall(source)) | set(
            _TOP_LEVEL_CONST_FN.findall(source)
        )
        shared = sorted(name for name in defined & theirs if name not in imported)
        if not shared:
            continue
        named = ", ".join(shared[:4])
        return (
            f"This defines {named} itself, and `{path.name}` exports "
            f"{'that name' if len(shared) == 1 else 'those names'} too. The "
            "assertions here run against this file's copy, so they pass "
            f"whatever `{path.name}` does - a green suite that is not evidence "
            "about the product."
            + (
                " Importing the module and then defining one of its names "
                "beside it leaves the assertions pointing at the copy."
                if imported
                else ""
            )
            + f" Import {named} from `./{path.name}` instead of defining "
            "it here."
        )
    return None
