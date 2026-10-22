"""An install's network reaches the package registries and GitHub, nothing else (plan SF.1).

The `install` category is the only one with a network, and nothing limited where
it went: a wheel URL, an `--index-url` mirror, a `.npmrc` registry or a tarball
dependency in `package.json` fetched and ran code from any host. Every host an
install names is checked before it runs, as seeding checks a clone.
"""
from __future__ import annotations

import os
from unittest import mock

from app.tools.install_egress import refusal


def test_an_install_by_name_or_from_a_registry_or_github_runs(tmp_path):
    for command in (["npm", "install", "express"], ["pip", "install", "fastapi"],
                    ["pip", "install", "git+https://github.com/owner/repo.git"],
                    ["npm", "install", "--registry=https://registry.npmjs.org/"],
                    ["python", "-m", "pip", "install", "-i", "https://pypi.org/simple", "httpx"]):
        assert refusal(command, tmp_path, {}) == "", command


def test_a_host_on_the_command_line_that_is_no_registry_is_refused(tmp_path):
    for command in (["pip", "install", "https://files.example.net/pkg-1.0-py3-none-any.whl"],
                    ["pip", "install", "--index-url", "https://mirror.example.net/simple", "requests"],
                    ["npm", "install", "--registry", "https://npm.example.net"],
                    ["pip", "install", "--trusted-host", "mirror.example.net", "x"],
                    ["npm", "install", "git@code.example.net:o/r.git"]):
        why = refusal(command, tmp_path, {})
        assert "example.net" in why and "INSTALL_ALLOWED_HOSTS" in why, command


def test_a_host_in_the_files_the_install_reads_is_refused(tmp_path):
    (tmp_path / "package.json").write_text('{"dependencies": {"left-pad": "https://cdn.example.net/lp.tgz", "ok": "^1.0.0"}}')
    assert "cdn.example.net (in package.json)" in refusal(["npm", "install"], tmp_path, {})

    (tmp_path / "package.json").write_text('{"dependencies": {"ok": "^1.0.0"}}')
    (tmp_path / ".npmrc").write_text("registry=https://npm.example.net/\n")
    assert "(in .npmrc)" in refusal(["npm", "ci"], tmp_path, {})

    (tmp_path / ".npmrc").unlink()
    (tmp_path / "requirements.txt").write_text("# from https://docs.example.net\nrequests==2.32.3\n")
    assert refusal(["pip", "install", "-r", "requirements.txt"], tmp_path, {}) == ""
    (tmp_path / "requirements.txt").write_text("--extra-index-url https://pkgs.example.net/simple\nrequests\n")
    assert "(in requirements.txt)" in refusal(["pip", "install", "-r", "requirements.txt"], tmp_path, {})


def test_the_operator_widens_the_list_or_lifts_it(tmp_path):
    command = ["pip", "install", "--index-url", "https://mirror.example.net/simple", "x"]
    assert refusal(command, tmp_path, {"INSTALL_ALLOWED_HOSTS": "example.net"}) == ""
    assert refusal(command, tmp_path, {"INSTALL_ALLOWED_HOSTS": "*"}) == ""


def test_the_sandbox_refuses_it_before_anything_runs(tmp_path):
    from app.tools.sandbox import SandboxExecutor

    env = {"ALLOW_COMMAND_EXECUTION": "true", "SANDBOX_EXECUTION_MODE": "in-container", "INSTALL_ALLOWED_HOSTS": ""}
    with mock.patch.dict(os.environ, env):
        result = SandboxExecutor.execute(
            ["pip", "install", "https://files.example.invalid/pkg-1.0-py3-none-any.whl"],
            repo_root=str(tmp_path), role_name="backend_specialist", category="install",
        )

    assert "returncode" not in result and "Not installing" in str(result.get("error")), result
