"""The official MCP servers of the libraries a product builds on, found in the MCP Registry.

Owner, 2026-10-20: where a model's training data is older than a library, the
stages should reach what the library's own team publishes for it. Many publish
an MCP server for their documentation - Svelte's answers at mcp.svelte.dev -
and list it in the official MCP Registry (registry.modelcontextprotocol.io).

Official means the server's verified namespace is the library's own. The
registry checks a reverse-DNS namespace (`dev.svelte/mcp`) against its domain
and an `io.github.<owner>` one against the GitHub account; the library's own
registry entry names its homepage and repository (`package_registry`'s
`homes`). A server published under anyone else's name - a third party's
`svelte-llm` - is not the library's, whatever it is called. Every ecosystem the
harness reads a manifest of is searched alike (`app.analysis.manifests`).

Only a remote server is attached: nothing is installed or run here. A package
server (`npx @sveltejs/mcp`) would run third-party code inside the worker,
outside the sandbox and beside the run's secrets, so it is left to the owner's
own configuration (`HARNESS_MCP_SERVERS`).

The registry can take many seconds to answer, so no stage waits for it: what is
found is kept in the workspace (`FOUND_FILE`), the search for what is not yet
known runs in the background, and a stage built later is given what it found.
Off when `HARNESS_MCP_DISCOVERY` is false.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlparse

logger = logging.getLogger(__name__)

#: Where what was found is kept, per workspace.
FOUND_FILE = ".harness/mcp-official.json"
#: Libraries searched for, at most, per product: the ones its manifests list first.
MOST_LIBRARIES = 24
TIMEOUT_SECONDS = float(os.environ.get("MCP_REGISTRY_TIMEOUT", "12"))
#: Hosts whose path names the account a repository belongs to.
_CODE_HOSTS = frozenset({"github.com", "gitlab.com", "codeberg.org", "bitbucket.org"})
#: Hosts anyone may have a subdomain of: a library homed at `foo.readthedocs.io`
#: is not readthedocs's, so on these only the exact name counts.
_SHARED_HOSTS = frozenset({
    "github.io", "gitlab.io", "readthedocs.io", "rtfd.io", "vercel.app", "netlify.app", "pages.dev",
    "herokuapp.com", "web.app", "firebaseapp.com", "azurewebsites.net", "blogspot.com", "wordpress.com",
})
#: Transports a remote server may be reached by, as the registry names them.
_REMOTE = {"streamable-http": "streamable_http", "sse": "sse"}

_LOCK = threading.Lock()
_SEARCHING: set[str] = set()

Fetch = Callable[[str], tuple[int, str]]


def enabled() -> bool:
    return os.environ.get("HARNESS_MCP_DISCOVERY", "true").strip().lower() not in {"0", "false", "no", "off"}


def _registry() -> str:
    return os.environ.get("MCP_REGISTRY_URL", "https://registry.modelcontextprotocol.io").rstrip("/")


def _identities(homes: list[str]) -> set[str]:
    """Who a library's homes say it belongs to: domains, and `host:account` for a code host."""
    found: set[str] = set()
    for url in homes:
        parsed = urlparse(str(url))
        host = (parsed.hostname or "").lower()
        if not host:
            continue
        account = parsed.path.strip("/").split("/", 1)[0].lower()
        if host in _CODE_HOSTS:
            if account:
                found.add(f"{host}:{account}")
        elif host.endswith(".github.io"):
            found.add("github.com:" + host.split(".", 1)[0])
        else:
            found.add(host.removeprefix("www."))
    return found


def _namespace_of(server_name: str) -> str:
    """Who a registry server's verified namespace names: a domain, or `github.com:account`."""
    namespace = str(server_name or "").split("/", 1)[0].lower()
    if namespace.startswith("io.github."):
        return "github.com:" + namespace[len("io.github."):]
    return ".".join(reversed(namespace.split(".")))


def is_official(server_name: str, homes: list[str]) -> bool:
    """Whether the server's verified namespace is the library's own."""
    namespace = _namespace_of(server_name)
    if not namespace or namespace.count(".") + namespace.count(":") < 1:
        return False
    for identity in _identities(homes):
        if ":" in identity or ":" in namespace:
            if identity == namespace:
                return True
        elif identity == namespace or (identity.endswith("." + namespace) and namespace not in _SHARED_HOSTS):
            return True
    return False


