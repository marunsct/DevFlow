"""The sandbox broker passes on only the sandbox's own Docker calls and container creates (deep review 2026-11-18, E1b).

Found in the deep review: the worker reached Docker through a socket proxy allowing `CONTAINERS=1, POST=1`, which
filters by endpoint and never reads a body, so a create with a bind mount of the host's root, `Privileged: true` or
the host's network passed it. The broker (`deploy/sandbox-broker`, not deployed yet) reads each create and passes on
only one shaped like `SandboxExecutor._run`'s `docker run`; every other call but the few that `docker run --rm` and
`docker kill` make is refused.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import socket
import sys
import threading
from pathlib import Path

import pytest

BROKER = Path(__file__).resolve().parents[1] / "deploy" / "sandbox-broker"
VOLUME = "langchain_appdata"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, BROKER / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


validator = _load("validator")


def _policy(**kwargs):
    return validator.Policy(workspace_volume=VOLUME, **kwargs)


def _create(**host) -> dict:
    """The body the Docker CLI sends for the sandbox's `docker run`, with `host` replacing HostConfig fields."""
    body = {
        "Hostname": "", "Domainname": "", "User": "1000:1000", "AttachStdin": False, "AttachStdout": True,
        "AttachStderr": True, "Tty": False, "OpenStdin": False, "StdinOnce": False,
        "Env": ["HOME=/workspace/.agent-home", "TMPDIR=/workspace/.agent-home/tmp", "ACCEPTANCE_PORT=41234"],
        "Cmd": ["npm", "test"], "Image": "harness-sandbox-python:pw1.64.0", "Volumes": None,
        "WorkingDir": "/workspace/notes", "Entrypoint": None, "OnBuild": None, "Labels": {},
        "HostConfig": {
            "Binds": None, "ContainerIDFile": "", "LogConfig": {"Type": "", "Config": {}}, "NetworkMode": "none",
            "PortBindings": {}, "RestartPolicy": {"Name": "no", "MaximumRetryCount": 0}, "AutoRemove": True,
            "VolumeDriver": "", "VolumesFrom": None, "ConsoleSize": [0, 0], "CapAdd": None, "CapDrop": ["ALL"],
            "CgroupnsMode": "", "Dns": [], "DnsOptions": [], "DnsSearch": [], "ExtraHosts": None, "GroupAdd": None,
            "IpcMode": "", "Cgroup": "", "Links": None, "OomScoreAdj": 0, "PidMode": "", "Privileged": False,
            "PublishAllPorts": False, "ReadonlyRootfs": True, "SecurityOpt": ["no-new-privileges"],
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,size=256m"}, "UTSMode": "", "UsernsMode": "", "ShmSize": 0,
            "Isolation": "", "CpuShares": 0, "Memory": 1073741824, "NanoCpus": 2000000000, "CgroupParent": "",
            "BlkioWeight": 0, "BlkioWeightDevice": [], "CpuPeriod": 0, "CpuQuota": 0, "CpusetCpus": "",
            "Devices": [], "DeviceCgroupRules": None, "DeviceRequests": None, "MemoryReservation": 0,
            "MemorySwap": 1073741824, "MemorySwappiness": None, "OomKillDisable": False, "PidsLimit": 512,
            "Ulimits": None, "Mounts": [{"Type": "volume", "Source": VOLUME, "Target": "/workspace",
                                         "VolumeOptions": {"Subpath": "workspaces/run-a/repo"}}],
            "MaskedPaths": None, "ReadonlyPaths": None,
        },
        "NetworkingConfig": {"EndpointsConfig": {"none": {}}},
    }
    body["HostConfig"].update(host)
    return body


def _decide_create(body: dict, name: str = "sandbox-0123456789ab", policy=None):
    return validator.decide("POST", f"/v1.47/containers/create?name={name}", json.dumps(body).encode(),
                            policy or _policy())


def test_the_sandbox_s_own_create_passes():
    assert _decide_create(_create()).allowed
    with_network = _create(NetworkMode="bridge")
    with_network["NetworkingConfig"] = {"EndpointsConfig": {"bridge": {}}}
    assert _decide_create(with_network).allowed


def _with(path: str, value):
    body = _create()
    target = body
    keys = path.split(".")
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    return body


