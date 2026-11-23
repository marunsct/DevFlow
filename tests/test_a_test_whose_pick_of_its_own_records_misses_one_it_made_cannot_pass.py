"""A test that picks its own records out of a list by a piece of text that fewer of the values it made hold than the
count it asserts cannot pass.

Measured on one run: a locked test made "Work <id>", "Personal <id>" and "Work Two <id>", kept the listed records whose
title included "Work <id>" and expected two. "Work Two <id>" never includes it, so the test failed a right product
through two attempts of fixes, and the suite dispute ruled it right twice, even when told to look for exactly this.
Only text is read here and the reports are made up: no suite runs.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.acceptance import junit, suite
from app.agents import suite_dispute
from app.stacks import contract, pack_named
from app.stacks.packs import _javascript as js

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
CORPUS = Path(__file__).parent / "fixtures" / "locked_suites"
TITLE = "[AC-4] filtering by tag returns only matching records"
HELPER = """async function createRecord(request, { title, url, tag, uniqueSuffix }) {
  const resp = await request.post('/api/records', { data: { title, url: `${url}?u=${uniqueSuffix}`, tag } });
  expect(resp.status()).toBe(201);
  return resp.json();
}
"""


def _a_test(pick: str = "b.title.includes(`Work ${id}`)", second: str = "`Work Two ${id}`", count: str = "2",
            marker: str = "crypto.randomUUID()") -> str:
    return f"""import {{ test, expect }} from '@playwright/test';
import crypto from 'node:crypto';

