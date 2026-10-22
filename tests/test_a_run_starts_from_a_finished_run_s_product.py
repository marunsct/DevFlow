"""A run starts from a completed run's product, with a change brief (plan BW.2).

Behind `CHANGE_REQUEST_RUNS`, off until measured. The product and its history
are copied; the old run's harness records and what installs make are not;
the new run is held to the product's own green tests by BW.1's contract.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from app.server import runs
from app.server.models import WorkspaceSource
from app.server.seeding import SeedError, seed_workspace

ON = {"CHANGE_REQUEST_RUNS": "on"}


def _finished(tmp_path: Path) -> Path:
    done = tmp_path / "done"
    (done / "app" / "node_modules" / "dep").mkdir(parents=True)
    (done / "app" / "node_modules" / "dep" / "index.js").write_text("x")
    (done / "app" / "main.py").write_text("print('hi')\n")
    (done / ".harness").mkdir()
    (done / ".harness" / "suite.json").write_text("{}")
    subprocess.run(["git", "-C", str(done), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(done), "-c", "user.email=h@example.com", "-c", "user.name=h", "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(done), "-c", "user.email=h@example.com", "-c", "user.name=h", "commit", "-qm", "v1"], check=True)
    return done


def test_on_the_product_and_its_history_are_copied_and_the_records_left_behind(tmp_path):
    done, new = _finished(tmp_path), tmp_path / "new"
    new.mkdir()
    source = WorkspaceSource(type="run", run_id="run-1")
    with mock.patch.dict(os.environ, ON):
        result = seed_workspace(new, source, resolve_upload=lambda _: None, resolve_run={"run-1": done}.get)

    assert result.seeded and result.provenance["type"] == "run" and result.provenance["run_id"] == "run-1"
    assert len(result.provenance["commit"]) == 40
    assert (new / "app" / "main.py").read_text() == "print('hi')\n" and (new / ".git").is_dir()
    assert not (new / "app" / "node_modules").exists() and not (new / ".harness" / "suite.json").exists()
    assert json.loads((new / ".harness" / "seeded.json").read_text())["provenance"]["type"] == "run"


def test_off_or_unknown_the_run_is_refused(tmp_path):
    done, new = _finished(tmp_path), tmp_path / "new"
    new.mkdir()
    source = WorkspaceSource(type="run", run_id="run-1")
    with mock.patch.dict(os.environ, {"CHANGE_REQUEST_RUNS": ""}), pytest.raises(SeedError, match="switched off"):
        seed_workspace(new, source, resolve_upload=lambda _: None, resolve_run={"run-1": done}.get)
    with mock.patch.dict(os.environ, ON), pytest.raises(SeedError, match="not completed"):
        seed_workspace(new, source, resolve_upload=lambda _: None, resolve_run=lambda _: None)


def test_only_a_completed_run_of_the_caller_s_tenant_is_found(tmp_path):
    records = {
        "mine": SimpleNamespace(status="completed", repo_root=str(tmp_path), tenant_id="t1"),
        "live": SimpleNamespace(status="running", repo_root=str(tmp_path), tenant_id="t1"),
        "theirs": SimpleNamespace(status="completed", repo_root=str(tmp_path), tenant_id="t2"),
    }
    runner = SimpleNamespace(run_store=SimpleNamespace(load=records.get))
    user = SimpleNamespace(role="operator", tenant_id="t1")

    assert runs._a_completed_run_s_workspace(runner, "mine", user) == tmp_path
    assert runs._a_completed_run_s_workspace(runner, "live", user) is None
    assert runs._a_completed_run_s_workspace(runner, "theirs", user) is None
    assert runs._a_completed_run_s_workspace(runner, "gone", user) is None


def test_the_copy_keeps_a_product_s_own_target_dir_drops_links_out_and_cleans_a_failed_copy(tmp_path):
    """`ignore_patterns` applied the top-level set at every depth, a nested link out of the workspace was
    copied, and a failed copy left a workspace every retry tripped over."""
    from app.server import change_request_runs

    finished = tmp_path / "finished"
    (finished / "shop" / "src" / "target").mkdir(parents=True)
    (finished / "shop" / "src" / "target" / "x.py").write_text("x = 1\n")
    (finished / "shop" / "node_modules").mkdir()
    (finished / "shop" / "package.json").write_text("{}")
    (finished / "shop" / "node_modules" / "m.js").write_text("")
    (finished / "shop" / "src" / "out").symlink_to("/etc/hostname")
    subprocess.run(["git", "-C", str(finished), "init", "-q"], check=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with mock.patch.dict(os.environ, {"CHANGE_REQUEST_RUNS": "on"}):
        change_request_runs.seed_from_run(workspace, finished, "run-x")
    assert (workspace / "shop" / "src" / "target" / "x.py").is_file(), "a product's own target/ is the product's"
    assert not (workspace / "shop" / "node_modules").exists() and not (workspace / "shop" / "src" / "out").exists()

    unreadable = finished / "shop" / "src" / "secret.py"
    unreadable.write_text("x\n")
    unreadable.chmod(0)
    again = tmp_path / "again"
    again.mkdir()
    try:
        with mock.patch.dict(os.environ, {"CHANGE_REQUEST_RUNS": "on"}), pytest.raises(SeedError):
            change_request_runs.seed_from_run(again, finished, "run-x")
        assert not (again / "shop").exists(), "nothing half-copied is left behind"
    finally:
        unreadable.chmod(0o644)
