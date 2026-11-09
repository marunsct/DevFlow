"""A failing acceptance test that counts every row of a table the whole suite writes to goes back to the suite.

Measured on one run: `test_ac21_invalid_signup_does_not_store` counted every account in the product's database
(`SELECT COUNT(*) FROM accounts`) and expected 0, while other tests had made 19; it failed with `assert 19 == 0`
on a product that refused the signup, and four fix rounds and a re-planned sprint went at the product.
"""
from types import SimpleNamespace

from app.acceptance import suite

SUITE = '''
import sqlite3


def test_ac1_signup(base_url):
    httpx.post(f"{base_url}/signup", json={"username": "a", "password": "b"})


def test_ac21_invalid_signup_does_not_store(base_url, service):
    httpx.post(f"{base_url}/signup", json={"username": ""})
    db = sqlite3.connect(service.data_dir / "tasks.db")
    count = db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    assert count == 0


def test_ac22_filtered_count(base_url, service):
    db = sqlite3.connect(service.data_dir / "tasks.db")
    assert db.execute("SELECT COUNT(*) FROM accounts WHERE username = ?", ("zz",)).fetchone()[0] == 0
'''


def _result(failures):
    tests = [SimpleNamespace(name=name, outcome="failed", message=message) for name, message in failures.items()]
    return SimpleNamespace(ran=True, report=SimpleNamespace(tests=tests))


def test_the_whole_table_count_that_failed_high_is_named(tmp_path, monkeypatch):
    path = tmp_path / "acceptance" / "test_api.py"
    path.parent.mkdir()
    path.write_text(SUITE)
    monkeypatch.setattr(suite, "suite_files", lambda root: [path])
    result = _result({
        "test_ac21_invalid_signup_does_not_store": "assert 19 == 0",
        "test_ac22_filtered_count": "assert 1 == 0",
    })

    found = suite.tests_that_count_every_row_of_a_shared_table(tmp_path, result)

    assert len(found) == 1 and "test_ac21_invalid_signup_does_not_store" in found[0] and "accounts" in found[0]


def test_nothing_is_named_before_it_fails(tmp_path, monkeypatch):
    path = tmp_path / "acceptance" / "test_api.py"
    path.parent.mkdir()
    path.write_text(SUITE)
    monkeypatch.setattr(suite, "suite_files", lambda root: [path])
    assert suite.tests_that_count_every_row_of_a_shared_table(tmp_path, _result({})) == []
