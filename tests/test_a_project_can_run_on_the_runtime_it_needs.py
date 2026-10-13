"""A project that needs another runtime version gets it, for its own commands only.

The image carries one version of each toolchain; Angular 22 needed Node 22.22
or later, and a Go module can ask for a newer Go than the image's. Commands run
inside the harness's own container, where no image per project can be built,
so `use_runtime` downloads the runtime from its official distribution, checks
it against the published checksum, unpacks it into a shared cache and puts it
first on the PATH of that project's commands - and, in container mode, picks
the image of that version.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tarfile
from pathlib import Path

import pytest

from app.tools import runtimes, sandbox
from app.tools.runtimes import RuntimeUnavailable, use

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _archive(top: str, executable: str, compression: str = "xz") -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode=f"w:{compression}") as tar:
        script = b"#!/bin/sh\necho provisioned\n"
        info = tarfile.TarInfo(f"{top}/bin/{executable}")
        info.size, info.mode = len(script), 0o755
        tar.addfile(info, io.BytesIO(script))
    return buffer.getvalue()


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("SANDBOX_TOOLCHAIN_DIR", str(tmp_path / "toolchains"))
    monkeypatch.setattr(runtimes.platform, "machine", lambda: "x86_64")
    return tmp_path / "toolchains"


def _node_registry(archive: bytes, digest: str | None = None, seen: list | None = None):
    name = "node-v22.23.3-linux-x64.tar.xz"
    pages = {
        "https://nodejs.org/dist/index.json": json.dumps([{"version": "v24.20.0"}, {"version": "v22.23.3"}]).encode(),
        "https://nodejs.org/dist/v22.23.3/SHASUMS256.txt":
            f"{digest or hashlib.sha256(archive).hexdigest()}  {name}\n".encode(),
        f"https://nodejs.org/dist/v22.23.3/{name}": archive,
    }

    def fetch(url):
        if seen is not None:
            seen.append(url)
        return pages[url]

    return fetch


def test_a_major_version_gets_its_newest_release_on_the_project_s_path(cache, tmp_path):
    workspace = tmp_path / "run"
    archive = _archive("node-v22.23.3-linux-x64", "node")

    assert use(workspace, "Node.js", "22", fetch=_node_registry(archive)) == {"runtime": "node", "version": "22.23.3"}

    first = runtimes.path_for(workspace, "/usr/bin").split(os.pathsep)[0]
    assert Path(first, "node").is_file() and first.startswith(str(cache))
    assert runtimes.path_for(tmp_path / "another-run", "/usr/bin") == "/usr/bin"


def test_a_runtime_downloaded_once_serves_every_later_run(cache, tmp_path):
    seen: list[str] = []
    fetch = _node_registry(_archive("node-v22.23.3-linux-x64", "node"), seen=seen)

    use(tmp_path / "one", "node", "22", fetch=fetch)
    use(tmp_path / "two", "node", "22.23", fetch=fetch)

    assert sum(url.endswith(".tar.xz") for url in seen) == 1


def test_an_archive_that_does_not_match_its_checksum_is_never_used(cache, tmp_path):
    fetch = _node_registry(_archive("node-v22.23.3-linux-x64", "node"), digest="0" * 64)

    with pytest.raises(RuntimeUnavailable, match="checksum"):
        use(tmp_path / "run", "node", "22", fetch=fetch)
    assert runtimes.recorded(tmp_path / "run") == {}


def test_an_archive_that_would_write_outside_its_directory_is_refused(cache, tmp_path):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:xz") as tar:
        info = tarfile.TarInfo("../../escaped")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    archive = buffer.getvalue()

    with pytest.raises(tarfile.OutsideDestinationError):
        use(tmp_path / "run", "node", "22", fetch=_node_registry(archive))
    assert not (cache.parent / "escaped").exists()


@pytest.mark.parametrize("runtime, version, said", [
    ("cobol", "85", "not a runtime this harness provides"),
    ("node", "latest; rm -rf /", "is not a version"),
    ("java", "21.0.2", "major version only"),
])
def test_what_cannot_be_provided_says_why(cache, tmp_path, runtime, version, said):
    with pytest.raises(RuntimeUnavailable, match=said):
        use(tmp_path / "run", runtime, version, fetch=lambda url: b"[]")


def test_a_host_that_is_not_a_runtime_distribution_is_never_fetched():
    with pytest.raises(RuntimeUnavailable, match="not a runtime distribution"):
        runtimes._fetch("https://example.com/node.tar.xz")


def test_go_and_java_are_read_from_their_own_distributions(cache, tmp_path):
    go_archive = _archive("go", "go", "gz")
    jdk_archive = _archive("jdk-25.0.4+1", "java", "gz")
    pages = {
        "https://go.dev/dl/?mode=json&include=all": json.dumps([{
            "version": "go1.27.2", "stable": True, "files": [{
                "filename": "go1.27.2.linux-amd64.tar.gz", "os": "linux", "arch": "amd64",
                "kind": "archive", "sha256": hashlib.sha256(go_archive).hexdigest(),
            }],
        }]).encode(),
        "https://go.dev/dl/go1.27.2.linux-amd64.tar.gz": go_archive,
        "https://api.adoptium.net/v3/assets/latest/25/hotspot?architecture=x64&image_type=jdk&os=linux&vendor=eclipse":
            json.dumps([{"release_name": "jdk-25.0.4+1", "binary": {"package": {
                "link": "https://github.com/adoptium/jdk.tar.gz",
                "checksum": hashlib.sha256(jdk_archive).hexdigest(),
            }}}]).encode(),
        "https://github.com/adoptium/jdk.tar.gz": jdk_archive,
    }

    assert use(tmp_path / "run", "golang", "1.27", fetch=pages.__getitem__)["version"] == "1.27.2"
    assert use(tmp_path / "run", "jdk", "25", fetch=pages.__getitem__)["version"] == "25.0.4+1"
    assert set(runtimes.recorded(tmp_path / "run")) == {"go", "java"}


def test_the_project_s_commands_run_on_it(cache, tmp_path):
    workspace = tmp_path / "run"
    workspace.mkdir()
    use(workspace, "node", "22", fetch=_node_registry(_archive("node-v22.23.3-linux-x64", "node")))

    environment = sandbox._child_environment(str(workspace), None)
    found = sandbox.SandboxExecutor._resolve_executable("node", str(workspace))

    assert environment["PATH"].split(os.pathsep)[0].startswith(str(cache))
    assert found is not None and found.startswith(str(cache))


def test_in_container_mode_the_image_is_the_pinned_version(cache, tmp_path):
    workspace = tmp_path / "run"
    use(workspace, "node", "22", fetch=_node_registry(_archive("node-v22.23.3-linux-x64", "node")))

    assert sandbox._image_for("npm", workspace) == "node:22.23.3-slim"
    assert sandbox._image_for("python3", workspace) == os.environ.get("SANDBOX_PYTHON_IMAGE", "python:3.12-slim")
    assert sandbox._image_for("npm") == os.environ.get("SANDBOX_NODE_IMAGE", "node:24-slim")


def test_specialists_are_given_it_and_its_description_names_no_product(tmp_path):
    from app.agents.specialists import create_specialist_agent
    from app.models import CompatibleChatOpenAI

    model = CompatibleChatOpenAI(model="Qwen3.5-9B-GGUF", api_key="unused", base_url="http://localhost:9/v1")
    agent = create_specialist_agent("testing", model=model, repo_root=tmp_path)

    assert "use_runtime" in agent.nodes["tools"].bound._tools_by_name
    assert not BANNED.search(runtimes.build_runtime_tool(str(tmp_path)).description)


def test_it_can_be_switched_off(monkeypatch, tmp_path):
    monkeypatch.setenv("SANDBOX_RUNTIMES_ENABLED", "false")

    assert runtimes.runtime_tools(str(tmp_path)) == []


def test_the_cache_outlives_a_redeploy_beside_the_workspaces(monkeypatch):
    monkeypatch.delenv("SANDBOX_TOOLCHAIN_DIR", raising=False)
    monkeypatch.setenv("WORKFLOW_WORKSPACE_ROOT", "/app/data/workspaces")

    assert runtimes.toolchain_dir() == Path("/app/data/toolchains")
