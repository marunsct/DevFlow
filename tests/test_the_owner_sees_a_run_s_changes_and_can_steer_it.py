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


def _client(root, monkeypatch, **record):
    """The real runs router over one run in `root`; the signed-in user, the run store (no database here) and the audit
    trail stood in for."""
    from types import SimpleNamespace

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.server import runs
    from app.server.auth import get_current_active_user, require_operator

    run = SimpleNamespace(run_id="run-1", tenant_id="t", status="running", repo_root=str(root), **record)
    runner = SimpleNamespace(run_store=SimpleNamespace(load=lambda run_id: run if run_id == "run-1" else None))
    monkeypatch.setattr(runs, "record_audit", lambda **kwargs: None)
    app = FastAPI()
    app.include_router(runs.create_runs_router(runner, SimpleNamespace(), str(root), str(root)))
    user = SimpleNamespace(username="owner", role="operator", tenant_id="t")
    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[require_operator] = lambda: user
    return TestClient(app)


def test_the_endpoints_exist(tmp_path, monkeypatch):
    client = _client(_repo(tmp_path), monkeypatch)

    history = client.get("/api/runs/run-1/changes").json()["commits"]
    shown = client.get(f"/api/runs/run-1/changes/{history[0]['sha']}")
    sent = client.post("/api/runs/run-1/steering", json={"text": "Keep the greeting short."})
    kept = client.get("/api/runs/run-1/steering").json()["notes"]

    assert [c["message"] for c in history][:1] == ["Fix: [AC-1] the greeting"]
    assert shown.status_code == 200 and "three" in str(shown.json())
    assert sent.status_code == 201 and "Keep the greeting short." in str(kept)


# --- Initiative AO.8: hygiene --------------------------------------------------

def test_git_is_run_without_textconv_or_an_external_diff_and_a_timeout_is_its_own_error(tmp_path, monkeypatch):
    import subprocess

    root = _repo(tmp_path)
    seen = []
    real = subprocess.run

    def spy(argv, **kwargs):
        seen.append(argv)
        return real(argv, **kwargs)

    monkeypatch.setattr(changes.subprocess, "run", spy)
    changes.diff(root, changes.commits(root)[0]["sha"])

    shown = next(a for a in seen if "show" in a)
    assert "--no-textconv" in shown and "--no-ext-diff" in shown and "core.fsmonitor=false" in shown

    def slow(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, 20)

    monkeypatch.setattr(changes.subprocess, "run", slow)
    with pytest.raises(changes.ChangesTookTooLong):
        changes.commits(root)


def test_the_endpoints_answer_504_on_a_timeout(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    client = _client(root, monkeypatch)
    sha = changes.commits(root)[0]["sha"]

    def slow(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, 20)

    monkeypatch.setattr(changes.subprocess, "run", slow)

    assert client.get("/api/runs/run-1/changes").status_code == 504
    assert client.get(f"/api/runs/run-1/changes/{sha}").status_code == 504


def test_an_agent_cannot_write_into_the_workspace_s_history(tmp_path):
    from app.tools.repository import RepositoryToolError, write_approved_artifact

    (tmp_path / ".harness").mkdir()
    (tmp_path / ".git" / "hooks").mkdir(parents=True)

    with pytest.raises(RepositoryToolError, match="which a tool fills"):  # the guard that already covered `.git/`
        write_approved_artifact(tmp_path, ".git/hooks/pre-commit", "#!/bin/sh\necho run\n")
    assert not (tmp_path / ".git" / "hooks" / "pre-commit").exists()


def test_the_evidence_names_what_the_release_did_not_prove_and_how_the_stack_is_covered(tmp_path, monkeypatch):
    from app.server import runs

    client = _client(tmp_path, monkeypatch, completion_gaps=["AC-2 ships deferred, unproven by the suite: no test"])

    evidence = client.get("/api/runs/run-1/evidence").json()

    assert evidence["completion_gaps"] == ["AC-2 ships deferred, unproven by the suite: no test"]
    assert "support_tier" in evidence
    assert runs._support_tier_of("/nowhere") == ""
