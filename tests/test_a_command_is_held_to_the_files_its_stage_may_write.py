"""A command is held to the files its stage may write, as the file tools are.

The file tools refused the acceptance writer product code a dozen ways; then it
ran `python3 -c "open('notes_api/storage.py', 'w').write(...)"`, which the
sandbox ran - failing only on the folder. What a held stage's command changes
outside its own files is put back, and what it makes there is removed.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from app.tools.sandbox import SandboxExecutor

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
WRITER = (
    "from pathlib import Path\n"
    "Path('notes_api/storage.py').write_text('changed by a command')\n"
    "Path('notes_api/extra.py').write_text('made by a command')\n"
    "Path('acceptance/notes.txt').write_text('the stage s own')\n"
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "acceptance.json").write_text(json.dumps({"project": "notes-api", "acceptance_dir": "acceptance"}))
    (tmp_path / ".project-directory").write_text("notes-api")
    root = tmp_path / "notes-api"
    (root / "notes_api").mkdir(parents=True)
    (root / "acceptance").mkdir()
    (root / "notes_api" / "storage.py").write_text("def save():\n    pass\n")
    (root / "acceptance" / "writer.py").write_text(WRITER)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def _run_as(stage: str, root: Path) -> dict:
    env = {"ALLOW_COMMAND_EXECUTION": "true", "SANDBOX_EXECUTION_MODE": "in-container"}
    with mock.patch.dict(os.environ, env), \
         mock.patch("app.observability.transcript._stage_from_config", lambda fallback: stage):
        return SandboxExecutor.execute(["python3", "acceptance/writer.py"], repo_root=str(root),
                                       role_name="testing_specialist", working_directory="notes-api")


def test_the_acceptance_writer_s_command_cannot_change_the_product(project: Path):
    outcome = _run_as("acceptance_author_0", project)

    product = project / "notes-api" / "notes_api"
    assert (product / "storage.py").read_text() == "def save():\n    pass\n"
    assert not (product / "extra.py").exists()
    assert (project / "notes-api" / "acceptance" / "notes.txt").read_text() == "the stage s own"
    assert set(outcome["put_back"]) == {"notes-api/notes_api/storage.py", "notes-api/notes_api/extra.py (made by the command)"}
    assert "put back as it was" in outcome["note"] and not BANNED.search(outcome["note"])


def test_a_builder_s_command_writes_the_product_as_before(project: Path):
    outcome = _run_as("specialist_backend_0", project)

    assert (project / "notes-api" / "notes_api" / "storage.py").read_text() == "changed by a command"
    assert "put_back" not in outcome


def test_a_test_round_s_command_may_write_tests_but_not_the_product(project: Path):
    (project / "notes-api" / "tests").mkdir()
    (project / "notes-api" / "acceptance" / "writer.py").write_text(
        "from pathlib import Path\n"
        "Path('notes_api/storage.py').write_text('a fix made by a test round')\n"
        "Path('tests/test_storage.py').write_text('def test_x():\\n    assert True\\n')\n"
    )

    outcome = _run_as("test_round_1", project)

    assert (project / "notes-api" / "notes_api" / "storage.py").read_text() == "def save():\n    pass\n"
    assert (project / "notes-api" / "tests" / "test_storage.py").exists()
    assert outcome["put_back"] == ["notes-api/notes_api/storage.py"]
