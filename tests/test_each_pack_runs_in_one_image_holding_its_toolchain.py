"""In container mode a pack's every command runs in one image holding its toolchain, runners, Node and browsers (LR.30).

Chosen by executable alone, the suite of a service in Rust, Go, Java, C#, PHP or
Ruby ran under Playwright in the Playwright image, and the `start.sh` its web
server runs found no `cargo`, `dotnet`, `mvn`, `php` or `ruby` there; `cargo
nextest` was in no image, and Java, .NET, PHP and Ruby commands fell to an image
with no toolchain. The default in-container mode never asks for an image.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from unittest import mock

import pytest

from app.stacks import contract
from app.stacks.packs import ALL_PACKS, _sandbox
from app.stacks.packs import _javascript as js
from app.stacks.packs import _python
from app.stacks.packs import csharp_aspnet_api, go_http_api, java_spring_api, php_slim_api, ruby_sinatra_api
from app.tools import sandbox

ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "scripts" / "loop" / "build_sandbox_images.sh"
#: What the Playwright image itself provides.
IN_THE_PLAYWRIGHT_IMAGE = {"npm", "npx", "node"}


def _dockerfile(image: str) -> Path:
    match = re.fullmatch(re.escape(_sandbox.IMAGE_PREFIX) + r"([a-z0-9-]+):pw" + re.escape(js.PLAYWRIGHT), image)
    assert match, f"{image} is not an image the build script tags"
    return ROOT / _sandbox.DOCKERFILES / match.group(1) / "Dockerfile"


@pytest.mark.parametrize("pack", ALL_PACKS, ids=lambda pack: pack.name)
def test_every_pack_names_an_image_that_exists_or_is_built_here(pack):
    assert pack.sandbox_image, f"{pack.name} names no sandbox image"
    if pack.sandbox_image == _sandbox.PLAYWRIGHT_IMAGE:
        return
    dockerfile = _dockerfile(pack.sandbox_image)
    assert dockerfile.is_file(), f"{pack.name}: {dockerfile} is missing"
    text = dockerfile.read_text(encoding="utf-8")
    # Built on the Playwright release the packs pin, so Node and the browsers match the suite's runner.
    assert "FROM mcr.microsoft.com/playwright:v${PLAYWRIGHT_VERSION}-noble" in text
    assert f"ARG PLAYWRIGHT_VERSION={js.PLAYWRIGHT}" in text


@pytest.mark.parametrize("pack", ALL_PACKS, ids=lambda pack: pack.name)
def test_every_command_a_pack_runs_finds_its_program_in_the_pack_s_image(pack):
    """A runner the pack starts - its installer, its unit runner, its acceptance runner - is in its image."""
    commands = (*pack.install, pack.unit_test, pack.acceptance_test)
    needed = set()
    for argv in commands:
        program = argv[0]
        if "/" in program:  # the project's own (`.venv/bin/python`, `vendor/bin/phpunit`), made by its install
            continue
        needed.add(program)
        if program == "cargo" and len(argv) > 1 and argv[1] == "nextest":
            needed.add("nextest")
    beyond_node = needed - IN_THE_PLAYWRIGHT_IMAGE
    if pack.sandbox_image == _sandbox.PLAYWRIGHT_IMAGE:
        assert not beyond_node, f"{pack.name} runs {sorted(beyond_node)}, which the Playwright image does not have"
        return
    text = _dockerfile(pack.sandbox_image).read_text(encoding="utf-8")
    words = {"python3": "python3", "mvn": "maven", "bundle": "bundle", "composer": "composer"}
    for program in sorted(beyond_node):
        assert words.get(program, program) in text, f"{pack.name}: nothing in its image installs {program}"


def test_the_images_carry_the_versions_the_packs_declare():
    def arg(toolchain: str, name: str) -> str:
        text = (ROOT / _sandbox.DOCKERFILES / toolchain / "Dockerfile").read_text(encoding="utf-8")
        return re.search(rf"^ARG {name}=(\S+)$", text, re.M).group(1)

    assert arg("go", "GO_VERSION").startswith(go_http_api.GO_VERSION + ".")
    assert arg("java", "JAVA_VERSION") == java_spring_api.JAVA_VERSION
    assert arg("dotnet", "DOTNET_CHANNEL") == csharp_aspnet_api.DOTNET
    assert arg("php", "PHP_VERSION") == php_slim_api.PHP_VERSION
    assert arg("ruby", "RUBY_VERSION").startswith(ruby_sinatra_api.RUBY_VERSION + ".")
    # Ubuntu 24.04, the Playwright image's base, ships Python 3.12.
    assert _python.PYTHON_VERSION == "3.12"


def test_the_build_script_tags_each_image_as_the_packs_name_it():
    text = BUILD_SCRIPT.read_text(encoding="utf-8")
    assert os.access(BUILD_SCRIPT, os.X_OK)
    assert 'tag="harness-sandbox-$toolchain:pw$playwright"' in text
    assert _sandbox.built_image("x") == f"harness-sandbox-x:pw{js.PLAYWRIGHT}"
    assert "src/app/stacks/packs/_javascript.py" in text and "deploy/sandbox-images/" in text


def _pack(name: str):
    return next(pack for pack in ALL_PACKS if pack.name == name)


@pytest.mark.parametrize("name", ["rust-axum-api", "csharp-aspnet-api", "java-spring-api", "ruby-rails-api"])
def test_a_workspace_on_a_pack_runs_every_command_in_the_pack_s_image(tmp_path, name):
    pack = _pack(name)
    contract.write(tmp_path, pack, "product", "Product")

    # The suite's runner and the product's own toolchain alike: the web server it starts runs beside it.
    for executable in ("npx", "npm", "cargo", "dotnet", "mvn", "bundle", "sh"):
        assert sandbox._image_for(executable, tmp_path) == pack.sandbox_image


def test_without_a_pack_the_image_is_still_chosen_by_executable(tmp_path):
    with mock.patch.dict(os.environ, {}, clear=False):
        for key in ("SANDBOX_NODE_IMAGE", "SANDBOX_PYTHON_IMAGE", "SANDBOX_RUST_IMAGE", "SANDBOX_BASE_IMAGE"):
            os.environ.pop(key, None)
        assert sandbox._image_for("npm", tmp_path) == "node:24-slim"
        assert sandbox._image_for("python3", tmp_path) == "python:3.12-slim"
        assert sandbox._image_for("cargo", tmp_path) == "rust:1-slim"
        assert sandbox._image_for("make", tmp_path) == "debian:12-slim"
        assert sandbox._image_for("npm") == "node:24-slim"


@pytest.mark.parametrize("executable, toolchain", [
    ("mvn", "java"), ("dotnet", "dotnet"), ("php", "php"), ("composer", "php"), ("bundle", "ruby"), ("ruby", "ruby"),
    ("go", "go"),
])
def test_without_a_pack_a_compiled_toolchain_s_command_runs_in_its_own_image(tmp_path, executable, toolchain):
    """Deep review 2026-11-18, item E3: with no pack, `mvn`, `dotnet`, `php` and `ruby` ran in a bare Debian with no
    toolchain, and `go` in Go 1.22 while the packs and the worker are on 1.26."""
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("SANDBOX_GO_IMAGE", None)
        assert sandbox._image_for(executable, tmp_path) == f"harness-sandbox-{toolchain}:pw{js.PLAYWRIGHT}"


def test_the_container_command_line_names_the_pack_s_image(monkeypatch, tmp_path):
    pack = _pack("rust-axum-api")
    contract.write(tmp_path, pack, "product", "Product")
    captured = {}

    class _Result:
        stdout, stderr, returncode = "", "", 0

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    monkeypatch.setattr("subprocess.run", lambda cmd, **_k: (captured.update(cmd=cmd), _Result())[1])
    with mock.patch.dict(os.environ, {"ALLOW_COMMAND_EXECUTION": "true", "SANDBOX_EXECUTION_MODE": "container"}):
        sandbox.SandboxExecutor.execute(["ls"], repo_root=str(tmp_path), role_name="general")

    command = captured["cmd"]
    assert command[command.index(pack.sandbox_image) + 1:] == ["ls"]


def test_the_default_in_container_mode_never_asks_for_an_image(monkeypatch, tmp_path):
    contract.write(tmp_path, _pack("rust-axum-api"), "product", "Product")

    def no_image(*_args, **_kwargs):
        raise AssertionError("in-container mode asked for an image")

    monkeypatch.setattr(sandbox, "_image_for", no_image)
    monkeypatch.setattr(sandbox.SandboxExecutor, "_execute_here", classmethod(lambda cls, *a, **k: {"ran": "here"}))
    with mock.patch.dict(os.environ, {"ALLOW_COMMAND_EXECUTION": "true", "SANDBOX_EXECUTION_MODE": "in-container"}):
        assert sandbox.SandboxExecutor.execute(["ls"], repo_root=str(tmp_path), role_name="general") == {"ran": "here"}