{HELPER}
test('{TITLE}', async ({{ request }}) => {{
  const id = {marker};
  await createRecord(request, {{ title: `Work ${{id}}`, url: 'https://a.test', tag: 'work', uniqueSuffix: `${{id}}-w1` }});
  await createRecord(request, {{ title: `Personal ${{id}}`, url: 'https://b.test', tag: 'personal', uniqueSuffix: 'p' }});
  await createRecord(request, {{ title: {second}, url: 'https://c.test', tag: 'work', uniqueSuffix: `${{id}}-w2` }});
  const filteredResp = await request.get('/api/records?tag=work');
  const filtered = await filteredResp.json();
  const myWork = filtered.filter((b) => {pick});
  expect(myWork.length).toBe({count});
}});
"""


MEASURED = _a_test()


def _workspace(tmp_path: Path, spec: str) -> Path:
    contract.write(tmp_path, pack_named("fullstack-node"), "records", "Records")
    (tmp_path / "records" / "acceptance").mkdir(parents=True)
    (tmp_path / "records" / "acceptance" / "records.spec.js").write_text(spec, encoding="utf-8")
    return tmp_path


def _failed(name: str = TITLE) -> suite.AcceptanceResult:
    report = junit.Report(tests=[junit.TestResult(name=name, outcome="failed", message="Expected: 2 Received: 1")],
                          found=True)
    return suite.AcceptanceResult(ran=True, report=report)


def _cannot_pass(root: Path) -> list[str]:
    result = _failed()
    return [item for item in suite.findings_that_reopen(root, result, suite.tests_that_cannot_pass(root, result))
            if "a marker every one of them carries whole" in item]


def test_the_measured_test_goes_back_naming_its_line_the_pick_and_the_value_it_misses(tmp_path):
    root = _workspace(tmp_path, MEASURED)
    suite.lock(root)

    found = _cannot_pass(root)

    assert len(found) == 1
    assert found[0].startswith("`records/acceptance/records.spec.js` line 17 ")
    assert "b.title.includes(`Work ${id}`)" in found[0]
    assert '"`Work Two ${id}`"' in found[0] and "expects 2" in found[0] and "only 1 can pass" in found[0]
    assert "b.title.includes(id)" in found[0]


@pytest.mark.parametrize("spec", [
    # Picked by the marker every record carries whole.
    _a_test(pick="b.title.includes(id)"),
    # Both titles hold what it picks by.
    _a_test(second="`Work ${id} two`"),
    # The count asserted is what the values can give.
    _a_test(count="1"),
    # The marker is not made up at run time, so records other tests made with it may be listed too.
    _a_test(marker="'fixed-marker'"),
], ids=["whole-marker", "both-match", "count-it-can-give", "marker-not-made-at-run-time"])
def test_a_test_whose_pick_can_keep_the_count_is_left_alone(tmp_path, spec):
    root = _workspace(tmp_path, spec)
    suite.lock(root)
    assert _cannot_pass(root) == []


@pytest.mark.parametrize("spec", [
    # A count worked out at run time.
    _a_test(count="before + 2"),
    # A value not written out in the test.
    _a_test(second="titles[1]"),
    # A write repeated by a loop makes two records that both pass, so three can.
    _a_test(count="3").replace("  const filteredResp", "  for (const n of ['a', 'b']) await createRecord("
                               "request, { title: `Work ${id}`, url: 'u', tag: 'work', uniqueSuffix: n });\n"
                               "  const filteredResp"),
    # A write through a function the file does not define.
    MEASURED.replace(HELPER, "import { createRecord } from './helpers.js';\n"),
    # Something taken in from elsewhere, given the marker, may make records of its own that pass.
    _a_test(count="3").replace(HELPER, HELPER + "import { seedMore } from './seed.js';\n").replace(
        "  const filteredResp", "  await seedMore(id);\n  const filteredResp"),
], ids=["computed-count", "value-not-written-out", "write-in-a-loop", "helper-from-elsewhere", "taken-in"])
def test_a_test_not_read_whole_is_left_alone(spec):
    assert js.own_records_a_pick_misses(spec) == []


def test_a_write_given_its_values_in_place_is_read_too():
    spec = """test('[AC-4] filter by tag', async ({ request }) => {
  const id = crypto.randomUUID();
  await request.post('/api/records', { data: { title: `Work ${id}`, tag: 'work' } });
  await request.post('/api/records', { data: { title: `Work Two ${id}`, tag: 'work' } });
  const listed = await (await request.get('/api/records?tag=work')).json();
  expect(listed.filter((b) => b.title.startsWith(`Work ${id}`))).toHaveLength(2);
});
"""
    assert js.own_records_a_pick_misses(spec) == [
        (6, "b.title.startsWith(`Work ${id}`)", "title", 2, 1, ("`Work Two ${id}`",), "id")]


def test_the_finding_speaks_of_the_test_in_plain_words(tmp_path):
    root = _workspace(tmp_path, MEASURED)
    finding = _cannot_pass(root)[0]
    assert "about the test, not the product" in finding
    assert not BANNED.search(finding)


def test_the_stored_suites_that_passed_their_hidden_tests_give_no_finding():
    found = {str(path.relative_to(CORPUS)): hits
             for path in sorted(CORPUS.rglob("*.spec.*"))
             if (hits := js.own_records_a_pick_misses(path.read_text(encoding="utf-8", errors="replace")))}
    assert len(list(CORPUS.rglob("*.spec.*"))) >= 100
    assert found == {}


def test_the_dispute_is_told_what_the_code_shows(tmp_path):
    root = _workspace(tmp_path, MEASURED)
    shown = suite.what_the_code_shows_of(root, [TITLE, "[AC-1] save a record"])

    text = suite_dispute.build_dispute_request(
        [(TITLE, "AC-4: x", "m")], "code", "brief", found_in_the_code=[finding for _, finding in shown],
    )["messages"][0]["content"]

    assert [name for name, _ in shown] == [TITLE]
    assert "a marker every one of them carries whole" in text and "cannot pass as it is written" in text


def test_a_dispute_that_calls_the_test_sound_still_reopens_it(tmp_path):
    from workflow_nodes import a_dispute

    root = _workspace(tmp_path, MEASURED)
    spec = root / "records" / "acceptance" / "records.spec.js"
    judged: list[str] = []

    def the_judge(state, config, *, initial_request, output_key, **kwargs):
        judged.append(" ".join(str(message["content"]) for message in initial_request["messages"]))
        return {output_key: object()}

    _, asked = a_dispute(tmp_path, [(TITLE, "AC-4: x", "Expected: 2 Received: 1")], [], reopened={}, patches={
        "app.acceptance.suite.suite_files": lambda _: [spec],
        "app.graph.workflow._run_gated_agent": the_judge,
    })

    assert judged and "a marker every one of them carries whole" in judged[0]
    assert len(asked["reopen"]) == 1
    assert [item for item in asked["reopen"][0]["broken"] if item.startswith(f"`{TITLE}` cannot pass")]


def test_every_pack_that_reads_locked_suites_reads_this_too():
    for name in ("fullstack-node", "browser-javascript", "browser-react"):
        assert pack_named(name).own_records_a_pick_misses is js.own_records_a_pick_misses
