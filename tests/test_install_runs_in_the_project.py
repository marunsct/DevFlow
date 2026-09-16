"""A bare `npm install` runs in the project instead of being refused.

Run 8d28ee3f spent two model calls on this: bare `npm install`, refused with
a message naming the directory to use, then the identical command with that
directory filled in. The refusal could only ever name one directory - a
project is pinned, and there is one - so the harness does what it was asking
for and says where it ran.
"""

import json

from app.tools.sandbox import (
    manifest_written_outside_the_project,
    the_project_this_command_belongs_in,
)


def _pinned(tmp_path, name="todo-app"):
    (tmp_path / name).mkdir()
    (tmp_path / name / "package.json").write_text("{}", encoding="utf-8")
    from app.tools.repository import _pin_project_directory

    _pin_project_directory(tmp_path, name)
    return tmp_path


def test_it_names_the_pinned_project_for_a_bare_install(tmp_path):
    root = _pinned(tmp_path)
    assert the_project_this_command_belongs_in(["npm", "install"], str(root)) == "todo-app"


def test_a_command_aimed_with_prefix_is_left_alone(tmp_path):
    root = _pinned(tmp_path)
    assert (
        the_project_this_command_belongs_in(
            ["npm", "install", "--prefix", "todo-app"], str(root)
        )
        is None
    )


def test_a_command_that_writes_no_manifest_is_left_alone(tmp_path):
    root = _pinned(tmp_path)
    assert the_project_this_command_belongs_in(["npm", "test"], str(root)) is None


def test_nothing_to_redirect_to_when_no_project_is_pinned(tmp_path):
    assert the_project_this_command_belongs_in(["npm", "install"], str(tmp_path)) is None


def test_the_old_message_still_describes_the_same_commands(tmp_path):
    """The two must agree: the message exists for callers that only report."""
    root = _pinned(tmp_path)
    assert manifest_written_outside_the_project(["npm", "install"], str(root))
    assert manifest_written_outside_the_project(["npm", "test"], str(root)) is None


def test_the_run_is_redirected_and_says_so(tmp_path, monkeypatch):
    root = _pinned(tmp_path)
    seen = {}

    from app.tools.sandbox import SandboxExecutor

    def fake_run(command, repo_root, role_name, category, extra_env, working_directory):
        seen["working_directory"] = working_directory
        return {"stdout": "", "stderr": "", "returncode": 0}

    monkeypatch.setattr(SandboxExecutor, "_run", staticmethod(fake_run))
    monkeypatch.setattr("app.tools.sandbox._record_execution", lambda *a, **k: None)
    monkeypatch.setattr("app.tools.sandbox._note_about_running_this_again", lambda *a, **k: "")

    outcome = SandboxExecutor.execute(["npm", "install"], str(root), category="install")

    assert seen["working_directory"] == "todo-app"
    assert "error" not in outcome
    assert "Ran this in 'todo-app'" in outcome["note"]


def test_a_directory_the_model_chose_is_not_overridden(tmp_path, monkeypatch):
    root = _pinned(tmp_path)
    seen = {}

    from app.tools.sandbox import SandboxExecutor

    def fake_run(command, repo_root, role_name, category, extra_env, working_directory):
        seen["working_directory"] = working_directory
        return {"stdout": "", "stderr": "", "returncode": 0}

    monkeypatch.setattr(SandboxExecutor, "_run", staticmethod(fake_run))
    monkeypatch.setattr("app.tools.sandbox._record_execution", lambda *a, **k: None)
    monkeypatch.setattr("app.tools.sandbox._note_about_running_this_again", lambda *a, **k: "")

    outcome = SandboxExecutor.execute(
        ["npm", "install"], str(root), category="install", working_directory="somewhere-else"
    )

    assert seen["working_directory"] == "somewhere-else"
    assert "Ran this in" not in (outcome.get("note") or "")
