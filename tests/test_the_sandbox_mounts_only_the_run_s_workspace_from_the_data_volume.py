"""Container mode mounts only the run's workspace, as a sub-path of the data volume (LR.30).

Found in the launch review: the workspace lives in the worker's named data volume, a path the host's Docker does not
have, so container mode could not mount it and every command ran inside the worker, beside its secrets and data.
"""
from __future__ import annotations

from app.tools import sandbox

WS = "/app/data/workspaces/default/workspace-run-x"


def test_a_named_volume_is_mounted_by_its_sub_path(monkeypatch):
    monkeypatch.setenv("SANDBOX_WORKSPACE_VOLUME", "langchain_appdata")
    monkeypatch.setenv("DATA_DIR", "/app/data")
    assert sandbox._workspace_mount(WS) == [
        "--mount", "type=volume,src=langchain_appdata,dst=/workspace,volume-subpath=workspaces/default/workspace-run-x"]


def test_without_a_volume_or_outside_it_the_host_path_is_bound_as_before(monkeypatch):
    monkeypatch.delenv("SANDBOX_WORKSPACE_VOLUME", raising=False)
    assert sandbox._workspace_mount(WS) == ["-v", f"{WS}:/workspace"]
    monkeypatch.setenv("SANDBOX_WORKSPACE_VOLUME", "langchain_appdata")
    assert sandbox._workspace_mount("/elsewhere/ws") == ["-v", "/elsewhere/ws:/workspace"]


def test_the_shared_deployment_file_runs_commands_in_containers_through_a_limited_proxy():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    sandbox_file = (root / "docker-compose.sandbox.yml").read_text()
    assert "SANDBOX_EXECUTION_MODE: container" in sandbox_file and "DOCKER_HOST: tcp://docker-proxy:2375" in sandbox_file
    assert "SANDBOX_WORKSPACE_VOLUME:" in sandbox_file and "volumes: !override" in sandbox_file
    for refused in ("EXEC: 0", "BUILD: 0", "VOLUMES: 0", "SECRETS: 0"):
        assert refused in sandbox_file
    assert "docker-cli" in (root / "Dockerfile").read_text()