def _get(url: str) -> tuple[int, str]:
    import httpx

    with httpx.Client(timeout=TIMEOUT_SECONDS, headers={"User-Agent": "software-harness-mcp-discovery"}) as client:
        response = client.get(url)
        return response.status_code, response.text


def servers_for(ecosystem: str, name: str, *, fetch: Fetch | None = None,
                homes: list[str] | None = None) -> list[dict[str, Any]]:
    """The library's official remote servers, as `mcp_tools` entries; [] when it has none or none was found."""
    from app.tools.package_registry import look_up

    fetch = fetch or _get
    if homes is None:
        homes = list(look_up(ecosystem, name).get("homes") or [])
    if not homes:
        return []
    word = name.rsplit("/", 1)[-1].split(":")[-1]
    status, body = fetch(f"{_registry()}/v0/servers?search={quote(word)}&version=latest&limit=30")
    if status != 200:
        return []
    found: list[dict[str, Any]] = []
    for item in (json.loads(body or "{}").get("servers") or []):
        server = item.get("server") or item
        meta = (item.get("_meta") or {}).get("io.modelcontextprotocol.registry/official") or {}
        if str(meta.get("status") or "active") != "active" or not is_official(str(server.get("name") or ""), homes):
            continue
        remote = next((r for r in server.get("remotes") or [] if str(r.get("type")) in _REMOTE and r.get("url")), None)
        if remote is None or not str(remote["url"]).startswith("https://"):
            continue
        found.append({
            "server": str(server["name"]),
            "transport": _REMOTE[str(remote["type"])],
            "url": str(remote["url"]),
            "tools": "*",
            "library": name,
            "official": True,
        })
    return found


def _read(root: Path) -> dict[str, list[dict[str, Any]]]:
    try:
        data = json.loads((root / FOUND_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(root: Path, found: dict[str, list[dict[str, Any]]]) -> None:
    path = root / FOUND_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(found, indent=2, sort_keys=True), encoding="utf-8")


def _libraries(root: Path) -> list[tuple[str, str]]:
    from app.analysis.manifests import in_the_project

    seen: list[tuple[str, str]] = []
    for _, ecosystem, package, _ in in_the_project(root):
        if (ecosystem, package) not in seen:
            seen.append((ecosystem, package))
    return seen[:MOST_LIBRARIES]


def _search(root: Path, libraries: list[tuple[str, str]], fetch: Fetch | None) -> None:
    for ecosystem, name in libraries:
        try:
            servers = servers_for(ecosystem, name, fetch=fetch)
        except Exception as exc:  # noqa: BLE001 - a library not answered is tried again later
            logger.info("The MCP Registry search for %s failed: %s", name, exc)
            continue
        with _LOCK:
            found = _read(root)
            found[f"{ecosystem}:{name}"] = servers
            _write(root, found)
        if servers:
            logger.info("Official MCP server for %s: %s", name, ", ".join(s["server"] for s in servers))


def official_servers(repo_root: str | Path | None, *, fetch: Fetch | None = None,
                     wait: bool = False) -> dict[str, dict[str, Any]]:
    """The official servers found so far for the product's libraries, by name; starts a search for the rest.

    `wait` searches in the caller's thread instead, for tests and the loop.
    """
    if not repo_root or not enabled():
        return {}
    root = Path(repo_root)
    try:
        libraries = _libraries(root)
        found = _read(root)
        missing = [lib for lib in libraries if f"{lib[0]}:{lib[1]}" not in found]
        key = str(root.resolve())
        if missing:
            if wait:
                _search(root, missing, fetch)
                found = _read(root)
            else:
                with _LOCK:
                    start = key not in _SEARCHING
                    _SEARCHING.add(key)
                if start:
                    def run() -> None:
                        try:
                            _search(root, missing, fetch)
                        finally:
                            with _LOCK:
                                _SEARCHING.discard(key)

                    threading.Thread(target=run, name="mcp-registry-search", daemon=True).start()
        servers: dict[str, dict[str, Any]] = {}
        for ecosystem, name in libraries:
            for entry in found.get(f"{ecosystem}:{name}") or []:
                servers.setdefault(re.sub(r"[^A-Za-z0-9]+", "_", entry["server"]).strip("_").lower(), entry)
        return servers
    except Exception:  # noqa: BLE001 - a stage without them is a stage as it was
        logger.debug("Could not read the official MCP servers", exc_info=True)
        return {}


__all__ = ["FOUND_FILE", "enabled", "is_official", "official_servers", "servers_for"]
