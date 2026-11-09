"""A test asserting an exact count on a list other tests write to depends on what ran before it, not on the product.

Measured on one run: a locked suite shared one service among its tests, one test expected exactly 2 from a list and
received 8, and six fix stages went at it before any dispute. These files are read as text; nothing here runs them.
"""
from __future__ import annotations

import re

import pytest

from app.acceptance import junit, spec_dry_run, suite
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

HEAD = "import { test, expect } from '@playwright/test';\n"
WRITER = HEAD + """test('[AC-1] creates a note', async ({ request }) => {
  const made = await request.post('/notes', { data: { title: 'a' } });
  expect(made.status()).toBe(201);
});
"""
INLINE = HEAD + """test('[AC-2] lists two', async ({ request }) => {
  await request.post('/notes', { data: { title: 'b' } });
  const listBefore = await request.get('/notes');
  expect((await listBefore.json()).length).toBe(2);
});
"""
THROUGH_A_VARIABLE = HEAD + """test('[AC-2] lists two', async ({ request }) => {
  const res = await request.get('/notes');
  const list = await res.json();
  expect(list.length).toBe(2);
});
"""
HAS_LENGTH = HEAD + """test('[AC-2] lists two', async ({ request }) => {
  const res = await request.get('/notes');
  const list = await res.json();
  expect(list).toHaveLength(2);
});
"""
EMPTY = HEAD + """test('[AC-2] starts empty', async ({ request }) => {
  const res = await request.get('/notes');
  expect(await res.json()).toEqual([]);
});
"""


