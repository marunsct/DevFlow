"""A runtime version a project needs and the image does not have.

The image carries one version of each toolchain. A project can need another:
Angular 22 needed Node 22.22 or later, a Go module can ask for a newer Go
than the image's (and `GOTOOLCHAIN=local` makes that an error rather than a
250 MB download into the workspace), a framework can need a newer JDK. Cloud
coding agents answer this with a container image per project; this harness
runs its commands inside its own container, where no image can be built, so a
project instead gets the runtime itself: downloaded once from the runtime's
own distribution, checked against the checksum published beside it, unpacked
into a cache every run shares, and put first on the PATH of that project's
commands only (`sandbox._child_environment`). In container mode the image is
chosen by the same pin (`sandbox._image_for`).

The hosts are fixed per runtime, a version must look like one, and an archive
is unpacked with the standard library's data filter, which refuses members
that would land outside the directory.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

#: Where the workspace records the runtimes its commands use.
RUNTIMES_FILE = ".harness/runtimes.json"
#: Seconds a download may take.
DOWNLOAD_TIMEOUT = float(os.environ.get("SANDBOX_RUNTIME_DOWNLOAD_TIMEOUT", "600"))
#: The largest archive accepted.
MAX_ARCHIVE_BYTES = 600 * 1024**2
#: A version as a person asks for one: "22", "22.22", "1.27.2", "3.13".
_A_VERSION = re.compile(r"^\d{1,4}(?:\.\d{1,4}){0,2}$")
#: The only hosts an archive is fetched from. The Temurin API links to GitHub
#: releases, which redirect to GitHub's object store.
_HOSTS = frozenset({
    "nodejs.org", "go.dev", "dl.google.com", "api.adoptium.net", "github.com",
    "objects.githubusercontent.com", "release-assets.githubusercontent.com",
})

#: Fetches a URL as bytes. Injected so tests need no network.
Fetch = Callable[[str], bytes]

_LOCK = threading.Lock()


class RuntimeUnavailable(RuntimeError):
    """The runtime cannot be provided; the message says why and what to do."""


def toolchain_dir() -> Path:
    """The cache every run's provisioned runtimes share."""
    configured = os.environ.get("SANDBOX_TOOLCHAIN_DIR", "").strip()
    if configured:
        return Path(configured)
    # Beside the workspaces, on the volume that outlives a redeploy: a runtime
    # downloaded once serves every later run.
    workspaces = os.environ.get("WORKFLOW_WORKSPACE_ROOT", "").strip()
    if workspaces:
        return Path(workspaces).parent / "toolchains"
    return Path.home() / ".cache" / "harness-toolchains"


