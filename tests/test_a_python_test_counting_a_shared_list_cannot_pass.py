"""A pytest suite that counts a list other tests write to is told so, as a JavaScript suite already was.

Measured on one run: one test created a note, the next created two and asserted the list held exactly 2; it held 3,
and two fix stages over half an hour went at a product that was right. These files are read as text, never run.
"""
from __future__ import annotations

import re

import pytest

from app.acceptance import junit, spec_dry_run, suite
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

SUITE = '''import httpx


def _create_note(base_url, title, body):
    resp = httpx.post(f"{base_url}/notes", json={"title": title, "body": body})
    assert resp.status_code == 201
    return resp.json()


def test_ac1_create_note(base_url):
    data = _create_note(base_url, "Test note", "Content here")
    assert data["title"] == "Test note"


def test_ac9_list_all_notes(base_url):
    _create_note(base_url, "First", "Body one")
    _create_note(base_url, "Second", "Body two")
    resp = httpx.get(f"{base_url}/notes")
    assert resp.status_code == 200
    notes = resp.json()
    assert isinstance(notes, list)
    assert len(notes) == 2
'''


def _suite(tmp_path, text, pack="python-http-api"):
    contract.write(tmp_path, pack_named(pack), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "test_api.py").write_text(text)
    return tmp_path


def _ran(*tests, locked=False):
    return suite.AcceptanceResult(ran=True, report=junit.Report(tests=list(tests), found=True))


def test_the_count_is_named_before_and_after_the_product_answers(tmp_path, monkeypatch):
    monkeypatch.setattr(spec_dry_run, "findings", lambda root: [])
    root = _suite(tmp_path, SUITE)
    [found] = [f for f in suite.tests_that_cannot_pass(root, suite.AcceptanceResult(ran=False)) if "exactly 2" in f]
    assert "test_api.py" in found and "`/notes`" in found and "test_ac9_list_all_notes" in found
    assert not BANNED.search(found)
    more = junit.TestResult(name="acceptance.test_api.test_ac9_list_all_notes", outcome="failed",
                            message="AssertionError: assert 3 == 2\n +  where 3 = len([...])")
    passed = junit.TestResult(name="acceptance.test_api.test_ac1_create_note", outcome="passed")
    assert len(suite.python_tests_that_count_a_list_other_tests_write_to(root, _ran(more, passed))) == 1


def test_fewer_than_expected_is_the_product_s_to_answer(tmp_path):
    fewer = junit.TestResult(name="acceptance.test_api.test_ac9_list_all_notes", outcome="failed",
                             message="AssertionError: assert 1 == 2")
    passed = junit.TestResult(name="acceptance.test_api.test_ac1_create_note", outcome="passed")
    assert suite.python_tests_that_count_a_list_other_tests_write_to(_suite(tmp_path, SUITE), _ran(fewer, passed)) == []


@pytest.mark.parametrize("change", [
    ("assert len(notes) == 2", "assert len(notes) >= 2"),
    ("    _create_note(base_url, \"First\", \"Body one\")\n",
     "    before = len(httpx.get(f\"{base_url}/notes\").json())\n    _create_note(base_url, \"First\", \"Body one\")\n"),
    ("def test_ac1_create_note(base_url):\n    data = _create_note(base_url, \"Test note\", \"Content here\")\n",
     "def test_ac1_create_note(base_url):\n    data = {\"title\": \"Test note\"}\n"),
])
def test_a_fair_count_is_left_alone(tmp_path, change):
    text = SUITE.replace(*change)
    found = suite.python_tests_that_count_a_list_other_tests_write_to(_suite(tmp_path, text))
    if "before" in change[1]:
        assert found  # Still an exact count of the whole list; only `len(before) + n` is fair.
    else:
        assert found == []


def test_a_suite_whose_fixture_resets_the_store_is_left_alone(tmp_path):
    text = "import pytest\n\n\n@pytest.fixture(autouse=True)\ndef fresh(base_url):\n    reset_store(base_url)\n\n\n" + SUITE
    assert suite.python_tests_that_count_a_list_other_tests_write_to(_suite(tmp_path, text)) == []


def test_a_command_line_suite_is_not_read(tmp_path):
    assert suite.python_tests_that_count_a_list_other_tests_write_to(_suite(tmp_path, SUITE, pack="python-cli")) == []
