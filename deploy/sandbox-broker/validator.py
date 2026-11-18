"""Which Docker API requests the sandbox broker passes on (deep review 2026-11-18, item E1b). Pure: no I/O.

The worker reached Docker through `tecnativa/docker-socket-proxy` with `CONTAINERS=1, POST=1`. That proxy filters by
endpoint, never by body, so a create with a bind mount of the host's root or `Privileged: true` passed, and the
worker - which runs model-written commands in in-container mode and reads model-written files in every mode - held
root on the host one request away. The broker passes on only the calls `docker run --rm` and `docker kill` make for
`app.tools.sandbox.SandboxExecutor._run`, and only a create shaped like the one that method builds:

    docker run --rm --name sandbox-<12 hex> --network none|bridge --memory Nm --memory-swap Nm --cpus C
      --pids-limit P --cap-drop ALL --security-opt no-new-privileges --read-only
      --tmpfs /tmp:rw,noexec,nosuid,size=256m
      --mount type=volume,src=<data volume>,dst=/workspace,volume-subpath=<the run's workspace>
      -w /workspace/... -u <uid>:<gid> --env K=V ... <image> <argv...>

What a create must and may carry, each a feature the sandbox uses:

- `Image`: starting with one of `allowed_image_prefixes` (the packs' `harness-sandbox-` images, the Playwright image,
  and the fallback images `sandbox._image_for` names when no pack does).
- `User`: set, and not root (`-u uid:gid`, the worker's own non-root user).
- `HostConfig.NetworkMode`: one of `allowed_networks` (`none`; `bridge` for installs and packs that fetch while
  building). `NetworkingConfig.EndpointsConfig` names no other network: one of the harness's own would reach its
  database and queue.
- `HostConfig.CapDrop` holds `ALL`; `CapAdd` is empty; `Privileged` is false.
- `HostConfig.SecurityOpt` is exactly `no-new-privileges` (in either spelling): no `seccomp=unconfined`,
  no `apparmor=unconfined`, no label changes.
- `HostConfig.ReadonlyRootfs` is true; `Tmpfs` mounts only `/tmp`.
- `HostConfig.Mounts`: exactly one, a `volume` mount of `workspace_volume` at `/workspace` with a relative
  `VolumeOptions.Subpath` and no driver options (a `local` driver's options can bind any host path). `Binds` is empty:
  the deployment runs with `SANDBOX_WORKSPACE_VOLUME` set, which is the volume mount, never a host path.
- `HostConfig.Memory`, `MemorySwap`, `NanoCpus` (or `CpuQuota`) and `PidsLimit` are all set above zero.
- `HostConfig.AutoRemove` (`--rm`), `LogConfig`, `RestartPolicy` `no`, and the CLI's zero-valued defaults.
- Every other `HostConfig` field is at its zero value: no devices, no host PID/IPC/UTS/user/cgroup namespace,
  no published ports, no sysctls, no runtime of its own, no `VolumesFrom`, no extra hosts.
- The `name` query parameter matches `container_name`.

The other calls: `GET/HEAD /_ping`, `GET /version`, `GET /info`; `attach`, `start`, `wait`, `kill`, `logs`,
`json` (inspect), `resize` and `DELETE` of a container the broker created or one whose name matches
`container_name`; `POST /images/create` and `GET /images/<name>/json` for an allowed image. Everything else is
refused.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable
from urllib.parse import parse_qs, unquote, urlsplit

#: The packs' images, then the fallback images `app.tools.sandbox._image_for` and a runtime pin
#: (`app.tools.runtimes.image_tag`) name.
DEFAULT_IMAGE_PREFIXES = (
    "harness-sandbox-", "mcr.microsoft.com/playwright:", "node:", "python:", "golang:", "rust:", "debian:",
    "eclipse-temurin:",
)


@dataclass(frozen=True)
class Policy:
    workspace_volume: str
    allowed_image_prefixes: tuple[str, ...] = DEFAULT_IMAGE_PREFIXES
    allowed_networks: tuple[str, ...] = ("none", "bridge")
    container_name: str = r"^sandbox-[0-9a-f]{12}$"
    #: Upper bounds, 0 for none: a create past them is refused.
    most_memory_bytes: int = 0
    most_nano_cpus: int = 0
    most_pids: int = 0
    #: Container ids the broker created, which later calls may name.
    created: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""
    #: For a create: the container name it asked for.
    name: str = ""


def allow(reason: str = "", name: str = "") -> Decision:
    return Decision(True, reason, name)


def refuse(reason: str) -> Decision:
    return Decision(False, reason)


# --- the create body -------------------------------------------------------------------------------------------

#: HostConfig fields that may be other than their zero value, each checked below.
_CHECKED = frozenset({
    "NetworkMode", "CapDrop", "CapAdd", "Privileged", "SecurityOpt", "ReadonlyRootfs", "Tmpfs", "Mounts", "Binds",
    "Memory", "MemorySwap", "NanoCpus", "CpuQuota", "CpuPeriod", "PidsLimit", "AutoRemove", "LogConfig",
    "RestartPolicy", "ConsoleSize", "CgroupnsMode", "IpcMode", "PidMode", "UTSMode", "UsernsMode", "Isolation",
    "OomScoreAdj", "ShmSize", "CpuShares", "MemorySwappiness", "Init",
})
#: Namespace settings: the container's own (empty or `private`), never the host's or another container's.
_NAMESPACES = ("CgroupnsMode", "IpcMode", "PidMode", "UTSMode", "UsernsMode")
_ROOT_USERS = frozenset({"", "0", "root", "0:0", "root:root", "root:0", "0:root"})


def _zero(value: Any) -> bool:
    """Whether a field is at the value the Docker CLI sends for an option nobody gave."""
    if value in (None, "", 0, False):
        return True
    if isinstance(value, (list, tuple)):
        return all(_zero(item) for item in value)
    if isinstance(value, dict):
        return all(_zero(item) for item in value.values())
    return False


def _positive(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _no_new_privileges(options: Iterable[Any]) -> bool:
    return [str(option).strip().lower() for option in options] in (
        ["no-new-privileges"], ["no-new-privileges:true"], ["no-new-privileges=true"])


def _the_workspace_mount(mounts: Any, policy: Policy) -> str:
    """Why the mounts are not the one workspace volume mount the sandbox makes; "" when they are."""
    if not isinstance(mounts, list) or len(mounts) != 1 or not isinstance(mounts[0], dict):
        return "exactly one mount, the run's workspace, is allowed"
    mount = mounts[0]
    if mount.get("Type") != "volume":
        return f"a mount of type {mount.get('Type')!r}: only a volume mount is allowed"
    if mount.get("Source") != policy.workspace_volume:
        return f"a mount of volume {mount.get('Source')!r}: only {policy.workspace_volume!r} is allowed"
    if mount.get("Target") != "/workspace":
        return f"a mount at {mount.get('Target')!r}: only /workspace is allowed"
    options = mount.get("VolumeOptions") or {}
    if not isinstance(options, dict):
        return "unreadable volume options"
    if not _zero(options.get("DriverConfig")) or not _zero(options.get("Labels")):
        return "volume driver options: a driver's options can bind any host path"
    subpath = str(options.get("Subpath") or "")
    parts = subpath.split("/")
    if not subpath or subpath.startswith("/") or ".." in parts or "" in parts:
        return f"a volume sub-path of {subpath!r}: a run's workspace, relative and inside the volume, is required"
    if not _zero(mount.get("BindOptions")) or not _zero(mount.get("TmpfsOptions")):
        return "bind or tmpfs options on the workspace mount"
    return ""


def create_problem(body: Any, policy: Policy) -> str:
    """Why this create body is not one the sandbox makes; "" when it is."""
    if not isinstance(body, dict):
        return "the body is not a JSON object"
    image = str(body.get("Image") or "")
    if not _image_allowed(image, policy):
        return f"image {image!r} is not a sandbox image"
    if str(body.get("User") or "").strip().lower() in _ROOT_USERS:
        return "the container would run as root: a non-root `User` is required"
    if not _zero(body.get("Entrypoint")):
        return "an entrypoint of its own"
    host = body.get("HostConfig")
    if not isinstance(host, dict):
        return "no HostConfig: the sandbox's limits are missing"
    if host.get("Privileged"):
        return "Privileged"
    if not _zero(host.get("CapAdd")):
        return f"CapAdd {host.get('CapAdd')!r}"
    if "ALL" not in [str(cap).upper() for cap in host.get("CapDrop") or []]:
        return "CapDrop does not hold ALL"
    if not _no_new_privileges(host.get("SecurityOpt") or []):
        return f"SecurityOpt {host.get('SecurityOpt')!r}: exactly no-new-privileges is required"
    if host.get("ReadonlyRootfs") is not True:
        return "the root filesystem is not read-only"
    tmpfs = host.get("Tmpfs") or {}
    if not isinstance(tmpfs, dict) or set(tmpfs) - {"/tmp"}:
        return f"tmpfs mounts {sorted(tmpfs) if isinstance(tmpfs, dict) else tmpfs!r}: only /tmp is allowed"
    if not _zero(host.get("Binds")):
        return f"Binds {host.get('Binds')!r}: no path of the host may be mounted"
    problem = _the_workspace_mount(host.get("Mounts"), policy)
    if problem:
        return problem
    network = str(host.get("NetworkMode") or "")
    if network not in policy.allowed_networks:
        return f"network mode {network!r}: only {', '.join(policy.allowed_networks)}"
    endpoints = ((body.get("NetworkingConfig") or {}).get("EndpointsConfig") or {})
    if not isinstance(endpoints, dict) or set(endpoints) - {network}:
        return f"networks {sorted(endpoints) if isinstance(endpoints, dict) else endpoints!r}: only {network!r}"
    for namespace in _NAMESPACES:
        if str(host.get(namespace) or "").lower() not in ("", "private"):
            return f"{namespace} {host.get(namespace)!r}: only the container's own"
    if str(host.get("Isolation") or "").lower() not in ("", "default"):
        return f"Isolation {host.get('Isolation')!r}"
    if not (_positive(host.get("Memory")) and _positive(host.get("MemorySwap")) and _positive(host.get("PidsLimit"))
            and (_positive(host.get("NanoCpus")) or _positive(host.get("CpuQuota")))):
        return "memory, swap, CPU and process limits are all required"
    if policy.most_memory_bytes and max(host["Memory"], host["MemorySwap"]) > policy.most_memory_bytes:
        return f"memory {host['Memory']} past the most allowed, {policy.most_memory_bytes}"
    if policy.most_nano_cpus and int(host.get("NanoCpus") or 0) > policy.most_nano_cpus:
        return f"CPUs {host.get('NanoCpus')} past the most allowed, {policy.most_nano_cpus}"
    if policy.most_pids and host["PidsLimit"] > policy.most_pids:
        return f"process limit {host['PidsLimit']} past the most allowed, {policy.most_pids}"
    restart = host.get("RestartPolicy") or {}
    if str((restart or {}).get("Name") or "no") not in ("no", ""):
        return f"restart policy {restart.get('Name')!r}"
    log = host.get("LogConfig") or {}
    if str(log.get("Type") or "") not in ("", "json-file", "local") or not _zero(log.get("Config")):
        return f"log driver {log.get('Type')!r}"
    if not isinstance(host.get("OomScoreAdj") or 0, int) or int(host.get("OomScoreAdj") or 0) < 0:
        return "a lower OOM score than the default"
    for key, value in host.items():
        if key not in _CHECKED and not _zero(value):
            return f"HostConfig.{key} {value!r}: the sandbox sets no such option"
    return ""


# --- the request ------------------------------------------------------------------------------------------------

_VERSION = re.compile(r"^/v\d+(?:\.\d+)?(?=/)")
_CONTAINER_CALL = re.compile(r"^/containers/([^/]+)/(attach|start|wait|kill|logs|json|resize)$")


def _image_allowed(reference: str, policy: Policy) -> bool:
    """Whether an image is a sandbox image: one of the prefixes, and nothing after it naming another repository
    (`harness-sandbox-x/anything` would be a Docker Hub user's image)."""
    return any(reference.startswith(prefix) and len(reference) > len(prefix) and "/" not in reference[len(prefix):]
               for prefix in policy.allowed_image_prefixes)


def _a_sandbox_container(identifier: str, policy: Policy) -> bool:
    """A name the sandbox gives, or an id (or a 12-character-or-longer prefix of one) the broker created."""
    if re.match(policy.container_name, identifier):
        return True
    return len(identifier) >= 12 and any(created.startswith(identifier) for created in policy.created)


def decide(method: str, target: str, body: bytes, policy: Policy) -> Decision:
    """Whether to pass on one request: `target` is the request's path and query, `body` its whole body."""
    method = method.upper()
    parts = urlsplit(target)
    path = _VERSION.sub("", unquote(parts.path)).rstrip("/") or "/"
    query = {key: values[-1] for key, values in parse_qs(parts.query).items()}
    if method in ("GET", "HEAD") and path in ("/_ping", "/version", "/info"):
        return allow()
    if method == "POST" and path == "/containers/create":
        name = query.get("name", "")
        if not re.match(policy.container_name, name):
            return refuse(f"a container named {name!r}: only the sandbox's own names")
        try:
            parsed = json.loads(body.decode("utf-8") or "null")
        except (UnicodeDecodeError, ValueError):
            return refuse("the create body is not JSON")
        problem = create_problem(parsed, policy)
        return refuse(problem) if problem else allow(name=name)
    found = _CONTAINER_CALL.match(path)
    if found and ((method == "POST" and found.group(2) not in ("json", "logs"))
                  or (method == "GET" and found.group(2) in ("json", "logs"))):
        if _a_sandbox_container(found.group(1), policy):
            return allow()
        return refuse(f"container {found.group(1)!r} is not one of the sandbox's")
    if method == "DELETE" and path.startswith("/containers/") and path.count("/") == 2:
        identifier = path.split("/")[2]
        if _a_sandbox_container(identifier, policy):
            return allow()
        return refuse(f"container {identifier!r} is not one of the sandbox's")
    if method == "POST" and path == "/images/create":
        reference = query.get("fromImage", "") + (f":{query['tag']}" if query.get("tag") else "")
        if query.get("fromSrc") or not _image_allowed(reference, policy):
            return refuse(f"pulling {reference!r}: only sandbox images")
        return allow()
    if method in ("GET", "HEAD") and path.startswith("/images/") and path.endswith("/json"):
        reference = path[len("/images/"):-len("/json")]
        return allow() if _image_allowed(reference, policy) else refuse(f"image {reference!r} is not a sandbox image")
    return refuse(f"{method} {path} is not a call the sandbox makes")


__all__ = ["DEFAULT_IMAGE_PREFIXES", "Decision", "Policy", "create_problem", "decide"]
