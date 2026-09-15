"""Where files go, decided once, so every stage puts them in the same place.

Each stage builds its own agent and none can see what an earlier one chose, so
without a stated convention each invents a layout and they disagree:

- run-64df2b20 put `test_auth.py` and `auth.test.js` in one `tests/` directory,
  beside `__init__.py`, `requirements.txt` and `package.json`.
- run-7b11cb67 wrote `css/style.css` first, so `css` became the project.
- run-2b5def74 finished with two `tests/` directories holding three files of
  the same names.

The convention is deliberately not one fixed skeleton. run-da6c5e19 shipped a
flat five-file project with a passing suite, and inventing `ui/`, `db/`,
`model/` for it would add structure nobody needs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.project_layout import PROJECT_LAYOUT


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_the_convention_names_the_project_after_the_product():
    flat = _flat(PROJECT_LAYOUT)

    assert "lowercase-with-hyphens" in flat
    assert "Never `app/`, `src/`, `backend/` or `css/`" in flat


def test_a_small_product_is_told_to_stay_flat():
    """run-da6c5e19 shipped five files in one directory and a passing suite."""
    flat = _flat(PROJECT_LAYOUT)

    assert "Keep it FLAT" in flat
    assert "A five-file product needs no folders" in flat


def test_a_multi_tier_product_gets_one_directory_per_tier():
    flat = _flat(PROJECT_LAYOUT)

    assert "One directory per tier" in flat
    assert "task-dashboard/backend/" in flat
    assert "task-dashboard/frontend/" in flat


def test_the_rule_that_makes_it_checkable_is_stated():
    flat = _flat(PROJECT_LAYOUT)

    assert "ONE LANGUAGE PER DIRECTORY" in flat
    assert "a manifest and a test runner address" in flat


def test_every_stage_that_shapes_the_project_is_told():
    """The architect decides it, the technical lead delegates against it, and
    every writing agent follows it. Reaching two of three is how a convention
    becomes a suggestion."""
    from app.agents.principal_architect import _SYSTEM_PROMPT as architect
    from app.agents.role_agent import _WRITING_RULES
    from app.agents.technical_lead import _SYSTEM_PROMPT as lead

    for name, text in (
        ("architect", architect), ("technical lead", lead), ("writing rules", _WRITING_RULES)
    ):
        assert "WHERE FILES GO" in text, name


# --- the check behind the last rule ---------------------------------------


def _summary(root: Path) -> list[str]:
    from app.analysis.integration_checks import summarise_integration

    return [l for l in summarise_integration(str(root)).splitlines() if "languages at once" in l]


def test_two_languages_in_one_directory_is_reported(tmp_path: Path):
    """run-64df2b20's actual shape, in a project whose stack was Python."""
    tests = tmp_path / "med2" / "tests"
    tests.mkdir(parents=True)
    (tests / "test_auth.py").write_text("def test_a(): pass\n", encoding="utf-8")
    (tests / "auth.test.js").write_text('test("a", () => {});\n', encoding="utf-8")

    found = _summary(tmp_path)

    assert found
    assert "Python" in found[0] and "JavaScript" in found[0]


def test_two_manifests_in_one_directory_is_reported(tmp_path: Path):
    """Neither runner sees a complete project."""
    project = tmp_path / "med2"
    project.mkdir()
    (project / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    (project / "package.json").write_text("{}\n", encoding="utf-8")

    assert _summary(tmp_path)


def test_a_flat_single_language_project_is_not_reported(tmp_path: Path):
    """run-da6c5e19's shape, which worked."""
    project = tmp_path / "task-manager"
    project.mkdir()
    for name in ("app.js", "app.test.mjs", "index.html", "style.css", "package.json"):
        (project / name).write_text("x\n", encoding="utf-8")

    assert _summary(tmp_path) == []


def test_tiers_in_their_own_directories_are_not_reported(tmp_path: Path):
    """The layout the convention asks for must not be flagged by the check
    behind the convention."""
    for folder, name in (
        ("backend", "main.py"), ("backend", "requirements.txt"),
        ("frontend", "App.jsx"), ("frontend", "package.json"),
    ):
        directory = tmp_path / "task-dashboard" / folder
        directory.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text("x\n", encoding="utf-8")

    assert _summary(tmp_path) == []


def test_typescript_beside_javascript_is_ordinary(tmp_path: Path):
    """One toolchain, one manifest - flagging it would teach the reviewer to
    discount the check."""
    project = tmp_path / "app-x"
    project.mkdir()
    (project / "a.ts").write_text("export const a = 1;\n", encoding="utf-8")
    (project / "b.js").write_text("export const b = 2;\n", encoding="utf-8")
    (project / "package.json").write_text("{}\n", encoding="utf-8")

    assert _summary(tmp_path) == []


def test_the_checks_can_see_a_python_project_at_all(tmp_path: Path):
    """They collected only web files, so every cross-file check was blind on a
    product with a Python or Go backend - which `brief_medium` asks for."""
    from app.analysis.integration_checks import _source_files

    (tmp_path / "main.py").write_text("x\n", encoding="utf-8")
    (tmp_path / "go.mod").write_text("module x\n", encoding="utf-8")
    (tmp_path / "app.js").write_text("x\n", encoding="utf-8")

    names = {p.name for p in _source_files(tmp_path)}

    assert {"main.py", "go.mod", "app.js"} <= names
