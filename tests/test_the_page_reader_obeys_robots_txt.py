"""The page reader obeys a site's robots.txt for its generic user agent, as the MCP fetch server does (plan WL.6).

RFC 9309: a robots.txt that is missing (4xx) allows everything; one that cannot be reached (5xx, or no answer) is
read as disallowing everything. The user agent names the reader, never who runs it.
"""
from __future__ import annotations

import re

import pytest

from app.tools import page_reader

PAGE = (200, {"content-type": "text/plain"}, b"How to configure the cache.")


def _site(robots, sent):
    def fetch(url):
        sent.append(url)
        if url == "https://docs.example.org/robots.txt":
            if isinstance(robots, Exception):
                raise robots
            return robots
        return PAGE
    return fetch


def _read(url, robots, sent):
    return page_reader.read(url, fetch=_site(robots, sent), resolve=lambda host: ["93.184.215.14"])


@pytest.mark.parametrize("robots", [
    (200, {}, b"User-agent: *\nDisallow: /\n"),
    (200, {}, b"User-agent: *\nDisallow: /guide/\n"),
    (503, {}, b""),
    TimeoutError("robots.txt timed out"),
])
def test_a_page_robots_txt_disallows_or_cannot_answer_for_is_not_read(robots):
    sent = []

    answer = _read("https://docs.example.org/guide/cache", robots, sent)

    assert "robots.txt" in answer["error"]
    assert sent == ["https://docs.example.org/robots.txt"], "the page itself is never requested"


@pytest.mark.parametrize("robots", [
    (200, {}, b"User-agent: *\nDisallow: /private/\n"),
    (404, {}, b""),
    (200, {}, b"User-agent: SomeOtherBot\nDisallow: /\n"),
])
def test_a_page_robots_txt_allows_is_read(robots):
    answer = _read("https://docs.example.org/guide/cache", robots, [])

    assert answer["text"] == "How to configure the cache."


def test_the_user_agent_names_the_reader_and_no_one_s_details():
    assert re.fullmatch(r"[\w.-]+/[\d.]+", page_reader.USER_AGENT)
    assert "@" not in page_reader.USER_AGENT and "http" not in page_reader.USER_AGENT
