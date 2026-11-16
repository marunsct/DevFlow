"""The suite writer is told up front that a file the harness keeps is tested by what it does, not by its text.

Measured on the language sweep: a test read `start.sh` and asserted what it contains, in two of the first four
families (one reclassified under dispute, one locked open after five rounds and reopened after drafting). The check
that finds such a test fires only once it fails - before a product exists it can pass against the scaffold's file -
so the writer was told only after the suite was locked.
"""
from __future__ import annotations

import re

from app.acceptance import requests
from app.acceptance.criteria import number
from app.stacks import pack_named

BANNED = re.compile(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _scaffolded(tmp_path):
    from app.stacks import contract

    contract.write(tmp_path, pack_named("node-http-api"), "notes", "Notes", None, scaffolded=True)
    return tmp_path


def test_the_request_names_the_kept_files_and_how_to_test_them(tmp_path):
    root = _scaffolded(tmp_path)
    content = requests.build_author_request(root, number("# Brief\n## Features\n- Add a note\n"))["messages"][-1]["content"]
    rule = requests.kept_files_rule(root)
    assert rule and rule in content
    assert "notes/start.sh" in rule and "text" in rule
    assert not BANNED.search(rule)


def test_with_no_kept_file_there_is_no_rule(tmp_path):
    assert requests.kept_files_rule(tmp_path) == ""
