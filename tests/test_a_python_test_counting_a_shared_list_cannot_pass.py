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


# A position in the whole list depends on what ran before, as a count does (the JavaScript check's rule, LF.808).
POSITIONAL = SUITE.replace(
    "    notes = resp.json()\n    assert isinstance(notes, list)\n    assert len(notes) == 2\n",
    "    notes = resp.json()\n    assert notes[0][\"title\"] == \"First\"\n",
)
POSITIONAL_INLINE = SUITE.replace(
    "    notes = resp.json()\n    assert isinstance(notes, list)\n    assert len(notes) == 2\n",
    "    assert resp.json()[1][\"title\"] == \"Second\"\n",
)


@pytest.mark.parametrize("text, at", [(POSITIONAL, "0"), (POSITIONAL_INLINE, "1")])
def test_a_position_in_a_shared_list_is_named(tmp_path, text, at):
    [found] = suite.python_tests_that_count_a_list_other_tests_write_to(_suite(tmp_path, text))
    assert f"position {at} of the whole list at `/notes`" in found and "test_ac9_list_all_notes" in found
    assert "Find this test's own records" in found
    assert not BANNED.search(found)


@pytest.mark.parametrize("change", [
    # Its own records found first, then their order checked.
    ("    notes = resp.json()\n", "    notes = [n for n in resp.json() if n[\"title\"] in (\"First\", \"Second\")]\n"),
    # Nothing else in the suite writes to that route.
    ("def test_ac1_create_note(base_url):\n    data = _create_note(base_url, \"Test note\", \"Content here\")\n",
     "def test_ac1_create_note(base_url):\n    data = {\"title\": \"Test note\"}\n"),
    # A position counted from the end is left alone: the newest record is this test's on most orders.
    ("assert notes[0]", "assert notes[-1]"),
])
def test_a_fair_position_is_left_alone(tmp_path, change):
    assert suite.python_tests_that_count_a_list_other_tests_write_to(_suite(tmp_path, POSITIONAL.replace(*change))) == []


def test_a_passing_positional_test_is_never_named(tmp_path):
    passed = junit.TestResult(name="acceptance.test_api.test_ac9_list_all_notes", outcome="passed")
    assert suite.python_tests_that_count_a_list_other_tests_write_to(_suite(tmp_path, POSITIONAL), _ran(passed)) == []
    failed = junit.TestResult(name="acceptance.test_api.test_ac9_list_all_notes", outcome="failed",
                              message="AssertionError: assert 'Test note' == 'First'")
    assert len(suite.python_tests_that_count_a_list_other_tests_write_to(_suite(tmp_path, POSITIONAL), _ran(failed))) == 1


# Each case below was reproduced by an independent review of the position check before it shipped.
HEAD = SUITE.split("def test_ac9_list_all_notes")[0]


def _named(tmp_path, body, result=None):
    return suite.python_tests_that_count_a_list_other_tests_write_to(_suite(tmp_path, HEAD + body), result)


@pytest.mark.parametrize("body", [
    # Any record there passes a check of its shape.
    'def test_ac9_ids(base_url):\n    _create_note(base_url, "First", "b")\n    resp = httpx.get(f"{base_url}/notes")\n'
    '    notes = resp.json()\n    assert notes[0]["id"] is not None\n',
    'def test_ac9_keys(base_url):\n    _create_note(base_url, "First", "b")\n    resp = httpx.get(f"{base_url}/notes")\n'
    '    notes = resp.json()\n    assert notes[0].keys() == {"id", "title", "body"}\n',
    # Newest first: the record this test made last sits at position 0, and the one before it at 1.
    'def test_ac9_newest_first(base_url):\n    _create_note(base_url, "First", "b")\n    _create_note(base_url, "Second", "b")\n'
    '    resp = httpx.get(f"{base_url}/notes")\n    notes = resp.json()\n    assert notes[0]["title"] == "Second"\n'
    '    assert notes[1]["title"] == "First"\n',
    'def test_ac9_newest_by_id(base_url):\n    a = _create_note(base_url, "First", "b")\n    b = _create_note(base_url, "Second", "b")\n'
    '    resp = httpx.get(f"{base_url}/notes")\n    notes = resp.json()\n    assert notes[0]["id"] == b["id"]\n',
    # Its own records kept under the same name.
    'def test_ac9_order(base_url):\n    a = _create_note(base_url, "First", "b")\n    b = _create_note(base_url, "Second", "b")\n'
    '    resp = httpx.get(f"{base_url}/notes")\n    notes = resp.json()\n'
    '    notes = [n for n in notes if n["id"] in (a["id"], b["id"])]\n    assert notes[0]["title"] == "First"\n',
    # Every record deleted first.
    'def test_ac9_order(base_url):\n    for n in httpx.get(f"{base_url}/notes").json():\n'
    '        httpx.delete(f"{base_url}/notes/{n[\'id\']}")\n    _create_note(base_url, "First", "b")\n'
    '    _create_note(base_url, "Second", "b")\n    resp = httpx.get(f"{base_url}/notes")\n    notes = resp.json()\n'
    '    assert notes[0]["title"] == "First"\n',
])
def test_a_position_any_right_product_passes_is_left_alone(tmp_path, body):
    assert _named(tmp_path, body) == []


