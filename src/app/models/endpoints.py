"""Whether an OpenAI-compatible endpoint is a self-hosted server or a hosted API.

The two want different requests. A self-hosted server - llama.cpp, LM Studio,
vLLM, Ollama - turns thinking on and off through the chat template
(`chat_template_kwargs`), and its replies are retried by the harness's own
client, which asks for less after a reply a proxy cut off. A hosted API knows
nothing of chat templates and may reject a field it does not recognise; its
transient errors, rate limits above all, are what the client's own retries are
for.

The harness used to answer this with `bool(base_url)`: every address was a
llama.cpp server. That held while every run used a local model, and broke on
the first hosted one - a judgement model on a hosted API was sent the template
switch on every call and had no retry for a 429.

Decided from the address, because that is where a server lives: loopback,
private, link-local and carrier-grade-NAT addresses, the container runtimes'
host aliases, single-label names (a service on a compose network or a machine
on a LAN) and the private-use suffixes are self-hosted; everything else is a
hosted API. `OPENAI_ENDPOINT_KIND` (`self-hosted` or `hosted`) settles the
rare server this gets wrong, such as a self-hosted server behind a public name.
"""

from __future__ import annotations

import ipaddress
import os
from typing import Mapping
from urllib.parse import urlparse

#: Names a container runtime gives the machine it runs on.
_HOST_ALIASES = frozenset({
    "localhost",
    "host.docker.internal",
    "gateway.docker.internal",
    "host.containers.internal",
    "host.lima.internal",
})

#: Suffixes reserved, or conventionally used, for names that never resolve on
#: the public internet.
_PRIVATE_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home.arpa", ".ts.net")

#: Carrier-grade NAT space, which `ipaddress` does not count as private and
#: overlay networks such as Tailscale hand out to the machines on them.
_SHARED_ADDRESS_SPACE = ipaddress.ip_network("100.64.0.0/10")

_SELF_HOSTED = frozenset({"self-hosted", "self_hosted", "selfhosted", "local"})
_HOSTED = frozenset({"hosted", "cloud", "remote"})


#: The names a container has for the machine it runs on.
_THE_HOST_FROM_A_CONTAINER = frozenset({"host.docker.internal", "gateway.docker.internal"})


def host_header_for(base_url: str | None) -> dict[str, str]:
    """`{"Host": "localhost:<port>"}` for a server reached from a container by the host's name; else {}.

    A model server on the owner's own machine is reached from the harness's
    container as `host.docker.internal`. A server guarding against DNS
    rebinding answers only to the names it was told it lives at, and
    refused that one: measured with one owner's server, every request was
    403 "Host 'host.docker.internal:9090' is not allowed", while the same
    server answered the owner's `http://127.0.0.1:9090/`. Each request names
    the server as the owner does.
    """
    try:
        parsed = urlparse(str(base_url or "").strip())
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError:
        return {}
    if host not in _THE_HOST_FROM_A_CONTAINER:
        return {}
    return {"Host": f"localhost:{port}" if port else "localhost"}


def is_self_hosted(base_url: str | None, environment: Mapping[str, str] | None = None) -> bool:
    """Whether `base_url` is a self-hosted model server rather than a hosted API."""
    values = os.environ if environment is None else environment
    override = str(values.get("OPENAI_ENDPOINT_KIND") or "").strip().lower()
    if override in _SELF_HOSTED:
        return True
    if override in _HOSTED:
        return False
    try:
        host = (urlparse(str(base_url or "").strip()).hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    if not host:
        return False
    if host in _HOST_ALIASES or host.endswith(_PRIVATE_SUFFIXES):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # A name. One label is a service or a machine on a private network;
        # a public API is always reached through a dotted name.
        return "." not in host
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or (address.version == 4 and address in _SHARED_ADDRESS_SPACE)
    )


#: Where a provider's own API is, for a provider configured without an address.
#: `local` has no provider of its own: LM Studio's default is the conventional
#: guess. Never left blank for `openai`: the OpenAI client falls back to the
#: `OPENAI_BASE_URL` environment variable, which in this deployment names the
#: local server, so a blank address quietly sent a hosted model's requests there.
PROVIDER_ADDRESSES = {
    "local": "http://localhost:1234/v1",
    "openai": "https://api.openai.com/v1",
}


def default_address(provider: str) -> str:
    """The address a provider is reached at when none is configured, or ""."""
    return PROVIDER_ADDRESSES.get(str(provider or "").strip().lower(), "")


__all__ = ["PROVIDER_ADDRESSES", "default_address", "is_self_hosted"]
