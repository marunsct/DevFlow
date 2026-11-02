"""A product no pack built gets the commands the harness knows in its README, with no round of the sprint for them.

Measured on a project with no stack pack: every criterion passed, the release went back through planning, drafting
and reviews twice for a README, recorded "fix the failing criteria first" with no criterion failing, and the one line
that came back still left the run marked as saying nowhere how to run the product.
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


@pytest.fixture
def project(tmp_path):
    (tmp_path / ".project-directory").write_text("app")
    (tmp_path / "app").mkdir()
    return tmp_path


def _with_a_start(project):
    (project / "app" / "server.py").write_text("print('serving')\n")


def _with_a_suite(project):
    (project / "app" / "acceptance").mkdir()
    (project / "app" / "acceptance" / "run.json").write_text(
        json.dumps({"command": THE_SUITE.split(), "report": "report.xml"}))


def _release(root, attempts, monkeypatch):
    from app.analysis import integration_checks

    monkeypatch.setattr(integration_checks, "problems_that_break_the_product", lambda root, stack=None, brief="": [])
    monkeypatch.setattr(delivery, "_unit_tests_failing", lambda root: [])
    with mock.patch.dict(os.environ, ON):
        return delivery.release(
            {"repository": SimpleNamespace(root_path=str(root)), "release_attempts": attempts},
            {"configurable": {}},
            SimpleNamespace(judgement_model=None, checkpointer=None, repo_root=str(root), allow_subdirectories=True),
        )


def test_the_start_and_the_suite_s_declared_command_are_written_once(project):
    _with_a_start(project)
    _with_a_suite(project)
    with mock.patch.dict(os.environ, ON):
        assert release_docs.complete_the_handoff(project) == ["app/README.md"]
        assert release_docs.what_the_handoff_lacks(project) == []
        assert release_docs.complete_the_handoff(project) == []
    text = (project / "app" / "README.md").read_text()
    assert text.count("python3 server.py") == 1 and text.count(THE_SUITE) == 1
    assert not BANNED.search(text)


def test_the_release_goes_on_with_no_round_of_the_sprint(project, monkeypatch):
    _with_a_start(project)
    _with_a_suite(project)
    released = _release(project, 0, monkeypatch)
    assert released["stage"] != "technical_lead"
    assert not any("how to run" in str(gap) for gap in released.get("completion_gaps") or [])


def test_a_readme_the_product_already_has_keeps_every_word_and_gains_a_section(project):
    _with_a_start(project)
    own = "# Seeded\n\nWritten by the people who own it.\n\n```sh\ncurl localhost:1/x\n```\n"
    (project / "app" / "README.md").write_text(own)
    with mock.patch.dict(os.environ, ON):
        assert release_docs.complete_the_handoff(project) == ["app/README.md"]
    text = (project / "app" / "README.md").read_text()
    assert text.startswith(own) and "python3 server.py" in text


def test_a_readme_naming_a_known_command_is_left_alone(project):
    _with_a_start(project)
    own = "# Seeded\n\nRun `python3 server.py`.\n"
    (project / "app" / "README.md").write_text(own)
    with mock.patch.dict(os.environ, ON):
        assert release_docs.complete_the_handoff(project) == []
    assert (project / "app" / "README.md").read_text() == own


def test_a_service_whose_start_is_unknown_keeps_the_gap_with_its_suite_written_once(project):
    interface_contract.record_at_lock(project, ["AC-1 GET /items -> 200"])
    _with_a_suite(project)
    with mock.patch.dict(os.environ, ON):
        assert release_docs.complete_the_handoff(project) == ["app/README.md"]
        release_docs.complete_the_handoff(project)
        lacks = release_docs.what_the_handoff_lacks(project)
    assert (project / "app" / "README.md").read_text().count(THE_SUITE) == 1
    assert any("says nowhere how to run" in lack for lack in lacks)


def test_when_nothing_is_known_nothing_is_written_and_no_start_file_is_invented(project):
    with mock.patch.dict(os.environ, ON):
        assert release_docs.complete_the_handoff(project) == []
        assert not (project / "app" / "README.md").exists()
        (project / "app" / "README.md").write_text("# Words only\n")
        lacks = release_docs.what_the_handoff_lacks(project)
    assert len(lacks) == 1 and "says nowhere how to run" in lacks[0]
    assert "start.sh" not in lacks[0]
    assert not BANNED.search(lacks[0])


@pytest.mark.parametrize("block", [
    "```sh\ncurl -s localhost:8000/items\n```",
    "```json\n{\"id\": 1}\n```",
    "```http\nGET /items\n```",
])
def test_a_block_that_only_shows_a_request_or_an_answer_says_nothing_of_how_to_run_it(project, block):
    (project / "app" / "README.md").write_text(f"# Items\n\n{block}\n")
    with mock.patch.dict(os.environ, ON):
        assert any("says nowhere how to run" in lack for lack in release_docs.what_the_handoff_lacks(project))


def test_a_block_with_a_command_of_its_own_still_counts(project):
    (project / "app" / "README.md").write_text("# Items\n\n```sh\nbin/serve --port 8000\n```\n")
    with mock.patch.dict(os.environ, ON):
        assert release_docs.what_the_handoff_lacks(project) == []


def test_a_hold_for_the_handoff_says_so_and_not_that_a_criterion_fails(project, monkeypatch):
    held = _release(project, 0, monkeypatch)
    assert held["stage"] == "technical_lead"
    recorded = held["decisions"][-1]
    assert recorded["decision"] == "fix the handoff first"
    assert recorded["decision"] in recorded["options"] and "release" in recorded["options"]
    assert "no README" in recorded["rationale"]
    assert not BANNED.search(recorded["decision"])
