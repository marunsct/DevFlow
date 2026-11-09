"""Installing the workspace's own project by its path adds no dependency, whatever the brief rules out.

Measured on two runs in a row: a suite writer's `pip install -e . pytest` (and `pip install -e word-tool/ pytest`)
was refused under a brief allowing the standard library only, though the project is the product itself.
"""
from __future__ import annotations

from unittest import mock

import pytest

from app.tools import sandbox

BRIEF = "Python 3 only, standard library - no third-party dependencies"


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "word-tool").mkdir()
    (tmp_path / "word-tool" / ".venv").mkdir()
    return tmp_path


def _refusal(workspace, command):
    with mock.patch.object(sandbox, "_the_brief_forbids_installing_anything", return_value=BRIEF):
        return sandbox._refuse_an_install_the_brief_rules_out(command, str(workspace))


@pytest.mark.parametrize("command", [
    ["pip", "install", "-e", "."],
    ["pip", "install", "-e", "word-tool/"],
    ["pip", "install", "file:word-tool"],
])
def test_the_project_itself_is_not_refused(workspace, command):
    assert _refusal(workspace, command) == ""


@pytest.mark.parametrize("command", [
    ["pip", "install", "requests"],
    ["pip", "install", "-e", ".", "requests"],
    ["pip", "install", "../elsewhere/"],
])
def test_a_third_party_package_is_still_refused(workspace, command):
    assert "Refusing to install" in _refusal(workspace, command)
