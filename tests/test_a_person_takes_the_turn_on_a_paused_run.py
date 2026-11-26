"""A person takes the turn on a paused run and edits its files through guarded writes (plans UX.12, UX.13).

The owner asked to edit a run's files in co-development mode. Stages commit with `git add -A`, revert a fix that
breaks a locked test and run a cut-off stage again, so a person writing beside them would see their lines swept into
a stage's commit or undone. So editing is turn-taking: one person holds an edit session on a stopped run, nothing
resumes it meanwhile, and every write is refused unless the caller holds the session, the path is one of the
product's files, the suite is not locked over it and the file is as the editor loaded it.
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _workspace(root):
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "h@example.com")
    _git(root, "config", "user.name", "harness")
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("print('one')\n")
    (root / "README.md").write_text("# The product\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "Scaffold")
    (root / ".harness").mkdir()
    (root / ".harness" / "contract.json").write_text("{}")
    (root / "node_modules" / "left-pad").mkdir(parents=True)
    (root / "node_modules" / "left-pad" / "index.js").write_text("module.exports = 1\n")
    (root / ".env").write_text("SECRET=1\n")
    return root


class _Client:
    """The real runs router over one run in `root`, signed in as whoever `as_` names; the run store stood in for."""

    def __init__(self, root, monkeypatch, status="paused"):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.server import auth, runs
        from app.server.auth import get_current_active_user, require_operator

        self.audits = []
        self.run = SimpleNamespace(run_id="run-1", tenant_id="t", status=status, repo_root=str(root))
        runner = SimpleNamespace(run_store=SimpleNamespace(load=lambda run_id: self.run if run_id == "run-1" else None))
        monkeypatch.setattr(runs, "record_audit", lambda **kwargs: None)
        monkeypatch.setattr(auth, "record_audit", lambda **kwargs: self.audits.append(kwargs))
        app = FastAPI()
        app.include_router(runs.create_runs_router(runner, SimpleNamespace(), str(root), str(root)))
        self.user = SimpleNamespace(username="alice", role="operator", tenant_id="t")
        app.dependency_overrides[get_current_active_user] = lambda: self.user
        app.dependency_overrides[require_operator] = lambda: self.user
        self.http = TestClient(app)

    def as_(self, name, tenant="t"):
        self.user = SimpleNamespace(username=name, role="operator", tenant_id=tenant)
        return self.http


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("CO_DEVELOPMENT", "on")


def _loaded(http, path):
    return http.get("/api/runs/run-1/files/content", params={"path": path}).json()["hash"]


# -- UX.12 ------------------------------------------------------------------------------------------------------------

def test_a_running_run_cannot_be_taken(tmp_path, monkeypatch, on):
    client = _Client(_workspace(tmp_path), monkeypatch, status="running")

    refused = client.as_("alice").post("/api/runs/run-1/edit-session")

    assert refused.status_code == 409
    assert client.http.get("/api/runs/run-1/edit-session").json()["session"] is None


def test_a_second_person_cannot_take_a_turn_someone_holds(tmp_path, monkeypatch, on):
    client = _Client(_workspace(tmp_path), monkeypatch)
    assert client.as_("alice").post("/api/runs/run-1/edit-session").status_code == 201

    refused = client.as_("bob").post("/api/runs/run-1/edit-session")

    assert refused.status_code == 409
    assert "alice" in refused.json()["detail"]["message"]
    assert client.as_("alice").get("/api/runs/run-1/edit-session").json()["session"]["yours"] is True


def test_opening_a_session_is_audited(tmp_path, monkeypatch, on):
    client = _Client(_workspace(tmp_path), monkeypatch)

    client.as_("alice").post("/api/runs/run-1/edit-session")

    assert [entry["action"] for entry in client.audits] == ["run.edit.open"]


def _paused_run(runner, root, run_id="run-1"):
    record = runner.register_run(run_id=run_id, thread_id=f"thread-{run_id}", document_names=["brief.md"],
                                 document_paths=["/tmp/brief.md"], owner="alice", tenant_id="t")
    record.status = "paused"
    record.repo_root = str(root)
    runner.run_store.save(record)
    return record


@pytest.fixture
def runner(run_store, monkeypatch):
    from app.server.events import EventBus
    from app.server.runner import WorkflowRunner

    monkeypatch.setenv("CHECKPOINTER_TYPE", "memory")
    return WorkflowRunner(EventBus(), run_store=run_store)


async def test_a_run_a_person_holds_is_not_resumed_answered_or_rewound(tmp_path, runner, on):
    from app.server import edit_session
    from app.server.runner import RunConflict

    root = _workspace(tmp_path)
    _paused_run(runner, root)
    edit_session.open_session(root, "alice", run_status="paused", driven=False)

    for attempt in (lambda: runner.resume_run("run-1"), lambda: runner.rewind_run("run-1", "c1"),
                    lambda: runner.submit_review("run-1", {"action": "approve"})):
        with pytest.raises(RunConflict, match="alice holds the turn"):
            await attempt()
    assert runner.run_store.load("run-1").status == "paused"


async def test_a_lapsed_session_keeps_the_files_and_still_holds_the_run(tmp_path, runner, on):
    from app.server import edit_session
    from app.server.runner import RunConflict

    root = _workspace(tmp_path)
    _paused_run(runner, root)
    long_ago = datetime.now(timezone.utc) - timedelta(hours=2)
    edit_session.open_session(root, "alice", run_status="paused", driven=False, now=long_ago)
    hash_ = edit_session._current(root, "src/app.py")[1]
    edit_session.save(root, "alice", "src/app.py", "print('mine')\n", hash_, run_status="paused", driven=False)

    with pytest.raises(RunConflict):
        await runner.resume_run("run-1")
    taken = edit_session.open_session(root, "bob", run_status="paused", driven=False)

    assert (root / "src" / "app.py").read_text() == "print('mine')\n"
    assert taken["holder"] == "bob" and taken["taken_over_from"] == "alice"
    assert "src/app.py" in taken["touched"]


def test_a_lapsed_session_that_changed_nothing_does_not_hold_the_run(tmp_path, on):
    from app.server import edit_session

    root = _workspace(tmp_path)
    long_ago = datetime.now(timezone.utc) - timedelta(hours=2)
    edit_session.open_session(root, "alice", run_status="paused", driven=False, now=long_ago)

    assert edit_session.blocking_resume(root) is None
    assert edit_session.state(root, "alice") is None


def test_a_session_that_changed_files_is_not_simply_closed(tmp_path, monkeypatch, on):
    client = _Client(_workspace(tmp_path), monkeypatch)
    http = client.as_("alice")
    http.post("/api/runs/run-1/edit-session")
    http.put("/api/runs/run-1/files/content", json={"path": "README.md", "content": "# Mine\n"},
             headers={"If-Match": _loaded(http, "README.md")})

    refused = http.delete("/api/runs/run-1/edit-session")

    assert refused.status_code == 409
    assert refused.json()["detail"]["files"] == ["README.md"]


# -- UX.13 ------------------------------------------------------------------------------------------------------------

def test_the_holder_saves_a_file_as_loaded_and_its_new_hash_is_returned(tmp_path, monkeypatch, on):
    root = _workspace(tmp_path)
    client = _Client(root, monkeypatch)
    http = client.as_("alice")
    http.post("/api/runs/run-1/edit-session")

    saved = http.put("/api/runs/run-1/files/content", json={"path": "src/app.py", "content": "print('two')\n"},
                     headers={"If-Match": _loaded(http, "src/app.py")})

    assert saved.status_code == 200
    assert (root / "src" / "app.py").read_text() == "print('two')\n"
    assert saved.json()["hash"] == _loaded(http, "src/app.py")


def test_a_write_without_a_session_is_refused(tmp_path, monkeypatch, on):
    client = _Client(_workspace(tmp_path), monkeypatch)
    http = client.as_("alice")

    refused = http.put("/api/runs/run-1/files/content", json={"path": "README.md", "content": "x"},
                       headers={"If-Match": _loaded(http, "README.md")})

    assert refused.status_code == 409


def test_a_write_by_someone_not_holding_the_turn_is_refused(tmp_path, monkeypatch, on):
    root = _workspace(tmp_path)
    client = _Client(root, monkeypatch)
    client.as_("alice").post("/api/runs/run-1/edit-session")
    http = client.as_("bob")

    refused = http.put("/api/runs/run-1/files/content", json={"path": "README.md", "content": "x"},
                       headers={"If-Match": _loaded(http, "README.md")})

    assert refused.status_code == 403
    assert (root / "README.md").read_text() == "# The product\n"


def test_a_file_that_moved_on_since_it_was_loaded_is_refused_with_its_text_now(tmp_path, monkeypatch, on):
    root = _workspace(tmp_path)
    client = _Client(root, monkeypatch)
    http = client.as_("alice")
    http.post("/api/runs/run-1/edit-session")
    loaded = _loaded(http, "README.md")
    (root / "README.md").write_text("# Written since\n")

    refused = http.put("/api/runs/run-1/files/content", json={"path": "README.md", "content": "# Mine\n"},
                       headers={"If-Match": loaded})

    assert refused.status_code == 409
    assert refused.json()["detail"]["content"] == "# Written since\n"
    assert (root / "README.md").read_text() == "# Written since\n"


@pytest.mark.parametrize("attack", ["/etc/passwd", "../outside.txt", "src/../../outside.txt"])
def test_a_path_outside_the_workspace_is_refused(tmp_path, monkeypatch, on, attack):
    root = tmp_path / "ws"
    root.mkdir()
    client = _Client(_workspace(root), monkeypatch)
    http = client.as_("alice")
    http.post("/api/runs/run-1/edit-session")

    refused = http.post("/api/runs/run-1/files", json={"path": attack, "content": "x"})

    assert refused.status_code == 400
    assert not (tmp_path / "outside.txt").exists()


@pytest.mark.parametrize("hidden", [".git/config", ".harness/contract.json", "node_modules/left-pad/index.js",
                                    ".env", "config/.env", "node_modules/new.js"])
def test_a_path_the_listing_hides_is_not_written(tmp_path, monkeypatch, on, hidden):
    root = _workspace(tmp_path)
    client = _Client(root, monkeypatch)
    http = client.as_("alice")
    http.post("/api/runs/run-1/edit-session")
    before = (root / hidden).read_bytes() if (root / hidden).exists() else None

    created = http.post("/api/runs/run-1/files", json={"path": hidden, "content": "x"})
    saved = http.put("/api/runs/run-1/files/content", json={"path": hidden, "content": "x"}, headers={"If-Match": "h"})

    assert created.status_code == 403 and saved.status_code == 403
    assert ((root / hidden).read_bytes() if (root / hidden).exists() else None) == before


def test_a_link_is_not_written_through(tmp_path, monkeypatch, on):
    root = tmp_path / "ws"
    root.mkdir()
    _workspace(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "src" / "linked").symlink_to(outside)
    (root / "notes.md").symlink_to(root / "README.md")
    client = _Client(root, monkeypatch)
    http = client.as_("alice")
    http.post("/api/runs/run-1/edit-session")

    into_a_folder = http.post("/api/runs/run-1/files", json={"path": "src/linked/x.py", "content": "x"})
    onto_a_file = http.put("/api/runs/run-1/files/content", json={"path": "notes.md", "content": "x"},
                           headers={"If-Match": _loaded(http, "README.md")})

    assert into_a_folder.status_code in (400, 403) and onto_a_file.status_code == 403
    assert list(outside.iterdir()) == [] and (root / "README.md").read_text() == "# The product\n"


def test_a_file_inside_the_locked_suite_is_refused_with_where_to_ask(tmp_path, monkeypatch, on):
    from app.acceptance import suite

    root = _workspace(tmp_path)
    (root / ".project-directory").write_text("notes\n")
    spec = root / "notes" / "acceptance" / "notes.spec.js"
    spec.parent.mkdir(parents=True)
    spec.write_text("test('[AC-1] adds', ()=>{});\n")
    suite.lock(root)
    client = _Client(root, monkeypatch)
    http = client.as_("alice")
    http.post("/api/runs/run-1/edit-session")

    refused = http.put("/api/runs/run-1/files/content", json={"path": "notes/acceptance/notes.spec.js", "content": "x"},
                       headers={"If-Match": _loaded(http, "notes/acceptance/notes.spec.js")})

    assert refused.status_code == 403
    assert "change request" in refused.json()["detail"]["message"]
    assert spec.read_text() == "test('[AC-1] adds', ()=>{});\n"


def test_a_file_too_large_is_refused(tmp_path, monkeypatch, on):
    client = _Client(_workspace(tmp_path), monkeypatch)
    http = client.as_("alice")
    http.post("/api/runs/run-1/edit-session")

    refused = http.post("/api/runs/run-1/files", json={"path": "big.txt", "content": "x" * (600 * 1024)})

    assert refused.status_code == 413


def test_text_that_is_not_text_is_refused(tmp_path, monkeypatch, on):
    client = _Client(_workspace(tmp_path), monkeypatch)
    http = client.as_("alice")
    http.post("/api/runs/run-1/edit-session")

    refused = http.post("/api/runs/run-1/files", json={"path": "data.bin", "content": "a\u0000b"})

    assert refused.status_code == 415


def test_nothing_is_written_once_the_run_is_going_again(tmp_path, monkeypatch, on):
    root = _workspace(tmp_path)
    client = _Client(root, monkeypatch)
    http = client.as_("alice")
    http.post("/api/runs/run-1/edit-session")
    loaded = _loaded(http, "README.md")
    client.run.status = "running"

    refused = http.put("/api/runs/run-1/files/content", json={"path": "README.md", "content": "x"},
                       headers={"If-Match": loaded})

    assert refused.status_code == 409
    assert (root / "README.md").read_text() == "# The product\n"


def test_the_holder_creates_renames_and_deletes_product_files(tmp_path, monkeypatch, on):
    root = _workspace(tmp_path)
    client = _Client(root, monkeypatch)
    http = client.as_("alice")
    http.post("/api/runs/run-1/edit-session")

    created = http.post("/api/runs/run-1/files", json={"path": "src/util/new.py", "content": "N = 1\n"})
    moved = http.post("/api/runs/run-1/files/rename", json={"path": "src/util/new.py", "to": "src/util/kept.py"},
                      headers={"If-Match": created.json()["hash"]})
    gone = http.delete("/api/runs/run-1/files", params={"path": "README.md"},
                       headers={"If-Match": _loaded(http, "README.md")})

    assert (created.status_code, moved.status_code, gone.status_code) == (201, 200, 200)
    assert (root / "src" / "util" / "kept.py").read_text() == "N = 1\n"
    assert not (root / "src" / "util" / "new.py").exists() and not (root / "README.md").exists()


def test_an_existing_file_is_not_created_over(tmp_path, monkeypatch, on):
    root = _workspace(tmp_path)
    client = _Client(root, monkeypatch)
    http = client.as_("alice")
    http.post("/api/runs/run-1/edit-session")

    refused = http.post("/api/runs/run-1/files", json={"path": "README.md", "content": "x"})

    assert refused.status_code == 409 and (root / "README.md").read_text() == "# The product\n"


def test_with_the_switch_off_every_write_route_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("CO_DEVELOPMENT", "off")
    root = _workspace(tmp_path)
    client = _Client(root, monkeypatch)
    http = client.as_("alice")

    answers = [
        http.post("/api/runs/run-1/edit-session"),
        http.post("/api/runs/run-1/edit-session/heartbeat"),
        http.delete("/api/runs/run-1/edit-session"),
        http.put("/api/runs/run-1/files/content", json={"path": "README.md", "content": "x"}, headers={"If-Match": "h"}),
        http.post("/api/runs/run-1/files", json={"path": "new.md", "content": "x"}),
        http.post("/api/runs/run-1/files/rename", json={"path": "README.md", "to": "R.md"}),
        http.delete("/api/runs/run-1/files", params={"path": "README.md"}),
        http.post("/api/runs/run-1/edit-session/hand-back", json={"reason": "x"}),
        http.post("/api/runs/run-1/edit-session/discard"),
        http.post("/api/runs/run-1/edit-session/bring-in", json={}),
    ]

    assert [answer.status_code for answer in answers] == [403] * len(answers)
    assert http.get("/api/runs/run-1/edit-session").json()["enabled"] is False
    assert (root / "README.md").read_text() == "# The product\n" and not (root / "new.md").exists()


def test_another_tenant_does_not_find_the_run(tmp_path, monkeypatch, on):
    client = _Client(_workspace(tmp_path), monkeypatch)

    refused = client.as_("mallory", tenant="other").post("/api/runs/run-1/edit-session")
    taken = client.as_("alice").post("/api/runs/run-1/edit-session")

    assert refused.status_code == 404 and taken.status_code == 201
