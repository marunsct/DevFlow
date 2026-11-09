"""Every product that ships gets its handoff, and the README says what a stranger needs (harness review HR2.PR.1-2).

41 of 104 products went out with no README: the harness wrote one only when nothing failed, so a product shipped with
failing unit tests had none. And of 63 READMEs, 3 named `PORT` or `DATA_DIR`, 3 named a route, and every one put the
start and the tests in one block that could not run as written - the start never returns.
"""
from __future__ import annotations

import json
import os
import re
from types import SimpleNamespace
from unittest import mock

import pytest

from app.acceptance import interface_contract
from app.graph import delivery
from app.stacks import release_docs

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
ON = {"RELEASE_DOCS_REQUIRED": "on"}
THE_SUITE = "python3 -m pytest acceptance --junitxml=report.xml"
SPEC = """# Technical specification

## Configuration
- variable: PORT; type: Environment Variable; default: 8000 (the server's own); description: Port the service listens on.
- variable: DATA_DIR; type: Environment Variable; default: data/; description: Where the records are kept.
- file: app/server.py; type: Entry Point; description: The service.

## Interface Contract
GET /items and POST /items are the routes.
"""


@pytest.fixture
def project(tmp_path):
    (tmp_path / ".project-directory").write_text("app")
    (tmp_path / "app" / "acceptance").mkdir(parents=True)
    (tmp_path / "app" / "server.py").write_text("print('serving')\n")
    (tmp_path / "app" / "acceptance" / "run.json").write_text(
        json.dumps({"command": THE_SUITE.split(), "report": "report.xml"}))
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technical_specification.md").write_text(SPEC)
    return tmp_path


def test_a_product_shipped_with_failing_unit_tests_gets_a_readme(project, monkeypatch) -> None:
    from app.analysis import integration_checks
    from app.graph import release_with_failing_unit_tests

    monkeypatch.setattr(integration_checks, "problems_that_break_the_product", lambda root, stack=None, brief="": [])
    monkeypatch.setattr(delivery, "_unit_tests_failing", lambda root: ["test_store.py::test_saves fails"])
    monkeypatch.setattr(release_with_failing_unit_tests, "may_ship", lambda *a, **k: True)
    with mock.patch.dict(os.environ, ON):
        delivery.release(
            {"repository": SimpleNamespace(root_path=str(project)), "release_attempts": 0},
            {"configurable": {}},
            SimpleNamespace(judgement_model=None, checkpointer=None, repo_root=str(project), allow_subdirectories=True),
        )
    readme = project / "app" / "README.md"
    assert readme.is_file(), "the product that ships has its handoff"
    assert "python3 server.py" in readme.read_text()


def test_the_readme_names_every_variable_the_specification_declares(project) -> None:
    with mock.patch.dict(os.environ, ON):
        release_docs.complete_the_handoff(project)
    text = (project / "app" / "README.md").read_text()
    assert "## Configuration" in text
    assert "| `PORT` | 8000 | Port the service listens on. |" in text
    assert "| `DATA_DIR` | data/ | Where the records are kept. |" in text
    assert not BANNED.search(text)


def test_the_start_stands_on_its_own_and_the_tests_come_after(project) -> None:
    with mock.patch.dict(os.environ, ON):
        release_docs.complete_the_handoff(project)
    text = (project / "app" / "README.md").read_text()
    fences = re.findall(r"```sh\n(.*?)```", text, re.DOTALL)
    start = next(f for f in fences if "python3 server.py" in f)
    assert THE_SUITE not in start, "the start never returns, so nothing after it in its block runs"
    assert text.index("python3 server.py") < text.index("## Testing it") < text.index(THE_SUITE)
    assert "stays running" in text


def test_the_routes_are_in_the_readme_though_the_specification_names_them(project) -> None:
    interface_contract.record_at_lock(project, ["AC-1 GET /items -> 200", "AC-2 POST /items -> 201"])
    with mock.patch.dict(os.environ, ON):
        release_docs.complete_the_handoff(project)
    text = (project / "app" / "README.md").read_text()
    assert "## What it serves" in text and "| GET | `/items` | 200 |" in text and "| POST | `/items` | 201 |" in text


def test_without_a_configuration_section_the_start_script_s_variables_are_listed(project) -> None:
    """HR2.G.4: the settings a stranger can change, from what the start script reads, when the specification says none."""
    (project / "docs" / "technical_specification.md").write_text("# Technical specification\n")
    (project / "app" / "start.sh").write_text(
        '#!/bin/sh\nexport PORT="${PORT:-8000}" DATA_DIR="${DATA_DIR:-data}"\nexec python3 server.py --host "${HOST:-127.0.0.1}"\n')
    with mock.patch.dict(os.environ, ON):
        release_docs.complete_the_handoff(project)
    text = (project / "app" / "README.md").read_text()
    for row in ("| `PORT` | 8000 |", "| `DATA_DIR` | data |", "| `HOST` | 127.0.0.1 |"):
        assert row in text, text


def test_a_command_line_tool_s_readme_says_how_it_is_used_and_needs_no_second_terminal(tmp_path) -> None:
    """Measured on the first release with LF.715: a command-line tool's README said how to install and test it,
    never how to use it, and told the reader its tests needed it running in another terminal."""
    (tmp_path / ".project-directory").write_text("cli")
    (tmp_path / "cli" / "acceptance").mkdir(parents=True)
    (tmp_path / "cli" / "acceptance" / "run.json").write_text(
        json.dumps({"command": THE_SUITE.split(), "report": "report.xml"}))
    interface_contract.record_at_lock(tmp_path, ["AC-1 command python -m wordstats <file> -> exit 0",
                                                 "AC-5 command python -m wordstats missing.txt -> exit 2"])
    with mock.patch.dict(os.environ, ON):
        release_docs.complete_the_handoff(tmp_path)
    text = (tmp_path / "cli" / "README.md").read_text()
    assert "## Using it" in text and "python -m wordstats <file>" in text and "python -m wordstats missing.txt" in text
    assert "another terminal" not in text
    assert not BANNED.search(text)


def test_the_handoff_score_does_not_ask_a_product_with_no_settings_to_name_them(tmp_path) -> None:
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "bench" / "score.py"
    spec = importlib.util.spec_from_file_location("bench_score_cli", path)
    score = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(score)
    product = tmp_path / "cli"
    product.mkdir()
    (product / "README.md").write_text("# Tool\n\n## Using it\n\n```sh\npython -m tool <file>\n```\n\nRun the tests with pytest.\n")
    found = score.handoff(product)
    assert found["handoff"]["readme_names_its_configuration"] is None
    assert found["handoff"]["readme_says_how_to_start"] is True
