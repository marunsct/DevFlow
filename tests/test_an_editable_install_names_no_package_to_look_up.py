"""An editable install names the project's own folder, never a package the registry should have (LF.1313).

Measured on one medium run: the stack setup's `pip install -e task-management-dashboard/backend[test]` was refused
twice as "the pypi registry has no package of that name", and the setup lost its calls to it.
"""
from __future__ import annotations

from app.tools import dependency_gate


def test_an_editable_install_of_the_project_s_own_folder_names_no_package():
    named = dependency_gate._named_on_the_command_line(  # noqa: SLF001
        ["pip", "install", "-e", "task-management-dashboard/backend[test]", "requests==2.32.3"])

    assert named == ["requests"]


def test_the_long_form_names_none_either():
    assert dependency_gate._named_on_the_command_line(  # noqa: SLF001
        ["pip", "install", "--editable", "backend"]) == []
