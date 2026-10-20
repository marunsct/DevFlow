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


def test_a_failed_install_is_raised_naming_the_manifests(monkeypatch, tmp_path):
    """Measured on one gate run: a JavaScript package written into `requirements.txt` failed every install,
    the product could not start, and no defect named the manifest."""
    (tmp_path / "shop").mkdir()
    (tmp_path / "shop" / "requirements.txt").write_text("fastapi\nrecharts\n")
    (tmp_path / "shop" / "package.json").write_text("{}")
    monkeypatch.setattr(acceptance_nodes, "_failing_due", lambda state: ([{"id": "AC-1", "tests": []}], "npm test"))
    monkeypatch.setattr(acceptance_nodes, "_root", lambda state: str(tmp_path))
    monkeypatch.setattr("app.tools.repository.pinned_project_directory", lambda root: "shop")
    monkeypatch.setattr(acceptance_nodes.suite, "last_result", lambda root: {
        "problem": acceptance_nodes.suite.PRODUCT_DID_NOT_START + " ModuleNotFoundError: passlib",
        "repairs": ["`pip install -r requirements.txt` failed after the project's manifest changed; it ended:\n"
                    "ERROR: No matching distribution found for recharts"],
    })
    monkeypatch.setattr(engineering, "underlined_in_the_batch", lambda state, root, since: [])
    monkeypatch.setattr("app.ci.load", lambda root, label: None)
    monkeypatch.setattr("app.ci.first_commit", lambda root: "base", raising=False)

    defects = acceptance_nodes.failing_due_defects({}, [])

    installs = [d for d in defects if "do not install" in d.description]
    assert installs and "No matching distribution found for recharts" in installs[0].description
    assert sorted(installs[0].affected_files) == ["shop/package.json", "shop/requirements.txt"]


def test_a_failed_install_is_raised_while_the_product_runs_and_passes(monkeypatch, tmp_path):
    """Measured on one gate run: the product ran on what an earlier install left, 31 of 34 tests
    passed, and the `requirements.txt` it would have released failed every install."""
    (tmp_path / "shop").mkdir()
    (tmp_path / "shop" / "requirements.txt").write_text("fastapi\nrecharts\n")
    monkeypatch.setattr(acceptance_nodes, "_failing_due", lambda state: ([], "npm test"))
    monkeypatch.setattr(acceptance_nodes, "_root", lambda state: str(tmp_path))
    monkeypatch.setattr("app.tools.repository.pinned_project_directory", lambda root: "shop")
    monkeypatch.setattr(acceptance_nodes.suite, "last_result", lambda root: {
        "repairs": ["`pip install -r requirements.txt` failed after the project's manifest changed; it ended:\n"
                    "ERROR: No matching distribution found for recharts"],
    })

    defects = acceptance_nodes.failing_due_defects({}, [])

    assert len(defects) == 1 and "do not install" in defects[0].description
    assert defects[0].affected_files == ["shop/requirements.txt"]
