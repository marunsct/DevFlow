"""A small project's files are in a stage's opening request.

Measured on one completed run of a ten-file, 347-line product: 82% of its 911
tool calls were reads, listings and searches, and `ui.js` was read 60 times
across 27 stages, each of which started a fresh conversation. Nothing here
names a language, a framework or a kind of product.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.project_snapshot import SNAPSHOT_BUDGET_CHARS, project_snapshot
from test_graph_routing import agents  # noqa: F401 - a fixture


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / ".project-directory").write_text("shop\n", encoding="utf-8")
    (tmp_path / "shop" / "tests").mkdir(parents=True)
    (tmp_path / "shop" / "cart.py").write_text("TOTAL = 0\n\ndef add(x):\n    return x\n", encoding="utf-8")
    (tmp_path / "shop" / "tests" / "test_cart.py").write_text("def test_add():\n    assert True\n", encoding="utf-8")
    return tmp_path


def test_the_files_are_there_numbered_the_way_read_file_numbers_them(project: Path) -> None:
    text = project_snapshot(project)

    assert "--- shop/cart.py (4 lines) ---" in text
    assert "def add(x):" in text
    assert any(line.strip().startswith("3") and "def add(x):" in line for line in text.splitlines())
    assert "line count" in text


def test_the_product_comes_before_its_tests(project: Path) -> None:
    text = project_snapshot(project)

    assert text.index("shop/cart.py") < text.index("shop/tests/test_cart.py")


def test_lockfiles_dependencies_and_binary_files_are_left_out(project: Path) -> None:
    (project / "shop" / "package-lock.json").write_text("{" + "x" * 500 + "}", encoding="utf-8")
    (project / "shop" / "node_modules" / "lib").mkdir(parents=True)
    (project / "shop" / "node_modules" / "lib" / "index.js").write_text("module.exports = 1\n", encoding="utf-8")
    (project / "shop" / "logo.png").write_bytes(b"\x89PNG\x00\x00binary")

    text = project_snapshot(project)

    assert "package-lock.json" not in text
    assert "node_modules" not in text
    assert "logo.png" not in text


def test_what_does_not_fit_is_named_and_the_product_is_kept(project: Path) -> None:
    (project / "shop" / "tests" / "test_big.py").write_text("x = 1\n" * (SNAPSHOT_BUDGET_CHARS // 4), encoding="utf-8")

    text = project_snapshot(project)

    assert "--- shop/cart.py" in text
    assert "Not included" in text and "shop/tests/test_big.py" in text
    assert len(text) < SNAPSHOT_BUDGET_CHARS + 2_000


def test_no_project_directory_yet_means_nothing(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "spec.md").write_text("# Spec\n", encoding="utf-8")

    assert project_snapshot(tmp_path) == ""
    assert project_snapshot(None) == ""


def test_an_empty_project_is_said_to_be_empty(tmp_path: Path) -> None:
    """One run's architect spent three turns finding an empty directory."""
    (tmp_path / ".project-directory").write_text("shop\n", encoding="utf-8")
    (tmp_path / "shop").mkdir()

    text = project_snapshot(tmp_path)

    assert "`shop/` has no files yet" in text
    assert "nothing in it to list, search or read" in text


def test_a_project_holding_only_harness_files_is_empty_too(tmp_path: Path) -> None:
    (tmp_path / ".project-directory").write_text("shop\n", encoding="utf-8")
    (tmp_path / "shop").mkdir()
    (tmp_path / "shop" / "package-lock.json").write_text("{}", encoding="utf-8")

    assert "has no files yet" in project_snapshot(tmp_path)


def test_a_stage_s_opening_request_carries_it_before_its_own_request(tmp_path: Path, agents) -> None:  # noqa: F811
    from test_graph_routing import (
        _approved_review,
        _document,
        _graph,
        _milestone,
        _milestone_review,
        _repository,
        _script_through_architecture,
        _security_review,
        _specialist,
        _sprint_plan,
        responds_with,
    )

    from app.graph.workflow import start_workflow

    # Pinned at intake from the product name in a real run; the scripted one
    # does not, so the pin is written here.
    (tmp_path / ".project-directory").write_text("acme-scheduling\n", encoding="utf-8")
    (tmp_path / "acme-scheduling").mkdir()
    (tmp_path / "acme-scheduling" / "booking.py").write_text("def book(slot):\n    return slot\n", encoding="utf-8")
    _script_through_architecture(agents, _approved_review())
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(_milestone("backend"))])
    agents.script("specialist_backend", [responds_with(_specialist())])
    agents.script("specialist_testing", [responds_with(_specialist())])
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])

    state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-snapshot")

    assert state["stage"] == "complete", state.get("error")
    opening = agents.requests["specialist_backend"][0]["messages"]
    assert opening[0]["content"].startswith("The project's files as they stood")
    assert "def book(slot):" in opening[0]["content"]
    assert not opening[-1]["content"].startswith("The project's files")
