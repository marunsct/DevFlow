"""Each harness check's findings against the suite are recorded under the check's name (harness review Q1).

No check's precision had ever been measured; false findings held runs for hours. The review records each finding as
it raises it, so a report can say per check how often it was right.
"""
from __future__ import annotations

import inspect

from app.acceptance import check_findings
from app.graph import acceptance_nodes


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


def test_the_review_records_every_check_it_sends_back():
    source = inspect.getsource(acceptance_nodes.acceptance_review)
    # `tests_that_cannot_pass` is recorded per inner check since HR2.Q.1, the bucket's name only for a finding none
    # of them raised.
    assert 'named.get(str(f), "tests_that_cannot_pass")' in source
    for check in ("vacuous_green", "locators_nobody_sees", "locators_that_pick_one",
                  "controls_never_found_by_name", "records_never_found_as_the_brief_shows_them",
                  "views_never_acted_within", "tests_that_want_json_from_a_204", "contract_lines_with_no_test"):
        assert f'check_findings.noted(root, rounds, "{check}"' in source, check
