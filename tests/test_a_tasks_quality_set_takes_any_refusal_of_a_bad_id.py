"""A non-numeric id refused with 400 passes the tasks quality sets, as their own helper allows.

Found in the deep review: the check that a foreign or malformed id is never a server error accepted 400 for no other
request, and a recorded run lost the quality test on `assert 400 in (404, 422)` for a product that refused it.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


class _Answer:
    def __init__(self, status_code, body=None):
        self.status_code, self._body, self.text = status_code, body or {}, ""

    def json(self):
        return self._body


class _Product:
    """Signs up and in, answers 404 for an item that is not yours, 400 for an id that is not a number."""

    def post(self, path, json=None, headers=None):
        return _Answer(201) if path == "/signup" else _Answer(200, {"token": "t"})

    def patch(self, path, json=None, headers=None):
        return _Answer(404)

    def delete(self, path, headers=None):
        return _Answer(400 if path.endswith("not-a-number") else 404)


@pytest.mark.parametrize("bench", ["tasks-api", "tasks-api-change"])
def test_a_bad_id_refused_with_400_is_not_a_lost_quality_test(bench, monkeypatch):
    monkeypatch.setenv("PRODUCT_DIR", str(ROOT))
    monkeypatch.syspath_prepend(str(ROOT / "benchmarks" / bench / "hidden"))
    monkeypatch.delitem(sys.modules, "conftest", raising=False)
    spec = importlib.util.spec_from_file_location(f"quality_{bench}", ROOT / "benchmarks" / bench / "quality" / "test_tasks_api_quality.py")
    quality = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(quality)

    quality.test_an_id_that_is_not_one_of_yours_is_never_a_server_error(_Product())
