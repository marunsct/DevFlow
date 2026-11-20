"""A harness finding that comes back unchanged after a repair goes to the QA lead, not to the suite's writers again.

Per-role audit 2026-11-20: 187 findings came back unchanged three or more times; one false finding was sent back seven
rounds running and held a repair open for ten model minutes. After one repair round leaves the same check's same
finding on the same test, the next round gives it to the QA lead as a suspected false positive and records it.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from app.acceptance import check_findings
from app.stacks import contract, pack_named
from workflow_nodes import an_acceptance_review

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
SPECIFICATION = SimpleNamespace(interface_contract=["AC-2 DELETE /notes/{id} -> 204 or 404"])
SUITE = """test('[AC-1] adds', async () => {});
test('[AC-2] delete answers json', async ({ request }) => {
  const res = await request.delete('/notes/1');
  expect(res.headers()['content-type']).toContain('application/json');
});
test('[AC-3] persists', async () => {});
"""
#: The same suite after a repair that changed it elsewhere: the check's finding reads the same.
REPAIRED = SUITE.replace("test('[AC-3] persists', async () => {});", "test('[AC-3] persists', async () => { /* kept */ });")
FAILED = ["[AC-1] adds", "[AC-2] delete answers json", "[AC-3] persists"]


class TheQaLead:
    """The QA lead's model call: records each request it is given and approves the suite."""

    def __init__(self):
        self.requests: list[str] = []

    def __call__(self, state, config, *, output_key, next_stage, initial_request, **kwargs):
        self.requests.append(initial_request["messages"][-1]["content"])
        return {output_key: SimpleNamespace(approved=True, findings=[]), "stage": next_stage}


def _review(tmp_path, spec, review_round, qa_lead):
    return an_acceptance_review(
        tmp_path, spec, failed=FAILED,
        state={"technical_specification": SPECIFICATION, "acceptance_round": review_round},
        patches={"app.graph.workflow._run_gated_agent": qa_lead})


def test_a_finding_unchanged_after_a_repair_goes_to_the_qa_lead_and_is_recorded_not_sent_back(tmp_path):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    qa_lead = TheQaLead()
    first = _review(tmp_path, SUITE, 1, qa_lead)
    assert [item for item in first["acceptance_feedback"] if "204" in item]

    second = _review(tmp_path, REPAIRED, 2, qa_lead)

    assert not [item for item in second.get("acceptance_feedback") or [] if "204" in item]
    assert qa_lead.requests and check_findings.SUSPECTED_HEADING in qa_lead.requests[-1]
    assert "204" in qa_lead.requests[-1].split(check_findings.SUSPECTED_HEADING, 1)[1]
    assert [row for row in check_findings.read(tmp_path)
            if row.get("kind") == "withheld" and row["check"] == "tests_that_want_json_from_a_204"]


def test_a_finding_raised_again_on_a_suite_nobody_repaired_still_goes_to_the_writers(tmp_path):
    """A review run again on the same suite (a resumed stage) has had no repair between: nothing is held back."""
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    _review(tmp_path, SUITE, 1, TheQaLead())

    again = _review(tmp_path, SUITE, 1, TheQaLead())

    assert again["stage"] == "acceptance_author"
    assert [item for item in again["acceptance_feedback"] if "204" in item]


def test_what_the_qa_lead_is_told_about_held_back_findings_avoids_the_banned_words():
    told = check_findings.for_the_qa_lead(["`api.spec.js` line(s) 2: a test asserts a JSON content type on a DELETE"])
    assert told.startswith(check_findings.SUSPECTED_HEADING) and "api.spec.js" in told
    assert not BANNED.search(told)


def test_a_finding_from_running_the_test_s_own_code_is_never_held_back(tmp_path):
    """The dry run reports what the test's code did when it ran: true however often it comes back."""
    from app.acceptance import suite

    (tmp_path / "acceptance").mkdir()
    (tmp_path / "acceptance" / "a.spec.js").write_text(SUITE)
    original = suite.suite_files
    suite.suite_files = lambda root: [tmp_path / "acceptance" / "a.spec.js"]
    try:
        ran = [("spec_dry_run", "`a.spec.js` line 3: the dry run of the suite stopped at `[AC-2] x`")]
        read_only = [("qa_lead", "`a.spec.js`: [AC-2] reads the wrong field")]
        assert check_findings.withheld(tmp_path, 1, ran + read_only) == []
        (tmp_path / "acceptance" / "a.spec.js").write_text(REPAIRED)
        assert check_findings.withheld(tmp_path, 2, ran + read_only) == [read_only[0][1]]
    finally:
        suite.suite_files = original
