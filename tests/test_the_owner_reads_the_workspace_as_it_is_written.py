"""The run page's Workspace tab: the product's files, read-only, as the stages write them (plan WS.1).

The owner asked to see the code while a run builds it. The tree must show what every stage's listing shows and
nothing else (no `.git`, no harness records, no installed or build folders, no credentials), a file is read only
inside the workspace, and each file's change is shown since the last accepted sprint - the scaffold before the first.
"""
from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _workspace(root, *, sprint_accepted=False):
    """A product's workspace: a scaffold commit, maybe an accepted sprint, then a stage's uncommitted work."""
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "h@example.com")
    _git(root, "config", "user.name", "harness")
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("print('scaffold')\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "Scaffold: a stack")
    if sprint_accepted:
        (root / "src" / "app.py").write_text("print('sprint one')\n")
        _git(root, "commit", "-qam", "Sprint 1")
        _git(root, "tag", "sprint-1")
    (root / "src" / "app.py").write_text("print('sprint one')\nprint('being written')\n")
    (root / "src" / "new.py").write_text("NEW = 1\n")
    (root / "README.md").write_text("# The product\n")
    # What the tree leaves out.
    (root / ".harness").mkdir()
    (root / ".harness" / "contract.json").write_text("{}")
    (root / ".agent-home").mkdir()
    (root / ".agent-home" / "history").write_text("x")
    (root / "node_modules" / "left-pad").mkdir(parents=True)
    (root / "node_modules" / "left-pad" / "index.js").write_text("module.exports = 1\n")
    (root / ".env").write_text("SECRET=1\n")
    return root


def _client(root, monkeypatch, tenant="t"):
    """The real runs router over one run in `root`; the signed-in user and the run store stood in for."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.server import runs
    from app.server.auth import get_current_active_user, require_operator

    run = SimpleNamespace(run_id="run-1", tenant_id="t", status="running", repo_root=str(root))
    runner = SimpleNamespace(run_store=SimpleNamespace(load=lambda run_id: run if run_id == "run-1" else None))
    monkeypatch.setattr(runs, "record_audit", lambda **kwargs: None)
    app = FastAPI()
    app.include_router(runs.create_runs_router(runner, SimpleNamespace(), str(root), str(root)))
    user = SimpleNamespace(username="owner", role="operator", tenant_id=tenant)
    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[require_operator] = lambda: user
    return TestClient(app)


def test_the_tree_shows_the_product_s_files_and_hides_the_harness_s_and_the_tools(tmp_path, monkeypatch):
    client = _client(_workspace(tmp_path), monkeypatch)

    shown = client.get("/api/runs/run-1/files").json()

    assert {f["path"]: f["size"] for f in shown["files"]} == {"README.md": 14, "src/app.py": 43, "src/new.py": 8}
    assert sorted(shown["changed"]) == ["README.md", "src/app.py", "src/new.py"]
    assert shown["since"] == "the scaffold"


def test_a_folder_a_tool_fills_beside_its_manifest_is_left_out_of_the_tree(tmp_path, monkeypatch):
    """Bundler's and Composer's `vendor/` is the tool's when the manifest sits beside it (LF.1148)."""
    (tmp_path / "Gemfile").write_text("source 'https://rubygems.org'\n")
    (tmp_path / "vendor" / "bundle").mkdir(parents=True)
    (tmp_path / "vendor" / "bundle" / "gem.rb").write_text("x")
    client = _client(tmp_path, monkeypatch)

    shown = client.get("/api/runs/run-1/files").json()

    assert [f["path"] for f in shown["files"]] == ["Gemfile"]
    assert shown["since"] is None and shown["changed"] == []


def test_one_file_s_text_is_read(tmp_path, monkeypatch):
    client = _client(_workspace(tmp_path), monkeypatch)

    shown = client.get("/api/runs/run-1/files/content", params={"path": "src/app.py"})

    assert shown.status_code == 200
    assert shown.json()["path"] == "src/app.py"
    assert shown.json()["content"] == "print('sprint one')\nprint('being written')\n"


@pytest.mark.parametrize("attack", ["/etc/passwd", "../../../../etc/passwd", "src/../../../../etc/hosts"])
def test_a_path_outside_the_workspace_is_refused(tmp_path, monkeypatch, attack):
    client = _client(_workspace(tmp_path), monkeypatch)

    for route in ("content", "diff"):
        refused = client.get(f"/api/runs/run-1/files/{route}", params={"path": attack})
        assert refused.status_code == 400
        assert "root:" not in refused.text


@pytest.mark.parametrize(
    "hidden", [".git/config", ".harness/contract.json", ".agent-home/history", "node_modules/left-pad/index.js", ".env"],
)
def test_a_file_the_tree_hides_is_not_read_by_name(tmp_path, monkeypatch, hidden):
    client = _client(_workspace(tmp_path), monkeypatch)

    for route in ("content", "diff"):
        assert client.get(f"/api/runs/run-1/files/{route}", params={"path": "src/app.py"}).status_code == 200
        assert client.get(f"/api/runs/run-1/files/{route}", params={"path": hidden}).status_code == 404
    assert client.get("/api/runs/run-1/files/content", params={"path": hidden, "at": "accepted"}).status_code == 404


def test_a_link_out_of_a_shown_folder_is_judged_by_where_it_leads(tmp_path, monkeypatch):
    root = _workspace(tmp_path)
    (root / "src" / "config").symlink_to(root / ".git" / "config")
    (root / "src" / "alias.py").symlink_to(root / "src" / "app.py")
    client = _client(root, monkeypatch)

    assert client.get("/api/runs/run-1/files/content", params={"path": "src/alias.py"}).json()["path"] == "src/app.py"
    assert client.get("/api/runs/run-1/files/content", params={"path": "src/config"}).status_code == 404


def test_a_binary_or_oversized_file_is_refused_for_reading(tmp_path, monkeypatch):
    root = _workspace(tmp_path)
    (root / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00")
    (root / "big.txt").write_text("a" * (600 * 1024))
    client = _client(root, monkeypatch)

    assert client.get("/api/runs/run-1/files/content", params={"path": "logo.png"}).status_code == 415
    assert client.get("/api/runs/run-1/files/content", params={"path": "big.txt"}).status_code == 415


def test_a_file_s_diff_is_since_the_last_accepted_sprint(tmp_path, monkeypatch):
    client = _client(_workspace(tmp_path, sprint_accepted=True), monkeypatch)

    shown = client.get("/api/runs/run-1/files/diff", params={"path": "src/app.py"}).json()

    assert shown["since"] == "sprint 1"
    assert "+print('being written')" in shown["diff"]
    assert "print('scaffold')" not in shown["diff"]
    assert shown["diff"].startswith("diff --git a/src/app.py b/src/app.py")


def test_before_any_sprint_a_file_s_diff_is_since_the_scaffold(tmp_path, monkeypatch):
    client = _client(_workspace(tmp_path), monkeypatch)

    shown = client.get("/api/runs/run-1/files/diff", params={"path": "src/app.py"}).json()

    assert shown["since"] == "the scaffold"
    assert "-print('scaffold')" in shown["diff"] and "+print('being written')" in shown["diff"]


def test_a_file_written_since_and_never_committed_shows_as_all_added(tmp_path, monkeypatch):
    client = _client(_workspace(tmp_path, sprint_accepted=True), monkeypatch)

    shown = client.get("/api/runs/run-1/files/diff", params={"path": "src/new.py"}).json()

    assert "--- /dev/null" in shown["diff"] and "+NEW = 1" in shown["diff"]


def test_an_unchanged_file_has_an_empty_diff(tmp_path, monkeypatch):
    root = _workspace(tmp_path, sprint_accepted=True)
    (root / "src" / "app.py").write_text("print('sprint one')\n")
    client = _client(root, monkeypatch)

    shown = client.get("/api/runs/run-1/files/diff", params={"path": "src/app.py"}).json()

    assert shown["diff"] == "" and shown["since"] == "sprint 1"


def test_a_run_in_another_tenant_shows_no_files(tmp_path, monkeypatch):
    """The same check as the artifact routes: another tenant's run is not found, not forbidden."""
    root = _workspace(tmp_path)
    assert _client(root, monkeypatch).get("/api/runs/run-1/files").status_code == 200
    client = _client(root, monkeypatch, tenant="someone-else")

    assert client.get("/api/runs/run-1/files").status_code == 404
    assert client.get("/api/runs/run-1/files/content", params={"path": "src/app.py"}).status_code == 404
    assert client.get("/api/runs/run-1/files/diff", params={"path": "src/app.py"}).status_code == 404


# -- the VS Code-style workspace (plan UX.7, UX.8): search across files, the hash and the base text --


def test_a_search_finds_text_in_a_listed_file_with_its_line(tmp_path, monkeypatch):
    client = _client(_workspace(tmp_path), monkeypatch)

    found = client.get("/api/runs/run-1/files/search", params={"q": "BEING written"})

    assert found.status_code == 200
    assert found.json()["hits"] == [{"path": "src/app.py", "line": 2, "column": 8, "text": "print('being written')"}]
    assert found.json()["truncated"] is False


def test_a_search_never_reaches_a_file_the_tree_hides(tmp_path, monkeypatch):
    """`.git`, the harness's records, installed folders, credential files and a link into `.git` are never searched."""
    root = _workspace(tmp_path)
    (root / ".harness" / "contract.json").write_text('{"zebra": 1}')
    (root / ".git" / "description").write_text("zebra\n")
    (root / "node_modules" / "left-pad" / "index.js").write_text("// zebra\n")
    (root / ".env").write_text("ZEBRA=1\n")
    (root / "src" / "config").symlink_to(root / ".git" / "description")
    (root / "src" / "zoo.py").write_text("ANIMAL = 'zebra'\n")
    client = _client(root, monkeypatch)

    found = client.get("/api/runs/run-1/files/search", params={"q": "zebra"}).json()

    assert [hit["path"] for hit in found["hits"]] == ["src/zoo.py"]


def test_a_search_stops_at_its_cap_and_says_so(tmp_path):
    from app.server.workspace_files import search

    root = _workspace(tmp_path)

    capped = search(root, "print", most_hits=1)  # two lines hold it
    out_of_time = search(root, "print", seconds=0)

    assert len(capped["hits"]) == 1 and capped["truncated"] is True
    assert out_of_time["hits"] == [] and out_of_time["timed_out"] is True


def test_a_search_of_a_run_in_another_tenant_is_not_found(tmp_path, monkeypatch):
    root = _workspace(tmp_path)
    assert _client(root, monkeypatch).get("/api/runs/run-1/files/search", params={"q": "print"}).status_code == 200
    client = _client(root, monkeypatch, tenant="someone-else")

    assert client.get("/api/runs/run-1/files/search", params={"q": "print"}).status_code == 404


def test_a_file_s_hash_changes_when_the_file_does(tmp_path, monkeypatch):
    root = _workspace(tmp_path)
    client = _client(root, monkeypatch)
    read = lambda: client.get("/api/runs/run-1/files/content", params={"path": "src/new.py"}).json()["hash"]
    first, again = read(), read()

    (root / "src" / "new.py").write_text("NEW = 2\n")

    assert first == again
    assert read() != first


def test_the_base_text_is_the_last_accepted_sprint_s(tmp_path, monkeypatch):
    client = _client(_workspace(tmp_path, sprint_accepted=True), monkeypatch)

    base = client.get("/api/runs/run-1/files/content", params={"path": "src/app.py", "at": "accepted"}).json()

    assert base["content"] == "print('sprint one')\n"
    assert base["since"] == "sprint 1" and base["exists"] is True


def test_before_any_sprint_the_base_text_is_the_scaffold_s_and_a_new_file_has_none(tmp_path, monkeypatch):
    client = _client(_workspace(tmp_path), monkeypatch)

    base = client.get("/api/runs/run-1/files/content", params={"path": "src/app.py", "at": "accepted"}).json()
    new = client.get("/api/runs/run-1/files/content", params={"path": "src/new.py", "at": "accepted"}).json()

    assert base["content"] == "print('scaffold')\n" and base["since"] == "the scaffold"
    assert new["content"] == "" and new["exists"] is False
