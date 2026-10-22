"""Under `CANONICAL_MEMORY` two requests over one code base get the same memory bytes, and the snapshot carries no clock (plan PX.3).

A changed opening was the first break behind 18-25% of uncached input on two
gate runs (PX.1): the memory put the files a request names first, and the
snapshot stamped the time.
"""
from __future__ import annotations

import os
import re
from unittest import mock

from app.agents import project_memory, project_snapshot


def _workspace(tmp_path):
    (tmp_path / ".project-directory").write_text("items-api")
    package = tmp_path / "items-api" / "items_api"
    package.mkdir(parents=True)
    (package / "store.py").write_text("def load():\n    return []\n")
    (package / "routes.py").write_text("from items_api.store import load\n")
    (package / "auth.py").write_text("def sign_in():\n    return 'token'\n")
    return tmp_path


def _two(tmp_path, switch):
    with mock.patch.dict(os.environ, {"CANONICAL_MEMORY": switch}):
        a, _ = project_memory.render(tmp_path, 50_000, focus="Fix items-api/items_api/routes.py")
        b, _ = project_memory.render(tmp_path, 50_000, focus="Fix items-api/items_api/auth.py")
    return a, b


def test_on_two_differently_aimed_requests_share_the_memory(tmp_path):
    a, b = _two(_workspace(tmp_path), "on")
    assert a == b


def test_off_the_named_file_comes_first_as_before(tmp_path):
    a, b = _two(_workspace(tmp_path), "")
    assert a != b


def test_on_the_snapshot_carries_no_clock(tmp_path):
    root = _workspace(tmp_path)
    with mock.patch.dict(os.environ, {"CANONICAL_MEMORY": "on"}):
        text = project_snapshot.project_snapshot(root)
    assert text and not re.search(r"\(\d\d:\d\d:\d\d\)", text) and "as this stage started" in text