def _suite(tmp_path, files, pack="node-hono-native-api"):
    contract.write(tmp_path, pack_named(pack), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (folder / name).write_text(text)
    return tmp_path


def _found(tmp_path, reader, **more):
    return suite.tests_that_count_a_list_other_tests_write_to(
        _suite(tmp_path, {"a.spec.js": WRITER, "b.spec.js": reader, **more}))


def _ran(*tests):
    return suite.AcceptanceResult(ran=True, report=junit.Report(tests=list(tests), found=True))


def _test(name, outcome, message=""):
    return junit.TestResult(name=name, outcome=outcome, message=message)


def test_the_round_and_the_review_are_told_of_the_measured_count(tmp_path, monkeypatch):
    monkeypatch.setattr(spec_dry_run, "findings", lambda root: [])
    root = _suite(tmp_path, {"a.spec.js": WRITER, "b.spec.js": INLINE})
    found = [f for f in suite.tests_that_cannot_pass(root, suite.AcceptanceResult(ran=False)) if "exactly 2" in f]
    assert len(found) == 1
    assert "b.spec.js" in found[0] and "`/notes`" in found[0] and "`.filter`" in found[0]
    assert "toBeGreaterThanOrEqual" in found[0]
    assert not BANNED.search(found[0])


@pytest.mark.parametrize("reader", [INLINE, THROUGH_A_VARIABLE, HAS_LENGTH, EMPTY])
def test_each_form_of_an_exact_count_is_found(tmp_path, reader):
    [found] = _found(tmp_path, reader)
    assert "b.spec.js" in found and not BANNED.search(found)


def test_a_write_through_a_helper_in_another_file_counts(tmp_path):
    helper = "export async function makeNote(request) { return request.post('/notes', { data: { title: 'x' } }); }\n"
    writer = HEAD + "import { makeNote } from './helper.js';\ntest('[AC-1] one', async ({ request }) => { await makeNote(request); });\n"
    root = _suite(tmp_path, {"helper.js": helper, "a.spec.js": writer, "b.spec.js": THROUGH_A_VARIABLE})
    assert len(suite.tests_that_count_a_list_other_tests_write_to(root)) == 1


@pytest.mark.parametrize("right", [
    # Filtered to its own records.
    """test('[AC-2] mine', async ({ request }) => {
  const res = await request.get('/notes');
  const list = await res.json();
  const mine = list.filter((n) => n.title === 'mine');
  expect(mine.length).toBe(2);
});""",
    """test('[AC-2] mine', async ({ request }) => {
  const res = await request.get('/notes');
  const list = (await res.json()).filter((n) => n.title === 'mine');
  expect(list).toHaveLength(2);
});""",
    """test('[AC-2] mine', async ({ request }) => {
  const res = await request.get('/notes');
  let list = await res.json();
  list = list.filter((n) => n.title === 'mine');
  expect(list.length).toBe(2);
});""",
    # Against an earlier count, or at least.
    """test('[AC-2] grows', async ({ request }) => {
  const before = await (await request.get('/notes')).json();
  await request.post('/notes', { data: { title: 'c' } });
  const after = await (await request.get('/notes')).json();
  expect(after.length).toBe(before.length + 1);
});""",
    """test('[AC-2] at least', async ({ request }) => {
  const list = await (await request.get('/notes')).json();
  expect(list.length).toBeGreaterThanOrEqual(2);
});""",
    # A service of its own, in the test.
    """test('[AC-6] survives', async ({ request }) => {
  const first = await startService();
  const res = await request.get('/notes');
  const list = await res.json();
  expect(list.length).toBe(1);
  await first.stop();
});""",
    # The test empties the list first, itself or through a helper.
    """test('[AC-2] two', async ({ request }) => {
  await clearAll(request);
  const list = await (await request.get('/notes')).json();
  expect(list.length).toBe(2);
});""",
    """test('[AC-2] two', async ({ request }) => {
  const old = await (await request.get('/notes')).json();
  for (const n of old) { await request.delete(`/notes/${n.id}`); }
  const list = await (await request.get('/notes')).json();
  expect(list.length).toBe(2);
});""",
    # Narrowed by the request: a query, a filter option, a nested route.
    """test('[AC-2] two', async ({ request }) => {
  const res = await request.get('/notes?tag=mine');
  expect((await res.json()).length).toBe(2);
});""",
    """test('[AC-2] two', async ({ request }) => {
  const res = await request.get('/notes', { params: { tag: 'mine' } });
  expect((await res.json()).length).toBe(2);
});""",
    # A list scoped to who is signed in.
    """test('[AC-2] two', async ({ request }) => {
  const res = await request.get('/notes', { headers: { Authorization: `Bearer ${made}` } });
  expect((await res.json()).length).toBe(2);
});""",
    # Not the list: a field of something else, and a route nothing else writes to.
    """test('[AC-2] one', async ({ request }) => {
  const res = await request.get('/notes');
  expect((await res.json()).total).toBe(2);
});""",
    """test('[AC-2] none', async ({ request }) => {
  const res = await request.get('/archive');
  expect((await res.json()).length).toBe(0);
});""",
])
def test_a_count_that_is_right_is_left_alone(tmp_path, right):
    assert _found(tmp_path, HEAD + right + "\n") == []


def test_only_the_test_itself_writing_there_is_left_alone(tmp_path):
    root = _suite(tmp_path, {"b.spec.js": INLINE})
    assert suite.tests_that_count_a_list_other_tests_write_to(root) == []


def test_a_hook_that_empties_the_list_is_read(tmp_path):
    hook = HEAD + """async function cleanAll(request) {
  const res = await request.get('/notes');
  for (const n of await res.json()) { await request.delete(`/notes/${n.id}`); }
}
test.beforeEach(async ({ request }) => { await cleanAll(request); });
""" + THROUGH_A_VARIABLE.removeprefix(HEAD)
    assert _found(tmp_path, hook) == []


def test_a_file_with_a_server_of_its_own_neither_reads_nor_writes_the_shared_list(tmp_path):
    own = HEAD + """import { startService } from './service.cjs';
let svc;
test.beforeAll(async () => { svc = await startService(); });
test('[AC-1] writes', async ({ request }) => {
  await request.post('/notes', { data: { title: 'a' } });
});
"""
    assert suite.tests_that_count_a_list_other_tests_write_to(_suite(tmp_path, {"a.spec.js": own, "b.spec.js": INLINE})) == []
    assert suite.tests_that_count_a_list_other_tests_write_to(
        _suite(tmp_path, {"a.spec.js": WRITER, "b.spec.js": own + THROUGH_A_VARIABLE.removeprefix(HEAD)})) == []


def test_a_write_in_a_helper_only_this_test_calls_is_not_elsewhere(tmp_path):
    only = HEAD + """async function makeNote(request) { return request.post('/notes', { data: { title: 'x' } }); }
test('[AC-2] two', async ({ request }) => {
  await makeNote(request);
  const list = await (await request.get('/notes')).json();
  expect(list.length).toBe(2);
});
"""
    assert suite.tests_that_count_a_list_other_tests_write_to(_suite(tmp_path, {"b.spec.js": only})) == []


def test_a_suite_of_a_kind_without_one_shared_service_is_left_alone(tmp_path):
    root = _suite(tmp_path, {"a.spec.js": WRITER, "b.spec.js": INLINE}, pack="browser-javascript")
    assert suite.tests_that_count_a_list_other_tests_write_to(root) == []


TITLE = "[AC-2] lists two"
TOO_MANY = "Error: expect(received).toBe(expected)\n\nExpected: \x1b[32m2\x1b[39m\nReceived: \x1b[31m8\x1b[39m\n"
TOO_FEW = "Error: expect(received).toBe(expected)\n\nExpected: 2\nReceived: 1\n"
STATUS = "Error: expect(received).toBe(expected)\n\nExpected: 200\nReceived: 500\n"


def _with_results(tmp_path, reader, *tests):
    root = _suite(tmp_path, {"a.spec.js": WRITER, "b.spec.js": reader})
    return suite.tests_that_count_a_list_other_tests_write_to(root, _ran(*tests))


def test_a_test_known_to_pass_is_not_named(tmp_path):
    assert _with_results(tmp_path, INLINE, _test(TITLE, "passed"), _test("[AC-1] creates a note", "passed")) == []


def test_a_test_whose_message_shows_more_came_back_is_named(tmp_path):
    assert len(_with_results(tmp_path, INLINE, _test(TITLE, "failed", TOO_MANY), _test("[AC-1] creates a note", "passed"))) == 1


def test_a_nonempty_list_where_an_empty_one_was_expected_is_named(tmp_path):
    message = "- Expected  - 1\n+ Received  + 3\n\n- Array []\n+ Array [\n+   \"x\",\n+ ]\n"
    assert len(_with_results(tmp_path, EMPTY.replace("starts empty", "lists two"), _test(TITLE, "failed", message), _test("x", "passed"))) == 1


@pytest.mark.parametrize("message", [TOO_FEW, STATUS])
def test_fewer_records_or_a_failure_before_the_count_are_the_product_s(tmp_path, message):
    assert _with_results(tmp_path, INLINE, _test(TITLE, "failed", message), _test("[AC-1] creates a note", "passed")) == []


def test_a_locked_suite_with_nothing_passing_still_needs_the_proof(tmp_path):
    root = _suite(tmp_path, {"a.spec.js": WRITER, "b.spec.js": INLINE})
    suite.lock(root)
    assert suite.tests_that_count_a_list_other_tests_write_to(root, _ran(_test(TITLE, "failed", STATUS))) == []


def test_before_any_product_answers_the_shape_alone_is_named_to_the_writer(tmp_path):
    assert len(_with_results(tmp_path, INLINE, _test(TITLE, "failed", "ECONNREFUSED"))) == 1


def test_a_test_not_in_the_report_is_not_named(tmp_path):
    assert _with_results(tmp_path, INLINE, _test("something else", "failed", TOO_MANY)) == []
