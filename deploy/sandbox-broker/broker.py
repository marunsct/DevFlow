"""The sandbox broker: a Docker API endpoint that passes on only the sandbox's own calls (deep review 2026-11-18, E1b).

Listens where `docker-proxy` did (`DOCKER_HOST=tcp://sandbox-broker:2375`), reads each request whole, asks
`validator.decide` whether the sandbox makes it, and passes it to the Docker socket or answers 403 with the reason in
Docker's own error shape (`{"message": ...}`, which the CLI prints). One request per connection: the request goes on
with `Connection: close`, so nothing after it on the same connection bypasses the check - except `attach`, which
upgrades to a raw stream and carries no further requests. The container ids its creates return are remembered, so
`start`, `attach` and `wait` may name them.

Settings (environment):
    BROKER_WORKSPACE_VOLUME        the data volume holding the runs' workspaces (required)
    BROKER_LISTEN                  host:port to listen on (0.0.0.0:2375)
    DOCKER_SOCKET                  the Docker socket (/var/run/docker.sock)
    BROKER_ALLOWED_IMAGE_PREFIXES  comma-separated (validator.DEFAULT_IMAGE_PREFIXES)
    BROKER_ALLOWED_NETWORKS        comma-separated (none,bridge)
    BROKER_MOST_MEMORY_BYTES, BROKER_MOST_NANO_CPUS, BROKER_MOST_PIDS   upper bounds, 0 for none
    BROKER_ENFORCE                 1 refuses (the default); 0 only logs what it would refuse, to verify a deployment
"""
from __future__ import annotations

import json
import logging
import os
import re
import socket
import socketserver
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validator import DEFAULT_IMAGE_PREFIXES, Policy, decide  # noqa: E402

logger = logging.getLogger("sandbox-broker")

MOST_HEAD_BYTES = 64 * 1024
MOST_BODY_BYTES = 1024 * 1024
_HOP_BY_HOP = frozenset({"connection", "keep-alive", "transfer-encoding", "content-length", "upgrade",
                         "proxy-connection", "proxy-authorization", "te", "trailer"})
_AN_ID = re.compile(rb'"Id"\s*:\s*"([0-9a-f]{64})"')


class BadRequest(Exception):
    pass


def _read_until(connection: socket.socket, buffer: bytearray, marker: bytes, most: int) -> int:
    while True:
        at = buffer.find(marker)
        if at >= 0:
            return at
        if len(buffer) > most:
            raise BadRequest("request head too long")
        chunk = connection.recv(65536)
        if not chunk:
            raise BadRequest("connection closed mid-request")
        buffer.extend(chunk)


def _read_exactly(connection: socket.socket, buffer: bytearray, size: int) -> bytes:
    while len(buffer) < size:
        chunk = connection.recv(65536)
        if not chunk:
            raise BadRequest("connection closed mid-body")
        buffer.extend(chunk)
    taken = bytes(buffer[:size])
    del buffer[:size]
    return taken


def read_request(connection: socket.socket) -> tuple[str, str, str, list[tuple[str, str]], bytes]:
    """(method, target, version, headers, body) of one request, its body read whole (chunked or not)."""
    buffer = bytearray()
    end = _read_until(connection, buffer, b"\r\n\r\n", MOST_HEAD_BYTES)
    head = bytes(buffer[:end]).decode("latin-1")
    del buffer[:end + 4]
    lines = head.split("\r\n")
    try:
        method, target, version = lines[0].split(" ", 2)
    except ValueError as exc:
        raise BadRequest("malformed request line") from exc
    headers = []
    for line in lines[1:]:
        name, _, value = line.partition(":")
        headers.append((name.strip(), value.strip()))
    named = {name.lower(): value for name, value in headers}
    if "chunked" in named.get("transfer-encoding", "").lower():
        body = bytearray()
        while True:
            at = _read_until(connection, buffer, b"\r\n", MOST_HEAD_BYTES)
            size = int(bytes(buffer[:at]).split(b";")[0].strip() or b"0", 16)
            del buffer[:at + 2]
            if size == 0:
                _read_until(connection, buffer, b"\r\n", MOST_HEAD_BYTES)  # the trailer's end
                break
            if len(body) + size > MOST_BODY_BYTES:
                raise BadRequest("request body too long")
            body.extend(_read_exactly(connection, buffer, size))
            _read_exactly(connection, buffer, 2)
        return method, target, version, headers, bytes(body)
    length = int(named.get("content-length", "0") or 0)
    if length > MOST_BODY_BYTES:
        raise BadRequest("request body too long")
    return method, target, version, headers, _read_exactly(connection, buffer, length)


