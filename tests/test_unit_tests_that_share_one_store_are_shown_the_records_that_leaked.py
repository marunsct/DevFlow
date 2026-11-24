"""Unit tests that share one store are shown the records that leaked between them (LF.1316).

Measured on a full-stack run: a store's node:test file failed with "6 !== 1" and with six records - titled as the
file's other tests titled what they made - where `[]` was expected. One store file served the whole test file, so each
test's records stayed for the next; the fixer held to test files rewrote it five times over two rounds, about six
minutes each, and never gave each test an empty store. It is one root of the recurring note that a product's own unit
tests ship failing.

So whoever writes or repairs unit tests is told that a test that stores data starts from an empty store of its own,
and a fixer of such failing tests is shown the evidence: the records that leaked and the tests that made them.
"""

from __future__ import annotations

import re
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.acceptance.junit import TestResult
from app.stacks import contract, pack_named

import the_fix_stage

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
EFFECTS = Path(__file__).resolve().parent.parent / "scripts" / "loop" / "effects.py"
HEADING = "These unit tests share stored data"

NODE_STORE_TEST = """const { test, describe } = require('node:test');
const assert = require('node:assert/strict');
const store = require('../src/store');

describe('store', () => {
  test('creates bookmarks', () => {
    store.create({ title: 'First', url: 'https://a.example', tag: 'misc' });
    store.create({ title: 'Second', url: 'https://b.example', tag: 'misc' });
    assert.equal(store.list().length, 2);
  });

  test('filters by tag', () => {
    store.create({ title: 'Work 1', url: 'https://w.example', tag: 'work' });
    store.create({ title: 'Personal 1', url: 'https://p.example', tag: 'personal' });
    assert.equal(store.list({ tag: 'work' }).length, 1);
  });

  test('a new bookmark is listed once', () => {
    store.create({ title: 'Only', url: 'https://o.example', tag: 'solo' });
    assert.equal(store.list().length, 1);
  });

  test('a fresh store lists nothing', () => {
    assert.deepEqual(store.list(), []);
  });
});
"""
NODE_STORE = """const fs = require('node:fs');
const path = require('node:path');
const DATA_DIR = process.env.DATA_DIR || path.join(__dirname, '..', 'data');
const FILE = path.join(DATA_DIR, 'bookmarks.json');
function load() { try { return JSON.parse(fs.readFileSync(FILE, 'utf8')); } catch { return []; } }
function create(b) { const all = load(); all.push(b); fs.mkdirSync(DATA_DIR, { recursive: true }); fs.writeFileSync(FILE, JSON.stringify(all)); return b; }
function list(filter = {}) { return load().filter(b => !filter.tag || b.tag === filter.tag); }
module.exports = { create, list };
"""


def _record(title: str, url: str, tag: str) -> str:
    return f"+   {{\n+     id: '5fbe27aa-00ab-494a',\n+     tag: '{tag}',\n+     title: '{title}',\n+     url: '{url}'\n+   }}"


#: `node --test --test-reporter=junit` on the file above, as Node 24 writes it (stack frames shortened).
COUNT_MESSAGE = "Expected values to be strictly equal:\n\n5 !== 1"
COUNT_BODY = """[Error [ERR_TEST_FAILURE]: Expected values to be strictly equal:

5 !== 1
] {
  code: 'ERR_TEST_FAILURE',
  failureType: 'testCodeFailure',
  cause: AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:

  5 !== 1

      at TestContext.<anonymous> (/workspace/bookmarks/tests/store.test.js:21:12) {
    generatedMessage: true,
    code: 'ERR_ASSERTION',
    actual: 5,
    expected: 1,
    operator: 'strictEqual',
    diff: 'simple'
  }
}"""
LIST_DIFF = ("Expected values to be strictly deep-equal:\n+ actual - expected\n\n+ [\n" + ",\n".join([
    _record("First", "https://a.example", "misc"), _record("Second", "https://b.example", "misc"),
    _record("Work 1", "https://w.example", "work"), _record("Personal 1", "https://p.example", "personal"),
    _record("Only", "https://o.example", "solo")]) + "\n+ ]\n- []")
LIST_BODY = f"""[Error [ERR_TEST_FAILURE]: {LIST_DIFF}
] {{
  code: 'ERR_TEST_FAILURE',
  cause: AssertionError [ERR_ASSERTION]: {LIST_DIFF}
      at TestContext.<anonymous> (/workspace/bookmarks/tests/store.test.js:25:12) {{
    actual: [ [Object], [Object], [Object], [Object], [Object] ],
    expected: [],
    operator: 'deepStrictEqual'
  }}
}}"""


