"""A suite file left out of a request points at the project memory that holds it, not at a read.

Measured on one run: a 58,000-character suite showed 24,000 in the review
request and told the reviewer to read the rest; the project memory held every
file whole, all five reads came back "is in the project memory", and the stall
rule withheld the reviewer's tools - a model call and five tool calls for
nothing.
"""

from __future__ import annotations

import re

from app.acceptance import requests

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _suite(tmp_path, monkeypatch):
    acceptance = tmp_path / "app" / "acceptance"
    acceptance.mkdir(parents=True)
    for n in range(6):
        (acceptance / f"part{n}.spec.js").write_text("// line\n" * 900)
    monkeypatch.setattr(requests.suite, "suite_files", lambda root: sorted(acceptance.glob("*.spec.js")))
    return tmp_path


def test_with_the_memory_on_a_file_left_out_is_in_the_memory(tmp_path, monkeypatch):
    monkeypatch.delenv("PROJECT_MEMORY", raising=False)
    text = requests.suite_text(_suite(tmp_path, monkeypatch))

    assert "it is in the project memory; read it only if the memory names it as not included" in text
    assert "read it with your tools" not in text
    assert not BANNED.search(requests._where_a_file_left_out_is())


def test_with_the_memory_off_it_is_read(tmp_path, monkeypatch):
    monkeypatch.setenv("PROJECT_MEMORY", "off")
    assert "(not shown - read it with your tools)" in requests.suite_text(_suite(tmp_path, monkeypatch))
