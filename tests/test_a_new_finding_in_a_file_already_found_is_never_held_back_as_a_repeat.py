"""A finding about a different test of the same file is a new finding, never held back as a repeat of the last one.

Measured on one run: every "signs in as a user no test signs up" finding in one Python suite file named only that
file, so all of them read as the same finding; after a repair, a true new finding about another test in the file was
held back from the writers as "unchanged" for four rounds and through the lock.
"""
from __future__ import annotations

from app.acceptance import check_findings

LOCKED = """import requests


def test_ac4_lists_items(base_url):
    r = requests.get(base_url + "/items", auth=("nobody", "pw"))
    assert r.status_code == 200


def test_ac4_deletes_an_item(base_url):
    r = requests.delete(base_url + "/items/1", auth=("ghost", "pw"))
    assert r.status_code == 204
"""
#: The writers' repair of the first test: it signs up the user it signs in as.
REPAIRED = LOCKED.replace('    r = requests.get(base_url + "/items", auth=("nobody", "pw"))',
                          '    requests.post(base_url + "/users", json={"name": "nobody"})\n'
                          '    r = requests.get(base_url + "/items", auth=("nobody", "pw"))')
CHECK = "tests_that_sign_in_as_nobody"


def _finding(line: int, user: str) -> str:
    return (f"`notes/acceptance/test_ac4_items.py` line {line}: signs in as `{user}`, a user no test signs up; "
            "sign the user up first in that test.")


def _a_suite(tmp_path):
    (tmp_path / ".project-directory").write_text("notes\n")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True)
    (folder / "test_ac4_items.py").write_text(LOCKED)
    return folder / "test_ac4_items.py"


def test_a_finding_about_another_test_of_the_same_file_goes_to_the_writers_after_a_repair(tmp_path):
    spec = _a_suite(tmp_path)
    check_findings.withheld(tmp_path, 1, [(CHECK, _finding(5, "nobody"))])
    spec.write_text(REPAIRED)

    held = check_findings.withheld(tmp_path, 2, [(CHECK, _finding(11, "ghost"))])

    assert held == []


def test_the_same_test_s_finding_after_a_repair_is_held_back_though_its_line_moved(tmp_path):
    spec = _a_suite(tmp_path)
    check_findings.withheld(tmp_path, 1, [(CHECK, _finding(10, "ghost"))])
    spec.write_text(REPAIRED)

    held = check_findings.withheld(tmp_path, 2, [(CHECK, _finding(11, "ghost"))])

    assert held == [_finding(11, "ghost")]