def _attr(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;").replace("\n", "&#10;")


def _node_report(count=(COUNT_MESSAGE, COUNT_BODY), listing=(LIST_DIFF, LIST_BODY)) -> str:
    where = 'classname="test" file="/workspace/bookmarks/tests/store.test.js"'
    return f"""<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="store" tests="4" failures="2">
    <testcase name="creates bookmarks" time="0.004" {where}/>
    <testcase name="filters by tag" time="0.001" {where}/>
    <testcase name="a new bookmark is listed once" time="0.001" {where}>
      <failure type="testCodeFailure" message="{_attr(count[0])}">{count[1].replace('&', '&amp;').replace('<', '&lt;')}</failure>
    </testcase>
    <testcase name="a fresh store lists nothing" time="0.001" {where}>
      <failure type="testCodeFailure" message="{_attr(listing[0])}">{listing[1].replace('&', '&amp;').replace('<', '&lt;')}</failure>
    </testcase>
  </testsuite>
</testsuites>
"""


def _node_workspace(root: Path, report: str | None = None, product: str = NODE_STORE) -> Path:
    """A full-stack Node workspace whose store tests share one store file, with its unit run's report."""
    contract.write(root, pack_named("fullstack-node"), "bookmarks", "Bookmarks")
    for path, text in {"bookmarks/tests/store.test.js": NODE_STORE_TEST, "bookmarks/src/store.js": product,
                       "bookmarks/test-results/unit.xml": report or _node_report()}.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text, encoding="utf-8")
    return root


def _unit_defect(*failing: TestResult):
    """The defect the harness raises for a failing unit run, from the runner's report it lists."""
    from app import ci
    from app.graph import workflow

    output = "# tests 4\n# fail 2\n" + ci.what_the_failing_unit_tests_say(list(failing))
    raised = workflow._the_unit_tests_fail(SimpleNamespace(delegated_tasks=[]), output, beside_a_green_suite=True)
    return the_fix_stage.a_defect(raised.description, actual_behavior=raised.actual_behavior, affected_files=[],
                                  owner="backend")


def _node_failures(root: Path):
    from app.acceptance import junit

    return [t for t in junit.read(root / "bookmarks/test-results/unit.xml").tests if t.outcome == "failed"]


# --- the fixer is shown the evidence ----------------------------------------------------------------------------


def test_node_store_tests_whose_counts_and_lists_grow_are_shown_the_records_other_tests_stored(tmp_path):
    root = _node_workspace(tmp_path)
    defect = _unit_defect(*_node_failures(root))

    _, seen = the_fix_stage.run(root, the_fix_stage.a_state(root, defect))

    [request] = seen.requests
    assert HEADING in request
    shown = request.split(HEADING, 1)[1]
    assert "bookmarks/tests/store.test.js" in shown
    assert "`First`" in shown and "`Second`" in shown and "`Work 1`" in shown
    assert "`creates bookmarks`" in shown and "`filters by tag`" in shown
    assert "`a fresh store lists nothing`" in shown and "`a new bookmark is listed once`" in shown
    assert "share one store" in shown
    # How a node:test file gives each test its own store, and the rule.
    assert "beforeEach" in shown and "mkdtempSync" in shown and "DATA_DIR" in shown
    assert "empty store of its own" in shown
    assert not BANNED.search(shown), shown


PYTEST_STORE_TEST = '''from app import store


def test_adds_an_item():
    store.add({"title": "Groceries"})
    store.add({"title": "Laundry"})
    assert len(store.all()) == 2


def test_a_single_item_is_counted_once():
    store.add({"title": "Dishes"})
    assert len(store.all()) == 1


def test_an_empty_store_lists_nothing():
    assert store.all() == []
'''


def test_pytest_tests_that_share_a_module_s_store_are_shown_the_same_evidence(tmp_path):
    (tmp_path / "items/tests").mkdir(parents=True)
    (tmp_path / "items/tests/test_store.py").write_text(PYTEST_STORE_TEST, encoding="utf-8")
    failing = [
        TestResult(name="test_a_single_item_is_counted_once", suite="tests.test_store", outcome="failed",
                   message="assert 3 == 1\n +  where 3 = len([{'title': 'Groceries'}, {'title': 'Laundry'}, "
                           "{'title': 'Dishes'}])"),
        TestResult(name="test_an_empty_store_lists_nothing", suite="tests.test_store", outcome="failed",
                   message="AssertionError: assert [{'title': 'Groceries'}, {'title': 'Laundry'}, "
                           "{'title': 'Dishes'}] == []\n  Left contains 3 more items, first extra item: "
                           "{'title': 'Groceries'}"),
    ]
    from app.analysis import shared_store_tests

    shown = shared_store_tests.for_a_fixer(tmp_path, _unit_defect(*failing))

    assert HEADING in shown and "items/tests/test_store.py" in shown
    assert "`Groceries`" in shown and "`Laundry`" in shown and "`Dishes`" in shown
    assert "`test_adds_an_item`" in shown and "`test_a_single_item_is_counted_once`" in shown
    assert "tmp_path" in shown and "monkeypatch.setenv" in shown


