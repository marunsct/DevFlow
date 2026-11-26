"""A person hands the turn back, or discards the edits, and a brownfield run keeps their work apart (UX.15-UX.16b).

Turn-taking is safe only if the agents learn of the person's change and the record keeps it as the person's: one
commit of exactly the session's files authored by them, a note the next stage reads, the checks taken before any
stage so a test the edit broke is not charged to a stage, and in a seeded run the code map built again, the seeded
tests changed only knowingly, the person's commit kept apart in the delivered branch, and changes pushed to the source
repository brought in at a pause - with a conflict leaving the workspace as it was.
"""
from __future__ import annotations

import re
import subprocess
from types import SimpleNamespace

import pytest

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


def _workspace(root):
    root.mkdir(exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "h@example.com")
    _git(root, "config", "user.name", "harness")
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("def greet():\n    return 'hi'\n")
    (root / "src" / "store.py").write_text("ITEMS = []\n")
    (root / "README.md").write_text("# The product\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "Scaffold")
    return root


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("CO_DEVELOPMENT", "on")


def _session(root, user="alice"):
    from app.server import edit_session

    edit_session.open_session(root, user, run_status="paused", driven=False)


def _save(root, path, text, user="alice", **kwargs):
    from app.server import edit_session

    return edit_session.save(root, user, path, text, edit_session._current(root, path)[1], run_status="paused",
                             driven=False, **kwargs)


def _hand_back(root, reason="greet by name", user="alice"):
    from app.server import edit_session

    return edit_session.hand_back(root, user, reason, run_id="", run_status="paused", driven=False)


# -- UX.15 ------------------------------------------------------------------------------------------------------------

def test_the_commit_holds_exactly_the_session_s_files_authored_by_the_person(tmp_path, on):
    root = _workspace(tmp_path / "ws")
    (root / "src" / "store.py").write_text("ITEMS = ['a stage was writing this']\n")
    _session(root)
    _save(root, "src/app.py", "def greet(name):\n    return f'hi {name}'\n")

    done = _hand_back(root)

    assert done["files"] == ["src/app.py"]
    assert _git(root, "show", "--name-only", "--format=%an|%s", "HEAD").split() == \
        ["alice|By", "alice:", "greet", "by", "name", "src/app.py"]
    assert "a stage was writing this" in (root / "src" / "store.py").read_text()
    assert "src/store.py" in _git(root, "status", "--porcelain")


def test_the_next_stage_s_first_call_carries_the_note_with_the_files(tmp_path, on):
    from app.server import steering

    root = _workspace(tmp_path / "ws")
    _session(root)
    _save(root, "src/app.py", "def greet(name):\n    return f'hi {name}'\n")
    _hand_back(root)

    told = steering.as_instructions(root, "defect_fix_1_0")

    assert "changed its files between stages" in told
    assert "src/app.py (+2 -2)" in told
    assert "greet by name" in told and "return f'hi {name}'" in told
    assert "change them only when a locked acceptance test requires it" in told


def test_the_notes_a_hand_back_writes_avoid_the_banned_words():
    from app.server import edit_session

    texts = [
        edit_session.note_text("alice", "rename the store", {"src/a.py": (1, 1)}, {"src/a.py": "R"}, "+x\n-y"),
        edit_session.checks_note(["unit: test_greet"], ["acceptance: [AC-1] adds"]),
        edit_session.MAP_OPENING,
    ]

    assert not [text for text in texts if BANNED.search(text)]


def test_a_changed_locked_suite_is_restored_and_reported(tmp_path, on):
    from app.acceptance import suite

    root = _workspace(tmp_path / "ws")
    (root / ".project-directory").write_text("notes\n")
    spec = root / "notes" / "acceptance" / "notes.spec.js"
    spec.parent.mkdir(parents=True)
    spec.write_text("test('[AC-1] adds', ()=>{});\n")
    suite.lock(root)
    _session(root)
    _save(root, "README.md", "# Mine\n")
    spec.write_text("test('[AC-1] adds', ()=>{ /* loosened */ });\n")

    done = _hand_back(root)

    assert spec.read_text() == "test('[AC-1] adds', ()=>{});\n"
    assert any("notes/acceptance/notes.spec.js" in line for line in done["restored_suite"])


def test_a_test_the_edit_broke_is_recorded_as_the_person_s(tmp_path, on, monkeypatch):
    from app import ci
    from app.server import edit_session, steering

    root = _workspace(tmp_path / "ws")
    _session(root)
    _save(root, "src/app.py", "def greet(name):\n    return f'hi {name}'\n")
    _hand_back(root)
    # The checks run the product's tests in the sandbox; its measurements stand in for the containers.
    monkeypatch.setattr(ci, "load", lambda root, which="latest": ci.Snapshot(
        label="sprint 1", commit="c1", unit={"test_greet": "passed", "test_store": "passed"}, acceptance={},
        unit_ran=True))
    monkeypatch.setattr(ci, "take", lambda root, label, **kw: ci.Snapshot(
        label=label, commit="c2", unit={"test_greet": "failed", "test_store": "passed"}, acceptance={},
        unit_ran=True))

    edit_session.take_the_pending_checks("", root)

    checks = edit_session.hand_backs(root)[-1]["checks"]
    assert checks["broke"] == ["unit: test_greet"]
    told = steering.as_instructions(root, "defect_fix_1_0")
    assert "the person's change broke them, not a stage: unit: test_greet" in told
    assert edit_session.take_the_pending_checks("", root) is None


def test_the_sprint_record_names_the_person_s_hand_back(tmp_path, on):
    from app.server import edit_session

    root = _workspace(tmp_path / "ws")
    _session(root)
    _save(root, "src/app.py", "def greet(name):\n    return name\n")
    _hand_back(root)

    lines = edit_session.for_the_sprint_record(root, since="2000-01-01T00:00:00+00:00")

    assert len(lines) == 1
    assert lines[0].startswith("alice handed back: greet by name (1 file(s): src/app.py")
    assert edit_session.for_the_sprint_record(root, since="2999-01-01T00:00:00+00:00") == []


def test_the_sprint_record_document_shows_a_hand_back_only_when_there_was_one():
    from app.agents.sprint_summary import render_sprint_summary

    def rendered(**extra):
        return render_sprint_summary(sprint_number=1, total_sprints=1, goal="Greet", planned=[],
                                     attempts=[{"number": 1, "status": "Completed", "features": [], "defects": [],
                                                **extra}])

    shown = rendered(hand_backs=["alice handed back: greet by name (1 file(s): src/app.py; commit abc)"])

    assert "## Changed by a Person" in shown and "- alice handed back: greet by name" in shown
    assert "Changed by a Person" not in rendered()


def test_a_rewind_is_offered_when_an_earlier_stage_s_document_was_changed(tmp_path, on):
    root = _workspace(tmp_path / "ws")
    (root / "docs").mkdir()
    (root / "docs" / "specification.md").write_text("# Spec\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "Specification")
    _session(root)
    _save(root, "docs/specification.md", "# Spec\n\nThe greeting names the person.\n")

    done = _hand_back(root, "the greeting names the person")

    assert done["rewind_offered"] is True and done["documents"] == ["docs/specification.md"]


def test_discard_puts_back_only_the_session_s_files(tmp_path, on):
    from app.server import edit_session

    root = _workspace(tmp_path / "ws")
    (root / "src" / "store.py").write_text("ITEMS = ['a stage was writing this']\n")
    _session(root)
    _save(root, "src/app.py", "broken(\n")
    edit_session.create(root, "alice", "src/extra.py", "X = 1\n", run_status="paused", driven=False)
    edit_session.rename(root, "alice", "README.md", "READ.md", edit_session._current(root, "README.md")[1],
                        run_status="paused", driven=False)

    done = edit_session.discard(root, "alice")

    assert sorted(done["restored"]) == ["READ.md", "README.md", "src/app.py", "src/extra.py"]
    assert (root / "src" / "app.py").read_text() == "def greet():\n    return 'hi'\n"
    assert (root / "README.md").read_text() == "# The product\n" and not (root / "READ.md").exists()
    assert not (root / "src" / "extra.py").exists()
    assert (root / "src" / "store.py").read_text() == "ITEMS = ['a stage was writing this']\n"
    assert edit_session.state(root, "alice") is None


def test_the_hand_back_route_is_audited_and_lets_the_run_go_on(tmp_path, monkeypatch, on):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.server import auth, edit_session, runs
    from app.server.auth import get_current_active_user, require_operator

    root = _workspace(tmp_path / "ws")
    audits = []
    run = SimpleNamespace(run_id="run-1", tenant_id="t", status="paused", repo_root=str(root))
    runner = SimpleNamespace(run_store=SimpleNamespace(load=lambda run_id: run))
    monkeypatch.setattr(auth, "record_audit", lambda **kwargs: audits.append(kwargs))
    app = FastAPI()
    app.include_router(runs.create_runs_router(runner, SimpleNamespace(), str(root), str(root)))
    user = SimpleNamespace(username="alice", role="operator", tenant_id="t")
    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[require_operator] = lambda: user
    http = TestClient(app)
    http.post("/api/runs/run-1/edit-session")
    loaded = http.get("/api/runs/run-1/files/content", params={"path": "README.md"}).json()["hash"]
    http.put("/api/runs/run-1/files/content", json={"path": "README.md", "content": "# Mine\n"},
             headers={"If-Match": loaded})

    done = http.post("/api/runs/run-1/edit-session/hand-back", json={"reason": "say what it is"})

    assert done.status_code == 200 and done.json()["files"] == ["README.md"]
    assert [entry["action"] for entry in audits] == ["run.edit.open", "run.edit.hand_back"]
    assert audits[-1]["detail"]["files"] == ["README.md"]
    assert edit_session.blocking_resume(root) is None


# -- UX.16a -----------------------------------------------------------------------------------------------------------

def _seeded(root):
    from app.acceptance.regression_contract import mark_seeded

    (root / "tests").mkdir()
    (root / "tests" / "test_app.py").write_text("def test_greet():\n    assert True\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "The product as it is")
    mark_seeded(root, {"type": "git", "commit": _git(root, "rev-parse", "HEAD").strip()})
    return root


def test_a_renamed_module_is_in_the_next_stage_s_code_map(tmp_path, on):
    from app.agents.code_map import HEADING
    from app.server import edit_session, steering

    root = _seeded(_workspace(tmp_path / "ws"))
    _session(root)
    edit_session.rename(root, "alice", "src/store.py", "src/inventory.py", edit_session._current(root, "src/store.py")[1],
                        run_status="paused", driven=False)
    _hand_back(root, "the store is the inventory")

    told = steering.as_instructions(root, "defect_fix_1_0")
    later = steering.as_instructions(root, "code_review_1_1")

    assert "built again after the person's change" in told
    assert "src/inventory.py" in told.split(HEADING)[1] and "src/store.py" not in told.split(HEADING)[1]
    assert "built again after the person's change" not in later


def test_a_seeded_test_is_changed_only_with_confirmation_and_the_baseline_is_taken_again(tmp_path, on, monkeypatch):
    from app import ci
    from app.server import edit_session

    root = _seeded(_workspace(tmp_path / "ws"))
    _session(root)

    with pytest.raises(edit_session.Refused) as refused:
        _save(root, "tests/test_app.py", "def test_greet():\n    assert 1\n")
    _save(root, "tests/test_app.py", "def test_greet():\n    assert 1\n", confirm_baseline=True)
    done = _hand_back(root, "a sharper baseline test")
    saved = []
    monkeypatch.setattr(ci, "load", lambda root, which="latest": None)
    monkeypatch.setattr(ci, "take", lambda root, label, **kw: ci.Snapshot(label=label, commit="c", unit={"t": "passed"},
                                                                          acceptance={}, unit_ran=True))
    monkeypatch.setattr(ci, "save", lambda root, snapshot, accepted=False: saved.append(accepted))
    checks = edit_session.take_the_pending_checks("", root)

    assert refused.value.status == 409 and refused.value.extra["needs_confirmation"] == "baseline_test"
    assert done["baseline_tests"] == ["tests/test_app.py"]
    assert checks["baseline_retaken"] is True and saved == [True]


def test_the_delivered_branch_keeps_the_person_s_commit_apart(tmp_path, on):
    from app.server import repository_delivery

    root = _seeded(_workspace(tmp_path / "ws"))
    base = _git(root, "rev-parse", "HEAD").strip()
    (root / "src" / "store.py").write_text("ITEMS = ['kept by a stage']\n")
    _git(root, "commit", "-qam", "Sprint 1")
    _session(root)
    _save(root, "src/app.py", "def greet(name):\n    return name\n")
    _hand_back(root, "greet by name")

    delivered = repository_delivery.delivered_commit(root, base, "The change\n")

    assert _git(root, "log", "--format=%an|%s", f"{base}..{delivered}").splitlines() == [
        "Product Workflow|The change", "alice|By alice: greet by name"]
    assert _git(root, "show", f"{delivered}:src/store.py") == "ITEMS = ['kept by a stage']\n"
    assert _git(root, "show", "--name-only", "--format=", f"{delivered}^").split() == ["src/app.py"]


# -- UX.16b -----------------------------------------------------------------------------------------------------------

def _two_repositories(tmp_path, monkeypatch):
    """The source repository a person pushes to, and a run's workspace seeded from it."""
    from app.server.seeding import seed_workspace

    monkeypatch.setenv("SEED_ALLOWED_SCHEMES", "file,https")
    source = _workspace(tmp_path / "source")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    seed_workspace(workspace, SimpleNamespace(type="git", url=f"file://{source}", ref=None, token=None, depth=1),
                   resolve_upload=lambda upload: None)
    return source, workspace


def test_a_pushed_commit_is_brought_in_and_noted(tmp_path, monkeypatch, on):
    from app.server import edit_session, steering

    source, root = _two_repositories(tmp_path, monkeypatch)
    (source / "src" / "store.py").write_text("ITEMS = ['pushed by the person']\n")
    _git(source, "commit", "-qam", "Seed the store")
    (root / "README.md").write_text("# The product, as a stage wrote it\n")
    _git(root, "-c", "user.name=harness", "-c", "user.email=h@x", "commit", "-qam", "Sprint 1")
    _session(root)

    done = edit_session.bring_in(root, "alice", run_id="", run_status="paused", driven=False)

    assert (root / "src" / "store.py").read_text() == "ITEMS = ['pushed by the person']\n"
    assert (root / "README.md").read_text() == "# The product, as a stage wrote it\n"
    assert done["files"] == ["src/store.py"] and done["kind"] == "brought_in"
    assert "src/store.py" in steering.as_instructions(root, "specialist_backend_0")


def test_a_conflict_stops_with_the_workspace_unchanged(tmp_path, monkeypatch, on):
    from app.server import edit_session

    source, root = _two_repositories(tmp_path, monkeypatch)
    (source / "src" / "app.py").write_text("def greet():\n    return 'hello'\n")
    _git(source, "commit", "-qam", "Hello")
    (root / "src" / "app.py").write_text("def greet():\n    return 'hey'\n")
    _git(root, "-c", "user.name=harness", "-c", "user.email=h@x", "commit", "-qam", "Sprint 1")
    head = _git(root, "rev-parse", "HEAD")
    _session(root)

    with pytest.raises(edit_session.Refused) as refused:
        edit_session.bring_in(root, "alice", run_id="", run_status="paused", driven=False)

    assert refused.value.status == 409 and refused.value.extra["conflicts"] == ["src/app.py"]
    assert _git(root, "rev-parse", "HEAD") == head
    assert (root / "src" / "app.py").read_text() == "def greet():\n    return 'hey'\n"
    assert _git(root, "status", "--porcelain", "--untracked-files=no") == ""
