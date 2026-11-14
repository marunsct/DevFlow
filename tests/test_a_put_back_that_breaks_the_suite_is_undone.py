"""A put-back of tests a repair was not sent for that leaves the suite worse is undone before the repair is judged.

Measured on one run: one test was put back into a file the repair had reshaped, the suite then ran no test at all, and
the whole repair of six tests was thrown away for that one put-back.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

from app.acceptance import suite
from app.graph import acceptance_nodes


def _result(tests):
    return SimpleNamespace(ran=True, report=SimpleNamespace(tests=[SimpleNamespace(outcome="passed")] * tests))


def test_the_repair_is_kept_when_only_the_put_back_broke_it(tmp_path, monkeypatch):
    spec = tmp_path / "a.spec.js"
    spec.write_text("repaired")
    monkeypatch.setattr(suite, "suite_files", lambda root: [spec])
    monkeypatch.setattr(suite, "gaps", lambda root: [])
    def put_back(root):
        spec.write_text("broken by the put-back")
        return ["[AC-5] edits"]

    monkeypatch.setattr(suite, "put_back_tests_the_repair_was_not_sent_for", put_back)
    monkeypatch.setattr(suite, "run", lambda root: _result(0 if spec.read_text().startswith("broken") else 38))
    monkeypatch.setattr(suite, "a_repair_that_made_it_worse",
                        lambda root, result: "worse" if not result.report.tests else "")

    problems, result, worse = acceptance_nodes._the_repair_measured(tmp_path)

    assert worse == "" and len(result.report.tests) == 38 and spec.read_text() == "repaired"


def test_a_repair_worse_on_its_own_is_still_reported(tmp_path, monkeypatch):
    spec = tmp_path / "a.spec.js"
    spec.write_text("repaired")
    monkeypatch.setattr(suite, "suite_files", lambda root: [spec])
    monkeypatch.setattr(suite, "gaps", lambda root: [])
    monkeypatch.setattr(suite, "put_back_tests_the_repair_was_not_sent_for", lambda root: ["[AC-5] edits"])
    monkeypatch.setattr(suite, "run", lambda root: _result(0))
    monkeypatch.setattr(suite, "a_repair_that_made_it_worse", lambda root, result: "worse")

    assert acceptance_nodes._the_repair_measured(tmp_path)[2] == "worse"


def test_the_review_measures_the_repair_this_way():
    assert "_the_repair_measured(root)" in inspect.getsource(acceptance_nodes.acceptance_review)
