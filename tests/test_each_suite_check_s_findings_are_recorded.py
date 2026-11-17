"""Each harness check's findings against the suite are recorded under the check's name (harness review Q1).

No check's precision had ever been measured; false findings held runs for hours. The review records each finding as
it raises it, so a report can say per check how often it was right.
"""
from __future__ import annotations

import pytest

from app.acceptance import check_findings
from app.stacks import contract, pack_named
from workflow_nodes import an_acceptance_review


def test_findings_pass_through_unchanged_and_are_recorded(tmp_path):
    found = ["`test_ac5_lists` counts every row in the shared list (12 records)"]
    assert check_findings.noted(tmp_path, 2, "locators_that_pick_one", found) == found
    rows = check_findings.read(tmp_path)
    assert rows[0]["check"] == "locators_that_pick_one" and rows[0]["round"] == 2
    assert rows[0]["tests"] == ["test_ac5_lists"]
    again = check_findings.noted(tmp_path, 3, "locators_that_pick_one", ["`test_ac5_lists` counts every row in the shared list (14 records)"])
    assert again and check_findings.read(tmp_path)[1]["fingerprint"] == rows[0]["fingerprint"]


def test_nothing_is_recorded_for_no_finding(tmp_path):
    assert check_findings.noted(tmp_path, 1, "vacuous_green", []) == []
    assert check_findings.read(tmp_path) == []


EVERY_CRITERION = """import { test, expect } from '@playwright/test';
test('[AC-1] adds', async ({ request }) => {
  const res = await request.post('/notes', {
    headers: { 'Content-Type': 'application/json' },
    data: { title: 'a' },
  });
  expect(res.status()).toBe(201);
});
test('[AC-2] deletes', async ({ request }) => {
  expect((await request.delete('/notes/1')).status()).toBe(404);
});
test('[AC-3] persists', async ({ request }) => {
  expect((await request.get('/notes')).status()).toBe(200);
});
"""
ALL_RAN = ["[AC-1] adds", "[AC-2] deletes", "[AC-3] persists"]


@pytest.mark.parametrize(("spec", "ran", "check"), [
    # A check inside `tests_that_cannot_pass` is recorded under its own name, not the bucket's (HR2.Q.1).
    (EVERY_CRITERION.replace("data: { title: 'a' },", "body: JSON.stringify({ title: 'a' }),"), ALL_RAN,
     "requests_with_a_fetch_body"),
    (EVERY_CRITERION, [], "vacuous_green"),
])
def test_the_review_records_a_finding_it_sends_back_under_its_check_s_name(tmp_path, spec, ran, check):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")

    update = an_acceptance_review(tmp_path, spec, failed=ran)

    assert update["stage"] == "acceptance_author"
    assert check in {row["check"] for row in check_findings.read(tmp_path)}
