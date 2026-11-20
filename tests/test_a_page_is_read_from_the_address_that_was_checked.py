"""A page is read from the very address that was checked, and the agents' page reader is the lookups' page reader.

The harness runs beside private services. A host checked once and then resolved again for the request can answer a
public address to the check and a private one to the connection (DNS rebinding), so the reader resolves a host once
per request, checks every address it has, and connects to the address it checked, naming the host in the request and,
for https, in the TLS handshake and the certificate check.

The agents' `read_web_page` had its own fetch and its own address check beside `page_reader`, so two places decided
whether an address may be read; now `page_reader` reads the page - checks, robots.txt, main text - and the agents'
reader keeps only the cut to the part about a topic, and the paging.
"""
from __future__ import annotations

import io
import ipaddress
import re
import socket
import ssl

import pytest

from app.tools import page_reader, web_search

PUBLIC, PRIVATE = "93.184.215.14", "10.0.0.7"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
PAGE = (b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 21\r\nConnection: close\r\n\r\n"
        b"How to set the cache.")
NO_ROBOTS = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"


class _Peer:
    """One connection's far end: what was sent to it, and the answer it gives."""

    def __init__(self) -> None:
        self.sent = b""
        self._answer: io.BytesIO | None = None

    def _reply(self) -> io.BytesIO:
        if self._answer is None:
            self._answer = io.BytesIO(NO_ROBOTS if b"/robots.txt " in self.sent else PAGE)
        return self._answer

    def sendall(self, data: bytes) -> None:
        self.sent += bytes(data)

    def send(self, data: bytes) -> int:
        self.sendall(data)
        return len(data)

    def makefile(self, *args, **kwargs) -> io.BytesIO:
        return self._reply()

    def recv(self, size: int) -> bytes:
        return self._reply().read(size)

    def settimeout(self, *args) -> None:
        pass

    def setsockopt(self, *args) -> None:
        pass

    def close(self) -> None:
        pass


@pytest.fixture
def network(monkeypatch):
    """The DNS and the network: `turns_private_after(n)` makes docs.example.org answer public to its first n lookups and
    private after; `connected` is every address a connection was made to, and `peers` what each was sent."""
    state = {"public_lookups": 0, "lookups": 0}
    connected: list[tuple[str, int]] = []
    peers: list[_Peer] = []
    for variable in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(variable, raising=False)

    def getaddrinfo(host, port, *args, **kwargs):
        try:
            address = str(ipaddress.ip_address(host))
        except ValueError:
            state["lookups"] += 1
            address = PUBLIC if state["lookups"] <= state["public_lookups"] else PRIVATE
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port or 0))]

    def create_connection(address, *args, **kwargs):
        host, port = address
        connected.append((getaddrinfo(host, port)[0][4][0], port))
        peers.append(_Peer())
        return peers[-1]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(socket, "create_connection", create_connection)

    class Network:
        def turns_private_after(self, lookups: int) -> None:
            state["public_lookups"] = lookups

    net = Network()
    net.connected, net.peers = connected, peers
    return net


@pytest.mark.parametrize("reader", [web_search.read_page, page_reader.read], ids=["agents", "lookups"])
@pytest.mark.parametrize("public_lookups", [1, 2, 3, 4, 5])
def test_a_host_whose_dns_answer_turns_private_is_never_connected_to_at_its_private_address(network, reader,
                                                                                           public_lookups):
    """Rebinding: whichever lookup the host's answer turns private at, no connection reaches the private address."""
    network.turns_private_after(public_lookups)

    reader("http://docs.example.org/guide")

    assert PRIVATE not in [address for address, _ in network.connected]


