"""A stage's build and test commands see the dependencies its manifest names.

Measured on a Rust run: drafting wrote `Cargo.toml` with `rusqlite` in it, and the unit-testing work order that came
next ran every `cargo build`, `check` and `test` before the harness's first measurement - the only point a changed
manifest was installed. Each command ran without a network, as every command but an install does, and failed "Could not
resolve host: index.crates.io" or, with `--offline`, "no matching package named `rusqlite` found"; the stage spent nine
minutes on retries and never saw a compile result. Across the stored runs the same signature answered 142 commands
(Rust 68, C# 60 as NU1301, JavaScript 9, Python 6, Go 1; 20 runs).
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from unittest import mock

import pytest

from app.stacks import contract, pack_named
from app.stacks.installed_before_a_command import why_it_could_not_reach_a_registry
from app.tools import sandbox

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

CARGO_TOML = '[package]\nname = "notes_api"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\naxum = "0.8"\n'

#: What cargo printed for the stage's `cargo test` without a network (captured from the run).
CARGO_UNREACHABLE = (
    "    Updating crates.io index\n"
    "warning: spurious network error (3 tries remaining): [6] Could not resolve hostname (Could not resolve host: "
    "index.crates.io)\n"
    "error: failed to get `axum` as a dependency of package `notes_api v0.1.0 (/workspace/notes-api)`\n\n"
    "Caused by:\n  download of config.json failed\n\nCaused by:\n  failed to download from "
    "`https://index.crates.io/config.json`\n"
)
#: And for `cargo check --offline`.
CARGO_OFFLINE = (
    "error: no matching package named `rusqlite` found\nlocation searched: crates.io index\n"
    "required by package `notes_api v0.1.0 (/workspace/notes-api)`\n"
    "As a reminder, you're using offline mode (--offline) which can sometimes cause surprising resolution failures, "
    "if this error is too confusing you may wish to retry without the offline flag.\n"
)


class _Docker:
    """The docker CLI as the sandbox drives it: each `docker run` recorded with its network, answered per program."""

    def __init__(self, answers: dict[str, tuple[int, str]] | None = None) -> None:
        self.runs: list[tuple[str, list[str]]] = []
        self.answers = answers or {}

    def __call__(self, cmd, **_kwargs):
        if cmd[1:2] != ["run"]:
            return mock.Mock(stdout="", stderr="", returncode=0)
        network = cmd[cmd.index("--network") + 1]
        # `-u <uid:gid>`, then `--env K=V` pairs, then the image, then the command.
        at = cmd.index("-u") + 2
        while cmd[at] in ("--env", "-e"):
            at += 2
        argv = cmd[at + 1:]
        self.runs.append((network, argv))
        code, stderr = self.answers.get(" ".join(argv[:2]), (0, ""))
        return mock.Mock(stdout="", stderr=stderr, returncode=code)


def _a_rust_service(root: Path) -> None:
    contract.write(root, pack_named("rust-axum-api"), "notes-api", "Notes")
    (root / "notes-api").mkdir()
    (root / "notes-api" / "Cargo.toml").write_text(CARGO_TOML)
    contract.installed(root)  # as the scaffold left it


def _a_stage_runs(monkeypatch, root: Path, docker: _Docker, command: list[str]) -> dict:
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    monkeypatch.setattr("subprocess.run", docker)
    monkeypatch.setattr(sandbox, "validate_command", lambda argv, *_a, **_k: [str(part) for part in argv])
    environment = {"ALLOW_COMMAND_EXECUTION": "true", "SANDBOX_EXECUTION_MODE": "container",
                   "PACKAGE_LOOKUP_ENABLED": "false"}
    with mock.patch.dict(os.environ, environment):
        return sandbox.SandboxExecutor.execute(command, repo_root=str(root), role_name="testing_specialist",
                                               working_directory="notes-api")


def _drafting_adds_a_crate(root: Path) -> None:
    (root / "notes-api" / "Cargo.toml").write_text(CARGO_TOML + 'rusqlite = { version = "0.40", features = ["bundled"] }\n')


def test_a_crate_drafting_added_is_installed_with_the_network_before_the_stage_s_build(monkeypatch, tmp_path):
    _a_rust_service(tmp_path)
    _drafting_adds_a_crate(tmp_path)
    docker = _Docker()

    result = _a_stage_runs(monkeypatch, tmp_path, docker, ["cargo", "test", "--lib"])

    assert docker.runs == [
        ("bridge", ["cargo", "build", "--all-targets"]),
        ("bridge", ["npm", "install", "--no-audit", "--no-fund"]),
        ("none", ["cargo", "test", "--lib"]),
    ]
    assert "installed the project's dependencies with the network" in result["note"]
    assert "`cargo build --all-targets`" in result["note"]
    assert not BANNED.search(result["note"])


def test_an_unchanged_manifest_installs_nothing_before_a_stage_s_command(monkeypatch, tmp_path):
    _a_rust_service(tmp_path)
    docker = _Docker()

    result = _a_stage_runs(monkeypatch, tmp_path, docker, ["cargo", "check"])

    assert docker.runs == [("none", ["cargo", "check"])]
    assert "Before this command" not in result.get("note", "")


def test_a_command_that_runs_none_of_the_project_s_programs_installs_nothing(monkeypatch, tmp_path):
    _a_rust_service(tmp_path)
    _drafting_adds_a_crate(tmp_path)
    docker = _Docker()

    _a_stage_runs(monkeypatch, tmp_path, docker, ["ls", "-la", "target"])

    assert docker.runs == [("none", ["ls", "-la", "target"])]


def test_an_install_that_failed_is_said_to_the_command_that_could_not_reach_the_registry_and_is_not_tried_again(
        monkeypatch, tmp_path):
    _a_rust_service(tmp_path)
    _drafting_adds_a_crate(tmp_path)
    docker = _Docker({
        "cargo build": (101, "error: failed to select a version for the requirement `rusqlite = \"^0.40\"`\n"),
        "cargo test": (101, CARGO_UNREACHABLE),
    })

    first = _a_stage_runs(monkeypatch, tmp_path, docker, ["cargo", "test", "--lib"])
    second = _a_stage_runs(monkeypatch, tmp_path, docker, ["cargo", "test", "--no-run"])

    installs = [argv for network, argv in docker.runs if network == "bridge"]
    assert installs == [["cargo", "build", "--all-targets"]]
    for result in (first, second):
        assert "failed to select a version for the requirement `rusqlite" in result["note"]
        assert result["note"].count("This command had no network") == 1
        assert "no network" in result["note"]
        assert "cannot change that" in result["note"]
        assert not BANNED.search(result["note"])


@pytest.mark.parametrize("command", [["cargo", "update"], ["cargo", "generate-lockfile"], ["go", "mod", "tidy"]])
def test_a_command_that_resolves_the_manifest_against_the_registry_is_given_the_network(monkeypatch, tmp_path, command):
    """Measured on stored runs: 11 `cargo update` and `cargo generate-lockfile` commands and one `go mod tidy` ran
    without a network and could not reach their registry."""
    _a_rust_service(tmp_path)
    docker = _Docker()

    _a_stage_runs(monkeypatch, tmp_path, docker, command)

    assert docker.runs == [("bridge", command)]


def test_an_install_sent_as_a_build_is_given_the_network(monkeypatch, tmp_path):
    """Measured on a stored run: `npm install` sent with the build category ran without a network and failed reaching
    the npm registry."""
    docker = _Docker()
    monkeypatch.setattr(sandbox, "validate_command", lambda argv, *_a, **_k: [str(part) for part in argv])
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    monkeypatch.setattr("subprocess.run", docker)
    with mock.patch.dict(os.environ, {"ALLOW_COMMAND_EXECUTION": "true", "SANDBOX_EXECUTION_MODE": "container",
                                      "PACKAGE_LOOKUP_ENABLED": "false"}):
        sandbox.SandboxExecutor.execute(["npm", "install"], repo_root=str(tmp_path), category="build")

    assert docker.runs == [("bridge", ["npm", "install"])]


#: Real outputs of stage commands that had no network, from stored runs, one per package manager.
_UNREACHABLE = {
    "cargo": CARGO_UNREACHABLE,
    "cargo offline": CARGO_OFFLINE,
    "dotnet": ("/workspace/notes-api/src/App/App.csproj : error NU1301: Unable to load the service index for source "
               "https://api.nuget.org/v3/index.json.\n  Failed to restore /workspace/notes-api/src/App/App.csproj\n"),
    "npm": ("npm error code EAI_AGAIN\nnpm error syscall getaddrinfo\nnpm error request to "
            "https://registry.npmjs.org/@prisma%2fadapter-libsql failed, reason: getaddrinfo EAI_AGAIN registry.npmjs.org\n"),
    "go": ('go: downloading modernc.org/sqlite v1.62.0\ngo: notes_api imports\n\tmodernc.org/sqlite: '
           'Get "https://proxy.golang.org/modernc.org/sqlite/@v/v1.62.0.zip": dial tcp: lookup proxy.golang.org on '
           '192.168.65.7:53: dial udp 192.168.65.7:53: connect: network is unreachable\n'),
    "pip": ("WARNING: Retrying (Retry(total=4)) after connection broken by 'NewConnectionError('<HTTPSConnection>: Failed "
            "to establish a new connection: [Errno -3] Temporary failure in name resolution')': /simple/bcrypt/\n"),
}


@pytest.mark.parametrize("manager", sorted(_UNREACHABLE))
def test_a_command_without_a_network_that_could_not_reach_a_registry_is_told_why(tmp_path, manager):
    said = why_it_could_not_reach_a_registry(
        tmp_path, {"stdout": "", "stderr": _UNREACHABLE[manager], "returncode": "1", "network": "none"})

    assert "no network" in said
    assert "cannot change that" in said
    assert not BANNED.search(said)


def test_the_note_names_the_harness_s_install_once_the_manifest_is_installed(tmp_path):
    _a_rust_service(tmp_path)

    said = why_it_could_not_reach_a_registry(
        tmp_path, {"stdout": "", "stderr": CARGO_OFFLINE, "returncode": "101", "network": "none"})

    assert "`cargo build --all-targets`" in said
    assert "name it in the manifest" in said


@pytest.mark.parametrize("outcome", [
    {"stderr": CARGO_UNREACHABLE, "returncode": "101", "network": "bridge"},
    {"stderr": CARGO_UNREACHABLE, "returncode": "0", "network": "none"},
    {"stderr": "error[E0425]: cannot find value `conn` in this scope\n", "returncode": "101", "network": "none"},
], ids=["it had a network", "it succeeded", "a compile error"])
def test_a_command_that_had_a_network_succeeded_or_failed_otherwise_gets_no_such_note(tmp_path, outcome):
    assert why_it_could_not_reach_a_registry(tmp_path, outcome) == ""


def test_the_sandbox_s_note_survives_a_cd_taken_as_the_working_directory(monkeypatch, tmp_path):
    """Measured on the same run: the stage sent `cd notes-api && cargo ...`, and the note saying the `cd` was taken as
    the working directory replaced whatever note the sandbox's answer carried."""
    from app.tools.agent_toolkit import build_terminal_command_tool

    (tmp_path / "notes-api").mkdir()
    monkeypatch.setattr(sandbox.SandboxExecutor, "execute", staticmethod(
        lambda **_kw: {"returncode": "101", "network": "none", "note": "This command had no network, by design."}))

    result = build_terminal_command_tool(str(tmp_path), "testing").func(
        command=["cd", "notes-api", "&&", "cargo", "check"])

    assert "This command had no network, by design." in result["note"]
    assert "working_directory" in result["note"]
