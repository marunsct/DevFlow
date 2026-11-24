"""The page reader reads a site's robots.txt as RFC 9309 says, and asks for it once per host (plan KS.7, LF.1297).

Measured 2026-11-24: Python's standard parser takes `*` and `$` in a rule literally, so GitHub's `Disallow: /*/tree/`
answered "allowed" for every tree page; and robots.txt was fetched again on every read, twice when a page redirected.
"""
from __future__ import annotations

import pytest

from app.tools import page_reader, robots

PAGE = (200, {"content-type": "text/plain"}, b"The page's own words.")


def _site(robots_txt: bytes, sent: list[str]):
    def fetch(url, address):
        sent.append(url)
        if url.endswith("/robots.txt"):
            return 200, {"content-type": "text/plain"}, robots_txt
        return PAGE
    return fetch


def _read(url: str, fetch) -> dict:
    return page_reader.read(url, fetch=fetch, resolve=lambda host: ["140.82.112.3"])


@pytest.mark.parametrize("rule, url", [
    ("Disallow: /*/tree/", "https://code.example.org/owner/repo/tree/main"),
    ("Disallow: /*.atom$", "https://code.example.org/owner/repo/releases.atom"),
    ("Disallow: /search$", "https://code.example.org/search"),
    ("Disallow: /*?tab=*", "https://code.example.org/owner?tab=stars"),
])
def test_a_wildcard_or_end_anchored_rule_refuses_the_page_it_names(rule, url):
    sent: list[str] = []

    answer = _read(url, _site(f"User-agent: *\n{rule}\n".encode(), sent))

    assert "robots.txt" in answer["error"]
    assert not [u for u in sent if not u.endswith("/robots.txt")], "the page itself is never requested"


@pytest.mark.parametrize("rule, url", [
    ("Disallow: /*/tree/", "https://code.example.org/owner/repo/blob/main/README.md"),
    ("Disallow: /search$", "https://code.example.org/search/issues"),
    ("Disallow: /*.atom$", "https://code.example.org/owner/repo/releases.atom.html"),
])
def test_a_wildcard_rule_leaves_the_pages_it_does_not_name_readable(rule, url):
    answer = _read(url, _site(f"User-agent: *\n{rule}\n".encode(), []))

    assert answer["text"] == "The page's own words."


def test_a_second_read_on_the_same_host_does_not_fetch_robots_txt_again():
    sent: list[str] = []
    fetch = _site(b"User-agent: *\nDisallow: /private/\n", sent)

    _read("https://docs.example.org/guide/one", fetch)
    _read("https://docs.example.org/guide/two", fetch)

    assert sent.count("https://docs.example.org/robots.txt") == 1
    assert "https://docs.example.org/guide/two" in sent


def test_a_robots_txt_that_could_not_be_reached_is_asked_again_on_the_next_read():
    sent: list[str] = []
    answers = iter([(503, {}, b""), (200, {}, b"User-agent: *\nDisallow: /private/\n")])

    def fetch(url, address):
        sent.append(url)
        return next(answers) if url.endswith("/robots.txt") else PAGE

    first = _read("https://docs.example.org/guide/one", fetch)
    second = _read("https://docs.example.org/guide/one", fetch)

    assert "robots.txt" in first["error"] and second["text"] == "The page's own words."
    assert sent.count("https://docs.example.org/robots.txt") == 2


@pytest.mark.parametrize("text, url, allowed", [
    # The longest matching rule wins, whichever comes first.
    ("User-agent: *\nAllow: /docs/public/\nDisallow: /docs/\n", "/docs/public/page", True),
    ("User-agent: *\nDisallow: /docs/\nAllow: /docs/public/\n", "/docs/public/page", True),
    ("User-agent: *\nDisallow: /docs/\nAllow: /docs/public/\n", "/docs/private", False),
    # An allow wins a tie in length.
    ("User-agent: *\nDisallow: /page\nAllow: /page\n", "/page", True),
    # A group naming the reader is obeyed instead of the `*` group; several user-agent lines make one group.
    ("User-agent: *\nDisallow: /\n\nUser-agent: other-bot\nUser-agent: software-harness-reader\nAllow: /\n",
     "/anything", True),
    ("User-agent: software-harness-reader\nDisallow: /only/\n\nUser-agent: *\nDisallow: /\n", "/elsewhere", True),
    # No group for the reader and none for everyone: everything is allowed.
    ("User-agent: some-crawler\nDisallow: /\n", "/anything", True),
    # An empty Disallow allows; robots.txt itself is always allowed; percent-encoding compares alike.
    ("User-agent: *\nDisallow:\n", "/anything", True),
    ("User-agent: *\nDisallow: /\n", "/robots.txt", True),
    ("User-agent: *\nDisallow: /a%3cd\n", "/a%3Cd/e", False),
])
def test_the_rules_are_matched_as_rfc_9309_says(text, url, allowed):
    assert robots.parse(text).allows("software-harness-reader/1.0", url) is allowed
