"""In container mode a command's container gets the environment an in-container command gets, as it sees it.

It got `HOME=/tmp` and nothing else, and its /tmp is a 256 MB tmpfs that may not hold anything executed: `go test`
builds its test binaries in TMPDIR, cargo, NuGet, Maven and npm keep their caches under HOME, and a suite that starts
the product reads ACCEPTANCE_PORT. Now HOME and TMPDIR are on the mounted workspace, the toolchain settings, the
concurrency budget and a port are passed, a worker path is moved under the mount or left out, the project's
virtualenv goes in front of the image's own PATH, and a runtime pin a pack's image does not carry is said to be
unused. The default in-container mode is as it was.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from app.stacks import contract
from app.stacks.packs import ALL_PACKS
from app.tools import sandbox

BANNED = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")


def _pack(name: str):
    return next(pack for pack in ALL_PACKS if pack.name == name)


class _Result:
    stdout, stderr, returncode = "", "", 0


def _run_in_its_container(monkeypatch, workspace: Path, command=("ls",), during=None, **kwargs) -> tuple[list[str], dict]:
    """The docker argv a command would run with, and its result - nothing is executed; `during` sees the argv then."""
    captured: dict = {}

    def run(cmd, **_kwargs):
        captured["cmd"] = cmd
        if during:
            during(cmd)
        return _Result()

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    monkeypatch.setattr("subprocess.run", run)
    # Which programs a role may run is not what these tests are about.
    monkeypatch.setattr(sandbox, "validate_command", lambda argv, *_a, **_k: [str(part) for part in argv])
    with mock.patch.dict(os.environ, {"ALLOW_COMMAND_EXECUTION": "true", "SANDBOX_EXECUTION_MODE": "container"}):
        result = sandbox.SandboxExecutor.execute(list(command), repo_root=str(workspace), role_name="general", **kwargs)
    assert "cmd" in captured, result
    return captured["cmd"], result


def _environment_of(docker_cmd: list[str]) -> dict[str, str]:
    pairs = [docker_cmd[i + 1] for i, part in enumerate(docker_cmd) if part in ("--env", "-e")]
    return dict(pair.split("=", 1) for pair in pairs)


def _after_the_image(docker_cmd: list[str], image: str) -> list[str]:
    return docker_cmd[docker_cmd.index(image) + 1:]


def test_home_and_the_temporary_directory_are_on_the_mounted_workspace(monkeypatch, tmp_path):
    docker_cmd, _ = _run_in_its_container(monkeypatch, tmp_path)
    environment = _environment_of(docker_cmd)

    assert environment["HOME"] == "/workspace/.agent-home"
    assert environment["TMPDIR"].startswith("/workspace/.agent-home/")
    # Not the container's noexec tmpfs.
    assert not environment["TMPDIR"].startswith("/tmp")
    assert (tmp_path / os.path.relpath(environment["TMPDIR"], "/workspace")).is_dir()
    # Short enough for a Unix socket under it.
    assert len(environment["TMPDIR"]) < 40


def test_the_toolchain_settings_the_budget_and_a_port_are_passed(monkeypatch, tmp_path):
    environment = _environment_of(_run_in_its_container(monkeypatch, tmp_path)[0])

    for key, value in sandbox.TOOLCHAIN_ENVIRONMENT.items():
        assert environment[key] == value
    for key in ("NODE_OPTIONS", "GOMAXPROCS", "GOMEMLIMIT", "CARGO_BUILD_JOBS"):
        assert environment.get(key), key
    assert environment["ACCEPTANCE_PORT"].isdigit()


def test_no_worker_path_reaches_the_container(monkeypatch, tmp_path):
    with mock.patch.dict(os.environ, {"PATH": "/opt/worker-only/bin:/usr/bin", "LANG": "C.UTF-8",
                                      "HTTP_PROXY": "http://worker-proxy:3128"}):
        environment = _environment_of(_run_in_its_container(monkeypatch, tmp_path)[0])

    # The image's PATH is the one that knows where its toolchain is.
    assert "PATH" not in environment
    assert environment["LANG"] == "C.UTF-8"
    assert "HTTP_PROXY" not in environment
    worker_only = (str(tmp_path), tempfile.gettempdir() + "/", os.path.expanduser("~"))
    for key, value in environment.items():
        assert not any(value.startswith(path) or f":{path}" in value for path in worker_only), (key, value)


def test_a_caller_s_values_are_moved_into_the_container_or_left_out(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    elsewhere = tmp_path / "worker"
    fresh_home = elsewhere / "start-home"
    fresh_home.mkdir(parents=True)
    a_file = elsewhere / "secret.txt"
    a_file.write_text("x")
    existed = []

    def during(cmd):
        existed.append((workspace / os.path.relpath(_environment_of(cmd)["HOME"], "/workspace")).is_dir())

    docker_cmd, _ = _run_in_its_container(monkeypatch, workspace, during=during, extra_env={
        "IN_THE_WORKSPACE": str(workspace / "product" / "data"),
        "HOME": str(fresh_home),
        "A_FILE": str(a_file),
        "HOST": "127.0.0.1",
        "PATH": "/usr/local/bin:/usr/bin",
        "IN_THE_IMAGE": "/nowhere-on-the-worker/bin",
    })
    environment = _environment_of(docker_cmd)

    assert environment["IN_THE_WORKSPACE"] == "/workspace/product/data"
    assert environment["HOST"] == "127.0.0.1"
    assert environment["IN_THE_IMAGE"] == "/nowhere-on-the-worker/bin"
    assert "A_FILE" not in environment
    assert "PATH" not in environment
    # An empty directory made for the command - a stranger's home - is an empty one of its own in the workspace,
    # removed once the command has ended.
    assert environment["HOME"].startswith("/workspace/.agent-home/tmp/stand-in-")
    assert existed == [True]
    assert not (workspace / os.path.relpath(environment["HOME"], "/workspace")).exists()
    # The caller's own directory is left as it was.
    assert fresh_home.is_dir()


def test_a_unit_run_s_fresh_data_directory_is_seen_under_the_mount_and_removed(monkeypatch, tmp_path):
    contract.write(tmp_path, _pack("node-http-api"), "product", "Product")
    (tmp_path / "product").mkdir(exist_ok=True)
    seen: dict = {}

    def during(cmd):
        value = _environment_of(cmd)["DATA_DIR"]
        seen["value"] = value
        seen["existed"] = (tmp_path / os.path.relpath(value, "/workspace")).is_dir()

    _run_in_its_container(monkeypatch, tmp_path, command=("npm", "test"), during=during, working_directory="product")

    assert seen["value"].startswith("/workspace/product/test-results/unit-data-")
    assert seen["existed"]
    assert not (tmp_path / os.path.relpath(seen["value"], "/workspace")).exists()


def test_the_project_s_virtualenv_goes_in_front_of_the_image_s_path(monkeypatch, tmp_path):
    pack = _pack("python-http-api")
    contract.write(tmp_path, pack, "product", "Product")
    bin_dir = tmp_path / "product" / ".venv" / "bin"
    bin_dir.mkdir(parents=True)
    # Made in the image, linked to the image's interpreter: a path the worker does not have.
    (bin_dir / "python").symlink_to("/usr/bin/no-such-python-on-the-worker")

    docker_cmd, _ = _run_in_its_container(monkeypatch, tmp_path, command=("pytest", "-q"),
                                          working_directory="product")
    started = _after_the_image(docker_cmd, pack.sandbox_image)

    assert started[:3] == ["/bin/sh", "-c", 'PATH="$1:$PATH"; export PATH; shift; exec "$@"']
    assert started[3:] == ["sh", "/workspace/product/.venv/bin", "pytest", "-q"]


def test_without_a_virtualenv_the_command_starts_as_it_is(monkeypatch, tmp_path):
    pack = _pack("rust-axum-api")
    contract.write(tmp_path, pack, "product", "Product")
    docker_cmd, _ = _run_in_its_container(monkeypatch, tmp_path)
    assert _after_the_image(docker_cmd, pack.sandbox_image) == ["ls"]


def _pin(workspace: Path, runtime: str, version: str) -> None:
    runtime_bin = workspace.parent / f"toolchains-{runtime}" / "bin"
    runtime_bin.mkdir(parents=True)
    pins = workspace / ".harness" / "runtimes.json"
    pins.parent.mkdir(parents=True, exist_ok=True)
    pins.write_text(json.dumps({runtime: {"version": version, "bin": str(runtime_bin)}}), encoding="utf-8")


def test_a_pin_the_pack_s_image_does_not_carry_is_said_to_be_unused(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    pack = _pack("node-http-api")
    contract.write(workspace, pack, "product", "Product")
    _pin(workspace, "node", "22.22.0")

    docker_cmd, result = _run_in_its_container(monkeypatch, workspace)

    said = result["runtime_not_used"]
    assert "node 22.22.0" in said and pack.sandbox_image in said and "not used" in said
    # Never on the PATH or anywhere else in the environment: the runtime cache is the worker's.
    assert not any("toolchains-node" in part for part in docker_cmd)
    assert not any(str(tmp_path) in value for value in _environment_of(docker_cmd).values())
    words = set(said.lower().replace("`", " ").replace(",", " ").replace(".", " ").split())
    assert not words & set(BANNED)


def test_without_a_pack_s_image_the_pin_chooses_the_image_and_nothing_is_said(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _pin(workspace, "node", "22.22.0")

    docker_cmd, result = _run_in_its_container(monkeypatch, workspace, command=("node", "--version"))

    assert "node:22.22.0-slim" in docker_cmd
    assert "runtime_not_used" not in result


def test_the_default_in_container_mode_is_as_it_was(monkeypatch, tmp_path):
    pack = _pack("python-http-api")
    contract.write(tmp_path, pack, "product", "Product")
    bin_dir = tmp_path / "product" / ".venv" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "python").symlink_to("/usr/bin/no-such-python-on-the-worker")
    captured: dict = {}

    class _Done:
        stdout, stderr, returncode = "", "", 0

    def watch(argv, *, cwd, env, **_kwargs):
        captured.update(argv=argv, cwd=cwd, env=env)
        return _Done()

    def no_container(*_args, **_kwargs):
        raise AssertionError("in-container mode built a container's environment")

    monkeypatch.setattr(sandbox, "_run_and_watch_the_tree", watch)
    monkeypatch.setattr(sandbox, "_container_environment", no_container, raising=False)
    with mock.patch.dict(os.environ, {"ALLOW_COMMAND_EXECUTION": "true", "SANDBOX_EXECUTION_MODE": "in-container"}):
        result = sandbox.SandboxExecutor.execute(["ls"], repo_root=str(tmp_path), role_name="general")

    environment = captured["env"]
    assert environment["HOME"] == str(tmp_path / ".agent-home")
    assert environment["TMPDIR"] == sandbox._short_temporary_directory(str(tmp_path))
    assert environment["PATH"]
    # A dangling interpreter is no virtualenv here, as before.
    assert str(bin_dir) not in environment["PATH"]
    assert not any(value.startswith("/workspace") for value in environment.values())
    assert captured["argv"][0].endswith("/ls")
    assert "runtime_not_used" not in result


@pytest.mark.parametrize("follow_links", [True, False])
def test_a_virtualenv_with_a_working_interpreter_is_found_either_way(tmp_path, follow_links):
    contract.write(tmp_path, _pack("python-http-api"), "product", "Product")
    bin_dir = tmp_path / "product" / ".venv" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "python").write_text("")
    assert sandbox._the_project_virtualenv(str(tmp_path), follow_links=follow_links) == str(bin_dir)