def _fetch(url: str) -> bytes:
    import httpx

    if urlparse(url).hostname not in _HOSTS:
        raise RuntimeUnavailable(f"{url} is not a runtime distribution this harness downloads from.")
    body = bytearray()
    with httpx.Client(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
        with client.stream("GET", url) as response:
            if response.status_code != 200:
                raise RuntimeUnavailable(f"{url} answered {response.status_code}.")
            if urlparse(str(response.url)).hostname not in _HOSTS:
                raise RuntimeUnavailable(f"{url} redirected to {response.url}, which is not trusted.")
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > MAX_ARCHIVE_BYTES:
                    raise RuntimeUnavailable(f"{url} is larger than any runtime archive should be.")
    return bytes(body)


def _arch(names: dict[str, str]) -> str:
    machine = platform.machine().lower()
    for key, value in names.items():
        if machine in key.split("|"):
            return value
    raise RuntimeUnavailable(f"No runtime archive is known for this machine ({machine}).")


def _matches(version: str, wanted: str) -> bool:
    return version == wanted or version.startswith(wanted + ".")


# --- one resolver per runtime: wanted version -> (exact version, url, sha256) ---

def _node(wanted: str, fetch: Fetch) -> tuple[str, str, str]:
    arch = _arch({"x86_64|amd64": "x64", "aarch64|arm64": "arm64"})
    for release in json.loads(fetch("https://nodejs.org/dist/index.json")):
        version = str(release.get("version", "")).lstrip("v")
        if _matches(version, wanted):
            name = f"node-v{version}-linux-{arch}.tar.xz"
            sums = fetch(f"https://nodejs.org/dist/v{version}/SHASUMS256.txt").decode()
            digest = next((line.split()[0] for line in sums.splitlines() if line.endswith(" " + name)), "")
            return version, f"https://nodejs.org/dist/v{version}/{name}", digest
    raise RuntimeUnavailable(f"Node.js has no release {wanted}.")


def _go(wanted: str, fetch: Fetch) -> tuple[str, str, str]:
    arch = _arch({"x86_64|amd64": "amd64", "aarch64|arm64": "arm64"})
    for release in json.loads(fetch("https://go.dev/dl/?mode=json&include=all")):
        version = str(release.get("version", "")).removeprefix("go")
        if release.get("stable") and _matches(version, wanted):
            for file in release.get("files") or []:
                if file.get("os") == "linux" and file.get("arch") == arch and file.get("kind") == "archive":
                    return version, f"https://go.dev/dl/{file['filename']}", str(file.get("sha256") or "")
    raise RuntimeUnavailable(f"Go has no stable release {wanted}.")


def _java(wanted: str, fetch: Fetch) -> tuple[str, str, str]:
    if "." in wanted:
        raise RuntimeUnavailable("A JDK is chosen by its major version only, e.g. 25.")
    arch = _arch({"x86_64|amd64": "x64", "aarch64|arm64": "aarch64"})
    found = json.loads(fetch(
        f"https://api.adoptium.net/v3/assets/latest/{wanted}/hotspot"
        f"?architecture={arch}&image_type=jdk&os=linux&vendor=eclipse"
    ))
    if not found:
        raise RuntimeUnavailable(f"Eclipse Temurin has no JDK {wanted}.")
    package = found[0]["binary"]["package"]
    version = str(found[0].get("release_name") or wanted).removeprefix("jdk-")
    return version, str(package["link"]), str(package.get("checksum") or "")


_RESOLVERS: dict[str, Callable[[str, Fetch], tuple[str, str, str]]] = {
    "node": _node, "go": _go, "java": _java,
}
#: Runtimes `uv` provides, and the executables each puts on the PATH.
_EXECUTABLES = {
    "node": ("node", "npm", "npx"),
    "go": ("go", "gofmt"),
    "java": ("java", "javac", "jar"),
    "python": ("python", "python3"),
}
#: What each runtime is called in a request.
_ALIASES = {
    "node": "node", "nodejs": "node", "node.js": "node",
    "go": "go", "golang": "go",
    "java": "java", "jdk": "java", "temurin": "java",
    "python": "python", "python3": "python",
}
SUPPORTED = tuple(_EXECUTABLES)


def _unpack(archive: bytes, url: str, into: Path) -> None:
    import io

    mode = "r:xz" if url.endswith(".xz") else "r:gz"
    with tarfile.open(fileobj=io.BytesIO(archive), mode=mode) as tar:
        tar.extractall(into, filter="data")


def _bin_dir(root: Path, executable: str) -> Path:
    for candidate in sorted(root.glob(f"**/bin/{executable}"), key=lambda path: len(path.parts)):
        if os.access(candidate, os.X_OK):
            return candidate.parent
    raise RuntimeUnavailable(f"The archive held no `bin/{executable}`.")


def _download(runtime: str, wanted: str, fetch: Fetch) -> tuple[str, Path]:
    version, url, digest = _RESOLVERS[runtime](wanted, fetch)
    home = toolchain_dir() / f"{runtime}-{version}"
    if (home / ".complete").is_file():
        return version, _bin_dir(home, _EXECUTABLES[runtime][0])
    if not digest:
        raise RuntimeUnavailable(f"No checksum is published for {url}; it is not used unchecked.")
    archive = fetch(url)
    if hashlib.sha256(archive).hexdigest() != digest.lower():
        raise RuntimeUnavailable(f"{url} did not match its published checksum.")
    toolchain_dir().mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{runtime}-", dir=toolchain_dir()))
    try:
        _unpack(archive, url, staging)
        (staging / ".complete").write_text(version, encoding="utf-8")
        shutil.rmtree(home, ignore_errors=True)
        staging.rename(home)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return version, _bin_dir(home, _EXECUTABLES[runtime][0])


def _python(wanted: str) -> tuple[str, Path]:
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeUnavailable("Python versions are provided through `uv`, which this image lacks.")
    where = toolchain_dir() / "python"
    environment = {"PATH": os.environ.get("PATH", ""), "HOME": str(toolchain_dir()),
                   "UV_PYTHON_INSTALL_DIR": str(where)}
    done = subprocess.run(
        [uv, "python", "install", wanted], capture_output=True, text=True, timeout=DOWNLOAD_TIMEOUT,
        env=environment, check=False,
    )
    if done.returncode != 0:
        raise RuntimeUnavailable(f"`uv python install {wanted}` failed: {(done.stderr or done.stdout)[-400:]}")
    found = subprocess.run(
        [uv, "python", "find", "--managed-python", wanted], capture_output=True, text=True, timeout=60,
        env=environment, check=False,
    )
    executable = Path((found.stdout or "").strip())
    if found.returncode != 0 or not executable.is_file():
        raise RuntimeUnavailable(f"Python {wanted} was installed but could not be found.")
    exact = re.search(r"\d+\.\d+\.\d+", executable.parent.parent.name)
    return (exact.group(0) if exact else wanted), executable.parent


def recorded(workspace: str | Path | None) -> dict[str, dict[str, str]]:
    """The runtimes this workspace's commands use, by name."""
    if not workspace:
        return {}
    try:
        data = json.loads((Path(workspace) / RUNTIMES_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {
        name: entry for name, entry in (data.items() if isinstance(data, dict) else ())
        if isinstance(entry, dict) and Path(str(entry.get("bin", ""))).is_dir()
    }


def path_for(workspace: str | Path | None, path: str) -> str:
    """`path` with this workspace's runtimes in front of it."""
    first = [entry["bin"] for entry in recorded(workspace).values()]
    return os.pathsep.join([*first, path]) if first else path


def use(workspace: str | Path, runtime: str, wanted: str, *, fetch: Fetch | None = None) -> dict[str, str]:
    """Provide `runtime` at `wanted` for this workspace's commands, and record it."""
    name = _ALIASES.get(str(runtime or "").strip().lower())
    if name is None:
        raise RuntimeUnavailable(
            f"{runtime!r} is not a runtime this harness provides; it provides {', '.join(SUPPORTED)}."
        )
    wanted = str(wanted or "").strip().lstrip("v")
    if not _A_VERSION.match(wanted):
        raise RuntimeUnavailable(f"{wanted!r} is not a version: give one like 22, 22.22 or 1.27.2.")
    with _LOCK:
        version, bin_dir = _python(wanted) if name == "python" else _download(name, wanted, fetch or _fetch)
        path = Path(workspace) / RUNTIMES_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data[name] = {"version": version, "bin": str(bin_dir)}
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    logger.info("Workspace %s now runs %s %s", workspace, name, version)
    return {"runtime": name, "version": version}


def image_tag(workspace: str | Path | None, executable: str) -> str | None:
    """The container image for `executable` at the version this workspace pinned, or None."""
    pins = recorded(workspace)
    for name, executables in _EXECUTABLES.items():
        if executable in executables and name in pins:
            version = pins[name]["version"]
            major = version.split(".")[0].split("+")[0]
            return {
                "node": f"node:{version}-slim",
                "go": f"golang:{version}",
                "java": f"eclipse-temurin:{major}-jdk",
                "python": f"python:{'.'.join(re.findall(r'\d+', version)[:2])}-slim",
            }[name]
    return None


def build_runtime_tool(repo_root: str) -> Any:
    from langchain_core.tools import tool

    @tool
    # `language`, not `runtime`: LangGraph's tool node takes a parameter named
    # `runtime` for its own injected runtime, so every call failed with an empty
    # error (measured live: 4 of 4 in one fix stage).
    def use_runtime(language: str, version: str) -> dict[str, Any]:
        """Run this project's commands on another version of a runtime.

        The environment has one version of each runtime. When a package needs
        another - its registry entry says so (see `look_up_package`), or an
        install refuses with an engine or version error - ask for that version
        here. It is downloaded from the runtime's official distribution,
        checked, and from then on every command of this project runs on it.

        Args:
            language: node, go, java or python.
            version: the version needed: a major version (22), or a more exact
                one (22.22, 1.27.2).
        """
        try:
            return use(repo_root, language, version)
        except RuntimeUnavailable as exc:
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - a failed download is an answer, not a crash
            logger.warning("Could not provide %s %s", language, version, exc_info=True)
            return {"error": f"{language} {version} could not be provided ({type(exc).__name__}): {exc}"}

    return use_runtime


def enabled() -> bool:
    return os.environ.get("SANDBOX_RUNTIMES_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}


def runtime_tools(repo_root: str) -> list[Any]:
    return [build_runtime_tool(repo_root)] if enabled() else []