ORDERED = ('def test_ac9_order(base_url):\n    _create_note(base_url, "First", "b")\n    _create_note(base_url, "Second", "b")\n'
           '    resp = httpx.get(f"{base_url}/notes")\n    notes = resp.json()\n    assert notes[0]["title"] == "First"\n')


def test_a_failure_before_the_position_is_the_product_s(tmp_path):
    passed = junit.TestResult(name="acceptance.test_api.test_ac1_create_note", outcome="passed")
    early = junit.TestResult(name="acceptance.test_api.test_ac9_order", outcome="failed",
                             message="AssertionError: assert 500 == 201")
    assert _named(tmp_path, ORDERED, _ran(early, passed)) == []
    there = junit.TestResult(name="acceptance.test_api.test_ac9_order", outcome="failed",
                             message="AssertionError: assert 'Test note' == 'First'")
    assert len(_named(tmp_path, ORDERED, _ran(there, passed))) == 1


@pytest.mark.parametrize("read", [
    '    resp = httpx.get(f"{base_url}/notes", timeout=5)\n    notes = resp.json()\n',
    '    notes = httpx.get(f"{base_url}/notes").json()\n',
    '    notes: list[dict] = httpx.get(f"{base_url}/notes", timeout=5).json()  # the list\n',
])
def test_the_ways_a_suite_reads_the_whole_list_are_all_read(tmp_path, read):
    head = 'def test_ac9_order(base_url):\n    _create_note(base_url, "First", "b")\n    _create_note(base_url, "Second", "b")\n'
    assert len(_named(tmp_path, head + read + '    assert notes[0]["title"] == "First"\n')) == 1
    assert len(_named(tmp_path, head + read + '    assert len(notes) == 2\n')) == 1


def test_an_async_suite_s_read_is_read(tmp_path):
    body = ('async def test_ac9_order(client):\n    await client.post("/notes", json={"title": "First"})\n'
            '    resp = await client.get("/notes")\n    notes = resp.json()\n    assert len(notes) == 1\n')
    assert len(_named(tmp_path, body)) == 1


def test_a_query_or_a_scoping_header_is_not_the_whole_list(tmp_path):
    for read in ('httpx.get(f"{base_url}/notes", params={"q": "First"})', 'httpx.get(f"{base_url}/notes", headers=mine)'):
        body = (f'def test_ac9_order(base_url):\n    _create_note(base_url, "First", "b")\n    resp = {read}\n'
                '    notes = resp.json()\n    assert len(notes) == 1\n')
        assert _named(tmp_path, body) == [], read


def test_the_line_named_is_the_test_s_own(tmp_path):
    fair = ('def test_ac2_mine(base_url):\n    a = _create_note(base_url, "First", "b")\n    resp = httpx.get(f"{base_url}/notes")\n'
            '    notes = [n for n in resp.json() if n["id"] == a["id"]]\n    assert notes[0]["title"] == "First"\n\n\n')
    [found] = _named(tmp_path, fair + "# notes[0]\n" + ORDERED)
    text = (tmp_path / "notes" / "acceptance" / "test_api.py").read_text().splitlines()
    line = int(re.search(r"line (\d+)", found).group(1))
    assert text[line - 1].strip() == 'assert notes[0]["title"] == "First"' and "test_ac9_order" in found
    assert line > text.index("def test_ac9_order(base_url):")


def test_a_failing_parametrized_case_is_named(tmp_path):
    passed = junit.TestResult(name="acceptance.test_api.test_ac1_create_note", outcome="passed")
    case = junit.TestResult(name="acceptance.test_api.test_ac9_list_all_notes[First]", outcome="failed",
                            message="AssertionError: assert 3 == 2")
    assert len(suite.python_tests_that_count_a_list_other_tests_write_to(_suite(tmp_path, SUITE), _ran(case, passed))) == 1


# A second independent review's reproductions, against the revised check.
CLIENT_HEAD = ('import httpx\nimport requests\n\nBASE = "http://localhost:8000"\n\n\n'
               'def test_ac1_create(client):\n    r = client.post("/notes", json={"title": "x"})\n    assert r.status_code == 201\n\n\n')


def _client_suite(tmp_path, body, result=None):
    return suite.python_tests_that_count_a_list_other_tests_write_to(_suite(tmp_path, CLIENT_HEAD + body), result)