@pytest.mark.parametrize("path, value", [
    ("HostConfig.Privileged", True),
    ("HostConfig.CapAdd", ["SYS_ADMIN"]),
    ("HostConfig.CapDrop", []),
    ("HostConfig.SecurityOpt", ["no-new-privileges", "seccomp=unconfined"]),
    ("HostConfig.SecurityOpt", ["apparmor=unconfined"]),
    ("HostConfig.ReadonlyRootfs", False),
    ("HostConfig.Binds", ["/:/host"]),
    ("HostConfig.Binds", ["/var/run/docker.sock:/var/run/docker.sock"]),
    ("HostConfig.Mounts", [{"Type": "bind", "Source": "/", "Target": "/workspace"}]),
    ("HostConfig.Mounts", [{"Type": "volume", "Source": "another_volume", "Target": "/workspace",
                            "VolumeOptions": {"Subpath": "x"}}]),
    ("HostConfig.Mounts", [{"Type": "volume", "Source": VOLUME, "Target": "/workspace",
                            "VolumeOptions": {"Subpath": "../../"}}]),
    ("HostConfig.Mounts", [{"Type": "volume", "Source": VOLUME, "Target": "/workspace"}]),
    ("HostConfig.Mounts", [{"Type": "volume", "Source": VOLUME, "Target": "/workspace", "VolumeOptions": {
        "Subpath": "workspaces/a", "DriverConfig": {"Name": "local", "Options": {"o": "bind", "device": "/"}}}}]),
    ("HostConfig.Mounts", [{"Type": "volume", "Source": VOLUME, "Target": "/workspace",
                            "VolumeOptions": {"Subpath": "a"}},
                           {"Type": "volume", "Source": VOLUME, "Target": "/data", "VolumeOptions": {"Subpath": "b"}}]),
    ("HostConfig.Tmpfs", {"/tmp": "rw", "/etc": "rw"}),
    ("HostConfig.NetworkMode", "host"),
    ("HostConfig.NetworkMode", "container:langchain-worker-1"),
    ("NetworkingConfig", {"EndpointsConfig": {"none": {}, "langchain_default": {}}}),
    ("HostConfig.PidMode", "host"),
    ("HostConfig.IpcMode", "host"),
    ("HostConfig.UsernsMode", "host"),
    ("HostConfig.Devices", [{"PathOnHost": "/dev/sda", "PathInContainer": "/dev/sda", "CgroupPermissions": "rwm"}]),
    ("HostConfig.DeviceRequests", [{"Driver": "nvidia", "Count": -1}]),
    ("HostConfig.Sysctls", {"kernel.core_pattern": "|/x"}),
    ("HostConfig.PortBindings", {"22/tcp": [{"HostPort": "2222"}]}),
    ("HostConfig.VolumesFrom", ["langchain-worker-1"]),
    ("HostConfig.Runtime", "runsc-debug"),
    ("HostConfig.CgroupParent", "/"),
    ("HostConfig.Memory", 0),
    ("HostConfig.MemorySwap", 0),
    ("HostConfig.NanoCpus", 0),
    ("HostConfig.PidsLimit", 0),
    ("HostConfig.PidsLimit", -1),
    ("HostConfig.RestartPolicy", {"Name": "always"}),
    ("HostConfig.LogConfig", {"Type": "syslog", "Config": {"syslog-address": "tcp://x:514"}}),
    ("User", ""),
    ("User", "0:0"),
    ("User", "root"),
    ("Image", "alpine:3"),
    ("Image", "harness-sandbox-x/evil:latest"),
    ("Entrypoint", ["/bin/sh"]),
])
def test_a_create_the_sandbox_would_not_make_is_refused(path, value):
    decision = _decide_create(_with(path, value))

    assert decision.allowed is False and decision.reason


def test_a_create_without_host_config_is_refused():
    body = _create()
    del body["HostConfig"]
    assert _decide_create(body).allowed is False


def test_a_container_name_not_the_sandbox_s_is_refused():
    assert _decide_create(_create(), name="anything").allowed is False


def test_a_create_past_the_set_limits_is_refused():
    policy = _policy(most_memory_bytes=512 * 1024**2, most_pids=256)
    assert _decide_create(_create(), policy=policy).allowed is False
    assert _decide_create(_create(Memory=256 * 1024**2, MemorySwap=256 * 1024**2, PidsLimit=128), policy=policy).allowed