def test_an_https_page_is_asked_of_the_checked_address_under_the_host_s_own_name(network, monkeypatch):
    """https: the connection goes to the checked address, and the request, the TLS handshake and the certificate
    check all name the host."""
    handshakes = []
    real = ssl.create_default_context

    def create_default_context(*args, **kwargs):
        context = real(*args, **kwargs)

        def wrap_socket(sock, server_hostname=None, **more):
            handshakes.append((server_hostname, context.check_hostname, context.verify_mode))
            return sock

        context.wrap_socket = wrap_socket
        return context

    monkeypatch.setattr(ssl, "create_default_context", create_default_context)
    network.turns_private_after(2)

    page_reader.read("https://docs.example.org/guide")

    assert network.connected and set(network.connected) == {(PUBLIC, 443)}
    assert handshakes and set(handshakes) == {("docs.example.org", True, ssl.CERT_REQUIRED)}
    assert all(b"\r\nHost: docs.example.org\r\n" in peer.sent for peer in network.peers)


# --- one reader: the agents' page reader reads through page_reader ---------------------------------------------------

def _site(pages: dict, robots: tuple = (404, {}, b"")):
    """A web of `pages` (url -> response) whose robots.txt is `robots`; it records each url asked."""
    asked: list[str] = []

    def fetch(url, address):
        asked.append(url)
        return robots if url.endswith("/robots.txt") else pages[url]

    fetch.asked = asked
    return fetch


def _public(host):
    return [PUBLIC]


def test_the_agents_page_reader_obeys_a_site_s_robots_txt():
    site = _site({"https://docs.example.org/guide": (200, {"content-type": "text/plain"}, b"The guide.")},
                 robots=(200, {}, b"User-agent: *\nDisallow: /\n"))

    answer = web_search.read_page("https://docs.example.org/guide", "cache", fetch=site, resolve=_public)

    assert "robots.txt" in answer["error"] and "https://docs.example.org/guide" not in site.asked


def test_the_part_about_a_topic_is_cut_from_the_page_s_main_text():
    page = ("<html><body><nav>Cache pricing cache plans cache</nav><main><h2>Install</h2><p>pip install it</p>"
            "<h2>Cache size</h2><p>Set the cache size with max_entries.</p></main><footer>cache cache</footer>"
            "</body></html>")
    site = _site({"https://docs.example.org/guide": (200, {"content-type": "text/html"}, page.encode())})

    answer = web_search.read_page("https://docs.example.org/guide", "cache size", fetch=site, resolve=_public)

    assert answer["excerpt"] == "## Cache size\n\nSet the cache size with max_entries."
    assert answer["source"] == "https://docs.example.org/guide" and answer["pages"] == 1


def test_a_long_page_read_by_the_agents_comes_in_parts_they_can_ask_for_in_order():
    paragraphs = "".join(f"<p>Paragraph {n}: " + "the cache keeps entries. " * 30 + "</p>" for n in range(30))
    site = _site({"https://docs.example.org/guide": (200, {"content-type": "text/html"},
                                                     f"<html><body>{paragraphs}</body></html>".encode())})

    topic = web_search.read_page("https://docs.example.org/guide", "cache entries", fetch=site, resolve=_public)
    second = web_search.read_page("https://docs.example.org/guide", page=2, fetch=site, resolve=_public)

    assert topic["pages"] == second["pages"] >= 3 and second["page"] == 2
    assert second["excerpt"].startswith("Paragraph ") and not second["excerpt"].startswith("Paragraph 0:")
    assert f"page 1 to {topic['pages']}" in topic["note"]


def test_what_the_agents_page_reader_tells_them_names_none_of_the_banned_words():
    page = "<html><body><main><h2>Cache</h2><p>" + "Set the cache size. " * 600 + "</p></main></body></html>"
    site = _site({"https://docs.example.org/guide": (200, {"content-type": "text/html"}, page.encode())})
    read_web_page = next(t for t in web_search.build_web_tools() if t.name == "read_web_page")

    notes = [web_search.read_page("https://docs.example.org/guide", "cache", fetch=site, resolve=_public)["note"],
             web_search.read_page("https://docs.example.org/guide", page=1, fetch=site, resolve=_public)["note"]]

    assert "page" in read_web_page.args and "part" in read_web_page.description
    assert all(note and not BANNED.search(note) for note in [*notes, read_web_page.description])