@pytest.mark.parametrize("body", [
    # params by position, auth, and params after an argument holding a call: the list is narrowed or scoped.
    'def test_ac9_tagged(client):\n    requests.post(BASE + "/notes", json={"title": "a", "tag": "t-1"})\n'
    '    resp = requests.get(BASE + "/notes", {"tag": "t-1"})\n    notes = resp.json()\n    assert len(notes) == 1\n',
    'def test_ac9_mine(client):\n    client.post("/notes", json={"title": "a"}, auth=("u1", "pw"))\n'
    '    resp = client.get("/notes", auth=("u1", "pw"))\n    notes = resp.json()\n    assert len(notes) == 1\n',
    'def test_ac9_tagged(client):\n    client.post("/notes", json={"title": "a", "tag": "t-9"})\n'
    '    resp = client.get("/notes", timeout=httpx.Timeout(5.0), params={"tag": "t-9"})\n    notes = resp.json()\n'
    '    assert len(notes) == 1\n',
    # Newest first, made in a loop: which record sits first cannot be traced, so it is left alone.
    'def test_ac9_newest(client):\n    for title in ["a", "b", "c"]:\n        client.post("/notes", json={"title": title})\n'
    '    resp = client.get("/notes")\n    notes = resp.json()\n    assert notes[0]["title"] == "c"\n',
    # A write to another route, or an update, makes no record of this list.
    'def test_ac9_newest(client):\n    client.post("/notes", json={"title": "older"})\n    client.post("/notes", json={"title": "newer"})\n'
    '    client.post("/tags", json={"name": "misc"})\n    resp = client.get("/notes")\n    notes = resp.json()\n'
    '    assert notes[0]["title"] == "newer"\n',
    # A record a fixture made, a value under a name that no write here bound, a key spelled like the value.
    'def test_ac9_fixture_newest(client, note):\n    resp = client.get("/notes")\n    notes = resp.json()\n'
    '    assert notes[0]["id"] == note["id"]\n',
    'def test_ac9_by_name(client):\n    title = "First"\n    client.post("/notes", json={"title": title})\n'
    '    client.post("/notes", json={"title": "Second"})\n    resp = client.get("/notes")\n    notes = resp.json()\n'
    '    assert notes[0]["title"] == title\n',
])
def test_what_the_second_review_found_named_is_left_alone(tmp_path, body):
    assert _client_suite(tmp_path, body) == []


@pytest.mark.parametrize("body", [
    # Records made in a loop and one of its own deleted: the count is still of the whole list.
    'def test_ac9_count(client):\n    made = []\n    for title in ["a", "b"]:\n'
    '        made.append(client.post("/notes", json={"title": title}).json())\n'
    '    client.delete(f"/notes/{made[0][\'id\']}")\n    resp = client.get("/notes")\n    notes = resp.json()\n'
    '    assert len(notes) == 1\n',
    # A name that says empty is not a test that empties the list.
    'def test_ac9_starts_empty(client):\n    client.post("/notes", json={"title": "a"})\n    resp = client.get("/notes")\n'
    '    notes = resp.json()\n    assert len(notes) == 1\n',
    # A keyword argument of the same name is not a binding; statements joined by `;` are read.
    'def test_ac9_count(client):\n    client.post("/notes", json={"title": "a"})\n    resp = client.get("/notes")\n'
    '    notes = resp.json()\n    show(\n        notes=notes,\n    )\n    assert len(notes) == 1\n',
    'def test_ac9_count(client):\n    client.post("/notes", json={"title": "a"})\n'
    '    resp = client.get("/notes"); notes = resp.json()\n    assert len(notes) == 1\n',
])
def test_what_the_second_review_found_missed_is_named(tmp_path, body):
    assert len(_client_suite(tmp_path, body)) == 1


def test_a_fixture_that_deletes_its_own_records_does_not_hide_the_file(tmp_path):
    fixture = ('import pytest\n\n\n@pytest.fixture\ndef mine(client):\n    made = [client.post("/notes", json={"title": "m"}).json()]\n'
               '    yield made\n    for note in made:\n        client.delete(f"/notes/{note[\'id\']}")\n\n\n')
    body = ('def test_ac9_count(client, mine):\n    client.post("/notes", json={"title": "a"})\n    resp = client.get("/notes")\n'
            '    notes = resp.json()\n    assert len(notes) == 2\n')
    assert len(_client_suite(tmp_path, fixture + body)) == 1


def test_a_test_before_a_class_of_tests_is_not_the_class_s(tmp_path):
    body = ('def test_ac2_mine(client):\n    r = client.post("/notes", json={"title": "z"})\n    assert r.status_code == 201\n\n\n'
            'class TestOrder:\n    def test_order(self, client):\n        client.post("/notes", json={"title": "First"})\n'
            '        client.post("/notes", json={"title": "Second"})\n        resp = client.get("/notes")\n'
            '        notes = resp.json()\n        assert notes[0]["title"] == "First"\n')
    found = _client_suite(tmp_path, body)
    assert len(found) == 1 and "`test_order`" in found[0]
