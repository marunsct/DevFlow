"""The page reader never reaches a private address, not even through a public page's redirect (plan WL.6).

The harness runs beside private services - the database, the model server, a cloud's metadata service - and a page
it is handed may point at one, or redirect to one. Every hop is resolved and checked before it is requested.
"""
from __future__ import annotations

import pytest

from app.tools import page_reader

ADDRESSES = {"docs.example.org": ["93.184.215.14"], "mirror.example.net": ["2606:2800:220:1::1"],
             "internal.example.org": ["10.0.0.7"], "metadata.example.org": ["169.254.169.254"]}


def _resolve(host):
    return ADDRESSES.get(host, [host])


def _site(pages, sent):
    """A web of `pages` (url -> response); robots.txt is absent everywhere."""
    def fetch(url, address):
        sent.append(url)
        if url.endswith("/robots.txt"):
            return 404, {}, b""
        return pages[url]
    return fetch


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8000/admin", "http://10.1.2.3/", "http://169.254.169.254/latest/meta-data/",
    "http://[::1]/", "http://[::ffff:127.0.0.1]/", "http://224.0.0.1/", "http://0.0.0.0/",
    "https://internal.example.org/notes", "file:///etc/passwd", "https://user:secret@docs.example.org/",
])
def test_a_private_or_unreadable_address_is_refused_without_a_request(url):
    sent = []

    answer = page_reader.read(url, fetch=_site({}, sent), resolve=_resolve)

    assert "error" in answer and sent == []


def test_a_public_page_that_redirects_to_a_private_one_is_refused_at_the_hop():
    sent = []
    pages = {"https://docs.example.org/guide": (302, {"location": "https://metadata.example.org/latest"}, b"")}

    answer = page_reader.read("https://docs.example.org/guide", fetch=_site(pages, sent), resolve=_resolve)

    assert "not on the public internet" in answer["error"] and "metadata.example.org" in answer["error"]
    assert not [url for url in sent if "metadata" in url]


def test_a_redirect_to_a_public_page_is_followed():
    sent = []
    pages = {"https://docs.example.org/old": (301, {"location": "https://mirror.example.net/new"}, b""),
             "https://mirror.example.net/new": (200, {"content-type": "text/plain"}, b"The guide moved here.")}

    answer = page_reader.read("https://docs.example.org/old", fetch=_site(pages, sent), resolve=_resolve)

    assert answer["url"] == "https://mirror.example.net/new" and answer["text"] == "The guide moved here."


def test_more_than_five_redirects_are_not_followed():
    pages = {f"https://docs.example.org/{n}": (302, {"location": f"/{n + 1}"}, b"") for n in range(10)}

    answer = page_reader.read("https://docs.example.org/0", fetch=_site(pages, []), resolve=_resolve)

    assert "redirected more than 5 times" in answer["error"]
