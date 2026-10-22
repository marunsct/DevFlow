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
#: The names the owner's machine has for itself.
_THIS_MACHINE = frozenset({"localhost", "127.0.0.1", "::1"})


def _in_a_container() -> bool:
    """Whether this process runs in a container (`/.dockerenv`), unless told otherwise."""
    told = str(os.environ.get("MODEL_LOCALHOST_IS_THIS_CONTAINER") or "").strip().lower()
    if told in {"1", "true", "yes", "on"}:
        return False
    return os.path.exists("/.dockerenv")


def reached_from_here(base_url: str | None) -> tuple[str, dict[str, str]]:
    """(the address to connect to, the headers to send) for a model server at `base_url`.

    A server on the owner's machine is reached from the harness's container as
    `host.docker.internal`, and an address the owner writes as `localhost`
    reaches the container itself there - one owner's setting of
    `http://localhost:9090/v1` was "connection refused" on every call. Such an
    address is reached through the host's name. And a server guarding against
    DNS rebinding answers only to the names it was told it lives at:
    measured with that owner's server, every request by the host's name was
    403 "Host 'host.docker.internal:9090' is not allowed", while it answered
    `http://127.0.0.1:9090/`. So each request names the server as its owner
    does.
    """
    text = str(base_url or "").strip()
    try:
        parsed = urlparse(text)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError:
        return text, {}
    named = f"{host}:{port}" if port else host
    if host in _THIS_MACHINE and _in_a_container():
        netloc = parsed.netloc.replace(parsed.hostname or host, "host.docker.internal", 1)
        if host == "::1":
            netloc = f"host.docker.internal:{port}" if port else "host.docker.internal"
        return parsed._replace(netloc=netloc).geturl(), {"Host": named if host != "::1" else (f"localhost:{port}" if port else "localhost")}
    if host in _THE_HOST_FROM_A_CONTAINER:
        return text, {"Host": f"localhost:{port}" if port else "localhost"}
    return text, {}


def host_header_for(base_url: str | None) -> dict[str, str]:
    """The headers `reached_from_here` sends for `base_url`."""
    return reached_from_here(base_url)[1]


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
