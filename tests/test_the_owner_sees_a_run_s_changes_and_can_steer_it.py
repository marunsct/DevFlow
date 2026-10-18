"""The owner sees what a run changed, commit by commit, and can steer a run while it runs (UI plan).

Owner decision 2026-10-18: a diff viewer, and steering built on the existing
instruction injection rather than a second mechanism. The workspace already
commits every stage's work; the changes endpoints only read that history. A
steering note is kept in the run's workspace, and the instruction middleware
adds it to every later model call of that run.
"""
from __future__ import annotations

import subprocess

import pytest

from app.server import changes, steering


def _repo(tmp_path):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "h@example.com")
    git("config", "user.name", "harness")
    (tmp_path / "app.py").write_text("print('one')\n")
    git("add", "-A")
    git("commit", "-qm", "Before defect_fix_1_0")
    (tmp_path / "app.py").write_text("print('two')\nprint('three')\n")
    git("commit", "-qam", "Fix: [AC-1] the greeting")
    return tmp_path


def test_the_history_lists_each_commit_with_its_files(tmp_path):
    root = _repo(tmp_path)

    found = changes.commits(root)

    assert [c["message"] for c in found] == ["Fix: [AC-1] the greeting", "Before defect_fix_1_0"]
    assert found[0]["files"] == [{"path": "app.py", "added": 2, "removed": 1}]


def test_one_commit_s_diff_is_returned(tmp_path):
    root = _repo(tmp_path)
    sha = changes.commits(root)[0]["sha"]

    shown = changes.diff(root, sha)

    assert "-print('one')" in shown["diff"] and "+print('three')" in shown["diff"]
    assert shown["truncated"] is False


def test_only_a_hash_reaches_git(tmp_path):
    root = _repo(tmp_path)
    with pytest.raises(changes.ChangesUnavailable):
        changes.diff(root, "HEAD; rm -rf /")
    with pytest.raises(changes.ChangesUnavailable):
        changes.diff(root, "--output=/tmp/x")


def test_a_workspace_with_no_history_says_so(tmp_path):
    with pytest.raises(changes.ChangesUnavailable):
        changes.commits(tmp_path)


def test_a_note_reaches_the_run_s_next_calls(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app.plugins import middleware

    steering.add(tmp_path, "Keep the sign-in page as it is; fix the session cookie.", "owner")
    monkeypatch.setattr(middleware, "_extract_stack_keywords", lambda root: [])
    seen = {}

    class _Request:
        system_message = SimpleNamespace(content="You are the backend specialist.")

        def override(self, **changes_):
            seen.update(changes_)
            return self

    middleware.build_plugin_instructions_middleware(str(tmp_path)).wrap_model_call(_Request(), lambda r: r)

    said = seen["system_message"].content
    assert said.startswith("You are the backend specialist.")
    assert "THE OWNER'S DIRECTION FOR THIS RUN" in said
    assert "fix the session cookie" in said


def test_notes_are_kept_and_a_call_carries_the_newest(tmp_path):
    for n in range(steering.MOST_NOTES_PER_CALL + 2):
        steering.add(tmp_path, f"note {n}", "owner")

    block = steering.as_instructions(tmp_path)

    assert len(steering.notes(tmp_path)) == steering.MOST_NOTES_PER_CALL + 2
    assert "note 0" not in block and f"note {steering.MOST_NOTES_PER_CALL + 1}" in block
    with pytest.raises(ValueError):
        steering.add(tmp_path, "   ", "owner")


def test_the_endpoints_exist():
    import inspect

    from app.server import runs

    source = inspect.getsource(runs)
    for route in ('"/{run_id}/changes"', '"/{run_id}/changes/{sha}"', '"/{run_id}/steering"'):
        assert route in source
