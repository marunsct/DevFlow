"""The page reader returns a page's own words without its menus and scripts, in parts that say which of how many,
and renders a page in a browser only when it answered 403 or builds its text with scripts (plan WL.6).
"""
from __future__ import annotations

from app.tools import page_reader

PUBLIC = ["93.184.215.14"]


def _serving(response, sent=None):
    def fetch(url, address):
        (sent if sent is not None else []).append(url)
        if url.endswith("/robots.txt"):
            return 404, {}, b""
        return response
    return fetch


def _read(response, page=1, render=None, sent=None):
    return page_reader.read("https://docs.example.org/guide", page, fetch=_serving(response, sent),
                            resolve=lambda host: PUBLIC, render=render or (lambda url, resolve: None))


def _html(body):
    return 200, {"content-type": "text/html; charset=utf-8"}, body.encode()


def test_the_main_text_leaves_out_menus_footers_and_scripts():
    answer = _read(_html("<html><head><style>p{}</style></head><body><nav><a>Home</a><a>Pricing</a></nav>"
                         "<main><h1>Caching</h1><p>Set the cache size with <code>max_entries</code>; entries past "
                         "it are dropped oldest first.</p></main>"
                         "<footer>Copyright</footer><script>track()</script></body></html>"))

    assert answer["text"] == "# Caching\n\nSet the cache size with max_entries; entries past it are dropped oldest first."
    assert (answer["page"], answer["pages"]) == (1, 1)


def test_a_long_page_comes_in_parts_that_say_which_of_how_many():
    paragraphs = "".join(f"<p>Paragraph {n}: " + "the cache keeps entries. " * 30 + "</p>" for n in range(30))

    first = _read(_html(f"<html><body>{paragraphs}</body></html>"))
    second = _read(_html(f"<html><body>{paragraphs}</body></html>"), page=2)

    assert first["pages"] == second["pages"] >= 3
    assert len(first["text"]) <= 8_000 and first["text"].startswith("Paragraph 0:")
    assert second["text"].startswith("Paragraph ") and second["text"] not in first["text"]
    assert f"Page 2 of {second['pages']}" in second["note"]


def test_a_script_only_shell_is_rendered_once_in_a_browser():
    rendered = []

    def render(url, resolve):
        rendered.append(url)
        return "Caching: set max_entries."

    answer = _read(_html("<html><body><div id='root'></div><script src='/app.js'></script></body></html>"),
                   render=render)

    assert answer["text"] == "Caching: set max_entries." and rendered == ["https://docs.example.org/guide"]


def test_a_403_page_is_tried_in_a_browser_and_refused_plainly_when_none_is_here():
    shown = _read((403, {"content-type": "text/html"}, b"<html><body>Checking your browser</body></html>"),
                  render=lambda url, resolve: "The guide, after the check.")
    refused = _read((403, {"content-type": "text/html"}, b"<html><body>Checking your browser</body></html>"))

    assert shown["text"] == "The guide, after the check."
    assert "403" in refused["error"] and "text" not in refused


def test_a_page_with_its_own_text_is_never_rendered():
    rendered = []

    _read(_html("<html><body><article><p>" + "Real text about caching. " * 20 + "</p></article>"
                "<script>analytics()</script></body></html>"),
          render=lambda url, resolve: rendered.append(url))

    assert rendered == []


def test_a_file_that_is_not_text_is_not_read():
    answer = _read((200, {"content-type": "application/pdf"}, b"%PDF-1.7"))

    assert "not a text page" in answer["error"]
