"""The model servers behind a load balancer, as the balancer lists them (LF.1579).

Measured: an endpoint of two llama.cpp instances behind one balancer, each started with one slot, served two
requests at once; but `/props` read through the balancer is answered by one instance, so the profile said one slot,
and readiness, the parallel waves, the fan-outs and the model call gate were all sized to one. Earlier two
instances of two slots each read as two, not four.

A balancer is recognised here and nowhere else: each reader in `READERS` asks the address for its own status page
and returns the endpoints it lists, or None when the address is not that balancer. A single server answers none of
them, and keeps the profile its own `/props` gives. An address that answered without a status page is not asked
again in this process.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse

STATUS_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class Endpoint:
    """One server behind the balancer: where it is, as the balancer names it, and whether it takes requests now."""

    url: str
    routable: bool
    name: str = ""


def _get_json(url: str, headers: dict[str, str]) -> Any:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=STATUS_TIMEOUT_SECONDS) as reply:
            return json.load(reply)
    except Exception:  # noqa: BLE001 - an address without the page says nothing
        return None


#: Olla's endpoint states that take requests (its routable states); `offline`, `unhealthy` and `unknown` do not.
_OLLA_ROUTABLE = frozenset({"healthy", "busy", "warming"})


def olla(origin: str, headers: dict[str, str]) -> list[Endpoint] | None:
    """The endpoints olla lists at `/internal/status/endpoints`, or None when `origin` is not olla."""
    body = _get_json(origin + "/internal/status/endpoints", headers)
    entries = body.get("endpoints") if isinstance(body, dict) else None
    if not isinstance(entries, list) or not entries:
        return None
    found = [
        Endpoint(url=str(entry["url"]), name=str(entry.get("name") or ""),
                 routable=str(entry.get("status") or "").strip().lower() in _OLLA_ROUTABLE)
        for entry in entries if isinstance(entry, dict) and entry.get("url")
    ]
    return found or None


#: Each balancer this harness can read, asked in turn; the first that recognises the address lists its endpoints.
READERS: tuple[Callable[[str, dict[str, str]], list[Endpoint] | None], ...] = (olla,)

#: Addresses (scheme and host) that answered as no balancer: not asked again in this process.
_NOT_A_BALANCER: set[str] = set()


def origin_of(base_url: str) -> str:
    """`scheme://host:port` of an address, without its path; "" when it has none."""
    try:
        parsed = urlparse(str(base_url or "").strip())
    except ValueError:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""


def endpoints(origin: str, headers: dict[str, str]) -> list[Endpoint] | None:
    """The endpoints behind the balancer at `origin` (reached as given, with `headers`); None for a single server.

    Never raises."""
    if not origin or origin in _NOT_A_BALANCER:
        return None
    for reader in READERS:
        try:
            found = reader(origin, headers)
        except Exception:  # noqa: BLE001
            found = None
        if found:
            return found
    _NOT_A_BALANCER.add(origin)
    return None


#: Names a machine gives itself: an endpoint the balancer lists at one of them is on the balancer's own machine.
_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0"})


def beside(balancer_url: str, endpoint_url: str) -> tuple[str, bool]:
    """(the endpoint's address as seen from where the balancer's address is seen, whether it is the balancer's host).

    The balancer names its endpoints as it reaches them: `http://127.0.0.1:2001` is on the balancer's machine, so
    from here it is that machine's name at port 2001. In the harness's container the machine is then reached as
    `host.docker.internal` (`app.models.endpoints.reached_from_here`), measured to answer there.
    """
    try:
        balancer, endpoint = urlparse(balancer_url), urlparse(endpoint_url)
        host = (endpoint.hostname or "").lower()
        balancer_host = balancer.hostname or ""
    except ValueError:
        return endpoint_url, False
    if host in _LOOPBACK and balancer_host:
        named = f"[{balancer_host}]" if ":" in balancer_host else balancer_host
        netloc = f"{named}:{endpoint.port}" if endpoint.port else named
        return endpoint._replace(netloc=netloc).geturl(), True
    return endpoint_url, host == balancer_host.lower()


def forget() -> None:
    _NOT_A_BALANCER.clear()


__all__ = ["Endpoint", "READERS", "beside", "endpoints", "forget", "olla", "origin_of"]
