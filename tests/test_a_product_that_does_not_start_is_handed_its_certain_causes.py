"""A test round that finds the product not starting raises the language service's certain findings too.

Measured on one gate run: the product stopped on a name its module did not
define, round after round. Each round raised only "the suite fails ...", whose
traceback names the importer, so every fix rewrote the importer. The gate had
named the module, but it runs once per batch, not per round.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.agents.specialists import ReportedDefect
from app.graph import acceptance_nodes, engineering


def test_the_start_defect_comes_with_what_the_language_service_finds(monkeypatch, tmp_path):
    monkeypatch.setattr(acceptance_nodes, "_failing_due", lambda state: ([{"id": "AC-1", "tests": []}], "npm test"))
    monkeypatch.setattr(acceptance_nodes, "_root", lambda state: str(tmp_path))
    monkeypatch.setattr(acceptance_nodes.suite, "last_result",
                        lambda root: {"problem": acceptance_nodes.suite.PRODUCT_DID_NOT_START + " ImportError"})
    monkeypatch.setattr("app.ci.load", lambda root, label: None)
    monkeypatch.setattr("app.ci.first_commit", lambda root: "base", raising=False)
    asked = []
    finding = ReportedDefect(
        description='shop/schemas/task.py line 3: "TaskCreate" is unknown - this fails when the code runs.',
        severity="major", reproduction_steps="r", expected_behavior="e", actual_behavior="a",
        affected_files=["shop/schemas/task.py"], owner="backend")
    monkeypatch.setattr(engineering, "underlined_in_the_batch",
                        lambda state, root, since: asked.append(since) or [finding])

    defects = acceptance_nodes.failing_due_defects({}, [])

    assert defects[0].description == acceptance_nodes.THE_PRODUCT_DOES_NOT_START
    assert [d.affected_files for d in defects[1:]] == [["shop/schemas/task.py"]]
    assert defects[1].source == "language service" and asked == ["base"]