@pytest.mark.parametrize("count, listing, product", [
    # The count is smaller than expected, and the list holds a broken record no test wrote: a real fault.
    (("Expected values to be strictly equal:\n\n0 !== 1", COUNT_BODY.replace("5 !== 1", "0 !== 1")
      .replace("actual: 5", "actual: 0")),
     ("Expected values to be strictly deep-equal:\n+ actual - expected\n\n+ [\n+   {\n+     title: undefined\n+   }\n+ ]\n"
      "- []", "x"),
     NODE_STORE),
    # The values are other tests' but no count or list came back larger: a wrong order, say.
    (("Expected values to be strictly equal:\n\n'First' !== 'Only'", "x"),
     ("Expected values to be strictly equal:\n\n'Second' !== 'Only'", "x"), NODE_STORE),
    # The records in the list are ones the product seeds itself, in every store.
    (("Expected values to be strictly equal:\n\n2 !== 0", "x"),
     ("Expected values to be strictly deep-equal:\n+ actual - expected\n\n+ [\n+   { title: 'First' },\n"
      "+   { title: 'Second' }\n+ ]\n- []", "x"),
     NODE_STORE + "const SEEDED = [{ title: 'First' }, { title: 'Second' }];\n"),
], ids=["a-real-fault", "not-larger-than-expected", "records-the-product-seeds"])
def test_a_unit_test_failing_without_records_from_other_tests_is_given_no_such_section(tmp_path, count, listing,
                                                                                          product):
    root = _node_workspace(tmp_path, _node_report(count, listing), product)

    _, seen = the_fix_stage.run(root, the_fix_stage.a_state(root, _unit_defect(*_node_failures(root))))

    assert HEADING not in seen.requests[0]


def test_a_failing_test_s_listing_keeps_what_came_instead_of_what_was_expected():
    """The node:assert message of the measured run was cut to "expected: 1," with neither "5 !== 1" nor "actual: 5"."""
    from app import ci

    failing = TestResult(name="a new bookmark is listed once", outcome="failed",
                         message=COUNT_BODY + "\n" + "      at Test.run (node:internal/test_runner/test:1397:25)\n" * 12)

    listed = ci.what_the_failing_unit_tests_say([failing])

    assert "5 !== 1" in listed and "actual: 5" in listed


def test_the_effects_report_counts_a_fixer_shown_tests_sharing_one_store(tmp_path):
    from app.analysis import shared_store_tests

    root = _node_workspace(tmp_path)
    shown = shared_store_tests.for_a_fixer(root, _unit_defect(*_node_failures(root)))
    record = {"kind": "model_request", "messages": [{"role": "user", "content": "the fix request" + shown}]}

    lines = "\n".join(runpy.run_path(str(EFFECTS))["effects"]([record], ""))

    assert "   1  LF.1316 unit tests shown sharing one store" in lines


# --- each language's runner wording and test definitions are read --------------------------------------------------


@pytest.mark.parametrize("path, message", [
    ("t.test.js", "Expected values to be strictly equal:\n\n6 !== 1"),
    ("t.test.ts", "expect(received).toHaveLength(expected)\n\nExpected length: 1\nReceived length: 6"),
    ("test_t.py", "assert 6 == 1"),
    ("test_t.py", "AssertionError: 6 != 1"),
    ("t_test.go", "Error: \"[a b c]\" should have 1 item(s), but has 3"),
    ("t.rs", "assertion `left == right` failed\n  left: 6\n right: 1"),
    ("TTest.java", "expected: <1> but was: <6>"),
    ("TTest.java", "Expected size: 1 but was: 6 in:"),
    ("TTest.kt", "expected: <0> but was: <2>"),
    ("TTests.cs", "Assert.Equal() Failure: Values differ\nExpected: 1\nActual:   6"),
    ("t_spec.rb", "expected: 1\n     got: 6\n\n(compared using ==)"),
    ("TTest.php", "Failed asserting that actual size 6 matches expected size 1."),
], ids=["node", "jest", "pytest", "unittest", "go", "rust", "junit", "assertj", "kotlin", "xunit", "rspec", "phpunit"])
def test_a_count_larger_than_expected_is_read_in_each_runner_s_words(path, message):
    from app.analysis.shared_store_tests import shows_more_than_expected

    assert shows_more_than_expected(path, message)


