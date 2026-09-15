"""Check the configured model endpoint before a run commits to it.

A model server that is not there produces the same symptom as a model that is
merely slow: nothing happens. Every stage's first call blocks, the run sits at
`running`, and the only way to tell the difference is to go and look at the
host.

Measured on run-18c0e34c: the local `llama-server` was restarted and bound a
different port each time - 8888, then 60847, then 56953 - while the stored
setting kept pointing at the first. The run stalled at
`awaiting_approval:principal_architect` and stayed there for about ten hours,
reporting `running` throughout. Nothing in the pipeline had ever asked whether
the endpoint answered.

This asks, once, at the point a run starts. It is deliberately a *probe*, not a
gate on every call: the question is "is anything serving here", and the honest
answers are yes, no, or "could not tell", never an exception.
"""

from __future__ import annotations

import json
import logging
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

#: Short, because this runs before a run starts and a healthy local server
#: answers `/models` in milliseconds.
PROBE_TIMEOUT_SECONDS = 8


@dataclass(frozen=True)
class EndpointStatus:
    """What the probe found. `reachable` is False only when it is sure."""

    reachable: bool
    detail: str
    checked: str = ""

    def __bool__(self) -> bool:
        return self.reachable


def _is_name_resolution_failure(exc: BaseException) -> bool:
    """Whether this failure is DNS rather than a refused or dead connection."""
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, socket.gaierror):
        return True
    text = str(reason).lower()
    return "name resolution" in text or "name or service not known" in text or "nodename" in text


def _listening(host: str, port: int, timeout: float) -> bool:
    """Whether anything accepts a TCP connection there."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def probe_endpoint(base_url: str, api_key: str = "", *, timeout: int = PROBE_TIMEOUT_SECONDS) -> EndpointStatus:
    """Whether an OpenAI-compatible server is answering at `base_url`.

    Never raises. A hosted provider with no `base_url` is reported reachable:
    there is nothing local to check and refusing to start would be worse than
    the problem this exists to catch.
    """
    if not base_url:
        return EndpointStatus(True, "No base URL is set, so there is nothing local to check.")

    parsed = urlparse(base_url)
    host, port = parsed.hostname, parsed.port
    if not host:
        return EndpointStatus(True, f"Could not read a host out of '{base_url}'; not blocking on it.")
    if port is None:
        port = 443 if parsed.scheme == "https" else 80

    # `host.docker.internal` resolves only inside a container. Outside one the
    # name fails and that says nothing about the server, so the socket check is
    # skipped and the HTTP request decides.
    if _listening(host, port, min(timeout, 3)) is False and host != "host.docker.internal":
        return EndpointStatus(
            False,
            f"Nothing is listening on {host}:{port}. The model server is not running "
            "there, or it restarted on a different port - local servers often pick a "
            "new one each launch. Start it, or update the endpoint in Settings.",
            checked=f"{host}:{port}",
        )

    endpoint = f"{base_url.rstrip('/')}/models"
    request = urllib.request.Request(endpoint, method="GET")
    if api_key:
        request.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = response.read(4096).decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
            served = payload.get("data") or payload.get("models") or []
            names = [str(m.get("id") or m.get("name") or "") for m in served if isinstance(m, dict)]
        except (ValueError, AttributeError):
            names = []
        listed = f" Serving: {', '.join(n for n in names[:3] if n)}." if any(names) else ""
        return EndpointStatus(True, f"The model server answered at {endpoint}.{listed}", endpoint)
    except urllib.error.HTTPError as exc:
        # A 401 or 404 still proves something is serving; only the transport
        # failures below mean "not there".
        return EndpointStatus(
            True,
            f"The server at {endpoint} answered with HTTP {exc.code}, so it is running.",
            endpoint,
        )
    except (urllib.error.URLError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        # `host.docker.internal` is a name the container runtime provides. Where
        # it does not resolve, the prober is simply not inside a container - it
        # has learned nothing about the server, and saying "not there" would
        # refuse every run from a host shell or a test process.
        if host == "host.docker.internal" and _is_name_resolution_failure(exc):
            return EndpointStatus(
                True,
                f"'{host}' does not resolve here, which means this process is not in "
                "a container rather than that the server is down. Not blocking on it.",
                endpoint,
            )
        return EndpointStatus(
            False,
            f"No model server answered at {endpoint} ({reason}). Start it, or update "
            "the endpoint in Settings - a local server that restarted may be on a "
            "different port now.",
            endpoint,
        )


def describe_model_endpoint(settings: object) -> EndpointStatus:
    """Probe whatever endpoint these settings point at. Never raises."""
    try:
        return probe_endpoint(
            str(getattr(settings, "openai_base_url", "") or ""),
            str(getattr(settings, "openai_api_key", "") or ""),
        )
    except Exception:  # noqa: BLE001 - a probe must never be the thing that fails
        logger.warning("The model endpoint probe could not run", exc_info=True)
        return EndpointStatus(True, "The endpoint probe could not run; not blocking on it.")


__all__ = ["EndpointStatus", "describe_model_endpoint", "probe_endpoint"]
