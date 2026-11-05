"""A fixer of a failing criterion is shown that criterion's failing tests, not the last command that failed anywhere.

Measured on one run: the fixer of "[AC-5] Delete a note" (`KeyError: 'id'`) was shown, as "what the last failing
command actually printed - believe this", a run of two other tests (AC-14, AC-15) that a different stage had made.
"""
import json

from app.acceptance import suite
from app.agents import specialists


def _with_a_result(tmp_path):
    (tmp_path / suite.RESULT_FILE).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / suite.RESULT_FILE).write_text(json.dumps({"criteria": {
        "AC-5": {"id": "AC-5", "status": "failed", "tests": [
            {"name": "test_ac_5_delete_note", "outcome": "failed",
             "message": "KeyError: 'id'\n    created = response.json()\n>   note_id = created['id']\nE   KeyError: 'id'"},
            {"name": "test_ac_5_delete_twice", "outcome": "passed", "message": ""}]},
        "AC-15": {"id": "AC-15", "status": "failed", "tests": [
            {"name": "test_ac_15_start_sh_exists", "outcome": "failed", "message": "assert False"}]},
    }}))
    return tmp_path


def test_the_criterion_s_own_failing_tests_are_the_evidence(tmp_path):
    seen = suite.what_the_criteria_s_tests_printed(_with_a_result(tmp_path), ("AC-5",))
    assert seen is not None
    assert "test_ac_5_delete_note" in seen["output"] and "created['id']" in seen["output"]
    assert "test_ac_15" not in seen["output"] and "test_ac_5_delete_twice" not in seen["output"]


def test_no_result_or_no_tag_gives_nothing(tmp_path):
    assert suite.what_the_criteria_s_tests_printed(tmp_path, ("AC-5",)) is None
    assert suite.what_the_criteria_s_tests_printed(_with_a_result(tmp_path), ()) is None


def test_the_brief_names_it_as_the_criterion_s_tests(tmp_path):
    seen = suite.what_the_criteria_s_tests_printed(_with_a_result(tmp_path), ("AC-5",))
    brief = specialists.build_defect_fix_request("[AC-5] Delete a note", "run it", "Delete a note", "KeyError",
                                                 [], True, str(tmp_path), observed=seen)["messages"][0]["content"]
    assert "--- What its failing tests printed ---" in brief and "last failing command" not in brief