@pytest.mark.parametrize("path, message", [
    ("t.test.js", "Expected values to be strictly equal:\n\n0 !== 1"),
    ("test_t.py", "assert 0 == 1"),
    ("TTest.java", "expected: <1> but was: <0>"),
    ("t.rs", "assertion `left == right` failed\n  left: 0\n right: 1"),
    ("t_spec.rb", "expected: 2\n     got: 1"),
], ids=["node", "pytest", "junit", "rust", "rspec"])
def test_a_count_smaller_than_expected_is_not_read_as_one_that_grew(path, message):
    from app.analysis.shared_store_tests import shows_more_than_expected

    assert not shows_more_than_expected(path, message)


@pytest.mark.parametrize("path, source, names", [
    ("t.test.js", "it('adds one', () => {});\ntest(\"lists all\", async () => {});", ["adds one", "lists all"]),
    ("test_t.py", "def test_adds():\n    pass\n\nasync def test_lists():\n    pass\n", ["test_adds", "test_lists"]),
    ("t_test.go", "func TestAdds(t *testing.T) {}\nfunc TestLists(t *testing.T) {}", ["TestAdds", "TestLists"]),
    ("t.rs", "#[test]\nfn adds() {}\n#[tokio::test]\nasync fn lists() {}", ["adds", "lists"]),
    ("TTest.java", "@Test\nvoid adds() {}\n@Test\npublic void lists() {}", ["adds", "lists"]),
    ("TTest.kt", "@Test\nfun `adds one`() {}\n@Test fun lists() {}", ["adds one", "lists"]),
    ("TTests.cs", "[Fact]\npublic void Adds() {}\n[Fact]\npublic async Task Lists() {}", ["Adds", "Lists"]),
    ("t_spec.rb", "it 'adds one' do\nend\nit \"lists all\" do\nend", ["adds one", "lists all"]),
    ("TTest.php", "public function testAdds(): void {}\npublic function testLists(): void {}", ["testAdds", "testLists"]),
], ids=["javascript", "python", "go", "rust", "java", "kotlin", "csharp", "ruby", "php"])
def test_each_language_s_tests_are_read_from_their_file(path, source, names):
    from app.analysis.shared_store_tests import tests_in

    assert [test.name for test in tests_in(path, source)] == names


# --- whoever writes or repairs unit tests is told the rule ---------------------------------------------------------


def test_the_testing_builder_is_told_a_test_that_stores_data_starts_from_an_empty_store():
    from app.agents.specialists import _system_prompt

    told = " ".join(_system_prompt("testing").split())

    assert "starts from an empty store of its own" in told and "never counts on what another test stored" in told


def test_the_acceptance_suite_s_writer_is_not_told_the_empty_store_rule():
    from app.agents.specialists import _system_prompt

    told = " ".join(_system_prompt("testing", writing_the_suite=True).split())

    assert "starts from an empty store of its own" not in told


def test_a_test_file_s_draft_is_told_the_rule_in_its_language_and_a_product_file_s_is_not(tmp_path):
    from app.graph import drafting

    order = SimpleNamespace(task_description="Bookmark store and its tests")

    test_draft = drafting.draft_request(tmp_path, "bookmarks/tests/store.test.js", order, None, None)
    python_draft = drafting.draft_request(tmp_path, "items/tests/test_store.py", order, None, None)
    code_draft = drafting.draft_request(tmp_path, "bookmarks/src/store.js", order, None, None)

    assert "starts from an empty store of its own" in test_draft and "beforeEach" in test_draft
    assert "starts from an empty store of its own" in python_draft and "tmp_path" in python_draft
    assert "starts from an empty store of its own" not in code_draft


def test_a_fixer_held_to_test_files_is_told_to_give_each_test_an_empty_store():
    from app.tools import tests_only_writes

    tests_only_writes.hold("run-1", "defect_fix_3_0")
    try:
        told = tests_only_writes.briefing("run-1", "defect_fix_3_0")
    finally:
        tests_only_writes.release("run-1", "defect_fix_3_0")

    assert "share one store" in told and "empty store of its own" in told
    assert not BANNED.search(told), told


def test_the_empty_store_rules_and_every_language_s_wording_avoid_the_banned_words():
    from app.agents.own_store_rule import FOR_A_FIXER, FOR_TEST_WRITERS
    from app.stacks.languages import LANGUAGES, Gap

    wording = [row.fresh_store for row in LANGUAGES if not isinstance(row.fresh_store, Gap)]

    assert len(wording) == len(LANGUAGES)
    for text in (FOR_TEST_WRITERS, FOR_A_FIXER, *wording):
        assert not BANNED.search(text), text