def forwarded_head(method: str, target: str, version: str, headers: list[tuple[str, str]], body: bytes) -> bytes:
    """The request as it goes to Docker: hop-by-hop headers replaced, one request on the connection."""
    upgrade = any(name.lower() == "upgrade" for name, _ in headers)
    lines = [f"{method} {target} {version}"]
    lines += [f"{name}: {value}" for name, value in headers if name.lower() not in _HOP_BY_HOP]
    if body or method in ("POST", "PUT"):
        lines.append(f"Content-Length: {len(body)}")
    lines += ["Connection: Upgrade", "Upgrade: tcp"] if upgrade else ["Connection: close"]
    return ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")


def _refusal(reason: str) -> bytes:
    body = json.dumps({"message": f"refused by the sandbox broker: {reason}"}).encode()
    return (b"HTTP/1.1 403 Forbidden\r\nContent-Type: application/json\r\nConnection: close\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode() + body)


def _pipe(source: socket.socket, target: socket.socket) -> None:
    try:
        while True:
            chunk = source.recv(65536)
            if not chunk:
                break
            target.sendall(chunk)
    except OSError:
        pass
    finally:
        try:
            target.shutdown(socket.SHUT_WR)
        except OSError:
            pass


class Broker(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], policy: Policy, docker_socket: str, enforce: bool) -> None:
        super().__init__(address, _Handler)
        self.policy, self.docker_socket, self.enforce = policy, docker_socket, enforce
        self.lock = threading.Lock()


class _Handler(socketserver.BaseRequestHandler):
    server: Broker

    def handle(self) -> None:
        client = self.request
        try:
            method, target, version, headers, body = read_request(client)
        except (BadRequest, ValueError, OSError) as exc:
            logger.warning("bad request: %s", exc)
            client.sendall(_refusal(str(exc)))
            return
        with self.server.lock:
            decision = decide(method, target, body, self.server.policy)
        if not decision.allowed:
            logger.warning("%s %s %s: %s", "refused" if self.server.enforce else "would refuse", method, target,
                           decision.reason)
            if self.server.enforce:
                client.sendall(_refusal(decision.reason))
                return
        docker = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            docker.connect(self.server.docker_socket)
            docker.sendall(forwarded_head(method, target, version, headers, body) + body)
            if decision.name:
                self._remember_the_container(docker, client)
                return
            upward = None
            if any(name.lower() == "upgrade" for name, _ in headers):
                upward = threading.Thread(target=_pipe, args=(client, docker), daemon=True)
                upward.start()
            _pipe(docker, client)
            if upward is not None:
                upward.join(timeout=5)
        finally:
            docker.close()

    def _remember_the_container(self, docker: socket.socket, client: socket.socket) -> None:
        """Pass a create's answer on whole, keeping the id it gives for the calls that will name it."""
        answer = bytearray()
        while True:
            chunk = docker.recv(65536)
            if not chunk:
                break
            answer.extend(chunk)
        found = _AN_ID.search(bytes(answer))
        if found:
            with self.server.lock:
                self.server.policy.created.add(found.group(1).decode())
        client.sendall(bytes(answer))


def policy_from_the_environment(environment: dict[str, str]) -> Policy:
    volume = environment.get("BROKER_WORKSPACE_VOLUME", "").strip()
    if not volume:
        raise SystemExit("BROKER_WORKSPACE_VOLUME is required: the data volume holding the runs' workspaces")

    def listed(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
        value = environment.get(name, "").strip()
        return tuple(part.strip() for part in value.split(",") if part.strip()) if value else default

    return Policy(
        workspace_volume=volume,
        allowed_image_prefixes=listed("BROKER_ALLOWED_IMAGE_PREFIXES", DEFAULT_IMAGE_PREFIXES),
        allowed_networks=listed("BROKER_ALLOWED_NETWORKS", ("none", "bridge")),
        most_memory_bytes=int(environment.get("BROKER_MOST_MEMORY_BYTES", "0") or 0),
        most_nano_cpus=int(environment.get("BROKER_MOST_NANO_CPUS", "0") or 0),
        most_pids=int(environment.get("BROKER_MOST_PIDS", "0") or 0),
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    policy = policy_from_the_environment(dict(os.environ))
    host, _, port = os.environ.get("BROKER_LISTEN", "0.0.0.0:2375").rpartition(":")
    enforce = os.environ.get("BROKER_ENFORCE", "1").strip().lower() not in ("0", "false", "no", "off")
    server = Broker((host or "0.0.0.0", int(port)), policy, os.environ.get("DOCKER_SOCKET", "/var/run/docker.sock"),
                    enforce)
    logger.info("sandbox broker on %s:%s, volume %s, %s", host, port, policy.workspace_volume,
                "enforcing" if enforce else "logging only")
    server.serve_forever()


if __name__ == "__main__":
    main()