@pytest.mark.parametrize("method, target, allowed", [
    ("GET", "/_ping", True),
    ("HEAD", "/v1.47/_ping", True),
    ("GET", "/v1.47/version", True),
    ("POST", "/v1.47/containers/sandbox-0123456789ab/attach?stderr=1&stdout=1&stream=1", True),
    ("POST", "/v1.47/containers/sandbox-0123456789ab/start", True),
    ("POST", "/v1.47/containers/sandbox-0123456789ab/wait?condition=removed", True),
    ("POST", "/v1.47/containers/sandbox-0123456789ab/kill", True),
    ("DELETE", "/v1.47/containers/sandbox-0123456789ab?force=1", True),
    ("POST", "/v1.47/containers/langchain-worker-1/kill", False),
    ("DELETE", "/v1.47/containers/langchain-db-1", False),
    ("POST", "/v1.47/containers/sandbox-0123456789ab/exec", False),
    ("POST", "/v1.47/containers/sandbox-0123456789ab/archive", False),
    ("PUT", "/v1.47/containers/sandbox-0123456789ab/archive?path=/", False),
    ("POST", "/v1.47/images/create?fromImage=harness-sandbox-python&tag=pw1.64.0", True),
    ("POST", "/v1.47/images/create?fromImage=alpine&tag=3", False),
    ("POST", "/v1.47/images/create?fromSrc=-&repo=harness-sandbox-x", False),
    ("GET", "/v1.47/images/harness-sandbox-python:pw1.64.0/json", True),
    ("POST", "/v1.47/build", False),
    ("POST", "/v1.47/volumes/create", False),
    ("POST", "/v1.47/networks/langchain_default/connect", False),
    ("GET", "/v1.47/containers/json", False),
    ("POST", "/v1.47/swarm/init", False),
])
def test_only_the_calls_the_sandbox_makes_pass(method, target, allowed):
    assert validator.decide(method, target, b"", _policy()).allowed is allowed


def test_a_container_the_broker_created_may_be_named_by_its_id():
    policy = _policy()
    full = "f" * 64
    assert validator.decide("POST", f"/containers/{full}/start", b"", policy).allowed is False
    policy.created.add(full)
    assert validator.decide("POST", f"/containers/{full}/start", b"", policy).allowed
    assert validator.decide("POST", f"/containers/{full[:12]}/wait", b"", policy).allowed


# --- through the broker itself ----------------------------------------------------------------------------------

class _FakeDocker:
    """A Docker socket that records each request it reads and answers a create with an id."""

    def __init__(self, path: Path) -> None:
        self.requests: list[bytes] = []
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(path))
        self.server.listen(8)
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while True:
            try:
                connection, _ = self.server.accept()
            except OSError:
                return
            data = b""
            while b"\r\n\r\n" not in data:
                data += connection.recv(65536)
            head, _, rest = data.partition(b"\r\n\r\n")
            length = next((int(line.split(b":")[1]) for line in head.split(b"\r\n")
                           if line.lower().startswith(b"content-length:")), 0)
            while len(rest) < length:
                rest += connection.recv(65536)
            self.requests.append(head + b"\r\n\r\n" + rest[:length])
            answer = json.dumps({"Id": "a" * 64, "Warnings": []}).encode()
            connection.sendall(b"HTTP/1.1 201 Created\r\nContent-Type: application/json\r\n"
                               + f"Content-Length: {len(answer)}\r\n\r\n".encode() + answer)
            connection.close()


@pytest.fixture
def broker(tmp_path):
    broker_module = _load("broker")
    docker = _FakeDocker(tmp_path / "docker.sock")
    server = broker_module.Broker(("127.0.0.1", 0), _policy(), str(tmp_path / "docker.sock"), enforce=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1], docker
    server.shutdown()
    docker.server.close()


def _ask(port: int, request: bytes) -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=5) as connection:
        connection.sendall(request)
        answer = b""
        while chunk := connection.recv(65536):
            answer += chunk
    return answer


def _post(target: str, body: bytes, extra: bytes = b"") -> bytes:
    return (f"POST {target} HTTP/1.1\r\nHost: docker\r\nContent-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n\r\n").encode() + body + extra


def test_a_privileged_create_never_reaches_docker(broker):
    port, docker = broker

    answer = _ask(port, _post("/v1.47/containers/create?name=sandbox-0123456789ab",
                              json.dumps(_create(Privileged=True)).encode()))

    assert answer.startswith(b"HTTP/1.1 403") and b"Privileged" in answer
    assert docker.requests == []


def test_the_sandbox_s_create_reaches_docker_and_its_id_may_then_be_started(broker):
    port, docker = broker

    created = _ask(port, _post("/v1.47/containers/create?name=sandbox-0123456789ab", json.dumps(_create()).encode()))
    started = _ask(port, _post(f"/v1.47/containers/{'a' * 64}/start", b""))

    assert created.startswith(b"HTTP/1.1 201") and started.startswith(b"HTTP/1.1 201")
    assert len(docker.requests) == 2
    assert b"Connection: close" in docker.requests[0]


def test_a_second_request_on_the_same_connection_does_not_slip_past_the_check(broker):
    port, docker = broker
    smuggled = _post("/v1.47/containers/create?name=sandbox-0123456789ab", json.dumps(_create(Privileged=True)).encode())

    _ask(port, _post("/v1.47/containers/create?name=sandbox-0123456789ab", json.dumps(_create()).encode(), smuggled))

    assert len(docker.requests) == 1
    assert b'"Privileged": true' not in docker.requests[0]
