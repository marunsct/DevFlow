"""Which files are unit tests, and which files tests reach the code through, are pack data (Initiative AO.10).

The check that unit tests name the served code knew Python and JavaScript test
names by a regular expression in `stacks/scaffold.py`, and `conftest.py` by name:
stack knowledge in the core, which a pack for another language could not extend.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

from app.stacks import pack_named, scaffold
from app.stacks.packs import ALL_PACKS


def test_the_core_check_names_no_test_file_convention():
    source = inspect.getsource(scaffold)
    assert "conftest" not in source
    assert "test_.*\\.py" not in source and "(test|spec)" not in source


def test_python_packs_and_a_python_service_declare_pytest_s_names_and_fixtures():
    for name in ("python-http-api", "python-flask-api", "fullstack-django", "fullstack-react-fastapi"):
        pack = pack_named(name)
        assert "test_*.py" in pack.unit_test_names and "*_test.py" in pack.unit_test_names, name
        assert pack.test_helpers == ("conftest.py",), name
    assert "*.test.tsx" in pack_named("fullstack-react-fastapi").unit_test_names


def test_every_pack_s_unit_pattern_is_a_unit_test_name_for_the_check():
    for pack in ALL_PACKS:
        sample = pack.unit_pattern.replace("*", "sample")
        assert scaffold._a_unit_test(Path(sample).name, pack), pack.name


def test_tests_reaching_the_served_code_through_a_fixture_name_nothing(tmp_path):
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "stack-pack.json").write_text(json.dumps(
        {"pack": "fullstack-react-fastapi", "project": "app", "package": "board", "title": "Board"}))
    tests = tmp_path / "app" / "tests"
    tests.mkdir(parents=True)
    (tests / "conftest.py").write_text("from board.main import app\n")
    (tests / "test_auth.py").write_text("def test_login(client): ...\n")
    (tmp_path / "app" / "board").mkdir()
    (tmp_path / "app" / "board" / "main.py").write_text("app = 1\n")

    assert not any("never name" in p for p in scaffold.code_the_product_does_not_run(tmp_path))
